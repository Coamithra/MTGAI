/**
 * Wizard Rendering & Final Review tab — the pipeline's terminal stage.
 *
 * Stage: rendering. The runner renders every card to a print-ready PNG (streaming
 * each into the gallery as it lands), then pauses here for final review (the
 * break-point defaults ON). There is NO QA / pixel-check pass — the user's two
 * actions ARE the remediation:
 *
 *   1. Edit any field of any card → a lightweight per-card finalize pass
 *      (reminder-text re-inject + validation + auto-fix) runs server-side and the
 *      card re-renders. The new render replaces the gallery thumbnail in place.
 *   2. Remove a card from the set → hard-delete + contiguous renumber of the
 *      card's collector-number group + re-render every card whose number changed.
 *
 * A final "Approve for print" footer button is the approve-to-print gate that
 * resumes the (last) stage.
 *
 * Registers via ``W.registerStageRenderer('rendering', ...)`` so wizard_stage.js
 * owns the header (status pill, break-point toggle, Edit-cascade button); this
 * module owns content + footer.
 *
 * Conventions (plans/wizard-tab-conventions.md):
 *   §1  single Save & Continue (here "Approve for print") footer when paused
 *   §3  form lock during stage-running / save-in-flight (W.setTabLocked)
 *   §7  AI actions through W.runAiAction (per-card edit / remove hold the AI lock)
 *   §8  status pill / §9 break toggle owned by the shell
 *   §10 sticky progress strip — driven by SSE (render_card events), not this module
 *   §12 escHtml/escAttr leaf helpers; lazy mount; .onclick rebind; symbol preview
 *   §17 fetchStageState / emptyStatePanel / paintFooter / runAiAction helpers
 *
 * Backend:
 *   GET  /api/wizard/rendering/state              → { cards[], has_content, report, ... }
 *   GET  /api/wizard/rendering/image/{cn}         → render PNG (FileResponse)
 *   POST /api/wizard/rendering/save-card          → { collector_number, fields } (edit + re-render)
 *   POST /api/wizard/rendering/remove-card        → { collector_number } (delete + renumber + re-render)
 *   POST /api/wizard/rendering/approve            → approve-to-print gate (then /advance)
 *
 * SSE: render_reset (start of a run) / render_card (one card rendered) — wired via
 * the W.onRenderingStream bridge in wizard.js. A render_card refreshes that card's
 * gallery thumbnail (cache-busted) without a full repaint.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'rendering';

  const escHtml = W.escHtml;
  const escAttr = W.escAttr;

  const local = {
    initialized: false,
    stageStatus: 'pending',
    cards: [],          // RenderingCard[] (server shape + transient _dirty)
    hasContent: false,
    report: null,
    locked: false,
    bootstrapping: false,
    filter: { rarity: 'all', rendered: 'all' },
  };

  W.registerStageRenderer(STAGE_ID, render);

  // SSE: live render thumbnails. render_card → refresh that card's image (cache-
  // busted) + mark has_render; render_reset → a fresh run begins.
  W.registerStream(STAGE_ID, {
    render_reset: () => { /* a fresh run begins; thumbnails refresh per render_card */ },
    render_card: (data, root) => {
      const cn = data && data.collector_number;
      if (!cn) return;
      const c = local.cards.find(x => x.collector_number === cn);
      if (c) c.has_render = true;
      refreshThumb(root || bodyRoot(), cn);
    },
  });

  // ---------------------------------------------------------------------------
  // Symbol token preview (display-only; stored text keeps the {T}/{W} tokens).
  // Mirrors wizard_finalize.js's palette so the preview reads like the card.
  // ---------------------------------------------------------------------------

  const SYMBOL_CLASS = {
    W: 'w', U: 'u', B: 'b', R: 'r', G: 'g',
    C: 'c', T: 't', Q: 'q', X: 'x', S: 's', E: 'e',
  };

  function symbolizeHtml(text) {
    if (!text) return '';
    return escHtml(text).replace(/\{([^}]+)\}/g, (whole, code) => {
      const raw = String(code).trim();
      const key = raw.toUpperCase();
      const cls = SYMBOL_CLASS[key] || (/^\d+$/.test(raw) ? 'generic' : 'other');
      const label = key === 'T' ? 'T' : key === 'Q' ? 'Q' : raw;
      return `<span class="wiz-sym wiz-sym-${cls}" title="${escAttr(whole)}">${escHtml(label)}</span>`;
    }).replace(/\n/g, '<br>');
  }

  function imgUrl(cn, bust) {
    const q = bust ? `?t=${bust}` : '';
    return `/api/wizard/rendering/image/${encodeURIComponent(cn)}${q}`;
  }

  // ---------------------------------------------------------------------------
  // Styles (injected once). Reuses the shared .wiz-sym badge classes; (re)defines
  // them here too so the tab works standalone if finalize didn't load first.
  // ---------------------------------------------------------------------------

  (function injectStyles() {
    if (document.getElementById('wiz-rendering-styles')) return;
    const s = document.createElement('style');
    s.id = 'wiz-rendering-styles';
    s.textContent = `
      .wiz-rendering-help {
        display: flex; gap: 0.5rem; align-items: flex-start;
        background: #16213e; border: 1px solid #2a2f55; border-radius: 6px;
        padding: 0.55rem 0.75rem; margin-bottom: 0.9rem;
        font-size: 0.8rem; color: #b8c0d8; line-height: 1.5;
      }
      .wiz-rendering-summary-bar {
        display: flex; flex-wrap: wrap; gap: 1.2rem; align-items: center;
        padding: 0.6rem 0.9rem; background: #1e2130; border-radius: 6px;
        margin-bottom: 0.85rem; font-size: 0.85rem; color: #9aa3b8;
      }
      .wiz-rendering-summary-bar strong { color: #e2e8f0; }
      .wiz-rendering-summary-bar .warn strong { color: #fb923c; }

      .wiz-rendering-filters {
        display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center;
        margin-bottom: 0.85rem;
      }
      .wiz-rendering-filters label {
        font-size: 0.75rem; color: #888; display: flex; align-items: center; gap: 0.3rem;
      }
      .wiz-rendering-filters select {
        padding: 0.25rem 0.5rem; background: #1a1a2e; border: 1px solid #333;
        border-radius: 5px; color: #e0e0e0; font-size: 0.78rem; font-family: inherit;
      }
      .wiz-rendering-filters select:focus { outline: none; border-color: #4a9eff; }

      .wiz-rendering-grid {
        display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
        gap: 0.9rem;
      }
      .wiz-rendering-empty { color: #666; font-style: italic; font-size: 0.85rem; padding: 1.5rem 0; }

      .wiz-rendering-card {
        background: #0f1729; border: 1px solid #1f2540; border-radius: 8px;
        padding: 0.7rem 0.75rem; display: flex; flex-direction: column; gap: 0.55rem;
      }
      .wiz-rendering-card.is-user { border-color: #4a9eff66; }
      .wiz-rendering-card-head {
        display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;
      }
      .wiz-rendering-cn { font-family: monospace; font-size: 0.76rem; color: #9aa3b8; }
      .wiz-rendering-cardname { font-weight: 700; font-size: 0.9rem; color: #e0e0e0; flex: 1; }
      .wiz-rendering-rarity {
        font-size: 0.6rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
        padding: 1px 5px; border-radius: 3px; background: #1a1a2e; color: #aaa;
      }
      .wiz-rendering-rarity.uncommon { color: #8cbfff; }
      .wiz-rendering-rarity.rare { color: #f5a623; }
      .wiz-rendering-rarity.mythic { color: #e94560; }
      .wiz-rendering-saved-tick { font-size: 0.7rem; color: #4ade80; opacity: 0; transition: opacity 0.2s; }
      .wiz-rendering-saved-tick.show { opacity: 1; }

      .wiz-rendering-thumb-wrap {
        position: relative; width: 100%; aspect-ratio: 822 / 1122;
        background: #06080f; border-radius: 6px; overflow: hidden;
        display: flex; align-items: center; justify-content: center;
      }
      /* zoom-in cursor lives on the <img> (present only when rendered) so an
         unrendered cell shows no affordance, matching the click handler's guard */
      .wiz-rendering-thumb { width: 100%; height: 100%; object-fit: contain; display: block; cursor: zoom-in; }
      .wiz-rendering-thumb-missing { color: #555; font-size: 0.8rem; font-style: italic; }

      .wiz-rendering-fields { display: none; flex-direction: column; gap: 0.45rem; }
      .wiz-rendering-card.editing .wiz-rendering-fields { display: flex; }
      .wiz-rendering-field { display: flex; flex-direction: column; gap: 0.2rem; }
      .wiz-rendering-field label { font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.05em; color: #888; }
      .wiz-rendering-field input, .wiz-rendering-field textarea {
        width: 100%; box-sizing: border-box; padding: 0.32rem 0.5rem;
        background: #1a1a2e; border: 1px solid #2a2f55; border-radius: 5px;
        color: #e0e0e0; font-size: 0.82rem; font-family: inherit;
      }
      .wiz-rendering-field input:focus, .wiz-rendering-field textarea:focus { outline: none; border-color: #4a9eff; }
      .wiz-rendering-field textarea { resize: vertical; min-height: 3rem; }
      .wiz-rendering-pt-row { display: flex; gap: 0.5rem; }
      .wiz-rendering-pt-row .wiz-rendering-field { flex: 1; }
      .wiz-rendering-slot { font-size: 0.72rem; color: #6f7790; font-style: italic; }
      .wiz-rendering-preview {
        font-size: 0.82rem; color: #cbd3e6; line-height: 1.55;
        background: #16213e; border-radius: 5px; padding: 0.35rem 0.5rem; min-height: 1.5rem;
      }
      .wiz-rendering-preview-lbl { font-size: 0.64rem; text-transform: uppercase; letter-spacing: 0.05em; color: #777; }

      .wiz-rendering-actions { display: flex; gap: 0.4rem; flex-wrap: wrap; }
      .wiz-rendering-btn {
        padding: 0.28rem 0.6rem; border-radius: 5px; font-size: 0.76rem; font-family: inherit;
        cursor: pointer; border: 1px solid #2a2f55; background: #1a1a2e; color: #cbd3e6;
      }
      .wiz-rendering-btn:hover:not(:disabled) { border-color: #4a9eff; }
      .wiz-rendering-btn:disabled { opacity: 0.5; cursor: not-allowed; }
      .wiz-rendering-btn.danger { color: #f0a08a; border-color: #5a3411; }
      .wiz-rendering-btn.danger:hover:not(:disabled) { border-color: #e94560; }
      .wiz-rendering-btn.primary { color: #9ee6b4; border-color: #2c5a3c; }

      .wiz-rendering-locked { opacity: 0.85; }
      .wiz-rendering-locked input:disabled,
      .wiz-rendering-locked textarea:disabled,
      .wiz-rendering-locked select:disabled,
      .wiz-rendering-locked button:disabled { cursor: not-allowed; }

      /* Inline symbol badges (mirrors wizard_finalize.js) */
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
        W.toast('Failed to load rendering state: ' + err.message, 'error')
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
        .catch(err => W.toast('Failed to refresh rendering state: ' + err.message, 'error'))
        .finally(() => { local.bootstrapping = false; });
      return;
    }

    paintFooter(footer, state);
    setLocked(local.locked);
  }

  function mountShellHtml() {
    return `
      <div data-role="rnd-help"></div>
      <div data-role="rnd-summary"></div>
      <div data-role="rnd-filters"></div>
      <div class="wiz-rendering-grid" data-role="rnd-grid">
        <div class="wiz-rendering-empty">Loading cards…</div>
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

  function paintHelp(root) {
    const slot = root.querySelector('[data-role="rnd-help"]');
    if (!slot) return;
    slot.innerHTML = `
      <div class="wiz-rendering-help">
        <span>🖼️</span>
        <span>Final review. Each card is rendered to its print-ready image. To fix a
          render (text overrun, awkward wording), click <strong>Edit</strong>, change
          a field, and <strong>Save &amp; re-render</strong>. To drop a card from the
          set, click <strong>Remove from set</strong> — the remaining cards in its
          number group renumber so collector numbers stay contiguous. When you're
          done, approve for print.</span>
      </div>
    `;
  }

  function paintSummary(root) {
    const slot = root.querySelector('[data-role="rnd-summary"]');
    if (!slot) return;
    const r = local.report;
    if (!r) { slot.innerHTML = ''; return; }
    const failed = r.failed || 0;
    slot.innerHTML = `
      <div class="wiz-rendering-summary-bar">
        <span><strong>${escHtml(String(r.rendered || 0))}</strong> rendered</span>
        <span><strong>${escHtml(String(r.skipped || 0))}</strong> skipped</span>
        <span class="${failed > 0 ? 'warn' : ''}"><strong>${escHtml(String(failed))}</strong> failed</span>
        ${r.elapsed_seconds ? `<span>${escHtml(String(r.elapsed_seconds))}s</span>` : ''}
      </div>
    `;
  }

  function paintFilters(root) {
    const slot = root.querySelector('[data-role="rnd-filters"]');
    if (!slot) return;
    if (!local.hasContent) { slot.innerHTML = ''; return; }
    slot.innerHTML = `
      <div class="wiz-rendering-filters">
        <label>Rarity
          <select data-role="rnd-filter-rarity">
            <option value="all" ${local.filter.rarity === 'all' ? 'selected' : ''}>All</option>
            <option value="common" ${local.filter.rarity === 'common' ? 'selected' : ''}>Common</option>
            <option value="uncommon" ${local.filter.rarity === 'uncommon' ? 'selected' : ''}>Uncommon</option>
            <option value="rare" ${local.filter.rarity === 'rare' ? 'selected' : ''}>Rare</option>
            <option value="mythic" ${local.filter.rarity === 'mythic' ? 'selected' : ''}>Mythic</option>
          </select>
        </label>
        <label>Render
          <select data-role="rnd-filter-rendered">
            <option value="all" ${local.filter.rendered === 'all' ? 'selected' : ''}>All</option>
            <option value="rendered" ${local.filter.rendered === 'rendered' ? 'selected' : ''}>Rendered</option>
            <option value="missing" ${local.filter.rendered === 'missing' ? 'selected' : ''}>Not rendered</option>
          </select>
        </label>
      </div>
    `;
    const bind = (role, key) => {
      const el = slot.querySelector(`[data-role="${role}"]`);
      if (el) el.onchange = () => { local.filter[key] = el.value; paintGrid(bodyRoot()); };
    };
    bind('rnd-filter-rarity', 'rarity');
    bind('rnd-filter-rendered', 'rendered');
  }

  // ---------------------------------------------------------------------------
  // Grid
  // ---------------------------------------------------------------------------

  function paintGrid(root) {
    const slot = root && root.querySelector('[data-role="rnd-grid"]');
    if (!slot) return;
    if (!local.hasContent) {
      const generating = local.stageStatus === 'running' || local.locked;
      slot.innerHTML = W.emptyStatePanel({
        generating,
        generatingMsg: 'Rendering is running — cards will appear as their images render.',
        emptyMsg: 'No cards yet. The Rendering stage must run first.',
        className: 'wiz-rendering-empty',
      });
      return;
    }
    const visible = visibleCards();
    if (visible.length === 0) {
      slot.innerHTML = `<div class="wiz-rendering-empty">No cards match the current filter.</div>`;
      return;
    }
    slot.innerHTML = visible.map(cardHtml).join('');
    visible.forEach(c => bindCard(slot, c.collector_number));
    setLocked(local.locked);
  }

  function visibleCards() {
    return local.cards.filter(c => {
      if (local.filter.rarity !== 'all' && c.rarity !== local.filter.rarity) return false;
      if (local.filter.rendered === 'rendered' && !c.has_render) return false;
      if (local.filter.rendered === 'missing' && c.has_render) return false;
      return true;
    });
  }

  function cardHtml(c) {
    const userBadge = (c.user_edited || c._dirty);
    const prov = userBadge ? 'user' : 'default';
    const cls = userBadge ? 'is-user' : '';
    const cn = c.collector_number;
    const thumb = c.has_render
      ? `<img class="wiz-rendering-thumb" data-role="rnd-thumb" src="${escAttr(imgUrl(cn))}" alt="${escAttr(c.name)}" loading="lazy">`
      : `<span class="wiz-rendering-thumb-missing" data-role="rnd-thumb-missing">Not rendered yet</span>`;

    return `
      <article class="wiz-rendering-card ${cls}" data-cn="${escAttr(cn)}">
        <div class="wiz-rendering-card-head">
          <span class="wiz-rendering-cn">${escHtml(cn)}</span>
          <span class="wiz-rendering-cardname">${escHtml(c.name || '(unnamed)')}</span>
          <span class="wiz-rendering-rarity ${escAttr(c.rarity || 'common')}">${escHtml(c.rarity || '')}</span>
          ${W.provenanceBadge(prov, { role: 'ai-badge' })}
          <span class="wiz-rendering-saved-tick" data-role="rnd-saved">Saved ✓</span>
        </div>
        <div class="wiz-rendering-thumb-wrap" data-role="rnd-thumb-wrap">${thumb}</div>
        ${c.slot_text ? `<div class="wiz-rendering-slot">Slot: ${escHtml(c.slot_text)}</div>` : ''}
        <div class="wiz-rendering-actions">
          <button type="button" class="wiz-rendering-btn" data-role="rnd-edit-toggle">Edit</button>
          <button type="button" class="wiz-rendering-btn danger" data-role="rnd-remove">Remove from set</button>
        </div>
        <div class="wiz-rendering-fields" data-role="rnd-fields">
          <div class="wiz-rendering-field">
            <label>Name</label>
            <input type="text" data-field="name" value="${escAttr(c.name || '')}">
          </div>
          <div class="wiz-rendering-field">
            <label>Mana cost</label>
            <input type="text" data-field="mana_cost" value="${escAttr(c.mana_cost || '')}">
          </div>
          <div class="wiz-rendering-field">
            <label>Type line</label>
            <input type="text" data-field="type_line" value="${escAttr(c.type_line || '')}">
          </div>
          <div class="wiz-rendering-field">
            <label>Oracle text</label>
            <textarea data-field="oracle_text" rows="4">${escHtml(c.oracle_text_editor != null ? c.oracle_text_editor : (c.oracle_text || ''))}</textarea>
            <span class="wiz-rendering-preview-lbl">Preview</span>
            <div class="wiz-rendering-preview" data-role="rnd-oracle-preview">${symbolizeHtml(c.oracle_text)}</div>
          </div>
          <div class="wiz-rendering-field">
            <label>Flavor text</label>
            <textarea data-field="flavor_text" rows="2">${escHtml(c.flavor_text || '')}</textarea>
          </div>
          <div class="wiz-rendering-pt-row">
            <div class="wiz-rendering-field">
              <label>Power</label>
              <input type="text" data-field="power" value="${escAttr(c.power == null ? '' : c.power)}">
            </div>
            <div class="wiz-rendering-field">
              <label>Toughness</label>
              <input type="text" data-field="toughness" value="${escAttr(c.toughness == null ? '' : c.toughness)}">
            </div>
            <div class="wiz-rendering-field">
              <label>Loyalty</label>
              <input type="text" data-field="loyalty" value="${escAttr(c.loyalty == null ? '' : c.loyalty)}">
            </div>
          </div>
          <div class="wiz-rendering-actions">
            <button type="button" class="wiz-rendering-btn primary" data-role="rnd-save">Save &amp; re-render</button>
          </div>
        </div>
      </article>
    `;
  }

  // ---------------------------------------------------------------------------
  // Per-card binding
  // ---------------------------------------------------------------------------

  function bindCard(slot, cn) {
    const el = slot.querySelector(`.wiz-rendering-card[data-cn="${W.cssEsc(cn)}"]`);
    if (!el) return;

    const toggle = el.querySelector('[data-role="rnd-edit-toggle"]');
    if (toggle) toggle.onclick = () => {
      el.classList.toggle('editing');
      toggle.textContent = el.classList.contains('editing') ? 'Close editor' : 'Edit';
    };

    el.querySelectorAll('[data-field]').forEach(input => {
      input.oninput = () => {
        const field = input.dataset.field;
        updateCard(cn, { [field]: input.value, _dirty: true });
        if (field === 'oracle_text') {
          const prev = el.querySelector('[data-role="rnd-oracle-preview"]');
          if (prev) prev.innerHTML = symbolizeHtml(input.value);
        }
        hideTick(el);
      };
    });

    const saveBtn = el.querySelector('[data-role="rnd-save"]');
    if (saveBtn) saveBtn.onclick = () => saveCard(cn, el);

    const removeBtn = el.querySelector('[data-role="rnd-remove"]');
    if (removeBtn) removeBtn.onclick = () => removeCard(cn);

    // Click the rendered thumbnail to open it full-scale. Bound on the wrap (not
    // the <img>) because refreshThumb swaps the wrap's innerHTML on re-render; the
    // wrap itself persists, so this binding survives. Reads the live <img> src so
    // a cache-busted re-render shows the latest pixels.
    const wrap = el.querySelector('[data-role="rnd-thumb-wrap"]');
    if (wrap) wrap.onclick = () => {
      const c = local.cards.find(x => x.collector_number === cn);
      if (!c || !c.has_render || !window.MTGAILightbox) return;
      const img = wrap.querySelector('[data-role="rnd-thumb"]');
      const url = (img && img.getAttribute('src')) || imgUrl(cn);
      const nm = (c && c.name) || cn;
      window.MTGAILightbox.open(url, { alt: nm, caption: `${nm} · ${cn}` });
    };
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

  function saveCard(cn, el) {
    W.runAiAction({
      isLocked: () => local.locked,
      setLocked,
      busyLabel: `Re-rendering ${cn}…`,
      url: '/api/wizard/rendering/save-card',
      body: () => ({ collector_number: cn, fields: gatherFields(cn) }),
      fallback: 'Re-render failed',
      onResult: () => {
        const c = local.cards.find(x => x.collector_number === cn);
        if (!c) return;
        // An edit never changes the collector number (only remove does), so the
        // card stays keyed by cn — just clear the dirty flag and refresh the image.
        c._dirty = false;
        c.user_edited = true;
        c.has_render = true;
        showTick(el);
        if (el) { el.classList.remove('editing'); el.classList.add('is-user'); }
        const tog = el && el.querySelector('[data-role="rnd-edit-toggle"]');
        if (tog) tog.textContent = 'Edit';
        refreshThumb(bodyRoot(), cn);
      },
    });
  }

  function removeCard(cn) {
    const c = local.cards.find(x => x.collector_number === cn);
    const nm = c ? (c.name || cn) : cn;
    W.runAiAction({
      isLocked: () => local.locked,
      setLocked,
      confirm: () => `Remove "${nm}" (${cn}) from the set? Remaining cards in its number group will renumber to stay contiguous. This cannot be undone.`,
      busyLabel: `Removing ${cn}…`,
      url: '/api/wizard/rendering/remove-card',
      body: () => ({ collector_number: cn }),
      fallback: 'Remove failed',
      onResult: (data) => {
        const renum = (data && data.renumbered) || [];
        if (renum.length) {
          W.toast(`Removed ${cn}; renumbered ${renum.length} card${renum.length !== 1 ? 's' : ''}.`, 'success');
        } else {
          W.toast(`Removed ${cn}.`, 'success');
        }
        // The whole pool's numbers may have shifted; refetch authoritative state.
        local.cards = [];
        local.hasContent = false;
        bootstrap(bodyRoot(), null).catch(err =>
          W.toast('Failed to refresh after remove: ' + err.message, 'error')
        );
      },
    });
  }

  function refreshThumb(root, cn) {
    if (!root) return;
    const el = root.querySelector(`.wiz-rendering-card[data-cn="${W.cssEsc(cn)}"]`);
    if (!el) return;
    const wrap = el.querySelector('[data-role="rnd-thumb-wrap"]');
    if (!wrap) return;
    wrap.innerHTML = `<img class="wiz-rendering-thumb" data-role="rnd-thumb" src="${escAttr(imgUrl(cn, Date.now()))}" alt="${escAttr(cn)}" loading="lazy">`;
  }

  function showTick(el) {
    const t = el && el.querySelector('[data-role="rnd-saved"]');
    if (!t) return;
    t.classList.add('show');
    clearTimeout(t._timer);
    t._timer = setTimeout(() => t.classList.remove('show'), 1600);
  }

  function hideTick(el) {
    const t = el && el.querySelector('[data-role="rnd-saved"]');
    if (t) t.classList.remove('show');
  }

  function updateCard(cn, patch) {
    const i = local.cards.findIndex(c => c.collector_number === cn);
    if (i >= 0) local.cards[i] = Object.assign({}, local.cards[i], patch);
  }

  // ---------------------------------------------------------------------------
  // Footer — Approve for print when paused on the latest tab (§1)
  // ---------------------------------------------------------------------------

  function paintFooter(footer, state) {
    if (!footer) return;
    const isLatest = !state || state.latestTabId === STAGE_ID;
    const status = local.stageStatus;

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Rendering is in the past — pipeline has moved on.</span>`;
    } else if (status === 'completed') {
      html = `<span class="wiz-footer-note">Set approved for print. 🎉</span>`;
    } else if (status === 'running') {
      html = `<span class="wiz-footer-note">Rendering cards…</span>`;
    } else if (status === 'paused_for_review') {
      html = `
        <button type="button" class="wiz-btn-primary" data-role="rnd-advance" ${local.locked ? 'disabled' : ''}>
          Approve for print
        </button>
        <span class="wiz-footer-note">Edit or remove any card above, then approve to finish.</span>
      `;
    } else if (status === 'failed') {
      html = `<span class="wiz-footer-note">Stage failed — check the progress strip for details.</span>`;
    } else {
      html = `<span class="wiz-footer-note">Runs automatically after Art Generation. Pauses here for final review.</span>`;
    }

    W.paintFooter(footer, html, { role: 'rnd-advance', onClick: onApprove });
  }

  function onApprove() {
    W.saveAndAdvance({
      stageId: STAGE_ID,
      saveUrl: '/api/wizard/rendering/approve',
      payload: () => ({}),
      isLocked: () => local.locked,
      setLocked,
      btnRole: 'rnd-advance',
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
      lockClass: 'wiz-rendering-locked',
      selectors: [
        '.wiz-rendering-card [data-field]',
        '.wiz-rendering-card button',
        '[data-role="rnd-filter-rarity"]',
        '[data-role="rnd-filter-rendered"]',
      ],
      footerSelector: '[data-role="rnd-advance"]',
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
