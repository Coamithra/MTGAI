# Card 5: Subsurface Expedition Leader — Strategy: s7-detailed-opus

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
> Name: Subsurface Expedition Leader
> Mana Cost: {2}{W}{W}
> Type: Creature â€” Human Soldier
> Rarity: rare
> Oracle Text: When ~ enters, salvage 6.
> {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> P/T: 3/4
> Flavor Text: "Every expedition needs someone willing to go first into the dark. The job has remarkably high turnover."
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
> # Card Review: Subsurface Expedition Leader
> 
> ## Templating & Rules Text
> 
> **Oracle text validity:** PASS. "When ~ enters" is a valid triggered ability template. The activated ability with a tap cost, mana cost, and sorcery-speed restriction is correctly formatted.
> 
> **Reminder text on first use:** ISSUE. Salvage is a custom set mechanic appearing here at rare. The first instance ("salvage 6") should include the reminder text for salvage. Even at rare, custom mechanics need reminder text on at least the first use on the card. The second instance can omit it. This should read:
> 
> > When ~ enters, salvage 6. *(Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*
> > {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> 
> **Capitalization:** PASS. "Salvage" appears mid-sentence in both cases and is correctly lowercased (it's a keyword action, functioning like "scry" — lowercase in running text).
> 
> **Current templating:** PASS. Uses "enters" not "enters the battlefield." "Activate only as a sorcery" is current templating.
> 
> ---
> 
> ## Keyword Interactions
> 
> **Negated or useless abilities:** PASS. No conflicting keywords. The ETB trigger and the activated ability serve complementary but distinct roles without contradiction.
> 
> **Conditional feasibility:** PASS. No conditionals present. Both abilities function straightforwardly.
> 
> ---
> 
> ## Balance
> 
> **Power level assessment:** MODERATE CONCERN.
> 
> At 4 mana for a 3/4 body, the baseline is already reasonable — comparable to cards like **Rumor Gatherer** (3/1 for {1}{W}{W}) or **Palace Jailer** (2/2 for {2}{W}{W} with monarch). The body is solid.
> 
> The ETB salvage 6 at rare is within the stated scaling (6+ at rare). This is a deep dig that will very reliably find an artifact in any deck that cares about artifacts. Essentially this reads "tutor an artifact to hand" in a dedicated deck, stapled to a body.
> 
> The repeatable salvage 3 activation is where this gets strong. Even at sorcery speed with a tap requirement, a repeatable card-selection/card-advantage engine on a reasonably-statted creature is significant. The total cost per activation (4 mana creature + 3 mana activation) is gated enough, but in longer games this generates substantial advantage.
> 
> Compared to **Recruiter of the Guard** (1/1 for {1}{W}{W}, tutors a creature) or **Ranger-Captain of Eos** (3/3 for {1}{W}{W}, tutors a CMC ≤1 creature), this is in a similar space — a body plus artifact-specific tutoring — but the repeatability pushes it. I'd call this at the upper boundary of acceptable for rare. It's powerful but probably fine given the sorcery restriction and the inherent limitation that salvage only finds artifacts.
> 
> ---
> 
> ## Design
> 
> **Focused purpose:** PASS. The card has a clear, singular identity: artifact-finding expedition leader. Both abilities serve the same mechanical theme (salvage) at different scales, which feels cohesive and intentional.
> 
> **Variability:** PASS. While salvage has inherent variance (you might whiff), the two different salvage values (6 vs. 3) create meaningfully different hit rates, making the distinction real rather than cosmetic.
> 
> **Interesting gameplay decisions:** PASS. Do you tap to salvage or attack with your 3/4? Do you deploy this when you need a specific artifact now (ETB) or hold it for a turn where you can also activate? Good tension.
> 
> ---
> 
> ## Color Pie
> 
> **Color appropriateness:** PASS. White is a listed salvage color. White gets 3/4 bodies at four mana routinely. White gets artifact synergies (historically strong in white). Sorcery-speed activated abilities with tap costs are universal.
> 
> ---
> 
> ## Additional Notes
> 
> **Flavor text:** Excellent. Darkly humorous and fits the "descent into dangerous territory" set theme perfectly.
> 
> **One minor flag:** Two salvage triggers on one card means a lot of library manipulation per turn cycle in practice. In Limited, this could create pace-of-play concerns with repeated looking/reordering. The sorcery restriction helps, but worth noting for play design.
> 
> ---
> 
> ## Summary
> 
> **Overall: STRONG DESIGN, MINOR TEMPLATING FIX NEEDED.** Add reminder text to the first salvage instance. The card is well-focused, flavorful, and appropriately powered for rare, sitting at the top end of the power band without crossing into problematic territory. The sorcery-speed restriction on the activated ability is smart gating.

*Tokens: 797 in / 1133 out — $0.0323*

### Step 2: Submit revised card based on review

**Prompt sent:**
> Based on the following review of a card, submit the revised card. If no issues were found, return the card unchanged with verdict OK.
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
> Review findings:
> # Card Review: Subsurface Expedition Leader
> 
> ## Templating & Rules Text
> 
> **Oracle text validity:** PASS. "When ~ enters" is a valid triggered ability template. The activated ability with a tap cost, mana cost, and sorcery-speed restriction is correctly formatted.
> 
> **Reminder text on first use:** ISSUE. Salvage is a custom set mechanic appearing here at rare. The first instance ("salvage 6") should include the reminder text for salvage. Even at rare, custom mechanics need reminder text on at least the first use on the card. The second instance can omit it. This should read:
> 
> > When ~ enters, salvage 6. *(Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*
> > {2}{W}, {T}: Salvage 3. Activate only as a sorcery.
> 
> **Capitalization:** PASS. "Salvage" appears mid-sentence in both cases and is correctly lowercased (it's a keyword action, functioning like "scry" — lowercase in running text).
> 
> **Current templating:** PASS. Uses "enters" not "enters the battlefield." "Activate only as a sorcery" is current templating.
> 
> ---
> 
> ## Keyword Interactions
> 
> **Negated or useless abilities:** PASS. No conflicting keywords. The ETB trigger and the activated ability serve complementary but distinct roles without contradiction.
> 
> **Conditional feasibility:** PASS. No conditionals present. Both abilities function straightforwardly.
> 
> ---
> 
> ## Balance
> 
> **Power level assessment:** MODERATE CONCERN.
> 
> At 4 mana for a 3/4 body, the baseline is already reasonable — comparable to cards like **Rumor Gatherer** (3/1 for {1}{W}{W}) or **Palace Jailer** (2/2 for {2}{W}{W} with monarch). The body is solid.
> 
> The ETB salvage 6 at rare is within the stated scaling (6+ at rare). This is a deep dig that will very reliably find an artifact in any deck that cares about artifacts. Essentially this reads "tutor an artifact to hand" in a dedicated deck, stapled to a body.
> 
> The repeatable salvage 3 activation is where this gets strong. Even at sorcery speed with a tap requirement, a repeatable card-selection/card-advantage engine on a reasonably-statted creature is significant. The total cost per activation (4 mana creature + 3 mana activation) is gated enough, but in longer games this generates substantial advantage.
> 
> Compared to **Recruiter of the Guard** (1/1 for {1}{W}{W}, tutors a creature) or **Ranger-Captain of Eos** (3/3 for {1}{W}{W}, tutors a CMC ≤1 creature), this is in a similar space — a body plus artifact-specific tutoring — but the repeatability pushes it. I'd call this at the upper boundary of acceptable for rare. It's powerful but probably fine given the sorcery restriction and the inherent limitation that salvage only finds artifacts.
> 
> ---
> 
> ## Design
> 
> **Focused purpose:** PASS. The card has a clear, singular identity: artifact-finding expedition leader. Both abilities serve the same mechanical theme (salvage) at different scales, which feels cohesive and intentional.
> 
> **Variability:** PASS. While salvage has inherent variance (you might whiff), the two different salvage values (6 vs. 3) create meaningfully different hit rates, making the distinction real rather than cosmetic.
> 
> **Interesting gameplay decisions:** PASS. Do you tap to salvage or attack with your 3/4? Do you deploy this when you need a specific artifact now (ETB) or hold it for a turn where you can also activate? Good tension.
> 
> ---
> 
> ## Color Pie
> 
> **Color appropriateness:** PASS. White is a listed salvage color. White gets 3/4 bodies at four mana routinely. White gets artifact synergies (historically strong in white). Sorcery-speed activated abilities with tap costs are universal.
> 
> ---
> 
> ## Additional Notes
> 
> **Flavor text:** Excellent. Darkly humorous and fits the "descent into dangerous territory" set theme perfectly.
> 
> **One minor flag:** Two salvage triggers on one card means a lot of library manipulation per turn cycle in practice. In Limited, this could create pace-of-play concerns with repeated looking/reordering. The sorcery restriction helps, but worth noting for play design.
> 
> ---
> 
> ## Summary
> 
> **Overall: STRONG DESIGN, MINOR TEMPLATING FIX NEEDED.** Add reminder text to the first salvage instance. The card is well-focused, flavorful, and appropriately powered for rare, sitting at the top end of the power band without crossing into problematic territory. The sorcery-speed restriction on the activated ability is smart gating.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Missing reminder text for salvage on first use. Custom set mechanic 'salvage' should include reminder text on its first instance on the card."
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

*Tokens: 2208 in / 355 out — $0.0199*

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
- Missing reminder text for salvage on first use. Custom set mechanic 'salvage' should include reminder text on its first instance on the card.

## D) Cost

- API calls: 2
- Input tokens: 3005
- Output tokens: 1488
- Cost: $0.0522