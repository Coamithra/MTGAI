/**
 * Model Registry page — read-only view of models.toml.
 *
 * Per-project model assignments + saved presets moved into the project's
 * Project Settings tab; this page renders the registry only.
 *
 * Globals from the template (declared in settings.html):
 *   MODEL_REGISTRY    — { llm: {key: {...}}, image: {key: {...}} }
 */

document.addEventListener('DOMContentLoaded', () => {
  renderRegistry();
});

function renderRegistry() {
  renderLLMRegistry();
  renderImageRegistry();
}

function renderLLMRegistry() {
  const tbody = document.getElementById('llm-registry-body');
  if (!tbody) return;

  const sorted = Object.entries(MODEL_REGISTRY.llm).sort((a, b) => b[1].tier - a[1].tier);
  const frag = document.createDocumentFragment();
  for (const [key, model] of sorted) {
    const tr = document.createElement('tr');
    tr.appendChild(codeCell(key));
    tr.appendChild(llmNameCell(model));
    tr.appendChild(textCell(model.provider, '#aaa'));
    tr.appendChild(llmPricingCell(model));
    tr.appendChild(textCell(String(model.tier), '#aaa'));
    frag.appendChild(tr);
  }
  tbody.replaceChildren(frag);
}

function renderImageRegistry() {
  const tbody = document.getElementById('image-registry-body');
  if (!tbody) return;

  const entries = Object.entries(MODEL_REGISTRY.image).sort((a, b) => {
    const ai = a[1].implemented ? 0 : 1;
    const bi = b[1].implemented ? 0 : 1;
    return ai - bi || a[1].name.localeCompare(b[1].name);
  });

  const frag = document.createDocumentFragment();
  for (const [key, model] of entries) {
    const tr = document.createElement('tr');
    tr.appendChild(codeCell(key));
    tr.appendChild(imageNameCell(model));
    tr.appendChild(textCell(model.provider, '#aaa'));
    tr.appendChild(imageCostCell(model));
    frag.appendChild(tr);
  }
  tbody.replaceChildren(frag);
}

function codeCell(text) {
  const td = document.createElement('td');
  const code = document.createElement('code');
  code.textContent = text;
  td.appendChild(code);
  return td;
}

function textCell(text, color) {
  const td = document.createElement('td');
  if (color) td.style.color = color;
  td.textContent = text;
  return td;
}

function tag(text, klass) {
  const span = document.createElement('span');
  span.className = `tag ${klass}`;
  span.textContent = text;
  return span;
}

function llmNameCell(model) {
  const td = document.createElement('td');
  td.appendChild(document.createTextNode(model.name));
  if (model.supports_vision) td.appendChild(tag('vision', 'tag-vision'));
  if (model.supports_effort) td.appendChild(tag('effort', 'tag-effort'));
  if (model.provider === 'llamacpp') td.appendChild(tag('local', 'tag-local'));
  return td;
}

function llmPricingCell(model) {
  const td = document.createElement('td');
  td.style.color = '#aaa';
  if (model.input_price > 0 || model.output_price > 0) {
    td.textContent = `$${model.input_price.toFixed(2)} / $${model.output_price.toFixed(2)}`;
  } else {
    const span = document.createElement('span');
    span.style.color = '#2ecc71';
    span.textContent = 'Free';
    td.appendChild(span);
  }
  return td;
}

function imageNameCell(model) {
  const td = document.createElement('td');
  td.appendChild(document.createTextNode(model.name));
  if (!model.implemented) td.appendChild(tag('not implemented', 'tag-placeholder'));
  if (model.provider === 'comfyui') td.appendChild(tag('local', 'tag-local'));
  return td;
}

function imageCostCell(model) {
  const td = document.createElement('td');
  td.style.color = '#aaa';
  if (model.cost_per_image > 0) {
    td.textContent = `$${model.cost_per_image.toFixed(3)}`;
  } else {
    const span = document.createElement('span');
    span.style.color = '#2ecc71';
    span.textContent = 'Free';
    td.appendChild(span);
  }
  return td;
}
