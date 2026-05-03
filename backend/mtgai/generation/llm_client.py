"""Minimal LLM client for card/mechanic generation, backed by llmfacade.

Public surface (preserved across refactor):
  - ``generate_with_tool(...)``      provider-agnostic structured-JSON call
  - ``calc_cost`` / ``cost_from_result``  pricing helpers
  - ``cap_model(...)``                MTGAI_MAX_MODEL ceiling
  - ``PRICING``                       per-model pricing table

Provider for a given ``model_id`` is resolved through the model registry
first, then via the ``MTGAI_PROVIDER`` env var as a fallback. Anthropic
runs through llmfacade's Anthropic provider; local models run through
llmfacade's ``llamacpp`` provider in **managed mode** — llmfacade owns a
``llama-swap`` subprocess that lazily spawns ``llama-server`` instances
on first use. Per-model launch knobs (gguf path, context size, KV cache
quantization, GPU offload) live in the registry and are passed at
``provider.new_model(...)`` time.

Tool schemas are accepted in Anthropic's ``input_schema`` dict shape (the
same shape MTGAI call sites have always used); we wrap them as
``llmfacade.Tool`` objects with a no-op ``fn`` since we read
``resp.tool_calls[0].input`` directly and never invoke the tool callable.
"""

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any

from llmfacade import LLM, Provider, SystemBlock, Tool
from llmfacade.exceptions import LLMError

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

_PROVIDER_RAW = os.environ.get("MTGAI_PROVIDER", "anthropic").strip().lower()
# Migration alias: stale .env files still set MTGAI_PROVIDER=ollama. Treat as
# llamacpp + warn, instead of letting _get_provider raise on an unknown name.
if _PROVIDER_RAW == "ollama":
    logger.warning(
        "MTGAI_PROVIDER=ollama is no longer supported; routing to llamacpp. "
        "Update your .env to remove the variable or set it to 'llamacpp'."
    )
    _PROVIDER_RAW = "llamacpp"
PROVIDER = _PROVIDER_RAW

try:
    MAX_RETRIES = max(1, int(os.environ.get("MTGAI_MAX_RETRIES", "3").strip()))
except ValueError:
    MAX_RETRIES = 3

# Repetition penalty applied to all llamacpp calls. Unlike Ollama (where
# the Go-native sampler silently dropped repeat_penalty on Gemma-class
# models — issue ollama#15783), llama.cpp honours this knob across every
# architecture. theme_extractor's streaming path overrides per-call on
# JSON-subcall retries; the structured tool-use path here uses this default.
LLAMACPP_REPEAT_PENALTY = 1.1

# Model tiers: family name -> (rank, latest model ID)
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


# ── Cost calculation ─────────────────────────────────────────────────


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

    Returns 0.0 for local models (not in PRICING or registry).
    """
    prices = PRICING.get(model)
    if prices is None:
        try:
            from mtgai.settings.model_registry import get_registry

            info = get_registry().get_llm_by_model_id(model)
            if info:
                prices = {"input": info.input_price, "output": info.output_price}
        except Exception:
            pass
    if prices is None:
        prices = {"input": 0, "output": 0}
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


# ── MAX_MODEL ceiling ────────────────────────────────────────────────


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
        logger.info("MAX_MODEL cap: %s -> %s", model, cap_model_id)
        if effort and "opus" not in cap_model_id:
            effort = None
        return cap_model_id, effort
    return model, effort


# ── llmfacade plumbing ───────────────────────────────────────────────

# Cached llmfacade providers — one per backend. Constructed once per process;
# conversations are built fresh per call. Lock-guarded because the FastAPI
# SSE handler + cancel/status routes can call generate_with_tool from
# multiple threads.
_PROVIDERS: dict[str, Provider] = {}
_PROVIDERS_LOCK = threading.Lock()


def _noop_tool_fn(**kw: Any) -> dict[str, Any]:
    """Stand-in callable for MTGAI's @tool wrappers - never invoked because
    we read structured args from ``Response.tool_calls[i].input`` directly.
    Module-level (not a lambda) so it survives any future Tool deepcopy."""
    return kw


def _get_provider(name: str) -> Provider:
    with _PROVIDERS_LOCK:
        if name in _PROVIDERS:
            return _PROVIDERS[name]
        manager = LLM.default()
        if name == "anthropic":
            # exact_count_tokens: hits the Anthropic free server-side
            # count_tokens endpoint when something asks for token counts
            # (theme_extractor uses this). auto_cache_tools: matches the
            # pre-migration behaviour of cache_control: ephemeral on the
            # tool schema.
            prov = manager.new_provider(
                "anthropic",
                exact_count_tokens=True,
                auto_cache_tools=True,
            )
        elif name == "llamacpp":
            # Managed mode: no base_url. llmfacade lazily spawns a
            # llama-swap subprocess on first call and supervises one
            # llama-server per registered model.
            #
            # Per-model launch knobs (gguf path, context_size, KV-cache
            # quant, GPU offload) come from the registry at new_model()
            # time — see _llamacpp_new_model() below.
            prov = manager.new_provider(
                "llamacpp",
                repeat_penalty=LLAMACPP_REPEAT_PENALTY,
            )
        else:
            raise ValueError(f"Unknown provider: {name}")
        _PROVIDERS[name] = prov
        return prov


def _make_tool(tool_schema: dict) -> Tool:
    """Wrap an MTGAI/Anthropic-style tool schema dict as an llmfacade Tool."""
    return Tool(
        name=tool_schema["name"],
        description=tool_schema.get("description", ""),
        schema=tool_schema.get("input_schema", {"type": "object", "properties": {}}),
        fn=_noop_tool_fn,
        is_async=False,
    )


def _llamacpp_new_model(provider: Provider, model_id: str):
    """Build an llmfacade Model for a registered llamacpp entry.

    Threads the registry's launch knobs (gguf_path, context_window,
    cache_type_k/_v, n_gpu_layers) into ``provider.new_model(...)`` so
    the supervisor can launch llama-server with the right flags. Models
    not in the registry get a minimal default launch (no gguf path → the
    call will fail at supervisor.register() time with a clear error).
    """
    from mtgai.settings.model_registry import get_registry

    info = get_registry().get_llm_by_model_id(model_id)
    if info is None or not info.gguf_path:
        raise ValueError(
            f"llamacpp model {model_id!r} is not in the registry (or missing "
            f"gguf_path). Add it to backend/mtgai/settings/models.toml."
        )

    launch_kwargs: dict[str, Any] = {
        "name": info.model_id,
        "gguf": info.gguf_path,
        "context_size": info.context_window,
    }
    if info.cache_type_k is not None:
        launch_kwargs["cache_type_k"] = info.cache_type_k
    if info.cache_type_v is not None:
        launch_kwargs["cache_type_v"] = info.cache_type_v
    if info.n_gpu_layers is not None:
        launch_kwargs["n_gpu_layers"] = info.n_gpu_layers
    return provider.new_model(**launch_kwargs)


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
    """Call Anthropic via llmfacade with forced tool_choice."""
    provider = _get_provider("anthropic")
    facade_model = provider.new_model(model)
    convo = facade_model.new_conversation(
        system_blocks=[SystemBlock(text=system_prompt, cache=cache)],
        tools=[_make_tool(tool_schema)],
        tool_choice=tool_schema["name"],
        # Provider-level auto_cache_tools is True; explicitly disable here
        # when the caller passes cache=False so we honour the contract.
        auto_cache_tools=cache,
        log_dir=False,
    )

    send_kwargs: dict[str, Any] = {
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if effort:
        send_kwargs["effort"] = effort

    resp = convo.send(user_prompt, **send_kwargs)

    # Anthropic surfaces output truncation as finish_reason="max_tokens".
    if resp.finish_reason == "max_tokens":
        raise ValueError(
            f"Response truncated (finish_reason=max_tokens). "
            f"Increase max_tokens (currently {max_tokens})."
        )

    if not resp.tool_calls:
        raise ValueError("No tool_use block in response")

    usage = resp.usage
    return {
        "result": resp.tool_calls[0].input,
        "input_tokens": usage.prompt_tokens if usage else 0,
        "output_tokens": usage.completion_tokens if usage else 0,
        "cache_creation_input_tokens": usage.cache_creation_tokens if usage else 0,
        "cache_read_input_tokens": usage.cache_read_tokens if usage else 0,
        "stop_reason": resp.finish_reason,
        "model": model,
    }


# ── llamacpp provider ────────────────────────────────────────────────


def _llamacpp_extract_json(text: str, tool_name: str) -> dict | None:
    """Try to extract a JSON object from model text output.

    Strategies (in order):
      1. Fenced JSON code block (```json ... ```)
      2. Qwen-style tool call: ``{"name": "tool", "arguments": {...}}``
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


def _generate_llamacpp(
    system_prompt: str,
    user_prompt: str,
    tool_schema: dict,
    model: str,
    temperature: float,
    max_tokens: int,
) -> dict:
    """Call a local model through llmfacade's llamacpp provider.

    llmfacade handles the transport (managed-mode llama-swap → llama-server,
    OpenAI-compatible /v1/chat/completions) and forwards llama.cpp-specific
    samplers (top_k, min_p, repeat_penalty) through ``extra_body``. We layer
    on our own retry + JSON-extraction fallback because local models often
    return tool args inline as text instead of as a structured tool call.
    Tiktoken-based pre-call budget check + post-call truncation guard remain.
    """
    from mtgai.generation.token_utils import (
        check_post_call_response,
        check_pre_call,
        count_messages_tokens,
    )

    tool_name = tool_schema["name"]

    # Build a legacy dict shape just for the budget check + estimate. The
    # actual call goes through llmfacade.
    legacy_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    legacy_tool = {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": tool_schema.get("description", ""),
            "parameters": tool_schema.get("input_schema", {"type": "object", "properties": {}}),
        },
    }
    check_pre_call(model, legacy_messages, tools=[legacy_tool], output_reserve=max_tokens)
    estimated_input = count_messages_tokens(legacy_messages, tools=[legacy_tool])

    logger.info(
        "llamacpp [%s] call: max_tokens=%d, estimated_input=%d",
        model,
        max_tokens,
        estimated_input,
    )

    provider = _get_provider("llamacpp")
    facade_model = _llamacpp_new_model(provider, model)
    convo = facade_model.new_conversation(
        system_blocks=[SystemBlock(text=system_prompt)],
        tools=[_make_tool(tool_schema)],
        max_tokens=max_tokens,
        temperature=temperature,
        log_dir=False,
    )

    next_user: str | None = user_prompt
    for attempt in range(MAX_RETRIES):
        try:
            resp = convo.send(next_user)
        except LLMError as e:
            raise ValueError(f"llamacpp [{model}] error: {e}") from e

        check_post_call_response(
            resp,
            model,
            num_predict=max_tokens,
            estimated_input_tokens=estimated_input,
        )

        usage = resp.usage
        in_tok = usage.prompt_tokens if usage else 0
        out_tok = usage.completion_tokens if usage else 0

        # Try 1: native function calling. Require the tool name to match -
        # local models occasionally invent a tool or pick a leftover name
        # from the system prompt; treating that as success would silently
        # return wrong-shape data.
        matched = next(
            (tc for tc in resp.tool_calls if tc.name == tool_name), None
        )
        if matched is not None:
            args = matched.input
            logger.info(
                "llamacpp [%s] tool call via native function calling (%d in, %d out)",
                model,
                in_tok,
                out_tok,
            )
            return {
                "result": args,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "stop_reason": "tool_use",
                "model": model,
            }

        # Try 2: extract JSON from text response
        if resp.text:
            extracted = _llamacpp_extract_json(resp.text, tool_name)
            if isinstance(extracted, dict):
                logger.info(
                    "llamacpp [%s] tool call via text extraction (%d in, %d out)",
                    model,
                    in_tok,
                    out_tok,
                )
                return {
                    "result": extracted,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "stop_reason": "tool_use",
                    "model": model,
                }

        # Retry: convo history already contains the bad assistant reply;
        # the next send appends a re-prompt and continues from there.
        if attempt < MAX_RETRIES - 1:
            logger.warning(
                "llamacpp [%s] failed to produce valid tool output (attempt %d/%d), retrying",
                model,
                attempt + 1,
                MAX_RETRIES,
            )
            next_user = (
                f"Please respond with ONLY a JSON object matching the '{tool_name}' "
                f"tool schema. No explanation, just the JSON."
            )

    raise ValueError(
        f"llamacpp [{model}] failed to produce valid tool output after {MAX_RETRIES} attempts"
    )


# ── Public API ───────────────────────────────────────────────────────


def _resolve_provider(model: str) -> str:
    """Determine the provider for a model by checking the registry.

    Falls back to the MTGAI_PROVIDER env var for backward compatibility.
    """
    try:
        from mtgai.settings.model_registry import get_registry

        registry = get_registry()
        model_info = registry.get_llm_by_model_id(model)
        if model_info:
            return model_info.provider
    except Exception:
        pass

    return PROVIDER


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

    Provider is determined automatically from the model registry, or falls
    back to the ``MTGAI_PROVIDER`` env var:
      - ``anthropic``: Anthropic API with forced tool_choice + prompt caching
        (system block + tools array) when ``cache=True``
      - ``llamacpp``: local model via managed-mode llama-swap + llama-server,
        through llmfacade's OpenAI-compatible transport. Honours
        ``repeat_penalty`` (unlike the retired Ollama path).

    Returns a dict with:
        - result: the parsed tool input (structured JSON)
        - input_tokens / output_tokens: token counts
        - cache_creation_input_tokens / cache_read_input_tokens: cache stats
          (0 for llamacpp)
        - stop_reason: the stop reason
        - model: effective model used
    """
    provider = _resolve_provider(model)

    if provider == "llamacpp":
        return _generate_llamacpp(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tool_schema=tool_schema,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

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
