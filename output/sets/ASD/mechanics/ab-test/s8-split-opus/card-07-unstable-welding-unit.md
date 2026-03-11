# Card 7: Unstable Welding Unit — Strategy: s8-split-opus

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
> PASS
> 
> The templating is correct.
> 
> - **Malfunction 1** is properly templated as a keyword ability with correct reminder text matching the set definition.
> - **Haste** is correctly listed as a separate keyword ability without reminder text, which is standard for evergreen keywords at common.
> - The reminder text is in parentheses on its first (and only) use.
> - Keyword capitalization is consistent (lowercase "malfunction" within reminder text referring to counters, capitalized "Malfunction" as the keyword ability name, capitalized "Haste").
> - The card's stats (4/2 haste for 3 mana at common) align with the malfunction design note that cards should be above-rate, with the entering tapped plus one turn of counter removal providing the tempo cost.
> - Type line, mana cost, and P/T formatting are all standard.

*Tokens: 563 in / 199 out — $0.0078*

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
> Let me work through the checklist carefully.
> 
> **Keyword nonbo check:**
> 
> This is the critical issue. **Malfunction 1 and Haste are a significant nonbo.** Malfunction causes the creature to enter tapped. Haste's primary function is allowing a creature to attack the turn it enters. But a tapped creature can't attack. So on the turn you cast it, Haste does nothing because it's tapped from Malfunction. On your next upkeep, the malfunction counter is removed, but by then the creature no longer has summoning sickness anyway — so Haste is again irrelevant.
> 
> Haste is **completely dead text** in the normal play pattern. The only scenario where Haste matters is if the creature is flickered/blinked (re-enters without Malfunction somehow) or given to you via an opponent's effect, which are extreme edge cases not worth a keyword at common.
> 
> **Other checks:**
> - Kitchen sink: No, only two keywords — but one is nonfunctional, so it reads as complexity without payoff.
> - Focused purpose: The intent seems to be an above-rate aggressive body with a tempo delay, which is a sound Malfunction design. But Haste contradicts the "delayed" identity.
> 
> **Issue found: Haste is negated by Malfunction 1, creating a keyword nonbo where Haste is effectively dead text.** Consider removing Haste, or replacing it with a relevant ability like menace or trample that functions when it actually attacks on turn 2.

*Tokens: 572 in / 349 out — $0.0116*

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
> **Balance Analysis: Unstable Welding Unit**
> 
> Let me work through this carefully.
> 
> **What this card does in practice:**
> 
> Turn 3: You play a 4/2 with haste, but it enters tapped with a malfunction counter. The haste is irrelevant on the turn it enters — it's tapped. On your next upkeep, the counter is removed. Then it can attack as a 4/2 on turn 4.
> 
> So effectively: a 3-mana 4/2 that can't attack until turn 4 (one full turn delay beyond a normal creature).
> 
> **Comparisons:**
> 
> - **Boggart Brute** (3R, 4/2, menace, common): Costs one more mana, has menace (evasion), attacks immediately on curve. This card costs one less mana but attacks one turn later and has no evasion.
> - **Raging Goblin** / **Haste creatures generally**: The haste here is flavor text on the entry turn due to the tapped clause. It only matters if the creature gets bounced and replayed (enters tapped again anyway) or in very niche scenarios.
> - **Oxidda Golem** / various 3-mana 4/2s: A vanilla 4/2 for 3 at common with a one-turn delay is a reasonable limited card — playable filler but not premium.
> 
> **Key Observation:**
> 
> Haste + Malfunction is a nonbo. The haste keyword does essentially nothing here since Malfunction already enters the creature tapped. It *would* matter if the counter were removed by some other effect (counter removal synergy), but at common in limited, this is a 4/2 for 3 that attacks a turn late with no relevant abilities most of the time.
> 
> **This is actually slightly below-rate for a malfunction card**, not above-rate. The haste is a trap/synergy hook rather than real upside in the default case.
> 
> **PASS** — appropriately costed common. The haste creates interesting counter-removal synergy without being threatening in baseline play.

*Tokens: 594 in / 486 out — $0.0151*

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
> - Templating: PASS
> 
> The templating is correct.
> 
> - **Malfunction 1** is properly templated as a keyword ability with correct reminder text matching the set definition.
> - **Haste** is correctly listed as a separate keyword ability without reminder text, which is standard for evergreen keywords at common.
> - The reminder text is in parentheses on its first (and only) use.
> - Keyword capitalization is consistent (lowercase "malfunction" within reminder text referring to counters, capitalized "Malfunction" as the keyword ability name, capitalized "Haste").
> - The card's stats (4/2 haste for 3 mana at common) align with the malfunction design note that cards should be above-rate, with the entering tapped plus one turn of counter removal providing the tempo cost.
> - Type line, mana cost, and P/T formatting are all standard.
> - Mechanics: Let me work through the checklist carefully.
> 
> **Keyword nonbo check:**
> 
> This is the critical issue. **Malfunction 1 and Haste are a significant nonbo.** Malfunction causes the creature to enter tapped. Haste's primary function is allowing a creature to attack the turn it enters. But a tapped creature can't attack. So on the turn you cast it, Haste does nothing because it's tapped from Malfunction. On your next upkeep, the malfunction counter is removed, but by then the creature no longer has summoning sickness anyway — so Haste is again irrelevant.
> 
> Haste is **completely dead text** in the normal play pattern. The only scenario where Haste matters is if the creature is flickered/blinked (re-enters without Malfunction somehow) or given to you via an opponent's effect, which are extreme edge cases not worth a keyword at common.
> 
> **Other checks:**
> - Kitchen sink: No, only two keywords — but one is nonfunctional, so it reads as complexity without payoff.
> - Focused purpose: The intent seems to be an above-rate aggressive body with a tempo delay, which is a sound Malfunction design. But Haste contradicts the "delayed" identity.
> 
> **Issue found: Haste is negated by Malfunction 1, creating a keyword nonbo where Haste is effectively dead text.** Consider removing Haste, or replacing it with a relevant ability like menace or trample that functions when it actually attacks on turn 2.
> - Balance: **Balance Analysis: Unstable Welding Unit**
> 
> Let me work through this carefully.
> 
> **What this card does in practice:**
> 
> Turn 3: You play a 4/2 with haste, but it enters tapped with a malfunction counter. The haste is irrelevant on the turn it enters — it's tapped. On your next upkeep, the counter is removed. Then it can attack as a 4/2 on turn 4.
> 
> So effectively: a 3-mana 4/2 that can't attack until turn 4 (one full turn delay beyond a normal creature).
> 
> **Comparisons:**
> 
> - **Boggart Brute** (3R, 4/2, menace, common): Costs one more mana, has menace (evasion), attacks immediately on curve. This card costs one less mana but attacks one turn later and has no evasion.
> - **Raging Goblin** / **Haste creatures generally**: The haste here is flavor text on the entry turn due to the tapped clause. It only matters if the creature gets bounced and replayed (enters tapped again anyway) or in very niche scenarios.
> - **Oxidda Golem** / various 3-mana 4/2s: A vanilla 4/2 for 3 at common with a one-turn delay is a reasonable limited card — playable filler but not premium.
> 
> **Key Observation:**
> 
> Haste + Malfunction is a nonbo. The haste keyword does essentially nothing here since Malfunction already enters the creature tapped. It *would* matter if the counter were removed by some other effect (counter removal synergy), but at common in limited, this is a 4/2 for 3 that attacks a turn late with no relevant abilities most of the time.
> 
> **This is actually slightly below-rate for a malfunction card**, not above-rate. The haste is a trap/synergy hook rather than real upside in the default case.
> 
> **PASS** — appropriately costed common. The haste creates interesting counter-removal synergy without being threatening in baseline play.
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Haste is a keyword nonbo with Malfunction 1: the creature enters tapped, so Haste is dead text on the turn it's cast. By the next upkeep when the malfunction counter is removed, summoning sickness has already worn off, making Haste irrelevant in virtually all normal play patterns. Replaced Haste with Menace, which provides meaningful evasion when the creature actually attacks."
  ],
  "name": "Unstable Welding Unit",
  "mana_cost": "{2}{R}",
  "type_line": "Artifact Creature \u2014 Construct",
  "oracle_text": "Malfunction 1 (This permanent enters tapped with 1 malfunction counter on it. At the beginning of your upkeep, remove a malfunction counter from it.)\nMenace",
  "rarity": "common",
  "power": "4",
  "toughness": "2",
  "flavor_text": "The sparks it produces are either welding material or a countdown to explosion. Usually both."
}
```

*Tokens: 2452 in / 387 out — $0.0219*

## C) Revised Card

```json
{
  "name": "Unstable Welding Unit",
  "mana_cost": "{2}{R}",
  "type_line": "Artifact Creature \u2014 Construct",
  "oracle_text": "Malfunction 1 (This permanent enters tapped with 1 malfunction counter on it. At the beginning of your upkeep, remove a malfunction counter from it.)\nMenace",
  "rarity": "common",
  "power": "4",
  "toughness": "2",
  "flavor_text": "The sparks it produces are either welding material or a countdown to explosion. Usually both."
}
```

**Changes made:**
- Haste is a keyword nonbo with Malfunction 1: the creature enters tapped, so Haste is dead text on the turn it's cast. By the next upkeep when the malfunction counter is removed, summoning sickness has already worn off, making Haste irrelevant in virtually all normal play patterns. Replaced Haste with Menace, which provides meaningful evasion when the creature actually attacks.

## D) Cost

- API calls: 4
- Input tokens: 4181
- Output tokens: 1421
- Cost: $0.0564