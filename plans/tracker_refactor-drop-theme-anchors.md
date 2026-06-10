# Tracker: refactor/drop-theme-anchors (card 6a29a46e — OPTION B)

## Phase 1: Pick Up
- [x] Claim card (move to Doing + claim comment)
- [x] Pull master
- [x] Read card + comments (OPTION B confirmed)
- [x] Worktree + branch + push

## Phase 2/3: Research + Design
- [x] grep all anchor-field references, distinguish theme reads vs visual-refs category key
- [x] Confirm theme.json is a plain dict (no Pydantic model); server.py assembly never writes anchors
- [ ] Read skeleton.build_reserved_slots + visual_reference_extractor.generate_visual_references
- [ ] Inspect MLP theme.json setting prose format for '# Notable Characters'/'# Landmarks'/'# Factions'
- [ ] Confirm visual_reference.py normalize_entity_key

## Phase 4: Implement
- [ ] skeleton/generator.py: drop legendary_characters/notable_cards from build_reserved_slots (keep card_requests)
- [ ] visual_reference_extractor.py: drop anchor inputs (_format_notable_cards_block, legends read); legacy theme.json tolerated (ignore unknown keys)
- [ ] visual_reference_extractor.generate_visual_references: completeness check + dropped_entities + loud WARN
- [ ] prose section parser (markdown 'Name: description' / 'Name — description')
- [ ] surface dropped_entities on stage result/artifacts
- [ ] CLAUDE.md: build_reserved_slots + visual_refs descriptions -> two-source model

## Phase 5: Verify
- [ ] Tests: legacy theme.json tolerated; build_reserved_slots card_requests only; completeness pass/warn; parser units
- [ ] ruff check . / ruff format . --check
- [ ] python -c "import mtgai"
- [ ] pytest

## Phase 6: Ship
- [ ] commit + push
- [ ] /review + fix findings
- [ ] pull/rebase master (coordinate w/ skeleton agent — keep both changes)
- [ ] re-lint + pytest
- [ ] PR + self-merge
- [ ] cleanup worktree/branch
- [ ] delete tracker
- [ ] card -> Done + comment
