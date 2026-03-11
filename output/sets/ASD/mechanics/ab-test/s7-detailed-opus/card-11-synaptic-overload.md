# Card 11: Synaptic Overload — Strategy: s7-detailed-opus

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

### Step 1: Detailed review analysis

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
> Review this card thoroughly. At minimum, check every criterion below (state PASS or describe the issue for each), but also flag anything else you notice.
> 
> **Templating & Rules Text:**
> - Is the oracle text valid MTG rules text?
> - Does every custom mechanic (salvage, malfunction, overclock) have reminder text on first use?
> - Is capitalization consistent (keyword capitalized at start of ability, lowercase mid-sentence)?
> - Does the card use current MTG templating ("enters" not "enters the battlefield")?
> 
> **Keyword Interactions:**
> - Are there any keywords that are negated or made useless by other abilities? (e.g., haste on a creature that always enters tapped)
> - If there's a conditional ("if you X this turn"), can the condition actually be false during normal play?
> 
> **Balance:**
> - Is the power level appropriate for the mana cost AND rarity? Compare to 2-3 well-known printed MTG cards at similar cost.
> - Note: malfunction cards are intentionally above-rate — the delayed entry IS the drawback.
> 
> **Design:**
> - Does the card have a focused purpose, or is it kitchen sink (3+ unrelated effects)?
> - If effects are variable (deal X damage, etc.), is the variability real or does it always resolve to the same value?
> - Does the card create interesting gameplay decisions?
> 
> **Color Pie:**
> - Are all abilities appropriate for this card's color(s)?
> 
> Provide your detailed analysis for each criterion.

**Response:**
> ## Card Review: Synaptic Overload
> 
> ---
> 
> ### Templating & Rules Text
> 
> **Oracle text validity:** ISSUE — Using overclock as an additional cost is a significant rules problem. The reminder text says "You may play them until end of turn," which grants a duration-based permission. Additional costs are paid during casting (step 601.2b), but the "you may play them until end of turn" component creates a lingering permission that doesn't fit cleanly into the additional cost framework. Additionally, "overclock" as defined is a keyword *action* (like scry or surveil), not a cost. Keyword actions describe game actions, but additional costs need to be clearly defined costs. The card should either use overclock as a separate triggered/activated ability or restructure. Something like "Overclock, then counter target spell" would be cleaner if overclock is a keyword action.
> 
> **Reminder text on first use:** PASS — Overclock has reminder text on its first and only use.
> 
> **Capitalization:** ISSUE — "overclock" in the lowercase mid-sentence reference "If you overclocked this turn" is fine, but "overclock" in the additional cost line after the comma should be examined. As a keyword action in rules text, this is acceptable. However, the additional cost structure itself is the deeper problem (see above).
> 
> **Current templating:** PASS — No enters-the-battlefield language needed here.
> 
> ---
> 
> ### Keyword Interactions
> 
> **Keywords negating each other:** ISSUE — This is a critical design flaw. Overclock exiles three cards you *may play until end of turn*. But this is an instant-speed counterspell, meaning you'll typically cast it on your opponent's turn. Cards exiled by overclock can only be played "until end of turn," which means you'd need to play them at instant speed or lose them entirely. Most cards exiled (creatures, sorceries, enchantments, lands) will be unplayable. This dramatically undermines the overclock mechanic's value and makes the "may play them" text nearly dead. The three exiled cards become almost pure downside (milling yourself) rather than the intended high-risk/reward tension.
> 
> **Conditional being falsifiable:** ISSUE — "If you overclocked this turn" is the additional cost to cast the spell. If overclock is a mandatory additional cost, you *always* overclock when casting this. The condition is never false during normal play of this card. This makes the "if" clause feel like a trap for players — it reads like conditionality but functions as certainty. This should just say "Counter target spell. Draw a card." with overclock as the additional cost, OR the overclock should be optional (which contradicts "additional cost" structure).
> 
> ---
> 
> ### Balance
> 
> Comparing to printed cards:
> 
> - **Cancel** ({1}{U}{U}): Unconditional counter, no upside, 3 mana.
> - **Counterspell** ({U}{U}): Unconditional counter, 2 mana, iconic and powerful.
> - **Arcane Denial** ({1}{U}): Counters a spell, opponent draws two, you draw one next upkeep.
> 
> At {1}{U}, this is a 2-mana unconditional counterspell that draws a card (since the condition is always true). The "cost" is exiling three cards, but since you can rarely use those exiled cards at instant speed on the opponent's turn, this is essentially Counterspell + cantrip for the downside of milling three cards. That is **significantly above rate** even at uncommon. In limited, this is absurd. In constructed, exiling three cards from your library is a near-trivial cost for a 2-mana counter-cantrip.
> 
> **BALANCE: FAIL — Too powerful.** This needs to cost {1}{U}{U} at minimum, or the draw should be removed.
> 
> ---
> 
> ### Design
> 
> **Focused purpose:** ISSUE — The card has a tension problem rather than a kitchen-sink problem. The overclock mechanic wants you to play cards on your turn (proactively), while counterspells want you to hold up mana reactively. These two design goals directly conflict, and not in a productive "interesting tension" way — the instant-speed timing just makes overclock's exiled cards stranded.
> 
> **Variability:** PASS — The overclock exile is technically variable in what you hit, but the functional outcome (cards are mostly unplayable) is nearly static.
> 
> **Interesting gameplay decisions:** FAIL — Since overclock is mandatory and the condition is always true, there's no meaningful decision point. You just counter and draw.
> 
> ---
> 
> ### Color Pie
> 
> **Counterspell:** PASS — Blue, fully appropriate.
> **Draw a card:** PASS — Blue, fully appropriate.
> **Overclock (U, R, B):** PASS — Blue has access.
> 
> ---
> 
> ### Summary
> 
> This card has three fundamental problems: (1) overclock as an additional cost is rules-questionable, (2) the instant-speed timing almost completely negates overclock's intended upside, and (3) the conditional draw is always true, making this an undercosted counter-cantrip. **Recommend a significant redesign** — either make it a sorcery-speed effect or restructure the overclock interaction entirely.

*Tokens: 805 in / 1203 out — $0.0341*

### Step 2: Submit revised card based on review

**Prompt sent:**
> Based on the following review of a card, submit the revised card. If no issues were found, return the card unchanged with verdict OK.
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
> Review findings:
> ## Card Review: Synaptic Overload
> 
> ---
> 
> ### Templating & Rules Text
> 
> **Oracle text validity:** ISSUE — Using overclock as an additional cost is a significant rules problem. The reminder text says "You may play them until end of turn," which grants a duration-based permission. Additional costs are paid during casting (step 601.2b), but the "you may play them until end of turn" component creates a lingering permission that doesn't fit cleanly into the additional cost framework. Additionally, "overclock" as defined is a keyword *action* (like scry or surveil), not a cost. Keyword actions describe game actions, but additional costs need to be clearly defined costs. The card should either use overclock as a separate triggered/activated ability or restructure. Something like "Overclock, then counter target spell" would be cleaner if overclock is a keyword action.
> 
> **Reminder text on first use:** PASS — Overclock has reminder text on its first and only use.
> 
> **Capitalization:** ISSUE — "overclock" in the lowercase mid-sentence reference "If you overclocked this turn" is fine, but "overclock" in the additional cost line after the comma should be examined. As a keyword action in rules text, this is acceptable. However, the additional cost structure itself is the deeper problem (see above).
> 
> **Current templating:** PASS — No enters-the-battlefield language needed here.
> 
> ---
> 
> ### Keyword Interactions
> 
> **Keywords negating each other:** ISSUE — This is a critical design flaw. Overclock exiles three cards you *may play until end of turn*. But this is an instant-speed counterspell, meaning you'll typically cast it on your opponent's turn. Cards exiled by overclock can only be played "until end of turn," which means you'd need to play them at instant speed or lose them entirely. Most cards exiled (creatures, sorceries, enchantments, lands) will be unplayable. This dramatically undermines the overclock mechanic's value and makes the "may play them" text nearly dead. The three exiled cards become almost pure downside (milling yourself) rather than the intended high-risk/reward tension.
> 
> **Conditional being falsifiable:** ISSUE — "If you overclocked this turn" is the additional cost to cast the spell. If overclock is a mandatory additional cost, you *always* overclock when casting this. The condition is never false during normal play of this card. This makes the "if" clause feel like a trap for players — it reads like conditionality but functions as certainty. This should just say "Counter target spell. Draw a card." with overclock as the additional cost, OR the overclock should be optional (which contradicts "additional cost" structure).
> 
> ---
> 
> ### Balance
> 
> Comparing to printed cards:
> 
> - **Cancel** ({1}{U}{U}): Unconditional counter, no upside, 3 mana.
> - **Counterspell** ({U}{U}): Unconditional counter, 2 mana, iconic and powerful.
> - **Arcane Denial** ({1}{U}): Counters a spell, opponent draws two, you draw one next upkeep.
> 
> At {1}{U}, this is a 2-mana unconditional counterspell that draws a card (since the condition is always true). The "cost" is exiling three cards, but since you can rarely use those exiled cards at instant speed on the opponent's turn, this is essentially Counterspell + cantrip for the downside of milling three cards. That is **significantly above rate** even at uncommon. In limited, this is absurd. In constructed, exiling three cards from your library is a near-trivial cost for a 2-mana counter-cantrip.
> 
> **BALANCE: FAIL — Too powerful.** This needs to cost {1}{U}{U} at minimum, or the draw should be removed.
> 
> ---
> 
> ### Design
> 
> **Focused purpose:** ISSUE — The card has a tension problem rather than a kitchen-sink problem. The overclock mechanic wants you to play cards on your turn (proactively), while counterspells want you to hold up mana reactively. These two design goals directly conflict, and not in a productive "interesting tension" way — the instant-speed timing just makes overclock's exiled cards stranded.
> 
> **Variability:** PASS — The overclock exile is technically variable in what you hit, but the functional outcome (cards are mostly unplayable) is nearly static.
> 
> **Interesting gameplay decisions:** FAIL — Since overclock is mandatory and the condition is always true, there's no meaningful decision point. You just counter and draw.
> 
> ---
> 
> ### Color Pie
> 
> **Counterspell:** PASS — Blue, fully appropriate.
> **Draw a card:** PASS — Blue, fully appropriate.
> **Overclock (U, R, B):** PASS — Blue has access.
> 
> ---
> 
> ### Summary
> 
> This card has three fundamental problems: (1) overclock as an additional cost is rules-questionable, (2) the instant-speed timing almost completely negates overclock's intended upside, and (3) the conditional draw is always true, making this an undercosted counter-cantrip. **Recommend a significant redesign** — either make it a sorcery-speed effect or restructure the overclock interaction entirely.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Overclock used as an additional cost doesn't work cleanly within the rules \u2014 keyword actions aren't costs. Restructured overclock as a keyword action in the spell's resolution.",
    "Instant-speed counterspell + overclock is anti-synergistic: exiled cards are mostly unplayable on opponent's turn. Made overclock optional to create a real decision point.",
    "The 'If you overclocked this turn' condition was always true when overclock was a mandatory additional cost, making the draw unconditional. Now that overclock is optional, the condition is meaningful.",
    "At {1}{U}, an unconditional counterspell that always draws a card is significantly above rate. Increased mana cost to {1}{U}{U} to align with Cancel-level pricing, with the optional cantrip as upside for the real risk of overclocking."
  ],
  "name": "Synaptic Overload",
  "mana_cost": "{1}{U}{U}",
  "type_line": "Instant",
  "oracle_text": "Counter target spell. You may overclock. If you do, draw a card. (To overclock, exile the top three cards of your library. You may play them until end of turn.)",
  "rarity": "uncommon",
  "flavor_text": "\"The prototype neural interface worked perfectly. The subject's brain, however, did not.\" \u2014Dr. Malleus, Cult of Science"
}
```

*Tokens: 2285 in / 450 out — $0.0227*

## C) Revised Card

```json
{
  "name": "Synaptic Overload",
  "mana_cost": "{1}{U}{U}",
  "type_line": "Instant",
  "oracle_text": "Counter target spell. You may overclock. If you do, draw a card. (To overclock, exile the top three cards of your library. You may play them until end of turn.)",
  "rarity": "uncommon",
  "flavor_text": "\"The prototype neural interface worked perfectly. The subject's brain, however, did not.\" \u2014Dr. Malleus, Cult of Science"
}
```

**Changes made:**
- Overclock used as an additional cost doesn't work cleanly within the rules — keyword actions aren't costs. Restructured overclock as a keyword action in the spell's resolution.
- Instant-speed counterspell + overclock is anti-synergistic: exiled cards are mostly unplayable on opponent's turn. Made overclock optional to create a real decision point.
- The 'If you overclocked this turn' condition was always true when overclock was a mandatory additional cost, making the draw unconditional. Now that overclock is optional, the condition is meaningful.
- At {1}{U}, an unconditional counterspell that always draws a card is significantly above rate. Increased mana cost to {1}{U}{U} to align with Cancel-level pricing, with the optional cantrip as upside for the real risk of overclocking.

## D) Cost

- API calls: 2
- Input tokens: 3090
- Output tokens: 1653
- Cost: $0.0568