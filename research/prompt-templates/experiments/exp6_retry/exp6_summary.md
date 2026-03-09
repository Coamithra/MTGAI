# Experiment 6: Validation-Retry Loop — Summary

**Model**: claude-sonnet-4-20250514
**Initial temperature**: 1.0
**Retry temperature**: 0.5
**Max retries**: 3
**Cards tested**: 7

---

## Overall Results

- **Convergence rate**: 6/7 (86%) fully fixed within 3 retries
- **Average retries needed**: 0.7
- **Average score improvement**: +0.08
- **Total API cost for retries**: $0.1705

## Per-Card Retry Results

| Slot | Type | Initial Score | Final Score | Initial Failures | Final Failures | Retries | Converged |
|------|------|--------------|-------------|----------------|----------------|---------|-----------|
| 9 | Creature (B) | 4.7 | 4.7 | 0 | 0 | 0 | Yes |
| 12 | Creature (R) | 4.7 | 4.7 | 0 | 0 | 0 | Yes |
| 14 | Creature (G) | 4.6 | 4.7 | 1 | 0 | 1 | Yes |
| 15 | Enchantment (G) | 4.7 | 4.7 | 0 | 0 | 0 | Yes |
| 22 | Enchantment — Saga (G) | 4.7 | 4.7 | 0 | 0 | 0 | Yes |
| 20 | Planeswalker (WB) | 4.7 | 4.7 | 1 | 1 | 3 | No |
| 24 | Basic Land — Forest (-) | 4.3 | 4.7 | 1 | 0 | 1 | Yes |

## Retry Chains

### Slot 9: Creature (B mythic)

- **Attempt 0**: 'Vorthak, Death's Sovereign' — avg=4.7, failures=[]

### Slot 12: Creature (R mythic)

- **Attempt 0**: 'Pyroclast, the World Scorcher' — avg=4.7, failures=[]

### Slot 14: Creature (G common)

- **Attempt 0**: 'Ironbark Behemoth' — avg=4.6, failures=['overstatted_common']
- **Attempt 1**: 'Ironbark Behemoth' — avg=4.7, failures=[]
  - Fixed: ['overstatted_common']

### Slot 15: Enchantment (G uncommon)

- **Attempt 0**: 'Verdant Awakening' — avg=4.7, failures=[]

### Slot 22: Enchantment — Saga (G rare)

- **Attempt 0**: 'Verdant Cycle' — avg=4.7, failures=[]

### Slot 20: Planeswalker (WB mythic)

- **Attempt 0**: 'Seraphim of the Damned' — avg=4.7, failures=['missing_period']
- **Attempt 1**: 'Seraphim of the Damned' — avg=4.7, failures=['missing_period']
- **Attempt 2**: 'Seraphim of the Damned' — avg=4.7, failures=['missing_period']
- **Attempt 3**: 'Seraphim of the Damned' — avg=4.7, failures=['missing_period']

### Slot 24: Basic Land — Forest (- common)

- **Attempt 0**: 'Forest' — avg=4.3, failures=['generic_or_existing_name']
- **Attempt 1**: 'Whisperwood Grove' — avg=4.7, failures=[]
  - Fixed: ['generic_or_existing_name']

## Failure Mode Fix Rates

| Failure Mode | Attempts | Fixed | Fix Rate |
|-------------|----------|-------|----------|
| generic_or_existing_name | 1 | 1 | 100% |
| missing_period | 1 | 0 | 0% |
| overstatted_common | 1 | 1 | 100% |

## Recommendation

Retry loop is **effective** — 6/7 cards converge. Use validation-retry in Phase 1C with max 3 attempts.

**Total API cost**: $0.1705