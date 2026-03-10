# Card 13: Vivisector Prime

## Card Data

```json
{
  "name": "Vivisector Prime",
  "mana_cost": "{2}{B}{B}",
  "cmc": 4,
  "colors": [
    "B"
  ],
  "color_identity": [
    "B"
  ],
  "type_line": "Creature � Human Scientist",
  "oracle_text": "Deathtouch\nWhenever you overclock (exile the top three cards of your library, you may play them until end of turn), each opponent loses 2 life and you gain 2 life.\n{3}{B}: Overclock.",
  "flavor_text": "\"The human circulatory system has such fascinating failure modes when subjected to protonium exposure.\"",
  "power": "3",
  "toughness": "3",
  "rarity": "rare",
  "keywords": [
    "Deathtouch",
    "Overclock"
  ],
  "design_notes": "Rare black creature with 'whenever you overclock' trigger and repeatable overclock. Creates a life-swing engine that rewards overclocking multiple times. The activated ability is expensive enough to be fair but cheap enough to be repeatable.",
  "_mechanic": "overclock",
  "_scores": {
    "rules_text": 5.0,
    "flavor_fit": 5.0,
    "balance": 5.0,
    "creativity": 5.0,
    "overall": 5.0,
    "issues": []
  }
}
```

---

## Ground Truth (Human Review)

**Status**: PASS
**Issues**: None

---

## Phase 1: Self-Critique

**AI Verdict**: FAIL
**Issues extracted** (2):

- [FAIL] missing_reminder_text: The oracle text uses 'overclock' but doesn't include the required reminder text.
- [FAIL] templating: The parenthetical explanation is embedded within the trigger condition instead of following the ability name as proper reminder text.

### Full Self-Critique Conversation

Looking at this card carefully:

**FAIL: Reminder text missing for custom mechanic**
The oracle text uses "overclock" but doesn't include the reminder text. According to the mechanic definition, overclock should have reminder text: "(Exile the top three cards of your library. You may play them until end of turn.)" The oracle text should read:
"Whenever you overclock (exile the top three cards of your library, you may play them until end of turn), each opponent loses 2 life and you gain 2 life."

**FAIL: Templating error in triggered ability**
The parenthetical explanation in the middle of the ability is incorrect templating. The reminder text should come after the ability name, not embedded within the trigger condition. The correct templating would be the fix mentioned above.

**WARN: Potential balance concern**
A 3/3 deathtouch for 4 mana with two relevant abilities seems pushed, even at rare. The activated ability essentially costs 3 mana for "draw up to 3 cards and gain 6 life in multiplayer" (assuming the triggered ability fires), which is very strong. However, overclock does exile the cards rather than putting them in hand, and there's risk of whiffing, so this may be acceptable at rare.

**WARN: Minor design redundancy**
Having both the keyword "Overclock" listed and the activated ability that grants overclock creates slight redundancy in the keywords field, though this doesn't affect the printed card.

The color pie placement (black getting life drain triggers and activated abilities) is appropriate, and there are no keyword naming collisions.

**Verdict: FAIL** - The reminder text issue must be fixed before this card can ship.

---

## Phase 2: Pointed Questions

**AI Verdict**: FAIL
**Issues extracted** (1):

- [FAIL] missing_reminder_text: The overclock mechanic lacks reminder text on its first use.

### Full Pointed Questions Conversation

Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?

**NO.** Deathtouch works normally on this 3/3 creature. The overclock ability doesn't interfere with deathtouch functionality.

Q2: Is reminder text present for all custom mechanics (salvage, malfunction, overclock)?

**NO.** The oracle text shows "Whenever you overclock" but overclock has no reminder text. According to the rules, the first use of overclock should include "(exile the top three cards of your library, you may play them until end of turn)." **FAIL** - Custom mechanics need reminder text on first use.

Q3: If this card has a conditional ("if you X this turn"), is that conditional actually meaningful?

**YES.** The trigger "Whenever you overclock" is meaningful because overclock can happen or not happen - you choose whether to activate the {3}{B} ability, and other cards could also cause overclock.

Q4: Is the power level appropriate for its mana cost and rarity?

**YES.** A 4-mana 3/3 with deathtouch is reasonable baseline (compare Gifted Aetherborn at 2 mana 2/3 deathtouch). The overclock synergy and life drain effect justify the rare slot without being overpowered.

Q5: Does this card try to do too many unrelated things (kitchen sink design)?

**NO.** The card has a focused design - it's built around the overclock mechanic with deathtouch as a combat keyword. The abilities work together thematically and mechanically.

Q6: If this card has variable damage or variable effects based on a count, is the variability real?

**YES.** The life loss/gain effect has real variability - it only happens when you overclock, which is optional and costs mana. You might overclock 0, 1, or multiple times per turn.

Q7: Do any mechanic names on this card collide with existing MTG keywords?

**NO.** The card uses "overclock" which correctly avoids collision with the existing "overload" keyword from Return to Ravnica.

Q8: Does this card have "enters tapped" or similar effects that are irrelevant for the card type?

**NO.** This is a creature without any "enters tapped" effects, so this question doesn't apply.

---

## Final Result

**Final Verdict**: FAIL
**Human Verdict**: PASS
**Match**: NO

**All issues** (3):

- [FAIL] missing_reminder_text: The overclock mechanic lacks reminder text on its first use.
- [FAIL] templating: The parenthetical explanation is embedded within the trigger condition instead of following the ability name as proper reminder text.
- [FAIL] missing_reminder_text: The oracle text uses 'overclock' but doesn't include the required reminder text.