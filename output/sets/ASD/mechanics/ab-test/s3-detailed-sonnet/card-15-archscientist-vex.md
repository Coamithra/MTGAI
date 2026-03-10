# Card 15: Archscientist Vex, the Unbound — Strategy: s3-detailed-sonnet

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
  "type_line": "Legendary Creature \u00ef\u00bf\u00bd Human Scientist",
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
> Type: Legendary Creature ï¿½ Human Scientist
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
> ## Templating & Rules Text
> 
> **ISSUE**: The oracle text has several templating problems:
> 
> 1. **Reminder text placement**: The overclock reminder text is embedded mid-ability rather than following standard reminder text conventions. It should be: "Cards exiled with overclock cost {2} less to cast. *(Overclock — Exile the top three cards of your library. You may play them until end of turn.)*"
> 
> 2. **Capitalization**: "overclock" should be capitalized as "Overclock" when referring to the keyword ability name.
> 
> 3. **Current templating**: The card correctly uses "enters" templating.
> 
> 4. **Rules validity**: The abilities are rules-valid but awkwardly templated.
> 
> ## Keyword Interactions
> 
> **PASS**: No problematic keyword interactions. Flying works normally, and the overclock-related abilities create synergy rather than conflict.
> 
> The conditional "whenever you cast a spell exiled with overclock" can be false during normal play (if you don't overclock or don't cast the exiled spells), which is appropriate design.
> 
> ## Balance
> 
> **ISSUE**: This card appears undercosted for its power level at mythic rarity.
> 
> Comparing to similar cards:
> - **Kess, Dissident Mage** (1UBR): 3/4 flying, lets you cast instants/sorceries from graveyard once per turn
> - **Narset, Enlightened Master** (3URW): 3/2 first strike, hexproof, attacks trigger exiles 4 and casts noncreatures for free
> - **Melek, Izzet Paragon** (4UR): 2/4, cast instants/sorceries from library top, copy if instant/sorcery
> 
> At 2UR, this card provides:
> 1. A 3/4 flying body (worth ~3.5 mana)
> 2. Cost reduction engine for exiled spells
> 3. Copy effect for exiled spells
> 
> This is significantly above the power curve. Should likely cost 3UR or 2UUR.
> 
> ## Design
> 
> **PASS**: The card has a focused purpose around the overclock mechanic. It's not kitchen sink design - both abilities specifically interact with overclock, creating a cohesive build-around commander.
> 
> The cost reduction creates meaningful decisions about which exiled spells to cast, and the copy effect provides additional value scaling. The variability is real since overclock results depend on what's exiled.
> 
> ## Color Pie
> 
> **PASS**: All abilities are appropriate for Izzet (UR):
> - **Flying**: Blue gets flying
> - **Cost reduction**: Both colors get cost reduction effects
> - **Copying spells**: Red's primary wheel house, blue secondary
> - **Impulse draw/exile play**: Red's domain, blue gets some access
> 
> The "Unbound" scientist flavor fits the color combination's themes of experimentation and breaking rules.
> 
> ## Additional Issues
> 
> **Legendary Rule Concern**: As written, this creates a very powerful engine that could be problematic in Commander format where it's always accessible. The combination of cost reduction + copying every overclock spell is potentially oppressive.
> 
> **Complexity**: While overclock is marked as complexity 3 (uncommon+), this card adds additional layers that might push it beyond appropriate complexity even for mythic.
> 
> ## Recommendation
> 
> Increase mana cost to 3UR or 2UUR, and fix the templating issues. Consider whether both the cost reduction AND copying are necessary, or if one effect would be sufficient for a more balanced design.

*Tokens: 835 in / 807 out — $0.0146*

### Step 2: Submit revised card based on review

**Prompt sent:**
> Based on the following review of a card, submit the revised card. If no issues were found, return the card unchanged with verdict OK.
> 
> Original card:
> Name: Archscientist Vex, the Unbound
> Mana Cost: {2}{U}{R}
> Type: Legendary Creature ï¿½ Human Scientist
> Rarity: mythic
> Oracle Text: Flying
> Cards exiled with overclock (exile the top three cards of your library, you may play them until end of turn) cost {2} less to cast.
> Whenever you cast a spell exiled with overclock, copy it. You may choose new targets for the copy.
> P/T: 3/4
> Flavor Text: "I have transcended the limitations of sanity, safety, and the laws of thermodynamics."
> 
> Review findings:
> ## Templating & Rules Text
> 
> **ISSUE**: The oracle text has several templating problems:
> 
> 1. **Reminder text placement**: The overclock reminder text is embedded mid-ability rather than following standard reminder text conventions. It should be: "Cards exiled with overclock cost {2} less to cast. *(Overclock — Exile the top three cards of your library. You may play them until end of turn.)*"
> 
> 2. **Capitalization**: "overclock" should be capitalized as "Overclock" when referring to the keyword ability name.
> 
> 3. **Current templating**: The card correctly uses "enters" templating.
> 
> 4. **Rules validity**: The abilities are rules-valid but awkwardly templated.
> 
> ## Keyword Interactions
> 
> **PASS**: No problematic keyword interactions. Flying works normally, and the overclock-related abilities create synergy rather than conflict.
> 
> The conditional "whenever you cast a spell exiled with overclock" can be false during normal play (if you don't overclock or don't cast the exiled spells), which is appropriate design.
> 
> ## Balance
> 
> **ISSUE**: This card appears undercosted for its power level at mythic rarity.
> 
> Comparing to similar cards:
> - **Kess, Dissident Mage** (1UBR): 3/4 flying, lets you cast instants/sorceries from graveyard once per turn
> - **Narset, Enlightened Master** (3URW): 3/2 first strike, hexproof, attacks trigger exiles 4 and casts noncreatures for free
> - **Melek, Izzet Paragon** (4UR): 2/4, cast instants/sorceries from library top, copy if instant/sorcery
> 
> At 2UR, this card provides:
> 1. A 3/4 flying body (worth ~3.5 mana)
> 2. Cost reduction engine for exiled spells
> 3. Copy effect for exiled spells
> 
> This is significantly above the power curve. Should likely cost 3UR or 2UUR.
> 
> ## Design
> 
> **PASS**: The card has a focused purpose around the overclock mechanic. It's not kitchen sink design - both abilities specifically interact with overclock, creating a cohesive build-around commander.
> 
> The cost reduction creates meaningful decisions about which exiled spells to cast, and the copy effect provides additional value scaling. The variability is real since overclock results depend on what's exiled.
> 
> ## Color Pie
> 
> **PASS**: All abilities are appropriate for Izzet (UR):
> - **Flying**: Blue gets flying
> - **Cost reduction**: Both colors get cost reduction effects
> - **Copying spells**: Red's primary wheel house, blue secondary
> - **Impulse draw/exile play**: Red's domain, blue gets some access
> 
> The "Unbound" scientist flavor fits the color combination's themes of experimentation and breaking rules.
> 
> ## Additional Issues
> 
> **Legendary Rule Concern**: As written, this creates a very powerful engine that could be problematic in Commander format where it's always accessible. The combination of cost reduction + copying every overclock spell is potentially oppressive.
> 
> **Complexity**: While overclock is marked as complexity 3 (uncommon+), this card adds additional layers that might push it beyond appropriate complexity even for mythic.
> 
> ## Recommendation
> 
> Increase mana cost to 3UR or 2UUR, and fix the templating issues. Consider whether both the cost reduction AND copying are necessary, or if one effect would be sufficient for a more balanced design.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Reminder text placement - overclock reminder text embedded mid-ability instead of following standard conventions",
    "Capitalization - 'overclock' should be capitalized as 'Overclock' when referring to keyword ability",
    "Balance - card appears undercosted at 2UR for its power level, should cost 3UR or 2UUR"
  ],
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{3}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Flying\nCards exiled with Overclock cost {2} less to cast. (Overclock \u2014 Exile the top three cards of your library. You may play them until end of turn.)\nWhenever you cast a spell exiled with Overclock, copy it. You may choose new targets for the copy.",
  "power": "3",
  "toughness": "4",
  "rarity": "mythic",
  "flavor_text": "I have transcended the limitations of sanity, safety, and the laws of thermodynamics."
}
```

*Tokens: 1647 in / 404 out — $0.0110*

## C) Revised Card

```json
{
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{3}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Flying\nCards exiled with Overclock cost {2} less to cast. (Overclock \u2014 Exile the top three cards of your library. You may play them until end of turn.)\nWhenever you cast a spell exiled with Overclock, copy it. You may choose new targets for the copy.",
  "rarity": "mythic",
  "power": "3",
  "toughness": "4",
  "flavor_text": "I have transcended the limitations of sanity, safety, and the laws of thermodynamics."
}
```

**Changes made:**
- Reminder text placement - overclock reminder text embedded mid-ability instead of following standard conventions
- Capitalization - 'overclock' should be capitalized as 'Overclock' when referring to keyword ability
- Balance - card appears undercosted at 2UR for its power level, should cost 3UR or 2UUR

## D) Cost

- API calls: 2
- Input tokens: 2482
- Output tokens: 1211
- Cost: $0.0256