"""Comprehensive tests for the validation library.

Tests cover the format-hygiene validators that run at gen time (schema, mana,
type_check, rules_text, text_overflow, uniqueness.collector_number) plus the
auto-fix system that deterministically corrects AUTO errors.

Design-judgment heuristics (power_level, color_pie, mechanical similarity)
live in :mod:`mtgai.analysis.heuristic_checks` now and are covered by
``tests/test_analysis/test_heuristic_checks.py``. Tests that exercise those
individual validator functions still live here (under TestPowerLevel etc.)
but call the validator directly rather than going through ``validate_card``.
"""

from __future__ import annotations

import pytest

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
from mtgai.validation.color_pie import validate_color_pie
from mtgai.validation.power_level import classify_pt, validate_power_level
from mtgai.validation.uniqueness import (
    validate_collector_number,
    validate_mechanical_similarity,
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


@pytest.fixture
def custom_keywords_salvage():
    """Supply a set's custom mechanics to the rules-text validators.

    Custom keywords are normally resolved from the active project's
    ``mechanics/approved.json``; tests with no on-disk project pin them via
    ``set_custom_keywords``. Resets the override afterwards so it can't bleed
    into other tests.
    """
    from mtgai.validation import rules_text

    rules_text.set_custom_keywords(["salvage", "malfunction", "overclock"])
    yield
    rules_text.set_custom_keywords(None)


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
        card, errors, _fixes, regen = validate_card_from_raw(raw)
        assert card is not None
        assert regen is False  # clean card needs no regen
        schema_errors = _errors_by_validator(errors, "schema")
        assert len(schema_errors) == 0

    def test_missing_name_is_manual(self):
        raw = {"type_line": "Creature — Bear"}
        card, errors, _fixes, regen = validate_card_from_raw(raw)
        assert card is None
        assert regen is True  # schema parse failure is a regen trigger
        assert len(errors) > 0
        assert all(e.severity == ValidationSeverity.MANUAL for e in errors)

    def test_wrong_type_is_manual(self):
        raw = {
            "name": "Bad Card",
            "type_line": "Creature",
            "cmc": "not a number",  # should be float
        }
        card, errors, _fixes, _regen = validate_card_from_raw(raw)
        # Should get at least one error about the float type
        assert card is None or any("cmc" in e.field for e in errors)


# ===========================================================================
# Color normalization (name-form -> canonical WUBRG letters)
# ===========================================================================


class TestColorNormalization:
    """``colors`` / ``color_identity`` accept full color names and normalize them
    to canonical WUBRG letters at validation, so name-form colors persisted
    out-of-band ('blue', 'White') can't mis-group downstream (e.g. 'blue' as 'B').
    """

    def test_name_form_blue_normalizes_to_letter(self):
        card = Card.model_validate({"name": "x", "type_line": "Creature", "colors": ["blue"]})
        assert card.colors == [Color.BLUE]
        assert [c.value for c in card.colors] == ["U"]

    def test_name_form_titlecase_white_normalizes(self):
        card = Card.model_validate({"name": "x", "type_line": "Creature", "colors": ["White"]})
        assert card.colors == [Color.WHITE]

    def test_mixed_name_form_multicolor_normalizes_each(self):
        card = Card.model_validate(
            {"name": "x", "type_line": "Creature", "colors": ["white", "blue"]}
        )
        assert card.colors == [Color.WHITE, Color.BLUE]
        assert [c.value for c in card.colors] == ["W", "U"]

    def test_canonical_letter_unchanged(self):
        card = Card.model_validate({"name": "x", "type_line": "Creature", "colors": ["U"]})
        assert card.colors == [Color.BLUE]

    def test_lowercase_canonical_letter_normalizes(self):
        card = Card.model_validate({"name": "x", "type_line": "Creature", "colors": ["u"]})
        assert card.colors == [Color.BLUE]

    def test_color_identity_also_normalized(self):
        card = Card.model_validate(
            {
                "name": "x",
                "type_line": "Creature",
                "colors": ["red"],
                "color_identity": ["red", "green"],
            }
        )
        assert card.colors == [Color.RED]
        assert card.color_identity == [Color.RED, Color.GREEN]

    def test_validate_card_from_raw_round_trip(self):
        raw = {
            "name": "Cybertronian Data-Link",
            "type_line": "Artifact",
            "mana_cost": "{U}",
            "oracle_text": "",
            "colors": ["blue"],
            "color_identity": ["blue"],
        }
        card, _errors, _fixes, _regen = validate_card_from_raw(raw)
        assert card is not None
        assert card.colors == [Color.BLUE]
        assert card.color_identity == [Color.BLUE]

    def test_invalid_color_still_rejected(self):
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            Card.model_validate({"name": "x", "type_line": "Creature", "colors": ["purple"]})


# ===========================================================================
# Mana consistency
# ===========================================================================


class TestDeriveManaFields:
    """``derive_mana_fields`` — card-gen derives cmc/colors/color_identity from
    mana_cost (+ oracle symbols) instead of asking the LLM for them."""

    def test_basic_cost(self):
        from mtgai.validation.mana import derive_mana_fields

        out = derive_mana_fields("{1}{W}{W}", None)
        assert out == {"cmc": 3.0, "colors": ["W"], "color_identity": ["W"]}

    def test_x_counts_as_zero_and_wubrg_order(self):
        from mtgai.validation.mana import derive_mana_fields

        out = derive_mana_fields("{X}{G}{W}", None)
        assert out["cmc"] == 2.0  # X = 0, two colored pips
        assert out["colors"] == ["W", "G"]  # WUBRG order, not input order

    def test_color_identity_picks_up_oracle_symbols(self):
        from mtgai.validation.mana import derive_mana_fields

        out = derive_mana_fields("{2}{R}", "{G}: ~ gains trample.")
        assert out["colors"] == ["R"]  # cost colors only
        assert out["color_identity"] == ["R", "G"]  # cost + oracle

    def test_empty_cost_land_with_oracle_mana(self):
        from mtgai.validation.mana import derive_mana_fields

        out = derive_mana_fields("", "{T}: Add {U} or {B}.")
        assert out["cmc"] == 0.0
        assert out["colors"] == []
        assert out["color_identity"] == ["U", "B"]

    def test_slim_model_output_validates_clean(self):
        """A card with only the fields the new schema asks for, once derived,
        passes the mana validator with no mismatch errors."""
        from mtgai.validation.mana import derive_mana_fields

        raw = {
            "name": "Autobot Precision Strike",
            "mana_cost": "{1}{W}{W}",
            "type_line": "Instant",
            "oracle_text": "Exile target creature unless its controller pays {2}.",
            "rarity": "common",
        }
        raw.update(derive_mana_fields(raw["mana_cost"], raw["oracle_text"]))
        card, _errors, fixes, _regen = validate_card_from_raw(raw, existing_cards=[], auto_fix=True)
        assert card is not None
        assert card.cmc == 3.0
        assert [c.value for c in card.colors] == ["W"]
        assert not [f for f in fixes if "mana." in f]  # no mana auto-fix churn


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

    def test_noncreature_vehicle_without_pt_is_manual(self):
        # A non-creature Vehicle (Artifact — Vehicle) with no P/T is the bug:
        # it slips past the creature rule but is non-functional once crewed.
        card = _make_card(
            card_types=["Artifact"],
            subtypes=["Vehicle"],
            type_line="Artifact — Vehicle",
            oracle_text="Crew 2",
            power=None,
            toughness=None,
        )
        errors = _errors_by_validator(validate_card(card), "type_check")
        assert any(e.error_code == "type_check.vehicle_missing_pt" for e in errors)
        assert _has_error(errors, validator="type_check", severity="MANUAL")

    def test_noncreature_vehicle_with_pt_is_ok(self):
        # A non-creature Vehicle WITH P/T is correct — it must not trip the
        # "non-creature has P/T" or "P/T without Creature" rules.
        card = _make_card(
            card_types=["Artifact"],
            subtypes=["Vehicle"],
            type_line="Artifact — Vehicle",
            oracle_text="Crew 2",
            power="3",
            toughness="4",
        )
        errors = _errors_by_validator(validate_card(card), "type_check")
        codes = {e.error_code for e in errors}
        assert "type_check.vehicle_missing_pt" not in codes
        assert "type_check.noncreature_has_pt" not in codes
        assert "type_check.pt_without_creature" not in codes

    def test_creature_vehicle_without_pt_is_manual(self):
        # A Creature — Vehicle missing P/T fails too: both the creature rule and
        # the vehicle rule fire; either is enough to block it.
        card = _make_card(
            card_types=["Artifact", "Creature"],
            subtypes=["Vehicle"],
            type_line="Artifact Creature — Vehicle",
            oracle_text="Crew 2",
            power=None,
            toughness=None,
        )
        errors = _errors_by_validator(validate_card(card), "type_check")
        codes = {e.error_code for e in errors}
        assert "type_check.vehicle_missing_pt" in codes
        assert "type_check.creature_missing_pt" in codes

    def test_vehicle_with_only_one_stat_is_manual(self):
        # The rule fires when EITHER stat is missing, not just both.
        card = _make_card(
            card_types=["Artifact"],
            subtypes=["Vehicle"],
            type_line="Artifact — Vehicle",
            oracle_text="Crew 2",
            power="3",
            toughness=None,
        )
        errors = _errors_by_validator(validate_card(card), "type_check")
        assert any(e.error_code == "type_check.vehicle_missing_pt" for e in errors)

    def test_vehicle_subtype_detection_is_case_insensitive(self):
        # The schema parser stores subtypes verbatim, so a "Artifact — vehicle"
        # type line yields a lowercase subtype. The Vehicle P/T rule must still
        # fire — this is the realistic path the bug travels.
        from mtgai.validation.schema import _parse_type_line

        raw = _make_card(
            card_types=[],
            subtypes=[],
            type_line="Artifact — vehicle",
            oracle_text="Crew 2",
            power=None,
            toughness=None,
        )
        card = _parse_type_line(raw)
        assert card.subtypes == ["vehicle"]
        errors = _errors_by_validator(validate_card(card), "type_check")
        assert any(e.error_code == "type_check.vehicle_missing_pt" for e in errors)


class TestTypeLineOrdering:
    """Type lines must read <supertypes> <card types> — <subtypes>.

    LLMs strand a card type after the dash ("Creature — Artifact Peacekeeper")
    or order the main types wrong; the structured parts come out right but the
    raw string — what renders — keeps the bad order. The AUTO fixer rebuilds it.
    """

    def test_stranded_card_type_is_auto_flagged(self):
        card = _make_card(
            type_line="Creature — Artifact Peacekeeper",
            card_types=["Creature", "Artifact"],
            subtypes=["Peacekeeper"],
        )
        errors = _errors_by_validator(validate_card(card), "type_check")
        assert any(e.error_code == "type_check.type_line_order" for e in errors)
        assert all(
            e.severity == ValidationSeverity.AUTO
            for e in errors
            if e.error_code == "type_check.type_line_order"
        )

    def test_auto_fix_moves_card_type_before_dash(self):
        raw = {
            "name": "Brass Sentinel",
            "type_line": "Creature — Artifact Peacekeeper",
            "mana_cost": "{3}",
            "cmc": 3.0,
            "oracle_text": "Vigilance",
            "power": "2",
            "toughness": "4",
            "rarity": "common",
        }
        card, _errors, fixes, regen = validate_card_from_raw(raw)
        assert regen is False
        assert card.type_line == "Artifact Creature — Peacekeeper"
        assert set(card.card_types) == {"Artifact", "Creature"}
        assert card.subtypes == ["Peacekeeper"]
        assert any("type_line_order" in f for f in fixes)

    def test_auto_fix_subtypeless_artifact_creature(self):
        """'Creature — Artifact' (no real subtype) collapses to 'Artifact Creature'."""
        raw = {
            "name": "Iron Husk",
            "type_line": "Creature — Artifact",
            "mana_cost": "{2}",
            "cmc": 2.0,
            "oracle_text": "",
            "power": "1",
            "toughness": "3",
            "rarity": "common",
        }
        card, _errors, _fixes, _regen = validate_card_from_raw(raw)
        assert card.type_line == "Artifact Creature"
        assert set(card.card_types) == {"Artifact", "Creature"}
        assert card.subtypes == []

    def test_main_type_order_normalized(self):
        """Card types before the dash get sorted into printed order too."""
        card = _make_card(
            type_line="Creature Artifact — Golem",
            card_types=["Creature", "Artifact"],
            subtypes=["Golem"],
        )
        errors = _errors_by_validator(validate_card(card), "type_check")
        order = next(e for e in errors if e.error_code == "type_check.type_line_order")
        assert "Artifact Creature — Golem" in order.message

    def test_dash_style_preserved(self):
        """The card's existing dash (-- vs —) survives the rebuild."""
        card = _make_card(
            type_line="Creature -- Artifact Peacekeeper",
            card_types=["Creature", "Artifact"],
            subtypes=["Peacekeeper"],
        )
        result = auto_fix_card(card, validate_card(card))
        assert result.card.type_line == "Artifact Creature -- Peacekeeper"

    def test_already_canonical_is_untouched(self):
        card = _make_card(
            type_line="Artifact Creature — Insect Beast",
            card_types=["Artifact", "Creature"],
            subtypes=["Insect", "Beast"],
        )
        errors = _errors_by_validator(validate_card(card), "type_check")
        assert not any(e.error_code == "type_check.type_line_order" for e in errors)

    def test_plain_creature_is_untouched(self):
        card = _make_card()  # "Creature — Beast"
        errors = _errors_by_validator(validate_card(card), "type_check")
        assert not any(e.error_code == "type_check.type_line_order" for e in errors)

    def test_supertype_ordering(self):
        """A misplaced supertype is pulled to the front of the main types."""
        card = _make_card(
            type_line="Creature Legendary — Spirit",
            card_types=["Creature"],
            supertypes=["Legendary"],
            subtypes=["Spirit"],
        )
        result = auto_fix_card(card, validate_card(card))
        assert result.card.type_line == "Legendary Creature — Spirit"


# ===========================================================================
# Structural shape checks — power / toughness / loyalty garbage, missing cost.
# All of these are regen triggers: a card can't be saved with garbage in its
# stat fields or no way to be cast, so validate_card_from_raw returns
# regen=True and the card-gen retry loop re-prompts the model.
# ===========================================================================


class TestStatShape:
    def test_pt_slash_triggers_regen(self):
        """LLM stuffs both stats in one field: power='1/1'. Regen."""
        raw = {
            "name": "Slash Stat",
            "type_line": "Creature — Beast",
            "mana_cost": "{2}{G}",
            "oracle_text": "Trample",
            "power": "1/1",
            "toughness": "1",
            "rarity": "common",
            "card_types": ["Creature"],
            "subtypes": ["Beast"],
        }
        _card, errors, _fixes, regen = validate_card_from_raw(raw)
        assert regen is True
        assert any(e.error_code == "type_check.pt_slash" for e in errors)

    def test_pt_literal_null_triggers_regen(self):
        """LLM writes the string 'null' into a stat field. Regen."""
        raw = {
            "name": "Literal Null Stat",
            "type_line": "Creature — Beast",
            "mana_cost": "{2}{G}",
            "oracle_text": "Trample",
            "power": "null",
            "toughness": "null",
            "rarity": "common",
            "card_types": ["Creature"],
            "subtypes": ["Beast"],
        }
        _card, errors, _fixes, regen = validate_card_from_raw(raw)
        assert regen is True
        assert any(e.error_code == "type_check.pt_literal_null" for e in errors)

    def test_pt_sentinel_dash_triggers_regen(self):
        """Sentinel '-' / '—' / 'N/A' all mean "no value"; regen instead of guessing."""
        raw = {
            "name": "Dash Stat",
            "type_line": "Creature — Beast",
            "mana_cost": "{2}{G}",
            "oracle_text": "",
            "power": "-",
            "toughness": "N/A",
            "rarity": "common",
            "card_types": ["Creature"],
            "subtypes": ["Beast"],
        }
        _card, errors, _fixes, regen = validate_card_from_raw(raw)
        assert regen is True
        assert sum(1 for e in errors if e.error_code == "type_check.pt_literal_null") >= 2

    def test_pt_nonstandard_garbage_triggers_regen(self):
        """A stat value that isn't an integer, '*', or a known special. Regen."""
        raw = {
            "name": "Garbage Stat",
            "type_line": "Creature — Beast",
            "mana_cost": "{2}{G}",
            "oracle_text": "",
            "power": "tall",
            "toughness": "2",
            "rarity": "common",
            "card_types": ["Creature"],
            "subtypes": ["Beast"],
        }
        _card, errors, _fixes, regen = validate_card_from_raw(raw)
        assert regen is True
        assert any(e.error_code == "type_check.pt_nonstandard" for e in errors)

    def test_legal_star_and_x_stats_are_fine(self):
        """``*`` and ``X`` are legal Magic stat values; no regen."""
        for value in ("*", "X", "1+*", "2+*", "*+1"):
            card = _make_card(power=value, toughness="2")
            assert _errors_by_validator(validate_card(card), "type_check") == [] or all(
                e.error_code
                not in {
                    "type_check.pt_slash",
                    "type_check.pt_literal_null",
                    "type_check.pt_nonstandard",
                }
                for e in _errors_by_validator(validate_card(card), "type_check")
            ), f"{value!r} should be a legal stat"

    def test_negative_pt_is_allowed_shape_wise(self):
        """Negative stats are rare but a legal shape (power_level heuristic
        flags them; the structural check just checks the format)."""
        card = _make_card(power="-1", toughness="2")
        errors = _errors_by_validator(validate_card(card), "type_check")
        assert not any(
            e.error_code
            in {
                "type_check.pt_slash",
                "type_check.pt_literal_null",
                "type_check.pt_nonstandard",
            }
            for e in errors
        )

    def test_loyalty_slash_also_caught(self):
        """The stat-shape checks apply to loyalty too — a slashed loyalty is
        the same kind of busted stat as a slashed P/T."""
        raw = {
            "name": "Slashed Loyalty PW",
            "type_line": "Planeswalker — Test",
            "mana_cost": "{2}{W}{U}",
            "oracle_text": "+1: Draw a card.\n-3: Target creature is exiled.",
            "loyalty": "3/1",
            "rarity": "mythic",
            "card_types": ["Planeswalker"],
            "subtypes": ["Test"],
        }
        _card, errors, _fixes, regen = validate_card_from_raw(raw)
        assert regen is True
        assert any(e.error_code == "type_check.pt_slash" for e in errors)


class TestNonlandMissingCost:
    def test_creature_with_no_cost_triggers_regen(self):
        """Predacon Sky-Stalker case: creature with mana_cost=None. Regen."""
        raw = {
            "name": "Costless Beast",
            "type_line": "Creature — Beast",
            "mana_cost": None,
            "oracle_text": "Trample",
            "power": "2",
            "toughness": "2",
            "rarity": "common",
            "card_types": ["Creature"],
            "subtypes": ["Beast"],
        }
        _card, errors, _fixes, regen = validate_card_from_raw(raw)
        assert regen is True
        assert any(e.error_code == "type_check.nonland_missing_cost" for e in errors)

    def test_artifact_with_empty_cost_triggers_regen(self):
        """Empty-string mana_cost on an artifact is just as broken as None."""
        raw = {
            "name": "Costless Artifact",
            "type_line": "Artifact",
            "mana_cost": "",
            "oracle_text": "{T}: Add {C}.",
            "rarity": "common",
            "card_types": ["Artifact"],
        }
        _card, errors, _fixes, regen = validate_card_from_raw(raw)
        assert regen is True
        assert any(e.error_code == "type_check.nonland_missing_cost" for e in errors)

    def test_land_with_no_cost_is_fine(self):
        """Lands are allowed (required) to have no mana cost."""
        raw = {
            "name": "Test Plains",
            "type_line": "Basic Land — Plains",
            "mana_cost": None,
            "oracle_text": "({T}: Add {W}.)",
            "rarity": "common",
            "card_types": ["Land"],
            "supertypes": ["Basic"],
            "subtypes": ["Plains"],
        }
        _card, errors, _fixes, regen = validate_card_from_raw(raw)
        assert regen is False
        assert not any(e.error_code == "type_check.nonland_missing_cost" for e in errors)

    def test_noncreature_pt_also_triggers_regen(self):
        """The pre-existing noncreature_has_pt finding is now a regen
        trigger — an artifact with P/T is structurally invalid MTG."""
        raw = {
            "name": "Stat Artifact",
            "type_line": "Artifact",
            "mana_cost": "{3}",
            "oracle_text": "{T}: Add {C}.",
            "power": "0",
            "toughness": "5",
            "rarity": "common",
            "card_types": ["Artifact"],
        }
        _card, errors, _fixes, regen = validate_card_from_raw(raw)
        assert regen is True
        assert any(e.error_code == "type_check.noncreature_has_pt" for e in errors)


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

    def test_haste_enters_tapped_nonbo(self):
        card = _make_card(
            oracle_text="Haste\nThis creature enters tapped.",
        )
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert _has_error(errors, validator="rules_text", severity="MANUAL")
        assert any("nonbo" in e.message.lower() for e in errors)

    def test_enters_tapped_without_haste_is_ok(self):
        card = _make_card(
            oracle_text="This creature enters tapped.",
        )
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert not any("nonbo" in e.message.lower() for e in errors)

    def test_haste_with_enters_tapped_only_in_reminder_is_ok(self):
        # A reminder describing entering tapped (e.g. a custom mechanic) is not
        # itself a nonbo — only an enters-tapped clause in the rules text is.
        card = _make_card(
            oracle_text="Haste\nMalfunction 2 (This permanent enters tapped with 2 counters.)",
        )
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert not any("nonbo" in e.message.lower() for e in errors)

    def test_reminder_text_in_oracle_not_flagged(self):
        """Reminder text in oracle is no longer flagged — it's injected programmatically."""
        card = _make_card(
            oracle_text=(
                "Flying (This creature can't be blocked except by creatures with flying.)"
            ),
        )
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert not any("reminder text" in e.message.lower() for e in errors)

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

    # ---- Reminder-text protection (parenthesized spans) ----
    # Reminder text is injected programmatically and may legitimately contain
    # phrases the AUTO fixers target. The scans must not flag, and the fixers
    # must not rewrite, anything inside parentheses (CLAUDE.md: "Validators
    # that touch oracle text must skip parenthesized text").

    def test_etb_only_in_reminder_not_flagged(self, custom_keywords_salvage):
        card = _make_card(
            oracle_text="Salvage 2 (When ~ enters the battlefield, return a card.)",
        )
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert not any("enters the battlefield" in e.message.lower() for e in errors)

    def test_fix_etb_preserves_reminder_text(self):
        """Genuine ETB outside parens is rewritten; reminder text inside is untouched."""
        original = (
            "When ~ enters the battlefield, draw a card. "
            "(Whenever this enters the battlefield, you may scry.)"
        )
        card = _make_card(oracle_text=original)
        result = auto_fix_card(card, validate_card(card))
        assert result.card.oracle_text == (
            "When ~ enters, draw a card. (Whenever this enters the battlefield, you may scry.)"
        )

    def test_cannot_only_in_reminder_not_flagged(self):
        card = _make_card(
            oracle_text="Flying (This creature cannot be blocked except by fliers.)",
        )
        errors = _errors_by_validator(validate_card(card), "rules_text")
        assert not any(e.error_code == "rules_text.cannot" for e in errors)

    def test_fix_cannot_preserves_reminder_text(self):
        original = "~ cannot attack. (Defenders cannot attack and can not be sacrificed.)"
        card = _make_card(oracle_text=original)
        result = auto_fix_card(card, validate_card(card))
        assert result.card.oracle_text == (
            "~ can't attack. (Defenders cannot attack and can not be sacrificed.)"
        )

    def test_fix_etb_still_rewrites_genuine_oracle(self):
        card = _make_card(oracle_text="When ~ enters the battlefield, draw a card.")
        result = auto_fix_card(card, validate_card(card))
        assert result.card.oracle_text == "When ~ enters, draw a card."

    def test_fix_cannot_still_rewrites_genuine_oracle(self):
        card = _make_card(oracle_text="~ cannot be blocked. Creatures can not block ~.")
        result = auto_fix_card(card, validate_card(card))
        assert result.card.oracle_text == "~ can't be blocked. Creatures can't block ~."

    def test_fix_etb_mixed_inside_and_outside_parens(self, custom_keywords_salvage):
        # Keyword line kept on top so this exercises only ETB paren-preservation,
        # not the keyword_ordering reorder.
        card = _make_card(
            oracle_text=(
                "Salvage (When ~ enters the battlefield, return it.)\n"
                "When ~ enters the battlefield, scry 1."
            ),
        )
        result = auto_fix_card(card, validate_card(card))
        assert result.card.oracle_text == (
            "Salvage (When ~ enters the battlefield, return it.)\nWhen ~ enters, scry 1."
        )


# ===========================================================================
# Keyword ordering
# ===========================================================================


class TestKeywordOrdering:
    """Keyword abilities must sit above complex abilities (MTG templating)."""

    def test_in_order_is_ok(self):
        card = _make_card(
            oracle_text="Flying\nWhen ~ enters, draw a card.",
        )
        errors = _errors_by_validator(validate_card(card), "keyword_ordering")
        assert errors == []

    def test_keyword_below_complex_is_flagged(self):
        card = _make_card(
            oracle_text="When ~ enters, draw a card.\nFlying",
        )
        errors = _errors_by_validator(validate_card(card), "keyword_ordering")
        assert _has_error(errors, validator="keyword_ordering", severity="AUTO")
        assert any(e.error_code == "keyword_ordering.misplaced" for e in errors)

    def test_keyword_sandwiched_is_flagged(self):
        card = _make_card(
            oracle_text=(
                "Whenever another creature dies, you may pay {B}.\n"
                "Shroud\n"
                "When ~ dies, look at the top three cards of your library."
            ),
        )
        errors = _errors_by_validator(validate_card(card), "keyword_ordering")
        assert _has_error(errors, validator="keyword_ordering", severity="AUTO")

    def test_multiple_keyword_lines_in_order_ok(self):
        card = _make_card(
            oracle_text="Flying, vigilance\nWard {2}\nWhen ~ enters, gain 2 life.",
        )
        errors = _errors_by_validator(validate_card(card), "keyword_ordering")
        assert errors == []

    def test_keywords_only_ok(self):
        card = _make_card(oracle_text="Flying\nTrample")
        errors = _errors_by_validator(validate_card(card), "keyword_ordering")
        assert errors == []

    def test_single_line_never_flagged(self):
        # A keyword that's part of a complex sentence isn't a keyword line.
        card = _make_card(
            oracle_text="When a creature with flying attacks, draw a card.",
        )
        errors = _errors_by_validator(validate_card(card), "keyword_ordering")
        assert errors == []

    def test_custom_keyword_ordering(self, custom_keywords_salvage):
        card = _make_card(
            oracle_text="When ~ enters, scry 1.\nSalvage 2",
            mechanic_tags=["salvage"],
        )
        errors = _errors_by_validator(validate_card(card), "keyword_ordering")
        assert _has_error(errors, validator="keyword_ordering", severity="AUTO")

    def test_equip_at_bottom_not_flagged(self):
        # Equip templates at the bottom of the textbox, not the top.
        card = _make_card(
            type_line="Artifact — Equipment",
            card_types=["Artifact"],
            subtypes=["Equipment"],
            power=None,
            toughness=None,
            oracle_text="Equipped creature gets +1/+1.\nEquip {2}",
        )
        errors = _errors_by_validator(validate_card(card), "keyword_ordering")
        assert errors == []

    # ---- Fixer ----

    def test_fix_reorders_keyword_above_complex(self):
        card = _make_card(oracle_text="When ~ enters, draw a card.\nFlying")
        result = auto_fix_card(card, validate_card(card))
        assert result.card.oracle_text == "Flying\n\nWhen ~ enters, draw a card."

    def test_fix_reorders_sandwiched_keyword(self):
        card = _make_card(
            oracle_text=(
                "Whenever another creature dies, you may pay {B}.\n"
                "Shroud\n"
                "When ~ dies, look at the top three cards."
            ),
        )
        result = auto_fix_card(card, validate_card(card))
        assert result.card.oracle_text == (
            "Shroud\n\n"
            "Whenever another creature dies, you may pay {B}.\n"
            "When ~ dies, look at the top three cards."
        )

    def test_fix_preserves_keyword_relative_order(self):
        card = _make_card(
            oracle_text="When ~ enters, gain 2 life.\nFlying, vigilance\nWard {2}",
        )
        result = auto_fix_card(card, validate_card(card))
        assert result.card.oracle_text == (
            "Flying, vigilance\nWard {2}\n\nWhen ~ enters, gain 2 life."
        )

    def test_fix_preserves_reminder_text_on_keyword_line(self):
        # Reminder text rides on the moved keyword line, untouched.
        card = _make_card(
            oracle_text=(
                "When ~ enters, draw a card.\n"
                "Flying (This creature can't be blocked except by fliers.)"
            ),
        )
        result = auto_fix_card(card, validate_card(card))
        assert result.card.oracle_text == (
            "Flying (This creature can't be blocked except by fliers.)\n\n"
            "When ~ enters, draw a card."
        )

    def test_in_order_card_fix_is_noop(self):
        card = _make_card(oracle_text="Flying\nWhen ~ enters, draw a card.")
        result = auto_fix_card(card, validate_card(card))
        assert result.card.oracle_text == "Flying\nWhen ~ enters, draw a card."


# ===========================================================================
# Custom-keyword resolution (active project → mechanics/approved.json)
# ===========================================================================


class TestCustomKeywordResolution:
    """The validators recognize the active project's custom mechanics as keywords.

    The vocabulary is no longer a hardcoded seed: ``rules_text.custom_keywords``
    resolves the active project's ``mechanics/approved.json`` mechanic names so
    any set's keywords classify as valid keyword-only lines.
    """

    @pytest.fixture
    def project_with_mechanics(self, tmp_path):
        """Pin an active project whose approved.json names one custom mechanic.

        Each test gets a unique ``tmp_path``, so the resolver's ``(path, ...)``
        cache can't bleed between tests — no manual cache reset is needed.
        """
        import json

        from mtgai.runtime import active_project
        from mtgai.settings import model_settings as ms
        from mtgai.validation import rules_text

        asset = tmp_path / "proj"
        (asset / "mechanics").mkdir(parents=True)
        (asset / "mechanics" / "approved.json").write_text(
            json.dumps([{"name": "Frostbite", "keyword_type": "keyword_ability"}]),
            encoding="utf-8",
        )
        active_project.write_active_project(
            active_project.ProjectState(
                set_code="FRZ", settings=ms.ModelSettings(asset_folder=str(asset))
            )
        )
        rules_text.set_custom_keywords(None)  # ensure active-project resolution
        yield asset
        rules_text.set_custom_keywords(None)
        active_project.clear_active_project()

    def test_approved_mechanic_recognized_as_keyword(self, project_with_mechanics):
        from mtgai.validation import rules_text

        assert "frostbite" in rules_text.custom_keywords()
        assert "frostbite" in rules_text.all_keywords()

    def test_custom_keyword_line_flagged_when_below_complex(self, project_with_mechanics):
        # "Frostbite 2" is a keyword-only line for this project, so ordering it
        # below a complex ability is an AUTO keyword_ordering finding.
        card = _make_card(oracle_text="When ~ enters, scry 1.\nFrostbite 2")
        errors = _errors_by_validator(validate_card(card), "keyword_ordering")
        assert _has_error(errors, validator="keyword_ordering", severity="AUTO")

    def test_no_project_falls_back_to_evergreen_only(self):
        from mtgai.runtime import active_project
        from mtgai.validation import rules_text

        active_project.clear_active_project()
        rules_text.set_custom_keywords(None)
        # No project open → only evergreen keywords; an unknown word isn't one.
        assert rules_text.custom_keywords() == frozenset()
        assert "frostbite" not in rules_text.all_keywords()
        assert "flying" in rules_text.all_keywords()

    def _open_with_mechanics(self, tmp_path, mechanics):
        import json

        from mtgai.runtime import active_project
        from mtgai.settings import model_settings as ms
        from mtgai.validation import rules_text

        asset = tmp_path / "proj"
        (asset / "mechanics").mkdir(parents=True)
        body = mechanics if isinstance(mechanics, str) else json.dumps(mechanics)
        (asset / "mechanics" / "approved.json").write_text(body, encoding="utf-8")
        active_project.write_active_project(
            active_project.ProjectState(
                set_code="TST", settings=ms.ModelSettings(asset_folder=str(asset))
            )
        )
        rules_text.set_custom_keywords(None)

    def test_only_keyword_ability_mechanics_recognized(self, tmp_path):
        """Ability words and keyword actions never classify a line as keyword-only."""
        from mtgai.runtime import active_project
        from mtgai.validation import rules_text

        try:
            self._open_with_mechanics(
                tmp_path,
                [
                    {"name": "Frostbite", "keyword_type": "keyword_ability"},
                    {"name": "Landfall", "keyword_type": "ability_word"},
                    {"name": "Investigate", "keyword_type": "keyword_action"},
                    {"name": "Untyped"},  # missing keyword_type defaults to ability
                ],
            )
            kws = rules_text.custom_keywords()
            assert "frostbite" in kws
            assert "untyped" in kws  # missing keyword_type treated as keyword_ability
            assert "landfall" not in kws
            assert "investigate" not in kws
        finally:
            rules_text.set_custom_keywords(None)
            active_project.clear_active_project()

    def test_malformed_approved_json_falls_back_to_empty(self, tmp_path):
        from mtgai.runtime import active_project
        from mtgai.validation import rules_text

        try:
            self._open_with_mechanics(tmp_path, "{ not valid json")
            assert rules_text.custom_keywords() == frozenset()
        finally:
            rules_text.set_custom_keywords(None)
            active_project.clear_active_project()

    def test_set_custom_keywords_strips_and_lowercases(self):
        from mtgai.validation import rules_text

        try:
            rules_text.set_custom_keywords([" Salvage ", "OVERCLOCK", "", "  "])
            assert rules_text.custom_keywords() == frozenset({"salvage", "overclock"})
        finally:
            rules_text.set_custom_keywords(None)

    def test_empty_override_suppresses_approved_json(self, tmp_path):
        """An explicit empty override wins over active-project resolution."""
        from mtgai.runtime import active_project
        from mtgai.validation import rules_text

        try:
            self._open_with_mechanics(
                tmp_path, [{"name": "Frostbite", "keyword_type": "keyword_ability"}]
            )
            rules_text.set_custom_keywords([])  # explicit empty, not None
            assert rules_text.custom_keywords() == frozenset()
            assert "frostbite" not in rules_text.all_keywords()
        finally:
            rules_text.set_custom_keywords(None)
            active_project.clear_active_project()


# ===========================================================================
# Power level
# ===========================================================================


class TestPowerLevel:
    """``validate_power_level`` is a design-judgment validator; it's called
    directly here (not through ``validate_card``, which now only runs format
    hygiene) and aggregated by ``analysis.heuristic_checks`` in production."""

    def test_vanilla_over_frontier_flagged(self):
        # 6/6 for 2 mana common vanilla -> printed 2-mana vanillas top out ~3/3.
        card = _make_card(
            mana_cost="{1}{G}",
            cmc=2.0,
            power="6",
            toughness="6",
            rarity=Rarity.COMMON,
            oracle_text="",
        )
        errors = validate_power_level(card)
        assert _has_error(errors, validator="power_level", severity="MANUAL")
        assert any(e.error_code == "power_level.pt_over" for e in errors)

    def test_vanilla_under_frontier_flagged(self):
        # 3/3 for 7 mana common vanilla -> below the printed 7-mana vanilla floor.
        card = _make_card(
            mana_cost="{6}{G}",
            cmc=7.0,
            power="3",
            toughness="3",
            rarity=Rarity.COMMON,
            oracle_text="",
        )
        errors = validate_power_level(card)
        assert any(e.error_code == "power_level.pt_under" for e in errors)

    def test_big_vanilla_is_fair(self):
        # 7/7 for 7 mana vanilla -> a fair big beater; must NOT be flagged
        # (the regression that started this: it used to be nuked as "overstatted").
        card = _make_card(
            mana_cost="{6}{G}",
            cmc=7.0,
            power="7",
            toughness="7",
            rarity=Rarity.COMMON,
            oracle_text="",
        )
        errors = validate_power_level(card)
        assert not any(
            e.error_code in ("power_level.pt_over", "power_level.pt_under") for e in errors
        )

    def test_ability_creature_not_pt_flagged(self):
        # A creature WITH abilities is exempt from the body-only P/T check entirely.
        card = _make_card(
            mana_cost="{1}{G}",
            cmc=2.0,
            power="6",
            toughness="6",
            rarity=Rarity.COMMON,
            oracle_text="Trample",
        )
        errors = validate_power_level(card)
        assert not any(
            e.error_code in ("power_level.pt_over", "power_level.pt_under") for e in errors
        )

    def test_mythic_vanilla_never_over(self):
        # A splashy mythic vanilla body is uncapped on the OVER side (e.g. 10/10-for-5).
        card = _make_card(
            mana_cost="{4}{G}",
            cmc=5.0,
            power="10",
            toughness="10",
            rarity=Rarity.MYTHIC,
            oracle_text="",
        )
        errors = validate_power_level(card)
        assert not any(e.error_code == "power_level.pt_over" for e in errors)

    def test_common_vanilla_fine(self):
        # 3/3 for 3 mana vanilla common -> squarely within the printed frontier.
        card = _make_card(
            oracle_text="",
            power="3",
            toughness="3",
        )
        errors = validate_power_level(card)
        assert not any("P/T" in e.message or "Power" in e.message for e in errors)

    def test_classify_pt_frontier_and_rarity(self):
        # Big fair beater is fair; over/under are caught; rarity raises the ceiling.
        assert classify_pt(7, 7, 7, Rarity.COMMON) == "fair"
        assert classify_pt(2, 6, 6, Rarity.COMMON) == "over"
        assert classify_pt(7, 3, 3, Rarity.COMMON) == "under"
        # 6/6-for-5 is over at common but the rare ceiling bonus makes it fair.
        assert classify_pt(5, 6, 6, Rarity.COMMON) == "over"
        assert classify_pt(5, 6, 6, Rarity.RARE) == "fair"
        # Mythic is never over.
        assert classify_pt(5, 12, 12, Rarity.MYTHIC) != "over"
        # A lopsided body within the stat budget is fine (distribution is a choice).
        assert classify_pt(4, 6, 2, Rarity.COMMON) == "fair"

    def test_nwo_modal_at_common(self):
        card = _make_card(oracle_text="Choose one —\n• Draw a card.\n• ~ deals 2 damage.")
        errors = validate_power_level(card)
        assert any("Modal" in e.message for e in errors)

    def test_nwo_ok_at_uncommon(self):
        card = _make_card(
            rarity=Rarity.UNCOMMON,
            oracle_text="Choose one —\n• Draw a card.\n• ~ deals 2 damage.",
        )
        errors = validate_power_level(card)
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
        errors = validate_power_level(card)
        assert any("Zero" in e.message or "zero" in e.message.lower() for e in errors)

    def test_not_run_through_validate_card(self):
        """The format-hygiene runner no longer surfaces power_level findings —
        those go through ``analysis.heuristic_checks`` now."""
        card = _make_card(
            mana_cost="{1}{G}",
            cmc=2.0,
            power="4",
            toughness="4",
            rarity=Rarity.COMMON,
            oracle_text="Trample",
        )
        assert _errors_by_validator(validate_card(card), "power_level") == []


# ===========================================================================
# Color pie
# ===========================================================================


class TestColorPie:
    """``validate_color_pie`` is a design-judgment validator; same shape as
    TestPowerLevel — called directly, aggregated by heuristic_checks."""

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
        assert validate_color_pie(card) == []

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
        errors = validate_color_pie(card)
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
        assert validate_color_pie(card) == []

    def test_trample_in_green_ok(self):
        card = _make_card(oracle_text="Trample")
        errors = validate_color_pie(card)
        assert not any("trample" in e.message.lower() for e in errors)

    def test_trample_in_blue_flagged(self):
        card = _make_card(
            colors=[Color.BLUE],
            color_identity=[Color.BLUE],
            mana_cost="{2}{U}",
            oracle_text="Trample",
        )
        errors = validate_color_pie(card)
        assert _has_error(errors, validator="color_pie", severity="MANUAL")

    def test_not_run_through_validate_card(self):
        """Format-hygiene runner doesn't surface color_pie findings."""
        card = _make_card(
            colors=[Color.BLUE],
            color_identity=[Color.BLUE],
            mana_cost="{2}{U}",
            oracle_text="Trample",
        )
        assert _errors_by_validator(validate_card(card), "color_pie") == []


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

    def test_oracle_overflow_triggers_regen_required(self):
        """Content overflow (oracle) is a regen trigger from validate_card_from_raw —
        the card-gen retry loop reacts to ``regen_required`` to re-prompt."""
        raw = {
            "name": "Verbose Beast",
            "type_line": "Creature — Beast",
            "mana_cost": "{2}{G}",
            "oracle_text": "x" * 350,  # over the 300-char creature limit
            "power": "3",
            "toughness": "3",
            "rarity": "common",
            "card_types": ["Creature"],
            "subtypes": ["Beast"],
        }
        card, errors, _fixes, regen = validate_card_from_raw(raw)
        assert card is not None  # schema still parsed
        assert regen is True
        assert any(e.error_code == "text_overflow.oracle" for e in errors)

    def test_long_type_line_is_auto_fixed_not_regen(self):
        """A type line a few chars over the guideline is AUTO-shortened by
        trimming trailing subtypes — NOT a regen trigger. This is the
        Megatron / slot-009 fix: a 47-char ``Legendary Artifact Creature —
        Decepticon Leader`` must not be regenerated-then-dropped."""
        raw = {
            "name": "Megatron",
            "type_line": "Legendary Artifact Creature — Decepticon Leader",
            "mana_cost": "{2}{W}{B}",
            "oracle_text": "Trample",
            "power": "5",
            "toughness": "5",
            "rarity": "mythic",
        }
        card, errors, fixes, regen = validate_card_from_raw(raw, auto_fix=True)
        assert card is not None
        assert regen is False  # auto-fixed, never reaches the regen loop
        assert len(card.type_line) <= 45
        assert card.type_line.startswith("Legendary Artifact Creature")
        assert any("type_line" in f for f in fixes)
        assert not any(e.error_code == "text_overflow.type_line" for e in errors)

    def test_type_line_overflow_fixer_trims_minimal_subtypes(self):
        """The fixer drops only as many trailing subtypes as needed to fit,
        keeping as much flavor as possible."""
        from mtgai.validation import ValidationError, ValidationSeverity
        from mtgai.validation.text_overflow import fix_type_line_overflow

        # 48 chars: "Legendary Creature — Eldrazi Horror Aberration Spawn"
        card = _make_card(
            type_line="Legendary Creature — Eldrazi Horror Aberration Spawn",
            card_types=["Creature"],
            supertypes=["Legendary"],
            subtypes=["Eldrazi", "Horror", "Aberration", "Spawn"],
        )
        err = ValidationError(
            validator="text_overflow",
            severity=ValidationSeverity.AUTO,
            field="type_line",
            message="too long",
            error_code="text_overflow.type_line",
        )
        fixed = fix_type_line_overflow(card, err)
        assert len(fixed.type_line) <= 45
        # Kept the leading subtypes, dropped only trailing ones.
        assert fixed.type_line.startswith("Legendary Creature — Eldrazi Horror")
        assert "Spawn" not in fixed.subtypes


# ===========================================================================
# Uniqueness
# ===========================================================================


class TestUniqueness:
    """Two surfaces:

    * ``validate_collector_number`` — AUTO collision fix, runs at gen time via
      ``validate_card``.
    * ``validate_mechanical_similarity`` — MANUAL design findings, lives in
      ``analysis.heuristic_checks`` and runs at council-review / final-QA time.
    """

    def test_duplicate_name_manual(self):
        card = _make_card(name="Fire Bolt", collector_number="002")
        existing = [_make_card(name="Fire Bolt", collector_number="001")]
        errors = validate_mechanical_similarity(card, existing)
        assert _has_error(errors, validator="uniqueness", severity="MANUAL")

    def test_near_duplicate_name_manual(self):
        card = _make_card(name="Fire Bolt", collector_number="002")
        existing = [_make_card(name="Fire Blt", collector_number="001")]
        errors = validate_mechanical_similarity(card, existing)
        assert _has_error(errors, validator="uniqueness", severity="MANUAL")

    def test_collector_number_collision_auto(self):
        """Collector-number collision stays at gen time as an AUTO fix —
        accessible both directly and through the format-hygiene runner."""
        card = _make_card(name="Card A", collector_number="001")
        existing = [_make_card(name="Card B", collector_number="001")]
        direct = validate_collector_number(card, existing)
        assert _has_error(direct, validator="uniqueness", severity="AUTO")
        # Also surfaces via validate_card (format-hygiene runner).
        runner_errors = _errors_by_validator(validate_card(card, existing), "uniqueness")
        assert _has_error(runner_errors, validator="uniqueness", severity="AUTO")

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
        errors = validate_mechanical_similarity(card, existing)
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
        assert validate_collector_number(card, existing) == []
        assert validate_mechanical_similarity(card, existing) == []

    def test_mechanical_similarity_not_run_through_validate_card(self):
        """Format-hygiene runner doesn't surface mechanical-similarity findings."""
        card = _make_card(name="Fire Bolt", collector_number="002")
        existing = [_make_card(name="Fire Bolt", collector_number="001")]
        # validate_card returns format-hygiene errors only — no duplicate-name MANUAL.
        runner_errors = _errors_by_validator(validate_card(card, existing), "uniqueness")
        assert not any(e.severity == ValidationSeverity.MANUAL for e in runner_errors)


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

    def test_auto_fix_modal_asterisk_bullet(self):
        """Markdown ``*`` bullets on modal lines get rewritten to ``•``."""
        card = _make_card(
            oracle_text=("Choose one —\n* Draw a card.\n* ~ deals 2 damage to any target."),
        )
        errors = validate_card(card)
        result = auto_fix_card(card, errors)
        assert "* Draw" not in result.card.oracle_text
        assert "* ~ deals" not in result.card.oracle_text
        assert "• Draw a card." in result.card.oracle_text
        assert "• ~ deals 2 damage to any target." in result.card.oracle_text
        assert any("modal_asterisk_bullet" in f for f in result.applied_fixes)

    def test_modal_asterisk_fix_leaves_other_asterisks_alone(self):
        """Mid-line ``*`` (e.g. inside a sentence) isn't a bullet, leave it."""
        card = _make_card(oracle_text="Power and toughness are each equal to *.")
        errors = validate_card(card)
        result = auto_fix_card(card, errors)
        assert "•" not in result.card.oracle_text
        assert result.card.oracle_text == "Power and toughness are each equal to *."

    def test_auto_fix_oracle_type_prefix(self):
        """An "Artifact." / "Creature." header line gets stripped."""
        card = _make_card(
            card_types=["Artifact"],
            type_line="Artifact",
            subtypes=[],
            power=None,
            toughness=None,
            oracle_text="Artifact.\n\n{T}: Add {C}.",
        )
        errors = validate_card(card)
        result = auto_fix_card(card, errors)
        assert not result.card.oracle_text.startswith("Artifact.")
        assert result.card.oracle_text.startswith("{T}: Add {C}.")
        assert any("oracle_type_prefix" in f for f in result.applied_fixes)

    def test_oracle_type_prefix_fix_only_strips_first_line(self):
        """A type word in the middle of oracle text isn't a prefix; don't strip."""
        card = _make_card(
            oracle_text="When ~ enters, destroy target Artifact you don't control.",
        )
        errors = validate_card(card)
        result = auto_fix_card(card, errors)
        # The middle "Artifact" is part of the rule; should be preserved.
        assert "Artifact" in result.card.oracle_text

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
        card, _errors, fixes, regen = validate_card_from_raw(raw)
        assert card is not None
        assert card.cmc == 3.0  # auto-fixed
        assert len(fixes) > 0
        assert regen is False  # auto-fixable issues don't trigger regen

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
        """A card that should trigger errors from multiple format-hygiene validators."""
        card = _make_card(
            name="Flame Serpent",
            mana_cost="{2}{R}",
            cmc=4.0,  # Wrong — should be 3
            colors=[Color.RED],
            color_identity=[Color.RED],
            card_types=["Creature"],
            type_line="Creature — Serpent",
            subtypes=["Serpent"],
            oracle_text=("Haste\nWhen Flame Serpent enters the battlefield, draw two cards"),
            power="5",
            toughness="5",
            rarity=Rarity.COMMON,
        )
        errors = validate_card(card)

        # Format-hygiene runner: mana + rules_text validators trip.
        validators_hit = {e.validator for e in errors}
        assert "mana" in validators_hit, "CMC mismatch should be caught"
        assert "rules_text" in validators_hit, "ETB/self-ref should be caught"

        # Design-tier MANUAL checks live in heuristic_checks, not validate_card —
        # verify they're findable there (red card with blue card-draw -> color_pie).
        from mtgai.analysis.heuristic_checks import check_card_heuristics

        heuristic_findings = check_card_heuristics(card)
        assert any(f.validator == "color_pie" for f in heuristic_findings)

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
