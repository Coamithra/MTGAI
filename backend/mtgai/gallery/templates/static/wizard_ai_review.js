/**
 * Wizard AI Design Review tab — per-card tiered review results display.
 *
 * Registers via W.registerStageRenderer('ai_review', ...) so the standard
 * wizard_stage.js shell owns the header (status pill, break-point toggle,
 * Edit-cascade button); this module owns content + footer.
 *
 * Backend model: CardReviewResult (mtgai/review/ai_review.py)
 *   { collector_number, card_name, rarity, review_tier ("single"|"council"),
 *     model, final_verdict ("OK"|"REVISE"), final_issues[], revised_card,
 *     card_was_changed, iterations[], council_reviews[],
 *     total_cost_usd, timestamp }
 *
 * Stage summary from review_all_cards():
 *   { reviewed, revised, cost_usd, summary }
 *
 * Conventions followed:
 *   §1  footer: paused_for_review + latest-tab → Next-step advance button
 *   §3  form lock (no editable controls here, but stage locking for UI state)
 *   §7  409 AI-mutex toast
 *   §12 escHtml, .onclick for rebind
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  const STAGE_ID = 'ai_review';

  // ---------------------------------------------------------------------------
  // Scoped styles (injected once)
  // ---------------------------------------------------------------------------

  (function injectStyles() {
    if (document.getElementById('wiz-ai-review-styles')) return;
    const s = document.createElement('style');
    s.id = 'wiz-ai-review-styles';
    s.textContent = `
      .wiz-ai-review-summary-bar {
        display: flex; flex-wrap: wrap; gap: 1.2rem; align-items: center;
        padding: 0.75rem 1rem;
        background: var(--wiz-surface2, #1e2130);
        border-radius: 6px;
        margin-bottom: 1rem;
      }
      .wiz-ai-review-summary-bar .wiz-ai-review-stat { font-size: 0.92rem; color: var(--wiz-text-muted, #9aa3b8); }
      .wiz-ai-review-summary-bar .wiz-ai-review-stat strong { color: var(--wiz-text, #e2e8f0); }
      .wiz-ai-review-list { display: flex; flex-direction: column; gap: 0.5rem; }
      .wiz-ai-review-card {
        background: var(--wiz-surface2, #1e2130);
        border-radius: 6px;
        border: 1px solid var(--wiz-border, #2d3348);
        overflow: hidden;
      }
      .wiz-ai-review-card-header {
        display: flex; align-items: center; gap: 0.6rem;
        padding: 0.55rem 0.85rem;
        cursor: pointer;
        user-select: none;
      }
      .wiz-ai-review-card-header:hover { background: var(--wiz-surface3, #252a3a); }
      .wiz-ai-review-cn { font-family: monospace; font-size: 0.82rem; color: var(--wiz-text-muted, #9aa3b8); min-width: 6rem; }
      .wiz-ai-review-name { flex: 1; font-weight: 500; font-size: 0.95rem; }
      .wiz-ai-review-rarity { font-size: 0.78rem; color: var(--wiz-text-muted, #9aa3b8); }
      .wiz-ai-review-tier-badge {
        font-size: 0.72rem; padding: 0.15rem 0.45rem;
        border-radius: 3px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em;
        background: var(--wiz-surface3, #252a3a); color: var(--wiz-text-muted, #9aa3b8);
      }
      .wiz-ai-review-tier-badge.council { background: #2d2060; color: #a78bfa; }
      .wiz-ai-review-verdict-pill {
        font-size: 0.78rem; padding: 0.15rem 0.5rem;
        border-radius: 3px; font-weight: 700; text-transform: uppercase;
      }
      .wiz-ai-review-verdict-pill.OK { background: #0d3320; color: #4ade80; }
      .wiz-ai-review-verdict-pill.REVISE { background: #3a1a00; color: #fb923c; }
      .wiz-ai-review-changed-tag {
        font-size: 0.72rem; color: #fb923c;
        font-style: italic;
      }
      .wiz-ai-review-expand-icon { font-size: 0.8rem; color: var(--wiz-text-muted, #9aa3b8); margin-left: auto; }
      .wiz-ai-review-card-body {
        padding: 0.75rem 1rem;
        border-top: 1px solid var(--wiz-border, #2d3348);
        font-size: 0.88rem;
      }
      .wiz-ai-review-card-body[hidden] { display: none; }
      .wiz-ai-review-issues { margin: 0.5rem 0 0; padding: 0; list-style: none; }
      .wiz-ai-review-issues li {
        display: flex; gap: 0.5rem; padding: 0.3rem 0;
        border-bottom: 1px solid var(--wiz-border, #2d3348);
        font-size: 0.85rem;
      }
      .wiz-ai-review-issues li:last-child { border-bottom: none; }
      .wiz-ai-review-sev {
        font-size: 0.72rem; font-weight: 700; padding: 0.1rem 0.35rem; border-radius: 3px;
        flex-shrink: 0; align-self: flex-start; margin-top: 0.1rem;
      }
      .wiz-ai-review-sev.FAIL { background: #3a0c0c; color: #f87171; }
      .wiz-ai-review-sev.WARN { background: #3a2a00; color: #fbbf24; }
      .wiz-ai-review-cat { color: var(--wiz-text-muted, #9aa3b8); font-size: 0.8rem; flex-shrink: 0; }
      .wiz-ai-review-council-row {
        display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 0.4rem 0;
      }
      .wiz-ai-review-council-member {
        font-size: 0.78rem; padding: 0.15rem 0.5rem;
        border-radius: 3px; background: var(--wiz-surface3, #252a3a);
        color: var(--wiz-text-muted, #9aa3b8);
      }
      .wiz-ai-review-council-member.REVISE { color: #fb923c; }
      .wiz-ai-review-council-member.OK { color: #4ade80; }
      .wiz-ai-review-cost { font-size: 0.78rem; color: var(--wiz-text-muted, #9aa3b8); margin-top: 0.4rem; }
      .wiz-ai-review-empty { color: var(--wiz-text-muted, #9aa3b8); padding: 2rem; text-align: center; }
      .wiz-ai-review-filter-bar { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.75rem; }
      .wiz-ai-review-filter-btn {
        font-size: 0.8rem; padding: 0.25rem 0.7rem; border-radius: 4px; cursor: pointer; border: 1px solid var(--wiz-border, #2d3348);
        background: var(--wiz-surface2, #1e2130); color: var(--wiz-text-muted, #9aa3b8);
      }
      .wiz-ai-review-filter-btn.active { background: var(--wiz-accent, #4f46e5); color: #fff; border-color: var(--wiz-accent, #4f46e5); }
    `;
    document.head.appendChild(s);
  })();

  // ---------------------------------------------------------------------------
  // Module state
  // ---------------------------------------------------------------------------

  const local = {
    initialized: false,
    stageStatus: 'pending',
    // TODO: populated by GET /api/wizard/ai_review/state
    // Shape: { reviews: CardReviewResult[], summary: { reviewed, revised, cost_usd } }
    reviews: [],
    summary: null,
    hasContent: false,
    bootstrapping: false,
    filter: 'all',  // 'all' | 'OK' | 'REVISE' | 'revised'
    expanded: new Set(),
  };

  W.registerStageRenderer(STAGE_ID, render);

  // ---------------------------------------------------------------------------
  // Top-level render (called by wizard_stage.js shell on every SSE rerender)
  // ---------------------------------------------------------------------------

  function render({ root, state, stage, content, footer }) {
    if (!local.initialized) {
      local.initialized = true;
      local.stageStatus = stage ? stage.status : 'pending';
      content.innerHTML = mountShellHtml();
      W.bindRerunButton(root, stage);
      bootstrap(root, state).catch(err => {
        W.toast('Failed to load AI review state: ' + err.message, 'error');
      });
      paintFooter(footer, state);
      return;
    }

    // Re-render path — update live state without clobbering the card list.
    const prevStatus = local.stageStatus;
    if (stage) local.stageStatus = stage.status;

    // When stage finishes and we still have no content, re-pull.
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
        .catch(err => W.toast('Failed to refresh AI review state: ' + err.message, 'error'))
        .finally(() => { local.bootstrapping = false; });
      return;
    }
    W.bindRerunButton(root, stage);
    paintFooter(footer, state);
  }

  function mountShellHtml() {
    return `
      ${W.rerunButtonHtml()}
      <div data-role="ar-summary"></div>
      <div data-role="ar-filter" class="wiz-ai-review-filter-bar"></div>
      <div data-role="ar-list" class="wiz-ai-review-list">
        <div class="wiz-ai-review-empty">Loading review results…</div>
      </div>
    `;
  }

  // ---------------------------------------------------------------------------
  // Bootstrap — fetch from backend, fall back to empty gracefully
  // ---------------------------------------------------------------------------

  async function bootstrap(root, state) {
    // TODO: GET /api/wizard/ai_review/state should return:
    //   { reviews: CardReviewResult[], summary: { reviewed, revised, cost_usd },
    //     stage_status: str, has_content: bool }
    let data = null;
    try {
      const resp = await fetch('/api/wizard/ai_review/state');
      if (resp.ok) {
        data = await resp.json();
      }
    } catch (_) {
      // Endpoint not yet implemented — render graceful empty state.
    }

    if (data) {
      local.reviews = Array.isArray(data.reviews) ? data.reviews : [];
      local.summary = data.summary || null;
      local.hasContent = !!data.has_content;
      if (data.stage_status) local.stageStatus = data.stage_status;
    }

    paintSummaryBar(root);
    paintFilter(root);
    paintList(root);
    paintFooter(getFooter(root), state);
  }

  // ---------------------------------------------------------------------------
  // Summary bar
  // ---------------------------------------------------------------------------

  function paintSummaryBar(root) {
    const slot = root.querySelector('[data-role="ar-summary"]');
    if (!slot) return;
    if (!local.hasContent || !local.summary) {
      slot.innerHTML = '';
      return;
    }
    const s = local.summary;
    const reviewed = s.reviewed || local.reviews.length;
    const revised = s.revised != null ? s.revised : local.reviews.filter(r => r.card_was_changed).length;
    const cost = s.cost_usd != null ? '$' + Number(s.cost_usd).toFixed(2) : '—';
    const okCount = local.reviews.filter(r => r.final_verdict === 'OK').length;
    const reviseCount = local.reviews.filter(r => r.final_verdict === 'REVISE').length;
    const singleCount = local.reviews.filter(r => r.review_tier === 'single').length;
    const councilCount = local.reviews.filter(r => r.review_tier === 'council').length;

    slot.innerHTML = `
      <div class="wiz-theme-section-header-row">
        <h3 style="margin:0">Review results</h3>
        <span class="wiz-ai-badge">AI</span>
      </div>
      <div class="wiz-ai-review-summary-bar">
        <span class="wiz-ai-review-stat"><strong>${escHtml(String(reviewed))}</strong> reviewed</span>
        <span class="wiz-ai-review-stat"><strong>${escHtml(String(okCount))}</strong> OK</span>
        <span class="wiz-ai-review-stat"><strong>${escHtml(String(reviseCount))}</strong> revised by AI</span>
        <span class="wiz-ai-review-stat"><strong>${escHtml(String(revised))}</strong> cards changed</span>
        <span class="wiz-ai-review-stat"><strong>${escHtml(String(singleCount))}</strong> single · <strong>${escHtml(String(councilCount))}</strong> council</span>
        <span class="wiz-ai-review-stat">Cost: <strong>${escHtml(cost)}</strong></span>
      </div>
    `;
  }

  // ---------------------------------------------------------------------------
  // Filter bar
  // ---------------------------------------------------------------------------

  function paintFilter(root) {
    const slot = root.querySelector('[data-role="ar-filter"]');
    if (!slot) return;
    if (!local.hasContent || !local.reviews.length) {
      slot.innerHTML = '';
      return;
    }
    const filters = [
      { id: 'all', label: 'All' },
      { id: 'OK', label: 'OK' },
      { id: 'REVISE', label: 'REVISE' },
      { id: 'revised', label: 'Changed' },
      { id: 'council', label: 'Council tier' },
    ];
    slot.innerHTML = filters.map(f =>
      `<button type="button" class="wiz-ai-review-filter-btn${local.filter === f.id ? ' active' : ''}"
         data-filter="${escAttr(f.id)}">${escHtml(f.label)}</button>`
    ).join('');
    slot.querySelectorAll('.wiz-ai-review-filter-btn').forEach(btn => {
      btn.onclick = () => {
        local.filter = btn.dataset.filter;
        paintFilter(root);
        paintList(root);
      };
    });
  }

  // ---------------------------------------------------------------------------
  // Card list
  // ---------------------------------------------------------------------------

  function paintList(root) {
    const slot = root.querySelector('[data-role="ar-list"]');
    if (!slot) return;

    if (!local.hasContent) {
      const running = local.stageStatus === 'running';
      slot.innerHTML = `<div class="wiz-ai-review-empty">${
        running
          ? 'AI review is running — results will appear when complete.'
          : 'No review results yet. The AI Review stage must complete first.'
      }</div>`;
      return;
    }

    const visible = filteredReviews();
    if (!visible.length) {
      slot.innerHTML = `<div class="wiz-ai-review-empty">No cards match this filter.</div>`;
      return;
    }

    slot.innerHTML = visible.map(r => reviewCardHtml(r)).join('');
    slot.querySelectorAll('.wiz-ai-review-card-header').forEach(hdr => {
      hdr.onclick = () => {
        const cn = hdr.closest('.wiz-ai-review-card').dataset.cn;
        if (local.expanded.has(cn)) {
          local.expanded.delete(cn);
        } else {
          local.expanded.add(cn);
        }
        const body = hdr.nextElementSibling;
        if (body) body.hidden = !local.expanded.has(cn);
        const icon = hdr.querySelector('.wiz-ai-review-expand-icon');
        if (icon) icon.textContent = local.expanded.has(cn) ? '▲' : '▼';
      };
    });
  }

  function filteredReviews() {
    return local.reviews.filter(r => {
      if (local.filter === 'OK') return r.final_verdict === 'OK';
      if (local.filter === 'REVISE') return r.final_verdict === 'REVISE';
      if (local.filter === 'revised') return !!r.card_was_changed;
      if (local.filter === 'council') return r.review_tier === 'council';
      return true;
    });
  }

  function reviewCardHtml(r) {
    const cn = r.collector_number || '?';
    const name = r.card_name || '?';
    const rarity = r.rarity || '';
    const tier = r.review_tier || 'single';
    const verdict = r.final_verdict || 'OK';
    const changed = !!r.card_was_changed;
    const isOpen = local.expanded.has(cn);
    const issueCount = (r.final_issues || []).length;
    const councilMembers = r.council_reviews || [];
    const cost = r.total_cost_usd != null ? '$' + Number(r.total_cost_usd).toFixed(4) : '';
    const iters = (r.iterations || []).length;

    // Build detail body
    const issueHtml = issueCount > 0
      ? `<ul class="wiz-ai-review-issues">${
          (r.final_issues || []).map(i => `
            <li>
              <span class="wiz-ai-review-sev ${escAttr(i.severity)}">${escHtml(i.severity)}</span>
              <span class="wiz-ai-review-cat">${escHtml(i.category)}</span>
              <span>${escHtml(i.description)}</span>
            </li>
          `).join('')
        }</ul>`
      : '<p style="margin:0.3rem 0;color:var(--wiz-text-muted,#9aa3b8);font-size:0.85rem;">No issues flagged.</p>';

    const councilHtml = councilMembers.length > 0
      ? `<div class="wiz-ai-review-council-row">${
          councilMembers.map(cm =>
            `<span class="wiz-ai-review-council-member ${escAttr(cm.verdict || 'OK')}">`
            + `Reviewer ${escHtml(String(cm.member_id))}: ${escHtml(cm.verdict || '?')}`
            + ` (${escHtml(String((cm.issues || []).length))} issues)`
            + `</span>`
          ).join('')
        }</div>`
      : '';

    const iterDetail = iters > 0
      ? `<span class="wiz-ai-review-cost">${escHtml(String(iters))} iteration${iters !== 1 ? 's' : ''}</span>`
      : '';

    return `
      <article class="wiz-ai-review-card" data-cn="${escAttr(cn)}">
        <div class="wiz-ai-review-card-header">
          <span class="wiz-ai-review-cn">${escHtml(cn)}</span>
          <span class="wiz-ai-review-name">${escHtml(name)}</span>
          <span class="wiz-ai-review-rarity">${escHtml(rarity)}</span>
          <span class="wiz-ai-review-tier-badge ${escAttr(tier)}">${escHtml(tier)}</span>
          <span class="wiz-ai-review-verdict-pill ${escAttr(verdict)}">${escHtml(verdict)}</span>
          ${changed ? '<span class="wiz-ai-review-changed-tag">revised</span>' : ''}
          <span class="wiz-ai-review-expand-icon">${isOpen ? '▲' : '▼'}</span>
        </div>
        <div class="wiz-ai-review-card-body" ${isOpen ? '' : 'hidden'}>
          ${councilHtml}
          ${issueHtml}
          <div class="wiz-ai-review-cost">
            ${cost ? `Cost: ${escHtml(cost)}` : ''}
            ${iterDetail}
          </div>
        </div>
      </article>
    `;
  }

  // ---------------------------------------------------------------------------
  // Footer (§1): paused_for_review + latest tab → Next-step advance
  // ---------------------------------------------------------------------------

  function paintFooter(footer, state) {
    if (!footer) return;
    const isLatest = !state || state.latestTabId === STAGE_ID;
    const isPaused = local.stageStatus === 'paused_for_review';
    const next = W.nextStageEntryAfter(STAGE_ID);
    const nextName = next ? next.name : 'Next stage';

    let html;
    if (!isLatest) {
      html = `<span class="wiz-footer-note">Review completed — results are read-only on a past tab.</span>`;
    } else if (isPaused) {
      html = `<button type="button" class="wiz-btn-primary" data-role="ar-next-step">Next step: ${escHtml(nextName)}</button>`;
    } else if (local.stageStatus === 'running') {
      html = `<span class="wiz-footer-note">AI review is in progress…</span>`;
    } else if (local.stageStatus === 'failed') {
      html = `<span class="wiz-footer-note">Stage failed — check logs and retry.</span>`;
    } else {
      html = `<span class="wiz-footer-note">Waiting for AI review to run.</span>`;
    }

    if (footer.dataset.lastFooter !== html) {
      footer.innerHTML = html;
      footer.dataset.lastFooter = html;
    }

    const btn = footer.querySelector('[data-role="ar-next-step"]');
    if (btn) bindNextStepButton(btn);
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
          if (resp.status === 409 && data.running_action) {
            W.toast(`${data.running_action} is in progress — try again when it finishes.`, 'error');
          } else {
            W.toast(data.error || 'Advance failed', 'error');
          }
          btn.disabled = false;
          btn.textContent = original;
        }
        // On success: leave disabled, SSE will repaint when next stage transitions.
      } catch (err) {
        W.toast('Network error: ' + err.message, 'error');
        btn.disabled = false;
        btn.textContent = original;
      }
    };
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function getFooter(root) {
    return root && root.querySelector('[data-role="footer"]');
  }

  const escHtml = W.escHtml;
  const escAttr = W.escAttr;
})();
