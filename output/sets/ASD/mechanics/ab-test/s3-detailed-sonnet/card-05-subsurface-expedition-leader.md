# Card 5: Subsurface Expedition Leader — Strategy: s3-detailed-sonnet

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
> ## Card Review: Subsurface Expedition Leader
> 
> **Templating & Rules Text:**
> - **Oracle text validity**: PASS - All rules text follows proper MTG syntax
> - **Custom mechanic reminder text**: **ISSUE** - Salvage is missing reminder text on both uses. Per the mechanics document, salvage should have reminder text: "(Look at the top X cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"
> - **Capitalization**: PASS - "salvage" is properly lowercase in both instances
> - **Current templating**: PASS - Uses "enters" correctly
> 
> **Keyword Interactions:**
> - PASS - No conflicting keywords or abilities present
> - PASS - No conditional abilities that could be impossible to fulfill
> 
> **Balance:**
> **ISSUE** - This card appears significantly undercosted for its power level and rarity. Comparison analysis:
> 
> - **Mana cost**: 2WW for a 3/4 body is already reasonable
> - **ETB effect**: Salvage 6 is extremely powerful - looking at 6 cards to find any artifact is nearly guaranteed card advantage
> - **Activated ability**: 2W to salvage 3 repeatedly is very strong repeatable card advantage
> - **Comparable cards**: 
>   - Ranger-Captain of Eos (2WW, 3/3) tutors for specific creatures once
>   - Stonehewer Giant (3WW, 4/4) has expensive equipment tutoring
>   - This card provides more card advantage than either at a lower cost
> 
> This feels like it should cost 3WW or 4W minimum, or the salvage values should be reduced (ETB salvage 4, activated salvage 2).
> 
> **Design:**
> - **Focus**: PASS - Card has a clear "artifact expedition leader" theme with cohesive tutoring effects
> - **Variability**: PASS - Salvage provides meaningful variance in what artifacts are available
> - **Gameplay decisions**: PASS - Creates interesting decisions about which artifacts to take and when to activate the ability
> 
> **Color Pie:**
> - PASS - White gets tutoring effects and is listed as a salvage color in the mechanics document
> 
> **Additional Issues:**
> - **Rarity appropriateness**: The power level and complexity seem appropriate for rare
> - **Flavor integration**: The mechanics align well with the flavor of an expedition leader finding artifacts
> 
> **Recommendation**: This card needs significant power level adjustment (higher mana cost or reduced salvage values) and must include reminder text for salvage. The design concept is solid but the execution is overpowered as currently costed.

*Tokens: 800 in / 600 out — $0.0114*

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
> ## Card Review: Subsurface Expedition Leader
> 
> **Templating & Rules Text:**
> - **Oracle text validity**: PASS - All rules text follows proper MTG syntax
> - **Custom mechanic reminder text**: **ISSUE** - Salvage is missing reminder text on both uses. Per the mechanics document, salvage should have reminder text: "(Look at the top X cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"
> - **Capitalization**: PASS - "salvage" is properly lowercase in both instances
> - **Current templating**: PASS - Uses "enters" correctly
> 
> **Keyword Interactions:**
> - PASS - No conflicting keywords or abilities present
> - PASS - No conditional abilities that could be impossible to fulfill
> 
> **Balance:**
> **ISSUE** - This card appears significantly undercosted for its power level and rarity. Comparison analysis:
> 
> - **Mana cost**: 2WW for a 3/4 body is already reasonable
> - **ETB effect**: Salvage 6 is extremely powerful - looking at 6 cards to find any artifact is nearly guaranteed card advantage
> - **Activated ability**: 2W to salvage 3 repeatedly is very strong repeatable card advantage
> - **Comparable cards**: 
>   - Ranger-Captain of Eos (2WW, 3/3) tutors for specific creatures once
>   - Stonehewer Giant (3WW, 4/4) has expensive equipment tutoring
>   - This card provides more card advantage than either at a lower cost
> 
> This feels like it should cost 3WW or 4W minimum, or the salvage values should be reduced (ETB salvage 4, activated salvage 2).
> 
> **Design:**
> - **Focus**: PASS - Card has a clear "artifact expedition leader" theme with cohesive tutoring effects
> - **Variability**: PASS - Salvage provides meaningful variance in what artifacts are available
> - **Gameplay decisions**: PASS - Creates interesting decisions about which artifacts to take and when to activate the ability
> 
> **Color Pie:**
> - PASS - White gets tutoring effects and is listed as a salvage color in the mechanics document
> 
> **Additional Issues:**
> - **Rarity appropriateness**: The power level and complexity seem appropriate for rare
> - **Flavor integration**: The mechanics align well with the flavor of an expedition leader finding artifacts
> 
> **Recommendation**: This card needs significant power level adjustment (higher mana cost or reduced salvage values) and must include reminder text for salvage. The design concept is solid but the execution is overpowered as currently costed.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Missing salvage reminder text",
    "Card appears significantly undercosted for its power level"
  ],
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{3}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When ~ enters, salvage 4. (Look at the top 4 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)\n{2}{W}, {T}: Salvage 2. (Look at the top 2 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.) Activate only as a sorcery.",
  "power": "3",
  "toughness": "4",
  "rarity": "rare",
  "flavor_text": "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
}
```

*Tokens: 1405 in / 382 out — $0.0099*

## C) Revised Card

```json
{
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{3}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When ~ enters, salvage 4. (Look at the top 4 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)\n{2}{W}, {T}: Salvage 2. (Look at the top 2 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.) Activate only as a sorcery.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
}
```

**Changes made:**
- Missing salvage reminder text
- Card appears significantly undercosted for its power level

## D) Cost

- API calls: 2
- Input tokens: 2205
- Output tokens: 982
- Cost: $0.0213