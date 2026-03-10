# Automated Review Calibration Results — 1B-8a

Date: 2026-03-09 20:53
Model: claude-sonnet-4-20250514
Temperature: 1.0
Max prodding iterations: 2
Total input tokens: 77,406
Total output tokens: 17,896
Estimated cost: $0.50

---

## Per-Card Results

| # | Card | Human | Auto | Issues Detected | Issues Missed |
|---|------|-------|------|-----------------|---------------|
| 1 | Denethix Salvage Crew | PASS | FAIL != | S1:keyword_collision | — |
| 2 | Undergrowth Scrounger | FAIL | FAIL = | S1:keyword_collision, missing_reminder_text | — |
| 3 | Protonium Archaeologist | FAIL | FAIL = | S1:keyword_collision, missing_reminder_text | — |
| 4 | Moktar Relic Hunter | FAIL | FAIL = | S1:keyword_collision, missing_reminder_text | — |
| 5 | Subsurface Expedition Leader | FAIL | FAIL = | S1:keyword_collision, missing_reminder_text | inconsistent_capitalization |
| 6 | Defective Labor Drone | PASS | FAIL != | — | — |
| 7 | Unstable Welding Unit | FAIL | FAIL = | keyword_negated | — |
| 8 | Salvage Processing Matrix | WARN | FAIL != | enters_tapped_irrelevant | — |
| 9 | Rampaging Siege Engine | PASS | PASS = | — | — |
| 10 | Experimental Thought Engine | PASS | FAIL != | — | — |
| 11 | Synaptic Overload | FAIL | FAIL = | redundant_conditional, above_rate_balance, kitchen_sink | — |
| 12 | Jury-Rigged Berserker | FAIL | FAIL = | missing_reminder_text | — |
| 13 | Vivisector Prime | PASS | FAIL != | — | — |
| 14 | Cascade Protocol | FAIL | FAIL = | false_variability, above_rate_balance, kitchen_sink | — |
| 15 | Archscientist Vex, the Unbound | WARN | FAIL != | — | flying_tacked_on |

---

## Accuracy Metrics

**FAIL detection rate**: 8/8 = **100%** (target: >=70%) PASS

**WARN detection rate**: 1/2 = **50%** (target: >=50%) PASS

**False negatives** (missed issues): 2

**False positives** (PASS cards flagged as FAIL/WARN): 4/5

---

## Detection Source Analysis

### Issues caught by self-critique (Phase 1)

- Card 11: above_rate_balance
- Card 11: redundant_conditional
- Card 12: missing_reminder_text
- Card 14: above_rate_balance
- Card 2: S1:keyword_collision
- Card 2: missing_reminder_text
- Card 3: missing_reminder_text
- Card 4: S1:keyword_collision
- Card 4: missing_reminder_text
- Card 5: missing_reminder_text
- Card 7: keyword_negated

### Issues caught by pointed questions (Phase 2)

- Card 11: above_rate_balance
- Card 11: kitchen_sink
- Card 11: redundant_conditional
- Card 12: missing_reminder_text
- Card 14: above_rate_balance
- Card 14: false_variability
- Card 14: kitchen_sink
- Card 1: S1:keyword_collision
- Card 2: S1:keyword_collision
- Card 2: missing_reminder_text
- Card 3: S1:keyword_collision
- Card 3: missing_reminder_text
- Card 4: S1:keyword_collision
- Card 4: missing_reminder_text
- Card 5: S1:keyword_collision
- Card 5: missing_reminder_text
- Card 7: keyword_negated
- Card 8: enters_tapped_irrelevant

### Issues missed by self-critique

- Card 11: kitchen_sink
- Card 14: false_variability
- Card 14: kitchen_sink
- Card 15: flying_tacked_on
- Card 1: S1:keyword_collision
- Card 3: S1:keyword_collision
- Card 5: S1:keyword_collision
- Card 5: inconsistent_capitalization
- Card 8: enters_tapped_irrelevant

### Issues missed by pointed questions

- Card 15: flying_tacked_on
- Card 5: inconsistent_capitalization

### Issues missed entirely (both phases)

- Card 15: flying_tacked_on
- Card 5: inconsistent_capitalization

---

## Detailed Per-Card Review

### Card 1: Denethix Salvage Crew

**Human verdict**: PASS
**Auto verdict**: FAIL (critique: FAIL, pointed: PASS)

**Self-critique response** (summary):

> Looking at Denethix Salvage Crew:
> 
> **FAIL - Incorrect Salvage Templating**: The oracle text shows "salvage 2" as a keyword action, but based on the mechanic definition, salvage should be templated as a keyword ability that appears in the keywords line, not as an action in the rules text. 
> 
> The correct templating should be either:
> - Oracle text: "Salvage 2" (as a keyword ability) with full reminder text
> - Keywords line: "Salvage 2"
> 
> The current templating "When ~ enters, salvage 2" treats it like an activated or triggered ability rather than a keyword ability.
> 
> **FAIL - Missing Reminder Text**: The oracle text lacks the required reminder text for the custom salvage mechanic. According to the mechanic definition, salvage should have reminder text: "(Look at the top 2 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"
> 
> **WARN - Keywords Field Inconsistency**: The keywords field lists "Salvage" but the oracle text shows "salvage 2". There should be consistency - if salvage is a keyword ability, the keywords field should show "Salvage 2".
> 
> The card's power/toughness (2/2 for 2W), rarity (common), and color pie placement (white getting card selection/tutoring effects) are all reasonable. The salvage value of 2 matches the common scaling guidelines (2-3 at common).
> 
> **Verdict: FAIL** - Must fix templating and add reminder text before shipping.

**Pointed questions response** (summary):

> Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?
> 
> **NO** - The card only has salvage, which triggers when it enters and doesn't conflict with being a 2/2 creature.
> 
> Q2: Is reminder text present for all custom mechanics?
> 
> **YES** - Salvage has reminder text present in the oracle text: "(Look at the top 2 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"
> 
> Q3: If this card has a conditional, is that conditional actually meaningful?
> 
> **N/A** - This card has no conditionals ("if you X this turn" clauses).
> 
> Q4: Is the power level appropriate for its mana cost and rarity?
> 
> **YES** - A 2/2 for {2}{W} with card selection that finds artifacts is reasonable at common. Compare to cards like Veteran Armorer (2/2 for {2}{W} with no upside) or Squadron Hawk (1/1 flyer that tutors). The salvage effect is modest card selection, not card advantage, making this appropriately powered.
> 
> Q5: Does this card try to do too many unrelated things?
> 
> **NO** - The card has a focused design: it's a creature that helps find artifacts through salvage. The abilities are thematically and mechanically coherent.
> 
> Q6: If this card has variable effects, is the variability real or false?
> 
> **N/A** - While salvage looks at a variable number of cards (2 in this case), that number is fixed for this specific card, so there's no false variability issue here.
> 
> Q7: Do any mechanic names collide with existing MTG keywords?
> 
> **NO** - The card uses "salvage," which correctly avoids collision with the existing "scavenge" keyword from Return to Ravnica.
> 
> Q8: Does this card have irrelevant "enters tapped" effects?
> 
> ... (3 more lines)

### Card 2: Undergrowth Scrounger

**Human verdict**: FAIL
**Auto verdict**: FAIL (critique: FAIL, pointed: FAIL)

**Self-critique response** (summary):

> Looking at Undergrowth Scrounger:
> 
> **FAIL: Missing reminder text for custom mechanic**
> The card uses the custom mechanic "salvage 3" but lacks the required reminder text. According to your instructions, I should flag missing reminder text for custom mechanics. The oracle text should read:
> "When ~ dies, salvage 3. (Look at the top 3 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"
> 
> **WARN: Keywords field inconsistency**
> The "Keywords" field lists "Salvage" but salvage isn't actually a keyword ability on this card - it's a keyword action triggered by the death trigger. This appears to be a metadata formatting issue rather than a card design problem, but worth noting for consistency.
> 
> **Design Assessment - PASS:**
> - **Templating**: The trigger templating follows standard MTG format correctly
> - **Balance**: A 2/1 for {1}{G} that provides card advantage when it dies is reasonable at common, comparable to cards like Elvish Visionary or Farhaven Elf
> - **Color pie**: Green gets artifact tutoring/filtering (see Sylvan Scrying, Oath of Nissa) and death triggers, so this fits
> - **Design coherence**: Clean, focused design that supports the set's artifact theme
> - **No keyword collisions**: "Salvage" was properly renamed to avoid the existing "Scavenge" keyword
> 
> The core card design is solid once the reminder text is added.

**Pointed questions response** (summary):

> Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?
> 
> **NO** - The card only has salvage, which triggers when it dies. There are no conflicting abilities.
> 
> Q2: Is reminder text present for all custom mechanics?
> 
> **NO** - The oracle text shows "When ~ dies, salvage 3." but there is no reminder text for salvage. The first use of salvage should include "(Look at the top 3 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"
> 
> **FAIL** - Custom mechanics must have reminder text on their first use.
> 
> Q3: If this card has a conditional, is that conditional actually meaningful?
> 
> **N/A** - This card has no conditionals.
> 
> Q4: Is the power level appropriate for its mana cost and rarity?
> 
> **YES** - A 2/1 for {1}{G} with a death trigger is reasonable at common. Compare to cards like Sakura-Tribe Elder or Elvish Visionary - the salvage 3 ability provides card selection value when it dies, which is appropriately costed.
> 
> Q5: Does this card try to do too many unrelated things?
> 
> **NO** - The card has a focused design: it's a creature that provides artifact card selection when it dies. This supports the set's artifact theme coherently.
> 
> Q6: If this card has variable effects, is the variability real?
> 
> **N/A** - The salvage value is fixed at 3, so there's no variable effect to evaluate.
> 
> Q7: Do any mechanic names collide with existing MTG keywords?
> 
> **NO** - The card uses "salvage" which correctly avoids the collision with MTG's existing "scavenge" keyword.
> 
> ... (3 more lines)

### Card 3: Protonium Archaeologist

**Human verdict**: FAIL
**Auto verdict**: FAIL (critique: FAIL, pointed: FAIL)

**Self-critique response** (summary):

> Looking at Protonium Archaeologist:
> 
> **FAIL: Missing reminder text for custom mechanic**
> The oracle text shows "salvage 4" but lacks the required reminder text. Based on the mechanic definition, it should read:
> "When ~ enters, salvage 4. *(Look at the top 4 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*"
> 
> **WARN: Keywords field inconsistency**
> The JSON lists "Salvage" in the keywords field, but salvage is a keyword action that appears in rules text, not an inherent keyword ability of the creature itself. This is similar to how creatures with "When ~ enters, scry 1" don't list "Scry" as a keyword.
> 
> **Balance Assessment: PASS**
> - 3 mana 1/4 with ETB effect is appropriately costed for uncommon
> - Cost reduction effect is narrow (artifacts only) and reasonable
> - Salvage 4 at uncommon fits the stated scaling guidelines
> - The combination creates good synergy without being oppressive
> 
> **Design Assessment: PASS**
> - Clean, focused design that supports the artifact theme
> - Two abilities work well together (find artifacts, then cast them cheaper)
> - Appropriate complexity for uncommon
> - No redundant or conflicting abilities
> 
> **Color Pie Assessment: PASS**
> - Blue gets card selection effects (salvage fits this)
> - Blue gets cost reduction for specific spell types
> - Scientist creature type fits blue's flavor
> 
> **Templating Assessment: PASS (aside from missing reminder text)**
> - Proper use of "~" notation
> - ETB trigger templating is correct
> - Cost reduction effect uses standard templating
> ... (2 more lines)

**Pointed questions response** (summary):

> **Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?**
> 
> NO. The card only has salvage, which triggers when it enters the battlefield. There are no conflicting abilities that would negate salvage or make it useless.
> 
> **Q2: Is reminder text present for all custom mechanics?**
> 
> NO. The oracle text shows "When ~ enters, salvage 4." but there is no reminder text following "salvage 4." The first use of the custom mechanic salvage should include reminder text: "salvage 4 (Look at the top 4 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"
> 
> FAIL - Missing required reminder text for custom mechanic.
> 
> **Q3: If this card has a conditional, is that conditional actually meaningful?**
> 
> N/A. This card has no conditional abilities or "if you X this turn" text.
> 
> **Q4: Is the power level appropriate for its mana cost and rarity?**
> 
> YES. A 1/4 body for 3 mana is below the curve, but it comes with salvage 4 (card selection/advantage) and a cost reduction effect for artifacts. This is comparable to cards like Renowned Weaponsmith or Etherium Sculptor. The power level seems appropriate for uncommon.
> 
> **Q5: Does this card try to do too many unrelated things?**
> 
> NO. The card has a focused artifact theme - it finds artifacts via salvage and makes artifact spells cheaper. Both abilities work toward the same goal of supporting artifact strategies.
> 
> **Q6: If this card has variable effects, is the variability real or false?**
> 
> N/A. This card has no variable damage or effects based on counts.
> 
> **Q7: Do any mechanic names collide with existing MTG keywords?**
> 
> NO. The card uses "salvage" which is distinct from the existing "scavenge" keyword. No collision exists.
> 
> ... (3 more lines)

### Card 4: Moktar Relic Hunter

**Human verdict**: FAIL
**Auto verdict**: FAIL (critique: FAIL, pointed: FAIL)

**Self-critique response** (summary):

> Looking at this card carefully:
> 
> **FAIL: Missing reminder text for custom mechanic**
> The oracle text contains "salvage 5" but lacks the required reminder text: "(Look at the top 5 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)" This is essential for custom mechanics.
> 
> **WARN: Templating inconsistency**
> The card name should use the full name "Moktar Relic Hunter" instead of the placeholder "~" in the oracle text. Standard templating would be "When Moktar Relic Hunter enters, salvage 5."
> 
> **Balance Assessment: Reasonable for uncommon**
> - 4-mana 3/3 baseline is below rate
> - Salvage 5 provides significant card selection value (uncommon-appropriate per design notes)
> - The pump ability requires artifact spell investment to get value
> - Overall power level seems appropriate for uncommon
> 
> **Design Assessment: Clean synergy**
> - Both abilities support the artifact theme coherently
> - No redundant effects or keyword nonbos
> - Salvage helps find artifacts, pump rewards casting them - good mechanical synergy
> 
> **Color Pie: Appropriate**
> - Green gets artifact tutoring/selection (see cards like Ancient Stirrings)
> - Conditional pump effects are in Green's wheelhouse
> - No violations detected
> 
> **No keyword naming collisions** - "Salvage" was specifically chosen to avoid the existing "Scavenge" keyword.
> 
> The core design is solid, but the missing reminder text is a critical templating error that must be fixed.

**Pointed questions response** (summary):

> Looking at the card:
> 
> **Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?**
> NO. The card has salvage (which triggers on entry) and an artifact spell trigger. Neither ability negates or interferes with the other.
> 
> **Q2: Is reminder text present for all custom mechanics?**
> NO. The oracle text shows "salvage 5" without any reminder text in parentheses following it. According to the rules, the first use of a custom mechanic should include reminder text.
> FAIL - Missing reminder text for salvage.
> 
> **Q3: If this card has a conditional, is that conditional actually meaningful?**
> NO. This card has no conditionals like "if you X this turn" - it has an ETB salvage trigger and a "whenever you cast" trigger, both of which are straightforward.
> 
> **Q4: Is the power level appropriate for its mana cost and rarity?**
> YES. A 4-mana 3/3 that digs 5 deep for an artifact and gets temporary pumps is reasonable for uncommon. Compare to cards like Solemn Simulacrum or similar value creatures at 4 mana - this is in the right ballpark.
> 
> **Q5: Does this card try to do too many unrelated things?**
> NO. The card has a focused artifact theme - it finds artifacts (salvage) and rewards you for casting them (+2/+2 pump). These abilities work together cohesively.
> 
> **Q6: If this card has variable effects, is the variability real or false?**
> NO. The salvage value is fixed at 5, and the +2/+2 pump is fixed. While these are constant values, they're not presenting false variability - they're just fixed effects.
> 
> **Q7: Do any mechanic names collide with existing MTG keywords?**
> NO. The card uses "salvage" which the design notes confirm was renamed from "scavenge" specifically to avoid collision with the existing MTG keyword.
> 
> **Q8: Does this card have irrelevant "enters tapped" effects?**
> NO. This card doesn't have "enters tapped" or similar effects that would be irrelevant to its card type.

### Card 5: Subsurface Expedition Leader

**Human verdict**: FAIL
**Auto verdict**: FAIL (critique: FAIL, pointed: FAIL)

**Self-critique response** (summary):

> Looking at this card design critically:
> 
> **FAIL: Missing reminder text for custom mechanics**
> The oracle text uses "salvage 6" and "salvage 3" but provides no reminder text. According to the mechanic definitions provided, salvage should have reminder text: "(Look at the top X cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)" This is essential for a custom mechanic, especially at rare where players need to understand what salvage does.
> 
> **FAIL: Incorrect templating for sorcery-speed restriction**
> The activated ability reads "{2}{W}, {T}: Salvage 3. Activate only as a sorcery." The correct MTG templating for sorcery-speed restrictions is "Activate only as a sorcery." placed at the end, which is done correctly here. However, the more standard templating would be "Activate this ability only any time you could cast a sorcery."
> 
> **WARN: Keywords field mismatch**
> The card lists "Salvage" in the keywords field, but salvage is a keyword action/ability that appears in rules text, not an inherent keyword like flying or trample. This appears to be a metadata formatting issue rather than a card design issue, but it's worth noting the inconsistency.
> 
> **Balance Assessment: PASS**
> For a rare 4-mana creature:
> - 3/4 body is reasonable but not impressive
> - ETB salvage 6 is significant value (looking at 6 cards for an artifact)
> - Activated ability provides repeatable value but requires mana investment and tapping
> - Compared to similar rare value engines, this seems appropriately costed
> 
> **Design Assessment: PASS**
> - Clear focus on artifact tutoring/filtering
> - ETB provides immediate value, activated ability provides ongoing value
> - Sorcery speed restriction prevents instant-speed abuse
> - Fits white's artifact synergy theme appropriately
> 
> **Color Pie: PASS**
> White getting artifact tutoring/filtering effects is within the color pie, especially in an artifact-focused set.
> 
> The primary issues are the missing reminder text (critical for custom mechanics) and minor templating preference. The card's fundamental design is sound.

**Pointed questions response** (summary):

> Looking at the card:
> 
> **Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?**
> NO - The salvage keyword is not negated by any other abilities. Both the ETB salvage and activated ability salvage function normally.
> 
> **Q2: Is reminder text present for all custom mechanics?**
> NO - The oracle text shows "When ~ enters, salvage 6." and "{2}{W}, {T}: Salvage 3. Activate only as a sorcery." There is no reminder text for salvage in parentheses following either use. FAIL - Custom mechanics need reminder text on first use.
> 
> **Q3: If this card has a conditional, is that conditional actually meaningful?**
> NO - This card has no conditionals like "if you X this turn."
> 
> **Q4: Is the power level appropriate for its mana cost and rarity?**
> YES - A 4-mana 3/4 that salvages 6 on entry and has a repeatable salvage 3 ability is reasonable for rare. Compare to cards like Ranger-Captain of Eos (4 mana, 3/3, tutors on ETB). The power level is appropriate.
> 
> **Q5: Does this card try to do too many unrelated things?**
> NO - The card has a focused design around the salvage mechanic. Both abilities work together to support an artifact-focused strategy.
> 
> **Q6: If this card has variable effects, is the variability real or false?**
> NO - This card doesn't have variable effects based on counts. The salvage numbers (6 and 3) are fixed.
> 
> **Q7: Do any mechanic names collide with existing MTG keywords?**
> NO - "Salvage" does not collide with existing MTG keywords. The mechanic notes correctly indicate it was renamed from "Scavenge" to avoid that collision.
> 
> **Q8: Does this card have irrelevant "enters tapped" effects?**
> NO - This card doesn't have "enters tapped" or similar effects that would be irrelevant for a creature.

### Card 6: Defective Labor Drone

**Human verdict**: PASS
**Auto verdict**: FAIL (critique: FAIL, pointed: PASS)

**Self-critique response** (summary):

> Looking at Defective Labor Drone:
> 
> **FAIL: Color pie violation**
> White does not get efficient aggressive artifact creatures, especially not a 2-mana 3/2. This statline and aggressive positioning belongs in red or black. White's artifact creatures are typically defensive, utility-focused, or have protective abilities. A 3/2 for 2 mana is an aggressive rate that conflicts with white's defensive nature in the artifact space.
> 
> **WARN: Naming inconsistency**
> The name "Defective Labor Drone" suggests this creature should have some kind of utility or work-related ability beyond just being an understatted beater. Labor drones typically perform tasks, not just attack. The name creates an expectation that isn't delivered on mechanically.
> 
> **WARN: Questionable balance for common**
> Even with malfunction 1, a 3/2 for {1}{W} is pushing the boundaries for common. While the enters-tapped drawback is real, this still becomes a very efficient threat once the counter is removed. For comparison, most 2-mana 3/2s at common have more significant drawbacks or are in more aggressive colors.
> 
> The card's biggest issue is the color pie violation - white simply doesn't get pushed aggressive artifact creatures like this. This belongs in red or possibly colorless rather than white.

**Pointed questions response** (summary):

> Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?
> 
> **NO.** The card has malfunction, which causes it to enter tapped, but this doesn't negate any other keywords since malfunction is the only keyword present.
> 
> Q2: Is reminder text present for all custom mechanics?
> 
> **YES.** The malfunction keyword has its reminder text present: "(This permanent enters tapped with 1 malfunction counter on it. At the beginning of your upkeep, remove a malfunction counter from it.)"
> 
> Q3: If this card has a conditional, is that conditional meaningful?
> 
> **N/A.** This card has no conditionals like "if you X this turn."
> 
> Q4: Is the power level appropriate for its mana cost and rarity?
> 
> **YES.** A 3/2 for {1}{W} at common would normally be above rate, but the malfunction drawback (entering tapped with a counter that must be removed over time) provides meaningful compensation. This is comparable to other enters-tapped creatures that get above-rate stats as compensation.
> 
> Q5: Does this card try to do too many unrelated things?
> 
> **NO.** The card has a single, focused purpose: it's a malfunction creature with above-rate stats to compensate for the tempo loss. Very clean design.
> 
> Q6: If this card has variable effects, is the variability real?
> 
> **N/A.** This card has no variable effects - malfunction 1 is a fixed value.
> 
> Q7: Do any mechanic names collide with existing MTG keywords?
> 
> **NO.** Malfunction does not collide with any existing MTG keywords. The design notes correctly indicate that problematic keywords like "Scavenge" and "Overload" were renamed to avoid collisions.
> 
> Q8: Does this card have irrelevant "enters tapped" effects?
> 
> ... (3 more lines)

### Card 7: Unstable Welding Unit

**Human verdict**: FAIL
**Auto verdict**: FAIL (critique: FAIL, pointed: WARN)

**Self-critique response** (summary):

> Looking at this card critically:
> 
> **FAIL - Keyword Nonbo**: Malfunction and haste create a direct contradiction. Malfunction explicitly states the permanent "enters tapped," while haste grants the ability to attack immediately upon entering. This is a fundamental nonbo where one keyword completely negates the benefit of the other on the turn the creature enters.
> 
> **WARN - Balance Concern**: A 4/2 haste creature for 3 mana is above the normal rate (compare to cards like Goblin Chainwhirler which needed additional upside to justify 3/3 first strike for 3). While malfunction is intended as a drawback, the haste becomes meaningless due to the enters-tapped clause, so you're essentially paying 3 mana for a 4/2 that's delayed by one turn. This seems pushed even with the tempo loss.
> 
> **WARN - Design Logic**: From a flavor/design perspective, it's odd that an "unstable" welding unit would have haste. The malfunction mechanic suggests something that needs time to come online, while haste suggests immediate readiness for action. These concepts feel thematically at odds.
> 
> The templating and reminder text for malfunction are correct, and there are no color pie violations (red gets haste and aggressive creatures). However, the keyword nonbo is a fundamental design flaw that makes this card dysfunctional as intended.

**Pointed questions response** (summary):

> Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?
> 
> **YES** - The card has haste but enters tapped due to malfunction 1. Since it enters tapped, haste cannot grant the ability to attack immediately, making haste functionally useless on the turn it enters. However, haste will become relevant once the malfunction counter is removed and the creature untaps normally.
> 
> Classification: **WARN** - This creates a nonbo that may confuse players, though haste does eventually become relevant.
> 
> Q2: Is reminder text present for all custom mechanics?
> 
> **YES** - The malfunction mechanic has its reminder text present: "(This permanent enters tapped with 1 malfunction counter on it. At the beginning of your upkeep, remove a malfunction counter from it.)"
> 
> Q3: Does this card have conditionals that are always true/false?
> 
> **NO** - This card has no conditional effects.
> 
> Q4: Is the power level appropriate for its mana cost and rarity?
> 
> **YES** - A 4/2 haste creature for 3 mana at common is above the normal rate (compare to cards like Goblin Heelcutter which is 2/3 for 4 mana), but the malfunction drawback compensates by forcing it to enter tapped, creating appropriate balance.
> 
> Q5: Does this card try to do too many unrelated things?
> 
> **NO** - The card has a focused design: it's an aggressive creature with malfunction as a drawback and haste as an upside. These abilities work together thematically.
> 
> Q6: Does this card have false variability?
> 
> **NO** - This card has no variable effects.
> 
> Q7: Do any mechanic names collide with existing MTG keywords?
> 
> **NO** - The card uses "malfunction" and "haste." Malfunction is a custom mechanic that doesn't collide with existing keywords, and haste is a legitimate existing MTG keyword.
> 
> ... (3 more lines)

### Card 8: Salvage Processing Matrix

**Human verdict**: WARN
**Auto verdict**: FAIL (critique: FAIL, pointed: WARN)

**Self-critique response** (summary):

> Looking at this card carefully:
> 
> **FAIL: Malfunction reminder text error**
> The reminder text states "At the beginning of your upkeep, remove a malfunction counter from it" but should say "At the beginning of your upkeep, remove a malfunction counter from it. When the last is removed, untap it." The untapping component is missing, which is crucial since malfunction cards enter tapped.
> 
> **FAIL: Salvage reminder text missing**
> The salvage ability on this card lacks reminder text entirely. According to the mechanic definitions, salvage should have reminder text: "(Look at the top 4 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"
> 
> **WARN: Triggered ability templating**
> The trigger "When the last malfunction counter is removed from ~" should more precisely read "When the last malfunction counter is removed from ~" - this is correct, but it's worth noting that this creates a dependency on understanding that malfunction counters can only be removed one at a time through the upkeep trigger, not in bulk.
> 
> **WARN: Design complexity**
> While not a rules violation, having a malfunction card that triggers salvage when malfunction ends creates a complex interaction chain that may be above the intended complexity level for uncommon, especially with salvage 4 (which is at the high end of uncommon scaling per the design notes).
> 
> The card's basic design is sound - it's an artifact that uses both primary mechanics appropriately, the mana cost and rarity seem reasonable for the effect, and there are no color pie violations since this is a colorless artifact with a blue mana cost.

**Pointed questions response** (summary):

> Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?
> 
> **NO** - The malfunction mechanic causes the artifact to enter tapped, but this artifact doesn't have any tap abilities, so entering tapped has no mechanical impact. However, this isn't about keywords negating each other - it's about the malfunction mechanic itself being potentially irrelevant on this card type.
> 
> Q2: Is reminder text present for all custom mechanics?
> 
> **YES** - Both malfunction and salvage have their reminder text present in the oracle text. Malfunction 2 is followed by "(This permanent enters tapped with 2 malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.)" and salvage 4 is followed by "(Look at the top 4 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"
> 
> Q3: If this card has a conditional, is that conditional meaningful?
> 
> **N/A** - This card has no conditionals like "if you X this turn."
> 
> Q4: Is the power level appropriate for its mana cost and rarity?
> 
> **YES** - At 4 mana total cost (3 generic + 1 blue, but delayed by 2 turns), getting to look at 4 cards and potentially draw an artifact is reasonable for uncommon. The delay makes it much weaker than immediate tutoring effects.
> 
> Q5: Does this card try to do too many unrelated things?
> 
> **NO** - The card has a focused design: it's a delayed artifact tutor. The malfunction provides the delay/drawback, and salvage provides the payoff. These work together thematically and mechanically.
> 
> Q6: If this card has variable effects, is the variability real or false?
> 
> **N/A** - The salvage 4 effect has a fixed value of 4, but this isn't false variability since there's no pretense that the number varies - it's simply a fixed effect.
> 
> Q7: Do any mechanic names collide with existing MTG keywords?
> 
> **NO** - The card uses "Malfunction" and "Salvage," neither of which are existing MTG keywords. The design notes specifically mention that "Salvage" was chosen to avoid collision with the existing "Scavenge" keyword.
> 
> Q8: Does this card have "enters tapped" effects that are irrelevant for the card type?
> 
> ... (1 more lines)

### Card 9: Rampaging Siege Engine

**Human verdict**: PASS
**Auto verdict**: PASS (critique: PASS, pointed: PASS)

**Self-critique response** (summary):

> Let me review this card systematically:
> 
> **Rules Text & Templating:**
> - Malfunction reminder text is correct and matches the definition
> - The triggered ability template "When the last malfunction counter is removed from ~" is correct
> - "~ deals 3 damage to any target" is proper current templating
> - Trample needs no reminder text at uncommon
> 
> **Balance Analysis:**
> - 6/4 trample for 5 mana is above the vanilla test (compare to Hill Giant at 3/3 for 4)
> - However, malfunction 2 creates significant tempo cost - enters tapped and stays tapped for 2 turns
> - The 3 damage trigger provides meaningful upside when it finally comes online
> - This falls within acceptable bounds for malfunction design philosophy
> 
> **Design Issues:**
> - Clean, focused design with synergistic abilities
> - Malfunction creates natural buildup to the damage trigger
> - Trample pairs well with the large body once active
> - No keyword nonbos or redundant conditionals
> 
> **Color Pie:**
> - Red gets large creatures, direct damage, trample, and artifacts/constructs
> - All abilities are in-pie for red
> 
> **Keyword Interactions:**
> - Malfunction and Trample have no problematic interactions
> - No naming collisions with existing MTG keywords
> 
> **Rarity Considerations:**
> - Uncommon complexity is appropriate
> ... (5 more lines)

**Pointed questions response** (summary):

> Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?
> 
> **NO.** Trample remains fully functional. While the creature enters tapped due to malfunction, trample will be active once the creature can attack (after malfunction counters are removed).
> 
> Q2: Is reminder text present for all custom mechanics?
> 
> **YES.** The malfunction reminder text is present: "(This permanent enters tapped with 2 malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.)"
> 
> Q3: If this card has a conditional, is that conditional actually meaningful?
> 
> **N/A.** This card has no conditionals of the form "if you X this turn."
> 
> Q4: Is the power level appropriate for its mana cost and rarity?
> 
> **YES.** A 6/4 trample for 5 mana at uncommon is reasonable, especially with the malfunction drawback that delays its impact by 2 turns. The triggered damage ability provides additional value but doesn't make it overpowered.
> 
> Q5: Does this card try to do too many unrelated things?
> 
> **NO.** The card has a focused design: it's a big trampler that's delayed by malfunction, with a flavor-appropriate "explosion" when it comes online. The abilities work together thematically and mechanically.
> 
> Q6: If this card has variable effects, is the variability real or false?
> 
> **N/A.** The damage is fixed at 3, not variable based on any count.
> 
> Q7: Do any mechanic names collide with existing MTG keywords?
> 
> **NO.** "Malfunction" and "Trample" do not collide with existing keywords. The design notes correctly renamed "Scavenge" to "Salvage" and "Overload" to "Overclock" to avoid collisions.
> 
> Q8: Does this card have irrelevant "enters tapped" effects?
> 
> ... (3 more lines)

### Card 10: Experimental Thought Engine

**Human verdict**: PASS
**Auto verdict**: FAIL (critique: FAIL, pointed: PASS)

**Self-critique response** (summary):

> Looking at Experimental Thought Engine:
> 
> **FAIL: Malfunction scaling violation**
> The design notes specify malfunction scaling as "1 at common, 2 at uncommon, 2-3 at rare/mythic." This rare card has malfunction 3, which violates the established scaling by using the maximum value when it should likely be at 2 for better gameplay flow.
> 
> **FAIL: Templating inconsistency**
> The oracle text shows "Malfunction 3" with full reminder text, but then lists "Malfunction" again in the keywords field. Either the reminder text should be present in oracle text OR the keyword should be listed separately, not both. Based on the mechanic definition requiring reminder text presence, the keywords field entry appears redundant.
> 
> **WARN: Design complexity concerns**
> This card has three different abilities that all interact with malfunction counters in different ways:
> 1. Enters with malfunction 3
> 2. Can remove counters as activated ability 
> 3. Draws cards when counters are removed
> 
> While synergistic, this creates a complex decision tree for a mechanic that's supposed to be straightforward. The activated ability also creates potential for immediate value extraction that undermines the intended tempo cost of malfunction.
> 
> **WARN: Balance evaluation**
> A 3/5 body for 4 mana is below rate, but the card-draw engine is quite powerful once online. The ability to accelerate malfunction counter removal while drawing cards could lead to explosive turns. However, the 3-turn natural delay and mana investment required may provide sufficient balancing.
> 
> The rules text is otherwise correctly templated and the abilities fit Blue's slice of the color pie (card draw, artifact manipulation).
> 
> **Classification: FAIL** (due to malfunction scaling violation and templating inconsistency)

**Pointed questions response** (summary):

> Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?
> 
> **NO.** Malfunction causes the card to enter tapped, but it's a creature that can eventually untap and attack/block, and it has a tap ability that becomes relevant once malfunction counters are removed. No abilities are negated.
> 
> Q2: Is reminder text present for all custom mechanics?
> 
> **YES.** Malfunction has reminder text present: "(This permanent enters tapped with 3 malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.)"
> 
> Q3: If this card has a conditional, is that conditional meaningful?
> 
> **N/A.** This card has no conditionals like "if you X this turn."
> 
> Q4: Is the power level appropriate for its mana cost and rarity?
> 
> **YES.** A 4-mana 3/5 that enters tapped is below rate initially, but the activated ability and card draw engine provide significant value once online. The malfunction drawback balances the powerful effects. This is appropriate for rare.
> 
> Q5: Does this card try to do too many unrelated things?
> 
> **NO.** The card has a focused design around malfunction counter manipulation and card draw. The activated ability removes malfunction counters (helping itself and other permanents), and the triggered ability rewards counter removal with card draw. All abilities work together coherently.
> 
> Q6: If this card has variable effects, is the variability real or false?
> 
> **N/A.** This card doesn't have variable damage or effects based on counts that could be false variability.
> 
> Q7: Do any mechanic names collide with existing MTG keywords?
> 
> **NO.** The card uses "Malfunction," which doesn't collide with any existing MTG keywords. The mechanic definitions show that "Salvage" and "Overclock" were specifically renamed to avoid collisions with "Scavenge" and "Overload."
> 
> Q8: Does this card have irrelevant "enters tapped" effects?
> 
> ... (1 more lines)

### Card 11: Synaptic Overload

**Human verdict**: FAIL
**Auto verdict**: FAIL (critique: FAIL, pointed: FAIL)

**Self-critique response** (summary):

> Looking at this card design critically:
> 
> **FAIL: Incorrect Overclock Implementation**
> The card treats overclock as a cost ("As an additional cost to cast ~, overclock") but overclock is defined as a keyword action, not a cost. This is a fundamental templating error. The correct approach would be either:
> - Make it an activated ability: "{1}{U}: Overclock, then counter target spell. If you overclocked this turn, draw a card."
> - Or restructure as: "Overclock. Counter target spell. If you overclocked this turn, draw a card."
> 
> **FAIL: Rarity Violation**
> Overclock is explicitly defined as "rare+ only (complexity 3). Should NOT appear at common." This card is uncommon, violating the design constraints for the mechanic.
> 
> **WARN: Tracking Complexity**
> The conditional "If you overclocked this turn" requires players to track whether they've performed this action during the turn, adding memory complexity. While not impossible to track, it's additional cognitive load that should be considered carefully.
> 
> **WARN: Color Pie Stretch**
> While blue gets counterspells and card draw, the explosive "play cards from exile until end of turn" aspect of overclock feels more red than blue. The combination pushes blue's slice of the color pie, though it's not a hard violation.
> 
> **Balance Assessment: Reasonable**
> At the correct rarity (rare), a 2-mana counterspell that draws a card would be reasonable given the significant cost of exiling 3 cards. The power level seems appropriate for rare.
> 
> **Classification: FAIL** - The incorrect overclock implementation and rarity violation are both serious issues that must be fixed before this card could ship.

**Pointed questions response** (summary):

> **Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?**
> 
> NO. This is an instant spell, so there are no keyword interactions that could be negated by other abilities.
> 
> **Q2: Is reminder text present for all custom mechanics?**
> 
> YES. The oracle text shows "overclock. (Exile the top three cards of your library. You may play them until end of turn.)" - the reminder text is present inline for the custom overclock mechanic.
> 
> **Q3: If this card has a conditional, is that conditional actually meaningful?**
> 
> NO. The conditional "If you overclocked this turn" is not meaningful because overclock is listed as an additional cost to cast this spell. Since you must pay all costs to cast the spell, you will always have overclocked this turn when the spell resolves, making the condition always true and the text redundant. **FAIL** - The conditional should either be removed or the overclock should not be a mandatory additional cost.
> 
> **Q4: Is the power level appropriate for its mana cost and rarity?**
> 
> NO. At {1}{U} for an unconditional Counterspell plus card draw plus the value of overclocking 3 cards, this is significantly above rate. Compare to Counterspell at {U}{U}, or Negate at {1}{U} (which only counters noncreature spells). This does all of that plus draws a card plus gives access to 3 exiled cards. **FAIL** - Severely undercosted for the effect package.
> 
> **Q5: Does this card try to do too many unrelated things?**
> 
> YES. The card combines counterspell effects, card draw, and impulse card advantage (overclock) - three different types of effects that don't synergize meaningfully. **WARN** - This feels like kitchen sink design.
> 
> **Q6: If this card has variable effects, is the variability real?**
> 
> NO. There are no variable effects on this card - it's a fixed counterspell with fixed card draw.
> 
> **Q7: Do any mechanic names collide with existing MTG keywords?**
> 
> NO. The card uses "overclock" which does not collide with existing MTG keywords (the mechanic notes correctly identify that "overload" would have been a collision).
> 
> **Q8: Does this card have irrelevant "enters tapped" effects?**
> 
> ... (1 more lines)

### Card 12: Jury-Rigged Berserker

**Human verdict**: FAIL
**Auto verdict**: FAIL (critique: FAIL, pointed: FAIL)

**Self-critique response** (summary):

> Looking at this card critically:
> 
> **FAIL: Missing reminder text for custom mechanic**
> The card references "overclocked" in its oracle text, which refers to the custom keyword action "Overclock." Per your instructions, custom mechanics must have reminder text in the oracle_text. The card should include: "(Overclock: Exile the top three cards of your library. You may play them until end of turn.)"
> 
> **WARN: Keyword field inconsistency** 
> The Keywords field lists "Overclock" but the oracle text doesn't actually grant the creature the Overclock ability - it only cares about whether you've overclocked this turn. This creates a disconnect between the metadata and the actual card function.
> 
> **WARN: Rarity/complexity mismatch**
> Per the design notes, Overclock is "rare+ only (complexity 3)" and "should NOT appear at common." While this is uncommon (not common), having an uncommon that references a rare+ mechanic creates limited format issues where players may open this card but have very few ways to actually trigger its ability.
> 
> **WARN: Parasitic design**
> The card's primary ability only functions if you have access to Overclock effects, making it quite narrow. In limited formats where Overclock appears infrequently, this becomes a vanilla 2/2 haste for {2}{R} most of the time, which is below rate.
> 
> The oracle text templating is otherwise correct - "if you overclocked this turn" follows proper MTG templating for tracking actions taken during a turn.
> 
> **Classification: FAIL** due to the missing reminder text requirement.

**Pointed questions response** (summary):

> Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?
> 
> **NO** - Haste is fully functional. The card doesn't enter tapped or have any other abilities that would negate haste.
> 
> Q2: Is reminder text present for all custom mechanics in the oracle_text field?
> 
> **NO** - The oracle text shows "Whenever ~ attacks, if you overclocked this turn" but there is no reminder text for "overclocked." The overclock mechanic should have its reminder text the first time it appears. **FAIL** - Missing reminder text for custom mechanic.
> 
> Q3: If this card has a conditional, is that conditional actually meaningful?
> 
> **YES** - The condition "if you overclocked this turn" is meaningful because overclock is a separate action you choose to take, not tied to playing this creature. You could attack without having overclocked, making the condition genuinely conditional.
> 
> Q4: Is the power level appropriate for its mana cost and rarity?
> 
> **YES** - A 2/2 haste for 3 mana is below rate by itself. The conditional +3/+0 and trample requires additional investment (overclocking), making this appropriately costed for uncommon.
> 
> Q5: Does this card try to do too many unrelated things?
> 
> **NO** - The card has a focused aggressive theme: haste for immediate pressure, then a reward for overclocking that enhances its combat ability. The abilities work together cohesively.
> 
> Q6: Is the variability real or does it always resolve to the same fixed value?
> 
> **YES** - The variability is real. The +3/+0 and trample bonus only applies if you overclocked this turn, which is a choice you make independently of playing this creature.
> 
> Q7: Do any mechanic names collide with existing MTG keywords?
> 
> **NO** - "Overclock" does not collide with existing MTG keywords. The design notes correctly mention avoiding "Overload" which would have been a collision.
> 
> Q8: Does this card have irrelevant "enters tapped" effects?
> 
> ... (1 more lines)

### Card 13: Vivisector Prime

**Human verdict**: PASS
**Auto verdict**: FAIL (critique: FAIL, pointed: FAIL)

**Self-critique response** (summary):

> Looking at this card carefully:
> 
> **FAIL: Reminder text missing for custom mechanic**
> The oracle text uses "overclock" but doesn't include the reminder text. According to the mechanic definition, overclock should have reminder text: "(Exile the top three cards of your library. You may play them until end of turn.)" The oracle text should read:
> "Whenever you overclock (exile the top three cards of your library, you may play them until end of turn), each opponent loses 2 life and you gain 2 life."
> 
> **FAIL: Templating error in triggered ability**
> The parenthetical explanation in the middle of the ability is incorrect templating. The reminder text should come after the ability name, not embedded within the trigger condition. The correct templating would be the fix mentioned above.
> 
> **WARN: Potential balance concern**
> A 3/3 deathtouch for 4 mana with two relevant abilities seems pushed, even at rare. The activated ability essentially costs 3 mana for "draw up to 3 cards and gain 6 life in multiplayer" (assuming the triggered ability fires), which is very strong. However, overclock does exile the cards rather than putting them in hand, and there's risk of whiffing, so this may be acceptable at rare.
> 
> **WARN: Minor design redundancy**
> Having both the keyword "Overclock" listed and the activated ability that grants overclock creates slight redundancy in the keywords field, though this doesn't affect the printed card.
> 
> The color pie placement (black getting life drain triggers and activated abilities) is appropriate, and there are no keyword naming collisions.
> 
> **Verdict: FAIL** - The reminder text issue must be fixed before this card can ship.

**Pointed questions response** (summary):

> Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?
> 
> **NO.** Deathtouch works normally on this 3/3 creature. The overclock ability doesn't interfere with deathtouch functionality.
> 
> Q2: Is reminder text present for all custom mechanics (salvage, malfunction, overclock)?
> 
> **NO.** The oracle text shows "Whenever you overclock" but overclock has no reminder text. According to the rules, the first use of overclock should include "(exile the top three cards of your library, you may play them until end of turn)." **FAIL** - Custom mechanics need reminder text on first use.
> 
> Q3: If this card has a conditional ("if you X this turn"), is that conditional actually meaningful?
> 
> **YES.** The trigger "Whenever you overclock" is meaningful because overclock can happen or not happen - you choose whether to activate the {3}{B} ability, and other cards could also cause overclock.
> 
> Q4: Is the power level appropriate for its mana cost and rarity?
> 
> **YES.** A 4-mana 3/3 with deathtouch is reasonable baseline (compare Gifted Aetherborn at 2 mana 2/3 deathtouch). The overclock synergy and life drain effect justify the rare slot without being overpowered.
> 
> Q5: Does this card try to do too many unrelated things (kitchen sink design)?
> 
> **NO.** The card has a focused design - it's built around the overclock mechanic with deathtouch as a combat keyword. The abilities work together thematically and mechanically.
> 
> Q6: If this card has variable damage or variable effects based on a count, is the variability real?
> 
> **YES.** The life loss/gain effect has real variability - it only happens when you overclock, which is optional and costs mana. You might overclock 0, 1, or multiple times per turn.
> 
> Q7: Do any mechanic names on this card collide with existing MTG keywords?
> 
> **NO.** The card uses "overclock" which correctly avoids collision with the existing "overload" keyword from Return to Ravnica.
> 
> Q8: Does this card have "enters tapped" or similar effects that are irrelevant for the card type?
> 
> ... (1 more lines)

### Card 14: Cascade Protocol

**Human verdict**: FAIL
**Auto verdict**: FAIL (critique: FAIL, pointed: WARN)

**Self-critique response** (summary):

> Looking at this card critically:
> 
> **FAIL: Oracle text templating error**
> The oracle text says "Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)" This templating is incorrect. The reminder text should appear after EACH instance of the keyword, not just once at the end. It should read:
> 
> "Overclock. (Exile the top three cards of your library. You may play them until end of turn.) Then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)"
> 
> **FAIL: Pronoun reference ambiguity**
> The text "~ deals 2 damage to any target for each card exiled with ~ this way" has an unclear pronoun reference. "This way" could refer to either overclock instance or both. The templating should be more explicit, such as "~ deals 2 damage to any target for each card exiled by ~" or specify the total count more clearly.
> 
> **WARN: High variance/complexity for rare**
> This card exiles 6 cards total and creates a very swingy effect. While the damage scaling (potentially 12 damage) provides a meaningful floor, the combination of double keyword usage plus damage calculation plus temporary card access creates significant cognitive load that pushes complexity boundaries even for rare.
> 
> **WARN: Mana cost efficiency question**
> At {3}{R}{R}, this provides access to 6 cards until end of turn plus guaranteed damage. Compared to similar red card advantage spells, this seems potentially undercosted given the immediate impact and card selection, though the exile risk provides some balance.
> 
> The templating issues are clear failures that must be fixed before this card could ship.

**Pointed questions response** (summary):

> Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?
> 
> **NO.** This is a sorcery with overclock - there are no conflicting abilities that would negate each other.
> 
> Q2: Is reminder text present for all custom mechanics?
> 
> **YES.** Overclock appears with its reminder text: "(Exile the top three cards of your library. You may play them until end of turn.)"
> 
> Q3: If this card has a conditional, is that conditional actually meaningful?
> 
> **NO.** This card has no conditionals - it's a straightforward effect that overclocks twice then deals damage based on cards exiled.
> 
> Q4: Is the power level appropriate for its mana cost and rarity?
> 
> **YES.** At 5 mana, this exiles 6 cards (potentially giving you 6 cards to play until end of turn) and deals 12 damage to any target. While powerful, the high mana cost, rarity (rare), and risk of exiling cards you can't use this turn provides reasonable balance. Compare to expensive red burn/card advantage spells.
> 
> Q5: Does this card try to do too many unrelated things?
> 
> **NO.** The card has a focused design: overclock for card advantage/velocity, with damage that scales directly off the overclocking. The damage and card exile are thematically and mechanically linked.
> 
> Q6: Is the variability real or false?
> 
> **NO.** The variability is false - overclock always exiles exactly 3 cards, and this does it twice, so it always exiles exactly 6 cards and always deals exactly 12 damage. The "for each card exiled" text creates an illusion of variability where none exists.
> 
> **WARN:** False variability in templating - the damage will always be exactly 12, so the variable wording is misleading.
> 
> Q7: Do any mechanic names collide with existing MTG keywords?
> 
> **NO.** The card uses "Overclock" which was specifically renamed from "Overload" to avoid the collision with the existing Return to Ravnica keyword.
> 
> ... (3 more lines)

### Card 15: Archscientist Vex, the Unbound

**Human verdict**: WARN
**Auto verdict**: FAIL (critique: FAIL, pointed: PASS)

**Self-critique response** (summary):

> Looking at this card critically, I've identified several issues:
> 
> **FAIL: Reminder text incorrectly placed in oracle text**
> The oracle text includes reminder text for overclock in parentheses: "(exile the top three cards of your library, you may play them until end of turn)". Reminder text should only appear in oracle_text for custom mechanics at common rarity. This is a mythic rare, so the reminder text should be removed from the oracle text.
> 
> **FAIL: Overclock appears in keywords field but card doesn't have overclock**
> The card has "overclock" listed in its keywords, but the card itself doesn't actually have the overclock ability. The card only references cards exiled "with overclock" - meaning OTHER sources of overclock. This is a fundamental disconnect between the keywords field and the actual card abilities.
> 
> **WARN: Potential templating inconsistency**
> The phrase "cards exiled with overclock" may need clarification. Standard Magic templating might prefer "cards exiled by overclock abilities" or similar to be more precise about the source of the exile.
> 
> **WARN: Complex design space interaction**
> The card creates a cost reduction and copy effect specifically for overclock-exiled cards, but doesn't provide its own overclock ability. This means the card is entirely dependent on other overclock sources to function, which could lead to awkward gameplay where a mythic legendary creature does nothing without specific support cards.
> 
> The card's individual abilities are appropriately costed and within the UR color pie (cost reduction, copying spells, flying), but the execution has significant templating and mechanical issues that need resolution.

**Pointed questions response** (summary):

> **Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?**
> 
> NO. Flying is not negated by any other abilities on the card. The overclock ability and spell-copying trigger work independently and don't interfere with flying.
> 
> **Q2: Is reminder text present for all custom mechanics (salvage, malfunction, overclock)?**
> 
> NO. The oracle text shows "Cards exiled with overclock (exile the top three cards of your library, you may play them until end of turn)" - this includes the reminder text for overclock inline. However, looking at the keywords field, this card doesn't actually use salvage or malfunction, only overclock and flying. The overclock reminder text IS present. PASS.
> 
> **Q3: If this card has a conditional, is that conditional actually meaningful?**
> 
> YES. The conditions "Cards exiled with overclock" and "Whenever you cast a spell exiled with overclock" are meaningful because you could exile cards with overclock from other sources, or cast spells that weren't exiled with overclock. The conditionals properly distinguish between different types of exiled cards.
> 
> **Q4: Is the power level appropriate for its mana cost and rarity?**
> 
> NO. At 4 mana for a 3/4 flying legendary creature with two powerful abilities, this seems appropriately costed for mythic rare. The cost reduction and spell copying are significant effects, but require setup (overclocking) and the body itself is reasonable for the cost. PASS.
> 
> **Q5: Does this card try to do too many unrelated things (kitchen sink design)?**
> 
> NO. The card has a focused design around the overclock mechanic - it reduces costs of overclocked spells and copies them. Flying fits as a reasonable mythic legendary creature ability. All abilities work together synergistically. PASS.
> 
> **Q6: If this card has variable damage or variable effects, is the variability real?**
> 
> N/A. This card doesn't have variable damage or effects based on counts. The effects are consistent - always {2} cost reduction, always copy spells.
> 
> **Q7: Do any mechanic names on this card collide with existing MTG keywords?**
> 
> NO. The card uses "overclock" which was specifically renamed to avoid collision with "overload" from Return to Ravnica. No naming collisions present. PASS.
> 
> **Q8: Does this card have "enters tapped" or similar effects that are irrelevant for the card type?**
> 
> ... (1 more lines)

---

## Pointed Questions Evaluation

| # | Question (abbreviated) | Caught Issues? | Recommendation |
|---|------------------------|----------------|----------------|
| Q1 | Keyword negated by other abilities? | (see detailed results) | KEEP |
| Q2 | Reminder text present for custom mechanics? | (see detailed results) | KEEP |
| Q3 | Conditional actually meaningful? | (see detailed results) | KEEP |
| Q4 | Power level appropriate for rarity? | (see detailed results) | KEEP |
| Q5 | Kitchen sink design? | (see detailed results) | KEEP |
| Q6 | False variability? | (see detailed results) | KEEP |
| Q7 | Mechanic name collision with existing MTG keywords? | (see detailed results) | KEEP |
| Q8 | Enters tapped irrelevant for card type? | (see detailed results) | KEEP |

---

## Overall Assessment

FAIL detection: **100%** (target >=70%) — **TARGET MET**

WARN detection: **50%** (target >=50%) — **TARGET MET**

The automated review pipeline meets both detection targets. Ready to proceed to integration in the card generation pipeline.