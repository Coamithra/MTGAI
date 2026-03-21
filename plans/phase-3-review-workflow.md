# Phase 3: HTML Review Workflow — Revised Plan

## Context

Phase 3 builds the human-in-the-loop review workflow. The original plan split this into a CLI toolkit (3A) and a static HTML gallery (3B). In practice, human review during the dev set happened ad-hoc — via HTML comparison pages and direct conversation. The CLI approve/reject/flag workflow was never used.

**This revised plan replaces both 3A and 3B** with a single, practical HTML-based review workflow designed for full-set review at scale (~280 cards).

**Guiding principle**: The review tool is an HTML page backed by a tiny local server. The user reviews visually, makes decisions per card, and submits. The pipeline handles the rest.

**Dependencies**: Card data exists (`output/sets/<code>/cards/*.json`), renders exist (`output/sets/<code>/renders/`), art exists (`output/sets/<code>/art/`).

**What we keep from the old plan**:
- Card loader + filter module (old 3A-1) — still needed as the data layer
- HTML gallery with card grid and filters (old 3B core)
- Booster pack viewer (old 3B-5) — useful for gut-checking draft feel
- Export command (old 3A-9) — needed for print and playtesting later

**What we cut**:
- CLI approve/reject/flag workflow (old 3A-2, 3A-7) — replaced by HTML review decisions
- Status transition engine — overkill, `review-decisions.json` is simpler
- CLI compare/show — the HTML gallery does this better visually
- File watcher (old 3B-9) — replaced by server-driven refresh

---

## The Review Loop

```
Full pipeline run
        │
        ▼
┌──────────────────┐
│  Review Gallery   │  ◄── HTML page showing all cards
│  (per-card votes) │      with per-card decision controls
└────────┬─────────┘
         │ User clicks "Submit"
         ▼
┌──────────────────┐
│ review-decisions  │  ◄── JSON file with per-card verdicts
│     .json         │
└────────┬─────────┘
         │ Pipeline reads decisions
         ├──────────────────────────────┐
         ▼                              ▼
┌──────────────────┐    ┌──────────────────────┐
│ Remake pipeline  │    │ Art redo pipeline     │
│ (regenerate card │    │ (keep card, new art,  │
│  + art + render) │    │  re-render)           │
└────────┬─────────┘    └──────────┬───────────┘
         │                          │
         ▼                          ▼
┌──────────────────────────────────────────────┐
│            Progress Gallery                   │  ◄── Shows completed + pending slots
│  "Reload manual edits" button for hand-tweaks │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
                 Review again
              (repeat until all OK)
```

### Per-Card Decision Options

| Decision | What happens | When to use |
|----------|-------------|-------------|
| **OK** (default) | Nothing — card ships as-is | Card is good |
| **Remake** | Full regeneration: new card text → new art → new render | Card is fundamentally broken |
| **Art redo** | Keep card JSON, regenerate art → re-render | Card design is fine, art is bad |
| **Manual tweak** | User edits JSON by hand, then reloads | Small text fix, stat adjustment, flavor text change |

---

## Architecture

### Local Server

A lightweight FastAPI server handles:
1. Serving the review gallery HTML
2. Receiving the submit POST (writes `review-decisions.json`)
3. Serving the progress gallery
4. Providing a reload endpoint for manual edits

**Why a server?** Pure static HTML can't write files. We need a server to:
- Save review decisions to disk
- Trigger pipeline actions
- Serve updated progress pages

**Kept minimal**: ~100-200 lines of FastAPI. No database, no auth, no sessions. Runs on localhost only.

```python
# Endpoints
GET  /                          # Redirect to review gallery
GET  /review                    # Review gallery (card grid + decision controls)
POST /review/submit             # Save decisions, kick off pipelines
GET  /progress                  # Progress gallery (pending + completed)
POST /progress/reload-manual    # Re-read manually edited JSONs
GET  /booster                   # Random booster pack viewer
GET  /api/cards                 # Card data as JSON (for client-side filtering)
GET  /api/decisions             # Current review decisions (for restoring state)
```

### Review Gallery Page (`/review`)

The main review interface. Shows all rendered cards in a filterable grid.

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  Anomalous Descent (ASD) — 280 cards — Review Round 1   │
│                                                          │
│  [Color: W U B R G M C All] [Rarity: C U R M All]      │
│  [Type: ▼] [CMC: 0-7+] [Show: All | Needs Decision]    │
│  Showing 280 of 280 cards                                │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │
│  │ rendered │  │ rendered │  │ rendered │  │ rendered │   │
│  │  card    │  │  card    │  │  card    │  │  card    │   │
│  │  image   │  │  image   │  │  image   │  │  image   │   │
│  │         │  │         │  │         │  │         │   │
│  ├─────────┤  ├─────────┤  ├─────────┤  ├─────────┤   │
│  │ Card Name│  │ Card Name│  │ Card Name│  │ Card Name│   │
│  │(●)OK     │  │(●)OK     │  │( )OK     │  │(●)OK     │   │
│  │( )Remake │  │( )Remake │  │( )Remake │  │( )Remake │   │
│  │( )Art    │  │( )Art    │  │(●)Art    │  │( )Art    │   │
│  │( )Tweak  │  │( )Tweak  │  │( )Tweak  │  │( )Tweak  │   │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘   │
│                                                          │
│  ... (more rows)                                        │
│                                                          │
├─────────────────────────────────────────────────────────┤
│  Summary: 270 OK, 5 Remake, 3 Art Redo, 2 Manual Tweak │
│                                                          │
│  [ Submit Review ]                                       │
└─────────────────────────────────────────────────────────┘
```

**Card interactions**:
- Click card image → expand to detail view (modal or inline) showing full card text, oracle text, flavor, P/T, all fields
- Click art thumbnail in detail view → see full-size art
- Radio buttons for decision — OK is pre-selected
- Optional notes field (text input) per card for context ("too similar to W-C-03", "flavor text is cringe")

**Filtering**:
- Toggle buttons for color, rarity (same as old 3B plan)
- "Needs Decision" filter shows only non-OK cards
- All filtering is client-side JavaScript against embedded `cards.json`
- URL hash state for bookmarkable filter combos

**Submit action**:
- POST to `/review/submit` with all decisions
- Server writes `output/sets/<code>/review-decisions.json`
- Server responds with summary + next steps
- Browser redirects to progress page

### Review Decisions File

```json
{
  "set_code": "ASD",
  "review_round": 1,
  "timestamp": "2026-03-21T14:30:00",
  "decisions": {
    "W-C-01": {"action": "ok"},
    "W-C-02": {"action": "ok"},
    "B-R-02": {"action": "remake", "note": "card is unfun, too swingy"},
    "R-U-03": {"action": "art_redo", "note": "art has six fingers"},
    "G-C-04": {"action": "manual_tweak", "note": "change P/T from 3/3 to 2/3"},
    "U-R-01": {"action": "remake"},
    "...": "..."
  },
  "summary": {
    "ok": 270,
    "remake": 5,
    "art_redo": 3,
    "manual_tweak": 2
  }
}
```

### Submit Behavior

When the user clicks Submit, the server:

1. **Writes** `review-decisions.json` to `output/sets/<code>/`
2. **For remakes**: Queues cards for full regeneration (card text → art → render). Implementation: writes a `remake-queue.json` that the generation pipeline reads.
3. **For art redos**: Queues cards for art regeneration only (keep card JSON, new art → re-render). Implementation: writes an `art-redo-queue.json` that the art pipeline reads.
4. **For manual tweaks**:
   - Lists the JSON file paths in the response
   - Opens them in the system editor (notepad/VS Code) via `os.startfile()` or `subprocess`
   - Or: displays the paths prominently on the progress page
5. **Generates** the progress gallery HTML
6. **Redirects** browser to progress page

### Progress Gallery Page (`/progress`)

Shows the state of all cards after submit. Three sections:

```
┌─────────────────────────────────────────────────────────┐
│  Review Progress — Round 1                               │
│  270 OK  |  5 Remaking (2 done)  |  3 Art Redo (1 done) │
│  2 Manual Tweak (0 reloaded)                             │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ── Pending ──────────────────────────────────────────   │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                 │
│  │ ⏳       │  │ ⏳       │  │ ✏️ manual│                 │
│  │ REMAKING │  │ ART REDO │  │  TWEAK  │                 │
│  │ B-R-02   │  │ R-U-03   │  │ G-C-04  │                 │
│  │          │  │          │  │         │                 │
│  └─────────┘  └─────────┘  └─────────┘                 │
│                                                          │
│  ── Completed ────────────────────────────────────────   │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                 │
│  │ NEW card │  │ NEW card │  │ NEW art  │                 │
│  │ ✅ done  │  │ ✅ done  │  │ ✅ done  │                 │
│  │ U-R-01   │  │ R-M-01   │  │ W-U-02  │                 │
│  └─────────┘  └─────────┘  └─────────┘                 │
│                                                          │
│  [ Reload Manual Edits ]  [ Start New Review Round ]     │
└─────────────────────────────────────────────────────────┘
```

**Auto-refresh**: The page polls `/api/progress` every 10 seconds (or uses SSE) to update pending slots as cards complete. No manual browser refresh needed.

**"Reload Manual Edits"** button: POST to `/progress/reload-manual`. Server re-reads the JSON files for manual-tweak cards, re-renders them, and updates the progress page.

**"Start New Review Round"** button: Once all pending slots are filled, redirects back to `/review` showing the full set again (with remade/redone cards in place). Review round counter increments.

### Booster Pack Viewer (`/booster`)

Random 15-card booster pack display for gut-checking draft feel.

- 10 Commons + 3 Uncommons + 1 Rare/Mythic + 1 Land
- "Open New Pack" button
- Pack stats sidebar: color breakdown, creature count, total CMC
- Uses rendered card images

Pack generation logic in `mtgai/packs.py` (shared Python module). The JS on the page calls `/api/booster` to get a random pack.

### Card Detail Modal

Clicking any card in the grid opens an expanded view:

- Large rendered card image
- All card fields (name, cost, type, oracle, flavor, P/T, rarity, collector #)
- Art image (full size, separate from render)
- If card has a review note, show it
- Previous/Next navigation
- Close button or click outside to dismiss

---

## Implementation

### File Structure

```
backend/mtgai/
├── review/
│   ├── __init__.py
│   ├── loaders.py           # Card loader (existing, upgrade to Card models)
│   ├── formatters.py        # Rich formatters (existing, keep for CLI stats)
│   ├── cli.py               # CLI commands (existing: list, show, stats, balance, ai-review, finalize)
│   ├── server.py            # FastAPI local review server (NEW)
│   ├── decisions.py         # Review decisions model + dispatcher (NEW)
│   └── gallery_builder.py   # HTML gallery generator (NEW)
├── gallery/
│   └── templates/
│       ├── base.html        # Jinja2 base (head, nav, dark theme)
│       ├── review.html      # Review gallery with decision controls
│       ├── progress.html    # Progress tracker page
│       ├── booster.html     # Booster pack viewer
│       ├── card_modal.html  # Card detail modal partial
│       └── static/
│           ├── style.css    # Dark theme, responsive grid
│           ├── review.js    # Filter/sort + decision state + submit
│           ├── progress.js  # Auto-refresh polling
│           └── booster.js   # Booster randomization
├── packs.py                 # Booster pack generation (shared)
└── ...
```

### Task Breakdown

**Phase 3A (Data Layer + CLI Keep)** — streamlined from 10 tasks to 3:

| Task | Description | Notes |
|------|-------------|-------|
| **3A-1** | Card loader upgrade — load Card models (not raw dicts), filter by color/rarity/type/CMC/keyword/mechanic | Upgrade existing `loaders.py`. Shared by CLI and gallery. |
| **3A-2** | Export command — CSV, JSON, print file copy | Keep from old plan. Needed for print/playtesting. |
| **3A-3** | Booster pack module — `mtgai/packs.py` with `generate_booster_pack()` | Shared by gallery and future analysis. |

**Phase 3B (HTML Review Workflow)** — replaces old 3B entirely:

| Task | Description | Depends On |
|------|-------------|------------|
| **3B-1** | Gallery builder scaffolding — Jinja2 templates, static assets, `cards.json` export | 3A-1 |
| **3B-2** | Base HTML template + dark theme CSS — responsive card grid, modal system | — |
| **3B-3** | Review gallery page — card grid with filters, per-card decision radios, submit button | 3B-1, 3B-2 |
| **3B-4** | Card detail modal — expanded view on click, all card fields, art view | 3B-2 |
| **3B-5** | Review decisions model + dispatcher — Pydantic model for decisions, dispatch to remake/art-redo/manual-tweak pipelines | 3A-1 |
| **3B-6** | FastAPI review server — serves gallery, handles submit POST, progress API | 3B-3, 3B-5 |
| **3B-7** | Progress page — pending/completed sections, auto-refresh, reload manual edits | 3B-2, 3B-6 |
| **3B-8** | Booster pack viewer page + API endpoint | 3A-3, 3B-6 |
| **3B-9** | CLI entry point — `python -m mtgai.review serve` starts the server, `--open` launches browser | 3B-6 |

### Dependencies (Python packages)

```
# Existing
typer[all] >= 0.9      # CLI (already installed)
rich >= 13.0           # Terminal formatting (already installed)

# New for Phase 3
fastapi >= 0.110       # Local review server
uvicorn >= 0.29        # ASGI server for FastAPI
jinja2 >= 3.1          # HTML templates
```

### Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Server | FastAPI | Already in project deps (from master plan), async, minimal boilerplate |
| Templates | Jinja2 | Standard Python templating, FastAPI has built-in support |
| Styling | Vanilla CSS (dark theme) | CSS Grid for card layout, no framework needed |
| Client JS | Vanilla JavaScript | Filter/sort on 280 cards is trivial, no React/Vue overhead |
| Data | `cards.json` + API endpoints | Client-side filtering, server-side mutations |
| Images | Lazy loading (`loading="lazy"`) | Native browser support, handles 280 card images fine |

### Dark Theme CSS

```css
/* Core palette */
--bg-primary: #1a1a2e;
--bg-secondary: #16213e;
--bg-card: #0f3460;
--text-primary: #e8e8e8;
--text-secondary: #a0a0a0;
--accent: #e94560;

/* MTG color accents for card borders */
--mtg-white: #f9faf4;
--mtg-blue: #0e68ab;
--mtg-black: #150b00;
--mtg-red: #d3202a;
--mtg-green: #00733e;
--mtg-gold: #c9a953;
--mtg-colorless: #8a8f93;
```

---

## Pipeline Integration

### Remake Queue

When submit dispatches remakes, it writes:

```json
// output/sets/ASD/remake-queue.json
{
  "cards": ["B-R-02", "U-R-01", "R-M-01", "W-R-02", "G-U-03"],
  "review_round": 1,
  "timestamp": "2026-03-21T14:30:00"
}
```

The generation pipeline (`card_generator.py`) reads this, archives the old card, regenerates, then runs art + render. On completion, updates a `remake-status.json` that the progress page polls.

### Art Redo Queue

```json
// output/sets/ASD/art-redo-queue.json
{
  "cards": ["R-U-03", "W-U-02", "B-C-05"],
  "review_round": 1,
  "timestamp": "2026-03-21T14:30:00"
}
```

The art pipeline reads this, regenerates art for these cards only (keeping card JSON), then re-renders. Same status tracking pattern.

### Manual Tweak Flow

1. Submit identifies manual-tweak cards
2. Server lists their JSON paths in the response
3. Progress page shows them as "pending manual edit" with file paths
4. User edits JSONs directly (notepad, VS Code, whatever)
5. User clicks "Reload Manual Edits" on progress page
6. Server re-reads those JSONs, re-runs validation + render
7. Cards appear in the completed section

---

## What's NOT in Phase 3

- **Status transition engine** — replaced by simple review decisions
- **CLI approve/reject/flag** — replaced by HTML review
- **Audit trail** — review-decisions.json IS the audit trail (timestamped, per-round)
- **File watcher** — replaced by server-driven progress polling
- **Cockatrice export** — defer to Phase 5 or later
- **Art review as separate page** — art is visible in the card detail modal; if art consistency review is needed, add a filter/grouping mode to the main gallery later

---

## Open Questions

1. **Pipeline dispatch**: Should submit kick off pipelines automatically (background subprocess), or just write the queue files and let the user run pipelines manually? Auto-dispatch is smoother UX but means the server needs to manage subprocesses. Manual dispatch means `python -m mtgai.generation.card_generator --queue` as a separate step.

2. **Simultaneous review + pipeline**: Can the user start reviewing round 2 while round 1 remakes are still in flight? Probably yes — just show pending slots alongside new results.

3. **Art comparison**: Should the art redo show the old art alongside the new art for comparison? Useful for judging improvement. Could show old art as a dimmed overlay or side-by-side in the progress page.

4. **Multi-set support**: For now, hardcode to single set. Add set selector when we actually have multiple sets.
