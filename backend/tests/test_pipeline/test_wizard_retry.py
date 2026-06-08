"""Tests for the FAILED-stage retry path.

Covers the HTTP endpoint ``POST /api/wizard/instance/retry`` (reset a failed
stage in place + kick the engine) and the engine method it exposes,
``PipelineEngine.retry_current`` (FAILED -> PENDING -> run). The endpoint stubs
``threading.Thread`` so the real loop never runs; the engine test stubs
``run`` so only the reset is observed.
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mtgai.pipeline import server as pipeline_server
from mtgai.pipeline.engine import PipelineEngine, load_state, save_state
from mtgai.pipeline.events import EventBus
from mtgai.pipeline.models import (
    PipelineConfig,
    PipelineState,
    PipelineStatus,
    StageStatus,
    create_pipeline_state,
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


def _seed_failed_state(failed: str = "finalize") -> PipelineState:
    """A backbone run that crashed on ``failed``: every backbone stage up to and
    including ``failed`` exists, all COMPLETED except ``failed`` which is FAILED,
    with ``current_instance_id`` left pointing at it and overall_status FAILED."""
    state = create_pipeline_state(PipelineConfig(set_code="ABC", set_name="ABC", set_size=20))
    hit = False
    for s in state.stages:
        if s.instance_id == failed:
            s.status = StageStatus.FAILED
            s.progress.error_message = "boom"
            hit = True
            break
        s.status = StageStatus.COMPLETED
    assert hit, f"{failed!r} not in backbone"
    state.current_instance_id = failed
    state.overall_status = PipelineStatus.FAILED
    save_state(state)
    return state


def _seed_completed_state() -> PipelineState:
    state = create_pipeline_state(PipelineConfig(set_code="ABC", set_name="ABC", set_size=20))
    for s in state.stages:
        s.status = StageStatus.COMPLETED
    state.current_instance_id = state.stages[-1].instance_id
    state.overall_status = PipelineStatus.COMPLETED
    save_state(state)
    return state


# ---------------------------------------------------------------------------
# POST /api/wizard/instance/retry
# ---------------------------------------------------------------------------


def test_retry_unknown_instance_400(client, no_thread_start):
    _make_set()
    _seed_failed_state()
    resp = client.post("/api/wizard/instance/retry", json={"instance_id": "finalize.9"})
    assert resp.status_code == 400
    assert "Unknown instance" in resp.json()["error"]


def test_retry_non_failed_instance_400(client, no_thread_start):
    _make_set()
    _seed_failed_state()
    resp = client.post("/api/wizard/instance/retry", json={"instance_id": "mechanics"})
    assert resp.status_code == 400
    assert "not failed" in resp.json()["error"]


def test_retry_409_when_engine_running(client):
    _make_set()
    state = _seed_failed_state()
    pipeline_server._engine = types.SimpleNamespace(is_running=True, state=state)
    resp = client.post("/api/wizard/instance/retry", json={"instance_id": "finalize"})
    assert resp.status_code == 409


def test_retry_409_when_extraction_running(client, no_thread_start):
    _make_set()
    _seed_failed_state()
    extraction_run.start_run("ABC")
    resp = client.post("/api/wizard/instance/retry", json={"instance_id": "finalize"})
    assert resp.status_code == 409


def test_retry_no_failed_stage_400(client, no_thread_start):
    _make_set()
    _seed_completed_state()
    resp = client.post("/api/wizard/instance/retry", json={})
    assert resp.status_code == 400
    assert "No failed stage" in resp.json()["error"]


def test_retry_success_kicks_engine(client, no_thread_start):
    _make_set()
    _seed_failed_state()
    resp = client.post("/api/wizard/instance/retry", json={"instance_id": "finalize"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["engine_started"] is True
    assert data["navigate_to"] == "/pipeline/finalize"
    assert len(no_thread_start) == 1
    # The thread runs the engine's retry_current (not the plain run loop).
    assert no_thread_start[0]._kwargs["target"] == pipeline_server._engine.retry_current
    reloaded = load_state()
    assert reloaded is not None
    assert reloaded.current_instance_id == "finalize"


def test_retry_defaults_to_current_failed_stage(client, no_thread_start):
    _make_set()
    _seed_failed_state("card_gen")
    resp = client.post("/api/wizard/instance/retry", json={})
    assert resp.status_code == 200
    assert resp.json()["navigate_to"] == "/pipeline/card_gen"


# ---------------------------------------------------------------------------
# engine.retry_current
# ---------------------------------------------------------------------------


def test_retry_current_resets_failed_to_pending(monkeypatch):
    _make_set()
    state = _seed_failed_state("finalize")
    engine = PipelineEngine(state, EventBus())
    ran: list[bool] = []
    monkeypatch.setattr(engine, "run", lambda: ran.append(True))
    engine.retry_current()
    assert ran == [True]
    target = next(s for s in engine.state.stages if s.instance_id == "finalize")
    assert target.status == StageStatus.PENDING
    assert target.progress.error_message is None


def test_retry_current_noop_when_not_failed(monkeypatch):
    _make_set()
    state = _seed_completed_state()
    engine = PipelineEngine(state, EventBus())
    ran: list[bool] = []
    monkeypatch.setattr(engine, "run", lambda: ran.append(True))
    engine.retry_current()
    assert ran == []  # nothing to retry — no run
