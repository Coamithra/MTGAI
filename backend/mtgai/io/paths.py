"""Path conventions and naming helpers for card/set files.

These build the *legacy* ``output_root/sets/<CODE>/...`` layout from
explicit arguments — they do not consult ``settings.toml`` or honour
the project's ``asset_folder``. Production stage runners go through
:func:`mtgai.io.asset_paths.set_artifact_dir` instead. The helpers here
are kept for legacy CLI scripts (``backend/scripts/generate_all_art.py``,
``mtgai/art/kontext_*.py``, ``mtgai/art/pulid_test.py``) and as the
canonical definition of the on-disk slug / subdirectory shape.
"""

import re
from pathlib import Path


def card_slug(collector_number: str, card_name: str) -> str:
    """Generate a filesystem-safe slug from collector number and card name.

    Example: card_slug("001", "Lightning Bolt") -> "001_lightning_bolt"
    """
    slug = card_name.lower().replace(" ", "_")
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    return f"{collector_number}_{slug}"


def set_dir(output_root: Path, set_code: str) -> Path:
    """Return the output directory for a given set code.

    Example: set_dir(Path("output"), "DSK") -> Path("output/sets/DSK")
    """
    return output_root / "sets" / set_code.upper()


def card_json_path(output_root: Path, set_code: str, collector_number: str, name: str) -> Path:
    """Return the JSON file path for a card."""
    slug = card_slug(collector_number, name)
    return set_dir(output_root, set_code) / "cards" / f"{slug}.json"


def art_path(
    output_root: Path, set_code: str, collector_number: str, name: str, version: int = 1
) -> Path:
    """Return the art file path for a card (versioned)."""
    slug = card_slug(collector_number, name)
    return set_dir(output_root, set_code) / "art" / f"{slug}_v{version}.png"


def render_path(output_root: Path, set_code: str, collector_number: str, name: str) -> Path:
    """Return the rendered card image path."""
    slug = card_slug(collector_number, name)
    return set_dir(output_root, set_code) / "renders" / f"{slug}.png"
