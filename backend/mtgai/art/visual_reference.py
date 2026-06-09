"""Visual reference dictionary for setting-specific creatures, factions, and landmarks.

Image generation models don't know what a Moktar or Morlock looks like. This module
loads plain-English visual descriptions from a JSON file and injects them into art
prompts when the card features a setting-specific entity.

The JSON file lives in the active project's asset folder at
``art-direction/visual-references.json``. This is a per-project data file produced
during set design (Phase 1A) or art direction (Phase 2A). The code is set-agnostic
— it just reads whatever JSON is provided.
"""

import json
import logging

logger = logging.getLogger(__name__)


def _load_visual_refs() -> dict:
    """Load the visual references JSON for the active project. Returns empty dict on failure."""
    from mtgai.io.asset_paths import set_artifact_dir

    path = set_artifact_dir() / "art-direction" / "visual-references.json"
    if not path.exists():
        logger.warning("No visual-references.json found at %s", path)
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("Failed to load visual references: %s", e)
        return {}


# Cache keyed by the active project's set_code so opening a different project
# doesn't pick up stale references from the previous one.
_cache: dict[str, dict] = {}


def get_refs() -> dict:
    """Get the visual references dict for the active project, with caching."""
    from mtgai.runtime.active_project import require_active_project

    set_code = require_active_project().set_code
    if set_code not in _cache:
        _cache[set_code] = _load_visual_refs()
    return _cache[set_code]


def detect_named_characters(
    card_name: str,
    type_line: str,
    oracle_text: str,
    flavor_text: str | None,
) -> list[str]:
    """Return list of legendary_characters keys that appear on this card."""
    refs = get_refs()
    characters = refs.get("legendary_characters", {})
    search_text = " ".join(
        filter(None, [card_name, type_line, oracle_text, flavor_text or ""])
    ).lower()
    return [key for key in characters if key in search_text]


def is_character_entity(entity_key: str) -> bool:
    """True when ``entity_key`` is a humanoid named character.

    PuLID-Flux locks a single *face*, so the local-Flux ref path conditions on
    ``legendary_characters`` entries only (the named, humanoid characters) — not
    creature types / factions / landmarks, which have no single identity. Used by
    the art-generation stage to decide whether a card's attached reference can
    drive face-lock conditioning.
    """
    return entity_key in get_refs().get("legendary_characters", {})


def get_character_appearance(entity_key: str) -> str | None:
    """The appearance prose for a ``legendary_characters`` entity, or ``None``.

    Feeds the late name->appearance substitution on the Flux path: the entity's
    name in an art prompt is swapped for this description (PuLID supplies the
    actual face), so the T5/CLIP text encoder — which can't resolve a name — still
    paints the right body/clothing/palette.
    """
    desc = get_refs().get("legendary_characters", {}).get(entity_key)
    return desc or None


def get_visual_references(
    card_name: str,
    type_line: str,
    oracle_text: str,
    flavor_text: str | None,
) -> str:
    """Return relevant visual reference text for a card.

    Searches the card's name, type_line, oracle_text, and flavor_text for
    keywords that match setting-specific entities, and returns concatenated
    visual descriptions for injection into the art prompt LLM call.
    """
    refs = get_refs()
    search_text = " ".join(
        filter(None, [card_name, type_line, oracle_text, flavor_text or ""])
    ).lower()

    results: list[str] = []
    seen: set[str] = set()

    # Check each category in priority order
    categories = [
        ("legendary_characters", "Character"),
        ("creature_types", "Creature Type"),
        ("factions", "Faction"),
        ("landmarks", "Location"),
    ]

    for category_key, label in categories:
        category = refs.get(category_key, {})
        for key, desc in category.items():
            if key in search_text and desc not in seen:
                results.append(f"[{label}: {key.title()}] {desc}")
                seen.add(desc)

    return "\n\n".join(results)


def get_flux_replacements() -> dict[str, str]:
    """Return the term replacement map for Flux prompt sanitization."""
    refs = get_refs()
    return refs.get("flux_term_replacements", {})


def get_set_art_direction() -> str:
    """Return the set-wide art-direction prose (``set_art_direction`` key).

    Produced by the Visual References stage's final step (frozen contract #2).
    Falls back to the older ``visual_motifs`` prose when the dedicated key is
    absent (pre-rework projects), then to ``""`` so the art-prompt LLM call just
    runs without a set-wide direction block.
    """
    refs = get_refs()
    direction = str(refs.get("set_art_direction") or "").strip()
    if direction:
        return direction
    motifs = refs.get("visual_motifs")
    if isinstance(motifs, list):
        motifs = ", ".join(str(m).strip() for m in motifs if str(m).strip())
    return str(motifs or "").strip()


def get_visual_motifs(limit: int = 3) -> list[str]:
    """Return the set's recurring visual motifs, cleaned and capped at ``limit``.

    The ``visual_motifs`` list in visual-references.json (e.g. "High-contrast
    metallic surfaces (glossy vs matte)") names recurring colors / materials /
    lighting the set's art should lean on. Unlike :func:`get_set_art_direction`
    (a paragraph of prose), these are short repeatable hints woven into every
    card's art prompt as a secondary style cue. Returns ``[]`` when none are
    present (or the value is malformed). ``limit=0`` returns the full list.
    """
    refs = get_refs()
    motifs = refs.get("visual_motifs")
    if not isinstance(motifs, list):
        return []
    cleaned = [str(m).strip() for m in motifs if str(m).strip()]
    return cleaned[:limit] if limit else cleaned


def get_cameo_entities() -> list[dict[str, str]]:
    """Return the style-guide entities eligible for an art cameo.

    Flattens the four keyed art-direction sub-dicts (``legendary_characters`` /
    ``creature_types`` / ``factions`` / ``landmarks``) into a flat list of
    ``{"key", "kind", "description"}`` records the art-prompt builder samples
    from when a per-card cameo roll hits. Returns ``[]`` when no references are
    available (no project / no refs file), so the cameo feature degrades to
    "never fires" rather than erroring.
    """
    refs = get_refs()
    categories = [
        ("legendary_characters", "character"),
        ("creature_types", "creature type"),
        ("factions", "faction"),
        ("landmarks", "location"),
    ]
    entities: list[dict[str, str]] = []
    for category_key, kind in categories:
        category = refs.get(category_key, {})
        if not isinstance(category, dict):
            continue
        for key, desc in category.items():
            text = str(desc or "").strip()
            if not text:
                continue
            entities.append({"key": str(key), "kind": kind, "description": text})
    return entities


# ---------------------------------------------------------------------------
# Artist directory (frozen contract #3: art-direction/artists.json)
# ---------------------------------------------------------------------------


def _load_artists() -> list[dict]:
    """Load ``art-direction/artists.json`` for the active project.

    Frozen shape ``{"artists": [{"name", "style_prompt"}, ...]}``. Returns an
    empty list when the file is absent or malformed — the consumer (art-prompt
    generation) degrades to leaving ``card.artist`` at its default and authoring
    a prompt with no artist style block.
    """
    from mtgai.io.asset_paths import set_artifact_dir

    path = set_artifact_dir() / "art-direction" / "artists.json"
    if not path.exists():
        logger.warning("No artists.json found at %s", path)
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("Failed to load artist directory: %s", e)
        return []
    raw = data.get("artists") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    artists: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        artists.append({"name": name, "style_prompt": str(entry.get("style_prompt") or "").strip()})
    return artists


# Artist-directory cache keyed by the active project's set_code, mirroring the
# ``_cache`` used for visual references so a project switch picks up the new file.
_artist_cache: dict[str, list[dict]] = {}


def get_artists() -> list[dict]:
    """Get the artist directory for the active project, with caching."""
    from mtgai.runtime.active_project import require_active_project

    set_code = require_active_project().set_code
    if set_code not in _artist_cache:
        _artist_cache[set_code] = _load_artists()
    return _artist_cache[set_code]
