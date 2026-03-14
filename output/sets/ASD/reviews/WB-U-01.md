# Review: WB-U-01 — Fist Tax Collector

- **Rarity:** uncommon
- **Tier:** single
- **Model:** claude-haiku-4-5-20251001
- **Verdict:** OK
- **Changed:** no
- **Cost:** $0.0052
- **Tokens:** 2,906 in / 710 out
- **Latency:** 9.0s
- **Timestamp:** 2026-03-14T12:30:47.609470+00:00

## Original Card

> Name: Fist Tax Collector
> Mana Cost: {W}{B}
> Type: Creature -- Human Advisor
> Rarity: uncommon
> Oracle Text: Whenever another creature you control dies, each opponent loses 1 life and you gain 1 life.
> Flavor Text: "The Vizier requires a contribution from every citizen. The dead are no exception."
> P/T: 2/1
> Design Notes: WB signpost uncommon for the Vizier's Regime archetype. A 2/1 for 2 is clean at uncommon. The death-trigger drain effect is the core payoff for the sacrifice-and-taxation theme -- it rewards you for trading creatures, tokens dying in combat, or deliberate sacrifice outlets. White gets lifegain, black gets life drain, and both colors care about creatures dying. The effect is incremental rather than explosive, giving the archetype inevitability without being oppressive. Pairs naturally with token generators like Edict of Continuity and sacrifice outlets like Koyl Yrenum. P+T of 3 at CMC 2 is within budget, and the 2/1 stat line makes it fragile enough that opponents can answer it before it accumulates too much value.

## Review Iterations

### Iteration 1

**Verdict:** OK (0 issues)  
**Cost:** $0.0052 (2,906 in / 710 out)  
**Latency:** 9.0s  
**Model:** claude-haiku-4-5-20251001

<details>
<summary>Prompt</summary>

## Custom Mechanics

### Salvage
- Type: keyword_ability
- Reminder text: (Look at the top X cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)
- Colors: White, Blue, Green
- Complexity: 1
- Appears at: common, uncommon, rare, mythic
- Design notes: Primary mechanic for the set. Complexity 1 makes it common-viable. X scaling: 2-3 at common, 4-5 at uncommon, 6+ at rare/mythic. Supports the artifact subtheme by filtering for artifacts. Does NOT tutor (unlike the original candidate) -- it looks at top X, reducing variance and keeping common versions simple. Renamed from 'Scavenge' to 'Salvage' to avoid collision with the existing MTG keyword 'Scavenge' from Return to Ravnica (which exiles creatures from graveyards to put +1/+1 counters on targets).

### Malfunction
- Type: keyword_ability
- Reminder text: (This permanent enters tapped with N malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.)
- Colors: White, Blue, Red
- Complexity: 2
- Appears at: common, uncommon, rare, mythic
- Design notes: Secondary mechanic. N scaling: 1 at common, 2 at uncommon, 2-3 at rare/mythic. Enters tapped is the key tempo cost. Overlaps well with WR (Spark Rebellion) and WU (Ancient Technology) draft archetypes. The colorless artifact slot (X-C-01) is a natural fit. Counter removal creates interesting interactions with the Cult of Science (UR) archetype.

### Overclock
- Type: keyword_action
- Reminder text: (Exile the top three cards of your library. You may play them until end of turn.)
- Colors: Blue, Red, Black
- Complexity: 3
- Appears at: uncommon, rare, mythic
- Design notes: Tertiary mechanic, rare+ only (complexity 3). Should NOT appear at common. This is a renamed/retuned version of the candidate 'Overload' to avoid collision with the existing MTG keyword 'Overload' from Return to Ravnica. High risk/reward: exiling 3 cards is significant, but playing them until end of turn is powerful. Fits UR (Mad Science) and UB (Deep Descent) archetypes. BR (Raider Warbands) can splash into it for explosive turns.


---

## Card to Review

Name: Fist Tax Collector
Mana Cost: {W}{B}
Type: Creature -- Human Advisor
Rarity: uncommon
Oracle Text: Whenever another creature you control dies, each opponent loses 1 life and you gain 1 life.
Flavor Text: "The Vizier requires a contribution from every citizen. The dead are no exception."
P/T: 2/1
Design Notes: WB signpost uncommon for the Vizier's Regime archetype. A 2/1 for 2 is clean at uncommon. The death-trigger drain effect is the core payoff for the sacrifice-and-taxation theme -- it rewards you for trading creatures, tokens dying in combat, or deliberate sacrifice outlets. White gets lifegain, black gets life drain, and both colors care about creatures dying. The effect is incremental rather than explosive, giving the archetype inevitability without being oppressive. Pairs naturally with token generators like Edict of Continuity and sacrifice outlets like Koyl Yrenum. P+T of 3 at CMC 2 is within budget, and the 2/1 stat line makes it fragile enough that opponents can answer it before it accumulates too much value.

---

## Review Checklist

List any issues with templating, mechanics, balance, design, or color pie.

Additionally, consider these specific questions:

1. Does this card have any keywords that are negated or made useless by other abilities on the card? For example, haste on a creature that always enters tapped, or flying on a creature with defender that doesn't care about it.
2. Is reminder text present for all custom mechanics (Salvage, Malfunction, Overclock)? The FIRST time each custom mechanic keyword appears in the oracle text, it should be followed by reminder text in parentheses. Only flag if there is genuinely NO reminder text at all for a custom mechanic's first use.
3. If this card has a conditional ('if you X this turn'), is that conditional actually meaningful -- can the condition ever be false when the card is played normally? For instance, if overclock is a mandatory additional cost, then 'if you overclocked this turn' is always true and therefore redundant.
4. Is the power level appropriate for its mana cost and rarity? Compare to well-known MTG cards at the same cost. Flag anything that seems significantly above or below rate. Exception: Malfunction cards are intentionally above-rate because the delay IS the drawback.
5. Does this card try to do too many unrelated things (kitchen sink design)? A good card has a focused purpose; a kitchen sink card piles on 3+ unrelated effects.
6. If this card has variable damage or variable effects based on a count, is the variability real or does it always resolve to the same fixed value? For example, 'deal 2 damage for each card exiled' where the exile count is always fixed at 6 means the damage is always 12.
7. Do any mechanic names on this card collide with existing MTG keywords? Specifically: 'Scavenge' is an existing MTG keyword from Return to Ravnica (2012). 'Overload' is an existing keyword from the same set. Our mechanics are Salvage, Malfunction, and Overclock.
8. Does this card have 'enters tapped' or similar effects that are irrelevant for the card type? For example, a noncreature artifact with no tap abilities entering tapped has no mechanical impact.

If the card is good as-is, verdict is OK with an empty issues list. If the card needs changes, verdict is REVISE and provide the complete revised card with ALL fields.

</details>

**Analysis:**

Fist Tax Collector is a well-designed WB signpost uncommon for the Vizier's Regime archetype. The card exemplifies focused design: a simple stat line (2/1 body for WW/B at uncommon) paired with a singular, synergistic death-trigger drain effect.

**Mechanics & Color Pie:**
The oracle text is correctly templated for modern MTG: "Whenever another creature you control dies, each opponent loses 1 life and you gain 1 life." This reads cleanly and follows the standard trigger pattern. White gets lifegain (a core color identity), black gets life drain (also core), and both colors have deep mechanical ties to creatures dying. This is solidly on-pie.

**Balance:**
At {W}{B} for a 2/1, the stat line is appropriate for uncommon. Two power and one toughness total 3 points, which is the standard budget for a 2-mana creature at this rarity. The creature is fragile—it dies to most early blockers or direct removal—which balances the incremental value it generates. The drain itself is not explosive; it triggers once per death event and generates 1 life drain at a time. This is not oppressive, and it requires setup (having other creatures in play and causing them to die). The payoff is incremental inevitability, which is thematically appropriate for a "Vizier's Regime" economy.

Comparable cards: Zulaport Cutthroat (a death-trigger life drain creature at uncommon from various sets) costs {1}{B} and has a 1/1 body, but it triggers on any creature death (yours or opponents'). Fist Tax Collector is {W}{B} (slightly more expensive) but has a 2/1 body and only triggers on *your* creatures dying (more restrictive). This is reasonable and slightly above Zulaport's rate due to the body, but the restriction balances it. No red flags.

**Design Quality:**
This card has a singular, focused purpose: serve as a payoff for the sacrifice-and-death subtheme in the WB signpost archetype. It does not try to do multiple unrelated things. The design note correctly identifies synergies (token generators, sacrifice outlets), which is exactly what a signpost uncommon should facilitate.

**Custom Mechanics:**
The card does not use Salvage, Malfunction, or Overclock keywords, so no reminder text is required.

**Keyword Negation:**
No keywords present, and the creature's fragility (1 toughness) is not negated by any ability—it's a real vulnerability that matters.

**No Issues Detected:**
The card is correctly templated, appropriately costed for its rarity, focused in design, on-pie for its colors, and well-balanced. No revisions needed.
