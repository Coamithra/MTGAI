/**
 * Wizard Human Final Review tab — full rendered-card-composite review gate.
 *
 * Stage: human_final_review (REVIEW pause gate — review_mode = 'human').
 * This is the LAST stage. The runner is a no-op; the engine pauses here
 * awaiting human sign-off. This renderer owns `content` + `footer`;
 * wizard_stage.js owns the header (status pill, break-point toggle, Edit button).
 *
 * Terminal state: latest tab + stage.status === 'completed' → show
 * "✓ Set complete" in the footer (matches stageFooterHtml in wizard_stage.js §8.4).
 *
 * Conventions followed:
 *   §1  "Next step" footer when paused_for_review; "✓ Set complete" when completed
 *   §3  form lock during any in-flight POST
 *   §8  status pill flows from stage.status via wizard_stage.js
 *   §9  "Stop after this step" toggle owned by wizard_stage.js
 *   §12 escHtml / escAttr; .onclick single-slot rebind; lazy mount + idempotent rerender
 *
 * Real data lives behind:
 *   GET  /api/wizard/human_final_review/state    → { cards[], approved, rejected }
 *   POST /api/wizard/human_final_review/decision → { card_id, decision: 'approve'|'reject', notes }
 *
 * Rendered card image URL:
 *   TODO: GET /api/wizard/human_final_review/render/<card_id>  (serves the final render PNG)
 *   Renders are gitignored; the path is not known at JS-write time.
 *   Until that endpoint exists every tile shows a card-shaped placeholder.
 *
 * Both are TODO — the tab degrades gracefully with zero backend.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'human_final_review';

  const STYLE_ID = 'wiz-' + STAGE_ID + '-styles';

  const local = {
    initialized: false,
    cards: [],          // [{id, name, rarity, colors, render_url, decision, notes}]
    hasContent: false,
    stageStatus: 'pending',
    locked: false,
    filter: { rarity: 'all', decision: 'all' },
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ---------------------------------------------------------------------------
  // Styles (injected once, scoped to wiz-hfr-*)
  // ---------------------------------------------------------------------------

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      /* ---- Human Final Review tab scoped styles ---- */
      .wiz-hfr-summary { margin-bottom: 0.75rem; }
      .wiz-hfr-counts {
        display: flex; gap: 1.25rem; flex-wrap: wrap;
        font-size: 0.82rem; color: #aaa; margin-bottom: 0.5rem;
      }
      .wiz-hfr-count-chip {
        display: flex; align-items: center; gap: 0.3rem;
      }
      .wiz-hfr-count-chip .chip-val {
        font-variant-numeric: tabular-nums; font-weight: 600; color: #e0e0e0;
      }
      .wiz-hfr-count-chip.approved .chip-val { color: #00d4aa; }
      .wiz-hfr-count-chip.rejected .chip-val { color: #ff4757; }

      .wiz-hfr-filters {
        display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center;
        margin-bottom: 0.85rem;
      }
      .wiz-hfr-filters label {
        font-size: 0.75rem; color: #888; display: flex; align-items: center; gap: 0.3rem;
      }
      .wiz-hfr-filters select {
        padding: 0.25rem 0.5rem;
        background: var(--bg-primary, #1a1a2e);
        border: 1px solid #333; border-radius: 5px;
        color: #e0e0e0; font-size: 0.78rem; font-family: inherit;
      }
      .wiz-hfr-filters select:focus { outline: none; border-color: #4a9eff; }

      .wiz-hfr-approve-all-row {
        display: flex; justify-content: flex-end; margin-bottom: 0.5rem;
      }

      /* Rendered card grid — card aspect ratio 822×1122 ≈ 0.732 */
      .wiz-hfr-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
        gap: 0.85rem;
      }
      .wiz-hfr-empty {
        color: #666; font-style: italic; font-size: 0.85rem;
        grid-column: 1 / -1; padding: 1.5rem 0;
      }

      .wiz-hfr-card {
        background: #0f1729;
        border: 1px solid #1f2540;
        border-radius: 8px;
        overflow: hidden;
        display: flex; flex-direction: column;
        transition: border-color 0.15s;
      }
      .wiz-hfr-card.decision-approve { border-color: #00d4aa55; }
      .wiz-hfr-card.decision-reject  { border-color: #ff475755; }

      /* Card render area — portrait aspect ratio matching the M15 frame */
      .wiz-hfr-render-frame {
        width: 100%;
        aspect-ratio: 0.732;   /* 822/1122 */
        overflow: hidden;
        background: #0a0f22;
        display: flex; align-items: center; justify-content: center;
        position: relative;
      }
      .wiz-hfr-render-frame img {
        width: 100%; height: 100%; object-fit: cover;
        display: block;
      }
      .wiz-hfr-render-placeholder {
        width: 100%; height: 100%;
        display: flex; flex-direction: column;
        align-items: center; justify-content: center;
        gap: 0.4rem;
        color: #444; font-size: 0.75rem; text-align: center;
        border: 1px dashed #2a2f55;
      }
      .wiz-hfr-render-placeholder-icon {
        font-size: 1.8rem; opacity: 0.35;
      }
      .wiz-hfr-render-placeholder-name {
        font-size: 0.72rem; color: #555; padding: 0 0.5rem;
      }

      .wiz-hfr-card-body {
        padding: 0.55rem 0.65rem;
        display: flex; flex-direction: column; gap: 0.4rem;
        flex: 1;
      }
      .wiz-hfr-card-name {
        font-weight: 700; font-size: 0.82rem; color: #e0e0e0;
        display: flex; justify-content: space-between; align-items: baseline; gap: 0.3rem;
        white-space: nowrap; overflow: hidden;
      }
      .wiz-hfr-card-name span:first-child {
        overflow: hidden; text-overflow: ellipsis;
      }
      .wiz-hfr-rarity {
        font-size: 0.62rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.06em; padding: 1px 5px; border-radius: 3px;
        background: #1a1a2e; color: #aaa; flex-shrink: 0;
      }
      .wiz-hfr-rarity.C { color: #aaa; }
      .wiz-hfr-rarity.U { color: #8cbfff; }
      .wiz-hfr-rarity.R { color: #f5a623; }
      .wiz-hfr-rarity.M { color: #e94560; }

      .wiz-hfr-controls {
        display: flex; gap: 0.35rem;
      }
      .wiz-hfr-btn-approve, .wiz-hfr-btn-reject {
        flex: 1;
        padding: 0.3rem 0.5rem;
        border-radius: 5px;
        font-size: 0.75rem; font-weight: 600;
        cursor: pointer; font-family: inherit;
        border: 1px solid transparent;
        transition: background 0.12s, border-color 0.12s;
      }
      .wiz-hfr-btn-approve {
        background: transparent; border-color: #00d4aa44; color: #00d4aa;
      }
      .wiz-hfr-btn-approve:hover { background: #00d4aa18; }
      .wiz-hfr-btn-approve.active { background: #00d4aa22; border-color: #00d4aa; }

      .wiz-hfr-btn-reject {
        background: transparent; border-color: #ff475744; color: #ff4757;
      }
      .wiz-hfr-btn-reject:hover { background: #ff475718; }
      .wiz-hfr-btn-reject.active { background: #ff475722; border-color: #ff4757; }

      .wiz-hfr-notes {
        width: 100%; box-sizing: border-box;
        padding: 0.28rem 0.45rem;
        background: var(--bg-primary, #1a1a2e);
        border: 1px solid #2a2f55; border-radius: 5px;
        color: #ccc; font-size: 0.73rem; font-family: inherit;
        resize: vertical; min-height: 2.2rem;
      }
      .wiz-hfr-notes:focus { outline: none; border-color: #4a9eff; }

      /* Form lock */
      .wiz-hfr-locked { opacity: 0.85; }
      .wiz-hfr-locked button:disabled,
      .wiz-hfr-locked textarea:disabled,
      .wiz-hfr-locked select:disabled { cursor: not-allowed; }
    `;
    document.head.appendChild(style);
  }

  // ---------------------------------------------------------------------------
  // Top-level render
  // ---------------------------------------------------------------------------

  function render({ root, state, stage, content, footer }) {
    injectStyles();

    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      bootstrap(root, state).catch(err => {
        W.toast('Failed to load final review state: ' + err.message, 'error');
        const slot = root.querySelector('[data-role="hfr-grid"]');
        if (slot) slot.innerHTML = `<div class="wiz-hfr-empty">Could not load render data — is a project open?</div>`;
      });
      paintFooter(footer, state);
      return;
    }

    const prevStatus = local.stageStatus;
    if (stage) local.stageStatus = stage.status;

    const justFinished =
      stage &&
      prevStatus !== local.stageStatus &&
      local.stageStatus !== 'pending' &&
      local.stageStatus !== 'running' &&
      !local.hasContent;
    if (justFinished) {
      bootstrap(root, state).catch(err =>
        W.toast('Failed to refresh final review state: ' + err.message, 'error')
      );
      return;
    }

    // Always repaint the footer for the final stage — the "✓ Set complete"
    // terminal state depends on both stageStatus and isLatest, and the
    // status may have just flipped from paused_for_review → completed.
    paintFooter(footer, state);
    setLocked(local.locked);
  }

  function mountShellHtml() {
    return `
      <div data-role="hfr-summary"></div>
      <div data-role="hfr-filters"></div>
      <div class="wiz-hfr-grid" data-role="hfr-grid">
        <div class="wiz-hfr-empty">Loading final review data…</div>
      </div>
    `;
  }

  // ---------------------------------------------------------------------------
  // Bootstrap
  // TODO: implement GET /api/wizard/human_final_review/state
  //   Response shape: { cards: RenderItem[], has_content: bool, stage_status: str }
  //   RenderItem: { id, name, rarity, colors, render_url: str|null,
  //                 decision: 'approve'|'reject'|null, notes: str }
  //   render_url is the server-relative path for the final rendered card PNG.
  //   TODO: GET /api/wizard/human_final_review/render/<card_id>
  // ---------------------------------------------------------------------------

  async function bootstrap(root, state) {
    let data;
    try {
      const resp = await fetch('/api/wizard/human_final_review/state');
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        if (resp.status === 404 || resp.status === 405) {
          data = { cards: [], has_content: false };
        } else {
          throw new Error(err.error || `HTTP ${resp.status}`);
        }
      } else {
        data = await resp.json();
      }
    } catch (_fetchErr) {
      data = { cards: [], has_content: false };
    }

    const incoming = Array.isArray(data.cards) ? data.cards : [];
    if (local.cards.length === 0) {
      local.cards = incoming;
    } else {
      const byId = {};
      local.cards.forEach(c => { byId[c.id] = c; });
      local.cards = incoming.map(c => {
        const ex = byId[c.id];
        if (ex && ex._local_edit) return ex;
        return c;
      });
    }
    local.hasContent = local.cards.length > 0;
    if (data.stage_status) local.stageStatus = data.stage_status;

    paintSummary(root, state);
    paintFilters(root);
    paintGrid(root, state);
    paintFooter(getFooter(root), state);
  }

  // ---------------------------------------------------------------------------
  // Summary
  // ---------------------------------------------------------------------------

  function paintSummary(root, _state) {
    const slot = root.querySelector('[data-role="hfr-summary"]');
    if (!slot) return;
    const total    = local.cards.length;
    const approved = local.cards.filter(c => c.decision === 'approve').length;
    const rejected = local.cards.filter(c => c.decision === 'reject').length;
    const pending  = total - approved - rejected;

    slot.innerHTML = `
      <div class="wiz-hfr-summary">
        <div class="wiz-theme-section-header-row" style="margin-bottom:0.5rem">
          <h3 style="margin:0">Final Review</h3>
        </div>
        <p style="color:#888;font-size:0.8rem;margin:0 0 0.5rem">
          Review the final rendered card composites. Approve to accept; reject to flag for rework.
        </p>
        <div class="wiz-hfr-counts">
          <span class="wiz-hfr-count-chip">
            <span class="chip-val">${total}</span> total
          </span>
          <span class="wiz-hfr-count-chip approved">
            <span class="chip-val">${approved}</span> approved
          </span>
          <span class="wiz-hfr-count-chip rejected">
            <span class="chip-val">${rejected}</span> rejected
          </span>
          <span class="wiz-hfr-count-chip">
            <span class="chip-val">${pending}</span> pending
          </span>
        </div>
        ${total > 0 ? `
        <div class="wiz-hfr-approve-all-row">
          <button type="button" class="wiz-btn-secondary" data-role="hfr-approve-all"
                  title="Mark all rendered cards approved">Approve all</button>
        </div>` : ''}
      </div>
    `;
    const btn = slot.querySelector('[data-role="hfr-approve-all"]');
    if (btn) btn.onclick = () => onApproveAll(root);
  }

  // ---------------------------------------------------------------------------
  // Filters
  // ---------------------------------------------------------------------------

  function paintFilters(root) {
    const slot = root.querySelector('[data-role="hfr-filters"]');
    if (!slot) return;
    if (!local.hasContent) { slot.innerHTML = ''; return; }
    slot.innerHTML = `
      <div class="wiz-hfr-filters">
        <label>Rarity
          <select data-role="hfr-filter-rarity">
            <option value="all" ${local.filter.rarity==='all'?'selected':''}>All</option>
            <option value="C"   ${local.filter.rarity==='C'?'selected':''}>Common</option>
            <option value="U"   ${local.filter.rarity==='U'?'selected':''}>Uncommon</option>
            <option value="R"   ${local.filter.rarity==='R'?'selected':''}>Rare</option>
            <option value="M"   ${local.filter.rarity==='M'?'selected':''}>Mythic</option>
          </select>
        </label>
        <label>Decision
          <select data-role="hfr-filter-decision">
            <option value="all"     ${local.filter.decision==='all'?'selected':''}>All</option>
            <option value="pending" ${local.filter.decision==='pending'?'selected':''}>Pending</option>
            <option value="approve" ${local.filter.decision==='approve'?'selected':''}>Approved</option>
            <option value="reject"  ${local.filter.decision==='reject'?'selected':''}>Rejected</option>
          </select>
        </label>
      </div>
    `;
    const rarSel = slot.querySelector('[data-role="hfr-filter-rarity"]');
    const decSel = slot.querySelector('[data-role="hfr-filter-decision"]');
    if (rarSel) rarSel.onchange = () => {
      local.filter.rarity = rarSel.value;
      paintGrid(bodyRoot(), W.getState());
    };
    if (decSel) decSel.onchange = () => {
      local.filter.decision = decSel.value;
      paintGrid(bodyRoot(), W.getState());
    };
  }

  // ---------------------------------------------------------------------------
  // Grid
  // ---------------------------------------------------------------------------

  function paintGrid(root, _state) {
    const slot = root && root.querySelector('[data-role="hfr-grid"]');
    if (!slot) return;
    if (!local.hasContent) {
      const generating = local.stageStatus === 'running' || local.locked;
      slot.innerHTML = `<div class="wiz-hfr-empty">${
        generating
          ? 'Cards are being rendered — check back once the rendering stage completes.'
          : 'No rendered cards yet. Renders will appear here once the rendering stage has run.'
      }</div>`;
      return;
    }
    const visible = visibleCards();
    if (visible.length === 0) {
      slot.innerHTML = `<div class="wiz-hfr-empty">No cards match the current filter.</div>`;
      return;
    }
    slot.innerHTML = visible.map(c => renderTileHtml(c)).join('');
    bindGrid(slot);
  }

  function visibleCards() {
    return local.cards.filter(c => {
      if (local.filter.rarity !== 'all' && c.rarity !== local.filter.rarity) return false;
      const dec = c.decision || null;
      if (local.filter.decision === 'pending' && dec !== null) return false;
      if (local.filter.decision === 'approve' && dec !== 'approve') return false;
      if (local.filter.decision === 'reject'  && dec !== 'reject')  return false;
      return true;
    });
  }

  function renderTileHtml(c) {
    const dec = c.decision || '';
    const rar = c.rarity || '';
    // TODO: replace placeholder once GET /api/wizard/human_final_review/render/<card_id> exists.
    const renderHtml = c.render_url
      ? `<img src="${escAttr(c.render_url)}" alt="Render for ${escAttr(c.name || '')}" loading="lazy">`
      : `<div class="wiz-hfr-render-placeholder">
           <span class="wiz-hfr-render-placeholder-icon">&#x1F3A8;</span>
           <span class="wiz-hfr-render-placeholder-name">${escHtml(c.name || 'Render pending')}</span>
         </div>`;
    return `
      <article class="wiz-hfr-card decision-${escAttr(dec)}" data-card-id="${escAttr(c.id)}">
        <div class="wiz-hfr-render-frame">${renderHtml}</div>
        <div class="wiz-hfr-card-body">
          <div class="wiz-hfr-card-name">
            <span>${escHtml(c.name || '(unnamed)')}</span>
            <span class="wiz-hfr-rarity ${escAttr(rar)}">${escHtml(rar)}</span>
          </div>
          <div class="wiz-hfr-controls">
            <button type="button" class="wiz-hfr-btn-approve${dec==='approve'?' active':''}"
                    data-action="approve">Approve</button>
            <button type="button" class="wiz-hfr-btn-reject${dec==='reject'?' active':''}"
                    data-action="reject">Reject</button>
          </div>
          <textarea class="wiz-hfr-notes" data-role="hfr-notes"
                    placeholder="Optional notes…" rows="2">${escHtml(c.notes || '')}</textarea>
        </div>
      </article>
    `;
  }

  function bindGrid(slot) {
    slot.querySelectorAll('.wiz-hfr-card').forEach(card => {
      const id = card.dataset.cardId;
      card.querySelectorAll('[data-action]').forEach(btn => {
        btn.onclick = () => onDecision(id, btn.dataset.action, card);
      });
      const notes = card.querySelector('[data-role="hfr-notes"]');
      if (notes) notes.oninput = () => {
        updateCard(id, { notes: notes.value, _local_edit: true });
      };
    });
  }

  // ---------------------------------------------------------------------------
  // Decision handlers
  // TODO: wire POST /api/wizard/human_final_review/decision
  //   Body: { card_id, decision: 'approve'|'reject', notes }
  // ---------------------------------------------------------------------------

  function onDecision(id, action, cardEl) {
    if (local.locked) return;
    const c = local.cards.find(x => x.id === id);
    const newDec = c && c.decision === action ? null : action;
    updateCard(id, { decision: newDec, _local_edit: true });

    if (cardEl) {
      cardEl.className = `wiz-hfr-card decision-${newDec || ''}`;
      cardEl.querySelectorAll('[data-action]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.action === newDec);
      });
    }

    // TODO: POST /api/wizard/human_final_review/decision
    const notes = cardEl && cardEl.querySelector('[data-role="hfr-notes"]');
    W.postJSON('/api/wizard/human_final_review/decision', {
      card_id: id,
      decision: newDec,
      notes: notes ? notes.value : '',
    }).catch(() => {});

    const root = bodyRoot();
    if (root) paintSummary(root, W.getState());
  }

  function onApproveAll(root) {
    if (local.locked) return;
    if (!confirm(`Approve all ${local.cards.length} rendered cards?`)) return;
    local.cards.forEach(c => { c.decision = 'approve'; c._local_edit = true; });
    paintSummary(root, W.getState());
    paintGrid(root, W.getState());
    // TODO: POST /api/wizard/human_final_review/decision with bulk payload
    W.postJSON('/api/wizard/human_final_review/decision', {
      bulk: true,
      decision: 'approve',
      card_ids: local.cards.map(c => c.id),
    }).catch(() => {});
  }

  function updateCard(id, patch) {
    const i = local.cards.findIndex(c => c.id === id);
    if (i >= 0) local.cards[i] = Object.assign({}, local.cards[i], patch);
  }

  // ---------------------------------------------------------------------------
  // Footer — "✓ Set complete" when latest + completed (final stage terminal state §8.4)
  //         "Next step" when paused_for_review; note when not yet paused.
  // ---------------------------------------------------------------------------

  function paintFooter(footer, state) {
    if (!footer) return;
    const isLatest = !state || state.latestTabId === STAGE_ID;
    const isPaused    = local.stageStatus === 'paused_for_review';
    const isCompleted = local.stageStatus === 'completed';

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Final review is in the past — the set has been completed.</span>`;
    } else if (isCompleted) {
      // §8.4 terminal state — mirrors stageFooterHtml's "✓ Set complete" branch.
      html = `<span class="wiz-footer-complete" role="status">&#x2713; Set complete</span>`;
    } else if (!isPaused) {
      html = `<span class="wiz-footer-note">Waiting for this stage to reach the review pause…</span>`;
    } else {
      // Derive next stage name; for the final stage this is typically null.
      const next = W.nextStageEntryAfter(STAGE_ID);
      const label = next ? `Next step: ${next.name}` : 'Finish set';
      html = `
        <button type="button" class="wiz-btn-primary" data-role="hfr-next-step"
                ${local.locked ? 'disabled' : ''}>
          ${escHtml(label)}
        </button>
        <span class="wiz-footer-note">Review renders above, then finish when ready.</span>
      `;
    }

    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
    }
    const btn = footer.querySelector('[data-role="hfr-next-step"]');
    if (btn) btn.onclick = onAdvance;
  }

  async function onAdvance() {
    if (local.locked) return;
    setLocked(true);
    const root = bodyRoot();
    const footer = getFooter(root);
    const btn = footer && footer.querySelector('[data-role="hfr-next-step"]');
    const orig = btn ? btn.textContent : '';
    if (btn) btn.textContent = 'Finishing…';
    try {
      const resp = await W.postJSON('/api/wizard/advance', {});
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        if (resp.status === 409 && data.running_action) {
          W.toast(`${data.running_action} is in progress — try again when it finishes.`, 'error');
        } else {
          W.toast(data.error || `Advance failed (${resp.status})`, 'error');
        }
        if (btn) btn.textContent = orig;
        return;
      }
      const data = await resp.json().catch(() => ({}));
      const next = W.nextStageEntryAfter(STAGE_ID);
      // For the last stage, navigate_to from the server is canonical.
      // Fall back to /pipeline if there's no next stage.
      window.location.assign(data.navigate_to || (next ? `/pipeline/${next.id}` : '/pipeline'));
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
      if (btn) btn.textContent = orig;
    } finally {
      setLocked(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Form lock (§3)
  // ---------------------------------------------------------------------------

  function setLocked(locked) {
    local.locked = !!locked;
    const root = bodyRoot();
    if (!root) return;
    root.classList.toggle('wiz-hfr-locked', !!locked);
    const sel = [
      '.wiz-hfr-btn-approve',
      '.wiz-hfr-btn-reject',
      '.wiz-hfr-notes',
      '[data-role="hfr-approve-all"]',
      '[data-role="hfr-filter-rarity"]',
      '[data-role="hfr-filter-decision"]',
    ].join(',');
    root.querySelectorAll(sel).forEach(el => { el.disabled = !!locked; });
    const footerBtn = root.querySelector('[data-role="hfr-next-step"]');
    if (footerBtn) footerBtn.disabled = !!locked;
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function bodyRoot() {
    return document.querySelector(`.wiz-tab-body[data-tab-id="${STAGE_ID}"]`);
  }

  function getFooter(root) {
    return root && root.querySelector('[data-role="footer"]');
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
