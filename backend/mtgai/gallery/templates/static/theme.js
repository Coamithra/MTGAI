/**
 * Theme Wizard — form logic for setting, constraints, and card requests.
 *
 * Expects EXISTING_THEME global (null or theme object) set by the template.
 */

// ---------------------------------------------------------------------------
// Extraction state
// ---------------------------------------------------------------------------

let _uploadId = null;
let _currentAnalysis = null;
let _uploadData = null;

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  if (EXISTING_THEME) {
    populateFromTheme(EXISTING_THEME);
  } else {
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

  // Show refresh buttons if there's setting text
  if (theme.setting || theme.theme || theme.flavor_description) {
    document.getElementById('refresh-constraints').style.display = 'inline-block';
    document.getElementById('refresh-card-requests').style.display = 'inline-block';
  }

  // Update status
  const status = document.getElementById('theme-status');
  status.textContent = 'Loaded: ' + (theme.name || theme.code);
  status.className = 'theme-status loaded';
}

// ---------------------------------------------------------------------------
// Dynamic lists (with AI-generated badge support)
// ---------------------------------------------------------------------------

function addConstraint(value, aiGenerated) {
  const list = document.getElementById('constraints-list');
  const item = document.createElement('div');
  item.className = 'list-item';
  if (aiGenerated) item.dataset.aiGenerated = 'true';

  const badge = aiGenerated ? '<span class="ai-badge">AI</span>' : '';
  item.innerHTML = `
    <input type="text" placeholder="e.g. Artifact subtheme — at least 6 artifact creatures"
           value="${escapeAttr(value || '')}"
           oninput="clearAiBadge(this)">
    ${badge}
    <button class="btn-remove" onclick="this.parentElement.remove()" title="Remove">&times;</button>
  `;
  list.appendChild(item);
  if (!value) item.querySelector('input').focus();
}

function addCardRequest(value, aiGenerated) {
  const list = document.getElementById('card-requests-list');
  const item = document.createElement('div');
  item.className = 'list-item';
  if (aiGenerated) item.dataset.aiGenerated = 'true';

  const badge = aiGenerated ? '<span class="ai-badge">AI</span>' : '';
  item.innerHTML = `
    <textarea rows="2"
      placeholder="e.g. Feretha's Throne, a legendary artifact, mythic rare, that gains control of creatures"
      oninput="clearAiBadge(this)"
    >${escapeHtml(value || '')}</textarea>
    ${badge}
    <button class="btn-remove" onclick="this.parentElement.remove()" title="Remove">&times;</button>
  `;
  list.appendChild(item);
  if (!value) item.querySelector('textarea').focus();
}

function clearAiBadge(el) {
  const item = el.closest('.list-item');
  if (item) {
    delete item.dataset.aiGenerated;
    const badge = item.querySelector('.ai-badge');
    if (badge) badge.remove();
  }
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

  const constraints = [];
  document.querySelectorAll('#constraints-list .list-item input').forEach(input => {
    const val = input.value.trim();
    if (val) constraints.push(val);
  });

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
    console.error('[theme.js] Network error:', err);
    showToast('Network error: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Save Theme';
  }
}

// ---------------------------------------------------------------------------
// Load existing theme — native file picker reads JSON content directly,
// sidestepping the browser's parent-path restriction (the file's `code` field
// is the source of truth, not the parent folder).
// ---------------------------------------------------------------------------

function loadExistingFromFile(event) {
  const input = event.target;
  const file = input.files && input.files[0];
  // Reset so the same file can be picked twice in a row.
  input.value = '';
  if (!file) return;

  const reader = new FileReader();
  reader.onload = () => {
    let theme;
    try {
      theme = JSON.parse(reader.result);
    } catch (err) {
      showToast('Could not parse JSON: ' + err.message, 'error');
      return;
    }
    if (!theme || typeof theme !== 'object' || Array.isArray(theme)) {
      showToast('File does not contain a theme object', 'error');
      return;
    }
    if (!theme.code) {
      showToast('File is missing a "code" field — not a valid theme.json', 'error');
      return;
    }
    populateFromTheme(theme);
    showToast(`Loaded theme for ${theme.code}`, 'success');
  };
  reader.onerror = () => {
    showToast('Could not read file', 'error');
  };
  reader.readAsText(file);
}

// ---------------------------------------------------------------------------
// File upload + analysis (Step 1)
// ---------------------------------------------------------------------------

async function uploadFile() {
  const fileInput = document.getElementById('extract-file');
  const file = fileInput.files[0];
  if (!file) {
    showToast('Select a file first', 'error');
    return;
  }

  const btn = document.getElementById('extract-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Analyzing...';

  try {
    const formData = new FormData();
    formData.append('file', file);

    const resp = await fetch('/api/pipeline/theme/upload', {
      method: 'POST',
      body: formData,
    });
    const data = await resp.json();
    if (data.error) {
      showToast('Error: ' + data.error, 'error');
      return;
    }

    _uploadId = data.upload_id;
    _uploadData = data;

    document.getElementById('extract-panel').classList.add('visible');
    await analyzeExtraction();

  } catch (err) {
    console.error('[theme.js] Network error:', err);
    showToast('Network error: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Analyze File';
  }
}

// ---------------------------------------------------------------------------
// Analyze extraction (token count + cost estimate)
// ---------------------------------------------------------------------------

async function analyzeExtraction() {
  document.getElementById('stat-tokens').textContent = '...';
  document.getElementById('stat-cost').textContent = '...';

  try {
    const resp = await fetch('/api/pipeline/theme/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ upload_id: _uploadId }),
    });
    const data = await resp.json();
    if (data.error) {
      showToast('Analysis error: ' + data.error, 'error');
      return;
    }

    _currentAnalysis = data;

    document.getElementById('stat-tokens').textContent = data.token_count.toLocaleString();
    document.getElementById('stat-tokens').className =
      'value ' + (data.fits_in_context ? 'ok' : 'warning');

    document.getElementById('stat-context').textContent =
      data.context_window.toLocaleString();

    document.getElementById('stat-chunks').textContent = data.chunk_count;
    document.getElementById('stat-chunks').className =
      'value ' + (data.chunk_count > 1 ? 'warning' : 'ok');

    document.getElementById('stat-cost').textContent =
      data.estimated_cost_usd > 0
        ? '$' + data.estimated_cost_usd.toFixed(4)
        : 'Free';

    document.getElementById('chunk-warning').style.display =
      data.chunk_count > 1 ? 'block' : 'none';

  } catch (err) {
    console.error('[theme.js] Analysis failed:', err);
    showToast('Analysis failed: ' + err.message, 'error');
  }
}

function dismissExtractionPanel() {
  document.getElementById('extract-panel').classList.remove('visible');
  _uploadId = null;
  _currentAnalysis = null;
  _uploadData = null;
}

async function cancelRunningExtraction() {
  const btn = document.getElementById('cancel-extract-btn');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Cancelling...';
  }
  try {
    await fetch('/api/pipeline/theme/cancel', { method: 'POST' });
  } catch (err) {
    console.error('[theme.js] Cancel failed:', err);
  }
}

// ---------------------------------------------------------------------------
// Run streaming extraction (Step 2)
// ---------------------------------------------------------------------------

async function runExtraction() {
  document.getElementById('extract-panel').classList.remove('visible');
  document.getElementById('extract-progress').classList.add('visible');

  const progressBar = document.getElementById('progress-bar');
  const progressStatus = document.getElementById('progress-status');
  const cancelBtn = document.getElementById('cancel-extract-btn');
  const textarea = document.getElementById('setting');

  textarea.value = '';
  progressBar.style.width = '10%';
  progressStatus.textContent = 'Starting extraction...';
  clearExtractionError('constraints-list');
  clearExtractionError('card-requests-list');

  const extractBtn = document.getElementById('run-extract-btn');
  extractBtn.disabled = true;
  if (cancelBtn) {
    cancelBtn.disabled = false;
    cancelBtn.textContent = 'Cancel Extraction';
  }

  const state = { gotDone: false, gotError: false, gotCancelled: false };

  try {
    const params = new URLSearchParams({ upload_id: _uploadId });
    const response = await fetch(`/api/pipeline/theme/extract-stream?${params}`);
    if (!response.ok) {
      if (response.status === 409) {
        throw new Error('Another extraction is already running');
      }
      throw new Error(`HTTP ${response.status} ${response.statusText}`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      const parts = buffer.split('\n\n');
      buffer = parts.pop();

      for (const part of parts) {
        if (!part.trim()) continue;
        const lines = part.split('\n');
        let eventType = null;
        let eventData = null;

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            try {
              eventData = JSON.parse(line.slice(6));
            } catch (e) { /* skip malformed */ }
          }
        }

        if (eventType && eventData) {
          handleExtractionEvent(eventType, eventData, textarea, progressBar, progressStatus, state);
        }
      }
    }

    if (!state.gotDone && !state.gotError && !state.gotCancelled) {
      progressStatus.textContent = 'Extraction aborted before completion';
      showToast('Extraction aborted before completion - see server logs', 'error');
      const settingText = textarea.value.trim();
      if (settingText) {
        showExtractionError('constraints-list',
          'Extraction stream ended before constraints were produced.',
          '',
          { label: 'Retry constraints', fn: refreshConstraints });
        showExtractionError('card-requests-list',
          'Extraction stream ended before card suggestions were produced.',
          '',
          { label: 'Retry card requests', fn: refreshCardRequests });
      }
    }
  } catch (err) {
    progressStatus.textContent = 'Extraction failed: ' + err.message;
    console.error('[theme.js] Extraction failed:', err);
    showToast('Extraction failed: ' + err.message, 'error');
  } finally {
    extractBtn.disabled = false;
    if (cancelBtn) cancelBtn.disabled = true;
    _uploadId = null;
    _uploadData = null;
    if (state.gotDone) {
      document.getElementById('extract-progress').classList.remove('visible');
    }
  }
}

function handleExtractionEvent(type, data, textarea, progressBar, progressStatus, state) {
  switch (type) {
    case 'status':
      progressStatus.textContent = data.message;
      if (data.message.includes('Generating theme')) {
        progressBar.style.width = '30%';
      } else if (data.message.includes('constraints')) {
        progressBar.style.width = '80%';
      }
      // Per-section progress: "Extracting X (3/7)..."
      const secMatch = data.message.match(/\((\d+)\/(\d+)\)/);
      if (secMatch) {
        const pct = 10 + (parseInt(secMatch[1]) / parseInt(secMatch[2])) * 65;
        progressBar.style.width = pct + '%';
      }
      break;

    case 'theme_chunk':
      textarea.value += data.text;
      textarea.scrollTop = textarea.scrollHeight;
      progressBar.style.width = '60%';
      break;

    case 'complete':
      progressBar.style.width = '75%';
      progressStatus.textContent = `Theme extracted ($${data.cost_usd.toFixed(4)})`;
      // For multi-chunk: theme_text has the final accumulated result
      if (data.theme_text) {
        textarea.value = data.theme_text;
        textarea.scrollTop = textarea.scrollHeight;
      }
      break;

    case 'constraints':
      clearExtractionError('constraints-list');
      if (data.constraints) {
        data.constraints.forEach(c => addConstraint(c, true));
        document.getElementById('refresh-constraints').style.display = 'inline-block';
      }
      break;

    case 'constraints_error':
      progressStatus.textContent = 'Constraints extraction failed - see section below';
      showExtractionError('constraints-list', data.message || 'Constraints extraction failed', data.raw || '',
        { label: 'Retry', fn: refreshConstraints });
      document.getElementById('refresh-constraints').style.display = 'inline-block';
      showToast('Constraints extraction failed', 'error');
      break;

    case 'card_suggestions':
      clearExtractionError('card-requests-list');
      if (data.suggestions) {
        data.suggestions.forEach(s => {
          const desc = `${s.name}: ${s.description}`;
          addCardRequest(desc, true);
        });
        document.getElementById('refresh-card-requests').style.display = 'inline-block';
      }
      break;

    case 'suggestions_error':
      progressStatus.textContent = 'Card-suggestion extraction failed - see section below';
      showExtractionError('card-requests-list', data.message || 'Card suggestions extraction failed', data.raw || '',
        { label: 'Retry', fn: refreshCardRequests });
      document.getElementById('refresh-card-requests').style.display = 'inline-block';
      showToast('Card suggestions failed', 'error');
      break;

    case 'done':
      if (state) state.gotDone = true;
      progressBar.style.width = '100%';
      progressStatus.textContent = `Extraction complete ($${data.total_cost_usd.toFixed(4)})`;
      showToast(`Extraction complete - $${data.total_cost_usd.toFixed(4)}`, 'success');
      break;

    case 'error':
      if (state) state.gotError = true;
      progressStatus.textContent = 'Error: ' + (data.message || 'unknown error');
      if (data.log_path) {
        progressStatus.textContent += ' - log: ' + data.log_path;
      }
      showToast('Error: ' + data.message, 'error');
      break;

    case 'cancelled':
      if (state) state.gotCancelled = true;
      progressStatus.textContent = 'Extraction cancelled';
      showToast('Extraction cancelled', 'success');
      break;
  }
}

// ---------------------------------------------------------------------------
// Inline error banner helpers
// ---------------------------------------------------------------------------

function showExtractionError(listId, message, raw, retry) {
  const list = document.getElementById(listId);
  if (!list) return;
  clearExtractionError(listId);
  const banner = document.createElement('div');
  banner.className = 'extraction-error';
  banner.dataset.errorFor = listId;

  const title = document.createElement('div');
  title.className = 'err-title';
  title.textContent = 'Extraction error';
  banner.appendChild(title);

  const msg = document.createElement('div');
  msg.textContent = message;
  banner.appendChild(msg);

  if (raw) {
    const rawBox = document.createElement('div');
    rawBox.className = 'err-raw';
    rawBox.textContent = raw.length > 1200 ? raw.slice(0, 1200) + '\n...[truncated]' : raw;
    banner.appendChild(rawBox);
  }

  if (retry && typeof retry.fn === 'function') {
    const actions = document.createElement('div');
    actions.className = 'err-actions';
    const btn = document.createElement('button');
    btn.textContent = retry.label || 'Retry';
    btn.addEventListener('click', () => retry.fn());
    actions.appendChild(btn);
    banner.appendChild(actions);
  }

  list.parentNode.insertBefore(banner, list);
}

function clearExtractionError(listId) {
  const existing = document.querySelector(`.extraction-error[data-error-for="${listId}"]`);
  if (existing) existing.remove();
}

// ---------------------------------------------------------------------------
// Refresh AI-generated items
// ---------------------------------------------------------------------------

async function refreshConstraints() {
  // Remove AI-generated constraints, or all if none are flagged (e.g. after load)
  const aiItems = document.querySelectorAll('#constraints-list .list-item[data-ai-generated="true"]');
  if (aiItems.length > 0) {
    aiItems.forEach(el => el.remove());
  } else {
    document.getElementById('constraints-list').innerHTML = '';
  }

  const settingText = document.getElementById('setting').value.trim();
  if (!settingText) {
    showToast('No setting text to extract constraints from', 'error');
    return;
  }

  const btn = document.getElementById('refresh-constraints');
  btn.disabled = true;
  btn.textContent = 'Refreshing...';

  clearExtractionError('constraints-list');
  try {
    const resp = await fetch('/api/pipeline/theme/extract-section', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme_text: settingText, kind: 'constraints' }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const msg = data.error || data.detail || `HTTP ${resp.status}`;
      showExtractionError('constraints-list', msg, '',
        { label: 'Retry', fn: refreshConstraints });
      showToast('Refresh failed: ' + msg + ' (try Ctrl+Shift+R if stale)', 'error');
      return;
    }
    if (data.error) {
      showExtractionError('constraints-list', data.error, '',
        { label: 'Retry', fn: refreshConstraints });
      showToast('Refresh error: ' + data.error, 'error');
      return;
    }
    if (data.constraints_error) {
      showExtractionError('constraints-list', data.constraints_error, data.constraints_raw || '',
        { label: 'Retry', fn: refreshConstraints });
      showToast('Constraints extraction failed', 'error');
      return;
    }
    const items = Array.isArray(data.constraints) ? data.constraints : [];
    items.forEach(c => addConstraint(c, true));
    if (items.length === 0) {
      showToast('LLM returned no constraints for this setting', 'warn');
    } else {
      showToast(`Constraints refreshed ($${(data.cost_usd || 0).toFixed(4)})`, 'success');
    }
  } catch (err) {
    showExtractionError('constraints-list', err.message, '',
      { label: 'Retry', fn: refreshConstraints });
    console.error('[theme.js] Refresh failed:', err);
    showToast('Refresh failed: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Refresh AI';
  }
}

async function refreshCardRequests() {
  // Remove AI-generated suggestions, or all if none are flagged (e.g. after load)
  const aiItems = document.querySelectorAll('#card-requests-list .list-item[data-ai-generated="true"]');
  if (aiItems.length > 0) {
    aiItems.forEach(el => el.remove());
  } else {
    document.getElementById('card-requests-list').innerHTML = '';
  }

  const settingText = document.getElementById('setting').value.trim();
  if (!settingText) {
    showToast('No setting text to extract card suggestions from', 'error');
    return;
  }

  const btn = document.getElementById('refresh-card-requests');
  btn.disabled = true;
  btn.textContent = 'Refreshing...';

  clearExtractionError('card-requests-list');
  try {
    const resp = await fetch('/api/pipeline/theme/extract-section', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme_text: settingText, kind: 'card_suggestions' }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const msg = data.error || data.detail || `HTTP ${resp.status}`;
      showExtractionError('card-requests-list', msg, '',
        { label: 'Retry', fn: refreshCardRequests });
      showToast('Refresh failed: ' + msg + ' (try Ctrl+Shift+R if stale)', 'error');
      return;
    }
    if (data.error) {
      showExtractionError('card-requests-list', data.error, '',
        { label: 'Retry', fn: refreshCardRequests });
      showToast('Refresh error: ' + data.error, 'error');
      return;
    }
    if (data.suggestions_error) {
      showExtractionError('card-requests-list', data.suggestions_error, data.suggestions_raw || '',
        { label: 'Retry', fn: refreshCardRequests });
      showToast('Card suggestions extraction failed', 'error');
      return;
    }
    const items = Array.isArray(data.card_suggestions) ? data.card_suggestions : [];
    items.forEach(s => {
      const desc = `${s.name}: ${s.description}`;
      addCardRequest(desc, true);
    });
    if (items.length === 0) {
      showToast('LLM returned no card suggestions for this setting', 'warn');
    } else {
      showToast(`Card suggestions refreshed ($${(data.cost_usd || 0).toFixed(4)})`, 'success');
    }
  } catch (err) {
    showExtractionError('card-requests-list', err.message, '',
      { label: 'Retry', fn: refreshCardRequests });
    console.error('[theme.js] Refresh failed:', err);
    showToast('Refresh failed: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Refresh AI';
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
