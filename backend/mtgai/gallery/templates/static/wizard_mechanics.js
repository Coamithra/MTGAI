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
    // The AI picker's rationale (pick-rationale.json): {source, model_id,
    // overall_rationale, selections:[{name,reason}]}. Surfaced in the
    // selection block (below the strip) so the user sees why these picks
    // were chosen.
    pickRationale: null,
    locked: false,
    bootstrapping: false,
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
    const prevStatus = local.stageStatus;
    if (stage) local.stageStatus = stage.status;

    // The stage runs LLM generation synchronously: candidates.json doesn't
    // exist until the call returns, so an initial bootstrap that fires
    // while the engine is mid-call sees an empty list. Re-pull state
    // when status flips out of running so the strip refreshes once the
    // candidates land. Gated on candidates.length===0 so we don't clobber
    // user edits after they've appeared.
    const justFinished =
      stage
      && prevStatus !== local.stageStatus
      && local.stageStatus !== 'pending'
      && local.stageStatus !== 'running'
      && local.candidates.length === 0
      && !local.bootstrapping;
    if (justFinished) {
      local.bootstrapping = true;
      bootstrap(root, state)
        .catch(err => W.toast('Failed to refresh mechanics state: ' + err.message, 'error'))
        .finally(() => { local.bootstrapping = false; });
      return;
    }
    paintFooter(footer, state);
    setLocked(local.locked);
  }

  function mountShellHtml() {
    return `
      <div class="wiz-mech-summary" data-role="mech-summary">
        <div class="wiz-mech-summary-loading">Loading mechanics state…</div>
      </div>
      <div class="wiz-mech-strip" data-role="mech-strip"></div>
      <div class="wiz-mech-selection" data-role="mech-selection"></div>
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
    local.pickRationale = data.pick_rationale || null;
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
    paintSelection(root);
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
    const hasCandidates = local.candidates.length > 0;
    const refreshLabel = hasCandidates ? 'Refresh AI…' : 'Generate AI candidates';
    const refreshTitle = hasCandidates
      ? 'Regenerate AI-flagged candidates (user-edited rows survive).'
      : 'Run mechanic generation now.';
    // Top of the tab = the created mechanics + their Refresh control. The
    // pick controls (Re-pick + selection blurb) live below the strip in
    // ``paintSelection``, mirroring the order of operations.
    slot.innerHTML = `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">Mechanic candidates</h3>
        <button type="button" class="wiz-btn-secondary wiz-refresh-btn"
                data-role="mech-refresh-summary"
                title="${escAttr(refreshTitle)}">${escHtml(refreshLabel)}</button>
      </div>
      <dl class="wiz-mech-context">
        <dt>Set</dt><dd>${escHtml(sp.set_name || '(unnamed)')}</dd>
        <dt>Size</dt><dd>${escHtml(String(sp.set_size || 0))} cards</dd>
        <dt>Picking</dt><dd>${escHtml(String(sp.mechanic_count || 0))} of ${local.candidates.length} candidates</dd>
        <dt>Model</dt><dd>${escHtml(local.modelId || '?')}</dd>
      </dl>
      ${local.themeSummary ? `<details class="wiz-mech-theme-preview"><summary>Theme excerpt</summary><div class="wiz-mech-theme-text">${escHtml(local.themeSummary)}</div></details>` : ''}
    `;
    const btn = slot.querySelector('[data-role="mech-refresh-summary"]');
    if (btn) btn.onclick = () => onRefreshAll();
  }

  // AI-picker rationale banner. Renders nothing for a user-made selection
  // (source !== 'ai') or when no picker has run yet, so the user's own
  // picks aren't mislabelled as the AI's.
  function pickRationaleHtml() {
    const pr = local.pickRationale;
    if (!pr || pr.source !== 'ai') return '';
    const selections = Array.isArray(pr.selections) ? pr.selections : [];
    const items = selections
      .map(s => `<li><strong>${escHtml(s.name || '?')}</strong>${s.reason ? ' — ' + escHtml(s.reason) : ''}</li>`)
      .join('');
    return `
      <div class="wiz-mech-pick-rationale" data-role="pick-rationale">
        <div class="wiz-mech-pick-rationale-head">
          <span class="wiz-ai-badge">AI</span>
          <strong>AI reasoning</strong>
          <span class="wiz-mech-pick-rationale-note">— picked ${selections.length} and pre-checked them above; override any time.</span>
        </div>
        ${items ? `<ul class="wiz-mech-pick-list">${items}</ul>` : ''}
        ${pr.overall_rationale ? `<p class="wiz-mech-pick-overall">${escHtml(pr.overall_rationale)}</p>` : ''}
      </div>
    `;
  }

  // ----------------------------------------------------------------------
  // Candidates strip
  // ----------------------------------------------------------------------

  function paintStrip(root) {
    const slot = root.querySelector('[data-role="mech-strip"]');
    if (!slot) return;
    if (!local.candidates.length) {
      const generating = local.stageStatus === 'running' || local.locked;
      slot.innerHTML = `
        <div class="wiz-mech-empty">
          ${generating
            ? 'Generating candidates… they will stream in here.'
            : 'No candidates yet. Click "Generate AI candidates" above, or advance from Theme.'}
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
          <summary>Design rationale</summary>
          <p>${escHtml(m.design_rationale || '(no rationale given)')}</p>
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

  // ----------------------------------------------------------------------
  // Selection block — below the strip: Re-pick button, then the blurb about
  // which mechanics are selected (AI rationale + pick count). Mirrors the
  // order of operations: create (top) → pick → review selection.
  // ----------------------------------------------------------------------

  function paintSelection(root) {
    const slot = root.querySelector('[data-role="mech-selection"]');
    if (!slot) return;
    if (!local.candidates.length) {
      slot.innerHTML = '';
      return;
    }
    const sp = local.setParams;
    slot.innerHTML = `
      <div class="wiz-mech-selection-actions">
        <button type="button" class="wiz-btn-secondary" data-role="mech-repick"
                title="Let the AI re-choose the best ${escAttr(String(sp.mechanic_count || 0))} from the current candidates.">
          Re-pick with AI
        </button>
      </div>
      ${pickRationaleHtml()}
      <div class="wiz-mech-final-picks" data-role="final-picks"></div>
    `;
    const repick = slot.querySelector('[data-role="mech-repick"]');
    if (repick) repick.onclick = () => onRePick();
    updateFinalPicks(root);
  }

  // The "Final picks" box reflects the live checkbox state — distinct from
  // the AI-reasoning box above (which records what the AI recommended). When
  // the user overrides a pick, this box (and its count) updates immediately.
  function updateFinalPicks(root) {
    const box = root.querySelector('[data-role="final-picks"]');
    if (!box) return;
    const want = local.setParams.mechanic_count || 0;
    const picked = Array.from(local.picks).sort((a, b) => a - b);
    const have = picked.length;
    const body = have
      ? `<ul class="wiz-mech-final-picks-list">${picked
          .map(i => `<li>${escHtml((local.candidates[i] && local.candidates[i].name) || '(unnamed)')}</li>`)
          .join('')}</ul>`
      : `<p class="wiz-mech-final-picks-empty">No mechanics selected yet — tick "Pick" on the cards above.</p>`;
    box.innerHTML = `
      <div class="wiz-mech-final-picks-head">
        <strong>Final picks</strong>
        <span class="wiz-mech-pick-count${have === want ? ' ok' : ''}">${have}/${want} picked</span>
      </div>
      ${body}
    `;
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
      updateFinalPicks(root);
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
    if (W.showBusy) W.showBusy('Regenerating candidate…');
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
      paintSelection(root);
      W.toast('Candidate regenerated.', 'success');
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    } finally {
      if (W.clearBusy) W.clearBusy();
      setLocked(false);
    }
  }

  async function onRefreshAll() {
    if (local.locked) return;
    const root = document.querySelector('.wiz-tab-body[data-tab-id="mechanics"]');
    if (!root) return;

    // Empty-strip path: no candidates on disk yet (initial generation
    // failed, or the user navigated here before the engine produced
    // anything). The button label flips to "Generate AI candidates" in
    // that state, so skip the AI-flagged-row gate and ask the server
    // to run a fresh generation.
    const hasCandidates = local.candidates.length > 0;
    let aiIndices = [];
    if (hasCandidates) {
      aiIndices = Array.from(root.querySelectorAll('.wiz-mech-card[data-ai-generated="true"]'))
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
    }
    setLocked(true);
    if (W.showBusy) {
      W.showBusy(hasCandidates ? 'Regenerating candidates…' : 'Generating candidates…');
    }
    // Repaint so the empty-strip message reflects the in-flight call
    // ("Generating candidates… they will stream in here." instead of
    // the idle "No candidates yet" copy).
    paintStrip(root);
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
      local.collisions = data.collisions || local.collisions;
      // Initial (from-scratch) generation re-runs the AI picker server-side
      // and returns its picks; apply them so the strip pre-selects.
      if (Array.isArray(data.picks)) {
        applyPicks(data.picks, {
          source: 'ai',
          overall_rationale: data.overall_rationale,
          selections: data.selections,
          model_id: data.model_id,
        });
      }
      paintSummary(root);
      paintStrip(root);
      paintSelection(root);
      paintFooter(getFooter(root), W.getState());
      W.toast(hasCandidates ? 'Candidates regenerated.' : 'Candidates generated.', 'success');
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    } finally {
      if (W.clearBusy) W.clearBusy();
      setLocked(false);
    }
  }

  // Apply an AI selection: replace the picks set + store the rationale.
  // Out-of-range indices are dropped defensively.
  function applyPicks(indices, rationale) {
    const n = local.candidates.length;
    local.picks = new Set((indices || []).filter(i => Number.isInteger(i) && i >= 0 && i < n));
    local.pickRationale = rationale || null;
  }

  async function onRePick() {
    if (local.locked) return;
    const root = document.querySelector('.wiz-tab-body[data-tab-id="mechanics"]');
    if (!root) return;
    if (
      local.picks.size > 0
      && !confirm('Let the AI choose the picks? This replaces your current selection.')
    ) {
      return;
    }
    setLocked(true);
    if (W.showBusy) W.showBusy('Selecting the best mechanics…');
    try {
      const resp = await W.postJSON('/api/wizard/mechanics/pick', {
        candidates: local.candidates,
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        if (resp.status === 409 && data.running_action) {
          W.toast(`${data.running_action} is in progress — try again when it finishes.`, 'error');
        } else {
          W.toast(data.error || `AI pick failed (${resp.status})`, 'error');
        }
        return;
      }
      applyPicks(data.picks, {
        source: 'ai',
        overall_rationale: data.overall_rationale,
        selections: data.selections,
        model_id: data.model_id,
      });
      paintSummary(root);
      paintStrip(root);
      paintSelection(root);
      paintFooter(getFooter(root), W.getState());
      W.toast('AI picked the mechanics.', 'success');
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    } finally {
      if (W.clearBusy) W.clearBusy();
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

    const next = W.nextStageEntryAfter(STAGE_ID);
    const nextName = next ? next.name : 'the next stage';

    let html;
    if (isCompleted && isLatest) {
      html = `<span class="wiz-footer-note">Mechanics saved. Engine is on ${nextName} — switch tabs to follow.</span>`;
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
          Save & Continue: ${nextName}
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
      const next = W.nextStageEntryAfter(STAGE_ID);
      const nextHref = next ? `/pipeline/${next.id}` : '/pipeline';
      window.location.assign(advData.navigate_to || saveData.navigate_to || nextHref);
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
      '[data-role="mech-refresh-summary"]',
      '[data-role="mech-repick"]',
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
