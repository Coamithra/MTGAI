"""Prefab data loading for the debug "use prefab" toggles.

When :class:`~mtgai.settings.model_settings.DebugSettings`'s
``use_prefab_cards`` / ``use_prefab_mechanics` flags are on, the
``card_gen`` / ``mechanics`` stages skip their LLM calls entirely and
install these pre-made artifacts instead. The point is iteration speed:
downstream stages (gates, art, render) can be exercised without paying
for — or waiting on — generation.

The prefab pool lives at ``<repo-root>/prefab_data/`` (a sibling of
``backend/``), populated by hand from a prior real run:

* ``prefab_data/cards/<collector>_<slug>.json`` — complete ``Card`` JSONs.
* ``prefab_data/mechanics/`` — a full mechanics selection: ``approved.json``
  + the same sidecars :func:`persist_mechanic_selection` writes.
"""

from pathlib import Path

from mtgai.io.atomic import atomic_write_text
from mtgai.models.card import Card

# <repo-root>/prefab_data — this file is at backend/mtgai/generation/prefab.py,
# so parents[3] is the repo root (the MTGAI folder that holds backend/).
PREFAB_ROOT = Path(__file__).resolve().parents[3] / "prefab_data"
PREFAB_CARDS_DIR = PREFAB_ROOT / "cards"
PREFAB_MECHANICS_DIR = PREFAB_ROOT / "mechanics"

# The selection files persist_mechanic_selection writes, in write order
# (approved.json — the marker downstream stages check — last).
_MECHANIC_FILES = (
    "candidates.json",
    "evergreen-keywords.json",
    "pointed-questions.json",
    "functional-tags.json",
    "pick-rationale.json",
    "approved.json",
)


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------


def prefab_cards_available() -> bool:
    """True when ``prefab_data/cards/`` holds at least one card JSON."""
    return PREFAB_CARDS_DIR.is_dir() and any(PREFAB_CARDS_DIR.glob("*.json"))


def load_prefab_cards() -> list[Card]:
    """Load every prefab card, sorted by filename (collector-number order)."""
    cards: list[Card] = []
    for p in sorted(PREFAB_CARDS_DIR.glob("*.json")):
        cards.append(Card.model_validate_json(p.read_text(encoding="utf-8")))
    return cards


# ---------------------------------------------------------------------------
# Mechanics
# ---------------------------------------------------------------------------


def prefab_mechanics_available() -> bool:
    """True when ``prefab_data/mechanics/approved.json`` exists."""
    return (PREFAB_MECHANICS_DIR / "approved.json").is_file()


def install_prefab_mechanics(mech_dir: Path) -> list[dict]:
    """Copy the prefab mechanics selection into ``mech_dir``.

    Mirrors :func:`persist_mechanic_selection`'s file set + write order
    (``approved.json`` last) so the Mechanics tab + downstream stages see a
    normal selection on disk. Returns the parsed ``approved.json`` list.
    """
    import json

    mech_dir.mkdir(parents=True, exist_ok=True)
    approved: list[dict] = []
    for name in _MECHANIC_FILES:
        src = PREFAB_MECHANICS_DIR / name
        if not src.exists():
            continue
        text = src.read_text(encoding="utf-8")
        atomic_write_text(mech_dir / name, text)
        if name == "approved.json":
            approved = json.loads(text)
    return approved
