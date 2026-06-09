"""Tests for the lands stage — 5 basics + an investigated bonus dual land.

The lands stage no longer generates land cycles (card-gen owns those now). It
makes two AI calls: basic-land flavor, then a fixing investigation that adds one
rare dual land only when a gap remains. ``generate_with_tool`` is monkeypatched on
the land_generator module (it imports the symbol at module top), dispatching on
the tool name.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

import mtgai.generation.land_generator as land_gen
from mtgai.generation.land_generator import (
    _build_basics_prompt,
    _build_investigation_prompt,
    _load_reprint_summary,
    _make_nonbasic_card,
    generate_lands,
)
from mtgai.models.enums import Color

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _skeleton() -> dict:
    return {
        "config": {"name": "Test Set", "code": "TST", "set_size": 60},
        "slots": [
            {"slot_id": "W-C-01", "tweaked_text": "White common creature", "card_id": None},
            {"slot_id": "U-C-01", "tweaked_text": "Blue common creature", "card_id": None},
        ],
    }


_BASICS_RESULT = {
    "basics": [
        {
            "land_name": n,
            "flavor_text": f"Flavor for {n}.",
            "art_scenes": [f"{n} vista {i}" for i in range(1, 5)],  # 4 distinct briefs
        }
        for n in ("Plains", "Island", "Swamp", "Mountain", "Forest")
    ]
}

_DUAL = {
    "name": "Sunset Delta",
    "type_line": "Land",
    "oracle_text": "{T}: Add {W} or {U}.",
    "flavor_text": "Where two rivers meet.",
}


def _llm_stub(*, needs_dual: bool, dual: dict | None = None):
    """Stub ``generate_with_tool`` dispatching on the tool name (basics vs investigation)."""

    def stub(**kwargs):
        name = kwargs["tool_schema"]["name"]
        if name == "create_basic_lands":
            result = _BASICS_RESULT
        else:  # investigate_fixing
            result: dict = {"needs_dual_land": needs_dual, "reasoning": "because"}
            if dual is not None:
                result["dual_land"] = dual
        return {"result": result, "input_tokens": 1, "output_tokens": 1}

    return stub


@pytest.fixture
def project_dir(tmp_path: Path) -> Iterator[Path]:
    """Active project + skeleton.json in the asset dir (set_artifact_dir → tmp_path)."""
    from mtgai.runtime import active_project
    from mtgai.settings.model_settings import ModelSettings

    (tmp_path / "skeleton.json").write_text(json.dumps(_skeleton()), encoding="utf-8")
    active_project.write_active_project(
        active_project.ProjectState(
            set_code="TST", settings=ModelSettings(asset_folder=str(tmp_path))
        )
    )
    yield tmp_path
    active_project.clear_active_project()


# ---------------------------------------------------------------------------
# generate_lands — accept / decline branches
# ---------------------------------------------------------------------------


def _fixed_alternates(monkeypatch, n: int) -> None:
    """Pin the per-type alternate count so card totals are deterministic."""
    monkeypatch.setattr(land_gen.random, "randint", lambda _a, _b: n)


class TestGenerateLands:
    def test_accept_writes_basics_and_dual(self, project_dir: Path, monkeypatch):
        _fixed_alternates(monkeypatch, 3)  # 5 types x 3 alternates + 1 dual = 16
        monkeypatch.setattr(land_gen, "generate_with_tool", _llm_stub(needs_dual=True, dual=_DUAL))
        monkeypatch.setattr(land_gen, "cost_from_result", lambda _r: 0.001)
        summary = generate_lands()
        cards_dir = project_dir / "cards"
        assert summary["total_cards"] == 16
        assert len(list(cards_dir.glob("*.json"))) == 16
        assert len(list(cards_dir.glob("L-01*_plains.json"))) == 3  # 3 Plains alternates
        l06 = next(cards_dir.glob("L-06_*.json"))
        data = json.loads(l06.read_text(encoding="utf-8"))
        assert data["rarity"] == "rare"
        assert data["is_reprint"] is False
        assert set(data["color_identity"]) == {"W", "U"}

    def test_both_calls_use_two_cached_system_blocks(self, project_dir: Path, monkeypatch):
        """Static context rides in cached system blocks for BOTH lands calls (cap: 2
        blocks + tool = 3 markers, under Anthropic's 4)."""
        _fixed_alternates(monkeypatch, 2)
        seen: dict[str, dict] = {}

        def stub(**kwargs):
            name = kwargs["tool_schema"]["name"]
            seen[name] = kwargs
            if name == "create_basic_lands":
                return {"result": _BASICS_RESULT, "input_tokens": 1, "output_tokens": 1}
            return {
                "result": {"needs_dual_land": False, "reasoning": "x"},
                "input_tokens": 1,
                "output_tokens": 1,
            }

        monkeypatch.setattr(land_gen, "generate_with_tool", stub)
        monkeypatch.setattr(land_gen, "cost_from_result", lambda _r: 0.0)
        generate_lands()
        for tool in ("create_basic_lands", "investigate_fixing"):
            kw = seen[tool]
            assert not kw.get("system_prompt")
            blocks = kw["system_blocks"]
            assert len(blocks) == 2 and all(cache is True for _t, cache in blocks)

    def test_decline_writes_basics_only(self, project_dir: Path, monkeypatch):
        _fixed_alternates(monkeypatch, 3)
        monkeypatch.setattr(land_gen, "generate_with_tool", _llm_stub(needs_dual=False))
        monkeypatch.setattr(land_gen, "cost_from_result", lambda _r: 0.0)
        summary = generate_lands()
        cards_dir = project_dir / "cards"
        assert summary["total_cards"] == 15  # 5 types x 3, no dual
        assert not list(cards_dir.glob("L-06_*.json"))

    def test_needs_dual_but_no_design_skips(self, project_dir: Path, monkeypatch):
        # needs_dual_land True but no dual_land object → no L-06 written.
        _fixed_alternates(monkeypatch, 3)
        monkeypatch.setattr(land_gen, "generate_with_tool", _llm_stub(needs_dual=True, dual=None))
        monkeypatch.setattr(land_gen, "cost_from_result", lambda _r: 0.0)
        summary = generate_lands()
        assert summary["total_cards"] == 15

    def test_needs_dual_partial_design_skips_without_crash(self, project_dir: Path, monkeypatch):
        # A local model can emit a partial dual_land ({name, type_line} only) via the
        # llamacpp text-extraction fallback (no schema enforcement). Before the fix,
        # the bare data["oracle_text"] subscript in _make_nonbasic_card raised
        # KeyError out of generate_lands AFTER the basics were already written. The
        # stage must complete cleanly: basics saved, the under-specified dual skipped.
        _fixed_alternates(monkeypatch, 3)
        partial_dual = {"name": "Sunset Delta", "type_line": "Land"}  # no oracle_text/flavor
        monkeypatch.setattr(
            land_gen, "generate_with_tool", _llm_stub(needs_dual=True, dual=partial_dual)
        )
        monkeypatch.setattr(land_gen, "cost_from_result", lambda _r: 0.0)
        summary = generate_lands()  # must NOT raise
        cards_dir = project_dir / "cards"
        assert summary["total_cards"] == 15  # 5 types x 3 basics, dual skipped
        assert not list(cards_dir.glob("L-06_*.json"))  # under-specified dual not materialized
        assert len(list(cards_dir.glob("L-01*_plains.json"))) == 3  # basics survived

    def test_alternates_count_in_range(self, project_dir: Path, monkeypatch):
        # No count pin: every basic type must land in [2, 4] printings.
        monkeypatch.setattr(land_gen, "generate_with_tool", _llm_stub(needs_dual=False))
        monkeypatch.setattr(land_gen, "cost_from_result", lambda _r: 0.0)
        generate_lands()
        cards_dir = project_dir / "cards"
        for base in ("L-01", "L-02", "L-03", "L-04", "L-05"):
            assert 2 <= len(list(cards_dir.glob(f"{base}*.json"))) <= 4

    def test_flavor_sparse_and_scenes_distinct(self, project_dir: Path, monkeypatch):
        _fixed_alternates(monkeypatch, 4)  # all 4 briefs → 4 printings per type
        monkeypatch.setattr(land_gen, "generate_with_tool", _llm_stub(needs_dual=False))
        monkeypatch.setattr(land_gen, "cost_from_result", lambda _r: 0.0)
        generate_lands()
        cards_dir = project_dir / "cards"
        for base in ("L-01", "L-02", "L-03", "L-04", "L-05"):
            cards = [json.loads(p.read_text(encoding="utf-8")) for p in cards_dir.glob(f"{base}*")]
            flavored = [c for c in cards if c.get("flavor_text")]
            assert len(flavored) == 1  # exactly one printing per type carries flavor
            # Each alternate gets a distinct art brief (in design_notes) → distinct art.
            assert len({c["design_notes"] for c in cards}) == len(cards)

    def test_collector_numbers_unique(self, project_dir: Path, monkeypatch):
        _fixed_alternates(monkeypatch, 4)
        monkeypatch.setattr(land_gen, "generate_with_tool", _llm_stub(needs_dual=True, dual=_DUAL))
        monkeypatch.setattr(land_gen, "cost_from_result", lambda _r: 0.0)
        generate_lands()
        cards_dir = project_dir / "cards"
        cns = [
            json.loads(p.read_text(encoding="utf-8"))["collector_number"]
            for p in cards_dir.glob("*.json")
        ]
        assert len(cns) == len(set(cns))  # no collector-number collisions

    def test_rerun_clears_stale_land_cards(self, project_dir: Path, monkeypatch):
        # A re-run must drop the prior run's land cards (old single basics, or
        # alternates this run won't reproduce) but leave non-land cards alone.
        cards_dir = project_dir / "cards"
        cards_dir.mkdir(parents=True, exist_ok=True)
        (cards_dir / "L-01_plains.json").write_text("{}", encoding="utf-8")  # stale single basic
        (cards_dir / "045_some_creature.json").write_text("{}", encoding="utf-8")  # card-gen card
        _fixed_alternates(monkeypatch, 2)
        monkeypatch.setattr(land_gen, "generate_with_tool", _llm_stub(needs_dual=False))
        monkeypatch.setattr(land_gen, "cost_from_result", lambda _r: 0.0)
        generate_lands()
        assert not (cards_dir / "L-01_plains.json").exists()  # stale basic cleared
        assert (cards_dir / "045_some_creature.json").exists()  # non-land survives
        assert (cards_dir / "L-01a_plains.json").exists()  # fresh alternate written

    def test_no_land_cycle_generation(self):
        # Land cycles moved to card-gen; the lands stage no longer carries the
        # cycle helpers, so it cannot emit cycle calls.
        assert not hasattr(land_gen, "generate_land_cycles")
        assert not hasattr(land_gen, "_make_cycle_land_card")

    def test_routes_log_dir_to_stage_logs(self, project_dir: Path, monkeypatch):
        # Both AI calls (basics + investigation) must route their transcript to
        # <asset>/lands/logs so it sits beside the stage artifacts.
        captured: list = []

        def stub(**kwargs):
            captured.append(kwargs.get("log_dir"))
            if kwargs["tool_schema"]["name"] == "create_basic_lands":
                result: dict = _BASICS_RESULT
            else:
                result = {"needs_dual_land": False, "reasoning": "ok"}
            return {"result": result, "input_tokens": 1, "output_tokens": 1}

        monkeypatch.setattr(land_gen, "generate_with_tool", stub)
        monkeypatch.setattr(land_gen, "cost_from_result", lambda _r: 0.0)
        generate_lands()
        assert len(captured) == 2  # basics + investigation
        assert all(d == project_dir / "lands" / "logs" for d in captured)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestMakeNonbasicCard:
    def test_rare_from_scratch(self):
        card = _make_nonbasic_card(_DUAL, "TST")
        assert card.rarity.value == "rare"
        assert card.is_reprint is False
        assert card.collector_number == "L-06"
        assert card.card_types == ["Land"]
        assert card.color_identity == [Color.WHITE, Color.BLUE]


class TestLoadReprintSummary:
    def test_absent_file_is_graceful(self, tmp_path: Path):
        assert "no reprints" in _load_reprint_summary(tmp_path).lower()

    def test_summarizes_selections(self, tmp_path: Path):
        (tmp_path / "reprint_selection.json").write_text(
            json.dumps(
                {
                    "selections": [
                        {
                            "candidate": {
                                "name": "Evolving Wilds",
                                "type_line": "Land",
                                "role": "fixing",
                            }
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        out = _load_reprint_summary(tmp_path)
        assert "Evolving Wilds" in out and "fixing" in out


class TestInvestigationPrompt:
    def test_includes_context_slots_and_reprints(self):
        context = {"setting": "S", "mechanics": "M", "archetypes": "A", "constraints": "C"}
        slots = [{"slot_id": "1", "text": "White common creature"}]
        system, ctx_block, user = _build_investigation_prompt(
            {"name": "Test"}, context, slots, "- Evolving Wilds (Land · fixing)"
        )
        # Static persona -> system block #1; set framing -> cached context block #2;
        # per-run dynamic content (slots + placed reprints) -> the user turn.
        assert "FINAL call" in system
        assert "S" in ctx_block and "M" in ctx_block
        assert "White common creature" in user
        assert "Evolving Wilds" in user


class TestBasicsPrompt:
    def test_splits_static_context_from_trigger(self):
        context = {"setting": "A drowned archipelago.", "constraints": "No planeswalkers."}
        system, ctx_block, user = _build_basics_prompt({"name": "Atoll"}, context)
        # Persona + output spec -> system block #1.
        assert "art director" in system
        assert "art_scenes" in system
        # Setting + constraints -> cached context block #2.
        assert "A drowned archipelago." in ctx_block
        assert "No planeswalkers." in ctx_block
        # User turn is a short trigger; the setting is not duplicated there.
        assert "create_basic_lands" in user
        assert "A drowned archipelago." not in user
