# Card 15: Archscientist Vex, the Unbound — Strategy: s8-split-opus

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
> Type: Legendary Creature â€” Human Scientist
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
> Here are the templating issues I found:
> 
> ---
> 
> **Issue 1: Overclock reminder text should not be embedded inline in a static ability.**
> 
> The current text places the full overclock reminder text parenthetically inside the static ability sentence, which is not how keyword actions work in MTG templating. A keyword action (like overclock) is used as a verb in sentences that tell you to perform it (e.g., "overclock" as an instruction). It should not be defined mid-sentence inside a static ability that merely references cards exiled by the action.
> 
> The card has no ability that actually instructs you to **perform** overclock. It only references cards that were exiled by overclock from other sources. The reminder text for overclock belongs on the card that tells you to overclock, not on a card that passively references it.
> 
> **Fix:** Remove the inline reminder text from the static ability. If you want reminder text for overclock on this card (for clarity at mythic), add it after an ability that actually uses the keyword action, or include a brief italicized note. The static ability should read cleanly:
> 
> > Cards you've exiled by overclocking cost {2} less to cast.
> 
> or
> 
> > Spells you cast from exile that were exiled with overclock cost {2} less to cast.
> 
> **Issue 2: "Cards exiled with overclock cost {2} less to cast" — imprecise templating.**
> 
> This doesn't specify "you" as the controller/owner, and "cards" should clarify they are being cast as "spells." Standard templating for cost reduction references spells you cast. Compare Goblin Electromancer or Helm of Awakening.
> 
> **Suggested wording:**
> > Spells you cast from among cards you've exiled by overclocking cost {2} less to cast.
> 
> **Issue 3: "Whenever you cast a spell exiled with overclock, copy it" — minor precision.**
> 
> This should say "a spell from among cards exiled by overclocking" or similar, to clearly tie into the keyword action's past results. Also, the copy trigger needs to handle the distinction between permanent spells and non-permanent spells — copying a permanent spell creates a token, while copying an instant/sorcery creates a copy on the stack. Current templating works for instants/sorceries but you may want to restrict it (as printed cards like Thousand-Year Storm do) or leave it open intentionally.
> 
> **Issue 4: Capitalization — "overclock" in the oracle text.**
> 
> In oracle text, keyword actions are not capitalized mid-sentence (correct as written). However, the reminder text parenthetical starts with a lowercase letter after an opening parenthesis mid-sentence, which is standard — this part is fine.
> 
> ---
> 
> **Summary:** The main problems are embedding overclock's reminder text inside a passive/static ability rather than on an ability that performs the action, and the cost-reduction line needing tighter templating to specify "spells you cast" and connect to the overclock exile zone properly.

*Tokens: 592 in / 679 out — $0.0199*

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
> Type: Legendary Creature â€” Human Scientist
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
> I need to analyze this card carefully against the checklist and general design principles.
> 
> **Keyword Nonbos:** Flying on a UR Legendary Scientist feels tacked on but isn't a nonbo mechanically. No issues here.
> 
> **Conditional Analysis:** The abilities trigger off "cards exiled with overclock" — but the card itself has no way to overclock. It has the reminder text parenthetically, but that's just a reminder of what overclock does, not an activated or triggered ability that performs overclock. The card is entirely dependent on other cards in your deck to do anything beyond being a 3/4 flyer for 4. This is acceptable for a build-around mythic legendary, but worth flagging that the reminder text inclusion is slightly misleading — it looks like the card itself overclocks.
> 
> **Kitchen Sink Check:** Three abilities — Flying, cost reduction for overclock cards, and copying overclock spells. Flying feels unrelated to the overclock theme. The cost reduction and copy trigger are synergistic and focused. **Flying reads as kitchen sink filler** to boost the card's power rather than serving the mechanical identity.
> 
> **Variability Check:** The cost reduction is always {2}, the copy is always one copy — no false variability issues.
> 
> **Focused Purpose:** The overclock synergy package (cost reduction + copy) is a clear, focused build-around. That part is excellent.
> 
> **Additional Issues:**
> 
> - **Power level concern:** Cost reduction of {2} AND copying every overclock spell is extremely explosive. Overclock exiles 3 cards; if even two are castable, you're getting massive mana savings plus free copies. This is a two-card-combo-level payoff that likely warps games immediately.
> - **The copy trigger on lands:** Overclock says "play," so you can play lands. "Whenever you cast a spell" correctly excludes lands, which is fine.
> - **Reminder text in oracle text** is unconventional formatting — overclock isn't a keyword this card possesses, so the inline reminder text is awkward.
> 
> **Design Issues Found:**
> 
> 1. **Kitchen sink — Flying is unrelated filler** that doesn't serve the overclock theme.
> 2. **The card doesn't itself overclock**, making it purely parasitic on other sources, yet the formatting somewhat obscures this.

*Tokens: 601 in / 519 out — $0.0160*

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
> Type: Legendary Creature â€” Human Scientist
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
> # Balance Analysis: Archscientist Vex, the Unbound
> 
> ## Card Breakdown
> 
> 4 mana (2UR) for a 3/4 flyer is already a solid body. The card then provides **two** extremely powerful static/triggered abilities that stack on the overclock mechanic:
> 
> 1. **Cost reduction of {2}** on all overclocked cards
> 2. **Copy every spell cast from overclock**
> 
> ## Key Concern: The Abilities Stack Multiplicatively
> 
> The cost reduction makes it trivial to chain overclocked spells, and **every single one gets copied**. This isn't "cast one big spell and copy it" — this is "cast potentially 2-3 spells from each overclock activation, and copy ALL of them."
> 
> With a single overclock activation (3 cards exiled), a realistic turn looks like:
> - Cast a 3-mana spell for {1} → get a copy (2 spells)
> - Cast a 2-mana spell for {0} → get a copy (2 more spells)
> - That's 4 spells worth of value from one overclock trigger, plus Vex is still on board.
> 
> ## Comparisons
> 
> | Card | Cost | What it does |
> |---|---|---|
> | **Archmage Emeritus** | 2UU | Draws a card per spell — no copying, no cost reduction |
> | **Double Vision** | 3RR | Copies first instant/sorcery per turn — 5 mana enchantment, once per turn |
> | **Goblin Electromancer** | UR | Cost reduction only, 2/2 body, no copying |
> 
> Vex is essentially **Goblin Electromancer + Double Vision (without the once-per-turn limit)** on a 3/4 flying body for 4 mana. Double Vision alone costs 5 mana and is limited to once per turn.
> 
> ## Verdict
> 
> **BALANCE ISSUE — The copy ability should be limited to once per turn.**
> 
> The cost reduction alone is a strong mythic ability. Unlimited copying on top of it creates degenerate turns too easily. Adding "the first spell you cast from exile each turn" to the copy trigger would preserve the mythic build-around excitement while preventing the card from being a one-turn-kill engine the moment any overclock source is activated.

*Tokens: 623 in / 546 out — $0.0168*

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
> Type: Legendary Creature â€” Human Scientist
> Rarity: mythic
> Oracle Text: Flying
> Cards exiled with overclock (exile the top three cards of your library, you may play them until end of turn) cost {2} less to cast.
> Whenever you cast a spell exiled with overclock, copy it. You may choose new targets for the copy.
> P/T: 3/4
> Flavor Text: "I have transcended the limitations of sanity, safety, and the laws of thermodynamics."
> 
> Issues found:
> - Templating: Here are the templating issues I found:
> 
> ---
> 
> **Issue 1: Overclock reminder text should not be embedded inline in a static ability.**
> 
> The current text places the full overclock reminder text parenthetically inside the static ability sentence, which is not how keyword actions work in MTG templating. A keyword action (like overclock) is used as a verb in sentences that tell you to perform it (e.g., "overclock" as an instruction). It should not be defined mid-sentence inside a static ability that merely references cards exiled by the action.
> 
> The card has no ability that actually instructs you to **perform** overclock. It only references cards that were exiled by overclock from other sources. The reminder text for overclock belongs on the card that tells you to overclock, not on a card that passively references it.
> 
> **Fix:** Remove the inline reminder text from the static ability. If you want reminder text for overclock on this card (for clarity at mythic), add it after an ability that actually uses the keyword action, or include a brief italicized note. The static ability should read cleanly:
> 
> > Cards you've exiled by overclocking cost {2} less to cast.
> 
> or
> 
> > Spells you cast from exile that were exiled with overclock cost {2} less to cast.
> 
> **Issue 2: "Cards exiled with overclock cost {2} less to cast" — imprecise templating.**
> 
> This doesn't specify "you" as the controller/owner, and "cards" should clarify they are being cast as "spells." Standard templating for cost reduction references spells you cast. Compare Goblin Electromancer or Helm of Awakening.
> 
> **Suggested wording:**
> > Spells you cast from among cards you've exiled by overclocking cost {2} less to cast.
> 
> **Issue 3: "Whenever you cast a spell exiled with overclock, copy it" — minor precision.**
> 
> This should say "a spell from among cards exiled by overclocking" or similar, to clearly tie into the keyword action's past results. Also, the copy trigger needs to handle the distinction between permanent spells and non-permanent spells — copying a permanent spell creates a token, while copying an instant/sorcery creates a copy on the stack. Current templating works for instants/sorceries but you may want to restrict it (as printed cards like Thousand-Year Storm do) or leave it open intentionally.
> 
> **Issue 4: Capitalization — "overclock" in the oracle text.**
> 
> In oracle text, keyword actions are not capitalized mid-sentence (correct as written). However, the reminder text parenthetical starts with a lowercase letter after an opening parenthesis mid-sentence, which is standard — this part is fine.
> 
> ---
> 
> **Summary:** The main problems are embedding overclock's reminder text inside a passive/static ability rather than on an ability that performs the action, and the cost-reduction line needing tighter templating to specify "spells you cast" and connect to the overclock exile zone properly.
> - Mechanics: I need to analyze this card carefully against the checklist and general design principles.
> 
> **Keyword Nonbos:** Flying on a UR Legendary Scientist feels tacked on but isn't a nonbo mechanically. No issues here.
> 
> **Conditional Analysis:** The abilities trigger off "cards exiled with overclock" — but the card itself has no way to overclock. It has the reminder text parenthetically, but that's just a reminder of what overclock does, not an activated or triggered ability that performs overclock. The card is entirely dependent on other cards in your deck to do anything beyond being a 3/4 flyer for 4. This is acceptable for a build-around mythic legendary, but worth flagging that the reminder text inclusion is slightly misleading — it looks like the card itself overclocks.
> 
> **Kitchen Sink Check:** Three abilities — Flying, cost reduction for overclock cards, and copying overclock spells. Flying feels unrelated to the overclock theme. The cost reduction and copy trigger are synergistic and focused. **Flying reads as kitchen sink filler** to boost the card's power rather than serving the mechanical identity.
> 
> **Variability Check:** The cost reduction is always {2}, the copy is always one copy — no false variability issues.
> 
> **Focused Purpose:** The overclock synergy package (cost reduction + copy) is a clear, focused build-around. That part is excellent.
> 
> **Additional Issues:**
> 
> - **Power level concern:** Cost reduction of {2} AND copying every overclock spell is extremely explosive. Overclock exiles 3 cards; if even two are castable, you're getting massive mana savings plus free copies. This is a two-card-combo-level payoff that likely warps games immediately.
> - **The copy trigger on lands:** Overclock says "play," so you can play lands. "Whenever you cast a spell" correctly excludes lands, which is fine.
> - **Reminder text in oracle text** is unconventional formatting — overclock isn't a keyword this card possesses, so the inline reminder text is awkward.
> 
> **Design Issues Found:**
> 
> 1. **Kitchen sink — Flying is unrelated filler** that doesn't serve the overclock theme.
> 2. **The card doesn't itself overclock**, making it purely parasitic on other sources, yet the formatting somewhat obscures this.
> - Balance: # Balance Analysis: Archscientist Vex, the Unbound
> 
> ## Card Breakdown
> 
> 4 mana (2UR) for a 3/4 flyer is already a solid body. The card then provides **two** extremely powerful static/triggered abilities that stack on the overclock mechanic:
> 
> 1. **Cost reduction of {2}** on all overclocked cards
> 2. **Copy every spell cast from overclock**
> 
> ## Key Concern: The Abilities Stack Multiplicatively
> 
> The cost reduction makes it trivial to chain overclocked spells, and **every single one gets copied**. This isn't "cast one big spell and copy it" — this is "cast potentially 2-3 spells from each overclock activation, and copy ALL of them."
> 
> With a single overclock activation (3 cards exiled), a realistic turn looks like:
> - Cast a 3-mana spell for {1} → get a copy (2 spells)
> - Cast a 2-mana spell for {0} → get a copy (2 more spells)
> - That's 4 spells worth of value from one overclock trigger, plus Vex is still on board.
> 
> ## Comparisons
> 
> | Card | Cost | What it does |
> |---|---|---|
> | **Archmage Emeritus** | 2UU | Draws a card per spell — no copying, no cost reduction |
> | **Double Vision** | 3RR | Copies first instant/sorcery per turn — 5 mana enchantment, once per turn |
> | **Goblin Electromancer** | UR | Cost reduction only, 2/2 body, no copying |
> 
> Vex is essentially **Goblin Electromancer + Double Vision (without the once-per-turn limit)** on a 3/4 flying body for 4 mana. Double Vision alone costs 5 mana and is limited to once per turn.
> 
> ## Verdict
> 
> **BALANCE ISSUE — The copy ability should be limited to once per turn.**
> 
> The cost reduction alone is a strong mythic ability. Unlimited copying on top of it creates degenerate turns too easily. Adding "the first spell you cast from exile each turn" to the copy trigger would preserve the mythic build-around excitement while preventing the card from being a one-turn-kill engine the moment any overclock source is activated.
> 
> Produce a revised version that fixes all identified issues while preserving the card's core identity and purpose. Do not change things that weren't flagged as issues. If all reviews said PASS, return the card unchanged with verdict OK.

**Tool call result:**
```json
{
  "changed": true,
  "verdict": "REVISED",
  "issues_found": [
    "Templating: Overclock reminder text embedded inline in a static ability that doesn't perform overclock \u2014 reminder text belongs on cards that instruct you to overclock, not on passive references",
    "Templating: Cost reduction line doesn't specify 'spells you cast' or connect properly to the overclock exile zone",
    "Templating: Copy trigger needs tighter wording to reference cards exiled by overclocking",
    "Mechanics: Flying is kitchen sink filler unrelated to the overclock theme",
    "Balance: Unlimited copying of ALL overclock spells combined with {2} cost reduction is far too explosive \u2014 should be limited to once per turn"
  ],
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "rarity": "mythic",
  "oracle_text": "Spells you cast from among cards you've exiled by overclocking cost {2} less to cast.\nWhenever you cast the first spell each turn from among cards you've exiled by overclocking, copy it. You may choose new targets for the copy.",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
}
```

*Tokens: 3190 in / 459 out — $0.0274*

## C) Revised Card

```json
{
  "name": "Archscientist Vex, the Unbound",
  "mana_cost": "{2}{U}{R}",
  "type_line": "Legendary Creature \u2014 Human Scientist",
  "oracle_text": "Spells you cast from among cards you've exiled by overclocking cost {2} less to cast.\nWhenever you cast the first spell each turn from among cards you've exiled by overclocking, copy it. You may choose new targets for the copy.",
  "rarity": "mythic",
  "power": "3",
  "toughness": "4",
  "flavor_text": "\"I have transcended the limitations of sanity, safety, and the laws of thermodynamics.\""
}
```

**Changes made:**
- Templating: Overclock reminder text embedded inline in a static ability that doesn't perform overclock — reminder text belongs on cards that instruct you to overclock, not on passive references
- Templating: Cost reduction line doesn't specify 'spells you cast' or connect properly to the overclock exile zone
- Templating: Copy trigger needs tighter wording to reference cards exiled by overclocking
- Mechanics: Flying is kitchen sink filler unrelated to the overclock theme
- Balance: Unlimited copying of ALL overclock spells combined with {2} cost reduction is far too explosive — should be limited to once per turn

## D) Cost

- API calls: 4
- Input tokens: 5006
- Output tokens: 2203
- Cost: $0.0801