# Phase 3: Review Tools — Implementation Plan

## Context

Phase 3 builds the human-in-the-loop review workflow. Phase 1A introduces a minimal CLI (list, show, stats). Phase 3 extends that into a full review toolkit (3A) and adds an HTML gallery viewer for visual review (3B). The guiding principle is **lightweight tooling, not a full web app** — CLI primary, static HTML for visual tasks.

**Dependencies**: Phase 1A (minimal CLI skeleton), Phase 1C (card data exists to review), Phase 2B/2C (art and rendered images exist for gallery).

**Can start early**: The CLI commands (3A) can be built and tested against mock card data immediately after Phase 0C (project setup). HTML gallery (3B) needs rendered images, so it blocks on Phase 2C for full functionality but can scaffold with placeholder images.

## Quick Start (Context Reset)

**Prerequisites**:
- Phase 0C complete: card schema (`backend/mtgai/models/card.py`)
- Phase 1A complete: minimal CLI skeleton (Typer-based)
- Card data exists in `output/sets/<code>/cards/` (from Phase 1C, or mock data for testing)

**Read first**: This plan. Review the card schema from Phase 0C and the CLI stub from Phase 1A.

**Start with**: Phase 3A Task 3A-1 (card loader + filter module).

## Deliverables Checklist

### Phase 3A: CLI Review Tools
- [ ] All CLI commands functional:
  - [ ] `mtgai review list` — with all filter options (color, rarity, type, status, CMC, keyword, mechanic)
  - [ ] `mtgai review show` — pretty-printed card detail with history
  - [ ] `mtgai review stats` — set statistics dashboard with bar charts
  - [ ] `mtgai review approve` — batch approve with safety checks
  - [ ] `mtgai review reject` — with required reason, optional regenerate flag
  - [ ] `mtgai review flag` — orthogonal flagging with categories
  - [ ] `mtgai review compare` — side-by-side card comparison
  - [ ] `mtgai review export` — CSV, JSON, print, Cockatrice formats
  - [ ] `mtgai review art` — art file info with --open support
- [ ] Status transition engine with audit trail
- [ ] Batch operations with safety (confirmation prompts, dry-run)
- [ ] Rich terminal formatting with color coding
- [ ] JSON output mode for piping

### Phase 3B: HTML Gallery Viewer
- [ ] `mtgai review gallery` command generates static HTML site
- [ ] Card grid page with filter/sort controls (index.html)
- [ ] Individual card detail pages (cards/NNN.html)
- [ ] Side-by-side comparison mode (compare.html)
- [ ] Sample booster pack viewer (booster.html)
- [ ] Art consistency review page (art-review.html)
- [ ] `mtgai/packs.py` — shared booster generation logic (reused by Phase 4B)
- [ ] Dark theme CSS, responsive layout
- [ ] Flagged card highlighting
- [ ] --open flag launches browser, --watch mode (optional) auto-regenerates

**Done when**: All CLI commands work against real card data, the HTML gallery generates and displays correctly in a browser, and the booster pack generation function is shared with Phase 4B.

---

## Design Decisions (Cross-Cutting Concerns)

### CLI Framework: Typer

Use **Typer** (built on Click) for the CLI. Rationale:
- Automatic `--help` generation from type hints
- Tab completion out of the box
- Subcommand groups (`review list`, `review approve`, etc.) with zero boilerplate
- Rich integration for colored/formatted terminal output
- Click is the alternative — Typer is simpler for our use case (no complex argument parsing needed)

The Phase 1A minimal CLI should be built with Typer from the start. This means Phase 3A is a natural extension, not a rewrite. **Design them together upfront** — define the command group structure in Phase 1A even if most commands are stubs.

### Phase 1A CLI Skeleton (design now, implement in Phase 1A)

```
mtgai review list    [Phase 1A — basic filtering]
mtgai review show    [Phase 1A — card detail view]
mtgai review stats   [Phase 1A — summary dashboard]
mtgai review approve [Phase 3A — stub in 1A]
mtgai review reject  [Phase 3A — stub in 1A]
mtgai review flag    [Phase 3A — stub in 1A]
mtgai review compare [Phase 3A]
mtgai review export  [Phase 3A]
mtgai review art     [Phase 3A]
mtgai review gallery [Phase 3B — launches gallery generation]
```

### HTML Gallery: Static HTML + Vanilla JS

No Flask/FastAPI server. No React. Generate static HTML files from card data using **Jinja2 templates**, serve with `python -m http.server`. Rationale:
- Zero runtime dependencies beyond what's already in the project
- Jinja2 is already a common Python dependency (likely pulled in by other tools)
- Files can be opened directly in a browser (no server needed for basic viewing)
- If hot-reload becomes painful, upgrade to a simple `livereload` watcher later — but start without it

### No "Regenerate" Button in Gallery

The gallery is a read-only viewer. Triggering art regeneration or card edits happens through the CLI. Adding regeneration buttons means building an API server, managing background jobs, handling errors in a browser — that's a full web app. The gallery shows you what to fix; the CLI fixes it.

### Audit Trail: Yes, Lightweight

Track who/when for status transitions. "Who" is just a configurable reviewer name (not full auth). Stored in the card JSON alongside the status field. This costs almost nothing to implement and is valuable when reviewing decisions later.

### Booster Pack Viewer: Shared Code with Phase 4B

The gallery's "sample booster pack" display and Phase 4B's "Limited Environment Analysis" both need a `generate_booster_pack()` function. Build this as a shared utility in `mtgai.packs` during Phase 3B, and Phase 4B reuses it. The gallery calls it for display; Phase 4B calls it for statistical analysis.

### Keyboard Shortcuts in CLI: No

Typer/Click CLIs don't have interactive keyboard shortcuts — they're command-based. For rapid review, the answer is batch operations and good filtering, not a TUI. If a TUI becomes necessary later, that's a separate tool (Textual), not part of Phase 3.

---

## Phase 3A: CLI Review Tools

### 3A.1 Command Inventory

All commands live under `mtgai review` (Typer app group). Entry point: `python -m mtgai review <command>`.

---

#### `review list` — Card Listing with Filters

```
mtgai review list [OPTIONS]

Options:
  --color, -c       TEXT     Filter by color identity (W, U, B, R, G, M for multicolor, C for colorless)
  --rarity, -r      TEXT     Filter by rarity (common, uncommon, rare, mythic)
  --type, -t        TEXT     Filter by card type (creature, instant, sorcery, enchantment, artifact, land, planeswalker)
  --status, -s      TEXT     Filter by status (draft, validated, approved, art_generated, rendered, print_ready)
  --cmc-min         INT      Minimum converted mana cost
  --cmc-max         INT      Maximum converted mana cost
  --keyword, -k     TEXT     Filter by keyword in name, rules text, or type line (substring match)
  --mechanic, -m    TEXT     Filter by set mechanic name
  --flagged          FLAG    Show only flagged cards
  --sort             TEXT    Sort by: name, cmc, rarity, color, collector_number, status (default: collector_number)
  --reverse          FLAG    Reverse sort order
  --format, -f      TEXT    Output format: table (default), compact, json
  --limit            INT     Max results to show (default: all)
  --set-code         TEXT    Set code to review (default: auto-detect from output/)

Output (table format):
  #    Name                  Cost   Type              Rarity    Color  Status       Flags
  001  Aetheric Sentinel     {2}{W} Creature - Golem  Uncommon  W      validated
  002  Mind Eraser           {1}{U} Instant           Common    U      approved
  003  Shadowfang Assassin   {2}{B} Creature - Human  Rare      B      flagged      ⚑ balance

Output (compact format):
  001 Aetheric Sentinel [2W] U Creature validated
  002 Mind Eraser [1U] C Instant approved
```

**Multiple filters are AND-combined.** Example: `--color W --rarity common --type creature` shows white common creatures only.

**Implementation notes:**
- Loads card data from `output/sets/<set-code>/cards/*.json`
- Table rendering via `rich.table.Table` (Rich library, already useful for other formatting)
- Terminal width handling: Rich auto-truncates columns. For very narrow terminals, fall back to compact format.

---

#### `review show <card>` — Detailed Card View

```
mtgai review show <CARD_ID>

Arguments:
  CARD_ID    Collector number (e.g., "001") or card name (fuzzy match)
```

Output: Pretty-printed card with all fields in a bordered panel.

```
╭─────────────────────────────────────────╮
│  #001 — Aetheric Sentinel               │
│  {2}{W}                                  │
│  Creature — Golem Soldier                │
│                                          │
│  Vigilance                               │
│  When Aetheric Sentinel enters, create   │
│  a 1/1 white Soldier creature token.     │
│                                          │
│  "The city's walls have eyes."           │
│                                          │
│  3/4                                     │
│                                          │
│  Rarity: Uncommon    Color: W            │
│  Status: validated   CMC: 3              │
│  Mechanic: —                             │
│  Art: output/sets/XYZ/art/001_aetheric…  │
│  Render: (not yet rendered)              │
│                                          │
│  History:                                │
│    2026-03-08 14:30  draft (generated)   │
│    2026-03-08 15:12  validated (auto)    │
╰─────────────────────────────────────────╯
```

**Fuzzy name match**: If `CARD_ID` is not a number, do case-insensitive substring match. If multiple matches, list them and ask to be more specific.

---

#### `review stats` — Set Statistics Dashboard

```
mtgai review stats [OPTIONS]

Options:
  --set-code   TEXT   Set code (default: auto-detect)
  --detailed    FLAG  Show per-color breakdowns
```

Output:

```
Set: Echoes of the Void (ETV) — 280 cards

Status Pipeline:
  draft          ████████████░░░░░░░░  42 (15%)
  validated      ████████░░░░░░░░░░░░  35 (13%)
  approved       ████████████████████  140 (50%)
  art_generated  ████████░░░░░░░░░░░░  33 (12%)
  rendered       ██████░░░░░░░░░░░░░░  20 (7%)
  print_ready    ██░░░░░░░░░░░░░░░░░░  10 (4%)

Rarity Distribution:
  Common: 101  Uncommon: 80  Rare: 64  Mythic: 15  Basic Land: 20

Color Distribution:
  W: 52   U: 53   B: 51   R: 54   G: 50   Multi: 40   Colorless: 20

Mana Curve (creatures):
  1: ████████   16
  2: ████████████████   32
  3: ██████████████████████   44
  4: ██████████████   28
  5: ████████   16
  6: ████   8
  7+: ██   4

Flagged Cards: 7
  ⚑ 003 Shadowfang Assassin — balance: P/T too high for CMC
  ⚑ 045 Eternal Damnation — text_overflow: rules text exceeds frame
  ...
```

**Implementation**: Compute all stats by iterating card JSON files. Use Rich for bar charts (they're just styled text). The `--detailed` flag adds per-color mana curves and per-color type breakdowns.

---

#### `review approve <target>` — Approve Cards

```
mtgai review approve <TARGET> [OPTIONS]

Arguments:
  TARGET     Card ID, comma-separated IDs ("001,002,003"), or "all"

Options:
  --filter     TEXT   Approve all cards matching filter (same syntax as `list` filters)
  --from-status TEXT  Only approve cards currently in this status (safety check)
  --reviewer    TEXT  Reviewer name for audit trail (default: from config)
  --note        TEXT  Optional note attached to the transition
  --dry-run     FLAG  Show what would be approved without doing it
```

Examples:
```bash
mtgai review approve 001                        # Approve single card
mtgai review approve 001,002,003                # Approve multiple
mtgai review approve all --from-status validated # Approve all validated cards
mtgai review approve --filter "--color W --rarity common" --dry-run
```

**Status transition**: Advances the card one step in the pipeline (see 3A.2). Refuses if the transition is invalid. Always prompts for confirmation on batch operations (more than 5 cards) unless `--yes` flag is passed.

---

#### `review reject <target>` — Reject Cards

```
mtgai review reject <TARGET> [OPTIONS]

Arguments:
  TARGET     Card ID, comma-separated IDs, or "all" (with filter)

Options:
  --reason, -r  TEXT   Required reason for rejection
  --filter      TEXT   Reject all cards matching filter
  --from-status TEXT   Only reject cards currently in this status
  --reviewer    TEXT   Reviewer name
  --regenerate  FLAG   Queue card for regeneration after rejection
  --dry-run     FLAG   Show what would be rejected
```

**Rejection resets status to `draft`** and increments the attempt counter. The reason is stored in the card's history. If `--regenerate` is passed, the card is marked for the next generation run to pick up.

---

#### `review flag <target>` — Flag for Attention

```
mtgai review flag <TARGET> [OPTIONS]

Arguments:
  TARGET     Card ID or comma-separated IDs

Options:
  --reason, -r   TEXT   Required flag reason (balance, text_overflow, art_quality, color_pie, other)
  --category     TEXT   Flag category for grouping
  --reviewer     TEXT   Reviewer name
  --clear        FLAG   Clear flag instead of setting it
```

Flagging does NOT change the card's pipeline status. It's an orthogonal marker — a card can be `approved` and `flagged` simultaneously (meaning it passed validation but a human wants to revisit it).

---

#### `review compare <card1> <card2>` — Side-by-Side Comparison

```
mtgai review compare <CARD1> <CARD2>

Arguments:
  CARD1, CARD2   Card IDs or names (same matching as `show`)
```

Output:

```
╭─────────────────────────╮  ╭─────────────────────────╮
│ #001 Aetheric Sentinel  │  │ #045 Iron Guardian       │
│ {2}{W}                  │  │ {3}{W}                   │
│ Creature — Golem        │  │ Creature — Golem         │
│                         │  │                          │
│ Vigilance               │  │ Vigilance, Reach         │
│ When ~ enters, create   │  │ When ~ enters, you gain  │
│ a 1/1 white Soldier     │  │ 3 life.                  │
│ creature token.         │  │                          │
│                         │  │                          │
│ 3/4                     │  │ 2/5                      │
│                         │  │                          │
│ Uncommon   CMC: 3       │  │ Uncommon   CMC: 4        │
│ Status: validated       │  │ Status: approved         │
╰─────────────────────────╯  ╰─────────────────────────╯

Differences:
  CMC: 3 vs 4
  P/T: 3/4 vs 2/5
  Keywords: [Vigilance] vs [Vigilance, Reach]
  Status: validated vs approved
```

**Use case**: Checking similar cards aren't too close in power level, or comparing a regenerated card to its previous version.

---

#### `review export` — Export Set Data

```
mtgai review export <FORMAT> [OPTIONS]

Arguments:
  FORMAT     Output format: csv, json, print, cockatrice

Options:
  --output, -o  PATH   Output file/directory (default: output/exports/)
  --status      TEXT    Only export cards with this status or higher
  --include-art FLAG    Include art file paths in export
```

Formats:
- **csv**: Flat spreadsheet with all card fields. For external review or spreadsheet analysis.
- **json**: Full card data as a single JSON array. For programmatic use.
- **print**: Copy all print-ready rendered images to a flat directory with standardized naming. For upload to print service.
- **cockatrice**: Export as Cockatrice XML for playtesting the set digitally.

---

#### `review art <card>` — Art File Info

```
mtgai review art <CARD_ID> [OPTIONS]

Arguments:
  CARD_ID    Card ID or name

Options:
  --open     FLAG   Open art file in system default image viewer
  --all      FLAG   Show all art attempts (not just current)
  --compare  FLAG   Show all versions side by side (opens file explorer to directory)
```

Output:

```
Card: #001 Aetheric Sentinel

Art Status: generated (attempt 2)
Current:  output/sets/ETV/art/001_aetheric_sentinel_v2.png
  Size:   1024x1024  Format: PNG  FileSize: 2.3 MB

Previous attempts:
  v1: output/sets/ETV/art/001_aetheric_sentinel_v1.png (rejected: wrong style)

Rendered: output/sets/ETV/rendered/001_aetheric_sentinel.png
  Size:   750x1050  Format: PNG  FileSize: 4.1 MB
```

The `--open` flag uses `os.startfile()` (Windows) / `xdg-open` (Linux) / `open` (macOS) to open the image in the default viewer.

---

### 3A.2 Status Transition Rules

Cards move through a linear pipeline with defined gates:

```
draft ──→ validated ──→ approved ──→ art_generated ──→ rendered ──→ print_ready
  ↑          │             │              │               │
  └──────────┴─────────────┴──────────────┴───────────────┘
                        (reject → back to draft)
```

| Transition | Trigger | Who/What |
|------------|---------|----------|
| `draft` → `validated` | Automatic: card passes all validation checks (rules text grammar, balance score, color pie, text overflow estimate) | `mtgai.validation` library (Phase 1C) |
| `validated` → `approved` | Manual: human reviews card data and approves | `review approve` CLI command |
| `approved` → `art_generated` | Automatic: art generation pipeline produces accepted art | Phase 2B art pipeline |
| `art_generated` → `rendered` | Automatic: card renderer produces the final card image | Phase 2C renderer |
| `rendered` → `print_ready` | Manual: human reviews rendered image and approves for printing | `review approve` CLI command |
| Any → `draft` | Manual: human rejects, resets to draft for regeneration | `review reject` CLI command |

**Rules**:
- Forward transitions skip exactly zero steps — you cannot go from `draft` directly to `approved` (must pass through `validated`).
- `review approve` advances one step forward (validated→approved or rendered→print_ready). It does NOT trigger automated steps (art generation, rendering) — those are separate pipeline commands.
- Rejection always resets to `draft`, regardless of current status. This forces the card through the full pipeline again.
- Bulk approval via `review approve all --from-status validated` is the expected workflow for batches that pass review.

**Status stored in card JSON**:

```json
{
  "status": "validated",
  "status_history": [
    {"status": "draft", "timestamp": "2026-03-08T14:30:00", "actor": "system", "note": "generated"},
    {"status": "validated", "timestamp": "2026-03-08T15:12:00", "actor": "system", "note": "passed all checks"}
  ],
  "flags": [
    {"category": "balance", "reason": "P/T high for CMC", "reviewer": "alex", "timestamp": "2026-03-08T16:00:00"}
  ],
  "generation_attempt": 1
}
```

### 3A.3 Batch Operations

Three mechanisms for batch operations:

1. **Comma-separated IDs**: `review approve 001,002,003,004`
2. **Filter-based**: `review approve --filter "--color W --rarity common"` (applies the same filters as `review list`)
3. **All with status gate**: `review approve all --from-status validated`

**Safety**:
- Batch operations on more than 5 cards require confirmation prompt (`Approve 42 cards? [y/N]`)
- `--yes` flag skips confirmation (for scripting)
- `--dry-run` flag always available — shows the list of affected cards without making changes
- Reject batch always requires `--reason` (no silent bulk rejections)

### 3A.4 Output Formatting

**Library**: Rich (Python library for terminal formatting).

**Table format rules**:
- Auto-detect terminal width via `shutil.get_terminal_size()`
- Below 80 columns: switch to compact format automatically
- Color coding in card list: white/blue/black/red/green text color matches MTG color identity. Multicolor = gold. Colorless = grey.
- Status color coding: draft=dim, validated=yellow, approved=green, art_generated=cyan, rendered=blue, print_ready=bright green
- Flagged cards get a `⚑` marker in red
- Mana cost symbols rendered as `{W}`, `{U}`, `{B}`, `{R}`, `{G}`, `{C}`, `{X}`, `{1}`, etc. (no Unicode mana symbols in terminal — keep it readable)

**JSON output**: When `--format json` is used, output raw JSON to stdout (no Rich formatting). This enables piping: `mtgai review list --format json | jq '.[] | .name'`.

### 3A.5 Integration Points

**Card data**: CLI reads from `output/sets/<set-code>/cards/<collector_number>_<name_slug>.json`. Each card is one JSON file. The CLI never holds a database — it scans the directory on each invocation. For a 280-card set, this is instantaneous.

**Art files**: Located at `output/sets/<set-code>/art/<collector_number>_<name_slug>_v<attempt>.png`. The card JSON's `art_path` field points to the current version.

**Rendered files**: Located at `output/sets/<set-code>/rendered/<collector_number>_<name_slug>.png`. The card JSON's `render_path` field points to the rendered image.

**Set detection**: If only one set exists in `output/sets/`, use it automatically. If multiple, require `--set-code` or prompt the user to choose.

**Config file**: `output/sets/<set-code>/review_config.json` stores:
- Default reviewer name
- Default sort order
- Any saved filter presets

---

## Phase 3B: HTML Gallery Viewer

### 3B.1 Static Site Generation

**Approach**: Python script using Jinja2 templates generates a self-contained HTML site.

```
mtgai review gallery [OPTIONS]

Options:
  --set-code    TEXT   Set code (default: auto-detect)
  --output, -o  PATH   Output directory (default: output/sets/<code>/gallery/)
  --open        FLAG   Open in default browser after generation
  --watch       FLAG   Watch for file changes and regenerate (optional, see 3B.5)
```

**Generated file structure**:

```
output/sets/ETV/gallery/
├── index.html          # Main gallery page (card grid + filters)
├── cards/
│   ├── 001.html        # Individual card detail pages
│   ├── 002.html
│   └── ...
├── compare.html        # Comparison mode page
├── booster.html        # Sample booster pack viewer
├── art-review.html     # Art consistency review page
├── css/
│   └── style.css       # All styles
├── js/
│   ├── gallery.js      # Filter/sort logic
│   ├── booster.js      # Booster randomization
│   └── compare.js      # Comparison mode logic
└── data/
    └── cards.json      # All card data as JSON (consumed by JS)
```

**Key design decision**: Card data is embedded as a single `cards.json` file that the JavaScript reads. This means filtering and sorting happen client-side with zero server round-trips. For 280 cards, this JSON is ~200-500 KB — trivial.

**Image references**: The HTML references rendered images via relative paths back to `../rendered/`. No image copying — the gallery sits alongside the existing output structure.

### 3B.2 Gallery Features

#### Card Grid (index.html)

The main view. Shows all cards as a responsive grid of rendered card images.

**Layout**:
- Card images displayed at ~250px wide (maintaining aspect ratio)
- Responsive grid: 5-6 cards per row on desktop, 2-3 on mobile
- Hover: card name + key stats overlay
- Click: opens card detail page
- Visual indicators: colored border for status (same scheme as CLI), red glow for flagged cards, dimmed for draft/rejected status

**Filter/Sort Controls** (sticky bar at top):

```
[Color: W U B R G M C All] [Rarity: C U R M All] [Type: ▼ dropdown]
[Status: ▼ dropdown] [CMC: 0-1-2-3-4-5-6-7+] [Keyword: ______ ]
[Sort: Name | CMC | Rarity | Color | # | Status] [↑↓]
[Show: All | Flagged Only | Needs Review]
```

- Filters are toggle buttons (click to activate/deactivate, multiple allowed)
- CMC filter is a range slider or clickable number buttons
- All filtering happens in JavaScript against the embedded `cards.json`
- URL hash updates with current filters (shareable/bookmarkable: `index.html#color=W&rarity=rare`)
- Card count displayed: "Showing 42 of 280 cards"

#### Card Detail View (cards/NNN.html)

Full card information page, accessed by clicking a card in the grid.

**Content**:
- Large rendered card image (if available, else art image, else placeholder)
- All card fields displayed in a readable layout
- Status badge with history timeline
- Flags section (if any)
- Art section: all art attempts as thumbnails (click to enlarge)
- Navigation: Previous/Next card buttons (respecting current filter/sort)
- Quick actions section: shows the CLI commands to approve/reject/flag this card (copy-to-clipboard)

```
┌──────────────────────────────────────────────────┐
│  [← Back to Gallery]    [← Prev]  #001  [Next →] │
│                                                    │
│  ┌─────────────┐   Name: Aetheric Sentinel        │
│  │             │   Cost: {2}{W}                    │
│  │  (rendered  │   Type: Creature — Golem Soldier  │
│  │   card      │   Rarity: Uncommon                │
│  │   image)    │   Set: Echoes of the Void (ETV)   │
│  │             │                                    │
│  │             │   Rules Text:                      │
│  │             │   Vigilance                        │
│  │             │   When Aetheric Sentinel enters,   │
│  │             │   create a 1/1 white Soldier       │
│  │             │   creature token.                  │
│  │             │                                    │
│  │             │   Flavor: "The city's walls have   │
│  │             │   eyes."                           │
│  │             │                                    │
│  │             │   P/T: 3/4                         │
│  └─────────────┘   CMC: 3                          │
│                                                    │
│  Status: validated ●───●───○───○───○───○           │
│          draft  val  app  art  ren  print           │
│                                                    │
│  CLI Commands:                                     │
│  $ mtgai review approve 001    [📋 Copy]           │
│  $ mtgai review reject 001 -r "reason"  [📋 Copy]  │
│  $ mtgai review flag 001 -r "reason"    [📋 Copy]  │
└──────────────────────────────────────────────────┘
```

#### Side-by-Side Comparison Mode (compare.html)

Select 2-4 cards to compare side by side.

**Access**: Click "Compare" checkbox on cards in the grid, then click "Compare Selected" button. Or navigate directly with URL params: `compare.html?cards=001,045`.

**Display**: Cards shown side by side with a diff section below highlighting differences in CMC, P/T, keywords, rarity, and status.

#### Flagged Card Highlighting

Flagged cards in the grid have:
- Red border or red corner badge
- Flag icon with tooltip showing the flag reason
- A dedicated "Flagged Only" filter button for quick access
- Flag count shown in the top stats bar: "7 flagged cards need attention"

#### Sample Booster Pack Viewer (booster.html)

Displays a randomized 15-card booster pack from the set.

**Pack composition** (standard MTG booster):
- 10 Commons
- 3 Uncommons
- 1 Rare (or Mythic at ~1:8 odds)
- 1 Basic Land

**Display**:
- Cards fanned out or in a grid, rendered images
- "Open New Pack" button generates a fresh random pack
- Pack stats sidebar: color breakdown, total CMC, creature count
- Useful for gut-checking: "Does this look like a real booster pack?"

**Shared code**: The pack generation logic lives in `mtgai/packs.py`:

```python
def generate_booster_pack(cards: list[Card], seed: int | None = None) -> list[Card]:
    """Generate a randomized booster pack following standard MTG distribution."""
```

This function is called by:
- `booster.js` (via the embedded `cards.json` — JS reimplementation of the same logic)
- Phase 4B's sealed pool generator (Python, calls the function directly)

To keep them in sync: the Python version is canonical. The JS version in `booster.js` is a lightweight port. If they ever diverge, Phase 4B's analysis is authoritative.

### 3B.3 Technology Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Template engine | Jinja2 | Already in Python ecosystem, familiar syntax, no extra dependencies |
| Styling | Vanilla CSS | Simple grid layout, no framework needed. CSS Grid + Flexbox. Dark theme (easy on eyes for long review sessions) |
| Interactivity | Vanilla JavaScript | Filter/sort on 280 cards is trivial. No React/Vue overhead. |
| Icons | Inline SVG | Mana symbols, flag icons, status dots. No icon font dependency. |
| Data | Embedded JSON | Single `cards.json` loaded once, all operations client-side |
| Image display | CSS object-fit | Responsive card image sizing with proper aspect ratios |

**Total JS**: Estimated ~300-500 lines across all files. This is not a web app — it's an interactive document.

**CSS dark theme**: Default dark background (#1a1a2e or similar), light text. Card images pop against dark backgrounds. Optional light theme toggle stored in `localStorage`.

### 3B.4 Art Review Mode (art-review.html)

A dedicated page for reviewing art consistency across the set.

**Layout**: Large grid of just the art images (not rendered cards), grouped by:
- Color (all white cards together, all blue, etc.)
- Card type (all creatures, all spells, all lands)
- Artist prompt style (if different style prompts were used)

**Purpose**: Spot outliers — one card's art that looks wildly different from the rest of its color or type. Catch style inconsistencies before rendering.

**Features**:
- Toggle between art-only and rendered-card views
- Zoom: click any art to see it full-size in a lightbox
- Side-by-side: select two arts to compare directly
- Notes panel: displays any art-related flags from the card data

### 3B.5 Auto-Regeneration

**Default: No auto-regeneration.** Run `mtgai review gallery` manually to regenerate.

**Optional watch mode**: `mtgai review gallery --watch` uses `watchdog` (Python file watcher library) to monitor `output/sets/<code>/cards/` and `output/sets/<code>/rendered/` directories. On change, regenerate the gallery. This is useful during active art generation when images are appearing one by one.

**Implementation**:
- `watchdog` is an optional dependency (not required for basic use)
- Watch triggers a debounced regeneration (wait 2 seconds after last change before rebuilding)
- Only regenerate affected card detail pages + the main index (incremental rebuild)
- Print a message to terminal: "Gallery updated — 3 cards changed"

**Why not LiveReload in the browser?** That requires injecting a WebSocket client into the HTML and running a server. Too much complexity. The user can just refresh the browser tab after seeing the "Gallery updated" terminal message.

### 3B.6 Deployment / Serving

**Primary**: Just open `index.html` directly in a browser. Modern browsers handle local file:// access for static content fine.

**If file:// causes CORS issues with JSON loading**: Serve with Python's built-in HTTP server:

```bash
cd output/sets/ETV/gallery/
python -m http.server 8080
# Open http://localhost:8080
```

**Convenience**: The `--open` flag on `mtgai review gallery` auto-opens the browser:
```bash
mtgai review gallery --open
# Generates gallery, then opens http://localhost:8080 in default browser
# (starts python -m http.server in background if needed)
```

No Docker, no nginx, no deployment pipeline. This is local tooling.

---

## Implementation Plan

### File Structure

```
mtgai/
├── cli/
│   ├── __init__.py
│   ├── main.py              # Typer app entry point, command group registration
│   └── review/
│       ├── __init__.py
│       ├── list_cmd.py       # review list
│       ├── show_cmd.py       # review show
│       ├── stats_cmd.py      # review stats
│       ├── approve_cmd.py    # review approve
│       ├── reject_cmd.py     # review reject
│       ├── flag_cmd.py       # review flag
│       ├── compare_cmd.py    # review compare
│       ├── export_cmd.py     # review export
│       ├── art_cmd.py        # review art
│       └── gallery_cmd.py    # review gallery (triggers 3B generation)
├── review/
│   ├── __init__.py
│   ├── card_loader.py        # Load card JSON files from output directory
│   ├── card_filter.py        # Filtering logic (shared by CLI and gallery)
│   ├── status.py             # Status transition logic + validation
│   ├── formatters.py         # Rich table/panel formatting for CLI output
│   └── audit.py              # Audit trail (status history, reviewer tracking)
├── gallery/
│   ├── __init__.py
│   ├── generator.py          # Main gallery generation orchestrator
│   ├── watcher.py            # File watcher for --watch mode (optional)
│   └── templates/
│       ├── base.html         # Jinja2 base template (head, nav, footer)
│       ├── index.html        # Card grid page
│       ├── card_detail.html  # Individual card page
│       ├── compare.html      # Comparison mode
│       ├── booster.html      # Booster pack viewer
│       ├── art_review.html   # Art consistency review
│       └── static/
│           ├── style.css
│           ├── gallery.js
│           ├── booster.js
│           └── compare.js
├── packs.py                  # Booster pack generation (shared: 3B + 4B)
└── models/
    └── card.py               # Card data model (Pydantic, from Phase 0C)
```

### Implementation Order

**Phase 3A tasks** (numbered for sequencing, but most can parallelize after 3A-1):

| Task | Description | Depends On | Estimate |
|------|-------------|------------|----------|
| 3A-1 | Card loader + filter module (`review/card_loader.py`, `card_filter.py`) | Phase 0C card schema | Core dependency for everything |
| 3A-2 | Status transition engine (`review/status.py`, `audit.py`) | 3A-1 | Small, self-contained |
| 3A-3 | Rich formatters (`review/formatters.py`) | 3A-1 | Table + panel rendering |
| 3A-4 | `review list` command | 3A-1, 3A-3 | Most-used command, build first |
| 3A-5 | `review show` command | 3A-1, 3A-3 | Second most-used |
| 3A-6 | `review stats` command | 3A-1, 3A-3 | Dashboard stats |
| 3A-7 | `review approve` + `reject` + `flag` commands | 3A-1, 3A-2 | Status mutation commands |
| 3A-8 | `review compare` command | 3A-1, 3A-3 | Side-by-side |
| 3A-9 | `review export` command | 3A-1 | Export formats |
| 3A-10 | `review art` command | 3A-1 | Art file info + open |

**Phase 3B tasks**:

| Task | Description | Depends On | Estimate |
|------|-------------|------------|----------|
| 3B-1 | Gallery generator scaffolding (`gallery/generator.py`) | 3A-1 | Jinja2 setup, output structure |
| 3B-2 | Base template + CSS (`base.html`, `style.css`) | — | Dark theme, responsive grid |
| 3B-3 | Card grid page (`index.html` template + `gallery.js`) | 3B-1, 3B-2 | Main gallery with filters |
| 3B-4 | Card detail pages (`card_detail.html` template) | 3B-1, 3B-2 | Individual card view |
| 3B-5 | Booster pack viewer (`booster.html` + `booster.js` + `packs.py`) | 3B-1, 3B-2 | Shared pack generation |
| 3B-6 | Comparison mode (`compare.html` + `compare.js`) | 3B-1, 3B-2 | Multi-card compare |
| 3B-7 | Art review page (`art_review.html`) | 3B-1, 3B-2 | Art consistency grid |
| 3B-8 | `review gallery` CLI command | 3B-1, 3A-1 | CLI entry point for generation |
| 3B-9 | File watcher (optional) (`gallery/watcher.py`) | 3B-1 | `--watch` mode with watchdog |

### Dependencies (Python packages)

```
# Phase 3A
typer[all] >= 0.9      # CLI framework (includes Rich, Click)
rich >= 13.0           # Terminal formatting (pulled in by typer[all])

# Phase 3B
jinja2 >= 3.1          # Template engine for HTML generation

# Optional
watchdog >= 3.0        # File watcher for gallery --watch mode
```

### Testing Strategy

| Test Type | What | How |
|-----------|------|-----|
| Unit | Card filtering logic | pytest: filter by color/rarity/type/CMC/keyword against fixture cards |
| Unit | Status transitions | pytest: valid transitions succeed, invalid ones raise errors, history is recorded |
| Unit | Booster pack generation | pytest: pack has correct rarity distribution, no duplicates, correct count |
| Unit | Export formats | pytest: CSV has correct columns, JSON is valid, Cockatrice XML validates |
| Integration | CLI commands | pytest + typer.testing.CliRunner: invoke commands, check stdout output |
| Integration | Gallery generation | pytest: generate gallery from fixture data, verify HTML files exist and contain expected content |
| Manual | Gallery visual review | Open generated gallery in browser, check layout, filters, navigation |

**Fixture data**: Create a set of ~20 mock cards covering all colors, rarities, types, and statuses. Used by all tests. Located in `tests/fixtures/mock_set/`.

---

## Open Questions for Implementation

1. **Card JSON schema finalization**: The exact field names and structure are defined in Phase 0C. The review tools consume this schema — they don't define it. Phase 3 implementation should wait for 0C to lock the schema, or use a preliminary version and adapt.

2. **Mana symbol rendering in HTML**: The gallery needs to render `{W}`, `{U}`, etc. as colored circles. Options: (a) use the Mana font by Andrew Gioia (web font, free), (b) inline SVG for each symbol, (c) simple colored CSS circles with letter. Recommendation: **Mana font** if licensing allows, otherwise CSS circles.

3. **Image placeholder strategy**: Before art/renders exist, the gallery needs placeholders. Options: (a) colored rectangle matching card color identity, (b) text-only card representation, (c) skip unrendered cards. Recommendation: **(a) colored placeholder** with card name overlaid — the gallery should be usable before any art exists.

4. **Performance at scale**: 280 card images in one page could be slow. Lazy loading (`loading="lazy"` attribute on `<img>`) handles this natively in modern browsers. No JavaScript lazy loading library needed.
