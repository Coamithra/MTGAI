# Card 14: Cascade Protocol — Strategy: s7-detailed-opus

## A) Original Card

```json
{
  "name": "Cascade Protocol",
  "mana_cost": "{3}{R}{R}",
  "cmc": 5,
  "colors": [
    "R"
  ],
  "type_line": "Sorcery",
  "oracle_text": "Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)\n~ deals 2 damage to any target for each card exiled with ~ this way.",
  "rarity": "rare",
  "keywords": [
    "Overclock"
  ],
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u00e2\u20ac\u201dFinal log, Research Station Gamma"
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
> Name: Cascade Protocol
> Mana Cost: {3}{R}{R}
> Type: Sorcery
> Rarity: rare
> Oracle Text: Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)
> ~ deals 2 damage to any target for each card exiled with ~ this way.
> Flavor Text: "The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion." â€”Final log, Research Station Gamma
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
> # Card Review: Cascade Protocol
> 
> ## Templating & Rules Text
> 
> **Reminder text on first use:** ISSUE — The reminder text provided only describes a single overclock instance. Since the card instructs you to "overclock, then overclock again," the reminder text in parentheses doesn't clarify that this happens twice with separate exile batches. More critically, the card says "each card exiled with ~ this way," but the reminder text doesn't help parse whether both overclocks count. This is functional but the reminder text is slightly misleading by only describing one iteration.
> 
> **Oracle text validity:** ISSUE — There are meaningful rules problems here. "Overclock, then overclock again" is novel templating. Keyword actions are typically performed once per instruction (e.g., "Scry 2, then scry 2 again" doesn't exist — it would just be "scry 4"). The reason this matters here is that overclock always exiles exactly 3, so the design clearly wants two separate batches of 3. However, the current templating is ambiguous about the damage clause. "Each card exiled with ~ this way" — does "this way" refer to both overclocks, or only the second? Standard MTG templating would likely need something cleaner, such as:
> 
> > *"Exile the top three cards of your library, then exile the top three cards of your library. You may play cards exiled this way until end of turn. ~ deals 2 damage to any target for each card exiled this way."*
> 
> This avoids the awkward double-keyword-action invocation entirely and makes the count unambiguous.
> 
> **Capitalization:** ISSUE — "Overclock" appears mid-sentence in "then overclock again" and is lowercase, which is correct for a keyword action (like "destroy" or "scry"). However, the first "Overclock" starting the sentence is capitalized, which is also correct. This is actually **PASS** on reflection.
> 
> **Modern templating ("enters" etc.):** PASS — No enter-the-battlefield effects on this sorcery, no concerns here.
> 
> ---
> 
> ## Keyword Interactions
> 
> **Keywords negating each other:** PASS — No conflicting keywords present.
> 
> **Conditional falsifiability:** ISSUE — The "each card exiled with ~ this way" clause suggests variability, but in practice, the card always exiles exactly 6 cards (3 + 3) unless the player has fewer than 6 cards in library. So the damage is virtually always 12 to any target. This is discussed further under Design/variability below.
> 
> ---
> 
> ## Balance
> 
> **MAJOR ISSUE** — This card deals 2 damage × 6 exiled cards = **12 damage to any target** for 5 mana, stapled onto what is essentially a massive impulse draw of 6 cards. Let's compare:
> 
> - **Crackle with Power** (XXXRR): Needs X=4 (total 6 mana) to deal 10 damage to one target, with no card advantage.
> - **Explosive Welcome** (6RR, 8 mana): Deals 12 total split between two targets, no card advantage.
> - **Fight with Fire** kicked (9 mana): 10 damage divided as you choose.
> 
> Cascade Protocol at **5 mana** deals 12 to any single target AND gives you access to 6 impulsed cards to play this turn. This is absurdly above rate. The overclock "downside" of exiling from your library is largely upside here since you get to play the cards. This is a 5-mana "kill virtually any creature or deal 12 to face" that also draws ~6 cards of impulse. It would be a strong rare at 8 mana, let alone 5.
> 
> **Suggested fix:** Either reduce damage to 1 per card exiled, significantly raise the mana cost (to 5RR or more), or remove the ability to play the exiled cards (which would conflict with overclock's definition, so raising the cost is preferable).
> 
> ---
> 
> ## Design
> 
> **Focused purpose:** PASS — The card has a clear identity: double overclock with a payoff for the exiled volume. The flavor is coherent.
> 
> **Variable or fixed output:** ISSUE — As noted, the variability is essentially illusory. Barring near-decking scenarios, this always exiles 6 and deals 12. The "each card exiled" language implies meaningful variance, but there is almost none. Consider whether the card should just say "deals 12 damage" for clarity, or if the mechanic should have real variance (e.g., "deals 2 damage for each nonland card exiled this way").
> 
> **Interesting decisions:** PARTIAL PASS — The overclock portion creates decisions about which exiled cards to play. The damage portion creates zero decisions since 12 to one target is straightforward.
> 
> ---
> 
> ## Color Pie
> 
> **PASS** — Direct damage is core red. Overclock is assigned to U/R/B, and red is included. Impulse draw is red. Everything checks out.
> 
> ---
> 
> ## Summary
> 
> The card's biggest problem is **extreme power level** — 12 guaranteed damage plus 6 impulse-drawn cards at 5 mana is unprintable. Secondary issues include **pseudo-variable damage that isn't actually variable** and **templating ambiguity** around double keyword action invocation. The concept is exciting but needs significant rebalancing.

*Tokens: 802 in / 1249 out — $0.0352*

### Step 2: Submit revised card based on review

**Prompt sent:**
> Based on the following review of a card, submit the revised card. If no issues were found, return the card unchanged with verdict OK.
> 
> Original card:
> Name: Cascade Protocol
> Mana Cost: {3}{R}{R}
> Type: Sorcery
> Rarity: rare
> Oracle Text: Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)
> ~ deals 2 damage to any target for each card exiled with ~ this way.
> Flavor Text: "The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion." â€”Final log, Research Station Gamma
> 
> Review findings:
> # Card Review: Cascade Protocol
> 
> ## Templating & Rules Text
> 
> **Reminder text on first use:** ISSUE — The reminder text provided only describes a single overclock instance. Since the card instructs you to "overclock, then overclock again," the reminder text in parentheses doesn't clarify that this happens twice with separate exile batches. More critically, the card says "each card exiled with ~ this way," but the reminder text doesn't help parse whether both overclocks count. This is functional but the reminder text is slightly misleading by only describing one iteration.
> 
> **Oracle text validity:** ISSUE — There are meaningful rules problems here. "Overclock, then overclock again" is novel templating. Keyword actions are typically performed once per instruction (e.g., "Scry 2, then scry 2 again" doesn't exist — it would just be "scry 4"). The reason this matters here is that overclock always exiles exactly 3, so the design clearly wants two separate batches of 3. However, the current templating is ambiguous about the damage clause. "Each card exiled with ~ this way" — does "this way" refer to both overclocks, or only the second? Standard MTG templating would likely need something cleaner, such as:
> 
> > *"Exile the top three cards of your library, then exile the top three cards of your library. You may play cards exiled this way until end of turn. ~ deals 2 damage to any target for each card exiled this way."*
> 
> This avoids the awkward double-keyword-action invocation entirely and makes the count unambiguous.
> 
> **Capitalization:** ISSUE — "Overclock" appears mid-sentence in "then overclock again" and is lowercase, which is correct for a keyword action (like "destroy" or "scry"). However, the first "Overclock" starting the sentence is capitalized, which is also correct. This is actually **PASS** on reflection.
> 
> **Modern templating ("enters" etc.):** PASS — No enter-the-battlefield effects on this sorcery, no concerns here.
> 
> ---
> 
> ## Keyword Interactions
> 
> **Keywords negating each other:** PASS — No conflicting keywords present.
> 
> **Conditional falsifiability:** ISSUE — The "each card exiled with ~ this way" clause suggests variability, but in practice, the card always exiles exactly 6 cards (3 + 3) unless the player has fewer than 6 cards in library. So the damage is virtually always 12 to any target. This is discussed further under Design/variability below.
> 
> ---
> 
> ## Balance
> 
> **MAJOR ISSUE** — This card deals 2 damage × 6 exiled cards = **12 damage to any target** for 5 mana, stapled onto what is essentially a massive impulse draw of 6 cards. Let's compare:
> 
> - **Crackle with Power** (XXXRR): Needs X=4 (total 6 mana) to deal 10 damage to one target, with no card advantage.
> - **Explosive Welcome** (6RR, 8 mana): Deals 12 total split between two targets, no card advantage.
> - **Fight with Fire** kicked (9 mana): 10 damage divided as you choose.
> 
> Cascade Protocol at **5 mana** deals 12 to any single target AND gives you access to 6 impulsed cards to play this turn. This is absurdly above rate. The overclock "downside" of exiling from your library is largely upside here since you get to play the cards. This is a 5-mana "kill virtually any creature or deal 12 to face" that also draws ~6 cards of impulse. It would be a strong rare at 8 mana, let alone 5.
> 
> **Suggested fix:** Either reduce damage to 1 per card exiled, significantly raise the mana cost (to 5RR or more), or remove the ability to play the exiled cards (which would conflict with overclock's definition, so raising the cost is preferable).
> 
> ---
> 
> ## Design
> 
> **Focused purpose:** PASS — The card has a clear identity: double overclock with a payoff for the exiled volume. The flavor is coherent.
> 
> **Variable or fixed output:** ISSUE — As noted, the variability is essentially illusory. Barring near-decking scenarios, this always exiles 6 and deals 12. The "each card exiled" language implies meaningful variance, but there is almost none. Consider whether the card should just say "deals 12 damage" for clarity, or if the mechanic should have real variance (e.g., "deals 2 damage for each nonland card exiled this way").
> 
> **Interesting decisions:** PARTIAL PASS — The overclock portion creates decisions about which exiled cards to play. The damage portion creates zero decisions since 12 to one target is straightforward.
> 
> ---
> 
> ## Color Pie
> 
> **PASS** — Direct damage is core red. Overclock is assigned to U/R/B, and red is included. Impulse draw is red. Everything checks out.
> 
> ---
> 
> ## Summary
> 
> The card's biggest problem is **extreme power level** — 12 guaranteed damage plus 6 impulse-drawn cards at 5 mana is unprintable. Secondary issues include **pseudo-variable damage that isn't actually variable** and **templating ambiguity** around double keyword action invocation. The concept is exciting but needs significant rebalancing.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Balance: 12 damage to any target plus 6 impulse-drawn cards at 5 mana is drastically above rate. Comparable cards cost 8-9 mana for similar damage without card advantage.",
    "Templating: 'Overclock, then overclock again' is ambiguous and unprecedented for keyword actions. The damage clause 'each card exiled with ~ this way' is unclear about whether it refers to both overclocks or only the second.",
    "Variable output is illusory: the card virtually always exiles exactly 6 cards, so 'each card exiled' language implies variance that doesn't meaningfully exist. Changing to 'each nonland card' adds real variance."
  ],
  "name": "Cascade Protocol",
  "mana_cost": "{4}{R}{R}",
  "type_line": "Sorcery",
  "oracle_text": "Exile the top three cards of your library, then exile the top three cards of your library. You may play cards exiled this way until end of turn.\nCascade Protocol deals 2 damage to any target for each nonland card exiled this way.",
  "rarity": "rare",
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u2014Final log, Research Station Gamma"
}
```

*Tokens: 2329 in / 426 out — $0.0223*

## C) Revised Card

```json
{
  "name": "Cascade Protocol",
  "mana_cost": "{4}{R}{R}",
  "type_line": "Sorcery",
  "oracle_text": "Exile the top three cards of your library, then exile the top three cards of your library. You may play cards exiled this way until end of turn.\nCascade Protocol deals 2 damage to any target for each nonland card exiled this way.",
  "rarity": "rare",
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u2014Final log, Research Station Gamma"
}
```

**Changes made:**
- Balance: 12 damage to any target plus 6 impulse-drawn cards at 5 mana is drastically above rate. Comparable cards cost 8-9 mana for similar damage without card advantage.
- Templating: 'Overclock, then overclock again' is ambiguous and unprecedented for keyword actions. The damage clause 'each card exiled with ~ this way' is unclear about whether it refers to both overclocks or only the second.
- Variable output is illusory: the card virtually always exiles exactly 6 cards, so 'each card exiled' language implies variance that doesn't meaningfully exist. Changing to 'each nonland card' adds real variance.

## D) Cost

- API calls: 2
- Input tokens: 3131
- Output tokens: 1675
- Cost: $0.0575