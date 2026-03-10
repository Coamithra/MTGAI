# Card 15: Archscientist Vex, the Unbound — Strategy: s8-split-opus

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
> Check:
> - Is the oracle text valid MTG rules text using current templating conventions?
> - Does every custom mechanic (salvage, malfunction, overclock) include reminder text in parentheses on its first use?
> - Is keyword capitalization consistent?
> - Are ability words, keyword abilities, and keyword actions used correctly?
> 
> List any templating issues found, or say "PASS" if the templating is correct.

**Response:**
> The templating has several issues:
> 
> 1. **"Overclock" needs to be properly formatted as a keyword action.** The current reminder text is formatted incorrectly. It should read:
>    - "Cards you overclock cost {2} less to cast." (where overclock would have its reminder text on first use)
>    
> 2. **The reminder text for overclock should be properly formatted.** It should read:
>    - "(To overclock, exile the top three cards of your library. You may play them until end of turn.)"
> 
> 3. **"Cards exiled with overclock" is non-standard templating.** This should reference the action more directly. Standard templating would be something like "Cards you overclock" or "Cards exiled this way" if referring to a specific overclock instance.
> 
> 4. **The second ability needs clarification.** It should specify "a spell from exile" or "a spell you overclocked" for clarity.
> 
> The corrected oracle text should read:
> 
> ```
> Flying
> Cards you overclock cost {2} less to cast. (To overclock, exile the top three cards of your library. You may play them until end of turn.)
> Whenever you cast a spell from exile, if you overclocked it, copy that spell. You may choose new targets for the copy.
> ```
> 
> Or alternatively:
> 
> ```
> Flying
> Overclock costs you pay cost {2} less. (To overclock, exile the top three cards of your library. You may play them until end of turn.)
> Whenever you cast a spell from exile, if it was exiled by an overclock effect, copy that spell. You may choose new targets for the copy.
> ```

*Tokens: 595 in / 374 out — $0.0370*

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
> Check:
> - Are there any keyword nonbos (keywords negated by other abilities on the card)?
> - If there's a conditional, can it actually be false during normal play?
> - Is this kitchen sink design (3+ unrelated effects piled together)?
> - If effects are variable, is the variability real or always the same value?
> - Does the design have a focused purpose?
> 
> List any design issues found, or say "PASS" if the design is sound.

**Response:**
> Looking at this card, I need to check for design issues:
> 
> **Design Issues Found:**
> 
> 1. **Parenthetical Reminder Text in Oracle Text**: The overclock reminder text "(exile the top three cards of your library, you may play them until end of turn)" should not appear in the oracle text of a mythic rare card. At mythic, keyword abilities should appear without reminder text, especially for a complex mechanic like overclock.
> 
> 2. **Kitchen Sink Design**: While the three abilities (flying, cost reduction, copying) all support an "overclock matters" theme, the card is doing a lot:
>    - Evasive body with flying
>    - Cost reduction for overclocked cards
>    - Copying overclocked spells
>    
>    This borders on kitchen sink design, though it's arguably focused enough around the overclock theme to be acceptable.
> 
> 3. **Memory Issues**: This creates a complex board state where players need to track:
>    - Which exiled cards were exiled with overclock vs other effects
>    - The cost reduction applying to those specific cards
>    - Multiple copies of spells
> 
> **Additional Observations:**
> - The 3/4 flying body for 4 mana is already a decent rate before the abilities
> - The cost reduction + copying creates explosive turns that could be problematic
> - The design strongly pushes players to overclock repeatedly, which aligns well with the UR color pair
> 
> **Verdict:** The reminder text issue definitely needs to be fixed. The complexity and power level concerns are notable but may be acceptable for a mythic rare build-around commander.

*Tokens: 604 in / 350 out — $0.0353*

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
> Check:
> - Is the power level appropriate for the mana cost AND rarity?
> - Compare to 2-3 well-known printed MTG cards at similar mana cost and rarity.
> - Note: malfunction cards are intentionally above-rate — the delayed entry IS the drawback. Do not flag these for being above-rate.
> - Note: mythic rares are allowed to be powerful build-arounds. Do not nerf mythics to rare power level.
> 
> State whether the balance is PASS, or describe the specific balance issue with card comparisons.

**Response:**
> **FAIL** - This card is significantly overpowered for its mana cost, even at mythic rare.
> 
> **Power Level Issues:**
> 
> 1. **Stats vs Similar Cards**: At 4 mana for a 3/4 flyer, this already has an efficient body. Compare to:
>    - [[Crackling Drake]] (UURR) - 4 mana for a */* flyer that draws a card
>    - [[Niv-Mizzet, Parun]] (UUURRR) - 6 mana for a 5/5 flyer with powerful abilities
>    - [[Galazeth Prismari]] (2UR) - 4 mana for a 3/4 flyer with artifact synergy
> 
> 2. **Ability Power**: The combination of cost reduction AND copying is exponentially powerful:
>    - Cost reduction of 2 makes this effectively ramp you by 6 mana per overclock activation
>    - Copying every spell cast this way doubles that value
>    - This can easily generate 10+ mana worth of value in a single turn
> 
> 3. **Comparison to Similar Effects**:
>    - [[Baral, Chief of Compliance]] - 2 mana for just 1 mana cost reduction on instants/sorceries
>    - [[Goblin Electromancer]] - 2 mana for just 1 mana cost reduction
>    - [[God-Eternal Kefnet]] - 4 mana for copying only the first instant/sorcery drawn each turn
> 
> **Specific Balance Concerns:**
> - Turn 5: Overclock, cast 3 spells for free/cheap, get 3 copies = potentially 6 spells in one turn
> - The permanent cost reduction makes this backbreaking with any overclock effects
> - No restriction on spell types means this works with permanents, creating overwhelming board states
> 
> **Recommendation**: Either remove the cost reduction OR the copying effect, not both. Even then, the remaining ability might need to be toned down (copy only instants/sorceries, or reduce cost by only 1).

*Tokens: 626 in / 488 out — $0.0460*

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
> Issues found:
> - Templating: The templating has several issues:
> 
> 1. **"Overclock" needs to be properly formatted as a keyword action.** The current reminder text is formatted incorrectly. It should read:
>    - "Cards you overclock cost {2} less to cast." (where overclock would have its reminder text on first use)
>    
> 2. **The reminder text for overclock should be properly formatted.** It should read:
>    - "(To overclock, exile the top three cards of your library. You may play them until end of turn.)"
> 
> 3. **"Cards exiled with overclock" is non-standard templating.** This should reference the action more directly. Standard templating would be something like "Cards you overclock" or "Cards exiled this way" if referring to a specific overclock instance.
> 
> 4. **The second ability needs clarification.** It should specify "a spell from exile" or "a spell you overclocked" for clarity.
> 
> The corrected oracle text should read:
> 
> ```
> Flying
> Cards you overclock cost {2} less to cast. (To overclock, exile the top three cards of your library. You may play them until end of turn.)
> Whenever you cast a spell from exile, if you overclocked it, copy that spell. You may choose new targets for the copy.
> ```
> 
> Or alternatively:
> 
> ```
> Flying
> Overclock costs you pay cost {2} less. (To overclock, exile the top three cards of your library. You may play them until end of turn.)
> Whenever you cast a spell from exile, if it was exiled by an overclock effect, copy that spell. You may choose new targets for the copy.
> ```
> - Mechanics: Looking at this card, I need to check for design issues:
> 
> **Design Issues Found:**
> 
> 1. **Parenthetical Reminder Text in Oracle Text**: The overclock reminder text "(exile the top three cards of your library, you may play them until end of turn)" should not appear in the oracle text of a mythic rare card. At mythic, keyword abilities should appear without reminder text, especially for a complex mechanic like overclock.
> 
> 2. **Kitchen Sink Design**: While the three abilities (flying, cost reduction, copying) all support an "overclock matters" theme, the card is doing a lot:
>    - Evasive body with flying
>    - Cost reduction for overclocked cards
>    - Copying overclocked spells
>    
>    This borders on kitchen sink design, though it's arguably focused enough around the overclock theme to be acceptable.
> 
> 3. **Memory Issues**: This creates a complex board state where players need to track:
>    - Which exiled cards were exiled with overclock vs other effects
>    - The cost reduction applying to those specific cards
>    - Multiple copies of spells
> 
> **Additional Observations:**
> - The 3/4 flying body for 4 mana is already a decent rate before the abilities
> - The cost reduction + copying creates explosive turns that could be problematic
> - The design strongly pushes players to overclock repeatedly, which aligns well with the UR color pair
> 
> **Verdict:** The reminder text issue definitely needs to be fixed. The complexity and power level concerns are notable but may be acceptable for a mythic rare build-around commander.
> - Balance: **FAIL** - This card is significantly overpowered for its mana cost, even at mythic rare.
> 
> **Power Level Issues:**
> 
> 1. **Stats vs Similar Cards**: At 4 mana for a 3/4 flyer, this already has an efficient body. Compare to:
>    - [[Crackling Drake]] (UURR) - 4 mana for a */* flyer that draws a card
>    - [[Niv-Mizzet, Parun]] (UUURRR) - 6 mana for a 5/5 flyer with powerful abilities
>    - [[Galazeth Prismari]] (2UR) - 4 mana for a 3/4 flyer with artifact synergy
> 
> 2. **Ability Power**: The combination of cost reduction AND copying is exponentially powerful:
>    - Cost reduction of 2 makes this effectively ramp you by 6 mana per overclock activation
>    - Copying every spell cast this way doubles that value
>    - This can easily generate 10+ mana worth of value in a single turn
> 
> 3. **Comparison to Similar Effects**:
>    - [[Baral, Chief of Compliance]] - 2 mana for just 1 mana cost reduction on instants/sorceries
>    - [[Goblin Electromancer]] - 2 mana for just 1 mana cost reduction
>    - [[God-Eternal Kefnet]] - 4 mana for copying only the first instant/sorcery drawn each turn
> 
> **Specific Balance Concerns:**
> - Turn 5: Overclock, cast 3 spells for free/cheap, get 3 copies = potentially 6 spells in one turn
> - The permanent cost reduction makes this backbreaking with any overclock effects
> - No restriction on spell types means this works with permanents, creating overwhelming board states
> 
> **Recommendation**: Either remove the cost reduction OR the copying effect, not both. Even then, the remaining ability might need to be toned down (copy only instants/sorceries, or reduce cost by only 1).
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Incorrect templating of overclock reminder text in oracle text",
    "Reminder text should not appear on mythic rare cards",
    "Card is significantly overpowered with both cost reduction AND copying effects",
    "The combination creates explosive turns generating 10+ mana of value"
  ],
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Flying\nWhenever you cast a spell from exile, if it was exiled by an overclock effect, copy that spell. You may choose new targets for the copy.",
  "rarity": "mythic",
  "power": "3",
  "toughness": "4",
  "flavor_text": "I have transcended the limitations of sanity, safety, and the laws of thermodynamics."
}
```

*Tokens: 2389 in / 353 out — $0.0623*

## C) Revised Card

```json
{
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Flying\nWhenever you cast a spell from exile, if it was exiled by an overclock effect, copy that spell. You may choose new targets for the copy.",
  "rarity": "mythic",
  "power": "3",
  "toughness": "4",
  "flavor_text": "I have transcended the limitations of sanity, safety, and the laws of thermodynamics."
}
```

**Changes made:**
- Incorrect templating of overclock reminder text in oracle text
- Reminder text should not appear on mythic rare cards
- Card is significantly overpowered with both cost reduction AND copying effects
- The combination creates explosive turns generating 10+ mana of value

## D) Cost

- API calls: 4
- Input tokens: 4214
- Output tokens: 1565
- Cost: $0.1806