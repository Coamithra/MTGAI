"""HTTP-level tests for the wizard advance endpoint + kickoff helper.

Covers ``POST /api/wizard/advance`` and ``_kickoff_pipeline_engine`` —
the two pieces that wire the wizard footer Next-step button (and the
post-extraction auto-advance hook) to the existing pipeline engine.

The tests intentionally avoid running the engine itself: we monkey-patch
``threading.Thread`` so the engine never actually starts, just so we can
assert that the helper *would* have started it and that it persists the
right state on disk + leaves the global ``_engine`` populated.
"""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from mtgai.pipeline import server as pipeline_server
from mtgai.pipeline.engine import save_state
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
def sets_root(isolated_output):
    """Yield the tmp ``sets`` root for tests that need a stable artifact dir."""
    return isolated_output


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def no_thread_start(monkeypatch):
    """Stub :class:`threading.Thread` so engine threads never actually run.

    We're testing the kickoff plumbing — that the helper builds the
    config, persists state, sets the global, and *would* spawn the
    engine — without letting the real engine loop fire and drag in
    every stage runner's heavy dependencies.
    """
    started: list[threading.Thread] = []

    class FakeThread:
        def __init__(self, *_, **kwargs):
            self._target = kwargs.get("target")
            self._kwargs = kwargs

        def start(self):
            started.append(self)

        def join(self, *_a, **_kw):
            return None

    monkeypatch.setattr(pipeline_server.threading, "Thread", FakeThread)
    return started


def _make_set(code: str) -> None:
    """Pin ``code`` as the active project against an asset folder under the tmp tree."""
    from mtgai.runtime import active_project

    set_dir = ms.OUTPUT_ROOT / "sets" / code
    set_dir.mkdir(parents=True, exist_ok=True)
    active_project.write_active_project(
        active_project.ProjectState(
            set_code=code, settings=ms.ModelSettings(asset_folder=str(set_dir))
        )
    )


def _seed_state(code: str, *, overall_status: PipelineStatus) -> PipelineState:
    """Create + persist a pipeline state stub for tests that need one."""
    state = create_pipeline_state(
        PipelineConfig(set_code=code, set_name=code, set_size=20),
    )
    state.overall_status = overall_status
    save_state(state)
    return state


# ---------------------------------------------------------------------------
# _build_pipeline_config_from_settings
# ---------------------------------------------------------------------------


def test_build_config_uses_set_params_and_break_points():
    _make_set("ASD")
    settings = ms.get_active_settings()
    new = settings.model_copy(
        update={
            "set_params": settings.set_params.model_copy(
                update={"set_name": "Astro Drift", "set_size": 35},
            ),
            "break_points": {"card_gen": "review", "skeleton": "auto"},
        }
    )
    ms.apply_settings(new)

    config = pipeline_server._build_pipeline_config_from_settings("ASD")
    assert config.set_code == "ASD"
    assert config.set_name == "Astro Drift"
    assert config.set_size == 35
    # card_gen explicit review; human stages default to review; auto omitted.
    assert config.stage_review_modes["card_gen"] == StageReviewMode.REVIEW
    assert config.stage_review_modes["human_card_review"] == StageReviewMode.REVIEW
    assert config.stage_review_modes["human_art_review"] == StageReviewMode.REVIEW
    assert config.stage_review_modes["human_final_review"] == StageReviewMode.REVIEW
    assert "skeleton" not in config.stage_review_modes


def test_build_config_falls_back_to_set_code_when_name_blank():
    _make_set("XYZ")
    config = pipeline_server._build_pipeline_config_from_settings("XYZ")
    # Default SetParams.set_name is "" — fall back to the code so the
    # engine has a non-empty title to log.
    assert config.set_name == "XYZ"


# ---------------------------------------------------------------------------
# _kickoff_pipeline_engine
# ---------------------------------------------------------------------------


def test_kickoff_creates_state_and_spawns_engine(no_thread_start):
    _make_set("ASD")
    state, err = pipeline_server._kickoff_pipeline_engine("ASD")
    assert err is None
    assert state is not None
    assert state.config.set_code == "ASD"
    assert pipeline_server._engine is not None
    assert pipeline_server._engine.state is state
    # Persisted to disk so a server restart can pick it up.
    from mtgai.pipeline.engine import load_state

    reloaded = load_state()
    assert reloaded is not None
    assert reloaded.config.set_code == "ASD"
    assert len(no_thread_start) == 1


def test_kickoff_refuses_paused_state(no_thread_start):
    """PAUSED needs ``engine.resume`` (which marks the paused stage
    completed first), not a fresh ``engine.run`` — re-entering run on a
    paused state would re-call the runner and discard the human review.
    The advance endpoint routes PAUSED to the resume branch; the helper
    itself rejects it as a defence-in-depth.
    """
    _make_set("ASD")
    seeded = _seed_state("ASD", overall_status=PipelineStatus.PAUSED)
    seeded.stages[0].status = StageStatus.COMPLETED
    seeded.stages[1].status = StageStatus.PAUSED_FOR_REVIEW
    save_state(seeded)

    state, err = pipeline_server._kickoff_pipeline_engine("ASD")
    assert state is None
    assert err is not None
    assert "paused" in err.lower()
    assert len(no_thread_start) == 0


def test_kickoff_reuses_existing_failed_state(no_thread_start):
    _make_set("ASD")
    seeded = _seed_state("ASD", overall_status=PipelineStatus.FAILED)
    seeded.stages[0].status = StageStatus.COMPLETED
    seeded.stages[1].status = StageStatus.FAILED
    save_state(seeded)

    state, err = pipeline_server._kickoff_pipeline_engine("ASD")
    assert err is None
    assert state is not None
    # First stage stays COMPLETED — we didn't create a fresh state on top.
    assert state.stages[0].status == StageStatus.COMPLETED
    assert len(no_thread_start) == 1


class _BusyEngine:
    """Stub engine for "already running" guard tests.

    The banner middleware reads ``_engine.state`` on every request to
    decide whether to render the pipeline banner, so the stub needs a
    ``state`` attribute even though the test only cares about
    ``is_running``.
    """

    is_running = True

    def __init__(self) -> None:
        self.state = create_pipeline_state(
            PipelineConfig(set_code="ASD", set_name="ASD", set_size=20),
        )


def test_kickoff_blocked_when_engine_already_running(monkeypatch):
    _make_set("ASD")
    monkeypatch.setattr(pipeline_server, "_engine", _BusyEngine())

    state, err = pipeline_server._kickoff_pipeline_engine("ASD")
    assert state is None
    assert err == "A pipeline is already running"


def test_kickoff_refuses_orphan_running_disk_state(no_thread_start):
    """A persisted RUNNING with no live engine = orphan; refuse."""
    _make_set("ASD")
    _seed_state("ASD", overall_status=PipelineStatus.RUNNING)

    state, err = pipeline_server._kickoff_pipeline_engine("ASD")
    assert state is None
    assert err is not None
    assert "RUNNING" in err


# ---------------------------------------------------------------------------
# POST /api/wizard/advance
# ---------------------------------------------------------------------------


def test_advance_kicks_off_when_no_state(client, no_thread_start):
    _make_set("ASD")
    resp = client.post("/api/wizard/advance", json={"set_code": "ASD"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    # First non-completed stage is the engine's first stage.
    assert data["next_stage_id"] == "skeleton"
    assert data["navigate_to"] == "/pipeline/skeleton"
    assert pipeline_server._engine is not None
    assert len(no_thread_start) == 1


def test_advance_resumes_when_paused(client, no_thread_start, monkeypatch):
    """PAUSED → ``engine.resume`` is scheduled; no navigate_to."""
    _make_set("ASD")
    state = _seed_state("ASD", overall_status=PipelineStatus.PAUSED)
    state.stages[0].status = StageStatus.COMPLETED
    state.stages[1].status = StageStatus.PAUSED_FOR_REVIEW
    state.current_stage_id = state.stages[1].stage_id
    save_state(state)

    # Capture which engine method gets scheduled (resume vs run vs
    # retry/skip) — the routing contract is what this test pins. Stub
    # to_thread so the captured callable is invoked synchronously and
    # asyncio's default executor doesn't hang TestClient teardown.
    scheduled: list[str] = []

    async def _capture_to_thread(fn, *_a, **_kw):
        scheduled.append(getattr(fn, "__name__", repr(fn)))
        return None

    monkeypatch.setattr(pipeline_server.asyncio, "to_thread", _capture_to_thread)

    resp = client.post("/api/wizard/advance", json={"set_code": "ASD"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    # Resume path doesn't include next_stage_id (would be misleading;
    # _first_pending_stage_id returns the paused stage, not the next
    # one) and doesn't navigate — user stays on the paused tab and SSE
    # handles the next-tab spawn without stealing focus.
    assert "navigate_to" not in data
    assert "next_stage_id" not in data
    assert pipeline_server._engine is not None
    assert scheduled == ["resume"]


def test_advance_paused_refuses_when_engine_already_running(client, monkeypatch):
    """Concurrent advance must not clobber a live ``_engine`` reference.

    Without the guard, a double-click during a brief PAUSED→RUNNING
    transition would replace ``_engine`` mid-flight, orphaning the
    previous daemon thread.
    """
    _make_set("ASD")
    state = _seed_state("ASD", overall_status=PipelineStatus.PAUSED)
    state.stages[0].status = StageStatus.PAUSED_FOR_REVIEW
    save_state(state)

    monkeypatch.setattr(pipeline_server, "_engine", _BusyEngine())

    resp = client.post("/api/wizard/advance", json={"set_code": "ASD"})
    assert resp.status_code == 409
    assert "already running" in resp.json()["error"].lower()


def test_advance_400s_when_failed(client):
    _make_set("ASD")
    state = _seed_state("ASD", overall_status=PipelineStatus.FAILED)
    state.stages[0].status = StageStatus.FAILED
    save_state(state)

    resp = client.post("/api/wizard/advance", json={"set_code": "ASD"})
    assert resp.status_code == 400
    assert "failed" in resp.json()["error"].lower()


def test_advance_400s_when_completed(client):
    _make_set("ASD")
    state = _seed_state("ASD", overall_status=PipelineStatus.COMPLETED)
    save_state(state)

    resp = client.post("/api/wizard/advance", json={"set_code": "ASD"})
    assert resp.status_code == 400


def test_advance_409s_when_no_project_open(client):
    """Endpoints read the active project from in-memory state — without
    one open they 409 with ``no_active_project`` so the wizard can
    bounce the user to New / Open."""
    resp = client.post("/api/wizard/advance", json={})
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_active_project"


def test_advance_accepts_lowercase_set_code(client, no_thread_start):
    """Validator uppercases before checking — lowercase is normalized,
    not rejected. Lock that in so a future stricter validator doesn't
    silently break links the user might have bookmarked.
    """
    _make_set("ASD")
    resp = client.post("/api/wizard/advance", json={"set_code": "asd"})
    assert resp.status_code == 200
    assert resp.json()["next_stage_id"] == "skeleton"


# ---------------------------------------------------------------------------
# _first_pending_stage_id
# ---------------------------------------------------------------------------


def test_first_pending_skips_completed_and_skipped():
    state = create_pipeline_state(
        PipelineConfig(set_code="ASD", set_name="Test", set_size=20),
    )
    state.stages[0].status = StageStatus.COMPLETED
    state.stages[1].status = StageStatus.SKIPPED
    state.stages[2].status = StageStatus.PAUSED_FOR_REVIEW
    assert pipeline_server._first_pending_stage_id(state) == state.stages[2].stage_id


def test_first_pending_returns_none_when_all_done():
    state = create_pipeline_state(
        PipelineConfig(set_code="ASD", set_name="Test", set_size=20),
    )
    for stage in state.stages:
        stage.status = StageStatus.COMPLETED
    assert pipeline_server._first_pending_stage_id(state) is None
