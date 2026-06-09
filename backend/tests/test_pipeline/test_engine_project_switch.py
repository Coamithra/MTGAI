"""Regression: a stale ``_engine`` must not survive a project switch.

``_get_current_state()`` prefers ``_engine.state`` whenever an engine exists —
even an idle one whose run already finished. Before the fix, ``/api/project/{open,
new,materialize}`` never cleared ``_engine``, so after project A's run left the
engine set, switching to project B served A's state from every state-reading
endpoint AND — worse — the first ``_heal_failed_stage`` on B resolved A's stale
state, flipped it, and ``save_state`` wrote it to B's ``pipeline-state.json``
(``save_state`` resolves the path through the *active* project, B) — clobbering
B's config with A's wholesale.

These tests pin that a switch invalidates the in-memory engine so state resolution
falls back to the active project's on-disk ``pipeline-state.json``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mtgai.pipeline import server as pipeline_server
from mtgai.pipeline.engine import PipelineEngine, load_state, save_state
from mtgai.pipeline.models import (
    PipelineConfig,
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


def _settings_for(code: str) -> ms.ModelSettings:
    """A project's settings with a real (tmp) asset folder so state can persist."""
    asset_dir = ms.OUTPUT_ROOT / "sets" / code
    Path(asset_dir).mkdir(parents=True, exist_ok=True)
    return ms.ModelSettings.from_preset("recommended").model_copy(
        update={"asset_folder": str(asset_dir)}
    )


def _pin_project(code: str) -> ms.ModelSettings:
    settings = _settings_for(code)
    active_project.write_active_project(
        active_project.ProjectState(set_code=code, settings=settings)
    )
    return settings


def _stale_engine_for(code: str) -> PipelineEngine:
    """Build an idle engine over project ``code``'s state with a FAILED stage."""
    state = create_pipeline_state(PipelineConfig(set_code=code, set_name=code))
    # Make the first stage FAILED + overall FAILED so a heal would mutate it.
    state.stages[0].status = StageStatus.FAILED
    state.current_instance_id = state.stages[0].instance_id
    state.overall_status = PipelineStatus.FAILED
    return PipelineEngine(state, pipeline_server.event_bus)


def test_open_clears_stale_engine_state(client):
    # Project A finished a run; its engine reference lingers.
    _pin_project("AAA")
    pipeline_server._engine = _stale_engine_for("AAA")
    assert pipeline_server._get_current_state().config.set_code == "AAA"

    # Switch to a freshly-opened project B.
    settings_b = _settings_for("BBB")
    mtg_toml = ms.dump_project_toml("BBB", settings_b)
    resp = client.post("/api/project/open", json={"toml": mtg_toml})
    assert resp.status_code == 200
    assert resp.json()["set_code"] == "BBB"

    # The stale engine reference is gone; state now resolves from B's disk
    # (which has no pipeline-state.json yet → None), never A's in-memory state.
    assert pipeline_server._engine is None
    assert pipeline_server._get_current_state() is None


def test_heal_does_not_write_old_project_state_into_new(client):
    # Project B already has a real on-disk pipeline-state.json.
    settings_b = _pin_project("BBB")
    state_b = create_pipeline_state(PipelineConfig(set_code="BBB", set_name="BBB"))
    save_state(state_b)
    state_path_b = Path(settings_b.asset_folder) / "pipeline-state.json"
    assert state_path_b.exists()

    # Project A's idle engine lingers (FAILED), then we switch to B via open.
    mtg_toml = ms.dump_project_toml("BBB", settings_b)
    # Pin A as active, attach its stale engine, THEN open B.
    _pin_project("AAA")
    pipeline_server._engine = _stale_engine_for("AAA")
    resp = client.post("/api/project/open", json={"toml": mtg_toml})
    assert resp.status_code == 200

    # The first heal on B must operate on B's state (or no-op), never A's.
    pipeline_server._heal_failed_stage("mechanics")

    # B's persisted config must still be B's — not overwritten with A's.
    persisted = load_state()
    assert persisted is not None
    assert persisted.config.set_code == "BBB"


def test_new_clears_stale_engine(client):
    _pin_project("AAA")
    pipeline_server._engine = _stale_engine_for("AAA")
    resp = client.post("/api/project/new", json={})
    assert resp.status_code == 200
    assert pipeline_server._engine is None


def test_materialize_clears_stale_engine(client):
    _pin_project("AAA")
    pipeline_server._engine = _stale_engine_for("AAA")
    asset_dir = ms.OUTPUT_ROOT / "sets" / "CCC"
    asset_dir.mkdir(parents=True, exist_ok=True)
    resp = client.post(
        "/api/project/materialize",
        json={
            "set_code": "CCC",
            "set_params": {"set_name": "Cee", "set_size": 60, "mechanic_count": 2},
            "asset_folder": str(asset_dir),
        },
    )
    assert resp.status_code == 200
    assert pipeline_server._engine is None
