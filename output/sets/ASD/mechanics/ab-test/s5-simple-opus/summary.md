# Strategy: s5-simple-opus

## Description

Single prompt: review card and return revised version or OK. One API call per card. Using Opus 4.6.

## Quick Results

- OK: 3 cards
- REVISED: 4 cards

## Results

| Card | Verdict | Issues Found | Changed | Cost |
|------|---------|-------------|---------|------|
| 2. Undergrowth Scrounger | OK | None | No | $0.0134 |
| 5. Subsurface Expedition Leader | REVISED | Salvage 6 on ETB is appropriate for rare per the scaling guidelines (6+ at rare/mythic) — this is fine.; Salvage 3 on... | Yes | $0.0191 |
| 6. Defective Labor Drone | OK | None | No | $0.0143 |
| 7. Unstable Welding Unit | OK | None | No | $0.0142 |
| 11. Synaptic Overload | REVISED | Overclock is a keyword action, not a keyword ability. It should not be used as 'an additional cost to cast' — keyword... | Yes | $0.0209 |
| 14. Cascade Protocol | REVISED | [; "; R | Yes | $0.0199 |
| 15. Archscientist Vex, the Unbound | REVISED | Overclock reminder text is incorrectly inlined in the oracle text. Overclock is a keyword action defined for the set,... | Yes | $0.0234 |

## Total Cost

- API calls: 7
- Total tokens: 9739 in / 3065 out
- Total cost: $0.1253

## Human Evaluation

| Card | Verdict | Human Assessment |
|------|---------|-----------------|
| 2. Undergrowth Scrounger | OK | Fine |
| 5. Subsurface Expedition Leader | REVISED | Beefy with free salvage but acceptable |
| 6. Defective Labor Drone | OK | Agree |
| 7. Unstable Welding Unit | OK | **FAIL** — did not catch haste+malfunction nonbo. Disappointing from Opus |
| 11. Synaptic Overload | REVISED | **FAIL** — same 1UU counter+overclock+draw pattern |
| 14. Cascade Protocol | REVISED | **FAIL** — went straight 6 dmg for 5 mana but didn't spot "for each card exiled" is always exactly 6 |
| 15. Archscientist Vex, the Unbound | REVISED | Fine — stronger abilities with synergy but weaker body |

**Score: 4/7 acceptable (3 failures)**
- Card 7: Simple/Opus missed the haste+malfunction nonbo entirely (OK'd it)
- Card 11: same broken counter+cantrip+overclock
- Card 14: false variability not detected
- Worst Opus result so far — simple prompting insufficient even for Opus