# Human Review Findings — Mechanic Test Cards

Date: 2026-03-09
Reviewer: Human + Opus (interactive session)
Input: `test-cards-original.json` (15 cards)

## Purpose

This document is the **ground truth** for evaluating an automated AI review pass.
An automated reviewer should be run on `test-cards-original.json` and its findings
compared against this document to measure detection accuracy.

---

## Set-Level Issues

### S1: Keyword Name Collision — "Scavenge" (RESOLVED)
- **Severity**: HIGH (resolved)
- **Cards affected**: All 5 salvage cards (1-5)
- **Issue**: "Scavenge" is an existing MTG keyword from Return to Ravnica (2012) that exiles creatures from graveyards to put +1/+1 counters on targets. Our mechanic does something completely different (dig through top cards for artifacts). Same type of conflict previously caught with Overload → Overclock.
- **Fix**: Renamed the mechanic to "Salvage" to avoid collision with the existing MTG keyword.

---

## Per-Card Issues

### Card 1: Denethix Salvage Crew
- **Issues**: None (set-level Scavenge naming issue now resolved -- renamed to Salvage)
- **Status**: PASS

### Card 2: Undergrowth Scrounger
- **Issues**:
  - TEMPLATING: Missing salvage reminder text
- **Status**: FAIL

### Card 3: Protonium Archaeologist
- **Issues**:
  - TEMPLATING: Missing salvage reminder text
- **Status**: FAIL

### Card 4: Moktar Relic Hunter
- **Issues**:
  - TEMPLATING: Missing salvage reminder text
- **Status**: FAIL

### Card 5: Subsurface Expedition Leader
- **Issues**:
  - TEMPLATING: Missing salvage reminder text (both ETB and activated ability)
  - TEMPLATING: Inconsistent capitalization — "salvage 6" (lowercase) vs "Salvage 3" (uppercase) on the same card
- **Status**: FAIL

### Card 6: Defective Labor Drone
- **Issues**: None
- **Status**: PASS

### Card 7: Unstable Welding Unit
- **Issues**:
  - DESIGN: Haste is a dead keyword. Malfunction 1 causes the creature to enter tapped, and the counter isn't removed until the next upkeep. By that point, summoning sickness has already worn off, so haste provides zero benefit. The keyword is fully negated by the malfunction mechanic.
- **Fix**: Remove haste, or replace with a keyword that matters while tapped (e.g., first strike, menace, trample — abilities relevant when attacking after the delay).
- **Status**: FAIL

### Card 8: Salvage Processing Matrix
- **Issues**:
  - DESIGN: "Enters tapped" from malfunction is mechanically irrelevant on a noncreature artifact with no tap abilities. The tapped/untapped status of this permanent never matters. Only the malfunction counters + removal trigger provide actual gameplay.
- **Note**: This is partially a mechanic-level issue (malfunction's "enters tapped" clause doesn't generalize well to all permanent types). Could be addressed by adding "can't activate abilities while it has malfunction counters" to the mechanic definition, or accepted as harmless flavor.
- **Status**: WARN

### Card 9: Rampaging Siege Engine
- **Issues**: None
- **Status**: PASS

### Card 10: Experimental Thought Engine
- **Issues**: None (strong but fair at rare)
- **Status**: PASS

### Card 11: Synaptic Overload
- **Issues**:
  - DESIGN: Redundant conditional. Overclock is a mandatory additional cost, so "if you overclocked this turn" is always true when this spell resolves. The conditional is meaningless — the card always counters + draws.
  - BALANCE: Once the redundant conditional is removed, the card is a {1}{U} hard counterspell that draws a card AND gives 3 cards of impulse draw. This is wildly above rate. Compare: Counterspell ({U}{U}) has no upside and is already considered too strong for Standard.
  - DESIGN: Kitchen sink — counter + draw + overclock is three unrelated effects piled together.
- **Fix**: Redesign as {1}{U}{U} (Cancel rate), remove overclock as additional cost, keep conditional: "Counter target spell. If you overclocked this turn, draw a card." Now it's a clean archetype payoff that requires external overclock setup.
- **Status**: FAIL

### Card 12: Jury-Rigged Berserker
- **Issues**:
  - TEMPLATING: Missing overclock reminder text
- **Note**: Design is actually good — conditional requires external overclock (unlike Synaptic Overload). This is how overclock payoff cards should work.
- **Status**: FAIL (templating only)

### Card 13: Vivisector Prime
- **Issues**: None
- **Status**: PASS

### Card 14: Cascade Protocol
- **Issues**:
  - DESIGN: False variability. "Deals 2 damage for each card exiled with ~ this way" — overclock always exiles exactly 3 cards, double overclock always exiles 6, so the damage is always 12. The variable wording implies the count could change, but it can't.
  - BALANCE: 12 damage for 5 mana is wildly above rate. Comparable: Lava Axe = 5 damage for 5 mana (player only). This does 2.4x the damage and hits any target, plus gives 6 cards of impulse draw.
  - DESIGN: Kitchen sink — double overclock + variable damage calculation + impulse draw is overloaded.
- **Fix**: Redesign as {1}{R} sorcery: "~ deals 2 damage to any target, plus 1 for each time you've overclocked this turn." Simple archetype payoff, scales with external setup, no kitchen sink. Possibly uncommon.
- **Status**: FAIL

### Card 15: Archscientist Vex, the Unbound
- **Issues**:
  - DESIGN: Flying feels tacked on / unrelated to overclock identity. Could be replaced with a thematic ability (prowess, scry on overclock, etc.)
  - BALANCE: Cost reduction + copying is extremely powerful together, but requires external overclock sources and she's mythic. On the line — acceptable for a mythic build-around.
- **Note**: User decided to keep this card largely as-is. The flying concern is minor polish. The power level is intentionally high for mythic.
- **Status**: WARN

---

## Summary

| Status | Count | Cards |
|--------|-------|-------|
| PASS   | 5     | 1, 6, 9, 10, 13 |
| WARN   | 2     | 8, 15 |
| FAIL   | 8     | 2, 3, 4, 5, 7, 11, 12, 14 |

### Issue Categories Found
1. **Keyword name collision** (set-level) — 1 instance
2. **Missing reminder text** (templating) — 5 cards
3. **Inconsistent capitalization** (templating) — 1 card
4. **Keyword negated by other abilities** (design) — 1 card
5. **Mechanic irrelevant on card type** (design) — 1 card
6. **Redundant conditional** (design) — 1 card
7. **Kitchen sink / too many effects** (design) — 2 cards
8. **False variability** (design) — 1 card
9. **Above-rate balance** (balance) — 2 cards

### Automated Reviewer Scoring Guide
An automated reviewer run on `test-cards-original.json` should be scored against these findings:
- **True Positive**: Reviewer flags an issue listed above
- **False Negative**: Reviewer misses an issue listed above
- **False Positive**: Reviewer flags something not listed (evaluate if it's a legitimate new finding or noise)
- **Target**: ≥70% true positive rate on FAIL cards, ≥50% on WARN cards
