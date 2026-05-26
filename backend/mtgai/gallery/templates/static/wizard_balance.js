/**
 * Wizard Balance Analysis tab — renders the BalanceAnalysisResult produced
 * by mtgai/analysis/balance.py (analyze_set()).
 *
 * Layout: summary header (N issues), then four sections:
 *   1. Color balance — horizontal div bars (color -> card count)
 *   2. Mechanic distribution — planned vs actual table per mechanic
 *   3. Conformance issues — slot mismatches (FAIL/WARN) list
 *   4. Interaction flags — degenerate-combo list with enabler + severity badge
 *
 * Conventions followed:
 *   §1  paused_for_review footer → primary "Next step" button via bindNextStepButton
 *   §3  form lock — no interactive surfaces, but setLocked() guards footer
 *   §6  past-tab editing goes through the Edit cascade (standard shell button)
 *   §8  status pill from stage state
 *   §9  break-point toggle owned by wizard_stage.js
 */

(function () {
  'use strict';

  /* -----------------------------------------------------------------------
   * Inject scoped styles once
   * --------------------------------------------------------------------- */
  if (!document.getElementById('wiz-balance-styles')) {
    const style = document.createElement('style');
    style.id = 'wiz-balance-styles';
    style.textContent = `
      /* Summary header */
      .wiz-balance-summary-header {
        display: flex;
        align-items: baseline;
        gap: 1.2rem;
        margin-bottom: 1.2rem;
        flex-wrap: wrap;
      }
      .wiz-balance-issue-count {
        font-size: 1.6rem;
        font-weight: 700;
        color: #e0e0e0;
      }
      .wiz-balance-issue-count.has-fails { color: #ff4757; }
      .wiz-balance-issue-count.has-warns { color: #ffa502; }
      .wiz-balance-issue-count.all-pass  { color: #00d4aa; }
      .wiz-balance-badge-row {
        display: flex;
        gap: 0.5rem;
        align-items: center;
      }
      .wiz-balance-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
      }
      .wiz-balance-badge.FAIL { background: #ff475733; color: #ff4757; }
      .wiz-balance-badge.WARN { background: #ffa50233; color: #ffa502; }
      .wiz-balance-badge.PASS { background: #00d4aa22; color: #00d4aa; }

      /* Color balance bars */
      .wiz-balance-color-grid {
        display: grid;
        grid-template-columns: 2.5rem 1fr 2.5rem;
        align-items: center;
        gap: 0.3rem 0.6rem;
        margin-top: 0.4rem;
      }
      .wiz-balance-color-label {
        font-size: 0.8rem;
        font-weight: 700;
        color: #ccc;
        text-align: right;
      }
      .wiz-balance-color-track {
        height: 12px;
        background: #1f2540;
        border-radius: 3px;
        overflow: hidden;
      }
      .wiz-balance-color-fill {
        height: 100%;
        border-radius: 3px;
        transition: width 0.3s ease;
      }
      /* MTG color identities */
      .wiz-balance-color-fill[data-color="W"] { background: #e8e8d0; }
      .wiz-balance-color-fill[data-color="U"] { background: #4a9eff; }
      .wiz-balance-color-fill[data-color="B"] { background: #9370db; }
      .wiz-balance-color-fill[data-color="R"] { background: #ff6347; }
      .wiz-balance-color-fill[data-color="G"] { background: #3cb371; }
      .wiz-balance-color-fill[data-color="C"] { background: #888; }
      .wiz-balance-color-count {
        font-size: 0.75rem;
        color: #999;
        font-variant-numeric: tabular-nums;
      }

      /* Mechanic distribution table */
      .wiz-balance-mech-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.82rem;
        margin-top: 0.4rem;
      }
      .wiz-balance-mech-table th {
        text-align: left;
        padding: 0.3rem 0.6rem;
        border-bottom: 1px solid #1f2540;
        color: #888;
        font-weight: 600;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
      }
      .wiz-balance-mech-table td {
        padding: 0.35rem 0.6rem;
        border-bottom: 1px solid #161830;
        color: #ccc;
      }
      .wiz-balance-mech-table tr:last-child td { border-bottom: none; }
      .wiz-balance-mech-delta { font-variant-numeric: tabular-nums; }
      .wiz-balance-mech-delta.over  { color: #ff4757; }
      .wiz-balance-mech-delta.under { color: #ffa502; }
      .wiz-balance-mech-delta.ok    { color: #00d4aa; }

      /* Issues list */
      .wiz-balance-issue-list {
        display: flex;
        flex-direction: column;
        gap: 0.4rem;
        margin-top: 0.4rem;
      }
      .wiz-balance-issue-row {
        display: flex;
        gap: 0.7rem;
        align-items: flex-start;
        padding: 0.5rem 0.7rem;
        background: #161830;
        border-radius: 5px;
        font-size: 0.82rem;
      }
      .wiz-balance-issue-sev {
        flex: 0 0 auto;
        margin-top: 1px;
      }
      .wiz-balance-issue-body { flex: 1 1 auto; color: #ccc; line-height: 1.4; }
      .wiz-balance-issue-meta {
        font-size: 0.74rem;
        color: #666;
        margin-top: 0.2rem;
      }
      .wiz-balance-issue-meta span + span::before { content: ' · '; }

      /* Interaction flags */
      .wiz-balance-flag-list {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        margin-top: 0.4rem;
      }
      .wiz-balance-flag-row {
        padding: 0.6rem 0.8rem;
        background: #161830;
        border-radius: 5px;
        font-size: 0.82rem;
        border-left: 3px solid #ffa502;
      }
      .wiz-balance-flag-row.FAIL { border-left-color: #ff4757; }
      .wiz-balance-flag-title {
        font-weight: 600;
        color: #e0e0e0;
        margin-bottom: 0.3rem;
      }
      .wiz-balance-flag-desc { color: #bbb; line-height: 1.4; margin-bottom: 0.3rem; }
      .wiz-balance-flag-enabler {
        font-size: 0.77rem;
        color: #888;
      }
      .wiz-balance-flag-enabler strong { color: #aaa; }
      .wiz-balance-flag-constraint {
        font-size: 0.77rem;
        color: #666;
        margin-top: 0.15rem;
        font-style: italic;
      }
    `;
    document.head.appendChild(style);
  }

  /* -----------------------------------------------------------------------
   * Module state
   * --------------------------------------------------------------------- */
  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'balance';

  const local = {
    initialized: false,
    stageStatus: 'pending',
    locked: false,
    bootstrapping: false,
    // Fields from BalanceAnalysisResult (balance.py / analysis/models.py)
    hasContent: false,
    totalCards: 0,
    summary: {},           // {PASS: N, WARN: N, FAIL: N}
    colorBalance: {},      // {color -> count}
    mechanicDistribution: [], // [{mechanic_name, planned:{rarity->N}, actual:{rarity->N}, total_planned, total_actual}]
    issues: [],            // [{check, severity, slot_id, card_name, message, expected, actual}]
    interactionFlags: [],  // [{cards_involved, interaction_type, description, severity, enabler_card, enabler_slot_id, why_enabler, replacement_constraint}]
    interactionAnalysis: '',
  };

  W.registerStageRenderer(STAGE_ID, render);

  /* -----------------------------------------------------------------------
   * Top-level render — called by wizard_stage.js shell on every SSE update
   * --------------------------------------------------------------------- */
  function render({ root, state, stage, content, footer }) {
    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      bootstrap(root, state).catch(err => {
        W.toast('Failed to load balance state: ' + err.message, 'error');
      });
      paintFooter(footer, state, stage);
      return;
    }

    // Re-render path: update status and re-check if we should re-bootstrap
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
        .catch(err => W.toast('Failed to refresh balance state: ' + err.message, 'error'))
        .finally(() => { local.bootstrapping = false; });
      return;
    }

    paintFooter(footer, state, stage);
  }

  function mountShellHtml() {
    return `
      <div data-role="balance-header"></div>
      <div data-role="balance-sections"></div>
    `;
  }

  /* -----------------------------------------------------------------------
   * Bootstrap — fetch artifact from server (or degrade gracefully)
   * --------------------------------------------------------------------- */
  async function bootstrap(root, state) {
    // TODO: implement GET /api/wizard/balance/state → BalanceAnalysisResult JSON
    let data = null;
    try {
      const resp = await fetch('/api/wizard/balance/state');
      if (resp.ok) {
        data = await resp.json();
      }
      // 404/409/500 — fall through to empty state; don't crash
    } catch (_) { /* network error — degrade to empty */ }

    if (data) {
      local.hasContent = true;
      local.totalCards = data.total_cards || 0;
      local.summary = data.summary || {};
      local.colorBalance = data.color_balance || {};
      local.mechanicDistribution = data.mechanic_distribution || [];
      local.issues = data.issues || [];
      local.interactionFlags = data.interaction_flags || [];
      local.interactionAnalysis = data.interaction_analysis || '';
    }

    paintHeader(root, state);
    paintSections(root, state);
    paintFooter(getFooter(root), state, null);
  }

  /* -----------------------------------------------------------------------
   * Header — issue count + PASS/WARN/FAIL badge row
   * --------------------------------------------------------------------- */
  function paintHeader(root, _state) {
    const slot = root.querySelector('[data-role="balance-header"]');
    if (!slot) return;

    if (!local.hasContent) {
      const isRunning = local.stageStatus === 'running' || local.locked;
      slot.innerHTML = `
        <div class="wiz-stage-empty">
          ${isRunning
            ? 'Balance analysis is running…'
            : 'No balance report yet. The analysis runs automatically as part of the pipeline.'}
        </div>
      `;
      return;
    }

    const fails = local.summary.FAIL || 0;
    const warns = local.summary.WARN || 0;
    const passes = local.summary.PASS || 0;
    const totalIssues = fails + warns;
    const countClass = fails > 0 ? 'has-fails' : warns > 0 ? 'has-warns' : 'all-pass';
    const countLabel = totalIssues === 0
      ? 'No issues found'
      : totalIssues === 1 ? '1 issue found' : `${totalIssues} issues found`;

    slot.innerHTML = `
      <div class="wiz-balance-summary-header">
        <span class="wiz-balance-issue-count ${countClass}">${escHtml(countLabel)}</span>
        <div class="wiz-balance-badge-row">
          ${fails > 0 ? `<span class="wiz-balance-badge FAIL">${fails} fail</span>` : ''}
          ${warns > 0 ? `<span class="wiz-balance-badge WARN">${warns} warn</span>` : ''}
          ${passes > 0 ? `<span class="wiz-balance-badge PASS">${passes} pass</span>` : ''}
        </div>
      </div>
      <dl class="wiz-stage-summary">
        <dt>Cards analysed</dt><dd>${escHtml(String(local.totalCards))}</dd>
        <dt>Mechanics</dt><dd>${escHtml(String(local.mechanicDistribution.length))}</dd>
        <dt>Interaction flags</dt><dd>${escHtml(String(local.interactionFlags.length))}</dd>
      </dl>
    `;
  }

  /* -----------------------------------------------------------------------
   * Sections — color balance, mechanic distribution, issues, interactions
   * --------------------------------------------------------------------- */
  function paintSections(root, _state) {
    const slot = root.querySelector('[data-role="balance-sections"]');
    if (!slot || !local.hasContent) return;

    slot.innerHTML = [
      paintColorBalanceHtml(),
      paintMechanicDistributionHtml(),
      paintConformanceIssuesHtml(),
      paintInteractionFlagsHtml(),
    ].join('');
  }

  function paintColorBalanceHtml() {
    const cb = local.colorBalance;
    const entries = Object.entries(cb);
    if (!entries.length) return '';

    const maxCount = Math.max(1, ...entries.map(([, n]) => n));
    const COLOR_ORDER = ['W', 'U', 'B', 'R', 'G'];
    const sorted = COLOR_ORDER
      .filter(c => cb[c] !== undefined)
      .map(c => [c, cb[c]])
      .concat(entries.filter(([c]) => !COLOR_ORDER.includes(c)));

    const rows = sorted.map(([color, count]) => {
      const pct = Math.round((count / maxCount) * 100);
      return `
        <span class="wiz-balance-color-label">${escHtml(color)}</span>
        <div class="wiz-balance-color-track">
          <div class="wiz-balance-color-fill" data-color="${escAttr(color)}" style="width:${pct}%"></div>
        </div>
        <span class="wiz-balance-color-count">${escHtml(String(count))}</span>
      `;
    }).join('');

    return `
      <div class="wiz-theme-section-header-row" style="margin-top:1.2rem">
        <h3 style="margin:0">Color balance</h3>
      </div>
      <div class="wiz-balance-color-grid">${rows}</div>
    `;
  }

  function paintMechanicDistributionHtml() {
    const dist = local.mechanicDistribution;
    if (!dist.length) return '';

    const rows = dist.map(m => {
      const planned = m.total_planned || 0;
      const actual = m.total_actual || 0;
      const delta = actual - planned;
      let deltaClass = 'ok';
      let deltaLabel = '✓';
      if (delta !== 0) {
        deltaClass = delta > 0 ? 'over' : 'under';
        deltaLabel = (delta > 0 ? '+' : '') + delta;
      }
      return `
        <tr>
          <td>${escHtml(m.mechanic_name)}</td>
          <td style="text-align:right;font-variant-numeric:tabular-nums">${escHtml(String(planned))}</td>
          <td style="text-align:right;font-variant-numeric:tabular-nums">${escHtml(String(actual))}</td>
          <td class="wiz-balance-mech-delta ${deltaClass}" style="text-align:right">${escHtml(deltaLabel)}</td>
        </tr>
      `;
    }).join('');

    return `
      <div class="wiz-theme-section-header-row" style="margin-top:1.2rem">
        <h3 style="margin:0">Mechanic distribution</h3>
      </div>
      <table class="wiz-balance-mech-table">
        <thead><tr>
          <th>Mechanic</th>
          <th style="text-align:right">Planned</th>
          <th style="text-align:right">Actual</th>
          <th style="text-align:right">Delta</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  function paintConformanceIssuesHtml() {
    // Show FAIL + WARN issues from the issues list (not interaction flags)
    const notable = local.issues.filter(i => i.severity === 'FAIL' || i.severity === 'WARN');
    if (!notable.length) return '';

    const items = notable.map(issue => {
      const metaParts = [];
      if (issue.check) metaParts.push(`<span>${escHtml(issue.check)}</span>`);
      if (issue.slot_id) metaParts.push(`<span>slot ${escHtml(issue.slot_id)}</span>`);
      if (issue.card_name) metaParts.push(`<span>${escHtml(issue.card_name)}</span>`);
      if (issue.expected && issue.actual) {
        metaParts.push(`<span>expected ${escHtml(issue.expected)}, got ${escHtml(issue.actual)}</span>`);
      }

      return `
        <div class="wiz-balance-issue-row">
          <span class="wiz-balance-issue-sev">
            <span class="wiz-balance-badge ${escAttr(issue.severity)}">${escHtml(issue.severity)}</span>
          </span>
          <div class="wiz-balance-issue-body">
            ${escHtml(issue.message)}
            ${metaParts.length ? `<div class="wiz-balance-issue-meta">${metaParts.join('')}</div>` : ''}
          </div>
        </div>
      `;
    }).join('');

    return `
      <div class="wiz-theme-section-header-row" style="margin-top:1.2rem">
        <h3 style="margin:0">Issues (${notable.length})</h3>
      </div>
      <div class="wiz-balance-issue-list">${items}</div>
    `;
  }

  function paintInteractionFlagsHtml() {
    const flags = local.interactionFlags;
    if (!flags.length) return '';

    const items = flags.map(flag => {
      const title = (flag.cards_involved || []).join(' + ');
      const rowSeverity = flag.severity === 'FAIL' ? 'FAIL' : 'WARN';
      return `
        <div class="wiz-balance-flag-row ${escAttr(rowSeverity)}">
          <div class="wiz-balance-flag-title">
            <span class="wiz-balance-badge ${escAttr(rowSeverity)}">${escHtml(rowSeverity)}</span>
            ${escHtml(title)}
            ${flag.interaction_type
              ? `<span style="color:#666;font-weight:400;font-size:0.77rem"> — ${escHtml(flag.interaction_type.replace(/_/g, ' '))}</span>`
              : ''}
          </div>
          <div class="wiz-balance-flag-desc">${escHtml(flag.description)}</div>
          ${flag.enabler_card ? `
            <div class="wiz-balance-flag-enabler">
              <strong>Enabler:</strong> ${escHtml(flag.enabler_card)}
              ${flag.enabler_slot_id ? `(slot ${escHtml(flag.enabler_slot_id)})` : ''}
              ${flag.why_enabler ? ` — ${escHtml(flag.why_enabler)}` : ''}
            </div>
          ` : ''}
          ${flag.replacement_constraint ? `
            <div class="wiz-balance-flag-constraint">Suggested replacement constraint: ${escHtml(flag.replacement_constraint)}</div>
          ` : ''}
        </div>
      `;
    }).join('');

    const summary = local.interactionAnalysis
      ? `<p style="color:#aaa;font-size:0.82rem;margin:0.5rem 0 0.8rem">${escHtml(local.interactionAnalysis)}</p>`
      : '';

    return `
      <div class="wiz-theme-section-header-row" style="margin-top:1.2rem">
        <h3 style="margin:0">Interaction flags (${flags.length})</h3>
      </div>
      ${summary}
      <div class="wiz-balance-flag-list">${items}</div>
    `;
  }

  /* -----------------------------------------------------------------------
   * Footer — Next-step button when paused; note otherwise
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
      html = `<span class="wiz-footer-note">Past stage — use the Edit button above to re-run balance analysis.</span>`;
    } else if (isPaused) {
      const next = W.nextStageEntryAfter(STAGE_ID);
      const label = next ? `Next step: ${next.name}` : 'Next step';
      html = `<button type="button" class="wiz-btn-primary" data-role="next-step">${escHtml(label)}</button>`;
    } else if (status === 'failed') {
      html = `<span class="wiz-footer-note">Stage failed — check the error above and re-run from Project Settings.</span>`;
    } else if (status === 'running') {
      html = `<span class="wiz-footer-note">Analysis is running…</span>`;
    } else {
      html = `<span class="wiz-footer-note">This stage runs automatically. Results appear here once complete.</span>`;
    }

    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
      // Reuse the standard bindNextStepButton from wizard_stage.js via POST /api/wizard/advance
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
        // On success leave disabled — SSE will update the pill + footer
      } catch (err) {
        W.toast('Network error: ' + err.message, 'error');
        btn.disabled = false;
        btn.textContent = original;
      }
    };
  }

  /* -----------------------------------------------------------------------
   * Form lock (§3) — no interactive inputs, but guard the footer button
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
