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
from mtgai.rendering.card_renderer import (
    LAND_WATERMARK_OPACITY,
    LAND_WATERMARK_TINT,
    _basic_land_symbol,
    _land_watermark_image,
    _render_land_watermark,
)
from mtgai.rendering.layout import NATIVE_TEXT_BOX
from mtgai.rendering.symbol_renderer import get_mana_glyph_silhouette


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


def test_with_opacity_scales_alpha() -> None:
    """`_with_opacity` scales the alpha channel by the given factor."""
    full = card_renderer.get_mana_symbol("U", 400)
    faint = card_renderer._with_opacity(full, 0.5)
    # A fully-opaque source pixel is halved (int truncation: 255 -> 127).
    full_max = max(full.split()[3].getdata())
    faint_max = max(faint.split()[3].getdata())
    assert faint_max == int(full_max * 0.5)


def test_watermark_opacity_is_faint() -> None:
    """The watermark opacity is low so flavor text reads even over dark glyphs."""
    assert 0.10 <= LAND_WATERMARK_OPACITY <= 0.20


def test_glyph_silhouette_is_bare_flat_tint() -> None:
    """The bare-glyph silhouette has flat-black RGB and a non-empty alpha shape.

    No circular disc: a disc-bearing full mana symbol would paint opaque pixels
    in the corners, but the bare glyph leaves them transparent.
    """
    sil = get_mana_glyph_silhouette("B", 400)
    if sil is None:  # no SVG backend available in this environment
        pytest.skip("no SVG backend for glyph rasterization")
    # RGB is uniformly black (tinted at the call site via alpha only).
    rgb = sil.convert("RGB")
    assert rgb.getextrema() == ((0, 0), (0, 0), (0, 0))
    # The glyph itself is present (some opaque alpha).
    alpha = sil.split()[3]
    assert max(alpha.getdata()) > 0
    # Corners are transparent — there is no disc behind the glyph.
    assert alpha.getpixel((4, 4)) == 0
    assert alpha.getpixel((395, 395)) == 0


def test_land_watermark_is_bare_glyph_tinted() -> None:
    """The composited land watermark is the bare glyph in the flat tint, faded.

    For Swamp ({B}) the OLD full-symbol path painted a near-black disc; the new
    path must instead carry the flat brown tint at the faint opacity wherever the
    glyph is drawn — never the symbol's own colors and never a disc. Requires an
    SVG backend (the bare glyph comes from the IcoMoon SVG); skipped otherwise,
    where `_land_watermark_image` degrades to the faded full symbol.
    """
    if get_mana_glyph_silhouette("B", 400) is None:
        pytest.skip("no SVG backend for glyph rasterization")
    wm = _land_watermark_image("B", 400)
    rgba = wm.load()
    # Find the most-opaque pixel (somewhere on the glyph shape).
    alpha = wm.split()[3]
    peak = max(alpha.getdata())
    assert peak > 0
    # Peak alpha never exceeds the faint-opacity ceiling (255 * opacity).
    assert peak <= int(255 * LAND_WATERMARK_OPACITY) + 1
    # The opaque glyph pixels carry the flat tint, not the symbol's near-black.
    w, h = wm.size
    found_tint = False
    for y in range(0, h, 7):
        for x in range(0, w, 7):
            r, g, b, a = rgba[x, y]
            if a > 0:
                assert (r, g, b) == LAND_WATERMARK_TINT
                found_tint = True
    assert found_tint
    # No disc: the corners stay transparent.
    assert alpha.getpixel((2, 2)) == 0
