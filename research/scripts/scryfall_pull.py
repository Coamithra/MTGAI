"""Scryfall API data pull script for MTG set design research.

Fetches booster-eligible card data for 5 recent MTG sets via the Scryfall API
and stores the raw JSON responses for downstream analysis.

Usage:
    python research/scripts/scryfall_pull.py

Output:
    research/raw-data/{set-code}/cards.json for each set

Sets pulled: dsk (Duskmourn), blb (Bloomburrow), otj (Thunder Junction),
             mkm (Karlov Manor), lci (Lost Caverns of Ixalan)

Rate limiting: 100ms between requests, 500ms between sets.
"""

import json
import sys
import time
from pathlib import Path

import requests

# Sets to analyze
SETS = ["dsk", "blb", "otj", "mkm", "lci"]

# Layouts to exclude (non-playable)
EXCLUDED_LAYOUTS = {"token", "art_series", "emblem", "double_faced_token"}

# Rate limiting
REQUEST_DELAY = 0.1  # 100ms between requests
SET_DELAY = 0.5  # 500ms between sets

# Headers
HEADERS = {
    "User-Agent": "MTGAISetCreator/0.1",
    "Accept": "application/json",
}

# Output directory (relative to project root)
RAW_DATA_DIR = Path(__file__).parent.parent / "raw-data"


def fetch_set_cards(set_code: str) -> list[dict]:
    """Fetch all booster-eligible cards for a set, handling pagination.

    Uses the Scryfall search API with `is:booster` filter, then additionally
    filters out excluded layouts client-side.
    """
    url = f"https://api.scryfall.com/cards/search?q=set:{set_code}+is:booster"
    all_cards: list[dict] = []
    page = 1

    while url:
        print(f"  Fetching page {page}...")
        response = requests.get(url, headers=HEADERS, timeout=30)

        if response.status_code != 200:
            print(f"  ERROR: HTTP {response.status_code} for {url}")
            print(f"  Response: {response.text[:500]}")
            break

        data = response.json()
        page_cards = data.get("data", [])

        # Filter out excluded layouts
        filtered = [c for c in page_cards if c.get("layout") not in EXCLUDED_LAYOUTS]
        all_cards.extend(filtered)

        excluded_count = len(page_cards) - len(filtered)
        if excluded_count > 0:
            print(f"  Excluded {excluded_count} non-playable cards from page {page}")

        # Check for more pages
        if data.get("has_more", False):
            url = data["next_page"]
            page += 1
            time.sleep(REQUEST_DELAY)
        else:
            url = None

    return all_cards


def pull_all_sets() -> dict[str, int]:
    """Pull card data for all configured sets. Returns card counts per set."""
    counts: dict[str, int] = {}

    for i, set_code in enumerate(SETS):
        print(f"\n[{i + 1}/{len(SETS)}] Fetching set: {set_code}")

        cards = fetch_set_cards(set_code)
        counts[set_code] = len(cards)

        # Save raw JSON
        output_dir = RAW_DATA_DIR / set_code
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "cards.json"
        output_path.write_text(
            json.dumps(cards, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print(f"  Saved {len(cards)} cards to {output_path}")

        # Pause between sets
        if i < len(SETS) - 1:
            time.sleep(SET_DELAY)

    return counts


def main() -> None:
    print("=" * 60)
    print("Scryfall Data Pull — MTG AI Set Creator")
    print("=" * 60)

    counts = pull_all_sets()

    print("\n" + "=" * 60)
    print("Summary:")
    print("-" * 40)
    for set_code, count in counts.items():
        print(f"  {set_code}: {count} cards")
    print(f"  Total: {sum(counts.values())} cards")
    print("=" * 60)


if __name__ == "__main__":
    main()
