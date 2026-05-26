/**
 * Wizard Character Portraits tab — grid of character reference portrait tiles.
 *
 * Registers via ``W.registerStageRenderer('char_portraits', ...)`` so the
 * standard wizard_stage.js shell still owns the header (status pill,
 * break-point toggle, Edit-cascade button) and we just paint the body + footer.
 *
 * Generates headshot reference portraits for legendary humanoid characters into
 * ``<asset>/art-direction/character-refs/<slug>_v<N>.png``.
 * Result shape from stages.py: ``{ generated: N }``
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
  const STAGE_ID = 'char_portraits';

  // ── Scoped styles (injected once) ──────────────────────────────────────────

  if (!document.getElementById('wiz-char_portraits-styles')) {
    const style = document.createElement('style');
    style.id = 'wiz-char_portraits-styles';
    style.textContent = `
      /* Character Portraits tab — image-grid layout */

      .wiz-char_portraits-summary {
        margin-bottom: 1rem;
      }

      .wiz-char_portraits-context {
        display: grid;
        grid-template-columns: max-content 1fr;
        gap: 0.3rem 1rem;
        font-size: 0.82rem;
        margin: 0.5rem 0 0 0;
      }
      .wiz-char_portraits-context dt { color: #888; }
      .wiz-char_portraits-context dd { margin: 0; color: #ddd; }

      .wiz-char_portraits-blurb {
        color: #888;
        font-size: 0.82rem;
        margin: 0.25rem 0 0.5rem 0;
      }

      /* Image grid shared shape — identical in char_portraits / art_gen / art_select */
      .wiz-char_portraits-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
        gap: 0.75rem;
        margin-top: 0.75rem;
      }

      /* Thumbnail tile — shared shape (duplicated identically in art_gen + art_select) */
      .wiz-char_portraits-tile {
        background: #0f1729;
        border: 1px solid #1f2540;
        border-radius: 6px;
        overflow: hidden;
        display: flex;
        flex-direction: column;
      }
      .wiz-char_portraits-tile-img {
        width: 100%;
        aspect-ratio: 3 / 4;   /* portrait orientation */
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
      .wiz-char_portraits-tile-img img {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        object-fit: cover;
      }
      .wiz-char_portraits-tile-name {
        padding: 0.35rem 0.5rem;
        font-size: 0.75rem;
        color: #ccc;
        font-weight: 600;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .wiz-char_portraits-tile-sub {
        padding: 0 0.5rem 0.35rem;
        font-size: 0.68rem;
        color: #666;
      }

      /* Locked-state visual cue */
      .wiz-char_portraits-locked .wiz-char_portraits-grid {
        opacity: 0.6;
        pointer-events: none;
      }
    `;
    document.head.appendChild(style);
  }

  // ── Module-local state ─────────────────────────────────────────────────────

  const local = {
    initialized: false,
    characters: [],     // [{key, name, versions: [{filename, attempt}]}]
    hasContent: false,
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
        W.toast('Failed to load character portraits state: ' + err.message, 'error');
      });
      paintFooter(footer, state);
      return;
    }

    const prevStatus = local.stageStatus;
    if (stage) local.stageStatus = stage.status;

    // If we had no content and the stage just finished, re-bootstrap.
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
        .catch(err => W.toast('Failed to refresh character portraits: ' + err.message, 'error'))
        .finally(() => { local.bootstrapping = false; });
      return;
    }

    paintFooter(footer, state);
    setLocked(local.locked);
  }

  function mountShellHtml() {
    return `
      <div class="wiz-char_portraits-summary" data-role="cp-summary">
        <div class="wiz-stage-empty">Loading character portraits state…</div>
      </div>
      <div class="wiz-char_portraits-grid" data-role="cp-grid"></div>
    `;
  }

  // ── Bootstrap (fetch state from server) ────────────────────────────────────

  async function bootstrap(root, state) {
    // TODO: implement GET /api/wizard/char_portraits/state
    // Expected response: { characters: [{key, name, versions: [{filename}]}], has_content, stage_status }
    let data = null;
    try {
      const resp = await fetch('/api/wizard/char_portraits/state');
      if (resp.ok) {
        data = await resp.json();
      }
    } catch (_) {
      // Backend not yet wired — degrade gracefully.
    }

    if (data) {
      local.characters = Array.isArray(data.characters) ? data.characters : [];
      local.hasContent = !!data.has_content;
      local.stageStatus = data.stage_status || local.stageStatus;
    }

    paintSummary(root);
    paintGrid(root);
    paintFooter(getFooter(root), state);
  }

  // ── Summary block ───────────────────────────────────────────────────────────

  function paintSummary(root) {
    const slot = root.querySelector('[data-role="cp-summary"]');
    if (!slot) return;
    const count = local.characters.length;
    slot.innerHTML = `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">Character reference portraits</h3>
      </div>
      <p class="wiz-char_portraits-blurb">
        Front-facing headshots for legendary humanoid characters —
        used as face-identity anchors (PuLID-Flux) for card art generation.
      </p>
      <dl class="wiz-char_portraits-context">
        <dt>Characters</dt><dd>${count > 0 ? count : '—'}</dd>
        <dt>Output</dt><dd>art-direction/character-refs/</dd>
      </dl>
    `;
  }

  // ── Image grid ──────────────────────────────────────────────────────────────

  function paintGrid(root) {
    const slot = root.querySelector('[data-role="cp-grid"]');
    if (!slot) return;

    const generating = local.stageStatus === 'running' || local.locked;

    if (!local.hasContent || local.characters.length === 0) {
      slot.innerHTML = `
        <div class="wiz-stage-empty">
          ${generating
            ? 'Generating character reference portraits…'
            : 'No portraits generated yet. Run the Character Portraits stage to generate them.'}
        </div>
      `;
      return;
    }

    slot.innerHTML = local.characters
      .map(char => portraitTileHtml(char))
      .join('');
  }

  /**
   * Thumbnail tile — one portrait character.
   * Shared shape: same structure as art_gen + art_select tiles.
   */
  function portraitTileHtml(char) {
    const name = char.name || char.key || '(unknown)';
    const versions = Array.isArray(char.versions) ? char.versions : [];
    const v1 = versions[0];

    // TODO: implement image serving route for character portraits
    // Placeholder: show filename in frame, attempt to load via /api/art/image?path=...
    const imgHtml = v1
      ? `<div class="wiz-char_portraits-tile-img">
           ${escHtml(v1.filename || '')}
           <!-- TODO: <img src="/api/art/image?path=${escAttr(v1.filename || '')}" alt="${escAttr(name)}" onerror="this.style.display='none'"> -->
         </div>`
      : `<div class="wiz-char_portraits-tile-img">(no portrait)</div>`;

    const versionLabel = versions.length > 1
      ? `${versions.length} versions`
      : versions.length === 1 ? '1 version' : '';

    return `
      <div class="wiz-char_portraits-tile">
        ${imgHtml}
        <div class="wiz-char_portraits-tile-name" title="${escAttr(name)}">${escHtml(name)}</div>
        ${versionLabel ? `<div class="wiz-char_portraits-tile-sub">${escHtml(versionLabel)}</div>` : ''}
      </div>
    `;
  }

  // ── Footer ──────────────────────────────────────────────────────────────────

  function paintFooter(footer, state) {
    if (!footer) return;
    const isLatest = !state || state.latestTabId === STAGE_ID;
    const isPaused = local.stageStatus === 'paused_for_review';
    const next = W.nextStageEntryAfter(STAGE_ID);
    const nextName = next ? next.name : 'Next step';

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Editing past portrait output is destructive — use the Edit button above.</span>`;
    } else if (isPaused) {
      html = `
        <button type="button" class="wiz-btn-primary" data-role="cp-next-step">
          Next step: ${escHtml(nextName)}
        </button>
      `;
    } else if (local.stageStatus === 'running') {
      html = `<span class="wiz-footer-note">Generating portraits… the Next Step button will appear when the stage pauses.</span>`;
    } else if (local.stageStatus === 'completed') {
      html = `<span class="wiz-footer-note">Portraits generated. Continuing to ${escHtml(nextName)}.</span>`;
    } else {
      html = `<span class="wiz-footer-note">Stage has not run yet.</span>`;
    }

    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
    }

    const btn = footer.querySelector('[data-role="cp-next-step"]');
    if (btn) btn.onclick = onNextStep;
  }

  async function onNextStep() {
    const footer = document.querySelector(`.wiz-tab-body[data-tab-id="${STAGE_ID}"] [data-role="footer"]`);
    const btn = footer && footer.querySelector('[data-role="cp-next-step"]');
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
    root.classList.toggle('wiz-char_portraits-locked', !!locked);
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
