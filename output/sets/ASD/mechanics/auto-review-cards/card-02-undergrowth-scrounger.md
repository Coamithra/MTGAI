# Card 2: Undergrowth Scrounger

## Card Data

```json
{
  "name": "Undergrowth Scrounger",
  "mana_cost": "{1}{G}",
  "cmc": 2,
  "colors": [
    "G"
  ],
  "color_identity": [
    "G"
  ],
  "type_line": "Creature � Human Scout",
  "oracle_text": "When ~ dies, salvage 3.",
  "flavor_text": "She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too.",
  "power": "2",
  "toughness": "1",
  "rarity": "common",
  "keywords": [
    "Salvage"
  ],
  "design_notes": "Death trigger salvage common. The aggressive 2/1 body for 2 mana is fine since the value comes when it dies. Green gets salvage representing natural adaptation and finding resources in the wild.",
  "_mechanic": "salvage",
  "_scores": {
    "rules_text": 4.5,
    "flavor_fit": 3.5,
    "balance": 5.0,
    "creativity": 4.5,
    "overall": 4.38,
    "issues": [
      "Missing or incorrect salvage reminder text"
    ]
  }
}
```

---

## Ground Truth (Human Review)

**Status**: FAIL
**Issues**: S1:keyword_collision, missing_reminder_text

---

## Phase 1: Self-Critique

**AI Verdict**: FAIL
**Issues extracted** (1):

- [FAIL] missing_reminder_text: The card uses the custom mechanic 'salvage 3' but lacks the required reminder text.

### Full Self-Critique Conversation

Looking at Undergrowth Scrounger:

**FAIL: Missing reminder text for custom mechanic**
The card uses the custom mechanic "salvage 3" but lacks the required reminder text. According to your instructions, I should flag missing reminder text for custom mechanics. The oracle text should read:
"When ~ dies, salvage 3. (Look at the top 3 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"

**WARN: Keywords field inconsistency**
The "Keywords" field lists "Salvage" but salvage isn't actually a keyword ability on this card - it's a keyword action triggered by the death trigger. This appears to be a metadata formatting issue rather than a card design problem, but worth noting for consistency.

**Design Assessment - PASS:**
- **Templating**: The trigger templating follows standard MTG format correctly
- **Balance**: A 2/1 for {1}{G} that provides card advantage when it dies is reasonable at common, comparable to cards like Elvish Visionary or Farhaven Elf
- **Color pie**: Green gets artifact tutoring/filtering (see Sylvan Scrying, Oath of Nissa) and death triggers, so this fits
- **Design coherence**: Clean, focused design that supports the set's artifact theme
- **No keyword collisions**: "Salvage" was properly renamed to avoid the existing "Scavenge" keyword

The core card design is solid once the reminder text is added.

---

## Phase 2: Pointed Questions

**AI Verdict**: FAIL
**Issues extracted** (1):

- [FAIL] missing_reminder_text: The salvage mechanic is missing reminder text on its first use.

### Full Pointed Questions Conversation

Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?

**NO** - The card only has salvage, which triggers when it dies. There are no conflicting abilities.

Q2: Is reminder text present for all custom mechanics?

**NO** - The oracle text shows "When ~ dies, salvage 3." but there is no reminder text for salvage. The first use of salvage should include "(Look at the top 3 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"

**FAIL** - Custom mechanics must have reminder text on their first use.

Q3: If this card has a conditional, is that conditional actually meaningful?

**N/A** - This card has no conditionals.

Q4: Is the power level appropriate for its mana cost and rarity?

**YES** - A 2/1 for {1}{G} with a death trigger is reasonable at common. Compare to cards like Sakura-Tribe Elder or Elvish Visionary - the salvage 3 ability provides card selection value when it dies, which is appropriately costed.

Q5: Does this card try to do too many unrelated things?

**NO** - The card has a focused design: it's a creature that provides artifact card selection when it dies. This supports the set's artifact theme coherently.

Q6: If this card has variable effects, is the variability real?

**N/A** - The salvage value is fixed at 3, so there's no variable effect to evaluate.

Q7: Do any mechanic names collide with existing MTG keywords?

**NO** - The card uses "salvage" which correctly avoids the collision with MTG's existing "scavenge" keyword.

Q8: Does this card have irrelevant "enters tapped" effects?

**NO** - This card doesn't enter tapped and doesn't have any abilities that would be irrelevant to its card type.

---

## Final Result

**Final Verdict**: FAIL
**Human Verdict**: FAIL
**Match**: YES

**All issues** (2):

- [FAIL] missing_reminder_text: The salvage mechanic is missing reminder text on its first use.
- [FAIL] missing_reminder_text: The card uses the custom mechanic 'salvage 3' but lacks the required reminder text.