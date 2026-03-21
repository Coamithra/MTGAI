// ==========================================================================
//  Review page JavaScript — Card Detail Modal
//  Handles modal open/close, navigation, card data population, and
//  decision sync between the grid radio buttons and the modal radios.
// ==========================================================================

// ---------------------------------------------------------------------------
//  Modal state
// ---------------------------------------------------------------------------
let currentModalIndex = -1;
let filteredCards = []; // Set by the gallery code that owns the card list

// ---------------------------------------------------------------------------
//  Public API — called from onclick handlers in card_modal.html
// ---------------------------------------------------------------------------

/**
 * Open the card detail modal for the card at `index` in filteredCards.
 * Adds a body scroll lock so the background doesn't scroll.
 */
function openModal(index) {
  if (!filteredCards.length) return;

  // Clamp index to valid range
  currentModalIndex = Math.max(0, Math.min(index, filteredCards.length - 1));

  var modal = document.getElementById('card-modal');
  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';

  populateModal(filteredCards[currentModalIndex]);
}

/**
 * Close the modal and restore body scrolling.
 */
function closeModal() {
  var modal = document.getElementById('card-modal');
  modal.style.display = 'none';
  document.body.style.overflow = '';
  currentModalIndex = -1;
}

/**
 * Navigate to the previous card (wraps around to the end).
 */
function prevCard() {
  if (!filteredCards.length) return;
  currentModalIndex =
    (currentModalIndex - 1 + filteredCards.length) % filteredCards.length;
  populateModal(filteredCards[currentModalIndex]);
}

/**
 * Navigate to the next card (wraps around to the start).
 */
function nextCard() {
  if (!filteredCards.length) return;
  currentModalIndex = (currentModalIndex + 1) % filteredCards.length;
  populateModal(filteredCards[currentModalIndex]);
}

// ---------------------------------------------------------------------------
//  Modal population
// ---------------------------------------------------------------------------

/**
 * Fill in every field inside the modal from a card data object.
 *
 * Expected card shape (from cards.json):
 *   collector_number, name, mana_cost, cmc, colors, color_identity,
 *   type_line, oracle_text, flavor_text, power, toughness, loyalty,
 *   rarity, set_code, render_path, art_path, mechanic_tags,
 *   is_reprint, design_notes
 */
function populateModal(card) {
  if (!card) return;

  // Navigation counter
  document.getElementById('modal-card-number').textContent =
    (currentModalIndex + 1) + ' / ' + filteredCards.length;

  // Card image: prefer render, then art, then placeholder
  var img = document.getElementById('modal-card-img');
  if (card.render_path) {
    img.src = card.render_path;
  } else if (card.art_path) {
    img.src = card.art_path;
  } else {
    img.src = '';
  }
  img.alt = card.name || 'Card image';

  // Name + mana cost
  document.getElementById('modal-card-name').textContent = card.name || '';
  document.getElementById('modal-mana-cost').innerHTML =
    formatManaCost(card.mana_cost);

  // Type line
  document.getElementById('modal-type-line').textContent =
    card.type_line || '';

  // Oracle text — preserve \n as line breaks
  var oracleEl = document.getElementById('modal-oracle-text');
  if (card.oracle_text) {
    oracleEl.innerHTML = escapeHtml(card.oracle_text)
      .replace(/\n/g, '<br>');
    oracleEl.style.display = '';
  } else {
    oracleEl.innerHTML = '';
    oracleEl.style.display = 'none';
  }

  // Flavor text
  var flavorEl = document.getElementById('modal-flavor-text');
  if (card.flavor_text) {
    flavorEl.innerHTML = escapeHtml(card.flavor_text)
      .replace(/\n/g, '<br>');
    flavorEl.style.display = '';
  } else {
    flavorEl.innerHTML = '';
    flavorEl.style.display = 'none';
  }

  // P/T or Loyalty
  var statsEl = document.getElementById('modal-stats');
  if (card.power != null && card.toughness != null) {
    statsEl.textContent = card.power + ' / ' + card.toughness;
    statsEl.style.display = '';
  } else if (card.loyalty != null) {
    statsEl.textContent = 'Loyalty: ' + card.loyalty;
    statsEl.style.display = '';
  } else {
    statsEl.textContent = '';
    statsEl.style.display = 'none';
  }

  // Rarity badge
  var rarityEl = document.getElementById('modal-rarity');
  var rarity = (card.rarity || 'common').toLowerCase();
  rarityEl.innerHTML =
    '<span class="badge badge-' + rarity + '">' +
    capitalize(rarity) + '</span>';

  // Collector number
  document.getElementById('modal-collector').textContent =
    card.collector_number || '';

  // Set code
  document.getElementById('modal-set-code').textContent =
    card.set_code || '';

  // Colors
  var colorsEl = document.getElementById('modal-colors');
  if (card.colors && card.colors.length) {
    colorsEl.innerHTML = card.colors
      .map(function (c) {
        return '<span class="badge badge-' + colorBadgeClass(c) + '">' +
          c + '</span>';
      })
      .join(' ');
  } else {
    colorsEl.innerHTML =
      '<span class="badge badge-colorless">C</span>';
  }

  // CMC
  document.getElementById('modal-cmc').textContent =
    card.cmc != null ? card.cmc : '';

  // Mechanic tags
  var mechRow = document.getElementById('modal-mechanic-row');
  var mechEl = document.getElementById('modal-mechanics');
  if (card.mechanic_tags && card.mechanic_tags.length) {
    mechEl.textContent = card.mechanic_tags.join(', ');
    mechRow.style.display = '';
  } else {
    mechRow.style.display = 'none';
  }

  // Reprint flag
  var reprintRow = document.getElementById('modal-reprint-row');
  var reprintEl = document.getElementById('modal-reprint');
  if (card.is_reprint) {
    reprintEl.textContent = 'Yes';
    reprintRow.style.display = '';
  } else {
    reprintRow.style.display = 'none';
  }

  // Design notes
  var notesRow = document.getElementById('modal-notes-row');
  var notesEl = document.getElementById('modal-design-notes');
  if (card.design_notes) {
    notesEl.textContent = card.design_notes;
    notesRow.style.display = '';
  } else {
    notesRow.style.display = 'none';
  }

  // Sync decision radios from grid -> modal
  syncDecisionToModal(card.collector_number);

  // Sync notes field from grid -> modal
  syncNotesToModal(card.collector_number);
}

// ---------------------------------------------------------------------------
//  Mana cost formatting
// ---------------------------------------------------------------------------

/**
 * Convert a mana cost string like "{2}{W}{U}" into styled spans.
 * Returns an HTML string.
 */
function formatManaCost(manaCost) {
  if (!manaCost) return '';
  return manaCost.replace(/\{([^}]+)\}/g, function (match, symbol) {
    var cls = 'mana-' + symbol.toLowerCase().replace('/', '');
    return '<span class="mana-symbol ' + cls + '">' +
      symbol + '</span>';
  });
}

// ---------------------------------------------------------------------------
//  Decision sync — grid <-> modal
// ---------------------------------------------------------------------------

/**
 * Read the grid's radio value for a card and check the matching modal radio.
 */
function syncDecisionToModal(collectorNumber) {
  if (!collectorNumber) return;

  // Grid radios have name="decision-<collector_number>"
  var gridName = 'decision-' + collectorNumber;
  var gridChecked = document.querySelector(
    'input[name="' + gridName + '"]:checked'
  );
  var value = gridChecked ? gridChecked.value : '';

  // Set the modal radio
  var modalRadios = document.querySelectorAll(
    'input[name="modal-decision"]'
  );
  modalRadios.forEach(function (radio) {
    radio.checked = (radio.value === value);
  });
}

/**
 * Read the grid's notes input for a card and populate the modal notes field.
 */
function syncNotesToModal(collectorNumber) {
  if (!collectorNumber) return;
  var gridNotes = document.getElementById('notes-' + collectorNumber);
  var modalNotes = document.getElementById('modal-notes-field');
  if (gridNotes && modalNotes) {
    modalNotes.value = gridNotes.value || '';
  } else if (modalNotes) {
    modalNotes.value = '';
  }
}

/**
 * When a modal radio changes, push the value back to the grid radio.
 */
function onModalDecisionChange(event) {
  if (currentModalIndex < 0 || !filteredCards.length) return;
  var card = filteredCards[currentModalIndex];
  if (!card) return;

  var gridName = 'decision-' + card.collector_number;
  var gridRadio = document.querySelector(
    'input[name="' + gridName + '"][value="' + event.target.value + '"]'
  );
  if (gridRadio) {
    gridRadio.checked = true;
    // Fire a change event so any grid listeners pick it up
    gridRadio.dispatchEvent(new Event('change', { bubbles: true }));
  }
}

/**
 * When the modal notes field changes, push the value back to the grid input.
 */
function onModalNotesChange(event) {
  if (currentModalIndex < 0 || !filteredCards.length) return;
  var card = filteredCards[currentModalIndex];
  if (!card) return;

  var gridNotes = document.getElementById('notes-' + card.collector_number);
  if (gridNotes) {
    gridNotes.value = event.target.value;
    // Fire input event so any grid listeners pick it up
    gridNotes.dispatchEvent(new Event('input', { bubbles: true }));
  }
}

// ---------------------------------------------------------------------------
//  Keyboard handling
// ---------------------------------------------------------------------------

document.addEventListener('keydown', function (event) {
  var modal = document.getElementById('card-modal');
  if (!modal || modal.style.display === 'none') return;

  switch (event.key) {
    case 'Escape':
      closeModal();
      event.preventDefault();
      break;
    case 'ArrowLeft':
      prevCard();
      event.preventDefault();
      break;
    case 'ArrowRight':
      nextCard();
      event.preventDefault();
      break;
  }
});

// ---------------------------------------------------------------------------
//  Click-outside-to-close
// ---------------------------------------------------------------------------

document.addEventListener('click', function (event) {
  var modal = document.getElementById('card-modal');
  if (!modal || modal.style.display === 'none') return;

  // If the click target IS the overlay (not the content inside it), close
  if (event.target === modal) {
    closeModal();
  }
});

// ---------------------------------------------------------------------------
//  Event listeners for modal controls
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', function () {
  // Modal decision radios -> sync back to grid
  var modalRadios = document.querySelectorAll(
    'input[name="modal-decision"]'
  );
  modalRadios.forEach(function (radio) {
    radio.addEventListener('change', onModalDecisionChange);
  });

  // Modal notes field -> sync back to grid
  var notesField = document.getElementById('modal-notes-field');
  if (notesField) {
    notesField.addEventListener('input', onModalNotesChange);
  }
});

// ---------------------------------------------------------------------------
//  Utility helpers
// ---------------------------------------------------------------------------

/** Escape HTML special characters to prevent XSS. */
function escapeHtml(text) {
  var div = document.createElement('div');
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
}

/** Capitalize first letter. */
function capitalize(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

/** Map a single-letter MTG color code to a badge CSS class name. */
function colorBadgeClass(colorCode) {
  var map = {
    'W': 'white',
    'U': 'blue',
    'B': 'black',
    'R': 'red',
    'G': 'green'
  };
  return map[colorCode] || 'colorless';
}

// ==========================================================================
//  Review page JavaScript — Gallery, Filters, and Submit
//  Manages the card grid, filter/sort state, decision tracking, and
//  review submission. Works alongside the modal code above.
// ==========================================================================

// ---------------------------------------------------------------------------
//  Gallery state
//  NOTE: `filteredCards` is declared at the top of this file (modal section).
//  NOTE: `escapeHtml` and `capitalize` are defined in the utility section above.
// ---------------------------------------------------------------------------
var allCards = [];        // All cards from server
var decisions = {};       // { collector_number: { action: 'ok', note: '' } }
var activeFilters = {
  colors: [],             // Active color filters (OR within)
  rarities: [],           // Active rarity filters (OR within)
  type: '',               // Type filter
  cmcs: [],               // Active CMC filters (OR within)
  show: 'all'             // 'all' or 'needs-decision'
};
var sortBy = 'collector_number';

// ---------------------------------------------------------------------------
//  Initialization
// ---------------------------------------------------------------------------

/**
 * Initialize the gallery with card data from the server.
 * Sets all decisions to 'ok' by default and renders the grid.
 */
function initGallery(cards) {
  allCards = cards;
  // Initialize all decisions to OK
  cards.forEach(function (card) {
    decisions[card.collector_number] = { action: 'ok', note: '' };
  });
  applyFiltersAndRender();
  updateCounts();
}

// ---------------------------------------------------------------------------
//  Filtering
// ---------------------------------------------------------------------------

/**
 * Apply all active filters + sort, then re-render the card grid.
 */
function applyFiltersAndRender() {
  filteredCards = allCards.filter(function (card) {
    // Color filter (OR within active colors)
    if (activeFilters.colors.length > 0) {
      var isMulti = card.color_identity.length > 1;
      var isColorless = card.color_identity.length === 0;
      var colorMatch = false;
      for (var i = 0; i < activeFilters.colors.length; i++) {
        var c = activeFilters.colors[i];
        if (c === 'M' && isMulti) colorMatch = true;
        else if (c === 'C' && isColorless) colorMatch = true;
        else if (card.color_identity.indexOf(c) !== -1) colorMatch = true;
      }
      if (!colorMatch) return false;
    }

    // Rarity filter
    if (activeFilters.rarities.length > 0) {
      if (activeFilters.rarities.indexOf(card.rarity) === -1) return false;
    }

    // Type filter
    if (activeFilters.type) {
      if (card.type_line.toLowerCase().indexOf(activeFilters.type.toLowerCase()) === -1) {
        return false;
      }
    }

    // CMC filter
    if (activeFilters.cmcs.length > 0) {
      var cmcMatch = false;
      for (var j = 0; j < activeFilters.cmcs.length; j++) {
        var cmcVal = activeFilters.cmcs[j];
        if (cmcVal === '6+') {
          if (card.cmc >= 6) cmcMatch = true;
        } else {
          if (card.cmc === parseInt(cmcVal, 10)) cmcMatch = true;
        }
      }
      if (!cmcMatch) return false;
    }

    // Show filter
    if (activeFilters.show === 'needs-decision') {
      var decision = decisions[card.collector_number];
      if (!decision || decision.action === 'ok') return false;
    }

    return true;
  });

  // Sort
  sortCards();

  // Render
  renderGrid();
  updateFilterCounts();
}

/**
 * Sort filteredCards in place based on the current sortBy value.
 */
function sortCards() {
  var rarityOrder = { common: 0, uncommon: 1, rare: 2, mythic: 3 };
  var colorOrder = { W: 0, U: 1, B: 2, R: 3, G: 4 };

  filteredCards.sort(function (a, b) {
    switch (sortBy) {
      case 'name':
        return a.name.localeCompare(b.name);
      case 'cmc':
        return (a.cmc - b.cmc) ||
          a.collector_number.localeCompare(b.collector_number);
      case 'rarity':
        return ((rarityOrder[a.rarity] || 0) - (rarityOrder[b.rarity] || 0)) ||
          a.collector_number.localeCompare(b.collector_number);
      case 'color': {
        var aColor = a.color_identity[0] || 'Z';
        var bColor = b.color_identity[0] || 'Z';
        var aOrd = colorOrder[aColor] !== undefined ? colorOrder[aColor] : 99;
        var bOrd = colorOrder[bColor] !== undefined ? colorOrder[bColor] : 99;
        return (aOrd - bOrd) ||
          a.collector_number.localeCompare(b.collector_number);
      }
      default:
        return a.collector_number.localeCompare(b.collector_number);
    }
  });
}

// ---------------------------------------------------------------------------
//  Grid rendering
// ---------------------------------------------------------------------------

/**
 * Clear and re-render the card grid from filteredCards.
 */
function renderGrid() {
  var grid = document.getElementById('card-grid');
  grid.innerHTML = '';

  filteredCards.forEach(function (card, index) {
    var tile = createCardTile(card, index);
    grid.appendChild(tile);
  });
}

/**
 * Create a single card tile DOM element.
 */
function createCardTile(card, index) {
  var tile = document.createElement('div');
  tile.className = 'card-tile';
  tile.dataset.collector = card.collector_number;

  // Card image: prefer render, then art, then placeholder
  var imgSrc = card.render_path || card.art_path || '';

  // Border color based on color identity
  var borderColor = getColorBorder(card.color_identity);
  if (borderColor) {
    tile.style.borderTopColor = borderColor;
    tile.style.borderTopWidth = '3px';
  }

  var decision = decisions[card.collector_number] || { action: 'ok', note: '' };

  var imageHtml;
  if (imgSrc) {
    imageHtml =
      '<div class="card-tile-image" onclick="openModal(' + index + ')">' +
        '<img src="' + escapeHtml(imgSrc) + '" alt="' + escapeHtml(card.name) +
        '" loading="lazy">' +
      '</div>';
  } else {
    imageHtml =
      '<div class="card-tile-image" onclick="openModal(' + index + ')">' +
        '<div class="card-placeholder" style="background: ' +
          (borderColor || 'var(--bg-card)') + '">' +
          '<span>' + escapeHtml(card.name) + '</span>' +
        '</div>' +
      '</div>';
  }

  var infoHtml =
    '<div class="card-tile-info">' +
      '<div class="card-name" title="' + escapeHtml(card.name) + '">' +
        escapeHtml(card.name) +
      '</div>' +
      '<div class="card-meta">' +
        escapeHtml(card.collector_number) + ' &middot; ' +
        card.rarity.charAt(0).toUpperCase() +
      '</div>' +
    '</div>';

  var radioHtml =
    '<div class="radio-group" data-collector="' + card.collector_number + '">' +
      '<label class="radio-label radio-ok decision-ok">' +
        '<input type="radio" name="decision-' + card.collector_number + '" value="ok" ' +
          (decision.action === 'ok' ? 'checked' : '') +
          ' onchange="onDecisionChange(\'' + card.collector_number + '\', \'ok\')">' +
        '<span>OK</span>' +
      '</label>' +
      '<label class="radio-label radio-remake decision-remake">' +
        '<input type="radio" name="decision-' + card.collector_number + '" value="remake" ' +
          (decision.action === 'remake' ? 'checked' : '') +
          ' onchange="onDecisionChange(\'' + card.collector_number + '\', \'remake\')">' +
        '<span>Remake</span>' +
      '</label>' +
      '<label class="radio-label radio-art-redo decision-art">' +
        '<input type="radio" name="decision-' + card.collector_number + '" value="art_redo" ' +
          (decision.action === 'art_redo' ? 'checked' : '') +
          ' onchange="onDecisionChange(\'' + card.collector_number + '\', \'art_redo\')">' +
        '<span>Art</span>' +
      '</label>' +
      '<label class="radio-label radio-tweak decision-tweak">' +
        '<input type="radio" name="decision-' + card.collector_number + '" value="manual_tweak" ' +
          (decision.action === 'manual_tweak' ? 'checked' : '') +
          ' onchange="onDecisionChange(\'' + card.collector_number + '\', \'manual_tweak\')">' +
        '<span>Tweak</span>' +
      '</label>' +
    '</div>';

  var notesHtml =
    '<input type="text" class="card-notes" id="notes-' + card.collector_number + '" ' +
      'placeholder="Notes..." value="' + escapeHtml(decision.note || '') + '" ' +
      'onchange="onNotesChange(\'' + card.collector_number + '\', this.value)">';

  tile.innerHTML = imageHtml + infoHtml + radioHtml + notesHtml;

  return tile;
}

/**
 * Return a CSS color value for a card's color identity border.
 */
function getColorBorder(colorIdentity) {
  if (!colorIdentity || colorIdentity.length === 0) return 'var(--mtg-colorless)';
  if (colorIdentity.length > 1) return 'var(--mtg-gold)';
  var colorMap = {
    W: 'var(--mtg-white)',
    U: 'var(--mtg-blue)',
    B: 'var(--mtg-black)',
    R: 'var(--mtg-red)',
    G: 'var(--mtg-green)'
  };
  return colorMap[colorIdentity[0]] || 'var(--mtg-colorless)';
}

// ---------------------------------------------------------------------------
//  Decision handling
// ---------------------------------------------------------------------------

/**
 * Called when a grid radio button changes. Updates the decisions map
 * and syncs to the modal if it's open on that card.
 */
function onDecisionChange(collectorNumber, action) {
  if (!decisions[collectorNumber]) {
    decisions[collectorNumber] = { action: 'ok', note: '' };
  }
  decisions[collectorNumber].action = action;
  updateCounts();

  // If the modal is open and showing this card, sync the modal radios
  if (currentModalIndex >= 0 && filteredCards.length > 0) {
    var card = filteredCards[currentModalIndex];
    if (card && card.collector_number === collectorNumber) {
      syncDecisionToModal(collectorNumber);
    }
  }
}

/**
 * Called when a grid notes input changes. Updates the decisions map.
 */
function onNotesChange(collectorNumber, note) {
  if (!decisions[collectorNumber]) {
    decisions[collectorNumber] = { action: 'ok', note: '' };
  }
  decisions[collectorNumber].note = note;
}

/**
 * Recount all decisions and update the summary bar.
 */
function updateCounts() {
  var ok = 0, remake = 0, artRedo = 0, tweak = 0;
  var keys = Object.keys(decisions);
  for (var i = 0; i < keys.length; i++) {
    var d = decisions[keys[i]];
    switch (d.action) {
      case 'ok': ok++; break;
      case 'remake': remake++; break;
      case 'art_redo': artRedo++; break;
      case 'manual_tweak': tweak++; break;
    }
  }
  document.getElementById('count-ok').textContent = ok;
  document.getElementById('count-remake').textContent = remake;
  document.getElementById('count-art-redo').textContent = artRedo;
  document.getElementById('count-tweak').textContent = tweak;
}

/**
 * Update the "Showing X of Y" counter in the filter bar.
 */
function updateFilterCounts() {
  document.getElementById('showing-count').textContent = filteredCards.length;
  document.getElementById('total-count').textContent = allCards.length;
}

// ---------------------------------------------------------------------------
//  Filter event listeners
// ---------------------------------------------------------------------------

/**
 * Attach click/change listeners to all filter controls.
 * Called once on DOMContentLoaded.
 */
function setupFilterListeners() {
  // Toggle buttons: color
  document.querySelectorAll('.filter-btn[data-filter="color"]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      btn.classList.toggle('active');
      activeFilters.colors = getActiveValues('color');
      applyFiltersAndRender();
    });
  });

  // Toggle buttons: rarity
  document.querySelectorAll('.filter-btn[data-filter="rarity"]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      btn.classList.toggle('active');
      activeFilters.rarities = getActiveValues('rarity');
      applyFiltersAndRender();
    });
  });

  // Toggle buttons: CMC
  document.querySelectorAll('.filter-btn[data-filter="cmc"]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      btn.classList.toggle('active');
      activeFilters.cmcs = getActiveValues('cmc');
      applyFiltersAndRender();
    });
  });

  // Show filter (exclusive — only one active at a time)
  document.querySelectorAll('.filter-btn[data-filter="show"]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.filter-btn[data-filter="show"]').forEach(function (b) {
        b.classList.remove('active');
      });
      btn.classList.add('active');
      activeFilters.show = btn.dataset.value;
      applyFiltersAndRender();
    });
  });

  // Type dropdown
  var typeFilter = document.getElementById('type-filter');
  if (typeFilter) {
    typeFilter.addEventListener('change', function (e) {
      activeFilters.type = e.target.value;
      applyFiltersAndRender();
    });
  }

  // Sort dropdown
  var sortSelect = document.getElementById('sort-select');
  if (sortSelect) {
    sortSelect.addEventListener('change', function (e) {
      sortBy = e.target.value;
      applyFiltersAndRender();
    });
  }
}

/**
 * Collect data-value from all active filter buttons of a given type.
 */
function getActiveValues(filterType) {
  var buttons = document.querySelectorAll(
    '.filter-btn[data-filter="' + filterType + '"].active'
  );
  var values = [];
  buttons.forEach(function (btn) {
    values.push(btn.dataset.value);
  });
  return values;
}

// ---------------------------------------------------------------------------
//  Submit review
// ---------------------------------------------------------------------------

/**
 * POST the decisions map to the server and redirect on success.
 */
function submitReview() {
  var btn = document.getElementById('submit-btn');
  btn.disabled = true;
  btn.textContent = 'Submitting...';

  fetch('/api/review/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decisions: decisions })
  })
    .then(function (response) {
      if (!response.ok) {
        throw new Error('Server error: ' + response.status);
      }
      return response.json();
    })
    .then(function (result) {
      // Redirect to progress page on success
      window.location.href = '/progress';
    })
    .catch(function (error) {
      alert('Submit failed: ' + error.message);
      btn.disabled = false;
      btn.textContent = 'Submit Review';
    });
}

// ---------------------------------------------------------------------------
//  Gallery initialization on page load
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', function () {
  if (typeof ALL_CARDS !== 'undefined') {
    initGallery(ALL_CARDS);
    setupFilterListeners();
  }
});
