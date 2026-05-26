/**
 * Wizard Render QA tab — QA report: summary header + list of cards with
 * remaining MANUAL validation issues.
 *
 * Stage ID: `render_qa`. Re-runs validators on rendered cards.
 * Stage artifacts: { errors_found, cards_clean } + total cards in progress.
 *
 * `render_qa` is review_eligible — when paused_for_review the footer shows
 * the Next-step advance button (same pattern as `bindNextStepButton` in
 * wizard_stage.js, reproduced here since the custom renderer owns the footer).
 *
 * Conventions followed:
 *   §1  derived next-step footer button when paused_for_review
 *   §3  no editable surfaces — display-only, so form lock is a no-op
 *   §8  status pill flows from stage state via wizard_stage.js
 *   §9  Stop after this step — handled by wizard_stage.js
 *   §10 sticky progress strip — driven by SSE, not this module
 *
 * TODO: card issue detail and rendered thumbnails require
 *       GET /api/wizard/render_qa/state (not yet wired on the backend).
 *       The tab degrades gracefully to summary-only if the endpoint is absent.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'render_qa';

  const STYLE_ID = 'wiz-render-qa-styles';

  const local = {
    initialized: false,
    stageStatus: 'pending',
    // Populated by /api/wizard/render_qa/state when available.
    report: null, // { total, cards_clean, errors_found, issues: [{card_name, issues: [string]}] } | null
    bootstrapAttempted: false,
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ---------------------------------------------------------------------------
  // Styles
  // ---------------------------------------------------------------------------

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      /* --- render_qa tab -------------------------------------------------- */
      .wiz-rqa-summary-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 0.5rem;
        padding: 0.75rem 0.9rem;
        background: #0f1729;
        border: 1px solid #1f2540;
        border-radius: 6px;
        margin-bottom: 1rem;
      }
      .wiz-rqa-summary-headline {
        font-size: 0.95rem;
        color: #ddd;
        font-weight: 600;
      }
      .wiz-rqa-summary-clean { color: #00d4aa; }
      .wiz-rqa-summary-issues { color: #ffa502; }
      .wiz-rqa-summary-none { color: #666; font-style: italic; font-size: 0.85rem; }
      .wiz-rqa-summary-stats {
        display: flex;
        gap: 1rem;
        font-size: 0.82rem;
        color: #999;
        font-variant-numeric: tabular-nums;
      }
      .wiz-rqa-summary-stats span b { color: #ddd; }

      .wiz-rqa-section-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 0.5rem;
      }
      .wiz-rqa-section-header h3 { margin: 0; font-size: 0.9rem; color: #ccc; }

      .wiz-rqa-issue-list {
        list-style: none;
        margin: 0;
        padding: 0;
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
      }
      .wiz-rqa-issue-item {
        display: flex;
        gap: 0.75rem;
        background: #0f1729;
        border: 1px solid rgba(255, 165, 2, 0.2);
        border-radius: 6px;
        padding: 0.6rem 0.75rem;
        align-items: flex-start;
      }
      .wiz-rqa-thumb-wrap {
        flex: 0 0 56px;
      }
      .wiz-rqa-thumb {
        width: 56px;
        background: #16213e;
        border: 1px solid #1f2540;
        border-radius: 4px;
        aspect-ratio: 822 / 1122;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.55rem;
        color: #555;
        text-align: center;
        overflow: hidden;
        word-break: break-word;
        padding: 2px;
      }
      .wiz-rqa-thumb img {
        width: 100%;
        height: 100%;
        object-fit: contain;
        border-radius: 3px;
      }
      .wiz-rqa-issue-body {
        flex: 1 1 auto;
        min-width: 0;
      }
      .wiz-rqa-card-name {
        font-size: 0.85rem;
        font-weight: 600;
        color: #e0e0e0;
        margin-bottom: 0.25rem;
      }
      .wiz-rqa-card-issues {
        list-style: disc;
        margin: 0;
        padding-left: 1.1rem;
        font-size: 0.78rem;
        color: #ffa502cc;
        display: flex;
        flex-direction: column;
        gap: 0.15rem;
      }

      .wiz-rqa-progress {
        background: #0f1729;
        border: 1px solid #1f2540;
        border-radius: 6px;
        padding: 0.75rem 0.9rem;
        margin-bottom: 1rem;
      }
      .wiz-rqa-progress-header {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        margin-bottom: 0.4rem;
        font-size: 0.85rem;
        color: #ddd;
      }
      .wiz-rqa-bar {
        height: 6px;
        background: #1a1a2e;
        border-radius: 3px;
        overflow: hidden;
        margin-top: 0.4rem;
      }
      .wiz-rqa-bar-fill {
        height: 100%;
        background: #4a9eff;
        border-radius: 3px;
        transition: width 0.3s ease;
      }
      .wiz-rqa-empty {
        color: #666;
        font-style: italic;
        font-size: 0.85rem;
        padding: 1rem 0;
      }
      .wiz-rqa-all-clean {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.75rem 0.9rem;
        background: rgba(0, 212, 170, 0.06);
        border: 1px solid rgba(0, 212, 170, 0.2);
        border-radius: 6px;
        color: #00d4aa;
        font-size: 0.88rem;
        font-weight: 600;
      }
      .wiz-rqa-note {
        font-size: 0.75rem;
        color: #555;
        margin-top: 0.75rem;
        font-style: italic;
      }
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

      // Attempt to pull detailed QA report once if the stage has completed.
      if (stage && (stage.status === 'completed' || stage.status === 'paused_for_review')) {
        fetchReport().catch(() => {/* degrades gracefully */});
      }

      paintBody(root, stage);
      paintFooter(footer, state, stage);
      return;
    }

    // Re-render path — update status and repaint reactively.
    const prevStatus = local.stageStatus;
    if (stage) local.stageStatus = stage.status;

    // If the stage just finished and we haven't tried fetching the report yet, fetch now.
    const justFinished = stage
      && prevStatus !== local.stageStatus
      && (local.stageStatus === 'completed' || local.stageStatus === 'paused_for_review')
      && !local.bootstrapAttempted;
    if (justFinished) {
      fetchReport().catch(() => {/* degrades gracefully */});
    }

    paintBody(root, stage);
    paintFooter(footer, state, stage);
  }

  function mountShellHtml() {
    return `
      <div data-role="rqa-body"></div>
    `;
  }

  // ---------------------------------------------------------------------------
  // Fetch detailed report from backend (best-effort)
  // ---------------------------------------------------------------------------

  async function fetchReport() {
    local.bootstrapAttempted = true;
    try {
      // TODO: GET /api/wizard/render_qa/state must be wired on the backend.
      // Expected response shape:
      //   { total: number, cards_clean: number, errors_found: number,
      //     issues: [{ card_name: string, issues: string[] }] }
      const resp = await fetch('/api/wizard/render_qa/state');
      if (!resp.ok) return; // silently degrade — summary from stage.progress still shows
      const data = await resp.json();
      if (data && typeof data.total === 'number') {
        local.report = data;
      }
    } catch (_) {/* non-critical */}

    const root = bodyRoot();
    if (root) {
      const stage = findCurrentStage();
      paintBody(root, stage);
    }
  }

  function findCurrentStage() {
    const state = W.getState ? W.getState() : null;
    if (!state || !state.pipeline) return null;
    return state.pipeline.stages.find(s => s.stage_id === STAGE_ID) || null;
  }

  // ---------------------------------------------------------------------------
  // Body
  // ---------------------------------------------------------------------------

  function paintBody(root, stage) {
    const slot = root.querySelector('[data-role="rqa-body"]');
    if (!slot) return;

    const status = stage ? stage.status : local.stageStatus;
    const progress = stage ? (stage.progress || {}) : {};

    // --- Pending or running --- show progress bar only.
    if (status === 'pending' || status === 'running') {
      slot.innerHTML = paintRunningHtml(status, progress);
      return;
    }

    // --- Failed --- show error block.
    if (status === 'failed') {
      const errMsg = progress.error_message || 'Render QA stage failed.';
      slot.innerHTML = `<div class="wiz-stage-error"><strong>Error:</strong> ${escHtml(errMsg)}</div>`;
      return;
    }

    // --- Completed / paused_for_review ---
    // Use detailed report if available; fall back to stage.progress artifacts.
    const artifacts = progress.artifacts || {};
    const total = local.report ? local.report.total : (progress.total_items || 0);
    const cardsClean = local.report ? local.report.cards_clean : (artifacts.cards_clean || 0);
    const errorsFound = local.report ? local.report.errors_found : (artifacts.errors_found || 0);
    const issues = local.report ? (local.report.issues || []) : [];
    const elapsed = formatElapsed(progress.started_at, progress.finished_at);

    slot.innerHTML = summaryHeaderHtml(total, cardsClean, errorsFound, elapsed)
      + issueListHtml(issues, errorsFound, total);
  }

  function paintRunningHtml(status, progress) {
    if (status === 'pending') {
      return '<div class="wiz-rqa-empty">Stage has not started yet.</div>';
    }
    const total = progress.total_items || 0;
    const completed = progress.completed_items || 0;
    const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
    const detail = progress.detail || progress.current_item || 'Validating rendered cards…';
    return `
      <div class="wiz-rqa-progress">
        <div class="wiz-rqa-progress-header">
          <span>${escHtml(detail)}</span>
          <span style="color:#999;font-size:0.78rem;font-variant-numeric:tabular-nums">${total > 0 ? pct + '%' : ''}</span>
        </div>
        ${total > 0 ? `
          <div class="wiz-rqa-bar">
            <div class="wiz-rqa-bar-fill" style="width:${pct}%"></div>
          </div>` : ''}
      </div>`;
  }

  function summaryHeaderHtml(total, cardsClean, errorsFound, elapsed) {
    let headline;
    if (total === 0) {
      headline = '<span class="wiz-rqa-summary-none">No cards found.</span>';
    } else if (errorsFound === 0) {
      headline = `<span class="wiz-rqa-summary-clean">${cardsClean}/${total} cards clean — all good!</span>`;
    } else {
      headline = `<span class="wiz-rqa-summary-issues">${cardsClean}/${total} cards clean · ${errorsFound} issue${errorsFound !== 1 ? 's' : ''} remaining</span>`;
    }
    const statsHtml = [
      total > 0 ? `<span><b>${total}</b> total</span>` : '',
      cardsClean > 0 ? `<span><b>${cardsClean}</b> clean</span>` : '',
      errorsFound > 0 ? `<span style="color:#ffa502"><b>${errorsFound}</b> issues</span>` : '',
      elapsed ? `<span>${escHtml(elapsed)}</span>` : '',
    ].filter(Boolean).join('');

    return `
      <div class="wiz-rqa-summary-header">
        <div class="wiz-rqa-summary-headline">${headline}</div>
        ${statsHtml ? `<div class="wiz-rqa-summary-stats">${statsHtml}</div>` : ''}
      </div>`;
  }

  function issueListHtml(issues, errorsFound, total) {
    if (total === 0) return '';

    if (!issues.length) {
      // No detailed issue data (endpoint not yet available), but we have a count.
      if (errorsFound === 0) {
        return `<div class="wiz-rqa-all-clean">✓ All cards passed validation.</div>`;
      }
      return `
        <div class="wiz-rqa-section-header"><h3>Cards with issues</h3></div>
        <div class="wiz-rqa-empty">
          Detailed issue list requires <code>/api/wizard/render_qa/state</code> — not yet wired up.
        </div>
        <p class="wiz-rqa-note">${errorsFound} MANUAL validation issue${errorsFound !== 1 ? 's' : ''} found across all cards.</p>`;
    }

    // Partition into flagged and clean.
    const flagged = issues.filter(i => i.issues && i.issues.length > 0);

    if (flagged.length === 0) {
      return `<div class="wiz-rqa-all-clean">✓ All cards passed validation — no MANUAL issues found.</div>`;
    }

    const itemsHtml = flagged.map(entry => {
      const name = entry.card_name || 'Unknown card';
      const issueItems = (entry.issues || []).map(iss =>
        `<li>${escHtml(iss)}</li>`
      ).join('');
      // TODO: replace placeholder thumb with real image once /api/wizard/rendering/image/<name>
      // (or equivalent) is available.
      return `
        <li class="wiz-rqa-issue-item">
          <div class="wiz-rqa-thumb-wrap">
            <div class="wiz-rqa-thumb" title="${escAttr(name)}">${escHtml(name.substring(0, 18))}</div>
          </div>
          <div class="wiz-rqa-issue-body">
            <div class="wiz-rqa-card-name">${escHtml(name)}</div>
            <ul class="wiz-rqa-card-issues">${issueItems}</ul>
          </div>
        </li>`;
    }).join('');

    return `
      <div class="wiz-rqa-section-header">
        <h3>Cards with issues (${flagged.length})</h3>
      </div>
      <ul class="wiz-rqa-issue-list">${itemsHtml}</ul>
      <p class="wiz-rqa-note">Only MANUAL validation issues are shown (AUTO issues are fixed programmatically before this point).</p>`;
  }

  // ---------------------------------------------------------------------------
  // Footer — derive next-step button when paused_for_review (§1)
  // ---------------------------------------------------------------------------

  function paintFooter(footer, state, stage) {
    if (!footer) return;

    const status = stage ? stage.status : local.stageStatus;
    const isLatest = !state || state.latestTabId === STAGE_ID;

    let html;
    if (!isLatest) {
      html = '<span class="wiz-footer-note">Past tab — editing not required for this QA stage.</span>';
    } else if (status === 'paused_for_review') {
      const next = W.nextStageEntryAfter(STAGE_ID);
      const label = next ? `Next step: ${escHtml(next.name)}` : 'Next step';
      html = `<button type="button" class="wiz-btn-primary" data-role="rqa-next-step">${label}</button>`;
    } else if (status === 'running') {
      html = '<span class="wiz-footer-note">QA check in progress…</span>';
    } else if (status === 'failed') {
      html = '<span class="wiz-footer-note">Stage failed — see error above. Retry support lands in a follow-up card.</span>';
    } else if (status === 'completed') {
      const next = W.nextStageEntryAfter(STAGE_ID);
      const nextName = next ? next.name : 'the next stage';
      html = `<span class="wiz-footer-note">QA complete. Engine continues automatically to ${escHtml(nextName)}.</span>`;
    } else {
      html = '<span class="wiz-footer-note">Stage has not started yet.</span>';
    }

    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
    }

    // Bind next-step advance button (mirrors wizard_stage.js bindNextStepButton).
    const btn = footer.querySelector('button[data-role="rqa-next-step"]');
    if (btn) btn.onclick = onNextStep;
  }

  async function onNextStep() {
    const footer = document.querySelector(
      `.wiz-tab-body[data-tab-id="${STAGE_ID}"] [data-role="footer"]`
    );
    const btn = footer && footer.querySelector('button[data-role="rqa-next-step"]');
    const original = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = 'Advancing…'; }
    try {
      const resp = await W.postJSON('/api/wizard/advance', {});
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        if (resp.status === 409 && data.running_action) {
          W.toast(`${data.running_action} is in progress — try again when it finishes.`, 'error');
        } else {
          W.toast(data.error || `Advance failed (${resp.status})`, 'error');
        }
        if (btn) { btn.disabled = false; btn.textContent = original; }
      }
      // On success: leave button disabled — SSE will repaint footer when stage transitions.
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
      if (btn) { btn.disabled = false; btn.textContent = original; }
    }
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function bodyRoot() {
    return document.querySelector(`.wiz-tab-body[data-tab-id="${STAGE_ID}"]`);
  }

  function formatElapsed(startedAt, finishedAt) {
    if (!startedAt) return '';
    const start = new Date(startedAt);
    const end = finishedAt ? new Date(finishedAt) : new Date();
    const seconds = Math.round((end - start) / 1000);
    if (seconds < 60) return seconds + 's';
    if (seconds < 3600) return Math.floor(seconds / 60) + 'm ' + (seconds % 60) + 's';
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    return hours + 'h ' + mins + 'm';
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
