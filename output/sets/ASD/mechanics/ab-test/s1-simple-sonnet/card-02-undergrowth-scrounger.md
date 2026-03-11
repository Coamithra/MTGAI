# Card 2: Undergrowth Scrounger — Strategy: s1-simple-sonnet

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
  "issues_found": "[\"Salvage scaling violation: Salvage 3 is listed as uncommon-floor (uncommon range is 4-5; common range is 2-3). A common card should use Salvage 2 or Salvage 3 only if 3 is considered the top of the common range. Re-reading the spec: common is 2-3, so Salvage 3 is technically permissible at common, BUT the trigger is a death trigger on a 2/1 for {1}{G} \u2014 already a reasonable rate. Salvage 3 on death at common is likely too efficient as card advantage relative to common power level expectations; Salvage 2 is the safer, more appropriate common-tier choice.\", \"Encoding artifact: The type line contains a garbled character ('\u00e2\u20ac\"') instead of a proper em dash ('\u2014'). This must be corrected to 'Creature \u2014 Human Scout'.\"]",
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

*Tokens: 1360 in / 510 out — $0.0117*

## C) Revised Card

```json
{
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
- s
- c
- a
- l
- i
- n
- g
-  
- v
- i
- o
- l
- a
- t
- i
- o
- n
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
- 3
-  
- i
- s
-  
- l
- i
- s
- t
- e
- d
-  
- a
- s
-  
- u
- n
- c
- o
- m
- m
- o
- n
- -
- f
- l
- o
- o
- r
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
-  
- i
- s
-  
- 4
- -
- 5
- ;
-  
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
-  
- i
- s
-  
- 2
- -
- 3
- )
- .
-  
- A
-  
- c
- o
- m
- m
- o
- n
-  
- c
- a
- r
- d
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
- S
- a
- l
- v
- a
- g
- e
-  
- 2
-  
- o
- r
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
- l
- y
-  
- i
- f
-  
- 3
-  
- i
- s
-  
- c
- o
- n
- s
- i
- d
- e
- r
- e
- d
-  
- t
- h
- e
-  
- t
- o
- p
-  
- o
- f
-  
- t
- h
- e
-  
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
- .
-  
- R
- e
- -
- r
- e
- a
- d
- i
- n
- g
-  
- t
- h
- e
-  
- s
- p
- e
- c
- :
-  
- c
- o
- m
- m
- o
- n
-  
- i
- s
-  
- 2
- -
- 3
- ,
-  
- s
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
- 3
-  
- i
- s
-  
- t
- e
- c
- h
- n
- i
- c
- a
- l
- l
- y
-  
- p
- e
- r
- m
- i
- s
- s
- i
- b
- l
- e
-  
- a
- t
-  
- c
- o
- m
- m
- o
- n
- ,
-  
- B
- U
- T
-  
- t
- h
- e
-  
- t
- r
- i
- g
- g
- e
- r
-  
- i
- s
-  
- a
-  
- d
- e
- a
- t
- h
-  
- t
- r
- i
- g
- g
- e
- r
-  
- o
- n
-  
- a
-  
- 2
- /
- 1
-  
- f
- o
- r
-  
- {
- 1
- }
- {
- G
- }
-  
- —
-  
- a
- l
- r
- e
- a
- d
- y
-  
- a
-  
- r
- e
- a
- s
- o
- n
- a
- b
- l
- e
-  
- r
- a
- t
- e
- .
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
- d
- e
- a
- t
- h
-  
- a
- t
-  
- c
- o
- m
- m
- o
- n
-  
- i
- s
-  
- l
- i
- k
- e
- l
- y
-  
- t
- o
- o
-  
- e
- f
- f
- i
- c
- i
- e
- n
- t
-  
- a
- s
-  
- c
- a
- r
- d
-  
- a
- d
- v
- a
- n
- t
- a
- g
- e
-  
- r
- e
- l
- a
- t
- i
- v
- e
-  
- t
- o
-  
- c
- o
- m
- m
- o
- n
-  
- p
- o
- w
- e
- r
-  
- l
- e
- v
- e
- l
-  
- e
- x
- p
- e
- c
- t
- a
- t
- i
- o
- n
- s
- ;
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
-  
- i
- s
-  
- t
- h
- e
-  
- s
- a
- f
- e
- r
- ,
-  
- m
- o
- r
- e
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
- c
- o
- m
- m
- o
- n
- -
- t
- i
- e
- r
-  
- c
- h
- o
- i
- c
- e
- .
- "
- ,
-  
- "
- E
- n
- c
- o
- d
- i
- n
- g
-  
- a
- r
- t
- i
- f
- a
- c
- t
- :
-  
- T
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
- c
- o
- n
- t
- a
- i
- n
- s
-  
- a
-  
- g
- a
- r
- b
- l
- e
- d
-  
- c
- h
- a
- r
- a
- c
- t
- e
- r
-  
- (
- '
- â
- €
- "
- '
- )
-  
- i
- n
- s
- t
- e
- a
- d
-  
- o
- f
-  
- a
-  
- p
- r
- o
- p
- e
- r
-  
- e
- m
-  
- d
- a
- s
- h
-  
- (
- '
- —
- '
- )
- .
-  
- T
- h
- i
- s
-  
- m
- u
- s
- t
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
- c
- o
- u
- t
- '
- .
- "
- ]

## D) Cost

- API calls: 1
- Input tokens: 1360
- Output tokens: 510
- Cost: $0.0117