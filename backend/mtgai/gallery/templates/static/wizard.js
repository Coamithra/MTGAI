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
    builtBodies: new Set(),
    eventSource: null,
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
      return `
        <button type="button" class="wiz-tab" data-tab-id="${escAttr(t.id)}">
          ${escHtml(t.title)}${statusBadge}
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
    if (!state.pipeline) return;
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
    if (!tab || tab.kind !== 'stage') return;
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
})();
