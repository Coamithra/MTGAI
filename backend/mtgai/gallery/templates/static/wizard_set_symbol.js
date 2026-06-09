/**
 * Wizard Set Symbol tab (stage_id ``set_symbol``).
 *
 * The per-set glyph (the type-line symbol). One LLM call proposes an emblem from
 * the theme, Flux renders a few candidate silhouettes, and the renderer recolors
 * the chosen mask per rarity (replacing the hardcoded placeholder triangle). The
 * tab shows the concept + the candidate previews, with re-roll / upload-your-own
 * / pick-which-version — mirroring the Character References tab.
 *
 * Streams live over SSE: set_symbol_reset / set_symbol_concept / set_symbol_version.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'set_symbol';
  const escHtml = W.escHtml;
  const escAttr = W.escAttr;

  if (!document.getElementById('wiz-set_symbol-styles')) {
    const style = document.createElement('style');
    style.id = 'wiz-set_symbol-styles';
    style.textContent = `
      .wiz-setsym-blurb { color:#888; font-size:0.82rem; margin:0.25rem 0 0.75rem 0; }
      .wiz-setsym-concept { color:#cdd; font-size:0.85rem; margin:0.2rem 0 0.6rem 0; }
      .wiz-setsym-concept .tag, .wiz-setsym-prompt .tag { color:#8a94b8; }
      .wiz-setsym-prompt { color:#667; font-size:0.72rem; font-style:italic; margin:0 0 0.6rem 0; }
      .wiz-setsym-grid {
        display:grid; grid-template-columns:repeat(auto-fill, minmax(150px, 1fr));
        gap:0.9rem; margin-top:0.5rem;
      }
      .wiz-setsym-tile {
        background:#0f1729; border:1px solid #1f2540; border-radius:6px;
        overflow:hidden; cursor:pointer; position:relative;
      }
      .wiz-setsym-tile.is-selected { outline:2px solid #6f7cff; outline-offset:-2px; }
      .wiz-setsym-img {
        aspect-ratio:1 / 1; background:#12192e; display:flex; align-items:center;
        justify-content:center; position:relative;
      }
      .wiz-setsym-img img { width:82%; height:82%; object-fit:contain; }
      .wiz-setsym-zoom {
        position:absolute; top:4px; right:4px; font-size:0.7rem; padding:0.1rem 0.3rem;
        border-radius:4px; border:1px solid #2a3155; background:rgba(8,12,24,0.8); color:#bcc;
        opacity:0; transition:opacity 0.12s;
      }
      .wiz-setsym-tile:hover .wiz-setsym-zoom { opacity:1; }
      .wiz-setsym-cap {
        font-size:0.66rem; color:#8a94b8; text-align:center; padding:0.25rem;
        text-transform:uppercase; letter-spacing:0.04em;
      }
      .wiz-setsym-cap .sel { color:#b9a8ff; }
      .wiz-setsym-actions { display:flex; gap:0.4rem; margin:0.4rem 0 0.2rem 0; }
      .wiz-setsym-actions label {
        font-size:0.72rem; padding:0.25rem 0.5rem; border-radius:4px;
        border:1px solid #2a3155; background:#161d34; color:#bcc; cursor:pointer;
      }
      .wiz-setsym-locked .wiz-setsym-grid { opacity:0.6; pointer-events:none; }
    `;
    document.head.appendChild(style);
  }

  const local = {
    initialized: false,
    concept: '',
    imagePrompt: '',
    rationale: '',
    versions: [], // [{tag, is_upload, preview_url, raw_url, is_selected}]
    selected: '',
    hasContent: false,
    stageStatus: 'pending',
    locked: false,
    bootstrapping: false,
    state: null,
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ── SSE live stream ─────────────────────────────────────────────────────────

  W.registerStream(STAGE_ID, {
    set_symbol_reset(_data, root) {
      local.versions = [];
      local.hasContent = false;
      local.selected = '';
      if (root) paintGrid(root);
    },
    set_symbol_concept(data, root) {
      local.concept = data.concept || '';
      local.imagePrompt = data.image_prompt || '';
      if (root) paintSummary(root);
    },
    set_symbol_version(data, root) {
      const version = data.version;
      if (version == null) return;
      const tag = String(version);
      // Cache-buster: a Re-roll overwrites preview_v*.png in place, so without a
      // fresh query param the browser serves the cached old glyph (matches the
      // rendering tab's ?t=Date.now()). The /state payload uses the file mtime.
      const preview =
        '/api/wizard/set_symbol/image?file=' +
        encodeURIComponent('preview_v' + tag + '.png') +
        '&t=' + Date.now();
      const item = { tag, is_upload: false, preview_url: preview, raw_url: '', is_selected: false };
      W.streamUpsert(local.versions, item, (x) => x.tag);
      // The engine selects the first candidate by default; reflect that live.
      if (!local.selected) { local.selected = tag; item.is_selected = true; }
      local.versions.forEach((v) => { v.is_selected = v.tag === local.selected; });
      local.hasContent = true;
      if (root) paintGrid(root);
    },
  });

  // ── Top-level render ────────────────────────────────────────────────────────

  function render({ root, state, stage, content, footer }) {
    local.state = state;
    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      bootstrap(root, state).catch((err) =>
        W.toast('Failed to load set symbol: ' + err.message, 'error')
      );
      paintFooter(footer, state);
      return;
    }

    const prevStatus = local.stageStatus;
    if (stage) local.stageStatus = stage.status;
    const justFinished =
      stage &&
      prevStatus !== local.stageStatus &&
      local.stageStatus !== 'pending' &&
      local.stageStatus !== 'running' &&
      !local.hasContent &&
      !local.bootstrapping;
    if (justFinished) {
      local.bootstrapping = true;
      bootstrap(root, state)
        .catch((err) => W.toast('Failed to refresh set symbol: ' + err.message, 'error'))
        .finally(() => { local.bootstrapping = false; });
      return;
    }

    paintFooter(footer, state);
    setLocked(local.locked);
  }

  function mountShellHtml() {
    return `
      <div data-role="ss-summary"></div>
      <div class="wiz-setsym-grid" data-role="ss-grid"></div>
    `;
  }

  async function bootstrap(root, state) {
    local.state = state;
    const data = await W.fetchStageState(STAGE_ID);
    if (data) applyData(data);
    paintSummary(root);
    paintGrid(root);
    paintFooter(W.tabFooter(root), state);
    setLocked(local.locked);
  }

  function applyData(data) {
    if (!data) return;
    local.concept = data.concept || '';
    local.imagePrompt = data.image_prompt || '';
    local.rationale = data.rationale || '';
    local.versions = Array.isArray(data.versions) ? data.versions : [];
    local.selected = data.selected_version || '';
    local.hasContent = !!data.has_content;
    if (data.stage_status) local.stageStatus = data.stage_status;
  }

  // ── Summary ──────────────────────────────────────────────────────────────────

  function paintSummary(root) {
    const slot = root.querySelector('[data-role="ss-summary"]');
    if (!slot) return;
    const isLatest = !local.state || local.state.latestTabId === STAGE_ID;
    const has = local.versions.length > 0;
    slot.innerHTML = `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">Set symbol</h3>
        ${isLatest ? `<div class="wiz-setsym-actions">
          <label>Upload your own
            <input type="file" accept="image/*" data-role="ss-upload" style="display:none">
          </label>
          <button type="button" class="wiz-refresh-btn" data-role="ss-refresh">
            ${has ? 'Re-roll&hellip;' : 'Generate set symbol'}
          </button>
        </div>` : ''}
      </div>
      <p class="wiz-setsym-blurb">
        The identifying glyph in every card's type line — generated from the set's
        identity and recolored per rarity at render time. Pick a candidate below,
        re-roll, or upload your own 2-tone icon.
      </p>
      ${local.concept ? `<div class="wiz-setsym-concept"><span class="tag">Concept:</span> ${escHtml(local.concept)}</div>` : ''}
      ${local.imagePrompt ? `<div class="wiz-setsym-prompt">${escHtml(local.imagePrompt)}</div>` : ''}
      ${local.rationale ? `<div class="wiz-setsym-prompt"><span class="tag">Why:</span> ${escHtml(local.rationale)}</div>` : ''}
    `;
    const btn = slot.querySelector('[data-role="ss-refresh"]');
    if (btn) btn.onclick = onRefresh;
    const upload = slot.querySelector('[data-role="ss-upload"]');
    if (upload) {
      upload.onchange = () => {
        const f = upload.files && upload.files[0];
        if (f) onUpload(f);
      };
    }
  }

  // ── Grid ──────────────────────────────────────────────────────────────────────

  function paintGrid(root) {
    const slot = root.querySelector('[data-role="ss-grid"]');
    if (!slot) return;
    const generating = local.stageStatus === 'running' || local.locked;
    if (!local.hasContent || local.versions.length === 0) {
      slot.innerHTML = `
        <div class="wiz-stage-empty">
          ${generating
            ? 'Proposing a concept and rendering candidate glyphs&hellip;'
            : 'No set symbol yet. Generate one, or upload your own icon.'}
        </div>`;
      return;
    }
    slot.innerHTML = local.versions.map(tileHtml).join('');
    local.versions.forEach((v) => bindTile(slot, v));
  }

  function tileHtml(v) {
    const label = v.is_upload ? 'uploaded' : 'candidate ' + v.tag;
    return `
      <div class="wiz-setsym-tile ${v.is_selected ? 'is-selected' : ''}" data-tag="${escAttr(v.tag)}"
           title="Click to use this as the set symbol">
        <div class="wiz-setsym-img">
          <img src="${escAttr(v.preview_url)}" alt="set symbol ${escAttr(v.tag)}" onerror="this.style.display='none'">
          <button type="button" class="wiz-setsym-zoom" data-role="ss-zoom">&#x2922;</button>
        </div>
        <div class="wiz-setsym-cap">${escHtml(label)}${v.is_selected ? ' <span class="sel">&#10003; in use</span>' : ''}</div>
      </div>`;
  }

  function bindTile(slot, v) {
    const tile = slot.querySelector(`.wiz-setsym-tile[data-tag="${W.cssEsc(v.tag)}"]`);
    if (!tile) return;
    tile.onclick = () => onSelect(v.tag);
    const zoom = tile.querySelector('[data-role="ss-zoom"]');
    if (zoom) {
      zoom.onclick = (e) => {
        e.stopPropagation();
        const img = tile.querySelector('img');
        if (img && window.MTGAILightbox) window.MTGAILightbox.open({ src: img.src, alt: 'set symbol ' + v.tag });
      };
    }
  }

  // ── Actions ──────────────────────────────────────────────────────────────────

  function onRefresh() {
    W.runAiAction({
      isLocked: () => local.locked,
      setLocked,
      confirm: () => (local.hasContent ? 'Re-propose a concept and regenerate all candidate glyphs?' : ''),
      busyLabel: 'Generating set symbol…',
      url: '/api/wizard/set_symbol/refresh',
      body: () => ({}),
      fallback: 'Set symbol generation failed',
      onResult: (data) => { applyData(data); repaint(); },
    });
  }

  async function onSelect(tag) {
    if (local.locked) return;
    try {
      const resp = await W.postJSON('/api/wizard/set_symbol/save', { version: tag });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { W.reportError(resp, data, 'Failed to set symbol'); return; }
      applyData(data);
      repaint();
      W.toast('Set symbol updated', 'success');
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    }
  }

  async function onUpload(file) {
    if (local.locked) return;
    const form = new FormData();
    form.append('file', file);
    try {
      const resp = await fetch('/api/wizard/set_symbol/upload', { method: 'POST', body: form });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { W.reportError(resp, data, 'Upload failed'); return; }
      applyData(data);
      repaint();
      W.toast('Uploaded set symbol', 'success');
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    }
  }

  function repaint() {
    const root = bodyRoot();
    if (root) { paintSummary(root); paintGrid(root); }
  }

  // ── Footer ──────────────────────────────────────────────────────────────────

  function paintFooter(footer, state) {
    if (!footer) return;
    const wstate = state || local.state;
    const isLatest = !wstate || wstate.latestTabId === STAGE_ID;
    const isPaused = local.stageStatus === 'paused_for_review';
    const next = W.nextStageEntryAfter(STAGE_ID);
    const nextName = next ? next.name : 'Next step';

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Editing a past set symbol is destructive — use the Edit button above.</span>`;
    } else if (isPaused || W.completedTipCanAdvance(wstate, STAGE_ID)) {
      html = `<button type="button" class="wiz-btn-primary" data-role="ss-advance">Next step: ${escHtml(nextName)}</button>`;
    } else if (local.stageStatus === 'running') {
      html = `<span class="wiz-footer-note">Generating set symbol… the Next Step button will appear when the stage pauses.</span>`;
    } else if (local.stageStatus === 'completed') {
      html = `<span class="wiz-footer-note">Set symbol generated. Continuing to ${escHtml(nextName)}.</span>`;
    } else {
      html = `<span class="wiz-footer-note">Stage has not run yet.</span>`;
    }

    W.paintFooter(footer, html, {
      role: 'ss-advance',
      onClick: () => W.advanceStage({
        stageId: STAGE_ID,
        isLocked: () => local.locked,
        setLocked,
        btnRole: 'ss-advance',
        navigate: false,
      }),
    });
  }

  // ── Form lock ────────────────────────────────────────────────────────────────

  function aiBusy() {
    return local.locked || local.stageStatus === 'running';
  }

  function setLocked(locked) {
    local.locked = !!locked;
    W.setTabLocked(bodyRoot(), aiBusy(), {
      lockClass: 'wiz-setsym-locked',
      selectors: [
        '[data-role="ss-refresh"]',
        '[data-role="ss-upload"]',
        '.wiz-setsym-tile',
      ],
      footerSelector: '[data-role="ss-advance"]',
    });
  }

  function bodyRoot() {
    return W.tabRoot(STAGE_ID);
  }
})();
