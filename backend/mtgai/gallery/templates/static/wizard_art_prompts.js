/**
 * Wizard Art Prompts tab — displays the Flux art prompt generated for each
 * card by ``mtgai.art.prompt_builder.generate_prompts_for_set()``.
 *
 * The field that stores the generated prompt on a card is ``art_prompt``
 * (from ``mtgai/models/card.py`` line 117 — top-level Card field, also on
 * CardFace for DFCs).
 *
 * ``art_prompts`` is NOT ``review_eligible`` — the engine never pauses here
 * automatically. Footer is always a ``wiz-footer-note``; no advance button.
 *
 * Conventions:
 *   §1  no advance button (stage is not review-eligible)
 *   §3  locked while stage is running (display-only; no editable fields)
 *   §6  past-tab: read-only
 *   §8  status pill driven by wizard_stage.js
 *   §9  "Stop after this step" handled by wizard_stage.js
 *   §13 NO section-level Refresh AI: this stage processes every card in the
 *       cards/ dir and the server side is the only thing that can drive it —
 *       the user advances past the prior stage to trigger it. A "Re-run"
 *       button would silently skip already-prompted cards; we omit it and let
 *       the user re-run the stage from the engine if needed.
 *
 * Registers via ``W.registerStageRenderer('art_prompts', render)``.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'art_prompts';

  // Rarity display order for the grouping UI
  const RARITY_ORDER = ['mythic', 'rare', 'uncommon', 'common', 'special', 'bonus'];

  const local = {
    initialized:  false,
    cards:        [],    // [{ name, collector_number, type_line, rarity, art_prompt, colors, card_faces }]
    hasContent:   false,
    processed:    0,
    skipped:      0,
    costUsd:      0,
    modelId:      '',
    stageStatus:  'pending',
    locked:       false,
    bootstrapping: false,
    // UI state
    filter:       '',    // free-text filter for card name / prompt
    groupBy:      'rarity', // 'rarity' | 'none'
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ---------------------------------------------------------------------------
  // Top-level render
  // ---------------------------------------------------------------------------

  function render({ root, state, stage, content, footer }) {
    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      bootstrap(root, state).catch(err => {
        W.toast('Failed to load art prompts: ' + err.message, 'error');
      });
      paintFooter(footer, state);
      return;
    }

    const prevStatus = local.stageStatus;
    if (stage) local.stageStatus = stage.status;

    const justFinished =
      stage
      && prevStatus !== local.stageStatus
      && local.stageStatus !== 'pending'
      && local.stageStatus !== 'running'
      && !local.hasContent
      && !local.bootstrapping;
    if (justFinished) {
      local.bootstrapping = true;
      bootstrap(root, state)
        .catch(err => W.toast('Failed to refresh art prompts: ' + err.message, 'error'))
        .finally(() => { local.bootstrapping = false; });
      return;
    }
    paintFooter(footer, state);
  }

  function mountShellHtml() {
    return `
      <div class="wiz-ap-summary" data-role="ap-summary">
        <div class="wiz-stage-empty">Loading art prompts…</div>
      </div>
      <div class="wiz-ap-controls" data-role="ap-controls" style="display:none"></div>
      <div class="wiz-ap-list" data-role="ap-list"></div>
    `;
  }

  // ---------------------------------------------------------------------------
  // Bootstrap — pull card art prompts from the server
  // ---------------------------------------------------------------------------

  async function bootstrap(root, state) {
    let data = null;
    try {
      // TODO: implement GET /api/wizard/art_prompts/state on the server.
      // Expected response shape:
      //   {
      //     has_content: bool,
      //     cards: [{ name, collector_number, type_line, rarity, art_prompt,
      //               colors, card_faces: [{name, art_prompt}] | null }],
      //     processed: int,
      //     skipped: int,
      //     cost_usd: float,
      //     model_id: str,
      //     stage_status: str,
      //   }
      const resp = await fetch('/api/wizard/art_prompts/state');
      if (resp.ok) {
        data = await resp.json().catch(() => null);
      } else if (resp.status === 404) {
        data = null; // endpoint not yet wired — degrade gracefully
      } else {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${resp.status}`);
      }
    } catch (err) {
      data = null;
    }

    if (data) {
      local.cards       = Array.isArray(data.cards) ? data.cards : [];
      local.hasContent  = !!data.has_content;
      local.processed   = data.processed || 0;
      local.skipped     = data.skipped || 0;
      local.costUsd     = data.cost_usd || 0;
      local.modelId     = data.model_id || '';
      local.stageStatus = data.stage_status || local.stageStatus;
    }

    paintSummary(root, state);
    paintControls(root);
    paintList(root);
    paintFooter(getFooter(root), state);
  }

  // ---------------------------------------------------------------------------
  // Summary block
  // ---------------------------------------------------------------------------

  function paintSummary(root, state) {
    const slot = root.querySelector('[data-role="ap-summary"]');
    if (!slot) return;

    const generating = local.stageStatus === 'running' || local.locked;

    if (!local.hasContent) {
      slot.innerHTML = generating
        ? '<div class="wiz-stage-empty">Generating art prompts…</div>'
        : '<div class="wiz-stage-empty">No art prompts yet. Advance from Visual References to generate them.</div>';
      return;
    }

    const costLabel = local.costUsd > 0 ? '$' + local.costUsd.toFixed(3) : '—';
    slot.innerHTML = `
      <dl class="wiz-stage-summary">
        <dt>Processed</dt><dd>${escHtml(String(local.processed))} cards</dd>
        <dt>Skipped</dt><dd>${escHtml(String(local.skipped))} (already had a prompt)</dd>
        <dt>Cost</dt><dd>${escHtml(costLabel)}</dd>
        ${local.modelId ? `<dt>Model</dt><dd>${escHtml(local.modelId)}</dd>` : ''}
      </dl>
    `;
  }

  // ---------------------------------------------------------------------------
  // Controls — filter + group-by (only shown when there are cards to browse)
  // ---------------------------------------------------------------------------

  function paintControls(root) {
    const slot = root.querySelector('[data-role="ap-controls"]');
    if (!slot) return;
    if (!local.hasContent || local.cards.length === 0) {
      slot.style.display = 'none';
      return;
    }
    slot.style.display = 'flex';
    // Only repaint if not already mounted to avoid clobbering the user's
    // in-progress filter text.
    if (slot.dataset.mounted === '1') return;
    slot.dataset.mounted = '1';
    slot.innerHTML = `
      <input type="search" class="wiz-ap-filter" data-role="ap-filter"
             placeholder="Filter by name or prompt text…" value="${escAttr(local.filter)}">
      <label class="wiz-ap-group-label">
        <input type="checkbox" data-role="ap-group-rarity" ${local.groupBy === 'rarity' ? 'checked' : ''}>
        Group by rarity
      </label>
    `;
    const filterInput = slot.querySelector('[data-role="ap-filter"]');
    if (filterInput) {
      filterInput.addEventListener('input', () => {
        local.filter = filterInput.value;
        paintList(root);
      });
    }
    const groupCb = slot.querySelector('[data-role="ap-group-rarity"]');
    if (groupCb) {
      groupCb.addEventListener('change', () => {
        local.groupBy = groupCb.checked ? 'rarity' : 'none';
        paintList(root);
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Card list
  // ---------------------------------------------------------------------------

  function paintList(root) {
    const slot = root.querySelector('[data-role="ap-list"]');
    if (!slot) return;
    if (!local.hasContent || local.cards.length === 0) {
      slot.innerHTML = '';
      return;
    }

    const q = local.filter.trim().toLowerCase();
    const visible = q
      ? local.cards.filter(c =>
          (c.name || '').toLowerCase().includes(q)
          || (c.art_prompt || '').toLowerCase().includes(q)
          || (c.collector_number || '').toLowerCase().includes(q)
        )
      : local.cards;

    if (visible.length === 0) {
      slot.innerHTML = `<div class="wiz-stage-empty">No cards match "${escHtml(q)}".</div>`;
      return;
    }

    if (local.groupBy === 'rarity') {
      const groups = {};
      visible.forEach(c => {
        const r = (c.rarity || 'common').toLowerCase();
        if (!groups[r]) groups[r] = [];
        groups[r].push(c);
      });
      const html = RARITY_ORDER
        .filter(r => groups[r] && groups[r].length > 0)
        .map(r => `
          <div class="wiz-ap-group">
            <div class="wiz-ap-group-header wiz-ap-rarity-${escAttr(r)}">
              ${escHtml(r.charAt(0).toUpperCase() + r.slice(1))}
              <span class="wiz-ap-group-count">${groups[r].length}</span>
            </div>
            ${groups[r].map(c => cardRowHtml(c)).join('')}
          </div>
        `)
        .join('');
      slot.innerHTML = html;
    } else {
      slot.innerHTML = visible.map(c => cardRowHtml(c)).join('');
    }
  }

  function cardRowHtml(card) {
    const prompt = card.art_prompt || null;
    const hasPrompt = !!prompt;

    // For DFCs, show per-face prompts if the top-level prompt is absent
    const faceParts = [];
    if (!hasPrompt && Array.isArray(card.card_faces)) {
      card.card_faces.forEach(face => {
        if (face.art_prompt) {
          faceParts.push(`
            <div class="wiz-ap-face">
              <span class="wiz-ap-face-name">${escHtml(face.name)}</span>
              <span class="wiz-ap-face-prompt">${escHtml(face.art_prompt)}</span>
            </div>
          `);
        }
      });
    }

    const colorsHtml = Array.isArray(card.colors) && card.colors.length > 0
      ? card.colors.map(c => `<span class="wiz-ap-pip wiz-ap-pip-${escAttr(c)}">${escHtml(c)}</span>`).join('')
      : '<span class="wiz-ap-pip wiz-ap-pip-C">C</span>';

    return `
      <div class="wiz-ap-card-row ${hasPrompt ? '' : 'wiz-ap-card-row--no-prompt'}">
        <div class="wiz-ap-card-meta">
          <span class="wiz-ap-card-num">${escHtml(card.collector_number || '')}</span>
          <span class="wiz-ap-pips">${colorsHtml}</span>
          <span class="wiz-ap-card-name">${escHtml(card.name || '(unnamed)')}</span>
          <span class="wiz-ap-type">${escHtml(card.type_line || '')}</span>
        </div>
        ${hasPrompt
          ? `<div class="wiz-ap-prompt">${escHtml(prompt)}</div>`
          : faceParts.length
            ? `<div class="wiz-ap-faces">${faceParts.join('')}</div>`
            : `<div class="wiz-ap-prompt wiz-ap-prompt--missing">No prompt generated yet.</div>`
        }
      </div>
    `;
  }

  // ---------------------------------------------------------------------------
  // Footer — art_prompts is never review_eligible; always a note
  // ---------------------------------------------------------------------------

  function paintFooter(footer, state) {
    if (!footer) return;
    // NOTE: art_prompts has review_eligible: False — the engine never pauses
    // here. The footer is always informational.
    const html = `<span class="wiz-footer-note">Art prompts run automatically — no review step. The engine advances to the next stage on completion.</span>`;
    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
    }
  }

  // ---------------------------------------------------------------------------
  // Form lock (§3) — display-only; lock the filter input + controls
  // ---------------------------------------------------------------------------

  function setLocked(locked) {
    local.locked = !!locked;
    const root = bodyRoot();
    if (!root) return;
    root.classList.toggle('wiz-ap-locked', !!locked);
    root.querySelectorAll('[data-role="ap-filter"], [data-role="ap-group-rarity"]').forEach(el => {
      el.disabled = !!locked;
    });
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function bodyRoot() {
    return document.querySelector(`.wiz-tab-body[data-tab-id="${STAGE_ID}"]`);
  }

  function getFooter(root) {
    return root && root.querySelector('[data-role="footer"]');
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

  // ---------------------------------------------------------------------------
  // Scoped styles — injected once
  // ---------------------------------------------------------------------------

  (function injectStyles() {
    if (document.getElementById('wiz-art_prompts-styles')) return;
    const style = document.createElement('style');
    style.id = 'wiz-art_prompts-styles';
    style.textContent = `
      /* ---- Controls row ---- */
      .wiz-ap-controls {
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 0.85rem;
        flex-wrap: wrap;
      }

      .wiz-ap-filter {
        flex: 1 1 220px;
        min-width: 160px;
        padding: 0.35rem 0.6rem;
        background: #0f1729;
        border: 1px solid #2a3560;
        border-radius: 4px;
        color: #ddd;
        font-size: 0.82rem;
        font-family: inherit;
      }

      .wiz-ap-filter:focus {
        outline: none;
        border-color: #4a9eff;
      }

      .wiz-ap-group-label {
        font-size: 0.80rem;
        color: #888;
        display: flex;
        align-items: center;
        gap: 0.35rem;
        cursor: pointer;
        white-space: nowrap;
      }

      /* ---- Rarity group headers ---- */
      .wiz-ap-group { margin-bottom: 0.5rem; }

      .wiz-ap-group-header {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        padding: 0.3rem 0.6rem;
        border-radius: 4px 4px 0 0;
        background: #12193a;
        border: 1px solid #1f2540;
        border-bottom: none;
        color: #888;
      }

      .wiz-ap-group-header.wiz-ap-rarity-mythic  { color: #e8954a; border-color: #4a2510; }
      .wiz-ap-group-header.wiz-ap-rarity-rare     { color: #e8cc4a; border-color: #3a3010; }
      .wiz-ap-group-header.wiz-ap-rarity-uncommon { color: #aac4d0; border-color: #1f3040; }
      .wiz-ap-group-header.wiz-ap-rarity-common   { color: #bbb;    border-color: #222840; }

      .wiz-ap-group-count {
        margin-left: auto;
        font-size: 0.68rem;
        padding: 1px 5px;
        background: rgba(74,158,255,0.1);
        color: #4a9eff;
        border-radius: 3px;
      }

      /* ---- Card rows ---- */
      .wiz-ap-card-row {
        display: flex;
        flex-direction: column;
        gap: 0.3rem;
        padding: 0.55rem 0.75rem;
        border: 1px solid #1f2540;
        border-top: none;
        background: #0f1729;
        transition: background 0.1s;
      }

      .wiz-ap-card-row:hover { background: #11193a; }

      .wiz-ap-card-row--no-prompt { opacity: 0.65; }

      .wiz-ap-card-row:last-child { border-radius: 0 0 4px 4px; }

      .wiz-ap-card-meta {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        flex-wrap: wrap;
      }

      .wiz-ap-card-num {
        font-size: 0.68rem;
        color: #555;
        font-variant-numeric: tabular-nums;
        min-width: 2.5rem;
      }

      /* WUBRG + colorless pips */
      .wiz-ap-pips { display: flex; gap: 2px; }

      .wiz-ap-pip {
        display: inline-block;
        width: 14px;
        height: 14px;
        border-radius: 50%;
        font-size: 0.55rem;
        font-weight: 700;
        text-align: center;
        line-height: 14px;
        background: #333;
        color: #fff;
      }

      .wiz-ap-pip-W { background: #f0e6c8; color: #333; }
      .wiz-ap-pip-U { background: #1a6ab0; }
      .wiz-ap-pip-B { background: #2a1a2e; border: 1px solid #6a3e7e; }
      .wiz-ap-pip-R { background: #b03020; }
      .wiz-ap-pip-G { background: #1a6a30; }
      .wiz-ap-pip-C { background: #666; }

      .wiz-ap-card-name {
        font-size: 0.85rem;
        font-weight: 600;
        color: #ddd;
      }

      .wiz-ap-type {
        font-size: 0.73rem;
        color: #666;
        flex: 1 1 auto;
        text-align: right;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      /* ---- Art prompt text ---- */
      .wiz-ap-prompt {
        font-size: 0.80rem;
        color: #aaa;
        line-height: 1.5;
        padding-left: 3.5rem; /* aligns with card name */
      }

      .wiz-ap-prompt--missing {
        color: #555;
        font-style: italic;
      }

      /* DFC faces */
      .wiz-ap-faces { padding-left: 3.5rem; display: flex; flex-direction: column; gap: 0.25rem; }

      .wiz-ap-face { display: flex; flex-direction: column; gap: 0.15rem; }

      .wiz-ap-face-name {
        font-size: 0.70rem;
        font-weight: 600;
        color: #666;
        text-transform: uppercase;
        letter-spacing: 0.05em;
      }

      .wiz-ap-face-prompt { font-size: 0.80rem; color: #aaa; line-height: 1.5; }

      /* ---- Locked state ---- */
      .wiz-ap-locked .wiz-ap-filter,
      .wiz-ap-locked [data-role="ap-group-rarity"] {
        cursor: not-allowed;
        opacity: 0.55;
      }
    `;
    document.head.appendChild(style);
  }());
})();
