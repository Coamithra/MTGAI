// ==========================================================================
//  Progress page JavaScript
//  Auto-refreshing progress tracker for cards in the review pipeline.
//  Shows pending/completed/error sections with polling updates.
// ==========================================================================

// ---------------------------------------------------------------------------
//  State
// ---------------------------------------------------------------------------
var progressData = null;   // Current progress data from server
var pollingTimer = null;    // setInterval handle
var POLL_INTERVAL = 10000;  // 10 seconds

// ---------------------------------------------------------------------------
//  Action display labels
// ---------------------------------------------------------------------------
var ACTION_LABELS = {
  remake: "Remake",
  art_redo: "Art Redo",
  manual_tweak: "Manual Tweak"
};

var ACTION_VERBS = {
  remake: "REMAKING",
  art_redo: "REDOING ART",
  manual_tweak: "MANUAL TWEAK"
};

// ---------------------------------------------------------------------------
//  Initialization
// ---------------------------------------------------------------------------

/**
 * Initialize the progress page from PROGRESS_DATA injected by the template.
 * Shows summary stats, renders card sections, starts polling.
 */
function initProgress(data) {
  progressData = data;

  if (!data || !data.cards || Object.keys(data.cards).length === 0) {
    renderEmptyState();
    return;
  }

  renderSummary(data);
  renderProgressCards(data);
  showReloadButton(data);
  startPolling(POLL_INTERVAL);
}

// ---------------------------------------------------------------------------
//  Summary rendering
// ---------------------------------------------------------------------------

/**
 * Compute summary counts from card data (since the server @property
 * is not included in JSON serialization).
 */
function computeSummary(data) {
  var summary = { pending: 0, in_progress: 0, completed: 0, error: 0 };
  var cards = data.cards || {};
  var keys = Object.keys(cards);
  for (var i = 0; i < keys.length; i++) {
    var status = cards[keys[i]].status || "pending";
    summary[status] = (summary[status] || 0) + 1;
  }
  return summary;
}

/**
 * Render the summary bar with review round, progress bar, and counts.
 */
function renderSummary(data) {
  var summaryEl = document.getElementById("progress-summary");
  var summary = computeSummary(data);
  var total = Object.keys(data.cards).length;
  var completed = summary.completed || 0;
  var errors = summary.error || 0;
  var pending = (summary.pending || 0) + (summary.in_progress || 0);
  var pct = total > 0 ? Math.round((completed / total) * 100) : 0;

  var allDone = pending === 0 && total > 0;

  var html =
    '<div class="progress-summary-header">' +
      '<span class="progress-round">Review Round ' + (data.review_round || 1) +
        '</span>' +
      '<span class="progress-total">' + total + ' card' + (total !== 1 ? 's' : '') +
        ' in progress</span>' +
    '</div>' +
    '<div class="progress-bar-container">' +
      '<div class="progress-bar-track">' +
        '<div class="progress-bar-fill' + (allDone ? ' complete' : '') +
          '" style="width: ' + pct + '%"></div>' +
      '</div>' +
      '<span class="progress-bar-label">' +
        completed + '/' + total + ' complete' +
        (errors > 0 ? ' | <span class="text-error">' + errors + ' error' +
          (errors !== 1 ? 's' : '') + '</span>' : '') +
        (pending > 0 ? ' | ' + pending + ' pending' : '') +
      '</span>' +
    '</div>';

  if (allDone) {
    html +=
      '<div class="progress-done-banner">' +
        'All cards processed!' +
        ' <button class="submit-btn" onclick="startNewRound()">' +
          'Start New Review Round' +
        '</button>' +
      '</div>';
  }

  summaryEl.innerHTML = html;
}

/**
 * Render the empty state when no progress data exists.
 */
function renderEmptyState() {
  var summaryEl = document.getElementById("progress-summary");
  summaryEl.innerHTML =
    '<div class="progress-empty">' +
      '<p>No review in progress.</p>' +
      '<p>Submit a review from the ' +
        '<a href="/review">Review page</a> to start tracking progress.</p>' +
    '</div>';

  document.getElementById("progress-list").innerHTML = "";
}

// ---------------------------------------------------------------------------
//  Card section rendering
// ---------------------------------------------------------------------------

/**
 * Render cards into pending/completed/error sections.
 */
function renderProgressCards(data) {
  var listEl = document.getElementById("progress-list");
  var cards = data.cards || {};
  var keys = Object.keys(cards);

  // Partition cards by status
  var pending = [];
  var completed = [];
  var errors = [];

  for (var i = 0; i < keys.length; i++) {
    var card = cards[keys[i]];
    if (card.status === "completed") {
      completed.push(card);
    } else if (card.status === "error") {
      errors.push(card);
    } else {
      // pending or in_progress
      pending.push(card);
    }
  }

  // Sort each group by collector number
  var sortByCN = function (a, b) {
    return a.collector_number.localeCompare(b.collector_number);
  };
  pending.sort(sortByCN);
  completed.sort(sortByCN);
  errors.sort(sortByCN);

  var html = "";

  // Error section (most important, show first)
  if (errors.length > 0) {
    html += renderSection("Errors", "error", errors, renderErrorTile);
  }

  // Pending section
  if (pending.length > 0) {
    html += renderSection("Pending", "pending", pending, renderPendingTile);
  }

  // Completed section
  if (completed.length > 0) {
    html += renderSection("Completed", "completed", completed, renderCompletedTile);
  }

  listEl.innerHTML = html;
}

/**
 * Render a section with header and card grid.
 */
function renderSection(title, className, cards, tileRenderer) {
  var html =
    '<div class="progress-section">' +
      '<h2 class="progress-section-title progress-section-' + className + '">' +
        title +
        ' <span class="progress-section-count">(' + cards.length + ')</span>' +
      '</h2>' +
      '<div class="card-grid">';

  for (var i = 0; i < cards.length; i++) {
    html += tileRenderer(cards[i]);
  }

  html += '</div></div>';
  return html;
}

/**
 * Render a pending card tile with hourglass icon, action label, and note.
 */
function renderPendingTile(card) {
  var actionLabel = ACTION_VERBS[card.action] || card.action.toUpperCase();
  var note = card.note || "";

  return (
    '<div class="progress-tile pending">' +
      '<div class="progress-tile-body">' +
        '<div class="progress-icon">' +
          (card.status === "in_progress" ? '<span class="spinner"></span>' : '&#9203;') +
        '</div>' +
        '<div class="progress-label">' + escapeHtml(actionLabel) + '</div>' +
        '<div class="progress-collector">' + escapeHtml(card.collector_number) + '</div>' +
        (note ? '<div class="progress-note">' + escapeHtml(note) + '</div>' : '') +
      '</div>' +
    '</div>'
  );
}

/**
 * Render a completed card tile with the rendered image (if available)
 * and a green checkmark overlay.
 */
function renderCompletedTile(card) {
  // Build an image path from the collector number.
  // The server mounts /renders/ for card images. The exact filename includes
  // the card slug, which we don't have here. Use the collector number to
  // build a data attribute; the image will be resolved by the render path
  // pattern or shown as a placeholder.
  var cn = card.collector_number;

  return (
    '<div class="progress-tile completed">' +
      '<div class="progress-tile-body">' +
        '<div class="progress-icon completed-icon">&#9989;</div>' +
        '<div class="progress-label">DONE</div>' +
        '<div class="progress-collector">' + escapeHtml(cn) + '</div>' +
        '<div class="progress-action-badge">' +
          escapeHtml(ACTION_LABELS[card.action] || card.action) +
        '</div>' +
      '</div>' +
    '</div>'
  );
}

/**
 * Render an error card tile with red styling and error message.
 */
function renderErrorTile(card) {
  var cn = card.collector_number;
  var errorMsg = card.error_message || "Unknown error";
  var actionLabel = ACTION_LABELS[card.action] || card.action;

  return (
    '<div class="progress-tile error">' +
      '<div class="progress-tile-body">' +
        '<div class="progress-icon">&#10060;</div>' +
        '<div class="progress-label">ERROR</div>' +
        '<div class="progress-collector">' + escapeHtml(cn) + '</div>' +
        '<div class="progress-action-badge">' + escapeHtml(actionLabel) + '</div>' +
        '<div class="progress-note progress-error-msg">' +
          escapeHtml(errorMsg) +
        '</div>' +
      '</div>' +
    '</div>'
  );
}

// ---------------------------------------------------------------------------
//  Polling
// ---------------------------------------------------------------------------

/**
 * Start polling GET /api/progress every intervalMs milliseconds.
 * Only re-renders if the data has changed.
 */
function startPolling(intervalMs) {
  if (pollingTimer) {
    clearInterval(pollingTimer);
  }

  pollingTimer = setInterval(function () {
    fetchProgress();
  }, intervalMs);
}

/**
 * Stop polling (called when all cards are done).
 */
function stopPolling() {
  if (pollingTimer) {
    clearInterval(pollingTimer);
    pollingTimer = null;
  }
}

/**
 * Fetch updated progress from the server and re-render if changed.
 */
function fetchProgress() {
  var setCode = progressData ? progressData.set_code : "ASD";

  fetch("/api/progress?set_code=" + encodeURIComponent(setCode))
    .then(function (response) {
      if (!response.ok) {
        throw new Error("Server error: " + response.status);
      }
      return response.json();
    })
    .then(function (newData) {
      if (hasChanged(progressData, newData)) {
        progressData = newData;
        renderSummary(newData);
        renderProgressCards(newData);
        showReloadButton(newData);

        // Stop polling if all done
        if (isAllComplete(newData)) {
          stopPolling();
        }
      }
    })
    .catch(function (error) {
      // Silently ignore polling errors (server may be restarting)
      console.warn("Progress poll failed:", error.message);
    });
}

/**
 * Compare old and new progress data to detect changes.
 * Uses a simple JSON string comparison on the cards dict.
 */
function hasChanged(oldData, newData) {
  if (!oldData && !newData) return false;
  if (!oldData || !newData) return true;

  // Compare serialized cards — fast and reliable
  var oldCards = JSON.stringify(oldData.cards || {});
  var newCards = JSON.stringify(newData.cards || {});
  return oldCards !== newCards;
}

/**
 * Check if all cards are completed or errored (nothing pending).
 */
function isAllComplete(data) {
  if (!data || !data.cards) return false;
  var keys = Object.keys(data.cards);
  if (keys.length === 0) return false;

  for (var i = 0; i < keys.length; i++) {
    var status = data.cards[keys[i]].status;
    if (status !== "completed" && status !== "error") {
      return false;
    }
  }
  return true;
}

// ---------------------------------------------------------------------------
//  Reload Manual Edits
// ---------------------------------------------------------------------------

/**
 * POST to /api/progress/reload-manual to re-read manually edited card JSONs.
 * Shows loading state on the button and refreshes the display on success.
 */
function reloadManualEdits() {
  var btn = document.getElementById("reload-manual-btn");
  if (!btn) return;

  var setCode = progressData ? progressData.set_code : "ASD";

  btn.disabled = true;
  btn.textContent = "Reloading...";

  fetch("/api/progress/reload-manual?set_code=" + encodeURIComponent(setCode), {
    method: "POST"
  })
    .then(function (response) {
      if (!response.ok) {
        throw new Error("Server error: " + response.status);
      }
      return response.json();
    })
    .then(function (result) {
      if (result.success) {
        var count = (result.updated || []).length;
        btn.textContent = count > 0
          ? "Reloaded " + count + " card" + (count !== 1 ? "s" : "")
          : "No changes";

        // Refresh the full progress display
        fetchProgress();

        // Reset button text after 2 seconds
        setTimeout(function () {
          btn.textContent = "Reload Manual Edits";
          btn.disabled = false;
        }, 2000);
      } else {
        throw new Error(result.error || "Unknown error");
      }
    })
    .catch(function (error) {
      alert("Reload failed: " + error.message);
      btn.textContent = "Reload Manual Edits";
      btn.disabled = false;
    });
}

// ---------------------------------------------------------------------------
//  Refresh button
// ---------------------------------------------------------------------------

/**
 * Manual refresh — fetch progress immediately (for the Refresh button).
 */
function refreshProgress() {
  fetchProgress();
}

// ---------------------------------------------------------------------------
//  Start new round
// ---------------------------------------------------------------------------

/**
 * Redirect to the review page to start a fresh review round.
 */
function startNewRound() {
  window.location.href = "/review";
}

// ---------------------------------------------------------------------------
//  Show/hide reload button
// ---------------------------------------------------------------------------

/**
 * Show the "Reload Manual Edits" button only if there are manual_tweak cards.
 */
function showReloadButton(data) {
  var btn = document.getElementById("reload-manual-btn");
  if (!btn) return;

  var hasManualTweaks = false;
  var cards = data.cards || {};
  var keys = Object.keys(cards);
  for (var i = 0; i < keys.length; i++) {
    if (cards[keys[i]].action === "manual_tweak") {
      hasManualTweaks = true;
      break;
    }
  }

  btn.style.display = hasManualTweaks ? "" : "none";
}

// ---------------------------------------------------------------------------
//  Utility
// ---------------------------------------------------------------------------

/** Escape HTML special characters to prevent XSS. */
function escapeHtml(text) {
  if (!text) return "";
  var div = document.createElement("div");
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
}

// ---------------------------------------------------------------------------
//  Page load
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", function () {
  if (typeof PROGRESS_DATA !== "undefined") {
    initProgress(PROGRESS_DATA);
  }
});
