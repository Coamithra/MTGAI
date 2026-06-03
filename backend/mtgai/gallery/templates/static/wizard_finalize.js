/**
 * Wizard Finalization tab — fully editable per-card review of finalized text.
 *
 * Stage: finalize. The runner auto-runs (reminder-text injection + validation +
 * auto-fix), then pauses here ONLY if the user toggled "Stop after this step"
 * (review_eligible: True; the break-point defaults off). The tab shows every
 * card with its finalized text, badges which cards the finalize stage edited and
 * what it changed (before/after + the applied auto-fixes), lets the user edit any
 * field by hand, and — when paused — advances via a Save & Continue footer.
 *
 * Special characters: card text stores symbols as ``{T}`` / ``{W}`` tokens (the
 * on-disk Scryfall form the renderer consumes). The editor textareas show the
 * raw tokens; a live preview under each oracle/cost field renders them as inline
 * symbol badges so the user sees how it'll look. A helper line at the top of the
 * tab documents the syntax.
 *
 * Registers via ``W.registerStageRenderer('finalize', ...)`` so wizard_stage.js
 * owns the header (status pill, break-point toggle, Edit-cascade button); this
 * module owns content + footer.
 *
 * Conventions (plans/wizard-tab-conventions.md):
 *   §1  single Save & Continue footer (W.saveAndAdvance) when paused on latest tab
 *   §3  form lock during stage-running / save-in-flight (W.setTabLocked)
 *   §5  provenance badges via W.provenanceBadge ('auto' = stage-edited, 'user' = edited)
 *   §8  status pill / §9 break toggle owned by the shell
 *   §12 escHtml/escAttr leaf helpers; lazy mount; .onclick rebind
 *   §17 fetchStageState / emptyStatePanel / paintFooter / saveAndAdvance helpers
 *
 * Backend:
 *   GET  /api/wizard/finalize/state      → { cards[], has_content, report, ... }
 *   POST /api/wizard/finalize/save-card  → { collector_number, fields }  (per-field blur save)
 *   POST /api/wizard/finalize/save       → { cards: [{collector_number, fields}] }  (bulk, Save & Continue)
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'finalize';

  const escHtml = W.escHtml;
  const escAttr = W.escAttr;

  const local = {
    initialized: false,
    stageStatus: 'pending',
    cards: [],          // FinalizeCard[] (server shape + transient _dirty)
    hasContent: false,
    report: null,
    locked: false,
    bootstrapping: false,
    filter: { rarity: 'all', edited: 'all', errors: 'all' },
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ---------------------------------------------------------------------------
  // Symbol token preview — turns {T}/{W}/{2}/... into inline badges (display
  // only; the stored text keeps the canonical tokens). Mirrors the mana palette
  // the renderer uses so the preview reads like the printed card.
  // ---------------------------------------------------------------------------

  const SYMBOL_CLASS = {
    W: 'w', U: 'u', B: 'b', R: 'r', G: 'g',
    C: 'c', T: 't', Q: 'q', X: 'x', S: 's', E: 'e',
  };

  function symbolizeHtml(text) {
    if (!text) return '';
    // Escape first, then replace the (already-escaped) {...} tokens with badges.
    return escHtml(text).replace(/\{([^}]+)\}/g, (whole, code) => {
      const raw = String(code).trim();
      const key = raw.toUpperCase();
      const cls = SYMBOL_CLASS[key] || (/^\d+$/.test(raw) ? 'generic' : 'other');
      const label = key === 'T' ? 'T' : key === 'Q' ? 'Q' : raw;
      return `<span class="wiz-sym wiz-sym-${cls}" title="${escAttr(whole)}">${escHtml(label)}</span>`;
    }).replace(/\n/g, '<br>');
  }

  // ---------------------------------------------------------------------------
  // Styles (injected once)
  // ---------------------------------------------------------------------------

  (function injectStyles() {
    if (document.getElementById('wiz-finalize-styles')) return;
    const s = document.createElement('style');
    s.id = 'wiz-finalize-styles';
    s.textContent = `
      .wiz-finalize-help {
        display: flex; gap: 0.5rem; align-items: flex-start;
        background: #16213e; border: 1px solid #2a2f55; border-radius: 6px;
        padding: 0.55rem 0.75rem; margin-bottom: 0.9rem;
        font-size: 0.8rem; color: #b8c0d8; line-height: 1.5;
      }
      .wiz-finalize-help code {
        background: #0f1729; border-radius: 3px; padding: 0.05rem 0.3rem;
        font-size: 0.78rem; color: #e0e0e0;
      }
      .wiz-finalize-summary-bar {
        display: flex; flex-wrap: wrap; gap: 1.2rem; align-items: center;
        padding: 0.6rem 0.9rem; background: #1e2130; border-radius: 6px;
        margin-bottom: 0.85rem; font-size: 0.85rem; color: #9aa3b8;
      }
      .wiz-finalize-summary-bar strong { color: #e2e8f0; }
      .wiz-finalize-summary-bar .warn strong { color: #fb923c; }

      .wiz-finalize-filters {
        display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center;
        margin-bottom: 0.85rem;
      }
      .wiz-finalize-filters label {
        font-size: 0.75rem; color: #888; display: flex; align-items: center; gap: 0.3rem;
      }
      .wiz-finalize-filters select {
        padding: 0.25rem 0.5rem; background: #1a1a2e; border: 1px solid #333;
        border-radius: 5px; color: #e0e0e0; font-size: 0.78rem; font-family: inherit;
      }
      .wiz-finalize-filters select:focus { outline: none; border-color: #4a9eff; }

      .wiz-finalize-grid { display: flex; flex-direction: column; gap: 0.85rem; }
      .wiz-finalize-empty { color: #666; font-style: italic; font-size: 0.85rem; padding: 1.5rem 0; }

      .wiz-finalize-card {
        background: #0f1729; border: 1px solid #1f2540; border-radius: 8px;
        padding: 0.85rem 0.9rem; display: flex; flex-direction: column; gap: 0.6rem;
      }
      .wiz-finalize-card.is-auto  { border-color: #8a6d2e66; }
      .wiz-finalize-card.is-user  { border-color: #4a9eff66; }

      .wiz-finalize-card-head {
        display: flex; align-items: center; gap: 0.55rem; flex-wrap: wrap;
      }
      .wiz-finalize-cn { font-family: monospace; font-size: 0.78rem; color: #9aa3b8; }
      .wiz-finalize-cardname { font-weight: 700; font-size: 0.95rem; color: #e0e0e0; flex: 1; }
      .wiz-finalize-rarity {
        font-size: 0.62rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
        padding: 1px 5px; border-radius: 3px; background: #1a1a2e; color: #aaa;
      }
      .wiz-finalize-rarity.common { color: #aaa; }
      .wiz-finalize-rarity.uncommon { color: #8cbfff; }
      .wiz-finalize-rarity.rare { color: #f5a623; }
      .wiz-finalize-rarity.mythic { color: #e94560; }
      .wiz-finalize-saved-tick { font-size: 0.72rem; color: #4ade80; opacity: 0; transition: opacity 0.2s; }
      .wiz-finalize-saved-tick.show { opacity: 1; }

      .wiz-finalize-changed {
        background: #16213e; border-radius: 6px; padding: 0.5rem 0.65rem; font-size: 0.8rem;
      }
      .wiz-finalize-changed summary { cursor: pointer; color: #fb923c; font-weight: 600; }
      .wiz-finalize-changed ul { margin: 0.4rem 0 0.3rem 1rem; padding: 0; color: #ccc; }
      .wiz-finalize-changed li { padding: 0.1rem 0; }
      .wiz-finalize-diff { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-top: 0.4rem; }
      .wiz-finalize-diff > div { background: #0f1729; border-radius: 5px; padding: 0.4rem 0.5rem; }
      .wiz-finalize-diff .lbl { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.05em; color: #888; margin-bottom: 0.2rem; }
      .wiz-finalize-diff .before { color: #ff8a8a; }
      .wiz-finalize-diff .after { color: #9ee6b4; }

      .wiz-finalize-manual {
        background: #2a1505; border: 1px solid #5a3411; border-radius: 6px;
        padding: 0.45rem 0.6rem; font-size: 0.78rem; color: #fbbf77;
      }
      .wiz-finalize-manual .code { font-family: monospace; font-weight: 700; margin-right: 0.35rem; }

      .wiz-finalize-fields { display: grid; grid-template-columns: 2fr 1fr; gap: 0.5rem 0.7rem; }
      .wiz-finalize-field { display: flex; flex-direction: column; gap: 0.2rem; }
      .wiz-finalize-field.full { grid-column: 1 / -1; }
      .wiz-finalize-field label { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.05em; color: #888; }
      .wiz-finalize-field input, .wiz-finalize-field textarea {
        width: 100%; box-sizing: border-box; padding: 0.32rem 0.5rem;
        background: #1a1a2e; border: 1px solid #2a2f55; border-radius: 5px;
        color: #e0e0e0; font-size: 0.82rem; font-family: inherit;
      }
      .wiz-finalize-field input:focus, .wiz-finalize-field textarea:focus { outline: none; border-color: #4a9eff; }
      .wiz-finalize-field textarea { resize: vertical; min-height: 3rem; }
      .wiz-finalize-pt-row { display: flex; gap: 0.5rem; }
      .wiz-finalize-pt-row .wiz-finalize-field { flex: 1; }
      .wiz-finalize-slot { font-size: 0.74rem; color: #6f7790; font-style: italic; }

      .wiz-finalize-preview {
        font-size: 0.82rem; color: #cbd3e6; line-height: 1.55;
        background: #16213e; border-radius: 5px; padding: 0.4rem 0.55rem; min-height: 1.6rem;
      }
      .wiz-finalize-preview-lbl { font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.05em; color: #777; }

      /* Inline symbol badges */
      .wiz-sym {
        display: inline-flex; align-items: center; justify-content: center;
        min-width: 1.05em; height: 1.05em; padding: 0 0.18em; margin: 0 0.04em;
        border-radius: 50%; font-size: 0.82em; font-weight: 700; line-height: 1;
        vertical-align: -0.12em; background: #c8c2bc; color: #1a1a1a;
      }
      .wiz-sym-w { background: #f8f0d8; color: #2a2418; }
      .wiz-sym-u { background: #9ad4f5; color: #06324d; }
      .wiz-sym-b { background: #6b6a6e; color: #efeae6; }
      .wiz-sym-r { background: #f0a08a; color: #4d1206; }
      .wiz-sym-g { background: #9ad6a8; color: #0c3a1c; }
      .wiz-sym-c, .wiz-sym-generic, .wiz-sym-x, .wiz-sym-s, .wiz-sym-e, .wiz-sym-other {
        background: #c8c2bc; color: #1a1a1a;
      }
      .wiz-sym-t, .wiz-sym-q { background: #2a2418; color: #e8e0d0; font-style: italic; }

      .wiz-finalize-locked { opacity: 0.85; }
      .wiz-finalize-locked input:disabled,
      .wiz-finalize-locked textarea:disabled,
      .wiz-finalize-locked select:disabled { cursor: not-allowed; }
    `;
    document.head.appendChild(s);
  })();

  // ---------------------------------------------------------------------------
  // Render / mount
  // ---------------------------------------------------------------------------

  function render({ root, state, stage, content, footer }) {
    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      bootstrap(root, state).catch(err =>
        W.toast('Failed to load finalize state: ' + err.message, 'error')
      );
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
        .catch(err => W.toast('Failed to refresh finalize state: ' + err.message, 'error'))
        .finally(() => { local.bootstrapping = false; });
      return;
    }

    paintFooter(footer, state);
    setLocked(local.locked);
  }

  function mountShellHtml() {
    return `
      <div data-role="fin-help"></div>
      <div data-role="fin-summary"></div>
      <div data-role="fin-filters"></div>
      <div class="wiz-finalize-grid" data-role="fin-grid">
        <div class="wiz-finalize-empty">Loading cards…</div>
      </div>
    `;
  }

  // ---------------------------------------------------------------------------
  // Bootstrap
  // ---------------------------------------------------------------------------

  async function bootstrap(root, state) {
    const data = await W.fetchStageState(STAGE_ID);
    if (data) {
      const incoming = Array.isArray(data.cards) ? data.cards : [];
      // Preserve in-progress edits the user already made this session.
      if (local.cards.length === 0) {
        local.cards = incoming;
      } else {
        const byCn = {};
        local.cards.forEach(c => { byCn[c.collector_number] = c; });
        local.cards = incoming.map(c => {
          const ex = byCn[c.collector_number];
          return ex && ex._dirty ? ex : c;
        });
      }
      local.hasContent = local.cards.length > 0;
      local.report = data.report || null;
      if (data.stage_status) local.stageStatus = data.stage_status;
    }

    paintHelp(root);
    paintSummary(root);
    paintFilters(root);
    paintGrid(root);
    paintFooter(getFooter(root), state);
    setLocked(local.locked);
  }

  // ---------------------------------------------------------------------------
  // Help line (symbol syntax)
  // ---------------------------------------------------------------------------

  function paintHelp(root) {
    const slot = root.querySelector('[data-role="fin-help"]');
    if (!slot) return;
    slot.innerHTML = `
      <div class="wiz-finalize-help">
        <span>💡</span>
        <span>Insert symbols with curly-brace tokens:
          <code>{T}</code> tap, <code>{Q}</code> untap,
          <code>{W}{U}{B}{R}{G}</code> coloured mana,
          <code>{C}</code> colourless, <code>{1}{2}…</code> generic, <code>{X}</code> variable,
          <code>{S}</code> snow, <code>{E}</code> energy. They render as the symbols shown in
          the live preview under each card and on the printed card.</span>
      </div>
    `;
  }

  // ---------------------------------------------------------------------------
  // Summary bar
  // ---------------------------------------------------------------------------

  function paintSummary(root) {
    const slot = root.querySelector('[data-role="fin-summary"]');
    if (!slot) return;
    const r = local.report;
    if (!r) { slot.innerHTML = ''; return; }
    const manual = r.total_manual_errors || 0;
    const ts = r.timestamp ? new Date(r.timestamp).toLocaleString() : '';
    slot.innerHTML = `
      <div class="wiz-finalize-summary-bar">
        <span><strong>${escHtml(String(r.total_cards || 0))}</strong> cards</span>
        <span><strong>${escHtml(String(r.cards_modified || 0))}</strong> auto-edited</span>
        <span><strong>${escHtml(String(r.total_auto_fixes || 0))}</strong> auto-fixes</span>
        <span class="${manual > 0 ? 'warn' : ''}"><strong>${escHtml(String(manual))}</strong> manual error${manual !== 1 ? 's' : ''}</span>
        ${ts ? `<span>Finalized: ${escHtml(ts)}</span>` : ''}
      </div>
    `;
  }

  // ---------------------------------------------------------------------------
  // Filters
  // ---------------------------------------------------------------------------

  function paintFilters(root) {
    const slot = root.querySelector('[data-role="fin-filters"]');
    if (!slot) return;
    if (!local.hasContent) { slot.innerHTML = ''; return; }
    slot.innerHTML = `
      <div class="wiz-finalize-filters">
        <label>Rarity
          <select data-role="fin-filter-rarity">
            <option value="all" ${local.filter.rarity === 'all' ? 'selected' : ''}>All</option>
            <option value="common" ${local.filter.rarity === 'common' ? 'selected' : ''}>Common</option>
            <option value="uncommon" ${local.filter.rarity === 'uncommon' ? 'selected' : ''}>Uncommon</option>
            <option value="rare" ${local.filter.rarity === 'rare' ? 'selected' : ''}>Rare</option>
            <option value="mythic" ${local.filter.rarity === 'mythic' ? 'selected' : ''}>Mythic</option>
          </select>
        </label>
        <label>Edits
          <select data-role="fin-filter-edited">
            <option value="all" ${local.filter.edited === 'all' ? 'selected' : ''}>All</option>
            <option value="edited" ${local.filter.edited === 'edited' ? 'selected' : ''}>Edited only</option>
            <option value="unedited" ${local.filter.edited === 'unedited' ? 'selected' : ''}>Unedited only</option>
          </select>
        </label>
        <label>Errors
          <select data-role="fin-filter-errors">
            <option value="all" ${local.filter.errors === 'all' ? 'selected' : ''}>All</option>
            <option value="manual" ${local.filter.errors === 'manual' ? 'selected' : ''}>Manual errors only</option>
          </select>
        </label>
      </div>
    `;
    const bind = (role, key) => {
      const el = slot.querySelector(`[data-role="${role}"]`);
      if (el) el.onchange = () => { local.filter[key] = el.value; paintGrid(bodyRoot()); };
    };
    bind('fin-filter-rarity', 'rarity');
    bind('fin-filter-edited', 'edited');
    bind('fin-filter-errors', 'errors');
  }

  // ---------------------------------------------------------------------------
  // Grid
  // ---------------------------------------------------------------------------

  function paintGrid(root) {
    const slot = root && root.querySelector('[data-role="fin-grid"]');
    if (!slot) return;
    if (!local.hasContent) {
      const generating = local.stageStatus === 'running' || local.locked;
      slot.innerHTML = W.emptyStatePanel({
        generating,
        generatingMsg: 'Finalization is running — cards will appear once it completes.',
        emptyMsg: 'No finalized cards yet. The Finalization stage must complete first.',
        className: 'wiz-finalize-empty',
      });
      return;
    }
    const visible = visibleCards();
    if (visible.length === 0) {
      slot.innerHTML = `<div class="wiz-finalize-empty">No cards match the current filter.</div>`;
      return;
    }
    slot.innerHTML = visible.map(cardHtml).join('');
    visible.forEach(c => bindCard(slot, c.collector_number));
  }

  function isEdited(c) { return !!(c.auto_edited || c.user_edited || c._dirty); }

  function visibleCards() {
    return local.cards.filter(c => {
      if (local.filter.rarity !== 'all' && c.rarity !== local.filter.rarity) return false;
      if (local.filter.edited === 'edited' && !isEdited(c)) return false;
      if (local.filter.edited === 'unedited' && isEdited(c)) return false;
      if (local.filter.errors === 'manual' && !(c.manual_errors && c.manual_errors.length)) return false;
      return true;
    });
  }

  function cardHtml(c) {
    const userBadge = (c.user_edited || c._dirty);
    const prov = userBadge ? 'user' : (c.auto_edited ? 'auto' : 'default');
    const cls = userBadge ? 'is-user' : (c.auto_edited ? 'is-auto' : '');

    return `
      <article class="wiz-finalize-card ${cls}" data-cn="${escAttr(c.collector_number)}">
        <div class="wiz-finalize-card-head">
          <span class="wiz-finalize-cn">${escHtml(c.collector_number)}</span>
          <span class="wiz-finalize-cardname">${escHtml(c.name || '(unnamed)')}</span>
          <span class="wiz-finalize-rarity ${escAttr(c.rarity || 'common')}">${escHtml(c.rarity || '')}</span>
          ${W.provenanceBadge(prov, { role: 'ai-badge' })}
          <span class="wiz-finalize-saved-tick" data-role="fin-saved">Saved ✓</span>
        </div>
        ${c.slot_text ? `<div class="wiz-finalize-slot">Slot: ${escHtml(c.slot_text)}</div>` : ''}
        ${changedBlockHtml(c)}
        ${manualBlockHtml(c)}
        <div class="wiz-finalize-fields">
          ${fieldHtml('Name', 'name', c.name, false, true)}
          ${fieldHtml('Mana cost', 'mana_cost', c.mana_cost, false, false)}
          <div class="wiz-finalize-field full">
            <label>Type line</label>
            <input type="text" data-field="type_line" value="${escAttr(c.type_line || '')}">
          </div>
          <div class="wiz-finalize-field full">
            <label>Oracle text</label>
            <textarea data-field="oracle_text" rows="4">${escHtml(c.oracle_text || '')}</textarea>
            <span class="wiz-finalize-preview-lbl">Preview</span>
            <div class="wiz-finalize-preview" data-role="fin-oracle-preview">${symbolizeHtml(c.oracle_text)}</div>
          </div>
          <div class="wiz-finalize-field full">
            <label>Flavor text</label>
            <textarea data-field="flavor_text" rows="2">${escHtml(c.flavor_text || '')}</textarea>
          </div>
          <div class="wiz-finalize-field full">
            <div class="wiz-finalize-pt-row">
              <div class="wiz-finalize-field">
                <label>Power</label>
                <input type="text" data-field="power" value="${escAttr(c.power == null ? '' : c.power)}">
              </div>
              <div class="wiz-finalize-field">
                <label>Toughness</label>
                <input type="text" data-field="toughness" value="${escAttr(c.toughness == null ? '' : c.toughness)}">
              </div>
              <div class="wiz-finalize-field">
                <label>Loyalty</label>
                <input type="text" data-field="loyalty" value="${escAttr(c.loyalty == null ? '' : c.loyalty)}">
              </div>
            </div>
          </div>
        </div>
      </article>
    `;
  }

  function fieldHtml(label, field, value, _multi, full) {
    return `
      <div class="wiz-finalize-field ${full ? 'full' : ''}">
        <label>${escHtml(label)}</label>
        <input type="text" data-field="${escAttr(field)}" value="${escAttr(value == null ? '' : value)}">
      </div>
    `;
  }

  function changedBlockHtml(c) {
    if (!c.auto_edited) return '';
    const fixes = (c.fixes_applied || []).map(f => `<li>${escHtml(f)}</li>`).join('');
    const before = c.original_oracle_text;
    const diff = before != null ? `
      <div class="wiz-finalize-diff">
        <div><div class="lbl">Before (pre-finalize)</div><div class="before">${symbolizeHtml(before)}</div></div>
        <div><div class="lbl">After (finalized)</div><div class="after">${symbolizeHtml(c.oracle_text)}</div></div>
      </div>` : '';
    return `
      <details class="wiz-finalize-changed">
        <summary>What the finalize stage changed</summary>
        ${fixes ? `<ul>${fixes}</ul>` : '<p style="margin:0.3rem 0;color:#9aa3b8">Reminder text was injected/normalized.</p>'}
        ${diff}
      </details>
    `;
  }

  function manualBlockHtml(c) {
    const errs = c.manual_errors || [];
    if (!errs.length) return '';
    const items = errs.map(e => {
      const code = e.code || 'unknown';
      const msg = e.message || '';
      const sug = e.suggestion ? ` — ${e.suggestion}` : '';
      return `<div><span class="code">[${escHtml(code)}]</span>${escHtml(msg)}${escHtml(sug)}</div>`;
    }).join('');
    return `<div class="wiz-finalize-manual">${items}</div>`;
  }

  // ---------------------------------------------------------------------------
  // Per-card binding: edit fields, live preview, blur-save
  // ---------------------------------------------------------------------------

  function bindCard(slot, cn) {
    const el = slot.querySelector(`.wiz-finalize-card[data-cn="${W.cssEsc(cn)}"]`);
    if (!el) return;
    el.querySelectorAll('[data-field]').forEach(input => {
      input.oninput = () => {
        const field = input.dataset.field;
        const val = input.value;
        updateCard(cn, { [field]: val, _dirty: true });
        if (field === 'oracle_text') {
          const prev = el.querySelector('[data-role="fin-oracle-preview"]');
          if (prev) prev.innerHTML = symbolizeHtml(val);
        }
        hideTick(el);
      };
      input.onblur = () => saveCard(cn, el);
    });
  }

  function gatherFields(cn) {
    const c = local.cards.find(x => x.collector_number === cn);
    if (!c) return {};
    return {
      name: c.name || '',
      mana_cost: c.mana_cost || '',
      type_line: c.type_line || '',
      oracle_text: c.oracle_text || '',
      flavor_text: c.flavor_text == null ? '' : c.flavor_text,
      power: c.power == null ? '' : c.power,
      toughness: c.toughness == null ? '' : c.toughness,
      loyalty: c.loyalty == null ? '' : c.loyalty,
    };
  }

  async function saveCard(cn, el) {
    const c = local.cards.find(x => x.collector_number === cn);
    if (!c || !c._dirty || local.locked) return;
    try {
      const resp = await W.postJSON('/api/wizard/finalize/save-card', {
        collector_number: cn,
        fields: gatherFields(cn),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { W.reportError(resp, data, 'Save failed'); return; }
      c._dirty = false;
      c.user_edited = true;
      showTick(el);
      // Flip the card's provenance badge to "edited" without a full repaint.
      if (el) el.classList.remove('is-auto');
      if (el) el.classList.add('is-user');
    } catch (err) {
      W.toast('Network error saving card: ' + (err && err.message ? err.message : err), 'error');
    }
  }

  function showTick(el) {
    const t = el && el.querySelector('[data-role="fin-saved"]');
    if (!t) return;
    t.classList.add('show');
    clearTimeout(t._timer);
    t._timer = setTimeout(() => t.classList.remove('show'), 1600);
  }

  function hideTick(el) {
    const t = el && el.querySelector('[data-role="fin-saved"]');
    if (t) t.classList.remove('show');
  }

  function updateCard(cn, patch) {
    const i = local.cards.findIndex(c => c.collector_number === cn);
    if (i >= 0) local.cards[i] = Object.assign({}, local.cards[i], patch);
  }

  // ---------------------------------------------------------------------------
  // Footer — Save & Continue when paused on the latest tab (§1)
  // ---------------------------------------------------------------------------

  function paintFooter(footer, state) {
    if (!footer) return;
    const isLatest = !state || state.latestTabId === STAGE_ID;
    const status = local.stageStatus;
    const next = W.nextStageEntryAfter(STAGE_ID);
    const nextName = next ? next.name : 'Next step';

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Finalization is in the past — pipeline has moved on.</span>`;
    } else if (status === 'completed') {
      html = `<span class="wiz-footer-note">Finalization complete. Engine is on ${escHtml(nextName)}.</span>`;
    } else if (status === 'running') {
      html = `<span class="wiz-footer-note">Finalization is running automatically…</span>`;
    } else if (status === 'paused_for_review') {
      html = `
        <button type="button" class="wiz-btn-primary" data-role="fin-advance" ${local.locked ? 'disabled' : ''}>
          Save &amp; Continue: ${escHtml(nextName)}
        </button>
        <span class="wiz-footer-note">Edit any card above (auto-saves on blur), then continue.</span>
      `;
    } else if (status === 'failed') {
      html = `<span class="wiz-footer-note">Stage failed — check the progress strip for details.</span>`;
    } else {
      html = `<span class="wiz-footer-note">Runs automatically after AI Review. Toggle “Stop after this step” to pause and edit here.</span>`;
    }

    W.paintFooter(footer, html, { role: 'fin-advance', onClick: onSaveAndContinue });
  }

  function onSaveAndContinue() {
    W.saveAndAdvance({
      stageId: STAGE_ID,
      saveUrl: '/api/wizard/finalize/save',
      payload: () => ({
        cards: local.cards
          .filter(c => c._dirty)
          .map(c => ({ collector_number: c.collector_number, fields: gatherFields(c.collector_number) })),
      }),
      isLocked: () => local.locked,
      setLocked,
      btnRole: 'fin-advance',
    });
  }

  // ---------------------------------------------------------------------------
  // Form lock (§3)
  // ---------------------------------------------------------------------------

  function aiBusy() {
    return local.locked || local.stageStatus === 'running';
  }

  function setLocked(locked) {
    local.locked = !!locked;
    W.setTabLocked(bodyRoot(), aiBusy(), {
      lockClass: 'wiz-finalize-locked',
      selectors: [
        '.wiz-finalize-card [data-field]',
        '[data-role="fin-filter-rarity"]',
        '[data-role="fin-filter-edited"]',
        '[data-role="fin-filter-errors"]',
      ],
      footerSelector: '[data-role="fin-advance"]',
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
})();
