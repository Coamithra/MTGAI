# Phase 1: Set Design Engine — Detailed Implementation Plan

> **Prerequisite**: Phase 0 (Research Sprint) must be complete. This plan references outputs from 0A (set structure data), 0C (project setup, card schema), 0D (LLM strategy), and 0E (proven prompt templates).

## Quick Start (Context Reset)

**Prerequisites**: Phase 0 complete. Specifically need:
- `research/set-template.json` (from 0A) — slot allocation targets
- `research/set-design.md` (from 0A) — design rules and constraints
- `research/llm-strategy.md` (from 0D) — model selection, prompting architecture
- `research/prompt-templates/BEST-SETTINGS.md` (from 0E) — proven prompt templates
- Project skeleton with card schema (from 0C) — `backend/mtgai/models/`

**Read first**: This plan, plus skim the prerequisite files listed above.

**Start with**: Phase 1A (Set Skeleton Generator).

## Deliverables Checklist

### Phase 1A: Set Skeleton Generator
- [ ] `output/sets/<code>/skeleton.json` — slot allocation matrix
- [ ] `output/sets/<code>/skeleton-overview.txt` — human-readable summary
- [ ] Draft archetype definitions (10 color pairs) in set metadata
- [ ] CLI commands working: `mtgai review list`, `mtgai review show`, `mtgai review stats`
- [ ] CLI architecture designed (Typer-based command groups, stubs for Phase 3A commands)
- [ ] Unit tests for all skeleton constraints passing
- [ ] `learnings/phase1a.md`

### Phase 1B: Mechanic Designer
- [ ] 2-4 set-specific mechanics defined with reminder text and rules templates
- [ ] Mechanics validated against color pie rules
- [ ] Mechanic distribution across rarities assigned
- [ ] Evergreen keyword assignments per color confirmed
- [ ] Human approval of each mechanic documented
- [ ] `learnings/phase1b.md`

### Phase 1C: Card Generator
- [ ] All ~280 card JSON files in `output/sets/<code>/cards/`
- [ ] `mtgai.validation` library complete:
  - [ ] `rules_text.py` — MTG rules text grammar validation
  - [ ] `balance.py` — power level / mana cost balance checks
  - [ ] `color_pie.py` — color pie violation detection
  - [ ] `text_overflow.py` — card text length / overflow estimation
  - [ ] `uniqueness.py` — duplicate / near-duplicate detection
  - [ ] `spelling.py` — spell check on card text fields
- [ ] Validation-retry loop functional (generate → validate → retry with feedback)
- [ ] All generated cards pass automated validation or are flagged for human review
- [ ] Reprint cards selected and integrated where appropriate
- [ ] `learnings/phase1c.md`

**Done when**: Full set of ~280 cards exists as validated JSON, skeleton constraints are satisfied, all validation tests pass, and CLI review tools allow human inspection.

---

## Phase 1A: Set Skeleton Generator

### 1A.1 Inputs & Outputs

**User Inputs** (via CLI or config file):

```python
@dataclass
class SetConfig:
    name: str                    # e.g., "Whispers of the Void"
    code: str                    # e.g., "WTV" (3-letter set code)
    theme: str                   # e.g., "Cosmic horror meets deep-sea exploration"
    flavor_description: str      # 2-3 paragraph world-building blurb
    card_count: int              # Target card count (default: 271)
    mechanic_count: int          # Number of new mechanics (default: 3, range 2-4)
    reprint_slots: int           # Number of reserved reprint slots (default: ~15-25)
    special_constraints: list[str]  # e.g., ["no planeswalkers", "artifact subtheme in UB"]
```

**System Output**: A `SetSkeleton` containing:

1. **Slot allocation matrix** — every card slot defined by (color, rarity, card type, CMC range, archetype tag, mechanic assignment)
2. **Draft archetype definitions** — 10 color-pair archetypes with strategy descriptions and key mechanic associations
3. **Mechanic slot map** — which slots are reserved for new mechanics vs evergreen keywords
4. **Balance report** — confirmation that all constraints pass, with per-color/rarity statistics
5. **Skeleton JSON file** — saved to `output/sets/<code>/skeleton.json`
6. **Skeleton overview** — a human-readable summary printed to console and saved as `output/sets/<code>/skeleton-overview.txt`

---

### 1A.2 Slot Allocation Algorithm

#### Reference Data: Real Set Distributions

Based on recent standard sets (Bloomburrow, Duskmourn: House of Horror, Outlaws of Thunder Junction, Murders at Karlov Manor), modern premier sets follow this approximate structure:

| Rarity | Count | Notes |
|--------|-------|-------|
| Common | 101 | ~20 per color + ~1 colorless/artifact |
| Uncommon | 80 | ~12-14 per color + 10-15 multicolor (gold) + 3-5 artifacts |
| Rare | 60 | ~7-8 per color + 10-15 multicolor + 3-5 colorless |
| Mythic Rare | 20 | ~2 per color + 5-8 multicolor + 2-3 colorless |
| Basic Land | 5 | 1 per basic type (not counted in 271) |
| **Total** | **~266-271** | Excluding basic lands and tokens |

#### Card Type Distribution Per Color (at Common)

Each color gets approximately 20 commons:

| Color | Creatures | Instants | Sorceries | Enchantments | Artifacts | Total |
|-------|-----------|----------|-----------|--------------|-----------|-------|
| White | 10-11 | 3-4 | 2 | 2-3 | 0-1 | ~20 |
| Blue | 8-9 | 4-5 | 2-3 | 1-2 | 0-1 | ~20 |
| Black | 9-10 | 3-4 | 2-3 | 1-2 | 0-1 | ~20 |
| Red | 9-10 | 3-4 | 3-4 | 0-1 | 0-1 | ~20 |
| Green | 10-12 | 2-3 | 1-2 | 1-2 | 0-1 | ~20 |
| Colorless | 0-1 | 0 | 0 | 0 | 0-1 | ~1 |

**Key ratio**: Creatures make up ~50-60% of commons, slightly less at uncommon (~45-50%), and more varied at rare/mythic.

#### CMC Distribution Target (Commons, per color)

The mana curve for limited play is critical. Target distribution per 20-card common color block:

| CMC | Count | Percentage |
|-----|-------|------------|
| 1 | 2-3 | 10-15% |
| 2 | 4-5 | 20-25% |
| 3 | 4-5 | 20-25% |
| 4 | 3-4 | 15-20% |
| 5 | 2-3 | 10-15% |
| 6+ | 1-2 | 5-10% |

#### Algorithm: Skeleton Construction

```
function build_skeleton(config: SetConfig) -> SetSkeleton:
    1. Initialize empty slot matrix
    2. Allocate rarity buckets:
       - commons = 101, uncommons = 80, rares = 60, mythics = 20
       - Subtract reprint_slots proportionally (most reprints at common/uncommon)
    3. For each rarity:
       a. Distribute across 5 colors (equal shares, ±1)
       b. Allocate multicolor slots:
          - Common: 0 multicolor (modern sets sometimes have 0-5)
          - Uncommon: 10 multicolor (1 per color pair — the "signpost uncommons")
          - Rare: 10-15 multicolor
          - Mythic: 5-8 multicolor
       c. Allocate colorless/artifact slots (2-5% of each rarity)
    4. For each (color, rarity) block:
       a. Assign card types using target ratios (creature-heavy at common)
       b. Assign CMC values following the curve targets
       c. Tag slots with archetype associations (1-2 archetypes per slot)
       d. Mark mechanic slots (new mechanic vs evergreen)
    5. Run all balance constraint validators (see 1A.5)
    6. If constraints fail, adjust via hill-climbing:
       - Identify violated constraint
       - Find swap candidates (change type, CMC, or move between colors)
       - Apply swap, re-validate
       - Max 1000 iterations before flagging for human intervention
    7. Return completed skeleton
```

#### Multicolor Slot Distribution

Multicolor cards follow the draft archetype structure:

| Rarity | Count | Pattern |
|--------|-------|---------|
| Uncommon | 10 | Exactly 1 "signpost" per color pair — defines the archetype |
| Rare | 10-15 | 1-2 per color pair, focusing on the most compelling archetypes |
| Mythic | 5-8 | Splashy multicolor cards, not all pairs need representation |

---

### 1A.3 Draft Archetype Design

Every modern MTG set defines 10 two-color draft archetypes. Each archetype has:
- A **mechanical identity** (what the deck *does*)
- A **signpost uncommon** (a multicolor uncommon that embodies the strategy)
- **Supporting cards** across both colors at common/uncommon that feed the archetype

#### Example Archetypes from Real Sets

**Bloomburrow (2024):**
| Color Pair | Archetype | Strategy |
|-----------|-----------|----------|
| WU | Birds (Flying) | Go-wide evasion with flying creatures |
| WB | Bats (Lifegain) | Drain life, bat tokens, lifegain payoffs |
| WR | Mice (Go-wide Aggro) | Small tokens, team pump effects |
| WG | Rabbits (Tokens) | Create tokens, go wide, green power buffs |
| UB | Rats (Threshold/graveyard) | Mill, threshold effects, rat synergy |
| UR | Otters (Spellslinger) | Prowess-like, cast noncreatures for value |
| UG | Frogs (Ramp/counters) | +1/+1 counters, land drops matter |
| BR | Lizards (Aggro/sacrifice) | Sacrifice for value, aggressive curve |
| BG | Squirrels (Food/recursion) | Food tokens, graveyard recursion |
| RG | Raccoons (Power matters) | High-power creatures, ferocious effects |

**Duskmourn: House of Horror (2024):**
| Color Pair | Archetype | Strategy |
|-----------|-----------|----------|
| WU | Enchantment control | Rooms, enchantment synergy |
| WB | Reanimator | Survive, bring back creatures |
| WR | Aggro survivors | Fast creatures, survival triggers |
| WG | Enchantress | Enchantment value engine |
| UB | Eerie (enchantment ETB) | Trigger "eerie" when enchantments enter |
| UR | Rooms/artifacts | Open rooms, artifact synergy |
| UG | Manifest dread | Face-down creatures, turn face-up for value |
| BR | Sacrifice/delirium | Sacrifice for value, card types in graveyard |
| BG | Delirium | Fill graveyard with card types for bonuses |
| RG | High-power aggro | Big creatures, power-matters |

#### Archetype Definition Data Model

```python
@dataclass
class DraftArchetype:
    color_pair: str              # e.g., "WU", "BR"
    name: str                    # e.g., "Eerie Control"
    strategy: str                # 1-2 sentence description
    primary_mechanic: str        # Which set mechanic this archetype uses most
    secondary_mechanics: list[str]  # Supporting mechanics
    key_card_types: list[str]    # e.g., ["enchantments", "creatures with ETB"]
    speed: str                   # "aggro", "midrange", "control"
    signpost_slot_id: str        # Reference to the signpost uncommon slot
    supporting_slot_ids: list[str]  # Slots tagged as archetype support
```

#### Archetype Generation Process

1. **LLM generates 10 archetype proposals** based on set theme, using few-shot examples from real sets
2. **Constraint check**: Each color must appear in exactly 4 archetypes (each color has 4 pair partners)
3. **Speed diversity**: At least 2 aggro, 2 control, 6 midrange (approximate — sets lean midrange)
4. **Mechanic coverage**: Each new set mechanic should appear as primary mechanic in at least 2 archetypes
5. **Human review**: Present archetypes for approval before card generation begins

---

### 1A.4 Mechanic Slot Assignment

Each card slot is tagged with its mechanic expectations:

| Slot Tag | Meaning |
|----------|---------|
| `new_mechanic:<name>` | This slot uses a specific new set mechanic |
| `evergreen` | This slot uses a standard evergreen keyword |
| `vanilla` | No keywords (important for common creatures — ~2-3 per color) |
| `french_vanilla` | Evergreen keyword only, no rules text beyond that |
| `complex` | Full rules text, possibly combining mechanics |

#### Distribution Rules

- **New mechanics at common**: Each new mechanic appears on 4-8 commons (2-3 per relevant color)
- **New mechanics at uncommon**: Each new mechanic appears on 3-6 uncommons
- **New mechanics at rare/mythic**: 1-3 per mechanic (the "pushed" or "build-around" versions)
- **As-fan target**: Each new mechanic should have an as-fan of 1.0-1.5 at common/uncommon (you see ~1-1.5 copies per booster pack on average)
- **Vanilla/french vanilla at common**: At least 2-3 vanilla creatures per color, plus 3-4 french vanilla
- **Complexity gradient**: Commons are simplest (New World Order), rares can be complex

#### As-Fan Calculation

```
as_fan(mechanic) = (count_in_commons / total_commons) * 10
                 + (count_in_uncommons / total_uncommons) * 3
                 + (count_in_rares_and_mythics / total_rares_and_mythics) * 1.14
```

(Based on a standard 14-card booster: 10C + 3U + 1R/M, approximately)

---

### 1A.5 Balance Constraints

Every constraint below must pass for the skeleton to be accepted. Constraints are implemented as individual validator functions in `mtgai.skeleton.constraints`.

#### Hard Constraints (Skeleton fails if violated)

| # | Constraint | Rule | Rationale |
|---|-----------|------|-----------|
| 1 | **Color balance** | Each color has exactly the same number of commons (±0) and within ±1 at each other rarity | Fundamental fairness |
| 2 | **Creature density (common)** | Each color has at least 8 creatures at common (out of ~20) | Limited needs creatures |
| 3 | **Creature density (overall)** | Total creatures ≥ 50% of set | Standard for limited play |
| 4 | **Removal density** | Each color has at least 2 removal spells at common, 1-2 at uncommon | Limited requires answers |
| 5 | **Mana curve** | Each color's common creatures have at least 1 card at CMC 1, 2, 3, 4, 5 | Curve-out must be possible |
| 6 | **Signpost uncommons** | Exactly 10 multicolor uncommons (1 per pair) | Defines draft archetypes |
| 7 | **Rarity totals** | C=101, U=80, R=60, M=20 (±5 for set-specific adjustments) | Standard set size |
| 8 | **No color in mythic > 3** | No single color has more than 3 mythics (mono-colored) | Prevent skew |
| 9 | **Legendary count** | At least 1 legendary creature per color at rare+, ~15-25 total legendaries | Commander demand, story characters |

#### Soft Constraints (Warning if violated, does not block)

| # | Constraint | Target | Tolerance |
|---|-----------|--------|-----------|
| 10 | **Mana fixing** | At least 5 mana-fixing cards (lands or artifacts) in the set | ±2 |
| 11 | **Combat tricks at common** | Each color has 1-2 combat tricks at common | ±1 |
| 12 | **Card draw** | Blue has the most card-draw effects; each color has at least 1 | — |
| 13 | **Enchantment removal** | White and green have enchantment removal at common/uncommon | Must exist |
| 14 | **Artifact removal** | Red and green have artifact removal at common/uncommon | Must exist |
| 15 | **Evasion** | Blue and white have the most evasion creatures at common | — |
| 16 | **Vanilla count** | At least 2 vanilla creatures per color at common | ±1 |
| 17 | **Mechanic as-fan** | Each new mechanic has as-fan ≥ 1.0 at common/uncommon | — |
| 18 | **Archetype support** | Each archetype has ≥ 6 supporting cards at common/uncommon across its two colors | — |

---

### 1A.6 CLI Review Tool

The CLI is invoked as `python -m mtgai.review` and provides three primary commands.

#### `list` — List cards with filtering

```bash
# List all cards in the set
python -m mtgai.review list

# Filter by color
python -m mtgai.review list --color white
python -m mtgai.review list --color WU        # multicolor pair

# Filter by rarity
python -m mtgai.review list --rarity common

# Filter by card type
python -m mtgai.review list --type creature

# Filter by status
python -m mtgai.review list --status draft
python -m mtgai.review list --status validated

# Filter by CMC
python -m mtgai.review list --cmc 3
python -m mtgai.review list --cmc 4+          # 4 or greater

# Filter by archetype tag
python -m mtgai.review list --archetype WU

# Filter by mechanic
python -m mtgai.review list --mechanic "Descend"

# Combine filters
python -m mtgai.review list --color red --rarity common --type creature

# Sort options
python -m mtgai.review list --sort cmc        # default
python -m mtgai.review list --sort name
python -m mtgai.review list --sort collector-number
```

**Output format** (compact table):

```
 #   | Name                  | Cost  | Type               | Rarity | P/T | Status
-----+-----------------------+-------+--------------------+--------+-----+-----------
 001 | Void Sentinel         | {1}{W}| Creature — Human   | C      | 2/2 | validated
 002 | Abyssal Ward          | {W}   | Instant            | C      | —   | draft
 003 | Deep-Sea Chaplain     | {2}{W}| Creature — Merfolk | C      | 2/3 | draft
 ...
Showing 20 of 271 cards (filtered: color=white, rarity=common)
```

For skeleton slots that don't yet have a generated card (Phase 1A output), display the slot spec:

```
 Slot | Color | Rarity | Type     | CMC | Archetype | Mechanic      | Status
------+-------+--------+----------+-----+-----------+---------------+---------
 W-C01| W     | C      | Creature | 1   | WR, WG    | evergreen     | empty
 W-C02| W     | C      | Creature | 2   | WU        | new:Descend   | empty
 W-C03| W     | C      | Creature | 2   | WB, WR    | french_vanilla| empty
 ...
```

#### `show` — Pretty-print a single card

```bash
python -m mtgai.review show "Void Sentinel"
python -m mtgai.review show 001              # by collector number
python -m mtgai.review show W-C01            # by slot ID (skeleton mode)
```

**Output format** (full card display):

```
╔══════════════════════════════════════════════╗
║  Void Sentinel                        {1}{W} ║
╠══════════════════════════════════════════════╣
║  Creature — Human Soldier                    ║
╠══════════════════════════════════════════════╣
║                                              ║
║  Vigilance                                   ║
║                                              ║
║  When Void Sentinel enters, you gain 2 life. ║
║                                              ║
╠══════════════════════════════════════════════╣
║  "The abyss stares, but I do not blink."     ║
╠══════════════════════════════════════════════╣
║                                        2/3   ║
╚══════════════════════════════════════════════╝
  Collector #: 001 | Rarity: Common | Status: validated
  Slot: W-C01 | Archetypes: WR, WG | Mechanic: evergreen
  Art: not generated | Render: not generated
  Validation: ✓ rules_text ✓ balance ✓ overflow ✓ color_pie ✓ spelling
```

#### `stats` — Set statistics summary

```bash
python -m mtgai.review stats
python -m mtgai.review stats --detailed       # per-color breakdown
python -m mtgai.review stats --curve           # mana curve visualization
python -m mtgai.review stats --archetypes      # archetype support stats
```

**Output format** (default):

```
Set: Whispers of the Void (WTV) — 271 cards

Rarity Distribution:
  Common:      101 (37.3%)
  Uncommon:     80 (29.5%)
  Rare:         60 (22.1%)
  Mythic Rare:  20 ( 7.4%)
  Basic Land:    5 ( 1.8%)
  Reprints:     18 ( 6.6%) [across all rarities]

Color Distribution (mono-colored):
         C     U     R     M   Total
  W     20    14     8     2     44
  U     20    14     8     2     44
  B     20    14     8     2     44
  R     20    14     8     2     44
  G     21    14     8     2     45
  Multi  0    10    15     7     32
  CL     0     0     5     3      8

Card Types:
  Creatures:      155 (57.2%)
  Instants:        38 (14.0%)
  Sorceries:       28 (10.3%)
  Enchantments:    22 ( 8.1%)
  Artifacts:       15 ( 5.5%)
  Planeswalkers:    3 ( 1.1%)
  Lands:           10 ( 3.7%)

Pipeline Status:
  Empty:       148 (54.6%)
  Draft:        52 (19.2%)
  Validated:    45 (16.6%)
  Approved:     26 ( 9.6%)

Constraint Check: 9/9 hard ✓ | 8/9 soft ✓ (1 warning)
  ⚠ Soft #11: Red has 0 combat tricks at common (target: 1-2)
```

**`--curve` output** (ASCII mana curve):

```
Common Creature Mana Curve (White):
CMC 1: ██░░░░░░░░ 2
CMC 2: █████░░░░░ 5
CMC 3: ████░░░░░░ 4
CMC 4: ███░░░░░░░ 3
CMC 5: ██░░░░░░░░ 2
CMC 6: █░░░░░░░░░ 1
```

---

### 1A.7 Data Model

#### `skeleton.json` Structure

```json
{
  "set": {
    "name": "Whispers of the Void",
    "code": "WTV",
    "theme": "Cosmic horror meets deep-sea exploration",
    "flavor_description": "...",
    "card_count": 271,
    "created_at": "2026-03-08T14:00:00Z",
    "version": 1
  },
  "archetypes": [
    {
      "color_pair": "WU",
      "name": "Deep Currents Control",
      "strategy": "Use evasive creatures and enchantment-based removal to control the board while draining the opponent's resources.",
      "primary_mechanic": "Descend",
      "secondary_mechanics": ["flying", "ward"],
      "speed": "control",
      "signpost_slot_id": "MULTI-U-01"
    }
  ],
  "mechanics": [
    {
      "name": "Descend",
      "type": "keyword_action",
      "reminder_text": "(To descend, mill two cards, then you may put a permanent card from among them onto the battlefield tapped.)",
      "colors": ["W", "U", "B"],
      "rarities": ["common", "uncommon", "rare", "mythic"],
      "slot_count": { "common": 8, "uncommon": 5, "rare": 3, "mythic": 1 }
    }
  ],
  "slots": [
    {
      "slot_id": "W-C-01",
      "color": "W",
      "rarity": "common",
      "card_type": "creature",
      "cmc_target": 1,
      "archetype_tags": ["WR", "WG"],
      "mechanic_tag": "evergreen",
      "is_reprint_slot": false,
      "card_id": null,
      "notes": ""
    },
    {
      "slot_id": "W-C-02",
      "color": "W",
      "rarity": "common",
      "card_type": "creature",
      "cmc_target": 2,
      "archetype_tags": ["WU"],
      "mechanic_tag": "new:Descend",
      "is_reprint_slot": false,
      "card_id": null,
      "notes": ""
    }
  ],
  "reprint_slots": [
    {
      "slot_id": "REPRINT-01",
      "rarity": "common",
      "color": "W",
      "scryfall_id": null,
      "card_name": null,
      "reason": "Common removal spell"
    }
  ],
  "balance_report": {
    "hard_constraints": {
      "color_balance": { "passed": true, "details": "All colors have 20 commons" },
      "creature_density_common": { "passed": true, "details": "Min 9, Max 11 creatures per color" }
    },
    "soft_constraints": {
      "mana_fixing": { "passed": true, "details": "7 fixing cards in set" },
      "combat_tricks": { "passed": false, "details": "Red has 0 combat tricks at common" }
    },
    "timestamp": "2026-03-08T14:05:00Z"
  }
}
```

#### `cards/<collector_number>_<slug>.json` Structure

Individual card files are stored in `output/sets/<code>/cards/` once generated (Phase 1C). The skeleton only contains slot definitions; card JSON files are created during generation.

```json
{
  "card_id": "wtv-001",
  "slot_id": "W-C-01",
  "collector_number": "001",
  "name": "Void Sentinel",
  "mana_cost": "{1}{W}",
  "cmc": 2,
  "colors": ["W"],
  "color_identity": ["W"],
  "type_line": "Creature — Human Soldier",
  "supertypes": [],
  "card_types": ["Creature"],
  "subtypes": ["Human", "Soldier"],
  "rules_text": "Vigilance\nWhen Void Sentinel enters, you gain 2 life.",
  "flavor_text": "\"The abyss stares, but I do not blink.\"",
  "power": "2",
  "toughness": "3",
  "loyalty": null,
  "rarity": "common",
  "keywords": ["Vigilance"],
  "mechanic_tags": ["evergreen"],
  "archetype_tags": ["WR", "WG"],
  "is_reprint": false,
  "reprint_source": null,
  "status": "validated",
  "validation_results": {
    "rules_text": { "passed": true },
    "balance": { "passed": true, "score": 0.82 },
    "overflow": { "passed": true, "estimated_lines": 3 },
    "color_pie": { "passed": true },
    "spelling": { "passed": true },
    "uniqueness": { "passed": true, "nearest_distance": 0.73 }
  },
  "generation_metadata": {
    "attempt": 1,
    "model": "claude-sonnet-4-20250514",
    "prompt_hash": "a3f8c...",
    "timestamp": "2026-03-08T15:30:00Z",
    "temperature": 0.7
  },
  "art_prompt": null,
  "art_path": null,
  "render_path": null
}
```

---

## Phase 1B: Mechanic Designer

### 1B.1 Mechanic Generation Process

#### Step-by-Step Flow

1. **Context Assembly**: Gather inputs for the LLM prompt:
   - Set theme and flavor description (from `SetConfig`)
   - Draft archetype definitions (from skeleton)
   - List of recent set mechanics to avoid repetition (from Phase 0A research data)
   - Color pie rules document (from Phase 0A research)
   - Target: generate `mechanic_count` new mechanics (default 3, range 2-4)

2. **LLM Generation Call**: Send a structured prompt requesting:
   - Mechanic name
   - Mechanic type: keyword ability, keyword action, ability word, or spell mechanic
   - Colors the mechanic appears in (1-3 colors typically)
   - Reminder text
   - Rules text template with placeholder `~` for card name
   - 3 example cards at different rarities showing the mechanic
   - Design rationale: how it connects to the set theme
   - Complexity rating: 1 (common-viable) to 3 (rare+ only)

3. **Parallel Generation**: Generate twice as many mechanics as needed (e.g., 6-8 candidates for 3 slots), then select the best via scoring and human approval.

4. **Mechanic Scoring** (automated):
   - **Flavor fit** (0-10): Does it match the set theme? (LLM-evaluated)
   - **Novelty** (0-10): How different is it from existing MTG mechanics? (checked against known mechanics list)
   - **Parasitism score** (0-10, lower is better): Can it work with cards outside this set? (LLM-evaluated)
   - **Complexity** (1-3): Is it appropriate for the rarities it targets?
   - **Color fit** (pass/fail): Does it respect color pie rules?

5. **Human Approval Gate** (see 1B.6)

#### Prompt Template (Sketch)

```
You are designing new Magic: The Gathering mechanics for a custom set.

SET CONTEXT:
- Name: {set_name}
- Theme: {theme}
- Flavor: {flavor_description}
- Draft Archetypes: {archetype_summaries}

DESIGN CONSTRAINTS:
- The mechanic must be {color_constraint} in the color pie
- Complexity level: {complexity_target} (1=common-viable, 2=uncommon+, 3=rare+)
- It must NOT closely duplicate any of these existing mechanics: {recent_mechanics_list}
- Reminder text must fit in parentheses on a single card line (~80 chars max)
- The mechanic must support Limited play (not purely constructed-focused)

Generate a new keyword {ability_type} mechanic. Provide:
1. Name (1-2 words)
2. Type (keyword ability / keyword action / ability word)
3. Colors it appears in
4. Reminder text in parentheses
5. Rules text template using ~ for the card name
6. Three example cards (common, uncommon, rare) that use this mechanic
7. Design rationale (2-3 sentences)

Use valid MTG rules text syntax. Follow Oracle text conventions.
```

---

### 1B.2 Color Pie Rules

The color pie constrains what effects each color can have. These rules are enforced during mechanic validation.

#### Primary, Secondary, and Tertiary Effects

| Effect Category | W | U | B | R | G |
|----------------|---|---|---|---|---|
| **Small creature removal** | P (exile, -X/-X, "destroy tapped") | T (bounce) | P (destroy, -X/-X) | P (damage) | T (fight) |
| **Large creature removal** | P (exile, board wipes) | P (bounce, steal) | P (destroy) | S (damage-based) | S (fight) |
| **Card draw** | T (conditional) | P | P (with life cost) | S (impulsive/exile) | S (creature-based) |
| **Direct damage** | — | — | S (life drain) | P | — |
| **Counterspells** | — | P | — | — | — |
| **Enchantment removal** | P | — | — | S (damage if creature) | P |
| **Artifact removal** | S | — | — | P | P |
| **Life gain** | P | — | S | — | S |
| **Flying** | P | P | S | S | — |
| **Trample** | — | — | — | S | P |
| **Haste** | — | — | S | P | S |
| **Hexproof/Ward** | S | P | — | — | S |
| **Deathtouch** | — | — | P | — | S |
| **First/Double strike** | P | — | — | P | — |
| **Vigilance** | P | — | — | — | S |
| **+1/+1 counters** | P | — | — | — | P |
| **Tokens (creature)** | P | S | S (zombies, etc.) | P (goblins, etc.) | P |
| **Graveyard recursion** | S (small creatures) | — | P | S (phoenixes) | S (creatures) |
| **Ramp/mana acceleration** | — | — | S (rituals) | S (rituals) | P |
| **Mill** | — | P | S | — | — |
| **Discard** | — | — | P | S (random) | — |
| **Tutoring** | — | — | P | — | S (creatures/lands) |

**P** = Primary, **S** = Secondary, **T** = Tertiary, **—** = Color break (violation)

#### Color Pie Validation Rules

For any new mechanic:
1. The mechanic's *core effect* must be primary or secondary in at least one of its assigned colors
2. The mechanic must NOT grant effects that are color breaks in its assigned colors (e.g., green counterspell)
3. If the mechanic is in 2+ colors, each color's version should lean into that color's strengths
4. A mechanic at common in a given color must use effects that are primary in that color (secondary effects push to uncommon+)

---

### 1B.3 Mechanic Templates

Each approved mechanic produces a template used by the card generator in Phase 1C.

```python
@dataclass
class MechanicTemplate:
    name: str                       # e.g., "Descend"
    type: str                       # "keyword_ability" | "keyword_action" | "ability_word"
    reminder_text: str              # e.g., "(To descend, mill two cards...)"
    rules_text_template: str        # Template with {param} placeholders
    parameters: list[MechanicParam] # Variable parts of the mechanic
    colors: list[str]               # Which colors get this mechanic
    rarity_range: list[str]         # ["common", "uncommon", "rare", "mythic"]
    complexity: int                 # 1-3
    flavor_connection: str          # How it ties to the set theme
    design_notes: str               # Tips for the card generator

@dataclass
class MechanicParam:
    name: str        # e.g., "N" in "Descend N"
    type: str        # "integer", "mana_cost", "card_type", etc.
    range: tuple     # e.g., (1, 5) for integers
    scales_with_rarity: bool  # Does the parameter get bigger at higher rarities?
```

#### Example Mechanic Template

```json
{
  "name": "Descend",
  "type": "keyword_action",
  "reminder_text": "(To descend, mill two cards, then you may put a permanent card from among them onto the battlefield tapped.)",
  "rules_text_template": "When {trigger}, descend.",
  "parameters": [],
  "colors": ["W", "U", "B"],
  "rarity_range": ["common", "uncommon", "rare", "mythic"],
  "complexity": 2,
  "common_patterns": [
    "When ~ enters, descend.",
    "When ~ dies, descend.",
    "{2}, {T}: Descend."
  ],
  "uncommon_patterns": [
    "Whenever you descend, {effect}.",
    "When ~ enters, descend. If a creature was put onto the battlefield this way, {bonus}."
  ],
  "rare_patterns": [
    "Whenever you descend, each opponent loses 2 life and you gain 2 life.",
    "At the beginning of your end step, if you descended this turn, draw a card."
  ],
  "design_notes": "At common, descend is a simple ETB/death trigger with modest value. At uncommon, add payoff cards that reward descending. At rare, the payoffs should be powerful engines."
}
```

---

### 1B.4 Evergreen Keyword Assignment

Current evergreen keywords in MTG and their primary color homes:

| Keyword | W | U | B | R | G | Notes |
|---------|---|---|---|---|---|-------|
| **Flying** | ★ | ★ | ● | ● | — | W and U primary, B and R secondary |
| **First strike** | ★ | — | — | ★ | — | W and R only |
| **Double strike** | ★ | — | — | ★ | — | Rare; W and R only |
| **Deathtouch** | — | — | ★ | — | ● | B primary, G secondary |
| **Haste** | — | — | ● | ★ | ● | R primary, B and G secondary (G rare) |
| **Hexproof** | — | ★ | — | — | ● | U primary, G secondary; used sparingly now |
| **Indestructible** | ● | — | ● | — | — | W secondary, B secondary; rare |
| **Lifelink** | ★ | — | ● | — | — | W primary, B secondary |
| **Menace** | — | — | ★ | ★ | — | B and R primary |
| **Reach** | — | — | — | — | ★ | G primary (occasionally W secondary) |
| **Trample** | — | — | — | ● | ★ | G primary, R secondary |
| **Vigilance** | ★ | — | — | — | ● | W primary, G secondary |
| **Ward {N}** | — | ★ | — | — | ● | U primary, G secondary |
| **Flash** | — | ★ | ● | — | ★ | U primary, G primary, B secondary |
| **Defender** | ★ | ★ | — | — | ● | Any color, most common in W and U |
| **Protection** | ★ | — | ● | — | ● | Deciduous; W primary |

**★** = Primary (appears regularly), **●** = Secondary (appears occasionally), **—** = Not in this color

#### Assignment Rules for the Set

- Each color should use 3-5 different evergreen keywords across its commons and uncommons
- **French vanilla commons**: Each color gets 3-4 creatures with only an evergreen keyword and no other rules text
- The most iconic keyword per color should appear on 3-5 cards (e.g., flying in blue, deathtouch in black)
- Some keywords are shared between colors at different rates (e.g., flying in white vs blue)
- Ward has replaced hexproof as the primary "protection from targeting" keyword in recent sets

---

### 1B.5 Validation

Mechanic validation runs before human approval and again when mechanics are used on cards.

#### Pre-Approval Validation (Mechanic Level)

| Check | Description | Severity |
|-------|-------------|----------|
| **Color pie compliance** | Core effect is primary/secondary in assigned colors | Hard fail |
| **Reminder text parseable** | Reminder text follows MTG Oracle text grammar | Hard fail |
| **Reminder text length** | Fits within ~100 characters (card rendering constraint) | Warning |
| **Name uniqueness** | Not an existing MTG keyword name (checked against comprehensive list) | Hard fail |
| **Effect uniqueness** | Functionally different from existing mechanics (LLM comparison) | Warning |
| **Complexity appropriate** | Complexity rating matches target rarity range | Warning |
| **Cross-mechanic interaction** | New mechanics don't create degenerate interactions with each other | Warning (LLM-evaluated) |
| **Template validity** | Rules text template produces valid MTG Oracle text when filled | Hard fail |

#### Post-Approval Validation (Card Level, during Phase 1C)

| Check | Description |
|-------|-------------|
| **Correct usage** | Card uses the mechanic template correctly (parameter in valid range) |
| **Color match** | Card's color is in the mechanic's allowed colors |
| **Rarity match** | Card's rarity is in the mechanic's allowed rarities |
| **Complexity match** | Complex mechanic usage doesn't appear at inappropriate rarities |

---

### 1B.6 Human Approval Gate

#### Workflow

1. **Present candidates**: Display all generated mechanic candidates (6-8) with:
   - Name, type, reminder text
   - Assigned colors and rarities
   - Three example cards per mechanic
   - Automated validation results
   - Scoring breakdown (flavor fit, novelty, parasitism, complexity, color fit)

2. **CLI approval commands**:
   ```bash
   # List mechanic candidates
   python -m mtgai.mechanics list

   # Show detailed mechanic with example cards
   python -m mtgai.mechanics show "Descend"

   # Approve a mechanic
   python -m mtgai.mechanics approve "Descend"

   # Reject a mechanic
   python -m mtgai.mechanics reject "Descend" --reason "Too similar to Surveil"

   # Request modification
   python -m mtgai.mechanics revise "Descend" --note "Make it only mill 1 card instead of 2"

   # Lock final mechanic set (requires exactly mechanic_count approved)
   python -m mtgai.mechanics finalize
   ```

3. **Finalization**: Once `mechanic_count` mechanics are approved:
   - Mechanic templates are written to `output/sets/<code>/mechanics.json`
   - Skeleton is updated with mechanic-to-slot assignments
   - Card generation (Phase 1C) is unblocked

4. **Iteration**: If all candidates are rejected, trigger a new generation round with feedback from rejections as negative examples.

---

## Phase 1C: Card Generator

### 1C.1 Generation Pipeline

#### Step-by-Step Flow

```
For each unfilled slot in the skeleton:
  1. PREPARE CONTEXT
     ├── Load slot spec (color, rarity, type, CMC, archetype, mechanic)
     ├── Load mechanic templates (if slot uses new mechanic)
     ├── Load archetype definition (if slot is archetype-tagged)
     ├── Gather already-generated cards for set awareness:
     │   ├── All cards in the same color (avoid redundancy)
     │   ├── All cards in the same archetype (ensure synergy)
     │   └── Summary statistics (how many of each type, CMC curve so far)
     └── Select few-shot examples from proven prompt templates (Phase 0E)

  2. GENERATE CARD
     ├── Build prompt with all context
     ├── Call LLM with structured JSON output
     ├── Parse response into Card data model
     └── Assign collector number

  3. VALIDATE CARD
     ├── Run all validators from mtgai.validation (see 1C.3)
     ├── Collect pass/fail/warning for each validator
     └── Determine overall status: passed | failed | warning

  4. HANDLE RESULT
     ├── If PASSED: Card status → "validated", save to cards/ directory
     ├── If WARNING: Card status → "validated" (with warnings noted), save
     ├── If FAILED:
     │   ├── If attempt < max_retries (default 3):
     │   │   ├── Build retry prompt with specific failure feedback
     │   │   ├── Include the failed card as negative example
     │   │   └── Go to step 2
     │   └── If attempt >= max_retries:
     │       ├── Card status → "flagged"
     │       ├── Save best attempt (highest validation score)
     │       └── Add to human review queue
     └── Update skeleton slot with card_id reference
```

#### Generation Order Strategy

Cards are NOT generated in collector number order. Instead, use this priority:

1. **Signpost uncommons first** (10 cards) — they define archetypes and set the tone
2. **Mythic rares** (20 cards) — set-defining cards, most creative freedom
3. **Rares** (60 cards) — complex designs that reward archetypes
4. **Uncommons** (remaining ~70 cards) — fill out archetype support
5. **Commons** (101 cards) — bread-and-butter limited cards, generated last because they need awareness of what the higher rarities already established
6. **Reprints** — selected after all new cards are generated, filling specific gaps

This order ensures the "identity" of the set is established before the "filler" is generated, and common card generation has full awareness of what the set needs.

---

### 1C.2 Card Type Specifics

Each card type has different generation requirements and prompt strategies.

#### Creatures

- **Required fields**: name, mana_cost, type_line (including creature types), rules_text, power, toughness
- **Optional**: flavor_text
- **P/T Guidelines by Rarity and CMC**:

  | CMC | Common P/T | Uncommon P/T | Rare P/T |
  |-----|-----------|--------------|----------|
  | 1 | 1/1, 2/1, 1/2 | 1/1 to 2/1 (with upside) | 1/1 to 2/2 (with strong abilities) |
  | 2 | 2/2, 2/1, 1/3 | 2/2 to 3/2 (with abilities) | 2/2 to 3/3 (with strong abilities) |
  | 3 | 3/2, 2/3, 3/3 | 3/3 to 3/4 (with abilities) | 3/3 to 4/4 (with strong abilities) |
  | 4 | 3/4, 4/3, 4/4 | 4/4 to 4/5 (with abilities) | 4/4 to 5/5 (with strong abilities) |
  | 5 | 4/4, 4/5, 5/4 | 5/5 to 5/4 (with abilities) | 5/5+ (with strong abilities) |
  | 6+ | 5/5, 6/5, 5/6 | 5/6+ (with abilities) | 6/6+ (with strong abilities) |

- **Vanilla test**: At common, a creature with no abilities should have above-average P/T for its CMC. A creature with strong abilities should have below-average P/T.
- **Creature types**: Use existing MTG creature types where possible. Each color has characteristic creature types (W: Human, Soldier, Knight, Angel; U: Merfolk, Wizard, Drake; B: Zombie, Vampire, Rat; R: Goblin, Dragon, Elemental; G: Elf, Beast, Treefolk). Mix in set-specific types as appropriate.

#### Instants and Sorceries

- **Required fields**: name, mana_cost, type_line, rules_text
- **Optional**: flavor_text
- **Key difference**: Instants can be cast at instant speed; sorceries cannot. This distinction matters for game balance:
  - Removal that exiles or destroys unconditionally is usually sorcery-speed
  - Conditional removal, damage-based removal, and combat tricks are usually instants
  - Card draw is usually sorcery (except cantrips attached to instant effects)
- **Prompt guidance**: Instants and sorceries should have clear, concise effects. Avoid overly wordy rules text at common.

#### Enchantments

- **Subtypes**: Aura (attached to permanent), Saga (chapter abilities), regular enchantment
- **Aura prompt**: Must specify "Enchant [something]" and what it grants
- **Saga prompt**: Must have exactly 3 chapters (I, II, III) with sequential effects, then sacrifice
- **Regular enchantments**: Static abilities, triggered abilities, or activated abilities
- **Color distribution**: White and green have the most enchantments at common; blue has enchantment synergy; black and red have fewer

#### Artifacts

- **Subtypes**: Equipment, Vehicle, regular artifact, Food, Treasure, Clue, Blood (token types are not generated as cards)
- **Equipment prompt**: Must specify equip cost and what it grants when equipped
- **Vehicle prompt**: Must specify crew cost and P/T
- **Colorless consideration**: Artifacts are typically colorless, but colored artifacts exist. At common, most artifacts are colorless equipment or mana rocks

#### Planeswalkers

- **Required fields**: name, mana_cost, type_line (Legendary Planeswalker — [Name]), loyalty, loyalty_abilities
- **Loyalty abilities**: Typically 3 abilities: [+N], [-N], [-N] (ultimate)
  - Plus ability: Incremental advantage (card selection, token, +1/+1 counter)
  - Minus ability: Removal, card draw, or significant effect
  - Ultimate: Game-winning effect, typically -6 to -8
- **Starting loyalty**: Usually CMC - 1 to CMC + 1
- **Rarity**: Always mythic rare (occasionally rare in some sets)
- **Count**: 2-5 per set
- **Generation strategy**: These are high-stakes cards — generate 3 candidates per slot and pick the best. Always flag for human review regardless of validation status.

#### Lands

- **Types**: Basic lands (5, not generated), dual/fixing lands, utility lands, creature-lands
- **Fixing lands at common/uncommon**: Tap lands that produce two colors (enters tapped, adds {A} or {B})
- **Utility lands at uncommon/rare**: Lands with activated abilities
- **Count**: 5-10 nonbasic lands per set
- **Color balance**: Fixing lands should cover the most important color pairs for the set's archetypes

#### Legendary Creatures

- **All legendary creatures are named characters** with unique, evocative names
- **Naming convention**: "[FirstName], [Title/Epithet]" or "[FirstName] [Surname]"
- **Each must feel unique**: No two legendaries should fill the same mechanical niche
- **Commander consideration**: Design with singleton 100-card format in mind (interesting build-around abilities)
- **Story integration**: Legendaries should feel like characters in the set's world
- **Distribution**: ~15-25 legendaries, at least 1 per color at rare+, signpost uncommon legends (one per color pair) are common in recent sets
- **Generation strategy**: Generate 2-3 candidates per slot. Always flag for human review.

---

### 1C.3 Validation Library (`mtgai.validation`)

This is the most critical shared component. Every validator is a pure function: takes a card (and optionally set context) and returns a `ValidationResult`.

```python
@dataclass
class ValidationResult:
    validator_name: str
    passed: bool
    severity: str          # "error" | "warning" | "info"
    message: str           # Human-readable explanation
    details: dict          # Machine-readable details (scores, specifics)
    suggestions: list[str] # Actionable fixes for the card generator retry prompt
```

#### Validator 1: Rules Text Parser (`validate_rules_text`)

**Purpose**: Verify that rules text follows MTG Oracle text grammar conventions.

**Checks**:

| Check | Pattern | Example (Correct) | Example (Incorrect) |
|-------|---------|-------------------|---------------------|
| **Self-reference** | Card refers to itself as `~` in generation, rendered as its own name | "When ~ enters" | "When this creature enters" |
| **Keyword formatting** | Evergreen keywords are capitalized, one per line or comma-separated | "Flying, vigilance" | "flying and vigilance" |
| **Reminder text** | In parentheses, after keyword | "Flying (This creature...)" | "Flying - This creature..." |
| **Mana symbols** | `{W}`, `{U}`, `{B}`, `{R}`, `{G}`, `{C}`, `{X}`, `{T}`, `{N}` | "{2}{W}: Gain 2 life." | "2W: Gain 2 life." |
| **Targeting** | "target" followed by a valid target type | "target creature" | "a creature of your choice" |
| **Enters triggers** | "When ~ enters" (not "enters the battlefield" post-2023) | "When ~ enters" | "When ~ enters the battlefield" |
| **Dies triggers** | "When ~ dies" (not "is put into a graveyard from the battlefield") | "When ~ dies" | "When ~ is destroyed" |
| **Activated abilities** | "{cost}: {effect}." format | "{2}, {T}: Draw a card." | "Pay 2 and tap: Draw a card." |
| **Triggered abilities** | "When/Whenever/At [trigger], [effect]." | "Whenever you cast..." | "Every time you cast..." |
| **Line breaks** | Each ability on its own line | Separate lines | Run-on paragraph |
| **Period termination** | Each ability ends with a period | "Draw a card." | "Draw a card" |
| **Modal spells** | "Choose one —" / "Choose two —" format | "Choose one —\n• Effect" | "Pick one of the following:" |
| **Loyalty abilities** | "[+N]:" / "[-N]:" / "[0]:" format | "[+1]: Draw a card." | "+1: Draw a card." |

**Implementation**: A combination of regex patterns and a simple recursive descent parser for structured rules text. Not a full MTG rules engine — just syntax validation.

**Severity**: Hard fail on formatting errors (mana symbols, self-reference). Warning on stylistic issues.

#### Validator 2: Balance Scorer (`validate_balance`)

**Purpose**: Flag cards that are over- or under-powered for their rarity and CMC.

**Scoring Model**:

The balance scorer computes a **power score** for each card and compares it against expected ranges per rarity/CMC.

```python
def compute_power_score(card: Card) -> float:
    score = 0.0

    # Base: P/T relative to CMC (creatures only)
    if card.is_creature:
        vanilla_baseline = get_vanilla_baseline(card.cmc)  # e.g., CMC 3 → 3/3
        stat_total = card.power + card.toughness
        baseline_total = vanilla_baseline.power + vanilla_baseline.toughness
        score += (stat_total - baseline_total) * 0.5

    # Keyword value
    for keyword in card.keywords:
        score += KEYWORD_VALUES[keyword]  # e.g., flying=1.5, vigilance=0.5, deathtouch=1.0

    # Ability value (estimated by complexity and effect type)
    for ability in card.parsed_abilities:
        score += estimate_ability_value(ability)

    # Card advantage
    score += estimate_card_advantage(card) * 1.0

    # Removal quality
    if is_removal(card):
        score += removal_quality_score(card)  # unconditional > conditional > damage-based

    return score
```

**Keyword Value Table** (approximate, tunable):

| Keyword | Value | Notes |
|---------|-------|-------|
| Flying | 1.5 | Premier evasion |
| First strike | 1.0 | Combat advantage |
| Double strike | 2.5 | Very powerful |
| Deathtouch | 1.0 | Excellent on small creatures |
| Haste | 0.75 | Tempo advantage |
| Hexproof | 2.0 | Very powerful, used sparingly |
| Lifelink | 1.0 | Lifegain + combat advantage |
| Menace | 0.75 | Moderate evasion |
| Reach | 0.25 | Defensive |
| Trample | 0.75 | Offensive, scales with power |
| Vigilance | 0.5 | Moderate |
| Ward {N} | 0.5*N | Scales with ward cost |
| Flash | 0.5 | Flexibility |

**Expected Power Score Ranges** (per rarity):

| Rarity | CMC 1 | CMC 2 | CMC 3 | CMC 4 | CMC 5 | CMC 6+ |
|--------|-------|-------|-------|-------|-------|--------|
| Common | -0.5 to 1.5 | 0 to 2 | 0 to 2.5 | 0.5 to 3 | 1 to 3.5 | 1.5 to 4 |
| Uncommon | 0 to 2.5 | 0.5 to 3 | 1 to 4 | 1.5 to 4.5 | 2 to 5 | 2.5 to 6 |
| Rare | 1 to 4 | 1.5 to 5 | 2 to 6 | 2.5 to 7 | 3 to 8 | 3.5 to 10 |
| Mythic | 2 to 6 | 2.5 to 8 | 3 to 10 | 3.5 to 12 | 4 to 14 | 4.5 to 16 |

**Severity**: Error if score is >2 points outside expected range. Warning if >1 point outside.

**Feedback for retry**: "This card's power score is {score}, which is above/below the expected range of {range} for a {rarity} at CMC {cmc}. Suggested adjustments: {specific_suggestions}."

#### Validator 3: Uniqueness Checker (`validate_uniqueness`)

**Purpose**: Ensure no two cards in the set are too similar in name or function.

**Name Similarity**:
- Compute Levenshtein edit distance between card name and all other card names in the set
- Flag if edit distance < 3 (e.g., "Void Sentinel" vs "Void Sentinal" — likely a typo/duplicate)
- Also flag if names share >60% of words (e.g., "Deep Sea Guardian" vs "Guardian of the Deep Sea")

**Functional Similarity**:
- Compare rules text using token-level Jaccard similarity
- Threshold: flag if Jaccard similarity > 0.7 between two cards of the same color and rarity
- This catches cases like two red commons that both deal 3 damage to any target

**Semantic Similarity** (optional, if embedding model available):
- Embed card rules text using a sentence transformer
- Flag if cosine similarity > 0.85 between two cards in the same color
- More expensive but catches functional duplicates with different wording

**Severity**: Error for name duplicates (edit distance < 2). Warning for functional similarity > 0.7.

#### Validator 4: Text Overflow Estimator (`validate_text_overflow`)

**Purpose**: Predict whether a card's text will fit within the physical card frame when rendered.

> **Cross-cutting suggestion addressed**: This validator is critical enough to prototype in Phase 0C as a standalone utility, so that its character/line limits can be fed into the card generation prompts from day one. The full implementation lives in `mtgai.validation`, but the core constants (max chars per line, max lines per field) should be established during Phase 0C and used as prompt constraints in Phase 0E.

**Text Field Limits** (based on standard MTG card frame at 63x88mm, ~300 DPI):

| Field | Max Characters | Max Lines | Font Size Reference |
|-------|---------------|-----------|-------------------|
| Card name | ~30 chars | 1 | ~9pt Beleren-equivalent |
| Mana cost | ~8 symbols | 1 | Symbol font |
| Type line | ~40 chars | 1 | ~8pt |
| Rules text | ~350 chars | ~8 lines | ~7.5pt body text |
| Flavor text | ~150 chars | ~3 lines | ~7pt italic |
| **Total text box** | ~500 chars | ~11 lines | Combined rules + flavor |
| P/T | 5 chars | 1 | ~10pt bold |

**Estimation Algorithm**:

```python
def estimate_overflow(card: Card) -> OverflowResult:
    # Count rules text lines (split on \n)
    rules_lines = card.rules_text.split('\n')
    rules_char_count = len(card.rules_text)

    # Account for keyword lines (shorter) vs ability lines (longer)
    estimated_rendered_lines = 0
    for line in rules_lines:
        if is_keyword_only(line):
            estimated_rendered_lines += 1  # Keywords are one line
        else:
            # Wrap long lines: ~45 chars per rendered line
            estimated_rendered_lines += math.ceil(len(line) / 45)

    # Flavor text
    flavor_lines = 0
    if card.flavor_text:
        flavor_lines = math.ceil(len(card.flavor_text) / 40)  # Italic is slightly wider
        estimated_rendered_lines += 1  # Separator line
        estimated_rendered_lines += flavor_lines

    # Check against limits
    max_lines = 11  # Total text box capacity
    # Reminder text in parentheses adds ~1-2 lines each
    reminder_count = card.rules_text.count('(')
    estimated_rendered_lines += reminder_count * 0.5  # Reminders often wrap

    overflow = estimated_rendered_lines > max_lines
    tight_fit = estimated_rendered_lines > max_lines - 1

    return OverflowResult(
        passed=not overflow,
        estimated_lines=estimated_rendered_lines,
        max_lines=max_lines,
        rules_chars=rules_char_count,
        flavor_chars=len(card.flavor_text or ""),
        tight_fit=tight_fit
    )
```

**Severity**: Error if estimated overflow. Warning if tight fit (within 1 line of limit).

**Feedback for retry**: "Card text is estimated at {N} lines but the card frame fits {max}. Reduce rules text by ~{chars} characters or remove flavor text. Current rules text: {rules_text}."

#### Validator 5: Color Pie Violation Detector (`validate_color_pie`)

**Purpose**: Ensure cards only use effects legal in their color(s).

**Implementation**:

1. Parse the card's rules text into a list of effects using pattern matching:
   - "destroy target creature" → removal(unconditional)
   - "deals N damage" → direct_damage
   - "draw N card(s)" → card_draw
   - "counter target spell" → counterspell
   - "gains N life" → lifegain
   - "search your library" → tutor
   - (30+ effect patterns total)

2. For each identified effect, check against the color pie table (from 1B.2):
   - If the effect is primary or secondary in the card's color(s) → PASS
   - If the effect is tertiary → WARNING
   - If the effect is a color break → ERROR

3. Special cases:
   - Multicolor cards can use effects from any of their colors
   - Artifacts/colorless cards have a restricted set of effects (no color-specific effects)
   - Hybrid mana cards must be valid in EACH color independently
   - "Color-shifted" effects at mythic rare are sometimes acceptable (warning, not error)

**Effect Pattern Database**:

```python
COLOR_PIE_EFFECTS = {
    "destroy_creature": {"W": "primary", "B": "primary", "R": "secondary"},
    "exile_creature": {"W": "primary"},
    "damage_creature": {"R": "primary", "B": "secondary"},
    "damage_player": {"R": "primary", "B": "secondary"},
    "counterspell": {"U": "primary"},
    "draw_cards": {"U": "primary", "B": "secondary", "G": "tertiary"},
    "lifegain": {"W": "primary", "B": "secondary", "G": "secondary"},
    "ramp": {"G": "primary", "R": "tertiary"},
    "tutor": {"B": "primary", "G": "secondary"},
    "discard": {"B": "primary", "R": "secondary"},
    "mill": {"U": "primary", "B": "secondary"},
    "return_from_graveyard": {"B": "primary", "W": "secondary", "G": "secondary"},
    "create_token": {"W": "primary", "R": "primary", "G": "primary", "B": "secondary"},
    "pump_creature": {"W": "primary", "G": "primary", "R": "secondary"},
    "fight": {"G": "primary"},
    "bounce": {"U": "primary"},
    "tap_creature": {"W": "primary", "U": "secondary"},
    "enchantment_removal": {"W": "primary", "G": "primary"},
    "artifact_removal": {"R": "primary", "G": "primary", "W": "secondary"},
    "land_destruction": {"R": "primary"},
    "haste_grant": {"R": "primary"},
    "flying_grant": {"W": "secondary", "U": "primary"},
    "indestructible_grant": {"W": "primary"},
    "hexproof_grant": {"U": "primary", "G": "secondary"},
    "menace_grant": {"B": "primary", "R": "primary"},
    "trample_grant": {"G": "primary", "R": "secondary"},
}
```

**Severity**: Error for color breaks. Warning for tertiary effects.

#### Validator 6: Spell Checker (`validate_spelling`)

**Purpose**: Catch typos in card names, rules text, flavor text, and type lines.

**Implementation**:

- Use `pyspellchecker` (Python library) as the base spell checker
- Maintain a custom dictionary of MTG-specific terms:
  - All evergreen keywords (flying, trample, etc.)
  - All creature types (Merfolk, Phyrexian, etc.)
  - All MTG jargon (mana, tapped, untapped, graveyard, battlefield, exile, etc.)
  - All card-specific invented words from the current set (character names, plane names, mechanic names)
  - Common MTG phrases that look like misspellings ("enters" used intransitively, "dies" as a game term)
- Skip checking inside mana symbols `{...}` and reminder text `(...)` (reminder text is template-generated)

**Custom Dictionary** (loaded from `data/mtg-dictionary.txt`):

```
# Creature types
Merfolk
Phyrexian
Treefolk
Shapeshifter
...

# Game terms
battlefield
graveyard
exile
mana
tapped
untapped
scry
surveil
...

# Set-specific (added per set)
# Added by mechanic designer and card generator
```

**Severity**: Error for rules text typos. Warning for flavor text typos (flavor text has more creative license).

#### Validator 7: Mana Cost Validator (`validate_mana_cost`)

**Purpose**: Verify mana cost is well-formed and consistent with the card's color identity.

**Checks**:

| Check | Rule |
|-------|------|
| **Format** | Only valid symbols: `{W}`, `{U}`, `{B}`, `{R}`, `{G}`, `{C}`, `{X}`, `{0}`-`{20}`, `{W/U}`, etc. |
| **Color match** | Colored mana symbols match the card's declared colors |
| **CMC match** | Computed CMC matches the declared CMC |
| **Hybrid validity** | Hybrid symbols use valid color pairs |
| **Land exception** | Lands have no mana cost (empty string, not "{0}") |
| **CMC reasonableness** | CMC is within expected range for the card type and rarity |

**Severity**: Error for all checks.

#### Validator 8: Type Line Validator (`validate_type_line`)

**Purpose**: Ensure the type line follows MTG conventions.

**Checks**:

| Check | Rule |
|-------|------|
| **Supertypes** | Only valid supertypes: Legendary, Basic, Snow, World |
| **Card types** | Only valid types: Creature, Instant, Sorcery, Enchantment, Artifact, Planeswalker, Land, Battle |
| **Subtypes** | Creature types from the official list; spell subtypes (Aura, Equipment, Saga, etc.) |
| **Legendary consistency** | If card has a proper name (capitalized first+last or "Name, Title"), it should be Legendary |
| **Creature has P/T** | Creatures must have power and toughness |
| **Non-creature has no P/T** | Non-creatures must NOT have power and toughness (except vehicles) |
| **Planeswalker has loyalty** | Planeswalkers must have starting loyalty |
| **Format** | "[Supertypes] [Types] — [Subtypes]" with em dash separator |

**Severity**: Error for all checks.

#### Validator Summary Table

| # | Validator | Module | Phase 1C Use | Phase 4 Use |
|---|-----------|--------|-------------|-------------|
| 1 | Rules Text Parser | `mtgai.validation.rules_text` | Per-card generation gate | Full-set report |
| 2 | Balance Scorer | `mtgai.validation.balance` | Per-card generation gate | Set-wide balance analysis |
| 3 | Uniqueness Checker | `mtgai.validation.uniqueness` | Per-card (against existing set cards) | Full-set duplicate scan |
| 4 | Text Overflow Estimator | `mtgai.validation.overflow` | Per-card generation gate | Full-set overflow report |
| 5 | Color Pie Detector | `mtgai.validation.color_pie` | Per-card generation gate | Full-set compliance report |
| 6 | Spell Checker | `mtgai.validation.spelling` | Per-card generation gate | Full-set spelling report |
| 7 | Mana Cost Validator | `mtgai.validation.mana_cost` | Per-card generation gate | Full-set report |
| 8 | Type Line Validator | `mtgai.validation.type_line` | Per-card generation gate | Full-set report |

---

### 1C.4 Reprint System

#### Purpose

Real MTG sets include 10-25 reprints: existing cards that are re-released with new art. Reprints serve multiple purposes:
- Fill gaps in the limited environment (common removal, mana fixing, staple combat tricks)
- Provide familiar cards for players
- Reduce the number of new designs needed

#### Reprint Selection Process

1. **Reserve slots in skeleton**: During Phase 1A, mark ~15-25 slots as `is_reprint_slot: true` with a `reason` field describing what the slot needs (e.g., "common white removal", "green mana dork", "red burn spell").

2. **Query Scryfall/MTGJSON for candidates**:
   ```python
   def find_reprint_candidates(slot: ReprintSlot) -> list[ScryfallCard]:
       # Search Scryfall API for cards matching slot requirements
       query = build_scryfall_query(
           color=slot.color,
           rarity=slot.rarity,
           card_type=slot.card_type,
           cmc_range=(slot.cmc_min, slot.cmc_max),
           # Prefer cards that have been reprinted before (proven designs)
           # Exclude cards on the Reserved List
           # Exclude cards that are too powerful for limited
       )
       candidates = scryfall_search(query)
       return rank_candidates(candidates, slot)
   ```

3. **Rank candidates** by:
   - **Limited playability**: Is this a good card for draft/sealed?
   - **Flavor fit**: Does the card name/concept fit the set theme? (LLM evaluation)
   - **Reprint history**: Cards that have been reprinted many times are safer choices
   - **Power level**: Must fit the set's power level expectations
   - **Mechanical synergy**: Does it support any of the set's draft archetypes?

4. **Human selection**: Present top 3-5 candidates per reprint slot for human approval:
   ```bash
   python -m mtgai.reprints suggest          # Show all reprint slot suggestions
   python -m mtgai.reprints suggest W-REPRINT-01  # Suggestions for specific slot
   python -m mtgai.reprints select W-REPRINT-01 "Pacifism"  # Select a reprint
   python -m mtgai.reprints clear W-REPRINT-01    # Clear selection
   ```

5. **Integration**: Selected reprints use the original card data (imported from Scryfall) but:
   - Get a new collector number for the set
   - Get flagged for new art generation in Phase 2
   - Keep original rules text exactly (no modifications)

#### Interaction with Skeleton

- Reprint slots are defined during skeleton creation (Phase 1A)
- Reprint selection happens AFTER new card generation (Phase 1C) so we know what gaps remain
- If a generated card fills a need that a reprint slot was meant for, the reprint slot can be converted to a new card slot (or vice versa)
- The skeleton tracks reprint slots separately but they count toward rarity/color totals

---

### 1C.5 Retry Loop

#### Retry Strategy

```python
MAX_RETRIES = 3  # Per card
RETRY_TEMPERATURE_BUMP = 0.1  # Increase temperature each retry for variety

async def generate_card_with_retries(slot: Slot, context: SetContext) -> Card:
    best_card = None
    best_score = -1

    for attempt in range(1, MAX_RETRIES + 1):
        temperature = BASE_TEMPERATURE + (attempt - 1) * RETRY_TEMPERATURE_BUMP

        if attempt == 1:
            prompt = build_initial_prompt(slot, context)
        else:
            prompt = build_retry_prompt(
                slot, context,
                previous_card=best_card,
                failures=best_card.validation_results,
                attempt=attempt
            )

        card = await generate_card(prompt, temperature=temperature)
        results = run_all_validators(card, context)
        card.validation_results = results

        # Score: count passed validators, weight by severity
        score = compute_validation_score(results)

        if score > best_score:
            best_card = card
            best_score = score

        # Check if good enough
        if all(r.passed for r in results if r.severity == "error"):
            card.status = "validated"
            return card

    # All retries exhausted — save best attempt as flagged
    best_card.status = "flagged"
    best_card.generation_metadata["flagged_reason"] = summarize_failures(best_card.validation_results)
    return best_card
```

#### Retry Prompt Enhancement

The retry prompt includes:
1. The original slot spec and context
2. The previous failed card as a negative example
3. Specific failure messages from each validator
4. The validator's suggested fixes
5. Explicit instruction: "Do NOT repeat the following mistakes: {failure_list}"

Example retry prompt addition:
```
PREVIOUS ATTEMPT FAILED VALIDATION:
- Balance: FAIL — Power score 6.5 exceeds range [0, 3] for a common at CMC 2.
  Suggestion: Reduce power/toughness or remove an ability.
- Color Pie: WARNING — "destroy target creature" is not primary in green.
  Suggestion: Use "fight" instead of "destroy" for green creature removal.

Generate an improved version that addresses these issues.
```

---

### 1C.6 Batch Processing

#### Why Batching Matters

Generating 271 cards one-by-one is expensive (token cost for repeated context) and slow. Batch processing groups related cards to share context efficiently.

#### Batch Strategy

```python
BATCH_SIZES = {
    "mythic": 4,       # Small batches for high-variance cards
    "rare": 6,         # Medium batches
    "uncommon": 8,     # Larger batches (more constrained = less variance)
    "common": 10,      # Largest batches (simplest cards)
}
```

#### Batch Composition

Cards are batched by shared context:
1. **Same color + rarity**: All white commons, all blue uncommons, etc.
2. **Archetype batches**: All UB archetype support cards together
3. **Mechanic batches**: All cards using "Descend" together

Each batch prompt includes:
- Shared context (set theme, color identity, archetype, mechanic templates)
- Slot specs for all cards in the batch
- Already-generated cards in the same color/archetype (for awareness)
- Instruction to generate all cards as a JSON array

#### Set Awareness Without Context Overflow

The full set of already-generated cards is too large for an LLM context window once you're 200+ cards in. Solution:

1. **Summary statistics** (always included): card count by type/CMC, keywords used, named characters
2. **Same-color cards** (always included): full data for all generated cards in the same color(s)
3. **Same-archetype cards** (included when relevant): full data for archetype-tagged cards
4. **Name list** (always included): just the names of all generated cards (for uniqueness)
5. **Condensed set overview** (always included): one-line summaries of all cards ("001: Void Sentinel - 1W 2/3 vigilance, ETB gain life")

This keeps the context under ~30K tokens even for late-stage generation.

#### Resumability

- Each batch result is saved immediately after generation + validation
- A `generation_progress.json` file tracks which slots are filled, which are pending, which are flagged
- If the process is interrupted, `python -m mtgai.generate resume` picks up from the last incomplete batch
- Each card's generation metadata includes the attempt number and prompt hash for reproducibility

---

## Cross-Cutting Concerns & Recommendations

### Visual Skeleton Overview

**Recommendation: Yes** — Phase 1A should produce a visual overview in addition to JSON.

Generate `skeleton-overview.txt` (ASCII) that shows:
- Color-by-rarity grid with slot counts
- Mana curve histogram per color (ASCII bars, as shown in the `stats --curve` output)
- Archetype map showing which slots support which archetypes
- Mechanic distribution heat map (which colors/rarities have which mechanics)

This text-based overview is sufficient for CLI-primary workflow. A fancier HTML version can wait for Phase 3B.

### Missing Validators

The current validator list is comprehensive for Phase 1C. Two additional validators to consider:

1. **Legendary Name Validator** (`validate_legendary_name`): Ensure legendary creatures have proper naming conventions (unique first name, title/epithet format). Check that no two legendaries share a first name unless intentional (related characters).

2. **Flavor Text Quality Validator** (`validate_flavor_text`): Basic checks — not empty for cards that should have it (simple commons, french vanilla creatures), not too similar to rules text, matches the set's tone. This could be LLM-evaluated.

These are lower priority and could be added iteratively.

### Design Review Checkpoint Between 1B and 1C

**Recommendation: Yes** — Add a mandatory checkpoint.

After mechanics are finalized (1B) and before card generation begins (1C):

1. **Update skeleton** with final mechanic assignments
2. **Generate 5 sample cards** (1 per color) using the approved mechanics
3. **Human review** of sample cards to verify:
   - Mechanics feel good on actual cards
   - Prompt templates produce quality output
   - Balance scoring works correctly
4. **Adjust mechanic templates** if needed based on sample card feedback
5. **Lock skeleton** — no more structural changes after this point

CLI command: `python -m mtgai.review checkpoint` — runs the design review checkpoint.

### Reprint Slot Interaction

**Recommendation**: Reprint slots are defined in the skeleton but filled LAST (after all new cards are generated). This allows:
- Reprint selection to fill actual gaps rather than predicted ones
- Slots to be converted between reprint and new-card as needed
- The card generator to focus on new designs without worrying about which slots are reprints

The skeleton reserves reprint slots in the color/rarity budget, so total counts remain correct regardless of when reprints are selected.

### Human-Assisted "Design Mode" for Key Cards

**Recommendation: Yes** — Add an optional "design mode" for mythics and legendaries.

For high-impact cards (mythic rares, legendary creatures, planeswalkers), offer an interactive generation mode:

```bash
# Interactive design mode for a specific slot
python -m mtgai.generate design M-W-01

# Flow:
# 1. System generates 3 candidates
# 2. User reviews all 3
# 3. User picks one OR provides feedback for a new round
# 4. User can manually edit any field before finalizing
# 5. Final card is validated and saved
```

This is critical because mythics and legendaries define the set's identity — they deserve more human attention than a batch-generated common.

### Text Overflow as Phase 0 Deliverable

**Recommendation: Yes** — Establish overflow constants in Phase 0C.

The text overflow estimator's core constants (max characters per line, max lines per text box, font size assumptions) should be determined during Phase 0C/0B when card rendering research is done. These constants are then:

1. Stored in `config/card_frame_limits.json`
2. Used as hard constraints in card generation prompts ("rules text must be under 350 characters")
3. Used by the overflow validator in Phase 1C

The full overflow validator (with line-wrapping estimation) is built in Phase 1C, but the limits it checks against come from Phase 0.

**Suggested Phase 0C addition**:
```json
// config/card_frame_limits.json
{
  "name_max_chars": 30,
  "type_line_max_chars": 40,
  "rules_text_max_chars": 350,
  "rules_text_max_lines": 8,
  "flavor_text_max_chars": 150,
  "flavor_text_max_lines": 3,
  "total_text_box_max_lines": 11,
  "chars_per_line": 45,
  "chars_per_line_italic": 40,
  "reminder_text_extra_lines": 1.5
}
```

---

## Implementation Order Within Phase 1

```
Phase 1A: Set Skeleton Generator
  ├── 1. Data models (SetConfig, Slot, DraftArchetype, SetSkeleton)
  ├── 2. Slot allocation algorithm
  ├── 3. Balance constraint validators
  ├── 4. CLI review tool (list, show, stats)
  ├── 5. Skeleton JSON export
  └── 6. Tests: constraint validation, real-set comparison

  ── CHECKPOINT: Human reviews skeleton ──

Phase 1B: Mechanic Designer
  ├── 1. Color pie rules database
  ├── 2. Mechanic generation prompts
  ├── 3. Mechanic template data model
  ├── 4. Evergreen keyword assignment
  ├── 5. Mechanic validation
  ├── 6. CLI approval workflow
  └── 7. Tests: color pie compliance, template validity

  ── CHECKPOINT: Human approves mechanics ──
  ── DESIGN REVIEW: 5 sample cards generated and reviewed ──

Phase 1C: Card Generator
  ├── 1. Validation library (all 8 validators)
  │   ├── Rules text parser
  │   ├── Balance scorer
  │   ├── Uniqueness checker
  │   ├── Text overflow estimator
  │   ├── Color pie violation detector
  │   ├── Spell checker
  │   ├── Mana cost validator
  │   └── Type line validator
  ├── 2. Card generation pipeline (prompt building, LLM calls, parsing)
  ├── 3. Retry loop with feedback
  ├── 4. Card type-specific generation strategies
  ├── 5. Batch processing system
  ├── 6. Design mode for mythics/legendaries
  ├── 7. Reprint system (Scryfall integration, selection CLI)
  └── 8. Tests: validator unit tests, end-to-end generation tests

  ── CHECKPOINT: Human reviews full set via CLI ──
```

---

## File & Module Structure

```
mtgai/
├── __init__.py
├── __main__.py                  # Entry point
├── models/
│   ├── __init__.py
│   ├── card.py                  # Card, CardStatus, GenerationMetadata
│   ├── set_config.py            # SetConfig
│   ├── skeleton.py              # SetSkeleton, Slot, ReprintSlot
│   ├── archetype.py             # DraftArchetype
│   └── mechanic.py              # MechanicTemplate, MechanicParam
├── skeleton/
│   ├── __init__.py
│   ├── generator.py             # build_skeleton() algorithm
│   ├── constraints.py           # All hard/soft constraint validators
│   └── allocator.py             # Slot allocation subroutines
├── mechanics/
│   ├── __init__.py
│   ├── designer.py              # Mechanic generation pipeline
│   ├── color_pie.py             # Color pie rules database
│   ├── evergreen.py             # Evergreen keyword assignments
│   └── templates.py             # Mechanic template management
├── generator/
│   ├── __init__.py
│   ├── pipeline.py              # Main generation pipeline
│   ├── prompts.py               # Prompt building for each card type
│   ├── batch.py                 # Batch processing logic
│   ├── retry.py                 # Retry loop with feedback
│   ├── design_mode.py           # Interactive design mode for key cards
│   └── reprints.py              # Reprint selection system
├── validation/
│   ├── __init__.py              # run_all_validators(), ValidationResult
│   ├── rules_text.py            # Rules text parser
│   ├── balance.py               # Balance scorer
│   ├── uniqueness.py            # Uniqueness checker
│   ├── overflow.py              # Text overflow estimator
│   ├── color_pie.py             # Color pie violation detector
│   ├── spelling.py              # Spell checker
│   ├── mana_cost.py             # Mana cost validator
│   └── type_line.py             # Type line validator
├── review/
│   ├── __init__.py
│   ├── __main__.py              # CLI entry: python -m mtgai.review
│   ├── list_cmd.py              # list command
│   ├── show_cmd.py              # show command
│   ├── stats_cmd.py             # stats command
│   └── formatters.py            # Table formatting, card pretty-print
├── data/
│   ├── mtg_dictionary.txt       # Custom spell-check dictionary
│   ├── creature_types.txt       # Official creature type list
│   └── existing_mechanics.txt   # Known MTG mechanics (for uniqueness checks)
└── config/
    └── card_frame_limits.json   # Text overflow constants (from Phase 0)
```

---

## Testing Strategy for Phase 1

| Test Type | What | Location |
|-----------|------|----------|
| **Constraint unit tests** | Each hard/soft constraint validator tested with passing and failing inputs | `tests/skeleton/test_constraints.py` |
| **Real-set comparison** | Generate skeleton, compare distributions against Bloomburrow/Duskmourn data | `tests/skeleton/test_real_sets.py` |
| **Mechanic validation tests** | Color pie checks, template parsing, reminder text formatting | `tests/mechanics/test_validation.py` |
| **Validator unit tests** | Each of 8 validators tested with known-good and known-bad cards | `tests/validation/test_*.py` (one per validator) |
| **Rules text parser tests** | Comprehensive test suite for MTG Oracle text patterns | `tests/validation/test_rules_text.py` |
| **Balance scorer calibration** | Score real MTG cards and verify they fall in expected ranges | `tests/validation/test_balance_calibration.py` |
| **Overflow estimator tests** | Test against real cards with known rendering results | `tests/validation/test_overflow.py` |
| **CLI output tests** | Verify formatting of list, show, stats commands | `tests/review/test_cli.py` |
| **Generation integration test** | Generate 5 cards, validate all pass, verify JSON output | `tests/generator/test_pipeline.py` |
| **Reprint search test** | Query Scryfall for known card slots, verify candidates | `tests/generator/test_reprints.py` |
