# Phase 1C Learnings: Card Generator

## What was built
- **Card generation pipeline** (`backend/mtgai/generation/card_generator.py`): Batch-generates cards from a skeleton of slot definitions, grouped by color. Resumable via `generation_progress.json`.
- **Prompt construction** (`backend/mtgai/generation/prompts.py`): System prompt with MTG rules reference, color pie, NWO guidelines. User prompt includes set theme, custom mechanics, preventive design checklist (8 pointed questions from 1B), and already-generated cards to avoid duplication.
- **Validation library** (`backend/mtgai/validation/`): 8 validators (schema, mana, type_check, rules_text, power_level, color_pie, text_overflow, uniqueness), 17 auto-fixers, `validate_card_from_raw()` entry point. Two severity levels: AUTO (deterministic fix) and MANUAL (needs LLM or human review).
- **60 cards generated** for Anomalous Descent (ASD) dev set. All mono-color, multicolor, and colorless slots filled.
- **Card gallery script** (`scripts/gen_card_gallery.py`): Generates human-readable markdown from card JSONs with live validation results.

## Generation run stats
- **Model**: Opus 4.6 with `effort=max`, `temperature=1.0`
- **16 batches**, 5 cards per batch (smaller for multicolor/colorless groups)
- **Total cost**: $2.78 (~$0.046/card)
- **Total time**: ~7.4 minutes (~27s average per batch)
- **Zero failures**: All 60 cards generated on first attempt, all returned valid JSON via tool_use
- **80,881 input tokens / 20,840 output tokens** across 16 API calls

## Validation results
- **42/60 cards clean** (no MANUAL issues)
- **18/60 cards with MANUAL warnings** (not blocking -- deferred to review phase)
- Breakdown of issues:
  - `reminder_in_oracle` (15): Reminder text for custom mechanics embedded in oracle_text instead of separate field. Cosmetic/schema convention, not a gameplay issue.
  - `text_overflow` (4): Rules text too long for card frame. Real rendering concern.
  - `color_pie` (3): Koyl Yrenum has hexproof + indestructible in mono-black (off-color). One blue card with reanimation effect.
  - `this_creature` (2): "this creature"/"This permanent" instead of `~` self-reference.
  - `malfunction_enters_tapped` (2): Redundant "enters tapped" wording when Malfunction already implies it.
  - `power_level.overstatted` (1): Rendon Ceratops 3/3 trample common exceeds P+T budget for creatures with abilities.
  - `power_level.nwo_multiple_keywords` (1): Common with 2 keyword abilities.

## What worked well
- **Batch generation with color grouping**: Grouping cards by color meant the LLM had consistent context within each batch. No color pie confusion across batches.
- **Preventive design checklist**: Baking the 8 pointed questions from 1B into the generation prompt prevented most of the failure modes found during the A/B test. Zero keyword nonbos, zero fake variability, zero keyword name collisions in 60 cards.
- **Already-generated cards in prompt**: Including previously generated card summaries in each batch prevented name collisions and mechanical duplication across the set.
- **Opus 4.6 at effort=max**: No truncation issues, no malformed JSON, no retry needed. The model handled the complex structured output reliably.
- **Auto-fixers**: Caught and fixed minor formatting issues (missing periods, outdated "enters the battlefield" phrasing, keyword comma formatting) without human intervention.
- **tool_use for structured output**: Using `tool_choice: force` with a JSON schema tool guaranteed valid card JSON every time. `stop_reason: tool_use` on all 60 cards.

## What didn't work / needs improvement

### 1. Missing "constraint derivation" step in pipeline (CRITICAL)
- The pipeline goes straight from set design (theme + mechanics) to slot allocation to card generation, with no step that analyzes what the mechanics *structurally require* from the set.
- **Example**: ASD's Salvage mechanic tutors for artifacts, and multiple archetypes have artifact-enters triggers. This implies the set needs high artifact density -- but nothing in the pipeline enforces that. Result: 22 cards reference artifacts, only 6 artifacts exist.
- **The general fix**: After set design defines theme and mechanics, a new "constraint derivation" step should analyze them and output **modifiers** to the skeleton and generation prompts. These are structural requirements that flow from design decisions:
  - Mechanic X tutors for card type Y → increase Y density to Z%
  - Theme involves graveyard recursion → ensure enough self-mill / discard enablers
  - Archetype A cares about tokens → guarantee N token producers at common
- This step should be an LLM revision pass on the **skeleton itself**: feed it the theme, mechanics, archetypes, AND a summary of the current skeleton (x commons, y uncommons, n% creature, etc.). Have it output concrete skeleton adjustments ("convert 6 creature slots to artifact creature slots", "cut 2 enchantment slots, add 2 common artifacts"). The skeleton is already the single source of truth for type/rarity distribution, so that's where the fix belongs -- not as a separate modifier bolted onto generation prompts.
- Without this step, the generator has no awareness of systemic needs -- it designs each card in isolation while the set as a whole falls apart structurally. Review can't fix this; by the time you notice, half the set needs redesigning.

### 2. Validator / prompt power level discrepancy
- Generation prompt says: "Common creatures: P+T should not exceed CMC + 3"
- Validator enforces: `CMC+3` for vanilla, `CMC+2` for creatures with abilities, `CMC+4` for creatures with downsides
- The LLM followed the prompt correctly (Rendon Ceratops 3/3 trample = 6 = CMC+3), but the validator is stricter for non-vanilla creatures
- **Fix needed**: Either align the prompt to the validator's tiered thresholds, or align the validator to the simpler rule. Currently the LLM is set up to fail on any common creature with abilities and stats at the upper end.

### 3. Reminder text in oracle_text (15 cards)
- The generation prompt says "The FIRST time a custom mechanic keyword appears in a card's oracle text, follow it with reminder text in parentheses"
- The LLM correctly followed this instruction
- The validator flags any parenthetical text in oracle_text as potential reminder text that should be in a separate field
- This is a schema design question, not a generation issue. The card JSON schema doesn't have a `reminder_text` field, so the LLM has nowhere else to put it.
- **Fix options**: (a) Add a `reminder_text` field to the card schema, (b) stop flagging reminder text in oracle_text since that's standard MTG formatting, or (c) accept the warnings as informational.

### 4. Unicode in LLM output
- Opus generates em dashes (U+2014) extensively in flavor text and design notes (134 instances across 59/60 cards)
- These cause encoding display issues in some markdown viewers and caused problems in the Phase 1B A/B test review pass
- **Fix applied**: Post-processing script to replace em/en dashes and curly quotes with ASCII equivalents in all card JSONs
- **Fix needed for pipeline**: Add a sanitization step in `card_generator.py` after receiving LLM output, before writing to disk. Replace non-ASCII punctuation automatically.

### 5. False positive type_check errors
- The type_check validator flagged `noncreature_has_pt` and `pt_without_creature` on cards that ARE creatures (e.g. "Legendary Creature -- Human Soldier")
- Root cause: The validator's type_line parser doesn't correctly parse "Creature" from type_lines with supertypes (Legendary) or subtypes
- Not blocking (filtered out in gallery generation) but noisy -- inflated the "cards with issues" count
- **Fix needed**: Update type_line parsing in type_check validator to handle supertypes correctly

### 6. Informal mana production false positive
- Validator flagged "Add two mana of any one color" as informal mana production
- This is correct MTG templating (see Gilded Lotus, Coalition Relic)
- **Fix applied**: Narrowed the regex to only flag when a color name is used (e.g. "add green mana") instead of any word before "mana"

### 7. Enchantment Artifact is almost never correct
- LLM generated 2 "Legendary Enchantment Artifact" cards (The Brain Engine, The Cartography Engine)
- In all of MTG, only the Theros gods' weapons use this type combination -- it's essentially never appropriate
- **Fix applied**: AUTO validator + auto-fixer strips "Enchantment" and rebuilds the type_line (e.g. `Legendary Enchantment -- Artifact` -> `Legendary Artifact`)

### 8. Type_line parser didn't handle double-hyphen dashes
- After scrubbing Unicode em dashes to `--`, the type_line parser couldn't split on `--` to separate types from subtypes
- This caused all creatures to be missing "Creature" from `card_types`, producing false positive `noncreature_has_pt` errors on every creature
- Also: when the LLM incorrectly put a dash between two card types (e.g. "Enchantment -- Artifact"), the parser now correctly identifies both as card types instead of treating the second as a subtype
- **Fix applied**: Updated parser regex to split on `--`, `–`, or `—`. Added logic to move card types that end up after the dash back into `card_types`.

## Design quality observations
- **Flavor text quality is high**: The LLM nailed the deadpan/darkly humorous tone consistently. Examples: "The first level of the dungeon is picked clean. The second level picks back." / "Forty-seven teeth, none of them from the same mouth."
- **Design notes are verbose but useful**: The LLM writes paragraph-length justifications for each card. Good for review but could be trimmed for the gallery.
- **Card naming is solid**: No duplicate names, names feel thematically consistent with the setting (Denethix, Moktar, Subsurface, Fist, etc.)
- **Mechanical diversity within colors**: Each color has vanilla, french vanilla, removal, complex sorcery, and build-around pieces at appropriate rarities.

## Cost
- Card generation (60 cards, 16 batches): $2.78
- Validation library development: $0 (hand-coded)
- **Total Phase 1C generation: $2.78**
- **Cumulative project spend: ~$13.12** ($10.34 pre-1C + $2.78 generation)

## Files produced
- `backend/mtgai/generation/card_generator.py` -- batch card generation pipeline
- `backend/mtgai/generation/prompts.py` -- prompt construction for card generation
- `backend/mtgai/generation/llm_client.py` -- LLM client (effort param, truncation check)
- `backend/mtgai/validation/` -- 8 validators, 18 auto-fixers
- `backend/tests/test_validation/test_validators.py` -- 73 validation tests
- `output/sets/ASD/cards/` -- 60 generated card JSONs
- `output/sets/ASD/generation_progress.json` -- generation progress/cost tracking
- `output/sets/ASD/generation_logs/` -- per-batch and per-card generation logs
- `output/sets/ASD/card_gallery.md` -- human-readable card gallery with validation results
- `scripts/gen_card_gallery.py` -- gallery generation script (runs live validation)

## What to watch for next
- **Artifact density must be addressed before review**: Either add more artifact slots to the skeleton or convert some existing cards to artifacts. The review pass can't fix a structural imbalance.
- **Reprint/land slots** (`1C-reprint`, `1C-lands`): These are opportunities to add more artifacts to the set (artifact lands, equipment reprints, mana rocks).
- **Human review** (`1C-review`): Focus on the 18 flagged cards plus spot-check a sample of the 42 clean ones. The color pie violations on Koyl Yrenum need a design decision.
- **Review pipeline** (Phase 4): The tiered council+iteration hybrid from 1B is ready to implement. The validation library provides pre-screening so the LLM reviewer can focus on design quality rather than formatting issues.
- **Unicode sanitization**: Add to the pipeline before the review pass generates more em dashes.
