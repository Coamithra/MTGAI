# Tracker: feat/ai-design-review-ui

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments)
- [x] Move card to Doing
- [x] Create worktree and branch, push -u

## Phase 2: Research
- [x] Read CONTRIBUTING.md + wizard-tab-conventions.md
- [x] Read ai_review.py (CardReviewResult shape, review_set/review_all_cards, council/single, _apply_revision)
- [x] Read existing wizard_ai_review.js scaffold (list view, TODO endpoints)
- [x] Read wizard_conformance.js (streaming gate analog) + wizard_card_gen.js (tiles/regen analog)
- [x] Read wizard_mechanics.js council panel (thumbs up/down reference)
- [x] Read stage_hooks.py, run_ai_review/run_conformance in stages.py
- [x] Read server.py card_gen endpoints + helpers (card_tile_dict, _heal_failed_stage, guarded_ai, etc.)
- [x] Read wizard.js SSE routing

## Phase 3: Design
- [x] Write plan (this file's sibling: ai-design-review-ui.md)

## Phase 4: Implement
- [x] Backend: stream hooks for ai_review council (stage_hooks.py)
- [x] Backend: thread council/review hooks through review_set/review_all_cards/_review_single/_review_council
- [x] Backend: run_ai_review wires hooks; build_ai_review_hooks
- [x] Backend: GET /api/wizard/ai_review/state
- [x] Backend: POST /api/wizard/ai_review/approve, /revise, /regenerate
- [x] Backend: register events in wizard.js (status via shell, no resolver needed)
- [x] Frontend: rewrite wizard_ai_review.js (tiles, stamps, council thumbs, submenu)
- [x] CLAUDE.md doc update (wizard-tab-conventions §17 already names ai_review as adopter)

## Phase 5: Verify
- [x] ruff check . / ruff format .
- [x] python -c "import mtgai"
- [x] pytest (1642 passed via root venv; new files: test_ai_review_ui, test_wizard_ai_review, test_stage_hooks)
- [x] Manual smoke (server starts, route 302s w/o project, static JS + SSE wiring served, HTTP tests cover /state+actions). Live council animation + revise LLM need a model → manual-only.
- [x] JS node --check syntax pass
- [ ] Spot-check diff

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review, fix findings
- [ ] Pull master, resolve conflicts
- [ ] Re-run lint + tests
- [ ] Merge to master, push
- [ ] Clean up worktree/branch
- [ ] Delete plan + tracker
- [ ] Move card to Done + comment
