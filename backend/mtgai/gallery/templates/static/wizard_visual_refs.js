/**
 * Wizard Visual References & Artists tab (stage_id ``visual_refs``).
 *
 * A fully editable art-direction surface, built on the standard stage shell
 * (``W.registerStageRenderer`` → wizard_stage.js owns the header: status pill,
 * break-point toggle, Edit-cascade). Three sections:
 *
 *   1. Art-Direction Dictionary — four entity categories, each a 2-column table
 *      (entry name | art-direction prose), one row per entity. Keys and prose
 *      are editable and the user can ADD their own rows. Below it: the Flux term
 *      replacements table, the visual motifs list, and the set-wide art
 *      direction textarea.
 *   2. Artist Directory — rows of (made-up artist name | style description),
 *      re-rollable as a set + manually editable + add/remove rows.
 *
 * Files (frozen contracts — plans/art-render-contracts.md):
 *   art-direction/visual-references.json: { legendary_characters, creature_types,
 *     factions, landmarks (each {slug:prose}), flux_term_replacements {term:repl},
 *     visual_motifs [str], set_art_direction str }
 *   art-direction/artists.json: { artists: [{name, style_prompt}] }
 *
 * Conventions:
 *   §1  one primary "Save & Continue" footer (when paused for review)
 *   §3  form lock during AI gen
 *   §6  past-tab edits route through the Edit cascade (read-only grid)
 *   §8  status pill flows from stage state
 *   §9  "Stop after this step" — handled by wizard_stage.js
 *   §13 section-level Refresh AI buttons, always rendered on the latest tab
 *
 * The stage is AUTO by default; the full review experience is reached by ticking
 * "Stop after this step" (the stage then pauses and the Save & Continue footer
 * appears).
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'visual_refs';

  const ENTITY_CATEGORIES = [
    { key: 'legendary_characters', label: 'Legendary Characters' },
    { key: 'creature_types',       label: 'Creature Types' },
    { key: 'factions',             label: 'Factions' },
    { key: 'landmarks',            label: 'Landmarks' },
  ];

  const local = {
    initialized: false,
    // entities: { <cat>: [{key, description}] }
    entities: {},
    flux: [],        // [{term, replacement}]
    motifs: [],      // [str]
    setArtDirection: '',
    artists: [],     // [{name, style_prompt}]
    hasContent: false,
    artistTarget: 0,
    setParams: { set_name: '', set_size: 0 },
    modelId: '',
    stageStatus: 'pending',
    locked: false,
    bootstrapping: false,
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ----------------------------------------------------------------------
  // Top-level render
  // ----------------------------------------------------------------------

  function render({ root, state, stage, content, footer }) {
    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      bootstrap(root, state).catch(err => {
        W.toast('Failed to load visual references: ' + err.message, 'error');
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
        .catch(err => W.toast('Failed to refresh visual references: ' + err.message, 'error'))
        .finally(() => { local.bootstrapping = false; });
      return;
    }
    paintFooter(footer, state);
    setLocked(local.locked);
  }

  function mountShellHtml() {
    return `
      <div class="wiz-vr-summary" data-role="vr-summary">
        <div class="wiz-stage-empty">Loading visual references…</div>
      </div>
      <div class="wiz-vr-body" data-role="vr-body"></div>
    `;
  }

  // ----------------------------------------------------------------------
  // Bootstrap from server
  // ----------------------------------------------------------------------

  async function bootstrap(root, state) {
    const data = await W.fetchStageState(STAGE_ID);
    if (data) applyState(data);
    paintSummary(root, state);
    paintBody(root, state);
    paintFooter(getFooter(root), state);
  }

  function applyState(data) {
    const ents = (data && data.entities) || {};
    local.entities = {};
    ENTITY_CATEGORIES.forEach(cat => {
      const rows = Array.isArray(ents[cat.key]) ? ents[cat.key] : [];
      local.entities[cat.key] = rows.map(r => ({
        key: String((r && r.key) || ''),
        description: String((r && r.description) || ''),
      }));
    });
    const flux = (data && data.flux_term_replacements) || {};
    local.flux = Object.keys(flux).map(term => ({ term, replacement: String(flux[term] || '') }));
    local.motifs = Array.isArray(data && data.visual_motifs)
      ? data.visual_motifs.map(m => String(m || ''))
      : [];
    local.setArtDirection = String((data && data.set_art_direction) || '');
    local.artists = Array.isArray(data && data.artists)
      ? data.artists.map(a => ({
          name: String((a && a.name) || ''),
          style_prompt: String((a && a.style_prompt) || ''),
        }))
      : [];
    local.hasContent = !!(data && data.has_content);
    local.artistTarget = (data && data.artist_count_target) || 0;
    local.setParams = (data && data.set_params) || local.setParams;
    local.modelId = (data && data.model_id) || '';
    local.stageStatus = (data && data.stage_status) || local.stageStatus;
  }

  // ----------------------------------------------------------------------
  // Summary
  // ----------------------------------------------------------------------

  function paintSummary(root, state) {
    const slot = root.querySelector('[data-role="vr-summary"]');
    if (!slot) return;
    const sp = local.setParams;
    const entityCount = ENTITY_CATEGORIES.reduce(
      (n, c) => n + (local.entities[c.key] || []).length, 0);
    slot.innerHTML = `
      <h3 style="margin:0 0 0.4rem">Visual References &amp; Artists</h3>
      <p class="wiz-vr-blurb">
        A transform of the theme into consistent art direction — a full visual
        brief per entity (so the same character always paints the same way), a
        roster of made-up artists, and the set-wide aesthetic. All editable below.
      </p>
      <dl class="wiz-vr-context">
        <dt>Set</dt><dd>${escHtml(sp.set_name || '(unnamed)')}</dd>
        <dt>Size</dt><dd>${escHtml(String(sp.set_size || 0))} cards</dd>
        <dt>Entities</dt><dd>${entityCount}</dd>
        <dt>Artists</dt><dd>${local.artists.length}</dd>
        <dt>Model</dt><dd>${escHtml(local.modelId || '?')}</dd>
      </dl>
    `;
  }

  // ----------------------------------------------------------------------
  // Body — dictionary + flux + motifs + set direction + artists
  // ----------------------------------------------------------------------

  function paintBody(root, state) {
    const slot = root.querySelector('[data-role="vr-body"]');
    if (!slot) return;
    const isPast = isPastTab(state);
    const ro = isPast ? 'disabled' : '';

    if (!local.hasContent) {
      slot.innerHTML = `
        ${dictHeaderHtml(isPast)}
        ${W.emptyStatePanel({
          generating: aiBusy(),
          generatingMsg: 'Transforming the theme into art direction…',
          emptyMsg: 'No visual references yet. Click "Generate" above, or advance from Finalization.',
          className: 'wiz-vr-empty',
        })}
      `;
      bindDictHeader(slot);
      return;
    }

    slot.innerHTML = `
      ${dictHeaderHtml(isPast)}
      ${ENTITY_CATEGORIES.map(cat => entityTableHtml(cat, ro)).join('')}
      ${fluxTableHtml(ro)}
      ${motifsHtml(ro)}
      ${setDirectionHtml(ro)}
      ${artistsSectionHtml(isPast, ro)}
    `;
    bindDictHeader(slot);
    if (!isPast) bindBody(slot);
  }

  function dictHeaderHtml(isPast) {
    const refreshLabel = local.hasContent ? 'Refresh AI…' : 'Generate';
    const title = isPast
      ? 'Use Edit above to regenerate past visual references.'
      : local.hasContent
        ? 'Re-transform the dictionary + set art direction from the theme (overwrites AI fields).'
        : 'Generate the art-direction dictionary from the theme now.';
    return `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">Art-Direction Dictionary</h3>
        <button type="button" class="wiz-btn-secondary wiz-refresh-btn"
                data-role="vr-refresh-dict"
                title="${escAttr(title)}" ${isPast ? 'disabled' : ''}>${escHtml(refreshLabel)}</button>
      </div>
    `;
  }

  function entityTableHtml(cat, ro) {
    const rows = (local.entities[cat.key] || []).map((r, i) => `
      <tr data-cat="${escAttr(cat.key)}" data-i="${i}">
        <td class="wiz-vr-key-cell">
          <input type="text" class="wiz-vr-key" data-role="vr-key"
                 placeholder="entity name" value="${escAttr(r.key)}" ${ro}>
        </td>
        <td class="wiz-vr-desc-cell">
          <textarea class="wiz-vr-desc" data-role="vr-desc" rows="3"
                    placeholder="Full art-direction brief…" ${ro}>${escHtml(r.description)}</textarea>
        </td>
        <td class="wiz-vr-rm-cell">
          ${ro ? '' : `<button type="button" class="wiz-vr-rm" data-role="vr-rm" title="Remove row">×</button>`}
        </td>
      </tr>
    `).join('');
    return `
      <details class="wiz-vr-section" open>
        <summary class="wiz-vr-section-summary">
          ${escHtml(cat.label)}
          <span class="wiz-vr-count">${(local.entities[cat.key] || []).length}</span>
        </summary>
        <table class="wiz-vr-table">
          <thead><tr><th>Entry</th><th>Art direction</th><th></th></tr></thead>
          <tbody data-role="vr-tbody" data-cat="${escAttr(cat.key)}">${rows}</tbody>
        </table>
        ${ro ? '' : `<button type="button" class="wiz-btn-secondary wiz-vr-add"
                 data-role="vr-add" data-cat="${escAttr(cat.key)}">+ Add ${escHtml(cat.label.replace(/s$/, ''))}</button>`}
      </details>
    `;
  }

  function fluxTableHtml(ro) {
    const rows = local.flux.map((r, i) => `
      <tr data-i="${i}">
        <td><input type="text" class="wiz-vr-flux-term" data-role="vr-flux-term"
                   placeholder="invented word" value="${escAttr(r.term)}" ${ro}></td>
        <td class="wiz-vr-tr-arrow">→</td>
        <td><input type="text" class="wiz-vr-flux-repl" data-role="vr-flux-repl"
                   placeholder="renderable phrase" value="${escAttr(r.replacement)}" ${ro}></td>
        <td class="wiz-vr-rm-cell">${ro ? '' : `<button type="button" class="wiz-vr-rm" data-role="vr-flux-rm" title="Remove">×</button>`}</td>
      </tr>
    `).join('');
    return `
      <details class="wiz-vr-section">
        <summary class="wiz-vr-section-summary">
          Flux Term Replacements
          <span class="wiz-vr-count">${local.flux.length}</span>
        </summary>
        <p class="wiz-vr-section-note">Invented words swapped for renderable generic phrases before prompts are sent.</p>
        <table class="wiz-vr-table"><tbody data-role="vr-flux-tbody">${rows}</tbody></table>
        ${ro ? '' : `<button type="button" class="wiz-btn-secondary wiz-vr-add" data-role="vr-flux-add">+ Add replacement</button>`}
      </details>
    `;
  }

  function motifsHtml(ro) {
    const rows = local.motifs.map((m, i) => `
      <div class="wiz-vr-motif-row" data-i="${i}">
        <input type="text" class="wiz-vr-motif" data-role="vr-motif"
               placeholder="set-wide art note" value="${escAttr(m)}" ${ro}>
        ${ro ? '' : `<button type="button" class="wiz-vr-rm" data-role="vr-motif-rm" title="Remove">×</button>`}
      </div>
    `).join('');
    return `
      <details class="wiz-vr-section">
        <summary class="wiz-vr-section-summary">
          Visual Motifs
          <span class="wiz-vr-count">${local.motifs.length}</span>
        </summary>
        <p class="wiz-vr-section-note">Set-wide art-direction notes applied to every prompt.</p>
        <div data-role="vr-motifs">${rows}</div>
        ${ro ? '' : `<button type="button" class="wiz-btn-secondary wiz-vr-add" data-role="vr-motif-add">+ Add motif</button>`}
      </details>
    `;
  }

  function setDirectionHtml(ro) {
    return `
      <details class="wiz-vr-section" open>
        <summary class="wiz-vr-section-summary">Set-Wide Art Direction</summary>
        <p class="wiz-vr-section-note">The overall aesthetic, palette, lighting, and mood for the whole set.</p>
        <textarea class="wiz-vr-setdir" data-role="vr-setdir" rows="8"
                  placeholder="Set-wide art direction prose…" ${ro}>${escHtml(local.setArtDirection)}</textarea>
      </details>
    `;
  }

  function artistsSectionHtml(isPast, ro) {
    const rows = local.artists.map((a, i) => `
      <tr data-i="${i}">
        <td class="wiz-vr-key-cell">
          <input type="text" class="wiz-vr-artist-name" data-role="vr-artist-name"
                 placeholder="Artist name" value="${escAttr(a.name)}" ${ro}>
        </td>
        <td class="wiz-vr-desc-cell">
          <textarea class="wiz-vr-artist-style" data-role="vr-artist-style" rows="2"
                    placeholder="Style description…" ${ro}>${escHtml(a.style_prompt)}</textarea>
        </td>
        <td class="wiz-vr-rm-cell">${ro ? '' : `<button type="button" class="wiz-vr-rm" data-role="vr-artist-rm" title="Remove">×</button>`}</td>
      </tr>
    `).join('');
    const refreshTitle = isPast
      ? 'Use Edit above to regenerate past artists.'
      : 'Re-roll the whole artist directory via AI (overwrites all rows).';
    return `
      <details class="wiz-vr-section" open>
        <summary class="wiz-vr-section-summary">
          Artist Directory
          <span class="wiz-vr-count">${local.artists.length}</span>
        </summary>
        <div class="wiz-theme-section-header-row" style="margin:0.4rem 0">
          <p class="wiz-vr-section-note" style="margin:0">
            Made-up illustrators, each with a signature style. Target ~${local.artistTarget} for this set.
          </p>
          <button type="button" class="wiz-btn-secondary wiz-refresh-btn"
                  data-role="vr-refresh-artists"
                  title="${escAttr(refreshTitle)}" ${isPast ? 'disabled' : ''}>Re-roll all</button>
        </div>
        <table class="wiz-vr-table">
          <thead><tr><th>Artist</th><th>Style</th><th></th></tr></thead>
          <tbody data-role="vr-artist-tbody">${rows}</tbody>
        </table>
        ${ro ? '' : `<button type="button" class="wiz-btn-secondary wiz-vr-add" data-role="vr-artist-add">+ Add artist</button>`}
      </details>
    `;
  }

  // ----------------------------------------------------------------------
  // Event binding
  // ----------------------------------------------------------------------

  function bindDictHeader(slot) {
    const dictBtn = slot.querySelector('[data-role="vr-refresh-dict"]');
    if (dictBtn) dictBtn.onclick = () => onRefreshDict();
  }

  function bindBody(slot) {
    // Entity tables
    ENTITY_CATEGORIES.forEach(cat => {
      const tbody = slot.querySelector(`[data-role="vr-tbody"][data-cat="${cssEsc(cat.key)}"]`);
      if (tbody) {
        tbody.querySelectorAll('tr').forEach(tr => {
          const i = parseInt(tr.dataset.i, 10);
          const keyEl = tr.querySelector('[data-role="vr-key"]');
          const descEl = tr.querySelector('[data-role="vr-desc"]');
          const rmEl = tr.querySelector('[data-role="vr-rm"]');
          if (keyEl) keyEl.addEventListener('input', () => { local.entities[cat.key][i].key = keyEl.value; });
          if (descEl) descEl.addEventListener('input', () => { local.entities[cat.key][i].description = descEl.value; });
          if (rmEl) rmEl.onclick = () => { local.entities[cat.key].splice(i, 1); repaintBody(); };
        });
      }
      const addBtn = slot.querySelector(`[data-role="vr-add"][data-cat="${cssEsc(cat.key)}"]`);
      if (addBtn) addBtn.onclick = () => { local.entities[cat.key].push({ key: '', description: '' }); repaintBody(); };
    });

    // Flux replacements
    const fluxBody = slot.querySelector('[data-role="vr-flux-tbody"]');
    if (fluxBody) {
      fluxBody.querySelectorAll('tr').forEach(tr => {
        const i = parseInt(tr.dataset.i, 10);
        const t = tr.querySelector('[data-role="vr-flux-term"]');
        const r = tr.querySelector('[data-role="vr-flux-repl"]');
        const rm = tr.querySelector('[data-role="vr-flux-rm"]');
        if (t) t.addEventListener('input', () => { local.flux[i].term = t.value; });
        if (r) r.addEventListener('input', () => { local.flux[i].replacement = r.value; });
        if (rm) rm.onclick = () => { local.flux.splice(i, 1); repaintBody(); };
      });
    }
    bindClick(slot, 'vr-flux-add', () => { local.flux.push({ term: '', replacement: '' }); repaintBody(); });

    // Motifs
    slot.querySelectorAll('.wiz-vr-motif-row').forEach(row => {
      const i = parseInt(row.dataset.i, 10);
      const inp = row.querySelector('[data-role="vr-motif"]');
      const rm = row.querySelector('[data-role="vr-motif-rm"]');
      if (inp) inp.addEventListener('input', () => { local.motifs[i] = inp.value; });
      if (rm) rm.onclick = () => { local.motifs.splice(i, 1); repaintBody(); };
    });
    bindClick(slot, 'vr-motif-add', () => { local.motifs.push(''); repaintBody(); });

    // Set art direction
    const setdir = slot.querySelector('[data-role="vr-setdir"]');
    if (setdir) setdir.addEventListener('input', () => { local.setArtDirection = setdir.value; });

    // Artists
    const artBody = slot.querySelector('[data-role="vr-artist-tbody"]');
    if (artBody) {
      artBody.querySelectorAll('tr').forEach(tr => {
        const i = parseInt(tr.dataset.i, 10);
        const n = tr.querySelector('[data-role="vr-artist-name"]');
        const s = tr.querySelector('[data-role="vr-artist-style"]');
        const rm = tr.querySelector('[data-role="vr-artist-rm"]');
        if (n) n.addEventListener('input', () => { local.artists[i].name = n.value; });
        if (s) s.addEventListener('input', () => { local.artists[i].style_prompt = s.value; });
        if (rm) rm.onclick = () => { local.artists.splice(i, 1); repaintBody(); };
      });
    }
    bindClick(slot, 'vr-artist-add', () => { local.artists.push({ name: '', style_prompt: '' }); repaintBody(); });
    bindClick(slot, 'vr-refresh-artists', () => onRefreshArtists());
  }

  function bindClick(slot, role, fn) {
    const el = slot.querySelector(`[data-role="${role}"]`);
    if (el) el.onclick = fn;
  }

  // Re-render the body in place (a structural add/remove changed the row set).
  function repaintBody() {
    const root = bodyRoot();
    if (!root) return;
    paintBody(root, W.getState());
    setLocked(local.locked);
  }

  // ----------------------------------------------------------------------
  // AI refresh actions (§7, §13)
  // ----------------------------------------------------------------------

  async function onRefreshDict() {
    await W.runAiAction({
      isLocked: () => local.locked,
      setLocked,
      confirm: () => (local.hasContent
        ? 'Re-transform the dictionary + set art direction from the theme? AI fields are overwritten.'
        : ''),
      busyLabel: 'Generating art direction…',
      run: async ({ post }) => {
        repaintBody();
        const data = await post('/api/wizard/visual_refs/refresh', {}, 'Refresh failed');
        if (!data) return;
        applyState(data);
        const root = bodyRoot();
        paintSummary(root, W.getState());
        paintBody(root, W.getState());
        paintFooter(getFooter(root), W.getState());
        W.toast('Art direction generated.', 'success');
      },
    });
  }

  async function onRefreshArtists() {
    await W.runAiAction({
      isLocked: () => local.locked,
      setLocked,
      confirm: () => (local.artists.length
        ? 'Re-roll the whole artist directory? All current artists are replaced.'
        : ''),
      busyLabel: 'Generating artists…',
      run: async ({ post }) => {
        const data = await post('/api/wizard/visual_refs/refresh-artists', {}, 'Refresh failed');
        if (!data) return;
        applyState(data);
        const root = bodyRoot();
        paintSummary(root, W.getState());
        paintBody(root, W.getState());
        paintFooter(getFooter(root), W.getState());
        W.toast('Artist directory regenerated.', 'success');
      },
    });
  }

  // ----------------------------------------------------------------------
  // Footer: Save & Continue
  // ----------------------------------------------------------------------

  function paintFooter(footer, state) {
    if (!footer) return;
    const isLatest = !state || state.latestTabId === STAGE_ID;
    const isPaused = local.stageStatus === 'paused_for_review';
    const isCompleted = local.stageStatus === 'completed';
    const next = W.nextStageEntryAfter(STAGE_ID);
    const nextName = next ? next.name : 'the next stage';

    const canAdvanceTip = W.completedTipCanAdvance(state, STAGE_ID);
    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Editing past visual references is destructive — use the Edit button above.</span>`;
    } else if (isPaused || canAdvanceTip) {
      // isPaused is the normal "Stop after this step" pause. canAdvanceTip is
      // the saved/reopened dead-end: completed but the pipeline persisted
      // PAUSED with a later stage pending and no PAUSED_FOR_REVIEW pause — show
      // the Save & Continue button so the user can resume instead of being
      // stranded by the "Engine is on X" note (the engine is not on X here).
      html = `
        <button type="button" class="wiz-btn-primary" data-role="vr-save-advance" ${local.locked ? 'disabled' : ''}>
          Save &amp; Continue: ${escHtml(nextName)}
        </button>
        <span class="wiz-footer-note">Review the art direction above, then continue.</span>
      `;
    } else if (isCompleted) {
      html = `<span class="wiz-footer-note">Visual references saved. Engine is on ${escHtml(nextName)} — switch tabs to follow.</span>`;
    } else {
      html = `<span class="wiz-footer-note">This stage runs automatically. Tick "Stop after this step" above to review here before continuing.</span>`;
    }
    W.paintFooter(footer, html, { role: 'vr-save-advance', onClick: onSaveAndAdvance });
  }

  function onSaveAndAdvance() {
    return W.saveAndAdvance({
      stageId: STAGE_ID,
      isLocked: () => local.locked,
      setLocked,
      btnRole: 'vr-save-advance',
      validate: () => null,
      saveUrl: '/api/wizard/visual_refs/save',
      payload: () => savePayload(),
    });
  }

  function savePayload() {
    const entities = {};
    ENTITY_CATEGORIES.forEach(cat => { entities[cat.key] = local.entities[cat.key] || []; });
    const flux = {};
    local.flux.forEach(r => { if ((r.term || '').trim()) flux[r.term.trim()] = r.replacement; });
    return {
      entities,
      flux_term_replacements: flux,
      visual_motifs: local.motifs,
      set_art_direction: local.setArtDirection,
      artists: local.artists,
    };
  }

  // ----------------------------------------------------------------------
  // Form lock (§3)
  // ----------------------------------------------------------------------

  function aiBusy() {
    return local.locked || local.stageStatus === 'running';
  }

  function setLocked(locked) {
    local.locked = !!locked;
    W.setTabLocked(bodyRoot(), aiBusy(), {
      lockClass: 'wiz-vr-locked',
      selectors: [
        '.wiz-vr-body input',
        '.wiz-vr-body textarea',
        '.wiz-vr-body button',
      ],
      footerSelector: '[data-role="vr-save-advance"]',
    });
  }

  // ----------------------------------------------------------------------
  // Helpers
  // ----------------------------------------------------------------------

  const bodyRoot = () => W.tabRoot(STAGE_ID);
  const getFooter = (root) => W.tabFooter(root);
  const isPastTab = (state) => W.isPastTab(STAGE_ID, state);
  const escHtml = W.escHtml;
  const escAttr = W.escAttr;
  const cssEsc = W.cssEsc;

  // ----------------------------------------------------------------------
  // Scoped styles
  // ----------------------------------------------------------------------

  (function injectStyles() {
    if (document.getElementById('wiz-visual_refs-styles')) return;
    const style = document.createElement('style');
    style.id = 'wiz-visual_refs-styles';
    style.textContent = `
      .wiz-vr-blurb { font-size: 0.82rem; color: #888; margin: 0.3rem 0 0.6rem; }
      .wiz-vr-context { display: grid; grid-template-columns: auto 1fr; gap: 0.15rem 0.75rem;
        font-size: 0.82rem; margin: 0 0 0.6rem; }
      .wiz-vr-context dt { color: #888; }
      .wiz-vr-context dd { margin: 0; color: #ccc; }

      .wiz-vr-section { border: 1px solid #1f2540; border-radius: 6px; margin-bottom: 0.75rem;
        background: #0f1729; overflow: hidden; padding-bottom: 0.5rem; }
      .wiz-vr-section-summary { display: flex; align-items: center; gap: 0.5rem;
        padding: 0.6rem 0.85rem; cursor: pointer; user-select: none; font-size: 0.88rem;
        font-weight: 600; color: #ccc; list-style: none; background: #12193a; }
      .wiz-vr-section-summary::-webkit-details-marker { display: none; }
      .wiz-vr-count { margin-left: auto; font-size: 0.72rem; background: #4a9eff22; color: #4a9eff;
        border-radius: 3px; padding: 1px 6px; font-weight: 400; }
      .wiz-vr-section-note { font-size: 0.78rem; color: #888; margin: 0.5rem 0.85rem 0; }

      .wiz-vr-table { width: 100%; border-collapse: collapse; font-size: 0.82rem;
        margin: 0.4rem 0; }
      .wiz-vr-table th { text-align: left; color: #888; font-weight: 500; font-size: 0.74rem;
        padding: 0.2rem 0.85rem; }
      .wiz-vr-table td { padding: 0.25rem 0.85rem; vertical-align: top; }
      .wiz-vr-key-cell { width: 26%; }
      .wiz-vr-rm-cell { width: 1.8rem; text-align: center; }
      .wiz-vr-key, .wiz-vr-flux-term, .wiz-vr-flux-repl, .wiz-vr-artist-name, .wiz-vr-motif {
        width: 100%; background: #0b1120; border: 1px solid #1f2540; border-radius: 4px;
        color: #e0e0e0; padding: 0.3rem 0.45rem; font-size: 0.82rem; box-sizing: border-box; }
      .wiz-vr-desc, .wiz-vr-artist-style, .wiz-vr-setdir { width: 100%; background: #0b1120;
        border: 1px solid #1f2540; border-radius: 4px; color: #e0e0e0; padding: 0.3rem 0.45rem;
        font-size: 0.82rem; line-height: 1.4; resize: vertical; box-sizing: border-box; }
      .wiz-vr-setdir { margin: 0.4rem 0.85rem; width: calc(100% - 1.7rem); }
      .wiz-vr-tr-arrow { color: #555; width: 1.4rem; text-align: center; }

      .wiz-vr-rm { background: none; border: none; color: #a05; cursor: pointer; font-size: 1rem;
        line-height: 1; padding: 0.2rem 0.3rem; }
      .wiz-vr-rm:hover { color: #f47; }
      .wiz-vr-add { margin: 0.2rem 0.85rem 0; font-size: 0.78rem; }

      .wiz-vr-motif-row { display: flex; gap: 0.4rem; align-items: center; padding: 0.15rem 0.85rem; }

      .wiz-vr-locked .wiz-vr-body input,
      .wiz-vr-locked .wiz-vr-body textarea,
      .wiz-vr-locked .wiz-vr-body button { cursor: not-allowed; }
    `;
    document.head.appendChild(style);
  }());
})();
