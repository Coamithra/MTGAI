"""Draft-archetype generation — driven by ``theme.json`` + ``mechanics/approved.json``.

Wired into the pipeline as the ``archetypes`` stage (between ``mechanics``
and ``skeleton`` in ``STAGE_RUNNERS``). The runner in
``mtgai.pipeline.stages`` does the orchestration; this module owns the
prompt assembly, tool-schema contract, color-pair normalization, and the
per-call log sidecar.

Mirrors ``mechanic_generator.py`` in shape. Templates live next door:

* ``mtgai/pipeline/prompts/archetype_system.txt`` — system prompt
* ``mtgai/pipeline/prompts/archetype_user.txt``   — user prompt

Output is a JSON array, one entry per two-color pair, each matching
``mtgai.models.set.DraftArchetype`` (plus a ``speed`` hint key the model
tolerates as an extra). Written to ``<asset>/archetypes.json`` — the
single source later stages (TC-6 prompts, TC-7 skeleton) consume.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mtgai.generation.llm_client import generate_with_tool

logger = logging.getLogger(__name__)

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent / "pipeline"
_PROMPTS_DIR = _PIPELINE_ROOT / "prompts"

# The ten two-color pairs in WUBRG guild order. Single source of truth for
# both the prompt's pair list and the post-call dedupe ordering.
COLOR_PAIRS: list[str] = ["WU", "WB", "WR", "WG", "UB", "UR", "UG", "BR", "BG", "RG"]

# WUBRG rank for canonicalising a raw pair ("UW" -> "WU").
_WUBRG_RANK: dict[str, int] = {c: i for i, c in enumerate("WUBRG")}

# Minimum surviving archetypes after dedupe before the runner treats the
# call as a failure. We ask for all ten; allow a small shortfall (a model
# occasionally merges two adjacent pairs) but bail if it's badly under.
MIN_ARCHETYPES = 8

SPEED_VALUES: list[str] = ["aggro", "midrange", "control", "tempo", "combo"]

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
                    "required": [
                        "color_pair",
                        "name",
                        "description",
                        "primary_mechanics",
                        "signpost_uncommon",
                        "speed",
                    ],
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
                            "description": "1-2 sentence strategy: how the deck is built and wins",
                        },
                        "primary_mechanics": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Approved set mechanics (exact names) this archetype leans on"
                            ),
                        },
                        "signpost_uncommon": {
                            "type": "string",
                            "description": "The gold uncommon that signals this archetype",
                        },
                        "speed": {
                            "type": "string",
                            "enum": SPEED_VALUES,
                            "description": "Archetype speed",
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


def _format_mechanics_block(approved: list[Any]) -> str:
    """Render the approved-mechanics list for the system prompt.

    Each mechanic shows name, colors, complexity, and design notes so the
    LLM can tie each archetype to the mechanics that share its colors.
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
        notes = mech.get("design_notes") or mech.get("flavor_connection") or ""
        if notes:
            lines.append(f"    {str(notes).strip()}")
    return "\n".join(lines) if lines else "(no approved mechanics)"


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
    """Surface legendary characters + notable cards as flavor anchors."""
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


def build_archetype_prompts(
    theme: dict,
    approved: list[dict],
    set_name: str,
    set_size: int,
) -> tuple[str, str]:
    """Render the archetype-generation system + user prompts."""
    sys_template = _read_template("archetype_system.txt")
    user_template = _read_template("archetype_user.txt")

    system_prompt = sys_template.format(
        set_name=set_name or "(unnamed set)",
        set_size=set_size,
        theme=(theme.get("theme") or theme.get("setting") or "(no theme provided)").strip(),
        flavor_description=(theme.get("flavor_description") or "").strip()
        or "(no flavor description provided)",
        mechanics_block=_format_mechanics_block(approved),
        creature_types_block=_format_creature_types_block(theme.get("creature_types") or []),
        constraints_block=_format_constraints_block(
            theme.get("constraints") or theme.get("special_constraints") or []
        ),
        characters_block=_format_characters_block(theme),
    )
    user_prompt = user_template.format(set_size=set_size)
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
    """
    by_pair: dict[str, dict] = {}
    for arch in archetypes:
        if not isinstance(arch, dict):
            continue
        pair = normalize_color_pair(arch.get("color_pair"))
        if pair is None or pair in by_pair:
            continue
        cleaned = dict(arch)
        cleaned["color_pair"] = pair
        cleaned.setdefault("primary_mechanics", [])
        by_pair[pair] = cleaned
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

    Raises ``RuntimeError`` if fewer than :data:`MIN_ARCHETYPES` survive
    color-pair normalization (the runner translates this to a stage
    failure).
    """
    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    project = require_active_project()
    settings = project.settings
    sp = settings.set_params
    model_id = settings.get_llm_model_id("archetypes")

    asset_dir = set_artifact_dir()
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

    system_prompt, user_prompt = build_archetype_prompts(
        theme=theme,
        approved=approved,
        set_name=sp.set_name or project.set_code or "Custom Set",
        set_size=sp.set_size,
    )

    logger.info(
        "Generating draft archetypes (model=%s, approved_mechanics=%d)",
        model_id,
        len(approved),
    )
    started = time.perf_counter()
    response: dict[str, Any] | None = None
    error: str | None = None
    try:
        response = generate_with_tool(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tool_schema=ARCHETYPE_TOOL_SCHEMA,
            model=model_id,
            temperature=1.0,
            max_tokens=8192,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        latency_s = time.perf_counter() - started
        _save_generation_log(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response=response,
            model_id=model_id,
            latency_s=latency_s,
            error=error,
        )

    raw = response["result"].get("archetypes") or []
    archetypes = dedupe_and_complete(raw)
    if len(archetypes) < MIN_ARCHETYPES:
        raise RuntimeError(
            f"Archetype generation produced {len(archetypes)} valid archetypes "
            f"(expected {len(COLOR_PAIRS)}, minimum {MIN_ARCHETYPES})"
        )
    return {
        "archetypes": archetypes,
        "input_tokens": response.get("input_tokens", 0),
        "output_tokens": response.get("output_tokens", 0),
        "model_id": model_id,
    }


def _save_generation_log(
    *,
    system_prompt: str,
    user_prompt: str,
    response: dict[str, Any] | None,
    model_id: str,
    latency_s: float,
    error: str | None,
) -> None:
    """Persist a per-call archetype-generation log under the active project.

    Path: ``<asset>/archetypes/logs/<isots>.json``. Captures full prompts,
    raw tool result, token usage, latency, and any error — same shape as
    the mechanic-generation log.
    """
    from mtgai.io.asset_paths import NoAssetFolderError, set_artifact_dir

    try:
        log_dir = set_artifact_dir() / "archetypes" / "logs"
    except NoAssetFolderError:
        return
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.warning("Could not create archetype-generation log dir at %s", log_dir)
        return

    timestamp = datetime.now(UTC).isoformat().replace(":", "-").replace("+00-00", "Z")
    log_path = log_dir / f"{timestamp}.json"
    payload: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "model": model_id,
        "latency_s": round(latency_s, 2),
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
    }
    if error is not None:
        payload["error"] = error
    if response is not None:
        payload.update(
            {
                "input_tokens": response.get("input_tokens", 0),
                "output_tokens": response.get("output_tokens", 0),
                "cache_creation_input_tokens": response.get("cache_creation_input_tokens", 0),
                "cache_read_input_tokens": response.get("cache_read_input_tokens", 0),
                "stop_reason": response.get("stop_reason", ""),
                "raw_result": response.get("result", {}),
            }
        )
    try:
        log_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        logger.warning("Could not write archetype-generation log to %s", log_path)
