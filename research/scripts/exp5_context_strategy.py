"""Experiment 5: Context Strategy

Test how set context affects duplicate avoidance and card coherence.
Strategy: Generate 10 cards with no context, then 14 more with 4 different
context strategies. Measure duplicates, conflicts, and quality.

Uses: T=1.0 (exp1 winner), FS=0 (exp2 winner)

Usage:
    python research/scripts/exp5_context_strategy.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "research/scripts")
from cached_llm import CachedLLM, CARDS_BATCH_TOOL_SCHEMA
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
OUTPUT_DIR = Path("research/prompt-templates/experiments/exp5_context")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Split: first 10 cards are the "existing" set, last 14 test context strategies
INITIAL_SLOTS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
TEST_SLOTS = [11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24]
TEST_BATCHES = [
    [11, 12, 13, 14, 15],
    [16, 17, 18, 19, 20],
    [21, 22, 23, 24],
]

CONTEXT_STRATEGIES = [
    "none",          # No context at all
    "names_only",    # Just the names of existing cards
    "compressed",    # Names + mana costs + one-line summaries + color stats
    "full_color",    # Full card JSON for same color
]


def build_initial_prompt(slot_indices: list[int]) -> str:
    """Build prompt for generating the initial 10 cards (no context)."""
    lines = [
        f"Generate {len(slot_indices)} Magic: The Gathering cards. "
        "Each card must fill a specific slot.\n"
    ]
    lines.append("**Slots to fill**:\n")
    for idx in slot_indices:
        card = CARD_SLOTS[idx - 1]
        lines.append(
            f"Slot {card['slot']}:\n"
            f"- Color: {card['color']}\n"
            f"- Rarity: {card['rarity']}\n"
            f"- Type: {card['type']}\n"
            f"- Complexity: {card['complexity']}\n"
            f"- Role: {card['notes']}\n"
        )
    lines.append("Output as JSON. Generate all cards. Every slot must be filled.")
    return "\n".join(lines)


def build_names_only_context(existing_cards: list[dict]) -> str:
    """Just card names."""
    names = [c.get("name", "Unknown") for c in existing_cards]
    return (
        "**Cards already in the set** (do NOT duplicate these names):\n"
        + ", ".join(names)
        + "\n"
    )


def build_compressed_context(existing_cards: list[dict]) -> str:
    """Names + mana costs + one-line summaries + color distribution."""
    lines = ["**Cards already in the set** (do NOT duplicate names or effects):\n"]
    for c in existing_cards:
        name = c.get("name", "?")
        mc = c.get("mana_cost", "")
        tl = c.get("type_line", "")
        oracle = c.get("oracle_text", "")
        summary = oracle[:60] + "..." if len(oracle) > 60 else oracle
        lines.append(f"- {name} ({mc}) — {tl} — {summary}")

    # Color distribution
    color_counts = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0}
    for c in existing_cards:
        for col in c.get("colors", []):
            if col in color_counts:
                color_counts[col] += 1
    lines.append(f"\n**Color distribution so far**: {color_counts}")
    lines.append(f"**Total cards**: {len(existing_cards)}\n")
    return "\n".join(lines)


def build_full_color_context(existing_cards: list[dict], target_colors: str) -> str:
    """Full card JSON for cards sharing a color with the target."""
    target_color_set = set(target_colors) if target_colors not in ("-", "C") else set()

    lines = ["**Cards already in the set matching your colors** (for reference):\n"]
    matched = []
    for c in existing_cards:
        card_colors = set(c.get("colors", []))
        if target_color_set & card_colors or (not target_color_set and not card_colors):
            matched.append(c)

    if matched:
        # Include full card JSON but without design_notes to save tokens
        for c in matched:
            display = {k: v for k, v in c.items() if k != "design_notes"}
            lines.append(json.dumps(display, indent=2))
            lines.append("")
    else:
        lines.append("(No matching cards yet)\n")

    # Also include names of all cards for dedup
    all_names = [c.get("name", "?") for c in existing_cards]
    lines.append(f"**All card names in the set** (do NOT duplicate): {', '.join(all_names)}\n")
    return "\n".join(lines)


def build_test_prompt(
    slot_indices: list[int],
    strategy: str,
    existing_cards: list[dict],
) -> str:
    """Build prompt for test batches with a given context strategy."""
    lines = [
        f"Generate {len(slot_indices)} Magic: The Gathering cards. "
        "Each card must fill a specific slot.\n"
    ]

    # Inject context based on strategy
    if strategy == "names_only":
        lines.append(build_names_only_context(existing_cards))
    elif strategy == "compressed":
        lines.append(build_compressed_context(existing_cards))
    elif strategy == "full_color":
        # Determine dominant color of this batch
        batch_colors = set()
        for idx in slot_indices:
            c = CARD_SLOTS[idx - 1]["color"]
            if c not in ("-", "C"):
                batch_colors.update(c)
        color_str = "".join(sorted(batch_colors)) if batch_colors else "C"
        lines.append(build_full_color_context(existing_cards, color_str))
    # "none" = no context added

    lines.append("**Slots to fill**:\n")
    for idx in slot_indices:
        card = CARD_SLOTS[idx - 1]
        lines.append(
            f"Slot {card['slot']}:\n"
            f"- Color: {card['color']}\n"
            f"- Rarity: {card['rarity']}\n"
            f"- Type: {card['type']}\n"
            f"- Complexity: {card['complexity']}\n"
            f"- Role: {card['notes']}\n"
        )
    lines.append("Output as JSON. Generate all cards. Every slot must be filled.")
    return "\n".join(lines)


def count_name_duplicates(initial_cards: list[dict], new_cards: list[dict]) -> list[str]:
    """Find duplicate names between initial and new cards."""
    initial_names = {c.get("name", "").lower() for c in initial_cards}
    duplicates = []
    for c in new_cards:
        name = c.get("name", "").lower()
        if name in initial_names:
            duplicates.append(c.get("name", ""))
    return duplicates


def count_similar_effects(initial_cards: list[dict], new_cards: list[dict]) -> list[str]:
    """Find cards with very similar oracle text."""
    similarities = []
    for nc in new_cards:
        nc_oracle = nc.get("oracle_text", "").lower()
        if not nc_oracle:
            continue
        for ic in initial_cards:
            ic_oracle = ic.get("oracle_text", "").lower()
            if not ic_oracle:
                continue
            # Simple similarity: check for substring overlap
            if len(nc_oracle) > 20 and len(ic_oracle) > 20:
                # Check if >60% of words overlap
                nc_words = set(nc_oracle.split())
                ic_words = set(ic_oracle.split())
                if len(nc_words) > 3 and len(ic_words) > 3:
                    overlap = nc_words & ic_words
                    similarity = len(overlap) / min(len(nc_words), len(ic_words))
                    if similarity > 0.6:
                        similarities.append(
                            f"'{nc.get('name')}' ~ '{ic.get('name')}' "
                            f"({similarity:.0%} word overlap)"
                        )
    return similarities


# ---------------------------------------------------------------------------
# Main experiment runner
# ---------------------------------------------------------------------------

def run_experiment():
    llm = CachedLLM()
    all_results = {}
    all_scores = []

    # Step 1: Generate the initial 10 cards (same for all strategies)
    print("=" * 60)
    print("Generating initial 10 cards (baseline, no context)")
    print("=" * 60)

    initial_batches = [
        [1, 2, 3, 4, 5],
        [6, 7, 8, 9, 10],
    ]
    initial_cards = []

    for batch_slots in initial_batches:
        prompt = build_initial_prompt(batch_slots)
        result = llm.generate(
            model=MODEL,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=TEMPERATURE,
            tool_schema=CARDS_BATCH_TOOL_SCHEMA,
            max_tokens=8192,
        )
        cards = parse_cards_from_result(result)
        initial_cards.extend(cards)
        hit = "CACHE HIT" if result.cache_hit else f"${result.cost_usd:.4f}"
        print(f"  Batch {batch_slots}: {len(cards)} cards ({hit})")
        for c in cards:
            print(f"    - {c.get('name', '?')}")
        if not result.cache_hit:
            time.sleep(1)

    print(f"\nInitial set: {len(initial_cards)} cards")
    print(f"Names: {[c.get('name') for c in initial_cards]}")

    # Step 2: Generate 14 test cards with each context strategy
    for strategy in CONTEXT_STRATEGIES:
        print(f"\n{'='*60}")
        print(f"Context strategy: {strategy}")
        print(f"{'='*60}")

        strategy_result = {
            "strategy": strategy,
            "batches": [],
            "new_cards": [],
        }

        for batch_slots in TEST_BATCHES:
            prompt = build_test_prompt(batch_slots, strategy, initial_cards)

            try:
                result = llm.generate(
                    model=MODEL,
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=prompt,
                    temperature=TEMPERATURE,
                    tool_schema=CARDS_BATCH_TOOL_SCHEMA,
                    max_tokens=8192,
                )

                cards = parse_cards_from_result(result)
                strategy_result["new_cards"].extend(cards)
                hit = "CACHE HIT" if result.cache_hit else f"${result.cost_usd:.4f}"
                print(f"  Batch {batch_slots}: {len(cards)} cards ({hit})")

                batch_data = {
                    "slots": batch_slots,
                    "cards": cards,
                    "cost_usd": result.cost_usd,
                    "cache_hit": result.cache_hit,
                    "tokens": {
                        "input": result.input_tokens,
                        "output": result.output_tokens,
                    },
                    "prompt_length": len(prompt),
                }
                strategy_result["batches"].append(batch_data)

                # Score each card
                for i, card in enumerate(cards):
                    slot_num = batch_slots[i] if i < len(batch_slots) else batch_slots[-1]
                    slot = CARD_SLOTS[slot_num - 1]
                    score_result = score_card(card, slot)

                    card_score = {
                        "card_slot": slot_num,
                        "strategy": strategy,
                        "card_name": card.get("name", "UNKNOWN"),
                        "scores": score_result["scores"],
                        "failure_modes": score_result["failure_modes"],
                    }
                    all_scores.append(card_score)

                    avg = sum(score_result["scores"].values()) / len(score_result["scores"])
                    fails = score_result["failure_modes"]
                    fail_str = f" [{', '.join(fails)}]" if fails else ""
                    print(f"    Card {slot_num} '{card.get('name', '?')}': avg={avg:.1f}{fail_str}")

                if not result.cache_hit:
                    time.sleep(1)

            except Exception as e:
                print(f"  ERROR: {e}")
                import traceback
                traceback.print_exc()

        # Analyze duplicates and similarities
        name_dupes = count_name_duplicates(initial_cards, strategy_result["new_cards"])
        similar = count_similar_effects(initial_cards, strategy_result["new_cards"])

        strategy_result["name_duplicates"] = name_dupes
        strategy_result["similar_effects"] = similar

        print(f"\n  Name duplicates with initial set: {len(name_dupes)} — {name_dupes}")
        print(f"  Similar effects: {len(similar)}")
        for s in similar:
            print(f"    {s}")

        all_results[strategy] = strategy_result

    # Save results
    save_path = OUTPUT_DIR / "exp5_raw_results.json"
    # Convert to serializable format
    save_data = {
        "initial_cards": initial_cards,
        "strategies": {k: {
            "strategy": v["strategy"],
            "batches": v["batches"],
            "name_duplicates": v["name_duplicates"],
            "similar_effects": v["similar_effects"],
        } for k, v in all_results.items()},
    }
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)
    print(f"\nRaw results saved to {save_path}")

    scores_path = OUTPUT_DIR / "exp5_scores.json"
    with open(scores_path, "w", encoding="utf-8") as f:
        json.dump(all_scores, f, indent=2, ensure_ascii=False)
    print(f"Scores saved to {scores_path}")

    # Generate summary
    summary = generate_summary(all_results, all_scores, initial_cards)
    summary_path = OUTPUT_DIR / "exp5_summary.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)
    print(f"Summary saved to {summary_path}")

    stats = llm.stats()
    print(f"\nCache stats: {json.dumps(stats, indent=2)}")


def generate_summary(
    all_results: dict,
    all_scores: list,
    initial_cards: list[dict],
) -> str:
    """Generate markdown summary."""
    dimensions = [
        "rules_text_correctness", "mana_cost_appropriateness",
        "power_level_for_rarity", "flavor_text_quality",
        "name_creativity", "type_line_correctness", "color_pie_compliance",
    ]

    lines = ["# Experiment 5: Context Strategy — Summary\n"]
    lines.append(f"**Model**: {MODEL}")
    lines.append(f"**Temperature**: {TEMPERATURE}")
    lines.append(f"**Few-shot count**: 0 (zero-shot, exp2 winner)")
    lines.append(f"**Initial cards**: {len(initial_cards)}")
    lines.append(f"**Test cards per strategy**: 14")
    lines.append(f"**Total scored**: {len(all_scores)}\n")

    total_cost = sum(
        b.get("cost_usd", 0)
        for r in all_results.values()
        for b in r["batches"]
    )
    lines.append(f"**Total API cost**: ${total_cost:.4f}\n")
    lines.append("\n---\n")

    # Quality comparison
    lines.append("## Quality Scores by Strategy\n")
    header = "| Dimension |"
    sep = "|-----------|"
    for s in CONTEXT_STRATEGIES:
        header += f" {s} |"
        sep += "------|"
    lines.append(header)
    lines.append(sep)

    strat_dim_avg = {}
    for strat in CONTEXT_STRATEGIES:
        strat_scores = [s for s in all_scores if s["strategy"] == strat]
        strat_dim_avg[strat] = {}
        for dim in dimensions:
            vals = [s["scores"][dim] for s in strat_scores if dim in s["scores"]]
            strat_dim_avg[strat][dim] = sum(vals) / len(vals) if vals else 0

    for dim in dimensions:
        dim_label = dim.replace("_", " ").title()
        row = f"| {dim_label} |"
        for strat in CONTEXT_STRATEGIES:
            row += f" {strat_dim_avg[strat][dim]:.2f} |"
        lines.append(row)

    row = "| **Overall Average** |"
    strat_overall = {}
    for strat in CONTEXT_STRATEGIES:
        vals = list(strat_dim_avg[strat].values())
        avg = sum(vals) / len(vals) if vals else 0
        strat_overall[strat] = avg
        row += f" **{avg:.2f}** |"
    lines.append(row)
    lines.append("")

    best_strat = max(strat_overall, key=strat_overall.get)
    lines.append(f"## Best Quality Strategy: **{best_strat}** (avg: {strat_overall[best_strat]:.2f})\n")

    # Duplicate/similarity analysis
    lines.append("## Duplicate & Similarity Analysis\n")
    lines.append("| Strategy | Name Dupes | Similar Effects | Total Issues |")
    lines.append("|----------|-----------|-----------------|-------------|")
    for strat in CONTEXT_STRATEGIES:
        r = all_results[strat]
        nd = len(r["name_duplicates"])
        se = len(r["similar_effects"])
        lines.append(f"| {strat} | {nd} | {se} | {nd + se} |")
    lines.append("")

    # Details
    for strat in CONTEXT_STRATEGIES:
        r = all_results[strat]
        if r["name_duplicates"] or r["similar_effects"]:
            lines.append(f"### {strat}")
            if r["name_duplicates"]:
                lines.append(f"- Name duplicates: {', '.join(r['name_duplicates'])}")
            for s in r["similar_effects"]:
                lines.append(f"- Similar: {s}")
            lines.append("")

    # Token cost comparison
    lines.append("## Token Usage\n")
    lines.append("| Strategy | Avg Input Tokens | Total Cost |")
    lines.append("|----------|-----------------|------------|")
    for strat in CONTEXT_STRATEGIES:
        r = all_results[strat]
        batches = [b for b in r["batches"] if "error" not in b]
        if batches:
            avg_in = sum(b["tokens"]["input"] for b in batches) / len(batches)
            total = sum(b["cost_usd"] for b in batches)
            lines.append(f"| {strat} | {avg_in:.0f} | ${total:.4f} |")
    lines.append("")

    # Recommendation
    lines.append("## Recommendation\n")

    # Find least-duplicating strategy that maintains quality
    best_dedup = min(
        CONTEXT_STRATEGIES,
        key=lambda s: (
            len(all_results[s]["name_duplicates"]) + len(all_results[s]["similar_effects"]),
            -strat_overall[s],
        ),
    )
    lines.append(f"- **Best quality**: {best_strat} (avg: {strat_overall[best_strat]:.2f})")
    lines.append(f"- **Fewest duplicates**: {best_dedup}")
    lines.append(
        f"- **Recommended for Phase 1C**: "
        f"Use **compressed** context (names + mana costs + summaries) for best balance "
        f"of duplicate avoidance vs token cost. Fall back to names_only if context window is tight."
    )
    lines.append(f"\n**Total API cost**: ${total_cost:.4f}")

    return "\n".join(lines)


if __name__ == "__main__":
    run_experiment()
