"""Validator: Keyword Ability Ordering.

MTG templating convention: standalone keyword abilities (Flying, Trample,
Ward {2}, and the set's custom keywords) appear at the **top** of the textbox,
above any complex triggered / activated / static abilities. Generation often
interleaves them (a keyword line sandwiched between or below complex abilities),
which renders awkwardly and reads non-standard.

This validator detects a keyword-only line that sits *after* a complex ability
line and emits an AUTO finding; :func:`fix_keyword_ordering` deterministically
hoists every keyword-only line to the top of the oracle text, preserving the
relative order within each group (a stable partition).

The classification of a line reuses :func:`rules_text.all_keywords` /
:func:`rules_text._is_keyword_only_line`, so the keyword vocabulary (evergreen +
the active project's custom mechanics) stays defined in one place.

Reminder text (parenthesized spans, injected programmatically — never
LLM-generated) is preserved byte-for-byte: lines are moved whole, so any
``(reminder)`` riding on a keyword line travels with it untouched, and the
parenthesized text is stripped only for *classification*.
"""

from __future__ import annotations

from mtgai.models.card import Card
from mtgai.validation import ValidationError, ValidationSeverity
from mtgai.validation.rules_text import _is_keyword_only_line, _strip_reminder

# Keywords whose ability conventionally templates at the **bottom** of the
# textbox, not the top: Equip (on Equipment) and Enchant (on Auras). A line
# carrying one is excluded from the top-hoist so we don't move it above the
# card's other abilities, where MTG never puts it.
_BOTTOM_KEYWORDS = ("equip", "enchant")


def _is_keyword_line(line: str) -> bool:
    """True if ``line`` is a top-of-textbox keyword-ability line (reminder ignored).

    A keyword line is one whose every comma-separated segment is a recognized
    keyword (evergreen or custom), e.g. ``"Flying, vigilance"`` or
    ``"Ward {2}"``. Reminder text is stripped before the check so a keyword line
    carrying an injected ``(reminder)`` still classifies as a keyword line.

    Lines carrying a bottom-templated keyword (Equip / Enchant) are excluded —
    those abilities render below the card's other abilities, so hoisting them
    would be wrong.
    """
    bare = _strip_reminder(line).strip()
    if not bare:
        return False
    if any(seg.strip().lower().startswith(_BOTTOM_KEYWORDS) for seg in bare.split(",")):
        return False
    return _is_keyword_only_line(bare)


def validate_keyword_ordering(card: Card) -> list[ValidationError]:
    """Flag oracle text where a keyword line appears below a complex ability.

    AUTO — :func:`fix_keyword_ordering` reorders. Returns at most one finding.
    """
    oracle = card.oracle_text or ""
    if "\n" not in oracle:
        return []

    lines = oracle.split("\n")
    seen_complex = False
    for line in lines:
        if not line.strip():
            continue
        if _is_keyword_line(line):
            if seen_complex:
                return [
                    ValidationError(
                        validator="keyword_ordering",
                        severity=ValidationSeverity.AUTO,
                        field="oracle_text",
                        message=(
                            "Keyword abilities must appear above complex abilities; "
                            f'found keyword line "{line.strip()}" below a complex ability'
                        ),
                        suggestion="Move keyword-ability lines to the top of the textbox.",
                        error_code="keyword_ordering.misplaced",
                    )
                ]
        else:
            seen_complex = True

    return []


def fix_keyword_ordering(card: Card, error: ValidationError) -> Card:
    """Hoist every keyword-only line above the complex abilities (stable partition).

    Keyword lines keep their relative order, complex lines keep theirs, and the
    two groups are separated by a single blank line (standard MTG templating).
    Blank lines from the original are dropped — the partition reimposes the
    canonical single-separator layout.
    """
    if not card.oracle_text:
        return card

    keyword_lines: list[str] = []
    complex_lines: list[str] = []
    for line in card.oracle_text.split("\n"):
        if not line.strip():
            continue
        if _is_keyword_line(line):
            keyword_lines.append(line)
        else:
            complex_lines.append(line)

    if not keyword_lines or not complex_lines:
        return card

    new_oracle = "\n".join([*keyword_lines, "", *complex_lines])
    return card.model_copy(update={"oracle_text": new_oracle})
