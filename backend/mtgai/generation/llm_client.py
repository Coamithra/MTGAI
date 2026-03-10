"""Minimal LLM client for card/mechanic generation."""

import os
from pathlib import Path

from anthropic import Anthropic

# Load .env file from project root
_ENV_PATH = Path("C:/Programming/MTGAI/.env")
if _ENV_PATH.exists():
    for line in _ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def generate_with_tool(
    system_prompt: str,
    user_prompt: str,
    tool_schema: dict,
    model: str = "claude-sonnet-4-20250514",
    temperature: float = 1.0,
    max_tokens: int = 8192,
) -> dict:
    """Call Anthropic API with tool_use for structured JSON output.

    Uses forced tool_choice so the model always returns structured data
    matching the provided tool_schema.

    Returns a dict with:
        - result: the parsed tool input (structured JSON)
        - input_tokens: tokens used in the prompt
        - output_tokens: tokens generated
    """
    client = Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        tools=[tool_schema],
        tool_choice={"type": "tool", "name": tool_schema["name"]},
    )
    # Extract tool use result
    for block in response.content:
        if block.type == "tool_use":
            return {
                "result": block.input,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
    raise ValueError("No tool_use block in response")
