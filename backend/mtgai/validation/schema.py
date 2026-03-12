"""Validator 1: JSON Schema Validation.

Parses raw LLM output (a dict) into a Card Pydantic model, converting any
Pydantic validation errors into the project's ValidationError format.
"""

from __future__ import annotations

import pydantic

from mtgai.models.card import Card
from mtgai.validation import ValidationError, ValidationSeverity


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

    return card, []


def _suggest_fix(error_type: str, field_name: str) -> str:
    suggestions: dict[str, str] = {
        "missing": f"Provide a value for '{field_name}'.",
        "string_type": f"Set '{field_name}' to a string value.",
        "float_type": f"Set '{field_name}' to a number like 3.0.",
        "enum": "Use one of the valid enum values.",
    }
    return suggestions.get(error_type, "Check the field type and format.")
