/**
 * Wizard Conformance tab (stage_id ``conformance``).
 *
 * The first review→regen gate: each generated card vs. its slot spec. Flags any
 * non-conforming card for regeneration. Renders this instance's findings
 * (``stage.result`` — the runner's artifacts, carried on the stage_update SSE),
 * so the backbone instance and any inserted ``conformance.2`` re-run render the
 * same way.
 *
 * Instance-aware (keys off ``stage.instance_id`` / ``tab.id``); shares the
 * ``wiz-gate-*`` styles injected by wizard_balance.js.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});

  if (!document.getElementById('wiz-gate-styles')) {
    const style = document.createElement('style');
    style.id = 'wiz-gate-styles';
    style.textContent = `
      .wiz-gate-ok { font-size: 1.1rem; font-weight: 700; color: #00d4aa; margin-bottom: 0.8rem; }
      .wiz-gate-flagged { font-size: 1.1rem; font-weight: 700; color: #ffa502; margin-bottom: 0.8rem; }
      .wiz-gate-analysis { color: #aaa; font-style: italic; margin: 0 0 1rem; }
      .wiz-gate-paused { color: #ffa502; margin: 0 0 1rem; }
      .wiz-gate-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.6rem; }
      .wiz-gate-list li { background: #ffffff08; border-left: 3px solid #ffa502; border-radius: 4px; padding: 0.6rem 0.8rem; }
      .wiz-gate-reason { color: #ccc; font-size: 0.9rem; margin-top: 0.25rem; }
    `;
    document.head.appendChild(style);
  }

  W.registerStageRenderer('conformance', render);

  function render({ state, stage, content, footer }) {
    if (content) content.innerHTML = bodyHtml(stage);
    paintFooter(footer, state, stage);
  }

  function bodyHtml(stage) {
    const status = stage ? stage.status : 'pending';
    if (status === 'pending') {
      return '<div class="wiz-stage-empty">Conformance check has not run yet.</div>';
    }
    if (status === 'running') {
      return '<div class="wiz-stage-empty">Checking each card against its slot spec…</div>';
    }
    const result = (stage && stage.result) || {};
    const flagged = result.flagged || [];
    const analysis = result.analysis || '';
    const header = flagged.length === 0
      ? '<div class="wiz-gate-ok">✓ Every card matches its slot spec.</div>'
      : '<div class="wiz-gate-flagged">' + flagged.length
        + ' card(s) flagged for regeneration</div>';
    const analysisBlock = analysis
      ? '<p class="wiz-gate-analysis">' + escHtml(analysis) + '</p>' : '';
    const pausedNote = (status === 'paused_for_review' && flagged.length)
      ? '<p class="wiz-gate-paused">Review limit reached — these cards are left flagged for you '
        + 'to edit or accept by hand before continuing.</p>'
      : '';
    const list = flagged.length
      ? '<ul class="wiz-gate-list">' + flagged.map(flaggedItemHtml).join('') + '</ul>'
      : '';
    return header + analysisBlock + pausedNote + list;
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
