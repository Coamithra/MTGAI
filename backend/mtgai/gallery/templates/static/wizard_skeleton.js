/**
 * Wizard Skeleton tab — the seed skeleton + its LLM-tweaked themed matrix.
 *
 * Registers via ``W.registerStageRenderer('skeleton', ...)`` so the standard
 * wizard_stage.js shell owns the header (status pill, break-point toggle,
 * Edit button); we paint the body + footer.
 *
 * This tab folds in the (tab-less) ``constraints`` stage: the skeleton stage
 * writes the deterministic seed (skeleton.json), then the constraints stage
 * relabels it into a free-text matrix (constraints.json). The body shows both
 * side by side — seed descriptor on the left, the editable themed blob on the
 * right — so the user reviews and tweaks the matrix before card generation.
 *
 * Because ``constraints`` has no tab of its own, its status (not skeleton's)
 * drives the review controls here: the footer's Save & Continue appears when
 * the constraints stage is ``paused_for_review`` on the latest tab. wizard.js's
 * updateStageStatus mirrors constraints stage_update events onto this tab.
 *
 * Conventions:
 *   §1  one primary "Save & Continue" footer button (when paused for review)
 *   §3  form lock during AI gen
 *   §6  past-tab edits route through wizard_stage.js / W.editFlow
 *   §8  status pill flows from the (folded) constraints stage state
 *   §13 section-level Refresh AI button, always rendered on the latest tab
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'skeleton';
  const CONSTRAINTS_ID = 'constraints';

  const COLOR_FULL = {
    W: 'White', U: 'Blue', B: 'Black', R: 'Red', G: 'Green',
    multicolor: 'Multicolor', colorless: 'Colorless',
  };

  const local = {
    initialized: false,
    seedById: {},      // slot_id -> seed slot dict
    matrix: [],        // [{slot_id, blob, reserved_card}] in matrix order
    hasMatrix: false,
    setParams: { set_name: '', set_size: 0 },
    themeSummary: '',
    modelId: '',
    constraintsStatus: 'pending',
    lastConstraintsStatus: null,
    locked: false,
    bootstrapping: false,
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ----------------------------------------------------------------------

  function render({ root, state, content, footer }) {
    const liveStatus = constraintsStatusFrom(state);
    if (!local.initialized) {
      local.initialized = true;
      local.constraintsStatus = liveStatus;
      local.lastConstraintsStatus = liveStatus;
      content.innerHTML = mountShellHtml();
      bootstrap(root, state).catch(err =>
        W.toast('Failed to load skeleton state: ' + err.message, 'error'));
      paintFooter(footer, state);
      return;
    }

    // Rerender path (SSE-driven). The constraints stage is tab-less, so we
    // watch its status here: when it flips into a terminal/paused state and
    // we still have no matrix (the derive finished while we were mounted),
    // re-pull so the grid fills.
    const prev = local.lastConstraintsStatus;
    local.lastConstraintsStatus = liveStatus;
    local.constraintsStatus = liveStatus;
    const justSettled =
      prev !== liveStatus
      && liveStatus !== 'pending'
      && liveStatus !== 'running'
      && !local.hasMatrix
      && !local.bootstrapping;
    if (justSettled) {
      local.bootstrapping = true;
      bootstrap(root, state)
        .catch(err => W.toast('Failed to refresh matrix: ' + err.message, 'error'))
        .finally(() => { local.bootstrapping = false; });
      return;
    }
    paintFooter(footer, state);
    setLocked(local.locked);
  }

  function constraintsStatusFrom(state) {
    const stages = state && state.pipeline && state.pipeline.stages;
    if (!stages) return local.constraintsStatus || 'pending';
    const c = stages.find(s => s.stage_id === CONSTRAINTS_ID);
    return c ? c.status : 'pending';
  }

  function mountShellHtml() {
    return `
      <div class="wiz-skel-summary" data-role="skel-summary">
        <div class="wiz-skel-loading">Loading skeleton…</div>
      </div>
      <div class="wiz-skel-grid" data-role="skel-grid"></div>
    `;
  }

  // ----------------------------------------------------------------------

  async function bootstrap(root, state) {
    const resp = await fetch('/api/wizard/constraints/state');
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.error || `HTTP ${resp.status}`);
    }
    const data = await resp.json();
    local.seedById = {};
    (Array.isArray(data.seed) ? data.seed : []).forEach(s => {
      if (s && s.slot_id) local.seedById[s.slot_id] = s;
    });
    local.matrix = Array.isArray(data.matrix) ? data.matrix : [];
    local.hasMatrix = !!data.has_matrix;
    local.setParams = data.set_params || local.setParams;
    local.themeSummary = data.theme_summary || '';
    local.modelId = data.model_id || '';
    if (data.constraints_status) local.constraintsStatus = data.constraints_status;

    paintSummary(root, state);
    paintGrid(root, state);
    paintFooter(getFooter(root), state);
  }

  // ----------------------------------------------------------------------
  // Summary block + §13 Refresh button
  // ----------------------------------------------------------------------

  function paintSummary(root, state) {
    const slot = root.querySelector('[data-role="skel-summary"]');
    if (!slot) return;
    const sp = local.setParams;
    const isPast = isPastTab(state);
    const refreshLabel = local.hasMatrix ? 'Re-derive AI…' : 'Derive matrix';
    const refreshTitle = isPast
      ? 'Use Edit above to revise the skeleton/matrix of a past stage.'
      : (local.hasMatrix
        ? 'Re-run the LLM relabel + request placement. Your inline edits are replaced.'
        : 'Run the LLM relabel + request placement now.');
    const placed = local.matrix.filter(m => m.reserved_card).length;
    slot.innerHTML = `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">Skeleton → themed matrix</h3>
        <button type="button" class="wiz-btn-secondary wiz-refresh-btn"
                data-role="skel-refresh"
                title="${escAttr(refreshTitle)}" ${isPast ? 'disabled' : ''}>
          ${escHtml(refreshLabel)}
        </button>
      </div>
      <p class="wiz-skel-blurb">The deterministic seed (left) relabeled to fit the set (right). Each themed blob becomes one card's generation brief — edit any of them, then continue.</p>
      <dl class="wiz-skel-context">
        <dt>Set</dt><dd>${escHtml(sp.set_name || '(unnamed)')}</dd>
        <dt>Slots</dt><dd>${escHtml(String(local.matrix.length || Object.keys(local.seedById).length))}</dd>
        <dt>Requests placed</dt><dd>${placed}</dd>
        <dt>Model</dt><dd>${escHtml(local.modelId || '?')}</dd>
      </dl>
      ${local.themeSummary ? `<details class="wiz-skel-theme-preview"><summary>Theme excerpt</summary><div class="wiz-skel-theme-text">${escHtml(local.themeSummary)}</div></details>` : ''}
    `;
    const btn = slot.querySelector('[data-role="skel-refresh"]');
    if (btn) btn.onclick = () => onRefresh();
  }

  // ----------------------------------------------------------------------
  // Before/after grid
  // ----------------------------------------------------------------------

  function paintGrid(root, state) {
    const slot = root.querySelector('[data-role="skel-grid"]');
    if (!slot) return;
    if (!local.hasMatrix) {
      const generating = local.constraintsStatus === 'running' || local.locked;
      slot.innerHTML = `
        <div class="wiz-skel-empty">
          ${generating
            ? 'Deriving the themed matrix…'
            : 'No themed matrix yet. Click "Derive matrix" above, or advance from Skeleton.'}
        </div>`;
      return;
    }
    const isPast = isPastTab(state);
    const ro = isPast ? 'disabled' : '';
    const rows = local.matrix.map(m => rowHtml(m, ro)).join('');
    slot.innerHTML = `
      <div class="wiz-skel-table" role="table">
        <div class="wiz-skel-head" role="row">
          <span>Slot</span><span>Seed</span><span>Themed (editable)</span>
        </div>
        ${rows}
      </div>`;
    if (!isPast) bindGrid(slot);
  }

  function rowHtml(m, ro) {
    const seed = local.seedById[m.slot_id];
    const reserved = (m.reserved_card || '').trim();
    return `
      <div class="wiz-skel-row${reserved ? ' wiz-skel-row--req' : ''}" data-slot-id="${escAttr(m.slot_id)}" role="row">
        <span class="wiz-skel-slotid">${escHtml(m.slot_id)}</span>
        <span class="wiz-skel-seed">${escHtml(seedDescriptor(seed))}</span>
        <span class="wiz-skel-themed">
          ${reserved ? `<span class="wiz-skel-reqbadge" title="Requested card placed here">★ ${escHtml(reserved)}</span>` : ''}
          <textarea class="wiz-skel-blob" data-role="blob" rows="2" placeholder="Themed tags for this slot…" ${ro}>${escHtml(m.blob || '')}</textarea>
        </span>
      </div>`;
  }

  function seedDescriptor(seed) {
    if (!seed) return '(no seed)';
    const parts = [
      COLOR_FULL[seed.color] || seed.color || '?',
      seed.rarity || '?',
      seed.card_type || '?',
      `CMC${seed.cmc_target != null ? seed.cmc_target : '?'}`,
      seed.mechanic_tag || '',
    ].filter(Boolean);
    let d = parts.join(' · ');
    if (seed.signpost_for) d += ` · signpost:${seed.signpost_for}`;
    return d;
  }

  function bindGrid(slot) {
    slot.querySelectorAll('.wiz-skel-row').forEach(row => {
      const sid = row.dataset.slotId;
      const ta = row.querySelector('[data-role="blob"]');
      if (ta) ta.addEventListener('input', () => updateBlob(sid, ta.value));
    });
  }

  function updateBlob(slotId, value) {
    const i = local.matrix.findIndex(m => m.slot_id === slotId);
    if (i >= 0) local.matrix[i] = Object.assign({}, local.matrix[i], { blob: value });
  }

  function applyMatrix(list) {
    if (!Array.isArray(list)) return;
    local.matrix = list;
    local.hasMatrix = list.length > 0;
  }

  // ----------------------------------------------------------------------
  // Refresh (full re-derive)
  // ----------------------------------------------------------------------

  async function onRefresh() {
    if (local.locked) return;
    if (local.hasMatrix
        && !confirm('Re-derive the whole matrix? Your inline edits will be replaced.')) {
      return;
    }
    setLocked(true);
    if (W.showBusy) W.showBusy(local.hasMatrix ? 'Re-deriving themed matrix…' : 'Deriving themed matrix…');
    const root = bodyRoot();
    paintGrid(root, W.getState());
    try {
      const resp = await W.postJSON('/api/wizard/constraints/refresh', {});
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) return reportError(resp, data, 'Re-derive failed');
      applyMatrix(data.matrix);
      if (data.model_id) local.modelId = data.model_id;
      paintSummary(root, W.getState());
      paintGrid(root, W.getState());
      paintFooter(getFooter(root), W.getState());
      W.toast(local.hasMatrix ? 'Matrix re-derived.' : 'Matrix derived.', 'success');
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    } finally {
      if (W.clearBusy) W.clearBusy();
      setLocked(false);
    }
  }

  function reportError(resp, data, fallback) {
    if (resp.status === 409 && data.running_action) {
      W.toast(`${data.running_action} is in progress — try again when it finishes.`, 'error');
    } else {
      W.toast(data.error || `${fallback} (${resp.status})`, 'error');
    }
  }

  // ----------------------------------------------------------------------
  // Footer: Save & Continue (latest tab + constraints paused_for_review)
  // ----------------------------------------------------------------------

  function paintFooter(footer, state) {
    if (!footer) return;
    const isLatest = !state || state.latestTabId === STAGE_ID;
    const status = local.constraintsStatus;
    const next = W.nextStageEntryAfter(CONSTRAINTS_ID);
    const nextName = next ? next.name : 'the next stage';

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Editing a past skeleton is destructive — use the Edit button above.</span>`;
    } else if (status === 'completed') {
      html = `<span class="wiz-footer-note">Matrix saved. Engine is on ${escHtml(nextName)} — switch tabs to follow.</span>`;
    } else if (status === 'running') {
      html = `<span class="wiz-footer-note">Deriving the themed matrix…</span>`;
    } else if (status !== 'paused_for_review') {
      html = `<span class="wiz-footer-note">The constraint pass runs automatically. Tick "Stop after this step" above to review the matrix here before continuing.</span>`;
    } else {
      const ok = local.hasMatrix && local.matrix.every(m => (m.blob || '').trim());
      html = `
        <button type="button" class="wiz-btn-primary" data-role="skel-save-advance" ${ok && !local.locked ? '' : 'disabled'}>
          Save &amp; Continue: ${escHtml(nextName)}
        </button>
        <span class="wiz-footer-note">${local.matrix.length} slots themed.</span>`;
    }
    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
    }
    const btn = footer.querySelector('[data-role="skel-save-advance"]');
    if (btn) btn.onclick = onSaveAndAdvance;
  }

  async function onSaveAndAdvance() {
    if (local.locked) return;
    if (!local.matrix.length || !local.matrix.every(m => (m.blob || '').trim())) {
      W.toast('Every slot needs a themed blob before continuing.', 'error');
      return;
    }
    setLocked(true);
    const root = bodyRoot();
    const footer = getFooter(root);
    const btn = footer && footer.querySelector('[data-role="skel-save-advance"]');
    const original = btn ? btn.textContent : '';
    if (btn) btn.textContent = 'Saving…';
    try {
      const saveResp = await W.postJSON('/api/wizard/constraints/save', { slots: local.matrix });
      const saveData = await saveResp.json().catch(() => ({}));
      if (!saveResp.ok) {
        W.toast(saveData.error || `Save failed (${saveResp.status})`, 'error');
        if (btn) btn.textContent = original;
        return;
      }
      if (btn) btn.textContent = 'Starting…';
      const advResp = await W.postJSON('/api/wizard/advance', {});
      const advData = await advResp.json().catch(() => ({}));
      if (!advResp.ok) {
        W.toast(advData.error || `Advance failed (${advResp.status})`, 'error');
        if (btn) btn.textContent = original;
        return;
      }
      window.location.assign(advData.navigate_to || saveData.navigate_to || '/pipeline');
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
      if (btn) btn.textContent = original;
    } finally {
      setLocked(false);
    }
  }

  // ----------------------------------------------------------------------
  // Form lock (§3)
  // ----------------------------------------------------------------------

  function setLocked(locked) {
    local.locked = !!locked;
    const root = bodyRoot();
    if (!root) return;
    root.classList.toggle('wiz-skel-locked', !!locked);
    root.querySelectorAll('.wiz-skel-blob, [data-role="skel-refresh"]').forEach(el => {
      el.disabled = !!locked;
    });
    const footerBtn = root.querySelector('[data-role="skel-save-advance"]');
    if (footerBtn) footerBtn.disabled = !!locked;
  }

  // ----------------------------------------------------------------------
  // Helpers
  // ----------------------------------------------------------------------

  function bodyRoot() {
    return document.querySelector(`.wiz-tab-body[data-tab-id="${STAGE_ID}"]`);
  }

  function getFooter(root) {
    return root && root.querySelector('[data-role="footer"]');
  }

  function isPastTab(state) {
    return !!state && state.latestTabId !== STAGE_ID;
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
})();
