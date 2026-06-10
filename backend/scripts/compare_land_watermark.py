"""Before/after comparison renders for the basic-land watermark fix.

Renders all six basics (Plains/Island/Swamp/Mountain/Forest/Wastes) with flavor
text crossing the watermark, OLD (full-color symbol @ 0.5) vs NEW (bare-glyph
flat tint @ 0.15), side by side per type. Output PNGs go to
``output/.scratch/land-watermark/``.

Run from ``backend/``::  python -m scripts.compare_land_watermark
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend"))

from mtgai.models.card import Card  # noqa: E402
from mtgai.rendering import card_renderer  # noqa: E402
from mtgai.rendering.symbol_renderer import get_mana_symbol  # noqa: E402

BASICS = [
    ("Plains", "W"),
    ("Island", "U"),
    ("Swamp", "B"),
    ("Mountain", "R"),
    ("Forest", "G"),
    ("Wastes", "C"),
]

FLAVOR = (
    "The wide land remembers every footstep that has ever crossed it, "
    "and forgets nothing of those who never returned."
)


def _basic(subtype: str, color: str) -> Card:
    return Card(
        name=subtype,
        type_line=f"Basic Land — {subtype}",
        supertypes=["Basic"],
        card_types=["Land"],
        subtypes=[subtype],
        color_identity=[color],
        oracle_text="",
        flavor_text=FLAVOR,
    )


def _old_watermark(canvas: Image.Image, card: Card) -> None:
    """The pre-fix watermark: faded FULL-color mana symbol @ 0.5."""
    symbol = card_renderer._basic_land_symbol(card)
    if symbol is None:
        return
    box = card_renderer.NATIVE_TEXT_BOX
    size = int(box.height * card_renderer.LAND_WATERMARK_SCALE)
    sym_img = card_renderer._with_opacity(get_mana_symbol(symbol, size), 0.5)
    canvas.alpha_composite(sym_img, (box.center_x - size // 2, box.center_y - size // 2))


def main() -> None:
    out_dir = _REPO / "output" / ".scratch" / "land-watermark"
    out_dir.mkdir(parents=True, exist_ok=True)
    renderer = card_renderer.CardRenderer(output_root=out_dir)
    # No project is open in this standalone harness; skip art resolution so the
    # text-box watermark (the thing under test) renders over placeholder art.
    renderer.resolve_art_path = lambda card: None  # type: ignore[method-assign]

    for subtype, color in BASICS:
        card = _basic(subtype, color)

        # NEW (current code)
        new_img = renderer.render_card(card)

        # OLD (monkeypatch the watermark renderer for the before shot)
        orig = card_renderer._render_land_watermark
        card_renderer._render_land_watermark = _old_watermark
        try:
            old_img = renderer.render_card(card)
        finally:
            card_renderer._render_land_watermark = orig

        w, h = new_img.size
        combo = Image.new("RGB", (w * 2 + 30, h), (40, 40, 40))
        combo.paste(old_img.convert("RGB"), (0, 0))
        combo.paste(new_img.convert("RGB"), (w + 30, 0))
        path = out_dir / f"compare_{subtype.lower()}.png"
        combo.save(path)
        print(f"wrote {path}  (left=OLD full-color@0.5, right=NEW bare-glyph tint@0.15)")


if __name__ == "__main__":
    main()
