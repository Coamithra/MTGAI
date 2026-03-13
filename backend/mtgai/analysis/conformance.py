"""Skeleton conformance analysis -- per-slot checks.

For each skeleton slot, finds the generated card and verifies:
color, rarity, card type, CMC proximity, and mechanic complexity tier.
"""

from __future__ import annotations

from mtgai.analysis.helpers import (
    classify_mechanic_complexity,
    get_card_types,
    infer_skeleton_color,
    infer_skeleton_color_pair,
)
from mtgai.analysis.models import AnalysisIssue, AnalysisSeverity, SlotConformanceResult
from mtgai.models.card import Card
from mtgai.skeleton.generator import SkeletonSlot


def check_slot_conformance(
    card: Card,
    slot: SkeletonSlot,
) -> SlotConformanceResult:
    """Check if a generated card conforms to its skeleton slot."""
    issues: list[AnalysisIssue] = []

    # 1. Color match
    card_color = infer_skeleton_color(card)
    if card_color != slot.color:
        issues.append(
            AnalysisIssue(
                check="conformance.color",
                severity=AnalysisSeverity.FAIL,
                slot_id=slot.slot_id,
                card_name=card.name,
                message=f"Color mismatch: slot expects {slot.color}, card is {card_color}",
                expected=slot.color,
                actual=card_color,
            )
        )

    # For multicolor, also check the color pair
    if slot.color == "multicolor" and slot.color_pair:
        card_pair = infer_skeleton_color_pair(card)
        if card_pair and card_pair != slot.color_pair:
            issues.append(
                AnalysisIssue(
                    check="conformance.color_pair",
                    severity=AnalysisSeverity.FAIL,
                    slot_id=slot.slot_id,
                    card_name=card.name,
                    message=(
                        f"Color pair mismatch: slot expects {slot.color_pair}, card is {card_pair}"
                    ),
                    expected=slot.color_pair,
                    actual=card_pair,
                )
            )

    # 2. Rarity match
    card_rarity = card.rarity.value if hasattr(card.rarity, "value") else str(card.rarity)
    if card_rarity != slot.rarity:
        issues.append(
            AnalysisIssue(
                check="conformance.rarity",
                severity=AnalysisSeverity.FAIL,
                slot_id=slot.slot_id,
                card_name=card.name,
                message=f"Rarity mismatch: slot expects {slot.rarity}, card is {card_rarity}",
                expected=slot.rarity,
                actual=card_rarity,
            )
        )

    # 3. Card type match
    card_types = get_card_types(card)
    card_types_lower = [t.lower() for t in card_types]
    slot_type = slot.card_type.lower()
    if slot_type not in card_types_lower:
        issues.append(
            AnalysisIssue(
                check="conformance.card_type",
                severity=AnalysisSeverity.WARN,
                slot_id=slot.slot_id,
                card_name=card.name,
                message=(
                    f"Card type mismatch: slot expects {slot.card_type},"
                    f" card types are {card_types}"
                ),
                expected=slot.card_type,
                actual=", ".join(card_types),
            )
        )

    # 4. CMC proximity
    cmc_diff = abs(card.cmc - slot.cmc_target)
    if cmc_diff >= 2:
        issues.append(
            AnalysisIssue(
                check="conformance.cmc",
                severity=AnalysisSeverity.FAIL,
                slot_id=slot.slot_id,
                card_name=card.name,
                message=(
                    f"CMC off by {cmc_diff:.0f}: slot targets {slot.cmc_target},"
                    f" card is {card.cmc:.0f}"
                ),
                expected=str(slot.cmc_target),
                actual=str(int(card.cmc)),
            )
        )
    elif cmc_diff >= 1:
        issues.append(
            AnalysisIssue(
                check="conformance.cmc",
                severity=AnalysisSeverity.WARN,
                slot_id=slot.slot_id,
                card_name=card.name,
                message=(
                    f"CMC off by {cmc_diff:.0f}: slot targets {slot.cmc_target},"
                    f" card is {card.cmc:.0f}"
                ),
                expected=str(slot.cmc_target),
                actual=str(int(card.cmc)),
            )
        )

    # 5. Mechanic complexity tier
    card_tier = classify_mechanic_complexity(card)
    slot_tier = slot.mechanic_tag
    if card_tier != slot_tier:
        # Complexity mismatch is a WARN not FAIL -- the LLM has some creative latitude
        issues.append(
            AnalysisIssue(
                check="conformance.mechanic_tier",
                severity=AnalysisSeverity.WARN,
                slot_id=slot.slot_id,
                card_name=card.name,
                message=(
                    f"Complexity tier mismatch: slot expects {slot_tier},"
                    f" card classified as {card_tier}"
                ),
                expected=slot_tier,
                actual=card_tier,
            )
        )

    return SlotConformanceResult(
        slot_id=slot.slot_id,
        card_name=card.name,
        matched=len(issues) == 0,
        issues=issues,
    )


def analyze_conformance(
    cards: list[Card],
    slots: list[SkeletonSlot],
) -> tuple[list[SlotConformanceResult], list[AnalysisIssue]]:
    """Match cards to slots by slot_id, then check each pair.

    Returns (per-slot results, aggregated issues).
    Cards without a slot_id (e.g. lands) are skipped.
    Unmatched slots (no card generated) are reported.
    """
    card_by_slot: dict[str, Card] = {}
    for card in cards:
        if card.slot_id:
            card_by_slot[card.slot_id] = card

    results: list[SlotConformanceResult] = []
    all_issues: list[AnalysisIssue] = []

    for slot in slots:
        card = card_by_slot.get(slot.slot_id)
        if card is None:
            issue = AnalysisIssue(
                check="conformance.missing_card",
                severity=AnalysisSeverity.FAIL,
                slot_id=slot.slot_id,
                message=f"No card generated for slot {slot.slot_id}",
            )
            results.append(
                SlotConformanceResult(
                    slot_id=slot.slot_id,
                    matched=False,
                    issues=[issue],
                )
            )
            all_issues.append(issue)
        else:
            result = check_slot_conformance(card, slot)
            results.append(result)
            all_issues.extend(result.issues)

    return results, all_issues
