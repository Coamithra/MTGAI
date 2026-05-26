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
 * The grid is read-only (selections are LLM-chosen; per-card editing is
 * out of scope for this precreation pass).  The Refresh-AI button and
 * per-card "Re-run" buttons are placeholders that toast a TODO until the
 * backend endpoint is added.
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

      /* Grid */
      .wiz-reprints-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
        gap: 0.75rem;
        margin-top: 0.75rem;
      }

      /* Tile */
      .wiz-reprints-tile {
        background: #0f1729;
        border: 1px solid #1f2540;
        border-radius: 8px;
        padding: 0.75rem;
        display: flex;
        flex-direction: column;
        gap: 0.35rem;
        transition: border-color 0.15s;
      }
      .wiz-reprints-tile:hover { border-color: #4a9eff55; }

      .wiz-reprints-tile-header {
        display: flex;
        align-items: baseline;
        gap: 0.5rem;
        flex-wrap: wrap;
      }
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
      .wiz-reprints-rarity {
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        padding: 1px 5px;
        border-radius: 3px;
        margin-left: auto;
        flex-shrink: 0;
      }
      .wiz-reprints-rarity-c { background: #2a2a2a; color: #aaa; }
      .wiz-reprints-rarity-u { background: #c0d0e022; color: #b0c8d8; }
      .wiz-reprints-rarity-r { background: #ffd70022; color: #ffd700; }
      .wiz-reprints-rarity-m { background: #ff8c0022; color: #ff8c00; }

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
      .wiz-reprints-reason {
        color: #999;
        line-height: 1.35;
      }

      /* Loading / empty / error */
      .wiz-reprints-loading {
        color: #666;
        font-style: italic;
        padding: 1.5rem 0;
      }

      /* Locked: faint dim */
      .wiz-reprints-locked .wiz-reprints-tile {
        opacity: 0.6;
        pointer-events: none;
      }
    `;
    document.head.appendChild(s);
  })();

  // ── Module state ──────────────────────────────────────────────────────────
  const local = {
    initialized: false,
    selections: [],     // SelectionPair[] from reprint_selection.json
    hasContent: false,
    poolSize: null,     // int, from server (may be null)
    eligibleSlots: null,
    stageStatus: 'pending',
    locked: false,
    bootstrapping: false,
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ── Top-level render (called by wizard_stage.js on mount + every SSE tick) ─

  function render({ root, state, stage, content, footer }) {
    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      bootstrap(root, state).catch(err => {
        W.toast('Failed to load reprints state: ' + err.message, 'error');
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
      <div data-role="reprints-grid"></div>
    `;
  }

  // ── Bootstrap from server ─────────────────────────────────────────────────

  async function bootstrap(root, state) {
    // TODO: implement GET /api/wizard/reprints/state that returns
    //   { selections: SelectionPair[], has_content: bool,
    //     pool_size: int, eligible_slots: int, stage_status: str }
    //   reading from <asset>/reprint_selection.json.
    let data = null;
    try {
      const resp = await fetch('/api/wizard/reprints/state');
      if (resp.ok) {
        data = await resp.json();
      } else if (resp.status === 404) {
        data = null; // endpoint not yet implemented — graceful empty
      } else {
        const j = await resp.json().catch(() => ({}));
        throw new Error(j.error || `HTTP ${resp.status}`);
      }
    } catch (err) {
      if (err.message && err.message.startsWith('HTTP ')) throw err;
      // Network error or 404 stub — degrade gracefully to empty state.
      data = null;
    }

    if (data) {
      local.selections = Array.isArray(data.selections) ? data.selections : [];
      local.hasContent = !!data.has_content || local.selections.length > 0;
      local.poolSize = data.pool_size != null ? data.pool_size : null;
      local.eligibleSlots = data.eligible_slots != null ? data.eligible_slots : null;
      if (data.stage_status) local.stageStatus = data.stage_status;
    }

    paintSummary(root, state);
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
      const generating = local.stageStatus === 'running' || local.locked;
      slot.innerHTML = `
        <div class="wiz-stage-empty">
          ${generating
            ? 'Selecting reprints from the curated pool…'
            : 'No reprints selected yet — runs after Skeleton.'}
        </div>
      `;
      return;
    }

    slot.innerHTML = `<div class="wiz-reprints-grid">${local.selections.map(sel => reprintTileHtml(sel)).join('')}</div>`;
  }

  function reprintTileHtml(sel) {
    const c = sel.candidate || {};
    const s = sel.slot || {};
    const rarityKey = (c.rarity || '').toLowerCase().charAt(0) || 'c';
    const rarityClass = `wiz-reprints-rarity-${escAttr(rarityKey)}`;
    const rarityLabel = escHtml(c.rarity || '?');

    // Clip oracle text to ~200 chars to keep tiles manageable.
    const oracle = c.oracle_text || '';
    const oracleClipped = oracle.length > 220 ? oracle.slice(0, 217) + '…' : oracle;

    return `
      <article class="wiz-reprints-tile">
        <div class="wiz-reprints-tile-header">
          <span class="wiz-reprints-name">${escHtml(c.name || '(unnamed)')}</span>
          ${c.mana_cost ? `<span class="wiz-reprints-cost">${escHtml(c.mana_cost)}</span>` : ''}
          <span class="wiz-reprints-rarity ${rarityClass}">${rarityLabel}</span>
        </div>
        ${c.type_line ? `<div class="wiz-reprints-type">${escHtml(c.type_line)}</div>` : ''}
        ${oracleClipped ? `<div class="wiz-reprints-oracle">${escHtml(oracleClipped)}</div>` : ''}
        <div class="wiz-reprints-slot-row">
          <span class="wiz-reprints-slot-label">Slot:</span>
          <span class="wiz-reprints-slot-id">${escHtml(s.slot_id || '?')}</span>
          ${sel.reason ? `<span class="wiz-reprints-reason">${escHtml(sel.reason)}</span>` : ''}
        </div>
      </article>
    `;
  }

  // ── Refresh / generate placeholder ───────────────────────────────────────

  async function onRefreshAll() {
    if (local.locked) return;
    if (local.hasContent) {
      if (!confirm('Re-run reprint selection? All current picks will be replaced.')) return;
    }
    // TODO: POST /api/wizard/reprints/refresh triggers run_reprints re-execution.
    W.toast('Re-running reprint selection is not yet wired to the backend. Follow-up needed.', 'warn');
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

    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
    }
    const btn = footer.querySelector('[data-role="reprints-advance"]');
    if (btn) btn.onclick = () => onAdvance();
  }

  async function onAdvance() {
    if (local.locked) return;
    setLocked(true);
    const footer = getFooter(bodyRoot());
    const btn = footer && footer.querySelector('[data-role="reprints-advance"]');
    const orig = btn ? btn.textContent : '';
    if (btn) btn.textContent = 'Advancing…';
    try {
      const resp = await W.postJSON('/api/wizard/advance', {});
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        if (resp.status === 409 && data.running_action) {
          W.toast(`${data.running_action} is in progress — try again when it finishes.`, 'error');
        } else {
          W.toast(data.error || `Advance failed (${resp.status})`, 'error');
        }
        if (btn) btn.textContent = orig;
        return;
      }
      const next = W.nextStageEntryAfter(STAGE_ID);
      const nextHref = next ? `/pipeline/${next.id}` : '/pipeline';
      window.location.assign(data.navigate_to || nextHref);
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
      if (btn) btn.textContent = orig;
    } finally {
      setLocked(false);
    }
  }

  // ── Form lock (§3) ────────────────────────────────────────────────────────

  function setLocked(locked) {
    local.locked = !!locked;
    const root = bodyRoot();
    if (!root) return;
    root.classList.toggle('wiz-reprints-locked', !!locked);
    root.querySelectorAll('[data-role="reprints-refresh-all"]').forEach(el => { el.disabled = !!locked; });
    const footerBtn = getFooter(root);
    if (footerBtn) {
      const btn = footerBtn.querySelector('[data-role="reprints-advance"]');
      if (btn) btn.disabled = !!locked;
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

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
