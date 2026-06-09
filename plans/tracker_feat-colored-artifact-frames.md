# Tracker: feat/colored-artifact-frames

## Phase 1: Pick Up the Card
- [x] Claim the top card — moved to Doing
- [x] Pull latest master
- [x] Read the card (description, comments, linked learnings doc)
- [x] Create worktree and branch

## Phase 2: Research
- [x] Read learnings/colored-artifact-frames.md
- [x] Read colors.py frame_key_for_identity + COLOR_TO_FRAME_KEY
- [x] Read card_renderer.py determine_frame_key + _load_frame + _load_pt_box
- [x] Read layout.py frame_path / pt_box_path
- [ ] Summarize findings

## Phase 3: Design
- [ ] Align with user on approach (A/B/C/D — flagged TBD)
- [ ] Draft file-by-file plan

## Phase 4: Implement
- [ ] Generate/blend colored artifact frame variants
- [ ] colors.py: compound artifact frame keys
- [ ] card_renderer.py: pick colored variant for colored artifacts
- [ ] Update CLAUDE.md / learnings doc if contract changes

## Phase 5: Verify
- [ ] ruff check . / ruff format .
- [ ] python -c "import mtgai"
- [ ] pytest
- [ ] Render a colored artifact card, eyeball PNG vs Scryfall ref
- [ ] Spot-check diff

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review, fix findings
- [ ] Pull master into branch
- [ ] Re-run lint + tests
- [ ] PR + self-merge, fast-forward master
- [ ] Clean up worktree/branch
- [ ] Delete tracker + update learnings doc
- [ ] Move card to Done + comment
- [ ] Follow-up cards
- [ ] Final overview to user
