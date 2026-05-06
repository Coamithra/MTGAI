# Tracker: refactor/projectstate-artifact-paths

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked plan)
- [x] Move card to Doing
- [ ] Create worktree and branch

## Phase 2: Research
- [x] Read mtgai/runtime/active_set.py (current state)
- [x] Read mtgai/io/asset_paths.py (set_artifact_dir + helpers)
- [x] Read mtgai/runtime/runtime_state.py (compute_runtime_state)
- [x] Read mtgai/settings/model_settings.py (get_settings, dump/parse_project_toml)
- [x] Read existing tests: test_runtime/test_active_set, test_runtime_state, test_io/test_asset_paths
- [x] Trace callers of set_artifact_dir / set_artifact_dir_if_known across the codebase
- [x] Trace callers of read_active_set / write_active_set / clear_active_set / iter_known_set_codes
- [x] Identify all 409 conversion sites at endpoint level
- [x] Summarize findings (root issues + design risks)

### Findings
- `set_artifact_dir(code)` is called in ~30 places: stage runners, generators, art, rendering, review, server endpoints, runtime_state. All take a set_code arg today, all route via `get_settings(code).asset_folder` → fall back to `output/sets/<CODE>/`.
- `set_artifact_dir_if_known()` has zero call sites in production after the recent merge — safe to delete.
- `iter_known_set_codes()` is used by `cleanup_orphan_running_stages` (engine.py) and `_get_current_state` (server.py) — both walk known sets and call `set_artifact_dir(code)` per code. Plan defers full deletion to commit 3.
- `compute_runtime_state(override)` allows a set_code override — only the test suite uses it; JS calls without args.
- `_per_set_cache` (model_settings) is keyed by set_code. Apply_settings updates it; ProjectState would need to stay coherent.

## Phase 3: Design

**ProjectState shape**: Pydantic BaseModel with `set_code: str`, `settings: ModelSettings`, `mtg_path: Path | None = None`. `arbitrary_types_allowed=True` for the Path field. Mutating settings creates a new ProjectState via `model_copy`.

**Module rename**: `mtgai/runtime/active_set.py` → `active_project.py`. `read_active_set / write_active_set / clear_active_set` stay as shim functions in the renamed module (for callers not updated yet). The validation helpers (`is_valid_set_code`, `normalize_code`, `SET_CODE_RE`), `iter_known_set_codes`, `await_lock_release{,_async}`, and `OUTPUT_ROOT` / `SETS_ROOT` constants stay.

**asset_paths.py**:
- Add `class NoAssetFolderError(RuntimeError)`.
- `set_artifact_dir()` — no arg. Reads active project. Raises `NoAssetFolderError` when no project is open or `asset_folder` is empty.
- Delete `set_artifact_dir_if_known()`.
- `OUTPUT_ROOT`, `SETS_ROOT` stay (referenced by tests + cleanup walk).

**Call site updates**: every `set_artifact_dir(set_code)` → `set_artifact_dir()`. ~30 sites; mechanical change. Stage runners and endpoints still take their `set_code` first param (deletion is commit 2).

**409 conversion at endpoints**: helper `_artifact_dir_or_409()` returning `(Path | None, JSONResponse | None)`. Wizard endpoints that touch `set_artifact_dir()` use it.

**Cleanup helpers** (`cleanup_orphan_running_stages`, `_get_current_state`): rewire to walk `SETS_ROOT` directly with inline `code → SETS_ROOT/code/pipeline-state.json`. Don't go through `set_artifact_dir`. Save back inline (don't use `save_state`).

**runtime_state.py**:
- `compute_runtime_state` reads `read_active_project()`.
- `_load_theme` / `_load_pipeline_summary` catch `NoAssetFolderError`; return None.
- `set_code_override` becomes test-only; for tests, the path is now: write_active_project first, then call.

**Settings sync (apply_settings)**: when applying for the active project's set_code, also rebuild the active ProjectState so `_active_project.settings` stays current. Lazy-import `active_project` to avoid cycles.

**Tests**:
- New `tests/test_runtime/test_active_project.py` — ProjectState construction, read/write/clear, mtg_path round-trip, settings access.
- `test_active_set.py` mostly stays (shims still pass).
- `test_asset_paths.py` rewrites — uses ProjectState fixture instead of legacy fallback.
- `test_runtime_state.py` — drops set_code override usage; uses write_active_project + tmp asset_folder.
- `test_engine_cleanup.py` — should keep working since cleanup goes inline now (already writes to SETS_ROOT/<code>).
- Other tests adjusted as needed.

- [x] Draft the ProjectState shape (settings + .mtg path; mutability semantics)
- [x] Decide rename: active_set.py → active_project.py (or similar)
- [x] Decide which functions stay as shims (read_active_set returning project.set_code)
- [x] Decide where the "raises if no asset_folder" exception lives + 409 conversion pattern
- [x] Plan the test additions/updates (ProjectState tests + active_set test updates)
- [ ] Align with the user on the design (auto-mode: proceed with reasonable assumptions)

## Phase 4: Implement
- [x] Rename active_set.py → active_project.py with ProjectState class
- [x] Update set_artifact_dir() to read from active project; delete set_artifact_dir_if_known()
- [x] Update compute_runtime_state to read from active project
- [x] Update import sites that referenced removed symbols
- [x] Convert callers' "no asset_folder" failures into 409 at endpoint level
- [x] Add ProjectState tests
- [x] Update existing active_set tests

## Phase 5: Verify
- [x] ruff check . (no new issues vs master — 48 pre-existing errors, all in untouched files)
- [x] ruff format . (no new issues vs master — 18 pre-existing in untouched files)
- [x] python -c "import mtgai" (smoke clean)
- [x] pytest (1013 passed; 8 pre-existing failures in test_review/test_server.py against legacy routes — same as master; test_config.py pre-existing import error — same as master)
- [ ] Manual: python -m mtgai.review serve --open — verify wizard project flow works
- [x] Spot-check the diff
- [ ] Flag anything needing manual testing

## Phase 6: Review & Ship
- [x] Commit with descriptive message
- [ ] Push branch
- [ ] /review (fix every finding before proceeding)
- [ ] git pull origin master into branch (resolve conflicts per rules)
- [ ] Re-run lint + tests after merge
- [ ] Return to root checkout
- [ ] Merge to master + push
- [ ] Clean up worktree + branch
- [ ] Delete tracker (the plan stays — there are 2 more commits)
- [ ] Move card to Done
- [ ] Comment on card with summary
- [ ] Create follow-up cards if any out-of-scope issues surfaced
- [ ] Final overview to user
