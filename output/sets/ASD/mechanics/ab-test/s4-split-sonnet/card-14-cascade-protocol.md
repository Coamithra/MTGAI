# Card 14: Cascade Protocol — Strategy: s4-split-sonnet

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
> Name: Cascade Protocol
> Mana Cost: {3}{R}{R}
> Type: Sorcery
> Rarity: rare
> Oracle Text: Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)
> ~ deals 2 damage to any target for each card exiled with ~ this way.
> Flavor Text: "The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion." ï¿½Final log, Research Station Gamma
> 
> Check:
> - Is the oracle text valid MTG rules text using current templating conventions?
> - Does every custom mechanic (salvage, malfunction, overclock) include reminder text in parentheses on its first use?
> - Is keyword capitalization consistent?
> - Are ability words, keyword abilities, and keyword actions used correctly?
> 
> List any templating issues found, or say "PASS" if the templating is correct.

**Response:**
> Looking at this card's templating:
> 
> **ISSUES FOUND:**
> 
> 1. **Incomplete reminder text**: The reminder text only appears once after the second "overclock" instead of after each instance. It should read:
>    ```
>    Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn. Exile the top three cards of your library. You may play them until end of turn.)
>    ```
>    OR more elegantly:
>    ```
>    Overclock twice. (Exile the top three cards of your library. You may play them until end of turn.)
>    ```
> 
> 2. **Pronoun reference issue**: The second sentence uses "~" to refer to the spell, but by the time the damage is dealt, the sorcery will have already resolved and be in the graveyard. The templating should likely track the exiled cards differently, such as:
>    ```
>    "~ deals 2 damage to any target for each card exiled this way."
>    ```
> 
> 3. **Minor formatting**: There appears to be a character encoding issue in the flavor text with "ï¿½" which should be an em dash "—".
> 
> **SUGGESTED ORACLE TEXT:**
> ```
> Overclock twice. (Exile the top three cards of your library. You may play them until end of turn.)
> Cascade Protocol deals 2 damage to any target for each card exiled this way.
> ```
> 
> The keyword capitalization is correct (lowercase "overclock"), and the mechanic usage follows the established pattern.

*Tokens: 564 in / 352 out — $0.0070*

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
> Name: Cascade Protocol
> Mana Cost: {3}{R}{R}
> Type: Sorcery
> Rarity: rare
> Oracle Text: Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)
> ~ deals 2 damage to any target for each card exiled with ~ this way.
> Flavor Text: "The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion." ï¿½Final log, Research Station Gamma
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
> Looking at this design, I found several issues:
> 
> **DESIGN ISSUES:**
> 
> 1. **Keyword nonbo**: The reminder text creates confusion. You wrote "Overclock, then overclock again" followed by reminder text that only explains one instance of overclock. This makes it unclear whether the card exiles 3 or 6 cards total.
> 
> 2. **Fake variability**: The damage clause says "for each card exiled with ~ this way" but overclock always exiles exactly 3 cards (per your design notes). If this does overclock twice, it will always exile 6 cards and always deal 12 damage. The "for each" templating suggests variability that doesn't actually exist.
> 
> 3. **Templating ambiguity**: The current wording doesn't clearly establish whether the damage references cards from both overclock instances or just one. If it's meant to count all exiled cards, the templating should be clearer.
> 
> **SUGGESTIONS:**
> - If this exiles 6 total cards, consider templating like: "Exile the top six cards of your library. You may play them until end of turn. ~ deals 2 damage to any target for each card exiled this way."
> - Or clarify the interaction between multiple overclock instances in the reminder text
> - The core concept (double overclock + damage scaling) is solid and focused, but the execution needs cleaning up
> 
> The design has a clear purpose (high-risk burn spell that scales with card access), but the templating issues need resolution.

*Tokens: 573 in / 337 out — $0.0068*

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
> Name: Cascade Protocol
> Mana Cost: {3}{R}{R}
> Type: Sorcery
> Rarity: rare
> Oracle Text: Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)
> ~ deals 2 damage to any target for each card exiled with ~ this way.
> Flavor Text: "The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion." ï¿½Final log, Research Station Gamma
> 
> Check:
> - Is the power level appropriate for the mana cost AND rarity?
> - Compare to 2-3 well-known printed MTG cards at similar mana cost and rarity.
> - Note: malfunction cards are intentionally above-rate — the delayed entry IS the drawback. Do not flag these for being above-rate.
> - Note: mythic rares are allowed to be powerful build-arounds. Do not nerf mythics to rare power level.
> 
> State whether the balance is PASS, or describe the specific balance issue with card comparisons.

**Response:**
> **Power Level Analysis: Cascade Protocol**
> 
> **What this card does:**
> - 5 mana sorcery
> - Exiles 6 cards total (3 + 3 from double overclock)
> - Deals 12 damage to any target (2 × 6 exiled cards)
> - Gives temporary access to 6 exiled cards until end of turn
> 
> **Power Level Assessment: FAIL - Significantly Overpowered**
> 
> **Specific Balance Issues:**
> 
> 1. **Damage Rate is Excessive**: 12 damage for 5 mana at sorcery speed is far above the damage curve. Compare to:
>    - **Lightning Bolt**: 3 damage for 1 mana (3:1 ratio)
>    - **Lava Axe**: 5 damage for 5 mana (1:1 ratio)  
>    - **Cascade Protocol**: 12 damage for 5 mana (2.4:1 ratio)
> 
> 2. **Card Advantage is Too High**: Getting 6 cards of selection with 12 damage stapled on creates enormous value. Similar effects:
>    - **Act on Impulse** (3 mana): Exiles 3 cards, playable until end of turn - no damage
>    - **Light Up the Stage** (2 mana): Exiles 2 cards, playable until end of turn - no damage
>    - **Cascade Protocol**: Does both effects at premium efficiency
> 
> 3. **Flexibility Problem**: The "any target" clause makes this both premium removal AND face damage, eliminating tactical decisions.
> 
> **Comparable Cards:**
> - **Crater's Claws** (X=7): 5 mana for 7 damage to any target - significantly weaker
> - **Banefire** (X=4): 5 mana for 4 damage, uncounterable - much weaker damage
> - **Chandra, Torch of Defiance** (4 mana planeswalker): Can exile 1 card OR deal 2 damage per turn - much slower
> 
> **Recommended Fix:**
> Either reduce to 6 total damage (1 per card) OR limit targeting to "target creature or planeswalker" OR increase cost to 6-7 mana. The current version provides rare-level card selection with mythic-level damage at an uncommon-level cost.
> 
> **Verdict: FAIL** - Needs significant power level reduction.

*Tokens: 595 in / 567 out — $0.0103*

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
> Name: Cascade Protocol
> Mana Cost: {3}{R}{R}
> Type: Sorcery
> Rarity: rare
> Oracle Text: Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)
> ~ deals 2 damage to any target for each card exiled with ~ this way.
> Flavor Text: "The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion." ï¿½Final log, Research Station Gamma
> 
> Issues found:
> - Templating: Looking at this card's templating:
> 
> **ISSUES FOUND:**
> 
> 1. **Incomplete reminder text**: The reminder text only appears once after the second "overclock" instead of after each instance. It should read:
>    ```
>    Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn. Exile the top three cards of your library. You may play them until end of turn.)
>    ```
>    OR more elegantly:
>    ```
>    Overclock twice. (Exile the top three cards of your library. You may play them until end of turn.)
>    ```
> 
> 2. **Pronoun reference issue**: The second sentence uses "~" to refer to the spell, but by the time the damage is dealt, the sorcery will have already resolved and be in the graveyard. The templating should likely track the exiled cards differently, such as:
>    ```
>    "~ deals 2 damage to any target for each card exiled this way."
>    ```
> 
> 3. **Minor formatting**: There appears to be a character encoding issue in the flavor text with "ï¿½" which should be an em dash "—".
> 
> **SUGGESTED ORACLE TEXT:**
> ```
> Overclock twice. (Exile the top three cards of your library. You may play them until end of turn.)
> Cascade Protocol deals 2 damage to any target for each card exiled this way.
> ```
> 
> The keyword capitalization is correct (lowercase "overclock"), and the mechanic usage follows the established pattern.
> - Mechanics: Looking at this design, I found several issues:
> 
> **DESIGN ISSUES:**
> 
> 1. **Keyword nonbo**: The reminder text creates confusion. You wrote "Overclock, then overclock again" followed by reminder text that only explains one instance of overclock. This makes it unclear whether the card exiles 3 or 6 cards total.
> 
> 2. **Fake variability**: The damage clause says "for each card exiled with ~ this way" but overclock always exiles exactly 3 cards (per your design notes). If this does overclock twice, it will always exile 6 cards and always deal 12 damage. The "for each" templating suggests variability that doesn't actually exist.
> 
> 3. **Templating ambiguity**: The current wording doesn't clearly establish whether the damage references cards from both overclock instances or just one. If it's meant to count all exiled cards, the templating should be clearer.
> 
> **SUGGESTIONS:**
> - If this exiles 6 total cards, consider templating like: "Exile the top six cards of your library. You may play them until end of turn. ~ deals 2 damage to any target for each card exiled this way."
> - Or clarify the interaction between multiple overclock instances in the reminder text
> - The core concept (double overclock + damage scaling) is solid and focused, but the execution needs cleaning up
> 
> The design has a clear purpose (high-risk burn spell that scales with card access), but the templating issues need resolution.
> - Balance: **Power Level Analysis: Cascade Protocol**
> 
> **What this card does:**
> - 5 mana sorcery
> - Exiles 6 cards total (3 + 3 from double overclock)
> - Deals 12 damage to any target (2 × 6 exiled cards)
> - Gives temporary access to 6 exiled cards until end of turn
> 
> **Power Level Assessment: FAIL - Significantly Overpowered**
> 
> **Specific Balance Issues:**
> 
> 1. **Damage Rate is Excessive**: 12 damage for 5 mana at sorcery speed is far above the damage curve. Compare to:
>    - **Lightning Bolt**: 3 damage for 1 mana (3:1 ratio)
>    - **Lava Axe**: 5 damage for 5 mana (1:1 ratio)  
>    - **Cascade Protocol**: 12 damage for 5 mana (2.4:1 ratio)
> 
> 2. **Card Advantage is Too High**: Getting 6 cards of selection with 12 damage stapled on creates enormous value. Similar effects:
>    - **Act on Impulse** (3 mana): Exiles 3 cards, playable until end of turn - no damage
>    - **Light Up the Stage** (2 mana): Exiles 2 cards, playable until end of turn - no damage
>    - **Cascade Protocol**: Does both effects at premium efficiency
> 
> 3. **Flexibility Problem**: The "any target" clause makes this both premium removal AND face damage, eliminating tactical decisions.
> 
> **Comparable Cards:**
> - **Crater's Claws** (X=7): 5 mana for 7 damage to any target - significantly weaker
> - **Banefire** (X=4): 5 mana for 4 damage, uncounterable - much weaker damage
> - **Chandra, Torch of Defiance** (4 mana planeswalker): Can exile 1 card OR deal 2 damage per turn - much slower
> 
> **Recommended Fix:**
> Either reduce to 6 total damage (1 per card) OR limit targeting to "target creature or planeswalker" OR increase cost to 6-7 mana. The current version provides rare-level card selection with mythic-level damage at an uncommon-level cost.
> 
> **Verdict: FAIL** - Needs significant power level reduction.
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Incomplete reminder text - should clarify that overclock happens twice",
    "Pronoun reference issue with spell name in damage clause",
    "Character encoding issue in flavor text",
    "Fake variability in damage clause when overclock always exiles exactly 3 cards",
    "Significantly overpowered - 12 damage for 5 mana is far above rate",
    "Card advantage too high when combined with premium damage"
  ],
  "name": "Cascade Protocol",
  "mana_cost": "{3}{R}{R}",
  "type_line": "Sorcery",
  "oracle_text": "Overclock twice. (Exile the top three cards of your library. You may play them until end of turn.)\nCascade Protocol deals 1 damage to target creature or planeswalker for each card exiled this way.",
  "rarity": "rare",
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u2014Final log, Research Station Gamma"
}
```

*Tokens: 2402 in / 354 out — $0.0125*

## C) Revised Card

```json
{
  "name": "Cascade Protocol",
  "mana_cost": "{3}{R}{R}",
  "type_line": "Sorcery",
  "oracle_text": "Overclock twice. (Exile the top three cards of your library. You may play them until end of turn.)\nCascade Protocol deals 1 damage to target creature or planeswalker for each card exiled this way.",
  "rarity": "rare",
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u2014Final log, Research Station Gamma"
}
```

**Changes made:**
- Incomplete reminder text - should clarify that overclock happens twice
- Pronoun reference issue with spell name in damage clause
- Character encoding issue in flavor text
- Fake variability in damage clause when overclock always exiles exactly 3 cards
- Significantly overpowered - 12 damage for 5 mana is far above rate
- Card advantage too high when combined with premium damage

## D) Cost

- API calls: 4
- Input tokens: 4134
- Output tokens: 1610
- Cost: $0.0366