// ==========================================================================
//  Booster Pack Viewer — JavaScript
//  Generates and displays randomized booster packs with stats sidebar.
// ==========================================================================

// ---------------------------------------------------------------------------
//  State
// ---------------------------------------------------------------------------
var boosterCards = [];     // All cards from the server (ALL_CARDS)
var currentPack = [];      // Currently displayed pack

// Set mechanics to detect in oracle text
var SET_MECHANICS = ['Salvage', 'Malfunction', 'Overclock'];

// Rarity sort order for pack display (rare/mythic first, like opening a real pack)
var RARITY_ORDER = { mythic: 0, rare: 1, uncommon: 2, common: 3 };

// ---------------------------------------------------------------------------
//  Initialization
// ---------------------------------------------------------------------------

/**
 * Initialize with all cards data. Generate and display first pack.
 */
function initBooster(cards) {
  boosterCards = cards;
  openNewPack();
}

// ---------------------------------------------------------------------------
//  Pack generation — server or client-side fallback
// ---------------------------------------------------------------------------

/**
 * Called when "Open New Pack" button is clicked.
 * Fetches from /api/booster, falls back to client-side generation.
 */
function openNewPack() {
  var seed = Math.floor(Math.random() * 2147483647);
  var seedEl = document.getElementById('pack-seed');
  if (seedEl) seedEl.textContent = 'Seed: ' + seed;

  fetch('/api/booster?seed=' + seed)
    .then(function (response) {
      if (!response.ok) throw new Error('Server error: ' + response.status);
      return response.json();
    })
    .then(function (packCards) {
      if (packCards.error) throw new Error(packCards.error);
      currentPack = packCards;
      renderPack(currentPack);
      renderPackStats(currentPack);
    })
    .catch(function (err) {
      console.warn('Booster API unavailable, using client-side generation:', err.message);
      currentPack = generatePackClientSide(boosterCards);
      renderPack(currentPack);
      renderPackStats(currentPack);
    });
}

// ---------------------------------------------------------------------------
//  Client-side fallback pack generation
// ---------------------------------------------------------------------------

/**
 * Pick `count` random items from an array without duplicates.
 */
function pickRandom(arr, count) {
  var shuffled = arr.slice();
  for (var i = shuffled.length - 1; i > 0; i--) {
    var j = Math.floor(Math.random() * (i + 1));
    var tmp = shuffled[i];
    shuffled[i] = shuffled[j];
    shuffled[j] = tmp;
  }
  return shuffled.slice(0, Math.min(count, shuffled.length));
}

/**
 * Generate a booster pack client-side from ALL_CARDS.
 * Standard distribution: 10 commons, 3 uncommons, 1 rare/mythic, 1 basic land.
 */
function generatePackClientSide(cards) {
  var commons = cards.filter(function (c) { return c.rarity === 'common' && !isBasicLand(c); });
  var uncommons = cards.filter(function (c) { return c.rarity === 'uncommon'; });
  var rares = cards.filter(function (c) { return c.rarity === 'rare'; });
  var mythics = cards.filter(function (c) { return c.rarity === 'mythic'; });
  var lands = cards.filter(function (c) { return isBasicLand(c); });

  var pack = [];

  // 1 rare (1/8 chance mythic upgrade)
  if (mythics.length > 0 && Math.random() < 0.125) {
    pack.push(pickRandom(mythics, 1)[0]);
  } else if (rares.length > 0) {
    pack.push(pickRandom(rares, 1)[0]);
  } else if (mythics.length > 0) {
    pack.push(pickRandom(mythics, 1)[0]);
  }

  // 3 uncommons
  pack.push.apply(pack, pickRandom(uncommons, 3));

  // 10 commons
  pack.push.apply(pack, pickRandom(commons, 10));

  // 1 basic land
  if (lands.length > 0) {
    pack.push(pickRandom(lands, 1)[0]);
  }

  // Sort by rarity (rare/mythic first, land last)
  pack.sort(function (a, b) {
    var aOrd = isBasicLand(a) ? 4 : (RARITY_ORDER[a.rarity] || 3);
    var bOrd = isBasicLand(b) ? 4 : (RARITY_ORDER[b.rarity] || 3);
    return aOrd - bOrd;
  });

  return pack;
}

/**
 * Check if a card is a basic land.
 */
function isBasicLand(card) {
  return card.type_line && card.type_line.indexOf('Basic Land') !== -1;
}

// ---------------------------------------------------------------------------
//  Pack rendering
// ---------------------------------------------------------------------------

/**
 * Display the 15 cards in the pack as a grid.
 * Cards are already sorted by rarity from the server/client-side generator.
 */
function renderPack(packCards) {
  var grid = document.getElementById('booster-grid');
  grid.innerHTML = '';

  packCards.forEach(function (card) {
    var tile = createBoosterCard(card);
    grid.appendChild(tile);
  });
}

/**
 * Create a single booster card tile DOM element.
 */
function createBoosterCard(card) {
  var tile = document.createElement('div');
  var rarity = (card.rarity || 'common').toLowerCase();
  tile.className = 'booster-card booster-rarity-' + rarity;
  if (isBasicLand(card)) {
    tile.className += ' booster-rarity-land';
  }

  // Image: prefer render_path, then art_path, then colored placeholder
  var imgSrc = card.render_path || card.art_path || '';

  if (imgSrc) {
    tile.innerHTML =
      '<div class="booster-card-image">' +
        '<img src="' + escapeHtmlBooster(imgSrc) + '" alt="' +
          escapeHtmlBooster(card.name) + '" loading="lazy">' +
      '</div>' +
      '<div class="booster-card-label">' +
        '<span class="booster-card-name">' + escapeHtmlBooster(card.name) + '</span>' +
        '<span class="badge badge-' + rarity + '">' + capitalizeBooster(rarity) + '</span>' +
      '</div>';
  } else {
    var bgColor = getColorBorderBooster(card.color_identity);
    tile.innerHTML =
      '<div class="booster-card-image">' +
        '<div class="card-placeholder" style="background: ' + bgColor + '">' +
          '<span>' + escapeHtmlBooster(card.name) + '</span>' +
        '</div>' +
      '</div>' +
      '<div class="booster-card-label">' +
        '<span class="booster-card-name">' + escapeHtmlBooster(card.name) + '</span>' +
        '<span class="badge badge-' + rarity + '">' + capitalizeBooster(rarity) + '</span>' +
      '</div>';
  }

  // Hover/click tooltip
  tile.addEventListener('mouseenter', function (e) { showTooltip(card, e); });
  tile.addEventListener('mousemove', function (e) { moveTooltip(e); });
  tile.addEventListener('mouseleave', hideTooltip);

  return tile;
}

// ---------------------------------------------------------------------------
//  Pack statistics sidebar
// ---------------------------------------------------------------------------

/**
 * Render pack statistics in the sidebar.
 */
function renderPackStats(packCards) {
  var stats = document.getElementById('booster-stats');
  if (!stats) return;

  var html = '';

  // --- Color breakdown ---
  html += '<div class="booster-stat-section">';
  html += '<h3 class="booster-stat-title">Colors</h3>';

  var colorCounts = { W: 0, U: 0, B: 0, R: 0, G: 0, multi: 0, colorless: 0 };
  packCards.forEach(function (card) {
    if (isBasicLand(card)) return; // Don't count lands in color breakdown
    var ci = card.color_identity || card.colors || [];
    if (ci.length === 0) {
      colorCounts.colorless++;
    } else if (ci.length > 1) {
      colorCounts.multi++;
    } else {
      var c = ci[0];
      if (colorCounts[c] !== undefined) colorCounts[c]++;
    }
  });

  var colorLabels = [
    { key: 'W', label: 'White', cls: 'booster-dot-w' },
    { key: 'U', label: 'Blue', cls: 'booster-dot-u' },
    { key: 'B', label: 'Black', cls: 'booster-dot-b' },
    { key: 'R', label: 'Red', cls: 'booster-dot-r' },
    { key: 'G', label: 'Green', cls: 'booster-dot-g' },
    { key: 'multi', label: 'Multi', cls: 'booster-dot-multi' },
    { key: 'colorless', label: 'Colorless', cls: 'booster-dot-colorless' },
  ];

  colorLabels.forEach(function (cl) {
    if (colorCounts[cl.key] > 0) {
      html += '<div class="booster-color-count">';
      html += '<span class="booster-dot ' + cl.cls + '"></span>';
      html += '<span class="booster-color-label">' + cl.label + '</span>';
      html += '<span class="booster-color-value">' + colorCounts[cl.key] + '</span>';
      html += '</div>';
    }
  });

  html += '</div>';

  // --- Rarity breakdown ---
  html += '<div class="booster-stat-section">';
  html += '<h3 class="booster-stat-title">Rarity</h3>';

  var rarityCounts = { mythic: 0, rare: 0, uncommon: 0, common: 0, land: 0 };
  packCards.forEach(function (card) {
    if (isBasicLand(card)) {
      rarityCounts.land++;
    } else {
      var r = (card.rarity || 'common').toLowerCase();
      if (rarityCounts[r] !== undefined) rarityCounts[r]++;
    }
  });

  var rarityLabels = [
    { key: 'mythic', label: 'Mythic', cls: 'badge-mythic' },
    { key: 'rare', label: 'Rare', cls: 'badge-rare' },
    { key: 'uncommon', label: 'Uncommon', cls: 'badge-uncommon' },
    { key: 'common', label: 'Common', cls: 'badge-common' },
    { key: 'land', label: 'Land', cls: 'badge-common' },
  ];

  rarityLabels.forEach(function (rl) {
    if (rarityCounts[rl.key] > 0) {
      html += '<div class="booster-stat-item">';
      html += '<span class="badge ' + rl.cls + '">' + rl.label + '</span>';
      html += '<span class="booster-stat-value">' + rarityCounts[rl.key] + '</span>';
      html += '</div>';
    }
  });

  html += '</div>';

  // --- Creature vs non-creature ---
  html += '<div class="booster-stat-section">';
  html += '<h3 class="booster-stat-title">Card Types</h3>';

  var creatureCount = 0;
  var nonCreatureCount = 0;
  var landCount = 0;
  packCards.forEach(function (card) {
    if (isBasicLand(card)) {
      landCount++;
    } else if (card.type_line && card.type_line.toLowerCase().indexOf('creature') !== -1) {
      creatureCount++;
    } else {
      nonCreatureCount++;
    }
  });

  html += '<div class="booster-stat-item">';
  html += '<span class="booster-stat-label">Creatures</span>';
  html += '<span class="booster-stat-value">' + creatureCount + '</span>';
  html += '</div>';
  html += '<div class="booster-stat-item">';
  html += '<span class="booster-stat-label">Non-creatures</span>';
  html += '<span class="booster-stat-value">' + nonCreatureCount + '</span>';
  html += '</div>';
  if (landCount > 0) {
    html += '<div class="booster-stat-item">';
    html += '<span class="booster-stat-label">Lands</span>';
    html += '<span class="booster-stat-value">' + landCount + '</span>';
    html += '</div>';
  }

  html += '</div>';

  // --- CMC stats ---
  html += '<div class="booster-stat-section">';
  html += '<h3 class="booster-stat-title">Mana Value</h3>';

  var totalCmc = 0;
  var cmcCards = 0;
  packCards.forEach(function (card) {
    if (!isBasicLand(card) && card.cmc != null) {
      totalCmc += card.cmc;
      cmcCards++;
    }
  });

  var avgCmc = cmcCards > 0 ? (totalCmc / cmcCards).toFixed(1) : '0.0';

  html += '<div class="booster-stat-item">';
  html += '<span class="booster-stat-label">Total CMC</span>';
  html += '<span class="booster-stat-value">' + totalCmc + '</span>';
  html += '</div>';
  html += '<div class="booster-stat-item">';
  html += '<span class="booster-stat-label">Average CMC</span>';
  html += '<span class="booster-stat-value">' + avgCmc + '</span>';
  html += '</div>';

  html += '</div>';

  // --- Mechanic presence ---
  var mechanicsFound = [];
  SET_MECHANICS.forEach(function (mech) {
    var found = packCards.some(function (card) {
      // Check mechanic_tags first
      if (card.mechanic_tags && card.mechanic_tags.length > 0) {
        for (var i = 0; i < card.mechanic_tags.length; i++) {
          if (card.mechanic_tags[i].toLowerCase().indexOf(mech.toLowerCase()) !== -1) {
            return true;
          }
        }
      }
      // Fallback: check oracle text
      if (card.oracle_text) {
        return card.oracle_text.toLowerCase().indexOf(mech.toLowerCase()) !== -1;
      }
      return false;
    });
    if (found) mechanicsFound.push(mech);
  });

  if (mechanicsFound.length > 0) {
    html += '<div class="booster-stat-section">';
    html += '<h3 class="booster-stat-title">Mechanics</h3>';
    mechanicsFound.forEach(function (mech) {
      html += '<div class="booster-stat-item">';
      html += '<span class="booster-mechanic-tag">' + mech + '</span>';
      html += '</div>';
    });
    html += '</div>';
  }

  stats.innerHTML = html;
}

// ---------------------------------------------------------------------------
//  Tooltip for card hover
// ---------------------------------------------------------------------------

/**
 * Show a tooltip with card details near the cursor.
 */
function showTooltip(card, event) {
  var tooltip = document.getElementById('booster-tooltip');
  if (!tooltip) return;

  var rarity = (card.rarity || 'common').toLowerCase();

  var html = '';
  html += '<div class="booster-tooltip-name">' + escapeHtmlBooster(card.name) + '</div>';

  if (card.mana_cost) {
    html += '<div class="booster-tooltip-mana">' + formatManaCostBooster(card.mana_cost) + '</div>';
  }

  html += '<div class="booster-tooltip-type">' + escapeHtmlBooster(card.type_line || '') + '</div>';
  html += '<span class="badge badge-' + rarity + '">' + capitalizeBooster(rarity) + '</span>';

  if (card.power != null && card.toughness != null) {
    html += '<div class="booster-tooltip-pt">' + card.power + ' / ' + card.toughness + '</div>';
  }

  tooltip.innerHTML = html;
  tooltip.style.display = 'block';
  moveTooltip(event);
}

/**
 * Position the tooltip near the cursor.
 */
function moveTooltip(event) {
  var tooltip = document.getElementById('booster-tooltip');
  if (!tooltip) return;

  var x = event.clientX + 16;
  var y = event.clientY + 16;

  // Keep tooltip within viewport
  var rect = tooltip.getBoundingClientRect();
  var tooltipWidth = rect.width || 200;
  var tooltipHeight = rect.height || 100;

  if (x + tooltipWidth > window.innerWidth - 8) {
    x = event.clientX - tooltipWidth - 8;
  }
  if (y + tooltipHeight > window.innerHeight - 8) {
    y = event.clientY - tooltipHeight - 8;
  }

  tooltip.style.left = x + 'px';
  tooltip.style.top = y + 'px';
}

/**
 * Hide the tooltip.
 */
function hideTooltip() {
  var tooltip = document.getElementById('booster-tooltip');
  if (tooltip) tooltip.style.display = 'none';
}

// ---------------------------------------------------------------------------
//  Mana cost formatting (local copy to avoid dependency on review.js)
// ---------------------------------------------------------------------------

/**
 * Convert a mana cost string like "{2}{W}{U}" into styled spans.
 */
function formatManaCostBooster(manaCost) {
  if (!manaCost) return '';
  return manaCost.replace(/\{([^}]+)\}/g, function (match, symbol) {
    var cls = 'mana-' + symbol.toLowerCase().replace('/', '');
    return '<span class="mana-symbol ' + cls + '">' + symbol + '</span>';
  });
}

// ---------------------------------------------------------------------------
//  Utility helpers (local copies to avoid dependency on review.js)
// ---------------------------------------------------------------------------

/** Escape HTML special characters. */
function escapeHtmlBooster(text) {
  if (!text) return '';
  var div = document.createElement('div');
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
}

/** Capitalize first letter. */
function capitalizeBooster(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

/** Get a CSS color for a card's color identity. */
function getColorBorderBooster(colorIdentity) {
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
//  Page initialization
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', function () {
  if (typeof ALL_CARDS !== 'undefined') {
    initBooster(ALL_CARDS);
  }
});
