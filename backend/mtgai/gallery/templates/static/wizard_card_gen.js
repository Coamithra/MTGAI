/**
 * Wizard Card Generation tab — live progress + rarity/colour grouped card grid.
 *
 * Registers via ``W.registerStageRenderer('card_gen', ...)`` so the standard
 * wizard_stage.js shell still owns the header (status pill, break-point
 * toggle, Edit-cascade button) and we paint the body + footer.
 *
 * Conventions:
 *   §1  one primary footer button when paused_for_review (bindNextStepButton
 *       pattern)
 *   §3  form lock during AI gen (read-only — no user-editable fields on this
 *       tab; lock suppresses any future action buttons)
 *   §6  past-tab edit cascade routes through wizard_stage.js / W.editFlow
 *   §8  status pill flows from stage state
 *   §9  Stop after this step — handled by wizard_stage.js
 *   §13 "Refresh AI…" section header button always rendered (recovery path
 *       for failed/empty runs)
 *
 * No user-editable card fields — card content is produced by the engine.
 * The tab's job is to surface live progress, show the generated cards once
 * they arrive, and let the user advance when paused_for_review.
 *
 * Cards load from ``GET /api/wizard/card_gen/state`` → { cards: Card[],
 * has_content, set_params, stage_status }. The "Refresh AI…" button hits
 * ``POST /api/wizard/card_gen/refresh`` (§13), which regenerates the whole set
 * from scratch and returns the same /state shape. Card shape mirrors
 * mtgai/models/card.py: name, mana_cost, type_line, oracle_text, rarity, power,
 * toughness, loyalty, colors, collector_number, flavor_text, status.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'card_gen';

  // Rarity order for grouped display — Mythic first, Common last.
  const RARITY_ORDER = ['mythic', 'rare', 'uncommon', 'common'];
  const RARITY_LABEL = {
    mythic: 'Mythic Rare',
    rare: 'Rare',
    uncommon: 'Uncommon',
    common: 'Common',
  };

  // Color ordering for the colour-group view (WUBRG + multicolor + colorless).
  const COLOR_ORDER = ['W', 'U', 'B', 'R', 'G', 'M', 'C'];
  const COLOR_LABEL = {
    W: 'White', U: 'Blue', B: 'Black', R: 'Red', G: 'Green',
    M: 'Multicolor', C: 'Colorless',
  };

  const local = {
    initialized: false,
    cards: [],          // Card[] from the server, once loaded
    hasContent: false,
    stageStatus: 'pending',
    setParams: { set_name: '', set_size: 0 },
    groupBy: 'rarity',  // 'rarity' | 'color'
    filterRarity: 'all',
    filterColor: 'all',
    locked: false,
    bootstrapping: false,
  };

  W.registerStageRenderer(STAGE_ID, render);

  // Inject scoped styles once at module load.
  (function injectStyles() {
    const STYLE_ID = 'wiz-card_gen-styles';
    if (document.getElementById(STYLE_ID)) return;
    const el = document.createElement('style');
    el.id = STYLE_ID;
    el.textContent = `
      /* ---- Card Gen tab scoped styles ---- */
      .wiz-cardgen-progress {
        background: #0f1729;
        border: 1px solid #1f2540;
        border-radius: 6px;
        padding: 0.75rem 0.9rem;
        margin-bottom: 1rem;
      }
      .wiz-cardgen-progress-headline {
        display: flex;
        align-items: baseline;
        gap: 0.6rem;
        flex-wrap: wrap;
        margin-bottom: 0.35rem;
      }
      .wiz-cardgen-progress-counts {
        font-size: 0.92rem;
        color: #e0e0e0;
        font-weight: 600;
        font-variant-numeric: tabular-nums;
      }
      .wiz-cardgen-progress-failed {
        font-size: 0.8rem;
        color: #ff4757;
      }
      .wiz-cardgen-progress-cost {
        font-size: 0.78rem;
        color: #888;
        font-variant-numeric: tabular-nums;
        margin-left: auto;
      }
      .wiz-cardgen-progress-detail {
        font-size: 0.78rem;
        color: #888;
        margin-top: 0.2rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .wiz-cardgen-controls {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        flex-wrap: wrap;
        margin-bottom: 0.9rem;
      }
      .wiz-cardgen-controls label {
        font-size: 0.78rem;
        color: #aaa;
      }
      .wiz-cardgen-controls select {
        padding: 0.3rem 0.55rem;
        background: #1a1a2e;
        border: 1px solid #333;
        border-radius: 5px;
        color: #e0e0e0;
        font-size: 0.78rem;
        font-family: inherit;
      }
      .wiz-cardgen-controls select:focus { outline: none; border-color: #4a9eff; }
      .wiz-cardgen-group {
        margin-bottom: 1.4rem;
      }
      .wiz-cardgen-group-label {
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        color: #4a9eff;
        border-bottom: 1px solid #1f2540;
        padding-bottom: 0.25rem;
        margin-bottom: 0.6rem;
      }
      .wiz-cardgen-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
        gap: 0.6rem;
      }
      .wiz-cardgen-card {
        background: #0f1729;
        border: 1px solid #1f2540;
        border-radius: 6px;
        padding: 0.6rem 0.7rem;
        font-size: 0.78rem;
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
        transition: border-color 0.15s;
      }
      .wiz-cardgen-card:hover { border-color: #4a9eff44; }
      .wiz-cardgen-card-name {
        font-weight: 700;
        font-size: 0.85rem;
        color: #e0e0e0;
        line-height: 1.2;
      }
      .wiz-cardgen-card-cost {
        font-size: 0.75rem;
        color: #aaa;
        font-family: monospace;
        letter-spacing: 0.02em;
      }
      .wiz-cardgen-card-type {
        font-size: 0.73rem;
        color: #888;
        border-bottom: 1px solid #1a2540;
        padding-bottom: 0.25rem;
        margin-bottom: 0.1rem;
      }
      .wiz-cardgen-card-text {
        color: #ccc;
        font-size: 0.75rem;
        line-height: 1.4;
        flex: 1 1 auto;
      }
      .wiz-cardgen-card-pt {
        font-size: 0.75rem;
        font-weight: 700;
        color: #e0e0e0;
        text-align: right;
        margin-top: 0.1rem;
      }
      .wiz-cardgen-card-rarity {
        font-size: 0.65rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        padding: 1px 5px;
        border-radius: 3px;
        align-self: flex-start;
      }
      .wiz-cardgen-card-rarity.mythic  { background: #c8732220; color: #c87322; border: 1px solid #c8732240; }
      .wiz-cardgen-card-rarity.rare    { background: #d4af3720; color: #d4af37; border: 1px solid #d4af3740; }
      .wiz-cardgen-card-rarity.uncommon{ background: #6c8ebf20; color: #6c8ebf; border: 1px solid #6c8ebf40; }
      .wiz-cardgen-card-rarity.common  { background: #33333320; color: #888;    border: 1px solid #33333350; }
      .wiz-cardgen-card-status {
        font-size: 0.65rem;
        color: #666;
        font-style: italic;
        text-align: right;
      }
      .wiz-cardgen-card-status.failed { color: #ff4757; font-style: normal; }
      .wiz-cardgen-empty {
        color: #666;
        font-style: italic;
        font-size: 0.85rem;
        padding: 1.5rem 0;
        text-align: center;
      }
      .wiz-cardgen-loading {
        color: #888;
        font-size: 0.85rem;
        font-style: italic;
        padding: 1.5rem 0;
        text-align: center;
      }
      .wiz-cardgen-error-block {
        padding: 0.5rem 0.75rem;
        background: rgba(255, 71, 87, 0.08);
        border: 1px solid rgba(255, 71, 87, 0.3);
        border-radius: 6px;
        color: #ffbac4;
        font-size: 0.82rem;
        margin-bottom: 0.75rem;
      }
      .wiz-cardgen-section {
        margin-bottom: 1.2rem;
      }
      /* locked state dim */
      .wiz-cardgen-locked .wiz-cardgen-controls select { opacity: 0.5; cursor: not-allowed; }
      .wiz-cardgen-locked button { opacity: 0.5; cursor: not-allowed; }
    `;
    document.head.appendChild(el);
  })();

  // --------------------------------------------------------------------
  // Top-level render (called by wizard_stage.js on every SSE rerender)
  // --------------------------------------------------------------------

  function render({ root, state, stage, content, footer }) {
    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      bindControls(root);
      // Attempt to load card data from the backend; degrade gracefully if
      // the endpoint doesn't exist yet.
      bootstrap(root, state).catch(err => {
        // Don't toast on a 404 — the endpoint is a follow-up; silently
        // show the placeholder so the tab doesn't look broken.
        if (!err.message.includes('404')) {
          W.toast('Failed to load card gen state: ' + err.message, 'error');
        }
        paintGrid(root);
      });
      paintFooter(footer, state, stage);
      return;
    }

    // Re-render path: SSE fires on every stage_update / item_progress.
    // Reactively repaint ONLY the live progress block (cheap, no DOM churn
    // on the card grid) and the footer. If status transitions out of running
    // and we still have no cards, trigger a re-bootstrap.
    const prevStatus = local.stageStatus;
    if (stage) local.stageStatus = stage.status;

    // Live progress — always update from stage.progress, no guard.
    paintProgress(root, stage);

    // Status transition: was running → now not running → no cards yet → refetch.
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
        .catch(err => {
          if (!err.message.includes('404')) {
            W.toast('Failed to refresh card gen state: ' + err.message, 'error');
          }
          paintGrid(root);
        })
        .finally(() => { local.bootstrapping = false; });
      return;
    }

    paintFooter(footer, state, stage);
    setLocked(local.locked);
  }

  function mountShellHtml() {
    return `
      <div class="wiz-cardgen-section" data-role="cg-progress-section">
        <div class="wiz-theme-section-header-row">
          <h3 style="margin:0">Generation progress</h3>
          <button type="button" class="wiz-btn-secondary wiz-refresh-btn"
                  data-role="cg-refresh-btn"
                  title="Regenerate all cards from scratch (deletes current cards; lands are kept).">
            Refresh AI…
          </button>
        </div>
        <div data-role="cg-progress"></div>
      </div>
      <div class="wiz-cardgen-section" data-role="cg-grid-section">
        <div class="wiz-theme-section-header-row">
          <h3 style="margin:0">Generated cards</h3>
          <div class="wiz-cardgen-controls" data-role="cg-controls" style="margin-bottom:0">
            <label for="cg-group-by">Group by</label>
            <select id="cg-group-by" data-role="cg-group-by">
              <option value="rarity">Rarity</option>
              <option value="color">Color</option>
            </select>
            <label for="cg-filter">Filter</label>
            <select id="cg-filter" data-role="cg-filter">
              <option value="all">All</option>
            </select>
          </div>
        </div>
        <div data-role="cg-grid"></div>
      </div>
    `;
  }

  // --------------------------------------------------------------------
  // Bootstrap — fetch card data from GET /api/wizard/card_gen/state
  // ({ cards, has_content, set_params, stage_status }). Degrades gracefully
  // if the call fails (shows the empty placeholder rather than erroring out).
  // --------------------------------------------------------------------

  async function bootstrap(root, state) {
    const resp = await fetch('/api/wizard/card_gen/state');
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.error || `HTTP ${resp.status}`);
    }
    const data = await resp.json();
    local.cards = Array.isArray(data.cards) ? data.cards : [];
    local.hasContent = local.cards.length > 0;
    local.setParams = data.set_params || local.setParams;
    local.stageStatus = data.stage_status || local.stageStatus;

    rebuildFilterOptions(root);
    paintGrid(root);
    paintFooter(getFooter(root), state, null);
  }

  // --------------------------------------------------------------------
  // Live progress block — purely reactive, no card data needed
  // --------------------------------------------------------------------

  function paintProgress(root, stage) {
    const slot = root && root.querySelector('[data-role="cg-progress"]');
    if (!slot) return;

    const progress = (stage && stage.progress) || {};
    const total = progress.total_items || 0;
    const completed = progress.completed_items || 0;
    const failed = progress.failed_items || 0;
    const cost = progress.cost_usd;
    const detail = progress.detail || progress.current_item || '';
    const error = progress.error_message || '';
    const status = (stage && stage.status) || local.stageStatus;

    if (status === 'pending' && !total) {
      slot.innerHTML = `<div class="wiz-stage-empty">Card generation has not started yet.</div>`;
      return;
    }

    const pct = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
    const costStr = (typeof cost === 'number' && cost > 0) ? '$' + cost.toFixed(3) : '';
    const failedHtml = failed > 0
      ? `<span class="wiz-cardgen-progress-failed">${failed} failed</span>`
      : '';

    slot.innerHTML = `
      <div class="wiz-cardgen-progress">
        <div class="wiz-cardgen-progress-headline">
          <span class="wiz-cardgen-progress-counts">
            ${escHtml(String(completed))} / ${escHtml(String(total || '?'))} cards generated
          </span>
          ${failedHtml}
          ${costStr ? `<span class="wiz-cardgen-progress-cost">${escHtml(costStr)}</span>` : ''}
        </div>
        ${total > 0 ? `
          <div class="wiz-stage-progress-bar">
            <div class="wiz-stage-progress-bar-fill" style="width:${pct}%"></div>
          </div>
        ` : ''}
        ${detail ? `<div class="wiz-cardgen-progress-detail">${escHtml(detail)}</div>` : ''}
        ${error ? `<div class="wiz-cardgen-error-block"><strong>Error:</strong> ${escHtml(error)}</div>` : ''}
      </div>
    `;
  }

  // --------------------------------------------------------------------
  // Filter control helpers
  // --------------------------------------------------------------------

  function rebuildFilterOptions(root) {
    const sel = root && root.querySelector('[data-role="cg-filter"]');
    if (!sel) return;
    const groupBy = local.groupBy;
    let options = '<option value="all">All</option>';
    if (groupBy === 'rarity') {
      const present = new Set(local.cards.map(c => (c.rarity || 'common').toLowerCase()));
      RARITY_ORDER.forEach(r => {
        if (present.has(r)) {
          options += `<option value="${escAttr(r)}">${escHtml(RARITY_LABEL[r] || r)}</option>`;
        }
      });
    } else {
      const present = new Set(local.cards.map(c => cardColorKey(c)));
      COLOR_ORDER.forEach(c => {
        if (present.has(c)) {
          options += `<option value="${escAttr(c)}">${escHtml(COLOR_LABEL[c] || c)}</option>`;
        }
      });
    }
    sel.innerHTML = options;
    // Restore filter selection if still valid, else reset.
    const vals = Array.from(sel.options).map(o => o.value);
    if (!vals.includes(local.filterRarity) && !vals.includes(local.filterColor)) {
      local.filterRarity = 'all';
      local.filterColor = 'all';
    }
    sel.value = groupBy === 'rarity' ? local.filterRarity : local.filterColor;
  }

  function bindControls(root) {
    root.addEventListener('change', function (e) {
      const role = e.target && e.target.dataset && e.target.dataset.role;
      if (role === 'cg-group-by') {
        local.groupBy = e.target.value;
        local.filterRarity = 'all';
        local.filterColor = 'all';
        rebuildFilterOptions(root);
        paintGrid(root);
      } else if (role === 'cg-filter') {
        if (local.groupBy === 'rarity') {
          local.filterRarity = e.target.value;
        } else {
          local.filterColor = e.target.value;
        }
        paintGrid(root);
      }
    });
    // Refresh AI button — §13.
    root.addEventListener('click', function (e) {
      const btn = e.target && e.target.closest('[data-role="cg-refresh-btn"]');
      if (btn) onRefreshCards();
    });
  }

  // --------------------------------------------------------------------
  // Card grid — grouped and filtered
  // --------------------------------------------------------------------

  function paintGrid(root) {
    const slot = root && root.querySelector('[data-role="cg-grid"]');
    if (!slot) return;

    if (!local.hasContent) {
      const running = local.stageStatus === 'running' || local.locked;
      slot.innerHTML = `
        <div class="wiz-cardgen-empty">
          ${running
            ? 'Cards are generating — they will appear here as each slot completes.'
            : 'No cards yet. Cards generate after the Skeleton, Reprints, and Lands stages complete '
              + '— or use “Refresh AI…” above to regenerate them from scratch.'
          }
        </div>
      `;
      return;
    }

    // Apply filter.
    const activeFilter = local.groupBy === 'rarity' ? local.filterRarity : local.filterColor;
    const filtered = activeFilter === 'all'
      ? local.cards
      : local.cards.filter(c => {
          if (local.groupBy === 'rarity') return (c.rarity || 'common').toLowerCase() === activeFilter;
          return cardColorKey(c) === activeFilter;
        });

    if (!filtered.length) {
      slot.innerHTML = `<div class="wiz-cardgen-empty">No cards match the current filter.</div>`;
      return;
    }

    // Group.
    const groups = buildGroups(filtered);
    slot.innerHTML = groups
      .map(({ key, label, cards }) => groupHtml(key, label, cards))
      .join('');
  }

  function buildGroups(cards) {
    if (local.groupBy === 'rarity') {
      return RARITY_ORDER
        .map(r => ({
          key: r,
          label: RARITY_LABEL[r] || r,
          cards: cards.filter(c => (c.rarity || 'common').toLowerCase() === r),
        }))
        .filter(g => g.cards.length > 0);
    }
    // color
    return COLOR_ORDER
      .map(c => ({
        key: c,
        label: COLOR_LABEL[c] || c,
        cards: cards.filter(card => cardColorKey(card) === c),
      }))
      .filter(g => g.cards.length > 0);
  }

  function groupHtml(key, label, cards) {
    return `
      <div class="wiz-cardgen-group">
        <div class="wiz-cardgen-group-label">${escHtml(label)} (${cards.length})</div>
        <div class="wiz-cardgen-grid">
          ${cards.map(c => cardTileHtml(c)).join('')}
        </div>
      </div>
    `;
  }

  function cardTileHtml(card) {
    const rarity = (card.rarity || 'common').toLowerCase();
    const hasStats = card.power != null && card.toughness != null;
    const hasLoyalty = card.loyalty != null;
    const cardStatus = card.status || '';
    const statusClass = cardStatus === 'failed' ? ' failed' : '';

    return `
      <article class="wiz-cardgen-card">
        <div class="wiz-cardgen-card-name">${escHtml(card.name || '(unnamed)')}</div>
        ${card.mana_cost ? `<div class="wiz-cardgen-card-cost">${escHtml(card.mana_cost)}</div>` : ''}
        ${card.type_line ? `<div class="wiz-cardgen-card-type">${escHtml(card.type_line)}</div>` : ''}
        ${card.oracle_text ? `<div class="wiz-cardgen-card-text">${escHtml(card.oracle_text)}</div>` : ''}
        <div style="display:flex;justify-content:space-between;align-items:flex-end;margin-top:0.25rem">
          <span class="wiz-cardgen-card-rarity ${escAttr(rarity)}">${escHtml(RARITY_LABEL[rarity] || rarity)}</span>
          ${hasStats
            ? `<span class="wiz-cardgen-card-pt">${escHtml(String(card.power))}/${escHtml(String(card.toughness))}</span>`
            : hasLoyalty
              ? `<span class="wiz-cardgen-card-pt">[${escHtml(String(card.loyalty))}]</span>`
              : ''}
        </div>
        ${cardStatus && cardStatus !== 'draft' ? `<div class="wiz-cardgen-card-status${escAttr(statusClass)}">${escHtml(cardStatus)}</div>` : ''}
      </article>
    `;
  }

  // Derives a single-char colour key for grouping.
  function cardColorKey(card) {
    const colors = Array.isArray(card.colors) ? card.colors : [];
    if (colors.length === 0) return 'C'; // colorless
    if (colors.length > 1) return 'M';   // multicolor
    return colors[0].charAt(0).toUpperCase();
  }

  // --------------------------------------------------------------------
  // Refresh AI — §13. POST /api/wizard/card_gen/refresh regenerates the whole
  // set from scratch (wipes cards/ + progress, keeps lands) and returns the
  // /state shape, which we repaint from directly.
  // --------------------------------------------------------------------

  async function onRefreshCards() {
    if (local.locked) return;
    if (local.hasContent) {
      if (!confirm('Regenerate all cards from scratch? This deletes the current cards and generates them again. (Lands are kept.)')) return;
    }
    setLocked(true);
    if (W.showBusy) W.showBusy('Regenerating cards…');
    try {
      const resp = await W.postJSON('/api/wizard/card_gen/refresh', {});
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        if (resp.status === 409 && data.running_action) {
          W.toast(`${data.running_action} is in progress — try again when it finishes.`, 'error');
        } else {
          W.toast(data.error || `Refresh failed (${resp.status})`, 'error');
        }
        return;
      }
      // The refresh response is the same shape as /state — repaint the grid
      // directly from it (no second round-trip).
      if (Array.isArray(data.cards)) {
        local.cards = data.cards;
        local.hasContent = local.cards.length > 0;
        local.setParams = data.set_params || local.setParams;
        local.stageStatus = data.stage_status || local.stageStatus;
        const root = bodyRoot();
        if (root) { rebuildFilterOptions(root); paintGrid(root); }
      }
      W.toast('Cards regenerated.', 'success');
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    } finally {
      if (W.clearBusy) W.clearBusy();
      setLocked(false);
    }
  }

  // --------------------------------------------------------------------
  // Footer — §1
  // --------------------------------------------------------------------

  function paintFooter(footer, state, stage) {
    if (!footer) return;
    const isLatest = !state || state.latestTabId === STAGE_ID;
    const status = (stage && stage.status) || local.stageStatus;
    const next = W.nextStageEntryAfter(STAGE_ID);
    const nextName = next ? next.name : 'the next stage';

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Editing past card generation is destructive — use the Edit button above.</span>`;
    } else if (status === 'completed') {
      const isFinal = !next;
      if (isFinal) {
        html = `<span class="wiz-footer-complete" role="status">&#10003; Set complete</span>`;
      } else {
        html = `<span class="wiz-footer-note">Cards generated. Engine is on ${escHtml(nextName)} — switch tabs to follow.</span>`;
      }
    } else if (status === 'failed') {
      html = `<span class="wiz-footer-note">Stage failed — use Refresh AI above to retry failed slots.</span>`;
    } else if (status === 'paused_for_review') {
      html = `
        <button type="button" class="wiz-btn-primary" data-role="cg-advance"
                ${local.locked ? 'disabled' : ''}>
          Next step: ${escHtml(nextName)}
        </button>
      `;
    } else {
      // pending or running
      html = `<span class="wiz-footer-note">Continue button appears once card generation is ready for review.</span>`;
    }

    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
    }
    const btn = footer.querySelector('[data-role="cg-advance"]');
    if (btn) btn.onclick = onAdvance;
  }

  async function onAdvance() {
    const footer = getFooter(bodyRoot());
    const btn = footer && footer.querySelector('[data-role="cg-advance"]');
    const original = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = 'Advancing…'; }
    try {
      const resp = await W.postJSON('/api/wizard/advance', {});
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        W.toast(data.error || 'Advance failed', 'error');
        if (btn) { btn.disabled = false; btn.textContent = original; }
        return;
      }
      // Button stays disabled — SSE will update status as engine continues.
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
      if (btn) { btn.disabled = false; btn.textContent = original; }
    }
  }

  // --------------------------------------------------------------------
  // Form lock — §3
  // --------------------------------------------------------------------

  function setLocked(locked) {
    local.locked = !!locked;
    const root = bodyRoot();
    if (!root) return;
    root.classList.toggle('wiz-cardgen-locked', !!locked);
    const sel = [
      '[data-role="cg-refresh-btn"]',
      '[data-role="cg-group-by"]',
      '[data-role="cg-filter"]',
    ].join(',');
    root.querySelectorAll(sel).forEach(el => { el.disabled = !!locked; });
    const footerBtn = root.querySelector('[data-role="cg-advance"]');
    if (footerBtn) footerBtn.disabled = !!locked;
  }

  // --------------------------------------------------------------------
  // Helpers
  // --------------------------------------------------------------------

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
