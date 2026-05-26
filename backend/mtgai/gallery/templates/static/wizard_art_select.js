/**
 * Wizard Art Selection tab — grid of cards each showing candidate art attempts
 * with the AI-selected version highlighted and a manual-override affordance.
 *
 * Registers via ``W.registerStageRenderer('art_select', ...)`` so the standard
 * wizard_stage.js shell still owns the header (status pill, break-point toggle,
 * Edit-cascade button).
 *
 * Haiku vision reviews all art attempts per card and picks the best version.
 * Result shape from stages.py: ``{ selected: N, cost_usd: F }``
 *
 * Conventions:
 *   §1  Next-step footer (when paused_for_review — review_eligible stage)
 *   §3  form lock during AI gen
 *   §8  status pill flows from stage state
 *   §9  Stop after this step — handled by wizard_stage.js
 *   §12 lazy mount; idempotent rerender
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'art_select';

  // ── Scoped styles (injected once) ──────────────────────────────────────────

  if (!document.getElementById('wiz-art_select-styles')) {
    const style = document.createElement('style');
    style.id = 'wiz-art_select-styles';
    style.textContent = `
      /* Art Selection tab — multi-attempt selection grid */

      .wiz-art_select-summary {
        margin-bottom: 1rem;
      }

      .wiz-art_select-context {
        display: grid;
        grid-template-columns: max-content 1fr;
        gap: 0.3rem 1rem;
        font-size: 0.82rem;
        margin: 0.5rem 0 0 0;
      }
      .wiz-art_select-context dt { color: #888; }
      .wiz-art_select-context dd { margin: 0; color: #ddd; }

      .wiz-art_select-blurb {
        color: #888;
        font-size: 0.82rem;
        margin: 0.25rem 0 0.5rem 0;
      }

      /* Image grid shared shape — identical in char_portraits / art_gen / art_select */
      .wiz-art_select-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
        gap: 1rem;
        margin-top: 0.75rem;
      }

      /* Card tile — wider than char_portraits to fit the attempts strip */
      .wiz-art_select-tile {
        background: #0f1729;
        border: 1px solid #1f2540;
        border-radius: 6px;
        overflow: hidden;
        display: flex;
        flex-direction: column;
      }

      .wiz-art_select-tile-name {
        padding: 0.4rem 0.6rem 0.25rem;
        font-size: 0.78rem;
        color: #ccc;
        font-weight: 600;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      /* Strip of attempt thumbnails inside each card tile */
      .wiz-art_select-attempts {
        display: flex;
        gap: 4px;
        padding: 0 0.5rem 0.5rem;
        overflow-x: auto;
      }

      /* Thumbnail tile — shared shape (duplicated identically in char_portraits + art_gen) */
      .wiz-art_select-attempt {
        flex: 0 0 auto;
        width: 80px;
        display: flex;
        flex-direction: column;
        gap: 2px;
        position: relative;
      }
      .wiz-art_select-attempt-img {
        width: 100%;
        aspect-ratio: 4 / 3;
        background: #12192e;
        border: 2px solid transparent;
        border-radius: 4px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.62rem;
        color: #444;
        text-align: center;
        word-break: break-all;
        padding: 0.2rem;
        box-sizing: border-box;
        position: relative;
        overflow: hidden;
        cursor: pointer;
        transition: border-color 0.15s;
      }
      .wiz-art_select-attempt-img:hover { border-color: #4a9eff88; }
      .wiz-art_select-attempt-img img {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        object-fit: cover;
      }

      /* Highlighted (AI-selected) attempt */
      .wiz-art_select-attempt.selected .wiz-art_select-attempt-img {
        border-color: #00d4aa;
        box-shadow: 0 0 0 1px #00d4aa44;
      }
      .wiz-art_select-attempt.selected .wiz-art_select-attempt-img::after {
        content: '✓ AI pick';
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        background: rgba(0, 212, 170, 0.82);
        color: #001a15;
        font-size: 0.58rem;
        font-weight: 700;
        text-align: center;
        padding: 2px 0;
        letter-spacing: 0.04em;
      }

      /* User-overridden attempt */
      .wiz-art_select-attempt.override .wiz-art_select-attempt-img {
        border-color: #ffa502;
        box-shadow: 0 0 0 1px #ffa50244;
      }
      .wiz-art_select-attempt.override .wiz-art_select-attempt-img::after {
        content: '✓ manual';
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        background: rgba(255, 165, 2, 0.82);
        color: #1a1000;
        font-size: 0.58rem;
        font-weight: 700;
        text-align: center;
        padding: 2px 0;
        letter-spacing: 0.04em;
      }

      .wiz-art_select-attempt-label {
        font-size: 0.65rem;
        color: #666;
        text-align: center;
      }

      /* AI reasoning snippet */
      .wiz-art_select-tile-reason {
        padding: 0 0.6rem 0.5rem;
        font-size: 0.7rem;
        color: #777;
        font-style: italic;
        line-height: 1.35;
      }

      /* Override button row */
      .wiz-art_select-tile-override-row {
        padding: 0 0.5rem 0.5rem;
        display: flex;
        justify-content: flex-end;
      }

      /* Locked state */
      .wiz-art_select-locked .wiz-art_select-grid {
        opacity: 0.6;
        pointer-events: none;
      }
    `;
    document.head.appendChild(style);
  }

  // ── Module-local state ─────────────────────────────────────────────────────

  const local = {
    initialized: false,
    // [{name, collector_number, selected_version, override_version, reasoning,
    //   versions: [{filename, attempt}]}]
    cards: [],
    hasContent: false,
    costUsd: 0,
    stageStatus: 'pending',
    locked: false,
    bootstrapping: false,
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ── Top-level render ────────────────────────────────────────────────────────

  function render({ root, state, stage, content, footer }) {
    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      bootstrap(root, state).catch(err => {
        W.toast('Failed to load art selection state: ' + err.message, 'error');
      });
      paintFooter(footer, state);
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
        .catch(err => W.toast('Failed to refresh art selection state: ' + err.message, 'error'))
        .finally(() => { local.bootstrapping = false; });
      return;
    }

    paintFooter(footer, state);
    setLocked(local.locked);
  }

  function mountShellHtml() {
    return `
      <div class="wiz-art_select-summary" data-role="as-summary">
        <div class="wiz-stage-empty">Loading art selection state…</div>
      </div>
      <div class="wiz-art_select-grid" data-role="as-grid"></div>
    `;
  }

  // ── Bootstrap (fetch state from server) ────────────────────────────────────

  async function bootstrap(root, state) {
    // TODO: implement GET /api/wizard/art_select/state
    // Expected response:
    //   { cards: [{name, collector_number, selected_version, override_version,
    //              reasoning, versions:[{filename, attempt}]}],
    //     has_content, cost_usd, stage_status }
    let data = null;
    try {
      const resp = await fetch('/api/wizard/art_select/state');
      if (resp.ok) {
        data = await resp.json();
      }
    } catch (_) {
      // Backend not yet wired — degrade gracefully.
    }

    if (data) {
      local.cards = Array.isArray(data.cards) ? data.cards : [];
      local.hasContent = !!data.has_content;
      local.costUsd = data.cost_usd || 0;
      local.stageStatus = data.stage_status || local.stageStatus;
    }

    paintSummary(root);
    paintGrid(root, state);
    paintFooter(getFooter(root), state);
  }

  // ── Summary block ───────────────────────────────────────────────────────────

  function paintSummary(root) {
    const slot = root.querySelector('[data-role="as-summary"]');
    if (!slot) return;
    const count = local.cards.length;
    const costStr = local.costUsd > 0 ? '$' + local.costUsd.toFixed(3) : '—';
    const selected = local.cards.filter(c => c.selected_version || c.override_version).length;
    slot.innerHTML = `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">AI art selection</h3>
      </div>
      <p class="wiz-art_select-blurb">
        Haiku vision reviews all generated attempts per card and picks the best version.
        You can override individual picks below.
      </p>
      <dl class="wiz-art_select-context">
        <dt>Cards</dt><dd>${count > 0 ? count : '—'}</dd>
        <dt>Selected</dt><dd>${count > 0 ? selected + '/' + count : '—'}</dd>
        <dt>Cost</dt><dd>${costStr}</dd>
      </dl>
    `;
  }

  // ── Image grid ──────────────────────────────────────────────────────────────

  function paintGrid(root, state) {
    const slot = root.querySelector('[data-role="as-grid"]');
    if (!slot) return;

    const generating = local.stageStatus === 'running' || local.locked;

    if (!local.hasContent || local.cards.length === 0) {
      slot.innerHTML = `
        <div class="wiz-stage-empty">
          ${generating
            ? 'Selecting best art versions…'
            : 'No selections yet. Run the Art Selection stage to let the AI pick the best versions.'}
        </div>
      `;
      return;
    }

    const isPast = isPastTab(state);
    slot.innerHTML = local.cards.map(card => selectionTileHtml(card, isPast)).join('');
    if (!isPast) bindOverrideButtons(slot);
  }

  /**
   * Thumbnail tile — one card with multiple attempt frames.
   * Selected attempt gets a green border + "AI pick" badge.
   * User-overridden attempt gets an orange border + "manual" badge.
   * Shared shape: same structure as char_portraits + art_gen tiles.
   */
  function selectionTileHtml(card, isPast) {
    const name = card.name || card.collector_number || '(unknown)';
    const versions = Array.isArray(card.versions) ? card.versions : [];
    const selected = card.override_version || card.selected_version;

    const attemptsHtml = versions.length > 0
      ? versions.map((v, i) => {
          const vLabel = 'v' + (v.attempt || (i + 1));
          const isSelected = selected === vLabel || selected === ('v' + (v.attempt || (i + 1)));
          const isOverride = !!(card.override_version && isSelected);
          const cls = isOverride ? 'override' : (isSelected ? 'selected' : '');

          // TODO: implement image serving route for card art
          // Suggested route: GET /api/art/image?path=<relative_path_under_asset>
          return `
            <div class="wiz-art_select-attempt${cls ? ' ' + cls : ''}"
                 data-version="${escAttr(vLabel)}"
                 data-card="${escAttr(card.collector_number || name)}">
              <div class="wiz-art_select-attempt-img"
                   title="${escAttr(v.filename || vLabel)}${isPast ? '' : ' — click to override selection'}">
                ${escHtml(v.filename || vLabel)}
                <!-- TODO: <img src="/api/art/image?path=${escAttr(v.filename || '')}" alt="${escAttr(name)} ${escAttr(vLabel)}" onerror="this.style.display='none'"> -->
              </div>
              <div class="wiz-art_select-attempt-label">${escHtml(vLabel)}</div>
            </div>
          `;
        }).join('')
      : `<div class="wiz-stage-empty" style="padding:0.5rem">(no versions)</div>`;

    const reasonHtml = card.reasoning
      ? `<div class="wiz-art_select-tile-reason">${escHtml(card.reasoning)}</div>`
      : '';

    // Override button: only on latest, non-locked tab.
    // TODO: implement POST /api/wizard/art_select/override
    const overrideRow = !isPast
      ? `<div class="wiz-art_select-tile-override-row">
           <button type="button" class="wiz-btn-secondary"
                   data-role="as-override"
                   data-card="${escAttr(card.collector_number || name)}"
                   title="TODO: POST /api/wizard/art_select/override"
                   disabled>
             Override…
           </button>
         </div>`
      : '';

    return `
      <div class="wiz-art_select-tile">
        <div class="wiz-art_select-tile-name" title="${escAttr(name)}">${escHtml(name)}</div>
        <div class="wiz-art_select-attempts">${attemptsHtml}</div>
        ${reasonHtml}
        ${overrideRow}
      </div>
    `;
  }

  function bindOverrideButtons(slot) {
    // TODO: wire override buttons to POST /api/wizard/art_select/override
    // For now the buttons are rendered disabled.  When the endpoint exists:
    //   btn.disabled = false;
    //   btn.onclick = () => onOverride(btn.dataset.card);
  }

  // async function onOverride(collectorNumber) {
  //   if (local.locked) return;
  //   // TODO: show a version picker dialog, then POST /api/wizard/art_select/override
  //   // { collector_number, version: 'v2' }
  //   W.toast('Manual override is not yet wired — coming soon.', 'warn');
  // }

  // ── Footer ──────────────────────────────────────────────────────────────────

  function paintFooter(footer, state) {
    if (!footer) return;
    const isLatest = !state || state.latestTabId === STAGE_ID;
    const isPaused = local.stageStatus === 'paused_for_review';
    const next = W.nextStageEntryAfter(STAGE_ID);
    const nextName = next ? next.name : 'Next step';

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Editing past art selection is destructive — use the Edit button above.</span>`;
    } else if (isPaused) {
      html = `
        <button type="button" class="wiz-btn-primary" data-role="as-next-step">
          Next step: ${escHtml(nextName)}
        </button>
      `;
    } else if (local.stageStatus === 'running') {
      html = `<span class="wiz-footer-note">Selecting best art versions… the Next Step button will appear when the stage pauses.</span>`;
    } else if (local.stageStatus === 'completed') {
      html = `<span class="wiz-footer-note">Art selection complete. Continuing to ${escHtml(nextName)}.</span>`;
    } else {
      html = `<span class="wiz-footer-note">Stage has not run yet.</span>`;
    }

    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
    }

    const btn = footer.querySelector('[data-role="as-next-step"]');
    if (btn) btn.onclick = onNextStep;
  }

  async function onNextStep() {
    const footer = document.querySelector(`.wiz-tab-body[data-tab-id="${STAGE_ID}"] [data-role="footer"]`);
    const btn = footer && footer.querySelector('[data-role="as-next-step"]');
    if (!btn || btn.disabled) return;
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
          W.toast(data.error || `Advance failed (${resp.status})`, 'error');
        }
        btn.disabled = false;
        btn.textContent = original;
      }
      // On success: leave button disabled, SSE will repaint.
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
      btn.disabled = false;
      btn.textContent = original;
    }
  }

  // ── Form lock (§3) ──────────────────────────────────────────────────────────

  function setLocked(locked) {
    local.locked = !!locked;
    const root = bodyRoot();
    if (!root) return;
    root.classList.toggle('wiz-art_select-locked', !!locked);
    const sel = ['[data-role="as-override"]'].join(',');
    root.querySelectorAll(sel).forEach(el => { el.disabled = true; }); // override stays disabled (TODO)
    const footerBtn = root.querySelector('[data-role="as-next-step"]');
    if (footerBtn) footerBtn.disabled = !!locked;
  }

  // ── Helpers ─────────────────────────────────────────────────────────────────

  function bodyRoot() {
    return document.querySelector(`.wiz-tab-body[data-tab-id="${STAGE_ID}"]`);
  }

  function getFooter(root) {
    return root && root.querySelector('[data-role="footer"]');
  }

  function isPastTab(state) {
    return !!state && state.latestTabId !== STAGE_ID;
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
