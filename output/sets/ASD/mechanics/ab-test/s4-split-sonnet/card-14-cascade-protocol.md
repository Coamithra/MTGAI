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
> Here are the templating issues found:
> 
> **1. Reminder text placement and duplication**
> When a keyword action appears multiple times on the same card, the reminder text should appear only once, on the first instance. The current text does this correctly in principle, but the reminder text is placed after the second "overclock" rather than after the first. It should read: "Overclock *(reminder text)*, then overclock again."
> 
> **2. Reminder text mismatch / insufficient**
> The reminder text only explains a single overclock instance ("Exile the top three cards..."), but the card performs the action twice, exiling up to six cards total. A reader relying solely on the reminder text would be misled about the card's actual effect. Consider noting this is performed twice, or adjusting the reminder text to "(Exile the top three cards of your library twice. You may play them until end of turn.)" — though this gets awkward. This is a genuine templating tension worth resolving.
> 
> **3. Self-reference tracking — "exiled with ~ this way"**
> MTG templating for tracking cards exiled by a specific spell typically uses "exiled this way" without "with ~." The phrasing "exiled with ~ this way" is redundant. Since this is a sorcery and context is clear, "exiled this way" suffices.
> 
> **4. Encoding artifact in flavor text**
> The flavor text contains garbled characters ("â€"") instead of an em dash (—). This is a character encoding issue.
> 
> **5. Minor: damage clause math clarity**
> The damage clause is functional but confirm intended behavior: two overclock instances exile up to 6 cards, so maximum damage is 12. This seems intentionally powerful at rare, but flag for balance review.

*Tokens: 563 in / 395 out — $0.0076*

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
> ## Design Issues Found
> 
> ### 1. Reminder Text Redundancy / Tracking Confusion
> The card says "Overclock, then overclock again" with a single reminder text block, but Overclock always exiles exactly 3 cards. This card exiles 6 total. The reminder text only describes one instance, which is misleading. Players need to know the total is 6 for the damage calculation. This needs clearer templating, something like: "Overclock twice. (Each instance of overclock exiles the top three cards...)" or just spelling out the full effect.
> 
> ### 2. Damage Variability Is Mostly Fake
> The card deals 2 damage per card exiled "this way." Since Overclock always exiles exactly 3 cards and this does it twice, the damage is almost always exactly **12** to any target. The variability only occurs in edge cases where the library has fewer than 6 cards — a near-irrelevant corner case. This reads as a variable effect but functionally isn't one. It would be cleaner and more honest to just say "deals 12 damage to any target."
> 
> ### 3. Power Level Concern
> 5 mana: draw/play 6 cards + deal 12 damage to any target. Even as a rare, this is extremely pushed. The Overclock risk is real but the damage floor is still enormous.
> 
> ### VERDICT: FAIL

*Tokens: 572 in / 320 out — $0.0065*

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
> ## Cascade Protocol Analysis
> 
> ### What the Card Does
> - 5 mana sorcery
> - Overclock twice = exile top 6 cards, may play them until end of turn
> - Deals 2 damage × 6 cards exiled = **12 damage guaranteed** (assuming no blanks)
> 
> ---
> 
> ### The Core Problem
> 
> The damage clause is not contingent on playing the exiled cards — it triggers **for each card exiled**, not each card played. This means you get **12 guaranteed damage** stapled to a wheel-style effect, regardless of card quality or playability.
> 
> ### Comparisons
> 
> | Card | Cost | Effect |
> |------|------|--------|
> | Fireball (variants) | Variable | ~12 damage costs 13+ mana |
> | Jaya's Immolating Inferno | {X}{R}{R} | 12 damage to three targets costs 12+RR |
> | Temporal Fissure (Storm) | {4}{U} | Considered broken at far less |
> 
> **Chandra's Ignition** at {3}{R}{R} only deals damage equal to a creature's power, requiring a board presence.
> 
> ### Specific Issues
> 
> 1. **The damage floor is too high.** 12 damage split freely to any targets for 5 mana breaks the rate by roughly 2-3× compared to printed burn.
> 2. **Double-Overclock is already a significant effect** worth 5+ mana on its own as a card advantage/velocity engine.
> 3. **Two powerful effects are simply concatenated** with no tension between them — the exiled cards are upside, the burn is guaranteed.
> 
> ### Suggested Fix
> Change to: *"...deals 2 damage for each card **played** from exile this way"* — this creates meaningful tension and caps damage at a realistic 4–8 based on hand quality and mana availability.
> 
> ## Verdict: **FAIL**

*Tokens: 594 in / 446 out — $0.0085*

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
> - Templating: Here are the templating issues found:
> 
> **1. Reminder text placement and duplication**
> When a keyword action appears multiple times on the same card, the reminder text should appear only once, on the first instance. The current text does this correctly in principle, but the reminder text is placed after the second "overclock" rather than after the first. It should read: "Overclock *(reminder text)*, then overclock again."
> 
> **2. Reminder text mismatch / insufficient**
> The reminder text only explains a single overclock instance ("Exile the top three cards..."), but the card performs the action twice, exiling up to six cards total. A reader relying solely on the reminder text would be misled about the card's actual effect. Consider noting this is performed twice, or adjusting the reminder text to "(Exile the top three cards of your library twice. You may play them until end of turn.)" — though this gets awkward. This is a genuine templating tension worth resolving.
> 
> **3. Self-reference tracking — "exiled with ~ this way"**
> MTG templating for tracking cards exiled by a specific spell typically uses "exiled this way" without "with ~." The phrasing "exiled with ~ this way" is redundant. Since this is a sorcery and context is clear, "exiled this way" suffices.
> 
> **4. Encoding artifact in flavor text**
> The flavor text contains garbled characters ("â€"") instead of an em dash (—). This is a character encoding issue.
> 
> **5. Minor: damage clause math clarity**
> The damage clause is functional but confirm intended behavior: two overclock instances exile up to 6 cards, so maximum damage is 12. This seems intentionally powerful at rare, but flag for balance review.
> - Mechanics: ## Design Issues Found
> 
> ### 1. Reminder Text Redundancy / Tracking Confusion
> The card says "Overclock, then overclock again" with a single reminder text block, but Overclock always exiles exactly 3 cards. This card exiles 6 total. The reminder text only describes one instance, which is misleading. Players need to know the total is 6 for the damage calculation. This needs clearer templating, something like: "Overclock twice. (Each instance of overclock exiles the top three cards...)" or just spelling out the full effect.
> 
> ### 2. Damage Variability Is Mostly Fake
> The card deals 2 damage per card exiled "this way." Since Overclock always exiles exactly 3 cards and this does it twice, the damage is almost always exactly **12** to any target. The variability only occurs in edge cases where the library has fewer than 6 cards — a near-irrelevant corner case. This reads as a variable effect but functionally isn't one. It would be cleaner and more honest to just say "deals 12 damage to any target."
> 
> ### 3. Power Level Concern
> 5 mana: draw/play 6 cards + deal 12 damage to any target. Even as a rare, this is extremely pushed. The Overclock risk is real but the damage floor is still enormous.
> 
> ### VERDICT: FAIL
> - Balance: ## Cascade Protocol Analysis
> 
> ### What the Card Does
> - 5 mana sorcery
> - Overclock twice = exile top 6 cards, may play them until end of turn
> - Deals 2 damage × 6 cards exiled = **12 damage guaranteed** (assuming no blanks)
> 
> ---
> 
> ### The Core Problem
> 
> The damage clause is not contingent on playing the exiled cards — it triggers **for each card exiled**, not each card played. This means you get **12 guaranteed damage** stapled to a wheel-style effect, regardless of card quality or playability.
> 
> ### Comparisons
> 
> | Card | Cost | Effect |
> |------|------|--------|
> | Fireball (variants) | Variable | ~12 damage costs 13+ mana |
> | Jaya's Immolating Inferno | {X}{R}{R} | 12 damage to three targets costs 12+RR |
> | Temporal Fissure (Storm) | {4}{U} | Considered broken at far less |
> 
> **Chandra's Ignition** at {3}{R}{R} only deals damage equal to a creature's power, requiring a board presence.
> 
> ### Specific Issues
> 
> 1. **The damage floor is too high.** 12 damage split freely to any targets for 5 mana breaks the rate by roughly 2-3× compared to printed burn.
> 2. **Double-Overclock is already a significant effect** worth 5+ mana on its own as a card advantage/velocity engine.
> 3. **Two powerful effects are simply concatenated** with no tension between them — the exiled cards are upside, the burn is guaranteed.
> 
> ### Suggested Fix
> Change to: *"...deals 2 damage for each card **played** from exile this way"* — this creates meaningful tension and caps damage at a realistic 4–8 based on hand quality and mana availability.
> 
> ## Verdict: **FAIL**
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Reminder text appeared after second overclock instance instead of first",
    "Reminder text only described one overclock instance, misleading players about 6 total cards exiled",
    "Self-reference used redundant 'with ~ this way' phrasing instead of clean 'this way'",
    "Flavor text had garbled encoding artifact instead of em dash (\u2014)",
    "Damage clause triggered on cards exiled (guaranteed 12) rather than cards played (variable, creates tension); fixed per balance review recommendation",
    "Damage was functionally a fixed 12 with fake variability; revised to trigger on cards played from exile for honest and balanced design"
  ],
  "name": "Cascade Protocol",
  "mana_cost": "{3}{R}{R}",
  "type_line": "Sorcery",
  "oracle_text": "Overclock (Exile the top three cards of your library. You may play them until end of turn.), then overclock again.\nCascade Protocol deals 2 damage to any target for each card played from exile this way.",
  "rarity": "rare",
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u2014Final log, Research Station Gamma"
}
```

*Tokens: 2579 in / 420 out — $0.0140*

## C) Revised Card

```json
{
  "name": "Cascade Protocol",
  "mana_cost": "{3}{R}{R}",
  "type_line": "Sorcery",
  "oracle_text": "Overclock (Exile the top three cards of your library. You may play them until end of turn.), then overclock again.\nCascade Protocol deals 2 damage to any target for each card played from exile this way.",
  "rarity": "rare",
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u2014Final log, Research Station Gamma"
}
```

**Changes made:**
- Reminder text appeared after second overclock instance instead of first
- Reminder text only described one overclock instance, misleading players about 6 total cards exiled
- Self-reference used redundant 'with ~ this way' phrasing instead of clean 'this way'
- Flavor text had garbled encoding artifact instead of em dash (—)
- Damage clause triggered on cards exiled (guaranteed 12) rather than cards played (variable, creates tension); fixed per balance review recommendation
- Damage was functionally a fixed 12 with fake variability; revised to trigger on cards played from exile for honest and balanced design

## D) Cost

- API calls: 4
- Input tokens: 4308
- Output tokens: 1581
- Cost: $0.0366