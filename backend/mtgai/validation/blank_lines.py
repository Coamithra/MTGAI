"""Validator: Blank Lines in Oracle Text.

Local card-gen models sometimes emit an empty paragraph — a run of two or more
consecutive newlines — between abilities (observed live 2026-06-10: card 049
Twilight Sparkle had a double newline between two abilities). The renderer skips
empty lines so it's invisible on the printed card, but the stored ``oracle_text``
is un-canonical and any consumer that splits/counts lines (``keyword_ordering``,
``rules_text`` line checks, ``text_overflow``) sees a phantom blank line.

:func:`collapse_blank_lines` collapses every run of 2+ newlines to one. It also
trims leading/trailing newlines (an oracle never legitimately starts or ends with
a blank line). Idempotent.

This runs in the whitespace pre-pass (``prenormalize_card_whitespace``), AFTER
the literal-escape normalization, so a literal ``\\n\\n`` that *decodes* to a real
blank line is also collapsed. The in-sequence :func:`validate_blank_lines` check
is the diagnostic surface (``auto_fix=False`` callers) and the backstop for a
direct ``validate_card`` + ``auto_fix_card`` caller without the pre-pass.

The validators-skip-parenthesized-text contract doesn't apply: a blank line is a
structural defect, and injected reminder text is single-line, never holding an
intentional empty paragraph.
"""

from __future__ import annotations

import re

from mtgai.models.card import Card
from mtgai.validation import ValidationError, ValidationSeverity

# A run of 2+ newlines, optionally with whitespace-only lines between them, is a
# blank-paragraph gap. Matching the whitespace too collapses "a\n   \nb" (a line
# of just spaces) as well as a bare "a\n\nb".
_BLANK_RUN_RE = re.compile(r"\n[ \t]*(?:\n[ \t]*)+")


def collapse_blank_lines(text: str) -> str:
    """Collapse runs of 2+ newlines to one and strip leading/trailing newlines.

    Idempotent: a single newline between non-blank lines is left as-is, so a
    second pass is a no-op.
    """
    return _BLANK_RUN_RE.sub("\n", text).strip("\n")


def _has_blank_lines(text: str | None) -> bool:
    if not text:
        return False
    return bool(_BLANK_RUN_RE.search(text)) or text != text.strip("\n")


def validate_blank_lines(card: Card) -> list[ValidationError]:
    """Flag oracle_text holding a blank line (empty paragraph) — AUTO."""
    if not _has_blank_lines(card.oracle_text):
        return []
    return [
        ValidationError(
            validator="rules_text",
            severity=ValidationSeverity.AUTO,
            field="oracle_text",
            message="Oracle text contains a blank line (empty paragraph) between abilities",
            suggestion="Collapse consecutive newlines to a single newline.",
            error_code="rules_text.blank_lines",
        )
    ]


def fix_blank_lines(card: Card, error: ValidationError) -> Card:
    """Collapse blank lines in oracle_text to single newlines."""
    if not card.oracle_text:
        return card
    new_oracle = collapse_blank_lines(card.oracle_text)
    if new_oracle == card.oracle_text:
        return card
    return card.model_copy(update={"oracle_text": new_oracle})
