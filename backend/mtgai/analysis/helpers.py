"""Utility functions shared across balance analyzers.

Handles type_line parsing, mechanic detection, removal/CA pattern matching,
and creature size classification.
"""

from __future__ import annotations

import re

from mtgai.models.card import Card
from mtgai.models.enums import CardType, Supertype

WUBRG_ORDER = ["W", "U", "B", "R", "G"]

# Evergreen keywords that define "french vanilla" creatures
EVERGREEN_KEYWORDS = {
    "deathtouch",
    "defender",
    "double strike",
    "first strike",
    "flash",
    "flying",
    "haste",
    "hexproof",
    "indestructible",
    "lifelink",
    "menace",
    "protection",
    "reach",
    "trample",
    "vigilance",
    "ward",
}

# Card types as strings (for matching against type_line)
CARD_TYPE_VALUES = {t.value for t in CardType}
SUPERTYPE_VALUES = {t.value for t in Supertype}

# Separator pattern for type_line: em dash, en dash, or double hyphen
_TYPE_LINE_SEP = re.compile(r"\s*(?:\u2014|\u2013|--)\s*")


def parse_card_types_from_type_line(type_line: str) -> list[str]:
    """Extract main card types from a type_line string.

    Handles supertypes (Legendary, Basic) and subtypes (after the dash).
    Returns only main card types matching CardType enum values.

    >>> parse_card_types_from_type_line("Legendary Artifact Creature -- Construct")
    ['Artifact', 'Creature']
    >>> parse_card_types_from_type_line("Instant")
    ['Instant']
    """
    parts = _TYPE_LINE_SEP.split(type_line, maxsplit=1)
    main_part = parts[0].strip()
    words = main_part.split()

    card_types: list[str] = []
    for word in words:
        # Title-case the word for matching
        w = word.strip().title()
        if w in CARD_TYPE_VALUES and w not in SUPERTYPE_VALUES:
            card_types.append(w)

    # Handle edge case: words after separator that are actually card types
    # e.g. "Legendary Enchantment -- Artifact" where Artifact is after the dash
    if len(parts) > 1:
        after_dash = parts[1].strip().split()
        for word in after_dash:
            w = word.strip().title()
            if w in CARD_TYPE_VALUES and w not in card_types:
                card_types.append(w)

    return card_types


def is_creature(card: Card) -> bool:
    """Check if a card is a creature (from card_types or type_line)."""
    if card.card_types and "Creature" in card.card_types:
        return True
    return "Creature" in parse_card_types_from_type_line(card.type_line)


def get_card_types(card: Card) -> list[str]:
    """Get card types, preferring the card_types field, falling back to type_line parsing."""
    if card.card_types:
        return card.card_types
    return parse_card_types_from_type_line(card.type_line)


def infer_skeleton_color(card: Card) -> str:
    """Map a card's colors to the skeleton color convention.

    [] -> "colorless"
    ["W"] -> "W"
    ["W", "U"] -> "multicolor"
    """
    if not card.colors:
        return "colorless"
    if len(card.colors) == 1:
        return card.colors[0].value
    return "multicolor"


def infer_skeleton_color_pair(card: Card) -> str | None:
    """For multicolor cards, derive the color pair string in WUBRG order.

    Returns None for mono/colorless cards.
    """
    if len(card.colors) < 2:
        return None
    sorted_colors = sorted(card.colors, key=lambda c: WUBRG_ORDER.index(c.value))
    return "".join(c.value for c in sorted_colors)


# Thresholds for complexity classification by rules text length (characters).
# Derived from analysis of 60-card ASD dev set — natural breakpoints in the data.
_VANILLA_MAX = 0
_FRENCH_VANILLA_MAX = 15
_EVERGREEN_MAX = 90

# Matches parenthesized reminder text: "(This creature can't block.)"
_REMINDER_RE = re.compile(r"\s*\([^)]*\)\.?")


def _rules_text_length(oracle_text: str) -> int:
    """Length of oracle text after stripping reminder text in parentheses."""
    return len(_REMINDER_RE.sub("", oracle_text).strip())


def classify_mechanic_complexity(card: Card) -> str:
    """Classify a card's complexity tier by rules text length.

    Returns one of: vanilla, french_vanilla, evergreen, complex.

    Thresholds (characters of rules text, excluding reminder text):
    - vanilla: 0 chars (no rules text)
    - french_vanilla: 1-15 chars (single keyword like "Flying")
    - evergreen: 16-90 chars (simple ETB, removal spell, tap ability)
    - complex: 91+ chars (multi-part effects, triggers, build-arounds)
    """
    length = _rules_text_length(card.oracle_text)

    if length <= _VANILLA_MAX:
        return "vanilla"
    if length <= _FRENCH_VANILLA_MAX:
        return "french_vanilla"
    if length <= _EVERGREEN_MAX:
        return "evergreen"
    return "complex"


# ---------------------------------------------------------------------------
# Removal detection
# ---------------------------------------------------------------------------

_REMOVAL_PATTERNS = [
    r"destroy target (creature|permanent|artifact|enchantment|planeswalker)",
    r"exile target (creature|permanent|artifact|enchantment|planeswalker)",
    r"deals? \d+ damage to",
    r"gets? [+-]\d+/-\d+",
    r"target creature gets -\d+/-\d+",
    r"return target \w+ to its owner's hand",
    r"counter target (spell|creature spell|noncreature spell)",
    r"fights? target",
    r"deals? damage equal to its power to target",
    r"enchanted creature can't attack or block",
    r"enchanted creature can't attack",
    r"tap target creature\. it doesn't untap",
    r"sacrifice a creature",
]

_REMOVAL_RE = re.compile("|".join(_REMOVAL_PATTERNS), re.IGNORECASE)


def detect_removal(oracle_text: str) -> bool:
    """Check if oracle text contains removal-like patterns."""
    return bool(_REMOVAL_RE.search(oracle_text))


# ---------------------------------------------------------------------------
# Card advantage detection
# ---------------------------------------------------------------------------

_CA_PATTERNS = [
    r"draw (a|one|two|three|\d+) cards?",
    r"create .+ creature tokens?",
    r"create .+ artifact tokens?",
    r"create .+ treasure tokens?",
    r"create .+ food tokens?",
    r"scry \d+",
    r"surveil \d+",
    r"return .+ from .+ graveyard to .+ (hand|battlefield)",
    r"exile the top .+ cards? .+ (play|cast) (it|them)",
    r"look at the top .+ cards? of your library",
    r"search your library for",
]

_CA_RE = re.compile("|".join(_CA_PATTERNS), re.IGNORECASE)


def detect_card_advantage(oracle_text: str) -> bool:
    """Check if oracle text contains card-advantage patterns."""
    return bool(_CA_RE.search(oracle_text))


# ---------------------------------------------------------------------------
# Mana fixing detection
# ---------------------------------------------------------------------------

_FIXING_PATTERNS = [
    r"add .+ mana of any",
    r"add \{[WUBRGC]\} or \{[WUBRGC]\}",
    r"add one mana of any color",
    r"search your library for a basic land",
    r"create .+ treasure token",
    r"any color",
]

_FIXING_RE = re.compile("|".join(_FIXING_PATTERNS), re.IGNORECASE)


def detect_mana_fixing(card: Card) -> bool:
    """Check if a card provides mana fixing."""
    text = card.oracle_text
    if _FIXING_RE.search(text):
        return True
    # Multi-color lands that tap for mana
    types = get_card_types(card)
    return "Land" in types and len(card.color_identity) > 1


# ---------------------------------------------------------------------------
# Creature size classification
# ---------------------------------------------------------------------------


def creature_weight_class(power: str | None, toughness: str | None) -> str:
    """Classify creature size by P+T sum.

    small: 1-2, medium: 3-4, beefy: 5-6, huge: 7+
    Returns "n/a" for non-numeric P/T (e.g. "*").
    """
    if power is None or toughness is None:
        return "n/a"
    try:
        total = int(power) + int(toughness)
    except ValueError:
        return "n/a"

    if total <= 2:
        return "small"
    if total <= 4:
        return "medium"
    if total <= 6:
        return "beefy"
    return "huge"
