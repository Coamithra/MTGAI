# Finalization UI

## Context

Card 6a209cc7. The `finalize` stage (`mtgai/review/finalize.py`) runs after AI
Review: it strips/injects reminder text, runs validation, auto-fixes AUTO errors,
and saves. Today its wizard tab (`wizard_finalize.js`) is a read-only *summary*
of the finalize report (auto-fixes + remaining MANUAL errors). The card asks for
a **fully featured editing UI**:

- show all cards with their new (finalized) text
- a visual indicator of which cards were edited and what the edits were
- the user can edit any field of any card manually
- special-character insertion (mana / tap symbols) with a helper line at the top
  explaining the `{T}` etc. tokens
- the user can choose to stop at this step ("Stop after this step"), then manually
  continue after editing (Save & Continue)

## Design

### Backend — `mtgai/review/finalize.py`

`finalize_set()` already computes, per modified card, the original oracle text
(`original_oracle`) and the list of applied fixes. To let the UI show *what* the
finalize stage changed, persist the original oracle text on each card's summary
entry: add `original_oracle_text` (the pre-finalize text) to the `entry` dict.
This is the single new piece of data the report needs; everything else (name,
fixes_applied, modified) already exists.

The summary dict is written to `<asset>/reports/finalize-report.json` (new — a
JSON sidecar next to the existing markdown report) so the wizard endpoint can read
it back without re-running finalize. `finalize_set` writes the JSON in the
`not dry_run` branch alongside `_write_report`.

### Backend — `mtgai/pipeline/server.py`

Three endpoints under `/api/wizard/finalize/*`, following §17 conventions
(`_require_active_project`, `set_artifact_dir`, `_read_request_json`,
`_next_stage_nav`, `_heal_failed_stage`, `_stage_status_in_state`):

1. `GET /api/wizard/finalize/state` — returns
   ```
   { cards: FinalizeCard[], has_content, report, stage_status, set_params }
   ```
   `FinalizeCard` is the full editable card shape (every field the UI edits):
   `collector_number, name, mana_cost, type_line, oracle_text, flavor_text,
   power, toughness, loyalty, rarity, colors, type fields, slot_text` plus
   finalize-provenance fields derived from the report:
   `auto_edited` (bool), `fixes_applied` (list[str]),
   `original_oracle_text` (str|null). Cards are read from the live `cards/`
   dir (skip Lands `L-*` and basics — finalize skips basics). Sorted by
   collector number. `report` carries the summary counts for a header strip.

2. `POST /api/wizard/finalize/save-card` — body `{collector_number, fields:{...}}`.
   Loads the card JSON, applies the edited fields via `card.model_copy(update=...)`
   (validates through the Pydantic model so an illegal value 400s), re-derives
   `mana_cost_parsed`/`cmc`/`colors` is NOT attempted here (manual edit is text;
   the renderer re-parses mana from `mana_cost` at render time). Saves via
   `save_card`. Marks the card `_user_edited` provenance (returned to the tab so
   the badge persists across reloads — stored as a transient: we re-derive
   "user edited" by comparing against the finalize report's original text is not
   reliable for arbitrary fields, so we persist a small marker). **Marker**: write
   the set of user-edited collector numbers to
   `<asset>/reports/finalize-user-edits.json` so the badge survives reload.
   Calls `_heal_failed_stage("finalize")`.

3. `POST /api/wizard/finalize/save` — bulk Save & Continue. Body
   `{cards: [{collector_number, fields}]}` persists any pending edits (same
   per-card apply), heals, then returns `{navigate_to: _next_stage_nav("finalize")}`.
   The tab's footer button then POSTs `/api/wizard/advance` (engine resume) when
   paused — mirroring the human_card_review advance pattern. Actually finalize's
   advance is the same as other review-gated stages: persist → advance → navigate.
   We use `W.saveAndAdvance` with this save URL.

No new pipeline stage, no schema change. `finalize` stays `review_eligible: False`
in STAGE_DEFINITIONS — BUT the "Stop after this step" toggle is rendered by the
stage shell unconditionally and the break-point → `review_mode == REVIEW` pause is
wired independent of `review_eligible`. So flipping the toggle on already makes the
engine pause after the finalize runner completes (reminder inject + auto-fix done),
which is exactly the "stop to edit, then continue" flow the card wants. To make the
intent explicit and let users discover it, we flip `finalize` to
`review_eligible: True` (metadata only; default break-point stays auto/off).

### Frontend — `wizard_finalize.js` (rewrite)

Full rewrite into an editable card grid following the §17 recipe + the
human_card_review tile pattern:

- **Symbol helper line** at the top: a dismissible info banner explaining the
  token syntax (`{T}` tap, `{W}{U}{B}{R}{G}` colors, `{1}{2}…` generic, `{C}`
  colorless, `{X}`, `{Q}` untap, etc.). Tokens in oracle/cost text render as small
  inline symbol badges (pure CSS, no SVG dep) in the read view; the textareas show
  the raw `{T}` tokens for editing.
- **Summary strip**: cards processed / auto-edited / auto-fixes / manual errors
  (from `report`).
- **Filter** row: rarity + "edited only" (auto-edited or user-edited) + "manual
  errors only".
- **Card grid**: one editable card per tile. Each tile:
  - header: collector number + name + rarity pill + provenance badge
    (`W.provenanceBadge`): `'auto'` when finalize auto-edited it, `'user'` (edited)
    once the user touches a field. A card both auto-edited and untouched shows the
    auto badge; once the user edits, it flips to the edited badge.
  - an **expandable "what changed"** block for auto-edited cards: lists
    `fixes_applied` and shows the before/after oracle text diff
    (`original_oracle_text` → current) so the user sees what finalize did.
  - editable fields: name, mana_cost, type_line, oracle_text (textarea),
    flavor_text (textarea), power, toughness, loyalty. Inputs show raw tokens.
  - a rendered-preview line under oracle_text showing the tokens as symbol badges
    so the user sees how it'll look.
  - per-card "Save" button → POST `/api/wizard/finalize/save-card`; debounced
    auto-save on blur also acceptable but explicit Save is clearer and matches the
    reprints manual-save contract. We use blur-save (persist on field blur) +
    visual "saved" tick, which is the smoothest editing UX, plus the bulk Save &
    Continue covers everything on advance.
- **Form lock (§3)** while the stage is running or a save is in flight.
- **Footer (§1)**: `W.saveAndAdvance` when paused_for_review on the latest tab
  ("Save & Continue: <next stage>"); a footer note otherwise. The save thunk
  gathers all dirty cards into the bulk `/finalize/save` payload.
- **Status pill (§8) + break toggle (§9)**: owned by the shell.

### Symbol rendering (frontend only)

A small `symbolizeHtml(text)` helper turns `{...}` tokens into
`<span class="wiz-sym wiz-sym-W">W</span>`-style badges with per-color CSS
(reusing the rendering color palette: W off-white, U blue, B black, R red, G
green, generic/colorless grey, T/Q grey tap glyph). This is display-only; the
underlying stored text keeps the canonical `{T}` tokens, matching
`oracle_text`/`mana_cost` schema (CLAUDE.md: field names match Scryfall; tokens
are the on-disk form the renderer's `symbol_renderer.parse_mana_cost` consumes).

## Tests

- `tests/test_review/test_finalize.py` (or existing finalize tests): assert the
  summary entry now carries `original_oracle_text` for a modified card.
- Endpoint behaviour is integration-level (needs an active project + asset dir);
  covered by manual smoke. Add a unit test for the per-card field-apply helper if
  it's factored into a pure function (`_apply_card_edits(card, fields) -> Card`)
  so an illegal field 400s and a legal one round-trips.

## Out of scope

- SVG symbol rendering in the browser (CSS badges suffice; the real SVGs are a
  render-stage concern).
- Editing card_faces (DFC) sub-fields — single-face only for now; DFC cards show
  their primary face fields. (Flag as follow-up if needed.)
- Re-running validation on a manual edit in the UI (the edit is trusted; the next
  pipeline pass / a later finalize re-run re-validates).

## Verification

1. `ruff check .` + `ruff format .` clean from `backend/`.
2. `python -c "import mtgai"`.
3. `pytest` green (finalize tests + no regressions).
4. Manual: `python -m mtgai.review serve --open`, open a project with finalized
   cards, navigate to the Finalization tab:
   - cards render with finalized text, auto-edited cards badged + "what changed"
     expandable shows fixes + before/after.
   - edit a field, blur → persists (reload shows the edit + "edited" badge).
   - symbol helper line present; tokens render as badges in the preview.
   - toggle "Stop after this step" on Project Settings or the tab; run to finalize;
     it pauses; edit; Save & Continue advances to Card Review.
