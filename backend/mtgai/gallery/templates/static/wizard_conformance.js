/**
 * Wizard "Conformance & Interactions" tab (stage_id ``conformance``).
 *
 * The single post-card_gen review gate. It runs three steps internally and
 * bounces any flagged card back to Card Generation. The tab renders two
 * sections that fill in live (the algorithmic duplicate check has no section of
 * its own — its hits are folded into the Conformance checklist as pre-failed
 * rows):
 *
 *  - **Conformance** runs ONE LLM call per card. The tab shows a checklist of
 *    every card (name only) up front, then appends a ✓ (conforms) / ✗ (flagged)
 *    to each as its verdict streams in — driven by ``conformance_cards`` (the
 *    initial list) + ``conformance_card`` (per-card verdict). A card whose check
 *    errored shows a neutral ⚠ and is never flagged.
 *  - **Interaction Check** is one whole-pool call; its section shows "Checking…"
 *    then the OK / flagged result, driven by ``conformance_step``.
 *
 * A purely algorithmic duplicate check (functionally-identical-modulo-mana-cost)
 * runs first and seeds its hits into ``conformance_cards`` with conforms=false,
 * so a duplicate shows an X in the Conformance checklist from the first paint.
 *
 * ``conformance_reset`` fires once at the start of a run to drop a prior run's
 * streamed rows. On reload / reattach the EventBus replays the buffered events;
 * if the buffer was cleared the tab falls back to the authoritative
 * ``stage.result.steps`` carried on stage_update (the conformance step carries
 * its full per-card ``cards`` list for exactly this).
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
      .wiz-gate-analysis { color: #aaa; font-style: italic; margin: 0 0 1rem; }
      .wiz-gate-paused { color: #ffa502; margin: 0 0 1rem; }
      .wiz-gate-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.6rem; }
      .wiz-gate-list li { background: #ffffff08; border-left: 3px solid #ffa502; border-radius: 4px; padding: 0.6rem 0.8rem; }
      .wiz-gate-reason { color: #ccc; font-size: 0.9rem; margin-top: 0.25rem; }
      .wiz-gate-checking { font-size: 1.05rem; font-weight: 600; color: #8b949e; display: flex; align-items: center; gap: 0.5rem; }
      .wiz-gate-checking::before { content: ''; width: 0.9rem; height: 0.9rem; border-radius: 50%; border: 2px solid #ffffff22; border-top-color: #58a6ff; display: inline-block; animation: wiz-gate-spin 0.7s linear infinite; }
      .wiz-gate-waiting { font-size: 1.05rem; color: #6e7681; }
      /* Per-card conformance checklist */
      .wiz-conf-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.15rem; }
      .wiz-conf-item { display: grid; grid-template-columns: 1.4rem 1fr; align-items: baseline; gap: 0.5rem; padding: 0.25rem 0.4rem; border-radius: 4px; }
      .wiz-conf-item.wiz-conf-bad { background: #ffa50212; }
      .wiz-conf-icon { width: 1.4rem; text-align: center; font-weight: 700; }
      .wiz-conf-ok .wiz-conf-icon { color: #00d4aa; }
      .wiz-conf-bad .wiz-conf-icon { color: #ffa502; }
      .wiz-conf-unknown .wiz-conf-icon { color: #d29922; }
      .wiz-conf-pending .wiz-conf-name { color: #8b949e; }
      .wiz-conf-pending .wiz-conf-icon { display: inline-block; width: 0.85rem; height: 0.85rem; border-radius: 50%; border: 2px solid #ffffff1a; border-top-color: #58a6ff; animation: wiz-gate-spin 0.7s linear infinite; }
      .wiz-conf-name { color: #ddd; }
      .wiz-conf-item .wiz-gate-reason { grid-column: 2; margin-top: 0.1rem; }
      @keyframes wiz-gate-spin { to { transform: rotate(360deg); } }
    `;
    document.head.appendChild(style);
  }

  const CONF_DEF = { id: 'conformance', label: 'Conformance' };
  const INTER_DEF = { id: 'interactions', label: 'Interaction Check' };

  // Per-step empty-state copy.
  const STEP_EMPTY = {
    conformance: '✓ Every card matches its slot spec.',
    interactions: '✓ No degenerate interactions found.',
  };

  // Per-instance tab state, keyed by instance id (tab.id). An inserted re-run
  // (conformance.2) gets its own entry so its streamed rows never bleed into the
  // backbone tab.
  //   steps     — conformance_step objects by id (the interactions verdict; the
  //               conformance step is mostly carried for its authoritative cards)
  //   confCards — ordered per-card checklist [{slot_id, card_name, conforms, reason}]
  //   confById  — slot_id -> the confCards entry (in-place updates)
  //   streaming — true once a reset/stream for this instance arrives; the merge
  //               then ignores the (stale until refreshed) authoritative result
  const instances = new Map();
  function stateFor(instanceId) {
    let s = instances.get(instanceId);
    if (!s) {
      s = { steps: {}, confCards: [], confById: {}, streaming: false, stage: null };
      instances.set(instanceId, s);
    }
    return s;
  }

  W.registerStageRenderer(STAGE_ID, render);

  // SSE bridge — wizard.js routes the conformance_* events here. Each carries
  // instance_id (== "conformance" for the backbone), so it lands in ITS instance
  // state + repaints ITS tab if mounted. A buffered replay on reattach drives the
  // same path, so a late-loading tab catches up.
  W.onConformanceStream = function (name, data) {
    const instanceId = (data && data.instance_id) || STAGE_ID;
    const local = stateFor(instanceId);
    local.streaming = true;
    if (name === 'conformance_reset') {
      local.steps = {};
      local.confCards = [];
      local.confById = {};
    } else if (name === 'conformance_cards') {
      // A card may arrive pre-flagged (conforms === false) when it was caught by
      // the algorithmic duplicate check — it renders as an X from the first paint
      // with its reason. Everything else starts pending (conforms undefined).
      local.confCards = (data.cards || []).map(c => ({
        slot_id: c.slot_id,
        card_name: c.card_name,
        conforms: c.conforms === false ? false : undefined,
        reason: c.reason || '',
      }));
      local.confById = {};
      local.confCards.forEach(c => { local.confById[c.slot_id] = c; });
    } else if (name === 'conformance_card') {
      let entry = local.confById[data.slot_id];
      if (!entry) {
        entry = { slot_id: data.slot_id, card_name: data.card_name, conforms: undefined, reason: '' };
        local.confCards.push(entry);
        local.confById[data.slot_id] = entry;
      }
      entry.conforms = data.conforms;
      entry.reason = data.reason || '';
      if (data.card_name) entry.card_name = data.card_name;
    } else if (name === 'conformance_step' && data.step && data.step.id) {
      local.steps[data.step.id] = data.step;
    }
    repaint(instanceId, local);
  };

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

    const confCards = resolveConfCards(local, result);
    const confStep = confCards ? null : resolveConfStep(local, result);
    const interStep = resolveInterStep(local, result);

    const hasAny = !!confCards || !!confStep || !!interStep;
    if (status === 'pending' && !hasAny && !(local && local.streaming)) {
      return '<div class="wiz-stage-empty">Conformance &amp; interaction check has not run yet.</div>';
    }

    const pausedNote = (status === 'paused_for_review' && (result.flagged || []).length)
      ? '<p class="wiz-gate-paused">Review limit reached — these cards are left flagged for you '
        + 'to edit or accept by hand before continuing.</p>'
      : '';

    const checking = status === 'running' || (local && local.streaming);

    // Conformance section: prefer the per-card checklist; fall back to the old
    // flat-step rendering for a pre-rework instance with no card list.
    let confSection;
    if (confCards) {
      confSection = conformanceCardsHtml(confCards, checking);
    } else if (confStep) {
      confSection = stepHtml(confStep);
    } else {
      confSection = stepPendingHtml(CONF_DEF, checking);
    }

    const interSection = interStep ? stepHtml(interStep) : stepPendingHtml(INTER_DEF, checking);

    return pausedNote + confSection + interSection;
  }

  // ---- source resolution (live stream overrides stale authoritative mid-run) --

  function resolveConfCards(local, result) {
    if (local) {
      if (local.confCards && local.confCards.length) return local.confCards;
      const st = local.steps && local.steps.conformance;
      if (st && Array.isArray(st.cards) && st.cards.length) return st.cards;
      if (local.streaming) return null; // mid-run: don't show stale authoritative
    }
    const cs = (Array.isArray(result.steps) ? result.steps : []).find(s => s && s.id === 'conformance');
    if (cs && Array.isArray(cs.cards) && cs.cards.length) return cs.cards;
    return null;
  }

  function resolveConfStep(local, result) {
    const live = local && local.steps && local.steps.conformance;
    if (live) return live;
    if (local && local.streaming) return null;
    let s = (Array.isArray(result.steps) ? result.steps : []).find(x => x && x.id === 'conformance');
    if (!s && ((result.flagged || []).length || result.analysis)) {
      // Backward-compat: a pre-merge instance persisted a flat {flagged, analysis}.
      s = { id: 'conformance', label: 'Conformance', flagged: result.flagged || [], analysis: result.analysis || '' };
    }
    return s || null;
  }

  function resolveInterStep(local, result) {
    const live = local && local.steps && local.steps.interactions;
    if (live) return live;
    if (local && local.streaming) return null;
    return (Array.isArray(result.steps) ? result.steps : []).find(s => s && s.id === 'interactions') || null;
  }

  // ---- rendering -------------------------------------------------------------

  function conformanceCardsHtml(cards, checking) {
    const total = cards.length;
    const pending = cards.filter(c => c.conforms === undefined);
    const flagged = cards.filter(c => c.conforms === false);
    const done = total - pending.length;
    let header;
    if (pending.length && checking) {
      header = '<div class="wiz-gate-progress">Checking each card… ' + done + '/' + total + '</div>';
    } else if (flagged.length) {
      header = '<div class="wiz-gate-flagged">' + flagged.length + ' card(s) flagged for regeneration</div>';
    } else {
      header = '<div class="wiz-gate-ok">' + STEP_EMPTY.conformance + '</div>';
    }
    const items = cards.map(confCardItemHtml).join('');
    return '<div class="wiz-gate-step">'
      + '<div class="wiz-gate-step-label">Conformance</div>'
      + header
      + '<ul class="wiz-conf-list">' + items + '</ul>'
      + '</div>';
  }

  function confCardItemHtml(c) {
    let icon, cls;
    if (c.conforms === true) { icon = '✓'; cls = 'wiz-conf-ok'; }
    else if (c.conforms === false) { icon = '✗'; cls = 'wiz-conf-bad'; }
    else if (c.conforms === null) { icon = '⚠'; cls = 'wiz-conf-unknown'; }
    else { icon = ''; cls = 'wiz-conf-pending'; }
    const name = escHtml(c.card_name || c.slot_id || '?');
    const showReason = (c.conforms === false || c.conforms === null) && c.reason;
    const reason = showReason ? '<div class="wiz-gate-reason">' + escHtml(c.reason) + '</div>' : '';
    return '<li class="wiz-conf-item ' + cls + '">'
      + '<span class="wiz-conf-icon">' + icon + '</span>'
      + '<span class="wiz-conf-name">' + name + '</span>'
      + reason
      + '</li>';
  }

  function stepHtml(step) {
    const flagged = step.flagged || [];
    const label = step.label || step.id || 'Step';
    const emptyMsg = STEP_EMPTY[step.id] || ('✓ ' + escHtml(label) + ': nothing flagged.');
    const header = flagged.length === 0
      ? '<div class="wiz-gate-ok">' + emptyMsg + '</div>'
      : '<div class="wiz-gate-flagged">' + flagged.length + ' card(s) flagged for regeneration</div>';
    const analysisBlock = step.analysis
      ? '<p class="wiz-gate-analysis">' + escHtml(step.analysis) + '</p>' : '';
    const list = flagged.length
      ? '<ul class="wiz-gate-list">' + flagged.map(flaggedItemHtml).join('') + '</ul>'
      : '';
    return '<div class="wiz-gate-step">'
      + '<div class="wiz-gate-step-label">' + escHtml(label) + '</div>'
      + header + analysisBlock + list
      + '</div>';
  }

  function stepPendingHtml(def, checking) {
    const body = checking
      ? '<div class="wiz-gate-checking">Checking…</div>'
      : '<div class="wiz-gate-waiting">Waiting…</div>';
    return '<div class="wiz-gate-step">'
      + '<div class="wiz-gate-step-label">' + escHtml(def.label) + '</div>'
      + body
      + '</div>';
  }

  function flaggedItemHtml(f) {
    const name = f.card_name ? ' — ' + escHtml(f.card_name) : '';
    return '<li><strong>' + escHtml(f.slot_id || '?') + '</strong>' + name
      + '<div class="wiz-gate-reason">' + escHtml(f.reason || '') + '</div></li>';
  }

  function paintFooter(footer, state, stage) {
    if (!footer) return;
    const status = stage ? stage.status : 'pending';
    const instanceId = stage ? stage.instance_id : null;
    const isLatest = !!instanceId && !!state && state.latestTabId === instanceId;
    let html;
    if (!isLatest) {
      html = '<span class="wiz-footer-note">Past stage — use Edit above to re-run from here.</span>';
    } else if (status === 'paused_for_review') {
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
