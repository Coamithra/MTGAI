# Tracker: feat/skeleton-generation

Reshape of the just-merged constraints stage (card 69f9d1ef) per design feedback:
collapse the separate `constraints` stage into ONE "Skeleton Generation" stage.

## Design (locked with user)
- ONE `skeleton` stage: deterministic seed → render each slot to a ` · ` string
  → LLM rewrites each string to fit theme/constraints/requests → store `tweaked_text`
  per slot in skeleton.json. Pass 2 places card_requests onto slots.
- skeleton.json keeps structured slots (reprints/lands untouched) + adds tweaked_text.
  Default string is re-rendered from structured fields (no separate default file).
- Diff UI: per-slot default-vs-tweaked diff via a proper word-level LCS diff
  (zero-dep, hand-rolled) — highlights actual changed tokens, not field splits.
- Auto-runs (no manual "Derive matrix"); Refresh re-rolls. Pauses for review.
- card-gen reads tweaked_text; programmatic color-batcher returns (LLM batcher deleted).
- "constraints" name gone everywhere; assignment + break-point move to `skeleton`.

## Implement
- [ ] SkeletonSlot: add `tweaked_text: str | None`; add render_slot_string()
- [ ] skeleton_relabel.py (rename from constraint_deriver.py): relabel + assign passes
      operate on per-slot strings; reconcile by slot_id; load helper drops
- [ ] run_skeleton: seed → render → LLM relabel+assign (ai_lock, logs→skeleton/logs)
      → write skeleton.json w/ tweaked_text. Remove run_constraints + clear_constraints.
- [ ] models.py: remove `constraints` STAGE_DEFINITIONS entry
- [ ] model_settings.py: drop `constraints` (assignments/presets/breaks); add `skeleton`
      (local default + recommended/all-local + DEFAULT_BREAK_POINTS review)
- [ ] wizard.py: remove fold (_fold_constraints_status + skip)
- [ ] wizard.js: remove constraints stage_update special-case
- [ ] wizard_stage.js: remove FOLDED_HOST/foldedStage
- [ ] server.py: /api/wizard/constraints/* → /api/wizard/skeleton/* (read/write skeleton.json)
- [ ] card_generator.py: read tweaked_text; drop llm_group_slots (programmatic batcher)
- [ ] prompts.py: _blob branch → tweaked_text branch
- [ ] wizard_skeleton.js: diff UI (default vs tweaked, field highlight), auto-run, skeleton endpoints
- [ ] prompts/*.txt: rename + reword for string-rewrite (drop "constraints"/"matrix" wording)
- [ ] tests: rework test_constraint_deriver→skeleton relabel; fix fold/stage-order tests
- [ ] CLAUDE.md + rename plans/constraints-stage.md → skeleton-generation.md

## Verify / ship
- [ ] ruff + import + pytest; boot smoke
- [ ] /review; merge to master; cleanup
