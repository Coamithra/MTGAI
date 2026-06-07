# Fix: Cancel/progress-strip hidden during char_portraits + art_gen image phase

Card 6a256732.

## Context
During the `char_portraits` ("Character References") and `art_gen` ("Art Generation")
tab-refresh actions, the long ComfyUI/Flux image-generation phase runs the AI lock but the
global progress strip + its Cancel button are hidden, so a ~20-min image phase is
uncancellable via the UI.

## Root cause (verified)
Two independent JS/SSE-flow facts combine:

1. **`runAiAction({busyLabel})` → `showBusy()` HIDES the Cancel button**
   (`wizard.js` `showBusy`: `cancelEl.style.display = 'none'`). It is restored only by
   `clearBusy()` at the very end of the action. So for the *whole* refresh action the engine
   Cancel button is hidden — yet `ai_lock.is_cancelled` *is* honoured by these workers, so the
   action is genuinely cancellable; only the affordance is missing.

2. **`_bus_poller(..., emit_done=True)` emits a terminal `phase:"done"` on context exit**
   (`server.py` `_bus_poller`). `wizard.js` `handlePhaseEvent` treats `phase==='done'` as the
   whole action finishing → `hideProgressStrip()` (strip hidden, clock stopped, bar reset).
   - **char_refs:** the `detect_poller` wraps ONLY the detection LLM call (correct — must not
     poll llama-swap during image gen, cards 6a25497b/6a254d60). Its exit fires `done` while the
     guarded action continues into the image phase → strip torn down for the whole image phase.
     The image phase emits only `char_refs_*` tile events (no `phase`), so nothing re-shows it.
   - **art_gen:** image gen runs FIRST with NO poller, then the judge poller runs LAST. During
     the (long, first) image phase there are no `phase` events at all → the strip is only
     `showBusy`'s (cancel hidden). The judge poller's terminal `done` then hides the strip — but
     that's at the very end, which is fine.

The **engine** path (`stages.run_char_portraits` / `run_art_gen`) does NOT have the bug:
it uses `make_poller` (no terminal `done`) and never calls `showBusy`, so the strip stays
visible (cancel at default-visible) through the image phase, just with a stale label.

## Design (file-by-file)

### Keep the strip alive during image gen by emitting indeterminate `phase("running")` ticks from the image-phase hooks
The image phase already fires per-entity / per-card hooks. Drive an indeterminate strip phase
from them so `handlePhaseEvent` re-shows the strip during image gen — for BOTH engine and
refresh paths (also fixes the engine path's stale label).

- `pipeline/stage_hooks.py` `build_char_refs_hooks`: in `on_entity_start`, also call
  `emitter.phase("running", "Generating reference images…")` alongside the existing
  `char_refs_entity` event. No live stats → `handlePhaseEvent` shows an honest indeterminate bar.

- `pipeline/server.py` `wizard_char_refs_refresh`: pass `emit_done=False` to the detect_poller
  so detection ending no longer tears down the strip. (The image-phase `phase("running")` ticks
  now keep it alive; `clearBusy()` in `runAiAction`'s `finally` is the single teardown.)

- `pipeline/server.py` `wizard_art_gen_refresh`: thread a progress callback into
  `generate_art_for_set` that emits `emitter.phase("running", "Generating art…")` (and an
  `art_gen_card` tile, matching the engine path) so the strip stays alive + cancel visible
  through the (first) image phase. The judge poller keeps `emit_done=True` (it is the last span;
  its `done` correctly closes the strip at the very end). Also apply the same `art_gen_card`
  progress callback to `wizard_art_gen_reroll`.

### Make the Cancel button re-appear whenever the strip is shown for a live phase
`wizard.js` `handlePhaseEvent`: when it shows the strip for a non-`done` phase, ensure the
engine Cancel button is visible (it was hidden by an earlier `showBusy`). A `phase` event only
fires for a real, in-flight, cancellable AI run, so showing Cancel here is correct. This undoes
`showBusy`'s hide once the image-phase ticks arrive, and is harmless for engine phases (cancel
already visible).

## Out of scope
- Not changing the deliberate poller scoping (no llama-swap polling during image gen).
- Not reworking `showBusy`/`runAiAction` globally; the targeted `handlePhaseEvent` cancel-restore
  is enough and least-risky.

## Tests
- `tests/test_pipeline/` (or nearest): a unit test asserting `_bus_poller(..., emit_done=False)`
  does NOT publish a terminal `phase:"done"`, and `emit_done=True` does (guarding the contract).

## Verification
- `ruff check .` / `ruff format .` clean; `python -c "import mtgai"`; `pytest` green.
- Live Flux verification (strip + Cancel visible through the image phase) by the QA bot post-merge.
