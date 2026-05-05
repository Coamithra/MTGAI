/**
 * Settings page — cross-set defaults: default preset, saved profiles
 * (view / rename / delete), and a read-only model registry view.
 *
 * Per-stage assignments moved to the per-set Project Settings tab.
 *
 * Globals from the template:
 *   MODEL_REGISTRY    — { llm: {key: {...}}, image: {key: {...}} }
 *   BUILTIN_PRESETS   — ["recommended", "all-haiku", "all-local", ...]
 *   SAVED_PROFILES    — ["profile-name", ...]
 *   DEFAULT_PRESET    — currently active default preset
 */

document.addEventListener('DOMContentLoaded', () => {
  renderDefaultPresetDropdown();
  renderProfilesTable();
  renderRegistry();
});

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

  sel.innerHTML = groups
    .filter(g => g.items.length > 0)
    .map(g => {
      const opts = g.items.map(name => {
        const selected = name === DEFAULT_PRESET ? 'selected' : '';
        return `<option value="${escapeAttr(name)}" ${selected}>${escapeHtml(name)}</option>`;
      }).join('');
      return `<optgroup label="${escapeAttr(g.label)}">${opts}</optgroup>`;
    })
    .join('');
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
      showToast(`Default preset → "${value}"`, 'success');
    } else {
      showToast('Error: ' + (data.error || 'Unknown'), 'error');
    }
  } catch (err) {
    console.error('[settings.js] Network error:', err);
    showToast('Network error: ' + err.message, 'error');
  }
}

// ---------------------------------------------------------------------------
// Saved profiles
// ---------------------------------------------------------------------------

function renderProfilesTable() {
  const tbody = document.getElementById('profiles-body');
  if (!tbody) return;

  if (SAVED_PROFILES.length === 0) {
    tbody.innerHTML = `<tr><td colspan="2" class="empty-row">No saved profiles yet. Create one from the Project Settings tab.</td></tr>`;
    return;
  }

  tbody.innerHTML = SAVED_PROFILES.map(name => `
    <tr>
      <td>${escapeHtml(name)}</td>
      <td>
        <div class="actions">
          <button class="btn" onclick="viewProfile('${escapeAttr(name)}')">View</button>
          <button class="btn" onclick="renameProfile('${escapeAttr(name)}')">Rename</button>
          <button class="btn btn-danger" onclick="deleteProfile('${escapeAttr(name)}')">Delete</button>
        </div>
      </td>
    </tr>
  `).join('');
}

async function viewProfile(name) {
  const dialog = document.getElementById('profile-view-dialog');
  const title = document.getElementById('profile-view-title');
  const body = document.getElementById('profile-view-body');
  title.textContent = `Profile: ${name}`;
  body.textContent = 'Loading…';
  dialog.showModal();

  try {
    const resp = await fetch(`/api/settings/load?name=${encodeURIComponent(name)}`);
    const data = await resp.json();
    if (data.settings) {
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
  const sanitized = newName.trim().replace(/[^a-zA-Z0-9_-]/g, '-').toLowerCase();
  if (!sanitized) {
    showToast('Invalid profile name', 'error');
    return;
  }
  if (sanitized === name) return;
  if (SAVED_PROFILES.includes(sanitized)) {
    showToast(`Profile "${sanitized}" already exists`, 'error');
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
      body: JSON.stringify({ name: sanitized, settings: loadData.settings }),
    });
    const saveData = await saveResp.json();
    if (!saveResp.ok || !saveData.success) {
      showToast('Error saving renamed profile: ' + (saveData.error || 'Unknown'), 'error');
      return;
    }

    const delResp = await fetch(`/api/settings/profile/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    });
    const delData = await delResp.json();
    if (!delResp.ok || !delData.success) {
      // The new file already exists; surface the partial-failure so the user
      // can clean up the old one manually rather than silently leaving both.
      showToast('Renamed but failed to remove old: ' + (delData.error || 'Unknown'), 'error');
    } else {
      showToast(`Renamed "${name}" → "${sanitized}"`, 'success');
    }

    SAVED_PROFILES.splice(SAVED_PROFILES.indexOf(name), 1, sanitized);
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
    showToast(`"${name}" is the current default preset. Pick a different default first.`, 'error');
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
  tbody.innerHTML = sorted.map(([key, model]) => {
    const tags = [];
    if (model.supports_vision) tags.push('<span class="tag tag-vision">vision</span>');
    if (model.supports_effort) tags.push('<span class="tag tag-effort">effort</span>');
    if (model.provider === 'llamacpp') tags.push('<span class="tag tag-local">local</span>');

    const pricing = model.input_price > 0 || model.output_price > 0
      ? `$${model.input_price.toFixed(2)} / $${model.output_price.toFixed(2)}`
      : '<span style="color: #2ecc71">Free</span>';

    return `
      <tr>
        <td><code>${escapeHtml(key)}</code></td>
        <td>${escapeHtml(model.name)}${tags.join('')}</td>
        <td style="color: #aaa">${escapeHtml(model.provider)}</td>
        <td style="color: #aaa">${pricing}</td>
        <td style="color: #aaa">${model.tier}</td>
      </tr>
    `;
  }).join('');
}

function renderImageRegistry() {
  const tbody = document.getElementById('image-registry-body');
  if (!tbody) return;

  const entries = Object.entries(MODEL_REGISTRY.image).sort((a, b) => {
    const ai = a[1].implemented ? 0 : 1;
    const bi = b[1].implemented ? 0 : 1;
    return ai - bi || a[1].name.localeCompare(b[1].name);
  });

  tbody.innerHTML = entries.map(([key, model]) => {
    const tags = [];
    if (!model.implemented) tags.push('<span class="tag tag-placeholder">not implemented</span>');
    if (model.provider === 'comfyui') tags.push('<span class="tag tag-local">local</span>');

    const cost = model.cost_per_image > 0
      ? `$${model.cost_per_image.toFixed(3)}`
      : '<span style="color: #2ecc71">Free</span>';

    return `
      <tr>
        <td><code>${escapeHtml(key)}</code></td>
        <td>${escapeHtml(model.name)}${tags.join('')}</td>
        <td style="color: #aaa">${escapeHtml(model.provider)}</td>
        <td style="color: #aaa">${cost}</td>
      </tr>
    `;
  }).join('');
}

// ---------------------------------------------------------------------------
// Toast + escaping
// ---------------------------------------------------------------------------

function showToast(message, type) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.className = `toast toast-${type} show`;
  setTimeout(() => toast.classList.remove('show'), 3000);
}

function escapeHtml(text) {
  if (text === undefined || text === null) return '';
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}

function escapeAttr(text) {
  if (text === undefined || text === null) return '';
  return String(text).replace(/&/g, '&amp;').replace(/'/g, '&#39;').replace(/"/g, '&quot;');
}
