# Colored Artifact Frames — Research & Future Plan
> Tracked: [Trello — Colored artifact frames](https://trello.com/c/xiFbWsDH)

## Implementation status (2026-06-09): Option A shipped
Colored artifacts now render with a tinted frame instead of flat gray. **Shipped Option A** (alpha-blend `m15FrameA` with each mono color frame), chosen after rendering an A-vs-median comparison: A stays in our native 2010×2814 Card Conjurer geometry so nothing misaligns, while the Scryfall-median path (below) produced more authentic frame *colors* but ghosted the title/type/rules text (at n=35 those zones carry text on most cards, so the per-pixel median can't out-vote it) plus slight text-doubling from the Scryfall→our-geometry mismatch. Pieces:
- `colors.artifact_frame_key(color_identity)` → `A` (colorless) / `AW`..`AG` (mono) / `AM` (multicolor gold). `card_renderer.determine_frame_key` calls it for non-land artifacts (artifact *lands* stay land frames).
- `layout.frame_path`/`pt_box_path` resolve 2-letter `A?` keys → `m15Frame{AW..AG,AM}.png` / `m15PT*`; `_load_frame`/`_load_pt_box` fall back to `A` if a variant is missing.
- Variant PNGs built offline by `backend/scripts/colored_artifact_frames.py build --method blend`. The blend weight is **per-color** (`PER_COLOR_BLEND_ALPHA`, default `DEFAULT_BLEND_ALPHA` = 0.45) — see the AW re-tune note below. The same script's `--method median` is the **mature** percentile-stack pipeline (ported from `generate_two_color_frames.py`) + `compare` renders the A-vs-D comparison.
- Tests: `backend/tests/test_rendering/test_colored_artifact_frames.py`.

### Update (2026-06-10): AW re-tuned to 0.30 (per-color blend weights)
On the MLP set the user found **AW too weak** — 036 Canterlot Glimmer Automaton read as a plain white/cream frame (cover the type line and you'd guess mono-white creature). Root cause: white has the *least* chroma of any frame, so an even 0.45 blend mostly lightens the gray into flat cream instead of asserting white-cast metal. Fix: the builder gained a `PER_COLOR_BLEND_ALPHA` map (`blend_alpha_for(tint, override)`), and **AW dropped to 0.30** — a bigger share of the gray `m15FrameA` base so visible metal texture survives, while the warm cast on the title/type bars + parchment still signals white identity. The other four monos (U/R/G praised, B audited fine — its "inverse risk" of dark-on-dark didn't materialize at 0.45) + AM all stay at 0.45, audited via synthetic renders. CLI `--alpha` overrides every color at once. Only `m15FrameAW.png` + `m15PTAW.png` were regenerated (the rest rebuild byte-identically). Before/after reproduction: `python -m scripts.compare_artifact_aw` (mono-W OLD 0.45 vs NEW 0.30; mono-B control unchanged).

**Follow-up — RESOLVED (2026-06-09): Option D rejected for artifacts, Option A is final.** The pixel-accurate stack path was finished to maturity (registration + zone-blanking, the same machinery that shipped two-color) and empirically lost to the blend. See "Update (2026-06-09): Option D tried-and-rejected for colored artifacts" at the bottom of this doc.

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

**Approach — Option D (empirical frame extraction by per-pixel stacking).** Rather than compositing
frames from masks (Option B) or alpha-blending mono frames (Option A), *derive the real frame from
real cards*. The insight: a frame's pixels are identical across every card of a given variant, while
art and text are not — so if you align N Scryfall cards of one frame and take a per-pixel statistic,
the varying text/art is out-voted and the static frame survives (any given text pixel is a minority,
since most of a text box is empty on most cards). This is the only approach that cleanly yields the
gold-pinline + L/R-colour split (pre-baking from mono frames only approximates it) and it produces
static PNGs with zero render-time cost — best of A's simplicity + B's accuracy.

Two corrections came out of the fit check the user asked for; both revise the first-draft recipe and
are worth recording because the naive version is the obvious-but-wrong one:

- **Source = M15 *hybrid* cards, not gold `c:wu` cards.** The first-draft recipe queried `c:wu` —
  wrong: real `frame:2015 c:wu` cards are flat *gold* (e.g. Efreet Weaponmaster), which IS our
  existing `m15FrameM`. The left/right split is the **hybrid** frame (e.g. Azorius Guildmage
  `{W/U}{W/U}`). So the source query is `frame:2015 is:hybrid id<=<pair> id>=<pair> -t:legendary
  -t:land …` (~25–35 unique-art cards/pair), nonfoil.
- **Percentile (p80), not median.** The first draft said per-pixel median; in practice card
  text/watermarks are dark on a bright frame, so a per-pixel **p80** (biased toward the brighter
  value) rejects ghost text far better than the 50th-percentile median without washing the colour
  out. Even so, shared text ("Creature —", names) survives *any* percentile in the flat bar zones,
  so the title/type bars + bottom strip are rebuilt from a **left/right gradient blend of the two
  clean mono frames**, and the rules box from clean mono parchment; the stack keeps the
  body/border/pinline/colour + the split P/T box. Net: best of D (authentic split body) + A (clean bars).

**Why it registers with our renderer.** Scryfall PNGs are 745×1040; scaling to our 2010×2814
introduces only ~0.3% vertical squash, and the M15 zone layout lines up with `layout.py` (verified
by overlaying our zone boxes on real cards), so the stacked frame sits correctly under our
masks/text zones.

**General recipe (reusable for any empirical frame):**
1. Pull ~30–50 nonfoil Scryfall `png` images of one variant (uniform 745×1040 → near-free
   alignment); filter to a single consistent frame (`-is:promo -is:funny -border:borderless
   -is:showcase`, plus the per-variant selector above).
2. Per-pixel stack (p80 for the split, median for flat zones), then **cut the art window to
   transparent** (it stacks to averaged-art mush, and the renderer composites art separately
   anyway); same for the set-symbol + collector/artist regions (they stack toward background and we
   draw our own).
3. Zone-clip with the masks we already ship (`m15MaskFrame/Pinline/...`) for crisp edges, rebuild the
   flat text bars from the mono-blend, and save as real PNGs.

**Caveats (from the design notes):** imperfect alignment can blur sharp pinlines (fix:
phase-correlation auto-align); a >50%-shared-glyph pixel can smudge (fix: more cards, or use the
mode); there's no "empty art box" ground truth, but we don't need one since the art window is cut.

**Implementation:** `backend/scripts/generate_two_color_frames.py` (offline, committed PNGs:
`m15Frame<PAIR>.png`, 10 pairs, WUBRG order; bars come from the gold `m15FrameM`, and the P/T box
is the gold `m15PTM` via a `pt_box_path` remap — the real hybrid-card convention, no per-pair P/T
assets); `colors.frame_key_for_identity` /
`two_color_key`; `layout.frame_path` / `pt_box_path`; `card_renderer.determine_frame_key` /
`_load_frame` / `_load_pt_box` / `_load_legendary_crown` (the pre-existing `CROWN_PAIR_MAP` is now
wired to the committed `crowns/<PAIR>.png`).

**One pipeline, three payoffs.** The same empirical-stack + mono-blend + zone-clip machinery covers
**two-color splits**, **hybrid pinlines**, and **colored artifacts** — build it once and all three
fall out. Colored artifacts currently ship via the cheaper **Option A** blends (sibling card, see top
of this doc); `determine_frame_key` routes non-land artifacts through `artifact_frame_key` and
everything else through `frame_key_for_identity`, so the two features compose today. The artifact
upgrade path was then *taken* and *rejected* — see the next section.

## Update (2026-06-09): Option D tried-and-rejected for colored artifacts
The two-color split frames shipped via Option D, so the obvious next step was to move the colored
artifacts off the Option-A blend onto the same pixel-accurate stack. **It was built to maturity and
empirically lost to the blend. Option A stays final for artifacts.**

**What was built.** `colored_artifact_frames.py`'s `--method median` was upgraded from the naive
first-draft median (plain `np.median`, flat resize, no zone-blanking — the genuinely-awful version) to
the *mature* pipeline ported from `generate_two_color_frames.py`: p80 percentile stack of ~40 real M15
mono-artifact cards/color (`frame:2015 t:artifact c=<x> -t:land -t:vehicle … unique:art`; vehicles
excluded — their darker frame muddies the stack; `c=m` for `AM`), art window cut via `m15FrameA`'s
alpha, the title/type/rules/bottom **text bars rebuilt from the Option-A blend** (text-free,
artifact-tinted, in our exact geometry), the baked-in P/T box erased + a fresh P/T cropped from the
stack masked to `m15PTA`. Per-color real-card counts are plentiful (W195/U219/B179/R192/G86, M124), so
feasibility was never the issue.

**Why it lost (the real finding).** The two fears the card named — Scryfall→our-geometry registration
and text ghosting — both **dissolved**: zone-clipping to our masks snaps everything into place (no
doubling, pinlines line up), and the bar-rebuild kills the ghosts. The ~0.3% aspect squash
(745×1040 → 2010×2814) was a red herring. The actual killer is **signal-to-noise inversion vs.
two-color**: a hybrid two-color frame carries a *strong, consistent split-colour* signal, but a
colored artifact is a *subtle colour tint over a busy, highly-variable gray metallic texture*. The p80
stack can't out-vote the varying filigree/rivets/panel shapes, so the body comes out **blotchy**, and
the weak tint gets contaminated — green and black especially pick up a dirty blue-gray cast and barely
read as their colour. The blend, by contrast, is clean, uniform, and correctly tinted; it simply looks
more like a finished MTG frame. There is **no cheap fix**: median's only upside (authentic metal
texture) *is* the noise, and more cards / a higher percentile won't repair the green/black miscolour.

**Reproduce.** `python -m scripts.colored_artifact_frames compare` (renders blend vs mature-median into
`output/colored-artifact-comparison/`; downloads cache under `output/.cache/colored-artifact-frames/`).
The mature `--method median` implementation + the `compare` harness are kept committed so a future
revisit (e.g. Option B native-geometry zone masking, which sidesteps both the aspect mismatch and the
stacking noise) starts from a working baseline rather than the naive median. The committed
`m15Frame{AW..AG,AM}.png` assets are **unchanged** — still the Option-A blends.
