# Card-gen regen instance: progress count + old/new card distinction

## Context

`card_gen` is a re-entrant stage. After the Conformance & Interactions / Design Review
gates flag cards (`regen_reason`/`flagged_by`, `rerun_from="card_gen"`), the engine appends
a fresh `card_gen.N` instance that regenerates **only the flagged slots** — not the whole
set. Two UI problems on those later instances:

1. **Wrong "X / Y" denominator.** The progress headline shows `X / Y cards generated` with
   `Y = total set size` (~277) even though the instance only re-creates the handful of
   flagged cards. The bar therefore looks stuck near 0% (e.g. `5 / 277`).
2. **No old/new distinction.** The grid shows the full live pool (all ~277 cards), with no
   visual cue for which cards this instance actually (re)generated vs which were carried
   over from the prior instance.

## Root cause (Part 1 — the count)

`generation/card_generator.py::generate_set` reports `len(all_slots)` (the full skeleton)
as the progress `total`:
- `card_generator.py:1193` — "preparing" callback `total = len(all_slots)`
- `card_generator.py:1487` — per-batch callback `total = len(all_slots)`
- `card_generator.py:1542` — return `total_slots = len(all_slots)` (→ `StageResult.total_items`
  → persisted `stage.progress.total_items`, so the *completed* display is also wrong)

`completed`/`filled` is already scoped to **this run** (`total_saved`), so only the
denominator is wrong. The set of slots this run generates is `unfilled` (computed at
`card_generator.py:1136-1161`, already post-cap and post-regen-drop): on a regen instance
flagged cards are dropped from `progress.filled_slots` so they re-enter `unfilled`, making
`len(unfilled)` exactly the regen count; on the first instance `unfilled == all_slots`.

### Fix
Introduce `run_target = len(unfilled)` right after the cap block and use it as the `total`
in both progress callbacks and as `total_slots` in the success-return dict. No threading,
no schema change. The "nothing to generate" early-return path is left as-is (it's the
all-filled 100% case, not a regen view).

## Root cause (Part 2 — old vs new)

The data to distinguish "regenerated this instance" already exists durably:
`StageState.entry_snapshot_id` points at the instance's entry card-pool snapshot
(`history/<entry_snapshot_id>/cards/`), and the live (or this instance's) pool is the
output. A card is **new this instance** iff its JSON differs from — or is absent in — the
entry snapshot (carried-over cards are *plain file copies* per `history.py`, so byte-equal;
regenerated cards differ, at minimum because the entry copy still carries the gate's
`regen_reason` flag).

### Fix
- **`stage_hooks.card_tile_dict`**: add an optional `is_new: bool = False` param; include
  `is_new` in the emitted tile shape (kept on **both** the SSE and `/state` paths so the
  shape stays byte-identical — only the value differs).
- **SSE stream** (`build_card_gen_hooks.on_card_saved`): emit `is_new=True` — any card
  streamed during the run was just (re)generated.
- **`/api/wizard/card_gen/state`** (`server.py`): resolve the viewed instance's
  `StageState` (by `instance_id`, default backbone) → its `entry_snapshot_id`. Build the set
  of `collector_number`s whose card differs from the entry snapshot's card-gen cards. Mark
  each tile `is_new` accordingly. Guard rails:
  - No `entry_snapshot_id` / missing snapshot (pre-version-tracking) → no highlight
    (`is_new=False` for all).
  - Entry snapshot has **zero** card-gen cards (the first `card_gen`, whose entry is the
    `lands` snapshot) → first generation, "everything is new" is not a useful distinction →
    no highlight.
  - Only when the entry snapshot *does* contain card-gen cards (a genuine regen instance)
    do we highlight the diff. The endpoint also returns `is_regen_instance: bool` so the tab
    can show a one-line legend.
- **`wizard_card_gen.js`**: render `is_new` cards with a distinct treatment (accent border +
  subtle background + a small "new" badge) and, when `is_regen_instance`, a one-line legend
  ("Highlighted cards were regenerated this round; the rest carried over."). The SSE upsert
  preserves `is_new` from the streamed card.

## Files touched
- `backend/mtgai/generation/card_generator.py` — `run_target` count fix (3 sites).
- `backend/mtgai/pipeline/stage_hooks.py` — `card_tile_dict(is_new=...)` + `build_card_gen_hooks`.
- `backend/mtgai/pipeline/server.py` — `/state` computes the regenerated set via entry-snapshot diff.
- `backend/mtgai/gallery/templates/static/wizard_card_gen.js` — highlight + legend.
- `CLAUDE.md` — note the `is_new` tile field + entry-snapshot diff if it's a documented contract.

## Tests
- `tests/` (mirrors source): a unit test that `generate_set`'s progress callback reports
  `total == len(unfilled)` on a regen-style run (some slots pre-flagged) — likely a small
  dry-run or a targeted test around the count. Reuse existing card_gen test fixtures if present.
- A `card_tile_dict` test asserting `is_new` flows into the tile shape.
- An entry-snapshot-diff unit test for the `/state` regenerated-set computation (extract the
  diff into a small pure helper so it's testable without a running server).

## Out of scope
- Changing which cards a gate flags or how regen works.
- The global progress strip styling (it already routes per-instance counts correctly; the
  count fix flows into it for free).
- Materializing reprints / any unrelated card_gen behavior.

## Verification
- `ruff check .` / `ruff format .`, `python -c "import mtgai"`, `pytest` from `backend/`.
- Manual: `python -m mtgai.review serve --open`, drive a set to a conformance flag so a
  `card_gen.2` instance appears; confirm the headline shows the regen count and the
  regenerated cards are visually distinct from carried-over ones.
