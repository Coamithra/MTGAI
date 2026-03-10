"""Phase 1B-7: Mechanic Validation Spike.

Generate 5 test cards per custom mechanic (15 total) to verify the LLM
can use novel keywords correctly. Score quality using Phase 0E criteria.

Run from project root:
    python research/scripts/mechanic_validation_spike.py
"""

import contextlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# Add research/scripts to path for cached_llm import
sys.path.insert(0, "research/scripts")
from cached_llm import CachedLLM

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-20250514"
TEMPERATURE = 1.0
MAX_TOKENS = 8192

OUTPUT_DIR = Path("output/sets/ASD/mechanics")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TEST_CARDS_PATH = OUTPUT_DIR / "test-cards.json"
RESULTS_PATH = OUTPUT_DIR / "validation-spike-results.md"

# ---------------------------------------------------------------------------
# System prompt — base from system-prompt-v1.md + custom mechanic definitions
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
- Include reminder text for custom set mechanics on their first use in oracle_text.

## Constraints

- DO NOT use silver-border or un-set mechanics (no dice rolling, no subgames, no breaking the fourth wall).
- DO NOT reference real-world people, places, brands, or events.
- DO NOT reuse existing MTG card names. All names must be original.
- DO NOT use the card's actual name in oracle_text — always use ~ as self-reference.
- DO NOT create cards that are strictly better than iconic staples at the same rarity and cost.

## Custom Set Mechanics — Anomalous Descent (ASD)

This set has three custom mechanics. Use them exactly as described below.

### 1. Scavenge X (keyword ability) — Colors: W, U, G — Complexity: 1

**Reminder text**: "(Look at the top X cards of your library. You may put an artifact card from among them into your hand. Put the rest on the bottom of your library in any order.)"

**X scaling by rarity**:
- Common: X = 2-3
- Uncommon: X = 4-5
- Rare/Mythic: X = 6+

**Usage patterns**:
- Common: "When ~ enters, scavenge 2." or "When ~ dies, scavenge 3." — simple ETB/death triggers
- Uncommon: "Scavenge 4" with a bonus effect, or payoff creatures that care about artifacts found
- Rare: "Scavenge 6+", repeatable scavenge via activated abilities, or "whenever you scavenge" triggers

**Oracle text format**: Write it as "scavenge N" (lowercase) in the rules text. Include the reminder text in parentheses after the first use on the card.

### 2. Malfunction N (keyword ability) — Colors: W, U, R — Complexity: 2

**Reminder text**: "(This permanent enters tapped with N malfunction counters on it. At the beginning of your upkeep, remove a malfunction counter from it.)"

**N scaling by rarity**:
- Common: N = 1
- Uncommon: N = 2
- Rare/Mythic: N = 2-3

**Usage patterns**:
- Common: "Malfunction 1" on creatures/artifacts with above-rate stats or effects. The delay IS the downside.
- Uncommon: "Malfunction 2" with "when the last malfunction counter is removed from ~" or "~ has [ability] as long as it has no malfunction counters" triggers
- Rare: "Malfunction 3" with powerful effects, counter manipulation, or ways to remove counters faster

**Oracle text format**: Write it as "malfunction N" (lowercase) in the rules text, typically as the first ability. Include reminder text in parentheses after first use.

### 3. Overclock (keyword action) — Colors: U, R, B — Complexity: 3

**Reminder text**: "(Exile the top three cards of your library. You may play them until end of turn.)"

**NOT available at common.** Primarily rare+.

**Usage patterns**:
- Uncommon: "As an additional cost to cast this spell, overclock." on spells, or "if you overclocked this turn" conditional bonuses
- Rare: Repeatable overclock via activated abilities, "whenever you overclock" triggers, or cards that reduce the risk of overclock
- Mythic: Powerful overclock payoffs, build-around effects

**Oracle text format**: Write "overclock" (lowercase) as a keyword action. Include reminder text in parentheses after first use. When used as an additional cost: "As an additional cost to cast ~, overclock."

## Set Theme — Anomalous Descent

Science-fantasy megadungeon set in far-future post-apocalyptic Earth. The city of Denethix clings to order at the edge of a wilderness teeming with dinosaurs, moktars, and rogue wizards. Beneath Mount Rendon lies the Anomalous Subsurface Environment — a self-spawning megadungeon filled with ancient super-science relics, degraded automatons, and things far worse.

Key flavor elements:
- Ancient technology misunderstood as magic
- Automatons, constructs, and protonium-metal artifacts
- Dungeon explorers seeking fortune in the ASE
- Deadpan, darkly humorous flavor text (the world takes itself seriously; the absurdity speaks for itself)
- Faction groups: Cult of Science, Unyielding Fist, Society of the Luminous Spark, moktars
- Creature types: Human, Automaton, Construct, Moktar, Wizard, Soldier, Scientist, Dinosaur
"""

# ---------------------------------------------------------------------------
# User prompts for each mechanic batch
# ---------------------------------------------------------------------------

BATCH_PROMPTS = {
    "scavenge": (
        "Generate 5 cards that use the Scavenge X mechanic for the Anomalous Descent set. "
        "Include:\n"
        "- 2 commons (one white creature and one green creature, Scavenge 2-3)\n"
        "- 2 uncommons (one blue and one green, Scavenge 4-5, with artifact-matters synergy)\n"
        "- 1 rare (any Scavenge color, Scavenge 6+, with a powerful or repeatable scavenge effect)\n\n"
        "Each card should use Scavenge correctly with reminder text on the first occurrence. "
        "Set theme: science-fantasy megadungeon with artifact subtheme. "
        "Include darkly humorous or deadpan flavor text that fits the Anomalous Descent setting. "
        "Use ~ for self-reference in oracle text. "
        "Include the keywords array with 'Scavenge' listed."
    ),
    "malfunction": (
        "Generate 5 cards that use the Malfunction N mechanic for the Anomalous Descent set. "
        "Include:\n"
        "- 2 commons (one white artifact creature with Malfunction 1, one red artifact creature "
        "with Malfunction 1 — both should have above-rate stats for their cost)\n"
        "- 2 uncommons (one blue artifact and one red creature, both Malfunction 2, "
        "with triggered abilities that trigger when the last malfunction counter is removed)\n"
        "- 1 rare (any Malfunction color, Malfunction 3, with a powerful payoff effect "
        "and/or counter manipulation)\n\n"
        "Each card should include reminder text on the first use of Malfunction. "
        "Malfunction should be the first ability listed in oracle text. "
        "Set theme: degraded automatons and ancient technology that needs rebooting. "
        "Include deadpan, darkly humorous flavor text. "
        "Use ~ for self-reference in oracle text. "
        "Include the keywords array with 'Malfunction' listed."
    ),
    "overclock": (
        "Generate 5 cards that use the Overclock mechanic for the Anomalous Descent set. "
        "Include:\n"
        "- 2 uncommons (one blue instant/sorcery and one red creature, both using overclock "
        "as an additional cost or with 'if you overclocked this turn' bonuses)\n"
        "- 2 rares (one black creature and one red sorcery, with repeatable overclock "
        "via activated abilities or 'whenever you overclock' triggers)\n"
        "- 1 mythic (blue or red legendary creature — a showcase card for the overclock mechanic "
        "with a splashy, powerful overclock payoff)\n\n"
        "Remember: Overclock should NOT appear at common. "
        "Each card should include reminder text on the first use of overclock. "
        "Overclock exiles the TOP THREE cards of your library — this is the risk/reward. "
        "Set theme: Cult of Science pushing ancient tech past its limits, mad experiments. "
        "Include darkly humorous flavor text. "
        "Use ~ for self-reference in oracle text. "
        "Include the keywords array with 'Overclock' listed."
    ),
}

# ---------------------------------------------------------------------------
# Tool schema — batch of cards with keywords field
# ---------------------------------------------------------------------------

CARD_TOOL_SCHEMA = {
    "name": "generate_cards",
    "description": "Generate a batch of MTG cards",
    "input_schema": {
        "type": "object",
        "required": ["cards"],
        "properties": {
            "cards": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "name",
                        "mana_cost",
                        "type_line",
                        "oracle_text",
                        "rarity",
                        "colors",
                        "cmc",
                    ],
                    "properties": {
                        "name": {"type": "string"},
                        "mana_cost": {
                            "type": "string",
                            "description": "e.g. {2}{W}{U}",
                        },
                        "cmc": {"type": "number"},
                        "colors": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["W", "U", "B", "R", "G"],
                            },
                        },
                        "color_identity": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["W", "U", "B", "R", "G"],
                            },
                        },
                        "type_line": {"type": "string"},
                        "oracle_text": {"type": "string"},
                        "flavor_text": {"type": "string"},
                        "power": {"type": "string"},
                        "toughness": {"type": "string"},
                        "rarity": {
                            "type": "string",
                            "enum": ["common", "uncommon", "rare", "mythic"],
                        },
                        "keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "design_notes": {"type": "string"},
                    },
                },
            }
        },
    },
}


# ---------------------------------------------------------------------------
# Mechanic-specific scoring
# ---------------------------------------------------------------------------


def score_mechanic_usage(card: dict, mechanic: str) -> dict[str, float | list[str]]:
    """Score a card on 4 dimensions (1-5 each) for mechanic validation.

    Returns dict with:
        - rules_text: correctness of mechanic syntax and Oracle text
        - flavor_fit: how well it fits the science-fantasy megadungeon theme
        - balance: P/T for CMC, effect appropriateness for rarity
        - creativity: interesting design, not just filler
        - overall: average of above
        - issues: list of specific issues found
    """
    oracle = card.get("oracle_text", "") or ""
    name = card.get("name", "") or ""
    mana_cost = card.get("mana_cost", "") or ""
    type_line = card.get("type_line", "") or ""
    flavor = card.get("flavor_text", "") or ""
    rarity = card.get("rarity", "") or ""
    power = card.get("power")
    toughness = card.get("toughness")
    cmc_val = card.get("cmc", 0) or 0
    issues: list[str] = []

    # ---- 1. Rules Text Correctness (1-5) ----
    rtc = 5.0

    # Check self-reference: uses card name instead of ~
    if name and len(name) > 3 and name in oracle:
        rtc -= 2.0
        issues.append(f"Uses card name '{name}' instead of ~ in oracle text")

    # Check old ETB wording
    if "enters the battlefield" in oracle.lower():
        rtc -= 1.0
        issues.append("Uses old 'enters the battlefield' wording instead of 'enters'")

    # Check mana cost ordering
    if mana_cost:
        symbols = re.findall(r"\{([^}]+)\}", mana_cost)
        found_colored = False
        for sym in symbols:
            if sym in ("W", "U", "B", "R", "G"):
                found_colored = True
            elif sym not in ("X", "C") and found_colored:
                try:
                    int(sym)
                    rtc -= 1.0
                    issues.append(f"Mana cost ordering wrong: {mana_cost}")
                    break
                except ValueError:
                    pass

    # Check CMC matches mana_cost
    if mana_cost:
        parsed_cmc = 0
        for sym in re.findall(r"\{([^}]+)\}", mana_cost):
            if sym in ("W", "U", "B", "R", "G", "C"):
                parsed_cmc += 1
            elif sym == "X":
                pass
            else:
                with contextlib.suppress(ValueError):
                    parsed_cmc += int(sym)
        if cmc_val and abs(parsed_cmc - cmc_val) > 0:
            rtc -= 0.5
            issues.append(f"CMC mismatch: field={cmc_val}, parsed={parsed_cmc}")

    # Mechanic-specific syntax checks
    oracle_lower = oracle.lower()

    if mechanic == "scavenge":
        # Must contain "scavenge N" where N is a digit
        scav_match = re.search(r"scavenge\s+(\d+)", oracle_lower)
        if not scav_match:
            rtc -= 2.0
            issues.append("Missing 'scavenge N' in oracle text")
        else:
            scav_n = int(scav_match.group(1))
            # Check X scaling for rarity
            if rarity == "common" and scav_n > 3:
                rtc -= 0.5
                issues.append(f"Common with scavenge {scav_n} (expected 2-3)")
            elif rarity == "uncommon" and (scav_n < 4 or scav_n > 5):
                rtc -= 0.5
                issues.append(f"Uncommon with scavenge {scav_n} (expected 4-5)")
            elif rarity in ("rare", "mythic") and scav_n < 6:
                rtc -= 0.5
                issues.append(f"Rare/mythic with scavenge {scav_n} (expected 6+)")

        # Check reminder text present
        if "look at the top" not in oracle_lower or "artifact card" not in oracle_lower:
            rtc -= 0.5
            issues.append("Missing or incorrect scavenge reminder text")

    elif mechanic == "malfunction":
        # Must contain "malfunction N"
        malf_match = re.search(r"malfunction\s+(\d+)", oracle_lower)
        if not malf_match:
            rtc -= 2.0
            issues.append("Missing 'malfunction N' in oracle text")
        else:
            malf_n = int(malf_match.group(1))
            if rarity == "common" and malf_n != 1:
                rtc -= 0.5
                issues.append(f"Common with malfunction {malf_n} (expected 1)")
            elif rarity == "uncommon" and malf_n != 2:
                rtc -= 0.5
                issues.append(f"Uncommon with malfunction {malf_n} (expected 2)")
            elif rarity in ("rare", "mythic") and malf_n < 2:
                rtc -= 0.5
                issues.append(f"Rare/mythic with malfunction {malf_n} (expected 2-3)")

        # Check reminder text
        if "malfunction counter" not in oracle_lower or "enters tapped" not in oracle_lower:
            rtc -= 0.5
            issues.append("Missing or incorrect malfunction reminder text")

        # Malfunction should be first ability
        first_line = oracle.split("\n")[0].strip().lower() if oracle else ""
        if "malfunction" not in first_line:
            rtc -= 0.25
            issues.append("Malfunction is not the first ability listed")

    elif mechanic == "overclock":
        # Must contain "overclock"
        if "overclock" not in oracle_lower:
            rtc -= 2.0
            issues.append("Missing 'overclock' in oracle text")

        # Should NOT be at common
        if rarity == "common":
            rtc -= 1.0
            issues.append("Overclock at common (should be uncommon+)")

        # Check reminder text
        if "exile the top three" not in oracle_lower:
            rtc -= 0.5
            issues.append("Missing or incorrect overclock reminder text")

    # Missing period at end of abilities
    oracle_lines = oracle.split("\n")
    evergreen_kw = [
        "flying",
        "first strike",
        "double strike",
        "deathtouch",
        "trample",
        "vigilance",
        "haste",
        "lifelink",
        "reach",
        "menace",
        "hexproof",
        "flash",
        "defender",
        "indestructible",
    ]
    for line in oracle_lines:
        ls = line.strip()
        if not ls:
            continue
        if ls.lower() in evergreen_kw:
            continue
        # Skip pure mechanic keyword lines
        if re.match(r"^(scavenge|malfunction|overclock)\s*\d*$", ls, re.IGNORECASE):
            continue
        if (
            len(ls) > 10
            and not ls.endswith(".")
            and not ls.endswith(")")
            and not ls.endswith('"')
            and not ls.endswith("\u2014")
        ):
            rtc -= 0.25
            if "missing_period" not in [i.split(":")[0] for i in issues]:
                issues.append("Missing period at end of ability text")

    rtc = max(1.0, min(5.0, rtc))

    # ---- 2. Flavor Fit (1-5) ----
    ff = 3.0

    # Check flavor text exists and fits theme
    if flavor:
        if len(flavor) > 15:
            ff += 0.5
        # Theme keywords that suggest good fit
        theme_words = [
            "dungeon",
            "automaton",
            "construct",
            "ancient",
            "protonium",
            "denethrix",
            "denethix",
            "subsurface",
            "moktar",
            "relic",
            "machine",
            "robot",
            "scientist",
            "cult",
            "science",
            "fist",
            "level",
            "descent",
            "expedition",
            "explore",
            "salvage",
            "scrap",
            "malfunction",
            "overclock",
            "technology",
            "tech",
            "laboratory",
            "lab",
            "experiment",
            "ruins",
            "artifact",
            "device",
            "mechanism",
            "broken",
            "degraded",
            "abandoned",
        ]
        flavor_lower = flavor.lower()
        theme_hits = sum(1 for w in theme_words if w in flavor_lower)
        if theme_hits >= 2:
            ff += 1.0
        elif theme_hits >= 1:
            ff += 0.5

        # Darkly humorous / deadpan tone check (quotes, em dashes, dry observations)
        if '"' in flavor or "\u2014" in flavor or "—" in flavor:
            ff += 0.5

        # Generic bad flavor
        bad_phrases = [
            "magic is",
            "the power of",
            "with great power",
            "in a world where",
            "the chosen one",
        ]
        for bp in bad_phrases:
            if bp in flavor_lower:
                ff -= 1.0
                issues.append("Generic flavor text")
                break
    else:
        ff -= 0.5
        issues.append("Missing flavor text")

    # Check card name fits theme
    name_lower = name.lower()
    name_theme_words = [
        "automaton",
        "construct",
        "relic",
        "dungeon",
        "salvage",
        "scrap",
        "ancient",
        "subsurface",
        "moktar",
        "denethix",
        "protonium",
        "scientist",
        "fist",
        "overclock",
        "malfunction",
        "descent",
        "expedition",
        "explorer",
        "delver",
        "tech",
        "machine",
        "robot",
        "mechanism",
        "reboot",
        "boot",
        "surge",
        "calibrat",
        "scaveng",
        "forag",
    ]
    if any(w in name_lower for w in name_theme_words):
        ff += 0.5

    # Check type line for setting creature types
    setting_types = [
        "Automaton",
        "Construct",
        "Moktar",
        "Scientist",
        "Morlock",
        "Dinosaur",
    ]
    if any(t in type_line for t in setting_types):
        ff += 0.5

    ff = max(1.0, min(5.0, ff))

    # ---- 3. Balance (1-5) ----
    bal = 5.0

    if power and toughness and "Creature" in type_line:
        try:
            p = int(power)
            t = int(toughness)
            if rarity == "common":
                # P + T should not exceed CMC + 3 (allow +4 for malfunction downside)
                limit = cmc_val + 3
                if mechanic == "malfunction":
                    limit = cmc_val + 4  # Malfunction is a real downside
                if cmc_val and p + t > limit + 1:
                    bal -= 1.0
                    issues.append(f"Overstatted: {p}/{t} at CMC {cmc_val} ({rarity})")
                # Very understatted
                if cmc_val and cmc_val >= 3 and p + t < cmc_val - 1:
                    bal -= 0.5
                    issues.append(f"Understatted: {p}/{t} at CMC {cmc_val}")
            elif rarity == "uncommon":
                if cmc_val and p + t > cmc_val + 5:
                    bal -= 1.0
                    issues.append(f"Overstatted uncommon: {p}/{t} at CMC {cmc_val}")
            elif rarity in ("rare", "mythic"):
                if cmc_val and p + t > cmc_val + 6:
                    bal -= 0.5
                    issues.append(f"Possibly overstatted rare: {p}/{t} at CMC {cmc_val}")
        except ValueError:
            pass  # */*, X/X are fine

    # Check effect matches rarity complexity
    ability_count = len([ln for ln in oracle_lines if ln.strip() and len(ln.strip()) > 5])
    if rarity == "common" and ability_count > 3:
        bal -= 0.5
        issues.append(f"Common with {ability_count} abilities (too complex)")
    if rarity == "mythic" and ability_count < 2 and len(oracle) < 40:
        bal -= 0.5
        issues.append("Mythic seems too simple")

    bal = max(1.0, min(5.0, bal))

    # ---- 4. Creativity (1-5) ----
    cre = 3.5  # Baseline

    # Longer design notes suggest more thought
    design_notes = card.get("design_notes", "") or ""
    if len(design_notes) > 50:
        cre += 0.5
    if len(design_notes) > 100:
        cre += 0.25

    # Card name length/quality
    name_words = name.split()
    if 2 <= len(name_words) <= 4:
        cre += 0.25  # Good name length
    if len(name_words) == 1 and len(name) < 5:
        cre -= 0.5

    # Does the card do something interesting with the mechanic beyond bare minimum?
    if mechanic == "scavenge":
        # Bonus for combining scavenge with other effects
        if "whenever" in oracle_lower and "scavenge" in oracle_lower:
            cre += 0.5
        if "artifact" in oracle_lower and "scavenge" in oracle_lower:
            cre += 0.25
    elif mechanic == "malfunction":
        # Bonus for counter manipulation / interesting triggers
        if "remove" in oracle_lower and "malfunction counter" in oracle_lower:
            cre += 0.25
        if "no malfunction counters" in oracle_lower or "last malfunction counter" in oracle_lower:
            cre += 0.5
    elif mechanic == "overclock":
        # Bonus for interesting overclock synergies
        if "whenever you overclock" in oracle_lower:
            cre += 0.5
        if "overclocked this turn" in oracle_lower:
            cre += 0.25

    cre = max(1.0, min(5.0, cre))

    # ---- Overall ----
    overall = (rtc + ff + bal + cre) / 4.0

    return {
        "rules_text": round(rtc, 1),
        "flavor_fit": round(ff, 1),
        "balance": round(bal, 1),
        "creativity": round(cre, 1),
        "overall": round(overall, 2),
        "issues": issues,
    }


def parse_cards_from_result(result) -> list[dict]:
    """Parse card data from a CachedResult."""
    parsed = result.parse_json()
    if parsed is None:
        try:
            parsed = json.loads(result.content)
        except json.JSONDecodeError:
            return []

    if isinstance(parsed, dict):
        if "cards" in parsed:
            return parsed["cards"]
        else:
            return [parsed]
    elif isinstance(parsed, list):
        return parsed
    return []


def print_card(card: dict, index: int) -> None:
    """Print a formatted card."""
    print(f"  [{index + 1}] {card.get('name', 'UNNAMED')}  {card.get('mana_cost', '')}")
    print(f"      {card.get('type_line', '')}")
    oracle = card.get("oracle_text", "")
    for line in oracle.split("\n"):
        print(f"      {line}")
    p = card.get("power")
    t = card.get("toughness")
    if p and t:
        print(f"      {p}/{t}")
    flavor = card.get("flavor_text")
    if flavor:
        print(f'      "{flavor}"')
    print(f"      [{card.get('rarity', '?')}]")
    notes = card.get("design_notes", "")
    if notes:
        print(f"      Design: {notes[:100]}{'...' if len(notes) > 100 else ''}")


def print_separator(char: str = "=", width: int = 80) -> None:
    print(char * width)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print_separator()
    print("PHASE 1B-7: Mechanic Validation Spike")
    print("Generating 15 test cards (5 per mechanic) for Anomalous Descent")
    print_separator()
    print()

    llm = CachedLLM()
    all_cards: list[dict] = []  # Each entry: {mechanic, card, scores}
    total_cost = 0.0

    for mechanic, prompt in BATCH_PROMPTS.items():
        print_separator("-")
        print(f"  BATCH: {mechanic.upper()}")
        print_separator("-")
        print(f"  Generating 5 {mechanic} cards...")

        result = llm.generate(
            model=MODEL,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=TEMPERATURE,
            tool_schema=CARD_TOOL_SCHEMA,
            max_tokens=MAX_TOKENS,
        )

        cost_str = "CACHE HIT" if result.cache_hit else f"${result.cost_usd:.4f}"
        if not result.cache_hit:
            total_cost += result.cost_usd
        print(f"  API call: {cost_str} | {result.input_tokens} in / {result.output_tokens} out")

        cards = parse_cards_from_result(result)
        print(f"  Parsed {len(cards)} cards\n")

        for i, card in enumerate(cards):
            print_card(card, i)
            scores = score_mechanic_usage(card, mechanic)

            print(
                f"      Scores: rules={scores['rules_text']:.1f} "
                f"flavor={scores['flavor_fit']:.1f} "
                f"balance={scores['balance']:.1f} "
                f"creativity={scores['creativity']:.1f} "
                f"=> overall={scores['overall']:.2f}"
            )
            if scores["issues"]:
                for issue in scores["issues"]:
                    print(f"        ! {issue}")
            print()

            all_cards.append({"mechanic": mechanic, "card": card, "scores": scores})

        # Pause between batches to avoid rate limits
        if not result.cache_hit:
            time.sleep(2)

    # ---------------------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------------------
    print()
    print_separator()
    print("SUMMARY")
    print_separator()

    # Per-mechanic averages
    mechanic_stats: dict[str, dict] = {}
    for mech_name in BATCH_PROMPTS:
        mech_cards = [c for c in all_cards if c["mechanic"] == mech_name]
        if not mech_cards:
            continue
        n = len(mech_cards)
        avg_rules = sum(c["scores"]["rules_text"] for c in mech_cards) / n
        avg_flavor = sum(c["scores"]["flavor_fit"] for c in mech_cards) / n
        avg_balance = sum(c["scores"]["balance"] for c in mech_cards) / n
        avg_creativity = sum(c["scores"]["creativity"] for c in mech_cards) / n
        avg_overall = sum(c["scores"]["overall"] for c in mech_cards) / n
        total_issues = sum(len(c["scores"]["issues"]) for c in mech_cards)

        mechanic_stats[mech_name] = {
            "count": n,
            "avg_rules": round(avg_rules, 2),
            "avg_flavor": round(avg_flavor, 2),
            "avg_balance": round(avg_balance, 2),
            "avg_creativity": round(avg_creativity, 2),
            "avg_overall": round(avg_overall, 2),
            "total_issues": total_issues,
        }

        print(f"\n  {mech_name.upper()} ({n} cards)")
        print(f"    Rules text:  {avg_rules:.2f}")
        print(f"    Flavor fit:  {avg_flavor:.2f}")
        print(f"    Balance:     {avg_balance:.2f}")
        print(f"    Creativity:  {avg_creativity:.2f}")
        print(f"    Overall:     {avg_overall:.2f}")
        print(f"    Issues:      {total_issues}")

    # Overall averages
    total_n = len(all_cards)
    if total_n > 0:
        grand_rules = sum(c["scores"]["rules_text"] for c in all_cards) / total_n
        grand_flavor = sum(c["scores"]["flavor_fit"] for c in all_cards) / total_n
        grand_balance = sum(c["scores"]["balance"] for c in all_cards) / total_n
        grand_creativity = sum(c["scores"]["creativity"] for c in all_cards) / total_n
        grand_overall = sum(c["scores"]["overall"] for c in all_cards) / total_n
    else:
        grand_rules = grand_flavor = grand_balance = grand_creativity = grand_overall = 0.0

    print(f"\n  GRAND TOTALS ({total_n} cards)")
    print(f"    Rules text:  {grand_rules:.2f}")
    print(f"    Flavor fit:  {grand_flavor:.2f}")
    print(f"    Balance:     {grand_balance:.2f}")
    print(f"    Creativity:  {grand_creativity:.2f}")
    print(f"    Overall:     {grand_overall:.2f}")
    print(f"    Total cost:  ${total_cost:.4f}")

    # GO/NO-GO assessment
    print()
    print_separator()
    print("GO/NO-GO ASSESSMENT (Phase 0E criteria)")
    print_separator()

    rules_pass = grand_rules >= 4.0
    overall_pass = grand_overall >= 3.5
    print(f"  Rules text avg: {grand_rules:.2f} (need >= 4.0) — {'PASS' if rules_pass else 'FAIL'}")
    print(
        f"  Overall avg:    {grand_overall:.2f} (need >= 3.5) — "
        f"{'PASS' if overall_pass else 'FAIL'}"
    )

    # Per-mechanic GO/NO-GO
    flagged_mechanics = []
    for mech_name, stats in mechanic_stats.items():
        mech_rules_pass = stats["avg_rules"] >= 4.0
        mech_overall_pass = stats["avg_overall"] >= 3.5
        status = "GO" if (mech_rules_pass and mech_overall_pass) else "NEEDS ITERATION"
        print(
            f"  {mech_name}: rules={stats['avg_rules']:.2f}, "
            f"overall={stats['avg_overall']:.2f} — {status}"
        )
        if not (mech_rules_pass and mech_overall_pass):
            flagged_mechanics.append(mech_name)

    verdict = "GO" if (rules_pass and overall_pass and not flagged_mechanics) else "NEEDS ITERATION"
    print(f"\n  VERDICT: {verdict}")
    if flagged_mechanics:
        print(f"  Flagged for iteration: {', '.join(flagged_mechanics)}")
    print_separator()

    # ---------------------------------------------------------------------------
    # Save test cards JSON
    # ---------------------------------------------------------------------------
    save_cards = []
    for entry in all_cards:
        card_data = dict(entry["card"])
        card_data["_mechanic"] = entry["mechanic"]
        card_data["_scores"] = entry["scores"]
        save_cards.append(card_data)

    TEST_CARDS_PATH.write_text(json.dumps(save_cards, indent=2, ensure_ascii=False))
    print(f"\nSaved {len(save_cards)} test cards to {TEST_CARDS_PATH}")

    # ---------------------------------------------------------------------------
    # Save results markdown
    # ---------------------------------------------------------------------------
    md_lines = [
        "# Mechanic Validation Spike Results",
        "",
        f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Model**: {MODEL}",
        f"**Temperature**: {TEMPERATURE}",
        f"**Cards generated**: {total_n}",
        f"**Total cost**: ${total_cost:.4f}",
        "",
        "## Per-Mechanic Results",
        "",
        "| Mechanic | Cards | Rules Text | Flavor Fit | Balance | Creativity | Overall | Issues |",
        "|----------|-------|-----------|------------|---------|------------|---------|--------|",
    ]

    for mech_name, stats in mechanic_stats.items():
        md_lines.append(
            f"| {mech_name} | {stats['count']} | {stats['avg_rules']:.2f} | "
            f"{stats['avg_flavor']:.2f} | {stats['avg_balance']:.2f} | "
            f"{stats['avg_creativity']:.2f} | {stats['avg_overall']:.2f} | "
            f"{stats['total_issues']} |"
        )

    md_lines.extend(
        [
            "",
            f"| **Overall** | **{total_n}** | **{grand_rules:.2f}** | "
            f"**{grand_flavor:.2f}** | **{grand_balance:.2f}** | "
            f"**{grand_creativity:.2f}** | **{grand_overall:.2f}** | "
            f"**{sum(s['total_issues'] for s in mechanic_stats.values())}** |",
            "",
            "## Card Details",
            "",
        ]
    )

    for mech_name in BATCH_PROMPTS:
        md_lines.append(f"### {mech_name.title()}")
        md_lines.append("")
        mech_cards = [c for c in all_cards if c["mechanic"] == mech_name]
        for entry in mech_cards:
            card = entry["card"]
            scores = entry["scores"]
            md_lines.append(f"**{card.get('name', 'UNNAMED')}** {card.get('mana_cost', '')}")
            md_lines.append(f"- Type: {card.get('type_line', '')}")
            md_lines.append(f"- Rarity: {card.get('rarity', '')}")
            oracle_escaped = card.get("oracle_text", "").replace("\n", " / ")
            md_lines.append(f"- Oracle: {oracle_escaped}")
            if card.get("power") and card.get("toughness"):
                md_lines.append(f"- P/T: {card['power']}/{card['toughness']}")
            if card.get("flavor_text"):
                md_lines.append(f'- Flavor: "{card["flavor_text"]}"')
            md_lines.append(
                f"- Scores: rules={scores['rules_text']:.1f}, "
                f"flavor={scores['flavor_fit']:.1f}, "
                f"balance={scores['balance']:.1f}, "
                f"creativity={scores['creativity']:.1f}, "
                f"overall={scores['overall']:.2f}"
            )
            if scores["issues"]:
                md_lines.append("- Issues:")
                for issue in scores["issues"]:
                    md_lines.append(f"  - {issue}")
            md_lines.append("")

    # GO/NO-GO section
    md_lines.extend(
        [
            "## GO/NO-GO Assessment",
            "",
            f"- Rules text avg: {grand_rules:.2f} (need >= 4.0) "
            f"-- {'PASS' if rules_pass else 'FAIL'}",
            f"- Overall avg: {grand_overall:.2f} (need >= 3.5) "
            f"-- {'PASS' if overall_pass else 'FAIL'}",
            "",
            "### Per-Mechanic Assessment",
            "",
        ]
    )

    for mech_name, stats in mechanic_stats.items():
        mech_rules_ok = stats["avg_rules"] >= 4.0
        mech_overall_ok = stats["avg_overall"] >= 3.5
        status = "GO" if (mech_rules_ok and mech_overall_ok) else "NEEDS ITERATION"
        md_lines.append(
            f"- **{mech_name}**: rules={stats['avg_rules']:.2f}, "
            f"overall={stats['avg_overall']:.2f} -- {status}"
        )

    md_lines.extend(
        [
            "",
            f"### Verdict: **{verdict}**",
            "",
        ]
    )

    if flagged_mechanics:
        md_lines.append(f"Mechanics flagged for iteration: {', '.join(flagged_mechanics)}")
        md_lines.append("")
        md_lines.append(
            "Recommended next steps: Review flagged mechanic syntax in system prompt, "
            "add few-shot examples, and re-run spike."
        )

    RESULTS_PATH.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"Saved results summary to {RESULTS_PATH}")

    # Cache stats
    stats_cache = llm.stats()
    print(f"\nCache stats: {json.dumps(stats_cache, indent=2)}")


if __name__ == "__main__":
    main()
