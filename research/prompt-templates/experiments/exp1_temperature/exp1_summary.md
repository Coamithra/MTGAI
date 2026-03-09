# Experiment 1: Temperature Sweep — Summary

**Model**: claude-sonnet-4-20250514

**Temperatures tested**: [0.3, 0.5, 0.7, 1.0]

**Cards per temperature**: 24

**Total cards scored**: 96

**Total API cost**: $0.4829


---

## Average Scores by Temperature

| Dimension | T=0.3 | T=0.5 | T=0.7 | T=1.0 |
|-----------|-------|-------|-------|-------|
| Rules Text Correctness | 5.00 | 5.00 | 4.96 | 5.00 |
| Mana Cost Appropriateness | 4.96 | 5.00 | 4.96 | 4.96 |
| Power Level For Rarity | 5.00 | 5.00 | 5.00 | 5.00 |
| Flavor Text Quality | 4.21 | 4.12 | 4.21 | 4.21 |
| Name Creativity | 3.88 | 3.88 | 3.75 | 3.88 |
| Type Line Correctness | 4.96 | 4.96 | 5.00 | 4.96 |
| Color Pie Compliance | 4.92 | 4.92 | 4.92 | 5.00 |
| **Overall Average** | **4.70** | **4.70** | **4.68** | **4.71** |


## Best Overall Temperature: **1.0** (avg: 4.71)

## Correctness vs. Creativity

| Metric | T=0.3 | T=0.5 | T=0.7 | T=1.0 |
|--------|-------|-------|-------|-------|
| Correctness (avg) | 4.96 | 4.97 | 4.96 | 4.98 |
| Creativity (avg) | 4.04 | 4.00 | 3.98 | 4.04 |
| Power Level | 5.00 | 5.00 | 5.00 | 5.00 |

## Failure Modes by Temperature

### Temperature 0.3
- **missing_period**: 3 occurrences
- **mythic_creature_not_legendary**: 1 occurrences
- **overstatted_common**: 1 occurrences
- **color_pie_violation_draw a card**: 1 occurrences
- **generic_or_existing_name**: 1 occurrences

### Temperature 0.5
- **missing_period**: 2 occurrences
- **mythic_creature_not_legendary**: 1 occurrences
- **color_pie_violation_draw a card**: 1 occurrences
- **generic_or_existing_name**: 1 occurrences

### Temperature 0.7
- **missing_period**: 3 occurrences
- **generic_or_existing_name**: 2 occurrences
- **overstatted_common**: 1 occurrences
- **color_pie_violation_draw a card**: 1 occurrences
- **old_etb_wording**: 1 occurrences

### Temperature 1.0
- **missing_period**: 2 occurrences
- **mythic_creature_not_legendary**: 1 occurrences
- **overstatted_common**: 1 occurrences
- **generic_or_existing_name**: 1 occurrences

## Per-Card Scores (All Temperatures)

| Slot | Temp | Name | RTC | MCA | PLR | FTQ | NC | TLC | CPC | Avg | Failures |
|------|------|------|-----|-----|-----|-----|-----|-----|-----|-----|----------|
|  1 | 0.3 | Steadfast Sentinel | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  2 | 0.3 | Dawnlight Pegasus | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  3 | 0.3 | Righteous Banishment | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  4 | 0.3 | Scholarly Insight | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  5 | 0.3 | Arcane Disruption | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  6 | 0.3 | Arcane Confluence | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  7 | 0.3 | Withering Strike | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  8 | 0.3 | Graveyard Harvester | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  9 | 0.3 | Vorthak, Death's Herald | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 | missing_period |
| 10 | 0.3 | Scorching Bolt | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 11 | 0.3 | Ember Raider | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 12 | 0.3 | Worldforge Dragon | 5 | 5 | 5 | 4 | 4 | 4 | 5 | 4.6 | mythic_creature_not_legendary, missing_period |
| 13 | 0.3 | Verdant Expedition | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 14 | 0.3 | Ironbark Behemoth | 5 | 4 | 5 | 4 | 4 | 5 | 5 | 4.6 | overstatted_common |
| 15 | 0.3 | Primal Awakening | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 16 | 0.3 | Skywatch Arbiter | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 17 | 0.3 | Bloodpact Ravager | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 18 | 0.3 | Wayfarer's Compass | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 19 | 0.3 | Chronarch Engine | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 20 | 0.3 | Seraph of Final Judgment | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 | missing_period |
| 21 | 0.3 | Forge of Possibilities | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 22 | 0.3 | The Verdant Awakening | 5 | 5 | 5 | 3 | 4 | 5 | 3 | 4.3 | color_pie_violation_draw a card |
| 23 | 0.3 | Crystalline Caverns | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 24 | 0.3 | Forest | 5 | 5 | 5 | 4 | 1 | 5 | 5 | 4.3 | generic_or_existing_name |
|  1 | 0.5 | Steadfast Sentinel | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  2 | 0.5 | Dawnwing Protector | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  3 | 0.5 | Divine Banishment | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  4 | 0.5 | Scholarly Insight | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  5 | 0.5 | Arcane Disruption | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  6 | 0.5 | Arcane Revelation | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  7 | 0.5 | Withering Strike | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  8 | 0.5 | Graveyard Scavenger | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  9 | 0.5 | Vorthak, Death's Herald | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 10 | 0.5 | Scorching Bolt | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 11 | 0.5 | Emberforge Warrior | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 12 | 0.5 | Inferno Tyrant | 5 | 5 | 5 | 4 | 4 | 4 | 5 | 4.6 | mythic_creature_not_legendary, missing_period |
| 13 | 0.5 | Verdant Pathfinding | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 14 | 0.5 | Thornback Behemoth | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 15 | 0.5 | Symbiotic Growth | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 16 | 0.5 | Skyward Magistrate | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 17 | 0.5 | Bloodpact Ravager | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 18 | 0.5 | Wayfarer's Compass | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 19 | 0.5 | Chronarch's Apparatus | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 20 | 0.5 | Seraphiel, Divine Arbiter | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 | missing_period |
| 21 | 0.5 | Forge of Fury | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 22 | 0.5 | The Worldtree's Awakening | 5 | 5 | 5 | 3 | 4 | 5 | 3 | 4.3 | color_pie_violation_draw a card |
| 23 | 0.5 | Crystal Caverns | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 24 | 0.5 | Forest | 5 | 5 | 5 | 4 | 1 | 5 | 5 | 4.3 | generic_or_existing_name |
|  1 | 0.7 | Steadfast Sentinel | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  2 | 0.7 | Dawnwing Protector | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  3 | 0.7 | Purifying Light | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  4 | 0.7 | Scholarly Insight | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  5 | 0.7 | Dispel Mastery | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  6 | 0.7 | Arcane Convergence | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  7 | 0.7 | Withering Strike | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  8 | 0.7 | Gravecaller Adept | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  9 | 0.7 | Malachar, Death's Herald | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 | missing_period |
| 10 | 0.7 | Lightning Bolt | 5 | 5 | 5 | 5 | 1 | 5 | 5 | 4.4 | generic_or_existing_name |
| 11 | 0.7 | Emberforge Raider | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 12 | 0.7 | Skyrender, the Inferno... | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 | missing_period |
| 13 | 0.7 | Verdant Exploration | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 14 | 0.7 | Ironbark Trampler | 5 | 4 | 5 | 4 | 4 | 5 | 5 | 4.6 | overstatted_common |
| 15 | 0.7 | Harmony of Growth | 4 | 5 | 5 | 3 | 4 | 5 | 3 | 4.1 | color_pie_violation_draw a card, old_etb_wording |
| 16 | 0.7 | Skywatch Magistrate | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 17 | 0.7 | Torment Sculptor | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 | missing_period |
| 18 | 0.7 | Traveler's Compass | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 19 | 0.7 | Chronarch Engine | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 20 | 0.7 | Seraphim, Divine Judge | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 21 | 0.7 | Forge of Possibilities | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 22 | 0.7 | The Great Migration | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 23 | 0.7 | Crystal Caverns | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 24 | 0.7 | Forest | 5 | 5 | 5 | 4 | 1 | 5 | 5 | 4.3 | generic_or_existing_name |
|  1 | 1.0 | Moorland Sentinel | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  2 | 1.0 | Radiant Pegasus | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  3 | 1.0 | Righteous Banishment | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  4 | 1.0 | Scholarly Insight | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  5 | 1.0 | Dispel the Weave | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  6 | 1.0 | Arcane Scrutiny | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  7 | 1.0 | Fatal Strike | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  8 | 1.0 | Crypt Harvester | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  9 | 1.0 | Vorthak, Death's Herald | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 | missing_period |
| 10 | 1.0 | Molten Bolt | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 11 | 1.0 | Embercharge Raider | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 12 | 1.0 | Worldfire Ancient | 5 | 5 | 5 | 4 | 4 | 4 | 5 | 4.6 | mythic_creature_not_legendary, missing_period |
| 13 | 1.0 | Verdant Wayfinding | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 14 | 1.0 | Ironbark Trampler | 5 | 4 | 5 | 4 | 4 | 5 | 5 | 4.6 | overstatted_common |
| 15 | 1.0 | Grove Sanctuary | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 16 | 1.0 | Skyward Arbitrator | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 17 | 1.0 | Bloodthirst Marauder | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 18 | 1.0 | Wayfarer's Compass | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 19 | 1.0 | Temporal Resonance Engine | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 20 | 1.0 | Seraph of Divine Retri... | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 21 | 1.0 | Forge of Inspiration | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 22 | 1.0 | The Wild Hunt | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 23 | 1.0 | Prismatic Wellspring | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 24 | 1.0 | Forest | 5 | 5 | 5 | 4 | 1 | 5 | 5 | 4.3 | generic_or_existing_name |

## Recommendation

- **Best temperature for correctness**: 1.0 (avg correctness: 4.98)
- **Best temperature for creativity**: 0.3 (avg creativity: 4.04)
- **Best overall temperature**: 1.0 (overall avg: 4.71)

**Recommended temperature for Phase 1C**: **1.0**

This temperature provides the best balance between rules text correctness and creative quality across all 7 scoring dimensions.

**Total API cost for this experiment**: $0.4829