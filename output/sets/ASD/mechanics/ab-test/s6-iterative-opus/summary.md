# Strategy: s6-iterative-opus

## Description

Same prompt as Simple, but if REVISED, feed revised card back. Loop until OK or max 5 iterations. Fresh conversation each iteration. Using Opus 4.6.

## Quick Results

- OK: 4 cards
- REVISED: 3 cards

## Results

| Card | Verdict | Issues Found | Changed | Cost |
|------|---------|-------------|---------|------|
| 2. Undergrowth Scrounger | OK | None | No | $0.0134 |
| 5. Subsurface Expedition Leader | OK | None | No | $0.0334 |
| 6. Defective Labor Drone | OK | None | No | $0.0143 |
| 7. Unstable Welding Unit | OK | None | No | $0.0142 |
| 11. Synaptic Overload | REVISED | Overclock exiles three cards that you may play 'until end of turn,' but this is an instant that will often be cast on... | Yes | $0.1014 |
| 14. Cascade Protocol | REVISED | Reminder text issue: The reminder text only explains overclock once using 'To overclock,' but the card performs the a... | Yes | $0.1178 |
| 15. Archscientist Vex, the Unbound | REVISED | Overclock is complexity 3 and restricted to U, R, B colors. The card is U/R, which is within the allowed color pair —... | Yes | $0.1236 |

## Total Cost

- API calls: 20
- Total tokens: 27900 in / 11146 out
- Total cost: $0.4182

## Human Evaluation

| Card | Verdict | Human Assessment |
|------|---------|-----------------|
| 2. Undergrowth Scrounger | OK | Fine |
| 5. Subsurface Expedition Leader | OK | Pretty strong result, single pass |
| 6. Defective Labor Drone | OK | Fine |
| 7. Unstable Welding Unit | OK | **FAIL** — false OK on haste+malfunction nonbo. Iteration can't fix what it doesn't detect |
| 11. Synaptic Overload | REVISED | Perfect |
| 14. Cascade Protocol | REVISED | Perfect |
| 15. Archscientist Vex, the Unbound | REVISED | Very nice end result |

**Score: 6/7 acceptable (1 failure)**
- Card 7: only failure — iteration's blind spot is false OKs (no second pass if first pass says OK)
- Cards 11 + 14: iteration fixed both cards that every other strategy so far has failed on
- Best score so far. Iteration + Opus is powerful for cards flagged as REVISED
- Weakness is structural: "are you sure it's OK?" doesn't really make sense as a strategy