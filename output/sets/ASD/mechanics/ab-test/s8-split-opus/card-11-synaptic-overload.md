# Card 11: Synaptic Overload — Strategy: s8-split-opus

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
> Several templating issues found:
> 
> 1. **"As an additional cost to cast ~"** - The tilde (~) should be replaced with "this spell" in modern templating.
> 
> 2. **"If you overclocked this turn"** - This doesn't work as written. Overclock isn't a player action that can be tracked this way. The card seems to want to check if you overclocked as part of casting this spell, but the templating doesn't support that.
> 
> 3. **Reminder text placement** - While the reminder text for overclock is included, the current wording creates a rules problem. The way it's written, you overclock as an additional cost, then the spell checks if you overclocked this turn, which is redundant and doesn't work with the cost/effect structure.
> 
> 4. **Flavor text** - The special character "ï¿½" appears instead of an em dash before "Dr. Malleus"
> 
> Suggested fix for the mechanical issue:
> - Option 1: "Counter target spell. Draw a card." (Since you always overclock to cast this)
> - Option 2: Make overclock part of the effect rather than a cost
> - Option 3: Create a different trigger condition that actually varies
> 
> The current design tries to create a conditional that will always be true, which is poor templating.

*Tokens: 567 in / 296 out — $0.0307*

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
> Looking at this card's design:
> 
> **Design Issues Found:**
> 
> 1. **Conditional Always True**: The biggest issue is that "If you overclocked this turn" will ALWAYS be true when this spell resolves. Since overclock is an additional cost to cast this spell, you must overclock to cast it, meaning the conditional is meaningless. The card effectively reads "Counter target spell. Draw a card." with extra steps.
> 
> 2. **Unclear Timing Interaction**: The reminder text says you can play the exiled cards "until end of turn," but this is an instant that could be cast during an opponent's turn. If cast during an opponent's turn, you'd have a very narrow window to play those cards (only instants/cards with flash before your turn begins).
> 
> 3. **Memory Issues**: While not a complete dealbreaker, having to track three exiled cards that can be played creates memory issues, especially when combined with drawing a card from the spell itself.
> 
> **Suggested Fix:**
> The card should either:
> - Remove the conditional entirely and just say "Counter target spell. Draw a card."
> - Change the condition to something that can actually vary (e.g., "If you control an artifact, draw a card")
> - Make overclock an optional ability rather than a cost
> 
> The current design has a fundamental flaw where the conditional check is pointless, making the card read more complex than it actually is.

*Tokens: 576 in / 308 out — $0.0317*

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
> Looking at Synaptic Overload, I need to evaluate a 2-mana counterspell with significant additional costs and benefits.
> 
> **Comparison to similar cards:**
> - **Counterspell** (UU) - The gold standard 2-mana counter
> - **Negate** (1U) - 2-mana conditional counter
> - **Memory Lapse** (1U) - 2-mana counter that puts on top of library
> - **Arcane Denial** (1U) - 2-mana counter with symmetrical card draw
> 
> **Analysis:**
> This card has several key components:
> 1. Base effect: 2-mana unconditional counterspell (already strong)
> 2. Additional cost: Overclock (exile top 3 cards)
> 3. Bonus: Draw a card if you overclocked this turn
> 
> The overclock cost is significant - you're exiling 3 cards from your library, which could include important spells you need. However, you can play those cards this turn, which partially mitigates the downside.
> 
> The "if you overclocked this turn" clause is interesting - it rewards you for overclocking multiple times in a turn, not just with this spell.
> 
> **Power Level Assessment:**
> This is essentially a 2-mana unconditional counterspell that:
> - Costs you 3 cards from library (significant downside)
> - But lets you play those 3 cards this turn (significant upside)
> - Can net you card advantage if you overclock multiple times
> 
> The card is very swingy - if you can play 1-2 of the exiled cards, you've turned a downside into massive upside. The draw trigger further rewards aggressive overclocking strategies.
> 
> **Verdict: BALANCE ISSUE**
> 
> This card is too powerful for uncommon. Getting an unconditional 2-mana counterspell with potential card advantage is approaching rare territory. The overclock "cost" can easily become an advantage if you hit playable cards. Compare to **Counterspell** itself, which wasn't printed at uncommon in modern sets until very recently, and this has significant upside potential.
> 
> Suggested fixes:
> 1. Make it cost {U}{U} instead of {1}{U}
> 2. Remove the card draw clause
> 3. Make it conditional (noncreature spells only)
> 4. Move to rare

*Tokens: 598 in / 541 out — $0.0495*

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
> - Templating: Several templating issues found:
> 
> 1. **"As an additional cost to cast ~"** - The tilde (~) should be replaced with "this spell" in modern templating.
> 
> 2. **"If you overclocked this turn"** - This doesn't work as written. Overclock isn't a player action that can be tracked this way. The card seems to want to check if you overclocked as part of casting this spell, but the templating doesn't support that.
> 
> 3. **Reminder text placement** - While the reminder text for overclock is included, the current wording creates a rules problem. The way it's written, you overclock as an additional cost, then the spell checks if you overclocked this turn, which is redundant and doesn't work with the cost/effect structure.
> 
> 4. **Flavor text** - The special character "ï¿½" appears instead of an em dash before "Dr. Malleus"
> 
> Suggested fix for the mechanical issue:
> - Option 1: "Counter target spell. Draw a card." (Since you always overclock to cast this)
> - Option 2: Make overclock part of the effect rather than a cost
> - Option 3: Create a different trigger condition that actually varies
> 
> The current design tries to create a conditional that will always be true, which is poor templating.
> - Mechanics: Looking at this card's design:
> 
> **Design Issues Found:**
> 
> 1. **Conditional Always True**: The biggest issue is that "If you overclocked this turn" will ALWAYS be true when this spell resolves. Since overclock is an additional cost to cast this spell, you must overclock to cast it, meaning the conditional is meaningless. The card effectively reads "Counter target spell. Draw a card." with extra steps.
> 
> 2. **Unclear Timing Interaction**: The reminder text says you can play the exiled cards "until end of turn," but this is an instant that could be cast during an opponent's turn. If cast during an opponent's turn, you'd have a very narrow window to play those cards (only instants/cards with flash before your turn begins).
> 
> 3. **Memory Issues**: While not a complete dealbreaker, having to track three exiled cards that can be played creates memory issues, especially when combined with drawing a card from the spell itself.
> 
> **Suggested Fix:**
> The card should either:
> - Remove the conditional entirely and just say "Counter target spell. Draw a card."
> - Change the condition to something that can actually vary (e.g., "If you control an artifact, draw a card")
> - Make overclock an optional ability rather than a cost
> 
> The current design has a fundamental flaw where the conditional check is pointless, making the card read more complex than it actually is.
> - Balance: Looking at Synaptic Overload, I need to evaluate a 2-mana counterspell with significant additional costs and benefits.
> 
> **Comparison to similar cards:**
> - **Counterspell** (UU) - The gold standard 2-mana counter
> - **Negate** (1U) - 2-mana conditional counter
> - **Memory Lapse** (1U) - 2-mana counter that puts on top of library
> - **Arcane Denial** (1U) - 2-mana counter with symmetrical card draw
> 
> **Analysis:**
> This card has several key components:
> 1. Base effect: 2-mana unconditional counterspell (already strong)
> 2. Additional cost: Overclock (exile top 3 cards)
> 3. Bonus: Draw a card if you overclocked this turn
> 
> The overclock cost is significant - you're exiling 3 cards from your library, which could include important spells you need. However, you can play those cards this turn, which partially mitigates the downside.
> 
> The "if you overclocked this turn" clause is interesting - it rewards you for overclocking multiple times in a turn, not just with this spell.
> 
> **Power Level Assessment:**
> This is essentially a 2-mana unconditional counterspell that:
> - Costs you 3 cards from library (significant downside)
> - But lets you play those 3 cards this turn (significant upside)
> - Can net you card advantage if you overclock multiple times
> 
> The card is very swingy - if you can play 1-2 of the exiled cards, you've turned a downside into massive upside. The draw trigger further rewards aggressive overclocking strategies.
> 
> **Verdict: BALANCE ISSUE**
> 
> This card is too powerful for uncommon. Getting an unconditional 2-mana counterspell with potential card advantage is approaching rare territory. The overclock "cost" can easily become an advantage if you hit playable cards. Compare to **Counterspell** itself, which wasn't printed at uncommon in modern sets until very recently, and this has significant upside potential.
> 
> Suggested fixes:
> 1. Make it cost {U}{U} instead of {1}{U}
> 2. Remove the card draw clause
> 3. Make it conditional (noncreature spells only)
> 4. Move to rare
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Tilde (~) should be replaced with 'this spell'",
    "Conditional 'if you overclocked this turn' is always true and meaningless",
    "Flavor text has corrupted character instead of em dash",
    "Too powerful for uncommon - unconditional 2-mana counter with upside"
  ],
  "name": "Synaptic Overload",
  "mana_cost": "{U}{U}",
  "type_line": "Instant",
  "oracle_text": "As an additional cost to cast this spell, overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nCounter target spell. Draw a card.",
  "rarity": "uncommon",
  "power": null,
  "toughness": null,
  "flavor_text": "\"The prototype neural interface worked perfectly. The subject's brain, however, did not.\" \u2014Dr. Malleus, Cult of Science"
}
```

*Tokens: 2294 in / 364 out — $0.0617*

## C) Revised Card

```json
{
  "name": "Synaptic Overload",
  "mana_cost": "{U}{U}",
  "type_line": "Instant",
  "oracle_text": "As an additional cost to cast this spell, overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nCounter target spell. Draw a card.",
  "rarity": "uncommon",
  "flavor_text": "\"The prototype neural interface worked perfectly. The subject's brain, however, did not.\" \u2014Dr. Malleus, Cult of Science"
}
```

**Changes made:**
- Tilde (~) should be replaced with 'this spell'
- Conditional 'if you overclocked this turn' is always true and meaningless
- Flavor text has corrupted character instead of em dash
- Too powerful for uncommon - unconditional 2-mana counter with upside

## D) Cost

- API calls: 4
- Input tokens: 4035
- Output tokens: 1509
- Cost: $0.1737