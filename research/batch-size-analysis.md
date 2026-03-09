# Batch Size Test Analysis

**Date**: 2026-03-08
**Model**: claude-sonnet-4-20250514
**Temperature**: 0.7
**Method**: Tool use (forced) — `generate_card` for batch 1, `generate_cards` for batches 3/5/10
**Pricing**: $3/M input tokens, $15/M output tokens

---

## Results Summary

| Batch Size | Cards Returned | Valid | Issues | In Tokens | Out Tokens | Total Cost | $/Card | Tokens/Card | Latency | Latency/Card |
|:----------:|:--------------:|:-----:|:------:|:---------:|:----------:|:----------:|:------:|:-----------:|:-------:|:------------:|
| 1          | 1              | 1     | 0      | 2,329     | 392        | $0.0129    | $0.0129 | 2,721      | 9.3s    | 9.3s         |
| 3          | 3              | 3     | 0      | 2,402     | 710        | $0.0179    | $0.0060 | 1,037      | 11.9s   | 4.0s         |
| 5          | 5              | 5     | 0      | 2,392     | 1,067      | $0.0232    | $0.0046 | 692        | 17.4s   | 3.5s         |
| 10         | 10             | 10    | 0      | 2,394     | 1,950      | $0.0364    | $0.0036 | 434        | 29.5s   | 3.0s         |

**Parse success rate: 100% across all batch sizes.** Tool use guarantees valid JSON structure.

---

## Cost Analysis

### Cost Per Card by Batch Size

| Batch Size | Cost/Card | Savings vs Batch 1 |
|:----------:|:---------:|:-------------------:|
| 1          | $0.0129   | baseline            |
| 3          | $0.0060   | 54% cheaper         |
| 5          | $0.0046   | 64% cheaper         |
| 10         | $0.0036   | 72% cheaper         |

The cost-per-card decreases steadily with larger batches, driven entirely by **input token amortization**. The system prompt (~2,300 input tokens) is shared across all cards in a batch. Input tokens stay nearly constant (~2,329-2,402) regardless of batch size, while output tokens scale linearly (~195-392 per card).

### Projected Set Cost (280 cards)

| Batch Size | API Calls | Est. Total Cost | With Batch API (50% off) |
|:----------:|:---------:|:---------------:|:------------------------:|
| 1          | 280       | $3.61           | $1.81                    |
| 3          | 94        | $1.68           | $0.84                    |
| 5          | 56        | $1.29           | $0.65                    |
| 10         | 28        | $1.01           | $0.51                    |

All options are well within the $30 budget. Even batch-of-1 generation is affordable.

---

## Token Efficiency

| Batch Size | Input/Card | Output/Card | Total/Card | Input Amortization Factor |
|:----------:|:----------:|:-----------:|:----------:|:-------------------------:|
| 1          | 2,329      | 392         | 2,721      | 1.0x (baseline)           |
| 3          | 801        | 237         | 1,037      | 2.9x                     |
| 5          | 478        | 213         | 692        | 4.9x                     |
| 10         | 239        | 195         | 434        | 9.7x                     |

Input token amortization scales almost linearly with batch size, as expected. Output tokens per card *decrease* slightly at larger batch sizes (392 -> 195), likely because design_notes get shorter in batch mode.

---

## Quality Assessment

### Overall

All 19 cards across all four test runs passed validation with zero issues. Every card had:
- Valid JSON structure (guaranteed by tool use)
- All required fields present and correctly typed
- Proper mana cost format (`{N}{C}`)
- Correct self-reference (`~`) usage
- Valid rarity values
- Appropriate creature stats (power/toughness present for all creatures)

### Batch-by-Batch Observations

**Batch 1 (1 card)**:
- Highest individual card quality. Thornback Herbalist is a well-designed card with a flavorful ETB ability.
- Longest and most detailed design_notes (83 words).
- However, the card may be slightly too powerful for common (land search on a 2-mana body is borderline).

**Batch 3 (3 cards)**:
- Good quality across all three cards. Each card is color-appropriate with clean designs.
- Ember Striker (red, CMC 3) has haste + ETB damage — two abilities is borderline for common under NWO but acceptable since both are simple.
- Design_notes are moderately detailed (~40 words each).

**Batch 5 (5 cards)**:
- All cards are clean vanilla-with-keyword designs. Very safe, NWO-compliant.
- Slightly less creative than batch 1 and 3 — cards are more formulaic (each is basically "keyword + stats").
- Crypt Lurker at {2}{B}{B} for a 3/2 deathtouch is well-designed (double black punishes splashing).
- Design_notes are shorter (~35 words each).

**Batch 10 (10 cards)**:
- All cards are valid and color-appropriate.
- **Name duplication across batches**: "Temple Guardian" appeared in both the batch-3 and batch-10 runs. "Crypt Lurker" appeared in both batch-5 and batch-10 runs. Within each batch, all names are unique, but the model reuses names across separate calls. This is expected behavior (no cross-call memory).
- Design variety is acceptable: mix of keyword-only creatures and ETB creatures.
- **No quality degradation for later cards** (cards 8-10 are as well-formed as cards 1-3).
- Design_notes are the shortest (~25 words each).
- Some cards are aggressively statted: Emberkin Warrior (2/1 haste for {R}) is strong, comparable to real MTG staples like Monastery Swiftspear (without prowess).

### Design Notes Quality Degradation

One clear trend: design_notes get shorter and more formulaic as batch size increases.

| Batch Size | Avg design_notes length | Quality |
|:----------:|:-----------------------:|:-------:|
| 1          | ~83 words               | Detailed, discusses tradeoffs and format implications |
| 3          | ~40 words               | Good, covers color pie reasoning |
| 5          | ~35 words               | Adequate, more formulaic |
| 10         | ~25 words               | Brief, sometimes just restates the card |

This makes sense: output tokens are budgeted across all cards, so each card gets less "attention." For the pipeline this is fine — design_notes are for human review, and the shorter notes still convey the key reasoning.

---

## Latency

| Batch Size | Total Latency | Latency/Card |
|:----------:|:-------------:|:------------:|
| 1          | 9.3s          | 9.3s         |
| 3          | 11.9s         | 4.0s         |
| 5          | 17.4s         | 3.5s         |
| 10         | 29.5s         | 3.0s         |

Latency is not a concern (pipeline is not user-facing), but larger batches are more efficient per card. Total wall-clock time for 280 cards:
- Batch 1: ~43 minutes
- Batch 5: ~16 minutes
- Batch 10: ~14 minutes

---

## Recommendation

### Optimal batch size: **5 cards per call**

Rationale:

1. **Cost efficiency**: Batch 5 achieves 64% savings over batch 1 ($0.0046 vs $0.0129 per card). Batch 10 saves another 8 percentage points (72% total), but with diminishing returns.

2. **Quality**: All batch sizes produced valid cards, but batch 5 maintains a good balance of creativity and mechanical soundness. Design_notes are still adequately detailed at batch 5.

3. **Partial failure risk**: If a batch-10 call fails or returns malformed output, 10 cards need regeneration. With batch 5, only 5 are at risk. In this test, no failures occurred, but in production with more complex prompts (set context, few-shot examples, archetype requirements), failure probability increases with batch size.

4. **Grouping**: 5 cards maps naturally to "one of each color" or "all creatures for one archetype" — useful organizational groupings for the generation pipeline.

5. **Alignment with Phase 0D plan**: The Phase 0D cost analysis was built around batches of 5 cards per call. The test data confirms those estimates are accurate.

### When to use other batch sizes

- **Batch 1**: Use for retries. When a card fails validation, regenerate it individually with specific feedback. Single-card calls allow maximum context for the retry prompt.
- **Batch 3**: Not recommended as a default. No natural grouping advantage over 5.
- **Batch 10**: Consider for bulk common creature generation where cards are mechanically simple and the risk of quality degradation is low. The 72% cost savings is attractive for this case. However, the default should remain 5.

---

## Raw Data

Full results with all card data are stored in `research/batch-size-test-results.json`.
