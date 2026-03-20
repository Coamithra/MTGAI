# wingedsheep/mtg-card-generator Reference

Source: [wingedsheep/mtg-card-generator](https://github.com/wingedsheep/mtg-card-generator)
Python project that generates full MTG sets from scratch — theme, cards, art, renders. Similar goal to MTGAI but very different approach.

## Verdict: Amateur Hour (But With Some Good Ideas to Lift)

Their pipeline is fundamentally simpler — single-pass generation, zero validation, no review, no balance analysis, no custom mechanics. Where we have 8 validators + 18 auto-fixers + tiered council review + balance analysis + skeleton-driven slot allocation, they have... a card count check. But their rendering system and a few architectural choices are worth studying.

---

## What They Do Worse Than Us

### Card Generation
- **Free text → LLM JSON parse** (two-step): LLM generates cards as prose, then a *second* LLM call parses that prose into JSON. We use `tool_choice` for structured output in one shot — cleaner, cheaper, more reliable.
- **No validation at all**: No mana cost validation, no rules text syntax checking, no color pie enforcement, no power level analysis, no text overflow checking. Cards are whatever the LLM spits out.
- **No review or iteration**: Single-pass generation. No council, no iteration loops. First output = final output.
- **No custom mechanics**: Their theme prompt explicitly says "don't introduce new mechanics." We design custom mechanics with reminder text injection.
- **No set skeleton**: Cards generated in batches (1M/3R/4U/5C per batch) with no pre-planned structure. Only balance mechanism is tracking color distribution between batches.
- **LLM-as-JSON-converter anti-pattern**: They burn an LLM call *per card* to convert between two known JSON schemas (internal → Scryfall-like). This is a deterministic transformation that should be 30 lines of Python. Costs money, adds failure modes, needs retry logic.
- **No Pydantic, no enums, no type safety**: Plain `@dataclass` with `from_dict`/`to_dict`. No validation on construction.

### Art
- **No art selection**: They generate exactly 1 image per card and use it. We generate 3 versions + Haiku vision selection.
- **Cloud-only image gen**: Replicate (Imagen 4 or FLUX 1.1 Pro) or local Diffusers (SDXL). No local high-quality option like our ComfyUI + Flux dev GGUF setup.
- **Fixed style prefix**: Every art prompt starts with `"Oil on canvas painting. Magic the gathering art. Rough brushstrokes."` — no per-card style adaptation.

---

## What They Do That's Worth Studying

### Rendering (The Good Part)

Their renderer is HTML/CSS/JS + Playwright screenshots. The card is composed as DOM elements with CSS layout, then a headless Chromium browser screenshots the result at 4x scale. This is slower than our Pillow approach but produces excellent typographic results because it uses the **browser's native text engine**.

#### Fonts (Match Real MTG Cards)
- **Card name**: Beleren Bold, ~9.5–12pt (responsive sizing with shrink-to-fit)
- **Type line**: Beleren Bold, ~8–10pt
- **Rules text**: MPlantin, 8pt base (shrinks to 4pt minimum)
- **P/T**: Beleren, 9.6pt
- **Flavor text**: MPlantin Italic
- **Reminder text**: MPlantin Italic (parenthesized text auto-detected)
- **Collector info**: Relay Wide Medium, 3.9pt
- **Artist name**: Beleren Small Caps, 4.5pt
- **Artist icon**: NDPMTG font (the character "a" renders as a paintbrush — clever!)

We currently use Cinzel/EB Garamond/Montserrat. **Beleren + MPlantin is what real MTG cards use** — this is the single biggest rendering improvement we could make. We already have these fonts in `assets/fonts/`.

#### CSS Millimeter Coordinate System
Card is 63.5mm × 88.9mm (real MTG card size). All positioning in mm:
- Art window: 54.7mm × 39.9mm at (4.4mm, 9.55mm)
- Name bar: 53.8mm × 5.1mm at top: 4mm
- Type bar: 53.8mm × 5.1mm at top: 49.9mm
- Oracle box: 53.8mm × 26mm at top: 55.6mm, padding 1.5mm
- P/T box: 11.58mm × 6.2mm, right: 3mm, bottom: 3.8mm
- Footer: top: 82.91mm, width: 55mm

#### Shrink-to-Fit Details
- **Name/type line**: Start at computed size, decrease by 0.5px/step until `scrollWidth <= clientWidth`, min 4px
- **Oracle text**: Start at 1.0em (8pt), decrease by 0.05em/step, min 0.5em (4pt). If creature (has P/T), reduce 5% more if at 90% of overflow threshold — avoids P/T overlap
- **Planeswalker oracle**: 6.48pt → 4pt, step 0.2pt

#### Flavor Separator
Plain `<hr>` element styled as a thin line. Paragraphs separated by `margin-bottom: 0.5mm`.

#### Mana Symbols in Oracle Text
Inline `<img>` tags sized at `0.8em` with `0.07em` horizontal margin, `vertical-align: baseline`. SVG assets for 80+ symbol codes including hybrid, Phyrexian, energy, tap, untap, snow.

#### Mana Cost (Name Bar)
Symbols at `1.35em` with `border-radius: 50%` and `box-shadow: -0.2mm 0.2mm 0 rgba(0,0,0,0.85)` for depth. Gap: 0.24mm. Container font-size: 6.4pt.

#### Color Determination Logic
- Artifacts → always `"Artifact"` frame
- Vehicles → `"Vehicle"` P/T box + background
- Colorless → `"Colourless"`
- 3+ colors → `"Gold"`
- 2 colors → dual code in WUBRG order (e.g., `"WU"`)
- Lands with no colors → `"Land"`

#### Special Card Layouts Supported
Planeswalkers (with loyalty badges, ability costs), Sagas (tall narrow right-side art, left-side text with roman numeral step icons), MDFC (front/back frames, hint bars), Transform DFC, Adventure. We only handle normal cards currently.

### Pipeline Architecture (Some Good Ideas)

#### Task-Specific Model Routing
```json
{
  "theme_generation": "openai/gpt-4o-2024-11-20",
  "card_batch_generation": "openai/gpt-4o-2024-11-20",
  "art_prompt_generation": "openai/gpt-4o-2024-11-20",
  "json_conversion_from_text": "google/gemini-2.5-flash",
  "render_format_conversion": "google/gemini-2.5-flash"
}
```
Creative tasks get expensive models, mechanical tasks get cheap ones. We already do this (Opus for generation/review, Haiku for art prompts/selection) but their config-driven approach is cleaner.

#### Inspiration Cards
They ship a CSV of all English MTG cards and randomly sample 50-100 as "inspiration" per batch. Not for theme — just mechanical examples so the LLM has real MTG cards to riff on. Interesting idea for prompt quality, though we get similar results from our detailed prompt construction.

#### Booster Draft GUI
A PyQt6 app (`mtg_booster_generator.py`) that generates 15-card draft packs and exports card sheets for Tabletop Simulator. Nice for playtesting.

#### Resumability
`SetStateAnalyzer` scans the output directory to determine which cards need art/rendering. Similar to our `progress.json` approach but filesystem-driven rather than state-file-driven.

---

## Actionable Takeaways for MTGAI

1. **Switch to Beleren + MPlantin fonts** — biggest single rendering improvement. We already have the font files in `assets/fonts/beleren/` and `assets/fonts/mplantin/`. Real MTG cards use Beleren Bold for names/types/P/T and MPlantin for oracle text.

2. **Use Relay Medium for collector info** — we have it in `assets/fonts/relay/`. More authentic than whatever we're using now.

3. **NDPMTG paintbrush font** for artist credit icon — the character "a" renders as a paintbrush. Clever and authentic.

4. **P/T overlap prevention** — their 90% threshold trick (if creature text fills >90% of oracle box, shrink 5% more) is worth adopting.

5. **Mana symbol drop shadow** — `box-shadow: -0.2mm 0.2mm 0 rgba(0,0,0,0.85)` on mana cost symbols adds depth. Easy to add.

6. **Flavor separator as an image asset** — Card Conjurer uses an image asset for the flavor bar (not just a drawn line). Could improve visual fidelity.

7. **Saga/Planeswalker/DFC layouts** — good reference data for when we eventually support these card types. Their coordinate system and layout rules are well-documented in CSS.

---

## Cost Comparison
- Their pipeline: ~$10-15 per 260-card set (GPT-4o + Gemini Flash + Replicate Imagen)
- Our pipeline: ~$13 for 60-card dev set (Opus for generation + council review, Haiku for art/selection, local ComfyUI for images)
- Per-card our approach is much more expensive, but we get validated, reviewed, balanced cards with curated art. They get unvalidated first drafts with random single-shot art.
