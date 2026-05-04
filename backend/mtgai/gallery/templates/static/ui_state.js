/**
 * Tiny localStorage + runtime-state helper shared across all pages.
 *
 * Layout:
 *   `mtgai:active_set`               -> last-used set code (string)
 *   `mtgai:<setCode>:<key>`          -> per-set UI ephemera
 *
 * Per-set keys live under the set so switching to a different set
 * doesn't bleed filters / drafts / scroll positions across.
 *
 * `fetchRuntimeState(setCode?)` hits `GET /api/runtime/state` and
 * returns the parsed payload. Used by every page on mount to hydrate
 * server-side truth (active runs, pipeline state, theme.json).
 */

(function () {
  'use strict';

  const ACTIVE_SET_KEY = 'mtgai:active_set';
  const DEFAULT_SET = 'ASD';

  function setCode() {
    try {
      return (localStorage.getItem(ACTIVE_SET_KEY) || DEFAULT_SET).toUpperCase();
    } catch (e) {
      return DEFAULT_SET;
    }
  }

  function setSetCode(code) {
    if (!code) return;
    try {
      localStorage.setItem(ACTIVE_SET_KEY, String(code).toUpperCase());
    } catch (e) {
      // Quota / privacy mode — silently no-op.
    }
  }

  function _key(key, code) {
    return 'mtgai:' + (code || setCode()) + ':' + key;
  }

  function get(key, fallback, code) {
    try {
      const raw = localStorage.getItem(_key(key, code));
      if (raw === null) return fallback;
      return JSON.parse(raw);
    } catch (e) {
      return fallback;
    }
  }

  function set(key, value, code) {
    try {
      localStorage.setItem(_key(key, code), JSON.stringify(value));
    } catch (e) {
      // Quota — silently no-op.
    }
  }

  function remove(key, code) {
    try {
      localStorage.removeItem(_key(key, code));
    } catch (e) {
      // ignore
    }
  }

  /**
   * Fetch /api/runtime/state. Returns the parsed payload or null on
   * any error (network down, server restarting). Pages should treat
   * null as "fall back to defaults", not a hard failure.
   */
  async function fetchRuntimeState(code) {
    try {
      const url = code
        ? '/api/runtime/state?set_code=' + encodeURIComponent(code)
        : '/api/runtime/state';
      const resp = await fetch(url);
      if (!resp.ok) return null;
      return await resp.json();
    } catch (e) {
      console.warn('[ui_state] /api/runtime/state failed:', e);
      return null;
    }
  }

  /**
   * Persist `code` as the server-side active set. Returns the refreshed
   * runtime-state payload on success, or null on error. Callers are
   * expected to follow up with a full-page reload — the active set is
   * baked into server-rendered templates (page titles, mounted
   * /renders, /art static dirs) so partial in-place updates would
   * leave the UI inconsistent.
   */
  async function activateSet(code) {
    if (!code) return null;
    try {
      const resp = await fetch('/api/runtime/active-set', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: String(code).toUpperCase() }),
      });
      if (!resp.ok) {
        console.warn('[ui_state] activateSet failed:', resp.status);
        return null;
      }
      const payload = await resp.json();
      if (payload && payload.active_set) setSetCode(payload.active_set);
      return payload;
    } catch (e) {
      console.warn('[ui_state] activateSet error:', e);
      return null;
    }
  }

  /**
   * Scaffold a new set on disk and activate it. Returns the refreshed
   * runtime-state payload on success, ``{error}`` on a 4xx response so
   * the modal can render the message inline (e.g. "set already exists"),
   * or null on a network failure.
   */
  async function createSet(code, name) {
    if (!code) return { error: 'Set code is required' };
    try {
      const resp = await fetch('/api/runtime/sets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: String(code).toUpperCase(),
          name: name || null,
        }),
      });
      if (!resp.ok) {
        let body = null;
        try { body = await resp.json(); } catch (e) { /* not JSON */ }
        return { error: (body && body.error) || ('HTTP ' + resp.status) };
      }
      const payload = await resp.json();
      if (payload && payload.active_set) setSetCode(payload.active_set);
      return payload;
    } catch (e) {
      console.warn('[ui_state] createSet error:', e);
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
    activateSet: activateSet,
    createSet: createSet,
  };
})();
