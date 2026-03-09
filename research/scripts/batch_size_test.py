"""Batch size test for MTG card generation via Claude Sonnet.

Tests batch sizes of 1, 3, 5, and 10 cards per API call.
Measures quality, parse success rate, cost per card, and latency.

Usage: python research/scripts/batch_size_test.py
"""

import json
import os
import time
from pathlib import Path

# Load .env from project root
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

import anthropic

# ── Constants ──────────────────────────────────────────────────────────────────

MODEL = "claude-sonnet-4-20250514"
TEMPERATURE = 0.7
# Claude Sonnet pricing (per million tokens)
INPUT_COST_PER_M = 3.0
OUTPUT_COST_PER_M = 15.0

# Required fields for a valid card
REQUIRED_FIELDS = ["name", "mana_cost", "cmc", "colors", "type_line", "oracle_text", "rarity"]
CREATURE_FIELDS = ["power", "toughness"]

# ── Load system prompt ─────────────────────────────────────────────────────────

system_prompt_path = (
    Path(__file__).parent.parent / "prompt-templates" / "system-prompt-v1.md"
)
raw = system_prompt_path.read_text(encoding="utf-8")

# Extract text inside the code fence
in_fence = False
lines: list[str] = []
for line in raw.splitlines():
    if line.strip().startswith("```") and not in_fence:
        in_fence = True
        continue
    if line.strip().startswith("```") and in_fence:
        break
    if in_fence:
        lines.append(line)

SYSTEM_PROMPT = "\n".join(lines)

# ── Card schema for tool_use ──────────────────────────────────────────────────

SINGLE_CARD_TOOL = {
    "name": "generate_card",
    "description": "Generate a single Magic: The Gathering card.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Original card name"},
            "mana_cost": {
                "type": "string",
                "description": "Mana cost string, e.g. '{2}{W}{U}'",
            },
            "cmc": {
                "type": "number",
                "description": "Converted mana cost (total mana value)",
            },
            "colors": {
                "type": "array",
                "items": {"type": "string", "enum": ["W", "U", "B", "R", "G"]},
                "description": "Colors from mana cost",
            },
            "color_identity": {
                "type": "array",
                "items": {"type": "string", "enum": ["W", "U", "B", "R", "G"]},
                "description": "Colors from mana cost and oracle text",
            },
            "type_line": {
                "type": "string",
                "description": "Full type line, e.g. 'Creature — Human Wizard'",
            },
            "oracle_text": {
                "type": "string",
                "description": "Rules text using ~ for self-reference",
            },
            "flavor_text": {
                "type": ["string", "null"],
                "description": "Evocative in-world flavor text",
            },
            "power": {
                "type": ["string", "null"],
                "description": "Power (creatures only)",
            },
            "toughness": {
                "type": ["string", "null"],
                "description": "Toughness (creatures only)",
            },
            "loyalty": {
                "type": ["string", "null"],
                "description": "Loyalty (planeswalkers only)",
            },
            "rarity": {
                "type": "string",
                "enum": ["common", "uncommon", "rare", "mythic"],
                "description": "Card rarity",
            },
            "layout": {"type": "string", "description": "Card layout, usually 'normal'"},
            "design_notes": {
                "type": "string",
                "description": "Design intent and reasoning",
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
    },
}

BATCH_CARDS_TOOL = {
    "name": "generate_cards",
    "description": "Generate multiple Magic: The Gathering cards as an array.",
    "input_schema": {
        "type": "object",
        "properties": {
            "cards": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Original card name"},
                        "mana_cost": {
                            "type": "string",
                            "description": "Mana cost string, e.g. '{2}{W}{U}'",
                        },
                        "cmc": {
                            "type": "number",
                            "description": "Converted mana cost (total mana value)",
                        },
                        "colors": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["W", "U", "B", "R", "G"],
                            },
                            "description": "Colors from mana cost",
                        },
                        "color_identity": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["W", "U", "B", "R", "G"],
                            },
                            "description": "Colors from mana cost and oracle text",
                        },
                        "type_line": {
                            "type": "string",
                            "description": "Full type line, e.g. 'Creature — Human Wizard'",
                        },
                        "oracle_text": {
                            "type": "string",
                            "description": "Rules text using ~ for self-reference",
                        },
                        "flavor_text": {
                            "type": ["string", "null"],
                            "description": "Evocative in-world flavor text",
                        },
                        "power": {
                            "type": ["string", "null"],
                            "description": "Power (creatures only)",
                        },
                        "toughness": {
                            "type": ["string", "null"],
                            "description": "Toughness (creatures only)",
                        },
                        "loyalty": {
                            "type": ["string", "null"],
                            "description": "Loyalty (planeswalkers only)",
                        },
                        "rarity": {
                            "type": "string",
                            "enum": ["common", "uncommon", "rare", "mythic"],
                            "description": "Card rarity",
                        },
                        "layout": {
                            "type": "string",
                            "description": "Card layout, usually 'normal'",
                        },
                        "design_notes": {
                            "type": "string",
                            "description": "Design intent and reasoning",
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
                },
                "description": "Array of card objects",
            },
        },
        "required": ["cards"],
    },
}

# ── Test prompts ──────────────────────────────────────────────────────────────

TEST_PROMPTS = {
    1: "Generate 1 green common creature. CMC 2-3.",
    3: (
        "Generate 3 common creatures: 1 white (CMC 2), 1 red (CMC 3), "
        "1 blue (CMC 1-2). Output as a JSON array of card objects."
    ),
    5: (
        "Generate 5 common creatures, one of each color (W, U, B, R, G). "
        "CMC 2-4. Output as a JSON array of card objects."
    ),
    10: (
        "Generate 10 common creatures: 2 of each color (W, U, B, R, G). "
        "CMC 1-4. Output as a JSON array of card objects."
    ),
}


# ── Validation helpers ────────────────────────────────────────────────────────


def validate_card(card: dict) -> list[str]:
    """Check a single card dict for issues. Returns list of issue strings."""
    issues = []

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in card or card[field] is None:
            issues.append(f"Missing required field: {field}")

    # Check creature-specific fields
    type_line = card.get("type_line", "")
    if "Creature" in type_line:
        for field in CREATURE_FIELDS:
            if field not in card or card[field] is None:
                issues.append(f"Creature missing {field}")

    # Check mana_cost format
    mana_cost = card.get("mana_cost", "")
    if mana_cost and not mana_cost.startswith("{"):
        issues.append(f"Mana cost not in brace format: {mana_cost}")

    # Check colors is a list
    colors = card.get("colors", [])
    if not isinstance(colors, list):
        issues.append(f"colors is not a list: {colors}")

    # Check rarity is valid
    rarity = card.get("rarity", "")
    if rarity not in ("common", "uncommon", "rare", "mythic"):
        issues.append(f"Invalid rarity: {rarity}")

    # Check self-reference uses ~
    oracle = card.get("oracle_text", "")
    name = card.get("name", "")
    if name and name in oracle:
        issues.append("oracle_text uses card name instead of ~")

    # Check cmc is a number
    cmc = card.get("cmc")
    if cmc is not None and not isinstance(cmc, (int, float)):
        issues.append(f"cmc is not a number: {cmc}")

    return issues


def calculate_cost(input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in USD for a given token count."""
    return (input_tokens / 1_000_000 * INPUT_COST_PER_M) + (
        output_tokens / 1_000_000 * OUTPUT_COST_PER_M
    )


# ── API call functions ────────────────────────────────────────────────────────


def run_batch_test(client: anthropic.Anthropic, batch_size: int) -> dict:
    """Run a single batch size test. Returns a results dict."""
    prompt = TEST_PROMPTS[batch_size]
    is_single = batch_size == 1

    tools = [SINGLE_CARD_TOOL] if is_single else [BATCH_CARDS_TOOL]
    tool_choice = (
        {"type": "tool", "name": "generate_card"}
        if is_single
        else {"type": "tool", "name": "generate_cards"}
    )

    print(f"\n{'='*60}")
    print(f"  Batch size: {batch_size}")
    print(f"  Prompt: {prompt}")
    print(f"{'='*60}")

    start_time = time.time()

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=8192,
            temperature=TEMPERATURE,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            tools=tools,
            tool_choice=tool_choice,
        )
        elapsed = time.time() - start_time
    except Exception as e:
        elapsed = time.time() - start_time
        return {
            "batch_size": batch_size,
            "success": False,
            "error": str(e),
            "latency_total_s": round(elapsed, 2),
            "raw_response": None,
        }

    # Extract token usage
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost = calculate_cost(input_tokens, output_tokens)

    # Parse the tool use response
    cards = []
    raw_tool_input = None
    parse_error = None

    for block in response.content:
        if block.type == "tool_use":
            raw_tool_input = block.input
            if is_single:
                cards = [block.input]
            else:
                cards = block.input.get("cards", [])
            break

    if not cards:
        parse_error = "No tool_use block found or empty cards array"

    # Validate each card
    valid_cards = 0
    cards_with_issues = 0
    all_issues: list[dict] = []
    quality_notes: list[str] = []

    for i, card in enumerate(cards):
        issues = validate_card(card)
        if issues:
            cards_with_issues += 1
            all_issues.append({"card_index": i, "name": card.get("name", "?"), "issues": issues})
        else:
            valid_cards += 1

        # Quality observations
        name = card.get("name", "?")
        oracle = card.get("oracle_text", "")
        power = card.get("power", "?")
        toughness = card.get("toughness", "?")
        mana_cost = card.get("mana_cost", "?")
        print(f"  [{i+1}] {name} — {mana_cost} — {power}/{toughness}")
        if oracle:
            # Truncate for display
            oracle_short = oracle[:80] + ("..." if len(oracle) > 80 else "")
            print(f"      {oracle_short}")

    num_cards = len(cards)
    cost_per_card = cost / num_cards if num_cards > 0 else 0
    latency_per_card = elapsed / num_cards if num_cards > 0 else 0

    result = {
        "batch_size": batch_size,
        "success": True,
        "num_cards_returned": num_cards,
        "valid_cards": valid_cards,
        "cards_with_issues": cards_with_issues,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cost_usd": round(cost, 6),
        "cost_per_card_usd": round(cost_per_card, 6),
        "tokens_per_card": round((input_tokens + output_tokens) / num_cards, 1) if num_cards else 0,
        "input_tokens_per_card": round(input_tokens / num_cards, 1) if num_cards else 0,
        "output_tokens_per_card": round(output_tokens / num_cards, 1) if num_cards else 0,
        "latency_total_s": round(elapsed, 2),
        "latency_per_card_s": round(latency_per_card, 2),
        "parse_error": parse_error,
        "validation_issues": all_issues,
        "quality_notes": quality_notes,
        "cards": cards,
    }

    # Print summary
    print(f"\n  Results:")
    print(f"    Cards returned: {num_cards}")
    print(f"    Valid: {valid_cards}, With issues: {cards_with_issues}")
    print(f"    Tokens: {input_tokens} in + {output_tokens} out = {input_tokens + output_tokens}")
    print(f"    Cost: ${cost:.4f} total, ${cost_per_card:.4f} per card")
    print(f"    Latency: {elapsed:.1f}s total, {latency_per_card:.1f}s per card")

    if all_issues:
        print(f"    Issues:")
        for issue in all_issues:
            print(f"      {issue['name']}: {', '.join(issue['issues'])}")

    return result


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    client = anthropic.Anthropic()

    print("=" * 60)
    print("  MTG AI — Batch Size Test")
    print(f"  Model: {MODEL}")
    print(f"  Temperature: {TEMPERATURE}")
    print(f"  Pricing: ${INPUT_COST_PER_M}/M input, ${OUTPUT_COST_PER_M}/M output")
    print("=" * 60)

    results = []
    batch_sizes = [1, 3, 5, 10]

    for batch_size in batch_sizes:
        result = run_batch_test(client, batch_size)
        results.append(result)

        # Space calls at least 1 second apart
        if batch_size != batch_sizes[-1]:
            time.sleep(1.5)

    # Save raw results
    output_path = Path(__file__).parent.parent / "batch-size-test-results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {output_path}")

    # Print comparison table
    print("\n" + "=" * 80)
    print("  COMPARISON TABLE")
    print("=" * 80)
    header = (
        f"{'Batch':>5} | {'Cards':>5} | {'Valid':>5} | {'Issues':>6} | "
        f"{'In Tok':>7} | {'Out Tok':>7} | {'Cost':>8} | {'$/Card':>8} | "
        f"{'Tok/Card':>8} | {'Time':>6} | {'T/Card':>6}"
    )
    print(header)
    print("-" * len(header))

    for r in results:
        if not r["success"]:
            print(f"{r['batch_size']:>5} | FAILED: {r.get('error', 'unknown')}")
            continue
        print(
            f"{r['batch_size']:>5} | "
            f"{r['num_cards_returned']:>5} | "
            f"{r['valid_cards']:>5} | "
            f"{r['cards_with_issues']:>6} | "
            f"{r['input_tokens']:>7} | "
            f"{r['output_tokens']:>7} | "
            f"${r['cost_usd']:>6.4f} | "
            f"${r['cost_per_card_usd']:>6.4f} | "
            f"{r['tokens_per_card']:>8.0f} | "
            f"{r['latency_total_s']:>5.1f}s | "
            f"{r['latency_per_card_s']:>5.1f}s"
        )

    print("\nDone!")


if __name__ == "__main__":
    main()
