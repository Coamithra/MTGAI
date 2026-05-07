/**
 * Wizard theme tab — content-only editor.
 *
 * Per design §8.3, the Theme tab keeps the constraint + card-request
 * + setting-prose surfaces. Upload, set_name, set_size, and
 * mechanic_count moved to the Project Settings tab — saving here no
 * longer round-trips those keys, so the next save naturally drops
 * them out of theme.json.
 *
 * Refresh-AI on individual sections is intentionally **not wired**
 * in this card — the AI lock + section refresh round-trip should
 * land alongside Project Settings since they share UX (model picker,
 * cost confirmation). Buttons render disabled with a tooltip.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  W.registerTabRenderer('content', renderThemeTab);

  // Module-scope flag: the theme tab body is mounted once per page
  // load. The wizard shell never re-mounts a tab body in this card,
  // so a one-shot guard is sufficient. If a future card adds in-place
  // re-bootstrapping it should track this on the tab body element
  // instead.
  const local = {
    initialized: false,
  };

  function renderThemeTab({ root, state }) {
    const footer = root.querySelector('[data-role="footer"]');

    if (local.initialized) {
      // SSE-driven re-render. Refresh the footer in place so the
      // Next-step button hides once the engine kicks off in the
      // background (auto-advance). The body has user-edited textareas
      // we don't want to clobber, so leave the body content alone.
      if (footer) {
        const desired = themeFooterHtml(state);
        if (footer.dataset.lastFooter !== desired) {
          footer.innerHTML = desired;
          footer.dataset.lastFooter = desired;
          bindThemeFooter(footer, state);
        }
      }
      refreshThemeHeader(root, state);
      refreshThemeBanner(root, state);
      // Bottom action row depends on isThemePast(state) which flips
      // when the engine kicks off — so it has to re-evaluate here too,
      // not just on first mount. Without this, Save Theme stays
      // visible after auto-advance until a tab navigation re-mounts.
      refreshThemeActions(root, state);
      return;
    }
    local.initialized = true;

    const content = root.querySelector('[data-role="content"]');
    if (!content) return;

    content.innerHTML = themeBodyHtml();
    if (footer) {
      const desired = themeFooterHtml(state);
      footer.innerHTML = desired;
      footer.dataset.lastFooter = desired;
      bindThemeFooter(footer, state);
    }

    bindThemeBody(state);
    refreshThemeHeader(root, state);
    refreshThemeBanner(root, state);
    refreshThemeActions(root, state);
  }

  // Theme tab is "past" once a pipeline-state.json exists — destructive
  // edits then need the §9 cascade gate.
  function isThemePast(state) {
    return !!state.pipeline;
  }

  function isEditingTheme() {
    return !!(W.editFlow && W.editFlow.getDraft('theme'));
  }

  function refreshThemeHeader(root, state) {
    const headerActions = root.querySelector('[data-role="header-actions"]');
    if (!headerActions) return;
    if (!W.editFlow || !isThemePast(state) || isEditingTheme()) {
      // Pre-pipeline-start, or already in edit mode — no Edit button.
      if (headerActions.querySelector('[data-role="theme-edit"]')) {
        headerActions.innerHTML = '';
      }
      return;
    }
    if (W.editFlow.isPipelineRunning()) {
      // Pipeline running: hide the button (Accept would 409 anyway).
      if (headerActions.querySelector('[data-role="theme-edit"]')) {
        headerActions.innerHTML = '';
      }
      return;
    }
    if (headerActions.querySelector('[data-role="theme-edit"]')) return;
    headerActions.innerHTML = `
      <button type="button" class="wiz-btn-secondary" data-role="theme-edit">Edit</button>
    `;
    headerActions.querySelector('[data-role="theme-edit"]').addEventListener(
      'click', () => onEditClick(state),
    );
  }

  function refreshThemeBanner(root, state) {
    const content = root.querySelector('[data-role="content"]');
    if (!content) return;
    const existing = content.querySelector('.wiz-edit-banner');
    if (isEditingTheme()) {
      if (!existing) {
        const banner = document.createElement('div');
        banner.className = 'wiz-edit-banner';
        banner.textContent =
          'Editing — Accept will save your changes and discard everything from Skeleton onward.';
        content.prepend(banner);
      }
    } else if (existing) {
      existing.remove();
    }
  }

  async function onEditClick(state) {
    const ok = await W.editFlow.confirmCascade({
      from_stage: 'theme',
      title: 'Edit Theme',
      body:
        'Editing the Theme tab will discard all generated content from Skeleton onward. '
        + 'Your theme.json edits commit on Accept.',
    });
    if (!ok) return;
    // Stash a draft so the pencil + banner appear. Accept reads the
    // current form state at click time, so no payload preview needed.
    W.editFlow.setDraft('theme', { dirty: false });
    const root = document.querySelector('.wiz-tab-body[data-tab-id="theme"]');
    if (root) {
      refreshThemeHeader(root, state);
      refreshThemeBanner(root, state);
      // Swap Save Theme for Cancel + Accept Edits in the body's bottom
      // action row. The footer (Next step) is hidden when editing.
      swapThemeActions(true, state);
      // Footer also goes empty during edit mode (§9.2) — re-render.
      const footer = root.querySelector('[data-role="footer"]');
      if (footer) {
        footer.innerHTML = '<span class="wiz-footer-note">Saving via Accept above.</span>';
        footer.dataset.lastFooter = '__editing__';
      }
    }
  }

  function swapThemeActions(editing, state) {
    const root = document.querySelector('.wiz-tab-body[data-tab-id="theme"]');
    if (root) refreshThemeActions(root, state, editing);
  }

  /**
   * Render the bottom action row by tab state:
   *   - editing      → Cancel + Accept Edits
   *   - past + idle  → hint "Click Edit above to change"
   *   - latest       → Save Theme (live-apply, pre-pipeline)
   *
   * Same DOM container holds all three modes; callers don't need to
   * track which mode is currently rendered. ``forceEditing`` lets the
   * onEditClick handler force the editing UI synchronously without
   * waiting for the next renderThemeTab tick.
   */
  function refreshThemeActions(root, state, forceEditing) {
    const actions = root.querySelector('.wiz-theme-actions');
    if (!actions) return;
    const editing = forceEditing !== undefined ? forceEditing : isEditingTheme();
    if (editing) {
      actions.innerHTML = `
        <button type="button" class="wiz-btn-secondary" id="wiz-theme-edit-cancel">Cancel</button>
        <button type="button" class="wiz-btn-primary" id="wiz-theme-edit-accept">Accept Edits</button>
      `;
      actions.querySelector('#wiz-theme-edit-cancel').addEventListener(
        'click', () => onEditCancel(state),
      );
      actions.querySelector('#wiz-theme-edit-accept').addEventListener(
        'click', () => onEditAccept(state),
      );
      return;
    }
    if (isThemePast(state)) {
      // Past Theme + not editing: hide Save Theme so the only commit
      // path is Edit → cascade (matches design §6.4 / §9 contract for
      // destructive theme.json changes).
      actions.innerHTML =
        '<span class="wiz-footer-note">Click Edit above to change theme.json.</span>';
      return;
    }
    actions.innerHTML = `
      <button type="button" class="wiz-btn-primary" id="wiz-save-theme">Save Theme</button>
    `;
    actions.querySelector('#wiz-save-theme').addEventListener(
      'click', () => saveTheme(state),
    );
  }

  function onEditCancel(state) {
    // Revert the form to the last-saved theme payload so the user's
    // local edits don't linger after Cancel. The wizard shell holds
    // the canonical state.theme; bindThemeBody re-populates from it.
    populateConstraints(state.theme && (state.theme.constraints || state.theme.special_constraints) || []);
    populateCardRequests(state.theme && state.theme.card_requests || []);
    document.getElementById('wiz-setting').value = readSettingProse(state.theme || {});
    setSettingMode('preview');
    W.editFlow.clearDraft('theme');
    const root = document.querySelector('.wiz-tab-body[data-tab-id="theme"]');
    if (root) {
      refreshThemeHeader(root, state);
      refreshThemeBanner(root, state);
      swapThemeActions(false, state);
      const footer = root.querySelector('[data-role="footer"]');
      if (footer) {
        footer.innerHTML = themeFooterHtml(state);
        footer.dataset.lastFooter = footer.innerHTML;
        bindThemeFooter(footer, state);
      }
    }
  }

  async function onEditAccept(state) {
    const setting = document.getElementById('wiz-setting').value.trim();
    if (!setting) {
      W.toast('Setting prose is empty. Add some text before accepting.', 'error');
      setSettingMode('edit');
      document.getElementById('wiz-setting').focus();
      return;
    }
    const constraints = [];
    document.querySelectorAll('#wiz-constraints-list .wiz-list-item').forEach(item => {
      const input = item.querySelector('input');
      if (!input) return;
      const val = input.value.trim();
      if (!val) return;
      constraints.push({
        text: val,
        source: item.dataset.aiGenerated === 'true' ? 'ai' : 'human',
      });
    });
    const cardRequests = [];
    document.querySelectorAll('#wiz-card-requests-list .wiz-list-item').forEach(item => {
      const ta = item.querySelector('textarea');
      if (!ta) return;
      const val = ta.value.trim();
      if (!val) return;
      cardRequests.push({
        text: val,
        source: item.dataset.aiGenerated === 'true' ? 'ai' : 'human',
      });
    });
    const theme = state.theme || {};
    const { set_size: _ignored_size, mechanic_count: _ignored_mech, ...rest } = theme;
    const payload = {
      ...rest,
      name: theme.name ?? '',
      code: state.activeSet,
      setting,
      constraints,
      card_requests: cardRequests,
    };

    const accept = document.getElementById('wiz-theme-edit-accept');
    if (accept) {
      accept.disabled = true;
      accept.textContent = 'Applying…';
    }
    try {
      const data = await W.editFlow.accept({
        from_stage: 'theme',
        theme_payload: payload,
      });
      W.editFlow.clearDraft('theme');
      if (data.warning) W.toast(data.warning, 'warn');
      window.location.assign(data.navigate_to || '/pipeline');
    } catch (err) {
      if (accept) {
        accept.disabled = false;
        accept.textContent = 'Accept Edits';
      }
      if (err.status === 409) W.toast(err.message, 'warn');
      else W.toast('Accept failed: ' + err.message, 'error');
    }
  }

  function themeBodyHtml() {
    return `
      <div class="wiz-theme-section">
        <div class="wiz-theme-section-header-row">
          <h3>Setting</h3>
          <button type="button" class="wiz-btn-secondary wiz-refresh-btn" id="wiz-refresh-theme" title="Re-run theme extraction from the source upload">Refresh AI…</button>
        </div>
        <p class="wiz-theme-section-desc">
          Prose describing your world. Feeds card generation, mechanics, art prompts.
          Edit / preview toggle below.
        </p>
        <div class="wiz-theme-toolbar">
          <button type="button" class="wiz-theme-mode-btn" data-mode="edit">Edit</button>
          <button type="button" class="wiz-theme-mode-btn active" data-mode="preview">Preview</button>
        </div>
        <textarea class="wiz-setting-textarea" id="wiz-setting" rows="16"
          style="display:none"
          placeholder="Setting prose lives here. Once Project Settings tab ships you'll be able to upload / paste from there."></textarea>
        <div class="wiz-setting-preview" id="wiz-setting-preview"></div>
      </div>

      <div class="wiz-theme-section">
        <div class="wiz-theme-section-header-row">
          <h3>Set Constraints</h3>
          <button type="button" class="wiz-btn-secondary wiz-refresh-btn" id="wiz-refresh-constraints" title="Re-extract constraints from the setting prose">Refresh AI</button>
        </div>
        <p class="wiz-theme-section-desc">
          Structural directives for the skeleton + card generation. Things like
          artifact density, color balance, card-type minimums.
        </p>
        <div class="wiz-list-items" id="wiz-constraints-list"></div>
        <button type="button" class="wiz-btn-add" id="wiz-add-constraint">+ Add constraint</button>
      </div>

      <div class="wiz-theme-section">
        <div class="wiz-theme-section-header-row">
          <h3>Card Requests</h3>
          <button type="button" class="wiz-btn-secondary wiz-refresh-btn" id="wiz-refresh-card-requests" title="Re-extract card requests from the setting prose">Refresh AI</button>
        </div>
        <p class="wiz-theme-section-desc">
          Cards you definitely want in the set — natural-language descriptions
          that get reserved slots in the skeleton.
        </p>
        <div class="wiz-list-items" id="wiz-card-requests-list"></div>
        <button type="button" class="wiz-btn-add" id="wiz-add-card-request">+ Add card request</button>
      </div>

      <div class="wiz-theme-actions">
        <button type="button" class="wiz-btn-primary" id="wiz-save-theme">Save Theme</button>
      </div>

      <dialog id="wiz-refresh-theme-dialog" class="wiz-modal">
        <h3 style="margin-top:0">Refresh theme</h3>
        <p>Re-runs the full theme extraction from your uploaded source. Replaces the setting prose. Pick which AI-generated subsections to also overwrite (unchecked → keep your edits).</p>
        <label style="display:block;margin:0.5rem 0">
          <input type="checkbox" id="wiz-refresh-theme-constraints"> Also refresh constraints
        </label>
        <label style="display:block;margin:0.5rem 0">
          <input type="checkbox" id="wiz-refresh-theme-cards"> Also refresh card requests
        </label>
        <div style="display:flex;gap:0.5rem;justify-content:flex-end;margin-top:1rem">
          <button type="button" class="wiz-btn-secondary" id="wiz-refresh-theme-cancel">Cancel</button>
          <button type="button" class="wiz-btn-primary" id="wiz-refresh-theme-confirm">Refresh</button>
        </div>
      </dialog>
    `;
  }

  function bindThemeBody(state) {
    const theme = state.theme || {};
    const setting = readSettingProse(theme);
    document.getElementById('wiz-setting').value = setting;

    document.querySelectorAll('.wiz-theme-mode-btn').forEach(btn => {
      btn.addEventListener('click', () => setSettingMode(btn.dataset.mode));
    });

    populateConstraints(theme.constraints || theme.special_constraints || []);
    populateCardRequests(theme.card_requests || []);

    document.getElementById('wiz-add-constraint').addEventListener('click', () => addConstraint('', false));
    document.getElementById('wiz-add-card-request').addEventListener('click', () => addCardRequest('', false));
    document.getElementById('wiz-save-theme').addEventListener('click', () => saveTheme(state));

    bindRefreshHandlers(state);

    setSettingMode('preview');
  }

  function readSettingProse(theme) {
    if (theme.setting) return theme.setting;
    const parts = [];
    if (theme.theme) parts.push(theme.theme);
    if (theme.flavor_description) parts.push(theme.flavor_description);
    return parts.join('\n\n');
  }

  function setSettingMode(mode) {
    const textarea = document.getElementById('wiz-setting');
    const preview = document.getElementById('wiz-setting-preview');
    if (!textarea || !preview) return;
    document.querySelectorAll('.wiz-theme-mode-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === mode);
    });
    if (mode === 'edit') {
      textarea.style.display = '';
      preview.style.display = 'none';
    } else {
      renderSettingPreview();
      textarea.style.display = 'none';
      preview.style.display = '';
    }
  }

  function renderSettingPreview() {
    const textarea = document.getElementById('wiz-setting');
    const preview = document.getElementById('wiz-setting-preview');
    if (!textarea || !preview) return;
    const text = textarea.value;
    if (!text.trim()) {
      preview.classList.add('empty');
      preview.textContent = 'No setting yet. Once the Project Settings tab ships, upload or paste prose from there.';
    } else {
      preview.classList.remove('empty');
      preview.innerHTML = renderMarkdown(text);
    }
  }

  // ------------------------------------------------------------------
  // Constraints + card requests
  // ------------------------------------------------------------------

  function populateConstraints(constraints) {
    const list = document.getElementById('wiz-constraints-list');
    list.innerHTML = '';
    if (!constraints.length) {
      addConstraint('', false);
      return;
    }
    for (const c of constraints) {
      const { text, source } = normalizeProvenance(c);
      addConstraint(text, source === 'ai');
    }
  }

  function populateCardRequests(requests) {
    const list = document.getElementById('wiz-card-requests-list');
    list.innerHTML = '';
    if (!requests.length) {
      addCardRequest('', false);
      return;
    }
    for (const r of requests) {
      const { text, source } = normalizeProvenance(r);
      addCardRequest(text, source === 'ai');
    }
  }

  function addConstraint(value, aiGenerated) {
    const list = document.getElementById('wiz-constraints-list');
    const item = document.createElement('div');
    item.className = 'wiz-list-item';
    if (aiGenerated) item.dataset.aiGenerated = 'true';
    const badge = aiGenerated ? '<span class="wiz-ai-badge">AI</span>' : '';
    item.innerHTML = `
      <input type="text" placeholder="e.g. Artifact subtheme — at least 6 artifact creatures"
             value="${escAttr(value || '')}">
      ${badge}
      <button type="button" class="wiz-btn-remove" title="Remove">&times;</button>
    `;
    list.appendChild(item);
    item.querySelector('input').addEventListener('input', () => clearAiBadge(item));
    item.querySelector('.wiz-btn-remove').addEventListener('click', () => item.remove());
    if (!value) item.querySelector('input').focus();
  }

  function addCardRequest(value, aiGenerated) {
    const list = document.getElementById('wiz-card-requests-list');
    const item = document.createElement('div');
    item.className = 'wiz-list-item';
    if (aiGenerated) item.dataset.aiGenerated = 'true';
    const badge = aiGenerated ? '<span class="wiz-ai-badge">AI</span>' : '';
    item.innerHTML = `
      <textarea rows="2"
        placeholder="e.g. Feretha's Throne — a legendary artifact that gains control of creatures">${escHtml(value || '')}</textarea>
      ${badge}
      <button type="button" class="wiz-btn-remove" title="Remove">&times;</button>
    `;
    list.appendChild(item);
    item.querySelector('textarea').addEventListener('input', () => clearAiBadge(item));
    item.querySelector('.wiz-btn-remove').addEventListener('click', () => item.remove());
    if (!value) item.querySelector('textarea').focus();
  }

  function clearAiBadge(item) {
    delete item.dataset.aiGenerated;
    const badge = item.querySelector('.wiz-ai-badge');
    if (badge) badge.remove();
  }

  // ------------------------------------------------------------------
  // Refresh AI — per-section + full theme
  // ------------------------------------------------------------------

  // Module-level: which subsections the active full-refresh asked the
  // server to overwrite. The done-event handler reads this to decide
  // whether to apply constraints / card_suggestions to the form.
  const refreshState = {
    fullActive: false,
    overwriteConstraints: false,
    overwriteCards: false,
  };

  function bindRefreshHandlers(state) {
    const constraintsBtn = document.getElementById('wiz-refresh-constraints');
    if (constraintsBtn) {
      constraintsBtn.addEventListener('click', () => onRefreshSection('constraints'));
    }
    const cardsBtn = document.getElementById('wiz-refresh-card-requests');
    if (cardsBtn) {
      cardsBtn.addEventListener('click', () => onRefreshSection('card_suggestions'));
    }
    const themeBtn = document.getElementById('wiz-refresh-theme');
    if (themeBtn) {
      themeBtn.addEventListener('click', () => openRefreshThemeDialog());
    }
    const dialog = document.getElementById('wiz-refresh-theme-dialog');
    if (dialog) {
      dialog.querySelector('#wiz-refresh-theme-cancel').addEventListener('click', () => {
        if (dialog.close) dialog.close(); else dialog.removeAttribute('open');
      });
      dialog.querySelector('#wiz-refresh-theme-confirm').addEventListener('click', () => {
        const overwriteC = dialog.querySelector('#wiz-refresh-theme-constraints').checked;
        const overwriteR = dialog.querySelector('#wiz-refresh-theme-cards').checked;
        if (dialog.close) dialog.close(); else dialog.removeAttribute('open');
        onRefreshTheme(state, overwriteC, overwriteR);
      });
    }

    // Subscribe to global section-result events from wizard.js's SSE.
    W.onSectionResult = handleSectionResult;
    W.onThemeStream = handleThemeStream;
  }

  // Streaming + terminal events for the full extraction. theme_chunk
  // is the per-token cadence (with tiny aggregated chunks); we append
  // to the textarea and re-render preview at a throttled rate so the
  // user sees the prose materialise.
  let _themePreviewTimer = null;
  function handleThemeStream(name, data) {
    if (!refreshState.fullActive) return;
    if (name === 'theme_theme_chunk') {
      const ta = document.getElementById('wiz-setting');
      if (!ta) return;
      ta.value += (data && data.text) || '';
      refreshState.streamSawChunk = true;
      if (_themePreviewTimer) return;
      _themePreviewTimer = setTimeout(() => {
        _themePreviewTimer = null;
        const preview = document.getElementById('wiz-setting-preview');
        if (preview) preview.innerHTML = renderMarkdown(ta.value);
      }, 200);
      return;
    }
    if (name === 'theme_constraints') {
      if (!refreshState.overwriteConstraints) return;
      const items = (data && data.constraints) || [];
      replaceListWithAi('wiz-constraints-list', items, addConstraint);
      return;
    }
    if (name === 'theme_card_suggestions') {
      if (!refreshState.overwriteCards) return;
      const raw = (data && data.suggestions) || [];
      const items = raw.map(s => (s && s.name && s.description) ? `${s.name}: ${s.description}` : (typeof s === 'string' ? s : ''));
      replaceListWithAi('wiz-card-requests-list', items, addCardRequest);
      return;
    }
    if (name === 'theme_done') {
      const ta = document.getElementById('wiz-setting');
      const preview = document.getElementById('wiz-setting-preview');
      if (ta && preview) preview.innerHTML = renderMarkdown(ta.value);
      refreshState.fullActive = false;
      W.toast('Theme refresh complete.', 'success');
      return;
    }
    if (name === 'theme_error' || name === 'theme_cancelled') {
      refreshState.fullActive = false;
      W.toast(`Refresh ${name === 'theme_error' ? 'failed' : 'cancelled'}: ${(data && data.message) || ''}`, 'error');
    }
  }

  function openRefreshThemeDialog() {
    const dialog = document.getElementById('wiz-refresh-theme-dialog');
    if (!dialog) return;
    dialog.querySelector('#wiz-refresh-theme-constraints').checked = false;
    dialog.querySelector('#wiz-refresh-theme-cards').checked = false;
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
  }

  async function onRefreshSection(kind) {
    const themeText = (document.getElementById('wiz-setting').value || '').trim();
    if (!themeText) {
      W.toast('Setting prose is empty — write something first.', 'error');
      return;
    }
    if (!confirm(`Re-extract ${kind === 'constraints' ? 'constraints' : 'card requests'} from the current setting prose? This replaces AI-generated entries (your edits stay).`)) return;
    refreshState.fullActive = false;

    // Clear AI items immediately so the user sees a blank slate while
    // the LLM generates the new batch.
    const listId = kind === 'constraints' ? 'wiz-constraints-list' : 'wiz-card-requests-list';
    const list = document.getElementById(listId);
    if (list) list.querySelectorAll('[data-ai-generated="true"]').forEach(el => el.remove());

    try {
      const resp = await fetch('/api/pipeline/theme/extract-section', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme_text: themeText, kind }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        if (resp.status === 409 && data.running_action) {
          W.toast(`${data.running_action} is in progress — try again when it finishes.`, 'error');
        } else {
          W.toast(data.error || `Refresh failed (${resp.status})`, 'error');
        }
        return;
      }
      // Body is SSE; we don't need to parse it here — the server also
      // publishes results to event_bus, which wizard.js's main SSE
      // hands off to handleSectionResult below. Just drain the stream
      // so the connection closes cleanly.
      try { resp.body.cancel && resp.body.cancel(); } catch (_) {}
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    }
  }

  async function onRefreshTheme(state, overwriteConstraints, overwriteCards) {
    if (!confirm('Re-run the full theme extraction from the source upload? Replaces the setting prose.')) return;
    refreshState.fullActive = true;
    refreshState.overwriteConstraints = overwriteConstraints;
    refreshState.overwriteCards = overwriteCards;
    refreshState.streamSawChunk = false;

    // Clear the setting textarea + preview so the user can watch the
    // new prose stream in. Also clear AI items in the subsections that
    // were marked for overwrite (their LLM payloads will repopulate).
    const ta = document.getElementById('wiz-setting');
    const preview = document.getElementById('wiz-setting-preview');
    if (ta) ta.value = '';
    if (preview) preview.innerHTML = '';
    if (overwriteConstraints) {
      const cl = document.getElementById('wiz-constraints-list');
      if (cl) cl.querySelectorAll('[data-ai-generated="true"]').forEach(el => el.remove());
    }
    if (overwriteCards) {
      const rl = document.getElementById('wiz-card-requests-list');
      if (rl) rl.querySelectorAll('[data-ai-generated="true"]').forEach(el => el.remove());
    }

    try {
      const resp = await fetch('/api/wizard/project/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force: true }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        if (resp.status === 409 && data.running_action) {
          W.toast(`${data.running_action} is in progress — try again when it finishes.`, 'error');
        } else {
          W.toast(data.error || `Refresh failed (${resp.status})`, 'error');
        }
        refreshState.fullActive = false;
        return;
      }
      W.toast('Theme refresh kicked off — watch the strip.', 'success');
      // Stay on the Theme tab; the global SSE strip + theme.json reload
      // on phase=done will repaint the body via the next renderThemeTab
      // tick fired from wizard.js's stage_update path.
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
      refreshState.fullActive = false;
    }
  }

  function handleSectionResult(name, data) {
    if (name === 'section_constraints') {
      const items = (data && data.constraints) || [];
      replaceListWithAi('wiz-constraints-list', items, addConstraint);
      W.toast('Constraints refreshed.', 'success');
      return;
    }
    if (name === 'section_card_suggestions') {
      const raw = (data && data.suggestions) || [];
      const items = raw.map(s => (s && s.name && s.description) ? `${s.name}: ${s.description}` : (typeof s === 'string' ? s : ''));
      replaceListWithAi('wiz-card-requests-list', items, addCardRequest);
      W.toast('Card requests refreshed.', 'success');
      return;
    }
    if (name === 'section_constraints_error') {
      W.toast('Constraints extraction failed: ' + (data.message || 'unknown'), 'error');
      return;
    }
    if (name === 'section_suggestions_error') {
      W.toast('Card-request extraction failed: ' + (data.message || 'unknown'), 'error');
      return;
    }
    // section_done — nothing to do; the strip hides on phase=done.
  }

  // Replace AI-tagged items only (preserve user edits) with a fresh
  // batch of AI items. Mirrors the legacy theme.js behaviour.
  function replaceListWithAi(listId, items, addFn) {
    const list = document.getElementById(listId);
    if (!list) return;
    const aiItems = list.querySelectorAll('[data-ai-generated="true"]');
    aiItems.forEach(el => el.remove());
    items.forEach(text => {
      if (text) addFn(text, true);
    });
  }

  function normalizeProvenance(item) {
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      const text = typeof item.text === 'string' ? item.text : '';
      const source = item.source === 'ai' ? 'ai' : 'human';
      return { text, source };
    }
    return { text: typeof item === 'string' ? item : '', source: 'human' };
  }

  // ------------------------------------------------------------------
  // Save
  // ------------------------------------------------------------------

  async function saveTheme(state) {
    const theme = state.theme || {};
    const setting = document.getElementById('wiz-setting').value.trim();

    if (!setting) {
      W.toast('Setting prose is empty. Add some text before saving.', 'error');
      setSettingMode('edit');
      document.getElementById('wiz-setting').focus();
      return;
    }

    const constraints = [];
    document.querySelectorAll('#wiz-constraints-list .wiz-list-item').forEach(item => {
      const input = item.querySelector('input');
      if (!input) return;
      const val = input.value.trim();
      if (!val) return;
      constraints.push({
        text: val,
        source: item.dataset.aiGenerated === 'true' ? 'ai' : 'human',
      });
    });

    const cardRequests = [];
    document.querySelectorAll('#wiz-card-requests-list .wiz-list-item').forEach(item => {
      const ta = item.querySelector('textarea');
      if (!ta) return;
      const val = ta.value.trim();
      if (!val) return;
      cardRequests.push({
        text: val,
        source: item.dataset.aiGenerated === 'true' ? 'ai' : 'human',
      });
    });

    // Carry forward unrelated keys the AI extractor may have written
    // (e.g. `special_constraints`, `theme`, `flavor_description` —
    // legacy companion fields) but drop the set-shape numerics. Those
    // moved to Project Settings (settings.toml.set_params) so writing
    // them here would compete with the new source of truth. `code` and
    // `name` are still written so the set picker can render the title
    // off theme.json without a settings.toml round-trip.
    const { set_size: _ignored_size, mechanic_count: _ignored_mech, ...rest } = theme;
    const payload = {
      ...rest,
      name: theme.name ?? '',
      code: state.activeSet,
      setting,
      constraints,
      card_requests: cardRequests,
    };

    const btn = document.getElementById('wiz-save-theme');
    btn.disabled = true;
    btn.textContent = 'Saving…';

    try {
      const resp = await fetch('/api/pipeline/theme/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const result = await resp.json();
      if (result.success) {
        state.theme = payload;
        W.toast(`Theme saved for ${payload.code}`, 'success');
      } else {
        W.toast('Error: ' + (result.error || 'Unknown'), 'error');
      }
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Save Theme';
    }
  }

  // ------------------------------------------------------------------
  // Markdown — zero-dep subset (mirrors theme.js's renderer)
  // ------------------------------------------------------------------

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

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------

  function escHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
  }

  function escAttr(text) {
    return escHtml(text).replace(/"/g, '&quot;');
  }

  // ------------------------------------------------------------------
  // Footer — Next-step (Theme → Skeleton)
  // ------------------------------------------------------------------

  function themeFooterHtml(state) {
    // Three cases:
    // 1. Pipeline already started (state.pipeline non-null) → engine
    //    has been kicked off; auto-advance handles the rest. Hide the
    //    button. Theme is "past" in the wizard timeline.
    // 2. No theme.json yet (state.theme null) → user is here ahead of
    //    extraction completing. Don't surface the button — the worker
    //    will auto-advance when it finishes (the kickoff is server-side).
    // 3. theme.json exists, no pipeline state → manual Next-step.
    //    Common path: an existing set whose theme.json was written in
    //    a prior session before the auto-advance hook landed, or one
    //    where the user navigated back to Theme to edit constraints
    //    before kicking off the pipeline.
    if (state.pipeline) {
      return '<span class="wiz-footer-note"></span>';
    }
    if (!state.theme) {
      return '<span class="wiz-footer-note"></span>';
    }
    return `
      <button type="button" class="wiz-btn-primary" data-role="theme-next">
        Next step: Skeleton Generation
      </button>
    `;
  }

  function bindThemeFooter(footer, state) {
    const btn = footer.querySelector('button[data-role="theme-next"]');
    if (!btn) return;
    // Single-slot via .onclick to avoid stacked listeners if the same
    // DOM node ever survives a re-bind (the dataset.lastFooter guard
    // makes this rare today, but innerHTML rewrites + onclick is the
    // belt-and-braces version).
    btn.onclick = async () => {
      const original = btn.textContent;
      btn.disabled = true;
      btn.textContent = 'Starting…';
      try {
        const resp = await fetch('/api/wizard/advance', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        });
        const data = await resp.json();
        if (!resp.ok) {
          W.toast(data.error || 'Start failed', 'error');
          btn.disabled = false;
          btn.textContent = original;
          return;
        }
        // Hard navigate to the first pending stage so the wizard
        // re-mounts with the engine already running and the new tab
        // visible. Soft-navigation would work too but the bootstrap
        // payload (visible_tabs / pipeline_state) is server-rendered,
        // so a reload is the simplest way to get them in sync.
        const target = data.navigate_to || '/pipeline/skeleton';
        window.location.assign(target);
      } catch (err) {
        W.toast('Network error: ' + err.message, 'error');
        btn.disabled = false;
        btn.textContent = original;
      }
    };
  }
})();
