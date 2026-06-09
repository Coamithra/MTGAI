/**
 * Wizard Character References tab (stage_id ``char_portraits``).
 *
 * The reworked Character References stage (card 6a20aa84): one tile per
 * recurring entity (a named character / location that appears on >1 card), each
 * showing its neutral reference image(s), which cards it attaches to, and a
 * per-entity submenu to re-roll, upload your own image, or pick which version is
 * the attached reference.
 *
 * Built from the shared helpers (conventions §17): registerStageRenderer +
 * fetchStageState + emptyStatePanel + paintFooter/advanceStage + runAiAction +
 * setTabLocked + registerStream. The stage streams entities + images live over
 * SSE (char_refs_reset / char_refs_entity / char_refs_image).
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'char_portraits';
  // The stage_id is ``char_portraits`` (kept through the art-topology reorg) but
  // its wizard endpoints live under the ``char_refs`` base, so the generic
  // ``/api/wizard/<stageId>/state`` URL would 404. Use this base for every HTTP
  // call (state/refresh/save/image/upload); STAGE_ID stays the renderer/stream/
  // tab-routing key.
  const ENDPOINT_BASE = 'char_refs';
  const escHtml = W.escHtml;
  const escAttr = W.escAttr;

  // ── Scoped styles (injected once) ──────────────────────────────────────────

  if (!document.getElementById('wiz-char_refs-styles')) {
    const style = document.createElement('style');
    style.id = 'wiz-char_refs-styles';
    style.textContent = `
      .wiz-char_refs-blurb { color:#888; font-size:0.82rem; margin:0.25rem 0 0.75rem 0; }
      .wiz-char_refs-grid {
        display:grid; grid-template-columns:repeat(auto-fill, minmax(220px, 1fr));
        gap:0.9rem; margin-top:0.5rem;
      }
      .wiz-char_refs-tile {
        background:#0f1729; border:1px solid #1f2540; border-radius:6px;
        overflow:hidden; display:flex; flex-direction:column;
      }
      .wiz-char_refs-versions { display:flex; gap:2px; background:#12192e; }
      .wiz-char_refs-img {
        flex:1; aspect-ratio:3 / 4; background:#12192e; position:relative;
        display:flex; align-items:center; justify-content:center;
        font-size:0.65rem; color:#445; text-align:center; overflow:hidden; cursor:pointer;
      }
      .wiz-char_refs-img img { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }
      .wiz-char_refs-img.is-attached { outline:2px solid #6f7cff; outline-offset:-2px; }
      .wiz-char_refs-body { padding:0.4rem 0.55rem 0.55rem; }
      .wiz-char_refs-name { font-size:0.82rem; color:#dde; font-weight:600; }
      .wiz-char_refs-kind { font-size:0.66rem; color:#778; text-transform:uppercase; letter-spacing:0.04em; }
      .wiz-char_refs-cards { font-size:0.68rem; color:#8a94b8; margin-top:0.3rem; }
      .wiz-char_refs-note { font-size:0.68rem; color:#667; margin-top:0.2rem; font-style:italic; }
      .wiz-char_refs-actions { display:flex; gap:0.35rem; margin-top:0.45rem; }
      .wiz-char_refs-actions button, .wiz-char_refs-actions label {
        font-size:0.66rem; padding:0.2rem 0.45rem; border-radius:4px;
        border:1px solid #2a3155; background:#161d34; color:#bcc; cursor:pointer;
      }
      .wiz-char_refs-badge {
        display:inline-block; font-size:0.6rem; padding:0.05rem 0.3rem; border-radius:3px;
        background:#2a2150; color:#b9a8ff; margin-left:0.3rem;
      }
      .wiz-char_refs-locked .wiz-char_refs-grid { opacity:0.6; pointer-events:none; }
    `;
    document.head.appendChild(style);
  }

  // ── Module-local state ─────────────────────────────────────────────────────

  const local = {
    initialized: false,
    entities: [],   // [{entity_key, name, kind, cards, note, versions, attached_path}]
    hasContent: false,
    stageStatus: 'pending',
    locked: false,
    bootstrapping: false,
    state: null,
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ── SSE live stream (char_refs_reset / _entity / _image) ────────────────────

  W.registerStream(STAGE_ID, {
    char_refs_reset(_data, root) {
      local.entities = [];
      local.hasContent = false;
      if (root) paintGrid(root);
    },
    char_refs_entity(data, root) {
      const e = data.entity;
      if (!e || !e.entity_key) return;
      const item = {
        entity_key: e.entity_key,
        name: e.name || e.entity_key,
        kind: e.kind || 'entity',
        cards: Array.isArray(e.cards) ? e.cards : [],
        note: e.note || '',
        versions: [],
        attached_path: '',
        generating: true,
      };
      W.streamUpsert(local.entities, item, (x) => x.entity_key);
      local.hasContent = true;
      if (root) paintGrid(root);
    },
    char_refs_image(data, root) {
      const key = data.entity_key;
      const path = data.ref_image_path;
      if (!key || !path) return;
      const ent = local.entities.find((x) => x.entity_key === key);
      if (!ent) return;
      ent.generating = false;
      const filename = path.split('/').pop();
      if (!ent.versions.some((v) => v.filename === filename)) {
        ent.versions.push({
          filename,
          url: '/api/wizard/char_refs/image?file=' + encodeURIComponent(filename),
          is_upload: filename.indexOf('upload') >= 0,
        });
      }
      if (!ent.attached_path) ent.attached_path = path;
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
        W.toast('Failed to load character references: ' + err.message, 'error')
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
        .catch((err) => W.toast('Failed to refresh character references: ' + err.message, 'error'))
        .finally(() => { local.bootstrapping = false; });
      return;
    }

    paintFooter(footer, state);
    setLocked(local.locked);
  }

  function mountShellHtml() {
    return `
      <div data-role="cr-summary"></div>
      <div class="wiz-char_refs-grid" data-role="cr-grid"></div>
    `;
  }

  // ── Bootstrap ───────────────────────────────────────────────────────────────

  async function bootstrap(root, state) {
    local.state = state;
    const data = await W.fetchStageState(ENDPOINT_BASE);
    if (data) {
      local.entities = Array.isArray(data.entities) ? data.entities : [];
      local.hasContent = !!data.has_content;
      local.stageStatus = data.stage_status || local.stageStatus;
    }
    paintSummary(root);
    paintGrid(root);
    paintFooter(W.tabFooter(root), state);
    setLocked(local.locked);
  }

  // ── Summary ──────────────────────────────────────────────────────────────────

  function paintSummary(root) {
    const slot = root.querySelector('[data-role="cr-summary"]');
    if (!slot) return;
    const isLatest = !local.state || local.state.latestTabId === STAGE_ID;
    const count = local.entities.length;
    slot.innerHTML = `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">Character references</h3>
        ${isLatest ? `<button type="button" class="wiz-refresh-btn" data-role="cr-refresh">
          ${count > 0 ? 'Re-detect &amp; regenerate…' : 'Generate references'}
        </button>` : ''}
      </div>
      <p class="wiz-char_refs-blurb">
        Neutral identity references for entities that recur across more than one card
        (characters AND locations). Each becomes conditioning for the Art Generation
        stage. One-card entities are skipped. ${count > 0 ? `<strong>${count}</strong> recurring entit${count === 1 ? 'y' : 'ies'}.` : ''}
      </p>
    `;
    const btn = slot.querySelector('[data-role="cr-refresh"]');
    if (btn) btn.onclick = onRefresh;
  }

  // ── Grid ──────────────────────────────────────────────────────────────────────

  function paintGrid(root) {
    const slot = root.querySelector('[data-role="cr-grid"]');
    if (!slot) return;
    const generating = local.stageStatus === 'running' || local.locked;

    if (!local.hasContent || local.entities.length === 0) {
      slot.innerHTML = `
        <div class="wiz-stage-empty">
          ${generating
            ? 'Detecting recurring entities and generating references…'
            : 'No recurring entities found yet. Run the Character References stage to detect them.'}
        </div>`;
      return;
    }
    slot.innerHTML = local.entities.map(entityTileHtml).join('');
    local.entities.forEach((ent) => bindTile(slot, ent));
  }

  function entityTileHtml(ent) {
    const versions = Array.isArray(ent.versions) ? ent.versions : [];
    const attachedFile = (ent.attached_path || '').split('/').pop();
    const imgs = versions.length
      ? versions
          .map((v) => {
            const isAttached = v.filename === attachedFile;
            return `<div class="wiz-char_refs-img ${isAttached ? 'is-attached' : ''}"
                 data-version="${escAttr(v.filename)}" title="Click to set as the attached reference">
              <img src="${escAttr(v.url)}" alt="${escAttr(ent.name)}" onerror="this.style.display='none'">
            </div>`;
          })
          .join('')
      : `<div class="wiz-char_refs-img">${ent.generating ? 'generating…' : '(no image)'}</div>`;

    const cards = (ent.cards || []).map(escHtml).join(', ');
    return `
      <div class="wiz-char_refs-tile" data-key="${escAttr(ent.entity_key)}">
        <div class="wiz-char_refs-versions">${imgs}</div>
        <div class="wiz-char_refs-body">
          <div class="wiz-char_refs-name">${escHtml(ent.name)}
            ${ent.generating ? '<span class="wiz-char_refs-badge">generating</span>' : ''}
          </div>
          <div class="wiz-char_refs-kind">${escHtml(ent.kind || 'entity')}</div>
          <div class="wiz-char_refs-cards">On ${(ent.cards || []).length} cards: ${cards}</div>
          ${ent.note ? `<div class="wiz-char_refs-note">${escHtml(ent.note)}</div>` : ''}
          <div class="wiz-char_refs-actions">
            <label>Upload
              <input type="file" accept="image/*" data-role="cr-upload" style="display:none">
            </label>
          </div>
        </div>
      </div>`;
  }

  function bindTile(slot, ent) {
    const tile = slot.querySelector(`.wiz-char_refs-tile[data-key="${W.cssEsc(ent.entity_key)}"]`);
    if (!tile) return;
    tile.querySelectorAll('[data-version]').forEach((node) => {
      node.onclick = () => onSelectVersion(ent.entity_key, node.dataset.version);
    });
    const upload = tile.querySelector('[data-role="cr-upload"]');
    if (upload) {
      upload.onchange = () => {
        const f = upload.files && upload.files[0];
        if (f) onUpload(ent.entity_key, f);
      };
    }
  }

  // ── Actions ──────────────────────────────────────────────────────────────────

  function onRefresh() {
    W.runAiAction({
      isLocked: () => local.locked,
      setLocked,
      confirm: () => (local.hasContent ? 'Re-detect entities and regenerate all references?' : ''),
      busyLabel: 'Generating references…',
      url: '/api/wizard/char_refs/refresh',
      body: () => ({}),
      fallback: 'Character references failed',
      onResult: (data) => applyState(data),
    });
  }

  async function onSelectVersion(entityKey, filename) {
    if (local.locked) return;
    const ref = 'art-direction/character-refs/' + filename;
    try {
      const resp = await W.postJSON('/api/wizard/char_refs/save', {
        entity_key: entityKey,
        ref_image_path: ref,
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { W.reportError(resp, data, 'Failed to set reference'); return; }
      applyState(data);
      W.toast('Reference updated', 'success');
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    }
  }

  async function onUpload(entityKey, file) {
    if (local.locked) return;
    const form = new FormData();
    form.append('entity_key', entityKey);
    form.append('file', file);
    try {
      const resp = await fetch('/api/wizard/char_refs/upload', { method: 'POST', body: form });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { W.reportError(resp, data, 'Upload failed'); return; }
      applyState(data);
      W.toast('Uploaded reference for ' + entityKey, 'success');
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    }
  }

  function applyState(data) {
    if (!data) return;
    local.entities = Array.isArray(data.entities) ? data.entities : local.entities;
    local.hasContent = !!data.has_content;
    if (data.stage_status) local.stageStatus = data.stage_status;
    const root = bodyRoot();
    if (root) { paintSummary(root); paintGrid(root); }
  }

  // ── Footer (auto-run stage; Next-step when paused) ──────────────────────────

  function paintFooter(footer, state) {
    if (!footer) return;
    const wstate = state || local.state;
    const isLatest = !wstate || wstate.latestTabId === STAGE_ID;
    const isPaused = local.stageStatus === 'paused_for_review';
    const next = W.nextStageEntryAfter(STAGE_ID);
    const nextName = next ? next.name : 'Next step';

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Editing past character references is destructive — use the Edit button above.</span>`;
    } else if (isPaused || W.completedTipCanAdvance(wstate, STAGE_ID)) {
      // 'completed' + can-advance is the saved/reopened dead-end: the stage
      // finished but the pipeline persisted PAUSED with a later stage pending
      // and no PAUSED_FOR_REVIEW pause. Surface the Next-step button so the
      // user can resume instead of being stranded by the "Continuing…" note.
      html = `<button type="button" class="wiz-btn-primary" data-role="cr-advance">Next step: ${escHtml(nextName)}</button>`;
    } else if (local.stageStatus === 'running') {
      html = `<span class="wiz-footer-note">Generating references… the Next Step button will appear when the stage pauses.</span>`;
    } else if (local.stageStatus === 'completed') {
      html = `<span class="wiz-footer-note">References generated. Continuing to ${escHtml(nextName)}.</span>`;
    } else {
      html = `<span class="wiz-footer-note">Stage has not run yet.</span>`;
    }

    W.paintFooter(footer, html, {
      role: 'cr-advance',
      onClick: () => W.advanceStage({
        stageId: STAGE_ID,
        isLocked: () => local.locked,
        setLocked,
        btnRole: 'cr-advance',
        navigate: false,
      }),
    });
  }

  // ── Form lock (§3) ──────────────────────────────────────────────────────────

  function aiBusy() {
    return local.locked || local.stageStatus === 'running';
  }

  function setLocked(locked) {
    local.locked = !!locked;
    W.setTabLocked(bodyRoot(), aiBusy(), {
      lockClass: 'wiz-char_refs-locked',
      selectors: [
        '[data-role="cr-refresh"]',
        '[data-role="cr-upload"]',
        '.wiz-char_refs-img',
      ],
      footerSelector: '[data-role="cr-advance"]',
    });
  }

  // ── Helpers ─────────────────────────────────────────────────────────────────

  function bodyRoot() {
    return W.tabRoot(STAGE_ID);
  }
})();
