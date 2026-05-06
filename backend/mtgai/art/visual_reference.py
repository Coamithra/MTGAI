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
