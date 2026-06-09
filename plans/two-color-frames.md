# Two-color (multicolor) card frames

> Trello: [Multicolor (two-color) card frames](https://trello.com/c/38VmZUZM) (6a2748f2)

## Context
Every two-color card currently renders with the flat **gold** `m15FrameM` (`determine_frame_key`
→ `frame_key_for_identity` returns `M` for any `len(colors)>1`). The bulk of a typical set is
two-color, so they all look identical. We want the modern MTG split look: left half = colour A,
right half = colour B, joined by a gold pinline — plus matching split P/T box and legendary crown.

## Approach (Option D, refined) — empirical median-stack of real frames
User picked Option D (median-stack real Scryfall cards into pixel-accurate PNGs) with the caveat
to verify Scryfall's format fits ours.

**Fit findings (research):**
- Our frames are 2010×2814 (5:7); Scryfall PNGs are 745×1040 (~0.716). A uniform scale to our
  size introduces ~0.3% vertical squash (8 px over the height) — negligible. M15 zone layout
  (title/art/type/text/PT) lines up with our `layout.py` constants when a real card is scaled to
  2010×2814 (verified by overlaying our zone boxes on real cards).
- **The card's source query was wrong.** `c:wu frame:2015` cards are flat *gold* (e.g. Efreet
  Weaponmaster) — that IS what standard two-colour "gold" cards look like. The left/right split is
  the **hybrid** frame (e.g. Azorius Guildmage `{W/U}{W/U}`). So the median source must be M15
  **hybrid** cards (`is:hybrid`), not gold two-colour cards.
- All 10 pairs have 25–35 non-legendary M15 hybrid cards (unique art) — enough to median-stack.
- Crowns already ship all 10 two-colour variants (`crowns/WU.png` …) in WUBRG order; `CROWN_PAIR_MAP`
  already exists in `card_renderer.py` (currently unused). Frame/PT filenames will match: WUBRG order
  → `m15FrameWU`, `m15PTWU`, etc.

## Design

### 1. Offline asset generation — `backend/scripts/generate_two_color_frames.py`
Standalone script (repo root via `Path(__file__).resolve().parents[2]`), kept in-repo for
regeneration. For each of the 10 pairs:
1. Query Scryfall for `frame:2015 is:hybrid id<=<pair> id>=<pair> -is:promo -is:digital
   -border:borderless -is:showcase -is:reskin -t:land -t:legendary -t:token`, `unique=art`.
2. Download each card's `png` (745×1040) to a gitignored cache (`output/.cache/two-color-frames/`),
   ~80 ms between requests (Scryfall etiquette).
3. Per-pixel **median** stack (RGB) → scale to 2010×2814.
4. Crop the PT box region (`NATIVE_PT_BOX`) → resize to PT-overlay size → mask with `m15PTM` alpha →
   save `m15PT<PAIR>.png` (the split P/T box).
5. Erase the baked-in PT box from the frame body (horizontally extend the clean text-box strip beside
   it) so non-creatures show a clean text box and creatures get the overlay on top.
6. Apply `m15FrameW`'s alpha (exact card silhouette + transparent art window) → save
   `m15Frame<PAIR>.png`.

Commits 10 frame PNGs + 10 PT box PNGs to `assets/frames/m15/`.

### 2. `rendering/colors.py`
- `COLOR_ORDER = "WUBRG"`, `two_color_key(colors) -> "WU"` (sort by WUBRG, concat).
- `frame_key_for_identity`: `len==2` (non-land) → `two_color_key`. Land/3+/colourless unchanged.

### 3. `rendering/layout.py`
- `frame_path` / `pt_box_path`: a 2-letter **colour-pair** key (not land `l*`) → `m15Frame<PAIR>` /
  `m15PT<PAIR>`. Land variants (`l*`) keep the existing lowercase path.

### 4. `rendering/card_renderer.py`
- `determine_frame_key`: artifacts still `A`, otherwise pass the colour-pair key through.
- `_load_frame`: a missing colour-pair frame falls back to **`M`** (gold), not `A`.
- `_load_pt_box`: colour-pair key → `m15PT<PAIR>` (fallback `M`); land mapping unchanged.
- `_load_legendary_crown`: 2-colour → `CROWN_PAIR_MAP` (WU.png …); 3+ → Gold.

## Tests — `backend/tests/test_rendering_frames.py`
- `two_color_key` / `frame_key_for_identity`: `[U,W]→"WU"`, `[G,W]→"WG"`, 3-colour→`M`,
  colourless→`A`, 1-colour→letter, land variants unchanged.
- `determine_frame_key`: two-colour creature→`"WU"`; two-colour artifact→`"A"`; mono/colourless/3+.
- `frame_path`/`pt_box_path`: `"WU"`→`m15FrameWU.png`/`m15PTWU.png`; land `"lw"` unchanged.
- Asset presence: all 10 `m15Frame<PAIR>.png` + `m15PT<PAIR>.png` exist and load at 2010×2814 /
  expected PT size.
- `CardRenderer._load_frame("WU")` / `_load_pt_box("WU")` / crown for a two-colour legendary load
  without falling back.

## Out of scope
- **Colored-artifact** frames (sibling card 69f86d87) — artifacts still render `A`.
- Hybrid-mana-specific detection (we apply the split to colour-identity, matching the card's intent).
- Upgrading mono/gold frames; three-colour shard/wedge frames (stay gold `M`).

## Verification
- `ruff check . && ruff format .`; `python -c "import mtgai"`; `pytest`.
- Render a two-colour card end-to-end and eyeball the split frame, PT box, and a legendary crown.
