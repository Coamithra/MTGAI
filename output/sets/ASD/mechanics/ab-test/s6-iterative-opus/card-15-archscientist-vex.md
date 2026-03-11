# Card 15: Archscientist Vex, the Unbound — Strategy: s6-iterative-opus

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

### Step 1: Iteration 1

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
    "Overclock reminder text is incorrectly inlined in the oracle text. As a keyword action, overclock should be used as a verb in a sentence, not parenthetically defined inline on first use like a keyword ability. The reminder text should follow the keyword action naturally.",
    "The word 'overclock' is not capitalized in the oracle text. Keyword actions should be capitalized when used as part of card text (e.g., 'Overclock' not 'overclock').",
    "The cost reduction ability references 'cards exiled with overclock' but the card itself has no ability that performs overclock. There's no overclock trigger or activated ability on the card \u2014 it only rewards you for overclocking from other sources. This is a valid build-around mythic design, but the first ability's phrasing is awkward as a standalone sentence. It should be templated more cleanly.",
    "Flying on a Human Scientist feels slightly off flavor but is acceptable for a mythic legendary in U/R. No change needed here.",
    "The copy ability combined with the cost reduction is extremely powerful. At mythic this is acceptable but worth flagging \u2014 copying every overclocked spell with no limit and reducing costs by {2} is a massive payoff. No change needed for mythic power level.",
    "P/T 3/4 with flying for {2}{U}{R} is reasonable for a mythic build-around that needs other overclock sources to function."
  ],
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Flying\nSpells you cast from exile that were exiled by overclock cost {2} less to cast.\nWhenever you cast a spell from exile that was exiled by overclock, copy it. You may choose new targets for the copy.",
  "rarity": "mythic",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
}
```

*Tokens: 1421 in / 630 out — $0.0229*

### Step 2: Iteration 2

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
> Type: Legendary Creature — Human Scientist
> Rarity: mythic
> Oracle Text: Flying
> Spells you cast from exile that were exiled by overclock cost {2} less to cast.
> Whenever you cast a spell from exile that was exiled by overclock, copy it. You may choose new targets for the copy.
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
    "Overclock is a keyword action, not a permanent or source that 'exiles' cards. The phrasing 'exiled by overclock' is awkward but functionally acceptable in MTG templating (similar to 'exiled by foretell'). However, 'overclock' should be italicized/formatted consistently as a keyword action, not capitalized as a proper noun.",
    "The phrase 'Spells you cast from exile that were exiled by overclock cost {2} less to cast' has a subtle templating issue. Standard MTG templating for cost reduction on spells uses 'Spells you cast from among cards exiled by overclock cost {2} less to cast' or similar. The current phrasing conflates the spell (on the stack) with the card (in exile). Should reference the cards exiled by the action.",
    "The copy trigger combined with a {2} cost reduction is extremely powerful for a 4-mana creature. Copying ANY spell from overclock (including other players' overclock effects if any exist) with no limitation is very pushed. However, as a mythic legendary creature in UR that requires setup (needing overclock sources), this is within mythic power budget, though the cost reduction should likely be {1} to avoid trivially free-casting and copying expensive spells.",
    "Flying on a UR Human Scientist feels slightly off-flavor. UR creatures at mythic more commonly have prowess or no evasion, but flying is within UR's color pie so this is minor.",
    "The triggered ability should specify 'if that spell has targets' or use the standard copy template more precisely."
  ],
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Flying\nSpells you cast from among cards exiled by overclock cost {1} less to cast.\nWhenever you cast a spell from among cards exiled by overclock, copy it. You may choose new targets for the copy.",
  "rarity": "mythic",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
}
```

*Tokens: 1412 in / 673 out — $0.0239*

### Step 3: Iteration 3

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
> Type: Legendary Creature — Human Scientist
> Rarity: mythic
> Oracle Text: Flying
> Spells you cast from among cards exiled by overclock cost {1} less to cast.
> Whenever you cast a spell from among cards exiled by overclock, copy it. You may choose new targets for the copy.
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
    "Overclock is a keyword action, not a keyword ability. The oracle text references 'cards exiled by overclock' as if overclock were a zone or source tracker, but keyword actions don't inherently track cards they exile. The text needs to explicitly reference the overclock action properly. In MTG templating, you'd need to say something like 'Whenever you overclock, [effect]' or reference cards exiled via a specific ability. The card needs to grant or trigger overclock itself to function as a build-around mythic.",
    "The cost reduction 'Spells you cast from among cards exiled by overclock cost {1} less' is ambiguous \u2014 overclock exiles 3 cards each time it's used, potentially across multiple instances. The tracking of 'cards exiled by overclock' needs cleaner templating similar to how impulse draw tracks exiled cards (e.g., 'cards exiled with overclock abilities you controlled').",
    "Flying on a UR Human Scientist feels slightly out of place flavor-wise, but is technically fine in blue. Minor concern only.",
    "The card has no way to overclock itself, making it entirely dependent on other cards. A mythic legendary build-around payoff for the set's signature mechanic should probably also enable it. Adding an activated overclock ability makes the card self-sufficient while still benefiting from other overclock sources.",
    "Copying every spell cast from overclock with no restrictions is extremely powerful, especially with the cost reduction stacked on top. For a 4-mana creature with no protection, this is strong but arguably appropriate at mythic. However, adding the activated overclock ability means we should tighten the copy trigger slightly to prevent runaway value \u2014 limiting to once per turn is cleaner."
  ],
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Flying\nSpells you cast from exile cost {1} less to cast.\n{1}, {T}: Overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nWhenever you cast a spell from exile, copy it. You may choose new targets for the copy. This ability triggers only once each turn.",
  "power": "3",
  "toughness": "4",
  "rarity": "mythic",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
}
```

*Tokens: 1410 in / 722 out — $0.0251*

### Step 4: Iteration 4

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
> Type: Legendary Creature — Human Scientist
> Rarity: mythic
> Oracle Text: Flying
> Spells you cast from exile cost {1} less to cast.
> {1}, {T}: Overclock. (Exile the top three cards of your library. You may play them until end of turn.)
> Whenever you cast a spell from exile, copy it. You may choose new targets for the copy. This ability triggers only once each turn.
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
    "Overclock reminder text on the card is correct and matches the mechanic definition. No issue there.",
    "The card has four distinct abilities (flying, cost reduction, activated overclock, triggered copy). For a mythic legendary this is acceptable but the combination of cost reduction + copying spells from exile is extremely powerful. The cost reduction makes the copies less relevant for tempo since you're already getting a discount, but the copy trigger on top creates a situation where every turn you activate Overclock you're potentially getting a free spell copy with no additional mana investment beyond the {1},{T} activation. This is a two-card engine in one card.",
    "The cost reduction applies to ALL spells cast from exile, not just those from Overclock. This has broad synergy with adventure cards, foretell, impulse draw, cascade, etc. Combined with the copy trigger, this is likely too much value consolidation for a 4-mana creature.",
    "Flying on a UR 3/4 legendary scientist feels tacked on and lacks flavor justification. A scientist doesn't typically fly. This also makes the card harder to interact with in combat while it generates massive value each turn.",
    "The 'once each turn' restriction on the copy trigger is good design, but the combination of persistent cost reduction + guaranteed copy each turn you Overclock (since you see 3 cards) makes this overwhelmingly consistent for a 4-mana card. Recommend removing flying to make it more vulnerable in combat, and tightening the cost reduction to only apply to Overclock-exiled cards by rewording, OR increasing mana cost. I'll remove flying and increase the activation cost to {2},{T} to create a more meaningful tempo tradeoff when using Overclock."
  ],
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Spells you cast from exile cost {1} less to cast.\n{2}, {T}: Overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nWhenever you cast a spell from exile, copy it. You may choose new targets for the copy. This ability triggers only once each turn.",
  "rarity": "mythic",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
}
```

*Tokens: 1437 in / 713 out — $0.0250*

### Step 5: Iteration 5

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
> Type: Legendary Creature — Human Scientist
> Rarity: mythic
> Oracle Text: Spells you cast from exile cost {1} less to cast.
> {2}, {T}: Overclock. (Exile the top three cards of your library. You may play them until end of turn.)
> Whenever you cast a spell from exile, copy it. You may choose new targets for the copy. This ability triggers only once each turn.
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
    "Overclock is complexity 3 and restricted to U, R, B colors. The card is U/R, which is within the allowed color pair \u2014 no issue there.",
    "The card has three distinct abilities plus an activated ability, which is a lot of text even for mythic. However, the abilities are synergistic and form a clear package (enabler + payoff), which is acceptable at mythic rare for a legendary creature.",
    "The cost reduction ({1} less) combined with copying spells from exile is extremely powerful. The copy ability triggering 'only once each turn' is a good safety valve, but the cost reduction applies to ALL spells cast from exile with no limit. Combined with the self-contained Overclock activation, this gives up to 3 exiled cards per turn at reduced cost plus one free copy. This is above the line for a 4-mana creature.",
    "The activated ability cost of {2}, {T} is quite cheap for Overclock on a repeatable source. Since this is a mythic legendary build-around, some power is expected, but the combination of cheap activation + cost reduction + copying creates a snowball engine that's too easy to assemble (it's all on one card). Raising the activation cost to {3}, {T} adds a meaningful mana tension \u2014 you want mana open to cast the exiled cards, so paying more to Overclock creates a real decision point.",
    "P/T 3/4 for a 4-mana creature with three powerful abilities is slightly generous. A 2/4 body still survives common removal and combat but makes the card less effective as both an engine AND a threat simultaneously, which is better for gameplay. However, 3/4 is defensible at mythic. The activation cost increase is the more important fix.",
    "The cost reduction ability should specify 'noncreature spells' or have some restriction to prevent degenerate interactions, but since it only reduces by {1} and the copy is once per turn, it's acceptable as-is for mythic."
  ],
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Spells you cast from exile cost {1} less to cast.\n{3}, {T}: Overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nWhenever you cast a spell from exile, copy it. You may choose new targets for the copy. This ability triggers only once each turn.",
  "rarity": "mythic",
  "power": "2",
  "toughness": "4",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
}
```

*Tokens: 1435 in / 783 out — $0.0267*

## C) Revised Card

```json
{
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Spells you cast from exile cost {1} less to cast.\n{3}, {T}: Overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nWhenever you cast a spell from exile, copy it. You may choose new targets for the copy. This ability triggers only once each turn.",
  "rarity": "mythic",
  "power": "2",
  "toughness": "4",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
}
```

**Changes made:**
- Overclock is complexity 3 and restricted to U, R, B colors. The card is U/R, which is within the allowed color pair — no issue there.
- The card has three distinct abilities plus an activated ability, which is a lot of text even for mythic. However, the abilities are synergistic and form a clear package (enabler + payoff), which is acceptable at mythic rare for a legendary creature.
- The cost reduction ({1} less) combined with copying spells from exile is extremely powerful. The copy ability triggering 'only once each turn' is a good safety valve, but the cost reduction applies to ALL spells cast from exile with no limit. Combined with the self-contained Overclock activation, this gives up to 3 exiled cards per turn at reduced cost plus one free copy. This is above the line for a 4-mana creature.
- The activated ability cost of {2}, {T} is quite cheap for Overclock on a repeatable source. Since this is a mythic legendary build-around, some power is expected, but the combination of cheap activation + cost reduction + copying creates a snowball engine that's too easy to assemble (it's all on one card). Raising the activation cost to {3}, {T} adds a meaningful mana tension — you want mana open to cast the exiled cards, so paying more to Overclock creates a real decision point.
- P/T 3/4 for a 4-mana creature with three powerful abilities is slightly generous. A 2/4 body still survives common removal and combat but makes the card less effective as both an engine AND a threat simultaneously, which is better for gameplay. However, 3/4 is defensible at mythic. The activation cost increase is the more important fix.
- The cost reduction ability should specify 'noncreature spells' or have some restriction to prevent degenerate interactions, but since it only reduces by {1} and the copy is once per turn, it's acceptable as-is for mythic.

## D) Cost

- API calls: 5
- Input tokens: 7115
- Output tokens: 3521
- Cost: $0.1236