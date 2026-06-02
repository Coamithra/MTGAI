/**
 * Wizard Reprints tab — a grid of reprint selection tiles on the standard stage
 * shell, editable on the latest tab.
 *
 * Stage ID: ``reprints``  (review_eligible: True)
 *
 * Data source: ``<asset>/reprint_selection.json`` — a ``ReprintSelection``
 * object whose ``selections`` list contains ``{ candidate, slot, reason, pinned }``
 * quadruples.
 *
 * The tab is a **hybrid** select+place surface (mirrors the archetypes tab's
 * preserve-on-refresh contract):
 *   - AI proposes the picks + placements (unpinned, "AI" badge).
 *   - The user can override per-pick on the latest tab: reassign a pick's slot,
 *     remove it, or add a fresh pick from the curated pool browser. Any manual
 *     touch **pins** the pick ("edited" badge).
 *   - "Refresh AI" keeps every pinned pick verbatim and re-rolls only the
 *     unpinned ones around them.
 *   - "Save & Continue" persists the working selections (no AI) via
 *     ``/api/wizard/reprints/save`` and advances, re-stamping the skeleton so
 *     card-gen skips the reprint slots.
 *
 * Conventions honoured:
 *   §1  One primary Save & Continue footer button when latest + paused_for_review.
 *   §3  Form lock during AI gen.
 *   §5  AI provenance badge + preserve-on-edit (pin = the preserve flag).
 *   §6  Past-tab edit cascade routes through wizard_stage.js / W.editFlow.
 *   §8  Status pill flows from stage state.
 *   §9  "Stop after this step" — handled by wizard_stage.js.
 *   §13 Section-level Refresh-AI button, always rendered on the latest tab.
 *
 * The per-rarity reprint knobs (``GET/POST /api/wizard/reprints/knobs``) stay on
 * the tab: one target per rarity, auto (lean rate × the set's estimated rarity
 * count, with jitter) or pinned. The resolved mix is told to the select pass as
 * soft guidance.
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
        align-items: center;
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
      .wiz-reprints-slot-select {
        flex: 1;
        min-width: 0;
        background: #0f1729;
        border: 1px solid #2a3252;
        border-radius: 4px;
        color: #cdd6f4;
        padding: 2px 4px;
        font-size: 0.72rem;
        font-family: monospace;
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

      /* Per-tile edit controls (latest tab) */
      .wiz-reprints-tile-actions {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.5rem;
        margin-top: 0.45rem;
        padding-top: 0.4rem;
        border-top: 1px solid #1f2540;
        font-size: 0.74rem;
      }
      .wiz-reprints-pin {
        display: flex;
        align-items: center;
        gap: 0.3rem;
        color: #bbb;
        cursor: pointer;
        user-select: none;
      }
      .wiz-reprints-remove {
        background: none;
        border: 1px solid #3a2330;
        color: #c66;
        border-radius: 4px;
        padding: 1px 7px;
        cursor: pointer;
        font-size: 0.8rem;
        line-height: 1.3;
      }
      .wiz-reprints-remove:hover { background: #2a1620; }

      /* Pool browser */
      .wiz-reprints-pool-panel {
        background: #0c1322;
        border: 1px solid #1f2540;
        border-radius: 8px;
        padding: 0.6rem 0.85rem;
        margin-bottom: 1rem;
      }
      .wiz-reprints-pool-panel > summary {
        cursor: pointer;
        font-weight: 600;
        font-size: 0.85rem;
        color: #cdd6f4;
        list-style: revert;
      }
      .wiz-reprints-pool-search {
        width: 100%;
        box-sizing: border-box;
        margin: 0.55rem 0;
        background: #0f1729;
        border: 1px solid #2a3252;
        border-radius: 4px;
        color: #e0e0e0;
        padding: 4px 8px;
        font-size: 0.82rem;
      }
      .wiz-reprints-pool-list {
        max-height: 340px;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
        gap: 0.3rem;
      }
      .wiz-reprints-pool-row {
        display: flex;
        align-items: flex-start;
        gap: 0.5rem;
        padding: 0.35rem 0.4rem;
        border: 1px solid #161d33;
        border-radius: 5px;
      }
      .wiz-reprints-pool-row.is-selected { border-color: #2f5d3a; background: #0e1a12; }
      .wiz-reprints-pool-row-main { flex: 1; min-width: 0; }
      .wiz-reprints-pool-row-head {
        display: flex;
        align-items: center;
        gap: 0.4rem;
        flex-wrap: wrap;
      }
      .wiz-reprints-pool-row-oracle {
        font-size: 0.72rem;
        color: #9aa;
        line-height: 1.35;
        margin-top: 0.15rem;
      }
      .wiz-reprints-pool-add {
        flex-shrink: 0;
        align-self: center;
        background: #15233a;
        border: 1px solid #2a3252;
        color: #cdd6f4;
        border-radius: 4px;
        padding: 3px 10px;
        cursor: pointer;
        font-size: 0.76rem;
      }
      .wiz-reprints-pool-add:hover { background: #1c3052; }
      .wiz-reprints-pool-add.is-selected { background: #1d3a26; border-color: #2f5d3a; color: #a9d8b6; }
      .wiz-reprints-pool-empty { color: #666; font-style: italic; padding: 0.5rem 0; font-size: 0.8rem; }

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
    selections: [],     // [{candidate, slot, reason, pinned}] working view
    hasContent: false,
    poolSize: null,     // int, from server (may be null)
    eligibleSlots: null,
    targetCount: null,  // target_reprint_count the LLM was asked for
    knobs: null,        // {common,uncommon,rare,mythic,jitter_pct} (null rarity = auto)
    provenance: {},     // {rarity: 'auto'|'user'}
    previewTargets: {}, // un-jittered per-rarity resolution of the current knobs
    knobsDirty: false,  // knob edits saved but not yet applied via Refresh
    pool: null,         // [candidate dict] from /pool (lazy)
    openSlots: [],      // [{slot_id, text}] from /pool (lazy)
    poolLoaded: false,
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
        rerender(root, state);
      });
      paintFooter(footer, state);
      return;
    }

    // Re-render path: keep footer reactive; don't repaint the grid (the user may
    // be mid-edit — reassigning a slot, typing in the pool search).
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
      <div data-role="reprints-pool"></div>
      <div data-role="reprints-knobs"></div>
      <div data-role="reprints-grid"></div>
    `;
  }

  // ── Bootstrap from server ─────────────────────────────────────────────────

  async function bootstrap(root, state) {
    // GET /api/wizard/reprints/state reads <asset>/reprint_selection.json and
    // recomputes pool/slot counts. null = 404 (graceful empty); other non-OK /
    // network errors throw to the render .catch.
    const data = await W.fetchStageState(STAGE_ID);

    if (data) {
      local.selections = normalizeSelections(data.selections);
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
    // The pool + open slots back both the per-tile slot dropdown and the pool
    // browser; load them once for an editable (latest, not-past) tab.
    if (isEditable(state)) {
      try { await ensurePool(); } catch (err) { W.toast('Failed to load reprint pool: ' + err.message, 'warn'); }
    }
    rerender(root, state);
  }

  function normalizeSelections(list) {
    if (!Array.isArray(list)) return [];
    return list.map(sel => ({
      candidate: sel.candidate || {},
      slot: sel.slot || { slot_id: '', descriptor: '' },
      reason: sel.reason || '',
      pinned: !!sel.pinned,
    }));
  }

  async function ensurePool() {
    if (local.poolLoaded) return;
    const resp = await fetch('/api/wizard/reprints/pool', { headers: { Accept: 'application/json' } });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    local.pool = Array.isArray(data.pool) ? data.pool : [];
    local.openSlots = Array.isArray(data.open_slots) ? data.open_slots : [];
    local.poolLoaded = true;
  }

  // Repaint every section that depends on the working selections.
  function rerender(root, state) {
    if (!root) return;
    paintSummary(root, state);
    paintPoolBrowser(root, state);
    paintKnobs(root, state);
    paintGrid(root, state);
    paintFooter(getFooter(root), state);
    setLocked(local.locked);
  }

  // ── Summary / section header (§13) ───────────────────────────────────────

  function paintSummary(root, state) {
    const slot = root.querySelector('[data-role="reprints-summary"]');
    if (!slot) return;
    const isPast = isPastTab(state);
    const refreshLabel = local.hasContent ? 'Refresh AI…' : 'Generate';
    const refreshTitle = local.hasContent
      ? 'Re-run AI selection. Pinned picks are kept; unpinned ones are re-rolled.'
      : 'Run reprint selection now.';

    const metaParts = [];
    if (local.poolSize != null) metaParts.push(`Pool: <strong>${escHtml(String(local.poolSize))}</strong>`);
    if (local.eligibleSlots != null) metaParts.push(`Eligible slots: <strong>${escHtml(String(local.eligibleSlots))}</strong>`);
    if (local.targetCount != null) metaParts.push(`Target: <strong>${escHtml(String(local.targetCount))}</strong>`);
    metaParts.push(`Picked: <strong>${escHtml(String(local.selections.length))}</strong>`);
    const pinnedCount = local.selections.filter(s => s.pinned).length;
    if (pinnedCount) metaParts.push(`Pinned: <strong>${escHtml(String(pinnedCount))}</strong>`);

    slot.innerHTML = `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">Reprint selections</h3>
        <button type="button" class="wiz-btn-secondary wiz-refresh-btn"
                data-role="reprints-refresh-all"
                title="${escAttr(isPast ? 'Use Edit above to revise past reprint selections.' : refreshTitle)}"
                ${isPast ? 'disabled' : ''}>${escHtml(refreshLabel)}</button>
      </div>
      <p style="font-size:0.8rem;color:#888;margin:0.3rem 0 0.6rem">
        Reprints that fill setting-agnostic skeleton slots. AI proposes; on this tab
        you can reassign a pick's slot, remove it, or add your own from the pool —
        any manual touch <em>pins</em> the pick so a Refresh keeps it.
      </p>
      ${metaParts.length ? `<div class="wiz-reprints-meta">${metaParts.join(' &nbsp;·&nbsp; ')}</div>` : ''}
    `;

    const btn = slot.querySelector('[data-role="reprints-refresh-all"]');
    if (btn) btn.onclick = () => onRefreshAll();
  }

  // ── Pool browser (manual select; latest tab only) ─────────────────────────

  function paintPoolBrowser(root, state) {
    const slot = root.querySelector('[data-role="reprints-pool"]');
    if (!slot) return;
    if (!isEditable(state) || !local.poolLoaded || !local.pool) {
      slot.innerHTML = '';
      return;
    }
    const rows = local.pool.map(c => poolRowHtml(c)).join('');
    slot.innerHTML = `
      <details class="wiz-reprints-pool-panel" data-role="reprints-pool-panel">
        <summary>Browse reprint pool (${escHtml(String(local.pool.length))} cards)</summary>
        <input type="text" class="wiz-reprints-pool-search" data-role="reprints-pool-search"
               placeholder="Search by name, type, or text…">
        <div class="wiz-reprints-pool-empty" data-role="reprints-pool-noresults" style="display:none">No cards match your search.</div>
        <div class="wiz-reprints-pool-list" data-role="reprints-pool-list">${rows}</div>
      </details>
    `;

    const search = slot.querySelector('[data-role="reprints-pool-search"]');
    if (search) search.addEventListener('input', () => filterPoolRows(root));
    slot.querySelectorAll('[data-role="reprints-pool-add"]').forEach(btn => {
      btn.onclick = () => onTogglePoolCard(btn.dataset.name);
    });
    refreshPoolButtons(root);
  }

  function poolRowHtml(c) {
    const oracle = (c.oracle_text || '').replace(/\n/g, ' / ');
    const oracleClipped = oracle.length > 140 ? oracle.slice(0, 137) + '…' : oracle;
    const haystack = `${c.name || ''} ${c.type_line || ''} ${c.oracle_text || ''} ${(c.role || '')}`.toLowerCase();
    return `
      <div class="wiz-reprints-pool-row" data-name="${escAttr(c.name || '')}" data-search="${escAttr(haystack)}">
        <div class="wiz-reprints-pool-row-main">
          <div class="wiz-reprints-pool-row-head">
            <span class="wiz-reprints-name">${escHtml(c.name || '(unnamed)')}</span>
            ${c.mana_cost ? `<span class="wiz-reprints-cost">${escHtml(c.mana_cost)}</span>` : ''}
            ${W.rarityPill(c.rarity)}
            ${c.type_line ? `<span class="wiz-reprints-type">${escHtml(c.type_line)}</span>` : ''}
          </div>
          ${oracleClipped ? `<div class="wiz-reprints-pool-row-oracle">${escHtml(oracleClipped)}</div>` : ''}
        </div>
        <button type="button" class="wiz-reprints-pool-add" data-role="reprints-pool-add"
                data-name="${escAttr(c.name || '')}">Add</button>
      </div>
    `;
  }

  function filterPoolRows(root) {
    const panel = root.querySelector('[data-role="reprints-pool"]');
    if (!panel) return;
    const q = (panel.querySelector('[data-role="reprints-pool-search"]')?.value || '').trim().toLowerCase();
    let shown = 0;
    panel.querySelectorAll('.wiz-reprints-pool-row').forEach(row => {
      const match = !q || (row.dataset.search || '').includes(q);
      row.style.display = match ? '' : 'none';
      if (match) shown++;
    });
    const none = panel.querySelector('[data-role="reprints-pool-noresults"]');
    if (none) none.style.display = shown ? 'none' : '';
  }

  // Reflect current selection membership onto every pool Add button (cheap, no
  // focus loss — buttons aren't text inputs).
  function refreshPoolButtons(root) {
    const panel = root.querySelector('[data-role="reprints-pool"]');
    if (!panel) return;
    const chosen = new Set(local.selections.map(s => (s.candidate.name || '').toLowerCase()));
    panel.querySelectorAll('[data-role="reprints-pool-add"]').forEach(btn => {
      const isSel = chosen.has((btn.dataset.name || '').toLowerCase());
      btn.textContent = isSel ? 'Added ✓' : 'Add';
      btn.classList.toggle('is-selected', isSel);
      btn.closest('.wiz-reprints-pool-row')?.classList.toggle('is-selected', isSel);
      btn.disabled = local.locked;
    });
  }

  function onTogglePoolCard(name) {
    if (local.locked) return;
    const lower = (name || '').toLowerCase();
    const existing = local.selections.findIndex(s => (s.candidate.name || '').toLowerCase() === lower);
    if (existing >= 0) {
      local.selections.splice(existing, 1);
      afterEdit();
      return;
    }
    const cand = (local.pool || []).find(c => (c.name || '').toLowerCase() === lower);
    if (!cand) { W.toast('Card not found in pool.', 'error'); return; }
    const free = firstFreeSlot();
    if (!free) {
      W.toast('No open slot left to place this reprint — remove one or free a slot.', 'warn');
      return;
    }
    local.selections.push({
      candidate: cand,
      slot: { slot_id: free.slot_id, descriptor: free.text || '' },
      reason: '',
      pinned: true,
    });
    afterEdit();
  }

  // ── Grid ──────────────────────────────────────────────────────────────────

  function paintGrid(root, state) {
    const slot = root.querySelector('[data-role="reprints-grid"]');
    if (!slot) return;

    if (!local.hasContent && !local.selections.length) {
      slot.innerHTML = W.emptyStatePanel({
        generating: aiBusy(),
        generatingMsg: 'Selecting reprints from the curated pool…',
        emptyMsg: 'No reprints selected yet — runs after Skeleton, or add your own from the pool above.',
      });
      return;
    }

    const editable = isEditable(state);
    slot.innerHTML = `<div class="wiz-tile-grid">${local.selections.map(sel => reprintTileHtml(sel, editable)).join('')}</div>`;
    if (editable) bindGrid(slot);
  }

  function reprintTileHtml(sel, editable) {
    const c = sel.candidate || {};
    const s = sel.slot || {};

    const oracle = c.oracle_text || '';
    const oracleClipped = oracle.length > 220 ? oracle.slice(0, 217) + '…' : oracle;
    const badge = W.provenanceBadge(sel.pinned ? 'user' : 'ai', { role: 'ai-badge' });

    const slotRow = editable
      ? `<div class="wiz-reprints-slot-row">
           <span class="wiz-reprints-slot-label">Slot:</span>
           <select class="wiz-reprints-slot-select" data-role="reprint-slot" data-name="${escAttr(c.name || '')}">
             ${slotOptionsHtml(sel)}
           </select>
         </div>`
      : `<div class="wiz-reprints-slot-row">
           <span class="wiz-reprints-slot-label">Slot:</span>
           <span class="wiz-reprints-slot-id">${escHtml(s.slot_id || '?')}</span>
         </div>`;

    const actions = editable
      ? `<div class="wiz-reprints-tile-actions">
           <label class="wiz-reprints-pin">
             <input type="checkbox" data-role="reprint-pin" data-name="${escAttr(c.name || '')}" ${sel.pinned ? 'checked' : ''}>
             Pin
           </label>
           <button type="button" class="wiz-reprints-remove" data-role="reprint-remove" data-name="${escAttr(c.name || '')}" title="Remove this reprint">Remove</button>
         </div>`
      : '';

    return `
      <article class="wiz-tile">
        <div class="wiz-tile-header">
          <span class="wiz-reprints-name">${escHtml(c.name || '(unnamed)')}</span>
          ${c.mana_cost ? `<span class="wiz-reprints-cost">${escHtml(c.mana_cost)}</span>` : ''}
          ${W.rarityPill(c.rarity)}
          ${badge}
        </div>
        ${c.type_line ? `<div class="wiz-reprints-type">${escHtml(c.type_line)}</div>` : ''}
        ${oracleClipped ? `<div class="wiz-reprints-oracle">${escHtml(oracleClipped)}</div>` : ''}
        ${slotRow}
        ${!editable && s.descriptor ? `<div class="wiz-reprints-replaces"><span class="wiz-reprints-slot-label">Replaces:</span> ${escHtml(s.descriptor)}</div>` : ''}
        ${sel.reason ? `<div class="wiz-reprints-reason">${escHtml(sel.reason)}</div>` : ''}
        ${actions}
      </article>
    `;
  }

  function slotOptionsHtml(sel) {
    const curId = sel.slot.slot_id || '';
    const used = usedSlotIds(sel.candidate.name);
    const opts = (local.openSlots || []).filter(o => !used.has(o.slot_id));
    if (curId && !opts.some(o => o.slot_id === curId)) {
      opts.unshift({ slot_id: curId, text: sel.slot.descriptor || '' });
    }
    return opts.map(o => {
      const label = `${o.slot_id}: ${(o.text || '').slice(0, 60)}`;
      return `<option value="${escAttr(o.slot_id)}" ${o.slot_id === curId ? 'selected' : ''}>${escHtml(label)}</option>`;
    }).join('');
  }

  function usedSlotIds(exceptName) {
    const lower = (exceptName || '').toLowerCase();
    const out = new Set();
    local.selections.forEach(s => {
      if ((s.candidate.name || '').toLowerCase() === lower) return;
      if (s.slot && s.slot.slot_id) out.add(s.slot.slot_id);
    });
    return out;
  }

  function firstFreeSlot() {
    const used = usedSlotIds(null);
    return (local.openSlots || []).find(o => !used.has(o.slot_id)) || null;
  }

  function bindGrid(slot) {
    slot.querySelectorAll('[data-role="reprint-slot"]').forEach(sel => {
      sel.onchange = () => onReassignSlot(sel.dataset.name, sel.value);
    });
    slot.querySelectorAll('[data-role="reprint-pin"]').forEach(cb => {
      cb.onchange = () => onTogglePin(cb.dataset.name, cb.checked);
    });
    slot.querySelectorAll('[data-role="reprint-remove"]').forEach(btn => {
      btn.onclick = () => onRemovePick(btn.dataset.name);
    });
  }

  function findSelection(name) {
    const lower = (name || '').toLowerCase();
    return local.selections.find(s => (s.candidate.name || '').toLowerCase() === lower) || null;
  }

  function onReassignSlot(name, slotId) {
    const sel = findSelection(name);
    if (!sel) return;
    const open = (local.openSlots || []).find(o => o.slot_id === slotId);
    sel.slot = { slot_id: slotId, descriptor: open ? (open.text || '') : sel.slot.descriptor };
    sel.pinned = true; // a hand placement is a pin (preserve on Refresh)
    afterEdit();
  }

  function onTogglePin(name, pinned) {
    const sel = findSelection(name);
    if (!sel) return;
    sel.pinned = !!pinned;
    afterEdit();
  }

  function onRemovePick(name) {
    const lower = (name || '').toLowerCase();
    const i = local.selections.findIndex(s => (s.candidate.name || '').toLowerCase() === lower);
    if (i < 0) return;
    local.selections.splice(i, 1);
    afterEdit();
  }

  // A manual edit changed the working selections — repaint the dependent surfaces
  // (grid dropdowns + summary counts + pool buttons + footer) without a server call.
  function afterEdit() {
    local.hasContent = local.selections.length > 0;
    const root = bodyRoot();
    const state = local.state;
    if (!root) return;
    paintGrid(root, state);
    paintSummary(root, state);
    refreshPoolButtons(root);
    paintFooter(getFooter(root), state);
    setLocked(local.locked);
  }

  // ── Knob panel: per-rarity reprint targets ───────────────────────────────

  function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

  function paintKnobs(root, state) {
    const slot = root.querySelector('[data-role="reprints-knobs"]');
    if (!slot) return;
    if (!local.knobs) { slot.innerHTML = ''; return; }
    const disabled = isPastTab(state) || local.locked;

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
        <div class="wiz-reprints-knob-grid" data-role="reprints-knob-grid"></div>
        <div class="wiz-reprints-knob-jitter">
          <label>Jitter</label>
          <input type="number" min="0" max="1" step="0.05" data-knob="jitter_pct"
                 value="${escAttr(String(jitter))}" ${disabled ? 'disabled' : ''}>
          <span class="wiz-reprints-knob-hint">proportional ± on the auto total (0 = off)</span>
        </div>
        <div class="wiz-reprints-knob-preview">Reprints this run ≈ <strong>${escHtml(String(total))}</strong>${pending}</div>
      </details>
    `;

    W.KnobPanel(slot.querySelector('[data-role="reprints-knob-grid"]'), {
      specs: RARITIES.map(r => ({ key: r, label: cap(r), min: 0, step: 1 })),
      values: local.knobs,
      provenance: local.provenance,
      defaultProvenance: 'auto',
      disabled,
      nullable: true,
      badgeAfterInput: true,
      placeholder: (spec) =>
        `auto (${local.previewTargets[spec.key] != null ? local.previewTargets[spec.key] : 0})`,
      event: 'change',
      classes: { row: 'wiz-reprints-knob' },
      onChange: () => onKnobChange(root, state),
    });

    const j = slot.querySelector('input[data-knob="jitter_pct"]');
    if (j) j.onchange = () => onKnobChange(root, state);
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

  // ── Refresh: re-run AI selection, preserving pinned picks ─────────────────

  function pinnedPayload() {
    return local.selections
      .filter(s => s.pinned && s.candidate.name && s.slot && s.slot.slot_id)
      .map(s => ({ card_name: s.candidate.name, slot_id: s.slot.slot_id, reason: s.reason || '' }));
  }

  async function onRefreshAll() {
    if (local.locked) return;
    const root = bodyRoot();
    const state = local.state;
    const knobs = root ? readKnobInputs(root) : null;
    const pinned = pinnedPayload();
    const confirmMsg = local.hasContent
      ? (pinned.length
          ? `Re-run AI selection? Your ${pinned.length} pinned pick${pinned.length === 1 ? '' : 's'} stay; the rest are re-rolled.`
          : 'Re-run reprint selection? Current picks will be replaced.')
      : '';
    await W.runAiAction({
      isLocked: () => local.locked,
      setLocked,
      confirm: () => confirmMsg,
      busyLabel: 'Selecting reprints…',
      run: async ({ post }) => {
        const body = {};
        if (knobs) body.knobs = knobs;
        if (pinned.length) body.pinned = pinned;
        const data = await post('/api/wizard/reprints/refresh', body, 'Refresh failed');
        if (!data) return;
        local.selections = normalizeSelections(data.selections);
        local.hasContent = !!data.has_content || local.selections.length > 0;
        local.targetCount = data.target_count != null ? data.target_count : local.targetCount;
        if (data.eligible_slots != null) local.eligibleSlots = data.eligible_slots;
        if (data.knobs) local.knobs = data.knobs;
        if (data.provenance) local.provenance = data.provenance;
        if (data.preview_targets) local.previewTargets = data.preview_targets;
        local.knobsDirty = false;
        rerender(root, state);
      },
    });
  }

  // ── Footer: Save & Continue when paused_for_review (§1) ──────────────────

  function paintFooter(footer, state) {
    if (!footer) return;
    const isLatest = !state || state.latestTabId === STAGE_ID;
    const isPaused = local.stageStatus === 'paused_for_review';
    const isCompleted = local.stageStatus === 'completed';
    const next = W.nextStageEntryAfter(STAGE_ID);
    const nextName = next ? next.name : 'the next stage';
    const n = local.selections.length;

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Editing past reprint selections is destructive — use the Edit button above.</span>`;
    } else if (isCompleted) {
      html = `<span class="wiz-footer-note">Reprints saved. Engine is on ${escHtml(nextName)} — switch tabs to follow.</span>`;
    } else if (!isPaused) {
      html = `<span class="wiz-footer-note">This stage runs automatically. Tick "Stop after this step" above to review + edit here before continuing.</span>`;
    } else {
      html = `
        <button type="button" class="wiz-btn-primary" data-role="reprints-advance"
                ${local.locked ? 'disabled' : ''}>
          Save &amp; Continue: ${escHtml(nextName)}
        </button>
        <span class="wiz-footer-note">${escHtml(String(n))} reprint${n === 1 ? '' : 's'} selected.</span>
      `;
    }

    W.paintFooter(footer, html, { role: 'reprints-advance', onClick: onSaveAndAdvance });
  }

  function selectionsPayload() {
    return local.selections
      .filter(s => s.candidate.name && s.slot && s.slot.slot_id)
      .map(s => ({
        card_name: s.candidate.name,
        slot_id: s.slot.slot_id,
        reason: s.reason || '',
        pinned: !!s.pinned,
      }));
  }

  function onSaveAndAdvance() {
    return W.saveAndAdvance({
      stageId: STAGE_ID,
      isLocked: () => local.locked,
      setLocked,
      btnRole: 'reprints-advance',
      saveUrl: '/api/wizard/reprints/save',
      payload: () => ({ selections: selectionsPayload() }),
    });
  }

  // ── Form lock (§3) ────────────────────────────────────────────────────────

  function aiBusy() {
    return local.locked || local.stageStatus === 'running';
  }

  function setLocked(locked) {
    local.locked = !!locked;
    W.setTabLocked(bodyRoot(), aiBusy(), {
      lockClass: 'wiz-tile-locked',
      selectors: [
        '[data-role="reprints-refresh-all"]',
        '[data-role="reprints-pool-add"]',
        '[data-role="reprints-pool-search"]',
        '[data-role="reprint-slot"]',
        '[data-role="reprint-pin"]',
        '[data-role="reprint-remove"]',
        'input[data-knob]',
      ],
      footerSelector: '[data-role="reprints-advance"]',
    });
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  const bodyRoot = () => W.tabRoot(STAGE_ID);

  const getFooter = (root) => W.tabFooter(root);

  const isPastTab = (state) => W.isPastTab(STAGE_ID, state);

  const isEditable = (state) => !isPastTab(state);

  const escHtml = W.escHtml;

  const escAttr = W.escAttr;

})();
