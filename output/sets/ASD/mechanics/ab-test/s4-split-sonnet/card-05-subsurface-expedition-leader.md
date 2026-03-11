# Card 5: Subsurface Expedition Leader — Strategy: s4-split-sonnet

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
> Type: Creature â€” Human Soldier
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
> Here are the issues found:
> 
> **Reminder Text Missing**
> 
> Salvage appears twice on this card. Per the submission guidelines, reminder text is required on its first use. The first instance ("When ~ enters, salvage 6.") lacks reminder text. The second instance on the activated ability correctly omits it, but the first must include it.
> 
> **Salvage Scaling Violation**
> 
> The guidelines specify salvage 6+ at rare/mythic, so "salvage 6" on the triggered ability is acceptable for rare. However, the activated ability uses "salvage 3," which is listed as a common-level scaling (2–3). This is not strictly a rules templating error, but it is worth flagging as a potential design inconsistency — using a below-rate salvage value on an activated ability of a rare card may be intentional (the activation cost gates it), but it should be confirmed as deliberate.
> 
> **"When ~ enters" Templating**
> 
> Current MtG templating convention following the 2023/2024 rules update uses "When [This card's name] enters" rather than "When [This card's name] enters the battlefield." The tilde shorthand (~) is used in card editors but should be replaced with the full card name in final oracle text. Confirm your editor substitutes ~ correctly.
> 
> **No Other Issues Found**
> 
> Keyword capitalization (Salvage) is consistent. The "Activate only as a sorcery" restriction is correctly templated. P/T and mana cost formatting appear correct.

*Tokens: 558 in / 342 out — $0.0068*

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
> Type: Creature â€” Human Soldier
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
> ## Design Review: Subsurface Expedition Leader
> 
> ### Keyword Nonbos
> No keyword conflicts. The activated ability's "activate only as a sorcery" restriction is standard and doesn't conflict with anything on the card.
> 
> ### Conditional Check
> No conditionals present.
> 
> ### Kitchen Sink Check
> Both abilities do the same thing (Salvage), just at different scales and contexts. ETB Salvage 6 is the headline payoff; the activated ability is a repeatable, smaller version. These are thematically and mechanically unified around the same action. **Not kitchen sink.**
> 
> ### Variability Check
> Salvage 6 is fixed. Salvage 3 is fixed. No false variability.
> 
> ### Focused Purpose
> Clear and focused: this card is an artifact-tutor engine. The ETB is a strong immediate payoff (Salvage 6 at rare is within the stated scaling guidelines), and the activated ability provides ongoing card selection. The "Expedition Leader" flavor supports the "dig for resources" mechanical identity cleanly.
> 
> ### Other Flags
> - **Power level note:** Salvage 6 on a 3/4 body for {2}{W}{W} is quite strong. Salvage 6 effectively digs through more than 10% of a 60-card deck for an artifact. Worth playtesting for being over-rate, though rare status supports this.
> - The activated ability cost ({2}{W}{T}) is reasonable as a sorcery-speed sink.
> 
> **PASS**

*Tokens: 567 in / 345 out — $0.0069*

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
> Type: Creature â€” Human Soldier
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
> ## Power Level Analysis: Subsurface Expedition Leader
> 
> ### Breaking Down the Card
> 
> **4 mana, 3/4 body** — solid baseline (comparable to Inspiring Overseer's efficiency tier)
> 
> **ETB Salvage 6:** Look at top 6, put an artifact into hand. At rare, this is appropriate scaling per the mechanic's own rules. This is essentially a 4-mana 3/4 that tutors an artifact into hand on entry. That's strong but not broken — it's conditional (needs artifacts in top 6) and puts you no net cards ahead (you're not drawing, you're filtering).
> 
> **{2}{W}, T: Salvage 3 (sorcery speed):** A repeatable activated ability at 3 mana, sorcery-only, tapped. This is meaningfully slow and telegraphed.
> 
> ---
> 
> ### Comparisons
> 
> - **Recruiter of the Guard** (3 mana, 1/1, tutors a creature to hand): Strictly better tutor effect for one less mana, though creature-restricted. Expedition Leader compares favorably in body, less favorably in tutor precision.
> - **Stoneforge Mystic** (2 mana, 1/2, tutors any equipment): Cheaper, more precise, has equipment-play ability. Expedition Leader's body and ETB are less explosive but less broken.
> - **Oswald Fiddlebender** (2 mana, 1/1, repeatable artifact tutor): More powerful activated ability, worse body. Expedition Leader's activated ability is weaker but the ETB compensates.
> 
> ---
> 
> ### Assessment
> 
> The card is appropriately costed. Salvage 6 on ETB at 4 mana is strong but conditional, and the repeatable ability is intentionally taxed (3 mana + tap + sorcery). The 3/4 body is fair for four mana in white.
> 
> **PASS**

*Tokens: 589 in / 453 out — $0.0086*

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
> Type: Creature â€” Human Soldier
> Rarity: rare
> Oracle Text: When ~ enters, salvage 6.
> {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> P/T: 3/4
> Flavor Text: "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
> 
> Issues found:
> - Templating: Here are the issues found:
> 
> **Reminder Text Missing**
> 
> Salvage appears twice on this card. Per the submission guidelines, reminder text is required on its first use. The first instance ("When ~ enters, salvage 6.") lacks reminder text. The second instance on the activated ability correctly omits it, but the first must include it.
> 
> **Salvage Scaling Violation**
> 
> The guidelines specify salvage 6+ at rare/mythic, so "salvage 6" on the triggered ability is acceptable for rare. However, the activated ability uses "salvage 3," which is listed as a common-level scaling (2–3). This is not strictly a rules templating error, but it is worth flagging as a potential design inconsistency — using a below-rate salvage value on an activated ability of a rare card may be intentional (the activation cost gates it), but it should be confirmed as deliberate.
> 
> **"When ~ enters" Templating**
> 
> Current MtG templating convention following the 2023/2024 rules update uses "When [This card's name] enters" rather than "When [This card's name] enters the battlefield." The tilde shorthand (~) is used in card editors but should be replaced with the full card name in final oracle text. Confirm your editor substitutes ~ correctly.
> 
> **No Other Issues Found**
> 
> Keyword capitalization (Salvage) is consistent. The "Activate only as a sorcery" restriction is correctly templated. P/T and mana cost formatting appear correct.
> - Mechanics: ## Design Review: Subsurface Expedition Leader
> 
> ### Keyword Nonbos
> No keyword conflicts. The activated ability's "activate only as a sorcery" restriction is standard and doesn't conflict with anything on the card.
> 
> ### Conditional Check
> No conditionals present.
> 
> ### Kitchen Sink Check
> Both abilities do the same thing (Salvage), just at different scales and contexts. ETB Salvage 6 is the headline payoff; the activated ability is a repeatable, smaller version. These are thematically and mechanically unified around the same action. **Not kitchen sink.**
> 
> ### Variability Check
> Salvage 6 is fixed. Salvage 3 is fixed. No false variability.
> 
> ### Focused Purpose
> Clear and focused: this card is an artifact-tutor engine. The ETB is a strong immediate payoff (Salvage 6 at rare is within the stated scaling guidelines), and the activated ability provides ongoing card selection. The "Expedition Leader" flavor supports the "dig for resources" mechanical identity cleanly.
> 
> ### Other Flags
> - **Power level note:** Salvage 6 on a 3/4 body for {2}{W}{W} is quite strong. Salvage 6 effectively digs through more than 10% of a 60-card deck for an artifact. Worth playtesting for being over-rate, though rare status supports this.
> - The activated ability cost ({2}{W}{T}) is reasonable as a sorcery-speed sink.
> 
> **PASS**
> - Balance: ## Power Level Analysis: Subsurface Expedition Leader
> 
> ### Breaking Down the Card
> 
> **4 mana, 3/4 body** — solid baseline (comparable to Inspiring Overseer's efficiency tier)
> 
> **ETB Salvage 6:** Look at top 6, put an artifact into hand. At rare, this is appropriate scaling per the mechanic's own rules. This is essentially a 4-mana 3/4 that tutors an artifact into hand on entry. That's strong but not broken — it's conditional (needs artifacts in top 6) and puts you no net cards ahead (you're not drawing, you're filtering).
> 
> **{2}{W}, T: Salvage 3 (sorcery speed):** A repeatable activated ability at 3 mana, sorcery-only, tapped. This is meaningfully slow and telegraphed.
> 
> ---
> 
> ### Comparisons
> 
> - **Recruiter of the Guard** (3 mana, 1/1, tutors a creature to hand): Strictly better tutor effect for one less mana, though creature-restricted. Expedition Leader compares favorably in body, less favorably in tutor precision.
> - **Stoneforge Mystic** (2 mana, 1/2, tutors any equipment): Cheaper, more precise, has equipment-play ability. Expedition Leader's body and ETB are less explosive but less broken.
> - **Oswald Fiddlebender** (2 mana, 1/1, repeatable artifact tutor): More powerful activated ability, worse body. Expedition Leader's activated ability is weaker but the ETB compensates.
> 
> ---
> 
> ### Assessment
> 
> The card is appropriately costed. Salvage 6 on ETB at 4 mana is strong but conditional, and the repeatable ability is intentionally taxed (3 mana + tap + sorcery). The 3/4 body is fair for four mana in white.
> 
> **PASS**
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Reminder text missing on first instance of Salvage in the triggered ability.",
    "Tilde (~) replaced with full card name in oracle text per final card formatting conventions."
  ],
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{2}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When Subsurface Expedition Leader enters, salvage 6. (Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)\n{2}{W}, {T}: Salvage 3. Activate only as a sorcery.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.\""
}
```

*Tokens: 2553 in / 366 out — $0.0131*

## C) Revised Card

```json
{
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{2}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When Subsurface Expedition Leader enters, salvage 6. (Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)\n{2}{W}, {T}: Salvage 3. Activate only as a sorcery.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.\""
}
```

**Changes made:**
- Reminder text missing on first instance of Salvage in the triggered ability.
- Tilde (~) replaced with full card name in oracle text per final card formatting conventions.

## D) Cost

- API calls: 4
- Input tokens: 4267
- Output tokens: 1506
- Cost: $0.0354