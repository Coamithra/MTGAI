# 3A-2: Build review export command (CSV/JSON/print)

## Context
`review export <format>` moves finished card data out of the pipeline so it can be
opened in a spreadsheet, re-imported as full JSON, or uploaded to a print service.
Three formats are in scope; Cockatrice XML is explicitly deferred to Phase 5.

Card data is loaded via the existing `mtgai.review.loaders.load_cards(set_code)`
(parses every `<asset_folder>/cards/*.json` through the Pydantic `Card` model and
sorts by collector_number). Renders live at `<asset_folder>/renders/<slug>.png`
(see `mtgai/rendering/card_renderer.py` L943 and `io/paths.render_path`).

## Design

### New module: `mtgai/review/exporters.py`
Pure functions, no I/O side effects beyond the requested file/dir writes. All take
an explicit `cards: list[Card]` (and for print, an explicit source dir) so they are
trivially unit-testable without an active project. The CLI is the only layer that
touches `load_cards` / `set_artifact_dir`.

- `CSV_COLUMNS: list[str]` — the flat column order.
- `card_to_row(card: Card) -> dict[str, str]` — flatten one card to CSV cell strings.
  - `color_identity` / `mechanic_tags` joined with `;` (no embedded commas).
  - bools rendered as `true`/`false`; `None` rendered as empty string; `cmc` as int
    when whole (`3` not `3.0`).
  - `oracle_text` newlines preserved (csv module quotes them correctly).
- `export_csv(cards, out_path: Path) -> int` — writes UTF-8 CSV (one header row +
  one row per card) using the stdlib `csv` module with `newline=""`. Returns count.
- `export_json(cards, out_path: Path) -> int` — writes a single JSON file whose
  top-level value is `list[Card.model_dump(mode="json")]` (per card description).
  `mode="json"` so datetimes/enums serialize. Returns count.
- `export_print(cards, renders_dir: Path, out_dir: Path) -> PrintExportResult` —
  copies each card's render PNG into a flat `out_dir`. Resolution order per card:
  1. `card.render_path` if set and the file exists (joined under renders_dir's
     parent / treated as relative-or-absolute);
  2. else `renders_dir/<slug>.png` where slug = `card_slug(collector_number, name)`.
  Missing renders are collected as `missing` (not fatal). Returns a small result
  object: `copied: list[str]`, `missing: list[str]`. Flat dir = same filename as the
  source PNG (the slug), so it's upload-ready.

`PrintExportResult` is a Pydantic BaseModel (project convention).

### CLI: replace the `export` stub in `mtgai/review/cli.py`
The current `@app.command("export")` stub becomes a Typer sub-app
`export_app = typer.Typer(...)` mounted via `app.add_typer(export_app, name="export")`,
with three commands mirroring existing subcommand style (`--set/-s`, `--out/-o`,
Rich console feedback, `typer.Exit(1)` on error):

- `export csv  --set ASD --out cards.csv`
- `export json --set ASD --out cards.json`
- `export print --set ASD --out print/`

Each loads cards via `load_cards(set_code)`; if empty, prints a yellow warning and
exits 0 (nothing to export is not an error). `print` resolves `renders_dir =
set_artifact_dir()/"renders"`, creates `out_dir`, and reports copied/missing counts.
`NoAssetFolderError` (no project open) is caught and reported as a red error +
exit 1, matching how other read paths surface it.

### Out of scope
- Cockatrice XML (deferred to Phase 5 per card).
- Tabletop Simulator deck sheets.
- Any re-import / round-trip loader (export only).
- Filtering flags on export (export the whole set; filtering is `review list`'s job).

## Tests — `backend/tests/test_review/test_exporters.py` (no real model)
- `card_to_row`: list joins, None->"", bool->true/false, whole-cmc->int, multi-color.
- `export_csv`: header matches CSV_COLUMNS; row count; round-trips back through
  `csv.DictReader`; oracle_text with newline survives; UTF-8 content.
- `export_json`: top-level is a JSON list; len matches; each entry re-parses through
  `Card(**entry)` cleanly; enum/datetime serialized.
- `export_print`: copies present renders by slug; respects `card.render_path`;
  records missing; flat output dir; idempotent re-run.
- Use the local `_make_card` helper + `tmp_path`. No LLM, no active project needed
  for the exporter unit tests (CLI wiring exercised separately if cheap).
