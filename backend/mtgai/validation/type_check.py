"""Validator 3: Type-Line / Stat Consistency.

Catches structural impossibilities that LLMs frequently produce, such as
creatures without power/toughness, planeswalkers without loyalty, auras
missing "Enchant", and equipment missing "Equip".
"""

from __future__ import annotations

import re

from mtgai.models.card import Card
from mtgai.validation import ValidationError, ValidationSeverity

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _manual(
    field: str, message: str, suggestion: str | None = None, *, error_code: str
) -> ValidationError:
    return ValidationError(
        validator="type_check",
        severity=ValidationSeverity.MANUAL,
        field=field,
        message=message,
        suggestion=suggestion,
        error_code=error_code,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def validate_type_consistency(card: Card) -> list[ValidationError]:
    """Check that the card's type line, stats, and abilities are consistent."""
    errors: list[ValidationError] = []

    is_creature = "Creature" in card.card_types
    is_planeswalker = "Planeswalker" in card.card_types
    has_power = card.power is not None
    has_toughness = card.toughness is not None
    has_loyalty = card.loyalty is not None
    has_faces = card.card_faces is not None and len(card.card_faces) > 0

    # 1. Creatures must have power and toughness
    if is_creature and (not has_power or not has_toughness):
        errors.append(
            _manual(
                "power/toughness",
                "Creature is missing power and/or toughness",
                "Set power and toughness for this creature.",
                error_code="type_check.creature_missing_pt",
            )
        )

    # 2. Non-creatures must NOT have power/toughness (skip DFCs)
    if not is_creature and (has_power or has_toughness) and not has_faces:
        errors.append(
            _manual(
                "power/toughness",
                "Non-creature card has power and/or toughness set",
                "Remove power/toughness from non-creature cards.",
                error_code="type_check.noncreature_has_pt",
            )
        )

    # 3. Planeswalkers must have loyalty
    if is_planeswalker and not has_loyalty:
        errors.append(
            _manual(
                "loyalty",
                "Planeswalker is missing starting loyalty",
                "Set starting loyalty for this planeswalker.",
                error_code="type_check.pw_missing_loyalty",
            )
        )

    # 4. Non-planeswalkers must NOT have loyalty
    if not is_planeswalker and has_loyalty:
        errors.append(
            _manual(
                "loyalty",
                "Non-planeswalker card has loyalty set",
                "Remove loyalty from non-planeswalker cards.",
                error_code="type_check.non_pw_has_loyalty",
            )
        )

    # 5. Instants and sorceries must NOT have power/toughness
    if ("Instant" in card.card_types or "Sorcery" in card.card_types) and (
        has_power or has_toughness
    ):
        errors.append(
            _manual(
                "power/toughness",
                "Instant or sorcery must not have power/toughness",
                "Remove power/toughness from instant/sorcery cards.",
                error_code="type_check.spell_has_pt",
            )
        )

    # 6. Auras must have "Enchant" ability
    if "Aura" in card.subtypes:
        has_enchant = any(line.startswith("Enchant ") for line in card.oracle_text.split("\n"))
        if not has_enchant:
            errors.append(
                _manual(
                    "oracle_text",
                    "Aura is missing an 'Enchant' ability",
                    "Auras must have an 'Enchant [permanent type]' ability.",
                    error_code="type_check.aura_missing_enchant",
                )
            )

    # 7. Equipment must have "Equip" ability
    if "Equipment" in card.subtypes:
        has_equip = bool(
            re.search(r"(?m)^Equip\b", card.oracle_text)
            or "Equip {" in card.oracle_text
            or "Equip—" in card.oracle_text
        )
        if not has_equip:
            errors.append(
                _manual(
                    "oracle_text",
                    "Equipment is missing an 'Equip' ability",
                    "Equipment must have an 'Equip {cost}' ability.",
                    error_code="type_check.equipment_missing_equip",
                )
            )

    # 8. Type line matches card_types/subtypes/supertypes
    if card.type_line:
        type_line_lower = card.type_line.lower()
        for supertype in card.supertypes:
            if supertype.lower() not in type_line_lower:
                errors.append(
                    _manual(
                        "type_line",
                        f"Supertype '{supertype}' not found in type_line '{card.type_line}'",
                        "Ensure type_line includes all supertypes.",
                        error_code="type_check.supertype_missing",
                    )
                )
        for card_type in card.card_types:
            if card_type.lower() not in type_line_lower:
                errors.append(
                    _manual(
                        "type_line",
                        f"Card type '{card_type}' not found in type_line '{card.type_line}'",
                        "Ensure type_line includes all card types.",
                        error_code="type_check.card_type_missing",
                    )
                )
        # Subtypes should appear after a dash separator
        dash_match = re.search(r"\s[—\-]\s", card.type_line)
        if card.subtypes and dash_match:
            subtype_part = card.type_line[dash_match.end() :].lower()
            for subtype in card.subtypes:
                if subtype.lower() not in subtype_part:
                    errors.append(
                        _manual(
                            "type_line",
                            f"Subtype '{subtype}' not found after dash in "
                            f"type_line '{card.type_line}'",
                            "Ensure type_line includes all subtypes after the dash separator.",
                            error_code="type_check.subtype_missing",
                        )
                    )
        elif card.subtypes and not dash_match:
            errors.append(
                _manual(
                    "type_line",
                    f"Card has subtypes {card.subtypes} but type_line "
                    f"'{card.type_line}' has no dash separator",
                    "Use ' — ' (em dash) to separate types from subtypes.",
                    error_code="type_check.missing_dash",
                )
            )

    # 9. Cards with power/toughness should include "Creature" in card_types
    if has_power and has_toughness and not is_creature:
        errors.append(
            _manual(
                "card_types",
                "Card has power/toughness but 'Creature' is not in card_types",
                "Card has power/toughness but 'Creature' is not in card_types.",
                error_code="type_check.pt_without_creature",
            )
        )

    return errors
