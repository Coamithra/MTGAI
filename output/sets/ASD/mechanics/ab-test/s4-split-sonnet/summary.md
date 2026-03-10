# Strategy: s4-split-sonnet

## Description

Three separate review passes (templating, mechanics, balance) followed by a single revision call combining all feedback. Four API calls per card. Using Sonnet.

## Quick Results

- OK: 1 cards
- REVISED: 6 cards

## Results

| Card | Verdict | Issues Found | Changed | Cost |
|------|---------|-------------|---------|------|
| 2. Undergrowth Scrounger | REVISED | Missing reminder text for salvage ability | Yes | $0.0281 |
| 5. Subsurface Expedition Leader | REVISED | Missing reminder text for salvage mechanic; Salvage scaling at minimum threshold (consider 7+ for rare impact); Color... | Yes | $0.0317 |
| 6. Defective Labor Drone | OK | None | No | $0.0296 |
| 7. Unstable Welding Unit | REVISED | Missing reminder text for Haste at common rarity; Keyword nonbo between Malfunction (enters tapped) and haste (irrele... | Yes | $0.0316 |
| 11. Synaptic Overload | REVISED | Incorrect overclock templating with redundant reminder text; Missing period after reminder text; Flavor text encoding... | Yes | $0.0336 |
| 14. Cascade Protocol | REVISED | Incomplete reminder text - should clarify that overclock happens twice; Pronoun reference issue with spell name in da... | Yes | $0.0366 |
| 15. Archscientist Vex, the Unbound | REVISED | Missing reminder text for first use of overclock; Inconsistent capitalization of overclock; Incorrect reminder text f... | Yes | $0.0351 |

## Total Cost

- API calls: 28
- Total tokens: 27407 in / 9602 out
- Total cost: $0.2263

## Human Evaluation

- **Card 02**: Good.
- **Card 05**: Good.
- **Card 06**: Good. (Correctly left unchanged.)
- **Card 07**: "When Unstable Welding Unit has no malfunction counters on it, it gains haste." Sees the vision but this doesn't do anything outside real fringe scenarios. Bad.
- **Card 11**: Got CHEAPER somehow. Absolute fail. Disqualifyingly bad.
- **Card 14**: Very good fix! Outlier in quality.
- **Card 15**: Also some good fixes — limiting to 1st card, reducing the reduction but keeping copy, removing flying.

**Verdict: PROMISING BUT FLAWED.** Splitting massively improves results vs other Sonnet strategies. Card 06 regression passed, Card 14 and 15 fixes are genuinely good. But Card 11 is a disqualifying outlier (counterspell for {U}). Possibly salvageable if a final sanity-check pass is added — a light review that only flags cards with flagrant problems then throws them back into the review system.