"""HTTP-level tests for the .mtg project-file endpoints.

Covers ``POST /api/project/new``, ``POST /api/project/open``,
``POST /api/project/materialize``, ``GET /api/project/serialize``, and
``POST /api/wizard/project/asset-folder``. The underlying TOML
serialisation helpers are unit-tested in ``test_settings/`` (round-trip
of ``dump_project_toml`` + ``parse_project_toml``).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mtgai.review.server import app
from mtgai.runtime import ai_lock, extraction_run
from mtgai.settings import model_settings as ms


@pytest.fixture(autouse=True)
def _reset(tmp_path, monkeypatch):
    sets_root = tmp_path / "sets"
    settings_dir = tmp_path / "settings"
    sets_root.mkdir(parents=True)
    settings_dir.mkdir(parents=True)

    from mtgai.io import asset_paths
    from mtgai.pipeline import engine
    from mtgai.pipeline import server as pipeline_server
    from mtgai.runtime import active_set, runtime_state

    monkeypatch.setattr(runtime_state, "SETS_ROOT", sets_root)
    monkeypatch.setattr(runtime_state, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(engine, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(pipeline_server, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(active_set, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(active_set, "SETS_ROOT", sets_root)
    monkeypatch.setattr(asset_paths, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(asset_paths, "SETS_ROOT", sets_root)

    monkeypatch.setattr(ms, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(ms, "SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(ms, "SETS_DIR", sets_root)
    monkeypatch.setattr(ms, "GLOBAL_TOML", settings_dir / "global.toml")
    monkeypatch.setattr(ms, "LEGACY_CURRENT_TOML", settings_dir / "current.toml")

    active_set.clear_active_set()
    ms.invalidate_cache()
    ai_lock.reset_for_tests()
    extraction_run.reset()
    yield
    active_set.clear_active_set()
    ms.invalidate_cache()
    ai_lock.reset_for_tests()
    extraction_run.reset()


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# .mtg TOML round-trip
# ---------------------------------------------------------------------------


def test_dump_then_parse_round_trips_all_fields():
    settings = ms.ModelSettings(
        set_params=ms.SetParams(set_name="Round Trip", set_size=42, mechanic_count=4),
        theme_input=ms.ThemeInputSource(
            kind="pdf", filename="src.pdf", upload_id="abc", char_count=2048
        ),
        asset_folder="C:/proj/round-trip",
        break_points={"human_card_review": "auto"},
        effort_overrides={"card_gen": "high"},
    )
    text = ms.dump_project_toml("RT", settings)
    code, parsed = ms.parse_project_toml(text)
    assert code == "RT"
    assert parsed.set_params.model_dump() == settings.set_params.model_dump()
    assert parsed.theme_input.model_dump() == settings.theme_input.model_dump()
    assert parsed.asset_folder == settings.asset_folder
    assert parsed.break_points == settings.break_points
    assert parsed.effort_overrides == settings.effort_overrides
    assert parsed.llm_assignments == settings.llm_assignments


def test_parse_rejects_missing_set_code():
    with pytest.raises(ValueError, match="set_code"):
        ms.parse_project_toml("[set_params]\nset_name = 'X'\n")


def test_parse_rejects_future_version():
    text = 'mtg_file_version = 999\nset_code = "TST"\n'
    with pytest.raises(ValueError, match="Unsupported"):
        ms.parse_project_toml(text)


# ---------------------------------------------------------------------------
# POST /api/project/new
# ---------------------------------------------------------------------------


def test_new_returns_blank_draft_payload(client):
    resp = client.post("/api/project/new", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    draft = data["draft"]
    assert draft["set_code"] == ""
    assert draft["set_params"]["set_name"] == ""
    assert draft["theme_input"]["kind"] == "none"
    assert draft["asset_folder"] == ""
    assert draft["pipeline_started"] is False
    assert isinstance(draft["llm_models"], list)
    assert isinstance(draft["break_points"], list)
    # Default-preset assignments populated so the dropdowns aren't empty.
    assert "card_gen" in draft["llm_assignments"]


def test_new_clears_active_set_pointer(client):
    from mtgai.runtime.active_set import read_active_set, write_active_set

    (ms.SETS_DIR / "OLD").mkdir()
    write_active_set("OLD")
    assert read_active_set() == "OLD"
    resp = client.post("/api/project/new", json={})
    assert resp.status_code == 200
    assert read_active_set() is None


# ---------------------------------------------------------------------------
# POST /api/project/open
# ---------------------------------------------------------------------------


def test_open_creates_set_dir_and_activates(client):
    settings = ms.ModelSettings(
        set_params=ms.SetParams(set_name="Open Test", set_size=80, mechanic_count=2),
        asset_folder="D:/assets/open-test",
    )
    text = ms.dump_project_toml("OPN", settings)
    resp = client.post("/api/project/open", json={"toml": text})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["set_code"] == "OPN"

    from mtgai.runtime.active_set import read_active_set

    assert read_active_set() == "OPN"
    assert (ms.SETS_DIR / "OPN" / "settings.toml").exists()
    loaded = ms.get_settings("OPN")
    assert loaded.set_params.set_size == 80
    assert loaded.asset_folder == "D:/assets/open-test"


def test_open_rejects_empty_body(client):
    resp = client.post("/api/project/open", json={})
    assert resp.status_code == 400


def test_open_rejects_invalid_toml(client):
    resp = client.post("/api/project/open", json={"toml": "not valid toml ["})
    assert resp.status_code == 400


def test_open_rejects_missing_set_code(client):
    text = "[set_params]\nset_name = 'X'\n"
    resp = client.post("/api/project/open", json={"toml": text})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/project/materialize
# ---------------------------------------------------------------------------


def test_materialize_creates_dir_and_returns_mtg_toml(client):
    body = {
        "set_code": "MAT",
        "set_params": {"set_name": "Materialised", "set_size": 60, "mechanic_count": 3},
        "theme_input": {"kind": "none"},
        "asset_folder": "E:/proj/mat",
        "llm_assignments": {"card_gen": "opus"},
        "image_assignments": {"art_gen": "flux-local"},
        "effort_overrides": {},
        "break_points": {},
    }
    resp = client.post("/api/project/materialize", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["set_code"] == "MAT"
    assert "mtg_toml" in data
    # The TOML the client writes must round-trip back through parse.
    code, parsed = ms.parse_project_toml(data["mtg_toml"])
    assert code == "MAT"
    assert parsed.set_params.set_name == "Materialised"
    assert parsed.asset_folder == "E:/proj/mat"
    # Settings.toml on disk holds the same shape.
    assert (ms.SETS_DIR / "MAT" / "settings.toml").exists()
    loaded = ms.get_settings("MAT")
    assert loaded.set_params.set_size == 60
    # Active set follows.
    from mtgai.runtime.active_set import read_active_set

    assert read_active_set() == "MAT"


def test_materialize_rejects_invalid_set_code(client):
    body = {
        "set_code": "lowercase",  # rejected by SET_CODE_RE
        "set_params": {"set_name": "X", "set_size": 60, "mechanic_count": 3},
        "theme_input": {"kind": "none"},
        "asset_folder": "",
        "llm_assignments": {},
        "image_assignments": {},
        "effort_overrides": {},
        "break_points": {},
    }
    resp = client.post("/api/project/materialize", json=body)
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/project/serialize
# ---------------------------------------------------------------------------


def test_serialize_returns_mtg_toml_for_active_set(client):
    # Materialise then serialise — the round-trip must match.
    body = {
        "set_code": "SER",
        "set_params": {"set_name": "Serialised", "set_size": 75, "mechanic_count": 5},
        "theme_input": {"kind": "none"},
        "asset_folder": "F:/proj/ser",
        "llm_assignments": {},
        "image_assignments": {},
        "effort_overrides": {},
        "break_points": {},
    }
    client.post("/api/project/materialize", json=body)
    resp = client.get("/api/project/serialize?set_code=SER")
    assert resp.status_code == 200
    data = resp.json()
    code, parsed = ms.parse_project_toml(data["mtg_toml"])
    assert code == "SER"
    assert parsed.set_params.set_size == 75
    assert parsed.asset_folder == "F:/proj/ser"


def test_serialize_400s_when_no_project_open(client):
    resp = client.get("/api/project/serialize")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/wizard/project/asset-folder
# ---------------------------------------------------------------------------


def test_asset_folder_save_persists_to_settings(client):
    # Materialise a set so settings.toml exists.
    client.post(
        "/api/project/materialize",
        json={
            "set_code": "AF1",
            "set_params": {"set_name": "Folder", "set_size": 60, "mechanic_count": 3},
            "theme_input": {"kind": "none"},
            "asset_folder": "",
            "llm_assignments": {},
            "image_assignments": {},
            "effort_overrides": {},
            "break_points": {},
        },
    )
    resp = client.post(
        "/api/wizard/project/asset-folder",
        json={"set_code": "AF1", "asset_folder": "G:/new/folder"},
    )
    assert resp.status_code == 200
    assert resp.json()["asset_folder"] == "G:/new/folder"
    loaded = ms.get_settings("AF1")
    assert loaded.asset_folder == "G:/new/folder"


def test_asset_folder_rejects_non_string(client):
    client.post(
        "/api/project/materialize",
        json={
            "set_code": "AF2",
            "set_params": {"set_name": "F2", "set_size": 60, "mechanic_count": 3},
            "theme_input": {"kind": "none"},
            "asset_folder": "",
            "llm_assignments": {},
            "image_assignments": {},
            "effort_overrides": {},
            "break_points": {},
        },
    )
    resp = client.post(
        "/api/wizard/project/asset-folder",
        json={"set_code": "AF2", "asset_folder": 123},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Project-switch lifecycle (AI-busy guard on /api/project/{new,open,materialize})
# ---------------------------------------------------------------------------


def _materialise_body(set_code: str) -> dict:
    return {
        "set_code": set_code,
        "set_params": {"set_name": "X", "set_size": 60, "mechanic_count": 3},
        "theme_input": {"kind": "none"},
        "asset_folder": "",
        "llm_assignments": {},
        "image_assignments": {},
        "effort_overrides": {},
        "break_points": {},
    }


def test_new_returns_409_when_ai_busy(client):
    """No force=true while an AI action holds the lock -> 409 + busy payload."""
    assert ai_lock.try_acquire("Theme extraction") is True
    try:
        resp = client.post("/api/project/new", json={})
        assert resp.status_code == 409
        body = resp.json()
        assert body["running"] is True
        assert body["running_action"] == "Theme extraction"
    finally:
        ai_lock.release()


def test_new_with_force_cancels_and_proceeds(client, monkeypatch):
    """force=true -> request_cancel + drain + clear pointer."""
    from mtgai.runtime import active_set as active_set_mod

    (ms.SETS_DIR / "OLD").mkdir()
    active_set_mod.write_active_set("OLD")

    assert ai_lock.try_acquire("Theme extraction") is True
    cancel_calls = {"n": 0}
    real_cancel = ai_lock.request_cancel

    def _spy() -> bool:
        cancel_calls["n"] += 1
        result = real_cancel()
        ai_lock.release()  # simulate the long-running stage winding down
        return result

    monkeypatch.setattr(ai_lock, "request_cancel", _spy)

    resp = client.post("/api/project/new", json={"force": True})
    assert resp.status_code == 200
    assert cancel_calls["n"] == 1
    assert active_set_mod.read_active_set() is None


def test_new_proceeds_on_drain_timeout(client, monkeypatch):
    """When the lock won't release in time, we still proceed (and log)."""
    from mtgai.runtime import active_set as active_set_mod

    assert ai_lock.try_acquire("Stuck action") is True
    try:
        monkeypatch.setattr(active_set_mod, "await_lock_release", lambda *a, **kw: False)
        resp = client.post("/api/project/new", json={"force": True})
        assert resp.status_code == 200
    finally:
        ai_lock.release()


def test_open_returns_409_when_ai_busy(client):
    settings = ms.ModelSettings(
        set_params=ms.SetParams(set_name="X", set_size=60, mechanic_count=3),
    )
    text = ms.dump_project_toml("OPN", settings)
    assert ai_lock.try_acquire("Card generation") is True
    try:
        resp = client.post("/api/project/open", json={"toml": text})
        assert resp.status_code == 409
        assert resp.json()["running_action"] == "Card generation"
    finally:
        ai_lock.release()


def test_open_with_force_proceeds(client, monkeypatch):
    settings = ms.ModelSettings(
        set_params=ms.SetParams(set_name="X", set_size=60, mechanic_count=3),
    )
    text = ms.dump_project_toml("OPN", settings)
    assert ai_lock.try_acquire("Card generation") is True

    real_cancel = ai_lock.request_cancel

    def _spy() -> bool:
        result = real_cancel()
        ai_lock.release()
        return result

    monkeypatch.setattr(ai_lock, "request_cancel", _spy)

    resp = client.post("/api/project/open", json={"toml": text, "force": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["set_code"] == "OPN"


def test_materialize_returns_409_when_ai_busy(client):
    assert ai_lock.try_acquire("Background work") is True
    try:
        resp = client.post("/api/project/materialize", json=_materialise_body("MAT"))
        assert resp.status_code == 409
    finally:
        ai_lock.release()


def test_materialize_with_force_proceeds(client, monkeypatch):
    assert ai_lock.try_acquire("Background work") is True

    real_cancel = ai_lock.request_cancel

    def _spy() -> bool:
        result = real_cancel()
        ai_lock.release()
        return result

    monkeypatch.setattr(ai_lock, "request_cancel", _spy)

    resp = client.post(
        "/api/project/materialize",
        json={**_materialise_body("MAT"), "force": True},
    )
    assert resp.status_code == 200, resp.text
