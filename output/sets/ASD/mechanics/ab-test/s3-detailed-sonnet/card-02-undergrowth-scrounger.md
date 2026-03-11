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
> Type: Creature â€” Human Scout
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
> # Undergrowth Scrounger — Design Review
> 
> ---
> 
> ## TEMPLATING & RULES TEXT
> 
> **Is the oracle text valid MTG rules text?**
> PASS. "When ~ dies, salvage 3." is clean and grammatically correct. The "~" placeholder for the card's name is standard shorthand in design documents. The trigger condition ("dies") is current templating (as opposed to the older "is put into a graveyard from the battlefield").
> 
> **Does every custom mechanic have reminder text on first use?**
> FAIL. Salvage 3 appears without its reminder text: *(Look at the top 3 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)* At common especially, reminder text is expected on every instance of a custom mechanic. This needs to be added.
> 
> **Is capitalization consistent?**
> PASS. "Salvage" is correctly capitalized as it opens the ability. No mid-sentence keyword usage to evaluate here.
> 
> **Does the card use current MTG templating ("enters" not "enters the battlefield")?**
> PASS. The card doesn't use any enters-the-battlefield language, so no issue here.
> 
> ---
> 
> ## KEYWORD INTERACTIONS
> 
> **Are any keywords negated or made useless by other abilities?**
> PASS. There is only one ability (the death trigger), and no other keywords are present. No conflicts exist.
> 
> **Can any conditional ever be trivially always-true or always-false?**
> PASS. The death trigger fires only when the creature actually dies, which is a genuine conditional — it will frequently not occur (e.g., if the creature is exiled, bounced, or the game ends). The condition is real and meaningful.
> 
> ---
> 
> ## BALANCE
> 
> **Is the power level appropriate for the mana cost and rarity?**
> 
> Let's benchmark:
> 
> - **Elvish Visionary** *(1G, 1/1, draws a card on ETB — common, Magic 2013 etc.)*: Cantrip on entry, 1/1 body. Considered a clean, efficient common.
> - **Llanowar Elves / Quirion Ranger** style 1/1s for G: These trade raw stats for utility.
> - **Winding Way / similar 2-mana G dig spells**: Winding Way (1G) digs 4 for one type. Salvage 3 is strictly weaker (only looks at 3, only finds artifacts), and here it's stapled to a 2/1 body with a *death trigger* rather than an ETB.
> 
> **Assessment:**
> The body (2/1 for 1G) is aggressively statted — essentially a **Grizzly Bears** for one less mana, which is already above rate in green for 2 mana. The death trigger adds a meaningful but conditional upside. The key question is how often you reliably trigger it.
> 
> At common, this card compares reasonably well. A 2/1 for {1}{G} is French vanilla-playable on its own in a set with an artifact theme (where Salvage has targets). The death trigger is:
> - **Less reliable** than an ETB (must die, not just enter)
> - **Conditional on finding artifacts** in the top 3 (deck-dependent)
> - **Narrower** than straight card draw (artifact cards only)
> 
> That said, **this may be slightly pushed for common** in aggressive shell. A 2/1 for 1G is already a strong rate (compare *Kird Ape* requiring a condition, or *Experiment One* as a 1/1 that grows). In a set context where:
> - Artifact synergies are plentiful (making Salvage live)
> - Combat is common (the creature will die)
> 
> ...the trigger will fire often enough to generate real value. I'd flag this as *borderline* but likely acceptable given the artifact restriction and death-trigger unreliability. If the set has lots of self-sacrifice or recursion, revisit.
> 
> **Verdict: PASS with a note.** Watch for synergy abuse with sacrifice outlets. If those exist at common, this becomes potentially too efficient.
> 
> ---
> 
> ## DESIGN
> 
> **Does the card have a focused purpose?**
> PASS. The card has a clear, cohesive identity: an aggressive early creature that rewards you for trading in combat by digging for artifact resources. This is a classic "value creature" archetype, and both halves (the body, the death trigger) serve the same game plan — get in early, trade, recoup value.
> 
> **Is variability real?**
> PASS. Salvage 3 is genuinely variable — the top 3 cards may or may not contain an artifact, and even if they do, the choice of whether to take it is meaningful. The number of cards seen (3) is fixed per the mechanic's scaling rules (appropriately uncommon territory... wait — see below).
> 
> **Does the card create interesting gameplay decisions?**
> PASS. Yes, though modestly. It encourages sequencing decisions (attack into blockers vs. holding back), and Salvage 3 creates mild choices about which card to take and how to order the rest. These are appropriate for common-level complexity.
> 
> ---
> 
> ## COLOR PIE
> 
> **Are all abilities appropriate for the card's color(s)?**
> 
> The card is Green. Let's check:
> 
> - **2/1 creature body**: PASS. Green has efficient creatures; a 2/1 for 1G is well within green's color pie.
> - **Death trigger**: PASS. Green has death triggers (e.g., Llanowar Elves variants, Rishkar's Expertise lineage, Winding Constrictor family). Green caring about creatures dying to generate value is on-pie.
> - **Salvage (artifact tutoring/digging)**: PASS per the set's own rules — Salvage is defined as a White/Blue/Green mechanic, so Green access is intentional and sanctioned.
> 
> No color pie violations.
> 
> ---
> 
> ## ADDITIONAL FLAGS
> 
> **⚠️ Salvage 3 at Common — Scaling Check**
> Per the set's own design rules: *Salvage scales as 2–3 at common, 4–5 at uncommon, 6+ at rare/mythic.* Salvage 3 is within the allowable common range. **PASS** — but this is at the top of the common range (3), which is worth noting. Ensure other common Salvage cards don't also all cluster at Salvage 3, which would make the lower end (Salvage 2) feel underpowered by comparison.
> 
> **⚠️ Flavor Text — Minor Concern**
> The flavor text is evocative and well-written. However, "The wilderness, unfortunately, knew her too" slightly implies danger or death found *her*, which works thematically with the death trigger. This is a soft PASS — it's atmospheric, fits the set's tone ("Anomalous Descent" implies something ominous), and the connection to the death trigger gives it mechanical resonance. Good flavor work.
> 
> **⚠️ Artifact Theme Dependency**
> Salvage is only valuable if the deck (and set) have meaningful artifact cards to find. If the set's artifact density is low, or if Green in particular doesn't interact heavily with artifacts, the death trigger will frequently whiff (finding no artifacts in the top 3). This isn't a card design flaw per se, but a **set-level design dependency** worth flagging for the lead designer. Ensure Green has enough artifact payoffs or artifacts in its color section to make Salvage feel rewarding rather than blank.
> 
> ---
> 
> ## SUMMARY TABLE
> 
> | Criterion | Result |
> |---|---|
> | Valid oracle text | ✅ PASS |
> | Reminder text present | ❌ FAIL — Salvage 3 missing reminder text |
> | Capitalization | ✅ PASS |
> | Current templating ("dies") | ✅ PASS |
> | Keyword conflicts | ✅ PASS |
> | Conditional validity | ✅ PASS |
> | Balance for cost/rarity | ✅ PASS (borderline, monitor) |
> | Focused design | ✅ PASS |
> | Real variability | ✅ PASS |
> | Interesting decisions | ✅ PASS |
> | Color pie | ✅ PASS |
> | Salvage scaling within rules | ✅ PASS |
> 
> **Primary fix required:** Add Salvage reminder text. Everything else is solid. This is a clean, functional common with good flavor and appropriate set-level integration.

*Tokens: 771 in / 2006 out — $0.0324*

### Step 2: Submit revised card based on review

**Prompt sent:**
> Based on the following review of a card, submit the revised card. If no issues were found, return the card unchanged with verdict OK.
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
> Review findings:
> # Undergrowth Scrounger — Design Review
> 
> ---
> 
> ## TEMPLATING & RULES TEXT
> 
> **Is the oracle text valid MTG rules text?**
> PASS. "When ~ dies, salvage 3." is clean and grammatically correct. The "~" placeholder for the card's name is standard shorthand in design documents. The trigger condition ("dies") is current templating (as opposed to the older "is put into a graveyard from the battlefield").
> 
> **Does every custom mechanic have reminder text on first use?**
> FAIL. Salvage 3 appears without its reminder text: *(Look at the top 3 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)* At common especially, reminder text is expected on every instance of a custom mechanic. This needs to be added.
> 
> **Is capitalization consistent?**
> PASS. "Salvage" is correctly capitalized as it opens the ability. No mid-sentence keyword usage to evaluate here.
> 
> **Does the card use current MTG templating ("enters" not "enters the battlefield")?**
> PASS. The card doesn't use any enters-the-battlefield language, so no issue here.
> 
> ---
> 
> ## KEYWORD INTERACTIONS
> 
> **Are any keywords negated or made useless by other abilities?**
> PASS. There is only one ability (the death trigger), and no other keywords are present. No conflicts exist.
> 
> **Can any conditional ever be trivially always-true or always-false?**
> PASS. The death trigger fires only when the creature actually dies, which is a genuine conditional — it will frequently not occur (e.g., if the creature is exiled, bounced, or the game ends). The condition is real and meaningful.
> 
> ---
> 
> ## BALANCE
> 
> **Is the power level appropriate for the mana cost and rarity?**
> 
> Let's benchmark:
> 
> - **Elvish Visionary** *(1G, 1/1, draws a card on ETB — common, Magic 2013 etc.)*: Cantrip on entry, 1/1 body. Considered a clean, efficient common.
> - **Llanowar Elves / Quirion Ranger** style 1/1s for G: These trade raw stats for utility.
> - **Winding Way / similar 2-mana G dig spells**: Winding Way (1G) digs 4 for one type. Salvage 3 is strictly weaker (only looks at 3, only finds artifacts), and here it's stapled to a 2/1 body with a *death trigger* rather than an ETB.
> 
> **Assessment:**
> The body (2/1 for 1G) is aggressively statted — essentially a **Grizzly Bears** for one less mana, which is already above rate in green for 2 mana. The death trigger adds a meaningful but conditional upside. The key question is how often you reliably trigger it.
> 
> At common, this card compares reasonably well. A 2/1 for {1}{G} is French vanilla-playable on its own in a set with an artifact theme (where Salvage has targets). The death trigger is:
> - **Less reliable** than an ETB (must die, not just enter)
> - **Conditional on finding artifacts** in the top 3 (deck-dependent)
> - **Narrower** than straight card draw (artifact cards only)
> 
> That said, **this may be slightly pushed for common** in aggressive shell. A 2/1 for 1G is already a strong rate (compare *Kird Ape* requiring a condition, or *Experiment One* as a 1/1 that grows). In a set context where:
> - Artifact synergies are plentiful (making Salvage live)
> - Combat is common (the creature will die)
> 
> ...the trigger will fire often enough to generate real value. I'd flag this as *borderline* but likely acceptable given the artifact restriction and death-trigger unreliability. If the set has lots of self-sacrifice or recursion, revisit.
> 
> **Verdict: PASS with a note.** Watch for synergy abuse with sacrifice outlets. If those exist at common, this becomes potentially too efficient.
> 
> ---
> 
> ## DESIGN
> 
> **Does the card have a focused purpose?**
> PASS. The card has a clear, cohesive identity: an aggressive early creature that rewards you for trading in combat by digging for artifact resources. This is a classic "value creature" archetype, and both halves (the body, the death trigger) serve the same game plan — get in early, trade, recoup value.
> 
> **Is variability real?**
> PASS. Salvage 3 is genuinely variable — the top 3 cards may or may not contain an artifact, and even if they do, the choice of whether to take it is meaningful. The number of cards seen (3) is fixed per the mechanic's scaling rules (appropriately uncommon territory... wait — see below).
> 
> **Does the card create interesting gameplay decisions?**
> PASS. Yes, though modestly. It encourages sequencing decisions (attack into blockers vs. holding back), and Salvage 3 creates mild choices about which card to take and how to order the rest. These are appropriate for common-level complexity.
> 
> ---
> 
> ## COLOR PIE
> 
> **Are all abilities appropriate for the card's color(s)?**
> 
> The card is Green. Let's check:
> 
> - **2/1 creature body**: PASS. Green has efficient creatures; a 2/1 for 1G is well within green's color pie.
> - **Death trigger**: PASS. Green has death triggers (e.g., Llanowar Elves variants, Rishkar's Expertise lineage, Winding Constrictor family). Green caring about creatures dying to generate value is on-pie.
> - **Salvage (artifact tutoring/digging)**: PASS per the set's own rules — Salvage is defined as a White/Blue/Green mechanic, so Green access is intentional and sanctioned.
> 
> No color pie violations.
> 
> ---
> 
> ## ADDITIONAL FLAGS
> 
> **⚠️ Salvage 3 at Common — Scaling Check**
> Per the set's own design rules: *Salvage scales as 2–3 at common, 4–5 at uncommon, 6+ at rare/mythic.* Salvage 3 is within the allowable common range. **PASS** — but this is at the top of the common range (3), which is worth noting. Ensure other common Salvage cards don't also all cluster at Salvage 3, which would make the lower end (Salvage 2) feel underpowered by comparison.
> 
> **⚠️ Flavor Text — Minor Concern**
> The flavor text is evocative and well-written. However, "The wilderness, unfortunately, knew her too" slightly implies danger or death found *her*, which works thematically with the death trigger. This is a soft PASS — it's atmospheric, fits the set's tone ("Anomalous Descent" implies something ominous), and the connection to the death trigger gives it mechanical resonance. Good flavor work.
> 
> **⚠️ Artifact Theme Dependency**
> Salvage is only valuable if the deck (and set) have meaningful artifact cards to find. If the set's artifact density is low, or if Green in particular doesn't interact heavily with artifacts, the death trigger will frequently whiff (finding no artifacts in the top 3). This isn't a card design flaw per se, but a **set-level design dependency** worth flagging for the lead designer. Ensure Green has enough artifact payoffs or artifacts in its color section to make Salvage feel rewarding rather than blank.
> 
> ---
> 
> ## SUMMARY TABLE
> 
> | Criterion | Result |
> |---|---|
> | Valid oracle text | ✅ PASS |
> | Reminder text present | ❌ FAIL — Salvage 3 missing reminder text |
> | Capitalization | ✅ PASS |
> | Current templating ("dies") | ✅ PASS |
> | Keyword conflicts | ✅ PASS |
> | Conditional validity | ✅ PASS |
> | Balance for cost/rarity | ✅ PASS (borderline, monitor) |
> | Focused design | ✅ PASS |
> | Real variability | ✅ PASS |
> | Interesting decisions | ✅ PASS |
> | Color pie | ✅ PASS |
> | Salvage scaling within rules | ✅ PASS |
> 
> **Primary fix required:** Add Salvage reminder text. Everything else is solid. This is a clean, functional common with good flavor and appropriate set-level integration.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Salvage 3 is missing reminder text. At common, reminder text is expected on every instance of a custom mechanic."
  ],
  "name": "Undergrowth Scrounger",
  "mana_cost": "{1}{G}",
  "type_line": "Creature \u2014 Human Scout",
  "oracle_text": "When ~ dies, salvage 3. *(Look at the top 3 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*",
  "rarity": "common",
  "power": "2",
  "toughness": "1",
  "flavor_text": "She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too."
}
```

*Tokens: 3055 in / 328 out — $0.0141*

## C) Revised Card

```json
{
  "name": "Undergrowth Scrounger",
  "mana_cost": "{1}{G}",
  "type_line": "Creature \u2014 Human Scout",
  "oracle_text": "When ~ dies, salvage 3. *(Look at the top 3 cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*",
  "rarity": "common",
  "power": "2",
  "toughness": "1",
  "flavor_text": "She knew every rust-eaten ruin in the wilderness. The wilderness, unfortunately, knew her too."
}
```

**Changes made:**
- Salvage 3 is missing reminder text. At common, reminder text is expected on every instance of a custom mechanic.

## D) Cost

- API calls: 2
- Input tokens: 3826
- Output tokens: 2334
- Cost: $0.0465