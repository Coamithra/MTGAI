# Tracker: fix/phase-flow — "Fix general phase flow issues"

Card: 6a22bfc9 (https://trello.com/c/SMPdSiMa)

## Requirements (from card)
- [ ] R1: Last tab = active; all previous tabs completed
- [ ] R2: Completed tabs cannot be user-edited or rerolled (would invalidate future tabs)
- [ ] R3: Completed tabs have an "edit" button → warning that editing invalidates (deletes) all future tabs and makes it active
- [ ] R3a: Future tabs NOT actually deleted until user edits/rerolls AND hits "start next phase". Until then a "cancel edits" button reverts the tab and re-locks it
- [ ] R4: "edit" button only usable when no current LLM process
- [ ] R5: Active tab's manual-edit + reroll buttons disabled while LLM running
- [ ] R6: Three exceptions while LLM running:
  - [ ] R6a: change model for a stage in project settings (unless that stage already running)
  - [ ] R6b: "stop after this step" checkbox always toggleable
  - [ ] R6c: sorting/UI buttons always functional
- [ ] R7: Cancel current LLM task halts pipeline → opens edit buttons on prev tabs + manual editing of active tab
  - [ ] R7a: each tab has clear "restart" option after a cancel; distinguish "reroll AI" vs full "restart"
  - [ ] R7b: if LLM halted, user can change model setting of active tab in project settings
- [ ] R8: When a stage completes, next stage auto-opens in UI (unless "stop after this step")

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card
- [x] Move card to Doing
- [x] Create worktree and branch

## Phase 2: Research — DONE
- [x] Map current wizard tab-lock / edit-cascade / active-tab model
- [x] Identify gaps vs the 8 requirements
- [x] Summarize findings (see plans/phase-flow-fixes.md)

## Phase 3: Design — DONE
- [x] Draft approach in plans/phase-flow-fixes.md
- [x] Align with user (R3a = simple delete-downstream + editable; R8 = auto-open only on tip)

## Phase 4: Implement — DONE
- [x] R3a backend: _apply_downstream_clear + /edit/unlock + after_only preview
- [x] R3a frontend: editFlow.unlock + bindEditButton single-confirm; drop stage-tab draft path
- [x] R6a backend: _stage_is_running 409 guard in wizard_project_save_model
- [x] R6c: card_gen sort/filter excluded from form lock
- [x] R8: auto-open new tip in updateStageStatus
- [x] Docs: wizard-tab-conventions.md §6 + CLAUDE.md edit-cascade note

## Phase 5: Verify — DONE
- [x] ruff check + format clean
- [x] pytest tests/test_pipeline (456 passed) incl. new unlock/downstream/model-gating tests
- [x] node --check on changed JS
- [ ] Manual smoke (flag: live-server walk of edit/unlock + auto-open + cancel→edit; needs models)

## Phase 6: Ship
- [ ] /review
- [ ] commit + PR + self-merge
- [ ] move card to Done + comment
