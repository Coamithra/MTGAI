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
from mtgai.io.atomic import atomic_write_text
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


# ---------------------------------------------------------------------------
# Land cycles (Phase C) — guildgate-style cycles budgeted in the skeleton
# ---------------------------------------------------------------------------

_LETTER_TO_COLOR = {
    "W": Color.WHITE,
    "U": Color.BLUE,
    "B": Color.BLACK,
    "R": Color.RED,
    "G": Color.GREEN,
}
_COLOR_FULL = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}


def _land_member_colors(slot: dict) -> list[Color]:
    """Color identity for a land-cycle member from its color_pair / color."""
    pair = slot.get("color_pair")
    if pair:
        return [_LETTER_TO_COLOR[c] for c in pair if c in _LETTER_TO_COLOR]
    color = slot.get("color")
    if color in _LETTER_TO_COLOR:
        return [_LETTER_TO_COLOR[color]]
    return []


def _land_member_label(slot: dict) -> str:
    """Human label of a land member's colors for the prompt."""
    pair = str(slot.get("color_pair") or "")
    if pair:
        return "/".join(_COLOR_FULL.get(c, c) for c in pair)
    color = slot.get("color")
    if color in _COLOR_FULL:
        return _COLOR_FULL[color]
    return "Colorless"


def _build_cycle_prompt(
    cycle_name: str, template: str, members: list[dict], set_config: dict
) -> tuple[str, str]:
    system = (
        "You are a Magic: The Gathering land designer. You design clean, parallel "
        "nonbasic land cycles for Limited play — every member of a cycle shares the "
        "same structure, differing only by the colors it serves."
    )
    member_lines = "\n".join(f"{i}. {_land_member_label(m)} land" for i, m in enumerate(members, 1))
    user = (
        f"# Land Cycle: {cycle_name} — {set_config.get('name', 'Unknown')}\n"
        f"**Setting**: {set_config.get('flavor_description', '') or set_config.get('theme', '')}\n"
        f"**Shared template**: {template or 'A simple Limited mana-fixing land.'}\n\n"
        f"Design exactly {len(members)} nonbasic lands — one per entry below, IN ORDER. "
        "Every land must follow the shared template (same structure / wording), differing "
        "only by the colors it serves. Keep them simple (Limited commons), give each a "
        "setting-appropriate name and a one-sentence flavor text.\n\n"
        f"{member_lines}\n"
    )
    return system, user


def _build_cycle_tool_schema(n: int) -> dict:
    return {
        "name": "create_land_cycle",
        "description": f"Create the {n} parallel lands of a cycle, in the requested order.",
        "input_schema": {
            "type": "object",
            "required": ["lands"],
            "properties": {
                "lands": {
                    "type": "array",
                    "description": f"Exactly {n} lands, one per requested member, in order.",
                    "items": {
                        "type": "object",
                        "required": ["name", "type_line", "oracle_text", "flavor_text"],
                        "properties": {
                            "name": {"type": "string"},
                            "type_line": {"type": "string", "description": "e.g. 'Land'"},
                            "oracle_text": {"type": "string"},
                            "flavor_text": {"type": "string"},
                        },
                    },
                }
            },
        },
    }


def _make_cycle_land_card(data: dict, slot: dict, set_code: str, cycle_id: str) -> Card:
    return Card(
        name=data["name"],
        mana_cost=None,
        cmc=0.0,
        colors=[],
        color_identity=_land_member_colors(slot),
        type_line=data.get("type_line") or "Land",
        supertypes=[],
        card_types=["Land"],
        subtypes=[],
        oracle_text=data.get("oracle_text", ""),
        flavor_text=data.get("flavor_text", ""),
        collector_number=str(slot.get("slot_id") or "L-00"),
        rarity=Rarity(slot.get("rarity", "common")),
        set_code=set_code,
        is_reprint=False,
        design_notes=f"Land cycle '{cycle_id}' member designed by the lands stage",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def generate_land_cycles(
    skeleton: dict,
    set_config: dict,
    model_id: str,
    set_code: str,
    cards_dir: Path,
    on_card_saved: Callable[[Card], None] | None = None,
    on_call_start: Callable[[str], None] | None = None,
) -> dict:
    """Generate the members of any land cycles budgeted in the skeleton.

    Land slots (``card_type == "land"``) carrying a ``cycle_id`` — e.g. a pairs10
    guildgate cycle — are generated here, one LLM call per cycle so the family
    shares a template and parallel structure. Returns ``{total_cards, cost_usd}``.
    """
    land_slots = [
        s for s in skeleton.get("slots", []) if s.get("card_type") == "land" and s.get("cycle_id")
    ]
    if not land_slots:
        return {"total_cards": 0, "cost_usd": 0.0}

    templates = {
        c.get("id"): (c.get("template", ""), c.get("name", c.get("id")))
        for c in (skeleton.get("cycles") or [])
        if isinstance(c, dict) and c.get("id")
    }
    by_cycle: dict[str, list[dict]] = {}
    for slot in land_slots:
        by_cycle.setdefault(slot["cycle_id"], []).append(slot)

    saved = 0
    cost = 0.0
    for cycle_id, members in by_cycle.items():
        template, cycle_name = templates.get(cycle_id, ("", cycle_id))
        system, user = _build_cycle_prompt(
            str(cycle_name or cycle_id), template, members, set_config
        )
        if on_call_start is not None:
            on_call_start(model_id)
        try:
            response = generate_with_tool(
                system_prompt=system,
                user_prompt=user,
                tool_schema=_build_cycle_tool_schema(len(members)),
                model=model_id,
                temperature=0.7,
                max_tokens=4096,
            )
        except Exception:
            logger.exception("Land cycle '%s' generation failed; skipping", cycle_id)
            continue
        cost += cost_from_result(response)
        lands_data = (response.get("result") or {}).get("lands") or []
        for slot, data in zip(members, lands_data, strict=False):
            if not isinstance(data, dict) or not data.get("name"):
                continue
            card = _make_cycle_land_card(data, slot, set_code, cycle_id)
            filename = f"{slot.get('slot_id')}_{_slugify(card.name)}.json"
            atomic_write_text(
                cards_dir / filename,
                json.dumps(card.model_dump(mode="json"), indent=2, ensure_ascii=False),
            )
            saved += 1
            logger.info("  Saved land-cycle member: %s (%s)", card.name, cycle_id)
            if on_card_saved is not None:
                on_card_saved(card)

    logger.info("Generated %d land-cycle card(s) ($%.4f)", saved, cost)
    return {"total_cards": saved, "cost_usd": cost}


def generate_lands(
    on_call_start: Callable[[str], None] | None = None,
    on_card_saved: Callable[[Card], None] | None = None,
) -> dict:
    """Generate land cards for the active project.

    Returns a summary dict with total_cards and cost_usd.

    Optional callbacks let a UI surface progress:
      ``on_call_start(model)`` fires right before the Haiku request,
      ``on_card_saved(card)`` fires after each Card is written to disk.
    """
    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    project = require_active_project()
    set_code = project.set_code
    set_dir = set_artifact_dir()
    skeleton_path = set_dir / "skeleton.json"
    cards_dir = set_dir / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)

    set_config = extract_set_config(skeleton_path)
    skeleton = (
        json.loads(skeleton_path.read_text(encoding="utf-8")) if skeleton_path.exists() else {}
    )
    has_land_cycles = any(
        s.get("card_type") == "land" and s.get("cycle_id") for s in skeleton.get("slots", [])
    )

    logger.info("Generating lands for set %s...", set_code)

    system, user = _build_prompt(set_config)
    tool_schema = _build_tool_schema()

    model_id = project.settings.get_llm_model_id("lands")
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
        atomic_write_text(
            path,
            json.dumps(card.model_dump(mode="json"), indent=2, ensure_ascii=False),
        )
        cards_saved += 1
        logger.info("  Saved %s: %s", basic["name"], filename)
        if on_card_saved is not None:
            on_card_saved(card)

    # The generic single fixing land is redundant when the skeleton budgets a
    # proper land cycle (it provides the fixing), so skip it in that case.
    if nonbasic_data and not has_land_cycles:
        card = _make_nonbasic_card(nonbasic_data, set_code)
        filename = f"L-06_{_slugify(nonbasic_data['name'])}.json"
        path = cards_dir / filename
        atomic_write_text(
            path,
            json.dumps(card.model_dump(mode="json"), indent=2, ensure_ascii=False),
        )
        cards_saved += 1
        if on_card_saved is not None:
            on_card_saved(card)
        logger.info("  Saved nonbasic: %s", nonbasic_data["name"])

    # Phase C: generate any land cycles budgeted in the skeleton (e.g. guildgates).
    if has_land_cycles:
        cyc_summary = generate_land_cycles(
            skeleton, set_config, model_id, set_code, cards_dir, on_card_saved, on_call_start
        )
        cards_saved += cyc_summary["total_cards"]
        cost += cyc_summary["cost_usd"]

    logger.info("Generated %d land cards ($%.4f)", cards_saved, cost)
    return {"total_cards": cards_saved, "cost_usd": cost}
