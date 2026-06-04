# Tracker: feat/unlimited-review-rounds

Card: [Conformance & Interactions (and other "returnable" stages) should not have a limit](https://trello.com/c/HV3WrQ28) (6a218781)

Desc: After C&I round 3 the app stops with a "review limit reached" pause. Instead it should just keep bouncing back to card regen — no limit. "Eventually the cards will conform ;)"

## Phase 1: Pick up
- [x] Read card
- [x] Move to Doing
- [x] Worktree + branch

## Phase 2/3: Research + Design
- [x] Locate limit: `MAX_REVIEW_ROUNDS = 3` in `pipeline/engine.py`; enforced in `_handle_rerun` (pauses at cap)
- [x] Confirm generic across all gates (keyed by gate_sid → covers conformance + ai_review + any returnable stage)
- [x] Confirm PAUSED_FOR_REVIEW still needed for break-points (lines 378/532/579) — keep it

Design: remove the cap. `_handle_rerun` always inserts a regen span. Drop the `"exhausted"` return + its handling in `run()`. Remove the `MAX_REVIEW_ROUNDS` constant. Update docstrings + CLAUDE.md note. Update tests.

## Phase 4: Implement
- [x] engine.py: remove constant, drop exhaustion branch, always insert
- [x] engine.py run(): drop `if rerun == "exhausted": return`
- [x] Update docstrings
- [x] CLAUDE.md: update the MAX_REVIEW_ROUNDS bullet
- [x] tests: rewrite test_gate_exhaustion_pauses_for_review → no-limit; drop MAX_REVIEW_ROUNDS import

## Phase 5: Verify
- [x] ruff check + format
- [x] python -c "import mtgai"
- [x] pytest tests/test_pipeline/test_review_loop.py
- [x] full pytest

- [x] wizard_conformance.js: drop stale "Review limit reached" pausedNote wording
- [x] full suite: 1818 passed, 1 skipped; ruff clean

## Phase 6: Ship
- [ ] Commit + push
- [ ] /review
- [ ] pull master, merge, cleanup
- [ ] move card Done + comment
- [ ] delete tracker
