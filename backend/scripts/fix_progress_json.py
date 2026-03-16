"""Fix stale progress.json by scanning actual art files on disk.

Adds cards with all 3 versions (v1, v2, v3) to the "completed" dict.
Leaves partial cards out so image_generator.py will regenerate them.

Usage (from backend/):
    python scripts/fix_progress_json.py
"""

import json
import re
from collections import defaultdict
from pathlib import Path

ART_DIR = Path("C:/Programming/MTGAI/output/sets/ASD/art")
PROGRESS_PATH = Path("C:/Programming/MTGAI/output/sets/ASD/art-generation-logs/progress.json")
VERSIONS_NEEDED = 3

# Pattern: collector_number_slug_vN.png
# Collector numbers like B-C-01, U-M-01, L-01, etc.
VERSION_RE = re.compile(r"^(.+)_v(\d+)\.png$")
# Collector number is the prefix before the card name slug.
# Card slugs are lowercase words joined by underscores.
# Collector numbers contain uppercase letters and dashes: e.g., B-C-01, L-01
CN_RE = re.compile(r"^([A-Z]+-?[A-Z]*-?\d+)_(.+)$")


def main():
    # Scan all png files
    files = sorted(ART_DIR.glob("*_v*.png"))
    print(f"Found {len(files)} art files in {ART_DIR}")

    # Group by collector number
    card_versions: dict[str, dict[int, Path]] = defaultdict(dict)

    for f in files:
        m = VERSION_RE.match(f.name)
        if not m:
            print(f"  WARNING: Could not parse version from {f.name}")
            continue

        base = m.group(1)  # e.g., "B-C-01_subsurface_scavenger"
        version = int(m.group(2))

        cn_match = CN_RE.match(base)
        if not cn_match:
            print(f"  WARNING: Could not parse collector number from {base}")
            continue

        collector_number = cn_match.group(1)
        card_versions[collector_number][version] = f

    print(f"Found {len(card_versions)} unique cards")

    # Separate complete vs partial
    complete = {}
    partial = {}
    for cn, versions in sorted(card_versions.items()):
        version_nums = sorted(versions.keys())
        if version_nums == [1, 2, 3]:
            complete[cn] = versions
        else:
            partial[cn] = versions

    print(f"  Complete (all 3 versions): {len(complete)}")
    print(f"  Partial (fewer than 3):    {len(partial)}")

    for cn, versions in sorted(partial.items()):
        version_nums = sorted(versions.keys())
        print(f"    {cn}: has versions {version_nums}")

    # Load existing progress.json
    if PROGRESS_PATH.exists():
        progress = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
        print(f"\nExisting progress.json has {len(progress['completed'])} completed entries")
    else:
        progress = {"completed": {}, "failed": {}, "skipped": []}
        print("\nNo existing progress.json found, creating new one")

    # Build new completed dict from complete cards only
    new_completed = {}
    for cn, versions in sorted(complete.items()):
        v3_path = versions[3]
        new_completed[cn] = {
            "version": 3,
            "path": str(v3_path),
            "elapsed": 0,
        }

    # Update progress: replace completed with our scan results
    progress["completed"] = new_completed

    # Remove completed cards from failed dict if present
    for cn in new_completed:
        progress["failed"].pop(cn, None)

    # Write updated progress.json
    PROGRESS_PATH.write_text(json.dumps(progress, indent=2), encoding="utf-8")
    print(f"\nWrote updated progress.json with {len(new_completed)} completed entries")
    print(f"  Path: {PROGRESS_PATH}")

    # Summary
    print(f"\nResult: image_generator.py will skip {len(new_completed)} completed cards")
    print(f"        and regenerate/complete {len(partial)} partial cards + any cards with no art")


if __name__ == "__main__":
    main()
