# Card 1: Denethix Salvage Crew

## Card Data

```json
{
  "name": "Denethix Salvage Crew",
  "mana_cost": "{2}{W}",
  "cmc": 3,
  "colors": [
    "W"
  ],
  "color_identity": [
    "W"
  ],
  "type_line": "Creature � Human Soldier",
  "oracle_text": "When ~ enters, salvage 2. (Look at the top 2 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)",
  "flavor_text": "\"The city pays us by the pound for metal scraps. They don't ask where we found the blood-soaked ones.\"",
  "power": "2",
  "toughness": "2",
  "rarity": "common",
  "keywords": [
    "Salvage"
  ],
  "design_notes": "Simple common creature with ETB salvage trigger. The 2/2 for 3 body is slightly below rate to account for the card advantage potential. White gets salvage as it represents organized salvage operations and finding useful tools.",
  "_mechanic": "salvage",
  "_scores": {
    "rules_text": 5.0,
    "flavor_fit": 5.0,
    "balance": 5.0,
    "creativity": 4.8,
    "overall": 4.94,
    "issues": []
  }
}
```

---

## Ground Truth (Human Review)

**Status**: PASS
**Issues**: S1:keyword_collision

---

## Phase 1: Self-Critique

**AI Verdict**: FAIL
**Issues extracted** (2):

- [FAIL] templating: Salvage is templated as a keyword action in oracle text instead of as a keyword ability.
- [FAIL] missing_reminder_text: Oracle text lacks required reminder text for the custom salvage mechanic.

### Full Self-Critique Conversation

Looking at Denethix Salvage Crew:

**FAIL - Incorrect Salvage Templating**: The oracle text shows "salvage 2" as a keyword action, but based on the mechanic definition, salvage should be templated as a keyword ability that appears in the keywords line, not as an action in the rules text. 

The correct templating should be either:
- Oracle text: "Salvage 2" (as a keyword ability) with full reminder text
- Keywords line: "Salvage 2"

The current templating "When ~ enters, salvage 2" treats it like an activated or triggered ability rather than a keyword ability.

**FAIL - Missing Reminder Text**: The oracle text lacks the required reminder text for the custom salvage mechanic. According to the mechanic definition, salvage should have reminder text: "(Look at the top 2 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"

**WARN - Keywords Field Inconsistency**: The keywords field lists "Salvage" but the oracle text shows "salvage 2". There should be consistency - if salvage is a keyword ability, the keywords field should show "Salvage 2".

The card's power/toughness (2/2 for 2W), rarity (common), and color pie placement (white getting card selection/tutoring effects) are all reasonable. The salvage value of 2 matches the common scaling guidelines (2-3 at common).

**Verdict: FAIL** - Must fix templating and add reminder text before shipping.

---

## Phase 2: Pointed Questions

**AI Verdict**: PASS
**Issues extracted** (0):

- None

### Full Pointed Questions Conversation

Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?

**NO** - The card only has salvage, which triggers when it enters and doesn't conflict with being a 2/2 creature.

Q2: Is reminder text present for all custom mechanics?

**YES** - Salvage has reminder text present in the oracle text: "(Look at the top 2 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"

Q3: If this card has a conditional, is that conditional actually meaningful?

**N/A** - This card has no conditionals ("if you X this turn" clauses).

Q4: Is the power level appropriate for its mana cost and rarity?

**YES** - A 2/2 for {2}{W} with card selection that finds artifacts is reasonable at common. Compare to cards like Veteran Armorer (2/2 for {2}{W} with no upside) or Squadron Hawk (1/1 flyer that tutors). The salvage effect is modest card selection, not card advantage, making this appropriately powered.

Q5: Does this card try to do too many unrelated things?

**NO** - The card has a focused design: it's a creature that helps find artifacts through salvage. The abilities are thematically and mechanically coherent.

Q6: If this card has variable effects, is the variability real or false?

**N/A** - While salvage looks at a variable number of cards (2 in this case), that number is fixed for this specific card, so there's no false variability issue here.

Q7: Do any mechanic names collide with existing MTG keywords?

**NO** - The card uses "salvage," which correctly avoids collision with the existing "scavenge" keyword from Return to Ravnica.

Q8: Does this card have irrelevant "enters tapped" effects?

**NO** - This card doesn't have "enters tapped" or similar effects.

**Overall Assessment: PASS** - No issues found.

---

## Final Result

**Final Verdict**: FAIL
**Human Verdict**: PASS
**Match**: NO

**All issues** (2):

- [FAIL] missing_reminder_text: Oracle text lacks required reminder text for the custom salvage mechanic.
- [FAIL] templating: Salvage is templated as a keyword action in oracle text instead of as a keyword ability.