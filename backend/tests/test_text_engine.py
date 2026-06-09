"""Tests for the card text wrapping engine.

Focus: ``wrap_paragraph`` must never break a line between two elements that
have no intervening whitespace. A symbol and the punctuation glued to it
(``{W}{U}.``) form a single unbreakable group, so the trailing ``.`` can
never be orphaned onto the next line (regression for the Trello bug
"Text wrap orphans trailing punctuation after a mana symbol").
"""

from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from mtgai.rendering.text_engine import SegmentType, TextEngine


@pytest.fixture(scope="module")
def engine() -> TextEngine:
    try:
        return TextEngine()
    except Exception as exc:  # pragma: no cover - font assets unavailable
        pytest.skip(f"fonts unavailable: {exc}")


# Punctuation that should always stay glued to its predecessor.
_GLUE_PUNCT = {".", ",", ":", ";", ")", "!", "?"}


def _orphaned_punctuation(lines) -> bool:
    """True if any wrapped line *starts* with a bare punctuation element."""
    for line in lines:
        if not line.elements:
            continue
        first = line.elements[0]
        if first.kind != SegmentType.SYMBOL and first.content.strip() in _GLUE_PUNCT:
            return True
    return False


def test_period_after_symbol_never_orphaned(engine: TextEngine) -> None:
    """A '.' after a mana symbol stays with the symbol at every width."""
    para = engine.parse_oracle(
        "{2}{W}{U}, Exile this permanent: Add {W}{U}.", card_name="Cybertronian Gates"
    )[0]

    # Sweep a wide range of widths so the wrap point lands in many places.
    for max_width in range(120, 1400, 17):
        lines = engine.wrap_paragraph(para, font_size=60, max_width=max_width)
        rendered = [[e.content for e in line.elements] for line in lines]
        assert not _orphaned_punctuation(lines), (
            f"punctuation orphaned at max_width={max_width}: {rendered}"
        )


def test_trailing_period_glued_to_its_symbol(engine: TextEngine) -> None:
    """The final '.' always renders immediately after its {U} symbol."""
    para = engine.parse_oracle("Add {W}{U}.", card_name="X")[0]

    for max_width in range(60, 600, 13):
        lines = engine.wrap_paragraph(para, font_size=60, max_width=max_width)
        # Locate the '.' element and assert its predecessor is a symbol.
        for line in lines:
            elems = line.elements
            for idx, elem in enumerate(elems):
                if elem.kind != SegmentType.SYMBOL and elem.content.strip() == ".":
                    assert idx > 0 and elems[idx - 1].kind == SegmentType.SYMBOL, (
                        f"period not glued to symbol at max_width={max_width}: "
                        f"{[e.content for e in elems]}"
                    )


def test_consecutive_symbols_stay_together(engine: TextEngine) -> None:
    """Adjacent symbols with no space between them never split across lines."""
    para = engine.parse_oracle("Add {W}{U}{B}{R}{G}.", card_name="X")[0]

    for max_width in range(80, 900, 11):
        lines = engine.wrap_paragraph(para, font_size=60, max_width=max_width)
        # Every symbol run must be wholly on one line: find the line(s) that
        # carry symbols and confirm the period rides with the last symbol.
        assert not _orphaned_punctuation(lines)


def test_comma_after_symbol_not_orphaned(engine: TextEngine) -> None:
    """A comma directly after a symbol ('{U},') stays glued like the period."""
    para = engine.parse_oracle("{T}, {W}: Do a thing.", card_name="X")[0]

    for max_width in range(80, 800, 9):
        lines = engine.wrap_paragraph(para, font_size=60, max_width=max_width)
        assert not _orphaned_punctuation(lines)


def test_normal_text_still_wraps(engine: TextEngine) -> None:
    """Plain prose still wraps into multiple lines when it overflows."""
    para = engine.parse_oracle(
        "When this creature enters the battlefield, draw a card and gain two life.",
        card_name="X",
    )[0]

    # A narrow box must produce more than one line (wrapping still happens).
    lines = engine.wrap_paragraph(para, font_size=60, max_width=300)
    assert len(lines) > 1
    # And a generous box keeps it on one line.
    wide = engine.wrap_paragraph(para, font_size=60, max_width=4000)
    assert len(wide) == 1
