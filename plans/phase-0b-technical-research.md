# Phase 0B: Technical Research - Implementation Plan

## 1. Objective

**What this phase delivers:** A complete, verified set of technology choices for image generation, card rendering, font selection, symbol assets, and print production -- documented in `research/tech-decisions.md` with comparison tables and a final recommendation for each category.

**Why it matters:** Phase 2C (Card Renderer) is a hard dependency on every decision made here. The renderer must know the exact DPI, bleed, dimensions, color space, file format, fonts, symbol assets, and frame approach *before* a single line of rendering code is written. Getting these wrong means re-rendering every card. Print service selection also locks the file spec, so the two decisions are coupled.

**Verification milestone:** A single complete card -- art generated, rendered onto a frame with correct fonts/symbols, exported as a print-ready file that passes the chosen print service's file validator.

**Deliverables:**
- `research/tech-decisions.md` -- comparison tables and final picks
- `research/proof-of-concept/` -- the 1-card PoC files (source art, rendered card, print-ready export)
- `learnings/phase0b.md` -- what worked, what didn't, parameter adjustments

---

## Quick Start (Context Reset)

**Prerequisites**: Python installed. GPU with 8GB+ VRAM (for local image generation testing). Internet access.

**Read first**: This plan is self-contained. Optionally skim `plans/master-plan.md` for project context.

**Start with**: Sections 2-6 can be researched in parallel. The 1-card PoC (Section 7) requires all prior research to be done.

**You're done when**: All items in Section 9 (Print Spec Lock-Down Checklist) are locked, the 1-card PoC passes all success criteria (Section 7.4), and `research/tech-decisions.md` is complete.

---

## 2. Image Generation Research

### 2.1 Candidates

| Option | Type | Access | Cost Model |
|--------|------|--------|------------|
| **ChatGPT Plus (DALL-E 3 / GPT-4o image gen)** | Cloud API | $20/mo subscription or API credits | Subscription: ~50 images/day via chat; API: ~$0.04-0.08/image (1024x1024) |
| **Midjourney** | Cloud (Discord / Web) | $10-30/mo subscription | Basic ($10): ~200 images/mo; Standard ($30): 15hr fast + unlimited relax |
| **SDXL (Stable Diffusion XL)** | Local | Free (open weights) | GPU electricity only; requires 8GB VRAM (fits our GPU) |
| **Flux.1 (Black Forest Labs)** | Local / API | Free (open weights for Flux.1-dev/schnell) | Local: free; API: ~$0.003-0.05/image via Replicate/fal.ai |
| **Stable Diffusion 3.5** | Local / API | Open weights (some variants) | Local: free; API via Stability AI |

### 2.2 Quality Assessment Criteria

Score each model 1-5 on these axes using the same test prompt set (10 prompts covering creature, spell, land, artifact, planeswalker art):

| Criterion | Weight | Notes |
|-----------|--------|-------|
| **Fantasy art quality** | 30% | Does it look like professional MTG art? Detail, composition, lighting |
| **Style consistency** | 25% | Can we get 10 images that look like they belong in the same set? |
| **Prompt adherence** | 15% | Does it actually render what we asked for? |
| **Aspect ratio control** | 10% | Can we reliably get the card art aspect ratio (~745:1040 px, roughly 5:7 or close to 3:4)? |
| **Resolution / upscale quality** | 10% | Native resolution and quality after upscaling to 300 DPI print size |
| **Speed & throughput** | 5% | Time per image; can we batch 280+ cards in a reasonable timeframe? |
| **Artifact frequency** | 5% | Hands, faces, text artifacts, weird anatomy |

### 2.3 Test Protocol

1. **Create 10 standardized test prompts** covering:
   - White creature (angel/knight)
   - Blue spell (counterspell/illusion)
   - Black creature (demon/zombie)
   - Red spell (fire/lightning)
   - Green creature (beast/elemental)
   - Multicolor legendary creature
   - Artifact
   - Land (plains, forest, island -- pick one)
   - Planeswalker character portrait
   - Dark/horror scene (test mood range)

2. **Run each prompt** on all candidate models with identical seed/cfg where possible.

3. **Blind comparison** -- number the outputs, score without knowing the source.

4. **Style consistency test** -- pick the best model, generate 10 more with a style prompt prefix, assess cohesion.

### 2.4 Card Art Specifications

| Spec | Value | Rationale |
|------|-------|-----------|
| **Art box aspect ratio** | ~1.56:1 (width:height) or approximately 63mm x 40mm on the physical card | Standard MTG art box proportions |
| **Recommended generation size** | 1024x1024 then crop, or generate at ~1536x1024 natively if model supports | Ensures sufficient resolution for 300 DPI after crop |
| **Minimum final resolution** | 744 x 478 px at 300 DPI (for standard art box) | Based on 63mm x 40.5mm art area at 300 DPI |
| **Preferred final resolution** | 1488 x 956 px or higher (600 DPI) | Allows downsampling for sharper print |
| **Color space** | Generate in sRGB, convert to CMYK during print export | All models output sRGB natively |

### 2.5 Character Reference / Style Consistency Workflow

For legendary creatures and planeswalkers appearing on multiple cards:
- **DALL-E 3 / GPT-4o**: Use conversation context to describe character, provide reference in chat
- **Midjourney**: Use `--cref` (character reference) flag with a reference image URL; `--sref` (style reference) for set-wide style
- **SDXL/Flux local**: Use IP-Adapter or LoRA fine-tuning on a reference image; ControlNet for pose/composition
- **Recommendation**: Test IP-Adapter + Flux.1-dev as primary local approach; Midjourney `--cref` as cloud fallback

### 2.6 Daily Generation Limits & Budget Impact

| Service | Daily/Monthly Limit | Cost for 300 cards | Cost for 500 cards (with variants) |
|---------|---------------------|--------------------|------------------------------------|
| ChatGPT Plus | ~50/day chat, unlimited via API | ~$20 subscription + $12-24 API | ~$20 + $20-40 |
| Midjourney Standard | Unlimited relax mode | $30/mo (1-2 months) | $30-60 |
| SDXL local | GPU-limited (~100-200/hr on 8GB) | $0 (electricity) | $0 |
| Flux.1-dev local | ~30-60/hr on 8GB GPU | $0 (electricity) | $0 |
| Flux via Replicate API | No hard limit | ~$1-15 | ~$2-25 |

### 2.7 Research Tasks

- [ ] Install ComfyUI or AUTOMATIC1111/Forge locally; download SDXL 1.0 and Flux.1-dev checkpoints
- [ ] Verify 8GB VRAM is sufficient for Flux.1-schnell and Flux.1-dev (schnell should fit; dev may need `--lowvram` or quantized model)
- [ ] Run the 10-prompt test suite on each candidate
- [ ] Score and tabulate results
- [ ] Test upscaling pipeline: Real-ESRGAN or SwinIR for 2x-4x upscale
- [ ] Test IP-Adapter for character consistency (install IP-Adapter for SDXL/Flux in ComfyUI)
- [ ] Document best prompt templates per card type

**Key URLs and resources:**
- ComfyUI: `https://github.com/comfyanonymous/ComfyUI`
- AUTOMATIC1111 Forge: `https://github.com/lllyasviel/stable-diffusion-webui-forge`
- Flux.1 models: `https://huggingface.co/black-forest-labs`
- SDXL: `https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0`
- IP-Adapter: `https://github.com/tencent-ailab/IP-Adapter`
- Real-ESRGAN: `https://github.com/xinntao/Real-ESRGAN`
- Replicate (Flux API): `https://replicate.com/black-forest-labs`
- Midjourney: `https://www.midjourney.com`

---

## 3. Card Rendering Research

### 3.1 Candidates

| Tool | Language | Approach | Variant Support | Automation |
|------|----------|----------|-----------------|------------|
| **Proxyshop** | Python (Photoshop scripting) | Uses Photoshop templates via `photoshop-python-api` | Excellent -- many community templates for all frame types | Semi-automated; requires Photoshop license |
| **cardconjurer** | JavaScript (web) | Browser-based canvas rendering | Good -- supports most standard frames | Manual (browser-based); would need Puppeteer automation for batch |
| **Custom Python (Pillow)** | Python | Programmatic image composition | Full control -- build each frame type | Full automation; significant up-front dev effort |
| **Custom Python (cairo/Pycairo)** | Python | Vector + raster composition | Full control with better text rendering than Pillow | Full automation; better text anti-aliasing; moderate dev effort |
| **Custom Python (Wand/ImageMagick)** | Python | ImageMagick bindings | Full control | Full automation; powerful but complex API |

### 3.2 Evaluation Criteria

| Criterion | Weight | Notes |
|-----------|--------|-------|
| **Output quality** | 25% | Anti-aliased text, clean frame edges, proper layer compositing |
| **Variant frame support** | 20% | Can it handle full-art, borderless, showcase, planeswalker, saga? |
| **Automation / batch capability** | 20% | Can we render 280+ cards unattended from a script? |
| **Text layout engine quality** | 15% | Line breaking, rules text with inline mana symbols, italic flavor text |
| **Maintainability** | 10% | Can we modify templates, add new frame types, adjust layout? |
| **Dependency weight** | 10% | External dependencies (Photoshop license, browser, etc.) |

### 3.3 Card Dimensions & Layout

Reference measurements for standard MTG card at 300 DPI:

| Element | Physical (mm) | Pixels at 300 DPI | Pixels at 600 DPI |
|---------|---------------|--------------------|--------------------|
| **Card size (cut)** | 63 x 88 | 744 x 1039 | 1488 x 2079 |
| **Card size (with 3mm bleed)** | 69 x 94 | 815 x 1110 | 1630 x 2220 |
| **Safe area (3mm inset)** | 57 x 82 | 673 x 969 | 1346 x 1937 |
| **Art box (approx)** | 56 x 40.5 | 661 x 478 | 1323 x 956 |
| **Text box (approx)** | 56 x 28 | 661 x 331 | 1323 x 661 |
| **Corner radius** | ~3mm | ~35px | ~71px |

### 3.4 Frame Templates

Need to acquire or create templates for:
- [ ] Standard frames: W, U, B, R, G, multicolor (gold), colorless/artifact, land
- [ ] Planeswalker frame
- [ ] Saga frame (if set uses sagas)
- [ ] Full-art frame
- [ ] Borderless frame
- [ ] Showcase frame (custom per set -- will need to design)
- [ ] Token frame
- [ ] Card back (custom design with "AI-Generated" indicator)

**Source for community templates:**
- Proxyshop templates: `https://github.com/MrTeferi/Proxyshop` (check `/templates/` directory)
- MTG.design: `https://mtg.design` (reference for layout measurements)
- Card Conjurer: `https://cardconjurer.com` (reference implementation)

### 3.5 Text Layout Engine Requirements

The text engine is the hardest part of card rendering. Requirements:

1. **Mixed formatting in a single text block**: Bold keywords, italic reminder text, inline mana symbols
2. **Automatic line breaking** with proper word wrapping
3. **Dynamic font sizing**: Reduce font size if text overflows (MTG does this for text-heavy cards)
4. **Inline symbol rendering**: Mana symbols ({W}, {U}, {B}, {R}, {G}, {C}, {X}), tap ({T}), untap ({Q}), energy ({E}), etc. must render inline at the correct size
5. **Flavor text separator**: The horizontal line between rules text and flavor text
6. **Ability separator**: Line breaks between distinct abilities

**Recommended approach**: If going custom Python, use Pycairo or Pillow with a custom text layout engine that parses MTG-formatted text (with `{symbol}` placeholders) and renders mixed runs of text and symbol images. This is non-trivial but gives full control.

### 3.6 Research Tasks

- [ ] Install Proxyshop, attempt to render a test card (requires Photoshop -- check if free alternatives like Photopea work)
- [ ] Inspect cardconjurer source code for layout logic and measurements
- [ ] Build a minimal Pillow prototype: load a frame PNG, composite art, render card name + mana cost
- [ ] Build a minimal Pycairo prototype: same test, compare text quality
- [ ] Test inline symbol rendering (place a mana symbol PNG/SVG mid-line in rules text)
- [ ] Measure actual MTG card dimensions from a physical card with calipers (verify 63x88mm)
- [ ] Document the rendering pipeline architecture decision

---

## 4. Font Research

### 4.1 Required Fonts

MTG uses proprietary fonts. We need open-source alternatives that are visually close:

| MTG Font | Used For | Style |
|----------|----------|-------|
| **Beleren** (various weights) | Card name, type line | Sharp geometric sans-serif with distinctive MTG feel |
| **Beleren Small Caps** | Card name on some variants | Small caps variant |
| **MPlantin** | Rules text, flavor text (italic) | Oldstyle serif, similar to Plantin |
| **Gotham Medium / Bold** | Collector info, set info, P/T | Clean geometric sans-serif |

### 4.2 Open-Source Alternatives

#### For Beleren (card names, type lines):

| Font | License | Source | Visual Match |
|------|---------|--------|--------------|
| **Beleren Proxy** (fan recreation) | Unclear -- verify | Various fan sites; search "Beleren proxy font" | Very close (if legal) |
| **JaceBeleren** (fan font) | Unclear -- verify | `https://fontstruct.com` (search for JaceBeleren) | Moderate match |
| **Planewalker** (fan font) | Free for personal use | `https://www.dafont.com/planewalker.font` or similar | Designed as Beleren alternative |
| **Cinzel** | OFL (SIL Open Font License) | `https://fonts.google.com/specimen/Cinzel` | Different style but usable for fantasy card names |
| **Alegreya Sans SC** | OFL | `https://fonts.google.com/specimen/Alegreya+Sans+SC` | Alternative if small caps needed |
| **Matrix II / Goudy Medieval** | Various | Commercial | Closer match but not free |

#### For MPlantin (body text):

| Font | License | Source | Visual Match |
|------|---------|--------|--------------|
| **Plantin** (original) | Commercial (Monotype) | Not free | Exact original family |
| **EB Garamond** | OFL | `https://fonts.google.com/specimen/EB+Garamond` | Good oldstyle serif match |
| **Crimson Text** | OFL | `https://fonts.google.com/specimen/Crimson+Text` | Slightly lighter but good match |
| **Cormorant Garamond** | OFL | `https://fonts.google.com/specimen/Cormorant+Garamond` | Elegant, slightly more contrast |
| **Sorts Mill Goudy** | OFL | `https://fonts.google.com/specimen/Sorts+Mill+Goudy` | Good oldstyle feel |
| **Spectral** | OFL | `https://fonts.google.com/specimen/Spectral` | Designed for screen + print, has italic |

#### For Gotham-like (P/T, collector info):

| Font | License | Source | Visual Match |
|------|---------|--------|--------------|
| **Montserrat** | OFL | `https://fonts.google.com/specimen/Montserrat` | Very close to Gotham |
| **Nunito Sans** | OFL | `https://fonts.google.com/specimen/Nunito+Sans` | Softer alternative |
| **Inter** | OFL | `https://fonts.google.com/specimen/Inter` | Clean geometric sans |

### 4.3 Visual Comparison Plan

1. Create a test card image with each font combination (name + body + P/T)
2. Print at actual card size (63x88mm) on standard paper
3. Place next to a real MTG card and compare readability and feel
4. Test at both 300 DPI and 600 DPI
5. Verify italic rendering quality for flavor text
6. Check all fonts include required glyphs: em-dash, bullet, quotation marks, accented characters

### 4.4 License Verification Checklist

For each font selected:
- [ ] Confirm exact license (OFL, Apache 2.0, MIT, etc.)
- [ ] Verify license permits: embedding in generated images (yes for OFL)
- [ ] Verify license permits: use in a printed product for personal use
- [ ] Verify license permits: distribution of the font file within the project repo (OFL allows this)
- [ ] Download from the official source (not a re-hosting site)
- [ ] Store license file alongside font files in `assets/fonts/LICENSE-<fontname>.txt`

### 4.5 Research Tasks

- [ ] Download top 2-3 candidates for each category
- [ ] Create the visual comparison test card (can be done with simple Pillow script)
- [ ] Print comparison at actual card size
- [ ] Make final font selection and document in `research/tech-decisions.md`
- [ ] Store chosen fonts in `assets/fonts/`

---

## 5. Mana / Symbol Assets

### 5.1 Available Symbol Libraries

| Library | Type | License | URL | Coverage |
|---------|------|---------|-----|----------|
| **Mana** (Andrew Gioia) | Icon font + CSS | MIT | `https://github.com/andrewgioia/mana` | Mana symbols, tap, energy, loyalty, hybrid, phyrexian -- comprehensive |
| **Keyrune** (Andrew Gioia) | Icon font + CSS | MIT | `https://github.com/andrewgioia/keyrune` | Set symbols (expansion icons) for all MTG sets |
| **mtg-icons** | SVG | Various | Search GitHub | Alternative SVG-based collections |
| **Scryfall SVGs** | SVG | Fair use | `https://scryfall.com/docs/api/card-symbols` | API returns SVG URIs for all symbols |

### 5.2 Symbol Rendering Approaches

| Approach | Pros | Cons | Best For |
|----------|------|------|----------|
| **Mana font glyphs** | Easy CSS/web rendering, scalable | Harder to use in Pillow/cairo image rendering | Web-based card preview (frontend) |
| **SVG symbols** | Scalable, exact colors, easy to compose | Need SVG renderer (cairo handles this well) | Print-quality card rendering |
| **Pre-rasterized PNGs** | Simplest to composite in Pillow | Fixed resolution, need multiple sizes | Quick prototype |
| **Hybrid: SVG for render, font for web** | Best of both worlds | Maintain two asset sets | Production system |

### 5.3 Symbols Inventory

Full list of symbols needed for card rendering:

**Mana symbols:** {W}, {U}, {B}, {R}, {G}, {C} (colorless), {X}, {0}-{20}
**Hybrid mana:** {W/U}, {W/B}, {U/B}, {U/R}, {B/R}, {B/G}, {R/G}, {R/W}, {G/W}, {G/U}
**Phyrexian mana:** {W/P}, {U/P}, {B/P}, {R/P}, {G/P}
**Other:** {T} (tap), {Q} (untap), {E} (energy), {CHAOS} (planar), loyalty up/down/zero
**Set symbol:** Custom -- needs to be designed for our set (with rarity colorization: black=common, silver=uncommon, gold=rare, mythic orange=mythic)

### 5.4 Set Symbol

A custom set symbol is needed. Options:
- Design it in this phase (simple SVG, can iterate later)
- Defer to Phase 2A (Art Direction) where it fits thematically with the set's visual identity
- **Recommendation**: Create a placeholder/draft set symbol now (simple geometric shape) so the PoC card is complete; finalize the real symbol in Phase 2A when the set theme is known

### 5.5 Research Tasks

- [ ] Clone `andrewgioia/mana` and `andrewgioia/keyrune` repos
- [ ] Extract SVG versions of all needed symbols from the Mana repo (they're in the repo as SVGs)
- [ ] Test rendering SVG symbols inline with text using Pycairo
- [ ] Test rendering PNG symbol sprites inline with text using Pillow
- [ ] Create a symbol rendering test: a mana cost like {2}{W}{U} and rules text with {T}: inline
- [ ] Document the chosen approach (SVG vs PNG vs font)
- [ ] Create placeholder set symbol SVG (simple design)

---

## 6. Print Service Research

### 6.1 Candidates

| Service | Location | Ships to NL | URL |
|---------|----------|-------------|-----|
| **MakePlayingCards (MPC)** | Hong Kong | Yes | `https://www.makeplayingcards.com` |
| **PrinterStudio** | Hong Kong (same parent as MPC) | Yes | `https://www.printerstudio.com` |
| **The Game Crafter** | USA (Wisconsin) | Yes (international) | `https://www.thegamecrafter.com` |
| **DriveThruCards** | USA | Yes (international) | `https://www.drivethrucards.com` |
| **Ivory Graphics** | UK | Yes (EU-adjacent) | `https://www.ivorygraphics.co.uk` |
| **Shuffled Ink** | USA | Yes (international) | `https://www.shuffledink.com` |
| **Cartamundi** | Belgium | Yes (local EU) | `https://www.cartamundi.com` (MOQ may be high) |
| **Board Games Maker** | China | Yes | `https://www.boardgamesmaker.com` |
| **AdMagic / Make My Game** | USA | Yes | `https://www.admaginc.com` |

### 6.2 Comparison Matrix

Research and fill in for each service:

| Spec | MPC | PrinterStudio | Game Crafter | Ivory | DriveThruCards |
|------|-----|---------------|--------------|-------|----------------|
| **DPI requirement** | 300 | 300 | 300 | 300 | 300 |
| **Bleed (mm)** | 3mm (36px) | 3mm | 3.175mm (1/8") | TBD | TBD |
| **Dimensions (mm)** | 63.5 x 88.9 | 63.5 x 88.9 | 63.5 x 88.9 | TBD | TBD |
| **Color space** | sRGB (auto convert) | sRGB | sRGB/CMYK | CMYK preferred | TBD |
| **File format** | PNG/JPG | PNG/JPG | PNG (preferred) | PDF/PNG | PNG |
| **Max file size** | ~5MB/card | ~5MB | 10MB | TBD | TBD |
| **Card stock options** | S30 (standard), S33 (linen), M31 (premium) | Similar to MPC | Various | TBD | TBD |
| **Closest to MTG feel** | S33 (linen) | S33 | Blue core? | TBD | TBD |
| **Min order qty** | 18 cards | 18 cards | 1 card | TBD | TBD |
| **Randomized boosters?** | No (ordered decks) | No | Possible (card packs) | No | No |

### 6.3 Cost Estimates

| Scenario | Cards | MPC (est.) | Game Crafter (est.) | EU Service (est.) |
|----------|-------|------------|---------------------|---------------------|
| **Test batch** | 20 cards | ~$5-8 + shipping | ~$8-12 + shipping | TBD |
| **Draft set** | 270 cards (18 boosters x 15) | ~$30-50 + shipping | ~$50-80 + shipping | TBD |
| **Full playset** | 1100+ cards | ~$100-150 + shipping | ~$150-250 + shipping | TBD |
| **Shipping to NL** | -- | ~$10-25 (HK) | ~$15-30 (USA) | ~$5-15 (EU) |
| **Customs/VAT** | -- | 21% VAT likely | 21% VAT likely | May be included |
| **Turnaround** | -- | 2-3 weeks prod + 1-2 weeks ship | 1-2 weeks + 1-2 weeks ship | TBD |

### 6.4 Key Questions per Service

- [ ] Do they accept custom card backs?
- [ ] Can we print different images on each card (not a deck of identical cards)?
- [ ] What is the upload workflow? (Individual files vs bulk upload vs API)
- [ ] Do they have a bulk/API upload option for 270+ unique cards?
- [ ] What is their exact safe area / cut tolerance?
- [ ] Can we order a test batch of 10-20 cards cheaply?
- [ ] What card stock most closely matches MTG card feel?
- [ ] Have other custom MTG proxy makers used this service? (Check r/mpcproxies for MPC reviews)

### 6.5 MPC-Specific Research (Primary Candidate)

MakePlayingCards is the most commonly used service for custom MTG proxies. Extra research:

- [ ] Confirm exact template dimensions: 822 x 1122 pixels at 300 DPI is the commonly cited spec
- [ ] Safe zone: 36px (3mm) bleed on each side, so final card content at 750 x 1050 px
- [ ] Investigate MPC Autofill tool (`https://mpcfill.com` or similar community tools) for bulk upload
- [ ] Check `r/mpcproxies` subreddit for current best practices and card stock recommendations
- [ ] Test order: Place a 20-card test with MPC before committing to full order
- [ ] Note: MPC uses the term "game cards (63 x 88mm)" -- select this product

### 6.6 Research Tasks

- [ ] Visit each service's website, locate their file specification page, record exact specs
- [ ] Get quotes for 270-card and 1100-card orders from top 3 services
- [ ] Identify EU-based services to avoid customs issues
- [ ] Check Cartamundi's minimum order quantity (may be too high for personal use)
- [ ] Document the recommended upload workflow for the chosen service
- [ ] Create a print-spec config template that the renderer will consume

---

## 7. 1-Card Proof of Concept

### 7.1 Goal

Produce a single complete, print-ready card file that validates the entire technical pipeline. This card will be a simple creature to minimize variables.

### 7.2 Test Card Specification

```
Name: Thornwood Guardian
Mana Cost: {2}{G}{G}
Type: Creature -- Treefolk Warrior
Rules Text: Vigilance
             Thornwood Guardian gets +1/+1 for each Forest you control.
Flavor Text: "The forest does not forget those who walk beneath its canopy."
P/T: 2/4
Rarity: Uncommon
Artist: AI Generated
Collector Number: 001/001
Set Code: TST
```

This card tests:
- Standard green creature frame
- A mana cost with both generic and colored symbols
- A keyword ability (Vigilance)
- Rules text with mana symbol formatting
- Flavor text (italic)
- Power/toughness box
- Collector info line
- Set symbol with uncommon (silver) rarity coloring

### 7.3 Step-by-Step Execution

#### Step 1: Generate Art (Day 1)
1. Use the top image generation candidate from Section 2 research
2. Prompt: `"A towering ancient treefolk warrior standing guard in a mystical green forest, bark armor, glowing green eyes, fantasy card game art style, detailed digital painting, dramatic lighting"`
3. Generate at 1024x1024 minimum
4. Crop/resize to card art aspect ratio (~1.56:1 width:height, approx 1488x956 px or similar)
5. Upscale if necessary using Real-ESRGAN
6. Save as `research/proof-of-concept/art-thornwood-guardian.png`

#### Step 2: Prepare Assets (Day 1-2)
1. Download chosen fonts (Beleren alternative + body text font)
2. Extract mana symbol SVGs/PNGs from Mana font repo ({2}, {G}, {T} at minimum)
3. Obtain or create a green creature frame template (from Proxyshop templates, cardconjurer, or manual recreation)
4. Create a simple placeholder set symbol SVG

#### Step 3: Render Card (Day 2-3)
1. Using the chosen rendering approach (Pillow, Pycairo, or Proxyshop):
   - Load frame template
   - Composite art into art box
   - Render card name ("Thornwood Guardian") in title font
   - Render mana cost symbols ({2}{G}{G}) right-aligned
   - Render type line ("Creature -- Treefolk Warrior")
   - Render rules text with "Vigilance" in bold/keyword style
   - Render flavor text in italic
   - Render P/T ("2/4") in P/T box
   - Render collector info, artist credit, set symbol
2. Save as `research/proof-of-concept/rendered-thornwood-guardian.png`

#### Step 4: Export Print-Ready File (Day 3)
1. Add 3mm bleed margins (extend/mirror edges or use template with bleed)
2. Ensure dimensions match print service spec (e.g., MPC: 822 x 1122 px at 300 DPI)
3. Convert color space to CMYK if required (or leave sRGB if service handles conversion)
4. Set correct DPI metadata in file header
5. Save as `research/proof-of-concept/print-ready-thornwood-guardian.png`

#### Step 5: Validate (Day 3-4)
1. Verify file dimensions and DPI with `identify` (ImageMagick) or Python script
2. If the print service has a file validator / preview tool, upload and check
3. Print at home on standard paper at actual card size (63x88mm) -- hold next to real MTG card
4. Check: text readable? Art quality acceptable? Frame looks right? Proportions correct?
5. Document results in `learnings/phase0b.md`

### 7.4 Success Criteria

- [ ] Art is visually acceptable fantasy illustration quality
- [ ] All text elements are readable at printed card size
- [ ] Mana symbols render correctly inline
- [ ] Card proportions match a real MTG card when printed
- [ ] File meets print service specifications (DPI, dimensions, format)
- [ ] Color accuracy is reasonable (no extreme shifts expected sRGB->CMYK)

---

## 8. Output Specifications

### 8.1 Structure of `research/tech-decisions.md`

```markdown
# Technical Decisions -- Phase 0B

## Image Generation
### Comparison Table
(Table from Section 2.2 with scores filled in)
### Recommendation
- **Primary**: [chosen model] -- reasoning
- **Fallback**: [fallback model] -- when to use
- **Style workflow**: [approach for consistency]
- **Upscaling pipeline**: [tool and settings]

## Card Rendering
### Comparison Table
(Table from Section 3.2 with evaluations)
### Recommendation
- **Approach**: [chosen tool/library]
- **Architecture**: [high-level rendering pipeline description]
- **Frame templates**: [source and format]
- **Text engine**: [approach for mixed text/symbol rendering]

## Fonts
### Comparison Table
(Visual comparison results)
### Final Selection
- **Card name font**: [font name] (license: X)
- **Body text font**: [font name] (license: X)
- **P/T & info font**: [font name] (license: X)
- **Font files location**: assets/fonts/

## Symbol Assets
### Approach
- **Mana/tap symbols**: [source, format, rendering method]
- **Set symbol**: [status -- placeholder or final]
- **Symbol files location**: assets/symbols/

## Print Service
### Comparison Table
(Table from Section 6.2 with all specs filled in)
### Recommendation
- **Primary service**: [name] -- reasoning
- **Card stock**: [specific stock code/name]
- **File spec**: [exact dimensions, DPI, format]
- **Cost estimate**: [for draft set and full playset]
- **Order workflow**: [step-by-step]

## Print Spec Lock-Down
(See Section 9 checklist -- all values finalized)

## 1-Card Proof of Concept Results
- Art generation: [model used, quality assessment]
- Rendering: [tool used, issues encountered]
- Print readiness: [validation results]
- Photos/screenshots of result

## Open Questions & Risks
(Any unresolved items)
```

---

## 9. Print Spec Lock-Down Checklist

These exact values MUST be finalized before Phase 2C begins. They will feed directly into the renderer configuration.

| Spec | Value (to be determined) | Locked? |
|------|--------------------------|---------|
| **DPI** | 300 (likely) or 600 | [ ] |
| **Card dimensions (mm)** | 63 x 88 (standard poker) or 63.5 x 88.9 | [ ] |
| **Bleed (mm)** | 3mm (typical) -- confirm with chosen printer | [ ] |
| **Canvas size with bleed (px)** | Calculated from DPI + dimensions + bleed | [ ] |
| **Safe area inset (mm)** | 3mm from cut line (typically) | [ ] |
| **Color space** | sRGB or CMYK (depends on printer) | [ ] |
| **ICC profile** | If CMYK: which profile? (e.g., US Web Coated SWOP v2) | [ ] |
| **File format** | PNG, JPG, or PDF | [ ] |
| **File naming convention** | e.g., `{set_code}_{collector_number}_{card_name}.png` | [ ] |
| **Card stock** | Specific stock code from chosen printer | [ ] |
| **Corner radius** | ~3mm (for rendering -- printer handles physical cutting) | [ ] |
| **Card back dimensions** | Same as card front with bleed | [ ] |

**These specs should be stored in a machine-readable config file** (e.g., `config/print-specs.json` or `config/print-specs.yaml`) that the renderer imports. Example:

```json
{
  "dpi": 300,
  "card_width_mm": 63.5,
  "card_height_mm": 88.9,
  "bleed_mm": 3.0,
  "safe_area_inset_mm": 3.0,
  "canvas_width_px": 822,
  "canvas_height_px": 1122,
  "color_space": "sRGB",
  "file_format": "png",
  "card_stock": "S33",
  "print_service": "makeplayingcards",
  "corner_radius_mm": 3.0
}
```

---

## 10. Cross-Cutting Concerns & Master Plan Suggestions

### 10.1 Should we evaluate more print services?

**Yes, but prioritize strategically.** The master plan lists MPC, PrinterStudio, and Game Crafter. I've added DriveThruCards, Ivory Graphics (UK), and Board Games Maker as additional candidates. The key addition is **EU-based services** -- shipping from Hong Kong or the USA to the Netherlands incurs customs fees and 21% import VAT on orders above the de minimis threshold. An EU-based printer (Ivory Graphics in the UK post-Brexit still has simplified customs, or Cartamundi in Belgium if MOQ is met) could save significant cost and time on larger orders.

**Recommendation:** Research all listed services in Section 6.1, but only get actual quotes from the top 3 after filtering by spec compatibility and shipping feasibility. MPC should remain the primary candidate given the large community of custom MTG card makers who use it.

### 10.2 Is the $50 art budget realistic?

**The master plan says "Flexible (quality > cost)" for art budget, not $50.** But let's assess realistic costs:

| Approach | Cost for ~300 unique card arts | Cost for ~500 (with variants) |
|----------|-------------------------------|-------------------------------|
| **Local (SDXL/Flux)** | $0 (electricity only, ~$2-5) | $0 |
| **ChatGPT Plus** | $20-40/mo for 1-2 months | $20-60 |
| **Midjourney Standard** | $30/mo for 1-2 months | $30-60 |
| **Replicate API (Flux)** | $5-25 | $10-50 |
| **Mixed (local + API fallback)** | $10-30 | $15-50 |

**Assessment:** $50 is realistic if using primarily local generation with selective API use for difficult prompts. If relying solely on Midjourney or DALL-E, budget $30-60 for 1-2 months of subscription. The main hidden cost is **time** -- local generation on an 8GB GPU is slower, and there will be significant regeneration cycles for quality control.

**Recommendation:** Budget $50-80 for art generation (subscriptions + API credits), but plan for local generation as the primary pipeline to keep costs near zero. Reserve API budget for character reference images, planeswalker art, and any prompts where local models struggle.

### 10.3 Should we create a set symbol in this phase or later?

**Create a placeholder now, finalize in Phase 2A.**

Reasoning:
- The 1-card PoC needs *some* set symbol to validate the rendering pipeline
- The real set symbol should match the set's theme, which isn't defined until Phase 1A
- Phase 2A (Art Direction) is the natural home for visual identity decisions
- A simple geometric placeholder (circle, diamond, triangle) is sufficient for the PoC

**Action:** Create `assets/symbols/set-symbol-placeholder.svg` during the PoC. Add "finalize set symbol" as a task in the Phase 2A plan.

### 10.4 Should print specs feed into a shared config file?

**Absolutely yes.** This is critical for consistency across the pipeline.

**Recommendation:** Create `config/print-specs.json` (or `.yaml`) as shown in Section 9. This file should be:
- The single source of truth for all dimensional/format specifications
- Imported by the card renderer (Phase 2C)
- Imported by the print export pipeline (Phase 5A)
- Imported by validation scripts (Phase 4)
- Version-controlled with the project

Additionally, create a `config/card-layout.json` that defines the pixel positions of every card element (art box, text box, name position, type line position, P/T box, etc.) relative to the canvas. This makes it trivial to adjust layout without modifying rendering code.

**Suggested config structure:**
```
config/
  print-specs.json       # DPI, dimensions, bleed, color space, printer info
  card-layout.json       # Element positions, font sizes, margins
  fonts.json             # Font file paths and usage mapping
  symbols.json           # Symbol asset paths and rendering settings
```

### 10.5 Font licensing risks

**Moderate risk -- needs careful handling.**

| Risk | Severity | Mitigation |
|------|----------|------------|
| Fan-made "Beleren" fonts may violate Wizards of the Coast trademarks | Medium | Only use fonts with clear licensing; avoid fonts that claim to be Beleren |
| Some "free" font sites redistribute commercial fonts illegally | Medium | Only download from official sources (Google Fonts, Font Squirrel with license verification, GitHub repos with explicit licenses) |
| SIL Open Font License requires attribution | Low | Include license files; add attribution in project docs |
| Font embedding in generated images is generally permitted under OFL | Low | Verify OFL Section 2 permits this (it does -- OFL allows use in documents/images) |
| MPlantin has no true open-source equivalent | Medium | EB Garamond or Crimson Text are close but not identical; accept visual difference or explore commercial license for Plantin (~$35-50 from Monotype for desktop use) |

**Recommendation:** Use only SIL OFL or Apache 2.0 licensed fonts. Accept that the fonts won't be *identical* to real MTG cards -- for a custom set, this is actually a feature (it's clearly distinct from official products). Flag this decision in `research/tech-decisions.md` with the rationale.

### 10.6 Additional Concerns

**Aspect ratio mismatch risk:** Different image generation models have different native aspect ratios. DALL-E 3 generates at 1024x1024 (square) or 1792x1024 (wide). Flux generates at arbitrary ratios. If we need ~1.56:1 art, we must either generate natively at that ratio (if the model supports it) or generate wider and crop. Cropping wastes generated content and may cut off important elements. **Test this explicitly in the PoC.**

**CMYK color shift:** sRGB-to-CMYK conversion can cause noticeable color shifts, especially in saturated blues and greens (common in MTG art). If the print service accepts sRGB (MPC does), prefer to submit in sRGB and let them handle conversion. If we must convert, use a proper ICC profile and visually inspect the result. **Include a color test strip in the test print batch.**

**Batch rendering performance:** Rendering 280+ cards with text layout, symbol compositing, and bleed extension could be slow. Benchmark the PoC card render time and extrapolate. If it's >5 seconds per card, consider caching intermediate assets (frames, symbols) and parallelizing rendering.

**Card back design:** The master plan specifies a custom card back with "AI-Generated" indicator. This is a single static image, but it must exactly match the front card dimensions and bleed. **Include card back design as a sub-task of the PoC or Phase 2C.**

---

## Appendix A: Timeline Estimate

| Task | Estimated Duration | Dependencies |
|------|-------------------|--------------|
| Image generation setup + testing | 2-3 days | None |
| Card rendering prototypes | 2-3 days | None (parallel with above) |
| Font research + comparison | 1 day | None (parallel) |
| Symbol asset acquisition + testing | 0.5 days | None (parallel) |
| Print service research | 1-2 days | None (parallel) |
| 1-card proof of concept | 2-3 days | All above complete |
| Documentation + tech-decisions.md | 1 day | PoC complete |
| **Total** | **5-8 days** | (with parallelization) |

## Appendix B: File/Folder Structure After Phase 0B

```
MTGAI/
  research/
    tech-decisions.md              # Main output document
    proof-of-concept/
      art-thornwood-guardian.png    # Generated art
      rendered-thornwood-guardian.png  # Rendered card
      print-ready-thornwood-guardian.png  # Print-ready export
      render-script.py             # Script used for PoC rendering
  learnings/
    phase0b.md                     # Lessons learned
  assets/
    fonts/
      [chosen-name-font].ttf
      [chosen-body-font].ttf
      [chosen-info-font].ttf
      LICENSE-*.txt
    symbols/
      mana/                        # {W}.svg, {U}.svg, etc.
      set-symbol-placeholder.svg
    frames/
      green-creature.png           # At minimum for PoC
  config/
    print-specs.json               # Locked print specifications
  plans/
    phase-0b-technical-research.md # This document
```

## Appendix C: Key External Resources

| Resource | URL | Purpose |
|----------|-----|---------|
| ComfyUI | `https://github.com/comfyanonymous/ComfyUI` | Local image generation UI |
| Flux.1 models | `https://huggingface.co/black-forest-labs` | Image generation checkpoints |
| SDXL | `https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0` | Image generation checkpoint |
| Mana font | `https://github.com/andrewgioia/mana` | Mana/tap symbols |
| Keyrune font | `https://github.com/andrewgioia/keyrune` | Set symbols |
| Proxyshop | `https://github.com/MrTeferi/Proxyshop` | Card rendering reference |
| Card Conjurer | `https://cardconjurer.com` | Card rendering reference |
| Google Fonts | `https://fonts.google.com` | Open-source fonts |
| MakePlayingCards | `https://www.makeplayingcards.com` | Print service |
| The Game Crafter | `https://www.thegamecrafter.com` | Print service |
| PrinterStudio | `https://www.printerstudio.com` | Print service |
| Scryfall API - Symbology | `https://api.scryfall.com/symbology` | Symbol reference data |
| r/mpcproxies | `https://reddit.com/r/mpcproxies` | MPC community knowledge |
| Real-ESRGAN | `https://github.com/xinntao/Real-ESRGAN` | Image upscaling |
| IP-Adapter | `https://github.com/tencent-ailab/IP-Adapter` | Character consistency |
