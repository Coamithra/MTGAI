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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mtgai.generation.llm_client import generate_with_tool

logger = logging.getLogger(__name__)

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent / "pipeline"
_PROMPTS_DIR = _PIPELINE_ROOT / "prompts"
_TEMPLATES_DIR = _PIPELINE_ROOT / "templates"

# Maximum number of mechanics a user may select for a single set — a sanity
# cap so the candidate pool (twice this, see ``candidate_count``) stays bounded.
MAX_MECHANIC_COUNT = 6


def candidate_count(mechanic_count: int) -> int:
    """Size of the candidate pool to generate for a given selection count.

    Twice the number the user will pick — enough slack for genuine choice
    and for dropping the occasional malformed local-model candidate.
    """
    return max(1, mechanic_count * 2)


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
                        "design_rationale",
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
                        "design_rationale": {
                            "type": "string",
                            "description": "Why this mechanic is good for the set",
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


# Tool schema for the AI picker: selects the best N from a candidate pool.
MECHANIC_PICK_TOOL_SCHEMA: dict = {
    "name": "select_best_mechanics",
    "description": (
        "Select the best mechanics from the candidate pool for this set, "
        "with a one-line reason per pick and an overall rationale for the slate."
    ),
    "input_schema": {
        "type": "object",
        "required": ["selections", "overall_rationale"],
        "properties": {
            "selections": {
                "type": "array",
                "description": "The chosen mechanics, by candidate number.",
                "items": {
                    "type": "object",
                    "required": ["candidate_number", "reason"],
                    "properties": {
                        "candidate_number": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "1-based number of the candidate from the list.",
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence on why this candidate earned a slot.",
                        },
                    },
                },
            },
            "overall_rationale": {
                "type": "string",
                "description": (
                    "Short rationale for the slate as a whole — color spread, "
                    "complexity mix, and how the picks work together."
                ),
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


def _read_template(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def _format_setting_block(theme: dict) -> str:
    """The setting prose for the prompt's single 'Setting' field.

    Handles both schemas: the current toolchain writes the world document to
    ``setting``; legacy ASD themes use a short ``theme`` one-liner plus a
    ``flavor_description`` prose blob. We surface the one-liner (if any) then
    the prose, so neither schema loses content — and there's no dead
    "(no flavor description provided)" subsection when only ``setting`` exists.
    """
    one_liner = (theme.get("theme") or "").strip()
    prose = (theme.get("flavor_description") or theme.get("setting") or "").strip()
    parts = [p for p in (one_liner, prose) if p]
    return "\n\n".join(parts) if parts else "(no setting provided)"


def _format_archetypes_block(archetypes: list[Any]) -> str:
    """Render the draft-archetype list, or ``""`` when there are none.

    Returns empty so the builder can omit the whole "## Draft archetypes"
    section rather than print a misleading placeholder. In the toolchain
    pipeline mechanics are designed *before* archetypes exist (archetypes are
    derived from the mechanics downstream), so this is empty for new sets;
    legacy ASD themes that carry ``draft_archetypes`` still render here.
    """
    lines: list[str] = []
    for arch in archetypes or []:
        if not isinstance(arch, dict):
            continue
        colors = arch.get("color_pair") or arch.get("colors") or ""
        name = arch.get("name") or ""
        desc = arch.get("description") or ""
        if name and desc:
            lines.append(f"- {colors}: {name} — {desc}".lstrip())
        elif name:
            lines.append(f"- {colors}: {name}".lstrip())
    return "\n".join(lines)


def _archetypes_section(archetypes: list[Any]) -> str:
    """Wrap the archetype list in its section header, or ``""`` when empty."""
    block = _format_archetypes_block(archetypes)
    return f"\n## Draft archetypes\n\n{block}\n" if block else ""


def _format_constraints_block(constraints: list[Any]) -> str:
    if not constraints:
        return "(no special constraints)"
    lines: list[str] = []
    for c in constraints:
        text = c.get("text") if isinstance(c, dict) else c
        if text:
            lines.append(f"- {text}")
    return "\n".join(lines) if lines else "(no special constraints)"


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
        setting_block=_format_setting_block(theme),
        archetypes_block=_archetypes_section(theme.get("draft_archetypes") or []),
        constraints_block=_format_constraints_block(
            theme.get("constraints") or theme.get("special_constraints") or []
        ),
        excluded_keywords=_format_excluded_keywords(known),
        expected_mechanic_density=expected_density,
    )
    user_prompt = user_template.format(
        mechanic_count=mechanic_count,
        set_size=set_size,
        expected_mechanic_density=expected_density,
    )
    return system_prompt, user_prompt


def _format_candidate_digest(candidates: list[dict]) -> str:
    """Render the candidate pool as a numbered list for the picker prompt.

    One block per candidate — number, name, type, colors, complexity, plus
    reminder text and rationale — so the LLM can weigh the slate. The
    1-based numbering is what the pick tool's ``candidate_number`` field
    refers back to (mapped to a 0-based index in :func:`pick_best_mechanics`).
    """
    if not candidates:
        return "(no candidates)"
    lines: list[str] = []
    for i, m in enumerate(candidates, 1):
        m = m or {}
        name = (m.get("name") or "?").strip() or "?"
        colors = "".join(m.get("colors") or []) or "colorless"
        cx = m.get("complexity", "?")
        ktype = m.get("keyword_type") or "?"
        lines.append(f"{i}. {name} — type: {ktype}; colors: {colors}; complexity: {cx}")
        reminder = (m.get("reminder_text") or "").strip()
        if reminder:
            lines.append(f"   reminder: {reminder}")
        rationale = (m.get("design_rationale") or m.get("design_notes") or "").strip()
        if rationale:
            lines.append(f"   rationale: {rationale}")
    return "\n".join(lines)


def build_pick_prompts(
    theme: dict,
    set_name: str,
    set_size: int,
    mechanic_count: int,
    candidates: list[dict],
) -> tuple[str, str]:
    """Render the picker's system + user prompts from theme + the candidate pool.

    The system prompt carries the set context + the selection criteria;
    the user prompt carries the numbered candidate digest. Mirrors the
    generation prompts' split so the system block stays cache-friendly.
    """
    sys_template = _read_template("mechanic_pick_system.txt")
    user_template = _read_template("mechanic_pick_user.txt")

    system_prompt = sys_template.format(
        set_name=set_name or "(unnamed set)",
        set_size=set_size,
        mechanic_count=mechanic_count,
        setting_block=_format_setting_block(theme),
        archetypes_block=_archetypes_section(theme.get("draft_archetypes") or []),
        constraints_block=_format_constraints_block(
            theme.get("constraints") or theme.get("special_constraints") or []
        ),
    )
    user_prompt = user_template.format(
        mechanic_count=mechanic_count,
        candidate_digest=_format_candidate_digest(candidates),
    )
    return system_prompt, user_prompt


def _format_already_designed(accepted: list[dict]) -> str:
    """Render the accepted-so-far mechanics as a rich 'vary from these' block.

    Since the trimmed output schema freed up the token budget, we surface
    the full picture of each prior mechanic — colors, complexity, type,
    reminder text, rationale — so the model can *see* the distribution so
    far (e.g. "all complexity 1, all UBR") and deliberately diverge instead
    of clustering.
    """
    if not accepted:
        return "No mechanics have been designed yet — this is the first candidate."
    lines = [
        "Mechanics already designed for this set so far. Your new mechanic must be "
        "clearly DISTINCT from all of these — deliberately vary the color identity, "
        "complexity, and mechanical space; do NOT cluster around what is already here:",
    ]
    for i, m in enumerate(accepted, 1):
        name = m.get("name") or "?"
        colors = "".join(m.get("colors") or []) or "colorless"
        cx = m.get("complexity", "?")
        ktype = m.get("keyword_type") or "?"
        lines.append(f"{i}. {name} — {colors}, complexity {cx}, {ktype}")
        reminder = (m.get("reminder_text") or "").strip()
        if reminder:
            lines.append(f"   text: {reminder}")
        rationale = (m.get("design_rationale") or "").strip()
        if rationale:
            lines.append(f"   rationale: {rationale}")
    return "\n".join(lines)


def _needed_hint(accepted: list[dict], remaining: int, enforce_simple_floor: bool) -> str:
    """Adaptive nudge to preserve the spread the batch prompt used to guarantee.

    The single strongest invariant from the old batch prompt was 'at least
    one complexity-1 (common-viable) mechanic'. If none exists yet and we're
    running low on remaining slots, force this one to fill that gap. Only
    applies when building a full pool (``enforce_simple_floor``) — a targeted
    refresh of one slot shouldn't be biased toward simple designs.
    """
    if not enforce_simple_floor:
        return ""
    has_simple = any(m.get("complexity") == 1 for m in accepted)
    if not has_simple and remaining <= 2:
        return (
            "- IMPORTANT: none of the mechanics so far are complexity 1, and the set "
            "needs at least one. Make THIS mechanic complexity 1 — simple enough to be "
            "viable at common with short reminder text."
        )
    return ""


def build_single_mechanic_user_prompt(
    *,
    accepted: list[dict],
    position: int,
    target: int,
    mechanic_count: int,
    set_size: int,
    expected_density: str,
    enforce_simple_floor: bool = True,
) -> str:
    """Render the per-call user prompt asking for ONE distinct mechanic.

    The system prompt (theme/flavor/constraints) is unchanged and shared
    across every call in the loop; only this user prompt varies, threading
    the already-accepted mechanics so the model avoids repeats.
    """
    template = _read_template("mechanic_user_single.txt")
    remaining = max(0, target - len(accepted))
    return template.format(
        position=position,
        target=target,
        mechanic_count=mechanic_count,
        set_size=set_size,
        expected_mechanic_density=expected_density,
        already_block=_format_already_designed(accepted),
        needed_hint=_needed_hint(accepted, remaining, enforce_simple_floor),
    )


def _is_valid_candidate(m: Any, seen_names: set[str], known: set[str]) -> bool:
    """Accept only well-formed, non-duplicate, non-colliding mechanic objects.

    Guards against the local-model JSON degradation that motivated the
    one-at-a-time loop: malformed entries (null/blank ``name``) and
    example-card debris promoted to the top level by JSON repair (which
    lack mechanic-level metadata) are rejected, as are duplicates.

    A candidate whose name matches a printed MTG keyword (``known``,
    lowercased) is rejected too, so the loop regenerates a replacement
    instead of keeping it: the wizard has no inline rename, so a colliding
    candidate is dead weight. This promotes the keyword collision from a
    soft warning to a hard reject — the system prompt already excludes
    known keywords, this is the backstop for the occasional slip-through.
    """
    if not isinstance(m, dict):
        return False
    name = m.get("name")
    if not isinstance(name, str) or not name.strip():
        return False
    normalized = name.strip().lower()
    if normalized in seen_names:
        return False
    if normalized in known:
        return False
    # A real mechanic carries design metadata an example card never would;
    # this distinguishes it from promoted example-card debris.
    return bool(m.get("reminder_text") or m.get("design_rationale"))


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
    "distribution",
)


def candidate_to_approved(candidate: dict) -> dict:
    """Project a candidate dict to the on-disk ``approved.json`` shape.

    * Copies the ``_APPROVED_FIELDS`` whitelist (name, keyword_type,
      reminder_text, colors, complexity, distribution) — anything else the
      candidate carries is dropped.
    * Renames ``design_rationale`` → ``design_notes`` (downstream
      consumers read ``design_notes``).
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


def generate_mechanic_candidates(*, theme: dict | None = None, count: int | None = None) -> dict:
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

    Generates ONE mechanic per call rather than the whole pool at once:
    local models degrade on long structured output (a single big tool call
    returned syntactically-valid but semantically-shredded JSON once the
    generation grew long — clean first mechanic, junk by the third). Each
    short call stays coherent; we validate the result, drop malformed or
    duplicate entries, feed the accepted names back so the model avoids
    repeats, and loop until the candidate pool (twice ``mechanic_count``)
    is reached or the attempt budget is spent.

    Succeeds as long as at least ``mechanic_count`` valid candidates are
    collected (that's all the user picks); raises ``RuntimeError`` only if
    the loop can't reach that floor, or if calls fail repeatedly up front.
    """
    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime import ai_lock
    from mtgai.runtime.active_project import require_active_project

    project = require_active_project()
    settings = project.settings
    sp = settings.set_params
    model_id = settings.get_llm_model_id("mechanics")
    # llmfacade writes each call's JSONL+HTML transcript here (named after the
    # tool); it's the canonical per-call log — no bespoke logger needed.
    log_dir = set_artifact_dir() / "mechanics" / "logs"

    if theme is None:
        theme_path = set_artifact_dir() / "theme.json"
        if not theme_path.exists():
            raise RuntimeError(f"theme.json not found at {theme_path} — run theme extraction first")
        theme = json.loads(theme_path.read_text(encoding="utf-8"))
    assert theme is not None

    # System prompt (theme/flavor/constraints) is stable across the whole
    # loop and prompt-cache-friendly; only the per-call user prompt varies,
    # threading the already-accepted mechanics. We discard the batch user
    # prompt build_mechanic_prompts returns and build a single-mechanic one.
    system_prompt, _ = build_mechanic_prompts(
        theme=theme,
        set_name=sp.set_name or project.set_code or "Custom Set",
        set_size=sp.set_size,
        mechanic_count=sp.mechanic_count,
    )
    expected_density = _expected_mechanic_density(sp.set_size, sp.mechanic_count)
    # Callers ask for exactly what they need: the stage / initial generation
    # wants the full pool (twice mechanic_count); the refresh-one endpoint wants 1.
    target = candidate_count(sp.mechanic_count) if count is None else max(1, count)
    floor = max(1, min(sp.mechanic_count, target))
    max_attempts = max(3, target * 2)
    # The "must include a complexity-1 mechanic" floor is a whole-pool concern;
    # don't impose it on a targeted single-slot refresh (count given).
    enforce_simple_floor = count is None

    logger.info(
        "Generating up to %d mechanic candidates one at a time "
        "(model=%s, set_size=%d, mech_count=%d, floor=%d, max_attempts=%d)",
        target,
        model_id,
        sp.set_size,
        sp.mechanic_count,
        floor,
        max_attempts,
    )

    # Printed-keyword set for the hard collision reject below. Built once
    # (it reads a template file) and reused across every attempt.
    known_keywords = known_keyword_set()

    accepted: list[dict] = []
    seen_names: set[str] = set()
    total_in = 0
    total_out = 0
    attempt = 0
    consecutive_errors = 0
    last_error: str | None = None

    while len(accepted) < target and attempt < max_attempts:
        if ai_lock.is_cancelled():
            logger.info("Mechanic generation cancelled after %d candidate(s)", len(accepted))
            break
        attempt += 1
        user_prompt = build_single_mechanic_user_prompt(
            accepted=accepted,
            position=len(accepted) + 1,
            target=target,
            mechanic_count=sp.mechanic_count,
            set_size=sp.set_size,
            expected_density=expected_density,
            enforce_simple_floor=enforce_simple_floor,
        )
        response: dict[str, Any] | None = None
        try:
            response = generate_with_tool(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                tool_schema=MECHANIC_TOOL_SCHEMA,
                model=model_id,
                temperature=1.0,
                max_tokens=4096,
                log_dir=log_dir,
            )
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Mechanic candidate attempt %d failed: %s", attempt, last_error)

        if response is None:
            # Fail fast on a persistent hard error (dead provider, missing
            # model) rather than burning the whole attempt budget on it.
            consecutive_errors += 1
            if consecutive_errors >= 3 and not accepted:
                raise RuntimeError(
                    f"Mechanic generation failed {consecutive_errors} calls in a row "
                    f"with no valid candidates: {last_error}"
                )
            continue
        consecutive_errors = 0
        total_in += response.get("input_tokens", 0) or 0
        total_out += response.get("output_tokens", 0) or 0

        returned = (response.get("result") or {}).get("mechanics") or []
        before = len(accepted)
        for m in returned:
            if not _is_valid_candidate(m, seen_names, known_keywords):
                nm = m.get("name") if isinstance(m, dict) else None
                if isinstance(nm, str) and nm.strip().lower() in known_keywords:
                    logger.info(
                        "Rejected mechanic %r — collides with a printed keyword; regenerating",
                        nm.strip(),
                    )
                continue
            accepted.append(m)
            seen_names.add(str(m["name"]).strip().lower())
            if len(accepted) >= target:
                break
        if len(accepted) == before:
            logger.info(
                "Attempt %d yielded no valid new candidate (%d returned); retrying",
                attempt,
                len(returned),
            )

    if len(accepted) < floor:
        raise RuntimeError(
            f"Mechanic generation produced only {len(accepted)} valid candidate(s) "
            f"after {attempt} attempt(s); need at least {floor}. The model may be "
            "returning malformed tool output — try a different mechanics model or re-run."
        )
    if len(accepted) < target:
        logger.warning(
            "Collected %d/%d mechanic candidates after %d attempts (>= floor of %d, proceeding)",
            len(accepted),
            target,
            attempt,
            floor,
        )
    return {
        "mechanics": accepted[:target],
        "input_tokens": total_in,
        "output_tokens": total_out,
        "model_id": model_id,
    }


def _resolve_picks(
    selections: list[Any],
    candidate_count_total: int,
    target: int,
) -> tuple[list[int], dict[int, str]]:
    """Turn the LLM's raw ``selections`` into exactly ``target`` valid indices.

    The model returns 1-based ``candidate_number`` values that may be
    out of range, duplicated, too few, or too many. We map them to 0-based
    indices, drop anything invalid or repeated, then **top up** with the
    first unused candidates if we came up short and **truncate** if we got
    too many — so the caller always receives a clean, deduplicated slate of
    ``min(target, candidate_count_total)`` picks. Returns ``(picks, reasons)``
    where ``reasons`` maps a picked index to the model's one-line reason
    (topped-up picks have no reason).
    """
    want = max(0, min(target, candidate_count_total))
    picks: list[int] = []
    reasons: dict[int, str] = {}
    seen: set[int] = set()
    for sel in selections or []:
        if not isinstance(sel, dict):
            continue
        num = sel.get("candidate_number")
        if not isinstance(num, int):
            continue
        idx = num - 1  # 1-based in the prompt/tool, 0-based on disk
        if idx < 0 or idx >= candidate_count_total or idx in seen:
            continue
        seen.add(idx)
        picks.append(idx)
        reason = sel.get("reason")
        if isinstance(reason, str) and reason.strip():
            reasons[idx] = reason.strip()
        if len(picks) >= want:
            break
    # Top up from the front if the model under-selected (or returned junk).
    if len(picks) < want:
        for idx in range(candidate_count_total):
            if idx not in seen:
                picks.append(idx)
                seen.add(idx)
                if len(picks) >= want:
                    break
    return picks[:want], reasons


def pick_best_mechanics(
    *,
    candidates: list[dict],
    theme: dict | None = None,
    count: int | None = None,
) -> dict:
    """Ask the LLM to pick the best ``count`` mechanics from ``candidates``.

    Reads ``theme.json`` + ``set_params`` from the active project (same as
    :func:`generate_mechanic_candidates`), renders the picker prompts, and
    runs a single tool call. The selection criteria (Limited playability,
    design space, color spread, complexity mix, theme fit, non-overlap)
    live in ``mechanic_pick_system.txt``.

    Always returns a clean slate — a malformed or failed pick call degrades
    to the first ``count`` candidates rather than raising, so the stage's
    auto-continue path can never be left without an ``approved.json``::

        {
            "picks": list[int],            # 0-based indices into candidates
            "selections": list[dict],      # [{name, reason}] aligned to picks
            "overall_rationale": str,
            "model_id": str,
            "input_tokens": int,
            "output_tokens": int,
        }
    """
    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    project = require_active_project()
    settings = project.settings
    sp = settings.set_params
    model_id = settings.get_llm_model_id("mechanics")
    log_dir = set_artifact_dir() / "mechanics" / "logs"

    if theme is None:
        theme_path = set_artifact_dir() / "theme.json"
        theme = json.loads(theme_path.read_text(encoding="utf-8")) if theme_path.exists() else {}
    assert theme is not None

    target = sp.mechanic_count if count is None else max(1, count)
    total = len(candidates)

    def _fallback(reason: str, model: str = model_id) -> dict:
        picks = list(range(min(target, total)))
        logger.warning(
            "Mechanic picker falling back to first %d candidates: %s", len(picks), reason
        )
        return {
            "picks": picks,
            "selections": [
                {"name": (candidates[i].get("name") or "?"), "reason": ""} for i in picks
            ],
            "overall_rationale": "",
            "model_id": model,
            "input_tokens": 0,
            "output_tokens": 0,
        }

    if total == 0:
        return _fallback("empty candidate pool")

    system_prompt, user_prompt = build_pick_prompts(
        theme=theme,
        set_name=sp.set_name or project.set_code or "Custom Set",
        set_size=sp.set_size,
        mechanic_count=target,
        candidates=candidates,
    )

    response: dict[str, Any] | None = None
    error: str | None = None
    try:
        response = generate_with_tool(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tool_schema=MECHANIC_PICK_TOOL_SCHEMA,
            model=model_id,
            temperature=0.4,
            max_tokens=2048,
            log_dir=log_dir,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    if response is None:
        return _fallback(error or "no response")

    result = response.get("result") or {}
    selections_raw = result.get("selections") or []
    picks, reasons = _resolve_picks(selections_raw, total, target)
    selections = [
        {"name": (candidates[i].get("name") or "?"), "reason": reasons.get(i, "")} for i in picks
    ]
    return {
        "picks": picks,
        "selections": selections,
        "overall_rationale": (result.get("overall_rationale") or "").strip(),
        "model_id": model_id,
        "input_tokens": response.get("input_tokens", 0) or 0,
        "output_tokens": response.get("output_tokens", 0) or 0,
    }


def persist_mechanic_selection(
    mech_dir: Path,
    candidates: list[dict],
    picks: list[int],
    *,
    source: str = "ai",
    overall_rationale: str = "",
    selections: list[dict] | None = None,
    model_id: str = "",
) -> list[dict]:
    """Write the candidates snapshot, sidecars, and ``approved.json`` for a selection.

    The single producer of a mechanics-stage selection on disk — used by the
    stage runner (AI picker), the wizard's ``/save`` (user override), and the
    re-pick endpoint, so the write order + sidecar set stay identical across
    all three.

    Order matters: ``approved.json`` is the marker downstream stages check, so
    the candidates snapshot + sidecars are written first and ``approved.json``
    last. A ``pick-rationale.json`` sidecar records who chose the slate
    (``source``: ``"ai"`` or ``"user"``) and the AI's reasons, for the wizard
    to surface. Returns the projected ``approved`` list.
    """
    mech_dir.mkdir(parents=True, exist_ok=True)

    def _write(name: str, data: Any) -> None:
        (mech_dir / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    _write("candidates.json", candidates)
    _write("evergreen-keywords.json", load_evergreen_defaults())
    approved = [candidate_to_approved(candidates[i]) for i in picks]
    _write("pointed-questions.json", render_pointed_questions(approved))
    # Empty stub — the LLM doesn't produce functional_tags; balance.py
    # tolerates the file being missing or empty.
    _write("functional-tags.json", {})
    _write(
        "pick-rationale.json",
        {
            "source": source,
            "model_id": model_id,
            "overall_rationale": overall_rationale,
            "selections": selections or [],
            "picked_at": datetime.now(UTC).isoformat(),
        },
    )
    _write("approved.json", approved)
    return approved
