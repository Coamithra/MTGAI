# Experiment 2: Few-Shot Example Count — Summary

**Model**: claude-sonnet-4-20250514
**Temperature**: 1.0 (winner from Experiment 1)
**Settings tested**: 2A, 2B, 2C, 2D
**Cards per setting**: 24
**Total cards scored**: 96

**Total API cost**: $0.5306

---

## Average Scores by Few-Shot Count

| Dimension | 2A (0 ex.) | 2B (1 ex.) | 2C (3 ex.) | 2D (5 ex.) |
|-----------||-----------||-----------||-----------||-----------|
| Rules Text Correctness | 5.00 | 4.96 | 5.00 | 4.92 |
| Mana Cost Appropriateness | 4.96 | 4.96 | 4.96 | 4.96 |
| Power Level for Rarity | 5.00 | 5.00 | 4.96 | 5.00 |
| Flavor Text Quality | 4.21 | 4.08 | 4.00 | 4.04 |
| Name Creativity | 3.88 | 3.88 | 3.88 | 3.88 |
| Type Line Correctness | 4.96 | 5.00 | 4.96 | 4.96 |
| Color Pie Compliance | 5.00 | 5.00 | 4.92 | 5.00 |
| **Overall Average** | **4.71** | **4.70** | **4.67** | **4.68** |

## Best Overall Setting: **2A** (avg: 4.71)

## Key Question: Do Few-Shot Examples Improve Rules Text Correctness?

| Setting | Rules Text Correctness | Type Line Correctness | Delta vs 0-shot |
|---------|----------------------|---------------------|-----------------|
| 2A | 5.00 | 4.96 | RTC +0.00 |
| 2B | 4.96 | 5.00 | RTC -0.04 |
| 2C | 5.00 | 4.96 | RTC +0.00 |
| 2D | 4.92 | 4.96 | RTC -0.08 |

## Correctness vs. Creativity

| Metric | 2A (0 ex.) | 2B (1 ex.) | 2C (3 ex.) | 2D (5 ex.) |
|--------|-----------|-----------|-----------|-----------|
| Correctness (avg) | 4.98 | 4.98 | 4.96 | 4.96 |
| Creativity (avg) | 4.04 | 3.98 | 3.94 | 3.96 |
| Power Level | 5.00 | 5.00 | 4.96 | 5.00 |

## Diminishing Returns Analysis

Does adding more examples continue to help, or do we hit diminishing returns?

| Transition | Overall Delta | RTC Delta | Creativity Delta |
|-----------|---------------|-----------|------------------|
| 0 -> 1 | -0.02 | -0.04 | -0.06 |
| 1 -> 3 | -0.03 | +0.04 | -0.04 |
| 3 -> 5 | +0.01 | -0.08 | +0.02 |
| 0 -> 5 | -0.04 | -0.08 | -0.08 |

## Token Cost Comparison

Adding few-shot examples increases input tokens. Is the quality improvement worth the cost increase?

| Setting | Input Tokens | Output Tokens | Total Cost | Cost vs 0-shot |
|---------|-------------|---------------|------------|----------------|
| 2A (0 ex.) | 12,272 | 5,446 | $0.1185 | 1.0x |
| 2B (1 ex.) | 13,567 | 5,843 | $0.1283 | 1.1x |
| 2C (3 ex.) | 15,925 | 5,882 | $0.1360 | 1.1x |
| 2D (5 ex.) | 18,328 | 6,185 | $0.1478 | 1.2x |

## Failure Modes by Setting

### 2A (0 examples)
- **missing_period**: 2 occurrences
- **mythic_creature_not_legendary**: 1 occurrences
- **overstatted_common**: 1 occurrences
- **generic_or_existing_name**: 1 occurrences

### 2B (1 examples)
- **missing_period**: 3 occurrences
- **overstatted_common**: 1 occurrences
- **generic_or_existing_name**: 1 occurrences

### 2C (3 examples)
- **missing_period**: 3 occurrences
- **mythic_creature_not_legendary**: 1 occurrences
- **overstatted_common**: 1 occurrences
- **nwo_violation_common**: 1 occurrences
- **color_pie_violation_draw a card**: 1 occurrences
- **generic_or_existing_name**: 1 occurrences

### 2D (5 examples)
- **missing_period**: 3 occurrences
- **mythic_creature_not_legendary**: 1 occurrences
- **overstatted_common**: 1 occurrences
- **self_reference_uses_name**: 1 occurrences
- **generic_or_existing_name**: 1 occurrences

## Per-Card Scores (All Settings)

| Slot | Setting | Name | RTC | MCA | PLR | FTQ | NC | TLC | CPC | Avg | Failures |
|------|---------|------|-----|-----|-----|-----|-----|-----|-----|-----|----------|
|  1 | 2A | Moorland Sentinel | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  2 | 2A | Radiant Pegasus | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  3 | 2A | Righteous Banishment | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  4 | 2A | Scholarly Insight | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  5 | 2A | Dispel the Weave | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  6 | 2A | Arcane Scrutiny | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  7 | 2A | Fatal Strike | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  8 | 2A | Crypt Harvester | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  9 | 2A | Vorthak, Death's He... | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 | missing_period |
| 10 | 2A | Molten Bolt | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 11 | 2A | Embercharge Raider | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 12 | 2A | Worldfire Ancient | 5 | 5 | 5 | 4 | 4 | 4 | 5 | 4.6 | mythic_creature_not_legendary, missing_period |
| 13 | 2A | Verdant Wayfinding | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 14 | 2A | Ironbark Trampler | 5 | 4 | 5 | 4 | 4 | 5 | 5 | 4.6 | overstatted_common |
| 15 | 2A | Grove Sanctuary | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 16 | 2A | Skyward Arbitrator | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 17 | 2A | Bloodthirst Marauder | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 18 | 2A | Wayfarer's Compass | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 19 | 2A | Temporal Resonance ... | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 20 | 2A | Seraph of Divine Re... | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 21 | 2A | Forge of Inspiration | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 22 | 2A | The Wild Hunt | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 23 | 2A | Prismatic Wellspring | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 24 | 2A | Forest | 5 | 5 | 5 | 4 | 1 | 5 | 5 | 4.3 | generic_or_existing_name |
|  1 | 2B | Temple Guardian | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  2 | 2B | Radiant Pegasus | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  3 | 2B | Divine Judgment | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  4 | 2B | Scholarly Insight | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  5 | 2B | Arcane Disruption | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  6 | 2B | Arcane Revelation | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  7 | 2B | Withering Strike | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  8 | 2B | Graveyard Scavenger | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  9 | 2B | Nethys, Death's Herald | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 10 | 2B | Scorching Blast | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 11 | 2B | Ironwall Raider | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 12 | 2B | Worldburner Tyrant | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 | missing_period |
| 13 | 2B | Wildwood Expedition | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 14 | 2B | Thornback Behemoth | 5 | 4 | 5 | 4 | 4 | 5 | 5 | 4.6 | overstatted_common |
| 15 | 2B | Primal Awakening | 4 | 5 | 5 | 3 | 4 | 5 | 5 | 4.4 | missing_period |
| 16 | 2B | Skyward Justiciar | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 17 | 2B | Bloodpact Ravager | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 18 | 2B | Wayfarer's Compass | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 19 | 2B | Chronarch's Nexus | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 20 | 2B | Seraph of Divine Ju... | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 | missing_period |
| 21 | 2B | Blazing Confluence | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 22 | 2B | Chronicle of the Wi... | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 23 | 2B | Crystalline Cavern | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 24 | 2B | Forest | 5 | 5 | 5 | 4 | 1 | 5 | 5 | 4.3 | generic_or_existing_name |
|  1 | 2C | Vigilant Recruit | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  2 | 2C | Steadfast Guardian | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  3 | 2C | Divine Verdict | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  4 | 2C | Scholarly Insight | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  5 | 2C | Arcane Disruption | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  6 | 2C | Archive of Echoes | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  7 | 2C | Grasp of Decay | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  8 | 2C | Carrion Seeker | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
|  9 | 2C | Vorthak, Death's He... | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 | missing_period |
| 10 | 2C | Searing Strike | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 11 | 2C | Ember Raider | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 12 | 2C | Inferno Sovereign | 5 | 5 | 5 | 4 | 4 | 4 | 5 | 4.6 | mythic_creature_not_legendary |
| 13 | 2C | Verdant Seeking | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 14 | 2C | Ironbark Behemoth | 5 | 4 | 5 | 4 | 4 | 5 | 5 | 4.6 | overstatted_common |
| 15 | 2C | Wild Growth Aura | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 | missing_period |
| 16 | 2C | Skybound Inquisitor | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 17 | 2C | Bloodpyre Ravager | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 18 | 2C | Traveler's Compass | 5 | 5 | 4 | 4 | 4 | 5 | 5 | 4.6 | nwo_violation_common |
| 19 | 2C | Nexus Engine | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 20 | 2C | Seraph of Sacred Sh... | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 | missing_period |
| 21 | 2C | Forge of Possibilities | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 22 | 2C | Chronicle of the Ve... | 5 | 5 | 5 | 3 | 4 | 5 | 3 | 4.3 | color_pie_violation_draw a card |
| 23 | 2C | Crystal Caverns | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 24 | 2C | Forest | 5 | 5 | 5 | 4 | 1 | 5 | 5 | 4.3 | generic_or_existing_name |
|  1 | 2D | Steadfast Guardian | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  2 | 2D | Skyward Sentinel | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  3 | 2D | Divine Judgment | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  4 | 2D | Scholarly Insight | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  5 | 2D | Dispel Thoughts | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
|  6 | 2D | Arcane Deliberation | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  7 | 2D | Shadow Strike | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
|  8 | 2D | Gravebound Harvester | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
|  9 | 2D | Malachar, Death's S... | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 | missing_period |
| 10 | 2D | Volcanic Burst | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 11 | 2D | Goblin Sprinter | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 4.9 |  |
| 12 | 2D | Pyroclasm Dragon | 5 | 5 | 5 | 4 | 4 | 4 | 5 | 4.6 | mythic_creature_not_legendary, missing_period |
| 13 | 2D | Nature's Guidance | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 14 | 2D | Ironbark Behemoth | 5 | 4 | 5 | 4 | 4 | 5 | 5 | 4.6 | overstatted_common |
| 15 | 2D | Verdant Overgrowth | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 16 | 2D | Sky Marshal Advisor | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 17 | 2D | Bloodpyre Assassin | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 18 | 2D | Wayfarer's Compass | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 19 | 2D | Temporal Orrery | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 20 | 2D | Seraph of Divine Ju... | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 | missing_period |
| 21 | 2D | Flames of Versatility | 3 | 5 | 5 | 5 | 4 | 5 | 5 | 4.6 | self_reference_uses_name |
| 22 | 2D | Chronicle of the Wi... | 5 | 5 | 5 | 3 | 4 | 5 | 5 | 4.6 |  |
| 23 | 2D | Resonant Caverns | 5 | 5 | 5 | 4 | 4 | 5 | 5 | 4.7 |  |
| 24 | 2D | Forest | 5 | 5 | 5 | 4 | 1 | 5 | 5 | 4.3 | generic_or_existing_name |

## Recommendation

- **Best setting for correctness**: 2A (avg correctness: 4.98)
- **Best setting for creativity**: 2A (avg creativity: 4.04)
- **Best overall setting**: 2A (overall avg: 4.71)

### Diminishing Returns Verdict

The jump from 3 to 5 examples shows significant diminishing returns compared to 0 to 3 examples. **3 examples is the sweet spot** for cost-effectiveness.

### Cost Impact

- 0-shot baseline cost: $0.1185 for 24 cards
- 3 examples cost: $0.1360 (1.1x baseline)
- 5 examples cost: $0.1478 (1.2x baseline)
- For a full 280-card set, the cost difference would be approximately $0.20 more with 3 examples vs 0-shot.

### Final Recommendation for Production Use

**Recommended few-shot count for Phase 1C**: **0 examples** (Setting 2A)

Use the matching strategy: pick examples by rarity, color, and type to maximize relevance to the cards being generated.

**Total API cost for this experiment**: $0.5306