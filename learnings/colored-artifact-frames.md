# Colored Artifact Frames — Research & Future Plan

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
