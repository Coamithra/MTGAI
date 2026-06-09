# Tracker: feat/supervisor-auto-resume

Card: Supervisor: full unattended server-side reopen + retry resume (6a273dc1c1a5d5232b2d767a)

## Phase 1: Pick Up the Card
- [x] Claim the card (two-phase handshake — won claim 2c98d445)
- [x] Pull latest master
- [x] Read the card
- [x] Create worktree and branch

## Phase 2: Research
- [ ] Read supervisor.py + heartbeat.py
- [ ] Read /api/project/open + cleanup_orphan_running_stages
- [ ] Read /api/wizard/instance/retry + engine.retry_current()
- [ ] Trace the supervised child boot path + serve CLI flags
- [ ] Summarize findings

## Phase 3: Design
- [ ] Draft approach
- [ ] Check reusable patterns
- [ ] (proceed — no approval gate needed per quick-ship default)

## Phase 4: Implement
- [ ] Persist last-opened .mtg path on project open
- [ ] serve --supervised --auto-resume flag plumbing
- [ ] After auto-restart: child re-opens .mtg via /api/project/open
- [ ] Auto-fire failed-stage retry via /api/wizard/instance/retry
- [ ] Per-stage retry ceiling / crash-resume loop guard
- [ ] Update CLAUDE.md

## Phase 5: Verify
- [ ] ruff check + format
- [ ] python -c "import mtgai"
- [ ] pytest
- [ ] Manual smoke notes

## Phase 6: Review & Ship
- [ ] Commit + push
- [ ] /review + fix findings
- [ ] Pull master, resolve conflicts
- [ ] Re-run lint + tests
- [ ] PR + self-merge
- [ ] Clean up worktree
- [ ] Delete tracker
- [ ] Move card to Done + comment
- [ ] Overview to user
