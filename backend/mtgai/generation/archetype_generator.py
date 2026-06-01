"""Draft-archetype generation — driven by ``theme.json`` + ``mechanics/approved.json``.

Wired into the pipeline as the ``archetypes`` stage (between ``mechanics``
and ``skeleton`` in ``STAGE_RUNNERS``). The runner in
``mtgai.pipeline.stages`` does the orchestration; this module owns the
prompt assembly, tool-schema contract, color-pair normalization, and the
per-call log sidecar.

Mirrors ``mechanic_generator.py`` in shape. Templates live next door:

* ``mtgai/pipeline/prompts/archetype_system.txt`` — system prompt
* ``mtgai/pipeline/prompts/archetype_user.txt``   — user prompt

Output is a JSON array, one entry per two-color pair, each projected to
``mtgai.models.set.DraftArchetype`` (``color_pair`` + ``name`` + free-text
``description``); ``dedupe_and_complete`` drops any extra keys a model
emits. Written to ``<asset>/archetypes.json`` — the single source later
stages (TC-6 prompts, TC-7 skeleton) consume.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from mtgai.generation.llm_client import generate_with_tool
from mtgai.generation.token_budgets import BATCH

logger = logging.getLogger(__name__)

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent / "pipeline"
_PROMPTS_DIR = _PIPELINE_ROOT / "prompts"

# The ten two-color pairs in WUBRG guild order. Single source of truth for
# both the prompt's pair list and the post-call dedupe ordering.
COLOR_PAIRS: list[str] = ["WU", "WB", "WR", "WG", "UB", "UR", "UG", "BR", "BG", "RG"]

# WUBRG rank for canonicalising a raw pair ("UW" -> "WU").
_WUBRG_RANK: dict[str, int] = {c: i for i, c in enumerate("WUBRG")}

# Full colour names, for human-readable pair labels in the focused-regen prompt
# ("WU" -> "White-Blue"). The full archetype prompt spells these out in its
# pair list; the focus prompt reuses the same labels.
_COLOR_FULL: dict[str, str] = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}


def pair_label(pair: str) -> str:
    """``"WU"`` -> ``"WU (White-Blue)"`` for prompt + UI display."""
    names = "-".join(_COLOR_FULL.get(c, c) for c in pair)
    return f"{pair} ({names})"


# Minimum surviving archetypes after dedupe before the runner treats the
# call as a failure. We ask for all ten; allow a small shortfall (a model
# occasionally merges two adjacent pairs) but bail if it's badly under.
MIN_ARCHETYPES = 8

# ---------------------------------------------------------------------------
# Tool schema: defines the structured output the LLM must return
# ---------------------------------------------------------------------------

ARCHETYPE_TOOL_SCHEMA: dict = {
    "name": "submit_draft_archetypes",
    "description": (
        "Submit the ten two-color draft archetypes for the custom MTG set, "
        "one per color pair. Each archetype must include all required fields."
    ),
    "input_schema": {
        "type": "object",
        "required": ["archetypes"],
        "properties": {
            "archetypes": {
                "type": "array",
                "description": "List of draft archetypes, one per color pair",
                "items": {
                    "type": "object",
                    "required": ["color_pair", "name", "description"],
                    "properties": {
                        "color_pair": {
                            "type": "string",
                            "enum": COLOR_PAIRS,
                            "description": "Two-letter color pair in WUBRG guild order",
                        },
                        "name": {
                            "type": "string",
                            "description": "Flavorful archetype name rooted in the setting",
                        },
                        "description": {
                            "type": "string",
                            "description": (
                                "Free-text intent. Lead with the WIN CONDITION (how a deck "
                                "drafting this pair closes the game), then how it's built to "
                                "get there. Where they apply, weave in whether the deck leans "
                                "heavily on an approved set mechanic and whether it hinges on a "
                                "key enabler card. Pace/speed is inherent in the gameplan; "
                                "don't state it separately."
                            ),
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


def _format_mechanics_block(approved: list[Any]) -> str:
    """Render the approved-mechanics list for the system prompt.

    Each mechanic shows name, colors, complexity, and its **reminder
    (oracle) text** — what the mechanic actually does, not its flavor
    rationale — so the LLM ties archetypes to the mechanics' real effects.
    """
    if not approved:
        return "(no approved mechanics — design archetypes around the set's flavor)"
    lines: list[str] = []
    for mech in approved:
        if not isinstance(mech, dict):
            continue
        name = mech.get("name") or "?"
        colors = mech.get("colors") or []
        colors_str = "".join(str(c) for c in colors) if colors else "?"
        complexity = mech.get("complexity")
        header = f"- {name} ({colors_str}"
        if complexity is not None:
            header += f", complexity {complexity}"
        header += ")"
        lines.append(header)
        reminder = (mech.get("reminder_text") or "").strip()
        if reminder:
            lines.append(f"    {reminder}")
    return "\n".join(lines) if lines else "(no approved mechanics)"


def _format_constraints_block(constraints: list[Any]) -> str:
    if not constraints:
        return "(no special constraints)"
    lines: list[str] = []
    for c in constraints:
        text = c.get("text") if isinstance(c, dict) else c
        if text:
            lines.append(f"- {text}")
    return "\n".join(lines) if lines else "(no special constraints)"


def _format_existing_block(existing: list[dict] | None, focus_pairs: list[str]) -> str:
    """Render the kept archetypes (the pairs *not* being regenerated).

    Used only by the focused-regen prompt so the LLM redesigns a few pairs
    while staying distinct from the ones the user is keeping. Pairs in
    ``focus_pairs`` are excluded (they're the ones being replaced), as are
    entries with no content yet (empty placeholders carry no useful signal).
    """
    skip = set(focus_pairs)
    lines: list[str] = []
    for arch in existing or []:
        if not isinstance(arch, dict):
            continue
        pair = normalize_color_pair(arch.get("color_pair"))
        if pair is None or pair in skip:
            continue
        name = (arch.get("name") or "").strip()
        desc = (arch.get("description") or "").strip()
        if not name and not desc:
            continue
        lines.append(f"- {pair_label(pair)} — {name or '(unnamed)'}: {desc or '(no intent)'}")
    if not lines:
        return "(No other archetypes are locked in yet — just design the requested pair(s).)"
    header = (
        "Already-designed archetypes for the OTHER pairs "
        "(keep your new designs distinct and non-overlapping):"
    )
    return header + "\n" + "\n".join(lines)


def build_archetype_prompts(
    theme: dict,
    approved: list[dict],
    set_name: str,
    set_size: int,
    *,
    focus_pairs: list[str] | None = None,
    existing: list[dict] | None = None,
) -> tuple[str, str]:
    """Render the archetype-generation system + user prompts.

    With ``focus_pairs`` set, the user prompt asks the model to regenerate
    *only* those pairs (passing the remaining archetypes as context via
    ``existing`` so the new designs stay distinct) — the per-card / partial
    "Refresh AI" path. Without it, the full ten-pair brief is used.
    """
    sys_template = _read_template("archetype_system.txt")
    system_prompt = sys_template.format(
        set_name=set_name or "(unnamed set)",
        set_size=set_size,
        setting_block=_format_setting_block(theme),
        mechanics_block=_format_mechanics_block(approved),
        constraints_block=_format_constraints_block(
            theme.get("constraints") or theme.get("special_constraints") or []
        ),
    )

    if focus_pairs:
        user_template = _read_template("archetype_user_focus.txt")
        user_prompt = user_template.format(
            set_size=set_size,
            focus_count=len(focus_pairs),
            focus_pairs=", ".join(pair_label(p) for p in focus_pairs),
            existing_block=_format_existing_block(existing, focus_pairs),
        )
    else:
        user_prompt = _read_template("archetype_user.txt").format(set_size=set_size)
    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Color-pair normalization + dedupe
# ---------------------------------------------------------------------------


def normalize_color_pair(raw: object) -> str | None:
    """Canonicalise a raw color-pair string to WUBRG guild order.

    ``"UW"`` -> ``"WU"``, ``"wu"`` -> ``"WU"``. Returns ``None`` for
    anything that isn't a distinct two-color pair drawn from WUBRG
    (e.g. ``"WW"``, ``"X"``, ``"WUB"``, ``""``).
    """
    if not isinstance(raw, str):
        return None
    letters = [c for c in raw.upper() if c in _WUBRG_RANK]
    if len(letters) != 2:
        return None
    a, b = letters
    if a == b:
        return None
    ordered = sorted((a, b), key=lambda c: _WUBRG_RANK[c])
    pair = "".join(ordered)
    return pair if pair in COLOR_PAIRS else None


def dedupe_and_complete(archetypes: list[Any]) -> list[dict]:
    """Normalize color pairs, drop malformed/duplicate entries, sort to order.

    Keeps the first archetype seen per valid color pair, normalising its
    ``color_pair`` to canonical WUBRG order, and returns the survivors in
    :data:`COLOR_PAIRS` order. Does NOT fabricate missing pairs — a short
    list is a soft signal the runner surfaces (and ultimately bails on via
    :data:`MIN_ARCHETYPES`).

    Each survivor is projected to exactly the schema's fields
    (``color_pair`` / ``name`` / ``description``). The tool schema only
    constrains what's *required*, so a model — especially a local one —
    can still emit stray keys (``speed``, ``signpost_uncommon``, …); this
    drops them so the on-disk archetype is strictly name + intent.
    """
    by_pair: dict[str, dict] = {}
    for arch in archetypes:
        if not isinstance(arch, dict):
            continue
        pair = normalize_color_pair(arch.get("color_pair"))
        if pair is None or pair in by_pair:
            continue
        by_pair[pair] = {
            "color_pair": pair,
            "name": str(arch.get("name") or ""),
            "description": str(arch.get("description") or ""),
        }
    return [by_pair[p] for p in COLOR_PAIRS if p in by_pair]


# ---------------------------------------------------------------------------
# On-disk loader (for downstream consumers — prompts.py / skeleton)
# ---------------------------------------------------------------------------


def load_archetypes(asset_dir: Path | None = None) -> list[dict]:
    """Load ``archetypes.json`` for the active project (or a given dir).

    Returns ``[]`` when the file doesn't exist — callers fall back to the
    theme's ``draft_archetypes`` in that case.
    """
    if asset_dir is None:
        from mtgai.io.asset_paths import set_artifact_dir

        asset_dir = set_artifact_dir()
    path = asset_dir / "archetypes.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------


def generate_archetypes(
    *,
    theme: dict | None = None,
    approved: list[dict] | None = None,
    focus_pairs: list[str] | None = None,
    existing: list[dict] | None = None,
) -> dict:
    """Generate the set's draft archetypes for the active project via LLM.

    Reads ``theme.json`` + ``mechanics/approved.json`` from the active
    project (unless passed in), assembles the prompts, and calls
    ``generate_with_tool``. Returns::

        {
            "archetypes": list[dict],   # normalized, one per pair, ordered
            "input_tokens": int,
            "output_tokens": int,
            "model_id": str,
        }

    Full run (``focus_pairs=None``): asks for all ten pairs and raises
    ``RuntimeError`` if fewer than :data:`MIN_ARCHETYPES` survive color-pair
    normalization (the runner translates this to a stage failure).

    Focused run (``focus_pairs`` given): the wizard's per-card / partial
    "Refresh AI" path — regenerates only those pairs, passing ``existing``
    (the user's current working list) as context so the new designs stay
    distinct from the kept ones. The returned ``archetypes`` are filtered to
    the requested pairs; raises ``RuntimeError`` if the model produced none
    of them.
    """
    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    project = require_active_project()
    settings = project.settings
    sp = settings.set_params
    model_id = settings.get_llm_model_id("archetypes")

    asset_dir = set_artifact_dir()
    # llmfacade writes each call's JSONL+HTML transcript here (named after the
    # tool); it's the canonical per-call log — no bespoke logger needed.
    log_dir = asset_dir / "archetypes" / "logs"
    if theme is None:
        theme_path = asset_dir / "theme.json"
        if not theme_path.exists():
            raise RuntimeError(f"theme.json not found at {theme_path} — run theme extraction first")
        theme = json.loads(theme_path.read_text(encoding="utf-8"))
    assert theme is not None

    if approved is None:
        approved_path = asset_dir / "mechanics" / "approved.json"
        if not approved_path.exists():
            raise RuntimeError(
                f"approved.json not found at {approved_path} — approve mechanics first"
            )
        loaded = json.loads(approved_path.read_text(encoding="utf-8"))
        approved = loaded if isinstance(loaded, list) else []

    # Canonicalise the requested focus pairs (drop anything invalid); a
    # caller that passes only junk degrades to a full run.
    norm_focus: list[str] | None = None
    if focus_pairs:
        seen: set[str] = set()
        norm_focus = []
        for p in focus_pairs:
            cp = normalize_color_pair(p)
            if cp is not None and cp not in seen:
                seen.add(cp)
                norm_focus.append(cp)
        norm_focus = norm_focus or None

    system_prompt, user_prompt = build_archetype_prompts(
        theme=theme,
        approved=approved,
        set_name=sp.set_name or project.set_code or "Custom Set",
        set_size=sp.set_size,
        focus_pairs=norm_focus,
        existing=existing,
    )

    logger.info(
        "Generating draft archetypes (model=%s, approved_mechanics=%d, focus=%s)",
        model_id,
        len(approved),
        norm_focus or "all",
    )
    response = generate_with_tool(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_schema=ARCHETYPE_TOOL_SCHEMA,
        model=model_id,
        temperature=1.0,
        max_tokens=BATCH,
        log_dir=log_dir,
    )

    raw = response["result"].get("archetypes") or []
    archetypes = dedupe_and_complete(raw)
    if norm_focus:
        wanted = set(norm_focus)
        archetypes = [a for a in archetypes if a["color_pair"] in wanted]
        if not archetypes:
            raise RuntimeError(
                "Focused archetype regeneration produced none of the requested pairs "
                f"({', '.join(norm_focus)})"
            )
    elif len(archetypes) < MIN_ARCHETYPES:
        raise RuntimeError(
            f"Archetype generation produced {len(archetypes)} valid archetypes "
            f"(expected {len(COLOR_PAIRS)}, minimum {MIN_ARCHETYPES})"
        )
    return {
        "archetypes": archetypes,
        "input_tokens": response.get("input_tokens", 0),
        "output_tokens": response.get("output_tokens", 0),
        # Provenance shows the base the user assigned, not the internal ctx twin.
        "model_id": settings.get_assigned_model_id("archetypes"),
    }
