# Supervisor: full unattended server-side reopen + retry resume

Card: 6a273dc1c1a5d5232b2d767a (follow-up to the supervisor card / PR #66).

## Context
`serve --supervised` already auto-restarts the server on a silent crash, but resume is
manual: the user re-opens the project (orphan-cleanup demotes the RUNNING stage → FAILED)
and clicks "Retry this step". This makes resume fully unattended behind an opt-in flag, so
a long art_gen run finishes overnight even when the OS kills the server mid-Flux.

## Design

**Approach: in-process auto-resume in the supervised child** (not supervisor→HTTP).
The card allows "the child ... re-open that .mtg server-side"; calling the underlying
functions (`cleanup_orphan_running_stages`, `retry_current`) directly is functionally
identical to the HTTP endpoints it names, reuses the exact same core, and avoids
HTTP-client + readiness-polling complexity. The supervisor (outer process) only signals
"this boot is a restart" via an env flag.

### Files
- **`mtgai/review/auto_resume.py`** (new) — owns:
  - `ENV_AUTO_RESUME="MTGAI_AUTO_RESUME"` + `is_auto_resume_boot()`.
  - Persistence under `heartbeat.supervisor_dir()`: `last-project.mtg` (the .mtg TOML — the
    browser ships content not a path, so we persist content) + `auto-resume-state.json`
    (the per-stage retry-ceiling counter). write/read/clear helpers for both.
  - `RESUME_CEILING=3` + `decide(prev, instance_id, completed) -> (bool, new_state)` — pure
    progress-aware ceiling: a stage crashing *while advancing* (completed_items grew since
    the last attempt — the bounded art_gen Flux kill carried by resume-skip) resets the
    counter so a long run resumes indefinitely; a stage crashing *without* progress is a
    poison pill, counted and stopped after the ceiling.
  - `maybe_auto_resume()` / `start_auto_resume()` — re-open last project (parse + pin +
    `cleanup_orphan_running_stages`), find the FAILED stage, apply the ceiling, fire
    `retry_current` via the shared spawn helper. Best-effort: never crashes boot.
- **`mtgai/pipeline/server.py`**:
  - Extract `_spawn_retry_engine(state, set_code)` from the retry endpoint (engine build +
    daemon thread + globals); endpoint + auto-resume both call it.
  - `project_open` / `project_materialize`: when `is_supervised_child()`, persist the .mtg
    TOML via `auto_resume.write_last_project(...)`.
  - `project_new`: clear it (abandoned project must not resume).
- **`mtgai/review/server.py`** lifespan: under a supervised child, after starting the
  heartbeat, if `auto_resume.is_auto_resume_boot()` spawn `start_auto_resume()`.
- **`mtgai/review/supervisor.py`**: `run_supervised(..., auto_resume=False)`. At session
  start (when auto_resume) clear last-project + state (fresh session ⇒ only resume a project
  opened this session). Set `ENV_AUTO_RESUME=1` on restart spawns only (never the first).
- **`mtgai/review/cli.py`**: `serve --auto-resume` (opt-in), threaded into `run_supervised`.

### Crash-resume loop guard
Two layers: the existing fast-failure boot-loop guard (a stage that crashes the server
*fast* on restart) + the new progress-aware per-stage ceiling (a stage that crashes slow
but never advances).

## Tests (`tests/test_review/test_auto_resume.py`)
- `decide`: first attempt resumes; progress resets the counter (resume forever); no-progress
  counts and stops at the ceiling; a new instance resets.
- persistence round-trip (write/read/clear last-project + state) under a tmp supervisor dir.
- `is_auto_resume_boot` reads the env.
- supervisor: `--auto-resume` sets `ENV_AUTO_RESUME` on restart spawns but not the first;
  off by default.

## Out of scope
- Switching the existing manual-retry flow (kept; auto-resume just shares its spawn helper).
- HTTP-based supervisor→child resume (in-process chosen instead).
- Persisting a real filesystem path (architecture ships TOML content, not a path).
