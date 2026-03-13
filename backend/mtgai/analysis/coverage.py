"""Set-wide coverage analysis.

Checks creature CMC curve, creature size distribution, removal density,
card advantage, mana fixing, mechanic distribution, and color balance.
"""

from __future__ import annotations

import re
from collections import defaultdict

from mtgai.analysis.helpers import (
    WUBRG_ORDER,
    creature_weight_class,
    detect_card_advantage,
    detect_mana_fixing,
    detect_removal,
    is_creature,
)
from mtgai.analysis.models import (
    AnalysisIssue,
    AnalysisSeverity,
    ColorCoverageResult,
    CreatureSizeEntry,
    MechanicDistribution,
)
from mtgai.models.card import Card

# CMC range we expect creatures to cover per color (1 through 6+)
_EXPECTED_CMC_RANGE = range(1, 7)


def _cards_by_color(cards: list[Card]) -> dict[str, list[Card]]:
    """Group cards by mono-color. Multicolor cards go under each of their colors."""
    by_color: dict[str, list[Card]] = defaultdict(list)
    for card in cards:
        if not card.colors:
            by_color["colorless"].append(card)
        else:
            for c in card.colors:
                by_color[c.value].append(card)
    return dict(by_color)


def _has_mechanic(oracle_text: str, mechanic_name: str) -> bool:
    """Check if oracle text mentions a mechanic name (case-insensitive word boundary)."""
    pattern = re.compile(rf"\b{re.escape(mechanic_name)}\b", re.IGNORECASE)
    return bool(pattern.search(oracle_text))


def analyze_color_coverage(
    cards: list[Card],
    mechanic_names: set[str],
    functional_tags: dict[str, list[str]],
) -> tuple[list[ColorCoverageResult], list[AnalysisIssue]]:
    """Per-color analysis: creature curve, size distribution, removal, card advantage."""
    by_color = _cards_by_color(cards)
    results: list[ColorCoverageResult] = []
    issues: list[AnalysisIssue] = []

    # Mechanics that provide removal or card advantage
    removal_mechanics = {name for name, tags in functional_tags.items() if "removal" in tags}
    ca_mechanics = {name for name, tags in functional_tags.items() if "card_advantage" in tags}

    for color in [*WUBRG_ORDER, "colorless"]:
        color_cards = by_color.get(color, [])
        if not color_cards:
            continue

        creatures = [c for c in color_cards if is_creature(c)]

        # Creature CMC buckets
        cmc_buckets: dict[int, int] = defaultdict(int)
        for c in creatures:
            bucket = min(int(c.cmc), 6)  # 6+ lumped together
            bucket = max(bucket, 0)
            cmc_buckets[bucket] += 1

        # Find CMC gaps (only for colors with enough creatures to be meaningful)
        cmc_gaps: list[int] = []
        if len(creatures) >= 3 and color != "colorless":
            for cmc_val in _EXPECTED_CMC_RANGE:
                if cmc_buckets.get(cmc_val, 0) == 0:
                    cmc_gaps.append(cmc_val)
                    issues.append(
                        AnalysisIssue(
                            check="coverage.cmc_gap",
                            severity=AnalysisSeverity.WARN,
                            message=(f"{color} has no creature at CMC {cmc_val}"),
                            expected=">=1",
                            actual="0",
                        )
                    )

        # Creature size distribution
        size_counts: dict[str, int] = defaultdict(int)
        for c in creatures:
            wc = creature_weight_class(c.power, c.toughness)
            size_counts[wc] += 1
        sizes = [
            CreatureSizeEntry(weight_class=wc, count=cnt) for wc, cnt in sorted(size_counts.items())
        ]

        # Removal counting (regex + mechanic tags)
        removal_cards: list[str] = []
        for c in color_cards:
            if detect_removal(c.oracle_text) or any(
                _has_mechanic(c.oracle_text, m) for m in removal_mechanics
            ):
                removal_cards.append(c.name)

        # Card advantage counting (regex + mechanic tags)
        ca_cards: list[str] = []
        for c in color_cards:
            has_ca = detect_card_advantage(c.oracle_text) or any(
                _has_mechanic(c.oracle_text, m) for m in ca_mechanics
            )
            if has_ca and c.name not in ca_cards:
                ca_cards.append(c.name)

        # Warn if a color has zero removal (at common/uncommon)
        common_uncommon = [c for c in color_cards if c.rarity.value in ("common", "uncommon")]
        cu_removal = [
            c
            for c in common_uncommon
            if detect_removal(c.oracle_text)
            or any(_has_mechanic(c.oracle_text, m) for m in removal_mechanics)
        ]
        if not cu_removal and color in WUBRG_ORDER:
            issues.append(
                AnalysisIssue(
                    check="coverage.removal_density",
                    severity=AnalysisSeverity.WARN,
                    message=f"{color} has no removal at common/uncommon",
                    expected=">=1",
                    actual="0",
                )
            )

        results.append(
            ColorCoverageResult(
                color=color,
                total_cards=len(color_cards),
                total_creatures=len(creatures),
                creature_cmc_buckets=dict(cmc_buckets),
                creature_cmc_gaps=cmc_gaps,
                creature_sizes=sizes,
                removal_count=len(removal_cards),
                removal_cards=removal_cards,
                card_advantage_count=len(ca_cards),
                card_advantage_cards=ca_cards,
            )
        )

    return results, issues


def analyze_mechanic_distribution(
    cards: list[Card],
    mechanics: list[dict],
) -> tuple[list[MechanicDistribution], list[AnalysisIssue]]:
    """Compare actual mechanic usage against planned distribution."""
    results: list[MechanicDistribution] = []
    issues: list[AnalysisIssue] = []

    for mech in mechanics:
        name = mech["name"]
        planned = mech.get("distribution", {})
        total_planned = sum(planned.values())

        # Count actual usage by scanning oracle text
        actual: dict[str, int] = defaultdict(int)
        for card in cards:
            if _has_mechanic(card.oracle_text, name):
                rarity = card.rarity.value if hasattr(card.rarity, "value") else str(card.rarity)
                actual[rarity] += 1
        total_actual = sum(actual.values())

        dist = MechanicDistribution(
            mechanic_name=name,
            planned=planned,
            actual=dict(actual),
            total_planned=total_planned,
            total_actual=total_actual,
        )
        results.append(dist)

        # Check for significant deviation
        if total_planned > 0:
            diff = total_actual - total_planned
            if diff > total_planned:
                issues.append(
                    AnalysisIssue(
                        check="coverage.mechanic_over",
                        severity=AnalysisSeverity.WARN,
                        message=(
                            f"{name} over-represented: planned {total_planned}, got {total_actual}"
                        ),
                        expected=str(total_planned),
                        actual=str(total_actual),
                    )
                )
            elif total_actual == 0:
                issues.append(
                    AnalysisIssue(
                        check="coverage.mechanic_missing",
                        severity=AnalysisSeverity.FAIL,
                        message=(f"{name} not used at all (planned {total_planned})"),
                        expected=str(total_planned),
                        actual="0",
                    )
                )
            elif diff < -1:
                issues.append(
                    AnalysisIssue(
                        check="coverage.mechanic_under",
                        severity=AnalysisSeverity.WARN,
                        message=(
                            f"{name} under-represented: planned {total_planned}, got {total_actual}"
                        ),
                        expected=str(total_planned),
                        actual=str(total_actual),
                    )
                )

    return results, issues


def analyze_mana_fixing(cards: list[Card]) -> list[str]:
    """Identify all mana-fixing sources, return card names."""
    return [card.name for card in cards if detect_mana_fixing(card)]


def analyze_color_balance(
    cards: list[Card],
) -> tuple[dict[str, int], list[AnalysisIssue]]:
    """Check that card counts per mono-color are roughly even.

    Only counts mono-color cards (multicolor and colorless excluded from balance check).
    Mean is computed across all 5 colors (including those with 0 cards).
    """
    counts: dict[str, int] = {}
    for color in WUBRG_ORDER:
        counts[color] = 0
    for card in cards:
        if len(card.colors) == 1:
            counts[card.colors[0].value] += 1

    issues: list[AnalysisIssue] = []

    values = list(counts.values())
    if sum(values) == 0:
        return counts, issues

    mean = sum(values) / len(values)

    for color, count in sorted(counts.items()):
        diff = abs(count - mean)
        if diff >= 3:
            issues.append(
                AnalysisIssue(
                    check="coverage.color_balance",
                    severity=AnalysisSeverity.WARN,
                    message=(
                        f"{color} has {count} mono-color cards (mean {mean:.1f}, diff {diff:.1f})"
                    ),
                    expected=f"~{mean:.0f}",
                    actual=str(count),
                )
            )

    return dict(counts), issues
