/**
 * Wizard Art Generation tab — live progress block + card art attempt grid.
 *
 * Registers via ``W.registerStageRenderer('art_gen', ...)`` so the standard
 * wizard_stage.js shell still owns the header (status pill, break-point
 * toggle, Edit-cascade button).
 *
 * Generates card art via ComfyUI + Flux into ``<asset>/art/<slug>_v<N>.png``.
 * Multiple attempt versions per card (typically 3).
 * Result shape from stages.py: ``{ generated: N, skipped: N, failed: N }``
 *
 * IMPORTANT: art_gen is NOT review_eligible — it never pauses for human
 * review. Footer is always a ``wiz-footer-note`` only.
 *
 * Conventions:
 *   §3  form lock during AI gen (no interactive controls here, but honour the pattern)
 *   §8  status pill flows from stage state
 *   §9  Stop after this step — handled by wizard_stage.js
 *   §10 live progress block updates reactively from stage.progress on each SSE rerender
 *   §12 lazy mount; idempotent rerender — progress block updates in place, grid only
 *       rebuilt when content count changes (avoid full repaint every SSE tick)
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'art_gen';

  // ── Scoped styles (injected once) ──────────────────────────────────────────

  if (!document.getElementById('wiz-art_gen-styles')) {
    const style = document.createElement('style');
    style.id = 'wiz-art_gen-styles';
    style.textContent = `
      /* Art Generation tab — live progress + image-grid layout */

      .wiz-art_gen-summary {
        margin-bottom: 1rem;
      }

      .wiz-art_gen-context {
        display: grid;
        grid-template-columns: max-content 1fr;
        gap: 0.3rem 1rem;
        font-size: 0.82rem;
        margin: 0.5rem 0 0 0;
      }
      .wiz-art_gen-context dt { color: #888; }
      .wiz-art_gen-context dd { margin: 0; color: #ddd; }

      .wiz-art_gen-blurb {
        color: #888;
        font-size: 0.82rem;
        margin: 0.25rem 0 0.5rem 0;
      }

      /* Live progress block — reactive, not rebuilt on every tick */
      .wiz-art_gen-progress {
        background: #0f1729;
        border: 1px solid #1f2540;
        border-radius: 6px;
        padding: 0.75rem 0.9rem;
        margin-bottom: 1rem;
      }
      .wiz-art_gen-progress-label {
        font-size: 0.82rem;
        color: #ccc;
        margin-bottom: 0.4rem;
        display: flex;
        gap: 0.75rem;
        flex-wrap: wrap;
        align-items: center;
      }
      .wiz-art_gen-progress-label .wiz-art_gen-pct {
        font-variant-numeric: tabular-nums;
        color: #4a9eff;
        font-weight: 600;
      }
      .wiz-art_gen-progress-label .wiz-art_gen-failed {
        color: #ff4757;
      }
      .wiz-art_gen-progress-label .wiz-art_gen-current {
        color: #888;
        font-style: italic;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        flex: 1 1 0;
        min-width: 0;
      }
      .wiz-art_gen-bar {
        height: 6px;
        background: #1a1a2e;
        border-radius: 3px;
        overflow: hidden;
      }
      .wiz-art_gen-bar-fill {
        height: 100%;
        background: #4a9eff;
        border-radius: 3px;
        transition: width 0.3s ease;
      }

      /* Image grid shared shape — identical in char_portraits / art_gen / art_select */
      .wiz-art_gen-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
        gap: 0.75rem;
        margin-top: 0.75rem;
      }

      /* Thumbnail tile — shared shape (duplicated identically in char_portraits + art_select) */
      .wiz-art_gen-tile {
        background: #0f1729;
        border: 1px solid #1f2540;
        border-radius: 6px;
        overflow: hidden;
        display: flex;
        flex-direction: column;
      }
      .wiz-art_gen-tile-img {
        width: 100%;
        aspect-ratio: 4 / 3;   /* landscape art orientation */
        background: #12192e;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.7rem;
        color: #444;
        text-align: center;
        padding: 0.4rem;
        box-sizing: border-box;
        word-break: break-all;
        border-bottom: 1px solid #1f2540;
        position: relative;
        overflow: hidden;
      }
      .wiz-art_gen-tile-img img {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        object-fit: cover;
      }
      .wiz-art_gen-tile-name {
        padding: 0.35rem 0.5rem;
        font-size: 0.75rem;
        color: #ccc;
        font-weight: 600;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .wiz-art_gen-tile-sub {
        padding: 0 0.5rem 0.35rem;
        font-size: 0.68rem;
        color: #666;
      }
      .wiz-art_gen-tile-attempts {
        display: flex;
        gap: 2px;
        padding: 0 0.5rem 0.35rem;
        flex-wrap: wrap;
      }
      .wiz-art_gen-attempt-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #4a9eff44;
        border: 1px solid #4a9eff66;
        flex: 0 0 auto;
        title: '';
      }
      .wiz-art_gen-attempt-dot.done { background: #00d4aa55; border-color: #00d4aa; }
      .wiz-art_gen-attempt-dot.failed { background: #ff475744; border-color: #ff4757; }

      /* Locked-state visual cue */
      .wiz-art_gen-locked .wiz-art_gen-grid {
        opacity: 0.7;
        pointer-events: none;
      }
    `;
    document.head.appendChild(style);
  }

  // ── Module-local state ─────────────────────────────────────────────────────

  const local = {
    initialized: false,
    cards: [],          // [{name, collector_number, versions: [{filename, attempt, done}]}]
    hasContent: false,
    stageStatus: 'pending',
    locked: false,
    bootstrapping: false,
    lastGridHash: '',   // avoid full grid repaint on every progress SSE tick
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ── Top-level render ────────────────────────────────────────────────────────

  function render({ root, state, stage, content, footer }) {
    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      bootstrap(root, state).catch(err => {
        W.toast('Failed to load art generation state: ' + err.message, 'error');
      });
      paintFooter(footer, state);
      return;
    }

    const prevStatus = local.stageStatus;
    if (stage) local.stageStatus = stage.status;

    // Always update the live progress block reactively (cheap DOM update).
    paintProgressBlock(root, stage);

    // Only rebuild grid when stage transitions out of running (new content landed).
    const justFinished =
      stage
      && prevStatus !== local.stageStatus
      && local.stageStatus !== 'pending'
      && local.stageStatus !== 'running'
      && !local.bootstrapping;
    if (justFinished) {
      local.bootstrapping = true;
      bootstrap(root, state)
        .catch(err => W.toast('Failed to refresh art generation state: ' + err.message, 'error'))
        .finally(() => { local.bootstrapping = false; });
      return;
    }

    paintFooter(footer, state);
    setLocked(local.locked);
  }

  function mountShellHtml() {
    return `
      <div class="wiz-art_gen-summary" data-role="ag-summary">
        <div class="wiz-stage-empty">Loading art generation state…</div>
      </div>
      <div class="wiz-art_gen-progress" data-role="ag-progress" hidden>
        <div class="wiz-art_gen-progress-label" data-role="ag-progress-label">Waiting…</div>
        <div class="wiz-art_gen-bar">
          <div class="wiz-art_gen-bar-fill" data-role="ag-bar-fill" style="width:0%"></div>
        </div>
      </div>
      <div class="wiz-art_gen-grid" data-role="ag-grid"></div>
    `;
  }

  // ── Bootstrap (fetch state from server) ────────────────────────────────────

  async function bootstrap(root, state) {
    // TODO: implement GET /api/wizard/art_gen/state
    // Expected response: { cards: [{name, collector_number, versions:[{filename,attempt}]}],
    //                      has_content, stage_status }
    let data = null;
    try {
      const resp = await fetch('/api/wizard/art_gen/state');
      if (resp.ok) {
        data = await resp.json();
      }
    } catch (_) {
      // Backend not yet wired — degrade gracefully.
    }

    if (data) {
      local.cards = Array.isArray(data.cards) ? data.cards : [];
      local.hasContent = !!data.has_content;
      local.stageStatus = data.stage_status || local.stageStatus;
    }

    paintSummary(root, state);
    paintGrid(root);
    paintFooter(getFooter(root), state);
  }

  // ── Summary block ───────────────────────────────────────────────────────────

  function paintSummary(root) {
    const slot = root.querySelector('[data-role="ag-summary"]');
    if (!slot) return;
    const count = local.cards.length;
    slot.innerHTML = `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">Card art generation</h3>
      </div>
      <p class="wiz-art_gen-blurb">
        Generates art for all cards via ComfyUI + Flux.1-dev.
        Multiple attempts per card — the best version is selected in the next stage.
      </p>
      <dl class="wiz-art_gen-context">
        <dt>Cards</dt><dd>${count > 0 ? count : '—'}</dd>
        <dt>Output</dt><dd>art/ (&lt;slug&gt;_v&lt;N&gt;.png)</dd>
      </dl>
    `;
  }

  // ── Live progress block (reactive — updated cheaply in place) ───────────────

  function paintProgressBlock(root, stage) {
    if (!stage) return;
    const block = root.querySelector('[data-role="ag-progress"]');
    const labelEl = root.querySelector('[data-role="ag-progress-label"]');
    const fillEl = root.querySelector('[data-role="ag-bar-fill"]');
    if (!block || !labelEl || !fillEl) return;

    const progress = stage.progress || {};
    const total = progress.total_items || 0;
    const completed = progress.completed_items || 0;
    const failed = progress.failed_items || 0;
    const isActive = stage.status === 'running' || total > 0;

    if (!isActive && stage.status === 'pending') {
      block.hidden = true;
      return;
    }
    block.hidden = false;

    const pct = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
    const current = progress.current_item || progress.detail || '';

    const failedHtml = failed > 0
      ? `<span class="wiz-art_gen-failed">${failed} failed</span>`
      : '';
    const currentHtml = current
      ? `<span class="wiz-art_gen-current">${escHtml(current)}</span>`
      : '';

    labelEl.innerHTML =
      `<span>${completed}/${total} cards · <span class="wiz-art_gen-pct">${pct}%</span></span>`
      + failedHtml
      + currentHtml;
    fillEl.style.width = pct + '%';
  }

  // ── Image grid ──────────────────────────────────────────────────────────────

  function paintGrid(root) {
    const slot = root.querySelector('[data-role="ag-grid"]');
    if (!slot) return;

    const generating = local.stageStatus === 'running' || local.locked;
    const hash = local.cards.length + ':' + local.stageStatus;
    if (slot.dataset.gridHash === hash) return;  // avoid thrashing during SSE ticks
    slot.dataset.gridHash = hash;

    if (!local.hasContent || local.cards.length === 0) {
      slot.innerHTML = `
        <div class="wiz-stage-empty">
          ${generating
            ? 'Generating art… thumbnails will appear when the stage completes.'
            : 'No art generated yet. Run the Art Generation stage to generate card art.'}
        </div>
      `;
      return;
    }

    slot.innerHTML = local.cards.map(card => artTileHtml(card)).join('');
  }

  /**
   * Thumbnail tile — one card with its art attempt(s).
   * Shared shape: same structure as char_portraits + art_select tiles.
   */
  function artTileHtml(card) {
    const name = card.name || card.collector_number || '(unknown)';
    const versions = Array.isArray(card.versions) ? card.versions : [];
    const v1 = versions[0];

    // TODO: implement image serving route for card art
    // Suggested route: GET /api/art/image?path=<relative_path_under_asset>
    const imgHtml = v1
      ? `<div class="wiz-art_gen-tile-img">
           ${escHtml(v1.filename || '')}
           <!-- TODO: <img src="/api/art/image?path=${escAttr(v1.filename || '')}" alt="${escAttr(name)}" onerror="this.style.display='none'"> -->
         </div>`
      : `<div class="wiz-art_gen-tile-img">(no art)</div>`;

    const dotsHtml = versions.length > 0
      ? `<div class="wiz-art_gen-tile-attempts">${versions.map((v, i) =>
          `<div class="wiz-art_gen-attempt-dot done" title="v${i + 1}: ${escAttr(v.filename || '')}"></div>`
        ).join('')}</div>`
      : '';

    return `
      <div class="wiz-art_gen-tile">
        ${imgHtml}
        <div class="wiz-art_gen-tile-name" title="${escAttr(name)}">${escHtml(name)}</div>
        ${versions.length > 1
          ? `<div class="wiz-art_gen-tile-sub">${versions.length} attempts</div>`
          : ''}
        ${dotsHtml}
      </div>
    `;
  }

  // ── Footer — art_gen is NOT review_eligible, never pauses ──────────────────

  function paintFooter(footer, state) {
    if (!footer) return;
    const next = W.nextStageEntryAfter(STAGE_ID);
    const nextName = next ? next.name : 'the next stage';

    let html;
    if (local.stageStatus === 'running') {
      html = `<span class="wiz-footer-note">Art generation is running — this stage completes automatically, no review step.</span>`;
    } else if (local.stageStatus === 'completed') {
      html = `<span class="wiz-footer-note">Art generation complete. Engine continues to ${escHtml(nextName)} automatically.</span>`;
    } else if (local.stageStatus === 'failed') {
      html = `<span class="wiz-footer-note">Stage failed — check the error above. Retry support lands in a follow-up card.</span>`;
    } else {
      html = `<span class="wiz-footer-note">Art generation runs automatically; no manual review step for this stage.</span>`;
    }

    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
    }
  }

  // ── Form lock (§3) ──────────────────────────────────────────────────────────

  function setLocked(locked) {
    local.locked = !!locked;
    const root = bodyRoot();
    if (!root) return;
    root.classList.toggle('wiz-art_gen-locked', !!locked);
  }

  // ── Helpers ─────────────────────────────────────────────────────────────────

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
