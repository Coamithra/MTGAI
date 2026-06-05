"""Validator 6: Power-Level Heuristics.

Checks power/toughness vs CMC balance, NWO (New World Order) complexity for
commons, and removal spell efficiency. All checks are MANUAL — they flag
cards for human/AI review but never auto-fix.
"""

from __future__ import annotations

import re

from mtgai.models.card import Card
from mtgai.models.enums import Rarity
from mtgai.validation import ValidationError, ValidationSeverity

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EVERGREEN_KEYWORDS = {
    "deathtouch",
    "defender",
    "double strike",
    "enchant",
    "equip",
    "first strike",
    "flash",
    "flying",
    "haste",
    "hexproof",
    "indestructible",
    "lifelink",
    "menace",
    "reach",
    "trample",
    "vigilance",
    "ward",
    "protection",
}

NWO_VIOLATION_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"choose (?:one|two|three)", re.IGNORECASE),
        "Modal abilities are too complex for common",
        "power_level.nwo_modal",
    ),
    (
        re.compile(r"whenever (?:a|an|another) creature dies", re.IGNORECASE),
        "Global death triggers are too complex for common",
        "power_level.nwo_death_trigger",
    ),
    (
        re.compile(r"whenever (?:a|an) (?:creature|permanent) enters", re.IGNORECASE),
        "Global ETB triggers are too complex for common",
        "power_level.nwo_etb_trigger",
    ),
    (
        re.compile(r"\bfor each\b", re.IGNORECASE),
        "Counting effects are too complex for common",
        "power_level.nwo_for_each",
    ),
    (
        re.compile(r"search your library", re.IGNORECASE),
        "Tutoring is too complex for common",
        "power_level.nwo_tutor",
    ),
]

# Fair vanilla power/toughness by mana value, derived from REAL printed cards
# (not a hand-rolled formula). Source query, reproducible:
#   (is:vanilla or is:frenchvanilla) t:creature game:paper -t:token -is:funny
# (~1397 cards on Scryfall) keeping each (power, toughness) printed on >=3 distinct
# cards, so one-off freaks (e.g. Gigantosaurus 10/10-for-5) drop out. Used only as a
# soft HINT to the AI design reviewer (see classify_pt + the wording in the
# heuristic consumers) — color intensity, downsides and pushed rarity legitimately
# move real fairness and this body-only frontier cannot see them.
FAIR_VANILLA_PT: dict[int, frozenset[tuple[int, int]]] = {
    0: frozenset({(0, 1)}),
    1: frozenset({(1, 1), (0, 3), (1, 2), (2, 1), (0, 4), (2, 2)}),
    2: frozenset(
        {
            (1, 1),
            (1, 2),
            (2, 1),
            (0, 4),
            (1, 3),
            (2, 2),
            (3, 1),
            (0, 5),
            (1, 4),
            (2, 3),
            (3, 2),
            (4, 1),
            (3, 3),
        }
    ),
    3: frozenset(
        {
            (1, 1),
            (1, 2),
            (2, 1),
            (1, 3),
            (2, 2),
            (3, 1),
            (0, 5),
            (1, 4),
            (2, 3),
            (3, 2),
            (4, 1),
            (1, 5),
            (2, 4),
            (3, 3),
            (4, 2),
            (0, 7),
            (3, 4),
        }
    ),
    4: frozenset(
        {
            (2, 1),
            (2, 2),
            (3, 1),
            (2, 3),
            (3, 2),
            (1, 5),
            (2, 4),
            (3, 3),
            (4, 2),
            (5, 1),
            (1, 6),
            (2, 5),
            (3, 4),
            (4, 3),
            (5, 2),
            (4, 4),
            (4, 5),
        }
    ),
    5: frozenset(
        {
            (3, 1),
            (3, 2),
            (2, 4),
            (3, 3),
            (4, 2),
            (2, 5),
            (3, 4),
            (4, 3),
            (6, 1),
            (3, 5),
            (4, 4),
            (5, 3),
            (6, 2),
            (3, 6),
            (4, 5),
            (5, 4),
            (6, 3),
            (5, 5),
            (7, 3),
        }
    ),
    6: frozenset(
        {
            (3, 3),
            (3, 4),
            (4, 3),
            (4, 4),
            (3, 6),
            (4, 5),
            (5, 4),
            (4, 6),
            (5, 5),
            (6, 4),
            (5, 6),
            (6, 5),
            (6, 6),
            (7, 6),
        }
    ),
    7: frozenset({(4, 4), (5, 5), (6, 4), (5, 6), (6, 5), (6, 6), (6, 7), (7, 7), (8, 8)}),
    8: frozenset({(6, 6), (7, 6)}),
}

# How far the OVER ceiling rises by rarity above the common (common-printed) max.
# A pushed rare/mythic vanilla is fine; mythic is uncapped (a splashy mythic body
# never flags OVER). The UNDER floor is rarity-independent — a weak rare is still weak.
RARITY_CEIL_BONUS: dict[Rarity, int | None] = {
    Rarity.COMMON: 0,
    Rarity.UNCOMMON: 1,
    Rarity.RARE: 3,
    Rarity.MYTHIC: None,
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _manual(
    field: str, message: str, suggestion: str | None = None, *, error_code: str
) -> ValidationError:
    return ValidationError(
        validator="power_level",
        severity=ValidationSeverity.MANUAL,
        field=field,
        message=message,
        suggestion=suggestion,
        error_code=error_code,
    )


def _is_numeric(value: str | None) -> bool:
    """Return True if *value* is a plain integer (possibly negative)."""
    if value is None:
        return False
    try:
        int(value)
        return True
    except ValueError:
        return False


def _count_keyword_abilities(oracle_text: str) -> int:
    """Count how many distinct evergreen keyword abilities appear."""
    text_lower = oracle_text.lower()
    return sum(1 for kw in EVERGREEN_KEYWORDS if kw in text_lower)


def _fair_band(cmc: int) -> tuple[frozenset[tuple[int, int]], int, int] | None:
    """Fair vanilla pairs + (floor_total, common_ceil_total) for a mana value.

    Returns ``None`` for mana values with no usable basis (no hint emitted). For
    mana values past the sampled range a band with an empty pair set is returned,
    extrapolated as ``P+T`` in ``[2*cmc-3, 2*cmc+2]`` (no dominance data).
    """
    pairs = FAIR_VANILLA_PT.get(cmc)
    if pairs:
        totals = [p + t for p, t in pairs]
        return pairs, min(totals), max(totals)
    if cmc >= 9:
        return frozenset(), 2 * cmc - 3, 2 * cmc + 2
    return None


def classify_pt(cmc: int, power: int, toughness: int, rarity: Rarity) -> str:
    """Classify a VANILLA creature's body as ``"over"`` / ``"under"`` / ``"fair"``.

    Checks the card against the printed-vanilla frontier (:data:`FAIR_VANILLA_PT`):
    a body is OVER when it exceeds every fair pair on both axes *and* its total
    beats the rarity-adjusted ceiling; UNDER when it is below every fair pair on
    both axes *and* under the floor. Mythic is never OVER. This is a hint only —
    color intensity, downsides and pushed rarity (which it can't see) move real
    fairness, so callers must frame it as guidance, not a rule.
    """
    band = _fair_band(cmc)
    if band is None:
        return "fair"
    pairs, floor_total, common_ceil = band
    total = power + toughness
    bonus = RARITY_CEIL_BONUS.get(rarity, 0)

    if not pairs:  # extrapolated band beyond the sample — total-only
        if bonus is not None and total > common_ceil + bonus:
            return "over"
        if total < floor_total:
            return "under"
        return "fair"

    covered_above = any(sp >= power and st >= toughness for sp, st in pairs)
    covered_below = any(sp <= power and st <= toughness for sp, st in pairs)
    if bonus is not None and not covered_above and total > common_ceil + bonus:
        return "over"
    if not covered_below and total < floor_total:
        return "under"
    return "fair"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def validate_power_level(card: Card) -> list[ValidationError]:
    """Run power-level heuristic checks. All findings are MANUAL severity."""
    errors: list[ValidationError] = []

    is_creature = "Creature" in card.card_types
    is_planeswalker = "Planeswalker" in card.card_types
    cmc = card.cmc
    oracle = card.oracle_text or ""

    # ------------------------------------------------------------------
    # 1. Vanilla creature P/T vs the printed-vanilla frontier (HINT only)
    # ------------------------------------------------------------------
    # Only VANILLA creatures (no rules text): an ability-bearing creature pays for
    # its ability in stats, which this body-only frontier can't weigh, so we leave
    # those to the reviewer. The finding is a soft hint (consumers frame it as
    # guidance, not a rule) — color intensity, downsides and pushed rarity all
    # legitimately move fair stats and ``classify_pt`` cannot see them.
    if (
        is_creature
        and not oracle.strip()
        and _is_numeric(card.power)
        and _is_numeric(card.toughness)
    ):
        p = int(card.power)  # type: ignore[arg-type]
        t = int(card.toughness)  # type: ignore[arg-type]
        verdict = classify_pt(int(cmc), p, t, card.rarity)
        band = _fair_band(int(cmc))
        if verdict in ("over", "under") and band is not None:
            pairs, floor_total, common_ceil = band
            if verdict == "over":
                examples = ", ".join(
                    f"{sp}/{st}" for sp, st in sorted(pairs, key=lambda x: -(x[0] + x[1]))[:3]
                )
                message = (
                    f"P/T {p}/{t} is bigger than printed {int(cmc)}-mana vanillas, "
                    f"which top out around {common_ceil} total"
                    + (f" (e.g. {examples})" if examples else "")
                    + ". Rough hint only -- color cost, downsides or pushed rarity "
                    "may well justify it."
                )
            else:
                examples = ", ".join(
                    f"{sp}/{st}" for sp, st in sorted(pairs, key=lambda x: x[0] + x[1])[:3]
                )
                message = (
                    f"P/T {p}/{t} is below printed {int(cmc)}-mana vanillas, "
                    f"which start around {floor_total} total"
                    + (f" (e.g. {examples})" if examples else "")
                    + ". Rough hint only."
                )
            errors.append(
                _manual(
                    "power/toughness",
                    message,
                    error_code=f"power_level.pt_{verdict}",
                )
            )

    # ------------------------------------------------------------------
    # 2. Negative P/T
    # ------------------------------------------------------------------
    if is_creature and _is_numeric(card.power) and _is_numeric(card.toughness):
        p = int(card.power)  # type: ignore[arg-type]
        t = int(card.toughness)  # type: ignore[arg-type]
        if p < 0 or t < 0:
            errors.append(
                _manual(
                    "power/toughness",
                    f"Negative power ({p}) or toughness ({t}) is extremely "
                    f"rare, verify intentional",
                    error_code="power_level.negative_pt",
                )
            )

    # ------------------------------------------------------------------
    # 3. NWO complexity for commons
    # ------------------------------------------------------------------
    if card.rarity == Rarity.COMMON:
        # 3a. Multiple keyword abilities
        kw_count = _count_keyword_abilities(oracle)
        if kw_count > 1:
            errors.append(
                _manual(
                    "oracle_text",
                    f"Common has {kw_count} keyword abilities; NWO suggests at most 1",
                    "Consider moving this card to uncommon or removing a keyword.",
                    error_code="power_level.nwo_multiple_keywords",
                )
            )

        # 3b. NWO violation patterns
        for pattern, reason, code in NWO_VIOLATION_PATTERNS:
            if pattern.search(oracle):
                errors.append(
                    _manual(
                        "oracle_text",
                        reason,
                        "Consider moving this card to uncommon or simplifying.",
                        error_code=code,
                    )
                )

    # ------------------------------------------------------------------
    # 4. Removal efficiency
    # ------------------------------------------------------------------
    if (
        cmc <= 1
        and re.search(r"destroy target creature", oracle, re.IGNORECASE)
        and card.rarity in (Rarity.COMMON, Rarity.UNCOMMON)
    ):
        errors.append(
            _manual(
                "oracle_text",
                f"CMC {cmc} unconditional creature removal at "
                f"{card.rarity.value} is very efficient",
                "Consider adding a restriction or raising the mana cost.",
                error_code="power_level.cheap_removal",
            )
        )

    # ------------------------------------------------------------------
    # 5. Planeswalker loyalty vs CMC
    # ------------------------------------------------------------------
    if is_planeswalker and _is_numeric(card.loyalty):
        loyalty = int(card.loyalty)  # type: ignore[arg-type]
        if abs(loyalty - cmc) > 2:
            errors.append(
                _manual(
                    "loyalty",
                    f"Starting loyalty {loyalty} on a CMC {cmc} planeswalker "
                    f"deviates from typical range (CMC +/- 2)",
                    "Verify the loyalty value is intentional.",
                    error_code="power_level.pw_loyalty_deviation",
                )
            )

    # ------------------------------------------------------------------
    # 6. Zero CMC nonland
    # ------------------------------------------------------------------
    if cmc == 0 and "Land" not in card.card_types:
        errors.append(
            _manual(
                "cmc",
                "Zero-CMC nonland cards require careful balance review",
                "Ensure the card is not too impactful for free.",
                error_code="power_level.zero_cmc",
            )
        )

    return errors
