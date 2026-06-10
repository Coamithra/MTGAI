/**
 * Wizard "Conformance & Interactions" tab (stage_id ``conformance``).
 *
 * The single post-card_gen review gate. It runs two streamed LLM passes plus an
 * algorithmic duplicate scan, and bounces any flagged card back to Card
 * Generation. Both passes are **batched, flag-only, streamed** (~40 cards per LLM
 * call; the model emits a block only for cards it flags), so the tab renders ONE
 * per-card checklist with **two status checkboxes per card** — one for each pass:
 *
 *  - **[C] Conformance** — each card vs. its slot spec. As flags stream in, every
 *    earlier not-yet-flagged card flips to ✓ (an advancing "approved frontier");
 *    flagged cards show ✗. Driven by ``conformance_cards`` (seed) +
 *    ``conformance_card`` (per-card verdict). A card with no resolvable slot spec
 *    is not conformance-checked and shows a muted · in this column.
 *  - **[I] Interaction** — each card checked for degenerate interactions with the
 *    rest of the pool (cumulative-context batches). A flagged enabler shows ✗ with
 *    the diagnosis; everything else ✓. Driven by ``interaction_cards`` (seed) +
 *    ``interaction_card`` (per-card verdict). A clean card may flip to ✗ later if a
 *    subsequent batch flags it as an enabler against newer cards.
 *
 * A purely algorithmic duplicate check (functionally-identical-modulo-mana-cost)
 * runs first and seeds its hits into ``conformance_cards`` with conforms=false,
 * so a duplicate shows ✗ in the Conformance column from the first paint.
 *
 * A third algorithmic (no-LLM) surface — the **Resource Economy** panel — renders
 * below the card checklist: a per-resource makers-vs-consumers table (Food,
 * Treasure, custom mechanic tokens) with coverage warnings. It streams as a
 * ``conformance_step`` (``step.id === 'economy'``) and rebuilds from
 * ``result.steps`` on reload. Advisory only — no card is flagged from it.
 *
 * Per-pass states: ✓ ok · ✗ flagged · ⚠ unknown (batch truncated) · spinner
 * pending (seeded, awaiting verdict) · empty not-started · muted · not-applicable.
 * A card is flagged for regeneration if EITHER column is ✗.
 *
 * ``conformance_reset`` fires once at the start of a run to drop a prior run's
 * streamed rows. On reload / reattach the EventBus replays the buffered events;
 * if the buffer was cleared the tab falls back to the authoritative
 * ``stage.result.steps`` carried on stage_update (each step carries its full
 * per-card ``cards`` list for exactly this).
 *
 * Instance-aware (keys off ``stage.instance_id`` / ``tab.id``), so the backbone
 * and any inserted ``conformance.2`` re-run render + stream identically.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'conformance';

  if (!document.getElementById('wiz-gate-styles')) {
    const style = document.createElement('style');
    style.id = 'wiz-gate-styles';
    style.textContent = `
      .wiz-gate-step { margin-bottom: 1.4rem; }
      .wiz-gate-step-label { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.06em; color: #8b949e; margin-bottom: 0.4rem; }
      .wiz-gate-ok { font-size: 1.1rem; font-weight: 700; color: #00d4aa; margin-bottom: 0.8rem; }
      .wiz-gate-flagged { font-size: 1.1rem; font-weight: 700; color: #ffa502; margin-bottom: 0.8rem; }
      .wiz-gate-progress { font-size: 1.05rem; font-weight: 600; color: #8b949e; margin-bottom: 0.8rem; display: flex; align-items: center; gap: 0.5rem; }
      .wiz-gate-progress::before { content: ''; width: 0.9rem; height: 0.9rem; border-radius: 50%; border: 2px solid #ffffff22; border-top-color: #58a6ff; display: inline-block; animation: wiz-gate-spin 0.7s linear infinite; }
      .wiz-gate-paused { color: #ffa502; margin: 0 0 1rem; }
      /* Two-checkbox per-card checklist */
      .wiz-gate2-legend { display: grid; grid-template-columns: 1.4rem 1.4rem 1fr; gap: 0.5rem; padding: 0 0.4rem 0.3rem; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.05em; color: #6e7681; }
      .wiz-gate2-legend span { text-align: center; }
      .wiz-gate2-legend .wiz-gate2-leg-name { text-align: left; }
      .wiz-gate2-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.15rem; }
      .wiz-gate2-item { display: grid; grid-template-columns: 1.4rem 1.4rem 1fr; align-items: baseline; gap: 0.5rem; padding: 0.25rem 0.4rem; border-radius: 4px; }
      .wiz-gate2-item.wiz-gate2-bad { background: #ffa50212; }
      .wiz-gate2-cell { width: 1.4rem; text-align: center; font-weight: 700; }
      .wiz-cell-ok { color: #00d4aa; }
      .wiz-cell-bad { color: #ffa502; }
      .wiz-cell-unknown { color: #d29922; }
      .wiz-cell-na { color: #484f58; }
      .wiz-cell-pending { display: inline-block; width: 0.85rem; height: 0.85rem; border-radius: 50%; border: 2px solid #ffffff1a; border-top-color: #58a6ff; animation: wiz-gate-spin 0.7s linear infinite; }
      .wiz-gate2-name { color: #ddd; }
      .wiz-gate2-item.wiz-gate2-bad .wiz-gate2-name { color: #eee; }
      .wiz-gate2-reason { grid-column: 3; margin-top: 0.1rem; color: #ccc; font-size: 0.85rem; }
      .wiz-gate2-reason b { color: #8b949e; font-weight: 600; }
      .wiz-gate-waiting { font-size: 1.05rem; color: #6e7681; }
      /* Resource-economy panel (third algorithmic step) */
      .wiz-econ { margin-top: 1.6rem; border-top: 1px solid #ffffff14; padding-top: 1.2rem; }
      .wiz-econ-warns { list-style: none; padding: 0; margin: 0 0 0.9rem; display: flex; flex-direction: column; gap: 0.4rem; }
      .wiz-econ-warn { background: #ffa50212; border-left: 3px solid #ffa502; color: #f0d9b5; padding: 0.45rem 0.6rem; border-radius: 4px; font-size: 0.85rem; }
      .wiz-econ-ok { color: #00d4aa; font-weight: 600; margin-bottom: 0.8rem; }
      .wiz-econ-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
      .wiz-econ-table th { text-align: left; color: #8b949e; font-weight: 600; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; padding: 0.3rem 0.5rem; border-bottom: 1px solid #ffffff14; }
      .wiz-econ-table th.wiz-econ-num, .wiz-econ-table td.wiz-econ-num { text-align: center; width: 4.5rem; }
      .wiz-econ-table td { padding: 0.35rem 0.5rem; border-bottom: 1px solid #ffffff0a; color: #ddd; vertical-align: top; }
      .wiz-econ-res { font-weight: 600; color: #eee; }
      .wiz-econ-make { color: #00d4aa; font-weight: 700; }
      .wiz-econ-use { color: #58a6ff; font-weight: 700; }
      .wiz-econ-low { color: #ffa502; }
      .wiz-econ-sub { color: #8b949e; font-size: 0.78rem; }
      .wiz-econ-mech { color: #b392f0; font-size: 0.78rem; }
      .wiz-econ-empty { color: #6e7681; font-size: 0.9rem; }
      @keyframes wiz-gate-spin { to { transform: rotate(360deg); } }
    `;
    document.head.appendChild(style);
  }

  // Per-instance tab state, keyed by instance id (tab.id). An inserted re-run
  // (conformance.2) gets its own entry so its streamed rows never bleed into the
  // backbone tab.
  //   rows       — slot_id -> {slot_id, card_name, conf:{state,reason}, inter:{state,reason}}
  //   order      — slot_ids in first-seen order (stable render order)
  //   confSeeded — slot_ids that appeared in conformance_cards (the conf-applicable
  //                set); a card absent here when interactions seeds is "na" for conf
  //   streaming  — true once a reset/stream arrives; the merge then ignores the
  //                (stale until refreshed) authoritative result
  const instances = new Map();
  function stateFor(instanceId) {
    let s = instances.get(instanceId);
    if (!s) {
      s = { rows: new Map(), order: [], confSeeded: new Set(), streaming: false, stage: null, economy: null };
      instances.set(instanceId, s);
    }
    return s;
  }

  W.registerStageRenderer(STAGE_ID, render);

  // SSE bridge — wizard.js routes the conformance_* + interaction_* events here.
  // Each carries instance_id (== "conformance" for the backbone), so it lands in
  // ITS instance state + repaints ITS tab if mounted. A buffered replay on
  // reattach drives the same path, so a late-loading tab catches up.
  W.onConformanceStream = function (name, data) {
    const instanceId = (data && data.instance_id) || STAGE_ID;
    const local = stateFor(instanceId);
    local.streaming = true;
    if (name === 'conformance_reset') {
      local.rows = new Map();
      local.order = [];
      local.confSeeded = new Set();
      local.economy = null;
    } else if (name === 'conformance_step') {
      // The economy step streams as a conformance_step the instant the (no-LLM)
      // analysis returns; the per-card conformance/interaction steps are rebuilt
      // from their streamed cards, so we only capture the economy one here.
      if (data.step && data.step.id === 'economy') local.economy = data.step;
    } else if (name === 'conformance_cards') {
      (data.cards || []).forEach(c => {
        const row = ensureRow(local, c.slot_id, c.card_name);
        local.confSeeded.add(c.slot_id);
        // A card pre-flagged by the algorithmic duplicate check arrives
        // conforms=false → ✗ from the first paint; everything else pending.
        row.conf = { state: c.conforms === false ? 'bad' : 'pending', reason: c.reason || '' };
      });
    } else if (name === 'conformance_card') {
      const row = ensureRow(local, data.slot_id, data.card_name);
      row.conf = { state: verdictState(data.conforms), reason: data.reason || '' };
    } else if (name === 'interaction_cards') {
      (data.cards || []).forEach(c => {
        const row = ensureRow(local, c.slot_id, c.card_name);
        row.inter = { state: 'pending', reason: '' };
        // Not in the conformance-applicable set → no slot spec to conform to.
        if (!local.confSeeded.has(c.slot_id)) row.conf = { state: 'na', reason: '' };
      });
    } else if (name === 'interaction_card') {
      const row = ensureRow(local, data.slot_id, data.card_name);
      row.inter = { state: verdictState(data.interacts), reason: data.reason || '' };
      // A flagged enabler can be an EARLIER card never seeded by the conformance
      // pass (a scoped re-run checks only regenerated cards but may pin the root
      // cause on an existing one). Show its Conformance column as muted · — it was
      // not conformance-checked here — matching the authoritative reload path.
      if (!row.conf && !local.confSeeded.has(data.slot_id)) {
        row.conf = { state: 'na', reason: '' };
      }
    }
    repaint(instanceId, local);
  };

  function ensureRow(local, slotId, cardName) {
    let row = local.rows.get(slotId);
    if (!row) {
      row = { slot_id: slotId, card_name: cardName || '', conf: null, inter: null };
      local.rows.set(slotId, row);
      local.order.push(slotId);
    } else if (cardName && !row.card_name) {
      row.card_name = cardName;
    }
    return row;
  }

  // A boolean|null verdict → a column state. true=ok, false=flagged, null=unknown
  // (batch truncated past it), undefined=still pending.
  function verdictState(v) {
    if (v === true) return 'ok';
    if (v === false) return 'bad';
    if (v === null) return 'unknown';
    return 'pending';
  }

  function repaint(instanceId, local) {
    const root = W.tabRoot(instanceId);
    if (!root) return; // tab not mounted — buffered events replay on next mount
    const content = root.querySelector('[data-role="content"]');
    if (!content) return;
    content.innerHTML = W.rerunButtonHtml() + bodyHtml(local.stage, local);
    W.bindRerunButton(content, local.stage);
  }

  function render({ tab, state, stage, content, footer }) {
    const instanceId = (stage && stage.instance_id) || (tab && tab.id) || STAGE_ID;
    const local = stateFor(instanceId);
    local.stage = stage;
    if (content) {
      content.innerHTML = W.rerunButtonHtml() + bodyHtml(stage, local);
      W.bindRerunButton(content, stage);
    }
    paintFooter(footer, state, stage);
  }

  function bodyHtml(stage, local) {
    const status = stage ? stage.status : 'pending';
    const result = (stage && stage.result) || {};

    const economyHtml = economyPanelHtml(resolveEconomy(local, result));

    const rows = resolveRows(local, result);
    const hasAny = rows.length > 0;
    if (status === 'pending' && !hasAny && !(local && local.streaming)) {
      return '<div class="wiz-stage-empty">Conformance &amp; interaction check has not run yet.</div>';
    }
    if (!hasAny) {
      const checking = status === 'running' || (local && local.streaming);
      return '<div class="wiz-gate-step"><div class="wiz-gate-step-label">Conformance &amp; Interactions</div>'
        + (checking ? '<div class="wiz-gate-progress">Checking…</div>' : '<div class="wiz-gate-waiting">Waiting…</div>')
        + '</div>' + economyHtml;
    }

    // A flagging gate bounces straight to card_gen (no round cap), so it never
    // pauses here with cards still flagged — the only pause left is a clean-pass
    // break-point, which has nothing flagged to note.
    const checking = status === 'running' || (local && local.streaming);
    return cardsHtml(rows, checking) + economyHtml;
  }

  // Live stream state wins; otherwise pull the economy step from the
  // authoritative result.steps (reload after the buffer cleared).
  function resolveEconomy(local, result) {
    if (local && local.economy) return local.economy;
    const steps = Array.isArray(result.steps) ? result.steps : [];
    return steps.find(s => s && s.id === 'economy') || null;
  }

  // ---- source resolution (live stream overrides stale authoritative mid-run) --

  // Returns an ordered array of unified rows {slot_id, card_name, conf, inter}.
  // Live stream state wins; otherwise rebuild from the authoritative per-step
  // ``cards`` snapshots (reload after the buffer was cleared).
  function resolveRows(local, result) {
    if (local && local.order.length) {
      return local.order.map(id => local.rows.get(id)).filter(Boolean);
    }
    if (local && local.streaming) return [];
    return rowsFromSteps(result);
  }

  function rowsFromSteps(result) {
    const steps = Array.isArray(result.steps) ? result.steps : [];
    const conf = steps.find(s => s && s.id === 'conformance');
    const inter = steps.find(s => s && s.id === 'interactions');
    const rows = new Map();
    const order = [];
    const ensure = (sid, name) => {
      let r = rows.get(sid);
      if (!r) { r = { slot_id: sid, card_name: name || '', conf: null, inter: null }; rows.set(sid, r); order.push(sid); }
      else if (name && !r.card_name) r.card_name = name;
      return r;
    };
    const confSeeded = new Set();
    (conf && Array.isArray(conf.cards) ? conf.cards : []).forEach(c => {
      confSeeded.add(c.slot_id);
      ensure(c.slot_id, c.card_name).conf = { state: verdictState(c.conforms), reason: c.reason || '' };
    });
    (inter && Array.isArray(inter.cards) ? inter.cards : []).forEach(c => {
      const r = ensure(c.slot_id, c.card_name);
      r.inter = { state: verdictState(c.interacts), reason: c.reason || '' };
      if (!confSeeded.has(c.slot_id)) r.conf = { state: 'na', reason: '' };
    });
    // Back-compat: a pre-rework instance persisted a flat conformance {flagged}.
    if (!conf || !Array.isArray(conf.cards) || !conf.cards.length) {
      const flat = conf && Array.isArray(conf.flagged) ? conf.flagged : (result.flagged || []);
      flat.forEach(f => { ensure(f.slot_id, f.card_name).conf = { state: 'bad', reason: f.reason || '' }; });
    }
    if (!inter || !Array.isArray(inter.cards) || !inter.cards.length) {
      const flat = inter && Array.isArray(inter.flagged) ? inter.flagged : [];
      flat.forEach(f => { ensure(f.slot_id, f.card_name).inter = { state: 'bad', reason: f.reason || '' }; });
    }
    return order.map(id => rows.get(id)).filter(Boolean);
  }

  // ---- rendering -------------------------------------------------------------

  function cardsHtml(rows, checking) {
    // "pending" = a seeded-but-unresolved cell (spinner); "none" = a pass not
    // started for this card yet (e.g. interactions during the conformance pass).
    const anyPending = rows.some(r => colState(r.conf) === 'pending' || colState(r.inter) === 'pending');
    const flagged = rows.filter(isFlagged);
    let header;
    if (checking && anyPending) {
      header = '<div class="wiz-gate-progress">Checking cards…</div>';
    } else if (flagged.length) {
      header = '<div class="wiz-gate-flagged">' + flagged.length + ' card(s) flagged for regeneration</div>';
    } else {
      header = '<div class="wiz-gate-ok">✓ Every card matches its slot spec and the pool is clean.</div>';
    }
    const legend = '<div class="wiz-gate2-legend"><span title="Conformance">C</span>'
      + '<span title="Interactions">I</span><span class="wiz-gate2-leg-name">Card</span></div>';
    const items = rows.map(cardItemHtml).join('');
    return '<div class="wiz-gate-step">'
      + '<div class="wiz-gate-step-label">Conformance &amp; Interactions</div>'
      + header + legend
      + '<ul class="wiz-gate2-list">' + items + '</ul>'
      + '</div>';
  }

  // 'none' = pass not started for this card (unseeded column); distinct from
  // 'pending' = seeded, awaiting its streamed verdict.
  function colState(col) {
    return col && col.state ? col.state : 'none';
  }

  function isFlagged(r) {
    return colState(r.conf) === 'bad' || colState(r.inter) === 'bad';
  }

  function cellHtml(col) {
    const state = colState(col);
    if (state === 'ok') return '<span class="wiz-gate2-cell wiz-cell-ok">✓</span>';
    if (state === 'bad') return '<span class="wiz-gate2-cell wiz-cell-bad">✗</span>';
    if (state === 'unknown') return '<span class="wiz-gate2-cell wiz-cell-unknown">⚠</span>';
    if (state === 'na') return '<span class="wiz-gate2-cell wiz-cell-na">·</span>';
    if (state === 'none') return '<span class="wiz-gate2-cell"></span>';
    return '<span class="wiz-gate2-cell"><span class="wiz-cell-pending"></span></span>';
  }

  function reasonHtml(label, col) {
    const state = colState(col);
    if ((state === 'bad' || state === 'unknown') && col && col.reason) {
      return '<div class="wiz-gate2-reason"><b>' + label + ':</b> ' + escHtml(col.reason) + '</div>';
    }
    return '';
  }

  function cardItemHtml(r) {
    const name = escHtml(r.card_name || r.slot_id || '?');
    const cls = isFlagged(r) ? ' wiz-gate2-bad' : '';
    return '<li class="wiz-gate2-item' + cls + '">'
      + cellHtml(r.conf) + cellHtml(r.inter)
      + '<span class="wiz-gate2-name">' + name + '</span>'
      + reasonHtml('Conformance', r.conf)
      + reasonHtml('Interaction', r.inter)
      + '</li>';
  }

  // ---- resource-economy panel ------------------------------------------------

  function colorBreakdown(byColor) {
    const entries = Object.entries(byColor || {}).filter(([, n]) => n);
    if (!entries.length) return '';
    entries.sort((a, b) => b[1] - a[1]);
    return entries.map(([c, n]) => c + ':' + n).join(' ');
  }

  function mechHtml(mechanics) {
    if (!Array.isArray(mechanics) || !mechanics.length) return '';
    const parts = mechanics.map(m =>
      escHtml(m.name) + ' (' + escHtml(m.role || '') + ', ' + (m.carriers || 0) + ' card' + ((m.carriers || 0) === 1 ? '' : 's') + ')'
    );
    return '<div class="wiz-econ-mech">via ' + parts.join(', ') + '</div>';
  }

  function economyPanelHtml(step) {
    if (!step) return '';
    const report = step.report || {};
    const resources = Array.isArray(report.resources) ? report.resources : [];
    const warnings = Array.isArray(step.warnings) ? step.warnings : (report.warnings || []);

    let warnHtml;
    if (warnings.length) {
      warnHtml = '<ul class="wiz-econ-warns">'
        + warnings.map(w => '<li class="wiz-econ-warn">⚠ ' + escHtml(w) + '</li>').join('')
        + '</ul>';
    } else if (resources.length) {
      warnHtml = '<div class="wiz-econ-ok">✓ Every consumed resource has adequate makers.</div>';
    } else {
      warnHtml = '';
    }

    let table;
    if (!resources.length) {
      table = '<div class="wiz-econ-empty">No consumable token resources (Food, Treasure, '
        + 'custom mechanic tokens) are in play in this set.</div>';
    } else {
      const rows = resources.map(r => {
        const low = (r.consumers > 0 && r.makers <= 1) ? ' wiz-econ-low' : '';
        const makeSub = colorBreakdown(r.makers_by_color);
        const useSub = colorBreakdown(r.consumers_by_color);
        return '<tr>'
          + '<td class="wiz-econ-res">' + escHtml(r.name) + mechHtml(r.mechanics) + '</td>'
          + '<td class="wiz-econ-num"><span class="wiz-econ-make' + low + '">' + (r.makers || 0) + '</span>'
          + (makeSub ? '<div class="wiz-econ-sub">' + escHtml(makeSub) + '</div>' : '') + '</td>'
          + '<td class="wiz-econ-num"><span class="wiz-econ-use">' + (r.consumers || 0) + '</span>'
          + (useSub ? '<div class="wiz-econ-sub">' + escHtml(useSub) + '</div>' : '') + '</td>'
          + '</tr>';
      }).join('');
      table = '<table class="wiz-econ-table"><thead><tr>'
        + '<th>Resource</th><th class="wiz-econ-num">Makers</th><th class="wiz-econ-num">Consumers</th>'
        + '</tr></thead><tbody>' + rows + '</tbody></table>';
    }

    return '<div class="wiz-econ"><div class="wiz-gate-step-label">Resource Economy</div>'
      + warnHtml + table + '</div>';
  }

  function paintFooter(footer, state, stage) {
    if (!footer) return;
    const status = stage ? stage.status : 'pending';
    const instanceId = stage ? stage.instance_id : null;
    const isLatest = !!instanceId && !!state && state.latestTabId === instanceId;
    let html;
    if (!isLatest) {
      html = '<span class="wiz-footer-note">Past stage — use Edit above to re-run from here.</span>';
    } else if (status === 'paused_for_review' || W.completedTipCanAdvance(state, instanceId)) {
      // 'completed' + can-advance is the saved/reopened dead-end: the gate
      // finished but the pipeline persisted PAUSED with a later stage pending
      // and no PAUSED_FOR_REVIEW pause. Surface the same Next-step button so
      // the user can resume the engine instead of being stranded.
      const next = W.nextStageEntryAfter(instanceId);
      html = '<button type="button" class="wiz-btn-primary" data-role="next-step">'
        + escHtml(next ? 'Next step: ' + next.name : 'Next step') + '</button>';
    } else if (status === 'failed') {
      html = '<span class="wiz-footer-note">Stage failed — see the error above.</span>';
    } else if (status === 'running') {
      html = '<span class="wiz-footer-note">Checking…</span>';
    } else {
      html = '<span class="wiz-footer-note">This gate runs automatically; a clean pass advances. '
        + 'Flagged cards bounce back to Card Generation.</span>';
    }
    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
      const btn = footer.querySelector('button[data-role="next-step"]');
      if (btn) bindNextStepButton(btn);
    }
  }

  function bindNextStepButton(btn) {
    btn.onclick = async () => {
      const original = btn.textContent;
      btn.disabled = true;
      btn.textContent = 'Advancing…';
      try {
        const resp = await W.postJSON('/api/wizard/advance', {});
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          W.toast(data.error || 'Advance failed', 'error');
          btn.disabled = false;
          btn.textContent = original;
        }
      } catch (err) {
        W.toast('Network error: ' + err.message, 'error');
        btn.disabled = false;
        btn.textContent = original;
      }
    };
  }

  function escHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
  }
})();
