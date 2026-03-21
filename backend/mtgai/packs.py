"""Booster pack generation for limited play (draft and sealed).

Produces randomized booster packs following standard MTG distribution:
  10 Commons, 3 Uncommons, 1 Rare (with ~1/8 mythic upgrade), 1 Basic Land.
"""

from __future__ import annotations

import logging
import random

from mtgai.models.card import Card
from mtgai.models.enums import Rarity

logger = logging.getLogger(__name__)

# Standard booster slot counts
COMMON_COUNT = 10
UNCOMMON_COUNT = 3
RARE_COUNT = 1
LAND_COUNT = 1
MYTHIC_UPGRADE_CHANCE = 1 / 8

# Rarity sort order for pack presentation (rare first, like opening a pack)
_RARITY_SORT_ORDER = {
    Rarity.MYTHIC: 0,
    Rarity.RARE: 1,
    Rarity.UNCOMMON: 2,
    Rarity.COMMON: 3,
}


def _is_basic_land(card: Card) -> bool:
    """Check if a card is a basic land."""
    return "Basic Land" in card.type_line


def _partition_by_rarity(
    cards: list[Card],
) -> tuple[list[Card], list[Card], list[Card], list[Card], list[Card]]:
    """Split cards into commons, uncommons, rares, mythics, and basic lands.

    Basic lands are separated first (regardless of rarity field), then the
    remaining cards are bucketed by their rarity enum value.

    Returns:
        Tuple of (commons, uncommons, rares, mythics, basic_lands).
    """
    commons: list[Card] = []
    uncommons: list[Card] = []
    rares: list[Card] = []
    mythics: list[Card] = []
    basic_lands: list[Card] = []

    for card in cards:
        if _is_basic_land(card):
            basic_lands.append(card)
        elif card.rarity == Rarity.COMMON:
            commons.append(card)
        elif card.rarity == Rarity.UNCOMMON:
            uncommons.append(card)
        elif card.rarity == Rarity.RARE:
            rares.append(card)
        elif card.rarity == Rarity.MYTHIC:
            mythics.append(card)

    return commons, uncommons, rares, mythics, basic_lands


# WUBRG color order for balanced distribution
_WUBRG = ["W", "U", "B", "R", "G"]


def _get_primary_color(card: Card) -> str:
    """Return the card's primary color letter, 'M' for multi, 'C' for colorless."""
    if not card.color_identity:
        return "C"
    if len(card.color_identity) > 1:
        return "M"
    return card.color_identity[0].value


def _pick_color_balanced(
    pool: list[Card],
    count: int,
    rng: random.Random,
    exclude: list[Card],
) -> list[Card]:
    """Pick cards with color balance mimicking real MTG print sheet collation.

    Real MTG draft boosters use print sheet runs to guarantee color balance:
    - **Commons (10)**: All 5 WUBRG colors represented, ~2 per color.
      Multicolor/colorless are in a separate run and fill remaining slots.
    - **Uncommons (3)**: Drawn from A/B runs ensuring 3 different colors.

    Algorithm:
    1. Bucket available cards by primary color (WUBRG + multicolor + colorless)
    2. Guarantee pass: pick 1 from each WUBRG color (ensures all 5 represented)
    3. Round-robin pass: continue cycling WUBRG to fill remaining mono-color slots
    4. Fill remaining from multicolor/colorless pool (separate "run")
    5. Fall back to any remaining cards if pool is thin

    Args:
        pool: Cards to pick from (all same rarity).
        count: How many to pick.
        rng: Random number generator.
        exclude: Cards already in the pack (by identity).

    Returns:
        List of picked cards (may be fewer than count if pool is thin).
    """
    exclude_ids = {id(c) for c in exclude}
    available = [c for c in pool if id(c) not in exclude_ids]

    if len(available) <= count:
        if len(available) < count:
            logger.warning(
                "Only %d cards available (need %d) — filling what we can.",
                len(available),
                count,
            )
        return list(available)

    # Bucket by color
    by_color: dict[str, list[Card]] = {c: [] for c in [*_WUBRG, "M", "C"]}
    for card in available:
        color = _get_primary_color(card)
        by_color.setdefault(color, []).append(card)

    # Shuffle each bucket
    for bucket in by_color.values():
        rng.shuffle(bucket)

    picked: list[Card] = []
    picked_ids: set[int] = set()

    def _pick_from(bucket_key: str) -> bool:
        """Pick one card from a bucket. Returns True if successful."""
        bucket = by_color[bucket_key]
        while bucket:
            card = bucket.pop()
            if id(card) not in picked_ids:
                picked.append(card)
                picked_ids.add(id(card))
                return True
        return False

    # Phase 1 — Guarantee pass: one card from each WUBRG color.
    # Real draft boosters guarantee all 5 colors at common.
    # Randomize order so no color is systematically favored.
    color_order = list(_WUBRG)
    rng.shuffle(color_order)
    for color in color_order:
        if len(picked) >= count:
            break
        _pick_from(color)

    # Phase 2 — Round-robin pass: continue cycling WUBRG for remaining
    # mono-color slots (~1 more per color for commons, giving ~2 each).
    rng.shuffle(color_order)
    for color in color_order:
        if len(picked) >= count:
            break
        _pick_from(color)

    # Phase 3 — Multicolor/colorless fill (separate "run" in real collation).
    # Real sheets put multicolor + colorless on a dedicated run sheet.
    for fallback_key in ["M", "C"]:
        if len(picked) >= count:
            break
        while len(picked) < count and by_color.get(fallback_key):
            _pick_from(fallback_key)

    # Phase 4 — Overflow: if still short, take from any remaining WUBRG
    # (a third pass, for when count > 10 or pool is uneven).
    if len(picked) < count:
        rng.shuffle(color_order)
        for color in color_order:
            if len(picked) >= count:
                break
            _pick_from(color)

    # Phase 5 — Last resort: grab whatever's left (very thin pools).
    if len(picked) < count:
        all_remaining = [
            c for bucket in by_color.values() for c in bucket if id(c) not in picked_ids
        ]
        rng.shuffle(all_remaining)
        for card in all_remaining:
            if len(picked) >= count:
                break
            picked.append(card)
            picked_ids.add(id(card))

    return picked


def generate_booster_pack(
    cards: list[Card],
    seed: int | None = None,
) -> list[Card]:
    """Generate a randomized booster pack following standard MTG distribution.

    Standard composition: 10 commons, 3 uncommons, 1 rare/mythic, 1 basic land.
    The rare slot has a ~1/8 chance of being upgraded to a mythic.

    Args:
        cards: Full set card pool to draw from.
        seed: Optional RNG seed for reproducibility.

    Returns:
        List of Card objects forming a booster pack, sorted by rarity
        (rare/mythic first, then uncommon, common, land last).

    Raises:
        ValueError: If there are zero commons or zero uncommons in the pool
            (minimum needed to form any reasonable pack).
    """
    rng = random.Random(seed)
    commons, uncommons, rares, mythics, basic_lands = _partition_by_rarity(cards)

    # Hard requirement: need at least some commons and uncommons
    if not commons:
        raise ValueError("Cannot generate booster pack: no common cards in pool.")
    if not uncommons:
        raise ValueError("Cannot generate booster pack: no uncommon cards in pool.")

    pack: list[Card] = []

    # --- Rare / Mythic slot ---
    rare_or_mythic: Card | None = None
    if mythics and rng.random() < MYTHIC_UPGRADE_CHANCE:
        rare_or_mythic = rng.choice(mythics)
    elif rares:
        rare_or_mythic = rng.choice(rares)
    elif mythics:
        # No rares at all — fall back to mythic
        rare_or_mythic = rng.choice(mythics)
    else:
        logger.warning("No rares or mythics available — rare slot unfilled.")

    if rare_or_mythic:
        pack.append(rare_or_mythic)

    # --- Uncommon slots (color-balanced: try for 3 different colors) ---
    pack.extend(_pick_color_balanced(uncommons, UNCOMMON_COUNT, rng, pack))

    # --- Common slots (color-balanced: ~2 per color like real MTG collation) ---
    pack_ids = {id(c) for c in pack}
    available_commons = [c for c in commons if id(c) not in pack_ids]
    pack.extend(_pick_color_balanced(available_commons, COMMON_COUNT, rng, pack))

    # --- Basic land slot ---
    if basic_lands:
        pack_ids = {id(c) for c in pack}
        available_lands = [c for c in basic_lands if id(c) not in pack_ids]
        if available_lands:
            pack.append(rng.choice(available_lands))
        else:
            logger.warning("All basic lands already in pack — land slot skipped.")
    else:
        logger.warning("No basic lands in pool — land slot skipped.")

    # Sort: rare/mythic first, then uncommon, then common, then land last
    def _sort_key(card: Card) -> int:
        if _is_basic_land(card):
            return 4  # lands last
        return _RARITY_SORT_ORDER.get(card.rarity, 3)

    pack.sort(key=_sort_key)
    return pack


def generate_sealed_pool(
    cards: list[Card],
    num_packs: int = 6,
    seed: int | None = None,
) -> list[Card]:
    """Generate a sealed pool by combining multiple booster packs.

    Each pack is generated with its own sub-seed derived from the master seed
    so that individual packs are independently randomized but the overall pool
    is reproducible.

    Args:
        cards: Full set card pool to draw from.
        num_packs: Number of booster packs to open (default 6 for sealed).
        seed: Optional master RNG seed for reproducibility.

    Returns:
        Combined list of all cards from all packs, sorted by rarity.
    """
    master_rng = random.Random(seed)
    pool: list[Card] = []

    for i in range(num_packs):
        pack_seed = master_rng.randint(0, 2**31 - 1)
        pack = generate_booster_pack(cards, seed=pack_seed)
        logger.info("Pack %d: %d cards", i + 1, len(pack))
        pool.extend(pack)

    # Sort combined pool by rarity
    def _sort_key(card: Card) -> int:
        if _is_basic_land(card):
            return 4
        return _RARITY_SORT_ORDER.get(card.rarity, 3)

    pool.sort(key=_sort_key)
    return pool
