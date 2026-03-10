# Card 11: Synaptic Overload

## Card Data

```json
{
  "name": "Synaptic Overload",
  "mana_cost": "{1}{U}",
  "cmc": 2,
  "colors": [
    "U"
  ],
  "color_identity": [
    "U"
  ],
  "type_line": "Instant",
  "oracle_text": "As an additional cost to cast ~, overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nCounter target spell. If you overclocked this turn, draw a card.",
  "flavor_text": "\"The prototype neural interface worked perfectly. The subject's brain, however, did not.\" �Dr. Malleus, Cult of Science",
  "power": null,
  "toughness": null,
  "rarity": "uncommon",
  "keywords": [
    "Overclock"
  ],
  "design_notes": "Uncommon blue instant using overclock as additional cost with conditional bonus. The base effect (counter spell) is fair for 1U, but the overclock cost gives you card selection plus a bonus card draw if you've already overclocked. Risk/reward of exiling cards balanced against powerful effects.",
  "_mechanic": "overclock",
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

**Status**: FAIL
**Issues**: redundant_conditional, above_rate_balance, kitchen_sink

---

## Phase 1: Self-Critique

**AI Verdict**: FAIL
**Issues extracted** (4):

- [FAIL] templating: Overclock is incorrectly implemented as a cost when it should be a keyword action.
- [FAIL] other: Card violates rarity constraints by using overclock at uncommon when it's defined as rare+ only.
- [WARN] other: Requires tracking whether overclock was used this turn, adding memory complexity.
- [WARN] color_pie: The explosive exile-and-play aspect of overclock pushes blue's color pie boundaries.

### Full Self-Critique Conversation

Looking at this card design critically:

**FAIL: Incorrect Overclock Implementation**
The card treats overclock as a cost ("As an additional cost to cast ~, overclock") but overclock is defined as a keyword action, not a cost. This is a fundamental templating error. The correct approach would be either:
- Make it an activated ability: "{1}{U}: Overclock, then counter target spell. If you overclocked this turn, draw a card."
- Or restructure as: "Overclock. Counter target spell. If you overclocked this turn, draw a card."

**FAIL: Rarity Violation**
Overclock is explicitly defined as "rare+ only (complexity 3). Should NOT appear at common." This card is uncommon, violating the design constraints for the mechanic.

**WARN: Tracking Complexity**
The conditional "If you overclocked this turn" requires players to track whether they've performed this action during the turn, adding memory complexity. While not impossible to track, it's additional cognitive load that should be considered carefully.

**WARN: Color Pie Stretch**
While blue gets counterspells and card draw, the explosive "play cards from exile until end of turn" aspect of overclock feels more red than blue. The combination pushes blue's slice of the color pie, though it's not a hard violation.

**Balance Assessment: Reasonable**
At the correct rarity (rare), a 2-mana counterspell that draws a card would be reasonable given the significant cost of exiling 3 cards. The power level seems appropriate for rare.

**Classification: FAIL** - The incorrect overclock implementation and rarity violation are both serious issues that must be fixed before this card could ship.

---

## Phase 2: Pointed Questions

**AI Verdict**: FAIL
**Issues extracted** (3):

- [FAIL] redundant_conditional: The conditional 'If you overclocked this turn' is always true since overclock is a mandatory additional cost to cast the spell.
- [FAIL] above_rate_balance: At {1}{U} this provides an unconditional counterspell plus card draw plus overclock value, which is severely undercosted compared to existing effects.
- [WARN] kitchen_sink: The card combines counterspell effects, card draw, and impulse card advantage without meaningful synergy.

### Full Pointed Questions Conversation

**Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?**

NO. This is an instant spell, so there are no keyword interactions that could be negated by other abilities.

**Q2: Is reminder text present for all custom mechanics?**

YES. The oracle text shows "overclock. (Exile the top three cards of your library. You may play them until end of turn.)" - the reminder text is present inline for the custom overclock mechanic.

**Q3: If this card has a conditional, is that conditional actually meaningful?**

NO. The conditional "If you overclocked this turn" is not meaningful because overclock is listed as an additional cost to cast this spell. Since you must pay all costs to cast the spell, you will always have overclocked this turn when the spell resolves, making the condition always true and the text redundant. **FAIL** - The conditional should either be removed or the overclock should not be a mandatory additional cost.

**Q4: Is the power level appropriate for its mana cost and rarity?**

NO. At {1}{U} for an unconditional Counterspell plus card draw plus the value of overclocking 3 cards, this is significantly above rate. Compare to Counterspell at {U}{U}, or Negate at {1}{U} (which only counters noncreature spells). This does all of that plus draws a card plus gives access to 3 exiled cards. **FAIL** - Severely undercosted for the effect package.

**Q5: Does this card try to do too many unrelated things?**

YES. The card combines counterspell effects, card draw, and impulse card advantage (overclock) - three different types of effects that don't synergize meaningfully. **WARN** - This feels like kitchen sink design.

**Q6: If this card has variable effects, is the variability real?**

NO. There are no variable effects on this card - it's a fixed counterspell with fixed card draw.

**Q7: Do any mechanic names collide with existing MTG keywords?**

NO. The card uses "overclock" which does not collide with existing MTG keywords (the mechanic notes correctly identify that "overload" would have been a collision).

**Q8: Does this card have irrelevant "enters tapped" effects?**

NO. This is an instant spell, so enters tapped effects are not applicable.

---

## Final Result

**Final Verdict**: FAIL
**Human Verdict**: FAIL
**Match**: YES

**All issues** (7):

- [FAIL] templating: Overclock is incorrectly implemented as a cost when it should be a keyword action.
- [WARN] color_pie: The explosive exile-and-play aspect of overclock pushes blue's color pie boundaries.
- [FAIL] above_rate_balance: At {1}{U} this provides an unconditional counterspell plus card draw plus overclock value, which is severely undercosted compared to existing effects.
- [FAIL] redundant_conditional: The conditional 'If you overclocked this turn' is always true since overclock is a mandatory additional cost to cast the spell.
- [FAIL] other: Card violates rarity constraints by using overclock at uncommon when it's defined as rare+ only.
- [WARN] other: Requires tracking whether overclock was used this turn, adding memory complexity.
- [WARN] kitchen_sink: The card combines counterspell effects, card draw, and impulse card advantage without meaningful synergy.