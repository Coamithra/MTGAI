"""Data loaders for the review CLI.

Reads skeleton.json, theme.json, and generated card JSON files
from the output directory for a given set code.

Provides filtering and sorting for Card models.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from mtgai.models.card import Card
from mtgai.models.enums import Color, Rarity
from mtgai.skeleton.generator import BalanceReport, SetConfig, SkeletonResult, SkeletonSlot

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _project_root() -> Path:
    """Return the project root (parent of backend/)."""
    return Path(__file__).resolve().parent.parent.parent.parent


def _set_dir(set_code: str) -> Path:
    """Return the artifact directory for ``set_code``.

    Routes through :func:`mtgai.io.asset_paths.set_artifact_dir` so reads
    follow the project's configured ``asset_folder`` when one is set,
    otherwise the legacy ``output/sets/<CODE>/`` location.
    """
    from mtgai.io.asset_paths import set_artifact_dir

    return set_artifact_dir()


# ---------------------------------------------------------------------------
# Skeleton & theme loaders (unchanged)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Card loaders
# ---------------------------------------------------------------------------


def load_cards_raw(set_code: str = "ASD") -> list[dict]:
    """Load generated card JSON files as raw dicts.

    Backward-compatible loader for code that expects dicts with .get() access.
    Returns a list of parsed dicts sorted by filename (collector_number order).
    """
    cards_dir = _set_dir(set_code) / "cards"
    if not cards_dir.exists():
        return []

    cards: list[dict] = []
    for card_path in sorted(cards_dir.glob("*.json")):
        raw = json.loads(card_path.read_text(encoding="utf-8"))
        cards.append(raw)
    return cards


def load_cards(
    set_code: str = "ASD",
    cards_dir: Path | None = None,
) -> list[Card]:
    """Load generated card JSON files as Card models.

    Parses each JSON file through the Pydantic Card model. Malformed files
    are logged and skipped. Results are sorted by collector_number.

    Args:
        set_code: Set code to load from (ignored if cards_dir is provided).
        cards_dir: Override directory to load from (useful for testing).

    Returns:
        List of Card models sorted by collector_number.
    """
    if cards_dir is None:
        cards_dir = _set_dir(set_code) / "cards"

    if not cards_dir.exists():
        return []

    cards: list[Card] = []
    for card_path in sorted(cards_dir.glob("*.json")):
        try:
            raw = json.loads(card_path.read_text(encoding="utf-8"))
            card = Card(**raw)
            cards.append(card)
        except Exception:
            logger.warning("Skipping malformed card file: %s", card_path.name, exc_info=True)

    # Sort by collector_number (natural string sort works for our format)
    cards.sort(key=lambda c: c.collector_number)
    return cards


# ---------------------------------------------------------------------------
# Card filter
# ---------------------------------------------------------------------------

# Rarity ordering used for sorting
RARITY_ORDER: dict[Rarity, int] = {
    Rarity.COMMON: 0,
    Rarity.UNCOMMON: 1,
    Rarity.RARE: 2,
    Rarity.MYTHIC: 3,
}

# WUBRG color ordering used for sorting
COLOR_ORDER: dict[Color, int] = {
    Color.WHITE: 0,
    Color.BLUE: 1,
    Color.BLACK: 2,
    Color.RED: 3,
    Color.GREEN: 4,
}


@dataclass
class CardFilter:
    """Filter criteria for cards. All non-None fields are AND-combined.

    Usage:
        filt = CardFilter(color="W", rarity="common")
        result = filter_cards(cards, filt)
    """

    # Color identity filter (W/U/B/R/G). Matches if the card's color_identity
    # contains this color.
    color: str | None = None

    # Rarity filter (common/uncommon/rare/mythic). Case-insensitive.
    rarity: str | None = None

    # Card type filter (creature/instant/sorcery/enchantment/artifact/land).
    # Substring match against type_line, case-insensitive.
    card_type: str | None = None

    # CMC filters
    cmc: float | None = None  # exact match
    cmc_min: float | None = None  # >= this value
    cmc_max: float | None = None  # <= this value

    # Keyword search: substring match in name, oracle_text, or type_line.
    # Case-insensitive.
    keyword: str | None = None

    # Mechanic tag filter: matches against mechanic_tags list.
    # Case-insensitive.
    mechanic: str | None = None

    # Set mechanic name in oracle text (e.g. "Salvage", "Malfunction", "Overclock").
    # Case-insensitive substring match in oracle_text.
    mechanic_name: str | None = None

    # Multiple colors (OR within this list, AND with other filters).
    # E.g., colors=["W", "U"] matches cards with W or U in color_identity.
    colors: list[str] = field(default_factory=list)


def filter_cards(cards: list[Card], filt: CardFilter) -> list[Card]:
    """Filter a list of Card models using AND-combined criteria.

    Args:
        cards: Cards to filter.
        filt: Filter criteria (all non-None fields are AND-combined).

    Returns:
        Filtered list of Card models (order preserved).
    """
    result = list(cards)

    # Color filter (single)
    if filt.color is not None:
        color_val = filt.color.strip().upper()
        result = [c for c in result if any(ci.value == color_val for ci in c.color_identity)]

    # Colors filter (multi, OR within)
    if filt.colors:
        color_vals = {cv.strip().upper() for cv in filt.colors}
        result = [c for c in result if any(ci.value in color_vals for ci in c.color_identity)]

    # Rarity filter
    if filt.rarity is not None:
        rarity_val = filt.rarity.strip().lower()
        result = [c for c in result if c.rarity.value == rarity_val]

    # Card type filter (substring in type_line)
    if filt.card_type is not None:
        type_val = filt.card_type.strip().lower()
        result = [c for c in result if type_val in c.type_line.lower()]

    # CMC exact
    if filt.cmc is not None:
        result = [c for c in result if c.cmc == filt.cmc]

    # CMC min
    if filt.cmc_min is not None:
        result = [c for c in result if c.cmc >= filt.cmc_min]

    # CMC max
    if filt.cmc_max is not None:
        result = [c for c in result if c.cmc <= filt.cmc_max]

    # Keyword search (name, oracle_text, type_line)
    if filt.keyword is not None:
        kw = filt.keyword.strip().lower()
        result = [
            c
            for c in result
            if kw in c.name.lower() or kw in c.oracle_text.lower() or kw in c.type_line.lower()
        ]

    # Mechanic tag filter
    if filt.mechanic is not None:
        mech_val = filt.mechanic.strip().lower()
        result = [c for c in result if any(t.lower() == mech_val for t in c.mechanic_tags)]

    # Set mechanic name in oracle text
    if filt.mechanic_name is not None:
        mname = filt.mechanic_name.strip().lower()
        result = [c for c in result if mname in c.oracle_text.lower()]

    return result


# ---------------------------------------------------------------------------
# Card sorting
# ---------------------------------------------------------------------------

# Valid sort keys
SORT_KEYS = {"name", "cmc", "rarity", "color", "collector_number"}


def sort_cards(
    cards: list[Card],
    sort_by: str = "collector_number",
    reverse: bool = False,
) -> list[Card]:
    """Sort a list of Card models by the given key.

    Args:
        cards: Cards to sort.
        sort_by: One of "name", "cmc", "rarity", "color", "collector_number".
        reverse: If True, sort descending.

    Returns:
        New sorted list of Card models.

    Raises:
        ValueError: If sort_by is not a recognized key.
    """
    if sort_by not in SORT_KEYS:
        raise ValueError(
            f"Unknown sort key '{sort_by}'. Valid keys: {', '.join(sorted(SORT_KEYS))}"
        )

    def _color_sort_key(card: Card) -> tuple[int, ...]:
        """Sort colorless first, then by WUBRG order of first color."""
        if not card.color_identity:
            return (-1,)
        return tuple(COLOR_ORDER.get(c, 99) for c in card.color_identity)

    key_fns = {
        "name": lambda c: c.name.lower(),
        "cmc": lambda c: c.cmc,
        "rarity": lambda c: RARITY_ORDER.get(c.rarity, 99),
        "color": _color_sort_key,
        "collector_number": lambda c: c.collector_number,
    }

    return sorted(cards, key=key_fns[sort_by], reverse=reverse)
