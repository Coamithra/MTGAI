# Tracker: feat/resource-economy

## Phase 1: Pick Up the Card
- [x] Claim card 6a29d07d (two-phase handshake)
- [x] Pull latest master
- [x] Read the card
- [x] Create worktree and branch

## Phase 2: Research
- [ ] Read duplicates.py + gate_common.py + conformance.py
- [ ] Read stages.run_conformance integration
- [ ] Read wizard_conformance.js (tab JS) step rendering
- [ ] Read mechanics/approved.json reminder text shape
- [ ] Eyeball MLP cards for oracle shapes (read-only)

## Phase 3: Design
- [ ] Write plans/resource-economy.md

## Phase 4: Implement
- [ ] mtgai/analysis/resource_economy.py
- [ ] Integrate into stages.run_conformance (third step)
- [ ] Tab JS rendering
- [ ] Tests
- [ ] Update CLAUDE.md

## Phase 5: Verify
- [ ] ruff check . / ruff format .
- [ ] python -c "import mtgai"
- [ ] pytest

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review + fix findings
- [ ] Pull master, re-lint/test
- [ ] PR + self-merge
- [ ] Clean up worktree, delete tracker/plan
- [ ] Move card to Done + comment
