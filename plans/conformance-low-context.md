# Bound the interaction gate's cumulative context to the assigned model's actual window

Trello: [Review conformance/interaction gate for low-context local models](https://trello.com/c/5rK8AkcW)

## Context

The merged `conformance` gate's **interaction step** (`analysis/interactions.py`)
scans for degenerate combos in **cumulative-context batches**: batch *i* is shown
every previously-reviewed card as *existing context* plus its ~20 *new* cards. So
the existing-context block — and the whole prompt — **grows with set size**; the
last batch's prompt is roughly the whole pool.

`model_settings.get_llm_model_id("conformance")` resolves the assigned base to its
48k downstream twin *except* once `set_size >= 400`, where it keeps the base's full
window (`_CONFORMANCE_FULL_CONTEXT_SET_SIZE`). Both assume the assigned base has a
large window.

**Bug:** if the user assigns a **low-context local model** to `conformance` (a base
whose `context_window` is smaller than the largest cumulative interaction batch),
the prompt outgrows the window. `stream_text` calls `token_utils.check_pre_call`,
which raises `ContextOverflowError`. `gate_common.stream_flag_batch` catches that as
a failed attempt, **retries at the same size** (deterministically fails again),
then returns `completed=False` → the batch's cards are marked `interacts=None`
("unknown"). The gate **degrades quietly** — cards silently skip interaction review.

## Design

Bound the cumulative existing-context to the assigned model's **actual** context
window (read from the registry, not assumed 128k). This combines two of the card's
options: a **sliding window** (most-recent cards) whose size is **derived from the
model's real `context_window`**. Net effect:

- **Large model (cloud 200k / Gemma base 128k):** nothing is dropped — full
  cross-batch coverage preserved (the change is a no-op for the common case).
- **Low-context model:** each batch's existing-context is trimmed to the most
  recent cards that fit, so the prompt never trips `ContextOverflowError`; coverage
  of far-apart pairs degrades (the accepted trade-off) but the gate keeps running.
- It **degrades loudly**: a single WARN names the model, its window, the set size,
  and how many context cards were dropped — instead of silently leaving cards
  unchecked.

### File-by-file

`backend/mtgai/analysis/interactions.py`:
- New helper `_bound_existing_context(existing, *, model, new_tokens, mechanics_tokens, system_tokens, tok_by_id)` → `(kept, dropped)`. Computes the per-batch existing-context token budget from `get_context_window(model)`, mirroring `check_pre_call`'s arithmetic (`int(ctx * (1 - SAFETY_MARGIN)) - MAX_TOKENS - system - new - mechanics - scaffold`), then keeps the most-recent cards (tail) within budget. `existing_budget <= 0` → send no existing context (extreme tiny model).
- In `analyze_interactions`: precompute `tok_by_id` (per-card serialized token cost) + `system_tokens` + `mechanics_tokens` once; per batch, trim `existing` through the helper before `_build_batch_prompt`; accumulate the dropped count and emit one WARN at the end when any trimming happened.
- A small constant `_PROMPT_SCAFFOLD_TOKENS` (generous flat reserve for headers/fences/task paragraph + `count_messages_tokens` per-message overhead).

No change to `gate_common.py` / `conformance.py` (conformance batches are fixed-size, not cumulative — they don't grow with set size).

### Tests (`tests/test_pipeline/test_conformance_gate.py`)
- `test_bound_existing_context_*`: unit-test the helper — large window keeps all; tiny window keeps only the recent tail; `<=0` budget drops all.
- `test_analyze_interactions_low_context_trims_existing`: with a small monkeypatched `context_window`, the later batch's prompt shows fewer "Existing cards (N)" than the full pool (proving the bound applied) and the run still completes (no `interacts=None`).
- `test_analyze_interactions_large_context_keeps_full_coverage`: with a large window, existing-context is untrimmed (regression guard for the no-op path) — the existing `test_analyze_interactions_cumulative_context` already covers this; extend/assert as needed.

## Out of scope
- **UI warning** when the assigned conformance base is too small for the set size
  (the card's 3rd option) — additive polish spanning the Project Settings payload +
  JS. Tracked as a follow-up card.
- Clamping `BATCH_SIZE` of *new* cards — the new batch is fixed at 20 (small); the
  cumulative existing-context is the only part that grows with set size, so bounding
  it solves the reported failure. A genuinely tiny model still can't honour a full
  20-card new batch, but that's the follow-up warning's job, not silent failure.
