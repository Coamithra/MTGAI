"""Tests for the heuristic design-judgment checks.

These were previously stamped on each card's ``generation_attempts[].validation_errors``
at gen time and read back by the council reviewer. They've moved out of the
gen-time validation path and into :mod:`mtgai.analysis.heuristic_checks` so they
get computed fresh against whatever card the council is about to review.
"""

from __future__ import annotations

from mtgai.analysis.heuristic_checks import (
    check_card_heuristics,
    format_findings_for_prompt,
)
from mtgai.models.card import Card
from mtgai.models.enums import Color, Rarity
from mtgai.validation import ValidationError, ValidationSeverity


def _make_card(**overrides) -> Card:
    defaults = {
        "name": "Test Creature",
        "mana_cost": "{2}{G}",
        "cmc": 3.0,
        "type_line": "Creature — Beast",
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


class TestCheckCardHeuristics:
    def test_clean_card_no_findings(self):
        card = _make_card(oracle_text="", rarity=Rarity.UNCOMMON)
        assert check_card_heuristics(card) == []

    def test_overstatted_common_surfaces_power_level(self):
        card = _make_card(
            mana_cost="{1}{G}",
            cmc=2.0,
            power="4",
            toughness="4",
            rarity=Rarity.COMMON,
            oracle_text="Trample",
        )
        findings = check_card_heuristics(card)
        assert any(f.validator == "power_level" for f in findings)

    def test_off_color_ability_surfaces_color_pie(self):
        card = _make_card(
            card_types=["Instant"],
            type_line="Instant",
            subtypes=[],
            colors=[Color.RED],
            color_identity=[Color.RED],
            mana_cost="{R}{R}",
            cmc=2.0,
            oracle_text="Counter target spell.",
            power=None,
            toughness=None,
        )
        findings = check_card_heuristics(card)
        assert any(f.validator == "color_pie" for f in findings)

    def test_findings_are_all_manual(self):
        """Heuristic checks never produce AUTO findings — they're advisory."""
        card = _make_card(
            mana_cost="{1}{G}",
            cmc=2.0,
            power="5",
            toughness="5",
            rarity=Rarity.COMMON,
            oracle_text="Trample",
        )
        findings = check_card_heuristics(card)
        assert findings  # something was flagged
        assert all(f.severity == ValidationSeverity.MANUAL for f in findings)

    def test_mechanical_similarity_requires_existing_cards(self):
        """Without ``existing_cards`` the similarity check is skipped."""
        card = _make_card(name="Bolt", oracle_text="~ deals 3 damage to any target.")
        twin = _make_card(
            name="Spark",
            collector_number="002",
            oracle_text="~ deals 3 damage to any target.",
        )

        # Without context: no similarity finding.
        no_context = check_card_heuristics(card)
        assert not any(f.error_code == "uniqueness.mechanical_similarity" for f in no_context)

        # With context: similarity surfaces.
        with_context = check_card_heuristics(card, existing_cards=[twin])
        assert any(f.error_code == "uniqueness.mechanical_similarity" for f in with_context)


class TestFormatFindingsForPrompt:
    def test_empty_findings_returns_empty_string(self):
        assert format_findings_for_prompt([]) == ""

    def test_findings_rendered_as_bullets(self):
        findings = [
            ValidationError(
                validator="power_level",
                severity=ValidationSeverity.MANUAL,
                field="power/toughness",
                message="Way too big for the mana cost",
            ),
            ValidationError(
                validator="color_pie",
                severity=ValidationSeverity.MANUAL,
                field="oracle_text",
                message="Counterspell in red is off-pie",
            ),
        ]
        rendered = format_findings_for_prompt(findings)
        assert "Validation Warnings" in rendered
        assert "Way too big for the mana cost" in rendered
        assert "Counterspell in red is off-pie" in rendered

    def test_duplicate_messages_deduped(self):
        msg = "Same problem twice"
        findings = [
            ValidationError(
                validator="power_level",
                severity=ValidationSeverity.MANUAL,
                field="x",
                message=msg,
            ),
            ValidationError(
                validator="color_pie",
                severity=ValidationSeverity.MANUAL,
                field="x",
                message=msg,
            ),
        ]
        rendered = format_findings_for_prompt(findings)
        assert rendered.count(msg) == 1
