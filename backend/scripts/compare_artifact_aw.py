"""Before/after comparison renders for the AW colored-artifact blend re-tune.

The AW (white colored-artifact) frame blend weight dropped from the global 0.45
to a per-color 0.30, giving white a bigger share of the gray ``m15FrameA`` base
so it reads as white-cast *metal* instead of a flat cream/white frame (the MLP
036 Canterlot Glimmer Automaton complaint).

Renders a synthetic mono-W artifact creature OLD (alpha 0.45) vs NEW (alpha 0.30)
side by side, plus a mono-B artifact creature OLD vs NEW as the audited control
(B's weight is unchanged at 0.45, so its two halves are identical — confirming
only AW moved). Output PNGs go to ``output/.scratch/artifact-aw/``.

Run from ``backend/``::  python -m scripts.compare_artifact_aw
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PIL import Image

import mtgai.rendering.layout as layout_mod
from mtgai.models.card import Card
from mtgai.rendering.card_renderer import CardRenderer
from scripts.colored_artifact_frames import (
    FRAMES_DIR,
    OUTPUT_ROOT,
    PROJECT_ROOT,
    build_blend_frame,
    build_blend_pt,
)

OUT = OUTPUT_ROOT / ".scratch" / "artifact-aw"


def _card(color: str, name: str) -> Card:
    return Card(
        name=name,
        type_line="Artifact Creature — Construct",
        mana_cost=f"{{3}}{{{color}}}",
        color_identity=[color],
        oracle_text="Vigilance\nWhen this enters, you gain 2 life.",
        flavor_text="Forged bright, it remembers the hand that shaped it.",
        power="3",
        toughness="3",
        rarity="rare",
        collector_number="A-01",
        set_code="ART",
    )


def _render_at_alpha(color: str, alpha: float) -> Image.Image:
    """Render the card with the colored-artifact frame baked at ``alpha``."""
    card = _card(color, f"{color} Automaton")
    orig = layout_mod.FRAMES_DIR
    staging = Path(tempfile.mkdtemp(prefix="frames-"))
    try:
        shutil.copytree(FRAMES_DIR, staging, dirs_exist_ok=True)
        build_blend_frame(color, alpha).save(staging / f"m15FrameA{color}.png")
        build_blend_pt(color, alpha).save(staging / f"m15PTA{color}.png")
        layout_mod.FRAMES_DIR = staging
        renderer = CardRenderer(assets_root=PROJECT_ROOT / "assets", output_root=OUT)
        renderer.resolve_art_path = lambda c: None  # type: ignore[method-assign]
        return renderer.render_card(card).convert("RGB")
    finally:
        layout_mod.FRAMES_DIR = orig
        shutil.rmtree(staging, ignore_errors=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pairs = [("W", 0.45, 0.30), ("B", 0.45, 0.45)]
    for color, old_a, new_a in pairs:
        old_img = _render_at_alpha(color, old_a)
        new_img = _render_at_alpha(color, new_a)
        w, h = old_img.size
        combo = Image.new("RGB", (w * 2 + 30, h), (40, 40, 40))
        combo.paste(old_img, (0, 0))
        combo.paste(new_img, (w + 30, 0))
        path = OUT / f"compare_{color.lower()}.png"
        combo.save(path)
        print(f"wrote {path}  (left=OLD a={old_a}, right=NEW a={new_a})")


if __name__ == "__main__":
    main()
