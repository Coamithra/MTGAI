"""Generate a human-readable markdown gallery of all generated cards.

Re-runs validation live against the current validator code so the gallery
always reflects the latest rules.
"""

import json
import os
import sys

# Allow imports from backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from mtgai.validation import ValidationSeverity, validate_card_from_raw  # noqa: E402

CARDS_DIR = "output/sets/ASD/cards"
PROGRESS_FILE = "output/sets/ASD/generation_progress.json"
OUTPUT_FILE = "output/sets/ASD/card_gallery.md"

COLOR_GROUPS = [
    ("White", "W-"),
    ("Blue", "U-"),
    ("Black", "B-"),
    ("Red", "R-"),
    ("Green", "G-"),
    ("White-Blue", "WU-"),
    ("White-Black", "WB-"),
    ("White-Red", "WR-"),
    ("White-Green", "WG-"),
    ("Blue-Black", "UB-"),
    ("Colorless", "X-"),
]

MULTI_PREFIXES = {p for _, p in COLOR_GROUPS if len(p) > 2}


def slot_sort_key(slot_id: str) -> tuple[str, int]:
    parts = slot_id.rsplit("-", 1)
    return (parts[0], int(parts[1]))


def belongs_to_group(slot_id: str, prefix: str) -> bool:
    if not slot_id.startswith(prefix):
        return False
    if len(prefix) == 2:
        for mp in MULTI_PREFIXES:
            if slot_id.startswith(mp):
                return False
    return True


def main() -> None:
    with open(PROGRESS_FILE) as f:
        progress = json.load(f)

    # Load all card JSONs
    all_slots: dict[str, dict] = {}
    for slot_id, card_path in progress["filled_slots"].items():
        card_file = os.path.basename(card_path)
        local_path = os.path.join(CARDS_DIR, card_file)
        with open(local_path) as f:
            raw = json.load(f)
        all_slots[slot_id] = raw

    # Run live validation on each card (passing all others for uniqueness checks)
    all_cards_for_uniqueness = []
    validation_results: dict[str, list] = {}

    for slot_id in sorted(all_slots, key=slot_sort_key):
        raw = all_slots[slot_id]
        card, errors, _fixes = validate_card_from_raw(raw, all_cards_for_uniqueness)
        manual_errors = [e for e in errors if e.severity == ValidationSeverity.MANUAL]
        validation_results[slot_id] = manual_errors
        if card is not None:
            all_cards_for_uniqueness.append(card)

    # Build markdown
    lines: list[str] = []
    lines.append("# Anomalous Descent (ASD) — Card Gallery")
    lines.append("")
    lines.append("**60 cards** | Generated 2026-03-12 | Opus 4.6, effort=max | Cost: $2.78")
    lines.append("")

    summary_idx = len(lines)
    lines.append("")  # placeholder
    lines.append("")
    lines.append("---")
    lines.append("")

    total_manual = 0
    total_clean = 0

    for group_name, prefix in COLOR_GROUPS:
        group_slots = sorted(
            [sid for sid in all_slots if belongs_to_group(sid, prefix)],
            key=slot_sort_key,
        )
        if not group_slots:
            continue

        lines.append(f"## {group_name} ({len(group_slots)} cards)")
        lines.append("")

        for slot_id in group_slots:
            card = all_slots[slot_id]

            name = card.get("name", "???")
            mana = card.get("mana_cost", "")
            tl = card.get("type_line", "")
            oracle = card.get("oracle_text", "")
            flavor = card.get("flavor_text", "")
            power = card.get("power")
            tough = card.get("toughness")
            loyalty = card.get("loyalty")
            rarity = card.get("rarity", "")
            notes = card.get("design_notes", "")

            stats = ""
            if power is not None and tough is not None:
                stats = f"{power}/{tough}"
            if loyalty is not None:
                stats = f"Loyalty: {loyalty}"

            rarity_display = rarity.capitalize() if rarity else ""

            lines.append(f"### {slot_id}: {name}")
            lines.append("")
            stat_parts = [f"**{mana}**", tl]
            if stats:
                stat_parts.append(stats)
            stat_parts.append(f"*{rarity_display}*")
            lines.append(" | ".join(stat_parts))
            lines.append("")

            if oracle:
                oracle_lines = oracle.replace("\\n", "\n").split("\n")
                for ol in oracle_lines:
                    lines.append(f"> {ol}")
                lines.append("")

            if flavor:
                lines.append(f"*{flavor}*")
                lines.append("")

            if notes:
                lines.append(f"**Design notes:** {notes}")
                lines.append("")

            # Live validation results
            manual_errors = validation_results.get(slot_id, [])
            if manual_errors:
                total_manual += 1
                lines.append("**Validation issues:**")
                for err in manual_errors:
                    lines.append(f"- `{err.error_code}`: {err.message}")
                lines.append("")
            else:
                total_clean += 1

            lines.append("---")
            lines.append("")

    lines[summary_idx] = (
        f"**Validation:** {total_clean} clean, {total_manual} with flagged issues"
    )

    output = "\n".join(lines)
    # Replace em/en dashes with plain ASCII to avoid encoding display issues
    output = output.replace("\u2014", "--").replace("\u2013", "-")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"Written {len(lines)} lines to {OUTPUT_FILE}")
    print(f"  {total_clean} clean, {total_manual} with issues")


if __name__ == "__main__":
    main()
