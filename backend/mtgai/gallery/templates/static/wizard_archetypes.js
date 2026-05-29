/**
 * Wizard Archetypes tab — a 10-card grid (one per two-color pair) on the
 * standard stage shell.
 *
 * Registers via ``W.registerStageRenderer('archetypes', ...)`` so the
 * standard wizard_stage.js shell still owns the header (status pill,
 * break-point toggle, Edit-cascade button) and we just paint the body +
 * footer. Unlike Mechanics there is no "pick" step: every color pair is
 * kept, one archetype each — so the body is a fixed ten-card grid the user
 * can edit + refresh, with no checkboxes or selection block.
 *
 * Conventions:
 *   §1  one primary "Save & Continue" footer button (when paused for review)
 *   §3  form lock during AI gen
 *   §5  AI provenance badge + preserve-on-edit
 *   §6  past-tab edit cascade routes through wizard_stage.js / W.editFlow
 *   §8  status pill flows from stage state
 *   §9  Stop after this step — handled by wizard_stage.js
 *   §13 section-level Refresh AI button, always rendered on the latest tab
 *
 * The stage is AUTO by default (it does not pause), so the full review
 * experience is reached by ticking "Stop after this step" (the stage then
 * pauses for review and the Save & Continue footer appears). On a past tab
 * the grid is read-only and revision goes through the Edit cascade.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'archetypes';

  // Guild names + the two colors per pair, for display. The pair set + order
  // are the server's (``local.pairs``); these are just the human labels.
  const GUILD = {
    WU: 'Azorius', WB: 'Orzhov', WR: 'Boros', WG: 'Selesnya', UB: 'Dimir',
    UR: 'Izzet', UG: 'Simic', BR: 'Rakdos', BG: 'Golgari', RG: 'Gruul',
  };

  const local = {
    initialized: false,
    archetypes: [],   // [{color_pair, name, description, _ai_generated}], 10 in WUBRG order
    pairs: [],        // [{pair, label}] from the server — canonical order
    hasContent: false,
    setParams: { set_name: '', set_size: 0 },
    themeSummary: '',
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
        W.toast('Failed to load archetypes state: ' + err.message, 'error');
      });
      paintFooter(footer, state);
      return;
    }
    // Re-render path: keep the status pill / footer reactive without
    // repainting the body (the user may be mid-edit).
    const prevStatus = local.stageStatus;
    if (stage) local.stageStatus = stage.status;

    // The stage writes archetypes.json synchronously, so a bootstrap that
    // fired mid-run sees no content. When status flips out of running and
    // we still have nothing, re-pull so the grid fills once it lands.
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
        .catch(err => W.toast('Failed to refresh archetypes state: ' + err.message, 'error'))
        .finally(() => { local.bootstrapping = false; });
      return;
    }
    paintFooter(footer, state);
    setLocked(local.locked);
  }

  function mountShellHtml() {
    return `
      <div class="wiz-arch-summary" data-role="arch-summary">
        <div class="wiz-arch-loading">Loading archetypes state…</div>
      </div>
      <div class="wiz-arch-grid" data-role="arch-grid"></div>
    `;
  }

  // ----------------------------------------------------------------------
  // Bootstrap from server
  // ----------------------------------------------------------------------

  async function bootstrap(root, state) {
    const data = await W.fetchStageState(STAGE_ID);
    if (data) {
      local.archetypes = Array.isArray(data.archetypes) ? data.archetypes : [];
      local.pairs = Array.isArray(data.pairs) ? data.pairs : [];
      local.hasContent = !!data.has_content;
      local.setParams = data.set_params || local.setParams;
      local.themeSummary = data.theme_summary || '';
      local.modelId = data.model_id || '';
      local.stageStatus = data.stage_status || local.stageStatus;
    }
    paintSummary(root, state);
    paintGrid(root, state);
    paintFooter(getFooter(root), state);
  }

  // ----------------------------------------------------------------------
  // Summary block — context + the section-level Refresh / Generate button (§13)
  // ----------------------------------------------------------------------

  function paintSummary(root, state) {
    const slot = root.querySelector('[data-role="arch-summary"]');
    if (!slot) return;
    const sp = local.setParams;
    const isPast = isPastTab(state);
    const refreshLabel = local.hasContent ? 'Refresh AI…' : 'Generate';
    const refreshTitle = local.hasContent
      ? 'Regenerate the AI-written archetypes (pairs you edited survive).'
      : 'Generate all ten draft archetypes now.';
    // Section button is always rendered (§13) but disabled on a past tab —
    // revising past archetypes is destructive and goes through the Edit
    // cascade (header button), not an inline refresh that would silently
    // desync the skeleton/cards already built from them.
    const filled = local.archetypes.filter(a => a.name || a.description).length;
    slot.innerHTML = `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">Draft archetypes</h3>
        <button type="button" class="wiz-btn-secondary wiz-refresh-btn"
                data-role="arch-refresh-all"
                title="${escAttr(isPast ? 'Use Edit above to revise past archetypes.' : refreshTitle)}"
                ${isPast ? 'disabled' : ''}>${escHtml(refreshLabel)}</button>
      </div>
      <p class="wiz-arch-blurb">One archetype per two-color pair — the "what deck am I drafting?" answer that shapes the skeleton's signpost uncommons and every card's flavor.</p>
      <dl class="wiz-arch-context">
        <dt>Set</dt><dd>${escHtml(sp.set_name || '(unnamed)')}</dd>
        <dt>Size</dt><dd>${escHtml(String(sp.set_size || 0))} cards</dd>
        <dt>Pairs</dt><dd>${filled}/10 filled</dd>
        <dt>Model</dt><dd>${escHtml(local.modelId || '?')}</dd>
      </dl>
      ${local.themeSummary ? `<details class="wiz-arch-theme-preview"><summary>Theme excerpt</summary><div class="wiz-arch-theme-text">${escHtml(local.themeSummary)}</div></details>` : ''}
    `;
    const btn = slot.querySelector('[data-role="arch-refresh-all"]');
    if (btn) btn.onclick = () => onRefreshAll();
  }

  // ----------------------------------------------------------------------
  // Archetype grid
  // ----------------------------------------------------------------------

  function paintGrid(root, state) {
    const slot = root.querySelector('[data-role="arch-grid"]');
    if (!slot) return;
    if (!local.hasContent) {
      slot.innerHTML = W.emptyStatePanel({
        generating: aiBusy(),
        generatingMsg: 'Generating the ten draft archetypes…',
        emptyMsg: 'No archetypes yet. Click "Generate" above, or advance from Mechanics.',
        className: 'wiz-arch-empty',
      });
      return;
    }
    const isPast = isPastTab(state);
    // Render one card per server-canonical pair, matched to its archetype.
    const byPair = {};
    local.archetypes.forEach(a => { byPair[a.color_pair] = a; });
    const order = local.pairs.length
      ? local.pairs.map(p => p.pair)
      : local.archetypes.map(a => a.color_pair);
    slot.innerHTML = order
      .map(pair => archetypeCardHtml(byPair[pair] || emptyArch(pair), isPast))
      .join('');
    bindGrid(slot, isPast);
  }

  function emptyArch(pair) {
    return { color_pair: pair, name: '', description: '', _ai_generated: true };
  }

  function archetypeCardHtml(arch, isPast) {
    const pair = arch.color_pair;
    const guild = GUILD[pair] || '';
    const aiGenerated = arch._ai_generated !== false;
    const aiBadge = aiGenerated
      ? '<span class="wiz-ai-badge" data-role="ai-badge">AI</span>'
      : '';
    const ro = isPast ? 'disabled' : '';
    return `
      <article class="wiz-arch-card" data-pair="${escAttr(pair)}"${aiGenerated ? ' data-ai-generated="true"' : ''}>
        <header class="wiz-arch-card-header">
          <span class="wiz-arch-pips">${pipsHtml(pair)}</span>
          <span class="wiz-arch-pair">
            <span class="wiz-arch-pair-code">${escHtml(pair)}</span>
            ${guild ? `<span class="wiz-arch-guild">${escHtml(guild)}</span>` : ''}
          </span>
          ${aiBadge}
        </header>
        <div class="wiz-arch-field">
          <label class="wiz-arch-label">Name</label>
          <input type="text" class="wiz-arch-name" data-role="arch-name"
                 placeholder="Archetype name" value="${escAttr(arch.name || '')}" ${ro}>
        </div>
        <div class="wiz-arch-field">
          <label class="wiz-arch-label">Intent — win condition first</label>
          <textarea class="wiz-arch-desc" data-role="arch-desc" rows="5"
                    placeholder="How a deck drafting this pair closes the game, then how it's built to get there." ${ro}>${escHtml(arch.description || '')}</textarea>
        </div>
        ${isPast ? '' : `
        <footer class="wiz-arch-card-footer">
          <button type="button" class="wiz-btn-secondary" data-role="arch-refresh-card"
                  title="Regenerate this pair via AI (the others stay).">
            Refresh AI
          </button>
        </footer>`}
      </article>
    `;
  }

  function pipsHtml(pair) {
    return String(pair).split('').map(c => `<span class="wiz-arch-pip wiz-arch-pip-${escAttr(c)}" title="${escAttr(c)}"></span>`).join('');
  }

  // ----------------------------------------------------------------------
  // Grid event binding
  // ----------------------------------------------------------------------

  function bindGrid(slot, isPast) {
    if (isPast) return; // read-only on a past tab
    slot.querySelectorAll('.wiz-arch-card').forEach(card => bindCard(card));
  }

  function bindCard(card) {
    const pair = card.dataset.pair;
    const name = card.querySelector('[data-role="arch-name"]');
    const desc = card.querySelector('[data-role="arch-desc"]');

    if (name) name.addEventListener('input', () => {
      updateArch(pair, { name: name.value });
      markEdited(pair, card);
    });
    if (desc) desc.addEventListener('input', () => {
      updateArch(pair, { description: desc.value });
      markEdited(pair, card);
    });

    const refresh = card.querySelector('[data-role="arch-refresh-card"]');
    if (refresh) refresh.onclick = () => onRefreshCard(pair);
  }

  function updateArch(pair, patch) {
    const i = local.archetypes.findIndex(a => a.color_pair === pair);
    if (i >= 0) local.archetypes[i] = Object.assign({}, local.archetypes[i], patch);
  }

  // §5: clear the AI badge once the user touches a field, and drop the flag
  // on the working entry so a Refresh AI leaves this pair untouched.
  function markEdited(pair, card) {
    delete card.dataset.aiGenerated;
    const badge = card.querySelector('[data-role="ai-badge"]');
    if (badge) badge.remove();
    updateArch(pair, { _ai_generated: false });
  }

  // ----------------------------------------------------------------------
  // Refresh — single pair + all (or initial generate)
  // ----------------------------------------------------------------------

  async function onRefreshCard(pair) {
    await W.runAiAction({
      isLocked: () => local.locked,
      setLocked,
      confirm: `Regenerate the ${pair} archetype? Other pairs stay; this one will be overwritten.`,
      busyLabel: `Regenerating ${pair} archetype…`,
      run: async ({ post }) => {
        const data = await post('/api/wizard/archetypes/refresh-card', {
          color_pair: pair,
          archetypes: local.archetypes,
        }, 'Refresh failed');
        if (!data) return;
        applyArchetypes(data.archetypes);
        const root = bodyRoot();
        paintSummary(root, W.getState());
        paintGrid(root, W.getState());
        W.toast(`${pair} archetype regenerated.`, 'success');
      },
    });
  }

  async function onRefreshAll() {
    if (local.locked) return;
    const root = bodyRoot();
    if (!root) return;

    // The AI-flagged-pair gather + confirm run before locking, so they stay
    // out of runAiAction (the empty path skips both — nothing to overwrite).
    let pairs = [];
    if (local.hasContent) {
      pairs = Array.from(root.querySelectorAll('.wiz-arch-card[data-ai-generated="true"]'))
        .map(card => card.dataset.pair);
      if (!pairs.length) {
        W.toast('No AI-written archetypes to refresh — every pair has been edited.', 'warn');
        return;
      }
      if (!confirm(`Regenerate ${pairs.length} AI-written archetype${pairs.length === 1 ? '' : 's'}? Pairs you edited stay.`)) {
        return;
      }
    }
    await W.runAiAction({
      isLocked: () => local.locked,
      setLocked,
      busyLabel: local.hasContent ? 'Regenerating archetypes…' : 'Generating archetypes…',
      run: async ({ post }) => {
        // Repaint so the empty grid reflects the in-flight call.
        paintGrid(root, W.getState());
        // Empty arrays = initial full generation; non-empty pairs = partial refresh.
        const data = await post('/api/wizard/archetypes/refresh-all', {
          pairs: local.hasContent ? pairs : [],
          archetypes: local.hasContent ? local.archetypes : [],
        }, 'Refresh failed');
        if (!data) return;
        applyArchetypes(data.archetypes);
        paintSummary(root, W.getState());
        paintGrid(root, W.getState());
        paintFooter(getFooter(root), W.getState());
        W.toast(local.hasContent ? 'Archetypes regenerated.' : 'Archetypes generated.', 'success');
      },
    });
  }

  function applyArchetypes(list) {
    if (!Array.isArray(list)) return;
    local.archetypes = list;
    local.hasContent = list.some(a => a.name || a.description);
  }

  // ----------------------------------------------------------------------
  // Footer: Save & Continue (latest tab + paused_for_review)
  // ----------------------------------------------------------------------

  function paintFooter(footer, state) {
    if (!footer) return;
    const isLatest = !state || state.latestTabId === STAGE_ID;
    const isPaused = local.stageStatus === 'paused_for_review';
    const isCompleted = local.stageStatus === 'completed';
    const next = W.nextStageEntryAfter(STAGE_ID);
    const nextName = next ? next.name : 'the next stage';
    const filled = local.archetypes.filter(a => (a.name || '').trim() && (a.description || '').trim()).length;

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Editing past archetypes is destructive — use the Edit button above.</span>`;
    } else if (isCompleted) {
      html = `<span class="wiz-footer-note">Archetypes saved. Engine is on ${escHtml(nextName)} — switch tabs to follow.</span>`;
    } else if (!isPaused) {
      // AUTO stage: it only pauses if "Stop after this step" is ticked.
      html = `<span class="wiz-footer-note">This stage runs automatically. Tick "Stop after this step" above to review here before continuing.</span>`;
    } else {
      const ok = filled === 10;
      html = `
        <button type="button" class="wiz-btn-primary" data-role="arch-save-advance" ${ok && !local.locked ? '' : 'disabled'}>
          Save &amp; Continue: ${escHtml(nextName)}
        </button>
        <span class="wiz-footer-note">${filled}/10 archetypes filled.</span>
      `;
    }
    W.paintFooter(footer, html, { role: 'arch-save-advance', onClick: onSaveAndAdvance });
  }

  function onSaveAndAdvance() {
    return W.saveAndAdvance({
      stageId: STAGE_ID,
      isLocked: () => local.locked,
      setLocked,
      btnRole: 'arch-save-advance',
      validate: () => {
        const filled = local.archetypes
          .filter(a => (a.name || '').trim() && (a.description || '').trim()).length;
        return filled === 10 ? null : 'Every pair needs a name and an intent before continuing.';
      },
      saveUrl: '/api/wizard/archetypes/save',
      payload: () => ({ archetypes: local.archetypes }),
    });
  }

  // ----------------------------------------------------------------------
  // Form lock (§3)
  // ----------------------------------------------------------------------

  // AI is "active" on this tab when this tab kicked off an op (local.locked) or
  // the engine is running the archetypes stage (stageStatus). The composite is
  // the standardized lock truth source across stage tabs (§3).
  function aiBusy() {
    return local.locked || local.stageStatus === 'running';
  }

  function setLocked(locked) {
    local.locked = !!locked;
    W.setTabLocked(bodyRoot(), aiBusy(), {
      lockClass: 'wiz-arch-locked',
      selectors: [
        '.wiz-arch-card input',
        '.wiz-arch-card textarea',
        '[data-role="arch-refresh-card"]',
        '[data-role="arch-refresh-all"]',
      ],
      footerSelector: '[data-role="arch-save-advance"]',
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
})();
