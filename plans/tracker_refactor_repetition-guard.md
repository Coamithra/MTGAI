# Tracker: refactor/repetition-guard

Card: Adopt llmfacade RepetitionGuard; remove our own repetition-loop detector (`6a235414`)

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments)
- [x] Move card to Doing
- [x] Create worktree and branch

## Phase 2: Research
- [x] Inventory our own repetition detection (theme_extractor `_detect_tandem_repeat`/`_detect_repetition_loop` + bands + integration + test)
- [x] Understand llmfacade RepetitionGuard API (send retries; stream aborts; scans output+tool args, not thinking)
- [x] Confirm llmfacade is editable path dep → RepetitionGuard already importable
- [x] Read llm_client.py call sites + theme_extractor streaming path

## Phase 3: Design
- [x] Draft plan in plans/repetition-guard.md
- [x] Align with user (approval gate) — central adoption chosen

## Phase 4: Implement
- [x] Central guard config + wire into llm_client llamacpp convos
- [x] Wire guard into theme_extractor streaming; remove bespoke detector + bands
- [x] Handle RepetitionLoopError: convert→OutputTruncatedError (send); stream consumers already catch
- [x] Retire test_repetition_detector.py; add wiring tests
- [x] Update CLAUDE.md + learnings

## Phase 5: Verify
- [x] ruff check + ruff format (clean)
- [x] python -c "import mtgai" (OK)
- [x] pytest (1938 passed; 1 pre-existing env collection error in test_config.py)
- [ ] Manual smoke (local theme extraction, forced loop) — flag for user
- [x] Spot-check diff

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review, fix findings
- [ ] Pull master into branch, resolve conflicts
- [ ] Re-run lint + tests
- [ ] PR + self-merge, fast-forward master
- [ ] Clean up worktree + branch
- [ ] Delete plan + tracker
- [ ] Move card to Done + comment
- [ ] Follow-up cards (e.g. llmfacade thinking-loop detection)
- [ ] Write overview to user
