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

Because validation findings are computed ONCE, on the card the validators see,
a literal escape must be healed *before* the line-based validators run — a
defect hidden inside the "one long line" (a misplaced keyword, a missing
period, an overflow miscount) would otherwise produce no finding at all, so
its fixer would never fire. :func:`prenormalize_card_whitespace` is that
pre-pass, applied by ``validate_card_from_raw`` (card-gen save) and
``finalize_card`` (finalize stage) ahead of the main validation sequence. The
in-sequence ``validate_escaped_whitespace`` check stays as the diagnostic
surface for ``auto_fix=False`` callers and as a backstop for any direct
``validate_card`` + ``auto_fix_card`` caller without the pre-pass.

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
TEXT_FIELDS = ("oracle_text", "flavor_text")

_LITERAL_ESCAPES = ("\\n", "\\t", "\\r")


def normalize_escaped_whitespace(text: str) -> str:
    r"""Replace literal ``\n``/``\r`` with real newlines and literal ``\t`` with a space.

    A literal ``\r\n`` pair collapses to ONE newline (handled first so the two
    halves aren't expanded into a blank line). Idempotent: the replacements
    never produce a new literal escape, so a second pass is a no-op. MTG card
    text never contains tabs, so a leaked ``\t`` collapses to a single space
    rather than a real tab.
    """
    return (
        text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n").replace("\\t", " ")
    )


def _has_literal_escape(text: str | None) -> bool:
    return bool(text) and any(esc in text for esc in _LITERAL_ESCAPES)


def validate_escaped_whitespace(card: Card) -> list[ValidationError]:
    r"""Flag fields holding a literal ``\n`` / ``\t`` / ``\r`` escape — AUTO, one per field."""
    errors: list[ValidationError] = []
    for field in TEXT_FIELDS:
        if _has_literal_escape(getattr(card, field, None)):
            errors.append(
                ValidationError(
                    validator="whitespace",
                    severity=ValidationSeverity.AUTO,
                    field=field,
                    message=(
                        f"{field} contains a literal backslash escape "
                        "(\\n, \\t or \\r) instead of real whitespace"
                    ),
                    suggestion="Replace the literal escape with real whitespace.",
                    error_code="whitespace.literal_escape",
                )
            )
    return errors


def fix_escaped_whitespace(card: Card, error: ValidationError) -> Card:
    """Normalize the flagged field's literal escapes to real whitespace."""
    if error.field not in TEXT_FIELDS:
        return card
    value = getattr(card, error.field, None)
    if not value:
        return card
    return card.model_copy(update={error.field: normalize_escaped_whitespace(value)})


def prenormalize_card_whitespace(card: Card) -> tuple[Card, list[str]]:
    """Apply the whitespace AUTO fixes ahead of the main validation pass.

    Two normalizations, in order:

    1. literal ``\\n`` / ``\\t`` / ``\\r`` escapes -> real whitespace
       (:func:`fix_escaped_whitespace`), and
    2. blank-line collapse (:func:`blank_lines.fix_blank_lines`), run AFTER (1)
       so a literal ``\\n\\n`` that decoded to a real blank line in step 1 is
       also collapsed.

    Returns the (possibly unchanged) card plus applied-fix descriptions in
    ``auto_fix_card``'s ``[code] message`` format, so callers can merge them
    into their ``applied_fixes`` report. See the module docstring for why this
    must run before the line-based validators compute their findings.
    """
    from mtgai.validation.blank_lines import fix_blank_lines, validate_blank_lines

    fixes: list[str] = []
    for error in validate_escaped_whitespace(card):
        card = fix_escaped_whitespace(card, error)
        fixes.append(f"[{error.error_code}] {error.message}")
    for error in validate_blank_lines(card):
        card = fix_blank_lines(card, error)
        fixes.append(f"[{error.error_code}] {error.message}")
    return card, fixes
