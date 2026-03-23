# MTGAI Project Conventions

## Toolchain Buildout (in progress)
Making MTGAI a reusable tool for any set, not just ASD. Say "continue toolchain buildout" to resume.

**Done:** Model settings system (/settings), theme wizard (/pipeline/theme), per-stage LLM routing, set-config.json eliminated, theme extraction upgrade (PDF/text extraction, streaming LLM output, token counting, chunking, constraints + card suggestion extraction with AI-generated badges).

**Remaining:**
- Mechanic generation pipeline stage (refactor mechanic_generator.py, review UI for picking 3 from 6)
- Archetype generation pipeline stage (LLM generates 10 color-pair archetypes)
- Visual reference extraction stage (LLM extracts visual-references.json from setting prose)
- Pointed questions template (mechanic name substitution)
- Prompts module update (use setting prose + archetypes.json)
- Skeleton integration (card_requests → reserved slots, constraints → revision)
- Configure page integration (check theme.json exists before pipeline start)

**Design:** Human provides setting prose + constraints + card requests. Pipeline generates mechanics, archetypes, visual refs, skeleton, cards. See `memory/project_toolchain_buildout.md` for details.

## Project Structure
- Backend code lives in `backend/mtgai/`
- Tests live in `backend/tests/`, mirroring the source structure
- Research outputs go in `research/`
- Learnings go in `learnings/`
- Plans and tracker in `plans/` (TRACKER.md is the master progress file)
- Generated files (art, renders, print files) go in `output/` (gitignored)
- Card JSON files are version-controlled in `output/sets/<SET_CODE>/cards/`

## Development
- Python 3.12+, managed with uv
- Linting: `ruff check .` and `ruff format .` from `backend/`
- Tests: `pytest` from `backend/`
- All commands run from the `backend/` directory

## Code Style
- Use Pydantic v2 models for all data structures
- Use StrEnum for enumerations
- Use `X | Y` union syntax (not `Union[X, Y]`)
- Use `list[X]` (not `List[X]`)
- Line length: 100 characters
- Imports sorted by Ruff (isort rules)

## Data Models
- Card schema is the single source of truth: `mtgai/models/card.py`
- Field names match Scryfall's API where applicable (e.g., `oracle_text`, not `rules_text`)
- All models inherit from `pydantic.BaseModel`
- Card data is stored as JSON files in `output/sets/<SET_CODE>/cards/`

## Naming Conventions
- Card files: `<collector_number>_<card_name_slug>.json`
- Art files: `<collector_number>_<card_name_slug>_v<attempt>.png`
- Render files: `<collector_number>_<card_name_slug>.png`

## Pipeline
- Cards progress through statuses: draft -> validated -> approved -> art_generated -> rendered -> print_ready
- Every generation attempt is tracked (prompt, model, timestamp, success/failure)
- Pipeline is resumable: interrupted operations resume from the last incomplete card

## LLM Client (`mtgai/generation/llm_client.py`)
- `generate_with_tool()` — unified entry point, provider selected by `MTGAI_PROVIDER` env var
- **Two providers:**
  - `anthropic` (default): Anthropic API with forced `tool_choice`, prompt caching, effort levels
  - `ollama`: local models via Ollama's OpenAI-compatible API (cost = $0.00)
- **Ollama config** (env vars):
  - `MTGAI_PROVIDER=ollama` — switch to local model
  - `MTGAI_OLLAMA_MODEL=qwen2.5:14b` — model name (default: qwen2.5:14b)
  - `MTGAI_OLLAMA_URL=http://localhost:11434` — Ollama API endpoint
- **Ollama tool extraction**: tries native function calling first, falls back to JSON extraction from text (fenced blocks, Qwen-style, bare JSON), retries up to 2x on garbage output
- **Prompt caching** (Anthropic only, `cache=True`): system prompt and tool schema marked with `cache_control` so sequential calls within ~5 min reuse the cached prefix at 90% discount
- Centralized `PRICING`, `calc_cost()`, and `cost_from_result()` — all callers import from here
  - `calc_cost()` accounts for cache pricing: 1.25x for cache creation, 0.1x for cache reads
  - `cost_from_result(result)` convenience wrapper unpacks a `generate_with_tool` result dict
  - Returns 0.0 for local/unknown models
- Supports `effort` parameter (Opus-only): "max", "high", "low"
- Model tier capping via `MTGAI_MAX_MODEL` env var (set to "haiku", "sonnet", or "opus")
  - Higher-tier requests are downgraded to the cap model
  - `effort` is removed if dropping below Opus
- `thinking` is incompatible with forced `tool_choice` — don't use together
- Always use full color names in prompts (not abbreviations like "R")
- **Provider routing**: `_resolve_provider(model_id)` checks model registry first, falls back to `MTGAI_PROVIDER` env var

## Model Settings (`mtgai/settings/`)
- **Model registry** (`models.toml`): TOML file listing all available LLM and image-gen models with provider, pricing, capabilities (effort, vision, caching)
- **Model settings** (`model_settings.py`): per-stage model assignments, presets, save/load profiles
  - `get_llm_model(stage_id)` → returns API model_id for the stage
  - `get_effort(stage_id)` → returns effort level or None
  - `get_image_model(stage_id)` → returns image model key
  - `apply_settings(settings)` → saves as `output/settings/current.toml`
  - `ModelSettings.from_preset(name)` → "recommended", "all-haiku", "all-local"
- **Settings UI** at `/settings` — per-stage model dropdowns, presets, profile save/load, cost estimation
- LLM stages: reprints, card_gen, balance, skeleton_rev, ai_review, art_prompts, art_select
- Image stages: char_portraits, art_gen
- Profiles saved as TOML in `output/settings/<name>.toml`
- Add new models by editing `backend/mtgai/settings/models.toml`

## Validation Library (`mtgai/validation/`)
- Two severity levels: **AUTO** (deterministically fixable) and **MANUAL** (needs LLM retry)
- AUTO errors are auto-fixed post-validation via registered fixer functions (18 fixers)
- MANUAL errors become structured retry prompts fed back to the LLM
- `validate_card_from_raw(raw_dict)` -> `(card, errors, applied_fixes)` — the main entry point
- 8 validators run in sequence: schema -> mana -> type_check -> rules_text -> power_level -> color_pie -> text_overflow -> uniqueness
- Auto-fix registry in `__init__.py` maps `error_code` -> fixer function, with lazy loading
- Cards are immutable Pydantic models — fixers return new instances via `card.model_copy(update={...})`
- No spelling validator — LLMs don't misspell; keyword capitalization and "cannot"->"can't" live in rules_text
- **Reminder text is NOT validated** — it's injected programmatically after review (see below)
- `text_overflow` strips reminder text before measuring oracle length (reminder can be shrunk/dropped at render)
- `rules_text` Check 2 (self-reference) skips parenthesized text to avoid false positives from injected reminder text
- `rules_text` Check 10 (line_period) accepts `)` as valid line ending (for lines ending with reminder text)

## Reminder Text Injection (`mtgai/generation/reminder_injector.py`)
- LLMs do NOT generate reminder text — prompts explicitly say "do not include reminder text"
- Reminder text is injected programmatically from mechanic definitions (`approved.json`)
- **Use vs. Reference heuristic** (generic, no hardcoded keyword names):
  - `keyword_ability` (parameterized, e.g., Salvage X): keyword + number = USE → inject. Bare keyword = REFERENCE → skip.
  - `keyword_action` (non-parameterized, e.g., Overclock): keyword as clause action = USE → inject. Trigger/conditional context ("whenever you [keyword]") = REFERENCE → skip.
- Number-to-word substitution (3 → "three") and singular/plural handling
- `finalize_reminder_text(card, mechanics)` — strips old reminder text then injects fresh
- `strip_reminder_text(oracle)` — removes parenthesized text ≥20 chars
- `REMINDER_STRIP_RE` regex exported for use by other modules

## Post-Review Finalization (`mtgai/review/finalize.py`)
- Runs after AI review: inject reminder text → full validation → auto-fix → save
- Produces `output/sets/<SET_CODE>/reports/finalize-report.md` listing MANUAL errors for human review
- CLI: `python -m mtgai.review finalize [--set ASD] [--dry-run] [--card W-C-01]`

## AI Review Pipeline (`mtgai/review/ai_review.py`)
- Tiered council+iteration hybrid from Phase 1B A/B test
- **C/U cards**: Single Opus reviewer + iteration (max 5 loops)
- **R/M cards + planeswalkers/sagas**: Full council (3 independent Opus reviewers + consensus synthesizer, 2-of-3 filter) + iteration
- Pointed questions loaded from `output/sets/<SET_CODE>/mechanics/pointed-questions.json` (evolving config)
- Token optimizations: only include relevant mechanic defs, skip synthesis if all 3 say OK
- Per-card review logs saved as JSON in `output/sets/<SET_CODE>/reviews/`
- Summary report in `output/sets/<SET_CODE>/reports/ai-review-summary.md`
- Resumable: skips cards with existing review logs
- **Does NOT check reminder text** — reminder text is added programmatically after review
- CLI: `python -m mtgai.review ai-review [--dry-run] [--card W-C-01]`
- Also: `python -m mtgai.review.ai_review [--dry-run] [--card W-C-01]`

## Balance Analysis (`mtgai/analysis/`)
- `analyze_set(set_code)` runs skeleton conformance, CMC curve, creature size, removal density, card advantage, mechanic distribution, mana fixing, color balance, and **interaction analysis** checks
- **Interaction analysis** (`interactions.py`): LLM-based degenerate combo detection — feeds full card pool to Sonnet, flags infinite combos / degenerate synergies / unintended loops
  - Identifies the "enabler" card (root cause) for each flagged interaction
  - Returns `InteractionFlag` with `enabler_slot_id` and `replacement_constraint`
  - Feeds into skeleton reviser for automatic enabler replacement
- CLI: `python -m mtgai.review balance --set ASD`
- Reports saved to `output/sets/<SET_CODE>/reports/balance-{report,analysis}.{md,json}`

## Skeleton Revision (`mtgai/generation/skeleton_reviser.py`)
- LLM proposes slot changes based on balance findings (including interaction flags), then regenerates affected cards
- CLI: `python -m mtgai.generation.skeleton_reviser [--dry-run] [--max-rounds N]`

## Testing
- Validation tests are the most important category — 71+ tests in `tests/test_validation/test_validators.py`
- Reminder injector tests: 31 tests in `tests/test_reminder_injector.py`
- Finalization tests: 6 tests in `tests/test_finalize.py`
- Use `_make_card(**overrides)` helper for creating test cards with sane defaults
- Test file structure mirrors source structure

## Git
- Card JSON is version-controlled
- Art and rendered images are NOT version-controlled (gitignored)
- Never commit API keys or .env files

## Art Pipeline (`mtgai/art/`)
- **ComfyUI** installed at `C:\Programming\ComfyUI` with Flux.1-dev Q8_0 GGUF
- `prompt_builder.py` — Haiku generates 40-60 word Flux-optimized visual descriptions, assembles with style line
- `visual_reference.py` — JSON-driven visual reference loader, Flux term replacements for setting-specific names
- `image_generator.py` — batch generation via ComfyUI API
  - Auto-starts ComfyUI, VRAM pre-check (lists GPU-hungry apps if insufficient), resumable via progress.json
  - `kill_comfyui()` — always kills ComfyUI on exit (Ctrl+C/Break, completion, crash) to free VRAM
  - `flush_comfyui()` — calls `/free` + `/history` after each gen to prevent GPU memory accumulation
  - Settings: 30 steps, 1024×768, euler sampler, guidance 3.5, Q8_0 GGUF
  - ~40s/image, generates 3 versions per card for selection
  - **CRITICAL**: Must use `subprocess.DEVNULL` not `subprocess.PIPE` when starting ComfyUI (tqdm crashes on piped stderr on Windows)
- `art_selector.py` — Haiku vision picks best version per card ($0.006/card)
  - Evaluates: AI artifacts (hands!), prompt adherence, composition, color identity, style consistency
  - Generates HTML report with side-by-side comparison + reasoning
- `workflows/flux_dev_gguf.json` — ComfyUI API workflow (10 nodes)
- `scripts/generate_all_art.py` — standalone batch runner (run in own terminal, not via Claude Code — 10min timeout limit)
- Art files: `output/sets/<SET>/art/<collector>_<slug>_v<N>.png` (gitignored)
- CLI: `python -m mtgai.art.image_generator --set ASD [--card W-C-01] [--dry-run]`
- CLI: `python -m mtgai.art.art_selector --set ASD [--report-only]`

## Card Renderer (`mtgai/rendering/`)
- `card_renderer.py` — orchestrator: loads card + art + frame → composites → saves PNG
- `text_engine.py` — rich text: inline mana symbols, bold keywords, italic reminder text, dynamic font sizing, word wrapping
- `layout.py` — zone bounding boxes (name bar, art window, type bar, text box, P/T, collector)
- `symbol_renderer.py` — mana/set symbol rendering with cairosvg→Pillow fallback
- `fonts.py` — font loading/caching (Cinzel, EB Garamond, Montserrat)
- `colors.py` — MTG color schemes, rarity colors, frame key mapping
- Frame templates: M15 frames from Card Conjurer in `assets/frames/m15/` (2010×2814 RGBA PNGs with transparent art windows)
- Renders at native 2010×2814, scales to 822×1122 (300 DPI) for final output
- **SVG symbol rendering** via pycairo + svg.path (cairosvg/libcairo unavailable on Windows, but pycairo 1.29 bundles its own Cairo)
  - `_rasterize_svg_pycairo()` — parses SVG path `d` attr, draws with Cairo's antialiased path engine
  - `_make_pycairo_set_symbol()` — draws ASD descending vortex triangle directly with pycairo
  - Symbol code → SVG filename mapping in `SYMBOL_SVG_MAP` (T→tap.svg, Q→untap.svg)
- **Variable font weights** — Cinzel Bold (700) for card names, EB Garamond Bold for keywords, Montserrat Bold for P/T
- **Legendary crown** for legendary creatures only (not artifacts/enchantments)
  - Crown assets in `assets/frames/m15/crowns/` (per color identity, from Card Conjurer)
  - Multicolor legendaries always use Gold crown (matching gold frames)
  - `m15MaskTitle.png` used to punch out the title bar shape from the crown (so frame name bar shows through)
  - Black underlay composited behind the crown (above art window, excluding title bar) to prevent frame colors bleeding through
  - Compositing order: canvas → art → frame → black underlay → crown (with title cutout) → text
  - Learned from mtgrender (github.com/Senryoku/mtgrender): they shift background down + black base behind crown
- **Text box fitting** — unified iterative loop in `render_text_box()`:
  - Three content reduction levels: full (oracle+reminder+flavor) → no flavor → no flavor + no reminder
  - At each level: find best font size → shrink for PT overlap → check ≤8 lines
  - PT overlap detection: `_would_overlap_pt()` simulates full layout (with vertical centering) and checks actual line bounding boxes against PT box region
  - Escalates to next reduction level only if constraints can't be met
- **Collector bar** positioning adapts to card type:
  - Creatures: text centered in bar, artist credit right-aligned to PT box edge
  - Non-creatures: text hugs top of collector bar, near text box frame edge
- **Colored artifact frames** not yet implemented — see `learnings/colored-artifact-frames.md` for research and future plan
- CLI: `python -m mtgai.rendering --set ASD [--card W-C-01] [--force]`
- **Iteration 3 complete** — SVG mana/tap/set symbols, dynamic text sizing, shrink-to-fit name+type lines, bold fonts, P/T overlap fix

## Character Identity Pipeline
- `character_portraits.py` — generates reference portraits via Flux dev (text-to-image)
- Character picks stored in `output/sets/<SET>/art-direction/character-refs/picks.json`
- **PuLID-Flux** at weight=0.5 for face identity injection (humanoid characters only)
  - Custom onnxruntime shim at `ComfyUI/custom_nodes/ComfyUI-PuLID-Flux/insightface_compat.py` (insightface 0.7+ can't build on Windows)
  - PuLID `forward_orig` patched for newer ComfyUI (`timestep_zero_index` kwarg)
  - Uses Q5_K_S Flux to leave VRAM headroom for PuLID models, fits in 12GB
- **Kontext Dev rejected** — copies style+composition, not just identity. No strength dial.
- Known MTG characters (Jace etc.) → use official Scryfall art as reference, not Flux

## Unified Pipeline (`mtgai/pipeline/`)
- **End-to-end orchestrator**: 17 stages from skeleton generation through final review
- `python -m mtgai.review serve --open` starts the server with pipeline dashboard
- **Dashboard** at `/pipeline` — vertical stage stepper with real-time SSE progress
- **Configuration** at `/pipeline/configure` — set identity + per-stage review toggles (Auto/Review/Skip)
- **Three presets**: Full Auto, Review Everything, Recommended (balance + AI review + art selection)
- **Human checkpoints**: Card Review, Art Review, Final Review always pause for human input
- **SSE real-time updates** via `/api/pipeline/events` — stage_update, item_progress, cost_update events
- **Pipeline state**: persisted to `output/sets/<SET>/pipeline-state.json` for crash recovery
- **Key files**:
  - `pipeline/models.py` — PipelineState, StageState, PipelineConfig (Pydantic)
  - `pipeline/engine.py` — PipelineEngine: run/resume/cancel/retry/skip
  - `pipeline/events.py` — Thread-safe EventBus for SSE
  - `pipeline/server.py` — FastAPI routes (page + API)
  - `pipeline/stages.py` — Stage registry mapping stage_id → library function
- **Model Settings** at `/settings` — per-stage LLM/image model selection, presets, profile save/load
- **Status banner** in `base.html` shows pipeline status across all pages
- `card_generator.generate_set()` now accepts `set_code` and `progress_callback` params
- `generation/land_generator.py` — extracted from `scripts/generate_lands.py` as callable function

## Current State (Phase 4C Complete, Pipeline built, Phase SC next)
- 66 cards generated for ASD dev set (60 main + 6 lands)
- 3 custom mechanics: Salvage (W/U/G), Malfunction (W/U/R), Overclock (U/R/B)
- Phases 0A-0E, 1A-1C, 4A, 4A-rev, 4B, 2A, 2B, 2C, 3A, 3B, 4C complete
- Unified pipeline dashboard built (Phases A-C of pipeline plan)
- Phase 3: HTML review workflow with FastAPI server
  - `python -m mtgai.review serve --open` starts local review server
  - Review gallery: card grid with filters, per-card OK/Remake/Art Redo/Manual Tweak decisions
  - Card detail modal with keyboard nav, mana cost rendering
  - Progress page with auto-refresh polling
  - Booster pack viewer with color-balanced collation (mimics real MTG draft boosters)
  - Manual tweak opens card JSONs in system editor on submit
  - Server discovers render/art images from disk (no card JSON path dependency)
  - Plan: `plans/phase-3-review-workflow.md`
- Next: Phase SC (scale-up to ~280 cards) via unified pipeline
