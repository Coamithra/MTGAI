"""Mechanic generation and validation for custom MTG sets."""

from pathlib import Path

from mtgai.generation.llm_client import generate_with_tool

# ---------------------------------------------------------------------------
# Tool schema: defines the structured output the LLM must return
# ---------------------------------------------------------------------------

MECHANIC_TOOL_SCHEMA: dict = {
    "name": "submit_mechanic_candidates",
    "description": (
        "Submit a list of mechanic candidates for the custom MTG set. "
        "Each mechanic must include all required fields."
    ),
    "input_schema": {
        "type": "object",
        "required": ["mechanics"],
        "properties": {
            "mechanics": {
                "type": "array",
                "description": "List of mechanic candidates",
                "items": {
                    "type": "object",
                    "required": [
                        "name",
                        "keyword_type",
                        "reminder_text",
                        "colors",
                        "complexity",
                        "flavor_connection",
                        "design_rationale",
                        "common_patterns",
                        "uncommon_patterns",
                        "rare_patterns",
                        "example_cards",
                    ],
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The mechanic keyword name",
                        },
                        "keyword_type": {
                            "type": "string",
                            "enum": [
                                "keyword_ability",
                                "ability_word",
                                "keyword_action",
                            ],
                            "description": "Type of keyword",
                        },
                        "reminder_text": {
                            "type": "string",
                            "description": ("Reminder text in parentheses, under 100 chars"),
                        },
                        "colors": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["W", "U", "B", "R", "G"],
                            },
                            "description": "Colors this mechanic appears in",
                        },
                        "complexity": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 3,
                            "description": ("1=common-viable, 2=uncommon+, 3=rare+"),
                        },
                        "flavor_connection": {
                            "type": "string",
                            "description": ("How the mechanic connects to set flavor"),
                        },
                        "design_rationale": {
                            "type": "string",
                            "description": ("Why this mechanic is good for the set"),
                        },
                        "common_patterns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": ("Rules text patterns for common cards"),
                        },
                        "uncommon_patterns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": ("Rules text patterns for uncommon cards"),
                        },
                        "rare_patterns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": ("Rules text patterns for rare/mythic cards"),
                        },
                        "example_cards": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": [
                                    "name",
                                    "mana_cost",
                                    "type_line",
                                    "oracle_text",
                                    "rarity",
                                ],
                                "properties": {
                                    "name": {"type": "string"},
                                    "mana_cost": {"type": "string"},
                                    "type_line": {"type": "string"},
                                    "oracle_text": {"type": "string"},
                                    "power": {"type": "string"},
                                    "toughness": {"type": "string"},
                                    "rarity": {
                                        "type": "string",
                                        "enum": [
                                            "common",
                                            "uncommon",
                                            "rare",
                                            "mythic",
                                        ],
                                    },
                                },
                            },
                            "description": "2-3 example cards using this mechanic",
                        },
                    },
                },
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert Magic: The Gathering set designer. You design custom mechanics \
that are flavorful, mechanically sound, and balanced for Limited play.

## Set Information: Anomalous Descent (ASD)

**Theme:** Science-fantasy megadungeon in far-future post-apocalyptic Earth.

**Flavor:** Thousands of years after civilization collapsed, the city of Denethix \
clings to order at the edge of a wilderness teeming with dinosaurs, moktars, and \
rogue wizards. Beneath Mount Rendon lies the Anomalous Subsurface Environment — \
a self-spawning megadungeon that predates humanity, filled with ancient super-science \
relics, degraded automatons, and things far worse. Adventurers descend seeking fortune. \
Most don't return.

The Vizier rules through lies. The Cult of Science worships technology they barely \
understand. The Society of the Luminous Spark fights slavery. Raiders, wizards, and \
dinosaurs roam the wilderness. And deep in the dungeon, something watches.

**Set Size:** 60 cards (small set).
**Custom Mechanics:** 3 (we need 6 candidates to choose from).

## Draft Archetypes
- WU: Ancient Technology — artifacts, automatons, incremental value (control)
- WB: Vizier's Regime — sacrifice, taxation, drain (midrange)
- WR: Spark Rebellion — go-wide aggro, equipment, combat tricks
- WG: Frontier Settlers — tokens, +1/+1 counters, go-wide (midrange)
- UB: Deep Descent — mill, graveyard, card selection (control)
- UR: Mad Science — spellslinger with artifact synergies (midrange)
- UG: Dungeon Ecology — +1/+1 counters, creature-based card advantage (midrange)
- BR: Raider Warbands — aggressive sacrifice, burn (aggro)
- BG: Twisted Evolution — graveyard recursion, death triggers (midrange)
- RG: Prehistoric Fury — ramp, dinosaurs, trample (midrange)

## Color Pie Reference (P=primary, S=secondary, T=tertiary)

| Effect              | W  | U  | B  | R  | G  |
|---------------------|----|----|----|----|-----|
| Direct damage       | —  | —  | —  | P  | —   |
| Destroy creature    | P  | —  | P  | —  | S   |
| Card draw           | T  | P  | S  | —  | T   |
| Counterspell        | —  | P  | —  | —  | —   |
| Graveyard recursion | S  | —  | P  | —  | S   |
| +1/+1 counters      | S  | T  | —  | —  | P   |
| Tokens              | P  | S  | S  | S  | P   |
| Life gain           | P  | —  | S  | —  | S   |
| Mill                | —  | P  | S  | —  | —   |
| Discard             | —  | —  | P  | S  | —   |
| Artifact synergy    | S  | P  | —  | S  | —   |
| Sacrifice effects   | —  | —  | P  | S  | —   |
| Ramp / mana accel   | —  | —  | —  | T  | P   |
| Pump / combat trick | P  | —  | S  | P  | P   |
| Evasion             | P  | P  | S  | S  | T   |
| Enchantment synergy | P  | S  | —  | —  | S   |

## Existing MTG Mechanics to AVOID Duplicating
Do NOT re-create any of these existing mechanics. Your designs must be meaningfully \
different in both flavor and function:
investigate, explore, surveil, amass, adapt, mutate, foretell, ward, channel, \
ninjutsu, crew, disturb, venture (into the dungeon), connive, enlist, domain, \
descend (the existing Ixalan mechanic), discover, disguise, manifest dread, eerie, \
collect evidence, plot, crime, suspect, offspring, valiant, survival, impending, \
delirium, threshold, flashback, madness, energy, convoke, delve, fabricate, \
proliferate, exploit, eternalize, embalm, exert, afterlife, spectacle, riot, \
escape, devotion, constellation, landfall, kicker, adventure, boast, sagas, \
learn/lessons, daybound/nightbound, blood tokens, clue tokens, food tokens, \
treasure tokens, map tokens, powerstone tokens, incubate.

## Design Constraints
1. Reminder text MUST be under 100 characters.
2. Each mechanic should appear in 2-3 colors (not all 5, not just 1).
3. At least one mechanic must be complexity 1 (viable at common).
4. Mechanics must support Limited play in a 60-card set.
5. Each mechanic needs clear design space for common, uncommon, and rare versions.
6. Mechanics should reinforce at least 2 draft archetypes.
7. Avoid parasitic mechanics — they should work with normal MTG cards too.
8. For a 60-card set, each mechanic should appear on roughly 6-10 cards.
"""

USER_PROMPT = """\
Design 6 mechanic candidates for the Anomalous Descent (ASD) set.

Requirements:
- We will select 3 of the 6, so generate extra for choice
- Each should feel DISTINCT from the others — different mechanical spaces
- Must fit the "science-fantasy megadungeon" theme
- Span different mechanical spaces:
  - At least one creature-focused mechanic
  - At least one spell-focused or triggered-ability mechanic
  - At least one that could go on any permanent type
- At least one MUST be complexity 1 (viable at common with simple reminder text)
- At least one should be complexity 2-3 for more interesting rare designs
- Each mechanic should support 2+ draft archetypes from the set
- Provide 2-3 example cards per mechanic showing different rarities

Think carefully about:
1. How the mechanic plays in Limited (is it fun? does it create interesting decisions?)
2. How it reinforces the set's themes (dungeon exploration, ancient tech, post-apocalypse)
3. How it interacts with the other potential mechanics
4. Whether it has enough design space for 6-10 cards in a 60-card set

For each mechanic, provide concrete rules text patterns showing how it would appear \
on commons, uncommons, and rares. Example cards should have complete, valid MTG \
templating (mana costs, type lines, oracle text with proper formatting).
"""


# ---------------------------------------------------------------------------
# Color pie validation
# ---------------------------------------------------------------------------

# Maps effect keywords to their primary/secondary colors
COLOR_PIE: dict[str, dict[str, str]] = {
    "direct_damage": {"R": "P"},
    "destroy_creature": {"W": "P", "B": "P", "G": "S"},
    "card_draw": {"U": "P", "B": "S", "W": "T", "G": "T"},
    "counterspell": {"U": "P"},
    "graveyard_recursion": {"B": "P", "W": "S", "G": "S"},
    "counters": {"G": "P", "W": "S", "U": "T"},
    "tokens": {"W": "P", "G": "P", "U": "S", "B": "S", "R": "S"},
    "life_gain": {"W": "P", "B": "S", "G": "S"},
    "mill": {"U": "P", "B": "S"},
    "discard": {"B": "P", "R": "S"},
    "artifact_synergy": {"U": "P", "W": "S", "R": "S"},
    "sacrifice": {"B": "P", "R": "S"},
    "ramp": {"G": "P", "R": "T"},
    "pump": {"W": "P", "R": "P", "G": "P", "B": "S"},
    "evasion": {"W": "P", "U": "P", "B": "S", "R": "S", "G": "T"},
    "enchantment_synergy": {"W": "P", "U": "S", "G": "S"},
}

# Effect keywords to look for in mechanic text
EFFECT_KEYWORDS: dict[str, list[str]] = {
    "direct_damage": ["damage", "deals damage"],
    "destroy_creature": ["destroy", "destroys"],
    "card_draw": ["draw", "draws", "card advantage"],
    "counterspell": ["counter", "counters a spell"],
    "graveyard_recursion": [
        "graveyard",
        "return from graveyard",
        "recursion",
        "reanimate",
    ],
    "counters": ["+1/+1 counter", "counter on", "counters on"],
    "tokens": ["token", "create a", "create tokens"],
    "life_gain": ["gain life", "life gain", "lifelink"],
    "mill": ["mill", "into graveyard from library"],
    "discard": ["discard"],
    "artifact_synergy": ["artifact", "artifacts"],
    "sacrifice": ["sacrifice"],
    "ramp": ["mana", "add {", "search for a land"],
    "pump": ["+1/+0", "+2/+2", "+1/+1 until", "gets +"],
    "evasion": [
        "flying",
        "menace",
        "trample",
        "can't be blocked",
        "unblockable",
    ],
    "enchantment_synergy": ["enchantment", "enchantments", "aura"],
}


def validate_mechanic_color_pie(mechanic: dict) -> list[str]:
    """Check a mechanic candidate against color pie rules.

    Returns a list of warning/error strings. Empty list means the mechanic
    passes validation.
    """
    warnings: list[str] = []
    colors = mechanic.get("colors", [])
    if not colors:
        warnings.append("ERROR: Mechanic has no assigned colors")
        return warnings

    # Collect all rules text for analysis
    all_text_parts = [
        mechanic.get("reminder_text", ""),
        mechanic.get("design_rationale", ""),
    ]
    for pattern_key in ("common_patterns", "uncommon_patterns", "rare_patterns"):
        all_text_parts.extend(mechanic.get(pattern_key, []))
    for card in mechanic.get("example_cards", []):
        all_text_parts.append(card.get("oracle_text", ""))
    all_text = " ".join(all_text_parts).lower()

    # Check each detected effect against color pie
    for effect_name, keywords in EFFECT_KEYWORDS.items():
        if any(kw in all_text for kw in keywords):
            pie = COLOR_PIE.get(effect_name, {})
            # Check if at least one assigned color has this as P or S
            has_primary_or_secondary = any(pie.get(c) in ("P", "S") for c in colors)
            if not has_primary_or_secondary and pie:
                # Check if it's at least tertiary
                has_tertiary = any(pie.get(c) == "T" for c in colors)
                if has_tertiary:
                    warnings.append(
                        f"WARN: '{effect_name}' is only tertiary in {colors} — use sparingly"
                    )
                else:
                    # Could be a false positive from keyword detection
                    warnings.append(
                        f"NOTE: '{effect_name}' detected in text but not "
                        f"primary/secondary in {colors} — verify intent"
                    )

    # Check reminder text length
    reminder = mechanic.get("reminder_text", "")
    if len(reminder) > 100:
        warnings.append(f"ERROR: Reminder text is {len(reminder)} chars (max 100)")

    # Check complexity vs target rarities
    complexity = mechanic.get("complexity", 1)
    if complexity == 1 and not mechanic.get("common_patterns"):
        warnings.append("WARN: Complexity 1 mechanic should have common patterns")

    return warnings


# ---------------------------------------------------------------------------
# Evergreen keyword assignment
# ---------------------------------------------------------------------------


def assign_evergreen_keywords() -> dict[str, list[str]]:
    """Return the standard evergreen keyword assignment for each color.

    These are the keywords the set will use on vanilla/french-vanilla creatures
    and as rider abilities. Based on standard MTG color pie conventions.
    """
    return {
        "W": ["flying", "first strike", "vigilance", "lifelink", "defender"],
        "U": ["flying", "ward", "flash", "hexproof"],
        "B": ["deathtouch", "menace", "lifelink", "flash"],
        "R": ["haste", "menace", "first strike", "trample"],
        "G": ["trample", "reach", "vigilance", "flash", "deathtouch"],
    }


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------


def generate_mechanic_candidates(
    theme_path: str | Path | None = None,
) -> list[dict]:
    """Generate mechanic candidates for the active project via LLM.

    Args:
        theme_path: Optional path to theme.json for context.
            Not directly injected into prompt (already in system prompt),
            but used for logging/verification.

    Returns:
        List of mechanic candidate dicts.
    """
    from mtgai.runtime.active_project import require_active_project

    model_id = require_active_project().settings.get_llm_model_id("mechanics")

    print("Calling LLM to generate mechanic candidates...")
    print(f"  Model: {model_id}")
    print("  Temperature: 1.0")
    print("  This may take 30-60 seconds...\n")

    response = generate_with_tool(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=USER_PROMPT,
        tool_schema=MECHANIC_TOOL_SCHEMA,
        model=model_id,
        temperature=1.0,
        max_tokens=8192,
    )

    mechanics = response["result"]["mechanics"]
    print(f"Received {len(mechanics)} mechanic candidates")
    print(f"  Token usage: {response['input_tokens']} input, {response['output_tokens']} output\n")
    return mechanics
