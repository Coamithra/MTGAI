"""Run the reprint selector pipeline for the ASD dev set.

Uses a single Haiku LLM call (~$0.002) to pick the best reprints from the
curated pool, matched against eligible skeleton slots.
Saves the ReprintSelection to output/sets/ASD/reprint_selection.json.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from mtgai.generation.reprint_selector import ReprintSelection, select_reprints

logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)-7s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def main() -> None:
    skeleton_path = Path("../output/sets/ASD/skeleton.json")
    output_path = Path("../output/sets/ASD/reprint_selection.json")

    logger.info("=" * 70)
    logger.info("REPRINT SELECTION PIPELINE — ASD dev set")
    logger.info("=" * 70)
    logger.info("Skeleton: %s", skeleton_path.resolve())
    logger.info("Output:   %s", output_path.resolve())
    logger.info("")

    result: ReprintSelection = select_reprints(
        skeleton_path=skeleton_path,
        count=2,
    )

    # Print results
    print()
    print("=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"Set code:              {result.set_code}")
    print(f"Set size:              {result.set_size}")
    print(f"Target reprint count:  {result.target_reprint_count}")
    print(f"Candidates considered: {result.all_candidates_considered}")
    print(f"Selections:            {len(result.selections)}")
    print(f"Timestamp:             {result.selection_timestamp}")
    print()

    if result.selections:
        print("-" * 70)
        print("REPRINT SELECTIONS")
        print("-" * 70)
        for i, pair in enumerate(result.selections, 1):
            slot = pair.slot
            cand = pair.candidate
            print(f"\n  [{i}] {cand.name}")
            print(
                f"      Slot:        {slot.slot_id} ({slot.color} {slot.rarity} {slot.card_type})"
            )
            print(f"      Role needed: {slot.role_needed}")
            print(f"      CMC target:  {slot.cmc_target}")
            print(f"      Mana cost:   {cand.mana_cost}")
            print(f"      Type line:   {cand.type_line}")
            print(f"      Oracle text: {cand.oracle_text}")
            if cand.power is not None:
                print(f"      P/T:         {cand.power}/{cand.toughness}")
            print(f"      Reason:      {pair.reason}")
    else:
        print("  (no selections)")

    # Save to JSON
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

    print()
    print("=" * 70)
    print(f"Saved to {output_path.resolve()}")
    print("=" * 70)


if __name__ == "__main__":
    main()
