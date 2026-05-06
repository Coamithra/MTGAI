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
 * destructive once the pipeline has started. Post-Start those fields
 * render disabled until the user clicks the section's Edit button,
 * which opens the §9 modal; on Continue the fields go editable + a
 * pencil indicator + banner show. Cancel reverts to the snapshot;
 * Accept commits via /api/wizard/edit/accept (cascade clear + kickoff).
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});

  // Per-tab state — populated lazily on first activation.
  // Subsequent activations re-render in place from `data` (see showTab
  // in wizard.js's rerender path).
  const local = {
    initialized: false,
    data: null,            // payload from GET /api/wizard/project
    pendingUploadId: null, // upload_id awaiting confirmation
    // True once the user has clicked Edit + confirmed the cascade modal.
    // While true, the cascade-clear fields (set_size, theme_input) are
    // editable and the section header shows Cancel + Accept. Bound to
    // the wizard shell's editDrafts via the 'project' key — Cancel
    // clears it, Accept clears + reloads.
    editingProject: false,
    // Snapshot of the original cascade-clear field values, captured at
    // Edit-click time. Cancel restores from this so partial edits don't
    // leak into the live-apply path.
    editSnapshot: null,
    // FileSystemFileHandle for the currently-open .mtg, if any. Populated
    // by Open / Save-as via showOpenFilePicker / showSaveFilePicker;
    // cleared by New. The handle persists across renders inside this IIFE
    // so subsequent Saves write through it without prompting again.
    fileHandle: null,
    fileName: null, // display name (basename of fileHandle, or null for untitled)
    // Untitled-project draft state — held only when there is no active
    // project on the server. Mirrors the shape /api/wizard/project would
    // return so the form renders the same way; first Save & Start
    // materialises it via /api/project/materialize.
    draft: null,
    // True when the in-memory form state has diverged from the .mtg on
    // disk (or the user just hit New / Open and hasn't typed yet). The
    // footer button label flips between "Save & Start project" (dirty)
    // and "Start project" (clean) on this. Untitled drafts always count
    // as dirty since there's no .mtg yet.
    dirty: false,
  };

  function markDirty() {
    if (local.dirty) return;
    local.dirty = true;
    refreshFooterLabel();
  }

  function markClean() {
    if (!local.dirty) return;
    local.dirty = false;
    refreshFooterLabel();
  }

  function refreshFooterLabel() {
    const btn = document.getElementById('wiz-start-project');
    if (!btn || !local.data) return;
    btn.textContent = footerButtonLabel(local.data);
    btn.disabled = !canStart(local.data);
  }

  function isUntitled() {
    return !!(local.data && local.data.untitled);
  }

  W.registerTabRenderer('project', renderProjectTab);

  // Cross-tab sync: when wizard_stage.js toggles a per-tab "Stop
  // after this step" checkbox, mirror the change into our local
  // payload + DOM so the Project Settings break-point row reflects
  // it on next paint (or immediately if the user is already here).
  W.onBreakPointChanged = function (stageId, review) {
    if (local.data && local.data.break_points) {
      const row = local.data.break_points.find(bp => bp.stage_id === stageId);
      if (row) row.review = review;
    }
    const cb = document.querySelector(
      `.wiz-bp-row input[type="checkbox"][data-stage-id="${cssEsc(stageId)}"]`,
    );
    if (cb) {
      cb.checked = review;
      const row = cb.closest('.wiz-bp-row');
      if (row) row.classList.toggle('wiz-bp-row--checked', review);
    }
  };

  function cssEsc(s) {
    if (window.CSS && CSS.escape) return CSS.escape(s);
    return String(s).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
  }

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

    if (!state.activeSet) {
      // No project file open — show only the New / Open toolbar and a
      // placeholder. Fields stay hidden until the user picks one or
      // creates a draft via New.
      local.data = null;
      renderForm(content, footer, null, state);
      return;
    }

    content.innerHTML = `
      <div class="wiz-project-loading">Loading project settings…</div>
    `;
    if (footer) footer.innerHTML = '';

    fetchProject()
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

  async function fetchProject() {
    // Server reads the active project from in-memory state; no query param.
    const resp = await fetch('/api/wizard/project');
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
    if (!data) {
      // No project loaded — toolbar only, with placeholder body.
      content.innerHTML = `
        ${renderProjectToolbar(null)}
        <div class="wiz-project-empty">
          <p>No project loaded.</p>
          <p>Click <strong>New</strong> to start a new project, or <strong>Open</strong> to load an existing <code>.mtg</code> file.</p>
        </div>
      `;
      if (footer) footer.innerHTML = '';
      bindProjectToolbarHandlers(state);
      return;
    }

    content.innerHTML = `
      ${renderProjectToolbar(data)}
      ${renderSetParamsSection(data)}
      ${renderAssetFolderSection(data)}
      ${renderThemeInputSection(data)}
      ${renderBreakPointsSection(data)}
      ${renderPresetRow(data)}
      ${renderModelAssignmentsSection(data)}
      ${renderExtractionStrip(data)}
    `;

    if (footer) {
      footer.innerHTML = `
        <button type="button" class="wiz-btn-primary" id="wiz-start-project">
          ${footerButtonLabel(data)}
        </button>
      `;
      footer.querySelector('#wiz-start-project').disabled = !canStart(data);
    }

    bindProjectToolbarHandlers(state);
    bindSetParamsHandlers(state);
    bindAssetFolderHandlers(state);
    bindThemeInputHandlers(state);
    bindBreakPointHandlers(state);
    bindPresetHandlers(state);
    bindModelHandlers(state);
    bindProjectEditHandlers(state);
    if (footer) {
      footer.querySelector('#wiz-start-project').addEventListener('click', () => onSaveAndStart(state));
    }
  }

  function footerButtonLabel(data) {
    const isUntitled = !!(local.data && local.data.untitled);
    const isDirty = local.dirty || isUntitled;
    if (data.theme_input.kind === 'existing' && !isUntitled && !isDirty) {
      return 'Continue to Theme';
    }
    return isDirty ? 'Save & Start project' : 'Start project';
  }

  // ------------------------------------------------------------------
  // Top toolbar: New / Open / Save (.mtg files via File System Access API)
  // ------------------------------------------------------------------

  function renderProjectToolbar(data) {
    const fileLabel = local.fileName
      ? escHtml(local.fileName)
      : '<em>Untitled project</em>';
    const stateLabel = data
      ? (local.fileHandle ? '' : ' <span class="wiz-proj-toolbar-dirty" title="Unsaved (no file yet)">●</span>')
      : '';
    return `
      <div class="wiz-proj-toolbar">
        <button type="button" class="wiz-btn-secondary" id="wiz-proj-new">New</button>
        <button type="button" class="wiz-btn-secondary" id="wiz-proj-open">Open…</button>
        <button type="button" class="wiz-btn-secondary" id="wiz-proj-save" ${data ? '' : 'disabled'}>Save…</button>
        ${data ? `<span class="wiz-proj-toolbar-active">${fileLabel}${stateLabel}</span>` : ''}
      </div>
    `;
  }

  function bindProjectToolbarHandlers(state) {
    const n = document.getElementById('wiz-proj-new');
    const o = document.getElementById('wiz-proj-open');
    const s = document.getElementById('wiz-proj-save');
    if (n) n.addEventListener('click', () => onNewClick(state));
    if (o) o.addEventListener('click', () => onOpenClick(state));
    if (s) s.addEventListener('click', () => onSaveClick(state));
  }

  // FS Access API gating — fall back gracefully when the browser doesn't
  // support it (Firefox, Safari). The Save button still functions via a
  // download fallback in those browsers.
  function fsAccessSupported() {
    return typeof window.showOpenFilePicker === 'function'
        && typeof window.showSaveFilePicker === 'function';
  }

  const MTG_PICKER_TYPES = [{
    description: 'MTGAI project',
    accept: { 'application/toml': ['.mtg'] },
  }];

  async function onNewClick(state) {
    if (local.data && hasUnsavedChanges()) {
      const ok = confirm('Discard the current project and start a new one? Unsaved changes will be lost.');
      if (!ok) return;
    }
    try {
      const resp = await postProjectAction('/api/project/new', {});
      if (resp === null) return; // user declined to cancel running action
      const data = await resp.json();
      if (!resp.ok) {
        W.toast(data.error || 'New failed', 'error');
        return;
      }
      local.fileHandle = null;
      local.fileName = null;
      local.draft = data.draft;
      local.data = data.draft;
      // Mark untitled so footer label / Save behaviour can branch.
      local.data.untitled = true;
      state.activeSet = '';
      rerenderProjectTab(state);
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    }
  }

  async function onOpenClick(state) {
    let text;
    let handle = null;
    let displayName = null;
    if (fsAccessSupported()) {
      try {
        const [picked] = await window.showOpenFilePicker({
          types: MTG_PICKER_TYPES,
          excludeAcceptAllOption: false,
          multiple: false,
        });
        handle = picked;
        const file = await handle.getFile();
        text = await file.text();
        displayName = file.name;
      } catch (err) {
        if (err && err.name === 'AbortError') return; // user cancelled
        W.toast('Open failed: ' + err.message, 'error');
        return;
      }
    } else {
      // Fallback: hidden <input type="file"> for browsers without FS Access.
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = '.mtg';
      const filePromise = new Promise((resolve, reject) => {
        input.addEventListener('change', () => {
          const f = input.files && input.files[0];
          if (!f) reject(new Error('No file picked'));
          else resolve(f);
        });
        input.addEventListener('cancel', () => reject({ name: 'AbortError' }));
      });
      input.click();
      let file;
      try {
        file = await filePromise;
      } catch (err) {
        if (err && err.name === 'AbortError') return;
        W.toast('Open failed: ' + err.message, 'error');
        return;
      }
      text = await file.text();
      displayName = file.name;
    }

    try {
      const resp = await postProjectAction('/api/project/open', { toml: text });
      if (resp === null) return; // user declined to cancel running action
      const data = await resp.json();
      if (!resp.ok) {
        W.toast(data.error || 'Open failed', 'error');
        return;
      }
      local.fileHandle = handle;
      local.fileName = displayName;
      local.draft = null;
      // Force a full reload so the wizard shell repaints with the new
      // active set's visible-tabs payload (Theme / stage tabs may now
      // exist if the project has been worked on).
      window.location.assign('/pipeline/project');
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    }
  }

  async function onSaveClick(state) {
    if (!local.data) return;
    try {
      const tomlText = await getCurrentMtgToml(state);
      if (tomlText == null) return;
      await writeMtgFile(tomlText);
    } catch (err) {
      if (err && err.name === 'AbortError') return;
      W.toast('Save failed: ' + err.message, 'error');
    }
  }

  // Returns the .mtg TOML to write. For an active project the server
  // owns the canonical bytes; for an untitled draft we materialise it
  // first (which also creates the per-set workspace + sets active).
  async function getCurrentMtgToml(state) {
    if (local.data && local.data.untitled) {
      const materialised = await materialiseDraft(state);
      if (!materialised) return null;
      return materialised.mtg_toml;
    }
    // Server reads the active project from in-memory state; no query param.
    const resp = await fetch('/api/project/serialize');
    const data = await resp.json();
    if (!resp.ok) {
      W.toast(data.error || 'Serialise failed', 'error');
      return null;
    }
    return data.mtg_toml;
  }

  // Validate the untitled draft + materialise it server-side so a real
  // settings.toml + active-set pointer exist. Returns the server's
  // response (with mtg_toml) on success, or null after surfacing an
  // error toast.
  async function materialiseDraft(state) {
    const draft = local.data;
    const code = (draft.set_code || '').trim().toUpperCase();
    if (!/^[A-Z0-9]{2,5}$/.test(code)) {
      W.toast('Set code is required (2–5 letters or digits)', 'error');
      return null;
    }
    const body = {
      set_code: code,
      set_params: draft.set_params,
      theme_input: draft.theme_input,
      asset_folder: draft.asset_folder || '',
      llm_assignments: draft.llm_assignments,
      image_assignments: draft.image_assignments,
      effort_overrides: draft.effort_overrides,
      // break_points payload from /new is the rendered list — convert to
      // the dict shape settings.toml stores.
      break_points: breakPointsListToDict(draft.break_points, draft.default_breaks || {}),
    };
    const resp = await postProjectAction('/api/project/materialize', body);
    if (resp === null) return null; // user declined to cancel running action
    const data = await resp.json();
    if (!resp.ok) {
      W.toast(data.error || 'Materialise failed', 'error');
      return null;
    }
    state.activeSet = data.set_code;
    delete local.data.untitled;
    return data;
  }

  function breakPointsListToDict(list, defaults) {
    const dict = {};
    list.forEach(bp => {
      const def = defaults[bp.stage_id];
      if (bp.review && def !== 'review') dict[bp.stage_id] = 'review';
      else if (!bp.review && def === 'review') dict[bp.stage_id] = 'auto';
    });
    return dict;
  }

  async function writeMtgFile(tomlText) {
    if (fsAccessSupported()) {
      let handle = local.fileHandle;
      if (!handle) {
        handle = await window.showSaveFilePicker({
          types: MTG_PICKER_TYPES,
          suggestedName: suggestedFilename(),
        });
        local.fileHandle = handle;
        local.fileName = handle.name || suggestedFilename();
      }
      const writable = await handle.createWritable();
      await writable.write(tomlText);
      await writable.close();
      W.toast(`Saved ${local.fileName}`, 'success');
    } else {
      // Download fallback — no persistent handle, so every Save prompts.
      const blob = new Blob([tomlText], { type: 'application/toml' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = suggestedFilename();
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      local.fileName = a.download;
      W.toast(`Downloaded ${local.fileName}`, 'success');
    }
    markClean();
    rerenderProjectTab(W.getState ? W.getState() : MTGAIWizard.getState());
  }

  function suggestedFilename() {
    const name = (local.data && local.data.set_params && local.data.set_params.set_name) || '';
    const code = (local.data && local.data.set_code) || 'project';
    const slug = (name || code).toString().trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    return `${slug || 'project'}.mtg`;
  }

  function hasUnsavedChanges() {
    // Untitled drafts always count as unsaved. For real projects we
    // can't easily tell without a diff, so be conservative: assume
    // unsaved if there's no fileHandle — that's the only case where
    // discarding actually loses data the user might still want.
    return !!(local.data && (local.data.untitled || !local.fileHandle));
  }

  function bindProjectEditHandlers(state) {
    const editBtn = document.getElementById('wiz-proj-edit');
    if (editBtn) {
      editBtn.addEventListener('click', () => onProjectEditClick(state));
    }
    const cancel = document.getElementById('wiz-proj-edit-cancel');
    if (cancel) {
      cancel.addEventListener('click', () => onProjectEditCancel(state));
    }
    const accept = document.getElementById('wiz-proj-edit-accept');
    if (accept) {
      accept.addEventListener('click', () => onProjectEditAccept(state));
    }
  }

  async function onProjectEditClick(state) {
    if (!W.editFlow) return;
    const ti = local.data.theme_input;
    const ok = await W.editFlow.confirmCascade({
      from_stage: 'project',
      // Theme input change wipes theme.json too — pre-flag so the
      // preview enumerates it in the modal.
      clear_theme_json: true,
      title: 'Edit set parameters & theme input',
      body:
        'Editing the target size or theme input will discard all generated content. '
        + 'Changing the theme input also clears theme.json so the next Start re-extracts.',
    });
    if (!ok) return;
    local.editingProject = true;
    // ThemeInputSource is currently flat (kind/filename/upload_id/
    // char_count/uploaded_at — all scalars) so a shallow clone matches
    // the deep-equal comparison in onProjectEditAccept. If a nested
    // field is added later, deep-clone here.
    local.editSnapshot = {
      set_size: local.data.set_params.set_size,
      theme_input: { ...ti },
    };
    if (W.editFlow) W.editFlow.setDraft('project', { dirty: false });
    rerenderProjectTab(state);
  }

  function onProjectEditCancel(state) {
    // Restore the cascade-clear fields to whatever was on screen before
    // Edit was clicked; live-apply changes (model/breaks) made during
    // the same session stay since they're not part of the cascade.
    if (local.editSnapshot) {
      local.data.set_params.set_size = local.editSnapshot.set_size;
      local.data.theme_input = local.editSnapshot.theme_input;
    }
    local.editingProject = false;
    local.editSnapshot = null;
    if (W.editFlow) W.editFlow.clearDraft('project');
    rerenderProjectTab(state);
  }

  async function onProjectEditAccept(state) {
    const sizeInput = document.getElementById('wiz-pp-size');
    const newSize = sizeInput ? parseInt(sizeInput.value, 10) : null;
    if (!newSize || newSize <= 0) {
      W.toast('Set size must be a positive integer', 'error');
      return;
    }
    const set_params_patch = newSize !== local.editSnapshot.set_size
      ? { set_size: newSize }
      : undefined;

    const tiNow = local.data.theme_input;
    const themeChanged = JSON.stringify(tiNow) !== JSON.stringify(local.editSnapshot.theme_input);
    const theme_input = themeChanged ? tiNow : undefined;
    // Wipe theme.json only if the theme-input source actually changed.
    const clear_theme_json = themeChanged;

    if (!set_params_patch && !theme_input) {
      // Edit mode entered but nothing changed — treat Accept as Cancel.
      onProjectEditCancel(state);
      W.toast('No changes to apply', 'warn');
      return;
    }

    const accept = document.getElementById('wiz-proj-edit-accept');
    if (accept) {
      accept.disabled = true;
      accept.textContent = 'Applying…';
    }
    try {
      const data = await W.editFlow.accept({
        from_stage: 'project',
        clear_theme_json,
        set_params_patch,
        theme_input,
      });
      if (W.editFlow) W.editFlow.clearDraft('project');
      if (data.warning) W.toast(data.warning, 'warn');
      window.location.assign(data.navigate_to || '/pipeline/project');
    } catch (err) {
      if (accept) {
        accept.disabled = false;
        accept.textContent = 'Accept';
      }
      if (err.status === 409) W.toast(err.message, 'warn');
      else W.toast('Accept failed: ' + err.message, 'error');
    }
  }

  function rerenderProjectTab(state) {
    const root = document.querySelector('.wiz-tab-body[data-tab-id="project"]');
    if (!root) return;
    const content = root.querySelector('[data-role="content"]');
    const footer = root.querySelector('[data-role="footer"]');
    renderForm(content, footer, local.data, state);
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
    // After pipeline start, set_size + theme_input are cascade-clear
    // fields (§6.4). They render disabled until the user clicks the
    // Edit button at the section level, which gates re-enabling them
    // behind the §9 modal.
    const cascadeLocked = data.pipeline_started && !local.editingProject;
    const sizeAttrs = cascadeLocked
      ? 'disabled title="Click Edit to change. Will discard everything from Skeleton onward."'
      : '';
    // Set code is editable only while the project is untitled — once
    // it's been materialised on disk, the code is the directory name
    // and renaming is out of scope for Phase 1.
    const codeEditable = isUntitled();
    const codeAttrs = codeEditable
      ? 'maxlength="5" pattern="[A-Z0-9]{2,5}" title="2–5 letters or digits"'
      : 'disabled';
    const editBtn = renderProjectEditControls(data);
    return `
      <section class="wiz-proj-section">
        <div class="wiz-proj-section-header">
          <h3>Set parameters</h3>
          ${editBtn}
        </div>
        ${local.editingProject ? '<div class="wiz-edit-banner">Editing — Accept will save and discard everything from Skeleton onward.</div>' : ''}
        <div class="wiz-proj-grid">
          <label>Set code
            <input type="text" id="wiz-pp-code" value="${escAttr(data.set_code)}" ${codeAttrs}>
          </label>
          <label>Set name
            <input type="text" id="wiz-pp-name" value="${escAttr(sp.set_name)}">
          </label>
          <label>Target size
            <input type="number" id="wiz-pp-size" value="${sp.set_size}" min="1" max="500" ${sizeAttrs}>
          </label>
          <label>Mechanic count
            <input type="number" id="wiz-pp-mech" value="${sp.mechanic_count}" min="0" max="20">
          </label>
        </div>
      </section>
    `;
  }

  function renderProjectEditControls(data) {
    if (!data.pipeline_started) return '';
    if (local.editingProject) {
      return `
        <div class="wiz-edit-actions">
          <button type="button" class="wiz-btn-secondary" id="wiz-proj-edit-cancel">Cancel</button>
          <button type="button" class="wiz-btn-primary" id="wiz-proj-edit-accept">Accept</button>
        </div>
      `;
    }
    if (W.editFlow && W.editFlow.isPipelineRunning()) return '';
    return `<button type="button" class="wiz-btn-secondary" id="wiz-proj-edit">Edit set parameters &amp; theme input</button>`;
  }

  function bindSetParamsHandlers(state) {
    const code = document.getElementById('wiz-pp-code');
    const name = document.getElementById('wiz-pp-name');
    const size = document.getElementById('wiz-pp-size');
    const mech = document.getElementById('wiz-pp-mech');
    if (code && !code.disabled) {
      code.addEventListener('input', () => {
        // Uppercase + strip non-alphanumeric in place so the value the
        // user sees matches what we'll send to the server.
        const cleaned = code.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 5);
        if (cleaned !== code.value) code.value = cleaned;
        local.data.set_code = cleaned;
        markDirty();
        refreshFooterLabel();
      });
    }
    name.addEventListener('change', () => saveParams(state, { set_name: name.value }));
    // size is a cascade-clear field — only live-apply when there's no
    // pipeline state on disk yet. Post-Start the field is enabled only
    // inside the edit flow, where Accept commits via the cascade
    // endpoint, not the live-apply one.
    if (!size.disabled && !local.editingProject) {
      size.addEventListener('change', () => saveParams(state, { set_size: parseInt(size.value, 10) || 0 }));
    }
    mech.addEventListener('change', () => saveParams(state, { mechanic_count: parseInt(mech.value, 10) || 0 }));
  }

  async function saveParams(state, patch) {
    if (isUntitled()) {
      // Untitled draft — mutate local.data only; first Save & Start
      // materialises the whole shape via /api/project/materialize.
      local.data.set_params = { ...local.data.set_params, ...patch };
      markDirty();
      return;
    }
    try {
      const resp = await postJSON('/api/wizard/project/params', patch);
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        W.toast(data.error || 'Save failed', 'error');
        return;
      }
      const data = await resp.json();
      local.data.set_params = data.set_params;
      markDirty();
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    }
  }

  // ------------------------------------------------------------------
  // Asset folder
  // ------------------------------------------------------------------

  function renderAssetFolderSection(data) {
    const folder = data.asset_folder || '';
    const supportsPicker = typeof window.showDirectoryPicker === 'function';
    const browseAttrs = supportsPicker ? '' : 'disabled title="Your browser does not support directory pickers — paste a path instead"';
    return `
      <section class="wiz-proj-section">
        <h3>Asset folder</h3>
        <p class="wiz-proj-desc">Where the pipeline writes generated artifacts (cards, theme, art, renders).</p>
        <div class="wiz-asset-folder-row">
          <input type="text" id="wiz-asset-folder" value="${escAttr(folder)}" placeholder="Choose a folder…">
          <button type="button" class="wiz-btn-secondary" id="wiz-asset-folder-browse" ${browseAttrs}>Browse…</button>
          <button type="button" class="wiz-btn-secondary" id="wiz-asset-folder-here" title="Use the folder containing the .mtg file" ${local.fileHandle ? '' : 'disabled'}>Use project file folder</button>
        </div>
      </section>
    `;
  }

  function bindAssetFolderHandlers(state) {
    const input = document.getElementById('wiz-asset-folder');
    const browse = document.getElementById('wiz-asset-folder-browse');
    const here = document.getElementById('wiz-asset-folder-here');
    if (input) {
      input.addEventListener('change', () => saveAssetFolder(state, input.value));
    }
    if (browse) {
      browse.addEventListener('click', async () => {
        if (typeof window.showDirectoryPicker !== 'function') return;
        try {
          const handle = await window.showDirectoryPicker({ mode: 'readwrite' });
          // We can't recover an absolute path from a directory handle —
          // the user has to type / paste it. Use the handle name as a
          // hint and prompt for the full path. (Phase 2 will resolve
          // this via storing the handle for actual writes.)
          const hint = handle.name || '';
          const path = prompt('Paste the full asset folder path:', hint);
          if (path == null) return;
          if (input) input.value = path.trim();
          await saveAssetFolder(state, path.trim());
        } catch (err) {
          if (err && err.name === 'AbortError') return;
          W.toast('Browse failed: ' + err.message, 'error');
        }
      });
    }
    if (here) {
      here.addEventListener('click', async () => {
        if (!local.fileHandle) return;
        // Same caveat as Browse — we know the file's name but not its
        // absolute directory, so prompt the user to confirm/paste.
        const hint = local.fileName ? local.fileName.replace(/\.mtg$/i, '') : '';
        const path = prompt(
          'Paste the path of the folder containing the .mtg file:',
          hint,
        );
        if (path == null) return;
        if (input) input.value = path.trim();
        await saveAssetFolder(state, path.trim());
      });
    }
  }

  async function saveAssetFolder(state, folder) {
    const trimmed = (folder || '').trim();
    if (isUntitled()) {
      local.data.asset_folder = trimmed;
      markDirty();
      return;
    }
    try {
      const resp = await postJSON('/api/wizard/project/asset-folder', {
        asset_folder: trimmed,
      });
      const data = await resp.json();
      if (!resp.ok) {
        W.toast(data.error || 'Save failed', 'error');
        return;
      }
      local.data.asset_folder = data.asset_folder;
      markDirty();
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
    // Same cascade-clear gate as set_size — only re-enabled while in
    // edit mode (toggled from the Set parameters section's Edit button).
    const cascadeLocked = data.pipeline_started && !local.editingProject;
    const inputDisabled = cascadeLocked
      ? ' disabled title="Click Edit (in Set parameters above) to change."'
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
    if (local.editingProject || isUntitled()) {
      // Edit-mode change OR untitled draft — don't live-apply.
      // Edit mode: server 409s post-Start; cascade Accept handler reads
      // the staged value at click time.
      // Untitled: there's no active set yet, so server-side persistence
      // is deferred to the first Save & Start.
      const ti = {
        kind: payload.kind,
        filename: payload.filename || null,
        upload_id: payload.upload_id || null,
        char_count: payload.char_count || null,
        uploaded_at: null,
      };
      local.data.theme_input = ti;
      markDirty();
      const root = document.querySelector('.wiz-tab-body[data-tab-id="project"]');
      if (root) {
        const status = root.querySelector('#wiz-ti-status');
        if (status) status.textContent = themeInputStatusText(ti);
        const pasteArea = root.querySelector('#wiz-ti-paste');
        const pasteCommit = root.querySelector('#wiz-ti-paste-commit');
        if (pasteArea) pasteArea.hidden = true;
        if (pasteCommit) pasteCommit.hidden = true;
      }
      refreshFooterLabel();
      if (local.editingProject) W.toast('Captured — Accept above to apply', 'success');
      return;
    }
    try {
      const resp = await postJSON('/api/wizard/project/theme-input', payload);
      const data = await resp.json();
      if (!resp.ok) {
        W.toast(data.error || 'Save failed', 'error');
        return;
      }
      local.data.theme_input = data.theme_input;
      markDirty();
      // Re-render the theme-input row + start button so the new state shows.
      const root = document.querySelector('.wiz-tab-body[data-tab-id="project"]');
      if (root) {
        const status = root.querySelector('#wiz-ti-status');
        if (status) status.textContent = themeInputStatusText(data.theme_input);
        const pasteArea = root.querySelector('#wiz-ti-paste');
        const pasteCommit = root.querySelector('#wiz-ti-paste-commit');
        if (pasteArea) pasteArea.hidden = true;
        if (pasteCommit) pasteCommit.hidden = true;
      }
      refreshFooterLabel();
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    }
  }

  // ------------------------------------------------------------------
  // Break points
  // ------------------------------------------------------------------

  function renderBreakPointsSection(data) {
    const rows = data.break_points.map(bp => `
      <li class="wiz-bp-row${bp.review ? ' wiz-bp-row--checked' : ''}">
        <label>
          <input type="checkbox" data-stage-id="${escAttr(bp.stage_id)}" ${bp.review ? 'checked' : ''}>
          Break after ${escHtml(bp.display_name)}
        </label>
      </li>
    `).join('');
    return `
      <section class="wiz-proj-section">
        <h3>Break points</h3>
        <p class="wiz-proj-desc">After these stages finish, the wizard pauses and waits for you to click "Next step".</p>
        <div class="wiz-bp-controls">
          <button type="button" class="wiz-btn-secondary" id="wiz-bp-all">Select all</button>
          <button type="button" class="wiz-btn-secondary" id="wiz-bp-none">Select none</button>
        </div>
        <ul class="wiz-bp-list">${rows}</ul>
      </section>
    `;
  }

  async function setBreakPoint(state, stageId, review) {
    if (isUntitled()) {
      if (local.data && local.data.break_points) {
        const row = local.data.break_points.find(bp => bp.stage_id === stageId);
        if (row) row.review = review;
      }
      markDirty();
      return true;
    }
    try {
      const resp = await postJSON('/api/wizard/project/breaks', {
        stage_id: stageId,
        review,
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        W.toast(data.error || 'Save failed', 'error');
        return false;
      }
      if (state.breakPoints) state.breakPoints[stageId] = review;
      if (local.data && local.data.break_points) {
        const row = local.data.break_points.find(bp => bp.stage_id === stageId);
        if (row) row.review = review;
      }
      markDirty();
      return true;
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
      return false;
    }
  }

  function bindBreakPointHandlers(state) {
    document.querySelectorAll('.wiz-bp-row input[type="checkbox"]').forEach(cb => {
      cb.addEventListener('change', async () => {
        const ok = await setBreakPoint(state, cb.dataset.stageId, cb.checked);
        if (!ok) {
          cb.checked = !cb.checked;
          return;
        }
        const row = cb.closest('.wiz-bp-row');
        if (row) row.classList.toggle('wiz-bp-row--checked', cb.checked);
      });
    });

    const setAll = async (review) => {
      const cbs = Array.from(document.querySelectorAll('.wiz-bp-row input[type="checkbox"]'));
      for (const cb of cbs) {
        if (cb.checked === review) continue;
        const ok = await setBreakPoint(state, cb.dataset.stageId, review);
        if (!ok) return;
        cb.checked = review;
        const row = cb.closest('.wiz-bp-row');
        if (row) row.classList.toggle('wiz-bp-row--checked', review);
      }
    };
    const allBtn = document.getElementById('wiz-bp-all');
    const noneBtn = document.getElementById('wiz-bp-none');
    if (allBtn) allBtn.addEventListener('click', () => setAll(true));
    if (noneBtn) noneBtn.addEventListener('click', () => setAll(false));
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
      </section>
    `;
  }

  function bindPresetHandlers(state) {
    document.querySelectorAll('.wiz-preset-btn').forEach(btn => {
      btn.addEventListener('click', () => onApplyPreset(state, btn.dataset.name));
    });
  }

  async function onApplyPreset(state, name) {
    if (!confirm(`Apply preset "${name}"? This replaces the current model assignments and break points (set parameters and theme input are kept).`)) return;
    if (isUntitled()) {
      // Apply via a synthetic local copy. Re-fetch the preset shape via
      // the materialise path's defaults isn't worth a server hop;
      // instead we ask the server to materialise just the preset into
      // local form fields. For now, refuse with a hint.
      W.toast('Save the project first, then apply preset.', 'warn');
      return;
    }
    try {
      const resp = await postJSON('/api/wizard/project/preset/apply', { name });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        W.toast(data.error || 'Apply failed', 'error');
        return;
      }
      W.toast(`Preset "${name}" applied`, 'success');
      markDirty();
      reloadProject(state);
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    }
  }

  async function reloadProject(state) {
    const root = document.querySelector('.wiz-tab-body[data-tab-id="project"]');
    if (!root) return;
    const data = await fetchProject();
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
    const applyLocal = () => {
      if (kind === 'llm') local.data.llm_assignments[stageId] = value;
      else if (kind === 'image') local.data.image_assignments[stageId] = value;
      else if (value) local.data.effort_overrides[stageId] = value;
      else delete local.data.effort_overrides[stageId];
    };
    if (isUntitled()) {
      applyLocal();
      markDirty();
      return;
    }
    try {
      const resp = await postJSON('/api/wizard/project/models', {
        kind,
        stage_id: stageId,
        value,
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        W.toast(data.error || 'Save failed', 'error');
        return;
      }
      applyLocal();
      markDirty();
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
    if (data.theme_input.kind === 'none') return false;
    if (isUntitled()) {
      // Need a valid set_code before we can materialise.
      const code = (data.set_code || '').trim().toUpperCase();
      if (!/^[A-Z0-9]{2,5}$/.test(code)) return false;
    }
    return true;
  }

  async function onSaveAndStart(state) {
    const btn = document.getElementById('wiz-start-project');
    if (!btn) return;
    const isUntitledNow = isUntitled();
    const needSave = isUntitledNow || local.dirty;
    btn.disabled = true;
    const original = btn.textContent;
    btn.textContent = needSave ? 'Saving…' : 'Starting…';

    if (needSave) {
      try {
        const tomlText = await getCurrentMtgToml(state);
        if (tomlText == null) {
          btn.disabled = false;
          btn.textContent = original;
          return;
        }
        await writeMtgFile(tomlText);
        markClean();
      } catch (err) {
        if (!err || err.name !== 'AbortError') {
          W.toast('Save failed: ' + err.message, 'error');
        }
        btn.disabled = false;
        btn.textContent = original;
        return;
      }
      btn.textContent = 'Starting…';
    }

    try {
      const resp = await postJSON('/api/wizard/project/start', {});
      const data = await resp.json();
      if (!resp.ok) {
        W.toast(data.error || 'Start failed', 'error');
        btn.disabled = false;
        btn.textContent = footerButtonLabel(local.data);
        return;
      }
      const target = data.navigate_to || '/pipeline/theme';
      window.location.assign(target);
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
      btn.disabled = false;
      btn.textContent = footerButtonLabel(local.data);
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

  // Wraps the project-switch endpoints with the 409 -> confirm -> retry
  // lifecycle. Returns the final fetch response, or null when the user
  // declines to interrupt an in-flight AI action.
  async function postProjectAction(url, body) {
    const payload = body || {};
    let resp = await postJSON(url, payload);
    if (resp.status === 409) {
      let busy = null;
      try { busy = await resp.json(); } catch (_) { /* not JSON */ }
      const action = (busy && busy.running_action) ? busy.running_action : 'An AI action';
      const ok = window.confirm(`${action} is in progress. Cancel it and continue?`);
      if (!ok) return null;
      resp = await postJSON(url, { ...payload, force: true });
    }
    return resp;
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
