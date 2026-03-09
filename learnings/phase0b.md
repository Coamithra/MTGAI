# Phase 0B: Technical Research — Learnings

## What Worked

### Pillow Rendering (7ms/card)
- Pillow is sufficient for MTG card rendering at 300 DPI. No need for Pycairo.
- Variable TTF fonts (Cinzel, EB Garamond, Montserrat) load and render correctly with `ImageFont.truetype()`.
- Word wrapping with `textwrap` + `font.getlength()` is reliable for rules text.
- Render time of 7ms/card means the full 280-card set renders in ~2 seconds.

### Font Selection
- **Cinzel** for card names gives a decorative serif look that feels right for a fantasy card game. The small-caps style is distinctive.
- **EB Garamond** for rules/flavor text is an excellent MPlantin substitute — clean, readable, proper italic support.
- **Montserrat** for P/T and collector info provides a clean geometric sans that's close to Gotham.
- All three are SIL OFL licensed — no restrictions on embedding in rendered images.

### Mana Symbol Approach
- Pre-rasterized colored circles with letter labels work as a functional fallback when CairoSVG isn't installed.
- SVG assets from `andrewgioia/mana` are comprehensive (40+ symbols).
- Symbol cache avoids redundant rendering — important for batch processing.

### Print Spec Lock-Down
- MPC's 822x1122px / 300 DPI / sRGB / PNG spec is well-documented and stable.
- S33 card stock is the community consensus for MTG-feel proxies.
- All specs stored in `config/print-specs.json` — single source of truth.

## What Didn't Work / Surprises

### Variable Font Weight Axis
- Pillow loads variable TTF fonts but doesn't expose weight axis selection via `truetype()`. The default weight (400/Regular) is used. For bold text, we use a separate bold font file or accept the regular weight.
- **Workaround**: EB Garamond bold uses the same variable font at default weight (acceptable for a prototype). In production (Phase 2C), consider using `fontTools` to instance specific weights, or just use static weight font files.

### SVG Rendering Gap
- Pillow cannot render SVGs natively. The mana SVGs from the Mana repo need conversion.
- CairoSVG is the cleanest solution (`pip install cairosvg`) but adds a native dependency (libcairo).
- The Pillow-only fallback (drawing colored circles) is functional but doesn't use the actual SVG artwork.
- **Decision**: For Phase 2C, install CairoSVG to use the real SVG assets. For now, the fallback is fine.

### Image Generation Not Hands-On Tested
- The 0B-img decision is research-based, not validated with actual GPU runs.
- Flux.1-dev is the recommended primary model, but VRAM fit on 8GB with quantization is unconfirmed.
- **Risk**: If NF4/GGUF quantized Flux produces visibly degraded output, we'll need to fall back to SDXL (which fits 8GB at FP16) or use Flux via API.
- Mitigation: Phase 2A includes a validation checklist for hands-on testing.

### Hybrid Mana Symbols Not Yet Handled
- The Mana repo provides hybrid symbols (W/U, B/R, etc.) via CSS class layering, not as individual SVGs.
- Rendering hybrid mana requires compositing: base split-color circle + symbol overlays.
- **Defer to Phase 2C** — not needed for the prototype card.

## Key Parameters for Downstream Phases

```
# Rendering
render_engine = "pillow"
canvas_width = 822
canvas_height = 1122
dpi = 300
render_time_per_card_ms = 7

# Fonts (variable TTF)
font_name = "assets/fonts/cinzel/Cinzel-Variable.ttf"          # 28px card name
font_body = "assets/fonts/eb-garamond/EBGaramond-Variable.ttf"  # 21px rules text
font_italic = "assets/fonts/eb-garamond/EBGaramond-Italic-Variable.ttf"  # 19px flavor
font_info = "assets/fonts/montserrat/Montserrat-Variable.ttf"   # 14px collector, 30px P/T

# Image generation (research-based, validate in Phase 2A)
image_gen_primary = "flux.1-dev"  # Local via ComfyUI, NF4/GGUF quantized
image_gen_fallback = "flux-api"   # fal.ai, ~$0.005/image
image_gen_secondary = "midjourney" # Manual, for hero cards only
upscaler = "real-esrgan-x4plus"

# Print
print_service = "makeplayingcards"
card_stock = "S33"
file_format = "png"
color_space = "sRGB"
```

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Rendering engine | Pillow | 7ms/card, sufficient quality, no native deps |
| Card name font | Cinzel (OFL) | Decorative serif, closest OFL match to Beleren |
| Body text font | EB Garamond (OFL) | Best OFL match to MPlantin, has italic |
| Info font | Montserrat (OFL) | Geometric sans, close to Gotham |
| Mana symbols | SVG (andrewgioia/mana) + Pillow fallback | MIT license, comprehensive |
| Image gen model | Flux.1-dev (local, quantized) | Best prompt adherence, $0 cost |
| Image gen fallback | Flux via API (fal.ai) | Same quality, no VRAM limits, <$5/set |
| Print service | MPC (S33 stock) | Community standard, no EU customs, ~$95/draft set |
| Print spec | 822x1122px, 300 DPI, sRGB, PNG | MPC standard |

## Risks to Watch

1. **Flux on 8GB VRAM**: Quantized model quality is unconfirmed. Test in Phase 2A.
2. **Frame templates**: Need to design actual PNG frames (currently procedural rectangles). Significant art/design effort.
3. **Dynamic font sizing**: Not yet implemented. Text-heavy cards may overflow text box.
4. **CairoSVG dependency**: Native library may be tricky on Windows. Test installation in Phase 2C.
