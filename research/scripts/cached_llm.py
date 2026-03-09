"""Cached LLM client — saves every request/response to disk.

Never makes the same API call twice. Cache key is a hash of
(model, system_prompt, user_prompt, temperature, tool_schema).

Usage:
    from cached_llm import CachedLLM
    llm = CachedLLM()
    result = llm.generate(
        model="claude-sonnet-4-20250514",
        system_prompt="You are...",
        user_prompt="Generate a card...",
        temperature=0.7,
        tool_schema=None,  # or dict for tool_use
    )
    # result is a CachedResult with .content, .input_tokens, .output_tokens, .cost_usd, etc.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

# Load .env
ENV_PATH = Path("C:/Programming/MTGAI/.env")
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

CACHE_DIR = Path("C:/Programming/MTGAI/research/prompt-templates/experiments/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Pricing per 1M tokens (as of March 2026)
PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}


@dataclass
class CachedResult:
    content: str  # The text/JSON content from the model
    raw_response: dict  # Full response saved for debugging
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    model: str
    temperature: float
    cache_hit: bool
    cache_key: str
    timestamp: str

    def parse_json(self) -> dict | list | None:
        """Try to parse content as JSON."""
        try:
            return json.loads(self.content)
        except json.JSONDecodeError:
            # Try extracting JSON from markdown code blocks
            import re
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", self.content)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            return None


def _compute_cache_key(
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    tool_schema: dict | None,
) -> str:
    """Compute a deterministic hash for the request."""
    payload = json.dumps(
        {
            "model": model,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "temperature": temperature,
            "tool_schema": tool_schema,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    prices = PRICING.get(model, {"input": 0, "output": 0})
    return (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000


class CachedLLM:
    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = cache_dir
        self.total_cost = 0.0
        self.total_calls = 0
        self.cache_hits = 0
        self.cache_misses = 0

    def generate(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        tool_schema: dict | None = None,
        max_tokens: int = 4096,
    ) -> CachedResult:
        """Generate a response, using cache if available."""
        cache_key = _compute_cache_key(model, system_prompt, user_prompt, temperature, tool_schema)
        cache_path = self.cache_dir / f"{cache_key}.json"

        # Check cache
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            self.cache_hits += 1
            self.total_calls += 1
            result = CachedResult(**cached)
            result.cache_hit = True
            return result

        # Cache miss — make the API call
        self.cache_misses += 1
        self.total_calls += 1

        if model.startswith("claude"):
            result = self._call_anthropic(
                model, system_prompt, user_prompt, temperature, tool_schema, max_tokens
            )
        elif model.startswith("gpt"):
            result = self._call_openai(
                model, system_prompt, user_prompt, temperature, tool_schema, max_tokens
            )
        else:
            raise ValueError(f"Unknown model: {model}")

        result.cache_key = cache_key
        result.cache_hit = False

        # Save to cache
        cache_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")

        self.total_cost += result.cost_usd
        return result

    def _call_anthropic(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        tool_schema: dict | None,
        max_tokens: int,
    ) -> CachedResult:
        import anthropic

        client = anthropic.Anthropic()
        start = time.time()

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        if tool_schema:
            kwargs["tools"] = [tool_schema]
            kwargs["tool_choice"] = {"type": "tool", "name": tool_schema["name"]}

        resp = client.messages.create(**kwargs)
        latency = int((time.time() - start) * 1000)

        # Extract content
        if tool_schema:
            # Tool use response — extract the tool input JSON
            for block in resp.content:
                if block.type == "tool_use":
                    content = json.dumps(block.input)
                    break
            else:
                content = resp.content[0].text if resp.content else ""
        else:
            content = resp.content[0].text if resp.content else ""

        cost = _calc_cost(model, resp.usage.input_tokens, resp.usage.output_tokens)

        return CachedResult(
            content=content,
            raw_response={"stop_reason": resp.stop_reason, "model": resp.model},
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            cost_usd=cost,
            latency_ms=latency,
            model=model,
            temperature=temperature,
            cache_hit=False,
            cache_key="",
            timestamp=datetime.now().isoformat(),
        )

    def _call_openai(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        tool_schema: dict | None,
        max_tokens: int,
    ) -> CachedResult:
        from openai import OpenAI

        client = OpenAI()
        start = time.time()

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        # For OpenAI, use json_object mode instead of tool_schema
        if tool_schema:
            kwargs["response_format"] = {"type": "json_object"}

        resp = client.chat.completions.create(**kwargs)
        latency = int((time.time() - start) * 1000)

        content = resp.choices[0].message.content or ""
        cost = _calc_cost(model, resp.usage.prompt_tokens, resp.usage.completion_tokens)

        return CachedResult(
            content=content,
            raw_response={"finish_reason": resp.choices[0].finish_reason, "model": resp.model},
            input_tokens=resp.usage.prompt_tokens,
            output_tokens=resp.usage.completion_tokens,
            cost_usd=cost,
            latency_ms=latency,
            model=model,
            temperature=temperature,
            cache_hit=False,
            cache_key="",
            timestamp=datetime.now().isoformat(),
        )

    def stats(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "total_cost_usd": round(self.total_cost, 4),
            "hit_rate": f"{self.cache_hits / max(self.total_calls, 1) * 100:.1f}%",
        }


# Card generation tool schema for Anthropic tool_use
CARD_TOOL_SCHEMA = {
    "name": "generate_card",
    "description": "Generate a single MTG card",
    "input_schema": {
        "type": "object",
        "required": ["name", "mana_cost", "type_line", "oracle_text", "rarity", "colors",
                      "color_identity", "cmc"],
        "properties": {
            "name": {"type": "string"},
            "mana_cost": {"type": "string", "description": "Mana cost like {2}{W}{U}. Empty for lands."},
            "cmc": {"type": "number"},
            "colors": {"type": "array", "items": {"type": "string", "enum": ["W", "U", "B", "R", "G"]}},
            "color_identity": {"type": "array", "items": {"type": "string", "enum": ["W", "U", "B", "R", "G"]}},
            "type_line": {"type": "string"},
            "oracle_text": {"type": "string", "description": "Rules text. Use ~ for self-reference."},
            "flavor_text": {"type": ["string", "null"]},
            "power": {"type": ["string", "null"]},
            "toughness": {"type": ["string", "null"]},
            "loyalty": {"type": ["string", "null"]},
            "rarity": {"type": "string", "enum": ["common", "uncommon", "rare", "mythic"]},
            "design_notes": {"type": "string"},
        },
    },
}

CARDS_BATCH_TOOL_SCHEMA = {
    "name": "generate_cards",
    "description": "Generate multiple MTG cards",
    "input_schema": {
        "type": "object",
        "required": ["cards"],
        "properties": {
            "cards": {
                "type": "array",
                "items": CARD_TOOL_SCHEMA["input_schema"],
            },
        },
    },
}
