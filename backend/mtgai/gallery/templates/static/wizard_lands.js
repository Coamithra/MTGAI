/**
 * Wizard Lands tab — a responsive grid of land card tiles on the standard
 * stage shell.
 *
 * Stage ID: ``lands``  (review_eligible: False — never pauses for review)
 *
 * Data source: land card JSONs in ``<asset>/cards/`` — basics + 1 nonbasic
 * produced by ``mtgai/generation/land_generator.py`` and written through
 * the standard card-save path.  Typical set: Plains, Island, Swamp,
 * Mountain, Forest (with flavour text) + 1 setting-specific nonbasic.
 *
 * Conventions honoured:
 *   §1  Footer is a wiz-footer-note only — lands never pause for review.
 *   §3  Form lock during AI gen.
 *   §6  Past-tab edit cascade via wizard_stage.js / W.editFlow.
 *   §8  Status pill flows from stage state.
 *   §9  "Stop after this step" — handled by wizard_stage.js.
 *   §13 Section-level Refresh-AI button, always rendered on the latest tab.
 *
 * The grid is read-only for this precreation pass.  The Refresh button is
 * a placeholder that toasts a TODO until the backend endpoint is added.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'lands';

  // ── Scoped styles (injected once) ────────────────────────────────────────
  (function injectStyles() {
    if (document.getElementById('wiz-lands-styles')) return;
    const s = document.createElement('style');
    s.id = 'wiz-lands-styles';
    s.textContent = `
      /* Summary / meta */
      .wiz-lands-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem 1.5rem;
        margin-bottom: 1rem;
        font-size: 0.82rem;
        color: #888;
      }
      .wiz-lands-meta strong { color: #ddd; }

      /* Grid — same column sizing as reprints for visual consistency */
      .wiz-lands-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
        gap: 0.75rem;
        margin-top: 0.75rem;
      }

      /* Tile */
      .wiz-lands-tile {
        background: #0f1729;
        border: 1px solid #1f2540;
        border-radius: 8px;
        padding: 0.75rem;
        display: flex;
        flex-direction: column;
        gap: 0.35rem;
        transition: border-color 0.15s;
      }
      .wiz-lands-tile:hover { border-color: #00d4aa44; }

      /* Basic land tiles get a subtle green tint; nonbasics are blue */
      .wiz-lands-tile[data-basic="true"] { border-color: #00d4aa22; }
      .wiz-lands-tile[data-basic="false"] { border-color: #4a9eff22; }

      .wiz-lands-tile-header {
        display: flex;
        align-items: baseline;
        gap: 0.5rem;
        flex-wrap: wrap;
      }
      .wiz-lands-name {
        font-weight: 600;
        font-size: 0.9rem;
        color: #e0e0e0;
        flex: 1 1 auto;
      }
      .wiz-lands-rarity {
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        padding: 1px 5px;
        border-radius: 3px;
        flex-shrink: 0;
      }
      .wiz-lands-rarity-c { background: #2a2a2a; color: #aaa; }
      .wiz-lands-rarity-u { background: #c0d0e022; color: #b0c8d8; }
      .wiz-lands-rarity-r { background: #ffd70022; color: #ffd700; }

      .wiz-lands-type {
        font-size: 0.73rem;
        color: #888;
        font-style: italic;
      }
      .wiz-lands-oracle {
        font-size: 0.76rem;
        color: #ccc;
        line-height: 1.45;
        white-space: pre-line;
      }
      .wiz-lands-flavor {
        font-size: 0.72rem;
        color: #777;
        font-style: italic;
        line-height: 1.4;
        border-top: 1px solid #1f2540;
        padding-top: 0.3rem;
        margin-top: 0.1rem;
      }

      /* Locked */
      .wiz-lands-locked .wiz-lands-tile {
        opacity: 0.6;
        pointer-events: none;
      }
    `;
    document.head.appendChild(s);
  })();

  // ── Module state ──────────────────────────────────────────────────────────
  const local = {
    initialized: false,
    lands: [],          // simplified land objects: {name, type_line, rarity, oracle_text, flavor_text}
    hasContent: false,
    stageStatus: 'pending',
    locked: false,
    bootstrapping: false,
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ── Top-level render ──────────────────────────────────────────────────────

  function render({ root, state, stage, content, footer }) {
    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      bootstrap(root, state).catch(err => {
        W.toast('Failed to load lands state: ' + err.message, 'error');
      });
      paintFooter(footer, state);
      return;
    }

    // Re-render path: reactive footer only.
    const prevStatus = local.stageStatus;
    if (stage) local.stageStatus = stage.status;

    const justFinished =
      stage
      && prevStatus !== local.stageStatus
      && local.stageStatus !== 'pending'
      && local.stageStatus !== 'running'
      && !local.hasContent
      && !local.bootstrapping;

    if (justFinished) {
      local.bootstrapping = true;
      bootstrap(root, state)
        .catch(err => W.toast('Failed to refresh lands state: ' + err.message, 'error'))
        .finally(() => { local.bootstrapping = false; });
      return;
    }

    paintFooter(footer, state);
    setLocked(local.locked);
  }

  function mountShellHtml() {
    return `
      <div data-role="lands-summary">
        <div style="color:#666;font-style:italic;padding:1rem 0">Loading land cards…</div>
      </div>
      <div data-role="lands-grid"></div>
    `;
  }

  // ── Bootstrap from server ─────────────────────────────────────────────────

  async function bootstrap(root, state) {
    // TODO: implement GET /api/wizard/lands/state that returns
    //   { lands: [{name, type_line, rarity, oracle_text, flavor_text}],
    //     has_content: bool, stage_status: str }
    //   reading the land card JSONs from <asset>/cards/ (filter type_line
    //   contains "Land").
    let data = null;
    try {
      const resp = await fetch('/api/wizard/lands/state');
      if (resp.ok) {
        data = await resp.json();
      } else if (resp.status === 404) {
        data = null; // endpoint not yet implemented — graceful empty
      } else {
        const j = await resp.json().catch(() => ({}));
        throw new Error(j.error || `HTTP ${resp.status}`);
      }
    } catch (err) {
      if (err.message && err.message.startsWith('HTTP ')) throw err;
      data = null;
    }

    if (data) {
      local.lands = Array.isArray(data.lands) ? data.lands : [];
      local.hasContent = !!data.has_content || local.lands.length > 0;
      if (data.stage_status) local.stageStatus = data.stage_status;
    }

    paintSummary(root, state);
    paintGrid(root, state);
    paintFooter(getFooter(root), state);
  }

  // ── Summary / section header (§13) ───────────────────────────────────────

  function paintSummary(root, state) {
    const slot = root.querySelector('[data-role="lands-summary"]');
    if (!slot) return;
    const isPast = isPastTab(state);
    const refreshLabel = local.hasContent ? 'Refresh AI…' : 'Generate';
    const refreshTitle = local.hasContent
      ? 'Regenerate all land cards (basics + nonbasic).'
      : 'Generate land cards now.';

    const basics = local.lands.filter(l => isBasicType(l.type_line)).length;
    const nonbasics = local.lands.length - basics;
    const metaParts = [];
    if (local.hasContent) {
      metaParts.push(`Basics: <strong>${escHtml(String(basics))}</strong>`);
      metaParts.push(`Nonbasics: <strong>${escHtml(String(nonbasics))}</strong>`);
      metaParts.push(`Total: <strong>${escHtml(String(local.lands.length))}</strong>`);
    }

    slot.innerHTML = `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">Land cards</h3>
        <button type="button" class="wiz-btn-secondary wiz-refresh-btn"
                data-role="lands-refresh-all"
                title="${escAttr(isPast ? 'Use Edit above to revise past land cards.' : refreshTitle)}"
                ${isPast ? 'disabled' : ''}>${escHtml(refreshLabel)}</button>
      </div>
      <p style="font-size:0.8rem;color:#888;margin:0.3rem 0 0.6rem">
        Five basics with setting-flavoured flavour text plus one nonbasic
        land design that fits the set's mana requirements.
      </p>
      ${metaParts.length ? `<div class="wiz-lands-meta">${metaParts.join(' &nbsp;·&nbsp; ')}</div>` : ''}
    `;

    const btn = slot.querySelector('[data-role="lands-refresh-all"]');
    if (btn) btn.onclick = () => onRefreshAll();
  }

  // ── Grid ──────────────────────────────────────────────────────────────────

  function paintGrid(root, state) {
    const slot = root.querySelector('[data-role="lands-grid"]');
    if (!slot) return;

    if (!local.hasContent) {
      const generating = local.stageStatus === 'running' || local.locked;
      slot.innerHTML = `
        <div class="wiz-stage-empty">
          ${generating
            ? 'Generating land cards…'
            : 'No land cards yet — this stage runs automatically after Reprints.'}
        </div>
      `;
      return;
    }

    // Sort: basics first (alphabetical), then nonbasics.
    const sorted = [...local.lands].sort((a, b) => {
      const aBasic = isBasicType(a.type_line);
      const bBasic = isBasicType(b.type_line);
      if (aBasic !== bBasic) return aBasic ? -1 : 1;
      return (a.name || '').localeCompare(b.name || '');
    });

    slot.innerHTML = `<div class="wiz-lands-grid">${sorted.map(l => landTileHtml(l)).join('')}</div>`;
  }

  function landTileHtml(land) {
    const isBasic = isBasicType(land.type_line);
    const rarityKey = (land.rarity || 'c').toLowerCase().charAt(0);
    const rarityClass = `wiz-lands-rarity-${escAttr(rarityKey)}`;
    const rarityLabel = escHtml(land.rarity || '?');

    const oracle = land.oracle_text || '';
    const flavor = land.flavor_text || '';

    return `
      <article class="wiz-lands-tile" data-basic="${escAttr(String(isBasic))}">
        <div class="wiz-lands-tile-header">
          <span class="wiz-lands-name">${escHtml(land.name || '(unnamed)')}</span>
          <span class="wiz-lands-rarity ${rarityClass}">${rarityLabel}</span>
        </div>
        ${land.type_line ? `<div class="wiz-lands-type">${escHtml(land.type_line)}</div>` : ''}
        ${oracle ? `<div class="wiz-lands-oracle">${escHtml(oracle)}</div>` : ''}
        ${flavor ? `<div class="wiz-lands-flavor">${escHtml(flavor)}</div>` : ''}
      </article>
    `;
  }

  function isBasicType(typeLine) {
    return /\bBasic\b/i.test(typeLine || '');
  }

  // ── Refresh placeholder ───────────────────────────────────────────────────

  async function onRefreshAll() {
    if (local.locked) return;
    if (local.hasContent) {
      if (!confirm('Regenerate all land cards? Existing land JSONs will be replaced.')) return;
    }
    // TODO: POST /api/wizard/lands/refresh triggers run_lands re-execution.
    W.toast('Regenerating lands is not yet wired to the backend. Follow-up needed.', 'warn');
  }

  // ── Footer: note only — lands never pause for review (§1) ────────────────

  function paintFooter(footer, state) {
    if (!footer) return;
    const isLatest = !state || state.latestTabId === STAGE_ID;
    const isCompleted = local.stageStatus === 'completed';
    const next = W.nextStageEntryAfter(STAGE_ID);
    const nextName = next ? next.name : 'the next stage';

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Past tab — use Edit above to revise land cards.</span>`;
    } else if (isCompleted) {
      html = `<span class="wiz-footer-complete">✓ Lands generated — engine will continue to ${escHtml(nextName)}.</span>`;
    } else if (local.stageStatus === 'running') {
      html = `<span class="wiz-footer-note">Generating land cards…</span>`;
    } else {
      html = `<span class="wiz-footer-note">Runs automatically; no review step.</span>`;
    }

    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
    }
  }

  // ── Form lock (§3) ────────────────────────────────────────────────────────

  function setLocked(locked) {
    local.locked = !!locked;
    const root = bodyRoot();
    if (!root) return;
    root.classList.toggle('wiz-lands-locked', !!locked);
    root.querySelectorAll('[data-role="lands-refresh-all"]').forEach(el => { el.disabled = !!locked; });
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

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

})();
