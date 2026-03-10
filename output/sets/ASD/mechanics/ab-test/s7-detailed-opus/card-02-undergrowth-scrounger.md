# Card 2: Undergrowth Scrounger — Strategy: s7-detailed-opus

## A) Original Card

```json
{
  "name": "Undergrowth Scrounger",
  "mana_cost": "{1}{G}",
  "cmc": 2,
  "colors": [
    "G"
  ],
  "type_line": "Creature \u00ef\u00bf\u00bd Human Scout",
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
> Name: Undergrowth Scrounger
> Mana Cost: {1}{G}
> Type: Creature ï¿½ Human Scout
> Rarity: common
> Oracle Text: When ~ dies, salvage 3.
> P/T: 2/1
> Flavor Text: She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too.
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
> ## Undergrowth Scrounger Review
> 
> ### Templating & Rules Text:
> **FAIL** - Missing reminder text for salvage. As a common card introducing a custom mechanic, it must include reminder text on first use. The oracle text should read:
> "When Undergrowth Scrounger dies, salvage 3. *(Look at the top three cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*"
> 
> ### Keyword Interactions:
> **PASS** - No keyword conflicts. The death trigger works cleanly with salvage.
> 
> ### Balance:
> **PASS** - Well-balanced for common. Comparable cards:
> - **Elvish Visionary** (1G, 1/1, draws a card on ETB) - Similar card advantage but immediate
> - **Doomed Traveler** (W, 1/1, leaves a 1/1 flyer on death) - Similar death value
> - **Wild Mongrel** (1G, 2/2, requires discard to pump) - Similar body, different utility
> 
> A 2/1 for 1G that potentially draws a card on death is strong but fair at common. The conditionality of salvage (must find an artifact) and the death requirement balance the aggressive body.
> 
> ### Design:
> **PASS** - Focused, elegant design. The card serves a clear purpose: an aggressive early creature that provides late-game value when it dies. The salvage 3 creates meaningful variance - you might find an artifact, you might not. This encourages interesting deckbuilding decisions around artifact density. The death trigger also creates combat decisions for both players.
> 
> ### Color Pie:
> **PASS** - Green gets efficient small creatures and library manipulation. While artifact-matters is more typically blue/white/red, green can interact with artifacts (see Naturalize effects), and salvage in green represents scavenging/natural reclamation themes. The death trigger also fits green's cycle-of-life philosophy.
> 
> ### Additional Notes:
> - The flavor text excellently captures the danger/reward theme
> - Good introductory common for the salvage mechanic
> - The Human Scout typing is flavorful and mechanically relevant
> 
> **Overall Assessment:** Strong common design that needs only the reminder text correction.

*Tokens: 773 in / 526 out — $0.0510*

### Step 2: Submit revised card based on review

**Prompt sent:**
> Based on the following review of a card, submit the revised card. If no issues were found, return the card unchanged with verdict OK.
> 
> Original card:
> Name: Undergrowth Scrounger
> Mana Cost: {1}{G}
> Type: Creature ï¿½ Human Scout
> Rarity: common
> Oracle Text: When ~ dies, salvage 3.
> P/T: 2/1
> Flavor Text: She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too.
> 
> Review findings:
> ## Undergrowth Scrounger Review
> 
> ### Templating & Rules Text:
> **FAIL** - Missing reminder text for salvage. As a common card introducing a custom mechanic, it must include reminder text on first use. The oracle text should read:
> "When Undergrowth Scrounger dies, salvage 3. *(Look at the top three cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*"
> 
> ### Keyword Interactions:
> **PASS** - No keyword conflicts. The death trigger works cleanly with salvage.
> 
> ### Balance:
> **PASS** - Well-balanced for common. Comparable cards:
> - **Elvish Visionary** (1G, 1/1, draws a card on ETB) - Similar card advantage but immediate
> - **Doomed Traveler** (W, 1/1, leaves a 1/1 flyer on death) - Similar death value
> - **Wild Mongrel** (1G, 2/2, requires discard to pump) - Similar body, different utility
> 
> A 2/1 for 1G that potentially draws a card on death is strong but fair at common. The conditionality of salvage (must find an artifact) and the death requirement balance the aggressive body.
> 
> ### Design:
> **PASS** - Focused, elegant design. The card serves a clear purpose: an aggressive early creature that provides late-game value when it dies. The salvage 3 creates meaningful variance - you might find an artifact, you might not. This encourages interesting deckbuilding decisions around artifact density. The death trigger also creates combat decisions for both players.
> 
> ### Color Pie:
> **PASS** - Green gets efficient small creatures and library manipulation. While artifact-matters is more typically blue/white/red, green can interact with artifacts (see Naturalize effects), and salvage in green represents scavenging/natural reclamation themes. The death trigger also fits green's cycle-of-life philosophy.
> 
> ### Additional Notes:
> - The flavor text excellently captures the danger/reward theme
> - Good introductory common for the salvage mechanic
> - The Human Scout typing is flavorful and mechanically relevant
> 
> **Overall Assessment:** Strong common design that needs only the reminder text correction.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Missing reminder text for salvage mechanic on common card"
  ],
  "name": "Undergrowth Scrounger",
  "mana_cost": "{1}{G}",
  "type_line": "Creature \u2014 Human Scout",
  "oracle_text": "When Undergrowth Scrounger dies, salvage 3. (Look at the top three cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)",
  "power": "2",
  "toughness": "1",
  "rarity": "common",
  "flavor_text": "She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too."
}
```

*Tokens: 1304 in / 315 out — $0.0432*

## C) Revised Card

```json
{
  "name": "Undergrowth Scrounger",
  "mana_cost": "{1}{G}",
  "type_line": "Creature \u2014 Human Scout",
  "oracle_text": "When Undergrowth Scrounger dies, salvage 3. (Look at the top three cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)",
  "rarity": "common",
  "power": "2",
  "toughness": "1",
  "flavor_text": "She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too."
}
```

**Changes made:**
- Missing reminder text for salvage mechanic on common card

## D) Cost

- API calls: 2
- Input tokens: 2077
- Output tokens: 841
- Cost: $0.0942