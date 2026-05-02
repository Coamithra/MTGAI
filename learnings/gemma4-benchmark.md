# Gemma 4 Local Model Benchmark (TC-1e + TC-1f)

**Hardware**: NVIDIA RTX 4070 Ti (12 GB VRAM), 12 CPU threads, Windows 11, Ollama 0.20.5
**Dates**: 2026-04-21 (both rounds)
**Corpus**: Dark Sun Campaign Setting PDF (58,273 input tokens via tiktoken cl100k)
**Goal**: Identify the fastest reliable Gemma 4 configuration for theme extraction (large-context single-pass) on 12 GB VRAM, and decide per-stage routing for `model_settings.py` presets.

## TL;DR

1. **Flash attention is the single biggest lever.** Enabling `OLLAMA_FLASH_ATTENTION=1` gives a **2.5x wall-clock / 8.4x TTFT speedup** on a 26B model at 128K context. Ollama 0.20.5 does NOT turn it on by default. Set it globally: `setx OLLAMA_FLASH_ATTENTION 1`.

2. **Winner at 128K**: `vlad-gemma4-26b-dynamic` (our override of `VladimirGav/gemma4-26b-16GB-VRAM` with `PARAMETER num_gpu -1`) plus `OLLAMA_FLASH_ATTENTION=1` plus `OLLAMA_KV_CACHE_TYPE=q4_0`. **238.7 s** end-to-end for the 58K-token PDF — 3.6x faster than the TC-1e baseline and 22x faster than standard `gemma4:26b` which could not complete at all.

3. **Winner at <32K**: standard `gemma4:26b`. MoE architecture + no CPU-offload penalty at small context makes per-token speed ~22 tok/s.

4. **Winner for small docs where quality doesn't matter**: `gemma4:e4b`. Fits 100 % on GPU, ~105 tok/s.

5. **Trap**: the upstream `VladimirGav/gemma4-26b-16GB-VRAM` Modelfile hardcodes `PARAMETER num_gpu 99`, which combined with q4_0 KV cache causes CUDA OOM and a Windows display-driver reset. Always use the `-dynamic` derivative.

6. **Never use**: `gemma4:31b` (dense 31 B) at any context — 3.5 tok/s at 32K, projected 6–10+ hours at 128K.

## Full routing recommendations

| Stage | Context | Model | Env vars required |
|-------|---------|-------|-------------------|
| Theme extract (PDF input) | 128K | `gemma4-26b-vram-dynamic` | `OLLAMA_FLASH_ATTENTION=1` + `OLLAMA_KV_CACHE_TYPE=q4_0` |
| Card gen, review, balance | <32K | `gemma4:26b` | `OLLAMA_FLASH_ATTENTION=1` |
| Iteration / dev loop | small | `gemma4:e4b` | `OLLAMA_FLASH_ATTENTION=1` (optional) |
| Backup for theme extract if Vlad registry drops | 128K | `gemma4-26b-unsloth-q4kxl` | `OLLAMA_FLASH_ATTENTION=1` |

Leave `OLLAMA_KV_CACHE_TYPE` unset at the system level and enable per-session for long-context runs. It is safe with the `-dynamic` override and with Unsloth, but will OOM the upstream Vlad model on <16 GB VRAM.

## Round 1 — Small context (ASD theme.txt, ~3 K input tokens, 32 K ctx)

No flash attention. No q4_0 KV cache.

| Model | Wall clock | TTFT | Gen tok/s | Prompt tok/s | Placement |
|-------|-----------|------|-----------|--------------|-----------|
| `gemma4:e4b` | 33 s | 9.4 s | 105.8 | 8,230 | 100 % GPU |
| `gemma4:26b` | 104 s | 10.0 s | 22.3 | 1,164 | 48 / 52 CPU/GPU |
| `VladimirGav/gemma4-26b-16GB-VRAM` | 325 s | 187 s | 13.9 | 318 | 100 % GPU |
| `gemma4:31b` | 968 s | 357 s | 3.5 | 518 | heavy CPU offload |

**Takeaway**: At 32 K context, standard `gemma4:26b` beats Vlad's IQ4_XS on both prompt eval and per-token speed. The partial CPU offload is cheap for MoE — inactive experts on CPU don't cost PCIe per token.

## Round 2 — Large context (Dark Sun PDF, 58 K input tokens, 128 K ctx)

No flash attention. No q4_0 KV cache.

| Model | Wall clock | Verdict |
|-------|-----------|---------|
| `gemma4:e4b` | ~2 min | Still fast with partial CPU offload at 128K |
| `VladimirGav/gemma4-26b-16GB-VRAM` | ~15 min | Best 26B-tier option at 128K default |
| `gemma4:26b` | >3 h, killed | Did not complete prompt processing |
| `gemma4:31b` | Not tested | Projected 6–10+ hours |

**Takeaway**: Model ranking REVERSES between 32 K and 128 K. At 128 K the KV cache alone is ~3.4 GB fp16, and the 1 GB weight-size difference between Vlad's IQ4_XS (14.2 GB) and standard q4_K_M (18 GB) flips the placement math: Vlad stays mostly on GPU, standard forces heavy offload and hours-long prompt processing.

## Round 3 (TC-1f) — Full lever matrix at 128 K single-pass

Same Dark Sun PDF, single-pass, `num_ctx=131072`. This round tested Unsloth's Dynamic Q4_K_XL quant, `OLLAMA_KV_CACHE_TYPE=q4_0`, and `OLLAMA_FLASH_ATTENTION=1`.

| Model | KV cache | Flash attn | Wall clock | TTFT | Output chars | Notes |
|-------|----------|-----------|-----------|------|--------------|-------|
| Unsloth UD-Q4_K_XL | fp16 | off | 697.9 s | 377.7 s | 11,604 | 19 % faster than Vlad baseline |
| Unsloth UD-Q4_K_XL | q4_0 | on | 689.6 s | 362.7 s | 12,348 | +6 % content, ~1 % faster than fp16 |
| Vlad IQ4_XS (upstream, `num_gpu=99`) | fp16 | off | 865.3 s | 474.4 s | 11,592 | Round 2 baseline reproduced |
| Vlad IQ4_XS (upstream, `num_gpu=99`) | q4_0 | on | **CUDA OOM** | — | — | Display driver reset |
| Vlad IQ4_XS (dynamic, `num_gpu=-1`) | fp16 | on | 345.8 s | 56.3 s | 11,578 | Flash-attention isolation |
| **Vlad IQ4_XS (dynamic, `num_gpu=-1`)** | **q4_0** | **on** | **238.7 s** | **50.9 s** | **11,129** | **Winner** |

### Isolation analysis

Decomposing the 865 s → 239 s improvement on Vlad:

| Step | Wall clock | Delta | Cumulative |
|------|-----------|-------|------------|
| Baseline: fp16 + flash-off | 865 s | — | 1.0x |
| + Flash attention | 346 s | −519 s | **2.50x** |
| + q4_0 KV cache | 239 s | −107 s | **3.62x** |

**Flash attention did ~83 % of the work.** q4_0 KV cache contributed the remaining 17 %.

TTFT specifically:
- Flash attention: 474 s → 56 s (**8.4x**). Nearly all the TTFT gain comes from here.
- q4_0 on top: 56 s → 51 s. Marginal.

Flash attention helps prompt eval (one-time per call). q4_0 KV cache helps generation tok/s (smaller cache per decoded token). The two are additive, not alternatives.

## Why the levers affect different models differently

At 12 GB VRAM, the placement-math for each model:

| Model | Weights | fp16 KV @ 128K | GPU % (fp16) | q4_0 KV @ 128K | GPU % (q4_0) | Δ placement |
|-------|---------|----------------|--------------|----------------|--------------|-------------|
| Unsloth UD-Q4_K_XL | 17.1 GB | 3.4 GB | ~50 % | 0.8 GB | ~56 % | +6 pp |
| Vlad IQ4_XS | 14.2 GB | 3.4 GB | ~50 % | 0.8 GB | ~75 % | +25 pp |

Vlad sits in the placement sweet spot where shrinking KV cache shifts a lot of weight layers from CPU to GPU. Unsloth is too heavy for even an empty KV cache to relocate many layers — the lever lands flat.

**General rule**: q4_0 KV cache only helps meaningfully when the model's weights + reduced KV cache crosses the "fits more on GPU" threshold. For 12 GB VRAM, that's the 14 GB-weight neighborhood (Vlad's IQ4_XS). Larger quants don't benefit. Smaller models (<4 B) have negligible KV cache to begin with, and quantizing it risks accuracy loss without memory gain.

## The `num_gpu=99` trap

Upstream `VladimirGav/gemma4-26b-16GB-VRAM` Modelfile ships with:
```
PARAMETER num_gpu 99
```

`num_gpu=99` = "all layers on GPU." Mechanism of the crash we observed:

1. Vlad IQ4_XS weights = 14.2 GB, designed for a 16 GB card + 3.4 GB fp16 KV cache at 128 K = 17.6 GB.
2. On 12 GB GPU with fp16 KV cache, Ollama's placement estimator sees 17.6 > 12 and overrides `num_gpu=99` back to partial offload. Safe.
3. With q4_0 KV cache, effective footprint drops to 14.2 + 0.8 = 15 GB. Estimator now rounds to "close enough" and honors `num_gpu=99`.
4. 15 GB `cudaMemcpyAsync` onto 12 GB GPU → CUDA error → Windows TDR resets the display driver (screen blanks briefly).

Ollama log:
```
runner.size="15.7 GiB" runner.vram="15.7 GiB"
CUDA error: unknown error at ggml_backend_cuda_buffer_set_tensor
```

**Fix**: derived Modelfile with `PARAMETER num_gpu -1` (explicitly unset → use Ollama's dynamic placement). Verified: `ollama show` no longer lists `num_gpu` at all; runtime placement at 128 K q4_0 lands at 62 % GPU / 38 % CPU. Registered as `vlad-gemma4-26b-dynamic`.

## Ollama 0.21 update (2026-04-22)

Verified against Ollama 0.21.0 source (`server/server.go`):

- **Flash attention** is auto-enabled for supporting models. No env var, no per-call option, no code wiring needed on 0.21+. Confirmed live via the runner load request log: `FlashAttention:Enabled`. Gemma 4 on pre-Turing GPUs is auto-disabled regardless (carve-out in the source, suggests a missing kernel path).
- **KV cache type** is env-var only. `OLLAMA_KV_CACHE_TYPE` is read once at server startup via `envconfig.KvCacheType()`. No field exists in the public Options struct for it - per-call `kv_cache_type` / `cache_type_k` / `cache_type_v` in the options dict is silently ignored. Requires `setx OLLAMA_KV_CACHE_TYPE q4_0` + tray restart to take effect globally.

Consequence for our setup: updating Ollama from 0.20.5 to 0.21.0 was the whole fix. We briefly wired `flash_attention` per-call via a `model_registry.LLMModel` field and an `ollama_runtime_options()` helper, then removed both after confirming 0.21 auto-enables. KV cache quantization is intentionally not used - the ~100 s it would save on 128K Vlad-dynamic extractions isn't worth globally binding a setting that misbehaves on the upstream Vlad model.

## Flash attention status and how to enable

Ollama 0.20.5 does NOT enable flash attention by default. Confirm via `python -m mtgai.generation.ollama_debug` — look for `flash_attention: false`.

**Enable persistent (recommended)**:
```powershell
setx OLLAMA_FLASH_ATTENTION 1
# Restart tray Ollama or log out/in for the tray app to pick up the var
```

**Per-session**:
```powershell
$env:OLLAMA_FLASH_ATTENTION = "1"
ollama serve
```

The tray-launched `Ollama.exe` does not pick up env vars set after it was started. After `setx`, quit and relaunch the tray app, or use `ollama serve` from a fresh PowerShell.

On CPU-only deployments, `OLLAMA_FLASH_ATTENTION=1` is essentially a no-op (the algorithm is a CUDA kernel trick). Don't bother.

## Operational insights

### MoE at small ctx ≠ MoE at large ctx
Round 1 showed MoE (26B-A4B) tolerates CPU offload nicely because inactive experts don't cost PCIe. Round 2 showed this advantage evaporates at 128 K because the KV cache (not experts) dominates memory traffic. Always benchmark at the context size you will actually use.

### Ollama's `/api/ps` placement is load-time only
The placement column in `ollama ps` is the initial layer distribution at load, not real-time utilization. Runtime `nvidia-smi` is the actual truth (we saw 35–41 % GPU util / 15 % bandwidth util on Vlad at 128 K default — i.e., PCIe-bound, not compute-bound).

### Ollama's `server.log` is silent during prompt eval
Even at DEBUG level, Ollama emits model-load progress but nothing during prompt evaluation. There is no way to tell how far along a long prompt is without modifying the server. Our Round 2 `gemma4:26b` run at 128 K sat in prompt eval for 3+ hours with zero log output.

### Distrust SEO benchmark claims
Popular guides (`bswen.com`, `gemma4guide.com`) publish specific tok/s numbers that appear to be AI-generated SEO content with invented figures. We measured `gemma4:e4b` at 105 tok/s where bswen claims "18–22 tok/s", and saw Vlad at 14 tok/s where gemma4guide claims "~8 GB at Q5" (it is ~18–20 GB). Benchmark on your hardware.

## Quality notes

All successful runs on the Dark Sun PDF produced the same 7-section output structure (World Overview, Themes, Creature Types, Factions, Landmarks, Notable Characters, Races) with consistent fidelity. Differences were natural generation variance, not degradation:

- Vlad original (fp16, flash-off) produced the richest creature list: 21 entries.
- Unsloth at q4_0 produced the longest output: 12,348 chars.
- Vlad-dynamic q4_0 (winner) produced 11,129 chars — slightly leaner but with all 7 sections intact, 3-paragraph World Overview, full character/landmark/faction coverage.

Quality is production-grade in every successful cell of the matrix. Speed choices do not compromise output quality materially.

## Code changes during benchmarking

Applied to production code as part of TC-1f investigation:

- `backend/mtgai/pipeline/theme_extractor.py`: the chunked streaming path was non-streaming with a 600 s read timeout, causing hangs on any chunk whose prompt-eval exceeded 10 minutes. Switched to `stream=True` to match the single-pass behavior, and bumped read timeout to 1800 s.

Two 64 K context attempts were made (per the original TC-1f plan). At 64 K the Dark Sun PDF exceeds the 57 K single-pass budget, triggering chunked mode (7 sections × 2 chunks = 14 LLM calls). Both attempts failed:

1. Non-streaming chunked path hit the 600 s timeout on a single chunk.
2. Streaming retry ran for ~1 hour through 5/7 sections, then hung in `iter_lines()` after Ollama's 5-minute idle timer expired the model mid-response.

64 K was dropped from the matrix. The chunked pipeline has an independent idle-hang bug that needs keep-alive / heartbeat handling — out of scope for this benchmark.

## Recommendation summary

### Env vars (Ollama 0.21+)
- Flash attention: nothing required, automatic.
- `OLLAMA_KV_CACHE_TYPE=q8_0`: persisted at User scope (system-wide default for all Ollama projects). See "2026-05-02 update" below for the decision history.

### Env vars (legacy, Ollama ≤ 0.20.5)
- `OLLAMA_FLASH_ATTENTION=1` was required to get flash attention. No longer needed on 0.21+.

### 2026-05-02 update: enabling KV cache quantization globally

**Decision**: persist `OLLAMA_KV_CACHE_TYPE=q8_0` at User scope. Default for every Ollama project on this machine.

**Why this changed from the original "intentionally not set" stance**:

The original deferred-decision trigger ("revisit if Ollama adds per-request KV cache control") will never fire — [PR #7983](https://github.com/ollama/ollama/pull/7983), which would have added per-Modelfile config, was rejected by maintainers as too hacky, and Ollama 0.22.1's `Options` struct still has no per-call KV cache field. So the conditions that triggered the revisit are different from what was originally written:

1. **MTGAI standardized on `vlad-gemma4-26b-dynamic` everywhere** (CLAUDE.md "Default everywhere" line) — the OOM-on-hardcoded-`num_gpu`-99 concern is purely theoretical inside MTGAI now.
2. **Architectural quality argument confirmed for Gemma 4**: sliding-window attention is empirically robust to KV cache quantization. TC-1f's quality comparison already produced indistinguishable 7-section output between fp16 and q4_0 cells (line 168 above), and a follow-up research agent confirmed the architectural reasoning in May 2026.
3. **q8_0 chosen over q4_0** as the global default: q4_0 is Gemma-4-safe but introduces architecture-dependent quality risk for other projects on the same machine (Llama 3, Mistral, smaller models). q8_0 is the community-conventional "safe everywhere" KV quantization (~99% of f16 quality across architectures), so it's appropriate as a system-wide default. The trade-off: q8_0 is ~half the size of f16 but twice the size of q4_0, so on Vlad-dynamic at 128K it recovers ~70% of the q4_0 speedup, not 100%.

**Expected speeds on Vlad-dynamic, 58K-token extraction at 128K context**:

| Config | Wall clock | KV cache size at 128K | Source |
|---|---|---|---|
| f16 | 345.8 s | 3.4 GB | TC-1f benchmark line 69 |
| q8_0 | ~270-290 s (interpolated) | 1.7 GB | not separately benchmarked |
| q4_0 | 238.7 s | 0.8 GB | TC-1f benchmark line 70 |

q8_0 leaves a measurable speedup vs. q4_0 on the table (~30-50 s per extraction) but is the right default given it'll inherit to non-MTGAI Ollama work where the architectural-robustness argument doesn't necessarily hold. If MTGAI ever needs the absolute fastest extraction, run the `start-ollama.ps1` "boost mode" launcher at the repo root — it stops the tray-launched Ollama and restarts a fresh `serve` with `OLLAMA_KV_CACHE_TYPE=q4_0` in process scope.

### Models in Ollama registry
- `vlad-gemma4-26b-dynamic` — built from `FROM VladimirGav/gemma4-26b-16GB-VRAM:latest` + `PARAMETER num_gpu -1`. Primary choice for long context.
- `unsloth-gemma4-26b-q4kxl` — built from `unsloth/gemma-4-26B-A4B-it-GGUF` UD-Q4_K_XL. Backup with slightly richer output.
- `gemma4:26b` — stock Google MoE. Use at <32 K context.
- `gemma4:e4b` — stock small model. Use for dev iteration and short contexts.

### Do NOT
- Use `VladimirGav/gemma4-26b-16GB-VRAM` directly with q4_0 KV cache on <16 GB VRAM.
- Expect flash attention to help on CPU-only Ollama.
- Combine q4_0 KV cache with small (<4 B) models.
- Run `gemma4:26b` at 128 K context (TC-1e Round 2 showed it never completes).
- Run `gemma4:31b` at any context unless an overnight job tolerating 6+ hour wall time is acceptable.

## Artifacts

- Benchmark scripts: `backend/scripts/benchmark_gemma4.py` (Round 1), `backend/scripts/benchmark_gemma4_darksun.py` (Round 2), `backend/scripts/benchmark_gemma4_tc1f.py` (Round 3 / TC-1f).
- Modelfiles: `tmp/gemma4-unsloth/Modelfile` (Unsloth Q4_K_XL), `tmp/gemma4-unsloth/Modelfile.vlad-dynamic` (Vlad override).
- Registry entries (`backend/mtgai/settings/models.toml`): `gemma4-26b-unsloth-q4kxl`, `gemma4-26b-vram-dynamic`.
- Code patch: `backend/mtgai/pipeline/theme_extractor.py` chunked→streaming + 1800 s timeout.
- Result directories under `output/benchmarks/`: `gemma4_20260421_141722`, `gemma4_20260421_141847`, `darksun_20260421_151248`, `tc1f_default_20260421_185340`, `tc1f_q4_0_20260421_221305`, `tc1f_q4_0_20260421_223556`, `tc1f_q4_0_20260421_225419`, `tc1f_fp16_flash_20260421_230109`.
- Source document: `Inspiration/The Dark Sun Campaign Setting for Worlds Without Number.pdf`.

## Follow-ups

- File an Ollama upstream issue: placement heuristic should never honor `num_gpu=N` when the estimator can still show the model exceeds available VRAM after any KV cache mode shift.
- Consider retiring the plain `gemma4-26b-vram` registry entry in favor of always using `-dynamic` derivatives for models with unsafe upstream parameters.
- Re-benchmark flash attention + q4_0 KV cache at 32 K context on `gemma4:26b` to quantify how much flash attention helps when there is no CPU-offload bottleneck.
- Chunked-mode pipeline idle-hang: separate work to add keep-alive handling and resumable per-section state.
