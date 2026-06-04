/**
 * Wizard Skeleton tab — the deterministic default skeleton vs its LLM relabel.
 *
 * Registers via ``W.registerStageRenderer('skeleton', ...)`` so the standard
 * wizard_stage.js shell owns the header (status pill, break-point toggle, Edit
 * button); we paint the body + footer.
 *
 * Skeleton Generation is one stage that builds the deterministic default
 * skeleton, then rewrites each slot's one-line descriptor with the LLM to fit
 * the set (theme / constraints / mechanics / requests). The tab surfaces those
 * two halves as two refreshable steps (mirroring the Theme tab's section
 * pattern):
 *   Step 1 — Structural knobs: the theme-tuned knob controls. "Refresh with AI"
 *            re-tunes them (honoring pins) and CASCADES into a skeleton rebuild
 *            + relabel — same as refreshing the top-level Theme also refreshes
 *            its sub-sections.
 *   Step 2 — Skeleton: each slot's DEFAULT descriptor diffed against the LLM's
 *            TWEAKED descriptor (a word-level diff highlights changes), editable.
 *            "Refresh" rebuilds the matrix from the CURRENT knob values, then
 *            runs the LLM relabel over it.
 * Both refreshes orchestrate the rebuild → relabel calls client-side so each
 * streamed slot lands in the right row. The stage auto-runs both on the happy
 * path, so there's no manual "generate" gate — these are the §13 re-roll surface.
 *
 * Conventions: §1 Save & Continue footer, §3 form lock, §6 past-tab edit
 * cascade (via wizard_stage.js), §8 status pill, §13 section Refresh button.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'skeleton';

  const local = {
    initialized: false,
    slots: [],        // [{slot_id, default_text, tweaked_text, reserved_card}]
    hasTweaked: false,
    setParams: { set_name: '', set_size: 0 },
    themeSummary: '',
    modelId: '',
    stageStatus: 'pending',
    locked: false,
    bootstrapping: false,
    // Live relabel streaming state. `streaming` is true between a reset and the
    // matching done; `streamUpdates` accumulates slot updates by id so a tab
    // mounted mid-relabel can merge them over the (still-default) /state slots.
    // `incomplete` is the durable "relabel kept partial" flag from the server.
    streaming: false,
    incomplete: false,
    streamUpdates: {},
    // Structural knobs (Phase 0). `knobs` is the value map, `knobSpecs` the
    // bounds the controls render from, `cycles` the reserved cycle families,
    // `knobsDefaulted` true when the phase-0 tuner fell back to defaults.
    knobs: {},
    knobSpecs: [],
    cycles: [],
    // Dropdown option lists for the cycle editor (spans / rarities / card_types),
    // from the backend (single source of truth); populated by bootstrap.
    cycleOptions: null,
    // The irregular-subtype bucket the picker offers ({value,label}); the chosen
    // members live on `knobs.irregular_subtypes` (theme-driven, RNG fills the rest).
    irregularSubtypeOptions: [],
    knobsDefaulted: false,
    knobWarnings: [],
    // True once a knob is hand-edited but not yet applied: knob edits only rebuild
    // the skeleton on the next Refresh, so we flag the grid is stale meanwhile.
    knobsDirty: false,
  };

  W.registerStageRenderer(STAGE_ID, render);
  // Registered at module load (not in render) so live relabel events are caught
  // even when the engine runs the skeleton stage while another tab is active.
  // The handlers resolve their own root via bodyRoot(); the root registerStream
  // passes is ignored.
  W.registerStream(STAGE_ID, {
    skeleton_relabel_reset: onRelabelReset,
    skeleton_slot: onRelabelSlot,
    skeleton_relabel_done: onRelabelDone,
  });

  // ----------------------------------------------------------------------

  function render({ root, state, stage, content, footer }) {
    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      bootstrap(root, state).catch(err =>
        W.toast('Failed to load skeleton state: ' + err.message, 'error'));
      paintFooter(footer, state);
      return;
    }
    // Re-render path: the stage writes skeleton.json synchronously, so a
    // bootstrap that fired mid-run sees no tweaks. When status settles and we
    // still have none, re-pull so the diff fills once the relabel lands.
    const prev = local.stageStatus;
    if (stage) local.stageStatus = stage.status;
    const justSettled =
      stage
      && prev !== local.stageStatus
      && local.stageStatus !== 'pending'
      && local.stageStatus !== 'running'
      && !local.hasTweaked
      && !local.bootstrapping;
    if (justSettled) {
      local.bootstrapping = true;
      bootstrap(root, state)
        .catch(err => W.toast('Failed to refresh skeleton: ' + err.message, 'error'))
        .finally(() => { local.bootstrapping = false; });
      return;
    }
    paintFooter(footer, state);
    // Re-sync the form lock: an SSE event may have flipped the stage to
    // `running` (engine relabel in flight) since the last paint.
    applyFormLock();
  }

  function mountShellHtml() {
    return `
      <section class="wiz-theme-section wiz-skel-step" data-role="skel-knobs">
        <div class="wiz-skel-loading">Loading knobs…</div>
      </section>
      <section class="wiz-theme-section wiz-skel-step" data-role="skel-skeleton">
        <div data-role="skel-summary">
          <div class="wiz-skel-loading">Loading skeleton…</div>
        </div>
        <div class="wiz-skel-grid" data-role="skel-grid"></div>
      </section>
    `;
  }

  // ----------------------------------------------------------------------

  async function bootstrap(root, state) {
    const data = await W.fetchStageState(STAGE_ID);
    if (data) {
      local.slots = Array.isArray(data.slots) ? data.slots : [];
      local.setParams = data.set_params || local.setParams;
      local.themeSummary = data.theme_summary || '';
      local.modelId = data.model_id || '';
      local.stageStatus = data.stage_status || local.stageStatus;
      local.incomplete = !!data.incomplete;
      local.knobs = data.knobs || {};
      local.knobSpecs = Array.isArray(data.knob_specs) ? data.knob_specs : [];
      local.cycles = Array.isArray(data.cycles) ? data.cycles : [];
      if (data.cycle_options) local.cycleOptions = data.cycle_options;
      if (Array.isArray(data.irregular_subtype_options)) {
        local.irregularSubtypeOptions = data.irregular_subtype_options;
      }
      local.knobsDefaulted = !!data.knobs_defaulted;
      local.knobWarnings = Array.isArray(data.knob_warnings) ? data.knob_warnings : [];
      // Re-apply any provisional slots that streamed in before this fetch landed
      // (a tab mounted mid-relabel: /state returns the pre-relabel default skeleton
      // while the live stream is already overwriting individual slots).
      local.slots.forEach(s => {
        const upd = local.streamUpdates[s.slot_id];
        if (!upd) return;
        s.tweaked_text = upd.tweaked_text;
        s.reserved_card = upd.reserved_card;  // replace (empty clears a stale tag)
      });
      local.hasTweaked = !!data.has_tweaked || local.slots.some(s => isChanged(s));
    }

    paintSummary(root, state);
    paintKnobs(root, state);
    paintGrid(root, state);
    paintFooter(getFooter(root), state);
    applyFormLock();
  }

  // ----------------------------------------------------------------------
  // Knobs panel — structural knobs (Phase 0) + cycles, above the slot diff
  // ----------------------------------------------------------------------

  const GROUP_LABELS = {
    rarity: 'Rarity weights',
    multicolor: 'Multicolor density',
    colorless: 'Colorless density',
    creature: 'Creature density',
    noncreature: 'Non-creature type bias',
    special: 'Planeswalkers & signposts',
    subtype: 'Card subtype mix',
  };

  function paintKnobs(root, state) {
    const slot = root.querySelector('[data-role="skel-knobs"]');
    if (!slot) return;
    if (!local.knobSpecs.length) { slot.innerHTML = ''; return; }
    const isPast = isPastTab(state);
    const disabled = isPast || aiBusy();

    const tunedCount = local.knobSpecs.filter(s => Number(local.knobs[s.key]) !== Number(s.default)).length;
    const provSummary = local.knobsDefaulted
      ? '<span class="wiz-skel-knob-prov default">defaults (AI tuning unavailable)</span>'
      : `<span class="wiz-skel-knob-prov ${tunedCount ? 'ai' : 'default'}">${tunedCount} knob(s) tuned</span>`;
    const warnHtml = (local.knobWarnings || []).length
      ? `<div class="wiz-skel-incomplete">⚠ ${local.knobWarnings.map(escHtml).join('<br>')}</div>`
      : '';
    const title = isPast
      ? 'Use Edit above to revise a past skeleton.'
      : 'Re-tune the knobs with AI (pinned knobs survive), then rebuild + relabel the skeleton below.';

    slot.innerHTML = `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">Step 1 · Structural knobs ${provSummary}</h3>
        <button type="button" class="wiz-btn-secondary wiz-refresh-btn" data-role="knob-refresh"
                title="${escAttr(title)}" ${disabled ? 'disabled' : ''}>Refresh with AI…</button>
      </div>
      <p class="wiz-theme-section-desc">Theme-tuned structure for the skeleton — the AI proposes within research-derived ranges, you adjust. Pin a knob to keep it on a re-tune. Hand-edits take effect when you Refresh the skeleton (Step 2); "Refresh with AI" re-tunes them and rebuilds the skeleton for you.</p>
      ${warnHtml}
      <div class="wiz-skel-knob-groups" data-role="skel-knob-grid"></div>
      <fieldset class="wiz-skel-cycle-box" data-role="irregular-picks"></fieldset>
      <fieldset class="wiz-skel-cycle-box">
        <legend>Cycles</legend>
        <p class="wiz-skel-cycle-blurb">Balance-preserving card families — one member per colour, pair, or trio, sharing a template. They're carved out of the rarity budget first. Add or edit them here; changes apply on the next Refresh.</p>
        <div class="wiz-skel-cycle-list" data-role="cycle-list"></div>
        <button type="button" class="wiz-btn-add" data-role="cycle-add" ${disabled ? 'disabled' : ''}>+ Add cycle</button>
      </fieldset>
      <div class="wiz-skel-knob-pending" data-role="knob-pending" ${local.knobsDirty ? '' : 'hidden'}>
        Knob/cycle edits pending — Refresh the skeleton (Step 2) to rebuild from them.
      </div>`;
    renderKnobGrid(slot, disabled);
    paintIrregularPicks(slot, disabled);
    const refresh = slot.querySelector('[data-role="knob-refresh"]');
    if (refresh) refresh.onclick = onKnobsRefresh;
    paintCycleList(slot, disabled);
    const addBtn = slot.querySelector('[data-role="cycle-add"]');
    if (addBtn) addBtn.onclick = onAddCycle;
  }

  // Render Step-1's knob grid via the shared W.KnobPanel: grouped fieldsets,
  // pinnable, range hints. A hand edit stamps 'user' provenance + flags the
  // grid dirty (it doesn't rebuild until a Refresh); a pin toggles the keep-list.
  function renderKnobGrid(slot, disabled) {
    W.KnobPanel(slot.querySelector('[data-role="skel-knob-grid"]'), {
      specs: local.knobSpecs,
      values: local.knobs,
      provenance: local.knobs.provenance || {},
      defaultProvenance: 'default',
      disabled,
      groups: GROUP_LABELS,
      rangeHint: true,
      pinned: local.knobs.pinned || [],
      event: 'input',
      classes: {
        group: 'wiz-skel-knob-group',
        row: 'wiz-skel-knob',
        range: 'wiz-skel-knob-range',
        pin: 'wiz-skel-knob-pin',
      },
      onChange: (key, value) => {
        local.knobs[key] = value;
        local.knobs.provenance = local.knobs.provenance || {};
        local.knobs.provenance[key] = 'user'; // §5 provenance: hand edit
        setKnobsDirty(true);
      },
      onPin: (key, checked) => {
        local.knobs.pinned = (local.knobs.pinned || []).filter(k => k !== key);
        if (checked) local.knobs.pinned.push(key);
      },
    });
  }

  // Irregular-subtype picker: WHICH deciduous specials (saga/class/shrine/…) the
  // theme weaves in. The order a member is checked is its preference order; the
  // `irregular_subtype_count` knob caps how many actually apply, and an empty list
  // hands the choice back to the seeded RNG. A hand-edit stamps 'user' provenance
  // and flags the grid dirty, exactly like a knob edit (rebuild on next Refresh).
  function paintIrregularPicks(slot, disabled) {
    const box = slot.querySelector('[data-role="irregular-picks"]');
    if (!box) return;
    const opts = local.irregularSubtypeOptions || [];
    if (!opts.length) { box.innerHTML = ''; box.hidden = true; return; }
    box.hidden = false;
    const picks = Array.isArray(local.knobs.irregular_subtypes)
      ? local.knobs.irregular_subtypes : [];
    const prov = (local.knobs.provenance || {}).irregular_subtypes || 'default';
    const provLabel = prov === 'ai' ? 'AI' : (prov === 'user' ? 'edited' : 'auto');
    const rows = opts.map(o => {
      const rank = picks.indexOf(o.value);
      const checked = rank >= 0;
      const order = checked ? `<span class="wiz-skel-irr-rank">#${rank + 1}</span>` : '';
      return `
        <label class="wiz-skel-irr-pick${checked ? ' is-on' : ''}">
          <input type="checkbox" data-role="irr-pick" value="${escAttr(o.value)}"
                 ${checked ? 'checked' : ''} ${disabled ? 'disabled' : ''}>
          <span class="wiz-skel-irr-name">${escHtml(o.label)}</span>${order}
        </label>`;
    }).join('');
    box.innerHTML = `
      <legend>Irregular subtype picks <span class="wiz-skel-knob-prov ${prov}">${provLabel}</span></legend>
      <p class="wiz-skel-cycle-blurb">Which deciduous "specials" the theme weaves in — saga, class, shrine, enchantment creature, colored artifact. Check those that fit (the order you check them is the preference order). The "Irregular subtypes" count above caps how many actually apply; leave all unchecked to let chance pick.</p>
      <div class="wiz-skel-irr-list">${rows}</div>`;
    box.querySelectorAll('[data-role="irr-pick"]').forEach(cb => {
      cb.onchange = () => onIrregularToggle(cb.value, cb.checked, slot, disabled);
    });
  }

  // Toggle one irregular-subtype pick, preserving check-order as preference order.
  function onIrregularToggle(value, on, slot, disabled) {
    let picks = Array.isArray(local.knobs.irregular_subtypes)
      ? local.knobs.irregular_subtypes.slice() : [];
    picks = picks.filter(v => v !== value);
    if (on) picks.push(value);
    local.knobs.irregular_subtypes = picks;
    local.knobs.provenance = local.knobs.provenance || {};
    local.knobs.provenance.irregular_subtypes = 'user';
    setKnobsDirty(true);
    paintIrregularPicks(slot, disabled);  // refresh the #rank badges
  }

  // ----------------------------------------------------------------------
  // Cycle editor — add / edit / remove cycles (Theme-tab card-requests UX).
  // The DOM rows are the source of truth while editing; collectCycles() reads
  // them into the knobs payload on Refresh (so edits flow into the rebuild).
  // ----------------------------------------------------------------------

  function paintCycleList(slot, disabled) {
    const list = slot.querySelector('[data-role="cycle-list"]');
    if (!list) return;
    list.innerHTML = '';
    (local.cycles || []).forEach(c => list.appendChild(cycleRow(c, disabled)));
  }

  function cycleRow(c, disabled) {
    const opts = local.cycleOptions || {};
    const spans = opts.spans || [
      { value: 'mono5', label: 'mono (5)' }, { value: 'pairs10', label: 'pairs (10)' },
      { value: 'allied5', label: 'allied (5)' }, { value: 'enemy5', label: 'enemy (5)' },
      { value: 'wedges5', label: 'wedges (5)' }, { value: 'shards5', label: 'shards (5)' },
    ];
    const rarities = opts.rarities || ['common', 'uncommon', 'rare', 'mythic'];
    const types = opts.card_types
      || ['creature', 'instant', 'sorcery', 'enchantment', 'artifact', 'planeswalker', 'land'];
    const dis = disabled ? 'disabled' : '';
    const sel = (v, want) => (v === want ? 'selected' : '');
    const item = document.createElement('div');
    item.className = 'wiz-skel-cycle-item';
    item.dataset.cycleId = c.id || newCycleId();
    item.innerHTML = `
      <div class="wiz-skel-cycle-row1">
        <input class="wiz-skel-cycle-name" data-role="cyc-name" placeholder="Cycle name (e.g. Energon Sources)"
               value="${escAttr(c.name || '')}" ${dis}>
        <select data-role="cyc-span" title="How the family spreads across colours" ${dis}>
          ${spans.map(s => `<option value="${escAttr(s.value)}" ${sel(s.value, c.span)}>${escHtml(s.label || s.value)}</option>`).join('')}
        </select>
        <select data-role="cyc-rarity" title="Rarity" ${dis}>
          ${rarities.map(r => `<option value="${escAttr(r)}" ${sel(r, c.rarity || 'uncommon')}>${escHtml(r)}</option>`).join('')}
        </select>
        <select data-role="cyc-type" title="Card type" ${dis}>
          ${types.map(t => `<option value="${escAttr(t)}" ${sel(t, c.card_type || 'creature')}>${escHtml(t)}</option>`).join('')}
        </select>
        <input type="number" data-role="cyc-cmc" min="0" max="12" title="CMC target (ignored for lands)"
               value="${c.cmc_target == null ? 3 : c.cmc_target}" ${dis}>
        <button type="button" class="wiz-btn-remove" data-role="cyc-remove" title="Remove cycle" ${dis}>&times;</button>
      </div>
      <input class="wiz-skel-cycle-template" data-role="cyc-template"
             placeholder="Template — the shared design brief every member follows (e.g. 'A dual land that taps for two colours and …')"
             value="${escAttr(c.template || '')}" ${dis}>`;
    item.querySelectorAll('input, select').forEach(el => {
      el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', () => setKnobsDirty(true));
    });
    // Lands have no mana value — zero the CMC when the type flips to land.
    const typeSel = item.querySelector('[data-role="cyc-type"]');
    const cmcInput = item.querySelector('[data-role="cyc-cmc"]');
    typeSel.addEventListener('change', () => {
      if (typeSel.value === 'land') cmcInput.value = 0;
    });
    item.querySelector('[data-role="cyc-remove"]').addEventListener('click', () => {
      item.remove();
      setKnobsDirty(true);
    });
    return item;
  }

  function onAddCycle() {
    const root = bodyRoot();
    const list = root && root.querySelector('[data-role="cycle-list"]');
    if (!list) return;
    const firstSpan = (local.cycleOptions && local.cycleOptions.spans && local.cycleOptions.spans[0]
      && local.cycleOptions.spans[0].value) || 'mono5';
    const row = cycleRow(
      { id: newCycleId(), name: '', span: firstSpan, rarity: 'uncommon', card_type: 'creature', cmc_target: 3, template: '' },
      false,
    );
    list.appendChild(row);
    setKnobsDirty(true);
    const name = row.querySelector('[data-role="cyc-name"]');
    if (name) name.focus();
  }

  // Read the cycle rows back into Cycle dicts for the knobs payload. The DOM is
  // authoritative while editing; rows with no name are dropped (a stray Add).
  // Falls back to the model when the editor isn't painted (past tab / pre-mount).
  function collectCycles() {
    const root = bodyRoot();
    const list = root && root.querySelector('[data-role="cycle-list"]');
    if (!list) return local.cycles || [];
    const out = [];
    list.querySelectorAll('.wiz-skel-cycle-item').forEach(item => {
      const name = item.querySelector('[data-role="cyc-name"]').value.trim();
      if (!name) return;
      out.push({
        id: item.dataset.cycleId,
        name,
        span: item.querySelector('[data-role="cyc-span"]').value,
        rarity: item.querySelector('[data-role="cyc-rarity"]').value,
        card_type: item.querySelector('[data-role="cyc-type"]').value,
        cmc_target: Number(item.querySelector('[data-role="cyc-cmc"]').value) || 0,
        template: item.querySelector('[data-role="cyc-template"]').value.trim(),
      });
    });
    return out;
  }

  function newCycleId() {
    return 'cyc-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 6);
  }

  // Show/hide the "knob edits pending" hint. A hand-edited knob doesn't rebuild
  // the skeleton until the next Refresh, so flag that the grid is now stale.
  function setKnobsDirty(dirty) {
    local.knobsDirty = !!dirty;
    const root = bodyRoot();
    if (!root) return;
    const note = root.querySelector('[data-role="knob-pending"]');
    if (note) note.hidden = !local.knobsDirty;
  }

  function knobValuesPayload() {
    const values = {};
    local.knobSpecs.forEach(s => { values[s.key] = local.knobs[s.key]; });
    // Carry the theme-driven irregular-subtype picks inside `knobs` so a
    // deterministic rebuild (/skeleton/knobs) preserves the choice instead of
    // dropping it (an AI re-tune re-decides them regardless).
    values.irregular_subtypes = local.knobs.irregular_subtypes || [];
    return {
      knobs: values,
      cycles: collectCycles(),
      pinned: local.knobs.pinned || [],
      provenance: local.knobs.provenance || {},
    };
  }

  // Step 1 refresh: re-tune the structural knobs with AI (honoring pins), then
  // cascade into a skeleton rebuild + relabel — mirrors the Theme tab's "refresh
  // the top level and the sub-levels refresh too" pattern.
  async function onKnobsRefresh() {
    await W.runAiAction({
      isLocked: () => local.locked,
      setLocked,
      confirm: () => (local.hasTweaked
        ? 'Re-tune the knobs with AI, then rebuild + relabel the skeleton? '
          + 'Your inline edits will be replaced.'
        : ''),
      busyLabel: 'Tuning structural knobs with AI…',
      // runRelabel already settles local.streaming on both paths; this is the
      // safety net for an early return / throw before it runs.
      onSettle: () => { local.streaming = false; },
      run: async ({ post, showBusy }) => {
        const root = bodyRoot();
        // Phase 0 — AI tune + deterministic rebuild. The tab's current knob values
        // go up as the tuner base, so unsaved hand-edits + pins are respected.
        const data = await post('/api/wizard/skeleton/knobs/tune', knobValuesPayload(), 'Tune failed');
        if (!data) return;
        applyKnobsResponse(data);
        W.toast(data.defaulted
          ? 'AI tuning unavailable — base knobs kept.'
          : 'Knobs re-tuned to the set.',
          data.defaulted ? 'warn' : 'success');
        // Phase 2 — cascade into the relabel over the freshly rebuilt skeleton.
        showBusy('Relabeling skeleton…');
        await runRelabel(root);
      },
    });
  }

  // A knobs endpoint rebuilt the default skeleton: adopt the new slots + knobs and
  // repaint. The relabel is gone (rebuild clears tweaked_text), so hasTweaked resets.
  function applyKnobsResponse(data) {
    if (Array.isArray(data.slots)) local.slots = data.slots;
    if (data.knobs) local.knobs = data.knobs;
    if (Array.isArray(data.knob_specs)) local.knobSpecs = data.knob_specs;
    if (Array.isArray(data.cycles)) local.cycles = data.cycles;
    if (data.cycle_options) local.cycleOptions = data.cycle_options;
    if (Array.isArray(data.irregular_subtype_options)) {
      local.irregularSubtypeOptions = data.irregular_subtype_options;
    }
    local.knobsDefaulted = !!data.knobs_defaulted;
    local.knobWarnings = Array.isArray(data.warnings) ? data.warnings : [];
    local.hasTweaked = local.slots.some(s => isChanged(s));
    local.knobsDirty = false;  // the rebuild consumed the current knob values
    const root = bodyRoot();
    if (!root) return;
    paintSummary(root, W.getState());
    paintKnobs(root, W.getState());
    paintGrid(root, W.getState());
    paintFooter(getFooter(root), W.getState());
    applyFormLock();
  }

  // ----------------------------------------------------------------------
  // Summary + §13 Refresh button
  // ----------------------------------------------------------------------

  function paintSummary(root, state) {
    const slot = root.querySelector('[data-role="skel-summary"]');
    if (!slot) return;
    const sp = local.setParams;
    const isPast = isPastTab(state);
    const label = 'Refresh…';
    const title = isPast
      ? 'Use Edit above to revise a past skeleton.'
      : 'Rebuild the skeleton from the current knobs, then re-run the LLM relabel. Your inline edits are replaced.';
    const changed = local.slots.filter(s => isChanged(s)).length;
    const placed = local.slots.filter(s => s.reserved_card).length;
    // While streaming, "Relabeled" tracks slots that have arrived this run so
    // the count visibly climbs; otherwise it's the diff count.
    const arrived = Object.keys(local.streamUpdates).length;
    const relabeledCell = local.streaming
      ? `${arrived} / ${local.slots.length}…`
      : String(changed);
    const pill = local.streaming
      ? '<span class="wiz-skel-livepill">● Relabeling live…</span>'
      : '';
    const banner = (local.incomplete && !local.streaming)
      ? `<div class="wiz-skel-incomplete">⚠ The relabel finished incomplete — some slots kept their
         default descriptor. The partial result is saved; edit them inline or
         <strong>Refresh…</strong> to try filling the rest.</div>`
      : '';
    slot.innerHTML = `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">Step 2 · Skeleton ${pill}</h3>
        <button type="button" class="wiz-btn-secondary wiz-refresh-btn"
                data-role="skel-refresh"
                title="${escAttr(title)}" ${isPast || aiBusy() ? 'disabled' : ''}>${escHtml(label)}</button>
      </div>
      <p class="wiz-theme-section-desc">The deterministic skeleton built from the knobs above, each slot rewritten by the LLM to fit the set. Refresh rebuilds it from the current knobs and re-themes it; changed parts are highlighted, and you can edit any tweaked line before continuing.</p>
      ${banner}
      <dl class="wiz-skel-context">
        <dt>Set</dt><dd>${escHtml(sp.set_name || '(unnamed)')}</dd>
        <dt>Slots</dt><dd>${escHtml(String(local.slots.length))}</dd>
        <dt>Relabeled</dt><dd>${relabeledCell}</dd>
        <dt>Requests placed</dt><dd>${placed}</dd>
        <dt>Model</dt><dd>${escHtml(local.modelId || '?')}</dd>
      </dl>
      ${local.themeSummary ? `<details class="wiz-skel-theme-preview"><summary>Theme excerpt</summary><div class="wiz-skel-theme-text">${escHtml(local.themeSummary)}</div></details>` : ''}
    `;
    const btn = slot.querySelector('[data-role="skel-refresh"]');
    if (btn) btn.onclick = () => onSkeletonRefresh();
  }

  // ----------------------------------------------------------------------
  // Slot grid — per-slot default→tweaked diff + editable tweaked line
  // ----------------------------------------------------------------------

  function paintGrid(root, state) {
    const slot = root.querySelector('[data-role="skel-grid"]');
    if (!slot) return;
    if (!local.slots.length) {
      slot.innerHTML = W.emptyStatePanel({
        generating: aiBusy(),
        generatingMsg: 'Generating the skeleton…',
        emptyMsg: 'No skeleton yet — advance from Archetypes.',
        className: 'wiz-skel-empty',
      });
      return;
    }
    const isPast = isPastTab(state);
    // Disabled when the tab is past (edit-cascade only) OR an AI run is in
    // flight — the freshly built textareas must come up locked so a relabel
    // repaint doesn't hand the user editable fields mid-run (§3).
    const ro = (isPast || aiBusy()) ? 'disabled' : '';
    slot.innerHTML = local.slots.map(s => rowHtml(s, ro)).join('');
    slot.classList.toggle('wiz-skel-grid--streaming', local.streaming);
    // Re-flag rows that already arrived this run so a mid-stream repaint doesn't
    // re-dim them.
    if (local.streaming) {
      Object.keys(local.streamUpdates).forEach(sid => {
        const row = slot.querySelector(`.wiz-skel-row[data-slot-id="${cssEsc(sid)}"]`);
        if (row) row.classList.add('wiz-skel-row--arrived');
      });
    }
    if (!isPast) bindGrid(slot);
  }

  function rowHtml(s, ro) {
    const reserved = (s.reserved_card || '').trim();
    const cls = 'wiz-skel-row'
      + (isChanged(s) ? ' wiz-skel-row--changed' : '')
      + (reserved ? ' wiz-skel-row--req' : '');
    return `
      <div class="${cls}" data-slot-id="${escAttr(s.slot_id)}">
        <div class="wiz-skel-row-head">
          <span class="wiz-skel-slotid">${escHtml(s.slot_id)}</span>
          ${reserved ? `<span class="wiz-skel-reqbadge" title="${escAttr(reserved)}">★ specially requested card</span>` : ''}
        </div>
        <div class="wiz-skel-diff" data-role="diff">${diffHtml(s.default_text, s.tweaked_text)}</div>
        <textarea class="wiz-skel-tweak" data-role="tweak" rows="2" ${ro}>${escHtml(s.tweaked_text || '')}</textarea>
      </div>`;
  }

  function isChanged(s) {
    return (s.tweaked_text || '') !== (s.default_text || '');
  }

  function bindGrid(slot) {
    slot.querySelectorAll('.wiz-skel-row').forEach(row => {
      const sid = row.dataset.slotId;
      const ta = row.querySelector('[data-role="tweak"]');
      const diff = row.querySelector('[data-role="diff"]');
      if (!ta) return;
      ta.addEventListener('input', () => {
        const s = local.slots.find(x => x.slot_id === sid);
        if (!s) return;
        s.tweaked_text = ta.value;
        if (diff) diff.innerHTML = diffHtml(s.default_text, s.tweaked_text);
        row.classList.toggle('wiz-skel-row--changed', isChanged(s));
      });
    });
  }

  function applySlots(list) {
    if (!Array.isArray(list)) return;
    local.slots = list;
    local.hasTweaked = list.some(s => isChanged(s));
  }

  // ----------------------------------------------------------------------
  // Live relabel streaming (wired at module load via W.registerStream above)
  // ----------------------------------------------------------------------
  //
  // Three events, fired for BOTH the engine auto-run and the manual Refresh
  // (and replayed from the bus buffer when a tab attaches mid-run):
  //   skeleton_relabel_reset — a fresh attempt is (re)starting
  //   skeleton_slot          — one slot's relabel/placement landed
  //   skeleton_relabel_done  — the relabel finished (success or kept-partial)

  // A fresh attempt begins. Drop the prior attempt's accumulated updates and
  // per-row "arrived" highlights and dim the grid so the user watches it
  // re-stream — the visible half of the rollback. Slot text is left in place
  // (we keep partial); arriving slots overwrite it row by row. Request
  // placements, though, are fully recomputed each roll, so the prior run's
  // "specially requested card" tags are cleared up front — Pass 2 re-adds the
  // new ones as they stream in.
  function onRelabelReset() {
    local.streaming = true;
    local.incomplete = false;
    local.streamUpdates = {};
    local.slots.forEach(s => { s.reserved_card = ''; });
    const root = bodyRoot();
    if (!root) return;
    // Repaint so the cleared tags actually leave the DOM; paintGrid re-applies
    // the streaming dim and (with streamUpdates now empty) drops all
    // arrived/req highlights.
    paintGrid(root, W.getState());
    paintSummary(root, W.getState());
    applyFormLock();
  }

  // One slot's relabel (Pass 1) or request placement (Pass 2) arrived. Record
  // it, update the model + the row's diff/textarea live, and mark it arrived.
  function onRelabelSlot(data) {
    const sid = data.slot_id;
    if (!sid) return;
    local.streamUpdates[sid] = {
      tweaked_text: data.tweaked_text == null ? '' : String(data.tweaked_text),
      reserved_card: data.reserved_card || '',
    };
    local.streaming = true;
    const s = local.slots.find(x => x.slot_id === sid);
    if (!s) {
      // Tab opened mid-run before the default skeleton loaded — pull it so the
      // streamed slots have rows to land in (bootstrap merges streamUpdates).
      if (local.slots.length === 0 && !local.bootstrapping && bodyRoot()) {
        local.bootstrapping = true;
        bootstrap(bodyRoot(), W.getState())
          .catch(() => {})
          .finally(() => { local.bootstrapping = false; });
      }
      return;
    }
    s.tweaked_text = local.streamUpdates[sid].tweaked_text;
    // Replace, don't merge: a Pass-1 event (reserved empty) clears any stale tag
    // on this slot; a Pass-2 placement sets the new one.
    s.reserved_card = local.streamUpdates[sid].reserved_card;
    local.hasTweaked = true;
    applyLiveSlot(s);
  }

  // The relabel finished (success or kept-partial). Settle the live view: drop
  // the dim, record the durable incomplete flag, and repaint so the summary
  // banner + counts + footer reflect the final state. The streamed slots are
  // already authoritative (the server persisted the same updates).
  function onRelabelDone(data) {
    local.streaming = false;
    local.incomplete = !!data.incomplete;
    const root = bodyRoot();
    if (!root) return;
    paintSummary(root, W.getState());
    paintGrid(root, W.getState());
    paintFooter(getFooter(root), W.getState());
    applyFormLock();
  }

  // Update one already-rendered row in place to match its slot model and flag
  // it just-arrived (un-dim + pulse). No-op if the row isn't in the DOM.
  function applyLiveSlot(s) {
    const root = bodyRoot();
    if (!root) return;
    const row = root.querySelector(`.wiz-skel-row[data-slot-id="${cssEsc(s.slot_id)}"]`);
    if (!row) return;
    const reserved = (s.reserved_card || '').trim();
    row.classList.toggle('wiz-skel-row--changed', isChanged(s));
    row.classList.toggle('wiz-skel-row--req', !!reserved);
    row.classList.add('wiz-skel-row--arrived');
    const diff = row.querySelector('[data-role="diff"]');
    if (diff) diff.innerHTML = diffHtml(s.default_text, s.tweaked_text);
    const ta = row.querySelector('[data-role="tweak"]');
    if (ta && ta.value !== (s.tweaked_text || '')) ta.value = s.tweaked_text || '';
    const head = row.querySelector('.wiz-skel-row-head');
    if (head) {
      let badge = head.querySelector('.wiz-skel-reqbadge');
      if (reserved) {
        if (!badge) {
          badge = document.createElement('span');
          badge.className = 'wiz-skel-reqbadge';
          badge.textContent = '★ specially requested card';
          head.appendChild(badge);
        }
        badge.title = reserved;
      } else if (badge) {
        badge.remove();  // placement gone this roll — strip the stale tag
      }
    }
  }

  // ----------------------------------------------------------------------
  // Word-level diff (LCS) — highlights what the relabel changed
  // ----------------------------------------------------------------------

  function diffHtml(a, b) {
    a = a == null ? '' : String(a);
    b = b == null ? '' : String(b);
    if (a === b) return `<span class="wiz-skel-eq">${escHtml(a)}</span>`;
    const aw = a.split(/(\s+)/);
    const bw = b.split(/(\s+)/);
    const n = aw.length;
    const m = bw.length;
    // LCS length table (n+1 x m+1), built bottom-up.
    const dp = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
    for (let i = n - 1; i >= 0; i--) {
      for (let j = m - 1; j >= 0; j--) {
        dp[i][j] = aw[i] === bw[j]
          ? dp[i + 1][j + 1] + 1
          : Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
    const out = [];
    let i = 0;
    let j = 0;
    const flush = (cls, text) => {
      if (text) out.push(`<span class="${cls}">${escHtml(text)}</span>`);
    };
    while (i < n && j < m) {
      if (aw[i] === bw[j]) {
        flush('wiz-skel-eq', aw[i]); i++; j++;
      } else if (dp[i + 1][j] >= dp[i][j + 1]) {
        flush('wiz-skel-del', aw[i]); i++;
      } else {
        flush('wiz-skel-ins', bw[j]); j++;
      }
    }
    while (i < n) { flush('wiz-skel-del', aw[i++]); }
    while (j < m) { flush('wiz-skel-ins', bw[j++]); }
    return out.join('');
  }

  // ----------------------------------------------------------------------
  // Refresh — Step 2 (rebuild + relabel) + the shared relabel call
  // ----------------------------------------------------------------------

  // Step 2 refresh: rebuild the deterministic skeleton from the CURRENT knob
  // values, then run the LLM relabel over it. Two awaited calls (not one combined
  // endpoint) so local.slots holds the rebuilt matrix before the relabel streams,
  // letting each slot's live update land in the right row.
  async function onSkeletonRefresh() {
    await W.runAiAction({
      isLocked: () => local.locked,
      setLocked,
      confirm: () => (local.hasTweaked
        ? 'Rebuild the skeleton from the current knobs and re-run the LLM relabel? '
          + 'Your inline edits will be replaced.'
        : ''),
      busyLabel: 'Rebuilding skeleton from knobs…',
      onSettle: () => { local.streaming = false; },
      run: async ({ post, showBusy }) => {
        const root = bodyRoot();
        // Phase 1 — deterministic rebuild from the current knobs (no AI lock).
        const kData = await post('/api/wizard/skeleton/knobs', knobValuesPayload(), 'Rebuild failed');
        if (!kData) return;
        applyKnobsResponse(kData);
        if ((kData.warnings || []).length) W.toast('Some knob values were clamped.', 'warn');
        // Phase 2 — LLM relabel over the rebuilt skeleton (streams slots live).
        showBusy('Relabeling skeleton…');
        await runRelabel(root);
      },
    });
  }

  // POST the relabel and reconcile to its authoritative response. The SSE stream
  // (skeleton_relabel_reset / _slot / _done) paints slots live meanwhile; this is
  // the final state the tab settles to. Shared by Step 2 and the Step 1 cascade.
  // The caller owns the AI lock (setLocked) + busy strip.
  async function runRelabel(root) {
    const resp = await W.postJSON('/api/wizard/skeleton/refresh', {});
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      // The live stream (if any started) never reached done — settle it here so
      // the grid doesn't stay dimmed, then surface the error.
      local.streaming = false;
      paintSummary(root, W.getState());
      paintGrid(root, W.getState());
      return reportError(resp, data, 'Relabel failed');
    }
    // Authoritative final state. The skeleton_relabel_done SSE event also settled
    // the live view; applying the response slots reconciles any drift.
    local.streaming = false;
    local.incomplete = !!data.incomplete;
    applySlots(data.slots);
    if (data.model_id) local.modelId = data.model_id;
    paintSummary(root, W.getState());
    paintGrid(root, W.getState());
    paintFooter(getFooter(root), W.getState());
    W.toast(
      data.incomplete
        ? 'Skeleton relabeled (incomplete — some slots kept their default).'
        : 'Skeleton relabeled.',
      data.incomplete ? 'warn' : 'success',
    );
  }

  const reportError = (resp, data, fallback) => W.reportError(resp, data, fallback);

  // ----------------------------------------------------------------------
  // Footer: Save & Continue (latest tab + paused_for_review)
  // ----------------------------------------------------------------------

  function paintFooter(footer, state) {
    if (!footer) return;
    const isLatest = !state || state.latestTabId === STAGE_ID;
    const status = local.stageStatus;
    const next = W.nextStageEntryAfter(STAGE_ID);
    const nextName = next ? next.name : 'the next stage';

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Editing a past skeleton is destructive — use the Edit button above.</span>`;
    } else if (status === 'completed') {
      html = `<span class="wiz-footer-note">Skeleton saved. Engine is on ${escHtml(nextName)} — switch tabs to follow.</span>`;
    } else if (status === 'running') {
      html = `<span class="wiz-footer-note">Generating + relabeling the skeleton…</span>`;
    } else if (status !== 'paused_for_review') {
      html = `<span class="wiz-footer-note">This stage runs automatically. Tick "Stop after this step" above to review the skeleton here before continuing.</span>`;
    } else {
      const ok = local.slots.length && local.slots.every(s => (s.tweaked_text || '').trim());
      html = `
        <button type="button" class="wiz-btn-primary" data-role="skel-save-advance" ${ok && !local.locked ? '' : 'disabled'}>
          Save &amp; Continue: ${escHtml(nextName)}
        </button>
        <span class="wiz-footer-note">${local.slots.length} slots.</span>`;
    }
    W.paintFooter(footer, html, { role: 'skel-save-advance', onClick: onSaveAndAdvance });
  }

  function onSaveAndAdvance() {
    return W.saveAndAdvance({
      stageId: STAGE_ID,
      isLocked: () => local.locked,
      setLocked,
      btnRole: 'skel-save-advance',
      validate: () => (local.slots.length && local.slots.every(s => (s.tweaked_text || '').trim())
        ? null
        : 'Every slot needs a tweaked descriptor before continuing.'),
      saveUrl: '/api/wizard/skeleton/save',
      payload: () => ({
        slots: local.slots.map(s => ({ slot_id: s.slot_id, tweaked_text: s.tweaked_text })),
      }),
    });
  }

  // ----------------------------------------------------------------------
  // Form lock (§3)
  // ----------------------------------------------------------------------

  // AI is "active" on this tab when this tab kicked off an op (local.locked),
  // the engine is running the skeleton stage (local.stageStatus running), or a
  // relabel is streaming in (local.streaming — covers the live engine run even
  // before this tab's stageStatus has caught up). Any of these disables every
  // editable surface.
  function aiBusy() {
    return local.locked || local.streaming || local.stageStatus === 'running';
  }

  function setLocked(locked) {
    local.locked = !!locked;
    applyFormLock();
  }

  // Sync the DOM to aiBusy(). paintGrid/paintSummary already build their
  // controls disabled inline from aiBusy(), but the footer button + the
  // container class still need syncing, and SSE-driven re-renders call this
  // directly so a stage flipping to `running` locks an already-painted grid.
  function applyFormLock() {
    W.setTabLocked(bodyRoot(), aiBusy(), {
      lockClass: 'wiz-skel-locked',
      selectors: [
        '.wiz-skel-tweak', '[data-role="skel-refresh"]', '[data-role="knob-refresh"]',
        'input[data-knob]', 'input[data-knob-pin]', '[data-role="cycle-add"]',
        '.wiz-skel-cycle-item input', '.wiz-skel-cycle-item select', '.wiz-skel-cycle-item button',
        '[data-role="irr-pick"]',
      ],
      footerSelector: '[data-role="skel-save-advance"]',
    });
  }

  // ----------------------------------------------------------------------
  // Helpers
  // ----------------------------------------------------------------------

  const bodyRoot = () => W.tabRoot(STAGE_ID);

  const getFooter = (root) => W.tabFooter(root);

  const isPastTab = (state) => W.isPastTab(STAGE_ID, state);

  const escHtml = W.escHtml;

  const escAttr = W.escAttr;

  // Escape a slot id for use inside a `[data-slot-id="…"]` CSS selector. Slot
  // ids are alphanumeric+hyphen today, but CSS.escape keeps the live-update
  // selector safe if that ever changes.
  const cssEsc = W.cssEsc;
})();
