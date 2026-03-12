"""Validator 7: Color Pie Consistency.

Checks that a card's abilities are consistent with its colors using a lookup
table of ability categories mapped to their primary and secondary colors.
All checks are MANUAL — color pie bends are flagged for review, never
auto-fixed.
"""

from __future__ import annotations

import re

from mtgai.models.card import Card
from mtgai.validation import ValidationError, ValidationSeverity

# ---------------------------------------------------------------------------
# Color pie ability map
# ---------------------------------------------------------------------------

COLOR_PIE_MAP: dict[str, dict] = {
    "direct_damage": {
        "patterns": [r"deals? \d+ damage to", r"~ deals damage equal to"],
        "primary": ["R"],
        "secondary": ["B"],
    },
    "destroy_creature": {
        "patterns": [r"destroy target creature", r"destroy all creatures"],
        "primary": ["B"],
        "secondary": ["W"],
    },
    "exile_creature": {
        "patterns": [
            r"exile target creature",
            r"exile target (?:nonland )?permanent",
        ],
        "primary": ["W"],
        "secondary": [],
    },
    "counterspell": {
        "patterns": [r"counter target spell", r"counter target .+ spell"],
        "primary": ["U"],
        "secondary": [],
    },
    "bounce": {
        "patterns": [
            r"return target .+ to .+ hand",
            r"return .+ to their owners?'? hands?",
        ],
        "primary": ["U"],
        "secondary": ["W"],
    },
    "card_draw": {
        "patterns": [r"draw (?:a|two|three|\d+) cards?"],
        "primary": ["U"],
        "secondary": ["B", "G"],
    },
    "tutor": {
        "patterns": [r"search your library for"],
        "primary": ["B"],
        "secondary": ["W", "G"],
    },
    "mana_ramp": {
        "patterns": [
            r"search your library for .+ land",
            r"put .+ land .+ onto the battlefield",
        ],
        "primary": ["G"],
        "secondary": [],
    },
    "lifegain": {
        "patterns": [r"gains? \d+ life", r"you gain .+ life"],
        "primary": ["W"],
        "secondary": ["B", "G"],
    },
    "life_drain": {
        "patterns": [r"loses? \d+ life", r"each opponent loses"],
        "primary": ["B"],
        "secondary": [],
    },
    "reanimation": {
        "patterns": [r"return .+ from .+ graveyard to the battlefield"],
        "primary": ["B"],
        "secondary": ["W"],
    },
    "land_destruction": {
        "patterns": [r"destroy target land", r"destroy all lands"],
        "primary": ["R"],
        "secondary": [],
    },
    "discard": {
        "patterns": [
            r"target (?:player|opponent) discards?",
            r"each opponent discards?",
        ],
        "primary": ["B"],
        "secondary": [],
    },
    "flying": {
        "patterns": [r"(?m)^\s*[Ff]lying\b"],
        "primary": ["W", "U"],
        "secondary": ["B"],
    },
    "first_strike": {
        "patterns": [r"\bfirst strike\b", r"\bdouble strike\b"],
        "primary": ["W", "R"],
        "secondary": [],
    },
    "trample": {
        "patterns": [r"\btrample\b"],
        "primary": ["G"],
        "secondary": ["R"],
    },
    "deathtouch": {
        "patterns": [r"\bdeathtouch\b"],
        "primary": ["B", "G"],
        "secondary": [],
    },
    "haste": {
        "patterns": [r"\bhaste\b"],
        "primary": ["R"],
        "secondary": ["B", "G"],
    },
    "vigilance": {
        "patterns": [r"\bvigilance\b"],
        "primary": ["W", "G"],
        "secondary": [],
    },
    "lifelink": {
        "patterns": [r"\blifelink\b"],
        "primary": ["W", "B"],
        "secondary": [],
    },
    "menace": {
        "patterns": [r"\bmenace\b"],
        "primary": ["B", "R"],
        "secondary": [],
    },
    "reach": {
        "patterns": [r"\breach\b"],
        "primary": ["G"],
        "secondary": ["W", "R"],
    },
    "hexproof": {
        "patterns": [r"\bhexproof\b"],
        "primary": ["U", "G"],
        "secondary": [],
    },
    "indestructible": {
        "patterns": [r"\bindestructible\b"],
        "primary": ["W"],
        "secondary": [],
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _manual(
    field: str, message: str, suggestion: str | None = None, *, error_code: str
) -> ValidationError:
    return ValidationError(
        validator="color_pie",
        severity=ValidationSeverity.MANUAL,
        field=field,
        message=message,
        suggestion=suggestion,
        error_code=error_code,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_color_pie(card: Card) -> list[ValidationError]:
    """Check that a card's abilities are consistent with its colors."""
    if not card.oracle_text:
        return []

    # Colorless artifacts get a pass
    if not card.colors and "Artifact" in card.card_types:
        return []

    errors: list[ValidationError] = []
    card_colors = {c.value for c in card.colors}

    for ability_name, ability in COLOR_PIE_MAP.items():
        primary: list[str] = ability["primary"]
        secondary: list[str] = ability["secondary"]
        allowed = set(primary + secondary)

        if not allowed:
            continue

        for pattern in ability["patterns"]:
            if re.search(pattern, card.oracle_text, re.IGNORECASE | re.MULTILINE):
                if not card_colors & allowed:
                    primary_str = "/".join(primary)
                    colors_str = "/".join(sorted(card_colors)) if card_colors else "colorless"
                    errors.append(
                        _manual(
                            "oracle_text",
                            f'Card is {colors_str} but has "{ability_name}" '
                            f"which is primarily {primary_str}",
                            error_code=f"color_pie.{ability_name}",
                        )
                    )
                break  # Don't double-report for the same category

    return errors
