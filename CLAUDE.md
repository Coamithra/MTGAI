# MTGAI Project Conventions

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
- `generate_with_tool()` — Anthropic API with forced `tool_choice` for structured JSON output
- Supports `effort` parameter (Opus-only): "max", "high", "low"
- Model tier capping via `MTGAI_MAX_MODEL` env var (set to "haiku", "sonnet", or "opus")
  - Higher-tier requests are downgraded to the cap model
  - `effort` is removed if dropping below Opus
- `thinking` is incompatible with forced `tool_choice` — don't use together
- Always use full color names in prompts (not abbreviations like "R")

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
- `analyze_set(set_code)` runs skeleton conformance, CMC curve, creature size, removal density, card advantage, mechanic distribution, mana fixing, and color balance checks
- CLI: `python -m mtgai.review balance --set ASD`
- Reports saved to `output/sets/<SET_CODE>/reports/balance-{report,analysis}.{md,json}`

## Skeleton Revision (`mtgai/generation/skeleton_reviser.py`)
- LLM proposes slot changes based on balance findings, then regenerates affected cards
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

## Current State (Phase 2A In Progress)
- 66 cards generated for ASD dev set (60 main + 6 lands)
- 3 custom mechanics: Salvage (W/U/G), Malfunction (W/U/R), Overclock (U/R/B)
- Phases 0A-0E, 1A-1C, 4A, 4A-rev, 4B complete (review-infra, review-run, finalize)
- AI review: 59 cards reviewed (Haiku, $0.58), 6 changed, 58 OK / 1 REVISE
- Post-review finalization done: reminder injection + 5 auto-fixes + 2 validator bugs fixed
- Review gallery: `output/sets/ASD/reports/card-review-gallery.html`
- Phase 2A art direction: style guide + prompts + personas done, ComfyUI pipeline built
- Art generation: 198 images complete (66 cards × 3 versions), art selection done ($0.37)
- Art quality: sufficient for dev set, not production — anatomy issues, too realistic, violence scenes fail. See `learnings/phase2a-art-quality.md`
- Next: character reference portraits → sample arts with character consistency → go/no-go gate
