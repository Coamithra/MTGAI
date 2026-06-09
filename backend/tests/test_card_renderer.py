"""Tests for CardRenderer's basic-land text-box watermark.

Basic lands have empty oracle text, so without a watermark their text box
renders blank. The renderer composites the land's produced-color mana symbol
large and centered in the text box (behind any flavor text).
"""

import pytest

pytest.importorskip("PIL")

from PIL import Image

from mtgai.models.card import Card
from mtgai.rendering import card_renderer
from mtgai.rendering.card_renderer import _basic_land_symbol, _render_land_watermark
from mtgai.rendering.layout import NATIVE_TEXT_BOX


def _basic_land(subtype: str, color: str) -> Card:
    return Card(
        name=subtype,
        type_line=f"Basic Land — {subtype}",
        supertypes=["Basic"],
        card_types=["Land"],
        subtypes=[subtype],
        color_identity=[color],
        oracle_text="",
    )


@pytest.mark.parametrize(
    ("subtype", "symbol"),
    [
        ("Plains", "W"),
        ("Island", "U"),
        ("Swamp", "B"),
        ("Mountain", "R"),
        ("Forest", "G"),
        ("Wastes", "C"),
    ],
)
def test_basic_land_symbol_maps_each_type(subtype: str, symbol: str) -> None:
    assert _basic_land_symbol(_basic_land(subtype, symbol)) == symbol


def test_basic_land_symbol_from_type_line_fallback() -> None:
    """Subtype list empty but type line names the basic type."""
    card = Card(
        name="Island",
        type_line="Basic Land — Island",
        supertypes=["Basic"],
        card_types=["Land"],
        subtypes=[],
        oracle_text="",
    )
    assert _basic_land_symbol(card) == "U"


def test_basic_land_symbol_none_for_nonbasic() -> None:
    # A non-basic land (e.g. a gate) is intentionally not watermarked.
    gate = Card(
        name="Azorius Gate",
        type_line="Land — Gate",
        card_types=["Land"],
        subtypes=["Gate"],
        oracle_text="Azorius Gate enters tapped.",
    )
    assert _basic_land_symbol(gate) is None

    creature = Card(name="Goblin", type_line="Creature — Goblin", card_types=["Creature"])
    assert _basic_land_symbol(creature) is None


def test_watermark_composited_for_basic_land() -> None:
    """The watermark draws non-transparent pixels into the text box."""
    canvas = Image.new("RGBA", (2010, 2814), (0, 0, 0, 0))
    _render_land_watermark(canvas, _basic_land("Forest", "G"))

    # Center of the text box should now carry opaque-ish watermark pixels.
    cx, cy = NATIVE_TEXT_BOX.center_x, NATIVE_TEXT_BOX.center_y
    assert canvas.getpixel((cx, cy))[3] > 0


def test_watermark_noop_for_nonland() -> None:
    canvas = Image.new("RGBA", (2010, 2814), (0, 0, 0, 0))
    creature = Card(name="Goblin", type_line="Creature — Goblin", card_types=["Creature"])
    _render_land_watermark(canvas, creature)

    cx, cy = NATIVE_TEXT_BOX.center_x, NATIVE_TEXT_BOX.center_y
    assert canvas.getpixel((cx, cy))[3] == 0


def test_watermark_opacity_is_reduced() -> None:
    """Watermark alpha is scaled down so flavor text reads on top."""
    full = card_renderer.get_mana_symbol("U", 400)
    faint = card_renderer._with_opacity(full, 0.5)
    # A fully-opaque source pixel is halved (int truncation: 255 -> 127).
    full_max = max(full.split()[3].getdata())
    faint_max = max(faint.split()[3].getdata())
    assert faint_max == int(full_max * 0.5)
