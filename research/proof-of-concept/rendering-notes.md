# Card Rendering Prototype — Findings & Recommendations

## Prototype Summary

**Script:** `research/proof-of-concept/render_prototype.py`
**Output:** `research/proof-of-concept/rendered-thornwood-prototype.png`
**Canvas:** 822 x 1122 px (MPC spec, 300 DPI with 3mm bleed)
**Render time:** ~16ms per card (single-threaded, no I/O bottleneck)

---

## What Pillow Can Do Well

1. **Basic card layout** — Drawing rectangles, rounded rectangles, lines, and solid fills is fast and straightforward. The `ImageDraw.rounded_rectangle()` method handles frame elements cleanly.

2. **Text rendering at 300 DPI** — TrueType font rendering with anti-aliasing looks crisp. At 300 DPI, a 28px font (≈6.7pt at print size) is readable for card names. A 21px font (≈5pt) works for rules text — comparable to actual MTG card body text.

3. **Bold and italic variants** — Pillow supports loading separate `.ttf` files for bold, italic, and bold-italic. We can use Georgia Bold for keywords and Georgia Italic for flavor text. This works for basic rich text.

4. **Word wrapping** — Using Python's `textwrap` module combined with `font.getlength()` for pixel measurement, we can implement reliable word wrapping. The prototype confirms all lines fit within the text box bounds.

5. **Gradient rendering** — Simple gradients (for art placeholders or frame effects) work via per-row line drawing, though this is slow compared to numpy-based approaches.

6. **Image compositing** — `Image.paste()` and `Image.alpha_composite()` handle layering art onto frames. This is Pillow's core strength.

7. **DPI metadata** — `img.save(path, dpi=(300, 300))` correctly sets DPI metadata for print services.

8. **Performance** — 16ms per card render means the full set (280 cards) could render in under 5 seconds. Even with art loading and symbol compositing, we'd expect <1 minute for the full set.

## What Pillow Cannot Do (or Does Poorly)

1. **Inline mixed content** — Pillow has no concept of a "text run" with mixed fonts, images, or styles in a single paragraph. Rendering rules text like `"{T}: Add {G}"` with inline mana symbols requires a custom layout engine that:
   - Parses `{symbol}` tokens
   - Measures each text/symbol run's width
   - Handles word-wrap across mixed runs
   - Manually positions each element pixel-by-pixel

   **Effort estimate:** 200-400 lines of custom layout code. Doable but tedious.

2. **No built-in rich text** — There's no way to render "bold this word, italic that word" in a single `draw.text()` call. Each style change requires a separate call with manual x-offset tracking.

3. **No kerning control** — Pillow relies on the font's built-in kerning tables. We can't adjust letter-spacing or do fine typographic control. For most card text this is fine, but mana costs like `{2}{G}{G}` would benefit from tighter spacing when rendered as actual symbols.

4. **No SVG rendering** — Mana symbols from the `andrewgioia/mana` repo are SVGs. Pillow cannot render SVGs natively. Options:
   - Pre-rasterize SVGs to PNGs at multiple sizes (simplest)
   - Use CairoSVG to convert SVG→PNG at render time
   - Use Pycairo to render SVGs directly onto the canvas

5. **No text-along-path** — Not needed for standard MTG cards, but would matter for special frames.

6. **Limited gradient support** — No built-in gradient fills. Must draw pixel-by-pixel or use numpy arrays. Frame templates with gradient overlays would need to be pre-made images rather than procedurally generated.

## Text Rendering Quality Assessment

| Aspect | Rating | Notes |
|--------|--------|-------|
| **Anti-aliasing** | Good | TrueType rendering is smooth at 300 DPI |
| **Sharpness** | Good | Comparable to print-quality output |
| **Bold weight** | Good | Separate bold font file renders correctly |
| **Italic quality** | Good | Georgia Italic is clean and readable |
| **Small text (14px / 3.4pt)** | Acceptable | Collector info is readable but tight |
| **Word spacing** | Good | Standard word spacing from the font |
| **Line spacing** | Manual | Must calculate manually; no `line-height` concept |
| **Overall print readiness** | Good | Would be readable on a printed card |

### Font Size Reference (at 300 DPI)

| Pixel Size | Point Equivalent | Use Case |
|------------|-----------------|----------|
| 14px | 3.4pt | Collector info, fine print |
| 19px | 4.6pt | Flavor text |
| 21px | 5.0pt | Rules text body |
| 22px | 5.3pt | Type line, mana cost |
| 28px | 6.7pt | Card name |
| 30px | 7.2pt | Power/Toughness |
| 36px | 8.6pt | Placeholder text |

## Layout Measurements Used

All positions in pixels at 300 DPI, relative to the 822x1122 canvas:

| Element | Position (x, y) | Size (w x h) | Notes |
|---------|-----------------|---------------|-------|
| **Bleed area** | Full canvas | 822 x 1122 | 36px (3mm) bleed on each side |
| **Card border** | (36, 36) | 750 x 1050 | 12px visible border inside bleed |
| **Content area** | (48, 48) | 726 x 1026 | Inside border |
| **Name bar** | (54, 54) | 714 x 50 | Top of content area |
| **Art box** | (66, 108) | 690 x 478 | Below name bar, 18px inset |
| **Type bar** | (54, 592) | 714 x 50 | Below art box |
| **Text box** | (66, 648) | 690 x 356 | Below type bar |
| **P/T box** | (674, 1000) | 90 x 46 | Bottom-right of text area |
| **Collector bar** | (54, 1030) | 714 x 38 | Bottom of card |

---

## Do We Need Pycairo?

### Arguments FOR Pycairo

1. **SVG symbol rendering** — Native SVG support means mana symbols render at any size without pre-rasterization. Cleaner pipeline.
2. **Pango text layout** — Pycairo + Pango provides a proper rich-text engine with:
   - Mixed bold/italic in a single text block
   - Proper Unicode handling and complex scripts
   - Built-in line breaking with hyphenation
   - Inline image support (with some effort)
3. **Vector frame templates** — Could define frames as SVG/vector paths for resolution independence.
4. **Better anti-aliasing** — Cairo uses sub-pixel rendering that can be slightly smoother than Pillow's.

### Arguments AGAINST Pycairo

1. **Added dependency** — Pycairo requires the Cairo C library. On Windows, this means either `pip install pycairo` (which bundles Cairo) or manual installation. Adds build complexity.
2. **Learning curve** — Cairo's API is quite different from Pillow. The team would need to learn a new drawing model (paths, surfaces, contexts).
3. **Pillow is sufficient** — For the prototype, Pillow handles all rendering needs. The main gap (inline symbols) can be solved with ~300 lines of custom code.
4. **Performance is fine** — 16ms per card with Pillow. Cairo won't meaningfully improve this.
5. **Mixing libraries** — Art compositing would still use Pillow (loading PNGs, resizing). We'd be mixing Pillow + Cairo, which adds complexity.

### Compromise: Pillow + CairoSVG

CairoSVG is a pure-Python SVG→PNG converter (uses Cairo under the hood but doesn't require the full Pycairo binding). This gives us:
- SVG→PNG conversion for mana symbols
- No need to learn the Cairo drawing API
- Pillow stays as the primary rendering engine
- `pip install cairosvg` — simpler than full Pycairo

---

## Architecture Recommendation

### Recommended: Pillow-only (with optional CairoSVG for symbols)

**Rationale:**

1. **Pillow is sufficient for all card rendering needs.** The prototype proves this. Text rendering quality at 300 DPI is good, layout is straightforward, and performance is excellent (16ms/card).

2. **The inline symbol problem is solvable.** A custom `RichTextRenderer` class (~300 lines) can parse `{symbol}` tokens, measure runs, and composite text + symbol PNGs with proper word-wrap. This is the main engineering effort but it's well-scoped.

3. **Pre-rasterized symbol PNGs eliminate the SVG dependency entirely.** If we pre-render all mana symbols from SVG to PNG at 3-4 standard sizes (16, 20, 24, 28px), Pillow can composite them directly. CairoSVG is only needed if we want on-the-fly SVG rendering.

4. **Frame templates should be pre-made PNGs, not procedural.** Rather than drawing frame elements procedurally (as in the prototype), the production renderer should load pre-designed frame template PNGs and composite art + text onto them. This gives much better visual quality and is easier to iterate on.

### Proposed Production Architecture

```
CardRenderer
├── FrameLoader          — loads frame template PNGs by color/type
├── ArtCompositor        — resizes and positions art in the art box
├── RichTextRenderer     — custom text layout engine
│   ├── parse_mtg_text() — splits text into runs (text, symbols, formatting)
│   ├── measure_runs()   — calculates pixel widths of each run
│   ├── wrap_lines()     — word-wraps mixed content to fit box width
│   └── render()         — draws text + symbols onto the image
├── SymbolCache          — loads and caches pre-rasterized mana symbol PNGs
├── FontManager          — loads and caches fonts by role and size
└── PrintExporter        — adds bleed, sets DPI metadata, optional CMYK conversion
```

### Migration Path

1. **Phase 0B (now):** Pillow prototype validates layout and text rendering ✓
2. **Phase 2C (renderer):** Build `RichTextRenderer` with inline symbol support using Pillow
3. **If text quality is insufficient:** Add Pycairo as a text rendering backend (swap-in, not rewrite)
4. **Frame templates:** Design in a graphics program, export as PNGs, load at render time

### Performance Estimate for Full Pipeline

| Step | Time per Card | Notes |
|------|--------------|-------|
| Load frame template | ~2ms | Cached after first load |
| Load + resize art | ~10ms | From disk, resize to art box |
| Composite art onto frame | ~2ms | PIL Image.paste() |
| Render all text elements | ~5ms | Including word-wrap calculation |
| Composite symbols | ~3ms | Pre-loaded, cached PNGs |
| Save to disk | ~15ms | PNG compression |
| **Total** | **~37ms** | **≈27 cards/second** |

For 280 cards: ~10 seconds. For 1100+ cards (full playset): ~41 seconds.

---

## Open Questions

1. **Font selection** — The prototype uses system fonts (Arial Bold, Georgia). Final production should use fonts closer to MTG's style (see Phase 0B Section 4 for candidates). This is a separate task.

2. **Frame template source** — Need to decide: create frame PNGs from scratch, extract from Proxyshop templates, or generate procedurally? Recommendation: design simple but clean frames in a graphics program.

3. **Dynamic font sizing** — Some MTG cards reduce body text font size when there's too much text. The production renderer needs a `fit_text_to_box()` function that tries progressively smaller font sizes.

4. **CMYK conversion** — The prototype outputs sRGB. MPC accepts sRGB, but if we use another print service, we may need ICC profile-based CMYK conversion. Pillow can do basic conversion; for proper ICC, we'd need `Pillow` with `littlecms` support (usually bundled).

5. **Card-specific layouts** — Planeswalkers, sagas, split cards, and double-faced cards all need different layouts. The prototype only covers standard creature cards. Each variant needs its own layout specification.
