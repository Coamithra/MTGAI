# DEPRECATED: Phase 1B-8a: Review Loop A/B Test Plan

> **DEPRECATED** — This was the pre-test plan for strategies S1-S8. The A/B test has been
> completed (including S9 Council, added later). The winning strategy and full results are
> documented in **`learnings/phase1b.md`** (section "Winning strategy: Tiered council+iteration
> hybrid", lines 160-172). Use that as the source of truth, not this file.

## Goal

Find the best AI review-and-revise strategy for the card generation pipeline. Each strategy takes a generated card, reviews it, and produces a revised card (or returns the original if it's clean). The winning strategy gets productionized in Phase 1C.

## How to Run

Each strategy is a standalone Python script in `research/scripts/ab-test/`. Run any strategy independently:

```bash
cd C:\Programming\MTGAI
uv run --directory backend python research/scripts/ab-test/strategy_N.py
```

Each writes output to `output/sets/ASD/mechanics/ab-test/<strategy-name>/`.

## Test Cards (7 of 15)

Use these 7 cards from `output/sets/ASD/mechanics/test-cards-original.json` (indices are 0-based in the JSON array, 1-based in the card numbering):

| Card # | Array Index | Name | Human Verdict | Test Purpose |
|--------|-------------|------|---------------|-------------|
| 2 | 1 | Undergrowth Scrounger | FAIL | Missing reminder text |
| 5 | 4 | Subsurface Expedition Leader | FAIL | Missing reminder text + inconsistent caps |
| 6 | 5 | Defective Labor Drone | PASS | Regression — should stay clean |
| 7 | 6 | Unstable Welding Unit | FAIL | Haste + malfunction nonbo |
| 11 | 10 | Synaptic Overload | FAIL | Redundant conditional, above-rate, kitchen sink |
| 14 | 13 | Cascade Protocol | FAIL | False variability, above-rate, kitchen sink |
| 15 | 14 | Archscientist Vex, the Unbound | WARN | Test for overnerfing — power is intentional |

Load them like this:
```python
import json
from pathlib import Path

ALL_CARDS = json.loads(Path("C:/Programming/MTGAI/output/sets/ASD/mechanics/test-cards-original.json").read_text())
TEST_INDICES = [1, 4, 5, 6, 10, 13, 14]  # 0-based
TEST_CARDS = [ALL_CARDS[i] for i in TEST_INDICES]
```

## Shared Infrastructure

### API Setup
```python
import os
from pathlib import Path
from anthropic import Anthropic

_ENV_PATH = Path("C:/Programming/MTGAI/.env")
if _ENV_PATH.exists():
    for line in _ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

client = Anthropic()
```

### Models
- **Sonnet**: `claude-sonnet-4-20250514` (strategies 1-4)
- **Opus**: `claude-opus-4-20250514` (strategies 5-8)
- Temperature: 1.0 for all
- Max tokens: 4096 for review calls, 8192 for revision calls

### Mechanic Definitions
Load from `output/sets/ASD/mechanics/approved.json`. Include in every prompt as context. Format as:

```
Custom mechanics for this set:

**Salvage X** (keyword_ability)
Reminder text: (Look at the top X cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)
Scaling: 2-3 at common, 4-5 at uncommon, 6+ at rare/mythic.
Colors: W, U, G. Complexity: 1 (common-viable).
Design note: Malfunction cards are INTENTIONALLY above-rate — the delayed entry IS the drawback.

**Malfunction N** (keyword_ability)
Reminder text: (This permanent enters tapped with N malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.)
Scaling: 1 at common, 2 at uncommon, 2-3 at rare/mythic.
Colors: W, U, R. Complexity: 2.
Design note: Enters tapped is the key tempo cost. Cards with malfunction are intentionally above-rate for their mana cost.

**Overclock** (keyword_action)
Reminder text: (Exile the top three cards of your library. You may play them until end of turn.)
Colors: U, R, B. Complexity: 3 (uncommon+ only, never at common).
Design note: High risk/reward. Always exiles exactly 3 cards.
```

### Card Format for Prompts
Format each card as:
```
Name: {name}
Mana Cost: {mana_cost}
Type: {type_line}
Rarity: {rarity}
Oracle Text: {oracle_text}
P/T: {power}/{toughness}  (omit if null)
```

Do NOT include the JSON metadata fields (`_mechanic`, `_scores`, `keywords`, `design_notes`) in review prompts — the reviewer should judge the card as printed, not the metadata.

### Revised Card Extraction
Use tool_use to extract the revised card as structured JSON. Tool schema:

```python
REVISED_CARD_TOOL = {
    "name": "submit_revised_card",
    "description": "Submit the final revised card, or the original card unchanged if no issues were found.",
    "input_schema": {
        "type": "object",
        "properties": {
            "changed": {
                "type": "boolean",
                "description": "True if the card was modified, False if returned as-is."
            },
            "verdict": {
                "type": "string",
                "enum": ["OK", "REVISED", "UNFIXABLE"],
                "description": "OK = no changes needed. REVISED = issues found and fixed. UNFIXABLE = issues found but can't be fixed without human input."
            },
            "issues_found": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of issues identified (empty if OK)."
            },
            "name": {"type": "string"},
            "mana_cost": {"type": "string"},
            "type_line": {"type": "string"},
            "oracle_text": {"type": "string"},
            "power": {"type": ["string", "null"]},
            "toughness": {"type": ["string", "null"]},
            "rarity": {"type": "string"},
            "flavor_text": {"type": ["string", "null"]},
        },
        "required": ["changed", "verdict", "issues_found", "name", "mana_cost", "type_line", "oracle_text", "rarity"]
    }
}
```

### Output Format
Each strategy writes to `output/sets/ASD/mechanics/ab-test/<strategy-name>/`:

```
<strategy-name>/
  summary.md              # Strategy description, total cost, per-card verdicts
  card-02-undergrowth-scrounger.md
  card-05-subsurface-expedition-leader.md
  card-06-defective-labor-drone.md
  card-07-unstable-welding-unit.md
  card-11-synaptic-overload.md
  card-14-cascade-protocol.md
  card-15-archscientist-vex.md
```

Each card report must contain (in this order):

```markdown
# Card N: {name} — Strategy: {strategy_name}

## A) Original Card
{card JSON, pretty-printed}

## B) Review Process

### Step 1: {description}
**Prompt sent:**
> {the exact prompt text}

**Response:**
> {the full AI response}

### Step 2: {description}
... (repeat for each AI call)

### Programmatic Analysis
- Reminder text check: {result}
- {any other automated checks}

## C) Revised Card
{revised card JSON, pretty-printed — or "No changes (OK)" if clean}

**Changes made:**
- {bullet list of changes, or "None"}

## D) Cost
- API calls: {N}
- Input tokens: {N}
- Output tokens: {N}
- Cost: ${X.XX}
```

The `summary.md` should contain:

```markdown
# Strategy: {name}

## Description
{how this strategy works}

## Results

| Card | Verdict | Issues Found | Changes Made | Cost |
|------|---------|-------------|-------------|------|
| ... | ... | ... | ... | ... |

## Total Cost
- API calls: {N}
- Total tokens: {in} in / {out} out
- Total cost: ${X.XX}
```

---

## Strategy 1: Simple (Sonnet)

**Model**: claude-sonnet-4-20250514
**Output dir**: `ab-test/s1-simple-sonnet/`

### Flow
1. Single prompt with card + mechanic definitions
2. AI reviews and either returns OK or a revised card
3. Extract result via tool_use

### Prompt
```
You are a senior Magic: The Gathering card designer. Review this custom card for the set "Anomalous Descent."

{mechanic definitions}

Card to review:
{card formatted as text}

Critically review this card and provide an improved version based on your findings. If the card is fine, return it unchanged with verdict OK.
```

Then force the `submit_revised_card` tool.

---

## Strategy 2: Iterative (Sonnet)

**Model**: claude-sonnet-4-20250514
**Output dir**: `ab-test/s2-iterative-sonnet/`

### Flow
1. Same prompt as Strategy 1
2. If the AI returns REVISED, take the revised card and run it through the same prompt again
3. Repeat until OK is returned or max 5 iterations
4. Log every iteration

### Prompt (same as Strategy 1, but on iterations 2+, the input card is the previously revised version)

Each iteration uses a fresh conversation (no history carried over — the revised card is the only context).

---

## Strategy 3: Detailed (Sonnet)

**Model**: claude-sonnet-4-20250514
**Output dir**: `ab-test/s3-detailed-sonnet/`

### Flow
1. Single prompt with detailed review checklist + pointed questions
2. AI reviews against every criterion and provides revised card
3. Extract result via tool_use

### Prompt
```
You are a senior Magic: The Gathering card designer. Review this custom card for the set "Anomalous Descent."

{mechanic definitions}

Card to review:
{card formatted as text}

Review this card thoroughly. At minimum, check every criterion below (state PASS or describe the issue for each), but also flag anything else you notice.

**Templating & Rules Text:**
- Is the oracle text valid MTG rules text?
- Does every custom mechanic (salvage, malfunction, overclock) have reminder text on first use?
- Is capitalization consistent (keyword capitalized at start of ability, lowercase mid-sentence)?
- Does the card use current MTG templating ("enters" not "enters the battlefield")?

**Keyword Interactions:**
- Are there any keywords that are negated or made useless by other abilities? (e.g., haste on a creature that always enters tapped)
- If there's a conditional ("if you X this turn"), can the condition actually be false during normal play?

**Balance:**
- Is the power level appropriate for the mana cost AND rarity? Compare to 2-3 well-known printed MTG cards at similar cost.
- Note: malfunction cards are intentionally above-rate — the delayed entry IS the drawback.

**Design:**
- Does the card have a focused purpose, or is it kitchen sink (3+ unrelated effects)?
- If effects are variable (deal X damage, etc.), is the variability real or does it always resolve to the same value?
- Does the card create interesting gameplay decisions?

**Color Pie:**
- Are all abilities appropriate for this card's color(s)?

After your review, provide the revised card. If no issues were found, return it unchanged with verdict OK.
```

Then force the `submit_revised_card` tool.

---

## Strategy 4: Split (Sonnet)

**Model**: claude-sonnet-4-20250514
**Output dir**: `ab-test/s4-split-sonnet/`

### Flow
1. **Pass 1 — Templating**: Ask AI to review only wording, templating, reminder text
2. **Pass 2 — Mechanics**: Ask AI to review gameplay mechanics, keyword interactions, design
3. **Pass 3 — Balance**: Ask AI to review power level, compare to printed cards
4. Collect all issues from all 3 passes
5. If any issues found, make a single revision call with all collected feedback
6. Extract result via tool_use

### Prompts

**Pass 1 — Templating:**
```
You are an MTG rules text editor. Focus primarily on the templating and wording of this custom card, but flag anything else you notice.

{mechanic definitions}

Card:
{card formatted as text}

Check:
- Is the oracle text valid MTG rules text using current templating conventions?
- Does every custom mechanic (salvage, malfunction, overclock) include reminder text in parentheses on its first use?
- Is keyword capitalization consistent?
- Are ability words, keyword abilities, and keyword actions used correctly?

List any templating issues found, or say "PASS" if the templating is correct.
```

**Pass 2 — Mechanics:**
```
You are an MTG game designer. Focus primarily on the gameplay mechanics and design of this custom card, but flag anything else you notice.

{mechanic definitions}

Card:
{card formatted as text}

Check:
- Are there any keyword nonbos (keywords negated by other abilities on the card)?
- If there's a conditional, can it actually be false during normal play?
- Is this kitchen sink design (3+ unrelated effects piled together)?
- If effects are variable, is the variability real or always the same value?
- Does the design have a focused purpose?

List any design issues found, or say "PASS" if the design is sound.
```

**Pass 3 — Balance:**
```
You are an MTG development/play design expert. Focus primarily on the power level of this custom card, but flag anything else you notice.

{mechanic definitions}

Card:
{card formatted as text}

Check:
- Is the power level appropriate for the mana cost AND rarity?
- Compare to 2-3 well-known printed MTG cards at similar mana cost and rarity.
- Note: malfunction cards are intentionally above-rate — the delayed entry IS the drawback. Do not flag these for being above-rate.
- Note: mythic rares are allowed to be powerful build-arounds. Do not nerf mythics to rare power level.

State whether the balance is PASS, or describe the specific balance issue with card comparisons.
```

**Revision call (if any issues found):**
```
You are a senior MTG card designer. Revise this card based on the following review feedback.

{mechanic definitions}

Original card:
{card formatted as text}

Issues found:
- Templating: {pass 1 findings}
- Mechanics: {pass 2 findings}
- Balance: {pass 3 findings}

Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues.
```

Then force the `submit_revised_card` tool.

---

## Strategies 5-8: Opus Variants

Identical to strategies 1-4 but using `claude-opus-4-20250514` instead of `claude-sonnet-4-20250514`.

| Strategy | Mirror of | Output dir |
|----------|-----------|------------|
| 5 | 1 (Simple) | `ab-test/s5-simple-opus/` |
| 6 | 2 (Iterative) | `ab-test/s6-iterative-opus/` |
| 7 | 3 (Detailed) | `ab-test/s7-detailed-opus/` |
| 8 | 4 (Split) | `ab-test/s8-split-opus/` |

---

## Evaluation Criteria (Human)

After all strategies run, the human reviews the output reports and judges:

1. **FAIL cards**: Did the revision actually fix the issue? Is the fix good?
2. **PASS card (Defective Labor Drone)**: Was it left alone? If changed, was the change harmful?
3. **WARN card (Archscientist Vex)**: Was it overnerfed? Did it preserve the intentionally high mythic power level?
4. **Overall quality**: Do the revised cards feel like well-designed MTG cards?
5. **Cost efficiency**: Is the cost/quality tradeoff acceptable for 280 cards?

## Cost Budget

Estimated total across all 8 strategies × 7 cards:
- Sonnet strategies (1-4): ~$2-4
- Opus strategies (5-8): ~$8-15
- **Total: ~$10-19**

All within the $30 project budget for experimentation.
