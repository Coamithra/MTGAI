"""Model Comparison Script — Task 0D-4

Generates the same 5 test cards on Claude Sonnet, GPT-4o, and GPT-4o-mini.
Records raw results, token usage, and latency for scoring.
"""

import json
import os
import time
from pathlib import Path

import anthropic
import openai

# ---------------------------------------------------------------------------
# 1. Load API keys from .env
# ---------------------------------------------------------------------------
env_path = Path("C:/Programming/MTGAI/.env")
for line in env_path.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())

# ---------------------------------------------------------------------------
# 2. Read the system prompt from the file (extract from code fence)
# ---------------------------------------------------------------------------
prompt_path = Path("C:/Programming/MTGAI/research/prompt-templates/system-prompt-v1.md")
prompt_md = prompt_path.read_text(encoding="utf-8")

# Extract text between the first ``` and the next ```
in_fence = False
system_prompt_lines: list[str] = []
for md_line in prompt_md.splitlines():
    if md_line.strip().startswith("```") and not in_fence:
        in_fence = True
        continue
    if md_line.strip().startswith("```") and in_fence:
        break
    if in_fence:
        system_prompt_lines.append(md_line)

SYSTEM_PROMPT = "\n".join(system_prompt_lines)
print(f"System prompt loaded: {len(SYSTEM_PROMPT)} chars")

# ---------------------------------------------------------------------------
# 3. Define the 5 test prompts
# ---------------------------------------------------------------------------
TEST_PROMPTS = [
    {
        "id": "common_white_creature",
        "prompt": (
            "Generate a white common creature card. CMC 2-3. "
            "Simple ability suitable for common (New World Order). Include flavor text."
        ),
    },
    {
        "id": "uncommon_blue_instant",
        "prompt": (
            "Generate a blue uncommon instant spell. CMC 2-4. "
            "Can have a moderately complex effect. Include flavor text."
        ),
    },
    {
        "id": "rare_black_legendary",
        "prompt": (
            "Generate a black rare legendary creature. CMC 4-6. "
            "Should have an impactful ability worthy of rare. Include flavor text."
        ),
    },
    {
        "id": "mythic_planeswalker",
        "prompt": (
            "Generate a mythic rare planeswalker card. 2-3 colors of your choice. CMC 3-5. "
            "Three loyalty abilities (+, -, ultimate). Include starting loyalty."
        ),
    },
    {
        "id": "uncommon_land",
        "prompt": (
            "Generate an uncommon nonbasic land. "
            "Should produce one or two colors of mana with a relevant ability or condition."
        ),
    },
]

# ---------------------------------------------------------------------------
# 4. Define the card schema for tool_use / JSON
# ---------------------------------------------------------------------------
CARD_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Original card name"},
        "mana_cost": {
            "type": "string",
            "description": "Mana cost string, e.g. '{2}{W}{U}'. Null for lands.",
        },
        "cmc": {"type": "number", "description": "Converted mana cost total (X counts as 0)"},
        "colors": {
            "type": "array",
            "items": {"type": "string", "enum": ["W", "U", "B", "R", "G"]},
            "description": "Colors matching mana_cost",
        },
        "color_identity": {
            "type": "array",
            "items": {"type": "string", "enum": ["W", "U", "B", "R", "G"]},
            "description": "Colors from mana_cost AND oracle_text mana symbols",
        },
        "type_line": {"type": "string", "description": "e.g. 'Creature — Human Wizard'"},
        "oracle_text": {
            "type": "string",
            "description": "Rules text using ~ for self-reference. Separate abilities with newline.",
        },
        "flavor_text": {"type": ["string", "null"], "description": "Evocative in-world flavor"},
        "power": {"type": ["string", "null"], "description": "Power for creatures, e.g. '3'"},
        "toughness": {
            "type": ["string", "null"],
            "description": "Toughness for creatures, e.g. '3'",
        },
        "loyalty": {
            "type": ["string", "null"],
            "description": "Starting loyalty for planeswalkers",
        },
        "rarity": {
            "type": "string",
            "enum": ["common", "uncommon", "rare", "mythic"],
            "description": "Card rarity",
        },
        "layout": {"type": "string", "description": "Card layout, usually 'normal'"},
        "design_notes": {
            "type": "string",
            "description": "Design intent, color pie reasoning, power level choices",
        },
    },
    "required": [
        "name",
        "mana_cost",
        "cmc",
        "colors",
        "color_identity",
        "type_line",
        "oracle_text",
        "rarity",
        "design_notes",
    ],
}

# ---------------------------------------------------------------------------
# 5. Model definitions
# ---------------------------------------------------------------------------
MODELS = [
    {"name": "claude-sonnet", "model_id": "claude-sonnet-4-20250514", "provider": "anthropic"},
    {"name": "gpt-4o", "model_id": "gpt-4o", "provider": "openai"},
    {"name": "gpt-4o-mini", "model_id": "gpt-4o-mini", "provider": "openai"},
]

# ---------------------------------------------------------------------------
# 6. API call functions
# ---------------------------------------------------------------------------

anthropic_client = anthropic.Anthropic()
openai_client = openai.OpenAI()


def call_anthropic(model_id: str, user_prompt: str) -> dict:
    """Call Anthropic API with tool_use for structured card output."""
    start = time.time()
    try:
        response = anthropic_client.messages.create(
            model=model_id,
            max_tokens=2048,
            temperature=0.7,
            system=SYSTEM_PROMPT,
            tools=[
                {
                    "name": "generate_card",
                    "description": "Generate a Magic: The Gathering card as structured data.",
                    "input_schema": CARD_TOOL_SCHEMA,
                }
            ],
            tool_choice={"type": "tool", "name": "generate_card"},
            messages=[{"role": "user", "content": user_prompt}],
        )
        latency_ms = int((time.time() - start) * 1000)

        # Extract the tool use result
        card_json = None
        for block in response.content:
            if block.type == "tool_use":
                card_json = block.input
                break

        return {
            "success": card_json is not None,
            "card_json": card_json,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "latency_ms": latency_ms,
            "error": None if card_json else "No tool_use block in response",
            "raw_response": str(response.content),
        }
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        return {
            "success": False,
            "card_json": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "latency_ms": latency_ms,
            "error": str(e),
            "raw_response": str(e),
        }


def call_openai(model_id: str, user_prompt: str) -> dict:
    """Call OpenAI API with JSON mode for structured card output."""
    start = time.time()

    # Add explicit JSON instruction to the user prompt for OpenAI
    json_instruction = (
        "\n\nReturn your card as a single valid JSON object with these fields: "
        "name, mana_cost, cmc, colors, color_identity, type_line, oracle_text, "
        "flavor_text, power, toughness, loyalty, rarity, layout, design_notes. "
        "Output ONLY the JSON object, no other text."
    )

    try:
        response = openai_client.chat.completions.create(
            model=model_id,
            temperature=0.7,
            max_tokens=2048,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt + json_instruction},
            ],
        )
        latency_ms = int((time.time() - start) * 1000)

        raw_content = response.choices[0].message.content
        try:
            card_json = json.loads(raw_content)
            success = True
            error = None
        except json.JSONDecodeError as je:
            card_json = None
            success = False
            error = f"JSON parse error: {je}"

        return {
            "success": success,
            "card_json": card_json,
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
            "latency_ms": latency_ms,
            "error": error,
            "raw_response": raw_content,
        }
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        return {
            "success": False,
            "card_json": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "latency_ms": latency_ms,
            "error": str(e),
            "raw_response": str(e),
        }


# ---------------------------------------------------------------------------
# 7. Run all 15 calls
# ---------------------------------------------------------------------------

def main():
    results: list[dict] = []
    total_calls = len(MODELS) * len(TEST_PROMPTS)
    call_num = 0

    for model in MODELS:
        for test in TEST_PROMPTS:
            call_num += 1
            print(
                f"[{call_num}/{total_calls}] {model['name']} — {test['id']}...",
                end=" ",
                flush=True,
            )

            if model["provider"] == "anthropic":
                result = call_anthropic(model["model_id"], test["prompt"])
                # Rate limit: 1 second between Anthropic calls
                time.sleep(1)
            else:
                result = call_openai(model["model_id"], test["prompt"])

            result["model_name"] = model["name"]
            result["model_id"] = model["model_id"]
            result["provider"] = model["provider"]
            result["prompt_id"] = test["id"]
            result["prompt_text"] = test["prompt"]

            status = "OK" if result["success"] else f"FAIL: {result['error']}"
            card_name = ""
            if result["card_json"] and isinstance(result["card_json"], dict):
                card_name = result["card_json"].get("name", "")
            print(
                f"{status} | {result['latency_ms']}ms | "
                f"in={result['input_tokens']} out={result['output_tokens']}"
                + (f" | {card_name}" if card_name else "")
            )

            results.append(result)

    # ---------------------------------------------------------------------------
    # 8. Save results
    # ---------------------------------------------------------------------------
    output_path = Path("C:/Programming/MTGAI/research/model-comparison-results.json")
    output_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nResults saved to {output_path}")

    # Summary
    print("\n=== Summary ===")
    for model in MODELS:
        model_results = [r for r in results if r["model_name"] == model["name"]]
        successes = sum(1 for r in model_results if r["success"])
        total_in = sum(r["input_tokens"] for r in model_results)
        total_out = sum(r["output_tokens"] for r in model_results)
        avg_latency = (
            sum(r["latency_ms"] for r in model_results) / len(model_results)
            if model_results
            else 0
        )
        print(
            f"{model['name']}: {successes}/5 success | "
            f"tokens in={total_in} out={total_out} | "
            f"avg latency={avg_latency:.0f}ms"
        )


if __name__ == "__main__":
    main()
