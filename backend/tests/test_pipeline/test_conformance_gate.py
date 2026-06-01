"""The merged Conformance & Interactions gate + its truncation-retry helper.

Covers ``analysis.gate_common.generate_gate_tool`` (retries a truncated local
response, bumping temperature; raises after exhausting retries) and
``pipeline.stages.run_conformance`` (runs both LLM steps, combines findings into
per-step artifacts, flags each step's cards for regen, and bounces to card_gen).
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

from mtgai.analysis import gate_common
from mtgai.analysis.models import ConformanceFinding, InteractionFlag
from mtgai.generation.token_utils import OutputTruncatedError
from mtgai.pipeline import stages as stages_mod
from mtgai.runtime import active_project
from mtgai.settings.model_settings import ModelSettings

# ----------------------------------------------------------------------
# generate_gate_tool — truncation retry
# ----------------------------------------------------------------------


def test_generate_gate_tool_retries_then_succeeds(monkeypatch):
    temps: list[float] = []

    def fake(**kwargs):
        temps.append(kwargs["temperature"])
        if len(temps) < 2:
            raise OutputTruncatedError("trunc", eval_count=10, num_predict=10)
        return {"result": {"ok": True}}

    monkeypatch.setattr(gate_common, "generate_with_tool", fake)
    out = gate_common.generate_gate_tool(base_temperature=0.2, system_prompt="s", user_prompt="u")
    assert out == {"result": {"ok": True}}
    # First attempt at the base temp; the retry is nudged up to escape the loop.
    assert temps == [pytest.approx(0.2), pytest.approx(0.4)]


def test_generate_gate_tool_raises_after_exhausting_retries(monkeypatch):
    attempts = [0]

    def fake(**kwargs):
        attempts[0] += 1
        raise OutputTruncatedError("trunc", eval_count=10, num_predict=10)

    monkeypatch.setattr(gate_common, "generate_with_tool", fake)
    with pytest.raises(OutputTruncatedError):
        gate_common.generate_gate_tool(
            base_temperature=0.2, retries=2, system_prompt="s", user_prompt="u"
        )
    assert attempts[0] == 3  # retries + 1


# ----------------------------------------------------------------------
# run_conformance — merged gate
# ----------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path):
    asset_dir = tmp_path / "asset"
    asset_dir.mkdir()
    active_project.write_active_project(
        active_project.ProjectState(
            set_code="ABC", settings=ModelSettings(asset_folder=str(asset_dir))
        )
    )
    yield asset_dir
    active_project.clear_active_project()


class _Emitter:
    def __init__(self):
        self.phases: list[tuple[str, str]] = []

    def phase(self, state, detail=""):
        self.phases.append((state, detail))


def _make_card(slot_id: str):
    from mtgai.models.card import Card

    return Card(
        name=f"Card {slot_id}",
        slot_id=slot_id,
        collector_number=slot_id,
        type_line="Creature — Test",
    )


def test_run_conformance_merges_both_steps(project, monkeypatch):
    from mtgai.io.card_io import load_card, save_card
    from mtgai.models.enums import CardStatus

    save_card(_make_card("W-C-01"), set_dir=project)
    save_card(_make_card("W-C-02"), set_dir=project)

    monkeypatch.setattr(
        "mtgai.analysis.conformance.check_conformance",
        lambda cards, slots: (
            [ConformanceFinding(slot_id="W-C-01", card_name="Card W-C-01", reason="wrong color")],
            "conformance analysis",
            0.01,
        ),
    )
    monkeypatch.setattr(
        "mtgai.analysis.interactions.analyze_interactions",
        lambda cards, mechanics: (
            [
                InteractionFlag(
                    enabler_slot_id="W-C-02",
                    reason="infinite loop with X",
                    replacement_constraint="no free untap",
                )
            ],
            "interaction analysis",
            0.02,
        ),
    )
    monkeypatch.setattr(stages_mod, "make_poller", lambda *a, **k: contextlib.nullcontext())

    result = stages_mod.run_conformance(None, _Emitter())

    assert result.success is True
    assert result.rerun_from == "card_gen"
    assert result.cost_usd == pytest.approx(0.03)

    steps = result.artifacts["steps"]
    assert [s["id"] for s in steps] == ["conformance", "interactions"]
    conf, inter = steps
    assert conf["flagged"][0]["slot_id"] == "W-C-01"
    assert conf["flagged"][0]["card_name"] == "Card W-C-01"
    assert conf["passed"] is False
    assert inter["flagged"][0]["slot_id"] == "W-C-02"
    assert "no free untap" in inter["flagged"][0]["reason"]
    assert inter["passed"] is False

    # Both cards persisted as flagged-for-regen by the merged stage.
    flagged_slots = {f["slot_id"] for f in result.artifacts["flagged"]}
    assert flagged_slots == {"W-C-01", "W-C-02"}
    for p in (project / "cards").glob("*.json"):
        card = load_card(p)
        assert card.flagged_by == "conformance"
        assert card.status == CardStatus.DRAFT
        assert card.regen_reason


def test_run_conformance_clean_pass_advances(project, monkeypatch):
    from mtgai.io.card_io import save_card

    save_card(_make_card("W-C-01"), set_dir=project)
    monkeypatch.setattr(
        "mtgai.analysis.conformance.check_conformance",
        lambda cards, slots: ([], "all conform", 0.0),
    )
    monkeypatch.setattr(
        "mtgai.analysis.interactions.analyze_interactions",
        lambda cards, mechanics: ([], "pool clean", 0.0),
    )
    monkeypatch.setattr(stages_mod, "make_poller", lambda *a, **k: contextlib.nullcontext())

    result = stages_mod.run_conformance(None, _Emitter())

    assert result.rerun_from is None
    assert result.artifacts["passed"] is True
    assert all(s["passed"] for s in result.artifacts["steps"])
    assert result.artifacts["flagged"] == []
