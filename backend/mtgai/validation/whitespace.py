r"""Validator: Escaped-Whitespace Normalization.

Local LLMs sometimes double-escape whitespace in their JSON tool output, so a
card's ``oracle_text`` arrives holding the LITERAL two-character sequence
``\n`` (backslash + n) instead of a real newline (observed live: one example
card with ``"Flying\nSquall 3"`` as a single line while its siblings in the
same call carried real newlines — a stochastic model quirk). Every line-based
check downstream (``keyword_ordering``, ``rules_text.line_period``,
``text_overflow``) splits on real newlines, so an affected card reads as one
long line and those checks/fixers silently misfire; the wizard also displays
the raw ``\n``.

This validator runs FIRST in the ``validate_card`` sequence so its AUTO fix is
applied before any line-structure-dependent fixer re-reads the card (fixers
run in finding order and each re-derives lines from the current card state).

:func:`normalize_escaped_whitespace` is the one canonical implementation —
the mechanics persistence path (``persist_mechanic_selection``) reuses it for
mechanic example cards, which never pass through ``validate_card``, and
``rendering/text_engine.py`` keeps its render-time replace as the backstop.

The validators-skip-parenthesized-text contract doesn't apply here: a pure
whitespace normalize is safe everywhere (injected reminder text never
legitimately contains a literal backslash escape).
"""

from __future__ import annotations

from mtgai.models.card import Card
from mtgai.validation import ValidationError, ValidationSeverity

# The free-text fields a double-escaped newline can corrupt. design_notes is
# prompt-only context (never rendered or line-split), so it's left alone.
_FIELDS = ("oracle_text", "flavor_text")

_LITERAL_ESCAPES = ("\\n", "\\t")


def normalize_escaped_whitespace(text: str) -> str:
    r"""Replace literal ``\n`` with a real newline and literal ``\t`` with a space.

    Idempotent: the replacements never produce a new literal escape, so a
    second pass is a no-op. MTG card text never contains tabs, so a leaked
    ``\t`` collapses to a single space rather than a real tab.
    """
    return text.replace("\\n", "\n").replace("\\t", " ")


def _has_literal_escape(text: str | None) -> bool:
    return bool(text) and any(esc in text for esc in _LITERAL_ESCAPES)


def validate_escaped_whitespace(card: Card) -> list[ValidationError]:
    r"""Flag fields holding a literal ``\n`` / ``\t`` escape — AUTO, one per field."""
    errors: list[ValidationError] = []
    for field in _FIELDS:
        if _has_literal_escape(getattr(card, field, None)):
            errors.append(
                ValidationError(
                    validator="whitespace",
                    severity=ValidationSeverity.AUTO,
                    field=field,
                    message=(
                        f"{field} contains a literal backslash escape "
                        "(\\n or \\t) instead of real whitespace"
                    ),
                    suggestion="Replace the literal escape with real whitespace.",
                    error_code="whitespace.literal_escape",
                )
            )
    return errors


def fix_escaped_whitespace(card: Card, error: ValidationError) -> Card:
    """Normalize the flagged field's literal escapes to real whitespace."""
    if error.field not in _FIELDS:
        return card
    value = getattr(card, error.field, None)
    if not value:
        return card
    return card.model_copy(update={error.field: normalize_escaped_whitespace(value)})
