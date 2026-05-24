# Tracker: feat/review-export (3A-2 review export command)

## Phase 1: Pick Up the Card
- [x] Pull latest master (branched from 321cbd7)
- [x] Read the card (description, comments)
- [x] Move card to Doing
- [x] Create worktree and branch + push upstream

## Phase 2: Research
- [x] Read review/cli.py (existing subcommand wiring + export stub at L545)
- [x] Read review/loaders.py (load_cards, load_cards_raw, CardFilter, sort)
- [x] Read review/decisions.py (review data source)
- [x] Read models/card.py (Card schema)
- [x] Read io/asset_paths.py + io/paths.py (renders live in <set_dir>/renders/<slug>.png)
- [x] Read tests/test_review/test_loaders.py + conftest.py (active-project test pattern: isolated_output)

## Phase 3: Design
- [x] Draft plan (plans/review-export.md)

## Phase 4: Implement
- [x] Create mtgai/review/exporters.py (export_csv, export_json, export_print)
- [x] Replace export stub in cli.py with a Typer sub-app (csv/json/print)
- [x] Update CLAUDE.md if new CLI entry point warrants it -> n/a (review CLI already documented broadly)

## Phase 5: Verify
- [x] ruff check + format changed files
- [x] python -c "import mtgai"
- [x] new test file passes
- [x] pytest tests/test_validation/ + tests/test_review/
- [x] spot-check diff

## Phase 6: Ship
- [x] Commit + push
- [x] /review (code-review skill) + fix findings
- [x] Pull master into branch
- [x] Re-run lint + tests
- [x] Merge to master + push
- [x] Remove worktree + branch
- [x] Delete plan + tracker
- [x] Move card to Done + comment
