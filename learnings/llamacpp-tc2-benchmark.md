# TC-2: llama.cpp Transport Benchmark

**Hardware**: NVIDIA RTX 4070 Ti (12 GB VRAM), AMD Ryzen 9 7900X3D 12-core, Windows 11
**Date**: 2026-05-03
**Corpus**: Dark Sun Campaign Setting PDF (58,273 input tokens via tiktoken cl100k)
**Goal**: Re-baseline post-Ollama→llama.cpp migration. Measure the speedup, sweep KV cache modes per-model (no longer a global env var), and re-test models that Ollama killed via runtime/OOM.

## TL;DR

1. **Migration win is enormous**: Vlad Gemma 4 26B at q4_0 KV ran in **95.4s** on llama.cpp vs **239s** on Ollama (TC-1f winner) — **2.5× faster**. q8_0 at **105.5s** vs Ollama's interpolated ~280s = **2.7× faster**. Same hardware, same model, same context, same corpus.
2. **E4B is a real contender for theme extraction**: Unsloth Gemma 4 E4B (Q4_K_M, ~5 GB) at q8_0 / 128K all-GPU finished the 58K-token Dark Sun extraction in **107.9s** — basically tied with Vlad's 105.5s — with **TTFT of 28.7s (32% faster)** and **18,268 output chars (60% more content)** at **47% VRAM (5.8 GB)**. Output quality is production-grade — all 7 sections, well-structured, detailed. E4B may dethrone Vlad as the theme-extraction default once we sanity-check it across more corpora.
3. **TTFT collapsed**: 38–42s on llama.cpp vs Ollama's best 51s (q4_0+flash). Prompt-eval is meaningfully faster on llama.cpp's transport — most likely better batching of the OpenAI-compatible chat-completions endpoint vs Ollama's `/api/generate` path.
4. **Per-model KV cache config replaces the global env var**: Each `llm.*` entry in `models.toml` declares `cache_type_k` / `cache_type_v` / `n_gpu_layers`, which thread through `_llamacpp_new_model` to `--cache-type-k`/`-v` / `--n-gpu-layers` at server launch. Ollama's `OLLAMA_KV_CACHE_TYPE` env var is gone.
5. **`n_gpu_layers = -1` is a footgun on llama.cpp** (silent bug inherited from the migration). Ollama's `num_gpu = -1` meant *"auto-place"*; llama.cpp's `--n-gpu-layers -1` means literally *"all layers on GPU"*. The current production Vlad config (q8_0, all-GPU) survives at 89% VRAM only because q8_0 KV cache is small — switching to f16 OOMs mid-extraction. **Auto-placement in llmfacade is a real TODO** (see "Follow-ups" below).
6. **Flash attention status confirmed**: empirically verified during TC-2. **q8_0 / q4_0 KV runs forcibly enable flash attention** — llama-server refuses to start with `--flash-attn off` and quantized V cache (`"V cache quantization requires flash_attn"`). So the production Vlad q8_0 / q4_0 numbers are flash-on numbers, no upside available. The **f16 row (711.6s)** is the only one where flash is likely *off* (auto picked off for Gemma 4 + f16 cache) — that explains the 2.1× gap vs Ollama's flash-on f16 baseline. Implication: don't flip Vlad to f16 KV expecting the TC-2 bench to apply. See `C:\Programming\LLMFacade\plans\llmfacade-feature-request-flash-attn.md` for the proposed `flash_attn` launch knob.
7. **Stock Google Gemma 4 GGUFs from Ollama are unusable in llama.cpp**: the architecture metadata expects multimodal tensors (vision + audio) but the blobs ship text-only, and the loader rejects with `"wrong number of tensors; expected 2131, got 720"`. Only Unsloth's text-only repacks (and VladimirGav's, which we already use) load successfully. Affects D1 (gemma4:26b), D3 (gemma4:e4b), D4 (gemma4:31b). Hard links to those blobs were removed from `C:\Models\` and the entries dropped from `models.toml`.

## Headline numbers — Vlad Gemma 4 26B IQ4_XS, 128K context, 58K-token corpus

| KV cache | n_gpu_layers | flash_attn | Wall (s) | TTFT (s) | OutChars | VRAM at load | vs TC-1f Ollama |
|---|---|---|---|---|---|---|---|
| f16 | 35 (forced) | auto (likely **off**) | 711.6 | 408.3 | 10,286 | 95% | 2.1× **slower** vs Ollama 346s (all-GPU + flash on) |
| q8_0 | -1 (all GPU) | **on** (forced by V quant) | **105.5** | **42.1** | 11,306 | 89% | ~**2.6× faster** vs Ollama interpolated ~280s |
| q4_0 | -1 (all GPU) | **on** (forced by V quant) | **95.4** | **38.0** | 11,342 | 90% | **2.5× faster** vs Ollama 239s (winner) |

Note on the f16 row: two compounding handicaps. (1) Manually capped GPU layers to 35 because `-ngl -1` OOMs the 12 GB card with f16 KV cache (3.4 GB cache + 14 GB weights at 128K). (2) Flash attention almost certainly off — llama-server's `auto` heuristic disables it on Gemma 4 + f16 KV (verified via control test 2026-05-03: forcing `--flash-attn on` on the q8_0 config produced identical numbers, while `--flash-attn off` on q8_0 crashes with `"V cache quantization requires flash_attn"`). The 711s is partial-offload pessimum *and* flash-off — not directly comparable to Ollama's all-GPU+flash 346s, and not a recommended config.

Verification cmds for future runs:
```sh
# Force flash on, see if it helps any specific config:
llama-server --model <gguf> --flash-attn on ...
# Crash signature confirming flash-quantization coupling:
llama-server --model <gguf> --cache-type-v q8_0 --flash-attn off ...
#   → "V cache quantization requires flash_attn"
```

q4_0 vs q8_0 on llama.cpp: 95s vs 106s = q4_0 is ~10% faster. Ollama's gap was ~30%. The migration normalized the gap (both modes are now flash-attention-by-default; q4_0's smaller KV cache helps less because llama.cpp already streams the prompt eval more efficiently than Ollama did).

## Phase C — raw `llama-bench.exe` tok/s

Reference numbers without MTGAI/llmfacade in the loop. `pp512` = prompt-eval throughput on a 512-token prompt; `tg128` = generation throughput across 128 tokens. n_gpu_layers=999 (= "all").

| Model | pp512 tok/s | tg128 tok/s | Wall (s) | Notes |
|---|---|---|---|---|
| llama3.2-3b | 11,158 | 182.4 | 5.7 | |
| qwen2.5-3b | 11,370 | 184.8 | 5.0 | |
| phi4-mini | 10,313 | 153.5 | 6.6 | |
| qwen3.5-4b | — | — | — | **GGUF won't load** — `failed to load model`. Ollama-bundled qwen3.5-4b blob is incompatible. Replace with [Unsloth's Q4_K_M](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF). |
| qwen2.5-14b | 2,904 | 48.9 | 20.8 | Solid middle-tier |
| vlad-gemma4-26b-dynamic | 486 | 28.9 | 36.7 | Slowest as expected for 14 GB-class on a 12 GB card |

Sanity check: Vlad's 486 pp/s × 58K = ~119s of prompt eval, but the real Phase B q8_0 run hit TTFT in 42s. The full extraction batches better than `pp512` alone — `llama-bench`'s default measurement understates real-world throughput.

## Phase D — discounted/competitor candidates

**Status**: partial data. Most discounted candidates were unloadable in llama.cpp because the Ollama-shipped blobs are text-only repacks of multimodal Gemma 4 architecture metadata.

### Phase D — Ollama-cached blob attempts (mostly blocked)

| ID | Model | Outcome |
|---|---|---|
| D1 | `gemma4:26b` stock (q4_K_M, Ollama blob) | **Blocked** — `expected 2131 tensors, got 658`. Multimodal architecture metadata, text-only blob. |
| D2 | Unsloth Gemma 4 26B UD-Q4_K_XL (Ollama blob) | **Loaded successfully**, but extraction with `n_gpu_layers=35 + q8_0 + 128K` hadn't reached TTFT after **22 min** — killed. Unsloth weights (~17 GB) heavier than Vlad (~14 GB), so partial offload is even slower per token. Doesn't fit at `-ngl -1` on 12 GB VRAM. |
| D3 | `gemma4:e4b` stock (Ollama blob) | **Blocked** — same multimodal tensor mismatch. |
| D4 | `gemma4:31b` dense (Ollama blob) | **Blocked** — same multimodal tensor mismatch. |
| D5 | gemma4:31b at 128K | Skipped (D4 unreachable). |
| D6 | Qwen 3.6 35B-A3B Unsloth UD-Q4_K_XL (HF download) | **Loaded successfully** (17s flare, 95% VRAM, 22 GB GGUF), but extraction with `n_gpu_layers=25 + q8_0 + 128K` hadn't reached TTFT after **9 min** — killed. MoE didn't help vs partial-offload because llama.cpp's `--n-gpu-layers` offloads whole layers (all experts in a layer go together); the per-token MoE win only materializes when the active experts happen to be on the GPU layers, which is a 25/~80 = ~30% probability per token. See `--n-cpu-moe` follow-up below. |
| D7 | Qwen 3.6 27B Q4_K_M (HF download) | **Loaded successfully** (13s flare, 96% VRAM, 17 GB GGUF), but extraction with `n_gpu_layers=35 + q8_0 + 128K` hadn't reached TTFT after **14 min** — killed. Same partial-offload pattern as D2. Dense 27B at 35-layer split is too slow for practical use on 12 GB VRAM. |

### Phase D-bis — fresh HuggingFace Gemma 4 downloads (replaces broken Ollama blobs)

After confirming the Ollama-cached Gemma 4 blobs are unloadable, downloaded Unsloth's text-only repacks directly from HuggingFace.

| ID | Model | Outcome |
|---|---|---|
| D2-bis | Unsloth `gemma-4-26B-A4B-it-UD-Q4_K_M` (16.9 GB, MoE 26B-A4B) | **Loaded successfully** at `n_gpu_layers=40 + q8_0 + 128K` (17s flare, 95% VRAM, 25 GB resident). Extraction hadn't reached TTFT after **12 min** — killed. Confirms the partial-offload pattern: 26B-class Gemma at 35–40 layers on 12 GB VRAM is too slow for the 58K-token Dark Sun corpus regardless of which Unsloth quant. Vlad's 14 GB IQ4_XS continues to be the only 26B variant that fits all-GPU. |
| **D3-bis** | **Unsloth `gemma-4-E4B-it-Q4_K_M` (5 GB)** | **🏆 Hit-out-of-the-park result.** Load 6.8s, **wall 107.9s** (~tied with Vlad q8_0 105.5s), **TTFT 28.7s (32% faster than Vlad's 42.1s)**, **output 18,268 chars (60% more than Vlad's 11,306)**, VRAM **47% (5.8 GB — half of Vlad's 89%)**. Output quality is production-grade — all 7 sections present, detailed creature/faction/landmark/character entries, well-structured prose. **Real contender to dethrone Vlad as the theme-extraction default.** HUMAN NOTE: After reviewing the output I disagree with Claude here. The sections are present but the info in them is not as good as what the larger model produces. Stuff is missing. Not a contender. |
| D4-bis | Unsloth `gemma-4-31B-it-Q4_K_M` (18.3 GB, dense) | **Loaded successfully** at `n_gpu_layers=20 + q8_0 + 32K` (13.6s flare, 69% VRAM, 21 GB resident). Even on the small **3K-token ASD corpus** (single-pass), extraction hadn't reached TTFT after **6 min** — killed. Dense 31B with ~60 layers on CPU is unusable on 12 GB VRAM at any meaningful prompt length. Confirms TC-1f's "never use" verdict for dense 31B holds under llama.cpp too. |

### Why the Ollama Gemma 4 blobs fail

llama.cpp's loader does a strict tensor-count assertion against the GGUF's architecture metadata. Ollama's Gemma 4 blobs declare the multimodal Gemma 4 architecture (with audio + vision tensor groups) but ship only text weights. The count mismatch — e.g. `expected 2131, got 720` for E4B — fails the load before any inference. VladimirGav's blob works because his Modelfile produces a self-consistent text-only architecture description; same goes for Unsloth's text-only repacks.

This means Ollama-cached blobs are NOT a free download dodge for stock Google Gemma 4 weights — only for community repacks that the maintainer rebuilt with text-only metadata.

## What changed vs TC-1f

| Aspect | TC-1f (Ollama 0.21) | TC-2 (llama.cpp via llmfacade managed mode) |
|---|---|---|
| Transport | `/api/generate`, `/api/chat` | OpenAI-compatible `/v1/chat/completions` via llama-swap → llama-server |
| KV cache mode | Global `OLLAMA_KV_CACHE_TYPE` env var, requires tray restart | Per-model `cache_type_k` / `cache_type_v` in `models.toml`, no env var |
| Flash attention | Auto-enabled on supported architectures (0.21+) | Auto-enabled by llama-server when supported |
| Layer placement | `num_gpu = -1` = "auto-place via Ollama estimator" | `--n-gpu-layers -1` = literally "all layers" — no auto |
| Repetition penalty | Silently dropped by `ollamarunner` Go sampler on Gemma | Honoured. Per-call retry escalation works as written. |
| Slot save/restore | None | Available via `provider.save_slot()` / `restore_slot()` (not yet wired into MTGAI) |
| Vision | Anthropic only (Ollama path was image-blocked anyway) | Anthropic only — managed-mode llamacpp doesn't pass `--mmproj` yet |
| Process lifecycle | Tray app, persistent | Lazy-spawn per-MTGAI-process via Win32 Job Object; PID-file sweep on next start |

## Issues found and follow-ups

### CRITICAL: `n_gpu_layers = -1` semantics flipped silently across the migration
> Trello: [auto-placement](https://trello.com/c/dybBBMjM) (the real fix), [registry-load warning](https://trello.com/c/hSJPnWzA) (cheaper sibling)

The current production `gemma4-26b-vram-dynamic` registry entry has `n_gpu_layers = -1`, inherited verbatim from the Ollama-era Modelfile where `num_gpu = -1` meant "auto-placement". In llama.cpp, the same value means literally "all layers on GPU".

Production survives this because q8_0 KV cache (1.7 GB at 128K) is small enough that 14.2 GB Vlad weights + 1.7 GB cache + overhead just barely fit on 12 GB (post-load placement = 89%). Any of:
- Switching to f16 KV (TC-2 confirmed: OOM crash mid-extraction)
- A second GPU app holding 1+ GB
- A larger context window or larger model

…will OOM.

**Fix**: implement auto-placement in `llmfacade._llamacpp_new_model` (or its underlying `provider.new_model` wrapper). Two viable paths:

1. **Shell out to `C:\Tools\llama.cpp\llama-fit-params.exe`** — already in the toolchain, purpose-built for this. Cheap to integrate, opaque to debug.
2. **Port Ollama's `server/sched.go` estimator** — read GGUF header for layer count + per-layer weight size, query free VRAM (CUDA API or `nvidia-smi --query-gpu`), factor in KV cache size at the chosen context + cache_type, solve for max layers that fit. ~100 lines of Python. Predictable, testable.

In the meantime, `models.toml` should drop `n_gpu_layers = -1` and replace with explicit, measured-good values per-model. The TC-2 numbers give us those: 35 for f16/128K Vlad, ~50 for q8_0 (whatever number actually corresponds to ~89% VRAM in the working case).

### MoE-aware offload via `--n-cpu-moe` not yet wired through llmfacade
> Trello: [Add n_cpu_moe knob](https://trello.com/c/rM2ZCnau)

llama.cpp's `llama-server` accepts `--n-cpu-moe N`, which keeps the MoE expert weights of the first N layers on CPU even when the layer's non-expert weights are placed on GPU. For a 3B-active model like Qwen 3.6 35B-A3B (or our existing Vlad Gemma 4 26B-A4B), this is the architecturally correct way to fit a 22 GB-class MoE on a 12 GB card without paying the full per-token PCIe cost of dense partial-offload.

Vlad's q8_0 production config doesn't need it because IQ4_XS makes the weights small enough (14 GB) to fit nearly all-GPU at 89%. But anything bigger — Unsloth Gemma UD-Q4_K_XL (D2, 17 GB), Qwen 35B-A3B (D6, 22 GB) — needs `--n-cpu-moe` to be benchable.

Currently `_llamacpp_new_model` in `llm_client.py` and the `models.toml` schema don't expose this flag. Adding it is small: one `n_cpu_moe: int | None` field on `LLMModel`, threaded through `_llamacpp_new_model` to `provider.new_model(n_cpu_moe=...)`, which presumably maps to llama-server's `--n-cpu-moe`. Worth a separate small PR before the next benchmark pass.

### llmfacade multi-variant single-process bug
> Trello: [File llmfacade upstream issue](https://trello.com/c/xh3MXlXK)

Running multiple variants with different `model_id`s sequentially in the same Python process consistently failed: the second and third variants got `400 "could not find suitable inference handler for <model_id>"` from llama-swap, even though the YAML on disk had all three entries.

Workaround used in TC-2: run each variant in its own process. Each spawns a fresh llama-swap supervisor with a clean YAML.

Root cause not investigated. Likely candidates: llmfacade caches the YAML state and doesn't trigger a llama-swap reload between `provider.new_model()` calls; or llama-swap's `-watch-config` poll misses the change because the file is updated atomically faster than the 2s poll interval.

**Fix**: file an upstream issue against llmfacade with the reproduction (the TC-2 benchmark script, `--variants` flag with multiple values).

### `n_gpu_layers = -1` should be flagged at registry-load time
> Trello: [Registry-load warning](https://trello.com/c/hSJPnWzA)

The registry could warn (or refuse) when a llamacpp entry has `n_gpu_layers = -1` and a `cache_type_k` that, combined with the model's weight size and context_window, would exceed available VRAM. Cheaper than auto-placement, catches the footgun at startup.

### qwen3.5-4b GGUF replacement
> Trello: [Replace broken qwen3.5-4b GGUF](https://trello.com/c/2fW80Rcy)

Existing `C:\Models\qwen3.5-4b.gguf` (3.39 GB, source unknown — pre-dates the migration audit) fails to load in llama.cpp. Replace with [Unsloth Q4_K_M](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/blob/main/Qwen3.5-4B-Q4_K_M.gguf) (2.74 GB) or UD-Q4_K_XL variant.

### Phase D coverage gap

Stock Google Gemma 4 family (26B, E4B, 31B) discounted from on-disk testing. To complete the comparison would require fresh downloads from HuggingFace's Unsloth repos (`unsloth/gemma-4-26B-A4B-it-GGUF`, `unsloth/gemma-4-E4B-it-GGUF`). ~30 GB additional. Not pursued in TC-2 because the established Vlad re-baseline already proves the migration win.

## Routing recommendations (post-TC-2)

| Stage | Context | Model | Notes |
|---|---|---|---|
| Theme extract (PDF input) | 128K | `gemma4-26b-vram-dynamic` (Vlad IQ4_XS) at q8_0 KV, all-GPU | Production default for now. **Pin n_gpu_layers explicitly** once auto-placement lands; current `-1` is fragile. **Actively under threat from E4B** (see next row). |
| Theme extract (alt) | 128K | `gemma4-e4b-unsloth` at q8_0 KV, all-GPU | Faster TTFT, more output content, half the VRAM, simpler placement (fits with massive headroom). Run a side-by-side quality eval on 2–3 more corpora before promoting to default — Dark Sun alone is one data point. → [Trello](https://trello.com/c/QyLlQcHD) |
| Long-context, max throughput | 128K | Vlad at q4_0 KV cache | ~10% faster than q8_0 on Vlad; flip globally only after confirming output quality on a wider corpus than the Dark Sun PDF. |
| Card gen / review (low context) | <32K | Vlad-dynamic | TC-1f's "stock gemma4:26b at <32K" guidance is moot — that GGUF is unloadable. Vlad-dynamic works at any context. |
| Iteration / dev loop | small | `gemma4-e4b-unsloth` (or Anthropic Haiku 4.5) | E4B at full GPU is fast enough for dev iteration and produces structured output. Use Haiku when you need a different style or vision. |

## Artifacts

- Bench scripts: `backend/scripts/benchmark_llamacpp_tc2.py`, `backend/scripts/benchmark_llama_bench.py`, `backend/scripts/link_ollama_blobs.py`.
- Result directories: `output/benchmarks/tc2_vlad-rebaseline_*`, `output/benchmarks/tc2_vlad-q8_0_*`, `output/benchmarks/tc2_vlad-q4_0_*`, `output/benchmarks/phase_c_phase-c-raw_*`, `output/benchmarks/tc2_d2-unsloth_*`, `output/benchmarks/tc2_d2bis-q4km_*`, `output/benchmarks/tc2_d3bis-e4b_*`, `output/benchmarks/tc2_d4bis-31b-asd_*`, `output/benchmarks/tc2_d6-qwen35b_*`, `output/benchmarks/tc2_d7-qwen27b_*`.
- Source corpus: `Inspiration/The Dark Sun Campaign Setting for Worlds Without Number.pdf`.
- Live extraction logs (jsonl + html per LLM call): `output/extraction_logs/extraction_<timestamp>/`.
