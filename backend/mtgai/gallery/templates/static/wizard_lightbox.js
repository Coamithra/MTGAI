/**
 * wizard_lightbox.js — shared click-to-zoom image pop-out (lightbox).
 *
 * The wizard's image grids (Art Generation & Review, Rendering & Final Review,
 * and any future grid) show art as small thumbnails. This module is the one
 * reusable surface for inspecting a piece at full scale — call it with a URL and
 * it overlays the image, centered, on a dark backdrop.
 *
 *   MTGAILightbox.open(src, opts?)  — open the overlay (src is the image URL)
 *   MTGAILightbox.open({ src, alt, caption })  — object form
 *   MTGAILightbox.close()           — close the active overlay (no-op if none)
 *
 * opts (all optional): { alt, caption }.
 *
 * Like wizard_dialog.js this is a DOM overlay, NEVER a native window: native
 * popups freeze page JS and are invisible to the claude-in-chrome QA driver (it
 * can only reach the DOM), and they're off-theme. It reuses the wizard's
 * .wiz-modal-overlay backdrop (dark, full-screen, focus-anchoring z-index) so it
 * tracks the theme for free; only the image frame + close button styling is
 * bespoke, injected once. It is focus-trapped (Tab stays on the close button,
 * Esc closes, backdrop click closes) and restores focus on close. The frame /
 * image / close control carry stable data-testid hooks for automation.
 *
 * Standalone by design — depends only on the DOM, not on window.MTGAIWizard — so
 * load order versus the wizard modules doesn't matter (loaded first, with
 * wizard_dialog.js).
 */
(function () {
  'use strict';
  const L = (window.MTGAILightbox = window.MTGAILightbox || {});

  function escHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
  }
  // escHtml escapes < > & but NOT quotes; attribute values need " escaped too.
  function escAttr(text) {
    return escHtml(text).replace(/"/g, '&quot;');
  }

  let stylesInjected = false;
  function injectStyles() {
    if (stylesInjected) return;
    stylesInjected = true;
    const style = document.createElement('style');
    style.id = 'mtgai-lightbox-styles';
    style.textContent = `
      .mtgai-lightbox-overlay { cursor: zoom-out; }
      .mtgai-lightbox-frame {
        position: relative;
        max-width: 92vw;
        max-height: 92vh;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 0.5rem;
        cursor: default;
      }
      .mtgai-lightbox-img {
        max-width: 92vw;
        max-height: 86vh;
        object-fit: contain;
        border-radius: 6px;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6);
        background: #06080f;
      }
      .mtgai-lightbox-caption {
        color: #cbd3e6;
        font-size: 0.82rem;
        text-align: center;
        max-width: 92vw;
      }
      .mtgai-lightbox-close {
        position: absolute;
        top: -0.6rem;
        right: -0.6rem;
        width: 1.9rem;
        height: 1.9rem;
        border-radius: 50%;
        border: 1px solid #2a3550;
        background: #16213e;
        color: #e0e0e0;
        font-size: 1.2rem;
        line-height: 1;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.5);
      }
      .mtgai-lightbox-close:hover { border-color: #4a9eff; color: #fff; }
      .mtgai-lightbox-close:focus { outline: none; border-color: #4a9eff; }
    `;
    document.head.appendChild(style);
  }

  // Single live overlay at a time (a second open() replaces the first).
  let active = null;

  function open(src, opts) {
    if (src && typeof src === 'object') {
      opts = src;
      src = opts.src;
    }
    opts = opts || {};
    if (!src) return;
    injectStyles();
    close();

    const prevFocus = document.activeElement;
    const overlay = document.createElement('div');
    overlay.className = 'wiz-modal-overlay mtgai-lightbox-overlay';
    overlay.dataset.modal = 'lightbox';
    overlay.setAttribute('data-testid', 'mtgai-lightbox');

    const name = opts.alt || opts.caption || 'Image preview';
    const captionHtml = opts.caption
      ? `<div class="mtgai-lightbox-caption">${escHtml(opts.caption)}</div>`
      : '';
    overlay.innerHTML = `
      <div class="mtgai-lightbox-frame" role="dialog" aria-modal="true"
           aria-label="${escAttr(name)}" data-testid="mtgai-lightbox-frame">
        <button type="button" class="mtgai-lightbox-close"
                data-testid="mtgai-lightbox-close" aria-label="Close">&times;</button>
        <img class="mtgai-lightbox-img" data-testid="mtgai-lightbox-img"
             src="${escAttr(src)}" alt="${escAttr(opts.alt || '')}">
        ${captionHtml}
      </div>
    `;
    document.body.appendChild(overlay);

    const closeBtn = overlay.querySelector('.mtgai-lightbox-close');

    // Tab cycles only the overlay's own controls (focus trap) — today that's
    // just the close button, but cycle the list (like wizard_dialog.js) so the
    // trap stays correct if the frame ever gains controls.
    function focusables() {
      return Array.from(overlay.querySelectorAll('button, a[href], input')).filter(
        el => !el.disabled,
      );
    }
    function onKey(e) {
      if (e.key === 'Escape') {
        e.stopPropagation();
        e.preventDefault();
        close();
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
    overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
    closeBtn.addEventListener('click', close);

    overlay._cleanup = () => {
      overlay.removeEventListener('keydown', onKey, true);
      if (prevFocus && typeof prevFocus.focus === 'function') {
        try { prevFocus.focus(); } catch (_) { /* element gone */ }
      }
    };

    active = overlay;
    closeBtn.focus();
  }

  function close() {
    if (!active) return;
    const overlay = active;
    active = null;
    if (overlay._cleanup) overlay._cleanup();
    overlay.remove();
  }

  L.open = open;
  L.close = close;
})();
