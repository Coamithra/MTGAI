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
import re

logger = logging.getLogger(__name__)

# Category -> human label, in priority order. Shared by the legacy substring
# matcher, the tag-driven lookup, and the entity catalog.
_CATEGORY_LABELS: tuple[tuple[str, str], ...] = (
    ("legendary_characters", "Character"),
    ("creature_types", "Creature Type"),
    ("factions", "Faction"),
    ("landmarks", "Location"),
)


def normalize_entity_key(s: str) -> str:
    """Canonical slug for an entity key: lowercase, non-alphanumeric runs → ``_``.

    The single normalization shared by the entity-tagging pass and the dictionary
    lookup so an ``optimus_prime`` tag matches an ``optimus prime`` dictionary key
    (and vice-versa) — the surface-form variance that broke the old substring
    matcher. Mirrors ``character_portraits._slugify``.
    """
    return re.sub(r"[^a-z0-9]+", "_", s.lower().strip()).strip("_")


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

    for category_key, label in _CATEGORY_LABELS:
        category = refs.get(category_key, {})
        for key, desc in category.items():
            if key in search_text and desc not in seen:
                results.append(f"[{label}: {key.title()}] {desc}")
                seen.add(desc)

    return "\n\n".join(results)


def _ref_index() -> dict[str, tuple[str, str, str]]:
    """Normalized lookup over the dictionary's keyed sub-dicts.

    ``{normalize_entity_key(key): (label, original_key, description)}``. Keyed by
    the canonical slug so a tag and a dictionary key whose surface forms differ
    (``optimus_prime`` vs ``optimus prime``) still resolve.
    """
    refs = get_refs()
    index: dict[str, tuple[str, str, str]] = {}
    for category_key, label in _CATEGORY_LABELS:
        category = refs.get(category_key, {})
        if not isinstance(category, dict):
            continue
        for key, desc in category.items():
            text = str(desc or "").strip()
            if not text:
                continue
            index.setdefault(normalize_entity_key(str(key)), (label, str(key), text))
    return index


def get_visual_references_for_keys(keys: list[str]) -> str:
    """Return the appearance-reference block for an explicit list of entity keys.

    The tag-driven replacement for :func:`get_visual_references` (substring): the
    unified entity-tagging pass decides which entities a card features, and this
    formats their dictionary appearance prose identically (``[Label: Key] desc``,
    deduped). Keys with no dictionary entry are skipped.
    """
    if not keys:
        return ""
    index = _ref_index()
    results: list[str] = []
    seen: set[str] = set()
    for key in keys:
        hit = index.get(normalize_entity_key(str(key)))
        if hit is None:
            continue
        label, original, desc = hit
        if desc in seen:
            continue
        seen.add(desc)
        results.append(f"[{label}: {original.title()}] {desc}")
    return "\n\n".join(results)


def get_entity_catalog() -> list[dict[str, str]]:
    """Flat ``[{entity_key, kind, name}]`` of every dictionary entity.

    Feeds the Art Prompts tab's add-tag picker (manual entity override). ``kind``
    uses the tag vocabulary (character / creature / faction / location). Returns
    ``[]`` when no references are available so the picker degrades to empty.
    """
    refs = get_refs()
    kinds = {
        "legendary_characters": "character",
        "creature_types": "creature",
        "factions": "faction",
        "landmarks": "location",
    }
    catalog: list[dict[str, str]] = []
    seen: set[str] = set()
    for category_key, _label in _CATEGORY_LABELS:
        category = refs.get(category_key, {})
        if not isinstance(category, dict):
            continue
        for key in category:
            slug = normalize_entity_key(str(key))
            if not slug or slug in seen:
                continue
            seen.add(slug)
            catalog.append(
                {"entity_key": slug, "kind": kinds[category_key], "name": str(key).title()}
            )
    return catalog


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
