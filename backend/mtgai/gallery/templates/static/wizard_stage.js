/**
 * Wizard tab renderer — generic stage placeholder.
 *
 * Per design doc §8.3, every non-Theme stage in v1 renders as
 * "progress-bar + summary block + per-stage event log" — no rich
 * per-stage UI yet. Skeleton/Lands/Reprints already have richer dashboards
 * today; carrying those over is in scope for a later card. The Theme tab
 * has its own renderer in wizard_theme.js; the Project Settings tab has
 * its own renderer in wizard_project.js.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});

  W.registerTabRenderer('stage', renderStageTab);

  // ------------------------------------------------------------------
  // Stage tab
  // ------------------------------------------------------------------

  function renderStageTab({ tab, root, state }) {
    const content = root.querySelector('[data-role="content"]');
    const footer = root.querySelector('[data-role="footer"]');
    if (!content) return;

    const stage = findStage(state, tab.id);
    if (!stage) {
      content.innerHTML = '<div class="wiz-stage-empty">No stage state available.</div>';
      return;
    }

    content.innerHTML = stageBodyHtml(stage);

    if (footer) {
      footer.innerHTML = stageFooterHtml(stage, state);
    }

    const pill = root.querySelector('.wiz-status-pill');
    if (pill) {
      pill.className = 'wiz-status-pill ' + stage.status;
      pill.textContent = stage.status.replace(/_/g, ' ');
    }
  }

  function stageBodyHtml(stage) {
    const progress = stage.progress || {};
    const total = progress.total_items || 0;
    const completed = progress.completed_items || 0;
    const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
    const cost = progress.cost_usd > 0 ? '$' + progress.cost_usd.toFixed(3) : '—';
    const elapsed = formatElapsed(progress.started_at, progress.finished_at);
    const detail = progress.detail || progress.current_item || '';

    const progressBlock = total > 0
      ? `
        <div class="wiz-stage-progress">
          <div>${escHtml(detail || 'Working…')} (${completed}/${total} · ${pct}%)</div>
          <div class="wiz-stage-progress-bar">
            <div class="wiz-stage-progress-bar-fill" style="width: ${pct}%"></div>
          </div>
        </div>
      `
      : (stage.status === 'pending'
        ? '<div class="wiz-stage-empty">Stage has not started yet.</div>'
        : `<div class="wiz-stage-empty">${escHtml(detail || 'No detailed progress reported.')}</div>`
      );

    const errorBlock = progress.error_message
      ? `<div class="wiz-stage-error"><strong>Error:</strong> ${escHtml(progress.error_message)}</div>`
      : '';

    return `
      <dl class="wiz-stage-summary">
        <dt>Status</dt><dd>${escHtml(stage.status.replace(/_/g, ' '))}</dd>
        <dt>Cost</dt><dd>${cost}</dd>
        <dt>Elapsed</dt><dd>${elapsed || '—'}</dd>
        <dt>Review mode</dt><dd>${escHtml(stage.review_mode || 'auto')}</dd>
      </dl>
      ${progressBlock}
      ${errorBlock}
    `;
  }

  function stageFooterHtml(stage, state) {
    const isLatest = state.latestTabId === stage.stage_id;
    const isTerminal = stage.status === 'completed' || stage.status === 'paused_for_review';
    if (isLatest && isTerminal) {
      return `<span class="wiz-footer-note">Next-step button lands in a follow-up card.</span>`;
    }
    if (stage.status === 'failed') {
      return `<span class="wiz-footer-note">Retry support lands in a follow-up card.</span>`;
    }
    return '<span class="wiz-footer-note"></span>';
  }

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------

  function findStage(state, stageId) {
    if (!state.pipeline) return null;
    return state.pipeline.stages.find(s => s.stage_id === stageId) || null;
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
})();
