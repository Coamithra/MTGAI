/**
 * Wizard Human Card Review tab — per-card text review gate.
 *
 * Stage: human_card_review (REVIEW pause gate — review_mode = 'human').
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
 *   GET  /api/wizard/human_card_review/state   → { cards[], approved, flagged, rejected }
 *   POST /api/wizard/human_card_review/decision → { card_id, decision: 'approve'|'reject'|'flag', notes }
 * Both are TODO — the tab degrades gracefully with zero backend.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'human_card_review';

  // One-time scoped styles injected lazily.
  const STYLE_ID = 'wiz-' + STAGE_ID + '-styles';

  const local = {
    initialized: false,
    cards: [],          // [{id, name, mana_cost, type_line, oracle_text, power, toughness, rarity, colors, decision, notes}]
    hasContent: false,
    stageStatus: 'pending',
    locked: false,
    filter: { rarity: 'all', color: 'all', decision: 'all' },
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ---------------------------------------------------------------------------
  // Styles (injected once, scoped to wiz-hcr-*)
  // ---------------------------------------------------------------------------

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      /* ---- Human Card Review tab scoped styles ---- */
      .wiz-hcr-summary { margin-bottom: 0.75rem; }
      .wiz-hcr-counts {
        display: flex; gap: 1.25rem; flex-wrap: wrap;
        font-size: 0.82rem; color: #aaa; margin-bottom: 0.5rem;
      }
      .wiz-hcr-counts .wiz-hcr-count-chip {
        display: flex; align-items: center; gap: 0.3rem;
      }
      .wiz-hcr-count-chip .chip-val {
        font-variant-numeric: tabular-nums; font-weight: 600; color: #e0e0e0;
      }
      .wiz-hcr-count-chip.approved .chip-val  { color: #00d4aa; }
      .wiz-hcr-count-chip.rejected .chip-val  { color: #ff4757; }
      .wiz-hcr-count-chip.flagged  .chip-val  { color: #ffa502; }

      .wiz-hcr-filters {
        display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center;
        margin-bottom: 0.85rem;
      }
      .wiz-hcr-filters label {
        font-size: 0.75rem; color: #888; display: flex; align-items: center; gap: 0.3rem;
      }
      .wiz-hcr-filters select {
        padding: 0.25rem 0.5rem;
        background: var(--bg-primary, #1a1a2e);
        border: 1px solid #333;
        border-radius: 5px;
        color: #e0e0e0;
        font-size: 0.78rem;
        font-family: inherit;
      }
      .wiz-hcr-filters select:focus { outline: none; border-color: #4a9eff; }
      .wiz-hcr-approve-all-row {
        display: flex; justify-content: flex-end; margin-bottom: 0.5rem;
      }

      .wiz-hcr-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
        gap: 0.85rem;
      }
      .wiz-hcr-empty {
        color: #666; font-style: italic; font-size: 0.85rem;
        grid-column: 1 / -1; padding: 1.5rem 0;
      }

      .wiz-hcr-card {
        background: #0f1729;
        border: 1px solid #1f2540;
        border-radius: 8px;
        padding: 0.85rem 0.9rem;
        display: flex; flex-direction: column; gap: 0.5rem;
        transition: border-color 0.15s;
      }
      .wiz-hcr-card.decision-approve { border-color: #00d4aa55; }
      .wiz-hcr-card.decision-reject  { border-color: #ff475755; }
      .wiz-hcr-card.decision-flag    { border-color: #ffa50255; }

      .wiz-hcr-card-name {
        font-weight: 700; font-size: 0.95rem; color: #e0e0e0;
        display: flex; justify-content: space-between; align-items: baseline; gap: 0.4rem;
      }
      .wiz-hcr-mana { font-size: 0.82rem; color: #aaa; flex-shrink: 0; }
      .wiz-hcr-type { font-size: 0.75rem; color: #888; font-style: italic; }
      .wiz-hcr-rarity {
        font-size: 0.65rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.06em; padding: 1px 5px; border-radius: 3px;
        background: #1a1a2e; color: #aaa; align-self: flex-start;
      }
      .wiz-hcr-rarity.C { color: #aaa; }
      .wiz-hcr-rarity.U { color: #8cbfff; }
      .wiz-hcr-rarity.R { color: #f5a623; }
      .wiz-hcr-rarity.M { color: #e94560; }

      .wiz-hcr-oracle {
        font-size: 0.8rem; color: #ccc; line-height: 1.5;
        background: #16213e; border-radius: 5px;
        padding: 0.45rem 0.6rem; min-height: 3.5rem;
      }
      .wiz-hcr-pt { font-size: 0.8rem; color: #aaa; text-align: right; }

      .wiz-hcr-controls {
        display: flex; gap: 0.35rem; flex-wrap: wrap; margin-top: 0.15rem;
      }
      .wiz-hcr-btn-approve, .wiz-hcr-btn-reject, .wiz-hcr-btn-flag {
        flex: 1;
        padding: 0.3rem 0.5rem;
        border-radius: 5px;
        font-size: 0.75rem; font-weight: 600;
        cursor: pointer; font-family: inherit;
        border: 1px solid transparent;
        transition: background 0.12s, border-color 0.12s;
      }
      .wiz-hcr-btn-approve {
        background: transparent; border-color: #00d4aa44; color: #00d4aa;
      }
      .wiz-hcr-btn-approve:hover { background: #00d4aa18; }
      .wiz-hcr-btn-approve.active { background: #00d4aa22; border-color: #00d4aa; }

      .wiz-hcr-btn-reject {
        background: transparent; border-color: #ff475744; color: #ff4757;
      }
      .wiz-hcr-btn-reject:hover { background: #ff475718; }
      .wiz-hcr-btn-reject.active { background: #ff475722; border-color: #ff4757; }

      .wiz-hcr-btn-flag {
        background: transparent; border-color: #ffa50244; color: #ffa502;
      }
      .wiz-hcr-btn-flag:hover { background: #ffa50218; }
      .wiz-hcr-btn-flag.active { background: #ffa50222; border-color: #ffa502; }

      .wiz-hcr-notes {
        width: 100%; box-sizing: border-box;
        padding: 0.3rem 0.5rem;
        background: var(--bg-primary, #1a1a2e);
        border: 1px solid #2a2f55;
        border-radius: 5px;
        color: #ccc; font-size: 0.75rem; font-family: inherit;
        resize: vertical; min-height: 2.5rem;
      }
      .wiz-hcr-notes:focus { outline: none; border-color: #4a9eff; }

      /* Form lock */
      .wiz-hcr-locked { opacity: 0.85; }
      .wiz-hcr-locked button:disabled,
      .wiz-hcr-locked textarea:disabled,
      .wiz-hcr-locked select:disabled {
        cursor: not-allowed;
      }
    `;
    document.head.appendChild(style);
  }

  // ---------------------------------------------------------------------------
  // Top-level render (called by wizard_stage.js shell)
  // ---------------------------------------------------------------------------

  function render({ root, state, stage, content, footer }) {
    injectStyles();

    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      bootstrap(root, state).catch(err => {
        W.toast('Failed to load card review state: ' + err.message, 'error');
        const slot = root.querySelector('[data-role="hcr-grid"]');
        if (slot) slot.innerHTML = `<div class="wiz-hcr-empty">Could not load cards — is a project open?</div>`;
      });
      paintFooter(footer, state);
      return;
    }

    // Idempotent re-render: keep the user's in-progress decisions; just
    // refresh the status-sensitive footer and lock state.
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
        W.toast('Failed to refresh card review state: ' + err.message, 'error')
      );
      return;
    }

    paintFooter(footer, state);
    setLocked(local.locked);
  }

  function mountShellHtml() {
    return `
      <div data-role="hcr-summary"></div>
      <div data-role="hcr-filters"></div>
      <div class="wiz-hcr-grid" data-role="hcr-grid">
        <div class="wiz-hcr-empty">Loading cards…</div>
      </div>
    `;
  }

  // ---------------------------------------------------------------------------
  // Bootstrap — fetch live state from server
  // TODO: implement GET /api/wizard/human_card_review/state
  //   Response shape: { cards: CardItem[], has_content: bool, stage_status: str }
  //   CardItem: { id, name, mana_cost, type_line, oracle_text, power, toughness,
  //               rarity, colors, decision: 'approve'|'reject'|'flag'|null, notes: str }
  // ---------------------------------------------------------------------------

  async function bootstrap(root, state) {
    let data;
    try {
      const resp = await fetch('/api/wizard/human_card_review/state');
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        // No backend yet — degrade gracefully.
        if (resp.status === 404 || resp.status === 405) {
          data = { cards: [], has_content: false };
        } else {
          throw new Error(err.error || `HTTP ${resp.status}`);
        }
      } else {
        data = await resp.json();
      }
    } catch (fetchErr) {
      // Network error or truly missing endpoint — show placeholder.
      data = { cards: [], has_content: false };
    }

    // Merge server decisions into any local decisions the user already made
    // this session (preserve-on-rerender).
    const incoming = Array.isArray(data.cards) ? data.cards : [];
    if (local.cards.length === 0) {
      local.cards = incoming;
    } else {
      // Merge: keep local decision/notes where the user has already acted.
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
    const slot = root.querySelector('[data-role="hcr-summary"]');
    if (!slot) return;
    const total = local.cards.length;
    const approved = local.cards.filter(c => c.decision === 'approve').length;
    const rejected = local.cards.filter(c => c.decision === 'reject').length;
    const flagged  = local.cards.filter(c => c.decision === 'flag').length;
    const pending  = total - approved - rejected - flagged;

    slot.innerHTML = `
      <div class="wiz-hcr-summary">
        <div class="wiz-theme-section-header-row" style="margin-bottom:0.5rem">
          <h3 style="margin:0">Card Review</h3>
        </div>
        <div class="wiz-hcr-counts">
          <span class="wiz-hcr-count-chip">
            <span class="chip-val">${total}</span> total
          </span>
          <span class="wiz-hcr-count-chip approved">
            <span class="chip-val">${approved}</span> approved
          </span>
          <span class="wiz-hcr-count-chip rejected">
            <span class="chip-val">${rejected}</span> rejected
          </span>
          <span class="wiz-hcr-count-chip flagged">
            <span class="chip-val">${flagged}</span> flagged
          </span>
          <span class="wiz-hcr-count-chip">
            <span class="chip-val">${pending}</span> pending
          </span>
        </div>
        ${total > 0 ? `
        <div class="wiz-hcr-approve-all-row">
          <button type="button" class="wiz-btn-secondary" data-role="hcr-approve-all"
                  title="Mark every card approved">
            Approve all
          </button>
        </div>` : ''}
      </div>
    `;
    const btn = slot.querySelector('[data-role="hcr-approve-all"]');
    if (btn) btn.onclick = () => onApproveAll(root);
  }

  // ---------------------------------------------------------------------------
  // Filters
  // ---------------------------------------------------------------------------

  function paintFilters(root) {
    const slot = root.querySelector('[data-role="hcr-filters"]');
    if (!slot) return;
    if (!local.hasContent) { slot.innerHTML = ''; return; }
    slot.innerHTML = `
      <div class="wiz-hcr-filters">
        <label>Rarity
          <select data-role="hcr-filter-rarity">
            <option value="all" ${local.filter.rarity==='all'?'selected':''}>All</option>
            <option value="C"   ${local.filter.rarity==='C'?'selected':''}>Common</option>
            <option value="U"   ${local.filter.rarity==='U'?'selected':''}>Uncommon</option>
            <option value="R"   ${local.filter.rarity==='R'?'selected':''}>Rare</option>
            <option value="M"   ${local.filter.rarity==='M'?'selected':''}>Mythic</option>
          </select>
        </label>
        <label>Decision
          <select data-role="hcr-filter-decision">
            <option value="all"     ${local.filter.decision==='all'?'selected':''}>All</option>
            <option value="pending" ${local.filter.decision==='pending'?'selected':''}>Pending</option>
            <option value="approve" ${local.filter.decision==='approve'?'selected':''}>Approved</option>
            <option value="reject"  ${local.filter.decision==='reject'?'selected':''}>Rejected</option>
            <option value="flag"    ${local.filter.decision==='flag'?'selected':''}>Flagged</option>
          </select>
        </label>
      </div>
    `;
    const rarSel = slot.querySelector('[data-role="hcr-filter-rarity"]');
    const decSel = slot.querySelector('[data-role="hcr-filter-decision"]');
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
    const slot = root && root.querySelector('[data-role="hcr-grid"]');
    if (!slot) return;
    if (!local.hasContent) {
      const generating = local.stageStatus === 'running' || local.locked;
      slot.innerHTML = `<div class="wiz-hcr-empty">${
        generating
          ? 'Cards are being generated — check back once the generation stage completes.'
          : 'No cards to review yet. Cards will appear here once the generation stage has run.'
      }</div>`;
      return;
    }
    const visible = visibleCards();
    if (visible.length === 0) {
      slot.innerHTML = `<div class="wiz-hcr-empty">No cards match the current filter.</div>`;
      return;
    }
    slot.innerHTML = visible.map(c => cardTileHtml(c)).join('');
    bindGrid(slot);
  }

  function visibleCards() {
    return local.cards.filter(c => {
      if (local.filter.rarity !== 'all' && c.rarity !== local.filter.rarity) return false;
      const dec = c.decision || null;
      if (local.filter.decision === 'pending' && dec !== null) return false;
      if (local.filter.decision === 'approve' && dec !== 'approve') return false;
      if (local.filter.decision === 'reject'  && dec !== 'reject')  return false;
      if (local.filter.decision === 'flag'    && dec !== 'flag')    return false;
      return true;
    });
  }

  function cardTileHtml(c) {
    const dec = c.decision || '';
    const rar = c.rarity || '';
    const pt = (c.power != null && c.toughness != null) ? `${escHtml(c.power)}/${escHtml(c.toughness)}` : '';
    return `
      <article class="wiz-hcr-card decision-${escAttr(dec)}" data-card-id="${escAttr(c.id)}">
        <div class="wiz-hcr-card-name">
          <span>${escHtml(c.name || '(unnamed)')}</span>
          <span class="wiz-hcr-mana">${escHtml(c.mana_cost || '')}</span>
        </div>
        <div style="display:flex;align-items:center;gap:0.4rem">
          <span class="wiz-hcr-type">${escHtml(c.type_line || '')}</span>
          <span class="wiz-hcr-rarity ${escAttr(rar)}">${escHtml(rar)}</span>
        </div>
        <div class="wiz-hcr-oracle">${escHtml(c.oracle_text || '')}</div>
        ${pt ? `<div class="wiz-hcr-pt">${pt}</div>` : ''}
        <div class="wiz-hcr-controls">
          <button type="button" class="wiz-hcr-btn-approve${dec==='approve'?' active':''}"
                  data-action="approve">Approve</button>
          <button type="button" class="wiz-hcr-btn-flag${dec==='flag'?' active':''}"
                  data-action="flag">Flag</button>
          <button type="button" class="wiz-hcr-btn-reject${dec==='reject'?' active':''}"
                  data-action="reject">Reject</button>
        </div>
        <textarea class="wiz-hcr-notes" data-role="hcr-notes"
                  placeholder="Optional notes…" rows="2">${escHtml(c.notes || '')}</textarea>
      </article>
    `;
  }

  function bindGrid(slot) {
    slot.querySelectorAll('.wiz-hcr-card').forEach(card => {
      const id = card.dataset.cardId;
      const btns = card.querySelectorAll('[data-action]');
      btns.forEach(btn => {
        btn.onclick = () => onDecision(id, btn.dataset.action, card);
      });
      const notes = card.querySelector('[data-role="hcr-notes"]');
      if (notes) notes.oninput = () => {
        updateCard(id, { notes: notes.value, _local_edit: true });
        // TODO: POST /api/wizard/human_card_review/decision on blur for notes too
      };
    });
  }

  // ---------------------------------------------------------------------------
  // Decision handlers
  // TODO: wire POST /api/wizard/human_card_review/decision
  //   Body: { card_id, decision: 'approve'|'reject'|'flag', notes }
  // ---------------------------------------------------------------------------

  function onDecision(id, action, cardEl) {
    if (local.locked) return;
    // Toggle off if already active.
    const c = local.cards.find(x => x.id === id);
    const newDec = c && c.decision === action ? null : action;
    updateCard(id, { decision: newDec, _local_edit: true });

    // Optimistic DOM update — no full repaint so user's scroll position holds.
    if (cardEl) {
      cardEl.className = `wiz-hcr-card decision-${newDec || ''}`;
      cardEl.querySelectorAll('[data-action]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.action === newDec);
      });
    }

    // Persist to server.
    // TODO: POST /api/wizard/human_card_review/decision
    const notes = cardEl && cardEl.querySelector('[data-role="hcr-notes"]');
    W.postJSON('/api/wizard/human_card_review/decision', {
      card_id: id,
      decision: newDec,
      notes: notes ? notes.value : '',
    }).catch(() => { /* no-op: decision is held in local state */ });

    // Refresh summary counts.
    const root = bodyRoot();
    if (root) paintSummary(root, W.getState());
  }

  function onApproveAll(root) {
    if (local.locked) return;
    if (!confirm(`Approve all ${local.cards.length} cards?`)) return;
    local.cards.forEach(c => { c.decision = 'approve'; c._local_edit = true; });
    paintSummary(root, W.getState());
    paintGrid(root, W.getState());
    // TODO: POST /api/wizard/human_card_review/decision with bulk payload
    W.postJSON('/api/wizard/human_card_review/decision', {
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
  // Footer — "Next step: <name>" when paused_for_review (§1)
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
      html = `<span class="wiz-footer-note">Card review is in the past — pipeline has moved on.</span>`;
    } else if (isCompleted) {
      html = `<span class="wiz-footer-note">Card review complete. Engine is on ${escHtml(nextName)}.</span>`;
    } else if (!isPaused) {
      html = `<span class="wiz-footer-note">Waiting for this stage to reach the review pause…</span>`;
    } else {
      html = `
        <button type="button" class="wiz-btn-primary" data-role="hcr-next-step"
                ${local.locked ? 'disabled' : ''}>
          Next step: ${escHtml(nextName)}
        </button>
        <span class="wiz-footer-note">Review cards above, then advance when ready.</span>
      `;
    }

    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
    }
    const btn = footer.querySelector('[data-role="hcr-next-step"]');
    if (btn) btn.onclick = onAdvance;
  }

  async function onAdvance() {
    if (local.locked) return;
    setLocked(true);
    const root = bodyRoot();
    const footer = getFooter(root);
    const btn = footer && footer.querySelector('[data-role="hcr-next-step"]');
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
    root.classList.toggle('wiz-hcr-locked', !!locked);
    const sel = [
      '.wiz-hcr-btn-approve',
      '.wiz-hcr-btn-reject',
      '.wiz-hcr-btn-flag',
      '.wiz-hcr-notes',
      '[data-role="hcr-approve-all"]',
      '[data-role="hcr-filter-rarity"]',
      '[data-role="hcr-filter-decision"]',
    ].join(',');
    root.querySelectorAll(sel).forEach(el => { el.disabled = !!locked; });
    const footerBtn = root.querySelector('[data-role="hcr-next-step"]');
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

  const escHtml = W.escHtml;
  const escAttr = W.escAttr;
})();
