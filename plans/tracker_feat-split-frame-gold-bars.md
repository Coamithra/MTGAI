# Tracker: feat/split-frame-gold-bars

Card: 6a2881ba — Two-color split frames: gold title/type bars + gold P/T box (canonical hybrid look)

## Phase 1: Pick Up the Card
- [x] Claim card (two-phase handshake, claim 421924ed — only claimant)
- [x] Pull latest master
- [x] Read the card
- [x] Create worktree and branch (.trees/feat/split-frame-gold-bars)

## Phase 2: Research
- [x] Read generate_two_color_frames.py in full (_clean_bars, _mono_split_blend, _build_pt_box)
- [x] Read layout.py pt_box_path + card_renderer._load_pt_box fallback
- [x] Confirm m15FrameM bar zones are clean/text-free and geometry-aligned (same Card Conjurer family)
- [x] Decide P/T approach: pt_box_path remap to m15PTM + delete the 10 per-pair P/T assets
- [x] Check tests covering frame/pt resolution (tests/test_rendering_frames.py)

## Phase 3: Design
- [x] Approach: _clean_bars pastes m15FrameM bars (drop _mono_split_blend); pt_box_path maps
      WUBRG-pair keys to m15PTM (AW/lw untouched); script stops writing P/T; delete 10 PT PNGs;
      regen 10 frames; update tests + CLAUDE.md + learnings doc

## Phase 4: Implement
- [x] Modify _clean_bars to paste bar zones from m15FrameM (deleted _mono_split_blend/_build_pt_box)
- [x] pt_box_path remap + _load_pt_box docstring; git rm 10 m15PT<PAIR>.png
- [x] Update tests (pt path mapping, gold-bar pixel regression test)
- [x] Update CLAUDE.md + learnings/colored-artifact-frames.md
- [x] Re-run generate script for all 10 pairs (19-32 source cards each, all wrote)
- [ ] Commit regenerated PNGs

## Phase 5: Verify
- [x] ruff check + format (clean)
- [x] pytest (2604 passed, incl. new gold-bar pixel test for all 10 pairs)
- [x] Render WU legend + RG non-legend — gold bars + gold P/T over split body, matches
      Senate Guildmage convention (output/frame_compare/ in worktree)
- [x] Eyeball all 10 regenerated frames (montage; split edges + gold bars on all)
- [x] Spot-check diff

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review, fix findings
- [ ] Pull master, re-run lint+tests
- [ ] PR + self-merge
- [ ] Clean up worktree/branch
- [ ] Delete tracker
- [ ] Move card to Done + summary comment
- [ ] Follow-up cards if needed
- [ ] Overview to user
