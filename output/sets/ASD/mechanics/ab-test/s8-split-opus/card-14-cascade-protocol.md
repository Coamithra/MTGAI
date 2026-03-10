# Card 14: Cascade Protocol — Strategy: s8-split-opus

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
> Looking at the oracle text for Cascade Protocol:
> 
> **Templating Issues Found:**
> 
> 1. **Missing reminder text**: The first instance of "overclock" should include its reminder text in parentheses. The second instance can omit it, but the first must have it for clarity.
> 
> 2. **Incorrect reference to "exiled with ~"**: The way this is templated suggests that Cascade Protocol itself is doing the exiling, but overclock is a keyword action that exiles cards as part of its own effect. The damage ability should reference "cards exiled this way" or "cards you exiled this turn" instead.
> 
> 3. **Ambiguous damage trigger**: The current wording could be interpreted as dealing 2 damage for each card (potentially 6 damage total if both overclocks exile 3 cards each), but it's unclear if this is the intent or if it should count only unique cards exiled.
> 
> **Corrected oracle text should be:**
> ```
> Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)
> Cascade Protocol deals 2 damage to any target for each card exiled this turn.
> ```
> 
> Or if the intent is to count only cards exiled by overclock this turn:
> ```
> Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)
> Cascade Protocol deals 2 damage to any target for each card you exiled with overclock this turn.
> ```

*Tokens: 564 in / 343 out — $0.0342*

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
> Looking at this card's design:
> 
> **Issues Found:**
> 
> 1. **Variable that's always the same value**: The card says "deals 2 damage to any target for each card exiled with ~ this way" but Overclock always exiles exactly 3 cards according to the mechanic notes. This means the damage is always 12 (2 × 6 cards total). This fake variability should either be removed (just say "deals 12 damage") or the mechanic should be modified to allow variable exile counts.
> 
> 2. **Unclear damage targeting**: The current wording "deals 2 damage to any target for each card exiled" is ambiguous. Does it deal all the damage to one target, or can you divide it among multiple targets? The wording needs clarification.
> 
> 3. **Power level concern**: 12 damage for 5 mana is extremely aggressive, even at rare. While Overclock has the downside of potentially exiling important cards, getting to play 6 cards until end of turn is already significant value. The damage on top makes this potentially too swingy.
> 
> **Recommendations:**
> - Either make the damage fixed ("~ deals 12 damage to any target") or rework how Overclock functions
> - Clarify if damage can be divided or must target a single entity
> - Consider reducing the damage multiplier or total damage output for better balance
> 
> The card does have a focused purpose (aggressive card advantage + reach) and doesn't suffer from kitchen sink design, but the pseudo-variable damage is a significant design flaw.

*Tokens: 573 in / 344 out — $0.0344*

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
> Looking at this card's power level:
> 
> **Cascade Protocol** - {3}{R}{R} Sorcery (Rare)
> 
> This exiles 6 cards total and deals 12 damage to any target, with the potential to play those 6 exiled cards this turn.
> 
> **Comparisons:**
> - **Banefire** ({X}{R}) - Deals X damage, uncounterable at X≥5. For 5 mana gets 4 damage.
> - **Burn from Within** ({X}{R}) - Deals X damage with exile clause. For 5 mana gets 4 damage.
> - **Crackle with Power** ({X}{X}{X}{R}{R}) - For 5 mana deals 5 damage to each of up to X targets (X=1).
> 
> **Analysis:**
> This card is drastically overpowered. For 5 mana at sorcery speed:
> - 12 damage to any target is triple the rate of comparable damage spells
> - Can potentially play 6 additional cards this turn (worth ~18+ mana of value)
> - The "downside" of exiling cards is actually an upside with overclock
> 
> Even if this dealt 2 damage per overclock activation (6 total) instead of per card exiled, it would still be pushing the power level. The current version essentially reads "5 mana: Deal 12 damage, draw and play up to 6 cards this turn."
> 
> **Balance verdict: FAIL**
> 
> The damage should be reduced to either:
> - 2 damage per overclock activation (6 total), or
> - 1 damage per card exiled (6 total)
> 
> Even with these changes, getting to potentially play 6 exiled cards for 5 mana is extremely powerful and might still be too strong at rare.

*Tokens: 595 in / 423 out — $0.0406*

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
> - Templating: Looking at the oracle text for Cascade Protocol:
> 
> **Templating Issues Found:**
> 
> 1. **Missing reminder text**: The first instance of "overclock" should include its reminder text in parentheses. The second instance can omit it, but the first must have it for clarity.
> 
> 2. **Incorrect reference to "exiled with ~"**: The way this is templated suggests that Cascade Protocol itself is doing the exiling, but overclock is a keyword action that exiles cards as part of its own effect. The damage ability should reference "cards exiled this way" or "cards you exiled this turn" instead.
> 
> 3. **Ambiguous damage trigger**: The current wording could be interpreted as dealing 2 damage for each card (potentially 6 damage total if both overclocks exile 3 cards each), but it's unclear if this is the intent or if it should count only unique cards exiled.
> 
> **Corrected oracle text should be:**
> ```
> Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)
> Cascade Protocol deals 2 damage to any target for each card exiled this turn.
> ```
> 
> Or if the intent is to count only cards exiled by overclock this turn:
> ```
> Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)
> Cascade Protocol deals 2 damage to any target for each card you exiled with overclock this turn.
> ```
> - Mechanics: Looking at this card's design:
> 
> **Issues Found:**
> 
> 1. **Variable that's always the same value**: The card says "deals 2 damage to any target for each card exiled with ~ this way" but Overclock always exiles exactly 3 cards according to the mechanic notes. This means the damage is always 12 (2 × 6 cards total). This fake variability should either be removed (just say "deals 12 damage") or the mechanic should be modified to allow variable exile counts.
> 
> 2. **Unclear damage targeting**: The current wording "deals 2 damage to any target for each card exiled" is ambiguous. Does it deal all the damage to one target, or can you divide it among multiple targets? The wording needs clarification.
> 
> 3. **Power level concern**: 12 damage for 5 mana is extremely aggressive, even at rare. While Overclock has the downside of potentially exiling important cards, getting to play 6 cards until end of turn is already significant value. The damage on top makes this potentially too swingy.
> 
> **Recommendations:**
> - Either make the damage fixed ("~ deals 12 damage to any target") or rework how Overclock functions
> - Clarify if damage can be divided or must target a single entity
> - Consider reducing the damage multiplier or total damage output for better balance
> 
> The card does have a focused purpose (aggressive card advantage + reach) and doesn't suffer from kitchen sink design, but the pseudo-variable damage is a significant design flaw.
> - Balance: Looking at this card's power level:
> 
> **Cascade Protocol** - {3}{R}{R} Sorcery (Rare)
> 
> This exiles 6 cards total and deals 12 damage to any target, with the potential to play those 6 exiled cards this turn.
> 
> **Comparisons:**
> - **Banefire** ({X}{R}) - Deals X damage, uncounterable at X≥5. For 5 mana gets 4 damage.
> - **Burn from Within** ({X}{R}) - Deals X damage with exile clause. For 5 mana gets 4 damage.
> - **Crackle with Power** ({X}{X}{X}{R}{R}) - For 5 mana deals 5 damage to each of up to X targets (X=1).
> 
> **Analysis:**
> This card is drastically overpowered. For 5 mana at sorcery speed:
> - 12 damage to any target is triple the rate of comparable damage spells
> - Can potentially play 6 additional cards this turn (worth ~18+ mana of value)
> - The "downside" of exiling cards is actually an upside with overclock
> 
> Even if this dealt 2 damage per overclock activation (6 total) instead of per card exiled, it would still be pushing the power level. The current version essentially reads "5 mana: Deal 12 damage, draw and play up to 6 cards this turn."
> 
> **Balance verdict: FAIL**
> 
> The damage should be reduced to either:
> - 2 damage per overclock activation (6 total), or
> - 1 damage per card exiled (6 total)
> 
> Even with these changes, getting to potentially play 6 exiled cards for 5 mana is extremely powerful and might still be too strong at rare.
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Missing reminder text on first overclock instance",
    "Incorrect self-reference with ~ in damage clause",
    "Pseudo-variable damage that's always 12",
    "Ambiguous damage targeting",
    "Severely overpowered - 12 damage for 5 mana plus playing 6 cards"
  ],
  "name": "Cascade Protocol",
  "mana_cost": "{3}{R}{R}",
  "type_line": "Sorcery",
  "oracle_text": "Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)\nCascade Protocol deals 6 damage to any target.",
  "rarity": "rare",
  "power": null,
  "toughness": null,
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u2014Final log, Research Station Gamma"
}
```

*Tokens: 2256 in / 358 out — $0.0607*

## C) Revised Card

```json
{
  "name": "Cascade Protocol",
  "mana_cost": "{3}{R}{R}",
  "type_line": "Sorcery",
  "oracle_text": "Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)\nCascade Protocol deals 6 damage to any target.",
  "rarity": "rare",
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u2014Final log, Research Station Gamma"
}
```

**Changes made:**
- Missing reminder text on first overclock instance
- Incorrect self-reference with ~ in damage clause
- Pseudo-variable damage that's always 12
- Ambiguous damage targeting
- Severely overpowered - 12 damage for 5 mana plus playing 6 cards

## D) Cost

- API calls: 4
- Input tokens: 3988
- Output tokens: 1468
- Cost: $0.1699