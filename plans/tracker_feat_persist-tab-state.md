# Tracker: feat/persist-tab-state

Card: [Persist tab state across navigation + browser restarts (hybrid model)](https://trello.com/c/omM01Egs) (id `69f88272`)

## Phase 1: Pick Up
- [x] Pull latest master
- [x] Read card description
- [x] Move card to Doing
- [x] Create worktree feat/persist-tab-state
- [x] Create tracker

## Phase 2: Research
- [x] Read pipeline server (FastAPI routes, SSE event bus)
- [x] Read theme wizard front-end (extract-stream consumer, state)
- [x] Read pipeline dashboard front-end (events stream)
- [x] Read configure page + review pages (filter / scroll state today)
- [x] Read base.html status banner (already polls /api/ai/status)
- [x] Read ai_lock.busy_payload + theme_extractor.is_running shim
- [x] Note all existing UI state and where it lives today
- [x] Sketch /api/runtime/state shape

## Phase 3: Design
- [x] Write plans/feat-persist-tab-state.md
- [x] Define endpoint shape + localStorage key conventions
- [x] Define SSE reattach contract (broadcast buffer + replay)
- [x] List file-by-file changes

## Phase 4: Implement
- [x] /api/runtime/state endpoint
- [x] /api/pipeline/theme/load endpoint
- [x] Theme wizard hydration + SSE reattach
- [x] Pipeline dashboard hydration (already worked via template + EventSource)
- [x] Configure page localStorage ephemera
- [x] Review pages localStorage ephemera (filters + sort + decisions + scroll)

## Phase 5: Verify
- [x] ruff check (new files clean; pre-existing issues unchanged)
- [x] ruff format (no changes needed)
- [x] python -c "import mtgai" — clean
- [x] pytest — 49 runtime tests pass; 773 total pass
- [x] Update CLAUDE.md with new endpoint contract + module
- [ ] Manual smoke: tab switch, reload, browser close+reopen, mid-extraction reattach (do before commit)

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review and fix findings
- [ ] Pull master, resolve any conflicts
- [ ] Re-run lint + tests
- [ ] Merge to master
- [ ] Clean up worktree + branch
- [ ] Delete plan + tracker files
- [ ] Move card to Done
- [ ] Comment on card with summary
- [ ] Final overview message to user
