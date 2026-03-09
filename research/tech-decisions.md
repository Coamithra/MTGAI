# Technical Decisions — Phase 0B

## Image Generation

> **Assessment basis**: Research-based scoring from community benchmarks, published comparisons,
> and documented model capabilities as of early 2026. Hands-on validation with our actual prompt
> templates is deferred to Phase 2A. Scores may be revised after that testing.

### Comparison Table

| Criterion (Weight) | GPT-4o Image Gen | Midjourney v6.1 | SDXL 1.0 (Local) | Flux.1-dev (Local) | Flux via API |
|---------------------|:-:|:-:|:-:|:-:|:-:|
| Fantasy art quality (30%) | 4 | 5 | 3 | 4 | 4 |
| Style consistency (25%) | 3 | 5 | 4 | 4 | 4 |
| Prompt adherence (15%) | 4 | 3 | 3 | 5 | 5 |
| Aspect ratio control (10%) | 3 | 4 | 5 | 5 | 5 |
| Resolution / upscale (10%) | 3 | 4 | 4 | 4 | 4 |
| Speed & throughput (5%) | 2 | 3 | 4 | 3 | 5 |
| Artifact frequency (5%) | 4 | 4 | 2 | 4 | 4 |
| **Weighted Score** | **3.45** | **4.35** | **3.55** | **4.20** | **4.30** |

### Score Rationale

- **GPT-4o Image Gen**: Strong prompt adherence and low artifacts, but output has a recognizable
  "AI polish" that reduces fantasy art depth. Limited throughput (rate limits, token cost ~$0.02-0.08
  per image). No batch mode. Style consistency is difficult to control across generations — no
  negative prompts, no seed control, no LoRA ecosystem.
- **Midjourney v6.1**: Best-in-class fantasy and painterly aesthetics. Excellent style consistency
  via `--sref` (style reference) and `--cref` (character reference) parameters. Weaker on literal
  prompt adherence — tends to "interpret" rather than follow instructions exactly. No official API;
  requires Discord bot interaction or third-party wrappers, which makes batch automation fragile.
  Cost: ~$30/month for Standard plan (~200 fast generations).
- **SDXL 1.0 (Local)**: Mature ecosystem with thousands of LoRAs, ControlNet support, and the
  largest community knowledge base. Native 1024x1024 output. Fantasy art quality is adequate but
  noticeably below Flux and Midjourney without heavy prompt engineering and LoRA stacking. Higher
  artifact rate (hands, faces, fine detail) than newer models. Runs comfortably on 8GB VRAM at
  FP16. ~4-6s/image at 25 steps on a mid-range GPU.
- **Flux.1-dev (Local)**: Best open-source prompt adherence — follows complex, multi-element
  prompts far more faithfully than SDXL or Midjourney. Strong aesthetic quality approaching
  Midjourney for many styles. Native 1024x1024 with good aspect ratio flexibility. Requires
  quantization on 8GB VRAM (see VRAM section below). LoRA ecosystem is growing rapidly but still
  smaller than SDXL's. ~8-15s/image on 8GB depending on quantization level.
- **Flux via API (Replicate/fal.ai)**: Same model quality as local Flux.1-dev but runs on cloud
  GPUs — no VRAM constraints, faster generation (~3-5s/image). Cost: ~$0.003-0.01/image on fal.ai
  or Replicate. For 280 cards at 3 attempts each: ~$2.50-8.40 total. Useful fallback when local
  generation hits VRAM limits or for parallel batch runs.

### Recommendation

**Primary: Flux.1-dev (Local) via ComfyUI**

Flux.1-dev offers the best balance of prompt adherence, image quality, and zero marginal cost for
our use case. Prompt adherence is the highest-priority capability for card art generation: each of
280+ cards has a unique scene description, and the model must faithfully render specific creatures,
environments, color palettes, and compositions without heavy manual intervention.

ComfyUI is the recommended local interface:
- Node-based workflow allows saving and reproducing exact generation pipelines
- Native support for Flux.1-dev, SDXL, and most diffusion models
- Built-in LoRA loading, ControlNet, and upscaling nodes
- Workflow JSON files can be version-controlled and shared
- Active community with frequent updates

**Fallback: Flux via API (fal.ai)**

For prompts where the local 8GB VRAM quantized model produces unacceptable results, or when batch
speed is critical, use fal.ai's Flux.1-dev endpoint. At ~$0.005/image, generating the entire set
with 3 attempts per card would cost under $5. This is also useful for A/B testing: compare local
quantized output against full-precision cloud output to gauge quality loss.

**Secondary fallback: Midjourney v6.1**

If specific cards require a painterly fantasy aesthetic that Flux struggles with (e.g., sweeping
landscapes, dramatic lighting, mythological creatures), Midjourney is the quality ceiling. Use
sparingly for hero cards (mythic rares, key story cards) where art quality matters most. Manual
process — not suitable for full batch generation.

### Style Consistency Workflow

Maintaining a cohesive visual identity across 280+ cards is the hardest challenge. Strategy:

1. **Master style prompt prefix**: Define a 30-50 word style block prepended to every art prompt.
   Example structure: `"[medium], [lighting style], [color palette], [artistic influence], [mood]"`.
   This anchors all images to a shared aesthetic.
2. **Per-rarity style tiers**: Slightly vary the style prefix by rarity (commons get simpler
   compositions, mythics get more dramatic lighting and detail).
3. **Color identity alignment**: Prompts include color-aligned palette cues (e.g., white cards lean
   warm/bright, black cards lean dark/desaturated). Encode these as part of the card-to-prompt
   pipeline.
4. **Flux LoRA (if available)**: If a suitable fantasy art LoRA exists for Flux.1-dev, use it to
   further anchor style. Alternatively, train a custom LoRA on 20-30 reference images of the
   desired style (requires ~1hr on cloud GPU). Evaluate this in Phase 2A.
5. **Seed + prompt versioning**: Log every generation with its seed, prompt, model version, and
   sampler settings in the card JSON metadata. This enables reproducibility and iterative
   refinement.
6. **Batch review checkpoints**: After every 20-30 cards, do a visual consistency review. Adjust
   the style prefix if drift is detected.

### Upscaling Pipeline

Card art is generated at 1024x1024 (or 832x1216 for portrait aspect) and must be placed into an
art box of 690x478px at 300 DPI. The generated resolution is sufficient for the art box without
upscaling in most cases (1024px wide > 690px needed). However, if higher fidelity is desired:

- **Primary upscaler**: Real-ESRGAN x4plus (or x2) — fast, artifact-free, well-suited for
  illustrated/painted content. Available as a ComfyUI node (`comfyui-reactor` or standalone).
- **Alternative**: SwinIR or 4x-UltraSharp for sharper detail preservation.
- **Workflow**: Generate at native resolution -> crop to target aspect ratio -> upscale if
  needed -> resize to final art box dimensions (690x478) with Lanczos resampling.
- **Do not upscale after compositing** — upscale the art before placing it in the card frame to
  avoid amplifying compression artifacts from the template layers.

### VRAM Considerations (8GB GPU)

Flux.1-dev's full BF16 weights require ~24GB VRAM, far exceeding our 8GB budget. Options:

| Quantization | VRAM Usage | Quality Impact | Speed Impact |
|--------------|-----------|----------------|-------------|
| FP8 (8-bit float) | ~12-13GB | Minimal — nearly indistinguishable from BF16 | ~10% slower |
| NF4 (4-bit normal float) | ~6-8GB | Slight softening of fine details, occasional color shift | ~20-30% slower |
| GGUF Q4/Q5 | ~5-7GB | Comparable to NF4, depends on quant variant | ~20-30% slower |

**Recommended approach for 8GB**:
- Use **NF4 quantization** (available via ComfyUI's built-in GGUF loader or `bitsandbytes` NF4).
  This fits comfortably in 8GB with room for the VAE and text encoders.
- Alternatively, use **GGUF Q5_K_M** format which offers a good quality/size tradeoff and has
  first-class ComfyUI support via the `ComfyUI-GGUF` custom node.
- The T5-XXL text encoder (used by Flux) is itself ~9GB at FP16. Use the FP8 or Q4 quantized
  version of T5 to save ~4-5GB. ComfyUI handles this via separate text encoder loading nodes.
- **Total VRAM budget**: ~3-4GB (Flux NF4/GGUF) + ~2-3GB (T5 quantized) + ~0.5GB (CLIP) +
  ~0.5GB (VAE) = ~6-8GB. Fits on 8GB with careful management.
- If VRAM is still tight during generation, enable **CPU offloading** for the text encoders
  (encode text on CPU, then unload before denoising). ComfyUI supports this natively.
- SDXL at FP16 (~6.5GB with VAE) is a reliable fallback that runs without any quantization on 8GB.

### Phase 2A Validation Plan

This assessment is research-based. The following must be validated hands-on in Phase 2A:

- [ ] Install ComfyUI and load Flux.1-dev GGUF Q5 model
- [ ] Verify generation works within 8GB VRAM budget
- [ ] Run 10-prompt test suite (see `plans/phase-0b-technical-research.md` Section 2) comparing
      local Flux NF4/GGUF vs cloud Flux vs SDXL baseline
- [ ] Evaluate style consistency: generate 5 cards with the same style prefix, assess visual
      cohesion
- [ ] Measure actual generation times per image
- [ ] Test Real-ESRGAN upscaling pipeline end-to-end
- [ ] Compare quantized local output against full-precision API output for quality delta
- [ ] Determine if a custom LoRA is needed or if prompt-only style control is sufficient

---

## Card Rendering

### Comparison Table

| Criterion (Weight) | Proxyshop | CardConjurer | Pillow | Pycairo | Wand/ImageMagick |
|---------------------|:-:|:-:|:-:|:-:|:-:|
| Output quality (25%) | Excellent | Good | Good | Excellent | Good |
| Variant frame support (20%) | Excellent | Good | Manual | Manual | Manual |
| Automation / batch (20%) | Semi (Photoshop) | No (browser) | Full | Full | Full |
| Text layout engine (15%) | Via Photoshop | Canvas API | Manual | Pango | ImageMagick |
| Maintainability (10%) | Low (templates) | Low (browser) | High | High | Medium |
| Dependency weight (10%) | Heavy (Photoshop) | Heavy (browser) | None | Medium | Medium |
| **Verdict** | Rejected | Rejected | **Selected** | Backup | Rejected |

### Recommendation
- **Primary**: **Pillow** — already installed, 16ms/card render time, sufficient text quality at 300 DPI
- **Fallback**: Pycairo — only if text rendering quality proves insufficient at print size
- **Architecture**: Frame template PNGs + Pillow compositing + custom RichTextRenderer for inline mana symbols
- **Frame templates**: Pre-designed PNGs (not procedural). Design in a graphics program, export at 822x1122px
- **Text engine**: Custom `RichTextRenderer` class (~300 lines) that parses `{symbol}` tokens, measures runs, handles word-wrap, composites text + symbol PNGs

### Key Measurements (300 DPI, 822x1122 canvas)

| Element | Position (x, y) | Size (w x h) |
|---------|-----------------|---------------|
| Bleed area | Full canvas | 822 x 1122 |
| Card border | (36, 36) | 750 x 1050 |
| Content area | (48, 48) | 726 x 1026 |
| Name bar | (54, 54) | 714 x 50 |
| Art box | (66, 108) | 690 x 478 |
| Type bar | (54, 592) | 714 x 50 |
| Text box | (66, 648) | 690 x 356 |
| P/T box | (674, 1000) | 90 x 46 |
| Collector bar | (54, 1030) | 714 x 38 |

See `research/proof-of-concept/rendering-notes.md` for full details.

---

## Fonts

### Final Selection

| Purpose | MTG Original | Selected Font | License | File |
|---------|-------------|---------------|---------|------|
| Card name, type line | Beleren | **Cinzel** (variable, 400-900 wght) | OFL | `assets/fonts/cinzel/Cinzel-Variable.ttf` |
| Rules text, flavor text | MPlantin | **EB Garamond** (variable, 400-800 wght + italic) | OFL | `assets/fonts/eb-garamond/EBGaramond-Variable.ttf` |
| P/T, collector info | Gotham | **Montserrat** (variable, 100-900 wght + italic) | OFL | `assets/fonts/montserrat/Montserrat-Variable.ttf` |

### Font Size Reference (300 DPI)

| Pixel Size | Point Equivalent | Use |
|------------|-----------------|-----|
| 28px | 6.7pt | Card name |
| 22px | 5.3pt | Type line, mana cost |
| 21px | 5.0pt | Rules text body |
| 19px | 4.6pt | Flavor text |
| 14px | 3.4pt | Collector info |
| 30px | 7.2pt | Power/Toughness |

### Notes
- All fonts are SIL Open Font License — permits embedding in images and printed products
- Variable TTF format — single file per family, weight selected at load time
- Not identical to real MTG fonts, but this is intentional: clearly distinct from official products
- See `assets/fonts/README.md` for sources and details

---

## Symbol Assets

### Approach
- **Mana/tap symbols**: SVGs from `andrewgioia/mana` repo (MIT license), stored in `assets/symbols/mana/`
- **Rendering method**: Pre-rasterize SVGs to PNGs at standard sizes (16, 20, 24, 28px) for Pillow compositing. Optional: use CairoSVG for on-the-fly conversion.
- **Set symbol**: Placeholder hexagonal shield in `assets/symbols/set-symbol-*.svg` with rarity color variants (common=black, uncommon=silver, rare=gold, mythic=orange). Final symbol designed in Phase 2A.
- **Symbol files location**: `assets/symbols/`

### Inventory
- 40 mana/game SVGs: basic (W/U/B/R/G/C), generic (0-20, X), tap/untap/energy, loyalty (up/down/zero/start), misc
- **Gap**: Hybrid mana (W/U, B/R, etc.) and colored Phyrexian mana are not individual SVGs in the Mana repo — they're rendered via CSS class layering. Will need to composite these at render time (base circle + color overlay + inner symbol).

### Keyrune
- Set symbol font/SVGs from `andrewgioia/keyrune` — GPL 3.0 + OFL license
- Available for reference but we'll use a custom set symbol

---

## Print Service

### Comparison Table

| Attribute | MPC | PrinterStudio | Game Crafter | Ivory (UK) |
|-----------|:---:|:---:|:---:|:---:|
| Ships to NL | Yes | Yes | Yes (expensive) | Yes (customs) |
| Card stock (MTG feel) | S33 (excellent) | S33 (same) | 310gsm (OK) | 320gsm (OK) |
| Max unique cards/deck | 612 | 612 | Limited | Unclear |
| Custom backs | Yes | Yes | Yes | Yes |
| Community for MTG | Huge (r/mpcproxies) | Small | None | None |
| Customs/VAT to NL | None (standard ship) | None (standard ship) | 21% VAT + customs | 21% VAT |
| Draft set (~280) cost | **~$95** | ~$95 | ~$110-135 | ~$190+ |
| Playset (~1100) cost | **~$255** | ~$255 | ~$250-280 | ~$640+ |

### Recommendation
- **Primary service**: **MakePlayingCards (MPC)**
- **Card stock**: S33 (Superior Smooth, black core) — closest to real MTG feel
- **File spec**: 822 x 1122 px, 300 DPI, sRGB, PNG
- **Cost estimate**: ~$25 test batch, ~$95 draft set, ~$255 full playset
- **Order workflow**: Web upload → select 396-card deck → S33 stock → drag-and-drop card images → standard shipping to NL
- **Key advantage**: No import tax/customs for EU standard shipping (verify with test order)

See `research/print-service-comparison.md` for full analysis.

---

## Print Spec Lock-Down

| Spec | Value | Locked? |
|------|-------|:-------:|
| DPI | 300 | [x] |
| Card dimensions (mm) | 63 x 88 | [x] |
| Bleed (mm) | 3mm | [x] |
| Canvas size with bleed (px) | 822 x 1122 | [x] |
| Safe area inset (mm) | 3mm (36px from edge) | [x] |
| Color space | sRGB | [x] |
| ICC profile | N/A (MPC handles conversion) | [x] |
| File format | PNG | [x] |
| File naming | `{set_code}_{collector_number:03d}_{card_name_slug}.png` | [x] |
| Card stock | S33 (Superior Smooth, black core) | [x] |
| Corner radius | ~3mm (printer handles cutting) | [x] |
| Card back dimensions | Same as front (822 x 1122) | [x] |

All specs stored in `config/print-specs.json`.

---

## 1-Card Proof of Concept Results

### Rendering Prototype
- **Tool used**: Pillow 10.4.0
- **Canvas**: 822 x 1122 px at 300 DPI
- **Render time**: 7ms
- **Output**: `research/proof-of-concept/rendered-thornwood-prototype.png`

### Results
- [x] All text elements render cleanly at 300 DPI
- [x] Word wrapping works correctly within text box bounds
- [x] Bold keywords and italic flavor text supported via separate font files
- [x] Layout proportions approximate a real MTG card
- [x] P/T box, collector info, type line all positioned correctly
- [x] **Project fonts integrated**: Cinzel (card name), EB Garamond (rules/flavor), Montserrat (P/T/info)
- [x] **Mana symbols render inline**: {2}{G}{G} rendered as colored circles in name bar
- [x] **Set symbol rendered**: Rarity-colored placeholder in type bar (silver for uncommon)
- [x] SVG fallback: Pillow-only colored circles when CairoSVG not installed

### Remaining for Full PoC (deferred to Phase 2A/2C)
- [ ] Generate actual art using Flux.1-dev and composite into frame
- [ ] Validate at print size (home-print test)
- [ ] Upload to MPC file validator

---

## Open Questions & Risks

1. **Image generation model**: Research-based recommendation is Flux.1-dev (NF4/GGUF quantized) via ComfyUI. Hands-on validation deferred to Phase 2A — quantized quality on 8GB VRAM is the key risk to confirm.
2. **Hybrid mana symbols**: Need to be composited at render time (not available as individual SVGs). Moderate engineering effort.
3. **Frame template creation**: Need to design actual frame PNGs. Proxyshop templates could serve as reference but can't be used directly.
4. **CMYK color shift**: MPC handles sRGB→CMYK conversion internally. Verify with test print that colors are acceptable.
5. **Dynamic font sizing**: Text-heavy cards may need auto-shrinking text. Not yet implemented.
6. **MPC dimensions**: 63x88mm vs MTG's 63.5x88.9mm — negligible difference in sleeves but worth noting.
