"""Tests for the fine-grained card-subtype overlay (skeleton-detail card).

Covers `_assign_subtypes` eligibility, the seeded/jittered randomization, the
irregular bucket, and the `render_slot_string` subtype label. The new subtype
knobs' defaults/clamping ride on the existing drift guard in test_skeleton_knobs.py.
"""

from __future__ import annotations

from collections import Counter

from mtgai.skeleton.generator import (
    IRREGULAR_SUBTYPES,
    SetConfig,
    SkeletonSlot,
    SlotCardSubtype,
    _assign_subtypes,
    generate_skeleton,
    render_slot_string,
    subtype_label,
)
from mtgai.skeleton.knobs import SkeletonKnobs, default_knobs

_IRREGULAR = {s.subtype for s in IRREGULAR_SUBTYPES}


def _cfg(size: int = 277) -> SetConfig:
    return SetConfig(name="Test", code="TST", set_size=size)


def _knobs(**overrides) -> SkeletonKnobs:
    return SkeletonKnobs(**{**default_knobs().model_dump(), **overrides})


def _subtypes(result) -> Counter:
    return Counter(s.card_subtype for s in result.slots if s.card_subtype)


# ---------------------------------------------------------------------------
# Integration through generate_skeleton
# ---------------------------------------------------------------------------


class TestGenerateWithSubtypes:
    def test_default_knobs_label_some_slots(self):
        res = generate_skeleton(_cfg(), default_knobs())
        labelled = [s for s in res.slots if s.card_subtype]
        assert labelled, "expected some slots to receive a subtype"

    def test_subtypes_do_not_change_coarse_type_counts(self):
        """The overlay must not disturb any card_type/color/rarity count."""
        knobs = default_knobs()
        with_sub = Counter(s.card_type for s in generate_skeleton(_cfg(), knobs).slots)
        # Re-run with all subtype counts zeroed → identical coarse distribution.
        bare = _knobs(
            equipment_count=0,
            vehicle_count=0,
            aura_count=0,
            artifact_creature_count=0,
            irregular_subtype_count=0,
        )
        without = Counter(s.card_type for s in generate_skeleton(_cfg(), bare).slots)
        assert with_sub == without

    def test_zeroed_counts_produce_no_subtypes(self):
        bare = _knobs(
            equipment_count=0,
            vehicle_count=0,
            aura_count=0,
            artifact_creature_count=0,
            irregular_subtype_count=0,
        )
        assert not _subtypes(generate_skeleton(_cfg(), bare))

    def test_same_seed_is_deterministic(self):
        a = generate_skeleton(_cfg(), default_knobs())
        b = generate_skeleton(_cfg(), default_knobs())
        fa = [(s.slot_id, s.card_subtype) for s in a.slots if s.card_subtype]
        fb = [(s.slot_id, s.card_subtype) for s in b.slots if s.card_subtype]
        assert fa and fa == fb

    def test_different_seed_reshuffles(self):
        a = generate_skeleton(_cfg(), default_knobs())
        c = generate_skeleton(_cfg(), _knobs(subtype_seed=7))
        fa = {(s.slot_id, s.card_subtype) for s in a.slots if s.card_subtype}
        fc = {(s.slot_id, s.card_subtype) for s in c.slots if s.card_subtype}
        assert fa and fc and fa != fc

    def test_seed_depends_only_on_code_and_seed_not_object_identity(self):
        """Re-run stability rests on a raw-string RNG seed (not `hash()`, which is
        per-process salted): two freshly-built identical slot lists must agree."""
        knobs = _knobs(subtype_jitter=0.0)
        out = []
        for _ in range(2):
            slots = [_slot(f"a{i}", "colorless", "artifact") for i in range(20)]
            slots += [_slot(f"e{i}", "B", "enchantment") for i in range(20)]
            _assign_subtypes(slots, knobs, set_size=277, set_code="TST")
            out.append([(s.slot_id, s.card_subtype) for s in slots if s.card_subtype])
        assert out[0] and out[0] == out[1]


# ---------------------------------------------------------------------------
# Eligibility — _assign_subtypes directly on a hand-built slot list
# ---------------------------------------------------------------------------


def _slot(sid: str, color: str, card_type: str, rarity: str = "common", **kw) -> SkeletonSlot:
    return SkeletonSlot(
        slot_id=sid, color=color, rarity=rarity, card_type=card_type, cmc_target=2, **kw
    )


class TestEligibility:
    def test_equipment_only_on_colorless_artifacts(self):
        slots = [_slot(f"a{i}", "colorless", "artifact") for i in range(10)]
        slots += [_slot(f"w{i}", "W", "artifact") for i in range(10)]  # colored artifacts
        knobs = _knobs(
            equipment_count=5,
            vehicle_count=0,
            aura_count=0,
            artifact_creature_count=0,
            irregular_subtype_count=0,
            subtype_jitter=0.0,
        )
        _assign_subtypes(slots, knobs, set_size=277, set_code="TST")
        equip = [s for s in slots if s.card_subtype == SlotCardSubtype.EQUIPMENT]
        assert len(equip) == 5
        assert all(s.color == "colorless" for s in equip)

    def test_aura_only_on_colored_enchantments(self):
        slots = [_slot(f"w{i}", "W", "enchantment") for i in range(10)]
        knobs = _knobs(
            equipment_count=0,
            vehicle_count=0,
            aura_count=4,
            artifact_creature_count=0,
            irregular_subtype_count=0,
            subtype_jitter=0.0,
        )
        _assign_subtypes(slots, knobs, set_size=277, set_code="TST")
        auras = [s for s in slots if s.card_subtype == SlotCardSubtype.AURA]
        assert len(auras) == 4
        assert all(s.card_type == "enchantment" and s.color != "colorless" for s in auras)

    def test_jitter_zero_hits_exact_count(self):
        slots = [_slot(f"c{i}", "G", "creature") for i in range(40)]
        knobs = _knobs(
            equipment_count=0,
            vehicle_count=0,
            aura_count=0,
            artifact_creature_count=6,
            irregular_subtype_count=0,
            subtype_jitter=0.0,
        )
        _assign_subtypes(slots, knobs, set_size=277, set_code="TST")
        ac = [s for s in slots if s.card_subtype == SlotCardSubtype.ARTIFACT_CREATURE]
        assert len(ac) == 6

    def test_capped_at_available_slots(self):
        slots = [_slot(f"a{i}", "colorless", "artifact") for i in range(3)]
        knobs = _knobs(
            equipment_count=20,  # asks for far more than 3 available
            vehicle_count=0,
            aura_count=0,
            artifact_creature_count=0,
            irregular_subtype_count=0,
            subtype_jitter=0.0,
        )
        _assign_subtypes(slots, knobs, set_size=277, set_code="TST")
        equip = [s for s in slots if s.card_subtype == SlotCardSubtype.EQUIPMENT]
        assert len(equip) == 3

    def test_special_slots_are_never_labelled(self):
        slots = [
            _slot("cy", "colorless", "artifact", cycle_id="c1"),
            _slot("rs", "colorless", "artifact", reserved_card="Sol Ring"),
            _slot("sp", "multicolor", "artifact", signpost_for="WU"),
            _slot("pw", "W", "planeswalker"),
            _slot("ld", "colorless", "land"),
        ]
        knobs = _knobs(
            equipment_count=20,
            vehicle_count=20,
            aura_count=20,
            artifact_creature_count=20,
            irregular_subtype_count=3,
            subtype_jitter=0.0,
        )
        _assign_subtypes(slots, knobs, set_size=277, set_code="TST")
        assert all(s.card_subtype is None for s in slots)

    def test_equipment_and_vehicle_share_the_pool_without_overlap(self):
        slots = [_slot(f"a{i}", "colorless", "artifact") for i in range(10)]
        knobs = _knobs(
            equipment_count=4,
            vehicle_count=3,
            aura_count=0,
            artifact_creature_count=0,
            irregular_subtype_count=0,
            subtype_jitter=0.0,
        )
        _assign_subtypes(slots, knobs, set_size=277, set_code="TST")
        labelled = [s for s in slots if s.card_subtype]
        # No double-labelling; counts are exactly 4 + 3.
        assert len(labelled) == 7
        kinds = Counter(s.card_subtype for s in labelled)
        assert kinds[SlotCardSubtype.EQUIPMENT] == 4
        assert kinds[SlotCardSubtype.VEHICLE] == 3


class TestIrregularBucket:
    def test_count_limits_how_many_specials_appear(self):
        # Plenty of colored enchantments + creatures so the bucket isn't slot-starved.
        slots = [_slot(f"e{i}", "B", "enchantment") for i in range(40)]
        slots += [_slot(f"c{i}", "G", "creature") for i in range(40)]
        knobs = _knobs(
            equipment_count=0,
            vehicle_count=0,
            aura_count=0,
            artifact_creature_count=0,
            irregular_subtype_count=2,
            subtype_jitter=0.0,
        )
        _assign_subtypes(slots, knobs, set_size=277, set_code="TST")
        present = {s.card_subtype for s in slots if s.card_subtype}
        assert present <= _IRREGULAR
        assert 0 < len(present) <= 2

    def test_zero_irregular_count_picks_none(self):
        slots = [_slot(f"e{i}", "B", "enchantment") for i in range(40)]
        knobs = _knobs(
            equipment_count=0,
            vehicle_count=0,
            aura_count=0,
            artifact_creature_count=0,
            irregular_subtype_count=0,
            subtype_jitter=0.0,
        )
        _assign_subtypes(slots, knobs, set_size=277, set_code="TST")
        assert all(s.card_subtype not in _IRREGULAR for s in slots)


class TestRenderLabel:
    def test_render_slot_string_shows_subtype_label(self):
        slot = _slot("x", "W", "enchantment", card_subtype="aura").model_dump()
        assert "aura (local enchantment)" in render_slot_string(slot)

    def test_render_slot_string_plain_when_no_subtype(self):
        slot = _slot("x", "W", "enchantment").model_dump()
        out = render_slot_string(slot)
        assert "enchantment" in out and "aura" not in out

    def test_subtype_label_falls_back_to_value(self):
        assert subtype_label("equipment") == "equipment"
        assert subtype_label("artifact_creature") == "artifact creature"
