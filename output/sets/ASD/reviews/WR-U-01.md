# Review: WR-U-01 — Rebel Firebrand

- **Rarity:** uncommon
- **Tier:** single
- **Model:** claude-haiku-4-5-20251001
- **Verdict:** OK
- **Changed:** no
- **Cost:** $0.0053
- **Tokens:** 3,009 in / 726 out
- **Latency:** 8.7s
- **Timestamp:** 2026-03-14T12:32:03.174693+00:00

## Original Card

> Name: Rebel Firebrand
> Mana Cost: {1}{W}{R}
> Type: Creature — Human Rebel
> Rarity: uncommon
> Oracle Text: Malfunction 2 (This permanent enters tapped with two malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.)\n{1}: Remove a malfunction counter from ~.
> Flavor Text: The Fist guns can't aim if their hands are burned off.
> P/T: 3/2
> Design Notes: WR signpost uncommon for Spark Rebellion archetype. Malfunction 2 provides a significant tempo cost (enters tapped, two-turn clock to be active), justified by aggressive stats (3/2). The activated ability {1} to remove malfunction counters allows interactive play: you can choose to pay mana to accelerate the card's usefulness, or hold up mana for combat tricks. This creates decision-making and rewards tempo planning. The modest mana cost means it can come down turn 2 and be active by turn 4, fitting WR's aggressive tempo play. Flavor reflects the rebel underdog nature and pyromaniac style. Stats fit common power budget: 3+2=5, CMC 3, so P+T = CMC+2, well within acceptable range."
> Validation Warnings (from auto-validator):
>   - Line 1: "This permanent" should use "~" or "this" only in specific MTG contexts
>   - Oracle text contains what looks like reminder text: "(This permanent enters tapped with two malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.)"

## Review Iterations

### Iteration 1

**Verdict:** OK (0 issues)  
**Cost:** $0.0053 (3,009 in / 726 out)  
**Latency:** 8.7s  
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

Name: Rebel Firebrand
Mana Cost: {1}{W}{R}
Type: Creature — Human Rebel
Rarity: uncommon
Oracle Text: Malfunction 2 (This permanent enters tapped with two malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.)\n{1}: Remove a malfunction counter from ~.
Flavor Text: The Fist guns can't aim if their hands are burned off.
P/T: 3/2
Design Notes: WR signpost uncommon for Spark Rebellion archetype. Malfunction 2 provides a significant tempo cost (enters tapped, two-turn clock to be active), justified by aggressive stats (3/2). The activated ability {1} to remove malfunction counters allows interactive play: you can choose to pay mana to accelerate the card's usefulness, or hold up mana for combat tricks. This creates decision-making and rewards tempo planning. The modest mana cost means it can come down turn 2 and be active by turn 4, fitting WR's aggressive tempo play. Flavor reflects the rebel underdog nature and pyromaniac style. Stats fit common power budget: 3+2=5, CMC 3, so P+T = CMC+2, well within acceptable range."
Validation Warnings (from auto-validator):
  - Line 1: "This permanent" should use "~" or "this" only in specific MTG contexts
  - Oracle text contains what looks like reminder text: "(This permanent enters tapped with two malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.)"

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

Rebel Firebrand is a well-designed uncommon signpost for the WR Spark Rebellion archetype. The card uses the Malfunction keyword as a tempo cost that's justified by its aggressive 3/2 stats and focused mechanical purpose.

**Templating & Mechanics:**
The oracle text correctly uses the Malfunction 2 keyword with proper reminder text on first appearance. The activated ability {1}: Remove a malfunction counter from ~ is a standard MTG construction. No templating issues present.

**Keyword Interaction:**
The reminder text for Malfunction correctly identifies the "enters tapped" clause. This is NOT a nonbo because Malfunction's entire design purpose is to represent the delayed tempo cost—the creature enters tapped and locked down for 1-2 turns, then activates via counter removal. This is intentional and central to the card's role in the archetype.

**Reminder Text:**
This is the first appearance of the Malfunction keyword in the card, and the complete reminder text is properly included. The validation warning about "This permanent" vs "~" is a false positive—the custom mechanic uses the standard MTG wording for enter-the-battlefield effects and is correct as-is.

**Balance:**
At uncommon, Rebel Firebrand costs {1}{W}{R} = 3 mana for a 3/2 creature. The cost to activate and remove malfunction counters is {1} each, which is reasonable. The card is intentionally above rate in terms of raw stats (3+2 = 5 vs CMC 3), but this is explicitly justified by the Malfunction drawback as noted in design notes. The two-turn clock to full activation rewards setup planning and fits WR's tempo identity.

Comparable cards: Stoneforge Mystic is {1}{W} for a 1/2 with a tutor, making it much stronger. Anafenza, Kin-Tree Spirit is {1}{W}{G} for a 0/3 that's noncombat-focused. At the uncommon 3-mana aggressive creature slot, this card is fairly positioned—above rate due to malfunction being the expressed drawback.

**Design Quality:**
The card has a focused, single purpose: aggressive tempo play with controlled malfunction removal. No kitchen sink effects. The activated ability creates meaningful decision-making (pay {1} to accelerate removal of malfunction counters or hold mana for interaction), which aligns well with the archetype's interactive play pattern.

**Color Pie:**
WR is appropriate for a Human Rebel with direct damage flavor (pyromaniac). White gets tempo/delay effects and artifact synergy; Red gets aggressive creatures and direct damage flavor. No color pie violations.

**Flavor:**
The flavor text "The Fist guns can't aim if their hands are burned off" effectively grounds the Malfunction mechanic in world narrative and supports the post-apocalyptic setting.
