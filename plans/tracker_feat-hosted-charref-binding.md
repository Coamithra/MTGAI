# Tracker: feat/hosted-charref-binding

Card 6a2752e9 — "Hosted character-ref binding: interleave labeled reference images + name-based art prompts"
Depends on LLMFacade card 6a275322 (labeled/interleaved reference images) — being implemented in parallel.

## Phase 1: Pick Up the Card
- [x] Claim the card — moved to Doing
- [x] Pull latest master
- [x] Read the card + LLMFacade dependency card
- [x] Create worktree and branch (feat/hosted-charref-binding)

## Phase 2: Research
- [x] Map hosted image-gen path (image_generator.generate_image_hosted)
- [x] Map char-ref attach (character_portraits.attach_refs_to_cards) + ArtCharacterRef model
- [x] Map art-prompt authoring (prompt_builder.generate_art_prompt)
- [x] Confirm LLMFacade currently has only flat reference_images (dependency NOT yet landed)
- [x] Confirm ordering: art_prompts runs BEFORE char_portraits

## Phase 3: Design
- [x] Decision: Flux scope — user picked "hosted-only, ignore Flux for now" (name-based prompts everywhere; Flux degrades until 6a274df0)
- [x] Write plans/hosted-charref-binding.md
- [ ] Final align with user on plan

## Phase 4: Implement
- [x] No schema change — label derived from entity_key (shared entity_display_name helper)
- [x] Part 1: visual_reference.entity_display_name + get_named_entities; prompt_builder roster + system prompt flip
- [x] Per-card label assembly: image_generator._resolve_labeled_refs
- [x] Wire interleaved labeled refs into generate_image_hosted (LabeledImage, function-level import)
- [x] Thread ref_labels: generate_art_for_set -> generate_image -> generate_image_hosted
- [x] Update existing tests (visual_refs="" -> named_entities; _resolve_ref_paths monkeypatch)
- [x] New tests (visual_reference name helpers, roster, _resolve_labeled_refs, hosted labeled/unlabeled)
- [x] CLAUDE.md updated (art_prompts name-based + hosted interleaving)

## Phase 5: Verify
- [x] ruff check / format clean
- [x] python -c "import mtgai" OK
- [x] pytest: 2226 passed, 2 skipped (hosted-labeled tests await dependency); test_config.py pre-existing env error (pydantic_settings)
- [ ] BLOCKED: run the 2 skipped hosted tests once LLMFacade LabeledImage lands
- [ ] Manual smoke: a real Gemini generate_image with 2 labeled refs (post-dependency)

## Phase 6: Review & Ship
- [x] Commit + push branch (pre-dependency)
- [ ] WAIT for LLMFacade 6a275322 to merge to main, then re-verify
- [ ] /review + fix findings
- [ ] Pull master, resolve conflicts
- [ ] PR + self-merge (only AFTER dependency lands)
- [ ] Clean worktree/branch, delete plan + tracker
- [ ] Move card to Done + comment
