# Tracker: fix/theme-section-stuck-strip

Card 6a245330 — Theme section Refresh AI leaves progress strip stuck.

## Phase 1: Pick Up
- [x] Pull latest master
- [x] Read card
- [x] Move card to Doing
- [x] Create worktree + branch + push

## Phase 2: Research
- [x] Read stream_section_extraction (theme_extractor.py)
- [x] Read _stream_section_refresh.worker (server.py)
- [x] Read handlePhaseEvent + phaseDisplayLabel (wizard.js)
- [x] Read test_phase_telemetry.py

## Phase 3: Design
- [x] Emit terminal phase=done (done + cancelled branches)
- [x] Human-readable title for json_subcall path

## Phase 4: Implement
- [x] theme_extractor.py changes
- [x] wizard.js prefers data.title
- [x] regression tests

## Phase 5: Verify
- [x] ruff check + format
- [x] import smoke
- [x] pytest (2029 passed, 1 skipped)
- [x] logical wizard.js sanity

## Phase 6: Ship
- [ ] commit + push
- [ ] /review + fix findings
- [ ] pull master into branch
- [ ] PR + self-merge
- [ ] clean worktree
- [ ] delete tracker
- [ ] card to Done + comment
