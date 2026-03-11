# Strategy: s7-detailed-opus

## Description

Two-step: first call gets detailed analysis against a comprehensive checklist (templating, keyword interactions, balance, design, color pie). Second call submits the revised card via tool_use. Two API calls per card. Using Opus 4.6.

## Quick Results

- OK: 1 cards
- REVISED: 6 cards

## Results

| Card | Verdict | Issues Found | Changed | Cost |
|------|---------|-------------|---------|------|
| 2. Undergrowth Scrounger | REVISED | Missing reminder text for the custom keyword 'salvage' at common rarity. | Yes | $0.0479 |
| 5. Subsurface Expedition Leader | REVISED | Missing reminder text for salvage on first use. Custom set mechanic 'salvage' should include reminder text on its fir... | Yes | $0.0522 |
| 6. Defective Labor Drone | OK | None | No | $0.0476 |
| 7. Unstable Welding Unit | REVISED | Haste is completely nonfunctional with Malfunction. Malfunction causes the creature to enter tapped, which negates ha... | Yes | $0.0535 |
| 11. Synaptic Overload | REVISED | Overclock used as an additional cost doesn't work cleanly within the rules — keyword actions aren't costs. Restructur... | Yes | $0.0568 |
| 14. Cascade Protocol | REVISED | Balance: 12 damage to any target plus 6 impulse-drawn cards at 5 mana is drastically above rate. Comparable cards cos... | Yes | $0.0575 |
| 15. Archscientist Vex, the Unbound | REVISED | Overclock is defined as a keyword action but the card never instructs you to perform it — no triggered or activated a... | Yes | $0.0571 |

## Total Cost

- API calls: 14
- Total tokens: 21100 in / 10682 out
- Total cost: $0.3725

## Human Evaluation

| Card | Verdict | Human Assessment |
|------|---------|-----------------|
| 2. Undergrowth Scrounger | REVISED | Fine |
| 5. Subsurface Expedition Leader | REVISED | Fine |
| 6. Defective Labor Drone | OK | Fine |
| 7. Unstable Welding Unit | REVISED | Good — replaced haste with menace. Detailed prompt catches the nonbo |
| 11. Synaptic Overload | REVISED | **FAIL** — 1UU counter+overclock+draw again. Detailed analysis detects issues but revision still undernerfs |
| 14. Cascade Protocol | REVISED | **FAIL** — interesting "nonland" restriction but still ~8 damage for 5 mana. Cool direction, iteration might fix it |
| 15. Archscientist Vex, the Unbound | REVISED | Good — auto-overclock is nice. Tricky timing but appropriate for mythic |

**Score: 5/7 acceptable (2 failures)**
- Card 7: detailed prompt successfully catches haste+malfunction nonbo (S5/S6 simple prompt missed it)
- Cards 11 + 14: detailed analysis identifies the problems but single-pass revision doesn't go far enough
- Key insight: detailed analysis + iteration could be the winning combo (analysis catches nonbos, iteration polishes balance)