# Phase 1A Learnings: Set Skeleton Generator

## What was built
- **Skeleton generator** (`backend/mtgai/skeleton/generator.py`, 897 lines): Takes a `SetConfig` + `set-template.json`, produces a slot allocation matrix with color/rarity/type/CMC/mechanic/archetype assignments. Scales from 20 to 300+ cards.
- **CLI review tool** (`backend/mtgai/review/`): Typer + Rich CLI with `list` (7 filters + sort), `show` (slot detail panel), `stats` (full dashboard with tables, CMC bar chart, constraint checks). 7 Phase 3A command stubs.
- **75 unit tests** (`backend/tests/test_skeleton.py`): Models, constraints, generation at multiple sizes, balance reports, edge cases, save/load round-trip.
- **Theme**: "Anomalous Descent" (ASD) — science-fantasy megadungeon set with 8 legendary characters, 10 draft archetypes.

## What worked well
- **Proportional scaling from set-template.json**: Using `BASE_SET_SIZE=277` and scaling down to 60 cards keeps ratios realistic. The same code will scale back up to ~280 for production.
- **MechanicTag tiers** (vanilla/french_vanilla/evergreen/complex): Clean abstraction that maps well to NWO complexity. Commons get simple tags, rares get complex. Phase 1B will refine with actual mechanic names.
- **Rich CLI for skeleton review**: Tables with color-coding make it easy to spot-check distributions. The stats dashboard with constraint checks provides instant validation.
- **Constraint-driven generation**: Hard constraints (color balance, creature density, signpost uncommons, rarity totals) catch errors early. Soft constraints (avg CMC, CMC coverage) provide warnings.

## Bugs found and fixed
- **Color balance remainder bug**: When common mono-color count wasn't divisible by 5, remainder was distributed unevenly across colors (e.g., W=7, U=7, B=6, R=6, G=6), violating the ±0 common color balance constraint. Fix: remainder goes to colorless bucket instead.

## Design decisions
- **4 commons per mono-color at dev-set size**: With 21 commons total, each of 5 colors gets 4 (=20) + 1 colorless artifact. This is tight but workable — each color gets 1 vanilla creature, 1 french_vanilla creature, 1 instant, 1 sorcery.
- **Archetype tags on every slot**: Each mono-color slot is tagged with all 4 of that color's archetype pairs. Multicolor slots are tagged with their specific pair. This makes archetype-filtered queries useful.
- **No lands in dev set skeleton**: The 60-slot skeleton focuses on spells/creatures. Basic lands and nonbasic lands will be added in Phase 1C (card generation).

## Surprises
- **Enchantment-heavy at uncommon/rare**: The type distribution algorithm assigns more enchantments than expected at higher rarities (10 total = 16.7%). This matches recent sets like Duskmourn but is worth watching — if the set doesn't have an enchantment theme, some could be converted to instants/sorceries during card generation.
- **Only 5 of 10 archetypes get signpost uncommons at dev-set size**: With only 5 multicolor uncommon slots (scaled from 10 at full size), half the archetypes lack their defining card. Acceptable for pipeline testing; full set will have all 10.

## What to watch for in Phase 1B
- The 3 custom mechanics need to be distributed across the existing MechanicTag slots. Some "complex" tagged slots should become `new_mechanic:<name>` slots.
- Mechanic validation spike (1B-7) should verify the LLM can use novel keywords correctly on actual skeleton slots.

## Cost
- $0 (no API calls — skeleton generation is deterministic algorithmic code)

## Files produced
- `backend/mtgai/skeleton/generator.py` — skeleton generator (897 lines)
- `backend/mtgai/skeleton/__init__.py` — public exports
- `backend/mtgai/review/cli.py` — Typer CLI app
- `backend/mtgai/review/loaders.py` — data loading from output/
- `backend/mtgai/review/formatters.py` — Rich formatting helpers
- `backend/mtgai/review/__main__.py` — entry point
- `backend/tests/test_skeleton.py` — 75 tests
- `output/sets/ASD/skeleton.json` — 60-slot skeleton
- `output/sets/ASD/skeleton-overview.txt` — human-readable summary
- `output/sets/ASD/theme.json` — set theme definition
- `output/sets/ASD/set-config.json` — set configuration
