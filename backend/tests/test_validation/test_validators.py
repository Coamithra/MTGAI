"""Comprehensive tests for the validation library.

Tests cover all 9 validators across happy paths and common LLM failure modes,
plus the auto-fix system that deterministically corrects AUTO errors.
"""

from __future__ import annotations

from mtgai.models.card import Card, ManaCost
from mtgai.models.enums import Color, Rarity
from mtgai.validation import (
    ValidationError,
    ValidationSeverity,
    auto_fix_card,
    format_validation_feedback,
    has_manual_errors,
    validate_card,
    validate_card_from_raw,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_card(**overrides) -> Card:
    """Create a minimal valid Card with sane defaults, overrideable for each test."""
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


def _errors_by_validator(errors: list[ValidationError], validator: str):
    return [e for e in errors if e.validator == validator]


def _has_error(errors: list[ValidationError], *, validator: str, severity: str | None = None):
    for e in errors:
        if e.validator == validator and (severity is None or e.severity == severity):
            return True
    return False


# ===========================================================================
# Schema validation (validate_card_from_raw)
# ===========================================================================


class TestSchemaValidation:
    def test_valid_card_parses(self):
        raw = {
            "name": "Grizzly Bears",
            "type_line": "Creature — Bear",
            "mana_cost": "{1}{G}",
            "cmc": 2.0,
            "oracle_text": "",
            "power": "2",
            "toughness": "2",
            "colors": ["G"],
            "color_identity": ["G"],
            "card_types": ["Creature"],
            "subtypes": ["Bear"],
        }
        card, errors, _fixes = validate_card_from_raw(raw)
        assert card is not None
        schema_errors = _errors_by_validator(errors, "schema")
        assert len(schema_errors) == 0

    def test_missing_name_is_manual(self):
        raw = {"type_line": "Creature — Bear"}
        card, errors, _fixes = validate_card_from_raw(raw)
        assert card is None
        assert len(errors) > 0
        assert all(e.severity == ValidationSeverity.MANUAL for e in errors)

    def test_wrong_type_is_manual(self):
        raw = {
            "name": "Bad Card",
            "type_line": "Creature",
            "cmc": "not a number",  # should be float
        }
        card, errors, _fixes = validate_card_from_raw(raw)
        # Should get at least one error about the float type
        assert card is None or any("cmc" in e.field for e in errors)


# ===========================================================================
# Mana consistency
# ===========================================================================


class TestManaConsistency:
    def test_valid_mana_cost(self):
        card = _make_card(mana_cost="{2}{G}", cmc=3.0, colors=[Color.GREEN])
        errors = _errors_by_validator(validate_card(card), "mana")
        assert len(errors) == 0

    def test_cmc_mismatch(self):
        card = _make_card(mana_cost="{2}{W}{W}", cmc=3.0)  # should be 4.0
        errors = _errors_by_validator(validate_card(card), "mana")
        assert _has_error(errors, validator="mana", severity="AUTO")
        assert any("cmc" in e.message.lower() for e in errors)

    def test_color_mismatch(self):
        card = _make_card(
            mana_cost="{1}{R}{G}",
            cmc=3.0,
            colors=[Color.RED],  # missing Green
        )
        errors = _errors_by_validator(validate_card(card), "mana")
        assert _has_error(errors, validator="mana", severity="AUTO")

    def test_color_identity_missing_oracle_colors(self):
        card = _make_card(
            oracle_text="{B}: ~ gains deathtouch until end of turn.",
            color_identity=[Color.GREEN],  # missing Black
        )
        errors = _errors_by_validator(validate_card(card), "mana")
        assert _has_error(errors, validator="mana", severity="AUTO")
        assert any("B" in e.message for e in errors)

    def test_wubrg_ordering_auto(self):
        card = _make_card(
            mana_cost="{R}{W}",
            cmc=2.0,
            colors=[Color.WHITE, Color.RED],
            color_identity=[Color.WHITE, Color.RED],
        )
        errors = _errors_by_validator(validate_card(card), "mana")
        auto = [e for e in errors if e.severity == ValidationSeverity.AUTO]
        assert any("WUBRG" in e.message for e in auto)

    def test_land_with_mana_cost_manual(self):
        card = _make_card(
            mana_cost="{2}",
            cmc=2.0,
            colors=[],
            color_identity=[],
            card_types=["Land"],
            type_line="Land",
            power=None,
            toughness=None,
        )
        errors = _errors_by_validator(validate_card(card), "mana")
        assert any("Land" in e.message for e in errors)
        assert any(e.severity == ValidationSeverity.MANUAL for e in errors)

    def test_invalid_mana_symbol(self):
        card = _make_card(mana_cost="{2W}", cmc=3.0)
        errors = _errors_by_validator(validate_card(card), "mana")
        assert _has_error(errors, validator="mana", severity="AUTO")

    def test_mana_cost_parsed_mismatch(self):
        card = _make_card(
            mana_cost="{2}{G}",
            cmc=3.0,
            mana_cost_parsed=ManaCost(raw="{1}{G}", cmc=2.0, colors=[Color.GREEN]),
        )
        errors = _errors_by_validator(validate_card(card), "mana")
        assert _has_error(errors, validator="mana", severity="AUTO")


# ===========================================================================
# Type consistency
# ===========================================================================


class TestTypeConsistency:
    def test_creature_without_pt_is_manual(self):
        card = _make_card(power=None, toughness=None)
        errors = _errors_by_validator(validate_card(card), "type_check")
        assert _has_error(errors, validator="type_check", severity="MANUAL")

    def test_noncreature_with_pt_is_manual(self):
        card = _make_card(
            card_types=["Instant"],
            type_line="Instant",
            subtypes=[],
            power="3",
            toughness="3",
        )
        errors = _errors_by_validator(validate_card(card), "type_check")
        assert _has_error(errors, validator="type_check", severity="MANUAL")

    def test_planeswalker_without_loyalty_is_manual(self):
        card = _make_card(
            card_types=["Planeswalker"],
            type_line="Planeswalker — Test",
            subtypes=["Test"],
            power=None,
            toughness=None,
            loyalty=None,
            oracle_text="+1: Draw a card.\n-3: Target player loses 3 life.",
        )
        errors = _errors_by_validator(validate_card(card), "type_check")
        assert _has_error(errors, validator="type_check", severity="MANUAL")
        assert any("loyalty" in e.message.lower() for e in errors)

    def test_aura_without_enchant_is_manual(self):
        card = _make_card(
            card_types=["Enchantment"],
            subtypes=["Aura"],
            type_line="Enchantment — Aura",
            oracle_text="Enchanted creature gets +2/+2.",
            power=None,
            toughness=None,
        )
        errors = _errors_by_validator(validate_card(card), "type_check")
        assert _has_error(errors, validator="type_check", severity="MANUAL")
        assert any("Enchant" in e.message for e in errors)

    def test_aura_with_enchant_is_ok(self):
        card = _make_card(
            card_types=["Enchantment"],
            subtypes=["Aura"],
            type_line="Enchantment — Aura",
            oracle_text="Enchant creature\nEnchanted creature gets +2/+2.",
            power=None,
            toughness=None,
        )
        errors = _errors_by_validator(validate_card(card), "type_check")
        assert not any("Enchant" in e.message and e.severity == "MANUAL" for e in errors)

    def test_equipment_without_equip_is_manual(self):
        card = _make_card(
            card_types=["Artifact"],
            subtypes=["Equipment"],
            type_line="Artifact — Equipment",
            oracle_text="Equipped creature gets +1/+1.",
            power=None,
            toughness=None,
        )
        errors = _errors_by_validator(validate_card(card), "type_check")
        assert _has_error(errors, validator="type_check", severity="MANUAL")
        assert any("Equip" in e.message for e in errors)


# ===========================================================================
# Rules text grammar
# ===========================================================================


class TestRulesText:
    def test_card_name_in_oracle(self):
        card = _make_card(
            name="Flame Serpent",
            oracle_text="When Flame Serpent enters, it deals 2 damage to each opponent.",
        )
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert _has_error(errors, validator="rules_text", severity="AUTO")
        assert any("card name" in e.message.lower() for e in errors)

    def test_tilde_self_ref_is_ok(self):
        card = _make_card(oracle_text="When ~ enters, it deals 2 damage to each opponent.")
        errors = _errors_by_validator(validate_card(card), "rules_text")
        # Should NOT flag self-reference
        assert not any("card name" in e.message.lower() for e in errors)

    def test_this_creature_is_manual(self):
        card = _make_card(oracle_text="When this creature enters, draw a card.")
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert _has_error(errors, validator="rules_text", severity="MANUAL")
        assert any("this creature" in e.message.lower() for e in errors)

    def test_enters_the_battlefield_outdated(self):
        card = _make_card(
            oracle_text="When ~ enters the battlefield, draw a card.",
        )
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert _has_error(errors, validator="rules_text", severity="AUTO")
        assert any("enters the battlefield" in e.message.lower() for e in errors)

    def test_enters_is_ok(self):
        card = _make_card(oracle_text="When ~ enters, draw a card.")
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert not any("enters the battlefield" in e.message.lower() for e in errors)

    def test_tap_colon_instead_of_symbol(self):
        card = _make_card(oracle_text="Tap: Add {G}.")
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert _has_error(errors, validator="rules_text", severity="AUTO")
        assert any("{T}" in (e.suggestion or "") for e in errors)

    def test_tap_symbol_is_ok(self):
        card = _make_card(oracle_text="{T}: Add {G}.")
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert not any("{T}" in (e.suggestion or "") for e in errors)

    def test_invalid_mana_symbol_in_text(self):
        card = _make_card(oracle_text="{2W}: ~ gets +1/+1 until end of turn.")
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert _has_error(errors, validator="rules_text", severity="MANUAL")
        assert any("mana symbol" in e.message.lower() for e in errors)

    def test_pay_n_informal_cost(self):
        card = _make_card(oracle_text="Pay 2: Draw a card.")
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert _has_error(errors, validator="rules_text", severity="MANUAL")

    def test_haste_malfunction_nonbo(self):
        card = _make_card(
            oracle_text="Haste\nMalfunction 2",
            mechanic_tags=["malfunction"],
        )
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert _has_error(errors, validator="rules_text", severity="MANUAL")
        assert any("nonbo" in e.message.lower() for e in errors)

    def test_malfunction_without_haste_is_ok(self):
        card = _make_card(
            oracle_text="Malfunction 2",
            mechanic_tags=["malfunction"],
            reminder_text="(This permanent enters tapped with 2 malfunction counters.)",
        )
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert not any("nonbo" in e.message.lower() for e in errors)

    def test_custom_mechanic_missing_reminder(self):
        card = _make_card(
            oracle_text="Salvage 3",
            mechanic_tags=["salvage"],
            reminder_text=None,
        )
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert any("reminder text" in e.message.lower() for e in errors)

    def test_custom_mechanic_with_reminder_ok(self):
        card = _make_card(
            oracle_text="Salvage 3",
            mechanic_tags=["salvage"],
            reminder_text="(Look at the top 3 cards of your library...)",
        )
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert not any(
            "reminder text" in e.message.lower() for e in errors if e.validator == "rules_text"
        )

    def test_reminder_text_in_oracle(self):
        card = _make_card(
            oracle_text="Flying (This creature can't be blocked except by creatures with flying.)",
        )
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert any("reminder text" in e.message.lower() for e in errors)

    def test_vanilla_creature_no_errors(self):
        card = _make_card(oracle_text="")
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert len(errors) == 0

    def test_cannot_instead_of_cant(self):
        card = _make_card(oracle_text="~ cannot be blocked.")
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert _has_error(errors, validator="rules_text", severity="AUTO")
        assert any("can't" in e.message for e in errors)

    def test_keyword_capitalization(self):
        card = _make_card(oracle_text="Flying, Trample")
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert _has_error(errors, validator="rules_text", severity="AUTO")
        assert any("lowercase" in e.message.lower() for e in errors)


# ===========================================================================
# Power level
# ===========================================================================


class TestPowerLevel:
    def test_common_overstatted(self):
        # 4/4 for 2 mana common with abilities -> P+T=8, CMC+2=4, way over
        card = _make_card(
            mana_cost="{1}{G}",
            cmc=2.0,
            power="4",
            toughness="4",
            rarity=Rarity.COMMON,
            oracle_text="Trample",
        )
        errors = _errors_by_validator(validate_card(card), "power_level")
        assert _has_error(errors, validator="power_level", severity="MANUAL")

    def test_common_vanilla_fine(self):
        # 3/3 for 3 mana vanilla common -> P+T=6, CMC+3=6, exactly at limit
        card = _make_card(
            oracle_text="",
            power="3",
            toughness="3",
        )
        errors = _errors_by_validator(validate_card(card), "power_level")
        assert not any("P+T" in e.message or "Power" in e.message for e in errors)

    def test_nwo_modal_at_common(self):
        card = _make_card(oracle_text="Choose one —\n• Draw a card.\n• ~ deals 2 damage.")
        errors = _errors_by_validator(validate_card(card), "power_level")
        assert any("Modal" in e.message for e in errors)

    def test_nwo_ok_at_uncommon(self):
        card = _make_card(
            rarity=Rarity.UNCOMMON,
            oracle_text="Choose one —\n• Draw a card.\n• ~ deals 2 damage.",
        )
        errors = _errors_by_validator(validate_card(card), "power_level")
        assert not any("Modal" in e.message for e in errors)

    def test_zero_cmc_nonland_flagged(self):
        card = _make_card(
            mana_cost="{0}",
            cmc=0.0,
            colors=[],
            color_identity=[],
            card_types=["Artifact"],
            type_line="Artifact",
            power=None,
            toughness=None,
            subtypes=[],
        )
        errors = _errors_by_validator(validate_card(card), "power_level")
        assert any("Zero" in e.message or "zero" in e.message.lower() for e in errors)


# ===========================================================================
# Color pie
# ===========================================================================


class TestColorPie:
    def test_counterspell_in_blue_ok(self):
        card = _make_card(
            card_types=["Instant"],
            type_line="Instant",
            subtypes=[],
            colors=[Color.BLUE],
            color_identity=[Color.BLUE],
            mana_cost="{U}{U}",
            cmc=2.0,
            oracle_text="Counter target spell.",
            power=None,
            toughness=None,
        )
        errors = _errors_by_validator(validate_card(card), "color_pie")
        assert len(errors) == 0

    def test_counterspell_in_red_flagged(self):
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
        errors = _errors_by_validator(validate_card(card), "color_pie")
        assert _has_error(errors, validator="color_pie", severity="MANUAL")

    def test_colorless_artifact_gets_pass(self):
        card = _make_card(
            card_types=["Artifact"],
            type_line="Artifact",
            subtypes=[],
            colors=[],
            color_identity=[],
            mana_cost="{3}",
            cmc=3.0,
            oracle_text="Draw a card.",
            power=None,
            toughness=None,
        )
        errors = _errors_by_validator(validate_card(card), "color_pie")
        assert len(errors) == 0

    def test_trample_in_green_ok(self):
        card = _make_card(oracle_text="Trample")
        errors = _errors_by_validator(validate_card(card), "color_pie")
        assert not any("trample" in e.message.lower() for e in errors)

    def test_trample_in_blue_flagged(self):
        card = _make_card(
            colors=[Color.BLUE],
            color_identity=[Color.BLUE],
            mana_cost="{2}{U}",
            oracle_text="Trample",
        )
        errors = _errors_by_validator(validate_card(card), "color_pie")
        assert _has_error(errors, validator="color_pie", severity="MANUAL")


# ===========================================================================
# Text overflow
# ===========================================================================


class TestTextOverflow:
    def test_short_card_no_overflow(self):
        card = _make_card()
        errors = _errors_by_validator(validate_card(card), "text_overflow")
        assert len(errors) == 0

    def test_long_name_flagged(self):
        card = _make_card(name="The Incredibly Long and Verbose Card Name That Exceeds Limits")
        errors = _errors_by_validator(validate_card(card), "text_overflow")
        assert any("name" in e.field for e in errors)

    def test_long_oracle_creature_flagged(self):
        card = _make_card(oracle_text="x" * 301)
        errors = _errors_by_validator(validate_card(card), "text_overflow")
        assert any("oracle" in e.field for e in errors)

    def test_long_oracle_noncreature_higher_limit(self):
        card = _make_card(
            oracle_text="x" * 350,
            card_types=["Instant"],
            type_line="Instant",
            subtypes=[],
            power=None,
            toughness=None,
        )
        errors = _errors_by_validator(validate_card(card), "text_overflow")
        # 350 < 400 limit for noncreature, so no error
        assert not any("oracle" in e.field for e in errors)


# ===========================================================================
# Uniqueness
# ===========================================================================


class TestUniqueness:
    def test_duplicate_name_manual(self):
        card = _make_card(name="Fire Bolt", collector_number="002")
        existing = [_make_card(name="Fire Bolt", collector_number="001")]
        errors = _errors_by_validator(validate_card(card, existing), "uniqueness")
        assert _has_error(errors, validator="uniqueness", severity="MANUAL")

    def test_near_duplicate_name_manual(self):
        card = _make_card(name="Fire Bolt", collector_number="002")
        existing = [_make_card(name="Fire Blt", collector_number="001")]
        errors = _errors_by_validator(validate_card(card, existing), "uniqueness")
        assert _has_error(errors, validator="uniqueness", severity="MANUAL")

    def test_collector_number_collision_auto(self):
        card = _make_card(name="Card A", collector_number="001")
        existing = [_make_card(name="Card B", collector_number="001")]
        errors = _errors_by_validator(validate_card(card, existing), "uniqueness")
        assert _has_error(errors, validator="uniqueness", severity="AUTO")
        assert any("collector" in e.message.lower() for e in errors)

    def test_mechanical_similarity_manual(self):
        card = _make_card(
            name="Bolt A",
            oracle_text="~ deals 3 damage to any target.",
            collector_number="002",
        )
        existing = [
            _make_card(
                name="Bolt B",
                oracle_text="~ deals 3 damage to any target.",
                collector_number="001",
            )
        ]
        errors = _errors_by_validator(validate_card(card, existing), "uniqueness")
        assert any("similar" in e.message.lower() for e in errors)

    def test_unique_cards_no_errors(self):
        card = _make_card(name="Unique Beast", collector_number="002")
        existing = [
            _make_card(
                name="Different Card",
                collector_number="001",
                mana_cost="{1}{R}",
                cmc=2.0,
                colors=[Color.RED],
                color_identity=[Color.RED],
                oracle_text="Haste",
            )
        ]
        errors = _errors_by_validator(validate_card(card, existing), "uniqueness")
        assert len(errors) == 0


# ===========================================================================
# Runner & feedback formatter
# ===========================================================================


class TestRunner:
    def test_clean_card_no_manual_errors(self):
        card = _make_card(oracle_text="", rarity=Rarity.UNCOMMON)
        errors = validate_card(card)
        assert not has_manual_errors(errors)

    def test_has_manual_errors_flag(self):
        errors = [
            ValidationError(
                validator="test",
                severity=ValidationSeverity.MANUAL,
                field="x",
                message="bad",
            ),
        ]
        assert has_manual_errors(errors)

    def test_format_feedback_includes_errors(self):
        errors = [
            ValidationError(
                validator="test",
                severity=ValidationSeverity.MANUAL,
                field="x",
                message="Thing is wrong",
                suggestion="Fix it",
            ),
        ]
        feedback = format_validation_feedback(
            "Test Card",
            errors,
            slot_color="G",
            slot_rarity="common",
            slot_type="Creature",
        )
        assert "Test Card" in feedback
        assert "Thing is wrong" in feedback
        assert "Fix it" in feedback
        assert "slot" in feedback.lower()


# ===========================================================================
# Auto-fix system
# ===========================================================================


class TestAutoFix:
    def test_auto_fix_cmc(self):
        """Card with wrong CMC gets auto-corrected."""
        card = _make_card(mana_cost="{2}{W}{W}", cmc=3.0)  # should be 4.0
        errors = validate_card(card)
        result = auto_fix_card(card, errors)
        assert result.card.cmc == 4.0
        assert any("cmc_mismatch" in f for f in result.applied_fixes)

    def test_auto_fix_colors(self):
        """Card with wrong colors gets auto-corrected."""
        card = _make_card(
            mana_cost="{1}{R}{G}",
            cmc=3.0,
            colors=[Color.RED],  # missing Green
        )
        errors = validate_card(card)
        result = auto_fix_card(card, errors)
        fixed_colors = {c.value for c in result.card.colors}
        assert fixed_colors == {"R", "G"}

    def test_auto_fix_invalid_format(self):
        """{2W} gets split into {2}{W}."""
        card = _make_card(mana_cost="{2W}", cmc=3.0)
        errors = validate_card(card)
        result = auto_fix_card(card, errors)
        assert result.card.mana_cost == "{2}{W}"
        assert any("invalid_format" in f for f in result.applied_fixes)

    def test_auto_fix_invalid_format_multi(self):
        """{WW} gets split into {W}{W}."""
        card = _make_card(
            mana_cost="{1}{WW}",
            cmc=3.0,
            colors=[Color.WHITE],
            color_identity=[Color.WHITE],
        )
        errors = validate_card(card)
        result = auto_fix_card(card, errors)
        assert result.card.mana_cost == "{1}{W}{W}"

    def test_auto_fix_wubrg_order(self):
        """Mana symbols get reordered to WUBRG."""
        card = _make_card(
            mana_cost="{R}{W}",
            cmc=2.0,
            colors=[Color.WHITE, Color.RED],
            color_identity=[Color.WHITE, Color.RED],
        )
        errors = validate_card(card)
        result = auto_fix_card(card, errors)
        assert result.card.mana_cost == "{W}{R}"

    def test_auto_fix_etb(self):
        """'enters the battlefield' gets replaced with 'enters'."""
        card = _make_card(oracle_text="When ~ enters the battlefield, draw a card.")
        errors = validate_card(card)
        result = auto_fix_card(card, errors)
        assert "enters the battlefield" not in result.card.oracle_text
        assert "enters" in result.card.oracle_text

    def test_auto_fix_card_name(self):
        """Card name in oracle text gets replaced with ~."""
        card = _make_card(
            name="Flame Serpent",
            oracle_text="When Flame Serpent enters, it deals 2 damage.",
        )
        errors = validate_card(card)
        result = auto_fix_card(card, errors)
        assert "Flame Serpent" not in result.card.oracle_text
        assert "~" in result.card.oracle_text

    def test_auto_fix_tap_colon(self):
        """'Tap:' gets replaced with '{T}:'."""
        card = _make_card(oracle_text="Tap: Add {G}.")
        errors = validate_card(card)
        result = auto_fix_card(card, errors)
        assert "{T}:" in result.card.oracle_text
        assert "Tap:" not in result.card.oracle_text

    def test_auto_fix_cannot(self):
        """'cannot' gets replaced with 'can't'."""
        card = _make_card(oracle_text="~ cannot be blocked.")
        errors = validate_card(card)
        result = auto_fix_card(card, errors)
        assert "cannot" not in result.card.oracle_text
        assert "can't" in result.card.oracle_text

    def test_auto_fix_keyword_caps(self):
        """Second keyword in comma list gets lowercased."""
        card = _make_card(oracle_text="Flying, Trample")
        errors = validate_card(card)
        result = auto_fix_card(card, errors)
        assert "trample" in result.card.oracle_text

    def test_auto_fix_collector_number(self):
        """Colliding collector number gets reassigned to next available."""
        card = _make_card(name="Card A", collector_number="001")
        existing = [_make_card(name="Card B", collector_number="001")]
        errors = validate_card(card, existing)
        result = auto_fix_card(card, errors)
        assert result.card.collector_number == "002"
        assert any("collector_number" in f for f in result.applied_fixes)

    def test_auto_fix_preserves_manual(self):
        """MANUAL errors pass through untouched."""
        card = _make_card(power=None, toughness=None)  # creature missing P/T
        errors = validate_card(card)
        result = auto_fix_card(card, errors)
        manual = [e for e in result.remaining_errors if e.severity == ValidationSeverity.MANUAL]
        assert any(e.validator == "type_check" for e in manual)

    def test_auto_fix_chained(self):
        """Multiple AUTO fixes compose correctly on one card."""
        card = _make_card(
            name="Flame Serpent",
            mana_cost="{R}{W}",
            cmc=3.0,  # wrong — should be 2
            colors=[Color.WHITE, Color.RED],
            color_identity=[Color.WHITE, Color.RED],
            oracle_text="When Flame Serpent enters the battlefield, draw a card.",
        )
        errors = validate_card(card)
        result = auto_fix_card(card, errors)
        # CMC fixed
        assert result.card.cmc == 2.0
        # WUBRG fixed
        assert result.card.mana_cost == "{W}{R}"
        # Card name replaced
        assert "Flame Serpent" not in result.card.oracle_text
        assert "~" in result.card.oracle_text
        # ETB fixed
        assert "enters the battlefield" not in result.card.oracle_text

    def test_validate_card_from_raw_with_autofix(self):
        """Integration: validate_card_from_raw applies auto-fixes."""
        raw = {
            "name": "Test Beast",
            "type_line": "Creature — Beast",
            "mana_cost": "{2}{G}",
            "cmc": 4.0,  # wrong — should be 3
            "oracle_text": "Trample",
            "power": "3",
            "toughness": "3",
            "colors": ["G"],
            "color_identity": ["G"],
            "card_types": ["Creature"],
            "subtypes": ["Beast"],
        }
        card, _errors, fixes = validate_card_from_raw(raw)
        assert card is not None
        assert card.cmc == 3.0  # auto-fixed
        assert len(fixes) > 0

    def test_color_identity_from_oracle_auto_fixed(self):
        """Oracle text color references get added to color_identity."""
        card = _make_card(
            oracle_text="{B}: ~ gains deathtouch until end of turn.",
            color_identity=[Color.GREEN],  # missing Black
        )
        errors = validate_card(card)
        result = auto_fix_card(card, errors)
        fixed_identity = {c.value for c in result.card.color_identity}
        assert "B" in fixed_identity
        assert "G" in fixed_identity


# ===========================================================================
# Integration: a card with multiple problems
# ===========================================================================


class TestIntegration:
    def test_card_with_multiple_issues(self):
        """A card that should trigger errors from multiple validators."""
        card = _make_card(
            name="Flame Serpent",
            mana_cost="{2}{R}",
            cmc=4.0,  # Wrong — should be 3
            colors=[Color.RED],
            color_identity=[Color.RED],
            card_types=["Creature"],
            type_line="Creature — Serpent",
            subtypes=["Serpent"],
            oracle_text=(
                "Haste\n"
                "When Flame Serpent enters the battlefield, "
                "Flame Serpent deals 3 damage to any target"
            ),
            power="5",
            toughness="5",
            rarity=Rarity.COMMON,
        )
        errors = validate_card(card)

        # Should have errors from multiple validators
        validators_hit = {e.validator for e in errors}
        assert "mana" in validators_hit, "CMC mismatch should be caught"
        assert "rules_text" in validators_hit, "ETB/self-ref should be caught"

        # Must have manual errors (requiring retry)
        assert has_manual_errors(errors)

    def test_auto_fix_then_only_manual_remain(self):
        """After auto-fixing, only MANUAL errors should remain."""
        card = _make_card(
            name="Flame Serpent",
            mana_cost="{2}{R}",
            cmc=4.0,  # AUTO: CMC mismatch
            colors=[Color.RED],
            color_identity=[Color.RED],
            card_types=["Creature"],
            type_line="Creature — Serpent",
            subtypes=["Serpent"],
            oracle_text=(
                "Haste\n"
                "When Flame Serpent enters the battlefield, "
                "Flame Serpent deals 3 damage to any target"
            ),
            power="5",
            toughness="5",
            rarity=Rarity.COMMON,
        )
        errors = validate_card(card)
        result = auto_fix_card(card, errors)

        # All remaining errors should be MANUAL
        for e in result.remaining_errors:
            assert e.severity == ValidationSeverity.MANUAL, (
                f"Non-MANUAL error after auto-fix: {e.error_code}: {e.message}"
            )

        # Auto-fixes should have been applied
        assert result.card.cmc == 3.0
        assert "Flame Serpent" not in result.card.oracle_text
        assert "enters the battlefield" not in result.card.oracle_text
