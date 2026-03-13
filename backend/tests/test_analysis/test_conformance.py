"""Tests for skeleton conformance analysis."""

from __future__ import annotations

from mtgai.analysis.conformance import analyze_conformance, check_slot_conformance
from mtgai.analysis.models import AnalysisSeverity
from mtgai.models.card import Card
from mtgai.models.enums import Color, Rarity
from mtgai.skeleton.generator import SkeletonSlot


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
        "collector_number": "G-C-01",
        "set_code": "TST",
        "card_types": ["Creature"],
        "subtypes": ["Beast"],
        "slot_id": "G-C-01",
    }
    defaults.update(overrides)
    return Card(**defaults)


def _make_slot(**overrides) -> SkeletonSlot:
    defaults = {
        "slot_id": "G-C-01",
        "color": "G",
        "rarity": "common",
        "card_type": "creature",
        "cmc_target": 3,
        "mechanic_tag": "french_vanilla",
    }
    defaults.update(overrides)
    return SkeletonSlot(**defaults)


class TestCheckSlotConformance:
    def test_perfect_match(self):
        card = _make_card()
        slot = _make_slot()
        result = check_slot_conformance(card, slot)
        assert result.matched
        assert len(result.issues) == 0

    def test_color_mismatch(self):
        card = _make_card(colors=[Color.RED])
        slot = _make_slot(color="G")
        result = check_slot_conformance(card, slot)
        assert not result.matched
        checks = [i.check for i in result.issues]
        assert "conformance.color" in checks

    def test_rarity_mismatch(self):
        card = _make_card(rarity=Rarity.RARE)
        slot = _make_slot(rarity="common")
        result = check_slot_conformance(card, slot)
        checks = [i.check for i in result.issues]
        assert "conformance.rarity" in checks

    def test_card_type_mismatch(self):
        card = _make_card(
            card_types=["Instant"],
            type_line="Instant",
            power=None,
            toughness=None,
        )
        slot = _make_slot(card_type="creature")
        result = check_slot_conformance(card, slot)
        checks = [i.check for i in result.issues]
        assert "conformance.card_type" in checks

    def test_cmc_exact_match(self):
        card = _make_card(cmc=3.0)
        slot = _make_slot(cmc_target=3)
        result = check_slot_conformance(card, slot)
        cmc_issues = [i for i in result.issues if i.check == "conformance.cmc"]
        assert len(cmc_issues) == 0

    def test_cmc_off_by_one_warns(self):
        card = _make_card(cmc=4.0)
        slot = _make_slot(cmc_target=3)
        result = check_slot_conformance(card, slot)
        cmc_issues = [i for i in result.issues if i.check == "conformance.cmc"]
        assert len(cmc_issues) == 1
        assert cmc_issues[0].severity == AnalysisSeverity.WARN

    def test_cmc_off_by_two_fails(self):
        card = _make_card(cmc=5.0)
        slot = _make_slot(cmc_target=3)
        result = check_slot_conformance(card, slot)
        cmc_issues = [i for i in result.issues if i.check == "conformance.cmc"]
        assert len(cmc_issues) == 1
        assert cmc_issues[0].severity == AnalysisSeverity.FAIL

    def test_mechanic_tier_mismatch_warns(self):
        card = _make_card(oracle_text="When ~ enters, salvage 3.")
        slot = _make_slot(mechanic_tag="vanilla")
        result = check_slot_conformance(card, slot)
        tier_issues = [i for i in result.issues if i.check == "conformance.mechanic_tier"]
        assert len(tier_issues) == 1
        assert tier_issues[0].severity == AnalysisSeverity.WARN

    def test_multicolor_conformance(self):
        card = _make_card(
            colors=[Color.WHITE, Color.BLUE],
            slot_id="WU-U-01",
            collector_number="WU-U-01",
            rarity=Rarity.UNCOMMON,
        )
        slot = _make_slot(
            slot_id="WU-U-01",
            color="multicolor",
            color_pair="WU",
            rarity="uncommon",
        )
        result = check_slot_conformance(card, slot)
        color_issues = [
            i for i in result.issues if i.check in ("conformance.color", "conformance.color_pair")
        ]
        assert len(color_issues) == 0


class TestAnalyzeConformance:
    def test_unmatched_slot_reported(self):
        slots = [_make_slot(slot_id="G-C-01")]
        cards: list[Card] = []
        results, issues = analyze_conformance(cards, slots)
        assert len(results) == 1
        assert not results[0].matched
        assert any(i.check == "conformance.missing_card" for i in issues)

    def test_matched_slot(self):
        slot = _make_slot(slot_id="G-C-01")
        card = _make_card(slot_id="G-C-01")
        results, _issues = analyze_conformance([card], [slot])
        assert results[0].matched

    def test_cards_without_slot_id_skipped(self):
        slot = _make_slot(slot_id="G-C-01")
        card = _make_card(slot_id="G-C-01")
        land = _make_card(slot_id=None, name="Forest")
        results, _ = analyze_conformance([card, land], [slot])
        assert len(results) == 1
