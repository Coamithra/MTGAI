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

  // --- AI-action error reporting -------------------------------------------
  // Standard toast for a failed AI-tab action: the 409 "AI busy" branch plus a
  // generic fallback. Lifted verbatim from the archetypes/skeleton copies.
  W.reportError = function (resp, data, fallback) {
    if (resp.status === 409 && data && data.running_action) {
      W.toast(`${data.running_action} is in progress — try again when it finishes.`, 'error');
    } else {
      W.toast((data && data.error) || `${fallback} (${resp.status})`, 'error');
    }
  };

  // --- AI provenance badge (conventions §5) --------------------------------
  // One badge component, one canonical vocab (ai / user / auto), display-only.
  // The three tabs that show provenance had each grown their own markup + vocab
  // (skeleton: wiz-ai-badge "AI" / wiz-skel-userbadge "edited" / nothing for
  // 'default'; reprints: wiz-reprints-knob-badge "auto"/"user"; theme/mechanics/
  // archetypes: a boolean _ai_generated → wiz-ai-badge "AI" / nothing). This maps
  // every synonym onto one rendering so they can't drift again:
  //   true  / 'ai'                     → the established .wiz-ai-badge "AI"
  //   'user'                           → .wiz-prov-badge.wiz-prov-user "edited"
  //   'auto' / 'default'               → .wiz-prov-badge.wiz-prov-auto "auto"
  //   false / null / undefined / ''    → '' (a hand-authored row carries no badge)
  // So provenanceBadge('default') and provenanceBadge('auto') render identically,
  // as do provenanceBadge(true) and provenanceBadge('ai').
  //   opts.role — emit data-role="<role>" so a clear-on-edit listener can find +
  //               remove the badge (the list-item badges use 'ai-badge').
  W.provenanceBadge = function (prov, opts) {
    const role = opts && opts.role ? ` data-role="${W.escAttr(opts.role)}"` : '';
    if (prov === true || prov === 'ai') return `<span class="wiz-ai-badge"${role}>AI</span>`;
    if (prov === 'user') return `<span class="wiz-prov-badge wiz-prov-user"${role}>edited</span>`;
    if (prov === 'auto' || prov === 'default') {
      return `<span class="wiz-prov-badge wiz-prov-auto"${role}>auto</span>`;
    }
    return '';
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
  //                   native confirm() (e.g. an initial generate has nothing to
  //                   overwrite, or the confirm is conditional on dirty state).
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
      if (msg && !window.confirm(msg)) return false;
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
  W.fetchStageState = async function (stageId) {
    const resp = await fetch(`/api/wizard/${stageId}/state`);
    if (resp.ok) return resp.json();
    if (resp.status === 404) return null;
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.error || `HTTP ${resp.status}`);
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

  // --- SSE stream bridge (conventions §14) ---------------------------------
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
