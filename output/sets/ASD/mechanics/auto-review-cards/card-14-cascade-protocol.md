# Card 14: Cascade Protocol

## Card Data

```json
{
  "name": "Cascade Protocol",
  "mana_cost": "{3}{R}{R}",
  "cmc": 5,
  "colors": [
    "R"
  ],
  "color_identity": [
    "R"
  ],
  "type_line": "Sorcery",
  "oracle_text": "Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)\n~ deals 2 damage to any target for each card exiled with ~ this way.",
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" �Final log, Research Station Gamma",
  "power": null,
  "toughness": null,
  "rarity": "rare",
  "keywords": [
    "Overclock"
  ],
  "design_notes": "Rare red sorcery that overclocks twice, guaranteeing 6 exiled cards and 12 damage. High mana cost balances the powerful effect. Gives you card selection while dealing significant damage, fitting red's aggressive nature.",
  "_mechanic": "overclock",
  "_scores": {
    "rules_text": 5.0,
    "flavor_fit": 4.0,
    "balance": 5.0,
    "creativity": 4.5,
    "overall": 4.62,
    "issues": []
  }
}
```

---

## Ground Truth (Human Review)

**Status**: FAIL
**Issues**: false_variability, above_rate_balance, kitchen_sink

---

## Phase 1: Self-Critique

**AI Verdict**: FAIL
**Issues extracted** (4):

- [FAIL] templating: Reminder text should appear after each instance of overclock, not just once at the end.
- [FAIL] templating: Pronoun reference 'this way' is ambiguous and unclear which overclock instance(s) it refers to.
- [WARN] other: High variance and complexity from double keyword usage plus damage calculation creates significant cognitive load.
- [WARN] above_rate_balance: Mana cost may be too efficient for accessing 6 cards plus guaranteed damage at {3}{R}{R}.

### Full Self-Critique Conversation

Looking at this card critically:

**FAIL: Oracle text templating error**
The oracle text says "Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)" This templating is incorrect. The reminder text should appear after EACH instance of the keyword, not just once at the end. It should read:

"Overclock. (Exile the top three cards of your library. You may play them until end of turn.) Then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)"

**FAIL: Pronoun reference ambiguity**
The text "~ deals 2 damage to any target for each card exiled with ~ this way" has an unclear pronoun reference. "This way" could refer to either overclock instance or both. The templating should be more explicit, such as "~ deals 2 damage to any target for each card exiled by ~" or specify the total count more clearly.

**WARN: High variance/complexity for rare**
This card exiles 6 cards total and creates a very swingy effect. While the damage scaling (potentially 12 damage) provides a meaningful floor, the combination of double keyword usage plus damage calculation plus temporary card access creates significant cognitive load that pushes complexity boundaries even for rare.

**WARN: Mana cost efficiency question**
At {3}{R}{R}, this provides access to 6 cards until end of turn plus guaranteed damage. Compared to similar red card advantage spells, this seems potentially undercosted given the immediate impact and card selection, though the exile risk provides some balance.

The templating issues are clear failures that must be fixed before this card could ship.

---

## Phase 2: Pointed Questions

**AI Verdict**: WARN
**Issues extracted** (1):

- [WARN] false_variability: The damage will always be exactly 12, so the variable wording 'for each card exiled this way' is misleading.

### Full Pointed Questions Conversation

Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?

**NO.** This is a sorcery with overclock - there are no conflicting abilities that would negate each other.

Q2: Is reminder text present for all custom mechanics?

**YES.** Overclock appears with its reminder text: "(Exile the top three cards of your library. You may play them until end of turn.)"

Q3: If this card has a conditional, is that conditional actually meaningful?

**NO.** This card has no conditionals - it's a straightforward effect that overclocks twice then deals damage based on cards exiled.

Q4: Is the power level appropriate for its mana cost and rarity?

**YES.** At 5 mana, this exiles 6 cards (potentially giving you 6 cards to play until end of turn) and deals 12 damage to any target. While powerful, the high mana cost, rarity (rare), and risk of exiling cards you can't use this turn provides reasonable balance. Compare to expensive red burn/card advantage spells.

Q5: Does this card try to do too many unrelated things?

**NO.** The card has a focused design: overclock for card advantage/velocity, with damage that scales directly off the overclocking. The damage and card exile are thematically and mechanically linked.

Q6: Is the variability real or false?

**NO.** The variability is false - overclock always exiles exactly 3 cards, and this does it twice, so it always exiles exactly 6 cards and always deals exactly 12 damage. The "for each card exiled" text creates an illusion of variability where none exists.

**WARN:** False variability in templating - the damage will always be exactly 12, so the variable wording is misleading.

Q7: Do any mechanic names collide with existing MTG keywords?

**NO.** The card uses "Overclock" which was specifically renamed from "Overload" to avoid the collision with the existing Return to Ravnica keyword.

Q8: Does this card have irrelevant "enters tapped" effects?

**NO.** This is a sorcery, so enters tapped effects would not be relevant or present.

---

## Final Result

**Final Verdict**: FAIL
**Human Verdict**: FAIL
**Match**: YES

**All issues** (5):

- [FAIL] templating: Reminder text should appear after each instance of overclock, not just once at the end.
- [WARN] false_variability: The damage will always be exactly 12, so the variable wording 'for each card exiled this way' is misleading.
- [WARN] other: High variance and complexity from double keyword usage plus damage calculation creates significant cognitive load.
- [WARN] above_rate_balance: Mana cost may be too efficient for accessing 6 cards plus guaranteed damage at {3}{R}{R}.
- [FAIL] templating: Pronoun reference 'this way' is ambiguous and unclear which overclock instance(s) it refers to.