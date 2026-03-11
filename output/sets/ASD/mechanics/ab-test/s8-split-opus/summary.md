# Strategy: s8-split-opus

## Description

Three separate review passes (templating, mechanics, balance) followed by a single revision call combining all feedback. Four API calls per card. Using Opus 4.6.

## Quick Results

- OK: 1 cards
- REVISED: 6 cards

## Results

| Card | Verdict | Issues Found | Changed | Cost |
|------|---------|-------------|---------|------|
| 2. Undergrowth Scrounger | REVISED | Missing reminder text for salvage keyword. Custom mechanics must include reminder text in parentheses on first use. T... | Yes | $0.0534 |
| 5. Subsurface Expedition Leader | REVISED | Missing reminder text on first use of salvage keyword | Yes | $0.0572 |
| 6. Defective Labor Drone | OK | None | No | $0.0500 |
| 7. Unstable Welding Unit | REVISED | Haste is a keyword nonbo with Malfunction 1: the creature enters tapped, so Haste is dead text on the turn it's cast.... | Yes | $0.0564 |
| 11. Synaptic Overload | REVISED | [; "; O | Yes | $0.0729 |
| 14. Cascade Protocol | REVISED | Fake variability: Overclock always exiles exactly 3, so double overclock always exiles 6, meaning the 'for each card ... | Yes | $0.0743 |
| 15. Archscientist Vex, the Unbound | REVISED | Templating: Overclock reminder text embedded inline in a static ability that doesn't perform overclock — reminder tex... | Yes | $0.0801 |

## Total Cost

- API calls: 28
- Total tokens: 30853 in / 11603 out
- Total cost: $0.4443

## Human Evaluation

| Card | Verdict | Human Assessment |
|------|---------|-----------------|
| 2. Undergrowth Scrounger | REVISED | Fine |
| 5. Subsurface Expedition Leader | REVISED | Fine |
| 6. Defective Labor Drone | OK | Fine |
| 7. Unstable Welding Unit | REVISED | Good — menace, catches the nonbo |
| 11. Synaptic Overload | REVISED | Good — just counter+overclock now, removed draw. Luck or methodology? |
| 14. Cascade Protocol | REVISED | **SOFT FAIL** — 6-for-5 still too good. Detected "illusory variance" in analysis but left the wording in the revision |
| 15. Archscientist Vex, the Unbound | REVISED | Fine — 2 less P/T, copies first overclock only, lost flying to compensate for strong ability |

**Score: 6/7 acceptable (1 soft failure)**
- Card 14: analysis correctly identified fake variability but revision didn't follow through — analysis ≠ action pattern again
- Card 11: best single-pass fix across all strategies (removed draw). Split may have helped by isolating balance pass
- Second-best score alongside S6, but different failure modes (S6: false OK on 7, S8: soft fail on 14)