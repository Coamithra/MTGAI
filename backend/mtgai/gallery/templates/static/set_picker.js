/**
 * Top-bar active-set picker.
 *
 * Renders into the `#set-picker` slot in base.html. Hydrates the
 * dropdown from `available_sets` in /api/runtime/state, switches the
 * active set on change (+ full reload to re-render server templates),
 * and handles the "+ New set..." flow via a small modal.
 */

(function () {
  'use strict';

  const NEW_SET_VALUE = '__new__';

  function escapeHtml(text) {
    if (text == null) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
  }

  function optionLabel(entry) {
    if (entry.name) return entry.code + ' — ' + entry.name;
    return entry.code;
  }

  function renderPicker(slot, state) {
    const sets = (state && state.available_sets) || [];
    const active = (state && state.active_set) || '';
    const activeKnown = sets.some((s) => s.code === active);

    const options = sets
      .map(
        (s) =>
          `<option value="${escapeHtml(s.code)}"${s.code === active ? ' selected' : ''}>${escapeHtml(optionLabel(s))}</option>`,
      )
      .join('');

    // When the persisted active set is gone (deleted on disk) but
    // others exist, surface a stale-pointer marker so the user has a
    // visible cue rather than a silently-wrong selection.
    const stalePlaceholder =
      active && !activeKnown && sets.length > 0
        ? `<option value="" disabled selected>${escapeHtml(active)} (missing)</option>`
        : '';

    // No sets at all — only the new-set entry, no stale placeholder.
    const emptyPlaceholder =
      sets.length === 0
        ? `<option value="" disabled selected>No sets — create one</option>`
        : '';

    slot.innerHTML = `
      <label class="set-picker-label" for="set-picker-select">Set</label>
      <select id="set-picker-select" class="set-picker-select">
        ${stalePlaceholder}
        ${emptyPlaceholder}
        ${options}
        <option value="${NEW_SET_VALUE}">+ New set...</option>
      </select>
    `;

    const select = slot.querySelector('#set-picker-select');
    select.addEventListener('change', onPickerChange);
  }

  async function onPickerChange(event) {
    const select = event.target;
    const value = select.value;

    if (value === NEW_SET_VALUE) {
      openNewSetModal();
      // Restore the previous selection visually until the modal resolves.
      const active = (window.MtgaiState && window.MtgaiState.setCode()) || '';
      select.value = active || '';
      return;
    }

    if (!value) return;

    select.disabled = true;
    const result = await window.MtgaiState.activateSet(value);
    if (result && result.active_set) {
      window.location.reload();
    } else {
      select.disabled = false;
      alert('Failed to switch set. Check the server log.');
    }
  }

  // ---------------------------------------------------------------
  // New-set modal
  // ---------------------------------------------------------------

  function openNewSetModal() {
    closeNewSetModal();
    const overlay = document.createElement('div');
    overlay.className = 'set-picker-modal-overlay';
    overlay.id = 'set-picker-modal';
    overlay.innerHTML = `
      <div class="set-picker-modal">
        <h2>Create New Set</h2>
        <p class="set-picker-modal-desc">
          The set code becomes the directory name under output/sets.
          Use 2–5 uppercase letters or digits.
        </p>
        <label for="set-picker-modal-code">Set Code</label>
        <input type="text" id="set-picker-modal-code"
               maxlength="5" placeholder="e.g. ASD"
               style="text-transform: uppercase;">
        <label for="set-picker-modal-name">Set Name (optional)</label>
        <input type="text" id="set-picker-modal-name"
               placeholder="e.g. Anomalous Descent">
        <div class="set-picker-modal-error" id="set-picker-modal-error"></div>
        <div class="set-picker-modal-actions">
          <button type="button" class="btn" id="set-picker-modal-cancel">Cancel</button>
          <button type="button" class="btn-primary" id="set-picker-modal-submit">Create &amp; Activate</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    const codeEl = overlay.querySelector('#set-picker-modal-code');
    codeEl.focus();
    overlay.querySelector('#set-picker-modal-cancel').addEventListener('click', closeNewSetModal);
    overlay.querySelector('#set-picker-modal-submit').addEventListener('click', submitNewSet);
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeNewSetModal();
    });
    document.addEventListener('keydown', escCloseNewSetModal);
  }

  function escCloseNewSetModal(e) {
    if (e.key === 'Escape') closeNewSetModal();
  }

  function closeNewSetModal() {
    const overlay = document.getElementById('set-picker-modal');
    if (overlay) overlay.remove();
    document.removeEventListener('keydown', escCloseNewSetModal);
  }

  async function submitNewSet() {
    const codeEl = document.getElementById('set-picker-modal-code');
    const nameEl = document.getElementById('set-picker-modal-name');
    const errEl = document.getElementById('set-picker-modal-error');
    const submit = document.getElementById('set-picker-modal-submit');
    if (!codeEl || !errEl || !submit) return;

    const code = (codeEl.value || '').trim().toUpperCase();
    const name = (nameEl.value || '').trim();
    errEl.textContent = '';

    if (!/^[A-Z0-9]{2,5}$/.test(code)) {
      errEl.textContent = 'Set code must be 2–5 uppercase letters or digits.';
      codeEl.focus();
      return;
    }

    submit.disabled = true;
    submit.textContent = 'Creating...';
    const result = await window.MtgaiState.createSet(code, name || null);
    if (result && result.active_set) {
      window.location.reload();
      return;
    }
    if (result && result.error) {
      errEl.textContent = result.error;
    } else {
      errEl.textContent = 'Failed to create set. Check the server log.';
    }
    submit.disabled = false;
    submit.textContent = 'Create & Activate';
  }

  // ---------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------

  document.addEventListener('DOMContentLoaded', async () => {
    const slot = document.getElementById('set-picker');
    if (!slot || !window.MtgaiState) return;

    const state = await window.MtgaiState.fetchRuntimeState();
    if (state && state.active_set) {
      window.MtgaiState.setSetCode(state.active_set);
    }
    renderPicker(slot, state || { available_sets: [], active_set: '' });
  });
})();
