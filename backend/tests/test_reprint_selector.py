"""Tests for the reprint selector — two-pass (select-from-pool, place-on-slots)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from mtgai.generation.reprint_selector import (
    ReprintCandidate,
    ReprintSelection,
    ReprintSlot,
    SelectionPair,
    _load_slot_texts,
    apply_selection_to_skeleton,
    convert_to_card,
    extract_set_config,
    format_candidate_tldr,
    load_reprint_knobs,
    load_reprint_pool,
    reset_reprint_stamps,
    select_reprints,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candidate(**overrides) -> ReprintCandidate:
    defaults = {
        "name": "Test Card",
        "mana_cost": "{1}{B}",
        "cmc": 2.0,
        "type_line": "Instant",
        "oracle_text": "Destroy target creature.",
        "colors": ["B"],
        "rarity": "common",
        "role": "removal_hard_kill",
        "source": "curated_pool",
        "edhrec_rank": 1500,
    }
    defaults.update(overrides)
    return ReprintCandidate(**defaults)


def _skeleton(slots: list[dict] | None = None) -> dict:
    if slots is None:
        slots = [
            {"slot_id": "B-C-03", "tweaked_text": "Black common removal instant", "card_id": None},
            {"slot_id": "G-C-01", "tweaked_text": "Green common mana creature", "card_id": None},
        ]
    return {
        "config": {"name": "Test Set", "code": "TST", "set_size": 60},
        "slots": slots,
        "total_slots": len(slots),
    }


def _llm_stub(select_names: list[str], placements: list[dict]):
    """Stub ``generate_with_tool`` dispatching on the tool name (select vs place)."""

    def stub(**kwargs):
        name = kwargs["tool_schema"]["name"]
        if name == "select_reprints":
            result = {
                "selections": [{"card_name": n, "reason": "fits the set"} for n in select_names]
            }
        else:  # place_reprints
            result = {"assignments": placements}
        return {"result": result, "input_tokens": 1, "output_tokens": 1}

    return stub


@pytest.fixture
def project_skeleton(tmp_path: Path) -> Iterator[Path]:
    """Active project (for the model id) + a skeleton.json in the asset dir."""
    from mtgai.runtime import active_project
    from mtgai.settings.model_settings import ModelSettings

    (tmp_path / "skeleton.json").write_text(json.dumps(_skeleton()), encoding="utf-8")
    active_project.write_active_project(
        active_project.ProjectState(
            set_code="TST", settings=ModelSettings(asset_folder=str(tmp_path))
        )
    )
    yield tmp_path / "skeleton.json"
    active_project.clear_active_project()


# ---------------------------------------------------------------------------
# Pool loading
# ---------------------------------------------------------------------------


class TestLoadReprintPool:
    def test_pool_loads(self):
        assert len(load_reprint_pool()) > 0

    def test_pool_size_in_range(self):
        assert 100 <= len(load_reprint_pool()) <= 400

    def test_setting_agnostic_field(self):
        by_name = {c.name: c for c in load_reprint_pool()}
        assert by_name["Murder"].setting_agnostic is True
        assert by_name["Llanowar Visionary"].setting_agnostic is False


# ---------------------------------------------------------------------------
# Candidate TLDR
# ---------------------------------------------------------------------------


class TestFormatCandidateTldr:
    def test_includes_rarity_cost_oracle(self):
        c = _make_candidate(
            name="Murder",
            mana_cost="{1}{B}{B}",
            oracle_text="Destroy target creature.",
            rarity="common",
        )
        assert format_candidate_tldr(c) == "Murder (common · {1}{B}{B} — Destroy target creature.)"

    def test_creature_pt(self):
        c = _make_candidate(
            name="Llanowar Elves",
            mana_cost="{G}",
            oracle_text="{T}: Add {G}.",
            power="1",
            toughness="1",
        )
        tldr = format_candidate_tldr(c)
        assert "1/1" in tldr and "{G}" in tldr

    def test_full_oracle_not_truncated(self):
        c = _make_candidate(name="Verbose", oracle_text="x" * 200)
        assert "x" * 200 in format_candidate_tldr(c)


# ---------------------------------------------------------------------------
# Slot loading
# ---------------------------------------------------------------------------


class TestLoadSlotTexts:
    def test_uses_tweaked_text(self, tmp_path: Path):
        sk = tmp_path / "skeleton.json"
        sk.write_text(json.dumps(_skeleton()), encoding="utf-8")
        slots = _load_slot_texts(sk)
        assert {s["slot_id"] for s in slots} == {"B-C-03", "G-C-01"}
        assert slots[0]["text"] == "Black common removal instant"

    def test_skips_filled_slots(self, tmp_path: Path):
        sk = tmp_path / "skeleton.json"
        sk.write_text(
            json.dumps(_skeleton([{"slot_id": "X", "tweaked_text": "t", "card_id": "taken"}])),
            encoding="utf-8",
        )
        assert _load_slot_texts(sk) == []

    def test_include_reprints_toggle(self, tmp_path: Path):
        # A reprint-stamped slot is listed by default (placement pass wants every
        # ordinary slot) but excluded for readers that treat it as filled (lands).
        sk = tmp_path / "skeleton.json"
        sk.write_text(
            json.dumps(
                _skeleton(
                    [
                        {"slot_id": "A", "tweaked_text": "a", "card_id": None},
                        {
                            "slot_id": "B",
                            "tweaked_text": "b",
                            "card_id": None,
                            "is_reprint_slot": True,
                            "reprint_card": "Murder · Instant · {1}{B}{B}",
                        },
                    ]
                )
            ),
            encoding="utf-8",
        )
        assert {s["slot_id"] for s in _load_slot_texts(sk)} == {"A", "B"}
        assert {s["slot_id"] for s in _load_slot_texts(sk, include_reprints=False)} == {"A"}


# ---------------------------------------------------------------------------
# Skeleton write-back (stamp / reset)
# ---------------------------------------------------------------------------


def _selection(pairs: list[tuple[str, str]]) -> ReprintSelection:
    """Build a ReprintSelection from (slot_id, card_name) tuples."""
    return ReprintSelection(
        set_code="TST",
        set_size=60,
        target_reprint_count=len(pairs),
        selections=[
            SelectionPair(
                slot=ReprintSlot(slot_id=sid, descriptor="orig"),
                candidate=_make_candidate(name=name),
                reason="r",
            )
            for sid, name in pairs
        ],
        all_candidates_considered=10,
        selection_timestamp="2026-05-27T00:00:00+00:00",
    )


class TestApplySelectionToSkeleton:
    def test_stamps_placed_slot_only(self, tmp_path: Path):
        sk = tmp_path / "skeleton.json"
        sk.write_text(json.dumps(_skeleton()), encoding="utf-8")
        stamped = apply_selection_to_skeleton(sk, _selection([("B-C-03", "Murder")]))
        assert stamped == 1
        slots = {s["slot_id"]: s for s in json.loads(sk.read_text())["slots"]}
        assert slots["B-C-03"]["is_reprint_slot"] is True
        assert "Murder" in slots["B-C-03"]["reprint_card"]
        # The other slot is untouched.
        assert not slots["G-C-01"].get("is_reprint_slot")
        # tweaked_text is preserved (so a later un-stamp restores the themed slot).
        assert slots["B-C-03"]["tweaked_text"] == "Black common removal instant"

    def test_rerun_resets_prior_stamps(self, tmp_path: Path):
        # A re-roll that places elsewhere must un-stamp the previous slot.
        sk = tmp_path / "skeleton.json"
        sk.write_text(json.dumps(_skeleton()), encoding="utf-8")
        apply_selection_to_skeleton(sk, _selection([("B-C-03", "Murder")]))
        apply_selection_to_skeleton(sk, _selection([("G-C-01", "Llanowar Elves")]))
        slots = {s["slot_id"]: s for s in json.loads(sk.read_text())["slots"]}
        assert not slots["B-C-03"]["is_reprint_slot"]
        assert slots["B-C-03"]["reprint_card"] is None
        assert slots["G-C-01"]["is_reprint_slot"] is True

    def test_missing_slot_is_skipped(self, tmp_path: Path):
        sk = tmp_path / "skeleton.json"
        sk.write_text(json.dumps(_skeleton()), encoding="utf-8")
        stamped = apply_selection_to_skeleton(sk, _selection([("DOES-NOT-EXIST", "Murder")]))
        assert stamped == 0

    def test_reset_reprint_stamps(self):
        skeleton = _skeleton(
            [
                {"slot_id": "A", "is_reprint_slot": True, "reprint_card": "Murder · Instant"},
                {"slot_id": "B", "is_reprint_slot": False},
            ]
        )
        assert reset_reprint_stamps(skeleton) is True
        assert all(not s.get("is_reprint_slot") for s in skeleton["slots"])
        # Idempotent: a second reset finds nothing to change.
        assert reset_reprint_stamps(skeleton) is False


# ---------------------------------------------------------------------------
# Knobs persistence
# ---------------------------------------------------------------------------


class TestLoadReprintKnobs:
    def test_reads_from_disk(self, tmp_path: Path):
        (tmp_path / "reprints").mkdir()
        (tmp_path / "reprints" / "knobs.json").write_text(
            json.dumps({"common": 3, "jitter_pct": 0.0}), encoding="utf-8"
        )
        k = load_reprint_knobs(tmp_path)
        assert k.common == 3 and k.jitter_pct == 0.0

    def test_default_when_absent(self, tmp_path: Path):
        assert load_reprint_knobs(tmp_path).common is None


# ---------------------------------------------------------------------------
# Set config
# ---------------------------------------------------------------------------


class TestExtractSetConfig:
    def test_basic_fields(self, tmp_path: Path):
        sk = tmp_path / "skeleton.json"
        sk.write_text(json.dumps(_skeleton()), encoding="utf-8")
        cfg = extract_set_config(sk)
        assert cfg["code"] == "TST"
        assert cfg["set_size"] == 60


# ---------------------------------------------------------------------------
# Two-pass selection
# ---------------------------------------------------------------------------


class TestSelectReprints:
    def test_select_and_place(self, project_skeleton: Path):
        stub = _llm_stub(
            ["Murder"], [{"card_name": "Murder", "slot_id": "B-C-03", "reason": "removal"}]
        )
        with patch("mtgai.generation.llm_client.generate_with_tool", stub):
            result = select_reprints(project_skeleton, count=1)
        assert result.target_reprint_count == 1
        assert len(result.selections) == 1
        assert result.selections[0].candidate.name == "Murder"
        assert result.selections[0].slot.slot_id == "B-C-03"

    def test_count_resolved_per_rarity_from_knobs(self, project_skeleton: Path):
        # 60-card set: auto common = round(0.030 * 60 * 95/276) = 1, others 0.
        stub = _llm_stub(["Murder"], [{"card_name": "Murder", "slot_id": "B-C-03", "reason": "r"}])
        with patch("mtgai.generation.llm_client.generate_with_tool", stub):
            result = select_reprints(project_skeleton)
        assert result.per_rarity_targets is not None
        assert result.target_reprint_count == sum(result.per_rarity_targets.values())
        assert result.per_rarity_targets["common"] == 1

    def test_unknown_card_name_dropped(self, project_skeleton: Path):
        stub = _llm_stub(["Not A Real Card"], [])
        with patch("mtgai.generation.llm_client.generate_with_tool", stub):
            result = select_reprints(project_skeleton, count=1)
        assert result.selections == []

    def test_placement_to_unknown_slot_dropped(self, project_skeleton: Path):
        stub = _llm_stub(["Murder"], [{"card_name": "Murder", "slot_id": "NOPE", "reason": "r"}])
        with patch("mtgai.generation.llm_client.generate_with_tool", stub):
            result = select_reprints(project_skeleton, count=1)
        assert result.selections == []  # bad slot → nothing placed

    def test_routes_log_dir_to_stage_logs(self, project_skeleton: Path):
        captured: list = []

        def stub(**kwargs):
            captured.append(kwargs.get("log_dir"))
            name = kwargs["tool_schema"]["name"]
            if name == "select_reprints":
                return {
                    "result": {"selections": [{"card_name": "Murder", "reason": "x"}]},
                    "input_tokens": 1,
                    "output_tokens": 1,
                }
            return {
                "result": {
                    "assignments": [{"card_name": "Murder", "slot_id": "B-C-03", "reason": "x"}]
                },
                "input_tokens": 1,
                "output_tokens": 1,
            }

        with patch("mtgai.generation.llm_client.generate_with_tool", stub):
            select_reprints(project_skeleton, count=1)
        assert captured and captured[0] == project_skeleton.parent / "reprints" / "logs"

    def test_zero_count_makes_no_calls(self, project_skeleton: Path):
        called = {"n": 0}

        def stub(**kwargs):
            called["n"] += 1
            return {"result": {}, "input_tokens": 0, "output_tokens": 0}

        with patch("mtgai.generation.llm_client.generate_with_tool", stub):
            result = select_reprints(project_skeleton, count=0)
        assert result.selections == []
        assert called["n"] == 0


# ---------------------------------------------------------------------------
# Card conversion
# ---------------------------------------------------------------------------


class TestConvertToCard:
    def test_basic_conversion(self):
        cand = _make_candidate(
            name="Murder", mana_cost="{1}{B}{B}", cmc=3.0, type_line="Instant", colors=["B"]
        )
        card = convert_to_card(cand, "B-C-03", "ASD", "61")
        assert card.name == "Murder"
        assert card.is_reprint is True
        assert card.slot_id == "B-C-03"
        assert card.rarity.value == "common"

    def test_creature_subtypes(self):
        cand = _make_candidate(
            name="Llanowar Elves",
            mana_cost="{G}",
            cmc=1.0,
            type_line="Creature -- Elf Druid",
            colors=["G"],
            power="1",
            toughness="1",
        )
        card = convert_to_card(cand, "G-C-01", "ASD", "62")
        assert "Elf" in card.subtypes and "Druid" in card.subtypes
        assert "Creature" in card.card_types
