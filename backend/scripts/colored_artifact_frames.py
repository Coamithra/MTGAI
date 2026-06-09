"""Build & compare colored-artifact M15 frame variants.

Two methods (full writeup in ``learnings/colored-artifact-frames.md``):

* ``blend``  (Option A) — alpha-blend the gray ``m15FrameA`` with each mono
  color frame at a fixed opacity. Stays 100% in our native 2010x2814 Card
  Conjurer geometry, so nothing can misalign. Ships fast, not pixel-real.
* ``median`` (Option D) — per-pixel MEDIAN stack of real Scryfall artifact
  cards per color: the static frame survives while varying art/text is
  out-voted. Resized onto our canvas and the art window punched with
  ``m15FrameA``'s alpha. Pixel-real frame, BUT Scryfall geometry
  (745x1040, aspect 0.7163) differs from ours (2010x2814, aspect 0.7143),
  so interior elements (pinlines) can sit a few px off our masks.

Both methods write ``m15Frame{AW,AU,AB,AR,AG,AM}.png`` plus matching
``m15PT*`` boxes (the P/T box is always the geometry-safe blend — its tint
is uniform and it is not the contested element). Mono colors use the
method; ``AM`` (multicolor artifact) is always a blend (too varied to median
cleanly).

Subcommands::

    python -m scripts.colored_artifact_frames build --method blend
    python -m scripts.colored_artifact_frames build --method median
    python -m scripts.colored_artifact_frames compare

``compare`` builds both into temp dirs and renders one example artifact
creature per color with each, into ``output/colored-artifact-comparison/``,
for side-by-side review — it never touches the tracked assets dir.
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRAMES_DIR = PROJECT_ROOT / "assets" / "frames" / "m15"
OUTPUT_ROOT = PROJECT_ROOT / "output"
CACHE_DIR = OUTPUT_ROOT / "scryfall-frame-cache"

MONO_COLORS = ["W", "U", "B", "R", "G"]
ARTIFACT_KEYS = {"W": "AW", "U": "AU", "B": "AB", "R": "AR", "G": "AG"}
MULTICOLOR_KEY = "AM"

# Mono color frame the blend tints toward; AM tints toward gold (M).
DEFAULT_BLEND_ALPHA = 0.45
SCRYFALL_GEOM = (745, 1040)
TARGET_GEOM = (2010, 2814)

_UA = {"User-Agent": "MTGAI-frame-research/1.0 (local research tool)", "Accept": "application/json"}


# ---------------------------------------------------------------------------
# Option A — blend
# ---------------------------------------------------------------------------
def _load(name: str) -> Image.Image:
    return Image.open(FRAMES_DIR / f"{name}.png").convert("RGBA")


def build_blend_frame(color: str, alpha: float = DEFAULT_BLEND_ALPHA) -> Image.Image:
    """Alpha-blend the gray artifact frame toward a mono color frame.

    ``color`` is a mono color letter (W/U/B/R/G) or ``M`` for the gold
    multicolor frame. Both inputs share our 2010x2814 geometry + the
    transparent art window, so the result stays perfectly aligned.
    """
    base = _load("m15FrameA")
    tint = _load(f"m15Frame{color}")
    return Image.blend(base, tint, alpha)


def build_blend_pt(color: str, alpha: float = DEFAULT_BLEND_ALPHA) -> Image.Image:
    """Blend the gray artifact P/T box toward a mono color P/T box."""
    base = _load("m15PTA")
    tint = _load(f"m15PT{color}")
    return Image.blend(base, tint, alpha)


# ---------------------------------------------------------------------------
# Option D — Scryfall median stack
# ---------------------------------------------------------------------------
def _scryfall_search(query: str) -> list[dict]:
    """Run a Scryfall search, paginating through all result pages."""
    url = "https://api.scryfall.com/cards/search?" + urllib.parse.urlencode(
        {"q": query, "unique": "prints"}
    )
    out: list[dict] = []
    while url:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
        out.extend(data.get("data", []))
        url = data.get("next_page")
        time.sleep(0.1)  # Scryfall asks for 50-100ms between requests
    return out


def fetch_artifact_pngs(color: str, n: int, cache_dir: Path) -> list[Path]:
    """Download up to ``n`` real mono-color artifact card PNGs for a color.

    Cached by Scryfall id under ``cache_dir`` so re-runs don't re-fetch.
    """
    query = (
        f"frame:2015 t:artifact c={color.lower()} -t:land "
        "-is:promo -is:funny -border:borderless -is:showcase -is:extended "
        "-is:textless game:paper"
    )
    cards = _scryfall_search(query)
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for card in cards:
        if len(paths) >= n:
            break
        img_uris = card.get("image_uris") or {}
        png_url = img_uris.get("png")
        if not png_url:  # double-faced / missing — skip
            continue
        dest = cache_dir / f"{card['id']}.png"
        if not dest.is_file():
            req = urllib.request.Request(png_url, headers={"User-Agent": _UA["User-Agent"]})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    dest.write_bytes(r.read())
            except (urllib.error.URLError, OSError) as exc:
                print(f"  skip {card.get('name', card['id'])}: download failed ({exc})")
                dest.unlink(missing_ok=True)
                continue
            time.sleep(0.1)
        paths.append(dest)
    return paths


def median_stack(pngs: list[Path]) -> Image.Image:
    """Per-pixel median of real card PNGs -> the static frame (RGB)."""
    stack = np.empty((len(pngs), SCRYFALL_GEOM[1], SCRYFALL_GEOM[0], 3), dtype=np.uint8)
    for i, p in enumerate(pngs):
        img = Image.open(p).convert("RGB")
        if img.size != SCRYFALL_GEOM:
            img = img.resize(SCRYFALL_GEOM, Image.LANCZOS)
        stack[i] = np.asarray(img)
    median = np.median(stack, axis=0).astype(np.uint8)
    return Image.fromarray(median, "RGB")


def build_median_frame(color: str, n: int, cache_dir: Path) -> tuple[Image.Image, int]:
    """Median-stack real Scryfall artifacts, fit to our canvas, punch art hole.

    The median frame is resized (non-proportional) to 2010x2814 so its outer
    bounds match ours, then given ``m15FrameA``'s alpha channel — reusing our
    exact card silhouette + art-window hole so art still composites correctly.
    Any interior misalignment shows as a thin ring at the art window (honest).
    """
    pngs = fetch_artifact_pngs(color, n, cache_dir)
    if not pngs:
        raise RuntimeError(f"No Scryfall artifacts found for color {color}")
    frame = median_stack(pngs).resize(TARGET_GEOM, Image.LANCZOS).convert("RGBA")
    frame.putalpha(_load("m15FrameA").split()[3])
    return frame, len(pngs)


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------
def write_variants(out_dir: Path, method: str, *, n: int, alpha: float) -> None:
    """Build all colored-artifact frame + P/T assets into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for color in MONO_COLORS:
        key = ARTIFACT_KEYS[color]
        if method == "blend":
            frame = build_blend_frame(color, alpha)
            note = f"blend a={alpha}"
        else:
            frame, used = build_median_frame(color, n, CACHE_DIR)
            note = f"median n={used}"
        frame.save(out_dir / f"m15Frame{key}.png")
        build_blend_pt(color, alpha).save(out_dir / f"m15PT{key}.png")
        print(f"  {key}: m15Frame{key}.png ({note}) + m15PT{key}.png")
    # AM (multicolor artifact) is always a gold blend.
    build_blend_frame("M", alpha).save(out_dir / f"m15Frame{MULTICOLOR_KEY}.png")
    build_blend_pt("M", alpha).save(out_dir / f"m15PT{MULTICOLOR_KEY}.png")
    print(f"  {MULTICOLOR_KEY}: m15Frame{MULTICOLOR_KEY}.png (blend gold) + m15PT box")


# ---------------------------------------------------------------------------
# Compare — render example cards with each method
# ---------------------------------------------------------------------------
def _example_cards():
    from mtgai.models.card import Card

    specs = [
        ("W", "Sunforged Sentinel", "{2}{W}", "Vigilance\nWhen this enters, gain 3 life.", 2, 3),
        ("U", "Tidecaller Automaton", "{2}{U}", "When this enters, draw a card.", 2, 2),
        (
            "B",
            "Grave-Iron Reaver",
            "{2}{B}",
            "Menace\nWhen this dies, each foe loses 2 life.",
            3,
            2,
        ),
        ("R", "Emberforge Colossus", "{3}{R}", "Haste\nWhen this attacks, deal 1 damage.", 4, 3),
        ("G", "Bramblesteel Guardian", "{3}{G}", "Reach, trample", 4, 4),
        ("WU", "Skyclad Arbiter", "{2}{W}{U}", "Flying\nWhen this enters, scry 2.", 3, 3),
        ("", "Hollow Sentinel", "{3}", "When this enters, you gain 1 life.", 2, 2),
    ]
    cards = []
    for i, (ci, name, cost, oracle, pw, tn) in enumerate(specs, start=1):
        identity = list(ci) if ci else []
        cards.append(
            Card(
                name=name,
                type_line="Artifact Creature — Construct",
                mana_cost=cost,
                color_identity=identity,
                oracle_text=oracle,
                power=str(pw),
                toughness=str(tn),
                rarity="rare",
                collector_number=f"A-{i:02d}",
                set_code="ART",
            )
        )
    return cards


def compare(n: int, alpha: float) -> None:
    import tempfile

    import mtgai.rendering.layout as layout_mod
    from mtgai.rendering.card_renderer import CardRenderer
    from mtgai.runtime.active_project import ProjectState, write_active_project
    from mtgai.settings.model_settings import ModelSettings

    out_root = OUTPUT_ROOT / "colored-artifact-comparison"
    out_root.mkdir(parents=True, exist_ok=True)

    # Empty active project so resolve_art_path returns None -> placeholder art.
    tmp_asset = Path(tempfile.mkdtemp(prefix="cmp-asset-"))
    write_active_project(
        ProjectState(set_code="ART", settings=ModelSettings(asset_folder=str(tmp_asset)))
    )

    cards = _example_cards()
    orig_frames_dir = layout_mod.FRAMES_DIR

    try:
        for method in ("blend", "median"):
            print(f"\n=== {method} ===")
            staging = Path(tempfile.mkdtemp(prefix=f"frames-{method}-"))
            try:
                shutil.copytree(FRAMES_DIR, staging, dirs_exist_ok=True)
                write_variants(staging, method, n=n, alpha=alpha)

                layout_mod.FRAMES_DIR = staging
                method_out = out_root / method
                method_out.mkdir(parents=True, exist_ok=True)
                renderer = CardRenderer(
                    assets_root=PROJECT_ROOT / "assets", output_root=OUTPUT_ROOT
                )
                for card in cards:
                    img = renderer.render_card(card, total_cards=len(cards))
                    label = "".join(card.color_identity) or "A"
                    img.save(method_out / f"{label}_{card.name.replace(' ', '_')}.png")
                    print(f"  rendered {label}: {card.name}")
            finally:
                layout_mod.FRAMES_DIR = orig_frames_dir
                shutil.rmtree(staging, ignore_errors=True)
    finally:
        shutil.rmtree(tmp_asset, ignore_errors=True)

    print(f"\nComparison renders in: {out_root}")
    print("  blend/   — Option A (geometry-safe alpha blend)")
    print("  median/  — Option D (Scryfall median stack)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Build colored-artifact frames into an assets dir")
    b.add_argument("--method", choices=["blend", "median"], required=True)
    b.add_argument("--out", default=str(FRAMES_DIR), help="Output frames dir (default: assets)")
    b.add_argument("--n", type=int, default=35, help="Cards per color to median-stack")
    b.add_argument("--alpha", type=float, default=DEFAULT_BLEND_ALPHA)

    c = sub.add_parser("compare", help="Render example cards with both methods")
    c.add_argument("--n", type=int, default=35)
    c.add_argument("--alpha", type=float, default=DEFAULT_BLEND_ALPHA)

    args = parser.parse_args()
    if args.cmd == "build":
        print(f"Building {args.method} frames -> {args.out}")
        write_variants(Path(args.out), args.method, n=args.n, alpha=args.alpha)
    elif args.cmd == "compare":
        compare(args.n, args.alpha)


if __name__ == "__main__":
    main()
