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
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u00e2\u20ac\u201dFinal log, Research Station Gamma"
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
> Flavor Text: "The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion." â€”Final log, Research Station Gamma
> 
> Check:
> - Is the oracle text valid MTG rules text using current templating conventions?
> - Does every custom mechanic (salvage, malfunction, overclock) include reminder text in parentheses on its first use?
> - Is keyword capitalization consistent?
> - Are ability words, keyword abilities, and keyword actions used correctly?
> 
> List any templating issues found, or say "PASS" if the templating is correct.

**Response:**
> Here are the templating issues I found:
> 
> ---
> 
> **1. Reminder text placement and scope for double overclock.**
> 
> The reminder text is placed after the first sentence, but the card performs overclock *twice*. As written, the reminder text parenthetical only follows the first use and could be read as applying only to that instance. More importantly, the reminder text says "Exile the top three cards," but the card exiles six total. The reminder text should appear after the full instruction, or be adjusted so it doesn't mislead.
> 
> **Suggested fix:**
> > Overclock, then overclock again. *(Each time, exile the top three cards of your library. You may play them until end of turn.)*
> 
> This clarifies that the reminder text describes each individual overclock instance.
> 
> ---
> 
> **2. "each card exiled with ~ this way" is ambiguous and slightly off-template.**
> 
> "Exiled with ~" typically refers to cards an ability explicitly exiles by name. Here, overclock is the keyword action doing the exiling, not the card by name. Additionally, "this way" is redundant alongside "with ~." The cleaner template references the total count from the overclock actions.
> 
> **Suggested fix:**
> > {CARDNAME} deals 2 damage to any target for each card exiled this way.
> 
> This is sufficient, since "this way" covers both overclock instances within this spell's resolution.
> 
> ---
> 
> **3. Flavor text encoding issue.**
> 
> The dash before "Final log" shows as `â€"` — this is a UTF-8 encoding error for an em dash. It should be `—`.
> 
> ---
> 
> **4. Minor: Damage targeting template.**
> 
> Current standard templating for "any target" damage tied to a variable amount would typically choose the target before determining the amount. Since this is a sorcery and the count is determined on resolution, you may want to confirm the target is chosen on cast (as normal for sorceries), with the damage amount determined on resolution. The current template handles this correctly by rules, but it's worth noting.
> 
> ---
> 
> All other aspects (keyword action usage for overclock, capitalization, mana cost formatting) look correct.

*Tokens: 562 in / 485 out — $0.0149*

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
> Flavor Text: "The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion." â€”Final log, Research Station Gamma
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
> I need to analyze this card carefully against the checklist and general design principles.
> 
> **Overclock twice:** This exiles 3 cards, then exiles 3 more cards, for 6 total cards exiled. The damage clause says "for each card exiled with ~ this way," which would always be 6 (barring an empty library edge case). That means this deals 12 damage to any target for 5 mana.
> 
> **Issue 1: Variability is fake.** The damage is "for each card exiled this way," but since Overclock always exiles exactly 3 (per the design note), and you do it twice, the number is functionally always 6. This means the card always deals 12 damage. The variable wording creates an illusion of variance where there is none in normal gameplay. It should just say "deals 12 damage" if that's the intent—or if variance is desired, the mechanic needs to actually produce it.
> 
> **Issue 2: Rate is wildly off.** 12 damage to any target for {3}{R}{R} is far above rate. This is a one-card kill condition that also gives you 6 cards of impulse draw. Compare to \[\[Fireball\]\] needing {12}{R} for 12 damage to one target with no card advantage. Even halved to 6 damage, the impulse draw of 6 cards stapled on makes this absurd.
> 
> **Issue 3: Kitchen sink concern.** Double Overclock (massive card advantage/selection engine) + scaling burn damage are two powerful, somewhat unrelated effects. The flavor connection ("cascade" = more overclock = more damage) is there, but mechanically the impulse draw and the burn don't serve the same gameplan cleanly. You want to play the exiled cards, but you also just won because you dealt 12.
> 
> **Issue 4: The Overclock reminder text is only on the first instance.** Minor templating note—the second overclock lacks its own reminder text, which is fine, but the single reminder text might confuse readers into thinking both overclocks together exile only 3 total.
> 
> **Summary:** The core issues are fake variability and a massively above-rate power level. NOT PASS.

*Tokens: 571 in / 511 out — $0.0156*

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
> Flavor Text: "The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion." â€”Final log, Research Station Gamma
> 
> Check:
> - Is the power level appropriate for the mana cost AND rarity?
> - Compare to 2-3 well-known printed MTG cards at similar mana cost and rarity.
> - Note: malfunction cards are intentionally above-rate — the delayed entry IS the drawback. Do not flag these for being above-rate.
> - Note: mythic rares are allowed to be powerful build-arounds. Do not nerf mythics to rare power level.
> 
> State whether the balance is PASS, or describe the specific balance issue with card comparisons.

**Response:**
> # Balance Review: Cascade Protocol
> 
> ## Card Analysis
> 
> **Cascade Protocol** — {3}{R}{R} Sorcery (Rare)
> 
> - Overclock twice → exile 6 cards total
> - Deal 2 damage per card exiled this way → **12 damage** to any target
> - You may play the 6 exiled cards until end of turn
> 
> ## Power Level Assessment
> 
> This card is doing two extremely powerful things simultaneously:
> 
> 1. **12 damage to any target** for 5 mana — this is a massive burn spell that can one-shot from over half a starting life total.
> 2. **Exile 6 cards and play them until end of turn** — this is a massive card advantage engine stapled on top.
> 
> Either half alone would be a strong rare. Together, this is unreasonable.
> 
> ## Comparisons
> 
> | Card | Cost | Effect |
> |------|------|--------|
> | **Crackle with Power** | {X}{X}{X}{R}{R} | Needs X=4 (10 mana) for 10 damage to one target, no card advantage |
> | **Burn Down the House** | {3}{R}{R} | 5 damage to each creature/planeswalker OR 3 tokens — no face damage, no cards |
> | **Apex of Power** | {7}{R}{R}{R} | Exile 10, play until end of turn, add 10 mana — 10 mana mythic for the impulse-draw half alone |
> 
> ## Core Problem
> 
> At 5 mana, this is essentially **"deal 12 to any target and draw ~3-4 playable cards."** The damage alone is above rate (compare to any 5-mana burn spell in history), and the impulse draw is a free Apex-of-Power-lite bolted on. This ends the game on the spot in virtually every scenario — either the 12 face damage kills them, or the 6 exiled cards bury them in advantage.
> 
> ## Suggested Fix
> 
> Either reduce the damage (1 per card = 6 damage) **or** reduce the overclock count to one (3 exiled → 6 damage), not both.
> 
> **FAIL — significantly above rate. The combination of lethal-range burn + massive card advantage at 5 mana has no precedent.**

*Tokens: 593 in / 543 out — $0.0165*

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
> Flavor Text: "The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion." â€”Final log, Research Station Gamma
> 
> Issues found:
> - Templating: Here are the templating issues I found:
> 
> ---
> 
> **1. Reminder text placement and scope for double overclock.**
> 
> The reminder text is placed after the first sentence, but the card performs overclock *twice*. As written, the reminder text parenthetical only follows the first use and could be read as applying only to that instance. More importantly, the reminder text says "Exile the top three cards," but the card exiles six total. The reminder text should appear after the full instruction, or be adjusted so it doesn't mislead.
> 
> **Suggested fix:**
> > Overclock, then overclock again. *(Each time, exile the top three cards of your library. You may play them until end of turn.)*
> 
> This clarifies that the reminder text describes each individual overclock instance.
> 
> ---
> 
> **2. "each card exiled with ~ this way" is ambiguous and slightly off-template.**
> 
> "Exiled with ~" typically refers to cards an ability explicitly exiles by name. Here, overclock is the keyword action doing the exiling, not the card by name. Additionally, "this way" is redundant alongside "with ~." The cleaner template references the total count from the overclock actions.
> 
> **Suggested fix:**
> > {CARDNAME} deals 2 damage to any target for each card exiled this way.
> 
> This is sufficient, since "this way" covers both overclock instances within this spell's resolution.
> 
> ---
> 
> **3. Flavor text encoding issue.**
> 
> The dash before "Final log" shows as `â€"` — this is a UTF-8 encoding error for an em dash. It should be `—`.
> 
> ---
> 
> **4. Minor: Damage targeting template.**
> 
> Current standard templating for "any target" damage tied to a variable amount would typically choose the target before determining the amount. Since this is a sorcery and the count is determined on resolution, you may want to confirm the target is chosen on cast (as normal for sorceries), with the damage amount determined on resolution. The current template handles this correctly by rules, but it's worth noting.
> 
> ---
> 
> All other aspects (keyword action usage for overclock, capitalization, mana cost formatting) look correct.
> - Mechanics: I need to analyze this card carefully against the checklist and general design principles.
> 
> **Overclock twice:** This exiles 3 cards, then exiles 3 more cards, for 6 total cards exiled. The damage clause says "for each card exiled with ~ this way," which would always be 6 (barring an empty library edge case). That means this deals 12 damage to any target for 5 mana.
> 
> **Issue 1: Variability is fake.** The damage is "for each card exiled this way," but since Overclock always exiles exactly 3 (per the design note), and you do it twice, the number is functionally always 6. This means the card always deals 12 damage. The variable wording creates an illusion of variance where there is none in normal gameplay. It should just say "deals 12 damage" if that's the intent—or if variance is desired, the mechanic needs to actually produce it.
> 
> **Issue 2: Rate is wildly off.** 12 damage to any target for {3}{R}{R} is far above rate. This is a one-card kill condition that also gives you 6 cards of impulse draw. Compare to \[\[Fireball\]\] needing {12}{R} for 12 damage to one target with no card advantage. Even halved to 6 damage, the impulse draw of 6 cards stapled on makes this absurd.
> 
> **Issue 3: Kitchen sink concern.** Double Overclock (massive card advantage/selection engine) + scaling burn damage are two powerful, somewhat unrelated effects. The flavor connection ("cascade" = more overclock = more damage) is there, but mechanically the impulse draw and the burn don't serve the same gameplan cleanly. You want to play the exiled cards, but you also just won because you dealt 12.
> 
> **Issue 4: The Overclock reminder text is only on the first instance.** Minor templating note—the second overclock lacks its own reminder text, which is fine, but the single reminder text might confuse readers into thinking both overclocks together exile only 3 total.
> 
> **Summary:** The core issues are fake variability and a massively above-rate power level. NOT PASS.
> - Balance: # Balance Review: Cascade Protocol
> 
> ## Card Analysis
> 
> **Cascade Protocol** — {3}{R}{R} Sorcery (Rare)
> 
> - Overclock twice → exile 6 cards total
> - Deal 2 damage per card exiled this way → **12 damage** to any target
> - You may play the 6 exiled cards until end of turn
> 
> ## Power Level Assessment
> 
> This card is doing two extremely powerful things simultaneously:
> 
> 1. **12 damage to any target** for 5 mana — this is a massive burn spell that can one-shot from over half a starting life total.
> 2. **Exile 6 cards and play them until end of turn** — this is a massive card advantage engine stapled on top.
> 
> Either half alone would be a strong rare. Together, this is unreasonable.
> 
> ## Comparisons
> 
> | Card | Cost | Effect |
> |------|------|--------|
> | **Crackle with Power** | {X}{X}{X}{R}{R} | Needs X=4 (10 mana) for 10 damage to one target, no card advantage |
> | **Burn Down the House** | {3}{R}{R} | 5 damage to each creature/planeswalker OR 3 tokens — no face damage, no cards |
> | **Apex of Power** | {7}{R}{R}{R} | Exile 10, play until end of turn, add 10 mana — 10 mana mythic for the impulse-draw half alone |
> 
> ## Core Problem
> 
> At 5 mana, this is essentially **"deal 12 to any target and draw ~3-4 playable cards."** The damage alone is above rate (compare to any 5-mana burn spell in history), and the impulse draw is a free Apex-of-Power-lite bolted on. This ends the game on the spot in virtually every scenario — either the 12 face damage kills them, or the 6 exiled cards bury them in advantage.
> 
> ## Suggested Fix
> 
> Either reduce the damage (1 per card = 6 damage) **or** reduce the overclock count to one (3 exiled → 6 damage), not both.
> 
> **FAIL — significantly above rate. The combination of lethal-range burn + massive card advantage at 5 mana has no precedent.**
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Fake variability: Overclock always exiles exactly 3, so double overclock always exiles 6, meaning the 'for each card exiled' wording creates illusory variance \u2014 always deals 12 damage.",
    "Massively above rate: 12 damage to any target + impulse draw 6 cards for 5 mana is unprecedented and game-ending with no counterplay.",
    "Kitchen sink design: Lethal burn + massive card advantage serve different gameplans; the burn makes the impulse draw irrelevant in most games.",
    "Reminder text placement misleading for double overclock \u2014 could imply only 3 total cards exiled.",
    "Templating: 'exiled with ~' is off-template when a keyword action does the exiling.",
    "Flavor text encoding error: em dash rendered as garbled UTF-8 characters."
  ],
  "name": "Cascade Protocol",
  "mana_cost": "{3}{R}{R}",
  "type_line": "Sorcery",
  "rarity": "rare",
  "oracle_text": "Overclock, then overclock again. (Each time, exile the top three cards of your library. You may play them until end of turn.)\n{CARDNAME} deals 1 damage to any target for each card exiled this way.",
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u2014Final log, Research Station Gamma",
  "power": null,
  "toughness": null
}
```

*Tokens: 2956 in / 495 out — $0.0272*

## C) Revised Card

```json
{
  "name": "Cascade Protocol",
  "mana_cost": "{3}{R}{R}",
  "type_line": "Sorcery",
  "oracle_text": "Overclock, then overclock again. (Each time, exile the top three cards of your library. You may play them until end of turn.)\n{CARDNAME} deals 1 damage to any target for each card exiled this way.",
  "rarity": "rare",
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u2014Final log, Research Station Gamma"
}
```

**Changes made:**
- Fake variability: Overclock always exiles exactly 3, so double overclock always exiles 6, meaning the 'for each card exiled' wording creates illusory variance — always deals 12 damage.
- Massively above rate: 12 damage to any target + impulse draw 6 cards for 5 mana is unprecedented and game-ending with no counterplay.
- Kitchen sink design: Lethal burn + massive card advantage serve different gameplans; the burn makes the impulse draw irrelevant in most games.
- Reminder text placement misleading for double overclock — could imply only 3 total cards exiled.
- Templating: 'exiled with ~' is off-template when a keyword action does the exiling.
- Flavor text encoding error: em dash rendered as garbled UTF-8 characters.

## D) Cost

- API calls: 4
- Input tokens: 4682
- Output tokens: 2034
- Cost: $0.0743