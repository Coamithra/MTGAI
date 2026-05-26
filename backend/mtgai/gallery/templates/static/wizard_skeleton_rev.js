/**
 * Wizard Skeleton Revision tab — renders the RevisionReport produced by
 * mtgai/generation/skeleton_reviser.py (run_revision()).
 *
 * Layout: summary header (N rounds · M cards replaced · $cost), then per-round:
 *   - Round header with cost + timestamp
 *   - LLM analysis text (prose)
 *   - Slot changes list: slot_id / current card / action / reasoning
 *   - Regenerated cards list
 *   - Metrics comparison (pre vs post key metrics)
 *
 * Conventions followed:
 *   §1  paused_for_review footer → primary "Next step" button
 *   §3  form lock — read-only view, guards footer button
 *   §6  past-tab editing goes through the Edit cascade (standard shell button)
 *   §8  status pill from stage state
 *   §9  break-point toggle owned by wizard_stage.js
 */

(function () {
  'use strict';

  /* -----------------------------------------------------------------------
   * Inject scoped styles once
   * --------------------------------------------------------------------- */
  if (!document.getElementById('wiz-skeleton_rev-styles')) {
    const style = document.createElement('style');
    style.id = 'wiz-skeleton_rev-styles';
    style.textContent = `
      /* Summary header */
      .wiz-skelrev-summary-header {
        display: flex;
        align-items: baseline;
        gap: 1.2rem;
        flex-wrap: wrap;
        margin-bottom: 1rem;
      }
      .wiz-skelrev-headline {
        font-size: 1.4rem;
        font-weight: 700;
        color: #e0e0e0;
      }
      .wiz-skelrev-cost {
        font-size: 0.9rem;
        color: #00d4aa;
        font-variant-numeric: tabular-nums;
      }

      /* Round card */
      .wiz-skelrev-round {
        border: 1px solid #1f2540;
        border-radius: 6px;
        margin-top: 1rem;
        overflow: hidden;
      }
      .wiz-skelrev-round-header {
        display: flex;
        align-items: center;
        gap: 1rem;
        padding: 0.55rem 0.85rem;
        background: #16213e;
        border-bottom: 1px solid #1f2540;
        font-size: 0.85rem;
        flex-wrap: wrap;
      }
      .wiz-skelrev-round-title {
        font-weight: 700;
        color: #e0e0e0;
        font-size: 0.95rem;
      }
      .wiz-skelrev-round-meta {
        color: #888;
        font-size: 0.78rem;
        font-variant-numeric: tabular-nums;
      }
      .wiz-skelrev-round-meta span + span::before { content: ' · '; }
      .wiz-skelrev-round-body {
        padding: 0.85rem;
      }

      /* Analysis prose */
      .wiz-skelrev-analysis {
        color: #bbb;
        font-size: 0.83rem;
        line-height: 1.55;
        margin-bottom: 0.9rem;
        padding: 0.6rem 0.75rem;
        background: #161830;
        border-radius: 4px;
        border-left: 3px solid #4a9eff44;
      }
      .wiz-skelrev-analysis-label {
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #555;
        font-weight: 700;
        margin-bottom: 0.35rem;
      }

      /* Changes list */
      .wiz-skelrev-changes { margin-bottom: 0.9rem; }
      .wiz-skelrev-changes-title {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #666;
        font-weight: 700;
        margin-bottom: 0.4rem;
      }
      .wiz-skelrev-change-row {
        display: grid;
        grid-template-columns: 4rem 1fr auto;
        gap: 0.4rem 0.7rem;
        align-items: start;
        padding: 0.45rem 0.6rem;
        background: #161830;
        border-radius: 4px;
        margin-bottom: 0.3rem;
        font-size: 0.82rem;
      }
      .wiz-skelrev-slot-id {
        font-family: monospace;
        font-size: 0.78rem;
        color: #888;
        padding-top: 1px;
      }
      .wiz-skelrev-change-main { color: #ccc; line-height: 1.4; }
      .wiz-skelrev-card-name { font-weight: 600; color: #e0e0e0; }
      .wiz-skelrev-change-reason { font-size: 0.77rem; color: #888; margin-top: 0.15rem; }
      .wiz-skelrev-action-badge {
        display: inline-block;
        padding: 2px 7px;
        border-radius: 3px;
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        white-space: nowrap;
        background: #1f2540;
        color: #aaa;
      }
      .wiz-skelrev-action-badge.regenerate  { background: #4a9eff22; color: #4a9eff; }
      .wiz-skelrev-action-badge.modify_slot { background: #ffa50222; color: #ffa502; }
      .wiz-skelrev-constraints {
        font-size: 0.75rem;
        color: #666;
        margin-top: 0.15rem;
        font-style: italic;
      }

      /* Regenerated cards */
      .wiz-skelrev-regen { margin-bottom: 0.9rem; }
      .wiz-skelrev-regen-title {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #666;
        font-weight: 700;
        margin-bottom: 0.4rem;
      }
      .wiz-skelrev-card-chips {
        display: flex;
        flex-wrap: wrap;
        gap: 0.35rem;
      }
      .wiz-skelrev-card-chip {
        padding: 3px 9px;
        background: #16213e;
        border: 1px solid #1f2540;
        border-radius: 12px;
        font-size: 0.78rem;
        color: #ccc;
      }

      /* Metrics comparison */
      .wiz-skelrev-metrics { }
      .wiz-skelrev-metrics-title {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #666;
        font-weight: 700;
        margin-bottom: 0.4rem;
      }
      .wiz-skelrev-metrics-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.8rem;
      }
      .wiz-skelrev-metrics-table th {
        text-align: left;
        padding: 0.25rem 0.5rem;
        border-bottom: 1px solid #1f2540;
        color: #555;
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
      }
      .wiz-skelrev-metrics-table td {
        padding: 0.25rem 0.5rem;
        border-bottom: 1px solid #111428;
        color: #bbb;
        font-variant-numeric: tabular-nums;
      }
      .wiz-skelrev-metrics-table tr:last-child td { border-bottom: none; }
      .wiz-skelrev-metric-improved { color: #00d4aa; }
      .wiz-skelrev-metric-worse    { color: #ff4757; }
    `;
    document.head.appendChild(style);
  }

  /* -----------------------------------------------------------------------
   * Module state
   * --------------------------------------------------------------------- */
  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'skeleton_rev';

  const local = {
    initialized: false,
    stageStatus: 'pending',
    locked: false,
    bootstrapping: false,
    // Fields from RevisionReport (skeleton_reviser.py)
    hasContent: false,
    setCode: '',
    rounds: [],           // [RevisionRound] — see skeleton_reviser.RevisionRound
    totalCostUsd: 0,
    totalCardsReplaced: 0,
  };

  W.registerStageRenderer(STAGE_ID, render);

  /* -----------------------------------------------------------------------
   * Top-level render
   * --------------------------------------------------------------------- */
  function render({ root, state, stage, content, footer }) {
    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      bootstrap(root, state).catch(err => {
        W.toast('Failed to load skeleton revision state: ' + err.message, 'error');
      });
      paintFooter(footer, state, stage);
      return;
    }

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
        .catch(err => W.toast('Failed to refresh skeleton revision state: ' + err.message, 'error'))
        .finally(() => { local.bootstrapping = false; });
      return;
    }

    paintFooter(footer, state, stage);
  }

  function mountShellHtml() {
    return `
      <div data-role="skelrev-header"></div>
      <div data-role="skelrev-rounds"></div>
    `;
  }

  /* -----------------------------------------------------------------------
   * Bootstrap — fetch revision report artifact
   * --------------------------------------------------------------------- */
  async function bootstrap(root, state) {
    // TODO: implement GET /api/wizard/skeleton_rev/state → RevisionReport JSON
    // Shape: {set_code, rounds:[{round_number, timestamp, plan:{analysis, changes:[{slot_id, current_card_name,
    //   action, new_constraints, reasoning}], expected_improvements}, slots_changed, cards_archived,
    //   cards_regenerated, cost_usd, pre_metrics, post_metrics}], total_cost_usd, total_cards_replaced}
    let data = null;
    try {
      const resp = await fetch('/api/wizard/skeleton_rev/state');
      if (resp.ok) {
        data = await resp.json();
      }
    } catch (_) { /* network error — degrade to empty */ }

    if (data) {
      local.hasContent = true;
      local.setCode = data.set_code || '';
      local.rounds = data.rounds || [];
      local.totalCostUsd = data.total_cost_usd || 0;
      local.totalCardsReplaced = data.total_cards_replaced || 0;
    }

    paintHeader(root, state);
    paintRounds(root, state);
    paintFooter(getFooter(root), state, null);
  }

  /* -----------------------------------------------------------------------
   * Header — summary stats
   * --------------------------------------------------------------------- */
  function paintHeader(root, _state) {
    const slot = root.querySelector('[data-role="skelrev-header"]');
    if (!slot) return;

    if (!local.hasContent) {
      const isRunning = local.stageStatus === 'running' || local.locked;
      slot.innerHTML = `
        <div class="wiz-stage-empty">
          ${isRunning
            ? 'Skeleton revision is running — slot changes and card regeneration are in progress…'
            : 'No revision report yet. Skeleton revision runs automatically after balance analysis.'}
        </div>
      `;
      return;
    }

    const roundCount = local.rounds.length;
    const roundLabel = roundCount === 1 ? '1 round' : `${roundCount} rounds`;
    const cardLabel = local.totalCardsReplaced === 1
      ? '1 card replaced'
      : `${local.totalCardsReplaced} cards replaced`;
    const costLabel = local.totalCostUsd > 0
      ? `$${local.totalCostUsd.toFixed(3)}`
      : '$0.000';

    slot.innerHTML = `
      <div class="wiz-skelrev-summary-header">
        <span class="wiz-skelrev-headline">${escHtml(roundLabel)}</span>
        <span class="wiz-skelrev-headline" style="font-size:1rem;color:#ccc">·</span>
        <span class="wiz-skelrev-headline" style="font-size:1rem">${escHtml(cardLabel)}</span>
        <span class="wiz-skelrev-cost">${escHtml(costLabel)}</span>
      </div>
      <dl class="wiz-stage-summary">
        <dt>Set</dt><dd>${escHtml(local.setCode || '—')}</dd>
        <dt>Rounds</dt><dd>${escHtml(String(roundCount))}</dd>
        <dt>Cards replaced</dt><dd>${escHtml(String(local.totalCardsReplaced))}</dd>
        <dt>Total cost</dt><dd>${escHtml(costLabel)}</dd>
      </dl>
    `;
  }

  /* -----------------------------------------------------------------------
   * Per-round cards
   * --------------------------------------------------------------------- */
  function paintRounds(root, _state) {
    const slot = root.querySelector('[data-role="skelrev-rounds"]');
    if (!slot || !local.hasContent) return;

    if (!local.rounds.length) {
      slot.innerHTML = `<div class="wiz-stage-empty" style="margin-top:0.8rem">No revision rounds recorded — the analysis found no set-level issues requiring changes.</div>`;
      return;
    }

    slot.innerHTML = local.rounds.map(rnd => roundHtml(rnd)).join('');
  }

  function roundHtml(rnd) {
    const ts = rnd.timestamp ? new Date(rnd.timestamp).toLocaleString() : '';
    const costLabel = rnd.cost_usd > 0 ? `$${rnd.cost_usd.toFixed(3)}` : '';
    const changeCount = (rnd.plan && rnd.plan.changes) ? rnd.plan.changes.length : 0;
    const regenCount = (rnd.cards_regenerated || []).length;

    const metaParts = [
      ts ? `<span>${escHtml(ts)}</span>` : '',
      costLabel ? `<span>${escHtml(costLabel)}</span>` : '',
      `<span>${changeCount} slot${changeCount !== 1 ? 's' : ''} changed</span>`,
      `<span>${regenCount} card${regenCount !== 1 ? 's' : ''} regenerated</span>`,
    ].filter(Boolean).join('');

    const analysis = (rnd.plan && rnd.plan.analysis) ? rnd.plan.analysis : '';
    const changes = (rnd.plan && rnd.plan.changes) ? rnd.plan.changes : [];
    const regenCards = rnd.cards_regenerated || [];
    const preMetrics = rnd.pre_metrics || {};
    const postMetrics = rnd.post_metrics || {};

    return `
      <div class="wiz-skelrev-round">
        <div class="wiz-skelrev-round-header">
          <span class="wiz-skelrev-round-title">Round ${escHtml(String(rnd.round_number))}</span>
          <div class="wiz-skelrev-round-meta">${metaParts}</div>
        </div>
        <div class="wiz-skelrev-round-body">
          ${analysis ? analysisHtml(analysis) : ''}
          ${changes.length ? changesHtml(changes) : ''}
          ${regenCards.length ? regenCardsHtml(regenCards) : ''}
          ${metricsHtml(preMetrics, postMetrics)}
        </div>
      </div>
    `;
  }

  function analysisHtml(text) {
    return `
      <div class="wiz-skelrev-analysis">
        <div class="wiz-skelrev-analysis-label">LLM analysis</div>
        ${escHtml(text)}
      </div>
    `;
  }

  function changesHtml(changes) {
    const rows = changes.map(c => {
      const actionClass = (c.action || '').replace(/[^a-z_]/g, '');
      const constraints = c.new_constraints
        ? Object.entries(c.new_constraints)
            .filter(([, v]) => v !== null && v !== undefined && v !== '')
            .map(([k, v]) => `${k}: ${v}`)
            .join(', ')
        : '';

      return `
        <div class="wiz-skelrev-change-row">
          <span class="wiz-skelrev-slot-id">${escHtml(c.slot_id || '—')}</span>
          <div class="wiz-skelrev-change-main">
            <span class="wiz-skelrev-card-name">${escHtml(c.current_card_name || '(unnamed)')}</span>
            ${c.reasoning ? `<div class="wiz-skelrev-change-reason">${escHtml(c.reasoning)}</div>` : ''}
            ${constraints ? `<div class="wiz-skelrev-constraints">${escHtml(constraints)}</div>` : ''}
          </div>
          <span class="wiz-skelrev-action-badge ${escAttr(actionClass)}">${escHtml((c.action || '').replace(/_/g, ' '))}</span>
        </div>
      `;
    }).join('');

    return `
      <div class="wiz-skelrev-changes">
        <div class="wiz-skelrev-changes-title">Slot changes (${changes.length})</div>
        ${rows}
      </div>
    `;
  }

  function regenCardsHtml(cards) {
    const chips = cards.map(name =>
      `<span class="wiz-skelrev-card-chip">${escHtml(name)}</span>`
    ).join('');
    return `
      <div class="wiz-skelrev-regen">
        <div class="wiz-skelrev-regen-title">Regenerated cards (${cards.length})</div>
        <div class="wiz-skelrev-card-chips">${chips}</div>
      </div>
    `;
  }

  function metricsHtml(pre, post) {
    // Only show keys that exist in either snapshot, skip 'summary' (nested obj)
    const allKeys = Array.from(new Set([...Object.keys(pre), ...Object.keys(post)]))
      .filter(k => k !== 'summary')
      .sort();
    if (!allKeys.length) return '';

    const rows = allKeys.map(key => {
      const preVal = pre[key] !== undefined ? String(pre[key]) : '—';
      const postVal = post[key] !== undefined ? String(post[key]) : '—';
      const preNum = parseFloat(pre[key]);
      const postNum = parseFloat(post[key]);
      let postClass = '';
      if (!isNaN(preNum) && !isNaN(postNum) && preNum !== postNum) {
        // Lower issues / mismatches is better; higher counts are context-dependent
        // — for now just highlight change direction generically
        postClass = postNum < preNum ? 'wiz-skelrev-metric-improved' : 'wiz-skelrev-metric-worse';
      }
      return `
        <tr>
          <td>${escHtml(key.replace(/_/g, ' '))}</td>
          <td>${escHtml(preVal)}</td>
          <td class="${postClass}">${escHtml(postVal)}</td>
        </tr>
      `;
    }).join('');

    return `
      <div class="wiz-skelrev-metrics">
        <div class="wiz-skelrev-metrics-title">Metrics before → after</div>
        <table class="wiz-skelrev-metrics-table">
          <thead><tr><th>Metric</th><th>Before</th><th>After</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  /* -----------------------------------------------------------------------
   * Footer — Next-step button when paused; informational note otherwise
   * --------------------------------------------------------------------- */
  function paintFooter(footer, state, stage) {
    if (!footer) return;
    const stageObj = stage || (state && state.pipeline && state.pipeline.stages
      ? state.pipeline.stages.find(s => s.stage_id === STAGE_ID)
      : null);
    const status = stageObj ? stageObj.status : local.stageStatus;
    const isLatest = !state || state.latestTabId === STAGE_ID;
    const isPaused = status === 'paused_for_review';

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Past stage — use the Edit button above to re-run skeleton revision.</span>`;
    } else if (isPaused) {
      const next = W.nextStageEntryAfter(STAGE_ID);
      const label = next ? `Next step: ${next.name}` : 'Next step';
      html = `<button type="button" class="wiz-btn-primary" data-role="next-step">${escHtml(label)}</button>`;
    } else if (status === 'failed') {
      html = `<span class="wiz-footer-note">Stage failed — check the error above and re-run from Project Settings.</span>`;
    } else if (status === 'running') {
      html = `<span class="wiz-footer-note">Revision is running — slot changes and card regeneration in progress…</span>`;
    } else {
      html = `<span class="wiz-footer-note">This stage runs automatically. Results appear here once complete.</span>`;
    }

    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
      const btn = footer.querySelector('button[data-role="next-step"]');
      if (btn) bindNextStepButton(btn);
    }
  }

  function bindNextStepButton(btn) {
    btn.onclick = async () => {
      const original = btn.textContent;
      btn.disabled = true;
      btn.textContent = 'Advancing…';
      try {
        const resp = await W.postJSON('/api/wizard/advance', {});
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          if (resp.status === 409 && data.running_action) {
            W.toast(`${data.running_action} is in progress — try again when it finishes.`, 'error');
          } else {
            W.toast(data.error || 'Advance failed', 'error');
          }
          btn.disabled = false;
          btn.textContent = original;
        }
      } catch (err) {
        W.toast('Network error: ' + err.message, 'error');
        btn.disabled = false;
        btn.textContent = original;
      }
    };
  }

  /* -----------------------------------------------------------------------
   * Form lock (§3) — read-only view, guard footer button
   * --------------------------------------------------------------------- */
  function setLocked(locked) {
    local.locked = !!locked;
    const root = bodyRoot();
    if (!root) return;
    const btn = root.querySelector('button[data-role="next-step"]');
    if (btn) btn.disabled = !!locked;
  }

  /* -----------------------------------------------------------------------
   * Helpers
   * --------------------------------------------------------------------- */
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
