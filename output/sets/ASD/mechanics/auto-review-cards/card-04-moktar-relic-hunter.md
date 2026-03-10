# Card 4: Moktar Relic Hunter

## Card Data

```json
{
  "name": "Moktar Relic Hunter",
  "mana_cost": "{3}{G}",
  "cmc": 4,
  "colors": [
    "G"
  ],
  "color_identity": [
    "G"
  ],
  "type_line": "Creature � Moktar Scout",
  "oracle_text": "When ~ enters, salvage 5.\nWhenever you cast an artifact spell, ~ gets +2/+2 until end of turn.",
  "flavor_text": "Moktars collect shiny things not for trade, but for the joy of hearing them rattle in their pouches.",
  "power": "3",
  "toughness": "3",
  "rarity": "uncommon",
  "keywords": [
    "Salvage"
  ],
  "design_notes": "Uncommon artifact payoff creature. The temporary pump creates exciting combat scenarios when you cast found artifacts. Moktar is a setting-specific creature type representing the post-human barbarian tribes.",
  "_mechanic": "salvage",
  "_scores": {
    "rules_text": 4.5,
    "flavor_fit": 5.0,
    "balance": 5.0,
    "creativity": 5.0,
    "overall": 4.88,
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
**Issues extracted** (2):

- [FAIL] missing_reminder_text: The oracle text contains 'salvage 5' but lacks the required reminder text for this custom mechanic.
- [WARN] templating: The card uses placeholder '~' instead of the full card name 'Moktar Relic Hunter' in the oracle text.

### Full Self-Critique Conversation

Looking at this card carefully:

**FAIL: Missing reminder text for custom mechanic**
The oracle text contains "salvage 5" but lacks the required reminder text: "(Look at the top 5 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)" This is essential for custom mechanics.

**WARN: Templating inconsistency**
The card name should use the full name "Moktar Relic Hunter" instead of the placeholder "~" in the oracle text. Standard templating would be "When Moktar Relic Hunter enters, salvage 5."

**Balance Assessment: Reasonable for uncommon**
- 4-mana 3/3 baseline is below rate
- Salvage 5 provides significant card selection value (uncommon-appropriate per design notes)
- The pump ability requires artifact spell investment to get value
- Overall power level seems appropriate for uncommon

**Design Assessment: Clean synergy**
- Both abilities support the artifact theme coherently
- No redundant effects or keyword nonbos
- Salvage helps find artifacts, pump rewards casting them - good mechanical synergy

**Color Pie: Appropriate**
- Green gets artifact tutoring/selection (see cards like Ancient Stirrings)
- Conditional pump effects are in Green's wheelhouse
- No violations detected

**No keyword naming collisions** - "Salvage" was specifically chosen to avoid the existing "Scavenge" keyword.

The core design is solid, but the missing reminder text is a critical templating error that must be fixed.

---

## Phase 2: Pointed Questions

**AI Verdict**: FAIL
**Issues extracted** (1):

- [FAIL] missing_reminder_text: The salvage 5 ability is missing reminder text for this custom mechanic.

### Full Pointed Questions Conversation

Looking at the card:

**Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?**
NO. The card has salvage (which triggers on entry) and an artifact spell trigger. Neither ability negates or interferes with the other.

**Q2: Is reminder text present for all custom mechanics?**
NO. The oracle text shows "salvage 5" without any reminder text in parentheses following it. According to the rules, the first use of a custom mechanic should include reminder text.
FAIL - Missing reminder text for salvage.

**Q3: If this card has a conditional, is that conditional actually meaningful?**
NO. This card has no conditionals like "if you X this turn" - it has an ETB salvage trigger and a "whenever you cast" trigger, both of which are straightforward.

**Q4: Is the power level appropriate for its mana cost and rarity?**
YES. A 4-mana 3/3 that digs 5 deep for an artifact and gets temporary pumps is reasonable for uncommon. Compare to cards like Solemn Simulacrum or similar value creatures at 4 mana - this is in the right ballpark.

**Q5: Does this card try to do too many unrelated things?**
NO. The card has a focused artifact theme - it finds artifacts (salvage) and rewards you for casting them (+2/+2 pump). These abilities work together cohesively.

**Q6: If this card has variable effects, is the variability real or false?**
NO. The salvage value is fixed at 5, and the +2/+2 pump is fixed. While these are constant values, they're not presenting false variability - they're just fixed effects.

**Q7: Do any mechanic names collide with existing MTG keywords?**
NO. The card uses "salvage" which the design notes confirm was renamed from "scavenge" specifically to avoid collision with the existing MTG keyword.

**Q8: Does this card have irrelevant "enters tapped" effects?**
NO. This card doesn't have "enters tapped" or similar effects that would be irrelevant to its card type.

---

## Final Result

**Final Verdict**: FAIL
**Human Verdict**: FAIL
**Match**: YES

**All issues** (3):

- [FAIL] missing_reminder_text: The salvage 5 ability is missing reminder text for this custom mechanic.
- [WARN] templating: The card uses placeholder '~' instead of the full card name 'Moktar Relic Hunter' in the oracle text.
- [FAIL] missing_reminder_text: The oracle text contains 'salvage 5' but lacks the required reminder text for this custom mechanic.