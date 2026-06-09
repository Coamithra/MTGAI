"""HTTP-level tests for the legacy ``POST /api/pipeline/start`` endpoint.

This endpoint predates the wizard's ``/api/wizard/project/start`` +
``_kickoff_pipeline_engine`` flow and is no longer driven by any JS / test /
doc, but it stays mounted (``review/server.py``). The bug it used to carry: it
accepted a PAUSED state and spawned ``engine.run`` over it, re-running the
PAUSED_FOR_REVIEW tip's runner and discarding the human review — exactly the
hazard ``_kickoff_pipeline_engine``'s docstring refuses. It also overwrote a
non-PAUSED/FAILED existing state (orphaned RUNNING / COMPLETED) with a fresh
``create_pipeline_state``, resetting all stage progress.

These tests pin the fixed contract: the legacy endpoint now mirrors the
kickoff helper's guards (PAUSED → 409 use-resume, orphan RUNNING → 409, never
clobber a salvageable existing state, only reuse FAILED for a from-failure
resume, create fresh only when there's no state).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mtgai.pipeline import server as pipeline_server
from mtgai.pipeline.engine import load_state, save_state
from mtgai.pipeline.models import (
    PipelineConfig,
    PipelineState,
    PipelineStatus,
    StageReviewMode,
    StageStatus,
    create_pipeline_state,
)
from mtgai.review.server import app
from mtgai.runtime import ai_lock, extraction_run
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
def no_engine_run(monkeypatch):
    """Stub the engine task spawn so ``engine.run`` never actually fires.

    The endpoint schedules ``asyncio.to_thread(_engine.run)``; capture the
    scheduled callable's name instead of running the heavy engine loop.
    """
    scheduled: list[str] = []

    async def _capture_to_thread(fn, *_a, **_kw):
        scheduled.append(getattr(fn, "__name__", repr(fn)))
        return None

    monkeypatch.setattr(pipeline_server.asyncio, "to_thread", _capture_to_thread)
    return scheduled


def _make_set(code: str) -> None:
    from mtgai.runtime import active_project

    set_dir = ms.OUTPUT_ROOT / "sets" / code
    set_dir.mkdir(parents=True, exist_ok=True)
    active_project.write_active_project(
        active_project.ProjectState(
            set_code=code, settings=ms.ModelSettings(asset_folder=str(set_dir))
        )
    )


def _seed_state(code: str, *, overall_status: PipelineStatus) -> PipelineState:
    state = create_pipeline_state(
        PipelineConfig(set_code=code, set_name=code, set_size=20),
    )
    state.overall_status = overall_status
    save_state(state)
    return state


def _start_body(code: str) -> dict:
    return {"set_code": code, "set_name": code, "set_size": 20}


# ---------------------------------------------------------------------------
# Primary bug: a PAUSED state must NOT be re-run by /start
# ---------------------------------------------------------------------------


def test_start_refuses_paused_state(client, no_engine_run):
    """The core fix: a PAUSED_FOR_REVIEW tip must not be re-run. /start returns
    409 (use /resume) instead of spawning engine.run over the paused stage."""
    _make_set("TST")
    seeded = _seed_state("TST", overall_status=PipelineStatus.PAUSED)
    seeded.stages[0].status = StageStatus.COMPLETED
    seeded.stages[1].status = StageStatus.PAUSED_FOR_REVIEW
    save_state(seeded)

    resp = client.post("/api/pipeline/start", json=_start_body("TST"))
    assert resp.status_code == 409
    assert "paused" in resp.json()["error"].lower()
    # No engine was scheduled — the paused stage is untouched.
    assert no_engine_run == []
    reloaded = load_state()
    assert reloaded is not None
    assert reloaded.overall_status == PipelineStatus.PAUSED
    assert reloaded.stages[1].status == StageStatus.PAUSED_FOR_REVIEW


# ---------------------------------------------------------------------------
# Secondary bug: a non-PAUSED/FAILED state must not be clobbered
# ---------------------------------------------------------------------------


def test_start_refuses_orphan_running_state(client, no_engine_run):
    """A persisted RUNNING with no live engine is an orphan. /start must not
    spawn a second engine over it nor clobber it with a fresh create."""
    _make_set("TST")
    seeded = _seed_state("TST", overall_status=PipelineStatus.RUNNING)
    seeded.stages[0].status = StageStatus.RUNNING
    save_state(seeded)

    resp = client.post("/api/pipeline/start", json=_start_body("TST"))
    assert resp.status_code == 409
    assert "running" in resp.json()["error"].lower()
    assert no_engine_run == []
    reloaded = load_state()
    assert reloaded is not None
    assert reloaded.overall_status == PipelineStatus.RUNNING
    # Progress not reset to a fresh create.
    assert reloaded.stages[0].status == StageStatus.RUNNING


def test_start_does_not_clobber_completed_state(client, no_engine_run):
    """A COMPLETED state must be reused, not overwritten with a fresh create that
    resets every stage's progress."""
    _make_set("TST")
    seeded = _seed_state("TST", overall_status=PipelineStatus.COMPLETED)
    for stage in seeded.stages:
        stage.status = StageStatus.COMPLETED
    save_state(seeded)

    resp = client.post("/api/pipeline/start", json=_start_body("TST"))
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    reloaded = load_state()
    assert reloaded is not None
    # Stages stay COMPLETED — they were reused, not reset to PENDING.
    assert all(s.status == StageStatus.COMPLETED for s in reloaded.stages)


# ---------------------------------------------------------------------------
# Allowed paths: FAILED resume + fresh create
# ---------------------------------------------------------------------------


def test_start_reuses_failed_state_and_applies_review_modes(client, no_engine_run):
    """FAILED is the documented from-failure resume: reuse the existing state
    (keeping completed work) and refresh review modes from the request config."""
    _make_set("TST")
    seeded = _seed_state("TST", overall_status=PipelineStatus.FAILED)
    seeded.stages[0].status = StageStatus.COMPLETED
    seeded.stages[1].status = StageStatus.FAILED
    save_state(seeded)

    body = _start_body("TST")
    body["stage_review_modes"] = {"card_gen": "review"}
    resp = client.post("/api/pipeline/start", json=body)
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert no_engine_run == ["run"]
    reloaded = load_state()
    assert reloaded is not None
    # Completed work preserved.
    assert reloaded.stages[0].status == StageStatus.COMPLETED
    # Review mode applied from the new config.
    card_gen = next(s for s in reloaded.stages if s.stage_id == "card_gen")
    assert card_gen.review_mode == StageReviewMode.REVIEW


def test_start_creates_fresh_state_when_none(client, no_engine_run):
    """No prior state → create a fresh one and spawn the engine."""
    _make_set("TST")
    assert load_state() is None

    resp = client.post("/api/pipeline/start", json=_start_body("TST"))
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert no_engine_run == ["run"]
    reloaded = load_state()
    assert reloaded is not None
    assert reloaded.config.set_code == "TST"


def test_start_409s_when_engine_already_running(client, monkeypatch):
    """A live engine in this process blocks /start regardless of disk state."""
    _make_set("TST")

    class _BusyEngine:
        is_running = True

        def __init__(self) -> None:
            self.state = create_pipeline_state(
                PipelineConfig(set_code="TST", set_name="TST", set_size=20),
            )

    monkeypatch.setattr(pipeline_server, "_engine", _BusyEngine())

    resp = client.post("/api/pipeline/start", json=_start_body("TST"))
    assert resp.status_code == 409
    assert "already running" in resp.json()["error"].lower()
