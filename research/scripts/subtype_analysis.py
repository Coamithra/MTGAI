"""Scryfall subtype-distribution analysis for the skeleton-detail card.

Pulls the last N premier sets (set_type in {expansion, core}, paper, non-digital)
and tabulates, per set, the count of cards in each fine-grained *subtype* the
skeleton might want to model:

* artifact subtypes: Equipment, Vehicle, (plain) Artifact, ...
* enchantment subtypes: Aura, Saga, Class, Room, Shrine, Background, Case, ...
* dual creature types: Artifact Creature, Enchantment Creature
* the Battle card type (Siege)

Then classifies each subtype by how many of the analyzed sets it appears in
(recurring vs irregular vs one-off), which decides whether it becomes a standing
skeleton knob or goes in the "irregular bucket" (pick 0-2 per set).

Usage:
    python research/scripts/subtype_analysis.py [N]    # N = number of sets (default 14)

Writes research/raw-data/subtype-analysis.json and prints a summary table.
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

HEADERS = {"User-Agent": "MTGAISetCreator/0.1", "Accept": "application/json"}
EXCLUDED_LAYOUTS = {"token", "art_series", "emblem", "double_faced_token"}
REQUEST_DELAY = 0.1
SET_DELAY = 0.25
OUT_DIR = Path(__file__).parent.parent / "raw-data"

# Subtypes we care about, grouped by the parent card type. We scan the type line
# (front face) for these tokens. "creature dual types" are detected separately.
ARTIFACT_SUBTYPES = ["Equipment", "Vehicle", "Attraction", "Contraption", "Fortification"]
ENCHANTMENT_SUBTYPES = [
    "Aura",
    "Saga",
    "Class",
    "Room",
    "Shrine",
    "Background",
    "Case",
    "Cartouche",
    "Curse",
    "Rune",
    "Shard",
]


def fetch_premier_sets(n: int) -> list[dict]:
    """Return the most recent *n* premier sets (expansion/core, paper, released)."""
    r = requests.get("https://api.scryfall.com/sets", headers=HEADERS, timeout=30)
    r.raise_for_status()
    sets = r.json().get("data", [])
    import datetime

    today = datetime.date.today().isoformat()
    premier = [
        s
        for s in sets
        if s.get("set_type") in {"expansion", "core"}
        and not s.get("digital", False)
        and (s.get("released_at") or "9999") <= today
        and (s.get("card_count") or 0) > 100  # skip tiny/special drops
    ]
    premier.sort(key=lambda s: s.get("released_at", ""), reverse=True)
    return premier[:n]


def fetch_set_cards(code: str) -> list[dict]:
    url = f"https://api.scryfall.com/cards/search?q=set:{code}+is:booster"
    out: list[dict] = []
    while url:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            print(f"  ERROR HTTP {resp.status_code} for {code}: {resp.text[:200]}")
            break
        data = resp.json()
        out.extend(c for c in data.get("data", []) if c.get("layout") not in EXCLUDED_LAYOUTS)
        url = data["next_page"] if data.get("has_more") else None
        if url:
            time.sleep(REQUEST_DELAY)
    return out


def front_type_line(card: dict) -> str:
    """Type line of the front face (DFCs put the front first)."""
    tl = card.get("type_line") or ""
    if "//" in tl:
        tl = tl.split("//")[0]
    faces = card.get("card_faces")
    if not tl and isinstance(faces, list) and faces:
        tl = faces[0].get("type_line", "")
    return tl.strip()


def analyze_set(cards: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    counts["_total"] = 0
    for c in cards:
        tl = front_type_line(c)
        if not tl:
            continue
        counts["_total"] += 1
        is_creature = "Creature" in tl
        is_artifact = "Artifact" in tl
        is_enchantment = "Enchantment" in tl

        if "Battle" in tl:
            counts["Battle"] += 1
        # dual creature types
        if is_creature and is_artifact:
            counts["Artifact Creature"] += 1
        if is_creature and is_enchantment:
            counts["Enchantment Creature"] += 1
        # non-creature artifact subtypes
        if is_artifact and not is_creature:
            matched = False
            for st in ARTIFACT_SUBTYPES:
                if st in tl:
                    counts[st] += 1
                    matched = True
            if not matched:
                counts["Artifact (plain)"] += 1
        # non-creature enchantment subtypes
        if is_enchantment and not is_creature:
            matched = False
            for st in ENCHANTMENT_SUBTYPES:
                if st in tl:
                    counts[st] += 1
                    matched = True
            if not matched:
                counts["Enchantment (plain)"] += 1
    return dict(counts)


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    sets = fetch_premier_sets(n)
    print(f"Analyzing {len(sets)} premier sets:")
    for s in sets:
        print(f"  {s['code']:5} {s.get('released_at','?')}  {s.get('name')}")

    per_set: dict[str, dict[str, int]] = {}
    for i, s in enumerate(sets):
        code = s["code"]
        print(f"\n[{i + 1}/{len(sets)}] {code} ...")
        cards = fetch_set_cards(code)
        per_set[code] = analyze_set(cards)
        per_set[code]["_name"] = s.get("name")  # type: ignore
        per_set[code]["_released"] = s.get("released_at")  # type: ignore
        print(f"  {per_set[code]['_total']} booster cards analyzed")
        time.sleep(SET_DELAY)

    # Aggregate: per subtype, list of per-set counts + how many sets it appears in.
    subtypes = set()
    for d in per_set.values():
        subtypes.update(k for k in d if not k.startswith("_"))

    agg: dict[str, dict] = {}
    n_sets = len(per_set)
    for st in sorted(subtypes):
        vals = [per_set[c].get(st, 0) for c in per_set]
        present = sum(1 for v in vals if v > 0)
        nonzero = [v for v in vals if v > 0]
        agg[st] = {
            "present_in_sets": present,
            "present_frac": round(present / n_sets, 2),
            "avg_when_present": round(sum(nonzero) / len(nonzero), 1) if nonzero else 0,
            "avg_overall": round(sum(vals) / n_sets, 1),
            "min": min(vals),
            "max": max(vals),
            "per_set": {c: per_set[c].get(st, 0) for c in per_set},
        }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "subtype-analysis.json"
    out_path.write_text(
        json.dumps(
            {"sets": [{"code": s["code"], "name": s.get("name"), "released": s.get("released_at")} for s in sets],
             "per_set": per_set, "aggregate": agg},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("\n" + "=" * 78)
    print(f"{'Subtype':<22} {'in_sets':>8} {'frac':>6} {'avg/set':>8} {'avg(present)':>13} {'min':>4} {'max':>4}")
    print("-" * 78)
    for st, a in sorted(agg.items(), key=lambda kv: kv[1]["present_in_sets"], reverse=True):
        print(
            f"{st:<22} {a['present_in_sets']:>5}/{n_sets:<2} {a['present_frac']:>6} "
            f"{a['avg_overall']:>8} {a['avg_when_present']:>13} {a['min']:>4} {a['max']:>4}"
        )
    print("=" * 78)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
