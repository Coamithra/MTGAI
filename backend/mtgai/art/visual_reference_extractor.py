"""Visual-reference extraction — driven by ``theme.json`` setting prose.

Wired into the pipeline as the ``visual_refs`` stage (just before
``art_prompts``, its earliest consumer — the art stages are the only
ones that read its output). The runner in ``mtgai.pipeline.stages`` does
the orchestration; this module owns the prompt assembly, tool-schema
contract, the flat-entity -> nested-category assembly, and the per-call
log sidecar.

Mirrors ``generation/archetype_generator.py`` in shape. Templates live in
the pipeline prompts dir:

* ``mtgai/pipeline/prompts/visual_references_system.txt`` — system prompt
* ``mtgai/pipeline/prompts/visual_references_user.txt``   — user prompt

Output is the per-project ``<asset>/art-direction/visual-references.json``
already consumed by ``mtgai.art.visual_reference`` and
``mtgai.art.character_portraits``. Its top-level keys are entity-category
dicts (``legendary_characters``, ``creature_types``, ``factions``,
``landmarks``), each mapping a lowercase entity key to a plain-English
visual description, plus a ``flux_term_replacements`` map and a set-wide
``visual_motifs`` list. The card 69f9d47e style-guide work builds its
``characters.json`` on top of this contract.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from mtgai.generation.llm_client import generate_with_tool
from mtgai.generation.token_budgets import STANDARD

logger = logging.getLogger(__name__)

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent / "pipeline"
_PROMPTS_DIR = _PIPELINE_ROOT / "prompts"

# Maps the LLM's per-entity ``category`` value to the top-level dict key the
# downstream art consumers read. Single source of truth for both the tool
# schema's enum and the assembly grouping.
CATEGORY_TO_KEY: dict[str, str] = {
    "legendary_character": "legendary_characters",
    "creature_type": "creature_types",
    "faction": "factions",
    "landmark": "landmarks",
}

CATEGORY_VALUES: list[str] = list(CATEGORY_TO_KEY)

# Order the category dicts appear in the written JSON (stable, human-readable).
_OUTPUT_CATEGORY_ORDER: list[str] = [
    "legendary_characters",
    "creature_types",
    "factions",
    "landmarks",
]


# ---------------------------------------------------------------------------
# Tool schema: defines the structured output the LLM must return
# ---------------------------------------------------------------------------

VISUAL_REF_TOOL_SCHEMA: dict = {
    "name": "submit_visual_references",
    "description": (
        "Submit the visual reference sheet for the custom MTG set: concrete "
        "plain-English appearance descriptions of every setting-specific "
        "entity, plus set-wide visual motifs, for the art-generation pipeline."
    ),
    "input_schema": {
        "type": "object",
        "required": ["entities", "visual_motifs"],
        "properties": {
            "entities": {
                "type": "array",
                "description": "One entry per setting-specific entity",
                "items": {
                    "type": "object",
                    "required": ["category", "key", "name", "visual_description"],
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": CATEGORY_VALUES,
                            "description": "Which kind of entity this is",
                        },
                        "key": {
                            "type": "string",
                            "description": "Short lowercase identifier (e.g. 'moktar')",
                        },
                        "name": {
                            "type": "string",
                            "description": "Proper display name",
                        },
                        "visual_description": {
                            "type": "string",
                            "description": (
                                "2-5 sentences of concrete, renderable appearance "
                                "(no backstory). Legendary characters start with "
                                "'Name: ' then the description."
                            ),
                        },
                        "flux_replacement": {
                            "type": "string",
                            "description": (
                                "Optional short generic phrase to substitute for an "
                                "invented word so Flux can render it"
                            ),
                        },
                    },
                },
            },
            "visual_motifs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "4-8 short set-wide art-direction notes",
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


def _format_characters_block(theme: dict) -> str:
    """Render the named-character hints for the system prompt.

    Surfaces each legendary's name, colors, role, and type so the model
    knows which individuals need a portrait-grade visual description.
    """
    legends = theme.get("legendary_characters") or []
    lines: list[str] = []
    for entry in legends:
        if isinstance(entry, dict):
            name = entry.get("name")
            if not name:
                continue
            role = entry.get("role") or entry.get("description") or ""
            type_line = entry.get("type") or entry.get("type_line") or ""
            header = f"- {name}"
            extras = [str(x).strip() for x in (type_line, role) if x]
            if extras:
                header += " — " + "; ".join(extras)
            lines.append(header)
        elif isinstance(entry, str) and entry.strip():
            lines.append(f"- {entry.strip()}")
    return "\n".join(lines) if lines else "(no named characters called out)"


def _format_creature_types_block(creature_types: Any) -> str:
    """Render setting-specific creature types, tolerating list or dict shape.

    theme.json stores creature types either as a flat list or as a dict with
    ``setting_specific`` / ``standard_mtg`` buckets. We only surface the
    setting-specific names — standard MTG types don't need a custom look.
    """
    names: list[str] = []
    if isinstance(creature_types, dict):
        for n in creature_types.get("setting_specific") or []:
            if isinstance(n, str) and n.strip():
                names.append(n.strip())
    elif isinstance(creature_types, list):
        for ct in creature_types:
            if isinstance(ct, str) and ct.strip():
                names.append(ct.strip())
            elif isinstance(ct, dict):
                n = ct.get("name") or ct.get("type")
                if n:
                    names.append(str(n).strip())
    return ", ".join(names) if names else "(no setting-specific creature types called out)"


def build_visual_reference_prompts(theme: dict, set_name: str) -> tuple[str, str]:
    """Render the visual-reference extraction system + user prompts."""
    sys_template = _read_template("visual_references_system.txt")
    user_template = _read_template("visual_references_user.txt")

    system_prompt = sys_template.format(
        set_name=set_name or "(unnamed set)",
        setting_block=_format_setting_block(theme),
        characters_block=_format_characters_block(theme),
        creature_types_block=_format_creature_types_block(theme.get("creature_types")),
    )
    user_prompt = user_template
    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Flat-entity -> nested-category assembly
# ---------------------------------------------------------------------------


def _slugify_key(raw: object) -> str | None:
    """Lowercase, collapse whitespace/punctuation to single spaces.

    The art consumers match keys as lowercase substrings of card text
    (``key in search_text``), so we keep internal spaces but strip edge
    punctuation. Returns ``None`` for anything that slugs to empty.
    """
    if not isinstance(raw, str):
        return None
    slug = re.sub(r"[^a-z0-9]+", " ", raw.lower()).strip()
    return slug or None


def assemble_visual_references(entities: Any, motifs: Any) -> dict:
    """Turn the flat LLM entity list into the nested category-dict schema.

    Groups each entity under its category's top-level key, slugifies the
    key, dedupes (first entity wins per key within a category), and builds
    the ``flux_term_replacements`` map from any entity carrying a
    non-empty ``flux_replacement``. Malformed entries (not a dict, unknown
    category, empty key or description) are dropped. ``visual_motifs`` is
    coerced to a list of non-empty strings.

    The returned dict always contains all four category keys (possibly
    empty), ``flux_term_replacements``, and ``visual_motifs`` — so
    downstream ``.get(...)`` reads never hit a surprise ``KeyError``.
    """
    result: dict[str, Any] = {key: {} for key in _OUTPUT_CATEGORY_ORDER}
    flux_replacements: dict[str, str] = {}

    if isinstance(entities, list):
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            category = ent.get("category")
            top_key = CATEGORY_TO_KEY.get(category) if isinstance(category, str) else None
            if top_key is None:
                continue
            slug = _slugify_key(ent.get("key"))
            if slug is None:
                continue
            desc = ent.get("visual_description")
            if not isinstance(desc, str) or not desc.strip():
                continue
            if slug in result[top_key]:
                continue  # first entity wins for this key
            result[top_key][slug] = desc.strip()

            replacement = ent.get("flux_replacement")
            if isinstance(replacement, str) and replacement.strip():
                flux_replacements.setdefault(slug, replacement.strip())

    result["flux_term_replacements"] = flux_replacements

    clean_motifs: list[str] = []
    if isinstance(motifs, list):
        for m in motifs:
            if isinstance(m, str) and m.strip():
                clean_motifs.append(m.strip())
    result["visual_motifs"] = clean_motifs

    return result


# ---------------------------------------------------------------------------
# On-disk loader (for downstream consumers)
# ---------------------------------------------------------------------------


def load_visual_references(asset_dir: Path | None = None) -> dict:
    """Load ``art-direction/visual-references.json`` for the active project.

    Returns ``{}`` when the file doesn't exist — parallels
    :func:`mtgai.generation.archetype_generator.load_archetypes`.
    """
    if asset_dir is None:
        from mtgai.io.asset_paths import set_artifact_dir

        asset_dir = set_artifact_dir()
    path = asset_dir / "art-direction" / "visual-references.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------


def generate_visual_references(*, theme: dict | None = None) -> dict:
    """Extract the set's visual references from setting prose via LLM.

    Reads ``theme.json`` from the active project (unless passed in),
    assembles the prompts, and calls ``generate_with_tool``. Returns::

        {
            "references": dict,   # the nested category-dict schema
            "input_tokens": int,
            "output_tokens": int,
            "model_id": str,
        }

    Raises ``RuntimeError`` if the model returns no usable entities (the
    runner translates this to a stage failure).
    """
    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    project = require_active_project()
    settings = project.settings
    sp = settings.set_params
    model_id = settings.get_llm_model_id("visual_refs")

    asset_dir = set_artifact_dir()
    # llmfacade writes each call's JSONL+HTML transcript here (named after the
    # tool); it's the canonical per-call log — no bespoke logger needed.
    log_dir = asset_dir / "art-direction" / "logs"
    if theme is None:
        theme_path = asset_dir / "theme.json"
        if not theme_path.exists():
            raise RuntimeError(f"theme.json not found at {theme_path} — run theme extraction first")
        theme = json.loads(theme_path.read_text(encoding="utf-8"))
    assert theme is not None

    system_prompt, user_prompt = build_visual_reference_prompts(
        theme=theme,
        set_name=sp.set_name or project.set_code or "Custom Set",
    )

    logger.info("Generating visual references (model=%s)", model_id)
    response = generate_with_tool(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_schema=VISUAL_REF_TOOL_SCHEMA,
        model=model_id,
        temperature=1.0,
        max_tokens=STANDARD,
        log_dir=log_dir,
    )

    result = response["result"]
    references = assemble_visual_references(
        result.get("entities") or [],
        result.get("visual_motifs") or [],
    )
    entity_count = sum(len(references[k]) for k in _OUTPUT_CATEGORY_ORDER)
    if entity_count == 0:
        raise RuntimeError(
            "Visual-reference generation produced no usable entities "
            "(every entry was malformed or empty)"
        )
    return {
        "references": references,
        "input_tokens": response.get("input_tokens", 0),
        "output_tokens": response.get("output_tokens", 0),
        # Provenance shows the base the user assigned, not the internal ctx twin.
        "model_id": settings.get_assigned_model_id("visual_refs"),
    }
