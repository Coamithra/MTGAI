# Phase 2C: Card Renderer — Iterative Improvement Plan

## Context

We're in Phase 2C of the MTGAI project, building an automated card renderer that composites AI-generated art + M15 frame templates + text into print-ready MTG card images.

**Current state (Iteration 3 complete):**
- 66 cards rendered at 822x1122 (300 DPI) in ~25 seconds total
- M15 frame templates from Card Conjurer (2010x2814 RGBA PNGs with transparent art windows)
- Fonts: Cinzel Bold (names/types), EB Garamond (rules), Montserrat Bold (P/T, info)
- Mana symbols: SVG glyphs via pycairo + svg.path (proper MTG icons)
- Set symbol: ASD descending vortex triangle via pycairo, rarity-colored
- TextEngine: dynamic font sizing, keyword bolding, italic reminder text, vertical centering
- Renderer code: `backend/mtgai/rendering/` package

**Comparison page:** `output/sets/ASD/reports/render-comparison.html`

---

## Iteration Process

Each iteration follows this **pixel-level comparison loop**:

1. **Fetch reference** — Pull a real MTG card from Scryfall that matches the card type
2. **Zoom-compare** — Compare each visual element at 200%+ zoom, one element at a time:
   - [ ] **Card name** — font, weight, size, position, letter spacing
   - [ ] **Mana cost symbols** — colors, glyph style, size relative to name bar, spacing
   - [ ] **Type line** — font, size, em dash, position
   - [ ] **Set symbol** — shape, colors, size relative to type bar
   - [ ] **Rules text** — font, size, line spacing, paragraph spacing, fills text box naturally
   - [ ] **Inline mana symbols** — colors match name bar symbols, size relative to text, baseline alignment
   - [ ] **Keyword formatting** — bold keywords, italic reminder text in parens
   - [ ] **Flavor text** — italic, separator line, color (slightly lighter than rules)
   - [ ] **P/T box** — text size, centering, position, doesn't overlap flavor
   - [ ] **Collector bar** — text content, size, color, position
   - [ ] **Frame color/tint** — does our frame match the real color for this identity?
   - [ ] **Art window** — crop/position/scale correct?
   - [ ] **Overall spacing** — margins, padding, proportions feel right?
3. **Log differences** — Note specific pixel-level gaps (e.g., "our {G} is dark green bg + white glyph; real is pale sage bg + dark green glyph")
4. **Fix** — Address gaps in code, highest impact first
5. **Re-render** — `cd backend && python -m mtgai.rendering --set ASD --force`
6. **Verify** — Re-fetch reference, re-zoom, confirm fix didn't break other cards
7. **Repeat** — Until a non-MTG-player can't tell which is ours at normal viewing distance

### Scryfall reference cards

Use Scryfall's API to fetch high-res images:
```
# JSON (get image URLs)
https://api.scryfall.com/cards/named?fuzzy=<card_name>&format=json

# Direct image
https://api.scryfall.com/cards/named?fuzzy=<card_name>&format=image&version=normal
```

**Reference cards to compare against** (pick ones matching our card's characteristics):
- **Simple creature:** Elvish Mystic, Savannah Lions, Grizzly Bears
- **Complex creature:** Murderous Rider, Thalia Guardian of Thraben
- **Instant/Sorcery:** Negate, Shock, Murder, Lightning Helix
- **Enchantment:** Pacifism, Oblivion Ring
- **Artifact:** Mind Stone, Sol Ring
- **Land:** Any basic, plus Command Tower or Evolving Wilds
- **Multicolor:** Lightning Helix, Baleful Strix
- **Legendary:** Jace Beleren (planeswalker), Omnath Locus of Creation

### What to zoom into

When comparing, **zoom to 200%+ and compare each element in isolation**. It's easy to miss color mismatches, spacing issues, and font weight differences at normal viewing size. Key things to catch:

- **Color accuracy** — mana symbol circle colors (pale bg + dark glyph for W/U/R/G, dark bg + light glyph for B), frame tints
- **Proportions** — symbol size vs text height, padding ratios, text box fill percentage
- **Font rendering** — weight (bold vs regular), kerning, baseline alignment of inline symbols
- **Edge cases** — very long names with wide mana costs, cards with 4+ abilities, vanilla creatures with only flavor text, lands with mana abilities

---

## Completed Iterations

### Iteration 1 → 2: Critical Fixes ✅
- [x] Mana cost symbols — SVG glyph rendering via pycairo
- [x] Rules text sizing — TextEngine with dynamic font sizing (85→55px range)
- [x] Set symbol — ASD vortex triangle via pycairo
- [x] P/T box text — bumped to 48px print (117px native)
- [x] Collector info — 22px print, white text, vertically centered
- [x] Escaped newlines — normalize literal `\n` in 43/66 cards

### Iteration 2 → 3: Major + Polish Fixes ✅
- [x] P/T overlapping flavor text — reserve 200px in text box for PT overlay
- [x] Type line truncation — shrink-to-fit for long types
- [x] Card name shrink-to-fit — auto-size around mana cost width
- [x] Bold card names — Cinzel weight 700 via variable font axis
- [x] Bold keywords + P/T — EB Garamond and Montserrat at weight 700
- [x] Vertical text centering — center content in text box when sparse
- [x] Mana symbol colors — pale bg + dark glyph (matching real MTG)
- [x] Tap symbol — proper curved arrow from tap.svg
- [x] Comparison page — rebuilt with correct filenames

---

## Next Iterations

### Iteration 4: Fine-tuning
- [ ] **Mana symbol outline** — real symbols have a thin dark outline/border ring
- [ ] **Symbol baseline alignment** — inline symbols should sit on the text baseline, not float
- [ ] **Flavor text for reprints** — Elvish Mystic and Murder need flavor text (data fix)
- [ ] **Text kerning** — compare individual character spacing against real cards
- [ ] **Color matching** — compare frame tint when scaled (any color shift from LANCZOS downscale?)

### Iteration 5: Edge cases
- [ ] Cards with very long names + wide mana costs (e.g., 5-symbol costs)
- [ ] Cards with no flavor text — verify text box spacing
- [ ] Cards with many abilities (4+ paragraphs) — verify dynamic sizing
- [ ] X in mana cost
- [ ] Basic lands — consider full-art land frames (we have `lw.png`, `lu.png`, etc.)
- [ ] Card back — design and render custom card back

---

## Quick Reference

### Commands
```bash
# Render all cards
cd C:\Programming\MTGAI\backend && python -m mtgai.rendering --set ASD --force

# Render single card for testing
python -m mtgai.rendering --set ASD --card W-C-01 --force

# Open comparison page
start "" "C:\Programming\MTGAI\output\sets\ASD\reports\render-comparison.html"
```

### Key files to edit
- `backend/mtgai/rendering/card_renderer.py` — compositing order, zone rendering, shrink-to-fit
- `backend/mtgai/rendering/text_engine.py` — font sizes, text positioning, dynamic sizing, vertical centering
- `backend/mtgai/rendering/symbol_renderer.py` — mana/set symbol rendering, pycairo SVG backend
- `backend/mtgai/rendering/layout.py` — zone bounding boxes (if positions are wrong)
- `backend/mtgai/rendering/fonts.py` — font loading, weight selection, variable font axes
- `backend/mtgai/rendering/colors.py` — mana symbol colors, rarity colors, frame key mapping

### Real card references
- Scryfall JSON API: `https://api.scryfall.com/cards/named?fuzzy=<name>&format=json`
- Scryfall image: `https://api.scryfall.com/cards/named?fuzzy=<name>&format=image&version=large`
- Card Conjurer frames: `assets/frames/m15/m15Frame{W,U,B,R,G,M,A,L}.png`

---

## Definition of Done

The renderer is "done" when:
1. All 8 frame types render correctly (W/U/B/R/G/multi/artifact/land)
2. Card name + mana cost are properly sized and positioned
3. Type line + set symbol are properly sized and positioned
4. Rules text is readable at card size with correct inline mana symbols
5. Flavor text is italic with separator line
6. P/T box is readable with correct size
7. Collector info bar is present
8. **A non-MTG-player looking at our render and a real card side-by-side would say "those look the same"**
