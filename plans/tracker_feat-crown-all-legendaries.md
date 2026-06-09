# Tracker: feat/crown-all-legendaries

Card 6a2881cd — Frame polish, step 1: Crown all legendary permanents, not just creatures

## Phase 1: Pick Up the Card
- [x] Claim the card (two-phase handshake — claim c916ca87, only claimant)
- [x] Pull latest master
- [x] Read the card
- [x] Create worktree and branch

## Phase 2: Research
- [x] Read card_renderer.py crown gate + _load_legendary_crown
- [x] Confirm crown assets cover artifact/land/gold/pairs
- [x] Check existing crown tests

## Phase 3: Design
- [x] Trivial — drop the `and creature` clause; no plan doc needed (card IS the plan)

## Phase 4: Implement
- [x] Drop the creature gate in render_card (planeswalkers stay crownless per real frames)
- [x] Tests: legendary artifact/enchantment/land/sorcery get crown; creature keeps it;
      planeswalker excluded; non-legendary stable

## Phase 5: Verify
- [x] ruff check + format
- [x] pytest (full suite green; red-test check confirmed old gate fails new cases)
- [x] Eyeball rendered legendary artifact + enchantment PNGs

## Phase 6: Review & Ship
- [x] Commit + push
- [x] /review, fix findings (planeswalker exclusion + boundary tests; tracker ticked)
- [ ] Pull master, re-test
- [ ] PR + self-merge
- [ ] Clean up worktree/branch, delete tracker
- [ ] Move card to Done + summary comment
