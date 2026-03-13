"""Tests for set-wide coverage analysis."""

from __future__ import annotations

from mtgai.analysis.coverage import (
    analyze_color_balance,
    analyze_color_coverage,
    analyze_mana_fixing,
    analyze_mechanic_distribution,
)
from mtgai.models.card import Card
from mtgai.models.enums import Color, Rarity


def _make_card(**overrides) -> Card:
    defaults = {
        "name": "Test Creature",
        "mana_cost": "{2}{G}",
        "cmc": 3.0,
        "type_line": "Creature -- Beast",
        "oracle_text": "Trample",
        "power": "3",
        "toughness": "3",
        "rarity": Rarity.COMMON,
        "colors": [Color.GREEN],
        "color_identity": [Color.GREEN],
        "collector_number": "001",
        "set_code": "TST",
        "card_types": ["Creature"],
        "subtypes": ["Beast"],
    }
    defaults.update(overrides)
    return Card(**defaults)


# ---------------------------------------------------------------------------
# Color coverage
# ---------------------------------------------------------------------------


class TestColorCoverage:
    def test_creature_cmc_curve(self):
        """Cards at CMC 1, 3, 5 should show a gap at 2, 4, 6."""
        cards = [
            _make_card(cmc=1.0, power="1", toughness="1"),
            _make_card(name="C2", cmc=3.0),
            _make_card(name="C3", cmc=5.0, power="4", toughness="4"),
        ]
        results, _issues = analyze_color_coverage(cards, set(), {})
        green = next(r for r in results if r.color == "G")
        assert 1 in green.creature_cmc_buckets
        assert 3 in green.creature_cmc_buckets
        assert 5 in green.creature_cmc_buckets
        # Gaps at CMC 2, 4, 6
        assert 2 in green.creature_cmc_gaps
        assert 4 in green.creature_cmc_gaps

    def test_removal_detected(self):
        cards = [
            _make_card(
                name="Murder",
                oracle_text="Destroy target creature.",
                type_line="Instant",
                card_types=["Instant"],
                power=None,
                toughness=None,
                colors=[Color.BLACK],
                color_identity=[Color.BLACK],
            ),
        ]
        results, _ = analyze_color_coverage(cards, set(), {})
        black = next(r for r in results if r.color == "B")
        assert black.removal_count == 1
        assert "Murder" in black.removal_cards

    def test_ca_via_mechanic_tag(self):
        """A card using Salvage should count as card advantage via functional tags."""
        cards = [
            _make_card(
                name="Salvager",
                oracle_text="When ~ enters, salvage 3.",
            ),
        ]
        tags = {"Salvage": ["card_advantage"]}
        results, _ = analyze_color_coverage(cards, {"Salvage"}, tags)
        green = next(r for r in results if r.color == "G")
        assert green.card_advantage_count >= 1
        assert "Salvager" in green.card_advantage_cards

    def test_no_removal_at_cu_warns(self):
        """A color with no removal at common/uncommon should produce a WARN."""
        cards = [
            _make_card(rarity=Rarity.COMMON, oracle_text="Trample"),
            _make_card(name="C2", rarity=Rarity.UNCOMMON, oracle_text="Flying"),
        ]
        _, issues = analyze_color_coverage(cards, set(), {})
        removal_issues = [i for i in issues if i.check == "coverage.removal_density"]
        assert any("G" in i.message for i in removal_issues)

    def test_creature_size_distribution(self):
        cards = [
            _make_card(name="Small", power="1", toughness="1", cmc=1.0),
            _make_card(name="Big", power="5", toughness="5", cmc=6.0),
        ]
        results, _ = analyze_color_coverage(cards, set(), {})
        green = next(r for r in results if r.color == "G")
        size_map = {e.weight_class: e.count for e in green.creature_sizes}
        assert size_map.get("small", 0) == 1
        assert size_map.get("huge", 0) == 1


# ---------------------------------------------------------------------------
# Mechanic distribution
# ---------------------------------------------------------------------------


class TestMechanicDistribution:
    def test_exact_match(self):
        mechanics = [
            {"name": "Salvage", "distribution": {"common": 2, "uncommon": 1}},
        ]
        cards = [
            _make_card(name="S1", oracle_text="Salvage 2.", rarity=Rarity.COMMON),
            _make_card(name="S2", oracle_text="Salvage 3.", rarity=Rarity.COMMON),
            _make_card(name="S3", oracle_text="Salvage 4.", rarity=Rarity.UNCOMMON),
        ]
        results, issues = analyze_mechanic_distribution(cards, mechanics)
        assert results[0].total_planned == 3
        assert results[0].total_actual == 3
        assert len(issues) == 0

    def test_over_represented(self):
        mechanics = [
            {"name": "Salvage", "distribution": {"common": 2}},
        ]
        cards = [
            _make_card(name=f"S{i}", oracle_text="Salvage 2.", rarity=Rarity.COMMON)
            for i in range(6)
        ]
        results, issues = analyze_mechanic_distribution(cards, mechanics)
        assert results[0].total_actual == 6
        assert any(i.check == "coverage.mechanic_over" for i in issues)

    def test_missing_mechanic(self):
        mechanics = [
            {"name": "Malfunction", "distribution": {"common": 2}},
        ]
        cards = [_make_card(oracle_text="Trample")]
        results, issues = analyze_mechanic_distribution(cards, mechanics)
        assert results[0].total_actual == 0
        assert any(i.check == "coverage.mechanic_missing" for i in issues)


# ---------------------------------------------------------------------------
# Mana fixing
# ---------------------------------------------------------------------------


class TestManaFixing:
    def test_treasure_maker(self):
        cards = [
            _make_card(
                name="Treasure Maker",
                oracle_text="Create a Treasure token.",
                type_line="Sorcery",
                card_types=["Sorcery"],
                power=None,
                toughness=None,
            ),
        ]
        assert "Treasure Maker" in analyze_mana_fixing(cards)

    def test_creature_not_fixing(self):
        cards = [_make_card(oracle_text="Trample")]
        assert len(analyze_mana_fixing(cards)) == 0


# ---------------------------------------------------------------------------
# Color balance
# ---------------------------------------------------------------------------


class TestColorBalance:
    def test_balanced(self):
        cards = [
            _make_card(name=f"{c}-1", colors=[c])
            for c in [Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN]
        ]
        counts, issues = analyze_color_balance(cards)
        assert all(v == 1 for v in counts.values())
        assert len(issues) == 0

    def test_imbalanced(self):
        cards = [_make_card(name=f"W-{i}", colors=[Color.WHITE]) for i in range(6)] + [
            _make_card(name="U-1", colors=[Color.BLUE]),
        ]
        _, issues = analyze_color_balance(cards)
        assert len(issues) > 0
        assert any("W" in i.message for i in issues)

    def test_multicolor_excluded(self):
        """Multicolor cards should not affect mono-color balance."""
        cards = [
            _make_card(name="WU-1", colors=[Color.WHITE, Color.BLUE]),
        ]
        counts, _ = analyze_color_balance(cards)
        # All 5 colors present but all zero (multicolor not counted)
        assert all(v == 0 for v in counts.values())
