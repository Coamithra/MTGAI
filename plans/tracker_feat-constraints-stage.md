# Tracker: feat/constraints-stage

Card 69f9d1ef (sMSqWKw6) — constraint-derivation stage. Plan: `plans/constraints-stage.md`.

## Phase 1–3 (done)
- [x] Card + plan + runbook, move to Doing, worktree + venv, plan lock-in committed
- [x] Research (skeleton model, stage runners, archetypes UI template, conventions,
      format_slot_specs, card-gen batching, skeleton_reviser, Transformers corpus)
- [x] Forks resolved with user: full free-text matrix + LLM batcher; fold UI into
      Skeleton tab; keep+re-scope skeleton_rev. Design appended to constraints-stage.md.

## Phase 4: Implement (done)
- [x] constraint_deriver.py (relabel + assign passes, reconcile, load, llm_group_slots)
- [x] prompts: constraints_{relabel,assign}_{system,user}.txt (brace-escaped few-shot)
- [x] run_constraints stage + clear_constraints + STAGE_RUNNERS/CLEARERS
- [x] STAGE_DEFINITIONS (constraints after skeleton) + DEFAULT_LLM_ASSIGNMENTS +
      recommended preset + DEFAULT_BREAK_POINTS(review)
- [x] card_generator: load matrix, inject _blob, LLM batching branch; prompts.format_slot_specs _blob branch
- [x] wizard.compute_visible_tabs fold + _fold_constraints_status; wizard.js stage_update fold
- [x] /api/wizard/constraints/{state,refresh,save} endpoints
- [x] wizard_skeleton.js bespoke tab + wizard.css + wizard.html script tag
- [x] skeleton_rev re-scope docstring + CLAUDE.md

## Phase 5: Verify (done so far)
- [x] ruff clean on all touched files (pre-existing repo violations untouched)
- [x] import smoke (server + wizard + deriver + card_gen)
- [x] pytest: 1240 passed (4 stage-order tests updated + 12 new deriver tests + fold test)
- [ ] boot smoke worktree server (non-LLM)
- [ ] LLM walkthrough — FLAG FOR USER (needs API key in their env; ~$0.10/run)

## Phase 6: Ship
- [ ] commit implementation
- [ ] /review + fix findings
- [ ] pull master, merge, cleanup worktree, delete plan+tracker, card→Done + comment
