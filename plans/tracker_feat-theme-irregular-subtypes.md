# Tracker: feat/theme-irregular-subtypes

Card: Theme-drive the irregular-subtype pick in the skeleton (6a216876)

## Phase 1: Pick Up the Card
- [x] Pull latest master (worktree off master HEAD 5d84556)
- [x] Read the card (description, linked context)
- [x] Move card to Doing
- [x] Create worktree and branch

## Phase 2: Research
- [x] Read `_assign_subtypes` + `IRREGULAR_SUBTYPES` (skeleton/generator.py)
- [x] Read `SkeletonKnobs` + `KNOB_SPECS` + `from_payload`/`merge_pins_from` (skeleton/knobs.py)
- [x] Read AI knob tuner (generation/skeleton_knobs_tuner.py) + prompts
- [x] Read wizard skeleton UI (wizard_skeleton.js) + server endpoints
- [x] Read existing subtype tests + drift test

## Phase 3: Design
- [x] Approach: add `irregular_subtypes: list[str]` to SkeletonKnobs (structured, like cycles)
- [x] UI scope confirmed with user: editable picks UI

## Phase 4: Implement
- [x] knobs.py: add `irregular_subtypes` field + from_payload validation + merge_pins_from carry-over
- [x] generator.py: `_assign_subtypes` uses irregular_subtypes as priority order, RNG fallback fill; expose IRREGULAR_SUBTYPE_NAMES
- [x] tuner: add `irregular_subtypes` to tool schema (enum array) + prompt guidance
- [x] server.py: round-trip `irregular_subtypes` (knobs payload + state)
- [x] wizard_skeleton.js: editable picks control + include in payload
- [x] CSS if needed
- [x] CLAUDE.md update

## Phase 5: Verify
- [x] ruff check + format
- [x] python -c "import mtgai"
- [x] pytest (subtypes, knobs, tuner)
- [ ] manual smoke (serve, skeleton tab) — flag for user

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review, fix findings
- [ ] pull master, merge, cleanup
- [ ] delete plan/tracker, move card to Done, comment
- [ ] overview to user
