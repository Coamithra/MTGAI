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

- [x] **0B-img**: Image generation research. Research-based assessment: Flux.1-dev (local, NF4/GGUF quantized) selected as primary, Flux via API as fallback, Midjourney for hero cards. Hands-on validation deferred to Phase 2A. Comparison table with weighted scores, VRAM analysis, and style consistency workflow documented.
  → `research/tech-decisions.md` (Image Generation section), `research/proof-of-concept/image-gen-test-prompts.md`
- [x] **0B-render**: Card rendering research. Test Proxyshop, cardconjurer, Pillow, Pycairo. Build minimal prototypes. Compare text quality, automation capability. Decision: Pillow (no Cairo needed — sufficient at 300 DPI).
  → `research/proof-of-concept/render_prototype.py`, `research/proof-of-concept/rendered-thornwood-prototype.png`, `research/proof-of-concept/rendering-notes.md`
- [x] **0B-font**: Font research. Downloaded Cinzel (card name), EB Garamond (body), Montserrat (P/T). All OFL licensed, variable TTF format.
  → `assets/fonts/{cinzel,eb-garamond,montserrat}/`
- [x] **0B-symbol**: Symbol assets. Cloned `andrewgioia/mana` (40 SVGs) + `andrewgioia/keyrune` (license). Created placeholder set symbol with rarity variants.
  → `assets/symbols/mana/`, `assets/symbols/set-symbol-*.svg`
- [x] **0B-print**: Print service research. MPC selected as primary (S33 stock, ~$95 draft set, ~$255 playset, no customs to NL via standard shipping).
  → `config/print-specs.json`, `research/print-service-comparison.md`
- [x] **0B-poc**: 1-card proof of concept — "Thornwood Guardian" (plan Section 7). Upgraded: project fonts (Cinzel/EB Garamond/Montserrat), inline mana symbols ({2}{G}{G}), set symbol with rarity colors. 7ms render time. Art placeholder (real art deferred to Phase 2A).
  → `research/proof-of-concept/render_prototype.py`, `research/proof-of-concept/rendered-thornwood-prototype.png`
- [x] **0B-specs**: Lock down print specs (plan Section 9 checklist). All values finalized: 822x1122px, 300 DPI, sRGB, PNG, S33 stock.
  → `config/print-specs.json`
- [x] **0B-doc**: Tech decisions document written with comparison tables and final picks (image gen section pending 0B-img).
  → `research/tech-decisions.md`
- [x] **0B-learn**: Write learnings → `learnings/phase0b.md`

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

- [x] **0D-1**: API setup — both Anthropic + OpenAI API keys verified working. Test script: `research/scripts/test_api_keys.py`
- [x] **0D-2**: Draft system prompt v1 (~1,800 tokens). → `research/prompt-templates/system-prompt-v1.md`
- [x] **0D-3**: Curate few-shot examples — 25 real cards with design_notes. → `research/few-shot-examples/` (25 JSONs + index.json)
- [x] **0D-4**: Model comparison — Claude Sonnet 89/100, GPT-4o 83/100, GPT-4o-mini 84/100. Sonnet selected as primary.
  → `research/model-comparison-scores.md`, `research/model-comparison-results.json`
- [x] **0D-5**: Batch size test — batch of 5 optimal (64% cost savings, 100% parse rate). → `research/batch-size-analysis.md`
- [x] **0D-6**: Design validation chain — 7 validators with hard/soft classification. → `research/validation-chain-design.md`
- [x] **0D-7**: Art prompt test — Haiku at 92% of Sonnet quality, 4x cheaper. Haiku selected for art prompts.
  → `research/art-prompt-comparison.md`
- [x] **0D-8**: Cost calculation — ~$2.57/set (Sonnet cards + Haiku art prompts). Budget allows 10+ iterations.
- [x] **0D-9**: Strategy document written. → `research/llm-strategy.md`
- [x] **0D-10**: Learnings written. → `learnings/phase0d.md`

---

## Phase 0E: Prompt Engineering Spike
> **Plan**: `plans/phase-0e-prompt-spike.md`
> **Needs**: 0D complete (model selection, prompting architecture)
> **Inputs**: `research/llm-strategy.md`, `research/prompt-templates/system-prompt-v1.md`, `research/few-shot-examples/`
> **Outputs**: `research/prompt-templates/BEST-SETTINGS.md` (card generation cookbook), experiment results in `research/prompt-templates/experiments/`, `learnings/phase0e.md`
> **What this does**: Generate ~24 test cards across all rarities/colors/types, run 6 experiments (temperature, few-shot count, batch size, output format, context strategy, retry loop), iterate on prompts, make GO/NO-GO decision. Budget: <$10. This is a GO/NO-GO gate for the entire project.

- [x] **0E-exp1**: Temperature sweep — T=1.0 wins (4.71 avg). All temps within 0.03 of each other. Cost: $0.48.
  → `research/prompt-templates/experiments/exp1_temperature/`
- [x] **0E-exp2**: Few-shot count — 0 (zero-shot) wins (4.71 avg). Examples hurt quality. Cost: $0.39.
  → `research/prompt-templates/experiments/exp2_fewshot/`
- [x] **0E-exp3**: SKIPPED — Already tested in Phase 0D. Batch-5 confirmed optimal (64% savings, 100% parse).
- [x] **0E-exp4**: SKIPPED — Already tested in Phase 0D. Tool_use confirmed (0% parse failures).
- [x] **0E-exp5**: Context strategies — compressed wins (1 similar effect vs 6 for names-only). Cost: $0.23.
  → `research/prompt-templates/experiments/exp5_context/`
- [x] **0E-exp6**: Validation-retry — 5/7 clean on first try, 2 more fixed in 1 retry. Converges fast. Cost: $0.17.
  → `research/prompt-templates/experiments/exp6_retry/`
- [x] **0E-confirm**: Confirmation batch — 20 cards, 4.73/5.0 avg, 0 below 3.0, 1/20 with failure, 0 duplicates. Cost: $0.10.
  → `research/prompt-templates/experiments/confirmation/`
- [x] **0E-best**: Best settings cookbook written. T=1.0, FS=0, batch-5, tool_use, compressed context. All GO criteria passed.
  → `research/prompt-templates/BEST-SETTINGS.md`
- [x] **0E-gate**: **HUMAN: GO** — All criteria passed with wide margin. Rules text avg 4.95-5.00 (threshold 4.0), overall 4.71-4.73 (threshold 3.5), retry rate ~5% (threshold 30%), parse rate 100% (threshold 95%), cost ~$2.57/set (threshold $30). Planeswalker/saga: use Opus for these complex types (~5-8 cards). Dev set approach adopted: ~60 cards through pipeline, scale to ~280 in Phase SC.
- [x] **0E-learn**: Write learnings → `learnings/phase0e.md`

---

## Phase 1A: Set Skeleton Generator
> **Plan**: `plans/phase-1-set-design-engine.md` Section 1A
> **Needs**: 0A (set-template.json, set-design.md), 0C (project skeleton, card schema), 0E (prompt templates)
> **Inputs**: `research/set-template.json`, `research/set-design.md`, `backend/mtgai/models/`
> **Outputs**: `output/sets/<code>/skeleton.json`, `output/sets/<code>/skeleton-overview.txt`, working CLI (list/show/stats), `learnings/phase1a.md`
> **What this does**: Given a theme, generate the structural backbone — slot allocation matrix (color x rarity x type x CMC), 10 draft archetypes, mechanic slot assignments. Skeleton generator accepts a `set_size` parameter and uses `set-template.json` scaling formulas — default to ~60 cards for development, scale to ~280 for final production. Build the minimal CLI for card review. HUMAN provides the set theme.

- [x] **1A-1**: HUMAN: Define set theme (name, code, theme description, flavor, constraints). Implement skeleton generator that reads `set-template.json` and produces slot allocation matrix. Must accept `set_size` parameter (default ~60 dev set; uses `set_size_scaling` formulas from template).
  → Theme: "Anomalous Descent" (ASD) — science-fantasy megadungeon in far-future post-apocalyptic Earth. 8 legendary characters, 10 draft archetypes. `backend/mtgai/skeleton/generator.py` (897 lines), `output/sets/ASD/theme.json`, `output/sets/ASD/set-config.json`
- [x] **1A-2**: Define 10 draft archetypes (one per color pair) with strategy descriptions
  → All 10 archetypes defined in `output/sets/ASD/theme.json` with color pairs, descriptions, speeds, and factions.
- [x] **1A-3**: Assign mechanic slots (which colors/rarities get which mechanics)
  → MechanicTag enum (vanilla/french_vanilla/evergreen/complex) assigned to all skeleton slots. Distribution follows NWO: commons get vanilla/french_vanilla, rares/mythics get complex.
- [x] **1A-4**: Build CLI `review list` command (Typer + Rich) — filter by color/rarity/type/status/CMC/keyword
  → `backend/mtgai/review/cli.py` — 7 filter options (--color, --rarity, --type, --cmc, --mechanic, --archetype, --set) + --sort. Color-coded Rich table output.
- [x] **1A-5**: Build CLI `review show <card>` — pretty-printed card detail with history
  → `python -m mtgai.review show <slot_id>` — Rich Panel with full slot details. Suggests similar IDs on not-found.
- [x] **1A-6**: Build CLI `review stats` — set statistics dashboard (rarity counts, color distribution, mana curve bars)
  → Full dashboard: rarity/color/type tables, CMC curve bar chart, archetype coverage with names, constraint checks. `--detailed` flag for per-color breakdown.
- [x] **1A-7**: Define full CLI command group structure (Typer), stub Phase 3A commands (approve/reject/flag/compare/export/art/gallery)
  → `backend/mtgai/review/` — cli.py (Typer app, 10 commands), loaders.py (data loading), formatters.py (Rich formatting). 7 Phase 3A stubs implemented.
- [x] **1A-8**: Write unit tests for all skeleton constraints (color balance, rarity totals, type spread, mana curve)
  → `backend/tests/test_skeleton.py` — 75 tests across 14 test classes. Tests models, constraints, generation at 60/100/280 sizes, balance reports, edge cases, save/load round-trip. Fixed color balance bug in `_distribute_colors()`.
- [x] **1A-9**: Generate skeleton for the set → `output/sets/<code>/skeleton.json` + `skeleton-overview.txt`
  → `output/sets/ASD/skeleton.json` (60 slots, all constraints pass), `output/sets/ASD/skeleton-overview.txt`
- [x] **1A-10**: HUMAN: Review skeleton via CLI — approve or adjust
  → Approved. 60-card dev set structure accepted (21C/21U/14R/4M). R/G having no mythics at dev-set size acknowledged as acceptable for pipeline testing.
- [x] **1A-11**: Write learnings → `learnings/phase1a.md`
  → Skeleton generator design, color balance bug fix, CLI architecture, dev-set tradeoffs documented.

---

## Phase 1B: Mechanic Designer
> **Plan**: `plans/phase-1-set-design-engine.md` Section 1B
> **Needs**: 1A (skeleton, archetypes)
> **Inputs**: `output/sets/<code>/skeleton.json`, `research/set-design.md` (mechanic patterns), `research/llm-strategy.md`
> **Outputs**: Mechanics defined in set metadata, rules text templates, `learnings/phase1b.md`
> **What this does**: AI-assisted creation of 2-4 set-specific keyword/ability mechanics fitting the theme. Validate against color pie. Define distribution. HUMAN approves each mechanic.

- [x] **1B-1**: Generate 2-4 set-specific mechanics via LLM (keyword abilities / ability words fitting the set theme)
  → 6 candidates generated via Claude Sonnet. 3 selected: **Scavenge X** (W/U/G, complexity 1), **Malfunction N** (W/U/R, complexity 2), **Overclock** (U/R/B, complexity 3). Infrastructure: `backend/mtgai/generation/llm_client.py`, `mechanic_generator.py`.
- [x] **1B-2**: Validate mechanics against color pie rules from `research/set-design.md`
  → Color pie validation built into mechanic_generator.py. All 3 approved mechanics pass.
- [x] **1B-3**: Assign evergreen keywords per color (which color gets flying, deathtouch, etc.)
  → `output/sets/ASD/mechanics/evergreen-keywords.json`
- [x] **1B-4**: Define mechanic distribution across rarities (how many cards per rarity use each mechanic)
  → `output/sets/ASD/mechanics/distribution.json` — 14 mechanic cards (23.3% of 60-card set). Scavenge=6, Malfunction=5, Overclock=3. Mapped to specific skeleton slots.
- [x] **1B-5**: Create rules text templates for each new mechanic (including reminder text)
  → `output/sets/ASD/mechanics/approved.json` — full templates with common/uncommon/rare patterns, reminder text, design notes.
- [x] **1B-6**: HUMAN: Review and approve each mechanic
  → Approved with refinements: Scavenge X = top-X dig (not tutor), Malfunction N = counter-based delay, Overclock = renamed from Overload to avoid MTG conflict.
- [x] **1B-7**: Mechanic validation spike — generate 5-10 test cards per custom mechanic using Phase 0E best settings, score against 0E criteria (rules text avg >= 4.0, overall >= 3.5), verify LLM can use novel keywords correctly. If quality is below threshold, iterate on mechanic templates/prompt before Phase 1C.
  → 15 test cards generated ($0.09). Scores: Scavenge 4.75, Malfunction 4.76, Overclock 4.80. All GO. Results: `output/sets/ASD/mechanics/validation-spike-results.md`, `test-cards.json`.
- [x] **1B-8**: HUMAN: Review sample cards — design review checkpoint
  → Human + Opus interactive review of all 15 test cards. Found 9 issue categories across 8 FAIL + 2 WARN cards: keyword name collision (Scavenge exists in MTG), missing reminder text (5 cards), inconsistent capitalization, haste negated by malfunction, "enters tapped" irrelevant on noncreature artifact, redundant conditional (overclock as mandatory cost + "if you overclocked"), kitchen sink design (2 cards), false variability, above-rate balance (12 dmg for 5 mana). Two cards fully redesigned (Synaptic Overload, Cascade Protocol). Originals preserved in `test-cards-original.json`, fixes in `test-cards-revised.json`, ground truth in `human-review-findings.md`.
- [x] **1B-8a**: Automated review pass validation — calibrate the AI self-critique review loop.
  **Architecture**: AI1 (generator/Sonnet) generates card → AI2 (reviewer) asks "critically review this card" → AI1 self-critiques → AI2 does sentiment analysis: if AI1 is confident card is good → PASS; if uncertain or flags issues → prod further → loop (max N iterations to prevent cost runaway). After the self-critique loop, AI2 asks a set of **explicit pointed questions** to catch blind spots the self-critique misses.
  **Calibration process**: Run this loop on `test-cards-original.json` (15 cards, without knowledge of findings). Compare output against `human-review-findings.md` ground truth. Issues the self-critique catches → validated. Issues it misses → become explicit pointed questions added to the review prompt. Target: ≥70% true positive rate on FAIL cards, ≥50% on WARN cards.
  → Inputs: `output/sets/ASD/mechanics/test-cards-original.json`, `output/sets/ASD/mechanics/approved.json`
  → Comparison: `output/sets/ASD/mechanics/human-review-findings.md`
  → Output: `output/sets/ASD/mechanics/auto-review-results.md` (findings + accuracy score + explicit questions list)
  → Results: FAIL detection 8/8 = 100% (target ≥70%), WARN detection 1/2 = 50% (target ≥50%). Self-critique catches reminder text + keyword nonbos; pointed questions essential for kitchen sink, false variability, enters-tapped irrelevance. Over-sensitive (5-6 false positives). $0.34 cost. Script: `research/scripts/auto_review_calibration.py`.
- [x] **1B-8b**: Rename "Scavenge" mechanic — name collides with existing MTG keyword (Return to Ravnica, 2012). HUMAN: chose "Salvage". Updated `approved.json`, `distribution.json`, test cards (original/revised/test-cards.json), `validation-spike-results.md`, `human-review-findings.md`. 7 files modified.
- [x] **1B-8c**: A/B test review-and-revise strategies — find the best AI review loop for Phase 1C.
  **Plan**: `plans/phase-1b-ab-test.md`
  **Test set**: 7 cards (2 PASS regression, 5 FAIL/WARN) from `test-cards-original.json`
  **Strategies** (9 total, 4 Sonnet + 4 Opus mirrors + 1 council):
  - S1/S5: Simple — single prompt "critically review, improve or OK"
  - S2/S6: Iterative — same prompt, loop until OK (max 5 iterations)
  - S3/S7: Detailed — single prompt with comprehensive checklist + pointed questions
  - S4/S8: Split — 3 separate passes (templating → mechanics → balance), then combine + revise
  - S9: Council — 3 independent Opus reviewers + consensus synthesizer (2-of-3 filter)
  **Output**: Per-card reports with original card, full conversation log, revised card, cost. → `output/sets/ASD/mechanics/ab-test/<strategy>/`
  **Evaluation**: HUMAN reviews revised cards for quality, regression, overnerfing, cost efficiency.
  **Budget**: ~$10-19 total across all 9 strategies.
  → **Round 1 results** (session 11, Opus 4.0): $3.83 total. Provisional winner: Hybrid (S4 Split/Sonnet + Opus sanity check). **Superseded by Round 2** — see 1B-8d below.
  → **Round 2** (session 12, Opus 4.6 + effort=max + S9 council): Partial — S1, S2, S5, S6, S9 complete. S3, S4, S7, S8 need rerun (thinking+truncation issues fixed mid-run). See `learnings/phase1b.md` for details.
  → **Round 2 complete** (session 13, Opus 4.6): S3-S9 all rerun successfully. Rerun cost: $1.45 (S3 $0.37, S4 $0.27, S7 $0.37, S8 $0.44) + S9 rerun $0.49. Human evaluated all 9 strategies.
  **Round 2 scores**: S1=4/7, S2=6/7, S3=5/7, S4=5/7, S5=4/7, S6=6/7, S7=5/7, S8=6/7, S9=6/7.
  **Key findings**: (1) Simple prompts miss nonbos even on Opus. (2) Detailed/split prompts catch nonbos but single-pass undernerfs balance. (3) Iteration fixes balance via multiple passes but can't fix false OKs. (4) Council produces most creative fixes but creativity → rules breakage risk. (5) The difference between simple and detailed is just one sentence ("List any issues with templating, mechanics, balance, design, or color pie") — the S7 detailed checklist was mostly superfluous. (6) Analysis ≠ action: S7 detected everything but produced worst fixes.
- [x] **1B-8d**: HUMAN: Pick winning strategy from A/B test results. Document choice and rationale.
  → **Winner: Tiered council+iteration hybrid.**
  **C/U cards**: Council-style prompt (single reviewer, category-nudge) + iteration (continue conversation, loop until OK or max N).
  **R/M cards**: Full council (3 independent Opus reviewers + consensus synthesizer) + iteration.
  **Token optimizations**: (1) Only include mechanic defs relevant to the card. (2) Skip synthesis if all 3 council reviewers say OK. (3) Use Anthropic prompt caching — batch by mechanic to maximize cache hits. (4) Continue conversation for iteration instead of fresh context each loop.
  **Rationale**: S6 (iterative/Opus) and S9 (council/Opus) tied at 6/7 with complementary strengths — iteration polishes balance, council catches nonbos and produces creative fixes for complex cards. Council creativity is valuable for R/M but overkill for C/U. The best way to minimize review cost is a strong initial generation prompt+model — don't generate with Haiku if you'll spend a fortune fixing afterwards.
  **Estimated cost**: ~$0.10/card C/U, ~$0.11/card R/M → ~$6-7 for 60-card dev set review pass.
- [x] **1B-9**: Write learnings → `learnings/phase1b.md`
  → Updated with Round 1 + Round 2 results, API learnings (thinking, effort, truncation), cost update.

---

## Phase 1C: Card Generator
> **Plan**: `plans/phase-1-set-design-engine.md` Section 1C
> **Needs**: 1B (mechanics), 0E (proven prompts, BEST-SETTINGS.md)
> **Inputs**: `output/sets/<code>/skeleton.json`, `research/prompt-templates/BEST-SETTINGS.md`, `research/prompt-templates/system-prompt-v*.md`, `output/sets/<code>/mechanics/approved.json`
> **Outputs**: Dev set (~60 card JSON files) in `output/sets/<code>/cards/`, `mtgai.validation` library, `learnings/phase1c.md`
> **What this does**: Build the validation library (heuristic first-pass gates), then generate cards filling skeleton slots via LLM with validation-retry loops. **Development mode**: generate a ~60-card dev set (covers all rarities, colors, and card types) to validate the full pipeline before scaling to 280. Cards go through: generate → heuristic validate → retry with feedback → save. Design-level quality review happens in Phase 4A+4B (AI review pipeline from 1B learnings).
>
> **1B learnings applied**:
> - Fold the 8 pointed questions from 1B into generation prompts as **preventive guidance** (cheaper to prevent than detect): no haste on malfunction creatures, always include reminder text for custom mechanics, don't use overclock as mandatory cost then check condition, etc.
> - Use full color names (not abbreviations) in all Sonnet prompts to avoid R≠Red confusion.
> - Fix U+FFFD encoding in test card data before production generation.
> - Heuristic validators are first-pass gates only — they catch formatting issues but NOT design issues (kitchen sink, keyword nonbos, false variability). Design review is in 4A+4B.

- [x] **1C-fix1**: Fix U+FFFD encoding in `output/sets/ASD/mechanics/test-cards-original.json` (em dashes replaced with Unicode replacement character — known issue from 1B A/B test)
  → Fixed in session 12: 16 U+FFFD → em dash (U+2014) in both `test-cards-original.json` and `test-cards.json`.
- [x] **1C-val1**: Build `mtgai.validation.rules_text` — regex-based MTG rules text grammar checks (self-reference ~, keyword spelling, trigger/activated/static patterns, mana symbol format, "enters" not "enters the battlefield")
  → Expanded scope: 16 checks including "enters the battlefield"→"enters", "Tap:"→"{T}:", haste+Malfunction nonbo, custom mechanic reminder text, informal costs, parenthetical reminder text detection, keyword capitalization, "cannot"→"can't". Also built `schema.py` (Pydantic parse validation), `mana.py` (CMC/color/identity consistency — 9 checks), and `type_check.py` (creature P/T, PW loyalty, aura/equipment structure — 9 checks).
- [x] **1C-val2**: Build `mtgai.validation.text_overflow` — character count heuristic using config text overflow constants
  → 5 checks: name (30), type line (45), oracle text (300/350/400 by type), flavor (200), combined.
- [x] **1C-val3**: Build `mtgai.validation.uniqueness` — exact name collision detection within the set
  → 4 checks: exact name, near-duplicate name (Levenshtein ≤ 2), collector number collision (AUTO-fixable), mechanical similarity (> 80% text + same CMC/color/type).
- [x] ~~**1C-val4**: Build `mtgai.validation.spelling`~~ — DELETED. LLMs don't misspell. Keyword capitalization and "cannot"→"can't" checks moved to `rules_text.py`.
- [x] **1C-val5**: `power_level.py` — P/T vs CMC by rarity, NWO complexity for commons, removal efficiency, PW loyalty vs CMC, zero-CMC nonland. All MANUAL (flags for LLM review).
- [x] **1C-val6**: `color_pie.py` — 24-category ability-to-color lookup table. All MANUAL (flags for LLM review).
- [x] **1C-val7**: Severity refactor — renamed HARD/SOFT to AUTO/MANUAL. AUTO errors are deterministically fixed post-validation (17 registered auto-fixers). MANUAL errors feed structured retry prompts to the LLM. Auto-fix registry with lazy loading, `validate_card_from_raw()` returns `(card, errors, applied_fixes)`.
  → 8 validator modules, ~50 distinct checks, 17 auto-fixers, 73 tests. Runner + auto-fix system + feedback formatter in `__init__.py`.
- [x] **1C-gen**: Implement card generation pipeline — LLM calls (tool use / function calling for structured output), batch of 5, validation chain, auto-fix AUTO errors, MANUAL errors ride along as metadata for Phase 4A+4B review. Generation prompts include 8 pointed questions from 1B as preventive design guidance + full color names. Uses Opus 4.6 with effort=max for all generation. Extensive per-batch and per-card logging.
  → `backend/mtgai/generation/card_generator.py` (pipeline), `backend/mtgai/generation/prompts.py` (prompt construction), `backend/mtgai/generation/llm_client.py` (API client with effort param). Also fixed `validation/schema.py` to parse `type_line` → `card_types`/`supertypes`/`subtypes` (eliminated 76 false positive MANUAL warnings).
- [x] **1C-common**: Generated 21 commons across W/U/B/R/G. All validated + auto-fixed.
- [x] **1C-uncommon**: Generated 21 uncommons including multicolor signpost uncommons.
- [x] **1C-rare**: Generated 14 rares. All single-batch (no single-card fallback needed).
- [x] **1C-mythic**: Generated 4 mythics (all Opus 4.6 + effort=max). Includes legendary creatures.
  → All 60 cards generated in one pipeline run: 16 batches, $2.78 total, 7.4 minutes, zero failures. 42/60 clean, 18 with real MANUAL warnings stored for Phase 4A+4B review. Cards saved to `output/sets/ASD/cards/`, logs to `output/sets/ASD/generation_logs/`.
- [x] **1C-postgen**: Post-generation cleanup: scrubbed Unicode em dashes from all 59 card JSONs, fixed type_line parser to handle `--` dashes, fixed false positive creature type_check errors, added enchantment-artifact AUTO fixer (#18), narrowed informal mana production regex, generated card gallery (`output/sets/ASD/card_gallery.md`) with live validation via `scripts/gen_card_gallery.py`. Identified critical pipeline gap: skeleton needs a constraint derivation step (22 artifact-caring cards vs 6 artifacts).
  → Validator now at 8 validators, 18 auto-fixers. Gallery script runs live validation (not stale logs). Key finding: skeleton needs LLM revision pass to align type distribution with mechanic requirements before card generation.
- [x] **1C-reprint-research**: Analyzed reprint patterns across 5 reference sets. Key findings: avg 7.8 reprints/set (2.8%), removal is #1 role (33%), mana fixing #2 (21%), combat tricks #3 (15%). Commons lead by count, mythics by percentage. Built reprint selector pipeline module (`mtgai/generation/reprint_selector.py`) with 75-card curated staple pool, deterministic role-based matching, and splashy reprint scoring (EDHREC popularity + age + thematic fit). 35 tests, $0 LLM cost.
  → `research/reprint-analysis.md`, `research/set-template.json` (reprints section), `backend/mtgai/generation/reprint_selector.py`, `backend/mtgai/generation/reprint_pool.json`, `backend/tests/test_reprint_selector.py`
- [x] **1C-reprint**: Select reprint cards from Scryfall data to fill identified skeleton slots. Use reprint analysis to pick candidates that fit the "Anomalous Descent" theme and support draft archetypes. HUMAN: approve reprint selections.
  → Refactored reprint selector: replaced rule-based scoring with single Haiku LLM call (~$0.002). Haiku sees set config + pre-filtered candidates per slot (color/rarity/type match), picks best N reprints with reasoning. 48 tests, all passing. Selected 2 reprints: Murder (B-C-03) and Elvish Mystic (G-C-01). Replaced Dungeon Rot and Wilderness Tracker. Architecture note: reprints should run BEFORE generation in future pipeline runs.
- [x] **1C-lands**: Generate nonbasic lands + basic land flavor text (5 basics = 1 per color for dev set)
  → Single Haiku call (~$0.002, 452 output tokens): 5 basic lands with set-themed flavor text + 1 common nonbasic (Descent Waypoint, W/U tapped dual). 6 card JSONs saved to `output/sets/ASD/cards/L-*.json`. Total set now 66 cards (60 main + 2 reprints replaced + 6 lands added).
- [x] **1C-review**: HUMAN: Big-picture set review (NOT card-by-card — that happens after AI review in 4A+4B).
  → Review complete. Key findings documented in `learnings/phase1c.md` under "1C Human Review findings":
  - Mechanics feel distinct and fun, but distribution is wrong: Salvage ~12 cards (planned 6), Malfunction 1 (planned 5), Overclock 1 (planned 3). Root cause: skeleton assigns complexity tiers, not specific mechanics.
  - Missing multicolor signposts for UR/UG/BR/BG/RG and missing legendaries (5 of 8) are 60-card budget effects — auto-resolve at ~280 cards.
  - Pipeline gaps identified for Phase SC: mechanic-to-slot assignment, constraint derivation, legend-to-slot mapping, notable card enforcement, planeswalker slot reservation.
  - 7 cards flagged for Phase 4A+4B AI review: Koyl Yrenum (color pie), Cult Savant (reanimation in blue), Law of the Wilderness (uncommon too powerful), Automated Sentry Grid (oppressive), Feretha (wrong colors), Reclaim the Surface (too narrow), Raider's Bounty (too punishing).
  - Flavor text quality A+. Set identity coherent but mechanically skewed toward Salvage.
  - Mana fixing too thin (Descent Waypoint WU-only). Reprints need flavor text.
- [x] **1C-learn**: Write learnings → `learnings/phase1c.md`
  → Comprehensive learnings covering generation stats, validation results, 8 issues found (artifact density imbalance, prompt/validator P+T discrepancy, reminder text schema, Unicode, enchantment-artifact, type_line parser, informal mana, false positive creature errors). Key pipeline insight: need skeleton revision step driven by mechanic analysis.

---

## Phase 4A+4B: Balance Gate + AI Design Review
> **Plan**: `learnings/phase1b.md` (section "Winning strategy: Tiered council+iteration hybrid", lines 160-172)
> **Needs**: 1C (dev set cards generated)
> **Inputs**: `output/sets/<code>/cards/*.json`, `research/set-template.json` (target ranges), `output/sets/<code>/mechanics/approved.json`, `learnings/phase1b.md` (pointed questions, strategy specs)
> **Outputs**: `output/sets/<code>/reports/balance-report.md`, `output/sets/<code>/reviews/` (per-card AI review logs), revised card JSONs
> **What this does**: Two-part gate before art investment. **Part A**: Statistical balance analysis (mana curves, P/T, removal density). **Part B**: AI design review using the **tiered council+iteration hybrid** proven in Phase 1B A/B test (Round 2, S9 Council).
>
> **Winning strategy from 1B A/B test** (see `learnings/phase1b.md` lines 160-172):
> - **C/U cards**: Single Opus reviewer with category nudge ("List any issues with templating, mechanics, balance, design, or color pie") + iteration (continue conversation, loop until OK or max N). ~$0.10/card.
> - **R/M cards**: Full council (3 independent Opus reviewers + consensus synthesizer, 2-of-3 filter) + iteration. ~$0.11/card.
> - **Planeswalkers/sagas**: Skip any Sonnet stage, go straight to Opus council.
> - **No Sonnet stage**: Opus 4.6 ($5/$25) is only ~1.7x Sonnet ($3/$15) and dramatically better at nonbos, balance, conditional reasoning. Sonnet cannot reason about mandatory-cost-as-conditional, malfunction as downside, or color abbreviations.
> - **Token optimizations**: Only include relevant mechanic defs, skip synthesis if all 3 council reviewers say OK, batch by mechanic for prompt caching, continue conversation for iteration.
> - **Estimated cost**: ~$6-7 for 60-card dev set.
> - Every AI review must produce a detailed log (prompt, full response, cost) for diagnosing bad reasoning.
> - The 8 pointed questions evolve — add new failure modes discovered during 1C generation.
>
> **Pointed questions** (from 1B, evolving):
> 1. Keywords negated by other abilities? (e.g., haste + malfunction)
> 2. ~~Reminder text present for all custom mechanics?~~ — **REMOVED**: reminder text is now injected programmatically after review, not generated by LLM.
> 3. Conditional actually meaningful — can it be false? (e.g., mandatory overclock + "if you overclocked")
> 4. Power level appropriate for rarity?
> 5. Kitchen sink — too many unrelated effects on one card?
> 6. Variable effects genuinely variable? (e.g., "per card exiled" when always exactly 3)
> 7. Mechanic name collision with existing MTG keywords?
> 8. "Enters tapped" relevant on this permanent type?

**--- Part A: Balance Analysis (skeleton conformance + set-wide coverage) ---**

- [x] **4A-1**: Skeleton conformance analysis — per-slot checks (color, rarity, card type, CMC, complexity tier match). 49/60 slots matched on ASD dev set.
- [x] **4A-2**: Creature CMC curve per color — flag gaps where a color has no creatures at a given CMC. Found gaps at CMC 4-6 (expected at 60 cards).
- [x] **4A-3**: Creature size distribution per color — weight classes (small/medium/beefy/huge by P+T sum).
- [x] **4A-4**: Removal spell density check per color — regex detection + mechanic functional tags. Ensures minimum removal at common/uncommon.
- [x] **4A-5**: Card advantage sources per color — regex detection + mechanic functional tags. Counts Salvage/Overclock as CA via tags.
- [x] **4A-6**: Mechanic distribution — planned vs actual counts. Confirmed Salvage 12 vs planned 6, Malfunction 3 vs 5, Overclock 1 vs 3.
- [x] **4A-7**: Mana fixing inventory — 4 sources found. Color balance check — nearly perfect (W:10, U:10, B:10, R:9, G:9).
- [x] **4A-8**: Generate balance reports → `output/sets/ASD/reports/balance-report.md` + `balance-analysis.json` (structured JSON for 4B AI review consumption).
- [x] **4A-9**: CLI command `python -m mtgai.review balance --set ASD`. 75 tests in `tests/test_analysis/`. All 490 project tests passing.
- [x] **4A-10**: Add `functional_tags` field to `Mechanic` model + retroactive `functional-tags.json` for ASD. Learnings documented for Phase 1B integration.
- [x] ~~**4B-1 through 4B-5**: Limited environment analysis (sealed pools, booster composition, draft archetypes, limited report)~~ — **CUT**. Skeleton + card generation rules guarantee Limited viability by construction. Sealed sims meaningless at 60 cards, marginal even at 280. AI design review (4B-review) catches actual quality issues. Pack generator can be built as polish before printing if desired.

**--- Part A-rev: Skeleton Revision + Targeted Regeneration ---**
> **Plan**: `plans/phase-4a-rev-skeleton-revision.md`
> 4A findings split into two buckets: **card-level** issues (color pie, power level, text overflow — handled by AI review in 4B) and **set-level** issues (mechanic distribution, artifact density, complexity tier mismatches — can't be fixed by reviewing individual cards). This step fixes set-level issues by having an LLM propose slot changes then regenerating only the affected cards.
>
> **Set-level issues to fix** (from 4A + 1C-review):
> - Mechanic distribution: Salvage 12 vs planned 6, Malfunction 3 vs 5, Overclock 1 vs 3
> - Complexity tier mismatches (11 cards)
> - Artifact density too low for Salvage archetype
> - At 280: missing legendaries, missing signpost uncommons, CMC curve gaps

- [x] **4A-rev-1**: Build revision pipeline (`backend/mtgai/generation/skeleton_reviser.py`):
  - Compact card serializer (~100 chars/card: `slot_id | name | cost | type P/T | oracle truncated`)
  - Revision prompt: compact card list + balance findings + mechanic defs/targets + theme → Opus 4.6 effort=max
  - Tool schema (`propose_revision_plan`): returns structured `{analysis, changes[], expected_improvements}`
  - `apply_revision_plan()`: archive old cards, update skeleton slot constraints (notes field), regenerate via 1C pipeline
  - `run_revision()`: full loop — serialize → prompt → apply → regenerate → validate → re-run 4A → loop if needed (max 2 rounds)
  - RevisionPlan/SlotChange Pydantic models
  → `backend/mtgai/generation/skeleton_reviser.py` (580 lines), `backend/tests/test_skeleton_reviser.py` (23 tests). All 513 project tests pass. CLI: `python -m mtgai.generation.skeleton_reviser [--dry-run] [--max-rounds N]`
- [x] **4A-rev-2**: Run skeleton revision on ASD dev set. Verify mechanic distribution and artifact density improve. Archive replaced cards.
  → 2 revision rounds (Opus, $3.38) + 1 fix regeneration (Haiku, $0.065). Initial run: 32 cards replaced (19 R1 + 13 R2) but regenerated cards didn't use requested mechanics due to two bugs: (1) `prompts.py:format_slot_specs` wasn't including the `notes` field in generation prompts, (2) `skeleton_reviser.py:apply_revision_plan` only applied `notes` from `new_constraints`, silently dropping `mechanic_tag`/`card_type` updates. After fixing both bugs, re-ran 11 affected slots with Haiku — 100% mechanic adherence. Final mechanic distribution: Salvage 8 (planned 6), Malfunction 7 (planned 5), Overclock 4 (planned 3). Color balance: W:10, U:10, B:10, R:9, G:9. 0 FAIL issues. 33 cards archived in `output/sets/ASD/cards/archive/`. Logs in `output/sets/ASD/revision_logs/`.

**--- Part B: AI Design Review (1B Tiered Council+Iteration Hybrid) ---**

- [x] **4B-review-infra**: Build AI review pipeline infrastructure. Implement the **tiered council+iteration hybrid** from 1B A/B test:
  1. **C/U tier — Single Opus reviewer + iteration** (~$0.10/card): Category nudge prompt ("List any issues with templating, mechanics, balance, design, or color pie") + iteration loop (continue conversation, max 5 iterations, loop until OK). Opus 4.6 effort=max.
  2. **R/M tier — Full Opus council + iteration** (~$0.11/card): 3 independent Opus reviewers analyze each card (same prompt, no cross-contamination). Synthesizer applies 2-of-3 consensus filter, produces revision. If REVISED, iterate until OK or max 5 iterations. Skip synthesis if all 3 reviewers say OK.
  3. **Planeswalkers/sagas**: Always use council tier regardless of rarity.
  Infrastructure must include: per-card review logging (prompt, full response, tool calls, cost, verdict) saved to `output/sets/<code>/reviews/<collector_number>.json`. The pointed questions list should be loaded from a config file (`output/sets/<code>/mechanics/pointed-questions.json`) so it can evolve as new failure modes are discovered. Token optimizations: only include relevant mechanic defs per card, batch by mechanic for prompt caching, continue conversation for iteration.
  → `backend/mtgai/review/ai_review.py` (1050+ lines), `output/sets/ASD/mechanics/pointed-questions.json` (8 questions). Pydantic models: ReviewIssue, ReviewVerdict, ReviewIteration, CouncilMemberReview, CardReviewResult. Tool schemas: submit_review (OK/REVISE + revised card), submit_synthesis (2-of-3 consensus). Respects MTGAI_MAX_MODEL env var via `generate_with_tool()`. Resumable (skips existing review logs). CLI: `python -m mtgai.review ai-review [--dry-run] [--card W-C-01]`. Dry-run verified: 41 single + 18 council = 59 cards (skips 5 basic lands + 2 reprints). All 513 tests pass.
- [x] **4B-reminder**: Programmatic reminder text injection pipeline. LLMs no longer generate reminder text — it's injected deterministically from mechanic definitions after review.
  - `backend/mtgai/generation/reminder_injector.py`: `strip_reminder_text()`, `inject_reminder_text()`, `finalize_reminder_text()`. Generic use-vs-reference heuristic: `keyword_ability` requires keyword+number for injection, `keyword_action` checks clause context (skips trigger/conditional patterns like "whenever you [keyword]"). Number-to-word substitution + singular/plural.
  - `backend/mtgai/review/finalize.py`: Post-review finalization pipeline — inject reminder text → full validation → auto-fix → save. Produces `finalize-report.md` with MANUAL errors for human review. CLI: `python -m mtgai.review finalize [--set ASD] [--dry-run] [--card W-C-01]`.
  - Validation updates: removed Check 11 (reminder_in_oracle) and Check 12 (custom_mechanic_no_reminder) from `rules_text.py`. Check 2 (self-reference) now skips parenthesized text. Check 10 (line_period) accepts `)` as valid ending. `text_overflow` strips reminder text before measuring.
  - Prompt updates: generation prompts now say "do NOT include reminder text". AI review prompts no longer check for reminder text.
  - Tests: 31 tests in `test_reminder_injector.py` (strip, inject uses, inject references, finalize), 6 tests in `test_finalize.py`. All 548 project tests pass.
  - Dry-run on ASD: 61 cards processed, 11 modified (reminder injection), 5 auto-fixes, 2 genuine MANUAL errors for human review.
- [x] **4B-review-run**: Run AI review on all 60 dev set cards:
  1. Single-reviewer + iteration on all C/U cards.
  2. Council + iteration on all R/M cards and planeswalkers/sagas.
  3. Apply revisions to card JSONs. Log all changes with full prompts/responses/costs.
  4. Generate review summary report.
  → `output/sets/<code>/reviews/`, `output/sets/<code>/reports/ai-review-summary.md`
  - **Results**: 59 cards reviewed (Murder reprint skipped), 58 OK / 1 REVISE (UB-U-01), 6 cards changed. Ran on Haiku (effort=max), cost $0.58. 118 review log files generated.

**--- Gate: Human Review ---**

- [x] **4B-finalize**: Run `python -m mtgai.review finalize --set ASD` after 4B-review-run completes. Injects reminder text, re-validates, auto-fixes, saves. Review `finalize-report.md` for any MANUAL errors.
  - **Results**: 61 cards, 11 modified (reminder injection), 5 auto-fixes, 2 MANUAL errors resolved:
    - G-R-02 "this creature" false positive: validator didn't skip quoted granted-ability text (`has "When this creature dies, ..."`). Fixed Check 2 in `rules_text.py` to strip double-quoted strings before matching.
    - B-R-02 empty type_line: `fix_enchantment_artifact` relied on `card_types` (empty) instead of parsing `type_line` directly. Fixed fixer in `type_check.py`, manually corrected card JSON to "Legendary Artifact".
    - W-C-02 overstatted (2/3 at CMC 2): deferred to human review at 4AB-gate.
  - Review gallery built: `output/sets/ASD/reports/card-review-gallery.html` (MTG-style card frames + reviewer comments). Generator script: `build_gallery.py`.
- [x] **4AB-gate**: HUMAN: Card-by-card "art ready" review. All 66 cards approved as art-ready by human reviewer (2026-03-14). Cards passed through heuristic validation (1C), statistical balance (4A), AI review (4B), and post-review finalization — human elected to approve all without individual edits.

---

## Phase 2A: Art Direction System
> **Plan**: `plans/phase-2-art-rendering-pipeline.md` Section 2A
> **Needs**: Set theme (from 1A). Can run parallel with Phase 1.
> **Inputs**: Set theme/description, `research/tech-decisions.md` (image generation model choice)
> **Outputs**: `output/sets/<code>/art-direction/style-guide.md`, prompt templates per card type, character reference images, set symbol SVG, `learnings/phase2a.md`
> **What this does**: Define the visual identity — color palette, mood, composition guidelines, character references. Generate 20 sample arts as go/no-go gate. This phase involves significant HUMAN judgment on art style preferences.

- [x] **2A-1**: HUMAN: Create style guide collaboratively — color palette, mood, setting, architecture, flora/fauna, per-color visual identity → `output/sets/ASD/art-direction/style-guide.md`
  - Stylized digital illustration (bold shapes, strong silhouettes, painterly texture). Researched ASE original art, Thundarr, Moebius, Dying Earth for visual DNA. Dual palette: warm/dusty surface, cool/eerie dungeon. Deadpan serious rendering of absurd subjects.
- [x] **2A-2**: Define art prompt templates per card type (creature, spell, land, artifact, planeswalker) — plan Section 2A.2
  - Flux-optimized prompts: subject front-loaded, 40-60 words, one style sentence. No negative phrasing, no game jargon, no setting-specific names.
  - Built `backend/mtgai/art/prompt_builder.py` — Haiku translates MTG → visual English, Flux sanitizer strips setting terms. Generated all 66 prompts ($0.10, zero errors, temp 0.6).
  - Built `backend/mtgai/art/visual_reference.py` — loads from `visual-references.json` (data-driven per set, not hardcoded). 13 creature types, 5 factions, 4 landmarks, 8 legendary characters sourced from ASE PDF.
  - Gallery updated with collapsible "Art Prompt" section per card: `output/sets/ASD/reports/card-review-gallery.html`
- [x] **2A-3**: Set up character consistency workflow — document visual descriptions, plan reference image pipeline
  - Visual reference dictionary in `visual-references.json` (data-driven, loaded by `visual_reference.py`) with descriptions for all 8 legendary characters, creature types, factions, landmarks. Sourced from ASE module PDF.
  - Character consistency plan: Flux Kontext Dev + PuLID for identity extraction. Generate neutral reference portraits (2A-5), then inject via PuLID during card art generation (2A-6/2B). PuLID extracts only face identity, ignoring reference style — text prompt controls all styling.
  - `prompt_builder.py` has `get_character_ref_paths()` to detect which cards need character refs and log reference image paths.
- [x] **2A-4**: Define artist style variation personas — different "artist" prompt prefixes to simulate varied art styles
  - 8 personas mapped to card colors (W=Classical Authority, U=Clinical Futurism, B=Dark Grotesque, R=Dynamic Action, G=Naturalist Exploration, Artifact=Technical Precision, Multi=Style Collision, Land=Panoramic Wonder). No extra data plumbing — reads `card.colors` directly.
- [x] **2A-5-infra**: ComfyUI + Flux.1-dev local image generation pipeline
  - ComfyUI installed at `C:\Programming\ComfyUI` with Flux.1-dev Q8_0 GGUF (12GB)
  - Built `backend/mtgai/art/image_generator.py` — batch generation via ComfyUI API, auto-start, VRAM pre-check, resumable progress
  - Built `backend/mtgai/art/art_selector.py` — Haiku vision picks best of 3 versions per card ($0.006/card)
  - Built `backend/scripts/generate_all_art.py` — standalone batch runner for overnight generation
  - API workflow JSON at `backend/mtgai/art/workflows/flux_dev_gguf.json`
  - Settings: 30 steps, 1024×768, euler sampler, guidance 3.5
  - Performance: ~40s/image warm, ~60s cold start. Full batch (198 images) ~2.2 hours
  - Key bug fixed: `subprocess.PIPE` crashes tqdm on Windows → use `subprocess.DEVNULL`
  - Learnings: `learnings/phase2a-comfyui.md`
- [x] **2A-5-batch**: 66 cards × 3 versions = 198 images generated via Flux.1-dev Q8_0 local (~2.5 hours total across interrupted sessions)
- [x] **2A-5-select**: Haiku art selector picked best version per card. 66/66 high confidence, $0.37. Report: `output/sets/ASD/reports/art-selection-report.html`
- [x] **2A-5-review**: HUMAN: Reviewed. Art quality sufficient for dev set pipeline validation. Key issues: anatomy problems (mangled limbs), too photorealistic (need stronger painterly style anchors), Haiku judge doesn't catch anatomy errors. Production set will need external art model + better judge LLM. Learnings: `learnings/phase2a-art-quality.md`
- [ ] **2A-5**: Generate character reference portraits for all 8 legendary characters using Flux dev (text-to-image from visual-references.json descriptions). Simple neutral headshots — plain background, even lighting, front-facing. Store in `output/sets/<code>/art-direction/character-refs/`.
- [ ] **2A-5b**: HUMAN: Review character reference portraits. Pick the best version for each character. These become the canonical identity references.
- [ ] **2A-6**: Generate 10+ sample card arts across card types using Flux dev. For cards featuring legendary characters, use Kontext Dev + PuLID workflow to inject character identity from reference portraits while letting the text prompt control style. Evaluate consistency and quality.
- [ ] **2A-7**: HUMAN: Go/no-go gate — 20 sample arts evaluated. Sufficient quality? Cohesive identity? Character consistency across cards? If NO, reassess image generation approach.
- [ ] **2A-8**: Finalize set symbol SVG (replaces Phase 0B placeholder) → `assets/symbols/set-symbol.svg`
- [ ] **2A-9**: Write learnings → `learnings/phase2a.md`

---

## Phase 2B: Art Generation Pipeline
> **Plan**: `plans/phase-2-art-rendering-pipeline.md` Section 2B
> **Needs**: 1C (card data), 2A (style guide + prompts), 4A+4B balance gate PASSED
> **Inputs**: `output/sets/<code>/cards/*.json`, `output/sets/<code>/art-direction/style-guide.md`, art prompt templates
> **Outputs**: Art images in `output/sets/<code>/art/`, `learnings/phase2b.md`
> **What this does**: Generate art for dev set (~60 cards). Batch process with rate limiting. Automated QA + human review. Validates the full art pipeline before scale-up.

- [ ] **2B-1**: Build batch art generation pipeline — rate limiting, error handling, resume from interruption
- [ ] **2B-2**: Generate art prompts for dev set cards using cheaper model (GPT-4o-mini / Haiku) — card data + style guide → image prompt
- [ ] **2B-3**: Generate art for dev set (~60 images across all rarities and types)
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
- [ ] **2C-7**: Render dev set (~60 cards) → `output/sets/<code>/renders/`
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
> **What this does**: Run quality checks on dev set rendered images (text overflow against actual renders, visual QA). Re-run all validators from 1C. Validates the QA tooling before scale-up.

- [ ] **4C-1**: Full-set rules text grammar validation (re-run `mtgai.validation.rules_text` on all cards)
- [ ] **4C-2**: Spell check across all card text fields
- [ ] **4C-3**: Duplicate/near-duplicate detection across full set
- [ ] **4C-4**: Flavor text quality check (not empty where expected, not present where card is too complex)
- [ ] **4C-5**: Cross-card interaction sanity checks (no infinite combos at common, no broken 2-card synergies)
- [ ] **4C-6**: Text overflow validation against actual rendered card images (not just character count heuristic)
- [ ] **4C-7**: Generate quality report → `output/sets/<code>/reports/quality-report.md`
- [ ] **4C-8**: Write learnings → `learnings/phase4.md`

---

## Phase SC: Scale-Up — Full Set Production
> **Plan**: Uses proven pipeline from Phases 1C, 4A+4B, 2B, 2C, 4C
> **Needs**: 4C passed on dev set — all tooling validated end-to-end
> **Inputs**: `output/sets/<code>/skeleton.json` (regenerated at full ~280 size), all pipeline code from prior phases
> **Outputs**: Full ~280-card set: cards, art, renders, balance + quality reports, `learnings/phase-sc.md`
> **What this does**: Now that the entire pipeline is proven on the ~60-card dev set, regenerate the skeleton at full size and run every card through the same pipeline. This is a production run, not a development phase — all tooling already works.

- [ ] **SC-1**: Regenerate skeleton at full set size (~280 cards) using `set_size` parameter. HUMAN: Review expanded skeleton.
- [ ] **SC-2**: Generate remaining cards to fill all skeleton slots (reuse dev set cards where they fit, generate ~220 new cards). Batch by color/rarity using proven 1C pipeline.
- [ ] **SC-3**: Run 4A balance analysis + 4A-rev skeleton revision on full set — proven tooling from dev set. Fixes mechanic distribution, artifact density, CMC gaps, missing legendaries/signposts automatically.
- [ ] **SC-4**: Run 4B AI design review on full set. HUMAN: Review balance + AI review reports. Fix any remaining issues.
- [ ] **SC-5**: Generate art for all new cards (~220 images) using proven 2B pipeline. May span multiple days.
- [ ] **SC-6**: HUMAN: Review art via gallery. Regenerate rejected art.
- [ ] **SC-7**: Render all ~280 cards using proven 2C pipeline.
- [ ] **SC-8**: Run full-set quality checks (4C) — rules text, spelling, duplicates, text overflow on renders.
- [ ] **SC-9**: HUMAN: Final review of complete set. Approve for print.
- [ ] **SC-10**: Write learnings → `learnings/phase-sc.md`

---

## Phase 5A: Print File Generation
> **Plan**: `plans/phase-4-5-validation-print.md` Section 5A
> **Needs**: SC passed, all ~280 cards rendered and validated
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
1A (skeleton ~60)  2A (art direction) ←── can run parallel
    │
    ▼
1B (mechanics)
    │
    ▼
1C (card gen ~60)  ←── DEV SET: validate pipeline
    │
    ▼
4A+4B (balance)    ←── smoke-test on dev set
    │
    ▼
2B (art gen ~60)
    │
    ▼
2C (render ~60)
    │
  ┌─┴──┐
  ▼    ▼
3A+3B  4C (quality) ←── can run parallel
  │    │
  └──┬─┘
     ▼
SC (SCALE-UP ~280)  ←── full production run through proven pipeline
     │                   (gen cards → balance → art → render → QA)
     ▼
5A (print files)
     │
     ▼
5B (print order)    ←── HUMAN: test batch then full order
     │
     ▼
5C (assembly)
```

---

## Session Notes

| Date | Session | Notes |
|------|---------|-------|
| 2026-03-08 | 1 | Completed Phase 0A (all 6 tasks) and Phase 0C (all 11 tasks). Phase 0B deferred — requires manual GPU/tool testing. Next: 0D (LLM strategy, needs 0C schema). |
| 2026-03-08 | 2 | Phase 0B: Completed 0B-render, 0B-font, 0B-symbol, 0B-print, 0B-specs, 0B-doc (6/9 tasks). Remaining: 0B-img (needs GPU), 0B-poc (needs art), 0B-learn (needs all done). Can proceed to 0D in parallel since 0C schema is ready. |
| 2026-03-08 | 3 | Phase 0D: COMPLETE (all 10 tasks). Claude Sonnet selected as primary ($2.57/set), batch of 5, Haiku for art prompts. Validation chain designed. ~$0.15 spent on testing. Next: 0E (prompt spike) or 0B-img (GPU). |
| 2026-03-09 | 4 | Phase 0E: 9/10 tasks done. T=1.0, FS=0, compressed context, tool_use. 4.73/5.0 confirmation. ~$1.42 spent on all experiments. Total API spend to date: ~$1.57. Awaiting HUMAN GO/NO-GO decision. Next: 0E-gate (human), then Phase 1A. |
| 2026-03-09 | 5 | Phase 0B: COMPLETE (all 9 tasks). Flux.1-dev selected for image gen (research-based, validate in Phase 2A). Render prototype upgraded with project fonts + mana symbols (7ms/card). All print specs locked. Next: 0E-gate (human GO/NO-GO), then Phase 1A. |
| 2026-03-09 | 6 | Phase 0E: COMPLETE — HUMAN GO decision. Added mechanic validation spike to 1B-7, Opus for planeswalkers/sagas in 1C. Adopted dev set approach (~60 cards) through all pipeline phases, with Phase SC (Scale-Up) for full ~280-card production. Updated TRACKER, phase-1, phase-3, cross-cutting-synthesis plans. Next: Phase 1A (set skeleton — HUMAN defines theme). |
| 2026-03-09 | 7 | Phase 1A: COMPLETE (all 11 tasks). Skeleton generator (897 lines), CLI review tool (Typer + Rich: list/show/stats + 7 Phase 3A stubs), 75 unit tests. Set: "Anomalous Descent" (ASD), 60-card dev set, all constraints pass. Fixed color balance remainder bug. $0 API cost. Next: Phase 1B (Mechanic Designer). |
| 2026-03-09 | 8 | Phase 1B: 7/9 tasks done. 3 mechanics approved: Scavenge X (W/U/G, dig for artifacts), Malfunction N (W/U/R, delayed power), Overclock (U/R/B, exile-and-play). LLM infra built (llm_client.py, mechanic_generator.py). Validation spike: 15 test cards, all GO (avg 4.77/5). $0.09 API cost. **BLOCKED on 1B-8**: human flagged issues with test card templating — revisit next session. |
| 2026-03-09 | 9 | Phase 1B-8: COMPLETE. Interactive human+Opus review of all 15 test cards found 9 issue categories across 8 FAIL + 2 WARN cards. Key findings: (1) "Scavenge" name collision with existing MTG keyword — needs rename, (2) haste negated by malfunction enters-tapped, (3) redundant conditional on Synaptic Overload hid broken power level, (4) Cascade Protocol 12 dmg for 5 mana wildly above rate + false variability, (5) missing reminder text on 5 cards. Two cards fully redesigned. Defined AI review architecture: AI1 self-critique → AI2 sentiment analysis → prod if uncertain → explicit pointed questions for blind spots. Added 1B-8a (calibration test) and 1B-8b (Scavenge rename). Files: `test-cards-original.json`, `test-cards-revised.json`, `human-review-findings.md`. Next: 1B-8a (run automated review calibration), 1B-8b (rename Scavenge). |
| 2026-03-09 | 10 | Phase 1B: 1B-8a/8b complete. Automated review calibration: FAIL detection 100% (8/8), WARN detection 50% (1/2). "Scavenge" renamed to "Salvage". Review loop has false positive problem (4/5 PASS cards flagged). Designed A/B test plan for 8 review-and-revise strategies. Next: 1B-8c (run A/B tests), 1B-8d (human picks winner), 1B-9 (learnings). |
| 2026-03-10 | 11 | Phase 1B: 1B-8c/8d complete. A/B tested 8 review strategies (4 Sonnet + 4 Opus) on 7 test cards, $3.83 total. Key findings: (1) Sonnet can't reason about mandatory-cost-as-conditional, (2) Sonnet doesn't understand malfunction-as-downside or R=Red, (3) Detailed analysis helps detection but hurts revision (Opus S7 identified but didn't fix balance), (4) Split approach best for Sonnet, (5) Iterative Opus only fully satisfactory but expensive + oscillation-prone. Provisional winner: Hybrid (S4 Split/Sonnet + Opus sanity check) — **superseded by Round 2 tiered council+iteration hybrid (session 13)**. Encoding issue (U+FFFD) in test data noted. Next: 1B-9 (learnings), then Phase 1C. |
| 2026-03-10 | 12 | Phase 1B: **PARTIAL REDO needed.** Discovered Round 1 A/B tests used Opus 4.0 ($15/$75), not 4.6 ($5/$25) — 3x cost difference invalidates Opus cost/benefit analysis. Rerunning all 9 strategies with Opus 4.6 + Sonnet 4.6 + `effort: "max"` for Opus. Added S9 (Council: 3 reviewers + 2-of-3 consensus). Fixed U+FFFD encoding in test cards. Completed S1 (4/7), S2 (6/7), S5, S6, S9 runs. S3/S4/S7/S8 hit thinking+truncation issues — removed thinking from all calls, added truncation guard, need rerun. API learnings: thinking incompatible with forced tool_choice, redundant for explicit analysis, `effort: "max"` is Opus-only. ~$2.97 spent on Round 2 so far. **Next: rerun S3/S4/S7/S8, human-evaluate S3-S9, pick final winner (1B-8d).** |
| 2026-03-14 | 14 | Pipeline restructuring: (1) **Cut 4B-1 through 4B-5** (limited environment analysis) — skeleton guarantees Limited viability by construction, sealed sims meaningless at 60 cards and marginal at 280. (2) **Split 4A findings** into card-level (→ AI review) and set-level (→ skeleton revision). Set-level issues can't be fixed by reviewing individual cards. (3) **Added Phase 4A-rev** (skeleton revision + targeted regeneration) between 4A and 4B-review: LLM proposes slot changes from compact card list + balance findings, regenerates only affected slots, re-runs 4A to verify. Plan: `plans/phase-4a-rev-skeleton-revision.md`. (4) Updated Phase SC to reuse 4A-rev tooling at 280 cards instead of deferring fixes. **Next: 4A-rev-1 (build revision pipeline), 4A-rev-2 (run on ASD dev set).** |
