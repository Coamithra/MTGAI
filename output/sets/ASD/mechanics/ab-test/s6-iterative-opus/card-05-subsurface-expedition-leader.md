# Card 5: Subsurface Expedition Leader — Strategy: s6-iterative-opus

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

### Step 1: Iteration 1

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
> Critically review this card and provide an improved version based on your findings. If the card is fine, return it unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Mana value too low for a rare with this much value",
    "Should be 'creature' not 'creature\u00ef\u00bf\u00bd'",
    "Missing 'the battlefield' in ETB trigger",
    "3/4 body plus double salvage at 4 mana is too efficient for rare",
    "Activated ability could be more interesting at rare"
  ],
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{3}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When Subsurface Expedition Leader enters the battlefield, salvage 6.\n{2}{W}, {T}: Salvage 3. You gain 2 life. Activate only as a sorcery.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
}
```

*Tokens: 1116 in / 378 out — $0.0451*

### Step 2: Iteration 2

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
> Mana Cost: {3}{W}{W}
> Type: Creature — Human Soldier
> Rarity: rare
> Oracle Text: When Subsurface Expedition Leader enters the battlefield, salvage 6.
> {2}{W}, {T}: Salvage 3. You gain 2 life. Activate only as a sorcery.
> P/T: 3/4
> Flavor Text: Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.
> 
> Critically review this card and provide an improved version based on your findings. If the card is fine, return it unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Salvage 6 at rare is appropriate but the card lacks sufficient payoff for a 5-mana rare",
    "The activated ability is overcosted and underpowered for a rare creature",
    "Card needs more synergy with artifacts to justify the salvage theme",
    "Power level is too low for a 5-mana rare in modern design"
  ],
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{3}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When Subsurface Expedition Leader enters the battlefield, salvage 6.\nWhenever you cast an artifact spell, you may pay {1}. If you do, create a 1/1 white Soldier creature token.\n{W}, {T}: Salvage 3. Activate only as a sorcery.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
}
```

*Tokens: 1125 in / 400 out — $0.0469*

### Step 3: Iteration 3

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
> Mana Cost: {3}{W}{W}
> Type: Creature — Human Soldier
> Rarity: rare
> Oracle Text: When Subsurface Expedition Leader enters the battlefield, salvage 6.
> Whenever you cast an artifact spell, you may pay {1}. If you do, create a 1/1 white Soldier creature token.
> {W}, {T}: Salvage 3. Activate only as a sorcery.
> P/T: 3/4
> Flavor Text: Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.
> 
> Critically review this card and provide an improved version based on your findings. If the card is fine, return it unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": false,
  "verdict": "OK",
  "issues_found": [],
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{3}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When Subsurface Expedition Leader enters the battlefield, salvage 6.\nWhenever you cast an artifact spell, you may pay {1}. If you do, create a 1/1 white Soldier creature token.\n{W}, {T}: Salvage 3. Activate only as a sorcery.",
  "power": "3",
  "toughness": "4",
  "rarity": "rare",
  "flavor_text": "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
}
```

*Tokens: 1149 in / 322 out — $0.0414*

## C) Revised Card

No changes (OK)

**Changes made:**
- None

## D) Cost

- API calls: 3
- Input tokens: 3390
- Output tokens: 1100
- Cost: $0.1333