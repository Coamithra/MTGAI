"""Generate land cards for the ASD dev set.

5 basic lands (with themed flavor text) + 1 common nonbasic land.
Uses a single Haiku call for all creative text (~$0.002).
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-7s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

from mtgai.generation.llm_client import generate_with_tool
from mtgai.generation.reprint_selector import extract_set_config
from mtgai.models.card import Card
from mtgai.models.enums import Color, Rarity

SKELETON_PATH = Path("../output/sets/ASD/skeleton.json")
CARDS_DIR = Path("../output/sets/ASD/cards")

# Basic land data (mechanical fields are fixed — only flavor text varies)
BASICS = [
    {"name": "Plains", "subtype": "Plains", "color_identity": Color.WHITE, "cn": "L-01"},
    {"name": "Island", "subtype": "Island", "color_identity": Color.BLUE, "cn": "L-02"},
    {"name": "Swamp", "subtype": "Swamp", "color_identity": Color.BLACK, "cn": "L-03"},
    {"name": "Mountain", "subtype": "Mountain", "color_identity": Color.RED, "cn": "L-04"},
    {"name": "Forest", "subtype": "Forest", "color_identity": Color.GREEN, "cn": "L-05"},
]


def _build_prompt(set_config: dict) -> tuple[str, str]:
    system = (
        "You are a Magic: The Gathering creative writer specializing in flavor text. "
        "You write evocative, concise, setting-appropriate flavor text."
    )
    user = (
        f"# Land Cards for {set_config.get('name', 'Unknown')}\n"
        f"**Theme**: {set_config.get('theme', '')}\n"
        f"**Setting**: {set_config.get('flavor_description', '')}\n"
        f"**Special**: {', '.join(set_config.get('special_constraints', []))}\n\n"
        "## Task 1: Basic Land Flavor Text\n"
        "Write 1-2 sentence flavor text for each basic land. Each should evoke a specific "
        "location or scene from this world. Use em-dashes for attribution if quoting a character.\n\n"
        "1. Plains — flat, open terrain near Denethix\n"
        "2. Island — water, coastline, or flooded underground areas\n"
        "3. Swamp — dark, decaying, toxic areas below the surface\n"
        "4. Mountain — volcanic, rocky, the peaks around Mount Rendon\n"
        "5. Forest — overgrown wilderness with dinosaurs and ancient growth\n\n"
        "## Task 2: Nonbasic Land Design\n"
        "Design exactly 1 common nonbasic land for mana fixing in Limited. It should:\n"
        "- Enter tapped (standard for common fixing lands)\n"
        "- Tap for one of two or more colors, OR sacrifice to fetch a basic\n"
        "- Have a setting-appropriate but generic name (no character names)\n"
        "- Have flavor text (1 sentence)\n"
        "- Be simple — this is a common land for Limited play\n"
    )
    return system, user


def _build_tool_schema() -> dict:
    return {
        "name": "create_lands",
        "description": "Create basic land flavor text and a nonbasic land design",
        "input_schema": {
            "type": "object",
            "properties": {
                "basics": {
                    "type": "array",
                    "description": "Flavor text for 5 basic lands (Plains, Island, Swamp, Mountain, Forest)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "land_name": {"type": "string"},
                            "flavor_text": {"type": "string"},
                        },
                        "required": ["land_name", "flavor_text"],
                    },
                },
                "nonbasic": {
                    "type": "object",
                    "description": "Design for 1 common nonbasic land",
                    "properties": {
                        "name": {"type": "string"},
                        "type_line": {"type": "string", "description": "e.g. 'Land'"},
                        "oracle_text": {"type": "string"},
                        "flavor_text": {"type": "string"},
                    },
                    "required": ["name", "type_line", "oracle_text", "flavor_text"],
                },
            },
            "required": ["basics", "nonbasic"],
        },
    }


def _make_basic_card(basic: dict, flavor_text: str) -> Card:
    return Card(
        name=basic["name"],
        mana_cost=None,
        cmc=0.0,
        colors=[],
        color_identity=[basic["color_identity"]],
        type_line=f"Basic Land \u2014 {basic['subtype']}",
        supertypes=["Basic"],
        card_types=["Land"],
        subtypes=[basic["subtype"]],
        oracle_text="",
        flavor_text=flavor_text,
        collector_number=basic["cn"],
        rarity=Rarity.COMMON,
        set_code="ASD",
        is_reprint=True,
        design_notes="Basic land with set-themed flavor text (Haiku)",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_nonbasic_card(data: dict) -> Card:
    # Parse color identity from oracle text (look for mana symbols)
    ci: list[Color] = []
    color_map = {"{W}": Color.WHITE, "{U}": Color.BLUE, "{B}": Color.BLACK,
                 "{R}": Color.RED, "{G}": Color.GREEN}
    for symbol, color in color_map.items():
        if symbol in data["oracle_text"]:
            ci.append(color)

    return Card(
        name=data["name"],
        mana_cost=None,
        cmc=0.0,
        colors=[],
        color_identity=ci,
        type_line=data["type_line"],
        supertypes=[],
        card_types=["Land"],
        subtypes=[],
        oracle_text=data["oracle_text"],
        flavor_text=data["flavor_text"],
        collector_number="L-06",
        rarity=Rarity.COMMON,
        set_code="ASD",
        is_reprint=False,
        design_notes="Nonbasic fixing land designed by Haiku",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _slugify(name: str) -> str:
    return name.lower().replace(" ", "_").replace("'", "").replace(",", "")


def main() -> None:
    set_config = extract_set_config(SKELETON_PATH)

    logger.info("=" * 60)
    logger.info("LAND GENERATION — ASD dev set")
    logger.info("=" * 60)

    system, user = _build_prompt(set_config)
    tool_schema = _build_tool_schema()

    logger.info("Calling Haiku for land flavor text + nonbasic design...")
    response = generate_with_tool(
        system_prompt=system,
        user_prompt=user,
        tool_schema=tool_schema,
        model="claude-haiku-4-5-20251001",
        temperature=0.7,  # Creative task — allow some variation
        max_tokens=2048,
    )

    result = response.get("result", {})
    basics_data = result.get("basics", [])
    nonbasic_data = result.get("nonbasic", {})

    logger.info("Input tokens:  %s", response.get("input_tokens", "?"))
    logger.info("Output tokens: %s", response.get("output_tokens", "?"))

    # Build flavor text lookup
    flavor_by_name = {b["land_name"]: b["flavor_text"] for b in basics_data}

    print()
    print("=" * 60)
    print("BASIC LANDS")
    print("=" * 60)

    cards_saved = []
    for basic in BASICS:
        flavor = flavor_by_name.get(basic["name"], "")
        if not flavor:
            logger.warning("No flavor text for %s!", basic["name"])
            continue

        card = _make_basic_card(basic, flavor)
        filename = f"{basic['cn']}_{_slugify(basic['name'])}.json"
        path = CARDS_DIR / filename
        path.write_text(
            json.dumps(card.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        cards_saved.append(filename)
        print(f"\n  {basic['name']} ({basic['cn']})")
        print(f"    \"{flavor}\"")

    print()
    print("=" * 60)
    print("NONBASIC LAND")
    print("=" * 60)

    if nonbasic_data:
        card = _make_nonbasic_card(nonbasic_data)
        filename = f"L-06_{_slugify(nonbasic_data['name'])}.json"
        path = CARDS_DIR / filename
        path.write_text(
            json.dumps(card.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        cards_saved.append(filename)
        print(f"\n  {nonbasic_data['name']}")
        print(f"    Type: {nonbasic_data['type_line']}")
        print(f"    Text: {nonbasic_data['oracle_text']}")
        print(f"    Flavor: \"{nonbasic_data['flavor_text']}\"")

    print()
    print("=" * 60)
    print(f"Saved {len(cards_saved)} land cards to {CARDS_DIR.resolve()}")
    for f in cards_saved:
        print(f"  {f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
