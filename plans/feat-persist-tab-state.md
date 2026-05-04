# Plan: Persist tab state across navigation + browser restarts

Trello: [omM01Egs](https://trello.com/c/omM01Egs)

## Context

Today, switching tabs throws away client-side state. Closing and reopening the browser also resets everything. AI runs (e.g. theme extraction) keep running on the server but the browser drops the SSE stream — and worse, the current `extract-stream` cancels the run on disconnect (`request_cancel()` in `request.is_disconnected()` branch). So tab-switching mid-extraction kills the run.

We want a hybrid model: server is source of truth for run state + extracted artifacts; browser localStorage holds purely-UI ephemera keyed by set code.

## Findings (from research)

Key files inspected:
- `mtgai/runtime/ai_lock.py` — app-wide mutex, `busy_payload()` returns `{running, running_action, started_at, log_path}`. **Reusable as-is.**
- `mtgai/pipeline/server.py`
  - `/api/ai/status` already exposes `busy_payload`
  - `/api/pipeline/state` already returns full pipeline state
  - `/api/pipeline/theme/save` writes `output/sets/<CODE>/theme.json`
  - **No** `/api/pipeline/theme/load` — load is purely client-side via file picker
  - `extract-stream` is single-subscriber: one queue, on disconnect calls `request_cancel()` (kills run)
  - `_upload_cache` is popped on stream completion or disconnect → can't reattach to same upload
- `mtgai/pipeline/theme_extractor.py` — `get_current_log_path()` exposes the active log dir
- `mtgai/pipeline/models.py` — `PipelineState` already has full state, persisted to `output/sets/<CODE>/pipeline-state.json`
- `mtgai/gallery/templates/theme.html` injects `EXISTING_THEME = null` on every page load → no server-side hydration today
- `mtgai/gallery/templates/static/theme.js` populates from `EXISTING_THEME` only; the "Load Existing" button reads a JSON file picked client-side
- Pipeline dashboard already template-injects `PIPELINE_STATE` from disk; survives reload — but doesn't auto-pick up theme/active set changes
- Configure / review / progress / settings: none persist filter selections, scroll, or expanded panels

## Design

### Server: `/api/runtime/state`

New endpoint, returns the canonical "what's the world look like right now" snapshot:

```json
{
  "active_set": "ASD",
  "ai_lock": { "running": true, "running_action": "Theme extraction", "started_at": "...", "log_path": "..." },
  "active_runs": {
    "theme_extraction": { "upload_id": "abc123", "started_at": "...", "events_count": 42 }
  },
  "pipeline": null | { ...PipelineState fields the banner needs... },
  "theme": null | { ...theme.json contents for active_set... }
}
```

`active_set` resolution order:
1. Explicit `?set_code=` query param
2. Most recently modified `output/sets/*/pipeline-state.json` parent dir
3. Most recently modified `output/sets/*/theme.json` parent dir
4. `MTGAI_REVIEW_SET` env var (default `"ASD"`)

### Server: `/api/pipeline/theme/load`

`GET /api/pipeline/theme/load?set_code=ASD` → returns `output/sets/ASD/theme.json` content, or 404 if absent. Lets the theme wizard hydrate on mount without bundling theme JSON into every request.

### Server: theme extraction reattach

Move the per-request extraction queue into a module-level `ExtractionRun` singleton that survives client disconnects.

New module: `mtgai/runtime/extraction_run.py`

```python
@dataclass
class ExtractionRun:
    upload_id: str
    started_at: datetime
    finished_at: datetime | None
    status: str   # "running" | "completed" | "cancelled" | "error"
    events: list[dict]              # full event log, replayed to late subscribers
    subscribers: set[queue.Queue]
    lock: threading.Lock

_run: ExtractionRun | None = None

def start_run(upload_id) -> ExtractionRun: ...
def append_event(event: dict) -> None: ...   # broadcasts to subscribers
def subscribe() -> queue.Queue: ...          # returns a queue pre-loaded with all past events
def unsubscribe(q: queue.Queue) -> None: ...
def mark_done(status: str) -> None: ...
def current() -> ExtractionRun | None: ...
def reset() -> None: ...                     # for tests
```

Modified `extract-stream`:
- If `_run` exists and is for `upload_id`: subscribe + replay + tail. Don't start a new worker.
- If `_run` exists and is running for a different upload_id: 409 with `busy_payload()`.
- If `_run` doesn't exist or last run completed: start fresh worker.
- On client disconnect: `unsubscribe()` only. **No `request_cancel()`**.
- Cancel is opt-in, via the existing `/api/ai/cancel` (or `/theme/cancel` alias) — wired to the cancel button.
- Don't pop `_upload_cache[upload_id]` on disconnect; only pop when the run completes or fails.

Late-subscriber UX: when the user tabs back, the front-end calls `extract-stream` again with the same `upload_id`. They see the full event log replay (theme text fills the textarea, status events bring the progress bar to its current %), then live-tail any new events. If the run already finished, they get the final events including `done` → UI shows "Extraction complete" without the user having to re-upload.

### Client: `static/ui_state.js`

Tiny helper module loaded on every page via `base.html`:

```js
window.MtgaiState = {
  setCode: () => localStorage.getItem('mtgai:active_set') || 'ASD',
  setSetCode: (c) => localStorage.setItem('mtgai:active_set', c.toUpperCase()),
  get: (key, fallback) => { ... },         // reads `mtgai:<setCode>:<key>`
  set: (key, value) => { ... },
  remove: (key) => { ... },
};
```

Plus a small `fetchRuntimeState(setCode?)` helper that hits `/api/runtime/state` and returns a Promise.

### Client: theme wizard

On mount:
1. `fetchRuntimeState()` → if `theme` non-null, populate form (via existing `populateFromTheme`)
2. If `active_runs.theme_extraction`, switch to "extraction in progress" UI: show progress bar, busy banner, and immediately start a subscriber to `extract-stream?upload_id=<active.upload_id>`
3. `EXISTING_THEME` template injection becomes a no-op (kept for backwards compat but server always sends `null`)

Persist to localStorage on input:
- Set name / code / size / mechanic count / setting prose / constraints array / card_requests array → all `mtgai:<setCode>:theme_draft.*`
- Cleared on save (theme.json on disk supersedes the draft)

### Client: pipeline dashboard

Already mostly works (template-injected state + `/api/pipeline/events` SSE auto-reconnect). One small change: switch from template injection to `fetchRuntimeState()` on mount, so a tab-back picks up state changes that happened while away. SSE reconnect is automatic via EventSource.

### Client: configure page

- Last-used set code: pulled from `MtgaiState.setCode()` on mount; saved on input
- Stage review modes: `mtgai:<setCode>:configure.stages`
- Active preset: `mtgai:<setCode>:configure.preset`
- Set size / mechanic count: same key prefix

### Client: review pages (review / progress / booster)

- Active filters: `mtgai:<setCode>:review.filters`
- Sort selection: `mtgai:<setCode>:review.sort`
- In-progress decisions (per card): `mtgai:<setCode>:review.decisions`
- Scroll position: `mtgai:<setCode>:review.scrollY` saved on `beforeunload`

## File-by-file changes

### Add
- `backend/mtgai/runtime/runtime_state.py` — `compute_runtime_state(set_code) -> dict`, `_resolve_active_set_code()`
- `backend/mtgai/runtime/extraction_run.py` — `ExtractionRun`, broadcast queue, `start_run`/`append_event`/`subscribe`/`unsubscribe`/`mark_done`/`current`/`reset`
- `backend/mtgai/gallery/templates/static/ui_state.js` — `MtgaiState`, `fetchRuntimeState`
- `backend/tests/test_runtime_state.py` — endpoint shape tests
- `backend/tests/test_extraction_run.py` — subscribe/replay/multi-subscriber/disconnect-doesn't-cancel tests

### Modify
- `backend/mtgai/pipeline/server.py`:
  - `/api/runtime/state` route
  - `/api/pipeline/theme/load` route
  - Refactor `extract-stream` to use `extraction_run` module — replay + tail + multi-subscriber
  - Disconnect → unsubscribe (not cancel)
- `backend/mtgai/gallery/templates/base.html` — load `ui_state.js`
- `backend/mtgai/gallery/templates/theme.html` — hydration banner / busy banner; `EXISTING_THEME` becomes no-op
- `backend/mtgai/gallery/templates/static/theme.js` — `fetchRuntimeState()` on mount, draft persistence, reattach UI
- `backend/mtgai/gallery/templates/static/configure.js` — localStorage persistence
- `backend/mtgai/gallery/templates/static/review.js` — localStorage persistence
- `CLAUDE.md` — document new endpoint + `extraction_run` module

## Tests

### Unit

- `test_runtime_state.py`:
  - returns ai_lock idle when no run
  - returns ai_lock running when extraction is in flight (mock acquire)
  - returns pipeline state when one exists
  - returns theme when theme.json exists
  - resolves `active_set` from various sources
- `test_extraction_run.py`:
  - subscribe before any events → receives nothing yet
  - append → subscriber receives
  - subscribe after events → replays in order
  - second subscriber receives same future events as first
  - unsubscribe doesn't drop other subscribers
  - mark_done emits final event to all subscribers
  - reset clears state for next run

### Manual (documented in tracker)

- Tab switch (no AI): theme form survives switching to /pipeline and back
- Page reload: theme form survives F5 (via fetchRuntimeState + theme.json on disk + localStorage drafts)
- Browser close + reopen: theme.json on disk + localStorage drafts hydrate
- Mid-extraction reattach: start extraction, navigate to /pipeline, navigate back to /pipeline/theme — should see the running extraction with progress, no double-stream

## Out of scope

- Cross-tab realtime sync within same browser (open in two tabs, edit one, see other update). The card explicitly excludes this.
- Persisting other AI runs (mechanic, archetype, card-gen, balance, art) — those stages don't exist yet. The `active_runs` dict shape is forward-compatible.
- Cleaning up old extraction runs on disk. Existing TTL/eviction in `_upload_cache` is sufficient for the in-memory side.

## Verification

- `ruff check .` and `ruff format .` clean
- `pytest` clean (focus on new test files)
- Manual smoke: tab switch / reload / browser restart / mid-extraction reattach
