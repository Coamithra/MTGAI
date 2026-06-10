"""Unit tests for the deterministic spec self-check (no LLM)."""

from __future__ import annotations

from mtgai.generation.spec_check import (
    SpecTargets,
    check_card_against_spec,
    detect_infeasible,
    format_spec_feedback,
    parse_spec_targets,
)
from mtgai.models.card import Card


def _slot(tweaked: str | None = None, **extra) -> dict:
    return {
        "slot_id": "001",
        "color": extra.pop("color", "W"),
        "rarity": extra.pop("rarity", "common"),
        "card_type": extra.pop("card_type", "creature"),
        "cmc_target": extra.pop("cmc_target", 2),
        "mechanic_tag": extra.pop("mechanic_tag", "vanilla"),
        "tweaked_text": tweaked,
        **extra,
    }


def _card(**overrides) -> Card:
    base = {
        "name": "Test Card",
        "mana_cost": "{1}{W}",
        "cmc": 2.0,
        "colors": ["W"],
        "color_identity": ["W"],
        "type_line": "Creature — Human",
    }
    base.update(overrides)
    return Card(**base)


# ---------------------------------------------------------------------------
# CMC parsing
# ---------------------------------------------------------------------------


def test_parse_cmc_canonical_descriptor() -> None:
    assert parse_spec_targets(_slot("White · common · creature · CMC4 · vanilla")).cmc == 4


def test_parse_cmc_with_space() -> None:
    assert parse_spec_targets(_slot("Green ramp creature at CMC 7")).cmc == 7


def test_parse_cmc_ambiguous_two_values_extracts_nothing() -> None:
    # A hand-edited "CMC2 or CMC3" pins no single CMC → conservative None.
    assert parse_spec_targets(_slot("creature, CMC2 or CMC3")).cmc is None


def test_parse_cmc_absent() -> None:
    assert parse_spec_targets(_slot("White · common · creature · vanilla")).cmc is None


# ---------------------------------------------------------------------------
# Color parsing
# ---------------------------------------------------------------------------


def test_parse_colors_mono_structured_field() -> None:
    assert parse_spec_targets(
        _slot("Blue · common · instant · CMC1 · vanilla")
    ).colors == frozenset({"U"})


def test_parse_colors_joined_pair_slash() -> None:
    assert parse_spec_targets(_slot("Blue/Green ramp creature CMC4")).colors == frozenset(
        {"U", "G"}
    )


def test_parse_colors_joined_pair_dash() -> None:
    assert parse_spec_targets(_slot("White-Blue flier that draws a card")).colors == frozenset(
        {"W", "U"}
    )


def test_parse_colors_signpost_tag_overrides_mono_field() -> None:
    # signpost:WU is the documented colour authority; it wins over the mono
    # structured colour field the relabel sometimes leaves contradicting.
    t = parse_spec_targets(_slot("White · uncommon · creature · CMC2 · complex · signpost:WU"))
    assert t.colors == frozenset({"W", "U"})


def test_parse_colors_bare_trailing_tag_does_not_override() -> None:
    # A bare "· UR" is an ambiguous archetype leftover, NOT a colour assertion:
    # the structured mono colour field wins, so colours = {U}, not {U, R}.
    t = parse_spec_targets(_slot("Blue · uncommon · instant · CMC3 · Cycling · UR"))
    assert t.colors == frozenset({"U"})


def test_parse_colors_prose_pair_in_note_does_not_override_mono_field() -> None:
    # A joined color phrasing in the free-text NOTE ("a red-green themed beast")
    # must NOT override the structured mono color field — that prose false
    # positive would poison retries (the slot is mono Red, not Red/Green).
    t = parse_spec_targets(
        _slot("Red · common · creature · CMC2 · vanilla (a red-green themed beast in flavor)")
    )
    assert t.colors == frozenset({"R"})


def test_parse_colors_multicolor_word_is_ambiguous() -> None:
    assert parse_spec_targets(_slot("Multicolor · uncommon · creature · CMC3")).colors is None


def test_parse_colors_colorless_word_is_ambiguous() -> None:
    assert parse_spec_targets(_slot("Colorless · common · artifact · CMC2")).colors is None


# ---------------------------------------------------------------------------
# Type parsing
# ---------------------------------------------------------------------------


def test_parse_type_simple() -> None:
    assert parse_spec_targets(_slot("Red · common · instant · CMC2 · burn")).card_type == "instant"


def test_parse_type_compound_enchantment_creature() -> None:
    assert (
        parse_spec_targets(_slot("Green · rare · enchantment creature · CMC7 · complex")).card_type
        == "enchantment creature"
    )


def test_parse_type_compound_artifact_creature() -> None:
    assert (
        parse_spec_targets(_slot("Colorless · rare · artifact creature · CMC4")).card_type
        == "artifact creature"
    )


def test_parse_type_tolerates_subtype_parenthetical() -> None:
    assert (
        parse_spec_targets(_slot("Red · common · creature (spider) · CMC2 · vanilla")).card_type
        == "creature"
    )


def test_parse_type_only_from_structured_field_not_prose() -> None:
    # The free-text note mentions "an artifact you control" but the type field
    # is creature — must not false-positive on the prose mention.
    t = parse_spec_targets(
        _slot("Red · common · creature · CMC2 · vanilla (notes: sacrifice an artifact you control)")
    )
    assert t.card_type == "creature"


# ---------------------------------------------------------------------------
# Fully-fuzzy descriptor extracts nothing
# ---------------------------------------------------------------------------


def test_unstructured_descriptor_extracts_nothing() -> None:
    t = parse_spec_targets(_slot("a flavorful card about a creature that fights at dawn"))
    assert t.is_empty()


def test_falls_back_to_render_slot_string_when_no_tweaked() -> None:
    # No tweaked_text → render_slot_string("White · common · creature · CMC2 · vanilla").
    t = parse_spec_targets(_slot(None, color="W", card_type="creature", cmc_target=2))
    assert t.cmc == 2
    assert t.colors == frozenset({"W"})
    assert t.card_type == "creature"


# ---------------------------------------------------------------------------
# check_card_against_spec
# ---------------------------------------------------------------------------


def test_check_card_matches_all() -> None:
    targets = SpecTargets(cmc=2, colors=frozenset({"W"}), card_type="creature")
    assert check_card_against_spec(_card(), targets) == []


def test_check_card_cmc_miss() -> None:
    targets = SpecTargets(cmc=4)
    misses = check_card_against_spec(_card(cmc=3.0), targets)
    assert len(misses) == 1
    assert misses[0].field == "cmc"
    assert misses[0].want == "4"
    assert "CMC3" in misses[0].got


def test_check_card_color_miss() -> None:
    targets = SpecTargets(colors=frozenset({"U", "G"}))
    misses = check_card_against_spec(_card(mana_cost="{U}", colors=["U"], cmc=1.0), targets)
    assert len(misses) == 1
    assert misses[0].field == "colors"


def test_check_card_type_miss() -> None:
    targets = SpecTargets(card_type="enchantment creature")
    misses = check_card_against_spec(_card(type_line="Creature — Human"), targets)
    assert len(misses) == 1
    assert misses[0].field == "card_type"


def test_check_card_hybrid_satisfies_two_colors_at_cmc1() -> None:
    # A {G/U} card is both green and blue at CMC1 — the spec is satisfied.
    card = _card(mana_cost="{G/U}", colors=["U", "G"], cmc=1.0)
    targets = SpecTargets(cmc=1, colors=frozenset({"U", "G"}))
    assert check_card_against_spec(card, targets) == []


# ---------------------------------------------------------------------------
# Infeasibility
# ---------------------------------------------------------------------------


def test_infeasible_two_colors_cmc1_suggests_hybrid() -> None:
    hint = detect_infeasible(SpecTargets(cmc=1, colors=frozenset({"U", "G"})))
    assert hint is not None
    assert "hybrid" in hint.lower()
    assert "{G/U}" in hint


def test_feasible_two_colors_cmc2_no_hint() -> None:
    assert detect_infeasible(SpecTargets(cmc=2, colors=frozenset({"U", "G"}))) is None


def test_infeasible_needs_both_cmc_and_colors() -> None:
    assert detect_infeasible(SpecTargets(cmc=1)) is None
    assert detect_infeasible(SpecTargets(colors=frozenset({"U", "G"}))) is None


# ---------------------------------------------------------------------------
# Feedback formatting
# ---------------------------------------------------------------------------


def test_format_spec_feedback_names_deltas_and_hint() -> None:
    targets = SpecTargets(cmc=1, colors=frozenset({"U", "G"}))
    misses = check_card_against_spec(_card(mana_cost="{U}", colors=["U"], cmc=1.0), targets)
    text = format_spec_feedback("My Card", misses, detect_infeasible(targets))
    assert "My Card" in text
    assert "colors" in text
    assert "hybrid" in text.lower()
