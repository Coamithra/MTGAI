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
      const wasIdle = (
        pipelineState.overall_status === 'not_started'
        || pipelineState.overall_status === 'completed'
        || pipelineState.overall_status === 'cancelled'
      );
      pipelineState.overall_status = data.overall_status;
      pipelineState.current_stage_id = data.current_stage;
      renderDashboard();
      // Fresh-run guard: when the pipeline transitions from idle → running,
      // wipe lingering sections from a prior run so the panel doesn't
      // accumulate stale stage groups.
      if (wasIdle && data.overall_status === 'running') {
        const root = document.getElementById('stage-sections');
        if (root) root.innerHTML = '';
        Object.keys(_sections).forEach((k) => delete _sections[k]);
      }
      if (data.overall_status === 'completed' || data.overall_status === 'cancelled'
          || data.overall_status === 'failed') {
        hidePipelinePhaseBanner();
      }
    }
  });

  eventSource.addEventListener('phase', (e) => {
    handlePipelinePhaseEvent(JSON.parse(e.data));
  });

  eventSource.addEventListener('stage_section_init', (e) => {
    const data = JSON.parse(e.data);
    initStageSections(data.stage_id, data.sections || []);
  });

  eventSource.addEventListener('stage_section_update', (e) => {
    const data = JSON.parse(e.data);
    updateSection(data);
  });

  eventSource.onerror = () => {
    // EventSource auto-reconnects, just log
    console.log('SSE connection lost, reconnecting...');
  };
}

// ---------------------------------------------------------------------------
// Stage sections (live filling)
// ---------------------------------------------------------------------------

// In-memory mirror of section state, keyed by `${stage_id}:${section_id}`.
// We keep this so append_text / append_item can mutate without refetching the
// DOM. Items always re-render the body from this canonical state.
const _sections = {};

function _sectionKey(stageId, sectionId) {
  return stageId + ':' + sectionId;
}

function initStageSections(stageId, sections) {
  const root = document.getElementById('stage-sections');
  if (!root) return;

  // If this stage already has a group (re-init on retry), wipe it.
  let group = document.getElementById('stage-section-group-' + stageId);
  if (group) {
    group.remove();
    Object.keys(_sections).forEach((k) => {
      if (k.startsWith(stageId + ':')) delete _sections[k];
    });
  }

  const stage = pipelineState
    ? pipelineState.stages.find((s) => s.stage_id === stageId)
    : null;
  const heading = stage ? stage.display_name : stageId;

  group = document.createElement('div');
  group.className = 'stage-section-group';
  group.id = 'stage-section-group-' + stageId;
  group.innerHTML = '<h3>' + escapeHtml(heading) + '</h3>';

  for (const s of sections) {
    const state = {
      stage_id: stageId,
      section_id: s.section_id,
      title: s.title || s.section_id,
      content_type: s.content_type || 'text',
      status: s.status || 'pending',
      content: s.content !== undefined ? s.content : null,
      detail: '',
    };
    _sections[_sectionKey(stageId, s.section_id)] = state;
    group.appendChild(buildSectionDOM(state));
  }
  root.appendChild(group);
  group.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function buildSectionDOM(state) {
  const wrap = document.createElement('div');
  wrap.className = 'section ' + state.status;
  wrap.dataset.stageId = state.stage_id;
  wrap.dataset.sectionId = state.section_id;
  wrap.id = 'section-' + state.stage_id + '-' + state.section_id;

  const header = document.createElement('div');
  header.className = 'section-header';
  header.innerHTML = `
    <span class="section-title">${escapeHtml(state.title)}</span>
    <span class="section-status ${state.status}">${state.status}</span>
    <span class="section-detail"></span>
  `;
  wrap.appendChild(header);

  const body = document.createElement('div');
  body.className = 'section-body';
  body.innerHTML = renderSectionContent(state);
  wrap.appendChild(body);

  return wrap;
}

function updateSection(data) {
  const key = _sectionKey(data.stage_id, data.section_id);
  const state = _sections[key];
  if (!state) {
    // Section update arrived before init — defer init wasn't sent.
    // Tolerate this by silently dropping; could happen on a stale tab.
    return;
  }

  if (data.status) state.status = data.status;
  if (data.detail !== undefined) state.detail = data.detail;
  if (data.content !== undefined) state.content = data.content;
  if (data.append_text !== undefined) {
    if (typeof state.content === 'string') {
      state.content = state.content + data.append_text;
    } else {
      state.content = data.append_text;
    }
  }
  if (data.append_item !== undefined) {
    if (!state.content || typeof state.content !== 'object') {
      state.content = { items: [] };
    }
    if (!Array.isArray(state.content.items)) state.content.items = [];
    state.content.items.push({ ...data.append_item, _justAdded: true });
  }

  const root = document.getElementById('section-' + data.stage_id + '-' + data.section_id);
  if (!root) return;

  // Status pill + class
  root.classList.remove('pending', 'running', 'done', 'failed');
  root.classList.add(state.status);
  const pill = root.querySelector('.section-status');
  if (pill) {
    pill.className = 'section-status ' + state.status;
    pill.textContent = state.status;
  }
  const detailEl = root.querySelector('.section-detail');
  if (detailEl) detailEl.textContent = state.detail || '';

  const body = root.querySelector('.section-body');
  if (body) body.innerHTML = renderSectionContent(state);

  // Strip the _justAdded marker after one frame (used for animation only)
  if (state.content && Array.isArray(state.content.items)) {
    requestAnimationFrame(() => {
      for (const item of state.content.items) delete item._justAdded;
    });
  }
}

function renderSectionContent(state) {
  const c = state.content;
  if (c === null || c === undefined || (Array.isArray(c) && c.length === 0)) {
    if (state.status === 'pending') {
      return '<div class="section-empty">Awaiting…</div>';
    }
    if (state.status === 'running') {
      return '<div class="section-empty">Working…</div>';
    }
    return '<div class="section-empty">(empty)</div>';
  }

  switch (state.content_type) {
    case 'text':
      return '<pre>' + escapeHtml(typeof c === 'string' ? c : JSON.stringify(c, null, 2)) + '</pre>';
    case 'markdown':
      return '<div class="md-rendered">' + renderMarkdown(typeof c === 'string' ? c : '') + '</div>';
    case 'kv':
      return renderKV(c);
    case 'table':
      return renderTable(c);
    case 'card_grid':
      return renderCardGrid(c);
    case 'card_tile':
      return renderCardTile(c);
    default:
      return '<pre>' + escapeHtml(JSON.stringify(c, null, 2)) + '</pre>';
  }
}

function renderKV(obj) {
  if (!obj || typeof obj !== 'object') return '';
  const rows = Object.entries(obj)
    .map(([k, v]) => `<dt>${escapeHtml(String(k))}</dt><dd>${escapeHtml(String(v))}</dd>`)
    .join('');
  return '<dl class="kv-list">' + rows + '</dl>';
}

function renderTable(content) {
  if (!content) return '';
  const rows = content.rows || content;
  if (!Array.isArray(rows) || rows.length === 0) return '';
  const [head, ...body] = rows;
  const ths = (head || []).map((c) => `<th>${escapeHtml(String(c))}</th>`).join('');
  const trs = body
    .map((row) => '<tr>' + (row || []).map((c) => `<td>${escapeHtml(String(c))}</td>`).join('') + '</tr>')
    .join('');
  const cls = content.scrollable ? ' class="scrollable"' : '';
  return `<table${cls}><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
}

function renderCardGrid(content) {
  const items = (content && content.items) || [];
  if (items.length === 0) {
    return '<div class="section-empty">No cards yet…</div>';
  }
  return '<div class="card-grid">' + items.map(renderCardTile).join('') + '</div>';
}

function renderCardTile(card) {
  if (!card) return '';
  const cost = card.mana_cost ? renderManaCost(card.mana_cost) : '';
  const flavor = card.flavor_text
    ? `<div class="card-tile-flavor">${escapeHtml(card.flavor_text)}</div>`
    : '';
  const oracle = card.oracle_text
    ? `<div class="card-tile-text">${escapeHtml(card.oracle_text)}</div>`
    : '';
  const meta = card.slot_id
    ? `<div class="card-tile-meta">slot ${escapeHtml(card.slot_id)}</div>`
    : '';
  const cls = card._justAdded ? 'card-tile fade-in' : 'card-tile';
  return `
    <div class="${cls}">
      <div class="card-tile-head">
        <span class="card-tile-name">${escapeHtml(card.name || '')}</span>
        <span class="card-tile-cost">${cost}</span>
      </div>
      <div class="card-tile-type">${escapeHtml(card.type_line || '')}${
        card.rarity ? ' &middot; ' + escapeHtml(String(card.rarity)) : ''
      }</div>
      ${oracle}
      ${flavor}
      ${meta}
    </div>
  `;
}

function renderManaCost(mc) {
  if (!mc) return '';
  // {W}{U} → W U with brackets stripped, monospace
  return escapeHtml(mc).replace(/\{([^}]+)\}/g, '<span>$1</span>').replace(/<\/?span>/g, '');
}

// ---------------------------------------------------------------------------
// Markdown (zero-dep, copied from theme.js)
// ---------------------------------------------------------------------------

function renderMarkdown(src) {
  if (!src) return '';
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const inline = (s) => esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
  const lines = src.split(/\r?\n/);
  const out = [];
  let para = [];
  let listItems = [];
  const flushPara = () => {
    if (para.length) {
      out.push('<p>' + inline(para.join(' ')) + '</p>');
      para = [];
    }
  };
  const flushList = () => {
    if (listItems.length) {
      out.push('<ul>' + listItems.map((l) => '<li>' + inline(l) + '</li>').join('') + '</ul>');
      listItems = [];
    }
  };
  for (const raw of lines) {
    const line = raw.replace(/\s+$/, '');
    if (!line.trim()) { flushPara(); flushList(); continue; }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flushPara(); flushList();
      const lvl = Math.min(6, Math.max(1, heading[1].length));
      out.push(`<h${lvl}>${inline(heading[2])}</h${lvl}>`);
      continue;
    }
    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet) { flushPara(); listItems.push(bullet[1]); continue; }
    flushList();
    para.push(line);
  }
  flushPara(); flushList();
  return out.join('\n');
}

// ---------------------------------------------------------------------------
// Phase banner (mirrors theme.js handlePhaseEvent shape)
// ---------------------------------------------------------------------------

function showPipelinePhaseBanner() {
  const b = document.getElementById('pipeline-phase-banner');
  if (b) b.classList.add('active');
}

function hidePipelinePhaseBanner() {
  const b = document.getElementById('pipeline-phase-banner');
  if (b) b.classList.remove('active', 'has-stats');
}

function handlePipelinePhaseEvent(data) {
  const banner = document.getElementById('pipeline-phase-banner');
  const bar = document.getElementById('pipeline-phase-bar');
  const activityEl = document.getElementById('pipeline-phase-activity');
  const elapsedEl = document.getElementById('pipeline-phase-elapsed');
  const stats = document.getElementById('pipeline-phase-stats');
  if (!banner || !bar || !activityEl || !stats) return;

  showPipelinePhaseBanner();

  const phase = data.phase || '';
  const stageId = data.stage_id || '';
  const stage = pipelineState
    ? pipelineState.stages.find((s) => s.stage_id === stageId)
    : null;
  const stageLabel = stage ? stage.display_name : stageId;
  const activity = data.activity || '';
  activityEl.textContent = stageLabel ? stageLabel + ' — ' + activity : activity;

  if (elapsedEl && typeof data.elapsed_s === 'number') {
    elapsedEl.textContent = formatPhaseElapsed(data.elapsed_s);
  }

  if (data.generation && phase === 'generation') {
    bar.classList.add('indeterminate');
    const tokens = data.generation.tokens || 0;
    const tps = data.generation.tok_per_sec || 0;
    stats.textContent = tokens.toLocaleString() + ' tok @ ' + tps.toFixed(1) + ' tok/s';
    banner.classList.add('has-stats');
    return;
  }
  bar.classList.remove('indeterminate');

  if (data.prompt_eval && data.prompt_eval.total > 0) {
    const pe = data.prompt_eval;
    const pct = Math.max(0, Math.min(100, (pe.processed / pe.total) * 100));
    bar.style.width = pct.toFixed(1) + '%';
    stats.textContent = 'Prompt: ' + pe.processed.toLocaleString() + ' / '
      + pe.total.toLocaleString() + ' (' + pct.toFixed(0) + '%)';
    banner.classList.add('has-stats');
    return;
  }

  stats.textContent = '';
  banner.classList.remove('has-stats');

  // Phase-kind defaults so the bar moves on transitions even without telemetry
  if (phase === 'starting') bar.style.width = '5%';
  else if (phase === 'running') bar.style.width = '30%';
  else if (phase === 'done') bar.style.width = '100%';
}

function formatPhaseElapsed(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return s + 's';
  const m = Math.floor(s / 60);
  const r = s % 60;
  return m + 'm ' + r + 's';
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
