# Phase 2: Art & Rendering Pipeline - Detailed Implementation Plan

> **Prerequisite phases**: Phase 0B (print specs), Phase 0D (LLM strategy), Phase 0E (prompt spike).
> **Parallel with**: Phase 1 (set design) -- 2A can run concurrently with 1A-1C.
> **Hard dependency for 2B**: Card data from Phase 1C (needs card names, types, descriptions to generate art prompts).
> **Hard dependency for 2C**: Print specs from Phase 0B (DPI, bleed, CMYK, printer file format requirements).

## Quick Start (Context Reset)

**Prerequisites**:
- Phase 0B complete: `research/tech-decisions.md` with print specs, font selections, symbol assets
- Phase 0B: `config/print-specs.json` locked
- Phase 1C complete (for 2B): card data in `output/sets/<code>/cards/` (needed for art prompts)
- Phase 0B print specs locked (for 2C): DPI, bleed, dimensions, color space finalized
- Phase 4A+4B balance gate passed (for 2B): don't generate art until set balance is confirmed

**Read first**: This plan, plus `research/tech-decisions.md` (Phase 0B output) for rendering stack and print spec decisions.

**Start with**: Phase 2A (Art Direction) — can run in parallel with Phase 1.

## Deliverables Checklist

### Phase 2A: Art Direction System
- [ ] `output/sets/<code>/art-direction/style-guide.md` — visual identity document
- [ ] Color palette, mood, composition guidelines per card type
- [ ] 10+ sample art pieces generated and evaluated for consistency
- [ ] Go/no-go gate passed (20 sample arts across card types)
- [ ] Character reference images for recurring characters (legendaries, planeswalkers)
- [ ] Finalized set symbol SVG (replaces Phase 0B placeholder)
- [ ] `learnings/phase2a.md`

### Phase 2B: Art Generation Pipeline
- [ ] Art generated for all ~280+ cards in `output/sets/<code>/art/`
- [ ] Automated QA passed on every image (resolution, aspect ratio, file size)
- [ ] Rejected art regenerated
- [ ] Post-processing applied (crop, color correct, upscale)
- [ ] Human review via HTML gallery — all art approved or flagged
- [ ] `learnings/phase2b.md`

### Phase 2C: Card Renderer
- [ ] Frame templates for all needed types (W/U/B/R/G/multi/artifact/land + planeswalker)
- [ ] Text layout engine working (mixed formatting, inline symbols, dynamic sizing)
- [ ] Proxy render mode (text-only without art) functional
- [ ] Dual resolution output: 72 DPI (screen) + 300+ DPI (print)
- [ ] All ~280 cards rendered to `output/sets/<code>/renders/`
- [ ] Custom card back designed with "AI-Generated" indicator
- [ ] Text overflow detection passing on every card
- [ ] Print spec compliance validated (DPI, dimensions, color space, bleed)
- [ ] Home-print test batch (~10 cards) checked for sizing/readability
- [ ] `learnings/phase2c.md`

**Done when**: Every card has approved art, a rendered card image, and the rendered images pass print spec compliance checks.

---

## Phase 2A: Art Direction System

### 2A.1: Style Guide Creation

**Goal**: Produce a single reference document (`output/sets/<set-code>/art-direction/style-guide.md`) that every art prompt inherits from. This guide is the "source of truth" for visual identity.

**Style guide structure:**

```
# <Set Name> - Visual Style Guide

## World Setting
- Geography: [terrain types, climate, time of day/season]
- Architecture: [building styles, materials, scale]
- Technology level: [medieval, Renaissance, magitech, etc.]
- Flora: [dominant plant types, colors, unusual vegetation]
- Fauna: [natural creatures, how they differ from real-world analogs]

## Color Palette
- Primary:    #XXXXXX, #XXXXXX (dominant scene colors)
- Secondary:  #XXXXXX, #XXXXXX (accent/contrast)
- Accent:     #XXXXXX (small pops of color, magical effects)
- Avoid:      #XXXXXX, #XXXXXX (colors that clash with the world)
- Per-color identity:
  - White cards: warm golds, ivory, sun-bleached stone
  - Blue cards: deep teal, silver, cold mist
  - Black cards: bruised purple, sickly green-black, obsidian
  - Red cards: volcanic orange, ember red, charcoal
  - Green cards: deep emerald, mossy brown, dappled sunlight

## Mood & Atmosphere
- Overall tone: [epic, eerie, whimsical, grim, hopeful]
- Lighting style: [golden hour, overcast, dramatic chiaroscuro, diffused]
- Weather/atmosphere: [mist, rain, clear, ash-filled]
- Emotional register by rarity:
  - Common: everyday, grounded, relatable
  - Uncommon: heightened, slightly dramatic
  - Rare: epic, cinematic, intense
  - Mythic: transcendent, awe-inspiring, otherworldly

## Artistic Style
- Medium reference: [digital painting, oil painting, watercolor, etc.]
- Detail level: [painterly broad strokes vs fine detail]
- Influence artists: [art style references -- NOT named real artists for AI prompts,
  instead describe the qualities: "Romantic-era landscape painting",
  "Pre-Raphaelite richness", "Studio Ghibli softness"]
- What to avoid: [photorealism, cartoonish, chibi, oversaturated HDR]

## World-Building Elements (consistency anchors)
- Clothing/armor styles per faction or color
- Recurring motifs (e.g., spiral patterns, crescent moons, thorned vines)
- Magic visual language (how spells look: particle effects, glows, runes)
- Iconic landmarks that may appear in backgrounds
```

**Process:**
1. Draft the style guide before any art generation.
2. Generate 5 "world concept" images to test whether the guide translates into coherent visuals.
3. Revise the guide based on what the AI actually produces (some descriptors work better than others).
4. Lock the guide. All subsequent prompts reference it.

**Deliverable:** `output/sets/<set-code>/art-direction/style-guide.md`

---

### 2A.2: Prompt Templates by Card Type

Each card type has distinct compositional and thematic needs. Prompts follow a layered structure:

**Universal prompt prefix** (prepended to every art prompt):
```
[Style guide excerpt: medium, mood, palette, world-building anchors]
Fantasy card game illustration.
```

**Universal prompt suffix** (appended to every art prompt):
```
No text, no borders, no card frames, no watermarks, no signatures.
High detail, painterly rendering, [aspect ratio directive].
```

#### Creature Prompts
```
Template:
"[Universal prefix]
A [size descriptor] [creature type] in a [action/pose].
[Physical description: body shape, distinguishing features, coloring].
[Environment: where it lives, background context].
[Lighting and mood matching rarity].
[Color identity visual cues: white=bright/divine, blue=arcane/watery, etc.].
The creature is the clear focal point, occupying 60-70% of the frame.
[Universal suffix]"

Key rules:
- Creature must be the dominant subject.
- Camera angle: slightly low for large creatures (conveys power),
  eye-level for humanoids, slightly above for small creatures.
- Leave compositional breathing room at top (card name area)
  and bottom (P/T box area).
- Legendary creatures: more detail, unique features, regal/imposing framing.
```

#### Spell Prompts (Instants & Sorceries)
```
Template:
"[Universal prefix]
A dramatic scene depicting [the spell effect in action].
[Who/what is casting or affected by the spell].
[Magical energy visual: color-coded to card color].
[Environment context].
Dynamic composition with strong motion lines or energy flow.
[Universal suffix]"

Key rules:
- Show the EFFECT, not a static scene. Instants should feel like a frozen moment.
- Sorceries can be more sweeping/wide-angle (they're bigger effects).
- Instants should feel sudden, tight-cropped, high-energy.
- Magic effects should follow set's visual language for spells.
```

#### Enchantment Prompts
```
Template:
"[Universal prefix]
[A scene, aura, or persistent magical effect].
[Ethereal, glowing, or otherworldly quality -- enchantments feel 'ongoing'].
[If Aura: show the enchantment affecting a subject].
[If global: show a landscape or scene transformed by the effect].
Soft luminous edges, subtle glow, sense of permanence.
[Universal suffix]"

Key rules:
- Enchantments should feel "lingering" -- less action, more atmosphere.
- Auras: show a subject WITH the enchantment visually applied.
- Use more diffused lighting than creature/spell art.
```

#### Artifact Prompts
```
Template:
"[Universal prefix]
A [material description] [object type] displayed [context: on pedestal,
being wielded, in a workshop, etc.].
[Intricate detail on the object itself].
[Material quality: metallic, crystalline, organic, ancient, etc.].
The artifact is the clear focal point, rendered with fine detail.
Neutral or muted background to emphasize the object.
[Universal suffix]"

Key rules:
- Artifacts are OBJECTS -- the item itself is the subject.
- Equipment: can show a figure holding/wearing it, but the item is the focus.
- Use dramatic lighting to highlight material properties (reflections, gems).
- Colorless artifacts: neutral palette. Colored artifacts: hint of color identity.
```

#### Land Prompts
```
Template:
"[Universal prefix]
A [landscape type] viewed from [vantage point].
[Time of day, weather, atmospheric conditions].
[World-building elements: architecture, vegetation, geological features].
[Color identity through environment: plains=open fields/sun,
island=coast/water, swamp=murky/decayed, mountain=peaks/volcanic,
forest=dense canopy/ancient trees].
Wide-angle landscape composition, sense of vastness and place.
No figures or creatures in the scene.
[Universal suffix]"

Key rules:
- Lands are ENVIRONMENTS -- no characters (or only tiny distant figures).
- Basic lands: iconic, immediately readable (Plains = open golden field).
- Nonbasic lands: blend two color identities or show a unique location.
- Panoramic composition, slightly wider framing than other card types.
- Emphasize depth (foreground detail, midground subject, background vista).
```

#### Planeswalker Prompts
```
Template:
"[Universal prefix]
A powerful [character description] [action: casting a spell, surveying,
arriving through a portal, etc.].
[Detailed clothing/armor matching faction and color identity].
[Magical aura or energy surrounding them, color-coded].
[Expression conveying personality: determined, cunning, serene, fierce].
Portrait-style composition: character fills most of the frame,
depicted from waist up or full body with strong presence.
Cinematic lighting, mythic-rare level of drama and grandeur.
[Universal suffix]"

Key rules:
- Planeswalkers are CHARACTER PORTRAITS -- the most "hero shot" framing.
- Must feel like the most important person in the room.
- Character reference images are critical here (see 2A.3).
- More detail and polish than typical creature art.
- Background should support the character's color identity but not compete.
```

**Deliverable:** `output/sets/<set-code>/art-direction/prompt-templates.md` plus a Python module `mtgai/art/prompt_builder.py` that programmatically assembles prompts from card data + templates + style guide.

---

### 2A.3: Character Consistency

**Problem**: Key characters (legendary creatures, planeswalkers, story-relevant beings) appear on multiple cards. They must be recognizable across appearances.

**Workflow:**

1. **Identify recurring characters**: From the card data, list every character that appears on 2+ cards (their own card plus referenced in other cards' art). Typically 5-15 characters per set.

2. **Generate character reference sheets**: For each recurring character, generate a dedicated reference image:
   ```
   Character Reference Sheet for [Name]:
   - Full body front view, neutral pose, plain background
   - Key identifying features: [list]
   - Clothing/armor details: [list]
   - Color palette for this character: [list]
   ```
   Save to: `output/sets/<set-code>/art-direction/characters/<name_slug>_reference.png`

3. **Store character descriptions**: Alongside the image, store a text description in `output/sets/<set-code>/art-direction/characters/<name_slug>.json`:
   ```json
   {
     "name": "Character Name",
     "reference_image": "characters/character_name_reference.png",
     "description": "Tall elven figure with silver hair...",
     "key_features": ["silver hair", "crescent scar on left cheek", "blue robes with gold trim"],
     "color_identity": ["U", "W"],
     "appears_on_cards": ["001_card_name", "045_card_name", "198_card_name"]
   }
   ```

4. **Reference image workflow in generation**:
   - For ChatGPT Plus / DALL-E: Upload the reference image in the same conversation and prompt "Use this character reference for [Name]." This leverages in-conversation visual memory.
   - For Midjourney: Use `--cref <url>` (character reference) flag with the stored reference image.
   - For local models (Stable Diffusion / Flux): Use IP-Adapter or similar image-to-image conditioning with the reference.

5. **Consistency validation**: After generating art for all cards featuring a character, lay them out side-by-side in the HTML gallery (Phase 2B.6) for human comparison. Flag inconsistencies for regeneration.

**Limitation acknowledgment**: Current AI image generation has imperfect character consistency. The workflow above maximizes consistency but will not achieve perfect results. The human review step is essential. Budget 1-2 extra regeneration attempts per character-featuring card.

---

### 2A.4: Artist Style Variation

**Philosophy**: Real MTG sets have 50+ different artists. Perfect visual uniformity would look artificial. Deliberate style variation is a feature.

**Approach -- controlled variation:**

1. **Define 4-6 "artist personas"** -- stylistic profiles that all share the set's palette and world-building elements but differ in technique:
   ```
   Persona A: "Romantic Landscape" -- soft brushwork, warm light, atmospheric perspective
   Persona B: "Dark Realism" -- high contrast, sharp detail, dramatic shadows
   Persona C: "Ethereal Impressionist" -- loose brushwork, luminous colors, dreamlike
   Persona D: "Bold Graphic" -- strong outlines, saturated colors, flat areas, poster-like
   Persona E: "Classical Oil" -- Renaissance composition, rich darks, glazed highlights
   ```

2. **Assign personas to card slots**: Each card in the set data gets an `art_style` field (can be random or curated):
   - Lands often benefit from Persona A or C (landscape-focused styles).
   - Creatures vary across all personas.
   - Spells lean toward Persona B or D (dramatic/graphic for action).
   - Planeswalkers get Persona E (classical grandeur).

3. **Cohesion anchors** (these stay constant across ALL personas):
   - Color palette from the style guide.
   - World-building elements (architecture, clothing, flora/fauna).
   - Lighting direction consistency within a color (e.g., white cards always lit from above).
   - Recurring motifs and symbols.

4. **Implementation in prompt builder**: The `prompt_builder.py` module appends the persona's style description to each card's prompt. The style guide prefix remains constant; only the style-specific suffix changes.

**Deliverable:** Artist personas documented in style guide. `art_style` field added to card data schema.

---

### 2A.5: Quality Evaluation Rubric

**Purpose**: Provide a consistent framework for evaluating generated art, used by both automated scoring (2B.3) and human review.

**Rubric (score 1-5 per criterion):**

| Criterion | 1 (Reject) | 3 (Acceptable) | 5 (Excellent) |
|-----------|-----------|-----------------|---------------|
| **Composition** | Subject unclear, awkward cropping, no focal point | Clear subject, decent framing, some wasted space | Strong focal point, dynamic composition, perfect framing for card |
| **Color Fidelity** | Completely off-palette, clashing colors | Mostly on-palette, minor deviations | Perfect palette match, beautiful color harmony |
| **Mood Match** | Wrong tone entirely (cheerful for a horror card) | Generally appropriate mood | Perfectly evokes the intended emotion |
| **Card-Size Readability** | Muddy, indistinct at card size (63x88mm) | Readable but lacks punch at small size | Striking and clear even at thumbnail size |
| **Artifact Detection** | Obvious AI artifacts: extra fingers, text, melted objects, impossible geometry | Minor artifacts that could be overlooked | Clean, no visible artifacts |
| **Style Consistency** | Doesn't match set's visual language at all | Recognizably from the same set | Feels perfectly integrated with the set |
| **Type Appropriateness** | Creature art on a land, landscape on an instant, etc. | Appropriate but generic | Art perfectly communicates the card's type and effect |

**Scoring thresholds:**
- **Auto-approve**: Average >= 4.0, no criterion below 3
- **Human review**: Average >= 3.0, no criterion below 2
- **Auto-reject**: Any criterion = 1, or average < 3.0

**Automated scoring** (what a script can check -- see 2B.3):
- Artifact Detection: partial automation via resolution analysis, edge detection for anomalies
- Card-Size Readability: downscale to card-size pixels, check contrast and detail preservation
- Color Fidelity: extract dominant colors, compare to palette hex values using deltaE

**Human scoring** (cannot be automated):
- Composition, Mood Match, Style Consistency, Type Appropriateness

---

### 2A.6: Go/No-Go Gate

**Trigger**: After generating 20 sample arts across a representative spread of card types.

**Sample distribution:**
- 4 creatures (one per rarity: common, uncommon, rare, mythic)
- 3 spells (1 instant, 1 sorcery, 1 with flashy effect)
- 2 enchantments (1 aura, 1 global)
- 2 artifacts (1 equipment, 1 non-equipment)
- 5 lands (1 per basic land type)
- 2 planeswalkers
- 2 legendaries (creature type)

**Evaluation criteria:**

1. **Quality bar**: At least 14/20 samples (70%) score "Acceptable" or higher on the rubric.
2. **Consistency check**: Lay out all 20 side-by-side. Does it look like they belong to the same set? (Y/N, requires human judgment.)
3. **Character consistency test**: Generate the same character twice. Are they recognizably the same person? (Y/N.)
4. **Aspect ratio compliance**: All 20 images are within acceptable aspect ratio (see 2A.7). (100% required.)
5. **Resolution compliance**: All 20 images meet minimum resolution requirements. (100% required.)
6. **Time/cost check**: Extrapolate from the 20 samples. Can 280+ cards be generated within budget and a reasonable timeframe (e.g., 2 weeks)?

**Decision framework:**
- **GO**: Criteria 1-5 pass. Proceed to Phase 2B.
- **ITERATE**: Criteria 4-5 pass but 1-3 have issues. Revise style guide and prompts, generate another 10 samples.
- **PIVOT**: Fundamental quality issues. Switch art generation approach (e.g., change service, try local models, adjust art style significantly). Re-run 2A from the beginning.

**Maximum iterations**: 3 rounds of 20 samples. If quality is still insufficient after 60 total sample images, escalate to a full approach reassessment (different AI service, different art style, or reduced scope).

---

### 2A.7: Aspect Ratio & Composition

**MTG card dimensions:**
- Full card: 63mm x 88mm (2.5" x 3.5")
- At 300 DPI: 744 x 1039 pixels (without bleed)
- With 3mm bleed: 69mm x 94mm = 815 x 1110 pixels

**Art area on a standard MTG card frame:**
- Art box: approximately 56mm x 41mm (the visible art window)
- At 300 DPI: approximately 661 x 483 pixels
- **Aspect ratio: ~1.37:1 (landscape orientation)**
- With bleed behind the frame (art extends under the border): generate at approximately 700 x 530 pixels minimum, ideally larger and crop down.

**Generation target resolution:**
- Generate at the highest resolution the service supports, then crop/resize.
- Minimum usable: 1024 x 748 pixels (allows for cropping and still meeting 300 DPI at card art box size).
- Ideal: 1536 x 1120 or higher.
- DALL-E 3 outputs 1024x1024 or 1792x1024. **Use 1792x1024 (landscape)** -- this is close to the needed ~1.37:1 ratio.
- Midjourney: use `--ar 4:3` or `--ar 11:8` (closest to 1.37:1).

**Composition safe zones** (what will be visible vs hidden by frame):
```
+--------------------------------------------------+
|  BLEED ZONE (hidden by frame border, ~3mm)       |
|  +--------------------------------------------+  |
|  | TOP SAFE ZONE (card name overlays here)    |  |
|  | Keep this area simple/dark for text legibility|
|  |                                            |  |
|  |     FOCAL POINT ZONE                       |  |
|  |     (center-upper area of the art box)     |  |
|  |     Primary subject goes here              |  |
|  |                                            |  |
|  | BOTTOM SAFE ZONE (type line overlays here) |  |
|  | Keep relatively simple/dark                |  |
|  +--------------------------------------------+  |
+--------------------------------------------------+
```

**Prompting for good composition:**
- Explicitly state in prompts: "Subject centered in the upper-middle area of the frame."
- For creatures: "Leave breathing room at top and bottom edges."
- For landscapes: "Horizon line in upper third or lower third, not centered."
- For portraits (planeswalkers): "Character from waist up, centered, looking slightly off-camera."
- Add to ALL prompts: "No important details in the outer 10% of the image edges (will be cropped)."

**Post-generation crop workflow** (handled in 2B.4):
1. Generate at service's native resolution.
2. Crop to exact 1.37:1 aspect ratio, centering on the detected focal point.
3. Resize to final art box dimensions (661 x 483 at 300 DPI, or larger if rendering at higher resolution for print).
4. Save both the original uncropped image (for re-cropping if needed) and the cropped version.

---

## Phase 2B: Art Generation Pipeline

### 2B.1: Batch Generation Architecture

**Goal**: Process 280+ cards through art generation with fault tolerance, rate limiting, and resumability.

**Architecture:**

```
mtgai/art/
    __init__.py
    prompt_builder.py     # Assembles prompts from card data + style guide + templates
    generator.py          # Abstract base class for art generation services
    dalle_generator.py    # DALL-E / ChatGPT Plus implementation
    midjourney_generator.py  # Midjourney implementation (if used)
    local_generator.py    # Local model implementation (Stable Diffusion / Flux)
    quality_scorer.py     # Automated quality checks
    post_processor.py     # Crop, resize, color correction
    batch_runner.py       # Orchestrates the full batch pipeline
    gallery.py            # HTML gallery generator
```

**Batch runner design (`batch_runner.py`):**

```python
class BatchRunner:
    """Orchestrates art generation for an entire set."""

    def __init__(self, set_code: str, generator: ArtGenerator, config: BatchConfig):
        self.set_code = set_code
        self.generator = generator
        self.config = config
        self.state_file = f"output/sets/{set_code}/art-generation-state.json"

    def run(self):
        """Main entry point. Processes all cards needing art."""
        cards = self.load_cards_needing_art()  # status == 'approved', no art yet
        state = self.load_or_create_state()

        for card in cards:
            if card.collector_number in state.completed:
                continue  # Already done -- resume support

            try:
                self.rate_limiter.wait()  # Respect API rate limits
                result = self.generate_for_card(card, attempt=state.get_attempt(card))
                self.save_result(card, result)
                state.mark_completed(card.collector_number)
            except RateLimitError:
                state.save()  # Persist progress
                self.wait_for_rate_limit_reset()
            except GenerationError as e:
                state.mark_failed(card.collector_number, str(e))
                continue  # Skip, will enter regeneration queue

            state.save()  # Persist after each card

    def generate_for_card(self, card: Card, attempt: int) -> GenerationResult:
        prompt = self.prompt_builder.build(card)
        raw_image = self.generator.generate(prompt)
        score = self.quality_scorer.score(raw_image, card)

        if score.auto_reject:
            if attempt < self.config.max_auto_retries:  # Default: 2
                return self.generate_for_card(card, attempt + 1)
            raise GenerationError(f"Failed after {attempt} attempts")

        processed = self.post_processor.process(raw_image, card)
        return GenerationResult(image=processed, score=score, prompt=prompt, attempt=attempt)
```

**State file (`art-generation-state.json`):**
```json
{
  "set_code": "XYZ",
  "started_at": "2026-03-10T14:00:00Z",
  "last_updated": "2026-03-10T16:34:00Z",
  "total_cards": 280,
  "completed": ["001", "002", "003"],
  "failed": {
    "004": {"error": "Rate limit exceeded", "attempts": 2, "last_attempt": "2026-03-10T15:22:00Z"}
  },
  "pending_review": ["005", "006"],
  "approved": [],
  "rejected": []
}
```

**Rate limiting strategy:**
- DALL-E 3 (ChatGPT Plus): ~50 images/3 hours (varies). Implement exponential backoff on 429 errors.
- Midjourney: ~200 images/day on standard plan. Track daily count, pause at 180.
- Local models: Limited by GPU speed (~2-5 minutes per image on 8GB VRAM). No rate limit, but track thermal throttling.

**Resume capability:**
- State file persisted after every card completion.
- On restart, `load_or_create_state()` reads existing state and skips completed cards.
- Failed cards are logged but not blocking -- they enter the regeneration queue (2B.5).

**CLI commands:**
```bash
python -m mtgai.art generate --set XYZ                    # Start/resume batch generation
python -m mtgai.art generate --set XYZ --card 042         # Generate for a single card
python -m mtgai.art status --set XYZ                      # Show progress summary
python -m mtgai.art retry-failed --set XYZ                # Retry all failed cards
python -m mtgai.art gallery --set XYZ                     # Generate HTML review gallery
```

---

### 2B.2: API/Service Integration

**Abstract generator interface:**

```python
from abc import ABC, abstractmethod
from pathlib import Path
from dataclasses import dataclass

@dataclass
class GenerationResult:
    image_path: Path
    prompt_used: str
    attempt_number: int
    service: str  # "dalle3", "midjourney", "local_flux"
    raw_metadata: dict  # Service-specific metadata

class ArtGenerator(ABC):
    @abstractmethod
    def generate(self, prompt: str, reference_images: list[Path] | None = None) -> Path:
        """Generate an image from a prompt. Returns path to saved image."""
        ...

    @abstractmethod
    def check_availability(self) -> bool:
        """Check if the service is available (credits remaining, API accessible)."""
        ...
```

**DALL-E 3 implementation (via OpenAI API):**
```python
class DalleGenerator(ArtGenerator):
    def generate(self, prompt: str, reference_images: list[Path] | None = None) -> Path:
        # If reference images provided, use ChatGPT conversation mode
        # (upload reference, then request generation in same thread)
        # Otherwise, use direct DALL-E 3 API call

        response = self.client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1792x1024",  # Landscape, closest to card art ratio
            quality="hd",      # Higher detail
            n=1
        )
        image_url = response.data[0].url
        image_path = self.download_and_save(image_url)
        return image_path
```

**File download and naming:**
- Download to: `output/sets/<set-code>/art/raw/<collector_number>_<card_name_slug>_v<attempt>.png`
- Example: `output/sets/XYZ/art/raw/042_goblin_firestarter_v1.png`
- Also save the prompt used: `output/sets/XYZ/art/raw/042_goblin_firestarter_v1_prompt.txt`

**Configuration** (`config/art-generation.json`):
```json
{
  "service": "dalle3",
  "api_key_env_var": "OPENAI_API_KEY",
  "default_size": "1792x1024",
  "quality": "hd",
  "max_retries_per_card": 3,
  "rate_limit": {
    "requests_per_minute": 5,
    "daily_limit": 50,
    "backoff_base_seconds": 60
  },
  "output_format": "png"
}
```

**API key management**: API key stored in environment variable (never in code or config files). The config file references the env var name, not the key itself.

---

### 2B.3: Quality Scoring Pipeline

**Automated checks (run on every generated image):**

```python
@dataclass
class QualityScore:
    resolution_ok: bool          # Meets minimum pixel requirements
    aspect_ratio_ok: bool        # Within tolerance of target ratio
    artifact_score: float        # 0.0 (clean) to 1.0 (heavy artifacts)
    color_palette_match: float   # 0.0 (completely off) to 1.0 (perfect match)
    contrast_score: float        # 0.0 (flat/muddy) to 1.0 (good contrast)
    card_size_clarity: float     # 0.0 (indistinct at card size) to 1.0 (clear)
    overall: float               # Weighted average
    auto_reject: bool            # True if any hard-fail criterion triggered
    issues: list[str]            # Human-readable issue descriptions
```

**Check implementations:**

1. **Resolution verification**:
   - Minimum: 1024 x 748 pixels.
   - Check: `image.width >= 1024 and image.height >= 748`.
   - Hard fail if below minimum.

2. **Aspect ratio check**:
   - Target: ~1.37:1 (landscape).
   - Tolerance: +/- 0.15 (accepts ratios from ~1.22:1 to ~1.52:1 since we crop).
   - Check: `abs(image.width / image.height - 1.37) < 0.15`.
   - Hard fail if outside tolerance (image cannot be cropped to fit).

3. **Artifact detection** (heuristic, not perfect):
   - **Text detection**: OCR pass (pytesseract) -- AI images often contain garbled text. Flag if OCR detects text-like patterns.
   - **Edge anomaly detection**: Use Canny edge detection and look for unnatural edge density clusters (melted/distorted areas).
   - **Hand/finger analysis**: This is the most common AI artifact. Use a pre-trained hand keypoint detector if available, or flag for human review by default.
   - Score: 0.0 (no artifacts detected) to 1.0 (heavy artifacts). Threshold for auto-reject: > 0.7.

4. **Color palette analysis**:
   - Extract top 5 dominant colors using k-means clustering on the image.
   - Compare each dominant color to the style guide palette using CIEDE2000 deltaE.
   - Score: average deltaE across dominant colors, normalized to 0-1 range.
   - Not a hard fail -- just informational for human review.

5. **Card-size readability check**:
   - Downscale image to actual card art box pixel size (approximately 200 x 146 pixels at screen resolution, simulating physical card at arm's length).
   - Compute local contrast (standard deviation of luminance in small patches).
   - If contrast is too low, the image will look muddy at card size.
   - Score: normalized contrast value.

6. **Color range analysis**:
   - Check that the image uses a reasonable dynamic range (not blown out, not too dark).
   - Histogram analysis: flag if >30% of pixels are near-black or near-white.

**Pipeline integration**: Quality scoring runs automatically after each generation. Results stored alongside the image in the state file. Auto-reject triggers immediate retry (up to `max_retries`). Borderline images are flagged for human review in the gallery.

---

### 2B.4: Post-Processing

**Tools: Pillow (Python Imaging Library)**

Pillow is the right choice here. It is pure Python, handles PNG/JPEG, supports all needed operations, and is already a natural dependency for the renderer. ImageMagick is more powerful but adds an external binary dependency. Use Pillow for everything; only fall back to ImageMagick if a specific operation is needed (e.g., advanced color profile conversion).

**Post-processing pipeline (per image):**

```python
class PostProcessor:
    def process(self, raw_image_path: Path, card: Card) -> Path:
        img = Image.open(raw_image_path)

        # 1. Crop to target aspect ratio (1.37:1)
        img = self.crop_to_aspect_ratio(img, target_ratio=1.37)

        # 2. Resize to target dimensions
        #    For print: 661 x 483 pixels at 300 DPI (art box size)
        #    Generate larger (e.g., 1322 x 966) for quality headroom
        img = self.resize(img, target_width=1322, target_height=966)

        # 3. Color correction
        img = self.auto_levels(img)          # Normalize brightness/contrast
        img = self.adjust_saturation(img)    # Slight boost if undersaturated

        # 4. Sharpening (resize can soften)
        img = self.sharpen(img, amount=0.3)  # Gentle unsharp mask

        # 5. Save processed version
        processed_path = self.get_processed_path(raw_image_path)
        img.save(processed_path, 'PNG', dpi=(300, 300))
        return processed_path

    def crop_to_aspect_ratio(self, img: Image, target_ratio: float) -> Image:
        """Center-crop to target aspect ratio."""
        current_ratio = img.width / img.height
        if current_ratio > target_ratio:
            # Too wide -- crop sides
            new_width = int(img.height * target_ratio)
            left = (img.width - new_width) // 2
            img = img.crop((left, 0, left + new_width, img.height))
        elif current_ratio < target_ratio:
            # Too tall -- crop top and bottom
            new_height = int(img.width / target_ratio)
            top = (img.height - new_height) // 2
            img = img.crop((0, top, img.width, top + new_height))
        return img
```

**Output file structure:**
```
output/sets/XYZ/art/
    raw/                    # Original, unmodified downloads
        042_goblin_firestarter_v1.png
        042_goblin_firestarter_v1_prompt.txt
        042_goblin_firestarter_v2.png          # Retry attempt
    processed/              # Cropped, resized, color-corrected
        042_goblin_firestarter.png             # Final approved version
    rejected/               # Moved here after rejection
        042_goblin_firestarter_v1.png
```

---

### 2B.5: Regeneration Workflow

**Cards enter the regeneration queue when:**
1. Automated quality scoring auto-rejects the image (and max auto-retries exhausted).
2. Human reviewer rejects the image in the HTML gallery.
3. Character consistency review flags the art as inconsistent.

**Regeneration queue data model:**
```json
{
  "regeneration_queue": [
    {
      "collector_number": "042",
      "card_name": "Goblin Firestarter",
      "reason": "human_reject",
      "rejection_notes": "Wrong creature type depicted -- shows a human instead of goblin",
      "previous_attempts": 2,
      "priority": "normal",
      "prompt_override": null,
      "style_notes": "Emphasize goblin features: green skin, large ears, mischievous expression"
    }
  ]
}
```

**Regeneration process:**
1. If `prompt_override` is set, use that instead of the default prompt.
2. If `style_notes` are provided, append them to the prompt.
3. If no overrides, regenerate with the same prompt (AI services are non-deterministic, so a retry may produce different results).
4. Increment attempt counter. After 5 total attempts for a single card, escalate to "requires manual intervention" (human edits the prompt or tries a different approach).

**CLI commands:**
```bash
python -m mtgai.art queue --set XYZ                       # Show regeneration queue
python -m mtgai.art reject --set XYZ --card 042 --reason "wrong creature type"
python -m mtgai.art regenerate --set XYZ                  # Process regeneration queue
python -m mtgai.art regenerate --set XYZ --card 042 --prompt "..."  # Override prompt
```

---

### 2B.6: HTML Gallery for Review

**Purpose**: Simple, static HTML page for human art review. No framework, no server needed -- just open the HTML file in a browser.

**Features:**
- Grid layout showing all cards with their generated art.
- Each card shows: art image, card name, collector number, type, current status, quality score.
- Filter buttons: by color, by rarity, by status (pending review / approved / rejected).
- Click on a card to see: full-size art, prompt used, all attempts (with version history), quality score breakdown.
- Approve/reject buttons that write back to the state file (via a tiny local Python HTTP server, or by generating a simple JSON file of decisions that gets imported).

**Implementation approach:**
- `gallery.py` reads all card data + art files + state and generates a single `gallery.html` file with inlined CSS/JS.
- Images referenced via relative file paths (not embedded -- keeps the HTML small).
- Filtering/sorting done in client-side JavaScript.
- Approve/reject UI writes a `review-decisions.json` file (simplest approach: the gallery page provides a "Copy decisions JSON" button; user pastes into a file; then `python -m mtgai.art apply-review --set XYZ` imports it). Alternatively, run a lightweight local HTTP handler.

**Gallery file:** `output/sets/<set-code>/art/gallery.html`

**V0 simplification**: For V0 (50 cards), the gallery can be a bare-bones grid. Full filtering and approval workflow added for V1.

---

### 2B.7: File Management

**Naming conventions:**
```
<collector_number>_<card_name_slug>_v<attempt>.<ext>

- collector_number: zero-padded to 3 digits (001, 042, 280)
- card_name_slug: lowercase, hyphens for spaces, alphanumeric only
  "Goblin Firestarter" -> "goblin-firestarter"
- attempt: integer starting at 1
- ext: png (always PNG for lossless quality)

Examples:
  001_plains_v1.png
  042_goblin-firestarter_v2.png
  280_elara-planeswalker_v1.png
```

**Directory structure:**
```
output/sets/<set-code>/
    art-direction/
        style-guide.md
        prompt-templates.md
        characters/
            <name_slug>_reference.png
            <name_slug>.json
    art/
        raw/                          # Unmodified downloads from AI service
            <naming-convention>.png
            <naming-convention>_prompt.txt
        processed/                    # Post-processed, ready for rendering
            <collector_number>_<card_name_slug>.png   # Final version only
        rejected/                     # Rejected art (kept for reference)
            <naming-convention>.png
        gallery.html                  # Review gallery
    art-generation-state.json         # Pipeline state (progress tracking)
```

**Versioning of art attempts:**
- Every raw attempt is kept (v1, v2, v3...).
- Only the approved version is copied to `processed/` (without the version suffix).
- Rejected versions are moved to `rejected/` for reference.
- The state file tracks which version was approved for each card.

**Storage estimates:**
- Each PNG at 1792x1024: ~3-5 MB.
- 280 cards x 2 attempts average x 4 MB = ~2.2 GB for raw art.
- Processed art (smaller): ~1.5 MB each, ~420 MB total.
- Total art storage: ~3 GB. Confirm disk space before starting batch generation.

**Binary file strategy (per master plan):**
- Art files are NOT version-controlled (in `.gitignore`).
- Only JSON state files and text prompts are version-controlled.
- Art lives in `output/` only.

---

## Phase 2C: Card Renderer

### 2C.1: Rendering Engine Selection

**Recommendation: Pillow (PIL/Pillow) as primary, with Cairo (pycairo) for advanced text layout.**

| Engine | Pros | Cons | Verdict |
|--------|------|------|---------|
| **Pillow** | Pure Python, widely used, simple API, handles images/fonts/drawing well, no external dependencies | Text layout is basic (no auto-wrapping, no rich text, no inline images in text), no vector graphics | Use for: image compositing, frame overlay, simple text, symbol placement |
| **Cairo (pycairo)** | Excellent text layout (with Pango), vector graphics, anti-aliased rendering, PDF output, precise typographic control | External dependency (C library), slightly more complex API, Windows install can be tricky | Use for: rules text layout, mana cost rendering, any text that needs precise positioning |
| **Wand (ImageMagick binding)** | Very powerful image manipulation, good text rendering | Heavy external dependency (ImageMagick), memory-hungry, slower | Overkill -- Pillow+Cairo covers everything needed |
| **ReportLab** | Excellent for PDF generation, CMYK support | Designed for documents, not card images. Would need a completely different approach | Not appropriate for pixel-based card rendering |
| **HTML/CSS + headless browser** | Easy layout, CSS handles text wrapping naturally | Slow (spawning browser), hard to control pixel-perfect output, CMYK conversion complex | Interesting for prototyping but not for production |
| **SVG + cairosvg** | Templates as SVG, render to PNG | Good for template-based approach, but complex for dynamic text sizing | Consider as alternative to pure Cairo |

**Recommended architecture:**
1. **Pillow** for image compositing: load frame template, overlay art, place symbols.
2. **Pango + Cairo** for all text rendering: card name, type line, rules text, flavor text, P/T, collector info. Pango provides proper text shaping, line wrapping, font fallback, and mixed formatting (bold, italic) in a single text block.
3. **Final output** via Pillow: compose all layers into the final card image, save as PNG with DPI metadata.

**Fallback**: If Cairo/Pango installation proves too problematic on Windows, use Pillow-only with a custom text layout engine (more code, but no external dependencies). This fallback requires implementing word wrapping, line spacing, and inline symbol placement manually.

**Module structure:**
```
mtgai/renderer/
    __init__.py
    card_renderer.py      # Main renderer -- orchestrates all components
    frame_manager.py      # Loads and manages frame templates
    text_engine.py        # Text layout and rendering (Cairo/Pango or Pillow fallback)
    symbol_renderer.py    # Mana symbols, tap, set symbol
    layout.py             # Card layout definitions (positions, sizes per frame type)
    print_export.py       # CMYK conversion, bleed, DPI, print-ready export
    card_back.py          # Custom card back renderer
```

---

### 2C.2: Frame Templates

**What are frame templates?**
Pre-made images that provide the card border, name bar, type bar, text box, and P/T box -- essentially everything except the art and text. The renderer composites art beneath the frame and places text on top.

**Required frame templates:**

| Frame Type | Used For | Color/Style |
|------------|----------|-------------|
| White | White cards | Pale gold/cream border |
| Blue | Blue cards | Silver-blue border |
| Black | Black cards | Dark grey/charcoal border |
| Red | Red cards | Deep red/orange border |
| Green | Green cards | Dark green border |
| Multicolor (Gold) | 2+ color cards | Gold border |
| Artifact | Colorless artifacts | Silver/grey border |
| Land | Land cards | Brown/tan border, no P/T box |
| Planeswalker | Planeswalkers | Special layout: loyalty abilities, starting loyalty |
| Saga | Saga enchantments (if used) | Vertical art, chapter markers |

**How to create/source frame templates:**

**Option A: Use existing open-source templates (recommended for V0)**
- **Proxyshop** (open source, Python): Has frame templates. Check licensing for derivative use.
- **Card Conjurer** (web-based, open source): Frame assets may be extractable.
- **Community resources**: Various fan-made MTG frame templates exist. Verify licensing.

**Option B: Create custom frames (recommended for V1+)**
- Design custom frames in a vector editor (Inkscape -- free).
- Export as PNG at 300 DPI with transparency (alpha channel) for the art window.
- Custom frames give the set a unique identity and avoid any licensing concerns.
- Frame design requirements:
  - Art window: transparent (alpha=0) so art composites beneath.
  - Name bar: semi-transparent or solid, with defined text placement area.
  - Text box: solid background (slight transparency optional for style).
  - P/T box: solid, defined position and size.
  - All borders and decorative elements are opaque.

**Frame template file format:**
- PNG with alpha channel (RGBA).
- 300 DPI, full card size with bleed (815 x 1110 pixels, or 69mm x 94mm).
- Stored in: `assets/frames/<frame_type>.png`.
- Accompanying JSON layout file: `assets/frames/<frame_type>_layout.json` defining text area bounding boxes (see 2C.3).

**Multicolor frame handling:**
- Cards with exactly 2 colors: use a hybrid frame (left half = color A, right half = color B). This requires generating hybrid frames or using a layered approach.
- Cards with 3+ colors: use the gold (multicolor) frame.
- Implementation: for 2-color hybrids, composite two single-color frames with a gradient mask.

---

### 2C.3: Text Layout Engine

This is the most complex component of the renderer. MTG cards have dense, precisely formatted text with multiple zones, font sizes, and inline symbols.

**Card layout definition (`layout.py`):**

Each frame type has an associated layout JSON defining bounding boxes for every text zone:

```json
{
  "frame_type": "standard",
  "card_size": {"width": 815, "height": 1110},
  "bleed": 36,
  "zones": {
    "art_window": {
      "x": 58, "y": 122, "width": 700, "height": 510
    },
    "card_name": {
      "x": 72, "y": 68, "width": 540, "height": 40,
      "font": "beleren_alternative",
      "font_size": 28,
      "color": "#000000",
      "alignment": "left",
      "vertical_alignment": "center"
    },
    "mana_cost": {
      "x": 620, "y": 68, "width": 160, "height": 40,
      "alignment": "right",
      "symbol_size": 28
    },
    "type_line": {
      "x": 72, "y": 648, "width": 600, "height": 34,
      "font": "beleren_alternative",
      "font_size": 22,
      "color": "#000000",
      "alignment": "left",
      "vertical_alignment": "center"
    },
    "set_symbol": {
      "x": 706, "y": 644, "width": 36, "height": 36,
      "alignment": "right"
    },
    "rules_text": {
      "x": 72, "y": 700, "width": 670, "height": 280,
      "font": "mplantin_alternative",
      "font_size": 22,
      "min_font_size": 14,
      "line_spacing": 1.2,
      "color": "#000000",
      "alignment": "left",
      "vertical_alignment": "top"
    },
    "flavor_text": {
      "x": 72, "y": null,
      "width": 670, "height": null,
      "font": "mplantin_alternative",
      "font_size": 20,
      "min_font_size": 14,
      "line_spacing": 1.15,
      "color": "#000000",
      "style": "italic",
      "alignment": "left"
    },
    "power_toughness": {
      "x": 668, "y": 1010, "width": 100, "height": 44,
      "font": "beleren_alternative",
      "font_size": 30,
      "color": "#000000",
      "alignment": "center",
      "vertical_alignment": "center"
    },
    "collector_info": {
      "x": 72, "y": 1060, "width": 670, "height": 24,
      "font": "mplantin_alternative",
      "font_size": 12,
      "color": "#FFFFFF",
      "alignment": "left"
    }
  }
}
```

**Note**: All pixel values above are approximate starting points for a 300 DPI card (815x1110 with bleed). Exact values must be calibrated against real MTG card layouts and adjusted based on the actual frame templates used.

#### Card Name Positioning and Font Sizing

```python
def render_card_name(self, card: Card, layout: dict) -> None:
    zone = layout["zones"]["card_name"]
    font = self.load_font(zone["font"], zone["font_size"])

    # Measure text width
    text_width = self.measure_text(card.name, font)

    # If name is too long, reduce font size (minimum: 70% of default)
    while text_width > zone["width"] and font.size > zone["font_size"] * 0.7:
        font = self.load_font(zone["font"], font.size - 1)
        text_width = self.measure_text(card.name, font)

    # If STILL too long after min font size, truncate is a last resort
    # (this should be flagged in Phase 1C validation)

    self.draw_text(card.name, zone, font)
```

#### Mana Cost Symbols (Right-Aligned, Variable Count)

Mana costs are rendered as a row of mana symbols, right-aligned in the mana cost zone.

```python
def render_mana_cost(self, card: Card, layout: dict) -> None:
    zone = layout["zones"]["mana_cost"]
    symbols = self.parse_mana_cost(card.mana_cost)
    # e.g., "{2}{U}{U}" -> ["2", "U", "U"]

    symbol_size = zone["symbol_size"]
    total_width = len(symbols) * (symbol_size + 2)  # 2px gap between symbols

    # Right-align: start from right edge of zone
    x = zone["x"] + zone["width"] - total_width
    y = zone["y"] + (zone["height"] - symbol_size) // 2

    for symbol in symbols:
        symbol_img = self.symbol_renderer.get_mana_symbol(symbol, symbol_size)
        self.canvas.paste(symbol_img, (x, y), symbol_img)  # Alpha composite
        x += symbol_size + 2
```

**Mana cost parsing:**
- Input format: `"{2}{U}{U}"` or `"{X}{R}{R}"`
- Split on `}{` boundaries.
- Each token maps to a symbol image (see 2C.4).
- Hybrid mana: `"{W/U}"` -- single symbol showing both colors.
- Phyrexian mana: `"{U/P}"` -- symbol with Phyrexian watermark.
- Generic: `"{1}"`, `"{2}"`, ... `"{15}"`, `"{X}"`.

#### Type Line with Set Symbol

```python
def render_type_line(self, card: Card, layout: dict) -> None:
    zone = layout["zones"]["type_line"]

    # Build type line text
    # Example: "Legendary Creature -- Goblin Warrior"
    type_text = card.type_line

    # Render text left-aligned
    font = self.load_font(zone["font"], zone["font_size"])
    self.draw_text(type_text, zone, font)

    # Render set symbol right-aligned in its own zone
    set_zone = layout["zones"]["set_symbol"]
    rarity_color = self.get_rarity_color(card.rarity)
    set_symbol = self.symbol_renderer.get_set_symbol(
        self.set_code, rarity_color, set_zone["width"]
    )
    self.canvas.paste(set_symbol, (set_zone["x"], set_zone["y"]), set_symbol)
```

**The em dash**: MTG type lines use an em dash (--) between card type and subtype. Ensure the font supports the em dash character (U+2014). If not, render with two hyphens.

#### Rules Text with Dynamic Font Sizing

This is the hardest text layout problem on the card. Rules text must:
- Word-wrap within the text box.
- Support inline mana symbols (e.g., "Pay {2}{B}: Target creature gets -1/-1").
- Support italic reminder text in parentheses.
- Support bold keyword abilities (optional -- many renderers skip this).
- Dynamically reduce font size if text overflows.
- Leave room for flavor text below.

**Approach:**

```python
def render_rules_and_flavor(self, card: Card, layout: dict) -> None:
    rules_zone = layout["zones"]["rules_text"]
    flavor_zone = layout["zones"]["flavor_text"]

    # Total available height for rules + flavor combined
    total_height = rules_zone["height"]
    if card.flavor_text:
        # Flavor text takes from the same vertical space
        # We'll calculate how to split it after measuring both

    # Parse rules text into segments
    segments = self.parse_rules_text(card.rules_text)
    # Returns: [
    #   {"type": "text", "content": "Pay ", "style": "normal"},
    #   {"type": "symbol", "content": "2"},
    #   {"type": "symbol", "content": "B"},
    #   {"type": "text", "content": ": Target creature gets -1/-1 until end of turn.", "style": "normal"},
    #   {"type": "newline"},  # Paragraph break (between abilities)
    #   {"type": "text", "content": "(Deathtouch)", "style": "italic"},  # Reminder text
    # ]

    # Try rendering at default font size
    font_size = rules_zone["font_size"]
    min_size = rules_zone["min_font_size"]

    while font_size >= min_size:
        rules_height = self.measure_rich_text_height(segments, rules_zone["width"], font_size)
        flavor_height = 0
        separator_height = 0

        if card.flavor_text:
            separator_height = 16  # Height of the flavor separator bar
            flavor_height = self.measure_text_height(
                card.flavor_text, rules_zone["width"], font_size - 2, italic=True
            )

        total_needed = rules_height + separator_height + flavor_height
        if total_needed <= total_height:
            break  # It fits
        font_size -= 1

    if font_size < min_size:
        # TEXT OVERFLOW -- flag this card (see 2C.7)
        font_size = min_size
        self.flag_overflow(card)

    # Render rules text
    y_cursor = rules_zone["y"]
    y_cursor = self.render_rich_text(segments, rules_zone["x"], y_cursor,
                                      rules_zone["width"], font_size)

    # Render flavor separator bar
    if card.flavor_text:
        y_cursor += 8  # Padding above separator
        self.draw_flavor_separator(rules_zone["x"] + 50, y_cursor,
                                    rules_zone["width"] - 100)
        y_cursor += separator_height

        # Render flavor text (italic)
        self.render_text_block(card.flavor_text, rules_zone["x"], y_cursor,
                               rules_zone["width"], font_size - 2,
                               italic=True, color=rules_zone["color"])
```

**Rich text parser (`parse_rules_text`):**
```python
def parse_rules_text(self, rules_text: str) -> list[dict]:
    """Parse MTG rules text into renderable segments.

    Handles:
    - Mana symbols: {W}, {U}, {B}, {R}, {G}, {C}, {1}-{20}, {X}
    - Tap symbol: {T}
    - Untap symbol: {Q}
    - Reminder text: (text in parentheses) -> italic
    - Paragraph breaks: \n between abilities
    - Loyalty costs: [+1], [-2], [0] for planeswalkers
    """
    segments = []
    i = 0
    in_reminder = False

    while i < len(rules_text):
        if rules_text[i] == '{':
            # Find closing brace
            end = rules_text.index('}', i)
            symbol = rules_text[i+1:end]
            segments.append({"type": "symbol", "content": symbol})
            i = end + 1
        elif rules_text[i] == '(':
            in_reminder = True
            segments.append({"type": "text", "content": "(", "style": "italic"})
            i += 1
        elif rules_text[i] == ')' and in_reminder:
            in_reminder = False
            segments.append({"type": "text", "content": ")", "style": "italic"})
            i += 1
        elif rules_text[i] == '\n':
            segments.append({"type": "newline"})
            i += 1
        else:
            # Collect normal text until next special character
            end = i
            while end < len(rules_text) and rules_text[end] not in '{(\n':
                if rules_text[end] == ')' and in_reminder:
                    break
                end += 1
            style = "italic" if in_reminder else "normal"
            segments.append({"type": "text", "content": rules_text[i:end], "style": style})
            i = end

    return segments
```

**Rich text rendering with inline symbols:**
```python
def render_rich_text(self, segments: list[dict], x: int, y: int,
                     max_width: int, font_size: int) -> int:
    """Render parsed segments with word wrapping and inline symbols.
    Returns the y position after the last line."""

    line_height = int(font_size * 1.3)
    cursor_x = x
    cursor_y = y
    symbol_size = int(font_size * 0.9)  # Symbols slightly smaller than text

    normal_font = self.load_font("mplantin_alt", font_size)
    italic_font = self.load_font("mplantin_alt_italic", font_size)

    for segment in segments:
        if segment["type"] == "newline":
            # Paragraph break -- extra spacing between abilities
            cursor_x = x
            cursor_y += int(line_height * 1.4)
            continue

        if segment["type"] == "symbol":
            # Check if symbol fits on current line
            if cursor_x + symbol_size > x + max_width:
                cursor_x = x
                cursor_y += line_height
            symbol_img = self.symbol_renderer.get_mana_symbol(
                segment["content"], symbol_size
            )
            self.canvas.paste(symbol_img, (cursor_x, cursor_y), symbol_img)
            cursor_x += symbol_size + 2
            continue

        # Text segment -- word wrap
        font = italic_font if segment.get("style") == "italic" else normal_font
        words = segment["content"].split(' ')

        for word in words:
            word_with_space = word + ' '
            word_width = self.measure_text(word_with_space, font)

            if cursor_x + word_width > x + max_width and cursor_x > x:
                # Wrap to next line
                cursor_x = x
                cursor_y += line_height

            self.draw.text((cursor_x, cursor_y), word_with_space,
                          font=font, fill="#000000")
            cursor_x += word_width

    return cursor_y + line_height
```

#### Flavor Text (Italic, Separator Bar)

- Rendered below rules text, in italic.
- Preceded by the **flavor separator bar**: a thin horizontal line centered in the text box, about 60% of the text box width, 1-2 pixels tall.
- Font size: 1-2pt smaller than rules text.
- If the card has no rules text, flavor text fills the entire text box (centered vertically).
- Attribution line (e.g., `-- Urza`) is right-aligned.

```python
def draw_flavor_separator(self, x: int, y: int, width: int) -> None:
    """Draw the thin horizontal line separating rules text from flavor text."""
    center_x = x + (self.text_box_width - width) // 2
    self.draw.line(
        [(center_x, y), (center_x + width, y)],
        fill="#000000", width=1
    )
```

#### Power/Toughness Box

```python
def render_power_toughness(self, card: Card, layout: dict) -> None:
    if card.power is None or card.toughness is None:
        return  # Non-creature cards, lands, etc.

    zone = layout["zones"]["power_toughness"]
    pt_text = f"{card.power}/{card.toughness}"
    font = self.load_font(zone["font"], zone["font_size"])

    # Center text in the P/T box
    text_width = self.measure_text(pt_text, font)
    text_x = zone["x"] + (zone["width"] - text_width) // 2
    text_y = zone["y"] + (zone["height"] - zone["font_size"]) // 2

    self.draw.text((text_x, text_y), pt_text, font=font, fill=zone["color"])
```

**Special cases:**
- `*/*` (variable P/T): Render the asterisks as-is.
- `1+*` (base + variable): Render as-is.
- Planeswalker loyalty: Rendered in the loyalty box (bottom right), similar positioning but different frame zone.

#### Collector Info Line

The bottom line of the card, in very small text:

```
042/280 U                                    XYZ * EN        AI Art Generator
[number/total] [rarity]    [set code] [star] [lang]         [artist credit]
```

```python
def render_collector_info(self, card: Card, layout: dict) -> None:
    zone = layout["zones"]["collector_info"]
    font = self.load_font(zone["font"], zone["font_size"])

    # Left side: collector number and rarity
    rarity_char = card.rarity[0].upper()  # C, U, R, M
    left_text = f"{card.collector_number}/{self.total_cards} {rarity_char}"

    # Center: set code and language
    center_text = f"{self.set_code} \u2605 EN"  # Star character

    # Right side: artist credit
    right_text = card.artist or "AI Art Generator"

    self.draw_text_left(left_text, zone, font)
    self.draw_text_center(center_text, zone, font)
    self.draw_text_right(right_text, zone, font)
```

---

### 2C.4: Symbol Rendering

**Mana symbols**: Pre-rendered circular icons with the standard MTG mana symbol designs.

**Symbol sources:**
- **Keyrune** (by Andrew Gioia): Open-source icon font for MTG set symbols. Available as SVG/font. https://keyrune.andrewgioia.com/
- **Mana** (by Andrew Gioia): Open-source icon font for mana symbols, tap symbol, and other MTG game symbols. https://mana.andrewgioia.com/
- Both are MIT-licensed and well-maintained.

**Symbol rendering approach:**

1. **Pre-render all symbols at multiple sizes**: At startup (or build time), render each symbol from the icon font to PNG at sizes: 16px, 20px, 24px, 28px, 32px, 36px. Cache in `assets/symbols/mana_<symbol>_<size>.png`.

2. **Symbol types to support:**
   - Colored mana: {W}, {U}, {B}, {R}, {G} -- each has a distinct background color and icon.
   - Colorless/generic: {C}, {0}-{20}, {X}, {Y}, {Z}.
   - Hybrid: {W/U}, {U/B}, {B/R}, {R/G}, {G/W}, etc. -- split circle, two colors.
   - Phyrexian: {W/P}, {U/P}, etc. -- mana symbol with Phyrexian overlay.
   - Tap/untap: {T}, {Q}.
   - Energy: {E} (if the set uses energy).
   - Snow: {S}.

3. **Rendering each symbol:**
```python
class SymbolRenderer:
    def __init__(self, symbol_font_path: str, cache_dir: str):
        self.cache = {}  # (symbol, size) -> PIL Image

    def get_mana_symbol(self, symbol: str, size: int) -> Image:
        """Get a mana symbol as a PIL Image with transparency."""
        cache_key = (symbol, size)
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Render from SVG or icon font
        img = self.render_symbol(symbol, size)
        self.cache[cache_key] = img
        return img

    def render_symbol(self, symbol: str, size: int) -> Image:
        """Render a single mana symbol."""
        # Create circular background
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Draw circle background with appropriate color
        bg_color = self.get_symbol_bg_color(symbol)
        draw.ellipse([0, 0, size-1, size-1], fill=bg_color, outline=(0, 0, 0, 255))

        # Draw the symbol character/icon centered
        icon = self.get_symbol_icon(symbol)
        # ... render icon centered in the circle

        return img

    def get_symbol_bg_color(self, symbol: str) -> tuple:
        return {
            'W': (248, 231, 185, 255),   # Warm off-white
            'U': (14, 104, 171, 255),     # Blue
            'B': (21, 11, 0, 255),        # Near-black
            'R': (211, 32, 42, 255),      # Red
            'G': (0, 115, 62, 255),       # Green
            'C': (204, 194, 193, 255),    # Colorless grey
        }.get(symbol, (204, 194, 193, 255))  # Default: grey for generic
```

**Set symbol with rarity coloring:**
- Common: black fill.
- Uncommon: silver (gradient or flat #8E8E8E).
- Rare: gold (#C6922A).
- Mythic Rare: orange-red (#D14D28, often with a gradient/glow effect).

```python
def get_set_symbol(self, set_code: str, rarity: str, size: int) -> Image:
    """Render the set symbol with rarity-appropriate coloring."""
    # Load set symbol SVG (custom designed for this set)
    base_svg = self.load_set_symbol_svg(set_code)

    rarity_colors = {
        'common': {'fill': '#000000'},
        'uncommon': {'fill': '#8E8E8E', 'stroke': '#5A5A5A'},
        'rare': {'fill': '#C6922A', 'stroke': '#8B6914'},
        'mythic': {'fill': '#D14D28', 'stroke': '#8B2500'},
    }

    colored_svg = self.apply_color(base_svg, rarity_colors[rarity])
    return self.svg_to_png(colored_svg, size)
```

**Set symbol design**: The set symbol is a custom piece of art (typically a simple icon/glyph) that represents the set. This should be designed during Phase 2A as part of the visual identity. Store as SVG in `assets/set-symbols/<set-code>.svg`.

---

### 2C.5: Print Specifications

**Target specifications** (verify against chosen printer from Phase 0B):

| Spec | Value | Notes |
|------|-------|-------|
| **DPI** | 300 | Minimum for print quality. Render at 300, export at 300. |
| **Color Space** | CMYK | Print uses CMYK, not RGB. Conversion required. |
| **Bleed** | 3mm (36 pixels at 300 DPI) | Extra image extending past the cut line. |
| **Card Size (trim)** | 63mm x 88mm (744 x 1039 pixels) | Final cut size. |
| **Card Size (with bleed)** | 69mm x 94mm (815 x 1110 pixels) | File size including bleed. |
| **File Format** | PNG or TIFF | PNG for lossless RGB, TIFF for CMYK. Check printer preference. |
| **Safe Zone** | 3mm inset from trim | Critical text/images must be at least 3mm inside the cut line. |

**Rendering pipeline for print:**

```python
class PrintExporter:
    def export_print_ready(self, card_image: Image, output_path: Path) -> None:
        """Convert a rendered card image to print-ready format."""

        # 1. Verify dimensions (should already be 815 x 1110 at this point)
        assert card_image.size == (815, 1110), f"Unexpected size: {card_image.size}"

        # 2. Verify DPI
        card_image.info['dpi'] = (300, 300)

        # 3. Convert RGB to CMYK
        #    Pillow can convert to CMYK, but for accurate conversion,
        #    use ICC profiles.
        cmyk_image = self.convert_to_cmyk(card_image)

        # 4. Save as TIFF (CMYK) or PNG (RGB -- some printers accept this)
        if self.printer_wants_cmyk:
            cmyk_image.save(output_path, 'TIFF', dpi=(300, 300),
                           compression='lzw')
        else:
            card_image.save(output_path, 'PNG', dpi=(300, 300))

    def convert_to_cmyk(self, rgb_image: Image) -> Image:
        """Convert RGB image to CMYK using ICC profile for accurate color."""
        # Option 1: Simple Pillow conversion (acceptable quality)
        cmyk = rgb_image.convert('CMYK')

        # Option 2: ICC profile-based conversion (better quality)
        # Requires: sRGB profile (input) and a CMYK profile (e.g., FOGRA39)
        # from PIL import ImageCms
        # srgb_profile = ImageCms.createProfile('sRGB')
        # cmyk_profile = ImageCms.getOpenProfile('assets/profiles/FOGRA39.icc')
        # transform = ImageCms.buildTransform(srgb_profile, cmyk_profile,
        #                                      'RGB', 'CMYK',
        #                                      renderingIntent=ImageCms.Intent.PERCEPTUAL)
        # cmyk = ImageCms.applyTransform(rgb_image, transform)

        return cmyk
```

**Bleed implementation in the rendering pipeline:**

The card is rendered at the full bleed size (815 x 1110) from the start. The frame templates include the bleed area. The art is placed to extend into the bleed zone (behind the frame border). Text and symbols stay within the safe zone.

```
|<-- 36px bleed -->|<-- 744px trim -->|<-- 36px bleed -->|
|                  |                  |                  |
|  Frame border extends into bleed   |                  |
|  Art extends behind frame border   |                  |
|  Text stays 36px inside trim edge  |                  |
```

**Dual output (screen + print):**
- **Screen resolution**: 744 x 1039 pixels, RGB, PNG, 72 DPI. Used for HTML gallery, digital review.
- **Print resolution**: 815 x 1110 pixels, CMYK, TIFF, 300 DPI. Used for print ordering.

Both versions generated in a single render pass (render at print resolution, then crop bleed and downscale for screen version).

---

### 2C.6: Custom Card Back

**Design requirements:**
1. Same dimensions as card front (815 x 1110 with bleed, 300 DPI).
2. Visually reminiscent of MTG card back (familiar shape/layout) but clearly distinct.
3. Custom set name and/or set symbol prominently displayed.
4. **Mandatory "Custom/AI-Generated" indicator**: Clear text stating this is not an official MTG product. Required both ethically and to avoid any trademark issues.
5. Color palette that complements the set's visual identity.
6. Symmetric design (card backs should look the same regardless of orientation -- you can't tell which way the card is facing from the back).

**Implementation approach:**

1. Design the card back as a static image (this is a one-time design task, not programmatic per card).
2. Create in a vector editor (Inkscape) or image editor (GIMP).
3. Export as PNG at 815 x 1110, 300 DPI.
4. Store at: `assets/card-back.png`.

**Card back elements:**
```
+------------------------------------------+
|                                          |
|          [Decorative border]             |
|                                          |
|              [Set Symbol]                |
|              (large, centered)           |
|                                          |
|            [Set Name]                    |
|                                          |
|         [Decorative pattern]             |
|         (subtle, fills background)       |
|                                          |
|     "Custom Set - AI Generated Art"      |
|     "Not an official MTG product"        |
|                                          |
|          [Decorative border]             |
|                                          |
+------------------------------------------+
```

**Print consideration**: The card back is the SAME for every card. The print service needs one card back file, applied to all cards. Verify with the printer whether they want separate back files per card or a single shared file.

---

### 2C.7: Text Overflow Handling

**Problem**: Some cards have a lot of rules text. If text doesn't fit in the text box even at minimum font size, we need a fallback strategy.

**Overflow detection:**

Text overflow is checked at two points:
1. **Phase 1C (generation time)**: The text overflow estimator in `mtgai.validation` predicts whether text will fit. Cards flagged here can have their text shortened by the LLM before art is even generated.
2. **Phase 2C (render time)**: The renderer performs exact measurement during layout. Even if the estimator said it would fit, actual rendering with the real font may differ.

**Overflow handling cascade:**

```python
def handle_text_overflow(self, card: Card, overflow_pixels: int) -> OverflowAction:
    """Determine what to do when text doesn't fit."""

    # Level 1: Reduce font size (already attempted in render_rules_and_flavor)
    # If we're here, font is already at minimum.

    # Level 2: Remove flavor text
    if card.flavor_text:
        return OverflowAction.REMOVE_FLAVOR_TEXT

    # Level 3: Abbreviate reminder text
    # "(This creature can't be blocked.)" -> "(Can't be blocked.)"
    if self.has_reminder_text(card.rules_text):
        return OverflowAction.SHORTEN_REMINDER_TEXT

    # Level 4: Remove reminder text entirely
    if self.has_reminder_text(card.rules_text):
        return OverflowAction.REMOVE_REMINDER_TEXT

    # Level 5: Flag for human edit
    return OverflowAction.FLAG_FOR_HUMAN

class OverflowAction(Enum):
    REMOVE_FLAVOR_TEXT = "remove_flavor"
    SHORTEN_REMINDER_TEXT = "shorten_reminder"
    REMOVE_REMINDER_TEXT = "remove_reminder"
    FLAG_FOR_HUMAN = "flag_human"
```

**Overflow logging:**
- Every overflow event is logged to `output/sets/<set-code>/renderer/overflow-report.json`.
- Includes: card name, collector number, overflow action taken, original text, modified text (if applicable).
- Cards flagged for human edit appear in a report for manual review.

**Prevention (upstream):**
- The Phase 1C text overflow estimator should catch most overflow cases before rendering.
- The estimator uses a simplified font measurement (average character width x character count) with a safety margin.
- Cards with long rules text should be flagged during generation and the LLM asked to produce a shorter version.

---

### 2C.8: Test Plan

**Test categories:**

#### Frame Type Tests
Render one test card for each frame type and visually verify:

| Test Card | Frame | Validates |
|-----------|-------|-----------|
| Plains | Land (white) | Basic land frame, no P/T, no rules text, land art window |
| Island | Land (blue) | Different color land frame |
| Cancel (counterspell) | Blue spell | Standard frame, mana symbols in cost, moderate rules text |
| Lightning Bolt | Red spell | Minimal rules text, single mana symbol |
| Grizzly Bears | Green creature | P/T box, simple rules text, creature type line |
| Serra Angel | White creature | Multiple keywords (flying, vigilance), uncommon rarity set symbol |
| Nicol Bolas (multicolor) | Gold creature | Gold frame, 3+ color mana cost, legendary type line |
| Sol Ring | Artifact | Artifact frame, no color identity |
| Aether Vial | Artifact | Artifact with activated ability, counters text |
| Test Planeswalker | Planeswalker | Planeswalker frame, loyalty abilities, starting loyalty |
| Test Saga | Saga | Saga frame (if implemented), chapter abilities |

#### Text Overflow Edge Cases

| Test Case | Description | Expected Behavior |
|-----------|-------------|-------------------|
| Short text | "Flying" | Large font, centered, plenty of space |
| Medium text | 3 abilities, 2 lines each | Default font, comfortable fit |
| Long text | 5 abilities with reminder text | Reduced font, flavor text removed if needed |
| Maximum text | 8+ lines of abilities | Minimum font, no flavor, possibly truncated reminder text |
| Long card name | "Asmoranomardicadaistinaculdacar" (30 chars) | Name font reduced, still readable |
| Many mana symbols | "{W}{U}{B}{R}{G}{W}{U}" (7 symbols) | Mana symbols fit, don't overlap name |
| No rules text, long flavor | Just flavor text | Flavor fills text box, italic, centered vertically |
| Only P/T | Vanilla creature (no abilities) | Empty text box, just P/T |

#### Print Specification Compliance

| Check | Method | Pass Criteria |
|-------|--------|---------------|
| DPI | Read image metadata | Exactly 300 DPI |
| Dimensions | Check pixel size | 815 x 1110 (with bleed) |
| Bleed presence | Visual check | Content extends to image edge, no white borders |
| Safe zone | Overlay safe zone template | No critical text within 36px of edge |
| CMYK export | Check color mode of TIFF | Mode == 'CMYK' |
| File size | Check file size | Within printer's limits (typically < 50MB per image) |
| Color accuracy | Compare RGB and CMYK versions | No extreme color shifts (human visual check) |

#### Automated Test Suite (`tests/test_renderer.py`)

```python
class TestCardRenderer:
    def test_basic_land_renders(self):
        """A basic land card renders without errors."""
        card = make_test_card(type="land", name="Plains")
        result = renderer.render(card)
        assert result.image.size == (815, 1110)

    def test_creature_has_pt_box(self):
        """Creature card renders P/T in the correct zone."""
        card = make_test_card(type="creature", power="2", toughness="3")
        result = renderer.render(card)
        # Check that P/T zone has non-background pixels
        pt_region = result.image.crop(layout.zones["power_toughness"].as_tuple())
        assert not is_blank(pt_region)

    def test_noncreature_has_no_pt_box(self):
        """Non-creature card doesn't render P/T."""
        card = make_test_card(type="instant", power=None, toughness=None)
        result = renderer.render(card)
        # P/T zone should be part of the frame (no extra content)

    def test_mana_cost_symbols_count(self):
        """Correct number of mana symbols rendered."""
        card = make_test_card(mana_cost="{2}{U}{U}")
        result = renderer.render(card)
        # Verify 3 symbols rendered in mana cost zone

    def test_long_name_reduces_font(self):
        """Long card names get smaller font, but still render completely."""
        card = make_test_card(name="A" * 40)
        result = renderer.render(card)
        # Should not raise an error

    def test_text_overflow_removes_flavor(self):
        """When rules text is too long, flavor text is removed first."""
        card = make_test_card(
            rules_text="Very long rules text " * 20,
            flavor_text="Some flavor"
        )
        result = renderer.render(card)
        assert result.overflow_action == OverflowAction.REMOVE_FLAVOR_TEXT

    def test_print_export_cmyk(self):
        """Print export produces CMYK TIFF at 300 DPI."""
        card = make_test_card()
        result = renderer.render(card)
        export_path = exporter.export_print_ready(result.image, tmp_path / "test.tiff")
        exported = Image.open(export_path)
        assert exported.mode == 'CMYK'
        assert exported.info['dpi'] == (300, 300)

    def test_all_mana_symbols_render(self):
        """Every mana symbol type renders without error."""
        symbols = ['W', 'U', 'B', 'R', 'G', 'C', '0', '1', '2', '10', '15',
                   'X', 'T', 'Q', 'S', 'E', 'W/U', 'U/B', 'B/R', 'R/G', 'G/W',
                   'W/P', 'U/P', 'B/P', 'R/P', 'G/P']
        for symbol in symbols:
            img = symbol_renderer.get_mana_symbol(symbol, 32)
            assert img.size == (32, 32)
            assert img.mode == 'RGBA'

    def test_set_symbol_rarity_colors(self):
        """Set symbol renders in correct color per rarity."""
        for rarity in ['common', 'uncommon', 'rare', 'mythic']:
            img = symbol_renderer.get_set_symbol('XYZ', rarity, 36)
            assert img.size == (36, 36)
            # Check dominant color matches expected rarity color
```

**Physical print test:**
- After the renderer is functional, print ~10 cards at home on cardstock.
- Verify: text readability at actual card size, color appearance, proper sizing when cut, bleed margins work.
- This is a manual test but should be done before rendering the full set.

---

## Cross-Cutting Concerns & Master Plan Recommendations

### Scheduling: Should Phase 2A Start Earlier?

**Recommendation: Yes.** Phase 2A (Art Direction System) is completely independent of card data. It only needs the set's theme (name, setting, mood), which is decided before Phase 1 begins. 2A can and should run in parallel with Phase 1 -- this is already noted in the master plan's execution order diagram, and this plan confirms it is the right approach.

**Revised dependency for 2A:**
- Needs: Set theme/name (available from project inception).
- Does NOT need: Card data, card names, or any Phase 1 output.
- Start as soon as: Phase 0B (image generation research) and 0D/0E (prompt engineering) are done.

### Dependency Graph Verification

The master plan says 2A and 1 can run in parallel, but 2B needs card data from 1C. This is **correct**:
- **2A** (art direction) only needs the set theme. No card data needed. Can run parallel with Phase 1.
- **2B** (art generation) needs individual card descriptions to generate art prompts. **Hard dependency on 1C** (card generator must produce card data first).
- **2C** (card renderer) needs art from 2B and card data from 1C. Also has a **hard dependency on 0B** (print specs).

The dependency graph in the master plan is accurate. No changes needed.

### Dual Resolution Output

**Recommendation: Yes, produce both.**
- **Screen resolution** (744 x 1039, RGB, 72 DPI PNG): For the HTML gallery, digital review, sharing online, playtesting with printed proxies on a home printer.
- **Print resolution** (815 x 1110, CMYK, 300 DPI TIFF): For the print service order.

Both can be generated from a single render pass at print resolution. The screen version is derived by cropping the bleed area and downscaling. Minimal extra cost.

### Custom Card Back Timing

**Recommendation: Start in Phase 2A, finalize in 2C.**

The card back design is part of the set's visual identity (2A), but its technical implementation (print-ready export with bleed) belongs in 2C. Suggested split:
- **2A**: Design the card back concept (sketch, color scheme, text content, layout).
- **2C**: Produce the final print-ready card back file.

It does NOT need to be a Phase 0B deliverable. The print research in 0B should confirm card back file requirements (same DPI/bleed as front, any special requirements), but the actual design happens in Phase 2.

### Phase 2D: Set Symbol Design

**Recommendation: Not a separate phase.** The set symbol is a small deliverable that fits naturally within Phase 2A (it is part of the set's visual identity). Add it as a sub-task of 2A:
- Design a simple icon/glyph representing the set's theme.
- Create as SVG for scalability.
- Test rendering at set symbol size (tiny -- about 8-10mm on the card).
- Store at `assets/set-symbols/<set-code>.svg`.

### Art Generation Timeline

**Recommendation: Include a timeline estimate.**

Based on typical daily limits:
- **DALL-E 3 (ChatGPT Plus)**: ~40-80 images/day (varies by plan and usage). At 60/day, 280 cards = ~5 days of generation (plus retries, so plan for 7-8 days).
- **Midjourney Standard**: ~200 images/day. 280 cards = ~2 days (plus retries: 3-4 days).
- **Local models**: ~200-300 images/day on a decent GPU (2-5 min/image). 280 cards in 1-2 days.

**Budget 10 calendar days** for art generation, including retries, regeneration queue processing, and human review cycles. This is not continuous work -- it is largely automated with intermittent human review.

### CMYK Color Profile Targeting

**Recommendation: Generate art in RGB, convert to CMYK at export time.**

AI image generators output RGB. There is no way to make them generate in CMYK. The conversion is unavoidable.

To minimize lossy conversion impact:
1. Avoid highly saturated blues and greens in the style guide palette -- these shift the most in CMYK.
2. Use ICC profile-based conversion (not naive Pillow `.convert('CMYK')`). The FOGRA39 profile is standard for European offset printing.
3. Generate a "CMYK preview" image during post-processing (convert to CMYK and back to RGB) so human reviewers see approximately what the printed card will look like.
4. Test-print a batch of 10 cards early to calibrate color expectations.

### Proxy Mode (Low-Res, Text-Only)

**Recommendation: Yes, implement a proxy mode.**

A proxy mode is extremely useful for:
- **Early playtesting**: Before any art is generated, print text-only proxies for gameplay testing.
- **Renderer development**: Test layout logic without needing art assets.
- **Fast iteration**: Regenerating 280 full cards is slow; proxies are instant.

**Implementation:**
```python
class RenderMode(Enum):
    PROXY = "proxy"       # 72 DPI, no art, colored text box, minimal
    SCREEN = "screen"     # 72 DPI, with art, RGB, no bleed
    PRINT = "print"       # 300 DPI, with art, CMYK, with bleed

# In card_renderer.py:
def render(self, card: Card, mode: RenderMode = RenderMode.SCREEN) -> RenderedCard:
    if mode == RenderMode.PROXY:
        return self.render_proxy(card)  # Simple colored rectangle + text
    # ... full render
```

Proxy mode renders:
- A colored rectangle matching the card's color identity (white, blue, black, red, green, gold, grey).
- Card name at top.
- Mana cost symbols.
- Type line.
- Rules text (full layout).
- P/T.
- No art, no frame template, no set symbol, no collector info.
- Fast to generate: <0.1 seconds per card vs ~1 second for full render.

---

## Implementation Order Within Phase 2

```
Phase 2A (can start during Phase 1):
  2A.1  Style Guide Creation
  2A.2  Prompt Templates by Card Type
  2A.3  Character Consistency Workflow (identify recurring characters after 1C)
  2A.4  Artist Style Variation (define personas)
  2A.7  Aspect Ratio & Composition Guidelines
        + Set symbol design (sub-task)
        + Card back concept design
  2A.5  Quality Evaluation Rubric
  2A.6  Go/No-Go Gate (generate 20 samples, evaluate)

Phase 2B (requires card data from 1C):
  2B.7  File Management (set up directory structure first)
  2B.2  API/Service Integration (implement generator interface)
  2B.3  Quality Scoring Pipeline
  2B.4  Post-Processing Pipeline
  2B.1  Batch Generation Architecture (orchestrator, uses 2B.2-2B.4)
  2B.5  Regeneration Workflow
  2B.6  HTML Gallery for Review

Phase 2C (requires art from 2B, print specs from 0B):
  2C.1  Rendering Engine Selection & Setup (install Pillow, Cairo)
  2C.4  Symbol Rendering (mana symbols, set symbol -- can test independently)
  2C.2  Frame Templates (source or create)
  2C.3  Text Layout Engine (most complex -- build incrementally)
        - Start with proxy mode (2C cross-cutting)
        - Then card name + mana cost
        - Then type line + set symbol
        - Then rules text (hardest part)
        - Then flavor text + separator
        - Then P/T
        - Then collector info
  2C.7  Text Overflow Handling
  2C.6  Custom Card Back (finalize from 2A concept)
  2C.5  Print Export (CMYK, bleed, DPI)
  2C.8  Test Plan Execution (runs throughout, formal test pass at end)
```

**Estimated effort:**
- Phase 2A: 3-5 working days (mostly creative/prompt engineering work).
- Phase 2B: 5-7 working days for the pipeline code, plus 7-10 calendar days for actual art generation.
- Phase 2C: 8-12 working days (the text layout engine alone is 3-5 days).
- **Total Phase 2: ~3-4 weeks** of active development plus art generation time.
