# Model Comparison Scores — Task 0D-4

**Date**: 2026-03-08
**Models**: Claude Sonnet (`claude-sonnet-4-20250514`), GPT-4o (`gpt-4o`), GPT-4o-mini (`gpt-4o-mini`)
**Temperature**: 0.7 for all calls
**System prompt**: `system-prompt-v1.md` (v1, ~5,000 chars)

---

## Scoring Criteria (1-5 scale)

| Score | Meaning |
|-------|---------|
| 5 | Excellent — production-ready, indistinguishable from professional design |
| 4 | Good — minor issues, easily fixable |
| 3 | Acceptable — functional but noticeable flaws |
| 2 | Poor — significant problems that need rework |
| 1 | Failing — fundamentally broken |

---

## Card 1: Common White Creature

| Criterion | Claude Sonnet | GPT-4o | GPT-4o-mini |
|-----------|--------------|--------|-------------|
| **Rules Text** | 5 | 5 | 4 |
| **Balance** | 5 | 4 | 3 |
| **Creativity** | 3 | 3 | 4 |
| **JSON Validity** | 5 | 5 | 5 |
| **Subtotal** | **18** | **17** | **16** |

### Notes

- **Claude Sonnet** — "Devoted Sentinel" {1}{W} 2/1 Vigilance. Perfectly clean common. P+T=3 = CMC+1, totally appropriate with a keyword. Uses `~` correctly (not needed here since there's no self-reference). Single keyword, NWO-compliant. Flavor text is clean but generic.

- **GPT-4o** — "Dawnlight Cavalier" {2}{W} 2/2 Vigilance. Also clean, but a 3-mana 2/2 with vigilance is slightly below rate — most 3-mana white commons at this stat line are unremarkable. P+T=4 = CMC+1, slightly conservative. Functional but unexciting.

- **GPT-4o-mini** — "Dawnwatch Sentry" {2}{W} 2/2 Vigilance + ETB create 1/1 Soldier token. Two abilities (keyword + triggered) pushes NWO complexity for common. A 3-mana 2/2 that creates a 1/1 token is effectively 3 power / 3 toughness across two bodies for 3 mana — this is more of an uncommon power level. The card design itself is *interesting* (higher creativity score) but not appropriate at common per New World Order rules.

---

## Card 2: Uncommon Blue Instant

| Criterion | Claude Sonnet | GPT-4o | GPT-4o-mini |
|-----------|--------------|--------|-------------|
| **Rules Text** | 3 | 4 | 5 |
| **Balance** | 2 | 4 | 5 |
| **Creativity** | 4 | 3 | 4 |
| **JSON Validity** | 5 | 5 | 5 |
| **Subtotal** | **14** | **16** | **19** |

### Notes

- **Claude Sonnet** — "Temporal Insight" {2}{U}: Look at top 4, put 2 in hand, rest on bottom, then draw a card. This is massively overpowered — it's essentially "draw 3 cards and scry 2" for 3 mana at instant speed. Ancestral Recall is 1 mana draw 3 and is banned everywhere. Even at uncommon, 3-mana draw 3+ is busted. The rules text also has a double-backslash issue (`\\n` rendered literally instead of as a newline), though this is a serialization artifact. The design is creative but wildly unbalanced.

- **GPT-4o** — "Temporal Confluence" {2}{U}{U}: Counter target spell + mill 2. Clean rules text using "puts the top two cards of their library into their graveyard" — technically this should use the keyword "mill 2" per modern Oracle templating, but the longform text is technically correct. A 4-mana hard counter with minor upside is reasonably balanced (Cancel is 3 mana, this adds a small mill rider for 1 more mana — slightly weak but printable). Adequate but safe design.

- **GPT-4o-mini** — "Temporal Disruption" {2}{U}: Bounce nonland permanent + Scry 2. Excellent clean design. Rules text is perfectly templated. 3-mana bounce + scry 2 is well-balanced for uncommon (comparable to existing cards like Blink of an Eye with different upside). Good creativity with the scry addition on a bounce spell.

---

## Card 3: Rare Black Legendary Creature

| Criterion | Claude Sonnet | GPT-4o | GPT-4o-mini |
|-----------|--------------|--------|-------------|
| **Rules Text** | 5 | 4 | 5 |
| **Balance** | 4 | 4 | 4 |
| **Creativity** | 5 | 4 | 4 |
| **JSON Validity** | 5 | 5 | 5 |
| **Subtotal** | **19** | **17** | **18** |

### Notes

- **Claude Sonnet** — "Vorthak, Death's Whisper" {2}{B}{B} 3/4 Deathtouch, death trigger recursion, activated destruction. Three abilities is appropriate for rare. Rules text is clean and uses proper MTG templating. The activated ability "{3}{B}{B}, {T}: Destroy target creature. Its controller loses life equal to its mana value." is correctly templated. Deathtouch + recursion + removal creates a cohesive death-themed design. 3/4 for 4 mana with deathtouch is solid. Excellent flavor text. Most creative of the three.

- **GPT-4o** — "Vorthos, Shadow Puppeteer" {2}{B}{B}{B} 4/4 Menace + sacrifice trigger + card draw. Note: "Vorthos" is an existing MTG community term (a player psychographic), which could cause confusion. The rules text is clean. "Pay 2 life" on the death trigger is proper templating. However, the triggered ability says "target opponent" which means the sacrifice trigger targets — this is technically correct but slightly unusual phrasing for this type of effect. 4/4 menace for 5 mana with upside is well-balanced.

- **GPT-4o-mini** — "Veilshadow Tyrant" {3}{B}{B} 5/4 Flying + attack sacrifice trigger + death token creation. Clean rules text. Flying is slightly unusual for black at this rate (black gets flying but usually on smaller creatures or vampires/demons — this is a Zombie Demon so it fits). 5/4 flying for 5 mana is reasonable at rare. The sacrifice-for-discard on attack plus death trigger for tokens creates good synergy.

---

## Card 4: Mythic Planeswalker

| Criterion | Claude Sonnet | GPT-4o | GPT-4o-mini |
|-----------|--------------|--------|-------------|
| **Rules Text** | 5 | 4 | 5 |
| **Balance** | 4 | 3 | 4 |
| **Creativity** | 5 | 3 | 3 |
| **JSON Validity** | 5 | 5 | 5 |
| **Subtotal** | **19** | **15** | **17** |

### Notes

- **Claude Sonnet** — "Kythara, Seer of Storms" {2}{U}{R} Loyalty 4. +1: Scry 2, draw, deal 1 damage. -3: Exile top 4, cast instants/sorceries with cost reduction. -7: Emblem copies all instants/sorceries. Excellent design that feels like a real planeswalker. The +1 is strong but not broken (combines blue and red effects). The -3 is flavorful impulsive draw with cost reduction — very Izzet. The ultimate is powerful and game-ending. Loyalty math works: +1 to 5, can -3 twice before dying. Proper use of `~` for self-reference. The flavor text being present is slightly unusual for planeswalkers (most planeswalkers don't have flavor text in MTG), but the system prompt requested it.

- **GPT-4o** — "Rhyssa, Nature's Conduit" {1}{G}{U} Loyalty 3. +1: Untap up to two lands. -2: Draw 1 (or 2 if flying creature). -6: Emblem draws on creature cast. This is only 2 colors (GU), which meets the minimum requirement. The +1 is somewhat weak and feels more like a green ramp ability. The -2 referencing "a creature with flying" is odd for Simic — flying isn't a core Simic mechanic. The ultimate is a weaker version of common GU effects. Overall feels underpowered for mythic and the mechanics don't synergize tightly. Also, at 3 loyalty with a -2, the planeswalker can only use its minus once before dying to the next +1, which limits play patterns.

- **GPT-4o-mini** — "Elysia, Dreamweaver" {3}{U}{G} Loyalty 4. +1: Scry 2, draw. -2: Create 3/3 Elemental with trample. -7: Emblem draws on creature cast. Clean design with proper loyalty math. The +1 is powerful (unconditional scry 2 + draw every turn). The -2 creates board presence. The ultimate is solid. However, the design is fairly generic — it doesn't have a strong identity beyond "draw cards and make creatures." Similar to GPT-4o's planeswalker but with better numbers.

---

## Card 5: Uncommon Land

| Criterion | Claude Sonnet | GPT-4o | GPT-4o-mini |
|-----------|--------------|--------|-------------|
| **Rules Text** | 5 | 4 | 4 |
| **Balance** | 4 | 5 | 3 |
| **Creativity** | 5 | 4 | 3 |
| **JSON Validity** | 5 | 5 | 4 |
| **Subtotal** | **19** | **18** | **14** |

### Notes

- **Claude Sonnet** — "Moonlit Observatory" (Land, WU). Enters tapped unless 2+ other lands. {T}: Add {W} or {U}. {2}{W}{U}, {T}: Scry 2, draw a card (sorcery speed only). Clean dual land with a utility ability. The conditional ETB tapped is modern design (similar to slow lands). The activated ability is expensive enough to be fair. Color identity correctly lists W and U (from mana abilities). Empty `mana_cost` field is correct for lands. Excellent overall design.

- **GPT-4o** — "Frostfire Crag" (Land, UR). {T}: Add {C}. {1}, {T}: Add {U} or {R}, deals 1 damage. This is a clean painland variant. The colorless mana mode gives flexibility. The {1} mana cost on the colored ability is unusual — most painlands don't require mana to activate. This makes it strictly worse than a basic land for colored mana in most situations (you need to spend mana to get colored mana). Well-balanced but perhaps overly cautious. Color identity correctly set.

- **GPT-4o-mini** — "Verdant Grove" (Land, G). {T}: Add {G}. {T}, Sacrifice: Create 2/2 Wolf with vigilance. Only produces one color, which is simpler than the prompt suggested ("one or two colors"). The `colors` field is set to `["G"]` which is incorrect — lands have no colors (they are colorless permanents regardless of what mana they produce). This is a JSON validity issue. The sacrifice ability is interesting but makes this feel like a worse Khalni Garden variant. Vigilance on a green Wolf token is slightly unusual.

---

## Overall Scores

| Card | Claude Sonnet | GPT-4o | GPT-4o-mini |
|------|--------------|--------|-------------|
| Common White Creature | 18 | 17 | 16 |
| Uncommon Blue Instant | 14 | 16 | 19 |
| Rare Black Legendary | 19 | 17 | 18 |
| Mythic Planeswalker | 19 | 15 | 17 |
| Uncommon Land | 19 | 18 | 14 |
| **Total (out of 100)** | **89** | **83** | **84** |
| **Average per card** | **17.8** | **16.6** | **16.8** |

---

## Token Usage & Cost

### Per-Model Totals

| Metric | Claude Sonnet | GPT-4o | GPT-4o-mini |
|--------|--------------|--------|-------------|
| Total Input Tokens | 11,900 | 6,954 | 6,954 |
| Total Output Tokens | 2,327 | 1,176 | 1,184 |
| Avg Latency (ms) | 9,211 | 3,662 | 5,152 |
| Input Cost | $0.0357 | $0.0174 | $0.00104 |
| Output Cost | $0.0349 | $0.0118 | $0.00071 |
| **Total Cost** | **$0.0706** | **$0.0292** | **$0.00175** |

### Pricing Used

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|----------------------|
| Claude Sonnet | $3.00 | $15.00 |
| GPT-4o | $2.50 | $10.00 |
| GPT-4o-mini | $0.15 | $0.60 |

### Cost Per Card (Average)

| Model | Cost/Card |
|-------|-----------|
| Claude Sonnet | $0.0141 |
| GPT-4o | $0.0058 |
| GPT-4o-mini | $0.00035 |

### Projected Cost for 270-Card Set

| Model | Estimated Cost |
|-------|---------------|
| Claude Sonnet | $3.81 |
| GPT-4o | $1.57 |
| GPT-4o-mini | $0.09 |

Note: These are optimistic projections. Real costs will be higher due to retries, validation failures, and the system prompt growing with few-shot examples.

---

## Key Findings

### 1. Self-Reference (`~`) Compliance
All three models correctly used `~` for self-reference where needed. Claude Sonnet and GPT-4o-mini were the most consistent. No model used the card's actual name in oracle text. **This is a pass for all models.**

### 2. Mana Cost Ordering
All models produced correct WUBRG ordering (generic first, then colored in WUBRG order). No errors observed.

### 3. JSON Validity
- **Claude Sonnet**: 5/5 valid via tool_use. Tool use guarantees schema compliance.
- **GPT-4o**: 5/5 valid via json_object mode. All required fields present, correct types.
- **GPT-4o-mini**: 5/5 parseable JSON, but one semantic error (land card with `colors: ["G"]` instead of `[]`).

### 4. Balance Issues
- **Claude Sonnet** had one significant balance failure: the blue instant "Temporal Insight" is essentially draw-3+ for 3 mana, which is far too powerful. Other cards were well-balanced.
- **GPT-4o** was the most consistently balanced but also the most conservative — cards tended to be safe rather than exciting.
- **GPT-4o-mini** had one NWO violation (common creature with two abilities) and an underpowered land, but the blue instant was the best-balanced card across all models.

### 5. Creativity
- **Claude Sonnet** produced the most interesting and cohesive designs. The legendary creature and planeswalker had strong mechanical identity and flavor integration.
- **GPT-4o** produced safe, functional designs that read like "default" MTG cards. Nothing wrong, but nothing exciting.
- **GPT-4o-mini** was surprisingly creative with the blue instant but generic elsewhere.

### 6. Design Notes Quality
- **Claude Sonnet** provided the most detailed and useful design notes, explicitly referencing color pie rules, NWO guidelines, and power level math.
- **GPT-4o** provided adequate but shorter notes.
- **GPT-4o-mini** provided the shortest notes, sometimes missing specific reasoning.

### 7. Latency
GPT-4o was the fastest (avg 3.7s), followed by GPT-4o-mini (avg 5.2s), then Claude Sonnet (avg 9.2s). For a batch pipeline, latency is less critical than quality and cost.

---

## Recommendation

### Primary Model: Claude Sonnet

Claude Sonnet scores highest overall (89/100) and excels at the most complex card types (legendary creatures, planeswalkers, utility lands). Its design notes are the most useful for the human review step. The tool_use API guarantees valid JSON schema, eliminating parse failures.

**Weakness**: The balance miss on the blue instant shows it can occasionally create overpowered designs. This is mitigable through the validation pipeline (Phase 1B) which will catch P+T and cost anomalies.

### Fallback / Validation Model: GPT-4o-mini

At 40x lower cost than Claude Sonnet, GPT-4o-mini produces surprisingly good output. It could serve as:
- A **first-pass generator** for simple commons/uncommons, with Claude Sonnet reserved for rares/mythics
- A **validation oracle** — generate the same card on both models and flag disagreements
- A **bulk retry model** when Claude Sonnet fails validation

### GPT-4o: Not Recommended as Primary

GPT-4o sits in an awkward middle ground — more expensive than GPT-4o-mini with only marginally better quality. Its conservative designs lack the creative spark needed for a custom MTG set. If OpenAI is needed, GPT-4o-mini provides better value.

### Suggested Pipeline Strategy

| Card Type | Primary Model | Estimated Cost/Card |
|-----------|--------------|---------------------|
| Mythic Rares | Claude Sonnet | $0.014 |
| Rares | Claude Sonnet | $0.014 |
| Uncommons | Claude Sonnet (first attempt), GPT-4o-mini (retries) | $0.008 avg |
| Commons | GPT-4o-mini (first attempt), Claude Sonnet (if fails validation) | $0.002 avg |

**Estimated total for 270-card set**: ~$1.50-$3.00 depending on retry rates.
