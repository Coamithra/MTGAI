# Skeleton Revision Report

Set: ASD
Total rounds: 2
Total cost: $3.3759
Total cards replaced: 32

---

## Round 1

Timestamp: 2026-03-14T00:42:49.825365+00:00
Cost: $1.9635

### Analysis

The set has three interrelated structural problems: (1) Salvage is massively over-represented at 12 cards vs 6 planned, meaning 6 Salvage cards need to lose the mechanic or be replaced; (2) Malfunction is 2 short (3 vs 5 planned); (3) Overclock is 2 short (1 vs 3 planned). Additionally, there are 11 complexity tier mismatches.

**Strategy:**
- The planned distribution tells us exactly which slots SHOULD have which mechanics. Cards in those slots that are missing their assigned mechanic need regeneration. Cards that have Salvage but SHOULDN'T need to lose it.
- **Slots that should have Salvage (6):** W-C-04, U-C-04, G-C-02, WU-U-01, WG-U-01, G-R-01. All 6 of these currently DO have Salvage — good, keep them.
- **Slots that should have Malfunction (5):** W-C-02, X-C-01, R-U-01, WR-U-01, U-R-01. Currently only X-U-01 has Malfunction (which isn't even in the plan). W-C-02 has no Malfunction, X-C-01 has no Malfunction, R-U-01 has no Malfunction, WR-U-01 has no Malfunction, U-R-01 has no Malfunction. So we need to regenerate these 5 slots — but W-C-02 (Fist Patrol Rider) is a simple vigilance creature, and the plan says it should have Malfunction 1. Similarly for the others.
- **Slots that should have Overclock (3):** UB-U-01, R-U-03, B-M-01. Currently only R-R-02 has Overclock. UB-U-01 has no Overclock, R-U-03 has no Overclock, B-M-01 has no Overclock.
- **Extra Salvage cards (not in plan):** G-U-01 (Moktar Salvager), G-U-02 (Rendon Packleader), U-U-02 (Subsurface Cartographer), W-U-02 (Fist Supply Marshal), U-M-01 (The Head Scientist), U-R-02 (The Cartography Engine) — these 6 have Salvage but their slots aren't in the Salvage plan. They need to lose Salvage.

I'll prioritize changes that fix BOTH mechanic distribution AND complexity mismatches simultaneously. Reprints (Murder B-C-03, Elvish Mystic G-C-01) are untouchable. Load-bearing cards (signpost uncommons, key rares, mythics with strong archetype roles) should be preserved where possible unless they're in a slot that demands a different mechanic.

**Key changes needed:**
1. W-C-02: Add Malfunction 1 (planned slot) — also fixes no complexity mismatch
2. X-C-01: Regenerate as Malfunction 1 artifact — fixes complexity mismatch (vanilla→evergreen with malfunction)
3. R-U-01: Regenerate with Malfunction 2 — fixes complexity mismatch (evergreen→complex)
4. WR-U-01: Regenerate with Malfunction 2 — signpost uncommon, plan demands it
5. U-R-01: Regenerate with Malfunction 3 — plan demands it
6. UB-U-01: Regenerate with Overclock — signpost uncommon, plan demands it
7. R-U-03: Regenerate with Overclock — plan demands it
8. B-M-01: Regenerate with Overclock — plan demands it
9-14. Remove excess Salvage from 6 cards: G-U-01, G-U-02, U-U-02, W-U-02, U-M-01, U-R-02

To minimize changes, I'll focus on the most impactful swaps. Some excess Salvage cards are on load-bearing slots (U-M-01 is a mythic, U-R-02 is a legendary rare) — I'll still regenerate them since they're in slots NOT planned for Salvage, but with care to preserve their archetype role.

### Changes (19)

- **W-C-02** (Fist Patrol Rider) — regenerate
  - New constraints: {"card_type": "Creature", "cmc_target": 2, "mechanic_tag": "malfunction", "notes": "Must use Malfunction 1. White common creature with vigilance. Above-rate stats (e.g. 2/3 or 3/2) justified by entering tapped with a malfunction counter. Human Soldier."}
  - Reasoning: Plan assigns Malfunction 1 to this slot. Current card is a simple vigilance 2/2 with no set mechanic. Regenerate as an above-rate creature with Malfunction 1 and vigilance. This adds +1 Malfunction. No Salvage is lost since it didn't have any.

- **X-C-01** (Corroded Exo-Frame) — regenerate
  - New constraints: {"card_type": "Artifact", "cmc_target": 2, "mechanic_tag": "malfunction", "notes": "Must use Malfunction 1. Common utility artifact (mana rock or similar). Enters tapped with 1 malfunction counter, providing a simple delayed benefit. Keep it simple for common."}
  - Reasoning: Plan assigns Malfunction 1 to this slot. Current card is a generic Equipment with no set mechanic and has a complexity mismatch (slot expects vanilla, card is evergreen). Regenerate as a common artifact with Malfunction 1 — a simple mana rock or utility artifact. This adds +1 Malfunction and fixes the complexity mismatch. Also improves artifact density.

- **R-U-01** (Spark Saboteur) — regenerate
  - New constraints: {"card_type": "Creature", "cmc_target": 2, "mechanic_tag": "malfunction", "notes": "Must use Malfunction 2. Red uncommon creature with aggressive stats. 'When the last malfunction counter is removed from ~, deal 3 damage to any target.' Human Rebel or Construct. Enters tapped with 2 counters as tempo cost."}
  - Reasoning: Plan assigns Malfunction 2 to this slot. Current card has no Malfunction and has a complexity mismatch (slot expects evergreen, card is complex). Regenerate as a red uncommon creature with Malfunction 2 and a payoff when the last counter is removed. This adds +1 Malfunction, fixes the complexity mismatch, and no Salvage is lost.

- **WR-U-01** (Spark Rallier) — regenerate
  - New constraints: {"card_type": "Creature", "cmc_target": 2, "mechanic_tag": "malfunction", "notes": "WR signpost uncommon. Must use Malfunction 2. '{1}: Remove a malfunction counter from ~.' Aggressive stats (e.g. 3/2 or 3/3) justified by Malfunction tempo cost. Human Rebel. Should signal the WR Spark Rebellion archetype."}
  - Reasoning: Plan assigns Malfunction 2 to this slot. This is the WR signpost uncommon — plan specifically wants it to showcase Malfunction with a self-removal activation. Current card has no Malfunction. Regenerate to match the archetype plan. No Salvage lost.

- **U-R-01** (Cult Savant) — regenerate
  - New constraints: {"card_type": "Artifact Creature", "cmc_target": 3, "mechanic_tag": "malfunction", "notes": "Must use Malfunction 3. Blue rare artifact creature (Construct or Automaton). Powerful payoff: 'Has hexproof as long as it has a malfunction counter on it' plus a strong ability once fully online. Above-rate body justified by long Malfunction delay."}
  - Reasoning: Plan assigns Malfunction 3 to this slot. Current card is an artifact-matters creature with no Malfunction. Regenerate as a blue rare with Malfunction 3 and a powerful payoff. This adds +1 Malfunction. No Salvage lost. Can be an artifact creature to help artifact density.

- **UB-U-01** (Depth Crawler Archivist) — regenerate
  - New constraints: {"card_type": "Creature", "cmc_target": 3, "mechanic_tag": "overclock", "notes": "UB signpost uncommon. Must use Overclock. 'When ~ enters, overclock. You may cast instant and sorcery cards exiled this way until end of your next turn.' Human Rogue or similar. 2/2 or 2/3 body. Should signal the UB archetype."}
  - Reasoning: Plan assigns Overclock to this slot as the UB signpost uncommon. Current card has mill/graveyard synergy but no Overclock. Regenerate with Overclock as the UB archetype enabler. This adds +1 Overclock. No Salvage lost.

- **R-U-03** (Raider's Bounty) — regenerate
  - New constraints: {"card_type": "Enchantment", "cmc_target": 4, "mechanic_tag": "overclock", "notes": "Red uncommon enchantment. Should reference Overclock. 'Whenever you cast a noncreature spell, if you overclocked this turn, ~ deals 2 damage to each opponent.' May have an activated overclock ability or trigger overclock on ETB. CMC 4 is fine for uncommon enchantment."}
  - Reasoning: Plan assigns Overclock to this slot. Current card is an enchantment with impulse-draw-on-combat-damage but no Overclock keyword. Regenerate as a red uncommon enchantment with Overclock synergy. This adds +1 Overclock. No Salvage lost.

- **B-M-01** (Apex of the Subsurface) — regenerate
  - New constraints: {"card_type": "Creature", "cmc_target": 4, "mechanic_tag": "overclock", "notes": "Black mythic creature. Must have repeatable Overclock: '{2}{B}, {T}: Overclock. Whenever you overclock, each opponent loses 2 life.' Horror or Demon type. Powerful body (4/4 or similar) with deathtouch. Legendary."}
  - Reasoning: Plan assigns Overclock to this slot as the black mythic. Current card is a 4/4 deathtouch Horror with exile-on-kill but no Overclock. Regenerate as a mythic creature with repeatable Overclock. This adds +1 Overclock. No Salvage lost.

- **W-U-02** (Fist Supply Marshal) — regenerate
  - New constraints: {"card_type": "Creature", "cmc_target": 3, "notes": "White uncommon creature. Evergreen complexity only \u2014 no set mechanics. Human Soldier with a simple evergreen ability like vigilance + a basic ETB (e.g., gain life, create a token). Should support white's go-wide or artifact-matters themes without using Salvage."}
  - Reasoning: This slot has Salvage but is NOT in the Salvage plan — it's one of 6 excess Salvage cards. Also has a complexity mismatch (slot expects evergreen, card is complex due to Salvage + artifact-enters trigger). Regenerate as a straightforward white uncommon creature with evergreen keywords only. This removes 1 excess Salvage and fixes the complexity mismatch.

- **U-U-02** (Subsurface Cartographer) — regenerate
  - New constraints: {"card_type": "Creature", "cmc_target": 3, "notes": "Blue uncommon creature. No Salvage. Human Wizard or Artificer with flying. 2/2 body. Can have an artifact-synergy ability (e.g., 'Whenever an artifact enters under your control, draw a card then discard a card') or simple card filtering. Supports blue's artifact themes without Salvage."}
  - Reasoning: This slot has Salvage but is NOT in the Salvage plan — excess Salvage card. Regenerate as a blue uncommon without Salvage. Can keep the flying combat-damage trigger flavor but with a different payoff. Removes 1 excess Salvage.

- **G-U-01** (Moktar Salvager) — regenerate
  - New constraints: {"card_type": "Creature", "cmc_target": 2, "notes": "Green uncommon creature. No Salvage. Moktar Warrior or Beast. 2/2 or 3/1 body. Can have a simple ability that supports green's themes (e.g., fight, +1/+1 counters, trample). Evergreen or simple triggered ability."}
  - Reasoning: This slot has Salvage but is NOT in the Salvage plan — excess Salvage card. Green uncommon slot. Regenerate as a green uncommon creature without Salvage. Can be an artifact creature to boost artifact density. Removes 1 excess Salvage.

- **G-U-02** (Rendon Packleader) — regenerate
  - New constraints: {"card_type": "Creature", "cmc_target": 4, "notes": "Green uncommon Dinosaur. No Salvage. 4/3 or 4/4 with trample. Can have a combat-damage trigger that doesn't involve Salvage (e.g., create a token, put a +1/+1 counter, fight). Supports green's midrange/dinosaur themes."}
  - Reasoning: This slot has Salvage but is NOT in the Salvage plan — excess Salvage card. Regenerate as a green uncommon creature without Salvage. A 4-mana dinosaur with trample and a non-Salvage ability. Removes 1 excess Salvage.

- **U-M-01** (The Head Scientist) — regenerate
  - New constraints: {"card_type": "Creature", "cmc_target": 3, "notes": "Blue mythic legendary creature. Human Artificer. No Salvage. Flash. 1/3 body. 'Artifact spells you cast cost {1} less to cast.' Replace Salvage with a different powerful ETB or static (e.g., 'When ~ enters, draw cards equal to the number of artifacts you control' or 'Artifacts you control have hexproof'). Must remain a strong artifact-matters build-around."}
  - Reasoning: This slot has Salvage but is NOT in the Salvage plan — excess Salvage card. This is blue's mythic, a key archetype piece. Regenerate preserving the artifact-matters legendary identity but replacing Salvage with a different powerful ability. Removes 1 excess Salvage.

- **U-R-02** (The Cartography Engine) — regenerate
  - New constraints: {"card_type": "Enchantment", "cmc_target": 4, "notes": "Blue rare legendary enchantment with artifact subtype. No Salvage. Artifact-matters engine: 'Whenever an artifact enters under your control, draw a card.' Or 'At the beginning of your upkeep, create a 1/1 colorless Construct artifact creature token.' Should be a powerful artifact-synergy engine without using Salvage."}
  - Reasoning: This slot has Salvage but is NOT in the Salvage plan — excess Salvage card. Legendary enchantment-artifact rare. Regenerate keeping the artifact-engine identity but without Salvage. Can use artifact-enters triggers with different payoffs. Removes 1 excess Salvage.

- **WU-U-01** (Relic Warden Automaton) — regenerate
  - New constraints: {"card_type": "Artifact Creature", "cmc_target": 2, "mechanic_tag": "salvage", "notes": "WU signpost uncommon. Artifact Creature \u2014 Construct. Must use Salvage 4. 'When ~ enters, salvage 4. If you put an artifact card into your hand this way, [bonus effect like scry 2, gain 2 life, or tap target creature].' 2/2 with vigilance. Signals the WU Ancient Technology archetype."}
  - Reasoning: This is the WU signpost uncommon. Plan says it should have Salvage 4 with an artifact payoff. Current card has no Salvage and has a complexity mismatch (slot expects complex, card is evergreen). Regenerate to match the plan. This keeps 1 planned Salvage card correct and fixes the complexity mismatch.

- **WG-U-01** (Frontier Homesteader) — regenerate
  - New constraints: {"card_type": "Creature", "cmc_target": 2, "mechanic_tag": "salvage", "notes": "WG signpost uncommon. Creature \u2014 Human Settler. Must use Salvage 4. 'When ~ enters, salvage 4.' Plus a payoff for finding artifacts or tokens theme. 1/1 or 2/2 body with a +1/+1 counter subtheme tie-in. Signals the WG Frontier Settlers archetype."}
  - Reasoning: This is the WG signpost uncommon. Plan says it should have Salvage 4. Current card has no Salvage and has a complexity mismatch (slot expects complex, card is evergreen). Regenerate to match the plan. Keeps 1 planned Salvage card correct and fixes the complexity mismatch.

- **U-U-01** (Cult Initiate) — regenerate
  - New constraints: {"card_type": "Creature", "cmc_target": 1, "notes": "Blue uncommon creature. Evergreen complexity only. Human Artificer 1/1. Simple artifact-matters creature with only evergreen keywords (e.g., 'Flash' or 'When ~ enters, scry 2'). No set mechanics, no complex triggers."}
  - Reasoning: Complexity mismatch: slot expects evergreen, card is complex (artifact-cast trigger + scry + power boost). Regenerate as a simpler blue uncommon creature with evergreen abilities only. No mechanic changes needed — just simplify.

- **B-U-02** (Luminous Spark Extractor) — regenerate
  - New constraints: {"card_type": "Creature", "cmc_target": 3, "notes": "Black uncommon creature. Evergreen complexity only. Human Assassin 2/2 or 3/1. Simple abilities like deathtouch, menace, or a basic ETB (e.g., 'When ~ enters, each opponent loses 2 life'). No complex conditional triggers."}
  - Reasoning: Complexity mismatch: slot expects evergreen, card is complex (ETB discard + conditional creature removal). Regenerate as a simpler black uncommon creature with evergreen-level abilities.

- **R-U-02** (Moktar War-Screamer) — regenerate
  - New constraints: {"card_type": "Creature", "cmc_target": 4, "notes": "Red uncommon creature. Evergreen complexity only. Moktar Berserker 3/3 or 4/2. Simple evergreen keywords like haste + trample, or haste + menace. No complex triggered abilities."}
  - Reasoning: Complexity mismatch: slot expects evergreen, card is complex (haste + attack trigger with scaling power boost). Regenerate as a simpler red uncommon creature with evergreen-level abilities.

### Expected Improvements
- salvage_count: 6
- malfunction_count: 5
- overclock_count: 3
- artifact_count: 8

### Metrics Comparison

| Metric | Before | After |
| ------ | ------ | ----- |
| malfunction_count | 3 | 2 |
| overclock_count | 1 | 1 |
| salvage_count | 12 | 10 |
| tier_mismatches | 11 | 9 |
| total_issues | 25 | 23 |

### Regenerated Cards
- Catacomb Extractor
- Ixthra, Flesh Architect
- Ruin-Trail Scavenger
- Rendon Apex Predator
- Moktar Firestarter
- Wasteland War-Raptor
- War-Camp Pillaging
- Flickerfield Operative
- Subsurface Cartographer
- Paradox Diver
- Anomalous Resonance
- The Custodian Remnant
- Depth-Blind Cataloger
- Fist Patrol Guard
- Gatehouse Requisitioner
- Frontier Homesteader
- Spark Cell Agitator
- Protonium Technician
- Scrapheap Shield

---

## Round 2

Timestamp: 2026-03-14T00:45:53.634880+00:00
Cost: $1.4124

### Analysis

The set has three main structural problems:

1. **Salvage is over-represented** (10 actual vs 6 planned, +4 delta). Cards with salvage that are NOT in the planned distribution: W-U-02 (Gatehouse Requisitioner), U-U-02 (Subsurface Cartographer), G-U-01 (Ruin-Trail Scavenger), and U-C-04 (Excavate the Archives has salvage but IS planned). Looking at the plan, the 6 planned salvage slots are W-C-04, U-C-04, G-C-02, WU-U-01, WG-U-01, G-R-01. The extra salvage cards beyond the plan are: W-U-02, U-U-02, G-U-01, and W-C-04 (which has salvage but the plan says it should). Counting actual salvage: W-C-04, U-C-04, W-U-02, WU-U-01, WG-U-01, G-U-01, G-R-01, U-U-02 = 8 visible plus possibly others. We need to remove ~4 salvage instances.

2. **Malfunction is under-represented** (2 actual vs 5 planned, -3 delta). Currently only X-U-01 has malfunction. The plan wants malfunction on W-C-02, X-C-01, R-U-01, WR-U-01, and U-R-01. That's 5 slots needing malfunction but only 1-2 have it.

3. **Overclock is under-represented** (1 actual vs 3 planned, -2 delta). Only R-R-02 has overclock. Plan wants it on UB-U-01, R-U-03, and B-M-01.

**Strategy:** 
- Replace excess salvage cards (W-U-02, U-U-02, G-U-01) with malfunction/overclock cards or simpler designs
- Fix planned malfunction slots (W-C-02, X-C-01, R-U-01, WR-U-01) by regenerating with malfunction
- Fix planned overclock slots (UB-U-01, R-U-03, B-M-01) by regenerating with overclock
- Fix complexity mismatches where they overlap with mechanic fixes
- Preserve load-bearing cards: signpost uncommons (WU-U-01, WG-U-01, WR-U-01, UB-U-01), key removal (Murder, Sanctioned Exile, Scorched Passage), reprints (Murder, Elvish Mystic), and archetype enablers

### Changes (13)

- **W-C-02** (Fist Patrol Guard) — regenerate
  - Reasoning: The plan explicitly calls for Malfunction 1 on this slot (above-rate 2-drop with vigilance that enters tapped). Current card is a vanilla 2/2 vigilance with no malfunction. Regenerating to add Malfunction 1 fixes one malfunction deficit and matches the planned distribution. Can keep similar stats/feel but with the mechanic added.

- **X-C-01** (Scrapheap Shield) — modify_slot
  - New constraints: {"card_type": "Artifact", "cmc_target": 2, "mechanic_tag": "malfunction", "notes": "Must use Malfunction 1. Simple common mana rock or utility artifact. Enters tapped with 1 malfunction counter. Should be a clean vanilla-complexity design aside from the keyword."}
  - Reasoning: Plan calls for Malfunction 1 on a common artifact (simple mana rock or utility artifact). Current card is an equipment with no malfunction and has a complexity mismatch (slot expects vanilla, card is evergreen). Changing to an artifact with Malfunction 1 fixes both the malfunction deficit and the complexity mismatch. A mana rock or utility artifact with Malfunction 1 is a clean common design.

- **R-U-01** (Moktar Firestarter) — regenerate
  - Reasoning: Plan explicitly calls for Malfunction 2 on this slot with a 'deal 3 damage when last counter removed' payoff. Current card has artifact-death triggers instead of malfunction, and has a complexity mismatch (slot expects evergreen, card is complex). Regenerating with Malfunction 2 fixes one malfunction deficit and the complexity mismatch. The malfunction payoff trigger is simpler to parse than the current artifact-sacrifice design.

- **WR-U-01** (Spark Cell Agitator) — regenerate
  - Reasoning: This is the WR signpost uncommon, and the plan explicitly calls for Malfunction 2 with a '{1}: Remove a malfunction counter' activation. Current card has an equipment-based trigger instead. Regenerating to match the planned malfunction design preserves the signpost role while fixing the mechanic distribution. This is load-bearing as a signpost but the MECHANIC is wrong, so it must change.

- **UB-U-01** (Depth-Blind Cataloger) — regenerate
  - Reasoning: This is the UB signpost uncommon, and the plan explicitly calls for overclock on this slot. Current card has mill/graveyard triggers but no overclock. Regenerating with overclock fixes one overclock deficit. Load-bearing as signpost but needs the correct mechanic to properly signal the UB archetype.

- **R-U-03** (War-Camp Pillaging) — regenerate
  - Reasoning: Plan calls for overclock on this slot ('Whenever you cast a noncreature spell, if you overclocked this turn, deal 2 damage'). Current card has an impulse-draw-on-combat-damage effect but no overclock keyword. Regenerating with overclock fixes the second overclock deficit.

- **B-M-01** (Ixthra, Flesh Architect) — regenerate
  - Reasoning: Plan calls for a mythic creature with repeatable overclock ('{2}{B}, {T}: Overclock'). Current card has death-exile-reanimate triggers but no overclock. Regenerating with overclock fixes the third overclock deficit. As a mythic, this is the right home for the complexity-3 overclock mechanic.

- **W-U-02** (Gatehouse Requisitioner) — regenerate
  - Reasoning: This card has salvage but is NOT one of the 6 planned salvage slots — it's an extra salvage card contributing to the +4 surplus. Replacing it with a non-salvage white uncommon creature reduces salvage count by 1. Slot expects evergreen complexity, so a clean creature with a simple keyword fits.

- **U-U-02** (Subsurface Cartographer) — regenerate
  - Reasoning: This card has salvage but is NOT one of the 6 planned salvage slots — another extra salvage card. Replacing with a non-salvage blue uncommon creature reduces salvage count by 1. Could be an artifact creature to boost artifact density. Slot expects evergreen complexity.

- **G-U-01** (Ruin-Trail Scavenger) — modify_slot
  - New constraints: {"card_type": "Artifact Creature", "cmc_target": 2, "notes": "Green uncommon artifact creature with a simple evergreen keyword (e.g., reach or trample). No salvage. Should support the artifact-matters subtheme by being an artifact itself. Construct or Beast type fits the setting."}
  - Reasoning: This card has salvage but is NOT one of the 6 planned salvage slots — a third extra salvage card. Also has a complexity mismatch (slot expects evergreen, card is complex). Replacing with a non-salvage green uncommon creature fixes both issues. Making it an artifact creature improves artifact density.

- **G-U-02** (Rendon Apex Predator) — modify_slot
  - New constraints: {"card_type": "Creature", "cmc_target": 4, "notes": "Green uncommon creature with evergreen keywords only (e.g., trample + reach, or trample + vigilance). Dinosaur type preferred. No set mechanics. Should be a solid midrange body."}
  - Reasoning: Complexity mismatch — slot expects evergreen but card is complex (fight-on-attack trigger). Replacing with a simpler green uncommon creature that uses only evergreen keywords. No mechanic distribution change needed, just complexity alignment.

- **B-U-02** (Catacomb Extractor) — modify_slot
  - New constraints: {"card_type": "Creature", "cmc_target": 3, "notes": "Black uncommon creature with deathtouch and one other evergreen keyword (e.g., menace or lifelink). Human Rogue type fits the setting. No set-specific mechanics. Simple, clean design."}
  - Reasoning: Complexity mismatch — slot expects evergreen but card is complex (artifact sacrifice on combat damage). Replacing with a simpler black uncommon creature with evergreen keywords. No mechanic distribution change needed.

- **W-C-04** (Salvage the Gatehouse) — regenerate
  - Reasoning: Complexity mismatch — slot expects complex but card reads as evergreen (token creation + salvage is straightforward). The plan DOES want salvage here, so salvage stays, but the card needs a more complex design to match the 'complex' tier expectation. Regenerate to add more mechanical depth around the salvage (e.g., conditional effect, choice, or scaling based on artifacts controlled).

### Expected Improvements
- salvage_count: 7
- malfunction_count: 5
- overclock_count: 3
- artifact_count: 8

### Metrics Comparison

| Metric | Before | After |
| ------ | ------ | ----- |
| malfunction_count | 2 | 3 |
| overclock_count | 1 | 1 |
| salvage_count | 10 | 8 |
| tier_mismatches | 9 | 10 |
| total_issues | 23 | 25 |

### Regenerated Cards
- Catacomb Harvester
- Luminous Spark Chirurgeon
- Salvaged Rootwalker
- Rendon Apex Tracker
- Moktar Flamebrander
- Rift-Engine Eruption
- Relay Node Technician
- Depth-Blind Cataloger
- Fist Patrol Scout
- Requisition Sweep
- Fist Checkpoint Warden
- Spark Instigator
- Subsurface Signal Lamp

---

## Post-Fix Regeneration

After the initial 2-round revision, two critical bugs were discovered:

1. **** was not including the  field in generation prompts — the LLM never saw instructions like "Must use Malfunction 1"
2. **** only applied the  key from , silently dropping  and  updates

Both bugs compounded: even though the revision plan correctly identified changes and wrote good constraints, the regenerated cards never received them.

### Fix Regeneration

- **Model**: claude-haiku-4-5-20251001
- **Cost**: \/usr/bin/bash.065
- **Slots**: 11 (B-M-01, G-U-01, R-U-01, R-U-03, U-M-01, U-R-01, UB-U-01, W-C-02, WG-U-01, WR-U-01, WU-U-01)
- **Mechanic adherence**: 100% (11/11)

### Final Mechanic Distribution

| Mechanic | Planned | Actual |
|----------|---------|--------|
| Salvage | 6 | 8 |
| Malfunction | 5 | 7 |
| Overclock | 3 | 4 |

### Final Color Balance

W:10, U:10, B:10, R:9, G:9

### Total Cost (all revision work)

\.44 (Opus revision analysis \.38 + Haiku fix regeneration \/usr/bin/bash.065)
