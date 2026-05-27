/**
 * Wizard Skeleton tab — the deterministic default skeleton vs its LLM relabel.
 *
 * Registers via ``W.registerStageRenderer('skeleton', ...)`` so the standard
 * wizard_stage.js shell owns the header (status pill, break-point toggle, Edit
 * button); we paint the body + footer.
 *
 * Skeleton Generation is one stage that builds the deterministic default
 * skeleton, then rewrites each slot's one-line descriptor with the LLM to fit
 * the set (theme / constraints / mechanics / requests). Each slot here shows
 * its DEFAULT descriptor diffed against the LLM's TWEAKED descriptor — a proper
 * word-level diff highlights exactly what changed — with the tweaked text
 * editable. Refresh re-rolls the relabel; the stage auto-runs it, so there's no
 * manual "generate" gate on the happy path.
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
  };

  W.registerStageRenderer(STAGE_ID, render);
  // Registered at module load (not in render) so live relabel events are caught
  // even when the engine runs the skeleton stage while another tab is active.
  W.onSkeletonStream = onSkeletonStream;

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
      <div class="wiz-skel-summary" data-role="skel-summary">
        <div class="wiz-skel-loading">Loading skeleton…</div>
      </div>
      <div class="wiz-skel-grid" data-role="skel-grid"></div>
    `;
  }

  // ----------------------------------------------------------------------

  async function bootstrap(root, state) {
    const resp = await fetch('/api/wizard/skeleton/state');
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.error || `HTTP ${resp.status}`);
    }
    const data = await resp.json();
    local.slots = Array.isArray(data.slots) ? data.slots : [];
    local.setParams = data.set_params || local.setParams;
    local.themeSummary = data.theme_summary || '';
    local.modelId = data.model_id || '';
    local.stageStatus = data.stage_status || local.stageStatus;
    local.incomplete = !!data.incomplete;
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

    paintSummary(root, state);
    paintGrid(root, state);
    paintFooter(getFooter(root), state);
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
    const label = local.hasTweaked ? 'Re-relabel AI…' : 'Relabel with AI';
    const title = isPast
      ? 'Use Edit above to revise a past skeleton.'
      : (local.hasTweaked
        ? 'Re-run the LLM relabel + request placement. Your inline edits are replaced.'
        : 'Run the LLM relabel + request placement now.');
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
         <strong>${escHtml(local.hasTweaked ? 'Re-relabel AI…' : 'Relabel with AI')}</strong>
         to try filling the rest.</div>`
      : '';
    slot.innerHTML = `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">Default → tweaked skeleton ${pill}</h3>
        <button type="button" class="wiz-btn-secondary wiz-refresh-btn"
                data-role="skel-refresh"
                title="${escAttr(title)}" ${isPast || aiBusy() ? 'disabled' : ''}>${escHtml(label)}</button>
      </div>
      <p class="wiz-skel-blurb">The deterministic default skeleton, each slot rewritten by the LLM to fit the set. Changed parts are highlighted; edit any tweaked line, then continue.</p>
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
    if (btn) btn.onclick = () => onRefresh();
  }

  // ----------------------------------------------------------------------
  // Slot grid — per-slot default→tweaked diff + editable tweaked line
  // ----------------------------------------------------------------------

  function paintGrid(root, state) {
    const slot = root.querySelector('[data-role="skel-grid"]');
    if (!slot) return;
    if (!local.slots.length) {
      const generating = local.stageStatus === 'running' || local.locked;
      slot.innerHTML = `
        <div class="wiz-skel-empty">
          ${generating ? 'Generating the skeleton…' : 'No skeleton yet — advance from Archetypes.'}
        </div>`;
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
  // Live relabel streaming (SSE bridged from wizard.js via W.onSkeletonStream)
  // ----------------------------------------------------------------------
  //
  // Three events, fired for BOTH the engine auto-run and the manual Refresh
  // (and replayed from the bus buffer when a tab attaches mid-run):
  //   skeleton_relabel_reset — a fresh attempt is (re)starting
  //   skeleton_slot          — one slot's relabel/placement landed
  //   skeleton_relabel_done  — the relabel finished (success or kept-partial)

  function onSkeletonStream(name, data) {
    if (name === 'skeleton_relabel_reset') return onRelabelReset();
    if (name === 'skeleton_slot') return onRelabelSlot(data || {});
    if (name === 'skeleton_relabel_done') return onRelabelDone(data || {});
  }

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
  // Refresh — re-run the relabel
  // ----------------------------------------------------------------------

  async function onRefresh() {
    if (local.locked) return;
    if (local.hasTweaked
        && !confirm('Re-run the LLM relabel? Your inline edits will be replaced.')) {
      return;
    }
    setLocked(true);
    if (W.showBusy) W.showBusy(local.hasTweaked ? 'Re-relabeling skeleton…' : 'Relabeling skeleton…');
    const root = bodyRoot();
    paintGrid(root, W.getState());
    try {
      const resp = await W.postJSON('/api/wizard/skeleton/refresh', {});
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        // The live stream (if any started) never reached done — settle it here
        // so the grid doesn't stay dimmed, then surface the error.
        local.streaming = false;
        paintSummary(root, W.getState());
        paintGrid(root, W.getState());
        return reportError(resp, data, 'Relabel failed');
      }
      // Authoritative final state. The skeleton_relabel_done SSE event also
      // settled the live view; applying the response slots reconciles any drift.
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
    } catch (err) {
      local.streaming = false;
      W.toast('Network error: ' + err.message, 'error');
    } finally {
      if (W.clearBusy) W.clearBusy();
      setLocked(false);
    }
  }

  function reportError(resp, data, fallback) {
    if (resp.status === 409 && data.running_action) {
      W.toast(`${data.running_action} is in progress — try again when it finishes.`, 'error');
    } else {
      W.toast(data.error || `${fallback} (${resp.status})`, 'error');
    }
  }

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
    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
    }
    const btn = footer.querySelector('[data-role="skel-save-advance"]');
    if (btn) btn.onclick = onSaveAndAdvance;
  }

  async function onSaveAndAdvance() {
    if (local.locked) return;
    if (!local.slots.length || !local.slots.every(s => (s.tweaked_text || '').trim())) {
      W.toast('Every slot needs a tweaked descriptor before continuing.', 'error');
      return;
    }
    setLocked(true);
    const root = bodyRoot();
    const footer = getFooter(root);
    const btn = footer && footer.querySelector('[data-role="skel-save-advance"]');
    const original = btn ? btn.textContent : '';
    if (btn) btn.textContent = 'Saving…';
    try {
      const payload = local.slots.map(s => ({ slot_id: s.slot_id, tweaked_text: s.tweaked_text }));
      const saveResp = await W.postJSON('/api/wizard/skeleton/save', { slots: payload });
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
      window.location.assign(advData.navigate_to || saveData.navigate_to || '/pipeline');
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
    const root = bodyRoot();
    if (!root) return;
    const locked = aiBusy();
    root.classList.toggle('wiz-skel-locked', locked);
    root.querySelectorAll('.wiz-skel-tweak, [data-role="skel-refresh"]').forEach(el => {
      el.disabled = locked;
    });
    const footerBtn = root.querySelector('[data-role="skel-save-advance"]');
    if (footerBtn) footerBtn.disabled = locked;
  }

  // ----------------------------------------------------------------------
  // Helpers
  // ----------------------------------------------------------------------

  function bodyRoot() {
    return document.querySelector(`.wiz-tab-body[data-tab-id="${STAGE_ID}"]`);
  }

  function getFooter(root) {
    return root && root.querySelector('[data-role="footer"]');
  }

  function isPastTab(state) {
    return !!state && state.latestTabId !== STAGE_ID;
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

  // Escape a slot id for use inside a `[data-slot-id="…"]` CSS selector. Slot
  // ids are alphanumeric+hyphen today, but CSS.escape keeps the live-update
  // selector safe if that ever changes.
  function cssEsc(text) {
    const s = String(text == null ? '' : text);
    return (window.CSS && CSS.escape) ? CSS.escape(s) : s.replace(/["\\]/g, '\\$&');
  }
})();
