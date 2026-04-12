"""Token counting and context budget utilities.

Uses tiktoken (cl100k_base encoding) as an approximation for all models.
This is ~10-30% off for non-OpenAI models (Gemma, Qwen, etc.) but good
enough for context budget calculations with a safety margin.

NOTE: Ollama has an open PR (#12030) for a native /api/tokenize endpoint
that would give exact model-specific token counts. When that merges, this
module should be upgraded to use it for Ollama models.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

# Lazy-loaded tiktoken encoder
_encoder = None

# Safety margin: reserve this fraction of context to account for tiktoken
# approximation error and Ollama overhead (chat template tokens, etc.)
SAFETY_MARGIN = 0.05  # 5%

# Tokens per image estimate (Ollama vision models)
TOKENS_PER_IMAGE = 1600


class ContextOverflowError(Exception):
    """Raised when input would exceed the model's context window."""

    def __init__(self, message: str, estimated_tokens: int, available_tokens: int):
        super().__init__(message)
        self.estimated_tokens = estimated_tokens
        self.available_tokens = available_tokens


class InputTruncatedError(Exception):
    """Raised when Ollama silently truncated the input."""

    def __init__(self, message: str, expected_tokens: int, actual_tokens: int):
        super().__init__(message)
        self.expected_tokens = expected_tokens
        self.actual_tokens = actual_tokens


class OutputTruncatedError(Exception):
    """Raised when model output was cut off by the token limit."""

    def __init__(self, message: str, eval_count: int, num_predict: int):
        super().__init__(message)
        self.eval_count = eval_count
        self.num_predict = num_predict


def _get_encoder():
    """Lazy-load the tiktoken encoder."""
    global _encoder
    if _encoder is None:
        import tiktoken

        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken cl100k_base.

    Returns approximate count. For Gemma/Qwen models this will be
    ~10-30% off, but consistent and fast.
    """
    try:
        return len(_get_encoder().encode(text))
    except Exception:
        # Fallback: ~4 chars per token for English
        logger.debug("tiktoken encode failed, using chars//4 heuristic")
        return len(text) // 4


def count_messages_tokens(
    messages: list[dict],
    tools: list[dict] | None = None,
) -> int:
    """Estimate total token count for a chat request.

    Counts all message content plus tool schema JSON. Adds a small
    overhead per message for chat formatting tokens.
    """
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += count_tokens(content)
        elif isinstance(content, list):
            # Multimodal content blocks
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        total += count_tokens(block.get("text", ""))
                    elif block.get("type") == "image":
                        total += TOKENS_PER_IMAGE
        total += 4  # per-message overhead (role, formatting)

    if tools:
        total += count_tokens(json.dumps(tools))

    return total


def get_context_window(model: str) -> int:
    """Look up context window for a model from the registry."""
    try:
        from mtgai.settings.model_registry import get_registry

        info = get_registry().get_llm_by_model_id(model)
        if info:
            return info.context_window
    except Exception:
        pass
    return 32768  # conservative default


def available_for_input(
    model: str,
    system_prompt: str,
    output_reserve: int = 4096,
    tools: list[dict] | None = None,
) -> int:
    """Calculate tokens available for user content.

    Subtracts system prompt, tool schema, output reserve, and safety
    margin from the model's context window.
    """
    ctx = get_context_window(model)
    used = count_tokens(system_prompt)
    if tools:
        used += count_tokens(json.dumps(tools))
    safe_ctx = int(ctx * (1 - SAFETY_MARGIN))
    available = safe_ctx - used - output_reserve
    return max(0, available)


def check_pre_call(
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    output_reserve: int = 4096,
) -> None:
    """Check if a request will fit in context BEFORE sending it.

    Raises ContextOverflowError if the estimated input exceeds the
    available context budget.
    """
    ctx = get_context_window(model)
    estimated = count_messages_tokens(messages, tools)
    safe_budget = int(ctx * (1 - SAFETY_MARGIN)) - output_reserve

    if estimated > safe_budget:
        raise ContextOverflowError(
            f"Input too large for {model}: ~{estimated} tokens estimated, "
            f"but only {safe_budget} available "
            f"(context={ctx}, output_reserve={output_reserve}, "
            f"safety_margin={SAFETY_MARGIN:.0%})",
            estimated_tokens=estimated,
            available_tokens=safe_budget,
        )

    utilization = estimated / ctx * 100
    if utilization > 80:
        logger.warning(
            "High context utilization for %s: ~%d/%d tokens (%.0f%%)",
            model,
            estimated,
            ctx,
            utilization,
        )
    else:
        logger.debug(
            "Context budget OK for %s: ~%d/%d tokens (%.0f%%)",
            model,
            estimated,
            ctx,
            utilization,
        )


def check_post_call(
    response_data: dict,
    estimated_input_tokens: int,
    model: str,
    num_predict: int | None = None,
) -> None:
    """Check an Ollama response for signs of truncation.

    Raises InputTruncatedError or OutputTruncatedError if truncation
    is detected.

    Args:
        response_data: Raw Ollama /api/chat response dict.
        estimated_input_tokens: Our tiktoken estimate of input tokens.
        model: Model name for error messages.
        num_predict: The num_predict value sent in the request (if any).
    """
    prompt_eval = response_data.get("prompt_eval_count", 0)
    eval_count = response_data.get("eval_count", 0)
    done_reason = response_data.get("done_reason", "")

    # --- Input truncation detection ---
    # If Ollama processed significantly fewer tokens than we estimated,
    # the input was silently truncated from the front.
    # Allow 30% tolerance because tiktoken counts differ from model tokenizer.
    if prompt_eval > 0 and estimated_input_tokens > 0:
        ratio = prompt_eval / estimated_input_tokens
        if ratio < 0.6:
            raise InputTruncatedError(
                f"Ollama [{model}] likely truncated input: processed {prompt_eval} "
                f"prompt tokens but we estimated ~{estimated_input_tokens}. "
                f"Ratio: {ratio:.2f} (expected ~0.7-1.3). "
                f"The model may have silently dropped the beginning of your input. "
                f"Reduce input size or increase num_ctx.",
                expected_tokens=estimated_input_tokens,
                actual_tokens=prompt_eval,
            )
        elif ratio < 0.7:
            logger.warning(
                "Ollama [%s] token count mismatch: %d processed vs ~%d estimated (ratio %.2f). "
                "Possible partial truncation - verify output quality.",
                model,
                prompt_eval,
                estimated_input_tokens,
                ratio,
            )

    # --- Output truncation detection ---
    # done_reason="length" means the model hit the token limit
    if done_reason == "length":
        raise OutputTruncatedError(
            f"Ollama [{model}] output was truncated (done_reason=length). "
            f"Generated {eval_count} tokens before hitting the limit. "
            f"Increase num_predict or reduce input to leave more room for output.",
            eval_count=eval_count,
            num_predict=num_predict or -1,
        )

    # Also check if eval_count hit num_predict exactly (another truncation signal)
    if num_predict and num_predict > 0 and eval_count >= num_predict:
        raise OutputTruncatedError(
            f"Ollama [{model}] output likely truncated: generated exactly "
            f"{eval_count} tokens (num_predict={num_predict}). "
            f"Increase num_predict to allow longer output.",
            eval_count=eval_count,
            num_predict=num_predict,
        )
