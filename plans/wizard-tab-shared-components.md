# Wizard tabs — shared components refactor

**Status:** planned. Snapshot taken at `cc54610`. No code changed yet — this is the
design + sequencing for a code-reuse pass across the pipeline wizard tabs
(Project Settings + Theme → Card Generation) and their backend endpoints.

**Tracking:** [Trello `refactor`](https://trello.com/c/IY49gZGb).

## Problem

The wizard tabs were grown by copying the two reference implementations
(Project Settings, Theme) into each new stage tab, then editing in place. The
result is exactly what `plans/wizard-tab-conventions.md` *prescribes* — that doc
repeatedly says "copy this helper into each new tab module" (§2 `requiredMark`,
§3 `setFormLocked`, §4 `renderMarkdown`, §7 the `ai_lock.hold` block, §13 the
section-refresh). Copy-as-convention worked to bootstrap the tabs, but it has two
costs now that there are ~10 tabs:

1. **Volume.** The same boilerplate is repeated 6–28 times. `escHtml`/`escAttr`
   are byte-identical in ~22 JS files; the `ai_lock.hold → 409` prologue appears
   ~7×; the active-project + asset-dir guards ~28× and ~20× respectively across
   `server.py`.
2. **Drift.** Independent copies have diverged in ways that look accidental, not
   intentional — so the tabs no longer behave consistently and bugs hide in the
   gaps (see *Inconsistencies & latent bugs* below). The clearest tell: `lands.js`
   literally comments "same column sizing as reprints," and stage tabs reuse
   Theme's `wiz-theme-section-header-row` CSS class — the files remember they were
   forked from each other.

The hunch that prompted this ("a lot of tabs independently implement the same
stuff as duplicates") is confirmed on both the frontend and the backend. §15 of
the conventions doc is the proof the fix works: the per-stage `_heal_failed_*`
one-offs were already collapsed into a single `_heal_failed_stage(stage_id)`, and
that convergence is now the documented convention. This plan does the same for the
rest of the shared surface.

## Evidence (snapshot at `cc54610`)

Tabs in scope (`backend/mtgai/gallery/templates/static/`): `wizard_project.js`,
`wizard_theme.js`, `wizard_mechanics.js`, `wizard_archetypes.js`,
`wizard_skeleton.js`, `wizard_reprints.js`, `wizard_lands.js`, `wizard_card_gen.js`
— against the existing shared core `wizard.js` + `wizard_stage.js`. Backend:
`pipeline/server.py` (the `/api/wizard/*` endpoints), `pipeline/stages.py`,
`pipeline/events.py`.

### Frontend duplication

| Pattern | Where | Similarity |
|---|---|---|
| `escHtml` / `escAttr` / `cssEsc` | ~22 files, verbatim | identical |
| `bodyRoot`/`tabRoot`/`getFooter`/`isPastTab` DOM lookups | every stage tab (3 different names for the tab-root lookup) | identical-but-renamed |
| `local` state object + `initialized` lazy-mount guard | mechanics, archetypes, skeleton, reprints, lands, card_gen | same shape, per-tab content key |
| `render()` mount → "just settled, re-bootstrap" lifecycle | same set | near-identical (one guard differs) |
| `bootstrap()` = fetch `/api/wizard/<tab>/state` + error unwrap + hydrate + repaint | same set | near-identical (404 policy diverges) |
| "Refresh with AI / Generate" button: guard→`setLocked`→`showBusy`→POST→409→toast→repaint→`finally` unlock | mechanics, archetypes, skeleton, reprints, lands, card_gen | near-identical |
| single-item "Refresh card" variant of the above | mechanics, archetypes | near-identical |
| 409 `running_action` toast + `reportError` | factored in archetypes+skeleton; **inlined ~5×** elsewhere | identical text |
| `saveAndAdvance`: save→`/api/wizard/advance`→navigate + button text-spinner | mechanics, archetypes, skeleton, theme | near-identical |
| `setFormLocked` form-lock | every editable tab | same recipe, per-tab class+selectors |
| `paintFooter` latest/past/completed/paused/running branch + `dataset.lastFooter` diff-guard + advance POST | every stage tab | same scaffold, per-tab copy |
| empty/loading placeholder (`generating = stageStatus==='running' || locked`) | every stage tab | near-identical |
| section header (`<h3>` + Refresh button) + context `<dl>` + theme-excerpt `<details>` | mechanics, archetypes, theme | near-identical (borrow Theme's CSS class) |
| AI-provenance badge + clear-on-edit | theme, mechanics, archetypes, skeleton, reprints | divergent selectors/classes/vocab |
| knob / bounded-control panel (input + bounds + provenance badge + pin + dirty hint + read-back) | skeleton (spec-driven), reprints (hardcoded) | same concept, divergent impl |
| read-only tile grid + rarity pill + scoped `injectStyles()` CSS | reprints, lands (skeleton shares empty-state) | ~70% identical CSS under different prefixes |
| SSE stream bridge (`W.on*Stream`): reset→merge-by-key→append→repaint | mechanics, skeleton, card_gen (theme variant) | same architecture, dedup reinvented per tab |
| local `postJSON` shadowing `W.postJSON` | project.js | redundant copy |
| MTG domain constants (`RARITY_ORDER`, `COLOR_ORDER`, …) | card_gen (likely recur elsewhere) | candidate shared module |

### Backend duplication (`server.py` unless noted)

| Pattern | Sites | Note |
|---|---|---|
| active-project guard → `_no_active_project_response()` | ~28 | `try: _require_active_project() except _NoActiveProject: …` |
| asset-dir resolve → `_no_asset_folder_response(exc)` | ~20 | `try: set_artifact_dir()/_mechanics_dir() except NoAssetFolderError: …` |
| `ai_lock.hold(label) → 409 busy` + `try: to_thread(gen) except: 500 {"error": str(exc)}` + `_heal_failed_stage` | 7 `hold` + 3 ad-hoc `is_running()` | the headline duplication; cancellation/heal **inconsistent** |
| JSON body parse → 400 envelope | `_read_request_json` in ~13, raw `await request.json()` in ~18 | raw form 500s on malformed body (project/edit endpoints never adopted the helper) |
| stage-artifact `_read_json` + shape re-validation + skeleton-presence gate | ~20 reads, **5 identical** `"No skeleton.json yet…"` gates | |
| knobs validate-and-persist (`POST /<tab>/knobs`) | reprints, skeleton (+ intra-skeleton dup) | |
| "next stage" nav computation from `STAGE_DEFINITIONS` | mechanics, archetypes, skeleton `save` | verbatim modulo stage id |
| SSE hook wiring written **twice** (engine `emitter.event` vs refresh `event_bus.publish`) | mechanics, skeleton, card_gen | logic dup (collision tag / persist) + silent payload-drift risk |
| stage-tab `state` endpoint shape (guard→guard→set_params+theme+model+status tail) | 6 | |
| three different "AI is busy" rejection mechanisms | `_project_switch_guard` (3) + `hold` (7) + `is_running()` (3) | converge on one primitive |

### Inconsistencies & latent bugs (fix opportunistically during the pass)

- **Duplicate SSE emit:** `_heal_failed_stage` publishes `pipeline_status` twice
  (`server.py` ~3796–3797) — copy-paste bug.
- **Uneven cancellation:** only `card_gen` polls `ai_lock.is_cancelled()` among the
  long refresh runs; skeleton/reprints/lands hold the lock but their worker never
  checks, so the Cancel button is a no-op for them (violates conventions §7).
- **Dead selectors:** `data-role="refresh-all"` in mechanics+archetypes
  `setLocked` matches no element (real roles are `mech-refresh-summary` /
  `arch-refresh-all`).
- **`postJSON` shadow:** `project.js` defines a private `postJSON` instead of using
  `W.postJSON`.
- **`hasContent` vs `.length`:** archetypes tracks a `local.hasContent` flag;
  mechanics (its near-twin) gates the same logic on `candidates.length`.
- **Provenance vocab split:** skeleton badges `default`, reprints badges `auto` for
  the same "not user-set" state; badge class `wiz-ai-badge` vs bespoke
  `wiz-reprints-knob-badge`.
- **`bootstrap` 404 policy:** reprints/lands degrade to empty on 404; skeleton
  throws on any non-OK — likely accidental.
- **`setFormLocked` truth source:** plain bool (card_gen, lands) vs composite
  `aiBusy()` (skeleton) — the simpler tabs may under-lock during an engine-driven
  run.
- **Cosmetic:** "Set complete" checkmark is `&#10003;` (card_gen) vs literal `✓`
  (lands); ellipsis differs across Refresh labels.
- **Malformed-body 500:** the ~18 raw `await request.json()` endpoints 500 where the
  `_read_request_json` ones cleanly 400.

## Design

Two new shared layers, mirrored frontend↔backend, each absorbing the patterns
above. The guiding rule: **a new tab should `import`/call a helper, not copy a
block.** The conventions doc is rewritten from "copy this" to "call this."

### Frontend

Extend `window.MTGAIWizard` (the existing `W` surface) — no build step / module
loader, so additions stay as `W.*` functions plus one new file for the heavier
base.

1. **`wizard_util.js` (new, loaded before the tabs)** — leaf helpers hoisted off
   the 22 copies: `W.escHtml`, `W.escAttr`, `W.cssEsc`, `W.tabRoot(id)`,
   `W.tabFooter(id)`, `W.isPastTab(id)`, `W.reportError(resp, data, fallback)`
   (lift skeleton/archetypes' version), `W.fmt.*` number formatters, and the
   `W.mtg` domain constants (`RARITY_ORDER`/`COLOR_ORDER`/labels). Delete the local
   copies. *Lowest risk, highest volume — do this first.*

2. **`W.runAiAction({ confirm, busyLabel, url, body, onResult, lock })`** — owns
   the universal lifecycle: `local.locked` guard → optional `confirm()` →
   `setLocked(true)` → `showBusy(busyLabel)` → `postJSON` → parse-or-`{}` → 409
   `running_action` branch (via `W.reportError`) → network-catch → `finally`
   `clearBusy()` + `setLocked(false)`. Tabs pass only the endpoint + an `onResult`
   repaint. Collapses every `onRefreshAll`/`onRefreshCard`/`refresh*` into one call.

3. **`W.setTabLocked(root, locked, { lockClass, selectors, footerSelector })`** —
   one form-lock implementation; tabs pass their selector set (or, better, mark
   lockable controls with a shared `data-wiz-lock` attribute so the core finds them
   generically). Standardize the truth source on the `aiBusy()` composite
   (own-lock OR streaming OR `stage.status === 'running'`).

4. **`W.fetchStageState(stageId)`** + a documented `{ has_content, stage_status,
   set_params, theme_summary, model_id }` response envelope → returns parsed JSON
   or throws a normalized `HTTP <n>`/`data.error`. Bakes in the graceful-404 path
   (fixing the skeleton divergence). Pairs with `W.emptyStatePanel({ generating,
   generatingMsg, emptyMsg })`.

5. **`W.paintFooter(footer, { isLatest, status, nextName, primary, notes })`** +
   `W.advanceStage(btn, { busyLabel })` + `W.saveAndAdvance({ saveUrl, payload,
   validate, btn })` — owns the `dataset.lastFooter` diff-guard, the
   latest/next preamble, the "Set complete" / `wiz-footer-note` markup, and the
   save→advance→navigate sequence with the button text-spinner. Per-status copy
   stays a per-tab argument.

6. **`W.provenanceBadge(prov)` + `W.markUserEdited(map, key, cardEl)`** — one badge
   component (one class, one vocab: `ai`/`user`/`auto`), one clear-on-edit. Folds in
   reprints' bespoke badge.

7. **`W.KnobPanel`** — a spec-driven bounded-control component (numeric input +
   min–max + step + provenance badge + optional pin + dirty hint + read-back),
   driven by a normalized spec list. Skeleton's server-fed `knobSpecs` is the
   superset shape; reprints supplies specs for its four rarities. Reconciles the
   default/auto vocab and the DOM-vs-`local` read-back split.

8. **`W.registerStream(stageId, { onReset, onItem, mergeKey, repaint })`** — owns
   the `W.on<Tab>Stream` hook assignment, name-dispatch, reset/merge-by-key/append
   bookkeeping, `liveRoot` caching, and terminal cleanup. Tabs supply the merge key
   + repaint. Highest-value extraction because the existing implementations already
   diverge (mechanics' busy-label vs theme's pill) and a new tab would otherwise
   copy a third variant.

9. **Shared tile-grid CSS** — one `wiz-tile` / `wiz-tile-grid` / `wiz-rarity-*` /
   `wiz-tile-locked` block (plus `W.rarityPill(rarity)`), so reprints/lands stop
   re-injecting prefix-renamed copies of the same rules. Skeleton adopts the shared
   `.wiz-stage-empty`. A shared `wizard.css` block is preferable to per-module
   `injectStyles()`.

A thin **`createStageTab({ stageId, mountShell, bootstrap, paint, hasContent })`**
factory can sit on top of #2–#8 to own the `local`/`initialized`/`stageStatus`/
`bootstrapping` lifecycle (patterns the mechanics/archetypes/reprints/lands tabs
share ~80%). Optional — the leaf helpers deliver most of the win even without it.

### Backend

FastAPI dependencies + small helpers in `pipeline/server.py` (or a new
`pipeline/wizard_endpoints.py` helper module). These are mechanical and verifiable
with `pytest`.

1. **`Depends(require_active_project)` / `Depends(require_asset_dir)`** — replace
   the ~28 + ~20 hand-written guard blocks. The happy path receives a resolved
   `ProjectState` / `Path`; the 409 is raised once inside the dependency. Add an
   explicit `read_theme_or_none()` so the "swallow `NoAssetFolderError` → None"
   intent (mechanics/archetypes/skeleton `state`) is named, not re-derived.

2. **`@ai_guarded(label, stage_id, poll_cancel=…)`** (or `async with
   guarded_ai(label) as run_id:`) — the headline collapse. Owns `ai_lock.hold` →
   409, the `try: to_thread(gen) except: 500 {"error": str(exc)}` envelope, and
   `_heal_failed_stage(stage_id)` on success. The single chokepoint to enforce a
   **uniform cancellation contract** (every long worker gets `ai_lock.is_cancelled()`
   polling) and fix the double `pipeline_status` emit. Converge the three
   busy-rejection mechanisms here + on `_project_switch_guard`.

3. **Adopt `_read_request_json` everywhere** (the ~18 raw `await request.json()`
   sites) — one 400 envelope, closes the malformed-body 500 gap.

4. **`_read_json_as(path, list|dict)`** (typed default on shape mismatch, kills the
   re-`isinstance` lines) + **`require_skeleton(asset)`** for the 5 identical
   skeleton-presence gates.

5. **`stage_state_base(stage_id, settings)`** returning the common `{ set_params,
   theme_summary, model_id, stage_status }` tail; each `state` endpoint merges its
   tab-specific payload. + **`_next_stage_nav(stage_id)`** for the `save` family.

6. **`pipeline/stage_hooks.py`** — the `on_reset`/`on_draft`/`on_finalized`/
   `on_slot`/`card_saved` lambdas + the finalized-persist/collision-tag logic,
   imported by **both** the engine stage runner and the refresh endpoint. Refresh
   endpoints construct a real `StageEmitter(event_bus, stage_id, …)` and reuse the
   *same* lambdas, so the engine and refresh paths can't drift in payload shape.

7. **`validate_and_persist_knobs(spec, body, asset)`** for the shared knob-write;
   `_skeleton_knobs_from_body(body)` for the intra-skeleton payload-overlay dup.

## Why this shape

- **Leaf-helpers-first, factory-last.** Hoisting `escHtml`/`reportError`/`runAiAction`
  is mechanical and independently shippable; the `createStageTab` factory and
  `KnobPanel` are bigger and can land later (or not at all) without blocking the
  cheap wins. Each phase is a self-contained PR.
- **No new frontend build step.** Everything stays `W.*` on the existing global +
  one new `<script>` in `wizard.html`'s `{% block scripts %}` ahead of the tabs —
  consistent with how `wizard.js`/`wizard_stage.js` already load.
- **Backend dependencies are the idiomatic FastAPI answer** to repeated prologue
  blocks; they're testable in isolation and shrink each endpoint to its real work.
- **Follows the §15 precedent.** `_heal_failed_stage` already proved that collapsing
  per-stage one-offs into one helper + a documented convention is the right move
  here; this extends it to the rest.
- **The convention becomes executable.** Today `wizard-tab-conventions.md` is a
  "copy this" checklist a human must apply by hand to each new tab; after the pass
  it's a "call this" reference, so a new tab inherits §1–§13 behavior by construction
  and can't silently drift.

## Sequencing (each phase independently shippable)

1. **F1 — leaf helpers** (`escHtml`/`escAttr`/`cssEsc`/`tabRoot`/`reportError`/
   `fmt`/`mtg` → `wizard_util.js`; delete copies). Pure mechanical, zero behavior
   change. Sweep the dead-selector / `postJSON`-shadow / checkmark-encoding nits
   here.
2. **B1 — backend dependencies** (`require_active_project`, `require_asset_dir`,
   `read_theme_or_none`, adopt `_read_request_json`). Mechanical; `pytest` covers it.
3. **F2 — `runAiAction` + `setTabLocked`**, migrate one tab (mechanics) as the
   reference, then the rest. Standardize the lock truth source.
4. **B2 — `@ai_guarded`** + uniform cancellation + the `_heal_failed_stage`
   double-emit fix. Migrate refresh endpoints onto it.
5. **F3 — `fetchStageState` envelope + `paintFooter`/`advanceStage`/`saveAndAdvance`
   + `emptyStatePanel`**; **B3 — `stage_state_base` + `_next_stage_nav`**.
6. **B4 — `stage_hooks.py`** (engine↔refresh hook dedup); **F4 — `registerStream`**.
7. **F5 — `provenanceBadge` + `KnobPanel` + shared tile-grid CSS**; **B5 — knob-write
   helpers**.
8. **Optional F6 — `createStageTab` factory** once the helpers it composes exist.
9. **Docs — rewrite `wizard-tab-conventions.md`** §2/§3/§4/§7/§13 to reference the
   new helpers; add a short "shared helpers" index.

## Out of scope / non-goals

- The art/render/review tabs (`art_*`, `render*`, `human_*`, `balance`,
  `finalize`, `skeleton_rev`, `visual_refs`) — the same helpers should serve them,
  but this pass is scoped to Theme→Card Generation. Migrating the rest is a
  follow-up that rides the same primitives.
- No behavior changes beyond the inconsistencies explicitly listed; this is a
  reuse/consistency pass, not a redesign of any tab's UX.
- No frontend bundler / framework introduction — stay on the plain-`W` global.
- The display-only reprint-materialization gap (tracked separately) is untouched.

## Risks & verification

- **No JS test harness.** Frontend phases need per-tab manual verification (mount,
  refresh, lock-during-gen, save & advance, edit cascade, failure modal). Keep each
  PR to one pattern across all tabs so the manual matrix is "re-test this one
  behavior on N tabs," not "re-test N tabs wholesale." `run`/`verify` skills against
  `python -m mtgai.review serve` cover the smoke path.
- **Backend phases** run `ruff` + `pytest` from `backend/`; the dependency/decorator
  swaps are behavior-preserving and unit-testable (busy 409, no-project 409,
  no-asset 409, malformed-body 400).
- **Drift risk during migration:** land F1/B1 (mechanical, no behavior change)
  first to shrink the surface before the behavior-bearing phases.
