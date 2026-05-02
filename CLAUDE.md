# MTGAI Project Conventions

## Local LLM Notes (Gemma 4, 12GB VRAM)
- **Gemma 4 26B-A4B** (MoE) is viable on 12GB VRAM with partial CPU offloading. Benchmarks show ~44 tok/s at 128k context with `--flash-attn` and Q4/Q5 quantization. MoE offloading penalty is much lower than dense models because inactive experts sitting on CPU don't incur PCIe transfer costs per token.
- **Gemma 4 E4B** fits entirely in 12GB at Q8_0 (~4.87 GB base, ~7 GB left for KV cache). Simpler, more consistent latency, zero offloading risk.
- Context vs VRAM: KV cache grows linearly. Formula: `VRAM = (P x b_w) + (0.55 + 0.08 x P) + KV_cache`. At Q4_K_M, b_w = 0.57 bytes/weight. See https://localllm.in/blog/interactive-vram-calculator for details.
- **VladimirGav/gemma4-26b-16GB-VRAM (IQ4_XS)** wins at 128K context on 12GB VRAM. IQ4_XS is llama.cpp's importance-aware 4-bit quant — smaller and smarter than standard q4_K_M. Smaller weights leave more VRAM for KV cache, dramatically reducing CPU offloading at large context. At 128K context with 58K input tokens, it finished theme extraction in ~15 min while standard `gemma4:26b` took 2.5+ hours (standard q4_K_M forces 55% CPU offload at 128K, crushing prompt processing).
- **HLWQ (Hadamard-Lloyd Weight Quantization)** is the successor to PolarQuant from the same author (caiovicentino1). PolarQuant track appears abandoned — the original 31B model was removed from HF. Current HLWQ models (`Gemma-4-26B-A4B-it-HLWQ-Q5`, `Gemopus-4-26B-A4B-it-HLWQ-Q5`) are SafeTensors only, no GGUF. Watch for community conversions. See TC-1d.
- **Flash attention** is auto-enabled on Ollama 0.20.5+ for an architecture allowlist that includes `gemma3`, `gemma4`, `qwen3*`, `gptoss`, `mistral3`, etc. (see [PR #15378](https://github.com/ollama/ollama/pull/15378), merged April 7 2026). For our default `vlad-gemma4-26b-dynamic` it's on automatically — no env var needed. The official Ollama FAQ at docs.ollama.com/faq still says FA is opt-in for everything; it's stale — believe the source (`fs/ggml/ggml.go`). For non-allowlisted models (e.g. `llama3`, `gemma2`, `grok`) you still need `OLLAMA_FLASH_ATTENTION=1`.
- **`OLLAMA_KV_CACHE_TYPE=q8_0`** is set persistently at User scope on this machine — q8_0 is broadly safe (~99% of f16 quality across architectures, including non-sliding-window models like Llama 3 and Mistral) and the convention community-wide for "safe KV quant". On Vlad-dynamic at 128K context, q8_0 trims the KV cache from 3.4 GB (f16) to 1.7 GB, which lets more weight layers stay on GPU and recovers most (~70%) of the q4_0 speedup without the per-architecture risk q4_0 carries. The env var is global (read once at server startup; no per-call or per-model override — see [PR #7983](https://github.com/ollama/ollama/pull/7983), rejected as too hacky), so it inherits to every Ollama process the tray autostarts, including non-MTGAI projects. q8_0's broad safety is what makes that fine.
- **Modelfile cannot set `kv_cache_type`.** Per `ollama show vlad-gemma4-26b-dynamic --modelfile`, the only PARAMETER directives we set are `num_gpu -1`, the standard sampling params, and stop tokens. KV cache type is server-wide and only configurable via the env var.
- **`start-ollama.ps1`** (repo root) is a "boost mode" launcher: stops any running Ollama processes and restarts `ollama serve` with `OLLAMA_KV_CACHE_TYPE=q4_0` in process scope, overriding the system-wide q8_0 default. Use it when you want maximum speed for an MTGAI extraction (saves ~30-50 s per 58K-token run vs q8_0). It prompts for confirmation before killing existing Ollama processes — important because killing mid-request will lose the in-flight work. After the boost-mode `serve` exits or restarts, the tray Ollama will autostart with q8_0 again. **Boost-mode logs go to `output/ollama-boost.log`** (stderr; stdout to `output/ollama-boost.stdout.log`) — the tray-managed `C:\Users\coami\AppData\Local\Ollama\server.log` goes silent the moment the launcher kills the tray's serve process, so the boost log is the only forensic record while boost mode is active. Overwrites on each launch; copy aside if you need to keep a session for analysis.
- **Slow-split symptoms** (running Vlad-dynamic at 128K against an Ollama process that didn't pick up `OLLAMA_KV_CACHE_TYPE`): `ollama ps` shows ~49%/51% CPU/GPU split, GPU sits at ~30W instead of 60-90W during inference, wall clock balloons from ~4 min to ~6 min for a 58K-token extraction. Most likely cause is a serve process that pre-dates the env var being set. Fix: `Stop-Process -Name 'ollama*' -Force` then let the tray restart Ollama (or run the launcher).
- **Current 26B-tier winner** (12 GB VRAM, long context, per TC-1f): `vlad-gemma4-26b-dynamic` + flash attention + KV cache quantization. TC-1f measured **q4_0** at 238.7 s for 58K-token extraction; **q8_0 is not separately benchmarked** but interpolates to roughly 270-290 s based on the placement-math (q8_0's 1.7 GB KV vs q4_0's 0.8 GB shifts ~half as many layers GPU-side). Either way, well under the 345 s f16 baseline. The `-dynamic` suffix is our override Modelfile (`PARAMETER num_gpu -1`) on top of `VladimirGav/gemma4-26b-16GB-VRAM`. NEVER use the upstream Vlad model with q4_0 KV cache on <16 GB VRAM; its hardcoded `num_gpu 99` causes CUDA OOM + display driver crash. q8_0 doesn't free enough VRAM to trigger the same trap, so the global default is safe even for upstream Vlad — but we don't use upstream Vlad anyway.
- **Default everywhere**: `vlad-gemma4-26b-dynamic` is now the default for all local LLM stages (theme extraction, mechanic gen, etc.). Originally we ran Unsloth on mechanic gen to test whether Vlad's more aggressive IQ4_XS quant was causing output repetition; turns out Gemma's repetition tendency is intrinsic (see `learnings/gemma-repetition-loops.md`) and we used to claim it was mitigated by `repeat_penalty=1.1` in the Ollama provider config — but per **[Ollama #15783](https://github.com/ollama/ollama/issues/15783)**, the `ollamarunner` Go-native sampler used by Gemma 4 (and other modern models) **silently ignores** `repeat_penalty`, `frequency_penalty`, and `presence_penalty`. Only `temperature`/`top_k`/`top_p`/`min_p` actually take effect on this code path. PR #15784 has the fix but is unmerged as of May 2026. So in practice today: Gemma's repetition is NOT being penalised at the sampler at all; what's actually mitigating it for us is the mid-stream tandem-repeat detector (`_detect_tandem_repeat` in theme_extractor.py), and on retries we now also escalate `temperature` (0.7 → 0.85 → 1.0) since that knob actually moves the model. We still pass `repeat_penalty=1.1` (and 1.15/1.20 escalation on retries) for forward-compat — the moment #15784 lands those start working. Single model = no Ollama swap latency between stages and full `keep_alive` payoff. Vlad's placement-math edge is neutral at <32K context, so nothing to lose.
- q4_0 KV cache only helps on models in the placement sweet spot (where a smaller KV cache shifts layers from CPU to GPU). On 12 GB VRAM, that's ~14 GB-weight models like Vlad's IQ4_XS. Larger models like Unsloth UD-Q4_K_XL (17.1 GB) barely benefit (~1%). Smaller models (<4 B) see no benefit and may lose accuracy from quantized KV representations.
- **Unsloth UD-Q4_K_XL GGUF** (`unsloth/gemma-4-26B-A4B-it-GGUF`, 17.1 GB) is 19% faster than upstream Vlad (`num_gpu=99`) at 128K context (TC-1f, 697.9 s vs 865.3 s wall clock — but both are far slower than `vlad-gemma4-26b-dynamic`'s 238 s with q4_0 KV + flash attn). Registered as `unsloth-gemma4-26b-q4kxl`. Slightly more verbose output than Vlad-dynamic (12,348 vs 11,129 chars) but Vlad-dynamic keeps all 7 sections intact. Kept in registry as documented backup if Vlad ever drops from HF.

## Toolchain Buildout (in progress)
Making MTGAI a reusable tool for any set, not just ASD. Say "continue toolchain buildout" to resume.

**Done:** Model settings system (/settings), theme wizard (/pipeline/theme), per-stage LLM routing, set-config.json eliminated, theme extraction upgrade (PDF/text extraction, streaming LLM output, token counting, chunking, constraints + card suggestion extraction with AI-generated badges), theme extraction hardening (single-extraction lock + cancel button, per-section compaction guard, pre/post overflow + truncation checks, Anthropic prompt caching, summary footer + Ollama metadata in extraction logs, SSE retry visibility - see "Theme Extraction" section).

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
- Everything under `output/` is gitignored. Pre-existing tracked files (e.g. ASD's `cards/`, `mechanics/`, `reports/`) remain tracked because git won't auto-untrack them, but anything new in `output/` won't be picked up by git. If you need a generated artifact in version control, put it somewhere else.

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

## Theme Extraction (`mtgai/pipeline/theme_extractor.py`)
- Front door for the theme wizard at `/pipeline/theme`. Reads PDF/text upload, runs a multi-stage LLM extraction, then a JSON pass for constraints + card suggestions.
- **Single extraction at a time**: reentrant `_run_lock` + `_cancel_event` enforce one run per process. `request_cancel()` aborts mid-stream from any thread; SSE handler also calls it on browser disconnect. UI exposes a "Cancel Extraction" button.
- **Endpoints**: `POST /api/pipeline/theme/upload`, `/analyze`, `/cancel`. `GET /extract-stream` (SSE) returns 409 if a run is already active. `GET /status` reports `running` + active log path.
- **Two extraction paths** based on token count vs. context window:
  - **Single-pass** (fits in one call): one LLM call with the full document.
  - **Per-section multi-chunk** (large docs): 7 sections × N chunks. Each section is built incrementally - first chunk seeds it, each subsequent chunk passes back the accumulated section for extension.
- **Compaction guard**: per-section accumulated text is bounded at 40% of chunk budget. When it exceeds, runs a compaction LLM call (with hard-truncate fallback) before the next chunk. Prevents quadratic context growth on long documents; trade-off is controlled information loss.
- **Pre/post overflow checks** (Ollama only, via `mtgai.generation.token_utils`): `count_messages_tokens` checks input fits before sending; `check_post_call` raises `InputTruncatedError` / `OutputTruncatedError` from `done` metadata.
- **Anthropic prompt caching**: system prompt marked `cache_control: ephemeral` so the per-section calls within ~5 min reuse the cached prefix (90% input discount).
- **Ollama hygiene**: native `/api/chat`, `keep_alive=15m`, stop sequences for source-text divider markers, captured `prompt_eval_count` / `eval_count` / duration metadata, error-body capture before raising.
- **Repetition loop detection**: `_detect_tandem_repeat` (suffix periodicity scan) runs every 64 chars of new content; aborts mid-stream so a runaway loop can't fill `num_predict`. Period-length-aware thresholds (e.g. period 2-4 chars: 8 reps; period 11-25 chars: 4 reps; period 61-120 chars: 2 reps). The period window must contain at least one alphanumeric character — suppresses ASCII-art / markdown-separator false positives like `"-"*N`, `"|---|---|"`, `"_"*N`. Catches the user-reported `"the-the-the-..."` failure mode that the old whitespace-split token detector missed (hyphen-glued tokens look like one token to `split()`).
- **Extraction log** (`output/extraction_logs/extraction_<ts>.md`, gitignored): one file per run with system + user prompts, streamed response, per-call Ollama metadata, retry markers, and a summary footer (wall time, total calls, tokens, retries, sections-with-content, cancel/abort reason). `tail -f` mirrors live LLM output.
- **SSE retry visibility**: every JSON-subcall retry yields a `status` event with attempt number + previous failure reason - keeps the progress bar moving on slow local models.
- **Upload cache TTL**: 30 min. Stale entries evicted on every upload.
- **Image / vision support removed** - was bloating logs with base64 and only the single-pass path ever used images.
- **Split JSON subcall output caps**: `_JSON_SUBCALL_CONSTRAINTS_MAX_TOKENS = 4096` (constraints output is short), `_JSON_SUBCALL_SUGGESTIONS_MAX_TOKENS = 8192` (card suggestions need more room for descriptions). Per-call override threads through `_stream_single_call` → `_stream_ollama_call` via `output_budget_override`. Defense against runaway generation filling context is now primarily the mid-stream repetition detector; the cap is secondary.
- **Partial text preserved on errors**: TRUNCATION, repetition ABORT, missing-done, and stream exceptions now include `partial_text` in the yielded error event. `_attempt_json_subcall` captures it as `raw`, so the UI aggregated error panel shows every attempt's streamed output - not just ones that completed cleanly. Previously all content was lost on error.
- **Content extraction from `done` frame**: Ollama's streaming loop now reads `message.content` from every frame including the final `done` frame, not just intermediate frames. Guards against format=json buffering behavior observed on some failed runs (where `eval_count: 4096` with a completely empty `### Response` section in the log).
- **Frame-count diagnostics** in per-call metadata: `frames_total`, `frames_with_content`, `theme_text_chars`. Successful runs show `frames_with_content` ≈ `eval_count` (genuine streaming). If a future failed run shows `frames_with_content: 0` with `eval_count > 0`, that's smoking-gun evidence of buffering. Curious unexplained detail: successful runs emit ~12-16 empty frames per content frame (possibly format=json grammar-validation heartbeats); benign but uncharacterized.
- **TODO (active): reproduce degenerate output with diagnostics**. Run the constraints + card_suggestions flow multiple times to try to trigger `done_reason=length` at 4096 + empty Response section again. The new frame-count fields will answer the open question: if `frames_with_content: 0`, Ollama was buffering in the done frame (the defensive fix already handles this). If `frames_with_content` is nonzero, the original empty-log behavior was caused by something else (iter_lines delimiter quirk, log handle state, etc.) and needs further investigation. Also: the ~12-16 empty frames per content frame ratio is unexplained; worth comparing across models (Anthropic vs Ollama, different Ollama models) to see if it's a format=json artifact or a general pattern.

## LLM Client (`mtgai/generation/llm_client.py`)
- **All transport goes through [llmfacade](https://pypi.org/project/llmfacade/)** — a unified Provider/Model/Conversation API over Anthropic and Ollama. MTGAI no longer talks to either provider's HTTP layer directly. Both `llm_client.py` (card/mechanic generation) and `theme_extractor.py` (streaming theme extraction) build llmfacade `Conversation` objects via `_get_provider("anthropic" | "ollama")` and call `convo.send(...)` or `convo.stream(...)`. `art_selector.py` does the same for vision calls (Anthropic image blocks via `ImageBlock.from_path`).
- `generate_with_tool()` — unified entry point, provider selected by `MTGAI_PROVIDER` env var (Anthropic by default).
- **Tool schemas**: callers still pass MTGAI/Anthropic-shaped tool schema dicts (`name`, `description`, `input_schema`). `_make_tool()` wraps them as `llmfacade.Tool` objects with a no-op callable; we read structured args from `Response.tool_calls[0].input` directly and never invoke the tool fn. `tool_choice=tool_schema["name"]` forces the model to emit a tool call.
- **Provider config** (env vars):
  - `MTGAI_PROVIDER=ollama` — switch to local model (default `anthropic`)
  - `MTGAI_OLLAMA_MODEL=qwen2.5:14b` — model name
  - `MTGAI_OLLAMA_URL=http://localhost:11434` — Ollama API endpoint
- **Anthropic provider settings** (set on the cached llmfacade Provider):
  - `exact_count_tokens=True` — hits Anthropic's free server-side `count_tokens` endpoint when `theme_extractor` asks for an exact pre-call estimate.
  - `auto_cache_tools=True` — reproduces the pre-migration `cache_control: ephemeral` on the tool schema so sequential calls within ~5 min reuse the cached prefix (90% discount). Per-call `cache=False` honours the contract by overriding to `auto_cache_tools=False` on that conversation.
  - System prompt caching: pass `SystemBlock(text=..., cache=True)` to mark for ephemeral caching.
- **Ollama provider settings**:
  - `keep_alive="15m"` — keeps the model loaded between calls.
  - `repeat_penalty=1.1` — Gemma-loop mitigation (see `learnings/gemma-repetition-loops.md`).
  - llmfacade uses Ollama's native `/api/chat` under the hood, so `num_ctx` is respected. We look the context window up from the model registry per-call and pass it via `convo.send(num_ctx=...)`.
- **Local models available**: Qwen 2.5 (7B/14B), Qwen3-VL 8B (vision), Gemma 4 E4B (fast, vision), Gemma 4 26B MoE (quality, vision, 128K context). Gemma 4 supports native tool calling and vision across all sizes. `all-local` preset uses Gemma 4 26B MoE for all stages.
- **Ollama tool extraction**: native function calling first via llmfacade's `resp.tool_calls`, falls back to JSON extraction from raw text (fenced blocks, Qwen-style, bare JSON) when the model emits args inline as text. Retries up to `MTGAI_MAX_RETRIES` (default 3) on garbage output.
- **Token counting** (`token_utils.py`): tiktoken cl100k_base for approximate counts on the Ollama path. Pre-call overflow check raises `ContextOverflowError`. Post-call `check_post_call_response(resp)` raises `InputTruncatedError` / `OutputTruncatedError` from llmfacade's `Response.usage` + `finish_reason="length"`.
- **Ollama debug** (`ollama_debug.py`): log scanner for Ollama's `server.log`. Set `MTGAI_DEBUG=1` to enable post-call log scanning and startup debug mode verification. CLI: `python -m mtgai.generation.ollama_debug [--since=N]`. Scans for truncation, OOM, CUDA errors, and generic warn/error lines.
- **Pricing**: centralized `PRICING`, `calc_cost()`, and `cost_from_result()` — all callers import from here.
  - `calc_cost()` accounts for cache pricing: 1.25x for cache creation, 0.1x for cache reads (read from llmfacade's `usage.cache_creation_input_tokens` / `cache_read_input_tokens`).
  - `cost_from_result(result)` convenience wrapper unpacks a `generate_with_tool` result dict.
  - Returns 0.0 for local/unknown models.
- **Effort + capping**: `effort` parameter (Opus-only: "max", "high", "low") forwarded as `convo.send(effort=...)`. `MTGAI_MAX_MODEL` env var caps the tier (haiku/sonnet/opus); higher-tier requests are downgraded and `effort` is dropped if below Opus.
- `thinking` is incompatible with forced `tool_choice` — don't use together.
- Always use full color names in prompts (not abbreviations like "R").
- **Provider routing**: `_resolve_provider(model_id)` checks model registry first, falls back to `MTGAI_PROVIDER` env var.
- **Frame diagnostics for theme extraction**: per-call `<NNN>-<slug>.meta.json` sidecars are written alongside llmfacade's JSONL log on every termination path (complete, stream_exception, repetition_abort, no_usage_frame, truncated, cancelled). Records `frames_total`, `frames_with_content`, `theme_text_chars`, prompt/completion tokens, finish_reason, outcome. See `_write_call_meta()` in `theme_extractor.py`.

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
- Full ignore patterns in `.gitignore` at repo root; see "Project Structure" for the tracked-vs-ignored breakdown under `output/`

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
