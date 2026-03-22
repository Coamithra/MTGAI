/**
 * Settings page — model assignment dropdowns, presets, profile save/load.
 *
 * Expects globals set by the template:
 *   MODEL_REGISTRY  — { llm: {key: {...}}, image: {key: {...}} }
 *   CURRENT_SETTINGS — { llm_assignments: {...}, image_assignments: {...}, effort_overrides: {...} }
 *   SAVED_PROFILES   — ["profile-name", ...]
 *   LLM_STAGES       — { stage_id: "Stage Name", ... }
 *   IMAGE_STAGES     — { stage_id: "Stage Name", ... }
 *   PRESETS          — { name: { llm: {...}, image: {...}, effort: {...} }, ... }
 */

// ---------------------------------------------------------------------------
// Cost estimates per stage (rough token usage for a 60-card set)
// ---------------------------------------------------------------------------

// Approximate input+output tokens per stage for a 60-card dev set.
// Calibrated from actual ASD pipeline runs (~$13 total with caching).
// These are PRE-caching estimates; actual cost is ~30-50% lower with caching.
const STAGE_TOKEN_ESTIMATES = {
  reprints:     { input: 10_000,   output: 2_000 },
  card_gen:     { input: 200_000,  output: 30_000 },
  balance:      { input: 50_000,   output: 10_000 },
  skeleton_rev: { input: 50_000,   output: 15_000 },
  ai_review:    { input: 400_000,  output: 80_000 },
  art_prompts:  { input: 30_000,   output: 10_000 },
  art_select:   { input: 50_000,   output: 5_000 },
};

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  renderLLMAssignments();
  renderImageAssignments();
  renderProfileList();
  updateCostEstimate();
});

// ---------------------------------------------------------------------------
// LLM assignment table
// ---------------------------------------------------------------------------

function renderLLMAssignments() {
  const tbody = document.getElementById('llm-assignments-body');
  if (!tbody) return;

  const stageIds = Object.keys(LLM_STAGES);
  const llmModels = MODEL_REGISTRY.llm;

  tbody.innerHTML = stageIds.map(stageId => {
    const stageName = LLM_STAGES[stageId];
    const currentKey = CURRENT_SETTINGS.llm_assignments[stageId] || '';
    const effort = CURRENT_SETTINGS.effort_overrides[stageId] || '';
    const currentModel = llmModels[currentKey];

    // Build dropdown options sorted by tier (highest first)
    const sorted = Object.entries(llmModels)
      .sort((a, b) => b[1].tier - a[1].tier);

    const options = sorted.map(([key, model]) => {
      const price = model.input_price > 0
        ? `$${model.input_price.toFixed(2)}/$${model.output_price.toFixed(2)}`
        : 'Free';
      const selected = key === currentKey ? 'selected' : '';
      const visionTag = model.supports_vision ? ' [vision]' : '';
      return `<option value="${key}" ${selected}>${escapeHtml(model.name)}${visionTag} — ${price}</option>`;
    }).join('');

    // Effort dropdown (only enabled if model supports it)
    const supportsEffort = currentModel && currentModel.supports_effort;

    return `
      <tr>
        <td>
          ${escapeHtml(stageName)}
          ${stageId === 'art_select' ? '<span class="tag tag-vision">vision</span>' : ''}
        </td>
        <td>
          <select class="model-select" data-stage="${stageId}" data-type="llm"
                  onchange="onModelChange(this)">
            ${options}
          </select>
        </td>
        <td>
          <select class="effort-select" data-stage="${stageId}" data-type="effort"
                  ${supportsEffort ? '' : 'disabled'}
                  onchange="onEffortChange(this)">
            <option value="" ${!effort ? 'selected' : ''}>—</option>
            <option value="low" ${effort === 'low' ? 'selected' : ''}>Low</option>
            <option value="high" ${effort === 'high' ? 'selected' : ''}>High</option>
            <option value="max" ${effort === 'max' ? 'selected' : ''}>Max</option>
          </select>
        </td>
        <td style="color: #888; font-size: 0.8rem">
          <span class="stage-cost" data-stage="${stageId}">
            ${currentModel ? formatPrice(currentModel) : '—'}
          </span>
        </td>
      </tr>
    `;
  }).join('');
}

function formatPrice(model) {
  if (model.input_price === 0 && model.output_price === 0) {
    return '<span style="color: #2ecc71">Free</span>';
  }
  return `$${model.input_price.toFixed(2)}`;
}

// ---------------------------------------------------------------------------
// Image assignment table
// ---------------------------------------------------------------------------

function renderImageAssignments() {
  const tbody = document.getElementById('image-assignments-body');
  if (!tbody) return;

  const stageIds = Object.keys(IMAGE_STAGES);
  const imageModels = MODEL_REGISTRY.image;

  tbody.innerHTML = stageIds.map(stageId => {
    const stageName = IMAGE_STAGES[stageId];
    const currentKey = CURRENT_SETTINGS.image_assignments[stageId] || '';

    const options = Object.entries(imageModels).map(([key, model]) => {
      const selected = key === currentKey ? 'selected' : '';
      const cost = model.cost_per_image > 0
        ? `$${model.cost_per_image.toFixed(3)}`
        : 'Free';
      const impl = model.implemented ? '' : ' (not yet implemented)';
      return `<option value="${key}" ${selected} ${model.implemented ? '' : 'disabled'}>${escapeHtml(model.name)}${impl} — ${cost}</option>`;
    }).join('');

    const currentModel = imageModels[currentKey];

    return `
      <tr>
        <td>${escapeHtml(stageName)}</td>
        <td>
          <select class="model-select" data-stage="${stageId}" data-type="image"
                  onchange="onImageModelChange(this)">
            ${options}
          </select>
        </td>
        <td style="color: #888; font-size: 0.8rem">
          ${currentModel
            ? (currentModel.cost_per_image > 0
              ? `$${currentModel.cost_per_image.toFixed(3)}`
              : '<span style="color: #2ecc71">Free</span>')
            : '—'}
        </td>
      </tr>
    `;
  }).join('');
}

// ---------------------------------------------------------------------------
// Change handlers
// ---------------------------------------------------------------------------

function onModelChange(select) {
  const stageId = select.dataset.stage;
  const modelKey = select.value;
  const model = MODEL_REGISTRY.llm[modelKey];

  // Update current settings
  CURRENT_SETTINGS.llm_assignments[stageId] = modelKey;

  // Update effort dropdown enabled state
  const effortSelect = document.querySelector(
    `select.effort-select[data-stage="${stageId}"]`
  );
  if (effortSelect) {
    effortSelect.disabled = !model || !model.supports_effort;
    if (!model || !model.supports_effort) {
      effortSelect.value = '';
      delete CURRENT_SETTINGS.effort_overrides[stageId];
    }
  }

  // Update cost display
  const costSpan = document.querySelector(`.stage-cost[data-stage="${stageId}"]`);
  if (costSpan && model) {
    costSpan.innerHTML = formatPrice(model);
  }

  clearActivePreset();
  updateCostEstimate();
}

function onEffortChange(select) {
  const stageId = select.dataset.stage;
  const value = select.value;

  if (value) {
    CURRENT_SETTINGS.effort_overrides[stageId] = value;
  } else {
    delete CURRENT_SETTINGS.effort_overrides[stageId];
  }

  clearActivePreset();
}

function onImageModelChange(select) {
  const stageId = select.dataset.stage;
  CURRENT_SETTINGS.image_assignments[stageId] = select.value;
  clearActivePreset();
}

// ---------------------------------------------------------------------------
// Presets
// ---------------------------------------------------------------------------

function applyPreset(presetName) {
  const preset = PRESETS[presetName];
  if (!preset) return;

  // Update settings
  CURRENT_SETTINGS.llm_assignments = { ...preset.llm };
  CURRENT_SETTINGS.image_assignments = { ...preset.image };
  CURRENT_SETTINGS.effort_overrides = { ...(preset.effort || {}) };

  // Re-render
  renderLLMAssignments();
  renderImageAssignments();
  updateCostEstimate();

  // Update preset button styling
  document.querySelectorAll('.preset-btn').forEach(btn => {
    const btnPreset = btn.getAttribute('onclick').match(/applyPreset\('(.+?)'\)/);
    btn.classList.toggle('active', btnPreset && btnPreset[1] === presetName);
  });
}

function clearActivePreset() {
  document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.classList.remove('active');
  });
}

// ---------------------------------------------------------------------------
// Cost estimation
// ---------------------------------------------------------------------------

function updateCostEstimate() {
  const llmModels = MODEL_REGISTRY.llm;
  let totalCost = 0;
  let details = [];

  for (const [stageId, tokens] of Object.entries(STAGE_TOKEN_ESTIMATES)) {
    const modelKey = CURRENT_SETTINGS.llm_assignments[stageId];
    const model = llmModels[modelKey];
    if (!model) continue;

    const inputCost = (tokens.input * model.input_price) / 1_000_000;
    const outputCost = (tokens.output * model.output_price) / 1_000_000;
    const stageCost = inputCost + outputCost;
    totalCost += stageCost;
  }

  const costEl = document.getElementById('cost-estimate');
  const detailEl = document.getElementById('cost-detail');

  if (costEl) {
    if (totalCost === 0) {
      costEl.textContent = '$0.00 (local models)';
      costEl.style.color = '#2ecc71';
    } else {
      costEl.textContent = `~$${totalCost.toFixed(2)}`;
      costEl.style.color = '#4a9eff';
    }
  }

  if (detailEl) {
    detailEl.textContent = totalCost > 0
      ? 'Pre-caching estimate \u2014 actual cost typically 30-50% lower'
      : '';
  }
}

// ---------------------------------------------------------------------------
// Profile save/load
// ---------------------------------------------------------------------------

function renderProfileList() {
  const select = document.getElementById('profile-select');
  if (!select) return;

  select.innerHTML = '<option value="">Load a profile...</option>';
  SAVED_PROFILES.forEach(name => {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name;
    select.appendChild(opt);
  });
}

async function saveProfile() {
  const nameInput = document.getElementById('profile-name');
  const name = nameInput.value.trim();
  if (!name) {
    showToast('Enter a profile name first', 'error');
    nameInput.focus();
    return;
  }

  // Sanitize name
  const safeName = name.replace(/[^a-zA-Z0-9_-]/g, '-').toLowerCase();

  try {
    const resp = await fetch('/api/settings/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: safeName,
        settings: CURRENT_SETTINGS,
      }),
    });
    const data = await resp.json();

    if (data.success) {
      showToast(`Saved profile "${safeName}"`, 'success');
      // Add to profile list if new
      if (!SAVED_PROFILES.includes(safeName)) {
        SAVED_PROFILES.push(safeName);
        renderProfileList();
      }
      nameInput.value = '';
    } else {
      showToast('Error: ' + (data.error || 'Unknown'), 'error');
    }
  } catch (err) {
    showToast('Network error: ' + err.message, 'error');
  }
}

async function loadProfile() {
  const select = document.getElementById('profile-select');
  const name = select.value;
  if (!name) {
    showToast('Select a profile first', 'error');
    return;
  }

  try {
    const resp = await fetch(`/api/settings/load?name=${encodeURIComponent(name)}`);
    const data = await resp.json();

    if (data.settings) {
      Object.assign(CURRENT_SETTINGS, data.settings);
      renderLLMAssignments();
      renderImageAssignments();
      updateCostEstimate();
      clearActivePreset();
      showToast(`Loaded profile "${name}"`, 'success');
    } else {
      showToast('Error: ' + (data.error || 'Profile not found'), 'error');
    }
  } catch (err) {
    showToast('Network error: ' + err.message, 'error');
  }
}

// ---------------------------------------------------------------------------
// Apply settings (save as current + activate)
// ---------------------------------------------------------------------------

async function applySettings() {
  try {
    const resp = await fetch('/api/settings/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(CURRENT_SETTINGS),
    });
    const data = await resp.json();

    if (data.success) {
      showToast('Settings applied', 'success');
    } else {
      showToast('Error: ' + (data.error || 'Unknown'), 'error');
    }
  } catch (err) {
    showToast('Network error: ' + err.message, 'error');
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

  setTimeout(() => {
    toast.classList.remove('show');
  }, 3000);
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
