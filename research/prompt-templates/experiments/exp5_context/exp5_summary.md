# Experiment 5: Context Strategy — Summary

**Model**: claude-sonnet-4-20250514
**Temperature**: 1.0
**Few-shot count**: 0 (zero-shot, exp2 winner)
**Initial cards**: 10
**Test cards per strategy**: 14
**Total scored**: 56

**Total API cost**: $0.3031


---

## Quality Scores by Strategy

| Dimension | none | names_only | compressed | full_color |
|-----------|------|------|------|------|
| Rules Text Correctness | 5.00 | 5.00 | 4.93 | 4.93 |
| Mana Cost Appropriateness | 4.93 | 5.00 | 4.93 | 5.00 |
| Power Level For Rarity | 5.00 | 5.00 | 5.00 | 5.00 |
| Flavor Text Quality | 3.86 | 3.86 | 3.86 | 4.00 |
| Name Creativity | 3.79 | 3.79 | 3.79 | 3.79 |
| Type Line Correctness | 4.93 | 5.00 | 4.93 | 4.93 |
| Color Pie Compliance | 5.00 | 5.00 | 5.00 | 5.00 |
| **Overall Average** | **4.64** | **4.66** | **4.63** | **4.66** |

## Best Quality Strategy: **names_only** (avg: 4.66)

## Duplicate & Similarity Analysis

| Strategy | Name Dupes | Similar Effects | Total Issues |
|----------|-----------|-----------------|-------------|
| none | 0 | 2 | 2 |
| names_only | 0 | 6 | 6 |
| compressed | 0 | 1 | 1 |
| full_color | 0 | 4 | 4 |

### none
- Similar: 'Worldfire Ancient' ~ 'Molten Bolt' (86% word overlap)
- Similar: 'Forge of Inspiration' ~ 'Molten Bolt' (86% word overlap)

### names_only
- Similar: 'Bloodpact Tormentor' ~ 'Molten Bolt' (100% word overlap)
- Similar: 'Prismatic Engine' ~ 'Scholarly Insight' (67% word overlap)
- Similar: 'Seraph of Divine Wrath' ~ 'Vorthak, Death's Herald' (67% word overlap)
- Similar: 'Blazing Confluence' ~ 'Molten Bolt' (100% word overlap)
- Similar: 'The Verdant Awakening' ~ 'Scholarly Insight' (67% word overlap)
- Similar: 'Crystalized Cavern' ~ 'Scholarly Insight' (67% word overlap)

### compressed
- Similar: 'Blazing Ultimatum' ~ 'Molten Bolt' (86% word overlap)

### full_color
- Similar: 'Bloodpact Ravager' ~ 'Molten Bolt' (86% word overlap)
- Similar: 'Chronarch's Observatory' ~ 'Scholarly Insight' (67% word overlap)
- Similar: 'Seraphine, Divine Arbiter' ~ 'Righteous Banishment' (67% word overlap)
- Similar: 'Pyroclastic Eruption' ~ 'Molten Bolt' (71% word overlap)

## Token Usage

| Strategy | Avg Input Tokens | Total Cost |
|----------|-----------------|------------|
| none | 2450 | $0.0726 |
| names_only | 2530 | $0.0748 |
| compressed | 2812 | $0.0747 |
| full_color | 3232 | $0.0810 |

## Recommendation

- **Best quality**: names_only (avg: 4.66)
- **Fewest duplicates**: compressed
- **Recommended for Phase 1C**: Use **compressed** context (names + mana costs + summaries) for best balance of duplicate avoidance vs token cost. Fall back to names_only if context window is tight.

**Total API cost**: $0.3031