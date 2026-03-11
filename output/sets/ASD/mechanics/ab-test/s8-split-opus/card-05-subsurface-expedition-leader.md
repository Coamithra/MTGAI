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
> Here are the templating issues found:
> 
> 1. **Missing reminder text on first use of salvage.** The first instance of "salvage 6" must include the reminder text in parentheses. The second use (salvage 3) does not need it, but the first one does.
> 
> 2. **Sorcery-speed restriction templating.** The current convention (as of recent sets) is **"Activate only as a sorcery."** — this matches what you have, so this part is correct.
> 
> **Suggested corrected Oracle text:**
> 
> > When ~ enters, salvage 6. *(Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*
> > {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> 
> Everything else checks out:
> - "When ~ enters" is current templating (post-MOM convention).
> - Mana cost, type line, and P/T are all fine.
> - Salvage scaling (6 on ETB at rare, 3 on activated ability) is within the defined parameters.
> - Keyword capitalization is consistent (lowercase "salvage" as a keyword ability used in rules text).
> 
> **Result: One issue found (missing reminder text on first use).**

*Tokens: 557 in / 309 out — $0.0105*

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
> PASS
> 
> The design is sound. Here's my reasoning:
> 
> - **No keyword nonbos**: Salvage is a simple library-filtering action with no conflicting interactions on this card.
> - **No false conditionals**: There are no conditionals to evaluate.
> - **Not kitchen sink**: Both abilities do the same thing (salvage) at different scales. The ETB provides a big initial dig, and the activated ability provides repeatable value. These are clearly related and reinforce a single game plan.
> - **Variability is real**: Salvage 6 (ETB) vs. Salvage 3 (activated) is a meaningful difference — the ETB is the splashy payoff, the tap ability is the grindier, smaller repeated effect. This scaling feels intentional and correct.
> - **Focused purpose**: This is a dedicated artifact-finding engine for a W-based artifact deck. The 3/4 body at 4 mana is reasonable, and the sorcery-speed restriction on the tap ability is a smart inclusion to prevent it from being too flexible.
> 
> The salvage 6 at rare is within the stated scaling guidelines (6+ at rare). The card reads cleanly and has a clear role as a value creature that rewards building around artifacts. The flavor text is a nice touch that doesn't affect evaluation but fits well.

*Tokens: 566 in / 298 out — $0.0103*

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
> # Balance Check: Subsurface Expedition Leader
> 
> ## Card Analysis
> 
> A 4-mana 3/4 that ETBs with Salvage 6, then has a repeatable Salvage 3 activated ability for {2}{W} + tap at sorcery speed.
> 
> ## Comparisons
> 
> - **Ranger of Eos** (2WW, 3/2, rare): Fetches two creatures with MV 1 or less to hand on ETB. Two guaranteed cards vs. one probable card from Salvage 6, but Ranger has a smaller body.
> - **Recruiter of the Guard** (2W, 1/1, rare): Tutors a creature with toughness 2 or less to hand. Guaranteed tutor but smaller body and one less mana.
> - **Inspiring Overseer** (2W, 2/1, common): Draws a card and gains 1 life for 3 mana. This is a full mana more but significantly more powerful.
> 
> ## Evaluation
> 
> **ETB Salvage 6:** In an artifact-heavy set, looking at 6 cards is very likely to hit (probably 70-80%+ in a dedicated deck). This is close to a conditional tutor stapled onto a solid body.
> 
> **Repeatable Salvage 3:** This is where the card gets strong. Even at sorcery speed and requiring tap + 3 mana, repeatable card selection/advantage on a 3/4 body is significant. In a deck built around artifacts, this generates steady advantage every turn it survives.
> 
> **Overall:** The body is reasonable at 3/4 for 4 mana. The ETB is strong but conditional. The activated ability provides excellent long-game value but requires mana investment and is sorcery-speed. For a rare in an artifact-focused set, this feels like a strong but fair engine card — it doesn't take over immediately and requires board presence plus mana to grind.
> 
> ## Verdict
> 
> **PASS** — Strong rare that rewards artifact-heavy deckbuilding without being pushed. The sorcery-speed restriction and mana cost on the activated ability are appropriate safety valves.

*Tokens: 588 in / 500 out — $0.0154*

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
> - Templating: Here are the templating issues found:
> 
> 1. **Missing reminder text on first use of salvage.** The first instance of "salvage 6" must include the reminder text in parentheses. The second use (salvage 3) does not need it, but the first one does.
> 
> 2. **Sorcery-speed restriction templating.** The current convention (as of recent sets) is **"Activate only as a sorcery."** — this matches what you have, so this part is correct.
> 
> **Suggested corrected Oracle text:**
> 
> > When ~ enters, salvage 6. *(Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*
> > {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> 
> Everything else checks out:
> - "When ~ enters" is current templating (post-MOM convention).
> - Mana cost, type line, and P/T are all fine.
> - Salvage scaling (6 on ETB at rare, 3 on activated ability) is within the defined parameters.
> - Keyword capitalization is consistent (lowercase "salvage" as a keyword ability used in rules text).
> 
> **Result: One issue found (missing reminder text on first use).**
> - Mechanics: PASS
> 
> The design is sound. Here's my reasoning:
> 
> - **No keyword nonbos**: Salvage is a simple library-filtering action with no conflicting interactions on this card.
> - **No false conditionals**: There are no conditionals to evaluate.
> - **Not kitchen sink**: Both abilities do the same thing (salvage) at different scales. The ETB provides a big initial dig, and the activated ability provides repeatable value. These are clearly related and reinforce a single game plan.
> - **Variability is real**: Salvage 6 (ETB) vs. Salvage 3 (activated) is a meaningful difference — the ETB is the splashy payoff, the tap ability is the grindier, smaller repeated effect. This scaling feels intentional and correct.
> - **Focused purpose**: This is a dedicated artifact-finding engine for a W-based artifact deck. The 3/4 body at 4 mana is reasonable, and the sorcery-speed restriction on the tap ability is a smart inclusion to prevent it from being too flexible.
> 
> The salvage 6 at rare is within the stated scaling guidelines (6+ at rare). The card reads cleanly and has a clear role as a value creature that rewards building around artifacts. The flavor text is a nice touch that doesn't affect evaluation but fits well.
> - Balance: # Balance Check: Subsurface Expedition Leader
> 
> ## Card Analysis
> 
> A 4-mana 3/4 that ETBs with Salvage 6, then has a repeatable Salvage 3 activated ability for {2}{W} + tap at sorcery speed.
> 
> ## Comparisons
> 
> - **Ranger of Eos** (2WW, 3/2, rare): Fetches two creatures with MV 1 or less to hand on ETB. Two guaranteed cards vs. one probable card from Salvage 6, but Ranger has a smaller body.
> - **Recruiter of the Guard** (2W, 1/1, rare): Tutors a creature with toughness 2 or less to hand. Guaranteed tutor but smaller body and one less mana.
> - **Inspiring Overseer** (2W, 2/1, common): Draws a card and gains 1 life for 3 mana. This is a full mana more but significantly more powerful.
> 
> ## Evaluation
> 
> **ETB Salvage 6:** In an artifact-heavy set, looking at 6 cards is very likely to hit (probably 70-80%+ in a dedicated deck). This is close to a conditional tutor stapled onto a solid body.
> 
> **Repeatable Salvage 3:** This is where the card gets strong. Even at sorcery speed and requiring tap + 3 mana, repeatable card selection/advantage on a 3/4 body is significant. In a deck built around artifacts, this generates steady advantage every turn it survives.
> 
> **Overall:** The body is reasonable at 3/4 for 4 mana. The ETB is strong but conditional. The activated ability provides excellent long-game value but requires mana investment and is sorcery-speed. For a rare in an artifact-focused set, this feels like a strong but fair engine card — it doesn't take over immediately and requires board presence plus mana to grind.
> 
> ## Verdict
> 
> **PASS** — Strong rare that rewards artifact-heavy deckbuilding without being pushed. The sorcery-speed restriction and mana cost on the activated ability are appropriate safety valves.
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Missing reminder text on first use of salvage keyword"
  ],
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{2}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When ~ enters, salvage 6. (Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)\n{2}{W}, {T}: Salvage 3. Activate only as a sorcery.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.\""
}
```

*Tokens: 2519 in / 334 out — $0.0209*

## C) Revised Card

```json
{
  "name": "Subsurface Expedition Leader",
  "mana_cost": "{2}{W}{W}",
  "type_line": "Creature \u2014 Human Soldier",
  "oracle_text": "When ~ enters, salvage 6. (Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)\n{2}{W}, {T}: Salvage 3. Activate only as a sorcery.",
  "rarity": "rare",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover.\""
}
```

**Changes made:**
- Missing reminder text on first use of salvage keyword

## D) Cost

- API calls: 4
- Input tokens: 4230
- Output tokens: 1441
- Cost: $0.0572