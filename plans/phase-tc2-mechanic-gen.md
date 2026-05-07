# Phase TC-2: Mechanic Generation (Wizard Tab + Pipeline Step)

> Trello: [TC-2 Mechanic generation pipeline stage](https://trello.com/c/yw02hjGi)
> Companion: [Move skeleton revision to pre-card-gen](https://trello.com/c/sMSqWKw6)
> Status: SPEC (drafted 2026-05-07)

## Purpose

Generate the set's 2–4 custom mechanics from the extracted theme **before** skeleton generation runs. Today the only place that produces `mechanics/approved.json` is a half-wired ASD-hardcoded `generation/mechanic_generator.py` that was driven manually for the dev set. Every downstream stage that reads `approved.json` (skeleton revision, card generation, reminder injection, AI review, finalization, balance analysis) assumes the file already exists — so without an actual generation step, the pipeline can't run for any set besides ASD.

## Where it sits

Current pipeline (`pipeline/stages.py:STAGE_RUNNERS`):

```
[theme extraction]  →  skeleton  →  reprints  →  lands  →  card_gen  →  balance  →  skeleton_rev  →  ai_review  →  ...
```

Target pipeline (this card + sister card sMSqWKw6):

```
[theme extraction]  →  mechanics  →  skeleton  →  constraints (was skeleton_rev)
                                              →  reprints  →  lands  →  card_gen  →  balance  →  ai_review  →  ...
```

`mechanics` is a real stage — first entry in `STAGE_RUNNERS`, registered alongside skeleton, reprints, etc. It runs through the standard stage tab UI (`wizard_stage.js`) and gets all the standard plumbing for free: stage status pill from `PipelineState.stages[i].status`, `Stop after this step` toggle reading the regular `break_points` map, `stage_update` SSE events, cancel button, edit cascade. Its tab body is bespoke (candidates strip with picks + inline edits) but the shell is the same as every other stage.

The skeleton generator itself stays "complexity-tier only"; specific mechanic-to-slot mapping happens in the constraints stage that consumes `approved.json` + `theme.json` + `skeleton.json`.

## Pipeline ordering decision: mechanics before skeleton

Two viable orderings exist. We pick **mechanics → skeleton** for these reasons:

1. **Mechanics shape the slot mix.** `set_template.json` rarity / CMC / type ratios are mechanic-agnostic averages. But a Salvage-heavy set wants more artifacts; a Saga-heavy set wants enchantment slots; a tokens-matter set wants creature slots that produce tokens. The skeleton's first cut should know this. The constraints stage then fine-tunes; it shouldn't be doing all the work.
2. **The user reviews mechanics in isolation.** If skeleton runs first and mechanics second, the user would read 280 slot rows trying to imagine which mechanic each one will eventually use. With mechanics first, the user reads 6 candidates → picks 3 → edits names/reminders, all on a clean tab, before the structural noise of slot allocation shows up.
3. **Cost asymmetry.** Mechanic gen is one LLM call (~$0.10). Skeleton gen is deterministic. Iterating on mechanics doesn't trigger expensive reruns downstream; iterating after skeleton would.

The cost: skeleton generation needs `approved.json` to exist when it runs. That's fine — `mechanic_count` from `set_params` already tells the skeleton how many mechanic slots to reserve, and the actual mechanic→slot mapping lives in the constraints stage anyway.

## Inputs

From the active project's settings + theme.json:

| Source | Field(s) | Use |
|--------|----------|-----|
| `theme.json` | `theme`, `flavor_description`, `draft_archetypes`, `creature_types`, `flavor_text_guidelines.themes` | Setting prose for the LLM to draw flavor connections from |
| `theme.json` | `legendary_characters`, `notable_cards` | Avoid mechanic name collisions with character / card names; flag mechanics that fit specific characters |
| `theme.json` | `special_constraints` | Additional design constraints (e.g. "no graveyard recursion in this set") |
| `set_params` | `mechanic_count` | How many mechanics to approve (default 3, configurable per project). LLM still proposes 6 candidates, user picks `mechanic_count` of them. |
| `set_params` | `set_size` | Sets the rough density target the LLM uses to propose `distribution` per mechanic |
| Model registry | `llm_assignments["mechanics"]` | Which model to call. Mirrors theme extraction — registry-driven, not hardcoded. |

No code paths read `theme.json` for mechanic gen today. This is the first consumer downstream of theme extraction, and the contract is fixed by `output/sets/ASD/theme.json` — verbatim keys above.

## Outputs

Same shapes as the existing ASD files so all downstream consumers (`generation/skeleton_reviser.py`, `generation/card_generator.py`, `generation/reminder_injector.py`, `review/ai_review.py`, `review/finalize.py`, `analysis/balance.py`) keep working unchanged.

Written to `<asset_folder>/mechanics/`:

- `candidates.json` — full list of 6 LLM-proposed candidates (audit trail; not consumed downstream).
- `approved.json` — the user's pick of `mechanic_count` mechanics, possibly edited. Schema **already locked** by ASD:
  ```
  name, keyword_type, reminder_text, colors, complexity,
  flavor_connection, design_notes, rarity_range,
  common_patterns, uncommon_patterns, rare_patterns,
  example_cards, distribution{common,uncommon,rare,mythic}
  ```
  The LLM emits `design_rationale`; we rename to `design_notes` on save (the existing schema's name).
- `evergreen-keywords.json` — auto-written from a per-color default table (the same one currently hardcoded in `mechanic_generator.assign_evergreen_keywords()`). Kept on disk so it's editable per project.
- `pointed-questions.json` — auto-written from the canonical 9-question template; mechanic name placeholders substituted (the user can hand-edit later). This is also TC-5's deliverable — we ship it here because it's trivial templating once we know the mechanic names.
- `functional-tags.json` — auto-written as `{}` (empty stub). The template offers each mechanic a tag picker but defaults to none; the user can fill in `card_advantage` / `removal` / `tempo_cost` etc. inline. Balance analysis already gracefully handles missing tags.

`distribution.json` is **not** written here. That file maps mechanics to specific skeleton slots and depends on the skeleton existing. It becomes the constraints stage's output (see card sMSqWKw6).

## Wizard UI

The Mechanics stage tab lives at `/pipeline/mechanics`, rendered through `wizard_stage.js` like every other stage tab, with a bespoke body for the candidates UI. All conventions in `plans/wizard-tab-conventions.md` apply.

### Tab visibility + status

Standard stage flow — `PipelineState.stages` carries a `mechanics` entry. The visible-tabs computation in `pipeline/wizard.py` already shows stage tabs based on stage status; nothing custom needed. Status values flow from the stage runner via `emitter.phase(...)`:

| Stage state | Pill |
|-------------|------|
| Not yet started | hidden / `pending` |
| Running gen | `running` |
| Awaiting user picks (gen done, no `approved.json` yet) | `paused_for_review` |
| User saved approved.json | `completed` |
| Errored | `failed` |

The `paused_for_review` pause is the **standard human-review pattern** already used by `human_card_review`, `human_art_review`, `human_final_review` — the runner emits the candidates as stage sections, then returns a `StageResult(detail="Awaiting human selection via Mechanics tab")` and the engine pauses until the save endpoint marks the stage done.

### Layout (top → bottom)

1. **Header**: tab title + status pill + `Stop after this step` checkbox (mirrors Theme — wizard-tab-conventions §9). The break-point id is `mechanic_gen`. Default-on, like `theme_extract`. Add to `DEFAULT_BREAK_POINTS` in `mtgai/settings/model_settings.py`.

2. **Setting context summary** (read-only): inline preview of `theme.json` `theme` + `mechanic_count` so the user remembers what they're designing for. Edit returns to the Theme / Project Settings tab via the past-tab edit cascade (wizard-tab-conventions §6).

3. **Candidates strip** (always 6 cards once generated):
   - One card per candidate. Each card shows: name (editable), keyword type chip, reminder text (editable), colors (multi-select chips), complexity (1/2/3 chip), flavor connection (collapsed "why this fits"), design rationale (collapsed), pattern lists (collapsed).
   - Each card carries `data-ai-generated="true"` + AI badge until any field is edited (wizard-tab-conventions §5). Refresh-AI replaces only still-AI rows.
   - Per-card **Pick** checkbox. The save handler enforces exactly `mechanic_count` picks before Save & Continue is enabled.
   - **Refresh AI** button per-card (regenerates a single candidate, freezing the others).
   - **Refresh All** button at the strip level (regenerates all unedited candidates). Confirm dialog if any picks already exist.

4. **Streaming preview pane** (only while gen is running):
   - Mirrors Theme's streaming textarea — chunks land in a markdown preview as the LLM generates. The tool-call schema means the candidates strip only fully populates on the terminal `mechanic_done` event, but a text-prefix run before the tool call lets the LLM "think out loud" about flavor fit so the user has something to read. (Same pattern as Theme's `theme_chunk`.)

5. **Footer**: single primary `Save & Continue` button (wizard-tab-conventions §1).
   - Disabled while AI gen is in flight (form lock §3).
   - Disabled until exactly `mechanic_count` candidates are picked.
   - On click: validate picks → POST `/api/wizard/mechanics/save` (writes `approved.json` + auto-generated sidecars) → POST `/api/wizard/advance` → hard-nav to `/pipeline/skeleton`.

### Kickoff

Standard stage kickoff — `/api/wizard/advance` from Theme calls into the engine, which runs the next pending stage. `mechanics` is first, so it runs immediately. The runner streams candidates through `emitter.update(section_id, ...)` calls and when the LLM tool call returns, it transitions to `paused_for_review` and the engine yields. The user's tab is already on `/pipeline/mechanics` (hard nav from Theme) and sees the candidates populate via the standard `stage_update` SSE event the wizard shell already handles.

There's no separate "Generate" button — kickoff is automatic, same as every other stage. If the user lands on a fresh project mid-stage (page reload), `wizard_stage.js` already mounts the right state from `PipelineState.stages[mechanics]`.

A **Refresh AI** button on the candidates strip lets the user regenerate after the initial run (within the same paused stage, doesn't re-advance the engine — calls a dedicated endpoint that just rewrites `candidates.json` + republishes the section).

### Edit cascade

Editing this tab once Skeleton has run is destructive — downstream slots may have been built around the old mechanic names. Route through `W.editFlow.confirmCascade` per wizard-tab-conventions §6. Body text: "Editing mechanics will discard the skeleton and all downstream content."

## Server endpoints

The standard stage SSE stream + `/api/wizard/advance` cover most of the lifecycle. Only mechanics-specific endpoints are bespoke:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/wizard/mechanics/refresh-card` | `{candidate_index}` — regenerate one candidate within the paused stage. Acquires `ai_lock`, rewrites `candidates.json`, republishes that section via `event_bus`. |
| `POST` | `/api/wizard/mechanics/refresh-all` | Regenerate all unedited candidates (only those still flagged `data-ai-generated`). |
| `POST` | `/api/wizard/mechanics/save` | `{picks: [int], edits: {idx: {field: value}}}` — writes `approved.json`, `evergreen-keywords.json`, `pointed-questions.json`, `functional-tags.json`. Marks the `mechanics` stage `completed`. Returns `{navigate_to: "/pipeline/skeleton"}`. |

Stage cancel + initial generation flow through the existing `/api/pipeline/cancel` + `/api/wizard/advance` endpoints — no new wiring. All bespoke endpoints respect the AI mutex (wizard-tab-conventions §7) — return 409 with `busy_payload()` on conflict.

## Stage runner

`pipeline/stages.py` gets a new `run_mechanics(progress_cb, emitter)` (and `mechanics` registered as the first entry in `STAGE_RUNNERS`). It:

1. Loads `theme.json` + `set_params` from the active project. Errors out via `StageResult(success=False, ...)` if missing — same pattern as `run_skeleton`.
2. Initializes sections via `emitter.init_sections(...)` — one section per candidate slot (`candidate_0` … `candidate_5`) plus an `overview` section for the narration prefix.
3. Wraps the LLM call in `with ai_lock.hold("Mechanic generation"):`. Polls `ai_lock.is_cancelled()` between candidates.
4. As each tool-call candidate object arrives, calls `emitter.update("candidate_N", status="done", content={...})`. The wizard shell already broadcasts `stage_update` to the tab and the candidates strip renders.
5. Persists raw candidates to `<asset_folder>/mechanics/candidates.json`.
6. Returns `StageResult(detail="Awaiting human selection")` — engine pauses, stage status flips to `paused_for_review`.

The bespoke `/api/wizard/mechanics/save` endpoint is the "stage-done" trigger that flips status to `completed` and lets the user click Save & Continue → `/api/wizard/advance` → next stage (skeleton).

Underlying LLM call lives in `generation/mechanic_generator.py` (existing file — strip the ASD hardcoding, keep the tool schema). The runner orchestrates; the generator does the API call.

## Prompt design

System prompt template at `backend/mtgai/pipeline/prompts/mechanic_system.txt` (mirrors `theme_section_system.txt`). Variables: `theme_text`, `flavor_description`, `set_size`, `mechanic_count`, `archetypes_block`, `creature_types_block`, `excluded_keywords` (the existing list of MTG keywords to avoid).

Drop the ASD-specific copy that's currently inlined in `mechanic_generator.py:137-214`. The new template is fully driven by `theme.json` — no set-specific text in code.

User prompt asks for **6 candidates** distributed across:
- 2 creature-focused
- 2 spell-focused
- 2 any-permanent

Each candidate must specify the existing schema fields. The model must avoid any keyword in `mtg_known_keywords.json` (a new asset — list of every printed keyword + ability word, sourced from Scryfall once and cached). This is what catches the Scavenge / Overload collisions that bit ASD.

Tool schema name stays `submit_mechanic_candidates` (already in `mechanic_generator.py:11`); we only change what feeds it.

### Reminder text policy

`reminder_text` is generated by the LLM **only for the candidates page**. Per the Phase 4B reminder-injection refactor, the canonical reminder text is what eventually goes into approved.json — the user can edit it on the candidates strip — and `reminder_injector.py` reads it from there to inject into cards programmatically. Cards never have LLM-written reminder text. Nothing downstream changes.

## Migration: ASD already has approved.json

When the wizard opens an existing project where `mechanics/approved.json` already exists, the engine sees the `mechanics` stage as `completed` (the runner's "is this stage done?" check is "does approved.json exist?"). Standard stage flow then:

- Tab renders in `completed` status with the existing approved mechanics shown in the strip, all editable.
- No regeneration — the stage doesn't re-run on a completed pipeline.
- If the user edits, route through the standard past-tab edit cascade (`W.editFlow.confirmCascade`) — same flow every other past stage uses. Cascade clears skeleton + downstream stage outputs and re-runs the engine starting from `mechanics`.

No data migration code needed — the stage is "complete if file exists" and the file already exists.

## Pointed-questions templating (also closes TC-5)

The 9 canonical questions live in `backend/mtgai/pipeline/templates/pointed_questions.json` with `{mechanic_name}` placeholders. Save handler substitutes per approved mechanic, writes `<asset_folder>/mechanics/pointed-questions.json`. Existing AI review code (`review/ai_review.py:43-44`) reads from that path unchanged.

When a new failure mode is discovered during card review, the user adds a question to the canonical template (it's a project-level concern, not per-set). This is straightforward future work; no code change in this phase.

## Tests

Unit:
- `tests/test_mechanic_extractor.py` — prompt assembly from theme.json fixture, tool-schema parsing, candidate-count enforcement, evergreen-keywords default generation, pointed-questions templating with mechanic substitution.
- Existing `tests/test_skeleton_reviser.py` shouldn't change — it loads `approved.json` from disk and our schema is identical.

Integration:
- `tests/test_pipeline/test_mechanic_flow.py` — fake LLM response → wizard save → verify all four output files written with correct shape, verify `approved.json` is loadable by `Mechanic.model_validate()`.
- Manual: open ASD project, confirm Mechanics tab loads in completed state with all 3 mechanics.

## Out of scope

- **Distribution.json**. Belongs to the constraints stage (sMSqWKw6).
- **Validation spike** (testing each mechanic with 5 sample cards). The 1B validation spike was a one-time "do mechanics generate good cards" experiment. The pipeline catches this naturally: AI review (4B) flags any mechanic that produces consistently broken cards, and the user can return to the Mechanics tab to refine.
- **A/B testing review strategies per mechanic**. 1B settled on tiered council+iteration; that's a global review setting, not per-mechanic.
- **Functional-tags inference**. Could be LLM-derived from each mechanic's patterns. Deferred — empty file is fine; balance.py handles missing tags.
- **Live SSE replay-on-reattach for in-flight runs**. Defer to a follow-up if it bites; the run-buffer pattern is already in place.

## Tracker entries

Replace TC-2 in `plans/TRACKER.md` with the multi-step breakdown:

- TC-2a: Refactor `generation/mechanic_generator.py` — strip ASD-hardcoded prompt, drive from `theme.json` + `set_params`. Keep tool schema. Add MTG-known-keywords collision check.
- TC-2b: Add `run_mechanics` to `pipeline/stages.py` and register as the first entry in `STAGE_RUNNERS`. Plus a stage artifact clearer.
- TC-2c: Build `wizard_mechanics.js` — bespoke candidates strip body inside the standard `wizard_stage.js` shell.
- TC-2d: Bespoke endpoints — `/api/wizard/mechanics/{refresh-card,refresh-all,save}`.
- TC-2e: Sidecar template assets — `pipeline/templates/pointed_questions.json`, `mtg_known_keywords.json`, evergreen-keywords default table.
- TC-2f: ASD migration smoke — open existing project, mechanics stage shows `completed`, edit a mechanic via cascade, verify skeleton + downstream get cleared.

TC-5 (pointed-questions template) folds into TC-2's save handler — close as duplicate.
