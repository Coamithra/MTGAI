# Tracker: feat/crown-underlay-title-bar

Card 6a2881df — Frame polish, step 2: Shrink legendary crown underlay to end at title bar

## Phase 1: Pick Up the Card
- [x] Claim the top card (two-phase handshake — claim ce304a3f, won)
- [x] Pull latest master
- [x] Read the card
- [x] Create worktree and branch

## Phase 2: Research
- [ ] Read `_make_crown_underlay` in card_renderer.py
- [ ] Read `_load_title_mask` / m15MaskTitle.png usage
- [ ] Find the title bar's lowest opaque row coordinate
- [ ] Check output/frame_compare/ scratch setup + real-card reference

## Phase 3: Design
- [ ] Decide how to compute/cache the underlay bottom edge
- [ ] Check for reusable patterns

## Phase 4: Implement
- [ ] End underlay rect at title bar bottom edge

## Phase 5: Verify
- [ ] ruff check / format
- [ ] Smoke import
- [ ] pytest
- [ ] Render a legendary card at full res, eyeball vs real card (Vaevictis Asmadi M19)
- [ ] Spot-check the diff

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review, fix findings
- [ ] Pull master into branch
- [ ] Re-run lint + tests
- [ ] PR + self-merge
- [ ] Clean up worktree + branch
- [ ] Delete tracker
- [ ] Move card to Done + comment
- [ ] Follow-up cards if needed
- [ ] Overview to the user
