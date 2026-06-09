# Tracker: fix/clear-stale-decision

Card 6a285a6b — clear_decision never called; stale user decision overrides fresh AI verdict after regen.

## Phase 1: Pick Up
- [x] Claim card (Doing + claim comment, earliest wins)
- [x] Pull master
- [x] Read card
- [x] Worktree + branch + push

## Phase 2: Research
- [ ] Read ai_review.py decisions sidecar (save/load/clear_decision, card_signature)
- [ ] Read server.py _effective_decision merge
- [ ] Find regen archive+replace point (card_gen)
- [ ] Summarize root cause

## Phase 3: Design
- [ ] Staleness contract: record signature on save_decision; _effective_decision ignores/clears stale
- [ ] Wire clear_decision at regen invalidation points
- [ ] Minimal coherent set

## Phase 4: Implement
- [ ] Code changes
- [ ] CLAUDE.md update if contract change

## Phase 5: Verify
- [ ] Regression test (decision v1 vs regen v2; unchanged still applies)
- [ ] ruff check + format
- [ ] smoke import
- [ ] full pytest

## Phase 6: Ship
- [ ] commit + push
- [ ] /review, fix findings
- [ ] pull master, resolve conflicts
- [ ] re-run lint+tests
- [ ] PR + self-merge
- [ ] cleanup worktree/branch
- [ ] delete tracker
- [ ] card to Done + summary comment
