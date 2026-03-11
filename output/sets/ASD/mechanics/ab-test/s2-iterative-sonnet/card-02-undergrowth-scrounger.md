# Card 2: Undergrowth Scrounger — Strategy: s2-iterative-sonnet

## A) Original Card

```json
{
  "name": "Undergrowth Scrounger",
  "mana_cost": "{1}{G}",
  "cmc": 2,
  "colors": [
    "G"
  ],
  "type_line": "Creature \u00e2\u20ac\u201d Human Scout",
  "oracle_text": "When ~ dies, salvage 3.",
  "power": "2",
  "toughness": "1",
  "rarity": "common",
  "keywords": [
    "Salvage"
  ],
  "flavor_text": "She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too."
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
> Name: Undergrowth Scrounger
> Mana Cost: {1}{G}
> Type: Creature â€” Human Scout
> Rarity: common
> Oracle Text: When ~ dies, salvage 3.
> P/T: 2/1
> Flavor Text: She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too.
> 
> Critically review this card and provide an improved version based on your findings. If the card is fine, return it unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": "[\"Salvage scaling violation: Salvage 3 is defined as uncommon-level (4-5 at uncommon, 2-3 at common). Salvage 3 sits at the top of the common range, which is technically allowed, but the trigger condition (on death) makes this significantly harder to control than a static or ETB trigger, which arguably warrants keeping it at Salvage 2 for common to avoid power/complexity creep.\", \"Trigger timing concern: A death trigger on a 2/1 for {1}{G} that replaces itself with an artifact from the top 3 cards is quite efficient. Salvage 2 is the safer and more appropriate common rate for a death-trigger payoff on a statted-up body.\", \"Type line encoding issue: 'Creature \u00e2\u20ac\" Human Scout' contains a mojibake/encoding artifact (\u00e2\u20ac\") instead of the correct em-dash (\u2014). Type line should read 'Creature \u2014 Human Scout'.\"]",
  "name": "Undergrowth Scrounger",
  "mana_cost": "{1}{G}",
  "type_line": "Creature \u2014 Human Scout",
  "oracle_text": "When Undergrowth Scrounger dies, salvage 2. (Look at the top two cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)",
  "rarity": "common",
  "power": "2",
  "toughness": "1",
  "flavor_text": "She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too."
}
```

*Tokens: 1360 in / 524 out — $0.0119*

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
> Name: Undergrowth Scrounger
> Mana Cost: {1}{G}
> Type: Creature — Human Scout
> Rarity: common
> Oracle Text: When Undergrowth Scrounger dies, salvage 2. (Look at the top two cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)
> P/T: 2/1
> Flavor Text: She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too.
> 
> Critically review this card and provide an improved version based on your findings. If the card is fine, return it unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": false,
  "verdict": "OK",
  "issues_found": [],
  "name": "Undergrowth Scrounger",
  "mana_cost": "{1}{G}",
  "type_line": "Creature \u2014 Human Scout",
  "oracle_text": "When Undergrowth Scrounger dies, salvage 2. (Look at the top two cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)",
  "rarity": "common",
  "power": "2",
  "toughness": "1",
  "flavor_text": "She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too."
}
```

*Tokens: 1402 in / 302 out — $0.0087*

## C) Revised Card

No changes (OK)

**Changes made:**
- None

## D) Cost

- API calls: 2
- Input tokens: 2762
- Output tokens: 826
- Cost: $0.0207