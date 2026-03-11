# Card 2: Undergrowth Scrounger — Strategy: s9-council-opus

## A) Original Card

```json
{
  "name": "Undergrowth Scrounger",
  "mana_cost": "{1}{G}",
  "cmc": 2,
  "colors": [
    "G"
  ],
  "type_line": "Creature \u00e2\u20ac\u201d Human Scout",
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
> Name: Undergrowth Scrounger
> Mana Cost: {1}{G}
> Type: Creature â€” Human Scout
> Rarity: common
> Oracle Text: When ~ dies, salvage 3.
> P/T: 2/1
> Flavor Text: She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too.
> 
> Critically review this card. List any issues you find with templating, mechanics, balance, design, or color pie. If the card is fine, say "No issues found." Be specific about each issue.

**Response:**
> I'll review this card systematically against the set's mechanical guidelines and general Magic design principles.
> 
> **Templating:** No issues. The death trigger with salvage follows standard templating conventions (e.g., comparable to "When ~ dies, scry 2" or similar patterns).
> 
> **Mechanics:** Salvage 3 at common is within the defined scaling range (2-3 at common). The mechanic is complexity 1, appropriate for common. ✓
> 
> **Color Pie:** Salvage is listed as available in W, U, and G. Green is valid. Green commonly gets death triggers and artifact/permanent searching effects. ✓
> 
> **Balance:** A 2/1 for {1}{G} is a slightly below-rate common body. The death trigger providing salvage 3 is a modest advantage — it's card selection, not guaranteed card advantage, since you only find an artifact if one is in the top 3. This feels appropriately costed for common. Comparable to cards like Elvish Visionary in value ceiling but less consistent. ✓
> 
> **Design:** The card plays well at common — simple to understand, provides a small value floor (a body that trades), and rewards being in the artifact-matters set without being parasitic (it's still a fine 2/1 if you miss on salvage). The death trigger creates interesting combat decisions. The flavor text nicely supports the mechanical story of the card. ✓
> 
> **No issues found.**

*Tokens: 477 in / 326 out — $0.0105*

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
> Name: Undergrowth Scrounger
> Mana Cost: {1}{G}
> Type: Creature â€” Human Scout
> Rarity: common
> Oracle Text: When ~ dies, salvage 3.
> P/T: 2/1
> Flavor Text: She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too.
> 
> Critically review this card. List any issues you find with templating, mechanics, balance, design, or color pie. If the card is fine, say "No issues found." Be specific about each issue.

**Response:**
> **Review of Undergrowth Scrounger**
> 
> No issues found.
> 
> **Reasoning:**
> 
> - **Templating:** "When ~ dies, salvage 3." is correctly templated as a triggered ability using the keyword action properly. Clean and readable for common.
> - **Mechanics:** Salvage 3 is within the common scaling range (2–3). Green is a listed salvage color. Complexity is appropriate for common — a simple French vanilla-adjacent creature with one death trigger.
> - **Balance:** A 2/1 for {1}{G} is a slightly below-rate body at common, which is appropriate given the card advantage potential on death. Salvage 3 is a conditional, filtered draw (artifact only) that requires the creature to die first, making it a fair two-for-one ceiling. Comparable to cards like Elvish Visionary in value profile but less consistent. Well-positioned for limited.
> - **Color Pie:** Green gets salvage per the set's color assignments. Green commonly gets death triggers that generate value (e.g., Byway Courier, Primal Druid). A Human Scout is a fine creature type for green.
> - **Design:** The card tells a clean story — a scrounger who finds useful artifacts even in death. The flavor text reinforces this nicely. Good limited role-player that incentivizes artifact-matters strategies without being parasitic.

*Tokens: 477 in / 315 out — $0.0103*

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
> Name: Undergrowth Scrounger
> Mana Cost: {1}{G}
> Type: Creature â€” Human Scout
> Rarity: common
> Oracle Text: When ~ dies, salvage 3.
> P/T: 2/1
> Flavor Text: She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too.
> 
> Critically review this card. List any issues you find with templating, mechanics, balance, design, or color pie. If the card is fine, say "No issues found." Be specific about each issue.

**Response:**
> I'll review **Undergrowth Scrounger** against the set's mechanics, standard templating, and design principles.
> 
> ---
> 
> **No issues found.**
> 
> This is a clean, well-designed common. Here's my reasoning across each axis:
> 
> - **Templating:** "When ~ dies, salvage 3." follows standard death trigger templating. The keyword ability handles the rest via reminder text. Correct.
> - **Mechanics:** Salvage 3 at common is within the defined scaling range (2–3 at common). Green is a listed salvage color. Complexity 1 is appropriate for common. All checks pass.
> - **Balance:** A 2/1 for {1}{G} with a death trigger that digs 3 deep for an artifact is a fair rate. The body trades down easily, and the salvage is conditional (you need artifacts in your top 3). This compares reasonably to cards like **Elvish Visionary** (which always draws) — here you get a slightly better body but a narrower, conditional reward. Well-calibrated for common.
> - **Color Pie:** Green gets creatures that find things when they die (e.g., treasure-finders, land-finders). A green creature that recovers artifacts from the environment fits both mechanically and flavor-wise, especially in a set themed around salvaging.
> - **Design:** The card tells a clear story — a scout who, upon dying, leaves behind useful scrap she found. The flavor text reinforces this. It plays a clean role as a low-drop that smooths artifact synergies without being overpowered.

*Tokens: 477 in / 363 out — $0.0115*

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
> Name: Undergrowth Scrounger
> Mana Cost: {1}{G}
> Type: Creature â€” Human Scout
> Rarity: common
> Oracle Text: When ~ dies, salvage 3.
> P/T: 2/1
> Flavor Text: She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too.
> 
> --- Reviewer 1 ---
> I'll review this card systematically against the set's mechanical guidelines and general Magic design principles.
> 
> **Templating:** No issues. The death trigger with salvage follows standard templating conventions (e.g., comparable to "When ~ dies, scry 2" or similar patterns).
> 
> **Mechanics:** Salvage 3 at common is within the defined scaling range (2-3 at common). The mechanic is complexity 1, appropriate for common. ✓
> 
> **Color Pie:** Salvage is listed as available in W, U, and G. Green is valid. Green commonly gets death triggers and artifact/permanent searching effects. ✓
> 
> **Balance:** A 2/1 for {1}{G} is a slightly below-rate common body. The death trigger providing salvage 3 is a modest advantage — it's card selection, not guaranteed card advantage, since you only find an artifact if one is in the top 3. This feels appropriately costed for common. Comparable to cards like Elvish Visionary in value ceiling but less consistent. ✓
> 
> **Design:** The card plays well at common — simple to understand, provides a small value floor (a body that trades), and rewards being in the artifact-matters set without being parasitic (it's still a fine 2/1 if you miss on salvage). The death trigger creates interesting combat decisions. The flavor text nicely supports the mechanical story of the card. ✓
> 
> **No issues found.**
> 
> --- Reviewer 2 ---
> **Review of Undergrowth Scrounger**
> 
> No issues found.
> 
> **Reasoning:**
> 
> - **Templating:** "When ~ dies, salvage 3." is correctly templated as a triggered ability using the keyword action properly. Clean and readable for common.
> - **Mechanics:** Salvage 3 is within the common scaling range (2–3). Green is a listed salvage color. Complexity is appropriate for common — a simple French vanilla-adjacent creature with one death trigger.
> - **Balance:** A 2/1 for {1}{G} is a slightly below-rate body at common, which is appropriate given the card advantage potential on death. Salvage 3 is a conditional, filtered draw (artifact only) that requires the creature to die first, making it a fair two-for-one ceiling. Comparable to cards like Elvish Visionary in value profile but less consistent. Well-positioned for limited.
> - **Color Pie:** Green gets salvage per the set's color assignments. Green commonly gets death triggers that generate value (e.g., Byway Courier, Primal Druid). A Human Scout is a fine creature type for green.
> - **Design:** The card tells a clean story — a scrounger who finds useful artifacts even in death. The flavor text reinforces this nicely. Good limited role-player that incentivizes artifact-matters strategies without being parasitic.
> 
> --- Reviewer 3 ---
> I'll review **Undergrowth Scrounger** against the set's mechanics, standard templating, and design principles.
> 
> ---
> 
> **No issues found.**
> 
> This is a clean, well-designed common. Here's my reasoning across each axis:
> 
> - **Templating:** "When ~ dies, salvage 3." follows standard death trigger templating. The keyword ability handles the rest via reminder text. Correct.
> - **Mechanics:** Salvage 3 at common is within the defined scaling range (2–3 at common). Green is a listed salvage color. Complexity 1 is appropriate for common. All checks pass.
> - **Balance:** A 2/1 for {1}{G} with a death trigger that digs 3 deep for an artifact is a fair rate. The body trades down easily, and the salvage is conditional (you need artifacts in your top 3). This compares reasonably to cards like **Elvish Visionary** (which always draws) — here you get a slightly better body but a narrower, conditional reward. Well-calibrated for common.
> - **Color Pie:** Green gets creatures that find things when they die (e.g., treasure-finders, land-finders). A green creature that recovers artifacts from the environment fits both mechanically and flavor-wise, especially in a set themed around salvaging.
> - **Design:** The card tells a clear story — a scout who, upon dying, leaves behind useful scrap she found. The flavor text reinforces this. It plays a clean role as a low-drop that smooths artifact synergies without being overpowered.
> 
> Based on the consensus of these 3 reviews (issues raised by at least 2 reviewers), produce a revised version of the card. If no issues have consensus, return the card unchanged with verdict OK. Only fix issues that at least 2 reviewers agree on.

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

*Tokens: 2443 in / 257 out — $0.0186*

## C) Revised Card

No changes (OK)

**Changes made:**
- None

## D) Cost

- API calls: 4
- Input tokens: 3874
- Output tokens: 1261
- Cost: $0.0509