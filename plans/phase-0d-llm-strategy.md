# Phase 0D: LLM & AI Strategy Research - Implementation Plan

## Objective

Define exactly how AI/LLMs are used throughout the MTG AI Set Creator pipeline. This phase produces a concrete strategy document (`research/llm-strategy.md`) covering model selection, prompting architecture, cost analysis, and the retry/validation loop. Every AI-driven phase (1B Mechanic Design, 1C Card Generation, 2A Art Direction) depends on the decisions made here.

---

## Quick Start (Context Reset)

**Prerequisites**: Anthropic and/or OpenAI API keys. Phase 0C card schema (or use the draft schema in this document).

**Read first**: This plan is self-contained. If Phase 0C is complete, import the Card model for JSON schema generation.

**Start with**: Section 9.1 Task 1 (API setup).

**You're done when**: `research/llm-strategy.md` is written per Section 8.1 structure, and all research tasks in Section 9.1 are complete.

---

## 1. Model Comparison

### 1.1 Candidates

| Model | Provider | Input $/1M tokens | Output $/1M tokens | Context Window | Structured Output | Batch API |
|-------|----------|-------------------|---------------------|----------------|-------------------|-----------|
| **Claude 4 Sonnet** | Anthropic | ~$3.00 | ~$15.00 | 200K | JSON mode via tool_use or raw JSON | Yes (50% discount, async) |
| **Claude 4 Opus** | Anthropic | ~$15.00 | ~$75.00 | 200K | Same as Sonnet | Yes (50% discount) |
| **Claude 3.5 Haiku** | Anthropic | ~$0.80 | ~$4.00 | 200K | Same | Yes (50% discount) |
| **GPT-4o** | OpenAI | ~$2.50 | ~$10.00 | 128K | JSON mode, function calling, Structured Outputs | Yes (50% discount, 24h) |
| **GPT-4o-mini** | OpenAI | ~$0.15 | ~$0.60 | 128K | Same as GPT-4o | Yes (50% discount) |
| **GPT-4.1** | OpenAI | ~$2.00 | ~$8.00 | 1M | Same as GPT-4o | Yes |
| **Local (Llama 3, Mistral)** | Self-hosted | $0 (GPU electricity) | $0 | 8K-128K | Via constrained decoding (Outlines, llama.cpp grammar) | N/A |

*Note: Prices are approximate as of early 2026. Verify current pricing before committing.*

### 1.2 Evaluation Criteria

| Criterion | Weight | Notes |
|-----------|--------|-------|
| **Output quality** (MTG rules text correctness) | Critical | The model must understand MTG rules grammar, color pie, and power level norms |
| **Structured output reliability** | Critical | Must produce valid JSON consistently. Parsing failures = wasted tokens |
| **Cost per set** | High | Must fit within ~$30 budget for LLM costs |
| **Context window** | Medium | Need room for system prompt + few-shot examples + set context + batch of cards |
| **Batch API availability** | Medium | 50% cost savings if we can tolerate async processing |
| **Latency** | Low | Not user-facing; batch processing is fine |

### 1.3 Recommendation Framework

Test each model during Phase 0E (Prompt Engineering Spike) on these axes:

1. **Generate 5 cards of varying complexity** (common creature, uncommon spell, rare legendary, mythic planeswalker, land) and score:
   - Rules text grammar correctness (0-5)
   - Mana cost / power level appropriateness (0-5)
   - Creativity / flavor (0-5)
   - JSON output validity (pass/fail)
2. **Measure tokens used** per card (input + output)
3. **Calculate cost** at current pricing

**Expected recommendation** (to be validated in 0E): Claude 4 Sonnet or GPT-4o for primary generation (best quality-to-cost ratio), with GPT-4o-mini or Haiku for bulk retry attempts on simpler cards (commons/uncommons).

### 1.4 Local Models Assessment

Local models (Llama 3 70B, Mistral Large, etc.) on an 8GB VRAM GPU:
- **8GB VRAM limits us to ~7B-13B parameter models** via quantization (Q4/Q5)
- **Quality is significantly lower** for specialized tasks like MTG rules text -- small models hallucinate keyword abilities, produce invalid mana costs, and don't understand color pie
- **Structured output is possible** via constrained decoding (llama.cpp grammars, Outlines), but adds complexity
- **Recommendation**: Not viable as primary generator. Potentially useful for simple tasks like slug generation, spell checking, or flavor text. Revisit if we get a beefier GPU.

---

## 2. Cost Analysis

### 2.1 Token Budget for a ~280-Card Set

#### Per-Card Token Estimates

| Component | Input Tokens | Output Tokens | Notes |
|-----------|-------------|---------------|-------|
| **System prompt** | ~2,000 | 0 | MTG rules, color pie reference, output format spec |
| **Few-shot examples** | ~1,500 | 0 | 3-5 example cards as reference (shared across batch) |
| **Set context** | ~500 | 0 | Set theme, mechanics, what's already generated |
| **Card slot specification** | ~200 | 0 | "Generate a white uncommon creature, CMC 3, for the WU fliers archetype" |
| **Generated card output** | 0 | ~400 | Full card JSON (~300-400 tokens for a typical card) |
| **Subtotal (1 card, 1 attempt)** | ~4,200 | ~400 | |

#### Batch Generation (5 cards per call)

| Component | Input Tokens | Output Tokens | Notes |
|-----------|-------------|---------------|-------|
| System prompt + few-shot | ~3,500 | 0 | Same as single, shared across batch |
| Set context | ~500 | 0 | Same |
| 5 card slot specifications | ~1,000 | 0 | 200 per card |
| 5 generated cards | 0 | ~2,000 | 400 per card |
| **Subtotal (5 cards, 1 attempt)** | ~5,000 | ~2,000 | |
| **Per card in batch** | ~1,000 | ~400 | ~4x cheaper on input vs single card |

#### Full Set Calculation

Assuming **batch generation of 5 cards per call** and a **25% retry rate** (cards that fail validation and need regeneration):

| Step | Calls | Input Tokens | Output Tokens | Notes |
|------|-------|-------------|---------------|-------|
| **Card generation** | 56 batches | 280,000 | 112,000 | 280 cards / 5 per batch |
| **Retries (25%)** | 14 batches | 70,000 | 28,000 | 70 failed cards / 5 per batch |
| **Retry with feedback** | -- | +35,000 | 0 | Validation errors added to retry prompts |
| **Mechanic design (1B)** | 5 calls | 25,000 | 10,000 | 2-4 mechanics, iterative |
| **Art prompt generation** | 56 batches | 168,000 | 56,000 | Separate call to generate image prompts (see Section 6) |
| **Total** | ~131 calls | **578,000** | **206,000** | |

#### Cost Estimates by Model

| Model | Input Cost | Output Cost | **Total** | With Batch API (50% off) |
|-------|-----------|-------------|-----------|--------------------------|
| **Claude 4 Sonnet** | $1.73 | $3.09 | **$4.82** | **$2.41** |
| **Claude 4 Opus** | $8.67 | $15.45 | **$24.12** | **$12.06** |
| **GPT-4o** | $1.45 | $2.06 | **$3.51** | **$1.76** |
| **GPT-4o-mini** | $0.09 | $0.12 | **$0.21** | **$0.11** |
| **GPT-4.1** | $1.16 | $1.65 | **$2.81** | **$1.40** |

### 2.2 Budget Assessment

**The $30 budget is very comfortable for Sonnet/GPT-4o class models.** Even without the batch API:
- Claude 4 Sonnet: ~$5 per set
- GPT-4o: ~$3.50 per set
- Multiple full retries of the entire set would still stay under $30

**Claude Opus at ~$24/set is feasible** but leaves little room for iteration. Use Opus only for quality-critical tasks (mythic rares, planeswalkers) if testing shows Sonnet is insufficient.

**The tiered approach**: Use Sonnet/GPT-4o for first generation. If retries are needed, try the same model once more with feedback. On third retry, either escalate to Opus or flag for human editing. This keeps costs low while maintaining a quality ceiling.

### 2.3 Cost Tracking

Implement cost tracking per card (already supported via `GenerationAttempt`):
```python
# After each API call, record actual token usage
attempt = GenerationAttempt(
    attempt_number=len(card.generation_attempts) + 1,
    timestamp=datetime.now(),
    prompt_used=prompt,
    model_used="claude-sonnet-4-20250514",
    success=True,
    # Add token tracking fields to GenerationAttempt model:
    input_tokens=response.usage.input_tokens,    # Proposed new field
    output_tokens=response.usage.output_tokens,   # Proposed new field
    cost_usd=calculated_cost,                      # Proposed new field
)
```

**Schema addition for 0C**: Add `input_tokens: int | None`, `output_tokens: int | None`, and `cost_usd: float | None` to `GenerationAttempt`. This lets us track actual spend vs budget in real time.

---

## 3. Prompting Architecture

### 3.1 Single Card vs Batch Generation

| Approach | Pros | Cons |
|----------|------|------|
| **Single card** | Simplest, max context per card, easy retry | ~4x more expensive (system prompt repeated per card) |
| **Batch of 5** | ~4x cheaper, cards can reference each other | Partial failures (1 bad card in a batch of 5), more complex parsing |
| **Batch of 10+** | Even cheaper | Output gets unreliable, harder to parse, one failure ruins the batch |

**Recommendation: Batch of 5 cards**, grouped by shared characteristics (same color, same rarity, or same archetype). This balances cost savings against output reliability.

**Partial failure handling**: If a batch of 5 returns 3 valid cards and 2 invalid ones, accept the 3 valid cards and retry only the 2 failures in a new call (single-card mode for retries to maximize quality).

### 3.2 Prompt Structure

```
[SYSTEM PROMPT]
  ├── Role: You are an expert MTG card designer...
  ├── MTG Rules Reference: Compact rules grammar guide
  │   ├── Keyword abilities list (current evergreen + set mechanics)
  │   ├── Rules text templates: "When ~ enters...", "Target creature gets..."
  │   ├── Color pie rules: What each color can/cannot do
  │   └── Power level guidelines per rarity
  ├── Output Format: JSON schema for Card model
  └── Constraints: What NOT to do (no silver-border, no un-set mechanics, etc.)

[USER PROMPT]
  ├── Set Context
  │   ├── Set name, theme, description
  │   ├── Set mechanics with reminder text
  │   └── Draft archetypes summary
  ├── Few-Shot Examples (3-5 cards)
  │   ├── Selected to match the requested card type/rarity
  │   └── Mix of real MTG cards and previously approved set cards
  ├── Already Generated Context (compressed)
  │   ├── List of card names already in the set (avoid duplicates)
  │   ├── Current color/rarity distribution (what's missing)
  │   └── Archetype coverage summary
  └── Card Slot Request
      ├── Color, rarity, card type, CMC range
      ├── Target archetype
      ├── Required mechanic (if any)
      └── Any specific constraints ("needs to be a removal spell", "signpost uncommon")
```

### 3.3 Few-Shot Example Selection

**Strategy**: Maintain a curated library of ~50 real MTG cards (from recent sets) organized by:
- Color (one per color)
- Rarity (common through mythic)
- Card type (creature, instant, sorcery, enchantment, artifact, planeswalker, land)
- Complexity (simple abilities vs complex multi-line text)

**Selection algorithm** for a given generation call:
1. Pick 1-2 examples matching the requested **rarity** (most important for power level calibration)
2. Pick 1 example matching the requested **color** (for color pie reference)
3. Pick 1 example matching the requested **card type** (for format reference)
4. If the card needs a **set mechanic**, include 1 example using a similar mechanic from a real set

Store examples in `research/few-shot-examples/` as JSON files. Each example should include the raw Scryfall data plus a `"design_notes"` field explaining why this card is a good example.

### 3.4 Structured Output Enforcement

**Option A: Tool Use / Function Calling** (recommended)
- Claude: Define a `generate_card` tool with the Card JSON schema as the parameter schema. The model is forced to produce valid JSON matching the schema.
- OpenAI: Use Structured Outputs (JSON Schema mode) which guarantees schema-valid JSON.
- **Advantage**: Guaranteed valid JSON structure. No parsing failures.
- **Disadvantage**: Minor -- the model might fill required fields with placeholder values to satisfy the schema.

**Option B: Raw JSON with Prompt Instructions**
- Tell the model to output JSON and parse the response.
- **Advantage**: Simpler API calls.
- **Disadvantage**: Occasional invalid JSON (missing commas, extra text around the JSON block).

**Recommendation**: Use **Tool Use / Function Calling** (Option A). The guaranteed JSON structure eliminates an entire class of failures and simplifies the pipeline code significantly. The Card Pydantic model can be directly converted to a JSON schema for the tool definition.

### 3.5 Context Window Management for Set-Wide Awareness

A full 280-card set's data would be ~100K+ tokens -- too large to include in every prompt. Strategy for maintaining set awareness:

**Compressed set summary** (~500 tokens) included in every generation call:
```json
{
  "cards_generated": 142,
  "cards_remaining": 138,
  "color_distribution": {"W": 28, "U": 26, "B": 30, "R": 27, "G": 31},
  "rarity_distribution": {"common": 80, "uncommon": 40, "rare": 18, "mythic": 4},
  "card_names": ["Lightning Bolt", "Serra Angel", ...],  // Full list for duplicate avoidance
  "archetype_coverage": {"WU": 12, "WB": 8, ...},
  "mechanic_usage": {"Delirium": 15, "Convoke": 8, ...}
}
```

**Card name list** is the most important piece -- it prevents the LLM from generating duplicate names. At ~2 tokens per name, 280 names is ~560 tokens. Affordable.

**Detailed context for related cards** (~200 tokens): When generating a card for the WU archetype, include the 2-3 most relevant already-generated WU cards as full JSON examples. This helps with mechanical coherence within an archetype.

---

## 4. Rules Text Enforcement

### 4.1 Validation Pipeline (Post-Generation)

Every generated card passes through this validation chain before being accepted:

```
Generated Card JSON
       |
       v
  [1] JSON Schema Validation (Pydantic model)
       |  - Does it match the Card schema?
       |  - Are required fields present?
       |  - Are enum values valid?
       v
  [2] Rules Text Grammar Check
       |  - MTG keyword abilities spelled correctly?
       |  - Standard templates used? ("When ~ enters" not "When this card enters")
       |  - Proper use of ~ as self-reference?
       |  - Ability words formatted correctly? (italicized ability word — effect)
       v
  [3] Mana Cost / CMC Consistency
       |  - Does the mana_cost field match the cmc field?
       |  - Are the colors field consistent with mana_cost?
       |  - Does color_identity include rules text color references?
       v
  [4] Color Pie Compliance
       |  - Does this card's abilities match its colors?
       |  - e.g., Red shouldn't have "Draw two cards" as a primary ability
       |  - Uses a rules table mapping ability types to allowed colors
       v
  [5] Power Level Check
       |  - P/T vs CMC appropriate for rarity?
       |  - Ability density appropriate for rarity?
       |  - Common cards follow New World Order (simple, no complex board states)?
       v
  [6] Text Length Check
       |  - Will the rules text + flavor text fit on the card?
       |  - Estimated via character count heuristic (exact rendering check in Phase 2C)
       v
  [7] Uniqueness Check
       |  - Is the name unique within the set?
       |  - Is the card mechanically distinct from other cards? (fuzzy matching on abilities)
       v
  ACCEPT or RETRY
```

### 4.2 Retry Loop with Feedback

```python
async def generate_card_with_retry(slot, set_context, max_retries=3):
    for attempt in range(1, max_retries + 1):
        card = await llm_generate_card(slot, set_context, feedback=feedback)
        validation_errors = validate_card(card)

        if not validation_errors:
            card.status = CardStatus.VALIDATED
            return card

        # Build feedback for next attempt
        feedback = format_validation_feedback(validation_errors)
        # Example feedback:
        # "Previous attempt failed validation:
        #  - Rules text uses 'this creature' instead of '~'
        #  - CMC 3 creature with 5/5 stats is too powerful for common
        #  Please fix these issues."

    # All retries exhausted -- flag for human review
    card.status = CardStatus.DRAFT
    card.design_notes = f"Failed validation after {max_retries} attempts: {validation_errors}"
    return card
```

**Key design decision**: Feedback is specific and actionable. Don't just say "validation failed" -- tell the model exactly what was wrong. This dramatically improves retry success rates.

### 4.3 Constrained Generation Techniques

Beyond post-hoc validation, we can constrain generation upfront:

1. **Type-line templates**: Provide a list of valid type lines (e.g., "Creature -- Human Wizard", "Legendary Enchantment -- Saga"). The LLM picks from the list or follows the pattern.
2. **Mana cost grammar**: Include a brief mana cost grammar in the system prompt: `"{X}" where X is a number or W/U/B/R/G/C. Examples: {1}{W}, {2}{B}{B}, {X}{R}{R}"`
3. **Keyword ability list**: Provide the exact list of evergreen keywords and set-specific mechanics. The LLM can reference only these.
4. **Power/toughness bounds**: Include a rarity-specific guideline: "Common creatures: P+T should not exceed CMC+3. Rare creatures: P+T can exceed CMC+4 with a drawback."

---

## 5. Rules Text Enforcement - Detailed Grammar

### 5.1 MTG Rules Text Patterns

Build a pattern library for validation. Key patterns:

```
# Self-reference
CORRECT: "When ~ enters the battlefield, ..."    (use ~ for card's own name)
WRONG:   "When this card enters the battlefield, ..."

# Triggered abilities
"When ~ enters, ..."
"Whenever ~ attacks, ..."
"At the beginning of your upkeep, ..."
"When ~ dies, ..."

# Activated abilities
"{cost}: {effect}"
"{T}: Add {G}."
"{2}{B}, Sacrifice a creature: ..."

# Keyword abilities (case-sensitive, specific formatting)
"Flying"
"First strike"
"Deathtouch"
"Trample"
"Vigilance"
"Haste"
"Lifelink"
"Reach"
"Menace"
"Ward {N}"
"Hexproof"

# Targeting
"Target creature gets +2/+2 until end of turn."
"Destroy target creature."
"Target player draws two cards."

# Modal spells
"Choose one --\n* Effect A\n* Effect B"
"Choose one or more --"

# Planeswalker abilities
"+1: Effect."
"-2: Effect."
"-7: Ultimate effect."
```

### 5.2 Validator Implementation Approach

The rules text validator should be **pattern-based, not a full parser**. A full MTG rules grammar parser is a massive undertaking (WotC's own rules engine is complex). Instead:

1. **Regex-based checks** for common mistakes (self-reference, keyword spelling, mana symbol format)
2. **Template matching** for ability structure (triggered, activated, static)
3. **Keyword dictionary** lookup (is this keyword real?)
4. **Heuristic scoring** rather than hard pass/fail for subjective checks (power level)

This is pragmatic: catch 90% of errors automatically, let human review catch the remaining 10%.

---

## 6. Art Prompt Generation

### 6.1 Should the card-design LLM also generate image prompts?

**Two-step approach recommended:**

| Approach | Pros | Cons |
|----------|------|------|
| **Same call** (card + art prompt together) | One API call, card context is fresh | Art prompts need different expertise, may reduce card quality |
| **Separate call** (generate card first, then art prompt) | Each call is focused, art prompt can reference final card data | Extra API cost (~$0.50 per set) |
| **Separate specialized prompt** | Best art quality | More complex pipeline |

**Recommendation: Separate call**, but cheap. After card generation is complete, run a batch pass to generate art prompts for all cards. This call can use a cheaper model (GPT-4o-mini or Haiku) since art prompt generation is less demanding than card design.

### 6.2 Art Prompt Architecture

```
[SYSTEM PROMPT]
  ├── Role: You are an art director for a fantasy card game
  ├── Style Guide: [From Phase 2A - color palette, mood, setting]
  ├── Output Format: JSON with "art_prompt" and "art_description" fields
  └── Constraints: No text in images, no card frames, art only

[USER PROMPT]
  ├── Card data (name, type, colors, oracle_text, flavor_text)
  ├── Card type visual guidelines:
  │   ├── Creature: "Show the creature in action, centered composition"
  │   ├── Instant/Sorcery: "Show the spell effect, dynamic energy"
  │   ├── Enchantment: "Show the enchantment's effect on the world"
  │   ├── Artifact: "Show the object, detailed, dramatic lighting"
  │   └── Land: "Landscape vista, panoramic, atmospheric"
  └── Style variation hint (optional): "In the style of [artist reference]"
```

### 6.3 Art Prompt Template

```
"A [art_style] illustration of [subject_description] for a fantasy card game.
[Scene/action description based on card abilities].
[Color palette and mood from set style guide].
[Composition guidelines based on card type].
No text, no borders, no card frame elements.
[Aspect ratio: 5:4 for standard card art box]."
```

---

## 7. Reproducibility

### 7.1 Temperature Settings

| Task | Temperature | Rationale |
|------|-------------|-----------|
| Card generation (first attempt) | 0.7 | Creative variety, reasonable adherence to constraints |
| Card generation (retry) | 0.5 | More focused, less likely to repeat errors |
| Mechanic design | 0.8 | Maximum creativity for novel mechanics |
| Art prompt generation | 0.6 | Creative but consistent with style guide |
| Validation/classification | 0.0 | Deterministic for reproducible checks |

### 7.2 Seed Strategies

- **Anthropic Claude**: Does not support seed parameter. Reproducibility via temperature=0 (deterministic mode) and saving the exact prompt.
- **OpenAI GPT-4o**: Supports `seed` parameter. Set a fixed seed per card slot (e.g., `seed = hash(set_code + collector_number)`) for reproducible first attempts.
- **In practice**: Perfect reproducibility is not critical. What matters is that we can **re-run with the same prompt** and get a similar (if not identical) result. This is why we save prompts in `GenerationAttempt`.

### 7.3 Prompt Versioning

All prompts are versioned artifacts:

```
research/
└── prompt-templates/
    ├── system-prompt-v1.md          # System prompt for card generation
    ├── system-prompt-v2.md          # Revised after 0E learnings
    ├── card-generation-v1.md        # User prompt template for card generation
    ├── art-prompt-v1.md             # User prompt template for art prompts
    ├── mechanic-design-v1.md        # User prompt template for mechanic design
    └── few-shot-examples/
        ├── common-creature.json
        ├── uncommon-spell.json
        ├── rare-legendary.json
        ├── mythic-planeswalker.json
        └── land.json
```

Each prompt template is a markdown file with:
- Version number and date
- Template with `{{placeholder}}` variables
- Change log (what changed from previous version and why)
- Performance notes (success rate in testing)

Every `GenerationAttempt` records the prompt version used, so we can correlate prompt changes with quality changes.

---

## 8. Output Specifications

### 8.1 Structure of `research/llm-strategy.md`

The final output of Phase 0D is a research document with these sections:

```markdown
# LLM Strategy for MTG AI Set Creator

## 1. Model Selection
- Primary model: [name, provider]
- Retry/cheap model: [name, provider]
- Rationale (link to 0E testing results)

## 2. Cost Budget
- Per-card cost estimate (input + output tokens)
- Per-set cost estimate (with retries)
- Budget allocation: generation vs art prompts vs mechanics
- Cost tracking implementation

## 3. Prompting Architecture
- System prompt (full text, versioned)
- User prompt template (full text, versioned)
- Few-shot example selection strategy
- Batch size decision and rationale

## 4. Structured Output
- Approach: Tool Use / Function Calling / Raw JSON
- JSON schema (derived from Card Pydantic model)
- Error handling for malformed output

## 5. Validation & Retry Pipeline
- Validation chain (ordered list of checks)
- Retry strategy (max attempts, feedback format)
- Escalation path (auto-retry -> human review)

## 6. Art Prompt Strategy
- Separate call vs combined
- Model choice for art prompts
- Prompt template

## 7. Reproducibility
- Temperature settings per task
- Seed strategy
- Prompt versioning approach

## 8. Context Window Management
- Set summary format
- Per-call token budget
- What to include/exclude

## 9. Open Questions & Risks
- What if the primary model's quality is insufficient?
- What if retry rates exceed 25%?
- How to handle model deprecation / pricing changes?
```

---

## 9. Research Execution Plan

### 9.1 Tasks (in order)

1. **API setup** (30 min): Set up Anthropic and OpenAI API keys. Verify access to Claude 4 Sonnet and GPT-4o. Create a simple test script that calls both APIs.

2. **System prompt drafting** (1 hour): Write the first version of the card generation system prompt. Include MTG rules reference, color pie summary, and output format specification. Store as `research/prompt-templates/system-prompt-v1.md`.

3. **Few-shot example curation** (1 hour): Pull 20-30 real MTG cards from Scryfall API across different colors, rarities, and types. Format as JSON matching our Card model. Store in `research/few-shot-examples/`.

4. **Model comparison** (2 hours): Generate the same 5 test cards with Claude 4 Sonnet, GPT-4o, and GPT-4o-mini. Score results. Document in a comparison table.

5. **Batch size testing** (1 hour): Test batch sizes of 1, 3, 5, and 10 cards per call. Measure quality and cost. Determine optimal batch size.

6. **Validation pipeline design** (1 hour): Define the validation chain. Write pseudocode for each validator. Determine which checks are hard-fail (retry) vs soft-fail (flag for review).

7. **Art prompt testing** (1 hour): Test art prompt generation with the card-design model vs a cheaper model. Compare prompt quality.

8. **Cost calculation** (30 min): Using actual token counts from testing, produce the final cost estimate for a 280-card set.

9. **Write `research/llm-strategy.md`** (1 hour): Compile all findings into the strategy document.

10. **Write `learnings/phase0d.md`** (30 min): Document what surprised us, what worked, anti-patterns.

**Estimated total: ~9 hours** (spread across 1-2 days)

### 9.2 Dependencies

- **Needs from 0C**: Card Pydantic model (to define JSON schema for structured output). If 0C isn't done yet, use a draft schema.
- **Feeds into 0E**: Prompt templates, model selection, batch strategy. 0E validates the decisions made here.
- **Feeds into 1B/1C**: Everything. The generation pipeline is built on top of this strategy.

---

## 10. Cross-Cutting Concerns & Master Plan Suggestions

### 10.1 Should the Card schema include fields not in the master plan?

**Yes -- specifically for the LLM pipeline, add these to the `GenerationAttempt` model** (defined in Phase 0C):

| Field | Type | Rationale |
|-------|------|-----------|
| `input_tokens` | `int \| None` | Track actual token usage per attempt for cost monitoring |
| `output_tokens` | `int \| None` | Same |
| `cost_usd` | `float \| None` | Calculated cost per attempt |
| `prompt_version` | `str \| None` | Which version of the prompt template was used (e.g., "system-v2") |

Also add to the `Card` model:
| Field | Type | Rationale |
|-------|------|-----------|
| `design_intent` | `str \| None` | The LLM's explanation of its design choices. Useful for review and iteration. |
| `complexity_score` | `int \| None` | Automated complexity rating (1-5). Useful for New World Order compliance at common. |

### 10.2 Is the pipeline status model sufficient?

For the LLM pipeline specifically, the six statuses are fine. The key insight is that **retry loops happen within a status transition, not as separate statuses**. A card in `draft` status might have 3 generation attempts -- but it doesn't move to `generation_failed` status. Instead, the attempts are tracked in `generation_attempts`, and the card either transitions to `validated` (success) or stays at `draft` with a `design_notes` flag (all retries exhausted).

**One addition worth considering**: a `generation_model` field on the Card itself (not just on attempts) recording which model produced the accepted version. This is useful for aggregate analysis: "Sonnet produced 70% of accepted cards on first try vs 50% for GPT-4o-mini."

### 10.3 Should 0C and 0D be merged?

**No, but the Card schema from 0C should be treated as a draft until 0D completes.** The LLM strategy (0D) will likely suggest:
- Adding token tracking fields to `GenerationAttempt` (confirmed above)
- Adding `design_intent` and `complexity_score` to `Card`
- Possibly adjusting field names to match what the LLM naturally produces

**Action**: 0C creates the initial schema. 0D may produce a small PR/update to the schema. This is a feature, not a problem -- the schema should evolve as we learn.

### 10.4 Should there be a shared config system?

**From the LLM perspective, absolutely.** The config system proposed in 0C (`MTGAIConfig`) should include:

```python
# LLM-specific config entries
llm_provider: str = "anthropic"
llm_model: str = "claude-sonnet-4-20250514"
llm_retry_model: str = "claude-sonnet-4-20250514"  # Model for retry attempts (could be cheaper)
llm_temperature: float = 0.7
llm_retry_temperature: float = 0.5
llm_max_retries: int = 3
llm_batch_size: int = 5
llm_art_prompt_model: str = "gpt-4o-mini"           # Cheaper model for art prompts

# API keys via environment variables
anthropic_api_key: str | None = None   # MTGAI_ANTHROPIC_API_KEY
openai_api_key: str | None = None      # MTGAI_OPENAI_API_KEY
```

This must be in the shared config (not scattered across generation code) because:
- Model selection affects cost, and cost tracking needs to know the model
- Temperature/retry settings are tuned during 0E and shouldn't be hardcoded
- API keys must come from environment, never from code

### 10.5 Token cost estimate: is $30 per set realistic?

**Yes, $30 is generous for current pricing.** Based on the detailed analysis in Section 2:

| Model | Cost per set (no batch API) | Cost per set (with batch API) |
|-------|---------------------------|-------------------------------|
| Claude 4 Sonnet | ~$5 | ~$2.50 |
| GPT-4o | ~$3.50 | ~$1.75 |
| Claude 4 Opus | ~$24 | ~$12 |

Even if we:
- Double the retry rate (50% instead of 25%): Sonnet cost ~$7
- Generate the entire set 3 times (major iteration): Sonnet cost ~$15
- Use Opus for all mythics/rares (~80 cards): adds ~$7

**Total worst case: ~$30.** The budget is realistic.

The bigger cost concern is **art generation**, which the master plan budgets at ~$20/mo subscription. If using API-based image generation instead (DALL-E 3 at ~$0.04-0.08 per image), 280 cards would cost $11-22 per set -- still within budget.

---

## 11. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM produces invalid MTG rules text consistently | High -- pipeline stalls | Invest heavily in few-shot examples. Validation feedback is very specific. Escalate to human edit after 3 retries. |
| Model pricing increases significantly | Medium -- budget pressure | Architecture is model-agnostic. Can swap models via config. Batch API provides 50% buffer. |
| Structured output mode produces shallow/templated cards | Medium -- quality | Test extensively in 0E. Tune temperature. Provide diverse few-shot examples. |
| Context window insufficient for set awareness | Medium -- duplicate cards, poor archetype coverage | Compressed set summary (500 tokens). Card name list for dedup. Tested in 0E. |
| Retry rate exceeds 50% | Medium -- cost and time | Indicates prompt issues, not model issues. Fix prompts before throwing money at retries. |
| Model deprecation (GPT-4o replaced, Claude version bumps) | Low -- short-term project | Pin model versions in config. Test new models before switching. |
