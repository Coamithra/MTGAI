# Card 14: Cascade Protocol — Strategy: s5-simple-opus

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

### Step 1: Review and revise (single pass)

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
> Critically review this card and provide an improved version based on your findings. If the card is fine, return it unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Incorrect reminder text - overclock always exiles exactly 3 cards, not variable",
    "Card doesn't actually exile cards itself, overclock does",
    "Damage calculation is ambiguous - overclock doesn't track which cards it exiles",
    "Missing flavor text quote attribution dash",
    "Card name doesn't match {R}{R} cost (cascade suggests {U} involvement)"
  ],
  "name": "Cascade Protocol",
  "mana_cost": "{3}{R}{R}",
  "type_line": "Sorcery",
  "oracle_text": "Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn. Then do it again.)\nCascade Protocol deals 6 damage to any target.",
  "rarity": "rare",
  "power": null,
  "toughness": null,
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u2014Final log, Research Station Gamma"
}
```

*Tokens: 1120 in / 378 out — $0.0452*

## C) Revised Card

```json
{
  "name": "Cascade Protocol",
  "mana_cost": "{3}{R}{R}",
  "type_line": "Sorcery",
  "oracle_text": "Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn. Then do it again.)\nCascade Protocol deals 6 damage to any target.",
  "rarity": "rare",
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u2014Final log, Research Station Gamma"
}
```

**Changes made:**
- Incorrect reminder text - overclock always exiles exactly 3 cards, not variable
- Card doesn't actually exile cards itself, overclock does
- Damage calculation is ambiguous - overclock doesn't track which cards it exiles
- Missing flavor text quote attribution dash
- Card name doesn't match {R}{R} cost (cascade suggests {U} involvement)

## D) Cost

- API calls: 1
- Input tokens: 1120
- Output tokens: 378
- Cost: $0.0452