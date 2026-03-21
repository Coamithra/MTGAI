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

document.addEventListener('DOMContentLoaded', () => {
  renderStageToggles();
  applyPreset('recommended');  // Default to recommended preset
});

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
  // Update active preset button
  document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.classList.toggle('active', btn.textContent.toLowerCase().includes(preset));
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
  const setCode = document.getElementById('set-code').value.trim().toUpperCase();
  const setSize = parseInt(document.getElementById('set-size').value, 10);

  // Validation
  if (!setName) {
    alert('Please enter a set name.');
    document.getElementById('set-name').focus();
    return;
  }
  if (!setCode || setCode.length < 2 || setCode.length > 3) {
    alert('Please enter a 2-3 letter set code.');
    document.getElementById('set-code').focus();
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
