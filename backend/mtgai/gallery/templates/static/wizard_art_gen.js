/**
 * Wizard Art Generation tab — merged generate + best-of-N judge + human review.
 *
 * One cohesive surface (the old art_select + human_art_review folded in):
 *   - art streams in live per card as it is generated + judged (art_gen_card),
 *   - each card shows its N versions with the LLM judge's auto-pick highlighted
 *     and the judge's reasoning,
 *   - the user can (re)pick the best version (override the auto-pick), reroll
 *     (regenerate a card's art), and upload their own image.
 *
 * Built from the shared helpers (plans/wizard-tab-conventions.md §17), not by
 * forking a stage tab: W.registerStageRenderer / fetchStageState / paintFooter /
 * advanceStage / runAiAction / setTabLocked / registerStream / rarityPill.
 *
 * Backend: /api/wizard/art_gen/{state,refresh,reroll,repick,upload} +
 * /api/wizard/art_gen/image/<filename>. SSE: art_gen_reset / art_gen_card via
 * W.onArtGenStream.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'art_gen';
  const escHtml = W.escHtml;
  const escAttr = W.escAttr;

  // ── Scoped styles ──────────────────────────────────────────────────────────

  if (!document.getElementById('wiz-art_gen-styles')) {
    const style = document.createElement('style');
    style.id = 'wiz-art_gen-styles';
    style.textContent = `
      .wiz-ag-blurb { color: #888; font-size: 0.82rem; margin: 0.25rem 0 0.75rem 0; }
      .wiz-ag-context {
        display: grid; grid-template-columns: max-content 1fr; gap: 0.3rem 1rem;
        font-size: 0.82rem; margin: 0 0 1rem 0;
      }
      .wiz-ag-context dt { color: #888; }
      .wiz-ag-context dd { margin: 0; color: #ddd; }

      .wiz-ag-grid {
        display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
        gap: 1rem; margin-top: 0.75rem;
      }
      .wiz-ag-card {
        background: #0f1729; border: 1px solid #1f2540; border-radius: 8px;
        padding: 0.6rem; display: flex; flex-direction: column; gap: 0.4rem;
      }
      .wiz-ag-card.is-streaming { border-color: #4a9eff66; }
      .wiz-ag-card-head { display: flex; justify-content: space-between; align-items: baseline; gap: 0.4rem; }
      .wiz-ag-card-name { font-size: 0.82rem; font-weight: 600; color: #e8d5b5;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .wiz-ag-card-cn { font-size: 0.68rem; color: #666; }

      .wiz-ag-versions { display: flex; gap: 0.35rem; flex-wrap: wrap; }
      .wiz-ag-version {
        position: relative; width: 84px; cursor: pointer; border-radius: 5px;
        overflow: hidden; border: 2px solid transparent; background: #12192e;
      }
      .wiz-ag-version.picked { border-color: #4ade80; }
      .wiz-ag-version .wiz-ag-thumb {
        width: 100%; aspect-ratio: 4 / 3; object-fit: cover; display: block;
        background: #12192e;
      }
      .wiz-ag-version .wiz-ag-vlabel {
        font-size: 0.62rem; text-align: center; padding: 1px 0; color: #aaa;
        background: #0b1120;
      }
      .wiz-ag-version.picked .wiz-ag-vlabel { color: #4ade80; font-weight: 600; }
      .wiz-ag-pickbadge {
        position: absolute; top: 2px; left: 2px; font-size: 0.6rem; line-height: 1;
        padding: 1px 3px; border-radius: 3px; background: #1a3a2a; color: #4ade80;
      }
      .wiz-ag-zoom {
        position: absolute; top: 2px; right: 2px; width: 1.25rem; height: 1.25rem;
        padding: 0; border-radius: 4px; border: 1px solid #2a3550; background: #0b1120cc;
        color: #cdd; font-size: 0.72rem; line-height: 1; cursor: zoom-in;
        display: flex; align-items: center; justify-content: center;
        opacity: 0; transition: opacity 0.12s;
      }
      .wiz-ag-version:hover .wiz-ag-zoom, .wiz-ag-zoom:focus { opacity: 1; }
      .wiz-ag-zoom:hover { background: #16213e; border-color: #4a9eff; color: #fff; }

      .wiz-ag-reason {
        font-size: 0.72rem; color: #9aa; line-height: 1.35; margin: 0;
        border-left: 2px solid #2a3550; padding-left: 0.5rem;
      }
      .wiz-ag-reason .wiz-ag-src { color: #4a9eff; }
      .wiz-ag-reason .wiz-ag-src.user { color: #c084fc; }

      .wiz-ag-actions { display: flex; gap: 0.35rem; margin-top: 0.2rem; }
      .wiz-ag-btn-sm {
        font-size: 0.7rem; padding: 0.22rem 0.5rem; border-radius: 4px;
        background: #1a2138; border: 1px solid #2a3550; color: #cdd; cursor: pointer;
      }
      .wiz-ag-btn-sm:hover { background: #232c4a; }
      .wiz-ag-empty-thumb {
        width: 84px; aspect-ratio: 4 / 3; display: flex; align-items: center;
        justify-content: center; font-size: 0.62rem; color: #555; background: #12192e;
        border-radius: 5px;
      }
      .wiz-ag-locked .wiz-ag-grid { opacity: 0.7; pointer-events: none; }
    `;
    document.head.appendChild(style);
  }

  // ── Module-local state ───────────────────────────────────────────────────────

  const local = {
    initialized: false,
    cards: [],            // [{collector_number, name, versions:[{filename,url}], pick, pick_source, reasoning, ...}]
    byCn: {},             // collector_number -> card (for fast stream patching)
    streaming: {},        // collector_number -> phase ("generated"|"judged") for live highlight
    hasContent: false,
    versionsPerCard: 3,
    judgeModel: '',
    provider: '',
    stageStatus: 'pending',
    canAdvance: false,    // COMPLETED tip, pipeline PAUSED, a pending successor waits
    locked: false,
    bootstrapping: false,
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ── SSE stream (art_gen_reset / art_gen_card) ───────────────────────────────

  W.onArtGenStream = function (name, data) {
    if (name === 'art_gen_reset') {
      local.streaming = {};
      const root = bodyRoot();
      if (root) paintGrid(root);
      return;
    }
    if (name === 'art_gen_card') {
      const cn = data && data.collector_number;
      if (!cn) return;
      local.streaming[cn] = data.phase || 'generated';
      const root = bodyRoot();
      if (!root) return;
      // A 'generated' event now carries the freshly written version tiles
      // ({filename, url}) — patch them onto the card so art shows live, not only
      // on stage-finish / F5. A 'judged' event's pick lands from disk on the
      // final re-bootstrap; mid-stream we just mark the tile active.
      const versions = Array.isArray(data.versions) ? data.versions : null;
      if (versions && versions.length) {
        applyStreamedVersions(root, cn, versions);
      }
      markStreaming(root, cn);
    }
  };

  // Patch a card's generated versions onto its tile live (or flip the whole grid
  // out of the "Generating…" placeholder on the first card to land).
  function applyStreamedVersions(root, cn, versions) {
    let card = local.byCn[cn];
    if (!card) {
      // The tab opened before bootstrap captured this card; show a minimal tile
      // (the cn doubles as the name until the next bootstrap fills metadata).
      card = { collector_number: cn, name: cn, versions: [] };
      local.byCn[cn] = card;
      local.cards.push(card);
    }
    card.versions = versions;
    const wasEmpty = !local.hasContent;
    local.hasContent = true;
    paintSummary(root);
    if (wasEmpty) {
      // First art to arrive — replace the placeholder with the real grid, then
      // re-apply the run lock + any active streaming highlights it wiped.
      paintGrid(root);
      setLocked(root, local.locked);
      Object.keys(local.streaming).forEach((c) => markStreaming(root, c));
      return;
    }
    patchCardVersions(root, cn, card);
  }

  function patchCardVersions(root, cn, card) {
    const sel = W.cssEsc ? W.cssEsc(cn) : cn;
    const cardEl = root.querySelector(`.wiz-ag-card[data-cn="${sel}"]`);
    const versionsEl = cardEl && cardEl.querySelector('.wiz-ag-versions');
    if (!versionsEl) {
      // Card not in the DOM yet (e.g. appended mid-stream) — full repaint.
      paintGrid(root);
      setLocked(root, local.locked);
      return;
    }
    const versions = Array.isArray(card.versions) ? card.versions : [];
    versionsEl.innerHTML = versions.length
      ? versions.map((v, i) => versionHtml(card, v, i + 1)).join('')
      : '<div class="wiz-ag-empty-thumb">(no art)</div>';
    versionsEl.querySelectorAll('.wiz-ag-version').forEach((vEl) => bindVersionTile(vEl, cn));
  }

  // Bind a version tile: click = pick it (the tab's interaction model), the
  // hover ⤢ button = open the full-scale lightbox (stopPropagation so it never
  // also picks). The full-size URL is read off the tile's own <img> so it tracks
  // a reroll/upload that swapped the src.
  function bindVersionTile(vEl, cn) {
    const pick = vEl.getAttribute('data-pick');
    vEl.onclick = () => onRepick(cn, pick);
    const zoomBtn = vEl.querySelector('[data-act="zoom"]');
    if (zoomBtn) {
      zoomBtn.onclick = (e) => {
        e.stopPropagation();
        const img = vEl.querySelector('.wiz-ag-thumb');
        const url = img && img.getAttribute('src');
        if (!url || !window.MTGAILightbox) return;
        const card = local.byCn[cn];
        const nm = (card && card.name) || cn;
        window.MTGAILightbox.open(url, { alt: `${nm} ${pick}`, caption: `${nm} · ${pick}` });
      };
    }
  }

  // ── Top-level render ────────────────────────────────────────────────────────

  function render({ root, state, stage, content, footer }) {
    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      bootstrap(root, state).catch((err) =>
        W.toast('Failed to load art generation state: ' + err.message, 'error'),
      );
      paintFooter(footer, state);
      return;
    }

    const prevStatus = local.stageStatus;
    if (stage) local.stageStatus = stage.status;

    // When the stage finishes (running -> not running), re-fetch so the picks +
    // version files land from disk.
    const justFinished =
      stage &&
      prevStatus !== local.stageStatus &&
      local.stageStatus !== 'pending' &&
      local.stageStatus !== 'running' &&
      !local.bootstrapping;
    if (justFinished) {
      local.bootstrapping = true;
      bootstrap(root, state)
        .catch((err) => W.toast('Failed to refresh: ' + err.message, 'error'))
        .finally(() => {
          local.bootstrapping = false;
        });
      return;
    }

    paintFooter(footer, state);
    setLocked(root, local.locked);
  }

  function mountShellHtml() {
    return `
      <div data-role="ag-summary"><div class="wiz-stage-empty">Loading art generation…</div></div>
      <div class="wiz-ag-grid" data-role="ag-grid"></div>
    `;
  }

  // ── Bootstrap ────────────────────────────────────────────────────────────────

  async function bootstrap(root, state) {
    const data = await W.fetchStageState(STAGE_ID);
    if (data) {
      // A bootstrap loads the durable on-disk truth — drop any mid-stream
      // highlight state so a finished/judged card can't keep a phantom active
      // border once the grid is repainted from disk.
      local.streaming = {};
      local.cards = Array.isArray(data.cards) ? data.cards : [];
      local.byCn = {};
      local.cards.forEach((c) => { local.byCn[c.collector_number] = c; });
      local.hasContent = !!data.has_content;
      local.versionsPerCard = data.versions_per_card || local.versionsPerCard;
      local.judgeModel = data.judge_model || '';
      local.provider = data.provider || '';
      local.stageStatus = data.stage_status || local.stageStatus;
      local.canAdvance = !!data.can_advance;
    }
    paintSummary(root, state);
    paintGrid(root);
    paintFooter(getFooter(root), state);
    setLocked(root, local.locked);
  }

  // ── Summary ──────────────────────────────────────────────────────────────────

  function paintSummary(root) {
    const slot = root.querySelector('[data-role="ag-summary"]');
    if (!slot) return;
    const withArt = local.cards.filter((c) => c.versions && c.versions.length).length;
    slot.innerHTML = `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">Art generation &amp; review</h3>
        <button type="button" class="wiz-refresh-btn" data-role="ag-refresh-all">
          ${local.hasContent ? 'Regenerate all…' : 'Generate art'}
        </button>
      </div>
      <p class="wiz-ag-blurb">
        Generates best-of-N art per card, the judge auto-picks the best, and you re-pick,
        reroll, or upload your own here.
      </p>
      <dl class="wiz-ag-context">
        <dt>Cards with art</dt><dd>${withArt} / ${local.cards.length || '—'}</dd>
        <dt>Versions per card</dt><dd>${local.versionsPerCard}</dd>
        <dt>Judge model</dt><dd>${escHtml(local.judgeModel || '—')}</dd>
        <dt>Provider</dt><dd>${escHtml(local.provider || '—')}</dd>
      </dl>
    `;
    const refreshBtn = slot.querySelector('[data-role="ag-refresh-all"]');
    if (refreshBtn) refreshBtn.onclick = onRefreshAll;
  }

  // ── Grid ─────────────────────────────────────────────────────────────────────

  function paintGrid(root) {
    const slot = root.querySelector('[data-role="ag-grid"]');
    if (!slot) return;

    const generating = local.stageStatus === 'running' || local.locked;
    if (!local.hasContent || local.cards.length === 0) {
      slot.innerHTML = `
        <div class="wiz-stage-empty">
          ${generating
            ? 'Generating art… tiles appear as each card finishes.'
            : 'No art generated yet. Click Generate art above (or run the stage).'}
        </div>`;
      return;
    }
    slot.innerHTML = local.cards.map(cardHtml).join('');
    bindCardActions(slot);
  }

  function cardHtml(card) {
    const versions = Array.isArray(card.versions) ? card.versions : [];
    const versionsHtml = versions.length
      ? versions.map((v, i) => versionHtml(card, v, i + 1)).join('')
      : '<div class="wiz-ag-empty-thumb">(no art)</div>';

    const src = card.pick_source === 'user' ? 'You picked' : card.pick_source ? 'AI picked' : '';
    const reasonHtml = card.reasoning
      ? `<p class="wiz-ag-reason">${src ? `<span class="wiz-ag-src ${card.pick_source === 'user' ? 'user' : ''}">${escHtml(src)}:</span> ` : ''}${escHtml(card.reasoning)}</p>`
      : '';

    return `
      <div class="wiz-ag-card" data-cn="${escAttr(card.collector_number)}">
        <div class="wiz-ag-card-head">
          <span class="wiz-ag-card-name" title="${escAttr(card.name)}">${escHtml(card.name)}</span>
          <span class="wiz-ag-card-cn">${escHtml(card.collector_number)}</span>
        </div>
        <div class="wiz-ag-versions">${versionsHtml}</div>
        ${reasonHtml}
        <div class="wiz-ag-actions">
          <button type="button" class="wiz-ag-btn-sm" data-act="reroll">Reroll</button>
          <button type="button" class="wiz-ag-btn-sm" data-act="upload">Upload…</button>
        </div>
        <input type="file" accept="image/*" data-role="ag-file" style="display:none">
      </div>`;
  }

  function versionHtml(card, v, num) {
    const label = 'v' + num;
    const isPicked = card.pick === label;
    return `
      <div class="wiz-ag-version ${isPicked ? 'picked' : ''}" data-pick="${escAttr(label)}"
           title="Click to pick ${label}">
        ${isPicked ? '<span class="wiz-ag-pickbadge">PICK</span>' : ''}
        <button type="button" class="wiz-ag-zoom" data-act="zoom"
                title="View full size" aria-label="View ${escAttr(label)} full size">⤢</button>
        <img class="wiz-ag-thumb" src="${escAttr(v.url)}" alt="${escAttr(label)}"
             onerror="this.style.visibility='hidden'">
        <div class="wiz-ag-vlabel">${label}</div>
      </div>`;
  }

  function bindCardActions(slot) {
    slot.querySelectorAll('.wiz-ag-card').forEach((cardEl) => {
      const cn = cardEl.getAttribute('data-cn');
      cardEl.querySelectorAll('.wiz-ag-version').forEach((vEl) => bindVersionTile(vEl, cn));
      const rerollBtn = cardEl.querySelector('[data-act="reroll"]');
      if (rerollBtn) rerollBtn.onclick = () => onReroll(cn);
      const uploadBtn = cardEl.querySelector('[data-act="upload"]');
      const fileInput = cardEl.querySelector('[data-role="ag-file"]');
      if (uploadBtn && fileInput) {
        uploadBtn.onclick = () => fileInput.click();
        fileInput.onchange = () => {
          if (fileInput.files && fileInput.files[0]) onUpload(cn, fileInput.files[0]);
        };
      }
    });
  }

  function markStreaming(root, cn) {
    const el = root.querySelector(`.wiz-ag-card[data-cn="${W.cssEsc ? W.cssEsc(cn) : cn}"]`);
    if (el) el.classList.add('is-streaming');
  }

  // ── Actions ──────────────────────────────────────────────────────────────────

  function onRefreshAll() {
    W.runAiAction({
      isLocked: () => local.locked,
      setLocked: (l) => setLocked(bodyRoot(), l),
      confirm: () => (local.hasContent ? 'Regenerate art for the whole set? Existing versions are kept; new ones are added.' : ''),
      busyLabel: 'Generating art…',
      url: '/api/wizard/art_gen/refresh',
      body: () => ({}),
      fallback: 'Art generation failed',
      onResult: (data) => applyState(data),
    });
  }

  function onReroll(cn) {
    W.runAiAction({
      isLocked: () => local.locked,
      setLocked: (l) => setLocked(bodyRoot(), l),
      confirm: () => `Reroll art for ${cn}? Its current versions are replaced.`,
      busyLabel: 'Rerolling art…',
      url: '/api/wizard/art_gen/reroll',
      body: () => ({ collector_number: cn }),
      fallback: 'Reroll failed',
      onResult: (data) => applyState(data),
    });
  }

  async function onRepick(cn, pick) {
    // Re-pick is a pure (no-AI) override — post directly, no AI lock dance.
    try {
      const resp = await fetch('/api/wizard/art_gen/repick', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ collector_number: cn, pick }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        W.toast(data.error || 'Re-pick failed', 'error');
        return;
      }
      applyState(data);
    } catch (e) {
      W.toast('Re-pick failed: ' + e.message, 'error');
    }
  }

  async function onUpload(cn, file) {
    try {
      const form = new FormData();
      form.append('collector_number', cn);
      form.append('file', file);
      const resp = await fetch('/api/wizard/art_gen/upload', { method: 'POST', body: form });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        W.toast(data.error || 'Upload failed', 'error');
        return;
      }
      W.toast('Uploaded art for ' + cn, 'success');
      applyState(data);
    } catch (e) {
      W.toast('Upload failed: ' + e.message, 'error');
    }
  }

  function applyState(data) {
    if (!data) return;
    if (Array.isArray(data.cards)) {
      local.cards = data.cards;
      local.byCn = {};
      local.cards.forEach((c) => { local.byCn[c.collector_number] = c; });
      local.hasContent = !!data.has_content;
    }
    if (data.stage_status) local.stageStatus = data.stage_status;
    if ('can_advance' in data) local.canAdvance = !!data.can_advance;
    const root = bodyRoot();
    if (root) {
      paintSummary(root);
      paintGrid(root);
      paintFooter(getFooter(root), null);
      setLocked(root, local.locked);
    }
  }

  // ── Footer (art_gen is review_eligible — pauses for human review) ────────────

  function paintFooter(footer, state) {
    if (!footer) return;
    const isLatest = !state || state.latestTabId === STAGE_ID;
    const status = local.stageStatus;
    const next = W.nextStageEntryAfter(STAGE_ID);
    const nextName = next ? next.name : 'the next stage';

    // 'completed' + can-advance is the saved/reopened dead-end: art finished but
    // the pipeline persisted PAUSED with rendering still pending and no
    // PAUSED_FOR_REVIEW pause. The server-fed local.canAdvance survives an
    // SSE repaint that passes state=null (the client helper needs live state);
    // gate it on the live status==='completed' so a stale-true flag can't show
    // the button mid-run. The client helper is the state-fresh second path.
    const canAdvanceTip =
      (status === 'completed' && local.canAdvance) || W.completedTipCanAdvance(state, STAGE_ID);
    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Art review completed — read-only on a past tab.</span>`;
    } else if (status === 'paused_for_review' || canAdvanceTip) {
      // Surface the same Next-step button so the user isn't stuck — advance()
      // resumes the engine into the pending stage.
      html = `<button type="button" class="wiz-btn-primary" data-role="ag-advance">Next step: ${escHtml(nextName)}</button>`;
    } else if (status === 'running') {
      html = `<span class="wiz-footer-note">Art generation is in progress…</span>`;
    } else if (status === 'failed') {
      html = `<span class="wiz-footer-note">Stage failed — see the error above; regenerate or fix a card to recover.</span>`;
    } else {
      html = `<span class="wiz-footer-note">Continue appears once art is ready for your sign-off.</span>`;
    }
    W.paintFooter(footer, html, { role: 'ag-advance', onClick: onAdvance });
  }

  function onAdvance() {
    return W.advanceStage({ stageId: STAGE_ID, btnRole: 'ag-advance', navigate: false });
  }

  // ── Form lock (§3) ──────────────────────────────────────────────────────────

  function aiBusy() {
    return local.locked || local.stageStatus === 'running';
  }

  function setLocked(root, locked) {
    local.locked = !!locked;
    if (!root) return;
    W.setTabLocked(root, aiBusy(), {
      lockClass: 'wiz-ag-locked',
      selectors: [
        '[data-role="ag-refresh-all"]',
        '.wiz-ag-btn-sm',
        '.wiz-ag-version',
      ],
      footerSelector: '[data-role="ag-advance"]',
    });
  }

  // ── Helpers ─────────────────────────────────────────────────────────────────

  function bodyRoot() {
    return document.querySelector(`.wiz-tab-body[data-tab-id="${STAGE_ID}"]`);
  }

  function getFooter(root) {
    return root && root.querySelector('[data-role="footer"]');
  }
})();
