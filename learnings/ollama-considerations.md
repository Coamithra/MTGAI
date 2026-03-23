# Ollama + Qwen 2.5 Context Window Considerations

Research date: 2026-03-22

## Questions Investigated
- Is Qwen 2.5 14B ignoring the beginning of long prompts a known issue?
- Does Ollama's `num_ctx` actually work correctly with Qwen 2.5, and are there gotchas?
- What is the real effective context length for Qwen 2.5 14B vs. advertised?

## Findings

### 1. Ollama silently truncates from the beginning

When input exceeds `num_ctx`, Ollama **drops the oldest tokens from the front** with zero warning. There is no error, no log (unless `OLLAMA_DEBUG=1`), no API response field indicating truncation occurred.

- "ollama *silently* discards the leading context. So users have no idea that most of their data hasn't been provided to the model." [S1]
- "When a conversation's token count exceeds the model's context length, Ollama silently drops older messages from the front of the conversation." [S2]
- "the beginning of your conversation or the start of a long document just gets dropped" [S3]

The `truncate` parameter defaults to `true` -- so this is always happening unless you disable it. [S2]

### 2. Ollama's default `num_ctx` is much lower than you think

Ollama does **not** default to the model's advertised context window. The defaults are based on your VRAM:

- < 24 GiB VRAM: **4k** context
- 24-48 GiB VRAM: **32k** context
- >= 48 GiB VRAM: **256k** context

Source: [S4]

On a 12GB GPU, `num_ctx` defaults to **4096 tokens** -- not 32k. So when you send ~20k tokens, Ollama silently truncates ~16k from the beginning. The model genuinely never sees that text.

### 3. The OpenAI-compatible API silently ignores `num_ctx`

**Critical for our codebase.** `llm_client.py` uses the OpenAI-compatible endpoint (`/v1`), which **does not support** the `num_ctx` parameter:

- "The OpenAI API does not have a way of setting the context size for a model." [S5]
- Issue #5356 specifically requests: "allow for num_ctx parameter in the openai API compatibility" [S5]

`theme_extractor.py` already works around this by using the native `/api/chat` endpoint (line 793-794: "The OpenAI compatibility layer silently ignores `num_ctx`, so we must use Ollama's native `/api/chat` endpoint"). But `llm_client.py` does **not** -- it calls `/v1/chat/completions`, meaning `num_ctx` is stuck at the VRAM-based default (4k on 12GB GPU).

### 4. `num_ctx` multiplied by `OLLAMA_NUM_PARALLEL`

If `OLLAMA_NUM_PARALLEL` is set (or auto-detected), the actual VRAM allocated is `num_ctx * OLLAMA_NUM_PARALLEL`. With the default of 4 parallel slots, requesting 32k context actually allocates 128k tokens worth of KV cache -- which may not fit in VRAM, causing model layers to offload to CPU and tank performance. [S6]

- "OLLAMA_NUM_PARALLEL sets how many requests ollama can handle concurrently. Each request handler needs its own context space, so total context is (number of handlers * context size)." [S6]

### 5. "Lost in the middle" is a separate real phenomenon, but secondary here

Even when `num_ctx` is correctly set, LLMs (including Qwen 2.5) exhibit a U-shaped attention curve -- they attend best to the beginning and end of the context, worst to the middle.

- "Performance is often highest when relevant information occurs at the beginning or end of the input context, and significantly degrades when models must access relevant information in the middle of long contexts." [S7]
- "The 13B base model has a dramatic primacy and recency bias -- there is a 20-point accuracy disparity between the best- and worst-case performance." [S7]
- The root cause is RoPE (Rotary Position Embedding), which "introduces a long-term decay effect that causes models to prioritize tokens at the beginning and end of sequences." [S7]

However, the symptom of ignoring the **beginning** specifically points to truncation, not "lost in the middle." The LitM effect would cause the model to ignore the *middle* while retaining the beginning and end.

### 6. Qwen 2.5 14B's actual context capabilities

The standard Qwen 2.5 14B Instruct supports **128k tokens** natively (not just 32k). However:

- The base model config defaults to **32,768 tokens**; beyond that, it uses YaRN length extrapolation [S8]
- GGUF quantized versions may not support YaRN -- "only vLLM supports YARN for length extrapolating" [S9]
- The 1M-context variant requires **320GB VRAM** for full context; accuracy degrades above 262k tokens [S10]

For the 14B Q4 GGUF on 12GB VRAM, 32k is a reasonable practical ceiling.

### 7. `num_predict` defaults to 128 tokens

Ollama's default `num_predict` (max output tokens) is **128 tokens** -- not unlimited. This silently truncates model output mid-sentence. Long narrations, structured JSON tool calls, and multi-step reasoning all get cut off without any error or warning.

Set `num_predict: -1` in the `options` field to remove the output cap:
```json
"options": {"num_ctx": 32768, "num_predict": -1}
```

Like `num_ctx`, the OpenAI-compatible `/v1` endpoint uses `max_tokens` instead, but the native `/api/chat` endpoint requires `num_predict` in `options`.

### 8. Qwen-specific Ollama bugs

Multiple open issues document Qwen-specific problems in Ollama:

- Issue #4811: "Qwen model failed to recognize system prompt when context exceeded ~3000 characters, even when `num_ctx` was increased." Moving content from system to user prompt was a workaround. [S11]
- Issue #2580: "Qwen long context query produces garbage response" -- same 12k context worked in LM Studio but produced incoherent output in Ollama [S12]

## Recommended Fixes

1. **Set `OLLAMA_CONTEXT_LENGTH=32768`** as an environment variable when starting Ollama. This changes the server-wide default.

2. **In `llm_client.py`**: Switch the Ollama calls from the OpenAI-compatible `/v1` endpoint to the native `/api/chat` endpoint (like `theme_extractor.py` already does), so you can pass `num_ctx` per-request.

3. **Set `OLLAMA_NUM_PARALLEL=1`** to prevent the context multiplier from eating VRAM. On 12GB, you can't afford parallel slots with 32k context.

4. **Enable `OLLAMA_DEBUG=1`** temporarily to see if truncation is actually occurring -- the debug logs show when context is trimmed.

5. **Set `num_predict: -1`** in the native API `options` to remove the 128-token output cap. Without this, tool calls and long responses get silently truncated.

6. **Alternatively**, create a custom Modelfile:
   ```
   FROM qwen2.5:14b
   PARAMETER num_ctx 32768
   ```
   Then `ollama create qwen2.5-32k -f Modelfile` -- this makes 32k the persistent default for that model.

## Gaps and Uncertainties

- No specific benchmarks found for Qwen 2.5 14B GGUF at exactly 20-32k context in Ollama (most reports are at extremes -- either default or 128k+)
- The exact interaction between GGUF quantization and YaRN/RoPE scaling for Qwen 2.5 in llama.cpp (which Ollama uses) is not well-documented
- Whether Ollama's `OLLAMA_FLASH_ATTENTION` helps with quality (not just speed) at longer contexts is unclear
- The Qwen-specific bugs (issues #4811, #2580) may or may not still be present in current Ollama versions

## Sources
- [S1] [HN discussion on num_ctx defaults](https://news.ycombinator.com/item?id=42833427)
- [S2] [Issue #4967: API silently truncates conversation](https://github.com/ollama/ollama/issues/4967)
- [S3] [Arsturn: Token context limit behavior](https://www.arsturn.com/blog/what-happens-when-you-exceed-the-token-context-limit-in-ollama)
- [S4] [Ollama docs: Context length](https://docs.ollama.com/context-length)
- [S5] [Issue #5356: num_ctx in OpenAI API compatibility](https://github.com/ollama/ollama/issues/5356)
- [S6] [Issue #6927: n_ctx 4x num_ctx multiplier](https://github.com/ollama/ollama/issues/6927)
- [S7] [Lost in the Middle paper (Liu et al.)](https://arxiv.org/abs/2307.03172)
- [S8] [Qwen 2.5-14B HuggingFace model card](https://huggingface.co/Qwen/Qwen2.5-14B)
- [S9] [Qwen quantization benchmarks](https://qwen.readthedocs.io/en/v2.5/benchmark/quantization_benchmark.html)
- [S10] [Qwen2.5-14B-Instruct-1M model card](https://huggingface.co/Qwen/Qwen2.5-14B-Instruct-1M)
- [S11] [Issue #4811: Qwen long text problem](https://github.com/ollama/ollama/issues/4811)
- [S12] [Issue #2580: Qwen long context garbage](https://github.com/ollama/ollama/issues/2580)
