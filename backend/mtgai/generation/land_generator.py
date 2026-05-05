"""Land generation — 5 basic lands + 1 common nonbasic fixing land.

Extracted from scripts/generate_lands.py for use by the unified pipeline.
Uses a single Haiku call for all creative text (~$0.002).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from mtgai.generation.llm_client import cost_from_result, generate_with_tool
from mtgai.generation.reprint_selector import extract_set_config
from mtgai.models.card import Card
from mtgai.models.enums import Color, Rarity

logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path("C:/Programming/MTGAI/output")

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
        "location or scene from this world. "
        "Use em-dashes for attribution if quoting a character.\n\n"
        "1. Plains\n"
        "2. Island\n"
        "3. Swamp\n"
        "4. Mountain\n"
        "5. Forest\n\n"
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
                    "description": (
                        "Flavor text for 5 basic lands (Plains, Island, Swamp, Mountain, Forest)"
                    ),
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
                        "type_line": {
                            "type": "string",
                            "description": "e.g. 'Land'",
                        },
                        "oracle_text": {"type": "string"},
                        "flavor_text": {"type": "string"},
                    },
                    "required": ["name", "type_line", "oracle_text", "flavor_text"],
                },
            },
            "required": ["basics", "nonbasic"],
        },
    }


def _make_basic_card(basic: dict, flavor_text: str, set_code: str) -> Card:
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
        set_code=set_code,
        is_reprint=True,
        design_notes="Basic land with set-themed flavor text (Haiku)",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_nonbasic_card(data: dict, set_code: str) -> Card:
    ci: list[Color] = []
    color_map = {
        "{W}": Color.WHITE,
        "{U}": Color.BLUE,
        "{B}": Color.BLACK,
        "{R}": Color.RED,
        "{G}": Color.GREEN,
    }
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
        set_code=set_code,
        is_reprint=False,
        design_notes="Nonbasic fixing land designed by Haiku",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _slugify(name: str) -> str:
    return name.lower().replace(" ", "_").replace("'", "").replace(",", "")


def generate_lands(
    set_code: str = "ASD",
    on_call_start: Callable[[str], None] | None = None,
    on_card_saved: Callable[[Card], None] | None = None,
) -> dict:
    """Generate land cards for a set.

    Returns a summary dict with total_cards and cost_usd.

    Optional callbacks let a UI surface progress:
      ``on_call_start(model)`` fires right before the Haiku request,
      ``on_card_saved(card)`` fires after each Card is written to disk.
    """
    set_dir = OUTPUT_ROOT / "sets" / set_code
    skeleton_path = set_dir / "skeleton.json"
    cards_dir = set_dir / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)

    set_config = extract_set_config(skeleton_path)

    logger.info("Generating lands for set %s...", set_code)

    system, user = _build_prompt(set_config)
    tool_schema = _build_tool_schema()

    # Resolve the configured model for the lands stage from per-set settings.
    from mtgai.settings.model_settings import get_llm_model

    model_id = get_llm_model("lands", set_code)
    if on_call_start is not None:
        on_call_start(model_id)
    response = generate_with_tool(
        system_prompt=system,
        user_prompt=user,
        tool_schema=tool_schema,
        model=model_id,
        temperature=0.7,
        max_tokens=2048,
    )

    result = response.get("result", {})
    basics_data = result.get("basics", [])
    nonbasic_data = result.get("nonbasic", {})
    cost = cost_from_result(response)

    logger.info(
        "Land gen tokens: in=%s out=%s cost=$%.4f",
        response.get("input_tokens", "?"),
        response.get("output_tokens", "?"),
        cost,
    )

    flavor_by_name = {b["land_name"]: b["flavor_text"] for b in basics_data}
    cards_saved = 0

    for basic in BASICS:
        flavor = flavor_by_name.get(basic["name"], "")
        if not flavor:
            logger.warning("No flavor text for %s!", basic["name"])
            continue

        card = _make_basic_card(basic, flavor, set_code)
        filename = f"{basic['cn']}_{_slugify(basic['name'])}.json"
        path = cards_dir / filename
        path.write_text(
            json.dumps(card.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        cards_saved += 1
        logger.info("  Saved %s: %s", basic["name"], filename)
        if on_card_saved is not None:
            on_card_saved(card)

    if nonbasic_data:
        card = _make_nonbasic_card(nonbasic_data, set_code)
        filename = f"L-06_{_slugify(nonbasic_data['name'])}.json"
        path = cards_dir / filename
        path.write_text(
            json.dumps(card.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        cards_saved += 1
        if on_card_saved is not None:
            on_card_saved(card)
        logger.info("  Saved nonbasic: %s", nonbasic_data["name"])

    logger.info("Generated %d land cards ($%.4f)", cards_saved, cost)
    return {"total_cards": cards_saved, "cost_usd": cost}
