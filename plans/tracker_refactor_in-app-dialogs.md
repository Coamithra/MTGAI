# Tracker: refactor/in-app-dialogs

Card 6a231f78 — Replace native window.confirm/alert/prompt with an in-app modal dialog system.

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, call sites)
- [x] Move card to Doing
- [x] Create worktree and branch + push

## Phase 2: Research
- [x] Grep all native dialog call sites in static/
- [x] Find existing modal pattern (wiz-modal-overlay / openCascadeModal in wizard.js)
- [x] Confirm which pages are live (wizard.html + settings.html; pipeline.html + configure.html are DEAD — not served)
- [x] Read runAiAction confirm hook (already async)
- [x] Read trickier call sites (save-preset prompt, in-progress confirm)

## Phase 3: Design
- [x] Draft approach (wizard_dialog.js self-contained module, own injected CSS)
- [x] Decide dead-code handling (pipeline.js/configure.js) — delete dead templates+JS
- [x] Align with user

## Phase 4: Implement
- [x] Create wizard_dialog.js (MTGAIDialog.confirm/alert/prompt -> Promise)
- [x] Include in wizard.html
- [x] Migrate wizard_util.js runAiAction confirm hook
- [x] Migrate wizard_project.js (discard, apply-preset, save-preset prompt, delete-preset, in-progress)
- [x] Migrate wizard_archetypes.js / wizard_mechanics.js / wizard_theme.js confirms
- [x] Migrate wizard.js native alerts (reportError network path) — none found; toast already used
- [x] Delete dead pipeline.html/pipeline.js + configure.html/configure.js
- [x] Update CLAUDE.md if a new convention is introduced

## Phase 5: Verify
- [x] grep clean (no window.confirm/alert/prompt in live wizard JS)
- [x] ruff (N/A — JS only; no python changed)
- [x] python -c "import mtgai" (templates removed — confirm no python references break)
- [x] pytest (check no test references the deleted templates/js)
- [x] Manual smoke: serve, drive preset-apply + a cascade-delete via DOM buttons
- [x] Spot-check diff

## Phase 6: Review & Ship
- [x] Commit + push
- [x] /review, fix findings
- [x] Pull master, resolve conflicts
- [x] Re-run lint + tests
- [x] PR + self-merge
- [x] Clean up worktree + branch
- [x] Delete tracker
- [x] Move card to Done + comment
- [x] Follow-up cards if needed
- [x] Final overview to user
