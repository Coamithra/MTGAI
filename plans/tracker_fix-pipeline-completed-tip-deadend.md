# Tracker: fix/pipeline-completed-tip-deadend

Card 6a259529 — Pipeline dead-ends at a COMPLETED review-eligible tip stage.

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card
- [x] Move card to Doing
- [x] Create worktree and branch

## Phase 2: Research
- [x] Read engine.resume() + current_stage/next_pending_stage machinery
- [x] Read server.py wizard_advance + project_open
- [x] Read wizard_art_gen.js paintFooter + wizard_util.js shared footer helpers
- [x] Identify root cause + design options

## Phase 3: Design
DESIGN:
- engine.resume(): when current_stage() is COMPLETED (not paused) AND overall_status==PAUSED
  AND next_pending_stage() exists, advance current_instance_id to that pending stage and
  call self.run() instead of no-opping. _run_loop already skips COMPLETED and runs the first
  pending stage. Keeps the normal paused_for_review path untouched.
- art_gen/state endpoint: also return overall_status + has_pending_successor so the footer
  can decide. paintFooter: render the Next-step button when status==='completed' AND latest
  tab AND overall PAUSED AND a pending successor exists.

## Phase 4: Implement
- [x] engine.resume() handles completed-tip + pending-successor
- [x] server wizard_advance no false success (409 when nothing to advance)
- [x] art_gen/state exposes overall_status + can_advance
- [x] footer surfaces Next-step button on completed+canAdvance
- [x] CLAUDE.md — no documented contract changed (no edit needed)

## Phase 5: Verify
- [x] ruff check + format (clean)
- [x] smoke import (ok)
- [x] pytest full suite: 2068 passed (test_config.py pre-existing missing-dep skip)
- [x] advance endpoint contract tests (no false success)

## Phase 6: Ship
- [ ] commit + push
- [ ] /review + fix findings
- [ ] pull master into branch
- [ ] PR + self-merge
- [ ] clean up worktree
- [ ] delete tracker
- [ ] move card to Done + comment
