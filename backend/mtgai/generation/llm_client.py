"""Minimal LLM client for card/mechanic generation.

Supports Anthropic prompt caching — system prompts and tool definitions are
marked with ``cache_control`` so sequential API calls within ~5 minutes reuse
the cached prefix at 90 % discount on input tokens.
"""

import logging
import os
from pathlib import Path

from anthropic import Anthropic

logger = logging.getLogger(__name__)

# Load .env file from project root
_ENV_PATH = Path("C:/Programming/MTGAI/.env")
if _ENV_PATH.exists():
    for line in _ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

# Model tiers: family name → (rank, latest model ID)
_MODEL_TIERS: dict[str, tuple[int, str]] = {
    "haiku": (0, "claude-haiku-4-5-20251001"),
    "sonnet": (1, "claude-sonnet-4-6"),
    "opus": (2, "claude-opus-4-6"),
}

# Pricing per 1M tokens (March 2026)
PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-opus-4-6": {"input": 15.00, "output": 75.00},
}


def calc_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> float:
    """Calculate API cost including prompt-cache pricing.

    - Non-cached input tokens: 1x base input price
    - Cache creation tokens: 1.25x base input price
    - Cache read tokens: 0.1x base input price
    - Output tokens: 1x base output price
    """
    prices = PRICING.get(model, {"input": 0, "output": 0})
    inp = prices["input"]
    return (
        input_tokens * inp
        + cache_creation_input_tokens * inp * 1.25
        + cache_read_input_tokens * inp * 0.1
        + output_tokens * prices["output"]
    ) / 1_000_000


def cost_from_result(result: dict) -> float:
    """Convenience: calculate cost directly from a ``generate_with_tool`` result."""
    return calc_cost(
        model=result["model"],
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        cache_creation_input_tokens=result.get("cache_creation_input_tokens", 0),
        cache_read_input_tokens=result.get("cache_read_input_tokens", 0),
    )


def _model_tier(model: str) -> int:
    """Return numeric tier for a model string, or -1 if unknown."""
    model_lower = model.lower()
    for family, (tier, _) in _MODEL_TIERS.items():
        if family in model_lower:
            return tier
    return -1


def cap_model(model: str, effort: str | None = None) -> tuple[str, str | None]:
    """Cap *model* to the MTGAI_MAX_MODEL ceiling.

    Set MTGAI_MAX_MODEL to a family name (haiku, sonnet, opus) and any call
    requesting a higher-tier model will be downgraded to the latest model in
    the cap tier.

    Returns ``(effective_model, effective_effort)``.
    """
    max_family = os.environ.get("MTGAI_MAX_MODEL", "").strip().lower()
    if not max_family:
        return model, effort

    cap = _MODEL_TIERS.get(max_family)
    if cap is None:
        logger.warning("MTGAI_MAX_MODEL=%r not recognised (use haiku/sonnet/opus)", max_family)
        return model, effort

    cap_tier, cap_model_id = cap
    req_tier = _model_tier(model)
    if req_tier == -1:
        return model, effort  # unknown model — pass through

    if req_tier > cap_tier:
        logger.info("MAX_MODEL cap: %s → %s", model, cap_model_id)
        if effort and "opus" not in cap_model_id:
            effort = None
        return cap_model_id, effort
    return model, effort


def generate_with_tool(
    system_prompt: str,
    user_prompt: str,
    tool_schema: dict,
    model: str = "claude-sonnet-4-6",
    temperature: float = 1.0,
    max_tokens: int = 8192,
    effort: str | None = None,
    cache: bool = True,
) -> dict:
    """Call Anthropic API with tool_use for structured JSON output.

    Uses forced tool_choice so the model always returns structured data
    matching the provided tool_schema.

    Args:
        effort: Optional effort level ("max", "high", "low"). Opus-only.
                Note: ``thinking`` is incompatible with forced tool_choice,
                but ``effort`` works fine.
        cache:  Enable Anthropic prompt caching.  Marks the system prompt
                and tool definition with ``cache_control`` so that repeated
                calls within ~5 min reuse the cached prefix (90 % cheaper).

    Returns a dict with:
        - result: the parsed tool input (structured JSON)
        - input_tokens: non-cached input tokens
        - output_tokens: tokens generated
        - cache_creation_input_tokens: tokens written to cache (first call)
        - cache_read_input_tokens: tokens read from cache (subsequent calls)
        - stop_reason: the stop reason from the API
        - model: effective model used
    """
    model, effort = cap_model(model, effort)

    client = Anthropic()

    if cache:
        system: str | list[dict] = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        tools = [{**tool_schema, "cache_control": {"type": "ephemeral"}}]
    else:
        system = system_prompt
        tools = [tool_schema]

    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user_prompt}],
        "tools": tools,
        "tool_choice": {"type": "tool", "name": tool_schema["name"]},
    }

    if effort:
        kwargs["output_config"] = {"effort": effort}

    response = client.messages.create(**kwargs)

    # Check for truncation (silent failure — must check stop_reason)
    if response.stop_reason == "max_tokens":
        raise ValueError(
            f"Response truncated (stop_reason=max_tokens). "
            f"Increase max_tokens (currently {max_tokens})."
        )

    # Extract cache usage stats
    cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0

    if cache and (cache_creation or cache_read):
        logger.debug(
            "Cache: %d created, %d read, %d non-cached",
            cache_creation,
            cache_read,
            response.usage.input_tokens,
        )

    # Extract tool use result
    for block in response.content:
        if block.type == "tool_use":
            return {
                "result": block.input,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": cache_read,
                "stop_reason": response.stop_reason,
                "model": model,
            }
    raise ValueError("No tool_use block in response")
