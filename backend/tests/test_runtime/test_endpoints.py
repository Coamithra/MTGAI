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


def test_runtime_state_reflects_active_project(client):
    """The active project drives the runtime payload (no query-param override)."""
    from mtgai.runtime import active_project, runtime_state
    from mtgai.settings.model_settings import ModelSettings, apply_settings

    sets_root = runtime_state.SETS_ROOT
    asset_dir = sets_root / "ABC"
    asset_dir.mkdir()
    (asset_dir / "theme.json").write_text(
        json.dumps({"code": "ABC", "name": "Test"}),
        encoding="utf-8",
    )
    apply_settings("ABC", ModelSettings(asset_folder=str(asset_dir)))
    active_project.write_active_set("ABC")

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
    """No project open → 409 (asset folder required), not 404.

    The endpoint can't reach an artifact dir without an open project, so
    the same posture as every other AI/asset-bound endpoint applies:
    return 409 ``no_asset_folder`` so the wizard pushes the user back
    to Project Settings.
    """
    resp = client.get("/api/pipeline/theme/load?set_code=NOPE")
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_asset_folder"


def test_theme_load_404_when_project_open_but_file_missing(client):
    """Project open but theme.json missing → 404."""
    from mtgai.runtime import active_project, runtime_state
    from mtgai.settings.model_settings import ModelSettings, apply_settings

    asset_dir = runtime_state.SETS_ROOT / "TST"
    asset_dir.mkdir(parents=True, exist_ok=True)
    apply_settings("TST", ModelSettings(asset_folder=str(asset_dir)))
    active_project.write_active_set("TST")

    resp = client.get("/api/pipeline/theme/load?set_code=TST")
    assert resp.status_code == 404


def test_theme_load_returns_json(client):
    """A saved theme.json round-trips through /api/pipeline/theme/load."""
    from mtgai.runtime import active_project, runtime_state
    from mtgai.settings.model_settings import ModelSettings, apply_settings

    asset_dir = runtime_state.SETS_ROOT / "TST"
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / "theme.json").write_text(
        json.dumps({"code": "TST", "name": "Test", "constraints": []}),
        encoding="utf-8",
    )
    apply_settings("TST", ModelSettings(asset_folder=str(asset_dir)))
    active_project.write_active_set("TST")

    resp = client.get("/api/pipeline/theme/load?set_code=TST")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == "TST"
    assert data["name"] == "Test"


def test_theme_load_400_on_blank_code(client):
    resp = client.get("/api/pipeline/theme/load?set_code=")
    # Blank set code fails the validation regex -> 400.
    # FastAPI itself may also bounce empty params with 422; accept either.
    assert resp.status_code in (400, 422)


def test_theme_load_400_on_traversal_attempt(client):
    """Set code with path-traversal characters -> 400, never reads disk."""
    resp = client.get("/api/pipeline/theme/load?set_code=../etc")
    assert resp.status_code == 400


def test_theme_save_400_on_invalid_code(client):
    """Save endpoint rejects malformed set codes the same way load does."""
    resp = client.post(
        "/api/pipeline/theme/save",
        json={"code": "../escape", "name": "x"},
    )
    assert resp.status_code == 400


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
