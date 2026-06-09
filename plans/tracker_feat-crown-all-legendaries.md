# Tracker: feat/crown-all-legendaries

Card 6a2881cd — Frame polish, step 1: Crown all legendary permanents, not just creatures

## Phase 1: Pick Up the Card
- [x] Claim the card (two-phase handshake — claim c916ca87, only claimant)
- [x] Pull latest master
- [x] Read the card
- [x] Create worktree and branch

## Phase 2: Research
- [ ] Read card_renderer.py crown gate + _load_legendary_crown
- [ ] Confirm crown assets cover artifact/land/gold/pairs
- [ ] Check existing crown tests

## Phase 3: Design
- [ ] Trivial — drop the `and creature` clause; no plan doc needed (card IS the plan)

## Phase 4: Implement
- [ ] Drop the creature gate in render_card
- [ ] Tests: legendary artifact + legendary enchantment get crown; non-legendary unaffected

## Phase 5: Verify
- [ ] ruff check + format
- [ ] pytest
- [ ] Eyeball one rendered legendary non-creature PNG

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review, fix findings
- [ ] Pull master, re-test
- [ ] PR + self-merge
- [ ] Clean up worktree/branch, delete tracker
- [ ] Move card to Done + summary comment
