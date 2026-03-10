# Card 14: Cascade Protocol — Strategy: s7-detailed-opus

## A) Original Card

```json
{
  "name": "Cascade Protocol",
  "mana_cost": "{3}{R}{R}",
  "cmc": 5,
  "colors": [
    "R"
  ],
  "type_line": "Sorcery",
  "oracle_text": "Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)\n~ deals 2 damage to any target for each card exiled with ~ this way.",
  "rarity": "rare",
  "keywords": [
    "Overclock"
  ],
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u00ef\u00bf\u00bdFinal log, Research Station Gamma"
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
> Name: Cascade Protocol
> Mana Cost: {3}{R}{R}
> Type: Sorcery
> Rarity: rare
> Oracle Text: Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)
> ~ deals 2 damage to any target for each card exiled with ~ this way.
> Flavor Text: "The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion." ï¿½Final log, Research Station Gamma
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
> ## Review of Cascade Protocol
> 
> ### Templating & Rules Text:
> **FAIL** - There are several templating issues:
> 1. The overclock mechanic lacks reminder text despite this being its first appearance on the card
> 2. "deals 2 damage to any target for each card exiled with ~ this way" should be "deals 2 damage to any target for each card exiled this way" (no need for the self-reference ~)
> 3. The flavor text has an encoding issue with the character "ï¿½" which should be an em dash
> 
> Corrected oracle text should be:
> "Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)
> Cascade Protocol deals 2 damage to any target for each card exiled this way."
> 
> ### Keyword Interactions:
> **PASS** - No problematic keyword interactions. Overclock's double application works cleanly and synergizes with the damage effect.
> 
> ### Balance:
> **FAIL** - This card is significantly overpowered for {3}{R}{R}:
> - Guaranteed 12 damage to any target (6 cards × 2 damage) is far too efficient
> - Compare to printed cards:
>   - **Lava Axe** ({4}{R}): 5 damage to target player only
>   - **Burn from Within** ({X}{R}): Needs 11 mana to deal 12 damage
>   - **Banefire** ({X}{R}): Also needs 11 mana for 12 damage
> - Additionally provides card advantage by letting you play 6 cards from the top of your library
> - This is more powerful than many mythic rares at 5 mana
> 
> ### Design:
> **PASS** - The card has a focused design combining resource generation with direct damage. The variability is real (you might not be able to play all exiled cards), though the damage is fixed. Creates interesting decisions about timing and whether you have mana available to cast the exiled cards.
> 
> ### Color Pie:
> **PASS** - Both impulsive draw (overclock) and direct damage are firmly in red's color pie. The combination feels appropriately red.
> 
> ### Additional Notes:
> - The power level issue could be addressed by either:
>   1. Reducing damage to 1 per card exiled (6 total damage)
>   2. Increasing the mana cost to {5}{R}{R} or {4}{R}{R}{R}
>   3. Making it deal damage only to creatures or planeswalkers
>   4. Having it deal damage divided among any number of targets
> - The flavor text effectively captures the chaotic, experimental nature of the effect
> 
> ### Overall Assessment:
> This card needs significant balance adjustments and minor templating fixes before it's print-ready. The core concept is sound and flavorful, but 12 damage for 5 mana is format-warping at rare.

*Tokens: 804 in / 673 out — $0.0625*

### Step 2: Submit revised card based on review

**Prompt sent:**
> Based on the following review of a card, submit the revised card. If no issues were found, return the card unchanged with verdict OK.
> 
> Original card:
> Name: Cascade Protocol
> Mana Cost: {3}{R}{R}
> Type: Sorcery
> Rarity: rare
> Oracle Text: Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)
> ~ deals 2 damage to any target for each card exiled with ~ this way.
> Flavor Text: "The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion." ï¿½Final log, Research Station Gamma
> 
> Review findings:
> ## Review of Cascade Protocol
> 
> ### Templating & Rules Text:
> **FAIL** - There are several templating issues:
> 1. The overclock mechanic lacks reminder text despite this being its first appearance on the card
> 2. "deals 2 damage to any target for each card exiled with ~ this way" should be "deals 2 damage to any target for each card exiled this way" (no need for the self-reference ~)
> 3. The flavor text has an encoding issue with the character "ï¿½" which should be an em dash
> 
> Corrected oracle text should be:
> "Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)
> Cascade Protocol deals 2 damage to any target for each card exiled this way."
> 
> ### Keyword Interactions:
> **PASS** - No problematic keyword interactions. Overclock's double application works cleanly and synergizes with the damage effect.
> 
> ### Balance:
> **FAIL** - This card is significantly overpowered for {3}{R}{R}:
> - Guaranteed 12 damage to any target (6 cards × 2 damage) is far too efficient
> - Compare to printed cards:
>   - **Lava Axe** ({4}{R}): 5 damage to target player only
>   - **Burn from Within** ({X}{R}): Needs 11 mana to deal 12 damage
>   - **Banefire** ({X}{R}): Also needs 11 mana for 12 damage
> - Additionally provides card advantage by letting you play 6 cards from the top of your library
> - This is more powerful than many mythic rares at 5 mana
> 
> ### Design:
> **PASS** - The card has a focused design combining resource generation with direct damage. The variability is real (you might not be able to play all exiled cards), though the damage is fixed. Creates interesting decisions about timing and whether you have mana available to cast the exiled cards.
> 
> ### Color Pie:
> **PASS** - Both impulsive draw (overclock) and direct damage are firmly in red's color pie. The combination feels appropriately red.
> 
> ### Additional Notes:
> - The power level issue could be addressed by either:
>   1. Reducing damage to 1 per card exiled (6 total damage)
>   2. Increasing the mana cost to {5}{R}{R} or {4}{R}{R}{R}
>   3. Making it deal damage only to creatures or planeswalkers
>   4. Having it deal damage divided among any number of targets
> - The flavor text effectively captures the chaotic, experimental nature of the effect
> 
> ### Overall Assessment:
> This card needs significant balance adjustments and minor templating fixes before it's print-ready. The core concept is sound and flavorful, but 12 damage for 5 mana is format-warping at rare.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Missing reminder text for overclock mechanic",
    "Incorrect self-reference with ~ in damage clause",
    "Character encoding issue in flavor text",
    "Card is significantly overpowered - 12 guaranteed damage for 5 mana is too efficient"
  ],
  "name": "Cascade Protocol",
  "mana_cost": "{3}{R}{R}",
  "type_line": "Sorcery",
  "oracle_text": "Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)\nCascade Protocol deals 1 damage to any target for each card exiled this way.",
  "rarity": "rare",
  "power": null,
  "toughness": null,
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u2014Final log, Research Station Gamma"
}
```

*Tokens: 1482 in / 353 out — $0.0487*

## C) Revised Card

```json
{
  "name": "Cascade Protocol",
  "mana_cost": "{3}{R}{R}",
  "type_line": "Sorcery",
  "oracle_text": "Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)\nCascade Protocol deals 1 damage to any target for each card exiled this way.",
  "rarity": "rare",
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u2014Final log, Research Station Gamma"
}
```

**Changes made:**
- Missing reminder text for overclock mechanic
- Incorrect self-reference with ~ in damage clause
- Character encoding issue in flavor text
- Card is significantly overpowered - 12 guaranteed damage for 5 mana is too efficient

## D) Cost

- API calls: 2
- Input tokens: 2286
- Output tokens: 1026
- Cost: $0.1112