# Strategy: s4-split-sonnet

## Description

Three separate review passes (templating, mechanics, balance) followed by a single revision call combining all feedback. Four API calls per card. Using Sonnet 4.6.

## Quick Results

- REVISED: 7 cards

## Results

| Card | Verdict | Issues Found | Changed | Cost |
|------|---------|-------------|---------|------|
| 2. Undergrowth Scrounger | REVISED | Missing reminder text for Salvage 3 on a common card. Added parenthetical reminder text per set guidelines, with the ... | Yes | $0.0334 |
| 5. Subsurface Expedition Leader | REVISED | Reminder text missing on first instance of Salvage in the triggered ability.; Tilde (~) replaced with full card name ... | Yes | $0.0354 |
| 6. Defective Labor Drone | REVISED | Balance: A 3/2 for {1}{W} with only Malfunction 1 (one-turn delay) is too aggressively above-rate for common rarity. ... | Yes | $0.0374 |
| 7. Unstable Welding Unit | REVISED | Ability ordering: Haste should appear before Malfunction 1 per MTG templating conventions (simpler keywords precede c... | Yes | $0.0360 |
| 11. Synaptic Overload | REVISED | [; "; O | Yes | $0.0401 |
| 14. Cascade Protocol | REVISED | Reminder text appeared after second overclock instance instead of first; Reminder text only described one overclock i... | Yes | $0.0366 |
| 15. Archscientist Vex, the Unbound | REVISED | Reminder text embedded mid-sentence inside a static ability (non-standard; malformed); 'Cards exiled with overclock' ... | Yes | $0.0485 |

## Total Cost

- API calls: 28
- Total tokens: 30922 in / 11641 out
- Total cost: $0.2674

## Human Evaluation

| Card | Verdict | Human Assessment |
|------|---------|-----------------|
| 2. Undergrowth Scrounger | REVISED | Fine |
| 5. Subsurface Expedition Leader | REVISED | Fine |
| 6. Defective Labor Drone | REVISED | Meh — nerfed to 2/2 malfunction 1 for 1W, which is trash. Bad cards exist but earlier runs produced better 2/3 |
| 7. Unstable Welding Unit | REVISED | Perfect — given trample |
| 11. Synaptic Overload | REVISED | **FAIL** — cost increased but still overclock + draw + counterspell |
| 14. Cascade Protocol | REVISED | **FAIL** — same dud position as S3 |
| 15. Archscientist Vex, the Unbound | REVISED | Good — 3/4 flying for 4, copies overclock spells (no cost reduction). Good for mythic, though earlier iterations were better |

**Score: 5/7 acceptable (2 failures)**
- Card 11: same pattern — counter+cantrip+overclock remains broken even with cost increase
- Card 14: converged on same weak redesign as S3
- Overall: a bit meh, but expanded prompting does steer the model better