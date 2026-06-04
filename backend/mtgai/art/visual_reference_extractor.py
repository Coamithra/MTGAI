"""Visual-reference + artist-directory generation — a transform over ``theme.json``.

Wired into the pipeline as the ``visual_refs`` stage (just before
``art_prompts``, its earliest consumer — the art stages are the only ones that
read its output). The runner in ``mtgai.pipeline.stages`` does the
orchestration; this module owns the prompt assembly, tool-schema contracts, the
flat-entity -> nested-category assembly, and the on-disk loaders.

This stage is a **transform**, not a re-extraction. The theme extractor already
paints art-grade visual detail for the four entity classes (creature types,
factions, landmarks, notable characters) inside ``theme.json`` — both as the
``setting`` markdown document (``# Creature Types`` / ``# Factions`` / ``#
Landmarks`` / ``# Notable Characters`` / ``# Races`` sections) and, when present,
as structured ``legendary_characters`` / ``notable_cards`` / ``creature_types``
fields. The job here is to normalize that into the slug-keyed, machine-readable
art-direction dictionary the art consumers need, *enriching* each entry into a
consistent, full visual brief (age, build, height, face, hair, skin, clothing,
equipment, palette, demeanor, distinguishing features) and filling gaps where
the theme is thin — so the same character always paints the same way. The
genuinely non-redundant pieces with no theme equivalent are produced fresh:
``flux_term_replacements`` (invented-word -> renderable phrase) and
``visual_motifs`` (set-wide art-direction notes).

Three artifacts come out of the stage:

* ``<asset>/art-direction/visual-references.json`` — the keyed dictionary
  (``legendary_characters`` / ``creature_types`` / ``factions`` / ``landmarks``
  + ``flux_term_replacements`` + ``visual_motifs`` + the ``set_art_direction``
  set-wide prose), consumed by ``mtgai.art.visual_reference`` and
  ``mtgai.art.character_portraits``.
* ``<asset>/art-direction/artists.json`` — the made-up artist directory
  (``{"artists": [{"name", "style_prompt"}]}``), consumed by ``art_prompts``.

Prompt templates live in the pipeline prompts dir:

* ``visual_references_system.txt`` / ``visual_references_user.txt`` — dictionary
* ``artist_directory_system.txt`` / ``artist_directory_user.txt``   — artists
* ``set_art_direction_system.txt`` / ``set_art_direction_user.txt`` — set prose
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from mtgai.generation import temperatures as temps
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

# Artist-directory sizing. A modern MTG set (~250-300 cards) credits ~70-90
# artists, but the card explicitly wants FEWER (a coherent, reusable handful)
# with >= ~10 cards per artist. ``set_size / 18`` lands around 12-18 cards per
# artist, clamped to a sane band so a tiny or huge set still gets a workable
# directory.
ARTISTS_PER_CARD_DIVISOR = 18
MIN_ARTISTS = 8
MAX_ARTISTS = 20


def target_artist_count(set_size: int) -> int:
    """How many made-up artists to generate for a set of ``set_size`` cards."""
    if set_size <= 0:
        return MIN_ARTISTS
    raw = round(set_size / ARTISTS_PER_CARD_DIVISOR)
    return max(MIN_ARTISTS, min(MAX_ARTISTS, raw))


# ---------------------------------------------------------------------------
# Tool schemas: define the structured output each LLM call must return
# ---------------------------------------------------------------------------

VISUAL_REF_TOOL_SCHEMA: dict = {
    "name": "submit_visual_references",
    "description": (
        "Submit the art-direction dictionary for the custom MTG set: a "
        "consistent, full visual brief for every setting-specific entity, plus "
        "set-wide motifs and Flux term replacements, for the art pipeline."
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
                                "A full, consistent art-direction brief (3-6 "
                                "sentences) so the same entity always paints the "
                                "same way: age/era, build, scale, face, hair/facial "
                                "hair, skin/materials, clothing/armor, equipment, "
                                "color palette, mood, distinguishing features. "
                                "Appearance only, no backstory. Legendary "
                                "characters start with 'Name: ' then the brief."
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

ARTIST_DIRECTORY_TOOL_SCHEMA: dict = {
    "name": "submit_artist_directory",
    "description": (
        "Submit a directory of made-up illustrators for the set. Each has a "
        "distinct, recognizable style so art across the set varies the way a "
        "real MTG set's mix of artists does."
    ),
    "input_schema": {
        "type": "object",
        "required": ["artists"],
        "properties": {
            "artists": {
                "type": "array",
                "description": "The artist roster",
                "items": {
                    "type": "object",
                    "required": ["name", "style_prompt"],
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": (
                                "A made-up illustrator name (do NOT copy a real "
                                "MTG artist's name). Plausible, varied origins."
                            ),
                        },
                        "style_prompt": {
                            "type": "string",
                            "description": (
                                "1-3 sentences describing this artist's signature "
                                "style — medium, brushwork, palette tendencies, "
                                "composition, mood, subject affinity — as guidance "
                                "an image model can act on."
                            ),
                        },
                    },
                },
            }
        },
    },
}

SET_ART_DIRECTION_TOOL_SCHEMA: dict = {
    "name": "submit_set_art_direction",
    "description": (
        "Submit the set-wide art direction: the overall aesthetic, palette "
        "strategy, lighting, materials, and mood that should pervade every card."
    ),
    "input_schema": {
        "type": "object",
        "required": ["set_art_direction"],
        "properties": {
            "set_art_direction": {
                "type": "string",
                "description": (
                    "2-4 paragraphs of set-wide art direction grounded in the "
                    "theme and good creative sense. Interesting but still within "
                    "MTG's painterly house style (no pixel art / radical "
                    "stylization). Cover overall aesthetic, palette strategy "
                    "(per-color or set-wide), lighting, recurring materials, and "
                    "mood."
                ),
            }
        },
    },
}


# ---------------------------------------------------------------------------
# Theme -> prompt source assembly
# ---------------------------------------------------------------------------


def _read_template(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def _format_setting_block(theme: dict) -> str:
    """The full painted setting prose for the prompt.

    The theme extractor stores its rich, art-grade extraction document under
    ``setting`` (markdown with ``# Creature Types`` / ``# Factions`` / ``#
    Landmarks`` / ``# Notable Characters`` / ``# Races`` sections). Legacy
    short-form themes use a ``theme`` one-liner plus a ``flavor_description``
    blob. We surface the one-liner (if any) then the prose so neither schema
    loses content — this is the richer source the transform reads.
    """
    one_liner = (theme.get("theme") or "").strip()
    prose = (theme.get("setting") or theme.get("flavor_description") or "").strip()
    parts = [p for p in (one_liner, prose) if p]
    return "\n\n".join(parts) if parts else "(no setting provided)"


def _format_characters_block(theme: dict) -> str:
    """Render the structured legendary-character anchors for the prompt.

    Surfaces each legendary's name, colors, role, and type so the transform
    knows which individuals need a full portrait-grade brief — and threads in
    the theme's own painted ``role`` text as the starting point to enrich.
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
    if not lines:
        return "(no structured named characters — read the setting prose)"
    return "\n".join(lines)


def _format_notable_cards_block(theme: dict) -> str:
    """Render structured notable_cards (artifacts/vehicles/places) as anchors."""
    notable = theme.get("notable_cards") or []
    lines: list[str] = []
    for entry in notable:
        if isinstance(entry, dict):
            name = entry.get("name")
            if not name:
                continue
            type_line = entry.get("type") or entry.get("type_line") or ""
            notes = entry.get("notes") or entry.get("description") or ""
            header = f"- {name}"
            extras = [str(x).strip() for x in (type_line, notes) if x]
            if extras:
                header += " — " + "; ".join(extras)
            lines.append(header)
        elif isinstance(entry, str) and entry.strip():
            lines.append(f"- {entry.strip()}")
    return "\n".join(lines) if lines else "(none called out)"


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
    return ", ".join(names) if names else "(none called out — read the setting prose)"


def build_visual_reference_prompts(theme: dict, set_name: str) -> tuple[str, str]:
    """Render the visual-dictionary transform system + user prompts."""
    sys_template = _read_template("visual_references_system.txt")
    user_template = _read_template("visual_references_user.txt")

    system_prompt = sys_template.format(
        set_name=set_name or "(unnamed set)",
        setting_block=_format_setting_block(theme),
        characters_block=_format_characters_block(theme),
        notable_cards_block=_format_notable_cards_block(theme),
        creature_types_block=_format_creature_types_block(theme.get("creature_types")),
    )
    return system_prompt, user_template


def build_artist_directory_prompts(theme: dict, set_name: str, count: int) -> tuple[str, str]:
    """Render the artist-directory system + user prompts."""
    sys_template = _read_template("artist_directory_system.txt")
    user_template = _read_template("artist_directory_user.txt")

    system_prompt = sys_template.format(
        set_name=set_name or "(unnamed set)",
        setting_block=_format_setting_block(theme),
        count=count,
    )
    user_prompt = user_template.format(count=count)
    return system_prompt, user_prompt


def build_set_art_direction_prompts(theme: dict, set_name: str) -> tuple[str, str]:
    """Render the set-wide art-direction system + user prompts."""
    sys_template = _read_template("set_art_direction_system.txt")
    user_template = _read_template("set_art_direction_user.txt")

    system_prompt = sys_template.format(
        set_name=set_name or "(unnamed set)",
        setting_block=_format_setting_block(theme),
    )
    return system_prompt, user_template


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


def assemble_artists(artists: Any) -> list[dict[str, str]]:
    """Coerce the LLM artist list into ``[{name, style_prompt}]`` (frozen shape).

    Drops malformed / empty entries and dedupes by lowercase name (first wins),
    so the directory never carries a junk or duplicate artist.
    """
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    if not isinstance(artists, list):
        return out
    for a in artists:
        if not isinstance(a, dict):
            continue
        name = a.get("name")
        style = a.get("style_prompt")
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(style, str) or not style.strip():
            continue
        name = name.strip()
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "style_prompt": style.strip()})
    return out


# ---------------------------------------------------------------------------
# On-disk loaders (for downstream consumers)
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


def load_artists(asset_dir: Path | None = None) -> list[dict[str, str]]:
    """Load ``art-direction/artists.json`` for the active project.

    Returns the ``artists`` list (``[]`` when the file or key is missing) —
    the frozen ``art_prompts`` consumer shape.
    """
    if asset_dir is None:
        from mtgai.io.asset_paths import set_artifact_dir

        asset_dir = set_artifact_dir()
    path = asset_dir / "art-direction" / "artists.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    artists = data.get("artists") if isinstance(data, dict) else None
    return assemble_artists(artists)


# ---------------------------------------------------------------------------
# Generation functions
# ---------------------------------------------------------------------------


def _load_theme(theme: dict | None, asset_dir: Path) -> dict:
    if theme is not None:
        return theme
    theme_path = asset_dir / "theme.json"
    if not theme_path.exists():
        raise RuntimeError(f"theme.json not found at {theme_path} — run theme extraction first")
    return json.loads(theme_path.read_text(encoding="utf-8"))


def generate_visual_references(*, theme: dict | None = None) -> dict:
    """Transform ``theme.json`` into the keyed art-direction dictionary.

    Reads ``theme.json`` from the active project (unless passed in), assembles
    the transform prompt (structured anchors + the full painted setting prose),
    and calls ``generate_with_tool``. Returns::

        {
            "references": dict,   # nested category-dict schema (no set_art_direction)
            "input_tokens": int,
            "output_tokens": int,
            "model_id": str,
        }

    Raises ``RuntimeError`` if the model returns no usable entities (the runner
    translates this to a stage failure). The set-wide ``set_art_direction`` is a
    separate call (:func:`generate_set_art_direction`) — the runner merges it.
    """
    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    project = require_active_project()
    settings = project.settings
    sp = settings.set_params
    model_id = settings.get_llm_model_id("visual_refs")

    asset_dir = set_artifact_dir()
    log_dir = asset_dir / "art-direction" / "logs"
    theme = _load_theme(theme, asset_dir)

    system_prompt, user_prompt = build_visual_reference_prompts(
        theme=theme,
        set_name=sp.set_name or project.set_code or "Custom Set",
    )

    logger.info("Transforming theme into visual references (model=%s)", model_id)
    response = generate_with_tool(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_schema=VISUAL_REF_TOOL_SCHEMA,
        model=model_id,
        temperature=temps.CREATIVE,
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


def generate_artists(*, theme: dict | None = None, count: int | None = None) -> dict:
    """Generate the made-up artist directory for the set.

    ``count`` defaults to :func:`target_artist_count` of the project's
    ``set_size``. Returns::

        {"artists": list[{name, style_prompt}], "model_id": str,
         "input_tokens": int, "output_tokens": int}

    Raises ``RuntimeError`` if the model returns no usable artists.
    """
    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    project = require_active_project()
    settings = project.settings
    sp = settings.set_params
    model_id = settings.get_llm_model_id("visual_refs")

    asset_dir = set_artifact_dir()
    log_dir = asset_dir / "art-direction" / "logs"
    theme = _load_theme(theme, asset_dir)

    resolved_count = (
        count if (isinstance(count, int) and count > 0) else target_artist_count(sp.set_size or 0)
    )

    system_prompt, user_prompt = build_artist_directory_prompts(
        theme=theme,
        set_name=sp.set_name or project.set_code or "Custom Set",
        count=resolved_count,
    )

    logger.info("Generating artist directory (count=%d, model=%s)", resolved_count, model_id)
    response = generate_with_tool(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_schema=ARTIST_DIRECTORY_TOOL_SCHEMA,
        model=model_id,
        temperature=temps.CREATIVE,
        max_tokens=STANDARD,
        log_dir=log_dir,
    )

    artists = assemble_artists(response["result"].get("artists") or [])
    if not artists:
        raise RuntimeError(
            "Artist-directory generation produced no usable artists "
            "(every entry was malformed or empty)"
        )
    return {
        "artists": artists,
        "input_tokens": response.get("input_tokens", 0),
        "output_tokens": response.get("output_tokens", 0),
        "model_id": settings.get_assigned_model_id("visual_refs"),
    }


def generate_set_art_direction(*, theme: dict | None = None) -> dict:
    """Generate the set-wide art-direction prose.

    Returns ``{"set_art_direction": str, "model_id": str, "input_tokens": int,
    "output_tokens": int}``. Raises ``RuntimeError`` if the model returns empty
    prose.
    """
    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    project = require_active_project()
    settings = project.settings
    sp = settings.set_params
    model_id = settings.get_llm_model_id("visual_refs")

    asset_dir = set_artifact_dir()
    log_dir = asset_dir / "art-direction" / "logs"
    theme = _load_theme(theme, asset_dir)

    system_prompt, user_prompt = build_set_art_direction_prompts(
        theme=theme,
        set_name=sp.set_name or project.set_code or "Custom Set",
    )

    logger.info("Generating set-wide art direction (model=%s)", model_id)
    response = generate_with_tool(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_schema=SET_ART_DIRECTION_TOOL_SCHEMA,
        model=model_id,
        temperature=temps.CREATIVE,
        max_tokens=STANDARD,
        log_dir=log_dir,
    )

    prose = response["result"].get("set_art_direction")
    if not isinstance(prose, str) or not prose.strip():
        raise RuntimeError("Set art-direction generation produced no usable prose")
    return {
        "set_art_direction": prose.strip(),
        "input_tokens": response.get("input_tokens", 0),
        "output_tokens": response.get("output_tokens", 0),
        "model_id": settings.get_assigned_model_id("visual_refs"),
    }
