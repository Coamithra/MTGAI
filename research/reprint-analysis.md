# Reprint Pattern Analysis — 5 Reference Sets

> **Date**: 2026-03-13
> **Sets analyzed**: Duskmourn (DSK), Bloomburrow (BLB), Outlaws of Thunder Junction (OTJ), Murders at Karlov Manor (MKM), Lost Caverns of Ixalan (LCI)
> **Methodology**: Scryfall JSON data. Filtered out basic lands, tokens, and non-card entries. Each card counted once (deduplicated by name). Reprint status from Scryfall's `reprint` boolean field.

---

## 1. Reprint Count and Percentage by Set and Rarity

### Per-Set Summary

| Set | Total Cards | Total Reprints | Reprint % |
|-----|------------|---------------|-----------|
| DSK (Duskmourn) | 271 | 6 | 2.2% |
| BLB (Bloomburrow) | 261 | 5 | 1.9% |
| OTJ (Outlaws of Thunder Junction) | 271 | 12 | 4.4% |
| MKM (Murders at Karlov Manor) | 271 | 5 | 1.8% |
| LCI (Lost Caverns of Ixalan) | 286 | 11 | 3.8% |
| **Average** | **272.0** | **7.8** | **2.8%** |

### By Rarity — Per Set

| Set | Common (total/repr/%) | Uncommon (total/repr/%) | Rare (total/repr/%) | Mythic (total/repr/%) |
|-----|----------------------|------------------------|--------------------|--------------------|
| DSK | 91 / 3 / 3.3% | 100 / 2 / 2.0% | 60 / 1 / 1.7% | 20 / 0 / 0.0% |
| BLB | 81 / 4 / 4.9% | 100 / 0 / 0.0% | 60 / 1 / 1.7% | 20 / 0 / 0.0% |
| OTJ | 91 / 5 / 5.5% | 100 / 0 / 0.0% | 60 / 5 / 8.3% | 20 / 2 / 10.0% |
| MKM | 81 / 3 / 3.7% | 100 / 1 / 1.0% | 70 / 1 / 1.4% | 20 / 0 / 0.0% |
| LCI | 108 / 3 / 2.8% | 92 / 3 / 3.3% | 64 / 2 / 3.1% | 22 / 3 / 13.6% |

### Cross-Set Averages by Rarity

| Rarity | Avg Total | Avg Reprints | Avg Reprint % |
|--------|----------|-------------|--------------|
| Common | 90.4 | 3.6 | 4.0% |
| Uncommon | 98.4 | 1.2 | 1.3% |
| Rare | 62.8 | 2.0 | 3.2% |
| Mythic | 20.4 | 1.0 | 4.7% |
| **Overall** | **272.0** | **7.8** | **2.8%** |

---

## 2. Do Reprints Concentrate at Common?

**Partially — commons have the most reprints by raw count but NOT the highest percentage.**

- **Common** leads in raw count: 18 of 39 total reprints (46.2%) are at common, which makes sense given commons are the largest rarity pool.
- By percentage, common (4.0%) is middle of the pack — mythic actually has the highest reprint percentage (4.7%), though this is driven by OTJ (2 mythic reprints) and LCI (3 mythic reprints).
- **Uncommon has the lowest reprint rate** at 1.3% — uncommons are almost always new designs, likely because the signpost uncommons and build-around uncommons are set-specific.
- **Rare reprints** are highly variable: OTJ had 5 rare reprints (8.3%) due to the Kaladesh fastland cycle, while BLB/MKM had only 1 each.

**Key insight**: Reprints serve different purposes at different rarities:
- **Common reprints**: functional staples (Murder, Shock, combat tricks) — the "glue" cards every Limited format needs.
- **Rare reprints**: mana fixing cycles (fastlands, fetchlands) and format staples reprinted for accessibility.
- **Mythic reprints**: fan-favorite splashy creatures reprinted for flavor/nostalgia (Gishath, Resplendent Angel, Archangel of Tithes).
- **Uncommon reprints**: rare and opportunistic — mostly efficient removal or card selection that happens to fit the set theme.

---

## 3. Functional Role Analysis

### Every Reprint Across All 5 Sets

#### DSK (Duskmourn) — 6 reprints
| Card | Rarity | Color | Role |
|------|--------|-------|------|
| Murder | Common | B | Removal (hard kill) |
| Scorching Dragonfire | Common | R | Removal (damage) |
| Terramorphic Expanse | Common | - | Mana fixing |
| Ethereal Armor | Uncommon | W | Aura (enchantment synergy) |
| Pyroclasm | Uncommon | R | Removal (sweeper) |
| Leyline of the Void | Rare | B | Constructed sideboard card |

#### BLB (Bloomburrow) — 5 reprints
| Card | Rarity | Color | Role |
|------|--------|-------|------|
| Banishing Light | Common | W | Removal (exile) |
| Run Away Together | Common | U | Removal (bounce) |
| Shore Up | Common | U | Combat trick (protection) |
| Uncharted Haven | Common | - | Mana fixing |
| Fabled Passage | Rare | - | Mana fixing (premium) |

#### OTJ (Outlaws of Thunder Junction) — 12 reprints
| Card | Rarity | Color | Role |
|------|--------|-------|------|
| Corrupted Conviction | Common | B | Card draw (sac outlet) |
| Fake Your Own Death | Common | B | Combat trick (protection) |
| Skulduggery | Common | B | Combat trick |
| Snakeskin Veil | Common | G | Combat trick (protection) |
| Take Up the Shield | Common | W | Combat trick (protection) |
| Blooming Marsh | Rare | - | Mana fixing (fastland) |
| Botanical Sanctum | Rare | - | Mana fixing (fastland) |
| Concealed Courtyard | Rare | - | Mana fixing (fastland) |
| Inspiring Vantage | Rare | - | Mana fixing (fastland) |
| Spirebluff Canal | Rare | - | Mana fixing (fastland) |
| Archangel of Tithes | Mythic | W | Splashy creature |
| Terror of the Peaks | Mythic | R | Splashy creature |

#### MKM (Murders at Karlov Manor) — 5 reprints
| Card | Rarity | Color | Role |
|------|--------|-------|------|
| Murder | Common | B | Removal (hard kill) |
| Shock | Common | R | Removal (damage) |
| Magnifying Glass | Common | - | Mana fixing / card draw |
| Lightning Helix | Uncommon | R/W | Removal (damage + lifegain) |
| Assassin's Trophy | Rare | B/G | Removal (universal) |

#### LCI (Lost Caverns of Ixalan) — 11 reprints
| Card | Rarity | Color | Role |
|------|--------|-------|------|
| Abrade | Common | R | Removal (damage + artifact hate) |
| Dead Weight | Common | B | Removal (debuff aura) |
| Rumbling Rockslide | Common | R | Removal (damage) |
| Chart a Course | Uncommon | U | Card draw |
| Sorcerous Spyglass | Uncommon | - | Utility artifact (hate) |
| Thrashing Brontodon | Uncommon | G | Removal (artifact/enchantment) |
| Growing Rites of Itlimoc | Rare | G | Constructed plant/reprint equity |
| Treasure Map | Rare | - | Card selection / mana |
| Cavern of Souls | Mythic | - | Mana fixing (premium) |
| Gishath, Sun's Avatar | Mythic | RGW | Splashy creature (nostalgia) |
| Resplendent Angel | Mythic | W | Splashy creature |

### Role Summary (All 39 Reprints)

| Role | Count | % of All Reprints |
|------|------:|------------------:|
| **Removal (all types combined)** | **13** | **33.3%** |
| — Removal (damage-based) | 6 | 15.4% |
| — Removal (destroy/exile) | 5 | 12.8% |
| — Removal (bounce) | 1 | 2.6% |
| — Removal (fight/bite) | 1 | 2.6% |
| **Mana fixing/ramp** | **8** | **20.5%** |
| **Combat trick / protection** | **6** | **15.4%** |
| **Splashy creature (nostalgia)** | **3** | **7.7%** |
| **Card draw / selection** | **3** | **7.7%** |
| **Utility enchantment** | **2** | **5.1%** |
| **Utility land** | **1** | **2.6%** |
| **Utility artifact** | **1** | **2.6%** |
| **Constructed sideboard/plant** | **2** | **5.1%** |

### Key Findings on Role Patterns

1. **Removal dominates**: 33.3% of all reprints are removal spells. This makes sense — every set needs Murder/Shock-tier common removal, and proven removal spells are safe reprints.

2. **Mana fixing is the #2 role**: 20.5% of reprints are lands or mana sources. At rare, mana fixing dominates entirely (5 of 10 rare reprints = fastlands in OTJ). At common, Terramorphic Expanse and Uncharted Haven provide budget fixing.

3. **Combat tricks / protection spells are the #3 role**: 15.4% of reprints are combat tricks. These are almost exclusively at common (Snakeskin Veil, Shore Up, Fake Your Own Death, Take Up the Shield). They serve as known-quantity Limited filler.

4. **Mythic reprints are fan favorites**: All 5 mythic reprints are either splashy creatures (Gishath, Archangel of Tithes, Resplendent Angel, Terror of the Peaks) or premium mana fixing (Cavern of Souls). These drive pack sales.

5. **Card draw reprints are uncommon**: Only 3 reprints (7.7%) serve the card draw/selection role. Sets tend to create new card-draw designs.

---

## 4. Reprint Targets for ASD

### Scaling from Reference Data

| Metric | 5-Set Average | 60-Card Dev Set (scaled) | 280-Card Full Set (scaled) |
|--------|--------------|-------------------------|---------------------------|
| Total reprints | 7.8 / 272 = 2.8% | **1-2 cards** | **7-8 cards** |
| Common reprints | 3.6 / 90.4 = 4.0% | ~1 | 3-4 |
| Uncommon reprints | 1.2 / 98.4 = 1.3% | 0 | 1 |
| Rare reprints | 2.0 / 62.8 = 3.2% | 0-1 | 2 |
| Mythic reprints | 1.0 / 20.4 = 4.7% | 0 | 1 |

**For the 60-card dev set**: 1-2 reprints is appropriate. Both should be at common. Given the dev set's purpose (testing the pipeline), reprints also serve as a useful control — we know exactly what a correctly-designed card looks like.

**For the 280-card full set**: 7-8 reprints total, distributed as:
- 3-4 common (removal + mana fixing + combat trick)
- 1 uncommon (removal or card selection)
- 2 rare (mana fixing cycle or format staples)
- 1 mythic (splashy nostalgia creature or premium land)

### Recommended Reprint Roles for ASD

Based on the role patterns above and ASD's specific mechanics (Salvage, Malfunction, Overclock — artifact-heavy themes), here are the best candidate roles for reprints:

#### Priority 1 — Common Reprints (high confidence)

| Role | Why | Example Candidates |
|------|-----|-------------------|
| **Black removal (hard kill)** | Murder appeared in 2 of 5 sets. Every Limited format needs unconditional creature removal in black. | Murder, Go for the Throat, Hero's Downfall |
| **Red removal (damage)** | Shock/Abrade/Scorching Dragonfire appeared in 4 of 5 sets. Red always needs efficient burn. ASD's artifact theme makes Abrade especially good. | Abrade (perfect — hits both creatures and artifacts), Shock, Lightning Strike |
| **Mana fixing land** | Terramorphic Expanse / Uncharted Haven appeared in 2 of 5 sets. Budget common fixing is essential for Limited. | Terramorphic Expanse, Evolving Wilds, Shimmering Grotto |

#### Priority 2 — Uncommon/Rare Reprints (moderate confidence)

| Role | Why | Example Candidates |
|------|-----|-------------------|
| **White removal (exile)** | Banishing Light appeared in BLB. Clean, flexible removal that is format-agnostic. | Banishing Light, Oblivion Ring |
| **Artifact/enchantment hate** | With ASD's artifact-heavy themes (Malfunction, Overclock), naturalize effects are important. Thrashing Brontodon was reprinted in LCI. | Thrashing Brontodon, Reclamation Sage, Naturalize |
| **Card draw (blue)** | Chart a Course appeared in LCI. Efficient card selection helps blue decks function. | Chart a Course, Opt, Impulse |

#### Priority 3 — Rare/Mythic Reprints (full set only)

| Role | Why | Example Candidates |
|------|-----|-------------------|
| **Rare dual lands** | OTJ reprinted an entire fastland cycle. Rare duals drive pack value and improve constructed. | Fastlands, painlands, or checklands matching ASD's color pairs |
| **Artifact synergy mythic** | ASD's heavy artifact theme could benefit from a known artifact-matters mythic. | Wurmcoil Engine, Hangarback Walker, or similar |

#### ASD-Specific Considerations

1. **Abrade is the ideal common reprint for ASD**: It's removal AND artifact hate in one card, directly supporting the set's artifact themes. It was reprinted in LCI which also had artifact themes.

2. **Avoid reprinting cards that use ASD's named mechanics**: Reprints should be mechanically generic. No card with Salvage, Malfunction, or Overclock should be a reprint (obviously — these are new mechanics).

3. **Mana fixing reprints help the 3-color Overclock archetype**: Overclock spans U/R/B, which needs good mana. A common fixing land reprint eases that pressure.

4. **Combat tricks are safe but low-priority for the dev set**: The dev set is small enough that we can fill combat trick slots with new designs. Save trick reprints for the full set where you need more filler.

---

## 5. Dev Set Recommendation (60 cards)

For the 60-card dev set, add **2 common reprints**:

1. **Murder** (B, Common, Instant) — "Destroy target creature." Unconditional black removal. Appeared in DSK and MKM. Clean, simple, proven.

2. **Abrade** (1R, Common, Instant) — "Choose one: Abrade deals 3 damage to target creature / Destroy target artifact." Perfect for ASD's artifact-heavy environment. Appeared in LCI.

These two reprints:
- Cover the two most common reprint roles (hard removal, damage-based removal)
- Provide essential Limited infrastructure (every format needs common removal)
- Serve as pipeline validation — known-good card designs that we can compare against our generated cards
- Are thematically neutral enough to fit any setting

---

## 6. Full Set Recommendation (280 cards)

For the 280-card full set, target **8 reprints** (2.9%, in line with the 2.8% average):

| Slot | Rarity | Role | Candidate |
|------|--------|------|-----------|
| 1 | Common | Black hard removal | Murder |
| 2 | Common | Red damage removal + artifact hate | Abrade |
| 3 | Common | Mana fixing land | Terramorphic Expanse or Evolving Wilds |
| 4 | Common | Blue card draw or combat trick | Opt, Shore Up, or similar |
| 5 | Uncommon | Artifact/enchantment removal | Thrashing Brontodon or Reclamation Sage |
| 6 | Rare | Dual land (pair TBD) | Fastland or painland |
| 7 | Rare | Dual land (pair TBD) | Fastland or painland |
| 8 | Mythic | Artifact-synergy creature or premium land | TBD based on final set design |

---

## Appendix: Raw Reprint Data

### Color Distribution of Reprints (All 39)

| Color | Count | % |
|-------|------:|--:|
| Colorless | 13 | 33.3% |
| Black | 7 | 17.9% |
| Red | 6 | 15.4% |
| White | 5 | 12.8% |
| Blue | 3 | 7.7% |
| Multicolor | 3 | 7.7% |
| Green | 2 | 5.1% |

Colorless dominates because mana-fixing lands (which have no color) are the most common reprint category. Among colored reprints, black and red lead — consistent with their roles as the primary removal colors.

### Set-by-Set Reprint Rate Variance

- **Low reprint sets** (1.8-2.2%): MKM, BLB, DSK — these sets had strong mechanical identities that left little room for generic reprints.
- **High reprint sets** (3.8-4.4%): OTJ, LCI — OTJ reprinted a 5-card rare land cycle, and LCI had returning Ixalan-block cards for nostalgia/tribal support.
- **Takeaway**: Reprint rate is partially driven by whether the set has a land cycle reprint (adds 5 cards instantly) and whether it's a "return" set with nostalgia reprints.
