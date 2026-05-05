# Tracker: feat/wizard-auto-advance

Card: [Wizard UI: auto-advance + Next-step button](https://trello.com/c/4PeIrdVa) (id `69f9e0fa`)

Refs: design doc §10 (auto-advance + AI-mutex interaction), §8.4 (Next-step button), umbrella tracker `plans/wizard-ui-redesign.md`.

## Phase 1: Pick up
- [x] Pull latest master
- [x] Read card + design doc
- [x] Move card to Doing
- [x] Create worktree + branch + push

## Phase 2: Research (done)
Findings:
- `engine._run_loop` already auto-advances stage→stage; pauses only on PAUSED_FOR_REVIEW
  (break point or always_review) or FAILED. So the "auto-advance through unbroken stages"
  half is already done; this card is about plumbing + the manual Next-step gesture.
- Theme is **not** a pipeline stage (`STAGE_DEFINITIONS` starts with `skeleton`); theme
  has no break-point UI. Once theme.json is written, the natural next action is to start
  the engine (which will run skeleton, etc., subject to break points).
- `/api/pipeline/start` (legacy configure.js entrypoint) takes a `PipelineConfig` body
  and creates the `PipelineState` + spawns the engine. Wizard needs the same kickoff
  but driven from `settings.toml` (set_params + break_points), not from a request body.
- `/api/pipeline/resume` already exists: marks the current PAUSED stage COMPLETED and
  re-enters `_run_loop`. Perfect for the Next-step button on a paused stage.
- "Don't steal focus" is already true: SSE handlers update `state.tabs[i].status` and
  `state.latestTabId`, but never `state.activeTabId`. Verified in wizard.js#updateStageStatus.
- Footer placeholders exist in both wizard_stage.js (`stageFooterHtml`) and
  wizard_theme.js — both say "Next-step button lands in a follow-up card". This is
  exactly the surface to replace.

## Phase 3: Design (done)
**Server side:**
- New helper `_kickoff_pipeline_engine(set_code: str)` in `pipeline/server.py`:
  - Loads settings.toml (`get_settings(set_code)`).
  - Builds `PipelineConfig(set_code, set_name, set_size, stage_review_modes)` from
    `set_params` + `break_points` (REVIEW for "review", AUTO otherwise).
  - Reuses or creates `PipelineState`, persists, sets `_engine`, spawns `engine.run`.
  - Idempotent: if pipeline-state.json already exists with overall_status NOT_STARTED
    or RUNNING, it's a no-op (engine already in flight).
- New endpoint `POST /api/wizard/advance` (request body `{"set_code": "..."}`):
  - If pipeline-state.json doesn't exist → kickoff engine.
  - If overall_status PAUSED → resume engine (existing logic).
  - If FAILED or COMPLETED → 400 (failed=Retry path is a separate card; completed has no next).
  - Returns `{"success": true, "navigate_to": "/pipeline/<next_stage>"}` on kickoff;
    just `{"success": true}` on resume (SSE handles tab spawn).
- Theme worker auto-advance: after `_persist_extraction_to_theme_json` succeeds AND
  pipeline-state.json doesn't exist yet, automatically call `_kickoff_pipeline_engine`.
  Server-side is the right place (single source of truth, no race between browsers).

**Client side:**
- `wizard_stage.js#stageFooterHtml`:
  - Latest tab + status `paused_for_review` → render Next-step button.
    Click → POST `/api/wizard/advance` with `{set_code}`.
  - Latest tab + final stage (`human_final_review`) + completed → "Set complete" text.
  - Else (failed, mid-stage) → existing placeholder text (retry is a separate card).
- `wizard_theme.js`: footer renders the Next-step button when:
  - theme.json exists (state.theme is non-null), AND
  - pipeline_state is null (engine hasn't been kicked off yet), AND
  - extraction is not active.
  Click → POST `/api/wizard/advance`.
- Don't steal focus: no client-side redirect on stage_update SSE; the new endpoint
  returns `navigate_to` only on the explicit click path so the user wins focus on
  their own action, not on a background event.
- Next-stage display name: derived client-side via the engine stage list.

## Phase 4: Implement
- [x] Server: `_kickoff_pipeline_engine(set_code)` helper
- [x] Server: `POST /api/wizard/advance` endpoint
- [x] Theme worker auto-advance hook
- [x] wizard_stage.js: footer Next-step / Set-complete rendering
- [x] wizard_theme.js: footer Next-step rendering
- [x] Test: advance endpoint kickoff path
- [x] Test: advance endpoint resume path
- [x] Test: helper idempotent on existing state

## Phase 5: Verify
- [ ] `ruff check .` clean
- [ ] `ruff format .` clean
- [ ] `python -c "import mtgai"` clean
- [ ] `pytest` clean
- [ ] Manual smoke: start a small set, watch tabs auto-advance with break off
- [ ] Manual smoke: set a break point, confirm Next-step button appears
- [ ] Manual smoke: navigate to past tab while a stage is generating, confirm focus is not stolen

## Phase 6: Ship
- [ ] Commit + push
- [ ] `/review` and address findings
- [ ] Merge master into branch
- [ ] Re-run lint + tests
- [ ] Merge to master + push
- [ ] Worktree cleanup
- [ ] Delete tracker doc
- [ ] Move card to Done + comment summary
- [ ] Tick checkbox on umbrella card 69f9e0ec
