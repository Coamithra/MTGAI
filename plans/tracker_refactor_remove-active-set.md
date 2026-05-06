# Tracker: refactor/remove-active-set

Phase 3 of the .mtg project-file refactor. Trello card 69fa8e48.

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read card 69fa8e48 (description) and the Phase 1/2 commits (0a26baa, a3ab4ab)
- [x] Move Phase 2 card to Done with shipping comment
- [x] Move Phase 3 card to Doing
- [x] Create worktree `.trees/refactor/remove-active-set` and push branch

## Phase 2: Research (audit) — DONE

Key findings:
- **`set_picker.js` is already dead code.** No template provides a `#set-picker` slot. The only references are inside `set_picker.js` itself + a stale comment in `style.css:154`. Removing the file is a no-op for runtime, but hygiene-positive.
- **`MtgaiState.activateSet` and `MtgaiState.createSet` in `ui_state.js` are only called from `set_picker.js`.** Once the picker is gone, these methods are dead.
- **The wizard already drives via in-memory `state.activeSet` in `wizard_project.js`.** Most endpoints accept `set_code` as a body/query param and the wizard uses that on every call. The few server-side `read_active_set()` fallbacks happen on the wizard shell render path (`/pipeline/<tab_id>`) and on `/api/wizard/project` (no-arg).
- **`active_set.py` exports more than the card lists.** Beyond the listed removals, it also has `iter_known_set_codes()`, `is_valid_set_code()`, `normalize_code()`, `SET_CODE_RE` — all genuinely needed elsewhere (engine cleanup, project registry walk, .mtg endpoints). They survive.
- **`output/sets/<CODE>/settings.toml` stays as the project registry.** Per Phase 2's commit msg, that file IS the registry. So `output/sets/<CODE>/` directory is NOT going away — only the active-set persistence layer (`output/settings/last_set.toml`) is.

Decision points:
- **Server-side active-project state mechanism after Phase 3:** in-memory module-level variable in `runtime/active_set.py` (replaces the on-disk `last_set.toml`). Set by `/api/project/{open,materialize}`, cleared by `/api/project/new`. Survives page reload, lost on server restart (matches the "fresh boot greets user with New / Open" requirement). No disk persistence ⇒ no `last_set.toml` ⇒ no lifespan unlink.
- **`set_code` stays as project metadata** (collector_number prefixes, `card.set_code`, file naming all use it). `SET_CODE_RE` stays.

## Phase 3: Design — file-by-file

### Lifecycle / cancellation

How the in-memory pointer interacts with in-flight AI work. The mutex (`mtgai/runtime/ai_lock.py`) already exposes `is_running()`, `request_cancel()`, `is_cancelled()`, `current_action()`, `busy_payload()` — we reuse those, no new primitives needed.

| Trigger | Pointer | AI work | UX |
|---|---|---|---|
| F5 / page reload | Survives (process memory) | Continues; SSE re-attaches via existing broadcast pattern | Same project re-renders; run stream resumes |
| Tab close, browser exit | Survives | Continues | Next tab landing on `/pipeline/<tab>` re-attaches |
| Server restart | Cleared (process death) | Killed with process | Boot greets user with New/Open |
| `/api/project/new` while AI running | Would clear under naive impl | Orphaned | **See below** |
| `/api/project/open` while AI running (different project) | Would swap under naive impl | Orphaned | **See below** |
| `/api/project/materialize` | Sets pointer to current draft's `set_code` | In practice never overlaps with AI | Defensive guard, same shape as below |

**Server contract for `/api/project/{new,open,materialize}` when `ai_lock.is_running()`:**

1. At the top of each handler, check `ai_lock.is_running()`.
2. If running and the request body did NOT include `"force": true`: return **409** with `ai_lock.busy_payload()` (`running_action`, `started_at`, `log_path`) so the client can render a confirmation modal naming what it would interrupt. No mutation happens on this path.
3. If running and `force=true`: call `ai_lock.request_cancel()`, then poll `ai_lock.is_running()` every 100 ms up to a 5 s deadline. On release, proceed with the pointer mutation as normal. On timeout, log a warning and proceed anyway — `request_cancel` has been signalled, the run will wind down; we don't block the user forever. (The new project's settings will load fine; the dying run can't write to the wrong project because each stage runner resolves `set_code` once at the top and doesn't re-read the pointer mid-run.)

**Helper**: extract the wait-for-release loop into a small `active_set._await_lock_release(deadline_s: float = 5.0) -> bool` (returns True if released cleanly, False on timeout) so all three handlers share it. Keep it in `active_set.py` since it's part of the project-switch lifecycle.

**Client flow** (`wizard.js` File menu):

- File → New / File → Open POST without `force` first.
- On 409: render a confirmation modal — "<running_action> is in progress. Cancel it and switch projects?" — using `running_action` from the response. On confirm, retry the POST with `force: true`. On dismiss, abort the navigation.
- On 200: navigate as today.

**`/api/project/materialize`** is only invoked from the kickoff "Save & Start" flow on a fresh draft, before any AI is running, so the guard is defensive — the 409+modal path will essentially never fire there. Including it keeps the three endpoints symmetric.

### Backend

**`mtgai/runtime/active_set.py`** — slim it down significantly:
- KEEP: `SET_CODE_RE`, `is_valid_set_code`, `normalize_code`, `iter_known_set_codes`, `read_active_set`, `write_active_set`. Re-export `SETS_ROOT` for callers that import it.
- CHANGE: `read_active_set` reads a module-level `_active_code: str | None`. `write_active_set` sets it. Add `clear_active_set()` for the `New` flow. No `tomllib`, no `tempfile`, no `os.replace`, no `_LAST_SET_PATH`.
- ADD: `await_lock_release(deadline_s: float = 5.0) -> bool` — small helper that polls `ai_lock.is_running()` every 100 ms up to the deadline, returns True on release, False on timeout. Used by the project-switch lifecycle. (Lives here rather than in `ai_lock.py` because the polling pattern is specific to the project-switch flow; `ai_lock` stays a generic mutex.)
- REMOVE: `_SETTINGS_DIR`, `_LAST_SET_PATH`, `list_sets`, `_read_theme_name`, `create_set`, `_force_remove`, `delete_set`. Imports of `json`, `os`, `shutil`, `stat`, `tempfile`, `tomllib`, `contextlib` go away.
- Module docstring rewrites — describe in-memory active-project, lifecycle (set on Open/Materialize, cleared on New, lost on restart), and that this is NOT persisted.

**`mtgai/runtime/runtime_state.py`**:
- `compute_runtime_state`: drop `available_sets` from response.
- `_resolve_active_set_code`: simplify — `override` → `read_active_set()` (now in-memory) → None. (Same flow, but `read_active_set` is cheaper.)

**`mtgai/pipeline/server.py`**:
- DELETE handlers: `set_active_set` (POST `/api/runtime/active-set`), `create_set_endpoint` (POST `/api/runtime/sets`), `delete_set_endpoint` (POST `/api/runtime/sets/delete`).
- DELETE the `_SET_CODE_RE = re.compile(...)` redefinition near the top (line ~50). Use `active_set.SET_CODE_RE` everywhere it's needed.
- `/api/project/new`: replace the `_LAST_SET_PATH.unlink(missing_ok=True)` with `active_set.clear_active_set()`. Remove the `import contextlib` it currently does just for that suppress. **Add the lifecycle guard**: at top of handler, if `ai_lock.is_running()` and `body.get("force") is not True`, return 409 with `ai_lock.busy_payload()`. If forced, call `ai_lock.request_cancel()` + `active_set.await_lock_release()` before clearing the pointer. The handler currently doesn't take a body — change signature to `async def project_new(request: Request)` and parse-or-empty the JSON body.
- `/api/project/open` + `/api/project/materialize`: same lifecycle guard at top — `is_running()` + `force` check → 409 / cancel-and-wait. Then keep the `active_set.write_active_set(set_code)` call as today (now in-memory).
- `/api/project/serialize` + `_theme_extract_model_key` + `wizard_project_payload`: their `active_set.read_active_set()` calls keep working (in-memory now). No lifecycle guard — they're read-only.

**`mtgai/review/server.py`**:
- Lifespan `_lifespan`: drop the `from mtgai.runtime.active_set import _LAST_SET_PATH` + `_LAST_SET_PATH.unlink(missing_ok=True)` block. Optionally call `active_set.clear_active_set()` to be explicit, but a fresh process already has `None` so this is redundant. Drop the `contextlib.suppress` + import. Update the lifespan docstring.
- `_get_set_code` helper: keep — it's a thin pass-through to `resolve_active_set_code()`. It's used by `/api/cards` and `/api/settings/apply` as a fallback.
- `_set_dir` helper: keep — already routes through `set_artifact_dir()`.

### Frontend

**`backend/mtgai/gallery/templates/static/wizard.js`** (File menu — lifecycle):
- Locate the File → New / File → Open POST sites. Wrap each in a small helper `postProjectAction(url, body)` that:
  1. POSTs `body` (no `force` field).
  2. If response is 409 with a `running_action` field, render a confirm modal — "<running_action> is in progress. Cancel it and continue?". On confirm, retry POST with `{...body, force: true}`. On dismiss, return without navigating.
  3. On 2xx, return the response so the caller can navigate.
- Re-use the existing busy-toast / modal styling rather than introducing a new component (the wizard already renders busy banners on 409 from other guarded endpoints — match that look).

**`backend/mtgai/gallery/templates/static/set_picker.js`**: DELETE entire file (already not loaded).

**`backend/mtgai/gallery/templates/static/ui_state.js`**:
- Drop `activateSet`, `createSet` functions and exports.
- `setCode()` currently defaults to `'ASD'` when no value in localStorage — change to return empty string. The wizard hydrates `state.activeSet` from `/api/runtime/state.active_set` on mount; `MtgaiState.setCode()` is only used by `configure.js` and shouldn't be hardcoding 'ASD' as a fallback.
- Drop the `mtgai:active_set` localStorage key. The wizard's in-memory state.activeSet is already the source of truth post-mount; localStorage was for the dead picker. (Per-set keys like `mtgai:<setCode>:configure.preset` survive.)

**`backend/mtgai/gallery/templates/static/configure.js`**:
- Lines 24-29 sync `state.active_set` to UI element. Keep — `state.active_set` from `/api/runtime/state` still exists post-Phase-3.
- Line 196: `MtgaiState.setCode()` — replace with `await MtgaiState.fetchRuntimeState()` (already done at line 24, can be threaded through).

**`backend/mtgai/gallery/templates/static/style.css`**:
- Drop the `.set-picker*` rules (the audit notes they exist around line 154). Drop the comment about `set_picker.js`.

### Tests

**`backend/tests/test_runtime/test_active_set.py`**:
- Keep tests for `is_valid_set_code`, `normalize_code`, `iter_known_set_codes`, basic `read_active_set` / `write_active_set` round-trip, and the `clear_active_set` helper.
- Add tests for `await_lock_release`: returns True when lock is never held, returns True when a held lock releases before the deadline, returns False on timeout. (Use a thread that holds the lock for a known duration, or directly manipulate `ai_lock._current` via `reset_for_tests` + a manual acquire.)
- Delete tests for `list_sets`, `create_set`, `delete_set`, `_LAST_SET_PATH` filesystem semantics, atomic-write behaviour.

**`backend/tests/test_runtime/test_endpoints.py`**:
- Delete `test_runtime_state_includes_available_sets` and the 3 endpoint tests (`test_active_set_post_*`, `test_create_set_post_*`, `test_runtime_sets_delete_*` if present). Update `test_runtime_state_idle` to drop the `available_sets` assertion.

**`backend/tests/test_runtime/test_runtime_state.py`**:
- Drop tests that depend on `_LAST_SET_PATH` filesystem reads/writes; keep tests that assert in-memory pointer behaviour.

**`backend/tests/test_pipeline/test_project_file.py`**:
- The 4 references to `read_active_set`/`write_active_set` (lines 30,123,150,206) keep working — same API, in-memory now.
- ADD lifecycle tests for each of `/api/project/{new,open,materialize}`:
  - Idle (no AI running) → 200, pointer mutates as expected.
  - AI running, no `force` → 409 with `running`/`running_action` in body, pointer unchanged.
  - AI running, `force=true` → cancel signalled, pointer mutates after lock releases. Use a fixture that holds the lock briefly in a background thread to simulate.
  - AI running, `force=true`, lock held past deadline → handler still returns 200 with a logged warning, pointer mutates anyway. (Patch `await_lock_release` to return False, or set deadline to a very small value.)

**`backend/tests/conftest.py`** (`isolated_output` fixture):
- Drop the `_LAST_SET_PATH` monkeypatch (no longer exists). Add a `clear_active_set()` call so each test starts with no active project. Keep all other patches.

**Wizard test fixtures (`test_wizard_*.py`)**:
- Drop `_LAST_SET_PATH` monkeypatch lines. Use `active_set.write_active_set(code)` directly to seed the in-memory pointer where tests need an active project.

### Docs

**`CLAUDE.md`** (project root):
- Update "Cross-cutting" → "Active set" bullet: rewrite to describe the file-as-project model. The picker is gone; the open `.mtg` defines the project; the server holds an in-memory pointer that's lost on restart.
- The architecture overview line about `mtgai/runtime/` mentions "active-set persistence" — change to "active-project pointer (in-memory)".

## Phase 4: Implement (in order)

1. [x] Slim down `mtgai/runtime/active_set.py` (in-memory pointer, drop `list_sets`/`create_set`/`delete_set`, add `clear_active_set`, add `await_lock_release` helper)
2. [x] Drop `available_sets` from `compute_runtime_state`
3. [x] Delete `/api/runtime/active-set`, `/api/runtime/sets`, `/api/runtime/sets/delete` handlers in `pipeline/server.py`
4. [x] Update `/api/project/new` to use `clear_active_set()` (drop `_LAST_SET_PATH.unlink`); add lifecycle guard (`is_running` → 409 / `force=true` → cancel + await release)
5. [x] Add the same lifecycle guard to `/api/project/open` and `/api/project/materialize`
6. [x] Drop `_SET_CODE_RE` duplicate in `pipeline/server.py`; use `active_set.SET_CODE_RE`
7. [x] Strip `_LAST_SET_PATH.unlink` from `review/server.py` lifespan; rewrite docstring
8. [x] Wire client-side File → New / Open through `postProjectAction()` helper in `wizard_project.js` (handle 409 → confirm modal → retry with `force=true`)
9. [x] Delete `static/set_picker.js`
10. [x] Trim `static/ui_state.js` (drop activateSet, createSet, ACTIVE_SET_KEY default to ''); update consumers
11. [x] Drop `.set-picker*` CSS rules and the stale comment
12. [x] Trim test suites per the design above (incl. new lifecycle tests for `/api/project/*` and `await_lock_release` unit tests)
13. [x] Update CLAUDE.md "Cross-cutting" Active-set bullet + the architecture overview line (mention the in-memory pointer + project-switch lifecycle)

## Phase 5: Verify

- [x] `ruff check .` — clean for files we touched (pre-existing failures elsewhere unchanged)
- [x] `ruff format .` — applied to `review/server.py` + `test_wizard_advance.py`
- [x] `python -c "import mtgai"` clean (full `from mtgai.runtime import active_set, runtime_state, ai_lock; from mtgai.review import server; from mtgai.pipeline import server as ps` succeeds)
- [x] `pytest` — 1020 pass / 8 fail, all 8 failures pre-existing on master (legacy `/review` redirect tests for the removed standalone page); the 100 runtime + project-file tests and 63 wizard tests touched by this card all pass.
- [ ] Smoke: `python -m mtgai.review serve --open` — wizard greets with New/Open, no top-bar picker, basic flow works (open ASD .mtg, navigate tabs, settings page loads)
- [ ] Smoke: project-switch-while-busy lifecycle — kick off theme extraction on one project, click File → Open with a different `.mtg` mid-run; confirm the modal appears with the running action's name; confirm cancel + open succeeds; confirm the SSE stream stops cleanly. Same exercise for File → New.
- [ ] Smoke: F5 mid-run — run does not cancel, broadcast SSE re-attaches on reload, project pointer survives.

## Phase 6: Review & Ship

- [ ] Commit + push
- [ ] `/review` — fix every finding
- [ ] `git pull origin master` and resolve conflicts
- [ ] Re-run lint + pytest after merge
- [ ] Merge to master and push
- [ ] Clean up worktree + branch
- [ ] Delete tracker file
- [ ] Move Trello card to Done with shipping comment
- [ ] Final overview to user
