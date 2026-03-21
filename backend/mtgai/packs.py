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

    # --- Uncommon slots ---
    uc_count = min(UNCOMMON_COUNT, len(uncommons))
    if uc_count < UNCOMMON_COUNT:
        logger.warning(
            "Only %d uncommons available (need %d) — filling what we can.",
            len(uncommons),
            UNCOMMON_COUNT,
        )
    pack.extend(rng.sample(uncommons, uc_count))

    # --- Common slots ---
    # Exclude any cards already in the pack (shouldn't happen across rarities, but safety)
    pack_ids = {id(c) for c in pack}
    available_commons = [c for c in commons if id(c) not in pack_ids]
    cm_count = min(COMMON_COUNT, len(available_commons))
    if cm_count < COMMON_COUNT:
        logger.warning(
            "Only %d commons available (need %d) — filling what we can.",
            len(available_commons),
            COMMON_COUNT,
        )
    pack.extend(rng.sample(available_commons, cm_count))

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
