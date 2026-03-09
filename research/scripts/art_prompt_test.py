"""Art prompt generation comparison: Sonnet vs Haiku vs GPT-4o-mini.

Tests whether cheaper models produce adequate art prompts compared to
the expensive card-design model (Sonnet). If cheap models produce 80%+
quality, we should use them for art prompt generation.

Usage: python research/scripts/art_prompt_test.py
"""

import json
import os
import sys
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an art director for a fantasy card game. Given a card's data, generate a detailed image generation prompt that would produce suitable card art.

Output a JSON object with:
- "art_prompt": The image generation prompt (100-200 words). Describe the scene, subject, composition, lighting, mood, and color palette. Specify "fantasy card game art style, detailed digital painting". Include "no text, no words, no letters, no watermark". Specify aspect ratio approximately 3:2 (wider than tall).
- "art_description": A brief 1-sentence description of what the art depicts."""

TEST_CARDS = [
    {
        "name": "Sentinel of Dawn",
        "mana_cost": "{2}{W}{W}",
        "type_line": "Creature — Angel Soldier",
        "oracle_text": "Flying, vigilance\nWhen Sentinel of Dawn enters, create two 1/1 white Soldier creature tokens.",
        "rarity": "rare",
        "colors": ["W"],
    },
    {
        "name": "Arcane Dissolution",
        "mana_cost": "{1}{U}{U}",
        "type_line": "Instant",
        "oracle_text": "Counter target spell. Scry 2.",
        "rarity": "uncommon",
        "colors": ["U"],
    },
    {
        "name": "Pyroclastic Surge",
        "mana_cost": "{3}{R}{R}",
        "type_line": "Sorcery",
        "oracle_text": "Pyroclastic Surge deals 4 damage to each creature and each planeswalker.",
        "rarity": "rare",
        "colors": ["R"],
    },
    {
        "name": "Mossback Titan",
        "mana_cost": "{4}{G}{G}",
        "type_line": "Creature — Beast",
        "oracle_text": "Trample\nMossback Titan gets +1/+1 for each land you control.",
        "power": "4",
        "toughness": "4",
        "rarity": "rare",
        "colors": ["G"],
    },
    {
        "name": "Twilight Expanse",
        "type_line": "Land",
        "oracle_text": "{T}: Add {C}.\n{T}, Pay 1 life: Add {W} or {B}.",
        "rarity": "rare",
        "colors": [],
    },
]

MODELS = [
    {"id": "claude-sonnet-4-20250514", "provider": "anthropic", "label": "Claude Sonnet"},
    {"id": "claude-haiku-4-5-20251001", "provider": "anthropic", "label": "Claude Haiku"},
    {"id": "gpt-4o-mini", "provider": "openai", "label": "GPT-4o-mini"},
]

TEMPERATURE = 0.6

# ---------------------------------------------------------------------------
# API callers
# ---------------------------------------------------------------------------


def call_anthropic(model_id: str, card: dict) -> dict:
    """Call Anthropic API and return result dict."""
    import anthropic

    client = anthropic.Anthropic()
    user_content = (
        "Generate an art prompt for this card. Respond with ONLY a JSON object, "
        "no other text.\n\n"
        f"Card data:\n```json\n{json.dumps(card, indent=2)}\n```"
    )

    start = time.time()
    resp = client.messages.create(
        model=model_id,
        max_tokens=1024,
        temperature=TEMPERATURE,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    latency = time.time() - start

    raw_text = resp.content[0].text
    # Parse JSON from response (strip markdown fences if present)
    json_text = raw_text.strip()
    if json_text.startswith("```"):
        # Remove ```json ... ``` wrapping
        lines = json_text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        json_text = "\n".join(lines)

    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError:
        parsed = {"art_prompt": raw_text, "art_description": "(parse error)"}

    return {
        "art_prompt": parsed.get("art_prompt", ""),
        "art_description": parsed.get("art_description", ""),
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "latency_s": round(latency, 2),
        "raw_response": raw_text,
    }


def call_openai(model_id: str, card: dict) -> dict:
    """Call OpenAI API and return result dict."""
    from openai import OpenAI

    client = OpenAI()
    user_content = (
        "Generate an art prompt for this card. Respond with ONLY a JSON object, "
        "no other text.\n\n"
        f"Card data:\n```json\n{json.dumps(card, indent=2)}\n```"
    )

    start = time.time()
    resp = client.chat.completions.create(
        model=model_id,
        max_tokens=1024,
        temperature=TEMPERATURE,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )
    latency = time.time() - start

    raw_text = resp.choices[0].message.content
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = {"art_prompt": raw_text, "art_description": "(parse error)"}

    return {
        "art_prompt": parsed.get("art_prompt", ""),
        "art_description": parsed.get("art_description", ""),
        "input_tokens": resp.usage.prompt_tokens,
        "output_tokens": resp.usage.completion_tokens,
        "latency_s": round(latency, 2),
        "raw_response": raw_text,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    results = []
    total_calls = len(MODELS) * len(TEST_CARDS)
    call_num = 0

    for model in MODELS:
        print(f"\n{'='*60}")
        print(f"Model: {model['label']} ({model['id']})")
        print(f"{'='*60}")

        for card in TEST_CARDS:
            call_num += 1
            print(f"  [{call_num}/{total_calls}] {card['name']}...", end=" ", flush=True)

            try:
                if model["provider"] == "anthropic":
                    result = call_anthropic(model["id"], card)
                else:
                    result = call_openai(model["id"], card)

                entry = {
                    "model": model["id"],
                    "model_label": model["label"],
                    "provider": model["provider"],
                    "card_name": card["name"],
                    "art_prompt": result["art_prompt"],
                    "art_description": result["art_description"],
                    "input_tokens": result["input_tokens"],
                    "output_tokens": result["output_tokens"],
                    "latency_s": result["latency_s"],
                }
                results.append(entry)
                print(
                    f"OK ({result['input_tokens']}in/{result['output_tokens']}out, "
                    f"{result['latency_s']}s)"
                )

            except Exception as e:
                print(f"FAILED — {e}")
                results.append(
                    {
                        "model": model["id"],
                        "model_label": model["label"],
                        "provider": model["provider"],
                        "card_name": card["name"],
                        "art_prompt": "",
                        "art_description": "",
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "latency_s": 0,
                        "error": str(e),
                    }
                )

            # Space Anthropic calls 1 second apart
            if model["provider"] == "anthropic":
                time.sleep(1)

    # Save results
    output_path = Path(__file__).parent.parent / "art-prompt-test-results.json"
    output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nResults saved to {output_path}")

    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for model in MODELS:
        model_results = [r for r in results if r["model"] == model["id"]]
        total_in = sum(r["input_tokens"] for r in model_results)
        total_out = sum(r["output_tokens"] for r in model_results)
        avg_latency = (
            sum(r["latency_s"] for r in model_results) / len(model_results)
            if model_results
            else 0
        )
        errors = sum(1 for r in model_results if r.get("error"))
        print(f"\n  {model['label']}:")
        print(f"    Total tokens: {total_in} in / {total_out} out")
        print(f"    Avg latency:  {avg_latency:.2f}s")
        print(f"    Errors:       {errors}/{len(model_results)}")


if __name__ == "__main__":
    main()
