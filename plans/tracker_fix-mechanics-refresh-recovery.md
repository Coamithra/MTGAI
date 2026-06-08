# Tracker: fix/mechanics-refresh-recovery

Card 6a26d56b — Mechanics refresh-recovery: pipeline doesn't auto-resume + stale 'failed' modal persists

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card
- [x] Move card to Doing
- [x] Create worktree and branch + push

## Phase 2: Research (done)
- [x] Read mechanics refresh endpoint (guarded_ai path)
- [x] Read engine kickoff / overall_status transitions
- [x] Trace how failed-state modal is surfaced + cleared
- [x] Identify root cause for BUG A (no auto-resume) and BUG B (stale modal)
- [x] Summarize findings

## Phase 3: Design (done)
BUG A: heal already does FAILED->PAUSED + Save&Continue. Add auto-resume when the
recovered stage's effective review mode is AUTO (no live break-point). Refactor the
advance PAUSED branch into `_resume_paused_engine()`; add `_should_auto_resume_recovered()`
predicate + call after the guarded_ai block in refresh-all + pick (gated on pre-state FAILED).
BUG B: `_heal_failed_stage` resets the SSE replay buffer (stale `failed` lingered + re-fired
on reconnect). Frontend: on any non-`failed` pipeline_status, dismiss the open failure modal +
reset the dedup latch.

## Phase 4: Implement (done)
- [x] `_resume_paused_engine()` helper + refactor advance
- [x] `_should_auto_resume_recovered()` + `_overall_status_is_failed()`
- [x] Wire auto-resume into refresh-all + pick
- [x] `_heal_failed_stage` resets replay buffer
- [x] Frontend: dismiss modal + reset latch on non-failed status
- [x] Tests (test_wizard_advance + test_wizard_mechanics)
- [x] Docs: wizard-tab-conventions.md §14 + §15

## Phase 5: Verify (done)
- [x] ruff check / format clean
- [x] smoke import
- [x] pytest (2103 passed; only pre-existing pydantic_settings env error in test_config.py)
- [ ] spot-check diff

## Phase 6: Review & Ship
- [x] commit + push
- [ ] /review + fix findings
- [ ] pull master, resolve conflicts
- [ ] PR + self-merge
- [ ] cleanup worktree/branch
- [ ] delete tracker
- [ ] move card to Done + comment
