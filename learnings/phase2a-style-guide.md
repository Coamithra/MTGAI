# Phase 2A-1 & 2A-4 Learnings: Style Guide & Artist Personas

## What We Did (Manually)

Built the art style guide and artist style personas for ASD by:
1. Researching the source material (ASE RPG module) for visual DNA
2. Cross-referencing aesthetic lineage (Thundarr, Moebius, Dying Earth, 1E D&D art)
3. Making creative decisions about style direction, palette, per-color identity
4. Defining 8 "artist personas" mapped to card colors

## Key Learnings for Automation

### 1. Source Material Research is Essential (and LLM-viable)

The style guide can't be generated in a vacuum — it needs to understand the *source material's* existing visual identity. For ASD, we researched the ASE RPG module's art (Brian "Glad" Thomas, pen & ink, OSR aesthetic) and its acknowledged influences (Thundarr the Barbarian, Dying Earth, Moebius).

**Automation insight**: An LLM can do this research step. Given a `theme.json` with setting description, tone notes, and literary/media influences, an LLM (Opus or Sonnet) could:
- Identify the visual DNA from named influences
- Describe the aesthetic lineage
- Propose a coherent style direction

The LLM doesn't need to *see* the source art — it knows what "Moebius-influenced science fantasy" or "Thundarr the Barbarian aesthetic" means and can translate that into image generation prompt language.

### 2. Style Choice Maps to Image Gen Capabilities

We chose "stylized digital" over "painterly-realistic" or "retro-illustrated." This wasn't arbitrary — it maps to what current image generation models (Flux, DALL-E, Midjourney) do well:
- **Painterly-realistic**: Models can do this but it's the most common failure mode for "AI look" (over-smooth skin, symmetrical faces, generic compositions)
- **Retro-illustrated**: Hard to get consistent — models tend to drift between cartoon and realistic
- **Stylized digital**: The sweet spot — models handle bold shapes and saturated color well, and the slight stylization masks AI imperfections

**Automation insight**: The style choice should factor in the image generation model's strengths. A `style_selector` step could:
- Input: `theme.json` tone + chosen image gen model
- Output: recommended style direction with rationale
- This is a one-time decision per set, so Opus-level reasoning is worth it

### 3. Per-Color Personas Are a Natural Mapping

We mapped 8 artist personas directly to card colors. This works because:
- MTG colors already carry strong aesthetic associations (White = order, Blue = knowledge, etc.)
- The set's factions/themes map cleanly to colors (by design — that's how MTG works)
- No extra metadata needed — `card.colors` is already on every card JSON

**Automation insight**: An LLM generating style personas should receive:
- The set's per-color archetype descriptions (from skeleton/theme)
- The master palette and world-building
- Instructions to create distinct but cohesive sub-styles
- Specific prompt prefix/suffix language for the chosen image gen model

The output format should be structured (JSON or structured markdown) so the art prompt pipeline can consume it programmatically.

### 4. The Style Guide Is Really a Prompt Engineering Document

Everything in the style guide ultimately exists to inform image generation prompts. The sections about "mood," "lighting," "recurring motifs" — these are all things that need to become prompt fragments.

**Automation insight**: The style guide should be written in two layers:
1. **Human-readable narrative** (what we wrote) — for review and creative alignment
2. **Machine-readable prompt fragments** (not yet written) — the actual text snippets that get injected into image gen prompts

Phase 2A-2 (prompt templates) bridges these two layers. The templates should reference specific style guide sections and translate them into prompt language.

### 5. Dual-World Settings Need Explicit Environment Rules

ASD has a surface/dungeon duality that affects every visual decision (palette, lighting, atmosphere). We encoded this as rules ("surface = warm/dusty, dungeon = cool/eerie").

**Automation insight**: The LLM needs a way to know whether a card depicts a surface or dungeon scene. Options:
- Infer from card text/type (creatures with "dungeon" in flavor text, underground creature types like Morlock)
- Add an `environment` tag to card data (surface/dungeon/both)
- Let the art prompt LLM decide based on the card's full context
- The third option is simplest and probably good enough — the LLM reading the card can figure out if a Morlock Scavenger is underground

### 6. "Played Straight" Is a Critical Prompt Instruction

The hardest part of the ASE aesthetic is the deadpan tone — absurd subjects rendered seriously. Image gen models tend toward either:
- Making weird things look goofy/cartoonish
- Making everything look generically epic/dramatic

**Automation insight**: Prompts need explicit instructions like "photographic documentary tone," "matter-of-fact composition," "no exaggeration or comedy." This should be baked into the universal prompt prefix, not left to per-card generation.

### 7. Legendary Characters Need Pre-Defined Visual Identities

We described 8 legendary characters in detail. For automation, these descriptions need to be:
- Stored as structured data (not just prose in a style guide)
- Referenced when generating art for cards that depict these characters
- Consistent across multiple cards (e.g., if the Vizier appears in both his own card and in another card's background)

**Automation insight**: Phase 2A-3 (character consistency) should produce a `characters.json` with structured visual descriptions that the art prompt pipeline can look up by character name.

## What Worked Well

- **Researching before creating**: Looking at the ASE source art and its influences gave the style guide authentic grounding rather than generic fantasy defaults
- **Color-keyed personas**: Clean mapping that requires zero extra data plumbing
- **Two-world palette**: Surface warm / dungeon cool gives strong visual variety within a cohesive set

## What to Improve for Full Automation

- **Add machine-readable prompt fragments** alongside the narrative style guide
- **Structure the character descriptions** as JSON for programmatic lookup
- **Include negative prompts** (what to avoid) — these are as important as positive prompts for image gen
- **Test the style guide against real image gen** before locking it (that's 2A-5/2A-6)
- **Version the style guide** — it will likely need revision after seeing sample outputs

## Cost Estimate for Automated Style Guide Generation

- 1x Opus call to generate full style guide (style direction + palette + personas + characters): ~$0.15-0.25
- Total: ~$0.15-0.25 per set (trivial)
- Human review is approve/tweak, not creative brainstorm — the LLM can make the initial style direction choice too

## Input/Output Spec for Future `generate_style_guide()` Pipeline

**Inputs**:
- `theme.json` (setting, tone, influences, factions, legendary characters)
- `mechanics/approved.json` (mechanic flavor descriptions)
- `skeleton.json` (color/archetype distribution)
- Image generation model choice (from `research/tech-decisions.md`)
- Optional: human creative preferences (style direction, palette preferences)

**Outputs**:
- `art-direction/style-guide.md` (narrative, human-readable)
- `art-direction/style-config.json` (machine-readable: palette hex codes, per-color persona prompt prefixes, universal prompt prefix/suffix, negative prompts, composition rules, resolution specs)
- `art-direction/characters.json` (structured visual descriptions for named characters)
