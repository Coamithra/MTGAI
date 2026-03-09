"""Experiment 6: Validation-Retry Loop

Take cards that failed validation in previous experiments, feed errors back
to the LLM, and measure convergence. Tests whether retry with specific
feedback improves card quality.

Uses: T=1.0 (exp1 winner), FS=0 (exp2 winner)

Usage:
    python research/scripts/exp6_retry_loop.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "research/scripts")
from cached_llm import CachedLLM, CARD_TOOL_SCHEMA
from exp1_temperature_sweep import (
    SYSTEM_PROMPT,
    CARD_SLOTS,
    score_card,
    parse_cards_from_result,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-20250514"
TEMPERATURE = 1.0
MAX_RETRIES = 3
OUTPUT_DIR = Path("research/prompt-templates/experiments/exp6_retry")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Cards that had failures in exp1 (T=1.0) — the ones we want to retry
PROBLEM_CARDS = [
    {
        "slot": 9,   # Black mythic — "missing_period"
        "card": CARD_SLOTS[8],
        "original_failures": ["missing_period", "mythic_creature_not_legendary"],
    },
    {
        "slot": 12,  # Red mythic — "missing_period", "mythic_creature_not_legendary"
        "card": CARD_SLOTS[11],
        "original_failures": ["missing_period", "mythic_creature_not_legendary"],
    },
    {
        "slot": 14,  # Green common creature — "overstatted_common"
        "card": CARD_SLOTS[13],
        "original_failures": ["overstatted_common"],
    },
    {
        "slot": 15,  # Green uncommon enchantment — potential color pie issues
        "card": CARD_SLOTS[14],
        "original_failures": ["color_pie_violation_draw a card"],
    },
    {
        "slot": 22,  # Saga — complex templating
        "card": CARD_SLOTS[21],
        "original_failures": [],  # May have subtle issues
    },
    {
        "slot": 20,  # Planeswalker — complex templating
        "card": CARD_SLOTS[19],
        "original_failures": ["missing_period"],
    },
    {
        "slot": 24,  # Basic land — "generic_or_existing_name"
        "card": CARD_SLOTS[23],
        "original_failures": ["generic_or_existing_name"],
    },
]


VALIDATION_ERROR_DESCRIPTIONS = {
    "missing_period": (
        "[HARD] Missing period at end of ability text. "
        "Every ability in oracle_text must end with a period."
    ),
    "mythic_creature_not_legendary": (
        "[SOFT] Mythic creatures should be Legendary. "
        "Add 'Legendary' to the type_line for mythic creatures."
    ),
    "overstatted_common": (
        "[HARD] Common creature has power+toughness exceeding CMC+3. "
        "Reduce stats or increase mana cost. Commons should be fairly statted."
    ),
    "color_pie_violation_draw a card": (
        "[HARD] Color pie violation: green cards should not draw cards unconditionally. "
        "Green draws are tied to creatures (e.g., 'draw cards equal to the greatest power')."
    ),
    "generic_or_existing_name": (
        "[HARD] Card name is generic or matches an existing MTG card. "
        "Create a unique, evocative fantasy name."
    ),
    "old_etb_wording": (
        "[HARD] Old ETB wording. Use 'When ~ enters' not 'When ~ enters the battlefield'."
    ),
    "generic_flavor": (
        "[SOFT] Flavor text is generic. Make it specific, evocative, and world-building."
    ),
}


def build_initial_prompt(slot: dict) -> str:
    """Build single-card generation prompt."""
    return (
        f"Generate a single Magic: The Gathering card.\n\n"
        f"**Requirements**:\n"
        f"- Color: {slot['color']}\n"
        f"- Rarity: {slot['rarity']}\n"
        f"- Type: {slot['type']}\n"
        f"- Complexity: {slot['complexity']}\n"
        f"- Role: {slot['notes']}\n\n"
        f"IMPORTANT:\n"
        f"- Mythic creatures MUST have 'Legendary' in the type line.\n"
        f"- Every ability must end with a period.\n"
        f"- Use 'When ~ enters' (NOT 'enters the battlefield').\n"
        f"- Card names must be unique and original (not existing MTG card names).\n"
        f"- For basic lands, the name must be 'Forest' (this is mandatory for basic lands).\n"
        f"  But add evocative, unique flavor text.\n"
    )


def build_retry_prompt(
    slot: dict,
    previous_card: dict,
    failures: list[str],
) -> str:
    """Build a retry prompt with specific validation feedback."""
    error_lines = []
    for fm in failures:
        desc = VALIDATION_ERROR_DESCRIPTIONS.get(fm, f"[ISSUE] {fm}")
        error_lines.append(f"  - {desc}")

    card_json = json.dumps(previous_card, indent=2)

    return (
        f"Your previous card attempt had validation errors. "
        f"Please regenerate with corrections.\n\n"
        f"**Previous card**:\n{card_json}\n\n"
        f"**Validation errors found**:\n"
        + "\n".join(error_lines) +
        f"\n\n**Original requirements**:\n"
        f"- Color: {slot['color']}\n"
        f"- Rarity: {slot['rarity']}\n"
        f"- Type: {slot['type']}\n"
        f"- Complexity: {slot['complexity']}\n"
        f"- Role: {slot['notes']}\n\n"
        f"Fix ALL listed issues. Keep what works. Regenerate the card.\n"
    )


# ---------------------------------------------------------------------------
# Main experiment runner
# ---------------------------------------------------------------------------

def run_experiment():
    llm = CachedLLM()
    all_retry_data = []

    for problem in PROBLEM_CARDS:
        slot = problem["card"]
        slot_num = problem["slot"]

        print(f"\n{'='*60}")
        print(f"Slot {slot_num}: {slot['type']} ({slot['color']}, {slot['rarity']})")
        print(f"Known issues: {problem['original_failures']}")
        print(f"{'='*60}")

        retry_history = []

        # Initial generation
        prompt = build_initial_prompt(slot)
        result = llm.generate(
            model=MODEL,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=TEMPERATURE,
            tool_schema=CARD_TOOL_SCHEMA,
            max_tokens=4096,
        )

        card_data = result.parse_json()
        if not card_data:
            try:
                card_data = json.loads(result.content)
            except json.JSONDecodeError:
                print(f"  PARSE ERROR on initial generation")
                card_data = {}

        score_result = score_card(card_data, slot)
        failures = score_result["failure_modes"]
        avg_score = sum(score_result["scores"].values()) / len(score_result["scores"])

        hit = "CACHE" if result.cache_hit else f"${result.cost_usd:.4f}"
        print(f"  Attempt 0: '{card_data.get('name', '?')}' avg={avg_score:.1f} "
              f"failures={failures} ({hit})")

        retry_entry = {
            "attempt": 0,
            "card": card_data,
            "scores": score_result["scores"],
            "failures": failures,
            "avg_score": avg_score,
            "cost_usd": result.cost_usd,
            "cache_hit": result.cache_hit,
        }
        retry_history.append(retry_entry)

        if not result.cache_hit:
            time.sleep(0.5)

        # Retry loop
        current_card = card_data
        current_failures = failures

        for retry_num in range(1, MAX_RETRIES + 1):
            if not current_failures:
                print(f"  No failures — skipping retries")
                break

            retry_prompt = build_retry_prompt(slot, current_card, current_failures)

            # Use slightly lower temperature for retries
            retry_temp = 0.5

            result = llm.generate(
                model=MODEL,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=retry_prompt,
                temperature=retry_temp,
                tool_schema=CARD_TOOL_SCHEMA,
                max_tokens=4096,
            )

            card_data = result.parse_json()
            if not card_data:
                try:
                    card_data = json.loads(result.content)
                except json.JSONDecodeError:
                    print(f"  PARSE ERROR on retry {retry_num}")
                    card_data = current_card  # Keep the previous attempt

            score_result = score_card(card_data, slot)
            new_failures = score_result["failure_modes"]
            new_avg = sum(score_result["scores"].values()) / len(score_result["scores"])

            hit = "CACHE" if result.cache_hit else f"${result.cost_usd:.4f}"
            print(f"  Attempt {retry_num}: '{card_data.get('name', '?')}' avg={new_avg:.1f} "
                  f"failures={new_failures} ({hit})")

            # Check which failures were fixed
            fixed = set(current_failures) - set(new_failures)
            new_issues = set(new_failures) - set(current_failures)
            if fixed:
                print(f"    Fixed: {fixed}")
            if new_issues:
                print(f"    NEW issues: {new_issues}")

            retry_entry = {
                "attempt": retry_num,
                "card": card_data,
                "scores": score_result["scores"],
                "failures": new_failures,
                "avg_score": new_avg,
                "cost_usd": result.cost_usd,
                "cache_hit": result.cache_hit,
                "fixed_issues": list(fixed),
                "new_issues": list(new_issues),
            }
            retry_history.append(retry_entry)

            current_card = card_data
            current_failures = new_failures

            if not result.cache_hit:
                time.sleep(0.5)

        # Summary for this card
        initial_score = retry_history[0]["avg_score"]
        final_score = retry_history[-1]["avg_score"]
        initial_failures = len(retry_history[0]["failures"])
        final_failures = len(retry_history[-1]["failures"])
        total_retries = len(retry_history) - 1

        print(f"\n  Summary: {initial_score:.1f} -> {final_score:.1f} "
              f"({initial_failures} -> {final_failures} failures) "
              f"in {total_retries} retries")

        all_retry_data.append({
            "slot": slot_num,
            "slot_info": {
                "color": slot["color"],
                "rarity": slot["rarity"],
                "type": slot["type"],
                "complexity": slot["complexity"],
            },
            "retry_history": retry_history,
            "converged": final_failures == 0,
            "retries_needed": total_retries,
            "score_improvement": final_score - initial_score,
            "failures_fixed": initial_failures - final_failures,
        })

    # Save results
    save_path = OUTPUT_DIR / "exp6_raw_results.json"
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(all_retry_data, f, indent=2, ensure_ascii=False)
    print(f"\nRaw results saved to {save_path}")

    # Generate summary
    summary = generate_summary(all_retry_data)
    summary_path = OUTPUT_DIR / "exp6_summary.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)
    print(f"Summary saved to {summary_path}")

    stats = llm.stats()
    print(f"\nCache stats: {json.dumps(stats, indent=2)}")


def generate_summary(retry_data: list) -> str:
    """Generate markdown summary of retry experiment."""
    lines = ["# Experiment 6: Validation-Retry Loop — Summary\n"]
    lines.append(f"**Model**: {MODEL}")
    lines.append(f"**Initial temperature**: {TEMPERATURE}")
    lines.append(f"**Retry temperature**: 0.5")
    lines.append(f"**Max retries**: {MAX_RETRIES}")
    lines.append(f"**Cards tested**: {len(retry_data)}\n")

    # Overall stats
    total_converged = sum(1 for r in retry_data if r["converged"])
    avg_retries = sum(r["retries_needed"] for r in retry_data) / len(retry_data)
    avg_improvement = sum(r["score_improvement"] for r in retry_data) / len(retry_data)

    total_cost = sum(
        entry["cost_usd"]
        for r in retry_data
        for entry in r["retry_history"]
        if not entry["cache_hit"]
    )

    lines.append("---\n")
    lines.append("## Overall Results\n")
    lines.append(f"- **Convergence rate**: {total_converged}/{len(retry_data)} "
                 f"({total_converged/len(retry_data)*100:.0f}%) fully fixed within {MAX_RETRIES} retries")
    lines.append(f"- **Average retries needed**: {avg_retries:.1f}")
    lines.append(f"- **Average score improvement**: {avg_improvement:+.2f}")
    lines.append(f"- **Total API cost for retries**: ${total_cost:.4f}")
    lines.append("")

    # Per-card breakdown
    lines.append("## Per-Card Retry Results\n")
    lines.append("| Slot | Type | Initial Score | Final Score | "
                 "Initial Failures | Final Failures | Retries | Converged |")
    lines.append("|------|------|--------------|-------------|"
                 "----------------|----------------|---------|-----------|")

    for r in retry_data:
        initial = r["retry_history"][0]
        final = r["retry_history"][-1]
        lines.append(
            f"| {r['slot']} | {r['slot_info']['type']} ({r['slot_info']['color']}) | "
            f"{initial['avg_score']:.1f} | {final['avg_score']:.1f} | "
            f"{len(initial['failures'])} | {len(final['failures'])} | "
            f"{r['retries_needed']} | {'Yes' if r['converged'] else 'No'} |"
        )
    lines.append("")

    # Detailed retry chains
    lines.append("## Retry Chains\n")
    for r in retry_data:
        info = r["slot_info"]
        lines.append(f"### Slot {r['slot']}: {info['type']} ({info['color']} {info['rarity']})\n")
        for entry in r["retry_history"]:
            name = entry["card"].get("name", "?")
            lines.append(
                f"- **Attempt {entry['attempt']}**: '{name}' — "
                f"avg={entry['avg_score']:.1f}, failures={entry['failures']}"
            )
            if entry.get("fixed_issues"):
                lines.append(f"  - Fixed: {entry['fixed_issues']}")
            if entry.get("new_issues"):
                lines.append(f"  - New: {entry['new_issues']}")
        lines.append("")

    # Failure mode fix rates
    lines.append("## Failure Mode Fix Rates\n")
    failure_attempts = {}
    for r in retry_data:
        initial_failures = set(r["retry_history"][0]["failures"])
        final_failures = set(r["retry_history"][-1]["failures"])
        for fm in initial_failures:
            if fm not in failure_attempts:
                failure_attempts[fm] = {"total": 0, "fixed": 0}
            failure_attempts[fm]["total"] += 1
            if fm not in final_failures:
                failure_attempts[fm]["fixed"] += 1

    if failure_attempts:
        lines.append("| Failure Mode | Attempts | Fixed | Fix Rate |")
        lines.append("|-------------|----------|-------|----------|")
        for fm, data in sorted(failure_attempts.items()):
            rate = data["fixed"] / data["total"] * 100 if data["total"] > 0 else 0
            lines.append(f"| {fm} | {data['total']} | {data['fixed']} | {rate:.0f}% |")
    lines.append("")

    # Recommendation
    lines.append("## Recommendation\n")
    if total_converged / len(retry_data) >= 0.6:
        lines.append(
            f"Retry loop is **effective** — {total_converged}/{len(retry_data)} cards converge. "
            f"Use validation-retry in Phase 1C with max {MAX_RETRIES} attempts."
        )
    else:
        lines.append(
            f"Retry loop has **limited effectiveness** — only {total_converged}/{len(retry_data)} converge. "
            f"Consider prompt improvements over retry-based fixes."
        )
    lines.append(f"\n**Total API cost**: ${total_cost:.4f}")

    return "\n".join(lines)


if __name__ == "__main__":
    run_experiment()
