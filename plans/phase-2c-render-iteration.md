# Phase 2C: Card Renderer — Iterative Improvement Plan

## Context

We're in Phase 2C of the MTGAI project, building an automated card renderer that composites AI-generated art + M15 frame templates + text into print-ready MTG card images. The first render pass (Iteration 1) produces recognizable cards but has significant layout and sizing issues compared to real MTG cards.

**Current state:**
- 66 cards rendered at 822x1122 (300 DPI) in ~25 seconds total
- M15 frame templates from Card Conjurer (2010x2814 RGBA PNGs with transparent art windows)
- Fonts: Cinzel (names), EB Garamond (rules), Montserrat (P/T, info)
- Mana symbols: Pillow fallback circles (cairosvg unavailable on Windows)
- Renderer code: `backend/mtgai/rendering/` package (layout, colors, fonts, symbols, text_engine, card_renderer)

**Comparison page:** `output/sets/ASD/reports/render-comparison.html`

---

## Iteration Process

Each iteration follows this loop:

1. **Compare** — Open comparison page, look at our renders vs real MTG cards side-by-side
2. **Identify** — List specific visual differences, categorized by severity (critical/major/minor)
3. **Fix** — Address top issues in code (highest severity first)
4. **Re-render** — `cd backend && python -m mtgai.rendering --set ASD --force`
5. **Review** — Refresh comparison page, verify fixes, identify remaining issues
6. **Repeat** — Until renders are near-indistinguishable from real cards at normal viewing distance

### How to compare against real cards

Use Scryfall's API to fetch high-res images of comparable real MTG cards:
```
https://api.scryfall.com/cards/named?fuzzy=<card_name>&format=image&version=normal
```

Good reference cards (common real MTG cards with similar characteristics):
- **White creature:** Traveling Minister, Savannah Lions, Elite Vanguard
- **Blue uncommon:** Negate, Essence Scatter
- **Black rare:** Murderous Rider, Doom Blade
- **Red common:** Shock, Goblin Arsonist
- **Green creature:** Elvish Mystic, Llanowar Elves
- **Multicolor:** Lightning Helix, Baleful Strix
- **Artifact:** Mind Stone, Sol Ring
- **Land:** Any basic land (Plains, Island, etc.)

---

## Iteration 1 → 2: Critical Fixes

These are the issues identified from the first render pass. Fix ALL critical issues before moving to major.

### CRITICAL: Mana cost symbols missing
- **What's wrong:** No mana symbols appear in the top-right of the name bar
- **Root cause:** Likely `render_mana_cost()` in text_engine.py — either not being called, symbols rendering off-screen, or mana_cost field is None/empty
- **Debug:** Add logging to `render_mana_cost()`, print the mana_cost value, check symbol positions
- **Fix:** Ensure symbols render right-aligned within the name bar, verify card.mana_cost is populated
- **Verify:** Rendered card should show colored circles like {1}{W} for a 1W cost

### CRITICAL: Rules text too small / wrong position
- **What's wrong:** Oracle text is barely readable, much smaller than real MTG cards
- **Root cause:** Font size calculation may be off. At native 2010x2814, body text should be ~42-50px (which scales to ~17-20px at 822x1122). Check `find_best_font_size()` range — it may start too small.
- **Debug:** Log the chosen font size, compare to expected. Render with a fixed known-good size to isolate.
- **Fix:** Adjust font size range in `find_best_font_size()`. For reference, real MTG rules text is ~8.5pt at print size (63x88mm) which is ~35px at 300 DPI → ~85px at native 2010x2814 resolution
- **Verify:** Rules text should be clearly readable at card size, filling most of the text box

### CRITICAL: Set symbol missing
- **What's wrong:** No set symbol on the right side of the type bar
- **Root cause:** `render_set_symbol()` may not be called, or symbol renders off-screen, or SVG loading fails silently
- **Debug:** Check if `render_set_symbol()` is called in card_renderer.py, add logging
- **Fix:** Ensure set symbol renders right-aligned in type bar at ~40px height (native), colored by rarity

## Iteration 2 → 3: Major Fixes

### MAJOR: P/T box text too small
- **What's wrong:** Power/toughness numbers are barely visible
- **Root cause:** Font size for P/T rendering is too small relative to the P/T box overlay
- **Fix:** P/T text should be large and bold — at native res the P/T box is 377x206, so text should be ~100-120px font size, centered
- **Verify:** P/T should be immediately readable (e.g., "2/3" fills most of the box)

### MAJOR: Collector info missing
- **What's wrong:** Bottom bar text (collector number, set code, artist) not visible
- **Root cause:** Text may be rendering in wrong color (dark on dark), or position is off
- **Fix:** Collector info should be light gray or white text on the dark bottom strip, ~16-20px at native res

### MAJOR: Text box spacing
- **What's wrong:** Text doesn't fill the text box naturally — too much empty space or cramped
- **Fix:** Adjust padding, line spacing, paragraph spacing. Real MTG cards have ~4-6px line spacing and ~8-12px paragraph spacing (at print size). Scale accordingly.

## Iteration 3 → 4: Polish

### MINOR: Font weight/style matching
- Compare font weights to real cards — Cinzel for names may need to be bolder, EB Garamond may need specific weight selection
- **How:** Place our render next to a Scryfall image at same size, compare letter thickness

### MINOR: Mana symbol quality
- Pillow circle fallbacks look OK but not great. Options:
  1. Pre-rasterize SVGs using an external tool (Inkscape CLI, or a one-time batch script)
  2. Find pre-rasterized mana symbol PNGs online (andrewgioia/mana has PNG exports)
  3. Accept circle fallbacks for dev set

### MINOR: Flavor text separator
- Should be a thin centered line between oracle and flavor text
- Real cards use a small ornate line ~60% of text box width

### MINOR: Keyword bolding
- Keywords like "Flying" and "Salvage 2" should be bolded in rules text
- Verify the keyword detection regex catches all keywords in the set

### MINOR: Reminder text italics
- Text in parentheses (20+ chars) should be italic
- Verify rendering matches real cards

## Iteration 4+: Fine-tuning

- **Text kerning** — compare individual character spacing
- **Color matching** — compare frame tint when scaled (any color shift from LANCZOS downscale?)
- **Edge cases** — cards with very long names, no flavor text, many abilities, X in mana cost
- **Basic lands** — consider full-art land frames (we have `lw.png`, `lu.png`, etc.)
- **Card back** — design and render custom card back

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
- `backend/mtgai/rendering/text_engine.py` — font sizes, text positioning, symbol rendering
- `backend/mtgai/rendering/card_renderer.py` — compositing order, zone usage, P/T overlay
- `backend/mtgai/rendering/layout.py` — zone bounding boxes (if positions are wrong)
- `backend/mtgai/rendering/symbol_renderer.py` — mana/set symbol appearance
- `backend/mtgai/rendering/fonts.py` — font loading, weight selection

### Real card references
- Scryfall image API: `https://api.scryfall.com/cards/named?fuzzy=<name>&format=image&version=large`
- Scryfall art crop: add `&version=art_crop`
- Card Conjurer frame reference: `assets/frames/m15/m15Frame{W,U,B,R,G,M,A,L}.png`

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
8. A non-MTG-player looking at our render and a real card side-by-side would say "those look the same"
