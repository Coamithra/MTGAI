"""Minimal LLM client for card/mechanic generation.

Supports two providers:
  - **Anthropic** (default): prompt caching, effort levels, forced tool_choice
  - **Ollama** (local): OpenAI-compatible API, text-based tool extraction fallback

Set ``MTGAI_PROVIDER=ollama`` to use a local model via Ollama.
"""

import json
import logging
import os
import re
import time
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

# ── Provider config ──────────────────────────────────────────────────

PROVIDER = os.environ.get("MTGAI_PROVIDER", "anthropic").strip().lower()
OLLAMA_MODEL = os.environ.get("MTGAI_OLLAMA_MODEL", "qwen2.5:14b").strip()
OLLAMA_URL = os.environ.get("MTGAI_OLLAMA_URL", "http://localhost:11434").strip()

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

    Returns 0.0 for local models (not in PRICING).
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


# ── Anthropic provider ───────────────────────────────────────────────


def _generate_anthropic(
    system_prompt: str,
    user_prompt: str,
    tool_schema: dict,
    model: str,
    temperature: float,
    max_tokens: int,
    effort: str | None,
    cache: bool,
) -> dict:
    """Call Anthropic API with forced tool_choice."""
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

    if response.stop_reason == "max_tokens":
        raise ValueError(
            f"Response truncated (stop_reason=max_tokens). "
            f"Increase max_tokens (currently {max_tokens})."
        )

    cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0

    if cache and (cache_creation or cache_read):
        logger.debug(
            "Cache: %d created, %d read, %d non-cached",
            cache_creation,
            cache_read,
            response.usage.input_tokens,
        )

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


# ── Ollama provider (OpenAI-compatible) ──────────────────────────────

# Max retries for Ollama connection errors
_OLLAMA_MAX_RETRIES = 3
_OLLAMA_RETRY_DELAY = 1.0

# Max retries when Ollama produces malformed tool output
_OLLAMA_MAX_TOOL_RETRIES = 2


def _ollama_translate_tool(tool_schema: dict) -> dict:
    """Convert Anthropic tool schema to OpenAI function-calling format."""
    return {
        "type": "function",
        "function": {
            "name": tool_schema["name"],
            "description": tool_schema.get("description", ""),
            "parameters": tool_schema.get("input_schema", {"type": "object", "properties": {}}),
        },
    }


def _ollama_extract_json(text: str, tool_name: str) -> dict | None:
    """Try to extract a JSON object from model text output.

    Strategies (in order):
      1. JSON code block (```json ... ```)
      2. Qwen-style tool call: {"name": "tool", "arguments": {...}}
      3. First top-level JSON object in text
    """
    # Strategy 1: fenced JSON code block
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 2: Qwen-style {"name": "tool", "arguments": {...}}
    qwen_pattern = r'\{"name":\s*"' + re.escape(tool_name) + r'",\s*"arguments":\s*(\{.*\})\}'
    qwen_match = re.search(qwen_pattern, text, re.DOTALL)
    if qwen_match:
        try:
            return json.loads(qwen_match.group(1))
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 3: first { ... } block (greedy from first { to last })
    brace_start = text.find("{")
    if brace_start != -1:
        # Find matching closing brace
        depth = 0
        for i in range(brace_start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[brace_start : i + 1])
                    except (json.JSONDecodeError, ValueError):
                        break

    return None


def _ollama_call_with_retry(client, kwargs: dict) -> object:
    """Call Ollama with connection retry."""
    import openai

    last_error: Exception | None = None
    for attempt in range(_OLLAMA_MAX_RETRIES):
        try:
            return client.chat.completions.create(**kwargs)
        except (openai.APITimeoutError, openai.APIConnectionError) as e:
            last_error = e
            if attempt < _OLLAMA_MAX_RETRIES - 1:
                logger.warning("Ollama connection error (attempt %d): %s", attempt + 1, e)
                time.sleep(_OLLAMA_RETRY_DELAY * (2**attempt))
    raise last_error  # type: ignore[misc]


def _generate_ollama(
    system_prompt: str,
    user_prompt: str,
    tool_schema: dict,
    model: str,
    temperature: float,
    max_tokens: int,
) -> dict:
    """Call Ollama via OpenAI-compatible API, with text-based tool extraction fallback."""
    import openai

    client = openai.OpenAI(
        base_url=f"{OLLAMA_URL}/v1",
        api_key="ollama",  # Ollama ignores this but the SDK requires it
    )

    ollama_model = model  # already set to OLLAMA_MODEL by caller
    tool_name = tool_schema["name"]
    oai_tool = _ollama_translate_tool(tool_schema)

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    kwargs: dict = {
        "model": ollama_model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
        "tools": [oai_tool],
    }

    for attempt in range(_OLLAMA_MAX_TOOL_RETRIES + 1):
        response = _ollama_call_with_retry(client, kwargs)
        choice = response.choices[0]
        msg = choice.message

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        # Try 1: native function calling
        if msg.tool_calls:
            for tc in msg.tool_calls:
                if tc.function.name == tool_name:
                    try:
                        result = json.loads(tc.function.arguments)
                    except (json.JSONDecodeError, TypeError):
                        result = {}
                    logger.info(
                        "Ollama [%s] tool call via native function calling (%d in, %d out)",
                        ollama_model,
                        input_tokens,
                        output_tokens,
                    )
                    return {
                        "result": result,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                        "stop_reason": "tool_use",
                        "model": ollama_model,
                    }

        # Try 2: extract JSON from text response
        if msg.content:
            extracted = _ollama_extract_json(msg.content, tool_name)
            if extracted and isinstance(extracted, dict):
                logger.info(
                    "Ollama [%s] tool call via text extraction (%d in, %d out)",
                    ollama_model,
                    input_tokens,
                    output_tokens,
                )
                return {
                    "result": extracted,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "stop_reason": "tool_use",
                    "model": ollama_model,
                }

        # Retry: append the bad response and ask again
        if attempt < _OLLAMA_MAX_TOOL_RETRIES:
            logger.warning(
                "Ollama [%s] failed to produce valid tool output (attempt %d/%d), retrying",
                ollama_model,
                attempt + 1,
                _OLLAMA_MAX_TOOL_RETRIES,
            )
            kwargs["messages"] = list(kwargs["messages"])
            kwargs["messages"].append(
                {
                    "role": "assistant",
                    "content": msg.content or "(empty response)",
                }
            )
            kwargs["messages"].append(
                {
                    "role": "user",
                    "content": (
                        f"Please respond with ONLY a JSON object matching the '{tool_name}' "
                        f"tool schema. No explanation, just the JSON."
                    ),
                }
            )

    raise ValueError(
        f"Ollama [{ollama_model}] failed to produce valid tool output "
        f"after {_OLLAMA_MAX_TOOL_RETRIES + 1} attempts"
    )


# ── Public API ───────────────────────────────────────────────────────


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
    """Call an LLM with tool_use for structured JSON output.

    Provider is selected by the ``MTGAI_PROVIDER`` env var:
      - ``anthropic`` (default): Anthropic API with forced tool_choice
      - ``ollama``: local model via Ollama's OpenAI-compatible API

    For Ollama, the ``model`` and ``effort`` params are ignored — the model
    is set by ``MTGAI_OLLAMA_MODEL`` (default: qwen2.5:14b). Prompt caching
    is also skipped (Ollama doesn't support it).

    Returns a dict with:
        - result: the parsed tool input (structured JSON)
        - input_tokens / output_tokens: token counts
        - cache_creation_input_tokens / cache_read_input_tokens: cache stats (0 for Ollama)
        - stop_reason: the stop reason
        - model: effective model used
    """
    if PROVIDER == "ollama":
        return _generate_ollama(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tool_schema=tool_schema,
            model=OLLAMA_MODEL,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # Default: Anthropic
    model, effort = cap_model(model, effort)
    return _generate_anthropic(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_schema=tool_schema,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        effort=effort,
        cache=cache,
    )
