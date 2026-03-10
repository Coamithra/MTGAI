# Card 12: Jury-Rigged Berserker

## Card Data

```json
{
  "name": "Jury-Rigged Berserker",
  "mana_cost": "{2}{R}",
  "cmc": 3,
  "colors": [
    "R"
  ],
  "color_identity": [
    "R"
  ],
  "type_line": "Creature � Human Soldier",
  "oracle_text": "Haste\nWhenever ~ attacks, if you overclocked this turn, ~ gets +3/+0 and gains trample until end of turn.",
  "flavor_text": "\"Sir, the combat stimulants are showing a 73% chance of catastrophic organ failure.\" \"Excellent. Deploy immediately.\"",
  "power": "2",
  "toughness": "2",
  "rarity": "uncommon",
  "keywords": [
    "Haste",
    "Overclock"
  ],
  "design_notes": "Uncommon red creature with conditional overclock bonus. Vanilla 2/2 haste for 3 is below rate, but becomes a 5/2 trampler if you overclock. Encourages building around overclock effects and rewards aggressive strategies.",
  "_mechanic": "overclock",
  "_scores": {
    "rules_text": 4.5,
    "flavor_fit": 4.0,
    "balance": 5.0,
    "creativity": 4.8,
    "overall": 4.56,
    "issues": [
      "Missing or incorrect overclock reminder text"
    ]
  }
}
```

---

## Ground Truth (Human Review)

**Status**: FAIL
**Issues**: missing_reminder_text

---

## Phase 1: Self-Critique

**AI Verdict**: FAIL
**Issues extracted** (3):

- [FAIL] missing_reminder_text: The card references 'overclocked' but is missing required reminder text for the custom Overclock mechanic.
- [WARN] above_rate_balance: The card creates limited format issues by referencing a rare+ mechanic at uncommon rarity, making it frequently a below-rate vanilla creature.
- [WARN] other: Parasitic design makes the card narrow and dependent on access to Overclock effects to function meaningfully.

### Full Self-Critique Conversation

Looking at this card critically:

**FAIL: Missing reminder text for custom mechanic**
The card references "overclocked" in its oracle text, which refers to the custom keyword action "Overclock." Per your instructions, custom mechanics must have reminder text in the oracle_text. The card should include: "(Overclock: Exile the top three cards of your library. You may play them until end of turn.)"

**WARN: Keyword field inconsistency** 
The Keywords field lists "Overclock" but the oracle text doesn't actually grant the creature the Overclock ability - it only cares about whether you've overclocked this turn. This creates a disconnect between the metadata and the actual card function.

**WARN: Rarity/complexity mismatch**
Per the design notes, Overclock is "rare+ only (complexity 3)" and "should NOT appear at common." While this is uncommon (not common), having an uncommon that references a rare+ mechanic creates limited format issues where players may open this card but have very few ways to actually trigger its ability.

**WARN: Parasitic design**
The card's primary ability only functions if you have access to Overclock effects, making it quite narrow. In limited formats where Overclock appears infrequently, this becomes a vanilla 2/2 haste for {2}{R} most of the time, which is below rate.

The oracle text templating is otherwise correct - "if you overclocked this turn" follows proper MTG templating for tracking actions taken during a turn.

**Classification: FAIL** due to the missing reminder text requirement.

---

## Phase 2: Pointed Questions

**AI Verdict**: FAIL
**Issues extracted** (1):

- [FAIL] missing_reminder_text: Missing reminder text for the custom mechanic 'overclocked'.

### Full Pointed Questions Conversation

Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?

**NO** - Haste is fully functional. The card doesn't enter tapped or have any other abilities that would negate haste.

Q2: Is reminder text present for all custom mechanics in the oracle_text field?

**NO** - The oracle text shows "Whenever ~ attacks, if you overclocked this turn" but there is no reminder text for "overclocked." The overclock mechanic should have its reminder text the first time it appears. **FAIL** - Missing reminder text for custom mechanic.

Q3: If this card has a conditional, is that conditional actually meaningful?

**YES** - The condition "if you overclocked this turn" is meaningful because overclock is a separate action you choose to take, not tied to playing this creature. You could attack without having overclocked, making the condition genuinely conditional.

Q4: Is the power level appropriate for its mana cost and rarity?

**YES** - A 2/2 haste for 3 mana is below rate by itself. The conditional +3/+0 and trample requires additional investment (overclocking), making this appropriately costed for uncommon.

Q5: Does this card try to do too many unrelated things?

**NO** - The card has a focused aggressive theme: haste for immediate pressure, then a reward for overclocking that enhances its combat ability. The abilities work together cohesively.

Q6: Is the variability real or does it always resolve to the same fixed value?

**YES** - The variability is real. The +3/+0 and trample bonus only applies if you overclocked this turn, which is a choice you make independently of playing this creature.

Q7: Do any mechanic names collide with existing MTG keywords?

**NO** - "Overclock" does not collide with existing MTG keywords. The design notes correctly mention avoiding "Overload" which would have been a collision.

Q8: Does this card have irrelevant "enters tapped" effects?

**NO** - This card doesn't have "enters tapped" or similar effects that would be irrelevant for a creature.

---

## Final Result

**Final Verdict**: FAIL
**Human Verdict**: FAIL
**Match**: YES

**All issues** (4):

- [WARN] above_rate_balance: The card creates limited format issues by referencing a rare+ mechanic at uncommon rarity, making it frequently a below-rate vanilla creature.
- [FAIL] missing_reminder_text: The card references 'overclocked' but is missing required reminder text for the custom Overclock mechanic.
- [FAIL] missing_reminder_text: Missing reminder text for the custom mechanic 'overclocked'.
- [WARN] other: Parasitic design makes the card narrow and dependent on access to Overclock effects to function meaningfully.