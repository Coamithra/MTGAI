# Card 15: Archscientist Vex, the Unbound — Strategy: s2-iterative-sonnet

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
  "issues_found": "[\"Overclock is a keyword action defined in the set \u2014 the oracle text should reference it as a keyword, not define it inline. The parenthetical definition in the cost-reduction line is redundant and non-standard; reminder text belongs in italics as a separate note, not embedded in the rules text sentence.\", \"The cost-reduction ability says 'Cards exiled with overclock cost {2} less to cast.' Overclock always exiles exactly 3 cards, and those cards can only be played until end of turn. A {2} cost reduction on all three exiled cards is extremely strong (potentially free spells) and likely too powerful even at mythic rare \u2014 {1} less is safer and more balanced.\", \"The copy trigger 'Whenever you cast a spell exiled with overclock, copy it' combined with the cost reduction creates a compounding power problem: cheap or free spells that are also copied. This is potentially broken with cheap instants/sorceries. The copy should be limited to instants and sorceries (the typical copy-spell constraint), since copying a permanent spell is unusual and likely unintended.\", \"Encoding the Overclock reminder text mid-sentence in the rules text is a templating error. Reminder text should follow the keyword reference in a separate parenthetical, not be fused into the ability sentence.\", \"The type line has a Unicode encoding artifact ('\u00e2\u20ac\"') instead of an em dash ('\u2014').\"]",
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Flying\nSpells you cast that were exiled by an overclock effect cost {1} less to cast.\nWhenever you cast an instant or sorcery spell that was exiled by an overclock effect, copy that spell. You may choose new targets for the copy.\n(Overclock: Exile the top three cards of your library. You may play them until end of turn.)",
  "rarity": "mythic",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
}
```

*Tokens: 1422 in / 657 out — $0.0141*

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
> Spells you cast that were exiled by an overclock effect cost {1} less to cast.
> Whenever you cast an instant or sorcery spell that was exiled by an overclock effect, copy that spell. You may choose new targets for the copy.
> (Overclock: Exile the top three cards of your library. You may play them until end of turn.)
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
    "OVERCLOCK REMINDER TEXT PLACEMENT: The Overclock reminder text is appended at the bottom as if it's a keyword on this card, but Overclock is a keyword ACTION (like 'scry' or 'proliferate'), not a keyword ability granted by this card. This card doesn't grant or have Overclock \u2014 it rewards playing cards exiled by Overclock effects elsewhere. The reminder text block doesn't belong here and is misleading. It should be removed entirely; the set's rules glossary or other cards handle the reminder.",
    "RULES LANGUAGE \u2014 'OVERCLOCK EFFECT': The phrase 'exiled by an overclock effect' is informal and not clean Magic rules language. Magic typically tracks this kind of exile via a zone-change condition or a defined phrase. The correct templating should reference cards 'exiled by Overclock' (using the keyword action name directly and consistently), matching how other triggered-exile mechanics are worded (e.g., 'exiled with Cascade,' 'exiled by a Foretell effect'). This is acceptable shorthand if established in the set's rules supplement, but the capitalization and phrasing should be consistent. 'Overclock effect' \u2192 'Overclock' (capitalize, drop 'effect' as redundant).",
    "STAT / POWER LEVEL CONCERN: 3/4 Flying for {2}{U}{R} is already above-rate for a non-Malfunction card (compare Crackling Drake, Murmuring Mystic, etc.). Combined with a cost-reduction ability AND a free copy trigger for instants/sorceries cast off Overclock, this card is extremely pushed \u2014 potentially format-warping at mythic. The copy trigger in particular is a massive free value engine. However, given this is a mythic Legendary build-around, this power level can be acceptable IF the deck investment in Overclock synergy is real. A minor stat trim (3/3) better signals 'build-around mythic' rather than 'generically powerful mythic,' making the Overclock payoff more essential.",
    "TEMPLATING \u2014 COST REDUCTION LAYER: 'Spells you cast that were exiled by an overclock effect cost {1} less to cast' should use the standard cost-reduction template: 'Spells you cast that were exiled by Overclock cost {1} less to cast.' (Remove 'an overclock effect' \u2192 'Overclock' for cleaner keyword-action reference.)"
  ],
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Flying\nSpells you cast that were exiled by Overclock cost {1} less to cast.\nWhenever you cast an instant or sorcery spell that was exiled by Overclock, copy that spell. You may choose new targets for the copy.",
  "rarity": "mythic",
  "power": "3",
  "toughness": "3",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
}
```

*Tokens: 1444 in / 875 out — $0.0175*

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
> Spells you cast that were exiled by Overclock cost {1} less to cast.
> Whenever you cast an instant or sorcery spell that was exiled by Overclock, copy that spell. You may choose new targets for the copy.
> P/T: 3/3
> Flavor Text: "I have transcended the limitations of sanity, safety, and the laws of thermodynamics."
> 
> Critically review this card and provide an improved version based on your findings. If the card is fine, return it unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "POWER LEVEL \u2014 CRITICAL: At {2}{U}{R} for a 3/3 flier, Vex already has a strong body. The combination of a cost reduction AND a free copy trigger for Overclocked spells is extremely pushed \u2014 effectively turning every Overclocked instant/sorcery into a Twincast for free. This is backbreaking alongside cheap spells and could trivially generate enormous value on the same turn Overclock resolves.",
    "PARASITIC SYNERGY RISK: The card is entirely parasitic on Overclock activations. While that's clearly intentional as a build-around mythic, the copy trigger has no cost or condition beyond 'cast a spell exiled by Overclock,' making it trivially consistent once Overclock is used. A legendary mythic build-around should demand more from the pilot.",
    "COST REDUCTION REDUNDANCY: The {1} reduction per spell is largely irrelevant when the copy trigger already provides enormous free value. It muddies the card's identity and may cause rules complications (e.g., should the copied spell also be considered 'cast' from exile? No, but players may be confused).",
    "MISSING OVERCLOCK ENABLEMENT: Vex has no way to Overclock herself, meaning she depends entirely on other cards. For a mythic build-around, giving her a native Overclock outlet (perhaps once per turn or with a cost) would make her more self-contained and reliably impressive, consistent with mythic design expectations.",
    "FLAVOR TEXT ALIGNMENT: The flavor text is excellent and should be retained exactly.",
    "STATS: 3/3 flying at {2}{U}{R} is already rate-positive for a mythic legendary. If the abilities are strengthened, the body could be trimmed to 3/2 to compensate."
  ],
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Flying\n{1}{U}{R}, {T}: Overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nWhenever you cast an instant or sorcery spell that was exiled by an Overclock, if Vex is on the battlefield, copy that spell. You may choose new targets for the copy.",
  "rarity": "mythic",
  "power": "3",
  "toughness": "2",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
}
```

*Tokens: 1417 in / 747 out — $0.0155*

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
> {1}{U}{R}, {T}: Overclock. (Exile the top three cards of your library. You may play them until end of turn.)
> Whenever you cast an instant or sorcery spell that was exiled by an Overclock, if Vex is on the battlefield, copy that spell. You may choose new targets for the copy.
> P/T: 3/2
> Flavor Text: "I have transcended the limitations of sanity, safety, and the laws of thermodynamics."
> 
> Critically review this card and provide an improved version based on your findings. If the card is fine, return it unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "RULES AMBIGUITY \u2014 Overclock tracking: The triggered ability says 'exiled by an Overclock' but Overclock is a keyword action, not a named zone or object. Cards exiled by Overclock are not distinctly tagged as such in the rules, so the game has no clean way to track which exiled cards came from which Overclock activation. This needs explicit wording referencing the exile zone relative to Vex's ability.",
    "RULES REDUNDANCY \u2014 'if Vex is on the battlefield' is unnecessary. Triggered abilities on permanents inherently check that the permanent is still on the battlefield at resolution (they simply cease to exist if the source leaves). This clause adds confusion rather than clarity.",
    "TEMPLATING \u2014 'Whenever you cast an instant or sorcery spell that was exiled by an Overclock' is non-standard templating. Correct MtG templating would use 'exiled with [CARDNAME]' or tie it to the specific ability via an exile-with-counter or bracket approach, similar to how Foretell and Suspend track their exiled cards.",
    "POWER LEVEL NOTE \u2014 The combination of a free Spells-Matter copy trigger + a reusable Overclock on a 4-mana Legendary is extremely powerful but likely acceptable at Mythic with the {T} cost acting as a brake. No change needed for power level alone, but clean templating is essential to avoid abuse through ambiguity."
  ],
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Flying\n{1}{U}{R}, {T}: Exile the top three cards of your library. Until end of turn, you may play cards exiled this way. (This is an Overclock.)\nWhenever you cast an instant or sorcery spell exiled with Archscientist Vex, the Unbound, copy that spell. You may choose new targets for the copy.",
  "rarity": "mythic",
  "power": "3",
  "toughness": "2",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
}
```

*Tokens: 1440 in / 674 out — $0.0144*

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
> Oracle Text: Flying
> {1}{U}{R}, {T}: Exile the top three cards of your library. Until end of turn, you may play cards exiled this way. (This is an Overclock.)
> Whenever you cast an instant or sorcery spell exiled with Archscientist Vex, the Unbound, copy that spell. You may choose new targets for the copy.
> P/T: 3/2
> Flavor Text: "I have transcended the limitations of sanity, safety, and the laws of thermodynamics."
> 
> Critically review this card and provide an improved version based on your findings. If the card is fine, return it unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Overclock reminder text is missing from the activated ability. Per the mechanic's definition, the reminder text '(Exile the top three cards of your library. You may play them until end of turn.)' should appear inline \u2014 but since the card already spells out the full effect in oracle text, the parenthetical '(This is an Overclock.)' label is non-standard. Per MTG templating conventions, keyword actions with reminder text should use the keyword followed by its reminder text, not a back-reference label. The oracle text should lead with 'Overclock' as the keyword action and let the triggered ability follow, rather than spelling out the effect and then labeling it.",
    "The activated ability spells out the full Overclock effect in oracle text AND appends '(This is an Overclock.)' \u2014 this is redundant and non-standard. Correct templating for a keyword action is to simply use the keyword: '{1}{U}{R}, {T}: Overclock. (Exile the top three cards of your library. You may play them until end of turn.)'",
    "The triggered ability references 'cards exiled with Archscientist Vex, the Unbound' \u2014 using the full legendary name in a self-referential trigger is correct per MTG rules for legendary permanents, so this is fine.",
    "Power/toughness of 3/2 with flying, a cheap repeatable Overclock, AND a spell-copy trigger is extremely pushed even for a mythic. However, the {1}{U}{R} tap cost with no built-in protection provides a reasonable tension point, so this is a design judgment call rather than a hard error. No change made to stats.",
    "Rarity and color identity are both correct: Overclock is a U/R mechanic, and mythic rarity is appropriate for the complexity rating of 3."
  ],
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Flying\n{1}{U}{R}, {T}: Overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nWhenever you cast an instant or sorcery spell exiled with Archscientist Vex, the Unbound, copy that spell. You may choose new targets for the copy.",
  "rarity": "mythic",
  "power": "3",
  "toughness": "2",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
}
```

*Tokens: 1446 in / 749 out — $0.0156*

## C) Revised Card

```json
{
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Flying\n{1}{U}{R}, {T}: Overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nWhenever you cast an instant or sorcery spell exiled with Archscientist Vex, the Unbound, copy that spell. You may choose new targets for the copy.",
  "rarity": "mythic",
  "power": "3",
  "toughness": "2",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
}
```

**Changes made:**
- Overclock reminder text is missing from the activated ability. Per the mechanic's definition, the reminder text '(Exile the top three cards of your library. You may play them until end of turn.)' should appear inline — but since the card already spells out the full effect in oracle text, the parenthetical '(This is an Overclock.)' label is non-standard. Per MTG templating conventions, keyword actions with reminder text should use the keyword followed by its reminder text, not a back-reference label. The oracle text should lead with 'Overclock' as the keyword action and let the triggered ability follow, rather than spelling out the effect and then labeling it.
- The activated ability spells out the full Overclock effect in oracle text AND appends '(This is an Overclock.)' — this is redundant and non-standard. Correct templating for a keyword action is to simply use the keyword: '{1}{U}{R}, {T}: Overclock. (Exile the top three cards of your library. You may play them until end of turn.)'
- The triggered ability references 'cards exiled with Archscientist Vex, the Unbound' — using the full legendary name in a self-referential trigger is correct per MTG rules for legendary permanents, so this is fine.
- Power/toughness of 3/2 with flying, a cheap repeatable Overclock, AND a spell-copy trigger is extremely pushed even for a mythic. However, the {1}{U}{R} tap cost with no built-in protection provides a reasonable tension point, so this is a design judgment call rather than a hard error. No change made to stats.
- Rarity and color identity are both correct: Overclock is a U/R mechanic, and mythic rarity is appropriate for the complexity rating of 3.

## D) Cost

- API calls: 5
- Input tokens: 7169
- Output tokens: 3702
- Cost: $0.0770