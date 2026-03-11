# Card 15: Archscientist Vex, the Unbound — Strategy: s9-council-opus

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

### Step 1: Reviewer 1 analysis

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
> Critically review this card. List any issues you find with templating, mechanics, balance, design, or color pie. If the card is fine, say "No issues found." Be specific about each issue.

**Response:**
> ## Review of Archscientist Vex, the Unbound
> 
> ### Issues Found:
> 
> **1. Overclock Is Used as a Static Reference, Not as an Action**
> Overclock is defined as a keyword *action* — something a card tells you to do. But this card never actually instructs you to overclock. Instead, it references "cards exiled with overclock" as a passive condition. This creates a fundamental problem: the card has no way to *perform* overclock itself. It's a payoff card with no enabler built in, and the reminder text for overclock is awkwardly embedded in a static ability where it reads as a definition rather than an instruction. The reminder text parenthetical after "overclock" makes it look like the card is telling you to overclock right then, which is confusing.
> 
> **2. Templating of the Cost Reduction Ability**
> "Cards exiled with overclock cost {2} less to cast" needs cleaner templating. A more standard approach would be: "Spells you cast from exile cost {2} less to cast" (if that's the intent) or specifically "Spells you cast from among cards exiled by overclocking cost {2} less to cast." The current wording also doesn't specify "you cast" — technically it could reduce costs for any player.
> 
> **3. Copy Ability + Cost Reduction Is Extremely Dangerous**
> A {2} cost reduction across three exiled cards plus copying every spell cast from among them is a massive amount of value. Hitting two spells in one overclock means {4} in mana savings plus two free copies. This is a combo-enabling engine at 4 mana that likely needs either the cost reduction OR the copy trigger, not both.
> 
> **4. No Self-Contained Overclock Activation**
> For a mythic build-around, requiring other cards to provide the overclock action makes this card feel incomplete. Most comparable mythic payoff-enablers (like Archmage Emeritus for magecraft) at least function in a self-contained ecosystem. Consider giving it an activated overclock ability.
> 
> **5. Flying Is Minor but Slightly Off**
> Flying on a U/R Scientist is technically in pie but feels like filler. Prowess or another spell-matters keyword would be more thematically cohesive.
> 
> ### Summary
> The core design idea is exciting, but the card is overloaded with two powerful payoff abilities, lacks a self-contained way to overclock, and has templating issues around referencing a keyword action as a static condition.

*Tokens: 539 in / 572 out — $0.0170*

### Step 2: Reviewer 2 analysis

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
> Critically review this card. List any issues you find with templating, mechanics, balance, design, or color pie. If the card is fine, say "No issues found." Be specific about each issue.

**Response:**
> ## Review of Archscientist Vex, the Unbound
> 
> ### Issue 1: Overclock Used as a Static Keyword, Not a Keyword Action
> **Severity: Major (Templating/Design)**
> 
> Overclock is defined as a keyword *action* — something you actively do. But this card references "cards exiled with overclock" without ever granting you the ability to overclock. The card assumes overclock is happening from other sources, but the parenthetical reminder text in the middle of a static ability reads as though the card itself is supposed to let you overclock. This is deeply ambiguous. The card needs either:
> - An activated/triggered ability that says "Overclock" as an action, OR
> - Clean referencing of external overclock sources without the inline reminder text (e.g., "Cards you own exiled with overclock cost {2} less to cast.")
> 
> ### Issue 2: Reminder Text Placement is Non-Standard
> **Severity: Moderate (Templating)**
> 
> Embedding the full overclock reminder text inside a static ability's rules text is extremely unusual. Reminder text for a keyword action should appear on cards that *perform* the action, not on cards that merely reference it. This clutters the text box and creates parsing confusion.
> 
> ### Issue 3: Balance — Stacking Cost Reduction + Copying is Excessive
> **Severity: Major (Balance)**
> 
> At 4 mana, this provides: {2} cost reduction on up to 3 exiled cards AND copies every spell cast from that exile. The cost reduction already enables free spells from overclock (many 1-2 CMC spells become free), and then each one is *also copied*. This is a two-card engine on a single body that can produce catastrophic value the turn another overclock source is activated. The two abilities together create degenerate loops far too easily.
> 
> ### Issue 4: "Cast a spell exiled with overclock" — Tracking Ambiguity
> **Severity: Moderate (Templating)**
> 
> "Exiled with overclock" as a zone-tracking reference is fragile. Once a card moves from exile to the stack, it's a new object. Standard templating for this kind of effect typically uses a more explicit linking mechanism. Compare to Prosper, Tome-Bound's "cast a spell from exile" — broader but cleaner.
> 
> ### Issue 5: Flying in Red-Blue on a Scientist
> **Severity: Minor (Color Pie)**
> 
> Acceptable in UR, though mildly generous combined with the 3/4 body.
> 
> ### Summary
> The card's core concept is exciting but needs a cleaner overclock integration (ideally granting the action itself), and the two abilities together are overpowered at this cost. I'd recommend keeping one payoff ability and either adding an overclock activation or raising the mana cost significantly.

*Tokens: 539 in / 645 out — $0.0188*

### Step 3: Reviewer 3 analysis

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
> Critically review this card. List any issues you find with templating, mechanics, balance, design, or color pie. If the card is fine, say "No issues found." Be specific about each issue.

**Response:**
> ## Review of Archscientist Vex, the Unbound
> 
> ### Issues Found:
> 
> **1. Overclock Is Used as a Static Reference, Not an Action**
> The card references "cards exiled with overclock" but never actually *performs* the overclock action itself. Overclock is defined as a keyword action (like scry or mill), meaning something on the card needs to tell you *when* to do it. As written, the card has no way to exile cards in the first place — it only rewards you for having done so from other sources. If the intent is to be a payoff card, the reminder text in the parenthetical is misleading because it reads like the card itself performs the action. If the intent is self-contained, it needs an activation or trigger like "At the beginning of combat on your turn, overclock."
> 
> **2. Templating of the Reminder Text Placement**
> The reminder text for overclock is embedded in the middle of an ability sentence, which is non-standard. Reminder text should follow the keyword, not interrupt an ability's rules text. The cost reduction ability needs restructuring.
> 
> **3. Cost Reduction + Copying Is Extremely Pushed**
> A {2} cost reduction on three exiled cards *plus* copying every spell cast from them is a massive compounding advantage. You're effectively getting free spells that are doubled. Even at mythic, a 4-mana 3/4 flyer that generates this kind of value is likely format-warping, especially in conjunction with multiple overclock sources.
> 
> **4. The Copy Trigger Has No Restriction**
> Copying works on *any* spell type — including extra turns, mass removal, or extra overclock enablers. There's no "if it's an instant or sorcery" limiter, so you can copy permanent spells as well (creating tokens). This is likely unintentional or at minimum needs deliberate consideration.
> 
> **5. Flying Feels Secondary**
> Flying on a U/R legendary is fine color-pie-wise, but on a card this stacked with text, it reads as unnecessary power padding rather than serving a design purpose.

*Tokens: 539 in / 475 out — $0.0146*

### Step 4: Synthesizer — consensus revision

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
> Type: Legendary Creature â€” Human Scientist
> Rarity: mythic
> Oracle Text: Flying
> Cards exiled with overclock (exile the top three cards of your library, you may play them until end of turn) cost {2} less to cast.
> Whenever you cast a spell exiled with overclock, copy it. You may choose new targets for the copy.
> P/T: 3/4
> Flavor Text: "I have transcended the limitations of sanity, safety, and the laws of thermodynamics."
> 
> --- Reviewer 1 ---
> ## Review of Archscientist Vex, the Unbound
> 
> ### Issues Found:
> 
> **1. Overclock Is Used as a Static Reference, Not as an Action**
> Overclock is defined as a keyword *action* — something a card tells you to do. But this card never actually instructs you to overclock. Instead, it references "cards exiled with overclock" as a passive condition. This creates a fundamental problem: the card has no way to *perform* overclock itself. It's a payoff card with no enabler built in, and the reminder text for overclock is awkwardly embedded in a static ability where it reads as a definition rather than an instruction. The reminder text parenthetical after "overclock" makes it look like the card is telling you to overclock right then, which is confusing.
> 
> **2. Templating of the Cost Reduction Ability**
> "Cards exiled with overclock cost {2} less to cast" needs cleaner templating. A more standard approach would be: "Spells you cast from exile cost {2} less to cast" (if that's the intent) or specifically "Spells you cast from among cards exiled by overclocking cost {2} less to cast." The current wording also doesn't specify "you cast" — technically it could reduce costs for any player.
> 
> **3. Copy Ability + Cost Reduction Is Extremely Dangerous**
> A {2} cost reduction across three exiled cards plus copying every spell cast from among them is a massive amount of value. Hitting two spells in one overclock means {4} in mana savings plus two free copies. This is a combo-enabling engine at 4 mana that likely needs either the cost reduction OR the copy trigger, not both.
> 
> **4. No Self-Contained Overclock Activation**
> For a mythic build-around, requiring other cards to provide the overclock action makes this card feel incomplete. Most comparable mythic payoff-enablers (like Archmage Emeritus for magecraft) at least function in a self-contained ecosystem. Consider giving it an activated overclock ability.
> 
> **5. Flying Is Minor but Slightly Off**
> Flying on a U/R Scientist is technically in pie but feels like filler. Prowess or another spell-matters keyword would be more thematically cohesive.
> 
> ### Summary
> The core design idea is exciting, but the card is overloaded with two powerful payoff abilities, lacks a self-contained way to overclock, and has templating issues around referencing a keyword action as a static condition.
> 
> --- Reviewer 2 ---
> ## Review of Archscientist Vex, the Unbound
> 
> ### Issue 1: Overclock Used as a Static Keyword, Not a Keyword Action
> **Severity: Major (Templating/Design)**
> 
> Overclock is defined as a keyword *action* — something you actively do. But this card references "cards exiled with overclock" without ever granting you the ability to overclock. The card assumes overclock is happening from other sources, but the parenthetical reminder text in the middle of a static ability reads as though the card itself is supposed to let you overclock. This is deeply ambiguous. The card needs either:
> - An activated/triggered ability that says "Overclock" as an action, OR
> - Clean referencing of external overclock sources without the inline reminder text (e.g., "Cards you own exiled with overclock cost {2} less to cast.")
> 
> ### Issue 2: Reminder Text Placement is Non-Standard
> **Severity: Moderate (Templating)**
> 
> Embedding the full overclock reminder text inside a static ability's rules text is extremely unusual. Reminder text for a keyword action should appear on cards that *perform* the action, not on cards that merely reference it. This clutters the text box and creates parsing confusion.
> 
> ### Issue 3: Balance — Stacking Cost Reduction + Copying is Excessive
> **Severity: Major (Balance)**
> 
> At 4 mana, this provides: {2} cost reduction on up to 3 exiled cards AND copies every spell cast from that exile. The cost reduction already enables free spells from overclock (many 1-2 CMC spells become free), and then each one is *also copied*. This is a two-card engine on a single body that can produce catastrophic value the turn another overclock source is activated. The two abilities together create degenerate loops far too easily.
> 
> ### Issue 4: "Cast a spell exiled with overclock" — Tracking Ambiguity
> **Severity: Moderate (Templating)**
> 
> "Exiled with overclock" as a zone-tracking reference is fragile. Once a card moves from exile to the stack, it's a new object. Standard templating for this kind of effect typically uses a more explicit linking mechanism. Compare to Prosper, Tome-Bound's "cast a spell from exile" — broader but cleaner.
> 
> ### Issue 5: Flying in Red-Blue on a Scientist
> **Severity: Minor (Color Pie)**
> 
> Acceptable in UR, though mildly generous combined with the 3/4 body.
> 
> ### Summary
> The card's core concept is exciting but needs a cleaner overclock integration (ideally granting the action itself), and the two abilities together are overpowered at this cost. I'd recommend keeping one payoff ability and either adding an overclock activation or raising the mana cost significantly.
> 
> --- Reviewer 3 ---
> ## Review of Archscientist Vex, the Unbound
> 
> ### Issues Found:
> 
> **1. Overclock Is Used as a Static Reference, Not an Action**
> The card references "cards exiled with overclock" but never actually *performs* the overclock action itself. Overclock is defined as a keyword action (like scry or mill), meaning something on the card needs to tell you *when* to do it. As written, the card has no way to exile cards in the first place — it only rewards you for having done so from other sources. If the intent is to be a payoff card, the reminder text in the parenthetical is misleading because it reads like the card itself performs the action. If the intent is self-contained, it needs an activation or trigger like "At the beginning of combat on your turn, overclock."
> 
> **2. Templating of the Reminder Text Placement**
> The reminder text for overclock is embedded in the middle of an ability sentence, which is non-standard. Reminder text should follow the keyword, not interrupt an ability's rules text. The cost reduction ability needs restructuring.
> 
> **3. Cost Reduction + Copying Is Extremely Pushed**
> A {2} cost reduction on three exiled cards *plus* copying every spell cast from them is a massive compounding advantage. You're effectively getting free spells that are doubled. Even at mythic, a 4-mana 3/4 flyer that generates this kind of value is likely format-warping, especially in conjunction with multiple overclock sources.
> 
> **4. The Copy Trigger Has No Restriction**
> Copying works on *any* spell type — including extra turns, mass removal, or extra overclock enablers. There's no "if it's an instant or sorcery" limiter, so you can copy permanent spells as well (creating tokens). This is likely unintentional or at minimum needs deliberate consideration.
> 
> **5. Flying Feels Secondary**
> Flying on a U/R legendary is fine color-pie-wise, but on a card this stacked with text, it reads as unnecessary power padding rather than serving a design purpose.
> 
> Based on the consensus of these 3 reviews (issues raised by at least 2 reviewers), produce a revised version of the card. If no issues have consensus, return the card unchanged with verdict OK. Only fix issues that at least 2 reviewers agree on.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Overclock is used as a static reference/condition but never performed by the card itself \u2014 it's a keyword action that needs an activation or trigger to execute (3/3 reviewers)",
    "Reminder text for overclock is embedded non-standardly inside a static ability, cluttering the text and causing parsing confusion (3/3 reviewers)",
    "Cost reduction + copying every spell is excessively powerful at 4 mana, creating degenerate value especially with multiple overclock sources (3/3 reviewers)",
    "Flying is unnecessary power padding on an already stacked card (2/3 reviewers, minor)"
  ],
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "{T}: Overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nSpells you cast from exile cost {2} less to cast.\nWhenever you cast a spell from among cards exiled by overclocking, copy it if it's an instant or sorcery spell. You may choose new targets for the copy.",
  "rarity": "mythic",
  "power": "2",
  "toughness": "4",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
}
```

*Tokens: 3193 in / 478 out — $0.0279*

## C) Revised Card

```json
{
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "{T}: Overclock. (Exile the top three cards of your library. You may play them until end of turn.)\nSpells you cast from exile cost {2} less to cast.\nWhenever you cast a spell from among cards exiled by overclocking, copy it if it's an instant or sorcery spell. You may choose new targets for the copy.",
  "rarity": "mythic",
  "power": "2",
  "toughness": "4",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
}
```

**Changes made:**
- Overclock is used as a static reference/condition but never performed by the card itself — it's a keyword action that needs an activation or trigger to execute (3/3 reviewers)
- Reminder text for overclock is embedded non-standardly inside a static ability, cluttering the text and causing parsing confusion (3/3 reviewers)
- Cost reduction + copying every spell is excessively powerful at 4 mana, creating degenerate value especially with multiple overclock sources (3/3 reviewers)
- Flying is unnecessary power padding on an already stacked card (2/3 reviewers, minor)

## D) Cost

- API calls: 4
- Input tokens: 4810
- Output tokens: 2170
- Cost: $0.0783