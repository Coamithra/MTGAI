# Mechanic Validation Spike Results

**Date**: 2026-03-09 03:29
**Model**: claude-sonnet-4-20250514
**Temperature**: 1.0
**Cards generated**: 15
**Total cost**: $0.0913

## Per-Mechanic Results

| Mechanic | Cards | Rules Text | Flavor Fit | Balance | Creativity | Overall | Issues |
|----------|-------|-----------|------------|---------|------------|---------|--------|
| salvage | 5 | 4.60 | 4.70 | 5.00 | 4.72 | 4.75 | 4 |
| malfunction | 5 | 5.00 | 4.20 | 5.00 | 4.88 | 4.76 | 0 |
| overclock | 5 | 4.90 | 4.60 | 5.00 | 4.72 | 4.80 | 1 |

| **Overall** | **15** | **4.83** | **4.50** | **5.00** | **4.77** | **4.77** | **5** |

## Card Details

### Salvage

**Denethix Salvage Crew** {2}{W}
- Type: Creature — Human Soldier
- Rarity: common
- Oracle: When ~ enters, salvage 2. (Look at the top 2 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)
- P/T: 2/2
- Flavor: ""The city pays us by the pound for metal scraps. They don't ask where we found the blood-soaked ones.""
- Scores: rules=5.0, flavor=5.0, balance=5.0, creativity=4.8, overall=4.94

**Undergrowth Scrounger** {1}{G}
- Type: Creature — Human Scout
- Rarity: common
- Oracle: When ~ dies, salvage 3.
- P/T: 2/1
- Flavor: "She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too."
- Scores: rules=4.5, flavor=3.5, balance=5.0, creativity=4.5, overall=4.38
- Issues:
  - Missing or incorrect salvage reminder text

**Protonium Archaeologist** {2}{U}
- Type: Creature — Human Scientist
- Rarity: uncommon
- Oracle: When ~ enters, salvage 4. / Artifact spells you cast cost {1} less to cast.
- P/T: 1/4
- Flavor: ""The ancients' trash is our treasure. Their treasure is our incomprehensible doom.""
- Scores: rules=4.5, flavor=5.0, balance=5.0, creativity=4.8, overall=4.81
- Issues:
  - Missing or incorrect salvage reminder text

**Moktar Relic Hunter** {3}{G}
- Type: Creature — Moktar Scout
- Rarity: uncommon
- Oracle: When ~ enters, salvage 5. / Whenever you cast an artifact spell, ~ gets +2/+2 until end of turn.
- P/T: 3/3
- Flavor: "Moktars collect shiny things not for trade, but for the joy of hearing them rattle in their pouches."
- Scores: rules=4.5, flavor=5.0, balance=5.0, creativity=5.0, overall=4.88
- Issues:
  - Missing or incorrect salvage reminder text

**Subsurface Expedition Leader** {2}{W}{W}
- Type: Creature — Human Soldier
- Rarity: rare
- Oracle: When ~ enters, salvage 6. / {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
- P/T: 3/4
- Flavor: ""Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.""
- Scores: rules=4.5, flavor=5.0, balance=5.0, creativity=4.5, overall=4.75
- Issues:
  - Missing or incorrect salvage reminder text

### Malfunction

**Defective Labor Drone** {1}{W}
- Type: Artifact Creature — Automaton
- Rarity: common
- Oracle: Malfunction 1 (This permanent enters tapped with 1 malfunction counter on it. At the beginning of your upkeep, remove a malfunction counter from it.)
- P/T: 3/2
- Flavor: ""It keeps trying to mine the ceiling. We've explained gravity to it seventeen times." —Foreman Krix"
- Scores: rules=5.0, flavor=4.5, balance=5.0, creativity=4.8, overall=4.81

**Unstable Welding Unit** {2}{R}
- Type: Artifact Creature — Construct
- Rarity: common
- Oracle: Malfunction 1 (This permanent enters tapped with 1 malfunction counter on it. At the beginning of your upkeep, remove a malfunction counter from it.) / Haste
- P/T: 4/2
- Flavor: "The sparks it produces are either welding material or a countdown to explosion. Usually both."
- Scores: rules=5.0, flavor=4.0, balance=5.0, creativity=4.8, overall=4.69

**Salvage Processing Matrix** {3}{U}
- Type: Artifact
- Rarity: uncommon
- Oracle: Malfunction 2 (This permanent enters tapped with 2 malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.) / When the last malfunction counter is removed from ~, salvage 4. (Look at the top 4 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)
- Flavor: "Once fully operational, it can sort through debris faster than a dozen scavengers. Getting it operational is the hard part."
- Scores: rules=5.0, flavor=4.0, balance=5.0, creativity=5.0, overall=4.75

**Rampaging Siege Engine** {4}{R}
- Type: Creature — Construct
- Rarity: uncommon
- Oracle: Malfunction 2 (This permanent enters tapped with 2 malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.) / When the last malfunction counter is removed from ~, ~ deals 3 damage to any target. / Trample
- P/T: 6/4
- Flavor: "It takes time to remember which end of itself does the destroying."
- Scores: rules=5.0, flavor=4.0, balance=5.0, creativity=5.0, overall=4.75

**Experimental Thought Engine** {2}{U}{U}
- Type: Artifact Creature — Construct
- Rarity: rare
- Oracle: Malfunction 3 (This permanent enters tapped with 3 malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.) / {2}{U}, {T}: Remove a malfunction counter from target permanent you control. / Whenever you remove a malfunction counter from a permanent you control, draw a card.
- P/T: 3/5
- Flavor: ""It's learning to fix itself. And us. And everything else, whether we want it to or not." —Dr. Vess"
- Scores: rules=5.0, flavor=4.5, balance=5.0, creativity=4.8, overall=4.81

### Overclock

**Synaptic Overload** {1}{U}
- Type: Instant
- Rarity: uncommon
- Oracle: As an additional cost to cast ~, overclock. (Exile the top three cards of your library. You may play them until end of turn.) / Counter target spell. If you overclocked this turn, draw a card.
- Flavor: ""The prototype neural interface worked perfectly. The subject's brain, however, did not." —Dr. Malleus, Cult of Science"
- Scores: rules=5.0, flavor=5.0, balance=5.0, creativity=4.8, overall=4.94

**Jury-Rigged Berserker** {2}{R}
- Type: Creature — Human Soldier
- Rarity: uncommon
- Oracle: Haste / Whenever ~ attacks, if you overclocked this turn, ~ gets +3/+0 and gains trample until end of turn.
- P/T: 2/2
- Flavor: ""Sir, the combat stimulants are showing a 73% chance of catastrophic organ failure." "Excellent. Deploy immediately.""
- Scores: rules=4.5, flavor=4.0, balance=5.0, creativity=4.8, overall=4.56
- Issues:
  - Missing or incorrect overclock reminder text

**Vivisector Prime** {2}{B}{B}
- Type: Creature — Human Scientist
- Rarity: rare
- Oracle: Deathtouch / Whenever you overclock (exile the top three cards of your library, you may play them until end of turn), each opponent loses 2 life and you gain 2 life. / {3}{B}: Overclock.
- P/T: 3/3
- Flavor: ""The human circulatory system has such fascinating failure modes when subjected to protonium exposure.""
- Scores: rules=5.0, flavor=5.0, balance=5.0, creativity=5.0, overall=5.00

**Cascade Protocol** {3}{R}{R}
- Type: Sorcery
- Rarity: rare
- Oracle: Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.) / ~ deals 2 damage to any target for each card exiled with ~ this way.
- Flavor: ""The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion." —Final log, Research Station Gamma"
- Scores: rules=5.0, flavor=4.0, balance=5.0, creativity=4.5, overall=4.62

**Archscientist Vex, the Unbound** {2}{U}{R}
- Type: Legendary Creature — Human Scientist
- Rarity: mythic
- Oracle: Flying / Cards exiled with overclock (exile the top three cards of your library, you may play them until end of turn) cost {2} less to cast. / Whenever you cast a spell exiled with overclock, copy it. You may choose new targets for the copy.
- P/T: 3/4
- Flavor: ""I have transcended the limitations of sanity, safety, and the laws of thermodynamics.""
- Scores: rules=5.0, flavor=5.0, balance=5.0, creativity=4.5, overall=4.88

## GO/NO-GO Assessment

- Rules text avg: 4.83 (need >= 4.0) -- PASS
- Overall avg: 4.77 (need >= 3.5) -- PASS

### Per-Mechanic Assessment

- **salvage**: rules=4.60, overall=4.75 -- GO
- **malfunction**: rules=5.00, overall=4.76 -- GO
- **overclock**: rules=4.90, overall=4.80 -- GO

### Verdict: **GO**
