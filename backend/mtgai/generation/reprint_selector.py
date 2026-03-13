"""Reprint selection for MTG set generation.

Two selection strategies:
1. Staple reprints: deterministic role-based matching against curated pool ($0 LLM cost)
2. Splashy reprints: popularity-based selection from Scryfall data, with optional
   LLM thematic check via Haiku (~$0.002 per call)

Staple reprints filter out setting-specific cards (setting_agnostic=False) so that
only flavor-neutral cards make it into arbitrary set worlds.
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

# Role inference priority — higher-priority roles sort first in candidate lists
_ROLE_PRIORITY: dict[str, int] = {
    "removal_hard_kill": 1,
    "removal_damage": 2,
    "removal_exile": 3,
    "removal_fight": 4,
    "removal_bounce": 5,
    "removal_sweeper": 6,
    "counterspell": 7,
    "mana_fixing": 8,
    "artifact_removal": 9,
    "combat_trick": 10,
    "card_draw": 11,
    "ramp": 12,
    "utility_creature": 13,
    "lifegain": 14,
    "disruption": 15,
    "equipment": 16,
    "token_maker": 17,
    "aura": 18,
    "graveyard_recursion": 19,
    "self_mill": 20,
    "defensive": 21,
}

# Mechanic tags that indicate a slot can accept a reprint (no set-specific mechanic)
_REPRINT_ELIGIBLE_MECHANIC_TAGS = {"vanilla", "french_vanilla", "evergreen"}

# Card types most commonly reprinted
_REPRINT_ELIGIBLE_TYPES = {"instant", "sorcery", "creature", "enchantment", "artifact", "land"}


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
    score: float = 0.0
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    source: str  # "curated_pool" or "scryfall"
    edhrec_rank: int | None = None
    most_recent_set: str | None = None
    most_recent_date: str | None = None
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
    """A matched slot + candidate pair."""

    slot: ReprintSlot
    candidate: ReprintCandidate


class ReprintSelection(BaseModel):
    """Complete reprint selection result for a set."""

    set_code: str
    set_size: int
    target_reprint_count: int
    staple_selections: list[SelectionPair]
    splashy_selections: list[ReprintCandidate]
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
    """Read skeleton.json and build the set_config dict used by scoring functions.

    Returns a dict with keys: name, code, theme, themes, creature_types,
    special_constraints, set_size.
    """
    with open(skeleton_path, encoding="utf-8") as f:
        skeleton = json.load(f)

    config = skeleton.get("config", {})

    # Infer themes from flavor_description and special_constraints
    themes: list[str] = []
    flavor = config.get("flavor_description", "").lower()
    constraints = config.get("special_constraints", [])

    # Check common theme keywords in flavor text
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

    # Infer creature types from constraints and flavor
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
    """Infer the functional role needed for a skeleton slot.

    Heuristics based on color + type combinations that map to common
    reprint roles.
    """
    ct_lower = card_type.lower()

    # Land slots → mana fixing
    if ct_lower == "land" or (color == "colorless" and ct_lower == "land"):
        return "mana_fixing"

    # Colorless artifact → could be many things, but utility creature or artifact_removal
    if color == "colorless" and ct_lower == "artifact":
        return "utility_creature"

    # Creature with vanilla/french_vanilla → utility creature
    if ct_lower == "creature" and mechanic_tag in ("vanilla", "french_vanilla"):
        return "utility_creature"

    # Spell-based role inference by color
    if ct_lower in ("instant", "sorcery"):
        if color == "B":
            return "removal_hard_kill"
        if color == "R":
            return "removal_damage"
        if color == "W":
            if cmc is not None and cmc <= 3:
                return "combat_trick"
            return "removal_exile"
        if color == "U":
            if cmc is not None and cmc <= 2:
                return "counterspell"
            return "removal_bounce"
        if color == "G":
            if cmc is not None and cmc <= 2:
                return "removal_fight"
            return "combat_trick"

    # Enchantment by color
    if ct_lower == "enchantment":
        if color == "W":
            return "removal_exile"
        if color == "G":
            return "artifact_removal"
        return "utility_creature"

    # Creature with evergreen → utility creature
    if ct_lower == "creature":
        return "utility_creature"

    # Fallback
    return "utility_creature"


def identify_reprint_slots(skeleton_path: Path) -> list[ReprintSlot]:
    """Read skeleton.json and identify slots eligible for reprints.

    A slot is eligible if:
    - mechanic_tag is in {vanilla, french_vanilla, evergreen}
    - card_type is a commonly reprinted type
    - NOT already assigned (card_id is null)

    Returns slots sorted by role priority (removal first).
    """
    with open(skeleton_path, encoding="utf-8") as f:
        skeleton = json.load(f)

    slots: list[ReprintSlot] = []
    for slot_data in skeleton.get("slots", []):
        mechanic_tag = slot_data.get("mechanic_tag", "")
        card_type = slot_data.get("card_type", "")
        card_id = slot_data.get("card_id")

        # Skip slots that already have a card assigned
        if card_id is not None:
            continue

        # Skip slots with set-specific mechanics
        if mechanic_tag not in _REPRINT_ELIGIBLE_MECHANIC_TAGS:
            continue

        # Skip unusual card types
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

    # Sort by role priority
    slots.sort(key=lambda s: _ROLE_PRIORITY.get(s.role_needed, 99))

    logger.info(
        "Identified %d reprint-eligible slots from skeleton (%d total slots)",
        len(slots),
        len(skeleton.get("slots", [])),
    )
    for s in slots:
        logger.debug(
            "  Slot %s: %s %s %s -> role=%s",
            s.slot_id,
            s.color,
            s.rarity,
            s.card_type,
            s.role_needed,
        )

    return slots


# ---------------------------------------------------------------------------
# Staple scoring
# ---------------------------------------------------------------------------


def _color_matches(candidate_colors: list[str], slot_color: str) -> bool:
    """Check if a candidate's colors match a slot's color requirement."""
    if slot_color == "colorless":
        return len(candidate_colors) == 0
    if slot_color == "multicolor":
        return len(candidate_colors) >= 2
    # Mono-color slot
    return candidate_colors == [slot_color]


def _type_matches(candidate_type_line: str, slot_card_type: str) -> bool:
    """Check if a candidate's type line is compatible with the slot's card type."""
    ct_lower = candidate_type_line.lower()
    st_lower = slot_card_type.lower()

    # Direct match
    if st_lower in ct_lower:
        return True

    # "Enchantment Creature" matches both "creature" and "enchantment" slots
    if st_lower == "creature" and "creature" in ct_lower:
        return True
    if st_lower == "enchantment" and "enchantment" in ct_lower:
        return True
    return st_lower == "artifact" and "artifact" in ct_lower


def score_staple_candidate(
    candidate: ReprintCandidate,
    slot: ReprintSlot,
    set_config: dict,
) -> float:
    """Score a curated pool candidate against a specific slot.

    Returns a 0.0-1.0 composite score. Candidates that fail hard
    requirements (color mismatch, rarity mismatch) score 0.0.
    """
    breakdown: dict[str, float] = {}

    # --- Hard requirements (must match) ---
    if not _color_matches(candidate.colors, slot.color):
        return 0.0

    if candidate.rarity != slot.rarity:
        return 0.0

    if not _type_matches(candidate.type_line, slot.card_type):
        return 0.0

    # --- Role match (40% weight) ---
    if candidate.role == slot.role_needed:
        breakdown["role_match"] = 0.40
    elif candidate.role.startswith("removal") and slot.role_needed.startswith("removal"):
        # Partial match: any removal for any removal slot
        breakdown["role_match"] = 0.25
    else:
        breakdown["role_match"] = 0.0

    # --- CMC proximity (25% weight) ---
    if slot.cmc_target is not None:
        cmc_diff = abs(candidate.cmc - slot.cmc_target)
        if cmc_diff == 0:
            breakdown["cmc_proximity"] = 0.25
        elif cmc_diff <= 1:
            breakdown["cmc_proximity"] = 0.18
        elif cmc_diff <= 2:
            breakdown["cmc_proximity"] = 0.10
        else:
            breakdown["cmc_proximity"] = 0.0
    else:
        breakdown["cmc_proximity"] = 0.15  # No target → moderate score

    # --- Popularity / EDHREC (20% weight) ---
    if candidate.edhrec_rank is not None:
        if candidate.edhrec_rank < 1000:
            breakdown["popularity"] = 0.20
        elif candidate.edhrec_rank < 3000:
            breakdown["popularity"] = 0.15
        elif candidate.edhrec_rank < 5000:
            breakdown["popularity"] = 0.10
        elif candidate.edhrec_rank < 10000:
            breakdown["popularity"] = 0.05
        else:
            breakdown["popularity"] = 0.0
    else:
        breakdown["popularity"] = 0.05

    # --- Thematic fit (15% weight) ---
    thematic_score = 0.0
    themes = set_config.get("themes", [])
    creature_types = set_config.get("creature_types", [])

    # Artifact theme bonus
    if "artifact" in themes and ("artifact" in candidate.tags or "Artifact" in candidate.type_line):
        thematic_score += 0.08
    # Creature type overlap
    for ct in creature_types:
        if ct in candidate.subtypes:
            thematic_score += 0.05
            break
    # Tag overlap with themes
    for theme in themes:
        if theme in candidate.tags:
            thematic_score += 0.03
            break

    breakdown["thematic_fit"] = min(thematic_score, 0.15)

    score = sum(breakdown.values())
    candidate.score_breakdown = breakdown
    candidate.score = round(score, 4)
    return score


# ---------------------------------------------------------------------------
# Staple selection
# ---------------------------------------------------------------------------


def select_staple_reprints(
    skeleton_path: Path,
    set_config: dict,
    count: int,
    pool_path: Path | None = None,
) -> list[SelectionPair]:
    """Select staple reprints by matching curated pool against skeleton slots.

    Uses greedy assignment: score all (candidate, slot) pairs, pick the
    highest-scoring pair, remove that candidate and slot, repeat.
    """
    pool = load_reprint_pool(pool_path)
    slots = identify_reprint_slots(skeleton_path)

    if not slots:
        logger.warning("No reprint-eligible slots found in skeleton")
        return []

    if not pool:
        logger.warning("Reprint pool is empty")
        return []

    # Filter out setting-specific cards
    total_before = len(pool)
    pool = [c for c in pool if c.setting_agnostic is not False]
    filtered_count = total_before - len(pool)
    if filtered_count > 0:
        logger.info(
            "Filtered out %d setting-specific candidates (%d remaining)",
            filtered_count,
            len(pool),
        )

    logger.info(
        "Scoring %d candidates against %d eligible slots (need %d selections)",
        len(pool),
        len(slots),
        count,
    )

    # Score all pairs
    scored_pairs: list[tuple[float, int, int]] = []  # (score, slot_idx, cand_idx)
    for si, slot in enumerate(slots):
        for ci, cand in enumerate(pool):
            sc = score_staple_candidate(
                # Make a copy so scoring doesn't mutate the original
                cand.model_copy(),
                slot,
                set_config,
            )
            if sc > 0:
                scored_pairs.append((sc, si, ci))

    # Sort descending by score
    scored_pairs.sort(key=lambda x: x[0], reverse=True)

    # Greedy assignment
    used_slots: set[int] = set()
    used_candidates: set[int] = set()
    selections: list[SelectionPair] = []

    for _sc, si, ci in scored_pairs:
        if len(selections) >= count:
            break
        if si in used_slots or ci in used_candidates:
            continue

        # Re-score with original candidate (to store breakdown)
        cand = pool[ci].model_copy()
        score_staple_candidate(cand, slots[si], set_config)

        selections.append(SelectionPair(slot=slots[si], candidate=cand))
        used_slots.add(si)
        used_candidates.add(ci)

        logger.info(
            "  Selected: %s (%.3f) -> slot %s (%s %s %s)",
            cand.name,
            cand.score,
            slots[si].slot_id,
            slots[si].color,
            slots[si].rarity,
            slots[si].role_needed,
        )

    logger.info("Selected %d staple reprints out of %d requested", len(selections), count)
    return selections


# ---------------------------------------------------------------------------
# Splashy scoring
# ---------------------------------------------------------------------------


def score_splashy_candidate(
    card_data: dict,
    set_config: dict,
    reference_date: str,
) -> tuple[float, dict[str, float]]:
    """Score a Scryfall card for 'splashy reprint' potential.

    Scoring weights:
    - Popularity (30%): based on edhrec_rank
    - Age (25%): years since released_at
    - Price (15%): USD market price signal
    - Thematic fit (20%): rule-based matching against set themes
    - Rarity match (10%): rare = 0.8, mythic = 1.0

    Returns (score, breakdown) tuple.
    """
    breakdown: dict[str, float] = {}

    # --- Popularity (30%) ---
    edhrec = card_data.get("edhrec_rank")
    if edhrec is not None:
        if edhrec < 1000:
            breakdown["popularity"] = 0.30
        elif edhrec < 3000:
            breakdown["popularity"] = 0.21
        elif edhrec < 5000:
            breakdown["popularity"] = 0.12
        elif edhrec < 10000:
            breakdown["popularity"] = 0.06
        else:
            breakdown["popularity"] = 0.0
    else:
        breakdown["popularity"] = 0.0

    # --- Age (25%) ---
    released = card_data.get("released_at", "")
    if released:
        try:
            release_date = datetime.strptime(released, "%Y-%m-%d").replace(tzinfo=UTC)
            ref = datetime.strptime(reference_date, "%Y-%m-%d").replace(tzinfo=UTC)
            years = (ref - release_date).days / 365.25
            if years >= 5:
                breakdown["age"] = 0.25
            elif years >= 3:
                breakdown["age"] = 0.18
            elif years >= 1:
                breakdown["age"] = 0.08
            else:
                breakdown["age"] = 0.0
        except ValueError:
            breakdown["age"] = 0.0
    else:
        breakdown["age"] = 0.0

    # --- Price signal (15%) ---
    prices = card_data.get("prices", {})
    usd_str = prices.get("usd") if prices else None
    if usd_str is not None:
        try:
            usd = float(usd_str)
            if usd >= 20:
                breakdown["price"] = 0.15
            elif usd >= 10:
                breakdown["price"] = 0.12
            elif usd >= 5:
                breakdown["price"] = 0.08
            elif usd >= 2:
                breakdown["price"] = 0.04
            else:
                breakdown["price"] = 0.0
        except ValueError:
            breakdown["price"] = 0.0
    else:
        breakdown["price"] = 0.0

    # --- Thematic fit (20%) ---
    thematic = 0.0
    themes = set_config.get("themes", [])
    creature_types = set_config.get("creature_types", [])
    type_line = card_data.get("type_line", "")
    oracle_text = card_data.get("oracle_text", "")
    # Artifact theme
    if "artifact" in themes:
        if "Artifact" in type_line:
            thematic += 0.10
        if "artifact" in oracle_text.lower():
            thematic += 0.05

    # Creature type overlap
    for ct in creature_types:
        if ct in type_line:
            thematic += 0.08
            break

    # Keyword overlap with set themes
    if "dinosaur" in themes and "Dinosaur" in type_line:
        thematic += 0.08

    # Generic oracle text thematic hints
    theme_text_hints = {
        "megadungeon": ["explore", "dungeon", "venture"],
        "science-fantasy": ["artifact", "construct"],
        "post-apocalyptic": ["sacrifice", "destroy", "ruin"],
        "graveyard": ["graveyard", "return from your graveyard"],
    }
    for theme in themes:
        for hint in theme_text_hints.get(theme, []):
            if hint in oracle_text.lower():
                thematic += 0.03
                break

    breakdown["thematic_fit"] = min(thematic, 0.20)

    # --- Rarity (10%) ---
    rarity = card_data.get("rarity", "")
    if rarity == "mythic":
        breakdown["rarity"] = 0.10
    elif rarity == "rare":
        breakdown["rarity"] = 0.08
    else:
        breakdown["rarity"] = 0.0

    return round(sum(breakdown.values()), 4), breakdown


# ---------------------------------------------------------------------------
# LLM thematic check for splashy reprints
# ---------------------------------------------------------------------------


def _llm_check_splashy_fit(
    candidates: list[ReprintCandidate],
    set_config: dict,
) -> list[ReprintCandidate]:
    """Ask Haiku which splashy candidates fit the set's theme/world.

    Sends the top candidates to Haiku with the set's flavor description.
    Returns only candidates that Haiku approves as thematically fitting.
    Cost: ~$0.002 per call.
    """
    from mtgai.generation.llm_client import generate_with_tool

    system_prompt = (
        "You are a Magic: The Gathering set designer evaluating whether existing "
        "cards would thematically fit as reprints in a new set. Focus on whether "
        "each card's NAME, creature types, and identity would feel at home in the "
        "described setting. Ignore mechanical fit — focus purely on flavor/theme."
    )

    # Build card list for the user prompt
    card_lines: list[str] = []
    for i, c in enumerate(candidates, 1):
        oracle_brief = c.oracle_text[:120] + "..." if len(c.oracle_text) > 120 else c.oracle_text
        card_lines.append(f"{i}. {c.name} — {c.type_line} — {oracle_brief}")

    user_prompt = (
        f"Set: {set_config.get('name', 'Unknown')}\n"
        f"Theme: {set_config.get('theme', 'Unknown')}\n"
        f"Flavor: {set_config.get('flavor_description', 'No description')}\n\n"
        f"Which of these cards would thematically fit as reprints in this set?\n\n"
        + "\n".join(card_lines)
        + "\n\nEvaluate each card's thematic fit."
    )

    tool_schema = {
        "name": "evaluate_thematic_fit",
        "description": "Evaluate which cards fit thematically in the set",
        "input_schema": {
            "type": "object",
            "properties": {
                "evaluations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "card_number": {
                                "type": "integer",
                                "description": "1-indexed card number from the list",
                            },
                            "fits": {
                                "type": "boolean",
                                "description": (
                                    "Whether the card's name and identity fit this setting"
                                ),
                            },
                            "reason": {
                                "type": "string",
                                "description": "Brief explanation",
                            },
                        },
                        "required": ["card_number", "fits", "reason"],
                    },
                }
            },
            "required": ["evaluations"],
        },
    }

    try:
        response = generate_with_tool(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tool_schema=tool_schema,
            model="claude-haiku-4-5-20251001",
            temperature=0.0,
            max_tokens=2048,
        )
    except Exception:
        logger.warning(
            "LLM thematic check failed, returning candidates unchanged",
            exc_info=True,
        )
        return candidates

    evaluations = response.get("result", {}).get("evaluations", [])

    # Log all evaluations
    for ev in evaluations:
        card_num = ev.get("card_number", 0)
        fits = ev.get("fits", False)
        reason = ev.get("reason", "")
        card_name = (
            candidates[card_num - 1].name if 1 <= card_num <= len(candidates) else f"?#{card_num}"
        )
        logger.info(
            "  Thematic check: %s -> %s (%s)",
            card_name,
            "FITS" if fits else "DOES NOT FIT",
            reason,
        )

    # Build set of approved card numbers
    approved_nums: set[int] = set()
    for ev in evaluations:
        if ev.get("fits", False):
            approved_nums.add(ev.get("card_number", 0))

    approved = [c for i, c in enumerate(candidates, 1) if i in approved_nums]
    logger.info(
        "LLM thematic check: %d/%d candidates approved",
        len(approved),
        len(candidates),
    )
    return approved


# ---------------------------------------------------------------------------
# Splashy selection
# ---------------------------------------------------------------------------


def _load_scryfall_cards(scryfall_data_dir: Path) -> list[dict]:
    """Load all card data from reference Scryfall JSON files."""
    all_cards: list[dict] = []
    if not scryfall_data_dir.exists():
        logger.warning("Scryfall data directory does not exist: %s", scryfall_data_dir)
        return all_cards

    for set_dir in sorted(scryfall_data_dir.iterdir()):
        cards_file = set_dir / "cards.json"
        if cards_file.exists():
            with open(cards_file, encoding="utf-8") as f:
                cards = json.load(f)
            logger.info("Loaded %d cards from %s", len(cards), set_dir.name)
            all_cards.extend(cards)

    logger.info("Total Scryfall cards loaded: %d", len(all_cards))
    return all_cards


def select_splashy_reprints(
    scryfall_data_dir: Path,
    set_config: dict,
    count: int = 2,
    min_edhrec_rank: int = 5000,
    min_age_years: float = 2,
    use_llm_filter: bool = True,
) -> list[ReprintCandidate]:
    """Select splashy (rare/mythic) reprints from Scryfall reference data.

    Filters for cards that:
    - Are reprints (have been printed before)
    - Are rare or mythic
    - Have an edhrec_rank (popularity proxy)
    - Meet minimum age threshold

    Returns top `count` candidates by composite score.
    """
    all_cards = _load_scryfall_cards(scryfall_data_dir)
    if not all_cards:
        logger.warning("No Scryfall data available for splashy reprint selection")
        return []

    reference_date = datetime.now(UTC).strftime("%Y-%m-%d")

    # Deduplicate by name (keep most recent printing)
    by_name: dict[str, dict] = {}
    for card in all_cards:
        name = card.get("name", "")
        if name in by_name:
            existing_date = by_name[name].get("released_at", "")
            new_date = card.get("released_at", "")
            if new_date > existing_date:
                by_name[name] = card
        else:
            by_name[name] = card

    # Filter
    candidates: list[tuple[float, dict]] = []
    for card in by_name.values():
        # Must be a reprint
        if not card.get("reprint", False):
            continue

        # Must be rare or mythic
        rarity = card.get("rarity", "")
        if rarity not in ("rare", "mythic"):
            continue

        # Must have edhrec rank and be popular enough
        edhrec = card.get("edhrec_rank")
        if edhrec is None or edhrec > min_edhrec_rank:
            continue

        # Must meet age threshold
        released = card.get("released_at", "")
        if released:
            try:
                release_date = datetime.strptime(released, "%Y-%m-%d").replace(tzinfo=UTC)
                ref = datetime.strptime(reference_date, "%Y-%m-%d").replace(tzinfo=UTC)
                years = (ref - release_date).days / 365.25
                if years < min_age_years:
                    continue
            except ValueError:
                continue
        else:
            continue

        # Skip double-faced / complex layouts for simplicity
        layout = card.get("layout", "normal")
        if layout not in ("normal", ""):
            continue

        score, bd = score_splashy_candidate(card, set_config, reference_date)
        card["_score_breakdown"] = bd
        candidates.append((score, card))

    logger.info(
        "Splashy reprint candidates after filtering: %d (from %d unique cards)",
        len(candidates),
        len(by_name),
    )

    # Sort by score descending
    candidates.sort(key=lambda x: x[0], reverse=True)

    # Log top candidates
    for sc, card in candidates[:10]:
        logger.info(
            "  Splashy candidate: %s (%.3f) [edhrec=%s, rarity=%s, set=%s]",
            card.get("name"),
            sc,
            card.get("edhrec_rank"),
            card.get("rarity"),
            card.get("set"),
        )

    # Convert top candidates to ReprintCandidate
    # If LLM filter is enabled, give Haiku more to choose from
    top_n = max(count * 2, 5) if use_llm_filter else count
    results: list[ReprintCandidate] = []
    for sc, card in candidates[:top_n]:
        results.append(
            ReprintCandidate(
                name=card.get("name", ""),
                mana_cost=card.get("mana_cost") or None,
                cmc=float(card.get("cmc", 0)),
                type_line=card.get("type_line", ""),
                oracle_text=card.get("oracle_text", ""),
                colors=card.get("colors", []),
                rarity=card.get("rarity", ""),
                role="splashy_reprint",
                score=sc,
                score_breakdown=card.get("_score_breakdown", {}),
                source="scryfall",
                edhrec_rank=card.get("edhrec_rank"),
                most_recent_set=card.get("set"),
                most_recent_date=card.get("released_at"),
                keywords=card.get("keywords", []),
                subtypes=_extract_subtypes(card.get("type_line", "")),
                tags=["splashy", "nostalgia"],
                power=card.get("power"),
                toughness=card.get("toughness"),
            )
        )

    # Apply LLM thematic filter if enabled
    if use_llm_filter and results:
        results = _llm_check_splashy_fit(results, set_config)
        results = results[:count]
    else:
        results = results[:count]

    logger.info("Selected %d splashy reprints", len(results))
    return results


def _extract_subtypes(type_line: str) -> list[str]:
    """Extract subtypes from a type line like 'Creature -- Elf Druid'."""
    if " -- " in type_line:
        return type_line.split(" -- ", 1)[1].strip().split()
    if " \u2014 " in type_line:
        return type_line.split(" \u2014 ", 1)[1].strip().split()
    return []


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def select_reprints(
    skeleton_path: Path,
    scryfall_data_dir: Path,
    set_config: dict | None = None,
    staple_count: int | None = None,
    splashy_count: int | None = None,
    pool_path: Path | None = None,
    use_llm_filter: bool = True,
) -> ReprintSelection:
    """Select reprints for a set — main entry point.

    If counts are not specified, computes from set size using the formula
    from set-template.json: reprint_count = round(set_size * 0.028).
    """
    if set_config is None:
        set_config = extract_set_config(skeleton_path)

    set_size = set_config.get("set_size", 60)
    set_code = set_config.get("code", "???")

    total_reprint_count = round(set_size * 0.028)
    # Ensure at least 1 reprint for any set
    total_reprint_count = max(1, total_reprint_count)

    if splashy_count is None:
        splashy_count = min(2, total_reprint_count // 4)

    if staple_count is None:
        staple_count = total_reprint_count - splashy_count

    logger.info(
        "Selecting reprints for %s: %d total (%d staple, %d splashy) from %d-card set",
        set_code,
        total_reprint_count,
        staple_count,
        splashy_count,
        set_size,
    )

    # Select staple reprints
    staple_selections = select_staple_reprints(
        skeleton_path, set_config, staple_count, pool_path=pool_path
    )

    # Select splashy reprints
    splashy_selections = select_splashy_reprints(
        scryfall_data_dir, set_config, count=splashy_count, use_llm_filter=use_llm_filter
    )

    # Count total candidates considered
    pool = load_reprint_pool(pool_path)
    scryfall_cards = _load_scryfall_cards(scryfall_data_dir)
    total_considered = len(pool) + len(scryfall_cards)

    result = ReprintSelection(
        set_code=set_code,
        set_size=set_size,
        target_reprint_count=total_reprint_count,
        staple_selections=staple_selections,
        splashy_selections=splashy_selections,
        all_candidates_considered=total_considered,
        selection_timestamp=datetime.now(UTC).isoformat(),
    )

    logger.info(
        "Reprint selection complete: %d staple + %d splashy = %d total "
        "(target was %d, considered %d candidates)",
        len(staple_selections),
        len(splashy_selections),
        len(staple_selections) + len(splashy_selections),
        total_reprint_count,
        total_considered,
    )

    return result


# ---------------------------------------------------------------------------
# Card conversion
# ---------------------------------------------------------------------------

# Color string to Color enum mapping
_COLOR_MAP: dict[str, Color] = {
    "W": Color.WHITE,
    "U": Color.BLUE,
    "B": Color.BLACK,
    "R": Color.RED,
    "G": Color.GREEN,
}

# Rarity string to Rarity enum mapping
_RARITY_MAP: dict[str, Rarity] = {
    "common": Rarity.COMMON,
    "uncommon": Rarity.UNCOMMON,
    "rare": Rarity.RARE,
    "mythic": Rarity.MYTHIC,
}


def _parse_card_types(type_line: str) -> tuple[list[str], list[str], list[str]]:
    """Parse a type line into (supertypes, card_types, subtypes).

    Example: 'Legendary Creature -- Elf Druid' ->
             (['Legendary'], ['Creature'], ['Elf', 'Druid'])
    """
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

    # Split on em-dash or double-dash
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
        color_identity=colors,  # For reprints, color identity == colors
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
        design_notes=f"Reprint selected via {candidate.source} (score={candidate.score:.3f})",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
