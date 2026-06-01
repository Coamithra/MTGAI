"""HTTP-level tests for the instance re-run endpoint + per-instance read-routing.

Covers ``POST /api/wizard/instance/rerun`` (restore entry pool -> truncate ->
re-append forward path -> kick engine) and the ``GET /api/wizard/card_gen/state``
``?instance_id=`` read-routing that lets a completed non-tip tab show its own
card-pool snapshot instead of the live (latest) pool.

Engine kickoff is stubbed at ``threading.Thread`` so the real loop never runs;
these tests stay focused on the state manipulation + routing.
"""

from __future__ import annotations

import json
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mtgai.pipeline import history
from mtgai.pipeline import server as pipeline_server
from mtgai.pipeline.engine import load_state, save_state
from mtgai.pipeline.models import (
    PipelineConfig,
    PipelineState,
    PipelineStatus,
    StageState,
    StageStatus,
)
from mtgai.review.server import app
from mtgai.runtime import active_project, ai_lock, extraction_run
from mtgai.settings import model_settings as ms


@pytest.fixture(autouse=True)
def _reset(isolated_output):
    ai_lock.reset_for_tests()
    extraction_run.reset()
    pipeline_server._engine = None
    pipeline_server._engine_task = None
    yield
    ai_lock.reset_for_tests()
    extraction_run.reset()
    pipeline_server._engine = None
    pipeline_server._engine_task = None


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def no_thread_start(monkeypatch):
    started: list = []

    class FakeThread:
        def __init__(self, *_, **kwargs):
            self._kwargs = kwargs

        def start(self):
            started.append(self)

        def join(self, *_a, **_kw):
            return None

    monkeypatch.setattr(pipeline_server.threading, "Thread", FakeThread)
    return started


def _make_set(code: str = "ABC") -> Path:
    set_dir = ms.OUTPUT_ROOT / "sets" / code
    set_dir.mkdir(parents=True, exist_ok=True)
    active_project.write_active_project(
        active_project.ProjectState(
            set_code=code, settings=ms.ModelSettings(asset_folder=str(set_dir))
        )
    )
    return set_dir


def _seed_loop_state() -> PipelineState:
    """A realistic run that bounced once: the full canonical backbone marked
    COMPLETED through finalize, with card_gen.2 + conformance.2 inserted after
    conformance and entry pointers stamped as the engine would. Persisted.

    Using the full backbone (not a hand-picked slice) keeps ``load_state``'s
    reconciler a no-op, so the endpoint sees exactly what we wrote.
    """
    from mtgai.pipeline.models import create_pipeline_state

    state = create_pipeline_state(PipelineConfig(set_code="ABC", set_name="ABC", set_size=20))
    done = {
        "mechanics", "archetypes", "skeleton", "reprints", "lands",
        "card_gen", "conformance", "balance", "ai_review", "finalize",
    }
    entry_by_inst = {
        "card_gen": "lands",
        "conformance": "card_gen",
        "balance": "conformance.2",
        "ai_review": "balance",
        "finalize": "ai_review",
    }
    for s in state.stages:
        if s.stage_id in done:
            s.status = StageStatus.COMPLETED
        if s.instance_id in entry_by_inst:
            s.entry_snapshot_id = entry_by_inst[s.instance_id]
    idx = next(i for i, s in enumerate(state.stages) if s.instance_id == "conformance")
    cg2 = StageState(stage_id="card_gen", instance_id="card_gen.2",
                     display_name="Card Generation 2", status=StageStatus.COMPLETED,
                     entry_snapshot_id="conformance")
    cf2 = StageState(stage_id="conformance", instance_id="conformance.2",
                     display_name="Conformance 2", status=StageStatus.COMPLETED,
                     entry_snapshot_id="card_gen.2")
    state.stages[idx + 1 : idx + 1] = [cg2, cf2]
    state.current_instance_id = "finalize"
    state.overall_status = PipelineStatus.COMPLETED
    save_state(state)
    return state


# ---------------------------------------------------------------------------
# /api/wizard/instance/rerun
# ---------------------------------------------------------------------------


def test_rerun_unknown_instance_400(client, no_thread_start):
    _make_set()
    _seed_loop_state()
    resp = client.post("/api/wizard/instance/rerun", json={"instance_id": "card_gen.9"})
    assert resp.status_code == 400
    assert "Unknown instance" in resp.json()["error"]


def test_rerun_non_rerunnable_stage_400(client, no_thread_start):
    _make_set()
    _seed_loop_state()
    resp = client.post("/api/wizard/instance/rerun", json={"instance_id": "lands"})
    assert resp.status_code == 400
    assert "not re-runnable" in resp.json()["error"]


def test_rerun_409_when_engine_running(client):
    _make_set()
    state = _seed_loop_state()
    # Fake a running engine; .state is read by the per-request banner middleware.
    pipeline_server._engine = types.SimpleNamespace(is_running=True, state=state)
    resp = client.post("/api/wizard/instance/rerun", json={"instance_id": "card_gen.2"})
    assert resp.status_code == 409


def test_rerun_success_truncates_and_kicks(client, no_thread_start):
    _make_set()
    _seed_loop_state()

    resp = client.post("/api/wizard/instance/rerun", json={"instance_id": "card_gen.2"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["engine_started"] is True
    assert data["navigate_to"] == "/pipeline/card_gen.2"
    assert len(no_thread_start) == 1  # engine kicked

    reloaded = load_state()
    assert reloaded is not None
    ids = [s.instance_id for s in reloaded.stages]
    cg2_pos = ids.index("card_gen.2")
    # Past instances (everything up to card_gen.2) keep their COMPLETED status.
    assert all(s.status == StageStatus.COMPLETED for s in reloaded.stages[:cg2_pos])
    assert reloaded.stages[cg2_pos].status == StageStatus.PENDING
    # Forward path re-appended: conformance.2 (sibling survives) then backbone tail.
    assert ids[cg2_pos + 1 : cg2_pos + 5] == ["conformance.2", "balance", "ai_review", "finalize"]
    # The full canonical tail is re-appended (art/render/human).
    assert "rendering" in ids[cg2_pos:] and "human_final_review" in ids[cg2_pos:]
    assert all(s.status == StageStatus.PENDING for s in reloaded.stages[cg2_pos:])
    assert reloaded.current_instance_id == "card_gen.2"
    assert reloaded.overall_status == PipelineStatus.NOT_STARTED


def test_rerun_missing_snapshot_warns(client, no_thread_start):
    _make_set()
    _seed_loop_state()  # no history/ written, so no entry snapshots exist
    resp = client.post("/api/wizard/instance/rerun", json={"instance_id": "card_gen.2"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "warning" in data and "version" in data["warning"].lower()


def test_rerun_requires_instance_id(client, no_thread_start):
    _make_set()
    _seed_loop_state()
    resp = client.post("/api/wizard/instance/rerun", json={})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# card_gen/state per-instance read-routing
# ---------------------------------------------------------------------------


def _write_card(dir_: Path, name: str, body: dict) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / name).write_text(json.dumps(body), encoding="utf-8")


def test_card_gen_state_routes_non_tip_to_history(client):
    asset = _make_set()
    (asset / "skeleton.json").write_text('{"slots": []}', encoding="utf-8")

    # State: card_gen completed, then conformance completed -> conformance is tip.
    config = PipelineConfig(set_code="ABC", set_name="ABC", set_size=20)
    stages = [
        StageState(stage_id="card_gen", instance_id="card_gen", display_name="Card Generation",
                   status=StageStatus.COMPLETED, entry_snapshot_id="lands"),
        StageState(stage_id="conformance", instance_id="conformance", display_name="Conformance",
                   status=StageStatus.COMPLETED, entry_snapshot_id="card_gen"),
    ]
    save_state(PipelineState(config=config, stages=stages, current_instance_id="conformance"))

    # card_gen's own output snapshot vs the (divergent) live pool.
    _write_card(
        history.snapshot_dir("card_gen", asset) / "cards",
        "001_x.json",
        {"collector_number": "001", "name": "FromHistory"},
    )
    _write_card(asset / "cards", "001_x.json", {"collector_number": "001", "name": "FromLive"})

    # Non-tip card_gen tab -> reads its history snapshot.
    by_inst = client.get("/api/wizard/card_gen/state?instance_id=card_gen").json()
    assert [c["name"] for c in by_inst["cards"]] == ["FromHistory"]

    # No instance hint -> live pool (the tip).
    live = client.get("/api/wizard/card_gen/state").json()
    assert [c["name"] for c in live["cards"]] == ["FromLive"]


def test_card_gen_state_tip_reads_live(client):
    asset = _make_set()
    (asset / "skeleton.json").write_text('{"slots": []}', encoding="utf-8")
    config = PipelineConfig(set_code="ABC", set_name="ABC", set_size=20)
    stages = [
        StageState(stage_id="card_gen", instance_id="card_gen", display_name="Card Generation",
                   status=StageStatus.COMPLETED, entry_snapshot_id="lands"),
    ]
    save_state(PipelineState(config=config, stages=stages, current_instance_id="card_gen"))

    _write_card(
        history.snapshot_dir("card_gen", asset) / "cards",
        "001_x.json",
        {"collector_number": "001", "name": "FromHistory"},
    )
    _write_card(asset / "cards", "001_x.json", {"collector_number": "001", "name": "FromLive"})

    # card_gen IS the tip here -> live pool, not the (stale) snapshot.
    data = client.get("/api/wizard/card_gen/state?instance_id=card_gen").json()
    assert [c["name"] for c in data["cards"]] == ["FromLive"]
