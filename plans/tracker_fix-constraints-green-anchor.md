# Tracker: fix/constraints-green-anchor (card 6a2976ad)

## Phase 1: Pick Up the Card
- [x] Claim card (moved to Doing, claim comment 90db4d89, earliest claim confirmed)
- [x] Pull latest master
- [x] Read the card
- [x] Create worktree + branch, push upstream

## Phase 2: Research
- [x] Verify how constraints_system.txt is loaded (theme_extractor._SECTION_SPECS -> _run_json_subcall read_text; no templating)
- [x] Confirm no sibling constraints prompt (card_suggestions_system.txt is a different pass)

## Phase 3: Design
- [x] Neutralize the green color-pie example (no color, no specific shift)
- [x] Add anti-anchoring instruction (examples illustrative only; omit categories that don't apply)
- [x] Review other example lines for anchoring risk (kept: they only fire on genuinely matching settings; instruction covers residual risk)

## Phase 4: Implement
- [x] Edit constraints_system.txt

## Phase 5: Verify
- [x] ruff check . clean (+ format check)
- [x] pytest clean (2615 passed)
- [x] Prompt file loads via the extractor's path (_SECTION_SPECS -> _PROMPTS_DIR read; content asserted)

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review, fix findings
- [ ] Pull master into branch, re-verify
- [ ] PR + self-merge, fast-forward root master
- [ ] Clean up worktree + branch + tracker
- [ ] Move card to Done + comment PR link
