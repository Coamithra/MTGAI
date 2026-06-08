# Tracker: fix/review-tip-deadend

## Phase 1: Pick Up
- [x] Pull latest master
- [x] Read card 6a26895c + reference commit 39e8afb
- [x] Move card to Doing
- [x] Create worktree + branch + push

## Phase 2: Research
- [ ] Read wizard_ai_review.js paintFooter
- [ ] Read wizard_util.js for shared footer helpers
- [ ] Audit conformance/finalize/loop tab footers
- [ ] Identify can_advance server seam (_stage_advance_state)

## Phase 3: Design
- [ ] Decide shared JS helper + shared server can_advance approach

## Phase 4: Implement
- [ ] Shared JS helper (W.completedTipCanAdvance or similar)
- [ ] Add can_advance to ai_review/state + other tab state endpoints
- [ ] Wire footers in affected tabs

## Phase 5: Verify
- [ ] ruff check + format
- [ ] smoke import
- [ ] pytest
- [ ] extend test_wizard_advance.py

## Phase 6: Ship
- [ ] commit + push
- [ ] /review + fix findings
- [ ] pull master, merge
- [ ] PR + self-merge
- [ ] cleanup worktree/branch
- [ ] delete tracker
- [ ] move card to Done + comment
