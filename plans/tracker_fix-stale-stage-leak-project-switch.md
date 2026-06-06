# Tracker: fix/stale-stage-leak-project-switch

Card 6a23f5b9 — Stale failed/cancelled stage leaks across project switch

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments)
- [x] Move card to Doing
- [x] Create worktree and branch
- [x] Push branch

## Phase 2: Research
- [ ] Read pipeline/events.py (reset_buffer name/signature)
- [ ] Read active_project.py (shared switch seam)
- [ ] Read server.py /api/project/{new,open,materialize}
- [ ] Read debug_routes.py debug_seed_stage / debug_quick_project
- [ ] Read wizard.js pipeline_status handler + _failureShownSig
- [ ] Identify shared switch seam vs per-endpoint

## Phase 3: Design
- [ ] Decide placement of reset_buffer() call
- [ ] Decide client _failureShownSig reset

## Phase 4: Implement
- [x] Server: reset_buffer() in _project_switch_guard (open/new/materialize)
- [x] Debug: _reset_event_buffer() in quick-project/seed-stage/open-path
- [x] Client: resetFailureLatch() on in-place /api/project/new
- [x] Tests: 5 new endpoint tests

## Phase 5: Verify
- [x] ruff check . (clean)
- [x] ruff format . (clean, reverted unrelated drift)
- [x] python -c "import mtgai" (clean)
- [x] pytest (1971 passed, 1 skipped)

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review, fix findings
- [ ] git pull origin master
- [ ] Re-run lint + tests
- [ ] PR + self-merge
- [ ] Cleanup worktree + branch
- [ ] Delete tracker
- [ ] Move card to Done + comment
- [ ] Final overview
