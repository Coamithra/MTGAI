"""Tests for knob threading + cycle reservation in generate_skeleton (card 6a16d8ff).

The schema itself is covered by test_skeleton_knobs.py; this file checks how the
knobs and cycles flow through the deterministic build: behavior preservation with
defaults, the scalar knobs reshaping the distribution within bounds, and cycles
being carved out balance-preservingly (including the guildgate land case).
"""

from __future__ import annotations

import pytest

from mtgai.skeleton.generator import (
    SetConfig,
    SlotCardType,
    _assign_card_types,
    _distribute_colors,
    _expand_cycle,
    _place_planeswalkers,
    _reserve_cycles,
    _scale_rarity,
    generate_skeleton,
)
from mtgai.skeleton.knobs import Cycle, CycleSpan, SkeletonKnobs, default_knobs


def _cfg(set_size: int = 277, **kw) -> SetConfig:
    return SetConfig(name="Test", code="TST", set_size=set_size, **kw)


# ---------------------------------------------------------------------------
# Behavior preservation with defaults
# ---------------------------------------------------------------------------


class TestDefaultsPreserveBehavior:
    @pytest.mark.parametrize("size", [20, 60, 100, 277, 300])
    def test_default_knobs_match_no_knobs(self, size: int):
        # Passing default_knobs() must be identical to passing nothing.
        a = generate_skeleton(_cfg(size))
        b = generate_skeleton(_cfg(size), knobs=default_knobs())
        assert [s.model_dump() for s in a.slots] == [s.model_dump() for s in b.slots]

    @pytest.mark.parametrize("size", [60, 100, 277, 300])
    def test_defaults_pass_hard_constraints(self, size: int):
        r = generate_skeleton(_cfg(size))
        assert r.balance_report.all_hard_passed is True

    def test_default_has_no_planeswalker(self):
        # planeswalker_count defaults to 0 — the failure-path skeleton is unchanged.
        r = generate_skeleton(_cfg(277))
        assert not any(s.card_type == "planeswalker" for s in r.slots)

    def test_default_has_no_cycles(self):
        r = generate_skeleton(_cfg(277))
        assert r.cycles == []
        assert all(s.cycle_id is None for s in r.slots)

    def test_scale_rarity_uses_weights(self):
        # Weights 95/98/63/20 sum to 276; the +1 to hit 277 lands in the largest
        # bucket (uncommon), matching the historical scaling.
        base = _scale_rarity(277)
        assert sum(base.values()) == 277
        assert base["common"] == 95 and base["rare"] == 63 and base["mythic"] == 20
        # Bumping the rare weight raises the rare count.
        bumped = _scale_rarity(277, SkeletonKnobs(rarity_rare=70))
        assert bumped["rare"] > base["rare"]
        assert sum(bumped.values()) == 277


# ---------------------------------------------------------------------------
# Scalar knobs reshape the distribution
# ---------------------------------------------------------------------------


class TestScalarKnobs:
    def test_gold_heavy_stays_balanced(self):
        k = SkeletonKnobs(multicolor_rare=0.45, multicolor_mythic=0.50, rarity_rare=70)
        r = generate_skeleton(_cfg(277), knobs=k)
        assert r.total_slots == 277
        assert r.balance_report.all_hard_passed is True
        assert (
            r.balance_report.multicolor_count
            > generate_skeleton(_cfg(277)).balance_report.multicolor_count
        )

    def test_two_signposts_per_pair_doubles_multicolor_uncommons(self):
        r1 = generate_skeleton(_cfg(277), knobs=SkeletonKnobs(signposts_per_pair=1))
        r2 = generate_skeleton(_cfg(277), knobs=SkeletonKnobs(signposts_per_pair=2))
        mu1 = sum(1 for s in r1.slots if s.rarity == "uncommon" and s.color == "multicolor")
        mu2 = sum(1 for s in r2.slots if s.rarity == "uncommon" and s.color == "multicolor")
        assert mu1 == 10 and mu2 == 20
        signs2 = sum(1 for s in r2.slots if s.signpost_for)
        assert signs2 == 20  # two signposts marked per pair
        assert r2.balance_report.all_hard_passed is True

    def test_planeswalker_count_places_pw_from_mythic(self):
        r = generate_skeleton(_cfg(277), knobs=SkeletonKnobs(planeswalker_count=2))
        pw = [s for s in r.slots if s.card_type == "planeswalker"]
        assert len(pw) == 2
        assert all(s.rarity == "mythic" for s in pw)
        assert r.balance_report.all_hard_passed is True

    def test_artifact_bias_adds_colored_artifacts(self):
        # Default puts no artifacts in colored slots; bumping the bias does.
        default_art = sum(
            1
            for s in generate_skeleton(_cfg(277)).slots
            if s.card_type == "artifact" and s.color != "colorless"
        )
        assert default_art == 0
        k = SkeletonKnobs(noncreature_artifact=0.5)
        skewed_art = sum(
            1
            for s in generate_skeleton(_cfg(277), knobs=k).slots
            if s.card_type == "artifact" and s.color != "colorless"
        )
        assert skewed_art > 0

    def test_creature_floor_preserved_under_knobs(self):
        k = SkeletonKnobs(creature_common=0.45, creature_uncommon=0.45)
        r = generate_skeleton(_cfg(277), knobs=k)
        assert r.balance_report.all_hard_passed is True

    def test_assign_card_types_respects_creature_knob(self):
        types = _assign_card_types("W", "common", 100, SkeletonKnobs(creature_common=0.60))
        assert sum(1 for t in types if t == SlotCardType.CREATURE) == 60

    def test_distribute_colors_count_invariant(self):
        slots = _distribute_colors("rare", 14, 60, SkeletonKnobs(multicolor_rare=0.40))
        assert len(slots) == 14


# ---------------------------------------------------------------------------
# Cycles
# ---------------------------------------------------------------------------


class TestCycleExpansion:
    def test_mono5_spans_each_color(self):
        members = _expand_cycle(Cycle(id="c", name="Titans", span=CycleSpan.MONO5))
        assert [m["color"] for m in members] == ["W", "U", "B", "R", "G"]

    def test_pairs10_spans_each_pair(self):
        members = _expand_cycle(Cycle(id="c", name="Gates", span=CycleSpan.PAIRS10))
        assert len(members) == 10
        assert {m["color_pair"] for m in members} == {
            "WU",
            "WB",
            "WR",
            "WG",
            "UB",
            "UR",
            "UG",
            "BR",
            "BG",
            "RG",
        }
        assert all(m["color"] == "multicolor" for m in members)

    def test_allied_and_enemy_partition_the_pairs(self):
        allied = {
            m["color_pair"] for m in _expand_cycle(Cycle(id="a", name="A", span=CycleSpan.ALLIED5))
        }
        enemy = {
            m["color_pair"] for m in _expand_cycle(Cycle(id="e", name="E", span=CycleSpan.ENEMY5))
        }
        assert len(allied) == 5 and len(enemy) == 5
        assert allied.isdisjoint(enemy)
        assert allied | enemy == {"WU", "WB", "WR", "WG", "UB", "UR", "UG", "BR", "BG", "RG"}

    def test_colorless_member(self):
        members = _expand_cycle(Cycle(id="c", name="X", span=CycleSpan.COLORLESS1))
        assert len(members) == 1 and members[0]["color"] == "colorless"

    def test_land_cycle_members_are_lands(self):
        members = _expand_cycle(
            Cycle(id="g", name="Gates", span=CycleSpan.PAIRS10, card_type="land", cmc_target=0)
        )
        assert all(m["card_type"] == "land" for m in members)
        assert all(m["cmc_target"] == 0 for m in members)
        assert all(m["cycle_id"] == "g" for m in members)


class TestCycleReservation:
    def test_mono5_rare_cycle_stays_balanced(self):
        k = SkeletonKnobs(
            cycles=[Cycle(id="t", name="Titans", span=CycleSpan.MONO5, rarity="rare", cmc_target=6)]
        )
        r = generate_skeleton(_cfg(277), knobs=k)
        assert r.total_slots == 277
        assert r.balance_report.all_hard_passed is True
        members = [s for s in r.slots if s.cycle_id == "t"]
        assert len(members) == 5
        assert {m.color for m in members} == {"W", "U", "B", "R", "G"}
        assert all(m.rarity == "rare" for m in members)

    def test_guildgate_land_cycle(self):
        k = SkeletonKnobs(
            cycles=[
                Cycle(
                    id="gates",
                    name="Gates",
                    span=CycleSpan.PAIRS10,
                    rarity="common",
                    card_type="land",
                    cmc_target=0,
                    template="Enters tapped; taps for the pair.",
                )
            ]
        )
        r = generate_skeleton(_cfg(277), knobs=k)
        assert r.total_slots == 277
        assert r.balance_report.all_hard_passed is True
        lands = [s for s in r.slots if s.card_type == "land"]
        assert len(lands) == 10
        assert all(s.cycle_id == "gates" for s in lands)
        # Lands are excluded from creature density, so it still holds.
        assert r.balance_report.creature_pct >= 50.0

    def test_uncommon_cycle_members_not_flagged_as_signposts(self):
        # A pairs10 uncommon creature cycle fills the multicolor-uncommon slots;
        # cycle members must NOT also get the signpost brief (competing prompt).
        k = SkeletonKnobs(
            cycles=[Cycle(id="mentors", name="Mentors", span=CycleSpan.PAIRS10, rarity="uncommon")]
        )
        r = generate_skeleton(_cfg(277), knobs=k)
        assert r.balance_report.all_hard_passed is True
        cycle_members = [s for s in r.slots if s.cycle_id == "mentors"]
        assert cycle_members  # the cycle landed
        assert all(s.signpost_for is None for s in cycle_members)

    def test_cycles_kept_recorded_on_result(self):
        k = SkeletonKnobs(
            cycles=[Cycle(id="t", name="Titans", span=CycleSpan.MONO5, rarity="rare")]
        )
        r = generate_skeleton(_cfg(277), knobs=k)
        assert [c.id for c in r.cycles] == ["t"]

    def test_oversized_cycle_dropped_with_warning(self):
        # A pairs10 cycle can't fit a tiny set's rarity budget — dropped + warned.
        k = SkeletonKnobs(
            cycles=[Cycle(id="big", name="Big", span=CycleSpan.PAIRS10, rarity="mythic")]
        )
        r = generate_skeleton(_cfg(20), knobs=k)
        assert r.total_slots == 20
        assert r.cycles == []
        assert any("Big" in w for w in r.knob_warnings)

    def test_reserve_cycles_decrements_budget(self):
        counts = _scale_rarity(277)
        members, kept, warnings = _reserve_cycles(
            [Cycle(id="t", name="T", span=CycleSpan.MONO5, rarity="rare")], counts
        )
        assert len(members["rare"]) == 5
        assert kept[0].id == "t"
        assert warnings == []


class TestPlacePlaneswalkers:
    def test_prefers_noncreature_mythic(self):
        from mtgai.skeleton.generator import SkeletonSlot

        slots = [
            SkeletonSlot(
                slot_id="1", color="U", rarity="mythic", card_type="creature", cmc_target=5
            ),
            SkeletonSlot(
                slot_id="2", color="B", rarity="mythic", card_type="sorcery", cmc_target=4
            ),
        ]
        n = _place_planeswalkers(slots, 1)
        assert n == 1
        assert slots[1].card_type == "planeswalker"  # the non-creature one
        assert slots[0].card_type == "creature"

    def test_skips_cycle_members(self):
        from mtgai.skeleton.generator import SkeletonSlot

        slots = [
            SkeletonSlot(
                slot_id="1",
                color="U",
                rarity="mythic",
                card_type="sorcery",
                cmc_target=5,
                cycle_id="c",
            ),
        ]
        assert _place_planeswalkers(slots, 1) == 0
        assert slots[0].card_type == "sorcery"

    def test_zero_is_noop(self):
        from mtgai.skeleton.generator import SkeletonSlot

        slots = [
            SkeletonSlot(
                slot_id="1", color="U", rarity="mythic", card_type="creature", cmc_target=5
            )
        ]
        assert _place_planeswalkers(slots, 0) == 0


def test_skeleton_result_round_trips_knobs_and_cycles(tmp_path):
    from mtgai.skeleton.generator import SkeletonResult, save_skeleton

    k = SkeletonKnobs(
        multicolor_rare=0.40,
        cycles=[Cycle(id="t", name="Titans", span=CycleSpan.MONO5, rarity="rare")],
    )
    r = generate_skeleton(_cfg(277), knobs=k)
    json_path, _ = save_skeleton(r, tmp_path)
    restored = SkeletonResult.model_validate_json(json_path.read_text(encoding="utf-8"))
    assert restored.knobs.multicolor_rare == 0.40
    assert [c.id for c in restored.cycles] == ["t"]
    assert any(s.cycle_id == "t" for s in restored.slots)
