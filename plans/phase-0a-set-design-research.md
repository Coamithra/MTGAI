# Phase 0A: MTG Set Design Research — Implementation Plan

## 1. Objective

**What this phase delivers:**
A comprehensive, data-backed reference document (`research/set-design.md`) and a reusable structural template (`research/set-template.json`) that define the exact statistical profile of a modern Magic: The Gathering set. Every number in these documents is verified against real Scryfall data from recent sets.

**Why it matters:**
This phase is the foundation for the entire project. Phase 1A (Set Skeleton Generator) directly consumes `set-template.json` to allocate card slots. If the distribution targets are wrong — too many creatures at common, wrong mana curve shape, missing removal density — the generated set will feel broken in limited play. Phase 1C (Card Generator) uses the design principles documented here to guide LLM prompts. Phase 4 (Validation) compares the finished set against these benchmarks. Getting Phase 0A wrong cascades errors through every downstream phase.

---

## Quick Start (Context Reset)

**Prerequisites**: Python installed. Internet access for Scryfall API. No prior phases required.

**Read first**: This plan is self-contained. Optionally skim `plans/master-plan.md` for project context.

**Start with**: Task 0A-1 (Scryfall data pull script).

**You're done when**: All items in Section 6 (Verification Criteria) are checked off.

---

## 2. Detailed Tasks

### Task 0A-1: Scryfall API Exploration & Data Pull Script
**Deliverable:** Python script `research/scripts/scryfall_pull.py` that fetches and stores raw set data.

- Write a Python script using `requests` (or `httpx`) to query the Scryfall API
- Implement rate limiting (50-100ms delay between requests; Scryfall allows 10 req/sec but good citizenship suggests staying below that)
- Pull full card data for 5 sets (see Section 3 for set list)
- Store raw JSON responses in `research/raw-data/<set-code>/cards.json`
- Handle pagination (Scryfall returns max 175 cards per page; follow `next_page` URLs)
- Filter out tokens, art cards, and non-playable extras (use `is:booster` or filter by `games` containing `"paper"` and exclude tokens/extras via card layout)
- Log progress and errors to stdout

### Task 0A-2: Data Analysis Script
**Deliverable:** Python script `research/scripts/analyze_sets.py` that reads raw data and computes all metrics.

- Read stored raw JSON from Task 0A-1
- Compute every metric listed in Section 4 (Data Collection Plan)
- Output results as both human-readable tables (printed to stdout / written to a summary file) and structured JSON
- Generate comparison tables across all analyzed sets
- Flag any anomalies or outliers (e.g., if a set has unusual color balance)

### Task 0A-3: Set Design Research Document
**Deliverable:** `research/set-design.md`

- Synthesize Scryfall data analysis with design philosophy knowledge
- Cover all three agent focus areas from the master plan:
  - **Agent 1 — Set Structure**: Card counts, rarity distribution, color distribution, type spread, mana curve (backed by data from Task 0A-2)
  - **Agent 2 — Mechanics & Balance**: Evergreen keywords, new mechanics patterns, legendary/planeswalker counts, color pie rules, draft archetypes
  - **Agent 3 — Design Philosophy**: New World Order, as-fan, theme-mechanic connections, storytelling patterns
- Include actual data tables with per-set breakdowns and computed averages
- Document decision rules (e.g., "a standard set should have 101 commons, 80 uncommons, 60 rares, 20 mythic rares")
- See Section 5 for the exact structure

### Task 0A-4: Set Template JSON
**Deliverable:** `research/set-template.json`

- Machine-readable template encoding the target distribution for a new set
- Derived directly from the averages/medians computed in Task 0A-2
- Includes slot allocation targets, acceptable ranges, and constraints
- See Section 5 for the exact schema

### Task 0A-5: Learnings Document
**Deliverable:** `learnings/phase0a.md`

- What worked, what didn't
- Scryfall API quirks encountered
- Data surprises (sets that deviated from expectations and why)
- Parameter adjustments for downstream phases
- Anti-patterns to avoid

### Task 0A-6: Verification & Cross-Check
**Deliverable:** Verification log appended to `learnings/phase0a.md`

- Cross-check computed numbers against at least 2 independent sources (MTG wiki set pages, WotC announcement articles listing card counts)
- Verify that `set-template.json` produces sensible allocations when applied to a hypothetical 280-card set
- Ensure all downstream consumers (Phase 1A, 1C, 4) have the data they need

---

## 3. Research Methodology

### 3.1 Scryfall API Reference

**Base URL:** `https://api.scryfall.com`

**Authentication:** None required. The API is free and public.

**Rate Limits:** Scryfall requests a maximum of 10 requests per second. To be a good API citizen, the script should insert a **100ms delay** between requests (achieving ~10 req/sec). If batch-pulling multiple sets, add a 500ms pause between sets.

**Required Headers:**
- `User-Agent`: Must include a descriptive project name and contact info (Scryfall requires this). Example: `User-Agent: MTGAISetCreator/0.1 (contact: <your-email>)`
- `Accept: application/json`

**Key Endpoints:**

| Endpoint | Purpose | Example |
|----------|---------|---------|
| `GET /sets` | List all sets with metadata | `https://api.scryfall.com/sets` |
| `GET /sets/:code` | Get a specific set's metadata | `https://api.scryfall.com/sets/dsk` |
| `GET /cards/search?q=...` | Search cards with Scryfall syntax | `https://api.scryfall.com/cards/search?q=set:dsk` |
| `GET /bulk-data` | Bulk data download links (alternative) | `https://api.scryfall.com/bulk-data` |

**Search Syntax (for the `q` parameter):**

| Filter | Syntax | Example |
|--------|--------|---------|
| Set code | `set:xxx` | `set:dsk` |
| Rarity | `rarity:common` (or `r:c`) | `set:dsk r:c` |
| Color | `color:white` (or `c:w`) | `set:dsk c:w` |
| Color identity | `id:wu` | `set:dsk id:wu` |
| Type | `type:creature` (or `t:creature`) | `set:dsk t:creature` |
| CMC | `cmc:3` or `cmc>=3` | `set:dsk cmc:3` |
| Is in boosters | `is:booster` | `set:dsk is:booster` |
| Keyword | `keyword:flying` (or `kw:flying`) | `set:dsk kw:flying` |

**Pagination:** Responses contain up to 175 cards. If `has_more` is `true`, follow the `next_page` URL. Continue until `has_more` is `false`.

**Card Object Fields We Need:**
`name`, `mana_cost`, `cmc` (converted mana cost), `type_line`, `oracle_text`, `power`, `toughness`, `loyalty`, `colors`, `color_identity`, `rarity`, `keywords` (array), `layout`, `set`, `collector_number`, `produced_mana`, `card_faces` (for DFCs), `legalities`, `games`

**Alternative: Bulk Data Download**
For large-scale analysis, Scryfall offers bulk data downloads at `GET /bulk-data`. The "Default Cards" file (~80MB JSON) contains every card. This avoids pagination entirely but requires filtering locally. Consider using this if pulling 5+ full sets — it's faster and more polite than hundreds of API calls.

**Recommendation:** Use the search API (`/cards/search?q=set:xxx+is:booster`) for targeted pulls of 5 sets. This keeps the data small and focused. Store raw responses for reuse. If we later need broader analysis, switch to bulk data.

### 3.2 Sets to Analyze

Pull data for **5 recent premier/Standard sets** to get a robust sample. Using 5 instead of 3 gives us better averages and lets us identify which patterns are consistent vs. set-specific.

| Set | Code | Release | Why Include |
|-----|------|---------|-------------|
| Duskmourn: House of Horror | `dsk` | Sep 2024 | Most recent standard set at time of research; horror theme |
| Bloomburrow | `blb` | Aug 2024 | Animal/nature theme; very different from Duskmourn |
| Outlaws of Thunder Junction | `otj` | Apr 2024 | Western theme; includes heist mechanics |
| Murders at Karlov Manor | `mkm` | Feb 2024 | Mystery/detective theme; includes investigate |
| The Lost Caverns of Ixalan | `lci` | Nov 2023 | Adventure theme; diverse card designs |

**Important:** Only analyze main set cards (those appearing in draft boosters). Exclude:
- Commander precon cards (these often have separate set codes, e.g., `dsc` for Duskmourn Commander)
- Special guests / bonus sheets (e.g., The List, Special Guests)
- Art cards, tokens, and non-playable extras
- Use `is:booster` in queries, then additionally filter results to exclude any remaining non-standard entries by checking the `layout` field (exclude `token`, `art_series`, `emblem`)

### 3.3 Design Philosophy Research

This does not come from Scryfall — it requires synthesizing established MTG design knowledge:

- **New World Order (NWO):** Common cards must be simple. Complexity is pushed to uncommon and above. Commons should have at most 1 keyword or ability. Board complexity at common is limited.
- **As-Fan:** The expected number of copies of a card type/mechanic per booster pack. Calculate from rarity distribution. Example: if 10 of 101 commons have flying, as-fan of flying at common is 10/101 * 10 (commons per pack) ≈ 0.99.
- **Color Pie Rules:** Which effects belong to which colors (e.g., direct damage = Red, card draw = Blue, lifegain = White, creature destruction = Black, artifact/enchantment removal = Green/White)
- **Draft Archetypes:** Each of the 10 two-color pairs should have a supported archetype. Typically signaled by uncommon multicolor "signpost" cards. Document the archetype patterns across analyzed sets.
- **BREAD (Best, Removal, Evasion, Advantage, Dregs):** How removal, evasion, and card advantage are distributed by color and rarity.

Sources: Mark Rosewater's "Making Magic" column archive (especially NWO article from 2011, annual State of Design articles), GDS3 essays, MTG wiki entries on set design.

---

## 4. Data Collection Plan

### 4.1 Per-Set Metrics to Extract

All metrics below should be computed for each of the 5 analyzed sets, plus a cross-set average and range.

#### A. Total Card Counts

| Metric | How to Compute |
|--------|---------------|
| Total cards in set (booster-eligible) | Count of cards where `is:booster` |
| Cards per rarity | Group by `rarity` field: `common`, `uncommon`, `rare`, `mythic` |
| Basic lands count | Count where `type_line` contains "Basic Land" |
| Total unique cards (excluding basic lands) | Total minus basic lands |

#### B. Color Distribution

| Metric | How to Compute |
|--------|---------------|
| Mono-color card counts (W/U/B/R/G) | Cards where `colors` has exactly 1 element |
| Multicolor card count | Cards where `colors` has 2+ elements |
| Colorless card count | Cards where `colors` is empty and not a land |
| Color pair distribution (for multicolor) | Group multicolor cards by their `colors` sorted pair (e.g., WU, WB, WR, etc.) |
| Per-color percentage of total | (mono-X + multi-including-X) / total, and also mono-X / total |
| Per-rarity color distribution | Cross-tab: for each rarity, what % is each mono-color? |

#### C. Card Type Distribution

| Metric | How to Compute |
|--------|---------------|
| Creature count (and % of total) | `type_line` contains "Creature" |
| Instant count | `type_line` contains "Instant" |
| Sorcery count | `type_line` contains "Sorcery" |
| Enchantment count (non-creature) | `type_line` contains "Enchantment" but not "Creature" |
| Artifact count (non-creature) | `type_line` contains "Artifact" but not "Creature" |
| Land count (non-basic) | `type_line` contains "Land" but not "Basic" |
| Planeswalker count | `type_line` contains "Planeswalker" |
| Other/hybrid types | Enchantment Creatures, Artifact Creatures (counted separately) |
| Per-rarity type distribution | Cross-tab: for each rarity, card type breakdown |
| Per-color type distribution | Cross-tab: for each mono-color, card type breakdown |

#### D. Mana Value (Converted Mana Cost) Curve

| Metric | How to Compute |
|--------|---------------|
| CMC distribution (0-7+) | Group by `cmc`, bucket 7+ together |
| Per-color mana curve | Cross-tab: for each mono-color, CMC distribution |
| Per-rarity mana curve | Cross-tab: for each rarity, CMC distribution |
| Average CMC overall | Mean of `cmc` across all non-land cards |
| Average CMC per color | Mean of `cmc` per mono-color |
| Median CMC overall and per color | Median of `cmc` |

#### E. Creature Statistics

| Metric | How to Compute |
|--------|---------------|
| Power/Toughness distribution | Group creatures by P/T (as integers where possible; handle `*` separately) |
| Average P/T per CMC | For creatures at each CMC, average power and average toughness |
| P/T vs CMC efficiency | Scatter data: (cmc, power, toughness) for all creatures |
| Creature subtypes frequency | Top 20 most common creature subtypes |

#### F. Keyword & Mechanic Analysis

| Metric | How to Compute |
|--------|---------------|
| Evergreen keyword frequency | Count of each keyword in the `keywords` array: flying, first strike, double strike, deathtouch, haste, hexproof, indestructible, lifelink, menace, reach, trample, vigilance, defender, flash, ward |
| Evergreen keywords per color | Cross-tab: for each color, frequency of each evergreen keyword |
| Evergreen keywords per rarity | Cross-tab: for each rarity, frequency of each evergreen keyword |
| Set-specific mechanic count | Keywords in `keywords` array that are NOT evergreen (these are set mechanics) |
| Number of distinct set mechanics | Count of unique non-evergreen keywords |
| Set mechanic distribution by rarity | How many cards per rarity have each set mechanic |
| Set mechanic distribution by color | How many cards per color have each set mechanic |
| As-fan calculation per keyword | For each keyword: (count at common / total commons) * commons per pack + (count at uncommon / total uncommons) * uncommons per pack + (count at rare / total rares) * rares per pack |

#### G. Special Card Counts

| Metric | How to Compute |
|--------|---------------|
| Legendary creatures count | `type_line` contains "Legendary Creature" |
| Legendary count per rarity | Cross-tab |
| Planeswalker count per rarity | Typically all mythic or rare |
| Saga count | `type_line` contains "Saga" (if present) |
| Modal DFC count | `layout` == "modal_dfc" |
| Transform DFC count | `layout` == "transform" |
| Equipment count | `type_line` contains "Equipment" |
| Aura count | `type_line` contains "Aura" |
| Vehicles count | `type_line` contains "Vehicle" |

#### H. Removal & Interaction Density

| Metric | How to Compute |
|--------|---------------|
| Removal spell count (approximate) | Cards whose `oracle_text` matches patterns: "destroy target", "exile target", "deals X damage to", "-X/-X", "target creature gets -" |
| Removal per color | Cross-tab |
| Removal per rarity | Cross-tab (important for limited — commons need baseline removal) |
| Counterspell count | `oracle_text` contains "counter target spell" |
| Combat trick count (approximate) | Instants where `oracle_text` contains "+X/+X" or "gets +", filtered to creatures |

#### I. Draft Archetype Signals

| Metric | How to Compute |
|--------|---------------|
| Uncommon multicolor cards | Cards at uncommon with 2+ colors — these are typically "signpost uncommons" |
| Color pair coverage at uncommon | Which of the 10 two-color pairs have an uncommon multicolor card |
| Rare/Mythic multicolor cards | Distribution of multicolor across color pairs at higher rarities |

#### J. Booster Pack Composition

| Metric | Source |
|--------|--------|
| Cards per booster pack | Known: 15 cards (10C + 3U + 1R/M + 1 Land in play boosters; draft boosters similar) |
| Mythic frequency | Known: ~1 in 7 rare slots is mythic (approximately 1:7 ratio) |
| Foil slot rules | Document current booster structure for play boosters vs draft boosters |

### 4.2 Cross-Set Aggregation

After computing per-set metrics, produce:

| Aggregation | Purpose |
|-------------|---------|
| Average across all 5 sets | Target values for `set-template.json` |
| Min/Max range | Acceptable variance window |
| Standard deviation | How consistent are these numbers across sets |
| Trend direction | Are recent sets trending toward more/fewer creatures, higher/lower curves, etc. |

---

## 5. Output Specifications

### 5.1 `research/set-design.md` Structure

```markdown
# MTG Set Design Reference

## 1. Executive Summary
Brief overview of findings: what defines a modern MTG set structurally.

## 2. Set Structure

### 2.1 Card Counts
Table: Per-set card counts by rarity, plus averages.
| Set | Commons | Uncommons | Rares | Mythics | Basic Lands | Total (Booster) |
Decision: Target card count for our set.

### 2.2 Color Distribution
Table: Per-set mono-color counts (W/U/B/R/G), multicolor, colorless.
Table: Percentage breakdown.
Finding: Expected per-color percentage and acceptable range.

### 2.3 Card Type Spread
Table: Creature/Instant/Sorcery/Enchantment/Artifact/Land/Planeswalker counts per set.
Table: Percentage breakdown.
Table: Per-rarity type distribution.
Finding: Creature-to-noncreature ratio, spell type mix.

### 2.4 Mana Curve
Table: CMC distribution (0, 1, 2, 3, 4, 5, 6, 7+) counts and percentages per set.
Chart description: Shape of the curve (peaks at 2-3, drops off sharply at 5+).
Table: Per-color mana curve.
Finding: Target CMC distribution.

### 2.5 Creature Statistics
Table: Average P/T by CMC.
Notable patterns: Vanilla test benchmarks per CMC.

## 3. Mechanics & Balance

### 3.1 Evergreen Keywords
Table: Frequency of each evergreen keyword across all 5 sets.
Table: Color assignment patterns (flying = W/U, deathtouch = B/G, etc.).
Table: Rarity distribution (most keywords at common/uncommon).

### 3.2 Set-Specific Mechanics
Table: How many new mechanics each set introduced.
Table: Mechanic distribution by rarity and color.
Pattern: Typically 2-4 new named mechanics per set, appearing on 15-40 cards total.

### 3.3 Legendary & Planeswalker Distribution
Table: Legendary creature counts by rarity and color.
Table: Planeswalker counts.
Pattern: Legendaries primarily at rare/mythic; some uncommon legendaries in recent sets.

### 3.4 Removal Density
Table: Removal spells per color per rarity.
Finding: Minimum removal density needed for healthy limited.

### 3.5 Draft Archetype Structure
Table: The 10 two-color archetypes per set and their signpost uncommons.
Pattern: How archetypes are signaled and supported.

## 4. Design Philosophy

### 4.1 New World Order
Summary of NWO principles and how they manifest in the data.
Common card complexity analysis.

### 4.2 As-Fan Calculations
Table: As-fan for key mechanics across the 5 sets.
Target: Recommended as-fan ranges for custom set mechanics.

### 4.3 Color Pie Reference
Summary: Which effects belong to which colors.
Table: Primary, secondary, and tertiary color assignments for common effects.

### 4.4 Theme-Mechanic Connection
How each analyzed set connects its theme to its mechanics.
Patterns for our own set design.

### 4.5 Storytelling Through Cards
How sets use legendary creatures, flavor text, and card names to tell stories.
Pattern: Named characters, location cards, event cards.

## 5. Recommendations for Our Set
Concrete targets derived from the data:
- Recommended total card count
- Rarity breakdown
- Color distribution targets
- Type spread targets
- Mana curve targets
- Mechanic slot budget
- Removal density minimums
- Draft archetype guidelines

## Appendix A: Raw Data Summary Tables
Full data tables for all 5 sets (the detailed numbers behind every finding above).

## Appendix B: Methodology Notes
How data was collected, any edge cases encountered, known limitations.

## Appendix C: Sources
Links to Scryfall queries used, articles referenced.
```

### 5.2 `research/set-template.json` Schema

This is the machine-readable output that Phase 1A (Set Skeleton Generator) consumes directly.

```json
{
  "meta": {
    "version": "1.0",
    "generated_from": ["dsk", "blb", "otj", "mkm", "lci"],
    "generated_date": "YYYY-MM-DD",
    "description": "Target distribution template for a standard MTG set, derived from analysis of 5 recent sets."
  },

  "set_size": {
    "total_booster_cards": { "target": 281, "min": 260, "max": 300 },
    "basic_lands": { "target": 5, "note": "1 per color, full-art versions optional" }
  },

  "rarity_distribution": {
    "common":  { "count": 101, "min": 80, "max": 111 },
    "uncommon": { "count": 80, "min": 60, "max": 100 },
    "rare":    { "count": 60, "min": 50, "max": 70 },
    "mythic":  { "count": 20, "min": 15, "max": 25 }
  },

  "color_distribution": {
    "description": "Percentage of non-land, non-colorless cards per mono-color",
    "per_color_target_pct": { "W": 20, "U": 20, "B": 20, "R": 20, "G": 20 },
    "tolerance_pct": 2,
    "multicolor_pct": { "target": 12, "min": 8, "max": 18 },
    "colorless_pct": { "target": 8, "min": 5, "max": 12 },
    "per_rarity": {
      "common": {
        "per_color_count": { "target": 18, "min": 15, "max": 21 },
        "multicolor_count": { "target": 0, "min": 0, "max": 2, "note": "Commons are almost never multicolor" },
        "colorless_count": { "target": 5, "min": 2, "max": 8 }
      },
      "uncommon": {
        "per_color_count": { "target": 12, "min": 10, "max": 15 },
        "multicolor_count": { "target": 10, "min": 10, "max": 15, "note": "The 10 signpost uncommons" },
        "colorless_count": { "target": 5, "min": 2, "max": 8 }
      },
      "rare": {
        "per_color_count": { "target": 8, "min": 6, "max": 12 },
        "multicolor_count": { "target": 10, "min": 5, "max": 15 },
        "colorless_count": { "target": 5, "min": 2, "max": 8 }
      },
      "mythic": {
        "per_color_count": { "target": 3, "min": 2, "max": 4 },
        "multicolor_count": { "target": 3, "min": 1, "max": 5 },
        "colorless_count": { "target": 2, "min": 0, "max": 3 }
      }
    }
  },

  "type_distribution": {
    "creature_pct":           { "target": 50, "min": 45, "max": 58 },
    "instant_pct":            { "target": 12, "min": 8, "max": 16 },
    "sorcery_pct":            { "target": 10, "min": 6, "max": 14 },
    "enchantment_pct":        { "target": 8, "min": 4, "max": 14 },
    "artifact_pct":           { "target": 8, "min": 4, "max": 14 },
    "land_nonbasic_pct":      { "target": 5, "min": 3, "max": 8 },
    "planeswalker_pct":       { "target": 1.5, "min": 1, "max": 3 },
    "per_rarity": {
      "common": {
        "creature_pct": { "target": 55, "min": 50, "max": 65 },
        "noncreature_spell_pct": { "target": 40, "min": 30, "max": 45 },
        "land_pct": { "target": 5, "min": 0, "max": 8 }
      },
      "uncommon": {
        "creature_pct": { "target": 45, "min": 38, "max": 55 },
        "noncreature_spell_pct": { "target": 45, "min": 35, "max": 55 },
        "land_pct": { "target": 8, "min": 3, "max": 12 }
      }
    }
  },

  "mana_curve": {
    "description": "Percentage of non-land cards at each CMC",
    "overall": {
      "cmc_0": { "target_pct": 2, "min": 0, "max": 4 },
      "cmc_1": { "target_pct": 10, "min": 7, "max": 14 },
      "cmc_2": { "target_pct": 20, "min": 16, "max": 25 },
      "cmc_3": { "target_pct": 22, "min": 18, "max": 27 },
      "cmc_4": { "target_pct": 18, "min": 14, "max": 22 },
      "cmc_5": { "target_pct": 13, "min": 9, "max": 16 },
      "cmc_6": { "target_pct": 8, "min": 5, "max": 12 },
      "cmc_7plus": { "target_pct": 5, "min": 2, "max": 8 }
    },
    "per_color": {
      "description": "Same structure as overall, keyed by W/U/B/R/G. Computed from data.",
      "note": "Red tends to curve lower; Green tends to curve higher."
    },
    "per_rarity": {
      "description": "Same structure as overall, keyed by rarity. Computed from data.",
      "note": "Commons curve lower on average; mythics tend to have higher CMC."
    },
    "average_cmc": { "target": 3.2, "min": 2.8, "max": 3.6, "note": "Excluding lands" }
  },

  "keywords": {
    "evergreen": {
      "flying":        { "typical_count": 20, "min": 15, "max": 28, "primary_colors": ["W", "U"] },
      "first_strike":  { "typical_count": 6,  "min": 3,  "max": 10, "primary_colors": ["W", "R"] },
      "double_strike": { "typical_count": 2,  "min": 0,  "max": 4,  "primary_colors": ["R", "W"] },
      "deathtouch":    { "typical_count": 8,  "min": 4,  "max": 12, "primary_colors": ["B", "G"] },
      "haste":         { "typical_count": 8,  "min": 4,  "max": 12, "primary_colors": ["R"] },
      "hexproof":      { "typical_count": 4,  "min": 2,  "max": 7,  "primary_colors": ["U", "G"] },
      "indestructible": { "typical_count": 3, "min": 1,  "max": 6,  "primary_colors": ["W"] },
      "lifelink":      { "typical_count": 7,  "min": 4,  "max": 12, "primary_colors": ["W", "B"] },
      "menace":        { "typical_count": 6,  "min": 3,  "max": 10, "primary_colors": ["B", "R"] },
      "reach":         { "typical_count": 5,  "min": 3,  "max": 8,  "primary_colors": ["G"] },
      "trample":       { "typical_count": 8,  "min": 4,  "max": 12, "primary_colors": ["G", "R"] },
      "vigilance":     { "typical_count": 7,  "min": 4,  "max": 12, "primary_colors": ["W", "G"] },
      "defender":      { "typical_count": 4,  "min": 2,  "max": 7,  "primary_colors": ["any"] },
      "flash":         { "typical_count": 6,  "min": 3,  "max": 10, "primary_colors": ["U", "G"] },
      "ward":          { "typical_count": 5,  "min": 2,  "max": 8,  "primary_colors": ["U", "W"] }
    },
    "set_mechanics": {
      "typical_count": { "target": 3, "min": 2, "max": 5 },
      "total_cards_with_set_mechanic": { "target": 40, "min": 20, "max": 60 },
      "note": "Each mechanic typically appears on 8-20 cards, spread across 2-3 colors"
    }
  },

  "special_cards": {
    "legendary_creatures": { "target": 20, "min": 15, "max": 30 },
    "planeswalkers":       { "target": 4,  "min": 2,  "max": 6 },
    "nonbasic_lands":      { "target": 15, "min": 10, "max": 20 },
    "equipment":           { "target": 4,  "min": 2,  "max": 8 },
    "auras":               { "target": 6,  "min": 3,  "max": 10 },
    "vehicles":            { "target": 2,  "min": 0,  "max": 5, "note": "Not all sets have vehicles" }
  },

  "removal_density": {
    "total_removal_spells": { "target": 25, "min": 20, "max": 35 },
    "common_removal":       { "target": 10, "min": 7,  "max": 15, "note": "Critical for limited play" },
    "per_color_minimum":    { "target": 2,  "note": "Every color should have at least 2 removal-adjacent effects at common" },
    "counterspells":        { "target": 3,  "min": 2,  "max": 5, "primary_color": "U" }
  },

  "draft_archetypes": {
    "count": 10,
    "structure": "One archetype per two-color pair",
    "signpost_uncommons": {
      "count": 10,
      "description": "One multicolor uncommon per color pair that signals the draft archetype"
    },
    "color_pairs": ["WU", "WB", "WR", "WG", "UB", "UR", "UG", "BR", "BG", "RG"]
  },

  "booster_composition": {
    "draft_booster": {
      "total_cards": 15,
      "commons": 10,
      "uncommons": 3,
      "rare_or_mythic": 1,
      "land": 1,
      "mythic_frequency": "1 in ~7 rare slots"
    }
  }
}
```

**Note:** All `target`, `min`, and `max` values shown above are illustrative estimates. The actual values must be computed from the real Scryfall data during execution. The script from Task 0A-2 will populate this template with real averages and ranges.

---

## 6. Verification Criteria

Phase 0A is complete when ALL of the following are true:

### 6.1 Data Completeness
- [ ] Raw Scryfall data stored for all 5 sets in `research/raw-data/<set-code>/cards.json`
- [ ] All metrics from Section 4 computed and present in the analysis output
- [ ] No placeholder or estimated values remain in `set-design.md` — every number is backed by data
- [ ] `set-template.json` is valid JSON and parseable

### 6.2 Data Accuracy
- [ ] Card counts per set cross-checked against at least one independent source (MTG wiki, Scryfall set page, or WotC announcement) — discrepancies documented with explanation
- [ ] Color distribution sums to 100% (within rounding)
- [ ] Type distribution sums to 100% (within rounding, accounting for dual-type cards)
- [ ] Mana curve distribution sums to 100% (within rounding)
- [ ] Rarity counts sum to total booster-eligible cards

### 6.3 Template Validity
- [ ] `set-template.json` passes JSON schema validation
- [ ] Applying the template to a hypothetical 280-card set produces allocations where:
  - Every slot is filled (no negative counts, no impossible constraints)
  - Color balance is within tolerance
  - Rarity totals match the target
  - A full 15-card booster pack can be constructed from the allocation
- [ ] The template's `min`/`max` ranges are not so tight they would reject real sets, and not so loose they allow degenerate distributions

### 6.4 Design Philosophy Coverage
- [ ] New World Order principles documented with concrete examples from analyzed sets
- [ ] Color pie reference table present with at least 15 common effect categories assigned to colors
- [ ] All 10 draft archetype slots documented for at least 3 of the 5 analyzed sets
- [ ] As-fan calculations present for at least 5 mechanics

### 6.5 Downstream Readiness
- [ ] Phase 1A team can read `set-template.json` and implement a skeleton generator without needing to ask questions about the data format
- [ ] Phase 1C team can reference `set-design.md` for generation constraints and validation rules
- [ ] Phase 4 team can derive validation thresholds from the documented ranges

### 6.6 Scripts & Reproducibility
- [ ] `research/scripts/scryfall_pull.py` runs successfully and reproduces the stored raw data
- [ ] `research/scripts/analyze_sets.py` runs successfully and reproduces the analysis from the stored raw data
- [ ] Both scripts have usage instructions in their docstrings or a `research/scripts/README.md`

---

## 7. Dependencies

### 7.1 What Phase 0A Needs (Inputs)

| Dependency | Source | Status |
|------------|--------|--------|
| Python environment | Phase 0C sets up the project, but Phase 0A can run standalone with just Python + `requests` | Can start immediately; no blocker |
| Internet access | Scryfall API is public | Available |
| Master plan context | This document | Available |

**Phase 0A has no hard blockers.** It can start immediately and run in parallel with Phase 0B.

### 7.2 What Others Need from Phase 0A (Outputs)

| Consumer Phase | What They Need | Artifact |
|----------------|---------------|----------|
| **Phase 0C** (Project Setup) | Card data schema should be validated against Scryfall's data model | `research/raw-data/` (sample card JSON for schema comparison) |
| **Phase 0D** (LLM Strategy) | Understanding of how many cards need to be generated, what complexity levels exist | `research/set-design.md` (Section 2, Section 3) |
| **Phase 0E** (Prompt Spike) | Real card examples for few-shot prompts, distribution targets | `research/raw-data/` (real card JSON), `research/set-design.md` |
| **Phase 1A** (Skeleton Generator) | Exact slot allocation targets | `research/set-template.json` (primary consumer) |
| **Phase 1B** (Mechanic Designer) | Mechanic patterns, keyword distribution data | `research/set-design.md` (Section 3) |
| **Phase 1C** (Card Generator) | Balance constraints, rules text patterns, color pie rules | `research/set-design.md` (Sections 3, 4) |
| **Phase 4** (Validation) | Acceptable ranges for all metrics | `research/set-template.json` (min/max ranges) |

---

## 8. Cross-Cutting Concerns & Master Plan Suggestions

### 8.1 Analyze 5 Sets Instead of 3

**Suggestion:** The master plan specifies 3 sets (Duskmourn, Bloomburrow, Thunder Junction). This plan expands to 5 sets by adding Murders at Karlov Manor and The Lost Caverns of Ixalan. **Rationale:**

- 3 sets is a small sample. One unusual set (e.g., one with an abnormally high artifact count due to its theme) can skew averages significantly.
- With 5 sets, we can compute meaningful standard deviations and identify which metrics are stable across sets vs. theme-dependent.
- The marginal cost is minimal: ~2 extra minutes of API calls and analysis time.
- **Risk of not doing this:** Phase 1A builds a skeleton generator on unreliable averages, and Phase 4 validation uses ranges that are too tight or too loose.

### 8.2 Store Raw Scryfall Data for Reuse

**Suggestion:** The master plan does not mention storing raw API responses. This plan creates `research/raw-data/<set-code>/cards.json` to cache the full Scryfall card data.

**Benefits:**
- Phase 0C needs real card JSON to validate the card data schema against Scryfall's model
- Phase 0E needs real card examples as few-shot prompts for LLM card generation
- Phase 1C can use real cards as reference examples when generating cards
- Avoids redundant API calls if we need to re-analyze or add new metrics later
- Enables future analysis without re-fetching (Scryfall asks users not to make unnecessary repeated requests)

**Storage impact:** ~1-2 MB per set (175-300 cards as JSON). Negligible.

### 8.3 Missing Data Points in the Master Plan

The master plan mentions "card counts by rarity, color distribution, card type spread, mana curve" but does not explicitly call out several important metrics that this plan adds:

| Metric | Why It Matters |
|--------|---------------|
| **Removal density per color per rarity** | Without enough common removal, limited play is miserable. Phase 1C needs minimum targets. |
| **Creature subtype frequency** | Tribal themes need to know how many cards share subtypes in a typical set. |
| **As-fan calculations** | Critical for limited play balance — how often does a mechanic appear in a booster pack? Phase 1A needs this for mechanic slot allocation. |
| **Multicolor distribution across color pairs** | Not just "how many multicolor cards" but "how many per color pair." Phase 1A needs this to ensure all 10 draft archetypes are supported. |
| **Legendary creature count per rarity** | Recent sets have uncommon legendaries (for Commander interest). Important for Phase 1C. |
| **Dual-faced card (DFC) prevalence** | Some sets use DFCs heavily, others don't. Our set needs to decide early. Affects Phase 2C renderer complexity. |

**Recommendation:** Add these to the master plan's Phase 0A description.

### 8.4 DFC / Special Layout Decision

**Flag:** The master plan does not address whether our custom set will include double-faced cards (DFCs), split cards, adventure cards, or other special layouts. This has major implications:

- **Phase 2C (Renderer)** must support each layout type as a separate frame template — this is significant work.
- **Phase 5 (Printing)** — DFCs require double-sided printing, which not all print services support (or they charge extra).

**Recommendation:** Phase 0A should document DFC/special layout prevalence in recent sets, but the decision of whether to include them should be made during Phase 0C (Project Setup) as a scope decision. For V0/V1, strongly recommend **no DFCs or special layouts** to keep the renderer simple.

### 8.5 Play Booster vs. Draft Booster Distinction

**Flag:** Starting with Murders at Karlov Manor (Feb 2024), WotC replaced Draft Boosters and Set Boosters with a unified "Play Booster." Play Boosters have a different composition than the old Draft Boosters:

- Play Booster: 14 cards (6-7 commons, 3 uncommons, 1 rare/mythic, 1 land, 1 wildcard of any rarity, 1 non-playable — art card/token/ad, optionally 1 The List card)
- Old Draft Booster: 15 cards (10 commons, 3 uncommons, 1 rare/mythic, 1 land)

**The master plan's Phase 5A references "10C + 3U + 1R/M + 1 land" which is the old Draft Booster format.** Since our set is for custom drafting, we can use whichever format we prefer. But we should make this decision explicitly.

**Recommendation:** Document both formats in `set-design.md`. For our custom set, use the **classic Draft Booster format** (10C + 3U + 1R/M + 1 land = 15 cards) since it's simpler and optimized for draft play, which is our primary use case. Update the master plan accordingly.

### 8.6 Reprint Card Data

**Flag:** The master plan's Phase 1C mentions reprints ("selecting existing cards from Scryfall/MTGJSON data to fill skeleton slots"). The raw Scryfall data stored by Phase 0A is exactly what Phase 1C needs for this. However, the current plan only stores data for the 5 analyzed sets.

**Recommendation:** Document in `set-design.md` which types of cards are commonly reprinted (staple commons like Cancel, Naturalize; mana fixing lands; basic removal). Phase 1C can then query Scryfall directly for specific reprint candidates. No additional work needed in Phase 0A, but note the connection.

### 8.7 `set-template.json` Should Be Parameterizable

**Suggestion:** The template should include a `set_size_scaling` section that explains how to adjust all numbers if the set size changes. For example, if we decide on 250 cards instead of 280, the template should indicate how to proportionally scale rarity counts, color allocations, etc. This makes the template useful for V0 (~50 cards) as well as V1 (~280 cards).

**Recommendation:** Include scaling formulas or a scaling function description in the template, not just fixed counts. Phase 1A's skeleton generator can then accept a target card count and derive all other numbers from the template.

### 8.8 Timeline Estimate

| Task | Estimated Duration | Notes |
|------|-------------------|-------|
| 0A-1: Scryfall pull script | 1-2 hours | Straightforward API client with rate limiting |
| 0A-2: Analysis script | 2-3 hours | Many metrics to compute; most are groupby/count operations |
| 0A-3: Set design document | 3-4 hours | Synthesizing data + design philosophy research |
| 0A-4: Set template JSON | 1 hour | Derived from 0A-2 output |
| 0A-5: Learnings document | 30 min | Written as we go, polished at end |
| 0A-6: Verification | 1-2 hours | Cross-checking, template validation |
| **Total** | **8-12 hours** | Can be done in 1-2 focused sessions |

### 8.9 Execution Order Within Phase 0A

```
0A-1 (Scryfall pull script)
  |
  v
0A-2 (Analysis script)   ---- can partially overlap with 0A-3 (design philosophy research)
  |                             |
  v                             v
0A-4 (Template JSON) <---- 0A-3 (Set design document)
  |                             |
  v                             v
0A-6 (Verification) ---- 0A-5 (Learnings)
```

Task 0A-1 must complete first (we need data). Task 0A-3's design philosophy sections can be researched in parallel with 0A-2 since they don't depend on Scryfall data. The template (0A-4) needs the analysis (0A-2) to be complete. Verification (0A-6) is last.
