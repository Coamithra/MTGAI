"""Data loaders for the review CLI.

Reads skeleton.json, theme.json, and generated card JSON files
from the output directory for a given set code.
"""

from __future__ import annotations

import json
from pathlib import Path

from mtgai.skeleton.generator import BalanceReport, SetConfig, SkeletonResult, SkeletonSlot


def _project_root() -> Path:
    """Return the project root (parent of backend/)."""
    return Path(__file__).resolve().parent.parent.parent.parent


def _set_dir(set_code: str) -> Path:
    """Return the output directory for a set code."""
    return _project_root() / "output" / "sets" / set_code


def load_skeleton(set_code: str = "ASD") -> SkeletonResult:
    """Load skeleton.json and parse it into a SkeletonResult.

    Raises FileNotFoundError if the skeleton file doesn't exist.
    """
    skeleton_path = _set_dir(set_code) / "skeleton.json"
    if not skeleton_path.exists():
        raise FileNotFoundError(
            f"No skeleton.json found at {skeleton_path}. Run the skeleton generator first."
        )

    raw = json.loads(skeleton_path.read_text(encoding="utf-8"))

    config = SetConfig(**raw["config"])
    slots = [SkeletonSlot(**s) for s in raw["slots"]]

    # Reconstruct balance report
    balance_raw = raw.get("balance_report", {})
    balance = BalanceReport(**balance_raw)

    # Reconstruct archetype_slots index
    archetype_slots = raw.get("archetype_slots", {})

    return SkeletonResult(
        config=config,
        slots=slots,
        balance_report=balance,
        archetype_slots=archetype_slots,
        total_slots=raw.get("total_slots", len(slots)),
    )


def load_theme(set_code: str = "ASD") -> dict | None:
    """Load theme.json if it exists. Returns the parsed dict or None."""
    theme_path = _set_dir(set_code) / "theme.json"
    if not theme_path.exists():
        return None
    return json.loads(theme_path.read_text(encoding="utf-8"))


def load_cards(set_code: str = "ASD") -> list[dict]:
    """Load generated card JSON files from output/sets/<code>/cards/.

    Returns a list of parsed card dicts (not Card models, to keep it loose
    until card generation is actually implemented).
    """
    cards_dir = _set_dir(set_code) / "cards"
    if not cards_dir.exists():
        return []

    cards: list[dict] = []
    for card_path in sorted(cards_dir.glob("*.json")):
        raw = json.loads(card_path.read_text(encoding="utf-8"))
        cards.append(raw)
    return cards
