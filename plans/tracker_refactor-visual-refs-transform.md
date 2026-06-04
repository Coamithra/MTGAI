# Tracker: refactor/visual-refs-transform (card 6a209d65)

## Phase 1: Pick up
- [x] Pull master
- [x] Read card + CONTRIBUTING + art-render-contracts + wizard-tab-conventions
- [x] Worktree + branch + push
- [x] uv sync --extra dev

## Phase 2: Research
- [x] Read visual_reference_extractor.py / visual_reference.py / character_portraits.py
- [x] Read stages.run_visual_refs
- [x] Read theme.json shape (legendary_characters, notable_cards, creature_types{setting_specific,standard_mtg}, draft_archetypes, special_constraints)
- [x] Read archetypes endpoints (editable-table pattern) + helpers (guarded_ai, _bus_poller, _stage_state_base, _coerce_candidates_payload)
- [x] Read existing wizard_visual_refs.js (read-only scaffold w/ TODO endpoints)
- [x] Research MTG artist count per set (~70-90 modern; card wants FEWER, >=10 cards/artist)

## Phase 3: Design
- [x] Approach below

## Phase 4: Implement
- [x] Rework visual_reference_extractor.py: transform from theme.json structured data; add artists + set_art_direction
- [x] New prompt templates (transform-oriented; artists; set art direction)
- [x] stages.run_visual_refs: swap internals to write visual-references.json (+ set_art_direction) + artists.json
- [x] server.py: /api/wizard/visual_refs/{state,refresh,refresh-artists,refresh-set-direction,save}
- [x] wizard_visual_refs.js: full editable table + artist directory + set-wide direction
- [x] CLAUDE.md update

## Phase 5: Verify
- [x] ruff check / format
- [x] python -c "import mtgai"
- [x] pytest (ignore only test_finalize::test_manual_errors_surfaced)
- [x] new tests (transform, artist parse, schema shape)

## Phase 6: Review & ship
- [x] /review + fix findings
- [x] commit + push
- [ ] STOP (no merge, no worktree removal, no Trello)

## Design

### Transform, not re-extract
`generate_visual_references` becomes a transform over theme.json structured data:
- legendary_characters (name/colors/role/type/rarity) -> richly-painted art-direction prose per character (age, build, height, face, hair/facial hair, skin, clothing/armor, equipment, palette, demeanor, distinguishing features). Fill gaps where theme is thin.
- creature_types.setting_specific -> art-direction prose
- notable_cards -> entities where they name a place/artifact/landmark/creature
- factions/landmarks: theme short-schema has none structured; LLM infers from flavor_description prose + special_constraints (transform of prose it already holds, plus gap-fill). Preserve flux_term_replacements + visual_motifs.
The LLM is GIVEN the theme's existing painted text and told to ENRICH/normalize into consistent art-direction prose, not re-invent.

### Artists (new step)
`generate_artists(set_size)` -> artists.json `{"artists":[{name,style_prompt}]}`. Count = clamp(round(set_size/18), 8, 20) (>=10 cards/artist, lean fewer). Made-up names, MTG-flavored style prompts.

### Set-wide art direction (final step)
`generate_set_art_direction(theme)` -> prose string stored as visual-references.json["set_art_direction"].

### Endpoints
- GET  /api/wizard/visual_refs/state -> {refs, artists, set_art_direction, has_content, artist_count_target, ...base}
- POST /api/wizard/visual_refs/refresh -> regenerate the dictionary (entities+motifs+flux+set_art_direction), guarded_ai
- POST /api/wizard/visual_refs/refresh-artists -> regenerate artists only, guarded_ai
- POST /api/wizard/visual_refs/save -> persist edited refs (incl set_art_direction) + artists; _heal_failed_stage; navigate_to
All AI endpoints log_dir -> art-direction/logs.
