# Card 15: Archscientist Vex, the Unbound — Strategy: s4-split-sonnet

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

### Step 1: Pass 1 — Templating review

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
> Card:
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
> Check:
> - Is the oracle text valid MTG rules text using current templating conventions?
> - Does every custom mechanic (salvage, malfunction, overclock) include reminder text in parentheses on its first use?
> - Is keyword capitalization consistent?
> - Are ability words, keyword abilities, and keyword actions used correctly?
> 
> List any templating issues found, or say "PASS" if the templating is correct.

**Response:**
> Looking at this card, I found several templating issues:
> 
> **ISSUES FOUND:**
> 
> 1. **Missing reminder text**: The first use of "overclock" in the oracle text lacks reminder text. It should read: "Cards exiled with overclock *(exile the top three cards of your library, you may play them until end of turn)* cost {2} less to cast."
> 
> 2. **Inconsistent capitalization**: "overclock" should be capitalized as "Overclock" in both instances in the oracle text, following MTG conventions for keyword actions.
> 
> 3. **Reminder text formatting**: The reminder text in the oracle text uses commas instead of periods. It should match the format given in the custom mechanics: "(Exile the top three cards of your library. You may play them until end of turn.)"
> 
> 4. **Character encoding issue**: There's a garbled character "ï¿½" in the type line that should be an em dash "—"
> 
> **CORRECTED ORACLE TEXT:**
> Flying
> Cards exiled with Overclock *(exile the top three cards of your library. You may play them until end of turn)* cost {2} less to cast.
> Whenever you cast a spell exiled with Overclock, copy it. You may choose new targets for the copy.
> 
> **CORRECTED TYPE LINE:**
> Legendary Creature — Human Scientist
> 
> The templating structure is otherwise sound, following current MTG conventions for cost reduction and spell copying effects.

*Tokens: 595 in / 328 out — $0.0067*

### Step 2: Pass 2 — Mechanics review

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
> Card:
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
> Check:
> - Are there any keyword nonbos (keywords negated by other abilities on the card)?
> - If there's a conditional, can it actually be false during normal play?
> - Is this kitchen sink design (3+ unrelated effects piled together)?
> - If effects are variable, is the variability real or always the same value?
> - Does the design have a focused purpose?
> 
> List any design issues found, or say "PASS" if the design is sound.

**Response:**
> Looking at this design systematically:
> 
> **Keyword nonbos**: None present. Flying doesn't interfere with the overclock synergies.
> 
> **Conditional falseness**: The conditionals can be false during normal play. You need to actually overclock to exile cards, and you need to cast those exiled cards to get the copy effect. Both require player action and deck construction choices.
> 
> **Kitchen sink design**: FAIL. This has 3+ unrelated effects:
> 1. Flying (evasion)
> 2. Cost reduction for overclocked cards (ramp effect)
> 3. Copy overclocked spells (value engine)
> 
> Flying has no thematic or mechanical connection to the overclock payoffs. It's just generic goodstuff stapled on.
> 
> **Variable effects**: The variability is real - you may overclock 0+ times per turn, and may cast 0-3 cards from each overclock activation.
> 
> **Focused purpose**: The overclock synergies are focused (cost reduction + copying creates a coherent "high-risk high-reward" identity), but flying muddles this focus.
> 
> **Additional issue - Complexity**: This is very complex for a 4-mana creature. It requires tracking exiled cards, their costs, and managing copies with new targets. The layered decision trees (which cards to overclock → which to cast → which targets for copies) create significant cognitive load.
> 
> **Design Issues Found:**
> 1. Kitchen sink design (flying unrelated to core identity)
> 2. High complexity for mana cost/body stats ratio
> 3. Flying feels like unnecessary power addition rather than purposeful design

*Tokens: 604 in / 355 out — $0.0071*

### Step 3: Pass 3 — Balance review

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
> Card:
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
> Check:
> - Is the power level appropriate for the mana cost AND rarity?
> - Compare to 2-3 well-known printed MTG cards at similar mana cost and rarity.
> - Note: malfunction cards are intentionally above-rate — the delayed entry IS the drawback. Do not flag these for being above-rate.
> - Note: mythic rares are allowed to be powerful build-arounds. Do not nerf mythics to rare power level.
> 
> State whether the balance is PASS, or describe the specific balance issue with card comparisons.

**Response:**
> Looking at Archscientist Vex, the Unbound:
> 
> **Power Level Analysis:**
> 
> This is a 4-mana 3/4 flyer that enables a powerful engine around the Overclock mechanic. Let me break down the effects:
> 
> 1. **Cost reduction**: Makes Overclock cards cost {2} less
> 2. **Copy effect**: Doubles every spell cast from Overclock exile
> 3. **3/4 flying body** for battlefield presence
> 
> **Comparisons to similar mythics:**
> 
> - **Chandra, Torch of Defiance** (2RR): 4 loyalty planeswalker with impulse draw, mana acceleration, damage, and a game-ending ultimate. Sees competitive play.
> - **Bloodbraid Elf** (1RGG): 3/2 haste with cascade, which provides immediate card advantage and tempo. Banned/restricted in multiple formats.
> - **Omnath, Locus of Creation** (WURG): 4/4 that generates massive value through landfall triggers. Format-warping mythic.
> 
> **Balance Assessment:**
> 
> This card creates an extremely powerful engine. The {2} cost reduction makes Overclock essentially free card selection, and copying every spell cast from exile doubles your resources. Unlike other powerful 4-drops that provide one-time value, Vex creates ongoing advantage every turn you Overclock.
> 
> The combination of cost reduction + copying creates explosive turns where you're essentially playing 6+ cards for minimal mana investment. This level of resource generation and mana cheating on a sticky flying threat appears stronger than established mythic benchmarks.
> 
> **Verdict: FAIL**
> 
> The card needs toning down. Suggestions:
> - Reduce cost reduction to {1}
> - Make copying conditional (e.g., "once each turn")
> - Or increase mana cost to 5
> 
> The current version risks being oppressive in any format where Overclock cards exist.

*Tokens: 626 in / 440 out — $0.0085*

### Step 4: Pass 4 — Revision (combining all feedback)

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
> Issues found:
> - Templating: Looking at this card, I found several templating issues:
> 
> **ISSUES FOUND:**
> 
> 1. **Missing reminder text**: The first use of "overclock" in the oracle text lacks reminder text. It should read: "Cards exiled with overclock *(exile the top three cards of your library, you may play them until end of turn)* cost {2} less to cast."
> 
> 2. **Inconsistent capitalization**: "overclock" should be capitalized as "Overclock" in both instances in the oracle text, following MTG conventions for keyword actions.
> 
> 3. **Reminder text formatting**: The reminder text in the oracle text uses commas instead of periods. It should match the format given in the custom mechanics: "(Exile the top three cards of your library. You may play them until end of turn.)"
> 
> 4. **Character encoding issue**: There's a garbled character "ï¿½" in the type line that should be an em dash "—"
> 
> **CORRECTED ORACLE TEXT:**
> Flying
> Cards exiled with Overclock *(exile the top three cards of your library. You may play them until end of turn)* cost {2} less to cast.
> Whenever you cast a spell exiled with Overclock, copy it. You may choose new targets for the copy.
> 
> **CORRECTED TYPE LINE:**
> Legendary Creature — Human Scientist
> 
> The templating structure is otherwise sound, following current MTG conventions for cost reduction and spell copying effects.
> - Mechanics: Looking at this design systematically:
> 
> **Keyword nonbos**: None present. Flying doesn't interfere with the overclock synergies.
> 
> **Conditional falseness**: The conditionals can be false during normal play. You need to actually overclock to exile cards, and you need to cast those exiled cards to get the copy effect. Both require player action and deck construction choices.
> 
> **Kitchen sink design**: FAIL. This has 3+ unrelated effects:
> 1. Flying (evasion)
> 2. Cost reduction for overclocked cards (ramp effect)
> 3. Copy overclocked spells (value engine)
> 
> Flying has no thematic or mechanical connection to the overclock payoffs. It's just generic goodstuff stapled on.
> 
> **Variable effects**: The variability is real - you may overclock 0+ times per turn, and may cast 0-3 cards from each overclock activation.
> 
> **Focused purpose**: The overclock synergies are focused (cost reduction + copying creates a coherent "high-risk high-reward" identity), but flying muddles this focus.
> 
> **Additional issue - Complexity**: This is very complex for a 4-mana creature. It requires tracking exiled cards, their costs, and managing copies with new targets. The layered decision trees (which cards to overclock → which to cast → which targets for copies) create significant cognitive load.
> 
> **Design Issues Found:**
> 1. Kitchen sink design (flying unrelated to core identity)
> 2. High complexity for mana cost/body stats ratio
> 3. Flying feels like unnecessary power addition rather than purposeful design
> - Balance: Looking at Archscientist Vex, the Unbound:
> 
> **Power Level Analysis:**
> 
> This is a 4-mana 3/4 flyer that enables a powerful engine around the Overclock mechanic. Let me break down the effects:
> 
> 1. **Cost reduction**: Makes Overclock cards cost {2} less
> 2. **Copy effect**: Doubles every spell cast from Overclock exile
> 3. **3/4 flying body** for battlefield presence
> 
> **Comparisons to similar mythics:**
> 
> - **Chandra, Torch of Defiance** (2RR): 4 loyalty planeswalker with impulse draw, mana acceleration, damage, and a game-ending ultimate. Sees competitive play.
> - **Bloodbraid Elf** (1RGG): 3/2 haste with cascade, which provides immediate card advantage and tempo. Banned/restricted in multiple formats.
> - **Omnath, Locus of Creation** (WURG): 4/4 that generates massive value through landfall triggers. Format-warping mythic.
> 
> **Balance Assessment:**
> 
> This card creates an extremely powerful engine. The {2} cost reduction makes Overclock essentially free card selection, and copying every spell cast from exile doubles your resources. Unlike other powerful 4-drops that provide one-time value, Vex creates ongoing advantage every turn you Overclock.
> 
> The combination of cost reduction + copying creates explosive turns where you're essentially playing 6+ cards for minimal mana investment. This level of resource generation and mana cheating on a sticky flying threat appears stronger than established mythic benchmarks.
> 
> **Verdict: FAIL**
> 
> The card needs toning down. Suggestions:
> - Reduce cost reduction to {1}
> - Make copying conditional (e.g., "once each turn")
> - Or increase mana cost to 5
> 
> The current version risks being oppressive in any format where Overclock cards exist.
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Missing reminder text for first use of overclock",
    "Inconsistent capitalization of overclock",
    "Incorrect reminder text formatting",
    "Character encoding issue in type line",
    "Kitchen sink design with unrelated flying ability",
    "Overpowered engine with unlimited cost reduction and copying",
    "High complexity for mana cost ratio"
  ],
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{1}{U}{R}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Cards exiled with Overclock (exile the top three cards of your library. You may play them until end of turn) cost {1} less to cast.\nWhenever you cast your first spell exiled with Overclock each turn, copy it. You may choose new targets for the copy.",
  "power": "3",
  "toughness": "4",
  "rarity": "mythic",
  "flavor_text": "I have transcended the limitations of sanity, safety, and the laws of thermodynamics."
}
```

*Tokens: 2300 in / 394 out — $0.0128*

## C) Revised Card

```json
{
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{1}{U}{R}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Cards exiled with Overclock (exile the top three cards of your library. You may play them until end of turn) cost {1} less to cast.\nWhenever you cast your first spell exiled with Overclock each turn, copy it. You may choose new targets for the copy.",
  "rarity": "mythic",
  "power": "3",
  "toughness": "4",
  "flavor_text": "I have transcended the limitations of sanity, safety, and the laws of thermodynamics."
}
```

**Changes made:**
- Missing reminder text for first use of overclock
- Inconsistent capitalization of overclock
- Incorrect reminder text formatting
- Character encoding issue in type line
- Kitchen sink design with unrelated flying ability
- Overpowered engine with unlimited cost reduction and copying
- High complexity for mana cost ratio

## D) Cost

- API calls: 4
- Input tokens: 4125
- Output tokens: 1517
- Cost: $0.0351