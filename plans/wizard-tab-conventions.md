# Wizard tab conventions

The wizard is a linear sequence of tabs, each one a stage of the
pipeline. Project Settings (`pipeline/project`) and Theme
(`pipeline/theme`) are the two reference implementations — every new
tab should follow the same patterns. Stage tabs (`wizard_stage.js`)
inherit most of these too, but stick to the two reference tabs when in
doubt.

Server-side state lives under `backend/mtgai/pipeline/wizard.py` +
`backend/mtgai/pipeline/server.py`; client logic per tab in
`backend/mtgai/gallery/templates/static/wizard_<name>.js`; shared shell
in `wizard.js` and `wizard.css`.

## 1. One primary "Save & Continue" footer button

Every editable tab ends in a single primary button in the wizard footer
(`[data-role="footer"]` of the tab body shell):

* **Always rendered** on the latest tab when not in edit mode.
* On click: validates required fields → saves the tab's data → calls
  `/api/wizard/advance` (or the tab's kickoff endpoint) → hard-navs to
  the next tab via `window.location.assign(data.navigate_to)`. Hard nav
  so the server-rendered `WIZARD_STATE` bootstrap matches the new
  pipeline state without a separate refetch.
* **Disabled** while AI work is in flight on this tab (form lock — see
  §3) and while the click handler is awaiting the request chain.
* **Validation errors** surface via `W.toast(message, 'error')` and a
  focus jump to the missing field. Don't silently no-op — the user
  pressed a primary button and deserves feedback.
* The body's `.wiz-<tab>-actions` row is reserved for the edit-cascade
  flow (Cancel + Accept Edits). Don't put a second commit button there
  on the latest tab — one primary action per tab.

**The next-step label + nav are derived, never hardcoded.** A footer
that names the upcoming stage ("Save & Continue: Archetype Generation")
or falls back to a `/pipeline/<stage>` path must read the stage from the
backend's `STAGE_DEFINITIONS`, never a literal. Two shared helpers on
`window.MTGAIWizard` do this:

* `nextStageEntryAfter(stageId)` → `{id, name}` of the stage *after*
  `stageId` (or `null` if last). For stage tabs — e.g. the Mechanics
  footer uses `nextStageEntryAfter('mechanics')`.
* `firstStageEntry()` → `{id, name}` of the **first** pipeline stage, for
  a pre-stage content tab whose "next" is wherever the pipeline starts
  (the Theme tab). Works before kickoff too.

Both back onto the same ordered list: `state.pipeline.stages` once the
engine is running, else the `stage_definitions` bootstrap key (added by
`serialize()` in `pipeline/wizard.py` precisely so content tabs can name
a stage before `pipeline_state` exists). Insert or reorder a stage
server-side in `STAGE_DEFINITIONS` and every footer follows automatically
— no client-side stage list to keep in sync. The server side matches:
`/api/wizard/mechanics/save` computes its `navigate_to` from
`STAGE_DEFINITIONS` rather than returning a literal path.

This rule exists because the Mechanics and Theme footers once hardcoded
`"Skeleton"` / `"Mechanic Generation"` and silently lied the moment the
`archetypes` stage was inserted between mechanics and skeleton — exactly
the kind of stage reordering that should cost zero footer edits. **Exception:** when a content tab's successor is another
content tab (not a pipeline stage), a fixed label is correct — Project
Settings → Theme reads "Continue to Theme" because Theme isn't a stage.
Only derive when the successor is a pipeline stage.

References: Project Settings `onSaveAndStart` in
`wizard_project.js:1313`, Theme `onSaveAndAdvance` and `themeFooterHtml`
in `wizard_theme.js`, the shared next-step helpers in `wizard.js`, and
the generic stage footer in `wizard_stage.js` (`stageFooterHtml`).

## 2. Required fields → red asterisk + canStart()

Required-field markers reuse the existing helper:

```js
function requiredMark() {
  return ' <span class="wiz-required" title="Required to run the pipeline">*</span>';
}
```

Already in `wizard_project.js`; copy that helper into each new tab
module. CSS is in `wizard.css` (`.wiz-required`). Apply to the field's
label or section heading.

A `canStart(data)` (or equivalent) predicate decides whether the
primary button is enabled. It's the *button*'s gate, not the
*validator* — validation runs again on click so error messages are
specific. Project Settings's `canStart` in `wizard_project.js:1306` is
the template:

```js
function canStart(data) {
  if (data.extraction_active) return false;
  if (data.theme_input.kind === 'none') return false;
  if (!data.asset_folder) return false;
  return true;
}
```

The server **must also** validate — never trust the client gate alone.
The endpoint returns the toast-friendly error and a 4xx status; the
button handler only cares whether `resp.ok`.

## 3. AI gen → form lock

Whenever an AI run is in flight on the tab, every editable surface
goes `disabled`:

* All inputs / textareas (including LLM-streamed ones — the JS still
  writes through `disabled` so streaming doesn't break)
* Add / remove buttons
* All Refresh-AI buttons
* The footer Save & Continue button

Each tab module defines its own `setFormLocked(locked)`:

```js
function setFormLocked(locked) {
  const root = document.querySelector('.wiz-tab-body[data-tab-id="<id>"]');
  if (!root) return;
  root.classList.toggle('wiz-<id>-locked', !!locked);
  const sel = [/* every interactive selector */].join(',');
  root.querySelectorAll(sel).forEach(el => { el.disabled = !!locked; });
  // Footer button lives outside the tab body — query separately:
  const footerBtn = document.querySelector('button[data-role="<id>-advance"]');
  if (footerBtn) footerBtn.disabled = !!locked;
}
```

Call `setFormLocked(true)` when:

* Mounting and the bootstrap says AI gen is in flight (e.g.
  `state.extractionActive`).
* The user kicks off an AI op from this tab.
* AFTER any `replaceListWithAi`-style call that adds new rows during
  streaming — the fresh DOM nodes need disabling too. Idempotent.

Call `setFormLocked(false)` when:

* The AI op's terminal event fires (`*_done`, `*_error`, `*_cancelled`).
* The kickoff request fails before the worker started.

Visual cue: the `.wiz-<tab>-locked` class adds a faint dim + a
`not-allowed` cursor on disabled controls so the user reads the locked
state at a glance (browsers grey out `disabled` controls already, but
the cursor change is the give-away that nothing is broken).

## 4. Streamed LLM output

Prose generated by an LLM appears token-by-token in its textarea while
the worker runs. The pattern (Theme tab, `wizard_theme.js`):

* Worker emits `*_chunk` events on the SSE bus (`event_bus.publish`).
* Tab handler appends to the textarea's `value` directly — `disabled`
  doesn't block programmatic writes.
* A throttled (~200ms) `setTimeout` re-renders the markdown preview so
  the user sees prose materialise without DOM thrashing.
* Terminal `*_done` event triggers a final preview render and unlocks
  the form.
* Markdown rendering uses the zero-dep subset in `wizard_theme.js`'s
  `renderMarkdown()`. Copy or share — don't pull in a markdown lib
  unless rendering needs grow well past headings/paragraphs/lists/
  inline code/bold/italics.

If the LLM returns markdown, render it as markdown — the user is going
to consume it visually, and a textarea full of `## headers` is jarring
when a preview would show formatted sections.

**SSE replay matters.** The wizard's main SSE stream (`/api/pipeline/events`,
hooked up in `wizard.js`) does **not** replay history — it tails the
event_bus from connect time forward. If a worker has been running for
30s before the page bootstraps, every chunk before the connect is gone.
Two consequences:

1. The `*_chunk` event is the only way prose lands in the textarea — if
   you missed the first half, you stay missing it. Show the strip + a
   "joining run mid-stream" hint when this is detectable.
2. For replay-on-reattach scenarios, use the run-buffer pattern in
   `mtgai/runtime/extraction_run.py` (replays full event log on
   subscribe). Theme extraction's dedicated SSE endpoint
   (`/api/pipeline/theme/extract-stream/{upload_id}`) does this; the
   wizard tab today doesn't, but it's the right pattern when reattach
   matters.

## 5. AI provenance: badge + preserve-on-edit

Items added by an LLM (constraints, card requests, future similar
lists) carry:

* `data-ai-generated="true"` on the `.wiz-list-item` element
* A visible `<span class="wiz-ai-badge">AI</span>` next to the input

When the user edits the input, the badge clears (input listener calls
`clearAiBadge(item)`). This is the core of the **preserve-on-refresh**
contract:

* "Refresh AI" buttons replace **only** items still flagged
  `data-ai-generated="true"` (see `replaceListWithAi`). User-authored
  rows survive untouched.
* Save handlers tag each item's source as `'ai' | 'human'` in the saved
  JSON so the next mount can re-render badges correctly.

Don't break this contract — it's the user's only protection against
losing hand-curated edits when they hit Refresh.

## 6. Past-tab edit cascade

A tab is "past" once a later tab exists in the strip
(`isPast: tabId !== state.latestTabId`). Past tabs cannot be saved
directly — the only commit path is the Edit cascade, which warns the
user that downstream content will be discarded:

1. Tab header renders an `Edit` button (gated by
   `W.editFlow.isPipelineRunning()` — hidden mid-run).
2. Click → `W.editFlow.confirmCascade({ from_stage, title, body })`
   shows the modal warning. The body should be specific about *what*
   gets discarded (e.g. "Editing the Theme tab will discard all
   generated content from Skeleton onward").
3. On confirm, `W.editFlow.setDraft(tabId, …)` stashes a draft
   marker and the tab swaps:
   * Header: hide Edit, show "Editing" pencil/banner.
   * Body action row: show **Cancel** + **Accept Edits**.
   * Footer: replaced with a "Saving via Accept above" hint.
   * Banner: a yellow `wiz-edit-banner` reminding the user that Accept
     is destructive.
4. **Cancel** discards the draft, repopulates the form from
   `state.theme` / equivalent, restores the original UI.
5. **Accept Edits** calls `W.editFlow.accept({ from_stage, ... payload })`
   which routes through `/api/wizard/edit/accept`. The endpoint
   clears all downstream stage outputs, persists the new payload, and
   returns a `navigate_to` for the post-edit tab.

The `editFlow` surface is in `wizard.js` (`window.MTGAIWizard.editFlow`).
Don't reinvent it — every editable tab routes destructive past-tab
edits through it.

**Latest tab edits** are different: they go directly through the
tab's regular Save / Save-and-Continue. No cascade needed because
nothing is downstream yet.

**Live-apply edits** (Project Settings only, currently): each input
change posts immediately to a granular endpoint
(`/api/wizard/project/{params,theme-input,breaks,models,...}`). The
.mtg file save still happens via the browser's File System Access API
on the user's explicit Save action. Live-apply is for keeping the
server's in-memory ProjectState in sync, not for committing to disk.

## 7. AI mutex + busy 409s

Only one AI action runs across the app at a time — guarded by
`mtgai/runtime/ai_lock.py`. Any AI-touching endpoint wraps its body
in:

```python
with ai_lock.hold("Action name") as acquired:
    if not acquired:
        return JSONResponse(ai_lock.busy_payload(), status_code=409)
    ...
```

Client side: any `409` with `data.running_action` becomes a toast:

```js
if (resp.status === 409 && data.running_action) {
  W.toast(`${data.running_action} is in progress — try again when it finishes.`, 'error');
}
```

Long-running workers must poll `ai_lock.is_cancelled()` so the user
can hit the cancel button on the progress strip.

## 8. Tab status pill

Every editable tab in the strip shows a status pill in its header
matching the stage lifecycle pill that stage tabs render — `running`
while AI work is in flight, `paused_for_review` once the tab has
output the user is being asked to review, `completed` once the
pipeline has moved past it, `failed` on error. The pill is rendered
by `wizard.js` (`renderTabShell`) from `tab.status`, with CSS in
`wizard.css` (`.wiz-tab-header .wiz-status-pill.<status>`).

For stage tabs the status flows directly from
`PipelineState.stages[i].status` and is updated in place by
`wizard_stage.js` on each `stage_update` SSE event.

For non-stage tabs (Theme today, future content tabs):

* `wizard.py` computes the status at page-load time from the tab's
  own lifecycle signals — Theme uses `extraction_active` →
  `running`, `state is not None` → `completed`, `theme is not None`
  → `paused_for_review`. See `_compute_theme_status` in
  `pipeline/wizard.py`.
* The tab module updates the pill in place on its terminal events
  via a small helper (Theme: `setThemePillStatus` flips
  `running` → `paused_for_review` on `theme_done`). The helper just
  rewrites `pill.className` + `pill.textContent` — same shape that
  `wizard_stage.js` uses for stages.

The `paused_for_review` pill is the user's visual cue that this tab
is waiting for them — pair it with the latest-tab Save & Continue
button (§1) so the call to action and the status pill both point at
the same gesture.

## 9. "Stop after this step" toggle in tab header

Every stage and content tab carries a `Stop after this step`
checkbox in its header-actions slot (`[data-role="header-actions"]`).
It mirrors the matching break-points entry on the Project Settings
tab — both surfaces edit the same `settings.break_points` map, and
toggling either keeps the other in sync via
`window.MTGAIWizard.onBreakPointChanged`.

The checkbox posts to `/api/wizard/project/breaks` with
`{stage_id, review}`. The server accepts every stage_id in
`STAGE_DEFINITIONS` plus the virtual `theme_extract` id (theme
extraction runs before the engine kicks off, so it isn't a real
stage but it has the same review semantics).

Default-on stages come from `DEFAULT_BREAK_POINTS` in
`mtgai/settings/model_settings.py` — currently `theme_extract`,
`human_card_review`, `human_art_review`, `human_final_review`. The
wizard bootstrap (`break_point_states` in `pipeline/models.py`)
resolves every stage + the `theme_extract` virtual entry to a bool
so each tab's checkbox can read its initial state without a second
fetch.

The shared CSS class is `.wiz-stage-break-toggle` (in `wizard.css`).
Reuse it — both stage tabs (`wizard_stage.js`) and Theme
(`wizard_theme.js`) render the toggle with the same classname /
shape so a hover or disabled treatment lands consistently.

The Project Settings tab itself is the exception: instead of one
toggle for itself, it surfaces the **full** break-points list. There
is no "Stop after Project Settings" — kickoff is always manual.

When adding a new tab, the toggle is non-optional. A user who
configured "Stop after Skeleton" once on Project Settings expects
to be able to flip the same bit from the Skeleton tab itself; the
two surfaces are facets of the same setting.

## 10. Sticky progress strip

The top-of-shell progress strip (`#wiz-progress-strip` in
`wizard.js`) sticks to the viewport top via `position: sticky` so the
user always sees in-flight work. Stage / activity / progress bar /
cancel button are populated from the SSE event stream
(`stage_update`, `phase`, etc.). A new tab adding AI gen doesn't need
to touch this — publish to the bus and the shell handles the strip.

## 11. Bootstrap snapshot vs live state

`WIZARD_STATE` (rendered into `wizard.html` by `serialize()` in
`pipeline/wizard.py`) is a snapshot at page-load time. Specifically:

* `state.theme`, `state.pipeline`, `state.extractionActive` etc. are
  **not** kept in sync after page load — when the worker writes
  theme.json mid-session, `state.theme` stays null until the next page
  reload.
* For "is extraction running RIGHT NOW", track a tab-local flag
  (Theme uses `refreshState.fullActive`) updated from SSE events.
* For cross-tab live state, hit `/api/runtime/state` (in `ui_state.js`
  via `MtgaiState.fetchRuntimeState()`).

When a tab transitions (e.g. extraction `*_done`), update both DOM
and the in-memory `state` slice on the wizard shell so any subsequent
re-render reads the right thing — even though the bootstrap value is
stale, downstream handlers may consume it.

## 12. Misc essentials

* **Toasts**: `W.toast(message, 'success'|'error'|'warn')`. Don't
  use `alert`.
* **Confirms**: native `confirm()` for low-stakes warnings;
  `<dialog>` with custom Cancel/Confirm buttons for anything
  multi-option. The full Refresh-AI dialog in
  `wizard_theme.js` is the template.
* **No project open**: 409 with `{code: "no_active_project"}` —
  surface a friendly "open or create a project" prompt rather than a
  raw error.
* **No asset folder**: 409 with `{code: "no_asset_folder"}` — point
  the user back to Project Settings.
* **URL routing**: each tab maps to `/pipeline/<tab_id>`. Refresh
  must land back on the same tab — `build_wizard_state` resolves the
  URL fragment into a visible tab ID on every request.
* **Lazy mount**: tab bodies build on first activation only
  (`local.initialized` flag). Re-renders hit the `local.initialized
  === true` branch which refreshes the footer / header / actions in
  place without rebinding the body's textareas (so user edits don't
  get clobbered by an SSE event).
* **Single-slot click handlers**: footer rebinds via `innerHTML`
  rewrites; use `.onclick = …` (not `addEventListener`) on rebind so
  surviving DOM nodes don't accumulate handlers.
* **Single source of truth on disk**: card JSON is version-controlled
  per `CLAUDE.md`. Theme.json + pipeline-state.json + .mtg are the
  canonical project artifacts — render from them, don't store
  duplicate state in localStorage.

## 13. Section-level Refresh AI button

Every AI-generated content section gets a top-right **Refresh AI** button
inside its section header (`.wiz-theme-section-header-row` in CSS terms —
heading on the left, button on the right). The button is **always
rendered**, regardless of whether the section currently has content. This
is non-negotiable: when an AI run failed silently or was never kicked off
(e.g. the user landed on a stage tab whose initial generation produced
nothing), the Refresh button is the only in-tab recovery path. Without
it, the user has to drop into the Edit cascade on a past tab to redo the
section, which also discards downstream content unnecessarily.

Behaviour:

* **Section is empty** → button reads "Generate AI candidates" /
  "Generate" / similar action verb. Click runs the same endpoint as
  Refresh; the server branches on the empty payload to do an initial
  generation. No confirmation dialog (nothing to overwrite).
* **Section has content** → button reads "Refresh AI…" (ellipsis when a
  modal will appear). Click confirms with a `confirm()` or modal when
  the action would overwrite user edits, then calls the endpoint.
  Preserve-on-edit (§5) still applies: only AI-flagged rows get
  replaced.
* **Form locked** (§3 AI gen in flight) → button `disabled` like the
  rest of the section's interactive surfaces. Include the button in the
  section's `setFormLocked()` selector list.

References: Theme tab's three section headers + dialog (`themeBodyHtml`
in `wizard_theme.js`); Mechanics tab's summary header
(`paintSummary` + `onRefreshAll` in `wizard_mechanics.js`). The shared
classes are `.wiz-theme-section-header-row` and `.wiz-refresh-btn` —
reuse them so a hover / disabled treatment lands consistently across
tabs.

The matching server endpoint accepts both branches (initial-generate
and partial-refresh) on the same URL; it inspects the request body
(empty `indices` + empty content list → initial; non-empty `indices` →
partial). One endpoint, one URL, two payload shapes — see
`/api/wizard/mechanics/refresh-all` for the pattern.

## 14. Stage-failure modal

When a pipeline stage fails the engine halts the run (`stage.status =
failed`, `overall_status = failed`) and stops walking the stage list.
That state is surfaced two ways, and **both are owned by the shell** — a
tab doesn't wire its own failure popup:

* **The modal** — `wizard.js` shows a single shared, informational
  `<dialog>`-style overlay (`showStageFailureModal`) on the
  `pipeline_status` SSE event whenever `overall_status === 'failed'`.
  It names the failed stage + shows its `progress.error_message` in a
  scrollable detail block (`.wiz-modal--error` / `.wiz-modal-error-detail`
  in `wizard.css`). It is **dismiss-only** (Got it / Esc / backdrop) —
  it deliberately offers **no** recovery buttons, because the recovery
  affordances already live on the failed stage's own tab (its §13
  Refresh button to retry, and its editable result to fix by hand). Don't
  duplicate those into the modal.
* **The inline error** — `wizard_stage.js` still renders the
  `error_message` in the stage body (`.wiz-stage-error`) for the user
  who's already on that tab; per-tab footers may add a short note.

Dedup: the engine's `pipeline_status: failed` event is replayed to
every new SSE subscriber (fresh page load, EventSource reconnect), so
the modal latches on a `stage_id + error` signature (`_failureShownSig`)
and only re-shows after the next `running`. A new tab adding AI gen gets
this for free — fail the stage (return `StageResult(success=False, …)`
or raise) and the shell handles the modal; don't roll your own.

## 15. Stage LLM transcripts → `<asset>/<stage>/logs`

Every stage generator that makes an AI call **must** route its llmfacade
transcript (JSONL **and HTML**) to the stage's own
`<asset>/<stage>/logs` directory by passing `log_dir=` to
`generate_with_tool` / `generate_text` / `stream_text`:

```python
log_dir = set_dir / "<stage>" / "logs"
generate_with_tool(..., log_dir=log_dir)
```

Omitting `log_dir` (default `None` → `True`) silently falls back to
llmfacade's session dirs under `backend/logs/` — the transcript still
gets written, but it's nowhere near the stage's artifacts, so the user
(and you, debugging a bad generation) can't find it next to the
cards/JSON the stage produced. The Lands tab shipped without this and
the logs went missing from the stage folder; don't repeat it.

This is the established pattern across every stage: mechanics →
`mechanics/logs`, archetypes → `archetypes/logs`, visual_refs →
`art-direction/logs`, skeleton → `skeleton/logs`, reprints →
`reprints/logs`, lands → `lands/logs`, card-gen → `generation_logs`. A
`Path` writes flat into that dir (no `llmfacade<stamp>` session subdir,
no auto-prune); llmfacade creates the directory. The transcript is named
after the tool via `_convo_name`, so the file is self-identifying. See
the **"LLM call logs"** note in `CLAUDE.md` for the transport detail.

The one exception is `card_generator`, which *additionally* keeps a
bespoke per-card/batch log for the post-generation validation errors +
applied fixes + cost that llmfacade can't capture — but it still routes
the llmfacade transcript to the same dir. Don't reinvent that bespoke
logger for other stages; the llmfacade transcript is the canonical
per-call log.
