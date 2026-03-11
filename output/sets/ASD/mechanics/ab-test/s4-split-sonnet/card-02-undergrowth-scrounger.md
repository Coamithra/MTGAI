# Card 2: Undergrowth Scrounger — Strategy: s4-split-sonnet

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
> ## Issues Found
> 
> **1. Missing Reminder Text for Salvage**
> 
> The card is common rarity, and per the set's mechanic guidelines, reminder text is required. "Salvage 3" appears without its reminder text in parentheses.
> 
> Should read:
> > When ~ dies, salvage 3. *(Look at the top three cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*
> 
> Note also that per current Oracle/reminder text conventions, numbers that appear in reminder text are typically written as words ("three") rather than numerals, even if the keyword itself uses a numeral ("salvage 3").
> 
> ---
> 
> **2. Salvage Scaling Check — Flag for Review**
> 
> The guidelines specify Salvage 2–3 at common. Salvage 3 is within range, so this **passes**, but worth confirming intentionality since it's at the top of the common band on a creature that already has a reasonable 2/1 body for {1}{G}.
> 
> ---
> 
> **3. No Other Mechanics Present**
> 
> Malfunction and Overclock do not appear on this card, so no issues there.
> 
> ---
> 
> **Summary:** One clear templating issue — **missing reminder text for Salvage 3**. Everything else is correctly templated.

*Tokens: 531 in / 305 out — $0.0062*

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
> ## Analysis
> 
> **Keyword nonbos:** None. Salvage 3 on death trigger is clean — no self-interference.
> 
> **Conditional check:** "When ~ dies" — yes, this can genuinely fail to trigger during normal play. The creature can be bounced, exiled, or simply win games before dying. The condition is real and meaningful.
> 
> **Kitchen sink check:** Two elements: a 2/1 body and a death trigger with Salvage 3. These are related (aggressive attacker that replaces itself with an artifact when it trades or is removed). Not kitchen sink.
> 
> **Variability check:** Salvage 3 is a fixed value. No variability concern.
> 
> **Focused purpose:** Yes — a cheap aggressive creature that provides card selection value on death, rewarding artifact synergy decks. The flavor of a scrounger who finds useful parts in ruins aligns mechanically. Salvage 3 at common is within spec per the guidelines.
> 
> **One flag worth noting:** Salvage 3 on a 2/1 for {1}{G} is quite strong. The salvage trigger fires *on death*, meaning the opponent must choose between letting the 2/1 attack freely or trading into it and giving you artifact tutoring. This is a clean design tension, but the power level is on the higher end for common — comparable to Elvish Visionary but with more selection. Worth monitoring in development.
> 
> **PASS**

*Tokens: 540 in / 324 out — $0.0065*

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
> ## Undergrowth Scrounger — Balance Analysis
> 
> ### Card Summary
> A 2/1 for {1}{G} that triggers Salvage 3 on death — digging 3 cards deep to find an artifact and putting the rest on the bottom.
> 
> ---
> 
> ### Comparisons
> 
> **Elvish Visionary** (1G, Common) — 1/1, draws a card on ETB. Immediate, unconditional card advantage for the same cost.
> 
> **Elvish Rejuvenator** (2G, Common) — 1/1, ETB puts a land from top 5 into play. Similar dig effect, enters play rather than dying.
> 
> **Catacomb Sifter** (1BG, Uncommon) — 3/3 with a death trigger that Scrys 1. Death trigger, but Scry 1 is far weaker than Salvage 3, and it's uncommon.
> 
> ---
> 
> ### Assessment
> 
> The card is **well-positioned but slightly pushed for common**.
> 
> - A 2/1 for {1}{G} is a reasonable body (Grizzly Bears baseline).
> - Salvage 3 on death is conditional card advantage — it requires dying, targets only artifacts, and digs 3 deep at common (the maximum per your scaling notes).
> - The conditionality (must die, must hit an artifact) meaningfully balances the effect. In artifact-light draws it can whiff.
> - The primary concern is that this functions as a resilient, recursive engine piece in artifact-matters decks — dying into a free artifact tutor is genuinely strong, especially in multiples or with sacrifice synergies.
> 
> The death trigger and artifact restriction keep it honest, but Salvage 3 at common on a reasonable body is doing a lot of work. Worth monitoring in development.
> 
> **PASS** — acceptable at common with the artifact-only restriction providing natural variance.

*Tokens: 562 in / 439 out — $0.0083*

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
> - Templating: ## Issues Found
> 
> **1. Missing Reminder Text for Salvage**
> 
> The card is common rarity, and per the set's mechanic guidelines, reminder text is required. "Salvage 3" appears without its reminder text in parentheses.
> 
> Should read:
> > When ~ dies, salvage 3. *(Look at the top three cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*
> 
> Note also that per current Oracle/reminder text conventions, numbers that appear in reminder text are typically written as words ("three") rather than numerals, even if the keyword itself uses a numeral ("salvage 3").
> 
> ---
> 
> **2. Salvage Scaling Check — Flag for Review**
> 
> The guidelines specify Salvage 2–3 at common. Salvage 3 is within range, so this **passes**, but worth confirming intentionality since it's at the top of the common band on a creature that already has a reasonable 2/1 body for {1}{G}.
> 
> ---
> 
> **3. No Other Mechanics Present**
> 
> Malfunction and Overclock do not appear on this card, so no issues there.
> 
> ---
> 
> **Summary:** One clear templating issue — **missing reminder text for Salvage 3**. Everything else is correctly templated.
> - Mechanics: ## Analysis
> 
> **Keyword nonbos:** None. Salvage 3 on death trigger is clean — no self-interference.
> 
> **Conditional check:** "When ~ dies" — yes, this can genuinely fail to trigger during normal play. The creature can be bounced, exiled, or simply win games before dying. The condition is real and meaningful.
> 
> **Kitchen sink check:** Two elements: a 2/1 body and a death trigger with Salvage 3. These are related (aggressive attacker that replaces itself with an artifact when it trades or is removed). Not kitchen sink.
> 
> **Variability check:** Salvage 3 is a fixed value. No variability concern.
> 
> **Focused purpose:** Yes — a cheap aggressive creature that provides card selection value on death, rewarding artifact synergy decks. The flavor of a scrounger who finds useful parts in ruins aligns mechanically. Salvage 3 at common is within spec per the guidelines.
> 
> **One flag worth noting:** Salvage 3 on a 2/1 for {1}{G} is quite strong. The salvage trigger fires *on death*, meaning the opponent must choose between letting the 2/1 attack freely or trading into it and giving you artifact tutoring. This is a clean design tension, but the power level is on the higher end for common — comparable to Elvish Visionary but with more selection. Worth monitoring in development.
> 
> **PASS**
> - Balance: ## Undergrowth Scrounger — Balance Analysis
> 
> ### Card Summary
> A 2/1 for {1}{G} that triggers Salvage 3 on death — digging 3 cards deep to find an artifact and putting the rest on the bottom.
> 
> ---
> 
> ### Comparisons
> 
> **Elvish Visionary** (1G, Common) — 1/1, draws a card on ETB. Immediate, unconditional card advantage for the same cost.
> 
> **Elvish Rejuvenator** (2G, Common) — 1/1, ETB puts a land from top 5 into play. Similar dig effect, enters play rather than dying.
> 
> **Catacomb Sifter** (1BG, Uncommon) — 3/3 with a death trigger that Scrys 1. Death trigger, but Scry 1 is far weaker than Salvage 3, and it's uncommon.
> 
> ---
> 
> ### Assessment
> 
> The card is **well-positioned but slightly pushed for common**.
> 
> - A 2/1 for {1}{G} is a reasonable body (Grizzly Bears baseline).
> - Salvage 3 on death is conditional card advantage — it requires dying, targets only artifacts, and digs 3 deep at common (the maximum per your scaling notes).
> - The conditionality (must die, must hit an artifact) meaningfully balances the effect. In artifact-light draws it can whiff.
> - The primary concern is that this functions as a resilient, recursive engine piece in artifact-matters decks — dying into a free artifact tutor is genuinely strong, especially in multiples or with sacrifice synergies.
> 
> The death trigger and artifact restriction keep it honest, but Salvage 3 at common on a reasonable body is doing a lot of work. Worth monitoring in development.
> 
> **PASS** — acceptable at common with the artifact-only restriction providing natural variance.
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Missing reminder text for Salvage 3 on a common card. Added parenthetical reminder text per set guidelines, with the number written as a word ('three') inside the reminder text per Oracle conventions."
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

*Tokens: 2454 in / 340 out — $0.0125*

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
- Missing reminder text for Salvage 3 on a common card. Added parenthetical reminder text per set guidelines, with the number written as a word ('three') inside the reminder text per Oracle conventions.

## D) Cost

- API calls: 4
- Input tokens: 4087
- Output tokens: 1408
- Cost: $0.0334