# Card 11: Synaptic Overload — Strategy: s5-simple-opus

## A) Original Card

```json
{
  "name": "Synaptic Overload",
  "mana_cost": "{1}{U}",
  "cmc": 2,
  "colors": [
    "U"
  ],
  "type_line": "Instant",
  "oracle_text": "As an additional cost to cast ~, overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nCounter target spell. If you overclocked this turn, draw a card.",
  "rarity": "uncommon",
  "keywords": [
    "Overclock"
  ],
  "flavor_text": "\"The prototype neural interface worked perfectly. The subject's brain, however, did not.\" \u00e2\u20ac\u201dDr. Malleus, Cult of Science"
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
> Name: Synaptic Overload
> Mana Cost: {1}{U}
> Type: Instant
> Rarity: uncommon
> Oracle Text: As an additional cost to cast ~, overclock. (Exile the top three cards of your library. You may play them until end of turn.)
> Counter target spell. If you overclocked this turn, draw a card.
> Flavor Text: "The prototype neural interface worked perfectly. The subject's brain, however, did not." â€”Dr. Malleus, Cult of Science
> 
> Critically review this card and provide an improved version based on your findings. If the card is fine, return it unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Overclock is a keyword action, not a keyword ability. It should not be used as 'an additional cost to cast' \u2014 keyword actions are performed as part of an effect, not as costs. The current templating treats it like an additional cost, but the reminder text says 'You may play them until end of turn,' which is an effect, not a cost structure. It should be written as a spell effect that instructs you to overclock.",
    "The conditional 'If you overclocked this turn' is awkward and has no clean rules meaning \u2014 overclock exiles cards and lets you play them, but there's no game state marker for 'having overclocked.' This needs to be restructured so the overclock happens as part of the spell's resolution, and the draw is a natural follow-up.",
    "At {1}{U} for an unconditional counterspell + overclock (exile 3, play them until end of turn) + draw a card, this is significantly above rate. Cancel is {1}{U}{U} for a vanilla counter. Even at uncommon, a 2-mana hard counter that also generates card advantage (draw + access to 3 exiled cards) is too strong. Bumping to {1}{U}{U} is appropriate.",
    "Minor: Flavor text has encoding artifacts (\u00e2\u20ac\" instead of em dash). Should use proper em dash (\u2014)."
  ],
  "name": "Synaptic Overload",
  "mana_cost": "{1}{U}{U}",
  "type_line": "Instant",
  "oracle_text": "Counter target spell. Overclock, then draw a card. (Exile the top three cards of your library. You may play them until end of turn.)",
  "rarity": "uncommon",
  "flavor_text": "\"The prototype neural interface worked perfectly. The subject's brain, however, did not.\" \u2014Dr. Malleus, Cult of Science"
}
```

*Tokens: 1394 in / 558 out — $0.0209*

## C) Revised Card

```json
{
  "name": "Synaptic Overload",
  "mana_cost": "{1}{U}{U}",
  "type_line": "Instant",
  "oracle_text": "Counter target spell. Overclock, then draw a card. (Exile the top three cards of your library. You may play them until end of turn.)",
  "rarity": "uncommon",
  "flavor_text": "\"The prototype neural interface worked perfectly. The subject's brain, however, did not.\" \u2014Dr. Malleus, Cult of Science"
}
```

**Changes made:**
- Overclock is a keyword action, not a keyword ability. It should not be used as 'an additional cost to cast' — keyword actions are performed as part of an effect, not as costs. The current templating treats it like an additional cost, but the reminder text says 'You may play them until end of turn,' which is an effect, not a cost structure. It should be written as a spell effect that instructs you to overclock.
- The conditional 'If you overclocked this turn' is awkward and has no clean rules meaning — overclock exiles cards and lets you play them, but there's no game state marker for 'having overclocked.' This needs to be restructured so the overclock happens as part of the spell's resolution, and the draw is a natural follow-up.
- At {1}{U} for an unconditional counterspell + overclock (exile 3, play them until end of turn) + draw a card, this is significantly above rate. Cancel is {1}{U}{U} for a vanilla counter. Even at uncommon, a 2-mana hard counter that also generates card advantage (draw + access to 3 exiled cards) is too strong. Bumping to {1}{U}{U} is appropriate.
- Minor: Flavor text has encoding artifacts (â€" instead of em dash). Should use proper em dash (—).

## D) Cost

- API calls: 1
- Input tokens: 1394
- Output tokens: 558
- Cost: $0.0209