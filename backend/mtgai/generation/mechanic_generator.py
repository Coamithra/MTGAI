"""Mechanic candidate generation — driven by ``theme.json`` + ``set_params``.

Wired into the pipeline as the ``mechanics`` stage (first entry in
``STAGE_RUNNERS``). The runner in ``mtgai.pipeline.stages`` does the
orchestration; this module owns the prompt assembly, tool-schema
contract, post-processing (color pie + known-keyword collision check),
and the sidecar generators that the wizard's save handler invokes.

Templates live next door:

* ``mtgai/pipeline/prompts/mechanic_system.txt`` — system prompt
* ``mtgai/pipeline/prompts/mechanic_user.txt``   — user prompt
* ``mtgai/pipeline/templates/mtg_known_keywords.json`` — collision list
* ``mtgai/pipeline/templates/evergreen_keywords.json`` — per-color defaults
* ``mtgai/pipeline/templates/pointed_questions.json``  — review questions
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from mtgai.generation.llm_client import generate_with_tool

logger = logging.getLogger(__name__)

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent / "pipeline"
_PROMPTS_DIR = _PIPELINE_ROOT / "prompts"
_TEMPLATES_DIR = _PIPELINE_ROOT / "templates"

CANDIDATE_COUNT = 6

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
                        "distribution",
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
                            "description": "Reminder text in parentheses, under 100 chars",
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
                            "description": "1=common-viable, 2=uncommon+, 3=rare+",
                        },
                        "flavor_connection": {
                            "type": "string",
                            "description": "How the mechanic connects to set flavor",
                        },
                        "design_rationale": {
                            "type": "string",
                            "description": "Why this mechanic is good for the set",
                        },
                        "common_patterns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Rules text patterns for common cards",
                        },
                        "uncommon_patterns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Rules text patterns for uncommon cards",
                        },
                        "rare_patterns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Rules text patterns for rare/mythic cards",
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
                        "distribution": {
                            "type": "object",
                            "required": ["common", "uncommon", "rare", "mythic"],
                            "description": (
                                "Approximate slot counts per rarity for this mechanic. "
                                "Should sum to roughly the set's mechanic-density target."
                            ),
                            "properties": {
                                "common": {"type": "integer", "minimum": 0},
                                "uncommon": {"type": "integer", "minimum": 0},
                                "rare": {"type": "integer", "minimum": 0},
                                "mythic": {"type": "integer", "minimum": 0},
                            },
                        },
                    },
                },
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


def _read_template(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def _format_archetypes_block(archetypes: list[Any]) -> str:
    """Render the draft-archetype list for the system prompt."""
    if not archetypes:
        return "(no archetypes specified — design mechanics that work across colors)"
    lines: list[str] = []
    for arch in archetypes:
        if not isinstance(arch, dict):
            continue
        colors = arch.get("color_pair") or arch.get("colors") or ""
        name = arch.get("name") or ""
        desc = arch.get("description") or ""
        if name and desc:
            lines.append(f"- {colors}: {name} — {desc}".lstrip())
        elif name:
            lines.append(f"- {colors}: {name}".lstrip())
    return "\n".join(lines) if lines else "(no archetypes specified)"


def _format_creature_types_block(creature_types: list[Any]) -> str:
    if not creature_types:
        return "(no specific creature types called out)"
    names: list[str] = []
    for ct in creature_types:
        if isinstance(ct, str):
            names.append(ct)
        elif isinstance(ct, dict):
            n = ct.get("name") or ct.get("type")
            if n:
                names.append(str(n))
    return ", ".join(names) if names else "(no specific creature types called out)"


def _format_constraints_block(constraints: list[Any]) -> str:
    if not constraints:
        return "(no special constraints)"
    lines: list[str] = []
    for c in constraints:
        text = c.get("text") if isinstance(c, dict) else c
        if text:
            lines.append(f"- {text}")
    return "\n".join(lines) if lines else "(no special constraints)"


def _format_characters_block(theme: dict) -> str:
    """Surface legendary characters + notable cards so the LLM avoids name collisions."""
    parts: list[str] = []
    legends = theme.get("legendary_characters") or []
    notable = theme.get("notable_cards") or []
    char_names: list[str] = []
    for entry in legends:
        if isinstance(entry, dict):
            n = entry.get("name")
            if n:
                char_names.append(str(n))
        elif isinstance(entry, str):
            char_names.append(entry)
    card_names: list[str] = []
    for entry in notable:
        if isinstance(entry, dict):
            n = entry.get("name") or entry.get("text")
            if n:
                card_names.append(str(n))
        elif isinstance(entry, str):
            card_names.append(entry)
    if char_names:
        parts.append("Legendary characters: " + ", ".join(char_names))
    if card_names:
        parts.append("Notable cards: " + ", ".join(card_names))
    return "\n".join(parts) if parts else "(none)"


def _expected_mechanic_density(set_size: int, mechanic_count: int) -> str:
    """Rough target for cards-per-mechanic in this set.

    Total set / (mechanic_count * 2) — about half the set carries
    custom mechanics, the rest is reprints + lands + non-mechanic
    designs. Returned as a "min-max" string the prompt drops into
    its design constraints.
    """
    if mechanic_count <= 0:
        return "6-10"
    per = max(1, set_size // (mechanic_count * 2))
    return f"{per}-{per * 2}"


def _format_excluded_keywords(known: dict) -> str:
    """Comma-separated list across every known-keyword bucket."""
    items: list[str] = []
    for bucket in ("evergreen", "deciduous", "set_keywords", "ability_words", "token_keywords"):
        items.extend(known.get(bucket, []))
    seen: set[str] = set()
    out: list[str] = []
    for k in items:
        kl = k.lower()
        if kl not in seen:
            seen.add(kl)
            out.append(k)
    return ", ".join(out)


def build_mechanic_prompts(
    theme: dict,
    set_name: str,
    set_size: int,
    mechanic_count: int,
) -> tuple[str, str]:
    """Render the mechanic-generation system + user prompts from theme + params."""
    sys_template = _read_template("mechanic_system.txt")
    user_template = _read_template("mechanic_user.txt")
    known = load_known_keywords()
    expected_density = _expected_mechanic_density(set_size, mechanic_count)

    system_prompt = sys_template.format(
        set_name=set_name or "(unnamed set)",
        set_size=set_size,
        mechanic_count=mechanic_count,
        theme=(theme.get("theme") or theme.get("setting") or "(no theme provided)").strip(),
        flavor_description=(theme.get("flavor_description") or "").strip()
        or "(no flavor description provided)",
        archetypes_block=_format_archetypes_block(theme.get("draft_archetypes") or []),
        creature_types_block=_format_creature_types_block(theme.get("creature_types") or []),
        constraints_block=_format_constraints_block(
            theme.get("constraints") or theme.get("special_constraints") or []
        ),
        characters_block=_format_characters_block(theme),
        excluded_keywords=_format_excluded_keywords(known),
        expected_mechanic_density=expected_density,
    )
    user_prompt = user_template.format(
        mechanic_count=mechanic_count,
        set_size=set_size,
        expected_mechanic_density=expected_density,
    )
    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Template loaders
# ---------------------------------------------------------------------------


def load_known_keywords() -> dict[str, list[str]]:
    """Per-bucket list of MTG keywords + ability words.

    Buckets: ``evergreen``, ``deciduous``, ``set_keywords``,
    ``ability_words``, ``token_keywords``.
    """
    path = _TEMPLATES_DIR / "mtg_known_keywords.json"
    return json.loads(path.read_text(encoding="utf-8"))


def known_keyword_set() -> set[str]:
    """Lowercase set of every known printed keyword for collision checks."""
    out: set[str] = set()
    for bucket in load_known_keywords().values():
        for k in bucket:
            out.add(k.lower())
    return out


def load_evergreen_defaults() -> dict[str, list[str]]:
    """Per-color default evergreen keyword list — written as a sidecar."""
    path = _TEMPLATES_DIR / "evergreen_keywords.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_pointed_questions_template() -> list[dict]:
    """Canonical questions with ``{mechanic_names}`` placeholder."""
    path = _TEMPLATES_DIR / "pointed_questions.json"
    return json.loads(path.read_text(encoding="utf-8"))


def render_pointed_questions(approved: list[dict]) -> list[dict]:
    """Substitute ``{mechanic_names}`` with the joined approved-mechanic names.

    Output shape matches what ``review/ai_review.py`` expects from the
    on-disk file — same keys, same types, just with the placeholders
    resolved per project.
    """
    names = ", ".join(m.get("name", "?") for m in approved)
    out: list[dict] = []
    for q in load_pointed_questions_template():
        rendered = dict(q)
        text = rendered.get("question", "")
        if "{mechanic_names}" in text:
            rendered["question"] = text.replace("{mechanic_names}", names)
        out.append(rendered)
    return out


# ---------------------------------------------------------------------------
# Color pie validation (kept; still useful for the candidates strip)
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

    all_text_parts = [
        mechanic.get("reminder_text", ""),
        mechanic.get("design_rationale", ""),
    ]
    for pattern_key in ("common_patterns", "uncommon_patterns", "rare_patterns"):
        all_text_parts.extend(mechanic.get(pattern_key, []))
    for card in mechanic.get("example_cards", []):
        all_text_parts.append(card.get("oracle_text", ""))
    all_text = " ".join(all_text_parts).lower()

    for effect_name, keywords in EFFECT_KEYWORDS.items():
        if any(kw in all_text for kw in keywords):
            pie = COLOR_PIE.get(effect_name, {})
            has_primary_or_secondary = any(pie.get(c) in ("P", "S") for c in colors)
            if not has_primary_or_secondary and pie:
                has_tertiary = any(pie.get(c) == "T" for c in colors)
                if has_tertiary:
                    warnings.append(
                        f"WARN: '{effect_name}' is only tertiary in {colors} — use sparingly"
                    )
                else:
                    warnings.append(
                        f"NOTE: '{effect_name}' detected in text but not "
                        f"primary/secondary in {colors} — verify intent"
                    )

    reminder = mechanic.get("reminder_text", "")
    if len(reminder) > 100:
        warnings.append(f"ERROR: Reminder text is {len(reminder)} chars (max 100)")

    complexity = mechanic.get("complexity", 1)
    if complexity == 1 and not mechanic.get("common_patterns"):
        warnings.append("WARN: Complexity 1 mechanic should have common patterns")

    return warnings


def detect_keyword_collisions(candidates: list[dict]) -> dict[int, str]:
    """Flag candidates whose name collides with a printed MTG keyword.

    Returns ``{candidate_index: collision_keyword}`` so the wizard can
    surface the warning per-card without filtering — the user might still
    want to keep the candidate and rename it inline.
    """
    known = known_keyword_set()
    out: dict[int, str] = {}
    for idx, mech in enumerate(candidates):
        name = (mech.get("name") or "").strip()
        if not name:
            continue
        if name.lower() in known:
            out[idx] = name
    return out


# ---------------------------------------------------------------------------
# approved.json projection
# ---------------------------------------------------------------------------


_APPROVED_FIELDS: tuple[str, ...] = (
    "name",
    "keyword_type",
    "reminder_text",
    "colors",
    "complexity",
    "flavor_connection",
    "common_patterns",
    "uncommon_patterns",
    "rare_patterns",
    "distribution",
)


def candidate_to_approved(candidate: dict) -> dict:
    """Project a candidate dict to the on-disk ``approved.json`` shape.

    * Renames ``design_rationale`` → ``design_notes`` (downstream
      consumers read ``design_notes``).
    * Drops ``example_cards`` (UI-only).
    * Synthesises ``rarity_range`` from non-zero ``distribution`` rarities
      so AI-review prompts have it.
    """
    out: dict = {}
    for key in _APPROVED_FIELDS:
        if key in candidate:
            out[key] = candidate[key]
    # Prefer the LLM's tool-schema field (``design_rationale``) over a
    # hand-edited ``design_notes``; the candidate strip surfaces the
    # rationale as the editable copy and there's no separate
    # ``design_notes`` editor today. Falling back the other way is just
    # defensive in case a future caller flips the field name back.
    out["design_notes"] = candidate.get("design_rationale") or candidate.get("design_notes", "")
    distribution = candidate.get("distribution") or {}
    rarity_range = [r for r in ("common", "uncommon", "rare", "mythic") if distribution.get(r, 0)]
    if not rarity_range:
        complexity = candidate.get("complexity", 1)
        if complexity >= 3:
            rarity_range = ["uncommon", "rare", "mythic"]
        else:
            rarity_range = ["common", "uncommon", "rare", "mythic"]
    out["rarity_range"] = rarity_range
    return out


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------


def generate_mechanic_candidates(*, theme: dict | None = None) -> dict:
    """Generate mechanic candidates for the active project via LLM.

    Reads ``theme.json`` and ``set_params`` from the active project,
    assembles the prompts, and calls ``generate_with_tool``. Returns
    the raw response shape for callers that want token usage too::

        {
            "mechanics": list[dict],
            "input_tokens": int,
            "output_tokens": int,
            "model_id": str,
        }

    Raises ``RuntimeError`` if the LLM returns fewer than the required
    candidate count (the runner translates this to a stage failure).
    """
    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    project = require_active_project()
    settings = project.settings
    sp = settings.set_params
    model_id = settings.get_llm_model_id("mechanics")

    if theme is None:
        theme_path = set_artifact_dir() / "theme.json"
        if not theme_path.exists():
            raise RuntimeError(f"theme.json not found at {theme_path} — run theme extraction first")
        theme = json.loads(theme_path.read_text(encoding="utf-8"))
    assert theme is not None

    system_prompt, user_prompt = build_mechanic_prompts(
        theme=theme,
        set_name=sp.set_name or project.set_code or "Custom Set",
        set_size=sp.set_size,
        mechanic_count=sp.mechanic_count,
    )

    logger.info(
        "Generating %d mechanic candidates (model=%s, set_size=%d, mech_count=%d)",
        CANDIDATE_COUNT,
        model_id,
        sp.set_size,
        sp.mechanic_count,
    )
    response = generate_with_tool(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_schema=MECHANIC_TOOL_SCHEMA,
        model=model_id,
        temperature=1.0,
        max_tokens=8192,
    )
    mechanics = response["result"].get("mechanics") or []
    if len(mechanics) < CANDIDATE_COUNT:
        raise RuntimeError(
            f"Mechanic generation returned {len(mechanics)} candidates (expected {CANDIDATE_COUNT})"
        )
    if len(mechanics) > CANDIDATE_COUNT:
        logger.warning(
            "LLM returned %d candidates; truncating to first %d",
            len(mechanics),
            CANDIDATE_COUNT,
        )
        mechanics = mechanics[:CANDIDATE_COUNT]
    return {
        "mechanics": mechanics,
        "input_tokens": response.get("input_tokens", 0),
        "output_tokens": response.get("output_tokens", 0),
        "model_id": model_id,
    }
