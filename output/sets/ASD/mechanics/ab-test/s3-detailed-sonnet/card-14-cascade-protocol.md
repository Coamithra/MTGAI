# Card 14: Cascade Protocol — Strategy: s3-detailed-sonnet

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
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u00ef\u00bf\u00bdFinal log, Research Station Gamma"
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
> Flavor Text: "The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion." ï¿½Final log, Research Station Gamma
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
> I'll review **Cascade Protocol** thoroughly against each criterion:
> 
> ## **Templating & Rules Text:**
> 
> **ISSUE** - The oracle text has several problems:
> 1. "Overclock, then overclock again" is unclear - it should specify the total number of cards exiled (6)
> 2. The damage clause "for each card exiled with ~ this way" is ambiguous about which cards count
> 3. Missing reminder text - this appears to be the first use of overclock in the set
> 
> **Corrected templating:**
> "Overclock twice. (Exile the top six cards of your library. You may play them until end of turn.)
> ~ deals 2 damage to any target for each card exiled this way."
> 
> ## **Keyword Interactions:**
> 
> **PASS** - No problematic keyword interactions. The overclock mechanic functions as intended.
> 
> ## **Balance:**
> 
> **ISSUE** - Significantly undercosted for a rare. This card provides:
> - 6 cards of impulse draw (worth ~4-5 mana)
> - Up to 12 damage to any target (worth ~3-4 mana at minimum)
> - Total value: 7-9 mana for 5 mana cost
> 
> Compare to:
> - **Light up the Stage** (2 mana, 2 cards) - this is 3x the effect
> - **Lightning Bolt** deals 3 for 1 mana - this deals 4x that for 5x the cost but with massive upside
> 
> Should cost {5}{R}{R} or {4}{R}{R}{R} at minimum.
> 
> ## **Design:**
> 
> **PASS** - Focused design combining card advantage with damage. The variability is real (0-6 cards could be uncastable, affecting damage). Creates interesting decisions about which exiled cards to play vs. maximizing damage.
> 
> ## **Color Pie:**
> 
> **PASS** - Both impulse draw and direct damage are firmly in red's color pie.
> 
> ## **Additional Issues:**
> 
> 1. **Power Level Concern**: Even at corrected cost, 12 potential damage to any target at instant speed equivalent is extremely dangerous for Standard formats
> 2. **Complexity**: Double-overclocking significantly increases cognitive load - tracking 6 exiled cards with different play restrictions
> 3. **Flavor disconnect**: The name "Cascade Protocol" evokes the cascade mechanic, which could confuse players
> 
> ## **Recommendation:**
> 
> Reduce to single overclock and adjust damage:
> ```
> Cascade Protocol {3}{R}{R}
> Sorcery
> Overclock. (Exile the top three cards of your library. You may play them until end of turn.)
> ~ deals 2 damage to any target for each card exiled this way.
> ```
> 
> This maintains the design intent while fixing balance and complexity issues.

*Tokens: 804 in / 640 out — $0.0120*

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
> Flavor Text: "The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion." ï¿½Final log, Research Station Gamma
> 
> Review findings:
> I'll review **Cascade Protocol** thoroughly against each criterion:
> 
> ## **Templating & Rules Text:**
> 
> **ISSUE** - The oracle text has several problems:
> 1. "Overclock, then overclock again" is unclear - it should specify the total number of cards exiled (6)
> 2. The damage clause "for each card exiled with ~ this way" is ambiguous about which cards count
> 3. Missing reminder text - this appears to be the first use of overclock in the set
> 
> **Corrected templating:**
> "Overclock twice. (Exile the top six cards of your library. You may play them until end of turn.)
> ~ deals 2 damage to any target for each card exiled this way."
> 
> ## **Keyword Interactions:**
> 
> **PASS** - No problematic keyword interactions. The overclock mechanic functions as intended.
> 
> ## **Balance:**
> 
> **ISSUE** - Significantly undercosted for a rare. This card provides:
> - 6 cards of impulse draw (worth ~4-5 mana)
> - Up to 12 damage to any target (worth ~3-4 mana at minimum)
> - Total value: 7-9 mana for 5 mana cost
> 
> Compare to:
> - **Light up the Stage** (2 mana, 2 cards) - this is 3x the effect
> - **Lightning Bolt** deals 3 for 1 mana - this deals 4x that for 5x the cost but with massive upside
> 
> Should cost {5}{R}{R} or {4}{R}{R}{R} at minimum.
> 
> ## **Design:**
> 
> **PASS** - Focused design combining card advantage with damage. The variability is real (0-6 cards could be uncastable, affecting damage). Creates interesting decisions about which exiled cards to play vs. maximizing damage.
> 
> ## **Color Pie:**
> 
> **PASS** - Both impulse draw and direct damage are firmly in red's color pie.
> 
> ## **Additional Issues:**
> 
> 1. **Power Level Concern**: Even at corrected cost, 12 potential damage to any target at instant speed equivalent is extremely dangerous for Standard formats
> 2. **Complexity**: Double-overclocking significantly increases cognitive load - tracking 6 exiled cards with different play restrictions
> 3. **Flavor disconnect**: The name "Cascade Protocol" evokes the cascade mechanic, which could confuse players
> 
> ## **Recommendation:**
> 
> Reduce to single overclock and adjust damage:
> ```
> Cascade Protocol {3}{R}{R}
> Sorcery
> Overclock. (Exile the top three cards of your library. You may play them until end of turn.)
> ~ deals 2 damage to any target for each card exiled this way.
> ```
> 
> This maintains the design intent while fixing balance and complexity issues.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Unclear templating: 'Overclock, then overclock again' should specify total cards exiled",
    "Ambiguous damage clause 'for each card exiled with ~ this way'",
    "Missing reminder text for overclock mechanic",
    "Significantly undercosted for the power level - provides 6 cards of impulse draw plus up to 12 damage",
    "Double overclock creates excessive complexity tracking 6 exiled cards"
  ],
  "name": "Cascade Protocol",
  "mana_cost": "{3}{R}{R}",
  "type_line": "Sorcery",
  "oracle_text": "Overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nCascade Protocol deals 2 damage to any target for each card exiled this way.",
  "rarity": "rare",
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u2014Final log, Research Station Gamma"
}
```

*Tokens: 1449 in / 354 out — $0.0097*

## C) Revised Card

```json
{
  "name": "Cascade Protocol",
  "mana_cost": "{3}{R}{R}",
  "type_line": "Sorcery",
  "oracle_text": "Overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nCascade Protocol deals 2 damage to any target for each card exiled this way.",
  "rarity": "rare",
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u2014Final log, Research Station Gamma"
}
```

**Changes made:**
- Unclear templating: 'Overclock, then overclock again' should specify total cards exiled
- Ambiguous damage clause 'for each card exiled with ~ this way'
- Missing reminder text for overclock mechanic
- Significantly undercosted for the power level - provides 6 cards of impulse draw plus up to 12 damage
- Double overclock creates excessive complexity tracking 6 exiled cards

## D) Cost

- API calls: 2
- Input tokens: 2253
- Output tokens: 994
- Cost: $0.0217