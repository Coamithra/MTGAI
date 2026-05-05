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
   ```
3. The supervisor lazy-loads on first reference. **TOML keys can't contain `.`** — use `qwen36-35b-a3b`, not `qwen3.6-35b-a3b`, or quote the section header.

## Default 26B config

`gemma4-26b-vram-dynamic` (long-context theme-extraction default, per TC-2):
- Vlad IQ4_XS GGUF + `cache_type_k/v = "q8_0"` + `n_gpu_layers = -1`.
- q8_0 KV trims cache from 3.4 GB (f16) to 1.7 GB at 128K context, freeing layers for GPU placement.

`gemma4-e4b-unsloth` is a real candidate to dethrone Vlad — competitive wall time at ~half the VRAM, faster TTFT, more output content. Pending broader quality comparison beyond Dark Sun corpus.

## Gotchas

- **`n_gpu_layers = -1` is "all layers on GPU", NOT auto-placement.** Unlike Ollama's `num_gpu = -1` (which used a placement estimator), llama.cpp interprets `-1` literally. Production Vlad config survives at 89% VRAM only because IQ4_XS (14 GB) + q8_0 KV (1.7 GB) just barely fits. f16 KV with `-1` OOMs mid-extraction. Treat `-1` as "manually verified to fit", not "auto-fit". Auto-placement is a real TODO → [Trello](https://trello.com/c/dybBBMjM).
- **Flash attention is forced ON for q8_0/q4_0 KV cache configs.** llama-server refuses `--flash-attn off` with quantized V cache (`"V cache quantization requires flash_attn"` — they're hard-coupled). For f16 KV (small models that don't quantize), pass `--flash-attn on` explicitly. Once llmfacade exposes `flash_attn` as a launch knob, set it explicitly on every entry → [Trello](https://trello.com/c/8zfB8zO6).
- **Stock Google Gemma 4 GGUFs from Ollama do NOT load in llama.cpp.** Architecture metadata expects multimodal tensors (vision + audio) but blobs ship text-only; loader rejects with `"wrong number of tensors; expected 2131, got 720"`. Only Unsloth's text-only repacks (and VladimirGav's) work.
- **Per-model KV-cache quantization** happens at server launch via `--cache-type-k`/`--cache-type-v`. llmfacade passes them when `cache_type_k`/`cache_type_v` are set on the entry. No global env var; per-server, per-model. q4_0 only helps in the placement sweet spot (where smaller KV shifts layers from CPU to GPU — i.e. ~14 GB-weight models on 12 GB VRAM). Smaller models lose quality; larger models barely benefit.
- **Local vision is an llmfacade gap.** The managed-mode llamacpp provider doesn't yet accept `mmproj_path` on `provider.new_model(...)` or marshal vision blocks into the OpenAI `image_url` shape llama-server consumes. `supports_vision = false` on every llamacpp registry entry, including Gemma 4 26B (which has a multimodal projector available). Don't flip the flag without plumbing `mmproj_path` through `_llamacpp_new_model` → [Trello](https://trello.com/c/kRrLt2GM).

## Repetition-loop mitigation

- `repeat_penalty=1.1` set provider-wide via llmfacade (rides `extra_body` onto the llama-server wire).
- JSON-subcall retries escalate per attempt: `_RETRY_REPEAT_PENALTIES = [None, 1.15, 1.20]` in `theme_extractor`. Override threads through `_attempt_json_subcall → _stream_single_call → _stream_llamacpp_call`.
- Temperature is intentionally NOT escalated (higher temperatures produce malformed JSON on smaller models; repeat_penalty alone breaks loops in practice).
- The mid-stream `_detect_tandem_repeat` (suffix periodicity scan, every 64 chars) is the primary runaway guard — it catches loops within 64 chars, before the sampler-level penalty would have taken effect.

## VRAM math

KV cache grows linearly with context. Formula: `VRAM = (P × b_w) + (0.55 + 0.08 × P) + KV_cache`. At Q4_K_M, `b_w = 0.57 bytes/weight`. Reference: https://localllm.in/blog/interactive-vram-calculator.

## Lifecycle

llama-swap subprocess + its YAML live under `<repo>/.llmfacade/`. First `convo.send()` in any process spawns it; OS-level kill-on-parent-death (Win32 Job Object on Windows) tears it down with the parent. PID-file sweep on next start reaps any orphan that survived a hard kill. No tray icon to manage; nothing to autostart at boot.
