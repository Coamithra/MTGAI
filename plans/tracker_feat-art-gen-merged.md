# Tracker: feat/art-gen-merged (card 6a20adda)

Rework `run_art_gen` internals into one cohesive stage: generate N -> LLM judge best-of-N
-> human review/override. Topology already merged at registry level (DO NOT touch
STAGE_DEFINITIONS / runner maps / break points / position tests).

## Phase 1: Pick up
- [x] Read card, CONTRIBUTING, contracts, conventions, source files
- [x] Worktree + branch + push
- [x] Tracker doc

## Phase 2/3: Design
- [x] Trace run_art_gen, image_generator, art_selector, settings, models.toml, wizard stub

## Phase 4: Implement
- [ ] Settings: best-of-N knob (SetParams.art_versions_per_card) + surface judge model
- [ ] image_generator.py: provider dispatch (flux direct / hosted stub), ref-conditioning
      (read art_character_refs -> PuLID/IP-Adapter stub), best-of-N (generate N versions)
- [ ] art_selector.py: fold judge into a per-card helper the stage calls
- [ ] stages.run_art_gen: gen N -> judge -> stream per card; cancellable; resumable; one AI lock
- [ ] server.py: /api/wizard/art_gen/{state,refresh,repick,reroll,upload} + image serving route
- [ ] wizard_art_gen.js: merged review surface (stream, repick, reroll, upload, auto-pick+reason)
- [ ] wizard.html: script tag (verify present) + SSE event names in wizard.js
- [ ] CLAUDE.md doc updates

## Phase 5: Verify
- [ ] ruff check . / ruff format .
- [ ] python -c "import mtgai"
- [ ] pytest (ignore known test_finalize.py::test_manual_errors_surfaced)
- [ ] new tests: best-of-N knob, ref-conditioning wiring, provider dispatch/stub, judge-model resolution
- [ ] preserve test_art_selector.py

## Phase 6: Review & ship (STOP after commit+push)
- [ ] /review, fix findings
- [ ] commit + push branch, STOP
