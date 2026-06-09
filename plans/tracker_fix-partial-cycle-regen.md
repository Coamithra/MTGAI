# Tracker: fix/partial-cycle-regen (card 6a286120)

## Phase 1: Pick Up the Card
- [x] Claim card 6a286120 (two-phase handshake, claim af7c9682 — won)
- [x] Pull latest master
- [x] Read the card
- [x] Create worktree .trees/fix-partial-cycle-regen + branch fix/partial-cycle-regen

## Phase 2: Research
- [x] Read card_generator.py (generate_set, reconcile_cycle_membership, regen path, sibling threading)
- [x] Read slot_grouper.py (find_cycle_families)
- [x] Read prompts.py (_cycle_note, format_slot_specs, sibling context)
- [x] Read commit 089751a (6a285a7e dropped-slot guarantee) and check 6a285a87 status
- [x] Summarize root cause

## Phase 3: Design
- [x] Decide approach (full-skeleton-aware audit/reconciliation; filled siblings as context)
- [x] Check non-regression: (a) dropped-slot guarantee, (b) first-run behaviour, (c) batching

## Phase 4: Implement
- [x] Code changes
- [x] Update CLAUDE.md if contract changes

## Phase 5: Verify
- [x] ruff check . / ruff format .
- [x] python -c "import mtgai"
- [x] pytest (full suite)
- [x] New unit tests for partial-cycle regen path
- [x] Spot-check diff

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review and fix findings
- [ ] Pull master, re-test
- [ ] PR create + merge, fast-forward master
- [ ] Clean up worktree + branch
- [ ] Delete tracker doc
- [ ] Move card to Done + summary comment
- [ ] Follow-up cards if needed
