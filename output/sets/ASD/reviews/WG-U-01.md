# Review: WG-U-01 — Reclaimed Settler

- **Rarity:** uncommon
- **Tier:** single
- **Model:** claude-haiku-4-5-20251001
- **Verdict:** OK
- **Changed:** no
- **Cost:** $0.0057
- **Tokens:** 2,811 in / 866 out
- **Latency:** 10.9s
- **Timestamp:** 2026-03-14T12:31:23.081723+00:00

## Original Card

> Name: Reclaimed Settler
> Mana Cost: {W}{G}
> Type: Creature — Human Settler
> Rarity: uncommon
> Oracle Text: When ~ enters, salvage 4. (Look at the top four cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)\nWhenever you create a token, put a +1/+1 counter on ~.
> Flavor Text: The best tools are the ones you find buried. The best settlers are the ones who know how to use 'em.
> P/T: 1/1
> Design Notes: WG signpost uncommon for the Frontier Settlers archetype. Salvage 4 on entry provides artifact tutor-like utility while filtering the top of library — supports both the artifact subtheme and WG's interest in finding ramp/mana artifacts. The body starts as a 1/1 (compliant with CMC+3 rule at uncommon), but grows via the +1/+1 counter trigger whenever the player creates tokens. This synergy signals the archetype's go-wide strategy and provides a payoff for the token-generation cards in the format (Edict of Continuity, Proclamation Enforcer, Kethra, etc.). The card rewards playing the WG game plan and scales naturally in limited while remaining focused and clean.
> Validation Warnings (from auto-validator):
>   - Oracle text contains what looks like reminder text: "(Look at the top four cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"

## Review Iterations

### Iteration 1

**Verdict:** OK (0 issues)  
**Cost:** $0.0057 (2,811 in / 866 out)  
**Latency:** 10.9s  
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


---

## Card to Review

Name: Reclaimed Settler
Mana Cost: {W}{G}
Type: Creature — Human Settler
Rarity: uncommon
Oracle Text: When ~ enters, salvage 4. (Look at the top four cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)\nWhenever you create a token, put a +1/+1 counter on ~.
Flavor Text: The best tools are the ones you find buried. The best settlers are the ones who know how to use 'em.
P/T: 1/1
Design Notes: WG signpost uncommon for the Frontier Settlers archetype. Salvage 4 on entry provides artifact tutor-like utility while filtering the top of library — supports both the artifact subtheme and WG's interest in finding ramp/mana artifacts. The body starts as a 1/1 (compliant with CMC+3 rule at uncommon), but grows via the +1/+1 counter trigger whenever the player creates tokens. This synergy signals the archetype's go-wide strategy and provides a payoff for the token-generation cards in the format (Edict of Continuity, Proclamation Enforcer, Kethra, etc.). The card rewards playing the WG game plan and scales naturally in limited while remaining focused and clean.
Validation Warnings (from auto-validator):
  - Oracle text contains what looks like reminder text: "(Look at the top four cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"

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


Reclaimed Settler is a well-designed WG signpost uncommon that effectively communicates its archetype's identity and strategy.

**Templating & Mechanics:**
The oracle text is correct. Salvage 4 appears with full reminder text on its first use, which is appropriate since Salvage is a custom mechanic new to the set. The reminder text is properly formatted in parentheses and accurately describes the ability. The templating follows modern conventions: "When ~ enters, salvage 4" correctly uses the creature token as the subject, and "Whenever you create a token, put a +1/+1 counter on ~" is standard incremental growth language.

**Balance:**
At {W}{G} for a 1/1 with two abilities, this is appropriately costed for uncommon. The initial 1/1 body is small and complies with the CMC+3 power guideline (2 CMC + 3 ≈ 5 power/toughness potential, and this starts at 1). The power level is comparable to other archetype signposts: the Salvage 4 effect provides real value by fixing the top of the library and tutoring for artifacts (a smoothing effect rather than a tutor), while the token trigger creates meaningful scaling within the WG token-focused strategy. Neither ability is undercosted, and the combination isn't oppressive—it requires both building around tokens (which is the WG game plan) AND playing artifact payoffs. This feels like a genuine uncommon payoff card.

**Design Quality:**
The card has a focused, coherent purpose: reward WG's token strategy while providing access to artifacts from the library. It signals the archetype without trying to do unrelated things. The Salvage trigger on entry ties directly into the artifact subtheme and provides early filtering, while the token counter trigger ties into the go-wide strategy. Both mechanics push players toward the same game plan—this is intentional synergy, not kitchen sink design.

**Color Pie:**
{W}{G} is correct for this card. White has creature token generation (Proclamation Enforcer, Edict of Continuity) and +1/+1 counter mechanics. Green has artifact tutor effects (Salvage fits here, searching for mana rocks) and token payoffs. This is solidly in pie for both colors.

**Keyword Interactions:**
No keywords are negated or made useless. Salvage is a reasonable static ability that doesn't conflict with the token counter trigger. Both abilities are relevant and encourage the same play pattern.

**Custom Mechanic Reminder Text:**
Salvage appears with full, accurate reminder text on its first appearance. This is correct and necessary.

**Conditional Logic:**
The token trigger is not a conditional in the redundant sense—"whenever you create a token" is a meaningful condition that will be false in games where tokens aren't created. The card encourages specific play patterns (token generation) rather than being an always-on effect.

**Real Variability:**
The Salvage effect has real variability in what artifacts you find in the top 4 cards, and how you arrange the non-artifact cards on the bottom. The token counter trigger depends on how many tokens the player generates during the game. Both are genuinely variable.

**Summary:**
This is a clean, well-executed signpost uncommon that does exactly what it should: communicate the WG archetype's strategy, reward the player for playing tokens, and provide artifact tutoring within the framework of library filtering. The card is balanced, templated correctly, and shows good design sense.

