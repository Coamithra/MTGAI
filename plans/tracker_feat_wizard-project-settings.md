# Tracker: feat/wizard-project-settings

Card: [Wizard UI: Project Settings tab + Start kickoff](https://trello.com/c/nFnduFre) (69f9e0f6)
Plan: plans/wizard-ui-redesign.md (§6, §9)

## Phase 1: Pick Up
- [x] Pull latest master
- [x] Read card + design doc
- [x] Move card to Doing
- [x] Create worktree + branch

## Phase 2: Research
- [x] Read current wizard shell (server.py, wizard.py, wizard.html, wizard.js)
- [x] Read trimmed Settings page (templates/settings.html, settings.js)
- [x] Read theme_extractor.py + theme.json — fields to migrate: name/set_size/mechanic_count
- [x] Read PipelineConfig + StageReviewMode + per-set settings.toml schema
- [x] Read AI mutex / ai_lock + extraction_run.py for SSE conventions
- [x] Identified presets / profiles endpoints under /api/settings/* (apply / save / load / global)
- [x] Findings summarized inline in conversation

## Phase 3: Design
- [x] Settings.toml grows [set_params] [theme_input] [break_points]; profiles save excludes set_params + theme_input
- [x] No new project-creation endpoint — POST /api/runtime/sets already handles it
- [x] Cascade-clear scope-down: pre-Start = freely editable; post-Start = read-only with hint pointing at §9 card
- [x] Theme tab in v1: navigate after Start; global progress strip shows extraction; Theme tab populates from theme.json once worker writes it on done
- [x] Worker variant writes theme.json on done — assembled from theme_text + constraints + card_suggestions

## Phase 4: Implement
- [x] settings.toml: added [set_params] [theme_input] [break_points]; profile saves strip set_params + theme_input
- [x] Migrate-on-load: pre-Project-Settings settings.toml gets name/set_size/mechanic_count lifted from theme.json on first get_settings()
- [x] Backend endpoints (all in mtgai/pipeline/server.py):
  - [x] GET /api/wizard/project — full project payload + registry slice + active-extraction flag
  - [x] POST /api/wizard/project/params — live-apply name/mechanic_count; size gated post-Start
  - [x] POST /api/wizard/project/theme-input — captures upload_id + metadata; gated post-Start
  - [x] POST /api/wizard/project/models — single-stage diff (kind=llm|image|effort)
  - [x] POST /api/wizard/project/breaks — single-stage toggle, rejects always_review
  - [x] POST /api/wizard/project/preset/apply — pulls preset, preserves per-set values
  - [x] POST /api/wizard/project/preset/save — strips per-set fields via profile_only=True
  - [x] POST /api/wizard/project/start — extracts (worker writes theme.json on done) or just navigates
- [x] wizard_project.js — Set parameters / Theme input / Break points / Apply preset / Models / Start
- [x] wizard.html: load wizard_project.js
- [x] Removed renderProjectTab placeholder from wizard_stage.js
- [x] wizard_theme.js: dropped name/set_size/mechanic_count round-trip on save
- [x] CSS for new sections in wizard.css (replaces .wiz-project-placeholder)
- [x] Cascade-clear scaffold deferred to §9 card (set_size + theme_input read-only post-Start with hint)
- [x] Updated CLAUDE.md (settings module + wizard module)

## Phase 5: Verify
- [x] `ruff check` clean for touched files (2 pre-existing N806 warnings on `DONE` sentinel ignored)
- [x] `ruff format` clean for touched files
- [x] `python -c "import mtgai"` smoke
- [x] `pytest` — 966 passed (added 27 new tests: 8 schema, 19 endpoints; 945→966)
- [x] Manual API smoke: GET payload + POST params/breaks/models/start round-trip work correctly
- [x] Migrate-on-load verified: ASD's settings.toml picked up "Anomalous Descent" from theme.json
- [ ] **Needs human eyeball**: actual browser-rendered Project Settings form (Chrome extension wasn't connected during smoke)

## Phase 6: Review & Ship
- [ ] Commit
- [ ] /review and fix findings
- [ ] git pull origin master into branch, resolve conflicts
- [ ] Re-run lint + tests
- [ ] Merge to master + push
- [ ] Worktree cleanup
- [ ] Move card to Done + comment with summary
- [ ] Tracker doc deleted (this file)
