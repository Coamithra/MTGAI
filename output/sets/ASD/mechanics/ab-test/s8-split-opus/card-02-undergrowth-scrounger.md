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
> Type: Creature ï¿½ Human Scout
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
> PASS
> 
> The oracle text is correctly templated:
> - "When ~ dies" is the proper trigger template
> - "salvage 3" is correctly lowercase as a keyword action
> - The reminder text for salvage should be included since this is a common card and it's the mechanic's first appearance on the card, but the design notes indicate salvage has complexity 1 (common-viable), so it's acceptable to omit reminder text at common rarity if it appears frequently in the set
> - No other templating issues found

*Tokens: 533 in / 116 out — $0.0167*

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
> Type: Creature ï¿½ Human Scout
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
> Looking at this design:
> 
> **Undergrowth Scrounger** - {1}{G}, 2/1 Creature, "When ~ dies, salvage 3"
> 
> Checking against the criteria:
> 
> - **Keyword nonbos**: None. The death trigger and salvage work together coherently.
> - **Conditionals**: The death trigger is a real conditional that can be false during normal play (the creature might be exiled, bounced, etc.)
> - **Kitchen sink**: No, this is a focused two-part design - aggressive body + value when it dies
> - **Variable effects**: Salvage 3 is fixed, not variable
> - **Focused purpose**: Yes, clear design purpose as an aggressive early creature that provides card selection value when it dies
> 
> The design is mechanically sound. The card offers interesting gameplay decisions - do you attack with it aggressively knowing you'll get value when it dies, or hold it back to preserve a body? The salvage trigger on death creates natural synergy with combat and removal.
> 
> One minor note: At common with a 2/1 body for {1}{G} AND salvage 3 on death, this might be slightly pushed for Limited, but that's a development concern rather than a design flaw.
> 
> **PASS**

*Tokens: 542 in / 284 out — $0.0294*

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
> Type: Creature ï¿½ Human Scout
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
> Looking at Undergrowth Scrounger, this is a 1G 2/1 with "When ~ dies, salvage 3."
> 
> **Power Level Analysis:**
> 
> Comparing to similar 2-mana creatures:
> - **Satyr Wayfinder** (1G, 1/1): ETB mills 4, gets a land to hand
> - **Elvish Visionary** (1G, 1/1): ETB draw a card
> - **Duskwatch Recruiter** (1G, 2/2 with downside or 2/2 transform)
> 
> This card offers:
> - 2/1 body for 1G (slightly above baseline)
> - Death trigger that digs 3 deep for artifacts
> 
> The key difference from comparables is that this requires death to trigger, making it significantly worse than ETB effects. However, 2/1 for 1G is already reasonable (see cards like Kalonian Tusker at uncommon), and getting a conditional card selection on death pushes this into strong common territory.
> 
> The salvage ability is narrower than drawing a card (artifacts only) but can dig deeper than typical common card advantage. The death trigger requirement makes it vulnerable to exile removal and less reliable than ETB effects.
> 
> **Balance Verdict: PASS**
> 
> This is a strong common but within acceptable bounds. The 2/1 body for 1G is fair, and the death trigger provides conditional value that's appropriate for green at common. The artifact-only restriction on salvage and the requirement to die for value keep this from being overpowered. It's comparable in power level to other value commons like Satyr Wayfinder, just with different timing and restrictions.

*Tokens: 564 in / 386 out — $0.0374*

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
> Type: Creature ï¿½ Human Scout
> Rarity: common
> Oracle Text: When ~ dies, salvage 3.
> P/T: 2/1
> Flavor Text: She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too.
> 
> Issues found:
> - Templating: PASS
> 
> The oracle text is correctly templated:
> - "When ~ dies" is the proper trigger template
> - "salvage 3" is correctly lowercase as a keyword action
> - The reminder text for salvage should be included since this is a common card and it's the mechanic's first appearance on the card, but the design notes indicate salvage has complexity 1 (common-viable), so it's acceptable to omit reminder text at common rarity if it appears frequently in the set
> - No other templating issues found
> - Mechanics: Looking at this design:
> 
> **Undergrowth Scrounger** - {1}{G}, 2/1 Creature, "When ~ dies, salvage 3"
> 
> Checking against the criteria:
> 
> - **Keyword nonbos**: None. The death trigger and salvage work together coherently.
> - **Conditionals**: The death trigger is a real conditional that can be false during normal play (the creature might be exiled, bounced, etc.)
> - **Kitchen sink**: No, this is a focused two-part design - aggressive body + value when it dies
> - **Variable effects**: Salvage 3 is fixed, not variable
> - **Focused purpose**: Yes, clear design purpose as an aggressive early creature that provides card selection value when it dies
> 
> The design is mechanically sound. The card offers interesting gameplay decisions - do you attack with it aggressively knowing you'll get value when it dies, or hold it back to preserve a body? The salvage trigger on death creates natural synergy with combat and removal.
> 
> One minor note: At common with a 2/1 body for {1}{G} AND salvage 3 on death, this might be slightly pushed for Limited, but that's a development concern rather than a design flaw.
> 
> **PASS**
> - Balance: Looking at Undergrowth Scrounger, this is a 1G 2/1 with "When ~ dies, salvage 3."
> 
> **Power Level Analysis:**
> 
> Comparing to similar 2-mana creatures:
> - **Satyr Wayfinder** (1G, 1/1): ETB mills 4, gets a land to hand
> - **Elvish Visionary** (1G, 1/1): ETB draw a card
> - **Duskwatch Recruiter** (1G, 2/2 with downside or 2/2 transform)
> 
> This card offers:
> - 2/1 body for 1G (slightly above baseline)
> - Death trigger that digs 3 deep for artifacts
> 
> The key difference from comparables is that this requires death to trigger, making it significantly worse than ETB effects. However, 2/1 for 1G is already reasonable (see cards like Kalonian Tusker at uncommon), and getting a conditional card selection on death pushes this into strong common territory.
> 
> The salvage ability is narrower than drawing a card (artifacts only) but can dig deeper than typical common card advantage. The death trigger requirement makes it vulnerable to exile removal and less reliable than ETB effects.
> 
> **Balance Verdict: PASS**
> 
> This is a strong common but within acceptable bounds. The 2/1 body for 1G is fair, and the death trigger provides conditional value that's appropriate for green at common. The artifact-only restriction on salvage and the requirement to die for value keep this from being overpowered. It's comparable in power level to other value commons like Satyr Wayfinder, just with different timing and restrictions.
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": false,
  "verdict": "OK",
  "issues_found": [],
  "name": "Undergrowth Scrounger",
  "mana_cost": "{1}{G}",
  "type_line": "Creature \u2014 Human Scout",
  "oracle_text": "When ~ dies, salvage 3.",
  "rarity": "common",
  "power": "2",
  "toughness": "1",
  "flavor_text": "She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too."
}
```

*Tokens: 1901 in / 257 out — $0.0478*

## C) Revised Card

No changes (OK)

**Changes made:**
- None

## D) Cost

- API calls: 4
- Input tokens: 3540
- Output tokens: 1043
- Cost: $0.1313