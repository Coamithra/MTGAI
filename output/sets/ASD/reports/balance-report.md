# Balance Analysis Report: ASD

**Cards**: 66 | **Skeleton slots**: 60 | **PASS**: 49 | **WARN**: 25 | **FAIL**: 0

## Skeleton Conformance

**49/60** slots matched perfectly.

| Slot | Card | Issues |
|------|------|--------|
| W-C-04 | Salvage the Gatehouse | [WARN] Complexity tier mismatch: slot expects complex, card classified as evergreen |
| U-C-04 | Excavate the Archives | [WARN] Complexity tier mismatch: slot expects complex, card classified as evergreen |
| G-C-01 | Elvish Mystic | [WARN] CMC off by 1: slot targets 2, card is 1; [WARN] Complexity tier mismatch: slot expects vanilla, card classified as french_vanilla |
| X-C-01 | Corroded Exo-Frame | [WARN] Complexity tier mismatch: slot expects vanilla, card classified as evergreen |
| W-U-02 | Fist Supply Marshal | [WARN] Complexity tier mismatch: slot expects evergreen, card classified as complex |
| U-U-01 | Cult Initiate | [WARN] Complexity tier mismatch: slot expects evergreen, card classified as complex |
| B-U-02 | Luminous Spark Extractor | [WARN] Complexity tier mismatch: slot expects evergreen, card classified as complex |
| R-U-01 | Spark Saboteur | [WARN] Complexity tier mismatch: slot expects evergreen, card classified as complex |
| R-U-02 | Moktar War-Screamer | [WARN] Complexity tier mismatch: slot expects evergreen, card classified as complex |
| WU-U-01 | Relic Warden Automaton | [WARN] Complexity tier mismatch: slot expects complex, card classified as evergreen |
| WG-U-01 | Frontier Homesteader | [WARN] Complexity tier mismatch: slot expects complex, card classified as evergreen |

## Color Coverage

### W
Cards: 19 | Creatures: 15 | Removal: 2 | Card Advantage: 10

**Creature CMC curve:**

| CMC | Count |
|-----|-------|
| 1 | 3 |
| 2 | 7 |
| 3 | 4 |
| 5 | 1 |

**CMC gaps:** 4, 6

**Size distribution:**
- beefy: 3
- huge: 1
- medium: 9
- small: 2

**Removal:** Sanctioned Exile, The Vizier's Decree

**Card advantage:** Salvage the Gatehouse, Feretha, the Hollow Founder, Cult Relic-Bearer, Fist Supply Marshal, Edict of Continuity, Proclamation Enforcer, Sura, Rendon Ranchmaster, Kethra, Spark Commander, The Custodian Eternal, Relic Warden Automaton

### U
Cards: 14 | Creatures: 10 | Removal: 1 | Card Advantage: 11

**Creature CMC curve:**

| CMC | Count |
|-----|-------|
| 1 | 3 |
| 2 | 3 |
| 3 | 3 |
| 5 | 1 |

**CMC gaps:** 4, 6

**Size distribution:**
- huge: 1
- medium: 7
- small: 2

**Removal:** Redirect Pulse

**Card advantage:** Redirect Pulse, Excavate the Archives, The Head Scientist, Cult Savant, The Cartography Engine, Cult Initiate, Subsurface Cartographer, Automated Sentry Grid, Depth Crawler Archivist, The Custodian Eternal, Relic Warden Automaton

### B
Cards: 13 | Creatures: 9 | Removal: 1 | Card Advantage: 5

**Creature CMC curve:**

| CMC | Count |
|-----|-------|
| 1 | 2 |
| 2 | 3 |
| 3 | 3 |
| 4 | 1 |

**CMC gaps:** 5, 6

**Size distribution:**
- beefy: 1
- huge: 1
- medium: 5
- small: 2

**Removal:** Murder

**Card advantage:** Plunder the Catacombs, Luminous Spark Extractor, Subsurface Harvest, Depth Crawler Archivist, Proclamation Enforcer

### R
Cards: 11 | Creatures: 7 | Removal: 5 | Card Advantage: 3

**Creature CMC curve:**

| CMC | Count |
|-----|-------|
| 2 | 4 |
| 3 | 2 |
| 4 | 1 |

**CMC gaps:** 1, 5, 6

**Size distribution:**
- beefy: 1
- medium: 6

**Removal:** Scorched Passage, Spark Detonator, The Burning Descent, Spark Saboteur, Raider's Bounty

**Card advantage:** Ransack the Storeroom, The Burning Descent, Kethra, Spark Commander

### G
Cards: 11 | Creatures: 7 | Removal: 1 | Card Advantage: 7

**Creature CMC curve:**

| CMC | Count |
|-----|-------|
| 1 | 1 |
| 2 | 3 |
| 3 | 2 |
| 4 | 1 |

**CMC gaps:** 5, 6

**Size distribution:**
- beefy: 2
- huge: 1
- medium: 2
- small: 2

**Removal:** Reclaim the Surface

**Card advantage:** Reclaim the Surface, Spore-Nest Forager, The Subsurface Reclaims, Moktar Salvager, Rendon Packleader, Law of the Wilderness, Sura, Rendon Ranchmaster

### colorless
Cards: 8 | Creatures: 0 | Removal: 0 | Card Advantage: 1

**Card advantage:** Flickering Relay Node

## Mechanic Distribution

| Mechanic | Planned | Actual | Status |
|----------|---------|--------|--------|
| Salvage | 6 | 12 | WARN (+6) |
| Malfunction | 5 | 3 | WARN (-2) |
| Overclock | 3 | 1 | WARN (-2) |

**Salvage** rarity breakdown:
| Rarity | Planned | Actual |
|--------|---------|--------|
| common | 3 | 2 |
| mythic | 0 | 3 |
| rare | 1 | 3 |
| uncommon | 2 | 4 |

**Malfunction** rarity breakdown:
| Rarity | Planned | Actual |
|--------|---------|--------|
| common | 2 | 0 |
| mythic | 0 | 0 |
| rare | 1 | 2 |
| uncommon | 2 | 1 |

**Overclock** rarity breakdown:
| Rarity | Planned | Actual |
|--------|---------|--------|
| common | 0 | 0 |
| mythic | 1 | 0 |
| rare | 0 | 1 |
| uncommon | 2 | 0 |

## Mana Fixing

**4 sources found:**
- Spore-Nest Forager
- Descent Waypoint
- Ransack the Storeroom
- Flickering Relay Node

## Color Balance (mono-color cards)

| Color | Count |
|-------|-------|
| W | 10 |
| U | 10 |
| B | 10 |
| R | 9 |
| G | 9 |

## All Issues

| Severity | Check | Message |
|----------|-------|---------|
| WARN | conformance.mechanic_tier | Complexity tier mismatch: slot expects complex, card classified as evergreen |
| WARN | conformance.mechanic_tier | Complexity tier mismatch: slot expects complex, card classified as evergreen |
| WARN | conformance.cmc | CMC off by 1: slot targets 2, card is 1 |
| WARN | conformance.mechanic_tier | Complexity tier mismatch: slot expects vanilla, card classified as french_vanilla |
| WARN | conformance.mechanic_tier | Complexity tier mismatch: slot expects vanilla, card classified as evergreen |
| WARN | conformance.mechanic_tier | Complexity tier mismatch: slot expects evergreen, card classified as complex |
| WARN | conformance.mechanic_tier | Complexity tier mismatch: slot expects evergreen, card classified as complex |
| WARN | conformance.mechanic_tier | Complexity tier mismatch: slot expects evergreen, card classified as complex |
| WARN | conformance.mechanic_tier | Complexity tier mismatch: slot expects evergreen, card classified as complex |
| WARN | conformance.mechanic_tier | Complexity tier mismatch: slot expects evergreen, card classified as complex |
| WARN | conformance.mechanic_tier | Complexity tier mismatch: slot expects complex, card classified as evergreen |
| WARN | conformance.mechanic_tier | Complexity tier mismatch: slot expects complex, card classified as evergreen |
| WARN | coverage.cmc_gap | W has no creature at CMC 4 |
| WARN | coverage.cmc_gap | W has no creature at CMC 6 |
| WARN | coverage.cmc_gap | U has no creature at CMC 4 |
| WARN | coverage.cmc_gap | U has no creature at CMC 6 |
| WARN | coverage.cmc_gap | B has no creature at CMC 5 |
| WARN | coverage.cmc_gap | B has no creature at CMC 6 |
| WARN | coverage.cmc_gap | R has no creature at CMC 1 |
| WARN | coverage.cmc_gap | R has no creature at CMC 5 |
| WARN | coverage.cmc_gap | R has no creature at CMC 6 |
| WARN | coverage.cmc_gap | G has no creature at CMC 5 |
| WARN | coverage.cmc_gap | G has no creature at CMC 6 |
| WARN | coverage.mechanic_under | Malfunction under-represented: planned 5, got 3 |
| WARN | coverage.mechanic_under | Overclock under-represented: planned 3, got 1 |
