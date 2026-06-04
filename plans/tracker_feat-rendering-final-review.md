# Tracker: feat/rendering-final-review

Card 6a20ae70 — Rendering & Final Review (merge render/QA/review; render all + manual edit + remove-card)

## Phase 1: Pick up
- [x] Read card + CONTRIBUTING + contracts + tab conventions
- [x] Worktree + branch + push
- [x] uv sync --extra dev

## Phase 2: Research
- [x] run_rendering / STAGE_RUNNERS (foundation already merged topology; QA/final_review runners gone)
- [x] finalize.py (per-card validate+reminder reuse) + finalize wizard tab (closest template)
- [x] card_renderer.py (render_set, render_and_save, render_card; CardRenderer() no-arg is broken — needs default args)
- [x] io/paths.py + card_io.py (card_slug, save_card with rename-on-slug-change)
- [x] collector_number format = <COLOR>-<RARITY>-<NN> (e.g. B-C-02); renumber = contiguous index per color-rarity group
- [x] SSE stream bridge (W.registerStream / wizard.js subscription block)
- [x] no image-serving route exists — must add one (render PNG by collector_number)

## Phase 3: Design (decisions)
- run_rendering: render all (stream per-card via render_card SSE event), under AI lock, cancellable, then pause for review (break=review default).
- New module mtgai/review/render_review.py: pure renumber + per-card finalize helpers (unit-testable, no FastAPI).
  - finalize_one_card(card, mechanics): reuse finalize.finalize_card scoped to one card.
  - plan_renumber(cards, removed_cn): returns {old_cn -> new_cn} remap within the removed card's color-rarity group, contiguous.
- Endpoints (server.py, append-only block):
  - GET  /api/wizard/rendering/state    → cards[] (with render_url + has_render), summary, stage base
  - POST /api/wizard/rendering/save-card → per-card edit: finalize-one + re-render that card (AI-lock guarded)
  - POST /api/wizard/rendering/remove-card → hard-delete + renumber group + re-render affected (AI-lock guarded)
  - POST /api/wizard/rendering/approve   → final approve-to-print gate (advance; last stage → /pipeline)
  - GET  /api/wizard/rendering/image/{cn} → serve render PNG (scoped to asset renders dir)
- wizard_rendering.js: gallery of render images streaming in + per-card editor + remove + approve footer.
- wizard.js: subscribe render_card / render_reset SSE events → onRenderingStream bridge.
- CardRenderer.__init__: default assets_root/output_root from repo_root() so CardRenderer() works.

## Phase 4: Implement
- [x] render_review.py (renumber + finalize-one helpers)
- [x] CardRenderer default-arg constructor
- [x] run_rendering: stream + cancellable + lock
- [x] server.py endpoints
- [x] wizard_rendering.js rewrite
- [x] wizard.js SSE subscription
- [x] CLAUDE.md doc update + Removed legacy pages note
- [x] Ensure check_card_heuristics no longer on render path (foundation already removed; verify)

## Phase 5: Verify
- [x] ruff check . / ruff format .
- [x] python -c "import mtgai"
- [x] pytest (ignore known test_finalize.py::test_manual_errors_surfaced)
- [x] new tests: per-card edit finalize pass, renumber (gaps, last-card, cross-refs)

## Phase 6: Ship (STOP after push)
- [x] self-review diff
- [x] commit + push branch
- STOP (no master merge, no worktree removal, no Trello)
