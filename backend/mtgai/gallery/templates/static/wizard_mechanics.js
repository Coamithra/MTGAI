/**
 * Wizard Mechanics tab — bespoke candidates strip on the standard
 * stage shell.
 *
 * Registers via ``W.registerStageRenderer('mechanics', ...)`` so the
 * standard wizard_stage.js shell still owns header (status pill,
 * break-point toggle, Edit-cascade button) and we just paint the
 * body + footer.
 *
 * Conventions:
 *   §1  one primary "Save & Continue" footer button
 *   §3  form lock during AI gen
 *   §5  AI provenance badge + preserve-on-edit
 *   §6  past-tab edit cascade routes through W.editFlow.confirmCascade
 *   §8  status pill flows from stage state
 *   §9  Stop after this step — handled by wizard_stage.js
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'mechanics';

  // Module-scoped state — survives SSE-driven rerenders. Refetch keeps
  // the disk view current; ``locked`` is the form-lock flag set during
  // an in-flight refresh-card / refresh-all call.
  const local = {
    initialized: false,
    candidates: [],
    approved: null,
    setParams: { set_name: '', set_size: 0, mechanic_count: 0 },
    themeSummary: '',
    modelId: '',
    collisions: {},
    stageStatus: 'pending',
    picks: new Set(),
    locked: false,
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ----------------------------------------------------------------------
  // Top-level render
  // ----------------------------------------------------------------------

  function render({ root, state, stage, content, footer, rerender }) {
    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      bootstrap(root, state).catch(err => {
        W.toast('Failed to load mechanics state: ' + err.message, 'error');
      });
      // Footer waits for bootstrap to know the picks count; render once
      // here as a placeholder ("Loading…") so the latest-tab footer slot
      // isn't blank during the fetch.
      paintFooter(footer, state);
      return;
    }
    // Re-render path: status pill / footer reactivity. Don't repaint
    // the body — the user may be mid-edit.
    if (stage) local.stageStatus = stage.status;
    paintFooter(footer, state);
    setLocked(local.locked);
  }

  function mountShellHtml() {
    return `
      <div class="wiz-mech-summary" data-role="mech-summary">
        <div class="wiz-mech-summary-loading">Loading mechanics state…</div>
      </div>
      <div class="wiz-mech-strip" data-role="mech-strip"></div>
      <div class="wiz-mech-strip-actions" data-role="mech-strip-actions"></div>
    `;
  }

  // ----------------------------------------------------------------------
  // Bootstrap from server
  // ----------------------------------------------------------------------

  async function bootstrap(root, state) {
    const resp = await fetch('/api/wizard/mechanics/state');
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.error || `HTTP ${resp.status}`);
    }
    const data = await resp.json();
    local.candidates = Array.isArray(data.candidates) ? data.candidates : [];
    local.approved = data.approved || null;
    local.setParams = data.set_params || local.setParams;
    local.themeSummary = data.theme_summary || '';
    local.modelId = data.model_id || '';
    local.collisions = data.collisions || {};
    local.stageStatus = data.stage_status || local.stageStatus;
    // Pre-seed picks from approved.json if it exists — the user has
    // already saved once and may be re-opening the tab. Match by name
    // since indices may have shifted between sessions.
    local.picks = preselectPicksFromApproved(local.candidates, local.approved);

    paintSummary(root);
    paintStrip(root);
    paintStripActions(root);
    paintFooter(getFooter(root), state);
  }

  function preselectPicksFromApproved(candidates, approved) {
    if (!Array.isArray(approved)) return new Set();
    const names = new Set(approved.map(m => (m && m.name || '').toLowerCase()));
    const out = new Set();
    candidates.forEach((c, idx) => {
      const name = (c && c.name || '').toLowerCase();
      if (name && names.has(name)) out.add(idx);
    });
    return out;
  }

  // ----------------------------------------------------------------------
  // Summary block
  // ----------------------------------------------------------------------

  function paintSummary(root) {
    const slot = root.querySelector('[data-role="mech-summary"]');
    if (!slot) return;
    const sp = local.setParams;
    slot.innerHTML = `
      <dl class="wiz-mech-context">
        <dt>Set</dt><dd>${escHtml(sp.set_name || '(unnamed)')}</dd>
        <dt>Size</dt><dd>${escHtml(String(sp.set_size || 0))} cards</dd>
        <dt>Picking</dt><dd>${escHtml(String(sp.mechanic_count || 0))} of ${local.candidates.length} candidates</dd>
        <dt>Model</dt><dd>${escHtml(local.modelId || '?')}</dd>
      </dl>
      ${local.themeSummary ? `<details class="wiz-mech-theme-preview"><summary>Theme excerpt</summary><div class="wiz-mech-theme-text">${escHtml(local.themeSummary)}</div></details>` : ''}
    `;
  }

  // ----------------------------------------------------------------------
  // Candidates strip
  // ----------------------------------------------------------------------

  function paintStrip(root) {
    const slot = root.querySelector('[data-role="mech-strip"]');
    if (!slot) return;
    if (!local.candidates.length) {
      slot.innerHTML = `
        <div class="wiz-mech-empty">
          ${local.stageStatus === 'running'
            ? 'Generating candidates… they will stream in here.'
            : 'No candidates yet. The pipeline will generate 6 once you advance from Theme.'}
        </div>
      `;
      return;
    }
    slot.innerHTML = local.candidates
      .map((c, idx) => candidateCardHtml(c, idx))
      .join('');
    bindStrip(slot);
  }

  function candidateCardHtml(mech, idx) {
    const collision = local.collisions[String(idx)];
    const collisionWarning = collision
      ? `<div class="wiz-mech-collision">⚠ Name collides with printed keyword: <strong>${escHtml(collision)}</strong>. Rename or pick a different candidate.</div>`
      : '';
    const picked = local.picks.has(idx);
    const m = mech || {};
    const colors = Array.isArray(m.colors) ? m.colors : [];
    const complexity = Number(m.complexity || 1);
    const keywordType = String(m.keyword_type || 'keyword_ability');
    const dist = m.distribution || {};
    // Provenance lives on the candidate dict — server persists
    // ``_ai_generated`` in candidates.json so it survives reload, and
    // refresh-{card,all} preserves the flag for rows the server didn't
    // overwrite. Default to true for legacy candidates that pre-date
    // the field.
    const aiGenerated = m._ai_generated !== false;
    const aiBadge = aiGenerated
      ? '<span class="wiz-ai-badge" data-role="ai-badge">AI</span>'
      : '';
    return `
      <article class="wiz-mech-card${picked ? ' picked' : ''}" data-idx="${idx}"${aiGenerated ? ' data-ai-generated="true"' : ''}>
        <header class="wiz-mech-card-header">
          ${aiBadge}
          <input type="text" class="wiz-mech-name" data-role="mech-name"
                 placeholder="Mechanic name"
                 value="${escAttr(m.name || '')}">
          <label class="wiz-mech-pick">
            <input type="checkbox" data-role="mech-pick" ${picked ? 'checked' : ''}>
            Pick
          </label>
        </header>
        ${collisionWarning}
        <div class="wiz-mech-row">
          <div class="wiz-mech-field">
            <span class="wiz-mech-label">Keyword type</span>
            <div class="wiz-mech-chip-row" data-role="kw-type">
              ${chipHtml('keyword_ability', 'Keyword ability', keywordType === 'keyword_ability')}
              ${chipHtml('ability_word', 'Ability word', keywordType === 'ability_word')}
              ${chipHtml('keyword_action', 'Keyword action', keywordType === 'keyword_action')}
            </div>
          </div>
          <div class="wiz-mech-field">
            <span class="wiz-mech-label">Complexity</span>
            <div class="wiz-mech-chip-row" data-role="complexity">
              ${chipHtml('1', '1', complexity === 1)}
              ${chipHtml('2', '2', complexity === 2)}
              ${chipHtml('3', '3', complexity === 3)}
            </div>
          </div>
          <div class="wiz-mech-field">
            <span class="wiz-mech-label">Colors</span>
            <div class="wiz-mech-chip-row" data-role="colors">
              ${['W', 'U', 'B', 'R', 'G'].map(c => chipHtml(c, c, colors.includes(c))).join('')}
            </div>
          </div>
        </div>
        <div class="wiz-mech-field">
          <span class="wiz-mech-label">Reminder text</span>
          <textarea class="wiz-mech-reminder" data-role="reminder"
                    rows="2" maxlength="120">${escHtml(m.reminder_text || '')}</textarea>
        </div>
        <div class="wiz-mech-field">
          <span class="wiz-mech-label">Distribution</span>
          <div class="wiz-mech-distribution">
            C: ${escHtml(String(dist.common || 0))} ·
            U: ${escHtml(String(dist.uncommon || 0))} ·
            R: ${escHtml(String(dist.rare || 0))} ·
            M: ${escHtml(String(dist.mythic || 0))}
          </div>
        </div>
        <details class="wiz-mech-details">
          <summary>Why this fits the set</summary>
          <p>${escHtml(m.flavor_connection || '(no flavor connection given)')}</p>
        </details>
        <details class="wiz-mech-details">
          <summary>Design rationale</summary>
          <p>${escHtml(m.design_rationale || '(no rationale given)')}</p>
        </details>
        <details class="wiz-mech-details">
          <summary>Pattern lists (common / uncommon / rare)</summary>
          ${patternListHtml('Common', m.common_patterns)}
          ${patternListHtml('Uncommon', m.uncommon_patterns)}
          ${patternListHtml('Rare/Mythic', m.rare_patterns)}
        </details>
        <details class="wiz-mech-details">
          <summary>Example cards (${(m.example_cards || []).length})</summary>
          ${(m.example_cards || []).map(exampleCardHtml).join('') || '<p>(none)</p>'}
        </details>
        <footer class="wiz-mech-card-footer">
          <button type="button" class="wiz-btn-secondary" data-role="refresh-card"
                  title="Regenerate this candidate via AI (the others stay).">
            Refresh AI
          </button>
        </footer>
      </article>
    `;
  }

  function chipHtml(value, label, active) {
    return `<button type="button" class="wiz-mech-chip${active ? ' active' : ''}" data-value="${escAttr(value)}">${escHtml(label)}</button>`;
  }

  function patternListHtml(label, items) {
    const list = (Array.isArray(items) ? items : []);
    if (!list.length) return `<p><em>${escHtml(label)}:</em> (none)</p>`;
    return `
      <p><em>${escHtml(label)}:</em></p>
      <ul>${list.map(p => `<li>${escHtml(String(p))}</li>`).join('')}</ul>
    `;
  }

  function exampleCardHtml(card) {
    if (!card || typeof card !== 'object') return '';
    const pt = card.power && card.toughness ? ` ${escHtml(card.power)}/${escHtml(card.toughness)}` : '';
    return `
      <div class="wiz-mech-example">
        <strong>${escHtml(card.name || '?')}</strong> ${escHtml(card.mana_cost || '')} —
        <em>${escHtml(card.type_line || '')}</em>${pt}
        <span class="wiz-mech-rarity">[${escHtml(card.rarity || '?')}]</span>
        <p>${escHtml(card.oracle_text || '')}</p>
      </div>
    `;
  }

  // ----------------------------------------------------------------------
  // Strip-level actions row
  // ----------------------------------------------------------------------

  function paintStripActions(root) {
    const slot = root.querySelector('[data-role="mech-strip-actions"]');
    if (!slot) return;
    if (!local.candidates.length) {
      slot.innerHTML = '';
      return;
    }
    slot.innerHTML = `
      <button type="button" class="wiz-btn-secondary" data-role="refresh-all">
        Refresh all AI candidates
      </button>
      <span class="wiz-mech-pick-count" data-role="pick-count"></span>
    `;
    const btn = slot.querySelector('[data-role="refresh-all"]');
    if (btn) btn.onclick = () => onRefreshAll();
    updatePickCountLabel(root);
  }

  function updatePickCountLabel(root) {
    const span = root.querySelector('[data-role="pick-count"]');
    if (!span) return;
    const want = local.setParams.mechanic_count || 0;
    const have = local.picks.size;
    span.textContent = `${have}/${want} picked`;
    span.classList.toggle('ok', have === want);
  }

  // ----------------------------------------------------------------------
  // Strip event binding
  // ----------------------------------------------------------------------

  function bindStrip(slot) {
    slot.querySelectorAll('.wiz-mech-card').forEach(card => bindCard(card));
  }

  function bindCard(card) {
    const idx = Number(card.dataset.idx);

    // Edit listeners — clear AI badge once the user touches an editable
    // field. AI provenance is maintained per §5: refresh-all only
    // overwrites rows still flagged ai-generated. The flag also lives
    // on ``local.candidates[idx]._ai_generated`` so it survives a
    // ``paintStrip`` rerender (refresh-card, etc.).
    const editFields = card.querySelectorAll('input, textarea, .wiz-mech-chip');
    editFields.forEach(el => {
      const handler = () => markEdited(idx, card);
      // Skip the pick checkbox — it's not a content edit.
      if (el.dataset && el.dataset.role === 'mech-pick') return;
      if (el.classList.contains('wiz-mech-chip')) el.addEventListener('click', handler);
      else el.addEventListener('input', handler);
    });

    // Pick checkbox
    const pick = card.querySelector('[data-role="mech-pick"]');
    if (pick) pick.addEventListener('change', () => {
      if (pick.checked) {
        local.picks.add(idx);
        card.classList.add('picked');
      } else {
        local.picks.delete(idx);
        card.classList.remove('picked');
      }
      const root = card.closest('.wiz-tab-body');
      updatePickCountLabel(root);
      const footer = getFooter(root);
      paintFooter(footer, W.getState());
    });

    // Name input — keep candidates list in sync so refresh-card POSTs
    // current edits.
    const name = card.querySelector('[data-role="mech-name"]');
    if (name) name.addEventListener('input', () => {
      local.candidates[idx] = setField(local.candidates[idx], 'name', name.value);
    });
    const reminder = card.querySelector('[data-role="reminder"]');
    if (reminder) reminder.addEventListener('input', () => {
      local.candidates[idx] = setField(local.candidates[idx], 'reminder_text', reminder.value);
    });

    // Chip rows: keyword type, complexity, colors
    bindChipRow(card, '[data-role="kw-type"]', { multi: false }, value => {
      local.candidates[idx] = setField(local.candidates[idx], 'keyword_type', value);
    });
    bindChipRow(card, '[data-role="complexity"]', { multi: false }, value => {
      local.candidates[idx] = setField(local.candidates[idx], 'complexity', Number(value));
    });
    bindChipRow(card, '[data-role="colors"]', { multi: true }, values => {
      local.candidates[idx] = setField(local.candidates[idx], 'colors', values);
    });

    // Refresh-card
    const refresh = card.querySelector('[data-role="refresh-card"]');
    if (refresh) refresh.onclick = () => onRefreshCard(idx);
  }

  function bindChipRow(card, selector, { multi }, onChange) {
    const row = card.querySelector(selector);
    if (!row) return;
    row.querySelectorAll('.wiz-mech-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        if (multi) {
          chip.classList.toggle('active');
        } else {
          row.querySelectorAll('.wiz-mech-chip').forEach(c => c.classList.remove('active'));
          chip.classList.add('active');
        }
        const active = Array.from(row.querySelectorAll('.wiz-mech-chip.active'))
          .map(c => c.dataset.value);
        onChange(multi ? active : (active[0] || ''));
      });
    });
  }

  function setField(mech, key, value) {
    const next = Object.assign({}, mech || {});
    next[key] = value;
    return next;
  }

  function markEdited(idx, card) {
    delete card.dataset.aiGenerated;
    const badge = card.querySelector('[data-role="ai-badge"]');
    if (badge) badge.remove();
    if (local.candidates[idx]) {
      local.candidates[idx] = setField(local.candidates[idx], '_ai_generated', false);
    }
  }

  // ----------------------------------------------------------------------
  // Refresh — single + all
  // ----------------------------------------------------------------------

  async function onRefreshCard(idx) {
    if (local.locked) return;
    if (!confirm('Regenerate this candidate? Other rows stay; this row will be overwritten.')) return;
    setLocked(true);
    try {
      const resp = await W.postJSON('/api/wizard/mechanics/refresh-card', {
        candidate_index: idx,
        candidates: local.candidates,
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        if (resp.status === 409 && data.running_action) {
          W.toast(`${data.running_action} is in progress — try again when it finishes.`, 'error');
        } else {
          W.toast(data.error || `Refresh failed (${resp.status})`, 'error');
        }
        return;
      }
      local.candidates = data.candidates || local.candidates;
      // The freshly-generated row is AI again. Existing user-edited
      // rows' AI flag stays cleared (the strip rerender below is
      // gated to the refreshed slot).
      const root = document.querySelector('.wiz-tab-body[data-tab-id="mechanics"]');
      paintStrip(root);
      paintStripActions(root);
      W.toast('Candidate regenerated.', 'success');
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    } finally {
      setLocked(false);
    }
  }

  async function onRefreshAll() {
    if (local.locked) return;
    const root = document.querySelector('.wiz-tab-body[data-tab-id="mechanics"]');
    if (!root) return;
    const aiIndices = Array.from(root.querySelectorAll('.wiz-mech-card[data-ai-generated="true"]'))
      .map(card => Number(card.dataset.idx));
    if (!aiIndices.length) {
      W.toast('No AI-flagged rows to refresh — every candidate has been edited.', 'warn');
      return;
    }
    if (local.picks.size > 0) {
      if (!confirm('Picks are set on this strip. Refreshing will replace AI-flagged rows; user-edited rows survive. Continue?')) {
        return;
      }
    } else if (!confirm(`Regenerate ${aiIndices.length} AI-flagged candidate${aiIndices.length === 1 ? '' : 's'}? Edited rows stay.`)) {
      return;
    }
    setLocked(true);
    try {
      const resp = await W.postJSON('/api/wizard/mechanics/refresh-all', {
        indices: aiIndices,
        candidates: local.candidates,
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        if (resp.status === 409 && data.running_action) {
          W.toast(`${data.running_action} is in progress — try again when it finishes.`, 'error');
        } else {
          W.toast(data.error || `Refresh failed (${resp.status})`, 'error');
        }
        return;
      }
      local.candidates = data.candidates || local.candidates;
      paintStrip(root);
      paintStripActions(root);
      W.toast('Candidates regenerated.', 'success');
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    } finally {
      setLocked(false);
    }
  }

  // ----------------------------------------------------------------------
  // Footer: Save & Continue (latest tab + paused_for_review)
  // ----------------------------------------------------------------------

  function paintFooter(footer, state) {
    if (!footer) return;
    const want = local.setParams.mechanic_count || 0;
    const have = local.picks.size;
    const isLatest = !state || state.latestTabId === STAGE_ID;
    const isPaused = local.stageStatus === 'paused_for_review';
    const isCompleted = local.stageStatus === 'completed';

    let html;
    if (isCompleted && isLatest) {
      html = `<span class="wiz-footer-note">Mechanics saved. Engine is on Skeleton — switch tabs to follow.</span>`;
    } else if (!isLatest) {
      // Past tab — edit cascade is the only way through. wizard_stage.js
      // owns the Edit button + cascade flow.
      html = `<span class="wiz-footer-note">Editing past mechanics is destructive — use the Edit button above.</span>`;
    } else if (!local.candidates.length || !isPaused) {
      html = `<span class="wiz-footer-note">Save & Continue appears once candidates are ready for review.</span>`;
    } else {
      const ok = have === want;
      html = `
        <button type="button" class="wiz-btn-primary" data-role="mech-save-advance" ${ok && !local.locked ? '' : 'disabled'}>
          Save & Continue: Skeleton Generation
        </button>
        <span class="wiz-footer-note">${have}/${want} picks selected.</span>
      `;
    }
    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
    }
    const btn = footer.querySelector('[data-role="mech-save-advance"]');
    if (btn) btn.onclick = onSaveAndAdvance;
  }

  async function onSaveAndAdvance() {
    if (local.locked) return;
    const want = local.setParams.mechanic_count || 0;
    if (local.picks.size !== want) {
      W.toast(`Pick exactly ${want} candidate${want === 1 ? '' : 's'} before continuing.`, 'error');
      return;
    }
    setLocked(true);
    const root = document.querySelector(`.wiz-tab-body[data-tab-id="${STAGE_ID}"]`);
    const footer = getFooter(root);
    const btn = footer && footer.querySelector('[data-role="mech-save-advance"]');
    const original = btn ? btn.textContent : '';
    if (btn) btn.textContent = 'Saving…';
    try {
      const picksSorted = Array.from(local.picks).sort((a, b) => a - b);
      const saveResp = await W.postJSON('/api/wizard/mechanics/save', {
        picks: picksSorted,
        candidates: local.candidates,
      });
      const saveData = await saveResp.json().catch(() => ({}));
      if (!saveResp.ok) {
        W.toast(saveData.error || `Save failed (${saveResp.status})`, 'error');
        if (btn) btn.textContent = original;
        return;
      }

      if (btn) btn.textContent = 'Starting…';
      const advResp = await W.postJSON('/api/wizard/advance', {});
      const advData = await advResp.json().catch(() => ({}));
      if (!advResp.ok) {
        W.toast(advData.error || `Advance failed (${advResp.status})`, 'error');
        if (btn) btn.textContent = original;
        return;
      }
      window.location.assign(advData.navigate_to || saveData.navigate_to || '/pipeline/skeleton');
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
      if (btn) btn.textContent = original;
    } finally {
      setLocked(false);
    }
  }

  // ----------------------------------------------------------------------
  // Form lock (§3)
  // ----------------------------------------------------------------------

  function setLocked(locked) {
    local.locked = !!locked;
    const root = document.querySelector(`.wiz-tab-body[data-tab-id="${STAGE_ID}"]`);
    if (!root) return;
    root.classList.toggle('wiz-mech-locked', !!locked);
    const sel = [
      '.wiz-mech-card input',
      '.wiz-mech-card textarea',
      '.wiz-mech-card .wiz-mech-chip',
      '[data-role="refresh-card"]',
      '[data-role="refresh-all"]',
    ].join(',');
    root.querySelectorAll(sel).forEach(el => { el.disabled = !!locked; });
    const footerBtn = root.querySelector('[data-role="mech-save-advance"]');
    if (footerBtn) footerBtn.disabled = !!locked;
  }

  // ----------------------------------------------------------------------
  // Helpers
  // ----------------------------------------------------------------------

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
})();
