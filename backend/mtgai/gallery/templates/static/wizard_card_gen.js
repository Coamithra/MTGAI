/**
 * Wizard Card Generation tab — live progress + rarity/colour grouped card grid.
 *
 * Registers via ``W.registerStageRenderer('card_gen', ...)`` so the standard
 * wizard_stage.js shell still owns the header (status pill, break-point
 * toggle, Edit-cascade button) and we paint the body + footer.
 *
 * Instance-aware: the card_gen stage can appear more than once (the review→regen
 * loop appends an inserted ``card_gen.2`` span after a gate flags cards — see the
 * "Re-entrant pipeline" note in CLAUDE.md). Each instance is its own wizard tab
 * with ``tab.id == instance_id`` (``"card_gen"`` for the backbone,
 * ``"card_gen.2"`` etc. for inserts). So ALL per-tab state lives in a Map keyed
 * by instance id (``stateFor``), every DOM/stream lookup resolves the tab by the
 * instance id (not a hardcoded ``"card_gen"``), and the SSE bridge routes each
 * ``card_gen_card`` / ``card_gen_reset`` to the tab named by its ``instance_id``.
 * Without this, an inserted instance shared the backbone's singleton state (so
 * its shell was never mounted) and its streamed cards painted into the backbone
 * tab — the inserted "Card Generation 2" tab looked empty.
 *
 * The ``/api/wizard/card_gen/state`` fetch stays on the stage route (there is no
 * per-instance state endpoint): it returns the full set from ``cards/`` on disk,
 * and the inserted instance's regenerated cards stream in on top via upsert —
 * which is exactly the backbone "cards pop in one by one" experience.
 *
 * Conventions:
 *   §1  one primary footer button when paused_for_review (bindNextStepButton
 *       pattern)
 *   §3  form lock during AI gen (read-only — no user-editable fields on this
 *       tab; lock suppresses any future action buttons)
 *   §6  past-tab edit cascade routes through wizard_stage.js / W.editFlow
 *   §8  status pill flows from stage state
 *   §9  Stop after this step — handled by wizard_stage.js
 *   §13 "Refresh AI…" section header button — gated to the tip instance
 *       (recovery path for failed/empty runs). It regenerates the whole live
 *       cards/ pool from scratch, which only makes sense for the loop tip; a
 *       non-tip regen instance is a frozen history/<id>/ snapshot, so the button
 *       is hidden there (matching the isLatest convention) — otherwise
 *       clicking it would cross-wire the backbone refresh response (full fresh
 *       pool, is_regen_instance=false) into that instance's per-tab state.
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
 * toughness, loyalty, colors, collector_number, flavor_text, status, plus
 * is_new (true for a card this instance regenerated). The /state response also
 * carries is_regen_instance — true on a review->regen instance. On such an
 * instance the cards this round regenerated are pulled into their own dedicated
 * "Regenerated this round" section at the top of the grid (instead of being
 * interleaved + badged within their rarity/colour groups); the first card_gen
 * run is all-new, so the section never appears there.
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

  // Per-instance tab state, keyed by instance id (tab.id). A stage that repeats
  // (card_gen, card_gen.2, …) gets one entry per instance so the inserted tab
  // never shares — and so the SSE handler can accumulate cards for an instance
  // whose tab the user hasn't opened yet.
  const instances = new Map();
  function stateFor(instanceId) {
    let s = instances.get(instanceId);
    if (!s) {
      s = {
        initialized: false,
        cards: [],          // Card[] from the server, once loaded
        hasContent: false,
        isRegenInstance: false,  // true on a review->regen instance: highlight the
                                 // cards THIS instance regenerated vs carried-over
        stageStatus: 'pending',
        setParams: { set_name: '', set_size: 0 },
        groupBy: 'rarity',  // 'rarity' | 'color'
        filterRarity: 'all',
        filterColor: 'all',
        locked: false,
        bootstrapping: false,
      };
      instances.set(instanceId, s);
    }
    return s;
  }

  W.registerStageRenderer(STAGE_ID, render);

  // SSE bridge — wizard.js forwards card_gen_reset / card_gen_card here. We
  // route by ``data.instance_id`` (events carry it; == "card_gen" for the
  // backbone) so an inserted instance's cards land in ITS tab + ITS state, not
  // the backbone's. ``root`` is resolved fresh per event and is null when that
  // instance's tab isn't mounted — paintGrid is skipped, but the per-instance
  // state still accumulates so the cards show once the user opens the tab (the
  // bootstrap /state fetch also covers it).
  W.onCardGenStream = function (name, data) {
    data = data || {};
    const instanceId = data.instance_id || STAGE_ID;
    const local = stateFor(instanceId);
    const root = W.tabRoot(instanceId);
    if (name === 'card_gen_reset') {
      // A from-scratch refresh wiped cards/ on disk: drop the local list so the
      // new run streams in against an empty grid.
      local.cards = [];
      local.hasContent = false;
      if (root) {
        rebuildFilterOptions(root, local);
        paintGrid(root, local);
      }
    } else if (name === 'card_gen_card') {
      // One freshly-saved card; merge by collector_number (replace if present,
      // else append) so duplicate deliveries from a /state refetch + SSE replay
      // are idempotent.
      const card = data.card;
      if (!card || !card.collector_number) return;
      W.streamUpsert(local.cards, card, (c) => c.collector_number);
      local.hasContent = true;
      if (root) {
        rebuildFilterOptions(root, local);
        paintGrid(root, local);
      }
    }
  };

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
      /* A card this instance (re)generated, vs one carried over from the prior
         instance. Only applied on a review->regen instance — primarily inside
         the dedicated "Regenerated this round" section, where the per-tile badge
         is suppressed and this border is the highlight (see paintGrid). */
      .wiz-cardgen-card.is-new {
        border-color: #45c98a;
        background: #102016;
        box-shadow: 0 0 0 1px #45c98a55;
      }
      .wiz-cardgen-card.is-new:hover { border-color: #45c98a; }
      .wiz-cardgen-new-badge {
        font-size: 0.6rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #45c98a;
        background: #45c98a1f;
        border: 1px solid #45c98a55;
        border-radius: 3px;
        padding: 1px 5px;
        align-self: flex-start;
      }
      /* Dedicated "Regenerated this round" section on a regen instance: a green
         accent header + a faint tinted band so the block reads as distinct from
         the carried-over rarity/colour groups below it. */
      .wiz-cardgen-group--new {
        background: #0d1a12;
        border: 1px solid #45c98a33;
        border-radius: 6px;
        padding: 0.6rem 0.7rem 0.2rem;
      }
      .wiz-cardgen-group-label--new {
        color: #45c98a;
        border-bottom-color: #45c98a33;
      }
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
      /* The skeleton slot's final relabeled descriptor, shown muted under the
         rarity row. Lets the user eyeball "did the card design fulfil the
         slot's brief?" without leaving the tab. */
      .wiz-cardgen-card-slot-text {
        font-size: 0.65rem;
        color: #777;
        font-style: italic;
        margin-top: 0.4rem;
        padding-top: 0.35rem;
        border-top: 1px dashed #2a2f4a;
        line-height: 1.3;
        word-wrap: break-word;
      }
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

  function render({ tab, root, state, stage, content, footer }) {
    const instanceId = tab.id;
    const local = stateFor(instanceId);

    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      bindControls(root, instanceId, local);
      setRefreshVisibility(root, isLatestInstance(state, instanceId));
      W.bindRerunButton(root, stage);
      // A missing /state route (404) returns null from fetchStageState — the
      // bootstrap then paints the empty placeholder. A hard error still toasts
      // and falls back to the placeholder so the tab doesn't look broken.
      bootstrap(root, state, local, instanceId).catch(err => {
        W.toast('Failed to load card gen state: ' + err.message, 'error');
        paintGrid(root, local);
      });
      paintFooter(footer, state, stage, instanceId, local);
      return;
    }

    // Re-render path: SSE fires on every stage_update / item_progress.
    // Reactively repaint ONLY the live progress block (cheap, no DOM churn
    // on the card grid) and the footer. If status transitions out of running
    // and we still have no cards, trigger a re-bootstrap.
    const prevStatus = local.stageStatus;
    if (stage) local.stageStatus = stage.status;

    // Live progress — always update from stage.progress, no guard.
    paintProgress(root, stage, local);

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
      bootstrap(root, state, local, instanceId)
        .catch(err => {
          W.toast('Failed to refresh card gen state: ' + err.message, 'error');
          paintGrid(root, local);
        })
        .finally(() => { local.bootstrapping = false; });
      W.bindRerunButton(root, stage);
      setRefreshVisibility(root, isLatestInstance(state, instanceId));
      return;
    }

    W.bindRerunButton(root, stage);
    setRefreshVisibility(root, isLatestInstance(state, instanceId));
    paintFooter(footer, state, stage, instanceId, local);
    setLocked(root, local, local.locked);
  }

  // The Refresh AI button regenerates the whole live cards/ pool from scratch,
  // which only makes sense for the loop tip — so it shows only on the latest
  // instance. A non-tip regen instance (e.g. card_gen.2) is a frozen
  // history/<id>/ snapshot; clicking refresh there would target the backbone
  // pool and write the backbone /state response (full fresh pool,
  // is_regen_instance=false) into this instance's per-tab state. Same liveness
  // as the footer's isLatest, re-evaluated on every render in case a later
  // instance is appended and this tab stops being the tip.
  function isLatestInstance(state, instanceId) {
    return !state || state.latestTabId === instanceId;
  }

  function setRefreshVisibility(root, visible) {
    const btn = root && root.querySelector('[data-role="cg-refresh-btn"]');
    if (btn) btn.hidden = !visible;
  }

  function mountShellHtml() {
    return `
      ${W.rerunButtonHtml()}
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
  //
  // The fetch is on the stage route (STAGE_ID), not the instance id — there is
  // no per-instance state endpoint, and the full set from disk is exactly what
  // an inserted instance should show (its regenerated cards stream in on top).
  // --------------------------------------------------------------------

  // Live card streaming (card_gen_reset / card_gen_card) is wired at module
  // load via W.onCardGenStream above.

  async function bootstrap(root, state, local, instanceId) {
    // Per-instance read-routing: a completed non-tip instance reads its own
    // card-pool snapshot (history/<instance_id>/) rather than the live tip pool.
    const data = await W.fetchStageState(STAGE_ID, { instance_id: instanceId });
    if (data) {
      local.cards = Array.isArray(data.cards) ? data.cards : [];
      local.hasContent = local.cards.length > 0;
      local.isRegenInstance = !!data.is_regen_instance;
      local.setParams = data.set_params || local.setParams;
      local.stageStatus = data.stage_status || local.stageStatus;
    }
    rebuildFilterOptions(root, local);
    paintGrid(root, local);
  }

  // --------------------------------------------------------------------
  // Live progress block — purely reactive, no card data needed
  // --------------------------------------------------------------------

  function paintProgress(root, stage, local) {
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

  function rebuildFilterOptions(root, local) {
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

  function bindControls(root, instanceId, local) {
    root.addEventListener('change', function (e) {
      const role = e.target && e.target.dataset && e.target.dataset.role;
      if (role === 'cg-group-by') {
        local.groupBy = e.target.value;
        local.filterRarity = 'all';
        local.filterColor = 'all';
        rebuildFilterOptions(root, local);
        paintGrid(root, local);
      } else if (role === 'cg-filter') {
        if (local.groupBy === 'rarity') {
          local.filterRarity = e.target.value;
        } else {
          local.filterColor = e.target.value;
        }
        paintGrid(root, local);
      }
    });
    // Refresh AI button — §13.
    root.addEventListener('click', function (e) {
      const btn = e.target && e.target.closest('[data-role="cg-refresh-btn"]');
      if (btn) onRefreshCards(root, local);
    });
  }

  // --------------------------------------------------------------------
  // Card grid — grouped and filtered
  // --------------------------------------------------------------------

  function paintGrid(root, local) {
    const slot = root && root.querySelector('[data-role="cg-grid"]');
    if (!slot) return;

    if (!local.hasContent) {
      slot.innerHTML = W.emptyStatePanel({
        generating: aiBusy(local),
        generatingMsg: 'Cards are generating — they will appear here as each slot completes.',
        emptyMsg: 'No cards yet. Cards generate after the Skeleton, Reprints, and Lands stages '
          + 'complete — or use “Refresh AI…” above to regenerate them from scratch.',
        className: 'wiz-cardgen-empty',
      });
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

    // Only a review->regen instance distinguishes new-vs-carried-over — on the
    // first card_gen every card is "new", so the distinction is noise.
    const highlightNew = !!local.isRegenInstance;
    // The cards THIS instance regenerated get their own dedicated section at the
    // TOP of the grid (instead of being interleaved + merely badged within their
    // rarity/colour groups), so the user can scan what changed this round at a
    // glance. The carried-over cards keep the normal rarity/colour grouping
    // below. Suppressed until at least one regenerated card is actually present:
    // a /state poll early in the run (before any card re-saved) would otherwise
    // show an empty "Regenerated" header.
    // Sort the dedicated section by collector number so it shows the same
    // deterministic order as the (rarity/colour-ordered) carried-over groups,
    // rather than SSE arrival order.
    const newCards = highlightNew
      ? filtered.filter(c => c.is_new).sort(byCollectorNumber)
      : [];
    const restCards = newCards.length ? filtered.filter(c => !c.is_new) : filtered;

    // Dedicated "Regenerated this round" group on top — flat grid (the header
    // already states what these are, so the per-tile badge is suppressed; the
    // green highlight border is kept for continuity).
    const newSection = newCards.length
      ? groupHtml('__new__', 'Regenerated this round', newCards, true, true)
      : '';
    const groups = buildGroups(restCards, local);
    slot.innerHTML = newSection + groups
      .map(({ key, label, cards }) => groupHtml(key, label, cards, false))
      .join('');
  }

  function buildGroups(cards, local) {
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

  // ``isNewSection`` marks the dedicated "Regenerated this round" group: it gets
  // an accent label and its tiles drop the redundant per-tile badge (the header
  // already says it) while keeping the green highlight border.
  function groupHtml(key, label, cards, highlightNew, isNewSection) {
    const groupClass = isNewSection ? ' wiz-cardgen-group--new' : '';
    const labelClass = isNewSection ? ' wiz-cardgen-group-label--new' : '';
    return `
      <div class="wiz-cardgen-group${groupClass}">
        <div class="wiz-cardgen-group-label${labelClass}">${escHtml(label)} (${cards.length})</div>
        <div class="wiz-cardgen-grid">
          ${cards.map(c => cardTileHtml(c, highlightNew, isNewSection)).join('')}
        </div>
      </div>
    `;
  }

  function cardTileHtml(card, highlightNew, suppressBadge) {
    const isNew = highlightNew && !!card.is_new;
    const rarity = (card.rarity || 'common').toLowerCase();
    const hasStats = card.power != null && card.toughness != null;
    const hasLoyalty = card.loyalty != null;
    const cardStatus = card.status || '';
    const statusClass = cardStatus === 'failed' ? ' failed' : '';
    // The skeleton slot's final relabeled descriptor (tweaked_text or, when
    // the relabel didn't touch it, render_slot_string on the seeds). Shown
    // muted under the rarity badge so you can eyeball "did the card design
    // fulfil the slot's brief?". Falls back to "" gracefully when slots_by_id
    // wasn't passed by the server (e.g. skeleton.json missing).
    const slotText = card.slot_text || '';
    const cn = card.collector_number || '';

    return `
      <article class="wiz-cardgen-card${isNew ? ' is-new' : ''}">
        ${isNew && !suppressBadge ? '<span class="wiz-cardgen-new-badge">Regenerated</span>' : ''}
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
        ${slotText ? `<div class="wiz-cardgen-card-slot-text" title="Skeleton slot ${escAttr(cn)}">${escHtml(cn)} — ${escHtml(slotText)}</div>` : ''}
      </article>
    `;
  }

  // Stable, numeric-aware sort by collector_number (e.g. "0007" < "0012").
  function byCollectorNumber(a, b) {
    return String(a.collector_number || '').localeCompare(
      String(b.collector_number || ''), undefined, { numeric: true });
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

  async function onRefreshCards(root, local) {
    await W.runAiAction({
      isLocked: () => local.locked,
      setLocked: (locked) => setLocked(root, local, locked),
      confirm: () => (local.hasContent
        ? 'Regenerate all cards from scratch? This deletes the current cards and generates them again. (Lands are kept.)'
        : ''),
      busyLabel: 'Regenerating cards…',
      run: async ({ post }) => {
        const data = await post('/api/wizard/card_gen/refresh', {}, 'Refresh failed');
        if (!data) return;
        // The refresh response is the same shape as /state — repaint the grid
        // directly from it (no second round-trip).
        if (Array.isArray(data.cards)) {
          local.cards = data.cards;
          local.hasContent = local.cards.length > 0;
          local.isRegenInstance = !!data.is_regen_instance;
          local.setParams = data.set_params || local.setParams;
          local.stageStatus = data.stage_status || local.stageStatus;
          if (root) { rebuildFilterOptions(root, local); paintGrid(root, local); }
        }
        W.toast('Cards regenerated.', 'success');
      },
    });
  }

  // --------------------------------------------------------------------
  // Footer — §1
  // --------------------------------------------------------------------

  function paintFooter(footer, state, stage, instanceId, local) {
    if (!footer) return;
    const isLatest = isLatestInstance(state, instanceId);
    const status = (stage && stage.status) || local.stageStatus;
    const next = W.nextStageEntryAfter(instanceId);
    const nextName = next ? next.name : 'the next stage';

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Editing past card generation is destructive — use the Edit button above.</span>`;
    } else if (status === 'completed') {
      const isFinal = !next;
      if (isFinal) {
        html = `<span class="wiz-footer-complete" role="status">✓ Set complete</span>`;
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

    W.paintFooter(footer, html, { role: 'cg-advance', onClick: () => onAdvance(instanceId) });
  }

  // No navigate: on success the button stays disabled and SSE drives the status
  // forward — a navigate would race the engine's own advance.
  function onAdvance(instanceId) {
    return W.advanceStage({ stageId: instanceId, btnRole: 'cg-advance', navigate: false });
  }

  // --------------------------------------------------------------------
  // Form lock — §3
  // --------------------------------------------------------------------

  // AI is "active" on this tab when this tab kicked off an op (local.locked) or
  // the engine is running the card_gen stage (stageStatus). The composite is
  // the standardized lock truth source across stage tabs (§3).
  function aiBusy(local) {
    return local.locked || local.stageStatus === 'running';
  }

  function setLocked(root, local, locked) {
    local.locked = !!locked;
    W.setTabLocked(root, aiBusy(local), {
      lockClass: 'wiz-cardgen-locked',
      selectors: [
        '[data-role="cg-refresh-btn"]',
        '[data-role="cg-group-by"]',
        '[data-role="cg-filter"]',
      ],
      footerSelector: '[data-role="cg-advance"]',
    });
  }

  // --------------------------------------------------------------------
  // Helpers
  // --------------------------------------------------------------------

  const escHtml = W.escHtml;

  const escAttr = W.escAttr;
})();
