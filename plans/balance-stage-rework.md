# Re-entrant pipeline (repeated stage instances) + Balance/Conformance redesign

## Context

Reimplementing the post-generation stages surfaced that the old `balance` stage emits
warnings nothing acts on. Co-designing with the user reshaped this into a far more general
capability: **a review stage flags specific cards, and the pipeline regenerates just those
cards and re-checks, until the review passes.** The agreed mechanism is **forward-only
insertion of repeated stage instances**: when a review flags cards, the engine *appends* a
fresh `card_gen` + review instance (scoped to the flagged cards) after the current step and
keeps walking forward. The user's target flow becomes literal, distinct, individually-
visible steps:

```
card_gen → balance → (flagged) card_gen 2 → balance 2 → (clean) skeleton_rev →
  (flagged) card_gen 3 → balance 3 → skeleton_rev 2 → (clean) ai_review → …
```

**User decisions (locked):**
- Re-entrancy = **append repeated stage instances**, forward-only (not a backward index jump).
- Each instance gets **its own wizard tab** ("Balance Analysis", "Balance Analysis 2", …).
- On budget exhaustion (cards still failing after N cycles): **pause for human review**,
  keep the best attempt, leave the cards flagged.
- The regen flag is a **field on the Card** (persisted, gallery-visible, survives restarts).
- **Drop the coverage checks entirely.** Replace algorithmic conformance with an LLM check.
  Keep the LLM interaction (degenerate-combo) check.

**Intended outcome:** one general "review → scoped regeneration → re-check" loop, realized
as a growable instance-based pipeline, with the interaction + conformance checks as its
first two consumers; `skeleton_rev` and `ai_review` migrate onto it later.

## Why feasible / what to reuse

- **Subset regeneration already exists:** `skeleton_reviser.regenerate_slots(slot_ids,
  skeleton, …)` (`backend/mtgai/generation/skeleton_reviser.py:578`) regenerates an explicit
  list of slots through the normal card-gen pipeline. Generalize it; don't reinvent.
- **The engine walk already tolerates growth:** `_run_loop` (`backend/mtgai/pipeline/engine.py:234`),
  the `all_done` check (`engine.py:339`), and `_first_pending_stage_id` (`server.py:1858`) all
  iterate the *live* `state.stages` list — appended instances are picked up and run as PENDING
  for free.
- **The breakage is concentrated in identity**, not the walk (see blast radius below).

---

## Part 1 — Instance-based, growable pipeline (foundational; behavior-neutral)

Goal: make a stage able to appear more than once, each with its own tab, **without changing
any current behavior** (nothing is inserted yet). Ship + test this first.

### Identity
- Add `instance_id: str` to `StageState` (`backend/mtgai/pipeline/models.py:85`). The
  **backbone** instance of each stage keeps `instance_id == stage_id` (so existing URLs,
  break-point keys, model assignments, runner/clearer lookups, and old persisted state all
  keep working). Inserted copies get `f"{stage_id}#{n}"` (e.g. `balance#2`), with display
  title suffixed (`Balance Analysis 2`).
- `stage_id` stays the **template key**: `STAGE_RUNNERS[stage_id]`, `STAGE_CLEARERS[stage_id]`,
  `display_name`, `review_eligible`, break-point + model-assignment resolution all stay keyed
  by `stage_id` and are **shared across instances** (all `balance` instances use the same
  model + break setting — intentional, no per-instance config).
- The current-stage pointer becomes **instance-based**: rename `current_stage_id` →
  `current_instance_id` and rewrite `PipelineState.current_stage()` (`models.py:125`) to match
  on `instance_id`. Update the handful of call sites the blast radius found.

### State reconciliation (the critical fix)
- `_sync_stages_with_definitions` (`engine.py:88`) currently rebuilds the list from a
  `{stage_id: stage}` dict — it **destroys dynamic duplicates on reload**. Rework it to
  reconcile the **backbone only** (ensure each `STAGE_DEFINITIONS` stage_id is present once in
  canonical order, drop removed ones) while **preserving non-backbone instances in place**
  relative to their preceding backbone anchor. Test: a state with `card_gen#2`/`balance#2`
  round-trips through `load_state()` unchanged.

### Wizard tab layer (the bulk of the UI churn)
Switch the tab key from `stage_id` to `instance_id` everywhere it's the routing/identity unit:
- **Server:** `wizard.py` `compute_visible_tabs` / `compute_latest_tab` / `resolve_tab` /
  `serialize` (`wizard.py:128–266`) emit one tab per instance keyed by `instance_id`, title
  with ordinal suffix. `_stage_status_in_state` (`server.py:2403`) and the next-stage
  navigation in the mechanics/archetypes/skeleton save endpoints (`server.py:2784,3205,3909`)
  must read the **runtime `state.stages`**, not `STAGE_DEFINITIONS` offsets (those skip
  inserted instances).
- **Client:** `wizard.js` `renderTabStrip` / `showTab` / `updateStageStatus` /
  `handlePhaseEvent` (`wizard.js:254–321,470–510,616–669`) key tabs + lookups by `instance_id`
  (`data-tab-id`). `wizard_stage.js` `findStage` / `renderStageTab` (`wizard_stage.js:36–62,374`)
  resolve the instance by `instance_id` but pick the renderer by `stage_id` (so one
  `wizard_balance.js` renders every balance instance, fed that instance's state).
- **Per-stage renderers** (`wizard_balance.js:508,511`, etc.): replace the hardcoded
  `find(stage_id === STAGE_ID)` + `latestTabId === STAGE_ID` with the instance passed in by
  the shell.

### SSE
Every stage event (`stage_update`, `phase`, `item_progress` in `events.py` / `StageEmitter`)
must carry **`instance_id` alongside `stage_id`** so the client updates the right tab. The
strip/tab handlers dispatch on `instance_id`.

### Edit-cascade
`_resolve_edit_point` + `_apply_cascade_clear` (`server.py:1990–2139`) work by index/slice
(fine for a growable list) but must resolve the boundary by `instance_id` and clear by
`stage_id` (clearer is shared). Note: clearing a stage with multiple instances clears the
shared artifacts once.

**Acceptance for Part 1:** existing pipelines run identically; a hand-constructed state with a
duplicated instance routes to two distinct tabs and survives reload.

---

## Part 2 — The review→regen loop (first consumers: balance + conformance)

### Card-flag substrate
Add to `Card` (`backend/mtgai/models/card.py:108`): `regen_reason: str | None`,
`flagged_by: str | None`. A review writes them onto failing cards and demotes `status` to
`DRAFT`. `card_gen` (`card_generator.py:813`) treats a slot as needing (re)generation when it
has **no card yet OR its card has `regen_reason` set**; on success it clears the flags and
archives the prior card (reuse `skeleton_reviser.archive_card`) and threads `regen_reason` into
the prompt (reuse `_retry_single_card`'s "previous attempt … fix this" shape). The flag *is*
the work-queue — no scope list needed in `StageResult`.

### Engine insertion
- `StageResult` gains `rerun_from: str | None` (`stages.py:60`). A review runner sets it to the
  upstream stage_id to bounce to (always `card_gen` here) when it flagged any cards.
- In `_run_loop`, after a successful stage with `result.rerun_from` set: if the count of
  existing instances of this review's `stage_id` `>= MAX_REVIEW_ROUNDS` (default 3) → the
  flagging instance goes `PAUSED_FOR_REVIEW` (exhaustion → human). Otherwise mark the flagging
  instance `COMPLETED` ("flagged N cards → regenerating"), **insert fresh instances** for the
  span `[rerun_from … this review]` (the stage_ids between them in canonical order) right after
  the current index, and continue the forward walk into them. Cascade falls out for free
  (a `skeleton_rev` bounce inserts `card_gen` + `balance` + `conformance` + `skeleton_rev`).
- Switch `_run_loop` from `for stage in …` to an index-driven `while i < len(stages)` so
  insertions after `i` are walked. Bound total growth by the per-stage_id instance cap.

### The two review stages
Order: `card_gen → balance → conformance → skeleton_rev → ai_review → …` (add `conformance`
to `STAGE_DEFINITIONS` after `balance`, with a runner + clearer).
- **`balance`** — keep `analyze_interactions`' prompt/tool substance (whole-pool LLM scan,
  names enabler + replacement constraint). Runner: scan → write `regen_reason =
  replacement_constraint`, `flagged_by="balance"` on each enabler → `rerun_from="card_gen"` if
  any, else clean.
- **`conformance`** (new) — one whole-set LLM call: every card + its slot spec (`tweaked_text`,
  falling back to `render_slot_string`) → list `slot_id`s that don't fulfil their spec + a
  one-line reason. Flag those (`flagged_by="conformance"`) → `rerun_from="card_gen"` or clean.
  **No descriptor parser** — the LLM judges adherence holistically.

### Deletions
- `analysis/coverage.py` + its models; `analysis/conformance.py` algorithmic checks + most of
  `helpers.py`'s regex/parsing; `analyze_set()`, `BalanceAnalysisResult`, `report.py`'s
  markdown/JSON `save_report`; the orphaned `mtgai review balance` CLI command (`cli.py:318`).
  Keep + adapt `interactions.py`; add the LLM conformance module.

### Tabs
`wizard_balance.js` (reworked) + new `wizard_conformance.js`: each shows the cards it flagged +
reasons and pass/paused state; an exhausted instance is the paused-for-review surface. Drop the
old color-bar/coverage sections. Endpoints `/api/wizard/{balance,conformance}/state` follow the
reprints `/state` convention.

### Transitional
`skeleton_rev` is **paused/skipped** in Part 3-pending state (it currently reads the removed
`balance-analysis.json`); a thin shim or a SKIPPED default keeps the pipeline green until
Part 3.

---

## Part 3 — Migration (follow-up card, not this change)

Migrate `skeleton_rev` to emit `rerun_from="card_gen"` via the shared flag substrate instead of
its private `run_revision` round loop, and give `ai_review` the same flag-and-regen behavior
(its in-stage `MAX_ITERATIONS` repair becomes engine-level regen). Retire `regenerate_slots`'
private loop in favor of the engine's.

## Files to change

**Part 1 (foundational):** `pipeline/models.py` (instance_id, current_instance_id,
current_stage()); `pipeline/engine.py` (_sync rework, while-loop, current-instance lookups);
`pipeline/events.py` (instance_id on SSE); `pipeline/wizard.py` (tabs by instance_id);
`pipeline/server.py` (routing, _stage_status_in_state, next-stage nav from runtime stages,
edit-cascade by instance); `gallery/templates/static/wizard.js` + `wizard_stage.js` +
per-stage `wizard_*.js` (instance-keyed tabs/lookups).

**Part 2 (loop + checks):** `pipeline/stages.py` (StageResult.rerun_from, run_conformance,
rework run_balance, registry + clearer); `pipeline/engine.py` (insertion + budget +
exhaustion-pause); `pipeline/models.py` (conformance in STAGE_DEFINITIONS); `models/card.py`
(regen_reason, flagged_by); `generation/card_generator.py` (flag-driven regen); `analysis/*`
(delete coverage/algorithmic-conformance/report; adapt interactions; add LLM conformance);
`pipeline/server.py` (`/api/wizard/{balance,conformance}/state`); `gallery/.../wizard_balance.js`
+ new `wizard_conformance.js`; `review/cli.py` (remove balance command); `generation/skeleton_reviser.py`
(extract regenerate_slots; pause its loop).

## Verification

- **Part 1 unit/regression (behavior-neutral):** existing `test_pipeline` suite stays green; a
  new test round-trips a state containing `card_gen#2`/`balance#2` through `load_state()`
  unchanged; `current_stage()` resolves the right instance; the wizard serialize emits two
  tabs for two instances with distinct ids/titles.
- **Engine insertion tests (core risk):** a fake review stage that flags N cards for K cycles
  then passes — assert the engine **inserts** `card_gen` + review instances each cycle
  (forward-only, list grows), `card_gen` regenerates only flagged cards, the run advances on
  clean, and the flagging instance **pauses_for_review** when the instance cap is hit with
  flags remaining. A cascade test: a `skeleton_rev` flag inserts the full upstream span and
  it all re-runs in order. A resume-after-crash test: kill mid-loop, reopen, confirm the grown
  list resumes.
- **Card-flag regen:** flag a card, run `card_gen`, assert only that slot regenerates, the
  reason rode into the prompt, the flag cleared, old card archived.
- **Manual end-to-end:** `python -m mtgai.review serve --open` on a generated set; force an
  interaction/conformance miss and watch the strip grow `balance → card_gen 2 → balance 2 …`
  with each as its own tab, then advance on clean; set the cap low + a persistent failure and
  confirm the instance pauses for human review with flagged cards shown.
- **Lint/tests:** `cd backend; ruff check . && ruff format . && pytest`.
- **CLI:** `mtgai review --help` no longer lists `balance`.
