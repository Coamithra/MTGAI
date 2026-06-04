# Tracker: refactor/art-render-topology (card 6a20b13a — FOUNDATION)

## Phase 1: Pick Up
- [x] Read card + CONTRIBUTING + CLAUDE.md
- [x] Card already in Doing
- [x] Create worktree + branch, push upstream
- [x] uv sync in worktree backend
- [x] Create tracker doc

## Phase 2: Research (done inline)
- [x] STAGE_DEFINITIONS (models.py:203)
- [x] STAGE_RUNNERS / STAGE_CLEARERS (stages.py)
- [x] model_settings.py (break points, assignments, names, presets)
- [x] server.py logs map + routing
- [x] wizard.html JS includes + per-tab JS renderers
- [x] art_selector model resolution (keep art_select model key)

## Phase 3: Decisions
- [x] char_portraits id KEPT (only display_name -> "Character References")
- [x] art_select model-assignment key KEPT (select pass still resolves it); removed only from STAGE_DEFINITIONS/runners/clearers/break_points
- [x] Remove 4 dead wizard JS tab files (art_select, human_art_review, render_qa, human_final_review)

## Phase 4: Implement
- [x] models.py STAGE_DEFINITIONS: 9 -> 5 tail
- [x] stages.py STAGE_RUNNERS: drop 4 ids; merged run_art_gen chains select; run_rendering render-only
- [x] stages.py STAGE_CLEARERS: drop 4 ids
- [x] stages.py: remove dead run_human_art_review / run_render_qa / run_human_final_review
- [x] model_settings.py DEFAULT_BREAK_POINTS: art_gen+rendering review; drop dead keys
- [x] server.py: logs map cleanup if needed
- [x] wizard.html: drop 4 JS script tags; rework not done
- [x] Remove 4 dead JS files
- [x] Tests updated
- [x] CLAUDE.md updated

## Phase 5: Verify
- [x] ruff check .
- [x] ruff format .
- [x] python -c "import mtgai"
- [x] pytest (full)
- [x] grep sweep for 4 removed ids

## Phase 6: Ship (partial — STOP after push)
- [x] Commit + push to feature branch
- [ ] (orchestrator handles merge — DO NOT)
