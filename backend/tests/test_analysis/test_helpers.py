"""Tests for analysis helper functions."""

from __future__ import annotations

from mtgai.analysis.helpers import (
    classify_mechanic_complexity,
    creature_weight_class,
    detect_card_advantage,
    detect_mana_fixing,
    detect_removal,
    get_card_types,
    infer_skeleton_color,
    infer_skeleton_color_pair,
    is_creature,
    parse_card_types_from_type_line,
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
# parse_card_types_from_type_line
# ---------------------------------------------------------------------------


class TestParseCardTypes:
    def test_simple_creature(self):
        assert parse_card_types_from_type_line("Creature -- Human Rogue") == ["Creature"]

    def test_artifact_creature(self):
        result = parse_card_types_from_type_line("Artifact Creature -- Construct")
        assert "Artifact" in result
        assert "Creature" in result

    def test_legendary_creature(self):
        result = parse_card_types_from_type_line("Legendary Creature -- Human Soldier")
        assert result == ["Creature"]
        assert "Legendary" not in result

    def test_instant(self):
        assert parse_card_types_from_type_line("Instant") == ["Instant"]

    def test_sorcery(self):
        assert parse_card_types_from_type_line("Sorcery") == ["Sorcery"]

    def test_enchantment_artifact_after_dash(self):
        result = parse_card_types_from_type_line("Legendary Enchantment -- Artifact")
        assert "Enchantment" in result
        assert "Artifact" in result
        assert "Legendary" not in result

    def test_basic_land(self):
        result = parse_card_types_from_type_line("Basic Land -- Plains")
        assert result == ["Land"]

    def test_em_dash_separator(self):
        result = parse_card_types_from_type_line("Creature \u2014 Beast")
        assert result == ["Creature"]

    def test_en_dash_separator(self):
        result = parse_card_types_from_type_line("Creature \u2013 Beast")
        assert result == ["Creature"]


# ---------------------------------------------------------------------------
# is_creature / get_card_types
# ---------------------------------------------------------------------------


class TestIsCreature:
    def test_creature_from_card_types(self):
        card = _make_card(card_types=["Creature"])
        assert is_creature(card)

    def test_creature_from_type_line(self):
        card = _make_card(card_types=[], type_line="Creature -- Beast")
        assert is_creature(card)

    def test_instant_not_creature(self):
        card = _make_card(
            card_types=["Instant"],
            type_line="Instant",
            power=None,
            toughness=None,
        )
        assert not is_creature(card)


class TestGetCardTypes:
    def test_prefers_card_types_field(self):
        card = _make_card(card_types=["Creature"], type_line="Instant")
        assert get_card_types(card) == ["Creature"]

    def test_falls_back_to_type_line(self):
        card = _make_card(card_types=[], type_line="Artifact Creature -- Construct")
        types = get_card_types(card)
        assert "Artifact" in types
        assert "Creature" in types


# ---------------------------------------------------------------------------
# infer_skeleton_color
# ---------------------------------------------------------------------------


class TestInferSkeletonColor:
    def test_mono_white(self):
        card = _make_card(colors=[Color.WHITE])
        assert infer_skeleton_color(card) == "W"

    def test_multicolor(self):
        card = _make_card(colors=[Color.WHITE, Color.BLUE])
        assert infer_skeleton_color(card) == "multicolor"

    def test_colorless(self):
        card = _make_card(colors=[])
        assert infer_skeleton_color(card) == "colorless"


class TestInferSkeletonColorPair:
    def test_wu(self):
        card = _make_card(colors=[Color.WHITE, Color.BLUE])
        assert infer_skeleton_color_pair(card) == "WU"

    def test_bg_ordered(self):
        # Even if given out of WUBRG order, should return "BG"
        card = _make_card(colors=[Color.GREEN, Color.BLACK])
        assert infer_skeleton_color_pair(card) == "BG"

    def test_mono_returns_none(self):
        card = _make_card(colors=[Color.RED])
        assert infer_skeleton_color_pair(card) is None


# ---------------------------------------------------------------------------
# classify_mechanic_complexity
# ---------------------------------------------------------------------------


class TestClassifyMechanicComplexity:
    def test_vanilla(self):
        card = _make_card(oracle_text="")
        assert classify_mechanic_complexity(card) == "vanilla"

    def test_french_vanilla_keyword(self):
        # "Flying" = 6 chars, within 15
        card = _make_card(oracle_text="Flying")
        assert classify_mechanic_complexity(card) == "french_vanilla"

    def test_french_vanilla_mana_dork(self):
        # "{T}: Add {G}." = 13 chars
        card = _make_card(oracle_text="{T}: Add {G}.")
        assert classify_mechanic_complexity(card) == "french_vanilla"

    def test_evergreen_simple_removal(self):
        # "Destroy target creature." = 24 chars
        card = _make_card(oracle_text="Destroy target creature.")
        assert classify_mechanic_complexity(card) == "evergreen"

    def test_evergreen_with_reminder_stripped(self):
        # After stripping reminder text: "When ~ enters, salvage 3." = 25 chars
        card = _make_card(
            oracle_text="When ~ enters, salvage 3. (Look at the top three cards "
            "of your library. You may put an artifact card from among them into "
            "your hand. Put the rest on the bottom in any order.)"
        )
        assert classify_mechanic_complexity(card) == "evergreen"

    def test_complex_long_text(self):
        # 91+ chars of rules text = complex
        card = _make_card(
            oracle_text="Whenever a creature you control dies, you may pay 1 life. "
            "If you do, draw a card. At the beginning of your end step, lose life."
        )
        assert classify_mechanic_complexity(card) == "complex"

    def test_complex_multi_ability(self):
        card = _make_card(
            oracle_text="Haste\nWhenever ~ attacks, create a 1/1 white token.\n"
            "{2}{R}: ~ gets +2/+0 until end of turn."
        )
        assert classify_mechanic_complexity(card) == "complex"


# ---------------------------------------------------------------------------
# detect_removal
# ---------------------------------------------------------------------------


class TestDetectRemoval:
    def test_destroy_creature(self):
        assert detect_removal("Destroy target creature.")

    def test_exile_permanent(self):
        assert detect_removal("Exile target permanent.")

    def test_damage_spell(self):
        assert detect_removal("~ deals 3 damage to any target.")

    def test_bounce(self):
        assert detect_removal("Return target creature to its owner's hand.")

    def test_counter(self):
        assert detect_removal("Counter target spell.")

    def test_fight(self):
        assert detect_removal("~ fights target creature.")

    def test_vanilla_not_removal(self):
        assert not detect_removal("Trample")

    def test_empty_not_removal(self):
        assert not detect_removal("")


# ---------------------------------------------------------------------------
# detect_card_advantage
# ---------------------------------------------------------------------------


class TestDetectCardAdvantage:
    def test_draw(self):
        assert detect_card_advantage("Draw a card.")

    def test_draw_two(self):
        assert detect_card_advantage("Draw two cards.")

    def test_create_token(self):
        assert detect_card_advantage("Create a 1/1 white Soldier creature token.")

    def test_scry(self):
        assert detect_card_advantage("Scry 2.")

    def test_search_library(self):
        assert detect_card_advantage("Search your library for a card.")

    def test_vanilla_not_ca(self):
        assert not detect_card_advantage("Flying")


# ---------------------------------------------------------------------------
# detect_mana_fixing
# ---------------------------------------------------------------------------


class TestDetectManaFixing:
    def test_any_color(self):
        card = _make_card(
            oracle_text="Add one mana of any color.",
            type_line="Artifact",
            card_types=["Artifact"],
            power=None,
            toughness=None,
        )
        assert detect_mana_fixing(card)

    def test_multicolor_land(self):
        card = _make_card(
            oracle_text="{T}: Add {W} or {U}.",
            type_line="Land",
            card_types=["Land"],
            colors=[],
            color_identity=[Color.WHITE, Color.BLUE],
            power=None,
            toughness=None,
        )
        assert detect_mana_fixing(card)

    def test_basic_creature_not_fixing(self):
        card = _make_card(oracle_text="Trample")
        assert not detect_mana_fixing(card)


# ---------------------------------------------------------------------------
# creature_weight_class
# ---------------------------------------------------------------------------


class TestCreatureWeightClass:
    def test_small(self):
        assert creature_weight_class("1", "1") == "small"

    def test_medium(self):
        assert creature_weight_class("2", "2") == "medium"

    def test_beefy(self):
        assert creature_weight_class("3", "3") == "beefy"

    def test_huge(self):
        assert creature_weight_class("5", "5") == "huge"

    def test_star_power(self):
        assert creature_weight_class("*", "4") == "n/a"

    def test_none_power(self):
        assert creature_weight_class(None, "3") == "n/a"
