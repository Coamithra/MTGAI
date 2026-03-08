# Phase 4 & 5: Full-Set Validation Report + Print Preparation & Delivery

## Context

Phase 4 is the **primary quality gate** between card creation and physical printing. The individual-card validators are built in Phase 1C (`mtgai.validation`), but Phase 4 runs them as a full-set suite and adds new analyses that only make sense at the set level: sealed/draft simulation, cross-card interactions, and aggregate balance reporting. Phase 5 transforms validated cards into print-ready files and manages the physical print order.

**Key dependency chain**: Phase 1C validators -> Phase 2C renderer -> Phase 3 review -> **Phase 4 report** -> Phase 5 print.

## Quick Start (Context Reset)

**Prerequisites**:
- Phase 1C complete: `mtgai.validation` library, all card JSON in `output/sets/<code>/cards/`
- Phase 2C complete (for 4C and 5): rendered card images in `output/sets/<code>/renders/`
- Phase 3B: `mtgai/packs.py` booster generation function (for 4B)
- `config/print-specs.json` locked (from Phase 0B)

**Read first**: This plan. Note that Phase 4 runs in TWO passes:
- **Pass 1 (after Phase 1C, BEFORE art generation)**: 4A + 4B — catches balance issues before investing in art
- **Pass 2 (after Phase 2C)**: 4C — quality checks on rendered cards

**Start with**: Phase 4A (Balance Analysis) immediately after Phase 1C completes.

## Deliverables Checklist

### Phase 4A: Balance Analysis
- [ ] Mana curve distribution report per color (vs targets from set-template.json)
- [ ] Creature P/T vs CMC analysis
- [ ] Removal spell density report
- [ ] Card advantage sources per color
- [ ] Rarity power level distribution
- [ ] Keyword/mechanic frequency with as-fan calculations
- [ ] Full balance report: `output/sets/<code>/reports/balance-report.md`

### Phase 4B: Limited Environment Analysis
- [ ] Sealed pool generator (6 packs of 15 cards)
- [ ] Sealed pool color analysis (can you build a 2-color deck from a pool?)
- [ ] Booster pack composition checks (proper rarity distribution per pack)
- [ ] Draft archetype support check (all 10 color pairs viable?)
- [ ] Statistical simulation results (100+ sealed pools analyzed)
- [ ] Limited report: `output/sets/<code>/reports/limited-report.md`

### Phase 4C: Quality Checks
- [ ] Rules text grammar validation (full set)
- [ ] Spell check across all card text
- [ ] Duplicate/near-duplicate detection
- [ ] Flavor text quality check
- [ ] Cross-card interaction sanity checks
- [ ] Text overflow validation against rendered cards
- [ ] Quality report: `output/sets/<code>/reports/quality-report.md`

### Phase 5A: Print File Generation
- [ ] All cards exported as print-ready images per printer specs
- [ ] Card sheets generated if required by printer
- [ ] Card back file exported
- [ ] Draft set: 24 randomized booster packs (8-player pod)
- [ ] Full playset: 4x commons/uncommons/rares, 2x mythics (configurable), basic lands
- [ ] Order manifest: `output/sets/<code>/print/manifest.json`
- [ ] Cost calculator output before committing to order

### Phase 5B: Print Order
- [ ] Step-by-step guide for chosen print service
- [ ] File upload checklist
- [ ] Test batch (~20 cards) ordered and reviewed
- [ ] Full order placed after test batch approval

### Phase 5C: Assembly
- [ ] Sorting guide for received cards
- [ ] Set guide insert (set name, mechanics reference, archetype guide)
- [ ] Box labels

- [ ] `learnings/phase4.md`
- [ ] `learnings/phase5.md`

**Done when**: All validation reports generated with pass/fail per check, all flagged cards reviewed, print files exported and validated against printer specs, and print order placed.

---

## Cross-Cutting Concerns & Recommendations

Before diving into the plan, these issues surfaced during planning and deserve explicit resolution:

### 1. Phase 4B is NEW code, not just "run existing validators"
The master plan says Phase 4 is a "quick run" using validators built in Phase 1C. That is true for 4A and 4C. But **Phase 4B (Limited Environment Analysis)** is entirely new: sealed pool simulation, draft archetype scoring, booster collation. This is non-trivial code. The plan below scopes it accordingly — expect 4B to take as long as 4A and 4C combined.

### 2. Should Phase 4B run before Phase 2 (art generation)?
**Yes, strongly recommended.** Art generation is the most expensive phase (time and credits). Running 4A + 4B after Phase 1C (before any art is generated) catches balance problems early. Proposed adjustment to execution order:

```
Phase 1C complete -> Phase 4A + 4B (balance gate) -> fix any issues -> Phase 2 (art) -> Phase 4C (quality) -> Phase 5
```

This means splitting Phase 4 into two passes:
- **Pass 1 (post-1C)**: 4A balance + 4B limited analysis. Catch structural problems before investing in art.
- **Pass 2 (post-2C)**: 4C quality checks + re-run 4A/4B to confirm fixes. Generate the final report.

### 3. Draft set: 18 boosters is not enough for 8-player draft
An 8-player draft requires 24 packs (3 packs per player). The master plan says 18. **Recommendation: generate 24 packs for draft, or allow configurable pack count.** Default to 24 for an 8-player pod. 18 would serve a 6-player pod. Make this a parameter: `--draft-players N` (default 8, producing 3N packs).

### 4. Full playset: mythic quantities
Real boosters contain mythics at ~1:8 ratio vs rares. A "full playset" of 4x each mythic is unrealistic — you would never open that many. **Recommendation:**
- Commons/Uncommons: 4x each
- Rares: 4x each (you want a full playset for constructed)
- Mythics: 2x each (compromise between realism and playability)
- Make this configurable: `--mythic-copies N` (default 2, max 4)

### 5. Card back dependency
The master plan mentions card back design in Phase 2C (renderer), but Phase 5A needs it for print files. **This dependency is already satisfied** — Phase 5 runs after Phase 2C. Just ensure the card back is rendered to the same print spec (DPI, bleed, CMYK) as card fronts. Add it to the Phase 2C deliverables checklist.

### 6. Basic lands
Real sets include ~20 basic lands (4 of each type, sometimes with unique art). Custom basics need custom art, which consumes art generation budget. **Recommendation:**
- Budget 20 basic lands (4 per type: Plains, Island, Swamp, Mountain, Forest)
- Each gets unique art (20 art generations — about 7% of the ~280 card budget)
- For print: include 20 of each basic in the full playset (real decks need many basics)
- For draft: include 1 basic land per booster (the 15th card slot) — can be any type, randomized
- Track basic land art generation in the art budget estimate

### 7. Phase 5C: Assembly
The master plan does not include post-delivery assembly. **Recommendation: add a lightweight Phase 5C** covering sleeving, sorting, box labels, and a one-page "set guide" insert (set name, mechanics, archetype guide). This is a manual process with a generated checklist — minimal code.

### 8. Cost calculator
Phase 5 should include a cost estimator that runs before placing the order. The print service APIs (or manual lookup) give per-card pricing. Multiplied by quantities from the order manifest, this gives a total cost before committing. Add to Phase 5A.

---

## Phase 4A: Balance Analysis

### 4A.1: Mana Curve Analysis

**What it does**: Compare the set's mana value distribution (per color, per rarity, overall) against target curves derived from real sets.

**Target distributions** (derived from Phase 0A research, benchmarked against 3 recent sets):

| CMC | Common creatures | Common non-creatures | Uncommon | Rare/Mythic |
|-----|-----------------|---------------------|----------|-------------|
| 0   | 0%              | 0-2%                | 0-2%     | 0-5%        |
| 1   | 10-15%          | 10-15%              | 8-12%    | 5-10%       |
| 2   | 20-30%          | 20-25%              | 18-25%   | 15-20%      |
| 3   | 20-25%          | 20-25%              | 20-25%   | 18-25%      |
| 4   | 15-20%          | 15-20%              | 18-22%   | 18-22%      |
| 5   | 8-12%           | 8-12%               | 10-15%   | 12-18%      |
| 6+  | 3-8%            | 5-10%               | 5-10%    | 10-20%      |

These ranges come from Phase 0A research data. Stored in `config/balance_targets.json` so they can be tuned without code changes.

**Comparison metrics**:
- **Chi-squared test**: Does the observed distribution deviate significantly from target? p < 0.05 = WARN, p < 0.01 = FAIL.
- **Mean CMC per color**: Should be within 0.3 of the target mean. Flag colors that skew too high (slow, unplayable in limited) or too low (aggressive, lacks finishers).
- **Curve shape**: Each color should have a roughly bell-shaped curve peaking at CMC 2-3. Flag colors with bimodal distributions or missing CMC buckets.

**Visualization** (for HTML report):
- Stacked bar chart: CMC on x-axis, card count on y-axis, stacked by color.
- Overlay line: target curve from real set average.
- Per-color small multiples: individual curve per color.

**Implementation**:
```python
# mtgai/validation/balance.py (extends existing module)

class ManaCurveAnalyzer:
    def __init__(self, targets: dict):  # loaded from balance_targets.json
        self.targets = targets

    def analyze(self, cards: list[Card]) -> ManaCurveReport:
        # Group by color, rarity, CMC
        # Compute chi-squared against targets
        # Compute mean CMC per color
        # Flag deviations
        pass
```

**Output**: `ManaCurveReport` with per-color pass/fail, overall pass/fail, flagged deviations with severity (INFO/WARN/FAIL).

---

### 4A.2: Creature Power/Toughness Analysis

**What it does**: Ensure creature stats are appropriate for their mana cost and rarity. A 5/5 for 2 mana is a problem. A 1/1 for 6 mana with no abilities is also a problem.

**Benchmarks** (by CMC, for vanilla-equivalent creatures):

| CMC | Common P/T range | Uncommon P/T range | Rare/Mythic P/T range |
|-----|-------------------|--------------------|-----------------------|
| 1   | 1/1 - 2/1         | 1/1 - 2/2          | 1/1 - 2/2             |
| 2   | 2/1 - 2/3         | 2/2 - 3/2          | 2/2 - 3/3             |
| 3   | 2/2 - 3/3         | 3/2 - 3/4          | 3/3 - 4/4             |
| 4   | 3/3 - 4/4         | 3/4 - 4/5          | 4/4 - 5/5             |
| 5   | 3/4 - 5/4         | 4/4 - 5/5          | 4/5 - 6/6             |
| 6+  | 4/4 - 6/6         | 5/5 - 7/7          | 5/5 - 8/8+            |

**Ability tax adjustment**: Cards with strong abilities should have lower stats. Define keyword costs:
- Flying: -0.5 total stats
- Trample: -0.5
- Vigilance: -0.25
- Haste: -0.5
- Deathtouch: -1.0
- Lifelink: -0.5
- First strike: -0.5
- Double strike: -1.5
- Hexproof: -1.0

For cards with non-keyword abilities, estimate a "complexity score" (0-3) based on rules text length and effect type, and subtract proportionally.

**Outlier detection**: Compute `stat_efficiency = (power + toughness - ability_tax) / CMC` for each creature. Flag:
- `stat_efficiency > expected_max_for_rarity`: Overpowered (WARN at 1 std dev, FAIL at 2 std dev)
- `stat_efficiency < expected_min_for_rarity`: Underpowered (WARN only — intentionally weak cards exist)
- Any common creature with total P/T > 8: FAIL (too complex for common)
- Any creature with power > 2 * CMC: FAIL (almost certainly broken)

**Output**: List of flagged creatures with their efficiency score, expected range, and severity.

---

### 4A.3: Removal Density Analysis

**What it does**: Ensure each color has enough removal to function in limited play.

**What counts as removal** (categorized):
- **Hard removal**: Destroy/exile target creature (Murder, Swords to Plowshares)
- **Conditional removal**: Destroy with condition (Doom Blade — nonblack, Smite the Monstrous — power 4+)
- **Damage-based removal**: Deal N damage to creature/player (Lightning Bolt, Searing Spear)
- **-X/-X effects**: Reduce toughness (Dead Weight, Grasp of Darkness)
- **Bounce**: Return to hand/library (Unsummon, Aether Gust)
- **Exile-based**: Temporary exile, O-Ring effects, Banishing Light
- **Combat tricks with removal upside**: Fight effects (Rabid Bite), deathtouch granters
- **Pacifism effects**: Enchant creature — can't attack/block

**Detection algorithm**: Parse rules text for patterns:
```python
REMOVAL_PATTERNS = {
    "hard_removal": [
        r"destroy target (creature|permanent)",
        r"exile target (creature|permanent)",
    ],
    "conditional_removal": [
        r"destroy target .+ (creature|permanent) (with|if|unless)",
    ],
    "damage_removal": [
        r"deals? \d+ damage to (target|any|each) (creature|target)",
    ],
    "minus_effects": [
        r"gets? [+-]\d+/[+-]\d+",  # then check if toughness reduction
    ],
    "bounce": [
        r"return target .+ to (its owner's hand|the top|the bottom)",
    ],
    "pacifism": [
        r"enchanted creature can't attack",
        r"enchanted creature can't block",
    ],
    "fight": [
        r"fights? target",
        r"deals damage equal to its power to target",
    ],
}
```

**Target density per color** (at common+uncommon, per 40 cards in that color):

| Color | Hard removal | Conditional | Damage | Bounce | Fight | Total removal spells |
|-------|-------------|-------------|--------|--------|-------|---------------------|
| White | 1-2         | 1-2         | 0      | 0-1    | 0     | 3-5                 |
| Blue  | 0           | 0           | 0      | 2-3    | 0     | 2-4 (+ counterspells)|
| Black | 2-3         | 1-2         | 0-1    | 0      | 0     | 4-6                 |
| Red   | 0-1         | 0-1         | 3-5    | 0      | 0-1   | 4-6                 |
| Green | 0           | 0-1         | 0      | 0      | 2-3   | 2-4                 |

**Counterspells** (blue only): Count separately. Target: 1-2 at common/uncommon.

**Comparison**: Compare to real set data from Phase 0A. Flag any color with fewer than 2 total removal-equivalent effects at common/uncommon.

**Output**: Per-color removal breakdown table, total count, comparison to targets, flagged shortages.

---

### 4A.4: Card Advantage Analysis

**What it does**: Ensure card advantage is distributed appropriately. Too much card draw at common makes games grindy; too little makes topdecking miserable.

**Categories of card advantage**:
- **Draw effects**: "Draw N cards", "Look at top N, put one in hand"
- **Cantrips**: "Draw a card" as secondary effect (e.g., on an enchantment or creature ETB)
- **Recursion**: "Return target card from graveyard to hand/battlefield"
- **Token generation**: Creating creature tokens (generates board presence without card expenditure)
- **2-for-1 effects**: Single card that removes two threats, or ETB effects that replace themselves
- **Card selection**: Scry, Surveil, "look at top N, put any number on bottom"

**Detection**: Rules text pattern matching (similar to removal):
```python
CARD_ADVANTAGE_PATTERNS = {
    "draw": [r"draw (\d+|a|two|three) cards?"],
    "cantrip": [r"draw a card"],  # differentiated by being secondary text
    "recursion": [r"return .+ from .+ graveyard to .+ (hand|battlefield)"],
    "tokens": [r"create .+ (\d+/\d+) .+ creature tokens?"],
    "selection": [r"scry \d+", r"surveil \d+"],
}
```

**Target distribution** (common + uncommon, per color):

| Color | Draw/Cantrip | Recursion | Tokens | Selection |
|-------|-------------|-----------|--------|-----------|
| White | 1-2         | 0-1       | 2-4    | 0-1       |
| Blue  | 3-5         | 0         | 0-1    | 2-4       |
| Black | 1-3         | 1-3       | 1-2    | 1-2       |
| Red   | 1-2 (impulse draw) | 0  | 1-2    | 0-1       |
| Green | 0-1         | 0-1       | 1-3    | 0-1       |

**Red "impulse draw"**: Exile top card, may play it this turn. Detect via: `r"exile the top .+ card .+ (play|cast) (it|them)"`.

**Output**: Per-color breakdown, total sources, comparison to targets, flags for any color with zero card advantage at common.

---

### 4A.5: Rarity Power Distribution

**What it does**: Verify that power level increases with rarity (New World Order compliance). Commons should be simpler and weaker; mythics should be splashy and powerful.

**Power scoring algorithm** (0-10 scale):

```python
def power_score(card: Card) -> float:
    score = 0.0

    # Base stat efficiency (creatures only)
    if card.is_creature:
        vanilla_stats = VANILLA_BENCHMARK[card.cmc]
        actual = card.power + card.toughness
        score += (actual - vanilla_stats) * 0.5  # deviation from vanilla

    # Keyword value
    for keyword in card.keywords:
        score += KEYWORD_VALUES.get(keyword, 0.25)

    # Ability complexity (proxy: rules text line count)
    ability_lines = card.rules_text.count('\n') + 1
    score += ability_lines * 0.3

    # Card advantage built-in
    if has_card_advantage(card):
        score += 1.0

    # Removal built-in
    if has_removal(card):
        score += 1.5

    # Mana efficiency
    if card.cmc > 0:
        score += max(0, (total_value - card.cmc) * 0.3)

    return clamp(score, 0, 10)
```

This is a rough heuristic, not a game engine. Calibrate by running it against ~100 real cards with known power levels from Phase 0A research data.

**Expected distribution**:

| Rarity | Mean score | Std dev | Max acceptable |
|--------|-----------|---------|----------------|
| Common | 2.0-3.5   | 0.8     | 5.0            |
| Uncommon | 3.5-5.0 | 1.0     | 7.0            |
| Rare   | 5.0-7.0   | 1.5     | 9.0            |
| Mythic | 6.5-9.0   | 1.5     | 10.0           |

**Flags**:
- Common with score > 5.0: WARN ("too complex/powerful for common")
- Common with score > 6.0: FAIL
- Mythic with score < 4.0: WARN ("underwhelming mythic")
- Any card where score is 2+ std dev above its rarity mean: WARN

**Output**: Histogram of power scores per rarity, flagged outliers, mean/median/std per rarity.

---

### 4A.6: As-Fan Calculations

**What it does**: Calculate how often a mechanic or theme appears in a typical booster pack (the "as-fan" metric). Critical for draft experience — if a mechanic appears in fewer than 1 in 3 packs, it won't feel like a real set theme.

**Definition**: As-fan = expected number of cards with property X in a single booster pack.

**Calculation** (for a standard booster: 10C + 3U + 1R/M + 1 basic land):

```python
def as_fan(cards_with_property: list[Card], all_cards: list[Card]) -> float:
    commons_with = count(c for c in cards_with_property if c.rarity == "common")
    total_commons = count(c for c in all_cards if c.rarity == "common")

    uncommons_with = count(c for c in cards_with_property if c.rarity == "uncommon")
    total_uncommons = count(c for c in all_cards if c.rarity == "uncommon")

    rares_with = count(c for c in cards_with_property if c.rarity == "rare")
    total_rares = count(c for c in all_cards if c.rarity == "rare")

    mythics_with = count(c for c in cards_with_property if c.rarity == "mythic")
    total_mythics = count(c for c in all_cards if c.rarity == "mythic")

    # Probability of opening a card with property in each slot
    p_common = commons_with / total_commons if total_commons else 0
    p_uncommon = uncommons_with / total_uncommons if total_uncommons else 0
    p_rare = rares_with / total_rares if total_rares else 0
    p_mythic = mythics_with / total_mythics if total_mythics else 0

    # Mythic appears in ~1/8 of rare slots
    p_rare_slot = p_rare * (7/8) + p_mythic * (1/8)

    return (10 * p_common) + (3 * p_uncommon) + (1 * p_rare_slot)
```

**Target as-fan values**:

| Property | Target as-fan | Minimum | Notes |
|----------|--------------|---------|-------|
| Each set mechanic (keyword) | 1.5-3.0 | 1.0 | Below 1.0 = mechanic barely shows up |
| Each color | 2.5-3.5 | 2.0 | Should be roughly equal |
| Creatures | 8-10 | 7 | Most cards in a pack should be creatures |
| Removal (all types) | 1.5-2.5 | 1.0 | At least 1 removal per pack on average |
| Card advantage | 1.0-2.0 | 0.5 | |
| Each draft archetype signpost | 0.3-0.8 | 0.2 | Gold uncommons, build-around cards |
| Multicolor cards | 1.0-2.0 | 0.5 | |
| Legendary creatures | 0.3-0.8 | 0.1 | |

**Output**: Table of as-fan values per mechanic, per theme, per color. Flags for any mechanic below minimum threshold. Comparison to real set as-fan data from Phase 0A.

---

## Phase 4B: Limited Environment Analysis

> **Important**: This is NEW code, not a reuse of Phase 1C validators. Budget development time accordingly.

### 4B.1: Booster Pack Composition

**Pack structure** (standard play booster):
- 10 commons (no more than 2 of any single color, at least 1 of each color if possible)
- 3 uncommons (no color duplicates)
- 1 rare or mythic rare (7:1 ratio rare:mythic)
- 1 basic land (random type)
- Total: 15 cards

**Collation rules** (to prevent "feel-bad" packs):
- No pack should have more than 4 cards of a single color (across all rarities)
- No pack should have 0 creatures
- No pack should have all creatures and no spells
- Each common color should appear at least once in the common slots
- No duplicate cards in a single pack

**Implementation**:

```python
# mtgai/limited/booster.py

class BoosterGenerator:
    def __init__(self, card_pool: list[Card], seed: int = None):
        self.rng = random.Random(seed)
        self.commons = [c for c in card_pool if c.rarity == "common"]
        self.uncommons = [c for c in card_pool if c.rarity == "uncommon"]
        self.rares = [c for c in card_pool if c.rarity == "rare"]
        self.mythics = [c for c in card_pool if c.rarity == "mythic"]
        self.basics = [c for c in card_pool if c.is_basic_land]

    def generate_pack(self) -> BoosterPack:
        pack = BoosterPack()

        # Rare/mythic slot (7:1 ratio)
        if self.rng.randint(1, 8) == 1 and self.mythics:
            pack.rare = self.rng.choice(self.mythics)
        else:
            pack.rare = self.rng.choice(self.rares)

        # 3 uncommons — no color duplicates
        pack.uncommons = self._pick_color_diverse(self.uncommons, 3)

        # 10 commons — color balanced (at least 1 per color, max 2 per color)
        pack.commons = self._pick_color_balanced_commons(10)

        # 1 basic land
        pack.land = self.rng.choice(self.basics)

        # Validate collation rules
        self._validate_pack(pack)

        return pack

    def _pick_color_balanced_commons(self, n: int) -> list[Card]:
        """Pick n commons with at least 1 per color, max 2 per color."""
        # 1. Pick 1 random common from each of the 5 colors (5 cards)
        # 2. Pick 5 more, respecting max-2-per-color constraint
        # 3. If colorless commons exist, they can fill remaining slots
        pass

    def generate_packs(self, count: int) -> list[BoosterPack]:
        return [self.generate_pack() for _ in range(count)]
```

**Validation on generated packs**:
- All collation rules pass
- No duplicate cards within a pack
- Rare/mythic ratio across many packs approximates 7:1

---

### 4B.2: Sealed Pool Generator

**Algorithm**:
1. Generate 6 booster packs using `BoosterGenerator`
2. Combine into a single pool of 90 cards (6 * 15)
3. Add unlimited basic lands (not counted in pool)

```python
# mtgai/limited/sealed.py

class SealedPoolGenerator:
    def __init__(self, booster_gen: BoosterGenerator):
        self.booster_gen = booster_gen

    def generate_pool(self) -> SealedPool:
        packs = self.booster_gen.generate_packs(6)
        all_cards = []
        for pack in packs:
            all_cards.extend(pack.all_cards())

        return SealedPool(
            cards=all_cards,
            packs=packs,  # keep pack breakdown for reporting
        )
```

---

### 4B.3: Sealed Pool Analysis

**Core question**: Can a player build a viable 2-color deck from a random sealed pool?

**"Viable 2-color deck" definition**:
- Exactly 2 colors (with optional colorless cards and splashable 3rd color cards)
- At least 13-17 creatures
- At least 22-24 total nonland cards (the rest are lands from the basic land pool)
- Reasonable mana curve (at least 2 cards at CMC 2, at least 2 at CMC 3)
- At least 1 removal spell

**Analysis per pool**:

```python
class SealedPoolAnalyzer:
    def analyze(self, pool: SealedPool) -> SealedAnalysis:
        results = {}

        # Test all 10 color pairs
        for pair in COLOR_PAIRS:  # WU, WB, WR, WG, UB, UR, UG, BR, BG, RG
            deck = self._best_deck_for_pair(pool, pair)
            results[pair] = DeckViability(
                total_playables=len(deck.playables),
                creature_count=deck.creature_count,
                removal_count=deck.removal_count,
                curve_quality=self._evaluate_curve(deck),
                is_viable=self._is_viable(deck),
                splash_needed=deck.splash_color is not None,
            )

        return SealedAnalysis(
            color_pair_results=results,
            viable_pair_count=sum(1 for r in results.values() if r.is_viable),
            best_pair=max(results, key=lambda p: results[p].total_playables),
        )
```

**Pass criteria** for the set:
- Across N simulated pools, at least 90% should have 2+ viable color pairs
- Across N simulated pools, at least 70% should have 3+ viable color pairs
- No single color pair should be viable in fewer than 20% of pools (indicates a color is too shallow)
- No single color pair should be viable in more than 60% of pools (indicates a color is too deep, warping)

---

### 4B.4: Draft Archetype Viability

**What it checks**: Each of the 10 2-color archetypes (defined in Phase 1A) has enough support at common and uncommon to be draftable.

**Per archetype, require**:
- At least 1 gold (multicolor) signpost uncommon for the pair
- At least 2-3 cards at common/uncommon that specifically reward or enable the archetype strategy
- Sufficient playables in both colors at common (at least 8-10 playable commons per color)
- The archetype's key mechanic appears on at least 4 commons + 2 uncommons across the two colors

**Detection**: Each archetype has a "strategy tag" defined in Phase 1A (e.g., WU = "flyers", BR = "sacrifice", GW = "tokens"). Cards are tagged with archetype relevance during Phase 1C generation. This analysis counts tagged cards per archetype.

**Archetype depth scoring**:

```python
class ArchetypeAnalyzer:
    def score_archetype(self, pair: str, cards: list[Card]) -> ArchetypeScore:
        relevant = [c for c in cards if pair in c.archetype_tags]
        signpost_count = count(c for c in relevant if c.is_gold and c.rarity == "uncommon")
        common_support = count(c for c in relevant if c.rarity == "common")
        uncommon_support = count(c for c in relevant if c.rarity == "uncommon")

        return ArchetypeScore(
            pair=pair,
            signpost_count=signpost_count,  # need >= 1
            common_support=common_support,   # need >= 4
            uncommon_support=uncommon_support,  # need >= 2
            total_support=len(relevant),
            # Letter grade
            grade=self._grade(signpost_count, common_support, uncommon_support),
        )
```

**Pass criteria**:
- All 10 archetypes have at least 1 signpost uncommon: PASS/FAIL (hard requirement)
- All 10 archetypes score at least a C grade (minimum viable): PASS/FAIL
- No archetype scores below D: FAIL
- Grade distribution: at least 3 archetypes at B or higher

---

### 4B.5: Statistical Simulation

**How many simulations for confidence?**

For sealed pool analysis:
- **100 pools**: Gives rough directional data. Sufficient for "does any color pair have zero viable pools?" checks. 95% CI width: ~10 percentage points.
- **500 pools**: Recommended default. 95% CI width: ~4.5 percentage points. Good enough to confidently say "WR is viable in 45% +/- 4.5% of pools."
- **1000 pools**: High confidence. 95% CI width: ~3 percentage points. Use for final pre-print validation.

**Recommendation**: Default to 500. Make configurable via `--sealed-sims N`. Run 1000 for the final Phase 4 report before printing.

**For draft simulation** (more complex — simulating 8 AI drafters is out of scope per the master plan's "statistical analysis only, no game simulation" constraint): Instead of simulating a full draft, compute:
- Card availability per archetype assuming roughly equal color preference across 8 drafters
- Whether the as-fan of archetype cards supports 2-3 drafters in any given archetype

**Performance**: 500 sealed simulations with pool analysis should complete in under 30 seconds on a modern machine. Each simulation is: generate 6 packs (fast), analyze 10 color pairs (fast string matching). No need for parallelization.

**Reproducibility**: Accept a `--seed` parameter. Log the seed in the report so results can be reproduced.

---

## Phase 4C: Quality Checks

### 4C.1: Rules Text Grammar Validation

**Parser specification**: Build a lightweight MTG rules text grammar validator. This is NOT a full MTG rules engine — it checks syntax patterns, not game semantics.

**Grammar rules to enforce**:

1. **Keyword formatting**: Keywords are capitalized and followed by reminder text in parentheses at first occurrence: `Flying (This creature can't be blocked except by creatures with flying or reach.)`
2. **Self-reference**: Cards refer to themselves by `~` in the internal data, rendered as the card name. Check that `~` is used consistently (not the literal card name in rules text).
3. **Target specification**: Every use of "target" must specify what is being targeted: "target creature", "target player", "target permanent", etc. Flag bare "target" without a noun.
4. **Tense and voice**: MTG rules use present tense, active voice. Flag past tense ("destroyed" instead of "destroys").
5. **Standard phrases**: Validate against a dictionary of standard MTG phrases:
   - "When ~ enters the battlefield" (not "enters play")
   - "At the beginning of your upkeep" (not "During your upkeep")
   - "Sacrifice a creature" (not "Sacrifice one creature")
   - "Until end of turn" (not "Until the end of turn" or "This turn")
   - "You may pay {X}" (not "Pay {X} if you want")
6. **Mana symbol formatting**: `{W}`, `{U}`, `{B}`, `{R}`, `{G}`, `{C}`, `{1}` through `{X}`. Flag malformed mana symbols.
7. **Ability structure**: Activated abilities follow the pattern `[Cost]: [Effect].` (colon separator). Triggered abilities start with "When", "Whenever", or "At". Static abilities are declarative statements.

**Common error patterns and fixes**:

| Error pattern | Fix suggestion |
|--------------|---------------|
| "enters play" | "enters the battlefield" |
| "tap: ..." (lowercase) | "Tap: ..." or use {T} symbol |
| "target" without noun | Specify target type |
| "each players" | "each player" (no possessive) |
| "it's controller" | "its controller" (possessive, no apostrophe) |
| "can not" | "can't" |
| Missing period at end | Add period |
| Double spaces | Single space |

**Implementation**:

```python
# mtgai/validation/rules_grammar.py

class RulesGrammarValidator:
    def __init__(self):
        self.standard_phrases = load_standard_phrases()
        self.error_patterns = load_error_patterns()
        self.keyword_db = load_keywords()

    def validate(self, card: Card) -> list[GrammarIssue]:
        issues = []
        text = card.rules_text

        for pattern, fix in self.error_patterns:
            if re.search(pattern, text):
                issues.append(GrammarIssue(
                    card=card.name,
                    severity="WARN",
                    pattern=pattern,
                    found=re.search(pattern, text).group(),
                    suggestion=fix,
                ))

        # Check keyword formatting
        issues.extend(self._check_keywords(card))

        # Check ability structure
        issues.extend(self._check_ability_structure(card))

        # Check mana symbols
        issues.extend(self._check_mana_symbols(card))

        return issues
```

---

### 4C.2: Spell Check

**Tool selection**: `pyspellchecker` (pure Python, no external dependencies, supports custom dictionaries).

**Custom MTG dictionary** (added to the base English dictionary):
- All evergreen keywords (flying, trample, vigilance, deathtouch, lifelink, etc.)
- All MTG-specific terms (battlefield, graveyard, exile, mana, tapped, untapped, upkeep, etc.)
- Card type words (planeswalker, artifact, enchantment, sorcery, instant, etc.)
- Subtype words (elf, goblin, merfolk, vampire, zombie, etc. — from Scryfall creature type list)
- Set-specific mechanic keywords (from Phase 1B)
- Set-specific proper nouns (character names, place names from the set's worldbuilding)

**What to spell-check**:
- Card names (flag unknown words, but with high tolerance — fantasy names are expected)
- Rules text (flag with medium confidence — many MTG terms)
- Flavor text (flag with high confidence — should be mostly normal English plus proper nouns)
- Type lines (flag unknown subtypes against the Scryfall subtype list)

**Implementation**:

```python
# mtgai/validation/spellcheck.py

from spellchecker import SpellChecker

class MTGSpellChecker:
    def __init__(self):
        self.spell = SpellChecker()
        self.spell.word_frequency.load_text_file("config/mtg_dictionary.txt")

    def check_card(self, card: Card) -> list[SpellIssue]:
        issues = []

        # Rules text — medium confidence
        for word in tokenize(card.rules_text):
            if word.lower() not in self.spell and not self._is_mana_symbol(word):
                candidates = self.spell.candidates(word)
                issues.append(SpellIssue(
                    card=card.name,
                    field="rules_text",
                    word=word,
                    suggestions=list(candidates)[:3] if candidates else [],
                    severity="WARN",
                ))

        # Flavor text — higher confidence
        # ... similar but severity="WARN" for all

        return issues
```

---

### 4C.3: Duplicate Detection

**Algorithm**: Multi-layered similarity check.

**Layer 1: Exact name match** — Trivial. Flag any two cards with identical names (excluding basic lands). Severity: FAIL.

**Layer 2: Near-name match** — Levenshtein distance. Flag pairs with distance <= 2 (e.g., "Flame Bolt" vs "Flame Jolt"). Severity: WARN.

```python
from difflib import SequenceMatcher

def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

# Flag pairs with similarity > 0.8
```

**Layer 3: Ability similarity** — Compare rules text after normalizing (strip reminder text, lowercase, replace card name with `~`). Use Jaccard similarity on word sets.

```python
def ability_similarity(a: Card, b: Card) -> float:
    words_a = set(normalize_rules(a.rules_text).split())
    words_b = set(normalize_rules(b.rules_text).split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)

# Flag pairs with similarity > 0.7 AND same CMC AND same color
```

**Layer 4: Functional duplicate** — Same mana cost, same type, same P/T (for creatures), and ability similarity > 0.8. This catches cards that are mechanically identical with different names. Severity: FAIL.

**Performance**: For a ~280-card set, pairwise comparison is 280*279/2 = ~39,000 pairs. With string operations this completes in under 1 second.

**Output**: List of flagged pairs with similarity scores, categorized by layer. Visual diff of the two cards side-by-side in the HTML report.

---

### 4C.4: Flavor Text Quality

**What can be automated**:

1. **Length checks**: Flavor text should not exceed the estimated available space on the card (depends on rules text length). Flag flavor text that would cause text overflow when combined with rules text.
   - Short rules text (1-2 lines): flavor text up to 150 characters
   - Medium rules text (3-4 lines): flavor text up to 80 characters
   - Long rules text (5+ lines): no flavor text recommended (or up to 40 characters)
   - Creatures with no abilities: flavor text up to 200 characters

2. **Quote attribution**: If flavor text is a quote (contains quotation marks), it should have attribution in the form `—Character Name` (em-dash, not hyphen). Flag quotes without attribution.

3. **Missing flavor text**: Flag cards that could have flavor text but don't (cards with short rules text and no flavor text). Severity: INFO (not all cards need flavor text, but most should have it).

4. **Flavor text on token-makers and complex cards**: Cards with 5+ lines of rules text should NOT have flavor text. Flag any that do. Severity: WARN.

5. **Tone consistency**: This is hard to automate fully. Basic heuristic: flag flavor text that contains modern slang, internet-speak, or anachronisms. Use a small blocklist of words unlikely to appear in fantasy flavor text (e.g., "internet", "basically", "literally", "lol").

**What cannot be automated** (mark for human review):
- Is the flavor text thematically appropriate for the card?
- Does it fit the set's world and tone?
- Is it well-written?
- Does it advance the set's story?

**Output**: Per-card flavor text flags, overall statistics (% of cards with flavor text, average length, quote attribution compliance).

---

### 4C.5: Cross-Card Interaction Detection

**What it checks**: Flag problematic card interactions that indicate design mistakes.

**Problematic patterns to detect**:

1. **Infinite loops at common/uncommon**: Two common/uncommon cards that together create an unbounded loop.
   - Pattern: Card A triggers on event X, produces event Y. Card B triggers on event Y, produces event X.
   - Detection: Build a trigger/effect graph for all commons/uncommons. Check for cycles.

```python
class InteractionGraph:
    def __init__(self):
        self.triggers = {}  # card_name -> list of (trigger_event, effect_event)

    def add_card(self, card: Card):
        # Parse triggers: "When X, do Y" -> (X, Y)
        # Parse static: "Whenever X, do Y" -> (X, Y)
        pass

    def find_cycles(self, max_rarity="uncommon") -> list[Cycle]:
        # BFS/DFS on the trigger->effect graph
        # Only consider cards at or below max_rarity
        pass
```

   - Common trigger/effect categories to track:
     - Creature enters the battlefield
     - Creature dies
     - Player gains life
     - Player draws a card
     - +1/+1 counter placed
     - Token created

2. **Repeatable damage combos at common**: Two commons that together deal unbounded damage per turn without additional mana cost. Severity: FAIL.

3. **Color hosing**: Cards that completely shut down a single color with no counterplay (e.g., "Creatures of the chosen color can't attack or block"). Acceptable at rare, flag at common/uncommon. Severity: WARN at uncommon, FAIL at common.

4. **Unblockable + equipment/aura synergy at common**: If the set has both unblockable creatures and powerful auras/equipment at common, the combination could be oppressive in limited. Flag if there are 3+ unblockable commons AND 2+ damage-boosting auras/equipment at common. Severity: WARN.

5. **Self-referential keyword loops**: A keyword mechanic that triggers itself (e.g., "Whenever you gain life, gain 1 life" — infinite loop). The Phase 1B mechanic validator should catch this, but double-check here. Severity: FAIL.

**Limitations**: This is heuristic-based. It will have false positives and will miss subtle interactions. The goal is to catch obvious design mistakes, not to be a complete game rules engine. Flag issues for human review, not auto-rejection.

**Output**: List of flagged interactions with involved cards, severity, and explanation.

---

## Phase 4 Report Format

### Report Structure

The validation report is the primary quality gate. It must be **actionable** — every flag should tell the reader exactly what is wrong and link to the specific card(s).

**Two output formats**: Generate both. The HTML report is for visual review; the CLI report is for scripted use and quick checks.

#### CLI Report (`stdout` or `output/reports/validation-report.txt`)

```
=== MTG AI SET VALIDATION REPORT ===
Set: [Set Name] ([SET])
Cards: 280 | Generated: 2026-03-08T14:30:00Z
Seed: 42 | Simulations: 500

=== SUMMARY ===
Phase 4A - Balance Analysis:     PASS (2 warnings)
Phase 4B - Limited Environment:  PASS (1 warning)
Phase 4C - Quality Checks:       WARN (5 warnings, 1 failure)
Overall:                          WARN — Review required before printing

=== FAILURES (must fix) ===
[FAIL] 4C.3 Duplicate Detection
  Card #042 "Flame Strike" and #187 "Fire Strike"
  Functional duplicate: same cost (3R), same effect, ability similarity 0.92
  → Review: Remove or differentiate one card

=== WARNINGS (should review) ===
[WARN] 4A.2 P/T Analysis
  Card #103 "Thundermaw Giant" (Common) — 5/5 for 4G
  stat_efficiency: 2.5 (expected max for common: 1.8)
  → Consider: Reduce to 4/4, increase CMC to 5G, or upshift to uncommon

[WARN] 4A.3 Removal Density
  Green has 1 removal effect at common/uncommon (target: 2-4)
  → Consider: Add 1 fight effect at common

... (all warnings listed)

=== INFO ===
[INFO] 4C.4 Flavor Text
  23 cards with short rules text have no flavor text
  → Optional: Add flavor text to enhance these cards

=== DETAILED RESULTS ===
[Section 4A.1 - Mana Curve] ...
[Section 4A.2 - P/T Analysis] ...
... (full detailed output)
```

#### HTML Report (`output/reports/validation-report.html`)

**Structure**:
- **Header**: Set name, date, overall pass/fail badge (green/yellow/red)
- **Executive Summary**: Pass/fail per section, total flags by severity
- **Interactive Table of Contents**: Jump to any section
- **Section per analysis** (4A.1 through 4C.5), each with:
  - Pass/fail badge
  - Summary paragraph
  - Data table or chart (rendered via inline SVG or lightweight JS charting — no heavy dependencies)
  - Flagged cards as clickable rows that expand to show card details
- **Card Index**: Alphabetical list of all cards. Each card shows all flags associated with it. Click to see full card data.
- **Appendix**: Raw data tables, simulation parameters, seed values

**Styling**: Single self-contained HTML file (inline CSS, no external dependencies). Dark theme matching the MTG aesthetic. Print-friendly CSS `@media print` rules for generating a PDF version.

**Card detail popup/section** (when clicking a flagged card):
- Card name, mana cost, type, rules text, flavor text, P/T
- Rendered card image (if available from Phase 2C)
- All flags for this card with severity and fix suggestions
- Collector number for easy reference

### Pass/Fail Criteria

| Severity | Meaning | Action required |
|----------|---------|-----------------|
| FAIL     | Blocking issue — must fix before printing | Fix the card/issue, re-run validation |
| WARN     | Potential problem — human should review | Review each warning, dismiss or fix |
| INFO     | Informational — nice to address | Optional improvement |

**Overall report verdict**:
- **PASS**: 0 FAILs, fewer than 5 WARNs
- **WARN**: 0 FAILs, 5+ WARNs — review required
- **FAIL**: 1+ FAILs — must fix before proceeding to Phase 5

---

## Phase 5A: Print File Generation

### 5A.1: Export Pipeline

**Input**: Rendered card images from Phase 2C (RGB PNG at 300+ DPI).
**Output**: Print-ready files per printer specification.

**Conversion steps**:

1. **DPI verification**: Confirm all card images are 300 DPI minimum. Upscale with Lanczos interpolation if needed (flag any card below 200 DPI as FAIL — quality too low).

2. **Color space conversion**: RGB to CMYK.
   - Use Pillow with ICC profiles: sRGB input profile -> FOGRA39 (European standard) or USWebCoatedSWOP (US standard) output profile.
   - Verify with the chosen printer which profile they expect.
   - Save as TIFF (lossless) or high-quality JPEG (95%+) depending on printer requirements.

```python
# mtgai/print/export.py
from PIL import Image, ImageCms

def convert_to_cmyk(image_path: str, output_path: str, icc_profile: str):
    img = Image.open(image_path)
    srgb = ImageCms.createProfile("sRGB")
    cmyk_profile = ImageCms.getOpenProfile(icc_profile)
    transform = ImageCms.buildTransform(srgb, cmyk_profile, "RGB", "CMYK")
    cmyk_img = ImageCms.applyTransform(img, transform)
    cmyk_img.save(output_path, dpi=(300, 300))
```

3. **Bleed margin verification**: Cards should have 3mm bleed on all sides (verify against Phase 0B printer specs). If the renderer (Phase 2C) already adds bleed, verify. If not, add it by extending the card edge pixels outward.

4. **File naming convention**: `<collector_number>_<card_name_slug>_front.{tiff,jpg}` and `card_back.{tiff,jpg}`.

5. **Batch export**: Process all cards in a single pipeline run with progress bar and error recovery. If a single card fails, log it and continue — don't stop the entire batch.

**Output directory structure**:
```
output/print/
  fronts/           # Individual card front images (CMYK, with bleed)
    001_card_name.tiff
    002_card_name.tiff
    ...
  backs/            # Card back image(s)
    card_back.tiff
  sheets/           # Card sheets (if needed) — see 5A.2
  draft/            # Draft set booster contents
  playset/          # Full playset card lists
  manifest.json     # Order manifest
  manifest.csv      # Human-readable order list
```

---

### 5A.2: Card Sheet Generation

**When needed**: Some print services (notably MakePlayingCards) accept individual card images. Others require cards laid out on sheets. Check Phase 0B research for the chosen printer's requirements.

**Sheet layout** (if required):

- Standard sheet sizes: A3 (297x420mm) or US Letter (8.5x11 inches)
- Card size: 63x88mm (2.5x3.5 inches) + 3mm bleed per side = 69x94mm
- Cards per A3 sheet: 4 columns x 4 rows = 16 cards (with margins for cut marks)
- Cards per Letter sheet: 3 columns x 3 rows = 9 cards

**Layout algorithm**:

```python
# mtgai/print/sheets.py

class SheetGenerator:
    def __init__(self, sheet_size_mm: tuple, card_size_mm: tuple, bleed_mm: float):
        self.sheet_w, self.sheet_h = sheet_size_mm
        self.card_w = card_size_mm[0] + 2 * bleed_mm
        self.card_h = card_size_mm[1] + 2 * bleed_mm
        self.margin_mm = 5  # margin around edges
        self.gap_mm = 2     # gap between cards for cut marks

    def generate_sheets(self, card_images: list[str]) -> list[Image]:
        cols = int((self.sheet_w - 2 * self.margin_mm) // (self.card_w + self.gap_mm))
        rows = int((self.sheet_h - 2 * self.margin_mm) // (self.card_h + self.gap_mm))
        per_sheet = cols * rows

        sheets = []
        for i in range(0, len(card_images), per_sheet):
            batch = card_images[i:i + per_sheet]
            sheet = self._lay_out_sheet(batch, cols, rows)
            sheets.append(sheet)

        return sheets

    def _lay_out_sheet(self, cards, cols, rows) -> Image:
        # Create blank sheet at 300 DPI
        # Place each card image at grid position
        # Add crop marks (thin lines at card corners, extending into the gap)
        # Add registration marks (circles at sheet corners for alignment)
        pass
```

**Crop marks**: 0.25pt black lines extending 3mm from each card corner into the gap area.
**Registration marks**: Standard crosshair circles at all four sheet corners.
**Color bars**: Optional — CMYK color calibration bar along one edge.

---

### 5A.3: Draft Set Generation

**Goal**: Generate the contents of 24 booster packs (default: 8-player draft, configurable) with correct rarity distribution and collation.

**Algorithm**:

```python
# mtgai/print/draft.py

class DraftSetGenerator:
    def __init__(self, card_pool: list[Card], players: int = 8):
        self.booster_gen = BoosterGenerator(card_pool)  # from Phase 4B
        self.pack_count = players * 3  # 3 packs per player

    def generate(self, seed: int = None) -> DraftSet:
        if seed is not None:
            self.booster_gen.rng = random.Random(seed)

        packs = self.booster_gen.generate_packs(self.pack_count)

        return DraftSet(
            packs=packs,
            total_cards=sum(len(p.all_cards()) for p in packs),
            card_quantities=self._compute_quantities(packs),
        )

    def _compute_quantities(self, packs) -> dict[str, int]:
        """Card name -> total copies needed across all packs."""
        counts = Counter()
        for pack in packs:
            for card in pack.all_cards():
                counts[card.name] += 1
        return dict(counts)
```

**Output**: `output/print/draft/` directory containing:
- `draft_manifest.json`: Full pack-by-pack breakdown (pack 1 contents, pack 2 contents, etc.)
- `draft_quantities.csv`: Card name, collector number, total copies needed
- Per-pack text files (optional, for manual pack assembly): `pack_01.txt` through `pack_24.txt`

**Physical assembly note**: The print service will deliver all cards as a single stack. The draft manifest tells you how to sort them into packs. Include a printed sorting guide.

---

### 5A.4: Full Playset Generation

**Goal**: Determine the exact quantity of each card needed for a "complete collection" suitable for constructed deck-building.

**Quantities**:

| Rarity | Default copies | Configurable | Rationale |
|--------|---------------|--------------|-----------|
| Common | 4             | `--common-copies` | Playset for constructed |
| Uncommon | 4           | `--uncommon-copies` | Playset for constructed |
| Rare | 4               | `--rare-copies` | Playset for constructed |
| Mythic | 2             | `--mythic-copies` | Simulates actual rarity; 4 is optional |
| Basic Land | 20 each   | `--basic-land-copies` | Real decks run many basics; 20 per type is generous |

**Basic land handling**:
- 5 land types x 4 unique art each = 20 unique basic land cards (from Phase 2)
- Print 20 copies of each unique art? No — print enough total basics per type.
- 20 copies per type = 100 basic lands total. Distribute evenly across the 4 art variants (5 copies each).
- Make this configurable. Some players want more basics.

**Total card count estimate** (for a 280-card set):
- ~101 commons x 4 = 404
- ~80 uncommons x 4 = 320
- ~60 rares x 4 = 240
- ~20 mythics x 2 = 40
- ~20 basic lands x 5 copies each = 100
- **Total: ~1,104 cards**

This is a large order. The cost calculator (5A.5) should run before committing.

**Output**: `output/print/playset/playset_manifest.csv` with columns: collector_number, card_name, rarity, copies, front_image_path, back_image_path.

---

### 5A.5: Order Manifest & Cost Calculator

**Order manifest** (`output/print/manifest.json`):

```json
{
  "set_name": "Example Set",
  "set_code": "EXS",
  "generated_date": "2026-03-08T14:30:00Z",
  "print_service": "MakePlayingCards",
  "orders": [
    {
      "order_type": "draft_set",
      "total_cards": 360,
      "unique_cards": 280,
      "file_format": "TIFF",
      "color_space": "CMYK",
      "dpi": 300,
      "card_stock": "S30 Standard Smooth",
      "finish": "MPC Card Finish",
      "items": [
        {"collector_number": "001", "name": "Card Name", "copies": 2, "front": "fronts/001_card_name.tiff", "back": "backs/card_back.tiff"}
      ]
    },
    {
      "order_type": "full_playset",
      "total_cards": 1104,
      "unique_cards": 300,
      "items": []
    }
  ]
}
```

**Cost calculator**:

```python
# mtgai/print/cost.py

# Pricing tiers (example: MakePlayingCards, as of research in Phase 0B)
# These are stored in config, not hardcoded
MPC_PRICING = {
    # cards_per_deck: price_per_deck
    18: 7.00,
    36: 9.50,
    54: 12.00,
    72: 14.50,
    108: 18.50,
    126: 20.00,
    180: 25.00,
    234: 30.00,
    396: 42.00,
    504: 50.00,
    612: 58.00,
}

def estimate_cost(manifest: OrderManifest) -> CostEstimate:
    total_cards = manifest.total_cards

    # Find the smallest deck size that fits
    for size, price in sorted(MPC_PRICING.items()):
        if total_cards <= size:
            return CostEstimate(
                cards=total_cards,
                deck_size=size,
                base_price=price,
                shipping_estimate=15.00,  # EU shipping estimate
                total_estimate=price + 15.00,
            )

    # If more than max deck size, split into multiple orders
    # ...
```

**The cost estimate is displayed before any order is placed.** It should be printed to the CLI and included in the report.

**Output**: Cost breakdown in the manifest, printed to CLI, included in the HTML report.

---

## Phase 5B: Print Order

### 5B.1: Step-by-Step Guide Generation

**Goal**: Generate a print-service-specific instruction document for the person placing the order. This is a semi-manual process — the guide is auto-generated, the human follows it.

**Generated guide** (`output/print/ORDER_GUIDE.md`):

```markdown
# Print Order Guide — [Set Name]

## Pre-Flight Checklist
- [ ] Phase 4 validation report shows PASS or WARN (no FAILs)
- [ ] All card images present in output/print/fronts/ (count: 280)
- [ ] Card back image present in output/print/backs/
- [ ] Cost estimate reviewed and approved: $XX.XX + $YY.YY shipping

## Step 1: Create Account
- Go to [print service URL]
- Create account / log in

## Step 2: Start New Project
- Select "Custom Game Cards" (or equivalent)
- Card size: Poker (63 x 88mm / 2.5 x 3.5 inches)
- Quantity: [from manifest]
- Card stock: [recommendation from Phase 0B]
- Finish: [recommendation from Phase 0B]

## Step 3: Upload Card Fronts
- Navigate to "Upload Front Images"
- Upload all files from output/print/fronts/
- Verify all images loaded correctly (count should match)
- Assign quantities per the manifest:
  [table of card name -> quantity]

## Step 4: Upload Card Back
- Navigate to "Upload Back Image"
- Upload output/print/backs/card_back.tiff
- Select "Same back for all cards"

## Step 5: Review & Order
- Preview at least 5 random cards in the printer's preview tool
- Verify text is readable, art is not cropped incorrectly
- Confirm total price matches estimate
- Place order

## Order Tracking
- Order date: ___
- Order number: ___
- Estimated delivery: ___
- Tracking number: ___
```

**Print service-specific variations**: The guide template is parameterized. Phase 0B research identifies the chosen print service and populates service-specific instructions (URL, terminology, upload flow).

---

### 5B.2: Test Batch Selection

**Goal**: Order a small batch (~20 cards) to verify print quality before committing to the full order.

**Representative sample selection algorithm**:

Pick 20 cards that cover:
- 1 card from each color (5 cards): White, Blue, Black, Red, Green
- 1 multicolor card
- 1 artifact
- 1 land (non-basic)
- 1 basic land
- 1 planeswalker (if exists)
- 1 card with maximum rules text length (tests text readability at small size)
- 1 card with minimum rules text (tests art prominence)
- 1 card with longest name (tests name rendering)
- 1 card per frame type used in the set (standard creature, standard instant, etc.)
- Fill remaining slots with cards that have diverse art styles (brightest, darkest, most detailed)

```python
# mtgai/print/test_batch.py

def select_test_batch(cards: list[Card], batch_size: int = 20) -> list[Card]:
    batch = []

    # Mandatory representatives
    batch.append(pick_one(cards, color="W"))
    batch.append(pick_one(cards, color="U"))
    batch.append(pick_one(cards, color="B"))
    batch.append(pick_one(cards, color="R"))
    batch.append(pick_one(cards, color="G"))
    batch.append(pick_one(cards, is_multicolor=True))
    batch.append(pick_one(cards, type_line_contains="Artifact"))
    batch.append(pick_one(cards, type_line_contains="Land", exclude_basic=True))
    batch.append(pick_one(cards, is_basic_land=True))

    # Edge cases
    batch.append(max(remaining(cards, batch), key=lambda c: len(c.rules_text)))
    batch.append(min(remaining(cards, batch), key=lambda c: len(c.rules_text)))
    batch.append(max(remaining(cards, batch), key=lambda c: len(c.name)))

    # Planeswalker if available
    pw = pick_one(cards, type_line_contains="Planeswalker")
    if pw:
        batch.append(pw)

    # Fill with diverse art
    while len(batch) < batch_size:
        # Pick the card most visually different from current batch
        # (heuristic: different card types, different colors)
        batch.append(pick_most_different(remaining(cards, batch), batch))

    return batch
```

**Output**: `output/print/test_batch/` directory with just the 20 selected cards, plus a `test_batch_manifest.csv`.

---

### 5B.3: Quality Verification Checklist

**What to check when the test batch arrives** (generated as a printable checklist):

```markdown
# Test Batch Quality Verification

## Card-Level Checks (check 3+ cards)
- [ ] Card dimensions correct (63 x 88mm ± 0.5mm)
- [ ] No important content cut off by trimming
- [ ] Bleed area trimmed evenly on all sides
- [ ] Text is readable at arm's length
- [ ] Small text (collector info, artist credit) is legible with slight effort
- [ ] Mana symbols are clearly distinguishable
- [ ] Art is not blurry or pixelated
- [ ] Art colors match screen colors reasonably (CMYK shift is expected but should not be extreme)
- [ ] Card back is centered and even

## Stock & Finish Checks
- [ ] Card stock feels appropriate (not too flimsy, not too stiff)
- [ ] Cards shuffle well together
- [ ] Cards shuffle well with real MTG cards (similar thickness/flexibility)
- [ ] Finish is consistent across all cards (no patches of different sheen)
- [ ] No visible printing artifacts (streaks, smudges, misalignment)

## Comparison Checks
- [ ] Place test card next to a real MTG card — size matches
- [ ] Place test card in a card sleeve — fits correctly
- [ ] Text size is comparable to real MTG cards
- [ ] Overall "feel" is acceptable for gameplay use

## Issues Found
Card #___ Issue: ___________________________________
Card #___ Issue: ___________________________________

## Verdict
- [ ] APPROVE — proceed with full order
- [ ] ADJUST — need to fix [specific issue] and re-order test batch
- [ ] REJECT — quality insufficient, explore alternative print service
```

---

### 5B.4: Full Order Checklist

**Final checklist before placing the full order** (run after test batch approval):

```markdown
# Full Order Pre-Flight Checklist

## Validation
- [ ] Phase 4 report verdict: PASS (or WARN with all warnings reviewed)
- [ ] Test batch approved (date: ___)
- [ ] No card changes since test batch was ordered

## Files
- [ ] All card fronts exported (count: ___)
- [ ] Card back file present
- [ ] All files are CMYK, 300 DPI, correct dimensions with bleed
- [ ] File names match manifest

## Order Details
- [ ] Draft set: ___ packs of 15 cards = ___ total cards
- [ ] Full playset: ___ unique cards x copies = ___ total cards
- [ ] Combined order total: ___ cards
- [ ] Estimated cost: $___.___ + $___.___ shipping = $___.___ total
- [ ] Budget approved

## Print Service Settings
- [ ] Card size: Poker (63x88mm)
- [ ] Card stock: [from test batch]
- [ ] Finish: [from test batch]
- [ ] Same back for all cards: Yes
- [ ] Shipping to: Netherlands
- [ ] Estimated delivery: ___ weeks

## Post-Order
- [ ] Save order confirmation number
- [ ] Save tracking number when available
- [ ] Document in learnings/phase5.md
```

---

## Phase 5C: Assembly (Post-Delivery)

> Lightweight addition — mostly manual with a generated guide.

### 5C.1: Sorting Guide

When the print order arrives, all cards are in a single stack (or multiple stacks for large orders). Generate a sorting guide:

1. **Sort by collector number**: Cards should already be in order if the printer respects file order. Verify.
2. **Draft packs**: Follow `draft_manifest.json` to assemble cards into individual booster packs. Each pack gets:
   - A small label or divider (print a sheet of pack labels: "Pack 1", "Pack 2", etc.)
   - Cards in the specified order
   - Wrap with a rubber band or place in a small bag
3. **Playset binder**: Sort by collector number, place in a binder with 9-pocket pages.
4. **Basic land station**: Separate all basic lands into 5 piles by type.

### 5C.2: Set Guide Insert

Generate a one-page (front and back) "set guide" for inclusion with the finished product:

- **Front**: Set name, set symbol, 1-paragraph flavor introduction, list of mechanics with 1-line reminder text each
- **Back**: Draft archetype guide (10 color pairs, each with archetype name and 1-line strategy description)

This is generated as a print-ready PDF from the set's metadata. Use the same print service or a regular printer.

### 5C.3: Box Label

If storing in a deck box or card box:
- Generate a label image with: Set name, set symbol, card count, date
- Print on adhesive paper and attach to box

---

## Implementation Timeline & Dependencies

```
Phase 4A (Balance Analysis)
  Depends on: Phase 1C complete (all cards generated)
  New code: ManaCurveAnalyzer, PTAnalyzer, RemovalAnalyzer,
            CardAdvantageAnalyzer, PowerScorer, AsFanCalculator
  Estimated effort: Medium (most logic is statistical aggregation)

Phase 4B (Limited Environment)
  Depends on: Phase 4A (uses card pool data), Phase 1A (archetype definitions)
  New code: BoosterGenerator, SealedPoolGenerator, SealedPoolAnalyzer,
            ArchetypeAnalyzer, simulation harness
  Estimated effort: Medium-High (sealed simulation is new, non-trivial)

Phase 4C (Quality Checks)
  Depends on: Phase 1C validators (extends them), Phase 2C (for rendered card checks)
  New code: InteractionGraph, enhanced duplicate detection, flavor text checks
  Estimated effort: Medium (builds on Phase 1C foundation)

Phase 4 Report Generation
  Depends on: 4A + 4B + 4C complete
  New code: HTML report generator, CLI report formatter
  Estimated effort: Low-Medium (templating and formatting)

Phase 5A (Print Files)
  Depends on: Phase 4 PASS verdict, Phase 2C (rendered cards), Phase 0B (print specs)
  New code: CMYK converter, sheet generator, draft/playset generators, cost calculator
  Estimated effort: Medium

Phase 5B (Print Order)
  Depends on: Phase 5A complete
  New code: Guide generator, test batch selector, checklist generators
  Estimated effort: Low (mostly template generation)

Phase 5C (Assembly)
  Depends on: Physical delivery of printed cards
  New code: Sorting guide generator, set guide PDF generator
  Estimated effort: Low
```

**Recommended execution order**:

```
Phase 1C complete
      |
      v
Phase 4A + 4B (balance gate — run BEFORE art generation)
      |
      v
Fix any balance issues found
      |
      v
Phase 2A -> 2B -> 2C (art + rendering)
      |
      v
Phase 4C (quality checks on rendered cards)
      |
      v
Phase 4 Report (full report generation)
      |
      v
Phase 5A (print file export)
      |
      v
Phase 5B.2 (test batch order)
      |
      v
Wait for delivery + Phase 5B.3 (quality verification)
      |
      v
Phase 5B.4 (full order)
      |
      v
Wait for delivery + Phase 5C (assembly)
```

---

## File Structure

New files added in Phase 4-5:

```
mtgai/
  validation/           # Existing from Phase 1C
    balance.py          # Extended: ManaCurveAnalyzer, PTAnalyzer, etc.
    rules_grammar.py    # Extended: enhanced grammar checks
    spellcheck.py       # Extended: MTG dictionary
    duplicates.py       # Extended: multi-layer similarity
    interactions.py     # NEW: cross-card interaction graph
    power_scorer.py     # NEW: rarity power distribution
  limited/              # NEW package
    __init__.py
    booster.py          # BoosterGenerator
    sealed.py           # SealedPoolGenerator, SealedPoolAnalyzer
    archetypes.py       # ArchetypeAnalyzer
    simulation.py       # Statistical simulation harness
  report/               # NEW package
    __init__.py
    generator.py        # Orchestrates all validators, produces report
    html_report.py      # HTML report generation
    cli_report.py       # CLI text report generation
    charts.py           # SVG chart generation for HTML report
  print/                # NEW package
    __init__.py
    export.py           # RGB->CMYK conversion, DPI checks, batch export
    sheets.py           # Card sheet layout, crop marks
    draft.py            # Draft set booster generation
    playset.py          # Full playset quantity calculation
    cost.py             # Cost estimator
    manifest.py         # Order manifest generation
    test_batch.py       # Test batch selection
    guides.py           # Order guide, verification checklist generation

config/
  balance_targets.json  # Tunable balance parameters
  mtg_dictionary.txt    # Custom spell-check dictionary
  print_services.json   # Print service pricing and specs
  removal_patterns.json # Regex patterns for removal detection
  keyword_values.json   # Keyword power values for scoring

output/
  reports/
    validation-report.html
    validation-report.txt
  print/
    fronts/
    backs/
    sheets/
    draft/
    playset/
    test_batch/
    manifest.json
    manifest.csv
    ORDER_GUIDE.md
    QUALITY_CHECKLIST.md
    FULL_ORDER_CHECKLIST.md
```

---

## CLI Commands

```bash
# Phase 4: Validation
python -m mtgai.report generate                     # Run full validation, generate both reports
python -m mtgai.report generate --format html       # HTML only
python -m mtgai.report generate --format cli        # CLI only
python -m mtgai.report generate --sealed-sims 1000  # High-confidence simulation
python -m mtgai.report generate --seed 42           # Reproducible results
python -m mtgai.report generate --sections 4a,4b    # Run only specific sections

# Phase 5: Print
python -m mtgai.print export                        # Export all print-ready files
python -m mtgai.print export --format tiff          # Force TIFF output
python -m mtgai.print export --color-space cmyk     # Force CMYK (default)
python -m mtgai.print sheets                        # Generate card sheets
python -m mtgai.print draft --players 8             # Generate draft set for 8 players
python -m mtgai.print draft --players 6 --seed 42   # 6-player draft, reproducible
python -m mtgai.print playset                       # Generate full playset manifest
python -m mtgai.print playset --mythic-copies 4     # 4x mythics instead of 2x
python -m mtgai.print cost                          # Show cost estimate
python -m mtgai.print test-batch                    # Select and export test batch
python -m mtgai.print guide                         # Generate order guide
```
