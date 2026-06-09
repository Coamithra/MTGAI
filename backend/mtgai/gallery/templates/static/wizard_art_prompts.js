/**
 * Wizard Art Prompts tab — artist-driven, LLM-authored, editable.
 *
 * Stage ID: ``art_prompts`` (review_eligible: False — never auto-pauses).
 *
 * Each card's Flux art prompt is authored by the LLM in the voice of a chosen
 * artist (``mtgai.art.prompt_builder.generate_prompts_for_set``). This tab:
 *   - streams every card in live as its prompt lands (per-card SSE, like
 *     card_gen — W.onArtPromptsStream / art_prompt_card / art_prompt_reset);
 *   - lets the user edit any prompt in place + reassign the credited artist,
 *     saving via /api/wizard/art_prompts/save-card;
 *   - surfaces the per-card cameo-probability knob (persisted via
 *     /api/wizard/art_prompts/knobs) and a "Refresh AI…" re-roll
 *     (/api/wizard/art_prompts/refresh) honouring it.
 *
 * Conventions honoured:
 *   §1  no Save & Continue advance button (stage is not review-eligible) —
 *       the footer is a status note; a break-point pause is resumed via "Next".
 *   §3  form lock during AI gen (aiBusy composite) via W.setTabLocked.
 *   §5  artist reassign is a per-tile edit (not the AI-provenance list contract).
 *   §6  past-tab: read-only (Edit cascade via wizard_stage.js).
 *   §7  refresh goes through W.runAiAction (lock → 409 → unlock).
 *   §8  status pill driven by the shell.
 *   §13 section-level Refresh-AI button, always rendered on the latest tab.
 *
 * Registers via ``W.registerStageRenderer('art_prompts', render)``.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'art_prompts';

  const escHtml = W.escHtml;
  const escAttr = W.escAttr;

  const RARITY_ORDER = ['mythic', 'rare', 'uncommon', 'common', 'special', 'bonus'];

  const local = {
    initialized: false,
    cards: [],        // [{name, collector_number, type_line, rarity, colors, artist, art_prompt, card_faces, entity_tags}]
    artists: [],      // directory artist names (for the reassign dropdown)
    entityCatalog: [], // [{entity_key, kind, name}] dictionary entities for the add-tag picker
    cameoProbability: 0.25,
    hasContent: false,
    prompted: 0,
    stageStatus: 'pending',
    locked: false,
    bootstrapping: false,
    filter: '',
    groupBy: 'rarity', // 'rarity' | 'none'
    state: null,
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ── SSE stream bridge (§17) ───────────────────────────────────────────────
  // wizard.js forwards art_prompt_reset / art_prompt_card here.
  W.registerStream(STAGE_ID, {
    art_prompt_reset(_data, root) {
      // A forced re-run is re-authoring every prompt: drop the local list so the
      // new run streams in against an empty grid.
      local.cards = [];
      local.hasContent = false;
      local.prompted = 0;
      if (root) {
        paintSummary(root, local.state);
        paintList(root);
      }
    },
    art_prompt_card(data, root) {
      const card = data.card;
      if (!card || !card.collector_number) return;
      W.streamUpsert(local.cards, card, (c) => c.collector_number);
      local.hasContent = true;
      local.prompted = local.cards.filter((c) => c.art_prompt).length;
      if (root) {
        paintSummary(root, local.state);
        paintList(root);
      }
    },
  });

  // ── Top-level render ──────────────────────────────────────────────────────

  function render({ root, state, stage, content, footer }) {
    local.state = state;
    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      bootstrap(root, state).catch((err) => {
        W.toast('Failed to load art prompts: ' + err.message, 'error');
        paintSummary(root, state);
        paintControls(root, state);
        paintList(root);
        paintFooter(getFooter(root), state);
      });
      paintFooter(footer, state);
      return;
    }

    const prevStatus = local.stageStatus;
    if (stage) local.stageStatus = stage.status;

    const justFinished =
      stage &&
      prevStatus !== local.stageStatus &&
      local.stageStatus !== 'pending' &&
      local.stageStatus !== 'running' &&
      !local.hasContent &&
      !local.bootstrapping;
    if (justFinished) {
      local.bootstrapping = true;
      bootstrap(root, state)
        .catch((err) => W.toast('Failed to refresh art prompts: ' + err.message, 'error'))
        .finally(() => {
          local.bootstrapping = false;
        });
      return;
    }
    paintFooter(footer, state);
    setLocked(local.locked);
  }

  function mountShellHtml() {
    return `
      <div data-role="ap-summary">
        <div class="wiz-stage-empty">Loading art prompts…</div>
      </div>
      <div data-role="ap-controls" style="display:none"></div>
      <div data-role="ap-list"></div>
    `;
  }

  // ── Bootstrap from server ─────────────────────────────────────────────────

  async function bootstrap(root, state) {
    local.state = state;
    const data = await W.fetchStageState(STAGE_ID);
    if (data) {
      local.cards = Array.isArray(data.cards) ? data.cards : [];
      local.artists = Array.isArray(data.artists) ? data.artists : [];
      local.entityCatalog = Array.isArray(data.entity_catalog) ? data.entity_catalog : [];
      local.cameoProbability =
        typeof data.cameo_probability === 'number' ? data.cameo_probability : local.cameoProbability;
      local.prompted = data.prompted || local.cards.filter((c) => c.art_prompt).length;
      local.hasContent = !!data.has_content || local.prompted > 0;
      if (data.stage_status) local.stageStatus = data.stage_status;
    }
    paintSummary(root, state);
    paintControls(root, state);
    paintList(root);
    paintFooter(getFooter(root), state);
  }

  // ── Summary + section header (§13) + cameo knob ──────────────────────────

  function paintSummary(root, state) {
    const slot = root.querySelector('[data-role="ap-summary"]');
    if (!slot) return;
    const isPast = isPastTab(state);
    const refreshLabel = local.hasContent ? 'Refresh AI…' : 'Generate';
    const refreshTitle = local.hasContent
      ? 'Re-author every card art prompt from scratch.'
      : 'Author art prompts for every card now.';

    const total = local.cards.length;
    const pct = Math.round((local.cameoProbability || 0) * 100);

    slot.innerHTML = `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">Art prompts</h3>
        <button type="button" class="wiz-btn-secondary wiz-refresh-btn"
                data-role="ap-refresh"
                title="${escAttr(isPast ? 'Use Edit above to revise past art prompts.' : refreshTitle)}"
                ${isPast ? 'disabled' : ''}>${escHtml(refreshLabel)}</button>
      </div>
      <p style="font-size:0.8rem;color:#888;margin:0.3rem 0 0.7rem">
        Each prompt is authored by an LLM in the voice of an assigned artist,
        grounded in the set's art direction + theme. Edit any prompt or reassign
        its artist below; a random subset features a style-guide cameo.
      </p>
      ${local.hasContent
        ? `<div class="wiz-ap-meta">
             <span>Prompts: <strong>${escHtml(String(local.prompted))}</strong> / ${escHtml(String(total))}</span>
             <span>Artists: <strong>${escHtml(String(local.artists.length))}</strong></span>
           </div>`
        : ''}
      <div class="wiz-ap-knob" data-role="ap-knob">
        <label for="ap-cameo">Cameo chance per card</label>
        <input type="range" id="ap-cameo" data-role="ap-cameo-range"
               min="0" max="100" step="5" value="${escAttr(String(pct))}"
               ${isPast ? 'disabled' : ''}>
        <span class="wiz-ap-knob-val" data-role="ap-cameo-val">${escHtml(String(pct))}%</span>
      </div>
    `;

    const refreshBtn = slot.querySelector('[data-role="ap-refresh"]');
    if (refreshBtn) refreshBtn.onclick = () => onRefresh();

    const range = slot.querySelector('[data-role="ap-cameo-range"]');
    const valEl = slot.querySelector('[data-role="ap-cameo-val"]');
    if (range) {
      range.oninput = () => {
        if (valEl) valEl.textContent = range.value + '%';
      };
      range.onchange = () => onCameoChange(parseInt(range.value, 10) / 100);
    }
  }

  // ── Controls — filter + group-by ──────────────────────────────────────────

  function paintControls(root, state) {
    const slot = root.querySelector('[data-role="ap-controls"]');
    if (!slot) return;
    if (!local.hasContent || local.cards.length === 0) {
      slot.style.display = 'none';
      return;
    }
    slot.style.display = 'flex';
    slot.className = 'wiz-ap-controls';
    if (slot.dataset.mounted === '1') return; // don't clobber in-progress filter text
    slot.dataset.mounted = '1';
    slot.innerHTML = `
      <input type="search" class="wiz-ap-filter" data-role="ap-filter"
             placeholder="Filter by name, artist, or prompt…" value="${escAttr(local.filter)}">
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

  // ── Card list ─────────────────────────────────────────────────────────────

  function paintList(root) {
    const slot = root.querySelector('[data-role="ap-list"]');
    if (!slot) return;
    if (!local.hasContent || local.cards.length === 0) {
      slot.innerHTML = W.emptyStatePanel({
        generating: aiBusy(),
        generatingMsg: 'Authoring art prompts…',
        emptyMsg: 'No art prompts yet — this stage runs automatically after Character References.',
      });
      return;
    }

    const q = local.filter.trim().toLowerCase();
    const visible = q
      ? local.cards.filter(
          (c) =>
            (c.name || '').toLowerCase().includes(q) ||
            (c.art_prompt || '').toLowerCase().includes(q) ||
            (c.artist || '').toLowerCase().includes(q) ||
            (c.collector_number || '').toLowerCase().includes(q)
        )
      : local.cards;

    if (visible.length === 0) {
      slot.innerHTML = `<div class="wiz-stage-empty">No cards match "${escHtml(q)}".</div>`;
      return;
    }

    let html;
    if (local.groupBy === 'rarity') {
      const groups = {};
      visible.forEach((c) => {
        const r = (c.rarity || 'common').toLowerCase();
        (groups[r] = groups[r] || []).push(c);
      });
      html = RARITY_ORDER.filter((r) => groups[r] && groups[r].length)
        .map(
          (r) => `
            <div class="wiz-ap-group">
              <div class="wiz-ap-group-header wiz-ap-rarity-${escAttr(r)}">
                ${escHtml(r.charAt(0).toUpperCase() + r.slice(1))}
                <span class="wiz-ap-group-count">${groups[r].length}</span>
              </div>
              ${groups[r].map((c) => cardRowHtml(c)).join('')}
            </div>`
        )
        .join('');
    } else {
      html = visible.map((c) => cardRowHtml(c)).join('');
    }
    slot.innerHTML = html;
    bindRows(root);
    setLocked(local.locked); // freshly-painted controls inherit the lock state
  }

  // ── Entity tags (the unified source: what each card features) ─────────────

  function entityName(key) {
    const hit = local.entityCatalog.find((e) => e.entity_key === key);
    if (hit && hit.name) return hit.name;
    return String(key || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function tagChipsHtml(card, isPast) {
    const tags = Array.isArray(card.entity_tags) ? card.entity_tags : [];
    const chips = tags
      .map((t) => {
        const key = t.entity_key || '';
        const kind = t.kind || 'entity';
        const remove = isPast
          ? ''
          : `<button type="button" class="wiz-ap-chip-x" data-role="ap-tag-remove" data-key="${escAttr(key)}" title="Remove tag" aria-label="Remove ${escAttr(entityName(key))}">×</button>`;
        return `<span class="wiz-ap-chip" data-key="${escAttr(key)}">${escHtml(entityName(key))}<span class="wiz-ap-chip-kind">${escHtml(kind)}</span>${remove}</span>`;
      })
      .join('');

    // The add-picker offers catalog entities not already tagged on this card.
    const tagged = new Set(tags.map((t) => t.entity_key));
    const addOpts = local.entityCatalog
      .filter((e) => !tagged.has(e.entity_key))
      .map(
        (e) =>
          `<option value="${escAttr(e.entity_key)}">${escHtml(e.name || e.entity_key)} (${escHtml(e.kind)})</option>`
      )
      .join('');
    const adder =
      isPast || !addOpts
        ? ''
        : `<select class="wiz-ap-tag-add" data-role="ap-tag-add" title="Add an entity this card features">
             <option value="">+ tag…</option>${addOpts}
           </select>`;

    const empty = tags.length || adder ? '' : '<span class="wiz-ap-chips-empty">no entities tagged</span>';
    return `<div class="wiz-ap-chips" data-role="ap-chips"><span class="wiz-ap-chips-label">Refs</span>${chips}${empty}${adder}</div>`;
  }

  function artistOptions(selected) {
    const names = local.artists.slice();
    if (selected && !names.includes(selected)) names.unshift(selected);
    if (!names.length) return '';
    return names
      .map(
        (n) =>
          `<option value="${escAttr(n)}" ${n === selected ? 'selected' : ''}>${escHtml(n)}</option>`
      )
      .join('');
  }

  function cardRowHtml(card) {
    const cn = card.collector_number || '';
    const prompt = card.art_prompt || '';
    const isPast = isPastTab(local.state);
    const colorsHtml =
      Array.isArray(card.colors) && card.colors.length
        ? card.colors
            .map((c) => `<span class="wiz-ap-pip wiz-ap-pip-${escAttr(c)}">${escHtml(c)}</span>`)
            .join('')
        : '<span class="wiz-ap-pip wiz-ap-pip-C">C</span>';

    const artistControl = local.artists.length
      ? `<select class="wiz-ap-artist-select" data-role="ap-artist" ${isPast ? 'disabled' : ''}>
           ${artistOptions(card.artist)}
         </select>`
      : `<span class="wiz-ap-artist-static">${escHtml(card.artist || 'AI Generated')}</span>`;

    // DFC faces: if the top-level prompt is empty but faces carry prompts, show them read-only.
    const faceParts =
      !prompt && Array.isArray(card.card_faces)
        ? card.card_faces
            .filter((f) => f.art_prompt)
            .map(
              (f) =>
                `<div class="wiz-ap-face"><span class="wiz-ap-face-name">${escHtml(f.name)}</span>` +
                `<span class="wiz-ap-face-prompt">${escHtml(f.art_prompt)}</span></div>`
            )
            .join('')
        : '';

    return `
      <div class="wiz-ap-card-row ${prompt ? '' : 'wiz-ap-card-row--no-prompt'}" data-cn="${escAttr(cn)}">
        <div class="wiz-ap-card-meta">
          <span class="wiz-ap-card-num">${escHtml(cn)}</span>
          <span class="wiz-ap-pips">${colorsHtml}</span>
          <span class="wiz-ap-card-name">${escHtml(card.name || '(unnamed)')}</span>
          ${W.rarityPill ? W.rarityPill(card.rarity) : ''}
          <span class="wiz-ap-type">${escHtml(card.type_line || '')}</span>
        </div>
        ${tagChipsHtml(card, isPast)}
        <div class="wiz-ap-artist-row">
          <label class="wiz-ap-artist-label">Artist</label>
          ${artistControl}
        </div>
        ${faceParts
          ? `<div class="wiz-ap-faces">${faceParts}</div>`
          : `<textarea class="wiz-ap-prompt-edit" data-role="ap-prompt" rows="3"
                       placeholder="No prompt yet — type one or hit Refresh AI." ${isPast ? 'disabled' : ''}>${escHtml(prompt)}</textarea>`}
        ${isPast
          ? ''
          : `<div class="wiz-ap-row-actions">
               <button type="button" class="wiz-btn-secondary wiz-ap-save-btn" data-role="ap-save" disabled>Save</button>
               <span class="wiz-ap-save-note" data-role="ap-save-note"></span>
             </div>`}
      </div>
    `;
  }

  function bindRows(root) {
    root.querySelectorAll('.wiz-ap-card-row[data-cn]').forEach((rowEl) => {
      const cn = rowEl.getAttribute('data-cn');

      // Entity-tag chips: remove (×) + add (picker). Present on the latest tab only.
      rowEl.querySelectorAll('[data-role="ap-tag-remove"]').forEach((btn) => {
        btn.onclick = () => {
          const card = local.cards.find((c) => c.collector_number === cn);
          if (!card) return;
          const key = btn.getAttribute('data-key');
          const next = (card.entity_tags || []).filter((t) => t.entity_key !== key);
          onTagsChange(cn, next);
        };
      });
      const addSel = rowEl.querySelector('[data-role="ap-tag-add"]');
      if (addSel) {
        addSel.onchange = () => {
          const key = addSel.value;
          if (!key) return;
          const card = local.cards.find((c) => c.collector_number === cn);
          if (!card) return;
          if ((card.entity_tags || []).some((t) => t.entity_key === key)) return;
          const cat = local.entityCatalog.find((e) => e.entity_key === key);
          const next = (card.entity_tags || []).concat([
            { entity_key: key, kind: cat ? cat.kind : 'entity' },
          ]);
          onTagsChange(cn, next);
        };
      }

      const promptEl = rowEl.querySelector('[data-role="ap-prompt"]');
      const artistEl = rowEl.querySelector('[data-role="ap-artist"]');
      const saveBtn = rowEl.querySelector('[data-role="ap-save"]');
      if (!saveBtn) return; // past tab — no editing controls

      const markDirty = () => {
        saveBtn.disabled = false;
        const note = rowEl.querySelector('[data-role="ap-save-note"]');
        if (note) note.textContent = '';
      };
      if (promptEl) promptEl.addEventListener('input', markDirty);
      if (artistEl) artistEl.addEventListener('change', markDirty);

      saveBtn.onclick = () => onSaveRow(cn, rowEl, promptEl, artistEl, saveBtn);
    });
  }

  // ── Save one edited row (no AI) ───────────────────────────────────────────

  async function onSaveRow(cn, rowEl, promptEl, artistEl, saveBtn) {
    if (local.locked) return;
    const payload = { collector_number: cn };
    if (promptEl) payload.art_prompt = promptEl.value;
    if (artistEl) payload.artist = artistEl.value;
    const note = rowEl.querySelector('[data-role="ap-save-note"]');
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving…';
    try {
      const resp = await fetch('/api/wizard/art_prompts/save-card', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        W.reportError(resp, data, 'Save failed');
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save';
        return;
      }
      if (data.tile) {
        W.streamUpsert(local.cards, data.tile, (c) => c.collector_number);
        local.prompted = local.cards.filter((c) => c.art_prompt).length;
      }
      saveBtn.textContent = 'Save';
      if (note) note.textContent = 'Saved ✓';
    } catch (err) {
      W.toast('Network error: ' + (err && err.message ? err.message : err), 'error');
      saveBtn.disabled = false;
      saveBtn.textContent = 'Save';
    }
  }

  // ── Entity-tag override (no AI — persists a manual per-card tag set) ───────

  async function onTagsChange(cn, nextTags) {
    if (local.locked) return;
    // Optimistic: reflect immediately, then reconcile from the server tile.
    const card = local.cards.find((c) => c.collector_number === cn);
    if (card) card.entity_tags = nextTags;
    paintList(bodyRoot());
    try {
      const resp = await fetch('/api/wizard/art_prompts/tags', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ collector_number: cn, tags: nextTags }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        W.reportError(resp, data, 'Could not save entity tags');
        return;
      }
      if (data.tile) {
        W.streamUpsert(local.cards, data.tile, (c) => c.collector_number);
        paintList(bodyRoot());
      }
    } catch (err) {
      W.toast('Network error: ' + (err && err.message ? err.message : err), 'error');
    }
  }

  // ── Cameo knob (no AI — pure config) ──────────────────────────────────────

  async function onCameoChange(prob) {
    local.cameoProbability = prob;
    try {
      const resp = await fetch('/api/wizard/art_prompts/knobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cameo_probability: prob }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        W.reportError(resp, data, 'Could not save cameo chance');
        return;
      }
      W.toast('Cameo chance set to ' + Math.round(prob * 100) + '%', 'success');
    } catch (err) {
      W.toast('Network error: ' + (err && err.message ? err.message : err), 'error');
    }
  }

  // ── Refresh: re-author all prompts under the AI lock (§7) ─────────────────

  async function onRefresh() {
    if (local.locked) return;
    const root = bodyRoot();
    const state = local.state;
    await W.runAiAction({
      isLocked: () => local.locked,
      setLocked,
      confirm: () =>
        local.hasContent ? 'Re-author every art prompt? Current prompts are replaced.' : '',
      busyLabel: local.hasContent ? 'Re-authoring art prompts…' : 'Authoring art prompts…',
      run: async ({ post }) => {
        const data = await post(
          '/api/wizard/art_prompts/refresh',
          { cameo_probability: local.cameoProbability },
          'Refresh failed'
        );
        if (!data) return;
        local.cards = Array.isArray(data.cards) ? data.cards : [];
        local.artists = Array.isArray(data.artists) ? data.artists : local.artists;
        if (Array.isArray(data.entity_catalog)) local.entityCatalog = data.entity_catalog;
        local.prompted = data.prompted || local.cards.filter((c) => c.art_prompt).length;
        local.hasContent = !!data.has_content || local.prompted > 0;
        if (typeof data.cameo_probability === 'number') local.cameoProbability = data.cameo_probability;
        if (data.stage_status) local.stageStatus = data.stage_status;
        if (root) {
          paintSummary(root, state);
          paintControls(root, state);
          paintList(root);
          paintFooter(getFooter(root), state);
        }
        W.toast('Art prompts regenerated.', 'success');
      },
    });
  }

  // ── Footer — art_prompts is never review_eligible (§1) ────────────────────

  function paintFooter(footer, state) {
    if (!footer) return;
    const isLatest = !state || state.latestTabId === STAGE_ID;
    const isPaused = local.stageStatus === 'paused_for_review';
    const isCompleted = local.stageStatus === 'completed';
    const next = W.nextStageEntryAfter(STAGE_ID);
    const nextName = next ? next.name : 'the next stage';
    // The saved/reopened dead-end: art prompts completed but the pipeline
    // persisted PAUSED with a later stage pending and no PAUSED_FOR_REVIEW
    // pause. Like isPaused, Next must RESUME the engine (a plain navigation
    // would strand it on the completed tip), so fold it into resumeEngine.
    const resumeEngine = isPaused || W.completedTipCanAdvance(state, STAGE_ID);
    const nextBtn = next
      ? `<button type="button" class="wiz-btn-primary" data-role="ap-next">Next: ${escHtml(next.name)} →</button>`
      : '';

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Past tab — use Edit above to revise art prompts.</span>`;
    } else if (resumeEngine) {
      html = `${nextBtn}<span class="wiz-footer-note">Paused after art prompts — continue when ready.</span>`;
    } else if (isCompleted) {
      html = `${nextBtn}<span class="wiz-footer-complete">✓ Art prompts authored — engine will continue to ${escHtml(nextName)}.</span>`;
    } else if (local.stageStatus === 'running') {
      html = `<span class="wiz-footer-note">Authoring art prompts…</span>`;
    } else {
      html = `<span class="wiz-footer-note">Runs automatically; no review step.</span>`;
    }
    W.paintFooter(footer, html, { role: 'ap-next', onClick: () => onGoNext(next, resumeEngine) });
  }

  function onGoNext(next, resumeEngine) {
    if (local.locked) return;
    if (!resumeEngine) {
      window.location.assign(next ? `/pipeline/${next.id}` : '/pipeline');
      return;
    }
    return W.advanceStage({
      stageId: STAGE_ID,
      isLocked: () => local.locked,
      setLocked,
      btnRole: 'ap-next',
    });
  }

  // ── Form lock (§3) ────────────────────────────────────────────────────────

  function aiBusy() {
    return local.locked || local.stageStatus === 'running';
  }

  function setLocked(locked) {
    local.locked = !!locked;
    W.setTabLocked(bodyRoot(), aiBusy(), {
      lockClass: 'wiz-ap-locked',
      selectors: [
        '[data-role="ap-refresh"]',
        '[data-role="ap-cameo-range"]',
        '[data-role="ap-filter"]',
        '[data-role="ap-group-rarity"]',
        '[data-role="ap-prompt"]',
        '[data-role="ap-artist"]',
        '[data-role="ap-save"]',
        '[data-role="ap-tag-add"]',
        '[data-role="ap-tag-remove"]',
      ],
    });
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  const bodyRoot = () => W.tabRoot(STAGE_ID);
  const getFooter = (root) => W.tabFooter(root);
  const isPastTab = (state) => W.isPastTab(STAGE_ID, state);

  // ── Scoped styles ─────────────────────────────────────────────────────────

  (function injectStyles() {
    if (document.getElementById('wiz-art_prompts-styles')) return;
    const style = document.createElement('style');
    style.id = 'wiz-art_prompts-styles';
    style.textContent = `
      .wiz-ap-meta {
        display: flex; gap: 1.4rem; font-size: 0.8rem; color: #888;
        margin-bottom: 0.6rem;
      }
      .wiz-ap-meta strong { color: #ddd; }

      .wiz-ap-knob {
        display: flex; align-items: center; gap: 0.6rem;
        font-size: 0.8rem; color: #aaa; margin-bottom: 0.9rem;
        background: #0f1729; border: 1px solid #1f2540; border-radius: 6px;
        padding: 0.5rem 0.8rem;
      }
      .wiz-ap-knob label { white-space: nowrap; }
      .wiz-ap-knob input[type="range"] { flex: 1 1 160px; max-width: 280px; accent-color: #4a9eff; }
      .wiz-ap-knob-val { font-variant-numeric: tabular-nums; color: #ddd; min-width: 2.5rem; }

      .wiz-ap-controls { align-items: center; gap: 0.75rem; margin-bottom: 0.85rem; flex-wrap: wrap; }
      .wiz-ap-filter {
        flex: 1 1 220px; min-width: 160px; padding: 0.35rem 0.6rem;
        background: #0f1729; border: 1px solid #2a3560; border-radius: 4px;
        color: #ddd; font-size: 0.82rem; font-family: inherit;
      }
      .wiz-ap-filter:focus { outline: none; border-color: #4a9eff; }
      .wiz-ap-group-label {
        font-size: 0.8rem; color: #888; display: flex; align-items: center;
        gap: 0.35rem; cursor: pointer; white-space: nowrap;
      }

      .wiz-ap-group { margin-bottom: 0.5rem; }
      .wiz-ap-group-header {
        display: flex; align-items: center; gap: 0.5rem; font-size: 0.75rem;
        font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
        padding: 0.3rem 0.6rem; border-radius: 4px 4px 0 0; background: #12193a;
        border: 1px solid #1f2540; border-bottom: none; color: #888;
      }
      .wiz-ap-group-header.wiz-ap-rarity-mythic  { color: #e8954a; border-color: #4a2510; }
      .wiz-ap-group-header.wiz-ap-rarity-rare     { color: #e8cc4a; border-color: #3a3010; }
      .wiz-ap-group-header.wiz-ap-rarity-uncommon { color: #aac4d0; border-color: #1f3040; }
      .wiz-ap-group-header.wiz-ap-rarity-common   { color: #bbb;    border-color: #222840; }
      .wiz-ap-group-count {
        margin-left: auto; font-size: 0.68rem; padding: 1px 5px;
        background: rgba(74,158,255,0.1); color: #4a9eff; border-radius: 3px;
      }

      .wiz-ap-card-row {
        display: flex; flex-direction: column; gap: 0.4rem;
        padding: 0.6rem 0.75rem; border: 1px solid #1f2540; border-top: none;
        background: #0f1729;
      }
      .wiz-ap-group .wiz-ap-card-row:last-child { border-radius: 0 0 4px 4px; }
      .wiz-ap-card-row--no-prompt { background: #120f1a; }

      .wiz-ap-card-meta { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
      .wiz-ap-card-num {
        font-size: 0.68rem; color: #6a7da0;
        font-variant-numeric: tabular-nums; min-width: 3rem;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }
      .wiz-ap-pips { display: flex; gap: 2px; }
      .wiz-ap-pip {
        display: inline-block; width: 14px; height: 14px; border-radius: 50%;
        font-size: 0.55rem; font-weight: 700; text-align: center; line-height: 14px;
        background: #333; color: #fff;
      }
      .wiz-ap-pip-W { background: #f0e6c8; color: #333; }
      .wiz-ap-pip-U { background: #1a6ab0; }
      .wiz-ap-pip-B { background: #2a1a2e; border: 1px solid #6a3e7e; }
      .wiz-ap-pip-R { background: #b03020; }
      .wiz-ap-pip-G { background: #1a6a30; }
      .wiz-ap-pip-C { background: #666; }
      .wiz-ap-card-name { font-size: 0.85rem; font-weight: 600; color: #ddd; }
      .wiz-ap-type {
        font-size: 0.73rem; color: #666; flex: 1 1 auto; text-align: right;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
      }

      .wiz-ap-chips {
        display: flex; align-items: center; gap: 0.35rem; flex-wrap: wrap;
        font-size: 0.72rem;
      }
      .wiz-ap-chips-label {
        font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.05em;
        color: #5d6f92; margin-right: 0.15rem;
      }
      .wiz-ap-chips-empty { font-size: 0.72rem; color: #555; font-style: italic; }
      .wiz-ap-chip {
        display: inline-flex; align-items: center; gap: 0.3rem;
        padding: 0.1rem 0.45rem; border-radius: 10px;
        background: #15233f; border: 1px solid #28406a; color: #cdd6e6;
      }
      .wiz-ap-chip-kind {
        font-size: 0.6rem; text-transform: uppercase; letter-spacing: 0.04em;
        color: #6a8bc0;
      }
      .wiz-ap-chip-x {
        border: none; background: none; color: #7a8baa; cursor: pointer;
        font-size: 0.85rem; line-height: 1; padding: 0; margin-left: 0.05rem;
      }
      .wiz-ap-chip-x:hover { color: #e86a6a; }
      .wiz-ap-tag-add {
        padding: 0.1rem 0.3rem; background: #1a1a2e; border: 1px solid #333;
        border-radius: 10px; color: #9fb0d0; font-size: 0.7rem; font-family: inherit;
      }
      .wiz-ap-tag-add:focus { outline: none; border-color: #4a9eff; }

      .wiz-ap-artist-row { display: flex; align-items: center; gap: 0.45rem; }
      .wiz-ap-artist-label {
        font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.05em; color: #5d6f92;
      }
      .wiz-ap-artist-select {
        padding: 0.25rem 0.45rem; background: #1a1a2e; border: 1px solid #333;
        border-radius: 4px; color: #e0e0e0; font-size: 0.76rem; font-family: inherit;
      }
      .wiz-ap-artist-select:focus { outline: none; border-color: #4a9eff; }
      .wiz-ap-artist-static { font-size: 0.76rem; color: #aaa; }

      .wiz-ap-prompt-edit {
        width: 100%; box-sizing: border-box; resize: vertical;
        padding: 0.45rem 0.55rem; background: #0b1120; border: 1px solid #2a3560;
        border-radius: 4px; color: #cdd6e6; font-size: 0.8rem; line-height: 1.5;
        font-family: inherit;
      }
      .wiz-ap-prompt-edit:focus { outline: none; border-color: #4a9eff; }

      .wiz-ap-row-actions { display: flex; align-items: center; gap: 0.6rem; }
      .wiz-ap-save-note { font-size: 0.72rem; color: #45c98a; }

      .wiz-ap-faces { display: flex; flex-direction: column; gap: 0.25rem; }
      .wiz-ap-face { display: flex; flex-direction: column; gap: 0.15rem; }
      .wiz-ap-face-name {
        font-size: 0.7rem; font-weight: 600; color: #666;
        text-transform: uppercase; letter-spacing: 0.05em;
      }
      .wiz-ap-face-prompt { font-size: 0.8rem; color: #aaa; line-height: 1.5; }

      .wiz-ap-locked .wiz-ap-prompt-edit,
      .wiz-ap-locked .wiz-ap-artist-select,
      .wiz-ap-locked .wiz-ap-filter { cursor: not-allowed; opacity: 0.55; }
    `;
    document.head.appendChild(style);
  })();
})();
