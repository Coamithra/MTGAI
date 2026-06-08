# Tracker: fix/art-gen-live-stream

Card 6a27035b — art_gen tab: live art streaming is broken (art only shows on stage-finish / F5).

## Phase 1: Pick Up
- [x] Pull latest master
- [x] Read the card + root-cause analysis
- [x] Move card to Doing
- [x] Create worktree + branch + push

## Phase 2: Research
- [x] Read wizard_art_gen.js (handler does not render art mid-stream)
- [x] Read stages.run_art_gen gen_progress (event carries no image path)
- [x] Read server.py _art_versions_for_card / _art_gen_cards / refresh _gen_progress
- [x] Confirm StageEmitter.event passes arbitrary kwargs to SSE
- [x] Confirm slug = `<cn>_<nameslug>`; resolve via card name (avoid cn-prefix glob ambiguity)

## Phase 3: Design (option (a) — emit version URLs in the event)
- [x] Shared helper to build {filename,url} version tiles for a card
- [x] cn->name map so emit can resolve slug from cn only

## Phase 4: Implement
- [x] image_generator.art_versions_for_card + card_names_by_cn helper
- [x] stages.run_art_gen: build name map, emit versions on art_gen_card 'generated'
- [x] server.py refresh _gen_progress: same; refactor _art_versions_for_card to reuse helper
- [x] wizard_art_gen.js: render streamed versions live into the tile
- [x] Tests: helper unit tests + art_gen_card-carries-versions emission test

## Phase 5: Verify
- [x] ruff check + format
- [x] python -c "import mtgai"
- [x] pytest (pipeline suite 563 + art subset all green; node --check JS)
- [x] Manual smoke note for user (art stage is multi-hour; logic-verify)

## Phase 6: Ship
- [ ] Commit + push
- [ ] /review + fix findings
- [ ] pull master, merge, lint+tests
- [ ] PR + self-merge
- [ ] cleanup worktree/branch
- [ ] delete tracker
- [ ] card -> Done + comment
