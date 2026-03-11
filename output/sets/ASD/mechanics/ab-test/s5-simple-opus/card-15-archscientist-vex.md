# Card 15: Archscientist Vex, the Unbound — Strategy: s5-simple-opus

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

### Step 1: Review and revise (single pass)

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
> Critically review this card and provide an improved version based on your findings. If the card is fine, return it unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Overclock reminder text is incorrectly inlined in the oracle text. Overclock is a keyword action defined for the set, so it should be referenced naturally within ability text, not have its reminder text embedded mid-sentence. The reminder text should appear on first use only, following standard MTG templating.",
    "The phrase 'Cards exiled with overclock' is ambiguous and non-standard. Since Overclock is a keyword action (not a zone or source), the card needs to define when overclock happens. As written, there's no ability on this card that actually performs the overclock action \u2014 it only references cards exiled by it. The card needs an activated or triggered ability that says 'overclock' to generate the exiled cards it cares about.",
    "The cost reduction + copy effect on every overclocked spell is extremely powerful with no restrictions. At mythic this is acceptable in power level but the copy ability should probably be limited to once per turn to prevent degenerate loops, especially since the cost reduction enables chaining multiple spells.",
    "Flying feels tacked on for a Human Scientist in U/R. Prowess or no evasion would be more flavorful and mechanically appropriate.",
    "P/T 3/4 with flying plus two powerful static/triggered abilities is slightly overloaded for 4 mana, even at mythic. Adjusting to 2/4 to reflect the card's role as a build-around engine rather than a beater."
  ],
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "{T}: Overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nSpells you cast from exile cost {2} less to cast.\nOnce each turn, whenever you cast a spell from exile, you may copy it. You may choose new targets for the copy.",
  "rarity": "mythic",
  "power": "2",
  "toughness": "4",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
}
```

*Tokens: 1421 in / 652 out — $0.0234*

## C) Revised Card

```json
{
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "{T}: Overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nSpells you cast from exile cost {2} less to cast.\nOnce each turn, whenever you cast a spell from exile, you may copy it. You may choose new targets for the copy.",
  "rarity": "mythic",
  "power": "2",
  "toughness": "4",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
}
```

**Changes made:**
- Overclock reminder text is incorrectly inlined in the oracle text. Overclock is a keyword action defined for the set, so it should be referenced naturally within ability text, not have its reminder text embedded mid-sentence. The reminder text should appear on first use only, following standard MTG templating.
- The phrase 'Cards exiled with overclock' is ambiguous and non-standard. Since Overclock is a keyword action (not a zone or source), the card needs to define when overclock happens. As written, there's no ability on this card that actually performs the overclock action — it only references cards exiled by it. The card needs an activated or triggered ability that says 'overclock' to generate the exiled cards it cares about.
- The cost reduction + copy effect on every overclocked spell is extremely powerful with no restrictions. At mythic this is acceptable in power level but the copy ability should probably be limited to once per turn to prevent degenerate loops, especially since the cost reduction enables chaining multiple spells.
- Flying feels tacked on for a Human Scientist in U/R. Prowess or no evasion would be more flavorful and mechanically appropriate.
- P/T 3/4 with flying plus two powerful static/triggered abilities is slightly overloaded for 4 mana, even at mythic. Adjusting to 2/4 to reflect the card's role as a build-around engine rather than a beater.

## D) Cost

- API calls: 1
- Input tokens: 1421
- Output tokens: 652
- Cost: $0.0234