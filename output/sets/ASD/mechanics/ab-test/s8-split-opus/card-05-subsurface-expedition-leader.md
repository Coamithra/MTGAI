# Card 5: Subsurface Expedition Leader — Strategy: s8-split-opus

## A) Original Card

```json
{
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{2}{W}{W}",
  "cmc": 4,
  "colors": [
    "W"
  ],
  "type_line": "Creature \u00ef\u00bf\u00bd Human Soldier",
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
> Name: Subsurface Expedition Leader
> Mana Cost: {2}{W}{W}
> Type: Creature ï¿½ Human Soldier
> Rarity: rare
> Oracle Text: When ~ enters, salvage 6.
> {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> P/T: 3/4
> Flavor Text: "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
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
> **Issues Found:**
> 
> 1. **Missing reminder text**: The card uses "salvage" twice but never includes the reminder text. Since this is a custom mechanic, it needs reminder text on at least its first appearance. The oracle text should read:
> 
> ```
> When ~ enters, salvage 6. (Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)
> {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> ```
> 
> 2. **Card type line**: There appears to be an encoding issue with "Creature ï¿½ Human Soldier". This should be "Creature — Human Soldier" with an em dash.
> 
> All other templating appears correct:
> - "enters" is properly shortened from "enters the battlefield"
> - The activated ability is properly formatted
> - "Activate only as a sorcery" is correct timing restriction templating
> - Power/toughness is properly formatted
> 
> The card would be valid once these issues are corrected.

*Tokens: 560 in / 255 out — $0.0275*

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
> Name: Subsurface Expedition Leader
> Mana Cost: {2}{W}{W}
> Type: Creature ï¿½ Human Soldier
> Rarity: rare
> Oracle Text: When ~ enters, salvage 6.
> {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> P/T: 3/4
> Flavor Text: "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
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
> Looking at Subsurface Expedition Leader:
> 
> **Design Analysis:**
> 
> The card has a clear, focused purpose: it's a dedicated salvage engine that provides both immediate and repeatable artifact selection. The two salvage abilities work together cohesively - a big dig when it enters, then smaller repeated digs afterward.
> 
> **Checking for issues:**
> 
> - **Keyword nonbos:** None. Both abilities synergize well.
> - **Conditional checks:** The sorcery-speed restriction on the activated ability is meaningful and can matter during normal play.
> - **Kitchen sink design:** No. Both abilities are salvage-based and create a coherent gameplan.
> - **Variable effects:** The salvage values (6 and 3) are fixed and intentional - the ETB provides a big initial value while the activated ability offers smaller, repeatable value.
> - **Focused purpose:** Yes, very focused as an artifact-matters value engine.
> 
> **Additional observations:**
> - The 4 mana 3/4 body is slightly below rate for rare, but this is appropriate given the powerful salvage 6 ETB effect
> - The activated ability costing 3 mana to salvage 3 creates interesting tension - you're paying premium for repeated selection
> - The sorcery-speed restriction is good design that prevents end-of-turn value grinding
> - At rare, salvage 6 fits the stated scaling guidelines (6+ at rare/mythic)
> 
> **PASS**
> 
> The design is sound and well-executed as a build-around rare for an artifact-matters deck.

*Tokens: 569 in / 349 out — $0.0347*

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
> Name: Subsurface Expedition Leader
> Mana Cost: {2}{W}{W}
> Type: Creature ï¿½ Human Soldier
> Rarity: rare
> Oracle Text: When ~ enters, salvage 6.
> {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> P/T: 3/4
> Flavor Text: "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
> 
> Check:
> - Is the power level appropriate for the mana cost AND rarity?
> - Compare to 2-3 well-known printed MTG cards at similar mana cost and rarity.
> - Note: malfunction cards are intentionally above-rate — the delayed entry IS the drawback. Do not flag these for being above-rate.
> - Note: mythic rares are allowed to be powerful build-arounds. Do not nerf mythics to rare power level.
> 
> State whether the balance is PASS, or describe the specific balance issue with card comparisons.

**Response:**
> Looking at Subsurface Expedition Leader as a 4-mana rare creature:
> 
> **Power Level Analysis:**
> 
> This card provides exceptional value for {2}{W}{W}:
> - 3/4 body (solid stats for 4 mana)
> - Immediate card selection via salvage 6 (likely nets 1-2 artifacts)
> - Repeatable salvage 3 engine
> 
> **Comparisons:**
> - **Ranger-Captain of Eos** (3 mana, 3/3): Tutors a 1-mana creature on ETB, has a powerful activated ability. This is similarly a value creature with card advantage.
> - **Militia Bugler** (3 mana, 2/3): Looks at top 4 cards for a creature with power 2 or less. This card is significantly better - more cards seen, better body, repeatable effect.
> - **Thalia's Lancers** (5 mana, 4/4): Searches entire library for a legendary card. This is more restricted but guaranteed, while Expedition Leader sees more cards total.
> 
> **Balance Verdict: NEEDS ADJUSTMENT**
> 
> The card is too efficient at 4 mana. The combination of:
> 1. Strong 3/4 body
> 2. Immediate salvage 6 (seeing 6 cards is very powerful)
> 3. Repeatable salvage 3
> 
> Makes this significantly above the power level of comparable rare creatures. 
> 
> **Suggested fixes:**
> - Reduce the body to 2/3 or 2/4, OR
> - Reduce initial salvage to 4, OR
> - Increase activation cost to {3}{W} or {2}{W}{W}
> 
> The card would be more appropriately costed at {3}{W}{W} with current stats, or needs a meaningful reduction in one of its three strong aspects to justify {2}{W}{W}.

*Tokens: 591 in / 438 out — $0.0417*

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
> Name: Subsurface Expedition Leader
> Mana Cost: {2}{W}{W}
> Type: Creature ï¿½ Human Soldier
> Rarity: rare
> Oracle Text: When ~ enters, salvage 6.
> {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> P/T: 3/4
> Flavor Text: "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
> 
> Issues found:
> - Templating: Looking at this card's templating:
> 
> **Issues Found:**
> 
> 1. **Missing reminder text**: The card uses "salvage" twice but never includes the reminder text. Since this is a custom mechanic, it needs reminder text on at least its first appearance. The oracle text should read:
> 
> ```
> When ~ enters, salvage 6. (Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)
> {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> ```
> 
> 2. **Card type line**: There appears to be an encoding issue with "Creature ï¿½ Human Soldier". This should be "Creature — Human Soldier" with an em dash.
> 
> All other templating appears correct:
> - "enters" is properly shortened from "enters the battlefield"
> - The activated ability is properly formatted
> - "Activate only as a sorcery" is correct timing restriction templating
> - Power/toughness is properly formatted
> 
> The card would be valid once these issues are corrected.
> - Mechanics: Looking at Subsurface Expedition Leader:
> 
> **Design Analysis:**
> 
> The card has a clear, focused purpose: it's a dedicated salvage engine that provides both immediate and repeatable artifact selection. The two salvage abilities work together cohesively - a big dig when it enters, then smaller repeated digs afterward.
> 
> **Checking for issues:**
> 
> - **Keyword nonbos:** None. Both abilities synergize well.
> - **Conditional checks:** The sorcery-speed restriction on the activated ability is meaningful and can matter during normal play.
> - **Kitchen sink design:** No. Both abilities are salvage-based and create a coherent gameplan.
> - **Variable effects:** The salvage values (6 and 3) are fixed and intentional - the ETB provides a big initial value while the activated ability offers smaller, repeatable value.
> - **Focused purpose:** Yes, very focused as an artifact-matters value engine.
> 
> **Additional observations:**
> - The 4 mana 3/4 body is slightly below rate for rare, but this is appropriate given the powerful salvage 6 ETB effect
> - The activated ability costing 3 mana to salvage 3 creates interesting tension - you're paying premium for repeated selection
> - The sorcery-speed restriction is good design that prevents end-of-turn value grinding
> - At rare, salvage 6 fits the stated scaling guidelines (6+ at rare/mythic)
> 
> **PASS**
> 
> The design is sound and well-executed as a build-around rare for an artifact-matters deck.
> - Balance: Looking at Subsurface Expedition Leader as a 4-mana rare creature:
> 
> **Power Level Analysis:**
> 
> This card provides exceptional value for {2}{W}{W}:
> - 3/4 body (solid stats for 4 mana)
> - Immediate card selection via salvage 6 (likely nets 1-2 artifacts)
> - Repeatable salvage 3 engine
> 
> **Comparisons:**
> - **Ranger-Captain of Eos** (3 mana, 3/3): Tutors a 1-mana creature on ETB, has a powerful activated ability. This is similarly a value creature with card advantage.
> - **Militia Bugler** (3 mana, 2/3): Looks at top 4 cards for a creature with power 2 or less. This card is significantly better - more cards seen, better body, repeatable effect.
> - **Thalia's Lancers** (5 mana, 4/4): Searches entire library for a legendary card. This is more restricted but guaranteed, while Expedition Leader sees more cards total.
> 
> **Balance Verdict: NEEDS ADJUSTMENT**
> 
> The card is too efficient at 4 mana. The combination of:
> 1. Strong 3/4 body
> 2. Immediate salvage 6 (seeing 6 cards is very powerful)
> 3. Repeatable salvage 3
> 
> Makes this significantly above the power level of comparable rare creatures. 
> 
> **Suggested fixes:**
> - Reduce the body to 2/3 or 2/4, OR
> - Reduce initial salvage to 4, OR
> - Increase activation cost to {3}{W} or {2}{W}{W}
> 
> The card would be more appropriately costed at {3}{W}{W} with current stats, or needs a meaningful reduction in one of its three strong aspects to justify {2}{W}{W}.
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Missing reminder text for salvage mechanic",
    "Encoding issue with creature type line (contained garbled characters)",
    "Card is too powerful for its mana cost - combination of strong body, salvage 6 ETB, and repeatable salvage 3 is above rare power level"
  ],
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{3}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When ~ enters, salvage 6. (Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)\n{2}{W}, {T}: Salvage 3. Activate only as a sorcery.",
  "power": "3",
  "toughness": "4",
  "rarity": "rare",
  "flavor_text": "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
}
```

*Tokens: 2184 in / 384 out — $0.0616*

## C) Revised Card

```json
{
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{3}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When ~ enters, salvage 6. (Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)\n{2}{W}, {T}: Salvage 3. Activate only as a sorcery.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
}
```

**Changes made:**
- Missing reminder text for salvage mechanic
- Encoding issue with creature type line (contained garbled characters)
- Card is too powerful for its mana cost - combination of strong body, salvage 6 ETB, and repeatable salvage 3 is above rare power level

## D) Cost

- API calls: 4
- Input tokens: 3904
- Output tokens: 1426
- Cost: $0.1655