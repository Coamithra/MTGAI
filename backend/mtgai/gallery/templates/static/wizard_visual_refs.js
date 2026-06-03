/**
 * Wizard Visual References tab — displays the per-project visual dictionary
 * extracted from setting prose into ``<asset>/art-direction/visual-references.json``.
 *
 * Shape of that file (from visual_reference_extractor.py / CLAUDE.md):
 *   legendary_characters  { name_key: "appearance description…" }
 *   creature_types        { name_key: "…" }
 *   factions              { name_key: "…" }
 *   landmarks             { name_key: "…" }
 *   flux_term_replacements { term: "replacement" }
 *   visual_motifs         [ "short note", … ]
 *
 * Conventions:
 *   §1  footer: latest + paused_for_review → Save & Continue; else wiz-footer-note
 *   §3  form lock while AI gen in flight (read-only display, no interactive elements today)
 *   §6  past-tab view is read-only; edit cascade via wizard_stage.js
 *   §8  status pill driven by stage state (wizard_stage.js)
 *   §9  "Stop after this step" toggle handled by wizard_stage.js
 *   §13 Refresh AI button always rendered (initial generate + re-extract)
 *
 * Registers via ``W.registerStageRenderer('visual_refs', render)`` — the standard
 * wizard_stage.js shell owns the header; we paint content + footer.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'visual_refs';

  // Ordered display config for the four entity-category dicts.
  const ENTITY_CATEGORIES = [
    { key: 'legendary_characters', label: 'Legendary Characters', icon: '★' },
    { key: 'creature_types',       label: 'Creature Types',       icon: '☽' },
    { key: 'factions',             label: 'Factions',             icon: '⚑' },
    { key: 'landmarks',            label: 'Landmarks',            icon: '◆' },
  ];

  const local = {
    initialized:  false,
    refs:         null,   // the parsed visual-references.json, or null
    hasContent:   false,
    setName:      '',
    modelId:      '',
    stageStatus:  'pending',
    locked:       false,
    bootstrapping: false,
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ---------------------------------------------------------------------------
  // Top-level render — called by wizard_stage.js on mount and each SSE repaint
  // ---------------------------------------------------------------------------

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

    // Re-render path — keep footer reactive; don't repaint the body
    // (no user-editable fields here, but guard anyway for consistency).
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
  }

  function mountShellHtml() {
    return `
      <div class="wiz-vr-summary" data-role="vr-summary">
        <div class="wiz-stage-empty">Loading visual references…</div>
      </div>
      <div class="wiz-vr-body" data-role="vr-body"></div>
    `;
  }

  // ---------------------------------------------------------------------------
  // Bootstrap — fetch state from server (graceful degradation; tab renders
  // without a backend and just shows an empty-state placeholder).
  // ---------------------------------------------------------------------------

  async function bootstrap(root, state) {
    let data = null;
    try {
      // TODO: implement GET /api/wizard/visual_refs/state on the server
      // Expected response shape:
      //   { has_content, refs, set_name, model_id, stage_status, cost_usd, entity_count }
      const resp = await fetch('/api/wizard/visual_refs/state');
      if (resp.ok) {
        data = await resp.json().catch(() => null);
      } else if (resp.status === 404) {
        // Endpoint not yet implemented — silently degrade to empty state
        data = null;
      } else {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${resp.status}`);
      }
    } catch (err) {
      // Network error or endpoint not yet wired — show empty placeholder
      data = null;
    }

    if (data) {
      local.refs        = data.refs || null;
      local.hasContent  = !!data.has_content;
      local.setName     = data.set_name || '';
      local.modelId     = data.model_id || '';
      local.stageStatus = data.stage_status || local.stageStatus;
    }

    paintSummary(root, state);
    paintBody(root, state);
    paintFooter(getFooter(root), state);
  }

  // ---------------------------------------------------------------------------
  // Summary header — entity count, term replacements, motifs + Refresh AI
  // ---------------------------------------------------------------------------

  function paintSummary(root, state) {
    const slot = root.querySelector('[data-role="vr-summary"]');
    if (!slot) return;
    const isPast = W.isPastTab(STAGE_ID, state);

    // Compute counts from refs
    let entityCount = 0;
    let replacementCount = 0;
    let motifCount = 0;
    if (local.refs) {
      ENTITY_CATEGORIES.forEach(cat => {
        const dict = local.refs[cat.key];
        if (dict && typeof dict === 'object') entityCount += Object.keys(dict).length;
      });
      const fr = local.refs.flux_term_replacements;
      replacementCount = (fr && typeof fr === 'object') ? Object.keys(fr).length : 0;
      const vm = local.refs.visual_motifs;
      motifCount = Array.isArray(vm) ? vm.length : 0;
    }

    const generating = local.stageStatus === 'running' || local.locked;
    const refreshLabel = local.hasContent ? 'Refresh AI…' : 'Generate';
    const refreshTitle = isPast
      ? 'Use Edit above to regenerate past visual references.'
      : local.hasContent
        ? 'Re-extract visual references from setting prose (overwrites all existing).'
        : 'Extract visual references from the theme setting prose now.';

    // §13: Refresh button always rendered; disabled on a past tab.
    slot.innerHTML = `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">Visual Dictionary</h3>
        <button type="button" class="wiz-btn-secondary wiz-refresh-btn"
                data-role="vr-refresh"
                title="${escAttr(refreshTitle)}"
                ${(isPast || generating) ? 'disabled' : ''}>${escHtml(refreshLabel)}</button>
      </div>
      <p class="wiz-vr-blurb">
        Per-project appearance descriptions for every setting-specific entity —
        used by the art pipeline to keep character and creature visuals consistent.
      </p>
      ${local.hasContent ? `
      <dl class="wiz-stage-summary">
        <dt>Entities</dt><dd>${escHtml(String(entityCount))}</dd>
        <dt>Term replacements</dt><dd>${escHtml(String(replacementCount))}</dd>
        <dt>Visual motifs</dt><dd>${escHtml(String(motifCount))}</dd>
        ${local.modelId ? `<dt>Model</dt><dd>${escHtml(local.modelId)}</dd>` : ''}
        ${local.setName ? `<dt>Set</dt><dd>${escHtml(local.setName)}</dd>` : ''}
      </dl>` : (generating
        ? '<div class="wiz-stage-empty">Extracting visual references from setting prose…</div>'
        : `<div class="wiz-stage-empty">
             No visual references yet. Click "Generate" above, or advance from Finalization.
           </div>`
      )}
    `;
    const btn = slot.querySelector('[data-role="vr-refresh"]');
    if (btn) btn.onclick = () => onRefresh();
  }

  // ---------------------------------------------------------------------------
  // Body — categorized entity sections + term replacements + motifs
  // ---------------------------------------------------------------------------

  function paintBody(root, state) {
    const slot = root.querySelector('[data-role="vr-body"]');
    if (!slot) return;
    if (!local.hasContent || !local.refs) {
      slot.innerHTML = '';
      return;
    }

    const refs = local.refs;
    const parts = [];

    // Four entity-category <details> sections
    ENTITY_CATEGORIES.forEach(cat => {
      const dict = refs[cat.key];
      if (!dict || typeof dict !== 'object') return;
      const entries = Object.entries(dict);
      if (entries.length === 0) return;
      parts.push(entitySectionHtml(cat, entries));
    });

    // Flux term replacements table
    const fr = refs.flux_term_replacements;
    if (fr && typeof fr === 'object' && Object.keys(fr).length > 0) {
      parts.push(termReplacementsHtml(fr));
    }

    // Visual motifs chips
    const vm = refs.visual_motifs;
    if (Array.isArray(vm) && vm.length > 0) {
      parts.push(visualMotifsHtml(vm));
    }

    slot.innerHTML = parts.join('');
  }

  function entitySectionHtml(cat, entries) {
    const rows = entries.map(([key, desc]) => `
      <div class="wiz-vr-entry">
        <div class="wiz-vr-entry-key">${escHtml(key)}</div>
        <div class="wiz-vr-entry-desc">${escHtml(String(desc))}</div>
      </div>
    `).join('');
    return `
      <details class="wiz-vr-section" open>
        <summary class="wiz-vr-section-summary">
          <span class="wiz-vr-section-icon">${cat.icon}</span>
          ${escHtml(cat.label)}
          <span class="wiz-vr-count">${entries.length}</span>
        </summary>
        <div class="wiz-vr-entries">${rows}</div>
      </details>
    `;
  }

  function termReplacementsHtml(fr) {
    const rows = Object.entries(fr).map(([term, replacement]) => `
      <tr>
        <td class="wiz-vr-tr-term">${escHtml(term)}</td>
        <td class="wiz-vr-tr-arrow">→</td>
        <td class="wiz-vr-tr-replacement">${escHtml(String(replacement))}</td>
      </tr>
    `).join('');
    return `
      <details class="wiz-vr-section">
        <summary class="wiz-vr-section-summary">
          <span class="wiz-vr-section-icon">⇄</span>
          Flux Term Replacements
          <span class="wiz-vr-count">${Object.keys(fr).length}</span>
        </summary>
        <p class="wiz-vr-section-note">
          Setting-specific words Flux doesn't recognise — swapped for renderable generic phrases before prompts are sent.
        </p>
        <table class="wiz-vr-tr-table">${rows}</table>
      </details>
    `;
  }

  function visualMotifsHtml(vm) {
    const chips = vm.map(m => `<span class="wiz-vr-motif-chip">${escHtml(m)}</span>`).join('');
    return `
      <details class="wiz-vr-section">
        <summary class="wiz-vr-section-summary">
          <span class="wiz-vr-section-icon">◎</span>
          Visual Motifs
          <span class="wiz-vr-count">${vm.length}</span>
        </summary>
        <p class="wiz-vr-section-note">Set-wide art-direction notes applied to every prompt.</p>
        <div class="wiz-vr-motifs">${chips}</div>
      </details>
    `;
  }

  // ---------------------------------------------------------------------------
  // Refresh / initial generate action
  // ---------------------------------------------------------------------------

  async function onRefresh() {
    if (local.locked) return;
    if (local.hasContent) {
      if (!confirm('Re-extract all visual references from setting prose? This will overwrite the current dictionary.')) return;
    }
    setLocked(true);
    if (W.showBusy) W.showBusy('Extracting visual references…');
    const root = bodyRoot();

    try {
      // TODO: implement POST /api/wizard/visual_refs/generate on the server
      const resp = await W.postJSON('/api/wizard/visual_refs/generate', {});
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        W.reportError(resp, data, 'Extraction failed');
        return;
      }
      local.refs       = data.refs || null;
      local.hasContent = !!(data.refs && Object.keys(data.refs.legendary_characters || {}).length
        + Object.keys(data.refs.creature_types || {}).length
        + Object.keys(data.refs.factions || {}).length
        + Object.keys(data.refs.landmarks || {}).length > 0);
      local.modelId    = data.model_id || local.modelId;
      paintSummary(root, W.getState());
      paintBody(root, W.getState());
      paintFooter(getFooter(root), W.getState());
      W.toast('Visual references extracted.', 'success');
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    } finally {
      if (W.clearBusy) W.clearBusy();
      setLocked(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Footer — §1: latest + paused_for_review → "Next step: …" advance button
  // ---------------------------------------------------------------------------

  function paintFooter(footer, state) {
    if (!footer) return;
    const isLatest  = !state || state.latestTabId === STAGE_ID;
    const isPaused  = local.stageStatus === 'paused_for_review';
    const isCompleted = local.stageStatus === 'completed';
    const next = W.nextStageEntryAfter(STAGE_ID);
    const nextName = next ? next.name : 'the next stage';

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Editing past visual references is destructive — use the Edit button above.</span>`;
    } else if (isCompleted) {
      html = `<span class="wiz-footer-note">Visual references saved. Engine is on ${escHtml(nextName)} — switch tabs to follow.</span>`;
    } else if (!isPaused) {
      // AUTO stage — only pauses if "Stop after this step" is ticked
      html = `<span class="wiz-footer-note">This stage runs automatically. Tick "Stop after this step" above to review here before continuing.</span>`;
    } else {
      // Paused for review
      html = `
        <button type="button" class="wiz-btn-primary" data-role="vr-advance" ${!local.locked ? '' : 'disabled'}>
          Next step: ${escHtml(nextName)}
        </button>
        <span class="wiz-footer-note">Review the visual dictionary above, then continue.</span>
      `;
    }
    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
    }
    const btn = footer.querySelector('[data-role="vr-advance"]');
    if (btn) btn.onclick = onAdvance;
  }

  async function onAdvance() {
    if (local.locked) return;
    setLocked(true);
    const root = bodyRoot();
    const footer = getFooter(root);
    const btn = footer && footer.querySelector('[data-role="vr-advance"]');
    const original = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = 'Advancing…'; }
    try {
      const resp = await W.postJSON('/api/wizard/advance', {});
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        W.toast(data.error || `Advance failed (${resp.status})`, 'error');
        if (btn) { btn.disabled = false; btn.textContent = original; }
        return;
      }
      const next = W.nextStageEntryAfter(STAGE_ID);
      const nextHref = next ? `/pipeline/${next.id}` : '/pipeline';
      window.location.assign(data.navigate_to || nextHref);
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
      if (btn) { btn.disabled = false; btn.textContent = original; }
    } finally {
      setLocked(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Form lock (§3) — display-only tab; only the Refresh button + advance btn
  // ---------------------------------------------------------------------------

  function setLocked(locked) {
    local.locked = !!locked;
    const root = bodyRoot();
    if (!root) return;
    root.classList.toggle('wiz-vr-locked', !!locked);
    root.querySelectorAll('[data-role="vr-refresh"]').forEach(el => { el.disabled = !!locked; });
    const advBtn = root.querySelector('[data-role="vr-advance"]');
    if (advBtn) advBtn.disabled = !!locked;
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function bodyRoot() {
    return document.querySelector(`.wiz-tab-body[data-tab-id="${STAGE_ID}"]`);
  }

  function getFooter(root) {
    return root && root.querySelector('[data-role="footer"]');
  }

  const escHtml = W.escHtml;
  const escAttr = W.escAttr;

  // ---------------------------------------------------------------------------
  // Scoped styles — injected once (dark-theme palette from wizard.css)
  // ---------------------------------------------------------------------------

  (function injectStyles() {
    if (document.getElementById('wiz-visual_refs-styles')) return;
    const style = document.createElement('style');
    style.id = 'wiz-visual_refs-styles';
    style.textContent = `
      .wiz-vr-blurb {
        font-size: 0.82rem;
        color: #888;
        margin: 0.4rem 0 0.75rem;
      }

      /* ---- Section <details> ---- */
      .wiz-vr-section {
        border: 1px solid #1f2540;
        border-radius: 6px;
        margin-bottom: 0.75rem;
        background: #0f1729;
        overflow: hidden;
      }

      .wiz-vr-section-summary {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.6rem 0.85rem;
        cursor: pointer;
        user-select: none;
        font-size: 0.88rem;
        font-weight: 600;
        color: #ccc;
        list-style: none;
        background: #12193a;
      }

      .wiz-vr-section-summary::-webkit-details-marker { display: none; }

      .wiz-vr-section[open] .wiz-vr-section-summary {
        border-bottom: 1px solid #1f2540;
      }

      .wiz-vr-section-icon {
        font-size: 0.8rem;
        color: #4a9eff;
        flex: 0 0 auto;
      }

      .wiz-vr-count {
        margin-left: auto;
        font-size: 0.72rem;
        background: #4a9eff22;
        color: #4a9eff;
        border-radius: 3px;
        padding: 1px 6px;
        font-weight: 400;
      }

      .wiz-vr-section-note {
        font-size: 0.78rem;
        color: #888;
        margin: 0.5rem 0.85rem 0;
      }

      /* ---- Entity entries ---- */
      .wiz-vr-entries {
        padding: 0.5rem 0.85rem 0.75rem;
        display: flex;
        flex-direction: column;
        gap: 0.6rem;
      }

      .wiz-vr-entry {
        display: grid;
        grid-template-columns: minmax(120px, 18%) 1fr;
        gap: 0.35rem 1rem;
        align-items: baseline;
      }

      .wiz-vr-entry-key {
        font-size: 0.8rem;
        font-weight: 600;
        color: #a0c4ff;
        text-transform: capitalize;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .wiz-vr-entry-desc {
        font-size: 0.82rem;
        color: #ccc;
        line-height: 1.45;
      }

      /* ---- Flux term replacements table ---- */
      .wiz-vr-tr-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.82rem;
        margin: 0.5rem 0 0.75rem;
        padding: 0 0.85rem;
        display: block;
      }

      .wiz-vr-tr-table tr {
        border-bottom: 1px solid #1f2540;
      }

      .wiz-vr-tr-table tr:last-child { border-bottom: none; }

      .wiz-vr-tr-table td {
        padding: 0.3rem 0.85rem;
        vertical-align: top;
      }

      .wiz-vr-tr-term {
        color: #a0c4ff;
        font-weight: 600;
        white-space: nowrap;
        width: 22%;
      }

      .wiz-vr-tr-arrow {
        color: #555;
        width: 1.5rem;
        text-align: center;
      }

      .wiz-vr-tr-replacement { color: #ccc; }

      /* ---- Visual motifs chips ---- */
      .wiz-vr-motifs {
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
        padding: 0.6rem 0.85rem 0.85rem;
      }

      .wiz-vr-motif-chip {
        font-size: 0.78rem;
        background: #1a1a3e;
        border: 1px solid #2a2a5e;
        border-radius: 4px;
        padding: 0.25rem 0.6rem;
        color: #c8c8ff;
        line-height: 1.3;
      }

      /* ---- Locked state ---- */
      .wiz-vr-locked [data-role="vr-refresh"],
      .wiz-vr-locked [data-role="vr-advance"] {
        cursor: not-allowed;
      }
    `;
    document.head.appendChild(style);
  }());
})();
