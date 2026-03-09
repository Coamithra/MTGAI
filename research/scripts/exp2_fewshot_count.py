"""Experiment 2: Few-Shot Count

Test how many few-shot examples are needed for reliable card generation.
Tests: 0, 1, 3, 5 examples per batch, all at temperature 1.0 (winner from exp1).

Usage:
    python research/scripts/exp2_fewshot_count.py
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
    BATCHES,
    score_card,
    parse_cards_from_result,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-20250514"
TEMPERATURE = 1.0  # Winner from exp1
FEWSHOT_COUNTS = [0, 1, 3, 5]
OUTPUT_DIR = Path("research/prompt-templates/experiments/exp2_fewshot")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
EXAMPLES_DIR = Path("research/few-shot-examples")

# ---------------------------------------------------------------------------
# Load few-shot examples
# ---------------------------------------------------------------------------

EXAMPLE_INDEX = json.loads((EXAMPLES_DIR / "index.json").read_text(encoding="utf-8"))
EXAMPLE_DATA = {}
for entry in EXAMPLE_INDEX:
    data = json.loads((EXAMPLES_DIR / entry["filename"]).read_text(encoding="utf-8"))
    EXAMPLE_DATA[entry["filename"]] = {
        "meta": entry,
        "card": data,
    }


def select_examples(slot: dict, count: int) -> list[dict]:
    """Select `count` few-shot examples relevant to the given card slot."""
    if count == 0:
        return []

    target_rarity = slot["rarity"]
    target_type = slot["type"].split(" — ")[0].split(" ")[0]  # "Creature", "Instant", etc.
    target_color = slot["color"]
    target_complexity = slot["complexity"]

    scored = []
    for fname, info in EXAMPLE_DATA.items():
        meta = info["meta"]
        card = info["card"]
        score = 0

        # Prioritize matching card type
        card_type_first = meta["card_type"].split(" — ")[0].split(" ")[0]
        if card_type_first == target_type:
            score += 4

        # Match rarity
        if meta["rarity"] == target_rarity:
            score += 2

        # Match color
        if target_color != "-" and target_color != "C":
            for c in target_color:
                if c in meta.get("colors", []):
                    score += 1

        # Match complexity (rough heuristic: check if example oracle_text length matches)
        oracle_len = len(card.get("oracle_text", ""))
        if target_complexity == "Vanilla" and oracle_len < 20:
            score += 1
        elif target_complexity == "Keyword-only" and 5 < oracle_len < 50:
            score += 1
        elif target_complexity == "Single ability" and 20 < oracle_len < 100:
            score += 1
        elif target_complexity == "Multi-ability" and oracle_len > 80:
            score += 1
        elif target_complexity == "Modal" and "Choose" in card.get("oracle_text", ""):
            score += 2
        elif "Saga" in target_type and "Saga" in meta["card_type"]:
            score += 3
        elif target_type == "Planeswalker" and "Planeswalker" in meta["card_type"]:
            score += 3

        scored.append((score, fname, info))

    # Sort by score descending, take top `count`
    scored.sort(key=lambda x: -x[0])
    return [item[2]["card"] for item in scored[:count]]


def format_examples(examples: list[dict]) -> str:
    """Format examples for inclusion in the user prompt."""
    if not examples:
        return ""

    lines = ["\n**Reference examples (real MTG cards):**\n"]
    for i, card in enumerate(examples, 1):
        # Build a simplified card dict for the prompt (remove design_notes, card_faces)
        display = {
            "name": card["name"],
            "mana_cost": card.get("mana_cost", ""),
            "cmc": card.get("cmc", 0),
            "colors": card.get("colors", []),
            "color_identity": card.get("color_identity", []),
            "type_line": card.get("type_line", ""),
            "oracle_text": card.get("oracle_text", ""),
            "flavor_text": card.get("flavor_text"),
            "power": card.get("power"),
            "toughness": card.get("toughness"),
            "loyalty": card.get("loyalty"),
            "rarity": card.get("rarity", ""),
        }
        lines.append(f"Example {i}:")
        lines.append(json.dumps(display, indent=2))
        lines.append("")

    return "\n".join(lines)


def build_batch_prompt(slot_indices: list[int], fewshot_count: int) -> str:
    """Build the user prompt for a batch of card slots with N few-shot examples."""
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

    # Select examples based on the first slot in the batch (representative)
    if fewshot_count > 0:
        # Collect unique examples across all slots in batch
        all_examples = []
        seen_names = set()
        for idx in slot_indices:
            slot = CARD_SLOTS[idx - 1]
            examples = select_examples(slot, fewshot_count)
            for ex in examples:
                if ex["name"] not in seen_names:
                    all_examples.append(ex)
                    seen_names.add(ex["name"])
                    if len(all_examples) >= fewshot_count:
                        break
            if len(all_examples) >= fewshot_count:
                break
        lines.append(format_examples(all_examples[:fewshot_count]))

    lines.append(
        "Output as JSON. Generate all cards. Every slot must be filled."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main experiment runner
# ---------------------------------------------------------------------------

def run_experiment():
    llm = CachedLLM()
    all_raw_results = []
    all_scores = []

    for fewshot in FEWSHOT_COUNTS:
        print(f"\n{'='*60}")
        print(f"Few-shot count: {fewshot}")
        print(f"{'='*60}")

        fs_result = {
            "fewshot_count": fewshot,
            "temperature": TEMPERATURE,
            "batches": [],
        }

        for batch_idx, batch_slots in enumerate(BATCHES, 1):
            print(f"  FS={fewshot}, Batch {batch_idx}/{len(BATCHES)} (slots {batch_slots})...")

            user_prompt = build_batch_prompt(batch_slots, fewshot)

            try:
                result = llm.generate(
                    model=MODEL,
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    temperature=TEMPERATURE,
                    tool_schema=CARDS_BATCH_TOOL_SCHEMA,
                    max_tokens=8192,
                )

                cards = parse_cards_from_result(result)
                print(
                    f"    -> Got {len(cards)} cards "
                    f"({'CACHE HIT' if result.cache_hit else f'${result.cost_usd:.4f}'})"
                )

                batch_data = {
                    "batch_num": batch_idx,
                    "slots": batch_slots,
                    "cards": cards,
                    "tokens": {
                        "input": result.input_tokens,
                        "output": result.output_tokens,
                    },
                    "cost_usd": result.cost_usd,
                    "cache_hit": result.cache_hit,
                    "latency_ms": result.latency_ms,
                    "prompt_length": len(user_prompt),
                }
                fs_result["batches"].append(batch_data)

                # Score each card
                for i, card in enumerate(cards):
                    slot_num = batch_slots[i] if i < len(batch_slots) else batch_slots[-1]
                    slot = CARD_SLOTS[slot_num - 1]
                    score_result = score_card(card, slot)

                    card_score = {
                        "card_slot": slot_num,
                        "fewshot_count": fewshot,
                        "card_name": card.get("name", "UNKNOWN"),
                        "scores": score_result["scores"],
                        "failure_modes": score_result["failure_modes"],
                        "notes": score_result["notes"],
                    }
                    all_scores.append(card_score)

                    avg = sum(score_result["scores"].values()) / len(score_result["scores"])
                    fails = score_result["failure_modes"]
                    fail_str = f" [{', '.join(fails)}]" if fails else ""
                    print(f"    Card {slot_num} '{card.get('name', '?')}': avg={avg:.1f}{fail_str}")

                if not result.cache_hit:
                    time.sleep(1)

            except Exception as e:
                print(f"    ERROR in batch {batch_idx}: {e}")
                import traceback
                traceback.print_exc()
                fs_result["batches"].append({
                    "batch_num": batch_idx,
                    "slots": batch_slots,
                    "cards": [],
                    "tokens": {"input": 0, "output": 0},
                    "cost_usd": 0,
                    "error": str(e),
                })

        all_raw_results.append(fs_result)

    # Save raw results
    raw_path = OUTPUT_DIR / "exp2_raw_results.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(all_raw_results, f, indent=2, ensure_ascii=False)
    print(f"\nRaw results saved to {raw_path}")

    # Save scores
    scores_path = OUTPUT_DIR / "exp2_scores.json"
    with open(scores_path, "w", encoding="utf-8") as f:
        json.dump(all_scores, f, indent=2, ensure_ascii=False)
    print(f"Scores saved to {scores_path}")

    # Generate summary
    summary = generate_summary(all_raw_results, all_scores)
    summary_path = OUTPUT_DIR / "exp2_summary.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)
    print(f"Summary saved to {summary_path}")

    stats = llm.stats()
    print(f"\nCache stats: {json.dumps(stats, indent=2)}")


def generate_summary(raw_results: list, all_scores: list) -> str:
    """Generate a markdown summary of the few-shot experiment."""
    dimensions = [
        "rules_text_correctness",
        "mana_cost_appropriateness",
        "power_level_for_rarity",
        "flavor_text_quality",
        "name_creativity",
        "type_line_correctness",
        "color_pie_compliance",
    ]

    lines = ["# Experiment 2: Few-Shot Count — Summary\n"]
    lines.append(f"**Model**: {MODEL}\n")
    lines.append(f"**Temperature**: {TEMPERATURE}\n")
    lines.append(f"**Few-shot counts tested**: {FEWSHOT_COUNTS}\n")
    lines.append(f"**Cards per setting**: 24\n")
    lines.append(f"**Total cards scored**: {len(all_scores)}\n")

    # Cost summary
    total_cost = sum(
        b.get("cost_usd", 0) for r in raw_results for b in r["batches"]
    )
    lines.append(f"**Total API cost**: ${total_cost:.4f}\n")

    lines.append("\n---\n")

    # Average scores by few-shot count
    lines.append("## Average Scores by Few-Shot Count\n")
    header = "| Dimension |"
    sep = "|-----------|"
    for fs in FEWSHOT_COUNTS:
        header += f" FS={fs} |"
        sep += "------|"
    lines.append(header)
    lines.append(sep)

    fs_dim_averages = {}
    for fs in FEWSHOT_COUNTS:
        fs_scores = [s for s in all_scores if s["fewshot_count"] == fs]
        fs_dim_averages[fs] = {}
        for dim in dimensions:
            vals = [s["scores"][dim] for s in fs_scores if dim in s["scores"]]
            avg = sum(vals) / len(vals) if vals else 0
            fs_dim_averages[fs][dim] = avg

    for dim in dimensions:
        dim_label = dim.replace("_", " ").title()
        row = f"| {dim_label} |"
        for fs in FEWSHOT_COUNTS:
            row += f" {fs_dim_averages[fs][dim]:.2f} |"
        lines.append(row)

    # Overall average row
    row = "| **Overall Average** |"
    fs_overall = {}
    for fs in FEWSHOT_COUNTS:
        vals = list(fs_dim_averages[fs].values())
        avg = sum(vals) / len(vals) if vals else 0
        fs_overall[fs] = avg
        row += f" **{avg:.2f}** |"
    lines.append(row)
    lines.append("")

    best_fs = max(fs_overall, key=fs_overall.get)
    lines.append(f"\n## Best Overall Few-Shot Count: **{best_fs}** (avg: {fs_overall[best_fs]:.2f})\n")

    # Token cost comparison
    lines.append("## Token Usage by Few-Shot Count\n")
    lines.append("| Few-Shot | Avg Input Tokens | Avg Output Tokens | Avg Cost/Batch |")
    lines.append("|----------|-----------------|-------------------|----------------|")
    for fs in FEWSHOT_COUNTS:
        fs_data = next((r for r in raw_results if r["fewshot_count"] == fs), None)
        if fs_data:
            batches = [b for b in fs_data["batches"] if "error" not in b]
            if batches:
                avg_in = sum(b["tokens"]["input"] for b in batches) / len(batches)
                avg_out = sum(b["tokens"]["output"] for b in batches) / len(batches)
                avg_cost = sum(b["cost_usd"] for b in batches) / len(batches)
                lines.append(f"| {fs} | {avg_in:.0f} | {avg_out:.0f} | ${avg_cost:.4f} |")
    lines.append("")

    # Failure modes comparison
    lines.append("## Failure Mode Counts by Few-Shot Count\n")
    for fs in FEWSHOT_COUNTS:
        fs_scores = [s for s in all_scores if s["fewshot_count"] == fs]
        all_failures = {}
        for s in fs_scores:
            for fm in s.get("failure_modes", []):
                all_failures[fm] = all_failures.get(fm, 0) + 1
        if all_failures:
            sorted_failures = sorted(all_failures.items(), key=lambda x: -x[1])
            lines.append(f"### FS={fs}")
            for fm, count in sorted_failures:
                lines.append(f"- **{fm}**: {count}")
            lines.append("")

    # Per-card details
    lines.append("## Per-Card Scores\n")
    lines.append("| Slot | FS | Name | RTC | MCA | PLR | FTQ | NC | TLC | CPC | Avg | Failures |")
    lines.append("|------|-----|------|-----|-----|-----|-----|-----|-----|-----|-----|----------|")

    for fs in FEWSHOT_COUNTS:
        fs_scores_sorted = sorted(
            [s for s in all_scores if s["fewshot_count"] == fs],
            key=lambda x: x["card_slot"],
        )
        for s in fs_scores_sorted:
            sc = s["scores"]
            avg = sum(sc.values()) / len(sc)
            fails = ", ".join(s.get("failure_modes", [])[:3])
            name = s.get("card_name", "?")
            if len(name) > 25:
                name = name[:22] + "..."
            lines.append(
                f"| {s['card_slot']:2d} | {fs} | {name} | "
                f"{sc.get('rules_text_correctness', '-')} | "
                f"{sc.get('mana_cost_appropriateness', '-')} | "
                f"{sc.get('power_level_for_rarity', '-')} | "
                f"{sc.get('flavor_text_quality', '-')} | "
                f"{sc.get('name_creativity', '-')} | "
                f"{sc.get('type_line_correctness', '-')} | "
                f"{sc.get('color_pie_compliance', '-')} | "
                f"{avg:.1f} | {fails} |"
            )

    lines.append("")

    # Recommendation
    lines.append("## Recommendation\n")

    # Best for correctness vs creativity
    correctness_dims = ["rules_text_correctness", "mana_cost_appropriateness",
                        "type_line_correctness", "color_pie_compliance"]
    creativity_dims = ["flavor_text_quality", "name_creativity"]

    best_correct_fs = max(
        FEWSHOT_COUNTS,
        key=lambda fs: sum(fs_dim_averages[fs][d] for d in correctness_dims) / len(correctness_dims),
    )
    best_creative_fs = max(
        FEWSHOT_COUNTS,
        key=lambda fs: sum(fs_dim_averages[fs][d] for d in creativity_dims) / len(creativity_dims),
    )

    lines.append(f"- **Best for correctness**: FS={best_correct_fs}")
    lines.append(f"- **Best for creativity**: FS={best_creative_fs}")
    lines.append(f"- **Best overall**: FS={best_fs} (avg: {fs_overall[best_fs]:.2f})")
    lines.append("")
    lines.append(f"**Recommended few-shot count for Phase 1C**: **{best_fs}**")
    lines.append(f"\n**Total API cost for this experiment**: ${total_cost:.4f}")

    return "\n".join(lines)


if __name__ == "__main__":
    run_experiment()
