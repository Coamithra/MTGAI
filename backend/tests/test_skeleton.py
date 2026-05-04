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
    SlotCardType,
    _assign_cmcs,
    _assign_mechanic_tags,
    _check_color_balance,
    _check_creature_density,
    _check_rarity_totals,
    _check_signpost_uncommons,
    _distribute_colors,
    _scale_rarity,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Path to the real set-template.json used by the generator.
TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "research" / "set-template.json"


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
    return generate_skeleton(_make_config(set_size), TEMPLATE_PATH)


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
    """_assign_mechanic_tags returns valid MechanicTag values."""

    def test_output_length(self):
        tags = _assign_mechanic_tags(20, "common")
        assert len(tags) == 20

    def test_all_tags_are_valid(self):
        valid = {e.value for e in MechanicTag}
        for rarity in ["common", "uncommon", "rare", "mythic"]:
            tags = _assign_mechanic_tags(15, rarity)
            assert all(t in valid for t in tags)

    def test_commons_have_vanilla(self):
        tags = _assign_mechanic_tags(30, "common")
        assert MechanicTag.VANILLA in tags

    def test_rares_have_no_vanilla(self):
        tags = _assign_mechanic_tags(30, "rare")
        assert MechanicTag.VANILLA not in tags


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
        """Slot IDs follow <COLOR>-<RARITY_LETTER>-<NN> pattern."""
        result = _generate(60)
        # Pattern: 1-2 letter color code (or X), dash, single capital letter, dash, 2 digits
        pattern = re.compile(r"^[A-Z]{1,2}-[CURM]-\d{2}$")
        for slot in result.slots:
            assert pattern.match(slot.slot_id), f"Bad slot_id: {slot.slot_id}"

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
        """Base size should produce counts very close to BASE_RARITY_COUNTS."""
        result = _generate(277)
        assert result.total_slots == 277

    def test_config_with_special_constraints(self):
        cfg = _make_config(
            set_size=60,
            special_constraints=["tribal_heavy", "artifact_matters"],
        )
        result = generate_skeleton(cfg, TEMPLATE_PATH)
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
