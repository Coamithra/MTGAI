# Tracker: feat/qa-bot

Card: QA Bot (6a23000b) — self-driving QA system that drives the wizard via claude-in-chrome,
finds bugs, logs them to Trello, farms fixes to subagents, and loops.

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments)
- [x] Move card to Doing
- [x] Create worktree and branch
- [x] Push branch
- [x] Tracker doc

## Phase 2: Research
- [x] How wizard saves .mtg (FS Access API picker — OS dialog, invisible to chrome; bypass needed)
- [x] Pipeline state seeding / skip-to-state (prefab system + StageState COMPLETED marking)
- [x] Server structure (cli.py serve, server.py app+routers), no existing debug flag
- [x] Model registry: gemma4-26b-iq2m + thinking_overrides=disabled
- [x] Existing prefab/debug system (use_prefab_cards/mechanics, DebugSettings)
- [x] Summarize findings

## Phase 3: Design
- [x] Draft approach (plans/qa-bot.md)
- [x] Check reusable patterns
- [x] Align with user — APPROVED: full system, full auto self-merge fixers, --debug flag gating

## Decisions (locked)
- Scope: FULL system (Part A app harness + Part B /qa-bot skill + orchestration/fix loop)
- Fix autonomy: full auto self-merge (fixers follow CONTRIBUTING end-to-end)
- Debug gating: `serve --debug` / MTGAI_DEBUG=1 mounts debug endpoints + wizard panel

## Phase 4: Implement
- [x] qa preset (model_settings.PRESETS)
- [x] debug_routes.py (state/quick-project/seed-stage/open-path/save-mtg)
- [x] serve --debug flag (cli.py) + mount (review/server.py)
- [x] wizard.html debug_enabled gate + wizard_debug.js panel
- [x] wizard_project.js save-button bypass
- [x] /qa-bot skill (SKILL.md + reference.md)
- [x] Update CLAUDE.md

## Phase 5: Verify
- [x] Lint (ruff check . clean; format clean)
- [x] Smoke import (mtgai + review.server)
- [x] Unit tests (debug_routes 9 pass; settings+pipeline 559 pass)
- [x] Manual smoke (debug on→routes+panel; off→404+no panel; real seed-stage vs transformers)

## Phase 6: Review & Ship
- [ ] Commit
- [ ] /review
- [ ] Pull master into branch
- [ ] Re-run lint + tests
- [ ] PR + self-merge
- [ ] Clean up worktree/branch
- [ ] Delete plan + tracker
- [ ] Move card to Done + comment
- [ ] Follow-up cards
- [ ] Overview to user
