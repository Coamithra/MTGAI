# Tracker: feat/art-gen-click-zoom

Card 6a29abdc — Art gen tab: image click-to-expand undiscoverable.

## Phase 1: Pick Up
- [x] Claim card (two-phase handshake)
- [x] Pull latest master
- [x] Read card + relevant code
- [x] Create worktree + branch + push

## Phase 2/3: Research + Design
- [x] Read wizard_art_gen.js (tiles, bindVersionTile, versionHtml, CSS)
- [x] Read wizard_rendering.js click-to-zoom pattern (wrap.onclick, cursor:zoom-in)
- [x] Confirm onRepick semantics (pick with 1 version = no-op state choice)

## Phase 4: Implement
- [ ] CSS: .wiz-ag-zoom always visible at opacity 0.45, full on hover/focus
- [ ] CSS: single-version tile cursor:zoom-in on image
- [ ] bindVersionTile: single version -> image click opens lightbox; multi -> click=pick
- [ ] versionHtml: mark single-version tiles (class) + correct title/cursor
- [ ] Re-evaluate on re-render (binding happens per paint, count-aware)

## Phase 5: Verify
- [ ] node --check the JS
- [ ] ruff check . (backend)
- [ ] pytest (backend)
- [ ] python -c "import mtgai"
- [ ] Self-review diff

## Phase 6: Ship
- [ ] Commit + push
- [ ] /review + fix findings
- [ ] Pull master into branch
- [ ] PR + self-merge
- [ ] Clean up worktree/branch
- [ ] Delete tracker
- [ ] Move card Done + comment + manual-verify checklist
