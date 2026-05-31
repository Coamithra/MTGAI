# Progress strip telemetry — tok/s coverage + cold-load heartbeat

Status: planned (Trello ticket filed 2026-05-31). Born from the local-LLM
investigation — see the tok/s symptoms below.

## Problem

The wizard's global progress strip (`#wiz-progress-strip`) shows live
prompt-eval / generation **tok/s** only sometimes:

1. **Coverage gap.** Live tok/s comes from a `PromptEvalPoller`
   (`generation/phase_poller.py`) that polls llama-server's `/slots` and emits
   `generation` phase events with `tok_per_sec`. It is only wrapped around **3
   stages**: `theme_extract`, `reprints`, `lands`. Every other local-model
   stage — `card_gen`, `mechanics`, `archetypes`, `skeleton` (relabel),
   `conformance`, `balance`, `ai_review`, `visual_refs`, `art_prompts` — runs
   without a poller, so the strip shows an indeterminate/static bar with no rate.

2. **Frozen label during prompt-eval (esp. after a model switch).** llama-server
   build **9010** dropped `n_prompt_tokens` / `n_prompt_tokens_processed` from
   `/slots` (captured payload keys: `id, id_task, is_processing, n_ctx,
   next_token, params, speculative` — only `next_token[0].n_decoded` survives).
   So the prompt-eval phase has no progress counter, and for a big input (theme
   extraction's ~minutes-long prompt eval, made worse by a cold-model load right
   after a switch) the strip **freezes on the last static label** until decoding
   starts. The generation-rate path itself is sound — confirmed `/slots` exposes
   `n_decoded` live and the frontend renders it.

3. **Silent failures.** The poll loop swallows `slots()` exceptions at DEBUG, so
   a genuine generation-phase drop is invisible in normal logs.

## Plan

### A. Poller hardening (`generation/phase_poller.py`)
- **Elapsed heartbeat in the dark window.** When there is no active slot / no
  counters (cold load, or build-9010 prompt-eval), emit a time-based
  `"{prefix} — evaluating prompt ({elapsed}s)"` heartbeat so the strip never
  freezes even when `/slots` returns nothing usable.
- **Diagnostic.** Promote the swallowed `slots()` failure to a **once-per-run
  WARN** including the resolved `/upstream/<model>/slots` URL, so a real failure
  (wrong target, wedged probe) is catchable instead of silent.

### B. Coverage rollout
Wrap each remaining local-model generate call in `PromptEvalPoller` (the proven
`reprints`/`lands` pattern at `stages.py:762/895`). Two emit paths:
- **Engine stage runners** (`stages.py`, `card_generator.py`,
  `mechanic_generator.py`, …): emit via `StageEmitter.phase`.
- **Tab-refresh endpoints** (`server.py`: mechanics "Re-pick with AI" / candidate
  refresh, card refresh, skeleton refresh, …): route the poller's emit through
  `event_bus.publish` so it paints the same strip the indeterminate `showBusy()`
  uses today.
Stages to cover: `card_gen`, `mechanics`, `archetypes`, `skeleton`,
`conformance`, `balance`, `ai_review`, `visual_refs`, `art_prompts`.
Order: **`card_gen` + `mechanics` first** (highest value), then the rest.

### C. Consolidate the two poller copies
`theme_extractor.py` carries its own `_PromptEvalPoller` (≈ lines 1371–1562)
duplicating `phase_poller.py`. Collapse onto the shared implementation so the
hardening in (A) lands once.

### D. Verify
Switch a stage to a **cold** local model, hit refresh: confirm the heartbeat
ticks during load + prompt-eval and tok/s shows during generation — on both an
engine run and a tab refresh. Spot-check cloud stages stay `NullPoller` (no
`/slots`).

## Notes / out of scope
- The build-9010 `/slots` counter drop is upstream llama.cpp; we adapt
  (heartbeat) rather than depend on those fields. Re-check if a future build
  restores `n_prompt_tokens*`.
- Cloud (Anthropic) stages have no `/slots` → stay `NullPoller`.

## Acceptance
- Live tok/s + a non-frozen prompt-eval heartbeat on **every** local-model stage,
  engine *and* tab-refresh.
- No frozen label during long prompt-eval / cold load.
- A single `PromptEvalPoller` implementation.

## Code refs
`generation/phase_poller.py` (poller), `pipeline/theme_extractor.py:1371–1562`
(duplicate poller + `_emit_phase`), `pipeline/stages.py:762/895`
(reprints/lands pattern), `pipeline/server.py` (tab-refresh endpoints),
`gallery/templates/static/wizard.js` `handlePhaseEvent` (renders `prompt_eval` +
`generation.tok_per_sec`).
