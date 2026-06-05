# Phase-flow fixes (Trello: "Fix general phase flow issues" — 6a22bfc9)

## Context
The wizard is a linear strip of stage tabs. The card specifies how completed
vs active tabs, editing, LLM-run locking, cancel/restart, and auto-advance
should behave. Most of it is already implemented; this card closes the gaps.

## Gap analysis (8 requirements)
- R1 last=active / earlier=completed — **done** (`latestTabId` = rightmost; `isPastTab`).
- R2 completed tabs can't edit/reroll — **done** (rich tabs disable editing+reroll when past).
- R3 completed tabs have Edit + warning — **done** (`confirmCascade`).
- R4 Edit only when no LLM — **done** (`shouldShowEditButton` checks `isPipelineRunning`).
- R5 active tab edits+rerolls locked during LLM — **done** (`setTabLocked`/`aiBusy`).
- **R3a** edit unlocks the tab + deletes downstream — **gap** (see Design).
- **R6a** model change blocked only for the *running* stage — **gap** (no gating today).
- R6b "stop after this step" always toggleable — **done** (toggle lives in header-actions, not swept by `setTabLocked`).
- **R6c** sort/UI buttons always functional — **gap** (card_gen `cg-group-by`/`cg-filter` are swept by the form lock).
- R7 cancel halts → re-opens edits + active editing — **done** (cancel flips `overall_status` off `running`).
- **R7a** distinct restart vs reroll — **mostly done** (every stage tab's "Refresh AI" = reroll==restart; loop tabs add "Re-run this step"). Verify post-cancel enablement; no new generic button.
- R7b model change of active tab when halted — covered by R6a (dropdowns aren't blanket-locked).
- **R8** stage completes → next tab auto-opens (unless stop) — **gap** (no auto-nav today).

## Design (per user's R3a simplification + R8 "only if viewing the tip")

### R3a — Edit = "delete downstream, unlock this tab"
User chose the simple model: clicking Edit on a completed **stage** tab shows
one "this deletes every tab after this one" confirm; on Yes, downstream tabs'
data is deleted, this stage's output is **kept**, and the tab becomes the active
(latest), fully-editable, restartable tip. No deferred deletion, no draft/Cancel.

Theme + Project Settings keep their existing draft-based edit flow (their content
is cheap to revert and an edit there legitimately invalidates stage 0 onward).

Backend (`pipeline/server.py`):
- `_apply_downstream_clear(state, idx)` — mirror of `_apply_cascade_clear` but
  starts at `idx+1`: clears downstream artifacts + history + drops regen-inserted
  duplicate instances after `idx`, **keeps** `stages[idx]` output and sets it
  `PAUSED_FOR_REVIEW`, sets `overall_status = PAUSED`, `current_instance_id =
  stages[idx].instance_id`.
- `POST /api/wizard/edit/unlock {from_stage}` — 409 if engine/extraction running
  (same guards as `/edit/accept`); resolves the instance index (rejects
  `project`/`theme` — those use `/edit/accept`); calls `_apply_downstream_clear`;
  returns `{success, navigate_to: /pipeline/<from_stage>}`.
- `_compute_cascade_preview(..., after_only=False)` + `/edit/preview` accept
  `after_only` so the unlock modal lists downstream-only.

Frontend:
- `wizard.js` `editFlow`: add `unlock({from_stage})` and thread `after_only`
  through `preview`/`confirmCascade`.
- `wizard_stage.js` `bindEditButton`: Edit → `confirmCascade({after_only:true})`
  → on confirm `editFlow.unlock` → `window.location.assign(navigate_to)`. Drop the
  stage-tab draft/Accept/Cancel banner path (`editing` branch, `editFooterHtml`,
  `bindStageEditActions`) — stage tabs no longer enter draft mode.

After reload the edited stage is `latestTabId` + `PAUSED_FOR_REVIEW`, so its own
renderer shows the editable grid + Refresh AI (reroll/restart) + the Next-step
("start next phase") footer that resumes the engine into the cleared downstream.

### R6a — model change blocked only for the running stage
`wizard_project_save_model`: if the requested `stage_id` is currently running
(engine running with a `RUNNING` stage of that `stage_id`, or theme extraction
running and `stage_id == "theme_extract"`), return 409 with a clear message.
Other stages' model changes stay allowed mid-run. `saveModel` already toasts
`data.error`.

### R6c — sort/filter buttons always live
`wizard_card_gen.js` `setLocked`: drop `cg-group-by` + `cg-filter` from the
`setTabLocked` selectors (pure view controls — no data/process change).

### R8 — auto-open the next stage tab (only if viewing the tip)
`wizard.js` `updateStageStatus`: when a new instance becomes the latest tab
(the append branch), if the user's `activeTabId` was the *previous* latest tip,
`showTab(newInstance)`. If they navigated back to inspect an earlier tab, don't
yank focus. Break-point pauses don't append a new running stage, so "stop after
this step" naturally suppresses the auto-open.

## Tests
- `tests/test_pipeline/` (or wherever server edit-flow tests live): a test for
  `_apply_downstream_clear` (downstream cleared + reset PENDING, edited stage kept
  PAUSED_FOR_REVIEW, duplicate instances after idx dropped, overall=PAUSED).
- `wizard_project_save_model` 409 when the targeted stage is the running stage;
  200 for a different stage mid-run.
- `_compute_cascade_preview(after_only=True)` lists downstream-only.

## Out of scope
- Deferred-deletion / "cancel edits" backup (user opted for immediate delete).
- A new generic "Restart" button distinct from Refresh AI (existing affordances suffice).
- Live-disabling the running stage's model dropdown in the UI (backend 409 + toast is the guard).
