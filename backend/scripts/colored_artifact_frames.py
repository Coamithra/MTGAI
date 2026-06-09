"""Build & compare colored-artifact M15 frame variants.

Two methods (full writeup in ``learnings/colored-artifact-frames.md``):

* ``blend``  (Option A) — alpha-blend the gray ``m15FrameA`` with each mono
  color frame at a fixed opacity. Stays 100% in our native 2010x2814 Card
  Conjurer geometry, so nothing can misalign. Ships fast, not pixel-real.
* ``median`` (Option D) — the **mature empirical-stack** pipeline ported from
  ``generate_two_color_frames.py`` (which shipped the two-color split frames):
  per-pixel **p80 percentile** stack of real Scryfall artifact cards per color
  (the static frame survives while varying art/text is out-voted; a high
  percentile biases toward the bright frame so dark ghost text is rejected
  better than a 50th-percentile median). The contested zones are then cleaned:
  the title/type/rules/bottom **text bars are rebuilt from the Option-A blend**
  (text-free, artifact-tinted, in our exact geometry), the baked-in P/T box is
  erased, and the silhouette + transparent art window are borrowed from
  ``m15FrameA``. The P/T overlay is cropped from the stack (authentic tint),
  masked to ``m15PTA``. Net: authentic stacked body/pinline/colour + clean bars.

  Verdict (2026-06-09, see learnings/colored-artifact-frames.md "tried-and-
  rejected"): the median path LOSES to the blend for artifacts. The registration
  worry (Scryfall 745x1040 aspect 0.7163 vs our 2010x2814 0.7143, a ~0.3% squash)
  turned out moot — the masks register it cleanly. The real killer is that a
  colored artifact is a subtle tint over a busy/variable gray metal texture, so
  the stack comes out blotchy + miscoloured. Kept here as a reproducible baseline.

Both methods write ``m15Frame{AW,AU,AB,AR,AG,AM}.png`` plus matching
``m15PT*`` boxes. Mono colors + ``AM`` (multicolor artifact, ``c=m``) use the
method; a color with too few real cards to stack falls back to the blend.

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
CACHE_DIR = OUTPUT_ROOT / ".cache" / "colored-artifact-frames"

MONO_COLORS = ["W", "U", "B", "R", "G"]
ARTIFACT_KEYS = {"W": "AW", "U": "AU", "B": "AB", "R": "AR", "G": "AG"}
MULTICOLOR_KEY = "AM"

# Mono color frame the blend tints toward; AM tints toward gold (M).
DEFAULT_BLEND_ALPHA = 0.45

# Native frame geometry (kept in sync with rendering/layout.py).
FRAME_W, FRAME_H = 2010, 2814
TARGET_GEOM = (FRAME_W, FRAME_H)
SCRYFALL_GEOM = (745, 1040)
PT_BOX = (1522, 2490, 1900, 2696)  # NATIVE_PT_BOX (left, top, right, bottom)
PT_OVERLAY_SIZE = (377, 206)  # m15PT*.png dimensions
BOTTOM_STRIP_TOP = 2596  # just below NATIVE_TEXT_BOX.bottom (2595) — collector strip

# Per-pixel percentile (not the 50th-percentile median): card text/watermarks are
# *dark* on a *bright* frame, so biasing toward the brighter value rejects ghost
# text far better than the median while keeping the frame colour. 80 matches the
# shipped two-color frames (see generate_two_color_frames.py / learnings doc).
STACK_PERCENTILE = 80.0
MIN_STACK = 8  # too few real cards to out-vote text → fall back to the blend

_UA = {"User-Agent": "MTGAI-frame-research/1.0 (local research tool)", "Accept": "application/json"}


# ---------------------------------------------------------------------------
# Option A — blend
# ---------------------------------------------------------------------------
def _load(name: str) -> Image.Image:
    return Image.open(FRAMES_DIR / f"{name}.png").convert("RGBA")


def _mask_alpha(name: str) -> Image.Image:
    return Image.open(FRAMES_DIR / f"{name}.png").convert("RGBA").split()[3]


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
# Option D — mature empirical percentile-stack (ported from two-color frames)
# ---------------------------------------------------------------------------
def _scryfall_search(query: str, unique: str = "art") -> list[dict]:
    """Run a Scryfall search, paginating through all result pages."""
    url = "https://api.scryfall.com/cards/search?" + urllib.parse.urlencode(
        {"q": query, "unique": unique, "order": "released", "dir": "asc"}
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


def fetch_artifact_pngs(scry_color: str, n: int, refresh: bool = False) -> list[Path]:
    """Download up to ``n`` real M15 artifact card PNGs for a Scryfall color token.

    ``scry_color`` is ``w``/``u``/``b``/``r``/``g`` (exact mono) or ``m``
    (multicolor). Vehicles are excluded — they carry a visibly different darker
    frame that would muddy the stack. ``unique:art`` keeps one printing per art
    so a heavily-reprinted card's art can't dominate (worse ghosting). Cached by
    Scryfall id under ``CACHE_DIR/<scry_color>``.
    """
    query = (
        f"frame:2015 t:artifact c={scry_color} -t:land -t:vehicle "
        "-is:promo -is:funny -border:borderless -is:showcase -is:extended "
        "-is:textless -is:digital game:paper"
    )
    cards = _scryfall_search(query)
    cache_dir = CACHE_DIR / scry_color
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for card in cards:
        if len(paths) >= n:
            break
        png_url = (card.get("image_uris") or {}).get("png")
        if not png_url:  # double-faced / missing — skip
            continue
        dest = cache_dir / f"{card['id']}.png"
        if refresh or not dest.is_file():
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


def _stack_percentile(paths: list[Path]) -> Image.Image:
    """Per-pixel p80 of all card PNGs, scaled to our native frame size (RGB)."""
    stack = np.empty((len(paths), SCRYFALL_GEOM[1], SCRYFALL_GEOM[0], 3), dtype=np.uint8)
    for i, p in enumerate(paths):
        img = Image.open(p).convert("RGB")
        if img.size != SCRYFALL_GEOM:
            img = img.resize(SCRYFALL_GEOM, Image.LANCZOS)
        stack[i] = np.asarray(img)
    blended = np.percentile(stack, STACK_PERCENTILE, axis=0).astype(np.uint8)
    return Image.fromarray(blended, "RGB").resize(TARGET_GEOM, Image.LANCZOS)


def _erase_pt_box(frame_rgb: Image.Image) -> Image.Image:
    """Paint over the baked-in P/T box with the clean text-box strip to its left.

    The text box + bottom frame border are horizontally translation-invariant, so
    copying an equal-width strip from immediately left of the P/T box extends the
    clean background over it — giving non-creature artifacts a clean text box
    (creatures get the separate P/T overlay on top).
    """
    left, top, right, bottom = PT_BOX
    width = right - left
    src_left = left - width
    if src_left < 0:
        return frame_rgb
    out = frame_rgb.copy()
    strip = out.crop((src_left, top, left, bottom))
    out.paste(strip, (left, top))
    return out


def _blend_bars(frame_rgb: Image.Image, tint: str) -> Image.Image:
    """Replace title/type/rules/bottom text zones with the clean Option-A blend.

    The real-card stack leaves shared ghost text in the flat text bars (card
    names, "Artifact Creature —", collector line) that even a high percentile
    can't out-vote, and averaged rules-text in the box. The Option-A blend is
    text-free, artifact-tinted, and already in our exact 2010x2814 geometry, so
    compositing it into those mask zones erases the ghosts while keeping the
    stacked body/pinline/border/colour. ``tint`` is the mono letter (W/U/B/R/G)
    or ``M`` for the gold multicolor blend.
    """
    blend = build_blend_frame(tint).convert("RGB")
    out = frame_rgb.copy()
    for mask_name in ("m15MaskTitle", "m15MaskType", "m15MaskRules"):
        out.paste(blend, (0, 0), _mask_alpha(mask_name))
    bottom = blend.crop((0, BOTTOM_STRIP_TOP, FRAME_W, FRAME_H))
    out.paste(bottom, (0, BOTTOM_STRIP_TOP))
    return out


def _apply_silhouette(frame_rgb: Image.Image) -> Image.Image:
    """Clip to m15FrameA's alpha (exact card outline + transparent art window)."""
    out = frame_rgb.convert("RGBA")
    out.putalpha(_load("m15FrameA").split()[3])
    return out


def _build_pt_box(frame_rgb: Image.Image) -> Image.Image:
    """Crop the P/T box from the stacked frame, masked to m15PTA's shape.

    The averaged P/T digits vary across cards so they wash toward the box
    background, leaving the authentic tinted artifact P/T box.
    """
    crop = frame_rgb.crop(PT_BOX).resize(PT_OVERLAY_SIZE, Image.LANCZOS).convert("RGBA")
    pt_template = _load("m15PTA")
    if pt_template.size != PT_OVERLAY_SIZE:
        pt_template = pt_template.resize(PT_OVERLAY_SIZE, Image.LANCZOS)
    crop.putalpha(pt_template.split()[3])
    return crop


def build_stack_frame(
    tint: str, scry_color: str, n: int, refresh: bool
) -> tuple[Image.Image, Image.Image, int] | None:
    """Stack real artifacts for one color → (frame RGBA, P/T RGBA, n_used).

    Returns ``None`` when too few real cards exist to out-vote text (caller
    falls back to the blend for that key).
    """
    paths = fetch_artifact_pngs(scry_color, n, refresh)
    if len(paths) < MIN_STACK:
        return None
    stacked = _stack_percentile(paths)
    pt_box = _build_pt_box(stacked)
    body = _blend_bars(_erase_pt_box(stacked), tint)
    frame = _apply_silhouette(body)
    return frame, pt_box, len(paths)


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------
def write_variants(out_dir: Path, method: str, *, n: int, alpha: float, refresh: bool) -> None:
    """Build all colored-artifact frame + P/T assets into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # tint letter -> Scryfall color token; AM is multicolor (c=m).
    targets = [(ARTIFACT_KEYS[c], c, c.lower()) for c in MONO_COLORS]
    targets.append((MULTICOLOR_KEY, "M", "m"))
    for key, tint, scry in targets:
        if method == "blend":
            build_blend_frame(tint, alpha).save(out_dir / f"m15Frame{key}.png")
            build_blend_pt(tint, alpha).save(out_dir / f"m15PT{key}.png")
            print(f"  {key}: m15Frame{key}.png (blend a={alpha}) + m15PT{key}.png")
            continue
        result = build_stack_frame(tint, scry, n, refresh)
        if result is None:
            build_blend_frame(tint, alpha).save(out_dir / f"m15Frame{key}.png")
            build_blend_pt(tint, alpha).save(out_dir / f"m15PT{key}.png")
            print(f"  {key}: m15Frame{key}.png (blend fallback — too few cards) + m15PT{key}.png")
            continue
        frame, pt_box, used = result
        frame.save(out_dir / f"m15Frame{key}.png")
        pt_box.save(out_dir / f"m15PT{key}.png")
        print(f"  {key}: m15Frame{key}.png (stack p{STACK_PERCENTILE:g} n={used}) + m15PT{key}.png")


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


def compare(n: int, alpha: float, refresh: bool) -> None:
    import tempfile

    import mtgai.rendering.layout as layout_mod
    from mtgai.rendering.card_renderer import CardRenderer
    from mtgai.runtime.active_project import ProjectState, write_active_project
    from mtgai.settings.model_settings import ModelSettings

    out_root = OUTPUT_ROOT / "colored-artifact-comparison"
    out_root.mkdir(parents=True, exist_ok=True)

    tmp_asset: Path | None = None
    orig_frames_dir = layout_mod.FRAMES_DIR

    try:
        # Empty active project so resolve_art_path returns None -> placeholder art.
        tmp_asset = Path(tempfile.mkdtemp(prefix="cmp-asset-"))
        write_active_project(
            ProjectState(set_code="ART", settings=ModelSettings(asset_folder=str(tmp_asset)))
        )
        cards = _example_cards()

        for method in ("blend", "median"):
            print(f"\n=== {method} ===")
            staging = Path(tempfile.mkdtemp(prefix=f"frames-{method}-"))
            try:
                shutil.copytree(FRAMES_DIR, staging, dirs_exist_ok=True)
                write_variants(staging, method, n=n, alpha=alpha, refresh=refresh)

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
        if tmp_asset is not None:
            shutil.rmtree(tmp_asset, ignore_errors=True)

    print(f"\nComparison renders in: {out_root}")
    print("  blend/   — Option A (geometry-safe alpha blend)")
    print("  median/  — Option D (mature percentile stack)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Build colored-artifact frames into an assets dir")
    b.add_argument("--method", choices=["blend", "median"], required=True)
    b.add_argument("--out", default=str(FRAMES_DIR), help="Output frames dir (default: assets)")
    b.add_argument("--n", type=int, default=40, help="Cards per color to stack")
    b.add_argument("--alpha", type=float, default=DEFAULT_BLEND_ALPHA)
    b.add_argument("--refresh", action="store_true", help="Re-download, ignore cache")

    c = sub.add_parser("compare", help="Render example cards with both methods")
    c.add_argument("--n", type=int, default=40)
    c.add_argument("--alpha", type=float, default=DEFAULT_BLEND_ALPHA)
    c.add_argument("--refresh", action="store_true", help="Re-download, ignore cache")

    args = parser.parse_args()
    if args.cmd == "build":
        print(f"Building {args.method} frames -> {args.out}")
        write_variants(
            Path(args.out), args.method, n=args.n, alpha=args.alpha, refresh=args.refresh
        )
    elif args.cmd == "compare":
        compare(args.n, args.alpha, args.refresh)


if __name__ == "__main__":
    main()
