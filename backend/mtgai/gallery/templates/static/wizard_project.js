/**
 * Wizard Project Settings tab — kickoff surface.
 *
 * Per design doc §6, this tab owns set parameters (name / target size /
 * mechanic count), the theme input source (PDF upload, paste, or load
 * existing theme.json), break points, model assignments, and the
 * "Start project" button. Edits are live-applied to settings.toml as
 * the user changes them; the only commit gesture is Start, which kicks
 * off the theme extractor and navigates to the Theme tab.
 *
 * Cascade-clear gate (§6.4 / §9): set_size + theme_input changes are
 * destructive once the pipeline has started. The full edit-flow modal
 * lands in the §9 card; for now those fields render disabled
 * post-Start and the wizard surfaces a hint pointing at the deferral.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});

  // Per-tab state — populated lazily on first activation.
  // The wizard shell never re-mounts a tab body in this card (the set
  // picker reloads the page) so a one-shot init flag is sufficient.
  // Subsequent activations re-render in place from `data` (see showTab
  // in wizard.js's rerender path).
  const local = {
    initialized: false,
    data: null,            // payload from GET /api/wizard/project
    pendingUploadId: null, // upload_id awaiting confirmation
  };

  W.registerTabRenderer('project', renderProjectTab);

  function renderProjectTab({ root, state }) {
    if (local.initialized) {
      // SSE-driven re-render — refresh the extraction-state strip if
      // anything changed underneath us. Don't replace the whole body
      // because in-progress form input would be lost.
      refreshExtractionStrip(root);
      return;
    }
    local.initialized = true;

    const content = root.querySelector('[data-role="content"]');
    const footer = root.querySelector('[data-role="footer"]');
    if (!content) return;

    content.innerHTML = `
      <div class="wiz-project-loading">Loading project settings…</div>
    `;
    if (footer) footer.innerHTML = '';

    fetchProject(state.activeSet)
      .then(data => {
        local.data = data;
        renderForm(content, footer, data, state);
      })
      .catch(err => {
        content.innerHTML = `<div class="wiz-project-error">Failed to load: ${escHtml(err.message)}</div>`;
      });
  }

  // ------------------------------------------------------------------
  // Fetch
  // ------------------------------------------------------------------

  async function fetchProject(setCode) {
    const resp = await fetch(`/api/wizard/project?set_code=${encodeURIComponent(setCode)}`);
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.error || `HTTP ${resp.status}`);
    }
    return await resp.json();
  }

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  function renderForm(content, footer, data, state) {
    content.innerHTML = `
      ${renderSetParamsSection(data)}
      ${renderThemeInputSection(data)}
      ${renderBreakPointsSection(data)}
      ${renderPresetRow(data)}
      ${renderModelAssignmentsSection(data)}
      ${renderExtractionStrip(data)}
    `;

    if (footer) {
      footer.innerHTML = `
        <button type="button" class="wiz-btn-primary" id="wiz-start-project">
          ${data.theme_input.kind === 'existing' ? 'Continue to Theme' : 'Start project'}
        </button>
      `;
      footer.querySelector('#wiz-start-project').disabled = !canStart(data);
    }

    bindSetParamsHandlers(state);
    bindThemeInputHandlers(state);
    bindBreakPointHandlers(state);
    bindPresetHandlers(state);
    bindModelHandlers(state);
    if (footer) {
      footer.querySelector('#wiz-start-project').addEventListener('click', () => onStart(state));
    }
  }

  function refreshExtractionStrip(root) {
    if (!local.data) return;
    const strip = root.querySelector('#wiz-extraction-strip');
    const newHtml = renderExtractionStrip(local.data);
    if (strip && newHtml.trim()) {
      const wrapper = document.createElement('div');
      wrapper.innerHTML = newHtml;
      strip.replaceWith(wrapper.firstElementChild);
    }
  }

  // ------------------------------------------------------------------
  // Set parameters
  // ------------------------------------------------------------------

  function renderSetParamsSection(data) {
    const sp = data.set_params;
    const sizeDisabled = data.pipeline_started ? 'disabled title="Read-only after pipeline start (cascade-clear edit flow lands in a follow-up card)"' : '';
    return `
      <section class="wiz-proj-section">
        <h3>Set parameters</h3>
        <div class="wiz-proj-grid">
          <label>Set code
            <input type="text" value="${escAttr(data.set_code)}" disabled>
          </label>
          <label>Set name
            <input type="text" id="wiz-pp-name" value="${escAttr(sp.set_name)}">
          </label>
          <label>Target size
            <input type="number" id="wiz-pp-size" value="${sp.set_size}" min="1" max="500" ${sizeDisabled}>
          </label>
          <label>Mechanic count
            <input type="number" id="wiz-pp-mech" value="${sp.mechanic_count}" min="0" max="20">
          </label>
        </div>
      </section>
    `;
  }

  function bindSetParamsHandlers(state) {
    const name = document.getElementById('wiz-pp-name');
    const size = document.getElementById('wiz-pp-size');
    const mech = document.getElementById('wiz-pp-mech');
    name.addEventListener('change', () => saveParams(state, { set_name: name.value }));
    if (!size.disabled) {
      size.addEventListener('change', () => saveParams(state, { set_size: parseInt(size.value, 10) || 0 }));
    }
    mech.addEventListener('change', () => saveParams(state, { mechanic_count: parseInt(mech.value, 10) || 0 }));
  }

  async function saveParams(state, patch) {
    try {
      const resp = await postJSON('/api/wizard/project/params', { set_code: state.activeSet, ...patch });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        W.toast(data.error || 'Save failed', 'error');
        return;
      }
      const data = await resp.json();
      local.data.set_params = data.set_params;
      W.toast('Saved', 'success');
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    }
  }

  // ------------------------------------------------------------------
  // Theme input
  // ------------------------------------------------------------------

  function renderThemeInputSection(data) {
    const ti = data.theme_input;
    const status = themeInputStatusText(ti);
    const inputDisabled = data.pipeline_started
      ? ' disabled title="Read-only after pipeline start (cascade-clear edit flow lands in a follow-up card)"'
      : '';
    return `
      <section class="wiz-proj-section">
        <h3>Theme input</h3>
        <div class="wiz-proj-theme-input">
          <div class="wiz-ti-status" id="wiz-ti-status">${escHtml(status)}</div>
          <div class="wiz-ti-controls">
            <label class="wiz-btn-secondary wiz-ti-upload-btn" ${inputDisabled.trim() ? 'aria-disabled="true"' : ''}>
              Upload PDF
              <input type="file" id="wiz-ti-file" accept=".pdf,.txt,.md"${inputDisabled} hidden>
            </label>
            <button type="button" class="wiz-btn-secondary" id="wiz-ti-paste-toggle"${inputDisabled}>
              Paste text
            </button>
            <button type="button" class="wiz-btn-secondary" id="wiz-ti-existing"${inputDisabled}>
              Use existing theme.json
            </button>
          </div>
          <textarea id="wiz-ti-paste" class="wiz-ti-paste-area" placeholder="Paste setting prose here…" hidden${inputDisabled}></textarea>
          <button type="button" class="wiz-btn-secondary" id="wiz-ti-paste-commit" hidden>Use this text</button>
        </div>
      </section>
    `;
  }

  function themeInputStatusText(ti) {
    switch (ti.kind) {
      case 'pdf': return `✓ Uploaded ${ti.filename || 'file'} (${formatChars(ti.char_count)})`;
      case 'text': return `✓ Pasted text (${formatChars(ti.char_count)})`;
      case 'existing': return `✓ Using existing theme.json`;
      default: return 'No input chosen yet — pick one to enable Start.';
    }
  }

  function formatChars(n) {
    if (typeof n !== 'number' || n <= 0) return '? chars';
    if (n >= 1000) return `${(n / 1000).toFixed(1)}k chars`;
    return `${n} chars`;
  }

  function bindThemeInputHandlers(state) {
    const fileInput = document.getElementById('wiz-ti-file');
    const pasteToggle = document.getElementById('wiz-ti-paste-toggle');
    const pasteArea = document.getElementById('wiz-ti-paste');
    const pasteCommit = document.getElementById('wiz-ti-paste-commit');
    const useExisting = document.getElementById('wiz-ti-existing');

    if (fileInput && !fileInput.disabled) {
      fileInput.addEventListener('change', () => onUpload(state, fileInput));
    }
    if (pasteToggle) {
      pasteToggle.addEventListener('click', () => {
        const showing = !pasteArea.hidden;
        pasteArea.hidden = showing;
        pasteCommit.hidden = showing;
        if (!showing) pasteArea.focus();
      });
    }
    if (pasteCommit) {
      pasteCommit.addEventListener('click', () => onPasteCommit(state, pasteArea.value));
    }
    if (useExisting && !useExisting.disabled) {
      useExisting.addEventListener('click', () => commitThemeInput(state, { kind: 'existing' }));
    }
  }

  async function onUpload(state, fileInput) {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    const status = document.getElementById('wiz-ti-status');
    status.textContent = `Uploading ${file.name}…`;

    try {
      const form = new FormData();
      form.append('file', file);
      const resp = await fetch('/api/pipeline/theme/upload', { method: 'POST', body: form });
      const data = await resp.json();
      if (!resp.ok) {
        W.toast('Upload failed: ' + (data.error || 'Unknown'), 'error');
        return;
      }
      await commitThemeInput(state, {
        kind: 'pdf',
        upload_id: data.upload_id,
        filename: data.filename,
        char_count: data.char_count,
      });
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    } finally {
      fileInput.value = '';
    }
  }

  async function onPasteCommit(state, text) {
    if (!text.trim()) {
      W.toast('Paste some text first', 'warn');
      return;
    }
    // Use the same upload endpoint — wrap the text as a synthetic .txt
    // file so the server's text-extraction path treats it as
    // already-decoded content. Avoids a second cache implementation.
    try {
      const form = new FormData();
      form.append('file', new Blob([text], { type: 'text/plain' }), 'pasted.txt');
      const resp = await fetch('/api/pipeline/theme/upload', { method: 'POST', body: form });
      const data = await resp.json();
      if (!resp.ok) {
        W.toast('Paste failed: ' + (data.error || 'Unknown'), 'error');
        return;
      }
      await commitThemeInput(state, {
        kind: 'text',
        upload_id: data.upload_id,
        filename: 'pasted.txt',
        char_count: data.char_count,
      });
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    }
  }

  async function commitThemeInput(state, payload) {
    try {
      const resp = await postJSON('/api/wizard/project/theme-input', {
        set_code: state.activeSet,
        ...payload,
      });
      const data = await resp.json();
      if (!resp.ok) {
        W.toast(data.error || 'Save failed', 'error');
        return;
      }
      local.data.theme_input = data.theme_input;
      // Re-render the theme-input row + start button so the new state shows.
      const root = document.querySelector('.wiz-tab-body[data-tab-id="project"]');
      if (root) {
        const status = root.querySelector('#wiz-ti-status');
        if (status) status.textContent = themeInputStatusText(data.theme_input);
        const startBtn = root.querySelector('#wiz-start-project');
        if (startBtn) {
          startBtn.disabled = !canStart(local.data);
          startBtn.textContent = data.theme_input.kind === 'existing'
            ? 'Continue to Theme' : 'Start project';
        }
        const pasteArea = root.querySelector('#wiz-ti-paste');
        const pasteCommit = root.querySelector('#wiz-ti-paste-commit');
        if (pasteArea) pasteArea.hidden = true;
        if (pasteCommit) pasteCommit.hidden = true;
      }
      W.toast('Theme input saved', 'success');
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    }
  }

  // ------------------------------------------------------------------
  // Break points
  // ------------------------------------------------------------------

  function renderBreakPointsSection(data) {
    const rows = data.break_points.map(bp => {
      const lockNote = bp.always_review ? ' <span class="wiz-bp-lock" title="Always pauses for review">🔒</span>' : '';
      const disabled = bp.always_review ? 'disabled' : '';
      return `
        <li class="wiz-bp-row">
          <label>
            <input type="checkbox" data-stage-id="${escAttr(bp.stage_id)}" ${bp.review ? 'checked' : ''} ${disabled}>
            Break after ${escHtml(bp.display_name)}${lockNote}
          </label>
        </li>
      `;
    }).join('');
    return `
      <section class="wiz-proj-section">
        <h3>Break points</h3>
        <p class="wiz-proj-desc">After these stages finish, the wizard pauses and waits for you to click "Next step". Card / Art / Final reviews are always-on.</p>
        <ul class="wiz-bp-list">${rows}</ul>
      </section>
    `;
  }

  function bindBreakPointHandlers(state) {
    document.querySelectorAll('.wiz-bp-row input[type="checkbox"]').forEach(cb => {
      if (cb.disabled) return;
      cb.addEventListener('change', async () => {
        try {
          const resp = await postJSON('/api/wizard/project/breaks', {
            set_code: state.activeSet,
            stage_id: cb.dataset.stageId,
            review: cb.checked,
          });
          if (!resp.ok) {
            const data = await resp.json().catch(() => ({}));
            W.toast(data.error || 'Save failed', 'error');
            cb.checked = !cb.checked; // revert
          }
        } catch (err) {
          W.toast('Network error: ' + err.message, 'error');
          cb.checked = !cb.checked;
        }
      });
    });
  }

  // ------------------------------------------------------------------
  // Presets
  // ------------------------------------------------------------------

  function renderPresetRow(data) {
    const builtins = data.builtin_presets.map(name =>
      `<button type="button" class="wiz-btn-secondary wiz-preset-btn" data-name="${escAttr(name)}">${escHtml(name)}</button>`
    ).join('');
    const profiles = data.saved_profiles.map(name =>
      `<button type="button" class="wiz-btn-secondary wiz-preset-btn" data-name="${escAttr(name)}">${escHtml(name)}</button>`
    ).join('');
    return `
      <section class="wiz-proj-section">
        <h3>Apply preset</h3>
        <div class="wiz-preset-row">
          <span class="wiz-preset-group-label">Built-in:</span> ${builtins}
        </div>
        ${profiles ? `<div class="wiz-preset-row"><span class="wiz-preset-group-label">Saved:</span> ${profiles}</div>` : ''}
        <div class="wiz-preset-actions">
          <button type="button" class="wiz-btn-secondary" id="wiz-save-as-profile">Save current as profile…</button>
        </div>
      </section>
    `;
  }

  function bindPresetHandlers(state) {
    document.querySelectorAll('.wiz-preset-btn').forEach(btn => {
      btn.addEventListener('click', () => onApplyPreset(state, btn.dataset.name));
    });
    const saveBtn = document.getElementById('wiz-save-as-profile');
    if (saveBtn) {
      saveBtn.addEventListener('click', () => onSaveProfile(state));
    }
  }

  async function onApplyPreset(state, name) {
    if (!confirm(`Apply preset "${name}"? This replaces the current model assignments and break points (set parameters and theme input are kept).`)) return;
    try {
      const resp = await postJSON('/api/wizard/project/preset/apply', {
        set_code: state.activeSet,
        name,
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        W.toast(data.error || 'Apply failed', 'error');
        return;
      }
      W.toast(`Preset "${name}" applied`, 'success');
      reloadProject(state);
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    }
  }

  async function onSaveProfile(state) {
    const name = (prompt('Profile name (letters, digits, "-", "_"):', '') || '').trim();
    if (!name) return;
    try {
      const resp = await postJSON('/api/wizard/project/preset/save', {
        set_code: state.activeSet,
        name,
      });
      const data = await resp.json();
      if (!resp.ok) {
        W.toast(data.error || 'Save failed', 'error');
        return;
      }
      W.toast(`Saved profile "${name}"`, 'success');
      // Add to local list so the new button shows without a refetch.
      if (!local.data.saved_profiles.includes(name)) {
        local.data.saved_profiles.push(name);
        local.data.saved_profiles.sort();
      }
      reloadProject(state);
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    }
  }

  async function reloadProject(state) {
    const root = document.querySelector('.wiz-tab-body[data-tab-id="project"]');
    if (!root) return;
    const data = await fetchProject(state.activeSet);
    local.data = data;
    const content = root.querySelector('[data-role="content"]');
    const footer = root.querySelector('[data-role="footer"]');
    renderForm(content, footer, data, state);
  }

  // ------------------------------------------------------------------
  // Model assignments
  // ------------------------------------------------------------------

  function renderModelAssignmentsSection(data) {
    const llmRows = LLM_STAGES.map(stage => {
      const assigned = data.llm_assignments[stage.id] || '';
      const opts = data.llm_models.map(m =>
        `<option value="${escAttr(m.key)}" ${m.key === assigned ? 'selected' : ''}>${escHtml(m.name)}</option>`
      ).join('');
      const model = data.llm_models.find(m => m.key === assigned);
      const supportsEffort = !!(model && model.supports_effort);
      const effort = data.effort_overrides[stage.id] || '';
      const effortCell = supportsEffort ? `
        <select data-effort-stage="${escAttr(stage.id)}" class="wiz-effort-select">
          ${EFFORT_OPTIONS.map(e => `<option value="${e.value}" ${e.value === effort ? 'selected' : ''}>${e.label}</option>`).join('')}
        </select>
      ` : '<span class="wiz-effort-na">—</span>';
      return `
        <tr>
          <td>${escHtml(stage.label)}</td>
          <td><select data-llm-stage="${escAttr(stage.id)}">${opts}</select></td>
          <td>${effortCell}</td>
        </tr>
      `;
    }).join('');

    const imageRows = IMAGE_STAGES.map(stage => {
      const assigned = data.image_assignments[stage.id] || '';
      const opts = data.image_models.map(m =>
        `<option value="${escAttr(m.key)}" ${m.key === assigned ? 'selected' : ''}>${escHtml(m.name)}${m.implemented ? '' : ' (not implemented)'}</option>`
      ).join('');
      return `
        <tr>
          <td>${escHtml(stage.label)}</td>
          <td colspan="2"><select data-image-stage="${escAttr(stage.id)}">${opts}</select></td>
        </tr>
      `;
    }).join('');

    return `
      <section class="wiz-proj-section">
        <h3>Model assignments</h3>
        <table class="wiz-models-table">
          <thead><tr><th>Stage</th><th>Model</th><th>Effort</th></tr></thead>
          <tbody>
            ${llmRows}
            ${imageRows}
          </tbody>
        </table>
      </section>
    `;
  }

  // Pipeline-order subset of stages that use LLMs / image models. Mirrors
  // LLM_STAGE_NAMES / IMAGE_STAGE_NAMES in model_settings.py — kept
  // client-side so we don't need a second fetch just to label rows.
  const LLM_STAGES = [
    { id: 'theme_extract', label: 'Theme extraction' },
    { id: 'mechanics', label: 'Mechanic generation' },
    { id: 'archetypes', label: 'Archetype generation' },
    { id: 'reprints', label: 'Reprint selection' },
    { id: 'lands', label: 'Land generation' },
    { id: 'card_gen', label: 'Card generation' },
    { id: 'balance', label: 'Balance analysis' },
    { id: 'skeleton_rev', label: 'Skeleton revision' },
    { id: 'ai_review', label: 'AI design review' },
    { id: 'art_prompts', label: 'Art prompt generation' },
    { id: 'art_select', label: 'Art selection' },
  ];
  const IMAGE_STAGES = [
    { id: 'char_portraits', label: 'Character portraits' },
    { id: 'art_gen', label: 'Art generation' },
  ];
  const EFFORT_OPTIONS = [
    { value: '', label: '—' },
    { value: 'low', label: 'Low' },
    { value: 'medium', label: 'Medium' },
    { value: 'high', label: 'High' },
    { value: 'max', label: 'Max' },
  ];

  function bindModelHandlers(state) {
    document.querySelectorAll('select[data-llm-stage]').forEach(sel => {
      sel.addEventListener('change', () => saveModel(state, 'llm', sel.dataset.llmStage, sel.value));
    });
    document.querySelectorAll('select[data-image-stage]').forEach(sel => {
      sel.addEventListener('change', () => saveModel(state, 'image', sel.dataset.imageStage, sel.value));
    });
    document.querySelectorAll('select[data-effort-stage]').forEach(sel => {
      sel.addEventListener('change', () => saveModel(state, 'effort', sel.dataset.effortStage, sel.value));
    });
  }

  async function saveModel(state, kind, stageId, value) {
    try {
      const resp = await postJSON('/api/wizard/project/models', {
        set_code: state.activeSet,
        kind,
        stage_id: stageId,
        value,
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        W.toast(data.error || 'Save failed', 'error');
        return;
      }
      // Local cache refresh so subsequent renders see the change.
      if (kind === 'llm') local.data.llm_assignments[stageId] = value;
      else if (kind === 'image') local.data.image_assignments[stageId] = value;
      else if (value) local.data.effort_overrides[stageId] = value;
      else delete local.data.effort_overrides[stageId];
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    }
  }

  // ------------------------------------------------------------------
  // Extraction strip + Start
  // ------------------------------------------------------------------

  function renderExtractionStrip(data) {
    if (!data.extraction_active) return '<div id="wiz-extraction-strip" hidden></div>';
    return `
      <div id="wiz-extraction-strip" class="wiz-extraction-strip">
        Theme extraction is in progress — see the global progress strip above.
        Switch to the Theme tab once it finishes.
      </div>
    `;
  }

  function canStart(data) {
    if (data.extraction_active) return false;
    return data.theme_input.kind !== 'none';
  }

  async function onStart(state) {
    const btn = document.getElementById('wiz-start-project');
    if (!btn) return;
    btn.disabled = true;
    const original = btn.textContent;
    btn.textContent = 'Starting…';
    try {
      const resp = await postJSON('/api/wizard/project/start', { set_code: state.activeSet });
      const data = await resp.json();
      if (!resp.ok) {
        W.toast(data.error || 'Start failed', 'error');
        btn.disabled = false;
        btn.textContent = original;
        return;
      }
      const target = data.navigate_to || '/pipeline/theme';
      // Navigate via full reload so the wizard reboots with the Theme
      // tab visible (the visible-tabs payload is computed server-side
      // at render time, and an extraction_active or freshly-written
      // theme.json is the trigger).
      window.location.assign(target);
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
      btn.disabled = false;
      btn.textContent = original;
    }
  }

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------

  async function postJSON(url, body) {
    return await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
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
