# Tracker: refactor/stage-hooks-stream (B4 + F4)

Phase B4 + F4 of the wizard shared-components refactor (Trello `6a188a6b`, 5/9 done).
Plan: `plans/wizard-tab-shared-components.md` §Design B6 + F8.

## Phase 1: Pick up
- [x] Pull latest master (up-to-date)
- [x] Read card + plan + CONTRIBUTING
- [x] Worktree `.trees/refactor-stage-hooks-stream` on branch `refactor/stage-hooks-stream`
- [ ] Card stays in Doing (umbrella); tick B4+F4 checklist item at the end

## Phase 2/3: Research + Design (done — see notes below)
- [x] Read engine path (stages.py run_mechanics/run_skeleton/run_card_gen)
- [x] Read refresh path (server.py mechanics refresh-card/all, card_gen state/refresh, skeleton refresh)
- [x] Read StageEmitter/EventBus (events.py)
- [x] Read frontend stream handlers (wizard.js dispatch + 3 tab handlers)
- [x] Confirm tests (test_wizard_mechanics/card_gen, test_card_tile_dict)

## Phase 4: Implement — B4 (backend)
- [x] NEW `pipeline/stage_hooks.py`: moved `card_tile_dict`; added `slots_by_id_from_skeleton`,
      `build_mechanic_hooks`, `build_skeleton_hooks` + `emit_skeleton_done`,
      `build_card_gen_hooks` + `emit_card_gen_reset`
- [x] `stages.py`: dropped card_tile_dict def; wired run_mechanics/run_skeleton/run_card_gen
- [x] `server.py`: StageEmitter + _refresh_emitter; wired mechanics refresh-card/all,
      card_gen state/refresh, skeleton refresh; slots_by_id_from_skeleton
- [x] `test_card_tile_dict.py`: import from stage_hooks
- [x] NEW test_stage_hooks.py: payload parity (engine vs refresh identical) + slot_for/collision/persist

## Phase 4: Implement — F4 (frontend)
- [x] `wizard_util.js`: `W.registerStream(stageId, handlers)` + `W.streamUpsert(list,item,keyFn)`
- [x] `wizard_card_gen.js`: registerStream; dropped liveRoot; uses streamUpsert
- [x] `wizard_skeleton.js`: registerStream
- [x] `wizard_mechanics.js`: registerStream

## Phase 5: Verify
- [x] ruff check . = 62 (baseline unchanged); format clean on touched files
- [x] python -c "import mtgai" ok
- [x] pytest = 1402 (1390 baseline + 12 new)
- [x] node eval-harness: 25 modules load clean; helpers + hooks present; registerStream/streamUpsert/escHtml behavior

## Phase 6: Review & Ship
- [ ] /review (cold, give worktree path + branch ref); fix findings
- [ ] pull master; merge; lint+test
- [ ] direct merge to master (ff) + push
- [ ] worktree cleanup; delete tracker
- [ ] tick B4+F4 checklist item + comment on card

---

## Design notes

### B4 — pipeline/stage_hooks.py
Refresh endpoints construct a real `StageEmitter(event_bus, stage_id, monotonic())` and reuse the
SAME hook builders the engine uses → engine & refresh can't drift in payload shape. (Side-fix: refresh
stream events now carry `instance_id` via emitter.event, matching the engine; FE ignores it.)

- `card_tile_dict(card, slots_by_id)` — moved here from stages.py (breaks the stages↔stage_hooks
  cycle, since the card_gen hook needs it). stages.py no longer references it directly; server.py +
  test import from stage_hooks now.
- `slots_by_id_from_skeleton(path) -> dict` — the {slot_id: slot} map build duplicated 3× (engine
  run_card_gen, card_gen_state, card_gen_refresh). Safe read, returns {} on missing/bad.
- `build_mechanic_hooks(emitter, *, pool, merged, candidates_path, known_keywords, slot_for=None,
  fire_reset=True, emit_phase=False)` → (on_reset, on_draft, on_finalized).
  - slot_for(position)->0-based slot: engine identity (p-1); refresh-card const idx; refresh-all _slot_for.
  - fire_reset: engine True; refresh-card N/A (no on_reset passed); refresh-all initial_generate only.
  - emit_phase: engine True (per-candidate phase ticks); refresh False (uses showBusy client-side).
  - owns _ai_generated tag, collision (name.lower() in known_keywords), incremental persist
    (atomic_write_text == old _write_json), canonical event payloads.
- `build_skeleton_hooks(emitter)` → (on_slot, on_reset); `emit_skeleton_done(emitter, *, incomplete, relabeled)`.
  on_progress phase tick stays in each caller (engine emitter.phase / refresh event_bus.stage_phase) —
  not a bespoke stream event, intentionally differs (elapsed telemetry).
- `build_card_gen_hooks(emitter, *, slots_by_id)` → (on_card_saved,); `emit_card_gen_reset(emitter)`.
  Engine does NOT emit reset (first run empty, resume keeps cards); refresh does (wiped cards/). Kept
  parameterized — not flattened.

### F4 — W.registerStream
- `W.registerStream(stageId, handlers)` — owns `W.on<Pascal>Stream` assignment + name→fn dispatch +
  fresh root resolution. handlers: `{ [sseEventName]: (data, root) => void }`, root = W.tabRoot(stageId).
- `W.streamUpsert(list, item, keyFn)` — merge-by-key/append primitive (card_gen by collector_number).
  skeleton (find-mutate in place) + mechanics (positional w/ padding) keep bespoke logic — they don't
  fit upsert-append; registerStream still dedups their dispatch boilerplate.
- card_gen drops `local.liveRoot` (root now passed per-event).
