"""Validator 1: JSON Schema Validation.

Parses raw LLM output (a dict) into a Card Pydantic model, converting any
Pydantic validation errors into the project's ValidationError format.

Also parses ``type_line`` into ``card_types`` / ``supertypes`` / ``subtypes``
since the LLM tool schema doesn't include those fields — they're derived.
"""

from __future__ import annotations

import pydantic

from mtgai.models.card import Card
from mtgai.validation import ValidationError, ValidationSeverity

# MTG type categories for parsing type_line
_SUPERTYPES = {"Legendary", "Basic", "Snow", "World"}
_CARD_TYPES = {
    "Creature",
    "Instant",
    "Sorcery",
    "Enchantment",
    "Artifact",
    "Planeswalker",
    "Land",
    "Battle",
    "Kindred",
}


def _parse_type_line(card: Card) -> Card:
    """Derive card_types, supertypes, and subtypes from type_line.

    Type line format: ``[Supertypes] <Card Types> [— Subtypes]``
    e.g. ``Legendary Creature — Human Wizard``
    """
    if not card.type_line:
        return card

    # Split on em-dash or double-hyphen
    parts = card.type_line.replace("—", "—").split("—")
    main_part = parts[0].strip()
    sub_part = parts[1].strip() if len(parts) > 1 else ""

    words = main_part.split()
    supertypes: list[str] = []
    card_types: list[str] = []

    for word in words:
        # Normalize capitalization for matching
        title = word.strip().title()
        if title in _SUPERTYPES:
            supertypes.append(title)
        elif title in _CARD_TYPES:
            card_types.append(title)

    subtypes = [s.strip() for s in sub_part.split() if s.strip()] if sub_part else []

    return card.model_copy(
        update={
            "supertypes": supertypes,
            "card_types": card_types,
            "subtypes": subtypes,
        }
    )


def validate_schema(raw: dict) -> tuple[Card | None, list[ValidationError]]:
    """Try to parse *raw* into a ``Card``.

    Returns ``(card, [])`` on success, or ``(None, errors)`` when the dict
    cannot be coerced into a valid ``Card``.
    """
    try:
        card = Card.model_validate(raw)
    except pydantic.ValidationError as exc:
        errors: list[ValidationError] = []
        for err in exc.errors():
            field = ".".join(str(part) for part in err["loc"])
            errors.append(
                ValidationError(
                    validator="schema",
                    severity=ValidationSeverity.MANUAL,
                    field=field,
                    message=err["msg"],
                    suggestion=_suggest_fix(err["type"], field),
                    error_code=f"schema.{err['type']}",
                )
            )
        return None, errors

    # Derive card_types/supertypes/subtypes from type_line
    card = _parse_type_line(card)

    return card, []


def _suggest_fix(error_type: str, field_name: str) -> str:
    suggestions: dict[str, str] = {
        "missing": f"Provide a value for '{field_name}'.",
        "string_type": f"Set '{field_name}' to a string value.",
        "float_type": f"Set '{field_name}' to a number like 3.0.",
        "enum": "Use one of the valid enum values.",
    }
    return suggestions.get(error_type, "Check the field type and format.")
