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
})();
