# Colored Artifact Frames — Research & Future Plan
> Tracked: [Trello — Colored artifact frames](https://trello.com/c/xiFbWsDH)

## Background
Modern MTG (Kaladesh onwards) uses a distinct frame for colored artifacts — a blend of the artifact gray texture with the card's color identity. Examples: Esper Sentinel (white artifact), The Blackstaff of Waterdeep (blue artifact). Our renderer currently uses the standard color/gold frame for colored artifacts, which is acceptable but not pixel-accurate.

## Key Finding: No Pre-Made Assets Exist
None of the reference projects have pre-baked colored artifact frame PNGs:
- **Card Conjurer** (`koherenc3/sbgames-cardconjurer`): Artifacts always get gray frame with `colorOverlayCheck = false`. No colored artifact variant.
- **wingedsheep/mtg-card-generator**: Artifacts always map to "Artifact" frame, no colored variant.
- **Investigamer/Proxyshop**: Uses Photoshop templates with layer compositing, not standalone PNGs.

## Card Conjurer's Masking Pipeline (for reference)
Card Conjurer achieves frame variety through dynamic compositing, not separate assets. The recipe:

1. **Start**: Opaque black RGBA canvas
2. **Apply masks**: `globalCompositeOperation = 'source-in'` with mask PNGs sequentially
   - `m15MaskFrame` — main frame body
   - `m15MaskPinline` — thin inner border lines
   - `m15MaskBorder` — outer card border
   - `m15MaskTitle` — title bar zone
   - `m15MaskType` — type bar zone
   - `m15MaskRules` — rules text box zone
3. **Draw frame texture**: Clipped by accumulated mask alpha
4. **Color overlay** (optional): `source-in` fill with solid color — this is how colored cards get their tint. Artifacts skip this step.
5. **Composite onto card canvas**: `source-over`

Each zone (frame body, pinline, border, etc.) goes through this pipeline independently, potentially with different color overlays. This is what enables hybrid frames (e.g., WU gold pinline on white frame body).

### Pillow Equivalent
The `source-in` operation in Pillow can be approximated with:
```python
from PIL import Image, ImageChops
# mask_alpha acts as the gate
result_alpha = ImageChops.multiply(canvas.split()[3], mask.split()[3])
canvas.putalpha(result_alpha)
```
We already use this approach for the legendary crown title cutout (`_load_legendary_crown` in card_renderer.py).

## Implementation Options (for future)

### Option A: Pre-Bake Blended PNGs (Simplest)
- Alpha-blend `m15FrameA.png` with each color frame at ~40-50% opacity
- Save as `m15FrameAW.png`, `m15FrameAU.png`, `m15FrameAB.png`, `m15FrameAR.png`, `m15FrameAG.png`, `m15FrameAM.png`
- Same for PT boxes: `m15PTAW.png`, etc.
- One-time offline step, zero render-time complexity
- **Downside**: Doesn't match real MTG exactly (real cards tint specific zones differently)

### Option B: Zone-Based Masking (Most Accurate)
- Replicate Card Conjurer's full masking pipeline in Pillow
- For each zone (frame, pinline, border, title, type, rules):
  1. Load zone mask PNG
  2. Load artifact texture, clip to mask
  3. Load color texture, clip to mask
  4. Alpha-blend the two at zone-specific ratios
  5. Composite onto card canvas
- **Upside**: Pixel-accurate to real MTG frames
- **Downside**: Complex, ~6 compositing passes per frame, fragile

### Option C: Mask-Based Tinting (Middle Ground)
- Use `m15MaskFrame` to identify frame body region
- Apply a color tint (HSL shift or overlay blend) to just the artifact frame's body pixels
- Leave pinlines/border untouched (they're already handled by the frame PNG)
- **Upside**: Single-pass, uses existing masks
- **Downside**: May not perfectly match real colored artifact appearance

## Recommended Future Approach
Start with **Option A** (pre-baked blends) to get something shipping fast, then upgrade to **Option B** if we need pixel-accuracy later. The masks are already in our assets directory (`m15MaskFrame.png`, `m15MaskPinline.png`, etc.) so the upgrade path is clear.

## Frame Key Mapping Change Needed
In `colors.py`, `frame_key_for_identity()` currently returns color-based keys for all cards with color identity. For colored artifacts, it should return a compound key like `"AW"` (artifact + white). Detection: check if `"Artifact" in type_line` AND `len(color_identity) > 0`.

## Assets We Have
All in `assets/frames/m15/`:
- Frame PNGs: `m15FrameA`, `m15FrameW`, `m15FrameU`, `m15FrameB`, `m15FrameR`, `m15FrameG`, `m15FrameM`, `m15FrameV`, `m15FrameL`
- Mask PNGs: `m15MaskBorder`, `m15MaskFrame`, `m15MaskPinline`, `m15MaskPinlineSuper`, `m15MaskRules`, `m15MaskTitle`, `m15MaskType`
- PT boxes: `m15PTA`, `m15PTB`, `m15PTC`, `m15PTG`, `m15PTM`, `m15PTR`, `m15PTU`, `m15PTV`, `m15PTW`
- Crowns: per-color in `crowns/` subdirectory

## Source Repos
- Card Conjurer: `github.com/koherenc3/sbgames-cardconjurer` (archived, WotC C&D)
  - Frame assets: `img/frames/m15/regular/`
  - Rendering logic: `js/creator-23.js` (`drawFrames()`, `cardFrameProperties()`)
  - M15 frame registration: `data/scripts/versions/m15/version.js`
- wingedsheep: `github.com/wingedsheep/mtg-card-generator`
- Proxyshop: `github.com/Investigamer/Proxyshop` (Photoshop automation, has colored artifact templates in PSD format)

## Update (2026-06-09): two-color (multicolor) split frames — DONE via Option D
Two-color cards now render with a left-colourA / right-colourB split frame (was flat gold `M`).
Tracked: [Trello — Multicolor (two-color) card frames](https://trello.com/c/38VmZUZM).

**Option D (empirical median/percentile stacking) was used**, with two findings from the
fit check the user asked for:
- **Source = M15 *hybrid* cards, not gold `c:wu` cards.** Real `frame:2015 c:wu` cards are flat
  *gold* (e.g. Efreet Weaponmaster) — that IS our existing `m15FrameM`. The left/right split is the
  **hybrid** frame (e.g. Azorius Guildmage `{W/U}{W/U}`). So the median source is
  `frame:2015 is:hybrid id<=<pair> id>=<pair> -t:legendary -t:land …` (~25–35 unique-art cards/pair).
- **Scryfall format fits ours.** Scryfall PNGs are 745×1040; scaling to our 2010×2814 introduces only
  ~0.3% vertical squash, and M15 zone layout lines up with `layout.py` (verified by overlaying our
  zone boxes on real cards), so the stacked frame registers with our masks/text zones.
- **Percentile, not median.** Card text/watermarks are dark on a bright frame, so a per-pixel **p80**
  (toward the brighter value) rejects ghost text far better than the 50th-percentile median without
  washing the colour out. Even so, shared text ("Creature —", names) survives any percentile in the
  flat bar zones, so the title/type bars + bottom strip are rebuilt from a **left/right gradient blend
  of the two clean mono frames**, and the rules box from clean mono parchment; the stack keeps the
  body/border/pinline/colour + the split P/T box. Best of D (authentic split body) + A (clean bars).

**Implementation:** `backend/scripts/generate_two_color_frames.py` (offline, committed PNGs:
`m15Frame<PAIR>.png` + `m15PT<PAIR>.png`, 10 pairs, WUBRG order); `colors.frame_key_for_identity` /
`two_color_key`; `layout.frame_path` / `pt_box_path`; `card_renderer.determine_frame_key` /
`_load_frame` / `_load_pt_box` / `_load_legendary_crown` (the pre-existing `CROWN_PAIR_MAP` is now
wired to the committed `crowns/<PAIR>.png`). **Colored artifacts are still out of scope** (this card's
sibling) — `determine_frame_key` short-circuits artifacts to `A`. The shared masking/blend pipeline
this doc envisioned can reuse the mono-blend + zone-clip helpers in the generation script.
