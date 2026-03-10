# Card 15: Archscientist Vex, the Unbound

## Card Data

```json
{
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "cmc": 4,
  "colors": [
    "U",
    "R"
  ],
  "color_identity": [
    "U",
    "R"
  ],
  "type_line": "Legendary Creature � Human Scientist",
  "oracle_text": "Flying\nCards exiled with overclock (exile the top three cards of your library, you may play them until end of turn) cost {2} less to cast.\nWhenever you cast a spell exiled with overclock, copy it. You may choose new targets for the copy.",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\"",
  "power": "3",
  "toughness": "4",
  "rarity": "mythic",
  "keywords": [
    "Flying",
    "Overclock"
  ],
  "design_notes": "Mythic legendary showcasing overclock as a build-around. Cost reduction makes overclocked cards more playable, while copying them provides explosive value. The copy effect works on any spell cast from overclock, creating powerful synergies. Splashy enough for mythic while being a clear overclock payoff.",
  "_mechanic": "overclock",
  "_scores": {
    "rules_text": 5.0,
    "flavor_fit": 5.0,
    "balance": 5.0,
    "creativity": 4.5,
    "overall": 4.88,
    "issues": []
  }
}
```

---

## Ground Truth (Human Review)

**Status**: WARN
**Issues**: flying_tacked_on

---

## Phase 1: Self-Critique

**AI Verdict**: FAIL
**Issues extracted** (2):

- [FAIL] missing_reminder_text: Reminder text for overclock appears in oracle text but should be removed at mythic rare.
- [WARN] templating: The phrase 'cards exiled with overclock' may need clarification to be more precise about the source of exile.

### Full Self-Critique Conversation

Looking at this card critically, I've identified several issues:

**FAIL: Reminder text incorrectly placed in oracle text**
The oracle text includes reminder text for overclock in parentheses: "(exile the top three cards of your library, you may play them until end of turn)". Reminder text should only appear in oracle_text for custom mechanics at common rarity. This is a mythic rare, so the reminder text should be removed from the oracle text.

**FAIL: Overclock appears in keywords field but card doesn't have overclock**
The card has "overclock" listed in its keywords, but the card itself doesn't actually have the overclock ability. The card only references cards exiled "with overclock" - meaning OTHER sources of overclock. This is a fundamental disconnect between the keywords field and the actual card abilities.

**WARN: Potential templating inconsistency**
The phrase "cards exiled with overclock" may need clarification. Standard Magic templating might prefer "cards exiled by overclock abilities" or similar to be more precise about the source of the exile.

**WARN: Complex design space interaction**
The card creates a cost reduction and copy effect specifically for overclock-exiled cards, but doesn't provide its own overclock ability. This means the card is entirely dependent on other overclock sources to function, which could lead to awkward gameplay where a mythic legendary creature does nothing without specific support cards.

The card's individual abilities are appropriately costed and within the UR color pie (cost reduction, copying spells, flying), but the execution has significant templating and mechanical issues that need resolution.

---

## Phase 2: Pointed Questions

**AI Verdict**: PASS
**Issues extracted** (0):

- None

### Full Pointed Questions Conversation

**Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?**

NO. Flying is not negated by any other abilities on the card. The overclock ability and spell-copying trigger work independently and don't interfere with flying.

**Q2: Is reminder text present for all custom mechanics (salvage, malfunction, overclock)?**

NO. The oracle text shows "Cards exiled with overclock (exile the top three cards of your library, you may play them until end of turn)" - this includes the reminder text for overclock inline. However, looking at the keywords field, this card doesn't actually use salvage or malfunction, only overclock and flying. The overclock reminder text IS present. PASS.

**Q3: If this card has a conditional, is that conditional actually meaningful?**

YES. The conditions "Cards exiled with overclock" and "Whenever you cast a spell exiled with overclock" are meaningful because you could exile cards with overclock from other sources, or cast spells that weren't exiled with overclock. The conditionals properly distinguish between different types of exiled cards.

**Q4: Is the power level appropriate for its mana cost and rarity?**

NO. At 4 mana for a 3/4 flying legendary creature with two powerful abilities, this seems appropriately costed for mythic rare. The cost reduction and spell copying are significant effects, but require setup (overclocking) and the body itself is reasonable for the cost. PASS.

**Q5: Does this card try to do too many unrelated things (kitchen sink design)?**

NO. The card has a focused design around the overclock mechanic - it reduces costs of overclocked spells and copies them. Flying fits as a reasonable mythic legendary creature ability. All abilities work together synergistically. PASS.

**Q6: If this card has variable damage or variable effects, is the variability real?**

N/A. This card doesn't have variable damage or effects based on counts. The effects are consistent - always {2} cost reduction, always copy spells.

**Q7: Do any mechanic names on this card collide with existing MTG keywords?**

NO. The card uses "overclock" which was specifically renamed to avoid collision with "overload" from Return to Ravnica. No naming collisions present. PASS.

**Q8: Does this card have "enters tapped" or similar effects that are irrelevant for the card type?**

NO. This card doesn't have "enters tapped" or similar effects. It's a creature that can attack, block, and use its abilities immediately upon entering. PASS.

---

## Final Result

**Final Verdict**: FAIL
**Human Verdict**: WARN
**Match**: NO

**All issues** (2):

- [FAIL] missing_reminder_text: Reminder text for overclock appears in oracle text but should be removed at mythic rare.
- [WARN] templating: The phrase 'cards exiled with overclock' may need clarification to be more precise about the source of exile.