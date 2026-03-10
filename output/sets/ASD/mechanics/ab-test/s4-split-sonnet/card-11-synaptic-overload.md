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
  "flavor_text": "\"The prototype neural interface worked perfectly. The subject's brain, however, did not.\" \u00ef\u00bf\u00bdDr. Malleus, Cult of Science"
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
> Flavor Text: "The prototype neural interface worked perfectly. The subject's brain, however, did not." ï¿½Dr. Malleus, Cult of Science
> 
> Check:
> - Is the oracle text valid MTG rules text using current templating conventions?
> - Does every custom mechanic (salvage, malfunction, overclock) include reminder text in parentheses on its first use?
> - Is keyword capitalization consistent?
> - Are ability words, keyword abilities, and keyword actions used correctly?
> 
> List any templating issues found, or say "PASS" if the templating is correct.

**Response:**
> Looking at this card, I've found several templating issues:
> 
> **ISSUES FOUND:**
> 
> 1. **Incorrect overclock templating**: The reminder text should not appear in the additional cost. It should be on the keyword action itself. The correct templating should be:
>    ```
>    As an additional cost to cast ~, overclock.
>    Overclock. (Exile the top three cards of your library. You may play them until end of turn.)
>    Counter target spell. If you overclocked this turn, draw a card.
>    ```
> 
> 2. **Missing period after reminder text**: The reminder text should end with a period: `(Exile the top three cards of your library. You may play them until end of turn.)`
> 
> 3. **Flavor text encoding issue**: There's a character encoding error in the flavor text: `ï¿½Dr. Malleus` should be `—Dr. Malleus` (em dash).
> 
> 4. **Redundant reminder text**: Since overclock appears twice (in the cost and as the action), the reminder text should only appear once on the keyword action line, not in the additional cost.
> 
> The corrected oracle text should read:
> ```
> As an additional cost to cast ~, overclock.
> Overclock. (Exile the top three cards of your library. You may play them until end of turn.)
> Counter target spell. If you overclocked this turn, draw a card.
> ```
> 
> All other aspects (keyword capitalization, mechanic usage) are correct.

*Tokens: 567 in / 338 out — $0.0068*

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
> Flavor Text: "The prototype neural interface worked perfectly. The subject's brain, however, did not." ï¿½Dr. Malleus, Cult of Science
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
> Looking at this design systematically:
> 
> **Keyword nonbos:** None present. The overclock mechanic works as intended.
> 
> **Conditional analysis:** The "If you overclocked this turn" conditional can actually be false during normal play. Since overclock is an additional cost, you could theoretically cast this spell without paying the additional cost (though you'd miss the card draw). This creates meaningful decision space.
> 
> **Kitchen sink check:** This is not kitchen sink design. The two effects (counterspell + conditional card draw) are closely related and thematically cohesive around the "overload/overclock" concept.
> 
> **Variability:** The overclock effect has real variability - you always exile exactly 3 cards, but what you can play from them varies significantly.
> 
> **Focused purpose:** Yes, this is a counterspell with an optional risk/reward upgrade mechanic that fits the set's themes.
> 
> **Design Issues Found:**
> 
> 1. **Wording inconsistency**: The reminder text says "If you overclocked this turn" but overclock is defined as a keyword action, not a general game state. The wording should probably be "If you paid the overclock cost" or similar, since you're checking if you paid the additional cost for this specific spell.
> 
> 2. **Minor templating**: The conditional references "this turn" when it should reference the specific casting of this spell, since overclock is tied to casting this particular spell.
> 
> The core design is sound, but the conditional wording needs refinement for clarity and precision.
> 
> **ISSUES FOUND** - templating needs adjustment for the conditional check.

*Tokens: 576 in / 353 out — $0.0070*

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
> Flavor Text: "The prototype neural interface worked perfectly. The subject's brain, however, did not." ï¿½Dr. Malleus, Cult of Science
> 
> Check:
> - Is the power level appropriate for the mana cost AND rarity?
> - Compare to 2-3 well-known printed MTG cards at similar mana cost and rarity.
> - Note: malfunction cards are intentionally above-rate — the delayed entry IS the drawback. Do not flag these for being above-rate.
> - Note: mythic rares are allowed to be powerful build-arounds. Do not nerf mythics to rare power level.
> 
> State whether the balance is PASS, or describe the specific balance issue with card comparisons.

**Response:**
> Looking at **Synaptic Overload**, I need to evaluate both the baseline effect and the overclock upside.
> 
> **Power Level Analysis:**
> 
> The baseline is a 2-mana counterspell, which is historically weak (see Cancel, Essence Scatter). However, the overclock cost creates significant complexity in evaluation.
> 
> **Overclock Cost-Benefit:**
> - **Cost**: Exile 3 cards from library (potential card disadvantage)
> - **Benefit**: Access to 3 cards until end of turn + draw a card
> - **Net**: If you can't play the exiled cards, you're down 2 cards total for a counterspell + draw
> 
> **Comparable Cards:**
> - **Counterspell** (1U): Clean counter, much more reliable
> - **Arcane Denial** (1U): Counters + draws, but gives opponent cards too
> - **Memory Deluge** (2UU): Similar card selection/advantage engine at higher cost
> 
> **The Problem:**
> This creates a feast-or-famine dynamic that's problematic at uncommon:
> - **Best case**: Counter + draw + play 2-3 relevant cards = massive advantage
> - **Worst case**: Counter + draw + exile 3 unplayable cards = significant disadvantage
> - **Complexity**: Requires extensive board state evaluation every time
> 
> The variance is too extreme for uncommon rarity. When it works, it's substantially better than premium counterspells. When it doesn't, it's actively bad.
> 
> **Comparison**: Premium 2-mana counters like Counterspell or Mana Leak provide consistent, predictable effects. This swings too wildly between "broken" and "terrible."
> 
> **FAIL** - The power level variance is inappropriate for uncommon. Either reduce to 1U with smaller overclock benefit, or increase to rare with the high-variance design intact.

*Tokens: 598 in / 426 out — $0.0082*

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
> Flavor Text: "The prototype neural interface worked perfectly. The subject's brain, however, did not." ï¿½Dr. Malleus, Cult of Science
> 
> Issues found:
> - Templating: Looking at this card, I've found several templating issues:
> 
> **ISSUES FOUND:**
> 
> 1. **Incorrect overclock templating**: The reminder text should not appear in the additional cost. It should be on the keyword action itself. The correct templating should be:
>    ```
>    As an additional cost to cast ~, overclock.
>    Overclock. (Exile the top three cards of your library. You may play them until end of turn.)
>    Counter target spell. If you overclocked this turn, draw a card.
>    ```
> 
> 2. **Missing period after reminder text**: The reminder text should end with a period: `(Exile the top three cards of your library. You may play them until end of turn.)`
> 
> 3. **Flavor text encoding issue**: There's a character encoding error in the flavor text: `ï¿½Dr. Malleus` should be `—Dr. Malleus` (em dash).
> 
> 4. **Redundant reminder text**: Since overclock appears twice (in the cost and as the action), the reminder text should only appear once on the keyword action line, not in the additional cost.
> 
> The corrected oracle text should read:
> ```
> As an additional cost to cast ~, overclock.
> Overclock. (Exile the top three cards of your library. You may play them until end of turn.)
> Counter target spell. If you overclocked this turn, draw a card.
> ```
> 
> All other aspects (keyword capitalization, mechanic usage) are correct.
> - Mechanics: Looking at this design systematically:
> 
> **Keyword nonbos:** None present. The overclock mechanic works as intended.
> 
> **Conditional analysis:** The "If you overclocked this turn" conditional can actually be false during normal play. Since overclock is an additional cost, you could theoretically cast this spell without paying the additional cost (though you'd miss the card draw). This creates meaningful decision space.
> 
> **Kitchen sink check:** This is not kitchen sink design. The two effects (counterspell + conditional card draw) are closely related and thematically cohesive around the "overload/overclock" concept.
> 
> **Variability:** The overclock effect has real variability - you always exile exactly 3 cards, but what you can play from them varies significantly.
> 
> **Focused purpose:** Yes, this is a counterspell with an optional risk/reward upgrade mechanic that fits the set's themes.
> 
> **Design Issues Found:**
> 
> 1. **Wording inconsistency**: The reminder text says "If you overclocked this turn" but overclock is defined as a keyword action, not a general game state. The wording should probably be "If you paid the overclock cost" or similar, since you're checking if you paid the additional cost for this specific spell.
> 
> 2. **Minor templating**: The conditional references "this turn" when it should reference the specific casting of this spell, since overclock is tied to casting this particular spell.
> 
> The core design is sound, but the conditional wording needs refinement for clarity and precision.
> 
> **ISSUES FOUND** - templating needs adjustment for the conditional check.
> - Balance: Looking at **Synaptic Overload**, I need to evaluate both the baseline effect and the overclock upside.
> 
> **Power Level Analysis:**
> 
> The baseline is a 2-mana counterspell, which is historically weak (see Cancel, Essence Scatter). However, the overclock cost creates significant complexity in evaluation.
> 
> **Overclock Cost-Benefit:**
> - **Cost**: Exile 3 cards from library (potential card disadvantage)
> - **Benefit**: Access to 3 cards until end of turn + draw a card
> - **Net**: If you can't play the exiled cards, you're down 2 cards total for a counterspell + draw
> 
> **Comparable Cards:**
> - **Counterspell** (1U): Clean counter, much more reliable
> - **Arcane Denial** (1U): Counters + draws, but gives opponent cards too
> - **Memory Deluge** (2UU): Similar card selection/advantage engine at higher cost
> 
> **The Problem:**
> This creates a feast-or-famine dynamic that's problematic at uncommon:
> - **Best case**: Counter + draw + play 2-3 relevant cards = massive advantage
> - **Worst case**: Counter + draw + exile 3 unplayable cards = significant disadvantage
> - **Complexity**: Requires extensive board state evaluation every time
> 
> The variance is too extreme for uncommon rarity. When it works, it's substantially better than premium counterspells. When it doesn't, it's actively bad.
> 
> **Comparison**: Premium 2-mana counters like Counterspell or Mana Leak provide consistent, predictable effects. This swings too wildly between "broken" and "terrible."
> 
> **FAIL** - The power level variance is inappropriate for uncommon. Either reduce to 1U with smaller overclock benefit, or increase to rare with the high-variance design intact.
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Incorrect overclock templating with redundant reminder text",
    "Missing period after reminder text",
    "Flavor text encoding issue (em dash)",
    "Wording inconsistency in conditional check",
    "Power level variance too extreme for uncommon rarity"
  ],
  "name": "Synaptic Overload",
  "mana_cost": "{U}",
  "type_line": "Instant",
  "oracle_text": "As an additional cost to cast this spell, overclock.\nOverclock. (Exile the top three cards of your library. You may play them until end of turn.)\nCounter target spell. If you paid the overclock cost, draw a card.",
  "rarity": "uncommon",
  "flavor_text": "\"The prototype neural interface worked perfectly. The subject's brain, however, did not.\" \u2014Dr. Malleus, Cult of Science"
}
```

*Tokens: 2266 in / 323 out — $0.0116*

## C) Revised Card

```json
{
  "name": "Synaptic Overload",
  "mana_cost": "{U}",
  "type_line": "Instant",
  "oracle_text": "As an additional cost to cast this spell, overclock.\nOverclock. (Exile the top three cards of your library. You may play them until end of turn.)\nCounter target spell. If you paid the overclock cost, draw a card.",
  "rarity": "uncommon",
  "flavor_text": "\"The prototype neural interface worked perfectly. The subject's brain, however, did not.\" \u2014Dr. Malleus, Cult of Science"
}
```

**Changes made:**
- Incorrect overclock templating with redundant reminder text
- Missing period after reminder text
- Flavor text encoding issue (em dash)
- Wording inconsistency in conditional check
- Power level variance too extreme for uncommon rarity

## D) Cost

- API calls: 4
- Input tokens: 4007
- Output tokens: 1440
- Cost: $0.0336