"""Quick test script to verify Anthropic and OpenAI API keys are working.

Usage: python research/scripts/test_api_keys.py
Reads API keys from .env file in project root.
"""

import os
import sys
from pathlib import Path

# Load .env from project root
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def test_anthropic():
    try:
        import anthropic

        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=50,
            messages=[{"role": "user", "content": "Say 'API test successful' in exactly those words."}],
        )
        text = resp.content[0].text
        print(f"  Anthropic (Claude Sonnet): OK — {text}")
        print(f"  Tokens: {resp.usage.input_tokens} in, {resp.usage.output_tokens} out")
        return True
    except Exception as e:
        print(f"  Anthropic: FAILED — {e}")
        return False


def test_openai():
    try:
        from openai import OpenAI

        client = OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=50,
            messages=[
                {"role": "user", "content": "Say 'API test successful' in exactly those words."}
            ],
        )
        text = resp.choices[0].message.content
        print(f"  OpenAI (GPT-4o-mini): OK — {text}")
        print(f"  Tokens: {resp.usage.prompt_tokens} in, {resp.usage.completion_tokens} out")
        return True
    except Exception as e:
        print(f"  OpenAI: FAILED — {e}")
        return False


if __name__ == "__main__":
    print("Testing API keys...\n")
    results = {}
    results["anthropic"] = test_anthropic()
    print()
    results["openai"] = test_openai()
    print()

    passed = sum(results.values())
    total = len(results)
    print(f"Result: {passed}/{total} APIs working")

    if not all(results.values()):
        failed = [k for k, v in results.items() if not v]
        print(f"Failed: {', '.join(failed)}")
        print("Check your .env file for missing or invalid API keys.")
        sys.exit(1)
