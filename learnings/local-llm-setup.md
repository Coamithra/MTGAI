# Local LLM Setup (Gemma 4, llama.cpp managed mode)

Operational notes for the local-LLM transport. For per-model benchmark numbers and the migration history, see `llamacpp-tc2-benchmark.md`. For the repetition-loop story (Ollama dropped `repeat_penalty`; llama.cpp honours it), see `gemma-repetition-loops.md`.

## Where things live

- **Backend**: llmfacade `llamacpp` provider in managed mode. First call lazy-spawns a `llama-swap` subprocess under `<repo>/.llmfacade/`; it supervises one `llama-server` instance per registered model.
- **Binaries**: `C:\Tools\llama.cpp\` (`llama-server.exe`, `llama-swap.exe` on PATH).
- **GGUFs**: `C:\Models\`.
- **Registry**: `backend/mtgai/settings/models.toml` declares per-model launch knobs (gguf path, context_size, KV-cache quant, GPU offload). Knobs are threaded into `provider.new_model(...)` by `_llamacpp_new_model()` in `llm_client.py`.

## Adding a model

1. Drop the `.gguf` into `C:\Models\`.
2. Add a section to `models.toml`:
   ```toml
   [llm.your-model-id]
   provider = "llamacpp"
   model_id = "your-model-id"     # llama-swap YAML key + OpenAI `model:` arg
   gguf_path = "C:/Models/your-file.gguf"
   context_window = 131072
   # optional
   cache_type_k = "q8_0"
   cache_type_v = "q8_0"
   n_gpu_layers = -1               # see footgun below
   thinking = "adaptive"           # optional: reason on tool turns (Gemma 4 / Qwen3)
   ```
3. The supervisor lazy-loads on first reference. **TOML keys can't contain `.`** — use `qwen36-35b-a3b`, not `qwen3.6-35b-a3b`, or quote the section header.

## Default 26B config

`gemma4-26b-unsloth-iq4xs` (the local default — `DEFAULT_LLM_ASSIGNMENTS` + the `all-local` preset point here):
- Unsloth's text-only 26B-A4B repack at UD-IQ4_XS GGUF (~13 GB) + `cache_type_k/v = "q8_0"` + `n_gpu_layers = -1` + `thinking = "adaptive"`.
- Mirrors the older `gemma4-26b-vram-dynamic` (Vlad) entry — still registered as a fallback — but turns on reasoning for tool-using turns (see "Thinking control" under Gotchas). q8_0 KV trims cache from 3.4 GB (f16) to 1.7 GB at 128K context; the registry-load VRAM check flags the `n_gpu_layers = -1` (WARN or ERROR level depending on free VRAM — warn-only, never raises by default), an expected, conservative message since the IQ4_XS file is ~0.6 GB smaller than Vlad's proven all-GPU config.

`gemma4-e4b-unsloth` is a real candidate to dethrone Vlad — competitive wall time at ~half the VRAM, faster TTFT, more output content. Pending broader quality comparison beyond Dark Sun corpus.

## Gotchas

- **`n_gpu_layers = -1` is "all layers on GPU", NOT auto-placement.** Unlike Ollama's `num_gpu = -1` (which used a placement estimator), llama.cpp interprets `-1` literally. Production Vlad config survives at 89% VRAM only because IQ4_XS (14 GB) + q8_0 KV (1.7 GB) just barely fits. f16 KV with `-1` OOMs mid-extraction. Treat `-1` as "manually verified to fit", not "auto-fit". Auto-placement is a real TODO → [Trello](https://trello.com/c/dybBBMjM).
  - **Registry-load VRAM check** (`settings/vram_estimate.py`, run from `ModelRegistry.load()`): for every `n_gpu_layers = -1` llamacpp entry it estimates weights (GGUF file size) + KV cache (from the GGUF header at the configured `context_window`/cache-type) + ~10% overhead, and compares to live `nvidia-smi` VRAM. Logs a WARNING above 85% of *free* VRAM and an ERROR above 100% of *total* VRAM (a guaranteed OOM). It is **warn-only by default** — it never raises — so a misestimate can't brick startup; the production Vlad config at ~89% will log one expected WARNING. Knobs: `MTGAI_VRAM_CHECK_STRICT=1` makes an over-total verdict raise `VramRiskError`; `MTGAI_DISABLE_VRAM_CHECK=1` skips the check entirely. Degrades to a silent no-op anywhere the GGUF file is absent or there's no NVIDIA GPU (CI, non-GPU boxes). This only *flags* the risk; it does not pick or change `n_gpu_layers` (that's [Trello](https://trello.com/c/dybBBMjM)).
- **Flash attention is forced ON for q8_0/q4_0 KV cache configs.** llama-server refuses `--flash-attn off` with quantized V cache (`"V cache quantization requires flash_attn"` — they're hard-coupled). For f16 KV (small models that don't quantize), pass `--flash-attn on` explicitly. Once llmfacade exposes `flash_attn` as a launch knob, set it explicitly on every entry → [Trello](https://trello.com/c/8zfB8zO6).
- **Stock Google Gemma 4 GGUFs from Ollama do NOT load in llama.cpp.** Architecture metadata expects multimodal tensors (vision + audio) but blobs ship text-only; loader rejects with `"wrong number of tensors; expected 2131, got 720"`. Only Unsloth's text-only repacks (and VladimirGav's) work.
- **Per-model KV-cache quantization** happens at server launch via `--cache-type-k`/`--cache-type-v`. llmfacade passes them when `cache_type_k`/`cache_type_v` are set on the entry. No global env var; per-server, per-model. q4_0 only helps in the placement sweet spot (where smaller KV shifts layers from CPU to GPU — i.e. ~14 GB-weight models on 12 GB VRAM). Smaller models lose quality; larger models barely benefit.
- **Local vision is an llmfacade gap.** The managed-mode llamacpp provider doesn't yet accept `mmproj_path` on `provider.new_model(...)` or marshal vision blocks into the OpenAI `image_url` shape llama-server consumes. `supports_vision = false` on every llamacpp registry entry, including Gemma 4 26B (which has a multimodal projector available). Don't flip the flag without plumbing `mmproj_path` through `_llamacpp_new_model` → [Trello](https://trello.com/c/kRrLt2GM).
- **Thinking control is a per-entry knob.** `thinking = "adaptive"` (or `"disabled"`) on a llamacpp entry threads through `_llamacpp_new_model` → `provider.new_model(thinking=...)`; llmfacade maps it to the GGUF chat template's `enable_thinking` kwarg, which only works because managed mode launches llama-server with `--jinja` (default-on). `thinking_style` auto-detects from the GGUF (Gemma 4 / Qwen3 → `TEMPLATE_KWARG`); set it explicitly only to override the once-per-model style-mismatch warning. **Keep the llamacpp tool path on auto `tool_choice`** — forcing tool_choice with thinking on makes llama.cpp misroute the tool call into `reasoning_content` (ggml-org/llama.cpp#20809), so `_generate_llamacpp` deliberately leaves it unforced (the Anthropic path forces it; the llamacpp path must not).

## Repetition-loop mitigation

- `repeat_penalty=1.1` set provider-wide via llmfacade (rides `extra_body` onto the llama-server wire).
- JSON-subcall retries escalate per attempt: `_RETRY_REPEAT_PENALTIES = [None, 1.15, 1.20]` in `theme_extractor`. Override threads through `_attempt_json_subcall → _stream_single_call → _stream_llamacpp_call`.
- Temperature is intentionally NOT escalated (higher temperatures produce malformed JSON on smaller models; repeat_penalty alone breaks loops in practice).
- The mid-stream `_detect_tandem_repeat` (suffix periodicity scan, every 64 chars) is the primary runaway guard — it catches loops within 64 chars, before the sampler-level penalty would have taken effect.

## VRAM math

KV cache grows linearly with context. Formula: `VRAM = (P × b_w) + (0.55 + 0.08 × P) + KV_cache`. At Q4_K_M, `b_w = 0.57 bytes/weight`. Reference: https://localllm.in/blog/interactive-vram-calculator.

## Lifecycle

llama-swap subprocess + its YAML live under `<repo>/.llmfacade/`. First `convo.send()` in any process spawns it; OS-level kill-on-parent-death (Win32 Job Object on Windows) tears it down with the parent. PID-file sweep on next start reaps any orphan that survived a hard kill. No tray icon to manage; nothing to autostart at boot.
