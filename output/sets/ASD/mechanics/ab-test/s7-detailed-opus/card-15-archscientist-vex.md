# Card 15: Archscientist Vex, the Unbound — Strategy: s7-detailed-opus

## A) Original Card

```json
{
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "cmc": 4,
  "colors": [
    "U",
    "R"
  ],
  "type_line": "Legendary Creature \u00e2\u20ac\u201d Human Scientist",
  "oracle_text": "Flying\nCards exiled with overclock (exile the top three cards of your library, you may play them until end of turn) cost {2} less to cast.\nWhenever you cast a spell exiled with overclock, copy it. You may choose new targets for the copy.",
  "power": "3",
  "toughness": "4",
  "rarity": "mythic",
  "keywords": [
    "Flying",
    "Overclock"
  ],
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
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
> Name: Archscientist Vex, the Unbound
> Mana Cost: {2}{U}{R}
> Type: Legendary Creature â€” Human Scientist
> Rarity: mythic
> Oracle Text: Flying
> Cards exiled with overclock (exile the top three cards of your library, you may play them until end of turn) cost {2} less to cast.
> Whenever you cast a spell exiled with overclock, copy it. You may choose new targets for the copy.
> P/T: 3/4
> Flavor Text: "I have transcended the limitations of sanity, safety, and the laws of thermodynamics."
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
> # Card Review: Archscientist Vex, the Unbound
> 
> ## Templating & Rules Text
> 
> **Oracle text validity:** ISSUE — The card has a significant templating problem. Overclock is defined as a keyword *action* (something you actively do), but the card never actually instructs you to perform it. The text "Cards exiled with overclock" references the results of overclocking, but there's no ability that says "Overclock" as an action. Compare to how a card like Prosper, Tome-Bound works: it has a triggered ability that exiles cards, then a separate ability that triggers off playing them. Vex needs an activated or triggered ability that says something like "At the beginning of your upkeep, overclock" or "{T}: Overclock." As written, the cost reduction and copy abilities are dead text because no overclock ever happens from this card alone. The card is essentially a 3/4 flyer for 4 that does nothing else unless you have *other* overclock cards — which is a bizarre mythic design. This needs a fundamental restructure.
> 
> **Reminder text on first use:** PASS — Overclock has reminder text on its first appearance in the oracle text.
> 
> **Capitalization:** ISSUE — "overclock" in the second ability ("Whenever you cast a spell exiled with overclock") should maintain consistent formatting. More critically, the reminder text is parenthetical inside the first ability in a way that's extremely awkward to parse. The reminder text for the keyword action should appear after the ability that *performs* the overclock, not embedded in a static ability that references its results.
> 
> **Current templating:** PASS — No "enters the battlefield" issues present.
> 
> ## Keyword Interactions
> 
> **Negated/useless keywords:** PASS — Flying is independently useful and not contradicted.
> 
> **Conditional abilities:** ISSUE — As discussed above, the condition "exiled with overclock" can *never be true* from this card's own abilities. If the intent is to synergize with other overclock cards in the deck, this is a build-around payoff, not a self-contained mythic legend. This needs to be flagged either way.
> 
> ## Balance
> 
> **Power level assessment:** CRITICAL ISSUE — If we assume the card is redesigned to actually grant overclock (e.g., "At the beginning of combat on your turn, overclock"), the combination of {2} cost reduction AND copying every spell cast from exile is *extremely* pushed. Let's compare:
> 
> - **Mizzix of the Izmagnus** (4 mana UR legend): Cost reduction that builds gradually and requires setup.
> - **Double Vision** (5 mana, enchantment): Copies first instant/sorcery per turn, once only.
> - **Prosper, Tome-Bound** (4 mana): Exiles one card per turn, generates one treasure — modest incremental value.
> 
> Vex would overclock (3 cards exiled), reduce their costs by {2} each, AND copy every single one. That's potentially casting 3 spells at massive discounts with free copies in a single turn — six effective spells. This is a repeatable, game-ending engine at 4 mana on a body with evasion. Even at mythic, this is far beyond rate. The copy ability should at minimum be limited to "the first spell you cast from exile each turn" or the cost reduction should be removed entirely.
> 
> **3/4 flying body:** The stats alone are reasonable for {2}{U}{R}, which makes the suite of abilities feel like pure upside stapled onto an already-playable creature.
> 
> ## Design
> 
> **Focused purpose vs. kitchen sink:** ISSUE — The card has four distinct elements: flying, cost reduction for overclock, copying overclock spells, and (implicitly needed) an overclock source. The cost reduction and copying are thematically linked but mechanically they stack into a degenerate combo rather than creating tension. There's no interesting decision point — you always overclock, you always cast everything you can, and everything gets copied. There is no reason to *not* do any of these things.
> 
> **Gameplay decisions:** ISSUE — The card lacks meaningful tension. Compare to Prosper, where you must decide whether to play the exiled card or your hand cards. Here, cost reduction actively removes the tension overclock is supposed to create (risk of losing cards you can't afford).
> 
> ## Color Pie
> 
> **Flying:** PASS — Appropriate for U/R.
> **Cost reduction:** PASS — Blue and red both get cost reduction.
> **Copying spells:** PASS — Core red/blue (Izzet) territory.
> **Overclock (impulse draw):** PASS — U/R per design notes.
> 
> ## Summary
> 
> **This card needs a redesign.** The two most critical issues are: (1) it never actually performs overclock, making most of its text non-functional in isolation, and (2) if it did overclock, the combination of cost reduction plus unconditional copying on a repeatable engine creates a power level far exceeding mythic norms at four mana. I'd recommend adding a triggered overclock ability, removing the cost reduction, and limiting the copy to once per turn.

*Tokens: 832 in / 1179 out — $0.0336*

### Step 2: Submit revised card based on review

**Prompt sent:**
> Based on the following review of a card, submit the revised card. If no issues were found, return the card unchanged with verdict OK.
> 
> Original card:
> Name: Archscientist Vex, the Unbound
> Mana Cost: {2}{U}{R}
> Type: Legendary Creature â€” Human Scientist
> Rarity: mythic
> Oracle Text: Flying
> Cards exiled with overclock (exile the top three cards of your library, you may play them until end of turn) cost {2} less to cast.
> Whenever you cast a spell exiled with overclock, copy it. You may choose new targets for the copy.
> P/T: 3/4
> Flavor Text: "I have transcended the limitations of sanity, safety, and the laws of thermodynamics."
> 
> Review findings:
> # Card Review: Archscientist Vex, the Unbound
> 
> ## Templating & Rules Text
> 
> **Oracle text validity:** ISSUE — The card has a significant templating problem. Overclock is defined as a keyword *action* (something you actively do), but the card never actually instructs you to perform it. The text "Cards exiled with overclock" references the results of overclocking, but there's no ability that says "Overclock" as an action. Compare to how a card like Prosper, Tome-Bound works: it has a triggered ability that exiles cards, then a separate ability that triggers off playing them. Vex needs an activated or triggered ability that says something like "At the beginning of your upkeep, overclock" or "{T}: Overclock." As written, the cost reduction and copy abilities are dead text because no overclock ever happens from this card alone. The card is essentially a 3/4 flyer for 4 that does nothing else unless you have *other* overclock cards — which is a bizarre mythic design. This needs a fundamental restructure.
> 
> **Reminder text on first use:** PASS — Overclock has reminder text on its first appearance in the oracle text.
> 
> **Capitalization:** ISSUE — "overclock" in the second ability ("Whenever you cast a spell exiled with overclock") should maintain consistent formatting. More critically, the reminder text is parenthetical inside the first ability in a way that's extremely awkward to parse. The reminder text for the keyword action should appear after the ability that *performs* the overclock, not embedded in a static ability that references its results.
> 
> **Current templating:** PASS — No "enters the battlefield" issues present.
> 
> ## Keyword Interactions
> 
> **Negated/useless keywords:** PASS — Flying is independently useful and not contradicted.
> 
> **Conditional abilities:** ISSUE — As discussed above, the condition "exiled with overclock" can *never be true* from this card's own abilities. If the intent is to synergize with other overclock cards in the deck, this is a build-around payoff, not a self-contained mythic legend. This needs to be flagged either way.
> 
> ## Balance
> 
> **Power level assessment:** CRITICAL ISSUE — If we assume the card is redesigned to actually grant overclock (e.g., "At the beginning of combat on your turn, overclock"), the combination of {2} cost reduction AND copying every spell cast from exile is *extremely* pushed. Let's compare:
> 
> - **Mizzix of the Izmagnus** (4 mana UR legend): Cost reduction that builds gradually and requires setup.
> - **Double Vision** (5 mana, enchantment): Copies first instant/sorcery per turn, once only.
> - **Prosper, Tome-Bound** (4 mana): Exiles one card per turn, generates one treasure — modest incremental value.
> 
> Vex would overclock (3 cards exiled), reduce their costs by {2} each, AND copy every single one. That's potentially casting 3 spells at massive discounts with free copies in a single turn — six effective spells. This is a repeatable, game-ending engine at 4 mana on a body with evasion. Even at mythic, this is far beyond rate. The copy ability should at minimum be limited to "the first spell you cast from exile each turn" or the cost reduction should be removed entirely.
> 
> **3/4 flying body:** The stats alone are reasonable for {2}{U}{R}, which makes the suite of abilities feel like pure upside stapled onto an already-playable creature.
> 
> ## Design
> 
> **Focused purpose vs. kitchen sink:** ISSUE — The card has four distinct elements: flying, cost reduction for overclock, copying overclock spells, and (implicitly needed) an overclock source. The cost reduction and copying are thematically linked but mechanically they stack into a degenerate combo rather than creating tension. There's no interesting decision point — you always overclock, you always cast everything you can, and everything gets copied. There is no reason to *not* do any of these things.
> 
> **Gameplay decisions:** ISSUE — The card lacks meaningful tension. Compare to Prosper, where you must decide whether to play the exiled card or your hand cards. Here, cost reduction actively removes the tension overclock is supposed to create (risk of losing cards you can't afford).
> 
> ## Color Pie
> 
> **Flying:** PASS — Appropriate for U/R.
> **Cost reduction:** PASS — Blue and red both get cost reduction.
> **Copying spells:** PASS — Core red/blue (Izzet) territory.
> **Overclock (impulse draw):** PASS — U/R per design notes.
> 
> ## Summary
> 
> **This card needs a redesign.** The two most critical issues are: (1) it never actually performs overclock, making most of its text non-functional in isolation, and (2) if it did overclock, the combination of cost reduction plus unconditional copying on a repeatable engine creates a power level far exceeding mythic norms at four mana. I'd recommend adding a triggered overclock ability, removing the cost reduction, and limiting the copy to once per turn.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Overclock is defined as a keyword action but the card never instructs you to perform it \u2014 no triggered or activated ability says 'overclock', making the cost reduction and copy abilities dead text in isolation.",
    "Reminder text for overclock is awkwardly embedded inside a static ability rather than after the ability that performs the overclock action.",
    "If overclock were added, the combination of {2} cost reduction AND unconditional copying of every spell cast from exile is extremely pushed for 4 mana \u2014 far beyond rate even at mythic.",
    "Card lacks meaningful gameplay tension: cost reduction removes the risk/reward inherent in overclock's temporary exile, and there's no decision point since you always want to cast and copy everything."
  ],
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Flying\nAt the beginning of combat on your turn, overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nWhenever you cast the first spell each turn from among cards you own in exile, copy it. You may choose new targets for the copy.",
  "rarity": "mythic",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
}
```

*Tokens: 2288 in / 480 out — $0.0234*

## C) Revised Card

```json
{
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Flying\nAt the beginning of combat on your turn, overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nWhenever you cast the first spell each turn from among cards you own in exile, copy it. You may choose new targets for the copy.",
  "rarity": "mythic",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
}
```

**Changes made:**
- Overclock is defined as a keyword action but the card never instructs you to perform it — no triggered or activated ability says 'overclock', making the cost reduction and copy abilities dead text in isolation.
- Reminder text for overclock is awkwardly embedded inside a static ability rather than after the ability that performs the overclock action.
- If overclock were added, the combination of {2} cost reduction AND unconditional copying of every spell cast from exile is extremely pushed for 4 mana — far beyond rate even at mythic.
- Card lacks meaningful gameplay tension: cost reduction removes the risk/reward inherent in overclock's temporary exile, and there's no decision point since you always want to cast and copy everything.

## D) Cost

- API calls: 2
- Input tokens: 3120
- Output tokens: 1659
- Cost: $0.0571