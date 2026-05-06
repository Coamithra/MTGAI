"""Load and save Card and Set JSON files."""

from pathlib import Path

from mtgai.io.paths import card_slug, set_dir
from mtgai.models.card import Card
from mtgai.models.set import Set


def save_card(card: Card, output_root: Path | None = None, *, set_dir: Path | None = None) -> Path:
    """Save a card as a JSON file. Returns the path written to.

    Resolution order for the destination directory (highest priority first):

    1. ``set_dir`` — explicit override; the card lands at
       ``set_dir/cards/<slug>.json``. Stage runners that already resolved
       the project's artifact dir pass it here so the routing is
       guaranteed correct without a second helper call.
    2. The project's ``set_artifact_dir(card.set_code)`` — consulted when
       neither argument is provided, so even the legacy two-arg call
       sites honour the user's configured ``asset_folder``.
    3. ``output_root/sets/<CODE>/cards/`` — the original two-arg
       behaviour, kept for back-compat with scripts that pass an
       explicit root and don't want the helper consulted.
    """
    if set_dir is not None:
        target_dir = set_dir / "cards"
    elif output_root is None:
        from mtgai.io.asset_paths import set_artifact_dir

        target_dir = set_artifact_dir(card.set_code) / "cards"
    else:
        target_dir = output_root / "sets" / card.set_code.upper() / "cards"
    path = target_dir / f"{card_slug(card.collector_number, card.name)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(card.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_card(path: Path) -> Card:
    """Load a card from a JSON file."""
    return Card.model_validate_json(path.read_text(encoding="utf-8"))


def save_set(mtg_set: Set, output_root: Path) -> Path:
    """Save set metadata (without cards) as set.json."""
    path = set_dir(output_root, mtg_set.code) / "set.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    set_without_cards = mtg_set.model_copy(update={"cards": []})
    path.write_text(set_without_cards.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_set(path: Path) -> Set:
    """Load set metadata from a JSON file."""
    return Set.model_validate_json(path.read_text(encoding="utf-8"))
