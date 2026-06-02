# Tracker: fix/engine-reprints-lands-ai-lock

Card: [Engine reprints/lands stages don't hold the AI lock](https://trello.com/c/axoC5rA1) (`6a1967d1`)

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments)
- [x] Move card to Doing
- [x] Create worktree and branch
- [ ] Push branch

## Phase 2: Research
- [x] Read run_reprints / run_lands in stages.py — confirmed no ai_lock.hold
- [x] Confirm canonical pattern (run_skeleton / run_card_gen / run_conformance)
- [x] Confirm workers poll ai_lock.is_cancelled() (reprint_selector, land_generator)
- [x] Confirm generate_lands returns {"cancelled": True}; select_reprints returns partial

## Phase 3: Design
Wrap the worker call in run_reprints and run_lands in `with ai_lock.hold(...)`:
- `if not acquired: return StageResult(success=False, "Another AI action holds the lock…")`
- after the worker, check cancel -> `return StageResult(success=False, …)` to halt the engine
  - reprints: `if ai_lock.is_cancelled()` before persisting the selection
  - lands: `if result.get("cancelled") or ai_lock.is_cancelled()` before cascade/persist of done
- Add local `from mtgai.runtime import ai_lock` import in each runner (mirrors run_skeleton)

## Phase 4: Implement
- [x] run_reprints: wrap select_reprints + cancel guard
- [x] run_lands: wrap generate_lands + cancel guard
- [x] Added 4 tests (busy-guard + cancel-halt for each) to test_stages_phase_emission.py

## Phase 5: Verify
- [x] ruff check . / ruff format . (clean)
- [x] python -c "import mtgai" (OK)
- [x] pytest tests/test_pipeline tests/test_runtime — 454 passed

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review, fix findings
- [ ] Pull master, merge, push
- [ ] Clean up worktree/branch
- [ ] Delete tracker
- [ ] Move card to Done + comment
