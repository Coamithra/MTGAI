# Version Tracking — per-instance card-pool snapshots for the review→regen loop

**Status:** proposed (design only — nothing implemented yet). Captured from a
design pass on `master`, 2026-06-01.

## Problem

The re-entrant pipeline (see CLAUDE.md "Re-entrant pipeline / review→regen loop")
already gives every looping-stage *instance* a stable identity and its own findings:

- `StageState.instance_id` is `stage_id` for the backbone and `f"{stage_id}.{n}"`
  for inserted copies (`make_instance_id`, `backend/mtgai/pipeline/models.py:92`).
  Each instance is its own wizard tab.
- Each `StageState.result` is per-instance, so the gate *verdicts* across rounds
  (`conformance` vs `conformance.2`, etc.) are already versioned and survive reloads.

What is **not** versioned is the thing the verdicts are *about* — the card pool.

- **One mutable card folder.** Every instance — `card_gen`, `card_gen.2`,
  `conformance`, `conformance.2`, `balance`, `ai_review` — reads and writes the single
  `<asset>/cards/` directory (`io/card_io.save_card`, `_flag_cards_for_regen` at
  `pipeline/stages.py:1018`, `review/finalize.py`). There is **no per-instance input
  state** on disk.
- **Gate flag-state is transient — and that's the point.** `conformance.1` stamps
  `regen_reason`/`flagged_by` on cards; `card_gen.2` then *consumes and clears* those
  flags during regen. By the time `balance.1` runs, the conformance flags are gone
  from the live pool. So re-running `conformance.1` faithfully is impossible from live
  state — you'd need the pool as it stood when `conformance.1` began.
- **`_regen_archive/` is not a clean snapshot.** `card_gen` moves flagged cards there
  before regen (`archive_card`, `generation/card_generator.py:871`), but it's a flat
  bag keyed by collector number with timestamp-collision suffixes — not "the pool as it
  stood on instance K's entry."
- **Refresh is stage-scoped, not instance-scoped.** `POST /api/wizard/card_gen/refresh`
  re-runs whichever instance is *current* (`pipeline/server.py:3907`); there is no way
  to target `card_gen.1` vs `card_gen.2`. The gate tabs (`conformance`, `balance`,
  `ai_review`) have no manual re-run at all — they render `stage.result` read-only.
- **Tabs silently show the wrong cards.** Every tab's state endpoint reads live
  `cards/` (`wizard_card_gen/state`, `pipeline/server.py:3867`), so an old `card_gen.1`
  tab viewed after `card_gen.2` ran shows the *latest* cards, not its own.

**Goal:** every duplicable instance knows the card-pool state on its entry, can be
re-run from that state on demand, and re-running resets future instances (tabs)
without disturbing past ones — e.g. re-running `card_gen.2` resets/deletes
`conformance.2` and `balance.2` (Interaction Check 2) but leaves `card_gen.1` /
`conformance.1` intact.

## Design

### Core model — one live folder + append-only per-instance snapshots

Keep `<asset>/cards/` as the single **live working set** (do not relocate it). Add a
write-once `history/` sidecar, one folder per instance, holding that instance's
**output**:

```
<asset>/
  cards/                       ← LIVE working set. Unchanged. Always == the "tip"
                                 of the loop (the latest completed instance).
  generation_progress.json     ← LIVE, unchanged
  history/
    lands/         cards/  progress.json    ← loop entry anchor
    card_gen/      cards/  progress.json     ← output snapshot of instance card_gen
    conformance/   cards/  progress.json
    card_gen.2/    cards/  progress.json
    conformance.2/ cards/  progress.json
    ...                                       ← one folder per instance_id
```

Instance K's **entry state** is the output snapshot of its immediate predecessor in
`state.stages`. Because the loop is forward-only and always leaves its result in
`cards/`, the live folder is always exactly what the downstream non-loop stages
(`finalize`, art, render) should read — so **those stages need zero changes.**

### Why this over folder-per-instance-as-primary (the obvious alternative)

The tempting variant is "give each instance its own primary folder and make it the
working dir." Same snapshot bytes, but it relocates the source of truth — and a large
body of code hardcodes `set_artifact_dir() / "cards"`, including the **downstream
non-loop stages (art, render) that have no concept of instances at all**. Making them
learn "which instance's folder is current" is a pervasive, error-prone refactor for no
extra capability. The history-sidecar keeps the change *additive*: existing
readers/writers keep pointing at `cards/`; only the wizard's per-instance *viewing* and
the re-run path learn about `history/`.

### Snapshot lifecycle

- **When:** on instance *completion*, under the AI lock, at the existing `save_state`
  seam (`pipeline/engine.py:56`). Copy live `cards/*.json` + `generation_progress.json`
  → `history/<instance_id>/`.
- **Which stages:** the loop stages (`card_gen`, `conformance`, `balance`, `ai_review`)
  plus the loop's entry anchor `lands` (the last pre-loop stage that writes cards, so
  `card_gen.1` has an entry to restore). `_regen_archive/` is **excluded** from
  snapshots (transient; history supersedes it).
- **Cost:** ~277 JSONs × ~2 KB ≈ 0.5 MB/snapshot; worst case ~15–20 instances ≈ 10 MB.
  Negligible; `output/` is already gitignored. Optional later optimization: hardlink
  instead of copy — *safe here* precisely because every writer uses
  `atomic_write_text` (rename-replace, never in-place mutation), so a hardlinked
  snapshot can't be clobbered.

### Re-run algorithm (uniform for *any* instance)

Re-running instance **K** at list index `idx`:

1. **Restore entry:** copy `history/<stages[idx-1].instance_id>/` → live `cards/` +
   `generation_progress.json`. (For the backbone `card_gen.1`, the predecessor is
   `lands`.) The snapshot encodes the correct flag/content state, so **no manual flag
   manipulation is needed** — `card_gen.2`'s entry already carries its flags;
   `conformance.2`'s entry already has clean cards.
2. **Truncate:** delete every stage *after* `idx` from `state.stages`; delete their
   `history/` folders.
3. **Reset K:** status → `PENDING`, clear `result`/`progress`; delete K's own
   `history/` (it re-emits on completion).
4. **Re-append the forward path:** for each canonical stage strictly *after* K's
   `stage_id` (loop tail + post stages), append a fresh `PENDING` instance, numbered
   via `make_instance_id(stage_id, count_of_existing_with_that_stage_id + 1)`.
5. **Resume** the engine at K.

**Step 4 is the crux.** It is the *forward* mirror of `_build_rerun_span`
(`pipeline/engine.py:478`) — that builds the backward slice `canonical[rerun_from …
gate]`; this builds `canonical[after K … end]`. The auto-numbering naturally yields a
backbone id (`balance`) when no earlier sibling survives and a `.N` id
(`conformance.2`) when one does — which is what re-establishes the gate that must
*follow* a regenerated `card_gen` instance (the bug a naive truncate-and-stop would
hit: the engine would walk off the end without re-checking the new cards).

### Worked example — re-run `card_gen.2`

List: `[card_gen.1, conformance.1, card_gen.2, conformance.2, balance.1, ai_review.1,
finalize]`. User hits **Refresh on `card_gen.2`**:

1. Restore `history/conformance.1/` (the flagged round-1 pool) → `cards/`.
2. Delete `conformance.2, balance.1, ai_review.1, finalize` + their history.
3. `card_gen.2` → `PENDING`.
4. Re-append `[conformance.2 (count→2), balance, ai_review, finalize]` fresh `PENDING`.
5. Resume. Engine re-runs `card_gen.2` (regens flagged cards), then `conformance.2`
   re-checks the new cards, then `balance`, `ai_review`, `finalize`; and if
   `conformance.2` flags again it inserts `card_gen.3` exactly as today.

Past instances (`card_gen.1`, `conformance.1`) are untouched. The identical algorithm
handles re-running `conformance.1`, `balance`, `ai_review`, or the backbone
`card_gen.1` with no special cases. It is the generalized form of the existing
**edit-cascade** (`/api/wizard/edit/accept`, which already truncates downstream when a
past tab is edited), so it slots into an established pattern.

### Wizard / API changes

- **Instance-aware refresh:** the refresh endpoints accept an `instance_id` (body or
  path) and run the algorithm above. SSE already carries `instance_id`
  (`card_gen_reset`, `card_gen_card`), so streamed updates route to the right tab.
- **Read-routing for viewing:** the tab state endpoints resolve cards from
  `history/<instance_id>/` for a *completed, non-tip* instance and from live `cards/`
  for the in-flight/tip instance. This also fixes the current bug where an old tab shows
  the latest cards.
- **Confirm dialog** when a re-run would cascade through already-generated art/renders
  (it regenerates them — same contract as the edit-cascade).

### Data-model change (minimal)

One optional field on `StageState` (`pipeline/models.py`):
`entry_snapshot_id: str | None` — the predecessor instance_id whose output is this
instance's entry. Derivable from list position, but storing it makes restore robust
against `_sync_stages_with_definitions` reordering and reload. Everything else
(snapshot existence) is just folder-presence on disk.

## Why this shape

- **Additive, not invasive.** The live `cards/` folder and every existing
  reader/writer stay put; downstream art/render are untouched because the loop always
  leaves its result at the tip. Only viewing and re-run learn about `history/`.
- **The snapshot encodes flag-state for free.** Restore needs no flag fix-up because
  each instance's output already captures the exact `regen_reason`/`flagged_by`/content
  state for that point in the loop. This is the property `_regen_archive/` lacks.
- **Re-run reuses the engine's own primitives.** Forward-path re-append is the mirror
  of `_build_rerun_span`; downstream truncation mirrors the edit-cascade. No new
  control-flow concept, no fighting the interleaved rounds list.
- **Bonus: diffable history.** Every instance's output is preserved, so the review UI
  can cheaply diff `card_gen.1` vs `card_gen.2` (or any pair).

## Edge cases to nail down in implementation

- **Backward compat / migration.** Existing projects have no `history/`. Degrade
  gracefully: if an instance's entry snapshot is missing, disable its Refresh button
  (or warn + fall back to a from-live re-run). New runs accrue history going forward;
  do **not** try to reconstruct from `_regen_archive/`.
- **`MAX_REVIEW_ROUNDS`.** Unchanged — a manual re-run is just another forward walk;
  the cap still trips at 3 instances of a gate (`pipeline/engine.py`).
- **finalize / art / render cascade.** Re-running a loop instance truncates *all*
  downstream, so already-generated art/renders regenerate — matches the edit-cascade
  contract; surface a confirm when art exists.
- **Windows file locks** (see global CLAUDE.md). Snapshot = copytree to
  `history/<id>.tmp` then rename; restore = clear-then-copytree into live `cards/`.
  Do it under the AI lock, with the Bash shell `cd`'d clear of the target, to avoid
  open-handle failures.
- **Scope.** Duplicable instances are `card_gen`, `conformance`, `balance` (Interaction
  Check), `ai_review` (Design Review). The `mechanics` stage loops *internally* but is
  single-instance/single-tab → out of scope.

## Folding in: scope down `clear_card_gen` (overzealous whole-`cards/` wipe)

`clear_card_gen()` (`pipeline/stages.py:1527`) is `_remove_path(_set_dir() / "cards")`
— it deletes the **entire** `cards/` directory. It's invoked by `_apply_cascade_clear`
(`pipeline/server.py:2344`) for every stage in `stages[start_idx:]` whenever a cascade
reaches `card_gen` — i.e. on almost any upstream edit. It is far too blunt:

1. **It destroys lands output.** The `lands` stage writes `L-*` cards into the *shared*
   `cards/` dir and runs *before* `card_gen`. An edit whose cascade starts at `card_gen`
   or later (`_resolve_edit_point`, `server.py:2248`) leaves `lands` upstream and
   un-re-run — yet `clear_card_gen` still nukes the whole dir, deleting the `L-*` cards
   lands produced. They never come back. This directly contradicts
   `/api/wizard/card_gen/refresh`, which deliberately *preserves* `L-*` via
   `_is_land_stage_card` (`server.py:3938-3944`). It is the only blunt whole-`cards/`
   delete in the tree.
2. **It's broader than its ownership and fires once per instance.** It removes the whole
   directory (not just card_gen's JSONs), and because the re-entrant loop can hold
   several `card_gen` instances in the cleared range, the cascade calls it once per
   instance — each redoing the same full-dir wipe.

**Fix, in two parts:**

1. **Scope it down (independent, ship-now).** `clear_card_gen()` should delete only
   card_gen-owned cards — `cards/*.json` minus `_is_land_stage_card` — plus
   `generation_progress.json` and `cards/_regen_archive/`, leaving the `L-*` lands cards
   intact. This is exactly the logic the refresh endpoint already runs inline; extract it
   into one shared helper (e.g. `clear_card_gen_cards()` in `stages.py`) and have both
   the clearer and the refresh endpoint call it (move/share `_is_land_stage_card`, which
   today lives in `server.py`). Net: the lands-destruction bug is gone and the clearer
   matches its documented ownership.
2. **Let snapshots subsume it (version-tracking integration).** Once `history/` exists,
   the cascade reset for the loop region *restores the entry snapshot* of the first
   cleared instance instead of deleting cards at all — and because each snapshot already
   contains the `L-*` lands cards, lands is preserved *for free* and the per-instance
   reset is precise. `clear_card_gen` then survives only as the no-snapshot fallback
   (migration / pre-version-tracking projects), in its scoped form, and the cascade
   clears card_gen cards once per stage rather than once per instance.

**Test impact:** `test_clear_card_gen_removes_cards_dir`
(`tests/test_pipeline/test_stage_clearers.py:76`) and the e2e equivalent
(`tests/test_io/test_asset_paths_e2e.py:72`) currently assert the *whole* `cards/` dir
is removed — they flip to "card_gen cards gone, `L-*` lands preserved."

## Resolved decisions (2026-06-01, with user)

- **Scope: all four duplicable stages** — `card_gen`, `conformance`, `balance`
  (Interaction Check), `ai_review` (Design Review) are all re-runnable in v1. The
  algorithm is uniform; ai_review costs only extra test coverage.
- **Snapshots: copy** (plain `copytree`), not hardlink. Revisit only if I/O hurts.
- **`history/` is internal-only** in v1 — no user-facing diff/versions affordance.
  v1 ships the re-run capability + correct per-instance card *viewing* (which fixes the
  "old tab shows latest cards" bug). A diff view is a tracked follow-up.

## Implementation order

### Part A — scope down `clear_card_gen` (independent, lands first)

1. `stages.py`: add `_is_land_stage_card(card: dict) -> bool` (moved from `server.py`);
   add `clear_card_gen_cards()` — deletes `cards/*.json` minus `L-*`, plus
   `generation_progress.json` + `cards/_regen_archive/`; `clear_card_gen()` delegates to it.
2. `server.py`: `card_gen/refresh`'s inline delete block + its `_is_land_stage_card` call
   the shared `stages` helpers (drop the server-local copy; re-export if other callers need it).
3. Tests: flip `test_clear_card_gen_removes_cards_dir` and the e2e
   `test_card_gen_clearer_targets_asset_folder` to "card_gen cards gone, `L-*` preserved,
   progress + `_regen_archive` gone"; add a `clear_card_gen_cards` preserves-`L-*` test.

### Part B — per-instance version tracking

4. `models.py`: add `StageState.entry_snapshot_id: str | None = None`.
5. New `pipeline/history.py`: `SNAPSHOT_STAGES = {lands, card_gen, conformance, balance,
   ai_review}`; `snapshot_instance(id)` (copytree live `cards/` + `generation_progress.json`
   -> `history/<id>/`, write-once, Windows-safe rmtree+copytree under the AI lock),
   `restore_snapshot(id)` (clear live `cards/` then copytree from `history/<id>/`),
   `delete_snapshot(id)`, `snapshot_exists(id)`.
6. `engine.py`:
   - One snapshot seam: right after a runner succeeds (post `cost_update`), snapshot the
     instance iff `stage_id in SNAPSHOT_STAGES`. Captures output for the normal-complete,
     paused-for-review, and inserted-gate-complete paths alike (resume()/skip() need none).
   - Stamp `entry_snapshot_id = stages[i-1].instance_id` (None for i==0) when a stage starts.
   - `rerun_instance(state, instance_id)`: restore entry snapshot -> truncate downstream
     (+ delete their `history/`) -> reset K to PENDING (+ delete K's snapshot) -> re-append
     canonical-forward path as fresh PENDING (`make_instance_id` auto-numbering — the
     forward mirror of `_build_rerun_span`) -> `current_instance_id=K`,
     `overall_status=NOT_STARTED`. Filesystem + state only; caller kicks the engine.
7. `server.py`:
   - `POST /api/wizard/instance/rerun` `{instance_id}` — guarded like `edit/accept`
     (409 if engine running / extraction running), runs `rerun_instance` + `_kickoff_pipeline_engine`.
     Returns `{success, navigate_to}`. Disabled client-side when the instance has no entry
     snapshot (migration). Surfaces a confirm when downstream art/renders exist.
   - Read-routing: `card_gen/state` (and the gate state surfaces) accept `?instance_id=` and
     read `history/<id>/` for a completed non-tip instance, live `cards/` for the tip / missing
     snapshot. Fixes the "old tab shows latest cards" bug.
   - Cascade integration: once snapshots exist, `_apply_cascade_clear` over a loop-region
     start restores the first cleared instance's entry snapshot (preserves `L-*` for free) and
     deletes the cleared instances' `history/`; `clear_card_gen` (scoped, Part A) stays the
     no-snapshot fallback.
8. Frontend: "Re-run this step" button on the four tabs (card_gen already instance-aware;
   add the gate tabs' button), wired to the rerun endpoint with the art-cascade confirm.
9. `CLAUDE.md`: document `history/`, the snapshot seam, `rerun_instance`, and the scoped
   `clear_card_gen`.

### Out of scope (follow-up cards)
- User-facing diff/versions view.
- Hardlink snapshot optimization.
- Reconstructing `history/` from `_regen_archive/` for pre-version-tracking projects.

## Original open questions (now resolved above)

- Confirm the duplicable-stage scope above (is `ai_review`/Design Review in or out for
  v1?).
- Hardlink vs copy for snapshots — start with copy (simplest), revisit if I/O hurts.
- Should `history/` be user-visible (a "versions" affordance / diff view) in v1, or an
  internal mechanism only?
