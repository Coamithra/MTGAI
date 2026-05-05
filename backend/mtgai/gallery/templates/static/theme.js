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

// Setting textarea mode: "edit" shows the raw textarea, "preview" renders
// the markdown into a sibling div. Streaming extraction forces "edit" so
// chunks remain visible as they arrive; on completion we flip to "preview".
let _settingMode = 'preview';

// ---------------------------------------------------------------------------
// Markdown rendering for the setting preview
// ---------------------------------------------------------------------------

/**
 * Tiny zero-dep markdown→HTML renderer scoped to what the theme prompt
 * produces: `# heading`, `## heading`, `- ` / `* ` bullets, `**bold**`,
 * `*italic*`, inline `` `code` ``, and blank-line paragraphs. Anything
 * exotic (tables, blockquotes, fenced code) falls through as raw text.
 */
function renderMarkdown(src) {
  if (!src) return '';
  // HTML-escape first so user content can't inject tags. Inline markers
  // are reintroduced as real tags below.
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
    if (!line.trim()) {
      flushPara(); flushList();
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flushPara(); flushList();
      const lvl = Math.min(6, Math.max(1, heading[1].length));
      out.push(`<h${lvl}>${inline(heading[2])}</h${lvl}>`);
      continue;
    }
    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      flushPara();
      listItems.push(bullet[1]);
      continue;
    }
    flushList();
    para.push(line);
  }
  flushPara();
  flushList();
  return out.join('\n');
}

function renderSettingPreview() {
  const textarea = document.getElementById('setting');
  const preview = document.getElementById('setting-preview');
  if (!textarea || !preview) return;
  const text = textarea.value;
  if (!text.trim()) {
    preview.classList.add('empty');
    preview.textContent = 'No setting yet — use Extract from File or paste text into Edit mode.';
  } else {
    preview.classList.remove('empty');
    preview.innerHTML = renderMarkdown(text);
  }
}

function setSettingMode(mode) {
  _settingMode = mode === 'edit' ? 'edit' : 'preview';
  const textarea = document.getElementById('setting');
  const preview = document.getElementById('setting-preview');
  const btnEdit = document.getElementById('setting-mode-edit');
  const btnPrev = document.getElementById('setting-mode-preview');
  if (!textarea || !preview) return;
  if (_settingMode === 'edit') {
    textarea.style.display = '';
    preview.style.display = 'none';
    btnEdit && btnEdit.classList.add('active');
    btnPrev && btnPrev.classList.remove('active');
  } else {
    renderSettingPreview();
    textarea.style.display = 'none';
    preview.style.display = '';
    btnEdit && btnEdit.classList.remove('active');
    btnPrev && btnPrev.classList.add('active');
  }
}

// ---------------------------------------------------------------------------
// Init — hydrate from server state, then layer in any localStorage draft
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', async () => {
  // Seed UI from a draft if present (covers tab-switch + reload between
  // edit and Save). The runtime-state hydration below overwrites whatever
  // the server has on disk, but draft-restore is the right move first
  // because the server hydration is async — we don't want a flash of
  // empty form.
  const draft = MtgaiState.get('theme_draft', null);
  if (draft) {
    populateFromTheme(draft);
  } else if (EXISTING_THEME) {
    populateFromTheme(EXISTING_THEME);
  } else {
    addConstraint();
    addCardRequest();
  }

  wireDraftPersistence();

  const state = await MtgaiState.fetchRuntimeState();
  if (state) {
    if (state.active_set) {
      MtgaiState.setSetCode(state.active_set);
      _renderActiveSetDisplay(state.active_set);
    }
    // The server theme is the authoritative copy *unless* the user
    // has unsaved edits in this browser. saveTheme() clears the draft,
    // so any draft we still see is by definition newer than what's on
    // disk. Only fall back to the server theme when there's no draft
    // for the same set code.
    if (state.theme && _shouldHydrateFromServer(state.theme, draft)) {
      populateFromTheme(state.theme);
    }
    if (state.active_runs && state.active_runs.theme_extraction) {
      // An extraction is running — reattach to its event stream so the
      // UI shows live progress as if the user never left.
      reattachExtraction(state.active_runs.theme_extraction.upload_id);
    }
  }

  // Default the setting field to preview when content exists, edit when
  // empty so the placeholder is visible. Click on the rendered preview
  // jumps to edit mode (single-click to start typing).
  initSettingMode();
});

function initSettingMode() {
  const textarea = document.getElementById('setting');
  const preview = document.getElementById('setting-preview');
  if (!textarea || !preview) return;
  preview.addEventListener('click', () => {
    if (_settingMode === 'preview') setSettingMode('edit');
  });
  // Re-render preview live as the user edits in edit mode (covers the
  // 'paste markdown into edit, switch to preview' flow without a re-render
  // race).
  textarea.addEventListener('input', () => {
    if (_settingMode === 'preview') renderSettingPreview();
  });
  setSettingMode(textarea.value.trim() ? 'preview' : 'edit');
}

function _renderActiveSetDisplay(code) {
  const display = document.getElementById('active-set-display');
  if (display) display.textContent = code || '—';
}

function _shouldHydrateFromServer(serverTheme, draft) {
  // No draft -> server theme always wins.
  if (!draft) return true;
  // Different sets -> server theme wins (the draft is for a different
  // set, switching context to the server's active set).
  if (serverTheme.code && draft.code && serverTheme.code !== draft.code) {
    return true;
  }
  // Same set code -> the draft represents unsaved local edits, since
  // saveTheme() clears the draft on success. Keep it.
  return false;
}

// ---------------------------------------------------------------------------
// Populate from existing theme
// ---------------------------------------------------------------------------

function populateFromTheme(theme) {
  document.getElementById('set-name').value = theme.name || '';
  if (theme.code) _renderActiveSetDisplay(theme.code);
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

  // Constraints. Items may be plain strings (legacy / pre-provenance saves)
  // or { text, source } objects (current shape). Bare strings default to human.
  const constraints = theme.constraints || theme.special_constraints || [];
  const constraintsList = document.getElementById('constraints-list');
  constraintsList.innerHTML = '';
  if (constraints.length === 0) {
    addConstraint();
  } else {
    constraints.forEach(c => {
      const { text, source } = _normalizeProvenanceItem(c);
      addConstraint(text, source === 'ai');
    });
  }

  // Card requests — same string|object handling.
  const requests = theme.card_requests || [];
  const requestsList = document.getElementById('card-requests-list');
  requestsList.innerHTML = '';
  if (requests.length === 0) {
    addCardRequest();
  } else {
    requests.forEach(r => {
      const { text, source } = _normalizeProvenanceItem(r);
      addCardRequest(text, source === 'ai');
    });
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
    <button class="btn-remove" onclick="removeListItem(this)" title="Remove">&times;</button>
  `;
  list.appendChild(item);
  if (!value) item.querySelector('input').focus();
  // DOM-level mutation: the wireDraftPersistence listener only catches
  // 'input' events, so a programmatic add (AI extraction, populateFromTheme)
  // wouldn't otherwise reach the draft. Without this the draft snapshot
  // predates the AI insertion and a tab switch loses the AI provenance.
  schedulePersistDraft();
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
    <button class="btn-remove" onclick="removeListItem(this)" title="Remove">&times;</button>
  `;
  list.appendChild(item);
  if (!value) item.querySelector('textarea').focus();
  schedulePersistDraft();
}

function removeListItem(btn) {
  const item = btn.closest('.list-item');
  if (item) item.remove();
  schedulePersistDraft();
}

function clearAiBadge(el) {
  const item = el.closest('.list-item');
  if (item) {
    delete item.dataset.aiGenerated;
    const badge = item.querySelector('.ai-badge');
    if (badge) badge.remove();
  }
}

// Coerce a constraint / card-request entry from disk into { text, source }.
// Accepts the legacy string shape and the current { text, source } object.
function _normalizeProvenanceItem(item) {
  if (item && typeof item === 'object' && !Array.isArray(item)) {
    const text = typeof item.text === 'string' ? item.text : '';
    const source = item.source === 'ai' ? 'ai' : 'human';
    return { text, source };
  }
  return { text: typeof item === 'string' ? item : '', source: 'human' };
}

// ---------------------------------------------------------------------------
// Collect form data
// ---------------------------------------------------------------------------

function collectThemeData() {
  const name = document.getElementById('set-name').value.trim();
  const code = (MtgaiState.setCode() || '').toUpperCase();
  const setSize = parseInt(document.getElementById('set-size').value, 10);
  const mechanicCount = parseInt(document.getElementById('mechanic-count').value, 10);
  const setting = document.getElementById('setting').value.trim();

  const constraints = [];
  document.querySelectorAll('#constraints-list .list-item').forEach(item => {
    const input = item.querySelector('input');
    if (!input) return;
    const val = input.value.trim();
    if (!val) return;
    const source = item.dataset.aiGenerated === 'true' ? 'ai' : 'human';
    constraints.push({ text: val, source });
  });

  const cardRequests = [];
  document.querySelectorAll('#card-requests-list .list-item').forEach(item => {
    const ta = item.querySelector('textarea');
    if (!ta) return;
    const val = ta.value.trim();
    if (!val) return;
    const source = item.dataset.aiGenerated === 'true' ? 'ai' : 'human';
    cardRequests.push({ text: val, source });
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
  if (!data.code || !/^[A-Z0-9]{2,5}$/.test(data.code)) {
    showToast('No active set selected. Use the top-bar picker to choose or create one.', 'error');
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
      MtgaiState.setSetCode(data.code);
      clearDraft();
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
// Load existing theme — native picker reads the JSON content client-side, so
// no server lookup or set-code typing is needed.
// ---------------------------------------------------------------------------

const _LOAD_FILE_MAX_BYTES = 5 * 1024 * 1024;

function loadExistingFromFile(event) {
  const input = event.target;
  const file = input.files && input.files[0];
  input.value = '';
  if (!file) return;

  if (file.size > _LOAD_FILE_MAX_BYTES) {
    showToast('File too large (>5 MB) to be a theme.json', 'error');
    return;
  }

  const reader = new FileReader();
  reader.onload = () => {
    let theme;
    try {
      theme = JSON.parse(reader.result.replace(/^﻿/, ''));
    } catch (err) {
      showToast('Could not parse JSON: ' + err.message, 'error');
      return;
    }
    if (!theme || typeof theme !== 'object' || Array.isArray(theme)) {
      showToast('File does not contain a theme object', 'error');
      return;
    }
    if (!theme.code && !theme.name) {
      showToast('File has no "code" or "name" field — not a theme.json', 'error');
      return;
    }
    populateFromTheme(theme);
    showToast(`Loaded ${theme.name || theme.code}`, 'success');
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
  // Streaming chunks land in the textarea — flip to edit mode so the user
  // can watch them arrive. The done handler swaps back to preview.
  setSettingMode('edit');
  progressBar.style.width = '10%';
  progressBar.classList.remove('indeterminate');
  progressStatus.textContent = 'Starting extraction...';
  resetPhaseBanner();
  showPhaseBanner('Starting extraction...');
  clearExtractionError('constraints-list');
  clearExtractionError('card-requests-list');

  const extractBtn = document.getElementById('run-extract-btn');
  extractBtn.disabled = true;
  if (cancelBtn) {
    cancelBtn.disabled = false;
    cancelBtn.textContent = 'Cancel Extraction';
  }

  // Snapshot regen-on-extraction toggles before we start streaming so a
  // user toggling them mid-run can't change behavior partway through.
  const regenC = document.getElementById('regen-constraints');
  const regenR = document.getElementById('regen-card-requests');
  const state = {
    gotDone: false,
    gotError: false,
    gotCancelled: false,
    regenConstraints: regenC ? regenC.checked : true,
    regenCardRequests: regenR ? regenR.checked : true,
  };

  try {
    const params = new URLSearchParams({ upload_id: _uploadId });
    const response = await fetch(`/api/pipeline/theme/extract-stream?${params}`);
    if (!response.ok) {
      if (response.status === 409) {
        const payload = await response.json().catch(() => null);
        showBusyToast(payload);
        progressStatus.textContent = 'Another AI action is running — try again when it finishes';
        return;
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
    progressBar.classList.remove('indeterminate');
    hidePhaseBanner();
    if (state.gotDone) {
      document.getElementById('extract-progress').classList.remove('visible');
    }
  }
}

function handleExtractionEvent(type, data, textarea, progressBar, progressStatus, state) {
  switch (type) {
    case 'status':
      progressStatus.textContent = data.message;
      // Phase events drive the bar now; the per-section heuristic stays
      // only as a fallback for older event streams or providers that
      // don't emit phase events. Skip it once phase telemetry has shown
      // up so the bar doesn't jump back to a coarse heuristic value.
      if (!_phaseDriving) {
        if (data.message.includes('Generating theme')) {
          progressBar.style.width = '30%';
        } else if (data.message.includes('constraints')) {
          progressBar.style.width = '80%';
        }
        const secMatch = data.message.match(/\((\d+)\/(\d+)\)/);
        if (secMatch) {
          const pct = 10 + (parseInt(secMatch[1]) / parseInt(secMatch[2])) * 65;
          progressBar.style.width = pct + '%';
        }
      }
      break;

    case 'phase':
      handlePhaseEvent(data, progressBar);
      break;

    case 'theme_chunk':
      textarea.value += data.text;
      textarea.scrollTop = textarea.scrollHeight;
      // Don't override phase-driven width during the generation phase —
      // the indeterminate stripe is the right indicator. Only nudge the
      // bar when we don't have phase telemetry to drive it.
      if (!_phaseDriving) {
        progressBar.style.width = '60%';
      }
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
        if (state && state.regenConstraints) clearAiItems('constraints-list');
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
        if (state && state.regenCardRequests) clearAiItems('card-requests-list');
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
      progressBar.classList.remove('indeterminate');
      hidePhaseBanner();
      progressStatus.textContent = `Extraction complete ($${data.total_cost_usd.toFixed(4)})`;
      showToast(`Extraction complete - $${data.total_cost_usd.toFixed(4)}`, 'success');
      // The textarea is full of fresh markdown; default back to preview
      // so the user sees structured prose, not raw # / **.
      setSettingMode('preview');
      break;

    case 'error':
      if (state) state.gotError = true;
      progressBar.classList.remove('indeterminate');
      hidePhaseBanner();
      progressStatus.textContent = 'Error: ' + (data.message || 'unknown error');
      if (data.log_path) {
        progressStatus.textContent += ' - log: ' + data.log_path;
      }
      showToast('Error: ' + data.message, 'error');
      break;

    case 'cancelled':
      if (state) state.gotCancelled = true;
      progressBar.classList.remove('indeterminate');
      hidePhaseBanner();
      progressStatus.textContent = 'Extraction cancelled';
      showToast('Extraction cancelled', 'success');
      break;
  }
}

// ---------------------------------------------------------------------------
// Live phase banner
// ---------------------------------------------------------------------------
//
// Driven by `phase` SSE events emitted from theme_extractor.py. The banner
// shows: activity label, elapsed time, and a real percent (structural
// section/chunk grid OR llamacpp prompt-eval n_prompt_tokens_processed /
// n_prompt_tokens). Once generation starts the bar switches to an
// indeterminate stripe + tok count + tok/s — total output tokens are
// unknown so a real percent doesn't exist.

let _phaseDriving = false; // suppresses the heuristic % math once phase data arrives

function resetPhaseBanner() {
  _phaseDriving = false;
  const banner = document.getElementById('phase-banner');
  if (!banner) return;
  banner.classList.remove('active', 'has-stats');
  document.getElementById('phase-activity').textContent = 'Starting extraction...';
  document.getElementById('phase-elapsed').textContent = '0s';
  document.getElementById('phase-stats').textContent = '';
}

function showPhaseBanner(activity) {
  const banner = document.getElementById('phase-banner');
  if (!banner) return;
  banner.classList.add('active');
  if (activity) {
    document.getElementById('phase-activity').textContent = activity;
  }
}

function hidePhaseBanner() {
  _phaseDriving = false;
  const banner = document.getElementById('phase-banner');
  if (!banner) return;
  banner.classList.remove('active', 'has-stats');
}

function handlePhaseEvent(data, progressBar) {
  _phaseDriving = true;
  const phase = data.phase || '';
  const activity = data.activity || '';
  showPhaseBanner(activity);
  const elapsedEl = document.getElementById('phase-elapsed');
  if (elapsedEl && typeof data.elapsed_s === 'number') {
    elapsedEl.textContent = formatElapsed(data.elapsed_s);
  }

  // Bar mode + width selection.
  // Priority: generation (indeterminate stripe) > prompt_eval (precise %)
  //         > structural (section/chunk grid %) > phase-kind defaults.
  const banner = document.getElementById('phase-banner');
  const stats = document.getElementById('phase-stats');
  if (!banner || !stats) return;

  if (phase === 'generation' && data.generation) {
    progressBar.classList.add('indeterminate');
    const tokens = data.generation.tokens || 0;
    const tps = data.generation.tok_per_sec || 0;
    stats.textContent = `${tokens.toLocaleString()} tok @ ${tps.toFixed(1)} tok/s`;
    banner.classList.add('has-stats');
    return;
  }

  // Non-generation phase: solid bar.
  progressBar.classList.remove('indeterminate');

  if (data.prompt_eval && data.prompt_eval.total > 0) {
    const pe = data.prompt_eval;
    const pct = Math.max(0, Math.min(100, (pe.processed / pe.total) * 100));
    progressBar.style.width = pct.toFixed(1) + '%';
    stats.textContent = `Prompt: ${pe.processed.toLocaleString()} / ${pe.total.toLocaleString()} tokens (${pct.toFixed(0)}%)`;
    banner.classList.add('has-stats');
    return;
  }

  if (data.structural && typeof data.structural.section_index === 'number'
      && typeof data.structural.section_total === 'number') {
    const s = data.structural;
    const sectionsDone = (s.section_index - 1);
    let sectionFrac = 0;
    if (typeof s.chunk_index === 'number' && typeof s.chunk_total === 'number' && s.chunk_total > 0) {
      sectionFrac = (s.chunk_index - 1) / s.chunk_total;
    }
    const overall = (sectionsDone + sectionFrac) / s.section_total;
    const pct = 5 + Math.max(0, Math.min(1, overall)) * 90;
    progressBar.style.width = pct.toFixed(1) + '%';
    let label = `Section ${s.section_index}/${s.section_total}`;
    if (typeof s.chunk_index === 'number' && typeof s.chunk_total === 'number') {
      label += ` · chunk ${s.chunk_index}/${s.chunk_total}`;
    }
    stats.textContent = label;
    banner.classList.add('has-stats');
    return;
  }

  // No structured data — clear stats but keep banner (activity label is enough).
  stats.textContent = '';
  banner.classList.remove('has-stats');

  // Phase-specific defaults so the bar moves on transitions even
  // without prompt-eval/structural data (e.g. Anthropic).
  if (phase === 'loading' || phase === 'counting') {
    progressBar.style.width = '5%';
  } else if (phase === 'json_subcall') {
    progressBar.style.width = '85%';
  } else if (phase === 'compacting') {
    progressBar.style.width = '50%';
  } else if (phase === 'extracting') {
    progressBar.style.width = '30%';
  } else if (phase === 'done') {
    progressBar.style.width = '100%';
  }
}

function formatElapsed(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return s + 's';
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}m ${r}s`;
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
  const settingText = document.getElementById('setting').value.trim();
  if (!settingText) {
    showToast('No setting text to extract constraints from', 'error');
    return;
  }

  await runSectionRefresh({
    kind: 'constraints',
    settingText,
    btnId: 'refresh-constraints',
    listId: 'constraints-list',
    retryFn: refreshConstraints,
    applyResult: (items) => {
      items.forEach(c => addConstraint(c, true));
    },
    successLabel: 'Constraints',
    emptyMessage: 'LLM returned no constraints for this setting',
  });
}

async function refreshCardRequests() {
  const settingText = document.getElementById('setting').value.trim();
  if (!settingText) {
    showToast('No setting text to extract card suggestions from', 'error');
    return;
  }

  await runSectionRefresh({
    kind: 'card_suggestions',
    settingText,
    btnId: 'refresh-card-requests',
    listId: 'card-requests-list',
    retryFn: refreshCardRequests,
    applyResult: (items) => {
      items.forEach(s => addCardRequest(`${s.name}: ${s.description}`, true));
    },
    successLabel: 'Card suggestions',
    emptyMessage: 'LLM returned no card suggestions for this setting',
  });
}

/**
 * Wipe the list in preparation for repopulation by a refresh result.
 * Removes only AI-tagged items if any are present (preserves user-added
 * entries); falls back to a full clear when nothing is tagged so a stale
 * post-load state still gets reset.
 */
function clearAiItems(listId) {
  const aiItems = document.querySelectorAll(`#${listId} .list-item[data-ai-generated="true"]`);
  if (aiItems.length > 0) {
    aiItems.forEach(el => el.remove());
  } else {
    document.getElementById(listId).innerHTML = '';
  }
}

/**
 * Shared section-refresh runner. Streams the SSE events from
 * /api/pipeline/theme/extract-section, dispatches phase ticks to the
 * same banner the full extraction uses, and applies the kind-specific
 * result events through the caller's `applyResult` callback.
 */
async function runSectionRefresh(opts) {
  const {
    kind, settingText, btnId, listId, retryFn,
    applyResult, successLabel, emptyMessage,
  } = opts;

  const btn = document.getElementById(btnId);
  btn.disabled = true;
  btn.textContent = 'Refreshing...';
  clearExtractionError(listId);

  // Show the same banner+bar the full extraction uses. Keep the cancel
  // button hidden — section refreshes are short and not user-cancellable.
  const progressEl = document.getElementById('extract-progress');
  const cancelBtn = document.getElementById('cancel-extract-btn');
  const progressBar = document.getElementById('progress-bar');
  const progressStatus = document.getElementById('progress-status');
  progressEl.classList.add('visible');
  if (cancelBtn) cancelBtn.style.display = 'none';
  resetPhaseBanner();
  showPhaseBanner(`Refreshing ${successLabel.toLowerCase()}...`);
  progressStatus.textContent = `Refreshing ${successLabel.toLowerCase()}...`;
  progressBar.style.width = '5%';

  let totalCost = 0;
  let collectedItems = null;
  let extractionError = null;
  let extractionRaw = '';
  let fatalError = null;

  try {
    const resp = await fetch('/api/pipeline/theme/extract-section', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme_text: settingText, kind }),
    });
    if (resp.status === 409) {
      const payload = await resp.json().catch(() => null);
      showBusyToast(payload);
      return;
    }
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      const msg = data.error || data.detail || `HTTP ${resp.status}`;
      showExtractionError(listId, msg, '', { label: 'Retry', fn: retryFn });
      showToast('Refresh failed: ' + msg + ' (try Ctrl+Shift+R if stale)', 'error');
      return;
    }

    // Server accepted the request — only now clear the existing items so
    // a 409 (busy) doesn't leave the user with an empty list.
    clearAiItems(listId);

    const reader = resp.body.getReader();
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
        let eventType = null;
        let eventData = null;
        for (const line of part.split('\n')) {
          if (line.startsWith('event: ')) eventType = line.slice(7).trim();
          else if (line.startsWith('data: ')) {
            try { eventData = JSON.parse(line.slice(6)); } catch (e) { /* skip */ }
          }
        }
        if (!eventType || !eventData) continue;

        switch (eventType) {
          case 'phase':
            handlePhaseEvent(eventData, progressBar);
            break;
          case 'status':
            progressStatus.textContent = eventData.message || progressStatus.textContent;
            break;
          case 'constraints':
            collectedItems = Array.isArray(eventData.constraints) ? eventData.constraints : [];
            break;
          case 'card_suggestions':
            collectedItems = Array.isArray(eventData.suggestions) ? eventData.suggestions : [];
            break;
          case 'constraints_error':
          case 'suggestions_error':
            extractionError = eventData.message || 'Extraction failed';
            extractionRaw = eventData.raw || '';
            break;
          case 'done':
            totalCost = eventData.cost_usd || 0;
            break;
          case 'error':
            if (eventData.busy) {
              showBusyToast(eventData);
              fatalError = '__busy__';
            } else {
              fatalError = eventData.message || 'unknown error';
            }
            break;
          case 'cancelled':
            fatalError = 'cancelled';
            break;
        }
      }
    }
  } catch (err) {
    fatalError = err.message;
    console.error('[theme.js] Refresh failed:', err);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Refresh AI';
    progressBar.classList.remove('indeterminate');
    hidePhaseBanner();
    progressEl.classList.remove('visible');
    if (cancelBtn) cancelBtn.style.display = '';
  }

  if (fatalError === '__busy__') {
    return; // Toast already shown.
  }
  if (fatalError) {
    showExtractionError(listId, fatalError, '', { label: 'Retry', fn: retryFn });
    showToast('Refresh failed: ' + fatalError, 'error');
    return;
  }
  if (extractionError) {
    showExtractionError(listId, extractionError, extractionRaw,
      { label: 'Retry', fn: retryFn });
    showToast(`${successLabel} extraction failed`, 'error');
    return;
  }
  const items = collectedItems || [];
  applyResult(items);
  if (items.length === 0) {
    showToast(emptyMessage, 'warn');
  } else {
    showToast(`${successLabel} refreshed ($${totalCost.toFixed(4)})`, 'success');
  }
}

// ---------------------------------------------------------------------------
// Toast notifications
// ---------------------------------------------------------------------------

function showToast(message, type, durationMs) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.className = `toast toast-${type} show`;
  setTimeout(() => toast.classList.remove('show'), durationMs || 3000);
}

/**
 * Show the shared "AI is busy" toast.
 *
 * Reads `{running_action, started_at, log_path}` from a 409 response body
 * (or from /api/ai/status) and formats it into a one-liner the user can
 * scan, e.g.
 *
 *   "Theme extraction running since 12:14:32 — please wait or cancel it"
 *
 * The wording is intentionally generic ("cancel it" rather than naming
 * a specific button) because the active action and the action being
 * rejected aren't always the same — e.g. the user clicks "Refresh AI"
 * on Set Constraints while a Theme extraction is in flight.
 *
 * Falls back to a generic message if the body is malformed (e.g. a 409
 * came back from a path that hasn't been migrated to the shared payload).
 */
function showBusyToast(payload) {
  const action = payload && payload.running_action;
  const startedAt = payload && payload.started_at;
  let msg;
  if (action && startedAt) {
    const t = new Date(startedAt);
    const hh = String(t.getHours()).padStart(2, '0');
    const mm = String(t.getMinutes()).padStart(2, '0');
    const ss = String(t.getSeconds()).padStart(2, '0');
    msg = `${action} running since ${hh}:${mm}:${ss} — please wait or cancel it`;
  } else {
    msg = 'Another AI action is already running — please wait or cancel it first';
  }
  showToast(msg, 'warn', 6000);
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
  if (text == null || text === '') return '';
  if (typeof text !== 'string') text = String(text);
  return text.replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ---------------------------------------------------------------------------
// Draft persistence — every edit writes to localStorage so tab-switch and
// reload don't lose work. Save-Theme clears the draft (theme.json is now
// the canonical copy).
// ---------------------------------------------------------------------------

let _draftPersistTimer = null;

function persistDraft() {
  const data = collectThemeData();
  data._draft_saved_at = Date.now();
  if (data.code) {
    MtgaiState.setSetCode(data.code);
  }
  MtgaiState.set('theme_draft', data);
}

function schedulePersistDraft() {
  if (_draftPersistTimer) clearTimeout(_draftPersistTimer);
  _draftPersistTimer = setTimeout(persistDraft, 250);
}

function clearDraft() {
  MtgaiState.remove('theme_draft');
}

function wireDraftPersistence() {
  // Capture every input/textarea change inside the page. Lists are
  // re-rendered dynamically by addConstraint / addCardRequest, so we
  // delegate from document instead of binding to the current nodes.
  document.addEventListener('input', (e) => {
    if (!e.target || !e.target.closest('.theme-page')) return;
    schedulePersistDraft();
  });
}

// ---------------------------------------------------------------------------
// Reattach an in-flight extraction
// ---------------------------------------------------------------------------

async function reattachExtraction(uploadId) {
  if (!uploadId) return;
  document.getElementById('extract-progress').classList.add('visible');

  const progressBar = document.getElementById('progress-bar');
  const progressStatus = document.getElementById('progress-status');
  const cancelBtn = document.getElementById('cancel-extract-btn');
  const textarea = document.getElementById('setting');

  progressBar.style.width = '5%';
  progressStatus.textContent = 'Reattaching to running extraction...';
  if (cancelBtn) {
    cancelBtn.disabled = false;
    cancelBtn.textContent = 'Cancel Extraction';
  }

  // Reset the textarea so replayed theme_chunk events rebuild it cleanly.
  textarea.value = '';
  setSettingMode('edit');

  // Reattach mirrors a fresh-start visual: the SSE replay will re-emit
  // every constraints/card_suggestions event the worker produced, so we
  // clear AI-tagged items by default to avoid duplicating them on top
  // of whatever the live tab already had.
  const state = {
    gotDone: false,
    gotError: false,
    gotCancelled: false,
    regenConstraints: true,
    regenCardRequests: true,
  };

  try {
    const params = new URLSearchParams({ upload_id: uploadId });
    const response = await fetch(`/api/pipeline/theme/extract-stream?${params}`);
    if (!response.ok) {
      progressStatus.textContent = 'Reattach failed: HTTP ' + response.status;
      return;
    }
    await consumeExtractionStream(response, textarea, progressBar, progressStatus, state);
  } catch (err) {
    progressStatus.textContent = 'Reattach error: ' + err.message;
    console.error('[theme.js] Reattach failed:', err);
  } finally {
    if (cancelBtn) cancelBtn.disabled = true;
    if (state.gotDone) {
      document.getElementById('extract-progress').classList.remove('visible');
    }
  }
}

async function consumeExtractionStream(response, textarea, progressBar, progressStatus, state) {
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
}
