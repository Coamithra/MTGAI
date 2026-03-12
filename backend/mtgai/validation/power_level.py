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

DOWNSIDE_PATTERNS = [
    re.compile(r"\bcan't block\b", re.IGNORECASE),
    re.compile(r"\bdefender\b", re.IGNORECASE),
    re.compile(r"\benters .+ tapped\b", re.IGNORECASE),
    re.compile(r"\bsacrifice ~\b", re.IGNORECASE),
    re.compile(r"\byou lose \d+ life\b", re.IGNORECASE),
    re.compile(r"\b~ doesn't untap\b", re.IGNORECASE),
]

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

# P+T thresholds indexed by (rarity, category) -> max allowed = CMC + delta
# Category: "vanilla" (no abilities), "abilities" (has abilities), "downside"
_PT_THRESHOLDS: dict[Rarity, dict[str, int | None]] = {
    Rarity.COMMON: {"vanilla": 3, "abilities": 2, "downside": 4},
    Rarity.UNCOMMON: {"vanilla": 4, "abilities": 3, "downside": 5},
    Rarity.RARE: {"vanilla": 5, "abilities": 4, "downside": None},
    Rarity.MYTHIC: {"vanilla": None, "abilities": None, "downside": None},
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


def _has_downside(oracle_text: str) -> bool:
    return any(pat.search(oracle_text) for pat in DOWNSIDE_PATTERNS)


def _count_keyword_abilities(oracle_text: str) -> int:
    """Count how many distinct evergreen keyword abilities appear."""
    text_lower = oracle_text.lower()
    return sum(1 for kw in EVERGREEN_KEYWORDS if kw in text_lower)


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
    # 1. Creature P+T vs CMC
    # ------------------------------------------------------------------
    if is_creature and _is_numeric(card.power) and _is_numeric(card.toughness):
        p = int(card.power)  # type: ignore[arg-type]
        t = int(card.toughness)  # type: ignore[arg-type]
        pt = p + t

        thresholds = _PT_THRESHOLDS.get(card.rarity)
        if thresholds is not None:
            has_abilities = bool(oracle.strip())
            downside = _has_downside(oracle)

            if downside:
                category = "downside"
            elif has_abilities:
                category = "abilities"
            else:
                category = "vanilla"

            delta = thresholds[category]
            if delta is not None and pt > cmc + delta:
                errors.append(
                    _manual(
                        "power/toughness",
                        f"Power {p} + Toughness {t} = {pt} on a CMC {cmc} "
                        f"{card.rarity.value} creature exceeds "
                        f"P+T <= CMC+{delta} guideline",
                        "Consider raising the mana cost or lowering stats.",
                        error_code="power_level.overstatted",
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
