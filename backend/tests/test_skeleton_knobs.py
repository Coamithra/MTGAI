"""Tests for the skeleton knobs schema (card 6a16d8ff, Phase A foundation).

Covers the spec↔field drift guard, clamp-on-validate, from_payload warnings +
provenance, non-creature weight normalization, pin merging, and Cycle
normalization / span sizing.
"""

from __future__ import annotations

from mtgai.skeleton.knobs import (
    CYCLE_SPAN_SIZE,
    KNOB_SPEC_BY_KEY,
    KNOB_SPECS,
    Cycle,
    CycleSpan,
    SkeletonKnobs,
    default_knobs,
    knob_specs_payload,
)

# ---------------------------------------------------------------------------
# Spec / field consistency (drift guard)
# ---------------------------------------------------------------------------


# Fields that are intentionally not clampable knobs (metadata / structured).
_NON_KNOB_FIELDS = {"cycles", "irregular_subtypes", "provenance", "pinned"}


class TestSpecFieldConsistency:
    def test_every_spec_is_a_model_field(self):
        for spec in KNOB_SPECS:
            assert spec.key in SkeletonKnobs.model_fields, f"{spec.key} not a field"

    def test_every_scalar_field_has_a_spec(self):
        # Reverse direction: a scalar SkeletonKnobs field without a KNOB_SPECS entry
        # would silently miss clamping, the AI tuner, and the wizard control. Only
        # the metadata/structured fields are allowed to have no spec.
        for name in SkeletonKnobs.model_fields:
            if name in _NON_KNOB_FIELDS:
                continue
            assert name in KNOB_SPEC_BY_KEY, f"{name} field has no KNOB_SPECS entry"

    def test_field_defaults_match_spec_defaults(self):
        knobs = SkeletonKnobs()
        for spec in KNOB_SPECS:
            assert getattr(knobs, spec.key) == spec.clamp(spec.default), (
                f"{spec.key} default drifted from its spec"
            )

    def test_spec_keys_unique(self):
        keys = [s.key for s in KNOB_SPECS]
        assert len(keys) == len(set(keys))

    def test_min_le_default_le_max(self):
        for spec in KNOB_SPECS:
            assert spec.min <= spec.default <= spec.max, f"{spec.key} default out of bounds"

    def test_payload_is_serializable(self):
        payload = knob_specs_payload()
        assert len(payload) == len(KNOB_SPECS)
        assert all("min" in p and "max" in p and "step" in p for p in payload)


# ---------------------------------------------------------------------------
# Clamp on validation
# ---------------------------------------------------------------------------


class TestClampOnValidate:
    def test_over_max_clamped(self):
        knobs = SkeletonKnobs(multicolor_mythic=9.0)
        assert knobs.multicolor_mythic == KNOB_SPEC_BY_KEY["multicolor_mythic"].max

    def test_under_min_clamped(self):
        knobs = SkeletonKnobs(rarity_rare=10)
        assert knobs.rarity_rare == KNOB_SPEC_BY_KEY["rarity_rare"].min

    def test_int_knob_rounds(self):
        knobs = SkeletonKnobs(signposts_per_pair=1.9)
        assert knobs.signposts_per_pair == 2
        assert isinstance(knobs.signposts_per_pair, int)

    def test_defaults_are_within_bounds(self):
        knobs = SkeletonKnobs()
        for spec in KNOB_SPECS:
            assert spec.min <= getattr(knobs, spec.key) <= spec.max

    def test_planeswalker_default_is_zero(self):
        # Preserves the failure-path skeleton (today has no planeswalker slot).
        assert SkeletonKnobs().planeswalker_count == 0


# ---------------------------------------------------------------------------
# from_payload
# ---------------------------------------------------------------------------


class TestFromPayload:
    def test_clamp_warning_recorded(self):
        knobs, warnings = SkeletonKnobs.from_payload({"multicolor_rare": 0.99})
        assert knobs.multicolor_rare == KNOB_SPEC_BY_KEY["multicolor_rare"].max
        assert any("Multicolor rares" in w for w in warnings)

    def test_in_range_value_no_warning(self):
        knobs, warnings = SkeletonKnobs.from_payload({"multicolor_rare": 0.30})
        assert knobs.multicolor_rare == 0.30
        assert warnings == []

    def test_non_numeric_ignored_with_warning(self):
        knobs, warnings = SkeletonKnobs.from_payload({"rarity_rare": "lots"})
        assert knobs.rarity_rare == KNOB_SPEC_BY_KEY["rarity_rare"].default
        assert any("non-numeric" in w for w in warnings)

    def test_unknown_keys_ignored(self):
        knobs, warnings = SkeletonKnobs.from_payload({"made_up_knob": 5})
        assert warnings == []
        assert not hasattr(knobs, "made_up_knob")

    def test_provenance_marks_changed_keys(self):
        knobs, _ = SkeletonKnobs.from_payload({"multicolor_rare": 0.40}, source="ai")
        assert knobs.provenance["multicolor_rare"] == "ai"
        # An unmentioned knob stays default-provenance.
        assert knobs.provenance["multicolor_mythic"] == "default"

    def test_value_equal_to_default_stays_default_provenance(self):
        knobs, _ = SkeletonKnobs.from_payload({"multicolor_rare": 0.25}, source="ai")
        assert knobs.provenance["multicolor_rare"] == "default"

    def test_cycles_parsed(self):
        knobs, _ = SkeletonKnobs.from_payload(
            {
                "cycles": [
                    {"id": "guildgates", "name": "Gates", "span": "pairs10", "card_type": "land"}
                ]
            }
        )
        assert len(knobs.cycles) == 1
        assert knobs.cycles[0].span == CycleSpan.PAIRS10

    def test_malformed_cycle_dropped(self):
        knobs, _ = SkeletonKnobs.from_payload(
            {"cycles": ["not a dict", {"id": "ok", "name": "Ok"}]}
        )
        assert len(knobs.cycles) == 1
        assert knobs.cycles[0].id == "ok"

    def test_irregular_subtypes_normalized(self):
        # Lowercased, stripped, deduped, blanks/non-strings dropped, order kept.
        knobs, _ = SkeletonKnobs.from_payload(
            {"irregular_subtypes": ["Saga", " SHRINE ", "saga", "", 5, "class"]}, source="ai"
        )
        assert knobs.irregular_subtypes == ["saga", "shrine", "class"]
        assert knobs.provenance["irregular_subtypes"] == "ai"

    def test_irregular_subtypes_empty_has_no_provenance_stamp(self):
        knobs, _ = SkeletonKnobs.from_payload({"irregular_subtypes": []}, source="ai")
        assert knobs.irregular_subtypes == []
        assert "irregular_subtypes" not in knobs.provenance

    def test_pinned_filtered_to_real_knobs(self):
        knobs, _ = SkeletonKnobs.from_payload({"pinned": ["multicolor_rare", "bogus"]})
        assert knobs.pinned == ["multicolor_rare"]

    def test_does_not_mutate_input(self):
        raw = {"signposts_per_pair": 1.7, "multicolor_rare": 0.40}
        SkeletonKnobs.from_payload(raw)
        # The int-knob rounding must not write back into the caller's dict.
        assert raw == {"signposts_per_pair": 1.7, "multicolor_rare": 0.40}

    def test_empty_payload_is_all_defaults(self):
        knobs, warnings = SkeletonKnobs.from_payload({})
        assert warnings == []
        assert knobs.model_dump(
            exclude={"provenance", "pinned", "cycles"}
        ) == SkeletonKnobs().model_dump(exclude={"provenance", "pinned", "cycles"})


# ---------------------------------------------------------------------------
# Non-creature weights
# ---------------------------------------------------------------------------


class TestNoncreatureWeights:
    def test_default_weights_sum_to_one(self):
        w = SkeletonKnobs().noncreature_weights()
        assert abs(sum(w.values()) - 1.0) < 1e-9

    def test_artifact_default_is_zero(self):
        assert SkeletonKnobs().noncreature_weights()["artifact"] == 0.0

    def test_all_zero_falls_back_to_even(self):
        knobs = SkeletonKnobs(
            noncreature_instant=0.0,
            noncreature_sorcery=0.0,
            noncreature_enchantment=0.0,
            noncreature_artifact=0.0,
        )
        w = knobs.noncreature_weights()
        assert all(abs(v - 0.25) < 1e-9 for v in w.values())

    def test_artifact_heavy_skews(self):
        knobs = SkeletonKnobs(noncreature_artifact=1.0)
        w = knobs.noncreature_weights()
        assert w["artifact"] > w["instant"]


# ---------------------------------------------------------------------------
# Pin merging
# ---------------------------------------------------------------------------


class TestMergePins:
    def test_pinned_value_restored_after_retune(self):
        base = SkeletonKnobs(multicolor_rare=0.40, pinned=["multicolor_rare"])
        base = base.model_copy(update={"provenance": {"multicolor_rare": "user"}})
        retuned = SkeletonKnobs(multicolor_rare=0.15)  # AI moved it
        merged = retuned.merge_pins_from(base)
        assert merged.multicolor_rare == 0.40
        assert merged.provenance["multicolor_rare"] == "user"
        assert merged.pinned == ["multicolor_rare"]

    def test_no_pins_no_cycles_returns_self(self):
        base = SkeletonKnobs()
        retuned = SkeletonKnobs(multicolor_rare=0.40)
        assert retuned.merge_pins_from(base) is retuned

    def test_base_cycles_preserved_with_no_pins(self):
        # Card 6a1ff25f: a user-defined cycle must survive an AI re-tune even when
        # the AI dropped it and no scalar knob is pinned.
        cyc = Cycle(id="gates", name="Guildgates", span=CycleSpan.PAIRS10, card_type="land")
        base = SkeletonKnobs(cycles=[cyc])
        retuned = SkeletonKnobs(multicolor_rare=0.40)  # AI proposed no cycles
        merged = retuned.merge_pins_from(base)
        assert [c.id for c in merged.cycles] == ["gates"]
        # AI's scalar move is otherwise honored (nothing pinned).
        assert merged.multicolor_rare == 0.40

    def test_base_cycles_preserved_with_pins(self):
        cyc = Cycle(id="gates", name="Guildgates", span=CycleSpan.PAIRS10, card_type="land")
        base = SkeletonKnobs(multicolor_rare=0.40, pinned=["multicolor_rare"], cycles=[cyc])
        base = base.model_copy(update={"provenance": {"multicolor_rare": "user"}})
        retuned = SkeletonKnobs(multicolor_rare=0.15)  # AI moved + dropped the cycle
        merged = retuned.merge_pins_from(base)
        assert [c.id for c in merged.cycles] == ["gates"]
        assert merged.multicolor_rare == 0.40
        assert merged.provenance["multicolor_rare"] == "user"

    def test_ai_added_cycle_kept_alongside_base(self):
        # A new AI cycle (distinct id) rides on top of the carried-over user cycle.
        user_cyc = Cycle(id="gates", name="Guildgates", span=CycleSpan.PAIRS10, card_type="land")
        ai_cyc = Cycle(id="titans", name="Titans", span=CycleSpan.MONO5, card_type="creature")
        base = SkeletonKnobs(cycles=[user_cyc])
        retuned = SkeletonKnobs(cycles=[ai_cyc])
        merged = retuned.merge_pins_from(base)
        assert [c.id for c in merged.cycles] == ["gates", "titans"]

    def test_ai_recycled_id_does_not_duplicate(self):
        # If the AI re-proposes a cycle with the same id, the user's version wins
        # and there's no duplicate.
        user_cyc = Cycle(id="gates", name="User Gates", span=CycleSpan.PAIRS10, card_type="land")
        ai_dupe = Cycle(id="gates", name="AI Gates", span=CycleSpan.MONO5, card_type="creature")
        base = SkeletonKnobs(cycles=[user_cyc])
        retuned = SkeletonKnobs(cycles=[ai_dupe])
        merged = retuned.merge_pins_from(base)
        assert [c.id for c in merged.cycles] == ["gates"]
        assert merged.cycles[0].name == "User Gates"

    def test_ai_cycles_kept_when_base_has_none(self):
        ai_cyc = Cycle(id="titans", name="Titans", span=CycleSpan.MONO5, card_type="creature")
        base = SkeletonKnobs()
        retuned = SkeletonKnobs(cycles=[ai_cyc])
        merged = retuned.merge_pins_from(base)
        assert [c.id for c in merged.cycles] == ["titans"]

    def test_ai_irregular_subtypes_replace_base(self):
        # A re-tune is meant to re-decide the picks: a non-empty AI list wins.
        base = SkeletonKnobs(irregular_subtypes=["saga"])
        retuned = SkeletonKnobs(irregular_subtypes=["shrine", "class"])
        merged = retuned.merge_pins_from(base)
        assert merged.irregular_subtypes == ["shrine", "class"]

    def test_empty_ai_irregular_subtypes_fall_back_to_base(self):
        # If the AI returned none, a prior/hand-edited pick (and its provenance
        # badge) must not be silently lost.
        base = SkeletonKnobs(irregular_subtypes=["saga"]).model_copy(
            update={"provenance": {"irregular_subtypes": "user"}}
        )
        retuned = SkeletonKnobs(multicolor_rare=0.40)  # AI proposed no picks
        merged = retuned.merge_pins_from(base)
        assert merged.irregular_subtypes == ["saga"]
        assert merged.provenance["irregular_subtypes"] == "user"

    def test_empty_ai_irregular_subtypes_carry_with_pins(self):
        base = SkeletonKnobs(
            multicolor_rare=0.40, pinned=["multicolor_rare"], irregular_subtypes=["shrine"]
        ).model_copy(update={"provenance": {"irregular_subtypes": "user"}})
        retuned = SkeletonKnobs(multicolor_rare=0.15)
        merged = retuned.merge_pins_from(base)
        assert merged.irregular_subtypes == ["shrine"]
        assert merged.provenance["irregular_subtypes"] == "user"
        assert merged.multicolor_rare == 0.40


# ---------------------------------------------------------------------------
# Cycle model
# ---------------------------------------------------------------------------


class TestCycle:
    def test_span_sizes_cover_all_spans(self):
        for span in CycleSpan:
            assert span in CYCLE_SPAN_SIZE

    def test_land_cmc_forced_to_zero(self):
        cyc = Cycle(id="c", name="Gates", card_type="land", cmc_target=4)
        assert cyc.cmc_target == 0

    def test_bad_rarity_normalized(self):
        cyc = Cycle(id="c", name="X", rarity="legendary")
        assert cyc.rarity == "uncommon"

    def test_bad_card_type_normalized(self):
        cyc = Cycle(id="c", name="X", card_type="spaceship")
        assert cyc.card_type == "creature"

    def test_size_property(self):
        assert Cycle(id="c", name="X", span=CycleSpan.PAIRS10).size == 10
        assert Cycle(id="c", name="X", span=CycleSpan.MONO5).size == 5
        assert Cycle(id="c", name="X", span=CycleSpan.ALLIED5).size == 5


def test_default_knobs_provenance_all_default():
    knobs = default_knobs()
    assert all(v == "default" for v in knobs.provenance.values())
    assert set(knobs.provenance) == {s.key for s in KNOB_SPECS}
