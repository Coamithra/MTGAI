# Tracker: refactor/prompt-cache-structural

Card: **Prompt caching: migrate structural stages to cached system blocks** (6a1ef90d)
Follow-up LOW tier from `plans/prompt-caching-optimization.md` (git a6df092 §4).

Pattern (from card_gen reference): bulk STATIC context → ONE cached system block;
per-call DYNAMIC content stays in the user message. `system_blocks=[(base, True), (static_ctx, True)]`.
Cap: ≤4 cache_control markers (tools + system blocks + optional last-user). No-op on llamacpp.

## Phase 1: Pick Up
- [x] Pull latest master
- [x] Read card + original design doc (a6df092 §4)
- [x] Move card to Doing
- [x] Create worktree + branch + push

## Phase 2: Research / Audit
- [x] archetypes — static already in `archetype_system.txt` (system_prompt, cached) → **no change**
- [x] skeleton relabel pass 1 — static in `skeleton_relabel_system.txt`; `stream_text` caches system → **no change**
- [x] skeleton knobs — static in USER → **migrate**
- [x] reprints select+place — static + ~350-card pool in USER → **migrate**
- [x] lands basics+investigation — static set context in USER → **migrate**
- [x] Confirm transport `system_blocks`/`cache_user` already shipped (commit 56de967)
- [x] Inspect existing tests (stubs read kwargs; some assert builder return shapes)

## Phase 3: Design
- [x] Skeleton knobs: split `skeleton_knobs_user.txt` → context block (cached system #2) + short trigger user; `tune_knobs` uses `system_blocks`
- [x] Reprints: `_build_select_user`/`_build_place_user` split into (context_block, trigger); call sites use `system_blocks`
- [x] Lands: `_build_basics_prompt`/`_build_investigation_prompt` return (system_blocks, user); call sites updated

## Phase 4: Implement
- [x] skeleton_knobs_tuner.py + templates (new skeleton_knobs_context.txt, slimmed user.txt)
- [x] reprint_selector.py (select + place split into context/trigger)
- [x] land_generator.py (basics + investigation -> (system, context, user))
- [x] Update CLAUDE.md prompt-caching note

## Phase 5: Verify
- [x] ruff check . (clean; 19 pre-existing format-only files untouched, separate card)
- [x] python -c "import mtgai" (OK)
- [x] pytest (full): 1563 passed (run via root .venv + PYTHONPATH; worktree has no venv)
- [x] Added migration unit tests (knobs/reprints/lands: static->cached block, dynamic->user)

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review, fix findings
- [ ] Pull master, resolve conflicts
- [ ] Re-run lint + tests
- [ ] Merge to master, push
- [ ] Clean up worktree + branch
- [ ] Delete tracker
- [ ] Move card to Done + comment
- [ ] Final overview to user
