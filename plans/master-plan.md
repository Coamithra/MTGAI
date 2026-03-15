# MTG AI Set Creator - Master Plan

## Context
Build a complete Magic: The Gathering custom set creator — from initial set design through card generation, art creation, card rendering, and physical printing. Greenfield project. Location: Holland (Netherlands).

## Phase Status

| Phase | Status | Notes |
|-------|--------|-------|
| 0A Set Design Research | COMPLETE | 5-set analysis, distribution targets |
| 0B Technical Research | COMPLETE | Flux + Pillow/Cairo, MPC, fonts, print specs locked |
| 0C Project Setup | COMPLETE | uv, Ruff, pytest, Pydantic models, CI |
| 0D LLM Strategy | COMPLETE | Sonnet for cards, Haiku for art prompts, batch-5 |
| 0E Prompt Spike | COMPLETE | T=1.0, zero-shot, tool_use, effort=max. GO gate passed |
| 1A Skeleton Generator | COMPLETE | 60-card dev set, CLI (list/show/stats), 75 tests |
| 1B Mechanic Designer | COMPLETE | Salvage, Malfunction, Overclock. A/B test of 9 review strategies |
| 1C Card Generator | COMPLETE | 60 cards, $2.78, zero failures. Validation library (8 validators, 18 fixers) |
| 1C Human Review | COMPLETE | See learnings/phase1c.md for findings |
| 4A Balance + Revision | COMPLETE | Balance analysis + skeleton revision pipeline. 2 bugs found & fixed in prompt pipeline. Mechanic targets met. |
| 4B AI Design Review | COMPLETE | 59 cards reviewed (Haiku, $0.58), 6 changed, 58 OK / 1 REVISE. Post-review finalization done: reminder injection + auto-fixes. 2 validator bugs fixed. |
| 4AB Human Review Gate | IN PROGRESS | Card-by-card "art ready" review. Gallery built for visual review. |
| 2A Art Direction | IN PROGRESS | Style guide + prompts done. ComfyUI + Flux pipeline built. Batch generation running (66×3 images). |
| 2B-5C | NOT STARTED | |

## Key Decisions
- **Stack**: Python backend (FastAPI) + lightweight review UI (CLI primary, simple HTML viewer for visual review)
- **Print**: Both draft set (24 boosters for 8-player pod) and full playset (4x common/uncommon/rare, 2x mythic — configurable)
- **Validation**: Statistical analysis only (no game simulation)
- **Card variants**: Deferred to V2+ (standard frames only for V0/V1)
- **Art generation**: ChatGPT Plus or Midjourney subscription (~$20/mo) — sufficient for 300+ images with daily credit renewal
- **Art budget**: ~$50-80 per set (LLM costs + subscription)
- **GPU**: NVIDIA 8GB+ VRAM available for local image generation
- **Data storage**: JSON files (no database — data is essentially static once generated)

---

## Phase 0: Research Sprint

> **Iterative loop for every sub-phase**: Research -> Document -> Verify -> Store Learnings

### 0A: MTG Set Design Research
**3 parallel research agents:**

| Agent | Focus | Sources |
|-------|-------|---------|
| 1 - Set Structure | Card counts, rarity distribution, color distribution, card type spread, mana curve | Scryfall API data pulls (free, 10 req/sec rate limit), MTG wiki |
| 2 - Mechanics & Balance | Evergreen keywords (current list), new mechanics per set, legendary/planeswalker counts, color pie rules, draft archetype patterns | Mark Rosewater articles, WotC design docs |
| 3 - Design Philosophy | New World Order, as-fan, how themes connect to mechanics, storytelling through cards | Rosewater "Making Magic" columns, GDS articles |

**Data sources**: Scryfall API is free and well-documented. Alternatives if needed: MTGJSON (bulk data downloads, no API needed), MTG GraphQL (community API).

**Additional data points**: removal density per color, as-fan calculations, subtype frequency, multicolor pair distribution, DFC/special layout prevalence.

**Verification**: Pull actual data for 5 recent sets (Duskmourn, Bloomburrow, Thunder Junction, Karlov Manor, Lost Caverns of Ixalan) and cross-check all numbers. Store raw Scryfall data in `data/scryfall/` for reuse by Phases 0C (schema validation), 0E (few-shot examples), 1C (reprint selection), and 4 (benchmarking).
**Output**: `research/set-design.md` + `research/set-template.json` (reusable structure template)
**Learnings -> `learnings/phase0a.md`**

### 0B: Technical Research
**3 parallel research agents:**

| Agent | Focus | Key Questions |
|-------|-------|---------------|
| 1 - Image Generation | ChatGPT Plus (DALL-E) vs Midjourney subscription. Quality comparison, character reference workflows, style variation techniques, aspect ratio control. Fallback: local models (SD, SDXL, Flux on 8GB+ GPU) | Which subscription produces the best fantasy card art? How well do character references work? How many images per day with credit renewal? |
| 2 - Card Rendering | Frame templates, dimensions (63x88mm), open-source tools (Proxyshop, cardconjurer), mana/tap symbols, set symbol creation. **Font alternatives** (see below) | What's the best library/approach for programmatic card rendering in Python? |
| 3 - Printing | Services shipping to NL (MakePlayingCards, PrinterStudio, Game Crafter, EU alternatives). File specs, card stock, costs, booster packs vs full sets | Can we order randomized boosters? What file format/DPI/bleed do they need? What does a full playset cost? |

**Font licensing**: Beleren and MPlantin are proprietary WotC fonts. Research open-source alternatives:
- Beleren alternatives: e.g., Planewalker (fan-made), Crimson Text, or other serif display fonts
- MPlantin alternatives: e.g., Plantin-like free serifs, EB Garamond, or Crimson Pro
- Mana/tap symbols: likely available via community projects (e.g., Keyrune, Mana font by Andrew Gioia)

**Print specs must be locked down here** — DPI, bleed, color space, and file format requirements feed directly into Phase 2C. This phase is a **hard dependency** for the renderer.

**Rendering stack**: Pillow for image composition, Cairo/Pango for text layout (best rich text support: inline symbols, italic reminder text, dynamic sizing).

**Verification**: Build a 1-card proof-of-concept: generate art -> render card -> export print-ready file. Include a placeholder set symbol.
**Output**: `research/tech-decisions.md` with comparison tables and final recommendations
**Learnings -> `learnings/phase0b.md`**

### 0C: Project Setup
- Initialize Python project (uv for deps, Ruff for linting, pytest for testing)
- Monorepo structure: `backend/`, `research/`, `learnings/`, `output/`, `data/scryfall/`, `config/`
- **Shared config system** (`pydantic-settings`): `config/print-specs.json`, `config/card-layout.json`, `config/fonts.json`, `config/symbols.json`
- **Text overflow constants** (max characters per field, font size assumptions) — defined here so they feed into prompt constraints before card generation starts
- **Card data schema** (first-class deliverable — all downstream systems depend on this):
  - Card: name, mana_cost, type_line, subtypes, supertypes, rules_text, flavor_text, power, toughness (strings, for `*/*`), loyalty, rarity, color_identity, collector_number, artist, art_path, render_path, draft_archetype, mechanic_tags, slot_id, is_reprint, scryfall_id, design_notes, art_prompt
  - Set: name, code, theme, description, cards[], mechanics[]
  - Mechanic: name, reminder_text, colors[], rarities[]
  - GenerationAttempt: input_tokens, output_tokens, cost_usd, prompt_version (alongside existing attempt tracking)
  - Validate schema against Scryfall's data model for compatibility
- **State management** (cards move through a pipeline — track where each one is):
  - Card status field: `draft` → `validated` → `approved` → `art_generated` → `rendered` → `print_ready`
  - Resumable pipeline: if art generation fails at card 150/280, resume from card 151
  - Each generation/render attempt tracked (attempt number, timestamp, prompt used)
  - Naming convention: `<collector_number>_<card_name_slug>_v<attempt>.{json,png}`
- **Binary file strategy**: `.gitignore` art and rendered images; they live in `output/` only. Card JSON is version-controlled.
- Data stored as JSON files in `output/sets/<set-code>/`
- CI: GitHub Actions for lint + test
- `CLAUDE.md` with project conventions

**Test**: Skeleton builds, lint passes, test runner works, schema validates against sample data.
**Learnings -> `learnings/phase0c.md`**

### 0D: LLM & AI Strategy Research
**Goal**: Define exactly how AI/LLMs are used throughout the pipeline.

**Research areas:**
- **Model selection**: Which LLM for card design? (Claude, GPT-4, local models?) Cost per set estimation
- **Structured output**: Use LLM tool use / function calling for card generation — guarantees schema validity, preferred over raw JSON mode
- **Prompting strategy**: Batch of 5 cards as default generation size (best tradeoff between context awareness, cost, and quality). Few-shot examples from real cards
- **Rules text enforcement**: How to ensure generated rules text follows MTG grammar — post-processing, constrained generation, validation + retry loops
- **Iteration workflow**: What happens when a generated card fails validation? Auto-retry with feedback? Human edit? How many retries before flagging?
- **Art prompt generation**: Use a cheaper model (GPT-4o-mini or Haiku) for art prompt generation — doesn't need an expensive model
- **Token budget**: Estimate total tokens needed for a full ~280-card set. Target ~$5-10/set for LLM costs
- **Reproducibility**: Seeding, temperature settings, saving prompts alongside outputs for iteration

**Output**: `research/llm-strategy.md` with model recommendations, prompt templates, cost breakdown
**Learnings -> `learnings/phase0d.md`**

### 0E: Prompt Engineering Spike
**Goal**: Validate LLM card generation quality before building the full pipeline.

- Generate ~20 cards across different rarities, colors, and types using the strategy from 0D
- Evaluate rules text correctness (MTG grammar: `"When ~ enters..."`, `"Target creature gets +X/+Y until end of turn."`)
- Test few-shot example effectiveness — how many examples needed per generation call?
- Test single-card vs batch generation (quality vs cost tradeoff)
- Test how to maintain set context — cards need awareness of what's already generated (avoiding duplicates, ensuring archetype support) without blowing the context window
- Test mana cost / power level consistency enforcement
- **Prototype validation-retry loop** — the retry loop is critical infrastructure; testing it here catches issues before Phase 1C relies on it
- Iterate on prompts until generation quality is acceptable

**Output**: Proven prompt templates saved in `research/prompt-templates/`, quality assessment of ~20 generated cards
**Learnings -> `learnings/phase0e.md`**: What prompt patterns work, failure modes, required retries per card type

---

## Phase 1: Set Design Engine

### 1A: Set Skeleton Generator
**Goal**: Given a theme, generate the structural backbone of a set.

- **Input**: theme name, flavor description, card count target, special constraints
- **Output**: Slot allocation matrix — how many cards per (color x rarity x type x CMC range)
- Enforce balance rules from Phase 0A research
- Define 10 draft archetypes (one per color pair)
- Assign mechanic slots (which rarities/colors get which mechanics)
- **CLI architecture design** (Typer-based): Define the full command group structure here even if most commands are stubs — avoids refactoring when Phase 3A extends it
- **Minimal CLI review tool** (needed for reviewing generated cards throughout Phase 1):
  - `python -m mtgai.review list` — list cards with filtering (color, rarity, type, status)
  - `python -m mtgai.review show <card>` — pretty-print all card fields
  - `python -m mtgai.review stats` — set statistics summary (rarity counts, color distribution, mana curve)
  - This minimal toolset is used throughout 1B and 1C; expanded into full review tools in Phase 3

**Test**: Unit tests for all constraints. Compare output against real set distributions.
**Review**: Human review of skeleton via CLI.
**Learnings -> `learnings/phase1a.md`**: Tune balance parameters.

### 1B: Mechanic Designer
**Goal**: AI-assisted creation of set-specific mechanics (using strategy from Phase 0D).

- Generate 2-4 new keyword/ability mechanics fitting the theme
- Validate against color pie rules
- Assign evergreen keywords per color
- Define mechanic distribution across rarities
- Rules text templates for each mechanic

**Test**: Rules text syntax validation. Color pie compliance checks.
**Review**: Human approval of each mechanic before card generation uses them.
**Learnings -> `learnings/phase1b.md`**: Mechanic patterns that work vs don't.

### 1C: Card Generator
**Goal**: AI-assisted generation of individual cards filling skeleton slots (using strategy from Phase 0D + proven prompts from Phase 0E).

- Card name, type line, mana cost, abilities, flavor text, P/T
- Proper MTG rules text templating (keyword formatting, reminder text)
- Power level appropriate to rarity and CMC
- Legendary creatures, planeswalkers (with loyalty abilities), special designs
- **Reprints**: Sets regularly include reprints of existing cards. Support selecting existing cards from Scryfall/MTGJSON data to fill skeleton slots (e.g., staple commons, mana fixing lands, removal spells). Reprints use original card data but get new art generated for the set's visual identity
- Validation + retry loop for cards that fail checks (per 0D strategy)

**Validation library** (`mtgai.validation`) — built here, reused by Phase 4 for full-set reports:
- Rules text parser (valid MTG grammar)
- Balance scorer (flag outliers per rarity/CMC)
- Uniqueness checker (no duplicate/near-duplicate cards)
- **Text overflow estimator** (will it fit on the card?)
- Color pie violation detector
- Spell check on all text fields
- Each validator runs on every generated card; failures trigger retry with feedback before flagging for human review

**Review**: Human review via CLI card viewer (from 1A) + HTML gallery.
**Learnings -> `learnings/phase1c.md`**: Common generation mistakes, prompt refinements.

**1C Review Findings** (dev set, 60 cards):
- Mechanics are conceptually distinct and fun, but distribution is wrong: Salvage over-represented (~12 cards vs planned 6), Malfunction (1 vs 5) and Overclock (1 vs 3) under-represented
- Missing multicolor signposts for UR/UG/BR/BG/RG and missing legendaries are **60-card budget effects** — auto-resolve at ~280 cards
- Pipeline gaps that do NOT auto-resolve at scale (see Phase SC below):
  1. **Mechanic-to-slot assignment**: skeleton says "complex", generator picks Salvage every time. Gets worse at scale.
  2. **Constraint derivation**: no step to analyze what mechanics structurally require (e.g., Salvage needs more artifacts)
  3. **Legend-to-slot mapping**: generator puts characters in wrong colors (Feretha planned UB, generated mono-W)
  4. **Notable card enforcement**: named artifacts/lands from theme.json not guaranteed
  5. **Planeswalker slot**: no explicit reservation
- Cards flagged for Phase 4A+4B AI review: Koyl Yrenum (color pie violations), Cult Savant (reanimation in blue), Law of the Wilderness (uncommon too powerful), Automated Sentry Grid (oppressive), Feretha (wrong colors), Reclaim the Surface (too narrow for common), Raider's Bounty (too punishing)

---

## Phase 2: Art & Rendering Pipeline

### 2A: Art Direction System
**Goal**: Consistent visual identity for the set.

- Define style guide: color palette, mood, setting, artistic style
- Create prompt templates per card type (creature, spell, land, etc.)
- Generate 10 sample arts, evaluate consistency
- Iterate on prompt engineering until style is cohesive

**Art generation approach**: ChatGPT Plus or Midjourney subscription (~$20-40/mo, may need 2 months for daily limits). Art prompts generated by a cheaper model (GPT-4o-mini or Haiku).
- Daily credit renewal means ~300 cards is feasible spread over multiple days
- **Character consistency via reference images**: Generate character reference art first, then feed it back to the model ("use this character reference") for all cards featuring that character
- **Varied artist styles are a feature, not a bug**: Real MTG sets have different artists per card. Rather than fighting for perfect consistency, lean into varied styles — each card can feel like a different artist's interpretation. Optionally add deliberate style variation prompts to simulate different artists
- **Go/no-go gate**: After generating 20 sample arts across card types, evaluate quality. If insufficient for the target quality bar, reassess approach before committing to 280+ generations

**Cohesive set identity** (varied styles doesn't mean random):
- Shared color palette and mood across all prompts
- Consistent world-building elements (architecture, flora, fauna, clothing styles)
- Lighting and composition guidelines per card type

**Test**: Side-by-side comparison of 10+ samples across different card types. Resolution and aspect ratio checks. Human evaluation of cohesion.
**Review**: Human picks best style direction.
**Learnings -> `learnings/phase2a.md`**: Best prompt patterns per card type, consistency techniques that work.

### 2B: Art Generation Pipeline
**Goal**: Generate art for all ~280+ cards.

- Batch generation with rate limiting and error handling
- Quality scoring (automated: resolution, artifacts, aspect ratio)
- Regeneration workflow for rejected art
- Post-processing: crop, color correct, upscale if needed

**Test**: Automated QA on every image (resolution, aspect ratio, file size).
**Review**: Human review via HTML gallery — approve/reject/regenerate per card.
**Learnings -> `learnings/phase2b.md`**: Which prompts/models produce best results by card type.

### 2C: Card Renderer
**Goal**: Combine card data + art into print-ready images.

**Hard dependency**: Print specs from Phase 0B must be finalized before this phase starts.

**Standard frames (V0/V1):**
- Per color (W/U/B/R/G), multicolor (gold), artifact (grey), land
- Planeswalker frame, Saga frame (if applicable)
- Proper text layout: name, mana cost, type line, rules text, flavor text, P/T, artist credit, collector info

**Rendering stack**: Pillow for image composition, Cairo/Pango for text layout (inline symbols, italic reminder text, dynamic sizing).

**Technical requirements** (driven by printer specs from 0B):
- **Dual resolution output**: screen-resolution (72 DPI) for review, print-resolution (300+ DPI, CMYK, 3mm bleed) for export
- Open-source alternative fonts (from 0B research)
- Mana symbols, tap symbol, set symbol with rarity color
- Collector number, set code, language indicator, artist credit
- **Proxy render mode**: text-only card rendering without art for early pipeline testing (enables full pipeline validation before art generation)

**Custom card back:**
- MTG card back style but with custom set branding
- Clear "Custom/AI-Generated" indicator to distinguish from real cards

**Test**:
- **Text overflow detection** on every single card
- Symbol rendering validation
- Print spec compliance (DPI, dimensions, color space, bleed)
- Home-print test batch (~10 cards) to check sizing/readability

**Learnings -> `learnings/phase2c.md`**: Rendering edge cases and fixes.

---

## Phase 3: Review & Human-in-the-Loop

> Lightweight tooling — CLI primary, simple HTML viewer for visual review. Full UI only if this proves insufficient.

### 3A: CLI Review Tools (extends minimal CLI from Phase 1A)
- Batch approve/reject/flag commands (card status transitions)
- Side-by-side card comparison
- Export commands (print files, card list CSV, full set JSON)
- Art review integration (show card data alongside art file path/thumbnail)

### 3B: HTML Gallery Viewer
- Static HTML generation showing all cards as rendered images
- Filter/sort by color, rarity, type, CMC
- Side-by-side view for art consistency review
- Flagged cards highlighted
- Sample booster pack viewer
- Regenerate from the gallery? Only if CLI workflow proves painful

**Test**: Validation tests for card data integrity. Manual review of HTML output.
**Learnings -> `learnings/phase3.md`**

---

## Phase 4: Full-Set Validation Report

> **Important**: The validation checks below are built as a **shared library** (`mtgai.validation`) during Phase 1, not Phase 4. Phase 1C uses these checks as generation-time gates (validate each card on creation, retry on failure). Phase 4 simply runs the full suite on the completed set and generates the report.

### 4A: Balance Analysis
- Mana curve distribution per color (compare to target)
- Creature P/T vs CMC analysis
- Removal spell density
- Card advantage sources per color
- Rarity power level distribution
- Keyword/mechanic frequency (as-fan calculations)

### ~~4B: Limited Environment Analysis~~ — CUT
> Sealed pool sims, booster composition checks, and draft archetype analysis removed from the critical path. Rationale: if the skeleton is well-designed and card generation follows it, Limited viability is guaranteed by construction. Sealed sims on the 60-card dev set are meaningless (need 90+ cards per pool), and at 280 cards they'd mostly confirm what the skeleton already enforces. The AI design review (4B-review) catches actual card quality issues far more effectively. Pack generator can be built later as a polish step before printing if desired.

### 4C: Quality Checks
- Rules text grammar validation
- Spell check across all card text
- Duplicate/near-duplicate detection
- Flavor text quality check
- Cross-card interaction sanity checks (no infinite combos at common, etc.)

**Output**: Full-set validation report with pass/fail per check, flagged cards for review. This should be a quick run, not a major phase — the hard work is building the validators in Phase 1.
**Learnings -> `learnings/phase4.md`**: Common validation failures, tuning thresholds.

---

## Phase SC: Scale-Up to Full Set (~280 cards)

> **Prerequisites**: Phase 4A+4B balance gate passed on dev set, pipeline improvements applied.

### Skeleton Generator Improvements (before regenerating at scale)

These are pipeline gaps identified during 1C review that get **worse** at scale:

1. **Mechanic-to-slot assignment**: Tag "complex" slots with specific set mechanics (`salvage`, `malfunction`, `overclock`) based on the approved distribution and color alignment. Currently the skeleton only assigns complexity tiers — the LLM picks freely and gravitates to the simplest mechanic.

2. **Constraint derivation step**: After set design defines theme + mechanics, analyze what the mechanics structurally require and output skeleton adjustments. E.g., Salvage tutors for artifacts → increase artifact density. This is an LLM revision pass on the skeleton itself (see `learnings/phase1c.md` for full design).

3. **Legend-to-slot mapping**: Map specific characters from `theme.json` to specific multicolor slots with correct color identity. Prevents Feretha (planned UB) ending up mono-W.

4. **Notable card slot reservation**: Reserve skeleton slots for named cards from `theme.json` (planeswalker, named artifacts/lands like Fereyn's Stone Head, God's Eye, Bank Inviolable).

5. **Planeswalker slot**: Explicit reservation — the current allocation logic never produces one.

### Scale-Up Generation
- Expand skeleton to ~280 cards (all 10 signpost uncommons, all legendaries, full artifact suite)
- Generate remaining cards with improved skeleton constraints
- Full balance analysis (100+ sealed pools, all 10 archetypes)
- Art generation for all cards

## Phase 5: Print Preparation & Delivery

### 5A: Print File Generation
- Export all cards as print-ready images (per printer specs locked in 0B)
- Generate card sheets if required by printer
- Card back file
- **Draft set**: Randomize cards into 24 booster packs (8-player pod) using classic Draft Booster format (10C + 3U + 1R/M + 1 basic land each — simpler than Play Boosters for a custom set)
- **Full playset**: 4x each common/uncommon/rare, 2x each mythic (configurable), basic lands (20 with custom art, 4 per color)
- **Cost calculator**: Estimate total print cost (card count x unit price) before committing to order
- Generate order manifest (card list, quantities, file mapping)

### 5B: Print Order (Semi-Manual)
- Step-by-step guide generated for the chosen print service
- File upload checklist
- Card stock and finish recommendation
- **Test batch first**: Order ~20 cards to verify quality before full order
- After test batch approval, place full order

### 5C: Assembly
- Sorting guide (organize printed cards by collector number)
- Set guide insert (set name, mechanics overview, draft archetype summary)
- Box label templates

**Learnings -> `learnings/phase5.md`**: Print service experience, quality notes.

---

## Budget Estimates

| Category | Estimate | Notes |
|----------|----------|-------|
| **AI (LLM for card design)** | ~$5-10 per set | Claude Sonnet ~$5, GPT-4o ~$3.50. Even with heavy retries, well under $30 |
| **Art generation** | $20-40/mo subscription | ChatGPT Plus or Midjourney. May need 2 months if spreading over daily limits. Local generation (SDXL/Flux) is free but lower quality |
| **Art budget total** | $50-80 | Subscription + LLM costs + basic land art |
| **Printing** | TBD | Needs landscape research in Phase 0B. Depends on service, card count, card stock. EU services avoid Dutch customs |
| **Fonts/Assets** | $0 | Open-source alternatives only |
| **Infrastructure** | $0 | Local GPU + local dev |

---

## Cross-Cutting: Testing Strategy

Focus on **validation tests** that catch real problems, not regression/E2E overhead.

| Level | What | When |
|-------|------|------|
| Unit | Card validation rules, balance checks, text formatting, schema validation | Every commit |
| Validation | Text overflow detection, rules text grammar, color pie compliance, print spec compliance | Per card generation/render |
| Integration | Full pipeline: generate card -> render -> export | Per phase completion |
| Print QA | Physical test prints | Before full print order |

---

## Cross-Cutting: Learnings Feedback Loop

```
Each phase produces: learnings/<phase>.md
  +-- What worked
  +-- What didn't
  +-- Parameter adjustments
  +-- Anti-patterns to avoid

Before starting any phase:
  +-- Read ALL prior learnings files
      +-- Adjust approach based on accumulated knowledge
```

The plan itself is a living document — updated after each phase with refined estimates and adjusted approaches.

---

## Iteration Model

| Version | Scope | Goal |
|---------|-------|------|
| **V0** | ~50 cards, standard frames only | Validate full pipeline end-to-end (generate -> art -> render -> export) |
| **V1** | Full set (~280 cards), standard frames only | Complete set with heavy human review and tweaking |
| **V2** | Refined V1 + **variant frames** (full-art, borderless, showcase, extended art) | Reduced human intervention, better prompts, fewer rejections, variant support |
| **Vprint** | Final polish | Print-ready files, test batch ordered, then full order |

---

## Suggested Execution Order

```
Phase 0A ─────────┐
Phase 0B ─────────┼──→ Phase 0C (setup) ──→ Phase 0D (LLM strategy) ──→ Phase 0E (prompt spike)
                  │                                                          │
                  │    ┌─────────────────────────────────────────────────────┘
                  │    │
                  │    ▼
                  │    Phase 1A (skeleton + CLI architecture)          ✓ COMPLETE
                  │        │
                  │        ▼
                  │    Phase 1B (mechanics)                            ✓ COMPLETE
                  │        │
                  │        ▼
                  │    Phase 1C (card gen + validation + review)       ✓ COMPLETE
                  │        │
                  │        ├──→ Phase 4A (balance + revision on dev set)  ✓ COMPLETE
                  │        │        │
                  │        │        ▼
                  │    Phase 4B (AI design review)  ✓ COMPLETE
                  │        │
                  │        ▼
                  │    Phase 2A (art direction, parallel with 4B)
                  │        │
                  │        ▼
                  │    Phase SC (skeleton improvements + scale to ~280)
                  │        │
                  │        ├──→ Phase 4A+4B (balance gate on full set)
                  │        │        │
                  │        │        ▼
                  │    Phase 2B (art generation) ◄── only after balance gate passes
                  │        │
                  │        ▼
                  │    Phase 2C (card renderer)
                  │        │
                  │        ▼
                  │    Phase 3A+3B (review tools)
                  │        │
                  │        ▼
                  │    Phase 4C (quality checks)
                  │        │
                  │        ▼
                  │    Phase 5A (print files) ──→ 5B (print order) ──→ 5C (assembly)
                  │
                  └──→ Print specs locked (hard dep for 2C)
```

**Key dependency**: 0B (print specs) must complete before 2C (renderer) starts.
**Key dependency**: 0E (prompt spike) must complete before 1C (card generation) starts.
**Key dependency**: Phase 4A+4B (balance gate) must pass before Phase 2B (art generation) starts — catch balance issues before investing in 280+ art pieces.
**Key dependency**: Phase SC (skeleton improvements) must complete before scaling to ~280 cards — mechanic distribution, constraint derivation, and legend mapping get worse at scale without these fixes.
**Key parallelization**: Art direction (Phase 2A) can begin in parallel with Phase 4A+4B.
**Validation library**: Built during Phase 1C, used as generation-time gates. Phase 4A+4B runs the balance suite after card generation; Phase 4C runs quality checks after rendering.
