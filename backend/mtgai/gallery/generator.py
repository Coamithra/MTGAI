"""Gallery generator — exports card data as JSON and builds the static gallery site.

Loads card models for a set, serializes them into a lightweight JSON file for
client-side filtering, and assembles the gallery directory with static assets
and rendered Jinja2 templates.
"""

from __future__ import annotations

import json
import logging
import shutil
import webbrowser
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from mtgai.models.card import Card
from mtgai.review.loaders import load_cards

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _project_root() -> Path:
    """Return the project root (parent of backend/)."""
    # generator.py -> gallery/ -> mtgai/ -> backend/ -> PROJECT_ROOT
    return Path(__file__).resolve().parent.parent.parent.parent


def _set_dir(set_code: str) -> Path:
    """Return the output directory for a set code."""
    return _project_root() / "output" / "sets" / set_code


def _templates_dir() -> Path:
    """Return the path to the gallery Jinja2 templates."""
    return Path(__file__).resolve().parent / "templates"


# ---------------------------------------------------------------------------
# Card serialization
# ---------------------------------------------------------------------------


def _card_to_gallery_dict(card: Card, gallery_dir: Path, set_dir: Path) -> dict:
    """Convert a Card model to a lightweight dict for the gallery JSON.

    Image paths are made relative to the gallery output directory so that
    ``../renders/...`` and ``../art/...`` resolve correctly when the HTML
    page is opened from the gallery directory.

    Args:
        card: The Card model to serialize.
        gallery_dir: The gallery output directory (for computing relative paths).
        set_dir: The set output directory (renders/ and art/ live here).

    Returns:
        A dict with only the fields the gallery needs.
    """
    # Build relative image paths from gallery dir to renders/art dirs.
    # Gallery lives at: output/sets/<SET>/gallery/
    # Renders at:       output/sets/<SET>/renders/<file>.png
    # Art at:           output/sets/<SET>/art/<file>.png
    # So relative path is ../renders/... and ../art/...

    render_path: str | None = None
    if card.render_path:
        # card.render_path is relative to set_dir (e.g. "renders/W-C-01_foo.png")
        render_abs = set_dir / card.render_path
        try:
            render_path = render_abs.relative_to(gallery_dir).as_posix()
        except ValueError:
            # Fall back to ../renders/... style path
            render_path = f"../{card.render_path}"

    art_path: str | None = None
    if card.art_path:
        art_abs = set_dir / card.art_path
        try:
            art_path = art_abs.relative_to(gallery_dir).as_posix()
        except ValueError:
            art_path = f"../{card.art_path}"

    return {
        "collector_number": card.collector_number,
        "name": card.name,
        "mana_cost": card.mana_cost,
        "cmc": card.cmc,
        "colors": [c.value for c in card.colors],
        "color_identity": [c.value for c in card.color_identity],
        "type_line": card.type_line,
        "oracle_text": card.oracle_text,
        "flavor_text": card.flavor_text,
        "power": card.power,
        "toughness": card.toughness,
        "rarity": card.rarity.value,
        "set_code": card.set_code,
        "render_path": render_path,
        "art_path": art_path,
        "mechanic_tags": list(card.mechanic_tags),
        "slot_id": card.slot_id,
        "is_reprint": card.is_reprint,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def export_cards_json(
    set_code: str,
    output_dir: Path,
    *,
    cards: list[Card] | None = None,
) -> Path:
    """Load all cards for a set and write them to a ``cards.json`` file.

    The JSON array contains one object per card with only the fields the
    gallery JavaScript needs for client-side filtering and display.

    Args:
        set_code: The set code (e.g. ``"ASD"``).
        output_dir: The gallery output directory. The JSON file is written to
            ``output_dir/data/cards.json``.
        cards: Optional pre-loaded card list. If *None*, cards are loaded
            from disk via ``load_cards(set_code)``.

    Returns:
        The path to the written ``cards.json`` file.
    """
    if cards is None:
        cards = load_cards(set_code)

    set_dir = _set_dir(set_code)
    gallery_dir = output_dir

    # Sort by collector_number (load_cards already sorts, but be explicit)
    cards_sorted = sorted(cards, key=lambda c: c.collector_number)

    gallery_dicts = [_card_to_gallery_dict(card, gallery_dir, set_dir) for card in cards_sorted]

    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    json_path = data_dir / "cards.json"
    json_path.write_text(
        json.dumps(gallery_dicts, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("Exported %d cards to %s", len(gallery_dicts), json_path)
    return json_path


def copy_static_assets(templates_dir: Path, output_dir: Path) -> None:
    """Copy static assets (CSS, JS) from templates to the gallery output.

    Copies ``templates_dir/static/`` to ``output_dir/static/``, overwriting
    any existing files.

    Args:
        templates_dir: Path to the gallery templates directory (contains
            a ``static/`` subdirectory with CSS/JS files).
        output_dir: The gallery output directory.
    """
    src = templates_dir / "static"
    dst = output_dir / "static"

    if not src.exists():
        logger.warning("No static assets found at %s", src)
        return

    # Remove existing static dir to get a clean copy
    if dst.exists():
        shutil.rmtree(dst)

    shutil.copytree(src, dst)
    logger.info("Copied static assets from %s to %s", src, dst)


def build_gallery(
    set_code: str,
    output_dir: Path | None = None,
    open_browser: bool = False,
) -> Path:
    """Build the full gallery for a set.

    Creates the output directory structure, exports card data as JSON,
    copies static assets, and renders Jinja2 templates.

    Args:
        set_code: The set code (e.g. ``"ASD"``).
        output_dir: Override gallery output directory. Defaults to
            ``output/sets/<SET_CODE>/gallery/``.
        open_browser: If *True*, open the gallery ``index.html`` in the
            default web browser after building.

    Returns:
        The gallery output directory path.
    """
    if output_dir is None:
        output_dir = _set_dir(set_code) / "gallery"

    # Create directory structure
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "data").mkdir(exist_ok=True)
    (output_dir / "static").mkdir(exist_ok=True)

    logger.info("Building gallery for set %s in %s", set_code, output_dir)

    # 1. Export card data
    cards = load_cards(set_code)
    export_cards_json(set_code, output_dir, cards=cards)

    # 2. Copy static assets
    templates_dir = _templates_dir()
    copy_static_assets(templates_dir, output_dir)

    # 3. Render Jinja2 templates
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=True,
    )

    # Render base.html as index.html
    template = env.get_template("base.html")
    index_html = template.render(
        set_code=set_code,
        card_count=len(cards),
    )
    index_path = output_dir / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    logger.info("Rendered index.html (%d cards)", len(cards))

    # 4. Optionally open in browser
    if open_browser:
        url = index_path.as_uri()
        logger.info("Opening gallery in browser: %s", url)
        webbrowser.open(url)

    logger.info("Gallery build complete: %s", output_dir)
    return output_dir
