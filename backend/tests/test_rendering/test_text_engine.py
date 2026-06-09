"""Tests for the card text parsing in mtgai.rendering.text_engine.

Focus: oracle/reminder text is tokenized into TEXT / SYMBOL / ITALIC_TEXT
segments. The regression of interest is mana symbols *inside* reminder
text — they must become SYMBOL segments (rendered as glyphs), not be
swallowed into one opaque ITALIC_TEXT blob with literal ``{T}`` braces.
"""

from __future__ import annotations

import pytest

# The rendering engine imports Pillow, which is an undeclared (system-installed)
# dependency absent from the managed venv — skip the whole module when it's not
# importable so the canonical `uv run pytest` stays green.
pytest.importorskip("PIL")

from mtgai.rendering.text_engine import SegmentType, TextEngine, TextSegment  # noqa: E402


@pytest.fixture
def engine() -> TextEngine:
    return TextEngine()


def _kinds(segs: list[TextSegment]) -> list[SegmentType]:
    return [s.kind for s in segs]


def test_plain_oracle_symbol_is_glyph(engine: TextEngine) -> None:
    segs = engine._parse_line_segments("Add {G} to your mana pool.")
    assert _kinds(segs) == [
        SegmentType.TEXT,
        SegmentType.SYMBOL,
        SegmentType.TEXT,
    ]
    assert segs[0].content == "Add "
    assert segs[1].content == "G"
    assert segs[2].content == " to your mana pool."


def test_symbol_inside_reminder_is_glyph(engine: TextEngine) -> None:
    """The core bug: {T} inside a reminder must be a SYMBOL, not literal."""
    line = "Overdrive ({T}, Remove one Energon counter from this artifact: Draw a card.)"
    segs = engine._parse_line_segments(line)

    # The keyword + space stays plain TEXT; the reminder splits into
    # italic text with a SYMBOL glyph for {T}.
    assert SegmentType.SYMBOL in _kinds(segs)
    sym_segs = [s for s in segs if s.kind == SegmentType.SYMBOL]
    assert [s.content for s in sym_segs] == ["T"]

    # No segment should contain a literal "{T}" — the braces must be gone.
    assert all("{T}" not in s.content for s in segs)

    # The reminder body is italic.
    italic = [s for s in segs if s.kind == SegmentType.ITALIC_TEXT]
    assert italic, "reminder text should produce ITALIC_TEXT segments"
    assert italic[0].content.startswith("(")
    assert any(")" in s.content for s in italic)


def test_multiple_symbols_inside_reminder(engine: TextEngine) -> None:
    line = "Convoke (You may tap {W} and {G} creatures to help cast this spell.)"
    segs = engine._parse_line_segments(line)
    sym_segs = [s.content for s in segs if s.kind == SegmentType.SYMBOL]
    assert sym_segs == ["W", "G"]
    assert all("{" not in s.content for s in segs)


def test_reminder_without_symbols_stays_italic(engine: TextEngine) -> None:
    line = "Flying (This creature can't be blocked except by creatures with flying.)"
    segs = engine._parse_line_segments(line)
    assert SegmentType.SYMBOL not in _kinds(segs)
    italic = [s for s in segs if s.kind == SegmentType.ITALIC_TEXT]
    assert len(italic) == 1
    assert italic[0].content.startswith("(") and italic[0].content.endswith(")")


def test_short_parenthetical_not_treated_as_reminder(engine: TextEngine) -> None:
    """A short parenthetical (<20 chars inside) is not a reminder, but a
    symbol in it should still render as a glyph via the plain-text path."""
    line = "Sacrifice this ({T})."
    segs = engine._parse_line_segments(line)
    sym_segs = [s.content for s in segs if s.kind == SegmentType.SYMBOL]
    assert sym_segs == ["T"]
    # Not promoted to italic reminder text.
    assert SegmentType.ITALIC_TEXT not in _kinds(segs)


def test_bold_all_applies_to_nonsymbol_text(engine: TextEngine) -> None:
    segs = engine._parse_line_segments("Add {G}.", bold_all=True)
    assert _kinds(segs) == [SegmentType.BOLD_TEXT, SegmentType.SYMBOL, SegmentType.BOLD_TEXT]


def test_text_with_no_symbols_or_reminders(engine: TextEngine) -> None:
    segs = engine._parse_line_segments("Draw a card.")
    assert _kinds(segs) == [SegmentType.TEXT]
    assert segs[0].content == "Draw a card."
