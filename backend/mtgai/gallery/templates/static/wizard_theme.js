/**
 * Wizard theme tab — content-only editor.
 *
 * Per design §8.3, the Theme tab keeps the constraint + card-request
 * + setting-prose surfaces but **drops the upload widget and any
 * numeric set-shape fields**. Upload moves to Project Settings in
 * the next card; set_name / set_size / mechanic_count are preserved
 * round-trip from the loaded theme.json without surfacing an editor
 * here (they'll land on Project Settings too).
 *
 * Refresh-AI on individual sections is intentionally **not wired**
 * in this card — the AI lock + section refresh round-trip should
 * land alongside Project Settings since they share UX (model picker,
 * cost confirmation). Buttons render disabled with a tooltip.
 */

(function () {
  'use strict';

  const W = (window.MTGAIWizard = window.MTGAIWizard || {});
  W.registerTabRenderer('content', renderThemeTab);

  // Module-scope flag: the theme tab body is mounted once per page
  // load. The wizard shell never re-mounts a tab body in this card
  // (set-picker switches reload the page), so a one-shot guard is
  // sufficient. If a future card adds in-place re-bootstrapping it
  // should track this on the tab body element instead.
  const local = {
    initialized: false,
  };

  function renderThemeTab({ root, state }) {
    if (local.initialized) return;
    local.initialized = true;

    const content = root.querySelector('[data-role="content"]');
    const footer = root.querySelector('[data-role="footer"]');
    if (!content) return;

    content.innerHTML = themeBodyHtml();
    if (footer) {
      footer.innerHTML = `<span class="wiz-footer-note">Auto-advance + Next-step button land in a follow-up card.</span>`;
    }

    bindThemeBody(state);
  }

  function themeBodyHtml() {
    return `
      <div class="wiz-theme-section">
        <h3>Setting</h3>
        <p class="wiz-theme-section-desc">
          Prose describing your world. Feeds card generation, mechanics, art prompts.
          Edit / preview toggle below.
        </p>
        <div class="wiz-theme-toolbar">
          <button type="button" class="wiz-theme-mode-btn" data-mode="edit">Edit</button>
          <button type="button" class="wiz-theme-mode-btn active" data-mode="preview">Preview</button>
        </div>
        <textarea class="wiz-setting-textarea" id="wiz-setting" rows="16"
          style="display:none"
          placeholder="Setting prose lives here. Once Project Settings tab ships you'll be able to upload / paste from there."></textarea>
        <div class="wiz-setting-preview" id="wiz-setting-preview"></div>
      </div>

      <div class="wiz-theme-section">
        <div class="wiz-theme-section-header-row">
          <h3>Set Constraints</h3>
        </div>
        <p class="wiz-theme-section-desc">
          Structural directives for the skeleton + card generation. Things like
          artifact density, color balance, card-type minimums.
        </p>
        <div class="wiz-list-items" id="wiz-constraints-list"></div>
        <button type="button" class="wiz-btn-add" id="wiz-add-constraint">+ Add constraint</button>
      </div>

      <div class="wiz-theme-section">
        <div class="wiz-theme-section-header-row">
          <h3>Card Requests</h3>
        </div>
        <p class="wiz-theme-section-desc">
          Cards you definitely want in the set — natural-language descriptions
          that get reserved slots in the skeleton.
        </p>
        <div class="wiz-list-items" id="wiz-card-requests-list"></div>
        <button type="button" class="wiz-btn-add" id="wiz-add-card-request">+ Add card request</button>
      </div>

      <div class="wiz-theme-actions">
        <button type="button" class="wiz-btn-primary" id="wiz-save-theme">Save Theme</button>
      </div>
    `;
  }

  function bindThemeBody(state) {
    const theme = state.theme || {};
    const setting = readSettingProse(theme);
    document.getElementById('wiz-setting').value = setting;

    document.querySelectorAll('.wiz-theme-mode-btn').forEach(btn => {
      btn.addEventListener('click', () => setSettingMode(btn.dataset.mode));
    });

    populateConstraints(theme.constraints || theme.special_constraints || []);
    populateCardRequests(theme.card_requests || []);

    document.getElementById('wiz-add-constraint').addEventListener('click', () => addConstraint('', false));
    document.getElementById('wiz-add-card-request').addEventListener('click', () => addCardRequest('', false));
    document.getElementById('wiz-save-theme').addEventListener('click', () => saveTheme(state));

    setSettingMode('preview');
  }

  function readSettingProse(theme) {
    if (theme.setting) return theme.setting;
    const parts = [];
    if (theme.theme) parts.push(theme.theme);
    if (theme.flavor_description) parts.push(theme.flavor_description);
    return parts.join('\n\n');
  }

  function setSettingMode(mode) {
    const textarea = document.getElementById('wiz-setting');
    const preview = document.getElementById('wiz-setting-preview');
    if (!textarea || !preview) return;
    document.querySelectorAll('.wiz-theme-mode-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === mode);
    });
    if (mode === 'edit') {
      textarea.style.display = '';
      preview.style.display = 'none';
    } else {
      renderSettingPreview();
      textarea.style.display = 'none';
      preview.style.display = '';
    }
  }

  function renderSettingPreview() {
    const textarea = document.getElementById('wiz-setting');
    const preview = document.getElementById('wiz-setting-preview');
    if (!textarea || !preview) return;
    const text = textarea.value;
    if (!text.trim()) {
      preview.classList.add('empty');
      preview.textContent = 'No setting yet. Once the Project Settings tab ships, upload or paste prose from there.';
    } else {
      preview.classList.remove('empty');
      preview.innerHTML = renderMarkdown(text);
    }
  }

  // ------------------------------------------------------------------
  // Constraints + card requests
  // ------------------------------------------------------------------

  function populateConstraints(constraints) {
    const list = document.getElementById('wiz-constraints-list');
    list.innerHTML = '';
    if (!constraints.length) {
      addConstraint('', false);
      return;
    }
    for (const c of constraints) {
      const { text, source } = normalizeProvenance(c);
      addConstraint(text, source === 'ai');
    }
  }

  function populateCardRequests(requests) {
    const list = document.getElementById('wiz-card-requests-list');
    list.innerHTML = '';
    if (!requests.length) {
      addCardRequest('', false);
      return;
    }
    for (const r of requests) {
      const { text, source } = normalizeProvenance(r);
      addCardRequest(text, source === 'ai');
    }
  }

  function addConstraint(value, aiGenerated) {
    const list = document.getElementById('wiz-constraints-list');
    const item = document.createElement('div');
    item.className = 'wiz-list-item';
    if (aiGenerated) item.dataset.aiGenerated = 'true';
    const badge = aiGenerated ? '<span class="wiz-ai-badge">AI</span>' : '';
    item.innerHTML = `
      <input type="text" placeholder="e.g. Artifact subtheme — at least 6 artifact creatures"
             value="${escAttr(value || '')}">
      ${badge}
      <button type="button" class="wiz-btn-remove" title="Remove">&times;</button>
    `;
    list.appendChild(item);
    item.querySelector('input').addEventListener('input', () => clearAiBadge(item));
    item.querySelector('.wiz-btn-remove').addEventListener('click', () => item.remove());
    if (!value) item.querySelector('input').focus();
  }

  function addCardRequest(value, aiGenerated) {
    const list = document.getElementById('wiz-card-requests-list');
    const item = document.createElement('div');
    item.className = 'wiz-list-item';
    if (aiGenerated) item.dataset.aiGenerated = 'true';
    const badge = aiGenerated ? '<span class="wiz-ai-badge">AI</span>' : '';
    item.innerHTML = `
      <textarea rows="2"
        placeholder="e.g. Feretha's Throne — a legendary artifact that gains control of creatures">${escHtml(value || '')}</textarea>
      ${badge}
      <button type="button" class="wiz-btn-remove" title="Remove">&times;</button>
    `;
    list.appendChild(item);
    item.querySelector('textarea').addEventListener('input', () => clearAiBadge(item));
    item.querySelector('.wiz-btn-remove').addEventListener('click', () => item.remove());
    if (!value) item.querySelector('textarea').focus();
  }

  function clearAiBadge(item) {
    delete item.dataset.aiGenerated;
    const badge = item.querySelector('.wiz-ai-badge');
    if (badge) badge.remove();
  }

  function normalizeProvenance(item) {
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      const text = typeof item.text === 'string' ? item.text : '';
      const source = item.source === 'ai' ? 'ai' : 'human';
      return { text, source };
    }
    return { text: typeof item === 'string' ? item : '', source: 'human' };
  }

  // ------------------------------------------------------------------
  // Save
  // ------------------------------------------------------------------

  async function saveTheme(state) {
    const theme = state.theme || {};
    const setting = document.getElementById('wiz-setting').value.trim();

    if (!setting) {
      W.toast('Setting prose is empty. Add some text before saving.', 'error');
      setSettingMode('edit');
      document.getElementById('wiz-setting').focus();
      return;
    }

    const constraints = [];
    document.querySelectorAll('#wiz-constraints-list .wiz-list-item').forEach(item => {
      const input = item.querySelector('input');
      if (!input) return;
      const val = input.value.trim();
      if (!val) return;
      constraints.push({
        text: val,
        source: item.dataset.aiGenerated === 'true' ? 'ai' : 'human',
      });
    });

    const cardRequests = [];
    document.querySelectorAll('#wiz-card-requests-list .wiz-list-item').forEach(item => {
      const ta = item.querySelector('textarea');
      if (!ta) return;
      const val = ta.value.trim();
      if (!val) return;
      cardRequests.push({
        text: val,
        source: item.dataset.aiGenerated === 'true' ? 'ai' : 'human',
      });
    });

    // Round-trip every key from the loaded theme so save here only
    // mutates the content surface (setting prose + constraints + card
    // requests). Legacy keys (`special_constraints`, `theme`,
    // `flavor_description`) survive the save unchanged — Project
    // Settings + a future migration can drop them once that surface
    // covers the editor for those fields.
    const payload = {
      ...theme,
      name: theme.name ?? '',
      code: state.activeSet,
      set_size: theme.set_size ?? 60,
      mechanic_count: theme.mechanic_count ?? 3,
      setting,
      constraints,
      card_requests: cardRequests,
    };

    const btn = document.getElementById('wiz-save-theme');
    btn.disabled = true;
    btn.textContent = 'Saving…';

    try {
      const resp = await fetch('/api/pipeline/theme/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const result = await resp.json();
      if (result.success) {
        state.theme = payload;
        W.toast(`Theme saved for ${payload.code}`, 'success');
      } else {
        W.toast('Error: ' + (result.error || 'Unknown'), 'error');
      }
    } catch (err) {
      W.toast('Network error: ' + err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Save Theme';
    }
  }

  // ------------------------------------------------------------------
  // Markdown — zero-dep subset (mirrors theme.js's renderer)
  // ------------------------------------------------------------------

  function renderMarkdown(src) {
    if (!src) return '';
    const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const inline = (s) => esc(s)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
    const lines = src.split(/\r?\n/);
    const out = [];
    let para = [];
    let listItems = [];
    const flushPara = () => {
      if (para.length) {
        out.push('<p>' + inline(para.join(' ')) + '</p>');
        para = [];
      }
    };
    const flushList = () => {
      if (listItems.length) {
        out.push('<ul>' + listItems.map((l) => '<li>' + inline(l) + '</li>').join('') + '</ul>');
        listItems = [];
      }
    };
    for (const raw of lines) {
      const line = raw.replace(/\s+$/, '');
      if (!line.trim()) { flushPara(); flushList(); continue; }
      const heading = line.match(/^(#{1,6})\s+(.+)$/);
      if (heading) {
        flushPara(); flushList();
        const lvl = Math.min(6, Math.max(1, heading[1].length));
        out.push(`<h${lvl}>${inline(heading[2])}</h${lvl}>`);
        continue;
      }
      const bullet = line.match(/^[-*]\s+(.+)$/);
      if (bullet) { flushPara(); listItems.push(bullet[1]); continue; }
      flushList();
      para.push(line);
    }
    flushPara(); flushList();
    return out.join('\n');
  }

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------

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
