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
