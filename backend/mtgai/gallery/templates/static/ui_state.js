/**
 * Tiny localStorage + runtime-state helper shared across all pages.
 *
 * The active-project code lives only in process / page memory — the
 * server holds the authoritative pointer (in-memory, set on .mtg
 * Open / Materialize, cleared on New) and pages mirror it locally so
 * per-set localStorage keys (`mtgai:<setCode>:configure.preset`) can
 * prefix correctly. There is no `mtgai:active_set` localStorage key.
 *
 * `fetchRuntimeState()` hits `GET /api/runtime/state` and returns the
 * parsed payload. Used by every page on mount to hydrate server-side
 * truth (active set, active runs, pipeline state, theme).
 */

(function () {
  'use strict';

  let _setCode = '';

  function setCode() {
    return _setCode;
  }

  function setSetCode(code) {
    _setCode = String(code || '').toUpperCase();
  }

  function _key(key, code) {
    return 'mtgai:' + (code || setCode()) + ':' + key;
  }

  // Per-set get/set/remove are a no-op when no project is open — the
  // alternative `mtgai::key` prefix would silently bleed across sets.
  function get(key, fallback, code) {
    const c = code || setCode();
    if (!c) return fallback;
    try {
      const raw = localStorage.getItem(_key(key, c));
      if (raw === null) return fallback;
      return JSON.parse(raw);
    } catch (e) {
      return fallback;
    }
  }

  function set(key, value, code) {
    const c = code || setCode();
    if (!c) return;
    try {
      localStorage.setItem(_key(key, c), JSON.stringify(value));
    } catch (e) {
      // Quota — silently no-op.
    }
  }

  function remove(key, code) {
    const c = code || setCode();
    if (!c) return;
    try {
      localStorage.removeItem(_key(key, c));
    } catch (e) {
      // ignore
    }
  }

  /**
   * Fetch /api/runtime/state. Returns the parsed payload or null on
   * any error (network down, server restarting). Pages should treat
   * null as "fall back to defaults", not a hard failure.
   */
  async function fetchRuntimeState() {
    try {
      // Server reads the active project from in-memory state.
      const resp = await fetch('/api/runtime/state');
      if (!resp.ok) return null;
      return await resp.json();
    } catch (e) {
      console.warn('[ui_state] /api/runtime/state failed:', e);
      return null;
    }
  }

  window.MtgaiState = {
    setCode: setCode,
    setSetCode: setSetCode,
    get: get,
    set: set,
    remove: remove,
    fetchRuntimeState: fetchRuntimeState,
  };
})();
