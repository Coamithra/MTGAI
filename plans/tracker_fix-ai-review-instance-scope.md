# Tracker: fix/ai-review-instance-scope (card 6a29a27f)

## Phase 1: Pick Up
- [x] Claim card (two-phase handshake)
- [x] Pull master
- [x] Read card + CONTRIBUTING
- [x] Create worktree + branch + push

## Phase 2: Research
- [ ] Read wizard_ai_review.js
- [ ] Read /api/wizard/ai_review/state endpoint + _effective_decision in server.py
- [ ] Read card_gen precedent (run_target scoping, is_new, entry_snapshot_id) in server.py
- [ ] Read pipeline/wizard.py tab payload for ai_review
- [ ] Read ai_review.py for flagged_by, regen_reason, verdict semantics
- [ ] Read history.py / engine for entry_snapshot_id, instance machinery
- [ ] Read plans/wizard-tab-conventions.md
- [ ] Find existing ai_review endpoint tests

## Phase 3: Design
- [ ] P1: scope headline + per-tile carried-over vs this-round
- [ ] P2: amber conformance-flag-accepted chip vs red-X design rejection
- [ ] Decide "this instance's cards" source (entry snapshot diff vs flagged subset)

## Phase 4: Implement
- [x] ai_review.review_is_stale helper
- [x] server.py state endpoint (load reviewed.json, drop stale reviews, upstream chip)
- [x] wizard_ai_review.js (flagged_upstream state)
- [x] wizard.py payload — not needed

## Phase 5: Verify
- [x] ruff check / format
- [x] smoke import
- [x] pytest (extend ai_review state tests) — 2671 passed
- [ ] manual-verification note for JS

## Phase 6: Ship
- [ ] commit + push
- [ ] /review
- [ ] pull master into branch
- [ ] PR + self-merge
- [ ] cleanup worktree/branch
- [ ] delete tracker
- [ ] card -> Done + comment
