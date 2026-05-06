"""Reprint selection for MTG set generation.

Identifies eligible skeleton slots, pre-filters the curated reprint pool by hard
constraints (color, rarity, type), then uses a single Haiku LLM call to pick the
best reprints for the set. Cost: ~$0.002 per selection.

This should run BEFORE card generation so that reprint slots are not wasted on
LLM-generated cards.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from mtgai.models.card import Card
from mtgai.models.enums import Color, Rarity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_POOL_PATH = Path(__file__).parent / "reprint_pool.json"

# Mechanic tags that indicate a slot can accept a reprint (no set-specific mechanic)
_REPRINT_ELIGIBLE_MECHANIC_TAGS = {"vanilla", "french_vanilla", "evergreen"}

# Card types most commonly reprinted
_REPRINT_ELIGIBLE_TYPES = {"instant", "sorcery", "creature", "enchantment", "artifact", "land"}

# Max candidates per slot sent to LLM (sorted by EDHREC popularity)
_MAX_CANDIDATES_PER_SLOT = 15


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class ReprintCandidate(BaseModel):
    """A card being considered for reprint."""

    name: str
    mana_cost: str | None = None
    cmc: float
    type_line: str
    oracle_text: str = ""
    colors: list[str] = Field(default_factory=list)
    rarity: str
    role: str
    setting_agnostic: bool | None = True
    source: str = "curated_pool"
    edhrec_rank: int | None = None
    keywords: list[str] = Field(default_factory=list)
    subtypes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    power: str | None = None
    toughness: str | None = None


class ReprintSlot(BaseModel):
    """A skeleton slot to be filled with a reprint."""

    slot_id: str
    color: str
    rarity: str
    card_type: str
    role_needed: str
    cmc_target: int | None = None
    mechanic_tag: str = ""


class SelectionPair(BaseModel):
    """A matched slot + candidate pair, with LLM reasoning."""

    slot: ReprintSlot
    candidate: ReprintCandidate
    reason: str = ""


class ReprintSelection(BaseModel):
    """Complete reprint selection result for a set."""

    set_code: str
    set_size: int
    target_reprint_count: int
    selections: list[SelectionPair]
    all_candidates_considered: int
    selection_timestamp: str


# ---------------------------------------------------------------------------
# Pool loading
# ---------------------------------------------------------------------------


def load_reprint_pool(pool_path: Path | None = None) -> list[ReprintCandidate]:
    """Load the curated reprint pool from JSON and return as candidate list."""
    path = pool_path or _POOL_PATH
    logger.info("Loading reprint pool from %s", path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    candidates: list[ReprintCandidate] = []
    for entry in data["cards"]:
        candidates.append(
            ReprintCandidate(
                name=entry["name"],
                mana_cost=entry.get("mana_cost") or None,
                cmc=float(entry["cmc"]),
                type_line=entry["type_line"],
                oracle_text=entry.get("oracle_text", ""),
                colors=entry.get("colors", []),
                rarity=entry["rarity"],
                role=entry["role"],
                setting_agnostic=entry.get("setting_agnostic", True),
                source="curated_pool",
                edhrec_rank=entry.get("edhrec_rank_approx"),
                keywords=entry.get("keywords", []),
                subtypes=entry.get("subtypes", []),
                tags=entry.get("tags", []),
                power=entry.get("power"),
                toughness=entry.get("toughness"),
            )
        )
    logger.info("Loaded %d candidates from curated pool", len(candidates))
    return candidates


# ---------------------------------------------------------------------------
# Set config extraction
# ---------------------------------------------------------------------------


def extract_set_config(skeleton_path: Path) -> dict:
    """Read skeleton.json and build the set_config dict.

    Returns a dict with keys: name, code, theme, flavor_description, themes,
    creature_types, special_constraints, set_size.
    """
    with open(skeleton_path, encoding="utf-8") as f:
        skeleton = json.load(f)

    config = skeleton.get("config", {})

    # Infer themes from flavor_description and special_constraints
    themes: list[str] = []
    flavor = config.get("flavor_description", "").lower()
    constraints = config.get("special_constraints", [])

    theme_keywords = {
        "artifact": ["artifact", "relic", "automaton", "construct", "super-science"],
        "megadungeon": ["megadungeon", "dungeon"],
        "science-fantasy": ["science-fantasy", "super-science"],
        "post-apocalyptic": ["post-apocalyptic", "apocalyptic", "collapsed"],
        "dinosaur": ["dinosaur"],
        "horror": ["horror", "nightmare"],
        "enchantment": ["enchantment"],
        "graveyard": ["graveyard", "undead", "zombie"],
    }
    for theme, kws in theme_keywords.items():
        if any(kw in flavor for kw in kws):
            themes.append(theme)

    for c in constraints:
        cl = c.lower()
        if "artifact" in cl and "artifact" not in themes:
            themes.append("artifact")
        if "dinosaur" in cl and "dinosaur" not in themes:
            themes.append("dinosaur")

    creature_types: list[str] = []
    type_candidates = [
        "Dinosaur",
        "Human",
        "Wizard",
        "Construct",
        "Elf",
        "Angel",
        "Horror",
        "Beast",
        "Rat",
        "Dragon",
        "Zombie",
    ]
    for ct in type_candidates:
        if ct.lower() in flavor or any(ct.lower() in c.lower() for c in constraints):
            creature_types.append(ct)

    return {
        "name": config.get("name", ""),
        "code": config.get("code", ""),
        "theme": config.get("theme", ""),
        "flavor_description": config.get("flavor_description", ""),
        "themes": themes,
        "creature_types": creature_types,
        "special_constraints": constraints,
        "set_size": config.get("set_size", 60),
    }


# ---------------------------------------------------------------------------
# Slot identification
# ---------------------------------------------------------------------------


def _infer_role(color: str, card_type: str, cmc: int | None, mechanic_tag: str) -> str:
    """Infer the functional role needed for a skeleton slot."""
    ct_lower = card_type.lower()

    if ct_lower == "land" or (color == "colorless" and ct_lower == "land"):
        return "mana_fixing"
    if color == "colorless" and ct_lower == "artifact":
        return "utility_creature"
    if ct_lower == "creature" and mechanic_tag in ("vanilla", "french_vanilla"):
        return "utility_creature"

    if ct_lower in ("instant", "sorcery"):
        if color == "B":
            return "removal_hard_kill"
        if color == "R":
            return "removal_damage"
        if color == "W":
            return "combat_trick" if cmc is not None and cmc <= 3 else "removal_exile"
        if color == "U":
            return "counterspell" if cmc is not None and cmc <= 2 else "removal_bounce"
        if color == "G":
            return "removal_fight" if cmc is not None and cmc <= 2 else "combat_trick"

    if ct_lower == "enchantment":
        if color == "W":
            return "removal_exile"
        if color == "G":
            return "artifact_removal"
        return "utility_creature"

    if ct_lower == "creature":
        return "utility_creature"

    return "utility_creature"


def identify_reprint_slots(skeleton_path: Path) -> list[ReprintSlot]:
    """Read skeleton.json and identify slots eligible for reprints.

    A slot is eligible if:
    - mechanic_tag is in {vanilla, french_vanilla, evergreen}
    - card_type is a commonly reprinted type
    - NOT already assigned (card_id is null)
    """
    with open(skeleton_path, encoding="utf-8") as f:
        skeleton = json.load(f)

    slots: list[ReprintSlot] = []
    for slot_data in skeleton.get("slots", []):
        mechanic_tag = slot_data.get("mechanic_tag", "")
        card_type = slot_data.get("card_type", "")
        card_id = slot_data.get("card_id")

        if card_id is not None:
            continue
        if mechanic_tag not in _REPRINT_ELIGIBLE_MECHANIC_TAGS:
            continue
        if card_type.lower() not in _REPRINT_ELIGIBLE_TYPES:
            continue

        color = slot_data.get("color", "")
        rarity = slot_data.get("rarity", "")
        cmc_target = slot_data.get("cmc_target")
        role = _infer_role(color, card_type, cmc_target, mechanic_tag)

        slots.append(
            ReprintSlot(
                slot_id=slot_data["slot_id"],
                color=color,
                rarity=rarity,
                card_type=card_type,
                role_needed=role,
                cmc_target=cmc_target,
                mechanic_tag=mechanic_tag,
            )
        )

    logger.info(
        "Identified %d reprint-eligible slots from skeleton (%d total slots)",
        len(slots),
        len(skeleton.get("slots", [])),
    )
    return slots


# ---------------------------------------------------------------------------
# Pre-filtering
# ---------------------------------------------------------------------------


def _color_matches(candidate_colors: list[str], slot_color: str) -> bool:
    """Check if a candidate's colors match a slot's color requirement."""
    if slot_color == "colorless":
        return len(candidate_colors) == 0
    if slot_color == "multicolor":
        return len(candidate_colors) >= 2
    return candidate_colors == [slot_color]


def _type_matches(candidate_type_line: str, slot_card_type: str) -> bool:
    """Check if a candidate's type line is compatible with the slot's card type."""
    ct_lower = candidate_type_line.lower()
    st_lower = slot_card_type.lower()

    if st_lower in ct_lower:
        return True
    if st_lower == "creature" and "creature" in ct_lower:
        return True
    if st_lower == "enchantment" and "enchantment" in ct_lower:
        return True
    return st_lower == "artifact" and "artifact" in ct_lower


def pre_filter_for_slot(
    pool: list[ReprintCandidate],
    slot: ReprintSlot,
) -> list[ReprintCandidate]:
    """Filter pool to candidates compatible with a slot (color, rarity, type).

    Returns candidates sorted by EDHREC rank (most popular first), capped at
    _MAX_CANDIDATES_PER_SLOT.
    """
    filtered = [
        c
        for c in pool
        if _color_matches(c.colors, slot.color)
        and c.rarity == slot.rarity
        and _type_matches(c.type_line, slot.card_type)
    ]
    filtered.sort(key=lambda c: c.edhrec_rank if c.edhrec_rank is not None else 999999)
    return filtered[:_MAX_CANDIDATES_PER_SLOT]


# ---------------------------------------------------------------------------
# LLM-based selection
# ---------------------------------------------------------------------------


def format_candidate_tldr(c: ReprintCandidate) -> str:
    """Format a candidate as a compact one-liner for the LLM prompt.

    Examples:
        "Murder ({1}{B}{B} — Destroy target creature.)"
        "Firebrand Archer ({1}{R} 2/1 — Whenever you cast a noncreature spell, ...)"
    """
    parts = [c.name, " ("]
    if c.mana_cost:
        parts.append(c.mana_cost)
    else:
        parts.append("no cost")
    if c.power is not None and c.toughness is not None:
        parts.append(f" {c.power}/{c.toughness}")
    oracle = c.oracle_text.replace("\n", " / ")
    if len(oracle) > 120:
        oracle = oracle[:117] + "..."
    if oracle:
        parts.append(f" — {oracle}")
    parts.append(")")
    return "".join(parts)


def _build_selection_prompt(
    slot_candidates: dict[str, tuple[ReprintSlot, list[ReprintCandidate]]],
    set_config: dict,
    count: int,
) -> tuple[str, str]:
    """Build system and user prompts for the LLM reprint selection call."""
    system_prompt = (
        "You are an expert Magic: The Gathering set designer selecting reprints "
        "for a new set. You know all existing MTG cards and understand Limited "
        "format design, draft archetypes, and reprint selection strategy."
    )

    color_names = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}
    lines = [
        f"# Reprint Selection for {set_config.get('name', 'Unknown')}",
        f"**Theme**: {set_config.get('theme', 'Unknown')}",
        f"**Setting**: {set_config.get('flavor_description', 'No description')}",
    ]
    constraints = set_config.get("special_constraints", [])
    if constraints:
        lines.append(f"**Special**: {', '.join(constraints)}")
    lines.append("")
    lines.append(f"Select exactly **{count}** reprints from the candidates below.")
    lines.append("Each reprint fills one skeleton slot. Pick (slot, card) pairs that:")
    lines.append("1. Fill essential Limited roles (removal and mana fixing first)")
    lines.append("2. Synergize with the set's themes and mechanics")
    lines.append("3. Are well-known staples that players enjoy seeing reprinted")
    lines.append("4. Have setting-agnostic names that fit any world")
    lines.append("")
    lines.append("## Eligible Slots and Candidates")
    lines.append("")

    for slot_id in sorted(slot_candidates):
        slot, candidates = slot_candidates[slot_id]
        color_name = color_names.get(slot.color, slot.color)
        cmc_note = f", CMC ~{slot.cmc_target}" if slot.cmc_target else ""
        lines.append(
            f"### {slot.slot_id} ({color_name} {slot.rarity} {slot.card_type}"
            f"{cmc_note}, role: {slot.role_needed})"
        )
        for c in candidates:
            lines.append(f"- {format_candidate_tldr(c)}")
        lines.append("")

    return system_prompt, "\n".join(lines)


def _llm_select_reprints(
    slots: list[ReprintSlot],
    pool: list[ReprintCandidate],
    set_config: dict,
    count: int,
) -> list[SelectionPair]:
    """Use Haiku to select the best reprints from pre-filtered candidates.

    Pre-filters the pool per slot, builds a compact prompt with TLDRs, and
    calls Haiku with tool use. Cost: ~$0.002.
    """
    from mtgai.generation.llm_client import generate_with_tool

    # Pre-filter candidates per slot
    slot_candidates: dict[str, tuple[ReprintSlot, list[ReprintCandidate]]] = {}
    for slot in slots:
        filtered = pre_filter_for_slot(pool, slot)
        if filtered:
            slot_candidates[slot.slot_id] = (slot, filtered)

    if not slot_candidates:
        logger.warning("No candidates match any eligible slot after pre-filtering")
        return []

    logger.info(
        "Pre-filtered candidates for %d slots (of %d eligible)",
        len(slot_candidates),
        len(slots),
    )
    for slot_id, (slot, cands) in sorted(slot_candidates.items()):
        logger.info("  %s (%s %s): %d candidates", slot_id, slot.color, slot.card_type, len(cands))

    system_prompt, user_prompt = _build_selection_prompt(slot_candidates, set_config, count)

    tool_schema = {
        "name": "assign_reprints",
        "description": "Assign reprint cards to skeleton slots",
        "input_schema": {
            "type": "object",
            "properties": {
                "selections": {
                    "type": "array",
                    "description": f"Exactly {count} (slot, card) assignments",
                    "items": {
                        "type": "object",
                        "properties": {
                            "slot_id": {
                                "type": "string",
                                "description": "The slot ID (e.g. 'B-C-03')",
                            },
                            "card_name": {
                                "type": "string",
                                "description": "Exact card name from the candidates list",
                            },
                            "reason": {
                                "type": "string",
                                "description": "Brief reason this card is a good reprint here",
                            },
                        },
                        "required": ["slot_id", "card_name", "reason"],
                    },
                }
            },
            "required": ["selections"],
        },
    }

    logger.info(
        "Calling Haiku for reprint selection (%d slots, need %d)",
        len(slot_candidates),
        count,
    )

    try:
        from mtgai.runtime.active_project import require_active_project

        response = generate_with_tool(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tool_schema=tool_schema,
            model=require_active_project().settings.get_llm_model_id("reprints"),
            temperature=0.0,
            max_tokens=2048,
        )
    except Exception:
        logger.error("LLM reprint selection failed", exc_info=True)
        return []

    raw_selections = response.get("result", {}).get("selections", [])

    # Build lookups for matching
    name_to_candidate: dict[str, ReprintCandidate] = {}
    for pair in slot_candidates.values():
        for c in pair[1]:
            name_to_candidate[c.name.lower()] = c

    slot_by_id: dict[str, ReprintSlot] = {
        slot_id: slot for slot_id, (slot, _) in slot_candidates.items()
    }

    # Parse response
    selections: list[SelectionPair] = []
    for raw in raw_selections:
        slot_id = raw.get("slot_id", "")
        card_name = raw.get("card_name", "")
        reason = raw.get("reason", "")

        slot = slot_by_id.get(slot_id)
        if slot is None:
            logger.warning("LLM returned unknown slot_id: %s", slot_id)
            continue

        candidate = name_to_candidate.get(card_name.lower())
        if candidate is None:
            logger.warning("LLM returned unknown card name: %s", card_name)
            continue

        selections.append(SelectionPair(slot=slot, candidate=candidate, reason=reason))
        logger.info("  Selected: %s -> %s (%s)", candidate.name, slot.slot_id, reason)

    if len(selections) != count:
        logger.warning(
            "LLM returned %d valid selections, expected %d",
            len(selections),
            count,
        )

    return selections


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def select_reprints(
    skeleton_path: Path,
    set_config: dict | None = None,
    count: int | None = None,
    pool_path: Path | None = None,
) -> ReprintSelection:
    """Select reprints for a set — main entry point.

    If count is not specified, computes from set size: round(set_size * 0.028).
    Uses an LLM (Haiku) to pick the best reprints from the curated pool.
    """
    if set_config is None:
        set_config = extract_set_config(skeleton_path)

    set_size = set_config.get("set_size", 60)
    set_code = set_config.get("code", "???")

    if count is None:
        count = max(1, round(set_size * 0.028))

    logger.info(
        "Selecting %d reprints for %s (%d-card set)",
        count,
        set_code,
        set_size,
    )

    # Load and filter pool
    pool = load_reprint_pool(pool_path)
    total_pool = len(pool)
    pool = [c for c in pool if c.setting_agnostic is not False]
    filtered_out = total_pool - len(pool)
    if filtered_out > 0:
        logger.info(
            "Filtered out %d setting-specific candidates (%d remaining)",
            filtered_out,
            len(pool),
        )

    # Identify eligible slots
    slots = identify_reprint_slots(skeleton_path)

    # LLM selection
    selections = _llm_select_reprints(slots, pool, set_config, count)

    result = ReprintSelection(
        set_code=set_code,
        set_size=set_size,
        target_reprint_count=count,
        selections=selections,
        all_candidates_considered=total_pool,
        selection_timestamp=datetime.now(UTC).isoformat(),
    )

    logger.info(
        "Reprint selection complete: %d selected (target %d, considered %d candidates)",
        len(selections),
        count,
        total_pool,
    )

    return result


# ---------------------------------------------------------------------------
# Card conversion
# ---------------------------------------------------------------------------

_COLOR_MAP: dict[str, Color] = {
    "W": Color.WHITE,
    "U": Color.BLUE,
    "B": Color.BLACK,
    "R": Color.RED,
    "G": Color.GREEN,
}

_RARITY_MAP: dict[str, Rarity] = {
    "common": Rarity.COMMON,
    "uncommon": Rarity.UNCOMMON,
    "rare": Rarity.RARE,
    "mythic": Rarity.MYTHIC,
}


def _parse_card_types(type_line: str) -> tuple[list[str], list[str], list[str]]:
    """Parse a type line into (supertypes, card_types, subtypes)."""
    supertypes_set = {"Legendary", "Basic", "Snow", "World"}
    card_types_set = {
        "Creature",
        "Instant",
        "Sorcery",
        "Enchantment",
        "Artifact",
        "Planeswalker",
        "Land",
    }

    if " \u2014 " in type_line:
        main_part, sub_part = type_line.split(" \u2014 ", 1)
    elif " -- " in type_line:
        main_part, sub_part = type_line.split(" -- ", 1)
    else:
        main_part = type_line
        sub_part = ""

    words = main_part.strip().split()
    supertypes = [w for w in words if w in supertypes_set]
    card_types = [w for w in words if w in card_types_set]
    subtypes = sub_part.strip().split() if sub_part.strip() else []

    return supertypes, card_types, subtypes


def convert_to_card(
    candidate: ReprintCandidate,
    slot_id: str,
    set_code: str,
    collector_number: str,
) -> Card:
    """Convert a ReprintCandidate to a Card model instance.

    Sets is_reprint=True and fills all required Card fields.
    """
    colors = [_COLOR_MAP[c] for c in candidate.colors if c in _COLOR_MAP]
    rarity = _RARITY_MAP.get(candidate.rarity, Rarity.COMMON)
    supertypes, card_types, subtypes = _parse_card_types(candidate.type_line)

    return Card(
        name=candidate.name,
        mana_cost=candidate.mana_cost,
        cmc=candidate.cmc,
        colors=colors,
        color_identity=colors,
        type_line=candidate.type_line,
        supertypes=supertypes,
        card_types=card_types,
        subtypes=subtypes,
        oracle_text=candidate.oracle_text,
        power=candidate.power,
        toughness=candidate.toughness,
        collector_number=collector_number,
        rarity=rarity,
        set_code=set_code,
        is_reprint=True,
        slot_id=slot_id,
        design_notes=f"Reprint selected from {candidate.source} pool",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
