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

  // Per-stage body + footer renderers. Stages with bespoke UI (e.g.
  // ``mechanics`` candidates strip) call ``W.registerStageRenderer``
  // at module load time; the standard placeholder is used for stages
  // without an entry. The custom renderer owns content + footer
  // (header pill, break-point toggle, and edit button still come
  // from the standard shell). Editing-mode renders the standard
  // cancel/accept UI even on stages with custom renderers — the
  // cascade is identical for every stage tab.
  const customStageRenderers = {};
  W.registerStageRenderer = function (stageId, fn) {
    customStageRenderers[stageId] = fn;
  };

  // ------------------------------------------------------------------
  // Stage tab
  // ------------------------------------------------------------------

  function renderStageTab({ tab, root, state, rerender }) {
    const content = root.querySelector('[data-role="content"]');
    const footer = root.querySelector('[data-role="footer"]');
    const headerActions = root.querySelector('[data-role="header-actions"]');
    if (!content) return;

    const stage = findStage(state, tab.id);
    if (!stage) {
      content.innerHTML = '<div class="wiz-stage-empty">No stage state available.</div>';
      return;
    }

    const editing = !!(W.editFlow && W.editFlow.getDraft(tab.id));
    const custom = !editing ? customStageRenderers[stage.stage_id] : null;

    if (custom) {
      // Custom renderer owns content + footer. We still update the
      // header pill below + break-point toggle / edit button via
      // headerActions. The renderer is responsible for being
      // idempotent on rerender (SSE-driven repaints fire on every
      // stage_update event).
      try {
        custom({ tab, root, state, stage, content, footer, rerender: !!rerender });
      } catch (err) {
        console.error('Custom stage renderer failed for', stage.stage_id, err);
        content.innerHTML = '<div class="wiz-stage-error">Stage renderer failed — see console.</div>';
      }
    } else {
      const banner = editing
        ? '<div class="wiz-edit-banner">Editing — Accept will discard everything from this stage onward and re-run.</div>'
        : '';
      content.innerHTML = banner + stageBodyHtml(stage);

      if (footer) {
        const desiredFooter = editing
          ? editFooterHtml()
          : stageFooterHtml(stage, state);
        if (footer.dataset.lastFooter !== desiredFooter) {
          footer.innerHTML = desiredFooter;
          footer.dataset.lastFooter = desiredFooter;
          if (editing) bindStageEditActions(footer, tab, state);
          else bindNextStepButton(footer, state);
        }
      }
    }

    if (headerActions) {
      // Idempotent re-render: SSE-driven rerenders fire on every
      // stage_update / item_progress event. Replacing innerHTML on
      // each tick would detach an in-flight click's checkbox before
      // its POST resolves and re-bind a fresh listener, so guard on
      // a desired-state fingerprint covering both the break-point
      // toggle and the Edit button visibility.
      const fingerprint = JSON.stringify({
        bp: !!state.breakPoints[stage.stage_id],
        editVisible: shouldShowEditButton(stage),
        editing,
      });
      if (headerActions.dataset.actionsFp !== fingerprint) {
        headerActions.innerHTML = breakPointToggleHtml(stage, state)
          + editButtonHtml(stage);
        headerActions.dataset.actionsFp = fingerprint;
        bindBreakPointToggle(headerActions, stage, state);
        bindEditButton(headerActions, tab, state);
      }
    }

    const pill = root.querySelector('.wiz-status-pill');
    if (pill) {
      pill.className = 'wiz-status-pill ' + stage.status;
      pill.textContent = stage.status.replace(/_/g, ' ');
    }
  }

  // ------------------------------------------------------------------
  // Edit button + cascade flow (design §9)
  // ------------------------------------------------------------------

  // Show Edit on a past stage tab when nothing is currently generating.
  // Latest-tab edits happen in place per §9.4 — the latest tab is
  // whatever the wizard considers furthest-along, so it never gets the
  // gate. Pipeline-running suppresses Edit entirely; the modal would
  // 409 anyway.
  function shouldShowEditButton(stage) {
    if (!W.editFlow) return false;
    if (W.editFlow.isPipelineRunning()) return false;
    return W.editFlow.isPastTab(stage.stage_id);
  }

  function editButtonHtml(stage) {
    if (!shouldShowEditButton(stage)) return '';
    const editing = !!W.editFlow.getDraft(stage.stage_id);
    if (editing) return '';
    return `<button type="button" class="wiz-btn-secondary" data-role="stage-edit">Edit</button>`;
  }

  function bindEditButton(container, tab, state) {
    const btn = container.querySelector('button[data-role="stage-edit"]');
    if (!btn) return;
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      try {
        const ok = await W.editFlow.confirmCascade({
          from_stage: tab.id,
          title: `Edit ${tab.title}`,
          body:
            `Editing ${tab.title} will discard all generated content from this stage onward `
            + `(${tab.title} itself will re-run on Accept).`,
        });
        if (!ok) return;
        // No editable form on stage tabs in v1 — store an empty draft so
        // the pencil + banner show, then the Accept button cascades.
        W.editFlow.setDraft(tab.id, { dirty: false, payload: {} });
        // Re-render this tab's body to swap in the edit banner + actions.
        const body = document.querySelector(
          `.wiz-tab-body[data-tab-id="${cssEsc(tab.id)}"]`,
        );
        if (body) renderStageTab({ tab, root: body, state });
      } finally {
        btn.disabled = false;
      }
    });
  }

  function editFooterHtml() {
    return `
      <div class="wiz-edit-actions">
        <button type="button" class="wiz-btn-secondary" data-role="stage-edit-cancel">Cancel</button>
        <button type="button" class="wiz-btn-primary" data-role="stage-edit-accept">Accept</button>
      </div>
    `;
  }

  function bindStageEditActions(footer, tab, state) {
    const cancel = footer.querySelector('button[data-role="stage-edit-cancel"]');
    const accept = footer.querySelector('button[data-role="stage-edit-accept"]');
    if (cancel) {
      cancel.onclick = () => {
        W.editFlow.clearDraft(tab.id);
        const body = document.querySelector(
          `.wiz-tab-body[data-tab-id="${cssEsc(tab.id)}"]`,
        );
        if (body) renderStageTab({ tab, root: body, state });
      };
    }
    if (accept) {
      accept.onclick = async () => {
        accept.disabled = true;
        const original = accept.textContent;
        accept.textContent = 'Applying…';
        try {
          const data = await W.editFlow.accept({ from_stage: tab.id });
          W.editFlow.clearDraft(tab.id);
          if (data.warning) W.MTGAIWizard.toast(data.warning, 'warn');
          // Hard-reload so the wizard rebuilds the tab strip + state
          // from the freshly-cleared pipeline-state.json. Soft repaint
          // would work but reload keeps the bootstrap payload as the
          // source of truth (matches the Theme→Skeleton handoff).
          window.location.assign(data.navigate_to || '/pipeline');
        } catch (err) {
          accept.disabled = false;
          accept.textContent = original;
          if (err.status === 409) {
            W.MTGAIWizard.toast(err.message, 'warn');
          } else {
            W.MTGAIWizard.toast('Accept failed: ' + err.message, 'error');
          }
        }
      };
    }
  }

  function cssEsc(s) {
    if (window.CSS && CSS.escape) return CSS.escape(s);
    return String(s).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
  }

  // ------------------------------------------------------------------
  // Break-point toggle (per design §6.7 / §8.2)
  // ------------------------------------------------------------------

  function breakPointToggleHtml(stage, state) {
    const checked = !!state.breakPoints[stage.stage_id];
    return `
      <label class="wiz-stage-break-toggle" title="When checked, the wizard pauses after this stage finishes.">
        <input type="checkbox" data-role="stage-break" ${checked ? 'checked' : ''}>
        Stop after this step
      </label>
    `;
  }

  function bindBreakPointToggle(container, stage, state) {
    const cb = container.querySelector('input[data-role="stage-break"]');
    if (!cb) return;
    cb.addEventListener('change', async () => {
      const desired = cb.checked;
      try {
        const resp = await window.MTGAIWizard.postJSON('/api/wizard/project/breaks', {
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

  // Next-stage display name comes from state.pipeline.stages, which is
  // sourced from the backend's STAGE_DEFINITIONS. Avoids duplicating
  // the stage list client-side (so adding a stage server-side doesn't
  // silently regress the footer label here).
  function nextStageEntryAfter(state, stageId) {
    if (!state.pipeline || !state.pipeline.stages) return null;
    const stages = state.pipeline.stages;
    const idx = stages.findIndex(s => s.stage_id === stageId);
    if (idx < 0 || idx === stages.length - 1) return null;
    const next = stages[idx + 1];
    return { id: next.stage_id, name: next.display_name };
  }

  function isFinalStage(state, stageId) {
    if (!state.pipeline || !state.pipeline.stages) return false;
    const stages = state.pipeline.stages;
    return stages.length > 0 && stages[stages.length - 1].stage_id === stageId;
  }

  function stageFooterHtml(stage, state) {
    const isLatest = state.latestTabId === stage.stage_id;

    // Final tab + completed = "Set complete" terminal state (§8.4).
    if (isLatest && isFinalStage(state, stage.stage_id) && stage.status === 'completed') {
      return `<span class="wiz-footer-complete" role="status">✓ Set complete</span>`;
    }

    // Latest tab + paused_for_review = manual Next-step gesture. The
    // engine has yielded the AI mutex and is waiting for the user.
    // Auto-advance handles the COMPLETED-on-non-final case server-side
    // (the engine just walks to the next stage), so we only render
    // Next-step on PAUSED_FOR_REVIEW.
    if (isLatest && stage.status === 'paused_for_review') {
      const next = nextStageEntryAfter(state, stage.stage_id);
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
    // Single-slot via .onclick (not addEventListener) so a hypothetical
    // re-bind on the same DOM node would replace rather than stack.
    btn.onclick = async () => {
      const original = btn.textContent;
      btn.disabled = true;
      btn.textContent = 'Advancing…';
      try {
        const resp = await window.MTGAIWizard.postJSON('/api/wizard/advance', {});
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
      } catch (err) {
        window.MTGAIWizard.toast('Network error: ' + err.message, 'error');
        btn.disabled = false;
        btn.textContent = original;
      }
    };
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
