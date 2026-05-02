# OLLAMA_KV_CACHE_TYPE quality impact (q4_0 vs f16)

Context: we run `OLLAMA_KV_CACHE_TYPE=q4_0` to keep `vlad-gemma4-26b-dynamic` mostly on GPU at 128K context (see CLAUDE.md, "Local LLM Notes"). q4_0 buys ~3× KV-cache shrink vs the default f16, but the obvious worry is whether it costs us output quality. This note collects what's actually been measured.

## TL;DR

- **q8_0 is universally safe** — every tested model loses < 0.05 perplexity vs f16. If we ever drop into doubt mode, fall back to q8_0 (still halves KV vs f16).
- **q4_0 is architecture-dependent**, ranging from lossless (hybrid attention) to catastrophic (Qwen 2.5).
- **Gemma 4 is in the favorable bucket** by architectural class (alternating sliding-window + global attention, shared KV cache). No direct PPL benchmark exists for Gemma 4 26B-A4B at q4_0, but the architectural argument is strong and matches what we observe (correct-looking 7-section extractions, no quality regression noted).
- **Don't blanket-apply q4_0 to non-Gemma models** without checking — Qwen 2.5 7B with q4_0 KV produces complete garbage (PPL 1378 vs 10.4 baseline).

## Measured perplexity (WikiText-2, Tesla P40, [S2])

| Model | f16 | q8_0 (Δ) | q4_0 (Δ) |
|---|---|---|---|
| Llama 3.2 3B | 14.5842 | 14.5766 (−0.008) | **15.3082 (+0.724)** |
| Llama 3.1 8B | 9.8488 | 9.8541 (+0.005) | **10.1181 (+0.269)** |
| Qwen 2.5 7B | 10.3707 | 10.4225 (+0.052) | **1378.89 (catastrophic — K projection bias)** |
| Qwen 3.5 9B (hybrid) | 9.7554 | 9.7572 (+0.002) | **9.7901 (+0.035)** |
| Gemma 4 27B | OOM | (test rig incompatible) | (test rig incompatible) |

Standard dense transformers (Llama) lose meaningful quality. Hybrid Qwen 3.5 is essentially lossless. Qwen 2.5 explodes — high-GQA models are flagged as sensitive [S1]. Gemma 4 27B couldn't be measured by this rig.

PR-author general estimates [S1]: q8_0 adds ~0.002–0.05 PPL; q4_0 adds ~0.21–0.25 PPL on average.

## Why hybrid models survive q4_0

From llama.cpp issue #21385 [S3]:

> "q4_0 KV cache is completely lossless on hybrid models (Qwen3.5) — BLEU 1.000 across 10 test configurations at 4x compression"

Mechanism (direct quote):

> "The linear/sliding attention layers act as error correction — quantization noise in the few attention layers is absorbed by the surrounding layers."

> "Standard models (Llama, Mistral) have no such correction because all layers use full attention."

Qwen 3.5 only uses 8 of 32 layers for full attention with KV cache; the remaining 24 are linear attention with no KV cache, so quantization noise has very few entry points and the surrounding layers absorb what does enter.

## Why Gemma 4 should follow the same pattern

Gemma 4 alternates local sliding-window and global full-context attention layers and uses a shared KV cache where later layers reuse K/V from earlier layers of the same attention type [S4]. Per the same source:

> "the architecture designed with quantization in mind from the start—the alternating attention, shared KV cache, and MoE sparsity all make the model more tolerant of reduced numerical precision than dense transformers with standard attention"

This puts Gemma 4 architecturally in the same class as Qwen 3.5 — the class that was empirically lossless under q4_0. The "Gemma 4 q4_0 is fine" conclusion is **by architectural analogy**, not by direct measurement.

## Sensitivity flags to remember

- **Embedding models**: don't quantize KV at all [S1].
- **High-GQA models** (Qwen 2 family explicitly): "may see a larger impact on precision from quantization than models with a low GQA count" [S1]. Qwen 2.5 7B is the catastrophic case in [S2].
- **Vision/multi-modal**: similar sensitivity warnings [S1].
- **Standard dense transformers** (Llama, Mistral): expect +0.2–0.7 PPL. Usable for casual generation, not ideal for structured/JSON output where precision matters.

## Open questions / what we haven't measured

- No direct PPL/BLEU for `vlad-gemma4-26b-dynamic` (IQ4_XS weights + q4_0 KV). Architectural inference only.
- The MoE sparsity contribution (A4B = 4B active of 26B total) isn't isolated in any benchmark we found.
- No long-context-specific quality study. Theory says q4_0 noise is per-token-independent so doesn't accumulate, but no one has empirically tested quality at 128K context for our exact setup.
- Task-class sensitivity (creative vs. structured JSON vs. tool calling) isn't quantified anywhere we found, only hand-waved.

If a future regression turns up — degraded JSON validity, weird extraction output, repetition loops that aren't fixed by `repeat_penalty=1.1` — flip `OLLAMA_KV_CACHE_TYPE` to `q8_0` as a first diagnostic. Halves the KV cache vs f16 (still helps placement) and is universally near-lossless.

## Sources

- [S1] https://smcleod.net/2024/12/bringing-k/v-context-quantisation-to-ollama/ — Blog post by Sam McLeod (author of the Ollama KV-cache-quantization PR), with PPL deltas and recommendations
- [S2] https://gist.github.com/mverrilli/dbd9935bdec44495e635a3c5cdf611d0 — WikiText-2 PPL sweep across 5 models on Tesla P40, raw f16/q8_0/q4_0 numbers
- [S3] https://github.com/ggml-org/llama.cpp/issues/21385 — llama.cpp issue on per-head adaptive KV quantization; BLEU=1.000 finding for hybrid models
- [S4] https://huggingface.co/blog/gemma4 — Gemma 4 architecture: alternating sliding/global attention, shared KV cache, designed for quantization
