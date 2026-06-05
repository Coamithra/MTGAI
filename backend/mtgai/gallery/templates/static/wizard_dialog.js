/**
 * wizard_dialog.js — in-app replacement for native window.confirm/alert/prompt.
 *
 * Native dialogs are OS-level windows outside the page DOM: they freeze page JS
 * and are invisible to the claude-in-chrome QA driver (which can only reach the
 * DOM), so a single confirm() hangs the whole QA harness. They're also off-theme
 * and not focus-/keyboard-styleable. This module is the styled, in-DOM, Promise-
 * based stand-in.
 *
 *   MTGAIDialog.confirm(message, opts?)        -> Promise<boolean>
 *   MTGAIDialog.alert(message, opts?)          -> Promise<void>
 *   MTGAIDialog.prompt(message, default, opts?) -> Promise<string|null>
 *
 * opts (all optional): { title, okLabel, cancelLabel }.
 *
 * The dialog reuses the wizard's existing .wiz-modal* / .wiz-btn-* chrome (from
 * wizard.css, always loaded on the wizard page) so it tracks the dark theme for
 * free; only the prompt input + message text need bespoke rules, injected once.
 * It is focus-trapped, Esc = cancel, Enter = confirm/submit, backdrop click =
 * cancel, and restores focus to the previously-focused element on close. The
 * OK / Cancel / input controls carry stable data-testid hooks so automation (and
 * humans) can drive it.
 *
 * Standalone by design — depends only on the DOM, not on window.MTGAIWizard — so
 * load order versus the wizard modules doesn't matter.
 */
(function () {
  'use strict';
  const D = (window.MTGAIDialog = window.MTGAIDialog || {});

  function escHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
  }

  // escHtml escapes < > & but NOT quotes; attribute values (input value,
  // aria-label) live in double-quoted attrs, so they also need " escaped.
  function escAttr(text) {
    return escHtml(text).replace(/"/g, '&quot;');
  }

  let dialogSeq = 0;

  let stylesInjected = false;
  function injectStyles() {
    if (stylesInjected) return;
    stylesInjected = true;
    const style = document.createElement('style');
    style.id = 'mtgai-dialog-styles';
    style.textContent = `
      .mtgai-dialog-message { white-space: pre-line; }
      .mtgai-dialog-input {
        width: 100%;
        box-sizing: border-box;
        margin-top: 0.75rem;
        padding: 0.5rem 0.6rem;
        background: #0f1830;
        border: 1px solid #2a3050;
        border-radius: 6px;
        color: #e0e0e0;
        font-family: inherit;
        font-size: 0.9rem;
      }
      .mtgai-dialog-input:focus {
        outline: none;
        border-color: #4a9eff;
      }
    `;
    document.head.appendChild(style);
  }

  // kind: 'confirm' | 'alert' | 'prompt'. Resolves:
  //   confirm -> true (OK) / false (Cancel, Esc, backdrop)
  //   alert   -> undefined (only an OK button)
  //   prompt  -> the input string (OK) / null (Cancel, Esc, backdrop)
  function openDialog(kind, message, opts) {
    opts = opts || {};
    injectStyles();
    // Per-kind sentinels: `cancelled` on Cancel/Esc/backdrop, `okValue` on OK.
    const cancelled = kind === 'prompt' ? null : kind === 'alert' ? undefined : false;

    return new Promise(resolve => {
      const prevFocus = document.activeElement;
      const overlay = document.createElement('div');
      overlay.className = 'wiz-modal-overlay';
      overlay.dataset.modal = 'dialog';

      const showCancel = kind !== 'alert';
      const okLabel = opts.okLabel || (kind === 'alert' ? 'OK' : kind === 'prompt' ? 'OK' : 'Confirm');
      const cancelLabel = opts.cancelLabel || 'Cancel';
      // Name the dialog for screen readers: aria-labelledby the title when one
      // exists, else aria-label the message (mirrors openCascadeModal).
      const titleId = `mtgai-dialog-title-${++dialogSeq}`;
      const titleHtml = opts.title ? `<h2 id="${titleId}">${escHtml(opts.title)}</h2>` : '';
      const nameAttr = opts.title
        ? `aria-labelledby="${titleId}"`
        : `aria-label="${escAttr(message)}"`;
      const inputHtml = kind === 'prompt'
        ? `<input type="text" class="mtgai-dialog-input" data-testid="mtgai-dialog-input"
                  value="${escAttr(opts.defaultValue || '')}" />`
        : '';
      const cancelBtn = showCancel
        ? `<button type="button" class="wiz-btn-secondary" data-dialog-action="cancel"
                   data-testid="mtgai-dialog-cancel">${escHtml(cancelLabel)}</button>`
        : '';

      overlay.innerHTML = `
        <div class="wiz-modal" role="${kind === 'alert' ? 'alertdialog' : 'dialog'}"
             aria-modal="true" ${nameAttr}>
          ${titleHtml}
          <p class="mtgai-dialog-message">${escHtml(message)}</p>
          ${inputHtml}
          <div class="wiz-modal-actions">
            ${cancelBtn}
            <button type="button" class="wiz-btn-primary" data-dialog-action="ok"
                    data-testid="mtgai-dialog-ok">${escHtml(okLabel)}</button>
          </div>
        </div>
      `;
      document.body.appendChild(overlay);

      const input = overlay.querySelector('.mtgai-dialog-input');
      const okBtn = overlay.querySelector('[data-dialog-action="ok"]');
      const cancelBtnEl = overlay.querySelector('[data-dialog-action="cancel"]');

      function close(result) {
        overlay.removeEventListener('keydown', onKey, true);
        overlay.remove();
        if (prevFocus && typeof prevFocus.focus === 'function') {
          try { prevFocus.focus(); } catch (_) { /* element gone */ }
        }
        resolve(result);
      }
      function confirmResult() {
        const okValue = kind === 'prompt' ? (input ? input.value : '') : kind === 'alert' ? undefined : true;
        close(okValue);
      }
      // Tab cycles only the dialog's own controls (focus trap).
      function focusables() {
        return Array.from(
          overlay.querySelectorAll('input, button')
        ).filter(el => !el.disabled);
      }
      function onKey(e) {
        if (e.key === 'Escape') {
          e.stopPropagation();
          e.preventDefault();
          close(cancelled);
        } else if (e.key === 'Enter') {
          // In a prompt the input has focus; Enter submits. Elsewhere Enter = OK.
          e.stopPropagation();
          e.preventDefault();
          confirmResult();
        } else if (e.key === 'Tab') {
          const items = focusables();
          if (!items.length) return;
          const first = items[0];
          const last = items[items.length - 1];
          if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
          } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }

      overlay.addEventListener('keydown', onKey, true);
      overlay.addEventListener('click', e => { if (e.target === overlay) close(cancelled); });
      okBtn.addEventListener('click', confirmResult);
      if (cancelBtnEl) cancelBtnEl.addEventListener('click', () => close(cancelled));

      // Focus the input (prompt) or the primary button so Enter/Esc work at once.
      if (input) {
        input.focus();
        input.select();
      } else {
        okBtn.focus();
      }
    });
  }

  D.confirm = (message, opts) => openDialog('confirm', message, opts);
  D.alert = (message, opts) => openDialog('alert', message, opts);
  D.prompt = (message, defaultValue, opts) =>
    openDialog('prompt', message, Object.assign({ defaultValue: defaultValue || '' }, opts || {}));
})();
