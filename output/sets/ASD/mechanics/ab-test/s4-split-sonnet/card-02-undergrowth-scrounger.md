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
> Looking at this card, I found one templating issue:
> 
> **ISSUE: Missing reminder text**
> - The card uses "salvage 3" but does not include the reminder text in parentheses. According to your specifications, custom mechanics should include reminder text on first use, and this appears to be a common card where reminder text would be especially important for clarity.
> 
> The oracle text should read:
> "When ~ dies, salvage 3. *(Look at the top 3 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*"
> 
> All other templating appears correct:
> - "When ~ dies" is proper current templating
> - Keyword capitalization is consistent (lowercase "salvage")
> - The salvage value of 3 falls within the common scaling range (2-3)
> - Green is an appropriate color for this mechanic per your specifications

*Tokens: 533 in / 209 out — $0.0047*

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
> Looking at Undergrowth Scrounger:
> 
> **Keyword nonbos:** None. The card only has one keyword ability (salvage) that triggers on death.
> 
> **Conditional analysis:** The death trigger is not conditional - it will always trigger when the creature dies during normal play.
> 
> **Kitchen sink design:** No. The card has a single focused effect - it's a creature that salvages when it dies.
> 
> **Variable effects:** The salvage value is fixed at 3, not variable.
> 
> **Focused purpose:** Yes. This is clearly designed as a value creature - you get a 2/1 body for 2 mana that replaces itself with an artifact when it dies. The design encourages aggressive play or trading in combat since the death trigger provides value.
> 
> **Additional observations:**
> - The power level seems appropriate for common - slightly below rate body (2/1 for 2) with upside
> - Salvage 3 at common aligns with the stated scaling (2-3 at common)
> - Green is an approved color for salvage per the mechanic guidelines
> - The flavor text nicely reinforces both the scrounging/salvaging theme and foreshadows the death trigger
> 
> **PASS**

*Tokens: 542 in / 271 out — $0.0057*

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
> Looking at **Undergrowth Scrounger**:
> 
> **Power Level Analysis:**
> - 2/1 for {1}{G} with upside is reasonable at common
> - Salvage 3 on death provides card selection value but requires you to have artifacts in your deck to be meaningful
> - The ability is conditional (only triggers on death) and narrow (artifact-matters)
> 
> **Comparisons to similar printed cards:**
> 1. **Elvish Visionary** (1G, 1/1, ETB draw a card) - This is a classic benchmark that trades immediate guaranteed value for a larger body and conditional value
> 2. **Doomed Traveler** (1W, 1/1, death trigger makes a 1/1 flyer) - Shows precedent for common death-trigger value creatures
> 3. **Sakura-Tribe Elder** (1G, 1/1, sacrifice to ramp) - Another 2-mana green utility creature, though this requires self-sacrifice
> 
> **Assessment:**
> The card fits well within common power level expectations. The 2/1 body for 2 mana is fair, and salvage 3 provides reasonable but not overwhelming value since:
> - It only triggers on death (not guaranteed)
> - It requires artifact density in your deck to be useful
> - It provides selection, not pure card advantage
> - The scaling (salvage 3 at common) matches your stated design guidelines
> 
> The card encourages draft synergies without being oppressive and has appropriate common complexity.
> 
> **PASS** - Power level is appropriate for 2-mana common with conditional, synergy-dependent upside.

*Tokens: 564 in / 369 out — $0.0072*

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
> - Templating: Looking at this card, I found one templating issue:
> 
> **ISSUE: Missing reminder text**
> - The card uses "salvage 3" but does not include the reminder text in parentheses. According to your specifications, custom mechanics should include reminder text on first use, and this appears to be a common card where reminder text would be especially important for clarity.
> 
> The oracle text should read:
> "When ~ dies, salvage 3. *(Look at the top 3 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*"
> 
> All other templating appears correct:
> - "When ~ dies" is proper current templating
> - Keyword capitalization is consistent (lowercase "salvage")
> - The salvage value of 3 falls within the common scaling range (2-3)
> - Green is an appropriate color for this mechanic per your specifications
> - Mechanics: Looking at Undergrowth Scrounger:
> 
> **Keyword nonbos:** None. The card only has one keyword ability (salvage) that triggers on death.
> 
> **Conditional analysis:** The death trigger is not conditional - it will always trigger when the creature dies during normal play.
> 
> **Kitchen sink design:** No. The card has a single focused effect - it's a creature that salvages when it dies.
> 
> **Variable effects:** The salvage value is fixed at 3, not variable.
> 
> **Focused purpose:** Yes. This is clearly designed as a value creature - you get a 2/1 body for 2 mana that replaces itself with an artifact when it dies. The design encourages aggressive play or trading in combat since the death trigger provides value.
> 
> **Additional observations:**
> - The power level seems appropriate for common - slightly below rate body (2/1 for 2) with upside
> - Salvage 3 at common aligns with the stated scaling (2-3 at common)
> - Green is an approved color for salvage per the mechanic guidelines
> - The flavor text nicely reinforces both the scrounging/salvaging theme and foreshadows the death trigger
> 
> **PASS**
> - Balance: Looking at **Undergrowth Scrounger**:
> 
> **Power Level Analysis:**
> - 2/1 for {1}{G} with upside is reasonable at common
> - Salvage 3 on death provides card selection value but requires you to have artifacts in your deck to be meaningful
> - The ability is conditional (only triggers on death) and narrow (artifact-matters)
> 
> **Comparisons to similar printed cards:**
> 1. **Elvish Visionary** (1G, 1/1, ETB draw a card) - This is a classic benchmark that trades immediate guaranteed value for a larger body and conditional value
> 2. **Doomed Traveler** (1W, 1/1, death trigger makes a 1/1 flyer) - Shows precedent for common death-trigger value creatures
> 3. **Sakura-Tribe Elder** (1G, 1/1, sacrifice to ramp) - Another 2-mana green utility creature, though this requires self-sacrifice
> 
> **Assessment:**
> The card fits well within common power level expectations. The 2/1 body for 2 mana is fair, and salvage 3 provides reasonable but not overwhelming value since:
> - It only triggers on death (not guaranteed)
> - It requires artifact density in your deck to be useful
> - It provides selection, not pure card advantage
> - The scaling (salvage 3 at common) matches your stated design guidelines
> 
> The card encourages draft synergies without being oppressive and has appropriate common complexity.
> 
> **PASS** - Power level is appropriate for 2-mana common with conditional, synergy-dependent upside.
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Missing reminder text for salvage ability"
  ],
  "name": "Undergrowth Scrounger",
  "mana_cost": "{1}{G}",
  "type_line": "Creature \u2014 Human Scout",
  "oracle_text": "When ~ dies, salvage 3. (Look at the top 3 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)",
  "power": "2",
  "toughness": "1",
  "rarity": "common",
  "flavor_text": "She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too."
}
```

*Tokens: 1964 in / 306 out — $0.0105*

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
- Missing reminder text for salvage ability

## D) Cost

- API calls: 4
- Input tokens: 3603
- Output tokens: 1155
- Cost: $0.0281