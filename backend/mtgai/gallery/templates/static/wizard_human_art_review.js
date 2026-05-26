/**
 * Wizard Human Art Review tab — per-card selected-art review gate.
 *
 * Stage: human_art_review (REVIEW pause gate — review_mode = 'human').
 * The runner is a no-op; the engine pauses here awaiting human sign-off.
 * This renderer owns `content` + `footer`; wizard_stage.js owns the
 * header (status pill, break-point toggle, Edit button).
 *
 * Conventions followed:
 *   §1  "Next step" footer button when paused_for_review (latest tab)
 *   §3  form lock during any in-flight POST
 *   §8  status pill flows from stage.status via wizard_stage.js
 *   §9  "Stop after this step" toggle owned by wizard_stage.js
 *   §12 escHtml / escAttr; .onclick single-slot rebind; lazy mount + idempotent rerender
 *
 * Real data lives behind:
 *   GET  /api/wizard/human_art_review/state   → { cards[], approved, rejected, regen }
 *   POST /api/wizard/human_art_review/decision → { card_id, decision: 'approve'|'reject'|'regen', notes }
 *
 * Image thumbnail URL:
 *   TODO: GET /api/wizard/human_art_review/art/<card_id>  (serves the selected art PNG)
 *   Art is gitignored; the path is not known at JS-write time.
 *   Until that endpoint exists every tile shows a placeholder frame.
 *
 * Both are TODO — the tab degrades gracefully with zero backend.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'human_art_review';

  const STYLE_ID = 'wiz-' + STAGE_ID + '-styles';

  const local = {
    initialized: false,
    cards: [],          // [{id, name, rarity, colors, art_url, decision, notes}]
    hasContent: false,
    stageStatus: 'pending',
    locked: false,
    filter: { rarity: 'all', decision: 'all' },
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ---------------------------------------------------------------------------
  // Styles (injected once, scoped to wiz-har-*)
  // ---------------------------------------------------------------------------

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      /* ---- Human Art Review tab scoped styles ---- */
      .wiz-har-summary { margin-bottom: 0.75rem; }
      .wiz-har-counts {
        display: flex; gap: 1.25rem; flex-wrap: wrap;
        font-size: 0.82rem; color: #aaa; margin-bottom: 0.5rem;
      }
      .wiz-har-count-chip {
        display: flex; align-items: center; gap: 0.3rem;
      }
      .wiz-har-count-chip .chip-val {
        font-variant-numeric: tabular-nums; font-weight: 600; color: #e0e0e0;
      }
      .wiz-har-count-chip.approved .chip-val { color: #00d4aa; }
      .wiz-har-count-chip.rejected .chip-val { color: #ff4757; }
      .wiz-har-count-chip.regen    .chip-val { color: #ffa502; }

      .wiz-har-filters {
        display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center;
        margin-bottom: 0.85rem;
      }
      .wiz-har-filters label {
        font-size: 0.75rem; color: #888; display: flex; align-items: center; gap: 0.3rem;
      }
      .wiz-har-filters select {
        padding: 0.25rem 0.5rem;
        background: var(--bg-primary, #1a1a2e);
        border: 1px solid #333; border-radius: 5px;
        color: #e0e0e0; font-size: 0.78rem; font-family: inherit;
      }
      .wiz-har-filters select:focus { outline: none; border-color: #4a9eff; }

      .wiz-har-approve-all-row {
        display: flex; justify-content: flex-end; margin-bottom: 0.5rem;
      }

      .wiz-har-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
        gap: 0.85rem;
      }
      .wiz-har-empty {
        color: #666; font-style: italic; font-size: 0.85rem;
        grid-column: 1 / -1; padding: 1.5rem 0;
      }

      .wiz-har-card {
        background: #0f1729;
        border: 1px solid #1f2540;
        border-radius: 8px;
        overflow: hidden;
        display: flex; flex-direction: column;
        transition: border-color 0.15s;
      }
      .wiz-har-card.decision-approve { border-color: #00d4aa55; }
      .wiz-har-card.decision-reject  { border-color: #ff475755; }
      .wiz-har-card.decision-regen   { border-color: #ffa50255; }

      /* Art thumbnail area — square aspect ratio placeholder */
      .wiz-har-art-frame {
        width: 100%; aspect-ratio: 4/3; overflow: hidden;
        background: #0a0f22;
        display: flex; align-items: center; justify-content: center;
        position: relative;
      }
      .wiz-har-art-frame img {
        width: 100%; height: 100%; object-fit: cover;
        display: block;
      }
      .wiz-har-art-placeholder {
        width: 100%; height: 100%;
        display: flex; flex-direction: column;
        align-items: center; justify-content: center;
        gap: 0.4rem;
        color: #444; font-size: 0.75rem; text-align: center;
        border: 1px dashed #2a2f55;
      }
      .wiz-har-art-placeholder-icon {
        font-size: 1.6rem; opacity: 0.4;
      }

      .wiz-har-card-body {
        padding: 0.65rem 0.75rem;
        display: flex; flex-direction: column; gap: 0.45rem;
        flex: 1;
      }
      .wiz-har-card-name {
        font-weight: 700; font-size: 0.88rem; color: #e0e0e0;
        display: flex; justify-content: space-between; align-items: baseline; gap: 0.3rem;
      }
      .wiz-har-rarity {
        font-size: 0.65rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.06em; padding: 1px 5px; border-radius: 3px;
        background: #1a1a2e; color: #aaa; flex-shrink: 0;
      }
      .wiz-har-rarity.C { color: #aaa; }
      .wiz-har-rarity.U { color: #8cbfff; }
      .wiz-har-rarity.R { color: #f5a623; }
      .wiz-har-rarity.M { color: #e94560; }

      .wiz-har-controls {
        display: flex; gap: 0.3rem; flex-wrap: wrap;
      }
      .wiz-har-btn-approve, .wiz-har-btn-reject, .wiz-har-btn-regen {
        flex: 1;
        padding: 0.28rem 0.4rem;
        border-radius: 5px;
        font-size: 0.72rem; font-weight: 600;
        cursor: pointer; font-family: inherit;
        border: 1px solid transparent;
        transition: background 0.12s, border-color 0.12s;
      }
      .wiz-har-btn-approve {
        background: transparent; border-color: #00d4aa44; color: #00d4aa;
      }
      .wiz-har-btn-approve:hover { background: #00d4aa18; }
      .wiz-har-btn-approve.active { background: #00d4aa22; border-color: #00d4aa; }

      .wiz-har-btn-reject {
        background: transparent; border-color: #ff475744; color: #ff4757;
      }
      .wiz-har-btn-reject:hover { background: #ff475718; }
      .wiz-har-btn-reject.active { background: #ff475722; border-color: #ff4757; }

      .wiz-har-btn-regen {
        background: transparent; border-color: #ffa50244; color: #ffa502;
      }
      .wiz-har-btn-regen:hover { background: #ffa50218; }
      .wiz-har-btn-regen.active { background: #ffa50222; border-color: #ffa502; }

      .wiz-har-notes {
        width: 100%; box-sizing: border-box;
        padding: 0.28rem 0.45rem;
        background: var(--bg-primary, #1a1a2e);
        border: 1px solid #2a2f55; border-radius: 5px;
        color: #ccc; font-size: 0.73rem; font-family: inherit;
        resize: vertical; min-height: 2.2rem;
      }
      .wiz-har-notes:focus { outline: none; border-color: #4a9eff; }

      /* Form lock */
      .wiz-har-locked { opacity: 0.85; }
      .wiz-har-locked button:disabled,
      .wiz-har-locked textarea:disabled,
      .wiz-har-locked select:disabled { cursor: not-allowed; }
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
        W.toast('Failed to load art review state: ' + err.message, 'error');
        const slot = root.querySelector('[data-role="har-grid"]');
        if (slot) slot.innerHTML = `<div class="wiz-har-empty">Could not load art data — is a project open?</div>`;
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
        W.toast('Failed to refresh art review state: ' + err.message, 'error')
      );
      return;
    }

    paintFooter(footer, state);
    setLocked(local.locked);
  }

  function mountShellHtml() {
    return `
      <div data-role="har-summary"></div>
      <div data-role="har-filters"></div>
      <div class="wiz-har-grid" data-role="har-grid">
        <div class="wiz-har-empty">Loading art review data…</div>
      </div>
    `;
  }

  // ---------------------------------------------------------------------------
  // Bootstrap
  // TODO: implement GET /api/wizard/human_art_review/state
  //   Response shape: { cards: ArtItem[], has_content: bool, stage_status: str }
  //   ArtItem: { id, name, rarity, colors, art_url: str|null,
  //              decision: 'approve'|'reject'|'regen'|null, notes: str }
  //   art_url is the server-relative path returned by the art-serving endpoint.
  //   TODO: GET /api/wizard/human_art_review/art/<card_id>
  // ---------------------------------------------------------------------------

  async function bootstrap(root, state) {
    let data;
    try {
      const resp = await fetch('/api/wizard/human_art_review/state');
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
    const slot = root.querySelector('[data-role="har-summary"]');
    if (!slot) return;
    const total    = local.cards.length;
    const approved = local.cards.filter(c => c.decision === 'approve').length;
    const rejected = local.cards.filter(c => c.decision === 'reject').length;
    const regen    = local.cards.filter(c => c.decision === 'regen').length;
    const pending  = total - approved - rejected - regen;

    slot.innerHTML = `
      <div class="wiz-har-summary">
        <div class="wiz-theme-section-header-row" style="margin-bottom:0.5rem">
          <h3 style="margin:0">Art Review</h3>
        </div>
        <div class="wiz-har-counts">
          <span class="wiz-har-count-chip">
            <span class="chip-val">${total}</span> total
          </span>
          <span class="wiz-har-count-chip approved">
            <span class="chip-val">${approved}</span> approved
          </span>
          <span class="wiz-har-count-chip rejected">
            <span class="chip-val">${rejected}</span> rejected
          </span>
          <span class="wiz-har-count-chip regen">
            <span class="chip-val">${regen}</span> regen
          </span>
          <span class="wiz-har-count-chip">
            <span class="chip-val">${pending}</span> pending
          </span>
        </div>
        ${total > 0 ? `
        <div class="wiz-har-approve-all-row">
          <button type="button" class="wiz-btn-secondary" data-role="har-approve-all"
                  title="Mark every card's art approved">Approve all</button>
        </div>` : ''}
      </div>
    `;
    const btn = slot.querySelector('[data-role="har-approve-all"]');
    if (btn) btn.onclick = () => onApproveAll(root);
  }

  // ---------------------------------------------------------------------------
  // Filters
  // ---------------------------------------------------------------------------

  function paintFilters(root) {
    const slot = root.querySelector('[data-role="har-filters"]');
    if (!slot) return;
    if (!local.hasContent) { slot.innerHTML = ''; return; }
    slot.innerHTML = `
      <div class="wiz-har-filters">
        <label>Rarity
          <select data-role="har-filter-rarity">
            <option value="all" ${local.filter.rarity==='all'?'selected':''}>All</option>
            <option value="C"   ${local.filter.rarity==='C'?'selected':''}>Common</option>
            <option value="U"   ${local.filter.rarity==='U'?'selected':''}>Uncommon</option>
            <option value="R"   ${local.filter.rarity==='R'?'selected':''}>Rare</option>
            <option value="M"   ${local.filter.rarity==='M'?'selected':''}>Mythic</option>
          </select>
        </label>
        <label>Decision
          <select data-role="har-filter-decision">
            <option value="all"     ${local.filter.decision==='all'?'selected':''}>All</option>
            <option value="pending" ${local.filter.decision==='pending'?'selected':''}>Pending</option>
            <option value="approve" ${local.filter.decision==='approve'?'selected':''}>Approved</option>
            <option value="reject"  ${local.filter.decision==='reject'?'selected':''}>Rejected</option>
            <option value="regen"   ${local.filter.decision==='regen'?'selected':''}>Regen</option>
          </select>
        </label>
      </div>
    `;
    const rarSel = slot.querySelector('[data-role="har-filter-rarity"]');
    const decSel = slot.querySelector('[data-role="har-filter-decision"]');
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
    const slot = root && root.querySelector('[data-role="har-grid"]');
    if (!slot) return;
    if (!local.hasContent) {
      const generating = local.stageStatus === 'running' || local.locked;
      slot.innerHTML = `<div class="wiz-har-empty">${
        generating
          ? 'Art is being generated — check back once the art generation stage completes.'
          : 'No art to review yet. Art will appear here once the art generation stage has run.'
      }</div>`;
      return;
    }
    const visible = visibleCards();
    if (visible.length === 0) {
      slot.innerHTML = `<div class="wiz-har-empty">No cards match the current filter.</div>`;
      return;
    }
    slot.innerHTML = visible.map(c => artTileHtml(c)).join('');
    bindGrid(slot);
  }

  function visibleCards() {
    return local.cards.filter(c => {
      if (local.filter.rarity !== 'all' && c.rarity !== local.filter.rarity) return false;
      const dec = c.decision || null;
      if (local.filter.decision === 'pending' && dec !== null) return false;
      if (local.filter.decision === 'approve' && dec !== 'approve') return false;
      if (local.filter.decision === 'reject'  && dec !== 'reject')  return false;
      if (local.filter.decision === 'regen'   && dec !== 'regen')   return false;
      return true;
    });
  }

  function artTileHtml(c) {
    const dec = c.decision || '';
    const rar = c.rarity || '';
    // TODO: replace placeholder once GET /api/wizard/human_art_review/art/<card_id> exists.
    const artHtml = c.art_url
      ? `<img src="${escAttr(c.art_url)}" alt="Art for ${escAttr(c.name || '')}" loading="lazy">`
      : `<div class="wiz-har-art-placeholder">
           <span class="wiz-har-art-placeholder-icon">&#x1F5BC;</span>
           <span>Art not yet available</span>
         </div>`;
    return `
      <article class="wiz-har-card decision-${escAttr(dec)}" data-card-id="${escAttr(c.id)}">
        <div class="wiz-har-art-frame">${artHtml}</div>
        <div class="wiz-har-card-body">
          <div class="wiz-har-card-name">
            <span>${escHtml(c.name || '(unnamed)')}</span>
            <span class="wiz-har-rarity ${escAttr(rar)}">${escHtml(rar)}</span>
          </div>
          <div class="wiz-har-controls">
            <button type="button" class="wiz-har-btn-approve${dec==='approve'?' active':''}"
                    data-action="approve">Approve</button>
            <button type="button" class="wiz-har-btn-regen${dec==='regen'?' active':''}"
                    data-action="regen" title="Mark for art regeneration">Regen</button>
            <button type="button" class="wiz-har-btn-reject${dec==='reject'?' active':''}"
                    data-action="reject">Reject</button>
          </div>
          <textarea class="wiz-har-notes" data-role="har-notes"
                    placeholder="Optional notes…" rows="2">${escHtml(c.notes || '')}</textarea>
        </div>
      </article>
    `;
  }

  function bindGrid(slot) {
    slot.querySelectorAll('.wiz-har-card').forEach(card => {
      const id = card.dataset.cardId;
      card.querySelectorAll('[data-action]').forEach(btn => {
        btn.onclick = () => onDecision(id, btn.dataset.action, card);
      });
      const notes = card.querySelector('[data-role="har-notes"]');
      if (notes) notes.oninput = () => {
        updateCard(id, { notes: notes.value, _local_edit: true });
      };
    });
  }

  // ---------------------------------------------------------------------------
  // Decision handlers
  // TODO: wire POST /api/wizard/human_art_review/decision
  //   Body: { card_id, decision: 'approve'|'reject'|'regen', notes }
  // ---------------------------------------------------------------------------

  function onDecision(id, action, cardEl) {
    if (local.locked) return;
    const c = local.cards.find(x => x.id === id);
    const newDec = c && c.decision === action ? null : action;
    updateCard(id, { decision: newDec, _local_edit: true });

    if (cardEl) {
      cardEl.className = `wiz-har-card decision-${newDec || ''}`;
      cardEl.querySelectorAll('[data-action]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.action === newDec);
      });
    }

    // TODO: POST /api/wizard/human_art_review/decision
    const notes = cardEl && cardEl.querySelector('[data-role="har-notes"]');
    W.postJSON('/api/wizard/human_art_review/decision', {
      card_id: id,
      decision: newDec,
      notes: notes ? notes.value : '',
    }).catch(() => {});

    const root = bodyRoot();
    if (root) paintSummary(root, W.getState());
  }

  function onApproveAll(root) {
    if (local.locked) return;
    if (!confirm(`Approve all ${local.cards.length} cards' art?`)) return;
    local.cards.forEach(c => { c.decision = 'approve'; c._local_edit = true; });
    paintSummary(root, W.getState());
    paintGrid(root, W.getState());
    // TODO: POST /api/wizard/human_art_review/decision with bulk payload
    W.postJSON('/api/wizard/human_art_review/decision', {
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
  // Footer
  // ---------------------------------------------------------------------------

  function paintFooter(footer, state) {
    if (!footer) return;
    const isLatest = !state || state.latestTabId === STAGE_ID;
    const isPaused = local.stageStatus === 'paused_for_review';
    const isCompleted = local.stageStatus === 'completed';
    const next = W.nextStageEntryAfter(STAGE_ID);
    const nextName = next ? next.name : 'Next step';

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Art review is in the past — pipeline has moved on.</span>`;
    } else if (isCompleted) {
      html = `<span class="wiz-footer-note">Art review complete. Engine is on ${escHtml(nextName)}.</span>`;
    } else if (!isPaused) {
      html = `<span class="wiz-footer-note">Waiting for this stage to reach the review pause…</span>`;
    } else {
      html = `
        <button type="button" class="wiz-btn-primary" data-role="har-next-step"
                ${local.locked ? 'disabled' : ''}>
          Next step: ${escHtml(nextName)}
        </button>
        <span class="wiz-footer-note">Review art above, then advance when ready.</span>
      `;
    }

    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
    }
    const btn = footer.querySelector('[data-role="har-next-step"]');
    if (btn) btn.onclick = onAdvance;
  }

  async function onAdvance() {
    if (local.locked) return;
    setLocked(true);
    const root = bodyRoot();
    const footer = getFooter(root);
    const btn = footer && footer.querySelector('[data-role="har-next-step"]');
    const orig = btn ? btn.textContent : '';
    if (btn) btn.textContent = 'Advancing…';
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
    root.classList.toggle('wiz-har-locked', !!locked);
    const sel = [
      '.wiz-har-btn-approve',
      '.wiz-har-btn-reject',
      '.wiz-har-btn-regen',
      '.wiz-har-notes',
      '[data-role="har-approve-all"]',
      '[data-role="har-filter-rarity"]',
      '[data-role="har-filter-decision"]',
    ].join(',');
    root.querySelectorAll(sel).forEach(el => { el.disabled = !!locked; });
    const footerBtn = root.querySelector('[data-role="har-next-step"]');
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
