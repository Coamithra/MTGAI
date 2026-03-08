"""Load and save Card and Set JSON files."""

from pathlib import Path

from mtgai.io.paths import card_json_path, set_dir
from mtgai.models.card import Card
from mtgai.models.set import Set


def save_card(card: Card, output_root: Path) -> Path:
    """Save a card as a JSON file. Returns the path written to."""
    path = card_json_path(output_root, card.set_code, card.collector_number, card.name)
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
