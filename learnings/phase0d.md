# Phase 0D Learnings

## What Worked

### Tool Use is a Game Changer
- Anthropic's tool_use guarantees valid JSON structure — 0% parse failure rate across 19 cards
- Eliminates an entire class of errors (malformed JSON, missing fields, wrong types)
- OpenAI's json_object mode is similar but slightly less strict (land card had semantic error with colors field)
- **Decision**: Use tool_use for all Anthropic calls, json_object for OpenAI

### Batch Generation is Cost-Effective
- Batch of 5: 64% cheaper than single-card generation (shared system prompt amortization)
- Input tokens stay nearly constant (~2,300-2,400) regardless of batch size
- Output scales linearly at ~195-400 tokens per card
- No quality degradation in batch mode — all 19 cards valid across batch sizes 1-10

### Budget is Not a Concern
- Full set generation costs ~$2.57 with Claude Sonnet (primary) + Haiku (art prompts)
- $30 budget allows 10+ complete regeneration cycles
- Even Claude Opus ($24/set) is feasible for quality-critical subsets

### Haiku is Sufficient for Art Prompts
- 92% of Sonnet quality at 4x less cost and 2.3x faster
- Art prompts are less precision-critical than card design — "very good" is good enough
- The image generation model introduces its own variance, making Sonnet vs Haiku gap negligible in practice

## What Surprised Us

### GPT-4o-mini is Surprisingly Good
- Scored 84/100 vs Sonnet's 89/100 — only 5 points lower at 40x less cost
- Best card in the test was GPT-4o-mini's blue instant (19/20 subtotal)
- Viable as a bulk generator for simple commons/uncommons
- **BUT**: Had NWO violations at common (two abilities) and semantic errors (land colors)

### GPT-4o is the Worst Value
- 83/100 — actually scored LOWER than GPT-4o-mini (84/100) on our test set
- More expensive than mini, less creative than Sonnet
- Conservative designs that read as "default" MTG cards
- **Decision**: Skip GPT-4o entirely. Use Sonnet or mini.

### Sonnet Can Be Overpowered
- "Temporal Insight" (draw 3+ for 3 mana instant speed) — massively broken
- Creative and well-designed mechanically, but balance was off
- Confirms validation pipeline is essential, not optional
- Balance validator needs to catch "total card advantage per mana" not just P/T vs CMC

### Design Notes Degrade in Large Batches
- Single card: ~83 words (detailed tradeoff analysis)
- Batch of 10: ~25 words (sometimes just restates the card)
- For human review, batch of 5 is the sweet spot (~35 words, still useful)

## Anti-Patterns to Avoid
- Don't use GPT-4o as a middle ground — it's worse than both alternatives
- Don't skip the balance validator even though tool_use guarantees valid JSON — semantic correctness ≠ game balance
- Don't include card names in art prompts — GPT-4o-mini does this, bad for image generation
- Don't set land cards' `colors` field to their mana production colors — lands are colorless permanents (GPT-4o-mini got this wrong)
- Don't rely on design_notes for quality assurance at batch sizes >5 — they get too brief

## Parameter Adjustments for Downstream

### Phase 0E (Prompt Spike)
- Start with temperature 0.7 (confirmed reasonable in testing)
- Test few-shot examples: 0, 1, 3, 5 (not yet tested — only ran with 0 examples)
- Test system prompt v1 specifically for balance issues (the biggest weakness found)
- Consider adding explicit "power level budget" to system prompt (e.g., "CMC 3 creature should have total P+T <= 5")

### Phase 1C (Card Generation)
- Use batch of 5 as default, batch of 1 for retries
- Implement the 7-validator chain from validation-chain-design.md
- Track cost per card via GenerationAttempt fields (already in schema)
- Name deduplication is critical — names repeated across separate batch calls

### Config Values to Set
```python
llm_provider = "anthropic"
llm_model = "claude-sonnet-4-20250514"
llm_retry_model = "claude-sonnet-4-20250514"
llm_temperature = 0.7
llm_retry_temperature = 0.5
llm_max_retries = 3
llm_batch_size = 5
llm_art_prompt_model = "claude-haiku-4-5-20251001"
llm_art_prompt_temperature = 0.6
```

## Verification Results
- 15/15 model comparison calls succeeded (100%)
- 19/19 batch test cards valid (100%)
- 15/15 art prompt calls succeeded (100%)
- Total API spend for all 0D testing: ~$0.15
- All scripts saved in `research/scripts/` and are re-runnable
