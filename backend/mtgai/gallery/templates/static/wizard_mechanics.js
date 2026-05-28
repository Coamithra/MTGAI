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
    // Which kind of refresh is currently in flight, if any. Set in the
    // refresh handlers, cleared in their ``finally``. Drives whether the
    // streaming events update the global progress strip's label with the
    // "Generating/Reviewing candidate X/N" sequence (refresh-all) or leave
    // the original "Regenerating candidate…" label alone (refresh-card,
    // where there's no meaningful "X of N" because it's a single shot).
    streamingMode: null,
  };

  W.registerStageRenderer(STAGE_ID, render);
  // SSE bridge from wizard.js — the mechanic generation stream pushes a draft
  // (pre-review) then a finalized version (post-review) per candidate, plus a
  // reset at the start of a from-scratch run.
  W.onMechanicsStream = onMechanicsStream;

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
    const m = mech || {};
    // Two placeholder cases share the slim card shell:
    //   _pending_generation — an AI run is actively filling this slot in.
    //                         Pulsing "Generating…" badge, no Refresh button
    //                         (the in-flight call owns the slot).
    //   empty slot (no name)— left over from a previous failed run; the user
    //                         can click Refresh AI inside the card to fill it.
    //
    // Rendering empty {} slots as full editable forms (the old default-fallback
    // path) was confusing — defaults made it look like a real card waiting for
    // input, when really it's "nothing here yet". This unified placeholder
    // makes the slot's actual state legible.
    const isPending = !!m._pending_generation;
    const isEmpty = !isPending && !((m.name || '').trim());
    if (isPending || isEmpty) {
      const badge = isPending
        ? '<span class="wiz-mech-reviewing" data-role="generating-badge">Generating…</span>'
        : '<span class="wiz-mech-empty-badge">Empty slot</span>';
      const body = isPending
        ? 'Waiting for the next candidate…'
        : 'No mechanic generated for this slot — click Refresh AI to fill it.';
      // Empty slots get a Refresh button (user-initiated re-fill); in-flight
      // slots don't (the active run already owns this slot).
      const footer = isPending
        ? ''
        : `<footer class="wiz-mech-card-footer">
             <button type="button" class="wiz-btn-secondary" data-role="refresh-card"
                     title="Generate a mechanic for this empty slot.">
               Refresh AI
             </button>
           </footer>`;
      return `
        <article class="wiz-mech-card wiz-mech-card--pending wiz-mech-card--placeholder"
                 data-idx="${idx}"${isPending ? ' data-pending-generation="true"' : ' data-empty-slot="true"'}>
          <header class="wiz-mech-card-header">
            ${badge}
            <span class="wiz-mech-placeholder-title">Slot ${idx + 1}</span>
          </header>
          <div class="wiz-mech-placeholder-body">${body}</div>
          ${footer}
        </article>
      `;
    }
    const collision = local.collisions[String(idx)];
    const collisionWarning = collision
      ? `<div class="wiz-mech-collision">⚠ Name collides with printed keyword: <strong>${escHtml(collision)}</strong>. Rename or pick a different candidate.</div>`
      : '';
    const picked = local.picks.has(idx);
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
    // Live-stream state: between the drafted event and the finalized event,
    // ``_pending_review`` is true. We surface a "Reviewing…" badge and keep
    // the form locked (the card is being rewritten any moment). After review,
    // ``_review_notes`` carries what the reviewer fixed (empty = unchanged).
    const pendingReview = !!m._pending_review;
    const reviewingBadge = pendingReview
      ? '<span class="wiz-mech-reviewing" data-role="reviewing-badge">Reviewing…</span>'
      : '';
    const reviewNotes = (m._review_notes || '').trim();
    const reviewNotesLine = (!pendingReview && reviewNotes)
      ? `<div class="wiz-mech-review-notes" title="The AI review pass tweaked this draft.">Reviewer tweak: ${escHtml(reviewNotes)}</div>`
      : '';
    return `
      <article class="wiz-mech-card${picked ? ' picked' : ''}${pendingReview ? ' wiz-mech-card--pending' : ''}" data-idx="${idx}"${aiGenerated ? ' data-ai-generated="true"' : ''}${pendingReview ? ' data-pending-review="true"' : ''}>
        <header class="wiz-mech-card-header">
          ${aiBadge}
          ${reviewingBadge}
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
        ${exampleCardsHtml(m.example_cards)}
        <details class="wiz-mech-details">
          <summary>Design rationale</summary>
          <p>${escHtml(m.design_rationale || '(no rationale given)')}</p>
        </details>
        ${reviewNotesLine}
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

  // Read-only "Example cards" preview — the two reference cards the mechanic
  // generator produces alongside the keyword. They propagate to card-gen as
  // concrete templating references, and we surface them visibly (not behind a
  // <details>) so the user can sanity-check the LLM's output at a glance.
  // Edits aren't possible inline — regenerate the candidate to change them.
  function exampleCardsHtml(examples) {
    if (!Array.isArray(examples) || !examples.length) return '';
    const items = examples
      .map(ex => {
        const e = ex || {};
        const name = e.name || '(unnamed)';
        const cost = e.mana_cost || '';
        const typeLine = e.type_line || '';
        const rarity = e.rarity || '';
        const oracle = e.oracle_text || '';
        const power = e.power;
        const toughness = e.toughness;
        const pt = (power !== undefined && power !== '' && toughness !== undefined && toughness !== '')
          ? ` ${power}/${toughness}` : '';
        const head = `<strong>${escHtml(name)}</strong>${cost ? ' ' + escHtml(cost) : ''}`;
        const meta = [escHtml(typeLine + pt), rarity ? `<span class="wiz-mech-rarity">${escHtml(rarity)}</span>` : '']
          .filter(Boolean).join(' · ');
        const oracleHtml = oracle ? `<p>${escHtml(oracle).replace(/\n/g, '<br>')}</p>` : '';
        return `<div class="wiz-mech-example">${head}${meta ? ' — ' + meta : ''}${oracleHtml}</div>`;
      })
      .join('');
    return `
      <div class="wiz-mech-field">
        <span class="wiz-mech-label">Example cards (card-gen reference)</span>
        <div class="wiz-mech-examples">${items}</div>
      </div>
    `;
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
    local.streamingMode = 'single';
    if (W.showBusy) W.showBusy('Regenerating candidate…');
    // Clear the slot immediately so the stale card doesn't linger while the
    // LLM works. The streamed drafted event will overwrite the placeholder.
    const root = document.querySelector(`.wiz-tab-body[data-tab-id="${STAGE_ID}"]`);
    if (local.candidates[idx]) {
      local.candidates[idx] = { _pending_generation: true };
      delete local.collisions[String(idx)];
      // Drop the pick — the slot's identity is about to change.
      local.picks.delete(idx);
      if (root) {
        paintStrip(root);
        updateFinalPicks(root);
      }
    }
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
      // gated to the refreshed slot). ``root`` is the outer-scoped
      // element grabbed before the optimistic clear above.
      if (root) {
        paintStrip(root);
        paintSelection(root);
      }
      W.toast('Candidate regenerated.', 'success');
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    } finally {
      local.streamingMode = null;
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
      // Refresh AI replaces both AI-flagged rows (last-AI-generated content
      // still untouched) and empty slots (left over from a failed run). The
      // user-edited rows have neither attribute and survive.
      aiIndices = Array.from(
        root.querySelectorAll('.wiz-mech-card[data-ai-generated="true"], .wiz-mech-card[data-empty-slot="true"]')
      ).map(card => Number(card.dataset.idx));
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
    local.streamingMode = 'all';
    if (W.showBusy) {
      W.showBusy(hasCandidates ? 'Regenerating candidates…' : 'Generating candidates…');
    }
    // Clear the slots about to be regenerated *immediately* so the stale
    // cards don't hang around while the LLM works. The streamed drafted
    // events refill these placeholders. Two cases:
    //   * Initial generate (no candidates yet) — populate the whole strip
    //     with ``pool``-many placeholders so the user sees the layout the
    //     candidates will land into. The streaming reset event (server
    //     fires it only for this path) is a no-op here since we've already
    //     done the work, but stays as the canonical "wipe + repopulate"
    //     signal for mid-run tab reattach.
    //   * Targeted refresh — blank only the AI-flagged rows; user-edited
    //     rows stay untouched. Drop any picks on the cleared rows since
    //     their identity is about to change.
    if (hasCandidates) {
      aiIndices.forEach(i => {
        local.candidates[i] = { _pending_generation: true };
        delete local.collisions[String(i)];
        local.picks.delete(i);
      });
    } else {
      const target = (local.setParams.mechanic_count || 0) * 2;
      const slots = target > 0 ? target : (local.candidates.length || 0);
      local.candidates = new Array(slots).fill(null).map(() => ({ _pending_generation: true }));
      local.collisions = {};
      local.picks = new Set();
    }
    paintStrip(root);
    paintSelection(root);
    updateFinalPicks(root);
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
      local.streamingMode = null;
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
  // Live streaming (SSE bridged from wizard.js via W.onMechanicsStream)
  //
  // Three events:
  //   mechanic_candidates_reset    — clear the strip (only fires on a from-
  //                                  scratch generation; targeted refresh
  //                                  preserves untouched rows)
  //   mechanic_candidate_drafted   — draft accepted, pre-review. Shows a
  //                                  "Reviewing…" badge on the card so the
  //                                  user can see it's not yet final.
  //   mechanic_candidate_finalized — review pass returned. Replaces the
  //                                  draft with the final mechanic +
  //                                  optional ``review_notes`` line.
  //
  // The handler is idempotent: a tab reattach mid-run sees the same events
  // it would have if it never left, so repainting on each event is safe.
  // We avoid clobbering picks: ``_review_notes`` lives on the candidate dict
  // alongside ``_ai_generated``; picks are tracked by index in ``local.picks``.
  // ----------------------------------------------------------------------

  function onMechanicsStream(name, data) {
    if (name === 'mechanic_candidates_reset') return onStreamReset(data || {});
    if (name === 'mechanic_candidate_drafted') return onStreamDrafted(data || {});
    if (name === 'mechanic_candidate_finalized') return onStreamFinalized(data || {});
  }

  function tabRoot() {
    return document.querySelector(`.wiz-tab-body[data-tab-id="${STAGE_ID}"]`);
  }

  // Replace the global progress strip's label so the user sees per-candidate
  // progress instead of a static "Regenerating candidates…" — Gemma can take
  // 30-60s per call so a static label looks frozen. Only updates if the
  // busy strip is already active AND we're in a refresh-all sequence (where
  // the "X of N" label is meaningful); refresh-card is one shot, so we leave
  // its label alone. showBusy is idempotent — calling it again rewrites the
  // label without disturbing the indeterminate bar animation.
  function setBusyLabel(label) {
    if (!local.locked || !W.showBusy) return;
    if (local.streamingMode !== 'all') return;
    W.showBusy(label);
  }

  function onStreamReset(data) {
    const root = tabRoot();
    if (!root) return;
    // Reset to a strip of "Generating…" placeholders — the events that follow
    // will replace them. We also clear picks/rationale because a from-scratch
    // reset implies a new pool; the AI picker will re-pick once the engine
    // path's HTTP response lands (or the user can re-pick manually).
    const target = Number(data && data.target) || local.candidates.length || 0;
    local.candidates = target > 0
      ? new Array(target).fill(null).map(() => ({ _pending_generation: true }))
      : [];
    local.collisions = {};
    local.picks = new Set();
    local.pickRationale = null;
    paintSummary(root);
    paintStrip(root);
    paintSelection(root);
    if (target > 0) setBusyLabel(`Generating candidate 1/${target}`);
  }

  function onStreamDrafted(data) {
    const root = tabRoot();
    if (!root) return;
    const position = Number(data && data.position);
    const target = Number(data && data.target) || local.candidates.length || 0;
    const candidate = data && data.candidate;
    if (!Number.isInteger(position) || position < 1 || !candidate) return;
    const idx = position - 1;
    // Pad ``local.candidates`` if a draft lands ahead of the slot (tab opened
    // mid-run, missed the reset). Each empty slot is just {} so paintStrip
    // renders a blank placeholder rather than crashing.
    while (local.candidates.length <= idx) local.candidates.push({});
    local.candidates[idx] = Object.assign({}, candidate, { _pending_review: true });
    // A streamed draft means the row is fresh AI — invalidate any prior
    // collision warning for this slot until the finalized event reasserts it.
    delete local.collisions[String(idx)];
    paintStrip(root);
    paintSummary(root);
    // The draft just landed; the review call is now in flight for the same
    // candidate. Reflect that in the global progress strip.
    if (target > 0) setBusyLabel(`Reviewing candidate ${position}/${target}`);
  }

  function onStreamFinalized(data) {
    const root = tabRoot();
    if (!root) return;
    const position = Number(data && data.position);
    const target = Number(data && data.target) || local.candidates.length || 0;
    const candidate = data && data.candidate;
    if (!Number.isInteger(position) || position < 1 || !candidate) return;
    const idx = position - 1;
    while (local.candidates.length <= idx) local.candidates.push({});
    local.candidates[idx] = Object.assign({}, candidate, {
      _pending_review: false,
      _review_notes: (data.review_notes || '').toString(),
    });
    if (data.collision_with) {
      local.collisions[String(idx)] = String(data.collision_with);
    } else {
      delete local.collisions[String(idx)];
    }
    paintStrip(root);
    paintSummary(root);
    // After the last finalized event the server runs the AI picker (a single
    // LLM call) before the HTTP response lands — surface that as the label
    // so the strip doesn't look frozen during the picker call. For mid-run
    // events, point at the next slot being generated.
    if (target > 0) {
      if (position >= target) {
        setBusyLabel('Picking best mechanics…');
      } else {
        setBusyLabel(`Generating candidate ${position + 1}/${target}`);
      }
    }
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
