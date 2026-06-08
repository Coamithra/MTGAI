/**
 * wizard_util.js — shared leaf helpers for the pipeline wizard tabs.
 *
 * Loaded first (before wizard.js and every per-tab module) so each module can
 * alias these off ``window.MTGAIWizard`` at the top of its IIFE instead of
 * copying byte-identical blocks. This is the "call this, not copy this" leaf
 * layer of the shared-components pass (plans/wizard-tab-shared-components.md).
 *
 * Holds the shared stage-tab surface every per-tab module calls instead of
 * copying: the leaf helpers (HTML/attr/CSS escaping, the stage-tab DOM lookups
 * that were forked under three names — bodyRoot/tabRoot, getFooter, isPastTab —
 * and the standard AI-action error toast), the AI-action lifecycle (runAiAction
 * / setTabLocked), and the stage-tab shell helpers (fetchStageState,
 * emptyStatePanel, paintFooter, saveAndAdvance, advanceStage). These call into
 * wizard.js's ``W.*`` surface (postJSON / toast / showBusy / nextStageEntryAfter)
 * at runtime, so load order doesn't matter even though this file loads first.
 */
(function () {
  'use strict';
  const W = (window.MTGAIWizard = window.MTGAIWizard || {});

  // --- HTML / attribute / CSS escaping -------------------------------------
  W.escHtml = function (text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
  };

  W.escAttr = function (text) {
    return W.escHtml(text).replace(/"/g, '&quot;');
  };

  // Uses CSS.escape where available (every modern browser); the fallback is an
  // identifier-style escape (drop anything outside [A-Za-z0-9_-]). Tab/slot ids
  // are alphanumeric+hyphen, so the fallback only matters in the no-CSS.escape
  // case — there it differs slightly from a quote-only attribute-value escape.
  W.cssEsc = function (s) {
    const str = String(s == null ? '' : s);
    return window.CSS && CSS.escape ? CSS.escape(str) : str.replace(/[^a-zA-Z0-9_-]/g, '\\$&');
  };

  // --- Stage-tab DOM lookups -----------------------------------------------
  // The stage shell (wizard_stage.js) renders one
  // ``.wiz-tab-body[data-tab-id="<stage>"]`` per visible tab, each containing a
  // ``[data-role="footer"]``. These three lookups were copied into every stage
  // tab, the root one under two names (bodyRoot, tabRoot).
  W.tabRoot = function (stageId) {
    return document.querySelector(`.wiz-tab-body[data-tab-id="${stageId}"]`);
  };

  W.tabFooter = function (root) {
    return root && root.querySelector('[data-role="footer"]');
  };

  W.isPastTab = function (stageId, state) {
    return !!state && state.latestTabId !== stageId;
  };

  // --- Read-only tile grid (shared chrome) ---------------------------------
  // Reprints + Lands both render a responsive grid of read-only card tiles. The
  // chrome (grid sizing, tile box, header row, rarity pill, locked dim) lived as
  // prefix-renamed copies in each tab's injectStyles() — lands literally commented
  // "same column sizing as reprints". The shared rules now live in wizard.css under
  // .wiz-tile-grid / .wiz-tile / .wiz-tile-header / .wiz-rarity* / .wiz-tile-locked;
  // a tab that needs tile variants (lands' per-basic border tint) layers its own
  // class alongside .wiz-tile. This helper renders the rarity pill off those rules.
  //
  // Maps a rarity (full word like "Rare" or a bare letter) to the c/u/r/m class;
  // the visible label is the full rarity word (or "?" when absent). Matches the
  // reprints/lands behavior it replaces: a missing rarity keys to 'c', labels '?'.
  W.rarityPill = function (rarity) {
    const word = rarity || '';
    const key = String(word).toLowerCase().charAt(0) || 'c';
    return `<span class="wiz-rarity wiz-rarity-${W.escAttr(key)}">${W.escHtml(word || '?')}</span>`;
  };

  // --- KnobPanel: spec-driven bounded-control grid -------------------------
  // Skeleton and Reprints both render a grid of bounded numeric "knob" controls
  // (label + provenance badge + number input + optional range hint / pin) and wire
  // the same input/pin bookkeeping — they had grown divergent copies of that
  // render+bind logic. W.KnobPanel renders the rows (grouped or flat) into a
  // container and binds the events, delegating the *reaction* to onChange/onPin so
  // each tab keeps its own state model + extras (skeleton's cycles, reprints'
  // jitter + preview). Each tab passes its own CSS class names, so sharing the
  // logic doesn't force a shared look. The provenance badge is W.provenanceBadge.
  //
  //   container — rendered into (innerHTML replaced); its own class is the grid.
  //   opts:
  //     specs      [{key,label,min,max?,step,default?,help?,group?}] (normalized).
  //     values     {key: number|null}.
  //     provenance {key: 'ai'|'user'|'auto'|'default'}.
  //     defaultProvenance — badge value for a key absent from `provenance`
  //                  (skeleton 'default', reprints 'auto'); omit → no badge.
  //     disabled   bool — render every input/pin disabled.
  //     groups     {groupKey: legend}; present → one fieldset per group (specs
  //                grouped by spec.group, first-seen order); absent → flat rows.
  //     nullable   bool — a null value renders a blank input (reprints' "auto");
  //                else it falls back to spec.default.
  //     placeholder(spec) → input placeholder string (reprints' "auto (N)").
  //     rangeHint  bool — append a "min–max" span after the input (skeleton).
  //     badgeAfterInput — bool; render the provenance badge as a sibling after
  //                  the input (reprints, whose fixed-width label can't hold it)
  //                  instead of inside the label (skeleton's flexible label).
  //     pinned     array of pinned keys — presence enables the pin checkbox.
  //     event      'input' | 'change' (default 'input') — which fires onChange.
  //     onChange(key, value, spec) — value is Number, or null on an empty input.
  //     onPin(key, checked)        — only wired when `pinned` is supplied.
  //     classes    { group, legend, row, label, input, range, pin } overrides.
  W.KnobPanel = function (container, opts) {
    if (!container) return;
    opts = opts || {};
    const cls = opts.classes || {};
    const ca = (c) => (c ? ` class="${c}"` : '');
    const specs = opts.specs || [];
    const values = opts.values || {};
    const provenance = opts.provenance || {};
    const pinnable = Array.isArray(opts.pinned);
    const pinned = opts.pinned || [];
    const ev = opts.event === 'change' ? 'change' : 'input';
    const dis = opts.disabled ? ' disabled' : '';

    const rowHtml = (spec) => {
      const key = spec.key;
      const prov = provenance[key] != null ? provenance[key] : opts.defaultProvenance;
      const badge = W.provenanceBadge(prov);
      const val = values[key];
      let valueAttr;
      if (val != null) valueAttr = W.escAttr(String(val));
      else valueAttr = opts.nullable ? '' : W.escAttr(String(spec.default != null ? spec.default : ''));
      const ph = opts.placeholder ? ` placeholder="${W.escAttr(opts.placeholder(spec))}"` : '';
      const maxAttr = spec.max != null ? ` max="${W.escAttr(String(spec.max))}"` : '';
      const title = spec.help ? ` title="${W.escAttr(spec.help)}"` : '';
      const range = opts.rangeHint
        ? `<span${ca(cls.range)}>${W.escHtml(String(spec.min))}–${W.escHtml(String(spec.max))}</span>`
        : '';
      const pin = pinnable
        ? `<label${ca(cls.pin)} title="Keep this value on a re-tune">`
          + `<input type="checkbox" data-knob-pin="${W.escAttr(key)}"`
          + `${pinned.includes(key) ? ' checked' : ''}${dis}> pin</label>`
        : '';
      const labelBadge = opts.badgeAfterInput ? '' : ` ${badge}`;
      const inputBadge = opts.badgeAfterInput ? ` ${badge}` : '';
      return `<div${ca(cls.row)} data-knob-row="${W.escAttr(key)}">`
        + `<label${ca(cls.label)}${title}>${W.escHtml(spec.label)}${labelBadge}</label>`
        + `<input type="number"${ca(cls.input)} data-knob="${W.escAttr(key)}"`
        + ` min="${W.escAttr(String(spec.min))}"${maxAttr} step="${W.escAttr(String(spec.step))}"`
        + ` value="${valueAttr}"${ph}${dis}>`
        + `${inputBadge}${range}${pin}</div>`;
    };

    let html;
    if (opts.groups) {
      const order = [];
      const byGroup = {};
      specs.forEach((s) => {
        if (!byGroup[s.group]) { byGroup[s.group] = []; order.push(s.group); }
        byGroup[s.group].push(s);
      });
      html = order.map((g) =>
        `<fieldset${ca(cls.group)}><legend${ca(cls.legend)}>${W.escHtml(opts.groups[g] || g)}</legend>`
        + `${byGroup[g].map(rowHtml).join('')}</fieldset>`
      ).join('');
    } else {
      html = specs.map(rowHtml).join('');
    }
    container.innerHTML = html;

    // Bind. Disabled inputs don't emit user events, so binding unconditionally is
    // safe (and a tab re-renders on lock changes anyway).
    const onChange = opts.onChange || (() => {});
    container.querySelectorAll('input[data-knob]').forEach((inp) => {
      const key = inp.getAttribute('data-knob');
      const spec = specs.find((s) => s.key === key);
      inp.addEventListener(ev, () => {
        const raw = inp.value;
        onChange(key, raw === '' ? null : Number(raw), spec);
      });
    });
    if (pinnable && opts.onPin) {
      container.querySelectorAll('input[data-knob-pin]').forEach((pin) => {
        const key = pin.getAttribute('data-knob-pin');
        pin.addEventListener('change', () => opts.onPin(key, pin.checked));
      });
    }
  };

  // --- AI-action error reporting -------------------------------------------
  // Standard toast for a failed AI-tab action: the 409 "AI busy" branch plus a
  // generic fallback. Lifted verbatim from the archetypes/skeleton copies.
  W.reportError = function (resp, data, fallback) {
    if (resp.status === 409 && data && data.running_action) {
      W.toast(`${data.running_action} is in progress — try again when it finishes.`, 'error');
    } else if (resp.status === 409 && data && data.code === 'no_asset_folder') {
      W.toast('No asset folder configured — open Project Settings and pick one.', 'error');
    } else {
      W.toast((data && data.error) || `${fallback} (${resp.status})`, 'error');
    }
  };

  // --- AI provenance badge (conventions §5) --------------------------------
  // One badge component, one markup, display-only. The tabs that show provenance
  // had each grown their own badge markup + vocab (skeleton: wiz-ai-badge "AI" /
  // wiz-skel-userbadge "edited" / nothing for 'default'; reprints: bespoke
  // wiz-reprints-knob-badge "auto"/"user"; theme/mechanics/archetypes: a boolean
  // _ai_generated → wiz-ai-badge "AI" / nothing). This unifies the markup while
  // preserving each tab's not-user-set rendering:
  //   true / 'ai'                          → the established .wiz-ai-badge "AI"
  //   'user'                               → .wiz-prov-badge.wiz-prov-user "edited"
  //   'auto'                               → .wiz-prov-badge.wiz-prov-auto "auto"
  //   'default' / false / null / '' / etc. → '' (no badge)
  // provenanceBadge(true) ≡ provenanceBadge('ai'). 'auto' (reprints' system-
  // resolved rarity) shows a badge; 'default' (skeleton's untouched-knob state)
  // shows none — distinct on purpose, matching each tab's prior look.
  //   opts.role — emit data-role="<role>" so a clear-on-edit listener can find +
  //               remove the badge (the list-item badges use 'ai-badge').
  W.provenanceBadge = function (prov, opts) {
    const role = opts && opts.role ? ` data-role="${W.escAttr(opts.role)}"` : '';
    if (prov === true || prov === 'ai') return `<span class="wiz-ai-badge"${role}>AI</span>`;
    if (prov === 'user') return `<span class="wiz-prov-badge wiz-prov-user"${role}>edited</span>`;
    if (prov === 'auto') return `<span class="wiz-prov-badge wiz-prov-auto"${role}>auto</span>`;
    return ''; // 'default' (skeleton untouched) + falsy (hand-authored row) → no badge
  };

  // --- AI-tab action lifecycle (conventions §7) ----------------------------
  // The universal "Refresh AI / Generate / Re-pick" lifecycle every stage tab
  // copied by hand: own-lock guard → optional confirm → setLocked(true) →
  // showBusy(label) → POST → parse-or-{} → 409/error toast → network catch →
  // finally clearBusy() + setLocked(false). Tabs supply only the variable bits.
  //
  // opts:
  //   isLocked()    — return true to no-op (the own-lock re-entrancy guard).
  //   setLocked(b)  — the tab's form-lock toggle (see W.setTabLocked).
  //   confirm       — string, or a () => string|'' thunk; '' / falsy skips the
  //                   MTGAIDialog.confirm() (e.g. an initial generate has nothing
  //                   to overwrite, or the confirm is conditional on dirty state).
  //   busyLabel     — initial global-progress-strip label (W.showBusy).
  //   onSettle()    — optional teardown run in the finally, before setLocked(false)
  //                   (e.g. clearing a streaming-mode flag) — runs on success,
  //                   early-return, and error alike.
  //
  // Two body shapes:
  //   Single POST:  { url, body, fallback, onResult }
  //     body may be an object or a () => object thunk (read at call time so it
  //     captures live edits). onResult(data) does the repaint on a 2xx.
  //   Multi-step:   { run: async ({ post, showBusy }) => { ... } }
  //     `post(url, body, fallback)` does one POST + parse + 409/error toast and
  //     returns the parsed data on 2xx or null on failure (already toasted, so
  //     callers just `if (!data) return;`). `showBusy(label)` relabels the strip
  //     mid-run (skeleton's knobs→relabel cascade). Use for optimistic paints or
  //     sequential calls.
  W.runAiAction = async function (opts) {
    const isLocked = opts.isLocked || (() => false);
    if (isLocked()) return false;
    if (opts.confirm) {
      const msg = typeof opts.confirm === 'function' ? opts.confirm() : opts.confirm;
      if (msg && !(await window.MTGAIDialog.confirm(msg))) return false;
    }
    if (opts.setLocked) opts.setLocked(true);
    if (opts.busyLabel && W.showBusy) W.showBusy(opts.busyLabel);
    const post = async (url, body, fallback) => {
      const payload = typeof body === 'function' ? body() : (body || {});
      const resp = await W.postJSON(url, payload);
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        W.reportError(resp, data, fallback || 'Request failed');
        return null;
      }
      return data;
    };
    const showBusy = (label) => { if (W.showBusy) W.showBusy(label); };
    try {
      if (opts.run) {
        await opts.run({ post, showBusy });
      } else {
        const data = await post(opts.url, opts.body, opts.fallback);
        if (data && opts.onResult) await opts.onResult(data);
      }
    } catch (err) {
      W.toast('Network error: ' + (err && err.message ? err.message : err), 'error');
    } finally {
      if (W.clearBusy) W.clearBusy();
      if (opts.onSettle) opts.onSettle();
      if (opts.setLocked) opts.setLocked(false);
    }
    return true;
  };

  // --- Form lock (conventions §3) ------------------------------------------
  // One DOM form-lock implementation. The tab computes its own "AI busy" truth
  // (own-lock OR streaming OR stage.status === 'running') and passes the bool;
  // this just toggles the dim class, disables the listed interactive selectors,
  // and disables the footer primary button. Tabs supply their selector set.
  //   opts: { lockClass, selectors: string[], footerSelector }
  W.setTabLocked = function (root, locked, opts) {
    if (!root) return;
    opts = opts || {};
    const on = !!locked;
    if (opts.lockClass) root.classList.toggle(opts.lockClass, on);
    const selectors = opts.selectors || [];
    if (selectors.length) {
      root.querySelectorAll(selectors.join(',')).forEach(el => { el.disabled = on; });
    }
    if (opts.footerSelector) {
      const btn = root.querySelector(opts.footerSelector);
      if (btn) btn.disabled = on;
    }
  };

  // --- Stage-tab shell helpers (conventions §1, §8) ------------------------
  // The footer / save-advance / first-paint-fetch / empty-state family every
  // stage tab hand-rolled (mechanics / archetypes / skeleton / reprints / lands
  // / card_gen). The per-status footer COPY and the per-tab body shape stay in
  // the tab; the lifecycle boilerplate (fetch+unwrap, the dataset.lastFooter
  // diff-guard, the save→advance→navigate / advance→navigate sequences with the
  // button text-spinner) lives here.

  // First-paint state fetch for a stage tab. Returns the parsed
  // ``GET /api/wizard/<stageId>/state`` body on 2xx, ``null`` on 404 (the route
  // is missing — caller degrades to its empty state), and throws a normalized
  // ``Error`` (``data.error`` or ``HTTP <n>``) on any other non-OK so the tab's
  // bootstrap ``.catch`` toasts it. Network rejections propagate the same way.
  // Standardizes the graceful-404 path that skeleton/mechanics/archetypes used
  // to throw on while reprints/lands swallowed.
  W.fetchStageState = async function (stageId, query) {
    let url = `/api/wizard/${stageId}/state`;
    if (query && typeof query === 'object') {
      const qs = Object.keys(query)
        .filter(k => query[k] !== undefined && query[k] !== null)
        .map(k => encodeURIComponent(k) + '=' + encodeURIComponent(query[k]))
        .join('&');
      if (qs) url += '?' + qs;
    }
    const resp = await fetch(url);
    if (resp.ok) return resp.json();
    if (resp.status === 404) return null;
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.error || `HTTP ${resp.status}`);
  };

  // ---- Per-instance re-run (version tracking) --------------------------------
  // A "Re-run this step" affordance for the duplicable loop tabs (card_gen,
  // conformance, balance, ai_review). It restores the card pool the instance
  // received on entry and re-runs it + every later step, leaving earlier steps
  // intact — the forward mirror of the engine's review->regen insert span.
  //
  // rerunButtonHtml() emits a hidden button; bindRerunButton(container, stage)
  // toggles its visibility/enabled-state from the stage and wires the click. The
  // button shows only once the instance has run, and is disabled (with a reason)
  // when the instance has no entry snapshot — i.e. a project created before
  // version tracking, which has no history/ to restore from.

  W.rerunButtonHtml = function () {
    return '<div class="wiz-rerun-row" style="margin-bottom:0.8rem">'
      + '<button type="button" class="wiz-btn-secondary" data-role="rerun-step" hidden>'
      + '\u21bb Re-run this step</button></div>';
  };

  W.bindRerunButton = function (container, stage) {
    if (!container) return;
    const btn = container.querySelector('[data-role="rerun-step"]');
    if (!btn) return;
    const ran = !!stage
      && ['completed', 'paused_for_review', 'failed'].indexOf(stage.status) !== -1;
    const hasSnap = !!(stage && stage.entry_snapshot_id);
    btn.hidden = !ran;
    btn.disabled = !hasSnap;
    btn.title = hasSnap
      ? 'Restore the card pool this step received on entry and re-run it plus every later step.'
      : 'Re-run unavailable: this project predates version tracking (no entry snapshot).';
    if (!ran || !hasSnap) { btn.onclick = null; return; }
    btn.onclick = function () {
      W.rerunInstance({
        instanceId: stage.instance_id,
        stageName: stage.display_name || stage.instance_id,
      });
    };
  };

  W.rerunInstance = async function (opts) {
    opts = opts || {};
    const instanceId = opts.instanceId;
    const stageName = opts.stageName || 'this step';
    if (!instanceId) return;
    if (W.editFlow && W.editFlow.isPipelineRunning && W.editFlow.isPipelineRunning()) {
      W.toast('Cancel the running stage first, then retry the re-run.', 'warn');
      return;
    }
    // Reuse the edit-cascade confirm modal: its /edit/preview lists exactly the
    // downstream stages (incl. any art/renders) this re-run will discard.
    const ok = await W.editFlow.confirmCascade({
      from_stage: instanceId,
      title: 'Re-run ' + stageName + '?',
      body: 'Re-running ' + stageName + ' restores the card pool it received on entry, '
        + 'then regenerates it and every later step — including any art and renders '
        + 'already generated. Earlier steps are left untouched.',
    });
    if (!ok) return;
    let data = {};
    try {
      const resp = await W.postJSON('/api/wizard/instance/rerun', { instance_id: instanceId });
      data = await resp.json().catch(function () { return {}; });
      if (!resp.ok) { W.reportError(resp, data, 'Re-run failed'); return; }
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
      return;
    }
    if (data.warning) W.toast(data.warning, 'warn');
    if (data.navigate_to) window.location.assign(data.navigate_to);
  };

  // ---- Retry a FAILED stage (in place) ---------------------------------------
  // A "Retry this step" affordance for any FAILED stage tab. Unlike Re-run, it is
  // non-destructive: it resets the failed stage PENDING->RUNNING and re-runs it,
  // relying on each stage's resume-skip so finished work is kept (no entry-pool
  // restore, no downstream truncation, no confirm). It is the UI for
  // ``engine.retry_current()`` — replaces the old manual pipeline-state.json edit.

  W.retryButtonHtml = function (stage) {
    if (!stage || stage.status !== 'failed') return '';
    return '<button type="button" class="wiz-btn-secondary" data-role="retry-step" title="'
      + 'Reset this failed step to pending and run it again in place. Resumable steps '
      + 'skip work already done, so nothing finished is lost.">↻ Retry this step</button>';
  };

  W.bindRetryButton = function (container, stage) {
    if (!container || !stage) return;
    const btn = container.querySelector('[data-role="retry-step"]');
    if (!btn) return;
    btn.onclick = function () {
      btn.disabled = true;
      W.retryStep({
        instanceId: stage.instance_id,
        stageName: stage.display_name || stage.instance_id,
      }).then(function (ok) { if (!ok) btn.disabled = false; });
    };
  };

  // Returns true on a successful kick (engine now re-running), false otherwise.
  // No navigation: the failed stage transitions in place; the SSE
  // ``pipeline_status: running`` event repaints the strip + active body and
  // dismisses any failure modal, so a hard reload would only be churn.
  W.retryStep = async function (opts) {
    opts = opts || {};
    const instanceId = opts.instanceId || null;
    if (W.editFlow && W.editFlow.isPipelineRunning && W.editFlow.isPipelineRunning()) {
      W.toast('A stage is already running — cancel it first, then retry.', 'warn');
      return false;
    }
    let data = {};
    try {
      const resp = await W.postJSON(
        '/api/wizard/instance/retry',
        instanceId ? { instance_id: instanceId } : {}
      );
      data = await resp.json().catch(function () { return {}; });
      if (!resp.ok) { W.reportError(resp, data, 'Retry failed'); return false; }
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
      return false;
    }
    if (data.warning) W.toast(data.warning, 'warn');
    return true;
  };

  // The empty / loading placeholder a stage tab paints when it has no content:
  // the generating message while an AI run fills it, the idle message otherwise.
  // ``className`` defaults to the shared ``wiz-stage-empty``; tabs with their own
  // empty-state CSS pass their class to keep the styling.
  W.emptyStatePanel = function (opts) {
    opts = opts || {};
    const cls = opts.className || 'wiz-stage-empty';
    const msg = opts.generating ? opts.generatingMsg : opts.emptyMsg;
    return `<div class="${cls}">${W.escHtml(msg || '')}</div>`;
  };

  // Paint a stage-tab footer: the ``dataset.lastFooter`` diff-guard (skip the
  // DOM write when the markup is unchanged, so SSE-driven repaints don't thrash
  // a footer the user may be interacting with) plus the single-primary-button
  // bind. The tab builds ``html`` (its per-status copy) and names its primary
  // control via ``primary = { role, onClick }``.
  W.paintFooter = function (footer, html, primary) {
    if (!footer) return;
    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
    }
    if (primary && primary.role) {
      const btn = footer.querySelector(`[data-role="${primary.role}"]`);
      if (btn && primary.onClick) btn.onclick = primary.onClick;
    }
  };

  // Resolve a stage tab's footer primary button by data-role (re-grabbed each
  // call, since paintFooter may have rebuilt the footer since).
  function footerBtn(stageId, role) {
    const footer = W.tabFooter(W.tabRoot(stageId));
    return role && footer ? footer.querySelector(`[data-role="${role}"]`) : null;
  }

  // Save & Continue: validate → POST the save → POST /api/wizard/advance →
  // navigate, with the footer button's text-spinner (Saving… → Starting…) and a
  // restore-on-failure. Used by the review-gated tabs (mechanics / archetypes /
  // skeleton). opts:
  //   stageId               — for the navigate fallback (next stage's URL).
  //   saveUrl, payload      — the save POST; payload may be an object or a thunk
  //                           read at call time (captures live edits).
  //   validate              — optional () => string|null; a non-empty string is
  //                           toasted as an error and aborts before locking.
  //   isLocked, setLocked   — the tab's re-entrancy guard + form-lock toggle.
  //   btnRole               — the footer primary button's data-role.
  W.saveAndAdvance = async function (opts) {
    if (opts.isLocked && opts.isLocked()) return;
    if (opts.validate) {
      const msg = opts.validate();
      if (msg) { W.toast(msg, 'error'); return; }
    }
    if (opts.setLocked) opts.setLocked(true);
    const btn = footerBtn(opts.stageId, opts.btnRole);
    const original = btn ? btn.textContent : '';
    const restore = () => { if (btn) btn.textContent = original; };
    try {
      if (btn) btn.textContent = 'Saving…';
      const payload = typeof opts.payload === 'function' ? opts.payload() : (opts.payload || {});
      const saveResp = await W.postJSON(opts.saveUrl, payload);
      const saveData = await saveResp.json().catch(() => ({}));
      if (!saveResp.ok) { W.reportError(saveResp, saveData, 'Save failed'); restore(); return; }
      if (btn) btn.textContent = 'Starting…';
      const advResp = await W.postJSON('/api/wizard/advance', {});
      const advData = await advResp.json().catch(() => ({}));
      if (!advResp.ok) { W.reportError(advResp, advData, 'Advance failed'); restore(); return; }
      const next = W.nextStageEntryAfter(opts.stageId);
      const nextHref = next ? `/pipeline/${next.id}` : '/pipeline';
      window.location.assign(advData.navigate_to || saveData.navigate_to || nextHref);
    } catch (err) {
      W.toast('Network error: ' + (err && err.message ? err.message : err), 'error');
      restore();
    } finally {
      if (opts.setLocked) opts.setLocked(false);
    }
  };

  // Resume the engine (POST /api/wizard/advance) from a paused stage, with the
  // footer button's text-spinner. Used by the auto-run tabs (reprints / lands
  // resume / card_gen). opts:
  //   stageId               — for the navigate fallback.
  //   isLocked, setLocked   — optional re-entrancy guard + form-lock toggle.
  //   btnRole               — the footer primary button's data-role.
  //   navigate              — true (default): on success, navigate to the next
  //                           tab. false (card_gen): leave the button disabled
  //                           and let SSE drive the status forward — no nav.
  W.advanceStage = async function (opts) {
    if (opts.isLocked && opts.isLocked()) return;
    const navigate = opts.navigate !== false;
    const btn = footerBtn(opts.stageId, opts.btnRole);
    const original = btn ? btn.textContent : '';
    const restore = () => {
      if (btn) { btn.disabled = false; btn.textContent = original; }
      if (opts.setLocked) opts.setLocked(false);
    };
    if (opts.setLocked) opts.setLocked(true);
    if (btn) { btn.disabled = true; btn.textContent = 'Advancing…'; }
    try {
      const resp = await W.postJSON('/api/wizard/advance', {});
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { W.reportError(resp, data, 'Advance failed'); restore(); return; }
      if (navigate) {
        const next = W.nextStageEntryAfter(opts.stageId);
        const nextHref = next ? `/pipeline/${next.id}` : '/pipeline';
        window.location.assign(data.navigate_to || nextHref);
      }
      // navigate:false → button stays disabled; SSE moves the stage forward.
    } catch (err) {
      W.toast('Network error: ' + (err && err.message ? err.message : err), 'error');
      restore();
    }
  };

  // --- SSE stream bridge (conventions §17) ---------------------------------
  // Wire a streaming stage tab's SSE hook. Owns the boilerplate every streaming
  // tab (mechanics / skeleton / card_gen) hand-rolled: the W.on<Stage>Stream
  // assignment, the event-name → handler dispatch, and the fresh tab-root
  // lookup. The shell (wizard.js) addEventListens the bus events and forwards
  // them here by name; the per-event semantics (collision tags, busy-label,
  // live-slot DOM patch, merge keys) stay in the tab handlers — they diverge too
  // much to fold into one onItem. Pair with W.streamUpsert for the merge-by-key
  // half where it fits (card_gen).
  //
  //   stageId  — "mechanics" / "skeleton" / "card_gen". The hook name is derived
  //              as on<PascalCase>Stream (card_gen → onCardGenStream) to match
  //              the shell's lookup.
  //   handlers — { [sseEventName]: (data, root) => void }. ``root`` is the live
  //              tab body (W.tabRoot(stageId)), resolved fresh per event and null
  //              when the tab isn't mounted (handlers already guard a falsy root).
  W.registerStream = function (stageId, handlers) {
    const pascal = String(stageId).replace(/(^|_)([a-z])/g, (_m, _sep, c) => c.toUpperCase());
    W['on' + pascal + 'Stream'] = function (name, data) {
      const fn = handlers[name];
      if (fn) fn(data || {}, W.tabRoot(stageId));
    };
  };

  // Merge a streamed item into a live list by key: replace the element whose key
  // matches (so a duplicate delivery from an SSE replay + a /state refetch is
  // idempotent), else append. Returns the item's index. The merge-by-key half of
  // the streaming bookkeeping; card_gen keys by collector_number.
  W.streamUpsert = function (list, item, keyFn) {
    const key = keyFn(item);
    const idx = list.findIndex((el) => keyFn(el) === key);
    if (idx >= 0) {
      list[idx] = item;
      return idx;
    }
    list.push(item);
    return list.length - 1;
  };
})();
