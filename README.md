# MTGAI — AI-Powered Magic: The Gathering Set Creator

Build complete custom Magic: The Gathering sets from scratch — from set design through card generation, AI art creation, card rendering, and physical printing. Python backend, CLI-first with HTML gallery for visual review.

## Current State

**Dev set "Anomalous Descent" (ASD)** — 66-card development set (60 main + 6 lands) through the full pipeline:

- **Set Design** — skeleton generator with slot allocation matrix, 10 draft archetypes, 3 custom mechanics
- **Card Generation** — Opus 4.6 with validation library (8 validators, 18 auto-fixers), tiered AI review (council + iteration)
- **Art Generation** — Flux.1-dev via local ComfyUI, Haiku vision-based art selection, PuLID character identity
- **Card Rendering** — M15 frame compositing with SVG mana symbols, dynamic text sizing, bold fonts, shrink-to-fit

### Custom Mechanics
| Mechanic | Colors | Description |
|----------|--------|-------------|
| **Salvage X** | W/U/G | Look at the top X cards of your library, put an artifact into your hand |
| **Malfunction N** | W/U/R | Enters with malfunction counters, can't attack/block until removed |
| **Overclock** | U/R/B | Exile a card from hand as additional cost for a bonus effect |

### Pipeline Phases
| Phase | Status | Description |
|-------|--------|-------------|
| 0A-0E | Done | Research, setup, LLM strategy, prompt engineering |
| 1A | Done | Set skeleton generator (60-card dev set) |
| 1B | Done | Mechanic designer + A/B test of 9 review strategies |
| 1C | Done | Card generation pipeline + validation library |
| 4A+4B | Done | Balance analysis + AI design review (tiered council) |
| 2A | Done | Art direction, style guide, character portraits, PuLID |
| 2B | Done | Batch art generation (198 images via Flux.1-dev local) |
| 2C | **In Progress** | Card renderer — iteration 3 complete |
| 3A/3B | Planned | CLI review tools + HTML gallery |
| SC | Planned | Scale-up to ~280 cards |
| 5A-5C | Planned | Print files, ordering, assembly |

## Project Structure

```
MTGAI/
├── backend/mtgai/          # Python backend
│   ├── models/             # Pydantic data models (Card, Set, Mechanic)
│   ├── generation/         # LLM card generation + validation-retry pipeline
│   ├── validation/         # 8 validators, 18 auto-fixers
│   ├── review/             # AI review pipeline (council + iteration)
│   ├── analysis/           # Balance analysis (CMC curve, removal density, etc.)
│   ├── art/                # Art prompt builder, ComfyUI integration, art selector
│   ├── rendering/          # Card renderer (Pillow + pycairo SVG symbols)
│   └── skeleton/           # Set skeleton generator
├── assets/                 # Fonts, frame templates, symbols
│   ├── fonts/              # Cinzel, EB Garamond, Montserrat, Beleren, MPlantin
│   ├── frames/m15/         # M15 frame PNGs (2010x2814 RGBA, from Card Conjurer)
│   └── symbols/            # Mana SVGs, set symbol
├── output/sets/ASD/        # Generated content for dev set
│   ├── cards/              # Card JSON files (version-controlled)
│   ├── art/                # AI-generated art (gitignored)
│   ├── renders/            # Rendered card images (gitignored)
│   └── reports/            # HTML comparison pages, balance reports
├── research/               # Set design research, LLM strategy, experiments
├── learnings/              # Per-phase learnings documents
├── plans/                  # Phase plans + TRACKER.md (master progress)
└── config/                 # Print specs, settings
```

## Development

```bash
# Prerequisites: Python 3.12+, uv
cd backend

# Install dependencies
uv pip install -e ".[dev]"

# Run tests (548+ tests)
pytest

# Lint
ruff check . && ruff format .

# Render all cards
python -m mtgai.rendering --set ASD --force

# Run balance analysis
python -m mtgai.review balance --set ASD

# Run AI review
python -m mtgai.review ai-review --set ASD
```

## Architecture

### LLM Usage
- **Opus 4.6** — card generation (effort=max), AI design review (council + iteration)
- **Haiku** — art prompts, reprint selection, art quality judging
- **Prompt caching** — system prompt + tool schema cached for 90% input token discount
- **Structured output** — all LLM calls use `tool_choice` for guaranteed JSON

### Card Renderer
- Composites card data + AI art + M15 frame templates into print-ready PNGs
- SVG mana symbol rendering via pycairo (cairosvg unavailable on Windows)
- Dynamic text sizing with shrink-to-fit for name/type lines
- Renders at native 2010x2814, scales to 822x1122 (300 DPI, MPC poker-size)

### Validation Pipeline
- 8 validators: schema, mana, type_check, rules_text, power_level, color_pie, text_overflow, uniqueness
- 18 auto-fixers for deterministic corrections (AUTO severity)
- MANUAL errors feed structured retry prompts back to the LLM
- Reminder text injected programmatically after AI review (not LLM-generated)

## Total API Cost

~$13.12 through Phase 2C for 66-card dev set:
- Card generation: $2.78 (Opus 4.6)
- AI review: $0.58 (Haiku)
- Skeleton revision: $3.45 (Opus + Haiku)
- Art prompts: $0.40 (Haiku)
- Art selection: $0.37 (Haiku)
- Research/experiments: ~$5.54

## License

Private project — not for redistribution. MTG is a trademark of Wizards of the Coast.
