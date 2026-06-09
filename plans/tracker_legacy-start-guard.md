# Tracker: fix/legacy-start-guard

Card 6a285a04 — Legacy POST /api/pipeline/start re-runs a PAUSED_FOR_REVIEW stage.

## Phase 1: Pick Up
- [x] Claim card (two-phase handshake; sole claim dd57f5c9)
- [x] Pull master
- [x] Read card + CONTRIBUTING + CLAUDE.md re-entrant section
- [x] Worktree + branch (.trees/legacy-start-guard, fix/legacy-start-guard, pushed)

## Phase 2: Research
- [x] Read legacy /start (server.py:7993) + _kickoff_pipeline_engine docstring (server.py:2436)
- [x] Confirm no callers: JS (only /state used), tests (none), docs (none)
- [x] Identify guards needed: PAUSED -> 409, RUNNING orphan -> 409, no clobber non-PAUSED/FAILED state

## Phase 3: Design
- [x] Route legacy /start through the same guards as _kickoff_pipeline_engine
  - PAUSED -> 409 "use resume instead" (don't re-run paused stage)
  - RUNNING (orphan) -> 409
  - FAILED -> reuse + update review modes (resume from failure)
  - COMPLETED/CANCELLED/NOT_STARTED/no-state -> reuse existing if present (no clobber), else create fresh

## Phase 4: Implement
- [x] Edit start_pipeline in server.py

## Phase 5: Verify
- [x] ruff check + format
- [x] smoke import
- [x] regression tests (PAUSED 409, RUNNING 409, no-clobber COMPLETED, FAILED reuse, fresh create)
- [x] full pytest

## Phase 6: Ship
- [x] commit + push
- [x] /review + fix findings
- [x] pull master, merge
- [x] PR + self-merge
- [x] cleanup worktree/branch, delete tracker
- [x] card -> Done + summary comment
