/**
 * Pipeline dashboard — SSE client, stage rendering, action buttons.
 *
 * Expects PIPELINE_STATE to be set as a global variable by the template
 * (null if no pipeline exists).
 */

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let pipelineState = PIPELINE_STATE;
let eventSource = null;

const STATUS_BADGES = {
  pending:           { text: 'Pending',  cls: 'badge-pending' },
  running:           { text: 'Running',  cls: 'badge-running' },
  paused_for_review: { text: 'Review',   cls: 'badge-paused' },
  completed:         { text: 'Done',     cls: 'badge-completed' },
  failed:            { text: 'Failed',   cls: 'badge-failed' },
  skipped:           { text: 'Skipped',  cls: 'badge-skipped' },
};

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  if (pipelineState) {
    renderDashboard();
    connectSSE();
  }
  // If pipelineState is null we shouldn't be on this page at all —
  // the server routes /pipeline to the configure form when no state
  // exists. The check stays as a defensive belt-and-braces.
});

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function renderDashboard() {
  const app = document.getElementById('pipeline-app');
  const state = pipelineState;
  const stages = state.stages;

  // Calculate overall progress
  const completedCount = stages.filter(s =>
    s.status === 'completed' || s.status === 'skipped'
  ).length;
  const pct = stages.length > 0 ? Math.round((completedCount / stages.length) * 100) : 0;

  // Find current stage for display
  const currentStage = stages.find(s => s.stage_id === state.current_stage_id);
  const statusLabel = formatPipelineStatus(state.overall_status);

  app.innerHTML = `
    <div class="pipeline-header">
      <div>
        <h1>${escapeHtml(state.config.set_name || state.config.set_code)} Pipeline</h1>
        <span style="color: #888; font-size: 0.85rem;">
          ${state.config.set_code} &middot; ${state.config.set_size} cards &middot; ${statusLabel}
        </span>
      </div>
      <div class="pipeline-stats">
        <div class="pipeline-stat">
          <div class="stat-value">${completedCount}/${stages.length}</div>
          <div class="stat-label">Stages</div>
        </div>
        <div class="pipeline-stat">
          <div class="stat-value">$${state.total_cost_usd.toFixed(2)}</div>
          <div class="stat-label">Cost</div>
        </div>
        <div class="pipeline-stat">
          <div class="stat-value">${pct}%</div>
          <div class="stat-label">Progress</div>
        </div>
      </div>
    </div>

    <div class="overall-progress">
      <div class="overall-progress-fill" style="width: ${pct}%"></div>
    </div>

    <div class="pipeline-actions" id="pipeline-actions">
      ${renderActionButtons(state)}
    </div>

    <div class="stage-list" id="stage-list">
      ${stages.map((s, i) => renderStageCard(s, i + 1)).join('')}
    </div>
  `;
}

function renderStageCard(stage, num) {
  const badge = STATUS_BADGES[stage.status] || STATUS_BADGES.pending;
  const progress = stage.progress || {};
  const hasProgress = progress.total_items > 0;
  const pct = hasProgress
    ? Math.round((progress.completed_items / progress.total_items) * 100)
    : 0;

  const reviewTag = stage.review_mode === 'review' && !stage.always_review
    ? '<span class="review-indicator">REVIEW</span>'
    : stage.always_review
    ? '<span class="review-indicator">HUMAN</span>'
    : '';

  const detail = progress.detail || progress.current_item || '';
  const cost = progress.cost_usd > 0 ? `$${progress.cost_usd.toFixed(3)}` : '';
  const elapsed = formatElapsed(progress.started_at, progress.finished_at);

  return `
    <div class="stage-card ${stage.status}" id="stage-${stage.stage_id}">
      <div class="stage-num">${stage.status === 'completed' ? '&#10003;' : stage.status === 'failed' ? '&#10007;' : num}</div>
      <div class="stage-info">
        <div class="stage-name">${escapeHtml(stage.display_name)}${reviewTag}</div>
        <div class="stage-detail">${escapeHtml(detail)}</div>
      </div>
      ${hasProgress && stage.status === 'running' ? `
        <div class="stage-progress-bar">
          <div class="stage-progress-fill" style="width: ${pct}%"></div>
        </div>
      ` : ''}
      <div class="stage-meta">
        ${cost ? `<span>${cost}</span>` : ''}
        ${elapsed ? `<span>${elapsed}</span>` : ''}
      </div>
      <span class="stage-badge ${badge.cls}">${badge.text}</span>
    </div>
  `;
}

function renderActionButtons(state) {
  const status = state.overall_status;
  const buttons = [];

  if (status === 'paused') {
    buttons.push(`<button class="btn btn-resume" onclick="resumePipeline()">Continue Pipeline</button>`);
    buttons.push(`<button class="btn btn-skip" onclick="skipStage()">Skip Stage</button>`);
  }
  if (status === 'running') {
    buttons.push(`<button class="btn btn-cancel" onclick="cancelPipeline()">Cancel</button>`);
  }
  if (status === 'failed') {
    buttons.push(`<button class="btn btn-retry" onclick="retryStage()">Retry Failed Stage</button>`);
    buttons.push(`<button class="btn btn-skip" onclick="skipStage()">Skip Stage</button>`);
  }
  if (status === 'completed' || status === 'cancelled' || status === 'not_started') {
    buttons.push(`<a href="/pipeline/configure" class="btn btn-configure">Configure New Run</a>`);
  }
  // Always show review link when paused at a human review stage
  const current = state.stages.find(s => s.stage_id === state.current_stage_id);
  if (current && current.status === 'paused_for_review' && current.always_review) {
    buttons.push(`<a href="/review" class="btn btn-configure">Open Review Gallery</a>`);
  }

  return buttons.join('');
}

// ---------------------------------------------------------------------------
// SSE connection
// ---------------------------------------------------------------------------

function connectSSE() {
  if (eventSource) {
    eventSource.close();
  }

  eventSource = new EventSource('/api/pipeline/events');

  eventSource.addEventListener('stage_update', (e) => {
    const data = JSON.parse(e.data);
    updateStage(data.stage_id, data.status, data.progress);
  });

  eventSource.addEventListener('item_progress', (e) => {
    const data = JSON.parse(e.data);
    updateItemProgress(data.stage_id, data.item, data.completed, data.total, data.detail);
  });

  eventSource.addEventListener('cost_update', (e) => {
    const data = JSON.parse(e.data);
    if (pipelineState) {
      pipelineState.total_cost_usd = data.total_cost;
      // Update cost display without full re-render
      const costEl = document.querySelector('.pipeline-stat .stat-value');
      // Find the cost stat (second one)
      const stats = document.querySelectorAll('.pipeline-stat .stat-value');
      if (stats.length >= 2) {
        stats[1].textContent = `$${data.total_cost.toFixed(2)}`;
      }
    }
  });

  eventSource.addEventListener('pipeline_status', (e) => {
    const data = JSON.parse(e.data);
    if (pipelineState) {
      pipelineState.overall_status = data.overall_status;
      pipelineState.current_stage_id = data.current_stage;
      renderDashboard();
    }
  });

  eventSource.onerror = () => {
    // EventSource auto-reconnects, just log
    console.log('SSE connection lost, reconnecting...');
  };
}

function updateStage(stageId, status, progress) {
  if (!pipelineState) return;

  const stage = pipelineState.stages.find(s => s.stage_id === stageId);
  if (!stage) return;

  stage.status = status;
  if (progress) {
    stage.progress = progress;
  }

  // Re-render the full dashboard to update counters, actions, etc.
  renderDashboard();
}

function updateItemProgress(stageId, item, completed, total, detail) {
  if (!pipelineState) return;

  const stage = pipelineState.stages.find(s => s.stage_id === stageId);
  if (!stage) return;

  stage.progress.current_item = item;
  stage.progress.completed_items = completed;
  stage.progress.total_items = total;
  stage.progress.detail = detail;

  // Update just the stage card (avoid full re-render for performance)
  const card = document.getElementById(`stage-${stageId}`);
  if (card) {
    const detailEl = card.querySelector('.stage-detail');
    if (detailEl) detailEl.textContent = detail;

    const progressFill = card.querySelector('.stage-progress-fill');
    if (progressFill && total > 0) {
      progressFill.style.width = `${Math.round((completed / total) * 100)}%`;
    }
  }
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

async function resumePipeline() {
  const btn = document.querySelector('.btn-resume');
  if (btn) { btn.disabled = true; btn.textContent = 'Resuming...'; }

  try {
    const resp = await fetch('/api/pipeline/resume', { method: 'POST' });
    const data = await resp.json();
    if (!data.success) {
      alert('Error: ' + (data.error || 'Unknown error'));
    }
  } catch (err) {
    alert('Network error: ' + err.message);
  }
}

async function cancelPipeline() {
  if (!confirm('Cancel the running pipeline?')) return;

  try {
    const resp = await fetch('/api/pipeline/cancel', { method: 'POST' });
    const data = await resp.json();
    if (!data.success) {
      alert('Error: ' + (data.error || 'Unknown error'));
    }
  } catch (err) {
    alert('Network error: ' + err.message);
  }
}

async function retryStage() {
  try {
    const resp = await fetch('/api/pipeline/retry', { method: 'POST' });
    const data = await resp.json();
    if (!data.success) {
      alert('Error: ' + (data.error || 'Unknown error'));
    }
  } catch (err) {
    alert('Network error: ' + err.message);
  }
}

async function skipStage() {
  const current = pipelineState?.stages.find(
    s => s.stage_id === pipelineState.current_stage_id
  );
  const name = current ? current.display_name : 'current stage';
  if (!confirm(`Skip "${name}"? This cannot be undone.`)) return;

  try {
    const resp = await fetch('/api/pipeline/skip', { method: 'POST' });
    const data = await resp.json();
    if (!data.success) {
      alert('Error: ' + (data.error || 'Unknown error'));
    }
  } catch (err) {
    alert('Network error: ' + err.message);
  }
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function formatPipelineStatus(status) {
  const labels = {
    not_started: 'Not Started',
    running: 'Running',
    paused: 'Paused for Review',
    completed: 'Completed',
    failed: 'Failed',
    cancelled: 'Cancelled',
  };
  return labels[status] || status;
}

function formatElapsed(startedAt, finishedAt) {
  if (!startedAt) return '';

  const start = new Date(startedAt);
  const end = finishedAt ? new Date(finishedAt) : new Date();
  const seconds = Math.round((end - start) / 1000);

  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${mins}m`;
}

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}
