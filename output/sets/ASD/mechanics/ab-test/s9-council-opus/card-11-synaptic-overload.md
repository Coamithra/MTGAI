# Card 11: Synaptic Overload — Strategy: s9-council-opus

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

### Step 1: Reviewer 1 analysis

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
> Name: Synaptic Overload
> Mana Cost: {1}{U}
> Type: Instant
> Rarity: uncommon
> Oracle Text: As an additional cost to cast ~, overclock. (Exile the top three cards of your library. You may play them until end of turn.)
> Counter target spell. If you overclocked this turn, draw a card.
> Flavor Text: "The prototype neural interface worked perfectly. The subject's brain, however, did not." â€”Dr. Malleus, Cult of Science
> 
> Critically review this card. List any issues you find with templating, mechanics, balance, design, or color pie. If the card is fine, say "No issues found." Be specific about each issue.

**Response:**
> ## Review: Synaptic Overload
> 
> ### Issues Found:
> 
> **1. Mechanical/Templating Issue — Overclock as Additional Cost**
> Overclock is defined as a keyword action, but using it as an additional cost creates problems. Additional costs are paid during casting, but Overclock's reminder text says "You may play them **until end of turn**," which implies an ongoing permission effect. Additional costs are discrete, one-time payments — they don't naturally create lingering game states. This is a poor fit. Overclock works better as a separate action (e.g., "When you cast ~, overclock") or as a triggered ability.
> 
> **2. Logical/Gameplay Issue — The "If you overclocked this turn" Condition Is Always True**
> Since Overclock is an additional cost of casting this very spell, you have *always* overclocked this turn when this spell resolves. The condition is never false — making the draw unconditional in practice. This makes the conditional text misleading and pointless. Either make the draw unconditional ("Counter target spell, then draw a card") or redesign the trigger to care about overclocking from another source.
> 
> **3. Balance Issue — Unconditional Counterspell + Draw + Impulse Access at {1}{U}**
> This is a 2-mana hard counter that always draws a card AND gives access to three exiled cards. That significantly exceeds Counterspell itself, which is already considered too strong for Standard-level formats. Even with the self-mill risk of Overclock, the card advantage here is extreme at uncommon.
> 
> **4. Design Tension — Counterspell Timing vs. Overclock Value**
> Holding up mana for a counterspell means you may not be able to play the three exiled cards meaningfully (especially lands or sorceries). This creates anti-synergy between the Overclock mechanic's payoff and the reactive play pattern of a counterspell, which is a frustrating play experience.
> 
> **5. Minor Templating — "Overclocked" as a Game Term**
> The condition "if you overclocked this turn" needs the keyword action to be formally trackable as a game event. This is supportable but should be confirmed as a set-wide convention, similar to "if you cycled this turn."
> 
> ### Summary
> The core concept of pairing Overclock with countermagic is interesting thematically but mechanically problematic. The card needs a redesign of how Overclock is integrated, the always-true condition needs addressing, and the overall rate needs significant adjustment.

*Tokens: 512 in / 580 out — $0.0171*

### Step 2: Reviewer 2 analysis

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
> Name: Synaptic Overload
> Mana Cost: {1}{U}
> Type: Instant
> Rarity: uncommon
> Oracle Text: As an additional cost to cast ~, overclock. (Exile the top three cards of your library. You may play them until end of turn.)
> Counter target spell. If you overclocked this turn, draw a card.
> Flavor Text: "The prototype neural interface worked perfectly. The subject's brain, however, did not." â€”Dr. Malleus, Cult of Science
> 
> Critically review this card. List any issues you find with templating, mechanics, balance, design, or color pie. If the card is fine, say "No issues found." Be specific about each issue.

**Response:**
> ## Review of Synaptic Overload
> 
> ### Issue 1: Overclock as an Additional Cost is Problematic
> Overclock exiles three cards you "may play until end of turn." But this is an instant, meaning you're most likely casting it on your opponent's turn during their spell. Playing lands from exile on an opponent's turn is impossible, and casting sorceries from exile on their turn is also impossible. This dramatically undercuts the "may play them" portion of overclock, making it a near-pure downside when used reactively. The additional cost framing forces the overclock to happen at the worst possible time for its payoff.
> 
> ### Issue 2: "If you overclocked this turn" is Redundant
> Since overclock is an **additional cost** to cast the spell, you have *always* overclocked this turn if this spell is on the stack. The conditional "If you overclocked this turn" will always be true when this spell resolves. This should either be unconditional ("draw a card") or the overclock should not be an additional cost, allowing the condition to matter from other overclock sources.
> 
> ### Issue 3: Balance Concern — Undercosted Counterspell with Upside
> At {1}{U}, this is a hard counter (no restrictions) that draws a card (guaranteed, per Issue 2). {1}{U} hard counters in modern design come with significant restrictions (e.g., Counterspell itself is considered above-rate). Adding card draw on top, even with the exile-three downside, creates a card that is likely too efficient for uncommon. The overclock "cost" can actually be upside in a deck built for it.
> 
> ### Issue 4: Design Note Tension
> The design notes say overclock is "high risk/reward" and complexity 3. Stapling it as a mandatory additional cost to a reactive counterspell compresses decision-making rather than expanding it — you don't choose *whether* to overclock, and you can't optimize *when* to overclock. This undermines the mechanic's intended design space.
> 
> ### Suggestions
> Consider making this a sorcery-speed card advantage spell with a counterspell mode, or make the overclock a separate triggered/optional ability, or restrict the counter (e.g., "counter target noncreature spell").

*Tokens: 512 in / 519 out — $0.0155*

### Step 3: Reviewer 3 analysis

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
> Name: Synaptic Overload
> Mana Cost: {1}{U}
> Type: Instant
> Rarity: uncommon
> Oracle Text: As an additional cost to cast ~, overclock. (Exile the top three cards of your library. You may play them until end of turn.)
> Counter target spell. If you overclocked this turn, draw a card.
> Flavor Text: "The prototype neural interface worked perfectly. The subject's brain, however, did not." â€”Dr. Malleus, Cult of Science
> 
> Critically review this card. List any issues you find with templating, mechanics, balance, design, or color pie. If the card is fine, say "No issues found." Be specific about each issue.

**Response:**
> ## Review of Synaptic Overload
> 
> ### Issue 1: Overclock as an Additional Cost on an Instant Creates Major Templating and Gameplay Problems
> 
> Overclock's reminder text says "You may play them **until end of turn**." When used as an additional cost to cast a spell (especially a counterspell cast on an opponent's turn), the exiled cards are almost entirely unplayable—you can only play instants from among them, and you can't play lands on an opponent's turn. This effectively turns the "high risk/reward" mechanic into pure downside (exiling 3 cards for virtually nothing) roughly 90% of the time you'd want to cast this card. The mechanic was clearly designed for sorcery-speed or main-phase use.
> 
> ### Issue 2: "If you overclocked this turn" Condition is Meaningless
> 
> Overclock is a mandatory additional cost of this spell. You **always** overclock when casting it. The condition "if you overclocked this turn" will always be true when this spell resolves, making the draw unconditional in practice. This reads like it was templated for a version where overclock was optional, or where the card didn't itself require overclocking. Either the additional cost should be removed (and the condition checks if you overclocked elsewhere), or the condition should be removed and the draw made explicit.
> 
> ### Issue 3: Counterspell + Draw a Card for {1}{U} is Undercosted
> 
> A hard counter at {1}{U} that also draws a card is significantly above rate, even at uncommon. **Cancel** is {1}{U}{U} with no upside. **Dissolve** (scry 1) costs {1}{U}{U}. Exiling three cards is a real cost, but as noted above, the condition is always met, making this a strict {1}{U} Counterspell + cantrip. This is too efficient even accounting for the exile.
> 
> ### Issue 4: Color Pie Tension with Overclock
> 
> Overclock is specified as U/R/B. Blue has access, so this is technically legal, but the impulse-draw nature of overclock on a reactive counterspell creates a fundamental tension—the mechanic wants proactive play while the card demands reactive timing.
> 
> ### Summary
> 
> This card needs significant rework. The core concept of combining overclock with a counterspell is inherently self-contradictory in gameplay terms.

*Tokens: 512 in / 551 out — $0.0163*

### Step 4: Synthesizer — consensus revision

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
> --- Reviewer 1 ---
> ## Review: Synaptic Overload
> 
> ### Issues Found:
> 
> **1. Mechanical/Templating Issue — Overclock as Additional Cost**
> Overclock is defined as a keyword action, but using it as an additional cost creates problems. Additional costs are paid during casting, but Overclock's reminder text says "You may play them **until end of turn**," which implies an ongoing permission effect. Additional costs are discrete, one-time payments — they don't naturally create lingering game states. This is a poor fit. Overclock works better as a separate action (e.g., "When you cast ~, overclock") or as a triggered ability.
> 
> **2. Logical/Gameplay Issue — The "If you overclocked this turn" Condition Is Always True**
> Since Overclock is an additional cost of casting this very spell, you have *always* overclocked this turn when this spell resolves. The condition is never false — making the draw unconditional in practice. This makes the conditional text misleading and pointless. Either make the draw unconditional ("Counter target spell, then draw a card") or redesign the trigger to care about overclocking from another source.
> 
> **3. Balance Issue — Unconditional Counterspell + Draw + Impulse Access at {1}{U}**
> This is a 2-mana hard counter that always draws a card AND gives access to three exiled cards. That significantly exceeds Counterspell itself, which is already considered too strong for Standard-level formats. Even with the self-mill risk of Overclock, the card advantage here is extreme at uncommon.
> 
> **4. Design Tension — Counterspell Timing vs. Overclock Value**
> Holding up mana for a counterspell means you may not be able to play the three exiled cards meaningfully (especially lands or sorceries). This creates anti-synergy between the Overclock mechanic's payoff and the reactive play pattern of a counterspell, which is a frustrating play experience.
> 
> **5. Minor Templating — "Overclocked" as a Game Term**
> The condition "if you overclocked this turn" needs the keyword action to be formally trackable as a game event. This is supportable but should be confirmed as a set-wide convention, similar to "if you cycled this turn."
> 
> ### Summary
> The core concept of pairing Overclock with countermagic is interesting thematically but mechanically problematic. The card needs a redesign of how Overclock is integrated, the always-true condition needs addressing, and the overall rate needs significant adjustment.
> 
> --- Reviewer 2 ---
> ## Review of Synaptic Overload
> 
> ### Issue 1: Overclock as an Additional Cost is Problematic
> Overclock exiles three cards you "may play until end of turn." But this is an instant, meaning you're most likely casting it on your opponent's turn during their spell. Playing lands from exile on an opponent's turn is impossible, and casting sorceries from exile on their turn is also impossible. This dramatically undercuts the "may play them" portion of overclock, making it a near-pure downside when used reactively. The additional cost framing forces the overclock to happen at the worst possible time for its payoff.
> 
> ### Issue 2: "If you overclocked this turn" is Redundant
> Since overclock is an **additional cost** to cast the spell, you have *always* overclocked this turn if this spell is on the stack. The conditional "If you overclocked this turn" will always be true when this spell resolves. This should either be unconditional ("draw a card") or the overclock should not be an additional cost, allowing the condition to matter from other overclock sources.
> 
> ### Issue 3: Balance Concern — Undercosted Counterspell with Upside
> At {1}{U}, this is a hard counter (no restrictions) that draws a card (guaranteed, per Issue 2). {1}{U} hard counters in modern design come with significant restrictions (e.g., Counterspell itself is considered above-rate). Adding card draw on top, even with the exile-three downside, creates a card that is likely too efficient for uncommon. The overclock "cost" can actually be upside in a deck built for it.
> 
> ### Issue 4: Design Note Tension
> The design notes say overclock is "high risk/reward" and complexity 3. Stapling it as a mandatory additional cost to a reactive counterspell compresses decision-making rather than expanding it — you don't choose *whether* to overclock, and you can't optimize *when* to overclock. This undermines the mechanic's intended design space.
> 
> ### Suggestions
> Consider making this a sorcery-speed card advantage spell with a counterspell mode, or make the overclock a separate triggered/optional ability, or restrict the counter (e.g., "counter target noncreature spell").
> 
> --- Reviewer 3 ---
> ## Review of Synaptic Overload
> 
> ### Issue 1: Overclock as an Additional Cost on an Instant Creates Major Templating and Gameplay Problems
> 
> Overclock's reminder text says "You may play them **until end of turn**." When used as an additional cost to cast a spell (especially a counterspell cast on an opponent's turn), the exiled cards are almost entirely unplayable—you can only play instants from among them, and you can't play lands on an opponent's turn. This effectively turns the "high risk/reward" mechanic into pure downside (exiling 3 cards for virtually nothing) roughly 90% of the time you'd want to cast this card. The mechanic was clearly designed for sorcery-speed or main-phase use.
> 
> ### Issue 2: "If you overclocked this turn" Condition is Meaningless
> 
> Overclock is a mandatory additional cost of this spell. You **always** overclock when casting it. The condition "if you overclocked this turn" will always be true when this spell resolves, making the draw unconditional in practice. This reads like it was templated for a version where overclock was optional, or where the card didn't itself require overclocking. Either the additional cost should be removed (and the condition checks if you overclocked elsewhere), or the condition should be removed and the draw made explicit.
> 
> ### Issue 3: Counterspell + Draw a Card for {1}{U} is Undercosted
> 
> A hard counter at {1}{U} that also draws a card is significantly above rate, even at uncommon. **Cancel** is {1}{U}{U} with no upside. **Dissolve** (scry 1) costs {1}{U}{U}. Exiling three cards is a real cost, but as noted above, the condition is always met, making this a strict {1}{U} Counterspell + cantrip. This is too efficient even accounting for the exile.
> 
> ### Issue 4: Color Pie Tension with Overclock
> 
> Overclock is specified as U/R/B. Blue has access, so this is technically legal, but the impulse-draw nature of overclock on a reactive counterspell creates a fundamental tension—the mechanic wants proactive play while the card demands reactive timing.
> 
> ### Summary
> 
> This card needs significant rework. The core concept of combining overclock with a counterspell is inherently self-contradictory in gameplay terms.
> 
> Based on the consensus of these 3 reviews (issues raised by at least 2 reviewers), produce a revised version of the card. If no issues have consensus, return the card unchanged with verdict OK. Only fix issues that at least 2 reviewers agree on.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Overclock as an additional cost on a reactive instant is fundamentally problematic \u2014 it forces the mechanic to trigger at the worst possible time (opponent's turn), making the exiled cards largely unplayable. All 3 reviewers agree.",
    "The 'if you overclocked this turn' condition is always true since overclock is a mandatory additional cost of this very spell, making the conditional meaningless/redundant. All 3 reviewers agree.",
    "A {1}{U} hard counterspell that effectively always draws a card is significantly undercosted, exceeding even Counterspell in power. All 3 reviewers agree.",
    "The reactive timing of a counterspell fundamentally conflicts with overclock's proactive, sorcery-speed-friendly design intent. All 3 reviewers agree."
  ],
  "name": "Synaptic Overload",
  "mana_cost": "{1}{U}{U}",
  "type_line": "Instant",
  "oracle_text": "Counter target spell. If you've overclocked this turn, draw a card.",
  "rarity": "uncommon",
  "flavor_text": "\"The prototype neural interface worked perfectly. The subject's brain, however, did not.\" \u2014Dr. Malleus, Cult of Science",
  "power": null,
  "toughness": null
}
```

*Tokens: 3124 in / 451 out — $0.0269*

## C) Revised Card

```json
{
  "name": "Synaptic Overload",
  "mana_cost": "{1}{U}{U}",
  "type_line": "Instant",
  "oracle_text": "Counter target spell. If you've overclocked this turn, draw a card.",
  "rarity": "uncommon",
  "flavor_text": "\"The prototype neural interface worked perfectly. The subject's brain, however, did not.\" \u2014Dr. Malleus, Cult of Science"
}
```

**Changes made:**
- Overclock as an additional cost on a reactive instant is fundamentally problematic — it forces the mechanic to trigger at the worst possible time (opponent's turn), making the exiled cards largely unplayable. All 3 reviewers agree.
- The 'if you overclocked this turn' condition is always true since overclock is a mandatory additional cost of this very spell, making the conditional meaningless/redundant. All 3 reviewers agree.
- A {1}{U} hard counterspell that effectively always draws a card is significantly undercosted, exceeding even Counterspell in power. All 3 reviewers agree.
- The reactive timing of a counterspell fundamentally conflicts with overclock's proactive, sorcery-speed-friendly design intent. All 3 reviewers agree.

## D) Cost

- API calls: 4
- Input tokens: 4660
- Output tokens: 2101
- Cost: $0.0758