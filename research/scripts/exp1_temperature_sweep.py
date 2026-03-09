"""Experiment 1: Temperature Sweep

Generate 24 test cards at 4 different temperatures (0.3, 0.5, 0.7, 1.0)
using Claude Sonnet. Score all 96 cards. Find the optimal temperature.

Usage:
    python research/scripts/exp1_temperature_sweep.py
"""

import json
import re
import sys
import time
from pathlib import Path

# Add research/scripts to path for cached_llm import
sys.path.insert(0, "research/scripts")
from cached_llm import CachedLLM, CARDS_BATCH_TOOL_SCHEMA

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-20250514"
TEMPERATURES = [0.3, 0.5, 0.7, 1.0]
OUTPUT_DIR = Path("research/prompt-templates/experiments/exp1_temperature")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# System prompt — extracted from system-prompt-v1.md (between ``` fences)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = r"""You are an expert Magic: The Gathering card designer with deep knowledge of game mechanics, color pie philosophy, and competitive balance.

Your task is to design original MTG cards and return them as valid JSON. Follow these rules precisely.

## MTG Rules Reference

### Evergreen Keywords
Flying, First strike, Double strike, Deathtouch, Trample, Vigilance, Haste, Lifelink, Reach, Menace, Hexproof, Flash, Defender, Indestructible, Ward {N}.

### Common Keyword Actions
Destroy, Exile, Sacrifice, Scry N, Mill N, Fight, Create token, Counter, Draw.

### Rules Text Patterns
- Self-reference: Always use ~ for the card's own name. Write "When ~ enters" not "When this creature enters" or "When [Card Name] enters".
- Triggered abilities: "When ~ enters, ...", "Whenever ~ attacks, ...", "At the beginning of your upkeep, ...", "When ~ dies, ..."
- Activated abilities: "{cost}: {effect}" — e.g., "{T}: Add {G}." or "{2}{B}, Sacrifice a creature: Draw a card."
- Static abilities: Keyword on its own line, or "Other creatures you control get +1/+1."
- Modal spells: "Choose one —\n* Effect A.\n* Effect B."
- Mana symbols: {W} white, {U} blue, {B} black, {R} red, {G} green, {C} colorless, {X} variable, {T} tap.

### Mana Cost Format
Generic mana first, then WUBRG order: {2}{W}{U} is correct, {W}{2}{U} is wrong. X costs come first: {X}{R}{R}.

## Color Pie

- **White (W)**: Lifegain, small creatures, tokens, exile-based removal, enchantments, vigilance, flying (small). Cannot draw cards without restriction.
- **Blue (U)**: Card draw, counterspells, bounce, flying (large), mill, scry, flash. Cannot destroy permanents directly.
- **Black (B)**: Creature destruction, discard, drain life, deathtouch, menace, raise dead, sacrifice-for-value. Pays life as a cost.
- **Red (R)**: Direct damage (burn), haste, temporary power boosts, artifact destruction, impulsive draw (exile top, cast this turn). Cannot gain life or destroy enchantments.
- **Green (G)**: Large creatures, mana ramp, trample, fight-based removal, +1/+1 counters, enchantment/artifact destruction, reach. Cannot deal direct damage to players.

## New World Order (Complexity by Rarity)

- **Common**: Simple. One keyword ability OR one short text ability. No complex board interactions. Creatures should have clean stats.
- **Uncommon**: Moderate. Up to two abilities or one complex ability. Signpost multicolor uncommons define draft archetypes.
- **Rare**: Complex allowed. Splashy effects, build-around potential, powerful legendaries.
- **Mythic**: Spectacular and unique. Planeswalkers, game-changing effects, iconic creatures.

### Power Level Guidelines
- Common creatures: P + T should not exceed CMC + 3. Extra stats require a drawback.
- Removal at common should be conditional or expensive. Unconditional removal starts at uncommon.
- Card draw at common: 1 card only, with a condition or at sorcery speed.

## Output Format

Return valid JSON matching this schema:

{
  "name": "string — original name, not an existing MTG card",
  "mana_cost": "string — e.g., '{2}{W}{U}'",
  "cmc": "number — converted mana cost total (X counts as 0)",
  "colors": ["W", "U", "B", "R", "G"] — subset matching mana_cost colors,
  "color_identity": ["W", "U", "B", "R", "G"] — colors from mana_cost AND oracle_text mana symbols,
  "type_line": "string — e.g., 'Creature — Human Wizard' or 'Legendary Enchantment'",
  "oracle_text": "string — rules text using ~ for self-reference. Separate abilities with \n",
  "flavor_text": "string or null — evocative in-world flavor",
  "power": "string or null — required for creatures, e.g., '3' or '*'",
  "toughness": "string or null — required for creatures",
  "loyalty": "string or null — required for planeswalkers",
  "rarity": "common | uncommon | rare | mythic",
  "layout": "normal",
  "design_notes": "string — explain your design intent, color pie reasoning, and power level choices"
}

### Field Rules
- power and toughness are strings (to support */*, X/X, etc.).
- cmc must equal the total mana value of mana_cost (each {W},{U},{B},{R},{G},{C} = 1, each {N} = N, {X} = 0).
- colors must exactly match the colored mana symbols in mana_cost. A card with mana_cost "{2}{R}" has colors ["R"].
- color_identity includes colors from both mana_cost and any mana symbols in oracle_text.
- Separate multiple abilities in oracle_text with \n (newline).
- Include flavor_text for most cards. Omit it only if rules text is very long.

## Constraints

- DO NOT use silver-border or un-set mechanics (no dice rolling, no subgames, no breaking the fourth wall).
- DO NOT reference real-world people, places, brands, or events.
- DO NOT reuse existing MTG card names. All names must be original.
- DO NOT use the card's actual name in oracle_text — always use ~ as self-reference.
- DO NOT create cards that are strictly better than iconic staples at the same rarity and cost.
- DO NOT put reminder text in oracle_text unless specifically requested. Reminder text goes in a separate field if needed."""

# ---------------------------------------------------------------------------
# 24-Card Test Matrix
# ---------------------------------------------------------------------------

CARD_SLOTS = [
    {"slot": 1,  "color": "W", "rarity": "common",   "type": "Creature",              "complexity": "Vanilla",       "notes": "No abilities, just P/T. Tests restraint."},
    {"slot": 2,  "color": "W", "rarity": "common",   "type": "Creature",              "complexity": "Keyword-only",  "notes": "Flying, lifelink, vigilance, etc. One keyword creature."},
    {"slot": 3,  "color": "W", "rarity": "uncommon", "type": "Instant",               "complexity": "Single ability", "notes": "Exile target... style. White's primary removal at uncommon."},
    {"slot": 4,  "color": "U", "rarity": "common",   "type": "Instant",               "complexity": "Single ability", "notes": "Draw + minor effect. Tests MTG draw templating (cantrip)."},
    {"slot": 5,  "color": "U", "rarity": "uncommon", "type": "Instant",               "complexity": "Single ability", "notes": "Counterspell variant. Tests stack interaction wording."},
    {"slot": 6,  "color": "U", "rarity": "rare",     "type": "Sorcery",               "complexity": "Multi-ability",  "notes": "Card selection/draw with choice. Tests modal wording."},
    {"slot": 7,  "color": "B", "rarity": "common",   "type": "Instant",               "complexity": "Single ability", "notes": "Destroy/damage creature. Tests targeting language."},
    {"slot": 8,  "color": "B", "rarity": "uncommon", "type": "Creature",              "complexity": "Multi-ability",  "notes": "ETB + graveyard interaction. Tests trigger wording."},
    {"slot": 9,  "color": "B", "rarity": "mythic",   "type": "Creature",              "complexity": "Multi-ability",  "notes": "Legendary creature, 2-3 abilities. Tests legendary design."},
    {"slot": 10, "color": "R", "rarity": "common",   "type": "Instant",               "complexity": "Single ability", "notes": "Direct damage (burn spell). Tests damage assignment wording."},
    {"slot": 11, "color": "R", "rarity": "common",   "type": "Creature",              "complexity": "Keyword-only",  "notes": "Haste + maybe another keyword. Tests aggressive statlines."},
    {"slot": 12, "color": "R", "rarity": "mythic",   "type": "Creature",              "complexity": "Multi-ability",  "notes": "Dragon or similar. Tests splashy mythic design."},
    {"slot": 13, "color": "G", "rarity": "common",   "type": "Sorcery",               "complexity": "Single ability", "notes": "Search for land. Tests 'search your library' templating."},
    {"slot": 14, "color": "G", "rarity": "common",   "type": "Creature",              "complexity": "Keyword-only",  "notes": "Big body with trample. Tests common P/T ceiling."},
    {"slot": 15, "color": "G", "rarity": "uncommon", "type": "Enchantment",           "complexity": "Multi-ability",  "notes": "Aura or static enchantment. Tests enchantment templating."},
    {"slot": 16, "color": "WU", "rarity": "uncommon","type": "Creature",              "complexity": "Multi-ability",  "notes": "Azorius archetype signpost. Tests gold card design."},
    {"slot": 17, "color": "BR", "rarity": "rare",    "type": "Creature",              "complexity": "Multi-ability",  "notes": "Rakdos build-around. Tests two-color identity."},
    {"slot": 18, "color": "C",  "rarity": "common",  "type": "Artifact",              "complexity": "Single ability", "notes": "Equipment or mana rock. Tests artifact templating."},
    {"slot": 19, "color": "C",  "rarity": "rare",    "type": "Artifact",              "complexity": "Multi-ability",  "notes": "Complex artifact with activated abilities. Tests tap/cost syntax."},
    {"slot": 20, "color": "WB", "rarity": "mythic",  "type": "Planeswalker",          "complexity": "Multi-ability",  "notes": "3 loyalty abilities. Tests planeswalker templating."},
    {"slot": 21, "color": "R",  "rarity": "rare",    "type": "Instant",               "complexity": "Modal",         "notes": "'Choose one' or 'Choose two' spell. Tests modal formatting."},
    {"slot": 22, "color": "G",  "rarity": "rare",    "type": "Enchantment — Saga",    "complexity": "Multi-ability",  "notes": "Chapter abilities. Tests Saga templating."},
    {"slot": 23, "color": "C",  "rarity": "uncommon","type": "Land",                  "complexity": "Single ability", "notes": "Nonbasic with activated ability. Tests land templating."},
    {"slot": 24, "color": "-",  "rarity": "common",  "type": "Basic Land — Forest",   "complexity": "Flavor text only","notes": "Tests basic land generation (name + flavor text only)."},
]

# Batches
BATCHES = [
    [1, 2, 3, 4, 5],      # white + blue
    [6, 7, 8, 9, 10],     # blue rare + black
    [11, 12, 13, 14, 15],  # red + green
    [16, 17, 18, 19, 20],  # multicolor + artifacts + planeswalker
    [21, 22, 23, 24],      # modal + saga + lands
]


def build_batch_prompt(slot_indices: list[int]) -> str:
    """Build the user prompt for a batch of card slots."""
    lines = [
        f"Generate {len(slot_indices)} Magic: The Gathering cards. "
        "Each card must fill a specific slot.\n"
    ]
    lines.append("**Slots to fill**:\n")
    for idx in slot_indices:
        card = CARD_SLOTS[idx - 1]  # slots are 1-indexed
        lines.append(
            f"Slot {card['slot']}:\n"
            f"- Color: {card['color']}\n"
            f"- Rarity: {card['rarity']}\n"
            f"- Type: {card['type']}\n"
            f"- Complexity: {card['complexity']}\n"
            f"- Role: {card['notes']}\n"
        )
    lines.append(
        "Output as JSON. Generate all cards. Every slot must be filled."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

COLOR_MAP = {
    "W": "white", "U": "blue", "B": "black", "R": "red", "G": "green",
}

# Keywords that each color should NOT have (hard color pie violations)
COLOR_PIE_VIOLATIONS = {
    "W": ["counter target spell", "direct damage", "deals damage to any target",
           "deals damage to target player"],
    "U": ["destroy target creature", "destroy target permanent",
           "deals damage"],
    "B": ["counter target spell", "destroy target artifact",
           "destroy target enchantment"],
    "R": ["gain life", "gains life", "destroy target enchantment",
           "counter target spell"],
    "G": ["counter target spell", "deals damage to target player",
           "deals damage to any target", "draw a card\n" ],  # unconditional draw
}


def score_card(card: dict, slot: dict) -> dict:
    """Score a single card on the 7-dimension rubric. Returns scores dict."""
    scores = {}
    failure_modes = []
    notes_parts = []

    oracle = card.get("oracle_text", card.get("rules_text", "")) or ""
    name = card.get("name", "")
    mana_cost = card.get("mana_cost", "") or ""
    type_line = card.get("type_line", "") or ""
    flavor = card.get("flavor_text", "") or ""
    rarity = card.get("rarity", "") or ""
    power = card.get("power")
    toughness = card.get("toughness")
    cmc_val = card.get("cmc", 0) or 0
    colors = card.get("colors", []) or []
    color_identity = card.get("color_identity", []) or []

    # --- 1. Rules Text Correctness (1-5) ---
    rtc = 5
    # Check old ETB wording
    if "enters the battlefield" in oracle.lower():
        rtc -= 1
        failure_modes.append("old_etb_wording")
    # Check self-reference (using card name instead of ~)
    if name and len(name) > 3 and name in oracle:
        rtc -= 2
        failure_modes.append("self_reference_uses_name")
    # Check keyword capitalization (keywords should be lowercase)
    keywords_to_check = ["Flying", "First Strike", "Double Strike", "Deathtouch",
                         "Trample", "Vigilance", "Haste", "Lifelink", "Reach",
                         "Menace", "Hexproof", "Flash", "Defender", "Indestructible"]
    # Keywords at start of oracle_text or after \n are OK to be capitalized
    # But mid-sentence capitalization is wrong
    oracle_lines = oracle.split("\n")
    for kw in keywords_to_check:
        # Check if keyword appears capitalized mid-sentence
        for line in oracle_lines:
            line_stripped = line.strip()
            # If the keyword IS the entire line, capitalization is fine
            if line_stripped.lower() == kw.lower():
                continue
            # If keyword starts the line, that's fine
            if line_stripped.startswith(kw):
                continue
            # If it appears mid-line with wrong caps (e.g., "has First Strike")
            if f" {kw}" in line_stripped and kw not in ["Flying", "Trample", "Haste",
                "Lifelink", "Reach", "Menace", "Hexproof", "Flash", "Defender",
                "Indestructible", "Vigilance", "Deathtouch"]:
                # Only flag multi-word keywords that are wrongly capitalized
                pass  # This is tricky — skip for now
    # "First Strike" should be "first strike" in keyword lists
    if "First Strike" in oracle and "first strike" not in oracle:
        # Check if it's on its own line
        for line in oracle_lines:
            if line.strip() == "First Strike":
                rtc -= 0.5
                failure_modes.append("keyword_capitalization")
                break
    if "Double Strike" in oracle and "double strike" not in oracle:
        for line in oracle_lines:
            if line.strip() == "Double Strike":
                rtc -= 0.5
                failure_modes.append("keyword_capitalization")
                break
    # Missing period at end of ability
    for line in oracle_lines:
        line_s = line.strip()
        if not line_s:
            continue
        # Skip pure keyword lines
        if line_s.lower() in [k.lower() for k in keywords_to_check]:
            continue
        # Skip loyalty abilities format check here
        if line_s.startswith("[") or line_s.startswith("I ") or line_s.startswith("II ") or line_s.startswith("III "):
            continue
        if len(line_s) > 10 and not line_s.endswith(".") and not line_s.endswith(")") and not line_s.endswith("—"):
            rtc -= 0.25
            if "missing_period" not in failure_modes:
                failure_modes.append("missing_period")
    # Activated ability missing colon
    # Pattern: mana/tap cost followed by effect without colon
    if "{T}" in oracle and ":" not in oracle and "Creature" in type_line:
        rtc -= 0.5
        failure_modes.append("activated_ability_missing_colon")
    # Clamp
    rtc = max(1, min(5, round(rtc)))
    scores["rules_text_correctness"] = rtc

    # --- 2. Mana Cost Appropriateness (1-5) ---
    mca = 5
    # Parse CMC from mana_cost
    if mana_cost:
        parsed_cmc = 0
        symbols = re.findall(r'\{([^}]+)\}', mana_cost)
        for sym in symbols:
            if sym in ("W", "U", "B", "R", "G", "C"):
                parsed_cmc += 1
            elif sym == "X":
                parsed_cmc += 0
            else:
                try:
                    parsed_cmc += int(sym)
                except ValueError:
                    pass
        # Check cmc field matches
        if cmc_val and abs(parsed_cmc - cmc_val) > 0:
            mca -= 1
            failure_modes.append("cmc_mismatch")
            notes_parts.append(f"CMC field {cmc_val} != parsed {parsed_cmc}")

    # Check P/T vs CMC for creatures
    if power and toughness and "Creature" in type_line:
        try:
            p = int(power)
            t = int(toughness)
            if rarity == "common":
                # P + T should not exceed CMC + 3
                if cmc_val and p + t > cmc_val + 4:
                    mca -= 1
                    failure_modes.append("overstatted_common")
                    notes_parts.append(f"Common {p}/{t} at CMC {cmc_val}")
                # Very understatted
                if cmc_val and cmc_val >= 3 and p + t < cmc_val:
                    mca -= 0.5
                    failure_modes.append("understatted")
        except ValueError:
            pass  # */*, X/X etc are fine

    # Mana cost ordering check
    if mana_cost:
        # Check generic comes before colored
        symbols = re.findall(r'\{([^}]+)\}', mana_cost)
        found_colored = False
        found_generic_after_colored = False
        for sym in symbols:
            if sym in ("W", "U", "B", "R", "G"):
                found_colored = True
            elif sym not in ("X", "C") and found_colored:
                try:
                    int(sym)
                    found_generic_after_colored = True
                except ValueError:
                    pass
        if found_generic_after_colored:
            mca -= 1
            failure_modes.append("mana_cost_ordering")

    mca = max(1, min(5, round(mca)))
    scores["mana_cost_appropriateness"] = mca

    # --- 3. Power Level for Rarity (1-5) ---
    plr = 5
    target_rarity = slot["rarity"]
    card_rarity = rarity

    # Rarity mismatch
    if card_rarity != target_rarity:
        plr -= 1
        failure_modes.append("rarity_mismatch")
        notes_parts.append(f"Asked for {target_rarity}, got {card_rarity}")

    # NWO check for commons
    if target_rarity == "common":
        # Count abilities (rough: count \n in oracle text)
        ability_count = len([l for l in oracle_lines if l.strip() and
                            l.strip().lower() not in [k.lower() for k in keywords_to_check]])
        keyword_count = len([l for l in oracle_lines if l.strip() and
                            l.strip().lower() in [k.lower() for k in keywords_to_check]])
        total_complexity = ability_count + max(0, keyword_count - 1)
        if total_complexity > 2:
            plr -= 1
            failure_modes.append("nwo_violation_common")
            notes_parts.append(f"Common with {ability_count} abilities + {keyword_count} keywords")

    # Mythic should be splashy
    if target_rarity == "mythic":
        if len(oracle) < 30:
            plr -= 1
            failure_modes.append("mythic_too_simple")

    plr = max(1, min(5, round(plr)))
    scores["power_level_for_rarity"] = plr

    # --- 4. Flavor Text Quality (1-5) ---
    ftq = 3  # baseline
    if flavor:
        if len(flavor) > 10:
            ftq = 4
        if len(flavor) > 30 and ("\"" in flavor or "\u2014" in flavor or "—" in flavor):
            ftq = 5  # Has quotes or attribution
        # Generic/bad flavor
        bad_phrases = ["magic is", "the power of", "with great power",
                       "in a world where", "the chosen one"]
        for bp in bad_phrases:
            if bp in flavor.lower():
                ftq -= 1
                failure_modes.append("generic_flavor")
                break
    else:
        # No flavor text
        if slot["complexity"] in ("Vanilla", "Keyword-only", "Single ability"):
            ftq = 2  # Simple cards should have flavor text
            failure_modes.append("missing_flavor_text")
        else:
            ftq = 3  # Complex cards may skip

    ftq = max(1, min(5, round(ftq)))
    scores["flavor_text_quality"] = ftq

    # --- 5. Name Creativity (1-5) ---
    nc = 4  # Start at good
    if name:
        words = name.split()
        if len(words) == 1 and len(name) < 6:
            nc = 3  # Very short/simple
        elif len(words) > 5:
            nc -= 1  # Too long
        # Check for very generic names
        generic_names = ["fire blast", "lightning bolt", "dark ritual",
                        "healing light", "magic sword", "power stone",
                        "forest", "mountain", "island", "swamp", "plains"]
        if name.lower() in generic_names:
            nc = 1
            failure_modes.append("generic_or_existing_name")
    else:
        nc = 1
        failure_modes.append("missing_name")

    nc = max(1, min(5, round(nc)))
    scores["name_creativity"] = nc

    # --- 6. Type Line Correctness (1-5) ---
    tlc = 5
    target_type = slot["type"]
    # Basic checks
    if target_type == "Creature" and "Creature" not in type_line:
        tlc -= 2
        failure_modes.append("wrong_type")
    if target_type == "Instant" and "Instant" not in type_line:
        tlc -= 2
        failure_modes.append("wrong_type")
    if target_type == "Sorcery" and "Sorcery" not in type_line:
        tlc -= 2
        failure_modes.append("wrong_type")
    if target_type == "Enchantment" and "Enchantment" not in type_line:
        tlc -= 2
        failure_modes.append("wrong_type")
    if target_type == "Artifact" and "Artifact" not in type_line:
        tlc -= 2
        failure_modes.append("wrong_type")
    if target_type == "Planeswalker" and "Planeswalker" not in type_line:
        tlc -= 2
        failure_modes.append("wrong_type")
    if target_type == "Land" and "Land" not in type_line:
        tlc -= 2
        failure_modes.append("wrong_type")
    if "Enchantment — Saga" in target_type and "Saga" not in type_line:
        tlc -= 1
        failure_modes.append("missing_saga_subtype")
    if "Basic Land" in target_type and "Basic" not in type_line:
        tlc -= 1
        failure_modes.append("missing_basic_supertype")

    # Creature should have subtypes
    if "Creature" in type_line and "—" not in type_line:
        tlc -= 1
        failure_modes.append("creature_missing_subtypes")

    # Mythic creatures that look legendary should have Legendary
    if slot["rarity"] == "mythic" and "Creature" in type_line:
        if "Legendary" not in type_line:
            tlc -= 0.5
            failure_modes.append("mythic_creature_not_legendary")

    # P/T on non-creatures
    if "Creature" not in type_line and power is not None and power != "null":
        # Check it's actually set (not None/null)
        if isinstance(power, str) and power.lower() != "null" and power != "":
            tlc -= 1
            failure_modes.append("pt_on_noncreature")

    # Missing P/T on creatures
    if "Creature" in type_line and (power is None or toughness is None):
        tlc -= 1
        failure_modes.append("creature_missing_pt")

    tlc = max(1, min(5, round(tlc)))
    scores["type_line_correctness"] = tlc

    # --- 7. Color Pie Compliance (1-5) ---
    cpc = 5
    slot_color = slot["color"]

    if slot_color in COLOR_PIE_VIOLATIONS and oracle:
        for violation_phrase in COLOR_PIE_VIOLATIONS[slot_color]:
            if violation_phrase.lower().strip() in oracle.lower():
                cpc -= 2
                failure_modes.append(f"color_pie_violation_{violation_phrase.strip()}")
                notes_parts.append(f"{slot_color} card has '{violation_phrase.strip()}'")

    # Check colors field matches slot color
    if slot_color not in ("-", "C"):
        expected_colors = list(slot_color)  # "WU" -> ["W", "U"]
        if colors:
            for c in expected_colors:
                if c not in colors:
                    cpc -= 1
                    failure_modes.append("color_mismatch")
                    notes_parts.append(f"Expected color {c} not in colors {colors}")
                    break

    cpc = max(1, min(5, round(cpc)))
    scores["color_pie_compliance"] = cpc

    return {
        "scores": scores,
        "failure_modes": list(set(failure_modes)),
        "notes": "; ".join(notes_parts) if notes_parts else "",
    }


def parse_cards_from_result(result) -> list[dict]:
    """Parse card data from a CachedResult."""
    parsed = result.parse_json()
    if parsed is None:
        # Try raw content
        try:
            parsed = json.loads(result.content)
        except json.JSONDecodeError:
            return []

    if isinstance(parsed, dict):
        # Could be {"cards": [...]} from tool use
        if "cards" in parsed:
            return parsed["cards"]
        else:
            return [parsed]
    elif isinstance(parsed, list):
        return parsed
    return []


# ---------------------------------------------------------------------------
# Main experiment runner
# ---------------------------------------------------------------------------

def run_experiment():
    llm = CachedLLM()
    all_raw_results = []
    all_scores = []

    for temp in TEMPERATURES:
        print(f"\n{'='*60}")
        print(f"Temperature: {temp}")
        print(f"{'='*60}")

        temp_result = {
            "temperature": temp,
            "batches": [],
        }

        for batch_idx, batch_slots in enumerate(BATCHES, 1):
            print(f"  Temp {temp}, Batch {batch_idx}/{len(BATCHES)} (slots {batch_slots})...")

            user_prompt = build_batch_prompt(batch_slots)

            try:
                result = llm.generate(
                    model=MODEL,
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    temperature=temp,
                    tool_schema=CARDS_BATCH_TOOL_SCHEMA,
                    max_tokens=8192,
                )

                cards = parse_cards_from_result(result)
                print(f"    -> Got {len(cards)} cards "
                      f"({'CACHE HIT' if result.cache_hit else f'${result.cost_usd:.4f}'})")

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
                }
                temp_result["batches"].append(batch_data)

                # Score each card
                for i, card in enumerate(cards):
                    slot_num = batch_slots[i] if i < len(batch_slots) else batch_slots[-1]
                    slot = CARD_SLOTS[slot_num - 1]
                    score_result = score_card(card, slot)

                    card_score = {
                        "card_slot": slot_num,
                        "temperature": temp,
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

                # Rate limiting: sleep between non-cached calls
                if not result.cache_hit:
                    time.sleep(1)

            except Exception as e:
                print(f"    ERROR in batch {batch_idx}: {e}")
                temp_result["batches"].append({
                    "batch_num": batch_idx,
                    "slots": batch_slots,
                    "cards": [],
                    "tokens": {"input": 0, "output": 0},
                    "cost_usd": 0,
                    "error": str(e),
                })

        all_raw_results.append(temp_result)

    # ---------------------------------------------------------------------------
    # Save raw results
    # ---------------------------------------------------------------------------
    raw_path = OUTPUT_DIR / "exp1_raw_results.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(all_raw_results, f, indent=2, ensure_ascii=False)
    print(f"\nRaw results saved to {raw_path}")

    # ---------------------------------------------------------------------------
    # Save scores
    # ---------------------------------------------------------------------------
    scores_path = OUTPUT_DIR / "exp1_scores.json"
    with open(scores_path, "w", encoding="utf-8") as f:
        json.dump(all_scores, f, indent=2, ensure_ascii=False)
    print(f"Scores saved to {scores_path}")

    # ---------------------------------------------------------------------------
    # Generate summary
    # ---------------------------------------------------------------------------
    summary = generate_summary(all_raw_results, all_scores)
    summary_path = OUTPUT_DIR / "exp1_summary.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)
    print(f"Summary saved to {summary_path}")

    # ---------------------------------------------------------------------------
    # Print cache stats
    # ---------------------------------------------------------------------------
    stats = llm.stats()
    print(f"\nCache stats: {json.dumps(stats, indent=2)}")


def generate_summary(raw_results: list, all_scores: list) -> str:
    """Generate a markdown summary of the experiment."""
    dimensions = [
        "rules_text_correctness",
        "mana_cost_appropriateness",
        "power_level_for_rarity",
        "flavor_text_quality",
        "name_creativity",
        "type_line_correctness",
        "color_pie_compliance",
    ]

    lines = ["# Experiment 1: Temperature Sweep — Summary\n"]
    lines.append(f"**Model**: {MODEL}\n")
    lines.append(f"**Temperatures tested**: {TEMPERATURES}\n")
    lines.append(f"**Cards per temperature**: 24\n")
    lines.append(f"**Total cards scored**: {len(all_scores)}\n")

    # Cost summary
    total_cost = 0
    for tr in raw_results:
        for b in tr["batches"]:
            total_cost += b.get("cost_usd", 0)
    lines.append(f"**Total API cost**: ${total_cost:.4f}\n")

    lines.append("\n---\n")

    # Average scores per temperature
    lines.append("## Average Scores by Temperature\n")
    lines.append("| Dimension | T=0.3 | T=0.5 | T=0.7 | T=1.0 |")
    lines.append("|-----------|-------|-------|-------|-------|")

    temp_dim_averages = {}
    for temp in TEMPERATURES:
        temp_scores = [s for s in all_scores if s["temperature"] == temp]
        temp_dim_averages[temp] = {}
        for dim in dimensions:
            vals = [s["scores"][dim] for s in temp_scores if dim in s["scores"]]
            avg = sum(vals) / len(vals) if vals else 0
            temp_dim_averages[temp][dim] = avg

    for dim in dimensions:
        dim_label = dim.replace("_", " ").title()
        row = f"| {dim_label} |"
        for temp in TEMPERATURES:
            row += f" {temp_dim_averages[temp][dim]:.2f} |"
        lines.append(row)

    # Overall average row
    row = "| **Overall Average** |"
    temp_overall = {}
    for temp in TEMPERATURES:
        vals = list(temp_dim_averages[temp].values())
        avg = sum(vals) / len(vals) if vals else 0
        temp_overall[temp] = avg
        row += f" **{avg:.2f}** |"
    lines.append(row)

    lines.append("")

    # Best temperature
    best_temp = max(temp_overall, key=temp_overall.get)
    lines.append(f"\n## Best Overall Temperature: **{best_temp}** (avg: {temp_overall[best_temp]:.2f})\n")

    # Correctness vs Creativity breakdown
    lines.append("## Correctness vs. Creativity\n")
    correctness_dims = ["rules_text_correctness", "mana_cost_appropriateness",
                        "type_line_correctness", "color_pie_compliance"]
    creativity_dims = ["flavor_text_quality", "name_creativity"]

    lines.append("| Metric | T=0.3 | T=0.5 | T=0.7 | T=1.0 |")
    lines.append("|--------|-------|-------|-------|-------|")

    for label, dims in [("Correctness (avg)", correctness_dims),
                        ("Creativity (avg)", creativity_dims),
                        ("Power Level", ["power_level_for_rarity"])]:
        row = f"| {label} |"
        for temp in TEMPERATURES:
            vals = [temp_dim_averages[temp][d] for d in dims]
            avg = sum(vals) / len(vals) if vals else 0
            row += f" {avg:.2f} |"
        lines.append(row)

    lines.append("")

    # Failure modes per temperature
    lines.append("## Failure Modes by Temperature\n")
    for temp in TEMPERATURES:
        temp_scores = [s for s in all_scores if s["temperature"] == temp]
        all_failures = {}
        for s in temp_scores:
            for fm in s.get("failure_modes", []):
                all_failures[fm] = all_failures.get(fm, 0) + 1
        if all_failures:
            sorted_failures = sorted(all_failures.items(), key=lambda x: -x[1])
            lines.append(f"### Temperature {temp}")
            for fm, count in sorted_failures:
                lines.append(f"- **{fm}**: {count} occurrences")
            lines.append("")

    # Per-card details table
    lines.append("## Per-Card Scores (All Temperatures)\n")
    lines.append("| Slot | Temp | Name | RTC | MCA | PLR | FTQ | NC | TLC | CPC | Avg | Failures |")
    lines.append("|------|------|------|-----|-----|-----|-----|-----|-----|-----|-----|----------|")

    for temp in TEMPERATURES:
        temp_scores = sorted([s for s in all_scores if s["temperature"] == temp],
                           key=lambda x: x["card_slot"])
        for s in temp_scores:
            sc = s["scores"]
            avg = sum(sc.values()) / len(sc)
            fails = ", ".join(s.get("failure_modes", [])[:3])
            name = s.get("card_name", "?")
            if len(name) > 25:
                name = name[:22] + "..."
            lines.append(
                f"| {s['card_slot']:2d} | {temp} | {name} | "
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

    # Find best for correctness and creativity separately
    best_correct_temp = max(TEMPERATURES,
        key=lambda t: sum(temp_dim_averages[t][d] for d in correctness_dims) / len(correctness_dims))
    best_creative_temp = max(TEMPERATURES,
        key=lambda t: sum(temp_dim_averages[t][d] for d in creativity_dims) / len(creativity_dims))

    lines.append(f"- **Best temperature for correctness**: {best_correct_temp} "
                f"(avg correctness: {sum(temp_dim_averages[best_correct_temp][d] for d in correctness_dims)/len(correctness_dims):.2f})")
    lines.append(f"- **Best temperature for creativity**: {best_creative_temp} "
                f"(avg creativity: {sum(temp_dim_averages[best_creative_temp][d] for d in creativity_dims)/len(creativity_dims):.2f})")
    lines.append(f"- **Best overall temperature**: {best_temp} "
                f"(overall avg: {temp_overall[best_temp]:.2f})")
    lines.append("")
    lines.append(f"**Recommended temperature for Phase 1C**: **{best_temp}**\n")
    lines.append(
        "This temperature provides the best balance between rules text correctness "
        "and creative quality across all 7 scoring dimensions."
    )
    lines.append(f"\n**Total API cost for this experiment**: ${total_cost:.4f}")

    return "\n".join(lines)


if __name__ == "__main__":
    run_experiment()
