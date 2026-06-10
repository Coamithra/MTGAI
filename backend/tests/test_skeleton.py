"""Tests for the skeleton generator (Phase 1A-8).

Covers model construction, constraint validation, skeleton generation at
multiple set sizes, balance reporting, and save/load round-tripping.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from mtgai.skeleton import (
    SetConfig,
    SkeletonResult,
    SkeletonSlot,
    generate_skeleton,
    save_skeleton,
)
from mtgai.skeleton.generator import (
    COLOR_PAIRS,
    COLORS,
    MechanicTag,
    ReservedSlotSpec,
    SlotCardType,
    _apply_reservations,
    _assign_cmcs,
    _assign_mechanic_tags,
    _check_color_balance,
    _check_creature_density,
    _check_rarity_totals,
    _check_signpost_uncommons,
    _distribute_colors,
    _mark_signpost_slots,
    _scale_rarity,
    _split_request,
    _top_up_creature_density,
    build_reserved_slots,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(set_size: int = 60, **kwargs) -> SetConfig:
    """Build a minimal SetConfig for testing."""
    defaults = {
        "name": "Test Set",
        "code": "TST",
        "theme": "Testing",
        "flavor_description": "A test set for unit tests.",
        "set_size": set_size,
    }
    defaults.update(kwargs)
    return SetConfig(**defaults)


def _generate(set_size: int = 60) -> SkeletonResult:
    """Convenience wrapper: generate a skeleton at the given size."""
    return generate_skeleton(_make_config(set_size))


# ---------------------------------------------------------------------------
# 1. Model tests — SetConfig & SkeletonSlot
# ---------------------------------------------------------------------------


class TestSetConfig:
    """Verify SetConfig defaults and custom construction."""

    def test_default_set_size(self):
        cfg = SetConfig(
            name="A",
            code="AAA",
            theme="t",
            flavor_description="d",
        )
        assert cfg.set_size == 60

    def test_default_mechanic_count(self):
        cfg = _make_config()
        assert cfg.mechanic_count == 3

    def test_default_special_constraints(self):
        cfg = _make_config()
        assert cfg.special_constraints == []

    def test_custom_values(self):
        cfg = _make_config(
            set_size=200,
            mechanic_count=5,
            special_constraints=["no_flying", "extra_artifacts"],
        )
        assert cfg.set_size == 200
        assert cfg.mechanic_count == 5
        assert len(cfg.special_constraints) == 2


class TestSkeletonSlot:
    """Verify SkeletonSlot field defaults and construction."""

    def test_minimal_creation(self):
        slot = SkeletonSlot(
            slot_id="W-C-01",
            color="W",
            rarity="common",
            card_type="creature",
            cmc_target=2,
        )
        assert slot.slot_id == "W-C-01"
        assert slot.archetype_tags == []
        assert slot.mechanic_tag == MechanicTag.EVERGREEN
        assert slot.is_reprint_slot is False
        assert slot.card_id is None
        assert slot.notes == ""
        assert slot.color_pair is None

    def test_multicolor_slot(self):
        slot = SkeletonSlot(
            slot_id="UB-U-01",
            color="multicolor",
            rarity="uncommon",
            card_type="creature",
            cmc_target=3,
            color_pair="UB",
            archetype_tags=["UB"],
        )
        assert slot.color_pair == "UB"
        assert slot.archetype_tags == ["UB"]


# ---------------------------------------------------------------------------
# 2. Constraint validator tests (unit-level)
# ---------------------------------------------------------------------------


def _build_slots_with_color_counts(
    rarity: str,
    per_color: dict[str, int],
) -> list[SkeletonSlot]:
    """Helper: create stub slots with given per-color counts at a rarity."""
    slots: list[SkeletonSlot] = []
    for color, n in per_color.items():
        for i in range(n):
            slots.append(
                SkeletonSlot(
                    slot_id=f"{color}-{rarity[0].upper()}-{i + 1:02d}",
                    color=color,
                    rarity=rarity,
                    card_type="creature",
                    cmc_target=3,
                )
            )
    return slots


class TestColorBalanceConstraint:
    """_check_color_balance: equal commons (±0), other rarities (±1)."""

    def test_perfect_common_balance_passes(self):
        slots = _build_slots_with_color_counts("common", {c: 4 for c in COLORS})
        results = _check_color_balance(slots)
        common_result = [r for r in results if r.name == "color_balance_common"]
        assert len(common_result) == 1
        assert common_result[0].passed is True

    def test_unequal_common_balance_fails(self):
        counts = {c: 4 for c in COLORS}
        counts["W"] = 5  # one extra white
        slots = _build_slots_with_color_counts("common", counts)
        results = _check_color_balance(slots)
        common_result = [r for r in results if r.name == "color_balance_common"]
        assert common_result[0].passed is False

    def test_uncommon_within_one_passes(self):
        counts = {"W": 4, "U": 5, "B": 4, "R": 5, "G": 4}
        slots = _build_slots_with_color_counts("uncommon", counts)
        results = _check_color_balance(slots)
        unc_result = [r for r in results if r.name == "color_balance_uncommon"]
        assert unc_result[0].passed is True

    def test_uncommon_spread_of_two_fails(self):
        counts = {"W": 3, "U": 5, "B": 4, "R": 5, "G": 4}
        slots = _build_slots_with_color_counts("uncommon", counts)
        results = _check_color_balance(slots)
        unc_result = [r for r in results if r.name == "color_balance_uncommon"]
        assert unc_result[0].passed is False

    def test_all_constraint_results_are_hard(self):
        slots = _build_slots_with_color_counts("rare", {c: 2 for c in COLORS})
        results = _check_color_balance(slots)
        assert all(r.is_hard for r in results)


class TestCreatureDensityConstraint:
    """_check_creature_density: overall ≥50%, per-color common ≥40%."""

    def test_overall_50pct_passes(self):
        slots = [
            SkeletonSlot(
                slot_id=f"W-C-{i:02d}",
                color="W",
                rarity="common",
                card_type="creature" if i <= 5 else "instant",
                cmc_target=2,
            )
            for i in range(1, 11)
        ]
        results = _check_creature_density(slots)
        overall = [r for r in results if r.name == "overall_creature_density"]
        assert overall[0].passed is True  # 5/10 = 50%

    def test_overall_below_50pct_fails(self):
        slots = [
            SkeletonSlot(
                slot_id=f"W-C-{i:02d}",
                color="W",
                rarity="common",
                card_type="creature" if i <= 4 else "instant",
                cmc_target=2,
            )
            for i in range(1, 11)
        ]
        results = _check_creature_density(slots)
        overall = [r for r in results if r.name == "overall_creature_density"]
        assert overall[0].passed is False  # 4/10 = 40%

    def test_per_color_common_40pct_passes(self):
        # 2 creatures + 3 non-creatures = 40%
        slots = []
        for i in range(1, 6):
            slots.append(
                SkeletonSlot(
                    slot_id=f"R-C-{i:02d}",
                    color="R",
                    rarity="common",
                    card_type="creature" if i <= 2 else "sorcery",
                    cmc_target=2,
                )
            )
        results = _check_creature_density(slots)
        red_common = [r for r in results if r.name == "creature_density_R_common"]
        assert red_common[0].passed is True

    def test_per_color_common_below_40pct_fails(self):
        # 1 creature + 4 non-creatures = 20%
        slots = []
        for i in range(1, 6):
            slots.append(
                SkeletonSlot(
                    slot_id=f"G-C-{i:02d}",
                    color="G",
                    rarity="common",
                    card_type="creature" if i <= 1 else "enchantment",
                    cmc_target=2,
                )
            )
        results = _check_creature_density(slots)
        green_common = [r for r in results if r.name == "creature_density_G_common"]
        assert green_common[0].passed is False


class TestSignpostUncommons:
    """_check_signpost_uncommons: multi-color uncommons count."""

    def test_small_set_needs_5(self):
        slots = [
            SkeletonSlot(
                slot_id=f"{COLOR_PAIRS[i]}-U-01",
                color="multicolor",
                rarity="uncommon",
                card_type="creature",
                cmc_target=3,
                color_pair=COLOR_PAIRS[i],
            )
            for i in range(5)
        ]
        result = _check_signpost_uncommons(slots, set_size=60)
        assert result.passed is True

    def test_small_set_under_5_fails(self):
        slots = [
            SkeletonSlot(
                slot_id="WU-U-01",
                color="multicolor",
                rarity="uncommon",
                card_type="creature",
                cmc_target=3,
                color_pair="WU",
            )
        ] * 4
        result = _check_signpost_uncommons(slots, set_size=60)
        assert result.passed is False

    def test_large_set_needs_10(self):
        slots = [
            SkeletonSlot(
                slot_id=f"{COLOR_PAIRS[i]}-U-01",
                color="multicolor",
                rarity="uncommon",
                card_type="creature",
                cmc_target=3,
                color_pair=COLOR_PAIRS[i],
            )
            for i in range(10)
        ]
        result = _check_signpost_uncommons(slots, set_size=280)
        assert result.passed is True


class TestSignpostMarking:
    """_mark_signpost_slots: one multicolor uncommon per pair flagged."""

    def _multi_uncommons(self, pairs: list[str], per_pair: int = 1) -> list[SkeletonSlot]:
        slots: list[SkeletonSlot] = []
        for pair in pairs:
            for n in range(per_pair):
                slots.append(
                    SkeletonSlot(
                        slot_id=f"{pair}-U-{n:02d}",
                        color="multicolor",
                        rarity="uncommon",
                        card_type="creature",
                        cmc_target=3,
                        color_pair=pair,
                    )
                )
        return slots

    def test_marks_one_per_pair(self):
        # Two multicolor uncommons per pair — only the first of each is flagged.
        slots = self._multi_uncommons(COLOR_PAIRS, per_pair=2)
        marked = _mark_signpost_slots(slots)
        assert marked == 10
        flagged = [s for s in slots if s.signpost_for]
        assert len(flagged) == 10
        assert {s.signpost_for for s in flagged} == set(COLOR_PAIRS)
        # Each flagged slot points at its own pair, and only the first per pair.
        for s in flagged:
            assert s.signpost_for == s.color_pair
            assert s.slot_id.endswith("-00")

    def test_caps_at_available_slots_dev_size(self):
        # Dev-size skeletons only have ~5 multicolor uncommons — only those pairs
        # get a signpost; the rest simply go uncovered (matches the learning).
        slots = self._multi_uncommons(COLOR_PAIRS[:5])
        marked = _mark_signpost_slots(slots)
        assert marked == 5
        assert {s.signpost_for for s in slots if s.signpost_for} == set(COLOR_PAIRS[:5])

    def test_ignores_non_signpost_slots(self):
        # Commons, rares, and mono-color slots are never signposts.
        slots = [
            SkeletonSlot(
                slot_id="WU-C",
                color="multicolor",
                rarity="common",
                card_type="creature",
                cmc_target=2,
                color_pair="WU",
            ),
            SkeletonSlot(
                slot_id="WU-R",
                color="multicolor",
                rarity="rare",
                card_type="creature",
                cmc_target=4,
                color_pair="WU",
            ),
            SkeletonSlot(
                slot_id="W-U", color="W", rarity="uncommon", card_type="creature", cmc_target=2
            ),
        ]
        assert _mark_signpost_slots(slots) == 0
        assert all(s.signpost_for is None for s in slots)

    def test_generate_skeleton_flags_signposts(self):
        # End-to-end: a generated dev-size skeleton flags exactly its
        # multicolor-uncommon count, one per distinct pair.
        result = generate_skeleton(_make_config(60))
        flagged = [s for s in result.slots if s.signpost_for]
        multi_unc = [s for s in result.slots if s.color == "multicolor" and s.rarity == "uncommon"]
        assert 0 < len(flagged) <= len(multi_unc)
        # One signpost per pair — no pair flagged twice.
        pairs = [s.signpost_for for s in flagged]
        assert len(pairs) == len(set(pairs))
        assert all(s.signpost_for == s.color_pair for s in flagged)

    def test_signposts_per_pair_zero_flags_none(self):
        # spp=0 opts the set out of gold signposts: none flagged, and the hard
        # multicolor-uncommon floor is lifted so the skeleton still validates.
        from mtgai.skeleton.knobs import SkeletonKnobs

        result = generate_skeleton(_make_config(277), knobs=SkeletonKnobs(signposts_per_pair=0))
        assert [s for s in result.slots if s.signpost_for] == []
        sp = next(c for c in result.balance_report.constraints if c.name == "signpost_uncommons")
        assert sp.passed is True

    def test_signposts_per_pair_two_flags_two_per_pair(self):
        # spp=2 flags two signposts per pair (20 at full size).
        from collections import Counter

        from mtgai.skeleton.knobs import SkeletonKnobs

        result = generate_skeleton(_make_config(277), knobs=SkeletonKnobs(signposts_per_pair=2))
        per_pair = Counter(s.signpost_for for s in result.slots if s.signpost_for)
        assert sum(per_pair.values()) == 20
        assert all(n == 2 for n in per_pair.values())


class TestRarityTotalsConstraint:
    """_check_rarity_totals: len(slots) == set_size."""

    def test_exact_count_passes(self):
        slots = [
            SkeletonSlot(
                slot_id=f"W-C-{i:02d}",
                color="W",
                rarity="common",
                card_type="creature",
                cmc_target=2,
            )
            for i in range(1, 11)
        ]
        result = _check_rarity_totals(slots, set_size=10)
        assert result.passed is True

    def test_wrong_count_fails(self):
        slots = [
            SkeletonSlot(
                slot_id="W-C-01",
                color="W",
                rarity="common",
                card_type="creature",
                cmc_target=2,
            )
        ]
        result = _check_rarity_totals(slots, set_size=5)
        assert result.passed is False


# ---------------------------------------------------------------------------
# 3. Internal helper tests
# ---------------------------------------------------------------------------


class TestScaleRarity:
    """_scale_rarity produces counts that sum to the requested set_size."""

    @pytest.mark.parametrize("size", [20, 60, 100, 200, 277, 300])
    def test_total_equals_set_size(self, size: int):
        counts = _scale_rarity(size)
        assert sum(counts.values()) == size

    def test_mythic_clamped_minimum(self):
        counts = _scale_rarity(20)
        assert counts["mythic"] >= 4

    def test_mythic_clamped_maximum(self):
        counts = _scale_rarity(300)
        assert counts["mythic"] <= 25

    def test_all_rarities_present(self):
        counts = _scale_rarity(60)
        assert set(counts.keys()) == {"common", "uncommon", "rare", "mythic"}


class TestDistributeColors:
    """_distribute_colors returns the correct number of assignments."""

    @pytest.mark.parametrize(
        "rarity,count,set_size",
        [
            ("common", 20, 60),
            ("uncommon", 21, 60),
            ("rare", 14, 60),
            ("mythic", 5, 60),
            ("common", 95, 277),
            ("uncommon", 98, 277),
        ],
    )
    def test_output_count_matches_input(self, rarity, count, set_size):
        slots = _distribute_colors(rarity, count, set_size)
        assert len(slots) == count

    def test_small_set_no_multicolor_commons(self):
        slots = _distribute_colors("common", 20, 60)
        multi = [s for s in slots if s["color"] == "multicolor"]
        assert len(multi) == 0


class TestAssignCmcs:
    """_assign_cmcs returns the right count and reasonable values."""

    @pytest.mark.parametrize("size", [1, 5, 20, 95])
    def test_output_length(self, size: int):
        cmcs = _assign_cmcs(size, "common")
        assert len(cmcs) == size

    def test_values_in_range(self):
        cmcs = _assign_cmcs(50, "common")
        assert all(1 <= c <= 7 for c in cmcs)

    def test_mythic_skews_higher(self):
        common_cmcs = _assign_cmcs(100, "common")
        mythic_cmcs = _assign_cmcs(100, "mythic")
        avg_common = sum(common_cmcs) / len(common_cmcs)
        avg_mythic = sum(mythic_cmcs) / len(mythic_cmcs)
        assert avg_mythic > avg_common


class TestAssignMechanicTags:
    """_assign_mechanic_tags assigns valid, type-aware MechanicTag values."""

    @staticmethod
    def _blocks(creatures: int, others: int = 0) -> dict[str, list[str]]:
        """One block with `creatures` creature slots followed by `others` spells."""
        return {"W": ["creature"] * creatures + ["instant"] * others}

    def test_output_index_aligned(self):
        block_types = self._blocks(15, 5)
        tags = _assign_mechanic_tags(block_types, "common")
        assert set(tags) == set(block_types)
        assert len(tags["W"]) == 20

    def test_all_tags_are_valid(self):
        valid = {e.value for e in MechanicTag}
        for rarity in ["common", "uncommon", "rare", "mythic"]:
            tags = _assign_mechanic_tags(self._blocks(10, 5), rarity)
            assert all(t in valid for t in tags["W"])

    def test_commons_have_vanilla_with_enough_creatures(self):
        # ~4% of 50 creatures -> 2 vanilla.
        tags = _assign_mechanic_tags(self._blocks(50), "common")
        assert MechanicTag.VANILLA in tags["W"]

    def test_rares_have_no_vanilla(self):
        tags = _assign_mechanic_tags(self._blocks(30), "rare")
        assert MechanicTag.VANILLA not in tags["W"]

    def test_vanilla_and_french_only_on_creatures(self):
        # Creatures first, then a colorless artifact-only block — neither vanilla nor
        # french_vanilla may ever land on a non-creature slot ("vanilla artifact").
        block_types: dict[str, list[str]] = {
            "W": ["creature"] * 40,
            "colorless": ["artifact"] * 8,
        }
        tags = _assign_mechanic_tags(block_types, "common")
        creature_tier = {MechanicTag.VANILLA, MechanicTag.FRENCH_VANILLA}
        for bk, types in block_types.items():
            for i, t in enumerate(types):
                if t != "creature":
                    assert tags[bk][i] not in creature_tier, (
                        f"{tags[bk][i]} landed on non-creature {bk}[{i}]"
                    )

    def test_vanilla_share_is_low(self):
        # Realistic density: true vanilla stays a tiny fraction of creatures
        # (recent sets ~1%), nothing like the historical 15%.
        tags = _assign_mechanic_tags(self._blocks(50), "common")
        n_vanilla = tags["W"].count(MechanicTag.VANILLA)
        assert 0 < n_vanilla <= 4


# ---------------------------------------------------------------------------
# 4. Skeleton generation integration tests
# ---------------------------------------------------------------------------


class TestSkeletonGeneration:
    """Full generate_skeleton() integration tests at various sizes."""

    def test_skeleton_60_cards_all_hard_constraints_pass(self):
        result = _generate(60)
        assert result.total_slots == 60
        assert result.balance_report.all_hard_passed is True

    def test_skeleton_100_cards_all_hard_constraints_pass(self):
        result = _generate(100)
        assert result.total_slots == 100
        assert result.balance_report.all_hard_passed is True

    def test_skeleton_280_cards_all_hard_constraints_pass(self):
        result = _generate(280)
        assert result.total_slots == 280
        assert result.balance_report.all_hard_passed is True

    def test_every_slot_has_required_fields(self):
        result = _generate(60)
        for slot in result.slots:
            assert slot.slot_id
            assert slot.color
            assert slot.rarity
            assert slot.card_type
            assert isinstance(slot.cmc_target, int)

    def test_slot_id_format(self):
        """Slot IDs are plain zero-padded collector numbers, and unique."""
        result = _generate(60)
        pattern = re.compile(r"^\d{3,}$")  # zero-padded to >= 3 digits, digits only
        seen: set[str] = set()
        for slot in result.slots:
            assert pattern.match(slot.slot_id), f"Bad slot_id: {slot.slot_id}"
            assert slot.slot_id not in seen, f"Duplicate slot_id: {slot.slot_id}"
            seen.add(slot.slot_id)

    def test_cmc_targets_in_range(self):
        result = _generate(100)
        for slot in result.slots:
            assert 1 <= slot.cmc_target <= 7, (
                f"CMC {slot.cmc_target} out of range for {slot.slot_id}"
            )

    def test_mechanic_tags_are_valid_enum_values(self):
        valid = {e.value for e in MechanicTag}
        result = _generate(60)
        for slot in result.slots:
            assert slot.mechanic_tag in valid, (
                f"Invalid mechanic_tag '{slot.mechanic_tag}' on {slot.slot_id}"
            )

    def test_card_types_are_valid(self):
        valid = {e.value for e in SlotCardType}
        result = _generate(60)
        for slot in result.slots:
            assert slot.card_type in valid, (
                f"Invalid card_type '{slot.card_type}' on {slot.slot_id}"
            )

    def test_rarities_are_valid(self):
        valid_rarities = {"common", "uncommon", "rare", "mythic"}
        result = _generate(60)
        for slot in result.slots:
            assert slot.rarity in valid_rarities

    def test_colors_are_valid(self):
        valid_colors = set(COLORS) | {"multicolor", "colorless"}
        result = _generate(60)
        for slot in result.slots:
            assert slot.color in valid_colors

    def test_multicolor_slots_have_color_pair(self):
        result = _generate(100)
        for slot in result.slots:
            if slot.color == "multicolor":
                assert slot.color_pair in COLOR_PAIRS, (
                    f"multicolor slot {slot.slot_id} missing valid color_pair"
                )

    def test_archetype_slots_populated(self):
        result = _generate(100)
        # At least some archetypes should have associated slots
        total_arch_slots = sum(len(v) for v in result.archetype_slots.values())
        assert total_arch_slots > 0

    def test_all_color_pairs_have_archetype_entries(self):
        result = _generate(100)
        for pair in COLOR_PAIRS:
            assert pair in result.archetype_slots


class TestTinySetCreatureDensity:
    """Tiny sets must still clear the set-wide 50% creature-density floor.

    On a very small set a rarity block can be too small to spread mono colors
    (a 4-slot common collapses to all-colorless artifacts → 0 creatures), and the
    per-rarity pooled allocator can't compensate cross-rarity. The post-build
    cross-rarity top-up (:func:`_top_up_creature_density`) rescues the floor.
    """

    @pytest.mark.parametrize("size", [15, 18, 20])
    def test_tiny_set_meets_density_floor(self, size: int):
        result = _generate(size)
        overall = next(
            c for c in result.balance_report.constraints if c.name == "overall_creature_density"
        )
        assert overall.passed is True, f"size={size}: {overall.message}"

    def test_top_up_only_changes_card_type(self):
        # The top-up touches only card_type — every other field (color, rarity)
        # and the colorless count are unchanged.
        result = _generate(20)
        before = {s.slot_id: (s.color, s.rarity) for s in result.slots}
        before_colorless = sum(1 for s in result.slots if s.color == "colorless")
        _top_up_creature_density(result.slots)  # idempotent — already topped up at gen
        assert {s.slot_id: (s.color, s.rarity) for s in result.slots} == before
        assert sum(1 for s in result.slots if s.color == "colorless") == before_colorless
        assert not [c for c in _check_color_balance(result.slots) if not c.passed]

    def test_top_up_is_noop_above_floor(self):
        # A balanced set already above the floor is left untouched.
        result = _generate(60)
        before = sum(1 for s in result.slots if s.card_type == SlotCardType.CREATURE)
        flipped = _top_up_creature_density(result.slots)
        after = sum(1 for s in result.slots if s.card_type == SlotCardType.CREATURE)
        assert flipped == 0
        assert after == before

    def test_top_up_skips_colorless_and_special_slots(self):
        # Below-floor pool of colorless artifacts + colored spells: the top-up
        # flips colored spells to creatures but never the colorless slots or a
        # signpost/cycle slot. With 6 non-land slots and 0 creatures the deficit is
        # ceil(6 * 0.5) = 3, but only 2 eligible (non-special) colored spells exist,
        # so it flips exactly 2 (the deficit-exceeds-pool best-effort branch).
        slots = [
            SkeletonSlot(
                slot_id=f"CL-{i:02d}",
                color="colorless",
                rarity="common",
                card_type="artifact",
                cmc_target=2,
            )
            for i in range(3)
        ] + [
            SkeletonSlot(
                slot_id="WU-U",
                color="multicolor",
                rarity="uncommon",
                card_type="instant",
                cmc_target=3,
                color_pair="WU",
                signpost_for="WU",
            ),
            SkeletonSlot(
                slot_id="WG-C",
                color="multicolor",
                rarity="common",
                card_type="enchantment",
                cmc_target=2,
                color_pair="WG",
                cycle_id="cyc1",
            ),
            SkeletonSlot(
                slot_id="W-C-1", color="W", rarity="common", card_type="instant", cmc_target=2
            ),
            SkeletonSlot(
                slot_id="U-C-1", color="U", rarity="common", card_type="sorcery", cmc_target=2
            ),
        ]
        flipped = _top_up_creature_density(slots)
        assert flipped == 2  # deficit 3, but only 2 eligible candidates
        by_id = {s.slot_id: s for s in slots}
        assert all(by_id[f"CL-{i:02d}"].card_type == "artifact" for i in range(3))
        assert by_id["WU-U"].card_type == "instant"  # signpost untouched
        assert by_id["WG-C"].card_type == "enchantment"  # cycle member untouched
        assert by_id["W-C-1"].card_type == "creature"  # ordinary spells flipped
        assert by_id["U-C-1"].card_type == "creature"

    def test_top_up_flips_lowest_rarity_first(self):
        # The deficit-sized flip prefers lower rarities (creatures are densest at
        # common in a real set). One creature short with both a common and a rare
        # spell eligible → the common flips, the rare is left.
        slots = [
            SkeletonSlot(
                slot_id="W-C", color="W", rarity="common", card_type="creature", cmc_target=2
            ),
            SkeletonSlot(
                slot_id="U-C", color="U", rarity="common", card_type="instant", cmc_target=2
            ),
            SkeletonSlot(
                slot_id="B-R", color="B", rarity="rare", card_type="sorcery", cmc_target=3
            ),
        ]
        # 3 non-land, 1 creature → deficit = ceil(3 * 0.5) - 1 = 1.
        flipped = _top_up_creature_density(slots)
        assert flipped == 1
        by_id = {s.slot_id: s for s in slots}
        assert by_id["U-C"].card_type == "creature"  # common spell flipped
        assert by_id["B-R"].card_type == "sorcery"  # rare spell left


# ---------------------------------------------------------------------------
# 5. Balance report tests
# ---------------------------------------------------------------------------


class TestBalanceReport:
    """Tests for the BalanceReport populated by generate_skeleton."""

    def test_balance_report_is_populated(self):
        result = _generate(60)
        br = result.balance_report
        assert br.rarity_counts
        assert br.color_counts
        assert br.type_counts
        assert br.cmc_distribution

    def test_all_hard_passed_for_default_configs(self):
        for size in [60, 100, 280]:
            result = _generate(size)
            assert result.balance_report.all_hard_passed is True, (
                f"Hard constraints failed for set_size={size}"
            )

    def test_stats_dict_has_expected_keys(self):
        result = _generate(60)
        br = result.balance_report
        assert "common" in br.rarity_counts
        assert "uncommon" in br.rarity_counts
        assert "rare" in br.rarity_counts
        assert "mythic" in br.rarity_counts

    def test_creature_pct_above_50(self):
        result = _generate(60)
        assert result.balance_report.creature_pct >= 50.0

    def test_average_cmc_is_reasonable(self):
        result = _generate(100)
        avg = result.balance_report.average_cmc
        # Should be in a reasonable range (roughly 2-4)
        assert 2.0 <= avg <= 4.5

    def test_constraints_list_not_empty(self):
        result = _generate(60)
        assert len(result.balance_report.constraints) > 0

    def test_rarity_counts_sum_to_total(self):
        result = _generate(60)
        total = sum(result.balance_report.rarity_counts.values())
        assert total == result.total_slots


# ---------------------------------------------------------------------------
# 6. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases: minimum and maximum viable sets."""

    def test_minimum_viable_set_20(self):
        result = _generate(20)
        assert result.total_slots == 20
        # The rarity total constraint must pass
        rarity_check = [c for c in result.balance_report.constraints if c.name == "rarity_total"]
        assert rarity_check[0].passed is True

    def test_large_set_300(self):
        result = _generate(300)
        assert result.total_slots == 300
        rarity_check = [c for c in result.balance_report.constraints if c.name == "rarity_total"]
        assert rarity_check[0].passed is True

    def test_base_set_size_277(self):
        """Base size should produce counts very close to the rarity-weight defaults."""
        result = _generate(277)
        assert result.total_slots == 277

    def test_config_with_special_constraints(self):
        cfg = _make_config(
            set_size=60,
            special_constraints=["tribal_heavy", "artifact_matters"],
        )
        result = generate_skeleton(cfg)
        assert result.total_slots == 60
        assert result.config.special_constraints == [
            "tribal_heavy",
            "artifact_matters",
        ]


# ---------------------------------------------------------------------------
# 7. save_skeleton() round-trip test
# ---------------------------------------------------------------------------


class TestSaveSkeleton:
    """save_skeleton persists JSON + overview and round-trips correctly."""

    def test_save_creates_files(self, tmp_path: Path):
        result = _generate(60)
        json_path, txt_path = save_skeleton(result, tmp_path)
        assert json_path.exists()
        assert txt_path.exists()
        assert json_path.name == "skeleton.json"
        assert txt_path.name == "skeleton-overview.txt"

    def test_json_round_trip(self, tmp_path: Path):
        result = _generate(60)
        json_path, _ = save_skeleton(result, tmp_path)

        loaded = json.loads(json_path.read_text(encoding="utf-8"))

        # Top-level keys
        assert loaded["total_slots"] == result.total_slots
        assert loaded["config"]["set_size"] == 60
        assert len(loaded["slots"]) == result.total_slots

        # Verify a slot round-trips properly
        first_slot = loaded["slots"][0]
        assert "slot_id" in first_slot
        assert "color" in first_slot
        assert "rarity" in first_slot
        assert "card_type" in first_slot
        assert "cmc_target" in first_slot

    def test_overview_contains_set_name(self, tmp_path: Path):
        result = _generate(60)
        _, txt_path = save_skeleton(result, tmp_path)
        overview = txt_path.read_text(encoding="utf-8")
        assert "Test Set" in overview
        assert "TST" in overview

    def test_save_to_nested_directory(self, tmp_path: Path):
        """save_skeleton creates parent directories if needed."""
        nested = tmp_path / "deep" / "nested" / "dir"
        result = _generate(60)
        json_path, txt_path = save_skeleton(result, nested)
        assert json_path.exists()
        assert txt_path.exists()

    def test_pydantic_round_trip(self, tmp_path: Path):
        """Load JSON and reconstruct a SkeletonResult via Pydantic."""
        original = _generate(60)
        json_path, _ = save_skeleton(original, tmp_path)

        raw = json_path.read_text(encoding="utf-8")
        restored = SkeletonResult.model_validate_json(raw)

        assert restored.total_slots == original.total_slots
        assert len(restored.slots) == len(original.slots)
        assert restored.config.set_size == original.config.set_size
        assert restored.balance_report.all_hard_passed == (original.balance_report.all_hard_passed)


# ---------------------------------------------------------------------------
# Provenance-tagged constraints / card_requests (theme.json round-trip)
# ---------------------------------------------------------------------------


class TestSetConfigProvenanceCoercion:
    """SetConfig must accept both bare-string and {text, source} list items."""

    def test_constraints_accept_strings(self):
        cfg = _make_config(constraints=["At least 6 artifacts", "No mill"])
        assert cfg.constraints == ["At least 6 artifacts", "No mill"]

    def test_constraints_accept_provenance_objects(self):
        cfg = _make_config(
            constraints=[
                {"text": "At least 6 artifacts", "source": "ai"},
                {"text": "No mill", "source": "human"},
            ]
        )
        assert cfg.constraints == ["At least 6 artifacts", "No mill"]

    def test_card_requests_accept_provenance_objects(self):
        cfg = _make_config(
            card_requests=[
                {"text": "Feretha's Throne: legendary artifact", "source": "ai"},
            ]
        )
        assert cfg.card_requests == ["Feretha's Throne: legendary artifact"]

    def test_mixed_strings_and_objects(self):
        cfg = _make_config(
            constraints=[
                "Manual constraint",
                {"text": "AI constraint", "source": "ai"},
            ]
        )
        assert cfg.constraints == ["Manual constraint", "AI constraint"]

    def test_special_constraints_legacy_field_also_normalizes(self):
        cfg = _make_config(special_constraints=[{"text": "Legacy with provenance", "source": "ai"}])
        assert cfg.special_constraints == ["Legacy with provenance"]

    def test_unknown_object_keys_ignored(self):
        cfg = _make_config(constraints=[{"text": "Has extras", "source": "ai", "extra": "ignored"}])
        assert cfg.constraints == ["Has extras"]

    def test_object_without_text_dropped(self):
        # An item with no "text" key has nothing to feed downstream — drop it
        # rather than coerce to "" which would be a silent garbage row.
        cfg = _make_config(constraints=[{"source": "ai"}, "Real constraint"])
        assert cfg.constraints == ["Real constraint"]

    def test_blank_items_dropped(self):
        # Whitespace-only text (from either shape) is garbage downstream;
        # the wizard already filters at save, the validator hardens it.
        cfg = _make_config(
            constraints=[
                "",
                "   ",
                {"text": "", "source": "ai"},
                {"text": "  ", "source": "human"},
                "Kept",
            ]
        )
        assert cfg.constraints == ["Kept"]


# ---------------------------------------------------------------------------
# Reserved slots (TC-7)
# ---------------------------------------------------------------------------


def _slot(
    slot_id: str,
    color: str,
    rarity: str,
    card_type: str = "creature",
    color_pair: str | None = None,
    is_reprint_slot: bool = False,
) -> SkeletonSlot:
    return SkeletonSlot(
        slot_id=slot_id,
        color=color,
        rarity=rarity,
        card_type=card_type,
        cmc_target=3,
        color_pair=color_pair,
        is_reprint_slot=is_reprint_slot,
    )


class TestSplitRequest:
    """_split_request peels a name off a prose 'Name — description'."""

    def test_em_dash(self):
        assert _split_request("Feretha — dead wizard-ruler") == (
            "Feretha",
            "dead wizard-ruler",
        )

    def test_colon(self):
        assert _split_request("Stone Head: flying vehicle") == ("Stone Head", "flying vehicle")

    def test_no_separator(self):
        assert _split_request("Just A Name") == ("Just A Name", "")


class TestBuildReservedSlots:
    """build_reserved_slots turns theme.json card_requests into ReservedSlotSpecs.

    card_requests is the single reserved-slot source — the old structured
    legendary_characters / notable_cards anchor fields are gone (nothing ever
    populated them); a legacy theme.json still carrying them must be tolerated
    (ignored), not crash.
    """

    def test_card_requests_prose_strings(self):
        theme = {"card_requests": ["Throne of Glass — a powerful relic"]}
        specs = build_reserved_slots(theme)
        assert len(specs) == 1
        assert specs[0].name == "Throne of Glass"
        assert specs[0].description == "a powerful relic"
        assert specs[0].colors == []
        assert specs[0].rarity is None
        assert specs[0].card_type is None

    def test_card_requests_colon_separator(self):
        theme = {"card_requests": ["Stone Head: flying vehicle"]}
        specs = build_reserved_slots(theme)
        assert specs[0].name == "Stone Head"
        assert specs[0].description == "flying vehicle"

    def test_card_requests_provenance_objects(self):
        theme = {"card_requests": [{"text": "Relic — a thing", "source": "ai"}]}
        specs = build_reserved_slots(theme)
        assert specs[0].name == "Relic"

    def test_dedupes_by_name_case_insensitive(self):
        theme = {"card_requests": ["Feretha — first", "feretha — duplicate prose"]}
        specs = build_reserved_slots(theme)
        # First occurrence of a name wins; the case-insensitive duplicate drops.
        assert len(specs) == 1
        assert specs[0].description == "first"

    def test_legacy_anchor_fields_are_ignored(self):
        # A legacy theme.json may still carry the removed anchor fields; they
        # must be silently ignored (only card_requests produces specs), not
        # crash the loader.
        theme = {
            "legendary_characters": [{"name": "Feretha", "colors": ["U", "B"], "rarity": "mythic"}],
            "notable_cards": [{"name": "Stone Head", "type": "Artifact"}],
            "card_requests": ["Throne of Glass — a relic"],
        }
        specs = build_reserved_slots(theme)
        assert len(specs) == 1
        assert specs[0].name == "Throne of Glass"

    def test_empty_theme_returns_empty(self):
        assert build_reserved_slots({}) == []

    def test_tolerates_malformed_entries(self):
        theme = {"card_requests": ["", "   "]}
        assert build_reserved_slots(theme) == []


class TestApplyReservations:
    """_apply_reservations claims slots best-effort without mutating structure."""

    def test_constrained_spec_matches_color_rarity_type(self):
        slots = [
            _slot("W-C-01", "W", "common"),
            _slot("UB-M-01", "multicolor", "mythic", color_pair="UB"),
            _slot("U-R-01", "U", "rare"),
        ]
        spec = ReservedSlotSpec(
            name="Feretha", colors=["U", "B"], rarity="mythic", card_type="creature"
        )
        unplaced = _apply_reservations(slots, [spec])
        assert unplaced == []
        reserved = [s for s in slots if s.reserved_card]
        assert len(reserved) == 1
        assert reserved[0].slot_id == "UB-M-01"
        assert reserved[0].reserved_card == "Feretha"

    def test_colorless_artifact_lands_on_artifact_slot(self):
        slots = [
            _slot("W-C-01", "W", "common", card_type="creature"),
            _slot("X-R-01", "colorless", "rare", card_type="artifact"),
        ]
        spec = ReservedSlotSpec(name="Stone Head", colors=[], card_type="artifact")
        _apply_reservations(slots, [spec])
        reserved = [s for s in slots if s.reserved_card]
        assert reserved[0].slot_id == "X-R-01"

    def test_name_only_prefers_higher_rarity(self):
        slots = [
            _slot("W-C-01", "W", "common"),
            _slot("U-M-01", "U", "mythic"),
            _slot("B-U-01", "B", "uncommon"),
        ]
        spec = ReservedSlotSpec(name="Mystery Card")
        _apply_reservations(slots, [spec])
        reserved = [s for s in slots if s.reserved_card]
        assert reserved[0].slot_id == "U-M-01"

    def test_skips_reprint_and_land_slots(self):
        slots = [
            _slot("R-R-01", "R", "rare", is_reprint_slot=True),
            _slot("X-C-01", "colorless", "common", card_type="land"),
            _slot("G-C-01", "G", "common"),
        ]
        spec = ReservedSlotSpec(name="Only Option")
        _apply_reservations(slots, [spec])
        reserved = [s for s in slots if s.reserved_card]
        assert len(reserved) == 1
        assert reserved[0].slot_id == "G-C-01"

    def test_two_specs_do_not_collide(self):
        slots = [
            _slot("U-M-01", "U", "mythic"),
            _slot("B-M-02", "B", "mythic"),
        ]
        specs = [ReservedSlotSpec(name="A"), ReservedSlotSpec(name="B")]
        _apply_reservations(slots, specs)
        reserved_names = {s.reserved_card for s in slots if s.reserved_card}
        assert reserved_names == {"A", "B"}

    def test_more_specs_than_slots_returns_unplaced(self):
        slots = [_slot("W-C-01", "W", "common")]
        specs = [ReservedSlotSpec(name="A"), ReservedSlotSpec(name="B")]
        unplaced = _apply_reservations(slots, specs)
        assert len(unplaced) == 1
        assert sum(1 for s in slots if s.reserved_card) == 1

    def test_planeswalker_request_unplaced_when_no_pw_slot(self):
        # The skeleton matrix has no planeswalker slots; a PW request must go
        # unplaced rather than land on a contradictory creature slot.
        slots = [_slot("U-M-01", "U", "mythic", card_type="creature")]
        spec = ReservedSlotSpec(name="Jace", card_type="planeswalker")
        unplaced = _apply_reservations(slots, [spec])
        assert unplaced == [spec]
        assert all(s.reserved_card is None for s in slots)

    def test_land_request_unplaced(self):
        slots = [_slot("G-C-01", "G", "common", card_type="creature")]
        spec = ReservedSlotSpec(name="Some Land", card_type="land")
        unplaced = _apply_reservations(slots, [spec])
        assert unplaced == [spec]
        assert all(s.reserved_card is None for s in slots)

    def test_empty_is_noop(self):
        slots = [_slot("W-C-01", "W", "common")]
        assert _apply_reservations(slots, []) == []
        assert slots[0].reserved_card is None


class TestReservedSlotsIntegration:
    """generate_skeleton honors reserved_slots without breaking the matrix."""

    def test_reservations_preserve_total_and_constraints(self):
        theme = {
            "legendary_characters": [
                {
                    "name": "Feretha",
                    "colors": ["U", "B"],
                    "rarity": "mythic",
                    "type": "Legendary Creature — Wizard",
                }
            ],
            "card_requests": ["Throne — a relic", "Beacon — a light"],
        }
        reserved = build_reserved_slots(theme)
        result = generate_skeleton(_make_config(60), reserved_slots=reserved)
        assert result.total_slots == 60
        assert result.balance_report.all_hard_passed is True
        stamped = [s for s in result.slots if s.reserved_card]
        assert len(stamped) == len(reserved)

    def test_none_is_noop(self):
        result = generate_skeleton(_make_config(60), reserved_slots=None)
        assert all(s.reserved_card is None for s in result.slots)

    def test_reserved_card_round_trips_through_save(self, tmp_path: Path):
        reserved = [ReservedSlotSpec(name="Pinned Card", rarity="mythic")]
        result = generate_skeleton(_make_config(60), reserved_slots=reserved)
        json_path, txt_path = save_skeleton(result, tmp_path)
        loaded = json.loads(json_path.read_text(encoding="utf-8"))
        stamped = [s for s in loaded["slots"] if s.get("reserved_card")]
        assert stamped and stamped[0]["reserved_card"] == "Pinned Card"
        assert "Reserved Cards" in txt_path.read_text(encoding="utf-8")
