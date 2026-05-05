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

- `mtgai/pipeline/` — end-to-end orchestrator: stage registry, FastAPI server, SSE event bus, wizard shell, configure page. State persisted to `output/sets/<SET>/pipeline-state.json`.
- `mtgai/pipeline/wizard.py` — wizard state resolver. Maps the on-disk `pipeline-state.json` + `theme.json` into the visible-tabs / latest-tab shape `wizard.html` consumes. URL routing lives in `pipeline/server.py` (`/pipeline/<tab_id>`). Project Settings (kickoff) tab payload comes from `GET /api/wizard/project`; live-apply edits go through `/api/wizard/project/{params,theme-input,breaks,models,preset/apply,preset/save}`; `POST /api/wizard/project/start` validates + spawns the theme extractor and tells the client to navigate to `/pipeline/theme`. The extraction worker, when launched via the kickoff path, also writes the assembled theme.json on `done` so the Theme tab finds populated content on next mount.
- `mtgai/pipeline/theme_extractor.py` — theme content extraction. Surfaced as the Theme tab inside the wizard. Uploads PDF/text, runs multi-stage LLM extraction, then JSON pass for constraints + card suggestions.
- `mtgai/generation/llm_client.py` — all LLM transport routes through [llmfacade](https://github.com/Coamithra/LLMFacade) (Anthropic + llama.cpp). Single entry point `generate_with_tool()`; provider resolved per-call from the model registry.
- `mtgai/settings/` — model registry (`models.toml`) + per-set assignments (`output/sets/<SET>/settings.toml`, one file per set) + global default-preset (`output/settings/global.toml`). `settings.toml` carries `[llm_assignments]` / `[image_assignments]` / `[effort_overrides]` / `[break_points]` / `[set_params]` (set_name + set_size + mechanic_count, lifted out of theme.json) / `[theme_input]` (kind + filename + upload_id + char_count + uploaded_at). All resolution goes through `get_settings(set_code)` / `get_llm_model(stage_id, set_code)`. Stage runners must resolve once at the top of the run. Profiles save with `profile_only=True` so they exclude `set_params` + `theme_input` (they're per-set, not template-able). Cross-set defaults UI at `/settings`; per-set Project Settings UI is the wizard's first tab (`/pipeline/project`, endpoints under `/api/wizard/project/*`).
- `mtgai/validation/` — two-tier validators (AUTO auto-fixed; MANUAL becomes LLM retry prompts). Cards immutable; fixers return new instances.
- `mtgai/generation/reminder_injector.py` — reminder text is **never LLM-generated**, always injected programmatically from mechanic definitions after review.
- `mtgai/review/finalize.py` — post-review: inject reminder → validate → auto-fix → save.
- `mtgai/review/ai_review.py` — tiered LLM review (single-reviewer for C/U, full council for R/M + planeswalkers/sagas), iteration loop, resumable.
- `mtgai/analysis/` — balance checks (CMC curve, color balance, etc.) plus LLM-based interaction analysis flagging degenerate combos with named enabler.
- `mtgai/generation/skeleton_reviser.py` — LLM proposes slot changes from balance findings, regenerates affected cards.
- `mtgai/art/` — Flux.1-dev (via ComfyUI at `C:\Programming\ComfyUI`) for art generation, Haiku vision for art selection. PuLID-Flux for character face identity (humanoids only).
- `mtgai/rendering/` — Pillow-based card compositor (M15 frames from Card Conjurer). Renders at 2010×2814, scales to 822×1122 (300 DPI).
- `mtgai/runtime/` — cross-cutting runtime (AI mutex, active-set persistence, broadcastable SSE for tab reattach). See "Cross-cutting" below.

## Cross-cutting

- **AI mutex (`mtgai/runtime/ai_lock.py`)**: app-wide, **one AI call at a time**. All AI-touching endpoints share it. Conflicting requests get 409 with a busy payload. New guarded endpoints wrap their body in `with ai_lock.hold("Action name") as acquired: if not acquired: return 409`. Long-running callers check `ai_lock.is_cancelled()` inside loops.
- **Tab state (`mtgai/runtime/runtime_state.py`, `extraction_run.py`)**: server is the source of truth for AI run state, pipeline state, and saved theme.json; browser holds UI ephemera in localStorage. SSE streams are broadcastable (tab-switching mid-run does not cancel; cancel is opt-in via the explicit button). New long-running AI runs should follow the same broadcast pattern. Aggregator: `GET /api/runtime/state`.
- **Active set**: top-bar set picker is the single source of truth (persisted to `output/settings/last_set.toml`). Endpoints under `/api/runtime/`.
- **Reminder text**: not validated, not LLM-generated. Stripped + injected by `reminder_injector` after review. Validators that touch oracle text must skip parenthesized text.

## Local LLMs
Local models run through llmfacade's `llamacpp` provider in managed mode (lazy-spawns `llama-swap`). Registry: `backend/mtgai/settings/models.toml`. For setup, gotchas, and adding a model, see `learnings/local-llm-setup.md`. For benchmarks: `learnings/llamacpp-tc2-benchmark.md`. For the Gemma repetition-loop story: `learnings/gemma-repetition-loops.md`.

## Toolchain Buildout (in progress)
Making MTGAI reusable for any set, not just ASD. Say "continue toolchain buildout" to resume. Remaining work tracked on Trello: TC-2 (mechanic gen) → TC-3 (archetype gen) → TC-4 (visual refs) → TC-5 (pointed questions template) → TC-6 (prompts module) → TC-7 (skeleton + configure integration).

## Git
- Card JSON is version-controlled. Art and rendered images are gitignored.
- Full ignore patterns in `.gitignore` at repo root.
