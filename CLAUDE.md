# MTGAI Project Conventions

## Trello Board
- **Board**: [MTGAI](https://trello.com/b/Am3RvaZM) — id `69f86a83`
- **Lists**: `To Do` → `Doing` → `Done`
- **Labels**: `bug` (red), `feature` (green), `refactor` (blue), `design` (purple), `infra` (orange), `docs` (yellow)
- **CLI**: `trello --board 69f86a83 <command>` (e.g. `card move`, `comment add`, `card add`). The `trello` binary is on PATH; see global `~/.claude/CLAUDE.md` for the cheat sheet.
- **Picking up a card?** Read `CONTRIBUTING.md` first — it's the runbook for the full workflow (tracker doc → worktree → research → design → implement → verify → review → ship → move card → comment). Do not skip the tracker doc step at the top.

## Local LLM Notes (Gemma 4, 12GB VRAM)
- **Backend**: local models run through **llmfacade's `llamacpp` provider in managed mode**. llmfacade lazy-spawns a `llama-swap` subprocess on first call and supervises one `llama-server` instance per registered model. Replaced Ollama in May 2026 — see "llama.cpp migration" below for the why. Binaries live at `C:\Tools\llama.cpp\` (both `llama-server.exe` and `llama-swap.exe` are on PATH). GGUFs live at `C:\Models\`. Per-model launch knobs (gguf path, context_size, KV-cache quant, GPU offload) are declared in `backend/mtgai/settings/models.toml` and threaded into `provider.new_model(...)` by `_llamacpp_new_model()` in `llm_client.py`.
- **Gemma 4 26B-A4B** (MoE) is viable on 12GB VRAM with partial CPU offloading. Benchmarks show ~44 tok/s at 128k context with flash attention and Q4/Q5 quantization. MoE offloading penalty is much lower than dense models because inactive experts sitting on CPU don't incur PCIe transfer costs per token.
- **Gemma 4 E4B** fits entirely in 12GB at Q8_0 (~4.87 GB base, ~7 GB left for KV cache). Simpler, more consistent latency, zero offloading risk.
- Context vs VRAM: KV cache grows linearly. Formula: `VRAM = (P x b_w) + (0.55 + 0.08 x P) + KV_cache`. At Q4_K_M, b_w = 0.57 bytes/weight. See https://localllm.in/blog/interactive-vram-calculator for details.
- **VladimirGav/gemma4-26b-16GB-VRAM (IQ4_XS)** wins at 128K context on 12GB VRAM. IQ4_XS is llama.cpp's importance-aware 4-bit quant — smaller and smarter than standard q4_K_M. Smaller weights leave more VRAM for KV cache, dramatically reducing CPU offloading at large context. At 128K context with 58K input tokens, it finished theme extraction in ~15 min on Ollama vs 2.5+ hours for standard `gemma4:26b` (standard q4_K_M forces 55% CPU offload at 128K, crushing prompt processing).
- **Flash attention is ON for q8_0 / q4_0 KV cache configs (forced by llama-server)**, OFF (auto-disabled) for f16 KV. Verified empirically TC-2 (2026-05-03): forcing `--flash-attn off` with q8_0 V cache crashes llama-server with `"V cache quantization requires flash_attn"` — they're hard-coupled. So our production Vlad q8_0 numbers (105.5s wall, 42.1s TTFT) and q4_0 (95.4s, 38.0s) are flash-on numbers, no additional upside available there. The TC-2 f16 row (711.6s wall, 408.3s TTFT) is the *only* one likely missing flash — for any future f16 KV use case on Gemma 4 (e.g. small models that don't quantize KV), explicitly pass `--flash-attn on`. Phase C's `llama-bench` JSON showed `"flash_attn": false` because llama-bench's defaults differ from llama-server's — ignore that signal. llama-server's flag is `-fa, --flash-attn [on|off|auto]`, default `auto`. **TODO**: once llmfacade exposes `flash_attn` as a launch knob (see `C:\Programming\LLMFacade\plans\llmfacade-feature-request-flash-attn.md`), set it explicitly to `on` on every llamacpp registry entry to remove ambiguity from the auto path. → [Trello](https://trello.com/c/8zfB8zO6)
- **Per-model KV-cache quantization** happens at server launch via `--cache-type-k` / `--cache-type-v` flags, which llmfacade passes through automatically when `cache_type_k` / `cache_type_v` are set on the model entry in `models.toml`. No global env var; per-server, per-model.
- **Default 26B config**: `gemma4-26b-vram-dynamic` in `models.toml` is the long-context winner (per TC-1f, re-baselined in TC-2) — Vlad IQ4_XS GGUF + `cache_type_k = "q8_0"` + `cache_type_v = "q8_0"` + `n_gpu_layers = -1`. q8_0 KV trims cache from ~3.4 GB (f16) to ~1.7 GB at 128K, freeing layers for GPU placement. Per-model declaration replaces Ollama's global `OLLAMA_KV_CACHE_TYPE` env var.
- **`n_gpu_layers = -1` is a footgun, not "auto"**. In Ollama, `num_gpu = -1` meant "use the placement estimator". In llama.cpp, `--n-gpu-layers -1` means literally **all layers on GPU**. The current production config survives only because Vlad IQ4_XS (14 GB) + q8_0 KV cache (1.7 GB) just barely fits at 89% VRAM. f16 KV with `-1` OOMs mid-extraction (TC-2 confirmed). Auto-placement in llmfacade is a real TODO — see `learnings/llamacpp-tc2-benchmark.md` for the two viable implementations. Until that lands, treat `n_gpu_layers = -1` as "manually verified to fit" not "auto-fit". → [Trello: auto-placement](https://trello.com/c/dybBBMjM), [Trello: registry-load warning sibling](https://trello.com/c/hSJPnWzA)
- **Repetition-loop mitigation now actually works.** On Ollama, `repeat_penalty` was silently dropped by the `ollamarunner` Go sampler on Gemma 4 and friends ([ollama#15783](https://github.com/ollama/ollama/issues/15783), unmerged PR #15784). On llama.cpp it's honoured everywhere. We pass `repeat_penalty=1.1` provider-wide via llmfacade. On JSON-subcall retries (the constraints + card-suggestions extraction passes — both Gemma's worst loop offenders), `theme_extractor._run_json_subcall` escalates per attempt: `_RETRY_REPEAT_PENALTIES = [None, 1.15, 1.20]`. The override threads through `_attempt_json_subcall → _stream_single_call → _stream_llamacpp_call` and rides llmfacade's `extra_body` onto the wire. Temperature is intentionally not escalated — higher temperatures produced malformed JSON on smaller models, and repeat_penalty alone breaks loops in practice. The mid-stream tandem-repeat detector (`_detect_tandem_repeat`) is still the primary runaway guard — it catches loops within 64 chars, well before the sampler-level penalty would have taken effect.
- q4_0 KV cache only helps on models in the placement sweet spot (where a smaller KV cache shifts layers from CPU to GPU). On 12 GB VRAM, that's ~14 GB-weight models like Vlad's IQ4_XS. Larger models like Unsloth UD-Q4_K_XL (17.1 GB) barely benefit (~1%). Smaller models (<4 B) see no benefit and may lose accuracy from quantized KV representations.

## llama.cpp migration (May 2026)
- **What changed.** Dropped the Ollama provider entirely from llmfacade and switched MTGAI to its new `llamacpp` provider in managed mode. Local models now go through `llama-swap → llama-server → /v1/chat/completions` (OpenAI-compatible). llama.cpp-specific samplers (`top_k`, `min_p`, `repeat_penalty`) ride the SDK's `extra_body=` kwarg and are forwarded verbatim onto the wire.
- **Why.** Five Ollama pain points fixed in one go: (1) `repeat_penalty` works on Gemma-class models again, (2) per-server / per-model KV-cache quant via `--cache-type-k` instead of a global env var, (3) `/health` and `/slots` introspection (llmfacade exposes `provider.slots()`, `provider.running()`, etc.), (4) `/slots/{id}?action=save|restore|erase` for KV-cache disk persistence (`provider.save_slot()` etc. — not yet wired into MTGAI but available), (5) `--ctx-size` actually honoured on the chat-completions endpoint (Ollama silently capped it on `/v1/chat/completions`).
- **Files retired.** `start-ollama.ps1` (boost-mode launcher; per-server KV quant replaces it). `backend/mtgai/generation/ollama_debug.py` (Ollama server.log scanner; managed-mode logs to `<llmfacade_dir>/logs/llamacpp-swap.log` if you need them). `ollama` Python SDK dropped from `pyproject.toml`. `tests/test_llm_client_ollama.py` renamed to `test_llm_client_llamacpp.py` and updated.
- **Files updated.** `models.toml` gained `gguf_path`, `cache_type_k`, `cache_type_v`, `n_gpu_layers` columns. `LLMModel` (model_registry.py) mirrors them. `_get_provider("llamacpp")` in `llm_client.py` is managed-mode (no `base_url`); `_llamacpp_new_model(provider, model_id)` looks up the registry entry and threads launch knobs into `provider.new_model(name=..., gguf=..., context_size=..., cache_type_k=..., n_gpu_layers=...)`. `_stream_ollama_call` → `_stream_llamacpp_call` in `theme_extractor.py`. `token_utils.py` error messages are provider-neutral.
- **Lifecycle.** llama-swap subprocess + its YAML live under `<repo>/.llmfacade/`. First `convo.send()` in any process spawns it; OS-level kill-on-parent-death (Win32 Job Object on Windows) tears it down with the parent. PID-file sweep on next start reaps any orphan that survived a hard kill. No tray icon to manage; nothing to autostart at boot.
- **Adding a model.** Drop a `.gguf` into `C:\Models\`, add a section to `backend/mtgai/settings/models.toml` with `provider = "llamacpp"`, `model_id` (the llama-swap YAML key — also what gets sent in OpenAI `model:`), `gguf_path`, `context_window`. Optionally `cache_type_k` / `cache_type_v` for KV-cache quant and `n_gpu_layers` (`-1` to offload all — but see footgun warning above). The supervisor lazy-loads it on first reference. **TOML keys can't contain `.`** — use `qwen36-35b-a3b`, not `qwen3.6-35b-a3b`, or quote the section header.
- **Stock Google Gemma 4 GGUFs from Ollama do NOT load in llama.cpp.** The architecture metadata expects multimodal tensors (vision + audio) but the blobs ship text-only. Loader rejects with `"wrong number of tensors; expected 2131, got 720"`. Only Unsloth's text-only repacks (and VladimirGav's, which we already use) work. Don't waste time hard-linking `gemma4:26b`, `gemma4:e4b`, or `gemma4:31b` from `~/.ollama/models/blobs/` — see TC-2 writeup. Unsloth's `gemma-4-26B-A4B-it-GGUF` is the right HF source for stock-Google Gemma 4 26B.
- **TC-2 numbers (post-migration, May 2026 re-baseline).** Vlad q8_0 / 128K / 58K input: **105.5s** (vs Ollama TC-1f estimate ~280s, **2.6× faster**). Vlad q4_0: **95.4s** (vs Ollama TC-1f winner 239s, **2.5× faster**). TTFT 38–42s on llama.cpp vs 51s on Ollama. q4_0 vs q8_0 gap narrowed from ~30% (Ollama) to ~10% (llama.cpp). Full results: `learnings/llamacpp-tc2-benchmark.md`.
- **TC-2 surprise contender — Unsloth Gemma 4 E4B.** Q4_K_M (~5 GB) at q8_0 / 128K all-GPU on the same Dark Sun corpus: **107.9s wall**, **TTFT 28.7s (32% faster than Vlad)**, **18,268 output chars (60% more)**, **47% VRAM (vs Vlad's 89%)**. Output quality is production-grade (all 7 sections, well-structured). Real candidate to dethrone Vlad as theme-extraction default — pending side-by-side quality comparison on more corpora than just Dark Sun. Registry entry: `gemma4-e4b-unsloth`.
- **Local vision is an llmfacade gap.** Anthropic models accept `ImageBlock.from_path(...)` for vision calls (used by `art_selector.py`); llmfacade's managed-mode llamacpp provider doesn't yet accept an `mmproj_path` on `provider.new_model(...)` or marshal vision content blocks into the OpenAI `image_url` shape llama-server consumes. Until that lands, `supports_vision = false` on every llamacpp registry entry, including Gemma 4 26B (which has a multimodal projector available). Don't flip the flag without plumbing `mmproj_path` through `_llamacpp_new_model`. → [Trello](https://trello.com/c/kRrLt2GM)

## Toolchain Buildout (in progress)
Making MTGAI a reusable tool for any set, not just ASD. Say "continue toolchain buildout" to resume.

**Done:** Model settings system (/settings), theme wizard (/pipeline/theme), per-stage LLM routing, set-config.json eliminated, theme extraction upgrade (PDF/text extraction, streaming LLM output, token counting, chunking, constraints + card suggestion extraction with AI-generated badges), theme extraction hardening (single-extraction lock + cancel button, per-section compaction guard, pre/post overflow + truncation checks, Anthropic prompt caching, summary footer + per-call provider metadata in extraction logs, SSE retry visibility - see "Theme Extraction" section).

**Remaining:**
- Mechanic generation pipeline stage (refactor mechanic_generator.py, review UI for picking 3 from 6) → [Trello TC-2](https://trello.com/c/yw02hjGi)
- Archetype generation pipeline stage (LLM generates 10 color-pair archetypes) → [Trello TC-3](https://trello.com/c/o0JsJ8Di)
- Visual reference extraction stage (LLM extracts visual-references.json from setting prose) → [Trello TC-4](https://trello.com/c/DTLkQuIM)
- Pointed questions template (mechanic name substitution) → [Trello TC-5](https://trello.com/c/RHKh2z6D)
- Prompts module update (use setting prose + archetypes.json) → [Trello TC-6](https://trello.com/c/MR5g9C8s)
- Skeleton integration (card_requests → reserved slots, constraints → revision) → [Trello TC-7](https://trello.com/c/Ypyo2QJI)
- Configure page integration (check theme.json exists before pipeline start) → [Trello TC-7](https://trello.com/c/Ypyo2QJI)

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

## Tab State Persistence (`mtgai/runtime/runtime_state.py`, `extraction_run.py`)
- **Hybrid model**: server is the source of truth for AI run state, pipeline state, and saved theme.json. The browser holds purely-UI ephemera (filters, scroll, expanded panels, draft text) under `mtgai:<setCode>:<key>` localStorage keys via `static/ui_state.js`'s `MtgaiState` API.
- **`GET /api/runtime/state`**: aggregator endpoint every page hits on mount. Returns `{active_set, available_sets, ai_lock, active_runs, pipeline, theme}`. `active_set` resolves from `?set_code=` -> persisted `output/settings/last_set.toml` (top-bar picker) -> most-recent on-disk `pipeline-state.json` -> most-recent `theme.json` -> `MTGAI_REVIEW_SET` env -> `"ASD"`. `available_sets` is `[{code, name|null}]` for every directory under `output/sets/` matching `[A-Z0-9]{2,5}`.
- **Active set persistence (`mtgai/runtime/active_set.py`)**: the top-bar set picker (rendered into `#set-picker` in `base.html` by `static/set_picker.js`) is the single source of truth for which set the UI works on. `read_active_set()` / `write_active_set(code)` round-trip via `output/settings/last_set.toml`; stale codes whose dir was deleted return `None` so the resolver falls through. `list_sets()` enumerates set dirs (with theme.json names when present); `create_set(code, name=None)` scaffolds a new dir and optionally writes a `{code, name}` theme.json stub.
- **Endpoints**: `POST /api/runtime/active-set {code}` switches the persisted active set (404 if the dir doesn't exist). `POST /api/runtime/sets {code, name?}` scaffolds + activates a brand-new set (409 if it already exists). `POST /api/pipeline/theme/save` also persists the saved code as the active set so the picker doesn't snap back to the previous selection on next page load.
- **`GET /api/pipeline/theme/load?set_code=`**: returns the saved `theme.json`; 404 when absent. Theme wizard uses this for server-driven hydration on page load.
- **Theme extraction reattach** (`mtgai/runtime/extraction_run.py`): the SSE event stream is broadcastable, not single-subscriber. The worker pushes events through `extraction_run.append_event(...)`, which fans out to every subscribed queue under a single lock. New SSE clients (`subscribe()`) get the full event log replayed before tailing live events. This means **tab-switching mid-extraction no longer cancels the run** — clients unsubscribe on disconnect, the worker keeps running, and a returning tab resumes streaming. Cancel is opt-in via the explicit cancel button (`POST /api/ai/cancel`). After `mark_done()`, late subscribers still get the full replay so the UI can render the final state.
- **Adding a new long-running AI run to `active_runs`**: extend `_active_runs_payload()` in `runtime_state.py` with the new run kind (mechanics, archetype, card-gen, etc.). The same broadcast pattern as `extraction_run` should be used for any future SSE stream that needs to survive tab switches.

## AI Mutex (`mtgai/runtime/ai_lock.py`)
- App-wide mutex enforcing **one AI call at a time** across the whole process. All AI-touching endpoints (theme extraction, the per-section refresh endpoints, future mechanic / archetype / card-gen / balance / AI-review / art stages) acquire the same lock. A second guarded action that arrives mid-run gets a 409 with `{running, running_action, started_at, log_path}` so the UI can render an informative "busy" toast.
- **API**: `try_acquire(name, log_path=None)` / `release()`, `hold(name, log_path=None)` context manager (yields True on success, False if busy), `is_running()`, `current_action()`, `request_cancel()`, `is_cancelled()`, `update_log_path(path)` for late-binding the per-run log dir, `busy_payload()` (JSON-shape used by the 409 body and `/api/ai/status`), `reset_for_tests()` (test-only).
- **Adding a new guarded endpoint**: wrap the AI-touching body in `with ai_lock.hold("Action name") as acquired: if not acquired: return 409`. Long-running callers should `if ai_lock.is_cancelled(): raise` inside their inner loops.
- **Status endpoints**: `GET /api/ai/status` returns the busy payload (running + action metadata). `POST /api/ai/cancel` signals cancel app-wide. The legacy `/api/pipeline/theme/status` and `/api/pipeline/theme/cancel` are kept as aliases — `theme_extractor.is_running` / `request_cancel` are now thin shims that delegate to `ai_lock`.

## Theme Extraction (`mtgai/pipeline/theme_extractor.py`)
- Front door for the theme wizard at `/pipeline/theme`. Reads PDF/text upload, runs a multi-stage LLM extraction, then a JSON pass for constraints + card suggestions.
- **Single extraction at a time**: enforced by the app-wide `mtgai.runtime.ai_lock` (see "AI Mutex" above). `request_cancel()` and `is_running()` are thin shims that delegate to `ai_lock`. SSE handler calls cancel on browser disconnect. UI exposes a "Cancel Extraction" button.
- **Endpoints**: `POST /api/pipeline/theme/upload`, `/analyze`, `/cancel`. `GET /extract-stream` (SSE) returns 409 with the shared busy payload if any AI action is active. `GET /status` reports `running` + active log path. `POST /extract-section` returns 409 + busy payload on conflict.
- **Two extraction paths** based on token count vs. context window:
  - **Single-pass** (fits in one call): one LLM call with the full document.
  - **Per-section multi-chunk** (large docs): 7 sections × N chunks. Each section is built incrementally - first chunk seeds it, each subsequent chunk passes back the accumulated section for extension.
- **Compaction guard**: per-section accumulated text is bounded at 40% of chunk budget. When it exceeds, runs a compaction LLM call (with hard-truncate fallback) before the next chunk. Prevents quadratic context growth on long documents; trade-off is controlled information loss.
- **Pre/post overflow checks** (llamacpp only, via `mtgai.generation.token_utils`): `count_messages_tokens` checks input fits before sending; `check_post_call_response(resp, ...)` (or the lower-level `check_post_call({prompt_tokens, completion_tokens, finish_reason}, ...)`) raises `InputTruncatedError` / `OutputTruncatedError` from llmfacade's `Response.usage` + `finish_reason`.
- **Anthropic prompt caching**: system prompt marked `cache_control: ephemeral` so the per-section calls within ~5 min reuse the cached prefix (90% input discount).
- **llamacpp hygiene**: managed-mode llama-swap supervises `llama-server` per registered model. Stop sequences for source-text divider markers (`_LLAMACPP_STOP_SEQUENCES`). Capture `prompt_tokens` / `completion_tokens` / `finish_reason` from llmfacade's `Response.usage`.
- **Repetition loop detection**: `_detect_tandem_repeat` (suffix periodicity scan) runs every 64 chars of new content; aborts mid-stream so a runaway loop can't fill `max_tokens`. Period-length-aware thresholds (e.g. period 2-4 chars: 8 reps; period 11-25 chars: 4 reps; period 61-120 chars: 2 reps). The period window must contain at least one alphanumeric character — suppresses ASCII-art / markdown-separator false positives like `"-"*N`, `"|---|---|"`, `"_"*N`. Catches the user-reported `"the-the-the-..."` failure mode that the old whitespace-split token detector missed (hyphen-glued tokens look like one token to `split()`).
- **Extraction log** (`output/extraction_logs/extraction_<ts>.md`, gitignored): one file per run with system + user prompts, streamed response, per-call provider metadata, retry markers, and a summary footer (wall time, total calls, tokens, retries, sections-with-content, cancel/abort reason). `tail -f` mirrors live LLM output.
- **SSE retry visibility**: every JSON-subcall retry yields a `status` event with attempt number + previous failure reason - keeps the progress bar moving on slow local models.
- **Live progress banner via `phase` SSE events**: every state transition emits `{"type": "phase", "phase": "loading|counting|extracting|compacting|json_subcall|generation|done", "activity": "<one-liner>", "elapsed_s": float, "structural"?: {...}, "prompt_eval"?: {processed, total}, "generation"?: {tokens, tok_per_sec, elapsed_s}}`. Wiring: a module-level `_phase_emit_fn` slot is set by the worker (`set_phase_emitter(extraction_run.append_event)` in `pipeline/server.py::_start_extraction_worker`) and cleared on exit. The non-streaming section-refresh path leaves it `None` so phase events drop silently. Section/chunk indices ride a `_StructuralState` singleton updated by `_run_multi_chunk`; JSON subcalls use a per-emit `structural_override`. During llamacpp streaming, a daemon `_PromptEvalPoller` polls `provider.slots(model=...)` every 500 ms and translates `n_prompt_tokens_processed/n_prompt_tokens` into `prompt_eval` ticks during TTFT, then `n_decoded` into `generation` ticks once decoding starts. Anthropic has no analogous introspection — the bar shows phase-default percents until `theme_chunk` events arrive. The frontend (`theme.html` + `theme.js::handlePhaseEvent`) renders a sticky banner with activity label + elapsed time + a real percent bar (structural OR prompt-eval), switching to an indeterminate stripe + tok/s during generation.
- **Upload cache TTL**: 30 min. Stale entries evicted on every upload.
- **Image / vision support removed** - was bloating logs with base64 and only the single-pass path ever used images.
- **Split JSON subcall output caps**: `_JSON_SUBCALL_CONSTRAINTS_MAX_TOKENS = 4096` (constraints output is short), `_JSON_SUBCALL_SUGGESTIONS_MAX_TOKENS = 8192` (card suggestions need more room for descriptions). Per-call override threads through `_stream_single_call` → `_stream_llamacpp_call` via `output_budget_override`. Defense against runaway generation filling context is now primarily the mid-stream repetition detector; the cap is secondary.
- **Partial text preserved on errors**: TRUNCATION, repetition ABORT, missing-done, and stream exceptions now include `partial_text` in the yielded error event. `_attempt_json_subcall` captures it as `raw`, so the UI aggregated error panel shows every attempt's streamed output - not just ones that completed cleanly. Previously all content was lost on error.
- **Frame-count diagnostics** in per-call metadata: `frames_total`, `frames_with_content`, `theme_text_chars`. Successful runs show `frames_with_content` ≈ `completion_tokens`. Observed under Ollama: ~12-16 empty frames per content frame (likely format=json grammar-validation heartbeats); ratio under llama.cpp not yet measured — worth comparing once we have a few full runs on the new transport. → [Trello](https://trello.com/c/9xsFULTP)

## LLM Client (`mtgai/generation/llm_client.py`)
- **All transport goes through [llmfacade](https://github.com/Coamithra/LLMFacade)** — a unified Provider/Model/Conversation API over Anthropic and llama.cpp. MTGAI no longer talks to either backend's HTTP layer directly. Both `llm_client.py` (card/mechanic generation) and `theme_extractor.py` (streaming theme extraction) build llmfacade `Conversation` objects via `_get_provider("anthropic" | "llamacpp")` and call `convo.send(...)` or `convo.stream(...)`. `art_selector.py` does the same for vision calls (Anthropic image blocks via `ImageBlock.from_path`).
- `generate_with_tool()` — unified entry point. Provider is resolved per-call from the model registry (`_resolve_provider(model_id)`); fallback to `MTGAI_PROVIDER` env var (default `anthropic`). Stale `MTGAI_PROVIDER=ollama` values are aliased to `llamacpp` with a one-shot warning so old `.env` files don't blow up at import.
- **Tool schemas**: callers still pass MTGAI/Anthropic-shaped tool schema dicts (`name`, `description`, `input_schema`). `_make_tool()` wraps them as `llmfacade.Tool` objects with a no-op callable; we read structured args from `Response.tool_calls[0].input` directly and never invoke the tool fn. `tool_choice=tool_schema["name"]` forces the model to emit a tool call.
- **Anthropic provider settings** (set on the cached llmfacade Provider):
  - `exact_count_tokens=True` — hits Anthropic's free server-side `count_tokens` endpoint when `theme_extractor` asks for an exact pre-call estimate.
  - `auto_cache_tools=True` — reproduces the pre-migration `cache_control: ephemeral` on the tool schema so sequential calls within ~5 min reuse the cached prefix (90% discount). Per-call `cache=False` honours the contract by overriding to `auto_cache_tools=False` on that conversation.
  - System prompt caching: pass `SystemBlock(text=..., cache=True)` to mark for ephemeral caching.
- **llamacpp provider settings**:
  - **Managed mode** (no `base_url=`): llmfacade owns a `llama-swap` subprocess that lazy-spawns `llama-server` instances on first call. Session dir: `<repo>/.llmfacade/`.
  - `repeat_penalty=1.1` — Gemma-loop mitigation, now actually honoured by the sampler (see `learnings/gemma-repetition-loops.md` + the migration section above).
  - Per-model launch knobs come from `models.toml` via `_llamacpp_new_model(provider, model_id)`: `gguf=` (required), `context_size=`, `cache_type_k=`, `cache_type_v=`, `n_gpu_layers=`. The supervisor regenerates `swap.yaml` and llama-swap's `-watch-config` picks up new entries automatically.
- **Local models available**: Qwen 2.5 (3B/14B), Qwen 3.5 4B, Phi-4 Mini, Llama 3.2 3B, Gemma 4 26B IQ4_XS (Vlad). Add models by dropping a `.gguf` into `C:\Models\` and registering it in `models.toml`. `all-local` preset uses Vlad Gemma 4 26B for all stages.
- **llamacpp tool extraction**: native function calling first via llmfacade's `resp.tool_calls` (now backed by llama.cpp's grammar-constrained tool format), falls back to JSON extraction from raw text (fenced blocks, Qwen-style, bare JSON) when the model emits args inline as text. Retries up to `MTGAI_MAX_RETRIES` (default 3) on garbage output.
- **Token counting** (`token_utils.py`): tiktoken cl100k_base for approximate counts on the llamacpp path. Pre-call overflow check raises `ContextOverflowError`. Post-call `check_post_call_response(resp)` raises `InputTruncatedError` / `OutputTruncatedError` from llmfacade's `Response.usage` + `finish_reason="length"`. (Exact tokenization via llama-server's `/tokenize` is available through `provider.count_tokens(text, model_id=...)` if a caller wants precision over speed.)
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
- **Per-set model settings** (`model_settings.py`): per-stage assignments + effort live in `output/sets/<SET>/settings.toml` — one file per set, so changing the LLM for `card_gen` on ASD does not silently affect DSN.
  - `get_llm_model(stage_id, set_code)` → API model_id for the stage on that set
  - `get_effort(stage_id, set_code)` → effort level or None
  - `get_image_model(stage_id, set_code)` → image model key
  - `apply_settings(set_code, settings)` → persists + caches the per-set file
  - `ModelSettings.from_preset(name)` → built-in presets ("recommended", "all-haiku", "all-local") *or* a saved profile by name
  - **Stage runners must resolve once at the top of the run** and reuse the resolved values for the whole stage — no per-call `get_llm_model` inside loops. This is how we deliver the "no mid-stage swap" guarantee without a `resolved_*` field on `StageState`.
- **Global defaults** (`output/settings/global.toml`): a tiny file with `default_preset = "<name>"` — used to seed every new set's settings.toml. Created on first call to `get_global_settings()`. If the legacy `output/settings/current.toml` exists at first creation it is copied into `imported.toml` and the default preset points at it.
- **Profile library** at `output/settings/<name>.toml`: reusable templates spanning sets. `save_profile(name)` writes one; `from_preset(name)` resolves built-in presets first, then the profile library. Reserved names: `global`, `current`.
- **Settings UI** at `/settings` — per-stage model dropdowns, presets, profile save/load, cost estimation. Endpoints accept an optional `set_code` query param (falls back to the active set); the wizard rewrite (TC tracker `Wizard UI redesign`) will plumb set_code explicitly through every request.
- **Migration**: existing sets without a settings.toml get one seeded on first `get_settings(set_code)` call — copy from `current.toml` if present, else from the global default preset, else built-in defaults. `current.toml` is no longer written to but is left on disk for manual cleanup.
- LLM stages: theme_extract, mechanics, archetypes, reprints, lands, card_gen, balance, skeleton_rev, ai_review, art_prompts, art_select. Image stages: char_portraits, art_gen.
- Add new models by editing `backend/mtgai/settings/models.toml`. Stage runners must never hardcode model IDs — always resolve via `get_llm_model(stage_id, set_code)`.

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
- **Colored artifact frames** not yet implemented — see `learnings/colored-artifact-frames.md` for research and future plan → [Trello](https://trello.com/c/xiFbWsDH)
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
