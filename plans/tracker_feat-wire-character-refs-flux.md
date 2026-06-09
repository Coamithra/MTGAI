# Tracker: feat/wire-character-refs-flux

Card: Wire character refs into the local Flux/ComfyUI workflow (PuLID/IP-Adapter) — 6a274df0

## Phase 1: Pick Up the Card
- [x] Claim the top card — moved to Doing
- [x] Pull latest master
- [x] Read the card + comments
- [x] Create worktree and branch + push

## Phase 2: Research
- [x] Read `_apply_character_refs` stub + call chain (image_generator.py)
- [x] Confirm PuLID-Flux custom nodes installed (ComfyUI-PuLID-Flux present)
- [x] Confirm model files present (pulid_flux_v0.9.1.safetensors, antelopev2 insightface)
- [x] Read PuLID node API (PulidFluxModelLoader/InsightFaceLoader/EvaClipLoader/ApplyPulidFlux)
- [x] Read hosted ref path (generate_image_hosted) + _resolve_ref_paths
- [x] Read visual_reference helpers (legendary_characters = humanoid characters)
- [x] Check sibling cards: 6a27581d (Doing, appearance-text/entity unify) + 4OaKhQ5K (binding) own the name->appearance prompt half
- [x] Read existing tests (test_image_generator.py)

## Phase 3: Design
- [x] Draft approach (this file)
- [ ] Align with user on scope (prompting-half boundary)

## Phase 4: Implement
- [ ] `_upload_image_to_comfyui(path)` helper (/upload/image)
- [ ] PuLID node injection in `_apply_character_refs`
- [ ] `_resolve_flux_face_refs(card, set_dir)` — single humanoid-character ref, max 1
- [ ] Branch ref resolution on provider in `generate_art_for_set`
- [ ] Metadata: character_refs_applied true/false
- [ ] Update CLAUDE.md art note + remove stub TODO

## Phase 5: Verify
- [ ] ruff check / format
- [ ] python -c "import mtgai"
- [ ] pytest (update stub test + add graph-injection tests)
- [ ] (optional) live ComfyUI smoke test

## Phase 6: Ship
- [ ] commit + /review + merge master + lint/test + PR self-merge
- [ ] cleanup worktree + delete tracker
- [ ] card -> Done + comment + follow-ups
