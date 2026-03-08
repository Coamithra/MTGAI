# MTG AI Set Creator — Progress Tracker

## Project

Build a complete Magic: The Gathering custom set creator — from set design through card generation, art creation, card rendering, and physical printing. Python backend (FastAPI), CLI-first with HTML gallery for visual review. Target: ~280-card set, printed via MakePlayingCards or similar.

**Repo root**: `C:\Programming\MTGAI`
**Plans dir**: `C:\Programming\MTGAI\plans\`
**Master plan**: `plans/master-plan.md` — full project overview, key decisions, budget, dependency graph

---

## Execution Protocol

**When the user says "continue with tracker.md":**

1. **Read this file** to find current progress (first unchecked `- [ ]` box).
2. **Identify the next task(s)** — check the phase's `Needs:` line to confirm prerequisites are met. If multiple independent tasks are available, propose running them in parallel.
3. **For each task to execute:**
   a. Read the detailed plan file (referenced in the phase header) for full context on that task.
   b. Read any input files listed in `Inputs:` that the task consumes.
   c. **Spawn a subagent** to do the work. Give it:
      - The task description from this tracker
      - Relevant sections from the detailed plan
      - Paths to input files it needs to read
      - Clear instruction to WRITE CODE / PRODUCE FILES (not just research)
      - The expected output files/artifacts
   d. Subagents may spawn their own sub-subagents for parallel subtasks (e.g., 0A could spawn 3 research agents in parallel).
4. **Verify the output** — check that the expected files exist and are well-formed.
5. **Update this tracker** — change `- [ ]` to `- [x]` for completed tasks.
6. **Report to the user** — summarize what was done, what was produced, and what's next.

**Subagent context template:**
> You are working on the MTG AI Set Creator project (repo: `C:\Programming\MTGAI`).
> Master plan: `plans/master-plan.md`. Detailed plan for this phase: `plans/<phase-file>.md`.
> Your task: [task description]. Read [specific plan section] for full details.
> Inputs you need: [list of files to read]. Outputs you must produce: [list of files to write].
> Write real, working code/content. Do not produce stubs or placeholders.

**Key rules:**
- Each task's output becomes the next task's input. Outputs must be complete enough to give context to the next phase with NO prior conversation history.
- Learnings files (`learnings/phase*.md`) capture what worked, what didn't, surprises, and parameter adjustments — these are read before starting any subsequent phase.
- Always read ALL existing `learnings/*.md` files before starting a new phase.
- If a task requires human input (marked with "HUMAN:"), stop and ask the user.

---

## Phase 0A: Set Design Research
> **Plan**: `plans/phase-0a-set-design-research.md`
> **Needs**: Nothing — can start immediately
> **Inputs**: Scryfall API (public, no auth)
> **Outputs**: `research/scripts/scryfall_pull.py`, `research/scripts/analyze_sets.py`, `research/raw-data/{dsk,blb,otj,mkm,lci}/cards.json`, `research/set-design.md`, `research/set-template.json`, `learnings/phase0a.md`
> **What this does**: Pull card data from 5 recent MTG sets via Scryfall API, analyze distributions (rarity, color, type, mana curve, keywords, removal density, as-fan), and produce a statistical reference document + machine-readable template that Phase 1 consumes to build the set skeleton.

- [x] **0A-1**: Write Scryfall data pull script. Fetch booster-eligible cards for 5 sets (dsk, blb, otj, mkm, lci) via `api.scryfall.com/cards/search?q=set:xxx+is:booster`. Rate limit 100ms. Handle pagination. Store raw JSON per set.
  → `research/scripts/scryfall_pull.py`, `research/raw-data/{code}/cards.json`
- [x] **0A-2**: Write analysis script. Read raw JSON, compute all metrics from plan Section 4 (card counts, color distribution, type spread, mana curve, creature stats, keyword frequency, removal density, draft archetype signals, booster composition). Output tables + structured JSON.
  → `research/scripts/analyze_sets.py`
- [x] **0A-3**: Write set design research document. Synthesize data with MTG design philosophy (New World Order, as-fan, color pie, draft archetypes). Structure per plan Section 5.1.
  → `research/set-design.md`
- [x] **0A-4**: Create set template JSON. Machine-readable distribution targets derived from analysis averages. Schema per plan Section 5.2. Include min/max ranges and scaling formulas for different set sizes.
  → `research/set-template.json`
- [x] **0A-5**: Write learnings → `learnings/phase0a.md`
- [x] **0A-6**: Verify — cross-check card counts against 2+ independent sources, validate template produces sensible 280-card allocation, confirm all downstream phases have data they need (plan Section 6).

---

## Phase 0B: Technical Research
> **Plan**: `plans/phase-0b-technical-research.md`
> **Needs**: Nothing — can run parallel with 0A
> **Inputs**: Local GPU (8GB+ VRAM), internet for service research
> **Outputs**: `research/tech-decisions.md`, `research/proof-of-concept/` (1-card PoC), `config/print-specs.json`, `assets/fonts/`, `assets/symbols/`, `learnings/phase0b.md`
> **What this does**: Research and select image generation model, card rendering stack (Pillow + Cairo/Pango), fonts, symbol assets, and print service. Lock down print specs. Validate with a 1-card proof of concept.

- [ ] **0B-img**: Image generation research. Install ComfyUI + SDXL/Flux locally. Run 10 standardized test prompts (plan Section 2.3). Score each model on fantasy art quality, style consistency, prompt adherence. Test upscaling (Real-ESRGAN). Test character reference workflows.
- [ ] **0B-render**: Card rendering research. Test Proxyshop, cardconjurer, Pillow, Pycairo. Build minimal prototypes. Compare text quality, automation capability. Decision: Pillow + Cairo/Pango per master plan.
- [ ] **0B-font**: Font research. Download top candidates for card name (Beleren alternatives), body text (MPlantin alternatives), P/T info (Gotham alternatives). Print comparison at card size. Verify OFL licenses. → `assets/fonts/`
- [ ] **0B-symbol**: Symbol assets. Clone `andrewgioia/mana` + `andrewgioia/keyrune`. Extract SVGs. Test inline rendering with Cairo. Create placeholder set symbol. → `assets/symbols/`
- [ ] **0B-print**: Print service research. Get specs from MPC, PrinterStudio, Game Crafter, EU services. Compare DPI/bleed/dimensions/card stock/cost/shipping to NL. Get quotes for 270-card and 1100-card orders.
- [ ] **0B-poc**: 1-card proof of concept — "Thornwood Guardian" (plan Section 7). Generate art → render onto frame with fonts/symbols → export print-ready file. Validate dimensions, DPI, readability. → `research/proof-of-concept/`
- [ ] **0B-specs**: Lock down print specs (plan Section 9 checklist). Every value finalized. → `config/print-specs.json`
- [ ] **0B-doc**: Write tech decisions document with comparison tables and final picks. → `research/tech-decisions.md`
- [ ] **0B-learn**: Write learnings → `learnings/phase0b.md`

---

## Phase 0C: Project Setup
> **Plan**: `plans/phase-0c-project-setup.md`
> **Needs**: Nothing — can run parallel with 0A/0B
> **Inputs**: None
> **Outputs**: Buildable Python project skeleton with Pydantic models, tests, CI, config system
> **What this does**: Initialize the monorepo structure, define all data models (Card, Set, Mechanic), set up tooling (uv, Ruff, pytest), CI, and config system. The card schema defined here is the single source of truth for all downstream phases.

- [x] **0C-1**: Create full directory structure per plan Section 1 (`backend/mtgai/`, `research/`, `learnings/`, `output/`, etc.)
- [x] **0C-2**: Write `backend/pyproject.toml` — project config, dependencies (pydantic, pydantic-settings), dev deps (pytest, ruff), ruff config (line-length 100, Python 3.12), pytest config
- [x] **0C-3**: Write Pydantic models per plan Section 2 — `enums.py` (Color, Rarity, CardType, CardStatus, CardLayout), `card.py` (Card, CardFace, ManaCost, GenerationAttempt with token tracking fields), `mechanic.py`, `set.py` (Set, SetSkeleton, DraftArchetype)
- [x] **0C-4**: Write `config.py` — `MTGAIConfig` using pydantic-settings with paths, LLM settings, print specs, text overflow constants (max chars per field), API keys from env
- [x] **0C-5**: Write I/O helpers — `card_io.py` (load/save card/set JSON), `paths.py` (card_slug, path conventions, naming helpers)
- [x] **0C-6**: Write test fixtures in `conftest.py` — sample cards (creature, instant, planeswalker, DFC), sample set
- [x] **0C-7**: Write tests — model creation/round-trip, status transitions, I/O round-trip, Scryfall field name compatibility
- [x] **0C-8**: Write `.gitignore` (ignore output art/renders, keep card JSON) and project `CLAUDE.md` (conventions per plan Section 7)
- [x] **0C-9**: Write `.github/workflows/ci.yml` — lint (ruff check + format) + test (pytest) on push/PR
- [x] **0C-10**: Run verification — `uv pip install`, `ruff check`, `pytest`, import test, `.gitignore` test (plan Section 9.4)
- [x] **0C-11**: Write learnings → `learnings/phase0c.md`

---

## Phase 0D: LLM & AI Strategy
> **Plan**: `plans/phase-0d-llm-strategy.md`
> **Needs**: 0C card schema (for JSON schema generation). Can use draft schema if 0C not done.
> **Inputs**: `backend/mtgai/models/card.py` (Pydantic model → JSON schema for tool use)
> **Outputs**: `research/llm-strategy.md`, `research/prompt-templates/system-prompt-v1.md`, `research/few-shot-examples/`, `learnings/phase0d.md`
> **What this does**: Select LLM model(s) for card generation, define prompting architecture (system prompt, few-shot strategy, batch size, structured output via tool use), design the validation-retry pipeline, estimate costs. Target: ~$5-10/set.

- [ ] **0D-1**: API setup — configure Anthropic + OpenAI API keys in `.env`, write test script calling both APIs
- [ ] **0D-2**: Draft system prompt v1 — MTG rules reference, color pie summary, output format spec, NWO guidelines, rules text formatting conventions → `research/prompt-templates/system-prompt-v1.md`
- [ ] **0D-3**: Curate few-shot examples — pull 20-30 real cards from Scryfall across colors/rarities/types, format as Card model JSON → `research/few-shot-examples/`
- [ ] **0D-4**: Model comparison — generate 5 test cards (common creature, uncommon spell, rare legendary, mythic planeswalker, land) on Claude Sonnet, GPT-4o, GPT-4o-mini. Score on rules text correctness, balance, creativity, JSON validity.
- [ ] **0D-5**: Batch size test — try 1, 3, 5, 10 cards per call. Measure quality vs cost. Decision: batch of 5 per master plan.
- [ ] **0D-6**: Design validation chain — JSON schema (Pydantic), rules text grammar, mana/CMC consistency, color pie, power level, text overflow, uniqueness. Define hard-fail vs soft-fail.
- [ ] **0D-7**: Art prompt test — compare card-design model vs cheaper model (GPT-4o-mini / Haiku) for art prompt generation quality
- [ ] **0D-8**: Cost calculation — use actual token counts from tests to estimate full 280-card set cost
- [ ] **0D-9**: Write strategy document (structure per plan Section 8.1) → `research/llm-strategy.md`
- [ ] **0D-10**: Write learnings → `learnings/phase0d.md`

---

## Phase 0E: Prompt Engineering Spike
> **Plan**: `plans/phase-0e-prompt-spike.md`
> **Needs**: 0D complete (model selection, prompting architecture)
> **Inputs**: `research/llm-strategy.md`, `research/prompt-templates/system-prompt-v1.md`, `research/few-shot-examples/`
> **Outputs**: `research/prompt-templates/BEST-SETTINGS.md` (card generation cookbook), experiment results in `research/prompt-templates/experiments/`, `learnings/phase0e.md`
> **What this does**: Generate ~24 test cards across all rarities/colors/types, run 6 experiments (temperature, few-shot count, batch size, output format, context strategy, retry loop), iterate on prompts, make GO/NO-GO decision. Budget: <$10. This is a GO/NO-GO gate for the entire project.

- [ ] **0E-exp1**: Temperature sweep — generate 24-card test matrix (plan Section 1) at temps 0.3, 0.5, 0.7, 1.0. Score all 96 cards on 7-dimension rubric (plan Section 3).
- [ ] **0E-exp2**: Few-shot count — 0, 1, 3, 5 examples per card. Use best temperature from exp1.
- [ ] **0E-exp3**: Batch generation — batch sizes 1, 5, 10, 24. Track quality + cost per card.
- [ ] **0E-exp4**: Output format — JSON mode vs prompt-only JSON vs free text + parse. Track parse success rate.
- [ ] **0E-exp5**: Context strategies — no context, names-only, compressed summary, full color data. Count duplicates/conflicts.
- [ ] **0E-exp6**: Validation-retry loop — take 5-10 failed cards, feed errors back, measure convergence (1-3 retries).
- [ ] **0E-confirm**: Confirmation batch — 20 additional cards with winning settings (include mechanic integration, context injection, archetype targeting).
- [ ] **0E-best**: Write best settings cookbook — model, temperature, few-shot count, batch size, output format, context strategy, expected quality, retry rate, cost per card/set, known limitations, failure mode mitigations → `research/prompt-templates/BEST-SETTINGS.md`
- [ ] **0E-gate**: **HUMAN: GO / NO-GO / CONDITIONAL GO decision** per Section 8 criteria. Rules text avg >= 4.0, overall >= 3.5, retry rate <= 30%, parse rate >= 95%, cost < $30/set.
- [ ] **0E-learn**: Write learnings → `learnings/phase0e.md`

---

## Phase 1A: Set Skeleton Generator
> **Plan**: `plans/phase-1-set-design-engine.md` Section 1A
> **Needs**: 0A (set-template.json, set-design.md), 0C (project skeleton, card schema), 0E (prompt templates)
> **Inputs**: `research/set-template.json`, `research/set-design.md`, `backend/mtgai/models/`
> **Outputs**: `output/sets/<code>/skeleton.json`, `output/sets/<code>/skeleton-overview.txt`, working CLI (list/show/stats), `learnings/phase1a.md`
> **What this does**: Given a theme, generate the structural backbone — slot allocation matrix (color x rarity x type x CMC), 10 draft archetypes, mechanic slot assignments. Build the minimal CLI for card review. HUMAN provides the set theme.

- [ ] **1A-1**: HUMAN: Define set theme (name, code, theme description, flavor, constraints). Implement skeleton generator that reads `set-template.json` and produces slot allocation matrix.
- [ ] **1A-2**: Define 10 draft archetypes (one per color pair) with strategy descriptions
- [ ] **1A-3**: Assign mechanic slots (which colors/rarities get which mechanics)
- [ ] **1A-4**: Build CLI `review list` command (Typer + Rich) — filter by color/rarity/type/status/CMC/keyword
- [ ] **1A-5**: Build CLI `review show <card>` — pretty-printed card detail with history
- [ ] **1A-6**: Build CLI `review stats` — set statistics dashboard (rarity counts, color distribution, mana curve bars)
- [ ] **1A-7**: Define full CLI command group structure (Typer), stub Phase 3A commands (approve/reject/flag/compare/export/art/gallery)
- [ ] **1A-8**: Write unit tests for all skeleton constraints (color balance, rarity totals, type spread, mana curve)
- [ ] **1A-9**: Generate skeleton for the set → `output/sets/<code>/skeleton.json` + `skeleton-overview.txt`
- [ ] **1A-10**: HUMAN: Review skeleton via CLI — approve or adjust
- [ ] **1A-11**: Write learnings → `learnings/phase1a.md`

---

## Phase 1B: Mechanic Designer
> **Plan**: `plans/phase-1-set-design-engine.md` Section 1B
> **Needs**: 1A (skeleton, archetypes)
> **Inputs**: `output/sets/<code>/skeleton.json`, `research/set-design.md` (mechanic patterns), `research/llm-strategy.md`
> **Outputs**: Mechanics defined in set metadata, rules text templates, `learnings/phase1b.md`
> **What this does**: AI-assisted creation of 2-4 set-specific keyword/ability mechanics fitting the theme. Validate against color pie. Define distribution. HUMAN approves each mechanic.

- [ ] **1B-1**: Generate 2-4 set-specific mechanics via LLM (keyword abilities / ability words fitting the set theme)
- [ ] **1B-2**: Validate mechanics against color pie rules from `research/set-design.md`
- [ ] **1B-3**: Assign evergreen keywords per color (which color gets flying, deathtouch, etc.)
- [ ] **1B-4**: Define mechanic distribution across rarities (how many cards per rarity use each mechanic)
- [ ] **1B-5**: Create rules text templates for each new mechanic (including reminder text)
- [ ] **1B-6**: HUMAN: Review and approve each mechanic
- [ ] **1B-7**: Generate 5 sample cards using new mechanics — design review checkpoint
- [ ] **1B-8**: Write learnings → `learnings/phase1b.md`

---

## Phase 1C: Card Generator
> **Plan**: `plans/phase-1-set-design-engine.md` Section 1C
> **Needs**: 1B (mechanics), 0E (proven prompts, BEST-SETTINGS.md)
> **Inputs**: `output/sets/<code>/skeleton.json`, `research/prompt-templates/BEST-SETTINGS.md`, `research/prompt-templates/system-prompt-v*.md`, `research/few-shot-examples/`
> **Outputs**: ~280 card JSON files in `output/sets/<code>/cards/`, `mtgai.validation` library, `learnings/phase1c.md`
> **What this does**: Build the validation library (6 validators), then generate all cards filling skeleton slots via LLM with validation-retry loops. Cards go through: generate → validate → retry with feedback → flag for human review if still failing.

- [ ] **1C-val1**: Build `mtgai.validation.rules_text` — regex-based MTG rules text grammar checks (self-reference ~, keyword spelling, trigger/activated/static patterns, mana symbol format)
- [ ] **1C-val2**: Build `mtgai.validation.balance` — P/T vs CMC scoring, ability density per rarity, NWO complexity check for commons
- [ ] **1C-val3**: Build `mtgai.validation.color_pie` — map ability types to allowed colors, flag violations
- [ ] **1C-val4**: Build `mtgai.validation.text_overflow` — character count heuristic using config text overflow constants
- [ ] **1C-val5**: Build `mtgai.validation.uniqueness` — exact name match + fuzzy mechanical similarity detection
- [ ] **1C-val6**: Build `mtgai.validation.spelling` — spell check card name, rules text, flavor text, type line
- [ ] **1C-gen**: Implement card generation pipeline — LLM calls (tool use / function calling for structured output), batch of 5, validation chain, retry with specific feedback, escalate to human after 3 failures
- [ ] **1C-common**: Generate all commons (~101 cards). Batch by color.
- [ ] **1C-uncommon**: Generate all uncommons (~80 cards). Include 10 signpost multicolor uncommons.
- [ ] **1C-rare**: Generate all rares (~60 cards). More complex — may need single-card generation for some.
- [ ] **1C-mythic**: Generate all mythics (~20 cards). Include planeswalkers, legendary creatures.
- [ ] **1C-reprint**: Select reprint cards from Scryfall data (staple commons, mana fixing, basic removal) to fill appropriate skeleton slots
- [ ] **1C-lands**: Generate nonbasic lands + basic land flavor text (20 basics = 4 per color)
- [ ] **1C-review**: HUMAN: Review generated cards via CLI. Approve, reject, or flag.
- [ ] **1C-learn**: Write learnings → `learnings/phase1c.md`

---

## Phase 4A+4B: Balance Gate
> **Plan**: `plans/phase-4-5-validation-print.md` Sections 4A, 4B
> **Needs**: 1C (all cards generated)
> **Inputs**: `output/sets/<code>/cards/*.json`, `research/set-template.json` (target ranges)
> **Outputs**: `output/sets/<code>/reports/balance-report.md`, `output/sets/<code>/reports/limited-report.md`
> **What this does**: Run full-set balance analysis and limited environment simulation BEFORE art generation. This is a gate — if balance fails, fix cards before investing in 280+ art pieces. Uses validators from 1C + new sealed/draft simulation code.

- [ ] **4A-1**: Mana curve distribution analysis per color — compare to targets in `set-template.json`
- [ ] **4A-2**: Creature P/T vs CMC analysis — flag outliers
- [ ] **4A-3**: Removal spell density check — ensure minimum per color at common
- [ ] **4A-4**: Card advantage sources per color — verify balanced
- [ ] **4A-5**: Keyword/mechanic frequency + as-fan calculations
- [ ] **4A-6**: Generate balance report → `output/sets/<code>/reports/balance-report.md`
- [ ] **4B-1**: Build sealed pool generator — `mtgai/packs.py` `generate_booster_pack()` (10C + 3U + 1R/M + 1 land), `generate_sealed_pool()` (6 packs)
- [ ] **4B-2**: Run 100+ sealed pool simulations — analyze color viability (can you build a 2-color deck?)
- [ ] **4B-3**: Booster pack composition checks — verify rarity distribution is correct
- [ ] **4B-4**: Draft archetype support check — are all 10 color pairs viable? Enough signpost cards?
- [ ] **4B-5**: Generate limited report → `output/sets/<code>/reports/limited-report.md`
- [ ] **4AB-gate**: HUMAN: Review reports. Fix any flagged balance issues (regenerate/modify cards) before proceeding to art generation. This is a hard gate.

---

## Phase 2A: Art Direction System
> **Plan**: `plans/phase-2-art-rendering-pipeline.md` Section 2A
> **Needs**: Set theme (from 1A). Can run parallel with Phase 1.
> **Inputs**: Set theme/description, `research/tech-decisions.md` (image generation model choice)
> **Outputs**: `output/sets/<code>/art-direction/style-guide.md`, prompt templates per card type, character reference images, set symbol SVG, `learnings/phase2a.md`
> **What this does**: Define the visual identity — color palette, mood, composition guidelines, character references. Generate 20 sample arts as go/no-go gate. This phase involves significant HUMAN judgment on art style preferences.

- [ ] **2A-1**: HUMAN: Create style guide collaboratively — color palette, mood, setting, architecture, flora/fauna, per-color visual identity → `output/sets/<code>/art-direction/style-guide.md`
- [ ] **2A-2**: Define art prompt templates per card type (creature, spell, land, artifact, planeswalker) — plan Section 2A.2
- [ ] **2A-3**: Set up character consistency workflow — generate reference images for key characters (legendaries, planeswalkers), document how to maintain consistency
- [ ] **2A-4**: Define artist style variation personas — different "artist" prompt prefixes to simulate varied art styles
- [ ] **2A-5**: Generate 10+ sample arts across card types, evaluate consistency and quality
- [ ] **2A-6**: HUMAN: Go/no-go gate — 20 sample arts evaluated. Sufficient quality? Cohesive identity? If NO, reassess image generation approach.
- [ ] **2A-7**: Finalize set symbol SVG (replaces Phase 0B placeholder) → `assets/symbols/set-symbol.svg`
- [ ] **2A-8**: Write learnings → `learnings/phase2a.md`

---

## Phase 2B: Art Generation Pipeline
> **Plan**: `plans/phase-2-art-rendering-pipeline.md` Section 2B
> **Needs**: 1C (card data), 2A (style guide + prompts), 4A+4B balance gate PASSED
> **Inputs**: `output/sets/<code>/cards/*.json`, `output/sets/<code>/art-direction/style-guide.md`, art prompt templates
> **Outputs**: Art images in `output/sets/<code>/art/`, `learnings/phase2b.md`
> **What this does**: Generate art for all ~280+ cards. Batch process with rate limiting. Automated QA + human review. May span multiple days due to daily generation limits.

- [ ] **2B-1**: Build batch art generation pipeline — rate limiting, error handling, resume from interruption
- [ ] **2B-2**: Generate art prompts for all cards using cheaper model (GPT-4o-mini / Haiku) — card data + style guide → image prompt
- [ ] **2B-3**: Generate art — commons (~101 images)
- [ ] **2B-4**: Generate art — uncommons (~80 images)
- [ ] **2B-5**: Generate art — rares + mythics (~80 images)
- [ ] **2B-6**: Generate art — lands + basic lands (~35 images including 20 basics)
- [ ] **2B-7**: Run automated QA — check resolution >= 1488x956px, correct aspect ratio ~1.56:1, file size reasonable, no obvious artifacts
- [ ] **2B-8**: Post-process — crop to art box ratio, color correct, upscale if needed (Real-ESRGAN)
- [ ] **2B-9**: HUMAN: Review art via HTML gallery (Phase 3B if available, else manual) — approve/reject per card
- [ ] **2B-10**: Regenerate rejected art with revised prompts
- [ ] **2B-11**: Write learnings → `learnings/phase2b.md`

---

## Phase 2C: Card Renderer
> **Plan**: `plans/phase-2-art-rendering-pipeline.md` Section 2C
> **Needs**: 0B (print specs, fonts, symbols), 2B (art images)
> **Inputs**: `config/print-specs.json`, `assets/fonts/`, `assets/symbols/`, `output/sets/<code>/art/`, `output/sets/<code>/cards/*.json`
> **Outputs**: Rendered card images in `output/sets/<code>/renders/`, card back image, `learnings/phase2c.md`
> **What this does**: Combine card data + art + frames into print-ready card images using Pillow + Cairo/Pango. Handle text layout with inline symbols, dynamic font sizing, and flavor text italics.

- [ ] **2C-1**: Build frame templates for standard colors (W/U/B/R/G/multicolor-gold/artifact-grey/land) — PNG assets at print resolution
- [ ] **2C-2**: Build planeswalker frame template (different layout: 3-4 loyalty abilities, no P/T box)
- [ ] **2C-3**: Build text layout engine — mixed formatting (bold keywords, italic reminder text, inline mana symbol SVGs), automatic line breaking, dynamic font sizing for text-heavy cards. Use Cairo/Pango.
- [ ] **2C-4**: Implement proxy render mode — text-only card rendering without art (colored placeholder). For testing pipeline before art exists.
- [ ] **2C-5**: Implement dual resolution output — 72 DPI for screen review + 300+ DPI for print (per `config/print-specs.json`)
- [ ] **2C-6**: Design custom card back — MTG card back style with custom set branding + "AI-Generated / Custom Set" indicator
- [ ] **2C-7**: Render all ~280 cards → `output/sets/<code>/renders/`
- [ ] **2C-8**: Run text overflow detection on every rendered card — verify text fits within frame
- [ ] **2C-9**: Validate print spec compliance — DPI, dimensions (63x88mm + 3mm bleed), color space, file format per `config/print-specs.json`
- [ ] **2C-10**: HUMAN: Home-print test batch (~10 cards on standard paper at actual size). Compare to real MTG card for sizing/readability.
- [ ] **2C-11**: Write learnings → `learnings/phase2c.md`

---

## Phase 3A: CLI Review Tools
> **Plan**: `plans/phase-3-review-tools.md` Section 3A
> **Needs**: 0C (card schema), 1A (CLI skeleton with Typer stubs)
> **Inputs**: `backend/mtgai/models/card.py`, `output/sets/<code>/cards/*.json`
> **Outputs**: Full CLI review toolkit under `mtgai review` command group
> **What this does**: Extend the minimal CLI from Phase 1A into a full review toolkit with batch approve/reject/flag, side-by-side comparison, export (CSV/JSON/Cockatrice), and art review commands.

- [ ] **3A-1**: Card loader + filter module — load card JSON from `output/` dir, filter by color/rarity/type/status/CMC/keyword/mechanic. Shared by CLI and gallery.
- [ ] **3A-2**: Status transition engine — enforce forward-only transitions (draft→validated→approved→art_generated→rendered→print_ready), rejection resets to draft, audit trail with timestamps
- [ ] **3A-3**: Rich formatters — table rendering, card panels, color-coded status/MTG colors, mana cost display
- [ ] **3A-4**: `review list` — full filter/sort, table + compact + JSON output modes
- [ ] **3A-5**: `review show <card>` — pretty-printed card detail with all fields + status history
- [ ] **3A-6**: `review stats` — dashboard with bar charts (status pipeline, rarity/color/type distribution, mana curve, flagged cards)
- [ ] **3A-7**: `review approve/reject/flag` — batch operations (comma IDs, filter-based, all+status gate), confirmation prompts, dry-run, required reason for reject
- [ ] **3A-8**: `review compare <card1> <card2>` — side-by-side Rich panels with diff section
- [ ] **3A-9**: `review export <format>` — CSV (flat spreadsheet), JSON (full card data), print (copy render files), Cockatrice (XML for playtesting)
- [ ] **3A-10**: `review art <card>` — show art file info, all attempts, `--open` to launch in system viewer

---

## Phase 3B: HTML Gallery Viewer
> **Plan**: `plans/phase-3-review-tools.md` Section 3B
> **Needs**: 3A-1 (card loader), rendered images (or placeholder colored rectangles)
> **Inputs**: `output/sets/<code>/cards/*.json`, `output/sets/<code>/renders/`
> **Outputs**: Static HTML gallery in `output/sets/<code>/gallery/`, `mtgai/packs.py` (shared booster generation)
> **What this does**: Generate a static HTML site (Jinja2 + vanilla JS) for visual card review. Card grid with filters, detail pages, side-by-side comparison, booster pack viewer, art consistency review. Dark theme. No server needed.

- [ ] **3B-1**: Gallery generator scaffolding — Jinja2 template setup, output structure, `cards.json` data export for client-side filtering
- [ ] **3B-2**: Base HTML template + CSS — dark theme, responsive grid (CSS Grid), card image sizing
- [ ] **3B-3**: Card grid page — `index.html` with toggle filters (color/rarity/type/status/CMC), sort options, card count, URL hash state
- [ ] **3B-4**: Card detail pages — `cards/NNN.html` with large image, all card fields, status timeline, CLI command copy buttons, prev/next nav
- [ ] **3B-5**: Booster pack viewer — `booster.html` randomized 15-card pack display. Build `mtgai/packs.py` `generate_booster_pack()` (shared with Phase 4B)
- [ ] **3B-6**: Comparison mode — `compare.html` select 2-4 cards side-by-side with diff
- [ ] **3B-7**: Art review page — `art-review.html` art-only grid grouped by color/type for consistency review
- [ ] **3B-8**: `review gallery` CLI command — generates gallery, `--open` launches browser, `--watch` optional auto-regenerate
- [ ] **3B-9**: File watcher (optional) — `watchdog` monitors card/render dirs, debounced gallery rebuild

---

## Phase 4C: Quality Checks
> **Plan**: `plans/phase-4-5-validation-print.md` Section 4C
> **Needs**: 2C (rendered cards)
> **Inputs**: `output/sets/<code>/cards/*.json`, `output/sets/<code>/renders/`
> **Outputs**: `output/sets/<code>/reports/quality-report.md`, `learnings/phase4.md`
> **What this does**: Second pass of Phase 4 — run quality checks that need rendered images (text overflow against actual renders, visual QA). Also re-run all validators from 1C as final confirmation.

- [ ] **4C-1**: Full-set rules text grammar validation (re-run `mtgai.validation.rules_text` on all cards)
- [ ] **4C-2**: Spell check across all card text fields
- [ ] **4C-3**: Duplicate/near-duplicate detection across full set
- [ ] **4C-4**: Flavor text quality check (not empty where expected, not present where card is too complex)
- [ ] **4C-5**: Cross-card interaction sanity checks (no infinite combos at common, no broken 2-card synergies)
- [ ] **4C-6**: Text overflow validation against actual rendered card images (not just character count heuristic)
- [ ] **4C-7**: Generate quality report → `output/sets/<code>/reports/quality-report.md`
- [ ] **4C-8**: Write learnings → `learnings/phase4.md`

---

## Phase 5A: Print File Generation
> **Plan**: `plans/phase-4-5-validation-print.md` Section 5A
> **Needs**: 4C passed, all cards rendered and validated
> **Inputs**: `output/sets/<code>/renders/`, `config/print-specs.json`, `output/sets/<code>/cards/*.json`
> **Outputs**: Print-ready files in `output/sets/<code>/print/`, `manifest.json`
> **What this does**: Export final print files per printer specs. Generate randomized booster packs for draft set. Generate full playset. Calculate total print cost.

- [ ] **5A-1**: Export all cards as print-ready images — correct DPI, dimensions with bleed, color space per `config/print-specs.json`
- [ ] **5A-2**: Generate card sheets if required by chosen print service
- [ ] **5A-3**: Export card back file (same spec as fronts)
- [ ] **5A-4**: Generate draft set — 24 randomized booster packs (8-player pod, 10C + 3U + 1R/M + 1 land each)
- [ ] **5A-5**: Generate full playset — 4x each common/uncommon/rare, 2x each mythic, basic lands
- [ ] **5A-6**: Generate order manifest → `output/sets/<code>/print/manifest.json` (card list, quantities, file mapping)
- [ ] **5A-7**: Run cost calculator — total print cost for draft set and full playset from chosen service. HUMAN: approve cost before ordering.

---

## Phase 5B: Print Order
> **Plan**: `plans/phase-4-5-validation-print.md` Section 5B
> **Needs**: 5A
> **Inputs**: `output/sets/<code>/print/`, print service account
> **Outputs**: Physical cards ordered
> **What this does**: Place the print order. Test batch first, then full order. All steps involve HUMAN action.

- [ ] **5B-1**: Generate step-by-step upload guide for chosen print service (MPC or selected alternative)
- [ ] **5B-2**: Create file upload checklist (all files present, correct naming, correct dimensions)
- [ ] **5B-3**: HUMAN: Order test batch (~20 cards) — verify quality before full commitment
- [ ] **5B-4**: HUMAN: Review test batch — card stock feel, color accuracy, text readability, sizing
- [ ] **5B-5**: HUMAN: Place full print order

---

## Phase 5C: Assembly
> **Plan**: `plans/phase-4-5-validation-print.md` Section 5C
> **Needs**: 5B (prints received)
> **Inputs**: Physical printed cards
> **Outputs**: Sorted cards, set guide, box labels, `learnings/phase5.md`
> **What this does**: Sort received cards, create reference materials for the physical set.

- [ ] **5C-1**: Generate sorting guide — card list sorted by collector number with pack assignments
- [ ] **5C-2**: Generate set guide insert — set name, theme summary, mechanics with reminder text, draft archetype guide (10 color pairs)
- [ ] **5C-3**: Generate box labels — set name, set symbol, card count, "AI-Generated Custom Set"
- [ ] **5C-4**: Write learnings → `learnings/phase5.md`

---

## Execution Order

```
0A + 0B + 0C (all parallel, no blockers)
         │
         ▼
    0D (needs 0C schema)
         │
         ▼
    0E (needs 0D) ←── GO/NO-GO GATE
         │
    ┌────┴────────────┐
    ▼                 ▼
1A (skeleton)    2A (art direction) ←── can run parallel
    │
    ▼
1B (mechanics)
    │
    ▼
1C (card generation)
    │
    ▼
4A+4B (balance gate) ←── HARD GATE before art
    │
    ▼
2B (art generation)  ←── may span multiple days
    │
    ▼
2C (card renderer)
    │
  ┌─┴──┐
  ▼    ▼
3A+3B  4C (quality)  ←── can run parallel
  │    │
  └──┬─┘
     ▼
5A (print files)
     │
     ▼
5B (print order)  ←── HUMAN: test batch then full order
     │
     ▼
5C (assembly)
```

---

## Session Notes

| Date | Session | Notes |
|------|---------|-------|
| 2026-03-08 | 1 | Completed Phase 0A (all 6 tasks) and Phase 0C (all 11 tasks). Phase 0B deferred — requires manual GPU/tool testing. Next: 0D (LLM strategy, needs 0C schema). |
