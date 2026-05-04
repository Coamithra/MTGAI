# Tracker: fix/ai-provenance

Card: [Persist 'AI generated' provenance tag on constraints + card requests](https://trello.com/c/Vbx7kyYW) (`69f882c3`)

## Phase 1: Pickup
- [x] Pull latest master
- [x] Read the card description
- [x] Move card to Doing
- [x] Create worktree + branch (`fix/ai-provenance`)
- [x] Push branch upstream
- [x] Write tracker doc

## Phase 2: Research
- [ ] Read `backend/mtgai/pipeline/theme_extractor.py` — JSON subcalls + emission
- [ ] Find theme schema (likely `mtgai/models/` or in extractor itself)
- [ ] Read theme wizard template (`/pipeline/theme` page)
- [ ] Read theme wizard JS (badge rendering, edit hooks)
- [ ] Find save/load endpoints for theme.json
- [ ] Trace where constraints + card_requests round-trip

## Phase 3: Design
- [x] Sketch schema changes (per-item `source` field)
- [x] Decide: client-side dirty tracking via `data-ai-generated` (already in place)
- [x] List file-by-file edits

**Design** (final):

Persisted shape in `theme.json` per the spec:
```
{ "constraints": [{ "text": "...", "source": "ai" | "human" }, ...],
  "card_requests": [{ "text": "...", "source": "ai" | "human" }, ...] }
```

- `theme.js`
  - `populateFromTheme()`: normalize each item — strings load as `human`, objects pass `source === "ai"` to addConstraint/addCardRequest
  - `collectThemeData()`: emit each row as `{text, source}` based on its `data-ai-generated` attribute
  - `addConstraint` / `addCardRequest` / `clearAiBadge`: unchanged (already wired)
- `skeleton/generator.py` `SetConfig`: add a field_validator on `constraints`/`card_requests`/`special_constraints` that accepts `str | {text, source}` and normalizes to `str`. Keeps server consumers (skeleton, card_gen, mechanic_gen, ai_review) working without per-call changes.

Server endpoint `/api/pipeline/theme/save` is a passthrough; no change needed.

Out of scope: server-side source-of-truth provenance comparison (spec allows client-side); changing the theme_extractor wire format (still emits bare strings).

## Phase 4: Implement
- [ ] Schema: add `source: Literal["ai", "human"]` per item
- [ ] Extractor: emit `source: "ai"` from JSON subcall results
- [ ] Persist: save/load round-trip preserves field
- [ ] UI: badge driven by `source == "ai"`; flips to human on edit
- [ ] Manually-added rows default to `human`
- [ ] Update CLAUDE.md if a contract changed

## Phase 5: Verify
- [x] `ruff check` on changed files: clean
- [x] `ruff format` on changed files: clean
- [x] `python -c "import mtgai"` smoke: clean
- [x] `pytest` (--ignore=tests/test_config.py for pre-existing pydantic_settings missing import): 782 passed
- [ ] Manual smoke for the user (UI behaviour can't be unit-tested — see "Manual Verification" below)

### Manual Verification
The user should walk through:
1. Theme wizard → upload a setting / paste prose → run extraction → AI-tagged constraints + card-requests appear
2. Save Theme → reload page → constraints + card-requests still show "AI" badges
3. Edit one AI-tagged row → badge drops on first keystroke
4. Add a new manual row → no badge ever
5. Save again → reload → only untouched AI rows still have badges; edited rows don't; manually-added rows don't

## Phase 6: Review & Ship
- [ ] Commit
- [ ] /review
- [ ] Pull master, resolve any conflicts
- [ ] Merge to master
- [ ] Clean up worktree + branch
- [ ] Delete tracker
- [ ] Move card to Done
- [ ] Comment on card with summary
