# Gemma Repetition Loops - Research Notes

Researched: 2026-04-23

## Question
Is it a known issue that Gemma models go into repetition loops, and is it related to quantization?

## TL;DR
- **Yes, repetition loops are a documented and (for Gemma 3) officially acknowledged issue** across Gemma 3 and Gemma 4.
- **It is not purely a quantization artifact.** It reproduces on bfloat16 vLLM deployments and in Google's own reference Gemma repo, not just GGUF/Q4_K_M setups.
- Reported causes are a mix of: backend/kernel bugs, chat-template misuse, sampling settings (low temp, no repetition penalty), and framework version regressions. For Gemma 4 specifically, reporters claim even `repeat_penalty` does not help, suggesting a deeper pathology.

## Key Evidence

### 1. Google staff acknowledgement (Gemma 3 27B)
From the HuggingFace model card discussion [S3], a Google org account replied to a user getting repetitions at <10% context usage:

> "Even when only a small portion of the context window is used, this repetition issue still shows up and it's not just limited to the RTX 3090. With different hardware setups have reported similar problems."

Their suggested workarounds:
- Higher temperature
- Repetition penalty ~1.1
- Adjust Top-k / Top-p
- Upgrade runtime version

### 2. Open bugs in Google's own Gemma repo (Gemma 4)
- **Issue #610** [S1] - "Deterministic Repetition Loop at 14th item in list" on Gemma-4-26B-A4B: model endlessly prints `"Wait, I found it. The 14. I will provide the 14"` when listing Firefly episodes.
- **Issue #622** [S2] - "Token repetition collapse during long generation" affecting Gemma-4-31B Dense and 26B MoE: words double (`"the the waves"`, `"sapphire sapphire"`), then collapse into a single repeated token (`"own own own own..."`) that fills the remaining budget. Reporter: *"repeat_penalty has no effect - tested at 1.0, 1.15, and 1.5, identical seeds fail identically at all values."*

### 3. Cross-backend reports
| Backend | Issue | Symptom |
|---|---|---|
| vLLM | #15752 [S4] | Gemma-3-12B-it infinite repetitive loops; reproduces on MI300 but not H200 (hardware path dependent) |
| vLLM | #20341 [S5] | No output / repeated outputs on Gemma 3 12B/27B; Google staff blamed chat-template misuse; commenters fingered RoPE/attention handling in pre-0.4.x vLLM; reportedly fixed on vllm-openai:v0.10.0 |
| llama.cpp | #14835 [S6] | Regression (commit bf9087f) caused gemma-3-4b-it to generate infinite `"and"` |
| llama.cpp | #21516 [S8] | Gemma 4 generates infinite `<unused>` tokens on Vulkan backend |
| Ollama | #15502 [S7] | Gemma 4 31B repetition loop during constrained JSON generation with free-text string fields |

### 4. Quantization angle
- #15752 and #20341 ran **bfloat16** (`--dtype bfloat16`) - still repeats.
- #610 and #622 are in **Google's reference codebase**, not a quant fork.
- Quantized setups (Q4_K_M via LM Studio/Ollama) also show it, so quantization may amplify but is not the root cause.

## Mitigations to Try (in order of simplicity)

1. **Fix the chat template** - Gemma needs `<start_of_turn>user ... <end_of_turn> <start_of_turn>model`. Missing this is the #1 cited cause.
2. **Raise temperature** - Google staff's first recommendation. Try 0.7-1.0.
3. **Repetition penalty ~1.1** - Standard fix (but confirmed ineffective for Gemma 4 #622).
4. **Upgrade the runtime** - vLLM >=0.10.0, recent llama.cpp, latest LM Studio. Many threads resolved after an upgrade.
5. **Check hardware path** - MI300 vs H200 behaved differently in #15752; Vulkan backend broken in llama.cpp #21516. If you have a choice of backend, try CUDA/CPU.
6. **Avoid constrained JSON with long free-text fields on Gemma 4** (#15502, #622) - known failure mode.

## Implications for MTGAI
- If we're routing to Gemma 3/4 for any long-form or JSON-constrained generation, assume repetition loops are a live risk and design for detection + retry.
- Don't assume a higher-bit quant fixes it - the problem exists at bf16.
- Smaller Gemma 3 variants (1B, 4B) appeared less affected in #15752; worth considering for throughput paths if quality is sufficient.
- Consider a repetition-loop detector (e.g. "last N tokens are the same token" or "last N words form a cycle") as a cheap guard before accepting a generation.

## Sources

- [S1] https://github.com/google-deepmind/gemma/issues/610 - Gemma-4-26B-A4B deterministic repetition loop
- [S2] https://github.com/google-deepmind/gemma/issues/622 - Gemma 4 token repetition collapse (31B Dense + 26B MoE)
- [S3] https://huggingface.co/google/gemma-3-27b-it/discussions/53 - Google org staff acknowledgement of Gemma 3 repetition
- [S4] https://github.com/vllm-project/vllm/issues/15752 - Gemma-3-12B-it repetitive loops on vLLM
- [S5] https://github.com/vllm-project/vllm/issues/20341 - Gemma 3 no output / repeated outputs on vLLM
- [S6] https://github.com/ggml-org/llama.cpp/issues/14835 - gemma-3-4b-it infinite "and" regression
- [S7] https://github.com/ollama/ollama/issues/15502 - Gemma 4 31B repetition in constrained JSON
- [S8] https://github.com/ggml-org/llama.cpp/issues/21516 - Gemma 4 infinite `<unused>` tokens on Vulkan

## Gaps
- No explicit Google statement labeling this an "intrinsic" Gemma weakness; their public framing is "try sampling/runtime fixes."
- Gemma 4 issue #622 appears unresolved at time of research.
- Did not verify Gemma 1/2 (7B/9B) against primary sources; the question's "gemma models" scope here is Gemma 3 + Gemma 4.
