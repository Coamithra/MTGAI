# Tracker: feat/skeleton-knobs (card 6a16d8ff)

Theme-driven skeleton knobs + cycle primitive. Full scope: Phases A + B + C.
Design: `plans/skeleton-knobs.md`.

## Phase 1: Pick up
- [x] Pull latest master
- [x] Read card + plan + research/set-design.md
- [x] Move card to Doing
- [x] Create worktree + branch + push

## Phase 2/3: Research + design
- [x] Read generator.py, skeleton_relabel.py, stages.run_skeleton
- [x] Read prompts.py (format_slot_specs, build_user_prompt), card_generator batching
- [x] Read land_generator.py + reprint_selector integration points
- [x] Read wizard_skeleton.js + wizard-tab-conventions.md
- [x] Confirm scope with user (all three phases)
- [ ] Finalize file-by-file design in plans/skeleton-knobs.md

## Phase 4: Implement — Phase A (scalar knobs)
- [ ] `skeleton/knobs.py`: SkeletonKnobs schema + KnobSpec registry + Cycle/CycleSpan + clamp/validate/feasibility + provenance
- [ ] `generator.py`: thread knobs into _scale_rarity / _distribute_colors / _assign_card_types / signposts / planeswalker; defaults reproduce current
- [ ] `generation/skeleton_knobs_tuner.py`: phase 0 LLM tuner (tool call, clamp, default-on-failure)
- [ ] prompts: `skeleton_knobs_{system,user}.txt`; lift shared _format_* block helpers
- [ ] `stages.run_skeleton`: insert phase 0 before generate_skeleton
- [ ] `server.py`: GET state includes knobs; POST /api/wizard/skeleton/knobs (set+validate+rebuild)
- [ ] `wizard_skeleton.js` + `wizard.css`: Knobs panel (controls, provenance, pin, Refresh)

## Phase 4: Implement — Phase B (spell cycles)
- [ ] Cycle reservation in generate_skeleton (balance-preserving spans)
- [ ] cycle_id + template stamped on member slots
- [ ] card_generator: cycle-coherent batching (members in one batch); format_slot_specs threads template
- [ ] tuner proposes cycles; UI lists cycles

## Phase 4: Implement — Phase C (land cycles)
- [ ] Land cycle slots in skeleton budget (card_type=land, cycle_id)
- [ ] card_generator skips land slots
- [ ] reprint identification skips cycle members
- [ ] lands stage generates land-cycle slots (one call, shared template)

## Phase 5: Verify
- [ ] ruff check + format clean
- [ ] python -c "import mtgai"
- [ ] pytest (esp. test_skeleton.py — no regressions; new tests for knobs/cycles)
- [ ] Manual smoke notes for LLM/pipeline paths

## Phase 6: Ship
- [ ] Commit + push
- [ ] /review, fix findings
- [ ] pull master, resolve, re-test
- [ ] merge to master, clean worktree
- [ ] delete plan + tracker
- [ ] move card to Done + comment
- [ ] follow-up cards if needed
- [ ] final overview to user
