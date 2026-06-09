# Tracker: fix/art-prompt-entity-unify

## Phase 1: Pick Up the Card
- [x] Claim the top card — move it to Doing FIRST
- [x] Pull latest master
- [x] Read the card (description, comments)
- [x] Create worktree and branch

## Phase 2: Research
- [ ] Read visual_reference.py (get_visual_references substring match)
- [ ] Read prompt_builder.py (get_character_ref_paths DEPRECATED, generate_art_prompt)
- [ ] Read char_portraits.py (detect_recurring_entities, art_character_refs producer)
- [ ] Read card.py ArtCharacterRef model
- [ ] Read wizard_art_prompts.js + art_prompts endpoints (UI tile badges)
- [ ] Trace consumers of get_visual_references / art_character_refs
- [ ] Summarize findings

## Phase 3: Design
- [ ] Draft approach: unify appearance-text on art_character_refs
- [ ] UI: per-card entity chips on Art Prompts tab
- [ ] Check reusable patterns (cameo badge 6a274ae3)
- [ ] Align with user

## Phase 4: Implement
- [ ] Drive appearance-text from art_character_refs entity keys
- [ ] Keep one-card entity appearance text
- [ ] Surface tagged entities in API state
- [ ] Render per-tile entity badges in wizard_art_prompts.js
- [ ] (bonus) editable/removable tags
- [ ] Update CLAUDE.md if contracts change

## Phase 5: Verify
- [ ] ruff check / format
- [ ] smoke import
- [ ] pytest
- [ ] manual smoke if feasible
- [ ] spot-check diff

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review, fix findings
- [ ] pull master, resolve conflicts
- [ ] re-run lint + tests
- [ ] PR + self-merge
- [ ] cleanup worktree/branch
- [ ] delete tracker
- [ ] move card to Done + comment
- [ ] follow-up cards
- [ ] overview to user
