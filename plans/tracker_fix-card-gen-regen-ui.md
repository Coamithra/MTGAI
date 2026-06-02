# Tracker: fix/card-gen-regen-ui

Card 6a1e13b4 — "Later instances of Card Generation phase show 'X / Y cards generated' where
Y is the total set size rather than the nr of cards that this phase needs to re-create. Also
this UI should distinguish visually between 'old' cards and new ones created during it."

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (desc is just the title; no linked plan)
- [x] Move card to Doing
- [x] Create worktree + branch (fix/card-gen-regen-ui)

## Phase 2: Research
- [x] Map card_gen progress UI + count flow (card_generator.py, stages.py, server.py, wizard_card_gen.js)
- [x] Confirm Y = len(all_slots) bug (card_generator.py:1193, 1487, 1542)
- [x] Confirm old/new distinction data path (entry_snapshot_id + history snapshots)

## Phase 3: Design
- [x] Draft approach (plans/card-gen-regen-ui.md)
- [ ] Align with user — get approval

## Phase 4: Implement
- [ ] Part 1: run_target count fix in generate_set
- [ ] Part 2a: card_tile_dict is_new param + SSE on_card_saved is_new=True
- [ ] Part 2b: /state endpoint computes regenerated set via entry-snapshot diff
- [ ] Part 2c: wizard_card_gen.js render new-card highlight + legend
- [ ] Update CLAUDE.md if a documented contract changes

## Phase 5: Verify
- [ ] ruff check . / ruff format .
- [ ] python -c "import mtgai"
- [ ] pytest (esp. any card_gen / tile-shape tests)
- [ ] Manual smoke note for the wizard

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review, fix findings
- [ ] Pull master, merge, cleanup worktree/branch
- [ ] Delete plan + tracker
- [ ] Move card to Done + comment
- [ ] Overview to user
