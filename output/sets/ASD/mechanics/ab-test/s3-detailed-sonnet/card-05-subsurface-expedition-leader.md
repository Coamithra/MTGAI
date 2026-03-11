# Card 5: Subsurface Expedition Leader — Strategy: s3-detailed-sonnet

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
> # Subsurface Expedition Leader — Review
> 
> ---
> 
> ## TEMPLATING & RULES TEXT
> 
> **Valid Oracle Text:** PASS
> All abilities are grammatically correct and mechanically sound. The "Activate only as a sorcery" rider on the activated ability is correctly templated (this is standard phrasing, see Kyodai, Soul of Kamigawa; Ajani's Pridemate variants, etc.).
> 
> **Reminder Text on First Use of Custom Mechanics:** FAIL
> Salvage 6 on the enters trigger is the first instance of the keyword on this card, and no reminder text is present. Per the set's own design conventions, reminder text should appear on the first use. The activated ability's Salvage 3 would not need it again on the same card, but the ETB instance does.
> 
> **Capitalization:** PASS
> "Salvage" is correctly capitalized at the start of each ability line. No mid-sentence capitalization errors detected.
> 
> **Modern Templating ("enters" not "enters the battlefield"):** PASS
> "When ~ enters, salvage 6." uses current post-2023 templating correctly.
> 
> ---
> 
> ## KEYWORD INTERACTIONS
> 
> **Keywords Negating Each Other:** PASS
> There are no conflicting keywords here. The card has no malfunction, no haste, no vigilance — nothing that creates internal contradiction.
> 
> **Conditional That Can't Be False:** PASS
> No conditional triggers or requirements are present. "Activate only as a sorcery" is a restriction, not a condition with a truth value — it simply limits timing and is always meaningful.
> 
> **One Interaction Worth Flagging — Sorcery Speed Restriction:**
> The restriction is appropriate and intentional, but worth noting explicitly: because Salvage already instructs you to look at the top X cards and put the rest on the bottom in any order, there is no instant-speed abuse case being closed off that wouldn't already exist. The sorcery restriction here is almost certainly present to prevent repeated activated library manipulation at instant speed (e.g., in response to a shuffle effect to reorder your library, or to rifle for answers at end of opponent's turn). This is a reasonable precaution and the templating is correct. PASS, but the design justification is sound.
> 
> ---
> 
> ## BALANCE
> 
> **Power Level Assessment:**
> 
> Let's benchmark this card:
> 
> | Card | Cost | Body | Effect |
> |---|---|---|---|
> | Militia Bugler | {2}{W} | 2/3 | Look at top 4, take a creature with power 2 or less |
> | Loran of the Third Path | {2}{W} | 2/3 | ETB draw + activated draw, multiple abilities |
> | Ranger-Captain of Eos | {2}{W} | 3/3 | ETB tutor for a 1-drop creature |
> | Subsurface Expedition Leader | {2}{W}{W} | 3/4 | ETB salvage 6, activated salvage 3 |
> 
> **ETB Ability (Salvage 6):** Looking at 6 cards to find an artifact is a powerful but conditional draw effect — it finds nothing if there are no artifacts in the top 6. At rare, Salvage 6 is within the scaling guidelines (6+ at rare/mythic). Comparable to Lae'zel's Acrobatics in scope of card selection. The condition (must be an artifact) meaningfully limits it.
> 
> **Body:** 3/4 for {2}{W}{W} is exactly on-rate — this is a French vanilla body at this cost (compare Siege Rhino is {1}{W}{B}{G} for 4/5 with abilities; 3/4 for four mana is solid but not exceptional).
> 
> **Activated Ability:** {2}{W} + tap + sorcery speed for Salvage 3 is a reasonably costed repeatable artifact tutor. Three mana + tap for looking at 3 is not broken — it will often whiff in a deck that isn't artifact-dense — but it adds meaningful late-game utility.
> 
> **Combined Assessment:** PASS, with a note. The combination of a strong ETB and a repeatable activated ability on an above-rate body for four mana is quite powerful in artifact-focused decks. However, both abilities are *conditional* (must find an artifact), which naturally self-regulates: in a non-artifact-heavy deck, this card is mediocre. In an artifact-heavy deck, it's excellent but not format-warping. This is appropriate for rare. The card does NOT have malfunction, so the above-rate body/ability combination isn't justified by a built-in drawback — worth monitoring in development, but within acceptable rare range.
> 
> ---
> 
> ## DESIGN
> 
> **Focused Purpose vs. Kitchen Sink:** PASS
> The card has a clear, unified identity: artifact tutor/engine piece. Both abilities do the same thing (Salvage) at different scales. This is not kitchen sink design — it's coherent vertical repetition, like how many creatures have an ETB effect and an activated version of the same effect (see Skullclamp-adjacent designs, Elspeth Tirel, etc.).
> 
> **Variability:** PASS
> Salvage 6 and Salvage 3 are genuinely variable: the effect depends on the density of artifacts in your library, the depth at which they're buried, and how many remain. This is real variability, not illusory variability. Both abilities can whiff meaningfully.
> 
> **Interesting Gameplay Decisions:** PASS, and this is a genuine strength of the card.
> - Do you activate immediately to dig for an artifact, or wait to see what you draw naturally?
> - Do you bottom specific non-artifact cards you've already seen via other effects?
> - In limited, deck construction decisions about artifact density are directly rewarded.
> - The sorcery restriction on the activated ability creates a "plan ahead" texture — you can't hold up the activation as a bluff.
> 
> **One Minor Design Note:** The ETB Salvage 6 is strictly more powerful than the activated Salvage 3 in raw lookup depth. It might be worth considering whether the activated ability should be Salvage 4 or 5 to feel more impactful as a repeatable effect, since Salvage 3 at {2}{W}+tap+sorcery will occasionally feel like a lot of investment for only 3 cards deep. This is a development note rather than a design error.
> 
> ---
> 
> ## COLOR PIE
> 
> **White having Salvage:** PASS
> Per the set's custom mechanic documentation, Salvage is explicitly listed as a White mechanic (W, U, G). White in the context of this set clearly has artifact-matters overlap, which is a reasonable extension of White's existing artifact affinity (White has historically had artifact recursion, artifact tutoring in certain set contexts, e.g., Theros artifact subthemes, Mirrodin block).
> 
> **Human Soldier subtype:** PASS
> White is the primary color of Human Soldiers and has been throughout Magic's history.
> 
> **No off-color abilities:** PASS
> There is nothing on this card that bleeds into Blue, Red, Black, or Green's exclusive territory. Artifact synergy in White is established within this set's design space.
> 
> ---
> 
> ## ADDITIONAL FLAGS
> 
> **1. Reminder Text — Priority Fix**
> As noted above, the ETB "salvage 6" needs reminder text. At rare, reminder text is sometimes omitted on paper for space, but since this is the *only* instance of the keyword on the card that a new player would see first, it should be present. Recommended addition:
> 
> > When ~ enters, salvage 6. *(Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*
> 
> **2. Flavor Text Consistency Check**
> The flavor text is strong and characterful — it fits a "someone keeps dying on these expeditions" tone well. The humor is dry and appropriate for a Soldier leader archetype. No issues.
> 
> **3. Rarity Alignment with Salvage Scaling**
> Salvage 6 on an ETB is correctly placed at rare per the scaling guidelines (6+ at rare/mythic). The activated Salvage 3 at rare is also fine — Salvage 3 would be uncommon as a standalone but is acceptable as a secondary ability at rare. PASS.
> 
> **4. Tap Symbol Availability**
> The card has no vigilance, no malfunction (which enters tapped), and no other ability that would prevent it from tapping. The activated {T} ability is fully accessible from the turn after it enters (or the same turn with haste enablers). No issues.
> 
> ---
> 
> ## SUMMARY TABLE
> 
> | Criterion | Result |
> |---|---|
> | Valid Oracle Text | ✅ PASS |
> | Reminder Text on First Use | ❌ FAIL — Salvage 6 ETB needs reminder text |
> | Capitalization | ✅ PASS |
> | Modern Templating | ✅ PASS |
> | Keyword Conflicts | ✅ PASS |
> | Conditional Always True/False | ✅ PASS |
> | Balance for Cost & Rarity | ✅ PASS (monitor in development) |
> | Focused Design | ✅ PASS |
> | Real Variability | ✅ PASS |
> | Interesting Decisions | ✅ PASS |
> | Color Pie | ✅ PASS |
> 
> **Overall:** One clear fix needed (reminder text). The card is well-designed, cohesive, appropriately rare, and creates genuine gameplay texture. The development team should watch it in artifact-dense limited environments, but it is not an obvious power outlier.

*Tokens: 798 in / 2248 out — $0.0361*

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
> # Subsurface Expedition Leader — Review
> 
> ---
> 
> ## TEMPLATING & RULES TEXT
> 
> **Valid Oracle Text:** PASS
> All abilities are grammatically correct and mechanically sound. The "Activate only as a sorcery" rider on the activated ability is correctly templated (this is standard phrasing, see Kyodai, Soul of Kamigawa; Ajani's Pridemate variants, etc.).
> 
> **Reminder Text on First Use of Custom Mechanics:** FAIL
> Salvage 6 on the enters trigger is the first instance of the keyword on this card, and no reminder text is present. Per the set's own design conventions, reminder text should appear on the first use. The activated ability's Salvage 3 would not need it again on the same card, but the ETB instance does.
> 
> **Capitalization:** PASS
> "Salvage" is correctly capitalized at the start of each ability line. No mid-sentence capitalization errors detected.
> 
> **Modern Templating ("enters" not "enters the battlefield"):** PASS
> "When ~ enters, salvage 6." uses current post-2023 templating correctly.
> 
> ---
> 
> ## KEYWORD INTERACTIONS
> 
> **Keywords Negating Each Other:** PASS
> There are no conflicting keywords here. The card has no malfunction, no haste, no vigilance — nothing that creates internal contradiction.
> 
> **Conditional That Can't Be False:** PASS
> No conditional triggers or requirements are present. "Activate only as a sorcery" is a restriction, not a condition with a truth value — it simply limits timing and is always meaningful.
> 
> **One Interaction Worth Flagging — Sorcery Speed Restriction:**
> The restriction is appropriate and intentional, but worth noting explicitly: because Salvage already instructs you to look at the top X cards and put the rest on the bottom in any order, there is no instant-speed abuse case being closed off that wouldn't already exist. The sorcery restriction here is almost certainly present to prevent repeated activated library manipulation at instant speed (e.g., in response to a shuffle effect to reorder your library, or to rifle for answers at end of opponent's turn). This is a reasonable precaution and the templating is correct. PASS, but the design justification is sound.
> 
> ---
> 
> ## BALANCE
> 
> **Power Level Assessment:**
> 
> Let's benchmark this card:
> 
> | Card | Cost | Body | Effect |
> |---|---|---|---|
> | Militia Bugler | {2}{W} | 2/3 | Look at top 4, take a creature with power 2 or less |
> | Loran of the Third Path | {2}{W} | 2/3 | ETB draw + activated draw, multiple abilities |
> | Ranger-Captain of Eos | {2}{W} | 3/3 | ETB tutor for a 1-drop creature |
> | Subsurface Expedition Leader | {2}{W}{W} | 3/4 | ETB salvage 6, activated salvage 3 |
> 
> **ETB Ability (Salvage 6):** Looking at 6 cards to find an artifact is a powerful but conditional draw effect — it finds nothing if there are no artifacts in the top 6. At rare, Salvage 6 is within the scaling guidelines (6+ at rare/mythic). Comparable to Lae'zel's Acrobatics in scope of card selection. The condition (must be an artifact) meaningfully limits it.
> 
> **Body:** 3/4 for {2}{W}{W} is exactly on-rate — this is a French vanilla body at this cost (compare Siege Rhino is {1}{W}{B}{G} for 4/5 with abilities; 3/4 for four mana is solid but not exceptional).
> 
> **Activated Ability:** {2}{W} + tap + sorcery speed for Salvage 3 is a reasonably costed repeatable artifact tutor. Three mana + tap for looking at 3 is not broken — it will often whiff in a deck that isn't artifact-dense — but it adds meaningful late-game utility.
> 
> **Combined Assessment:** PASS, with a note. The combination of a strong ETB and a repeatable activated ability on an above-rate body for four mana is quite powerful in artifact-focused decks. However, both abilities are *conditional* (must find an artifact), which naturally self-regulates: in a non-artifact-heavy deck, this card is mediocre. In an artifact-heavy deck, it's excellent but not format-warping. This is appropriate for rare. The card does NOT have malfunction, so the above-rate body/ability combination isn't justified by a built-in drawback — worth monitoring in development, but within acceptable rare range.
> 
> ---
> 
> ## DESIGN
> 
> **Focused Purpose vs. Kitchen Sink:** PASS
> The card has a clear, unified identity: artifact tutor/engine piece. Both abilities do the same thing (Salvage) at different scales. This is not kitchen sink design — it's coherent vertical repetition, like how many creatures have an ETB effect and an activated version of the same effect (see Skullclamp-adjacent designs, Elspeth Tirel, etc.).
> 
> **Variability:** PASS
> Salvage 6 and Salvage 3 are genuinely variable: the effect depends on the density of artifacts in your library, the depth at which they're buried, and how many remain. This is real variability, not illusory variability. Both abilities can whiff meaningfully.
> 
> **Interesting Gameplay Decisions:** PASS, and this is a genuine strength of the card.
> - Do you activate immediately to dig for an artifact, or wait to see what you draw naturally?
> - Do you bottom specific non-artifact cards you've already seen via other effects?
> - In limited, deck construction decisions about artifact density are directly rewarded.
> - The sorcery restriction on the activated ability creates a "plan ahead" texture — you can't hold up the activation as a bluff.
> 
> **One Minor Design Note:** The ETB Salvage 6 is strictly more powerful than the activated Salvage 3 in raw lookup depth. It might be worth considering whether the activated ability should be Salvage 4 or 5 to feel more impactful as a repeatable effect, since Salvage 3 at {2}{W}+tap+sorcery will occasionally feel like a lot of investment for only 3 cards deep. This is a development note rather than a design error.
> 
> ---
> 
> ## COLOR PIE
> 
> **White having Salvage:** PASS
> Per the set's custom mechanic documentation, Salvage is explicitly listed as a White mechanic (W, U, G). White in the context of this set clearly has artifact-matters overlap, which is a reasonable extension of White's existing artifact affinity (White has historically had artifact recursion, artifact tutoring in certain set contexts, e.g., Theros artifact subthemes, Mirrodin block).
> 
> **Human Soldier subtype:** PASS
> White is the primary color of Human Soldiers and has been throughout Magic's history.
> 
> **No off-color abilities:** PASS
> There is nothing on this card that bleeds into Blue, Red, Black, or Green's exclusive territory. Artifact synergy in White is established within this set's design space.
> 
> ---
> 
> ## ADDITIONAL FLAGS
> 
> **1. Reminder Text — Priority Fix**
> As noted above, the ETB "salvage 6" needs reminder text. At rare, reminder text is sometimes omitted on paper for space, but since this is the *only* instance of the keyword on the card that a new player would see first, it should be present. Recommended addition:
> 
> > When ~ enters, salvage 6. *(Look at the top six cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)*
> 
> **2. Flavor Text Consistency Check**
> The flavor text is strong and characterful — it fits a "someone keeps dying on these expeditions" tone well. The humor is dry and appropriate for a Soldier leader archetype. No issues.
> 
> **3. Rarity Alignment with Salvage Scaling**
> Salvage 6 on an ETB is correctly placed at rare per the scaling guidelines (6+ at rare/mythic). The activated Salvage 3 at rare is also fine — Salvage 3 would be uncommon as a standalone but is acceptable as a secondary ability at rare. PASS.
> 
> **4. Tap Symbol Availability**
> The card has no vigilance, no malfunction (which enters tapped), and no other ability that would prevent it from tapping. The activated {T} ability is fully accessible from the turn after it enters (or the same turn with haste enablers). No issues.
> 
> ---
> 
> ## SUMMARY TABLE
> 
> | Criterion | Result |
> |---|---|
> | Valid Oracle Text | ✅ PASS |
> | Reminder Text on First Use | ❌ FAIL — Salvage 6 ETB needs reminder text |
> | Capitalization | ✅ PASS |
> | Modern Templating | ✅ PASS |
> | Keyword Conflicts | ✅ PASS |
> | Conditional Always True/False | ✅ PASS |
> | Balance for Cost & Rarity | ✅ PASS (monitor in development) |
> | Focused Design | ✅ PASS |
> | Real Variability | ✅ PASS |
> | Interesting Decisions | ✅ PASS |
> | Color Pie | ✅ PASS |
> 
> **Overall:** One clear fix needed (reminder text). The card is well-designed, cohesive, appropriately rare, and creates genuine gameplay texture. The development team should watch it in artifact-dense limited environments, but it is not an obvious power outlier.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Missing reminder text on first use of the Salvage keyword (ETB ability). Reminder text should appear on the first instance of a custom mechanic on a card."
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

*Tokens: 3324 in / 359 out — $0.0154*

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
- Missing reminder text on first use of the Salvage keyword (ETB ability). Reminder text should appear on the first instance of a custom mechanic on a card.

## D) Cost

- API calls: 2
- Input tokens: 4122
- Output tokens: 2607
- Cost: $0.0515