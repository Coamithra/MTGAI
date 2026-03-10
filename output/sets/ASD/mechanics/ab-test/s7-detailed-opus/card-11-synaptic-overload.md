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
  "flavor_text": "\"The prototype neural interface worked perfectly. The subject's brain, however, did not.\" \u00ef\u00bf\u00bdDr. Malleus, Cult of Science"
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
> Flavor Text: "The prototype neural interface worked perfectly. The subject's brain, however, did not." ï¿½Dr. Malleus, Cult of Science
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
> **Templating & Rules Text:**
> - **Oracle text validity**: PASS with minor concern. The text is valid, though the self-referential condition "If you overclocked this turn" is unusual since you're forced to overclock as part of casting this spell. This creates a condition that's always true when the spell resolves.
> - **Reminder text**: PASS. Overclock has its reminder text on first use.
> - **Capitalization**: PASS. "overclock" is correctly lowercase after the comma.
> - **Current templating**: PASS. Uses current templating standards.
> 
> **Keyword Interactions:**
> - **Negated keywords**: ISSUE. The condition "If you overclocked this turn" is always true when this spell resolves, since overclocking is a mandatory additional cost. This makes the conditional meaningless—the card will always draw a card.
> - **Conditional checking**: ISSUE. As noted above, the condition cannot be false during normal play of this card.
> 
> **Balance:**
> - **Power level**: ISSUE. This is significantly overpowered for {1}{U} at uncommon. Let's compare:
>   - **Counterspell** ({U}{U}): Counter target spell, no card draw
>   - **Memory Lapse** ({1}{U}): Counter target spell, put it on top of library
>   - **Arcane Denial** ({1}{U}): Counter target spell, opponents draw cards
>   
>   This card is essentially a 2-mana hard counter that cantrips. Even with the overclock "cost" (which provides additional value by letting you play 3 cards), this is too efficient. The overclock mechanic is meant to be high-risk/reward, but here it's all reward.
> 
> **Design:**
> - **Focused purpose**: PASS. The card has a clear purpose as a counterspell with card advantage.
> - **Variable effects**: ISSUE. The "if you overclocked" condition always resolves to true, making it not truly variable.
> - **Gameplay decisions**: MIXED. While overclock creates interesting decisions about what to play from exile, the mandatory nature here reduces decision-making.
> 
> **Color Pie:**
> - PASS. Counterspells and card draw are both firmly in blue's slice of the color pie. Overclock is also in U according to the set mechanics.
> 
> **Additional Concerns:**
> 1. **Rules confusion**: Players might not understand that they've "overclocked this turn" when it's a mandatory cost of this specific spell.
> 2. **Development issue**: This creates a 2-mana counterspell that replaces itself AND gives you access to 3 additional cards. Even if you can't play all the exiled cards, the power level is too high.
> 
> **Recommended Fix:**
> Change the oracle text to remove the redundant conditional:
> "As an additional cost to cast ~, overclock.
> Counter target spell. Draw a card."
> 
> Even with this fix, the card may still be too powerful at uncommon for {1}{U}. Consider either increasing the cost to {2}{U} or removing the card draw.

*Tokens: 807 in / 700 out — $0.0646*

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
> Flavor Text: "The prototype neural interface worked perfectly. The subject's brain, however, did not." ï¿½Dr. Malleus, Cult of Science
> 
> Review findings:
> **Templating & Rules Text:**
> - **Oracle text validity**: PASS with minor concern. The text is valid, though the self-referential condition "If you overclocked this turn" is unusual since you're forced to overclock as part of casting this spell. This creates a condition that's always true when the spell resolves.
> - **Reminder text**: PASS. Overclock has its reminder text on first use.
> - **Capitalization**: PASS. "overclock" is correctly lowercase after the comma.
> - **Current templating**: PASS. Uses current templating standards.
> 
> **Keyword Interactions:**
> - **Negated keywords**: ISSUE. The condition "If you overclocked this turn" is always true when this spell resolves, since overclocking is a mandatory additional cost. This makes the conditional meaningless—the card will always draw a card.
> - **Conditional checking**: ISSUE. As noted above, the condition cannot be false during normal play of this card.
> 
> **Balance:**
> - **Power level**: ISSUE. This is significantly overpowered for {1}{U} at uncommon. Let's compare:
>   - **Counterspell** ({U}{U}): Counter target spell, no card draw
>   - **Memory Lapse** ({1}{U}): Counter target spell, put it on top of library
>   - **Arcane Denial** ({1}{U}): Counter target spell, opponents draw cards
>   
>   This card is essentially a 2-mana hard counter that cantrips. Even with the overclock "cost" (which provides additional value by letting you play 3 cards), this is too efficient. The overclock mechanic is meant to be high-risk/reward, but here it's all reward.
> 
> **Design:**
> - **Focused purpose**: PASS. The card has a clear purpose as a counterspell with card advantage.
> - **Variable effects**: ISSUE. The "if you overclocked" condition always resolves to true, making it not truly variable.
> - **Gameplay decisions**: MIXED. While overclock creates interesting decisions about what to play from exile, the mandatory nature here reduces decision-making.
> 
> **Color Pie:**
> - PASS. Counterspells and card draw are both firmly in blue's slice of the color pie. Overclock is also in U according to the set mechanics.
> 
> **Additional Concerns:**
> 1. **Rules confusion**: Players might not understand that they've "overclocked this turn" when it's a mandatory cost of this specific spell.
> 2. **Development issue**: This creates a 2-mana counterspell that replaces itself AND gives you access to 3 additional cards. Even if you can't play all the exiled cards, the power level is too high.
> 
> **Recommended Fix:**
> Change the oracle text to remove the redundant conditional:
> "As an additional cost to cast ~, overclock.
> Counter target spell. Draw a card."
> 
> Even with this fix, the card may still be too powerful at uncommon for {1}{U}. Consider either increasing the cost to {2}{U} or removing the card draw.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Redundant conditional - 'If you overclocked this turn' is always true when overclock is mandatory",
    "Overpowered at uncommon - 2-mana counterspell that cantrips plus overclock value"
  ],
  "name": "Synaptic Overload",
  "mana_cost": "{1}{U}",
  "type_line": "Instant",
  "oracle_text": "As an additional cost to cast ~, overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nCounter target spell. Draw a card.",
  "rarity": "uncommon",
  "power": null,
  "toughness": null,
  "flavor_text": "\"The prototype neural interface worked perfectly. The subject's brain, however, did not.\" \u2014Dr. Malleus, Cult of Science"
}
```

*Tokens: 1512 in / 346 out — $0.0486*

## C) Revised Card

```json
{
  "name": "Synaptic Overload",
  "mana_cost": "{1}{U}",
  "type_line": "Instant",
  "oracle_text": "As an additional cost to cast ~, overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nCounter target spell. Draw a card.",
  "rarity": "uncommon",
  "flavor_text": "\"The prototype neural interface worked perfectly. The subject's brain, however, did not.\" \u2014Dr. Malleus, Cult of Science"
}
```

**Changes made:**
- Redundant conditional - 'If you overclocked this turn' is always true when overclock is mandatory
- Overpowered at uncommon - 2-mana counterspell that cantrips plus overclock value

## D) Cost

- API calls: 2
- Input tokens: 2319
- Output tokens: 1046
- Cost: $0.1132