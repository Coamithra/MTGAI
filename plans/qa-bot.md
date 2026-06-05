# QA Bot — self-driving QA system

Card: **QA Bot** (`6a23000b`). Build a self-driving QA system that drives the wizard via
claude-in-chrome, finds bugs, logs them to Trello, farms fixes to subagents (CONTRIBUTING,
full auto self-merge), and loops — restarting the server + a fresh orchestrator when enough
fixes have landed.

## Context

The wizard (`python -m mtgai.review serve`) is a long, slow, LLM-heavy pipeline. Two things
block an autonomous browser agent from QA-ing it:

1. **The native save/open file picker.** The `.mtg` is written 100% client-side via
   `window.showSaveFilePicker()` ([wizard_project.js](../backend/mtgai/gallery/templates/static/wizard_project.js)).
   That's an OS dialog, invisible to claude-in-chrome's DOM tools — the bot gets stuck.
2. **Slow start phases.** Reaching e.g. `ai_review` means running theme_extract → mechanics →
   skeleton → … which can take many minutes even on the cheap model.

There's already a **prefab/debug** system ([prefab.py](../backend/mtgai/generation/prefab.py),
`DebugSettings.use_prefab_{cards,mechanics}`) that short-circuits `card_gen`/`mechanics`, and a
golden complete project on disk (`sets (new)/transformers/`, reached `ai_review`) we can copy
from for deep-stage seeding.

## Design

### Part A — App-side QA harness (gated behind `serve --debug` / `MTGAI_DEBUG=1`)

**Decisions (locked with user):** full system, fixers full-auto-self-merge, `--debug` gating.

1. **`qa` preset** (`settings/model_settings.py` `PRESETS`): every LLM stage →
   `gemma4-26b-iq2m`, `thinking` disabled everywhere. Applied via the existing
   `/api/wizard/project/preset/apply` (already merges `thinking_overrides`).

2. **Debug router** `pipeline/debug_routes.py` (mounted only in debug mode):
   - `GET  /api/debug/state` — `{enabled, prefab_*, golden_candidates, active}`.
   - `POST /api/debug/quick-project` — materialize + activate a QA project in-process
     (qa preset, small set, prefab on, optional inline theme text), persist its `.mtg`
     server-side under `output/qa-runs/<name>/`. **No file picker.** Returns navigate target.
   - `POST /api/debug/seed-stage` — copy a source asset folder (default: auto-detected golden)
     into a fresh `output/qa-runs/<name>/`, rewrite `pipeline-state.json` so stages before the
     target are COMPLETED and the target + downstream are reset PENDING, activate. Jumps the
     wizard straight to any stage with real upstream artifacts present.
   - `POST /api/debug/open-path` — open a `.mtg` from a server-side path (no picker).
   - `POST /api/debug/save-mtg` — write the active project's `.mtg` to its asset folder
     (the Save-button bypass).

3. **Save-button bypass** (`wizard_project.js`): when debug mode is on, `writeMtgFile` POSTs to
   `/api/debug/save-mtg` instead of `showSaveFilePicker()`, so a bot can click Save headlessly.

4. **Debug panel** (`static/wizard_debug.js`, auto-loaded; shows only when `/api/debug/state`
   reports enabled): a floating panel with Quick-project, Seed-to-stage (dropdown), Open-path,
   Save-now buttons — the "debug buttons" the card asks for.

5. **`serve --debug`** (`review/cli.py`): sets `MTGAI_DEBUG=1`; `review/server.py` mounts the
   debug router when enabled.

### Part B — QA methodology (`.claude/skills/qa-bot/`)

A `/qa-bot` skill the orchestrator runs:
1. Pull master, launch `serve --debug`, open Chrome to `/pipeline`.
2. Apply `qa` preset + a quick/seeded project via the debug endpoints.
3. Loop: spawn a **QA probe subagent** (fresh context) to adversarially drive ONE area via
   claude-in-chrome (click everything, bad input, cancel mid-run, tab-switch, edit past stages)
   and report bugs with repro + console errors + screenshot.
4. Orchestrator logs each bug to Trello (To Do, `bug`), and **farms the fix** to a subagent that
   runs CONTRIBUTING end-to-end (full auto self-merge) in its own worktree.
5. Track a bug count; when enough fixes have landed to need a server restart, restart + hand off
   to a fresh orchestrator.

Single live app + AI mutex ⇒ QA driving is **serial** (one probe at a time); only the *fixes*
(code edits) run in parallel worktrees.

## Tests
- `tests/test_pipeline/test_debug_routes.py` — debug gating off by default; quick-project creates
  + activates; seed-stage rewrites state; endpoints 404 when disabled.
- `tests/test_settings/` — `qa` preset resolves all-gemma + thinking-disabled.

## Out of scope
- The native OS save/open picker itself (unreachable by a browser agent — documented, bypassed).
- ComfyUI-dependent art generation correctness (seed gets you to the tab; running Flux needs ComfyUI).

## Verification
- Lint + import + pytest.
- Manual: `serve --debug`, open `/pipeline`, click the debug panel → quick-project + seed-stage,
  confirm the wizard lands on the target tab with artifacts.
