# Wizard UI Redesign — Design Doc

**Status:** Draft, awaiting approval before implementation.
**Owner:** Coamithra
**Date:** 2026-05-05

---

## 1. Problem

The current `/pipeline` UI is a flat dashboard with sibling tabs that don't reflect the linear, dependency-driven nature of the pipeline. Users can't tell at a glance which stage is "live," can't break out of full-auto mode without going to a separate Configure page, and can't make targeted edits to a finished stage without manually invalidating downstream artifacts. The Theme tab is the only stage that already feels like a wizard step (live progress, editable sub-items, manual refresh) — the rest should follow that pattern.

A second, related problem: model assignments are a process-wide singleton (`get_settings()` loaded from `output/settings/current.toml`). Changing the LLM for `card_gen` while a set is mid-run silently affects that set's next stage. Settings that influence a run should travel with the run.

## 2. Goals

- Replace the flat tab dashboard with a **linear wizard**, one tab per pipeline stage, fronted by a **Project Settings tab** that owns set-level configuration and theme inputs.
- Make break points (manual halts) **first-class in the wizard header**, not buried in a Configure page.
- Allow targeted **edits to past stages** with explicit, warned cascading invalidation.
- Move per-run settings (model assignments, break points, theme input) onto the per-set settings file. Keep global settings to a small, well-defined set.
- Keep the pipeline's existing resumability, AI-mutex, and active-set semantics.
- Keep per-stage internal UI minimal in v1 — defer per-stage richness (Art grid, AI-review iteration view, etc.) to follow-up work.

## 3. Non-goals (deferred)

- Per-stage editor UIs beyond what already exists. Some stages already have meaningful UI today (Theme; Skeleton; Lands; Reprints) and those carry over into the wizard shell as-is. The remaining stages ship in v1 as a progress bar + summary block, with rich per-stage UIs landing iteratively as follow-ups.
- Selective downstream invalidation (e.g., editing one mechanic only invalidates affected cards). v1 = blanket clear from edit-point onward.
- Snapshot/rollback of cleared artifacts. v1 = clear is destructive, with strong warning.
- Multi-user / multi-browser concurrency (still governed by global AI mutex; no new locking).

---

## 4. Conceptual model

### 4.1 Stages → Wizard tabs

The wizard has one tab per pipeline stage, in pipeline order, plus a **Project Settings** tab as the kickoff. There is a strict division of concerns between the kickoff tab and the Theme stage:

- **Project Settings** owns everything **structural / numeric** about a set: set code, set name, target size, rarity targets, model assignments, break points, theme input source.
- **Theme** owns everything **content-extracted from the user's prose**: the extracted theme summary, thematic constraints (e.g., "must feature orcs", "no dragons"), card requests / suggestions. Nothing numeric or set-shape lives here.

This split is what lets every stage downstream of Project Settings auto-run with no special cases.

| Order | Tab ID                | Tab title             | Notes |
| ----: | --------------------- | --------------------- | ----- |
|     – | `project`             | Project Settings      | **The only tab that needs user input to advance.** Owns set parameters, model assignments, break points, theme input (PDF/text upload or pick existing `theme.json`), and the **"Start project"** button. Always present. |
|     0 | `theme`               | Theme                 | Auto-runs from inputs prepared on the Project Settings tab. |
|     1 | `skeleton`            | Skeleton              | |
|     2 | `reprints`            | Reprints              | |
|     3 | `lands`               | Lands                 | |
|     4 | `card_gen`            | Card Generation       | |
|     5 | `balance`             | Balance Analysis      | |
|     6 | `skeleton_rev`        | Skeleton Revision     | Iterates with `balance` — handled internally; tab shows final. |
|     7 | `ai_review`           | AI Design Review      | |
|     8 | `finalize`            | Finalization          | |
|     9 | `human_card_review`   | Card Review           | `always_review` — wizard treats this identically to a hard break. |
|    10 | `art_prompts`         | Art Prompts           | |
|    11 | `char_portraits`      | Character Portraits   | |
|    12 | `art_gen`             | Art Generation        | |
|    13 | `art_select`          | Art Selection         | |
|    14 | `human_art_review`    | Art Review            | `always_review`. |
|    15 | `rendering`           | Card Rendering        | |
|    16 | `render_qa`           | Render QA             | |
|    17 | `human_final_review`  | Final Review          | `always_review`. |

Promoting Project Settings to a wizard tab means **every other tab follows the same auto-advance pattern** — Theme is no longer special. The user-input gate is the Start button on Project Settings; once clicked, downstream tabs spawn and run on the same rules as everything else.

A separate **Global Settings** page (not a wizard tab) lives at `/settings` for cross-set defaults (see §7).

### 4.2 Tab visibility

- **Brand new project:** only the **Project Settings** tab is visible. The wizard does not pre-create downstream tabs.
- A new tab is **created and opened** when the prior stage completes (or when the user clicks "Next: <stage>" if a break is in effect; or when the user clicks "Start project" on the Project Settings tab to spawn the Theme tab).
- Tabs are never closeable.
- Once a tab exists, it is reachable from the tab strip even if the user is on a later one.

### 4.3 "Latest tab" / current vs. past

- **Latest tab** = the furthest-along tab that has been created (regardless of generating/done/errored). Project Settings is "past" once Theme has spawned — it's accessible but read-only by default.
- Only the **latest tab** is editable by default. Past tabs are read-only until the user clicks "Edit" in the header (§9).
- The user can freely **navigate** between any visible tab; navigation does not cancel or pause anything (matches current `extraction_run` broadcast semantics).

---

## 5. Settings scope — global vs per-set

### 5.1 Per-set settings (new)

Stored under `output/sets/<SET>/settings.toml` (separate file from `pipeline-state.json` so settings can be edited without touching live run state):

| Setting | Source today | Per-set rationale |
| --- | --- | --- |
| `llm_assignments` (per stage) | global `current.toml` | Model choice changes mid-run; locking it to the set lets you change defaults safely. |
| `image_assignments` (per stage) | global `current.toml` | Same. |
| `effort_overrides` (per stage) | global `current.toml` | Same. |
| `stage_review_modes` (break points) | already on per-set `PipelineConfig` | No change — stays per-set. |
| Set parameters (`set_code`, `set_name`, `set_size`) | already per-set | No change. |
| Theme input source (PDF path / pasted text / "loaded from file") | implicit in `theme.json` today | Captured for resumability and audit. |

### 5.2 Global settings (kept global)

| Setting | Storage | Why global |
| --- | --- | --- |
| **Default preset for new sets** | `output/settings/global.toml` (new) | A user-level default; new sets bootstrap their per-set settings from this. |
| **Saved profiles library** | `output/settings/<profile_name>.toml` (existing, minus `current.toml`) | Library of reusable templates spanning sets. Apply-to-set is a one-shot copy. |
| **Active set picker** | `output/settings/last_set.toml` (existing) | UI state, not a run-affecting setting; stays as-is. |
| **Model registry** | `backend/mtgai/settings/models.toml` (existing) | Catalog of available models; structural, not a user setting. |

### 5.3 API refactor

- `get_settings()` (no-arg, singleton) becomes deprecated. Replace with `get_settings(set_code: str)` returning the per-set `ModelSettings`, loading from `output/sets/<set>/settings.toml`.
- Convenience functions (`get_llm_model(stage_id)`, `get_image_model(stage_id)`, `get_effort(stage_id)`) gain a `set_code` parameter. Every existing pipeline stage runner already has `set_code` in scope — mechanical refactor.
- Cache: per-set settings file is small (~1 KB TOML). A `dict[set_code, ModelSettings]` cache invalidated on save fits naturally.

### 5.4 Migration

- **New sets:** at set creation (folder creation in `output/sets/<SET>/`), seed `settings.toml` from `output/settings/global.toml` (which itself is seeded from the legacy `current.toml` on first run).
- **Existing sets without `settings.toml`:** on first load, copy from current global `current.toml`, then write the per-set file. One-time silent migration.
- **`current.toml`:** retired after migration. The "current state" is now whichever set is active in the top-bar picker.

### 5.5 Mid-run mutation

- Changing model assignments on an in-progress set affects only that set, only future stage runs.
- **Decision:** model assignments are read **once at stage start**, cached on the running `StageState`, and not re-read mid-stage. Prevents accidental mid-stage swaps if a user toggles a dropdown while `card_gen` is iterating.

---

## 6. Project Settings tab

The Project Settings tab is the kickoff surface of the wizard. It owns everything the user defines about a set and is the only tab that requires explicit user action to advance the pipeline.

### 6.1 Layout

```
┌──────────────────────────────────────────────────────────────┐
│ Project Settings — <SET CODE>                                │
│                                                              │
│  ─ Set parameters ─                                          │
│   Set code: ASD     Name: …     Target size: 60              │
│   Rarity split: C 40% U 33% R 22% M 5%   (or counts)         │
│                                                              │
│  ─ Theme input ─                                             │
│   ◉ Upload PDF / paste text   [drop zone / textarea]         │
│   ○ Load existing theme.json  [picker]                       │
│   Status: <none chosen> | <ready: ASD-pitch.pdf>             │
│                                                              │
│  ─ Break points ─                                            │
│   ☐ Break after Theme                                        │
│   ☐ Break after Skeleton                                     │
│   ☑ Break after Card Generation                              │
│   …                                                          │
│   (locked-on rows for the three human_* stages)              │
│                                                              │
│  ─ LLM model assignments ─                                   │
│   Theme Extraction:    [Haiku ▾]                             │
│   Mechanic Generation: [Sonnet ▾]                            │
│   Card Generation:     [Opus ▾]   Effort: [Max ▾]            │
│   …                                                          │
│   Estimated cost per set: $X.XX                              │
│                                                              │
│  ─ Image model assignments ─                                 │
│   Character Portraits: [Flux Local ▾]                        │
│   Art Generation:      [Flux Local ▾]                        │
│                                                              │
│   Apply preset to this set:                                  │
│   [ Recommended ] [ Cheap ] [ Local ] [ <profile> ]          │
│   [ Save current as profile ]                                │
│                                                              │
│ ──────────────────────────────────────────────────────────── │
│                                  [ Start project ]           │
└──────────────────────────────────────────────────────────────┘
```

### 6.2 New-project flow

1. User opens the app. Top-bar picker shows existing sets or **"+ New project"**.
2. Clicking "+ New project" prompts for set code (and pre-fills name); the wizard creates `output/sets/<SET>/` and seeds `settings.toml` from `output/settings/global.toml`.
3. The wizard opens with only the **Project Settings** tab. Fields are editable.
4. User picks a theme input (upload PDF / paste text / pick existing `theme.json`), tweaks model assignments and break points if desired.
5. **"Start project"** is enabled once a theme input is chosen. Click → wizard spawns the Theme tab and starts the theme extractor with the chosen inputs.
6. Auto-advance handles the rest, subject to break points.

### 6.3 Existing-project flow

1. User picks an existing set in the top-bar picker.
2. Wizard loads, reconstructs all tabs that have artifacts (§11), and lands on the latest tab.
3. Project Settings tab is accessible from the tab strip; in this state it is **past** (not the latest tab) and read-only by default.
4. To change settings, the user clicks **Edit** in the Project Settings header — see §6.4.

### 6.4 Editing the Project Settings tab — two flavors

Project Settings is unique in that not all of its fields invalidate downstream work equally. We treat its sub-sections differently:

**Live-apply changes (no cascade clear):**
- **Model assignments** (LLM / image / effort) — affect only future stage runs (already-generated artifacts are valid regardless of which model produced them).
- **Break points** — affect only future stage transitions.
- **Set name** — cosmetic.

These are always editable directly, no Edit-button gate, no warning. They write through to `settings.toml` immediately. Mid-run, they take effect at the next stage start (per §5.5).

**Cascade-clear changes (full warning + downstream wipe):**
- **Set code** — identifier; rename is treated as create-new (out of scope for v1; show as read-only).
- **Target size** — changes the skeleton; invalidates skeleton onward.
- **Theme input** (re-uploading a different PDF, switching source) — invalidates everything from Theme onward.

Editing these requires the standard Edit flow described in §9 (modal warning enumerating what gets cleared, pencil indicator, Cancel/Accept).

### 6.5 Kill `skip`

- Remove `skip` mode from the UI.
- Drop `skip_stages` from `PipelineConfig` writes (UI never sets it).
- `StageStatus.SKIPPED` stays in the enum for internal use (e.g., a set with no character cards auto-skipping `char_portraits` based on inputs — confirm during implementation), but is not user-selectable.

### 6.6 Break points

- Every stage runs auto **unless** it has a break point set. Break point = "after this stage finishes, halt — wait for me to click 'Next' before creating the next tab."
- UI: one checkbox per stage, **"Break after <stage>"**. The three `always_review` stages (`human_card_review`, `human_art_review`, `human_final_review`) show as locked-on with a tooltip "Always pauses for review."
- Persistence: existing `stage_review_modes` dict on `PipelineConfig` reused — `REVIEW` = break, `AUTO` = no break. (Two-value flag now.)

### 6.7 Per-tab override: "Stop after this step"

- Each non-Project-Settings wizard tab's header has a **"Stop after this step"** checkbox.
- Effect = same as setting a break point on Project Settings, just for this one stage.
- **Precedence rule (union):** if either the Project Settings break point or the per-tab checkbox is set, the pipeline halts. Either alone is sufficient.
- Persistence: checkbox state writes through to `stage_review_modes` for that stage. Single source of truth.

### 6.8 Save current as profile

- Captures the current per-set settings (LLM/image/effort + break points, **excluding** set parameters and theme input) into the global profile library at `output/settings/<profile_name>.toml`.
- Profiles can later be applied to other sets via the per-set preset row.

---

## 7. Global Settings page (`/settings`)

Distinct from the wizard. Reachable from a top-bar nav link. Does **not** affect any active set directly; it's the default-and-library page.

Sections:

- **Default preset for new sets.** Dropdown over built-in presets + saved profiles. Stored in `output/settings/global.toml`.
- **Saved profiles library.** List of named profiles; rename / delete / view contents. Apply-to-set is exposed via the Project Settings tab, not here.
- **Model registry (read-only).** A table view of `models.toml` so the user can see what's available without leaving the app. Editing is still file-based for now.

The old `/pipeline/configure` route redirects to the active set's Project Settings tab (`/pipeline/project`). The old per-stage assignment table on `/settings` moves into the Project Settings tab.

---

## 8. Tab anatomy (non-Project-Settings tabs)

Every stage tab has the same skeleton:

```
┌─────────────────────────────────────────────────────────────┐
│ GLOBAL HEADER  (set picker · global progress strip · etc.)  │
├─────────────────────────────────────────────────────────────┤
│ TAB STRIP  [ Project ] [ Theme ✏️ ] [ Skeleton ] [ Cards … ] │
├─────────────────────────────────────────────────────────────┤
│ TAB HEADER                                                  │
│   Title · Status pill                                       │
│   Live process line  (e.g. "LLM: drafting card C-12 (4/60)") │
│   ▢ Stop after this step          [ Edit ]  [ Refresh ]     │
├─────────────────────────────────────────────────────────────┤
│ TAB BODY                                                    │
│   v1: progress bar + summary block + per-stage event log    │
│   Theme: existing rich UI (constraints, suggestions, etc.)  │
├─────────────────────────────────────────────────────────────┤
│ TAB FOOTER                                                  │
│              [ Next step: <next stage name> ]               │
└─────────────────────────────────────────────────────────────┘
```

### 8.1 Global progress strip

- Fixed at top across all tabs (not per-tab).
- Shows: which stage is currently generating, % complete, current item, cancel button.
- Sourced from the existing pipeline SSE bus.

### 8.2 Tab header

- **Live process line:** mirrors what the Theme tab already shows ("LLM: …", "Validator: …"). Backed by the existing SSE event stream for that stage.
- **"Stop after this step" checkbox** (§6.7). Not present on Project Settings (it's pre-Theme — there's nothing in front of it to "stop after").
- **"Edit" button** (§9) — disabled on the latest tab (it's already editable) and on any tab currently generating.
- **"Refresh"** — re-runs the stage from scratch on the current tab. Shows a confirm if the stage has downstream-affecting outputs.

### 8.3 Tab body — v1

- **Theme:** existing UI **minus the upload widget and any numeric set-shape fields** — those moved to Project Settings (§4.1). Theme keeps only the extracted content surface: theme summary, thematic constraints, card requests / suggestions, refresh-per-subitem controls. If the current `theme.json` schema mixes numeric and content fields, the split happens during the Project Settings phase (§14.5) and is called out in §15.
- **Skeleton, Lands, Reprints:** already have meaningful UI today; carry over as-is into the wizard shell. Minor reskinning to fit the tab anatomy (header / body / footer) is OK; substantive redesign is out of scope.
- **Every other stage** (Card Generation, Balance, Skeleton Revision, AI Review, Finalize, Art Prompts, Character Portraits, Art Generation, Art Selection, Rendering, Render QA, and the three `human_*` review stages): progress bar + summary block ("60 cards generated, 3 retries, $0.42 spent") + the existing event log scroll. **No new per-stage UI in v1.**
- Per-stage rich UIs (Art grid, AI Review iteration view, Skeleton-revision diff, etc.) ship as follow-up cards, one per stage.

### 8.4 Tab footer — Next button

- Single primary button: **"Next step: <next stage display name>"**.
- On Project Settings the button text is **"Start project"** (and the next stage is Theme).
- Visible/enabled when:
  - Stage is `COMPLETED` or `PAUSED_FOR_REVIEW`, **and**
  - This is the latest tab.
- Clicking creates the next tab, navigates to it, and starts the next stage (subject to its own break point).
- When the next stage's break point is **off** and the current stage finishes successfully, the wizard performs this transition automatically — i.e., the user doesn't have to click. (Project Settings is the exception: even with no break points anywhere, the user always clicks Start to kick off Theme.)
- On the final tab (`human_final_review`), the button is replaced with a "Set complete" state.

---

## 9. Editing a past tab

### 9.1 Entering edit mode

- User clicks **"Edit"** in the header of a past tab.
- Wizard shows a modal warning:

  > **Editing this stage will discard all generated content from later stages.**
  >
  > The following will be cleared and regenerated when you accept:
  >  • Cards (60)
  >  • Card art (60)
  >  • Renders (60)
  >  • AI review notes
  >
  > Cancel to keep things as they are. Continue to start editing — your changes won't take effect until you Accept.

- The modal enumerates **exactly which artifacts get cleared** (computed from the pipeline state — completed downstream stages and their item counts). Wording stays explicit, not euphemistic.
- "Continue" puts the tab into edit mode; nothing is cleared yet.
- **Project Settings exception:** model-assignment and break-point edits do not require this gate (§6.4). Only set-param / theme-input edits do.

### 9.2 Editing UX

- Edit-mode tab gets a **pencil indicator** (`✏️`) in its tab-strip label and a banner "Editing — changes not yet applied."
- The tab's editable controls (same as when it was the latest tab) become live again.
- The **"Edit" button** is replaced by a pair: **"Cancel"** (revert local state, exit edit mode) and **"Accept"** (commit + cascade-clear + regenerate from next stage).
- The footer's "Next step" button is hidden during edit mode.
- **Navigation while editing:** user can switch tabs freely — the in-progress edit state is held locally in the wizard (per-tab). The pencil icon stays on the tab strip. No autosave to disk; nothing is mutated until Accept. Cancel discards the local edits.
- **Two simultaneous edit sessions** (edit Project Settings, navigate to Skeleton, click Edit there) — allowed; each tab's pencil persists. Accepting one doesn't affect the other's draft state, but the cascade may invalidate the other (e.g., accepting Project Settings clears Skeleton, including any draft edits on it). Show a "draft on a downstream tab will be lost" warning in the Accept confirm.

### 9.3 Accept = cascade clear + regenerate

On **Accept**:

1. Persist the tab's edits to the stage's input artifact (e.g., `theme.json`, `settings.toml`).
2. Reset all stages **after** this one to `PENDING`, clear their `progress`, and delete their on-disk artifacts (cards, art, renders, etc. — the existing artifact-write paths know what they own; we add a stage-level `clear_artifacts(set_code)` callback).
3. Save `pipeline-state.json`.
4. Close all wizard tabs after the edited one (tab strip shrinks back).
5. Auto-run the next stage (subject to break point). Project Settings is the exception: Accept on a theme-input change brings the user back to "Start project" state — it does not auto-run Theme. (Mirrors the new-project flow where the user must click Start.)

### 9.4 Latest-tab editing — no Edit button needed

The latest tab is editable in place — no Edit button, no warning. Same UX as today's Theme tab when you're on it: tweak constraints, click refresh on a sub-item.

---

## 10. Auto-advance + AI mutex interaction

- The AI mutex remains globally enforced — only one stage runs at a time.
- **Auto-advance triggers** when a stage finishes successfully *and* the stage has no break point *and* no per-tab "Stop after" override.
- **Project Settings never auto-advances.** Theme spawns only on explicit "Start project."
- **On failure**, auto-advance does **not** fire. The tab enters a fail state with the error message and a Retry button. The latest-tab pointer stays on the failed tab.
- **User on a non-latest tab when current finishes:** auto-advance still fires. **Decision: do not steal focus.** Create the new tab in the strip, start its work, but leave the user on whatever tab they're viewing. The global progress strip tells them work has moved on.

---

## 11. Resume / startup states

When the wizard loads (or the active set switches), startup logic resolves to one of these:

| State | Trigger | Wizard behavior |
| --- | --- | --- |
| **Brand new** | Set folder exists but no `theme.json` and no `pipeline-state.json` | Show only Project Settings tab, in editable state. Start button disabled until a theme input is chosen. |
| **Started, mid-run, no error** | Some stages `COMPLETED`, one stage `RUNNING` | Re-create Project Settings + all completed tabs + the running tab. Land on the running tab. Global progress strip resumes streaming SSE for it. |
| **Paused for review** | A stage is `PAUSED_FOR_REVIEW` (break hit) | Same as mid-run, but the latest tab shows the "Next step" button enabled instead of progress. |
| **Errored** | Last stage is `FAILED` | Re-create Project Settings + completed tabs + the failed tab. Latest tab shows the error block + Retry button. **Auto-advance does not fire.** |
| **Fully complete** | All stages `COMPLETED` | All tabs exist, all read-only. The user can browse them; clicking Edit on any tab works as in §9. |
| **Mid-run, but server restarted** | State has a `RUNNING` stage but no actual job is running | On boot, demote any `RUNNING` stage with no live job to `FAILED` with message "Interrupted — server restart." User retries manually. *(Implementation: detect on engine init; rewrite state once.)* |

**Save semantics:** there is no explicit "save" button. State writes to `pipeline-state.json` on every transition (already true today). Live-apply Project-Settings changes write to `settings.toml` immediately. Edit-flow drafts (§9) stay in-memory until Accept.

**Active-set switch mid-run:**
- Switching the active set while a stage is generating cancels that generation (existing behavior — the AI mutex caller checks `ai_lock.is_cancelled()`).
- Show a confirm dialog: "Switching sets will cancel the running stage on <SET>. Continue?"
- After confirm, the new set's wizard loads in whichever startup state matches.
- *Open:* on switching back later, do we auto-resume the cancelled stage? **v1: no.** The cancelled stage is `FAILED` ("Cancelled by set switch"); user clicks Retry.

---

## 12. Failure handling

- Stage runners already return `StageResult(success=False, error_message=…)` and write `progress.error_message`. The tab body surfaces this directly.
- A failed tab shows: error message, last item attempted, optional traceback (collapsible), **Retry** button.
- Retry re-runs the stage from the start (same semantics as today's "rerun").
- Auto-advance is gated on success only — never fires on failure.
- A failed `human_*` review stage doesn't really exist (they're paused-for-input, not running) — so this only applies to AI/automated stages.

---

## 13. URL routing

- Wizard root: `/pipeline`.
- Project Settings: `/pipeline/project`.
- Each pipeline stage tab: `/pipeline/<stage_id>` (e.g., `/pipeline/theme`, `/pipeline/skeleton`).
- Global Settings: `/settings`.
- On load:
  - If the URL points to a wizard tab that doesn't exist yet for this set, redirect to the **latest tab** (or `/pipeline/project` if brand new).
  - `/pipeline/configure` (legacy) → `/pipeline/project`.
- Refresh always lands on the same URL.
- Tab-strip clicks update the URL via `history.pushState`.

---

## 14. Implementation phases

Roughly in order; each phase ships independently.

1. **Settings refactor.**
   - Per-set `settings.toml` schema + load/save. Add `get_settings(set_code)` API; deprecate the singleton.
   - One-time migration: existing sets get `settings.toml` seeded from `current.toml`.
   - Introduce `output/settings/global.toml` for default-preset and seed it from existing `current.toml`.
   - Thread `set_code` through `get_llm_model`/`get_image_model`/`get_effort` callers.
   - Cache `StageState`-level resolved model at stage start (lock against mid-stage mutation).

2. **Schema & server prep.**
   - Drop `skip_stages` from UI-facing config (keep enum value for internal auto-skip).
   - Confirm `stage_review_modes` 2-value semantics.
   - Add `clear_artifacts(set_code)` per stage runner (no-op for stages without artifacts).
   - Add startup-cleanup: demote orphaned `RUNNING` stages to `FAILED` on engine init.

3. **Global Settings page.**
   - Trim `/settings` to: default preset + saved-profiles library + read-only registry view.
   - Move per-stage assignment table out of `/settings` (it's going to the Project Settings tab).

4. **Wizard skeleton.**
   - Tab strip + global progress strip + tab shell (header / body / footer).
   - URL routing.
   - Startup state resolution from `pipeline-state.json` + `settings.toml`.
   - Theme tab plugged into the new shell **with the upload widget removed** (it moves to Project Settings).
   - Other tabs render as progress-bar-plus-summary placeholder bodies.

5. **Project Settings tab.**
   - New first tab. Set parameters + theme input + break points + LLM/image assignments + presets + Save-as-profile.
   - **Start project** button kicks off Theme.
   - Live-apply for model/break-point edits; edit-flow gate for set-param / theme-input edits.

6. **Per-tab break-point checkbox** in the header (non-Project-Settings tabs), wired to `stage_review_modes`.

7. **Auto-advance + Next-step button** logic, including failure gating, Project-Settings exception (no auto-advance), and the "don't steal focus" rule.

8. **Edit flow.**
   - Edit button + warning modal with cascade enumeration.
   - In-memory draft state per tab + pencil indicator.
   - Accept → cascade clear + regenerate.
   - Cancel → revert.

9. **Per-stage UI iteration** (one card per stage; defer until §1–8 are stable).

---

## 15. Open questions

- **Conditional skip:** is there ever a stage that's structurally not applicable for a given set (e.g., `char_portraits` when the set has zero characters)? If yes, those should auto-`SKIPPED` based on inputs, not user toggle. Confirm during implementation.
- **Editing while downstream is running:** spec'd to allow it (you can open Edit on Project Settings while Cards is generating). The Accept confirm explicitly states "this will cancel the in-flight <stage> run." Cancel uses existing mutex `is_cancelled()` path.
- **Long-running per-card stages (Art, Render):** the v1 progress-bar body is accurate but minimal. Likely first to need a real per-stage UI.
- **Cancellation of an in-progress edit** when the user closes the browser: edits are in-memory, so they're lost. Accept this for v1 (matches the no-save-button principle — explicit Accept is the only commit).
- **Set code rename:** v1 treats set code as immutable post-creation (read-only on Project Settings once Theme has run). Worth revisiting if the user actually wants to rename.
- **New project bootstrap UX:** does "+ New project" prompt for set code in a modal before opening the Project Settings tab, or does the tab itself host the empty state? Probably the latter (one fewer dialog), but pin down during phase 5.
- **`theme.json` schema split:** today's theme extractor produces a single artifact that may mix numeric set-shape fields (e.g., target size, rarity counts) with thematic content (theme summary, constraints, card requests). To honor the §4.1 split, audit `theme_extractor.py` outputs and migrate any numeric fields to `settings.toml` / `PipelineConfig`. Theme stage's job becomes purely content extraction; numeric defaults are read from Project Settings before extraction starts and used to *guide* extraction (e.g., "produce ~22 rare card requests"), but Theme does not own those numbers.

---

## 16. Trello

Suggested card breakdown (one per phase in §14):

- `refactor` Wizard UI: per-set settings + global.toml split
- `feature` Wizard UI: schema & server prep
- `feature` Wizard UI: trim global Settings page
- `feature` Wizard UI: wizard shell + URL routing + startup
- `feature` Wizard UI: Project Settings tab + Start kickoff
- `feature` Wizard UI: per-tab break-point checkbox
- `feature` Wizard UI: auto-advance + Next-step
- `feature` Wizard UI: edit flow + cascade clear
- (later) per-stage UIs, one card each
