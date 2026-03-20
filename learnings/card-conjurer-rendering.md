# Card Conjurer Rendering Reference

Source: [koherenc3/sbgames-cardconjurer](https://github.com/koherenc3/sbgames-cardconjurer)
Archived local fork of Card Conjurer (shut down Nov 2022, WotC C&D). JavaScript/PHP web app using HTML5 Canvas. Same M15 frame template system our frame PNGs come from.

## Canvas & Coordinate System
- Base canvas: **1500x2100 pixels**
- All coordinates normalized to 0-1 ratios (resolution-agnostic)
- Multiple compositing canvases: `line`, `paragraph`, `text`, `frame`, `watermark`, `bottomInfo`
- Effects (outline, shadow) applied per-layer before compositing upward

## M15 Frame Coordinates (at 1500x2100 base)

| Element | x | y | size | Notes |
|---------|---|---|------|-------|
| Card Name | 126/1500 | 188/2100 | 80/2100 | font: belerenb |
| Type Line | 126/1500 | 1264/2100 | 68/2100 | font: belerenb |
| Rules Text | 135/1500 | 1370/2100 | 74/2100 | font: mplantin |
| P/T | 1191/1500 | 1954/2100 | 78/2100 | font: belerenbsc, center-aligned |
| Art Window | 115/1500 | 237/2100 | 1270x929 | |
| PT Box | 1136/1500 | 1858/2100 | 282x154 | |
| Mana Symbols | right-align from 1316/1500 | same as name | diameter=70 | spacing=78 between symbols |

## Font Sizing (as % of card height)
- Card name: 3.81% (80/2100)
- Type line: 3.24% (68/2100)
- Rules text: 3.52% (74/2100)
- P/T: 3.71% (78/2100)

## Mana Symbol Rendering
- **Inline symbol diameter**: `textSize * 0.78`
- **Vertical positioning**: `y = textSize - symbolDiameter * 0.95` (anchors near text baseline, 5% upward nudge)
- Hybrid mana symbols rendered at 1.2x scale (taller to fit split design)
- Multiple style packs available (standard, M21, outline, cartoony, Neon, etc.)
- Symbols loaded as pre-rendered PNG/SVG assets

## Text Wrapping Algorithm
- Word-by-word measurement using `measureText()`
- Line break when `currentWordWidth + currentLineWidth > maxWidth`
- Mana symbols treated as atomic (unbreakable) inline elements

## Shrink-to-Fit
- Decrements font size by **1px per iteration** when text overflows container
- Re-renders entire text object at each size attempt
- Minimum: 1px (practically no floor)

## Paragraph & Line Spacing
- **Paragraph breaks**: Add `textSize * 0.35` extra spacing
- Line height: implicit (textSize used directly as line advance, plus inter-line gap)

## Flavor Separator
- Width: **95% of text box width**
- Height: 0.2% of card height
- Position: 80% of textSize below the last oracle text line
- Drawn as an image asset (not a line) — has a `bar` and `whitebar` variant

## Vertical Text Centering
- Formula: `(containerHeight - totalTextHeight) / 2` — true vertical centering of text block within text box

## Text Outline/Shadow
- **Outline**: `strokeText()` first, then `fillText()` on top — crisp border without blur
- **Shadow**: Configurable X/Y offset (equal), no blur by default, black color
- Outline width configurable per text element (e.g., 0.003 = ~8-9px at 2814 height)

## Bold/Italic Toggling
- Inline `{i}` / `{/i}` tags toggle italic mid-line
- For mplantin font: appends 'i' to font extension (loads mplantini variant)
- For other fonts: prepends 'italic ' to CSS font style
- Bold similarly via font variant switching

## Frame Composition
- Layers drawn in reverse array order
- Uses Canvas `source-in` composite operation for masking (dynamic color swaps without separate frame assets per color)
- Legend crown overlays as separate layers
- PT box as separate overlay image positioned at fixed coordinates

## Collector Info Bar
- Position: y = 93.77% to 97.19% of card height
- Font: gothammedium at 0.0171 size, mplantin at 0.0143-0.0162
- White text with outline (width 0.003)
- Watermark at 0.4 opacity

## Reprint Flavor Text Gap (Discovered During Render Comparison)

Our reprints (Elvish Mystic, Murder) render without flavor text because the reprint selector
(`reprint_selector.py`) doesn't generate or carry over flavor text. Real printings of these
cards have flavor text that fills the text box and makes the card look complete.

**Fix**: When Haiku selects reprints, also ask it to generate set-appropriate flavor text.
The LLM already has the set config (theme, setting) in context. Add `flavor_text` to the
`assign_reprints` tool schema and populate `Card.flavor_text` in `convert_to_card()`.

This is a data pipeline fix, not a renderer fix — the renderer correctly renders whatever
flavor text the card has (or leaves the text box sparse if there is none).

## Flavor Text Overindexing (Phase 2C Discovery)

27/66 cards (41%) have 8+ lines of wrapped text at proper font sizes. 17 cards have
>8 lines and need flavor text dropped to render cleanly. This means the generation
pipeline gave flavor text to too many text-heavy cards.

**Root cause**: The skeleton/generation pipeline doesn't account for render-time text
density. Cards with long oracle text (activated abilities, reminder text) shouldn't
also get flavor text.

**Fix for future sets**:
- Skeleton should specify which slots get flavor text (~40-50% of cards, biased toward
  simple cards with short oracle text)
- Generation prompts should say "no flavor text" for cards with 3+ abilities or
  reminder text
- Render-time fallback: if >8 wrapped lines, drop flavor; if still >8, strip reminder text
