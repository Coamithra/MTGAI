# Card 2: Undergrowth Scrounger — Strategy: s3-detailed-sonnet

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

### Step 1: Detailed review analysis

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
> Type: Creature ï¿½ Human Scout
> Rarity: common
> Oracle Text: When ~ dies, salvage 3.
> P/T: 2/1
> Flavor Text: She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too.
> 
> Review this card thoroughly. At minimum, check every criterion below (state PASS or describe the issue for each), but also flag anything else you notice.
> 
> **Templating & Rules Text:**
> - Is the oracle text valid MTG rules text?
> - Does every custom mechanic (salvage, malfunction, overclock) have reminder text on first use?
> - Is capitalization consistent (keyword capitalized at start of ability, lowercase mid-sentence)?
> - Does the card use current MTG templating ("enters" not "enters the battlefield")?
> 
> **Keyword Interactions:**
> - Are there any keywords that are negated or made useless by other abilities? (e.g., haste on a creature that always enters tapped)
> - If there's a conditional ("if you X this turn"), can the condition actually be false during normal play?
> 
> **Balance:**
> - Is the power level appropriate for the mana cost AND rarity? Compare to 2-3 well-known printed MTG cards at similar cost.
> - Note: malfunction cards are intentionally above-rate — the delayed entry IS the drawback.
> 
> **Design:**
> - Does the card have a focused purpose, or is it kitchen sink (3+ unrelated effects)?
> - If effects are variable (deal X damage, etc.), is the variability real or does it always resolve to the same value?
> - Does the card create interesting gameplay decisions?
> 
> **Color Pie:**
> - Are all abilities appropriate for this card's color(s)?
> 
> Provide your detailed analysis for each criterion.

**Response:**
> ## Review of Undergrowth Scrounger
> 
> **Templating & Rules Text:**
> - **PASS** - Oracle text is valid MTG rules text
> - **ISSUE** - Missing reminder text for salvage. Per the mechanics document, salvage has complexity 1 (common-viable), so reminder text should be included on first use at common
> - **PASS** - Capitalization is correct (salvage lowercase mid-sentence)
> - **PASS** - Uses current templating (though no "enters" clause present to evaluate)
> 
> **Keyword Interactions:**
> - **PASS** - No conflicting keywords or abilities
> - **PASS** - No conditional abilities present to evaluate
> 
> **Balance:**
> **PASS** - Power level is appropriate for rarity and cost. This compares well to:
> - **Doomed Traveler** (1W, 1/1, creates 1/1 flyer on death) - Similar ETB-to-death value engine
> - **Tuktuk the Explorer** (2R, 1/1, creates 5/5 on death) - Higher cost but much bigger payoff
> - **Augur of Bolas** (1U, 1/3, looks at top 3 for instant/sorcery) - Similar card selection but different trigger timing
> 
> The 2/1 body for 2 mana is slightly below rate, but the death trigger provides reasonable value. Salvage 3 gives meaningful card selection without being overpowered.
> 
> **Design:**
> - **PASS** - Focused design with clear purpose as a death-trigger value creature
> - **PASS** - No variable effects to evaluate
> - **PASS** - Creates interesting decisions around when to trade it off and whether to play it into removal
> 
> **Color Pie:**
> - **PASS** - Green gets creature death triggers and artifact interaction (especially salvaging/regrowth effects)
> - **PASS** - Salvage is listed as available in Green per the mechanics document
> 
> ## Additional Observations:
> 
> **Positive:**
> - Clean, elegant design that showcases the salvage mechanic effectively
> - Reasonable Common complexity level
> - Good flavor integration with the scrounging theme
> - Creates natural synergy with artifact-based strategies
> 
> **Issues to Address:**
> - **CRITICAL:** Must add salvage reminder text: "When ~ dies, salvage 3. *(Look at the top 3 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*"
> 
> ## Overall Assessment:
> Solid common design once reminder text is added. The card effectively introduces players to salvage while providing reasonable Limited playability.

*Tokens: 773 in / 609 out — $0.0115*

### Step 2: Submit revised card based on review

**Prompt sent:**
> Based on the following review of a card, submit the revised card. If no issues were found, return the card unchanged with verdict OK.
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
> Review findings:
> ## Review of Undergrowth Scrounger
> 
> **Templating & Rules Text:**
> - **PASS** - Oracle text is valid MTG rules text
> - **ISSUE** - Missing reminder text for salvage. Per the mechanics document, salvage has complexity 1 (common-viable), so reminder text should be included on first use at common
> - **PASS** - Capitalization is correct (salvage lowercase mid-sentence)
> - **PASS** - Uses current templating (though no "enters" clause present to evaluate)
> 
> **Keyword Interactions:**
> - **PASS** - No conflicting keywords or abilities
> - **PASS** - No conditional abilities present to evaluate
> 
> **Balance:**
> **PASS** - Power level is appropriate for rarity and cost. This compares well to:
> - **Doomed Traveler** (1W, 1/1, creates 1/1 flyer on death) - Similar ETB-to-death value engine
> - **Tuktuk the Explorer** (2R, 1/1, creates 5/5 on death) - Higher cost but much bigger payoff
> - **Augur of Bolas** (1U, 1/3, looks at top 3 for instant/sorcery) - Similar card selection but different trigger timing
> 
> The 2/1 body for 2 mana is slightly below rate, but the death trigger provides reasonable value. Salvage 3 gives meaningful card selection without being overpowered.
> 
> **Design:**
> - **PASS** - Focused design with clear purpose as a death-trigger value creature
> - **PASS** - No variable effects to evaluate
> - **PASS** - Creates interesting decisions around when to trade it off and whether to play it into removal
> 
> **Color Pie:**
> - **PASS** - Green gets creature death triggers and artifact interaction (especially salvaging/regrowth effects)
> - **PASS** - Salvage is listed as available in Green per the mechanics document
> 
> ## Additional Observations:
> 
> **Positive:**
> - Clean, elegant design that showcases the salvage mechanic effectively
> - Reasonable Common complexity level
> - Good flavor integration with the scrounging theme
> - Creates natural synergy with artifact-based strategies
> 
> **Issues to Address:**
> - **CRITICAL:** Must add salvage reminder text: "When ~ dies, salvage 3. *(Look at the top 3 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*"
> 
> ## Overall Assessment:
> Solid common design once reminder text is added. The card effectively introduces players to salvage while providing reasonable Limited playability.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Missing reminder text for salvage mechanic at common rarity"
  ],
  "name": "Undergrowth Scrounger",
  "mana_cost": "{1}{G}",
  "type_line": "Creature \u2014 Human Scout",
  "oracle_text": "When Undergrowth Scrounger dies, salvage 3. *(Look at the top 3 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*",
  "power": "2",
  "toughness": "1",
  "rarity": "common",
  "flavor_text": "She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too."
}
```

*Tokens: 1387 in / 320 out — $0.0090*

## C) Revised Card

```json
{
  "name": "Undergrowth Scrounger",
  "mana_cost": "{1}{G}",
  "type_line": "Creature \u2014 Human Scout",
  "oracle_text": "When Undergrowth Scrounger dies, salvage 3. *(Look at the top 3 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*",
  "rarity": "common",
  "power": "2",
  "toughness": "1",
  "flavor_text": "She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too."
}
```

**Changes made:**
- Missing reminder text for salvage mechanic at common rarity

## D) Cost

- API calls: 2
- Input tokens: 2160
- Output tokens: 929
- Cost: $0.0204