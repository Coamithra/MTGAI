# Tracker: fix/cycle-audit-drop

Card 6a285a7e — Slot dropped from its cycle by the audit is still generated as a CYCLE MEMBER.

## Phase 1: Pick Up
- [x] Claim card (handshake, earliest wins)
- [x] Pull master
- [x] Read card
- [x] Create worktree + branch
- [ ] Push branch

## Phase 2: Research
- [ ] Read card_generator.py generate_set (template stamp ~1143, sibling lookup ~1427, append ~1593)
- [ ] Read prompts.py _cycle_note ~381
- [ ] Read slot_grouper.py (the audit)
- [ ] Trace cycle_id confirmed-vs-seed membership
- [ ] Summarize root cause

## Phase 3: Design
- [ ] Decide mechanism: confirmed cycle membership from audit = single source of truth
- [ ] Keep scope to THIS card; don't conflict with 6a285a83 / 6a285a87

## Phase 4: Implement
- [ ] Stamp/clear confirmed membership after audit
- [ ] Key template stamp, _cycle_note, sibling lookup/append off confirmed membership
- [ ] Regression test

## Phase 5: Verify
- [ ] ruff check . clean
- [ ] ruff format .
- [ ] python -c "import mtgai"
- [ ] full pytest green

## Phase 6: Ship
- [ ] Commit + push
- [ ] /review and fix findings
- [ ] git pull origin master
- [ ] PR + self-merge
- [ ] Cleanup worktree/branch
- [ ] Delete tracker
- [ ] Card to Done + summary comment
