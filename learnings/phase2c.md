# Phase 2C Learnings — Card Renderer

## Summary

Built a card renderer that composites AI art + M15 frame templates + text into print-ready MTG card images. Three iterations of pixel-level comparison against real Scryfall cards drove the quality from "placeholder" to "passable at arm's length."

**Key files:**
- `backend/mtgai/rendering/card_renderer.py` — orchestrator
- `backend/mtgai/rendering/text_engine.py` — rich text layout engine
- `backend/mtgai/rendering/symbol_renderer.py` — SVG mana/set symbol rendering via pycairo
- `backend/mtgai/rendering/layout.py` — zone bounding boxes
- `backend/mtgai/rendering/fonts.py` — font loading with variable font weight support
- `backend/mtgai/rendering/colors.py` — MTG color schemes, rarity colors

## What Worked

### pycairo for SVG Symbol Rendering
cairosvg doesn't work on Windows (requires libcairo system library). But pycairo 1.29+ bundles its own Cairo DLL. We parse SVG `<path d="...">` attributes with the `svg.path` library and render them directly with Cairo's antialiased path engine. Quality is excellent — proper curves, fills, strokes.

### M15 Frame Templates from Card Conjurer
The Card Conjurer project (archived after WotC C&D) published M15 frame PNGs at 2010x2814 with transparent art windows. These are production-quality — the frame images ARE the card frame, we just composite art behind the transparent region and text on top.

### Iterative Pixel Comparison Process
Each iteration: fetch a real card from Scryfall → zoom to 200% → compare each element (name, mana, type, symbols, text, P/T, collector) → log differences → fix highest-impact first → re-render → verify. This drove rapid quality improvement across 3 iterations.

### Variable Font Weights
Cinzel (card names) and EB Garamond (keywords) both support variable font weights via OpenType variation axes. Loading at weight 700 gives proper bold rendering without needing separate bold font files. `PIL.ImageFont.truetype(font_path, size, layout_engine=RAQM)` with `font.set_variation_by_axes([700])` works cleanly.

### Dynamic Text Sizing
TextEngine tries the largest font size first, measures total height, and steps down until text fits the box. Combined with shrink-to-fit for name/type lines (where mana cost symbols consume horizontal space), this handles everything from vanilla creatures to text-heavy mythics.

## What Didn't Work

### cairosvg on Windows
cairosvg requires the `libcairo2` shared library which isn't available via pip on Windows. Multiple workarounds (GTK runtime, conda cairo, manual DLL) all failed or were fragile. The pycairo approach (bundled Cairo) was the winning path.

### Pillow's Built-in Text Rendering for Symbols
Pillow can draw text and basic shapes, but rendering SVG mana symbols (complex paths with fills, strokes, circles) requires a proper vector graphics engine. Using pycairo for symbols and Pillow for everything else was the right split.

### First-Pass Font Choices
We started with Cinzel/EB Garamond/Montserrat as open-source alternatives to the real MTG fonts (Beleren Bold/MPlantin). These are noticeably different — Cinzel has serifs where Beleren doesn't, EB Garamond's weight differs from MPlantin. We later downloaded Beleren and MPlantin for a potential font swap (files in `assets/fonts/beleren/` and `assets/fonts/mplantin/`) but haven't switched yet. This is the single biggest remaining visual improvement.

## Iteration History

### Iteration 1 (Initial Renderer)
- Basic compositing: art → frame → text overlay
- Placeholder colored circles for mana symbols
- Fixed font sizes (no dynamic sizing)
- No set symbol, no collector bar
- Result: "obviously a render, not a card"

### Iteration 2 (Critical Fixes)
- SVG mana symbol rendering via pycairo
- TextEngine with dynamic font sizing (85→55px range)
- ASD set symbol (descending vortex triangle) via pycairo
- P/T box text at proper size
- Collector info bar with white text
- Fixed escaped `\n` literals in 43/66 card oracle texts
- Result: "looks like an MTG card, but details are off"

### Iteration 3 (Major Polish)
- P/T box no longer overlaps flavor text (200px reservation in text box)
- Shrink-to-fit for type lines and card names (auto-sizes around mana cost width)
- Bold Cinzel (weight 700) for card names
- Bold EB Garamond for keywords, Montserrat Bold for P/T
- Vertical text centering in text box for sparse cards
- Mana symbol colors corrected (pale background + dark glyph, matching real MTG)
- Tap symbol from tap.svg (proper curved arrow)
- Result: "passable at arm's length, details visible under scrutiny"

## Discoveries

### Flavor Text Overindexing
27/66 cards (41%) have 8+ lines of wrapped text at proper font sizes. The generation pipeline gave flavor text to too many text-heavy cards. Fix for future sets: skeleton should specify which slots get flavor text, generation prompts should say "no flavor text" for cards with 3+ abilities.

### Reprint Flavor Text Gap
Reprints (Elvish Mystic, Murder) render without flavor text because the reprint selector doesn't generate it. The LLM already has set context — should also generate set-appropriate flavor text. This is tracked in memory as a feedback item.

### Card Conjurer Reference Data
Studied the archived Card Conjurer source (JavaScript/Canvas). Got exact coordinates for all M15 card zones, font sizing percentages, mana symbol diameter formulas, paragraph spacing, and flavor separator positioning. This data drove our layout.py bounding boxes and symbol sizing.

### wingedsheep/mtg-card-generator Reference
HTML/CSS renderer with Playwright screenshots — different approach (browser text engine vs our Pillow/pycairo), but documented exact font names (Beleren Bold, MPlantin, Relay Medium) and sizing. Confirmed our open-source font substitutes are the main visual gap.

## Remaining Work

### Iteration 4 (Fine-tuning)
- Switch to Beleren + MPlantin fonts (biggest single improvement)
- Mana symbol outline/border ring
- Symbol baseline alignment in inline text
- Text kerning comparison against real cards

### Iteration 5 (Edge Cases)
- Very long names + wide mana costs
- Cards with no flavor text
- Cards with 4+ abilities
- X in mana cost
- Basic land frames (full-art using lw/lu/lb/lr/lg assets)
- Custom card back design

## Performance

- Full 66-card render: ~25 seconds
- Per-card: ~380ms average
- Bottleneck: pycairo SVG symbol rasterization (~60% of per-card time)
- No parallelization yet (sequential, could easily thread)

## Cost

$0 — all rendering is local (Pillow + pycairo). No LLM calls in the rendering pipeline.
