"""Generate pixel-accurate two-color M15 split frames by percentile-stacking real cards.

Option D from ``learnings/colored-artifact-frames.md``: the frame pixels are constant
across all cards of a given frame variant while art/text vary, so a per-pixel stack of
many aligned cards reconstructs the static frame (varying text/art is out-voted). We take
a high percentile rather than the median — card text/watermarks are dark on a bright
frame, so biasing toward the brighter value rejects ghosts better (see STACK_PERCENTILE).

Source = real MTG **hybrid** M15 cards (e.g. Azorius Guildmage ``{W/U}{W/U}``), which carry
the left-colourA / right-colourB split + gold pinline the card asks for. (Plain ``c:wu``
two-colour cards are flat *gold* — that is the existing ``m15FrameM`` look.)

For each of the ten colour pairs this writes ``m15Frame<PAIR>.png`` into
``assets/frames/m15/`` — the split frame, clipped to our exact card silhouette
(it borrows ``m15FrameW``'s alpha, so the art window is transparent and the outline
matches the mono frames pixel-for-pixel). The title/type bars + bottom strip come from
the gold ``m15FrameM`` frame: real hybrid cards keep GOLD furniture over the split body
(e.g. Senate Guildmage), and the stack can't provide it cleanly anyway (shared ghost
text). No P/T overlay is written — two-colour creatures use the gold ``m15PTM.png``
(``layout.pt_box_path`` maps split keys to it), the same real-card convention.

Idempotent: downloaded card PNGs are cached under ``output/.cache/two-color-frames/`` (gitignored),
so re-runs only re-stack. Pass ``--pairs WU,UB`` to limit, ``--limit N`` to cap cards per pair,
``--refresh`` to ignore the cache.

Run from anywhere:
    PYTHONIOENCODING=utf-8 python backend/scripts/generate_two_color_frames.py
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
FRAMES_DIR = REPO_ROOT / "assets" / "frames" / "m15"
CACHE_DIR = REPO_ROOT / "output" / ".cache" / "two-color-frames"

# Native frame size + the P/T box zone (kept in sync with rendering/layout.py).
FRAME_W, FRAME_H = 2010, 2814
PT_BOX = (1522, 2490, 1900, 2696)  # NATIVE_PT_BOX (left, top, right, bottom)

# WUBRG-ordered colour pairs — matches the existing crown/PT filenames.
COLOR_ORDER = "WUBRG"
PAIRS = ["WU", "WB", "WR", "WG", "UB", "UR", "UG", "BR", "BG", "RG"]

SCRYFALL_SEARCH = "https://api.scryfall.com/cards/search"
USER_AGENT = "MTGAI-frame-research/1.0 (https://github.com/Coamithra/MTGAI)"
REQUEST_SPACING_S = 0.08  # Scryfall asks for 50-100 ms between requests.
DEFAULT_LIMIT = 60

# Per-pixel percentile (not the 50th-percentile median): card text/watermarks are *dark*
# on a *bright* frame, so biasing toward the brighter value rejects ghost text far better
# than the median while keeping the frame colour. 80 balances ghost suppression vs. not
# washing the colour out (90+ over-brightens; see plans/two-color-frames.md).
STACK_PERCENTILE = 80.0


def _get(url: str) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _search_pngs(pair: str, limit: int) -> list[tuple[str, str]]:
    """Return [(scryfall_id, png_url)] of M15 hybrid cards with colour identity == pair."""
    ident = pair.lower()
    query = (
        f"frame:2015 is:hybrid id<={ident} id>={ident} "
        "-is:promo -is:digital -border:borderless -is:showcase -is:reskin "
        "-t:land -t:legendary -t:token"
    )
    url = f"{SCRYFALL_SEARCH}?q={urllib.parse.quote(query)}&unique=art&order=released&dir=asc"
    out: list[tuple[str, str]] = []
    while url and len(out) < limit:
        data = _get(url)
        for card in data.get("data", []):
            png = card.get("image_uris", {}).get("png")
            if png:
                out.append((card["id"], png))
            if len(out) >= limit:
                break
        url = data.get("next_page") if data.get("has_more") else None
        time.sleep(REQUEST_SPACING_S)
    return out


def _download(pair: str, cards: list[tuple[str, str]], refresh: bool) -> list[Path]:
    pair_cache = CACHE_DIR / pair
    pair_cache.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for sid, png_url in cards:
        dest = pair_cache / f"{sid}.png"
        if refresh or not dest.is_file():
            req = urllib.request.Request(png_url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    dest.write_bytes(resp.read())
            except urllib.error.URLError as exc:
                # URLError is the superclass of HTTPError — covers DNS/timeout/reset
                # too, so one flaky download skips that card rather than aborting the run.
                print(f"  ! {sid}: {exc}")
                continue
            time.sleep(REQUEST_SPACING_S)
        paths.append(dest)
    return paths


def _stack_frame(paths: list[Path]) -> Image.Image:
    """Per-pixel percentile of all cards, scaled to our native frame size (RGB)."""
    stack = np.empty((len(paths), 1040, 745, 3), dtype=np.uint8)
    for i, p in enumerate(paths):
        img = Image.open(p).convert("RGB")
        if img.size != (745, 1040):
            img = img.resize((745, 1040), Image.LANCZOS)
        stack[i] = np.asarray(img)
    blended = np.percentile(stack, STACK_PERCENTILE, axis=0).astype(np.uint8)
    return Image.fromarray(blended, "RGB").resize((FRAME_W, FRAME_H), Image.LANCZOS)


def _clean_bars(frame: Image.Image) -> Image.Image:
    """Replace the title + type bar zones with the gold ``m15FrameM`` bars.

    The bars are flat colour fields with no art, so the real-card stack leaves shared
    ghost text there ("Creature —", card names) that even a high percentile can't out-vote.
    Real hybrid cards keep GOLD title/type bars and a gold P/T box over the split body
    (e.g. Senate Guildmage) — exactly the ``m15FrameM`` look — so the gold template is
    both the clean source AND the canonical one; the stack keeps the body, border,
    pinline, and rules box.
    """
    gold = Image.open(FRAMES_DIR / "m15FrameM.png").convert("RGBA")
    out = frame.copy()
    for mask_name in ("m15MaskTitle", "m15MaskType"):
        zone = Image.open(FRAMES_DIR / f"{mask_name}.png").convert("RGBA").split()[3]
        out.paste(gold, (0, 0), zone)
    # Bottom collector strip: flat dark border that ghosts shared copyright/collector
    # text; the gold frame is clean there too. (Rules box ends at NATIVE_TEXT_BOX.bottom.)
    bottom = gold.crop((0, 2596, FRAME_W, FRAME_H)).convert("RGB")
    out.paste(bottom, (0, 2596))
    return out


def _clean_rules_box(frame_rgb: Image.Image) -> Image.Image:
    """Replace the rules-box interior with the mono frame's clean parchment.

    The text box is colour-neutral beige on every M15 frame, so borrowing
    ``m15FrameW``'s rules zone (masked by ``m15MaskRules``) erases the guild watermark
    and shared rules-text ghosts the stack leaves behind, with no loss of colour fidelity
    (the split-coloured frame border around the box stays from the stack).
    """
    mono = Image.open(FRAMES_DIR / "m15FrameW.png").convert("RGB")
    rules_mask = Image.open(FRAMES_DIR / "m15MaskRules.png").convert("RGBA").split()[3]
    out = frame_rgb.copy()
    out.paste(mono, (0, 0), rules_mask)
    return out


def _erase_pt_box(frame_rgb: Image.Image) -> Image.Image:
    """Paint over the baked-in P/T box with the clean text-box strip just left of it.

    The text box + bottom frame border are horizontally translation-invariant, so copying
    an equal-width strip from immediately left of the P/T box extends the clean background
    over it — giving non-creature two-colour cards a clean text box (creatures get the
    separate P/T overlay on top).
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


def _apply_silhouette(frame_rgb: Image.Image) -> Image.Image:
    """Clip to m15FrameW's alpha (exact outline + transparent art window)."""
    template = Image.open(FRAMES_DIR / "m15FrameW.png").convert("RGBA")
    out = frame_rgb.convert("RGBA")
    out.putalpha(template.split()[3])
    return out


def generate_pair(pair: str, limit: int, refresh: bool) -> None:
    print(f"[{pair}] searching Scryfall…")
    cards = _search_pngs(pair, limit)
    print(f"[{pair}] {len(cards)} cards; downloading…")
    paths = _download(pair, cards, refresh)
    if len(paths) < 8:
        print(f"[{pair}] ! only {len(paths)} usable cards — skipping (too few to stack)")
        return
    print(f"[{pair}] stacking {len(paths)} cards (p{STACK_PERCENTILE:g})…")
    stacked = _stack_frame(paths)

    body = _clean_bars(_clean_rules_box(_erase_pt_box(stacked)))
    frame = _apply_silhouette(body)
    frame.save(FRAMES_DIR / f"m15Frame{pair}.png")
    print(f"[{pair}] wrote m15Frame{pair}.png")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pairs", help="Comma-separated subset, e.g. WU,UB (default: all 10)")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Max cards per pair")
    ap.add_argument("--refresh", action="store_true", help="Re-download, ignore cache")
    args = ap.parse_args()

    pairs = [p.strip().upper() for p in args.pairs.split(",")] if args.pairs else PAIRS
    for pair in pairs:
        generate_pair(pair, args.limit, args.refresh)


if __name__ == "__main__":
    main()
