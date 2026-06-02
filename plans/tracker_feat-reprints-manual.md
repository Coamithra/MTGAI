# Tracker: feat/reprints-manual

Card: [Reprints tab: manual select + place reprints](https://trello.com/c/rQZ20z02) (`6a17151a`)

## Phase 1: Pick Up
- [x] Pull latest master
- [x] Read the card + touch points
- [x] Move card to Doing
- [x] Create worktree + branch + push

## Phase 2: Research
- [x] Read `reprint_selector.py` (select/place passes, apply_selection_to_skeleton, knobs)
- [x] Read `wizard_reprints.js` (read-only grid + knob panel + Refresh)
- [x] Read reprints endpoints in `server.py` (state/knobs/refresh)
- [x] Read archetypes tab + endpoints (preserve-on-refresh contract to mirror)
- [x] Read wizard-tab-conventions.md (§5 provenance, §6 cascade, §15 heal, §17 helpers)
- [x] Inspect reprint_pool.json shape (227 cards)

## Phase 3: Design
- [x] Write plan doc (`plans/reprints-manual-select.md`)
- [x] Align with user — get approval

## Phase 4: Implement
- [x] `reprint_selector.py`: add `pinned` field to `SelectionPair`; thread `pinned=` through `select_reprints`
- [x] `server.py`: `_resolve_selection_pairs` helper (rebuild from pool+skeleton, validate)
- [x] `server.py`: `GET /api/wizard/reprints/pool` (full pool + open slots)
- [x] `server.py`: `POST /api/wizard/reprints/save` (manual write, no AI, stamp + heal)
- [x] `server.py`: `/refresh` accepts `pinned` → preserve on re-roll
- [x] `wizard_reprints.js`: editable grid (slot reassign, pin, remove), pool browser, save footer
- [x] CLAUDE.md: update reprints stage doc if contract changes

## Phase 5: Verify
- [x] `ruff check .` + `ruff format .`
- [x] `python -c "import mtgai"`
- [x] `pytest` (esp. any reprint tests)
- [ ] Manual smoke via `python -m mtgai.review serve --open`

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] `/review`
- [ ] Pull master, resolve conflicts
- [ ] Re-run lint + tests
- [ ] Merge to master, clean worktree/branch
- [ ] Delete plan + tracker
- [ ] Move card to Done + comment
- [ ] Final overview
