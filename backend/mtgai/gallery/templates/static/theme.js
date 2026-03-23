/**
 * Theme Wizard — form logic for setting, constraints, and card requests.
 *
 * Expects EXISTING_THEME global (null or theme object) set by the template.
 */

// ---------------------------------------------------------------------------
// Extraction state
// ---------------------------------------------------------------------------

let _uploadId = null;
let _extractionModels = [];
let _currentAnalysis = null;
let _uploadData = null;

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  // Always load model list (needed for refresh buttons)
  loadExtractionModels();

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

    // Load model list and show panel
    await loadExtractionModels();
    showExtractionPanel(data);
    await analyzeExtraction();

  } catch (err) {
    showToast('Network error: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Analyze File';
  }
}

async function loadExtractionModels() {
  const resp = await fetch('/api/pipeline/theme/models');
  const data = await resp.json();
  _extractionModels = data.models;

  const select = document.getElementById('extract-model');
  select.innerHTML = _extractionModels.map(m => {
    const price = m.input_price > 0
      ? `$${m.input_price.toFixed(2)}/$${m.output_price.toFixed(2)}`
      : 'Free';
    const vision = m.supports_vision ? ' [vision]' : '';
    return `<option value="${escapeAttr(m.key)}">${escapeHtml(m.name)}${vision} &mdash; ${price}</option>`;
  }).join('');

  // Default to whatever is configured in settings for theme_extract
  const defaultKey = data.default_key || 'haiku';
  if (select.querySelector(`option[value="${defaultKey}"]`)) {
    select.value = defaultKey;
  }
}

function showExtractionPanel(uploadData) {
  document.getElementById('extract-panel').classList.add('visible');

  // Enable/disable images checkbox based on image count
  const imgGroup = document.getElementById('images-checkbox-group');
  const imgCheckbox = document.getElementById('include-images');
  if (uploadData.image_count === 0) {
    imgCheckbox.disabled = true;
    imgCheckbox.checked = false;
    imgGroup.style.opacity = '0.5';
    imgGroup.title = 'No images found in document';
  } else {
    imgCheckbox.disabled = false;
    imgGroup.style.opacity = '1';
    imgGroup.title = `${uploadData.image_count} image${uploadData.image_count !== 1 ? 's' : ''} found`;
  }
}

// ---------------------------------------------------------------------------
// Analyze extraction (token count + cost estimate)
// ---------------------------------------------------------------------------

async function analyzeExtraction() {
  const modelKey = document.getElementById('extract-model').value;
  const includeImages = document.getElementById('include-images').checked;

  // Show loading state in stats
  document.getElementById('stat-tokens').textContent = '...';
  document.getElementById('stat-cost').textContent = '...';

  try {
    const resp = await fetch('/api/pipeline/theme/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        upload_id: _uploadId,
        model_key: modelKey,
        include_images: includeImages,
      }),
    });
    const data = await resp.json();
    if (data.error) {
      showToast('Analysis error: ' + data.error, 'error');
      return;
    }

    _currentAnalysis = data;

    // Update stats display
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

    // Chunk warning
    document.getElementById('chunk-warning').style.display =
      data.chunk_count > 1 ? 'block' : 'none';

    // Update images checkbox based on model vision support
    const imgCheckbox = document.getElementById('include-images');
    const imgGroup = document.getElementById('images-checkbox-group');
    if (!data.supports_vision) {
      imgCheckbox.disabled = true;
      imgCheckbox.checked = false;
      imgGroup.title = 'Selected model does not support vision';
      imgGroup.style.opacity = '0.5';
    } else if (_uploadData && _uploadData.image_count > 0) {
      imgCheckbox.disabled = false;
      imgGroup.style.opacity = '1';
      imgGroup.title = `${_uploadData.image_count} image${_uploadData.image_count !== 1 ? 's' : ''} found`;
    }

  } catch (err) {
    showToast('Analysis failed: ' + err.message, 'error');
  }
}

function onExtractModelChange() {
  analyzeExtraction();
}

function onIncludeImagesChange() {
  analyzeExtraction();
}

function cancelExtraction() {
  document.getElementById('extract-panel').classList.remove('visible');
  _uploadId = null;
  _currentAnalysis = null;
  _uploadData = null;
}

// ---------------------------------------------------------------------------
// Run streaming extraction (Step 2)
// ---------------------------------------------------------------------------

async function runExtraction() {
  const modelKey = document.getElementById('extract-model').value;
  const includeImages = document.getElementById('include-images').checked;

  // Hide panel, show progress
  document.getElementById('extract-panel').classList.remove('visible');
  document.getElementById('extract-progress').classList.add('visible');

  const progressBar = document.getElementById('progress-bar');
  const progressStatus = document.getElementById('progress-status');
  const textarea = document.getElementById('setting');

  textarea.value = '';
  progressBar.style.width = '10%';
  progressStatus.textContent = 'Starting extraction...';

  const extractBtn = document.getElementById('run-extract-btn');
  extractBtn.disabled = true;

  try {
    const params = new URLSearchParams({
      upload_id: _uploadId,
      model_key: modelKey,
      include_images: includeImages,
    });
    const response = await fetch(`/api/pipeline/theme/extract-stream?${params}`);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Parse SSE events from buffer
      const parts = buffer.split('\n\n');
      buffer = parts.pop(); // keep incomplete event in buffer

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
          handleExtractionEvent(eventType, eventData, textarea, progressBar, progressStatus);
        }
      }
    }
  } catch (err) {
    showToast('Extraction failed: ' + err.message, 'error');
  } finally {
    document.getElementById('extract-progress').classList.remove('visible');
    extractBtn.disabled = false;
    _uploadId = null;
    _uploadData = null;
  }
}

function handleExtractionEvent(type, data, textarea, progressBar, progressStatus) {
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
      if (data.constraints) {
        data.constraints.forEach(c => addConstraint(c, true));
        document.getElementById('refresh-constraints').style.display = 'inline-block';
      }
      break;

    case 'card_suggestions':
      if (data.suggestions) {
        data.suggestions.forEach(s => {
          const desc = `${s.name}: ${s.description}`;
          addCardRequest(desc, true);
        });
        document.getElementById('refresh-card-requests').style.display = 'inline-block';
      }
      break;

    case 'done':
      progressBar.style.width = '100%';
      showToast(`Extraction complete — $${data.total_cost_usd.toFixed(4)}`, 'success');
      break;

    case 'error':
      showToast('Error: ' + data.message, 'error');
      break;
  }
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

  const modelKey = document.getElementById('extract-model')?.value || 'haiku';
  const btn = document.getElementById('refresh-constraints');
  btn.disabled = true;
  btn.textContent = 'Refreshing...';

  try {
    const resp = await fetch('/api/pipeline/theme/extract-constraints', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme_text: settingText, model_key: modelKey }),
    });
    const data = await resp.json();
    if (data.error) {
      showToast('Refresh error: ' + data.error, 'error');
      return;
    }
    if (data.constraints) {
      data.constraints.forEach(c => addConstraint(c, true));
    }
    showToast(`Constraints refreshed ($${data.cost_usd.toFixed(4)})`, 'success');
  } catch (err) {
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

  const modelKey = document.getElementById('extract-model')?.value || 'haiku';
  const btn = document.getElementById('refresh-card-requests');
  btn.disabled = true;
  btn.textContent = 'Refreshing...';

  try {
    const resp = await fetch('/api/pipeline/theme/extract-constraints', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme_text: settingText, model_key: modelKey }),
    });
    const data = await resp.json();
    if (data.error) {
      showToast('Refresh error: ' + data.error, 'error');
      return;
    }
    if (data.card_suggestions) {
      data.card_suggestions.forEach(s => {
        const desc = `${s.name}: ${s.description}`;
        addCardRequest(desc, true);
      });
    }
    showToast(`Card suggestions refreshed ($${data.cost_usd.toFixed(4)})`, 'success');
  } catch (err) {
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
