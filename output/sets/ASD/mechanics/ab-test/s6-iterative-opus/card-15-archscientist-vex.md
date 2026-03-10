# Card 15: Archscientist Vex, the Unbound — Strategy: s6-iterative-opus

## A) Original Card

```json
{
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "cmc": 4,
  "colors": [
    "U",
    "R"
  ],
  "type_line": "Legendary Creature \u00ef\u00bf\u00bd Human Scientist",
  "oracle_text": "Flying\nCards exiled with overclock (exile the top three cards of your library, you may play them until end of turn) cost {2} less to cast.\nWhenever you cast a spell exiled with overclock, copy it. You may choose new targets for the copy.",
  "power": "3",
  "toughness": "4",
  "rarity": "mythic",
  "keywords": [
    "Flying",
    "Overclock"
  ],
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
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
> Name: Archscientist Vex, the Unbound
> Mana Cost: {2}{U}{R}
> Type: Legendary Creature ï¿½ Human Scientist
> Rarity: mythic
> Oracle Text: Flying
> Cards exiled with overclock (exile the top three cards of your library, you may play them until end of turn) cost {2} less to cast.
> Whenever you cast a spell exiled with overclock, copy it. You may choose new targets for the copy.
> P/T: 3/4
> Flavor Text: "I have transcended the limitations of sanity, safety, and the laws of thermodynamics."
> 
> Critically review this card and provide an improved version based on your findings. If the card is fine, return it unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Overclock reminder text appears inline in the oracle text when it should be formatted as a keyword action",
    "Cost reduction effect is too powerful when combined with copying - effectively gives 4 mana discount per spell",
    "3/4 flying body for 4 mana is above rate for a creature with such powerful abilities",
    "The card's power level is extremely high even for mythic rare"
  ],
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Wizard",
  "oracle_text": "Flying\nSpells you cast from exile cost {1} less to cast.\nWhenever you cast a spell from exile, you may pay {2}. If you do, copy that spell. You may choose new targets for the copy.",
  "power": "2",
  "toughness": "3",
  "rarity": "mythic",
  "flavor_text": "I have transcended the limitations of sanity, safety, and the laws of thermodynamics."
}
```

*Tokens: 1151 in / 395 out — $0.0469*

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
> Name: Archscientist Vex, the Unbound
> Mana Cost: {2}{U}{R}
> Type: Legendary Creature — Human Wizard
> Rarity: mythic
> Oracle Text: Flying
> Spells you cast from exile cost {1} less to cast.
> Whenever you cast a spell from exile, you may pay {2}. If you do, copy that spell. You may choose new targets for the copy.
> P/T: 2/3
> Flavor Text: I have transcended the limitations of sanity, safety, and the laws of thermodynamics.
> 
> Critically review this card and provide an improved version based on your findings. If the card is fine, return it unchanged with verdict OK.

**Tool call result:**
```json
{
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Wizard",
  "oracle_text": "Flying\nWhenever you cast your first spell from exile each turn, copy that spell. You may choose new targets for the copy.\n{U}{R}: Overclock. Activate only once each turn.",
  "power": "2",
  "toughness": "3",
  "rarity": "mythic",
  "flavor_text": "I have transcended the limitations of sanity, safety, and the laws of thermodynamics.",
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Original design too generically powerful with any exile effects",
    "Lacked synergy with set's Overclock mechanic",
    "Cost reduction plus copy effect was too swingy",
    "Missing quotation marks in flavor text"
  ]
}
```

*Tokens: 1136 in / 352 out — $0.0434*

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
> Name: Archscientist Vex, the Unbound
> Mana Cost: {2}{U}{R}
> Type: Legendary Creature — Human Wizard
> Rarity: mythic
> Oracle Text: Flying
> Whenever you cast your first spell from exile each turn, copy that spell. You may choose new targets for the copy.
> {U}{R}: Overclock. Activate only once each turn.
> P/T: 2/3
> Flavor Text: I have transcended the limitations of sanity, safety, and the laws of thermodynamics.
> 
> Critically review this card and provide an improved version based on your findings. If the card is fine, return it unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Power level too low for mythic rare - 4 mana 2/3 flyer with conditional ability",
    "Overclock activation is redundant with reminder text",
    "Design doesn't feel mythic enough for a legendary creature",
    "Stats and abilities don't justify mythic rarity"
  ],
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{1}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Wizard",
  "oracle_text": "Flying\nWhenever you cast a spell from exile, copy that spell. You may choose new targets for the copy.\n{U}{R}: Overclock. (Exile the top three cards of your library. You may play them until end of turn.) Activate only once each turn.",
  "rarity": "mythic",
  "power": "2",
  "toughness": "3",
  "flavor_text": "I have transcended the limitations of sanity, safety, and the laws of thermodynamics."
}
```

*Tokens: 1129 in / 384 out — $0.0457*

### Step 4: Iteration 4

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
> Name: Archscientist Vex, the Unbound
> Mana Cost: {1}{U}{R}
> Type: Legendary Creature — Human Wizard
> Rarity: mythic
> Oracle Text: Flying
> Whenever you cast a spell from exile, copy that spell. You may choose new targets for the copy.
> {U}{R}: Overclock. (Exile the top three cards of your library. You may play them until end of turn.) Activate only once each turn.
> P/T: 2/3
> Flavor Text: I have transcended the limitations of sanity, safety, and the laws of thermodynamics.
> 
> Critically review this card and provide an improved version based on your findings. If the card is fine, return it unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": false,
  "verdict": "OK",
  "issues_found": [],
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{1}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Wizard",
  "oracle_text": "Flying\nWhenever you cast a spell from exile, copy that spell. You may choose new targets for the copy.\n{U}{R}: Overclock. (Exile the top three cards of your library. You may play them until end of turn.) Activate only once each turn.",
  "rarity": "mythic",
  "power": "2",
  "toughness": "3",
  "flavor_text": "I have transcended the limitations of sanity, safety, and the laws of thermodynamics."
}
```

*Tokens: 1146 in / 319 out — $0.0411*

## C) Revised Card

No changes (OK)

**Changes made:**
- None

## D) Cost

- API calls: 4
- Input tokens: 4562
- Output tokens: 1450
- Cost: $0.1772