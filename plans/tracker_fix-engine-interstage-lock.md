# Tracker: fix/engine-interstage-lock

Card 6a2869af — Engine inter-stage window (snapshot + span insertion) runs lock-free between stages

## Phase 1: Pick Up the Card
- [x] Claim card (two-phase handshake; claim b1144bec won)
- [x] Pull latest master
- [x] Read the card (description + comments)
- [x] Create worktree and branch

## Phase 2: Research
- [x] Inspect draft commit 2468ff7 on fix/gate-lock-flag, diff vs current master
- [x] Read engine.py _run_loop / _snapshot_instance_output / _handle_rerun
- [x] Read history.py invariant comment
- [x] Read ai_lock.py (non-reentrancy, run_id, cancel semantics)
- [x] Read stages.py runner lock usage (PR #130 shipped: gates flag under hold)
- [x] Check existing engine/history tests (test_gate_flag_lock.py, test_review_loop.py)
- [x] Summarize findings

## Phase 3: Design
- [x] Decide: ADAPT the draft. Its stages.py half already shipped (PR #130). Its
      engine half wrapped only the snapshot, inside _snapshot_instance_output.
      New design: one `ai_lock.hold(f"Finishing {stage.display_name}")` in
      _run_loop around BOTH _snapshot_instance_output + _handle_rerun, released
      before walking into the next stage (non-reentrancy: the next runner takes
      its own hold). Busy (endpoint won the sub-ms race) -> WARN + skip the
      snapshot only (degrades to from-live re-run, the existing best-effort
      contract); _handle_rerun ALWAYS runs (engine-owned in-memory state +
      pipeline-state.json — skipping it would orphan stamped flags and kill the
      regen loop). history.py docstring + CLAUDE.md updated to match.

## Phase 4: Implement
- [ ] Implement changes
- [ ] Update history.py invariant comment / CLAUDE.md if contract changes

## Phase 5: Verify
- [ ] ruff check . / ruff format .
- [ ] python -c "import mtgai"
- [ ] pytest (full suite)
- [ ] Add/extend unit tests for the lock-ownership seam
- [ ] Spot-check diff

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review and fix findings
- [ ] Pull master, re-test
- [ ] PR create + self-merge, fast-forward master
- [ ] Clean up worktree + branch
- [ ] Delete stale local branch fix/gate-lock-flag
- [ ] Delete tracker doc before final push
- [ ] Move card to Done + summary comment
- [ ] Follow-up cards if needed
