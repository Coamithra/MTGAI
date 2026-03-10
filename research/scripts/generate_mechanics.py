"""Generate mechanic candidates for the Anomalous Descent (ASD) set.

Phase 1B: Mechanic generation infrastructure.
Calls the LLM to produce 6 candidate mechanics, validates them against
the color pie, and saves results + evergreen keyword assignments.

Run from project root:
    python research/scripts/generate_mechanics.py
"""

import json
import sys
from pathlib import Path

# Add backend to path so we can import mtgai
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from mtgai.generation.mechanic_generator import (
    assign_evergreen_keywords,
    generate_mechanic_candidates,
    validate_mechanic_color_pie,
)

THEME_PATH = Path("output/sets/ASD/theme.json")
CANDIDATES_PATH = Path("output/sets/ASD/mechanics/candidates.json")
EVERGREEN_PATH = Path("output/sets/ASD/mechanics/evergreen-keywords.json")


def print_separator(char: str = "=", width: int = 80) -> None:
    print(char * width)


def print_mechanic_summary(mechanic: dict, index: int, warnings: list[str]) -> None:
    """Print a formatted summary of a single mechanic candidate."""
    print_separator("-")
    print(f"  #{index + 1}: {mechanic['name']}")
    print(f"  Type:       {mechanic['keyword_type']}")
    print(f"  Colors:     {', '.join(mechanic['colors'])}")
    print(f"  Complexity: {mechanic['complexity']}")
    print(f"  Reminder:   ({mechanic['reminder_text']})")
    print(f"  Flavor:     {mechanic['flavor_connection'][:80]}...")
    print(f"  Rationale:  {mechanic['design_rationale'][:80]}...")
    print(f"  Examples:   {len(mechanic.get('example_cards', []))} cards")

    if warnings:
        print(f"  Validation: {len(warnings)} issue(s)")
        for w in warnings:
            print(f"    - {w}")
    else:
        print("  Validation: PASS")


def main() -> None:
    # 1. Load theme
    print_separator()
    print("PHASE 1B: Mechanic Generation for Anomalous Descent (ASD)")
    print_separator()

    if THEME_PATH.exists():
        theme = json.loads(THEME_PATH.read_text())
        print(f"Loaded theme: {theme['name']} ({theme['code']})")
        print(f"  Set size: {theme['set_size']} cards")
        print(f"  Mechanic slots: {theme['mechanic_count']}")
    else:
        print(f"WARNING: Theme file not found at {THEME_PATH}")
        theme = None
    print()

    # 2. Generate mechanic candidates
    mechanics = generate_mechanic_candidates(theme_path=THEME_PATH)

    # 3. Validate each candidate
    all_warnings: dict[int, list[str]] = {}
    for i, mech in enumerate(mechanics):
        all_warnings[i] = validate_mechanic_color_pie(mech)

    # 4. Print summary table
    print_separator()
    print("MECHANIC CANDIDATES SUMMARY")
    print_separator()

    for i, mech in enumerate(mechanics):
        print_mechanic_summary(mech, i, all_warnings[i])

    # Print comparison table
    print()
    print_separator()
    print("COMPARISON TABLE")
    print_separator()
    header = f"{'#':<3} {'Name':<25} {'Type':<17} {'Colors':<10} {'Cplx':<5} {'Issues':<6}"
    print(header)
    print("-" * len(header))
    for i, mech in enumerate(mechanics):
        colors = ",".join(mech["colors"])
        issues = len(all_warnings[i])
        issue_str = str(issues) if issues > 0 else "OK"
        print(
            f"{i + 1:<3} {mech['name']:<25} {mech['keyword_type']:<17} "
            f"{colors:<10} {mech['complexity']:<5} {issue_str:<6}"
        )

    # Print example cards for each mechanic
    print()
    print_separator()
    print("EXAMPLE CARDS")
    print_separator()
    for i, mech in enumerate(mechanics):
        print(f"\n--- {mech['name']} ---")
        for card in mech.get("example_cards", []):
            print(f"  {card['name']} {card['mana_cost']}")
            print(f"    {card['type_line']}")
            oracle = card["oracle_text"].replace("\n", "\n    ")
            print(f"    {oracle}")
            if card.get("power") and card.get("toughness"):
                print(f"    {card['power']}/{card['toughness']}")
            print(f"    [{card['rarity']}]")
            print()

    # 5. Save candidates
    CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATES_PATH.write_text(json.dumps(mechanics, indent=2))
    print(f"Saved {len(mechanics)} candidates to {CANDIDATES_PATH}")

    # 6. Save evergreen keywords
    evergreen = assign_evergreen_keywords()
    EVERGREEN_PATH.write_text(json.dumps(evergreen, indent=2))
    print(f"Saved evergreen keywords to {EVERGREEN_PATH}")

    # Final summary
    print()
    print_separator()
    total_issues = sum(len(w) for w in all_warnings.values())
    clean = sum(1 for w in all_warnings.values() if not w)
    print(
        f"Done. {len(mechanics)} candidates generated, "
        f"{clean} clean, {total_issues} total validation notes."
    )
    print("Next step: review candidates and select 3 for the set.")
    print_separator()


if __name__ == "__main__":
    main()
