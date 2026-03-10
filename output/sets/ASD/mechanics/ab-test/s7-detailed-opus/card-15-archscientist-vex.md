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
> ## Card Review: Archscientist Vex, the Unbound
> 
> ### Templating & Rules Text:
> **ISSUE** - The overclock reminder text needs proper punctuation and capitalization. It should read: "(Exile the top three cards of your library. You may play them until end of turn.)" with a period after "turn" and capital "E" at the start.
> 
> **ISSUE** - The cost reduction ability needs clearer templating. Current Oracle text would be: "Spells you cast from among cards exiled with overclock cost {2} less to cast." The current wording "Cards exiled with overclock" is ambiguous about when the cost reduction applies.
> 
> **PASS** - Capitalization is otherwise consistent
> **PASS** - Uses current templating standards
> 
> ### Keyword Interactions:
> **PASS** - Flying works independently of other abilities
> **PASS** - No conflicting or negated keywords present
> **PASS** - The overclock trigger condition can naturally be false (when you're not casting from overclock exile)
> 
> ### Balance:
> **CONCERNING** - This is extremely powerful for 4 mana at mythic. Let me compare:
> 
> - **Feather, the Redeemed** (1RW, 3/4 flying) - Similar stats but provides card advantage differently
> - **Niv-Mizzet, Parun** (UUURRR, 5/5 flying) - More expensive but similar "value engine" role
> - **Arclight Phoenix** (3R, 3/2 flying haste) - Less immediate impact
> 
> Vex provides:
> 1. Efficient 3/4 flying body for 4 mana
> 2. Cost reduction on overclocked spells (effectively ramping 2 mana per spell)
> 3. Free copies of every overclocked spell
> 
> This is likely too strong. Playing 3 spells from overclock with Vex out generates 6 mana of discount AND 3 free spell copies. This seems above the power level of most 4-mana mythics.
> 
> ### Design:
> **PASS** - Has a focused purpose: overclock synergy commander
> **PASS** - Creates interesting decisions about when to overclock and sequencing
> **MINOR ISSUE** - The combination of cost reduction AND copying might be one effect too many for clean gameplay
> 
> ### Color Pie:
> **PASS** - Flying is primary in blue
> **PASS** - Cost reduction is primary in blue
> **PASS** - Copying spells is primary in blue/red
> **PASS** - The overclock synergy fits the UR spellslinger identity
> 
> ### Additional Notes:
> 1. This card essentially demands you build around overclock, which is good for a mythic legendary
> 2. The memory issues of tracking which exiled cards get the discount could be problematic in paper
> 3. Consider if both the cost reduction AND copying are necessary - one might be sufficient for an exciting build-around
> 
> ### Recommendation:
> The card needs templating fixes and is likely too powerful. Consider either:
> - Removing the cost reduction and keeping just the copy effect
> - Increasing the mana cost to {3}{U}{R} 
> - Making the copy effect triggered only once per turn

*Tokens: 835 in / 733 out — $0.0675*

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
> ## Card Review: Archscientist Vex, the Unbound
> 
> ### Templating & Rules Text:
> **ISSUE** - The overclock reminder text needs proper punctuation and capitalization. It should read: "(Exile the top three cards of your library. You may play them until end of turn.)" with a period after "turn" and capital "E" at the start.
> 
> **ISSUE** - The cost reduction ability needs clearer templating. Current Oracle text would be: "Spells you cast from among cards exiled with overclock cost {2} less to cast." The current wording "Cards exiled with overclock" is ambiguous about when the cost reduction applies.
> 
> **PASS** - Capitalization is otherwise consistent
> **PASS** - Uses current templating standards
> 
> ### Keyword Interactions:
> **PASS** - Flying works independently of other abilities
> **PASS** - No conflicting or negated keywords present
> **PASS** - The overclock trigger condition can naturally be false (when you're not casting from overclock exile)
> 
> ### Balance:
> **CONCERNING** - This is extremely powerful for 4 mana at mythic. Let me compare:
> 
> - **Feather, the Redeemed** (1RW, 3/4 flying) - Similar stats but provides card advantage differently
> - **Niv-Mizzet, Parun** (UUURRR, 5/5 flying) - More expensive but similar "value engine" role
> - **Arclight Phoenix** (3R, 3/2 flying haste) - Less immediate impact
> 
> Vex provides:
> 1. Efficient 3/4 flying body for 4 mana
> 2. Cost reduction on overclocked spells (effectively ramping 2 mana per spell)
> 3. Free copies of every overclocked spell
> 
> This is likely too strong. Playing 3 spells from overclock with Vex out generates 6 mana of discount AND 3 free spell copies. This seems above the power level of most 4-mana mythics.
> 
> ### Design:
> **PASS** - Has a focused purpose: overclock synergy commander
> **PASS** - Creates interesting decisions about when to overclock and sequencing
> **MINOR ISSUE** - The combination of cost reduction AND copying might be one effect too many for clean gameplay
> 
> ### Color Pie:
> **PASS** - Flying is primary in blue
> **PASS** - Cost reduction is primary in blue
> **PASS** - Copying spells is primary in blue/red
> **PASS** - The overclock synergy fits the UR spellslinger identity
> 
> ### Additional Notes:
> 1. This card essentially demands you build around overclock, which is good for a mythic legendary
> 2. The memory issues of tracking which exiled cards get the discount could be problematic in paper
> 3. Consider if both the cost reduction AND copying are necessary - one might be sufficient for an exciting build-around
> 
> ### Recommendation:
> The card needs templating fixes and is likely too powerful. Consider either:
> - Removing the cost reduction and keeping just the copy effect
> - Increasing the mana cost to {3}{U}{R} 
> - Making the copy effect triggered only once per turn

**Tool call result:**
```json
{
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Flying\nSpells you cast from among cards exiled with overclock cost {2} less to cast. (Exile the top three cards of your library. You may play them until end of turn.)\nWhenever you cast a spell from among cards exiled with overclock, copy it. You may choose new targets for the copy.",
  "power": "3",
  "toughness": "4",
  "rarity": "mythic",
  "flavor_text": "I have transcended the limitations of sanity, safety, and the laws of thermodynamics.",
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Overclock reminder text needed proper punctuation and capitalization",
    "Cost reduction ability needed clearer templating to specify 'Spells you cast from among cards exiled with overclock'",
    "Copy trigger needed similar templating update for clarity"
  ]
}
```

*Tokens: 1573 in / 384 out — $0.0524*

## C) Revised Card

```json
{
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Flying\nSpells you cast from among cards exiled with overclock cost {2} less to cast. (Exile the top three cards of your library. You may play them until end of turn.)\nWhenever you cast a spell from among cards exiled with overclock, copy it. You may choose new targets for the copy.",
  "rarity": "mythic",
  "power": "3",
  "toughness": "4",
  "flavor_text": "I have transcended the limitations of sanity, safety, and the laws of thermodynamics."
}
```

**Changes made:**
- Overclock reminder text needed proper punctuation and capitalization
- Cost reduction ability needed clearer templating to specify 'Spells you cast from among cards exiled with overclock'
- Copy trigger needed similar templating update for clarity

## D) Cost

- API calls: 2
- Input tokens: 2408
- Output tokens: 1117
- Cost: $0.1199