# Card 5: Subsurface Expedition Leader — Strategy: s4-split-sonnet

## A) Original Card

```json
{
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{2}{W}{W}",
  "cmc": 4,
  "colors": [
    "W"
  ],
  "type_line": "Creature \u00ef\u00bf\u00bd Human Soldier",
  "oracle_text": "When ~ enters, salvage 6.\n{2}{W}, {T}: Salvage 3. Activate only as a sorcery.",
  "power": "3",
  "toughness": "4",
  "rarity": "rare",
  "keywords": [
    "Salvage"
  ],
  "flavor_text": "\"Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.\""
}
```

## B) Review Process

### Step 1: Pass 1 — Templating review

**Prompt sent:**
> Custom mechanics for this set:
> 
> **Salvage X** (keyword_ability)
> Reminder text: (Look at the top X cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)
> Scaling: 2-3 at common, 4-5 at uncommon, 6+ at rare/mythic.
> Colors: W, U, G. Complexity: 1 (common-viable).
> 
> **Malfunction N** (keyword_ability)
> Reminder text: (This permanent enters tapped with N malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.)
> Scaling: 1 at common, 2 at uncommon, 2-3 at rare/mythic.
> Colors: W, U, R. Complexity: 2.
> Design note: Enters tapped is the key tempo cost. Cards with malfunction are intentionally above-rate for their mana cost.
> 
> **Overclock** (keyword_action)
> Reminder text: (Exile the top three cards of your library. You may play them until end of turn.)
> Colors: U, R, B. Complexity: 3 (uncommon+ only, never at common).
> Design note: High risk/reward. Always exiles exactly 3 cards.
> 
> Card:
> Name: Subsurface Expedition Leader
> Mana Cost: {2}{W}{W}
> Type: Creature ï¿½ Human Soldier
> Rarity: rare
> Oracle Text: When ~ enters, salvage 6.
> {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> P/T: 3/4
> Flavor Text: "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
> 
> Check:
> - Is the oracle text valid MTG rules text using current templating conventions?
> - Does every custom mechanic (salvage, malfunction, overclock) include reminder text in parentheses on its first use?
> - Is keyword capitalization consistent?
> - Are ability words, keyword abilities, and keyword actions used correctly?
> 
> List any templating issues found, or say "PASS" if the templating is correct.

**Response:**
> Looking at this card, I found one templating issue:
> 
> **ISSUE FOUND:**
> 
> 1. **Missing reminder text**: The custom mechanic "salvage" is missing its reminder text on both instances. According to your specifications, custom mechanics should include reminder text in parentheses on their first use. Since this appears to be the first use of salvage on this card, both instances should include the reminder text: "(Look at the top X cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"
> 
> The corrected oracle text should read:
> ```
> When ~ enters, salvage 6. (Look at the top 6 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)
> {2}{W}, {T}: Salvage 3.
> ```
> 
> All other templating appears correct:
> - Keyword capitalization is consistent (lowercase "salvage")
> - The activated ability template is correct
> - The sorcery-speed restriction is properly templated
> - The keyword ability usage follows MTG conventions

*Tokens: 560 in / 258 out — $0.0056*

### Step 2: Pass 2 — Mechanics review

**Prompt sent:**
> Custom mechanics for this set:
> 
> **Salvage X** (keyword_ability)
> Reminder text: (Look at the top X cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)
> Scaling: 2-3 at common, 4-5 at uncommon, 6+ at rare/mythic.
> Colors: W, U, G. Complexity: 1 (common-viable).
> 
> **Malfunction N** (keyword_ability)
> Reminder text: (This permanent enters tapped with N malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.)
> Scaling: 1 at common, 2 at uncommon, 2-3 at rare/mythic.
> Colors: W, U, R. Complexity: 2.
> Design note: Enters tapped is the key tempo cost. Cards with malfunction are intentionally above-rate for their mana cost.
> 
> **Overclock** (keyword_action)
> Reminder text: (Exile the top three cards of your library. You may play them until end of turn.)
> Colors: U, R, B. Complexity: 3 (uncommon+ only, never at common).
> Design note: High risk/reward. Always exiles exactly 3 cards.
> 
> Card:
> Name: Subsurface Expedition Leader
> Mana Cost: {2}{W}{W}
> Type: Creature ï¿½ Human Soldier
> Rarity: rare
> Oracle Text: When ~ enters, salvage 6.
> {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> P/T: 3/4
> Flavor Text: "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
> 
> Check:
> - Are there any keyword nonbos (keywords negated by other abilities on the card)?
> - If there's a conditional, can it actually be false during normal play?
> - Is this kitchen sink design (3+ unrelated effects piled together)?
> - If effects are variable, is the variability real or always the same value?
> - Does the design have a focused purpose?
> 
> List any design issues found, or say "PASS" if the design is sound.

**Response:**
> Looking at this card design:
> 
> **Keyword nonbos:** None. Both salvage abilities work together synergistically.
> 
> **Conditionals:** The activated ability has "Activate only as a sorcery" - this is a real restriction that can be false during opponents' turns, combat, etc.
> 
> **Kitchen sink design:** No. Both effects use the same mechanic (salvage) at different scales, creating a cohesive artifact-tutoring theme.
> 
> **Variable effects:** The variability is real - salvage 6 vs salvage 3 provides meaningfully different selection power and card advantage.
> 
> **Focused purpose:** Yes. Clear artifact-matters commander/value engine with escalating salvage effects.
> 
> **Design Issues Found:**
> 
> 1. **Salvage scaling violation:** The card uses salvage 6, but your design notes specify salvage scaling as "6+ at rare/mythic." At exactly 6, this sits at the minimum threshold. Consider salvage 7+ to feel more appropriately rare-level impactful.
> 
> 2. **Color pie concern:** White is listed as a salvage color, but tutoring artifacts isn't typically a white effect. White usually gets equipment tutoring specifically, not general artifact tutoring. This might be pushing white's slice of the color pie unless the set establishes this as acceptable.
> 
> Otherwise, the mechanical design is sound with good synergy between effects and appropriate complexity for rare.

*Tokens: 569 in / 311 out — $0.0064*

### Step 3: Pass 3 — Balance review

**Prompt sent:**
> Custom mechanics for this set:
> 
> **Salvage X** (keyword_ability)
> Reminder text: (Look at the top X cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)
> Scaling: 2-3 at common, 4-5 at uncommon, 6+ at rare/mythic.
> Colors: W, U, G. Complexity: 1 (common-viable).
> 
> **Malfunction N** (keyword_ability)
> Reminder text: (This permanent enters tapped with N malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.)
> Scaling: 1 at common, 2 at uncommon, 2-3 at rare/mythic.
> Colors: W, U, R. Complexity: 2.
> Design note: Enters tapped is the key tempo cost. Cards with malfunction are intentionally above-rate for their mana cost.
> 
> **Overclock** (keyword_action)
> Reminder text: (Exile the top three cards of your library. You may play them until end of turn.)
> Colors: U, R, B. Complexity: 3 (uncommon+ only, never at common).
> Design note: High risk/reward. Always exiles exactly 3 cards.
> 
> Card:
> Name: Subsurface Expedition Leader
> Mana Cost: {2}{W}{W}
> Type: Creature ï¿½ Human Soldier
> Rarity: rare
> Oracle Text: When ~ enters, salvage 6.
> {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> P/T: 3/4
> Flavor Text: "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
> 
> Check:
> - Is the power level appropriate for the mana cost AND rarity?
> - Compare to 2-3 well-known printed MTG cards at similar mana cost and rarity.
> - Note: malfunction cards are intentionally above-rate — the delayed entry IS the drawback. Do not flag these for being above-rate.
> - Note: mythic rares are allowed to be powerful build-arounds. Do not nerf mythics to rare power level.
> 
> State whether the balance is PASS, or describe the specific balance issue with card comparisons.

**Response:**
> Looking at **Subsurface Expedition Leader** as a 4-mana rare white creature:
> 
> **Power Level Analysis:**
> - 3/4 body for 4 mana is below rate but reasonable for a utility creature
> - ETB Salvage 6 provides significant card selection and potential card advantage
> - Repeatable Salvage 3 for {2}{W}, T creates long-term value engine
> - Double white in cost suggests this is meant for dedicated white or artifact-heavy decks
> 
> **Comparable Cards:**
> - **Ranger-Captain of Eos** (1WW, 3/3): Tutors for specific creatures, has Flash protection ability - clearly more powerful
> - **Recruiter of the Guard** (2W, 1/1): Tutors any creature with power ≤2, much smaller body but more reliable tutor
> - **Palace Jailer** (2WW, 2/2): Draws cards via monarch, smaller body but guaranteed card draw vs. conditional artifact finding
> 
> **Balance Assessment:**
> The card sits in an interesting spot. Salvage 6 on ETB is quite powerful card selection (looking at 6 cards is substantial), but it's conditional on finding artifacts. The activated ability creates a repeatable engine, which is valuable in longer games.
> 
> However, compared to other 4-mana white rares that provide card advantage, this feels appropriately powered. It's not as immediately impactful as Ranger-Captain's tutor + protection, but offers more long-term value. The double white requirement and artifact-dependency provide meaningful deckbuilding constraints.
> 
> **PASS** - The power level is appropriate for a 4-mana rare. The card provides good value without being oppressive, has clear deckbuilding requirements, and fits well within the power band of similar white utility creatures at rare.

*Tokens: 591 in / 415 out — $0.0080*

### Step 4: Pass 4 — Revision (combining all feedback)

**Prompt sent:**
> Custom mechanics for this set:
> 
> **Salvage X** (keyword_ability)
> Reminder text: (Look at the top X cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)
> Scaling: 2-3 at common, 4-5 at uncommon, 6+ at rare/mythic.
> Colors: W, U, G. Complexity: 1 (common-viable).
> 
> **Malfunction N** (keyword_ability)
> Reminder text: (This permanent enters tapped with N malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.)
> Scaling: 1 at common, 2 at uncommon, 2-3 at rare/mythic.
> Colors: W, U, R. Complexity: 2.
> Design note: Enters tapped is the key tempo cost. Cards with malfunction are intentionally above-rate for their mana cost.
> 
> **Overclock** (keyword_action)
> Reminder text: (Exile the top three cards of your library. You may play them until end of turn.)
> Colors: U, R, B. Complexity: 3 (uncommon+ only, never at common).
> Design note: High risk/reward. Always exiles exactly 3 cards.
> 
> Original card:
> Name: Subsurface Expedition Leader
> Mana Cost: {2}{W}{W}
> Type: Creature ï¿½ Human Soldier
> Rarity: rare
> Oracle Text: When ~ enters, salvage 6.
> {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> P/T: 3/4
> Flavor Text: "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
> 
> Issues found:
> - Templating: Looking at this card, I found one templating issue:
> 
> **ISSUE FOUND:**
> 
> 1. **Missing reminder text**: The custom mechanic "salvage" is missing its reminder text on both instances. According to your specifications, custom mechanics should include reminder text in parentheses on their first use. Since this appears to be the first use of salvage on this card, both instances should include the reminder text: "(Look at the top X cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"
> 
> The corrected oracle text should read:
> ```
> When ~ enters, salvage 6. (Look at the top 6 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)
> {2}{W}, {T}: Salvage 3.
> ```
> 
> All other templating appears correct:
> - Keyword capitalization is consistent (lowercase "salvage")
> - The activated ability template is correct
> - The sorcery-speed restriction is properly templated
> - The keyword ability usage follows MTG conventions
> - Mechanics: Looking at this card design:
> 
> **Keyword nonbos:** None. Both salvage abilities work together synergistically.
> 
> **Conditionals:** The activated ability has "Activate only as a sorcery" - this is a real restriction that can be false during opponents' turns, combat, etc.
> 
> **Kitchen sink design:** No. Both effects use the same mechanic (salvage) at different scales, creating a cohesive artifact-tutoring theme.
> 
> **Variable effects:** The variability is real - salvage 6 vs salvage 3 provides meaningfully different selection power and card advantage.
> 
> **Focused purpose:** Yes. Clear artifact-matters commander/value engine with escalating salvage effects.
> 
> **Design Issues Found:**
> 
> 1. **Salvage scaling violation:** The card uses salvage 6, but your design notes specify salvage scaling as "6+ at rare/mythic." At exactly 6, this sits at the minimum threshold. Consider salvage 7+ to feel more appropriately rare-level impactful.
> 
> 2. **Color pie concern:** White is listed as a salvage color, but tutoring artifacts isn't typically a white effect. White usually gets equipment tutoring specifically, not general artifact tutoring. This might be pushing white's slice of the color pie unless the set establishes this as acceptable.
> 
> Otherwise, the mechanical design is sound with good synergy between effects and appropriate complexity for rare.
> - Balance: Looking at **Subsurface Expedition Leader** as a 4-mana rare white creature:
> 
> **Power Level Analysis:**
> - 3/4 body for 4 mana is below rate but reasonable for a utility creature
> - ETB Salvage 6 provides significant card selection and potential card advantage
> - Repeatable Salvage 3 for {2}{W}, T creates long-term value engine
> - Double white in cost suggests this is meant for dedicated white or artifact-heavy decks
> 
> **Comparable Cards:**
> - **Ranger-Captain of Eos** (1WW, 3/3): Tutors for specific creatures, has Flash protection ability - clearly more powerful
> - **Recruiter of the Guard** (2W, 1/1): Tutors any creature with power ≤2, much smaller body but more reliable tutor
> - **Palace Jailer** (2WW, 2/2): Draws cards via monarch, smaller body but guaranteed card draw vs. conditional artifact finding
> 
> **Balance Assessment:**
> The card sits in an interesting spot. Salvage 6 on ETB is quite powerful card selection (looking at 6 cards is substantial), but it's conditional on finding artifacts. The activated ability creates a repeatable engine, which is valuable in longer games.
> 
> However, compared to other 4-mana white rares that provide card advantage, this feels appropriately powered. It's not as immediately impactful as Ranger-Captain's tutor + protection, but offers more long-term value. The double white requirement and artifact-dependency provide meaningful deckbuilding constraints.
> 
> **PASS** - The power level is appropriate for a 4-mana rare. The card provides good value without being oppressive, has clear deckbuilding requirements, and fits well within the power band of similar white utility creatures at rare.
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Missing reminder text for salvage mechanic",
    "Salvage scaling at minimum threshold (consider 7+ for rare impact)",
    "Color pie concern with white artifact tutoring"
  ],
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{2}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When Subsurface Expedition Leader enters, salvage 7. (Look at the top 7 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)\n{2}{W}, {T}: Salvage 3.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
}
```

*Tokens: 2126 in / 358 out — $0.0117*

## C) Revised Card

```json
{
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{2}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When Subsurface Expedition Leader enters, salvage 7. (Look at the top 7 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)\n{2}{W}, {T}: Salvage 3.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
}
```

**Changes made:**
- Missing reminder text for salvage mechanic
- Salvage scaling at minimum threshold (consider 7+ for rare impact)
- Color pie concern with white artifact tutoring

## D) Cost

- API calls: 4
- Input tokens: 3846
- Output tokens: 1342
- Cost: $0.0317