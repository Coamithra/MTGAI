# MTGAI Project Conventions

## Trello Board
- **Board**: [MTGAI](https://trello.com/b/Am3RvaZM) — id `69f86a83`
- **Lists**: `To Do` → `Doing` → `Done`. **Labels**: `bug` (red), `feature` (green), `refactor` (blue), `design` (purple), `infra` (orange), `docs` (yellow)
- **CLI**: `trello --board 69f86a83 <command>` (e.g. `card move`, `comment add`, `card add`)
- **Picking up a card?** Read `CONTRIBUTING.md` first — it's the runbook (tracker doc → worktree → research → design → implement → verify → review → ship).

## Project Structure
- Backend: `backend/mtgai/`. Tests: `backend/tests/` (mirrors source). Research: `research/`. Learnings: `learnings/`. Plans + tracker: `plans/` (TRACKER.md is master progress).
- All `output/` is gitignored. Pre-existing tracked files (ASD's `cards/`, `mechanics/`, `reports/`) stay tracked; new artifacts in `output/` won't be picked up.

## Development
- Python 3.12+ (uv-managed). Lint: `ruff check .` / `ruff format .` from `backend/`. Tests: `pytest` from `backend/`.

## Code Style
- Pydantic v2 for all data structures. StrEnum for enumerations.
- `X | Y` union syntax (not `Union[X, Y]`). `list[X]` (not `List[X]`).
- Line length 100. Imports sorted by Ruff (isort).

## Data Models
- Card schema is the single source of truth: `mtgai/models/card.py`. Field names match Scryfall (`oracle_text`, not `rules_text`).
- Card data: JSON files in `output/sets/<SET_CODE>/cards/`.
- Naming: `<collector_number>_<card_name_slug>.json`; art: `..._v<attempt>.png`; render: `....png`.

## Architecture overview

The codebase is a multi-stage pipeline that turns a setting prose document into a finished MTG set (cards + art + rendered images). Stages are orchestrated by `mtgai/pipeline/` and surfaced at `/pipeline` in the local FastAPI server (`python -m mtgai.review serve --open`). Each stage is independently runnable from the CLI.

Card statuses: `draft → validated → approved → art_generated → rendered → print_ready`. Pipeline is resumable; every generation attempt is tracked.

**Key modules** (look in the file for detail; CLI flags via `--help`):

- `mtgai/pipeline/` — end-to-end orchestrator: stage registry, FastAPI server, SSE event bus, wizard shell, configure page. State persisted to `<asset_folder>/pipeline-state.json` (the asset folder the user picked on Project Settings).
- `mtgai/pipeline/wizard.py` — wizard state resolver. Maps the on-disk `pipeline-state.json` + `theme.json` into the visible-tabs / latest-tab shape `wizard.html` consumes. URL routing lives in `pipeline/server.py` (`/pipeline/<tab_id>`). Project Settings (kickoff) tab payload comes from `GET /api/wizard/project`; live-apply edits go through `/api/wizard/project/{params,theme-input,breaks,models,preset/apply,preset/save}`; `POST /api/wizard/project/start` validates + spawns the theme extractor and tells the client to navigate to `/pipeline/theme`. The extraction worker, when launched via the kickoff path, also writes the assembled theme.json on `done` so the Theme tab finds populated content on next mount.
- `mtgai/pipeline/theme_extractor.py` — theme content extraction. Surfaced as the Theme tab inside the wizard. Uploads PDF/text, runs multi-stage LLM extraction, then JSON pass for constraints + card suggestions.
- `mtgai/generation/llm_client.py` — all LLM transport routes through [llmfacade](https://github.com/Coamithra/LLMFacade) (Anthropic + llama.cpp). Single entry point `generate_with_tool()`; provider resolved per-call from the model registry.
- `mtgai/settings/` — model registry (`models.toml`) + the active project's `ModelSettings` (in-memory only; the .mtg file is the persistent store) + global default-preset (`output/settings/global.toml`). The settings shape carries `[llm_assignments]` / `[image_assignments]` / `[effort_overrides]` / `[break_points]` / `[set_params]` (set_name + set_size + mechanic_count) / `[theme_input]` (kind + filename + upload_id + char_count + uploaded_at) / `asset_folder`. All resolution goes through `get_active_settings()` (or `require_active_project().settings`); helpers no longer take `set_code`. The wizard's live-apply endpoints call `apply_settings(new)` to update the pointer; the user saves the .mtg via the browser's File System Access API to persist. Profiles save with `profile_only=True` so they exclude `set_params` + `theme_input` (they're per-project, not template-able). Cross-set defaults UI at `/settings`; per-project Project Settings UI is the wizard's first tab (`/pipeline/project`, endpoints under `/api/wizard/project/*`).
- `mtgai/validation/` — two-tier validators (AUTO auto-fixed; MANUAL becomes LLM retry prompts). Cards immutable; fixers return new instances.
- `mtgai/generation/reminder_injector.py` — reminder text is **never LLM-generated**, always injected programmatically from mechanic definitions after review.
- `mtgai/review/finalize.py` — post-review: inject reminder → validate → auto-fix → save.
- `mtgai/review/ai_review.py` — tiered LLM review (single-reviewer for C/U, full council for R/M + planeswalkers/sagas), iteration loop, resumable.
- `mtgai/analysis/` — balance checks (CMC curve, color balance, etc.) plus LLM-based interaction analysis flagging degenerate combos with named enabler.
- `mtgai/generation/skeleton_reviser.py` — LLM proposes slot changes from balance findings, regenerates affected cards.
- `mtgai/art/` — Flux.1-dev (via ComfyUI at `C:\Programming\ComfyUI`) for art generation, Haiku vision for art selection. PuLID-Flux for character face identity (humanoids only).
- `mtgai/rendering/` — Pillow-based card compositor (M15 frames from Card Conjurer). Renders at 2010×2814, scales to 822×1122 (300 DPI).
- `mtgai/runtime/` — cross-cutting runtime (AI mutex, in-memory active-project pointer, broadcastable SSE for tab reattach). See "Cross-cutting" below.

## Cross-cutting

- **AI mutex (`mtgai/runtime/ai_lock.py`)**: app-wide, **one AI call at a time**. All AI-touching endpoints share it. Conflicting requests get 409 with a busy payload. New guarded endpoints wrap their body in `with ai_lock.hold("Action name") as acquired: if not acquired: return 409`. Long-running callers check `ai_lock.is_cancelled()` inside loops.
- **Tab state (`mtgai/runtime/runtime_state.py`, `extraction_run.py`)**: server is the source of truth for AI run state, pipeline state, and saved theme.json; browser holds UI ephemera in localStorage. SSE streams are broadcastable (tab-switching mid-run does not cancel; cancel is opt-in via the explicit button). New long-running AI runs should follow the same broadcast pattern. Aggregator: `GET /api/runtime/state`.
- **Active project**: which `.mtg` is open is the source of truth. The server holds a process-memory `ProjectState` pointer (`mtgai/runtime/active_project.py` — set_code + settings + .mtg path) — set by `/api/project/{open,materialize}`, cleared by `/api/project/new`, lost on restart so a fresh boot always greets the user with New / Open. Stage outputs land under the project's `asset_folder`; `mtgai/io/asset_paths.set_artifact_dir()` reads the active project and raises `NoAssetFolderError` (translated to 409 at endpoints) if none is open. Switching projects mid-AI-run requires `force=true` in the request body; without it the endpoint returns 409 + the AI lock's busy payload so the client can render a confirm modal. The cancel path calls `ai_lock.request_cancel()` then `active_project.await_lock_release()` before flipping the pointer.
- **Reminder text**: not validated, not LLM-generated. Stripped + injected by `reminder_injector` after review. Validators that touch oracle text must skip parenthesized text.

## Local LLMs
Local models run through llmfacade's `llamacpp` provider in managed mode (lazy-spawns `llama-swap`). Registry: `backend/mtgai/settings/models.toml`. For setup, gotchas, and adding a model, see `learnings/local-llm-setup.md`. For benchmarks: `learnings/llamacpp-tc2-benchmark.md`. For the Gemma repetition-loop story: `learnings/gemma-repetition-loops.md`.

## Toolchain Buildout (in progress)
Making MTGAI reusable for any set, not just ASD. Say "continue toolchain buildout" to resume. Remaining work tracked on Trello: TC-2 (mechanic gen) → TC-3 (archetype gen) → TC-4 (visual refs) → TC-5 (pointed questions template) → TC-6 (prompts module) → TC-7 (skeleton + configure integration).

## Removed legacy pages
Standalone pages **/theme**, **/review**, **/progress**, **/booster** were removed when the wizard subsumed their surfaces. The HTML templates, JS, and route handlers are deleted from the working tree but preserved in git history — when building out the corresponding pipeline stages (review UI, progress dashboard, booster preview), pull them back via `git show <pre-removal-sha>:backend/mtgai/gallery/templates/<name>.html` (and `static/<name>.js`) or `git checkout <sha> -- <path>`. Underlying business logic in `mtgai/review/decisions.py` and `mtgai/packs.py` was kept untouched.

## Git
- Card JSON is version-controlled. Art and rendered images are gitignored.
- Full ignore patterns in `.gitignore` at repo root.
