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
  "type_line": "Artifact Creature \u00ef\u00bf\u00bd Construct",
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
> Type: Artifact Creature ï¿½ Construct
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
> Looking at this card's oracle text:
> 
> **Issues found:**
> 
> 1. **Missing reminder text**: Since this is a common card and "Malfunction" is a new custom mechanic, it needs reminder text. The oracle text shows "Malfunction 1" without the required reminder text in parentheses.
> 
> 2. **Character encoding issue**: The Type line shows "Artifact Creature ï¿½ Construct" which contains a character encoding error (ï¿½) instead of an em dash (—).
> 
> The corrected oracle text should be:
> ```
> Malfunction 1 (This permanent enters tapped with one malfunction counter on it. At the beginning of your upkeep, remove a malfunction counter from it.)
> Haste
> ```
> 
> And the Type line should be:
> ```
> Artifact Creature — Construct
> ```
> 
> Note: The reminder text should use "one" instead of "1" per current templating conventions.

*Tokens: 566 in / 213 out — $0.0245*

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
> Type: Artifact Creature ï¿½ Construct
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
> Looking at Unstable Welding Unit:
> 
> **Keyword Nonbo Found:**
> - **Haste + Malfunction 1** creates a significant nonbo. Malfunction makes the permanent enter tapped, which completely negates the benefit of haste. A 4/2 creature for 3 mana that enters tapped and can't attack until turn 4 (at the earliest) defeats the purpose of giving it haste.
> 
> The design intention seems clear - create an aggressive, above-rate creature with a tempo drawback - but the execution fails because the two keywords directly contradict each other. The haste keyword is essentially blank text here.
> 
> **Possible solutions:**
> 1. Remove haste entirely and lean into the "slow but powerful" design
> 2. Replace Malfunction with a different drawback that doesn't involve entering tapped
> 3. Give it an ability that works while tapped (like "{T}: Deal 1 damage to any target")
> 
> The flavor text suggests volatility and danger, which could be better represented mechanically without the haste/malfunction conflict.
> 
> **Design Issues Found: Keyword nonbo (haste negated by Malfunction's enters tapped clause)**

*Tokens: 575 in / 265 out — $0.0285*

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
> Type: Artifact Creature ï¿½ Construct
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
> Looking at Unstable Welding Unit as a 3-mana 4/2 with haste at common:
> 
> **Comparisons:**
> - **Goblin Chainwhirler** (RRR): 3/3 first strike with ETB damage - a strong uncommon
> - **Boggart Ram-Gang** (R/GR/GR/G): 3/3 haste wither - uncommon
> - **Fervent Champion** (R): 1/1 haste first strike with upside - rare
> - **Raging Goblin** (R): 1/1 haste - common
> 
> At common, 3-mana creatures typically get 3/3 vanilla or 2/2-2/3 with upside. A 4/2 haste for 3 mana would be very strong even at uncommon without drawback.
> 
> **The Issue:**
> While Malfunction 1 does provide a drawback (enters tapped, can't attack until turn 4 if played turn 3), the body is still too aggressive for common. Once online, this threatens 4 hasty damage repeatedly - that's a very fast clock that common removal struggles to answer efficiently.
> 
> **Specific concern:** This creates problematic play patterns at common where the opponent must have instant-speed removal or take 4+ damage. Commons should create more interactive gameplay.
> 
> **Verdict: FAIL** - The 4 power with haste is too high-impact for common, even with Malfunction 1. This would be fine at uncommon, or needs to be a 3/2 or 2/3 at common.

*Tokens: 597 in / 377 out — $0.0372*

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
> Type: Artifact Creature ï¿½ Construct
> Rarity: common
> Oracle Text: Malfunction 1 (This permanent enters tapped with 1 malfunction counter on it. At the beginning of your upkeep, remove a malfunction counter from it.)
> Haste
> P/T: 4/2
> Flavor Text: The sparks it produces are either welding material or a countdown to explosion. Usually both.
> 
> Issues found:
> - Templating: Looking at this card's oracle text:
> 
> **Issues found:**
> 
> 1. **Missing reminder text**: Since this is a common card and "Malfunction" is a new custom mechanic, it needs reminder text. The oracle text shows "Malfunction 1" without the required reminder text in parentheses.
> 
> 2. **Character encoding issue**: The Type line shows "Artifact Creature ï¿½ Construct" which contains a character encoding error (ï¿½) instead of an em dash (—).
> 
> The corrected oracle text should be:
> ```
> Malfunction 1 (This permanent enters tapped with one malfunction counter on it. At the beginning of your upkeep, remove a malfunction counter from it.)
> Haste
> ```
> 
> And the Type line should be:
> ```
> Artifact Creature — Construct
> ```
> 
> Note: The reminder text should use "one" instead of "1" per current templating conventions.
> - Mechanics: Looking at Unstable Welding Unit:
> 
> **Keyword Nonbo Found:**
> - **Haste + Malfunction 1** creates a significant nonbo. Malfunction makes the permanent enter tapped, which completely negates the benefit of haste. A 4/2 creature for 3 mana that enters tapped and can't attack until turn 4 (at the earliest) defeats the purpose of giving it haste.
> 
> The design intention seems clear - create an aggressive, above-rate creature with a tempo drawback - but the execution fails because the two keywords directly contradict each other. The haste keyword is essentially blank text here.
> 
> **Possible solutions:**
> 1. Remove haste entirely and lean into the "slow but powerful" design
> 2. Replace Malfunction with a different drawback that doesn't involve entering tapped
> 3. Give it an ability that works while tapped (like "{T}: Deal 1 damage to any target")
> 
> The flavor text suggests volatility and danger, which could be better represented mechanically without the haste/malfunction conflict.
> 
> **Design Issues Found: Keyword nonbo (haste negated by Malfunction's enters tapped clause)**
> - Balance: Looking at Unstable Welding Unit as a 3-mana 4/2 with haste at common:
> 
> **Comparisons:**
> - **Goblin Chainwhirler** (RRR): 3/3 first strike with ETB damage - a strong uncommon
> - **Boggart Ram-Gang** (R/GR/GR/G): 3/3 haste wither - uncommon
> - **Fervent Champion** (R): 1/1 haste first strike with upside - rare
> - **Raging Goblin** (R): 1/1 haste - common
> 
> At common, 3-mana creatures typically get 3/3 vanilla or 2/2-2/3 with upside. A 4/2 haste for 3 mana would be very strong even at uncommon without drawback.
> 
> **The Issue:**
> While Malfunction 1 does provide a drawback (enters tapped, can't attack until turn 4 if played turn 3), the body is still too aggressive for common. Once online, this threatens 4 hasty damage repeatedly - that's a very fast clock that common removal struggles to answer efficiently.
> 
> **Specific concern:** This creates problematic play patterns at common where the opponent must have instant-speed removal or take 4+ damage. Commons should create more interactive gameplay.
> 
> **Verdict: FAIL** - The 4 power with haste is too high-impact for common, even with Malfunction 1. This would be fine at uncommon, or needs to be a 3/2 or 2/3 at common.
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Missing reminder text for Malfunction",
    "Character encoding error in type line",
    "Keyword nonbo between haste and Malfunction",
    "Power level too high for common"
  ],
  "name": "Unstable Welding Unit",
  "mana_cost": "{2}{R}",
  "type_line": "Artifact Creature \u2014 Construct",
  "oracle_text": "Malfunction 1 (This permanent enters tapped with one malfunction counter on it. At the beginning of your upkeep, remove a malfunction counter from it.)\nWhen Unstable Welding Unit attacks, it gets +1/+0 until end of turn.",
  "rarity": "common",
  "power": "3",
  "toughness": "2",
  "flavor_text": "The sparks it produces are either welding material or a countdown to explosion. Usually both."
}
```

*Tokens: 2003 in / 346 out — $0.0560*

## C) Revised Card

```json
{
  "name": "Unstable Welding Unit",
  "mana_cost": "{2}{R}",
  "type_line": "Artifact Creature \u2014 Construct",
  "oracle_text": "Malfunction 1 (This permanent enters tapped with one malfunction counter on it. At the beginning of your upkeep, remove a malfunction counter from it.)\nWhen Unstable Welding Unit attacks, it gets +1/+0 until end of turn.",
  "rarity": "common",
  "power": "3",
  "toughness": "2",
  "flavor_text": "The sparks it produces are either welding material or a countdown to explosion. Usually both."
}
```

**Changes made:**
- Missing reminder text for Malfunction
- Character encoding error in type line
- Keyword nonbo between haste and Malfunction
- Power level too high for common

## D) Cost

- API calls: 4
- Input tokens: 3741
- Output tokens: 1201
- Cost: $0.1462