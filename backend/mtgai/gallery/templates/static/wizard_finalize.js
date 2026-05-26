/**
 * Wizard Finalization tab — summary of reminder-text injection, auto-fixes,
 * and remaining MANUAL errors that need human attention.
 *
 * Registers via W.registerStageRenderer('finalize', ...) so wizard_stage.js
 * shell owns the header (status pill, break-point toggle, Edit button);
 * this module owns content + footer.
 *
 * Backend model: finalize_set() return dict (mtgai/review/finalize.py)
 *   { set_code, timestamp, dry_run, total_cards, cards_modified,
 *     total_auto_fixes, total_manual_errors,
 *     cards: [{ collector_number, name, fixes_applied[], manual_errors[
 *       { code, field, message, suggestion }], modified }] }
 *
 * NOTE: finalize is review_eligible: False — it never pauses for review.
 * Footer is always a wiz-footer-note; there is no "Next step" advance button.
 *
 * Conventions followed:
 *   §1  footer: wiz-footer-note only (no advance — finalize never pauses)
 *   §3  no editable controls; stage-running awareness for empty state copy
 *   §7  409 AI-mutex handling
 *   §12 escHtml, .onclick for rebind
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'finalize';

  // ---------------------------------------------------------------------------
  // Scoped styles (injected once)
  // ---------------------------------------------------------------------------

  (function injectStyles() {
    if (document.getElementById('wiz-finalize-styles')) return;
    const s = document.createElement('style');
    s.id = 'wiz-finalize-styles';
    s.textContent = `
      .wiz-finalize-summary-bar {
        display: flex; flex-wrap: wrap; gap: 1.2rem; align-items: center;
        padding: 0.75rem 1rem;
        background: var(--wiz-surface2, #1e2130);
        border-radius: 6px;
        margin-bottom: 1rem;
      }
      .wiz-finalize-stat { font-size: 0.92rem; color: var(--wiz-text-muted, #9aa3b8); }
      .wiz-finalize-stat strong { color: var(--wiz-text, #e2e8f0); }
      .wiz-finalize-section-header { margin: 1.25rem 0 0.5rem; }
      .wiz-finalize-card {
        background: var(--wiz-surface2, #1e2130);
        border-radius: 6px;
        border: 1px solid var(--wiz-border, #2d3348);
        margin-bottom: 0.5rem;
        overflow: hidden;
      }
      .wiz-finalize-card-header {
        display: flex; align-items: center; gap: 0.6rem;
        padding: 0.55rem 0.85rem;
        cursor: pointer;
        user-select: none;
      }
      .wiz-finalize-card-header:hover { background: var(--wiz-surface3, #252a3a); }
      .wiz-finalize-cn { font-family: monospace; font-size: 0.82rem; color: var(--wiz-text-muted, #9aa3b8); min-width: 6rem; }
      .wiz-finalize-name { flex: 1; font-weight: 500; font-size: 0.95rem; }
      .wiz-finalize-badge {
        font-size: 0.72rem; padding: 0.15rem 0.45rem; border-radius: 3px;
        font-weight: 600; background: var(--wiz-surface3, #252a3a); color: var(--wiz-text-muted, #9aa3b8);
      }
      .wiz-finalize-badge.manual { background: #3a1a00; color: #fb923c; }
      .wiz-finalize-badge.fixed { background: #0d3320; color: #4ade80; }
      .wiz-finalize-expand-icon { font-size: 0.8rem; color: var(--wiz-text-muted, #9aa3b8); margin-left: auto; }
      .wiz-finalize-card-body {
        padding: 0.75rem 1rem;
        border-top: 1px solid var(--wiz-border, #2d3348);
        font-size: 0.88rem;
      }
      .wiz-finalize-card-body[hidden] { display: none; }
      .wiz-finalize-errors { margin: 0; padding: 0; list-style: none; }
      .wiz-finalize-errors li {
        padding: 0.4rem 0;
        border-bottom: 1px solid var(--wiz-border, #2d3348);
        font-size: 0.85rem;
      }
      .wiz-finalize-errors li:last-child { border-bottom: none; }
      .wiz-finalize-error-code {
        font-family: monospace; font-size: 0.78rem; font-weight: 700;
        background: #3a1a00; color: #fb923c;
        padding: 0.1rem 0.35rem; border-radius: 3px; margin-right: 0.4rem;
      }
      .wiz-finalize-suggestion {
        font-size: 0.8rem; color: var(--wiz-text-muted, #9aa3b8);
        margin-top: 0.2rem; font-style: italic;
      }
      .wiz-finalize-fixes { margin: 0; padding: 0 0 0 1rem; }
      .wiz-finalize-fixes li { font-size: 0.85rem; padding: 0.15rem 0; color: #4ade80; }
      .wiz-finalize-empty { color: var(--wiz-text-muted, #9aa3b8); padding: 2rem; text-align: center; }
      .wiz-finalize-all-clean {
        padding: 1rem; text-align: center; border-radius: 6px;
        background: #0d3320; color: #4ade80; font-weight: 500;
      }
      .wiz-finalize-pipeline-info {
        display: flex; flex-direction: column; gap: 0.3rem;
        font-size: 0.85rem; color: var(--wiz-text-muted, #9aa3b8);
        padding: 0.75rem 0;
      }
      .wiz-finalize-pipeline-info span { display: flex; gap: 0.5rem; align-items: center; }
      .wiz-finalize-step-tag {
        font-size: 0.72rem; font-weight: 600; padding: 0.1rem 0.4rem;
        border-radius: 3px; background: var(--wiz-surface3, #252a3a); color: var(--wiz-text-muted, #9aa3b8);
      }
    `;
    document.head.appendChild(s);
  })();

  // ---------------------------------------------------------------------------
  // Module state
  // ---------------------------------------------------------------------------

  const local = {
    initialized: false,
    stageStatus: 'pending',
    // TODO: populated by GET /api/wizard/finalize/state
    // Shape: { result: finalize_set() dict, stage_status, has_content }
    result: null,
    hasContent: false,
    bootstrapping: false,
    expanded: new Set(),
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ---------------------------------------------------------------------------
  // Top-level render
  // ---------------------------------------------------------------------------

  function render({ root, state, stage, content, footer }) {
    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      bootstrap(root, state).catch(err => {
        W.toast('Failed to load finalize state: ' + err.message, 'error');
      });
      paintFooter(footer, state);
      return;
    }

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
        .catch(err => W.toast('Failed to refresh finalize state: ' + err.message, 'error'))
        .finally(() => { local.bootstrapping = false; });
      return;
    }
    paintFooter(footer, state);
  }

  function mountShellHtml() {
    return `
      <div data-role="fin-summary"></div>
      <div data-role="fin-pipeline-steps"></div>
      <div data-role="fin-manual-section"></div>
      <div data-role="fin-fixes-section"></div>
    `;
  }

  // ---------------------------------------------------------------------------
  // Bootstrap — fetch from backend, degrade gracefully
  // ---------------------------------------------------------------------------

  async function bootstrap(root, state) {
    // TODO: GET /api/wizard/finalize/state should return:
    //   { result: finalize_set() dict, stage_status: str, has_content: bool }
    let data = null;
    try {
      const resp = await fetch('/api/wizard/finalize/state');
      if (resp.ok) {
        data = await resp.json();
      }
    } catch (_) {
      // Endpoint not yet implemented — render graceful empty state.
    }

    if (data) {
      local.result = data.result || null;
      local.hasContent = !!data.has_content;
      if (data.stage_status) local.stageStatus = data.stage_status;
    }

    paintSummaryBar(root);
    paintPipelineSteps(root);
    paintManualSection(root);
    paintFixesSection(root);
    paintFooter(getFooter(root), state);
  }

  // ---------------------------------------------------------------------------
  // Summary bar
  // ---------------------------------------------------------------------------

  function paintSummaryBar(root) {
    const slot = root.querySelector('[data-role="fin-summary"]');
    if (!slot) return;

    if (!local.hasContent || !local.result) {
      slot.innerHTML = '';
      return;
    }

    const r = local.result;
    const totalCards = r.total_cards || 0;
    const modified = r.cards_modified || 0;
    const autoFixes = r.total_auto_fixes || 0;
    const manualErrors = r.total_manual_errors || 0;
    const ts = r.timestamp ? new Date(r.timestamp).toLocaleString() : '';

    slot.innerHTML = `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">Finalization summary</h3>
      </div>
      <div class="wiz-finalize-summary-bar">
        <span class="wiz-finalize-stat"><strong>${escHtml(String(totalCards))}</strong> cards processed</span>
        <span class="wiz-finalize-stat"><strong>${escHtml(String(modified))}</strong> cards modified</span>
        <span class="wiz-finalize-stat"><strong>${escHtml(String(autoFixes))}</strong> auto-fixes applied</span>
        <span class="wiz-finalize-stat ${manualErrors > 0 ? 'wiz-finalize-stat--warn' : ''}">
          <strong>${escHtml(String(manualErrors))}</strong> manual error${manualErrors !== 1 ? 's' : ''} remaining
        </span>
        ${ts ? `<span class="wiz-finalize-stat">Ran: ${escHtml(ts)}</span>` : ''}
      </div>
    `;
  }

  // ---------------------------------------------------------------------------
  // Pipeline steps info block (what finalize does)
  // ---------------------------------------------------------------------------

  function paintPipelineSteps(root) {
    const slot = root.querySelector('[data-role="fin-pipeline-steps"]');
    if (!slot) return;

    slot.innerHTML = `
      <div class="wiz-finalize-pipeline-info">
        <span><span class="wiz-finalize-step-tag">1</span> Reminder text injection — strips any LLM-written reminder text, then injects fresh text from mechanic definitions.</span>
        <span><span class="wiz-finalize-step-tag">2</span> Validation — full validation suite run on every card.</span>
        <span><span class="wiz-finalize-step-tag">3</span> Auto-fix — AUTO-category errors corrected programmatically; MANUAL errors listed below for human review.</span>
        <span><span class="wiz-finalize-step-tag">4</span> Save — modified cards written back to disk.</span>
      </div>
    `;
  }

  // ---------------------------------------------------------------------------
  // MANUAL errors section (the actionable part for the user)
  // ---------------------------------------------------------------------------

  function paintManualSection(root) {
    const slot = root.querySelector('[data-role="fin-manual-section"]');
    if (!slot) return;

    if (!local.hasContent) {
      const running = local.stageStatus === 'running';
      slot.innerHTML = `
        <div class="wiz-theme-section-header-row" style="margin-top:1.25rem">
          <h3 style="margin:0">MANUAL errors</h3>
        </div>
        <div class="wiz-finalize-empty">${
          running
            ? 'Finalization is running…'
            : 'No finalization results yet. The Finalize stage must complete first.'
        }</div>
      `;
      return;
    }

    const r = local.result;
    const manualCards = (r.cards || []).filter(c => c.manual_errors && c.manual_errors.length > 0);

    let bodyHtml;
    if (manualCards.length === 0) {
      bodyHtml = `<div class="wiz-finalize-all-clean">All cards passed validation — no manual errors remaining.</div>`;
    } else {
      bodyHtml = manualCards.map(c => manualCardHtml(c)).join('');
    }

    slot.innerHTML = `
      <div class="wiz-theme-section-header-row" style="margin-top:1.25rem">
        <h3 style="margin:0">MANUAL errors <span style="font-size:0.85rem;font-weight:400;color:var(--wiz-text-muted,#9aa3b8)">(${escHtml(String(manualCards.length))} card${manualCards.length !== 1 ? 's' : ''})</span></h3>
      </div>
      <p class="wiz-stage-empty" style="padding:0.25rem 0 0.75rem">These issues could not be fixed automatically. Edit the card JSON directly or re-run card generation for the affected slots.</p>
      ${bodyHtml}
    `;

    slot.querySelectorAll('.wiz-finalize-card-header').forEach(hdr => {
      hdr.onclick = () => {
        const cn = hdr.closest('.wiz-finalize-card').dataset.cn;
        const section = hdr.closest('[data-role]').dataset.role;
        const key = section + ':' + cn;
        if (local.expanded.has(key)) {
          local.expanded.delete(key);
        } else {
          local.expanded.add(key);
        }
        const body = hdr.nextElementSibling;
        if (body) body.hidden = !local.expanded.has(key);
        const icon = hdr.querySelector('.wiz-finalize-expand-icon');
        if (icon) icon.textContent = local.expanded.has(key) ? '▲' : '▼';
      };
    });
  }

  function manualCardHtml(c) {
    const cn = c.collector_number || '?';
    const name = c.name || '?';
    const errCount = (c.manual_errors || []).length;
    const key = 'fin-manual-section:' + cn;
    const isOpen = local.expanded.has(key);

    const errorItemsHtml = (c.manual_errors || []).map(e => {
      const code = e.code || 'unknown';
      const msg = e.message || '';
      const sug = e.suggestion || '';
      return `
        <li>
          <span class="wiz-finalize-error-code">${escHtml(code)}</span>
          ${escHtml(msg)}
          ${sug ? `<div class="wiz-finalize-suggestion">Suggestion: ${escHtml(sug)}</div>` : ''}
        </li>
      `;
    }).join('');

    return `
      <div class="wiz-finalize-card" data-cn="${escAttr(cn)}">
        <div class="wiz-finalize-card-header">
          <span class="wiz-finalize-cn">${escHtml(cn)}</span>
          <span class="wiz-finalize-name">${escHtml(name)}</span>
          <span class="wiz-finalize-badge manual">${escHtml(String(errCount))} error${errCount !== 1 ? 's' : ''}</span>
          <span class="wiz-finalize-expand-icon">${isOpen ? '▲' : '▼'}</span>
        </div>
        <div class="wiz-finalize-card-body" ${isOpen ? '' : 'hidden'}>
          <ul class="wiz-finalize-errors">${errorItemsHtml}</ul>
        </div>
      </div>
    `;
  }

  // ---------------------------------------------------------------------------
  // Auto-fixes section (informational — shows what was corrected)
  // ---------------------------------------------------------------------------

  function paintFixesSection(root) {
    const slot = root.querySelector('[data-role="fin-fixes-section"]');
    if (!slot) return;

    if (!local.hasContent || !local.result) {
      slot.innerHTML = '';
      return;
    }

    const r = local.result;
    const fixedCards = (r.cards || []).filter(c => c.fixes_applied && c.fixes_applied.length > 0);

    if (!fixedCards.length) {
      slot.innerHTML = '';
      return;
    }

    const cardsHtml = fixedCards.map(c => {
      const cn = c.collector_number || '?';
      const name = c.name || '?';
      const fixCount = c.fixes_applied.length;
      const key = 'fin-fixes-section:' + cn;
      const isOpen = local.expanded.has(key);
      const fixesHtml = c.fixes_applied.map(f => `<li>${escHtml(f)}</li>`).join('');
      return `
        <div class="wiz-finalize-card" data-cn="${escAttr(cn)}">
          <div class="wiz-finalize-card-header">
            <span class="wiz-finalize-cn">${escHtml(cn)}</span>
            <span class="wiz-finalize-name">${escHtml(name)}</span>
            <span class="wiz-finalize-badge fixed">${escHtml(String(fixCount))} fix${fixCount !== 1 ? 'es' : ''}</span>
            <span class="wiz-finalize-expand-icon">${isOpen ? '▲' : '▼'}</span>
          </div>
          <div class="wiz-finalize-card-body" ${isOpen ? '' : 'hidden'}>
            <ul class="wiz-finalize-fixes">${fixesHtml}</ul>
          </div>
        </div>
      `;
    }).join('');

    slot.innerHTML = `
      <div class="wiz-theme-section-header-row wiz-finalize-section-header">
        <h3 style="margin:0">Auto-fixes applied <span style="font-size:0.85rem;font-weight:400;color:var(--wiz-text-muted,#9aa3b8)">(${escHtml(String(fixedCards.length))} card${fixedCards.length !== 1 ? 's' : ''})</span></h3>
      </div>
      ${cardsHtml}
    `;

    slot.querySelectorAll('.wiz-finalize-card-header').forEach(hdr => {
      hdr.onclick = () => {
        const cn = hdr.closest('.wiz-finalize-card').dataset.cn;
        const section = hdr.closest('[data-role]').dataset.role;
        const key = section + ':' + cn;
        if (local.expanded.has(key)) {
          local.expanded.delete(key);
        } else {
          local.expanded.add(key);
        }
        const body = hdr.nextElementSibling;
        if (body) body.hidden = !local.expanded.has(key);
        const icon = hdr.querySelector('.wiz-finalize-expand-icon');
        if (icon) icon.textContent = local.expanded.has(key) ? '▲' : '▼';
      };
    });
  }

  // ---------------------------------------------------------------------------
  // Footer (§1): finalize never pauses — footer is always a note
  // ---------------------------------------------------------------------------

  function paintFooter(footer, state) {
    if (!footer) return;
    const isLatest = !state || state.latestTabId === STAGE_ID;

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Finalization complete — view is read-only on a past tab.</span>`;
    } else if (local.stageStatus === 'running') {
      html = `<span class="wiz-footer-note">Finalization is running automatically…</span>`;
    } else if (local.stageStatus === 'completed') {
      const next = W.nextStageEntryAfter(STAGE_ID);
      html = next
        ? `<span class="wiz-footer-note">Finalization complete. Engine is now on <strong>${escHtml(next.name)}</strong>.</span>`
        : `<span class="wiz-footer-note">Finalization complete.</span>`;
    } else if (local.stageStatus === 'failed') {
      html = `<span class="wiz-footer-note">Stage failed — check the progress strip for details.</span>`;
    } else {
      html = `<span class="wiz-footer-note">Runs automatically after AI Review — no review step.</span>`;
    }

    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
    }
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function getFooter(root) {
    return root && root.querySelector('[data-role="footer"]');
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
