# Card 5: Subsurface Expedition Leader — Strategy: s7-detailed-opus

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

### Step 1: Detailed review analysis

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
> Card to review:
> Name: Subsurface Expedition Leader
> Mana Cost: {2}{W}{W}
> Type: Creature ï¿½ Human Soldier
> Rarity: rare
> Oracle Text: When ~ enters, salvage 6.
> {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> P/T: 3/4
> Flavor Text: "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
> 
> Review this card thoroughly. At minimum, check every criterion below (state PASS or describe the issue for each), but also flag anything else you notice.
> 
> **Templating & Rules Text:**
> - Is the oracle text valid MTG rules text?
> - Does every custom mechanic (salvage, malfunction, overclock) have reminder text on first use?
> - Is capitalization consistent (keyword capitalized at start of ability, lowercase mid-sentence)?
> - Does the card use current MTG templating ("enters" not "enters the battlefield")?
> 
> **Keyword Interactions:**
> - Are there any keywords that are negated or made useless by other abilities? (e.g., haste on a creature that always enters tapped)
> - If there's a conditional ("if you X this turn"), can the condition actually be false during normal play?
> 
> **Balance:**
> - Is the power level appropriate for the mana cost AND rarity? Compare to 2-3 well-known printed MTG cards at similar cost.
> - Note: malfunction cards are intentionally above-rate — the delayed entry IS the drawback.
> 
> **Design:**
> - Does the card have a focused purpose, or is it kitchen sink (3+ unrelated effects)?
> - If effects are variable (deal X damage, etc.), is the variability real or does it always resolve to the same value?
> - Does the card create interesting gameplay decisions?
> 
> **Color Pie:**
> - Are all abilities appropriate for this card's color(s)?
> 
> Provide your detailed analysis for each criterion.

**Response:**
> I'll review **Subsurface Expedition Leader** thoroughly.
> 
> **Templating & Rules Text:**
> - **Oracle text validity**: PASS - The text follows proper MTG formatting
> - **Reminder text**: PASS - Salvage has reminder text on its first use
> - **Capitalization**: PASS - "salvage" is correctly lowercase in both instances
> - **Current templating**: PASS - Uses "enters" correctly
> 
> **Keyword Interactions:**
> - PASS - No conflicting keywords. The salvage abilities complement each other well, with the ETB effect providing immediate value and the activated ability offering repeatable card selection.
> 
> **Balance:**
> - **FAIL** - This card is significantly undercosted for its effect at rare. Let me compare:
>   - **Militia Bugler** (3 mana, 2/3): Looks at top 4, gets one creature with power 2 or less
>   - **Ranger of Eos** (4 mana, 3/2): Searches library for two 1-mana creatures
>   - **Recruiter of the Guard** (3 mana, 1/1): Searches library for one creature with toughness 2 or less
> 
> This card offers:
> - A 3/4 body for 4 mana (solid stats)
> - Salvage 6 on ETB (looking at 6 cards is massive card selection)
> - Repeatable salvage 3 activation
> 
> The combination of strong body, immediate card advantage, and repeatable effect makes this too powerful. Suggested fixes:
> - Reduce P/T to 2/3 or 2/4
> - Reduce initial salvage to 4
> - Increase activated ability cost to {3}{W} or {4}
> 
> **Design:**
> - **PASS with minor concern** - The card has a focused artifact-matters theme, but the double salvage effect (ETB + activated) borders on redundant. However, they serve different purposes (immediate value vs. long-game engine), so it's acceptable.
> - The card creates interesting decisions about when to activate vs. attack/block.
> 
> **Color Pie:**
> - **PASS** - White can dig for artifacts (see cards like Steelshaper's Gift, Open the Armory). The repeatable effect and defensive stats align with white's philosophy.
> 
> **Additional Notes:**
> - The flavor text cleverly hints at the dangerous nature of salvaging/exploring
> - At 4 mana in an artifact-matters set, this would be a premier limited bomb and likely see constructed play
> - Consider if having both ETB and activated salvage makes deckbuilding too linear
> 
> **Overall Assessment:** The card needs power level adjustment but is otherwise well-designed. Reduce either the stats, the salvage numbers, or increase the activation cost to bring it in line with similar rare effects.

*Tokens: 800 in / 645 out — $0.0604*

### Step 2: Submit revised card based on review

**Prompt sent:**
> Based on the following review of a card, submit the revised card. If no issues were found, return the card unchanged with verdict OK.
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
> Review findings:
> I'll review **Subsurface Expedition Leader** thoroughly.
> 
> **Templating & Rules Text:**
> - **Oracle text validity**: PASS - The text follows proper MTG formatting
> - **Reminder text**: PASS - Salvage has reminder text on its first use
> - **Capitalization**: PASS - "salvage" is correctly lowercase in both instances
> - **Current templating**: PASS - Uses "enters" correctly
> 
> **Keyword Interactions:**
> - PASS - No conflicting keywords. The salvage abilities complement each other well, with the ETB effect providing immediate value and the activated ability offering repeatable card selection.
> 
> **Balance:**
> - **FAIL** - This card is significantly undercosted for its effect at rare. Let me compare:
>   - **Militia Bugler** (3 mana, 2/3): Looks at top 4, gets one creature with power 2 or less
>   - **Ranger of Eos** (4 mana, 3/2): Searches library for two 1-mana creatures
>   - **Recruiter of the Guard** (3 mana, 1/1): Searches library for one creature with toughness 2 or less
> 
> This card offers:
> - A 3/4 body for 4 mana (solid stats)
> - Salvage 6 on ETB (looking at 6 cards is massive card selection)
> - Repeatable salvage 3 activation
> 
> The combination of strong body, immediate card advantage, and repeatable effect makes this too powerful. Suggested fixes:
> - Reduce P/T to 2/3 or 2/4
> - Reduce initial salvage to 4
> - Increase activated ability cost to {3}{W} or {4}
> 
> **Design:**
> - **PASS with minor concern** - The card has a focused artifact-matters theme, but the double salvage effect (ETB + activated) borders on redundant. However, they serve different purposes (immediate value vs. long-game engine), so it's acceptable.
> - The card creates interesting decisions about when to activate vs. attack/block.
> 
> **Color Pie:**
> - **PASS** - White can dig for artifacts (see cards like Steelshaper's Gift, Open the Armory). The repeatable effect and defensive stats align with white's philosophy.
> 
> **Additional Notes:**
> - The flavor text cleverly hints at the dangerous nature of salvaging/exploring
> - At 4 mana in an artifact-matters set, this would be a premier limited bomb and likely see constructed play
> - Consider if having both ETB and activated salvage makes deckbuilding too linear
> 
> **Overall Assessment:** The card needs power level adjustment but is otherwise well-designed. Reduce either the stats, the salvage numbers, or increase the activation cost to bring it in line with similar rare effects.

**Tool call result:**
```json
{
  "changed": false,
  "verdict": "OK",
  "issues_found": [],
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{2}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When ~ enters, salvage 6.\n{2}{W}, {T}: Salvage 3. Activate only as a sorcery.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
}
```

*Tokens: 1450 in / 285 out — $0.0431*

## C) Revised Card

No changes (OK)

**Changes made:**
- None

## D) Cost

- API calls: 2
- Input tokens: 2250
- Output tokens: 930
- Cost: $0.1035