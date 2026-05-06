/**
 * Wizard shell — tab strip, global progress strip, URL routing.
 *
 * Bootstraps from the global ``WIZARD_STATE`` set by wizard.html.
 * Each tab body is built lazily on first activation; tabs are
 * pre-mounted (hidden) the first time the user reaches them.
 *
 * URL contract: each tab maps to ``/pipeline/<tab_id>``. Refresh
 * lands on the same tab because the server resolves the URL
 * fragment back to a visible tab on every request (see
 * ``mtgai.pipeline.wizard``).
 */

(function () {
  'use strict';

  // ------------------------------------------------------------------
  // State
  // ------------------------------------------------------------------

  const state = {
    activeSet: WIZARD_STATE.active_set,
    activeTabId: WIZARD_STATE.active_tab_id,
    latestTabId: WIZARD_STATE.latest_tab_id,
    tabs: WIZARD_STATE.visible_tabs,
    pipeline: WIZARD_STATE.pipeline_state,
    theme: WIZARD_STATE.theme,
    // stage_id -> bool, mirrors settings.break_points. Both the
    // Project Settings break-point list and the per-tab "Stop after
    // this step" checkbox in stage headers read/write through this
    // map (each via its own handler) so toggles in one surface show
    // up in the other without a refetch.
    breakPoints: WIZARD_STATE.break_points || {},
    builtBodies: new Set(),
    eventSource: null,
    // tabId -> { dirty: bool, payload?: object } — held in browser memory
    // until Accept/Cancel per design §9.2. Per-tab modules read/write this
    // via MTGAIWizard.editDrafts (no autosave; nothing is persisted until
    // Accept).
    editDrafts: new Map(),
  };

  // Per-stage UI hooks registered by wizard_stage.js / wizard_theme.js.
  // Modules call ``window.MTGAIWizard.registerTabRenderer(kind, fn)`` at
  // load time; the shell calls them when the tab body needs mounting.
  const renderers = {};

  // Public surface — tab modules attach to this object so they can be
  // loaded independently of wizard.js's internal scope.
  window.MTGAIWizard = window.MTGAIWizard || {};
  window.MTGAIWizard.registerTabRenderer = function (kind, fn) {
    renderers[kind] = fn;
  };
  window.MTGAIWizard.getState = () => state;
  window.MTGAIWizard.toast = showToast;
  window.MTGAIWizard.postJSON = (url, body) => fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  // Edit flow (§9) — modal preview + draft state + cascade Accept.
  // Per-tab renderers call window.MTGAIWizard.editFlow.* to gate their
  // destructive edits behind the warning modal. Draft state is held in
  // ``state.editDrafts`` (keyed by tab id) so navigating between tabs
  // doesn't lose in-progress edits.
  //
  // Load-order assumption: this assignment runs at IIFE evaluation time
  // (before any DOMContentLoaded handler fires) so per-tab renderers,
  // which run from inside ``init`` -> ``mountTabBody``, always observe
  // a populated ``editFlow``. wizard_*.js are loaded after wizard.js by
  // wizard.html (see {% block scripts %}), reinforcing the order.
  window.MTGAIWizard.editFlow = {
    isPipelineRunning() {
      return !!(state.pipeline && state.pipeline.overall_status === 'running');
    },
    isPastTab(tabId) {
      // A tab is "past" if it's not the latest one — Project Settings
      // is past once Theme exists, Theme is past once any pipeline
      // stage has begun, etc. Same notion the latestTabId tracks.
      return tabId !== state.latestTabId && state.tabs.some(t => t.id === tabId);
    },
    getDraft(tabId) {
      return state.editDrafts.get(tabId) || null;
    },
    setDraft(tabId, draft) {
      state.editDrafts.set(tabId, draft);
      renderTabStrip();
    },
    clearDraft(tabId) {
      state.editDrafts.delete(tabId);
      renderTabStrip();
    },
    async preview({ from_stage, clear_theme_json }) {
      const resp = await fetch('/api/wizard/edit/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          from_stage,
          clear_theme_json: !!clear_theme_json,
        }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.error || `HTTP ${resp.status}`);
      }
      return await resp.json();
    },
    async accept({ from_stage, clear_theme_json, theme_payload, set_params_patch, theme_input }) {
      const body = {
        from_stage,
        clear_theme_json: !!clear_theme_json,
      };
      if (theme_payload !== undefined) body.theme_payload = theme_payload;
      if (set_params_patch !== undefined) body.set_params_patch = set_params_patch;
      if (theme_input !== undefined) body.theme_input = theme_input;
      const resp = await fetch('/api/wizard/edit/accept', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        const err = new Error(data.error || `HTTP ${resp.status}`);
        err.status = resp.status;
        throw err;
      }
      return data;
    },
    /**
     * Open the cascade-clear warning modal. Returns a Promise that
     * resolves to true if the user clicks "Continue", false if Cancel
     * (or backdrop-close). Pipeline-running case auto-rejects with a
     * toast so the modal isn't shown — Accept would 409 anyway.
     */
    async confirmCascade({ from_stage, clear_theme_json, title, body }) {
      if (this.isPipelineRunning()) {
        showToast('Cancel the running stage first, then retry the edit.', 'warn');
        return false;
      }
      let preview;
      try {
        preview = await this.preview({ from_stage, clear_theme_json });
      } catch (err) {
        showToast('Preview failed: ' + err.message, 'error');
        return false;
      }
      return await openCascadeModal({
        title: title || 'Confirm cascade',
        intro: body || 'Editing this stage will discard all generated content from later stages.',
        cleared: preview.cleared,
        clearThemeJson: preview.clear_theme_json,
      });
    },
  };

  // ------------------------------------------------------------------
  // Init
  // ------------------------------------------------------------------

  document.addEventListener('DOMContentLoaded', init);

  function init() {
    const root = document.getElementById('wizard-app');
    if (!root) return;

    root.innerHTML = `
      <nav class="wiz-tab-strip" id="wiz-tab-strip" aria-label="Wizard tabs"></nav>
      <div class="wiz-progress-strip" id="wiz-progress-strip" hidden>
        <span class="wiz-progress-stage" id="wiz-progress-stage"></span>
        <span class="wiz-progress-activity" id="wiz-progress-activity"></span>
        <div class="wiz-progress-bar"><div class="wiz-progress-bar-fill" id="wiz-progress-bar-fill"></div></div>
        <button class="wiz-progress-cancel" id="wiz-progress-cancel" type="button">Cancel</button>
      </div>
      <div class="wiz-tab-bodies" id="wiz-tab-bodies"></div>
      <div class="wiz-toast" id="wiz-toast"></div>
    `;

    renderTabStrip();
    showTab(state.activeTabId, /* push */ false);

    document.getElementById('wiz-progress-cancel').addEventListener('click', cancelCurrent);
    window.addEventListener('popstate', onPopState);

    connectSSE();
  }

  // ------------------------------------------------------------------
  // Tab strip
  // ------------------------------------------------------------------

  function renderTabStrip() {
    const strip = document.getElementById('wiz-tab-strip');
    if (!strip) return;
    strip.innerHTML = state.tabs.map(t => {
      const statusBadge = t.status
        ? `<span class="wiz-tab-status ${t.status}">${t.status.replace(/_/g, ' ')}</span>`
        : '';
      // Pencil = tab is in edit mode (per-tab module wrote a draft).
      // Per design §9.2 the icon stays put while the user navigates so
      // they can find their way back to the in-progress edit.
      const pencil = state.editDrafts.has(t.id)
        ? ' <span class="wiz-tab-pencil" title="Editing — changes not yet applied" aria-label="Editing">✏️</span>'
        : '';
      return `
        <button type="button" class="wiz-tab" data-tab-id="${escAttr(t.id)}">
          ${escHtml(t.title)}${pencil}${statusBadge}
        </button>
      `;
    }).join('');

    strip.querySelectorAll('.wiz-tab').forEach(btn => {
      btn.addEventListener('click', () => showTab(btn.dataset.tabId, /* push */ true));
    });

    updateActiveTabHighlight();
  }

  function updateActiveTabHighlight() {
    document.querySelectorAll('.wiz-tab').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tabId === state.activeTabId);
    });
  }

  // ------------------------------------------------------------------
  // Tab body mounting
  // ------------------------------------------------------------------

  function showTab(tabId, push) {
    const tab = state.tabs.find(t => t.id === tabId);
    if (!tab) return;

    state.activeTabId = tabId;

    if (!state.builtBodies.has(tabId)) {
      mountTabBody(tab);
      state.builtBodies.add(tabId);
    } else {
      // Re-invoke the renderer so SSE updates that arrived while the
      // user was on a different tab paint into the body before we
      // unhide it. Without this, the placeholder shows stage state
      // from whenever this tab was last active.
      const body = document.querySelector(
        `.wiz-tab-body[data-tab-id="${cssEsc(tabId)}"]`,
      );
      const renderer = renderers[tab.kind];
      if (body && renderer) renderer({ tab, root: body, state, rerender: true });
    }

    document.querySelectorAll('.wiz-tab-body').forEach(el => {
      el.hidden = el.dataset.tabId !== tabId;
    });

    updateActiveTabHighlight();

    if (push) {
      history.pushState({ tabId }, '', `/pipeline/${tabId}`);
    }
  }

  function mountTabBody(tab) {
    const container = document.getElementById('wiz-tab-bodies');
    const body = document.createElement('section');
    body.className = 'wiz-tab-body';
    body.dataset.tabId = tab.id;
    body.innerHTML = renderTabShell(tab);
    container.appendChild(body);

    const renderer = renderers[tab.kind];
    if (renderer) {
      renderer({ tab, root: body, state });
    }
  }

  function renderTabShell(tab) {
    const statusPill = tab.status
      ? `<span class="wiz-status-pill ${tab.status}">${tab.status.replace(/_/g, ' ')}</span>`
      : '';
    return `
      <header class="wiz-tab-header">
        <h2>${escHtml(tab.title)}</h2>
        ${statusPill}
        <span class="wiz-process-line" data-role="process-line"></span>
        <div class="wiz-tab-header-actions" data-role="header-actions"></div>
      </header>
      <div class="wiz-tab-content" data-role="content"></div>
      <footer class="wiz-tab-footer" data-role="footer"></footer>
    `;
  }

  // ------------------------------------------------------------------
  // History
  // ------------------------------------------------------------------

  function onPopState(ev) {
    const id = (ev.state && ev.state.tabId) || tabIdFromPathname();
    if (id && state.tabs.some(t => t.id === id)) {
      showTab(id, /* push */ false);
    }
  }

  function tabIdFromPathname() {
    const m = window.location.pathname.match(/^\/pipeline\/([^/]+)/);
    return m ? m[1] : null;
  }

  // ------------------------------------------------------------------
  // SSE — global progress strip + per-stage updates
  // ------------------------------------------------------------------

  function connectSSE() {
    if (state.eventSource) state.eventSource.close();
    state.eventSource = new EventSource('/api/pipeline/events');

    state.eventSource.addEventListener('stage_update', (e) => {
      const data = JSON.parse(e.data);
      updateStageStatus(data.stage_id, data.status, data.progress);
    });

    state.eventSource.addEventListener('item_progress', (e) => {
      const data = JSON.parse(e.data);
      updateStageProgress(
        data.stage_id, data.item, data.completed, data.total, data.detail,
      );
    });

    state.eventSource.addEventListener('cost_update', (e) => {
      const data = JSON.parse(e.data);
      if (state.pipeline) {
        state.pipeline.total_cost_usd = data.total_cost;
        rerenderActiveStageBody();
      }
    });

    state.eventSource.addEventListener('pipeline_status', (e) => {
      const data = JSON.parse(e.data);
      if (!state.pipeline) return;
      state.pipeline.overall_status = data.overall_status;
      state.pipeline.current_stage_id = data.current_stage;
      if (
        data.overall_status === 'completed'
        || data.overall_status === 'cancelled'
        || data.overall_status === 'failed'
      ) {
        hideProgressStrip();
      }
      rerenderActiveStageBody();
    });

    state.eventSource.addEventListener('phase', (e) => {
      handlePhaseEvent(JSON.parse(e.data));
    });

    state.eventSource.onerror = () => {
      // EventSource auto-reconnects.
    };
  }

  function updateStageStatus(stageId, status, progress) {
    if (!state.pipeline) {
      // The bootstrap snapshot was rendered before any pipeline-state
      // existed (e.g. user is on Theme and the post-extraction
      // auto-advance just kicked off the engine in the background).
      // Pull the freshly-persisted state so subsequent SSE events have
      // somewhere to write — and so dependent UI like the Theme tab's
      // Next-step button hides itself once `state.pipeline` is truthy.
      // Fire-and-forget: if the fetch fails (network blip), we'll try
      // again on the next stage_update.
      hydratePipelineFromServer().then(() => {
        // Re-apply this very event so the eventually-hydrated state
        // reflects the status we just heard about.
        if (state.pipeline) updateStageStatus(stageId, status, progress);
      });
      return;
    }
    const stage = state.pipeline.stages.find(s => s.stage_id === stageId);
    if (!stage) return;
    stage.status = status;
    if (progress) stage.progress = progress;

    const tabIdx = state.tabs.findIndex(t => t.id === stageId);
    if (tabIdx >= 0) {
      state.tabs[tabIdx].status = status;
    } else if (status !== 'pending') {
      // Stage just left PENDING during this session — the bootstrap
      // snapshot didn't include it but the visibility rule (compute_visible_tabs
      // in wizard.py) now would. Append the tab so the strip surfaces
      // it without forcing the user to refresh.
      state.tabs.push({
        id: stageId,
        title: stage.display_name,
        kind: 'stage',
        status,
      });
      state.latestTabId = stageId;
    }
    renderTabStrip();
    rerenderActiveStageBody();
  }

  // Lazy hydrator for the case where the bootstrap had no pipeline_state
  // (user landed on Theme before kickoff). Hits the existing /api/pipeline/
  // state endpoint, which returns the engine's in-memory state when one
  // is attached.
  let _hydrateInFlight = null;
  function hydratePipelineFromServer() {
    if (_hydrateInFlight) return _hydrateInFlight;
    _hydrateInFlight = fetch('/api/pipeline/state')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data && data.config) {
          state.pipeline = data;
          rerenderActiveStageBody();
        }
      })
      .catch(() => null)
      .finally(() => { _hydrateInFlight = null; });
    return _hydrateInFlight;
  }

  function updateStageProgress(stageId, item, completed, total, detail) {
    if (!state.pipeline) return;
    const stage = state.pipeline.stages.find(s => s.stage_id === stageId);
    if (!stage) return;
    stage.progress.current_item = item;
    stage.progress.completed_items = completed;
    stage.progress.total_items = total;
    stage.progress.detail = detail;
    rerenderActiveStageBody();
  }

  function rerenderActiveStageBody() {
    const tab = state.tabs.find(t => t.id === state.activeTabId);
    // Stage + content (Theme) kinds both react to pipeline SSE events;
    // Theme uses them to refresh its footer Next-step button when the
    // engine kicks off in the background. Project tab is a one-shot
    // form fed by its own fetch, so no SSE-driven repaint there.
    if (!tab || (tab.kind !== 'stage' && tab.kind !== 'content')) return;
    const body = document.querySelector(`.wiz-tab-body[data-tab-id="${cssEsc(tab.id)}"]`);
    if (!body) return;
    const renderer = renderers[tab.kind];
    if (renderer) renderer({ tab, root: body, state, rerender: true });
  }

  function handlePhaseEvent(data) {
    const phase = data.phase || '';

    // Phase events come from non-pipeline AI runs too (theme section
    // refreshes etc.) — without this, the strip would stick at 100%
    // forever after a section refresh because no `pipeline_status`
    // terminal event ever fires for that path.
    if (phase === 'done') {
      hideProgressStrip();
      return;
    }

    showProgressStrip();
    const stageEl = document.getElementById('wiz-progress-stage');
    const activityEl = document.getElementById('wiz-progress-activity');
    const fillEl = document.getElementById('wiz-progress-bar-fill');
    if (!stageEl || !activityEl || !fillEl) return;

    const stageId = data.stage_id || '';
    const stageObj = state.pipeline
      ? state.pipeline.stages.find(s => s.stage_id === stageId)
      : null;
    stageEl.textContent = stageObj ? stageObj.display_name : stageId;
    activityEl.textContent = data.activity || '';

    if (phase === 'starting') fillEl.style.width = '5%';
    else if (phase === 'running') fillEl.style.width = '30%';
    else if (phase === 'generation') fillEl.style.width = '60%';
  }

  function showProgressStrip() {
    const strip = document.getElementById('wiz-progress-strip');
    if (strip) strip.hidden = false;
  }

  function hideProgressStrip() {
    const strip = document.getElementById('wiz-progress-strip');
    if (strip) strip.hidden = true;
  }

  async function cancelCurrent() {
    try {
      await fetch('/api/ai/cancel', { method: 'POST' });
    } catch (_e) {
      // Best-effort — server already logs the failure.
    }
  }

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------

  function showToast(message, kind) {
    const toast = document.getElementById('wiz-toast');
    if (!toast) return;
    toast.textContent = message;
    toast.className = `wiz-toast show ${kind || 'success'}`;
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(() => {
      toast.classList.remove('show');
    }, 2500);
  }

  function escHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
  }

  function escAttr(text) {
    return escHtml(text).replace(/"/g, '&quot;');
  }

  function cssEsc(s) {
    if (window.CSS && CSS.escape) return CSS.escape(s);
    return String(s).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
  }

  // ------------------------------------------------------------------
  // Cascade-clear modal (design §9.1)
  // ------------------------------------------------------------------

  /**
   * Show the §9 warning modal listing exactly what will be cleared.
   * Returns a promise that resolves true if the user clicks Continue,
   * false if Cancel / Esc / backdrop click. Continue does NOT mutate
   * anything — it just lets the caller proceed into edit mode (or
   * straight to Accept on tabs with no editable form).
   */
  function openCascadeModal({ title, intro, cleared, clearThemeJson }) {
    return new Promise(resolve => {
      const overlay = document.createElement('div');
      overlay.className = 'wiz-modal-overlay';
      const items = (cleared || []).map(c => {
        const label = c.item_count > 0
          ? `${escHtml(c.display_name)} (${c.item_count})`
          : escHtml(c.display_name);
        return `<li>${label} <span class="wiz-modal-status">${escHtml(c.status.replace(/_/g, ' '))}</span></li>`;
      }).join('');
      const themeRow = clearThemeJson
        ? `<li>theme.json <span class="wiz-modal-status">setting + constraints + card requests</span></li>`
        : '';
      const empty = !items && !themeRow
        ? '<li class="wiz-modal-empty">Nothing on disk to clear — Continue applies your edits and re-runs from this point.</li>'
        : '';
      overlay.innerHTML = `
        <div class="wiz-modal" role="dialog" aria-modal="true" aria-labelledby="wiz-modal-title">
          <h2 id="wiz-modal-title">${escHtml(title)}</h2>
          <p>${escHtml(intro)}</p>
          <p class="wiz-modal-cleared-label">The following will be cleared and regenerated when you Accept:</p>
          <ul class="wiz-modal-cleared">${themeRow}${items}${empty}</ul>
          <p class="wiz-modal-foot">Cancel to keep things as they are. Continue to start editing — your changes won't take effect until you Accept.</p>
          <div class="wiz-modal-actions">
            <button type="button" class="wiz-btn-secondary" data-modal-action="cancel">Cancel</button>
            <button type="button" class="wiz-btn-primary" data-modal-action="continue">Continue</button>
          </div>
        </div>
      `;
      document.body.appendChild(overlay);

      function close(result) {
        overlay.removeEventListener('keydown', onKey, true);
        overlay.remove();
        resolve(result);
      }
      function onKey(e) {
        if (e.key === 'Escape') { e.stopPropagation(); close(false); }
      }
      overlay.addEventListener('keydown', onKey, true);
      overlay.addEventListener('click', e => {
        if (e.target === overlay) close(false);
      });
      overlay.querySelector('[data-modal-action="cancel"]').addEventListener('click', () => close(false));
      overlay.querySelector('[data-modal-action="continue"]').addEventListener('click', () => close(true));
      // Focus Continue so keyboard users can confirm with Enter; Esc cancels.
      const cont = overlay.querySelector('[data-modal-action="continue"]');
      if (cont) cont.focus();
    });
  }
})();
