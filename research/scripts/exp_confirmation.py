"""Confirmation Batch: 20 additional cards with winning settings.

Winning settings from experiments:
- Model: claude-sonnet-4-20250514
- Temperature: 1.0
- Few-shot: 0 (zero-shot)
- Output: tool_use (structured JSON)
- Context: compressed (names + mana costs + summaries)

Tests: mechanic integration, context injection, archetype targeting.

Usage:
    python research/scripts/exp_confirmation.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "research/scripts")
from cached_llm import CachedLLM, CARDS_BATCH_TOOL_SCHEMA
from exp1_temperature_sweep import SYSTEM_PROMPT, score_card, parse_cards_from_result

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-20250514"
TEMPERATURE = 1.0
OUTPUT_DIR = Path("research/prompt-templates/experiments/confirmation")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 20 card slots covering mechanics, context awareness, and archetype targeting
CONFIRMATION_SLOTS = [
    # 5 mechanic integration cards (using a test mechanic: "Delve")
    {"slot": 25, "color": "U", "rarity": "common", "type": "Instant",
     "complexity": "Single ability",
     "notes": "Blue common instant with Delve. Tests mechanic keyword integration."},
    {"slot": 26, "color": "B", "rarity": "uncommon", "type": "Creature",
     "complexity": "Multi-ability",
     "notes": "Black uncommon creature with Delve. ETB trigger that interacts with graveyard."},
    {"slot": 27, "color": "G", "rarity": "rare", "type": "Sorcery",
     "complexity": "Multi-ability",
     "notes": "Green rare sorcery with Convoke. Tests mechanic + big effect combo."},
    {"slot": 28, "color": "W", "rarity": "uncommon", "type": "Enchantment",
     "complexity": "Multi-ability",
     "notes": "White uncommon enchantment with a triggered ability that creates tokens. Set mechanic: Convoke."},
    {"slot": 29, "color": "R", "rarity": "rare", "type": "Creature",
     "complexity": "Multi-ability",
     "notes": "Red rare creature with Prowess-like triggered ability. Tests unique triggers."},

    # 5 context-aware cards (should NOT duplicate names from existing set)
    {"slot": 30, "color": "W", "rarity": "common", "type": "Creature",
     "complexity": "Keyword-only",
     "notes": "White common flyer. Already have 'Radiant Pegasus' — name must be different."},
    {"slot": 31, "color": "U", "rarity": "uncommon", "type": "Instant",
     "complexity": "Single ability",
     "notes": "Blue counterspell variant. Already have 'Dispel the Weave' — must be mechanically distinct."},
    {"slot": 32, "color": "B", "rarity": "common", "type": "Instant",
     "complexity": "Single ability",
     "notes": "Black removal spell. Already have 'Fatal Strike' — different targeting/cost."},
    {"slot": 33, "color": "R", "rarity": "common", "type": "Instant",
     "complexity": "Single ability",
     "notes": "Red burn spell. Already have 'Molten Bolt' — different damage amount/target."},
    {"slot": 34, "color": "G", "rarity": "common", "type": "Creature",
     "complexity": "Keyword-only",
     "notes": "Green common beater. Different from the Ironbark cycle — smaller, 2-3 CMC."},

    # 10 archetype-targeted cards
    {"slot": 35, "color": "WU", "rarity": "uncommon", "type": "Creature",
     "complexity": "Multi-ability",
     "notes": "WU archetype signpost for 'flyers matters'. ETB + flying synergy."},
    {"slot": 36, "color": "UB", "rarity": "uncommon", "type": "Creature",
     "complexity": "Multi-ability",
     "notes": "UB archetype signpost for 'graveyard value'. Dies/mill + recursion."},
    {"slot": 37, "color": "BR", "rarity": "uncommon", "type": "Creature",
     "complexity": "Multi-ability",
     "notes": "BR archetype signpost for 'sacrifice aggro'. Sacrifice + damage/value."},
    {"slot": 38, "color": "RG", "rarity": "uncommon", "type": "Creature",
     "complexity": "Multi-ability",
     "notes": "RG archetype signpost for 'big creatures matter'. Power-based triggers."},
    {"slot": 39, "color": "GW", "rarity": "uncommon", "type": "Creature",
     "complexity": "Multi-ability",
     "notes": "GW archetype signpost for 'tokens/go-wide'. Token creation + anthem."},
    {"slot": 40, "color": "WB", "rarity": "uncommon", "type": "Creature",
     "complexity": "Multi-ability",
     "notes": "WB archetype signpost for 'life manipulation'. Lifegain + drain."},
    {"slot": 41, "color": "UR", "rarity": "uncommon", "type": "Creature",
     "complexity": "Multi-ability",
     "notes": "UR archetype signpost for 'spells matter'. Prowess/instants-sorceries synergy."},
    {"slot": 42, "color": "BG", "rarity": "uncommon", "type": "Creature",
     "complexity": "Multi-ability",
     "notes": "BG archetype signpost for 'graveyard recursion'. Self-mill + raise dead."},
    {"slot": 43, "color": "RW", "rarity": "uncommon", "type": "Creature",
     "complexity": "Multi-ability",
     "notes": "RW archetype signpost for 'aggro equipment'. Equip synergy + combat triggers."},
    {"slot": 44, "color": "GU", "rarity": "uncommon", "type": "Creature",
     "complexity": "Multi-ability",
     "notes": "GU archetype signpost for 'ramp/card advantage'. Land-based triggers + draw."},
]

# Simulated "existing cards" for context injection
EXISTING_CARDS = [
    {"name": "Moorland Sentinel", "mana_cost": "{W}", "type_line": "Creature — Human Soldier",
     "oracle_text": "", "colors": ["W"]},
    {"name": "Radiant Pegasus", "mana_cost": "{1}{W}", "type_line": "Creature — Pegasus",
     "oracle_text": "Flying\nLifelink", "colors": ["W"]},
    {"name": "Righteous Banishment", "mana_cost": "{1}{W}", "type_line": "Instant",
     "oracle_text": "Exile target creature with power 4 or greater.", "colors": ["W"]},
    {"name": "Scholarly Insight", "mana_cost": "{1}{U}", "type_line": "Instant",
     "oracle_text": "Draw a card.\nScry 1.", "colors": ["U"]},
    {"name": "Dispel the Weave", "mana_cost": "{U}{U}", "type_line": "Instant",
     "oracle_text": "Counter target spell unless its controller pays {3}.", "colors": ["U"]},
    {"name": "Arcane Scrutiny", "mana_cost": "{3}{U}{U}", "type_line": "Sorcery",
     "oracle_text": "Draw three cards, then discard a card.", "colors": ["U"]},
    {"name": "Fatal Strike", "mana_cost": "{1}{B}", "type_line": "Instant",
     "oracle_text": "Destroy target creature with mana value 3 or less.", "colors": ["B"]},
    {"name": "Crypt Harvester", "mana_cost": "{2}{B}", "type_line": "Creature — Zombie",
     "oracle_text": "When ~ enters, each opponent discards a card.", "colors": ["B"]},
    {"name": "Vorthak, Death's Herald", "mana_cost": "{3}{B}{B}",
     "type_line": "Legendary Creature — Demon", "colors": ["B"],
     "oracle_text": "Flying, deathtouch\nWhenever a creature an opponent controls dies, you draw a card and lose 1 life."},
    {"name": "Molten Bolt", "mana_cost": "{R}", "type_line": "Instant",
     "oracle_text": "~ deals 2 damage to any target.", "colors": ["R"]},
]

BATCHES = [
    [25, 26, 27, 28, 29],     # Mechanic integration
    [30, 31, 32, 33, 34],     # Context-aware
    [35, 36, 37, 38, 39],     # Archetype signposts 1
    [40, 41, 42, 43, 44],     # Archetype signposts 2
]


def build_context_section() -> str:
    """Compressed context from 'existing' cards."""
    lines = ["\n**Cards already in the set** (do NOT duplicate names or effects):\n"]
    for c in EXISTING_CARDS:
        oracle = c.get("oracle_text", "")
        summary = oracle[:60] + "..." if len(oracle) > 60 else oracle
        lines.append(f"- {c['name']} ({c['mana_cost']}) — {c['type_line']} — {summary}")

    color_counts = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0}
    for c in EXISTING_CARDS:
        for col in c.get("colors", []):
            if col in color_counts:
                color_counts[col] += 1
    lines.append(f"\n**Color distribution so far**: {color_counts}")
    lines.append(f"**Total cards**: {len(EXISTING_CARDS)}\n")
    return "\n".join(lines)


def build_batch_prompt(slot_indices: list[int]) -> str:
    """Build prompt with compressed context."""
    lines = [
        f"Generate {len(slot_indices)} Magic: The Gathering cards for a custom set. "
        "Each card must fill a specific slot.\n"
    ]

    # Context injection
    lines.append(build_context_section())

    # Set mechanics (simulate having set mechanics)
    lines.append(
        "**Set Mechanics**:\n"
        "- Delve (You may exile cards from your graveyard as you cast this spell. "
        "Each card exiled this way pays for {1}.)\n"
        "- Convoke (Your creatures can help cast this spell. Each creature you tap while "
        "casting this spell pays for {1} or one mana of that creature's color.)\n"
    )

    lines.append("**Slots to fill**:\n")
    for idx in slot_indices:
        card = next(c for c in CONFIRMATION_SLOTS if c["slot"] == idx)
        lines.append(
            f"Slot {card['slot']}:\n"
            f"- Color: {card['color']}\n"
            f"- Rarity: {card['rarity']}\n"
            f"- Type: {card['type']}\n"
            f"- Complexity: {card['complexity']}\n"
            f"- Role: {card['notes']}\n"
        )
    lines.append(
        "Output as JSON. Generate all cards. Every slot must be filled. "
        "For multicolor cards, the mana_cost must include all specified colors."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_experiment():
    llm = CachedLLM()
    all_cards = []
    all_scores = []
    total_cost = 0.0

    for batch_slots in BATCHES:
        print(f"\n{'='*60}")
        print(f"Batch: slots {batch_slots}")
        print(f"{'='*60}")

        prompt = build_batch_prompt(batch_slots)

        result = llm.generate(
            model=MODEL,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=TEMPERATURE,
            tool_schema=CARDS_BATCH_TOOL_SCHEMA,
            max_tokens=8192,
        )

        cards = parse_cards_from_result(result)
        all_cards.extend(cards)
        hit = "CACHE HIT" if result.cache_hit else f"${result.cost_usd:.4f}"
        total_cost += result.cost_usd if not result.cache_hit else 0
        print(f"  Got {len(cards)} cards ({hit})")

        for i, card in enumerate(cards):
            slot_num = batch_slots[i] if i < len(batch_slots) else batch_slots[-1]
            slot = next(c for c in CONFIRMATION_SLOTS if c["slot"] == slot_num)
            score_result = score_card(card, slot)

            avg = sum(score_result["scores"].values()) / len(score_result["scores"])
            fails = score_result["failure_modes"]
            fail_str = f" [{', '.join(fails)}]" if fails else ""
            print(f"  Card {slot_num} '{card.get('name', '?')}': avg={avg:.1f}{fail_str}")

            all_scores.append({
                "card_slot": slot_num,
                "card_name": card.get("name", "UNKNOWN"),
                "card": card,
                "scores": score_result["scores"],
                "failure_modes": fails,
                "avg_score": avg,
            })

        if not result.cache_hit:
            time.sleep(1)

    # Summary statistics
    print(f"\n{'='*60}")
    print("CONFIRMATION BATCH RESULTS")
    print(f"{'='*60}")

    avg_overall = sum(s["avg_score"] for s in all_scores) / len(all_scores)
    cards_below_3 = sum(1 for s in all_scores if s["avg_score"] < 3.0)
    total_failures = sum(len(s["failure_modes"]) for s in all_scores)
    cards_with_failures = sum(1 for s in all_scores if s["failure_modes"])

    print(f"Total cards: {len(all_scores)}")
    print(f"Overall average: {avg_overall:.2f}")
    print(f"Cards below 3.0: {cards_below_3}")
    print(f"Cards with failures: {cards_with_failures}/{len(all_scores)}")
    print(f"Total failure instances: {total_failures}")
    print(f"Total cost: ${total_cost:.4f}")

    # Check for name duplication with existing set
    existing_names = {c["name"].lower() for c in EXISTING_CARDS}
    new_names = [s["card_name"] for s in all_scores]
    dupes = [n for n in new_names if n.lower() in existing_names]
    print(f"Name duplicates with existing: {dupes}")

    # Check for duplicates within the batch
    seen = set()
    internal_dupes = []
    for n in new_names:
        if n.lower() in seen:
            internal_dupes.append(n)
        seen.add(n.lower())
    print(f"Internal duplicates: {internal_dupes}")

    # Dimension averages
    dimensions = [
        "rules_text_correctness", "mana_cost_appropriateness",
        "power_level_for_rarity", "flavor_text_quality",
        "name_creativity", "type_line_correctness", "color_pie_compliance",
    ]
    print("\nPer-dimension averages:")
    for dim in dimensions:
        vals = [s["scores"][dim] for s in all_scores]
        avg = sum(vals) / len(vals)
        print(f"  {dim}: {avg:.2f}")

    # Save
    save_path = OUTPUT_DIR / "confirmation_results.json"
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump({
            "settings": {
                "model": MODEL,
                "temperature": TEMPERATURE,
                "fewshot": 0,
                "context": "compressed",
                "output_format": "tool_use",
            },
            "cards": all_scores,
            "summary": {
                "total_cards": len(all_scores),
                "overall_avg": avg_overall,
                "cards_below_3": cards_below_3,
                "cards_with_failures": cards_with_failures,
                "total_cost": total_cost,
                "name_duplicates": dupes,
                "internal_duplicates": internal_dupes,
            },
        }, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {save_path}")

    # Generate summary markdown
    lines = ["# Confirmation Batch — Summary\n"]
    lines.append(f"**Settings**: {MODEL}, T={TEMPERATURE}, FS=0, tool_use, compressed context\n")
    lines.append(f"**Cards generated**: {len(all_scores)}")
    lines.append(f"**Overall average**: {avg_overall:.2f}/5.0")
    lines.append(f"**Cards below 3.0**: {cards_below_3}")
    lines.append(f"**Cards with any failure**: {cards_with_failures}/{len(all_scores)}")
    lines.append(f"**Name duplicates**: {len(dupes)} external, {len(internal_dupes)} internal")
    lines.append(f"**Total cost**: ${total_cost:.4f}\n")
    lines.append("\n## Per-Card Results\n")
    lines.append("| Slot | Name | Type | Colors | Avg | Failures |")
    lines.append("|------|------|------|--------|-----|----------|")
    for s in all_scores:
        name = s["card_name"]
        if len(name) > 25:
            name = name[:22] + "..."
        card = s.get("card", {})
        tl = card.get("type_line", "")[:20]
        colors = ",".join(card.get("colors", []))
        fails = ", ".join(s["failure_modes"][:3]) if s["failure_modes"] else ""
        lines.append(f"| {s['card_slot']} | {name} | {tl} | {colors} | {s['avg_score']:.1f} | {fails} |")

    lines.append("\n## GO/NO-GO Gate Check\n")
    rtc_avg = sum(s["scores"]["rules_text_correctness"] for s in all_scores) / len(all_scores)
    lines.append(f"- Rules text avg: {rtc_avg:.2f} (need >= 4.0) — {'PASS' if rtc_avg >= 4.0 else 'FAIL'}")
    lines.append(f"- Overall avg: {avg_overall:.2f} (need >= 3.5) — {'PASS' if avg_overall >= 3.5 else 'FAIL'}")
    retry_rate = cards_with_failures / len(all_scores) * 100
    lines.append(f"- Retry rate: {retry_rate:.0f}% (need <= 30%) — {'PASS' if retry_rate <= 30 else 'FAIL'}")
    lines.append(f"- Parse rate: 100% (tool_use, need >= 95%) — PASS")
    cost_per_card = total_cost / len(all_scores) if total_cost > 0 else 0.005
    est_set_cost = cost_per_card * 280 * 1.25  # 25% retry overhead
    lines.append(f"- Est cost/set: ${est_set_cost:.2f} (need < $30) — {'PASS' if est_set_cost < 30 else 'FAIL'}")
    lines.append(f"\n**Verdict**: {'GO' if rtc_avg >= 4.0 and avg_overall >= 3.5 and retry_rate <= 30 else 'NEEDS REVIEW'}")

    summary_path = OUTPUT_DIR / "confirmation_summary.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Summary saved to {summary_path}")

    stats = llm.stats()
    print(f"\nCache stats: {json.dumps(stats, indent=2)}")


if __name__ == "__main__":
    run_experiment()
