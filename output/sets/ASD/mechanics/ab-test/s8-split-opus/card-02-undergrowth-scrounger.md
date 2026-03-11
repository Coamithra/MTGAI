# Card 2: Undergrowth Scrounger — Strategy: s8-split-opus

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
> Name: Undergrowth Scrounger
> Mana Cost: {1}{G}
> Type: Creature â€” Human Scout
> Rarity: common
> Oracle Text: When ~ dies, salvage 3.
> P/T: 2/1
> Flavor Text: She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too.
> 
> Check:
> - Is the oracle text valid MTG rules text using current templating conventions?
> - Does every custom mechanic (salvage, malfunction, overclock) include reminder text in parentheses on its first use?
> - Is keyword capitalization consistent?
> - Are ability words, keyword abilities, and keyword actions used correctly?
> 
> List any templating issues found, or say "PASS" if the templating is correct.

**Response:**
> Looking at the card:
> 
> **Name:** Undergrowth Scrounger
> **Oracle Text:** When ~ dies, salvage 3.
> 
> **Issues found:**
> 
> 1. **Missing reminder text for salvage.** Per the review criteria, every custom mechanic must include reminder text in parentheses on its first use on the card. It should read:
> 
> > When ~ dies, salvage 3. *(Look at the top three cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*
> 
> Note: The reminder text should spell out "three" rather than use the numeral "3," matching standard MTG templating conventions for reminder text (e.g., surveil 3's reminder text says "three").
> 
> No other issues found. The triggered ability template ("When ~ dies" + action) is correct, the capitalization is consistent, salvage is properly used as a keyword ability, and the card's complexity and scaling (salvage 3 at common) align with the set's design parameters.

*Tokens: 530 in / 238 out — $0.0086*

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
> Name: Undergrowth Scrounger
> Mana Cost: {1}{G}
> Type: Creature â€” Human Scout
> Rarity: common
> Oracle Text: When ~ dies, salvage 3.
> P/T: 2/1
> Flavor Text: She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too.
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
> PASS
> 
> The design is clean and focused. A 2/1 for {1}{G} is a reasonable common body, and Salvage 3 on death gives it a clear role as a value creature that replaces itself (conditionally) when it trades. The death trigger and Salvage work well together thematically (the scout finds something useful as she falls) and mechanically (you're incentivized to trade aggressively in combat, which green commons want to do).
> 
> No issues found:
> - **No keyword nonbos.** Nothing on the card prevents it from dying or conflicts with Salvage.
> - **The conditional (dying) is naturally and frequently true** in normal gameplay through combat and removal.
> - **Not kitchen sink.** One body, one triggered ability.
> - **No false variability.** Salvage 3 is a fixed value.
> - **Focused purpose.** Early board presence that rewards artifact-heavy deckbuilding and incentivizes aggressive trading.
> 
> Salvage 3 at common is within the stated scaling guidelines (2–3 at common). The overall power level feels appropriate for a common—comparable to cards like Elvish Visionary in feel, but narrower since it requires artifacts in the deck and requires the creature to die first.

*Tokens: 539 in / 286 out — $0.0098*

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
> Name: Undergrowth Scrounger
> Mana Cost: {1}{G}
> Type: Creature â€” Human Scout
> Rarity: common
> Oracle Text: When ~ dies, salvage 3.
> P/T: 2/1
> Flavor Text: She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too.
> 
> Check:
> - Is the power level appropriate for the mana cost AND rarity?
> - Compare to 2-3 well-known printed MTG cards at similar mana cost and rarity.
> - Note: malfunction cards are intentionally above-rate — the delayed entry IS the drawback. Do not flag these for being above-rate.
> - Note: mythic rares are allowed to be powerful build-arounds. Do not nerf mythics to rare power level.
> 
> State whether the balance is PASS, or describe the specific balance issue with card comparisons.

**Response:**
> **Balance Assessment: PASS**
> 
> ---
> 
> **Card Analysis:**
> 
> Undergrowth Scrounger is a 2/1 for {1}{G} with a death trigger that provides card selection (Salvage 3 — look at top 3, find an artifact or whiff). This is a clean, well-designed common.
> 
> ---
> 
> **Comparisons:**
> 
> 1. **Elvish Visionary** ({1}{G}, 1/1, ETB draw a card) — The gold standard for green 2-drop value creatures. Visionary guarantees a card on entry. Scrounger has a better body (2/1 vs 1/1), but its value is conditional (death trigger, not ETB) and the Salvage 3 can whiff if no artifact is in the top 3. Significantly weaker overall value generation.
> 
> 2. **Satyr Wayfinder** ({1}{G}, 1/1, ETB mill 4 and grab a land) — Another value 2-drop. Wayfinder's ability is an ETB (more reliable), hits a more common card type (lands), and fuels the graveyard. Scrounger trades up better in combat but offers less consistent value.
> 
> 3. **Fireblade Charger** ({R}, 1/1, death trigger deals damage) — Similar "aggressive body + death trigger value" template. Scrounger is appropriately scaled up for costing one more mana with a bigger body and a selection-based death trigger.
> 
> ---
> 
> **Reasoning:**
> 
> - A 2/1 for 2 is a baseline common body.
> - The death trigger (not ETB) adds meaningful delay and counterplay.
> - Salvage 3 at common is on-rate per the mechanic's scaling guidelines.
> - The artifact-specific filter means this can legitimately miss, keeping it fair.
> - Serves a clear draft role: enables artifact-matters synergies in green without being oppressive.
> 
> No issues with complexity, color pie, or templating.

*Tokens: 561 in / 467 out — $0.0145*

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
> Name: Undergrowth Scrounger
> Mana Cost: {1}{G}
> Type: Creature â€” Human Scout
> Rarity: common
> Oracle Text: When ~ dies, salvage 3.
> P/T: 2/1
> Flavor Text: She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too.
> 
> Issues found:
> - Templating: Looking at the card:
> 
> **Name:** Undergrowth Scrounger
> **Oracle Text:** When ~ dies, salvage 3.
> 
> **Issues found:**
> 
> 1. **Missing reminder text for salvage.** Per the review criteria, every custom mechanic must include reminder text in parentheses on its first use on the card. It should read:
> 
> > When ~ dies, salvage 3. *(Look at the top three cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*
> 
> Note: The reminder text should spell out "three" rather than use the numeral "3," matching standard MTG templating conventions for reminder text (e.g., surveil 3's reminder text says "three").
> 
> No other issues found. The triggered ability template ("When ~ dies" + action) is correct, the capitalization is consistent, salvage is properly used as a keyword ability, and the card's complexity and scaling (salvage 3 at common) align with the set's design parameters.
> - Mechanics: PASS
> 
> The design is clean and focused. A 2/1 for {1}{G} is a reasonable common body, and Salvage 3 on death gives it a clear role as a value creature that replaces itself (conditionally) when it trades. The death trigger and Salvage work well together thematically (the scout finds something useful as she falls) and mechanically (you're incentivized to trade aggressively in combat, which green commons want to do).
> 
> No issues found:
> - **No keyword nonbos.** Nothing on the card prevents it from dying or conflicts with Salvage.
> - **The conditional (dying) is naturally and frequently true** in normal gameplay through combat and removal.
> - **Not kitchen sink.** One body, one triggered ability.
> - **No false variability.** Salvage 3 is a fixed value.
> - **Focused purpose.** Early board presence that rewards artifact-heavy deckbuilding and incentivizes aggressive trading.
> 
> Salvage 3 at common is within the stated scaling guidelines (2–3 at common). The overall power level feels appropriate for a common—comparable to cards like Elvish Visionary in feel, but narrower since it requires artifacts in the deck and requires the creature to die first.
> - Balance: **Balance Assessment: PASS**
> 
> ---
> 
> **Card Analysis:**
> 
> Undergrowth Scrounger is a 2/1 for {1}{G} with a death trigger that provides card selection (Salvage 3 — look at top 3, find an artifact or whiff). This is a clean, well-designed common.
> 
> ---
> 
> **Comparisons:**
> 
> 1. **Elvish Visionary** ({1}{G}, 1/1, ETB draw a card) — The gold standard for green 2-drop value creatures. Visionary guarantees a card on entry. Scrounger has a better body (2/1 vs 1/1), but its value is conditional (death trigger, not ETB) and the Salvage 3 can whiff if no artifact is in the top 3. Significantly weaker overall value generation.
> 
> 2. **Satyr Wayfinder** ({1}{G}, 1/1, ETB mill 4 and grab a land) — Another value 2-drop. Wayfinder's ability is an ETB (more reliable), hits a more common card type (lands), and fuels the graveyard. Scrounger trades up better in combat but offers less consistent value.
> 
> 3. **Fireblade Charger** ({R}, 1/1, death trigger deals damage) — Similar "aggressive body + death trigger value" template. Scrounger is appropriately scaled up for costing one more mana with a bigger body and a selection-based death trigger.
> 
> ---
> 
> **Reasoning:**
> 
> - A 2/1 for 2 is a baseline common body.
> - The death trigger (not ETB) adds meaningful delay and counterplay.
> - Salvage 3 at common is on-rate per the mechanic's scaling guidelines.
> - The artifact-specific filter means this can legitimately miss, keeping it fair.
> - Serves a clear draft role: enables artifact-matters synergies in green without being oppressive.
> 
> No issues with complexity, color pie, or templating.
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Missing reminder text for salvage keyword. Custom mechanics must include reminder text in parentheses on first use. The numeral in the reminder text should be spelled out as 'three' per standard MTG templating conventions."
  ],
  "name": "Undergrowth Scrounger",
  "mana_cost": "{1}{G}",
  "type_line": "Creature \u2014 Human Scout",
  "oracle_text": "When ~ dies, salvage 3. (Look at the top three cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)",
  "rarity": "common",
  "power": "2",
  "toughness": "1",
  "flavor_text": "She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too."
}
```

*Tokens: 2376 in / 343 out — $0.0205*

## C) Revised Card

```json
{
  "name": "Undergrowth Scrounger",
  "mana_cost": "{1}{G}",
  "type_line": "Creature \u2014 Human Scout",
  "oracle_text": "When ~ dies, salvage 3. (Look at the top three cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)",
  "rarity": "common",
  "power": "2",
  "toughness": "1",
  "flavor_text": "She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too."
}
```

**Changes made:**
- Missing reminder text for salvage keyword. Custom mechanics must include reminder text in parentheses on first use. The numeral in the reminder text should be spelled out as 'three' per standard MTG templating conventions.

## D) Cost

- API calls: 4
- Input tokens: 4006
- Output tokens: 1334
- Cost: $0.0534