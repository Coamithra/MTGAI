/**
 * Settings page — cross-set defaults: default preset, saved profiles
 * (view / rename / delete), and a read-only model registry view.
 *
 * Per-stage assignments moved to the per-set Project Settings tab.
 *
 * Globals from the template (declared in settings.html):
 *   MODEL_REGISTRY    — { llm: {key: {...}}, image: {key: {...}} }
 *   BUILTIN_PRESETS   — ["recommended", "all-haiku", "all-local", ...]
 *   SAVED_PROFILES    — ["profile-name", ...]
 *   DEFAULT_PRESET    — currently active default preset (mutated on save)
 */

const PROFILE_NAME_RE = /^[a-zA-Z0-9_-]+$/;

document.addEventListener('DOMContentLoaded', () => {
  renderDefaultPresetDropdown();
  renderProfilesTable();
  renderRegistry();
  wireGlobalListeners();
});

function wireGlobalListeners() {
  const sel = document.getElementById('default-preset');
  if (sel) sel.addEventListener('change', onDefaultPresetChange);

  const closeBtn = document.getElementById('profile-view-close');
  if (closeBtn) {
    closeBtn.addEventListener('click', () => {
      const d = document.getElementById('profile-view-dialog');
      if (d) d.close();
    });
  }
}

// ---------------------------------------------------------------------------
// Default preset
// ---------------------------------------------------------------------------

function renderDefaultPresetDropdown() {
  const sel = document.getElementById('default-preset');
  if (!sel) return;

  const groups = [
    { label: 'Built-in presets', items: BUILTIN_PRESETS },
    { label: 'Saved profiles', items: SAVED_PROFILES },
  ];

  const frag = document.createDocumentFragment();
  for (const g of groups) {
    if (g.items.length === 0) continue;
    const og = document.createElement('optgroup');
    og.label = g.label;
    for (const name of g.items) {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      if (name === DEFAULT_PRESET) opt.selected = true;
      og.appendChild(opt);
    }
    frag.appendChild(og);
  }
  sel.replaceChildren(frag);
}

async function onDefaultPresetChange() {
  const sel = document.getElementById('default-preset');
  const value = sel.value;
  try {
    const resp = await fetch('/api/settings/global', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ default_preset: value }),
    });
    const data = await resp.json();
    if (resp.ok && data.success) {
      DEFAULT_PRESET = value;
      showToast(`Default preset → "${value}"`, 'success');
    } else {
      showToast('Error: ' + (data.error || 'Unknown'), 'error');
      // Revert the dropdown to the persisted value.
      sel.value = DEFAULT_PRESET;
    }
  } catch (err) {
    console.error('[settings.js] Network error:', err);
    showToast('Network error: ' + err.message, 'error');
    sel.value = DEFAULT_PRESET;
  }
}

// ---------------------------------------------------------------------------
// Saved profiles
// ---------------------------------------------------------------------------

function renderProfilesTable() {
  const tbody = document.getElementById('profiles-body');
  if (!tbody) return;

  if (SAVED_PROFILES.length === 0) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 2;
    td.className = 'empty-row';
    td.textContent = 'No saved profiles yet. Create one from the project Settings tab.';
    tr.appendChild(td);
    tbody.replaceChildren(tr);
    return;
  }

  const frag = document.createDocumentFragment();
  for (const name of SAVED_PROFILES) {
    frag.appendChild(buildProfileRow(name));
  }
  tbody.replaceChildren(frag);
}

function buildProfileRow(name) {
  const tr = document.createElement('tr');

  const nameCell = document.createElement('td');
  nameCell.textContent = name;
  tr.appendChild(nameCell);

  const actionCell = document.createElement('td');
  const actions = document.createElement('div');
  actions.className = 'actions';
  for (const [action, label, klass] of [
    ['view', 'View', 'btn'],
    ['rename', 'Rename', 'btn'],
    ['delete', 'Delete', 'btn btn-danger'],
  ]) {
    const btn = document.createElement('button');
    btn.className = klass;
    btn.textContent = label;
    btn.dataset.action = action;
    btn.dataset.profile = name;
    btn.addEventListener('click', onProfileAction);
    actions.appendChild(btn);
  }
  actionCell.appendChild(actions);
  tr.appendChild(actionCell);

  return tr;
}

function onProfileAction(event) {
  const btn = event.currentTarget;
  const action = btn.dataset.action;
  const name = btn.dataset.profile;
  if (!name) return;

  if (action === 'view') return viewProfile(name);
  if (action === 'rename') return renameProfile(name);
  if (action === 'delete') return deleteProfile(name);
}

async function viewProfile(name) {
  const dialog = document.getElementById('profile-view-dialog');
  const title = document.getElementById('profile-view-title');
  const body = document.getElementById('profile-view-body');
  title.textContent = `Profile: ${name}`;
  body.textContent = 'Loading…';
  if (typeof dialog.showModal === 'function') {
    dialog.showModal();
  } else {
    dialog.setAttribute('open', '');
  }

  try {
    const resp = await fetch(`/api/settings/load?name=${encodeURIComponent(name)}`);
    const data = await resp.json();
    if (resp.ok && data.settings) {
      body.textContent = JSON.stringify(data.settings, null, 2);
    } else {
      body.textContent = 'Error: ' + (data.error || 'Unknown');
    }
  } catch (err) {
    body.textContent = 'Network error: ' + err.message;
  }
}

async function renameProfile(name) {
  const newName = prompt(`Rename profile "${name}" to:`, name);
  if (newName === null) return;

  const candidate = newName.trim().toLowerCase();
  if (!candidate || !PROFILE_NAME_RE.test(candidate)) {
    showToast('Invalid name (use letters, digits, "-", "_")', 'error');
    return;
  }
  if (candidate === name) return;
  if (SAVED_PROFILES.includes(candidate)) {
    showToast(`Profile "${candidate}" already exists`, 'error');
    return;
  }

  try {
    const loadResp = await fetch(`/api/settings/load?name=${encodeURIComponent(name)}`);
    const loadData = await loadResp.json();
    if (!loadResp.ok || !loadData.settings) {
      showToast('Error loading profile: ' + (loadData.error || 'Unknown'), 'error');
      return;
    }

    const saveResp = await fetch('/api/settings/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: candidate, settings: loadData.settings }),
    });
    const saveData = await saveResp.json();
    if (!saveResp.ok || !saveData.success) {
      showToast('Error saving renamed profile: ' + (saveData.error || 'Unknown'), 'error');
      return;
    }

    // If we're renaming the *active* default, repoint global.toml at the new
    // name first — otherwise the upcoming DELETE would 409 because the server
    // refuses to delete the currently-active default.
    if (name === DEFAULT_PRESET) {
      const globResp = await fetch('/api/settings/global', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ default_preset: candidate }),
      });
      const globData = await globResp.json();
      if (!globResp.ok || !globData.success) {
        showToast(
          'Renamed but failed to update default-preset pointer: ' + (globData.error || 'Unknown'),
          'error',
        );
        return;
      }
      DEFAULT_PRESET = candidate;
    }

    const delResp = await fetch(`/api/settings/profile/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    });
    const delData = await delResp.json();
    if (!delResp.ok || !delData.success) {
      showToast('Renamed but failed to remove old: ' + (delData.error || 'Unknown'), 'error');
    } else {
      showToast(`Renamed "${name}" → "${candidate}"`, 'success');
    }

    SAVED_PROFILES.splice(SAVED_PROFILES.indexOf(name), 1, candidate);
    SAVED_PROFILES.sort();
    renderProfilesTable();
    renderDefaultPresetDropdown();
  } catch (err) {
    console.error('[settings.js] Network error:', err);
    showToast('Network error: ' + err.message, 'error');
  }
}

async function deleteProfile(name) {
  if (name === DEFAULT_PRESET) {
    showToast(
      `"${name}" is the current default preset. Pick a different default first.`,
      'error',
    );
    return;
  }
  if (!confirm(`Delete profile "${name}"? This cannot be undone.`)) return;

  try {
    const resp = await fetch(`/api/settings/profile/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    });
    const data = await resp.json();
    if (resp.ok && data.success) {
      const idx = SAVED_PROFILES.indexOf(name);
      if (idx >= 0) SAVED_PROFILES.splice(idx, 1);
      renderProfilesTable();
      renderDefaultPresetDropdown();
      showToast(`Deleted "${name}"`, 'success');
    } else {
      showToast('Error: ' + (data.error || 'Unknown'), 'error');
    }
  } catch (err) {
    console.error('[settings.js] Network error:', err);
    showToast('Network error: ' + err.message, 'error');
  }
}

// ---------------------------------------------------------------------------
// Read-only registry
// ---------------------------------------------------------------------------

function renderRegistry() {
  renderLLMRegistry();
  renderImageRegistry();
}

function renderLLMRegistry() {
  const tbody = document.getElementById('llm-registry-body');
  if (!tbody) return;

  const sorted = Object.entries(MODEL_REGISTRY.llm).sort((a, b) => b[1].tier - a[1].tier);
  const frag = document.createDocumentFragment();
  for (const [key, model] of sorted) {
    const tr = document.createElement('tr');
    tr.appendChild(codeCell(key));
    tr.appendChild(llmNameCell(model));
    tr.appendChild(textCell(model.provider, '#aaa'));
    tr.appendChild(llmPricingCell(model));
    tr.appendChild(textCell(String(model.tier), '#aaa'));
    frag.appendChild(tr);
  }
  tbody.replaceChildren(frag);
}

function renderImageRegistry() {
  const tbody = document.getElementById('image-registry-body');
  if (!tbody) return;

  const entries = Object.entries(MODEL_REGISTRY.image).sort((a, b) => {
    const ai = a[1].implemented ? 0 : 1;
    const bi = b[1].implemented ? 0 : 1;
    return ai - bi || a[1].name.localeCompare(b[1].name);
  });

  const frag = document.createDocumentFragment();
  for (const [key, model] of entries) {
    const tr = document.createElement('tr');
    tr.appendChild(codeCell(key));
    tr.appendChild(imageNameCell(model));
    tr.appendChild(textCell(model.provider, '#aaa'));
    tr.appendChild(imageCostCell(model));
    frag.appendChild(tr);
  }
  tbody.replaceChildren(frag);
}

function codeCell(text) {
  const td = document.createElement('td');
  const code = document.createElement('code');
  code.textContent = text;
  td.appendChild(code);
  return td;
}

function textCell(text, color) {
  const td = document.createElement('td');
  if (color) td.style.color = color;
  td.textContent = text;
  return td;
}

function tag(text, klass) {
  const span = document.createElement('span');
  span.className = `tag ${klass}`;
  span.textContent = text;
  return span;
}

function llmNameCell(model) {
  const td = document.createElement('td');
  td.appendChild(document.createTextNode(model.name));
  if (model.supports_vision) td.appendChild(tag('vision', 'tag-vision'));
  if (model.supports_effort) td.appendChild(tag('effort', 'tag-effort'));
  if (model.provider === 'llamacpp') td.appendChild(tag('local', 'tag-local'));
  return td;
}

function llmPricingCell(model) {
  const td = document.createElement('td');
  td.style.color = '#aaa';
  if (model.input_price > 0 || model.output_price > 0) {
    td.textContent = `$${model.input_price.toFixed(2)} / $${model.output_price.toFixed(2)}`;
  } else {
    const span = document.createElement('span');
    span.style.color = '#2ecc71';
    span.textContent = 'Free';
    td.appendChild(span);
  }
  return td;
}

function imageNameCell(model) {
  const td = document.createElement('td');
  td.appendChild(document.createTextNode(model.name));
  if (!model.implemented) td.appendChild(tag('not implemented', 'tag-placeholder'));
  if (model.provider === 'comfyui') td.appendChild(tag('local', 'tag-local'));
  return td;
}

function imageCostCell(model) {
  const td = document.createElement('td');
  td.style.color = '#aaa';
  if (model.cost_per_image > 0) {
    td.textContent = `$${model.cost_per_image.toFixed(3)}`;
  } else {
    const span = document.createElement('span');
    span.style.color = '#2ecc71';
    span.textContent = 'Free';
    td.appendChild(span);
  }
  return td;
}

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------

function showToast(message, type) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.className = `toast toast-${type} show`;
  setTimeout(() => toast.classList.remove('show'), 3000);
}
