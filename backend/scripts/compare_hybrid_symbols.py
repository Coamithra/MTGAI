"""Comparison strip + full-card render for the hybrid/twobrid/phyrexian symbol fix.

Before this change ``symbol_renderer`` had no compound-symbol handling, so
``{G/U}`` / ``{2/W}`` / ``{W/P}`` fell back to a flat gray disc with the literal
text ("G/U") drawn on it. They are now synthesized at render time from the mono
glyph parts: hybrid/twobrid as a diagonal two-tone split disc, phyrexian as a
single colored disc with the phi glyph.

This harness writes:

  - ``compare_strip_<size>.png`` — a row of (mono G, {G/U}, {G/W}, {2/W}, {W/P})
    at title-bar (~96px) and oracle-inline (~44px) sizes, so you can eyeball the
    split direction + glyph placement at both scales.
  - ``card_hybrid.png`` — a full synthetic card whose mana cost is ``{G/U}{G/U}``
    (title-bar path) and whose oracle text carries an activated cost ``{2/W}``
    (inline path), proving both call sites composite.

Run from ``backend/``::  python -m scripts.compare_hybrid_symbols
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

STRIP_SYMBOLS = ["G", "G/U", "G/W", "2/W", "W/P"]
STRIP_SIZES = [96, 44]  # title-bar-ish and oracle-inline-ish


def _strip(size: int) -> Image.Image:
    pad = max(4, size // 8)
    cell = size + pad
    strip = Image.new("RGBA", (cell * len(STRIP_SYMBOLS) + pad, cell), (40, 40, 40, 255))
    for i, sym in enumerate(STRIP_SYMBOLS):
        img = get_mana_symbol(sym, size)
        strip.alpha_composite(img, (pad + i * cell, pad // 2))
    return strip


def _hybrid_card() -> Card:
    return Card(
        name="Tidecaller of the Verge",
        type_line="Creature — Merfolk Druid",
        card_types=["Creature"],
        subtypes=["Merfolk", "Druid"],
        mana_cost="{G/U}{G/U}",
        color_identity=["G", "U"],
        power="2",
        toughness="2",
        oracle_text=(
            "{2/W}, {T}: Tidecaller of the Verge gains hexproof until end of turn.\n"
            "When this creature enters, you may pay {W/P}."
        ),
        flavor_text="Two tides, one will.",
    )


def main() -> None:
    out_dir = _REPO / "output" / ".scratch" / "hybrid-symbols"
    out_dir.mkdir(parents=True, exist_ok=True)

    for size in STRIP_SIZES:
        strip = _strip(size)
        path = out_dir / f"compare_strip_{size}.png"
        strip.convert("RGB").save(path)
        print(f"wrote {path}  ({'  '.join(STRIP_SYMBOLS)} @ {size}px)")

    renderer = card_renderer.CardRenderer(output_root=out_dir)
    renderer.resolve_art_path = lambda card: None  # type: ignore[method-assign]
    card = _hybrid_card()
    card_img = renderer.render_card(card)
    card_path = out_dir / "card_hybrid.png"
    card_img.convert("RGB").save(card_path)
    print(f"wrote {card_path}  (title {{G/U}}{{G/U}} + inline {{2/W}} / {{W/P}})")


if __name__ == "__main__":
    main()
