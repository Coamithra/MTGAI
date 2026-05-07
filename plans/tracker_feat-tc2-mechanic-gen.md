# Tracker: feat/tc2-mechanic-gen

> Card: [TC-2: Mechanic generation pipeline stage](https://trello.com/c/yw02hjGi) (id `69f86d62`)
> Plan: `plans/phase-tc2-mechanic-gen.md`
> Companion: TC-5 (pointed questions templating) — folds in here, close as duplicate

## Phase 1: Pick up the card
- [x] Pull latest master
- [x] Read card description + plan
- [x] Move card to Doing
- [x] Create worktree `.trees/feat-tc2-mechanic-gen` on `feat/tc2-mechanic-gen`
- [x] Push branch upstream

## Phase 2: Research
- [ ] Read pipeline scaffolding: server.py, wizard.py, engine.py, events.py, models.py, stages.py
- [ ] Read settings/model_settings.py — DEFAULT_BREAK_POINTS, llm_assignments shape
- [ ] Read downstream consumers — skeleton_reviser, reminder_injector, ai_review, finalize, balance — to verify approved.json schema we have to honor
- [ ] Read theme_extractor.py for the streaming pattern (chunk → full event)
- [ ] Read wizard_theme.js + wizard_stage.js for tab UI patterns
- [ ] Read ai_lock + extraction_run for mutex / replay-buffer
- [ ] Inventory ASD `output/sets/ASD/mechanics/` to lock the on-disk schema

## Phase 3: Design
- [ ] Tweak the existing plan if research surfaces gaps; otherwise proceed
- [ ] Confirm with user before implementing — auto mode says proceed unless something is risky/destructive

## Phase 4: Implement
- [ ] **TC-2a**: Refactor `mechanic_generator.py` — drop ASD copy, drive from theme.json + set_params, add MTG-known-keywords collision check, prompt template at `pipeline/prompts/mechanic_system.txt`
- [ ] **TC-2e**: Template assets — `pipeline/templates/pointed_questions.json`, `mtg_known_keywords.json`, evergreen-keywords default
- [ ] **TC-2b**: `run_mechanics` runner + STAGE_RUNNERS + STAGE_DEFINITIONS + STAGE_CLEARERS + DEFAULT_BREAK_POINTS update
- [ ] **TC-2d**: Bespoke endpoints `/api/wizard/mechanics/{refresh-card,refresh-all,save}`
- [ ] **TC-2c**: `wizard_mechanics.js` bespoke candidates strip
- [ ] Update CLAUDE.md if a new convention or contract is introduced

## Phase 5: Verify
- [ ] `ruff check .` clean (from `backend/`)
- [ ] `ruff format .` clean
- [ ] `python -c "import mtgai"` smoke
- [ ] `pytest` clean
- [ ] **TC-2f** ASD migration smoke: open project → mechanics shows `completed`; edit via cascade → downstream cleared; re-runs from mechanics
- [ ] Manual UI smoke (kickoff, candidates strip, picks, refresh-card, refresh-all, save+advance)

## Phase 6: Ship
- [ ] Commit + push
- [ ] `/review` — fix every finding before proceeding
- [ ] Pull master, resolve any conflicts (merge rules)
- [ ] Re-run lint + tests
- [ ] Return to root checkout
- [ ] Merge to master + push
- [ ] Worktree + branch cleanup
- [ ] Delete `plans/phase-tc2-mechanic-gen.md` + this tracker
- [ ] Move card to Done
- [ ] Comment on card with summary + commit hashes
- [ ] Close TC-5 as duplicate (point to this card)
- [ ] Create follow-up cards for anything deferred
- [ ] Final overview to user
