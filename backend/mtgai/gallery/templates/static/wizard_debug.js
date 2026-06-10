/* QA/debug panel — loaded ONLY under `serve --debug` (see wizard.html guard).
 *
 * A floating, collapsible control surface that gives a self-driving QA bot (and
 * a human) one-click access to the debug endpoints in
 * `mtgai/pipeline/debug_routes.py`:
 *   - Quick project   -> POST /api/debug/quick-project (no file picker)
 *   - Seed to stage   -> POST /api/debug/seed-stage     (jump to any stage)
 *   - Open .mtg path  -> POST /api/debug/open-path
 *   - Save now        -> POST /api/debug/save-mtg
 *
 * Deliberately self-contained (no MTGAIWizard dependency) so it works on every
 * tab and can't be broken by a bug in the surface under test.
 */
(function () {
  'use strict';

  if (!window.MTGAI_DEBUG) return;

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) Object.entries(attrs).forEach(([k, v]) => {
      if (k === 'style') node.style.cssText = v;
      else if (k === 'text') node.textContent = v;
      else node.setAttribute(k, v);
    });
    (children || []).forEach((c) => node.appendChild(c));
    return node;
  }

  async function post(url, body) {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || `${resp.status}`);
    return data;
  }

  function setStatus(msg, isError) {
    const s = document.getElementById('qa-debug-status');
    if (s) {
      s.textContent = msg;
      s.style.color = isError ? '#ff6b6b' : '#7CFC9B';
    }
  }

  function render(state) {
    const PANEL_BG = '#15161a';
    const wrap = el('div', {
      id: 'qa-debug-panel',
      style:
        'position:fixed;bottom:12px;right:12px;z-index:99999;width:300px;' +
        'background:' + PANEL_BG + ';color:#e6e6e6;border:1px solid #3a3d46;' +
        'border-radius:8px;font:12px/1.4 system-ui,sans-serif;box-shadow:0 4px 18px rgba(0,0,0,.5);',
    });

    const header = el('div', {
      style:
        'display:flex;align-items:center;justify-content:space-between;padding:8px 10px;' +
        'cursor:pointer;background:#1d1f25;border-radius:8px 8px 0 0;user-select:none;',
    });
    header.appendChild(el('span', { text: '🐛 QA Debug', style: 'font-weight:600;' }));
    const toggle = el('span', { text: '▾', style: 'opacity:.7;' });
    header.appendChild(toggle);

    const body = el('div', { style: 'padding:10px;display:flex;flex-direction:column;gap:10px;' });

    // --- Quick project --------------------------------------------------
    const qpCode = el('input', { type: 'text', value: 'QA', placeholder: 'set code', style: inputCss() });
    const qpSize = el('input', { type: 'number', value: '60', min: '10', max: '720', style: inputCss() });
    const qpPrefab = el('input', { type: 'checkbox' });
    qpPrefab.checked = true;
    const qpTheme = el('textarea', {
      placeholder: 'optional theme prose (enables extraction)…',
      style: inputCss() + 'height:48px;resize:vertical;',
    });
    const qpBtn = el('button', { text: 'Quick project', style: btnCss() });
    qpBtn.onclick = async () => {
      qpBtn.disabled = true;
      try {
        const data = await post('/api/debug/quick-project', {
          set_code: qpCode.value, set_size: Number(qpSize.value),
          prefab: qpPrefab.checked, theme_text: qpTheme.value,
        });
        setStatus('Created ' + data.set_code + ' → navigating…');
        window.location.href = data.navigate;
      } catch (e) { setStatus('Quick project: ' + e.message, true); }
      finally { qpBtn.disabled = false; }
    };
    // "prefab assets exist on disk" — distinct from the active project's actual
    // use_prefab_* settings (shown in the footer). Placed here, next to the
    // quick-project prefab checkbox, where availability is what's relevant.
    const qpAvail = el('div', {
      text:
        'prefab assets: cards ' + (state.prefab_cards ? 'available' : 'missing') +
        ', mech ' + (state.prefab_mechanics ? 'available' : 'missing'),
      style: 'font-size:10px;opacity:.6;',
    });
    body.appendChild(section('Quick project (no picker)', [
      row([labelled('code', qpCode), labelled('size', qpSize)]),
      row([labelled('prefab cards/mechanics', qpPrefab)]),
      qpAvail, qpTheme, qpBtn,
    ]));

    // --- Seed to stage --------------------------------------------------
    const srcSel = el('select', { style: inputCss() });
    if (!state.golden_candidates.length) {
      srcSel.appendChild(el('option', { value: '', text: '(no golden project found)' }));
    }
    state.golden_candidates.forEach((c, i) => {
      const o = el('option', { value: c.path, text: c.name + (i === 0 ? ' (newest)' : '') });
      srcSel.appendChild(o);
    });
    const stageSel = el('select', { style: inputCss() });
    state.stages.forEach((s) => {
      stageSel.appendChild(el('option', { value: s.stage_id, text: s.display_name }));
    });
    const seedBtn = el('button', { text: 'Seed → jump to stage', style: btnCss() });
    seedBtn.onclick = async () => {
      seedBtn.disabled = true;
      try {
        const data = await post('/api/debug/seed-stage', {
          target_stage: stageSel.value, source_dir: srcSel.value || undefined,
        });
        setStatus('Seeded to ' + data.target_stage + ' → navigating…');
        window.location.href = data.navigate;
      } catch (e) { setStatus('Seed: ' + e.message, true); }
      finally { seedBtn.disabled = false; }
    };
    body.appendChild(section('Seed to stage (skip slow phases)', [
      labelled('source', srcSel), labelled('stage', stageSel), seedBtn,
    ]));

    // --- Open path / Save now ------------------------------------------
    const openInput = el('input', { type: 'text', placeholder: 'server path to .mtg or folder', style: inputCss() });
    const openBtn = el('button', { text: 'Open path', style: btnCss() });
    openBtn.onclick = async () => {
      try {
        const data = await post('/api/debug/open-path', { path: openInput.value });
        setStatus('Opened ' + data.set_code + ' → reloading…');
        window.location.href = '/pipeline';
      } catch (e) { setStatus('Open: ' + e.message, true); }
    };
    const saveBtn = el('button', { text: 'Save .mtg now', style: btnCss() });
    saveBtn.onclick = async () => {
      try {
        const data = await post('/api/debug/save-mtg', {});
        setStatus('Saved ' + data.path);
      } catch (e) { setStatus('Save: ' + e.message, true); }
    };
    body.appendChild(section('Open / Save', [openInput, openBtn, saveBtn]));

    // --- Status + meta --------------------------------------------------
    // The footer reports the ACTIVE project's real use_prefab_* settings (does
    // the live run actually use prefab?), NOT prefab availability on disk (which
    // lives near the quick-project checkbox above). They are different signals.
    const meta = el('div', { style: 'font-size:11px;opacity:.7;' });
    if (state.active) {
      meta.textContent =
        'active: ' + (state.active.set_code || '(unnamed)') +
        ' · uses prefab cards:' + (state.active.use_prefab_cards ? '✓' : '✗') +
        ' mech:' + (state.active.use_prefab_mechanics ? '✓' : '✗');
    } else {
      meta.textContent = 'active: none';
    }
    body.appendChild(meta);
    body.appendChild(el('div', { id: 'qa-debug-status', style: 'font-size:11px;min-height:14px;color:#7CFC9B;' }));

    let collapsed = false;
    header.onclick = () => {
      collapsed = !collapsed;
      body.style.display = collapsed ? 'none' : 'flex';
      toggle.textContent = collapsed ? '▸' : '▾';
    };

    wrap.appendChild(header);
    wrap.appendChild(body);
    return wrap;
  }

  function inputCss() {
    return 'width:100%;box-sizing:border-box;background:#0e0f12;color:#e6e6e6;' +
      'border:1px solid #3a3d46;border-radius:4px;padding:4px 6px;font:12px system-ui;';
  }
  function btnCss() {
    return 'width:100%;background:#2d6cdf;color:#fff;border:0;border-radius:4px;' +
      'padding:6px;cursor:pointer;font:12px/1 system-ui;font-weight:600;';
  }
  function row(children) {
    return el('div', { style: 'display:flex;gap:6px;align-items:center;' }, children);
  }
  function labelled(text, control) {
    const lab = el('label', { style: 'display:flex;flex-direction:column;gap:2px;flex:1;font-size:11px;opacity:.85;' });
    lab.appendChild(document.createTextNode(text));
    lab.appendChild(control);
    return lab;
  }
  function section(title, children) {
    const sec = el('div', { style: 'display:flex;flex-direction:column;gap:6px;border-top:1px solid #2a2c33;padding-top:8px;' });
    sec.appendChild(el('div', { text: title, style: 'font-weight:600;font-size:11px;opacity:.9;' }));
    children.forEach((c) => sec.appendChild(c));
    return sec;
  }

  async function init() {
    let state;
    try {
      const resp = await fetch('/api/debug/state');
      state = await resp.json();
    } catch (e) {
      return; // debug routes not mounted — stay silent
    }
    if (!state || !state.enabled) return;
    if (document.getElementById('qa-debug-panel')) return;
    document.body.appendChild(render(state));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
