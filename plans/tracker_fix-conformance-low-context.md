# Tracker: fix/conformance-low-context-local

## Phase 1: Pick Up the Card
- [x] Claim the top card (two-phase handshake — won, claim 101651db earliest)
- [x] Pull latest master
- [x] Read the card (desc + comments)
- [x] Create worktree and branch

## Phase 2: Research
- [ ] Read interactions.py (BATCH_SIZE, cumulative context)
- [ ] Read gate_common.py (stream_flag_batch, check_pre_call path)
- [ ] Read conformance.py
- [ ] Read model_settings.py (_CONFORMANCE_FULL_CONTEXT_SET_SIZE, get_llm_model_id)
- [ ] Read model_registry context_window + twin resolution
- [ ] Trace how context_window is read; how stream_text pre-call check raises
- [ ] Summarize findings

## Phase 3: Design
- [ ] Draft approach (clamp BATCH_SIZE / sliding window / UI warning)
- [ ] Check reusable patterns
- [ ] Align with user

## Phase 4: Implement
- [ ] Make the changes
- [ ] Document conventions (CLAUDE.md if needed)

## Phase 5: Verify
- [ ] ruff check + format
- [ ] python -c "import mtgai"
- [ ] pytest
- [ ] Manual smoke if needed
- [ ] Spot-check diff

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review
- [ ] Pull master into branch
- [ ] Re-run lint + tests
- [ ] PR + self-merge
- [ ] Clean up worktree/branch
- [ ] Delete plan + tracker
- [ ] Move card to Done + comment
- [ ] Follow-up cards
- [ ] Overview to user
