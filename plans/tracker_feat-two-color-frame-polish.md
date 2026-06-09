# Tracker: feat/two-color-frame-polish

Cards: 6a2881ee (step 3: gradient two-color legendary crowns) + 6a2881fa (step 4: gold-frame render toggle), done together per user request.

## Phase 1: Pick Up the Card
- [x] Claim both cards — two-phase handshake (claim f079d9f1, earliest/only comments)
- [x] Pull latest master
- [x] Read the cards
- [x] Create worktree and branch

## Phase 2: Research
- [x] Read card_renderer._load_legendary_crown + CROWN_PAIR_MAP
- [x] generate_two_color_frames.py::_mono_split_blend does NOT exist (card drift) — implemented gradient mask fresh
- [x] Read colors.frame_key_for_identity / two_color_key + layout.frame_path/pt_box_path
- [x] Setting lives in SetParams (like art_versions_per_card); live-apply, no cascade
- [x] Crowns share 2882×654 geometry — masked composite safe

## Phase 3: Design
- [x] Draft approach (file-by-file)
- [x] Check reusable patterns

## Phase 4: Implement
- [x] Step 3: _blend_pair_crown gradient synthesis (CROWN_SEAM_FRACTION 0.18), committed PNGs as fallback
- [x] Step 4: SetParams.two_color_frame split|gold; determine_frame_key collapse; crown routing; endpoint validation; Project Settings select
- [x] Update CLAUDE.md contracts

## Phase 5: Verify
- [x] ruff check + format (clean, via root venv — worktree can't uv sync, relative llmfacade path)
- [x] smoke import (implicit in pytest)
- [x] pytest — 2614 passed
- [x] Rendered WU legendary both modes + raw WU/BR blended crowns — eyeballed, correct

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review, fix findings
- [ ] Pull master into branch
- [ ] Re-run lint + tests
- [ ] PR + self-merge
- [ ] Clean up worktree/branch
- [ ] Delete tracker
- [ ] Move cards to Done + comment
- [ ] Follow-up cards if needed
- [ ] Final overview to user
