# Phase 1B Learnings: Mechanic Designer

## What was built
- **3 custom mechanics** for "Anomalous Descent" (ASD):
  - **Salvage X** (W/U/G, complexity 1): Look at top X cards, take an artifact. Common-viable. Renamed from "Scavenge" to avoid collision with existing MTG keyword (Return to Ravnica, 2012).
  - **Malfunction N** (W/U/R, complexity 2): Enters tapped with N malfunction counters, remove one per upkeep. Delayed power at above-rate stats.
  - **Overclock** (U/R/B, complexity 3): Exile top 3 cards, play until end of turn. High risk/reward. Uncommon+ only. Renamed from "Overload" (same collision issue).
- **LLM infrastructure**: `backend/mtgai/generation/llm_client.py` (Anthropic client with tool_use), `mechanic_generator.py` (mechanic generation pipeline).
- **Mechanic distribution**: 14 mechanic cards (23.3% of 60-card dev set). Mapped to specific skeleton slots.
- **Automated review pipeline**: `research/scripts/auto_review_calibration.py` — self-critique loop + pointed questions, calibrated against human ground truth.
- **15 test cards** generated, human-reviewed, 8 FAIL + 2 WARN found, 2 fully redesigned.

## What worked well
- **LLM mechanic generation**: Claude Sonnet generated 6 strong candidates from a single prompt. 3 selected with minimal human adjustment. Cost: ~$0.09.
- **Validation spike approach**: Generating 5 test cards per mechanic before committing to production was invaluable. Found systemic issues (missing reminder text, keyword nonbos) early.
- **Interactive human+AI review**: Session 9's detailed card-by-card review established ground truth that made the automated review calibration possible.
- **Pointed questions architecture**: Self-critique alone caught ~60% of issues; adding targeted pointed questions brought detection to 100% of FAIL cards. The questions act as a checklist for known LLM blind spots.

## LLM blind spots discovered
These are failure modes the LLM generator consistently produces but doesn't catch in self-scoring:

1. **Missing reminder text** (5/15 cards): The LLM includes reminder text on the first card using a mechanic, then systematically drops it on subsequent cards. Each card should have reminder text on first use of a custom keyword.
2. **Keyword nonbos** (1/15): Haste + Malfunction — haste is fully negated because malfunction causes enter-tapped and counter isn't removed until next upkeep (by which point summoning sickness has worn off).
3. **Redundant conditionals** (1/15): Using overclock as a mandatory additional cost then checking "if you overclocked this turn" — always true, hides the real power level.
4. **Kitchen sink design** (2/15): Piling 3+ unrelated effects on one card. LLM optimizes for "interesting" rather than "focused."
5. **False variability** (1/15): "2 damage per card exiled" when overclock always exiles exactly 3 — the variable wording implies variance that doesn't exist.
6. **Above-rate balance** (2/15): 12 damage for 5 mana (Lava Axe = 5 for 5), {1}{U} hard counter + draw + impulse draw. LLM self-scores balance at 5.0 for both.
7. **Mechanic-type mismatch** (1/15): "Enters tapped" from malfunction is irrelevant on noncreature artifacts with no tap abilities.
8. **Keyword name collisions**: LLM reuses existing MTG keywords. Caught twice: Overload → Overclock, Scavenge → Salvage.

## Self-scoring is unreliable
- LLM self-scored the 15 test cards at **4.77/5.0 average**
- Human review found **8 FAIL + 2 WARN** (only 5 clean passes)
- The self-scoring mechanism has no predictive value for real design quality issues
- Lesson: Never use LLM self-scores as a quality gate. Always use the external review loop.

## Automated review calibration results
- **FAIL detection: 100%** (8/8, target ≥70%)
- **WARN detection: 50%** (1/2, target ≥50%)
- **Cost: $0.34** for 15 cards (~$0.023/card)
- **Over-sensitivity**: 5-6 false positives (flagging clean cards). Main source: overly strict reminder text checks on cards that already had inline reminder text.
- **No prodding needed**: Model gave clear verdicts without the uncertainty loop, suggesting prompts are well-calibrated.
- **Misses**: Inconsistent capitalization (minor), flying feels tacked on (subjective). Both acceptable misses.

### Pointed questions to keep (all 8 proved useful):
1. Keywords negated by other abilities?
2. Reminder text present for custom mechanics?
3. Conditional actually meaningful (can it be false)?
4. Power level appropriate for rarity?
5. Kitchen sink (too many unrelated effects)?
6. Variable effects genuinely variable?
7. Mechanic name collision with existing MTG keywords?
8. "Enters tapped" relevant on this permanent type?

## Design decisions
- **Salvage X scaling**: 2-3 at common, 4-5 at uncommon, 6+ at rare/mythic. Top-X dig (not tutor) keeps variance manageable.
- **Malfunction N scaling**: 1 at common, 2 at uncommon, 2-3 at rare. "Enters tapped" is the tempo cost; counters gate powerful abilities.
- **Overclock at uncommon+ only**: Complexity 3 mechanic. Exiling 3 cards is a significant resource cost that commons can't evaluate well (NWO).
- **Clean archetype payoffs preferred**: Cards like the redesigned Synaptic Overload ({1}{U}{U} counter, draw if you overclocked externally) are better than cards that include overclock as a mandatory cost + check their own condition.

## A/B test: Review-and-revise strategies (1B-8c/8d)

### Round 1 (session 11) — Opus 4.0, no effort parameter

Tested 8 strategies (4 Sonnet + 4 Opus) on 7 test cards with known human verdicts. $3.83 total cost.

| # | Type | Model | Cost | Human Verdict |
|---|------|-------|------|---------------|
| S1 | Simple | Sonnet 4.0 | $0.06 | DISQUALIFIED — R!=Red confusion, malfunction blindness |
| S2 | Iterative | Sonnet 4.0 | $0.22 | DISQUALIFIED — goes off the rails, design erosion |
| S3 | Detailed | Sonnet 4.0 | $0.15 | FAIL — tenuous balance grasp |
| S4 | Split | Sonnet 4.0 | $0.23 | PROMISING — one disqualifying outlier ({U} counterspell) |
| S5 | Simple | Opus 4.0 | $0.31 | OK — one miss (Card 14 balance) |
| S6 | Iterative | Opus 4.0 | $1.02 | SATISFACTORY — all acceptable, expensive + oscillation |
| S7 | Detailed | Opus 4.0 | $0.74 | FAIL — identifies but doesn't fix balance issues |
| S8 | Split | Opus 4.0 | $1.11 | FAIL — {U}{U} counterspell unacceptable |

**Winner (provisional): Hybrid** — S4 (Split/Sonnet) + Opus sanity check for balance outliers.

### Round 2 (session 12) — Opus 4.6, effort=max, +S9 council

**Why rerun:** Round 1 used Opus 4.0 (`claude-opus-4-20250514`, $15/$75) — two generations behind current Opus 4.6 (`claude-opus-4-6`, $5/$25). 3x price difference invalidates all Round 1 Opus cost/benefit analysis. Sonnet also updated to 4.6 (`claude-sonnet-4-6`, $3/$15 — same price as 4.0).

**Changes from Round 1:**
- Updated model IDs: Opus 4.6, Sonnet 4.6
- Added `effort: "max"` (API `output_config`) for all Opus strategies — Opus-only feature
- Added S9: Council strategy (3 independent Opus reviewers + consensus synthesizer)
- Removed `thinking` from all calls — incompatible with `tool_choice: force`, redundant for text analysis (thinking tokens billed as output, and explicit analysis text IS the reasoning)
- Increased `max_tokens` from 4096 to 8192 for text calls
- Added truncation guard: `stop_reason == "max_tokens"` raises `RuntimeError`
- Fixed U+FFFD encoding bug in test cards (em dashes restored)

**S9 Council design:**
- 3 independent `call_text` reviewers analyze the card with the same prompt (no cross-contamination)
- 1 `call_with_tool` synthesizer receives all 3 reviews + the card, applies 2-of-3 consensus filter
- Only issues flagged by 2+ reviewers are acted on → reduces false positives
- 4 API calls per card

**Round 2 results (complete):**

| # | Type | Model | Cost | Score | Key failure |
|---|------|-------|------|-------|-------------|
| S1 | Simple | Sonnet 4.6 | $0.09 | 4/7 | Missed nonbo, balance ×2 |
| S2 | Iterative | Sonnet 4.6 | $0.34 | 6/7 | 1 disqualifying (Card 7 nonbo) |
| S3 | Detailed | Sonnet 4.6 | $0.37 | 5/7 | Balance (Cards 11+14) |
| S4 | Split | Sonnet 4.6 | $0.27 | 5/7 | Balance (Cards 11+14) |
| S5 | Simple | Opus 4.6 max | $0.13 | 4/7 | Missed nonbo (!), balance ×2 |
| S6 | Iterative | Opus 4.6 max | $0.42 | **6/7** | False OK on Card 7 |
| S7 | Detailed | Opus 4.6 max | $0.37 | 5/7 | Balance (Cards 11+14) |
| S8 | Split | Opus 4.6 max | $0.44 | **6/7** | Soft fail Card 14 |
| S9 | Council | Opus 4.6 max | $0.49 | **6/7** | Card 14 creative but rules-broken |

**Observations:**
- Simple prompts miss nonbos even on Opus — S5 OK'd haste+malfunction just like S1
- Detailed/split prompts catch nonbos but single-pass undernerfs balance
- Iteration fixes balance via multiple passes but can't fix false OKs
- Council produces most creative fixes — S9 Card 11 matched human's own redesign
- Council creativity cuts both ways: Card 14 was an ambitious but rules-broken concept
- The detailed prompt advantage is just one sentence: "List any issues with templating, mechanics, balance, design, or color pie." The full S7 checklist was mostly superfluous.
- Analysis ≠ action: S7 detected everything but produced worst Opus fixes

### Key findings — Sonnet vs Opus

**Sonnet limitations (consistent across all strategies and model versions):**
1. Cannot reason about mandatory-cost-as-conditional patterns (Card 11: overclock is mandatory additional cost, so "if you overclocked" is always true — Sonnet says it CAN be false)
2. Doesn't understand malfunction as a downside (nerfs clean malfunction cards because it sees above-rate stats without recognizing the tempo cost)
3. Confuses color abbreviations (R != Red in mechanic definitions)
4. Balance execution is poor even when issues are identified

**Opus limitations:**
1. ~~Expensive (5x Sonnet pricing)~~ Now ~1.7x Sonnet pricing with 4.6 ($5/$25 vs $3/$15)
2. Iterative approach causes oscillation ("too strong" → "too weak" → "too strong")
3. Detailed analysis can HURT revision — S7 correctly identified Card 11 as overpowered but didn't change it (got lost in templating fixes)
4. Still misses some balance issues (Card 14: 6 damage for 5 mana + double overclock)

### Strategy-level insights

1. **Splitting helps Sonnet dramatically**: S4 (Split) produced the best Sonnet results. Focused prompts per domain (templating, mechanics, balance) work better than one big prompt.
2. **Splitting doesn't help Opus**: Opus already reasons well in single passes. Splitting just adds cost.
3. **Iteration helps Opus, hurts Sonnet**: Opus self-corrects across iterations (S6 satisfactory). Sonnet drifts further from the original with each iteration (S2 goes off the rails in Round 1, but 6/7 in Round 2 with Sonnet 4.6).
4. **Detailed checklists help detection, hurt execution**: Both S3 and S7 identified more issues but produced worse revisions. Too much context → conservative fixes.
5. **Analysis ≠ action**: The biggest surprise. S7 (Detailed/Opus) had the best analytical output but the worst fix quality among Opus strategies. Correctly diagnosing a problem doesn't mean the model will fix it.
6. **Council consensus reduces false positives AND boosts creativity**: S9 caught the haste+malfunction nonbo that Sonnet consistently misses. More surprisingly, the synthesizer produced the most creative fixes (Card 11 matched human's own redesign). Multiple perspectives seem to give the synthesizer "permission" to make bolder changes.
7. **The minimal "detailed" nudge**: The only prompt difference between S5/S6 (simple) and S7+ (detailed) that matters is one sentence: "List any issues with templating, mechanics, balance, design, or color pie." The full S7 checklist was mostly restating what Opus already knows.
8. **Strong generation > cheap review**: The best way to minimize review cost is a strong initial generation prompt+model. Don't generate with Haiku if you'll spend a fortune fixing afterwards.

### API learnings

1. **Thinking + forced `tool_choice` incompatible**: API returns 400 "Thinking may not be enabled when tool_choice forces tool use." Use `effort` parameter instead for tool calls.
2. **Thinking is redundant for explicit analysis calls**: When the prompt asks "analyze this card and explain your reasoning," the model's text output IS the reasoning. Thinking adds a second reasoning pass billed as output tokens — pure waste.
3. **`effort: "max"` is Opus-only**: API parameter `output_config: {"effort": "max"}`. Lower levels ("low"/"medium"/"high") available for all models.
4. **Truncation is silent failure**: `stop_reason == "max_tokens"` means the response was cut off. Must check and raise an error — otherwise you get partial/broken JSON or incomplete analysis.
5. **Model version matters for cost**: Opus 4.0 ($15/$75) → Opus 4.6 ($5/$25) = 3x cheaper. Always verify model IDs match latest available.

### Confounding factors
- **Encoding (Round 1 only)**: Test data had U+FFFD instead of em dashes — fixed before Round 2.
- **Thinking token waste (Round 2, initial runs)**: S3, S4, S7, S8 initially had thinking enabled, eating into token budget and causing truncation. Fixed and rerun in session 13.
- **Small sample**: 7 test cards, single run per strategy. Results are directional, not statistically significant.

### Winning strategy: Tiered council+iteration hybrid

**C/U cards**: Council-style prompt (single reviewer with category nudge: "List any issues with templating, mechanics, balance, design, or color pie") + iteration (continue conversation, loop until OK or max N).

**R/M cards**: Full council (3 independent Opus reviewers + consensus synthesizer) + iteration.

**Token optimizations**:
1. Only include mechanic defs relevant to the card
2. Skip synthesis if all 3 council reviewers say OK
3. Use Anthropic prompt caching — batch by mechanic to maximize cache hits
4. Continue conversation for iteration instead of fresh context each loop (saves resending system prompt + mechanic defs)

**Estimated review cost**: ~$0.10/card C/U, ~$0.11/card R/M → ~$6-7 for 60-card dev set.

## Cost
- Mechanic generation: ~$0.09
- Validation spike (15 test cards): ~$0.09
- Automated review calibration: ~$0.34
- A/B test Round 1 (8 strategies × 7 cards, Opus 4.0): ~$3.83
- A/B test Round 2 (S1-S9 complete, Opus 4.6): ~$4.42
- **Total Phase 1B: ~$8.77**

## Files produced
- `backend/mtgai/generation/llm_client.py` — LLM client with tool_use
- `backend/mtgai/generation/mechanic_generator.py` — mechanic generation pipeline
- `output/sets/ASD/mechanics/approved.json` — 3 approved mechanics with templates
- `output/sets/ASD/mechanics/distribution.json` — mechanic-to-slot assignments
- `output/sets/ASD/mechanics/evergreen-keywords.json` — per-color evergreen keywords
- `output/sets/ASD/mechanics/test-cards-original.json` — 15 test cards (pre-review)
- `output/sets/ASD/mechanics/test-cards-revised.json` — 15 test cards (post-review)
- `output/sets/ASD/mechanics/human-review-findings.md` — ground truth for review calibration
- `output/sets/ASD/mechanics/auto-review-results.md` — automated review calibration results
- `output/sets/ASD/mechanics/validation-spike-results.md` — spike quantitative results
- `output/sets/ASD/mechanics/ab-test/` — 9 strategy directories with per-card reports + summaries
- `research/scripts/auto_review_calibration.py` — automated review calibration script
- `research/scripts/mechanic_validation_spike.py` — mechanic test card generator
- `research/scripts/ab-test/run_strategy.py` — A/B test runner (9 strategies, updated for Opus 4.6 + effort + truncation guard)

## What to watch for in Phase 1C
- **Review pipeline** (tiered council+iteration hybrid): See "Winning strategy" above. Implementation goes in Phase 4A+4B; 1C uses heuristic validators only.
- **Strong generation matters most**: Use good prompts + capable models for initial card generation. Preventing issues is far cheaper than detecting and fixing them. Include the 8 pointed questions as preventive guidance in generation prompts.
- **Extensive review logs are essential**: Every AI review must produce a detailed log (prompt sent, full AI response, tool call result, cost) similar to the A/B test card reports. Without these, you can't diagnose bad reasoning (e.g., R!=Red confusion) or iterate on prompts. Store per-card review logs alongside card JSON in `output/sets/<code>/reviews/`.
- ~~Fix U+FFFD encoding in card data before production generation~~ DONE (session 12)
- The pointed questions list should evolve as new failure modes are discovered
- For complex card types (planeswalkers, sagas), skip Sonnet entirely and go straight to Opus generation AND review
