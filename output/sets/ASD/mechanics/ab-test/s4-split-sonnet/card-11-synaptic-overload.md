# Card 11: Synaptic Overload — Strategy: s4-split-sonnet

## A) Original Card

```json
{
  "name": "Synaptic Overload",
  "mana_cost": "{1}{U}",
  "cmc": 2,
  "colors": [
    "U"
  ],
  "type_line": "Instant",
  "oracle_text": "As an additional cost to cast ~, overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nCounter target spell. If you overclocked this turn, draw a card.",
  "rarity": "uncommon",
  "keywords": [
    "Overclock"
  ],
  "flavor_text": "\"The prototype neural interface worked perfectly. The subject's brain, however, did not.\" \u00e2\u20ac\u201dDr. Malleus, Cult of Science"
}
```

## B) Review Process

### Step 1: Pass 1 — Templating review

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
> Card:
> Name: Synaptic Overload
> Mana Cost: {1}{U}
> Type: Instant
> Rarity: uncommon
> Oracle Text: As an additional cost to cast ~, overclock. (Exile the top three cards of your library. You may play them until end of turn.)
> Counter target spell. If you overclocked this turn, draw a card.
> Flavor Text: "The prototype neural interface worked perfectly. The subject's brain, however, did not." â€”Dr. Malleus, Cult of Science
> 
> Check:
> - Is the oracle text valid MTG rules text using current templating conventions?
> - Does every custom mechanic (salvage, malfunction, overclock) include reminder text in parentheses on its first use?
> - Is keyword capitalization consistent?
> - Are ability words, keyword abilities, and keyword actions used correctly?
> 
> List any templating issues found, or say "PASS" if the templating is correct.

**Response:**
> Here are the templating issues found:
> 
> ---
> 
> **1. Overclock cannot function as an additional cost**
> 
> Overclock is a keyword action (like Scry or Surveil), not a cost. Additional costs must be things you *pay*, and keyword actions describe *effects* that happen. You cannot make a player "pay" a keyword action as an additional cost.
> 
> The correct approach is one of:
> - "As an additional cost to cast this spell, exile the top three cards of your library. You may play them until end of turn." (inline, no keyword in the cost line)
> - Or restructure so Overclock happens as part of the spell's effect: "Counter target spell. Then overclock. If you overclocked this turn, draw a card."
> 
> The current templating is mechanically and structurally invalid under MTG rules.
> 
> ---
> 
> **2. "If you overclocked this turn" is a problematic conditional**
> 
> The game has no clean way to track whether a keyword action was performed "this turn" across multiple spells/abilities. This phrasing works fine if Overclock happens on the same spell, but as written it implies a broader turn-wide check. If Overclock is moved to the effect line, the clause should simply read "If you do, draw a card" referring directly to the preceding Overclock instruction.
> 
> ---
> 
> **3. Reminder text placement**
> 
> If Overclock is moved to the effect line, the reminder text parenthetical follows immediately after its first instance on that line, which the current text does correctly in structure — just needs repositioning per the fix above.
> 
> ---
> 
> **4. Encoding artifact in flavor text**
> 
> The `â€"` is a character encoding error for an em dash (—). Not a rules issue, but worth flagging.
> 
> ---
> 
> **VERDICT: FAIL** — primary issue is Overclock used as an additional cost, which is invalid templating.

*Tokens: 566 in / 427 out — $0.0081*

### Step 2: Pass 2 — Mechanics review

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
> Card:
> Name: Synaptic Overload
> Mana Cost: {1}{U}
> Type: Instant
> Rarity: uncommon
> Oracle Text: As an additional cost to cast ~, overclock. (Exile the top three cards of your library. You may play them until end of turn.)
> Counter target spell. If you overclocked this turn, draw a card.
> Flavor Text: "The prototype neural interface worked perfectly. The subject's brain, however, did not." â€”Dr. Malleus, Cult of Science
> 
> Check:
> - Are there any keyword nonbos (keywords negated by other abilities on the card)?
> - If there's a conditional, can it actually be false during normal play?
> - Is this kitchen sink design (3+ unrelated effects piled together)?
> - If effects are variable, is the variability real or always the same value?
> - Does the design have a focused purpose?
> 
> List any design issues found, or say "PASS" if the design is sound.

**Response:**
> ## Design Issues Found
> 
> ### 1. Conditional Is Never False (Critical)
> 
> "If you overclocked this turn, draw a card" is **always true**. Overclock is an additional cost to cast this spell — you cannot cast Synaptic Overload without overclocking. The condition has exactly zero variance; it always draws a card. This should either be unconditional ("draw a card") or the condition needs to reference something external ("if you've overclocked twice or more this turn").
> 
> ### 2. Overclock as Additional Cost Creates a Structural Problem
> 
> Overclock is defined as a keyword **action** (something you do), not a keyword ability (something a permanent has). Putting it as an additional cost is mechanically unusual and potentially problematic — it means casting this spell **requires** you to exile the top three cards, making it a mandatory high-risk cost rather than a choice. Combined with issue #1, the card is just "counter target spell, exile top 3, draw a card" with no decision point. The overclock framing adds complexity without adding gameplay texture.
> 
> ### 3. Functional Card Is Clean But Overclock Reminder Text Is Doubled
> 
> The reminder text in the additional cost restates the full overclock definition, which already appears in the keyword glossary. Minor templating issue — precedent (e.g., Kicker) suggests the reminder text can be shortened or omitted on the card itself.
> 
> ### Overall
> The core design (counterspell + card advantage at tempo/deck cost) is focused, but the self-referential condition should be cut.

*Tokens: 575 in / 352 out — $0.0070*

### Step 3: Pass 3 — Balance review

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
> Card:
> Name: Synaptic Overload
> Mana Cost: {1}{U}
> Type: Instant
> Rarity: uncommon
> Oracle Text: As an additional cost to cast ~, overclock. (Exile the top three cards of your library. You may play them until end of turn.)
> Counter target spell. If you overclocked this turn, draw a card.
> Flavor Text: "The prototype neural interface worked perfectly. The subject's brain, however, did not." â€”Dr. Malleus, Cult of Science
> 
> Check:
> - Is the power level appropriate for the mana cost AND rarity?
> - Compare to 2-3 well-known printed MTG cards at similar mana cost and rarity.
> - Note: malfunction cards are intentionally above-rate — the delayed entry IS the drawback. Do not flag these for being above-rate.
> - Note: mythic rares are allowed to be powerful build-arounds. Do not nerf mythics to rare power level.
> 
> State whether the balance is PASS, or describe the specific balance issue with card comparisons.

**Response:**
> ## Synaptic Overload — Balance Analysis
> 
> ### Understanding the Card
> 
> This is a {1}{U} instant counterspell where:
> - **Additional cost**: Overclock (exile top 3, may play until end of turn)
> - **Effect**: Counter target spell
> - **Bonus**: Draw a card if you overclocked this turn (which you always did, since it's an additional cost)
> 
> The draw condition is effectively unconditional given the additional cost structure — overclocking is mandatory, so the draw is always live.
> 
> ### What You're Actually Getting
> 
> For {1}{U} + exile top 3: **Counter target spell + draw a card**
> 
> The "cost" is the Overclock, but Overclock is simultaneously a cost *and* a significant upside (three cards available to play). So this card gives you:
> 1. A hard counter
> 2. A free card draw
> 3. Access to three additional cards this turn
> 
> ### Comparisons
> 
> - **Counterspell** ({U}{U}): Just counters. No draw, no bonus cards. Strictly harder to cast.
> - **Dismiss** ({2}{U}{U}): Counter + draw a card. Costs four mana total.
> - **Memory Lapse** ({1}{U}): Soft counter only, no draw.
> - **Frantic Search** ({2}{U}): Draw 2, discard 2, untap lands — and this is considered very powerful.
> 
> ### The Problem
> 
> Overclocking as an **additional cost** is misleading templating — costs are supposed to be drawbacks. Overclock here functions almost entirely as **upside**. Even accepting some risk of self-mill, you're paying {1}{U} for:
> 
> - Hard counter (worth ~{U}{U} or {1}{U} with conditions)
> - Draw a card (worth ~{1}{U} alone)
> - Three extra cards accessible this turn
> 
> **This is significantly above rate for uncommon.** The Overclock risk (losing top 3 if unplayable) is real but minor in a deck built around artifacts/this mechanic.
> 
> ---
> 
> ## FAIL
> 
> **Specific issue**: The mandatory Overclock as additional cost is net positive, making this a {1}{U} hard counter that always replaces itself. Dismiss costs {2}{U}{U} for the same counter+draw effect without the Overclock upside. Recommend either raising cost to {2}{U}, making the draw conditional on something other than Overclock itself, or making Overclock optional (not additional cost) so the draw requires deliberate setup.

*Tokens: 597 in / 587 out — $0.0106*

### Step 4: Pass 4 — Revision (combining all feedback)

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
> Original card:
> Name: Synaptic Overload
> Mana Cost: {1}{U}
> Type: Instant
> Rarity: uncommon
> Oracle Text: As an additional cost to cast ~, overclock. (Exile the top three cards of your library. You may play them until end of turn.)
> Counter target spell. If you overclocked this turn, draw a card.
> Flavor Text: "The prototype neural interface worked perfectly. The subject's brain, however, did not." â€”Dr. Malleus, Cult of Science
> 
> Issues found:
> - Templating: Here are the templating issues found:
> 
> ---
> 
> **1. Overclock cannot function as an additional cost**
> 
> Overclock is a keyword action (like Scry or Surveil), not a cost. Additional costs must be things you *pay*, and keyword actions describe *effects* that happen. You cannot make a player "pay" a keyword action as an additional cost.
> 
> The correct approach is one of:
> - "As an additional cost to cast this spell, exile the top three cards of your library. You may play them until end of turn." (inline, no keyword in the cost line)
> - Or restructure so Overclock happens as part of the spell's effect: "Counter target spell. Then overclock. If you overclocked this turn, draw a card."
> 
> The current templating is mechanically and structurally invalid under MTG rules.
> 
> ---
> 
> **2. "If you overclocked this turn" is a problematic conditional**
> 
> The game has no clean way to track whether a keyword action was performed "this turn" across multiple spells/abilities. This phrasing works fine if Overclock happens on the same spell, but as written it implies a broader turn-wide check. If Overclock is moved to the effect line, the clause should simply read "If you do, draw a card" referring directly to the preceding Overclock instruction.
> 
> ---
> 
> **3. Reminder text placement**
> 
> If Overclock is moved to the effect line, the reminder text parenthetical follows immediately after its first instance on that line, which the current text does correctly in structure — just needs repositioning per the fix above.
> 
> ---
> 
> **4. Encoding artifact in flavor text**
> 
> The `â€"` is a character encoding error for an em dash (—). Not a rules issue, but worth flagging.
> 
> ---
> 
> **VERDICT: FAIL** — primary issue is Overclock used as an additional cost, which is invalid templating.
> - Mechanics: ## Design Issues Found
> 
> ### 1. Conditional Is Never False (Critical)
> 
> "If you overclocked this turn, draw a card" is **always true**. Overclock is an additional cost to cast this spell — you cannot cast Synaptic Overload without overclocking. The condition has exactly zero variance; it always draws a card. This should either be unconditional ("draw a card") or the condition needs to reference something external ("if you've overclocked twice or more this turn").
> 
> ### 2. Overclock as Additional Cost Creates a Structural Problem
> 
> Overclock is defined as a keyword **action** (something you do), not a keyword ability (something a permanent has). Putting it as an additional cost is mechanically unusual and potentially problematic — it means casting this spell **requires** you to exile the top three cards, making it a mandatory high-risk cost rather than a choice. Combined with issue #1, the card is just "counter target spell, exile top 3, draw a card" with no decision point. The overclock framing adds complexity without adding gameplay texture.
> 
> ### 3. Functional Card Is Clean But Overclock Reminder Text Is Doubled
> 
> The reminder text in the additional cost restates the full overclock definition, which already appears in the keyword glossary. Minor templating issue — precedent (e.g., Kicker) suggests the reminder text can be shortened or omitted on the card itself.
> 
> ### Overall
> The core design (counterspell + card advantage at tempo/deck cost) is focused, but the self-referential condition should be cut.
> - Balance: ## Synaptic Overload — Balance Analysis
> 
> ### Understanding the Card
> 
> This is a {1}{U} instant counterspell where:
> - **Additional cost**: Overclock (exile top 3, may play until end of turn)
> - **Effect**: Counter target spell
> - **Bonus**: Draw a card if you overclocked this turn (which you always did, since it's an additional cost)
> 
> The draw condition is effectively unconditional given the additional cost structure — overclocking is mandatory, so the draw is always live.
> 
> ### What You're Actually Getting
> 
> For {1}{U} + exile top 3: **Counter target spell + draw a card**
> 
> The "cost" is the Overclock, but Overclock is simultaneously a cost *and* a significant upside (three cards available to play). So this card gives you:
> 1. A hard counter
> 2. A free card draw
> 3. Access to three additional cards this turn
> 
> ### Comparisons
> 
> - **Counterspell** ({U}{U}): Just counters. No draw, no bonus cards. Strictly harder to cast.
> - **Dismiss** ({2}{U}{U}): Counter + draw a card. Costs four mana total.
> - **Memory Lapse** ({1}{U}): Soft counter only, no draw.
> - **Frantic Search** ({2}{U}): Draw 2, discard 2, untap lands — and this is considered very powerful.
> 
> ### The Problem
> 
> Overclocking as an **additional cost** is misleading templating — costs are supposed to be drawbacks. Overclock here functions almost entirely as **upside**. Even accepting some risk of self-mill, you're paying {1}{U} for:
> 
> - Hard counter (worth ~{U}{U} or {1}{U} with conditions)
> - Draw a card (worth ~{1}{U} alone)
> - Three extra cards accessible this turn
> 
> **This is significantly above rate for uncommon.** The Overclock risk (losing top 3 if unplayable) is real but minor in a deck built around artifacts/this mechanic.
> 
> ---
> 
> ## FAIL
> 
> **Specific issue**: The mandatory Overclock as additional cost is net positive, making this a {1}{U} hard counter that always replaces itself. Dismiss costs {2}{U}{U} for the same counter+draw effect without the Overclock upside. Recommend either raising cost to {2}{U}, making the draw conditional on something other than Overclock itself, or making Overclock optional (not additional cost) so the draw requires deliberate setup.
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": "[\"Overclock cannot function as an additional cost \u2014 it is a keyword action, not a payable cost. Moved to effect line.\", \"The draw condition 'if you overclocked this turn' was always true due to mandatory additional cost structure, making the conditional meaningless. Replaced with 'if you do' referencing the in-line Overclock.\", \"Balance: mandatory Overclock as additional cost was net positive (counter + draw + 3 accessible cards for {1}{U}), well above rate. Raised mana cost to {2}{U} to compensate.\", \"Flavor text encoding error: \u00e2\u20ac\" replaced with proper em dash \u2014.\"]",
  "name": "Synaptic Overload",
  "mana_cost": "{2}{U}",
  "type_line": "Instant",
  "oracle_text": "Counter target spell. Then overclock. If you do, draw a card. (To overclock, exile the top three cards of your library. You may play them until end of turn.)",
  "rarity": "uncommon",
  "flavor_text": "\"The prototype neural interface worked perfectly. The subject's brain, however, did not.\" \u2014Dr. Malleus, Cult of Science"
}
```

*Tokens: 2787 in / 403 out — $0.0144*

## C) Revised Card

```json
{
  "name": "Synaptic Overload",
  "mana_cost": "{2}{U}",
  "type_line": "Instant",
  "oracle_text": "Counter target spell. Then overclock. If you do, draw a card. (To overclock, exile the top three cards of your library. You may play them until end of turn.)",
  "rarity": "uncommon",
  "flavor_text": "\"The prototype neural interface worked perfectly. The subject's brain, however, did not.\" \u2014Dr. Malleus, Cult of Science"
}
```

**Changes made:**
- [
- "
- O
- v
- e
- r
- c
- l
- o
- c
- k
-  
- c
- a
- n
- n
- o
- t
-  
- f
- u
- n
- c
- t
- i
- o
- n
-  
- a
- s
-  
- a
- n
-  
- a
- d
- d
- i
- t
- i
- o
- n
- a
- l
-  
- c
- o
- s
- t
-  
- —
-  
- i
- t
-  
- i
- s
-  
- a
-  
- k
- e
- y
- w
- o
- r
- d
-  
- a
- c
- t
- i
- o
- n
- ,
-  
- n
- o
- t
-  
- a
-  
- p
- a
- y
- a
- b
- l
- e
-  
- c
- o
- s
- t
- .
-  
- M
- o
- v
- e
- d
-  
- t
- o
-  
- e
- f
- f
- e
- c
- t
-  
- l
- i
- n
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
- d
- r
- a
- w
-  
- c
- o
- n
- d
- i
- t
- i
- o
- n
-  
- '
- i
- f
-  
- y
- o
- u
-  
- o
- v
- e
- r
- c
- l
- o
- c
- k
- e
- d
-  
- t
- h
- i
- s
-  
- t
- u
- r
- n
- '
-  
- w
- a
- s
-  
- a
- l
- w
- a
- y
- s
-  
- t
- r
- u
- e
-  
- d
- u
- e
-  
- t
- o
-  
- m
- a
- n
- d
- a
- t
- o
- r
- y
-  
- a
- d
- d
- i
- t
- i
- o
- n
- a
- l
-  
- c
- o
- s
- t
-  
- s
- t
- r
- u
- c
- t
- u
- r
- e
- ,
-  
- m
- a
- k
- i
- n
- g
-  
- t
- h
- e
-  
- c
- o
- n
- d
- i
- t
- i
- o
- n
- a
- l
-  
- m
- e
- a
- n
- i
- n
- g
- l
- e
- s
- s
- .
-  
- R
- e
- p
- l
- a
- c
- e
- d
-  
- w
- i
- t
- h
-  
- '
- i
- f
-  
- y
- o
- u
-  
- d
- o
- '
-  
- r
- e
- f
- e
- r
- e
- n
- c
- i
- n
- g
-  
- t
- h
- e
-  
- i
- n
- -
- l
- i
- n
- e
-  
- O
- v
- e
- r
- c
- l
- o
- c
- k
- .
- "
- ,
-  
- "
- B
- a
- l
- a
- n
- c
- e
- :
-  
- m
- a
- n
- d
- a
- t
- o
- r
- y
-  
- O
- v
- e
- r
- c
- l
- o
- c
- k
-  
- a
- s
-  
- a
- d
- d
- i
- t
- i
- o
- n
- a
- l
-  
- c
- o
- s
- t
-  
- w
- a
- s
-  
- n
- e
- t
-  
- p
- o
- s
- i
- t
- i
- v
- e
-  
- (
- c
- o
- u
- n
- t
- e
- r
-  
- +
-  
- d
- r
- a
- w
-  
- +
-  
- 3
-  
- a
- c
- c
- e
- s
- s
- i
- b
- l
- e
-  
- c
- a
- r
- d
- s
-  
- f
- o
- r
-  
- {
- 1
- }
- {
- U
- }
- )
- ,
-  
- w
- e
- l
- l
-  
- a
- b
- o
- v
- e
-  
- r
- a
- t
- e
- .
-  
- R
- a
- i
- s
- e
- d
-  
- m
- a
- n
- a
-  
- c
- o
- s
- t
-  
- t
- o
-  
- {
- 2
- }
- {
- U
- }
-  
- t
- o
-  
- c
- o
- m
- p
- e
- n
- s
- a
- t
- e
- .
- "
- ,
-  
- "
- F
- l
- a
- v
- o
- r
-  
- t
- e
- x
- t
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
- e
- r
- r
- o
- r
- :
-  
- â
- €
- "
-  
- r
- e
- p
- l
- a
- c
- e
- d
-  
- w
- i
- t
- h
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
- —
- .
- "
- ]

## D) Cost

- API calls: 4
- Input tokens: 4525
- Output tokens: 1769
- Cost: $0.0401