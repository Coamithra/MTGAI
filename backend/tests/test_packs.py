"""Tests for booster pack generation (mtgai.packs)."""

from __future__ import annotations

import pytest

from mtgai.models.card import Card
from mtgai.models.enums import Rarity
from mtgai.packs import generate_booster_pack, generate_sealed_pool


def _make_card(
    name: str = "Test Card",
    rarity: Rarity = Rarity.COMMON,
    collector_number: str = "T-01",
    type_line: str = "Creature — Human",
) -> Card:
    """Create a minimal Card for testing."""
    return Card(
        name=name,
        rarity=rarity,
        collector_number=collector_number,
        type_line=type_line,
        set_code="TST",
    )


def _make_full_pool() -> list[Card]:
    """Create a card pool with plenty of each rarity + basic lands.

    20 commons, 10 uncommons, 5 rares, 3 mythics, 5 basic lands = 43 cards.
    """
    cards: list[Card] = []
    for i in range(20):
        cards.append(_make_card(f"Common {i}", Rarity.COMMON, f"C-{i:02d}"))
    for i in range(10):
        cards.append(_make_card(f"Uncommon {i}", Rarity.UNCOMMON, f"U-{i:02d}"))
    for i in range(5):
        cards.append(_make_card(f"Rare {i}", Rarity.RARE, f"R-{i:02d}"))
    for i in range(3):
        cards.append(_make_card(f"Mythic {i}", Rarity.MYTHIC, f"M-{i:02d}"))
    for i, land_name in enumerate(["Plains", "Island", "Swamp", "Mountain", "Forest"]):
        cards.append(
            _make_card(
                land_name,
                Rarity.COMMON,
                f"L-{i:02d}",
                type_line=f"Basic Land — {land_name}",
            )
        )
    return cards


class TestGenerateBoosterPack:
    """Tests for generate_booster_pack()."""

    def test_basic_pack_has_15_cards(self):
        pool = _make_full_pool()
        pack = generate_booster_pack(pool, seed=42)
        assert len(pack) == 15

    def test_rarity_distribution(self):
        pool = _make_full_pool()
        pack = generate_booster_pack(pool, seed=42)

        # Count by rarity (excluding basic lands)
        basics = [c for c in pack if "Basic Land" in c.type_line]
        non_basics = [c for c in pack if "Basic Land" not in c.type_line]

        commons = [c for c in non_basics if c.rarity == Rarity.COMMON]
        uncommons = [c for c in non_basics if c.rarity == Rarity.UNCOMMON]
        rares_mythics = [c for c in non_basics if c.rarity in (Rarity.RARE, Rarity.MYTHIC)]

        assert len(commons) == 10
        assert len(uncommons) == 3
        assert len(rares_mythics) == 1
        assert len(basics) == 1

    def test_no_duplicates_in_pack(self):
        pool = _make_full_pool()
        pack = generate_booster_pack(pool, seed=42)
        # Check by object identity — same Card object should not appear twice
        assert len(pack) == len(set(id(c) for c in pack))
        # Also check by collector number (more robust)
        collector_nums = [c.collector_number for c in pack]
        assert len(collector_nums) == len(set(collector_nums))

    def test_seeded_is_reproducible(self):
        pool = _make_full_pool()
        pack_a = generate_booster_pack(pool, seed=123)
        pack_b = generate_booster_pack(pool, seed=123)
        assert [c.name for c in pack_a] == [c.name for c in pack_b]

    def test_different_seeds_give_different_packs(self):
        pool = _make_full_pool()
        pack_a = generate_booster_pack(pool, seed=1)
        pack_b = generate_booster_pack(pool, seed=2)
        # Very unlikely to be identical with different seeds
        names_a = [c.name for c in pack_a]
        names_b = [c.name for c in pack_b]
        assert names_a != names_b

    def test_mythic_upgrade_frequency(self):
        """Over many packs, mythic upgrades should happen ~1/8 of the time."""
        pool = _make_full_pool()
        mythic_count = 0
        total_packs = 1000

        for seed in range(total_packs):
            pack = generate_booster_pack(pool, seed=seed)
            # The rare/mythic slot card (first card after sort)
            rare_slot = [
                c
                for c in pack
                if c.rarity in (Rarity.RARE, Rarity.MYTHIC) and "Basic Land" not in c.type_line
            ]
            if rare_slot and rare_slot[0].rarity == Rarity.MYTHIC:
                mythic_count += 1

        # Expected: 125 (1/8 of 1000). Allow wide tolerance for randomness.
        rate = mythic_count / total_packs
        assert 0.07 < rate < 0.20, f"Mythic upgrade rate {rate:.3f} outside expected range"

    def test_pack_sorted_rare_first(self):
        """Pack should be sorted: mythic/rare, uncommon, common, basic land."""
        pool = _make_full_pool()
        pack = generate_booster_pack(pool, seed=42)

        rarity_order = []
        for c in pack:
            if "Basic Land" in c.type_line:
                rarity_order.append(4)
            elif c.rarity == Rarity.MYTHIC:
                rarity_order.append(0)
            elif c.rarity == Rarity.RARE:
                rarity_order.append(1)
            elif c.rarity == Rarity.UNCOMMON:
                rarity_order.append(2)
            elif c.rarity == Rarity.COMMON:
                rarity_order.append(3)

        assert rarity_order == sorted(rarity_order), "Pack not sorted by rarity"

    def test_no_commons_raises(self):
        cards = [
            _make_card("Unc 1", Rarity.UNCOMMON, "U-01"),
            _make_card("Unc 2", Rarity.UNCOMMON, "U-02"),
            _make_card("Unc 3", Rarity.UNCOMMON, "U-03"),
            _make_card("Rare 1", Rarity.RARE, "R-01"),
        ]
        with pytest.raises(ValueError, match="no common cards"):
            generate_booster_pack(cards, seed=1)

    def test_no_uncommons_raises(self):
        cards = [_make_card(f"Com {i}", Rarity.COMMON, f"C-{i:02d}") for i in range(15)]
        with pytest.raises(ValueError, match="no uncommon cards"):
            generate_booster_pack(cards, seed=1)

    def test_no_rares_or_mythics_graceful(self):
        """If no rares/mythics exist, pack still works — just 14 non-land + 1 land."""
        cards = [_make_card(f"Com {i}", Rarity.COMMON, f"C-{i:02d}") for i in range(15)]
        cards.extend([_make_card(f"Unc {i}", Rarity.UNCOMMON, f"U-{i:02d}") for i in range(5)])
        cards.append(_make_card("Plains", Rarity.COMMON, "L-01", type_line="Basic Land — Plains"))

        pack = generate_booster_pack(cards, seed=42)
        # 10 commons + 3 uncommons + 0 rare + 1 land = 14
        assert len(pack) == 14
        rares = [c for c in pack if c.rarity in (Rarity.RARE, Rarity.MYTHIC)]
        assert len(rares) == 0

    def test_no_basic_lands_returns_14(self):
        """If no basic lands in pool, pack has 14 cards."""
        cards = [_make_card(f"Com {i}", Rarity.COMMON, f"C-{i:02d}") for i in range(15)]
        cards.extend([_make_card(f"Unc {i}", Rarity.UNCOMMON, f"U-{i:02d}") for i in range(5)])
        cards.append(_make_card("Big Rare", Rarity.RARE, "R-01"))

        pack = generate_booster_pack(cards, seed=42)
        assert len(pack) == 14

    def test_small_pool_graceful_degradation(self):
        """With very few cards, fill what we can without crashing."""
        cards = [
            _make_card("Com 1", Rarity.COMMON, "C-01"),
            _make_card("Com 2", Rarity.COMMON, "C-02"),
            _make_card("Unc 1", Rarity.UNCOMMON, "U-01"),
            _make_card("Rare 1", Rarity.RARE, "R-01"),
        ]
        pack = generate_booster_pack(cards, seed=42)
        # 2 commons (only 2 available) + 1 uncommon + 1 rare + 0 land = 4
        assert len(pack) == 4
        assert any(c.rarity == Rarity.RARE for c in pack)
        assert any(c.rarity == Rarity.UNCOMMON for c in pack)

    def test_no_rares_falls_back_to_mythic(self):
        """If no rares but mythics exist, the rare slot uses a mythic."""
        cards = [_make_card(f"Com {i}", Rarity.COMMON, f"C-{i:02d}") for i in range(12)]
        cards.extend([_make_card(f"Unc {i}", Rarity.UNCOMMON, f"U-{i:02d}") for i in range(5)])
        cards.append(_make_card("Mythic Beast", Rarity.MYTHIC, "M-01"))

        pack = generate_booster_pack(cards, seed=99)
        mythics = [c for c in pack if c.rarity == Rarity.MYTHIC and "Basic Land" not in c.type_line]
        assert len(mythics) == 1

    def test_nonbasic_lands_are_not_in_land_slot(self):
        """Non-basic lands should be treated by their rarity, not as basic lands."""
        cards = [_make_card(f"Com {i}", Rarity.COMMON, f"C-{i:02d}") for i in range(12)]
        cards.extend([_make_card(f"Unc {i}", Rarity.UNCOMMON, f"U-{i:02d}") for i in range(5)])
        cards.append(_make_card("Rare 1", Rarity.RARE, "R-01"))
        # This is a non-basic land — should NOT fill the basic land slot
        cards.append(
            _make_card(
                "Mystic Gate",
                Rarity.RARE,
                "R-02",
                type_line="Land",
            )
        )

        pack = generate_booster_pack(cards, seed=42)
        basics = [c for c in pack if "Basic Land" in c.type_line]
        assert len(basics) == 0
        # Pack should be 14 (no basic land slot filled)
        assert len(pack) == 14


class TestGenerateSealedPool:
    """Tests for generate_sealed_pool()."""

    def test_sealed_pool_card_count(self):
        pool = _make_full_pool()
        sealed = generate_sealed_pool(pool, num_packs=6, seed=42)
        # 6 packs * 15 cards = 90
        assert len(sealed) == 90

    def test_sealed_pool_reproducible(self):
        pool = _make_full_pool()
        sealed_a = generate_sealed_pool(pool, seed=7)
        sealed_b = generate_sealed_pool(pool, seed=7)
        assert [c.name for c in sealed_a] == [c.name for c in sealed_b]

    def test_sealed_pool_sorted_by_rarity(self):
        pool = _make_full_pool()
        sealed = generate_sealed_pool(pool, seed=42)

        rarity_order = []
        for c in sealed:
            if "Basic Land" in c.type_line:
                rarity_order.append(4)
            elif c.rarity == Rarity.MYTHIC:
                rarity_order.append(0)
            elif c.rarity == Rarity.RARE:
                rarity_order.append(1)
            elif c.rarity == Rarity.UNCOMMON:
                rarity_order.append(2)
            elif c.rarity == Rarity.COMMON:
                rarity_order.append(3)

        assert rarity_order == sorted(rarity_order)

    def test_sealed_pool_custom_pack_count(self):
        pool = _make_full_pool()
        sealed = generate_sealed_pool(pool, num_packs=3, seed=42)
        # 3 packs * 15 cards = 45
        assert len(sealed) == 45

    def test_sealed_pool_can_have_duplicate_cards(self):
        """Cards can appear in multiple packs within a sealed pool (drawn from same set)."""
        pool = _make_full_pool()
        sealed = generate_sealed_pool(pool, num_packs=6, seed=42)
        names = [c.name for c in sealed]
        # With 6 packs from a 43-card pool, duplicates are guaranteed
        assert len(names) > len(set(names))
