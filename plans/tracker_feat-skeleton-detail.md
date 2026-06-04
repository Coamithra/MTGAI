# Tracker: feat/skeleton-detail

Card: [Revisit skeleton - make more detailed](https://trello.com/c/qHGgod0O) (id `6a215fb8`)

Goal: make the skeleton generator produce a fine-grained, randomized card-type
distribution (artifact creature vs equipment vs vehicle vs colorless artifact;
global vs local enchantment vs aura vs saga; etc.) so LLM-filled slots produce a
varied set that stands toe-to-toe with real MTG sets. Two stages: (1) research a
fine-grained type distribution with random ranges; (2) implement in the skeleton
generator + knobs + related stages with user/AI-tweakable randomization.

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments)
- [x] Move card to Doing
- [x] Create worktree and branch + push

## Phase 2: Research
- [x] Read existing research/ + learnings/ for type-distribution material
- [x] Read skeleton generator + knobs current state (generator.py, knobs.py, tuner)
- [x] Trace how slot type flows into card_gen prompt
- [x] Research pass: fine-grained card-type distribution in real MTG sets (ranges)
      -> research/set-design.md §2.3 + A.3 already has equipment/aura/vehicle/saga
         counts + ranges + artifact-creature / enchantment-creature figures.
- [x] Summarize findings (subtype distribution table below)

## Phase 3: Design
- [x] Draft approach in plans/skeleton-detail.md
- [x] Identify knob/schema changes, randomization model, blast radius
- [x] Align with user (approved: full set + irregular bucket + scryfall + det. seed)
- [x] Scryfall pass over last 12 sets -> research/subtype-distribution.md

## Phase 4: Implement
- [x] Implement skeleton type-detail + randomization (SlotCardSubtype, _assign_subtypes)
- [x] Thread through knobs (7 new KNOB_SPECS + SkeletonKnobs fields, subtype group)
- [x] Wizard GROUP_LABELS + knobs context prompt
- [x] Update CLAUDE.md / plan / research docs

## Phase 5: Verify
- [x] ruff check + format (clean)
- [x] python -c "import mtgai" (OK)
- [x] pytest (1788 passed; test_config.py pre-broken: missing pydantic_settings)
- [x] Manual smoke (generate_skeleton: subtypes appear, invariants hold, det+reroll)
- [ ] Spot-check diff

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review, fix findings
- [ ] Pull master, resolve conflicts
- [ ] Re-run lint + tests
- [ ] Merge to master + push
- [ ] Clean up worktree + branch
- [ ] Delete plan + tracker
- [ ] Move card to Done + comment
- [ ] Follow-up cards
- [ ] Final overview to user
