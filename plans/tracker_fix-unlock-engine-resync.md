# Tracker: fix/unlock-engine-resync

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card
- [x] Move card to Doing
- [x] Create worktree and branch

## Phase 2: Research
- [ ] Read _apply_downstream_clear + /edit/unlock handler
- [ ] Read _get_current_state, _engine usage
- [ ] Read _kickoff_pipeline_engine + /edit/accept path
- [ ] Determine the right resync call (keep stage PAUSED_FOR_REVIEW, no auto-run)

## Phase 3: Design
- [ ] Decide fix shape

## Phase 4: Implement
- [ ] Resync engine after unlock
- [ ] Regression test

## Phase 5: Verify
- [ ] ruff check + format
- [ ] smoke import
- [ ] pytest

## Phase 6: Ship
- [ ] commit + push
- [ ] /review
- [ ] pull master, resolve conflicts
- [ ] PR + self-merge
- [ ] cleanup worktree/branch
- [ ] delete tracker
- [ ] move card Done + comment
