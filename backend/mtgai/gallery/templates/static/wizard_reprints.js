/**
 * Wizard Reprints tab — a responsive grid of reprint selection tiles on the
 * standard stage shell.
 *
 * Stage ID: ``reprints``  (review_eligible: True)
 *
 * Data source: ``<asset>/reprint_selection.json`` — a ``ReprintSelection``
 * object whose ``selections`` list contains ``{ candidate, slot, reason }``
 * triples.
 *
 * Conventions honoured:
 *   §1  One primary footer button when latest + paused_for_review.
 *   §3  Form lock during AI gen (no editable fields, but lock disables
 *       the advance button and the refresh placeholder).
 *   §6  Past-tab edit cascade routes through wizard_stage.js / W.editFlow.
 *   §8  Status pill flows from stage state.
 *   §9  "Stop after this step" — handled by wizard_stage.js.
 *   §13 Section-level Refresh-AI button, always rendered on the latest tab.
 *
 * The grid itself is read-only (selections are LLM-chosen), but the tab exposes
 * the **per-rarity reprint knobs** (``GET/POST /api/wizard/reprints/knobs``): one
 * target per rarity, each auto (lean rate × the set's estimated rarity count,
 * with a proportional jitter) or pinned to an exact number. The resolved mix is
 * told to the select pass as soft guidance. The Refresh button
 * (``POST /api/wizard/reprints/refresh``) persists the knobs and re-runs selection
 * under the AI lock at a non-zero temperature so a manual re-roll surfaces
 * alternative picks.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'reprints';

  // ── Scoped styles (injected once) ────────────────────────────────────────
  (function injectStyles() {
    if (document.getElementById('wiz-reprints-styles')) return;
    const s = document.createElement('style');
    s.id = 'wiz-reprints-styles';
    s.textContent = `
      /* Summary bar */
      .wiz-reprints-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem 1.5rem;
        margin-bottom: 1rem;
        font-size: 0.82rem;
        color: #888;
      }
      .wiz-reprints-meta strong { color: #ddd; }

      /* Grid + tile chrome + rarity pill are shared (.wiz-tile* / .wiz-rarity*
         in wizard.css). Only the reprint-specific tile content lives here. */
      .wiz-reprints-name {
        font-weight: 600;
        font-size: 0.9rem;
        color: #e0e0e0;
      }
      .wiz-reprints-cost {
        font-size: 0.78rem;
        color: #aaa;
        font-family: monospace;
      }
      .wiz-reprints-type {
        font-size: 0.73rem;
        color: #888;
        font-style: italic;
      }
      .wiz-reprints-oracle {
        font-size: 0.76rem;
        color: #ccc;
        line-height: 1.45;
        white-space: pre-line;
      }

      .wiz-reprints-slot-row {
        display: flex;
        align-items: flex-start;
        gap: 0.4rem;
        margin-top: 0.25rem;
        padding-top: 0.35rem;
        border-top: 1px solid #1f2540;
        font-size: 0.73rem;
      }
      .wiz-reprints-slot-label {
        color: #666;
        white-space: nowrap;
        flex-shrink: 0;
      }
      .wiz-reprints-slot-id {
        font-family: monospace;
        color: #4a9eff;
        white-space: nowrap;
      }
      .wiz-reprints-replaces {
        font-size: 0.72rem;
        color: #8a7a55;
        line-height: 1.4;
        margin-top: 0.3rem;
        font-style: italic;
      }
      .wiz-reprints-replaces .wiz-reprints-slot-label {
        color: #6b5e3f;
        font-style: normal;
      }
      .wiz-reprints-reason {
        color: #999;
        line-height: 1.35;
        font-size: 0.73rem;
        margin-top: 0.3rem;
      }

      /* Loading / empty / error */
      .wiz-reprints-loading {
        color: #666;
        font-style: italic;
        padding: 1.5rem 0;
      }

      /* Locked-tile dim is shared (.wiz-tile-locked .wiz-tile in wizard.css). */

      /* Knob panel */
      .wiz-reprints-knobs-panel {
        background: #0c1322;
        border: 1px solid #1f2540;
        border-radius: 8px;
        padding: 0.6rem 0.85rem;
        margin-bottom: 1rem;
      }
      .wiz-reprints-knobs-panel > summary {
        cursor: pointer;
        font-weight: 600;
        font-size: 0.85rem;
        color: #cdd6f4;
        list-style: revert;
      }
      .wiz-reprints-knobs-panel .wiz-reprints-knobs-help {
        font-size: 0.76rem;
        color: #888;
        margin: 0.4rem 0 0.6rem;
        line-height: 1.45;
      }
      .wiz-reprints-knob-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 0.5rem 0.9rem;
      }
      .wiz-reprints-knob {
        display: flex;
        align-items: center;
        gap: 0.4rem;
        font-size: 0.78rem;
      }
      .wiz-reprints-knob > label { color: #bbb; width: 4.7rem; flex-shrink: 0; }
      .wiz-reprints-knob input,
      .wiz-reprints-knob-jitter input {
        width: 4.5rem;
        background: #0f1729;
        border: 1px solid #2a3252;
        border-radius: 4px;
        color: #e0e0e0;
        padding: 2px 5px;
        font-size: 0.8rem;
      }
      .wiz-reprints-knob input:disabled { opacity: 0.5; }
      .wiz-reprints-knob-hint { color: #666; font-size: 0.7rem; }
      .wiz-reprints-knob-jitter {
        display: flex;
        align-items: center;
        gap: 0.4rem;
        font-size: 0.78rem;
        margin-top: 0.6rem;
      }
      .wiz-reprints-knob-jitter > label { color: #bbb; width: 4.7rem; flex-shrink: 0; }
      .wiz-reprints-knob-preview {
        font-size: 0.78rem;
        color: #aaa;
        margin-top: 0.6rem;
        padding-top: 0.5rem;
        border-top: 1px solid #1f2540;
      }
      .wiz-reprints-knob-preview strong { color: #ddd; }
      .wiz-reprints-knob-pending { color: #e0b050; }
    `;
    document.head.appendChild(s);
  })();

  // ── Module state ──────────────────────────────────────────────────────────
  const RARITIES = ['common', 'uncommon', 'rare', 'mythic'];

  const local = {
    initialized: false,
    selections: [],     // SelectionPair[] from reprint_selection.json
    hasContent: false,
    poolSize: null,     // int, from server (may be null)
    eligibleSlots: null,
    targetCount: null,  // target_reprint_count the LLM was asked for
    knobs: null,        // {common,uncommon,rare,mythic,jitter_pct} (null rarity = auto)
    provenance: {},     // {rarity: 'auto'|'user'}
    previewTargets: {}, // un-jittered per-rarity resolution of the current knobs
    knobsDirty: false,  // knob edits saved but not yet applied via Refresh
    state: null,        // last wizard state (handlers run outside render's closure)
    stageStatus: 'pending',
    locked: false,
    bootstrapping: false,
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ── Top-level render (called by wizard_stage.js on mount + every SSE tick) ─

  function render({ root, state, stage, content, footer }) {
    local.state = state;
    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      bootstrap(root, state).catch(err => {
        W.toast('Failed to load reprints state: ' + err.message, 'error');
        // Hard fetch error (network / non-404): paint the empty UI so the tab
        // doesn't sit stuck on the "Loading…" placeholder (mirrors card_gen).
        paintSummary(root, state);
        paintKnobs(root, state);
        paintGrid(root, state);
        paintFooter(getFooter(root), state);
      });
      paintFooter(footer, state);
      return;
    }

    // Re-render path: keep footer reactive; don't repaint the grid.
    const prevStatus = local.stageStatus;
    if (stage) local.stageStatus = stage.status;

    const justFinished =
      stage
      && prevStatus !== local.stageStatus
      && local.stageStatus !== 'pending'
      && local.stageStatus !== 'running'
      && !local.hasContent
      && !local.bootstrapping;

    if (justFinished) {
      local.bootstrapping = true;
      bootstrap(root, state)
        .catch(err => W.toast('Failed to refresh reprints state: ' + err.message, 'error'))
        .finally(() => { local.bootstrapping = false; });
      return;
    }

    paintFooter(footer, state);
    setLocked(local.locked);
  }

  function mountShellHtml() {
    return `
      <div data-role="reprints-summary">
        <div class="wiz-reprints-loading">Loading reprint selections…</div>
      </div>
      <div data-role="reprints-knobs"></div>
      <div data-role="reprints-grid"></div>
    `;
  }

  // ── Bootstrap from server ─────────────────────────────────────────────────

  async function bootstrap(root, state) {
    // GET /api/wizard/reprints/state reads <asset>/reprint_selection.json and
    // recomputes pool/slot counts:
    //   { selections: SelectionPair[], has_content, pool_size, eligible_slots,
    //     target_count, stage_status }
    // null = 404 (route missing — graceful empty); other non-OK / network
    // errors throw to the render .catch.
    const data = await W.fetchStageState(STAGE_ID);

    if (data) {
      local.selections = Array.isArray(data.selections) ? data.selections : [];
      local.hasContent = !!data.has_content || local.selections.length > 0;
      local.poolSize = data.pool_size != null ? data.pool_size : null;
      local.eligibleSlots = data.eligible_slots != null ? data.eligible_slots : null;
      local.targetCount = data.target_count != null ? data.target_count : null;
      local.knobs = data.knobs || local.knobs;
      local.provenance = data.provenance || {};
      local.previewTargets = data.preview_targets || {};
      if (data.stage_status) local.stageStatus = data.stage_status;
    }

    local.state = state;
    paintSummary(root, state);
    paintKnobs(root, state);
    paintGrid(root, state);
    paintFooter(getFooter(root), state);
  }

  // ── Summary / section header (§13) ───────────────────────────────────────

  function paintSummary(root, state) {
    const slot = root.querySelector('[data-role="reprints-summary"]');
    if (!slot) return;
    const isPast = isPastTab(state);
    const refreshLabel = local.hasContent ? 'Refresh AI…' : 'Generate';
    const refreshTitle = local.hasContent
      ? 'Re-run reprint selection (all slots re-evaluated).'
      : 'Run reprint selection now.';

    const metaParts = [];
    if (local.poolSize != null) metaParts.push(`Pool: <strong>${escHtml(String(local.poolSize))}</strong>`);
    if (local.eligibleSlots != null) metaParts.push(`Eligible slots: <strong>${escHtml(String(local.eligibleSlots))}</strong>`);
    if (local.targetCount != null) metaParts.push(`Target: <strong>${escHtml(String(local.targetCount))}</strong>`);
    if (local.hasContent) metaParts.push(`Picked: <strong>${escHtml(String(local.selections.length))}</strong>`);

    slot.innerHTML = `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">Reprint selections</h3>
        <button type="button" class="wiz-btn-secondary wiz-refresh-btn"
                data-role="reprints-refresh-all"
                title="${escAttr(isPast ? 'Use Edit above to revise past reprint selections.' : refreshTitle)}"
                ${isPast ? 'disabled' : ''}>${escHtml(refreshLabel)}</button>
      </div>
      <p style="font-size:0.8rem;color:#888;margin:0.3rem 0 0.6rem">
        LLM-selected reprints that fill setting-agnostic skeleton slots — vanilla,
        french-vanilla, and evergreen roles whose flavour survives transplant.
      </p>
      ${metaParts.length ? `<div class="wiz-reprints-meta">${metaParts.join(' &nbsp;·&nbsp; ')}</div>` : ''}
    `;

    const btn = slot.querySelector('[data-role="reprints-refresh-all"]');
    if (btn) btn.onclick = () => onRefreshAll();
  }

  // ── Grid ──────────────────────────────────────────────────────────────────

  function paintGrid(root, state) {
    const slot = root.querySelector('[data-role="reprints-grid"]');
    if (!slot) return;

    if (!local.hasContent) {
      slot.innerHTML = W.emptyStatePanel({
        generating: aiBusy(),
        generatingMsg: 'Selecting reprints from the curated pool…',
        emptyMsg: 'No reprints selected yet — runs after Skeleton.',
      });
      return;
    }

    slot.innerHTML = `<div class="wiz-tile-grid">${local.selections.map(sel => reprintTileHtml(sel)).join('')}</div>`;
  }

  function reprintTileHtml(sel) {
    const c = sel.candidate || {};
    const s = sel.slot || {};

    // Clip oracle text to ~200 chars to keep tiles manageable.
    const oracle = c.oracle_text || '';
    const oracleClipped = oracle.length > 220 ? oracle.slice(0, 217) + '…' : oracle;

    return `
      <article class="wiz-tile">
        <div class="wiz-tile-header">
          <span class="wiz-reprints-name">${escHtml(c.name || '(unnamed)')}</span>
          ${c.mana_cost ? `<span class="wiz-reprints-cost">${escHtml(c.mana_cost)}</span>` : ''}
          ${W.rarityPill(c.rarity)}
        </div>
        ${c.type_line ? `<div class="wiz-reprints-type">${escHtml(c.type_line)}</div>` : ''}
        ${oracleClipped ? `<div class="wiz-reprints-oracle">${escHtml(oracleClipped)}</div>` : ''}
        <div class="wiz-reprints-slot-row">
          <span class="wiz-reprints-slot-label">Slot:</span>
          <span class="wiz-reprints-slot-id">${escHtml(s.slot_id || '?')}</span>
        </div>
        ${s.descriptor ? `<div class="wiz-reprints-replaces"><span class="wiz-reprints-slot-label">Replaces:</span> ${escHtml(s.descriptor)}</div>` : ''}
        ${sel.reason ? `<div class="wiz-reprints-reason">${escHtml(sel.reason)}</div>` : ''}
      </article>
    `;
  }

  // ── Knob panel: per-rarity reprint targets (§ skeleton-knobs analog) ─────

  function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

  function paintKnobs(root, state) {
    const slot = root.querySelector('[data-role="reprints-knobs"]');
    if (!slot) return;
    if (!local.knobs) { slot.innerHTML = ''; return; }
    const disabled = isPastTab(state) || local.locked;

    const rows = RARITIES.map(r => {
      const v = local.knobs[r];
      const prov = local.provenance[r] || 'auto';
      const previewN = local.previewTargets[r] != null ? local.previewTargets[r] : 0;
      return `
        <div class="wiz-reprints-knob">
          <label>${escHtml(cap(r))}</label>
          <input type="number" min="0" step="1" data-knob="${r}"
                 value="${v != null ? escAttr(String(v)) : ''}"
                 placeholder="auto (${escAttr(String(previewN))})" ${disabled ? 'disabled' : ''}>
          ${W.provenanceBadge(prov)}
        </div>`;
    }).join('');

    const total = RARITIES.reduce((a, r) => a + (local.previewTargets[r] || 0), 0);
    const jitter = local.knobs.jitter_pct != null ? local.knobs.jitter_pct : 0.25;
    const pending = local.knobsDirty
      ? ` <span class="wiz-reprints-knob-pending">— knob edits pending; Refresh to apply.</span>`
      : '';

    slot.innerHTML = `
      <details class="wiz-reprints-knobs-panel" open>
        <summary>Reprint targets</summary>
        <p class="wiz-reprints-knobs-help">
          How many reprints to pull per rarity. Leave blank for <em>auto</em>
          (lean reprint rates × the set's estimated rarity counts); auto rarities
          get a proportional random nudge each run (Jitter). Pinned numbers are
          exact. The mix is told to the model as soft guidance — a near miss is
          fine — and it places the picks on the plainest slots.
        </p>
        <div class="wiz-reprints-knob-grid">${rows}</div>
        <div class="wiz-reprints-knob-jitter">
          <label>Jitter</label>
          <input type="number" min="0" max="1" step="0.05" data-knob="jitter_pct"
                 value="${escAttr(String(jitter))}" ${disabled ? 'disabled' : ''}>
          <span class="wiz-reprints-knob-hint">proportional ± on the auto total (0 = off)</span>
        </div>
        <div class="wiz-reprints-knob-preview">Reprints this run ≈ <strong>${escHtml(String(total))}</strong>${pending}</div>
      </details>
    `;

    if (!disabled) {
      slot.querySelectorAll('input[data-knob]').forEach(inp => {
        inp.onchange = () => onKnobChange(root, state);
      });
    }
  }

  function readKnobInputs(root) {
    const out = {};
    RARITIES.forEach(r => {
      const inp = root.querySelector(`input[data-knob="${r}"]`);
      out[r] = (inp && inp.value !== '') ? Number(inp.value) : null;
    });
    const j = root.querySelector('input[data-knob="jitter_pct"]');
    out.jitter_pct = j && j.value !== '' ? Number(j.value) : 0.25;
    return out;
  }

  async function onKnobChange(root, state) {
    if (local.locked) return;
    const knobs = readKnobInputs(root);
    try {
      const resp = await W.postJSON('/api/wizard/reprints/knobs', { knobs });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        W.toast(data.error || `Save failed (${resp.status})`, 'error');
        return;
      }
      local.knobs = data.knobs || local.knobs;
      local.provenance = data.provenance || local.provenance;
      if (data.preview_targets) local.previewTargets = data.preview_targets;
      local.knobsDirty = true;
      paintKnobs(root, state);
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    }
  }

  // ── Refresh: re-run selection with the current knobs ─────────────────────

  async function onRefreshAll() {
    if (local.locked) return;
    const root = bodyRoot();
    const state = local.state;
    const knobs = root ? readKnobInputs(root) : null;
    await W.runAiAction({
      isLocked: () => local.locked,
      setLocked,
      confirm: () => (local.hasContent ? 'Re-run reprint selection? Current picks will be replaced.' : ''),
      busyLabel: 'Selecting reprints…',
      run: async ({ post }) => {
        const data = await post('/api/wizard/reprints/refresh', knobs ? { knobs } : {}, 'Refresh failed');
        if (!data) return;
        local.selections = Array.isArray(data.selections) ? data.selections : [];
        local.hasContent = !!data.has_content || local.selections.length > 0;
        local.targetCount = data.target_count != null ? data.target_count : local.targetCount;
        if (data.eligible_slots != null) local.eligibleSlots = data.eligible_slots;
        if (data.knobs) local.knobs = data.knobs;
        if (data.provenance) local.provenance = data.provenance;
        if (data.preview_targets) local.previewTargets = data.preview_targets;
        local.knobsDirty = false;
        if (root) {
          paintSummary(root, state);
          paintKnobs(root, state);
          paintGrid(root, state);
          paintFooter(getFooter(root), state);
        }
      },
    });
  }

  // ── Footer: advance button when paused_for_review (§1) ───────────────────

  function paintFooter(footer, state) {
    if (!footer) return;
    const isLatest = !state || state.latestTabId === STAGE_ID;
    const isPaused = local.stageStatus === 'paused_for_review';
    const isCompleted = local.stageStatus === 'completed';
    const next = W.nextStageEntryAfter(STAGE_ID);
    const nextName = next ? next.name : 'the next stage';

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Editing past reprint selections is destructive — use the Edit button above.</span>`;
    } else if (isCompleted) {
      html = `<span class="wiz-footer-note">Reprints saved. Engine is on ${escHtml(nextName)} — switch tabs to follow.</span>`;
    } else if (!isPaused) {
      html = `<span class="wiz-footer-note">This stage runs automatically. Tick "Stop after this step" above to review here before continuing.</span>`;
    } else {
      html = `
        <button type="button" class="wiz-btn-primary" data-role="reprints-advance"
                ${local.locked ? 'disabled' : ''}>
          Next step: ${escHtml(nextName)}
        </button>
        <span class="wiz-footer-note">${escHtml(String(local.selections.length))} reprint${local.selections.length === 1 ? '' : 's'} selected.</span>
      `;
    }

    W.paintFooter(footer, html, { role: 'reprints-advance', onClick: onAdvance });
  }

  function onAdvance() {
    return W.advanceStage({
      stageId: STAGE_ID,
      isLocked: () => local.locked,
      setLocked,
      btnRole: 'reprints-advance',
    });
  }

  // ── Form lock (§3) ────────────────────────────────────────────────────────

  // AI is "active" on this tab when this tab kicked off an op (local.locked) or
  // the engine is running the reprints stage (stageStatus). The composite is
  // the standardized lock truth source across stage tabs (§3).
  function aiBusy() {
    return local.locked || local.stageStatus === 'running';
  }

  function setLocked(locked) {
    local.locked = !!locked;
    W.setTabLocked(bodyRoot(), aiBusy(), {
      lockClass: 'wiz-tile-locked',
      selectors: ['[data-role="reprints-refresh-all"]', 'input[data-knob]'],
      footerSelector: '[data-role="reprints-advance"]',
    });
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  const bodyRoot = () => W.tabRoot(STAGE_ID);

  const getFooter = (root) => W.tabFooter(root);

  const isPastTab = (state) => W.isPastTab(STAGE_ID, state);

  const escHtml = W.escHtml;

  const escAttr = W.escAttr;

})();
