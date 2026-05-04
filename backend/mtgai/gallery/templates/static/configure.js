/**
 * Configuration page — form logic, preset buttons, pipeline start.
 *
 * Expects STAGE_DEFINITIONS to be set as a global variable by the template.
 */

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

// Which stages to recommend for review mode
const RECOMMENDED_REVIEW = ['balance', 'skeleton_rev', 'ai_review', 'art_select'];

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', async () => {
  renderStageToggles();

  // Hydrate set identity from runtime state, then layer in any saved
  // localStorage values for stage toggles. Falls back to the
  // 'recommended' preset if nothing is saved.
  const state = await MtgaiState.fetchRuntimeState();
  if (state) {
    if (state.active_set) {
      MtgaiState.setSetCode(state.active_set);
      const display = document.getElementById('active-set-display');
      if (display) display.textContent = state.active_set;
    }
    if (state.theme) {
      const nameEl = document.getElementById('set-name');
      if (nameEl && !nameEl.value && state.theme.name) {
        nameEl.value = state.theme.name;
      }
      const sizeEl = document.getElementById('set-size');
      if (sizeEl && state.theme.set_size) {
        sizeEl.value = state.theme.set_size;
      }
    }
  }

  hydrateConfigureUiFromStorage();
  wireConfigurePersistence();
});

function hydrateConfigureUiFromStorage() {
  const preset = MtgaiState.get('configure.preset', 'recommended');
  applyPreset(preset);

  const stages = MtgaiState.get('configure.stages', null);
  if (stages && typeof stages === 'object') {
    Object.entries(stages).forEach(([stageId, mode]) => {
      const radio = document.getElementById(`${stageId}-${mode}`);
      if (radio) radio.checked = true;
    });
  }
}

function persistConfigureUi() {
  const stages = {};
  STAGE_DEFINITIONS.forEach((stage) => {
    if (stage.always_review) return;
    const selected = document.querySelector(
      `input[name="stage-${stage.stage_id}"]:checked`
    );
    if (selected) stages[stage.stage_id] = selected.value;
  });
  MtgaiState.set('configure.stages', stages);
}

function wireConfigurePersistence() {
  document.querySelectorAll('input[type="radio"]').forEach((r) => {
    r.addEventListener('change', persistConfigureUi);
  });
  document.querySelectorAll('input[type="text"], input[type="number"]').forEach((el) => {
    el.addEventListener('input', persistConfigureUi);
  });
  document.querySelectorAll('.preset-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      // Read the preset key from data-preset (set in configure.html)
      // — parsing the visible label would silently break if a copy
      // change ever renames a button.
      const preset = btn.dataset.preset || 'recommended';
      MtgaiState.set('configure.preset', preset);
      // applyPreset runs from the inline onclick handler; persist the
      // stage mapping after it lands.
      setTimeout(persistConfigureUi, 0);
    });
  });
}

// ---------------------------------------------------------------------------
// Stage toggle table
// ---------------------------------------------------------------------------

function renderStageToggles() {
  const tbody = document.getElementById('stage-toggles-body');
  if (!tbody) return;

  tbody.innerHTML = STAGE_DEFINITIONS.map((stage, i) => {
    const num = i + 1;
    const locked = stage.always_review;
    const notEligible = !stage.review_eligible && !stage.always_review;

    return `
      <tr class="${locked ? 'locked' : ''}" data-stage-id="${stage.stage_id}">
        <td style="color: #666">${num}</td>
        <td>${escapeHtml(stage.display_name)}${locked ? ' <span style="color: #ffa502; font-size: 0.7rem">(always)</span>' : ''}</td>
        <td>
          <div class="toggle-group">
            ${locked ? `
              <span style="color: #ffa502; font-size: 0.8rem">Review</span>
            ` : notEligible ? `
              <input type="radio" name="stage-${stage.stage_id}" value="auto" id="${stage.stage_id}-auto" checked>
              <label for="${stage.stage_id}-auto">Auto</label>
              <input type="radio" name="stage-${stage.stage_id}" value="skip" id="${stage.stage_id}-skip">
              <label for="${stage.stage_id}-skip">Skip</label>
            ` : `
              <input type="radio" name="stage-${stage.stage_id}" value="auto" id="${stage.stage_id}-auto">
              <label for="${stage.stage_id}-auto">Auto</label>
              <input type="radio" name="stage-${stage.stage_id}" value="review" id="${stage.stage_id}-review">
              <label for="${stage.stage_id}-review">Review</label>
              <input type="radio" name="stage-${stage.stage_id}" value="skip" id="${stage.stage_id}-skip">
              <label for="${stage.stage_id}-skip">Skip</label>
            `}
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

// ---------------------------------------------------------------------------
// Presets
// ---------------------------------------------------------------------------

function applyPreset(preset) {
  // Update active preset button — match against `data-preset` instead
  // of the visible label so a copy change doesn't break the selector.
  document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.preset === preset);
  });

  STAGE_DEFINITIONS.forEach(stage => {
    if (stage.always_review) return;  // Can't change human review stages

    let value;
    switch (preset) {
      case 'auto':
        value = 'auto';
        break;
      case 'review':
        value = stage.review_eligible ? 'review' : 'auto';
        break;
      case 'recommended':
        value = RECOMMENDED_REVIEW.includes(stage.stage_id) ? 'review' : 'auto';
        break;
      default:
        value = 'auto';
    }

    const radio = document.getElementById(`${stage.stage_id}-${value}`);
    if (radio) radio.checked = true;
  });
}

// ---------------------------------------------------------------------------
// Start pipeline
// ---------------------------------------------------------------------------

async function startPipeline() {
  const setName = document.getElementById('set-name').value.trim();
  const setCode = (MtgaiState.setCode() || '').toUpperCase();
  const setSize = parseInt(document.getElementById('set-size').value, 10);

  // Validation
  if (!setName) {
    alert('Please enter a set name.');
    document.getElementById('set-name').focus();
    return;
  }
  if (!setCode || !/^[A-Z0-9]{2,5}$/.test(setCode)) {
    alert('No active set selected. Use the top-bar picker to choose or create one.');
    return;
  }
  if (!setSize || setSize < 20 || setSize > 400) {
    alert('Set size must be between 20 and 400.');
    document.getElementById('set-size').focus();
    return;
  }

  // Collect stage review modes
  const stageReviewModes = {};
  const skipStages = [];

  STAGE_DEFINITIONS.forEach(stage => {
    if (stage.always_review) return;

    const selected = document.querySelector(
      `input[name="stage-${stage.stage_id}"]:checked`
    );
    if (selected) {
      if (selected.value === 'skip') {
        skipStages.push(stage.stage_id);
      } else {
        stageReviewModes[stage.stage_id] = selected.value;
      }
    }
  });

  const config = {
    set_code: setCode,
    set_name: setName,
    set_size: setSize,
    stage_review_modes: stageReviewModes,
    skip_stages: skipStages,
  };

  // Disable button
  const btn = document.getElementById('start-btn');
  btn.disabled = true;
  btn.textContent = 'Starting...';

  try {
    const resp = await fetch('/api/pipeline/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    const data = await resp.json();

    if (data.success) {
      window.location.href = '/pipeline';
    } else {
      alert('Error: ' + (data.error || 'Unknown error'));
      btn.disabled = false;
      btn.textContent = 'Start Pipeline';
    }
  } catch (err) {
    alert('Network error: ' + err.message);
    btn.disabled = false;
    btn.textContent = 'Start Pipeline';
  }
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
