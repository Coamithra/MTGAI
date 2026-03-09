# Recommended Card Generation Settings

## Model
**Claude Sonnet** (`claude-sonnet-4-20250514`)
- 89/100 on model comparison (Phase 0D)
- 4.71-4.73/5.0 across all experiment configurations
- Guaranteed valid JSON via tool_use (0% parse failures)

## Temperature: 1.0
- Counterintuitive winner — highest tested temperature scored best overall
- Correctness: 4.98/5.0 (better than T=0.3's 4.96)
- Creativity: 4.04/5.0 (tied with T=0.3)
- No quality degradation vs lower temperatures

## Few-Shot Examples: 0 (zero-shot)
- System prompt alone is sufficient — Claude Sonnet has strong MTG knowledge
- Adding examples slightly decreased quality (4.71 → 4.66 at 5 examples)
- More examples introduced old ETB wording from example cards
- Saves ~600-1500 input tokens per call

## Batch Size: 5 cards per call
- 64% cost savings vs single-card generation (Phase 0D finding)
- 100% parse success rate
- No quality degradation vs single-card
- Natural grouping: one per color, or all cards for one archetype
- Use single-card mode for retries only

## Output Format: Tool Use (Anthropic `tool_use`)
- 0% parse failure rate across 200+ cards tested
- Guarantees valid JSON structure, correct field types, required fields present
- Schema: `CARDS_BATCH_TOOL_SCHEMA` in `research/scripts/cached_llm.py`

## Context Strategy: Compressed Summary
- Include: card names, mana costs, one-line oracle summaries, color distribution stats
- Best balance of duplicate avoidance (1 similar effect) vs token cost
- Template:
  ```
  **Cards already in the set** (do NOT duplicate names or effects):
  - Card Name ({mana_cost}) — Type Line — Oracle text summary...

  **Color distribution so far**: {"W": N, "U": N, ...}
  **Total cards**: N
  ```

## System Prompt Version: v1
- Location: `research/prompt-templates/system-prompt-v1.md`
- ~1,800 tokens covering: MTG rules reference, color pie, NWO, output format
- No modifications needed based on experiments — v1 performed excellently

## Quality Metrics

| Metric | Value | GO Threshold |
|--------|-------|-------------|
| Rules text correctness avg | 4.95-5.00 | >= 4.0 |
| Overall average | 4.71-4.73 | >= 3.5 |
| Cards below 3.0 | 0 | <= 2 |
| Parse success rate | 100% | >= 95% |
| Retry rate | 5% (1/20) | <= 30% |
| Cost per card (batch 5) | $0.0046-0.0053 | — |
| Cost per set (280 cards) | ~$2.57 | < $30 |

**Verdict: GO** — All criteria passed with significant margin.

## Cost Projections

| Component | Model | Calls | Est. Cost |
|-----------|-------|-------|-----------|
| Card generation (batch 5) | Sonnet | 56 | $1.29 |
| Retries (5% rate, single) | Sonnet | 14 | $0.18 |
| Art prompts (batch 5) | Haiku | 56 | $0.31 |
| **Total** | | **~126** | **~$1.78** |

Budget: $30 allocated. Headroom for 15+ complete regeneration cycles.

## Known Limitations

1. **Missing period on planeswalker loyalty abilities**: Scoring flags this but it's often a false positive — loyalty ability format `[+1]: Effect` doesn't always end with a period in practice. Post-process: verify planeswalker abilities manually.

2. **Mythic creatures sometimes lack "Legendary"**: ~20% of mythic creatures omit "Legendary" from type_line. Mitigation: add explicit instruction in prompt OR post-process validation to add it.

3. **"Forest" basic land**: Model generates "Forest" as the name for basic forests (correct behavior, but scorer flags it). Handle basic lands as a special case.

4. **Old ETB wording**: Appears in ~5% of cards ("enters the battlefield" instead of "enters"). Trivial regex post-process: `s/enters the battlefield/enters/g`.

5. **Overstatted commons**: ~5% of common creatures exceed P+T > CMC+3. Caught by balance validator.

## Failure Modes Requiring Post-Processing

| Mode | Frequency | Mitigation |
|------|-----------|------------|
| Old ETB wording | ~5% | Regex replacement |
| Missing period | ~8% | Append period to non-keyword ability lines |
| Mythic not Legendary | ~20% of mythics | Add "Legendary" to type_line if creature + mythic |
| Overstatted common | ~5% of commons | Flag for retry with balance feedback |
| Color pie soft bend | <3% | Manual review; most are debatable, not violations |

## Decision Tree for Phase 1C

```
IF generating common creatures/instants/sorceries:
    → Batch of 5, T=1.0, zero-shot, compressed context
IF generating uncommon signpost multicolors:
    → Batch of 5, T=1.0, zero-shot, compressed context + archetype description
IF generating rares:
    → Batch of 5, T=1.0, zero-shot, compressed context
IF generating mythics (legendaries, planeswalkers, sagas):
    → Batch of 5 or single, T=1.0, zero-shot, compressed context
    → Use Claude Opus for planeswalkers and sagas (complex templating, small count ~5-8 cards, justifies higher per-card cost)
    → Manual review strongly recommended
IF retrying a failed card:
    → Single card, T=0.5, zero-shot, include previous card + error feedback
    → Max 3 retries, then flag for human review
IF generating basic lands:
    → Special case: only need name + flavor_text
    → Batch of 5 (all 5 basic land types at once)
```

## Reproduction

All experiment scripts are in `research/scripts/`:
- `exp1_temperature_sweep.py` — Temperature 0.3/0.5/0.7/1.0
- `exp2_fewshot_count.py` — Few-shot 0/1/3/5
- `exp5_context_strategy.py` — Context none/names/compressed/full
- `exp6_retry_loop.py` — Validation-retry convergence
- `exp_confirmation.py` — 20-card confirmation batch
- `cached_llm.py` — Caching layer (all responses in `experiments/cache/`)

Total experiment cost: ~$1.50 across all experiments.
