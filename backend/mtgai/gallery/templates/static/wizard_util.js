/**
 * wizard_util.js — shared leaf helpers for the pipeline wizard tabs.
 *
 * Loaded first (before wizard.js and every per-tab module) so each module can
 * alias these off ``window.MTGAIWizard`` at the top of its IIFE instead of
 * copying byte-identical blocks. This is the "call this, not copy this" leaf
 * layer of the shared-components pass (plans/wizard-tab-shared-components.md).
 *
 * Pure, dependency-free helpers only: HTML/attr/CSS escaping, the stage-tab DOM
 * lookups that were forked under three different names (bodyRoot/tabRoot,
 * getFooter, isPastTab), and the standard AI-action error toast. Anything that
 * owns the AI-lock / fetch lifecycle lives in wizard.js, not here.
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
})();
