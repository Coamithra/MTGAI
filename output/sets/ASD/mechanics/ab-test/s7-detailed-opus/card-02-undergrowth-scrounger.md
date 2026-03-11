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
  "type_line": "Creature \u00e2\u20ac\u201d Human Scout",
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
> Type: Creature â€” Human Scout
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
> ## Card Review: Undergrowth Scrounger
> 
> ---
> 
> ### Templating & Rules Text
> 
> **Is the oracle text valid MTG rules text?**
> PASS — "When ~ dies, salvage 3." is clean, correct triggered ability templating. Dies triggers are well-established.
> 
> **Does every custom mechanic have reminder text on first use?**
> **ISSUE** — At common, salvage should include its reminder text. The card as written shows only "salvage 3" with no reminder text parenthetical. It should read:
> 
> > When ~ dies, salvage 3. *(Look at the top 3 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*
> 
> **Is capitalization consistent?**
> PASS — "salvage" appears mid-sentence and is lowercase, which is correct for keyword actions (compare: "scry 2", "surveil 3").
> 
> **Does the card use current MTG templating?**
> PASS — No enters-the-battlefield effects are present; "dies" is current templating.
> 
> ---
> 
> ### Keyword Interactions
> 
> **Are there any keywords negated or made useless by other abilities?**
> PASS — No conflicting interactions. The death trigger and salvage work independently and logically together.
> 
> **If there's a conditional, can the condition actually be false?**
> PASS — The only condition is "dies," which is a standard trigger that can naturally be true or false depending on game events. No always-on issue.
> 
> ---
> 
> ### Balance
> 
> **Is power level appropriate for mana cost and rarity?**
> 
> PASS — A 2/1 for {1}{G} is a slightly below-rate baseline (compare **Elvish Visionary** at 1/1 that draws a card on ETB, or **Satyr Wayfinder** at 1/1 that fills the graveyard and finds a land). The death trigger is notably weaker than an ETB trigger because:
> 
> - It requires the creature to die (not guaranteed, and opponent controls timing somewhat).
> - Salvage 3 only digs for *artifacts*, which is narrower than drawing a card.
> - Looking at 3 cards at common is within the stated scaling (2–3).
> 
> This compares favorably to something like **Mire Triton** (2-mana 2/1, deathtouch, self-mill on ETB) — Undergrowth Scrounger trades deathtouch and guaranteed value for a conditional, narrow dig. Feels appropriately powered for common.
> 
> ---
> 
> ### Design
> 
> **Does the card have a focused purpose?**
> PASS — Very focused. It's a cheap body that provides artifact-related card selection as a consolation prize on death. Clean, single-purpose common design.
> 
> **Is variability real?**
> PASS — Salvage 3 always looks at exactly 3 cards, but the outcome genuinely varies based on library composition. You might hit zero artifacts or one, creating real variance.
> 
> **Does the card create interesting gameplay decisions?**
> PASS — Modest but real. The opponent has a decision about whether to kill it (granting the salvage trigger) or leave it alive. The controller may make favorable attacks knowing the death payoff. For a common, this is an appropriate level of decision-making.
> 
> ---
> 
> ### Color Pie
> 
> **Are all abilities appropriate for this card's color(s)?**
> PASS — Green is listed as a salvage color (W, U, G). Green commonly has death triggers on creatures (e.g., **Yavimaya Elder**). Green frequently tutors or digs for specific card types. A Human Scout creature type in green is standard.
> 
> ---
> 
> ### Additional Notes
> 
> - **Flavor text** is excellent for a common — evocative, concise, and tonally appropriate for the set's theme.
> - **Creature type Human Scout** fits well for a green creature that scrounges through ruins.
> - Minor consideration: at common in limited, this card's value is directly tied to the density of artifacts in the set. If the set has a healthy artifact count, this is a nice role-player; if not, it's a vanilla 2/1 with flavor text. Ensure as-fan supports this.
> 
> ---
> 
> ### Final Verdict
> **Mostly clean. One fix required:** Add reminder text for salvage. Otherwise, this is a well-designed, appropriately powered common that supports the set's artifact themes without overcomplicating the board at common rarity.

*Tokens: 770 in / 1029 out — $0.0296*

### Step 2: Submit revised card based on review

**Prompt sent:**
> Based on the following review of a card, submit the revised card. If no issues were found, return the card unchanged with verdict OK.
> 
> Original card:
> Name: Undergrowth Scrounger
> Mana Cost: {1}{G}
> Type: Creature â€” Human Scout
> Rarity: common
> Oracle Text: When ~ dies, salvage 3.
> P/T: 2/1
> Flavor Text: She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too.
> 
> Review findings:
> ## Card Review: Undergrowth Scrounger
> 
> ---
> 
> ### Templating & Rules Text
> 
> **Is the oracle text valid MTG rules text?**
> PASS — "When ~ dies, salvage 3." is clean, correct triggered ability templating. Dies triggers are well-established.
> 
> **Does every custom mechanic have reminder text on first use?**
> **ISSUE** — At common, salvage should include its reminder text. The card as written shows only "salvage 3" with no reminder text parenthetical. It should read:
> 
> > When ~ dies, salvage 3. *(Look at the top 3 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*
> 
> **Is capitalization consistent?**
> PASS — "salvage" appears mid-sentence and is lowercase, which is correct for keyword actions (compare: "scry 2", "surveil 3").
> 
> **Does the card use current MTG templating?**
> PASS — No enters-the-battlefield effects are present; "dies" is current templating.
> 
> ---
> 
> ### Keyword Interactions
> 
> **Are there any keywords negated or made useless by other abilities?**
> PASS — No conflicting interactions. The death trigger and salvage work independently and logically together.
> 
> **If there's a conditional, can the condition actually be false?**
> PASS — The only condition is "dies," which is a standard trigger that can naturally be true or false depending on game events. No always-on issue.
> 
> ---
> 
> ### Balance
> 
> **Is power level appropriate for mana cost and rarity?**
> 
> PASS — A 2/1 for {1}{G} is a slightly below-rate baseline (compare **Elvish Visionary** at 1/1 that draws a card on ETB, or **Satyr Wayfinder** at 1/1 that fills the graveyard and finds a land). The death trigger is notably weaker than an ETB trigger because:
> 
> - It requires the creature to die (not guaranteed, and opponent controls timing somewhat).
> - Salvage 3 only digs for *artifacts*, which is narrower than drawing a card.
> - Looking at 3 cards at common is within the stated scaling (2–3).
> 
> This compares favorably to something like **Mire Triton** (2-mana 2/1, deathtouch, self-mill on ETB) — Undergrowth Scrounger trades deathtouch and guaranteed value for a conditional, narrow dig. Feels appropriately powered for common.
> 
> ---
> 
> ### Design
> 
> **Does the card have a focused purpose?**
> PASS — Very focused. It's a cheap body that provides artifact-related card selection as a consolation prize on death. Clean, single-purpose common design.
> 
> **Is variability real?**
> PASS — Salvage 3 always looks at exactly 3 cards, but the outcome genuinely varies based on library composition. You might hit zero artifacts or one, creating real variance.
> 
> **Does the card create interesting gameplay decisions?**
> PASS — Modest but real. The opponent has a decision about whether to kill it (granting the salvage trigger) or leave it alive. The controller may make favorable attacks knowing the death payoff. For a common, this is an appropriate level of decision-making.
> 
> ---
> 
> ### Color Pie
> 
> **Are all abilities appropriate for this card's color(s)?**
> PASS — Green is listed as a salvage color (W, U, G). Green commonly has death triggers on creatures (e.g., **Yavimaya Elder**). Green frequently tutors or digs for specific card types. A Human Scout creature type in green is standard.
> 
> ---
> 
> ### Additional Notes
> 
> - **Flavor text** is excellent for a common — evocative, concise, and tonally appropriate for the set's theme.
> - **Creature type Human Scout** fits well for a green creature that scrounges through ruins.
> - Minor consideration: at common in limited, this card's value is directly tied to the density of artifacts in the set. If the set has a healthy artifact count, this is a nice role-player; if not, it's a vanilla 2/1 with flavor text. Ensure as-fan supports this.
> 
> ---
> 
> ### Final Verdict
> **Mostly clean. One fix required:** Add reminder text for salvage. Otherwise, this is a well-designed, appropriately powered common that supports the set's artifact themes without overcomplicating the board at common rarity.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Missing reminder text for the custom keyword 'salvage' at common rarity."
  ],
  "name": "Undergrowth Scrounger",
  "mana_cost": "{1}{G}",
  "type_line": "Creature \u2014 Human Scout",
  "oracle_text": "When ~ dies, salvage 3. (Look at the top 3 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)",
  "rarity": "common",
  "power": "2",
  "toughness": "1",
  "flavor_text": "She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too."
}
```

*Tokens: 2077 in / 316 out — $0.0183*

## C) Revised Card

```json
{
  "name": "Undergrowth Scrounger",
  "mana_cost": "{1}{G}",
  "type_line": "Creature \u2014 Human Scout",
  "oracle_text": "When ~ dies, salvage 3. (Look at the top 3 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)",
  "rarity": "common",
  "power": "2",
  "toughness": "1",
  "flavor_text": "She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too."
}
```

**Changes made:**
- Missing reminder text for the custom keyword 'salvage' at common rarity.

## D) Cost

- API calls: 2
- Input tokens: 2847
- Output tokens: 1345
- Cost: $0.0479