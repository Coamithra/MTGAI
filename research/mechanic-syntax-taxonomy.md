# MTG Mechanic Syntax Taxonomy

> Reference for the `mechanics` stage prompts. Goal: teach a local LLM **"here are all
> the legal shapes a mechanic can take"** by canonical example instead of by a prose
> checklist of do's/don'ts. Every reminder text below is **verbatim** from official
> sources (see Sources). Reminder text is the parenthesized italic definition; in our
> schema it is `reminder_text`, the keyword's real definition (`reminder_injector`
> stamps it onto cards downstream).

## The three `keyword_type` buckets

- **keyword ability** (`keyword_ability`) — a named ability with a rules meaning. The
  richest bucket; decomposes into syntactic shapes A–G below. Reminder text *defines*
  the keyword.
- **ability word** (`ability_word`) — CR 207.2c: *"An ability word appears in italics at
  the beginning of some abilities. Ability words are similar to keywords in that they tie
  together cards that have similar functionality, but they have no special rules meaning
  and no individual entries in the Comprehensive Rules."* Italic flavor label, **no
  reminder text** — each card writes its own full ability after the word.
- **keyword action** (`keyword_action`) — CR 701.1: a *specialized verb* ("some
  specialized verbs are used whose meanings may not be clear … sometimes reminder text
  summarizes their meanings"). The reminder defines the verb's game action.

## The complete shape set

Every legal mechanic definition reduces to one of these nine shapes. The bucket follows
the **syntax of the reminder**, not the mechanic's name or flavor.

| # | keyword_type | Shape | Reminder pattern | Canonical example |
|---|---|---|---|---|
| A | keyword_ability | Bare static keyword | `(This creature <static rule>.)` | Flying |
| B | keyword_ability | `Keyword N` (numeric parameter) | `(… <N spelled out> …)` | Crew 4, Annihilator 2 |
| C | keyword_ability | `Keyword {cost}` → activated ability | `({cost}: <effect>. <timing>.)` | Equip {1}, Cycling {2} |
| D | keyword_ability | Triggered ability | `(When/Whenever …, <effect>.)` | Prowess, Cascade |
| E | keyword_ability | Static / replacement effect | `(When this dies… / This enters with…)` | Undying, Vanishing 3 |
| F | keyword_ability | Casting modifier `Keyword {cost}` | `(You may cast … for its <name> cost…)` | Flashback, Convoke, Madness |
| G | keyword_ability | **Kicker shape** — shared cost, card-defined effect | `(You may pay an additional {cost}…)` — **no payoff in reminder** | Kicker, Spree, Bargain |
| H | ability_word | Italic flavor label, **no reminder** | `Word — <condition>, <effect>` (full ability on the card) | Landfall, Delirium |
| I | keyword_action | Specialized verb (+ optional N) | `(To <verb> N, <defined action>.)` | Scry N, Investigate |

---

## Shape A — Bare static keyword (the word *is* the whole ability)

Single parenthetical gloss; no parameter, no cost.

- **Flying** — `(This creature can't be blocked except by creatures with flying or reach.)`
- **Trample** — `(This creature can deal excess combat damage to the player or planeswalker it's attacking.)`
- **Lifelink** — `(Damage dealt by this creature also causes you to gain that much life.)`
- **Deathtouch** — `(Any amount of damage this deals to a creature is enough to destroy it.)`
- **Vigilance** — `(Attacking doesn't cause this creature to tap.)`
- **Reach** — `(This creature can block creatures with flying.)`

## Shape B — `Keyword N` (numeric parameter)

N appears on the keyword **and** is spelled out in the reminder; N scales magnitude
(counters / permanents / life). This is how you get clean common/uncommon/rare design
space (N = 1/2/3) without contradicting the reminder.

- **Crew 4** — `(Tap any number of creatures you control with total power 4 or more: This Vehicle becomes an artifact creature until end of turn.)`
- **Annihilator 2** — `(Whenever this creature attacks, defending player sacrifices two permanents of their choice.)`
- **Devour 1** — `(As this creature enters, you may sacrifice any number of creatures. It enters with that many +1/+1 counters on it.)`
- **Bloodthirst 2** — `(If an opponent was dealt damage this turn, this creature enters with two +1/+1 counters on it.)`
- **Fading 5** — `(This creature enters with five fade counters on it. At the beginning of your upkeep, remove a fade counter from it. If you can't, sacrifice it.)`
- **Modular 3** — `(This creature enters with three +1/+1 counters on it. When it dies, you may put its +1/+1 counters on target artifact creature.)`

## Shape C — `Keyword {cost}` → reminder expands the full activated ability

The cost lives appended to the keyword on the card; the reminder restates the cost
before the colon, the effect after, plus any timing restriction (most: "only as a
sorcery").

- **Equip {1}** — `({1}: Attach to target creature you control. Equip only as a sorcery.)`
- **Cycling {2}** — `({2}, Discard this card: Draw a card.)`
- **Unearth {1}{B}** — `({1}{B}: Return this card from your graveyard to the battlefield. It gains haste. Exile it at the beginning of the next end step or if it would leave the battlefield. Unearth only as a sorcery.)`
- **Level up {W}** — `({W}: Put a level counter on this. Level up only as a sorcery.)`
- **Outlast {W}** — `({W}, {T}: Put a +1/+1 counter on this creature. Outlast only as a sorcery.)`

## Shape D — Triggered ability (reminder begins "When/Whenever…")

- **Cascade** — `(When you cast this spell, exile cards from the top of your library until you exile a nonland card that costs less. You may cast it without paying its mana cost. Put the exiled cards on the bottom in a random order.)`
- **Prowess** — `(Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)`
- **Exalted** — `(Whenever a creature you control attacks alone, that creature gets +1/+1 until end of turn.)`
- **Battle cry** — `(Whenever this creature attacks, each other attacking creature gets +1/+0 until end of turn.)`
- **Afflict 3** — `(Whenever this creature becomes blocked, defending player loses 3 life.)` *(trigger + numeric parameter — shapes compose)*
- **Evolve** — `(Whenever a creature you control enters, if that creature has greater power or toughness than this creature, put a +1/+1 counter on this creature.)`
- **Mentor** — `(Whenever this creature attacks, put a +1/+1 counter on target attacking creature with lesser power.)`

## Shape E — Static / replacement effect (alters how things happen)

Often "enters with…" or "When this dies, return…".

- **Undying** — `(When this creature dies, if it had no +1/+1 counters on it, return it to the battlefield under its owner's control with a +1/+1 counter on it.)`
- **Persist** — `(When this creature dies, if it had no -1/-1 counters on it, return it to the battlefield under its owner's control with a -1/-1 counter on it.)`
- **Vanishing 3** — `(This creature enters with three time counters on it. At the beginning of your upkeep, remove a time counter from it. When the last is removed, sacrifice it.)`
- **Riot** — `(This creature enters with your choice of a +1/+1 counter or haste.)`

## Shape F — Casting modifier (alternative/additional cost, cost reduction, or alternate zone)

Where a cost varies per card it is appended to the keyword.

- **Flashback {3}{R}** — `(You may cast this card from your graveyard for its flashback cost. Then exile it.)` *(alternate zone)*
- **Foretell {4}{U}{U}** — `(During your turn, you may pay {2} and exile this card from your hand face down. Cast it on a later turn for its foretell cost.)`
- **Overload {3}{U}** — `(You may cast this spell for its overload cost. If you do, change "target" in its text to "each.")`
- **Convoke** — `(Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)` *(cost-payment aid, no parameter)*
- **Affinity for artifacts** — `(This spell costs {1} less to cast for each artifact you control.)` *(templated "Affinity for <thing>")*
- **Madness {1}{R}** — `(If you discard this card, discard it into exile. When you do, cast it for its madness cost or put it into your graveyard.)`
- **Delve** — `(Each card you exile from your graveyard while casting this spell pays for {1}.)`
- **Escape—{3}{R}{G}, Exile three other cards from your graveyard** — `(You may cast this card from your graveyard for its escape cost.)` *(em-dash separator + extra cost on the keyword line)*

## Shape G — The "Kicker shape" (shared cost/choice, card-defined effect)

The reminder describes **only the shared cost or choice mechanism; the EFFECT lives in
the card's own rules text** and is never stated in the reminder. The two example cards
*should* differ in effect — that is the design, not an inconsistency. **Never** put an
`[effect]` placeholder in the reminder.

- **Kicker {2}** — `(You may pay an additional {2} as you cast this spell.)` — reminder = cost only; "if kicked…" payoff is the card's separate text.
- **Multikicker {1}{W}** — `(You may pay an additional {1}{W} any number of times as you cast this spell.)`
- **Escalate {2}** — `(Pay this cost for each mode chosen beyond the first.)`
- **Entwine {2}** — `(Choose both if you pay the entwine cost.)`
- **Spree** — `(Choose one or more additional costs.)`
- **Bargain** — `(You may sacrifice an artifact, enchantment, or token as you cast this spell.)`

## Shape H — Ability words (italic flavor label, NO reminder text)

The word has no rules meaning; the card supplies the whole ability after an em-dash.
Form: `Word — <condition>, <effect>`. There is **no parenthesized reminder** for an
ability word.

- **Landfall** (Lotus Cobra) — "Landfall — Whenever a land you control enters, add one mana of any color."
- **Threshold** (Nimble Mongoose) — "Threshold — This creature gets +2/+2 as long as there are seven or more cards in your graveyard."
- **Domain** (Tribal Flames) — "Domain — Tribal Flames deals X damage to any target, where X is the number of basic land types among lands you control."
- **Constellation** (Eidolon of Blossoms) — "Constellation — Whenever this creature or another enchantment you control enters, draw a card."
- **Delirium** (Traverse the Ulvenwald) — "Delirium — If there are four or more card types among cards in your graveyard, instead search…"
- **Raid** (Bellowing Saddlebrute) — "Raid — When this creature enters, you lose 4 life unless you attacked this turn."
- **Coven** (Candlegrove Witch) — "Coven — At the beginning of combat on your turn, if you control three or more creatures with different powers, this creature gains flying until end of turn."

## Shape I — Keyword actions (specialized verb + parenthesized definition; many take N)

- **Scry N** (Preordain) — `(To scry 2, look at the top two cards of your library, then put any number of them on the bottom and the rest on top in any order.)`
- **Surveil N** (Discovery) — `(To surveil 2, look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)`
- **Explore** (Merfolk Branchwalker) — `(Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on this creature, then put the card back or put it into your graveyard.)`
- **Investigate** (Tireless Tracker) — `(Create a Clue token. It's an artifact with "{2}, Sacrifice this token: Draw a card.")`
- **Amass [Type] N** (Lazotep Plating) — `(Put a +1/+1 counter on an Army you control. It's also a Zombie. If you don't control an Army, create a 0/0 black Zombie Army creature token first.)`
- **Goad** (Disrupt Decorum) — `(Until your next turn, those creatures attack each combat if able and attack a player other than you if able.)`
- **Mill N** (Ruin Crab) — `(To mill a card, a player puts the top card of their library into their graveyard.)`
- **Connive N** (Raffine) — `(Draw X cards, then discard X cards. Put a +1/+1 counter on that creature for each nonland card discarded this way.)`
- **Venture into the dungeon** (Cloister Gargoyle) — `(Enter the first room or advance to the next room.)`
- **Populate** (Growing Ranks) — `(Create a token that's a copy of a creature token you control.)`
- **Proliferate** (Contagion Clasp) — `(Choose any number of permanents and/or players, then give each another counter of each kind already there.)`

---

## Categorization notes & ambiguities

The bucket/shape follows the **syntax of the reminder text**, not the mechanic's name:

- **Riot** is colloquially a "trigger" but its reminder is a *replacement* ("enters with
  your choice…") → shape E, not D.
- **Dethrone** reads as static but its reminder begins "Whenever…" → shape D (triggered).
- **Fabricate** is a *triggered keyword ability* (`Fabricate 3 (When this enters…)`),
  **not** a bare keyword action — its reminder describes the trigger. Contrast with
  Scry/Mill whose reminders describe only the verb's action.
- **Investigate / Amass / Connive** are keyword-action *verbs used inside other
  abilities*, rarely standalone keywords.
- A mechanic can **compose** shapes: `Afflict N` is triggered (D) + numeric (B).

## Uncertainties (flagged during research)

- **Menace** self-form reminder is high-confidence but not character-verified; only the
  *granted* parenthetical `(It can't be blocked except by two or more creatures.)` was
  fetched verbatim.
- **Poisonous** verbatim text is Sliver-specific (`poisonous 1` … "a Sliver deals combat
  damage") — no generic self-card template was ever printed.
- "Ability words have no reminder text" is established by inference (CR 207.2c "no
  special rules meaning" + every example carrying no parenthetical), not one literal
  sentence.

## Sources

- **CR 701.1** (keyword-action definition) — `https://api.academyruins.com/cr/701.1`
- **CR 207.2c** (ability-word definition + full enumeration) — `https://yawgatog.com/resources/magic-rules/`
- **Reminder text** — Scryfall API official Oracle text, `https://api.scryfall.com/cards/named?exact=<card>`, for every card cited above. (mtg.wiki and mtg.fandom.com returned HTTP 403 to the fetcher; the Scryfall API serves authoritative Oracle text and was used throughout.)
