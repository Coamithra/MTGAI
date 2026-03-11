# Card 5: Subsurface Expedition Leader — Strategy: s2-iterative-sonnet

## A) Original Card

```json
{
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{2}{W}{W}",
  "cmc": 4,
  "colors": [
    "W"
  ],
  "type_line": "Creature \u00e2\u20ac\u201d Human Soldier",
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
> Type: Creature â€” Human Soldier
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
  "issues_found": "[\"Salvage 6 on entry at rare is acceptable per scaling rules (6+ at rare/mythic), but white is listed as a valid Salvage color, so that's fine.\", \"The activated ability uses Salvage 3, which is in the uncommon range (4-5) \u2014 actually Salvage 3 falls in the COMMON range (2-3 per scaling rules), which is fine for a rare card to use downward. No issue there.\", \"CRITICAL: The activated ability costs {2}{W}{T} and grants Salvage 3 (looks at top 3, nets at best 1 artifact). For a 4-mana body with a 3-mana activated ability, this is underwhelming and largely redundant given the powerful ETB. The activated ability provides very little incremental value at rare, where players expect meaningful reuse.\", \"MECHANICAL REDUNDANCY: Both abilities do the same thing (Salvage), just at different scales. A rare creature should have more design texture \u2014 the activated ability should do something meaningfully different or synergistic, not just a smaller version of the ETB.\", \"POWER LEVEL: A 3/4 for {2}{W}{W} (4 mana) with Salvage 6 on ETB is already a strong rare. The activated ability as written adds marginal value and clutters the card. It should either be cut or replaced with something that rewards the artifacts you're finding.\", \"ENCODING ISSUE: The type line contains a garbled character ('Creature \u00e2\u20ac\" Human Soldier') \u2014 this is a UTF-8 encoding artifact for an em dash and should be 'Creature \u2014 Human Soldier'. Flagging for templating team.\"]",
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{2}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When Subsurface Expedition Leader enters, salvage 6.\n{2}{W}, {T}: Each artifact creature you control gets +1/+1 until end of turn. Activate only as a sorcery.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.\""
}
```

*Tokens: 1387 in / 685 out — $0.0144*

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
> Mana Cost: {2}{W}{W}
> Type: Creature — Human Soldier
> Rarity: rare
> Oracle Text: When Subsurface Expedition Leader enters, salvage 6.
> {2}{W}, {T}: Each artifact creature you control gets +1/+1 until end of turn. Activate only as a sorcery.
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
    "Salvage 6 on a rare is correct per scaling rules (6+ at rare/mythic), but this card has NO artifact synergy in its activated ability \u2014 it only buffs artifact *creatures*, yet the card itself is a Human Soldier with no artifact type. Salvage 6 is used to find artifacts, which pairs thematically and mechanically with the pump ability, so the synergy is present but one-sided. This is acceptable.",
    "Mana cost {2}{W}{W} for a 3/4 with Salvage 6 and a pump ability is significantly overloaded for a rare at 4 mana. Salvage 6 alone on a 4-drop would already be strong (it digs 6 cards deep for an artifact). Adding a relevant activated pump ability makes this card very pushed even for rare. Slight adjustment recommended: either raise the mana cost to {3}{W}{W} (5 mana) to reflect the card's power, or reduce the stat line to 3/3 to compensate.",
    "The activated ability cost {2}{W}{W} is quite expensive for a +1/+1 buff until end of turn that only affects artifact creatures. At sorcery speed this is often too slow and costly to be impactful unless the player controls many artifact creatures. The cost should be reduced to {1}{W} to make it a meaningful payoff for building an artifact creature board, otherwise it will rarely be used.",
    "Color identity is pure White ({W}{W}), which is valid for Salvage per the set rules. No violation."
  ],
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{3}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When Subsurface Expedition Leader enters, salvage 6. (Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)\n{1}{W}, {T}: Each artifact creature you control gets +1/+1 until end of turn. Activate only as a sorcery.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.\""
}
```

*Tokens: 1402 in / 694 out — $0.0146*

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
> Oracle Text: When Subsurface Expedition Leader enters, salvage 6. (Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)
> {1}{W}, {T}: Each artifact creature you control gets +1/+1 until end of turn. Activate only as a sorcery.
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
    "Salvage 6 on a rare is valid per scaling rules (6+ at rare/mythic), but Salvage is listed as a W/U/G mechanic \u2014 White is allowed, so no issue there.",
    "The main mechanical tension: this card has Salvage to find artifact cards AND a pump ability for artifact creatures, but it costs {3}{W}{W} (5 mana) for a 3/4 body. The rate feels slightly off \u2014 Salvage 6 is a strong ETB, but the pump ability requires {1}{W} and tapping, is sorcery-speed, and only affects artifact creatures you control. For a 5-mana rare, the pump activation is narrow and weak as a payoff. Consider reducing activation cost or broadening to all creatures to make the second ability feel worthwhile at rare.",
    "Salvage reminder text in the oracle text is redundant with the printed reminder text section \u2014 in a real card, you either include the reminder in parentheses inline OR omit it (it is already inline here, which is correct). No change needed.",
    "Color identity concern: White is a listed Salvage color, so that is fine. However, the artifact-creature tribal pump is a more Red or White-artifact effect. Purely White artifact-creature buffs are a little unusual but acceptable for this set's theme.",
    "The sorcery-speed restriction on the pump ability is slightly over-constraining for a rare. Sorcery speed on a {1}{W} tap ability that only affects artifact creatures is a significant triple-restriction (cost + tap + sorcery + narrow targeting). Recommend removing the 'Activate only as a sorcery' clause to make the card feel rare-worthy.",
    "Power/toughness of 3/4 for {3}{W}{W} is slightly below vanilla rate (a vanilla 5-drop is typically 4/4 or 5/4). This is partially justified by the strong ETB Salvage 6, but the below-rate body combined with a weak second ability makes the card feel undertuned for rare. Suggest bumping P/T to 3/5 or 4/4 to ensure the card feels appropriately powerful."
  ],
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{3}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When Subsurface Expedition Leader enters, salvage 6. (Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)\n{1}{W}, {T}: Each artifact creature you control gets +1/+1 until end of turn.",
  "rarity": "rare",
  "power": "3",
  "toughness": "5",
  "flavor_text": "\"Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.\""
}
```

*Tokens: 1439 in / 823 out — $0.0167*

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
> Name: Subsurface Expedition Leader
> Mana Cost: {3}{W}{W}
> Type: Creature — Human Soldier
> Rarity: rare
> Oracle Text: When Subsurface Expedition Leader enters, salvage 6. (Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)
> {1}{W}, {T}: Each artifact creature you control gets +1/+1 until end of turn.
> P/T: 3/5
> Flavor Text: "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
> 
> Critically review this card and provide an improved version based on your findings. If the card is fine, return it unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Salvage 6 on a White creature is a mechanical color identity violation. The Salvage mechanic is defined for W, U, G \u2014 White is permitted, BUT the activated ability pumping artifact creatures is a Red/White Voltron-style effect that fits better, so color is fine. However, the primary issue is that Salvage 6 at rare is acceptable per scaling rules (6+ at rare/mythic), so that is fine.",
    "More critically: The body is a 3/5 for {3}{W}{W} (5 mana) with a strong ETB (Salvage 6) AND a cheap repeatable lord effect for artifact creatures. This is significantly over-rate even for a rare \u2014 there is no Malfunction drawback or other balancing cost. Salvage 6 alone on a 5-mana body would be reasonable; a repeatable lord effect on top of that is too much value at rare without a drawback.",
    "The activated ability \u2014 {1}{W}, {T}: Each artifact creature you control gets +1/+1 until end of turn \u2014 is a strong wide anthem effect. Combined with a 3/5 body and Salvage 6, the card is too pushed. The power/toughness should be reduced, the activation cost increased, or the mana cost raised to {4}{W}{W} to reflect the total package.",
    "Minor: The reminder text is correctly included inline, which is correct for the set template. No issues there.",
    "Flavor text is thematically appropriate for the set 'Anomalous Descent' and well-written. No changes needed."
  ],
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{4}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When Subsurface Expedition Leader enters, salvage 6. (Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)\n{2}{W}, {T}: Each artifact creature you control gets +1/+1 until end of turn.",
  "rarity": "rare",
  "power": "3",
  "toughness": "5",
  "flavor_text": "\"Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.\""
}
```

*Tokens: 1430 in / 691 out — $0.0147*

### Step 5: Iteration 5

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
> Mana Cost: {4}{W}{W}
> Type: Creature — Human Soldier
> Rarity: rare
> Oracle Text: When Subsurface Expedition Leader enters, salvage 6. (Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)
> {2}{W}, {T}: Each artifact creature you control gets +1/+1 until end of turn.
> P/T: 3/5
> Flavor Text: "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
> 
> Critically review this card and provide an improved version based on your findings. If the card is fine, return it unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Salvage 6 on a rare is compliant with scaling rules (6+ at rare/mythic), but the overall card is overloaded for its cost. A 3/5 for {4}{W}{W} with both a strong enters-the-battlefield tutor effect AND a relevant activated ability is too much value on one card.",
    "Salvage 6 specifically searches for artifact cards, but the activated ability buffs artifact creatures. However, White is not a primary artifact-matters color, and the combination of artifact-searching ETB + artifact-creature anthem on a Human Soldier feels thematically scattered \u2014 more like a Blue-White artifact synergy card without the Blue.",
    "The activated ability cost {2}{W} + tap to grant +1/+1 until end of turn to all artifact creatures is quite weak for a six-mana rare. It's a win-more effect that does little when behind and doesn't justify the investment. It should either be cut to streamline the card, or made meaningfully impactful (e.g., a stronger buff or a permanent effect).",
    "The body (3/5) is solid but slightly large for a support/utility rare that already has a powerful ETB. Consider trimming the stat line slightly to 3/4 to offset the power elsewhere.",
    "Reminder text for Salvage 6 is correctly included, which is good practice for a keyword with variable X values."
  ],
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{3}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When Subsurface Expedition Leader enters, salvage 6. (Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)\nArtifact creatures you control get +1/+1.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.\""
}
```

*Tokens: 1430 in / 630 out — $0.0137*

## C) Revised Card

```json
{
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{3}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When Subsurface Expedition Leader enters, salvage 6. (Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)\nArtifact creatures you control get +1/+1.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.\""
}
```

**Changes made:**
- Salvage 6 on a rare is compliant with scaling rules (6+ at rare/mythic), but the overall card is overloaded for its cost. A 3/5 for {4}{W}{W} with both a strong enters-the-battlefield tutor effect AND a relevant activated ability is too much value on one card.
- Salvage 6 specifically searches for artifact cards, but the activated ability buffs artifact creatures. However, White is not a primary artifact-matters color, and the combination of artifact-searching ETB + artifact-creature anthem on a Human Soldier feels thematically scattered — more like a Blue-White artifact synergy card without the Blue.
- The activated ability cost {2}{W} + tap to grant +1/+1 until end of turn to all artifact creatures is quite weak for a six-mana rare. It's a win-more effect that does little when behind and doesn't justify the investment. It should either be cut to streamline the card, or made meaningfully impactful (e.g., a stronger buff or a permanent effect).
- The body (3/5) is solid but slightly large for a support/utility rare that already has a powerful ETB. Consider trimming the stat line slightly to 3/4 to offset the power elsewhere.
- Reminder text for Salvage 6 is correctly included, which is good practice for a keyword with variable X values.

## D) Cost

- API calls: 5
- Input tokens: 7088
- Output tokens: 3523
- Cost: $0.0741