#!/usr/bin/env python
"""A/B test runner for card review-and-revise strategies.

Usage:
    uv run --directory backend python research/scripts/ab-test/run_strategy.py <strategy_number>

    strategy_number: 1-8
    1=Simple/Sonnet, 2=Iterative/Sonnet, 3=Detailed/Sonnet, 4=Split/Sonnet
    5=Simple/Opus,   6=Iterative/Opus,   7=Detailed/Opus,   8=Split/Opus
"""

import json
import os
import sys
import time
from pathlib import Path

from anthropic import Anthropic

# ── Config ────────────────────────────────────────────────────────────────────

ROOT = Path("C:/Programming/MTGAI")
CARDS_PATH = ROOT / "output/sets/ASD/mechanics/test-cards-original.json"
OUTPUT_BASE = ROOT / "output/sets/ASD/mechanics/ab-test"

SONNET = "claude-sonnet-4-20250514"
OPUS = "claude-opus-4-20250514"

PRICING = {  # USD per million tokens
    SONNET: {"input": 3.0, "output": 15.0},
    OPUS: {"input": 15.0, "output": 75.0},
}

STRATEGIES = {
    1: {"name": "s1-simple-sonnet", "model": SONNET, "type": "simple"},
    2: {"name": "s2-iterative-sonnet", "model": SONNET, "type": "iterative"},
    3: {"name": "s3-detailed-sonnet", "model": SONNET, "type": "detailed"},
    4: {"name": "s4-split-sonnet", "model": SONNET, "type": "split"},
    5: {"name": "s5-simple-opus", "model": OPUS, "type": "simple"},
    6: {"name": "s6-iterative-opus", "model": OPUS, "type": "iterative"},
    7: {"name": "s7-detailed-opus", "model": OPUS, "type": "detailed"},
    8: {"name": "s8-split-opus", "model": OPUS, "type": "split"},
}

# 0-based indices into test-cards-original.json
TEST_INDICES = [1, 4, 5, 6, 10, 13, 14]

CARD_REPORT_NAMES = {
    1: "card-02-undergrowth-scrounger",
    4: "card-05-subsurface-expedition-leader",
    5: "card-06-defective-labor-drone",
    6: "card-07-unstable-welding-unit",
    10: "card-11-synaptic-overload",
    13: "card-14-cascade-protocol",
    14: "card-15-archscientist-vex",
}

CARD_NUMBERS = {1: 2, 4: 5, 5: 6, 6: 7, 10: 11, 13: 14, 14: 15}

REVISED_CARD_TOOL = {
    "name": "submit_revised_card",
    "description": (
        "Submit the final revised card, or the original card unchanged "
        "if no issues were found."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "changed": {
                "type": "boolean",
                "description": "True if the card was modified, False if returned as-is.",
            },
            "verdict": {
                "type": "string",
                "enum": ["OK", "REVISED", "UNFIXABLE"],
                "description": "OK=no changes needed. REVISED=fixed. UNFIXABLE=needs human.",
            },
            "issues_found": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of issues identified (empty if OK).",
            },
            "name": {"type": "string"},
            "mana_cost": {"type": "string"},
            "type_line": {"type": "string"},
            "oracle_text": {"type": "string"},
            "power": {"type": ["string", "null"]},
            "toughness": {"type": ["string", "null"]},
            "rarity": {"type": "string"},
            "flavor_text": {"type": ["string", "null"]},
        },
        "required": [
            "changed", "verdict", "issues_found",
            "name", "mana_cost", "type_line", "oracle_text", "rarity",
        ],
    },
}

MECHANIC_DEFS = """Custom mechanics for this set:

**Salvage X** (keyword_ability)
Reminder text: (Look at the top X cards of your library. You may put an artifact card from among \
them into your hand. Put the rest on the bottom of your library in any order.)
Scaling: 2-3 at common, 4-5 at uncommon, 6+ at rare/mythic.
Colors: W, U, G. Complexity: 1 (common-viable).

**Malfunction N** (keyword_ability)
Reminder text: (This permanent enters tapped with N malfunction counters on it. At the beginning \
of your upkeep, remove a malfunction counter from it.)
Scaling: 1 at common, 2 at uncommon, 2-3 at rare/mythic.
Colors: W, U, R. Complexity: 2.
Design note: Enters tapped is the key tempo cost. Cards with malfunction are intentionally \
above-rate for their mana cost.

**Overclock** (keyword_action)
Reminder text: (Exile the top three cards of your library. You may play them until end of turn.)
Colors: U, R, B. Complexity: 3 (uncommon+ only, never at common).
Design note: High risk/reward. Always exiles exactly 3 cards."""

STRATEGY_DESCS = {
    "simple": (
        "Single prompt: review card and return revised version or OK. "
        "One API call per card."
    ),
    "iterative": (
        "Same prompt as Simple, but if REVISED, feed revised card back. "
        "Loop until OK or max 5 iterations. Fresh conversation each iteration."
    ),
    "detailed": (
        "Two-step: first call gets detailed analysis against a comprehensive checklist "
        "(templating, keyword interactions, balance, design, color pie). "
        "Second call submits the revised card via tool_use. Two API calls per card."
    ),
    "split": (
        "Three separate review passes (templating, mechanics, balance) followed by "
        "a single revision call combining all feedback. Four API calls per card."
    ),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_env():
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def format_card(card):
    """Format a card dict as text for prompts (no metadata)."""
    lines = [
        f"Name: {card['name']}",
        f"Mana Cost: {card['mana_cost']}",
        f"Type: {card['type_line']}",
        f"Rarity: {card['rarity']}",
        f"Oracle Text: {card['oracle_text']}",
    ]
    if card.get("power") is not None:
        lines.append(f"P/T: {card['power']}/{card['toughness']}")
    if card.get("flavor_text"):
        lines.append(f"Flavor Text: {card['flavor_text']}")
    return "\n".join(lines)


def card_display_json(card):
    """Pretty-print card for report display (no internal metadata)."""
    display = {}
    for key in [
        "name", "mana_cost", "cmc", "colors", "type_line", "oracle_text",
        "power", "toughness", "rarity", "keywords", "flavor_text",
    ]:
        if key in card and card[key] is not None:
            display[key] = card[key]
    return json.dumps(display, indent=2)


def calc_cost(model, input_tokens, output_tokens):
    p = PRICING[model]
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


def tool_result_to_card(result, original):
    """Convert tool_use result back to a card dict for iterative passes."""
    return {
        "name": result.get("name", original["name"]),
        "mana_cost": result.get("mana_cost", original["mana_cost"]),
        "type_line": result.get("type_line", original["type_line"]),
        "oracle_text": result.get("oracle_text", original["oracle_text"]),
        "power": result.get("power"),
        "toughness": result.get("toughness"),
        "rarity": result.get("rarity", original["rarity"]),
        "flavor_text": result.get("flavor_text", original.get("flavor_text")),
    }


# ── API calls ─────────────────────────────────────────────────────────────────

def call_with_tool(client, model, system, user, max_tokens=8192):
    """API call with forced tool_use. Returns (tool_input, text_parts, usage)."""
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=1.0,
        system=system,
        messages=[{"role": "user", "content": user}],
        tools=[REVISED_CARD_TOOL],
        tool_choice={"type": "tool", "name": "submit_revised_card"},
    )
    text_parts = [b.text for b in resp.content if b.type == "text"]
    tool_input = None
    for b in resp.content:
        if b.type == "tool_use":
            tool_input = b.input
    if tool_input is None:
        raise ValueError("No tool_use block in response")
    return tool_input, text_parts, resp.usage


def call_text(client, model, system, user, max_tokens=4096):
    """API call for text response. Returns (text, usage)."""
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=1.0,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "\n".join(b.text for b in resp.content if b.type == "text")
    return text, resp.usage


# ── Strategy implementations ──────────────────────────────────────────────────
# Each returns (steps: list[dict], result: dict)

def run_simple(client, card, model, _mech_text):
    system = (
        'You are a senior Magic: The Gathering card designer reviewing cards '
        'for the set "Anomalous Descent."'
    )
    user = f"""{MECHANIC_DEFS}

Card to review:
{format_card(card)}

Critically review this card and provide an improved version based on your \
findings. If the card is fine, return it unchanged with verdict OK."""

    tool_input, text_parts, usage = call_with_tool(client, model, system, user)
    steps = [{
        "description": "Review and revise (single pass)",
        "prompt": user,
        "response": "\n".join(text_parts) if text_parts else "",
        "tool_result": tool_input,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
    }]
    return steps, tool_input


def run_iterative(client, card, model, _mech_text):
    system = (
        'You are a senior Magic: The Gathering card designer reviewing cards '
        'for the set "Anomalous Descent."'
    )
    current = card
    steps = []
    result = None

    for i in range(5):
        user = f"""{MECHANIC_DEFS}

Card to review:
{format_card(current)}

Critically review this card and provide an improved version based on your \
findings. If the card is fine, return it unchanged with verdict OK."""

        tool_input, text_parts, usage = call_with_tool(client, model, system, user)
        steps.append({
            "description": f"Iteration {i + 1}",
            "prompt": user,
            "response": "\n".join(text_parts) if text_parts else "",
            "tool_result": tool_input,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        })
        result = tool_input

        if tool_input.get("verdict") == "OK":
            break

        current = tool_result_to_card(tool_input, card)
        time.sleep(1)

    return steps, result


def run_detailed(client, card, model, _mech_text):
    """Two-step: detailed text analysis, then tool submission."""
    system = (
        'You are a senior Magic: The Gathering card designer reviewing cards '
        'for the set "Anomalous Descent."'
    )

    # Step 1: Detailed review (text response)
    review_prompt = f"""{MECHANIC_DEFS}

Card to review:
{format_card(card)}

Review this card thoroughly. At minimum, check every criterion below \
(state PASS or describe the issue for each), but also flag anything else \
you notice.

**Templating & Rules Text:**
- Is the oracle text valid MTG rules text?
- Does every custom mechanic (salvage, malfunction, overclock) have reminder \
text on first use?
- Is capitalization consistent (keyword capitalized at start of ability, \
lowercase mid-sentence)?
- Does the card use current MTG templating ("enters" not "enters the \
battlefield")?

**Keyword Interactions:**
- Are there any keywords that are negated or made useless by other abilities? \
(e.g., haste on a creature that always enters tapped)
- If there's a conditional ("if you X this turn"), can the condition actually \
be false during normal play?

**Balance:**
- Is the power level appropriate for the mana cost AND rarity? Compare to \
2-3 well-known printed MTG cards at similar cost.
- Note: malfunction cards are intentionally above-rate — the delayed entry \
IS the drawback.

**Design:**
- Does the card have a focused purpose, or is it kitchen sink (3+ unrelated \
effects)?
- If effects are variable (deal X damage, etc.), is the variability real or \
does it always resolve to the same value?
- Does the card create interesting gameplay decisions?

**Color Pie:**
- Are all abilities appropriate for this card's color(s)?

Provide your detailed analysis for each criterion."""

    review_text, review_usage = call_text(client, model, system, review_prompt)
    steps = [{
        "description": "Detailed review analysis",
        "prompt": review_prompt,
        "response": review_text,
        "input_tokens": review_usage.input_tokens,
        "output_tokens": review_usage.output_tokens,
    }]

    time.sleep(1)

    # Step 2: Submit revised card (tool call)
    revision_prompt = f"""Based on the following review of a card, submit the revised card. \
If no issues were found, return the card unchanged with verdict OK.

Original card:
{format_card(card)}

Review findings:
{review_text}"""

    tool_input, text_parts, tool_usage = call_with_tool(client, model, system, revision_prompt)
    steps.append({
        "description": "Submit revised card based on review",
        "prompt": revision_prompt,
        "response": "\n".join(text_parts) if text_parts else "",
        "tool_result": tool_input,
        "input_tokens": tool_usage.input_tokens,
        "output_tokens": tool_usage.output_tokens,
    })

    return steps, tool_input


def run_split(client, card, model, _mech_text):
    steps = []
    findings = {}

    # Pass 1: Templating
    sys1 = (
        "You are an MTG rules text editor. Focus primarily on the templating "
        "and wording of this custom card, but flag anything else you notice."
    )
    usr1 = f"""{MECHANIC_DEFS}

Card:
{format_card(card)}

Check:
- Is the oracle text valid MTG rules text using current templating conventions?
- Does every custom mechanic (salvage, malfunction, overclock) include \
reminder text in parentheses on its first use?
- Is keyword capitalization consistent?
- Are ability words, keyword abilities, and keyword actions used correctly?

List any templating issues found, or say "PASS" if the templating is correct."""

    text1, usage1 = call_text(client, model, sys1, usr1)
    steps.append({
        "description": "Pass 1 — Templating review",
        "prompt": usr1,
        "response": text1,
        "input_tokens": usage1.input_tokens,
        "output_tokens": usage1.output_tokens,
    })
    findings["templating"] = text1
    time.sleep(1)

    # Pass 2: Mechanics
    sys2 = (
        "You are an MTG game designer. Focus primarily on the gameplay "
        "mechanics and design of this custom card, but flag anything else you notice."
    )
    usr2 = f"""{MECHANIC_DEFS}

Card:
{format_card(card)}

Check:
- Are there any keyword nonbos (keywords negated by other abilities on the card)?
- If there's a conditional, can it actually be false during normal play?
- Is this kitchen sink design (3+ unrelated effects piled together)?
- If effects are variable, is the variability real or always the same value?
- Does the design have a focused purpose?

List any design issues found, or say "PASS" if the design is sound."""

    text2, usage2 = call_text(client, model, sys2, usr2)
    steps.append({
        "description": "Pass 2 — Mechanics review",
        "prompt": usr2,
        "response": text2,
        "input_tokens": usage2.input_tokens,
        "output_tokens": usage2.output_tokens,
    })
    findings["mechanics"] = text2
    time.sleep(1)

    # Pass 3: Balance
    sys3 = (
        "You are an MTG development/play design expert. Focus primarily on the "
        "power level of this custom card, but flag anything else you notice."
    )
    usr3 = f"""{MECHANIC_DEFS}

Card:
{format_card(card)}

Check:
- Is the power level appropriate for the mana cost AND rarity?
- Compare to 2-3 well-known printed MTG cards at similar mana cost and rarity.
- Note: malfunction cards are intentionally above-rate — the delayed entry \
IS the drawback. Do not flag these for being above-rate.
- Note: mythic rares are allowed to be powerful build-arounds. Do not nerf \
mythics to rare power level.

State whether the balance is PASS, or describe the specific balance issue \
with card comparisons."""

    text3, usage3 = call_text(client, model, sys3, usr3)
    steps.append({
        "description": "Pass 3 — Balance review",
        "prompt": usr3,
        "response": text3,
        "input_tokens": usage3.input_tokens,
        "output_tokens": usage3.output_tokens,
    })
    findings["balance"] = text3
    time.sleep(1)

    # Pass 4: Revision
    sys4 = (
        "You are a senior MTG card designer. Revise this card based on the "
        "following review feedback."
    )
    usr4 = f"""{MECHANIC_DEFS}

Original card:
{format_card(card)}

Issues found:
- Templating: {findings['templating']}
- Mechanics: {findings['mechanics']}
- Balance: {findings['balance']}

Produce a revised version that fixes all identified issues while preserving \
the card's core identity and purpose. Do not change things that weren't \
flagged as issues. If all reviews said PASS, return the card unchanged \
with verdict OK."""

    tool_input, text_parts, usage4 = call_with_tool(client, model, sys4, usr4)
    steps.append({
        "description": "Pass 4 — Revision (combining all feedback)",
        "prompt": usr4,
        "response": "\n".join(text_parts) if text_parts else "",
        "tool_result": tool_input,
        "input_tokens": usage4.input_tokens,
        "output_tokens": usage4.output_tokens,
    })

    return steps, tool_input


# ── Report generation ─────────────────────────────────────────────────────────

def write_card_report(out_dir, card_idx, card, strategy_name, model, steps, result):
    """Write per-card markdown report. Returns (total_in, total_out, total_cost)."""
    card_num = CARD_NUMBERS[card_idx]
    filename = CARD_REPORT_NAMES[card_idx] + ".md"

    lines = [f"# Card {card_num}: {card['name']} — Strategy: {strategy_name}\n"]

    # A) Original Card
    lines.append("## A) Original Card\n")
    lines.append(f"```json\n{card_display_json(card)}\n```\n")

    # B) Review Process
    lines.append("## B) Review Process\n")
    for i, step in enumerate(steps, 1):
        lines.append(f"### Step {i}: {step['description']}\n")

        lines.append("**Prompt sent:**")
        for pline in step["prompt"].split("\n"):
            lines.append(f"> {pline}")
        lines.append("")

        if step.get("response"):
            lines.append("**Response:**")
            for rline in step["response"].split("\n"):
                lines.append(f"> {rline}")
            lines.append("")

        if step.get("tool_result"):
            lines.append("**Tool call result:**")
            lines.append(f"```json\n{json.dumps(step['tool_result'], indent=2)}\n```\n")

        cost = calc_cost(model, step["input_tokens"], step["output_tokens"])
        lines.append(
            f"*Tokens: {step['input_tokens']} in / {step['output_tokens']} out "
            f"— ${cost:.4f}*\n"
        )

    # C) Revised Card
    lines.append("## C) Revised Card\n")
    if result.get("changed"):
        revised = {"name": result.get("name"), "mana_cost": result.get("mana_cost")}
        revised["type_line"] = result.get("type_line")
        revised["oracle_text"] = result.get("oracle_text")
        revised["rarity"] = result.get("rarity")
        if result.get("power") is not None:
            revised["power"] = result["power"]
            revised["toughness"] = result.get("toughness")
        if result.get("flavor_text") is not None:
            revised["flavor_text"] = result["flavor_text"]
        lines.append(f"```json\n{json.dumps(revised, indent=2)}\n```\n")
        lines.append("**Changes made:**")
        for issue in result.get("issues_found", []):
            lines.append(f"- {issue}")
        lines.append("")
    else:
        lines.append("No changes (OK)\n")
        lines.append("**Changes made:**\n- None\n")

    # D) Cost
    total_in = sum(s["input_tokens"] for s in steps)
    total_out = sum(s["output_tokens"] for s in steps)
    total_cost = calc_cost(model, total_in, total_out)
    lines.append("## D) Cost\n")
    lines.append(f"- API calls: {len(steps)}")
    lines.append(f"- Input tokens: {total_in}")
    lines.append(f"- Output tokens: {total_out}")
    lines.append(f"- Cost: ${total_cost:.4f}")

    (out_dir / filename).write_text("\n".join(lines), encoding="utf-8")
    return total_in, total_out, total_cost


def write_summary(out_dir, strategy_name, model, strategy_type, card_results):
    """Write summary markdown report. Returns total_cost."""
    model_label = "Opus" if "opus" in model else "Sonnet"
    desc = f"{STRATEGY_DESCS[strategy_type]} Using {model_label}."

    lines = [f"# Strategy: {strategy_name}\n"]
    lines.append(f"## Description\n\n{desc}\n")

    # Quick counts
    verdicts = [r[3].get("verdict", "?") for r in card_results]
    lines.append("## Quick Results\n")
    for v in ["OK", "REVISED", "UNFIXABLE", "ERROR"]:
        count = verdicts.count(v)
        if count:
            lines.append(f"- {v}: {count} cards")
    lines.append("")

    # Results table
    lines.append("## Results\n")
    lines.append("| Card | Verdict | Issues Found | Changed | Cost |")
    lines.append("|------|---------|-------------|---------|------|")

    total_calls = 0
    total_in = 0
    total_out = 0

    for card_idx, card, steps, result in card_results:
        card_num = CARD_NUMBERS[card_idx]
        name = card["name"]
        verdict = result.get("verdict", "?")
        issues = result.get("issues_found", [])
        issues_str = "; ".join(issues[:3]) if issues else "None"
        if len(issues_str) > 120:
            issues_str = issues_str[:117] + "..."
        changed = "Yes" if result.get("changed") else "No"

        n_in = sum(s["input_tokens"] for s in steps)
        n_out = sum(s["output_tokens"] for s in steps)
        cost = calc_cost(model, n_in, n_out)

        total_calls += len(steps)
        total_in += n_in
        total_out += n_out

        lines.append(f"| {card_num}. {name} | {verdict} | {issues_str} | {changed} | ${cost:.4f} |")

    total_cost = calc_cost(model, total_in, total_out)
    lines.append(f"\n## Total Cost\n")
    lines.append(f"- API calls: {total_calls}")
    lines.append(f"- Total tokens: {total_in} in / {total_out} out")
    lines.append(f"- Total cost: ${total_cost:.4f}")

    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    return total_cost


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) != 2 or sys.argv[1] not in [str(i) for i in range(1, 9)]:
        print(__doc__)
        sys.exit(1)

    strategy_num = int(sys.argv[1])
    config = STRATEGIES[strategy_num]
    strategy_name = config["name"]
    model = config["model"]
    strategy_type = config["type"]

    model_label = "Opus" if "opus" in model else "Sonnet"
    print(f"=== Strategy {strategy_num}: {strategy_name} ({model_label}) ===\n")

    load_env()
    client = Anthropic()

    all_cards = json.loads(CARDS_PATH.read_text())
    test_cards = [(idx, all_cards[idx]) for idx in TEST_INDICES]

    out_dir = OUTPUT_BASE / strategy_name
    out_dir.mkdir(parents=True, exist_ok=True)

    runner = {
        "simple": run_simple,
        "iterative": run_iterative,
        "detailed": run_detailed,
        "split": run_split,
    }[strategy_type]

    card_results = []
    for card_idx, card in test_cards:
        card_num = CARD_NUMBERS[card_idx]
        print(f"  Card {card_num}: {card['name']}...", end=" ", flush=True)

        try:
            steps, result = runner(client, card, model, MECHANIC_DEFS)
            card_results.append((card_idx, card, steps, result))

            tok_in, tok_out, cost = write_card_report(
                out_dir, card_idx, card, strategy_name, model, steps, result
            )
            print(f"{result.get('verdict', '?')} (${cost:.4f})")
        except Exception as e:
            print(f"ERROR: {e}")
            card_results.append((card_idx, card, [], {
                "changed": False, "verdict": "ERROR",
                "issues_found": [str(e)],
                "name": card["name"], "mana_cost": card["mana_cost"],
                "type_line": card["type_line"], "oracle_text": card["oracle_text"],
                "rarity": card["rarity"],
            }))

        time.sleep(1)  # Rate limiting

    total_cost = write_summary(out_dir, strategy_name, model, strategy_type, card_results)

    print(f"\nDone! Total cost: ${total_cost:.4f}")
    print(f"Output: {out_dir}")


if __name__ == "__main__":
    main()
