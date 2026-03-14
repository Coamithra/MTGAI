# Phase 4A-rev: Skeleton Revision + Targeted Regeneration

## Purpose

After 4A balance analysis identifies **set-level** structural issues (mechanic distribution, artifact density, complexity tier mismatches), this step fixes them by having an LLM propose slot changes and then regenerating only the affected cards.

This is distinct from the AI design review (4B-review), which fixes **card-level** issues (color pie violations, power level, templating). Set-level issues can't be fixed by reviewing individual cards — telling a reviewer "this should be a small creature" or "this should use Malfunction instead of Salvage" would just create new imbalances.

## Problem Statement (ASD Dev Set)

From `output/sets/ASD/reports/balance-analysis.json`:

| Issue | Details |
|-------|---------|
| Salvage over-represented | 12 actual vs 6 planned (2x over) |
| Malfunction under-represented | 3 actual vs 5 planned |
| Overclock under-represented | 1 actual vs 3 planned |
| Complexity tier mismatches | 11 cards (complex↔evergreen swaps) |
| Artifact density too low | 22 cards reference artifacts, only 6 artifacts exist |
| CMC gaps at 4-6 | Expected at 60 cards — no action for dev set |
| Red has no CMC 1 creature | 60-card budget effect — no action for dev set |

**Only the first 5 are actionable at dev-set scale.** CMC gaps and missing legendaries/signposts resolve at 280.

## Architecture

### Step 1: Compact Card Serialization

Serialize every card in the set to a compact one-line format for the LLM prompt:

```
W-C-01 | Cult Relic-Bearer | {1}{W} | Creature — Human Cleric 2/1 | Salvage 2 (Look at top 2...)
W-C-02 | Proclamation Enforcer | {2}{W} | Creature — Human Soldier 2/3 | vigilance, ETB each opponent loses 1 life you gain that much
```

Fields: `slot_id | name | mana_cost | type_line [P/T] | oracle_text (truncated to ~80 chars, no reminder text)`

At ~100-130 chars per card, 60 cards ≈ ~7-8k chars ≈ ~2k tokens. At 280 cards ≈ ~35k chars ≈ ~9k tokens. Easily fits.

### Step 2: Revision Prompt

Single LLM call (Opus 4.6, effort=max) with:

**System prompt**: You are an expert MTG set designer. You analyze set-wide structural problems and propose targeted fixes by reassigning skeleton slots.

**User prompt sections**:
1. **Compact card list** (from Step 1)
2. **Balance findings** (from `balance-analysis.json` — only set-level issues, not card-level)
3. **Mechanic definitions** (from `mechanics/approved.json` — full definitions with reminder text, rarity ranges, color assignments)
4. **Mechanic distribution targets** (from `mechanics/distribution.json` — planned vs actual)
5. **Set theme summary** (from `theme.json` — archetypes, creature types, flavor guidelines)
6. **Instructions**: "Propose a revision plan to fix the structural issues listed above. For each change, specify:"
   - `slot_id`: Which slot to change
   - `action`: One of `regenerate` (new card in same slot), `modify_slot` (change slot constraints then regenerate)
   - `new_constraints`: If modify_slot — what changes (e.g., `card_type: artifact_creature`, `mechanic_tag: complex`, `notes: "Must use Malfunction 1"`)
   - `reasoning`: Why this card was chosen for replacement (e.g., "generic vanilla creature, least load-bearing in white commons")
   - Rules:
     - Preserve load-bearing cards (signpost uncommons, key removal, archetype enablers, reprints)
     - Prefer replacing generic/vanilla cards over mechanically interesting ones
     - Don't change more slots than necessary
     - Each replacement must serve a specific structural need (don't just shuffle cards around)
     - New slot constraints must be achievable by the card generator (valid color/rarity/type/CMC combinations)

**Tool schema** (forced structured output):
```json
{
  "name": "propose_revision_plan",
  "input_schema": {
    "type": "object",
    "properties": {
      "analysis": {
        "type": "string",
        "description": "Brief analysis of the structural issues and overall revision strategy"
      },
      "changes": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "slot_id": {"type": "string"},
            "current_card_name": {"type": "string"},
            "action": {"type": "string", "enum": ["regenerate", "modify_slot"]},
            "new_constraints": {
              "type": "object",
              "description": "New slot constraints. Only include fields that change.",
              "properties": {
                "card_type": {"type": "string"},
                "cmc_target": {"type": "integer"},
                "mechanic_tag": {"type": "string"},
                "notes": {"type": "string", "description": "Generation guidance, e.g. 'Must use Malfunction 1' or 'Artifact creature with salvage synergy'"}
              }
            },
            "reasoning": {"type": "string"}
          },
          "required": ["slot_id", "current_card_name", "action", "reasoning"]
        }
      },
      "expected_improvements": {
        "type": "object",
        "description": "Expected post-revision mechanic distribution and artifact count",
        "properties": {
          "salvage_count": {"type": "integer"},
          "malfunction_count": {"type": "integer"},
          "overclock_count": {"type": "integer"},
          "artifact_count": {"type": "integer"}
        }
      }
    },
    "required": ["analysis", "changes", "expected_improvements"]
  }
}
```

### Step 3: Apply Revision Plan

For each change in the revision plan:

1. **Archive the old card**: Move `output/sets/ASD/cards/<old>.json` to `output/sets/ASD/cards/archive/<old>.json` (don't delete — we may want to compare)
2. **Update the skeleton slot** if `action == "modify_slot"`: Apply new constraints to the slot in `skeleton.json`
3. **Regenerate the card**: Use the existing 1C generation pipeline (`card_generator.py`) with the updated slot. The slot's `notes` field carries the revision guidance into the generation prompt.
4. **Validate**: Standard validation pipeline (8 validators + auto-fix)

### Step 4: Re-run Balance Analysis

After all changes applied, re-run `4A` balance checks on the revised set. If structural issues remain (e.g., LLM proposed too few changes, or new cards still don't use the right mechanics), loop back to Step 2 with the updated card list. Max 2 revision rounds to prevent cost runaway.

## Implementation

### New module: `backend/mtgai/generation/skeleton_reviser.py`

```python
# Key functions:

def serialize_card_compact(card: Card) -> str:
    """One-line card summary: slot_id | name | cost | type P/T | oracle (truncated)"""

def build_revision_prompt(
    cards: list[Card],
    balance_analysis: dict,
    mechanics: list[dict],
    distribution: dict,
    theme: dict,
) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt) for the revision LLM call."""

def parse_revision_plan(raw: dict) -> RevisionPlan:
    """Parse tool output into a structured RevisionPlan."""

def apply_revision_plan(
    plan: RevisionPlan,
    skeleton_path: Path,
    cards_dir: Path,
    archive_dir: Path,
) -> list[str]:
    """Archive old cards, update skeleton slots, return list of slot_ids to regenerate."""

def regenerate_slots(
    slot_ids: list[str],
    skeleton_path: Path,
    set_code: str,
) -> list[Card]:
    """Regenerate specific slots using existing card_generator pipeline."""

def run_revision(
    set_code: str,
    max_rounds: int = 2,
) -> RevisionReport:
    """Full revision pipeline: serialize → prompt → apply → regenerate → re-check → loop if needed."""
```

### Data model: `RevisionPlan`

```python
class SlotChange(BaseModel):
    slot_id: str
    current_card_name: str
    action: Literal["regenerate", "modify_slot"]
    new_constraints: dict | None = None
    reasoning: str

class RevisionPlan(BaseModel):
    analysis: str
    changes: list[SlotChange]
    expected_improvements: dict
```

## Integration with Existing Pipeline

- **Reads**: `skeleton.json`, `cards/*.json`, `balance-analysis.json`, `mechanics/approved.json`, `mechanics/distribution.json`, `theme.json`
- **Writes**: Updated `skeleton.json` (if slots modified), new card JSONs in `cards/`, archived cards in `cards/archive/`, `reports/revision-report.md`
- **Reuses**: `llm_client.generate_with_tool()`, `card_generator` batch generation (for regenerating specific slots), `validation` pipeline, `balance.py` analysis (for re-check)
- **Does not touch**: Any card not in the revision plan

## Cost Estimate

- **Revision prompt** (Step 2): ~2-3k input tokens (cards) + ~2k (balance + mechanics + instructions) ≈ ~5k input, ~2k output → ~$0.13/round
- **Regeneration** (Step 3): ~$0.046/card × ~10-15 cards ≈ ~$0.50-0.70/round
- **Total**: ~$0.65-0.85 per round, max 2 rounds ≈ **~$1.30-1.70**

## Slot Notes Integration

The skeleton slot `notes` field already exists and is included in the generation prompt via `format_slot_specs()`. The revision step sets this field to carry specific guidance:

```
notes: "Must use Malfunction 1. Artifact creature. Replace generic vanilla — set needs more Malfunction density and artifact targets for Salvage."
```

The card generator already reads `notes` and includes it in the slot spec section of the user prompt, so no prompt code changes needed.

## Output

- `output/sets/ASD/cards/archive/` — old versions of replaced cards
- `output/sets/ASD/reports/revision-report.md` — what changed, why, before/after mechanic distribution
- Updated `output/sets/ASD/skeleton.json` — slot constraints revised
- Updated `output/sets/ASD/cards/*.json` — regenerated cards
- Updated `output/sets/ASD/reports/balance-report.md` — re-run after revision

## Scaling to 280

Same process, same code. The compact serialization stays under ~9k tokens at 280 cards. The LLM may propose more changes (more slots to fix), but the per-card regeneration cost scales linearly. At 280 cards with ~30 slot changes: ~$0.13 (revision) + ~$1.40 (regeneration) ≈ ~$1.55/round.
