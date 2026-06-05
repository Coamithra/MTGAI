/**
 * Wizard AI Design Review tab — per-card review grid with stamps, a live
 * council, and manual approve / revise / regenerate.
 *
 * Registers via ``W.registerStageRenderer('ai_review', ...)`` so the standard
 * wizard_stage.js shell owns the header (status pill, break-point toggle,
 * Edit-cascade button); this module owns the body + footer.
 *
 * What it shows (matches the card spec):
 *  - The full set of reviewable cards as tiles, distinguishing reviewed cards
 *    (a green ✓ "approved" stamp or a red ✗ "rejected" stamp + reddened tile +
 *    a short rejection reason) from to-be-reviewed cards (a muted "to review"
 *    tag, dimmed).
 *  - A live council panel while a card is under review — 👍/👎 thumbs per
 *    reviewer, round by round, mirroring the mechanics council.
 *  - A "✎ Tweaked by AI" mark on any card the review revised in place, with
 *    an always-visible per-field before→after of what changed (the ``changes``
 *    tile field; a bare mark when no field-level diff is available).
 *  - A per-card submenu (⋯): Approve / Revise… (inline textbox → in-place LLM
 *    revision, executed immediately, re-opens for another round) / Regenerate
 *    (flags the slot back to Card Generation).
 *
 * Backend:
 *  - ``GET  /api/wizard/ai_review/state`` → { cards: Tile[], has_content,
 *    summary, ...stage_state_base }. A Tile carries the card display fields +
 *    {reviewed, verdict, issues, card_was_changed, changes:[{field,label,
 *    before,after}], review_tier, council, flagged,
 *    effective:{verdict:"approved"|"rejected"|"pending", reason, source}}.
 *  - ``POST /api/wizard/ai_review/{approve,revise,regenerate}`` → { tile }.
 *  - SSE: ai_review_reset / ai_review_card_start / ai_review_council /
 *    ai_review_card_done (routed here by wizard.js → W.onAiReviewStream).
 *
 * Instance-aware: ai_review is a re-entrant loop stage (it can appear as
 * ``ai_review.2``), so per-tab state lives in a Map keyed by ``tab.id``, exactly
 * like card_gen / conformance.
 *
 * Conventions: §1 footer (advance), §3 form lock, §7 W.runAiAction for the
 * manual actions, §8 status pill (shell), §9 stop-after toggle (shell).
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'ai_review';
  const escHtml = W.escHtml;
  const escAttr = W.escAttr;

  // -------------------------------------------------------------------------
  // Scoped styles (injected once)
  // -------------------------------------------------------------------------

  (function injectStyles() {
    if (document.getElementById('wiz-ai-review-styles')) return;
    const s = document.createElement('style');
    s.id = 'wiz-ai-review-styles';
    s.textContent = `
      .wiz-ar-summary-bar {
        display: flex; flex-wrap: wrap; gap: 1.1rem; align-items: center;
        padding: 0.7rem 0.95rem; background: #0f1729; border: 1px solid #1f2540;
        border-radius: 6px; margin-bottom: 1rem;
      }
      .wiz-ar-stat { font-size: 0.88rem; color: #9aa3b8; }
      .wiz-ar-stat strong { color: #e2e8f0; font-variant-numeric: tabular-nums; }
      .wiz-ar-filter-bar { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.85rem; }
      .wiz-ar-filter-btn {
        font-size: 0.78rem; padding: 0.25rem 0.7rem; border-radius: 4px; cursor: pointer;
        border: 1px solid #2d3348; background: #1e2130; color: #9aa3b8;
      }
      .wiz-ar-filter-btn.active { background: #4f46e5; color: #fff; border-color: #4f46e5; }
      .wiz-ar-grid {
        display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
        gap: 0.7rem;
      }
      .wiz-ar-card {
        position: relative; background: #0f1729; border: 1px solid #1f2540;
        border-radius: 6px; padding: 0.65rem 0.7rem 0.55rem; font-size: 0.78rem;
        display: flex; flex-direction: column; gap: 0.28rem;
      }
      .wiz-ar-card.approved { border-color: #2e7d52; }
      .wiz-ar-card.rejected { border-color: #8a3030; background: #1d1012; }
      .wiz-ar-card.pending { opacity: 0.72; }
      .wiz-ar-card.reviewing { border-color: #58a6ff; }
      /* Corner stamp */
      .wiz-ar-stamp {
        position: absolute; top: 0.4rem; right: 0.4rem; width: 1.5rem; height: 1.5rem;
        border-radius: 50%; display: flex; align-items: center; justify-content: center;
        font-size: 0.95rem; font-weight: 800; line-height: 1;
      }
      .wiz-ar-stamp.approved { background: #0d3320; color: #4ade80; border: 1px solid #2e7d52; }
      .wiz-ar-stamp.rejected { background: #3a0c0c; color: #f87171; border: 1px solid #8a3030; }
      .wiz-ar-card-name { font-weight: 700; font-size: 0.86rem; color: #e0e0e0; line-height: 1.2; padding-right: 1.8rem; }
      .wiz-ar-card-cost { font-size: 0.74rem; color: #aaa; font-family: monospace; }
      .wiz-ar-card-type { font-size: 0.72rem; color: #8b949e; border-bottom: 1px solid #1a2540; padding-bottom: 0.22rem; }
      .wiz-ar-card-text { color: #ccc; font-size: 0.74rem; line-height: 1.4; flex: 1 1 auto; white-space: pre-wrap; }
      .wiz-ar-card-pt { font-size: 0.74rem; font-weight: 700; color: #e0e0e0; text-align: right; }
      .wiz-ar-card-rarity {
        font-size: 0.62rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
        padding: 1px 5px; border-radius: 3px; align-self: flex-start;
      }
      .wiz-ar-card-rarity.mythic { background: #c8732220; color: #c87322; border: 1px solid #c8732240; }
      .wiz-ar-card-rarity.rare { background: #d4af3720; color: #d4af37; border: 1px solid #d4af3740; }
      .wiz-ar-card-rarity.uncommon { background: #6c8ebf20; color: #6c8ebf; border: 1px solid #6c8ebf40; }
      .wiz-ar-card-rarity.common { background: #33333320; color: #888; border: 1px solid #33333350; }
      .wiz-ar-pending-tag { font-size: 0.62rem; color: #8b949e; font-style: italic; align-self: flex-start; }
      /* Section label shared by the "why rejected" + "what changed" boxes */
      .wiz-ar-reject-label, .wiz-ar-changes-label {
        font-size: 0.62rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;
        color: #8b949e;
      }
      .wiz-ar-reject { display: flex; flex-direction: column; gap: 0.18rem; margin-top: 0.1rem; }
      .wiz-ar-reject-reason {
        font-size: 0.72rem; color: #f8b4b4; background: #3a0c0c40; border-left: 2px solid #8a3030;
        padding: 0.3rem 0.45rem; border-radius: 0 4px 4px 0; line-height: 1.35; white-space: pre-wrap;
      }
      /* Issues list (collapsible details) */
      .wiz-ar-issues { margin: 0.2rem 0 0; padding: 0; list-style: none; }
      .wiz-ar-issues li { display: flex; gap: 0.4rem; padding: 0.2rem 0; font-size: 0.72rem; align-items: baseline; }
      .wiz-ar-sev { font-size: 0.62rem; font-weight: 700; padding: 0.05rem 0.3rem; border-radius: 3px; flex-shrink: 0; }
      .wiz-ar-sev.FAIL { background: #3a0c0c; color: #f87171; }
      .wiz-ar-sev.WARN { background: #3a2a00; color: #fbbf24; }
      .wiz-ar-details summary { cursor: pointer; font-size: 0.7rem; color: #8b949e; }
      /* "Tweaked by AI" mark + per-field what-changed diff */
      .wiz-ar-tweak { display: flex; flex-direction: column; gap: 0.28rem; margin-top: 0.1rem; }
      .wiz-ar-tweak-badge {
        font-size: 0.62rem; font-weight: 700; color: #c4b5fd; align-self: flex-start;
        background: #2a1f47; border: 1px solid #4c3a82; border-radius: 3px;
        padding: 0.1rem 0.42rem; display: inline-flex; align-items: center; gap: 0.28rem;
      }
      .wiz-ar-changes { margin: 0.15rem 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 0.3rem; }
      .wiz-ar-change { display: flex; flex-direction: column; gap: 0.1rem; font-size: 0.7rem; }
      .wiz-ar-change-field { color: #9aa3b8; font-weight: 700; }
      .wiz-ar-change-ba { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.3rem; line-height: 1.35; }
      .wiz-ar-change-before { color: #d49a9a; text-decoration: line-through; opacity: 0.85; white-space: pre-wrap; }
      .wiz-ar-change-arrow { color: #6e7681; }
      .wiz-ar-change-after { color: #9ece9e; white-space: pre-wrap; }
      /* Council panel (mirrors mechanics) */
      .wiz-ar-reviewing-badge {
        font-size: 0.62rem; font-weight: 700; color: #58a6ff; align-self: flex-start;
        display: inline-flex; align-items: center; gap: 0.3rem;
      }
      .wiz-ar-reviewing-badge::before {
        content: ''; width: 0.7rem; height: 0.7rem; border-radius: 50%;
        border: 2px solid #ffffff22; border-top-color: #58a6ff; display: inline-block;
        animation: wiz-ar-spin 0.7s linear infinite;
      }
      .wiz-ar-council { display: flex; flex-direction: column; gap: 0.25rem; margin-top: 0.1rem; }
      .wiz-ar-council-row { display: flex; align-items: center; gap: 0.4rem; font-size: 0.7rem; flex-wrap: wrap; }
      .wiz-ar-council-round { color: #8b949e; min-width: 4.2rem; }
      .wiz-ar-council-slots { display: inline-flex; gap: 0.15rem; }
      .wiz-ar-council-slot { width: 1.05rem; text-align: center; }
      .wiz-ar-council-slot.ok { color: #4ade80; }
      .wiz-ar-council-slot.revise { color: #fb923c; }
      .wiz-ar-council-slot.error { color: #6e7681; }
      .wiz-ar-council-slot.pending { color: #3a3f55; }
      .wiz-ar-council-slot.running { color: #58a6ff; animation: wiz-ar-pulse 1s ease-in-out infinite; }
      .wiz-ar-council-synth { color: #a78bfa; font-size: 0.66rem; }
      .wiz-ar-council-synth.running::after { content: '…'; }
      /* Submenu */
      .wiz-ar-actions { display: flex; align-items: center; justify-content: flex-end; gap: 0.3rem; margin-top: 0.15rem; position: relative; }
      .wiz-ar-menu-btn {
        background: #1e2130; border: 1px solid #2d3348; color: #c9d1d9; border-radius: 4px;
        font-size: 0.85rem; line-height: 1; padding: 0.2rem 0.5rem; cursor: pointer;
      }
      .wiz-ar-menu-btn:hover { background: #252a3a; }
      .wiz-ar-menu {
        position: absolute; right: 0; top: 1.7rem; z-index: 5; min-width: 9rem;
        background: #161a28; border: 1px solid #2d3348; border-radius: 6px;
        box-shadow: 0 6px 18px #0008; padding: 0.3rem; display: flex; flex-direction: column; gap: 0.15rem;
      }
      .wiz-ar-menu[hidden] { display: none; }
      .wiz-ar-menu button {
        text-align: left; background: none; border: none; color: #c9d1d9; font-size: 0.78rem;
        padding: 0.35rem 0.5rem; border-radius: 4px; cursor: pointer; width: 100%;
      }
      .wiz-ar-menu button:hover { background: #232838; }
      .wiz-ar-menu button.danger { color: #f87171; }
      .wiz-ar-revise-box { margin-top: 0.4rem; display: flex; flex-direction: column; gap: 0.35rem; }
      .wiz-ar-revise-box textarea {
        width: 100%; min-height: 3.2rem; resize: vertical; background: #11151f; color: #e0e0e0;
        border: 1px solid #2d3348; border-radius: 5px; padding: 0.4rem 0.5rem; font: inherit; font-size: 0.74rem;
      }
      .wiz-ar-revise-box textarea:focus { outline: none; border-color: #4a9eff; }
      .wiz-ar-revise-actions { display: flex; gap: 0.4rem; justify-content: flex-end; }
      .wiz-ar-btn-sm { font-size: 0.72rem; padding: 0.25rem 0.65rem; border-radius: 4px; cursor: pointer; border: 1px solid #2d3348; background: #1e2130; color: #c9d1d9; }
      .wiz-ar-btn-sm.primary { background: #4f46e5; border-color: #4f46e5; color: #fff; }
      .wiz-ar-empty { color: #6e7681; font-style: italic; padding: 2rem; text-align: center; }
      .wiz-ar-locked .wiz-ar-menu-btn, .wiz-ar-locked .wiz-ar-btn-sm, .wiz-ar-locked .wiz-ar-menu button { opacity: 0.5; cursor: not-allowed; }
      @keyframes wiz-ar-spin { to { transform: rotate(360deg); } }
      @keyframes wiz-ar-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
    `;
    document.head.appendChild(s);
  })();

  // -------------------------------------------------------------------------
  // Per-instance tab state, keyed by instance id (tab.id).
  //   cards     — Tile[] from /state, merged with live SSE updates
  //   byCn      — collector_number -> tile (in-place updates)
  //   council   — collector_number -> { size, maxRounds, steps:[...] } live panel
  //   reviewing — Set of collector_numbers currently under review
  //   reviseOpen — collector_number whose inline revise box is open (or null)
  // -------------------------------------------------------------------------
  const instances = new Map();
  function stateFor(instanceId) {
    let s = instances.get(instanceId);
    if (!s) {
      s = {
        initialized: false,
        stageStatus: 'pending',
        cards: [],
        byCn: {},
        council: {},
        reviewing: new Set(),
        summary: null,
        hasContent: false,
        bootstrapping: false,
        filter: 'all',
        reviseOpen: null,
        openMenu: null,
        locked: false,
      };
      instances.set(instanceId, s);
    }
    return s;
  }

  W.registerStageRenderer(STAGE_ID, render);

  // -------------------------------------------------------------------------
  // SSE bridge — wizard.js routes the ai_review_* events here. Each card-scoped
  // event carries a collector_number so it lands on ITS tile + ITS instance.
  // The events don't carry an instance id (review runs on the loop tip), so they
  // route to the tip tab; a non-tip instance reads its frozen verdicts from
  // /state. We update every mounted instance's matching tile defensively.
  // -------------------------------------------------------------------------
  W.onAiReviewStream = function (name, data) {
    data = data || {};
    instances.forEach((local, instanceId) => {
      const root = W.tabRoot(instanceId);
      if (name === 'ai_review_reset') {
        local.council = {};
        local.reviewing = new Set();
        if (root) paintGrid(root, local);
        return;
      }
      const cn = data.collector_number || (data.tile && data.tile.collector_number);
      if (name === 'ai_review_card_start') {
        local.reviewing.add(data.collector_number);
        local.council[data.collector_number] = { size: 1, maxRounds: 0, steps: [] };
        if (root) paintGrid(root, local);
      } else if (name === 'ai_review_council') {
        applyCouncil(local, cn, data.event || {});
        if (root) paintGrid(root, local);
      } else if (name === 'ai_review_card_done') {
        local.reviewing.delete(cn);
        delete local.council[cn];
        if (data.tile) mergeTile(local, data.tile);
        local.hasContent = local.cards.length > 0;
        if (root) { paintSummary(root, local); paintGrid(root, local); }
      }
    });
  };

  // Merge one streamed council ``event`` (mechanics-shaped) into a card's panel.
  function applyCouncil(local, cn, event) {
    if (!cn) return;
    // In-progress revision: the loop pushes the revised card body each round so the
    // tile updates live while still "Reviewing…" (the final stamped tile lands on
    // card_done). Mutate the existing tile in place (shared ref with local.cards).
    if (event.kind === 'card') {
      if (event.card) {
        const existing = local.byCn[cn];
        if (existing) Object.assign(existing, event.card);
        else mergeTile(local, Object.assign({ collector_number: cn }, event.card));
      }
      return;
    }
    const c = local.council[cn] || (local.council[cn] = { size: 1, maxRounds: 0, steps: [] });
    if (event.kind === 'round') {
      const verdicts = Array.isArray(event.verdicts) ? event.verdicts : [];
      // The independent panel (round 1 of a council tier) sizes the slot row.
      if (verdicts.length > c.size) c.size = verdicts.length;
      const existing = c.steps.find((s) => s.kind === 'round' && s.round === event.round);
      if (existing) {
        existing.verdicts = verdicts;
        if (event.synth) existing.synth = event.synth;
      } else {
        c.steps.push({ kind: 'round', round: event.round, verdicts, synth: event.synth || null });
      }
    }
  }

  function mergeTile(local, tile) {
    if (!tile || !tile.collector_number) return;
    W.streamUpsert(local.cards, tile, (t) => t.collector_number);
    local.byCn[tile.collector_number] = local.cards.find((t) => t.collector_number === tile.collector_number);
  }

  // -------------------------------------------------------------------------
  // Render lifecycle
  // -------------------------------------------------------------------------

  function render({ tab, root, state, stage, content, footer }) {
    const instanceId = (stage && stage.instance_id) || (tab && tab.id) || STAGE_ID;
    const local = stateFor(instanceId);

    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      W.bindRerunButton(root, stage);
      bindGrid(root, instanceId, local);
      bootstrap(root, state, local, instanceId).catch((err) => {
        W.toast('Failed to load AI review state: ' + err.message, 'error');
        paintGrid(root, local);
      });
      paintFooter(footer, state, local, instanceId);
      return;
    }

    const prevStatus = local.stageStatus;
    if (stage) local.stageStatus = stage.status;

    const justFinished =
      stage &&
      prevStatus !== local.stageStatus &&
      local.stageStatus !== 'pending' &&
      local.stageStatus !== 'running' &&
      !local.bootstrapping;
    if (justFinished) {
      local.bootstrapping = true;
      bootstrap(root, state, local, instanceId)
        .catch((err) => W.toast('Failed to refresh AI review state: ' + err.message, 'error'))
        .finally(() => { local.bootstrapping = false; });
    }
    W.bindRerunButton(root, stage);
    paintFooter(footer, state, local, instanceId);
    setLocked(root, local, local.locked);
  }

  function mountShellHtml() {
    return `
      ${W.rerunButtonHtml()}
      <div data-role="ar-summary"></div>
      <div data-role="ar-filter" class="wiz-ar-filter-bar"></div>
      <div data-role="ar-grid">
        <div class="wiz-ar-empty">Loading review results…</div>
      </div>
    `;
  }

  async function bootstrap(root, state, local, instanceId) {
    const data = await W.fetchStageState(STAGE_ID, { instance_id: instanceId });
    if (data) {
      local.cards = Array.isArray(data.cards) ? data.cards : [];
      local.byCn = {};
      local.cards.forEach((t) => { if (t.collector_number) local.byCn[t.collector_number] = t; });
      local.summary = data.summary || null;
      local.hasContent = local.cards.length > 0;
      if (data.stage_status) local.stageStatus = data.stage_status;
    }
    paintSummary(root, local);
    paintFilter(root, local);
    paintGrid(root, local);
    paintFooter(getFooter(root), state, local, instanceId);
  }

  // -------------------------------------------------------------------------
  // Summary bar + filter
  // -------------------------------------------------------------------------

  function paintSummary(root, local) {
    const slot = root && root.querySelector('[data-role="ar-summary"]');
    if (!slot) return;
    if (!local.hasContent) { slot.innerHTML = ''; return; }
    const s = local.summary || {};
    const total = s.total != null ? s.total : local.cards.length;
    const approved = s.approved != null ? s.approved : count(local, 'approved');
    const rejected = s.rejected != null ? s.rejected : count(local, 'rejected');
    const pending = s.pending != null ? s.pending : count(local, 'pending');
    const revised = s.revised != null ? s.revised : local.cards.filter((t) => t.card_was_changed).length;
    slot.innerHTML = `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">Review results</h3>
        <span class="wiz-ai-badge">AI</span>
      </div>
      <div class="wiz-ar-summary-bar">
        <span class="wiz-ar-stat"><strong>${escHtml(String(total))}</strong> cards</span>
        <span class="wiz-ar-stat"><strong>${escHtml(String(approved))}</strong> approved</span>
        <span class="wiz-ar-stat"><strong>${escHtml(String(rejected))}</strong> rejected</span>
        <span class="wiz-ar-stat"><strong>${escHtml(String(pending))}</strong> to review</span>
        <span class="wiz-ar-stat"><strong>${escHtml(String(revised))}</strong> revised by AI</span>
      </div>
    `;
  }

  function count(local, verdict) {
    return local.cards.filter((t) => effective(t).verdict === verdict).length;
  }

  function paintFilter(root, local) {
    const slot = root && root.querySelector('[data-role="ar-filter"]');
    if (!slot) return;
    if (!local.hasContent) { slot.innerHTML = ''; return; }
    const filters = [
      { id: 'all', label: 'All' },
      { id: 'approved', label: 'Approved' },
      { id: 'rejected', label: 'Rejected' },
      { id: 'pending', label: 'To review' },
    ];
    slot.innerHTML = filters
      .map((f) => `<button type="button" class="wiz-ar-filter-btn${local.filter === f.id ? ' active' : ''}" data-filter="${escAttr(f.id)}">${escHtml(f.label)}</button>`)
      .join('');
    slot.querySelectorAll('.wiz-ar-filter-btn').forEach((btn) => {
      btn.onclick = () => { local.filter = btn.dataset.filter; paintFilter(root, local); paintGrid(root, local); };
    });
  }

  // -------------------------------------------------------------------------
  // Card grid
  // -------------------------------------------------------------------------

  function paintGrid(root, local) {
    const slot = root && root.querySelector('[data-role="ar-grid"]');
    if (!slot) return;
    if (!local.hasContent) {
      const running = local.stageStatus === 'running';
      slot.innerHTML = `<div class="wiz-ar-empty">${running
        ? 'AI review is running — cards will be stamped as each is reviewed.'
        : 'No cards to review yet. AI review runs after card generation.'}</div>`;
      return;
    }
    const visible = local.cards.filter((t) => {
      if (local.filter === 'all') return true;
      return effective(t).verdict === local.filter;
    });
    if (!visible.length) {
      slot.innerHTML = `<div class="wiz-ar-empty">No cards match this filter.</div>`;
      return;
    }
    slot.innerHTML = `<div class="wiz-ar-grid">${visible.map((t) => tileHtml(t, local)).join('')}</div>`;
    setLocked(root, local, local.locked);
  }

  // The effective decision drives the stamp. The server-built tile (/state)
  // carries ``effective`` (with the persisted regen_reason as the "why"); the
  // live-streamed tile (ai_review_card_done) does not, so derive it here from the
  // verdict + issues so a freshly-rejected card still shows its reason before the
  // next /state reload.
  function effective(tile) {
    if (tile.effective) return tile.effective;
    if (!tile.reviewed) return { verdict: 'pending', reason: '' };
    if (tile.verdict === 'OK') return { verdict: 'approved', reason: '' };
    const issues = Array.isArray(tile.issues) ? tile.issues : [];
    const reason = issues.map((i) => i && i.description).filter(Boolean).join('; ');
    return { verdict: 'rejected', reason };
  }

  function tileHtml(tile, local) {
    const cn = tile.collector_number || '';
    const eff = effective(tile);
    const reviewing = local.reviewing.has(cn);
    const verdict = reviewing ? 'reviewing' : eff.verdict;
    const rarity = (tile.rarity || 'common').toLowerCase();
    const hasPt = tile.power != null && tile.toughness != null;
    const hasLoyalty = tile.loyalty != null;

    const stamp = verdict === 'approved'
      ? '<span class="wiz-ar-stamp approved" title="Approved">✓</span>'
      : verdict === 'rejected'
        ? '<span class="wiz-ar-stamp rejected" title="Rejected">✗</span>'
        : '';

    const reviewingBadge = reviewing ? '<span class="wiz-ar-reviewing-badge">Reviewing…</span>' : '';
    const councilPanel = reviewing ? councilPanelHtml(local.council[cn]) : '';
    const pendingTag = (!reviewing && verdict === 'pending') ? '<span class="wiz-ar-pending-tag">To review</span>' : '';
    const rejectReason = (verdict === 'rejected' && eff.reason)
      ? `<div class="wiz-ar-reject">
           <div class="wiz-ar-reject-label">Why rejected</div>
           <div class="wiz-ar-reject-reason">${escHtml(eff.reason)}</div>
         </div>` : '';

    const issues = Array.isArray(tile.issues) ? tile.issues : [];
    const issuesBlock = (!reviewing && issues.length)
      ? `<details class="wiz-ar-details"><summary>${issues.length} issue${issues.length !== 1 ? 's' : ''}</summary>
           <ul class="wiz-ar-issues">${issues.map((i) =>
             `<li><span class="wiz-ar-sev ${escAttr(i.severity || '')}">${escHtml(i.severity || '')}</span><span>${escHtml(i.description || '')}</span></li>`
           ).join('')}</ul></details>`
      : '';

    const tweakBlock = reviewing ? '' : tweakHtml(tile);

    const reviseBox = (local.reviseOpen === cn) ? reviseBoxHtml(cn) : '';
    const menu = reviewing ? '' : actionsHtml(cn, local);

    return `
      <article class="wiz-ar-card ${escAttr(verdict)}" data-cn="${escAttr(cn)}">
        ${stamp}
        <div class="wiz-ar-card-name">${escHtml(tile.name || '(unnamed)')}</div>
        ${tile.mana_cost ? `<div class="wiz-ar-card-cost">${escHtml(tile.mana_cost)}</div>` : ''}
        ${tile.type_line ? `<div class="wiz-ar-card-type">${escHtml(tile.type_line)}</div>` : ''}
        ${tile.oracle_text ? `<div class="wiz-ar-card-text">${escHtml(tile.oracle_text)}</div>` : ''}
        <div style="display:flex;justify-content:space-between;align-items:flex-end;gap:0.4rem">
          <span class="wiz-ar-card-rarity ${escAttr(rarity)}">${escHtml(rarity)}</span>
          ${hasPt ? `<span class="wiz-ar-card-pt">${escHtml(String(tile.power))}/${escHtml(String(tile.toughness))}</span>`
            : hasLoyalty ? `<span class="wiz-ar-card-pt">[${escHtml(String(tile.loyalty))}]</span>` : ''}
        </div>
        ${reviewingBadge}
        ${councilPanel}
        ${pendingTag}
        ${rejectReason}
        ${issuesBlock}
        ${tweakBlock}
        ${menu}
        ${reviseBox}
      </article>
    `;
  }

  // "Tweaked by AI" mark + the per-field before/after the review changed. The
  // mark shows whenever the review revised the card in place; the diff rows are
  // present only when the tile carries field-level changes (else just the mark,
  // per the card spec's "a 'tweaked' mark is also fine" fallback).
  function tweakHtml(tile) {
    if (!tile.card_was_changed) return '';
    const badge = '<span class="wiz-ar-tweak-badge" title="The AI review revised this card in place">✎ Tweaked by AI</span>';
    const changes = Array.isArray(tile.changes) ? tile.changes : [];
    if (!changes.length) return `<div class="wiz-ar-tweak">${badge}</div>`;
    const rows = changes.map((c) => `
      <li class="wiz-ar-change">
        <span class="wiz-ar-change-field">${escHtml(c.label || c.field || '')}</span>
        <span class="wiz-ar-change-ba">
          <span class="wiz-ar-change-before">${escHtml(c.before)}</span>
          <span class="wiz-ar-change-arrow">→</span>
          <span class="wiz-ar-change-after">${escHtml(c.after)}</span>
        </span>
      </li>`).join('');
    return `
      <div class="wiz-ar-tweak">
        ${badge}
        <div class="wiz-ar-changes-label">What changed (${changes.length})</div>
        <ul class="wiz-ar-changes">${rows}</ul>
      </div>`;
  }

  function actionsHtml(cn, local) {
    const open = local.openMenu === cn;
    return `
      <div class="wiz-ar-actions">
        <button type="button" class="wiz-ar-menu-btn" data-role="ar-menu-toggle" data-cn="${escAttr(cn)}" title="Review actions" aria-haspopup="true" aria-expanded="${open ? 'true' : 'false'}">⋯</button>
        <div class="wiz-ar-menu" data-role="ar-menu" data-cn="${escAttr(cn)}" ${open ? '' : 'hidden'}>
          <button type="button" data-action="approve" data-cn="${escAttr(cn)}">Approve</button>
          <button type="button" data-action="revise" data-cn="${escAttr(cn)}">Revise…</button>
          <button type="button" class="danger" data-action="regenerate" data-cn="${escAttr(cn)}">Regenerate</button>
        </div>
      </div>
    `;
  }

  function reviseBoxHtml(cn) {
    return `
      <div class="wiz-ar-revise-box" data-role="ar-revise" data-cn="${escAttr(cn)}">
        <textarea data-role="ar-revise-text" placeholder="Describe what to change (e.g. 'reduce the power to 2/2 and remove trample')…"></textarea>
        <div class="wiz-ar-revise-actions">
          <button type="button" class="wiz-ar-btn-sm" data-action="revise-cancel" data-cn="${escAttr(cn)}">Cancel</button>
          <button type="button" class="wiz-ar-btn-sm primary" data-action="revise-submit" data-cn="${escAttr(cn)}">Apply revision</button>
        </div>
      </div>
    `;
  }

  // Live council panel — mirrors wizard_mechanics.js councilRoundRowHtml.
  function councilPanelHtml(council) {
    if (!council || !Array.isArray(council.steps) || !council.steps.length) return '';
    const size = Math.max(1, Number(council.size) || 1);
    const rows = council.steps.map((step) => councilRowHtml(step, size, step === lastRound(council))).join('');
    return `<div class="wiz-ar-council">${rows}</div>`;
  }

  function lastRound(council) {
    for (let i = council.steps.length - 1; i >= 0; i--) {
      if (council.steps[i].kind === 'round') return council.steps[i];
    }
    return null;
  }

  function councilRowHtml(step, size, isActive) {
    const verdicts = Array.isArray(step.verdicts) ? step.verdicts : [];
    const runningSlot = (isActive && !step.synth && verdicts.length < size) ? verdicts.length : -1;
    const slots = [];
    for (let i = 0; i < size; i++) {
      const v = verdicts[i];
      let cls = 'pending', glyph = '·', title = 'Queued reviewer';
      if (v === 'ok') { cls = 'ok'; glyph = '👍'; title = 'Reviewer: looks good'; }
      else if (v === 'revise') { cls = 'revise'; glyph = '👎'; title = 'Reviewer: wants changes'; }
      else if (v === 'error') { cls = 'error'; glyph = '–'; title = 'Reviewer call failed'; }
      else if (i === runningSlot) { cls = 'running'; glyph = '⟳'; title = 'Reviewer is reading the card…'; }
      slots.push(`<span class="wiz-ar-council-slot ${cls}" title="${escAttr(title)}">${glyph}</span>`);
    }
    let synth = '';
    if (step.synth === 'running') synth = '<span class="wiz-ar-council-synth running">Combining feedback</span>';
    else if (step.synth === 'done') synth = '<span class="wiz-ar-council-synth">→ revised</span>';
    return `
      <div class="wiz-ar-council-row">
        <span class="wiz-ar-council-round">Round ${escHtml(String(Number(step.round) || 1))}</span>
        <span class="wiz-ar-council-slots">${slots.join('')}</span>
        ${synth}
      </div>
    `;
  }

  // -------------------------------------------------------------------------
  // Grid interactions (submenu, manual actions) — delegated click handler.
  // -------------------------------------------------------------------------

  function bindGrid(root, instanceId, local) {
    root.addEventListener('click', function (e) {
      const t = e.target;
      const toggle = t.closest && t.closest('[data-role="ar-menu-toggle"]');
      if (toggle) { e.stopPropagation(); toggleMenu(root, local, toggle.dataset.cn); return; }
      const actionBtn = t.closest && t.closest('[data-action]');
      if (actionBtn) {
        e.stopPropagation();
        handleAction(root, local, instanceId, actionBtn.dataset.action, actionBtn.dataset.cn);
        return;
      }
      // Click elsewhere closes any open menu.
      if (local.openMenu) { local.openMenu = null; paintGrid(root, local); }
    });
  }

  function toggleMenu(root, local, cn) {
    local.openMenu = local.openMenu === cn ? null : cn;
    paintGrid(root, local);
  }

  function handleAction(root, local, instanceId, action, cn) {
    if (local.locked) return;
    if (action === 'approve') { local.openMenu = null; doApprove(root, local, cn); }
    else if (action === 'revise') { local.openMenu = null; local.reviseOpen = cn; paintGrid(root, local); focusRevise(root, cn); }
    else if (action === 'revise-cancel') { local.reviseOpen = null; paintGrid(root, local); }
    else if (action === 'revise-submit') { doRevise(root, local, cn); }
    else if (action === 'regenerate') { local.openMenu = null; doRegenerate(root, local, cn); }
  }

  function focusRevise(root, cn) {
    const box = root.querySelector(`[data-role="ar-revise"][data-cn="${W.cssEsc ? W.cssEsc(cn) : cn}"] [data-role="ar-revise-text"]`);
    if (box) box.focus();
  }

  function applyTile(local, tile) {
    if (!tile || !tile.collector_number) return;
    mergeTile(local, tile);
  }

  function doApprove(root, local, cn) {
    W.runAiAction({
      isLocked: () => local.locked,
      setLocked: (l) => setLocked(root, local, l),
      busyLabel: 'Approving…',
      url: '/api/wizard/ai_review/approve',
      body: () => ({ collector_number: cn }),
      fallback: 'Approve failed',
      onResult: (data) => { applyTile(local, data.tile); refresh(root, local); W.toast('Card approved.', 'success'); },
    });
  }

  function doRevise(root, local, cn) {
    const ta = root.querySelector(`[data-role="ar-revise"][data-cn="${W.cssEsc ? W.cssEsc(cn) : cn}"] [data-role="ar-revise-text"]`);
    const instructions = (ta && ta.value || '').trim();
    if (!instructions) { W.toast('Describe what to change first.', 'error'); if (ta) ta.focus(); return; }
    W.runAiAction({
      isLocked: () => local.locked,
      setLocked: (l) => setLocked(root, local, l),
      busyLabel: 'Revising card…',
      url: '/api/wizard/ai_review/revise',
      body: () => ({ collector_number: cn, instructions }),
      fallback: 'Revision failed',
      onResult: (data) => {
        applyTile(local, data.tile);
        local.reviseOpen = null;  // revised → approved; user can re-open to revise again
        refresh(root, local);
        W.toast('Card revised.', 'success');
      },
    });
  }

  function doRegenerate(root, local, cn) {
    W.runAiAction({
      isLocked: () => local.locked,
      setLocked: (l) => setLocked(root, local, l),
      confirm: () => 'Regenerate this card from scratch? It will be rebuilt by Card Generation when the pipeline next runs that stage.',
      busyLabel: 'Flagging for regeneration…',
      url: '/api/wizard/ai_review/regenerate',
      body: () => ({ collector_number: cn }),
      fallback: 'Regenerate failed',
      onResult: (data) => { applyTile(local, data.tile); refresh(root, local); W.toast('Card flagged for regeneration.', 'warn'); },
    });
  }

  function refresh(root, local) {
    paintSummary(root, local);
    paintFilter(root, local);
    paintGrid(root, local);
  }

  // -------------------------------------------------------------------------
  // Footer (§1)
  // -------------------------------------------------------------------------

  function paintFooter(footer, state, local, instanceId) {
    if (!footer) return;
    const isLatest = !state || state.latestTabId === instanceId;
    const status = local.stageStatus;
    const next = W.nextStageEntryAfter(instanceId);
    const nextName = next ? next.name : 'the next stage';

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Review completed — results are read-only on a past tab.</span>`;
    } else if (status === 'paused_for_review') {
      html = `<button type="button" class="wiz-btn-primary" data-role="ar-advance">Next step: ${escHtml(nextName)}</button>`;
    } else if (status === 'running') {
      html = `<span class="wiz-footer-note">AI review is in progress…</span>`;
    } else if (status === 'failed') {
      html = `<span class="wiz-footer-note">Stage failed — see the error above; approve or revise a card to recover.</span>`;
    } else {
      html = `<span class="wiz-footer-note">Continue appears once review is ready for your sign-off.</span>`;
    }
    W.paintFooter(footer, html, { role: 'ar-advance', onClick: () => onAdvance(instanceId) });
  }

  function onAdvance(instanceId) {
    return W.advanceStage({ stageId: instanceId, btnRole: 'ar-advance', navigate: false });
  }

  // -------------------------------------------------------------------------
  // Form lock (§3)
  // -------------------------------------------------------------------------

  function aiBusy(local) {
    return local.locked || local.stageStatus === 'running';
  }

  function setLocked(root, local, locked) {
    local.locked = !!locked;
    W.setTabLocked(root, aiBusy(local), {
      lockClass: 'wiz-ar-locked',
      selectors: [
        '[data-role="ar-menu-toggle"]',
        '[data-role="ar-menu"] button',
        '.wiz-ar-btn-sm',
        '[data-role="ar-revise-text"]',
      ],
      footerSelector: '[data-role="ar-advance"]',
    });
  }

  // -------------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------------

  function getFooter(root) {
    return root && root.querySelector('[data-role="footer"]');
  }
})();
