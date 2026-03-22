/**
 * Theme Wizard — form logic for setting, constraints, and card requests.
 *
 * Expects EXISTING_THEME global (null or theme object) set by the template.
 */

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  if (EXISTING_THEME) {
    populateFromTheme(EXISTING_THEME);
  } else {
    // Start with one empty constraint and one empty card request
    addConstraint();
    addCardRequest();
  }
});

// ---------------------------------------------------------------------------
// Populate from existing theme
// ---------------------------------------------------------------------------

function populateFromTheme(theme) {
  document.getElementById('set-name').value = theme.name || '';
  document.getElementById('set-code').value = theme.code || '';
  document.getElementById('set-size').value = theme.set_size || 60;
  document.getElementById('mechanic-count').value = theme.mechanic_count || 3;
  document.getElementById('setting').value = theme.setting || '';

  // Legacy format: combine theme + flavor_description into setting
  if (!theme.setting && (theme.theme || theme.flavor_description)) {
    let parts = [];
    if (theme.theme) parts.push(theme.theme);
    if (theme.flavor_description) parts.push(theme.flavor_description);
    document.getElementById('setting').value = parts.join('\n\n');
  }

  // Constraints
  const constraints = theme.constraints || theme.special_constraints || [];
  const constraintsList = document.getElementById('constraints-list');
  constraintsList.innerHTML = '';
  if (constraints.length === 0) {
    addConstraint();
  } else {
    constraints.forEach(c => addConstraint(c));
  }

  // Card requests
  const requests = theme.card_requests || [];
  const requestsList = document.getElementById('card-requests-list');
  requestsList.innerHTML = '';
  if (requests.length === 0) {
    addCardRequest();
  } else {
    requests.forEach(r => addCardRequest(r));
  }

  // Update status
  const status = document.getElementById('theme-status');
  status.textContent = 'Loaded: ' + (theme.name || theme.code);
  status.className = 'theme-status loaded';
}

// ---------------------------------------------------------------------------
// Dynamic lists
// ---------------------------------------------------------------------------

function addConstraint(value) {
  const list = document.getElementById('constraints-list');
  const item = document.createElement('div');
  item.className = 'list-item';
  item.innerHTML = `
    <input type="text" placeholder="e.g. Artifact subtheme — at least 6 artifact creatures"
           value="${escapeAttr(value || '')}">
    <button class="btn-remove" onclick="this.parentElement.remove()" title="Remove">&times;</button>
  `;
  list.appendChild(item);
  if (!value) item.querySelector('input').focus();
}

function addCardRequest(value) {
  const list = document.getElementById('card-requests-list');
  const item = document.createElement('div');
  item.className = 'list-item';
  item.innerHTML = `
    <textarea rows="2"
      placeholder="e.g. Feretha's Throne, a legendary artifact, mythic rare, that gains control of creatures"
    >${escapeHtml(value || '')}</textarea>
    <button class="btn-remove" onclick="this.parentElement.remove()" title="Remove">&times;</button>
  `;
  list.appendChild(item);
  if (!value) item.querySelector('textarea').focus();
}

// ---------------------------------------------------------------------------
// Collect form data
// ---------------------------------------------------------------------------

function collectThemeData() {
  const name = document.getElementById('set-name').value.trim();
  const code = document.getElementById('set-code').value.trim().toUpperCase();
  const setSize = parseInt(document.getElementById('set-size').value, 10);
  const mechanicCount = parseInt(document.getElementById('mechanic-count').value, 10);
  const setting = document.getElementById('setting').value.trim();

  // Collect constraints (skip empty)
  const constraints = [];
  document.querySelectorAll('#constraints-list .list-item input').forEach(input => {
    const val = input.value.trim();
    if (val) constraints.push(val);
  });

  // Collect card requests (skip empty)
  const cardRequests = [];
  document.querySelectorAll('#card-requests-list .list-item textarea').forEach(ta => {
    const val = ta.value.trim();
    if (val) cardRequests.push(val);
  });

  return {
    name,
    code,
    set_size: setSize,
    mechanic_count: mechanicCount,
    setting,
    constraints,
    card_requests: cardRequests,
  };
}

// ---------------------------------------------------------------------------
// Save theme
// ---------------------------------------------------------------------------

async function saveTheme() {
  const data = collectThemeData();

  // Validation
  if (!data.name) {
    showToast('Please enter a set name.', 'error');
    document.getElementById('set-name').focus();
    return;
  }
  if (!data.code || data.code.length < 2 || data.code.length > 3) {
    showToast('Please enter a 2-3 letter set code.', 'error');
    document.getElementById('set-code').focus();
    return;
  }
  if (!data.setting) {
    showToast('Please describe your setting.', 'error');
    document.getElementById('setting').focus();
    return;
  }

  const btn = document.getElementById('save-btn');
  btn.disabled = true;
  btn.textContent = 'Saving...';

  try {
    const resp = await fetch('/api/pipeline/theme/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    const result = await resp.json();

    if (result.success) {
      showToast(`Theme saved for ${data.code}`, 'success');
      const status = document.getElementById('theme-status');
      status.textContent = 'Saved: ' + data.name;
      status.className = 'theme-status loaded';
    } else {
      showToast('Error: ' + (result.error || 'Unknown'), 'error');
    }
  } catch (err) {
    showToast('Network error: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Save Theme';
  }
}

// ---------------------------------------------------------------------------
// Load existing theme
// ---------------------------------------------------------------------------

async function loadExisting() {
  const code = document.getElementById('set-code').value.trim().toUpperCase();
  if (!code) {
    showToast('Enter a set code first', 'error');
    document.getElementById('set-code').focus();
    return;
  }

  try {
    const resp = await fetch(`/api/pipeline/theme/load/${encodeURIComponent(code)}`);
    const data = await resp.json();

    if (data.theme) {
      populateFromTheme(data.theme);
      showToast(`Loaded theme for ${code}`, 'success');
    } else {
      showToast(data.error || `No theme found for ${code}`, 'error');
    }
  } catch (err) {
    showToast('Network error: ' + err.message, 'error');
  }
}

// ---------------------------------------------------------------------------
// Extract setting from uploaded file
// ---------------------------------------------------------------------------

async function extractFromFile() {
  const fileInput = document.getElementById('extract-file');
  const file = fileInput.files[0];

  if (!file) {
    showToast('Select a file first', 'error');
    return;
  }

  const btn = document.getElementById('extract-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Extracting...';

  try {
    const formData = new FormData();
    formData.append('file', file);

    const resp = await fetch('/api/pipeline/theme/extract', {
      method: 'POST',
      body: formData,
    });
    const data = await resp.json();

    if (data.setting) {
      // Append to existing setting text (don't overwrite)
      const textarea = document.getElementById('setting');
      const existing = textarea.value.trim();
      textarea.value = existing
        ? existing + '\n\n---\n\n' + data.setting
        : data.setting;

      if (data.constraints && data.constraints.length > 0) {
        data.constraints.forEach(c => addConstraint(c));
      }

      showToast('Setting extracted from file', 'success');
    } else {
      showToast('Error: ' + (data.error || 'Extraction failed'), 'error');
    }
  } catch (err) {
    showToast('Network error: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Extract Setting';
  }
}

// ---------------------------------------------------------------------------
// Toast notifications
// ---------------------------------------------------------------------------

function showToast(message, type) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.className = `toast toast-${type} show`;
  setTimeout(() => toast.classList.remove('show'), 3000);
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function escapeAttr(text) {
  if (!text) return '';
  return text.replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
