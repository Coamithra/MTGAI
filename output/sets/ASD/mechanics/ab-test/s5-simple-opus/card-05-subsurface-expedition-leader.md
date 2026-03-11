# Card 5: Subsurface Expedition Leader — Strategy: s5-simple-opus

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
  "issues_found": [
    "Salvage 6 on ETB is appropriate for rare per the scaling guidelines (6+ at rare/mythic) \u2014 this is fine.",
    "Salvage 3 on the activated ability is slightly below the uncommon floor (4-5) but as a repeatable ability on a rare card, the value of 3 is reasonable for balance. However, since this is a rare card and the ability costs {2}{W} + tap + sorcery speed (significant restrictions), bumping to Salvage 4 would better match the rare identity and feel more rewarding for the investment.",
    "The sorcery-speed restriction and tap cost on the activated ability already provide sufficient tempo cost, so Salvage 4 on a repeatable ability remains balanced at rare.",
    "No mechanical errors found \u2014 Salvage is correctly used as a keyword ability with a number, and the card is in-color (W) for Salvage."
  ],
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{2}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When ~ enters, salvage 6.\n{2}{W}, {T}: Salvage 4. Activate only as a sorcery.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.\""
}
```

*Tokens: 1386 in / 488 out — $0.0191*

## C) Revised Card

```json
{
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{2}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When ~ enters, salvage 6.\n{2}{W}, {T}: Salvage 4. Activate only as a sorcery.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.\""
}
```

**Changes made:**
- Salvage 6 on ETB is appropriate for rare per the scaling guidelines (6+ at rare/mythic) — this is fine.
- Salvage 3 on the activated ability is slightly below the uncommon floor (4-5) but as a repeatable ability on a rare card, the value of 3 is reasonable for balance. However, since this is a rare card and the ability costs {2}{W} + tap + sorcery speed (significant restrictions), bumping to Salvage 4 would better match the rare identity and feel more rewarding for the investment.
- The sorcery-speed restriction and tap cost on the activated ability already provide sufficient tempo cost, so Salvage 4 on a repeatable ability remains balanced at rare.
- No mechanical errors found — Salvage is correctly used as a keyword ability with a number, and the card is in-color (W) for Salvage.

## D) Cost

- API calls: 1
- Input tokens: 1386
- Output tokens: 488
- Cost: $0.0191