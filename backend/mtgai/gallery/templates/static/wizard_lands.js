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
 *   §1  Lands never *auto*-pause for review. The footer shows a status note plus a
 *       "Next" button: a plain client-side tab change when the engine has already
 *       advanced, or — if a break point ("Stop after this step") paused the engine
 *       here — a resume (POST /api/wizard/advance) then navigate, like Reprints.
 *   §3  Form lock during AI gen.
 *   §6  Past-tab edit cascade via wizard_stage.js / W.editFlow.
 *   §8  Status pill flows from stage state.
 *   §9  "Stop after this step" — handled by wizard_stage.js.
 *   §13 Section-level Refresh-AI button, always rendered on the latest tab.
 *
 * The grid is read-only.  The Refresh button re-runs the lands stage under the
 * AI lock via ``POST /api/wizard/lands/refresh`` (basic-land alternate arts +
 * the dual-land fixing investigation), then repaints from the response.
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

      /* Collector number — the alternate-printing key (L-01a, L-01b, …) */
      .wiz-lands-cn {
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        font-size: 0.66rem;
        letter-spacing: 0.04em;
        color: #6a7da0;
        flex-shrink: 0;
      }

      .wiz-lands-type {
        font-size: 0.73rem;
        color: #888;
        font-style: italic;
      }

      /* Per-alternate art brief — makes each printing visibly distinct */
      .wiz-lands-brief {
        font-size: 0.73rem;
        color: #8fa6c8;
        line-height: 1.4;
      }
      .wiz-lands-brief-label {
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-size: 0.62rem;
        color: #5d6f92;
        margin-right: 0.35rem;
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
    // simplified land objects:
    //   {name, type_line, rarity, oracle_text, flavor_text, collector_number, design_notes}
    lands: [],
    hasContent: false,
    stageStatus: 'pending',
    locked: false,
    bootstrapping: false,
    state: null,        // latest wizard state, kept so refresh can repaint
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ── Top-level render ──────────────────────────────────────────────────────

  function render({ root, state, stage, content, footer }) {
    local.state = state;
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
    local.state = state;
    // GET /api/wizard/lands/state returns the durable tile shape read from the
    //   L-* card JSONs in <asset>/cards/:
    //   { lands: [{name, type_line, rarity, oracle_text, flavor_text,
    //              collector_number, design_notes}],
    //     has_content: bool, stage_status: str }
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

    // Sort: basics first (alphabetical), then nonbasics. Within one land type the
    // alternates share a name, so break ties on collector number (L-01a < L-01b)
    // to keep a type's printings in a stable, readable order.
    const sorted = [...local.lands].sort((a, b) => {
      const aBasic = isBasicType(a.type_line);
      const bBasic = isBasicType(b.type_line);
      if (aBasic !== bBasic) return aBasic ? -1 : 1;
      const byName = (a.name || '').localeCompare(b.name || '');
      if (byName !== 0) return byName;
      return (a.collector_number || '').localeCompare(b.collector_number || '');
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
    const cn = land.collector_number || '';
    const brief = artBrief(land);

    return `
      <article class="wiz-lands-tile" data-basic="${escAttr(String(isBasic))}">
        <div class="wiz-lands-tile-header">
          <span class="wiz-lands-name">${escHtml(land.name || '(unnamed)')}</span>
          ${cn ? `<span class="wiz-lands-cn">${escHtml(cn)}</span>` : ''}
          <span class="wiz-lands-rarity ${rarityClass}">${rarityLabel}</span>
        </div>
        ${land.type_line ? `<div class="wiz-lands-type">${escHtml(land.type_line)}</div>` : ''}
        ${brief ? `<div class="wiz-lands-brief"><span class="wiz-lands-brief-label">Art</span>${escHtml(brief)}</div>` : ''}
        ${oracle ? `<div class="wiz-lands-oracle">${escHtml(oracle)}</div>` : ''}
        ${flavor ? `<div class="wiz-lands-flavor">${escHtml(flavor)}</div>` : ''}
      </article>
    `;
  }

  // The lands stage stores each alternate's one-sentence art brief in
  // design_notes as "Alternate basic land art — <scene>". Strip that prefix so
  // the tile shows just the scene; the bonus dual's design_notes is an internal
  // note (not an art brief), so it isn't surfaced here.
  const ALT_BRIEF_PREFIX = 'Alternate basic land art';
  function artBrief(land) {
    const notes = (land.design_notes || '').trim();
    if (!notes.startsWith(ALT_BRIEF_PREFIX)) return '';
    // Drop the prefix and any leading em-dash / hyphen separator + spaces.
    return notes.slice(ALT_BRIEF_PREFIX.length).replace(/^[\s—–-]+/, '').trim();
  }

  function isBasicType(typeLine) {
    return /\bBasic\b/i.test(typeLine || '');
  }

  // ── Refresh: re-run the lands stage under the AI lock ────────────────────

  async function onRefreshAll() {
    if (local.locked) return;
    if (local.hasContent) {
      if (!confirm('Regenerate all land cards? Existing land JSONs will be replaced.')) return;
    }
    const root = bodyRoot();
    const state = local.state;
    setLocked(true);
    if (W.showBusy) W.showBusy(local.hasContent ? 'Regenerating land cards…' : 'Generating land cards…');
    try {
      const resp = await W.postJSON('/api/wizard/lands/refresh', {});
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        if (resp.status === 409 && data.running_action) {
          W.toast(`${data.running_action} is in progress — try again when it finishes.`, 'error');
        } else {
          W.toast(data.error || `Refresh failed (${resp.status})`, 'error');
        }
        return;
      }
      local.lands = Array.isArray(data.lands) ? data.lands : [];
      local.hasContent = !!data.has_content || local.lands.length > 0;
      if (data.stage_status) local.stageStatus = data.stage_status;
      if (root) {
        paintSummary(root, state);
        paintGrid(root, state);
        paintFooter(getFooter(root), state);
      }
      W.toast('Land cards regenerated.', 'success');
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    } finally {
      if (W.clearBusy) W.clearBusy();
      setLocked(false);
    }
  }

  // ── Footer: note only — lands never pause for review (§1) ────────────────

  function paintFooter(footer, state) {
    if (!footer) return;
    const isLatest = !state || state.latestTabId === STAGE_ID;
    const isCompleted = local.stageStatus === 'completed';
    // Lands never *auto*-pauses for review, but a break point ("Stop after this
    // step") can pause the engine here — then continuing means resuming the engine,
    // not just changing tabs. ``onGoNext(next, resume=true)`` handles that.
    const isPaused = local.stageStatus === 'paused_for_review';
    const next = W.nextStageEntryAfter(STAGE_ID);
    const nextName = next ? next.name : 'the next stage';

    // The "Next" button moves to the following tab. When paused it first resumes the
    // engine; otherwise it's a plain navigation (the engine already advanced on its
    // own). If the target tab isn't visible yet the server redirects to the latest.
    const nextBtn = next
      ? `<button type="button" class="wiz-btn-primary" data-role="lands-next">Next: ${escHtml(next.name)} →</button>`
      : '';

    let html;
    if (!isLatest) {
      // Engine has advanced past lands — this is now a past tab. No "Next"
      // button here (it would just re-resolve to the latest tab anyway, and
      // it reads as a stale control); the user follows the engine via the tab
      // strip. Matches the Reprints / Card Gen past-tab footer.
      html = `<span class="wiz-footer-note">Past tab — use Edit above to revise land cards.</span>`;
    } else if (isPaused) {
      html = `${nextBtn}<span class="wiz-footer-note">Paused after lands — continue when ready.</span>`;
    } else if (isCompleted) {
      html = `${nextBtn}<span class="wiz-footer-complete">✓ Lands generated — engine will continue to ${escHtml(nextName)}.</span>`;
    } else if (local.stageStatus === 'running') {
      html = `<span class="wiz-footer-note">Generating land cards…</span>`;
    } else {
      html = `<span class="wiz-footer-note">Runs automatically; no review step.</span>`;
    }

    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
    }
    const btn = footer.querySelector('[data-role="lands-next"]');
    if (btn) btn.onclick = () => onGoNext(next, isPaused);
  }

  async function onGoNext(next, resumeEngine) {
    if (local.locked) return;
    const nextHref = next ? `/pipeline/${next.id}` : '/pipeline';
    // Not paused — the engine already moved on, so this is a plain tab change.
    if (!resumeEngine) {
      window.location.assign(nextHref);
      return;
    }
    // Paused at a break point: resume the engine (mirrors the Reprints advance),
    // then navigate to the next tab.
    setLocked(true);
    try {
      const resp = await W.postJSON('/api/wizard/advance', {});
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        if (resp.status === 409 && data.running_action) {
          W.toast(`${data.running_action} is in progress — try again when it finishes.`, 'error');
        } else {
          W.toast(data.error || `Advance failed (${resp.status})`, 'error');
        }
        return;
      }
      window.location.assign(data.navigate_to || nextHref);
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    } finally {
      setLocked(false);
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

  const bodyRoot = () => W.tabRoot(STAGE_ID);

  const getFooter = (root) => W.tabFooter(root);

  const isPastTab = (state) => W.isPastTab(STAGE_ID, state);

  const escHtml = W.escHtml;

  const escAttr = W.escAttr;

})();
