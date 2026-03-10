# Card 5: Subsurface Expedition Leader

## Card Data

```json
{
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{2}{W}{W}",
  "cmc": 4,
  "colors": [
    "W"
  ],
  "color_identity": [
    "W"
  ],
  "type_line": "Creature � Human Soldier",
  "oracle_text": "When ~ enters, salvage 6.\n{2}{W}, {T}: Salvage 3. Activate only as a sorcery.",
  "flavor_text": "\"Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.\"",
  "power": "3",
  "toughness": "4",
  "rarity": "rare",
  "keywords": [
    "Salvage"
  ],
  "design_notes": "Rare with repeatable salvage via activated ability. The high initial salvage 6 and expensive but powerful activated ability create a powerful build-around card for artifact-based strategies. The sorcery-speed restriction prevents overpowered instant-speed value generation.",
  "_mechanic": "salvage",
  "_scores": {
    "rules_text": 4.5,
    "flavor_fit": 5.0,
    "balance": 5.0,
    "creativity": 4.5,
    "overall": 4.75,
    "issues": [
      "Missing or incorrect salvage reminder text"
    ]
  }
}
```

---

## Ground Truth (Human Review)

**Status**: FAIL
**Issues**: S1:keyword_collision, missing_reminder_text, inconsistent_capitalization

---

## Phase 1: Self-Critique

**AI Verdict**: FAIL
**Issues extracted** (2):

- [FAIL] missing_reminder_text: The oracle text uses 'salvage 6' and 'salvage 3' but provides no reminder text for this custom mechanic.
- [FAIL] templating: The activated ability should use 'Activate this ability only any time you could cast a sorcery' instead of 'Activate only as a sorcery.'

### Full Self-Critique Conversation

Looking at this card design critically:

**FAIL: Missing reminder text for custom mechanics**
The oracle text uses "salvage 6" and "salvage 3" but provides no reminder text. According to the mechanic definitions provided, salvage should have reminder text: "(Look at the top X cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)" This is essential for a custom mechanic, especially at rare where players need to understand what salvage does.

**FAIL: Incorrect templating for sorcery-speed restriction**
The activated ability reads "{2}{W}, {T}: Salvage 3. Activate only as a sorcery." The correct MTG templating for sorcery-speed restrictions is "Activate only as a sorcery." placed at the end, which is done correctly here. However, the more standard templating would be "Activate this ability only any time you could cast a sorcery."

**WARN: Keywords field mismatch**
The card lists "Salvage" in the keywords field, but salvage is a keyword action/ability that appears in rules text, not an inherent keyword like flying or trample. This appears to be a metadata formatting issue rather than a card design issue, but it's worth noting the inconsistency.

**Balance Assessment: PASS**
For a rare 4-mana creature:
- 3/4 body is reasonable but not impressive
- ETB salvage 6 is significant value (looking at 6 cards for an artifact)
- Activated ability provides repeatable value but requires mana investment and tapping
- Compared to similar rare value engines, this seems appropriately costed

**Design Assessment: PASS**
- Clear focus on artifact tutoring/filtering
- ETB provides immediate value, activated ability provides ongoing value
- Sorcery speed restriction prevents instant-speed abuse
- Fits white's artifact synergy theme appropriately

**Color Pie: PASS**
White getting artifact tutoring/filtering effects is within the color pie, especially in an artifact-focused set.

The primary issues are the missing reminder text (critical for custom mechanics) and minor templating preference. The card's fundamental design is sound.

---

## Phase 2: Pointed Questions

**AI Verdict**: FAIL
**Issues extracted** (1):

- [FAIL] missing_reminder_text: The salvage mechanic lacks reminder text on both uses of the keyword.

### Full Pointed Questions Conversation

Looking at the card:

**Q1: Does this card have any keywords that are negated or made useless by other abilities on the card?**
NO - The salvage keyword is not negated by any other abilities. Both the ETB salvage and activated ability salvage function normally.

**Q2: Is reminder text present for all custom mechanics?**
NO - The oracle text shows "When ~ enters, salvage 6." and "{2}{W}, {T}: Salvage 3. Activate only as a sorcery." There is no reminder text for salvage in parentheses following either use. FAIL - Custom mechanics need reminder text on first use.

**Q3: If this card has a conditional, is that conditional actually meaningful?**
NO - This card has no conditionals like "if you X this turn."

**Q4: Is the power level appropriate for its mana cost and rarity?**
YES - A 4-mana 3/4 that salvages 6 on entry and has a repeatable salvage 3 ability is reasonable for rare. Compare to cards like Ranger-Captain of Eos (4 mana, 3/3, tutors on ETB). The power level is appropriate.

**Q5: Does this card try to do too many unrelated things?**
NO - The card has a focused design around the salvage mechanic. Both abilities work together to support an artifact-focused strategy.

**Q6: If this card has variable effects, is the variability real or false?**
NO - This card doesn't have variable effects based on counts. The salvage numbers (6 and 3) are fixed.

**Q7: Do any mechanic names collide with existing MTG keywords?**
NO - "Salvage" does not collide with existing MTG keywords. The mechanic notes correctly indicate it was renamed from "Scavenge" to avoid that collision.

**Q8: Does this card have irrelevant "enters tapped" effects?**
NO - This card doesn't have "enters tapped" or similar effects that would be irrelevant for a creature.

---

## Final Result

**Final Verdict**: FAIL
**Human Verdict**: FAIL
**Match**: YES

**All issues** (3):

- [FAIL] missing_reminder_text: The oracle text uses 'salvage 6' and 'salvage 3' but provides no reminder text for this custom mechanic.
- [FAIL] templating: The activated ability should use 'Activate this ability only any time you could cast a sorcery' instead of 'Activate only as a sorcery.'
- [FAIL] missing_reminder_text: The salvage mechanic lacks reminder text on both uses of the keyword.