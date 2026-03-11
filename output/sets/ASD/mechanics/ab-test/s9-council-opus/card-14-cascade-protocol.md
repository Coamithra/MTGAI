# Card 14: Cascade Protocol — Strategy: s9-council-opus

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

### Step 1: Reviewer 1 analysis

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
> Card to review:
> Name: Cascade Protocol
> Mana Cost: {3}{R}{R}
> Type: Sorcery
> Rarity: rare
> Oracle Text: Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)
> ~ deals 2 damage to any target for each card exiled with ~ this way.
> Flavor Text: "The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion." â€”Final log, Research Station Gamma
> 
> Critically review this card. List any issues you find with templating, mechanics, balance, design, or color pie. If the card is fine, say "No issues found." Be specific about each issue.

**Response:**
> ## Review of Cascade Protocol
> 
> ### Issues Found:
> 
> **1. Reminder Text Placement Error (Templating)**
> The reminder text only appears after the first "overclock," but the card performs the action twice. The reminder text should either appear after the second instance or not at all (since it's rare). More importantly, the current placement could imply the reminder only defines the first overclock. Standard templating would place it once after all instances or omit it entirely at rare.
> 
> **2. Ambiguous "exiled with ~" Tracking (Templating/Rules)**
> The phrase "each card exiled with ~ this way" is doing heavy lifting. Overclock exiles cards as a keyword action — those cards are exiled by the keyword action, not necessarily "by Cascade Protocol" in the rules sense. This needs careful templating. A cleaner approach might be "for each card exiled this way" or the card could explicitly state "Exile the top six cards of your library. You may play them until end of turn. ~ deals 2 damage to any target for each card exiled this way" — though that changes the mechanic's identity.
> 
> **3. Potential Damage Output is Excessive (Balance)**
> Six cards exiled means 12 damage to any target for 5 mana at sorcery speed, before you even consider playing the exiled cards. That's a near-lethal burn spell that *also* gives you access to up to six cards. Even accounting for the self-mill risk, this is significantly above rate. The combination of a strong card-advantage engine AND a primary win-condition level of damage on one card is problematic. Consider reducing to 1 damage per card exiled, or dealing damage only to creatures.
> 
> **4. Double Overclock Creates Complexity Overload (Design)**
> Overclock is already complexity 3 (uncommon+ only). Doubling it on one card means tracking two separate sets of three exiled cards, potentially across different zones, while also resolving a damage trigger. This pushes toward complexity 4+ territory, which is high even for rare.
> 
> **5. Minor: Name Overlap Concern**
> "Cascade" is a heavily loaded term in Magic (the mechanic Cascade). While not strictly illegal, this naming risks confusion and should be reconsidered.

*Tokens: 509 in / 513 out — $0.0154*

### Step 2: Reviewer 2 analysis

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
> Card to review:
> Name: Cascade Protocol
> Mana Cost: {3}{R}{R}
> Type: Sorcery
> Rarity: rare
> Oracle Text: Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)
> ~ deals 2 damage to any target for each card exiled with ~ this way.
> Flavor Text: "The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion." â€”Final log, Research Station Gamma
> 
> Critically review this card. List any issues you find with templating, mechanics, balance, design, or color pie. If the card is fine, say "No issues found." Be specific about each issue.

**Response:**
> ## Review of Cascade Protocol
> 
> ### Issues Found:
> 
> **1. Templating Issue – Reminder Text Placement**
> The reminder text appears only after the first instance of "overclock," but the card uses the keyword twice. Since both instances are the same keyword action, the reminder text should appear only once, typically after the last usage, or not at all at rare (where reminder text is often omitted). More critically, the reminder text as placed could be misread as applying to the full line rather than just the first overclock.
> 
> **2. Templating Issue – "Exiled with ~" Tracking Ambiguity**
> The phrase "each card exiled with ~ this way" is doing heavy lifting. Overclock as defined is a keyword action that exiles cards as its own effect—the cards are exiled *by overclock*, not technically *by Cascade Protocol*. This creates a tracking/rules ambiguity. Cards like this typically need to be more explicit, e.g., "for each card exiled this way" or the overclock action itself needs to be structured so the card is the source of the exile. Compare how cards reference things put into zones by keyword actions.
> 
> **3. Balance Concern – Damage Ceiling Is Extreme**
> Six cards are exiled total, meaning this deals **12 damage to any target** for 5 mana before you even consider the card advantage from playing those exiled cards. That's a one-card kill in most scenarios, plus potentially playing up to 6 cards. Even at rare, a 5-mana sorcery that is near-guaranteed lethal burn *and* provides massive card advantage is significantly above rate. The damage should likely be 1 per card, or target only creatures, or the effect needs another meaningful restriction.
> 
> **4. Design Concern – Overclock's Risk/Reward Is Negated**
> The design note says overclock is "high risk/reward" because you may lose cards you can't play. But dealing damage based on cards exiled means even unplayable exiled cards contribute to the kill. This undermines the core tension of the mechanic. The card rewards you for the "risk" portion rather than asking you to navigate it.
> 
> **5. Minor Templating – "Overclock, then overclock again"**
> This phrasing is informal for Oracle text. A cleaner template would be "Overclock. Then overclock." (two separate sentences), following precedent like "Scry 2, then scry 2" patterns, though even those are uncommon. Alternatively, consider whether a single "exile the top six" with custom text would be cleaner.
> 
> ### Summary
> The core concept is exciting but the damage scaling makes this far too powerful and it undermines overclock's intended risk profile. Needs significant rebalancing.

*Tokens: 509 in / 621 out — $0.0181*

### Step 3: Reviewer 3 analysis

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
> Card to review:
> Name: Cascade Protocol
> Mana Cost: {3}{R}{R}
> Type: Sorcery
> Rarity: rare
> Oracle Text: Overclock, then overclock again. (Exile the top three cards of your library. You may play them until end of turn.)
> ~ deals 2 damage to any target for each card exiled with ~ this way.
> Flavor Text: "The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion." â€”Final log, Research Station Gamma
> 
> Critically review this card. List any issues you find with templating, mechanics, balance, design, or color pie. If the card is fine, say "No issues found." Be specific about each issue.

**Response:**
> ## Review of Cascade Protocol
> 
> ### Issues Found:
> 
> **1. Templating Issue — Reminder Text Misplaced and Incomplete**
> The reminder text after "Overclock, then overclock again" only explains one instance of overclock. Since the card performs the action twice, the reminder text shouldn't be parenthetically attached to the combined instruction in a way that's ambiguous. More importantly, "overclock again" is somewhat informal. Standard templating would likely read: "Overclock. Then overclock." as two separate sentences, mirroring how Magic handles repeated keyword actions (e.g., "Scry 2, then scry 2" isn't used — they'd either combine or separate cleanly).
> 
> **2. Tracking Issue — "Each card exiled with ~ this way"**
> This creates a meaningful tracking problem. Overclock exiles cards face-up (presumably playable until end of turn), but some of those cards may get *played* between the first and second overclock. The damage clause references cards "exiled with ~ this way," so players need to carefully distinguish which exiled cards came from this spell versus other overclock sources, and track whether any were already played before the damage resolves. Since this is all one spell resolving, the cards can't actually be played mid-resolution — so the count is always 6. This means the damage clause is effectively always "deals 12 damage," making the scaling text misleading flavor.
> 
> **3. Balance Issue — Effectively 12 Damage for 5 Mana**
> If the count is always 6 (since you can't play cards during resolution), this is a 5-mana sorcery that deals 12 damage to any target. That is massively above rate, even at rare. For comparison, \{4}\{R}\{R} Inferno deals 6 damage. This likely needs significant recosting or the damage needs to scale down (1 damage per card, or the damage resolves after the play window).
> 
> **4. Design Concern — Overclock Value is Excessive**
> Six cards of impulse draw plus massive damage on a single card creates a play pattern where this functions as both a finisher and a card advantage engine simultaneously. This likely crowds out interesting decision-making.
> 
> ### Recommendation:
> Restructure so the damage counts cards *still in exile* at end of resolution, or reduce to a single overclock with a damage rider.

*Tokens: 509 in / 540 out — $0.0160*

### Step 4: Synthesizer — consensus revision

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
> --- Reviewer 1 ---
> ## Review of Cascade Protocol
> 
> ### Issues Found:
> 
> **1. Reminder Text Placement Error (Templating)**
> The reminder text only appears after the first "overclock," but the card performs the action twice. The reminder text should either appear after the second instance or not at all (since it's rare). More importantly, the current placement could imply the reminder only defines the first overclock. Standard templating would place it once after all instances or omit it entirely at rare.
> 
> **2. Ambiguous "exiled with ~" Tracking (Templating/Rules)**
> The phrase "each card exiled with ~ this way" is doing heavy lifting. Overclock exiles cards as a keyword action — those cards are exiled by the keyword action, not necessarily "by Cascade Protocol" in the rules sense. This needs careful templating. A cleaner approach might be "for each card exiled this way" or the card could explicitly state "Exile the top six cards of your library. You may play them until end of turn. ~ deals 2 damage to any target for each card exiled this way" — though that changes the mechanic's identity.
> 
> **3. Potential Damage Output is Excessive (Balance)**
> Six cards exiled means 12 damage to any target for 5 mana at sorcery speed, before you even consider playing the exiled cards. That's a near-lethal burn spell that *also* gives you access to up to six cards. Even accounting for the self-mill risk, this is significantly above rate. The combination of a strong card-advantage engine AND a primary win-condition level of damage on one card is problematic. Consider reducing to 1 damage per card exiled, or dealing damage only to creatures.
> 
> **4. Double Overclock Creates Complexity Overload (Design)**
> Overclock is already complexity 3 (uncommon+ only). Doubling it on one card means tracking two separate sets of three exiled cards, potentially across different zones, while also resolving a damage trigger. This pushes toward complexity 4+ territory, which is high even for rare.
> 
> **5. Minor: Name Overlap Concern**
> "Cascade" is a heavily loaded term in Magic (the mechanic Cascade). While not strictly illegal, this naming risks confusion and should be reconsidered.
> 
> --- Reviewer 2 ---
> ## Review of Cascade Protocol
> 
> ### Issues Found:
> 
> **1. Templating Issue – Reminder Text Placement**
> The reminder text appears only after the first instance of "overclock," but the card uses the keyword twice. Since both instances are the same keyword action, the reminder text should appear only once, typically after the last usage, or not at all at rare (where reminder text is often omitted). More critically, the reminder text as placed could be misread as applying to the full line rather than just the first overclock.
> 
> **2. Templating Issue – "Exiled with ~" Tracking Ambiguity**
> The phrase "each card exiled with ~ this way" is doing heavy lifting. Overclock as defined is a keyword action that exiles cards as its own effect—the cards are exiled *by overclock*, not technically *by Cascade Protocol*. This creates a tracking/rules ambiguity. Cards like this typically need to be more explicit, e.g., "for each card exiled this way" or the overclock action itself needs to be structured so the card is the source of the exile. Compare how cards reference things put into zones by keyword actions.
> 
> **3. Balance Concern – Damage Ceiling Is Extreme**
> Six cards are exiled total, meaning this deals **12 damage to any target** for 5 mana before you even consider the card advantage from playing those exiled cards. That's a one-card kill in most scenarios, plus potentially playing up to 6 cards. Even at rare, a 5-mana sorcery that is near-guaranteed lethal burn *and* provides massive card advantage is significantly above rate. The damage should likely be 1 per card, or target only creatures, or the effect needs another meaningful restriction.
> 
> **4. Design Concern – Overclock's Risk/Reward Is Negated**
> The design note says overclock is "high risk/reward" because you may lose cards you can't play. But dealing damage based on cards exiled means even unplayable exiled cards contribute to the kill. This undermines the core tension of the mechanic. The card rewards you for the "risk" portion rather than asking you to navigate it.
> 
> **5. Minor Templating – "Overclock, then overclock again"**
> This phrasing is informal for Oracle text. A cleaner template would be "Overclock. Then overclock." (two separate sentences), following precedent like "Scry 2, then scry 2" patterns, though even those are uncommon. Alternatively, consider whether a single "exile the top six" with custom text would be cleaner.
> 
> ### Summary
> The core concept is exciting but the damage scaling makes this far too powerful and it undermines overclock's intended risk profile. Needs significant rebalancing.
> 
> --- Reviewer 3 ---
> ## Review of Cascade Protocol
> 
> ### Issues Found:
> 
> **1. Templating Issue — Reminder Text Misplaced and Incomplete**
> The reminder text after "Overclock, then overclock again" only explains one instance of overclock. Since the card performs the action twice, the reminder text shouldn't be parenthetically attached to the combined instruction in a way that's ambiguous. More importantly, "overclock again" is somewhat informal. Standard templating would likely read: "Overclock. Then overclock." as two separate sentences, mirroring how Magic handles repeated keyword actions (e.g., "Scry 2, then scry 2" isn't used — they'd either combine or separate cleanly).
> 
> **2. Tracking Issue — "Each card exiled with ~ this way"**
> This creates a meaningful tracking problem. Overclock exiles cards face-up (presumably playable until end of turn), but some of those cards may get *played* between the first and second overclock. The damage clause references cards "exiled with ~ this way," so players need to carefully distinguish which exiled cards came from this spell versus other overclock sources, and track whether any were already played before the damage resolves. Since this is all one spell resolving, the cards can't actually be played mid-resolution — so the count is always 6. This means the damage clause is effectively always "deals 12 damage," making the scaling text misleading flavor.
> 
> **3. Balance Issue — Effectively 12 Damage for 5 Mana**
> If the count is always 6 (since you can't play cards during resolution), this is a 5-mana sorcery that deals 12 damage to any target. That is massively above rate, even at rare. For comparison, \{4}\{R}\{R} Inferno deals 6 damage. This likely needs significant recosting or the damage needs to scale down (1 damage per card, or the damage resolves after the play window).
> 
> **4. Design Concern — Overclock Value is Excessive**
> Six cards of impulse draw plus massive damage on a single card creates a play pattern where this functions as both a finisher and a card advantage engine simultaneously. This likely crowds out interesting decision-making.
> 
> ### Recommendation:
> Restructure so the damage counts cards *still in exile* at end of resolution, or reduce to a single overclock with a damage rider.
> 
> Based on the consensus of these 3 reviews (issues raised by at least 2 reviewers), produce a revised version of the card. If no issues have consensus, return the card unchanged with verdict OK. Only fix issues that at least 2 reviewers agree on.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Reminder text placement is ambiguous/misplaced \u2014 all 3 reviewers agree it's poorly positioned after the first overclock and could cause confusion. (3/3 consensus)",
    "\"Exiled with ~ this way\" creates tracking/rules ambiguity since overclock is a keyword action that does the exiling, not the card itself \u2014 all 3 reviewers flag this. (3/3 consensus)",
    "Damage output is excessive \u2014 12 damage to any target for 5 mana plus massive card advantage is far above rate, even at rare. All 3 reviewers agree. (3/3 consensus)",
    "\"Overclock, then overclock again\" is informal templating \u2014 2 of 3 reviewers suggest \"Overclock. Then overclock.\" as cleaner Oracle text. (2/3 consensus)",
    "Double overclock undermines the risk/reward tension of the mechanic \u2014 exiled cards contribute to damage whether playable or not. 2 of 3 reviewers flag this design concern. (2/3 consensus)"
  ],
  "name": "Cascade Protocol",
  "mana_cost": "{3}{R}{R}",
  "type_line": "Sorcery",
  "oracle_text": "Overclock. Then overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nThen ~ deals 1 damage to any target for each card exiled this way that you didn't play.",
  "rarity": "rare",
  "power": null,
  "toughness": null,
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u2014Final log, Research Station Gamma"
}
```

*Tokens: 3145 in / 541 out — $0.0293*

## C) Revised Card

```json
{
  "name": "Cascade Protocol",
  "mana_cost": "{3}{R}{R}",
  "type_line": "Sorcery",
  "oracle_text": "Overclock. Then overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nThen ~ deals 1 damage to any target for each card exiled this way that you didn't play.",
  "rarity": "rare",
  "flavor_text": "\"The cascade effect exceeded all theoretical parameters. Fortunately, so did the explosion.\" \u2014Final log, Research Station Gamma"
}
```

**Changes made:**
- Reminder text placement is ambiguous/misplaced — all 3 reviewers agree it's poorly positioned after the first overclock and could cause confusion. (3/3 consensus)
- "Exiled with ~ this way" creates tracking/rules ambiguity since overclock is a keyword action that does the exiling, not the card itself — all 3 reviewers flag this. (3/3 consensus)
- Damage output is excessive — 12 damage to any target for 5 mana plus massive card advantage is far above rate, even at rare. All 3 reviewers agree. (3/3 consensus)
- "Overclock, then overclock again" is informal templating — 2 of 3 reviewers suggest "Overclock. Then overclock." as cleaner Oracle text. (2/3 consensus)
- Double overclock undermines the risk/reward tension of the mechanic — exiled cards contribute to damage whether playable or not. 2 of 3 reviewers flag this design concern. (2/3 consensus)

## D) Cost

- API calls: 4
- Input tokens: 4672
- Output tokens: 2215
- Cost: $0.0787