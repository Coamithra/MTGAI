# Card 5: Subsurface Expedition Leader — Strategy: s9-council-opus

## A) Original Card

```json
{
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{2}{W}{W}",
  "cmc": 4,
  "colors": [
    "W"
  ],
  "type_line": "Creature \u00e2\u20ac\u201d Human Soldier",
  "oracle_text": "When ~ enters, salvage 6.\n{2}{W}, {T}: Salvage 3. Activate only as a sorcery.",
  "power": "3",
  "toughness": "4",
  "rarity": "rare",
  "keywords": [
    "Salvage"
  ],
  "flavor_text": "\"Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.\""
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
> Name: Subsurface Expedition Leader
> Mana Cost: {2}{W}{W}
> Type: Creature â€” Human Soldier
> Rarity: rare
> Oracle Text: When ~ enters, salvage 6.
> {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> P/T: 3/4
> Flavor Text: "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
> 
> Critically review this card. List any issues you find with templating, mechanics, balance, design, or color pie. If the card is fine, say "No issues found." Be specific about each issue.

**Response:**
> ## Review of Subsurface Expedition Leader
> 
> ### Issues Found:
> 
> **1. Balance Concern — ETB Salvage 6 is Very Efficient at This Cost**
> A 3/4 for {2}{W}{W} is already a reasonable rate. Stapling salvage 6 (a rare-tier scaling value) as an ETB means this card generates significant card advantage the moment it resolves, before the opponent can interact with the creature. Combined with a repeatable salvage 3 activation, this card provides an enormous amount of card selection/advantage in artifact-heavy decks. The total package is pushed — consider whether the ETB should be salvage 4–5 instead, or whether the body should be smaller (e.g., 2/3).
> 
> **2. Repeatable Salvage with No Meaningful Gate**
> The activated ability costs {2}{W} and a tap, sorcery-speed only. While the sorcery restriction is good, on a 3/4 body that already replaced itself on entry, the repeated activation has relatively low opportunity cost in slower matchups. This card threatens to dominate limited games where it survives, functioning as a card advantage engine with a solid body. The sorcery restriction helps but may not be sufficient.
> 
> **3. Flavor Text — Tonal Mismatch with Rarity/Role**
> The flavor text leans into comedic/self-deprecating humor ("remarkably high turnover"), which slightly undercuts the card's mechanical identity as a powerful rare expedition leader. This is a minor concern and somewhat subjective, but the tone feels more common/uncommon.
> 
> ### What's Done Well:
> - Templating is clean and correct.
> - Sorcery-speed restriction on the activated ability is a smart design choice.
> - Salvage scaling (6 on ETB, 3 on activation) correctly maps to rare guidelines.
> - Color pie alignment is fine — white gets salvage per the mechanic definition.
> 
> ### Summary:
> The card is mechanically sound but likely **overtuned** for a 4-mana rare. I'd recommend either reducing the ETB to salvage 4–5, or shrinking the body to 2/3.

*Tokens: 504 in / 497 out — $0.0149*

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
> Name: Subsurface Expedition Leader
> Mana Cost: {2}{W}{W}
> Type: Creature â€” Human Soldier
> Rarity: rare
> Oracle Text: When ~ enters, salvage 6.
> {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> P/T: 3/4
> Flavor Text: "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
> 
> Critically review this card. List any issues you find with templating, mechanics, balance, design, or color pie. If the card is fine, say "No issues found." Be specific about each issue.

**Response:**
> ## Review: Subsurface Expedition Leader
> 
> ### Issues Found:
> 
> **1. Balance — ETB Salvage 6 is extremely generous at rare alongside a repeated salvage ability.**
> Salvage 6 on a 3/4 body for 4 mana is already a strong rare-level effect by the set's own scaling guidelines (6+ is rare/mythic territory). Stapling a repeatable Salvage 3 activation onto the same card creates a card that dominates any artifact-synergy limited deck. The ETB alone would make this a strong card; the activated ability pushes it into bomb territory with minimal counterplay since the value is front-loaded. Consider either reducing the ETB to Salvage 4-5, or removing the activated ability in favor of just the ETB.
> 
> **2. Design — Redundant play pattern reduces decision-making.**
> Both abilities do the same thing at different scales. There's no tension or interesting choice here — you always want to use both. Stronger rare designs typically create decisions. Consider differentiating the two abilities (e.g., the activated ability could put the artifact directly onto the battlefield, or have a different conditional trigger) to create more interesting gameplay.
> 
> **3. Minor Templating — Activate restriction wording.**
> "Activate only as a sorcery" is correct modern templating. No issue here.
> 
> **4. Color Pie — Clean.**
> White has access to Salvage per the set mechanics, and a 3/4 body with tap abilities is well within white's creature design space.
> 
> **5. Flavor Text — Good.**
> The dark humor fits the set's tone well and adds personality without conflicting with the mechanical identity.
> 
> ### Summary:
> The card is mechanically functional and correctly templated, but is overloaded on raw value for a 4-mana rare. The primary concern is power level in Limited and the lack of meaningful design tension between the two abilities.

*Tokens: 504 in / 432 out — $0.0133*

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
> Name: Subsurface Expedition Leader
> Mana Cost: {2}{W}{W}
> Type: Creature â€” Human Soldier
> Rarity: rare
> Oracle Text: When ~ enters, salvage 6.
> {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> P/T: 3/4
> Flavor Text: "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
> 
> Critically review this card. List any issues you find with templating, mechanics, balance, design, or color pie. If the card is fine, say "No issues found." Be specific about each issue.

**Response:**
> ## Review of Subsurface Expedition Leader
> 
> ### Issues Found:
> 
> **1. Balance Concern — ETB Salvage 6 is extremely generous at this rate.**
> A 3/4 for {2}{W}{W} is already a reasonable baseline body. Salvage 6 on entry is the maximum end of the rare scaling, meaning this card essentially guarantees finding an artifact from a deep dig the moment it resolves. Combined with a repeatable salvage 3 activated ability, this card provides an enormous amount of card selection/advantage for a single card. The ETB alone would justify the rare slot; the activated ability pushes this into potentially oppressive territory in any artifact-heavy limited deck. Consider reducing the ETB to salvage 4–5, or increasing the activation cost.
> 
> **2. Design Concern — Repetitive gameplay pattern.**
> Both abilities do the same thing (salvage) at different scales. While this is clean and readable, it makes the card feel one-note for a rare. Rares typically offer some decision-making tension or a second axis of play. This is a softer concern — the card is functional — but it reads more like an uncommon design with rare numbers stapled on.
> 
> **3. Minor Templating — "enters" shorthand is correct (post-MOM templating).**
> No issue here; just confirming.
> 
> **4. Color Pie — Clean.**
> White has salvage access per the set's mechanics, and a 3/4 body with utility is well within white's slice.
> 
> **5. Flavor Text — Solid.** Appropriately darkly humorous for the set's tone.
> 
> ### Summary:
> The primary concern is cumulative value. The card is a guaranteed artifact tutor (from 6 deep) on a solid body that then tutors again every turn. Pulling back slightly on either the ETB depth or the activation cost would bring this into a healthier spot.

*Tokens: 504 in / 430 out — $0.0133*

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
> Name: Subsurface Expedition Leader
> Mana Cost: {2}{W}{W}
> Type: Creature â€” Human Soldier
> Rarity: rare
> Oracle Text: When ~ enters, salvage 6.
> {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> P/T: 3/4
> Flavor Text: "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
> 
> --- Reviewer 1 ---
> ## Review of Subsurface Expedition Leader
> 
> ### Issues Found:
> 
> **1. Balance Concern — ETB Salvage 6 is Very Efficient at This Cost**
> A 3/4 for {2}{W}{W} is already a reasonable rate. Stapling salvage 6 (a rare-tier scaling value) as an ETB means this card generates significant card advantage the moment it resolves, before the opponent can interact with the creature. Combined with a repeatable salvage 3 activation, this card provides an enormous amount of card selection/advantage in artifact-heavy decks. The total package is pushed — consider whether the ETB should be salvage 4–5 instead, or whether the body should be smaller (e.g., 2/3).
> 
> **2. Repeatable Salvage with No Meaningful Gate**
> The activated ability costs {2}{W} and a tap, sorcery-speed only. While the sorcery restriction is good, on a 3/4 body that already replaced itself on entry, the repeated activation has relatively low opportunity cost in slower matchups. This card threatens to dominate limited games where it survives, functioning as a card advantage engine with a solid body. The sorcery restriction helps but may not be sufficient.
> 
> **3. Flavor Text — Tonal Mismatch with Rarity/Role**
> The flavor text leans into comedic/self-deprecating humor ("remarkably high turnover"), which slightly undercuts the card's mechanical identity as a powerful rare expedition leader. This is a minor concern and somewhat subjective, but the tone feels more common/uncommon.
> 
> ### What's Done Well:
> - Templating is clean and correct.
> - Sorcery-speed restriction on the activated ability is a smart design choice.
> - Salvage scaling (6 on ETB, 3 on activation) correctly maps to rare guidelines.
> - Color pie alignment is fine — white gets salvage per the mechanic definition.
> 
> ### Summary:
> The card is mechanically sound but likely **overtuned** for a 4-mana rare. I'd recommend either reducing the ETB to salvage 4–5, or shrinking the body to 2/3.
> 
> --- Reviewer 2 ---
> ## Review: Subsurface Expedition Leader
> 
> ### Issues Found:
> 
> **1. Balance — ETB Salvage 6 is extremely generous at rare alongside a repeated salvage ability.**
> Salvage 6 on a 3/4 body for 4 mana is already a strong rare-level effect by the set's own scaling guidelines (6+ is rare/mythic territory). Stapling a repeatable Salvage 3 activation onto the same card creates a card that dominates any artifact-synergy limited deck. The ETB alone would make this a strong card; the activated ability pushes it into bomb territory with minimal counterplay since the value is front-loaded. Consider either reducing the ETB to Salvage 4-5, or removing the activated ability in favor of just the ETB.
> 
> **2. Design — Redundant play pattern reduces decision-making.**
> Both abilities do the same thing at different scales. There's no tension or interesting choice here — you always want to use both. Stronger rare designs typically create decisions. Consider differentiating the two abilities (e.g., the activated ability could put the artifact directly onto the battlefield, or have a different conditional trigger) to create more interesting gameplay.
> 
> **3. Minor Templating — Activate restriction wording.**
> "Activate only as a sorcery" is correct modern templating. No issue here.
> 
> **4. Color Pie — Clean.**
> White has access to Salvage per the set mechanics, and a 3/4 body with tap abilities is well within white's creature design space.
> 
> **5. Flavor Text — Good.**
> The dark humor fits the set's tone well and adds personality without conflicting with the mechanical identity.
> 
> ### Summary:
> The card is mechanically functional and correctly templated, but is overloaded on raw value for a 4-mana rare. The primary concern is power level in Limited and the lack of meaningful design tension between the two abilities.
> 
> --- Reviewer 3 ---
> ## Review of Subsurface Expedition Leader
> 
> ### Issues Found:
> 
> **1. Balance Concern — ETB Salvage 6 is extremely generous at this rate.**
> A 3/4 for {2}{W}{W} is already a reasonable baseline body. Salvage 6 on entry is the maximum end of the rare scaling, meaning this card essentially guarantees finding an artifact from a deep dig the moment it resolves. Combined with a repeatable salvage 3 activated ability, this card provides an enormous amount of card selection/advantage for a single card. The ETB alone would justify the rare slot; the activated ability pushes this into potentially oppressive territory in any artifact-heavy limited deck. Consider reducing the ETB to salvage 4–5, or increasing the activation cost.
> 
> **2. Design Concern — Repetitive gameplay pattern.**
> Both abilities do the same thing (salvage) at different scales. While this is clean and readable, it makes the card feel one-note for a rare. Rares typically offer some decision-making tension or a second axis of play. This is a softer concern — the card is functional — but it reads more like an uncommon design with rare numbers stapled on.
> 
> **3. Minor Templating — "enters" shorthand is correct (post-MOM templating).**
> No issue here; just confirming.
> 
> **4. Color Pie — Clean.**
> White has salvage access per the set's mechanics, and a 3/4 body with utility is well within white's slice.
> 
> **5. Flavor Text — Solid.** Appropriately darkly humorous for the set's tone.
> 
> ### Summary:
> The primary concern is cumulative value. The card is a guaranteed artifact tutor (from 6 deep) on a solid body that then tutors again every turn. Pulling back slightly on either the ETB depth or the activation cost would bring this into a healthier spot.
> 
> Based on the consensus of these 3 reviews (issues raised by at least 2 reviewers), produce a revised version of the card. If no issues have consensus, return the card unchanged with verdict OK. Only fix issues that at least 2 reviewers agree on.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Balance \u2014 ETB Salvage 6 is too generous at 4 mana alongside a repeatable salvage ability. All 3 reviewers agree the ETB should be reduced to salvage 4-5, or the body/activation cost adjusted.",
    "Design \u2014 Redundant gameplay pattern with both abilities doing the same thing (salvage) at different scales, reducing decision-making tension for a rare. Raised by Reviewers 2 and 3."
  ],
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{2}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When ~ enters, salvage 5.\n{3}{W}, {T}: Put an artifact card from your hand onto the battlefield tapped. Activate only as a sorcery.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.\""
}
```

*Tokens: 2825 in / 395 out — $0.0240*

## C) Revised Card

```json
{
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{2}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When ~ enters, salvage 5.\n{3}{W}, {T}: Put an artifact card from your hand onto the battlefield tapped. Activate only as a sorcery.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.\""
}
```

**Changes made:**
- Balance — ETB Salvage 6 is too generous at 4 mana alongside a repeatable salvage ability. All 3 reviewers agree the ETB should be reduced to salvage 4-5, or the body/activation cost adjusted.
- Design — Redundant gameplay pattern with both abilities doing the same thing (salvage) at different scales, reducing decision-making tension for a rare. Raised by Reviewers 2 and 3.

## D) Cost

- API calls: 4
- Input tokens: 4337
- Output tokens: 1754
- Cost: $0.0655