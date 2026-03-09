# Phase 0E Learnings: Prompt Engineering Spike

## What Worked

### Zero-Shot is Best
- Claude Sonnet has sufficient built-in MTG knowledge — no few-shot examples needed
- Adding examples actually decreased quality (4.71 → 4.66 at 5 examples)
- Examples introduced old ETB wording from pre-2023 card templates
- Saves 600-1500 input tokens per call

### Temperature 1.0 is Optimal
- Counterintuitive: highest temperature tested scored best (4.71 avg)
- No quality degradation in correctness (4.98) or creativity (4.04)
- All temperatures scored within 0.03 of each other — temperature has minimal impact
- Conclusion: Claude Sonnet's card generation is robust to temperature

### Tool Use Eliminates Parse Failures
- 0% parse failure rate across 200+ cards
- Every card has correct JSON structure, types, and required fields
- Semantic errors still possible but structural errors are impossible

### Compressed Context Prevents Duplicates
- Names + mana costs + one-line summaries is the sweet spot
- Only 1 similar effect detected vs 6 for names-only
- Full card JSON wastes tokens without meaningful quality improvement

### Retry Loop Converges Fast
- 5/7 test cards were clean on first attempt (with improved prompt)
- 2/7 fixed in exactly 1 retry
- Adding explicit instructions ("mythic creatures MUST be Legendary") to the prompt
  eliminated issues that previously appeared in every run

### Quality is Consistently High
- 4.73/5.0 on confirmation batch (20 cards)
- 0 cards below 3.0 on any dimension
- Only 1/20 had any failure (old ETB wording — trivial regex fix)
- Estimated retry rate: ~5% (far below the 30% threshold)

## What Didn't Work

### Few-Shot Examples Hurt Quality
- Expected: examples would improve rules text correctness
- Actual: examples introduced old formatting patterns
- Root cause: even "curated" examples can contain outdated Oracle text
- If we ever revisit this: use only post-2023 Oracle-verified examples

### The Scoring System Has False Positives
- "missing_period" on planeswalker loyalty abilities (format is `[+1]: Effect`)
- "generic_or_existing_name" on basic lands (Forest IS the correct name)
- "similar effects" detection uses word overlap which is too coarse — two burn spells
  sharing words like "deals damage" doesn't mean they're duplicates
- Phase 1C validators should be more nuanced than the experiment scorer

## Key Findings

| Parameter | Best Value | Runner-Up | Reason |
|-----------|-----------|-----------|--------|
| Temperature | 1.0 | 0.3 (tie) | All temps near-identical; 1.0 slightly wins |
| Few-shot | 0 | 1 | Zero-shot best; examples hurt |
| Context | Compressed | Full color | Compressed = best dedup at lowest token cost |
| Batch size | 5 | 1 (retries) | From Phase 0D; confirmed here |
| Output | Tool use | — | 0% parse failure; no alternative needed |

## Prompt Anti-Patterns (Things That Made Cards Worse)

- Adding few-shot examples with pre-2023 Oracle text
- Using more than 3 examples (diminishing returns → negative returns)
- Not explicitly stating constraints like "mythic creatures MUST be Legendary"

## Prompt Patterns (Things That Made Cards Better)

- Explicit constraint lines: "IMPORTANT: mythic creatures MUST have 'Legendary'"
- Compressed context with color distribution stats
- Role descriptions that say what the card should DO, not just what it IS
- Specifying archetype the card should support

## Parameter Adjustments for Phase 1C

```python
llm_model = "claude-sonnet-4-20250514"
llm_temperature = 1.0
llm_retry_temperature = 0.5
llm_fewshot_count = 0
llm_batch_size = 5
llm_max_retries = 3
llm_context_strategy = "compressed"
llm_output_format = "tool_use"
llm_art_prompt_model = "claude-haiku-4-5-20251001"
```

## Open Questions for Phase 1C

1. **Will quality hold at 280 cards?** Our tests maxed at 24 cards per run. The context
   window will grow as the set fills. May need to rotate context or use summary-only mode
   for later batches.

2. **Mechanic integration quality**: Confirmation batch used Delve/Convoke (existing mechanics).
   Novel set-specific mechanics need testing once Phase 1B defines them.

3. **Planeswalker scoring**: Current scorer flags false positives on loyalty ability formatting.
   Phase 1C needs a planeswalker-specific validator.

4. **Name deduplication at scale**: 0 duplicates in 20-card test, but 280 cards with
   similar prompts may produce more collisions. Context injection handles this but
   needs testing at scale.

## Failure Modes Discovered

| Mode | Frequency | Severity | Mitigation |
|------|-----------|----------|------------|
| Old ETB wording | ~5% | Low | Regex: `s/enters the battlefield/enters/g` |
| Missing period | ~8% | Low | Append period to non-keyword lines |
| Mythic not Legendary | ~20% of mythics | Medium | Explicit prompt instruction |
| Overstatted common | ~5% | Medium | Balance validator → retry |
| Color pie soft bend | <3% | Low | Manual review |
| Name reuses existing MTG card | <2% | Medium | Name validator vs Scryfall DB |

## Experiment Cost Summary

| Experiment | Cost | Cards |
|-----------|------|-------|
| Exp1 (temperature) | $0.48 | 96 |
| Exp2 (few-shot) | $0.39 | 96 |
| Exp5 (context) | $0.23 | 56 |
| Exp6 (retry) | $0.17 | 12 |
| Confirmation | $0.10 | 20 |
| Cache test + misc | ~$0.05 | — |
| **Total** | **~$1.42** | **280** |

Well under the $10 budget ceiling. The caching layer saved an estimated $0.50+ by
avoiding duplicate API calls across experiments.
