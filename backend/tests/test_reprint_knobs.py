"""Tests for reprint knobs — per-rarity targets + proportional jitter."""

from __future__ import annotations

import random

import pytest
from pydantic import ValidationError

from mtgai.generation.reprint_knobs import (
    RARITY_WEIGHTS,
    REPRINT_RARITY_RATES,
    ReprintKnobs,
    auto_target,
    default_knobs,
    from_payload,
    resolve_targets,
)


class TestReprintKnobsModel:
    def test_default_all_auto(self):
        k = default_knobs()
        assert k.common is None and k.uncommon is None
        assert k.rare is None and k.mythic is None
        assert k.jitter_pct == 0.25

    def test_negative_clamps_to_zero(self):
        assert ReprintKnobs(common=-5).common == 0

    def test_huge_clamps_to_max(self):
        assert ReprintKnobs(rare=9999).rare == 40

    def test_jitter_clamped(self):
        assert ReprintKnobs(jitter_pct=-1.0).jitter_pct == 0.0
        assert ReprintKnobs(jitter_pct=9.0).jitter_pct == 1.0

    def test_provenance(self):
        prov = ReprintKnobs(common=2).provenance()
        assert prov["common"] == "user"
        assert prov["rare"] == "auto"


class TestFromPayload:
    def test_blank_and_none_are_auto(self):
        k = from_payload({"common": "", "uncommon": None})
        assert k.common is None and k.uncommon is None

    def test_numeric_parsed(self):
        k = from_payload({"common": "3", "rare": 1})
        assert k.common == 3 and k.rare == 1

    def test_junk_is_auto(self):
        assert from_payload({"common": "abc"}).common is None

    def test_jitter_parsed(self):
        assert from_payload({"jitter_pct": "0.5"}).jitter_pct == 0.5

    def test_non_dict_is_default(self):
        assert from_payload(None).common is None

    def test_infinity_is_auto(self):
        # JSON ``1e400`` parses to ``float('inf')``; int(inf) raised an
        # uncaught OverflowError -> 500. Now it drops to auto (None), like junk.
        for val in (float("inf"), float("-inf"), "1e400", "-1e400", float("nan")):
            k = from_payload({"common": val})
            assert k.common is None, val

    def test_infinity_jitter_is_default(self):
        # A non-finite jitter falls back to the field default (0.25), no crash.
        for val in (float("inf"), float("-inf"), "1e400", float("nan")):
            k = from_payload({"jitter_pct": val})
            assert k.jitter_pct == 0.25, val

    def test_infinity_across_all_rarities(self):
        k = from_payload(
            {"common": "1e400", "uncommon": "-1e400", "rare": float("inf"), "mythic": float("nan")}
        )
        assert k.common is None and k.uncommon is None
        assert k.rare is None and k.mythic is None


class TestModelDirectConstructionNonFinite:
    """Direct ``ReprintKnobs(...)`` construction must not crash on non-finite input."""

    def test_inf_int_field_raises_clean_validation_error(self):
        # An int rarity field rejects a non-finite float at the Pydantic coercion
        # layer (a catchable ValidationError, NOT an uncaught OverflowError/500).
        for val in (float("inf"), float("-inf"), float("nan")):
            with pytest.raises(ValidationError):
                ReprintKnobs(common=val)

    def test_inf_jitter_clamps(self):
        # jitter_pct is a plain float field, so it reaches the model validator,
        # which clamps inf/-inf into [0, 1] and coerces NaN to 0.
        assert ReprintKnobs(jitter_pct=float("inf")).jitter_pct == 1.0
        assert ReprintKnobs(jitter_pct=float("-inf")).jitter_pct == 0.0
        assert ReprintKnobs(jitter_pct=float("nan")).jitter_pct == 0.0


class TestAutoTarget:
    def test_rate_times_estimated_rarity_count(self):
        # rate x (set_size x rarity_weight / total_weight)
        total_w = sum(RARITY_WEIGHTS.values())
        expected = round(REPRINT_RARITY_RATES["common"] * 277 * RARITY_WEIGHTS["common"] / total_w)
        assert auto_target("common", 277) == expected

    def test_277_common_is_about_three(self):
        assert auto_target("common", 277) == 3

    def test_tiny_set_rounds_low(self):
        assert auto_target("mythic", 60) == 0


class TestResolveTargets:
    def test_pinned_is_exact(self):
        out = resolve_targets(ReprintKnobs(common=4, jitter_pct=0.0), 277)
        assert out["common"] == 4

    def test_auto_derives_from_rate(self):
        out = resolve_targets(ReprintKnobs(jitter_pct=0.0), 277)
        assert out["common"] == auto_target("common", 277)
        assert out["rare"] == auto_target("rare", 277)

    def test_no_jitter_when_pct_zero(self):
        out = resolve_targets(ReprintKnobs(jitter_pct=0.0), 277)
        assert sum(out.values()) == sum(auto_target(r, 277) for r in out)

    def test_jitter_seeded_in_band(self):
        # 277-set auto total ~5; amount = round(0.25*5) = 1, realized on commons.
        out = resolve_targets(ReprintKnobs(jitter_pct=0.25), 277, rng=random.Random(0))
        assert 4 <= sum(out.values()) <= 6

    def test_pinned_rarity_never_jittered(self):
        out = resolve_targets(ReprintKnobs(common=5, jitter_pct=1.0), 277, rng=random.Random(7))
        assert out["common"] == 5
