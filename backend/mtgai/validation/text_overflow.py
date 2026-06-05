"""Validator 8: Text Overflow — character count limits per field.

Flags cards whose name, type line, oracle text, or flavor text may not fit
on a physical card. Name / oracle / flavor / combined overflows are MANUAL
(need AI/human to shorten). The type-line overflow is AUTO: it's almost always
a couple of chars of flavor subtype past the 45-char guideline, and the safe,
deterministic remedy is to trim trailing subtypes until it fits — far cheaper
and more reliable than regenerating the whole card (which the model tends to
re-emit with the same over-long, thematically-locked subtype).
"""

from __future__ import annotations

import re

from mtgai.models.card import Card
from mtgai.validation import ValidationError, ValidationSeverity

# Matches parenthesized reminder text (20+ chars) — stripped before measuring.
_REMINDER_RE = re.compile(r"\s*\([^)]{20,}\)\.?")

# Splits a type line into "<supertypes + card types>" and "<subtypes>" on an
# em-dash, en-dash, or double-hyphen (matches schema._parse_type_line's split).
_TYPE_DASH_RE = re.compile(r"\s*(?:\u2014|\u2013|--)\s*")

# --- Character limits ---
NAME_LIMIT = 30
TYPE_LINE_LIMIT = 45
FLAVOR_LIMIT = 200

# Oracle text limits by card type
ORACLE_LIMIT_CREATURE = 300
ORACLE_LIMIT_PLANESWALKER = 350
ORACLE_LIMIT_OTHER = 400

# Combined oracle + flavor limits
COMBINED_LIMIT_CREATURE = 350
COMBINED_LIMIT_OTHER = 450


def _manual(
    field: str, message: str, suggestion: str | None = None, *, error_code: str
) -> ValidationError:
    return ValidationError(
        validator="text_overflow",
        severity=ValidationSeverity.MANUAL,
        field=field,
        message=message,
        suggestion=suggestion,
        error_code=error_code,
    )


def _auto(
    field: str, message: str, suggestion: str | None = None, *, error_code: str
) -> ValidationError:
    return ValidationError(
        validator="text_overflow",
        severity=ValidationSeverity.AUTO,
        field=field,
        message=message,
        suggestion=suggestion,
        error_code=error_code,
    )


def fix_type_line_overflow(card: Card, _error: ValidationError) -> Card:
    """Shorten an over-long type line by trimming trailing subtypes.

    Subtypes are flavor; dropping the trailing one keeps the card a legal
    Magic object and still renders. Trim from the end until the line fits the
    guideline (or no subtypes remain — at which point the line is just the
    supertypes + card types and can't be shortened further without changing
    the card). Returns the original card untouched if it can't be improved.
    """
    parts = _TYPE_DASH_RE.split(card.type_line, maxsplit=1)
    main_part = parts[0].strip()
    if len(parts) < 2 or not parts[1].strip():
        return card  # no subtypes to trim

    subtypes = parts[1].split()
    while subtypes:
        candidate = f"{main_part} — {' '.join(subtypes)}"
        if len(candidate) <= TYPE_LINE_LIMIT:
            new_card = card.model_copy(update={"type_line": candidate})
            return new_card.model_copy(update={"subtypes": list(subtypes)})
        subtypes.pop()

    # All subtypes dropped — fall back to the bare main type line.
    new_card = card.model_copy(update={"type_line": main_part})
    return new_card.model_copy(update={"subtypes": []})


def _oracle_limit(card: Card) -> int:
    """Return the oracle text character limit based on card type."""
    if "Creature" in card.card_types:
        return ORACLE_LIMIT_CREATURE
    if "Planeswalker" in card.card_types:
        return ORACLE_LIMIT_PLANESWALKER
    return ORACLE_LIMIT_OTHER


def _combined_limit(card: Card) -> int:
    """Return the combined oracle+flavor character limit based on card type."""
    if "Creature" in card.card_types:
        return COMBINED_LIMIT_CREATURE
    return COMBINED_LIMIT_OTHER


def validate_text_overflow(card: Card) -> list[ValidationError]:
    """Check character counts to flag cards whose text won't fit."""
    errors: list[ValidationError] = []

    # 1. Card name length
    name_len = len(card.name)
    if name_len > NAME_LIMIT:
        errors.append(
            _manual(
                "name",
                f'Card name "{card.name}" is {name_len} characters.'
                f" Names over {NAME_LIMIT} chars may not fit",
                error_code="text_overflow.name",
            )
        )

    # 2. Type line length — AUTO: trim trailing subtypes to fit (see fixer).
    type_len = len(card.type_line)
    if type_len > TYPE_LINE_LIMIT:
        errors.append(
            _auto(
                "type_line",
                f"Type line is {type_len} characters,"
                f" exceeding the {TYPE_LINE_LIMIT}-char guideline",
                "Trim trailing subtypes so the line fits.",
                error_code="text_overflow.type_line",
            )
        )

    # 3. Oracle text length (strip reminder text — it can be dropped/shrunk at render)
    oracle_len = len(_REMINDER_RE.sub("", card.oracle_text))
    limit = _oracle_limit(card)
    oracle_over = oracle_len > limit
    if oracle_over:
        errors.append(
            _manual(
                "oracle_text",
                f"Oracle text is {oracle_len} characters,"
                f" exceeding the {limit}-char limit for this card type",
                "Shorten rules text or split across abilities.",
                error_code="text_overflow.oracle",
            )
        )

    # 4. Flavor text length
    flavor_len = len(card.flavor_text) if card.flavor_text else 0
    flavor_over = flavor_len > FLAVOR_LIMIT
    if flavor_over:
        errors.append(
            _manual(
                "flavor_text",
                f"Flavor text is {flavor_len} characters,"
                f" exceeding the {FLAVOR_LIMIT}-char guideline",
                "Trim flavor text to fit.",
                error_code="text_overflow.flavor",
            )
        )

    # 5. Combined oracle + flavor (only if individual checks passed)
    if not oracle_over and not flavor_over and flavor_len > 0:
        combined_len = oracle_len + flavor_len
        comb_limit = _combined_limit(card)
        if combined_len > comb_limit:
            errors.append(
                _manual(
                    "oracle_text",
                    f"Combined oracle + flavor text is {combined_len} "
                    f"characters, exceeding the {comb_limit}-char limit for "
                    f"this card type",
                    "Shorten oracle or flavor text so both fit.",
                    error_code="text_overflow.combined",
                )
            )

    return errors
