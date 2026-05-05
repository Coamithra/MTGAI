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
    const headerActions = root.querySelector('[data-role="header-actions"]');
    if (!content) return;

    const stage = findStage(state, tab.id);
    if (!stage) {
      content.innerHTML = '<div class="wiz-stage-empty">No stage state available.</div>';
      return;
    }

    content.innerHTML = stageBodyHtml(stage);

    if (footer) {
      const desiredFooter = stageFooterHtml(stage, state);
      if (footer.dataset.lastFooter !== desiredFooter) {
        footer.innerHTML = desiredFooter;
        footer.dataset.lastFooter = desiredFooter;
        bindNextStepButton(footer, state);
      }
    }

    if (headerActions) {
      // Idempotent re-render: SSE-driven rerenders fire on every
      // stage_update / item_progress event. Replacing innerHTML on
      // each tick would detach an in-flight click's checkbox before
      // its POST resolves and re-bind a fresh listener, so guard on
      // the value the toggle currently displays.
      const desiredChecked = !!stage.always_review || !!state.breakPoints[stage.stage_id];
      const existing = headerActions.querySelector('input[data-role="stage-break"]');
      const existingChecked = existing && existing.checked;
      if (!existing || existingChecked !== desiredChecked) {
        headerActions.innerHTML = breakPointToggleHtml(stage, state);
        bindBreakPointToggle(headerActions, stage, state);
      }
    }

    const pill = root.querySelector('.wiz-status-pill');
    if (pill) {
      pill.className = 'wiz-status-pill ' + stage.status;
      pill.textContent = stage.status.replace(/_/g, ' ');
    }
  }

  // ------------------------------------------------------------------
  // Break-point toggle (per design §6.7 / §8.2)
  // ------------------------------------------------------------------

  function breakPointToggleHtml(stage, state) {
    const lockedOn = !!stage.always_review;
    const checked = lockedOn || !!state.breakPoints[stage.stage_id];
    const disabledAttr = lockedOn ? 'disabled aria-disabled="true"' : '';
    const titleAttr = lockedOn
      ? ' title="Always pauses for review"'
      : ' title="When checked, the wizard pauses after this stage finishes."';
    const labelText = lockedOn ? 'Stop after this step (always on)' : 'Stop after this step';
    const lockGlyph = lockedOn ? ' <span class="wiz-bp-lock" aria-hidden="true">🔒</span>' : '';
    return `
      <label class="wiz-stage-break-toggle"${titleAttr}>
        <input
          type="checkbox"
          data-role="stage-break"
          ${checked ? 'checked' : ''}
          ${disabledAttr}
        >
        ${labelText}${lockGlyph}
      </label>
    `;
  }

  function bindBreakPointToggle(container, stage, state) {
    const cb = container.querySelector('input[data-role="stage-break"]');
    if (!cb || cb.disabled) return;
    cb.addEventListener('change', async () => {
      const desired = cb.checked;
      try {
        const resp = await window.MTGAIWizard.postJSON('/api/wizard/project/breaks', {
          set_code: state.activeSet,
          stage_id: stage.stage_id,
          review: desired,
        });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          window.MTGAIWizard.toast(data.error || 'Save failed', 'error');
          cb.checked = !desired;
          return;
        }
        state.breakPoints[stage.stage_id] = desired;
        // Notify peer renderers (Project Settings) that a break-point
        // bit changed. wizard_project listens via this hook so its
        // checkbox row stays in sync without a refetch.
        if (typeof window.MTGAIWizard.onBreakPointChanged === 'function') {
          window.MTGAIWizard.onBreakPointChanged(stage.stage_id, desired);
        }
      } catch (err) {
        window.MTGAIWizard.toast('Network error: ' + err.message, 'error');
        cb.checked = !desired;
      }
    });
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

  // Pipeline stage order — kept in sync with backend STAGE_DEFINITIONS so
  // we can render "Next step: <name>" without an extra fetch. Anything
  // not in this list (e.g. legacy or future stages) falls back to the
  // generic "Next step" label so a stale client still works.
  const STAGE_ORDER = [
    { id: 'skeleton', name: 'Skeleton Generation' },
    { id: 'reprints', name: 'Reprint Selection' },
    { id: 'lands', name: 'Land Generation' },
    { id: 'card_gen', name: 'Card Generation' },
    { id: 'balance', name: 'Balance Analysis' },
    { id: 'skeleton_rev', name: 'Skeleton Revision' },
    { id: 'ai_review', name: 'AI Design Review' },
    { id: 'finalize', name: 'Finalization' },
    { id: 'human_card_review', name: 'Card Review' },
    { id: 'art_prompts', name: 'Art Prompt Generation' },
    { id: 'char_portraits', name: 'Character Portraits' },
    { id: 'art_gen', name: 'Art Generation' },
    { id: 'art_select', name: 'Art Selection' },
    { id: 'human_art_review', name: 'Art Review' },
    { id: 'rendering', name: 'Card Rendering' },
    { id: 'render_qa', name: 'Render QA' },
    { id: 'human_final_review', name: 'Final Review' },
  ];

  const FINAL_STAGE_ID = STAGE_ORDER[STAGE_ORDER.length - 1].id;

  function nextStageEntry(stageId) {
    const idx = STAGE_ORDER.findIndex(s => s.id === stageId);
    if (idx < 0 || idx === STAGE_ORDER.length - 1) return null;
    return STAGE_ORDER[idx + 1];
  }

  function stageFooterHtml(stage, state) {
    const isLatest = state.latestTabId === stage.stage_id;

    // Final tab + completed = "Set complete" terminal state (§8.4).
    if (
      isLatest
      && stage.stage_id === FINAL_STAGE_ID
      && stage.status === 'completed'
    ) {
      return `<span class="wiz-footer-complete" role="status">✓ Set complete</span>`;
    }

    // Latest tab + paused_for_review = manual Next-step gesture. The
    // engine has yielded the AI mutex and is waiting for the user.
    // Auto-advance handles the COMPLETED-on-non-final case server-side
    // (the engine just walks to the next stage), so we only render
    // Next-step on PAUSED_FOR_REVIEW.
    if (isLatest && stage.status === 'paused_for_review') {
      const next = nextStageEntry(stage.stage_id);
      const label = next ? `Next step: ${next.name}` : 'Next step';
      return `<button type="button" class="wiz-btn-primary" data-role="next-step">${escHtml(label)}</button>`;
    }

    if (stage.status === 'failed') {
      return `<span class="wiz-footer-note">Retry support lands in a follow-up card.</span>`;
    }
    return '<span class="wiz-footer-note"></span>';
  }

  function bindNextStepButton(footer, state) {
    const btn = footer.querySelector('button[data-role="next-step"]');
    if (!btn) return;
    btn.addEventListener('click', async () => {
      const original = btn.textContent;
      btn.disabled = true;
      btn.textContent = 'Advancing…';
      try {
        const resp = await window.MTGAIWizard.postJSON('/api/wizard/advance', {
          set_code: state.activeSet,
        });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          window.MTGAIWizard.toast(data.error || 'Advance failed', 'error');
          btn.disabled = false;
          btn.textContent = original;
          return;
        }
        // Success: leave the button disabled — the engine is now
        // running, and the SSE stream will repaint the footer in place
        // when the next stage enters PAUSED_FOR_REVIEW or this tab's
        // status transitions away from paused_for_review.
        btn.textContent = 'Advancing…';
      } catch (err) {
        window.MTGAIWizard.toast('Network error: ' + err.message, 'error');
        btn.disabled = false;
        btn.textContent = original;
      }
    });
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
