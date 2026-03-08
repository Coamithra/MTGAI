# Phase 0E: Prompt Engineering Spike - Implementation Plan

## Objective

Validate that LLM-based card generation can produce Magic: The Gathering cards of sufficient quality to power the Phase 1C Card Generator. This is a **GO/NO-GO gate** before investing in the full pipeline.

**GO criteria**: The LLM can reliably produce cards with correct rules text grammar, appropriate power levels for their rarity, and creative names/flavor — with a tolerable retry rate (< 30% of cards needing regeneration).

**NO-GO triggers**: Rules text is consistently broken, power levels are wildly miscalibrated, or the retry rate exceeds 50% even after prompt iteration.

**Dependencies**: Phase 0D (LLM & AI Strategy Research) must be complete. We need model selection and cost estimates before running experiments.

**Budget ceiling**: All experiments in this phase should cost < $10 in LLM API calls total.

---

## Quick Start (Context Reset)

**Prerequisites**: Phase 0D complete (model selection, cost estimates). API keys configured. Budget ceiling: <$10 in API calls.

**Read first**: `research/llm-strategy.md` (Phase 0D output) for model choice and prompting architecture. This plan validates those decisions.

**Start with**: Section 2 (Prompt Template Development) to prepare prompts, then Section 4 (Experiments) to run them.

**You're done when**: GO/NO-GO decision made per Section 8 criteria, `BEST-SETTINGS.md` written per Section 7, and `learnings/phase0e.md` complete.

---

## 1. Test Matrix: 24 Cards to Generate

24 cards (slightly above the ~20 target) to ensure adequate coverage across every axis. Each card has a specific slot defined by rarity, color, type, and complexity tier.

### By Rarity
| Rarity | Count | Rationale |
|--------|-------|-----------|
| Common | 9 | Largest share of any set; must nail NWO simplicity |
| Uncommon | 6 | Where most set mechanics live; moderate complexity |
| Rare | 5 | Complex cards; multi-ability, build-arounds |
| Mythic | 3 | Splashy, exciting designs; hardest to balance |
| Basic Land | 1 | Flavor text only; tests a different generation mode |

### The 24-Card Test Matrix

| # | Name Slot | Color | Rarity | Type | Complexity | Notes |
|---|-----------|-------|--------|------|------------|-------|
| 1 | White Vanilla | W | Common | Creature | Vanilla | No abilities, just P/T. Tests restraint |
| 2 | White Keyword | W | Common | Creature | Keyword-only | Flying, lifelink, vigilance, etc. |
| 3 | White Removal | W | Uncommon | Instant | Single ability | "Exile target..." style. Tests rules text precision |
| 4 | Blue Cantrip | U | Common | Instant | Single ability | Draw + minor effect. Tests MTG draw templating |
| 5 | Blue Counter | U | Uncommon | Instant | Single ability | Counterspell variant. Tests stack interaction wording |
| 6 | Blue Card Draw | U | Rare | Sorcery | Multi-ability | Card selection/draw with choice. Tests modal wording |
| 7 | Black Removal | B | Common | Instant | Single ability | Destroy/damage creature. Tests targeting language |
| 8 | Black Recursion | B | Uncommon | Creature | Multi-ability | ETB + graveyard interaction. Tests trigger wording |
| 9 | Black Mythic | B | Mythic | Creature | Multi-ability | Legendary creature, 2-3 abilities. Tests legendary design |
| 10 | Red Burn | R | Common | Instant | Single ability | Direct damage. Tests damage assignment wording |
| 11 | Red Aggro | R | Common | Creature | Keyword-only | Haste + maybe another keyword. Tests aggressive statlines |
| 12 | Red Mythic | R | Mythic | Creature | Multi-ability | Dragon or similar. Tests splashy mythic design |
| 13 | Green Ramp | G | Common | Sorcery | Single ability | Search for land. Tests "search your library" templating |
| 14 | Green Fatty | G | Common | Creature | Keyword-only | Big body with trample. Tests common P/T ceiling |
| 15 | Green Enchantment | G | Uncommon | Enchantment | Multi-ability | Aura or static enchantment. Tests enchantment templating |
| 16 | Multicolor WU | WU | Uncommon | Creature | Multi-ability | Azorius archetype signpost. Tests gold card design |
| 17 | Multicolor BR | BR | Rare | Creature | Multi-ability | Rakdos build-around. Tests two-color identity |
| 18 | Colorless Artifact | C | Common | Artifact | Single ability | Equipment or mana rock. Tests artifact templating |
| 19 | Artifact Rare | C | Rare | Artifact | Multi-ability | Complex artifact with activated abilities. Tests tap/cost syntax |
| 20 | Planeswalker | WB | Mythic | Planeswalker | Multi-ability | 3 loyalty abilities. Tests planeswalker templating |
| 21 | Modal Spell | R | Rare | Instant | Modal | "Choose one" or "Choose two" spell. Tests modal formatting |
| 22 | Saga | G | Rare | Enchantment - Saga | Multi-ability | Chapter abilities. Tests Saga templating |
| 23 | Land Utility | C | Uncommon | Land | Single ability | Nonbasic with activated ability. Tests land templating |
| 24 | Basic Land | - | Basic Land | Basic Land - Forest | Flavor text only | Tests basic land generation (name + flavor text only) |

### Coverage Verification

**By color**: W(3), U(3), B(3), R(4), G(4), Multicolor(2), Colorless(4), Land(1) — every color has 3+.

**By type**: Creature(11), Instant(5), Sorcery(2), Enchantment(2), Artifact(2), Planeswalker(1), Land(1) — all major types covered.

**By complexity**: Vanilla(1), Keyword-only(3), Single ability(7), Multi-ability(10), Modal(1), Saga(1), Planeswalker(1) — weighted toward harder cases since those are the real risk.

---

## 2. Prompt Template Development

### 2.1 System Prompt: MTG Design Expert

This is the foundation prompt used for all generation calls.

```
You are a senior Magic: The Gathering card designer with 20 years of experience at Wizards of the Coast. You have deep expertise in:

1. **Rules text grammar**: You write rules text exactly as it appears on printed MTG cards. You follow Oracle text conventions precisely.

2. **Color pie philosophy**: You understand what each color can and cannot do:
   - WHITE: Small creatures, lifegain, exile-based removal, enchantments, tokens, protection, taxing effects, board wipes, first strike, flying, vigilance, lifelink
   - BLUE: Card draw, counterspells, bounce, flying creatures, mill, copy effects, library manipulation, flash, hexproof
   - BLACK: Creature destruction, discard, graveyard recursion, life payment for power, deathtouch, menace, lifelink (on vampires/demons)
   - RED: Direct damage, haste, temporary power boosts, artifact destruction, impulse draw, first strike, trample (on big creatures), menace
   - GREEN: Big creatures, mana ramp, fight/bite effects, trample, reach, creature tutoring, enchantment/artifact removal, +1/+1 counters

3. **New World Order (NWO)**: Commons must be simple. Complex abilities belong at uncommon+. Board complexity at common should be minimal.

4. **Power level by rarity**:
   - Common: Simple, efficient, bread-and-butter effects. Creatures are fairly statted (no better than +1 total P/T above the "vanilla test" for their CMC)
   - Uncommon: More complex, can have 1-2 abilities, signpost cards for draft archetypes. Slightly above-rate or with meaningful upside
   - Rare: Powerful build-around cards, complex interactions, 2-3 abilities. Can be significantly above-rate with conditions or setup costs
   - Mythic: Splashy, game-changing effects. Legendary creatures, planeswalkers, "wow factor" cards. High power but usually high mana cost

5. **Rules text formatting conventions**:
   - Use ~ as a placeholder for the card's name in rules text
   - Keyword abilities are lowercase: flying, trample, haste, deathtouch, lifelink, vigilance, menace, reach, first strike, double strike, hexproof, flash, defender, indestructible
   - Triggered abilities start with "When", "Whenever", or "At"
   - "When ~ enters" (NOT "enters the battlefield" — this was updated in 2023)
   - "Target creature gets +X/+Y until end of turn." (period at end)
   - Activated abilities use the format: "[Cost]: [Effect]." with a colon after cost
   - Tap symbol is {T}, mana symbols are {W}, {U}, {B}, {R}, {G}, {C}, generic is {1}, {2}, etc.
   - Loyalty abilities on planeswalkers: [+N], [-N], [0]
   - Saga chapters: "I — ", "II — ", "III — " (Roman numerals, em dash)
   - "Choose one —" and "Choose two —" for modal spells (em dash after)
   - Reminder text in parentheses: *(Reminder text goes here.)*

6. **Card naming**: Names should be 1-4 words, evocative, and fit the fantasy genre. Avoid real-world references. Avoid names of existing MTG cards.

You output cards ONLY in the JSON format specified in the user prompt. You never add commentary outside the JSON structure.
```

### 2.2 Single-Card Generation Prompt

```
Generate a single Magic: The Gathering card for a custom set with the following constraints:

**Set context**: {set_theme_description}
**Set mechanics**: {mechanics_list}

**Card requirements**:
- Color: {color}
- Rarity: {rarity}
- Type: {type}
- Complexity: {complexity_description}
- Role: {role_description}

{few_shot_section}

Output the card as a JSON object with exactly these fields:
{
  "name": "Card Name",
  "mana_cost": "{2}{W}",
  "type_line": "Creature — Human Soldier",
  "rules_text": "First strike\nWhen ~ enters, create a 1/1 white Soldier creature token.",
  "flavor_text": "\"Flavor quote here.\" —Attribution",
  "power": "3",
  "toughness": "2",
  "rarity": "uncommon",
  "color_identity": ["W"]
}

Rules for the JSON:
- power/toughness: Only include for creatures. Use strings (e.g., "3", "*").
- mana_cost: Use {W}{U}{B}{R}{G}{C}{1}{2}{X} notation. Omit for lands.
- rules_text: Use \n for line breaks between abilities. Use ~ for card name.
- flavor_text: Optional. Use escaped quotes for speech. Omit for complex cards where rules text fills the card.
- color_identity: Array of color letters. Empty array [] for colorless. Use all colors in the mana cost plus any color indicators.
```

### 2.3 Batch Generation Prompt

```
Generate {batch_size} Magic: The Gathering cards for a custom set. Each card must fill a specific slot.

**Set context**: {set_theme_description}
**Set mechanics**: {mechanics_list}

**Cards already in the set** (for context — do NOT duplicate these):
{existing_cards_summary}

**Slots to fill**:
{slot_list_with_requirements}

{few_shot_section}

Output as a JSON array of card objects. Each card must have exactly these fields:
[
  {
    "slot": 1,
    "name": "...",
    "mana_cost": "...",
    "type_line": "...",
    "rules_text": "...",
    "flavor_text": "...",
    "power": "...",
    "toughness": "...",
    "rarity": "...",
    "color_identity": [...]
  },
  ...
]

Generate all {batch_size} cards. Every slot must be filled.
```

### 2.4 Few-Shot Examples

Use real MTG cards as examples. The examples should be recent (post-2023 templating) to ensure correct rules text grammar (e.g., "When ~ enters" not "When ~ enters the battlefield").

**Recommended example cards by complexity tier:**

| Tier | Example Cards (use Scryfall data) |
|------|----------------------------------|
| Vanilla | Grizzly Bears, Sanctuary Cat, Pillarfield Ox |
| Keyword-only | Inspiring Overseer, Raffine's Informant, Monastery Swiftspear |
| Single ability | Murder, Shock, Rampant Growth, Negate |
| Multi-ability | Sheoldred the Apocalypse, Atraxa Grand Unifier |
| Modal | Prismari Command, Boros Charm |
| Planeswalker | The Wandering Emperor, Liliana of the Veil (recent Oracle text) |
| Saga | The Eldest Reborn, Urza's Saga |

**Format each example like this:**

```
**Example — {complexity tier}:**
{
  "name": "Inspiring Overseer",
  "mana_cost": "{2}{W}",
  "type_line": "Creature — Angel",
  "rules_text": "Flying\nWhen ~ enters, you gain 1 life and draw a card.",
  "flavor_text": "\"Every battlefield has a hero waiting for permission to rise.\"",
  "power": "2",
  "toughness": "1",
  "rarity": "common",
  "color_identity": ["W"]
}
```

### 2.5 Set Context Injection Strategy

The context window problem: by the time we're generating card 200+, the "set so far" is far too large to include verbatim. Strategy:

**Tier 1 — Always include (fits in any context window):**
- Set theme (2-3 sentences)
- Set mechanics with reminder text (5-10 lines)
- Color pair archetype summary (10 lines, one per pair)

**Tier 2 — Include when generating within a color/archetype:**
- Summary of cards already in that color (names + mana costs + one-line description)
- Summary of cards in the relevant archetype pair
- Estimated size: ~50-100 tokens per card = ~2,000-4,000 tokens for a full color

**Tier 3 — Include as compressed summary:**
- Full set statistics: "White has 12/15 commons filled, 4/5 uncommons, needs more 2-drops"
- Names-only list of all cards generated so far (for deduplication)
- Estimated size: ~2,000 tokens for a full 280-card set

**Context injection template:**

```
**Set: {set_name}** — {theme_description}

**Set Mechanics:**
{mechanic_name_1} — {reminder_text}
{mechanic_name_2} — {reminder_text}

**Draft Archetypes:**
WU: {archetype_description}
WB: {archetype_description}
... (all 10)

**Current {color} cards:**
{name} ({mana_cost}) — {one_line_summary}
{name} ({mana_cost}) — {one_line_summary}
...

**Set statistics:**
- {color}: {x}/{y} commons, {x}/{y} uncommons, needs {gap_description}
- Overall: {total_generated}/{total_target} cards complete

**Names used (do not duplicate):**
{comma_separated_list_of_all_card_names}
```

---

## 3. Evaluation Criteria (Scoring Rubric)

Each generated card is scored on a 1-5 scale across 7 dimensions. A card is considered **acceptable** if it scores 3+ on every dimension and averages 3.5+ overall.

| Dimension | 1 (Fail) | 3 (Acceptable) | 5 (Excellent) |
|-----------|----------|-----------------|---------------|
| **Rules Text Correctness** | Broken syntax, impossible effects, wrong templates | Minor formatting issues, slightly awkward phrasing but functionally correct | Perfect Oracle text, indistinguishable from a real card |
| **Mana Cost Appropriateness** | Wildly over/undercosted (e.g., {1}{W} for a 5/5 flyer) | Slightly pushed or conservative but within 1 mana of correct | Precisely costed — matches what WotC would print |
| **Power Level for Rarity** | Common with mythic-level complexity or power; mythic that's draft chaff | Slightly above or below expected power band | Dead-on for the rarity — commons are simple, mythics are splashy |
| **Flavor Text Quality** | Nonsensical, generic ("Magic is powerful"), or cringe | Serviceable, fits the card, doesn't distract | Evocative, memorable, adds world-building depth |
| **Name Creativity** | Generic ("Fire Blast"), existing MTG name, or real-world reference | Reasonable fantasy name, fits the card type | Evocative, unique, immediately makes you want to read the card |
| **Type Line Correctness** | Wrong supertypes, nonsensical creature types, format errors | Correct format, reasonable types but maybe not ideal choices | Perfect — correct supertypes, creature types match color pie and flavor |
| **Color Pie Compliance** | Hard break (e.g., red counterspell, green card draw without creatures) | Soft bend — slightly outside normal but defensible | Perfectly within the color's slice of the pie |

### Aggregate Scoring

- **Per-card score**: Average of all 7 dimensions
- **Per-experiment score**: Average across all 24 cards
- **GO threshold**: Per-experiment average >= 3.5, with no more than 2 cards scoring below 3.0 on any single dimension
- **NO-GO threshold**: Per-experiment average < 3.0, or more than 5 cards with critical failures (score of 1 on Rules Text Correctness or Color Pie Compliance)

---

## 4. Experiments to Run

### Experiment 1: Temperature Sweep

**Goal**: Find the optimal temperature for balancing creativity vs. correctness.

| Setting | Temperature | Cards | Expectation |
|---------|-------------|-------|-------------|
| 1A | 0.3 | All 24 | Conservative, correct, possibly boring names/flavor |
| 1B | 0.5 | All 24 | Sweet spot hypothesis — correct with some creativity |
| 1C | 0.7 | All 24 | More creative but possibly more rules errors |
| 1D | 1.0 | All 24 | Most creative but likely highest error rate |

**Evaluation**: Score all 96 generated cards (24 x 4 temperatures). Plot correctness dimensions vs. creativity dimensions by temperature. Identify the knee of the curve.

**Cost estimate**: ~$2-4 depending on model (4 full runs of 24 cards).

### Experiment 2: Few-Shot Count

**Goal**: Determine how many examples are needed for reliable generation.

| Setting | Examples | Cards | Notes |
|---------|----------|-------|-------|
| 2A | 0 (zero-shot) | All 24 | Baseline — system prompt only |
| 2B | 1 example per card | All 24 | One example matching the complexity tier |
| 2C | 3 examples per card | All 24 | Mix of complexity tiers, including one matching |
| 2D | 5 examples per card | All 24 | Full spread; test for diminishing returns |

**Use the best temperature from Experiment 1.**

**Evaluation**: Score all 96 cards. Compare rules text correctness and type line correctness specifically — these are the dimensions most likely to benefit from examples.

**Cost estimate**: ~$2-5 (more examples = more input tokens).

### Experiment 3: Single vs. Batch Generation

**Goal**: Compare quality and cost when generating one card at a time vs. batches.

| Setting | Batch Size | Total Calls | Notes |
|---------|------------|-------------|-------|
| 3A | 1 (single) | 24 | Maximum context per card, highest cost |
| 3B | 5 | 5 (4x5 + 1x4) | Moderate batch, still manageable |
| 3C | 10 | 3 (2x10 + 1x4) | Larger batch, test for quality degradation |
| 3D | 24 (all at once) | 1 | Single massive call, cheapest but likely worst |

**Use the best temperature and few-shot count from Experiments 1-2.**

**Evaluation**: Compare per-card quality scores by batch size. Track cost per card (input + output tokens). Look for specific failure modes in large batches (duplicate names, converging designs, dropped cards).

**Cost estimate**: ~$2-3.

### Experiment 4: JSON Mode vs. Free Text + Parsing

**Goal**: Determine the most reliable output format.

| Setting | Output Mode | Notes |
|---------|-------------|-------|
| 4A | JSON mode / structured output (if model supports it) | Use the model's built-in JSON enforcement |
| 4B | Prompt-only JSON (no mode enforcement) | Rely on prompt instructions alone |
| 4C | Free text + post-parse | Ask for a specific text format, parse into JSON after |

**Use best settings from Experiments 1-3.**

**Evaluation**: Track parse success rate (did we get valid JSON?), field completeness (were all fields present?), and card quality scores. Free text may allow the model to be more "natural" but risks format inconsistency.

**Cost estimate**: ~$1-2.

### Experiment 5: Context Window Strategies for Set Awareness

**Goal**: Test how well the LLM uses set context to avoid duplicates and maintain coherence.

| Setting | Context Strategy | Notes |
|---------|-----------------|-------|
| 5A | No context | Generate in isolation — how many duplicates/conflicts arise? |
| 5B | Names-only list | Just card names of previously generated cards |
| 5C | Compressed summary (Tier 2+3 from section 2.5) | Names, mana costs, one-liners, plus set stats |
| 5D | Full card data for same color | Complete JSON of all cards in the same color |

**Process**: Generate 10 cards first (no context), then generate the next 14 using each context strategy.

**Evaluation**: Count duplicate names, duplicate effects, archetype coverage gaps, and overall coherence of the mini-set.

**Cost estimate**: ~$2-3.

### Experiment 6: Validation-Retry Loop Prototype

**Goal**: Test whether feeding validation errors back to the LLM improves card quality on retry.

| Setting | Description | Notes |
|---------|------------|-------|
| 6A | Generate → validate → show errors → regenerate (1 retry) | Test if retry fixes the issue |
| 6B | Generate → validate → show errors → regenerate (up to 3 retries) | Test convergence |

**Process**: Take 5-10 cards that failed validation in previous experiments. Feed the specific validation errors back to the LLM with the prompt: "This card has the following issues: {errors}. Please regenerate with corrections." Track whether quality improves, stays the same, or degrades.

**Evaluation**: Retry convergence rate (% of cards fixed within 1-3 retries). Quality of retried cards vs originals. Token cost of retries.

**Cost estimate**: ~$1-2.

### Total Estimated Experiment Budget: $10-19

If this exceeds the $10 target, run Experiments 1 and 2 first, then use those results to reduce the search space for Experiments 3-5 (e.g., only test 2 batch sizes instead of 4).

---

## 5. Failure Mode Catalog

Common LLM card generation failures to actively watch for during evaluation.

### Category A: Rules Text Grammar Errors

| Failure | Example | Correct Form |
|---------|---------|--------------|
| Old ETB wording | "When ~ enters the battlefield" | "When ~ enters" |
| Missing period | "Target creature gets +2/+2 until end of turn" | "...until end of turn." |
| Wrong targeting syntax | "Destroy a creature" | "Destroy target creature" |
| Wrong keyword case | "Flying, First Strike" | "Flying, first strike" |
| Wrong mana symbol format | "(2)(W)" or "2W" | "{2}{W}" |
| Activated ability format error | "{T}, Sacrifice ~, Draw a card" | "{T}, Sacrifice ~: Draw a card." |
| Missing colon in activated abilities | "{2}{W} Draw a card." | "{2}{W}: Draw a card." |
| Loyalty ability format error | "+1, Draw a card" | "[+1]: Draw a card." |
| Saga chapter format error | "Chapter 1: Effect" | "I — Effect" |
| Wrong "choose" format | "Choose one:" | "Choose one —" |
| Reminder text outside parens | "Flying — this creature can't be blocked..." | "Flying *(This creature can't be blocked except...)*" |
| Using card name instead of ~ | "When Stormclaw enters" (in rules_text) | "When ~ enters" |
| Hybrid mana errors | "{W/U}" when not intended | Use only if the card is actually hybrid |
| "You may" on non-optional abilities | "You may draw a card" (when it should be mandatory) | "Draw a card." |
| "Each opponent" vs "target opponent" confusion | Using one when the other is appropriate | Match the intended targeting |

### Category B: Power Level / Balance Errors

| Failure | Example | Why It's Wrong |
|---------|---------|----------------|
| Undercosted removal | "{W}: Exile target creature" | Should be {3}{W}+ for unconditional exile |
| Common with mythic complexity | Common with 3 triggered abilities | Violates NWO |
| Free or near-free counterspell | "{U}: Counter target spell" | Should be {1}{U}+ for hard counter |
| Creature above vanilla curve at common | 3/3 for {1}{G} with upside at common | Commons should be at or below vanilla curve |
| Too many keywords | Common creature with flying, trample, haste, lifelink | Keyword soup belongs at rare+ |
| Draw-two at common | Common that draws 2+ cards without drawback | Card advantage engine at common breaks NWO |
| Planeswalker with too many starting loyalty | 6-loyalty 3-mana planeswalker | Starting loyalty should be close to CMC |

### Category C: Design / Flavor Errors

| Failure | Example | Why It's Wrong |
|---------|---------|----------------|
| Real MTG card name | "Lightning Bolt" as a generated card | Must be original names |
| Real-world references | "Einstein's Theory" or "Cybernetic Implant" | Should be fantasy-setting names |
| Color pie violation | Green: "Counter target spell" | Green cannot counter spells |
| Nonsensical creature type | "Creature — Human Fish Warrior" | Creature types should make sense together |
| Impossible ability combo | "Defender" + "must attack each combat" | These directly contradict each other |
| Wrong supertype | "Legendary Instant" | Instants are rarely legendary (possible but unusual) |
| Missing "Legendary" on named characters | "Creature — Vampire" named "Sorin, Dark Lord" | Named characters should be Legendary |
| Flavor text on complex cards | Full rules text + long flavor text | Text overflow — complex cards shouldn't have flavor text |

### Category D: Structural / Format Errors

| Failure | Example | Why It's Wrong |
|---------|---------|----------------|
| P/T on non-creatures | Instant with "power": "3" | Only creatures have P/T |
| Missing P/T on creatures | Creature without power/toughness | All creatures need P/T |
| Mana cost on basic lands | Basic Forest with mana_cost: "{G}" | Basic lands have no mana cost |
| Loyalty on non-planeswalkers | Creature with a loyalty field | Only planeswalkers have loyalty |
| Empty rules text on non-vanilla | Uncommon creature with no abilities | Uncommon+ should have at least one ability |
| Wrong color identity | Card with {R} in cost but color_identity: ["G"] | Must match |
| Duplicate card in batch | Two cards with same name in one batch output | Batch deduplication failure |

---

## 6. Experiment Execution Protocol

### Step-by-step for each experiment run:

1. **Prepare the prompt** using the templates from Section 2, inserting the experiment-specific parameters (temperature, few-shot count, batch size, etc.).

2. **Run the generation** call. Save the full request and response (prompt + completion) to `research/prompt-templates/experiments/exp{N}_{setting}.json`.

3. **Parse the output**. If JSON parsing fails, record the failure and attempt manual extraction. Track parse success rate.

4. **Score each card** against the rubric in Section 3. Record scores in a structured format:
   ```json
   {
     "card_name": "...",
     "experiment": "1A",
     "scores": {
       "rules_text_correctness": 4,
       "mana_cost_appropriateness": 5,
       "power_level_for_rarity": 3,
       "flavor_text_quality": 4,
       "name_creativity": 3,
       "type_line_correctness": 5,
       "color_pie_compliance": 5
     },
     "failure_modes": ["old_etb_wording"],
     "notes": "Used 'enters the battlefield' instead of 'enters' in one ability"
   }
   ```

5. **Catalog any failure modes** observed, adding to the Failure Mode Catalog if new ones are discovered.

6. **Aggregate scores** per experiment setting and compare.

### Iteration Protocol

After each experiment, before moving to the next:
- Review the worst-scoring cards. What specific prompt changes would fix them?
- Update the system prompt or card generation prompt if a clear improvement is identified.
- Re-run the worst 3-5 cards with the updated prompt to verify improvement.
- Document the prompt change and its effect in the learnings file.

---

## 7. Output Specifications

### Directory Structure

```
research/
  prompt-templates/
    system-prompt-v1.md          # The system prompt, versioned
    single-card-template-v1.md   # Single-card generation prompt template
    batch-template-v1.md         # Batch generation prompt template
    few-shot-examples.json       # All few-shot example cards (from real MTG)
    context-injection-template.md # Set context injection template
    experiments/
      exp1_temperature/
        exp1a_t03.json           # Full request + response + scores
        exp1b_t05.json
        exp1c_t07.json
        exp1d_t10.json
        exp1_summary.md          # Comparative analysis
      exp2_fewshot/
        exp2a_zero.json
        exp2b_one.json
        exp2c_three.json
        exp2d_five.json
        exp2_summary.md
      exp3_batch/
        exp3a_single.json
        exp3b_batch5.json
        exp3c_batch10.json
        exp3d_batch24.json
        exp3_summary.md
      exp4_format/
        exp4a_json_mode.json
        exp4b_prompt_json.json
        exp4c_free_text.json
        exp4_summary.md
      exp5_context/
        exp5a_no_context.json
        exp5b_names_only.json
        exp5c_compressed.json
        exp5d_full_color.json
        exp5_summary.md
    BEST-SETTINGS.md             # Final recommended settings for Phase 1C

learnings/
  phase0e.md                     # What worked, what didn't, anti-patterns
```

### `BEST-SETTINGS.md` Contents

This file is the primary deliverable — the "card generation cookbook" for Phase 1C.

```
# Recommended Card Generation Settings

## Model: {model_name}
## Temperature: {best_temperature}
## Few-shot examples: {count} per call
## Batch size: {recommended_batch_size}
## Output format: {json_mode / prompt_json / free_text}
## Context strategy: {tier_description}

## System prompt version: v{N} (see system-prompt-v{N}.md)
## Single-card template version: v{N}
## Batch template version: v{N}

## Expected quality: {average_score}/5.0
## Expected retry rate: {percentage}%
## Estimated cost per card: ${amount}
## Estimated cost per full set (280 cards): ${amount}

## Known limitations:
- {limitation_1}
- {limitation_2}

## Failure modes requiring post-processing:
- {mode_1}: {mitigation}
- {mode_2}: {mitigation}
```

### `learnings/phase0e.md` Contents

```
# Phase 0E Learnings: Prompt Engineering Spike

## What Worked
- ...

## What Didn't
- ...

## Key Findings
- Best temperature: X (reason)
- Few-shot sweet spot: N examples (reason)
- Batch vs single: (finding)
- JSON mode: (finding)
- Context strategy: (finding)

## Prompt Anti-Patterns (Things That Made Cards Worse)
- ...

## Prompt Patterns (Things That Made Cards Better)
- ...

## Parameter Adjustments for Phase 1C
- ...

## Open Questions for Phase 1C
- ...

## Failure Modes Discovered (additions to catalog)
- ...
```

---

## 8. Success Criteria (GO/NO-GO Gate)

### GO — Proceed to Phase 1

ALL of the following must be true after prompt iteration:

1. **Rules text correctness**: Average score >= 4.0 across all cards. No more than 2 cards with score < 3. Zero cards with completely unparseable or impossible rules text.

2. **Overall quality**: Average score across all 7 dimensions >= 3.5 for the best experiment configuration.

3. **Retry rate**: With the best configuration, no more than 30% of generated cards need regeneration to reach acceptable quality (score 3+ on all dimensions).

4. **JSON reliability**: Parse success rate >= 95% (valid JSON with all required fields).

5. **Cost viability**: Estimated cost for a full 280-card set (including retries) stays under $30 in LLM API calls — within the ~$30 LLM budget from the master plan.

6. **Planeswalker & Saga capability**: The LLM can generate at least passable (score 3+) planeswalker and Saga cards. These are the hardest templates, and if the LLM cannot handle them, we need to plan for more manual design of these card types.

### NO-GO — Reassess

If ANY of the following are true:

1. **Rules text average < 3.0** even after 3+ rounds of prompt iteration. The LLM fundamentally cannot produce correct MTG grammar.

2. **More than 50% retry rate** — we'd spend more time fixing than generating.

3. **Color pie violations are systemic** — the LLM doesn't understand what colors can/can't do, even with explicit instructions.

4. **Cost per set exceeds $50** — breaks the budget constraint from the master plan.

### CONDITIONAL GO — Proceed with Caveats

If GO criteria are met but with reservations:

- **Planeswalkers/Sagas are weak**: GO, but plan to hand-design these card types in Phase 1C instead of generating them.
- **Batch quality drops off**: GO, but use single-card generation for rare/mythic and batch only for common/uncommon.
- **High retry rate on specific types**: GO, but build type-specific prompt variants for Phase 1C (separate prompts for creatures vs. instants vs. enchantments).

---

## 9. Cross-Cutting Concerns & Master Plan Suggestions

### Should this phase also test art prompt generation (bridging to Phase 2A)?

**Recommendation: Yes, lightly.** For 5-6 of the 24 test cards, also ask the LLM to generate an art prompt alongside the card data. This lets us evaluate:
- Can one prompt produce both a card and a usable art description?
- Or should art prompting be a completely separate step?
- What art prompt style works best for the chosen image generation service?

This doesn't need to be a full experiment — just a "while we're here" addition. Add an optional `art_prompt` field to the JSON schema:
```json
{
  "art_prompt": "A towering angel with golden armor descending from storm clouds, dramatic lighting from below, fantasy oil painting style, detailed wings"
}
```

Evaluate these art prompts qualitatively and record findings in `learnings/phase0e.md`. This will save time in Phase 2A.

### Is 20 cards enough to validate? Should it be 30-40?

**Recommendation: 24 is sufficient for the initial pass, but plan for a confirmation run.**

24 cards covers all major axes (rarity, color, type, complexity). However, after settling on the best configuration from the experiments, run a **confirmation batch of 20 additional cards** using only the winning settings. This gives us 44 total scored cards — enough statistical confidence to make the GO/NO-GO call.

The confirmation batch should include:
- 5 cards using set-specific mechanics (test mechanic integration)
- 5 cards that need to be aware of existing cards (test context injection)
- 10 cards that fill specific archetype needs (test design intentionality)

If the master plan budget allows, increase to 30-card test matrix initially instead of 24. But 24 + 20 confirmation = 44 scored cards is likely more valuable than 40 cards in a single pass, because the confirmation batch uses optimized settings.

### Should the prompt templates be versioned and tracked in git?

**Recommendation: Absolutely, and this should be a hard rule.**

Prompt templates are the "source code" of the card generation system. They must be:
- **Version-controlled in git** alongside the project code
- **Versioned in filenames** (system-prompt-v1.md, v2.md, etc.) so experiment results reference a specific version
- **Never modified in place** — create a new version, note what changed and why
- **Stored with their experiment results** — every experiment JSON file references the prompt version used

Add to `CLAUDE.md`:
```
## Prompt Template Rules
- All prompt templates live in research/prompt-templates/
- Templates are versioned: system-prompt-v1.md, v2.md, etc.
- Never edit a published version — create a new one
- Every experiment records which prompt version it used
- The BEST-SETTINGS.md file references the final winning versions
```

### Should this phase produce a "card generation cookbook" for Phase 1C?

**Recommendation: Yes — this is actually the primary deliverable.**

The `BEST-SETTINGS.md` file described in Section 7 IS the cookbook. Phase 1C should be able to pick up this file and immediately know:
- Which model, temperature, few-shot count, batch size, and output format to use
- Which prompt templates to start from
- Which card types need special handling
- What retry rate to expect
- What post-processing / validation is needed

The cookbook should also include:
- **A decision tree for prompt selection**: "If generating a common creature, use template X with N examples. If generating a planeswalker, use template Y with M examples."
- **Known failure modes and mitigations**: "The LLM often uses old ETB wording. Post-process rules text to replace 'enters the battlefield' with 'enters'."
- **Cost projections**: "At the recommended settings, generating 280 cards will cost approximately $X and require approximately Y API calls."

### Does the master plan underestimate the iteration needed here?

**Recommendation: Probably yes. Build in a buffer.**

The master plan describes Phase 0E as a list of things to test, but prompt engineering is inherently iterative. Expect:

- **3-5 rounds of system prompt revision** based on failure analysis
- **Per-type prompt specialization** — the same prompt won't work equally well for vanilla creatures and planeswalkers
- **Discovery of failure modes not in the initial catalog** — LLMs find creative ways to be wrong
- **Potential model comparison** — if the initially chosen model from Phase 0D performs poorly, this phase may need to test 2-3 models

**Suggested time allocation:**
- Experiments 1-2 (temperature + few-shot): 1 day
- Experiments 3-5 (batch + format + context): 1 day
- Prompt iteration based on findings: 2-3 days
- Confirmation batch + final scoring: 0.5 days
- Documentation and cookbook: 0.5 days
- **Total: 5-6 working days** (not the 1-2 days you might assume from the task list)

**Master plan update suggestion**: Add a note to Phase 0E in the master plan that says "Allow 1 week. This is the most iteration-heavy research phase." Also consider adding a feedback arrow from Phase 1C back to the prompt templates — when Phase 1C generates a full set, prompt refinements discovered there should be folded back into the templates.

### Additional suggestion: Test a validation-retry loop

The master plan mentions "Validation + retry loop for cards that fail checks" in Phase 1C. Phase 0E should prototype this loop, not just test single-shot generation. Specifically:

1. Generate a card
2. Run basic validation (rules text grammar, mana cost sanity, color pie check)
3. If validation fails, feed the error back to the LLM: "This card has the following issues: {issues}. Please regenerate with corrections."
4. Measure: How many retries does it take? Does retry quality improve or just shuffle the errors?

This is critical information for Phase 1C's architecture — if retries converge quickly (1-2 attempts), we can automate aggressively. If retries don't converge, Phase 1C needs more human-in-the-loop design.

---

## Appendix A: Example Full Prompt (Ready to Use)

Below is a complete, copy-pasteable prompt for generating a single uncommon white removal spell. This is what an actual API call would look like using the templates above.

**System prompt**: (Use the full system prompt from Section 2.1)

**User prompt**:
```
Generate a single Magic: The Gathering card for a custom set with the following constraints:

**Set context**: "Ashenveil" is a gothic horror set on a plane where the boundary between the living and dead worlds has shattered. Spirits walk among the living, ancient vampires war with holy orders, and the land itself is haunted. The tone is dark but with notes of hope — the living fight back.

**Set mechanics**:
- Haunt (When this creature dies, exile it haunting target creature. The haunted creature gains this creature's abilities.)
- Vestige {cost} (You may cast this spell for its vestige cost from your graveyard. If you do, exile it as it resolves.)
- Consecrate (Exile any number of cards from graveyards. This spell costs {1} less for each card exiled this way.)

**Card requirements**:
- Color: White
- Rarity: Uncommon
- Type: Instant
- Complexity: Single ability — clean, efficient removal spell
- Role: White's primary creature removal at uncommon. Should be conditional (white doesn't get unconditional removal at uncommon). Should interact with the set's graveyard themes.

**Example — Single ability instant:**
{
  "name": "Go for the Throat",
  "mana_cost": "{1}{B}",
  "type_line": "Instant",
  "rules_text": "Destroy target nonartifact creature.",
  "flavor_text": "\"That's the thing about most fiends. They still need to breathe.\"",
  "power": null,
  "toughness": null,
  "rarity": "uncommon",
  "color_identity": ["B"]
}

**Example — Single ability instant (white removal):**
{
  "name": "Fateful Absence",
  "mana_cost": "{1}{W}",
  "type_line": "Instant",
  "rules_text": "Destroy target creature or planeswalker. Its controller investigates.",
  "flavor_text": "\"It came looking for me, but I was already gone.\" —Rem Karolus",
  "power": null,
  "toughness": null,
  "rarity": "uncommon",
  "color_identity": ["W"]
}

Output the card as a JSON object with exactly these fields:
{
  "name": "Card Name",
  "mana_cost": "{2}{W}",
  "type_line": "Instant",
  "rules_text": "Rules text here.",
  "flavor_text": "\"Flavor quote here.\" —Attribution",
  "power": null,
  "toughness": null,
  "rarity": "uncommon",
  "color_identity": ["W"]
}

Rules for the JSON:
- power/toughness: null for non-creatures. Use strings for creatures (e.g., "3", "*").
- mana_cost: Use {W}{U}{B}{R}{G}{C}{1}{2}{X} notation. Omit for lands.
- rules_text: Use \n for line breaks between abilities. Use ~ for card name.
- flavor_text: Optional. Use escaped quotes for speech. Set to null for complex cards where rules text fills the card.
- color_identity: Array of color letters. Empty array [] for colorless.
```

---

## Appendix B: Real Card Data for Few-Shot Examples

Source these from Scryfall API (https://api.scryfall.com/cards/named?exact={name}) to ensure up-to-date Oracle text. Do NOT rely on memory — Oracle text gets updated (e.g., the 2023 ETB wording change).

**Cards to pull for the example library:**

| Card | Why |
|------|-----|
| Grizzly Bears | Vanilla creature baseline |
| Inspiring Overseer | Common creature with keyword + ETB trigger |
| Monastery Swiftspear | Keyword creature with prowess |
| Murder | Clean removal instant |
| Negate | Counterspell template |
| Rampant Growth | Land search sorcery template |
| Lightning Bolt | Damage spell baseline |
| Prismari Command | Modal spell (choose two) |
| Charming Prince | Multi-modal ETB creature |
| The Wandering Emperor | Planeswalker with flash |
| The Eldest Reborn | Saga template |
| Skullclamp | Equipment template |
| Sol Ring | Mana artifact template |
| Caves of Koilos | Pain land (utility land template) |
| Sheoldred, the Apocalypse | Complex legendary mythic |

Store all of these in `research/prompt-templates/few-shot-examples.json` with full Scryfall-sourced Oracle text.
