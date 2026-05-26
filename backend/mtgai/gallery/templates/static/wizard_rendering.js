/**
 * Wizard Rendering tab — live progress block + placeholder card gallery.
 *
 * Stage ID: `rendering`. Pillow compositor renders cards to print-ready images
 * in <asset>/renders/. Result shape: { rendered, skipped, failed, elapsed_seconds }.
 *
 * `rendering` is review_eligible: False — it never pauses for review. Footer is
 * always a wiz-footer-note. No advance button.
 *
 * Conventions followed:
 *   §3  form lock during AI gen (none here — display-only tab)
 *   §8  status pill flows from stage state via wizard_stage.js
 *   §9  Stop after this step — handled by wizard_stage.js
 *   §10 sticky progress strip — driven by SSE, not this module
 *
 * The progress block updates reactively from `stage.progress` on each SSE
 * rerender without rebuilding the whole gallery.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'rendering';

  // Scoped styles — injected once.
  const STYLE_ID = 'wiz-rendering-styles';

  const local = {
    initialized: false,
    stageStatus: 'pending',
    // Summary from last completed run — fetched from the stage artifacts.
    summary: null,   // { rendered, skipped, failed, elapsed_seconds } | null
    // Placeholder gallery items — fetched from state, no real image URLs yet.
    cardNames: [],   // string[]
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
      /* --- rendering tab -------------------------------------------------- */
      .wiz-rendering-progress {
        background: #0f1729;
        border: 1px solid #1f2540;
        border-radius: 6px;
        padding: 0.75rem 0.9rem;
        margin-bottom: 1rem;
      }
      .wiz-rendering-progress-header {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        margin-bottom: 0.4rem;
        font-size: 0.85rem;
        color: #ddd;
      }
      .wiz-rendering-progress-stats {
        font-size: 0.78rem;
        color: #999;
        font-variant-numeric: tabular-nums;
      }
      .wiz-rendering-bar {
        height: 6px;
        background: #1a1a2e;
        border-radius: 3px;
        overflow: hidden;
        margin-top: 0.4rem;
      }
      .wiz-rendering-bar-fill {
        height: 100%;
        background: #4a9eff;
        border-radius: 3px;
        transition: width 0.3s ease;
      }
      .wiz-rendering-summary {
        display: grid;
        grid-template-columns: max-content 1fr;
        gap: 0.35rem 1.25rem;
        margin-bottom: 1rem;
        font-size: 0.82rem;
      }
      .wiz-rendering-summary dt { color: #888; }
      .wiz-rendering-summary dd { margin: 0; color: #ddd; }
      .wiz-rendering-section-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 0.6rem;
      }
      .wiz-rendering-section-header h3 { margin: 0; font-size: 0.95rem; color: #ccc; }
      .wiz-rendering-gallery {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
        gap: 0.6rem;
      }
      .wiz-rendering-thumb {
        background: #0f1729;
        border: 1px solid #1f2540;
        border-radius: 6px;
        aspect-ratio: 822 / 1122;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 0.4rem;
        font-size: 0.68rem;
        color: #666;
        text-align: center;
        overflow: hidden;
        word-break: break-word;
        gap: 0.25rem;
      }
      .wiz-rendering-thumb img {
        width: 100%;
        height: 100%;
        object-fit: contain;
        border-radius: 4px;
      }
      .wiz-rendering-thumb .wiz-rendering-thumb-name {
        color: #999;
        font-size: 0.65rem;
        line-height: 1.2;
        text-align: center;
        word-break: break-word;
      }
      .wiz-rendering-empty {
        color: #666;
        font-style: italic;
        font-size: 0.85rem;
        padding: 1.5rem 0;
      }
      .wiz-rendering-note {
        font-size: 0.75rem;
        color: #555;
        margin-top: 0.75rem;
        font-style: italic;
      }
    `;
    document.head.appendChild(style);
  }

  // ---------------------------------------------------------------------------
  // Top-level render — called by wizard_stage.js on every SSE stage_update
  // ---------------------------------------------------------------------------

  function render({ root, state, stage, content, footer }) {
    injectStyles();

    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      // Async fetch of card names for the gallery placeholder.
      fetchCardNames(state).catch(() => {/* non-critical */});
      paintProgress(root, stage);
      paintGallery(root);
      paintFooter(footer, state, stage);
      return;
    }

    // Re-render path: update progress block reactively without touching the
    // gallery (avoid layout jank on every SSE tick).
    if (stage) local.stageStatus = stage.status;
    paintProgress(root, stage);

    // When the stage finishes (running→completed/failed) repaint everything
    // so the summary and gallery populate.
    const wasRunning = local.stageStatus === 'running';
    const justFinished = stage && wasRunning
      && stage.status !== 'running'
      && stage.status !== 'pending';
    if (justFinished) {
      paintGallery(root);
    }

    paintFooter(footer, state, stage);
  }

  function mountShellHtml() {
    return `
      <div data-role="rendering-progress"></div>
      <div data-role="rendering-gallery-wrap"></div>
    `;
  }

  // ---------------------------------------------------------------------------
  // Progress block — reactive from stage.progress
  // ---------------------------------------------------------------------------

  function paintProgress(root, stage) {
    const slot = root.querySelector('[data-role="rendering-progress"]');
    if (!slot) return;

    if (!stage) {
      slot.innerHTML = '<div class="wiz-rendering-empty">No stage data.</div>';
      return;
    }

    const progress = stage.progress || {};
    const status = stage.status || 'pending';
    const total = progress.total_items || 0;
    const completed = progress.completed_items || 0;
    const failed = progress.failed_items || 0;
    const cost = progress.cost_usd > 0 ? '$' + progress.cost_usd.toFixed(3) : null;
    const detail = progress.detail || progress.current_item || '';
    const elapsed = formatElapsed(progress.started_at, progress.finished_at);

    // Summary dl — only when the stage has run at least once.
    const hasSummary = status === 'completed' || status === 'failed' || (total > 0);
    const summaryHtml = hasSummary ? `
      <dl class="wiz-rendering-summary">
        <dt>Status</dt><dd>${escHtml(status.replace(/_/g, ' '))}</dd>
        ${completed > 0 ? `<dt>Rendered</dt><dd>${completed}</dd>` : ''}
        ${failed > 0 ? `<dt>Failed</dt><dd><span style="color:#ff4757">${failed}</span></dd>` : ''}
        ${total > 0 ? `<dt>Total</dt><dd>${total}</dd>` : ''}
        ${elapsed ? `<dt>Elapsed</dt><dd>${escHtml(elapsed)}</dd>` : ''}
        ${cost ? `<dt>Cost</dt><dd>${escHtml(cost)}</dd>` : ''}
      </dl>` : '';

    // Progress bar — only while running or if total is known.
    let progressBarHtml = '';
    if (status === 'running' || (total > 0)) {
      const pct = total > 0 ? Math.round(((completed + failed) / total) * 100) : 0;
      const label = status === 'running'
        ? (detail || `Rendering… ${completed + failed}/${total}`)
        : (detail || `${completed} rendered · ${failed} failed`);
      progressBarHtml = `
        <div class="wiz-rendering-progress">
          <div class="wiz-rendering-progress-header">
            <span>${escHtml(label)}</span>
            <span class="wiz-rendering-progress-stats">${pct}%</span>
          </div>
          <div class="wiz-rendering-bar">
            <div class="wiz-rendering-bar-fill" style="width:${pct}%"></div>
          </div>
        </div>`;
    } else if (status === 'pending') {
      progressBarHtml = '<div class="wiz-rendering-empty">Stage has not started yet.</div>';
    }

    const errorHtml = progress.error_message
      ? `<div class="wiz-stage-error"><strong>Error:</strong> ${escHtml(progress.error_message)}</div>`
      : '';

    slot.innerHTML = summaryHtml + progressBarHtml + errorHtml;
  }

  // ---------------------------------------------------------------------------
  // Gallery — placeholder thumbnail frames, one per card
  // ---------------------------------------------------------------------------

  async function fetchCardNames(state) {
    // Best-effort: try to pull a card list for placeholder frames.
    // TODO: replace with real thumbnail route once image serving is wired up.
    try {
      const resp = await fetch('/api/wizard/rendering/state');
      if (!resp.ok) return;
      const data = await resp.json();
      if (Array.isArray(data.card_names)) {
        local.cardNames = data.card_names;
        local.summary = data.summary || null;
      }
    } catch (_) {/* non-critical — placeholder gallery degrades gracefully */}

    const root = bodyRoot();
    if (root) paintGallery(root);
  }

  function paintGallery(root) {
    const slot = root.querySelector('[data-role="rendering-gallery-wrap"]');
    if (!slot) return;

    const names = local.cardNames;
    const hasCards = names && names.length > 0;
    const isRunning = local.stageStatus === 'running';

    const headerHtml = `
      <div class="wiz-rendering-section-header">
        <h3>Rendered cards</h3>
      </div>`;

    if (isRunning && !hasCards) {
      slot.innerHTML = headerHtml + '<div class="wiz-rendering-empty">Rendering in progress…</div>';
      return;
    }

    if (!hasCards) {
      slot.innerHTML = headerHtml + '<div class="wiz-rendering-empty">No rendered cards yet.</div>';
      return;
    }

    const thumbsHtml = names.map(name => {
      // TODO: replace placeholder with real image once /api/wizard/rendering/image/<name>
      // (or equivalent) is wired up. For now, render a sized box with the card name.
      return `
        <div class="wiz-rendering-thumb" title="${escAttr(name)}">
          <span class="wiz-rendering-thumb-name">${escHtml(name)}</span>
        </div>`;
    }).join('');

    slot.innerHTML = `
      ${headerHtml}
      <div class="wiz-rendering-gallery">${thumbsHtml}</div>
      <p class="wiz-rendering-note">Thumbnail images will display here once the image route is wired up.</p>
    `;
  }

  // ---------------------------------------------------------------------------
  // Footer — rendering never pauses; always a footer-note
  // ---------------------------------------------------------------------------

  function paintFooter(footer, state, stage) {
    if (!footer) return;

    const status = stage ? stage.status : local.stageStatus;
    let html;

    if (status === 'running') {
      html = '<span class="wiz-footer-note">Rendering in progress — no action required.</span>';
    } else if (status === 'failed') {
      html = '<span class="wiz-footer-note">Rendering failed. See the error above; retry support lands in a follow-up card.</span>';
    } else if (status === 'completed') {
      const next = W.nextStageEntryAfter(STAGE_ID);
      const nextName = next ? next.name : 'the next stage';
      html = `<span class="wiz-footer-note">Rendering complete. Engine continues automatically to ${escHtml(nextName)}.</span>`;
    } else {
      html = '<span class="wiz-footer-note">Runs automatically — no review step.</span>';
    }

    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
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
