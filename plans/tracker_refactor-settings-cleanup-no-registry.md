# Tracker: refactor/settings-cleanup-no-registry

Card: [Refactor 3: settings cleanup + delete registry](https://trello.com/c/K6ZdG44V) (id 69fb66ed)
Plan: `plans/refactor_set-code-decoupling.md` (commit 3 section)

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked plan)
- [x] Move card to Doing
- [x] Create worktree and branch

## Phase 2: Research
- [x] Audit current state of `mtgai/settings/model_settings.py`: `get_settings`, `_per_set_cache`, `_seed_per_set_settings`, `_SETS_DIR`/`_SETS_ROOT`
- [x] Audit `mtgai/runtime/active_project.py`: `iter_known_set_codes`, `is_valid_set_code`, `normalize_code`, regex
- [x] Audit `mtgai/pipeline/engine.py::cleanup_orphan_running_stages` — confirm whether it can operate on active project alone
- [x] Find all callers of `get_settings(...)`, `iter_known_set_codes`, `normalize_code`, `_seed_per_set_settings`
- [x] Audit legacy CLI scripts (`art/kontext_sample.py`, `kontext_ab_test.py`, `pulid_test.py`, `scripts/generate_all_art.py`)
- [x] Audit tests that exercise the registry / per-set cache

## Phase 3: Design
- [x] Map each registry/legacy symbol to its replacement (delete vs rename vs rewire)
- [x] Decide fate of legacy CLI scripts (update vs deprecate stub vs delete) — port to `--mtg <path>` arg via `cli_shim.activate_from_mtg`
- [x] Confirm no public surface still expects the old API

## Phase 4: Implement
- [x] Rename `get_settings(set_code)` → `get_active_settings()` and update callers
- [x] Delete `_per_set_cache` and `_seed_per_set_settings()`
- [x] Delete `_SETS_DIR` / `_SETS_ROOT` constants from `model_settings.py`
- [x] Delete `iter_known_set_codes()` and update `cleanup_orphan_running_stages()`
- [x] Relax `is_valid_set_code` regex (free-form string); remove `normalize_code` if unused
- [x] Update legacy CLI scripts (renderer + art + skeleton revisor) to take `--mtg <path>`
- [x] Test cleanup: drop registry tests, update fixtures to use ProjectState directly

## Phase 5: Verify
- [x] `ruff check .` and `ruff format .` clean from `backend/` (zero new warnings vs master)
- [x] `python -c "import mtgai"` smoke
- [x] `pytest` from `backend/` — 994 pass, 8 pre-existing failures

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] `/review`; address findings
- [ ] Pull master, resolve conflicts, re-run lint + tests
- [ ] Merge to master + push
- [ ] Cleanup worktree + branch
- [ ] Delete plan + tracker (last commit on master if applicable)
- [ ] Move card to Done + comment summary
- [ ] Open follow-up cards if any (also close 69fb72a7 as duplicate)
