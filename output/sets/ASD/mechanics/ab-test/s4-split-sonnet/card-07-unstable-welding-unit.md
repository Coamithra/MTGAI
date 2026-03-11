# Card 7: Unstable Welding Unit — Strategy: s4-split-sonnet

## A) Original Card

```json
{
  "name": "Unstable Welding Unit",
  "mana_cost": "{2}{R}",
  "cmc": 3,
  "colors": [
    "R"
  ],
  "type_line": "Artifact Creature \u00e2\u20ac\u201d Construct",
  "oracle_text": "Malfunction 1 (This permanent enters tapped with 1 malfunction counter on it. At the beginning of your upkeep, remove a malfunction counter from it.)\nHaste",
  "power": "4",
  "toughness": "2",
  "rarity": "common",
  "keywords": [
    "Malfunction",
    "Haste"
  ],
  "flavor_text": "The sparks it produces are either welding material or a countdown to explosion. Usually both."
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
> Name: Unstable Welding Unit
> Mana Cost: {2}{R}
> Type: Artifact Creature â€” Construct
> Rarity: common
> Oracle Text: Malfunction 1 (This permanent enters tapped with 1 malfunction counter on it. At the beginning of your upkeep, remove a malfunction counter from it.)
> Haste
> P/T: 4/2
> Flavor Text: The sparks it produces are either welding material or a countdown to explosion. Usually both.
> 
> Check:
> - Is the oracle text valid MTG rules text using current templating conventions?
> - Does every custom mechanic (salvage, malfunction, overclock) include reminder text in parentheses on its first use?
> - Is keyword capitalization consistent?
> - Are ability words, keyword abilities, and keyword actions used correctly?
> 
> List any templating issues found, or say "PASS" if the templating is correct.

**Response:**
> ## Review: Unstable Welding Unit
> 
> ### Malfunction Reminder Text
> The reminder text present on the card matches the defined reminder text for Malfunction 1. ✓
> 
> ### Mechanic Usage
> Only Malfunction is used; Salvage and Overclock do not appear. No issues there. ✓
> 
> ### Keyword Capitalization
> - "Malfunction 1" — correct ✓
> - "Haste" — correct ✓
> 
> ### Rules Text Order
> In MTG templating, static/triggered abilities and keyword abilities with reminder text are typically listed before other keyword abilities when the reminder text is present. However, the more relevant convention here is that **Haste should be listed before Malfunction**, or at minimum, intrinsic keyword abilities (Haste) are conventionally listed **before** triggered/complex keyword abilities. Actually, the more standard ordering places simpler keyword abilities first, then more complex ones. Listing Haste after Malfunction is a minor ordering issue — **Haste should precede Malfunction** by standard MTG keyword ordering conventions.
> 
> ### Other Flags
> - The card is **Common** with Malfunction 1 — consistent with the design note (1 at common). ✓
> - Red Malfunction is permitted by color notes. ✓
> - A 4/2 with Haste at {2}{R} that enters tapped for one turn is a **design/balance note**, not a templating issue, but it's intentionally above-rate per the design spec. ✓
> 
> ---
> 
> ### Issues Found:
> 1. **Ability ordering**: "Haste" should appear before "Malfunction 1" per MTG templating conventions (simpler keywords precede complex keyword abilities with reminder text).

*Tokens: 564 in / 399 out — $0.0077*

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
> Name: Unstable Welding Unit
> Mana Cost: {2}{R}
> Type: Artifact Creature â€” Construct
> Rarity: common
> Oracle Text: Malfunction 1 (This permanent enters tapped with 1 malfunction counter on it. At the beginning of your upkeep, remove a malfunction counter from it.)
> Haste
> P/T: 4/2
> Flavor Text: The sparks it produces are either welding material or a countdown to explosion. Usually both.
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
> ## Design Review: Unstable Welding Unit
> 
> ### Keyword Nonbo Check
> 
> **Malfunction + Haste: Partial nonbo.**
> 
> Haste's primary value is attacking or using tap abilities the turn a creature enters the battlefield. Malfunction 1 causes the creature to enter **tapped**, which means Haste is completely negated on the turn it enters — the turn Haste matters most. The creature will be ready to attack on the following turn regardless of whether it has Haste, because Malfunction 1 resolves at the beginning of that upkeep.
> 
> Haste effectively does nothing on this card. It reads as flavorful (it's fast and unstable!) but functionally provides zero mechanical benefit in nearly all game states.
> 
> ### Other Checks
> 
> - **Conditional always false?** N/A — no conditional.
> - **Kitchen sink?** No, only two keywords.
> - **Variable effects?** N/A.
> - **Focused purpose?** Yes — above-rate aggressive beater with a tempo delay cost, which is clean Malfunction design.
> 
> ### Summary
> 
> **One design issue:** Haste is a dead keyword. A 4/2 for {2}{R} that enters tapped will attack on turn 4 with or without Haste. Consider replacing Haste with a more relevant ability (e.g., **Trample**, a triggered ETB effect, or simply no second keyword), or bumping stats slightly and removing Haste entirely.

*Tokens: 573 in / 338 out — $0.0068*

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
> Name: Unstable Welding Unit
> Mana Cost: {2}{R}
> Type: Artifact Creature â€” Construct
> Rarity: common
> Oracle Text: Malfunction 1 (This permanent enters tapped with 1 malfunction counter on it. At the beginning of your upkeep, remove a malfunction counter from it.)
> Haste
> P/T: 4/2
> Flavor Text: The sparks it produces are either welding material or a countdown to explosion. Usually both.
> 
> Check:
> - Is the power level appropriate for the mana cost AND rarity?
> - Compare to 2-3 well-known printed MTG cards at similar mana cost and rarity.
> - Note: malfunction cards are intentionally above-rate — the delayed entry IS the drawback. Do not flag these for being above-rate.
> - Note: mythic rares are allowed to be powerful build-arounds. Do not nerf mythics to rare power level.
> 
> State whether the balance is PASS, or describe the specific balance issue with card comparisons.

**Response:**
> ## Unstable Welding Unit — Balance Analysis
> 
> ### The Card in Context
> - **{2}{R}**, Common, Artifact Creature, 4/2 with Haste and Malfunction 1
> - Malfunction 1 means it enters tapped and can't attack turn 3. It attacks freely from turn 4 onward.
> 
> ---
> 
> ### Comparisons
> 
> **Goblin Heelcutter** ({3}{R}, Common) — 3/2 with Dash {2}{R}, giving haste temporarily. A 4/2 with haste permanently is a strictly better statline for less mana.
> 
> **Brazen Scourge** ({1}{R}{R}, Uncommon) — 3/3 with Haste. At uncommon, costs the same effective mana, is 3/3 vs 4/2 (roughly comparable), and has no drawback.
> 
> **Viashino Pyromancer** ({1}{R}, Common) — 2/1 with a bonus ETB. Far weaker statline.
> 
> ---
> 
> ### Assessment
> 
> **PASS.**
> 
> Malfunction 1 on a 4/2 Haste is above-rate by design, and the delayed entry is a real tempo cost — you're paying 3 mana on turn 3 to get an attacker on turn 4, effectively making it behave closer to a 4-mana creature on entry. By the time it attacks, the board has developed and a 4/2 is solid but not format-warping. The haste becomes relevant primarily in topdeck/late-game situations.
> 
> The Brazen Scourge comparison at uncommon confirms the statline is aggressive but not out of line for Malfunction's intended above-rate philosophy at common.

*Tokens: 595 in / 412 out — $0.0080*

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
> Name: Unstable Welding Unit
> Mana Cost: {2}{R}
> Type: Artifact Creature â€” Construct
> Rarity: common
> Oracle Text: Malfunction 1 (This permanent enters tapped with 1 malfunction counter on it. At the beginning of your upkeep, remove a malfunction counter from it.)
> Haste
> P/T: 4/2
> Flavor Text: The sparks it produces are either welding material or a countdown to explosion. Usually both.
> 
> Issues found:
> - Templating: ## Review: Unstable Welding Unit
> 
> ### Malfunction Reminder Text
> The reminder text present on the card matches the defined reminder text for Malfunction 1. ✓
> 
> ### Mechanic Usage
> Only Malfunction is used; Salvage and Overclock do not appear. No issues there. ✓
> 
> ### Keyword Capitalization
> - "Malfunction 1" — correct ✓
> - "Haste" — correct ✓
> 
> ### Rules Text Order
> In MTG templating, static/triggered abilities and keyword abilities with reminder text are typically listed before other keyword abilities when the reminder text is present. However, the more relevant convention here is that **Haste should be listed before Malfunction**, or at minimum, intrinsic keyword abilities (Haste) are conventionally listed **before** triggered/complex keyword abilities. Actually, the more standard ordering places simpler keyword abilities first, then more complex ones. Listing Haste after Malfunction is a minor ordering issue — **Haste should precede Malfunction** by standard MTG keyword ordering conventions.
> 
> ### Other Flags
> - The card is **Common** with Malfunction 1 — consistent with the design note (1 at common). ✓
> - Red Malfunction is permitted by color notes. ✓
> - A 4/2 with Haste at {2}{R} that enters tapped for one turn is a **design/balance note**, not a templating issue, but it's intentionally above-rate per the design spec. ✓
> 
> ---
> 
> ### Issues Found:
> 1. **Ability ordering**: "Haste" should appear before "Malfunction 1" per MTG templating conventions (simpler keywords precede complex keyword abilities with reminder text).
> - Mechanics: ## Design Review: Unstable Welding Unit
> 
> ### Keyword Nonbo Check
> 
> **Malfunction + Haste: Partial nonbo.**
> 
> Haste's primary value is attacking or using tap abilities the turn a creature enters the battlefield. Malfunction 1 causes the creature to enter **tapped**, which means Haste is completely negated on the turn it enters — the turn Haste matters most. The creature will be ready to attack on the following turn regardless of whether it has Haste, because Malfunction 1 resolves at the beginning of that upkeep.
> 
> Haste effectively does nothing on this card. It reads as flavorful (it's fast and unstable!) but functionally provides zero mechanical benefit in nearly all game states.
> 
> ### Other Checks
> 
> - **Conditional always false?** N/A — no conditional.
> - **Kitchen sink?** No, only two keywords.
> - **Variable effects?** N/A.
> - **Focused purpose?** Yes — above-rate aggressive beater with a tempo delay cost, which is clean Malfunction design.
> 
> ### Summary
> 
> **One design issue:** Haste is a dead keyword. A 4/2 for {2}{R} that enters tapped will attack on turn 4 with or without Haste. Consider replacing Haste with a more relevant ability (e.g., **Trample**, a triggered ETB effect, or simply no second keyword), or bumping stats slightly and removing Haste entirely.
> - Balance: ## Unstable Welding Unit — Balance Analysis
> 
> ### The Card in Context
> - **{2}{R}**, Common, Artifact Creature, 4/2 with Haste and Malfunction 1
> - Malfunction 1 means it enters tapped and can't attack turn 3. It attacks freely from turn 4 onward.
> 
> ---
> 
> ### Comparisons
> 
> **Goblin Heelcutter** ({3}{R}, Common) — 3/2 with Dash {2}{R}, giving haste temporarily. A 4/2 with haste permanently is a strictly better statline for less mana.
> 
> **Brazen Scourge** ({1}{R}{R}, Uncommon) — 3/3 with Haste. At uncommon, costs the same effective mana, is 3/3 vs 4/2 (roughly comparable), and has no drawback.
> 
> **Viashino Pyromancer** ({1}{R}, Common) — 2/1 with a bonus ETB. Far weaker statline.
> 
> ---
> 
> ### Assessment
> 
> **PASS.**
> 
> Malfunction 1 on a 4/2 Haste is above-rate by design, and the delayed entry is a real tempo cost — you're paying 3 mana on turn 3 to get an attacker on turn 4, effectively making it behave closer to a 4-mana creature on entry. By the time it attacks, the board has developed and a 4/2 is solid but not format-warping. The haste becomes relevant primarily in topdeck/late-game situations.
> 
> The Brazen Scourge comparison at uncommon confirms the statline is aggressive but not out of line for Malfunction's intended above-rate philosophy at common.
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Ability ordering: Haste should appear before Malfunction 1 per MTG templating conventions (simpler keywords precede complex keyword abilities with reminder text).",
    "Haste is a dead keyword: Malfunction 1 causes the creature to enter tapped, completely negating Haste on the turn it enters. Haste provides zero mechanical benefit. Replaced with Trample to preserve aggressive identity while being functionally relevant."
  ],
  "name": "Unstable Welding Unit",
  "mana_cost": "{2}{R}",
  "type_line": "Artifact Creature \u2014 Construct",
  "oracle_text": "Trample\nMalfunction 1 (This permanent enters tapped with 1 malfunction counter on it. At the beginning of your upkeep, remove a malfunction counter from it.)",
  "rarity": "common",
  "power": "4",
  "toughness": "2",
  "flavor_text": "The sparks it produces are either welding material or a countdown to explosion. Usually both."
}
```

*Tokens: 2568 in / 388 out — $0.0135*

## C) Revised Card

```json
{
  "name": "Unstable Welding Unit",
  "mana_cost": "{2}{R}",
  "type_line": "Artifact Creature \u2014 Construct",
  "oracle_text": "Trample\nMalfunction 1 (This permanent enters tapped with 1 malfunction counter on it. At the beginning of your upkeep, remove a malfunction counter from it.)",
  "rarity": "common",
  "power": "4",
  "toughness": "2",
  "flavor_text": "The sparks it produces are either welding material or a countdown to explosion. Usually both."
}
```

**Changes made:**
- Ability ordering: Haste should appear before Malfunction 1 per MTG templating conventions (simpler keywords precede complex keyword abilities with reminder text).
- Haste is a dead keyword: Malfunction 1 causes the creature to enter tapped, completely negating Haste on the turn it enters. Haste provides zero mechanical benefit. Replaced with Trample to preserve aggressive identity while being functionally relevant.

## D) Cost

- API calls: 4
- Input tokens: 4300
- Output tokens: 1537
- Cost: $0.0360