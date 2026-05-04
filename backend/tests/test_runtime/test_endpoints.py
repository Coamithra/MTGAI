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
def _reset(tmp_path, monkeypatch):
    sets_root = tmp_path / "sets"
    sets_root.mkdir(parents=True)

    from mtgai.pipeline import engine
    from mtgai.runtime import runtime_state

    monkeypatch.setattr(runtime_state, "SETS_ROOT", sets_root)
    monkeypatch.setattr(runtime_state, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(engine, "OUTPUT_ROOT", tmp_path)

    ai_lock.reset_for_tests()
    extraction_run.reset()
    yield
    ai_lock.reset_for_tests()
    extraction_run.reset()


@pytest.fixture
def client():
    return TestClient(app)


def test_runtime_state_idle(client, monkeypatch):
    monkeypatch.delenv("MTGAI_REVIEW_SET", raising=False)
    resp = client.get("/api/runtime/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_set"] == "ASD"
    assert data["ai_lock"]["running"] is False
    assert data["active_runs"] == {}
    assert data["pipeline"] is None
    assert data["theme"] is None


def test_runtime_state_with_explicit_set(client, monkeypatch):
    """The set_code query param overrides disk + env resolution."""
    from mtgai.runtime import runtime_state

    sets_root = runtime_state.SETS_ROOT
    set_dir = sets_root / "ABC"
    set_dir.mkdir()
    (set_dir / "theme.json").write_text(
        json.dumps({"code": "ABC", "name": "Test"}),
        encoding="utf-8",
    )

    resp = client.get("/api/runtime/state?set_code=ABC")
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
    resp = client.get("/api/pipeline/theme/load?set_code=NOPE")
    assert resp.status_code == 404


def test_theme_load_returns_json(client, monkeypatch):
    """A saved theme.json round-trips through /api/pipeline/theme/load."""
    from mtgai.pipeline import server as pipeline_server
    from mtgai.runtime import runtime_state

    set_dir = runtime_state.SETS_ROOT / "TST"
    set_dir.mkdir(parents=True, exist_ok=True)
    (set_dir / "theme.json").write_text(
        json.dumps({"code": "TST", "name": "Test", "constraints": []}),
        encoding="utf-8",
    )

    # Redirect the helper to our tmp SETS_ROOT instead of the
    # hard-coded production path. Keeps the validation regex live so
    # we still exercise the 400 path on bad codes.
    real_re = pipeline_server._SET_CODE_RE

    def _patched(set_code):
        code = (set_code or "").strip().upper()
        if not real_re.fullmatch(code):
            return None
        return runtime_state.SETS_ROOT / code / "theme.json"

    monkeypatch.setattr(pipeline_server, "_theme_path", _patched)

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
