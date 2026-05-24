# Tracker: feat/tc4-visual-refs (TC-4 Visual Reference Extraction Stage)

Card: `69f86d68` — TC-4: Visual reference extraction stage

## Phase 1: Pick Up the Card
- [x] Read the card (description, comments)
- [x] Move card to Doing
- [x] Create worktree and branch from master (db2073e)

## Phase 2: Research
- [x] Read TC-3 archetype_generator.py (mirror target)
- [x] Read stages.py (STAGE_RUNNERS / STAGE_CLEARERS)
- [x] Read pipeline/models.py (STAGE_DEFINITIONS)
- [x] Read existing art/visual_reference.py (consumer contract)
- [x] Read art/character_portraits.py (consumer contract)
- [x] Read existing ASD visual-references.json (real shape)
- [x] Read model_settings.py (LLM assignments, break points)
- [x] Read wizard.py (auto tab per stage)
- [x] Inspect theme.json input shape
- [x] Read generate_with_tool signature
- [x] Read conftest.py (isolated_output fixture)

## Phase 3: Design
- [x] Write design plan

## Phase 4: Implement
- [x] New: backend/mtgai/art/visual_reference_extractor.py
- [x] New: backend/mtgai/pipeline/prompts/visual_references_system.txt
- [x] New: backend/mtgai/pipeline/prompts/visual_references_user.txt
- [x] Register stage in pipeline/models.py STAGE_DEFINITIONS (after archetypes)
- [x] Register runner in pipeline/stages.py STAGE_RUNNERS + run_visual_refs
- [x] Register clearer in pipeline/stages.py STAGE_CLEARERS + clear_visual_refs
- [x] Add LLM assignment defaults in model_settings.py
- [x] New: backend/tests/test_visual_reference_extractor.py
- [x] Update CLAUDE.md (new stage)

## Phase 5: Verify
- [x] ruff check . (clean)
- [x] ruff format . (clean)
- [x] python -c "import mtgai"
- [x] pytest new test file
- [x] pytest tests/test_validation/
- [x] full pytest --ignore=tests/test_config.py (mocked LLM only)
- [x] spot-check diff

## Phase 6: Review & Ship
- [x] Commit + push branch
- [x] /review (code-review)
- [x] Fix findings
- [x] Pull master into branch
- [x] Merge to master + push
- [x] Remove worktree + branch
- [x] Delete tracker + plan
- [x] Move card to Done
- [x] Comment on card
