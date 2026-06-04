# Tracker: feat/char-refs — Character Reference Images rework

Card: 6a20aa84 — recurring-entity refs, neutral images, streaming/upload UI.

## Phase 1: Pick up
- [x] Pull master
- [x] Read card + CONTRIBUTING + contracts + wizard conventions
- [x] Move card to Doing (already there)
- [x] Worktree + branch + push
- [x] uv sync --extra dev (running)

## Phase 2: Research (done)
- char_portraits stage_id KEPT. STAGE_DEFINITIONS untouched (review_eligible=True already).
- Card.ArtCharacterRef + art_character_refs already on master.
- Old approach: prompt_builder.get_character_ref_paths scans at render time.
- ASD dict: character_portraits._extract_portrait_details:105 — to gut.
- visual_reference.json keyed dicts: legendary_characters/creature_types/factions/landmarks.
- LLM stage pattern: land_generator (generate_with_tool, system_blocks, ai_lock, cancel).
- Image gen: image_generator.generate_image_comfyui(prompt,width,height) -> (bytes, meta).
- SSE: StageEmitter.event(type, **data); stage_hooks pattern. event_bus in server.
- Image serving: /art/ /renders/ referenced but NOT mounted — need a char-refs image route.

## Phase 3: Design
- [x] Rewrite character_portraits.py: LLM recurring-entity detection + neutral gen + attach refs.
- [x] Drop _extract_portrait_details ASD dict.

## Phase 4: Implement
- [x] character_portraits.py: detect_recurring_entities (LLM) + build neutral prompts from visual-references.json + generate (ComfyUI) + attach art_character_refs to cards.
- [x] stages.run_char_portraits: swap internals (ai_lock, poller, cancel, emitter, SSE hooks).
- [x] clear_char_portraits: also strip art_character_refs off cards.
- [x] server.py: /api/wizard/char_refs/{state,refresh,upload,save} + image-serving route.
- [x] wizard_char_refs.js (replace wizard_char_portraits.js usage) + script tag.
- [x] CLAUDE.md doc update.

## Phase 5: Verify
- [x] ruff check . / ruff format .
- [x] python -c "import mtgai"
- [x] pytest (ignore known test_finalize::test_manual_errors_surfaced)
- [x] Add tests: entity detection parsing, attachment, ASD-dict removal regression.

## Phase 6: Ship (STOP after push)
- [x] Self-review full diff
- [x] Commit + push branch
- [ ] STOP — no merge, no worktree removal, no Trello.

## Manual-test notes
- Live image gen needs ComfyUI (not runnable here) — gen path mocked in tests.
- Downstream art_gen reads card.art_character_refs.
