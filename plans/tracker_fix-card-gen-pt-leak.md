# Tracker: fix/card-gen-pt-leak

Card 6a26d933 — card_gen creatures emit P/T into oracle_text; rules_text.line_period fixer cements it; some saved with null power/toughness

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments)
- [x] Move card to Doing
- [x] Create worktree and branch

## Phase 2: Research
- [ ] Read rules_text.line_period fixer
- [ ] Read type_check validator (creature_missing_pt)
- [ ] Read validation runner / cascade
- [ ] Trace card_gen save + retry logic
- [ ] Summarize root cause

## Phase 3: Design
- [ ] Draft approach (defect A + defect B)
- [ ] Align with user

## Phase 4: Implement
- [ ] Fixer: detect bare N/N oracle line -> move to power/toughness
- [ ] line_period: skip bare N/N P/T-looking line
- [ ] Ensure creature_missing_pt triggers retry/flag
- [ ] Update CLAUDE.md if needed

## Phase 5: Verify
- [ ] ruff check / format
- [ ] smoke import
- [ ] pytest
- [ ] spot-check diff

## Phase 6: Ship
- [ ] Commit + push
- [ ] /review
- [ ] pull master, merge
- [ ] PR + self-merge
- [ ] cleanup worktree
- [ ] delete tracker
- [ ] card -> Done + comment
