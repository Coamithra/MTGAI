# Tracker: feat/finalization-ui

Card 6a209cc7 "Finalization UI" — fully featured editing UI for the `finalize` stage.

## Phase 1: Pick Up
- [x] Pull latest master
- [x] Read the card + CONTRIBUTING + wizard-tab-conventions + finalize.py
- [x] Move card to Doing
- [x] Create worktree + branch, push

## Phase 2: Research
- [x] Read finalize.py (backend stage)
- [x] Read STAGE_DEFINITIONS / break-point / engine pause logic
- [x] Read card model + card_io + card_tile_dict + card_gen state/save endpoints
- [x] Read wizard_finalize.js scaffold + human_card_review scaffold
- [x] Confirm symbol tokens stored as {T}/{W} in oracle_text; no FE symbol renderer yet

## Phase 3: Design
- [x] Write plan

## Phase 4: Implement
- [ ] Backend: finalize_set captures original_oracle_text per modified card
- [ ] Backend: GET /api/wizard/finalize/state — cards (full editable fields) + finalize report
- [ ] Backend: POST /api/wizard/finalize/save-card — persist a manual per-card edit
- [ ] Backend: POST /api/wizard/finalize/save — bulk save + heal + nav (Save & Continue)
- [ ] Backend: finalize review_eligible stays metadata; break-point already wired
- [ ] Frontend: rewrite wizard_finalize.js — full card grid, edit-any-field, edited badges, symbol helper, footer advance
- [ ] CSS additions if needed (reuse shared tile/locked classes)
- [ ] Docs: update CLAUDE.md / wizard-tab-conventions.md if new pattern

## Phase 5: Verify
- [ ] ruff check . / ruff format .
- [ ] python -c "import mtgai"
- [ ] pytest
- [ ] Manual smoke: serve, walk finalize tab (render, edit persist, stop/continue)

## Phase 6: Ship
- [ ] Commit + push
- [ ] /review, fix findings
- [ ] pull master, resolve conflicts, re-verify
- [ ] merge to master, push
- [ ] cleanup worktree/branch
- [ ] delete plan + tracker
- [ ] card to Done + comment
