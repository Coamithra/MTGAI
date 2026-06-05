# Wizard tab conventions

The wizard is a linear sequence of tabs, each one a stage of the
pipeline. **Build a new tab by *calling* the shared helpers (§17), not by
copying an existing tab.** Copy-as-bootstrap is what these tabs were grown
from, and it is exactly what made them drift — byte-identical helpers diverging
in ways that hid bugs. The shared `window.MTGAIWizard` (`W.*`) surface plus the
backend helpers catalogued in §17 now own every cross-tab concern; a tab
supplies only its own content, per-status copy, and reactions. Project Settings
(`pipeline/project`) and Theme (`pipeline/theme`) remain useful worked examples
of the patterns below, but they are illustrations, **not templates to fork**.
§1–§16 document each convention; §17 is a build-a-new-tab recipe + the helper
index — start there.

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
each `*/save` endpoint computes its `navigate_to` via the shared
`_next_stage_nav(stage_id)` helper (`pipeline/server.py`) — "the stage after
`stage_id` in `STAGE_DEFINITIONS`, else `/pipeline`" — rather than re-deriving
the index inline or returning a literal path.

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

**Call the shared footer / save-advance helpers, don't hand-roll them.**
The lifecycle boilerplate every stage tab used to copy lives on
`window.MTGAIWizard` (`wizard_util.js`); the tab keeps only its per-status
footer *copy* and its body shape:

* `W.fetchStageState(stageId)` — first-paint fetch of
  `GET /api/wizard/<stageId>/state`. Returns the parsed body on 2xx, `null`
  on 404 (route missing → tab degrades to its empty state), and throws a
  normalized `Error` on any other failure (the bootstrap `.catch` toasts it).
  Standardizes the graceful-404 path. Bootstrap shape: `const data = await
  W.fetchStageState(STAGE_ID); if (data) { …hydrate local… } …paint…`.
* `W.emptyStatePanel({ generating, generatingMsg, emptyMsg, className })` —
  the empty/loading placeholder a tab paints when it has no content yet
  (`generating` = `aiBusy()`). `className` defaults to the shared
  `wiz-stage-empty`.
* `W.paintFooter(footer, html, { role, onClick })` — owns the
  `dataset.lastFooter` diff-guard (skip the DOM write when the markup is
  unchanged so SSE repaints don't thrash a footer mid-interaction) plus the
  single-primary-button bind. The tab builds `html` from its own
  branch-per-status copy.
* `W.saveAndAdvance({ stageId, saveUrl, payload, validate, isLocked,
  setLocked, btnRole })` — the review-gated tabs' Save & Continue: `validate`
  → POST save → POST `/api/wizard/advance` → `window.location.assign`, with
  the button's Saving…→Starting… text-spinner and restore-on-failure.
  `payload` may be a thunk (read at call time so it captures live edits);
  `validate` returns an error string (toasted, aborts) or `null`.
* `W.advanceStage({ stageId, isLocked, setLocked, btnRole, navigate })` — the
  auto-run tabs' resume: POST `/api/wizard/advance` then navigate. Pass
  `navigate: false` (card_gen) to leave the button disabled and let SSE drive
  the status forward instead of navigating.

The matching backend tail is `_stage_state_base(stage_id, settings)`
(`pipeline/server.py`), which returns the `{set_params, theme_summary,
model_id, stage_status}` quad every `*/state` endpoint merges its
tab-specific keys onto.

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

**Call `W.setTabLocked`, don't hand-roll the DOM sweep.** The shared
helper (`wizard_util.js`) owns the dim-class toggle + the `disabled`
sweep + the footer button; the tab supplies only its selector set. Each
tab keeps a thin `setLocked(locked)` that records `local.locked` and
delegates the DOM to the helper, computing the lock truth from an
`aiBusy()` composite:

```js
// The standardized lock truth source: own-lock OR (where the tab streams)
// a streaming flag OR the engine running this stage. Lock when ANY holds.
function aiBusy() {
  return local.locked || local.stageStatus === 'running'; // + local.streaming if you stream
}

function setLocked(locked) {
  local.locked = !!locked;
  W.setTabLocked(tabRoot(), aiBusy(), {
    lockClass: 'wiz-<id>-locked',
    selectors: ['<every interactive selector>'],
    footerSelector: '[data-role="<id>-advance"]', // omit if the footer is plain nav
  });
}
```

`aiBusy()` (not a bare `local.locked`) is the truth source so an
engine-driven run — which sets `stage.status === 'running'` without the
tab ever calling `setLocked(true)` — still disables the form. The
re-render path calls `setLocked(local.locked)` after refreshing
`local.stageStatus`, so a stage flipping to `running` over SSE re-locks
an already-painted body.

`setLocked` runs (directly or via `W.runAiAction`, §7) when:

* Mounting and the bootstrap says AI gen is in flight.
* The user kicks off an AI op from this tab (`runAiAction` owns this).
* AFTER any `replaceListWithAi`-style call that adds new rows during
  streaming — the fresh DOM nodes need disabling too. Idempotent.

`setLocked(false)` runs:

* When the AI op's terminal event / request chain finishes
  (`runAiAction`'s `finally` owns this).
* When the kickoff request fails before the worker started.

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
* A visible AI badge next to the input, rendered by
  **`W.provenanceBadge(aiGenerated, { role: 'ai-badge' })`** — the `role`
  emits `data-role="ai-badge"` so `clearAiBadge` can find + remove it on edit.

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

**Call `W.provenanceBadge(prov)` (`wizard_util.js`), don't hand-roll the
badge.** It is the one provenance-badge component: `true` / `'ai'` → the purple
"AI" badge, `'user'` → "edited", `'auto'` → "auto", and anything else
(`'default'`, a falsy value) → no badge. `true` and `'ai'` render identically.
It unifies the *markup* across the boolean list-item badge here (`_ai_generated`)
and the knob-provenance badges the Skeleton + Reprints tabs show, while keeping
each tab's not-user-set rendering: Reprints' `'auto'` (a system-resolved rarity)
shows a badge; Skeleton's `'default'` (an untouched knob) shows none — they were
distinct before and stay distinct. The `KnobPanel` (§17) renders it for knob
controls. This replaced three divergent badge markups (`wiz-ai-badge`,
`wiz-skel-userbadge`, the bespoke `wiz-reprints-knob-badge`).

## 6. Past-tab edit cascade

A tab is "past" once a later tab exists in the strip
(`isPast: tabId !== state.latestTabId`). Past tabs cannot be saved
directly — the only commit path is the Edit button, which warns the
user that downstream content will be discarded. There are **two edit
models**, by tab kind:

### Stage tabs → "unlock" (delete downstream, edit in place)

A completed **stage** tab's Edit is destructive-but-simple: one confirm,
then the tab is unlocked in place and every later tab is discarded. No
draft, no revert (the user opted out of the backup-and-cancel complexity).

1. Tab header renders an `Edit` button (gated by
   `W.editFlow.isPipelineRunning()` — hidden mid-run; the only entry
   to Edit is "no LLM is running").
2. Click → `W.editFlow.confirmCascade({ from_stage, after_only: true,
   title, body })` shows the modal warning, listing the
   *downstream-only* tabs that will be discarded (`after_only` lists the
   stages *after* `from_stage`; the edited stage's own output is kept).
3. On confirm → `W.editFlow.unlock({ from_stage })` →
   `POST /api/wizard/edit/unlock`. The endpoint (`_apply_downstream_clear`)
   clears `stages[idx+1:]` (artifacts + history + regen-inserted duplicate
   instances), **keeps** the edited stage's output, sets it
   `PAUSED_FOR_REVIEW` + the pipeline `PAUSED`, and returns a `navigate_to`.
4. The client hard-navs; the edited stage is now `latestTabId` +
   `PAUSED_FOR_REVIEW`, so its own renderer shows the editable grid +
   Refresh AI (reroll) + the Next-step footer that resumes the engine into
   the cleared downstream. **There is no stage-tab draft/Cancel/Accept** —
   `wizard_stage.js` no longer renders an editing banner.

### Content tabs (Theme, Project Settings) → draft (deferred, revertable)

Theme + Project Settings keep the deferred draft flow — their content is
form fields cheap to revert, and editing them legitimately invalidates the
whole pipeline (stage 0 onward), so there's no "keep this stage" notion:

1. Edit → `W.editFlow.confirmCascade({ from_stage, ... })` (no `after_only` —
   the cascade includes stage 0 onward).
2. On confirm → `W.editFlow.setDraft(tabId, …)`: header shows the "Editing"
   pencil/banner, the body action row shows **Cancel** + **Accept Edits**.
3. **Cancel** discards the draft, repopulates from `state.theme` / equivalent.
4. **Accept Edits** → `W.editFlow.accept({ from_stage, ...payload })` →
   `POST /api/wizard/edit/accept` (`_apply_cascade_clear`, which clears
   `stages[idx:]` *including* stage 0 and re-runs), persists the payload,
   returns `navigate_to`.

The `editFlow` surface is in `wizard.js` (`window.MTGAIWizard.editFlow`).
Don't reinvent it — every editable tab routes destructive past-tab
edits through it.

**Latest tab edits** are different: they go directly through the
tab's regular Save / Save-and-Continue. No cascade needed because
nothing is downstream yet.

### Auto-open the next tab

When the engine completes a stage and auto-advances (no "Stop after this
step"), the next stage's tab **auto-opens in the UI** — but only when the
user is currently viewing the tip (`activeTabId === prevLatest` in
`updateStageStatus`). If they've navigated back to inspect an earlier tab,
focus is left where it is. A break-point pause never starts the next stage,
so no new tab appends and the auto-open never fires (the "Stop after this
step" exception falls out for free).

### Sort / view controls stay live during a run

Pure view controls (card_gen's Group-by / Filter) change neither data nor
process, so they are **excluded from the form lock** (`setTabLocked`
selectors) and stay usable while an LLM run is in flight. Only AI-triggering
controls (Refresh / Generate) + the Save & Continue footer lock.

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

Client side, **route every AI-tab action through `W.runAiAction`**
(`wizard_util.js`) instead of hand-rolling the lifecycle. It owns the
whole recipe a tab used to copy: own-lock guard → optional `confirm` →
`setLocked(true)` → `showBusy(label)` → POST → parse-or-`{}` → the
`409 running_action` / generic error toast (via `W.reportError`) →
network catch → `finally` `clearBusy()` + `setLocked(false)`. A tab
supplies only the variable bits:

```js
// Single-POST form (most refresh / generate / re-pick buttons):
W.runAiAction({
  isLocked: () => local.locked,
  setLocked,
  confirm: () => (local.hasContent ? 'Regenerate? Current output is replaced.' : ''),
  busyLabel: 'Regenerating…',
  url: '/api/wizard/<tab>/refresh', body: () => ({ ... }), fallback: 'Refresh failed',
  onResult: (data) => { /* apply + repaint here */ },
});

// Multi-step form (e.g. skeleton's knobs → relabel cascade): pass `run`
// instead of url/onResult. `post(url, body, fallback)` returns the parsed
// data on 2xx or null (already toasted); `showBusy(label)` relabels mid-run.
W.runAiAction({
  isLocked: () => local.locked, setLocked, busyLabel: 'Step one…',
  onSettle: () => { /* teardown that must run on success + error alike */ },
  run: async ({ post, showBusy }) => {
    const a = await post('/api/.../one', body1, 'Step one failed'); if (!a) return;
    showBusy('Step two…');
    const b = await post('/api/.../two', body2, 'Step two failed'); if (!b) return;
    repaint();
  },
});
```

The empty-string `confirm` thunk skips the native prompt (initial
generates have nothing to overwrite). DOM-gather pre-flight that must run
*before* locking (e.g. collecting AI-flagged rows, the pick-aware confirm)
stays outside `runAiAction`; everything from the lock onward goes in.

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
`mechanics`, `skeleton`, `human_art_review`, `human_final_review`. The
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
* **Card text symbol preview**: card text stores mana / tap symbols as
  the canonical `{T}` / `{W}` / `{2}` tokens (the on-disk Scryfall form
  the renderer's `symbol_renderer.parse_mana_cost` consumes). A tab that
  *displays* that text should render the tokens as inline badges, not show
  raw braces — `wizard_finalize.js`'s `symbolizeHtml(text)` is the template:
  escape first, then replace each `{...}` with a `.wiz-sym .wiz-sym-<code>`
  span (the per-color palette mirrors the renderer's `MANA_COLORS`). A tab
  that *edits* the text keeps the raw tokens in the textarea and shows a
  live `symbolizeHtml` preview beneath it, plus a one-line helper at the top
  documenting the `{T}` etc. syntax. Display-only — the stored text always
  keeps the tokens.

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

## 15. Failed-stage recovery: heal on every successful manual write

When a stage's engine run fails (model exhausts its retry budget, a cancel
returns `success=False`, the server is interrupted mid-run, etc.) it lands
in `StageStatus.FAILED` and `PipelineStatus.FAILED`. From there the engine
won't advance until the stage is back in `PAUSED_FOR_REVIEW` — the user's
manual recovery (Refresh AI, Re-pick, edit + Save, knob retune, etc.) puts
valid output back on disk but **doesn't on its own flip the status**, so
the wizard footer's Save & Continue stays hidden forever. The stage looks
stuck even though its content is good.

The fix is one line at the end of every recovery-style endpoint:

```python
from mtgai.pipeline.server import _heal_failed_stage  # already imported in-module

# After persisting the regenerated/saved output and before the JSONResponse:
_heal_failed_stage("<stage_id>")
```

`_heal_failed_stage` (in `pipeline/server.py`) demotes the stage's status
FAILED → PAUSED_FOR_REVIEW, flips `overall_status` FAILED → PAUSED, clears
`progress.error_message`, persists `pipeline-state.json`, and publishes the
matching `stage_update` + `pipeline_status` SSE events so open tabs update
without a reload. It's **idempotent and a no-op when the stage isn't failed**
— safe to call from any successful path without gating.

When to call it:

* **Refresh-style endpoints** (`*/refresh`, `*/refresh-all`, `*/refresh-card`,
  `*/knobs/tune`, `*/pick`) — call after the regenerated output is written
  to disk.
* **Save endpoints** (`*/save`) — call after `atomic_write_text` /
  `persist_*` so the subsequent `/api/wizard/advance` finds the stage in
  PAUSED_FOR_REVIEW and resumes the engine.
* **Pure-config endpoints** (e.g. `*/knobs` that only persist settings
  without regenerating output) — skip; they don't change the stage's
  "valid output exists" state and the next refresh will heal anyway.

Every stage that can fail (mechanics, archetypes, skeleton, reprints,
lands, card_gen, plus any future stage with a wizard tab) **must** call
this from its recovery endpoints. The failure path itself stays in the
engine — don't reinvent it per-stage. Reference call sites in
`pipeline/server.py`: every `_heal_failed_stage(...)` line.

This rule exists because the original card_gen and mechanics endpoints each
shipped with their own `_heal_failed_<stage>_stage` helper as a one-off
patch, and every new stage's refresh endpoint repeated the bug (Archetypes
shipped with no heal; the user hit a FAILED stage, refreshed successfully,
and had no way to advance). One generic helper called from every recovery
endpoint is the convention now.

## 16. Stage LLM transcripts → `<asset>/<stage>/logs`

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

## 17. Shared helpers — call, don't copy

The wizard tabs were bootstrapped by *copying* the two reference tabs
(Project Settings, Theme) into each new stage tab. That seeded byte-identical
leaf helpers, lifecycle blocks, and CSS — which then drifted (Skeleton vs
Reprints badged the same state with different words; Lands' grid CSS literally
commented "same column sizing as reprints"). The shared surface below replaces
"copy this block" with "call this helper", so a new tab inherits §1–§16
behaviour by construction instead of re-deriving it and silently diverging.
Below: a build-a-new-tab recipe, then the frontend + backend helper index (the
sections above cite individual entries inline).

### Building a new tab

A new stage / content tab is assembled, in order, from:

1. **Alias `W`** at the top of the IIFE (`const W = window.MTGAIWizard`), then
   the leaf helpers it uses (`const escHtml = W.escHtml`, …). Never re-implement
   them — that is how `escHtml`/`escAttr` ended up byte-identical in ~22 files.
2. **Mount + first paint** — register with `W.registerStageRenderer(id, render)`
   (stage tab) or `W.registerTabRenderer` (content tab); fetch state with
   `W.fetchStageState(id)` (graceful 404 → `null`); show `W.emptyStatePanel(...)`
   while there's no content.
3. **Footer** — build the per-status copy, paint it with `W.paintFooter`, and
   drive the primary button with `W.saveAndAdvance` (review-gated) or
   `W.advanceStage` (auto-run). The next-stage label/nav comes from
   `W.nextStageEntryAfter(id)` — never hardcode it (§1).
4. **AI actions** — route every Refresh / Generate / Re-pick through
   `W.runAiAction` (§7); never hand-roll the lock → busy → POST → 409 → unlock
   lifecycle.
5. **Form lock** — a thin `setLocked` that records `local.locked` and delegates
   the DOM to `W.setTabLocked`, with the truth source the `aiBusy()` composite
   (§3).
6. **Provenance** — render any AI / edited badge with `W.provenanceBadge` (§5)
   and keep the clear-on-edit contract.
7. **Bounded controls** — knob / numeric panels via `W.KnobPanel`; read-only
   card tiles via the shared `.wiz-tile*` grid + `W.rarityPill`.
8. **Live streaming** — wire SSE-driven live tiles with `W.registerStream` +
   `W.streamUpsert`; per-event semantics stay in the tab's handlers.
9. **Status pill (§8) + "Stop after this step" toggle (§9)** — the shell renders
   both; the tab only emits the SSE events / the toggle markup.
10. **Backend endpoints** — `*/state` merges `_stage_state_base`; `*/save` navs
    via `_next_stage_nav`; AI endpoints wrap their work in `guarded_ai` and lean
    on the success-only `_heal_failed_stage` (§7, §15); parse bodies with
    `_read_request_json`; route the LLM transcript to `<asset>/<stage>/logs`
    (§16).

If a concern isn't covered by a helper yet, **add it to `wizard_util.js` /
`server.py` and document it here** — don't copy a block from a sibling tab.

**The art / render / review tabs are the next adopters.** They were scoped out
of the shared-components pass (`plans/wizard-tab-shared-components.md`) but ride
the *same* primitives — build them from this recipe, not by forking a stage
tab. The review-loop instances (conformance / interactions / design-review,
which appear more than once per run) especially reuse the stage shell, the
footer/advance helpers, `W.runAiAction`, and `guarded_ai` verbatim; if one of
those falls short for a review tab, extend the helper rather than re-deriving it
locally.

### Frontend — `window.MTGAIWizard`, installed by `wizard_util.js`

`wizard_util.js` loads before `wizard.js` and every tab module, so a tab
aliases these off `W` at the top of its IIFE instead of carrying private
copies.

* **Leaf helpers** — `W.escHtml` / `W.escAttr` / `W.cssEsc` (escaping);
  `W.tabRoot(id)` / `W.tabFooter(root)` / `W.isPastTab(id, state)` (the
  stage-tab DOM lookups, once forked under three names); `W.reportError(resp,
  data, fallback)` (the 409-busy / generic AI-action error toast).
* **AI-action lifecycle (§7)** — `W.runAiAction(opts)` owns the own-lock guard
  → confirm → lock → `showBusy` → POST → 409/error toast → unlock recipe;
  `W.setTabLocked(root, locked, { lockClass, selectors, footerSelector })` is
  the form-lock DOM sweep.
* **Stage-tab shell (§1)** — `W.fetchStageState(id)` (first-paint GET, graceful
  404 → `null`); `W.emptyStatePanel(opts)`; `W.paintFooter(footer, html,
  { role, onClick })` (the `dataset.lastFooter` diff-guard); `W.saveAndAdvance`
  / `W.advanceStage` (save→advance→navigate / resume→navigate, with the button
  text-spinner).
* **Provenance + controls** — `W.provenanceBadge(prov, { role })` (§5, the one
  badge component); `W.KnobPanel(container, opts)` (the spec-driven
  bounded-control grid the Skeleton + Reprints knob panels render through —
  grouped/flat, pinnable, nullable-"auto", range hint, badge placement; the tab
  supplies state + `onChange`/`onPin` reactions + its own CSS classes + extras
  like Skeleton's cycles / Reprints' jitter); `W.rarityPill(rarity)` + the
  shared read-only tile grid CSS in `wizard.css` (`.wiz-tile` / `.wiz-tile-grid`
  / `.wiz-tile-header` / `.wiz-rarity*` / `.wiz-tile-locked`, used by Reprints +
  Lands — a tile variant layers its own class beside `.wiz-tile`).
* **SSE stream bridge (live tiles)** — `W.registerStream(stageId, handlers)`
  owns the `W.on<Stage>Stream` hook assignment + event-name dispatch + fresh
  tab-root lookup the mechanics / skeleton / card_gen streaming tabs hand-rolled;
  `W.streamUpsert(list, item, keyFn)` is the merge-by-key/append primitive. The
  per-event semantics (collision tags, busy label, live-slot patch) stay in the
  tab handlers — they diverge too much to fold into one `onItem`.

### Backend — `pipeline/server.py` unless noted

* **Guards** — a registered exception handler turns a `_NoActiveProject` /
  `NoAssetFolderError` raised anywhere (including nested helpers) into the 409
  `{error, code}` payloads, so an endpoint calls `_require_active_project()` /
  `set_artifact_dir()` inline rather than wrapping each in try/except.
  `read_theme_or_none()` names the "swallow `NoAssetFolderError` → None" intent.
* **`guarded_ai(label, stage_id=…)` (§7, §15)** — the AI-tab endpoint context
  manager: `ai_lock.hold` → 409 busy, the `try/500 {error}` envelope (worker
  exceptions become `AIActionError`), the success-only `_heal_failed_stage`, and
  release. Set `guard.skip_heal = True` to opt out after a cancelled run.
* **`_read_request_json(request)`** — JSON body parse with a 400 envelope on
  malformed input (use it instead of raw `await request.json()`).
* **`_stage_state_base(stage_id, settings)` (§1)** — the `{set_params,
  theme_summary, model_id, stage_status}` tail every `*/state` merges its
  tab-specific keys onto; **`_next_stage_nav(stage_id)`** — the `*/save`
  navigate computation.
* **`_skeleton_knobs_from_body(body)`** — the Skeleton tab's `{knobs, cycles,
  pinned, provenance}` overlay onto `SkeletonKnobs.from_payload`, shared by
  `/skeleton/knobs` (deterministic rebuild) and `/skeleton/knobs/tune` (AI
  re-tune base). `ReprintKnobs` validates too differently (nullable-auto vs
  clamp) to share the step, so the reprint side keeps `_write_reprint_knobs`.
* **`pipeline/stage_hooks.py`** — the engine↔refresh SSE hook builders
  (`build_{mechanic,skeleton,card_gen}_hooks`, `emit_skeleton_done`,
  `emit_card_gen_reset`, `card_tile_dict`, `slots_by_id_from_skeleton`). Both
  the engine stage runner and the refresh endpoints construct them against a
  real `StageEmitter`, so the two paths' event payloads can't drift.
