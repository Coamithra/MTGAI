# Phase 4A Learnings: Balance Analysis (Design Phase)

## Key insight: 4A is skeleton conformance, not set-specific analysis

The balance analysis should verify that generated cards conform to what the skeleton specified. The skeleton is the single source of truth for set structure — after the constraint derivation step (Phase SC) adjusts it for set-specific needs (artifact density, mechanic distribution, etc.), Phase 4A just checks: "did the generator follow the plan?"

This keeps 4A fully general across any set. Set-specific structural requirements (like "needs high artifact density") are encoded in the skeleton by earlier phases, not hard-coded into the analysis.

## Mechanics need functional tags at creation time (Phase 1B prerequisite)

Custom set mechanics often provide removal, card advantage, mana fixing, or other functional roles. Examples from ASD:
- **Salvage**: card advantage (filters top of library, finds artifacts)
- **Overclock**: card advantage (exiles top 3, may play until end of turn)
- **Malfunction**: tempo cost (enters tapped with delay counters) — not removal/CA/fixing

If mechanics aren't tagged with their functional roles during Phase 1B (mechanic generation), the balance analysis can't correctly count removal density, card advantage sources, etc. A card with "Salvage 3" IS card advantage, but regex-based oracle text scanning won't know that without the tag.

**Required change**: Add a `functional_tags` field to the `Mechanic` model (e.g., `["card_advantage"]`, `["removal", "conditional"]`, `["mana_fixing"]`). The LLM that designs mechanics in Phase 1B should assign these tags. The balance analyzer then loads mechanic definitions and counts any card using a tagged mechanic toward that functional category.

This must be implemented BEFORE Phase 4A runs, either by:
1. Retroactively tagging existing mechanics in `approved.json` (quick fix for dev set)
2. Adding it to the mechanic generation pipeline for future sets (proper fix)

## What 4A checks (refined scope)

### Skeleton conformance (per-slot)
- Color match: generated card color matches skeleton slot color
- Rarity match: generated card rarity matches skeleton slot rarity
- Card type match: creature slot got a creature, instant slot got an instant, etc.
- CMC proximity: generated card CMC is close to skeleton's `cmc_target`
- Mechanic assignment: if skeleton specifies a mechanic (post-Phase SC), card uses it

### Set-wide coverage (general checks)
- **Creature CMC curve per color**: No gaps in the 1-6+ range. Every color should have creatures at most CMC values. Flag missing CMC buckets.
- **Creature size distribution per color**: Each color should have creatures spanning a range of P+T values appropriate to that color's identity (green = beefy, blue = small + abilities). Flag colors missing weight classes.
- **Removal density per color**: Enough removal at common/uncommon, using mechanic functional tags to count custom mechanics that provide removal.
- **Card advantage per color**: Enough CA sources, counting mechanics tagged as card advantage.
- **Mana fixing inventory**: Enough color fixing for the set's multicolor needs.
- **Mechanic distribution vs plan**: Actual mechanic counts vs skeleton's planned distribution.
- **Color balance**: Roughly even card counts across colors.

### What 4A does NOT check
- Individual card power level (P/T vs CMC for a specific card) — that's the AI review's job
- Individual card design quality — that's 4B
- Rendered card quality — that's 4C

## How retroactive functional tagging was done (for Phase 1B integration)

For the ASD dev set, mechanics were already generated without functional tags. We retroactively
created `output/sets/ASD/mechanics/functional-tags.json` as a sidecar file:

```json
{
  "Salvage": ["card_advantage"],
  "Overclock": ["card_advantage"],
  "Malfunction": ["tempo_cost"]
}
```

The balance analyzer loads both `approved.json` and `functional-tags.json`, merging tags. If a
mechanic already has `functional_tags` in its definition (via the `Mechanic` model field added
in this phase), those take priority; the sidecar is a fallback for older data.

**For future iterations**: The mechanic generation step (Phase 1B / `mechanic_generator.py`)
should have the LLM assign `functional_tags` at mechanic creation time. Add this to the tool
schema / prompt so the LLM outputs tags like `["card_advantage"]`, `["removal"]`,
`["mana_fixing"]`, or `["tempo_cost"]` alongside the mechanic definition. This eliminates the
need for retroactive tagging entirely.

Suggested tag vocabulary:
- `card_advantage` — provides extra cards or card selection
- `removal` — removes or neutralizes opposing permanents
- `mana_fixing` — produces mana of colors other than the card's own
- `token_generation` — creates creature or artifact tokens
- `tempo_cost` — imposes a tempo penalty (enters tapped, delay counters, etc.)
- `lifegain` — gains life as a primary effect
- `ramp` — accelerates mana production (not fixing, just more mana)

## First run results (ASD dev set, 66 cards)

- **Skeleton conformance**: 32/60 slots matched perfectly, 28 had WARN-level issues
  - Dominant issue: mechanic complexity tier mismatches (28 WARNs). The skeleton assigns
    many "complex" slots but the cards were classified as "evergreen" because they don't use
    set mechanics. This is expected before Phase SC adds mechanic-to-slot assignment.
  - 1 CMC deviation (off by 1)
  - 0 color/rarity/type mismatches
- **Creature CMC gaps**: Every color missing creatures at CMC 5-6 (expected at 60 cards)
- **Mechanic distribution**: Salvage 12 vs planned 6 (over), Malfunction 3 vs 5, Overclock 1 vs 3
- **Mana fixing**: 4 sources found (Spore-Nest Forager, Descent Waypoint, Ransack the Storeroom, Flickering Relay Node)
- **Color balance**: Nearly perfect (W:10, U:10, B:10, R:9, G:9)
- **0 FAIL issues**, 42 WARN issues total

## Implementation details

### Module structure
```
backend/mtgai/analysis/
    __init__.py    — public API (analyze_set)
    models.py      — Pydantic result models (BalanceAnalysisResult, etc.)
    helpers.py     — type_line parser, removal/CA/fixing detectors, weight class
    conformance.py — per-slot skeleton conformance checks
    coverage.py    — set-wide coverage analysis
    balance.py     — top-level orchestrator
    report.py      — Markdown + JSON report generation
```

### CLI
`python -m mtgai.review balance --set ASD` runs the full analysis and saves reports to
`output/sets/<CODE>/reports/balance-report.md` and `balance-analysis.json`.

### Tests
72 tests in `tests/test_analysis/` (helpers: 28, conformance: 12, coverage: 13, total: 72 + existing 415 = 487 all passing).

### Key data quality workaround
58/66 cards have empty `card_types` field. The analyzer parses `type_line` strings instead
(e.g., "Legendary Artifact Creature -- Construct" -> ["Artifact", "Creature"]). This is a
known data quality issue from Phase 1C that should be fixed in the generation pipeline.

---

## Phase 4A-rev: Skeleton Revision Pipeline

**Date**: 2026-03-14
**Total cost**: $3.44 (Opus revision analysis $3.38 + Haiku fix regen $0.065)

### What Worked

- **Revision pipeline architecture** — compact card serialization, balance findings + mechanic targets to Opus, structured revision plan via tool_use, apply to skeleton, regenerate only affected slots — is the right design.
- **Haiku for regeneration** — $0.065 for 11 cards vs $3.38 for Opus. Haiku produced 100% mechanic adherence when given proper prompts. Expensive models are needed for *analysis*, not execution.
- **Detailed logging** — full prompts and responses in `revision_logs/` made it possible to diagnose the prompt bugs by comparing what the skeleton had vs what the LLM actually saw.

### Critical Bugs Found and Fixed

All in the same class: **fields exist in the data model, get populated correctly, but are silently dropped when building prompts or transferring between modules.**

1. **`notes` dropped from generation prompt** (`prompts.py:format_slot_specs`): Revision guidance like "Must use Malfunction 2" was never shown to the generator LLM. The field was simply never added to the format function.

2. **`mechanic_tag` dropped during revision plan application** (`skeleton_reviser.py:apply_revision_plan`): For `regenerate` actions, only `notes` was applied from `new_constraints` — `mechanic_tag`, `card_type` etc. were silently dropped.

3. **`archetype_tags` dropped for monocolor slots** (`prompts.py:format_slot_specs`): Archetype lookup only happened for multicolor slots via `color_pair`. Monocolor cards — the majority of the set — got zero draft archetype guidance.

4. **`is_reprint_slot` never sent to LLM** (`prompts.py:format_slot_specs`): Reprint slots were generated as original designs.

5. **`mechanic_tags`/`draft_archetype` never set on Card model** (`card_generator.py:_process_batch_result`): Fields existed on the model but were never populated from skeleton data during generation.

6. **Oracle text over-truncated** (`prompts.py:format_set_context`): Hard-cut at 60 chars mid-word. Increased to 120 chars with clause-boundary-aware truncation.

7. **System prompt parsing fragile** (`prompts.py:load_system_prompt`): `string.index("```")` replaced with regex + explicit error on no match.

### Design Lesson: Revision model was over-prescriptive

The revision LLM (Opus) was designing entire cards in the `notes` field — exact ability text, stats, creature types, keywords. This turned the generation LLM into a transcriber rather than a designer.

**Fix applied**: Tightened tool schema description and instructions to constrain `notes` to brief mechanic/structural constraints only (e.g., "Must use Malfunction 2, UB signpost"). Creative decisions belong to the generation model.

### Design Lesson: Silent data loss is the deadliest bug class

All prompt-related bugs produced zero errors — the pipeline ran successfully but generated worse cards. The only symptom was "the LLM isn't doing what we asked" which looks like an LLM quality problem, not a code bug.

**Mitigation for scale-up**: Add prompt verification assertions before the full 280-card run. If a slot has non-empty `notes`, the formatted spec must contain "Notes:". If a slot has `archetype_tags`, the spec must contain "Supports archetypes" or "Archetype". Fail fast on data loss.

### Post-revision metrics

- Salvage: 12 -> 8 (planned 6)
- Malfunction: 3 -> 7 (planned 5)
- Overclock: 1 -> 4 (planned 3)
- Color balance: W:10, U:10, B:10, R:9, G:9
- 33 cards archived, 11 re-regenerated after bug fix
- 0 FAIL issues in balance analysis
