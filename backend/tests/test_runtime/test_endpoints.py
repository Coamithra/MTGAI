"""HTTP-level smoke tests for the runtime / theme endpoints.

The unit tests in ``test_runtime_state.py`` and ``test_extraction_run.py``
cover the underlying logic; these tests ensure the FastAPI wiring
returns the right shapes / status codes.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from mtgai.review.server import app
from mtgai.runtime import ai_lock, extraction_run


@pytest.fixture(autouse=True)
def _reset(isolated_output):
    """Per-test reset of run-state singletons.

    ``isolated_output`` (from :mod:`tests.conftest`) handles the full
    artifact-path patching chain; this wrapper just resets the AI lock
    and extraction-run state that this test module exercises.
    """
    ai_lock.reset_for_tests()
    extraction_run.reset()
    yield
    ai_lock.reset_for_tests()
    extraction_run.reset()


@pytest.fixture
def client():
    return TestClient(app)


def test_runtime_state_idle(client, monkeypatch):
    """No project loaded → ``active_set`` is null + theme/pipeline blank."""
    monkeypatch.delenv("MTGAI_REVIEW_SET", raising=False)
    resp = client.get("/api/runtime/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_set"] is None
    assert data["ai_lock"]["running"] is False
    assert data["active_runs"] == {}
    assert data["pipeline"] is None
    assert data["theme"] is None


def test_runtime_state_reflects_active_project(client, isolated_output):
    """The active project drives the runtime payload (no query-param override)."""
    from mtgai.runtime import active_project
    from mtgai.settings.model_settings import ModelSettings

    asset_dir = isolated_output / "ABC"
    asset_dir.mkdir()
    (asset_dir / "theme.json").write_text(
        json.dumps({"code": "ABC", "name": "Test"}),
        encoding="utf-8",
    )
    active_project.write_active_project(
        active_project.ProjectState(
            set_code="ABC", settings=ModelSettings(asset_folder=str(asset_dir))
        )
    )

    resp = client.get("/api/runtime/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_set"] == "ABC"
    assert data["theme"]["code"] == "ABC"


def test_runtime_state_reflects_active_extraction(client):
    """A running extraction run shows up under active_runs."""
    extraction_run.start_run("upload-1")
    try:
        resp = client.get("/api/runtime/state")
        assert resp.status_code == 200
        data = resp.json()
        assert "theme_extraction" in data["active_runs"]
        assert data["active_runs"]["theme_extraction"]["upload_id"] == "upload-1"
    finally:
        extraction_run.mark_done("completed")


def test_theme_load_404_when_missing(client):
    """No project open → 409 ``no_active_project``.

    The endpoint can't reach an artifact dir without an open project, so
    the same posture as every other wizard endpoint applies: return 409
    so the client knows to push the user back to New / Open instead of
    treating the path as a 404 to retry.
    """
    resp = client.get("/api/pipeline/theme/load?set_code=NOPE")
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_active_project"


def test_theme_load_404_when_project_open_but_file_missing(client, isolated_output):
    """Project open but theme.json missing → 404."""
    from mtgai.runtime import active_project
    from mtgai.settings.model_settings import ModelSettings

    asset_dir = isolated_output / "TST"
    asset_dir.mkdir(parents=True, exist_ok=True)
    active_project.write_active_project(
        active_project.ProjectState(
            set_code="TST", settings=ModelSettings(asset_folder=str(asset_dir))
        )
    )

    resp = client.get("/api/pipeline/theme/load?set_code=TST")
    assert resp.status_code == 404


def test_theme_load_returns_json(client, isolated_output):
    """A saved theme.json round-trips through /api/pipeline/theme/load."""
    from mtgai.runtime import active_project
    from mtgai.settings.model_settings import ModelSettings

    asset_dir = isolated_output / "TST"
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / "theme.json").write_text(
        json.dumps({"code": "TST", "name": "Test", "constraints": []}),
        encoding="utf-8",
    )
    active_project.write_active_project(
        active_project.ProjectState(
            set_code="TST", settings=ModelSettings(asset_folder=str(asset_dir))
        )
    )

    resp = client.get("/api/pipeline/theme/load?set_code=TST")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == "TST"
    assert data["name"] == "Test"


def test_theme_load_409_when_no_project_open(client):
    """Theme/load now reads the active project — 409 ``no_active_project`` when none.

    Set code is no longer a query param; any stray ``?set_code=...`` is
    ignored. The endpoint only cares about the in-memory pointer.
    """
    resp = client.get("/api/pipeline/theme/load")
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_active_project"


def test_theme_save_409_when_no_project_open(client):
    """Theme/save mirrors theme/load — 409 when no project is open."""
    resp = client.post(
        "/api/pipeline/theme/save",
        json={"name": "x"},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_active_project"


def test_extract_stream_404_for_missing_upload(client):
    """Fresh-start path with no upload returns 404."""
    resp = client.get("/api/pipeline/theme/extract-stream?upload_id=does-not-exist")
    assert resp.status_code == 404


def test_extract_stream_busy_when_other_action_held(client):
    """Different AI action holds the lock -> 409 with busy payload."""
    assert ai_lock.try_acquire("Some other action") is True
    try:
        resp = client.get("/api/pipeline/theme/extract-stream?upload_id=anything")
        assert resp.status_code == 409
        body = resp.json()
        assert body["running"] is True
        assert body["running_action"] == "Some other action"
    finally:
        ai_lock.release()


def test_extract_stream_reattach_replays_events(client):
    """Subscriber to an active run gets replayed events (full SSE
    round-trip via TestClient)."""
    extraction_run.start_run("upload-reattach")
    extraction_run.append_event({"type": "theme_chunk", "text": "hello"})
    extraction_run.append_event({"type": "theme_chunk", "text": "world"})
    extraction_run.mark_done("completed")
    # After mark_done, late subscribers replay the events plus get the
    # sentinel, so the SSE stream closes cleanly during the test.

    with client.stream("GET", "/api/pipeline/theme/extract-stream?upload_id=upload-reattach") as r:
        assert r.status_code == 200
        body_chunks = []
        for chunk in r.iter_text():
            body_chunks.append(chunk)
            if len(body_chunks) > 50:
                break  # safety
        body = "".join(body_chunks)
        # Both replayed events should appear in the SSE body.
        assert '"text": "hello"' in body
        assert '"text": "world"' in body
