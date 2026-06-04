# Tracker: fix/midrun-stop-after-step

Card: [Make "[ ] stop after this step" work when pressed mid-run](https://trello.com/c/0pXQApCg) (id `6a218a076e311541d92d7bb6`)

## Phase 1: Pick Up the Card
- [x] Pull latest master (worktree branched off master @ 5d84556)
- [x] Read the card + trace the feature
- [x] Move card to Doing
- [x] Create worktree and branch

## Phase 2: Research
- [x] Trace the toggle: wizard_stage.js -> POST /api/wizard/project/breaks -> apply_settings(break_points)
- [x] Trace the engine pause decision: engine.py _run_loop line ~377 reads FROZEN stage.review_mode
- [x] Root cause: review_mode is frozen at build (build_stages/_build_initial_states); live break_points changes never reach a running/pending stage
- [x] Confirm apply_settings -> write_active_project -> read_active_project share the pointer (engine thread sees live toggles)
- [x] Confirm backbone instance discriminator: instance_id == stage_id (make_instance_id)

## Phase 3: Design
- [x] Fix: at the engine pause decision, re-resolve the LIVE break point for BACKBONE instances (sync stage.review_mode), leaving inserted regen-loop instances pinned AUTO (preserves _build_rerun_span contract)
- [x] Align with user (small isolated engine fix; proceeded)

## Phase 4: Implement
- [x] engine.py: add live break-point re-resolve before the pause check
- [x] CLAUDE.md: note the live re-resolve

## Phase 5: Verify
- [x] ruff check / ruff format clean
- [x] import mtgai smoke ok
- [x] pytest: full suite 1838 passed, 1 skipped (3 new tests)
- [x] Spot-check diff

## Phase 6: Review & Ship
- [ ] Commit + push branch
- [ ] /review, fix findings
- [ ] Pull master, resolve conflicts
- [ ] Merge to master (CONFIRM with user — dirty master tree)
- [ ] Clean up worktree/branch, delete tracker
- [ ] Move card to Done + comment
- [ ] Final overview
