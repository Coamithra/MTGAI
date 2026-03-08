"""MTG set data analysis script.

Reads raw Scryfall JSON from research/raw-data/{set-code}/cards.json,
computes all metrics defined in Phase 0A plan Section 4, and outputs:
- Human-readable summary tables to stdout
- Structured JSON to research/raw-data/analysis.json

Usage:
    python research/scripts/analyze_sets.py

Metrics computed:
  A. Total card counts & rarity distribution
  B. Color distribution (mono, multi, colorless)
  C. Card type distribution
  D. Mana curve (CMC distribution)
  E. Creature statistics (P/T vs CMC)
  F. Keyword & mechanic analysis (evergreen + set-specific)
  G. Special card counts (legendary, planeswalker, DFC, etc.)
  H. Removal & interaction density
  I. Draft archetype signals (signpost uncommons)
  J. Booster pack composition reference
"""

import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

SETS = ["dsk", "blb", "otj", "mkm", "lci"]
RAW_DATA_DIR = Path(__file__).parent.parent / "raw-data"

EVERGREEN_KEYWORDS = [
    "flying", "first strike", "double strike", "deathtouch", "haste",
    "hexproof", "indestructible", "lifelink", "menace", "reach",
    "trample", "vigilance", "defender", "flash", "ward",
]

COLOR_NAMES = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}

# Patterns for removal detection in oracle text
REMOVAL_PATTERNS = [
    r"destroy target",
    r"exile target",
    r"deals? \d+ damage to",
    r"gets? [+-]\d+/[+-]\d+",
    r"target creature gets -",
    r"destroy all",
    r"exile all",
]

COUNTERSPELL_PATTERN = r"counter target spell"
COMBAT_TRICK_PATTERN = r"gets? \+\d+/\+\d+"


def load_set_cards(set_code: str) -> list[dict]:
    """Load raw card JSON for a set."""
    path = RAW_DATA_DIR / set_code / "cards.json"
    return json.loads(path.read_text(encoding="utf-8"))


def get_card_colors(card: dict) -> list[str]:
    """Get the colors of a card, handling DFCs."""
    return card.get("colors", [])


def is_creature(card: dict) -> bool:
    return "Creature" in card.get("type_line", "")


def is_instant(card: dict) -> bool:
    return "Instant" in card.get("type_line", "")


def is_sorcery(card: dict) -> bool:
    return "Sorcery" in card.get("type_line", "")


def is_enchantment_only(card: dict) -> bool:
    tl = card.get("type_line", "")
    return "Enchantment" in tl and "Creature" not in tl


def is_artifact_only(card: dict) -> bool:
    tl = card.get("type_line", "")
    return "Artifact" in tl and "Creature" not in tl


def is_land(card: dict) -> bool:
    return "Land" in card.get("type_line", "")


def is_basic_land(card: dict) -> bool:
    return "Basic Land" in card.get("type_line", "")


def is_nonbasic_land(card: dict) -> bool:
    return is_land(card) and not is_basic_land(card)


def is_planeswalker(card: dict) -> bool:
    return "Planeswalker" in card.get("type_line", "")


def is_legendary(card: dict) -> bool:
    return "Legendary" in card.get("type_line", "")


def get_oracle_text(card: dict) -> str:
    """Get oracle text, combining faces for DFCs."""
    if card.get("card_faces"):
        return " ".join(f.get("oracle_text", "") for f in card["card_faces"])
    return card.get("oracle_text", "") or ""


def is_removal(card: dict) -> bool:
    text = get_oracle_text(card).lower()
    return any(re.search(p, text) for p in REMOVAL_PATTERNS)


def is_counterspell(card: dict) -> bool:
    text = get_oracle_text(card).lower()
    return bool(re.search(COUNTERSPELL_PATTERN, text))


def is_combat_trick(card: dict) -> bool:
    text = get_oracle_text(card).lower()
    return is_instant(card) and bool(re.search(COMBAT_TRICK_PATTERN, text))


def analyze_card_counts(cards: list[dict]) -> dict:
    """Section 4.1A: Total card counts."""
    rarity_counts = Counter(c["rarity"] for c in cards)
    basic_lands = sum(1 for c in cards if is_basic_land(c))
    return {
        "total": len(cards),
        "common": rarity_counts.get("common", 0),
        "uncommon": rarity_counts.get("uncommon", 0),
        "rare": rarity_counts.get("rare", 0),
        "mythic": rarity_counts.get("mythic", 0),
        "basic_lands": basic_lands,
        "total_minus_basics": len(cards) - basic_lands,
    }


def analyze_color_distribution(cards: list[dict]) -> dict:
    """Section 4.1B: Color distribution."""
    mono = Counter()
    multi_count = 0
    colorless_count = 0
    color_pair_counter = Counter()

    non_land = [c for c in cards if not is_land(c)]

    for card in non_land:
        colors = get_card_colors(card)
        if len(colors) == 0:
            colorless_count += 1
        elif len(colors) == 1:
            mono[colors[0]] += 1
        else:
            multi_count += 1
            pair = "".join(sorted(colors))
            color_pair_counter[pair] += 1

    total_non_land = len(non_land)
    result = {
        "mono_counts": dict(mono),
        "multicolor_count": multi_count,
        "colorless_count": colorless_count,
        "total_non_land": total_non_land,
        "color_pair_distribution": dict(color_pair_counter),
    }

    # Per-color percentages (mono only)
    if total_non_land > 0:
        result["mono_pct"] = {
            c: round(mono.get(c, 0) / total_non_land * 100, 1)
            for c in "WUBRG"
        }
        result["multi_pct"] = round(multi_count / total_non_land * 100, 1)
        result["colorless_pct"] = round(colorless_count / total_non_land * 100, 1)

    # Per-rarity color distribution
    per_rarity = {}
    for rarity in ["common", "uncommon", "rare", "mythic"]:
        rarity_cards = [c for c in non_land if c["rarity"] == rarity]
        rarity_mono = Counter()
        rarity_multi = 0
        rarity_colorless = 0
        for card in rarity_cards:
            colors = get_card_colors(card)
            if len(colors) == 0:
                rarity_colorless += 1
            elif len(colors) == 1:
                rarity_mono[colors[0]] += 1
            else:
                rarity_multi += 1
        per_rarity[rarity] = {
            "mono": dict(rarity_mono),
            "multicolor": rarity_multi,
            "colorless": rarity_colorless,
            "total": len(rarity_cards),
        }
    result["per_rarity"] = per_rarity

    return result


def analyze_type_distribution(cards: list[dict]) -> dict:
    """Section 4.1C: Card type distribution."""
    counts = {
        "creature": sum(1 for c in cards if is_creature(c)),
        "instant": sum(1 for c in cards if is_instant(c)),
        "sorcery": sum(1 for c in cards if is_sorcery(c)),
        "enchantment_only": sum(1 for c in cards if is_enchantment_only(c)),
        "artifact_only": sum(1 for c in cards if is_artifact_only(c)),
        "land_nonbasic": sum(1 for c in cards if is_nonbasic_land(c)),
        "land_basic": sum(1 for c in cards if is_basic_land(c)),
        "planeswalker": sum(1 for c in cards if is_planeswalker(c)),
    }

    # Count hybrid types
    counts["enchantment_creature"] = sum(
        1 for c in cards
        if "Enchantment" in c.get("type_line", "") and "Creature" in c.get("type_line", "")
    )
    counts["artifact_creature"] = sum(
        1 for c in cards
        if "Artifact" in c.get("type_line", "") and "Creature" in c.get("type_line", "")
    )

    total = len(cards)
    if total > 0:
        counts["creature_pct"] = round(counts["creature"] / total * 100, 1)
        counts["instant_pct"] = round(counts["instant"] / total * 100, 1)
        counts["sorcery_pct"] = round(counts["sorcery"] / total * 100, 1)

    # Per-rarity type distribution
    per_rarity = {}
    for rarity in ["common", "uncommon", "rare", "mythic"]:
        r_cards = [c for c in cards if c["rarity"] == rarity]
        per_rarity[rarity] = {
            "creature": sum(1 for c in r_cards if is_creature(c)),
            "instant": sum(1 for c in r_cards if is_instant(c)),
            "sorcery": sum(1 for c in r_cards if is_sorcery(c)),
            "enchantment_only": sum(1 for c in r_cards if is_enchantment_only(c)),
            "artifact_only": sum(1 for c in r_cards if is_artifact_only(c)),
            "land_nonbasic": sum(1 for c in r_cards if is_nonbasic_land(c)),
            "planeswalker": sum(1 for c in r_cards if is_planeswalker(c)),
            "total": len(r_cards),
        }
    counts["per_rarity"] = per_rarity

    return counts


def analyze_mana_curve(cards: list[dict]) -> dict:
    """Section 4.1D: Mana value / CMC distribution."""
    non_land = [c for c in cards if not is_land(c)]
    cmcs = [c.get("cmc", 0) for c in non_land]

    # Bucket CMC values
    buckets = defaultdict(int)
    for cmc in cmcs:
        key = int(cmc) if cmc < 7 else 7
        buckets[key] += 1

    total = len(non_land)
    distribution = {}
    for i in range(8):
        label = f"cmc_{i}" if i < 7 else "cmc_7plus"
        count = buckets.get(i, 0)
        distribution[label] = {
            "count": count,
            "pct": round(count / total * 100, 1) if total > 0 else 0,
        }

    result = {
        "distribution": distribution,
        "average_cmc": round(statistics.mean(cmcs), 2) if cmcs else 0,
        "median_cmc": round(statistics.median(cmcs), 1) if cmcs else 0,
    }

    # Per-color mana curve
    per_color = {}
    for color in "WUBRG":
        color_cards = [c for c in non_land if get_card_colors(c) == [color]]
        color_cmcs = [c.get("cmc", 0) for c in color_cards]
        if color_cmcs:
            color_buckets = defaultdict(int)
            for cmc in color_cmcs:
                key = int(cmc) if cmc < 7 else 7
                color_buckets[key] += 1
            per_color[color] = {
                "average_cmc": round(statistics.mean(color_cmcs), 2),
                "count": len(color_cards),
                "distribution": {
                    str(i): color_buckets.get(i, 0) for i in range(8)
                },
            }
    result["per_color"] = per_color

    # Per-rarity mana curve
    per_rarity = {}
    for rarity in ["common", "uncommon", "rare", "mythic"]:
        r_cards = [c for c in non_land if c["rarity"] == rarity]
        r_cmcs = [c.get("cmc", 0) for c in r_cards]
        if r_cmcs:
            per_rarity[rarity] = {
                "average_cmc": round(statistics.mean(r_cmcs), 2),
                "count": len(r_cards),
            }
    result["per_rarity"] = per_rarity

    return result


def analyze_creature_stats(cards: list[dict]) -> dict:
    """Section 4.1E: Creature statistics."""
    creatures = [c for c in cards if is_creature(c)]

    pt_by_cmc = defaultdict(list)
    subtypes = Counter()

    for c in creatures:
        power = c.get("power")
        toughness = c.get("toughness")
        cmc = int(c.get("cmc", 0))

        # Parse P/T (skip * values for averages)
        try:
            p = int(power)
            t = int(toughness)
            pt_by_cmc[cmc].append((p, t))
        except (ValueError, TypeError):
            pass

        # Subtypes
        tl = c.get("type_line", "")
        if "—" in tl:
            sub_part = tl.split("—")[1].strip()
            for subtype in sub_part.split():
                if subtype.strip():
                    subtypes[subtype.strip()] += 1

    # Average P/T per CMC
    avg_pt_by_cmc = {}
    for cmc, pts in sorted(pt_by_cmc.items()):
        if pts:
            avg_p = round(statistics.mean(p for p, t in pts), 2)
            avg_t = round(statistics.mean(t for p, t in pts), 2)
            avg_pt_by_cmc[str(cmc)] = {
                "avg_power": avg_p,
                "avg_toughness": avg_t,
                "count": len(pts),
            }

    return {
        "total_creatures": len(creatures),
        "avg_pt_by_cmc": avg_pt_by_cmc,
        "top_subtypes": dict(subtypes.most_common(20)),
    }


def analyze_keywords(cards: list[dict]) -> dict:
    """Section 4.1F: Keyword & mechanic analysis."""
    evergreen_counts = Counter()
    evergreen_by_color = defaultdict(Counter)
    evergreen_by_rarity = defaultdict(Counter)
    set_mechanics = Counter()
    set_mechanics_by_color = defaultdict(Counter)
    set_mechanics_by_rarity = defaultdict(Counter)

    for card in cards:
        keywords = [kw.lower() for kw in card.get("keywords", [])]
        colors = get_card_colors(card)
        rarity = card.get("rarity", "common")

        for kw in keywords:
            if kw in EVERGREEN_KEYWORDS:
                evergreen_counts[kw] += 1
                for color in colors:
                    evergreen_by_color[kw][color] += 1
                evergreen_by_rarity[kw][rarity] += 1
            else:
                set_mechanics[kw] += 1
                for color in colors:
                    set_mechanics_by_color[kw][color] += 1
                set_mechanics_by_rarity[kw][rarity] += 1

    # As-fan calculation for evergreen keywords
    commons = [c for c in cards if c["rarity"] == "common"]
    uncommons = [c for c in cards if c["rarity"] == "uncommon"]
    rares = [c for c in cards if c["rarity"] == "rare"]

    as_fan = {}
    for kw in evergreen_counts:
        common_count = sum(1 for c in commons if kw in [k.lower() for k in c.get("keywords", [])])
        uncommon_count = sum(
            1 for c in uncommons if kw in [k.lower() for k in c.get("keywords", [])]
        )
        rare_count = sum(1 for c in rares if kw in [k.lower() for k in c.get("keywords", [])])

        total_c = len(commons) or 1
        total_u = len(uncommons) or 1
        total_r = len(rares) or 1

        # As-fan = (count_at_rarity / total_at_rarity) * slots_per_pack
        af = (
            (common_count / total_c) * 10
            + (uncommon_count / total_u) * 3
            + (rare_count / total_r) * 1
        )
        as_fan[kw] = round(af, 3)

    return {
        "evergreen": dict(evergreen_counts),
        "evergreen_by_color": {kw: dict(colors) for kw, colors in evergreen_by_color.items()},
        "evergreen_by_rarity": {kw: dict(r) for kw, r in evergreen_by_rarity.items()},
        "set_mechanics": dict(set_mechanics),
        "set_mechanics_by_color": {
            kw: dict(colors) for kw, colors in set_mechanics_by_color.items()
        },
        "set_mechanics_by_rarity": {
            kw: dict(r) for kw, r in set_mechanics_by_rarity.items()
        },
        "num_set_mechanics": len(set_mechanics),
        "total_cards_with_set_mechanic": sum(set_mechanics.values()),
        "as_fan": as_fan,
    }


def analyze_special_cards(cards: list[dict]) -> dict:
    """Section 4.1G: Special card counts."""
    legendary_creatures = [c for c in cards if is_legendary(c) and is_creature(c)]
    legendary_by_rarity = Counter(c["rarity"] for c in legendary_creatures)

    planeswalkers = [c for c in cards if is_planeswalker(c)]
    pw_by_rarity = Counter(c["rarity"] for c in planeswalkers)

    return {
        "legendary_creatures": len(legendary_creatures),
        "legendary_by_rarity": dict(legendary_by_rarity),
        "planeswalkers": len(planeswalkers),
        "planeswalker_by_rarity": dict(pw_by_rarity),
        "sagas": sum(1 for c in cards if "Saga" in c.get("type_line", "")),
        "modal_dfc": sum(1 for c in cards if c.get("layout") == "modal_dfc"),
        "transform_dfc": sum(1 for c in cards if c.get("layout") == "transform"),
        "equipment": sum(1 for c in cards if "Equipment" in c.get("type_line", "")),
        "auras": sum(1 for c in cards if "Aura" in c.get("type_line", "")),
        "vehicles": sum(1 for c in cards if "Vehicle" in c.get("type_line", "")),
    }


def analyze_removal(cards: list[dict]) -> dict:
    """Section 4.1H: Removal & interaction density."""
    removal_cards = [c for c in cards if is_removal(c)]
    removal_by_color = defaultdict(int)
    removal_by_rarity = Counter()

    for c in removal_cards:
        removal_by_rarity[c["rarity"]] += 1
        colors = get_card_colors(c)
        if not colors:
            removal_by_color["colorless"] += 1
        for color in colors:
            removal_by_color[color] += 1

    counterspells = sum(1 for c in cards if is_counterspell(c))
    combat_tricks = sum(1 for c in cards if is_combat_trick(c))

    return {
        "total_removal": len(removal_cards),
        "removal_by_color": dict(removal_by_color),
        "removal_by_rarity": dict(removal_by_rarity),
        "counterspells": counterspells,
        "combat_tricks": combat_tricks,
    }


def analyze_draft_signals(cards: list[dict]) -> dict:
    """Section 4.1I: Draft archetype signals."""
    uncommon_multi = [
        c for c in cards
        if c["rarity"] == "uncommon" and len(get_card_colors(c)) >= 2
    ]
    rare_multi = [
        c for c in cards
        if c["rarity"] in ("rare", "mythic") and len(get_card_colors(c)) >= 2
    ]

    # Group uncommon multicolor by color pair
    signpost_pairs = Counter()
    signpost_cards = {}
    for c in uncommon_multi:
        colors = sorted(get_card_colors(c))
        if len(colors) == 2:
            pair = "".join(colors)
            signpost_pairs[pair] += 1
            if pair not in signpost_cards:
                signpost_cards[pair] = []
            signpost_cards[pair].append(c["name"])

    all_pairs = ["BG", "BR", "BU", "BW", "GR", "GU", "GW", "RU", "RW", "UW"]
    coverage = {p: signpost_pairs.get(p, 0) for p in all_pairs}

    return {
        "uncommon_multicolor_count": len(uncommon_multi),
        "rare_multicolor_count": len(rare_multi),
        "signpost_pair_coverage": coverage,
        "signpost_card_names": signpost_cards,
        "pairs_covered": sum(1 for v in coverage.values() if v > 0),
    }


def analyze_set(set_code: str) -> dict:
    """Run all analyses on a single set."""
    cards = load_set_cards(set_code)
    return {
        "set_code": set_code,
        "card_counts": analyze_card_counts(cards),
        "color_distribution": analyze_color_distribution(cards),
        "type_distribution": analyze_type_distribution(cards),
        "mana_curve": analyze_mana_curve(cards),
        "creature_stats": analyze_creature_stats(cards),
        "keywords": analyze_keywords(cards),
        "special_cards": analyze_special_cards(cards),
        "removal": analyze_removal(cards),
        "draft_signals": analyze_draft_signals(cards),
    }


def compute_cross_set_averages(all_analyses: list[dict]) -> dict:
    """Compute averages, min, max across all sets for key metrics."""
    n = len(all_analyses)

    def avg_metric(path_fn):
        values = [path_fn(a) for a in all_analyses]
        return {
            "average": round(statistics.mean(values), 1),
            "min": min(values),
            "max": max(values),
            "stdev": round(statistics.stdev(values), 1) if n > 1 else 0,
        }

    return {
        "total_cards": avg_metric(lambda a: a["card_counts"]["total"]),
        "commons": avg_metric(lambda a: a["card_counts"]["common"]),
        "uncommons": avg_metric(lambda a: a["card_counts"]["uncommon"]),
        "rares": avg_metric(lambda a: a["card_counts"]["rare"]),
        "mythics": avg_metric(lambda a: a["card_counts"]["mythic"]),
        "creature_pct": avg_metric(lambda a: a["type_distribution"]["creature_pct"]),
        "average_cmc": avg_metric(lambda a: a["mana_curve"]["average_cmc"]),
        "total_removal": avg_metric(lambda a: a["removal"]["total_removal"]),
        "legendary_creatures": avg_metric(lambda a: a["special_cards"]["legendary_creatures"]),
        "planeswalkers": avg_metric(lambda a: a["special_cards"]["planeswalkers"]),
        "uncommon_signpost_pairs": avg_metric(
            lambda a: a["draft_signals"]["pairs_covered"]
        ),
        "set_mechanics_count": avg_metric(lambda a: a["keywords"]["num_set_mechanics"]),
    }


def print_summary(all_analyses: list[dict], averages: dict) -> None:
    """Print human-readable summary tables."""
    print("\n" + "=" * 80)
    print("MTG SET ANALYSIS — CROSS-SET SUMMARY")
    print("=" * 80)

    # Card counts table
    print("\n### Card Counts by Rarity")
    print(f"{'Set':<6} {'Total':>6} {'Common':>8} {'Uncommon':>8} {'Rare':>6} {'Mythic':>7} {'Basic':>6}")
    print("-" * 55)
    for a in all_analyses:
        cc = a["card_counts"]
        print(
            f"{a['set_code']:<6} {cc['total']:>6} {cc['common']:>8} "
            f"{cc['uncommon']:>8} {cc['rare']:>6} {cc['mythic']:>7} {cc['basic_lands']:>6}"
        )
    print("-" * 55)
    print(
        f"{'AVG':<6} {averages['total_cards']['average']:>6.0f} "
        f"{averages['commons']['average']:>8.0f} {averages['uncommons']['average']:>8.0f} "
        f"{averages['rares']['average']:>6.0f} {averages['mythics']['average']:>7.0f}"
    )

    # Color distribution
    print("\n### Mono-Color Distribution (% of non-land cards)")
    print(f"{'Set':<6} {'W':>6} {'U':>6} {'B':>6} {'R':>6} {'G':>6} {'Multi':>7} {'CL':>6}")
    print("-" * 55)
    for a in all_analyses:
        cd = a["color_distribution"]
        mp = cd.get("mono_pct", {})
        print(
            f"{a['set_code']:<6} {mp.get('W', 0):>5.1f}% {mp.get('U', 0):>5.1f}% "
            f"{mp.get('B', 0):>5.1f}% {mp.get('R', 0):>5.1f}% {mp.get('G', 0):>5.1f}% "
            f"{cd.get('multi_pct', 0):>6.1f}% {cd.get('colorless_pct', 0):>5.1f}%"
        )

    # Mana curve
    print("\n### Average CMC (non-land cards)")
    for a in all_analyses:
        mc = a["mana_curve"]
        print(f"  {a['set_code']}: avg={mc['average_cmc']}, median={mc['median_cmc']}")
    print(
        f"  AVERAGE: {averages['average_cmc']['average']}"
        f" (range: {averages['average_cmc']['min']}-{averages['average_cmc']['max']})"
    )

    # Removal
    print("\n### Removal Density")
    for a in all_analyses:
        rm = a["removal"]
        print(
            f"  {a['set_code']}: {rm['total_removal']} removal spells, "
            f"{rm['counterspells']} counterspells, {rm['combat_tricks']} combat tricks"
        )

    # Draft signals
    print("\n### Draft Archetype Coverage (10 color pairs)")
    for a in all_analyses:
        ds = a["draft_signals"]
        print(
            f"  {a['set_code']}: {ds['pairs_covered']}/10 pairs covered "
            f"({ds['uncommon_multicolor_count']} uncommon multicolor cards)"
        )

    # Keywords
    print("\n### Top Evergreen Keywords (cross-set totals)")
    total_evergreen = Counter()
    for a in all_analyses:
        for kw, count in a["keywords"]["evergreen"].items():
            total_evergreen[kw] += count
    for kw, count in total_evergreen.most_common(15):
        avg = count / len(all_analyses)
        print(f"  {kw:<20} total={count:>4}  avg/set={avg:>5.1f}")

    print("\n### Set-Specific Mechanics")
    for a in all_analyses:
        kw = a["keywords"]
        top = sorted(kw["set_mechanics"].items(), key=lambda x: -x[1])[:5]
        top_str = ", ".join(f"{k}({v})" for k, v in top)
        print(f"  {a['set_code']}: {kw['num_set_mechanics']} mechanics — {top_str}")


def main() -> None:
    print("=" * 60)
    print("MTG Set Analysis — Phase 0A-2")
    print("=" * 60)

    all_analyses = []
    for set_code in SETS:
        print(f"\nAnalyzing {set_code}...")
        analysis = analyze_set(set_code)
        all_analyses.append(analysis)

    averages = compute_cross_set_averages(all_analyses)

    # Save structured JSON
    output = {
        "sets": all_analyses,
        "cross_set_averages": averages,
    }
    output_path = RAW_DATA_DIR / "analysis.json"
    output_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nFull analysis saved to {output_path}")

    print_summary(all_analyses, averages)


if __name__ == "__main__":
    main()
