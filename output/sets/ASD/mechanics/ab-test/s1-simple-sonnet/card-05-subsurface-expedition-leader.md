# Card 5: Subsurface Expedition Leader — Strategy: s1-simple-sonnet

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
  "issues_found": "[\"Salvage 6 on a rare is correct per scaling rules (6+ at rare/mythic), but Salvage 3 on the activated ability violates the scaling guidelines: Salvage 2-3 is defined as common-level scaling, and an activated ability on a rare should use a value of 4-5 (uncommon range) or 6+ to match the card's rarity. Using Salvage 3 on a rare feels underscaled and wastes design space.\", \"The activated ability cost of {2}{W}{T} is relatively cheap for repeated Salvage on a rare. Bumping to Salvage 4 keeps it in the uncommon scaling band (4-5), which is appropriate for a repeatable rare ability and adds meaningful differentiation from common Salvage cards.\", \"The encoding of the em dash in the type line appears corrupted ('Creature \u00e2\u20ac\" Human Soldier'). This is a display/encoding issue that should be corrected to 'Creature \u2014 Human Soldier'.\"]",
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{2}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When Subsurface Expedition Leader enters, salvage 6.\n{2}{W}, {T}: Salvage 4. Activate only as a sorcery.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.\""
}
```

*Tokens: 1387 in / 519 out — $0.0119*

## C) Revised Card

```json
{
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{2}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When Subsurface Expedition Leader enters, salvage 6.\n{2}{W}, {T}: Salvage 4. Activate only as a sorcery.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.\""
}
```

**Changes made:**
- [
- "
- S
- a
- l
- v
- a
- g
- e
-  
- 6
-  
- o
- n
-  
- a
-  
- r
- a
- r
- e
-  
- i
- s
-  
- c
- o
- r
- r
- e
- c
- t
-  
- p
- e
- r
-  
- s
- c
- a
- l
- i
- n
- g
-  
- r
- u
- l
- e
- s
-  
- (
- 6
- +
-  
- a
- t
-  
- r
- a
- r
- e
- /
- m
- y
- t
- h
- i
- c
- )
- ,
-  
- b
- u
- t
-  
- S
- a
- l
- v
- a
- g
- e
-  
- 3
-  
- o
- n
-  
- t
- h
- e
-  
- a
- c
- t
- i
- v
- a
- t
- e
- d
-  
- a
- b
- i
- l
- i
- t
- y
-  
- v
- i
- o
- l
- a
- t
- e
- s
-  
- t
- h
- e
-  
- s
- c
- a
- l
- i
- n
- g
-  
- g
- u
- i
- d
- e
- l
- i
- n
- e
- s
- :
-  
- S
- a
- l
- v
- a
- g
- e
-  
- 2
- -
- 3
-  
- i
- s
-  
- d
- e
- f
- i
- n
- e
- d
-  
- a
- s
-  
- c
- o
- m
- m
- o
- n
- -
- l
- e
- v
- e
- l
-  
- s
- c
- a
- l
- i
- n
- g
- ,
-  
- a
- n
- d
-  
- a
- n
-  
- a
- c
- t
- i
- v
- a
- t
- e
- d
-  
- a
- b
- i
- l
- i
- t
- y
-  
- o
- n
-  
- a
-  
- r
- a
- r
- e
-  
- s
- h
- o
- u
- l
- d
-  
- u
- s
- e
-  
- a
-  
- v
- a
- l
- u
- e
-  
- o
- f
-  
- 4
- -
- 5
-  
- (
- u
- n
- c
- o
- m
- m
- o
- n
-  
- r
- a
- n
- g
- e
- )
-  
- o
- r
-  
- 6
- +
-  
- t
- o
-  
- m
- a
- t
- c
- h
-  
- t
- h
- e
-  
- c
- a
- r
- d
- '
- s
-  
- r
- a
- r
- i
- t
- y
- .
-  
- U
- s
- i
- n
- g
-  
- S
- a
- l
- v
- a
- g
- e
-  
- 3
-  
- o
- n
-  
- a
-  
- r
- a
- r
- e
-  
- f
- e
- e
- l
- s
-  
- u
- n
- d
- e
- r
- s
- c
- a
- l
- e
- d
-  
- a
- n
- d
-  
- w
- a
- s
- t
- e
- s
-  
- d
- e
- s
- i
- g
- n
-  
- s
- p
- a
- c
- e
- .
- "
- ,
-  
- "
- T
- h
- e
-  
- a
- c
- t
- i
- v
- a
- t
- e
- d
-  
- a
- b
- i
- l
- i
- t
- y
-  
- c
- o
- s
- t
-  
- o
- f
-  
- {
- 2
- }
- {
- W
- }
- {
- T
- }
-  
- i
- s
-  
- r
- e
- l
- a
- t
- i
- v
- e
- l
- y
-  
- c
- h
- e
- a
- p
-  
- f
- o
- r
-  
- r
- e
- p
- e
- a
- t
- e
- d
-  
- S
- a
- l
- v
- a
- g
- e
-  
- o
- n
-  
- a
-  
- r
- a
- r
- e
- .
-  
- B
- u
- m
- p
- i
- n
- g
-  
- t
- o
-  
- S
- a
- l
- v
- a
- g
- e
-  
- 4
-  
- k
- e
- e
- p
- s
-  
- i
- t
-  
- i
- n
-  
- t
- h
- e
-  
- u
- n
- c
- o
- m
- m
- o
- n
-  
- s
- c
- a
- l
- i
- n
- g
-  
- b
- a
- n
- d
-  
- (
- 4
- -
- 5
- )
- ,
-  
- w
- h
- i
- c
- h
-  
- i
- s
-  
- a
- p
- p
- r
- o
- p
- r
- i
- a
- t
- e
-  
- f
- o
- r
-  
- a
-  
- r
- e
- p
- e
- a
- t
- a
- b
- l
- e
-  
- r
- a
- r
- e
-  
- a
- b
- i
- l
- i
- t
- y
-  
- a
- n
- d
-  
- a
- d
- d
- s
-  
- m
- e
- a
- n
- i
- n
- g
- f
- u
- l
-  
- d
- i
- f
- f
- e
- r
- e
- n
- t
- i
- a
- t
- i
- o
- n
-  
- f
- r
- o
- m
-  
- c
- o
- m
- m
- o
- n
-  
- S
- a
- l
- v
- a
- g
- e
-  
- c
- a
- r
- d
- s
- .
- "
- ,
-  
- "
- T
- h
- e
-  
- e
- n
- c
- o
- d
- i
- n
- g
-  
- o
- f
-  
- t
- h
- e
-  
- e
- m
-  
- d
- a
- s
- h
-  
- i
- n
-  
- t
- h
- e
-  
- t
- y
- p
- e
-  
- l
- i
- n
- e
-  
- a
- p
- p
- e
- a
- r
- s
-  
- c
- o
- r
- r
- u
- p
- t
- e
- d
-  
- (
- '
- C
- r
- e
- a
- t
- u
- r
- e
-  
- â
- €
- "
-  
- H
- u
- m
- a
- n
-  
- S
- o
- l
- d
- i
- e
- r
- '
- )
- .
-  
- T
- h
- i
- s
-  
- i
- s
-  
- a
-  
- d
- i
- s
- p
- l
- a
- y
- /
- e
- n
- c
- o
- d
- i
- n
- g
-  
- i
- s
- s
- u
- e
-  
- t
- h
- a
- t
-  
- s
- h
- o
- u
- l
- d
-  
- b
- e
-  
- c
- o
- r
- r
- e
- c
- t
- e
- d
-  
- t
- o
-  
- '
- C
- r
- e
- a
- t
- u
- r
- e
-  
- —
-  
- H
- u
- m
- a
- n
-  
- S
- o
- l
- d
- i
- e
- r
- '
- .
- "
- ]

## D) Cost

- API calls: 1
- Input tokens: 1387
- Output tokens: 519
- Cost: $0.0119