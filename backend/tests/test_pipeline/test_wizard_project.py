"""HTTP-level tests for the Project Settings wizard endpoints.

Covers the eight ``/api/wizard/project*`` routes the kickoff tab calls
on first paint and on every form change. Underlying ``ModelSettings``
schema and migration logic is unit-tested in
``test_settings/test_per_set_settings.py``; these tests pin the FastAPI
contract — payload shape, status codes, and the cascade-clear gate.
"""

from __future__ import annotations

import json

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

    from mtgai.pipeline import engine
    from mtgai.pipeline import server as pipeline_server
    from mtgai.runtime import active_set, runtime_state

    monkeypatch.setattr(runtime_state, "SETS_ROOT", sets_root)
    monkeypatch.setattr(runtime_state, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(engine, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(pipeline_server, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(active_set, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(active_set, "SETS_ROOT", sets_root)
    monkeypatch.setattr(active_set, "_SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(active_set, "_LAST_SET_PATH", settings_dir / "last_set.toml")

    monkeypatch.setattr(ms, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(ms, "SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(ms, "SETS_DIR", sets_root)
    monkeypatch.setattr(ms, "GLOBAL_TOML", settings_dir / "global.toml")
    monkeypatch.setattr(ms, "LEGACY_CURRENT_TOML", settings_dir / "current.toml")

    ms.invalidate_cache()
    ai_lock.reset_for_tests()
    extraction_run.reset()
    yield
    ms.invalidate_cache()
    ai_lock.reset_for_tests()
    extraction_run.reset()


@pytest.fixture
def client():
    return TestClient(app)


def _make_set(code: str, *, theme: dict | None = None) -> None:
    from mtgai.runtime import runtime_state

    set_dir = runtime_state.SETS_ROOT / code
    set_dir.mkdir(parents=True, exist_ok=True)
    if theme is not None:
        (set_dir / "theme.json").write_text(json.dumps(theme), encoding="utf-8")


# ---------------------------------------------------------------------------
# GET /api/wizard/project
# ---------------------------------------------------------------------------


def test_get_project_payload_shape(client):
    _make_set("ASD")
    resp = client.get("/api/wizard/project?set_code=ASD")
    assert resp.status_code == 200
    data = resp.json()
    assert data["set_code"] == "ASD"
    # Default seed: empty name, default size, theme_input=none.
    assert data["set_params"]["set_size"] == 60
    assert data["theme_input"]["kind"] == "none"
    # Break points: every stage rendered; human review stages default to checked-on.
    by_id = {bp["stage_id"]: bp for bp in data["break_points"]}
    for sid in ("human_card_review", "human_art_review", "human_final_review"):
        assert by_id[sid]["review"] is True
    # No always_review field is exposed any more.
    assert "always_review" not in data["break_points"][0]
    # Registry slice is included so the dropdowns can render.
    assert any(m["key"] == "opus" for m in data["llm_models"])
    assert any(m["key"] == "flux-local" for m in data["image_models"])
    assert "recommended" in data["builtin_presets"]
    assert data["pipeline_started"] is False
    assert data["extraction_active"] is False


def test_get_project_payload_picks_up_theme_json_migration(client):
    """A pre-Project-Settings set with name/set_size in theme.json
    surfaces those values in set_params via the seed-time migration."""
    _make_set(
        "ASD",
        theme={"code": "ASD", "name": "Anomalous", "set_size": 80, "mechanic_count": 5},
    )
    resp = client.get("/api/wizard/project?set_code=ASD")
    data = resp.json()
    assert data["set_params"]["set_name"] == "Anomalous"
    assert data["set_params"]["set_size"] == 80
    assert data["set_params"]["mechanic_count"] == 5
    # Existing theme.json => "existing" so Start is enabled.
    assert data["theme_input"]["kind"] == "existing"


def test_get_project_payload_404_for_unknown_set(client):
    resp = client.get("/api/wizard/project?set_code=NOPE")
    assert resp.status_code == 404


def test_get_project_payload_400_for_bad_set_code(client):
    # ``a`` is too short for the regex — fails up-front validation
    # before the directory check (which would otherwise be 404).
    resp = client.get("/api/wizard/project?set_code=a")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/wizard/project/params
# ---------------------------------------------------------------------------


def test_save_params_live_applies_name_and_mechanic_count(client):
    _make_set("ASD")
    resp = client.post(
        "/api/wizard/project/params",
        json={"set_code": "ASD", "set_name": "Avoria", "mechanic_count": 4},
    )
    assert resp.status_code == 200
    settings = ms.get_settings("ASD")
    assert settings.set_params.set_name == "Avoria"
    assert settings.set_params.mechanic_count == 4


def test_save_params_rejects_negative_mechanic_count(client):
    _make_set("ASD")
    resp = client.post(
        "/api/wizard/project/params",
        json={"set_code": "ASD", "mechanic_count": -1},
    )
    assert resp.status_code == 400


def test_save_params_blocks_set_size_change_post_pipeline(client, tmp_path):
    """set_size lives behind the cascade-clear gate once a pipeline-state.json exists."""
    _make_set("ASD")
    # Simulate "pipeline started" by writing a stub state file.
    (tmp_path / "sets" / "ASD" / "pipeline-state.json").write_text("{}", encoding="utf-8")

    resp = client.post(
        "/api/wizard/project/params",
        json={"set_code": "ASD", "set_size": 99},
    )
    assert resp.status_code == 409
    # set_name change is still allowed in the same call.
    resp_ok = client.post(
        "/api/wizard/project/params",
        json={"set_code": "ASD", "set_name": "Updated"},
    )
    assert resp_ok.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/wizard/project/theme-input
# ---------------------------------------------------------------------------


def test_save_theme_input_pdf(client):
    _make_set("ASD")
    resp = client.post(
        "/api/wizard/project/theme-input",
        json={
            "set_code": "ASD",
            "kind": "pdf",
            "upload_id": "abcd1234",
            "filename": "pitch.pdf",
            "char_count": 12345,
        },
    )
    assert resp.status_code == 200
    ti = ms.get_settings("ASD").theme_input
    assert ti.kind == "pdf"
    assert ti.upload_id == "abcd1234"
    assert ti.uploaded_at is not None  # server stamps this


def test_save_theme_input_blocks_kind_change_post_pipeline(client, tmp_path):
    _make_set("ASD")
    (tmp_path / "sets" / "ASD" / "pipeline-state.json").write_text("{}", encoding="utf-8")
    # First commit: existing — works (matches seeded default).
    client.post(
        "/api/wizard/project/theme-input",
        json={"set_code": "ASD", "kind": "none"},
    )
    # Now try to swap kinds — gated.
    resp = client.post(
        "/api/wizard/project/theme-input",
        json={"set_code": "ASD", "kind": "existing"},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# POST /api/wizard/project/breaks
# ---------------------------------------------------------------------------


def test_save_break_toggles_on_and_off(client):
    _make_set("ASD")
    resp_on = client.post(
        "/api/wizard/project/breaks",
        json={"set_code": "ASD", "stage_id": "card_gen", "review": True},
    )
    assert resp_on.status_code == 200
    assert ms.get_settings("ASD").break_points == {"card_gen": "review"}

    resp_off = client.post(
        "/api/wizard/project/breaks",
        json={"set_code": "ASD", "stage_id": "card_gen", "review": False},
    )
    assert resp_off.status_code == 200
    assert ms.get_settings("ASD").break_points == {}


def test_save_break_human_review_stage_can_be_unchecked(client):
    _make_set("ASD")
    resp = client.post(
        "/api/wizard/project/breaks",
        json={"set_code": "ASD", "stage_id": "human_card_review", "review": False},
    )
    assert resp.status_code == 200
    assert ms.get_settings("ASD").break_points["human_card_review"] == "auto"


# ---------------------------------------------------------------------------
# POST /api/wizard/project/models
# ---------------------------------------------------------------------------


def test_save_model_llm(client):
    _make_set("ASD")
    resp = client.post(
        "/api/wizard/project/models",
        json={"set_code": "ASD", "kind": "llm", "stage_id": "card_gen", "value": "haiku"},
    )
    assert resp.status_code == 200
    assert ms.get_settings("ASD").llm_assignments["card_gen"] == "haiku"


def test_save_model_effort_clears_on_empty_value(client):
    _make_set("ASD")
    # Default has card_gen effort = max
    assert ms.get_settings("ASD").effort_overrides.get("card_gen") == "max"
    resp = client.post(
        "/api/wizard/project/models",
        json={"set_code": "ASD", "kind": "effort", "stage_id": "card_gen", "value": ""},
    )
    assert resp.status_code == 200
    assert "card_gen" not in ms.get_settings("ASD").effort_overrides


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------


def test_apply_preset_replaces_models_and_breaks_only(client):
    """Built-in presets travel with model + break-point changes; per-set
    set_params and theme_input are kept."""
    _make_set("ASD")
    # Pre-seed set_params + theme_input.
    settings = ms.get_settings("ASD")
    settings = settings.model_copy(
        update={
            "set_params": ms.SetParams(set_name="MySet", set_size=80),
            "theme_input": ms.ThemeInputSource(kind="pdf", filename="x.pdf"),
        }
    )
    ms.apply_settings("ASD", settings)

    resp = client.post(
        "/api/wizard/project/preset/apply",
        json={"set_code": "ASD", "name": "all-haiku"},
    )
    assert resp.status_code == 200
    after = ms.get_settings("ASD")
    # Models swapped.
    assert after.llm_assignments["card_gen"] == "haiku"
    # Per-set fields preserved.
    assert after.set_params.set_name == "MySet"
    assert after.theme_input.kind == "pdf"


def test_apply_preset_rejects_unknown_name(client):
    _make_set("ASD")
    resp = client.post(
        "/api/wizard/project/preset/apply",
        json={"set_code": "ASD", "name": "does-not-exist"},
    )
    assert resp.status_code == 400


def test_save_profile_excludes_set_params_and_theme_input(client):
    _make_set("ASD")
    settings = ms.get_settings("ASD")
    settings = settings.model_copy(
        update={
            "set_params": ms.SetParams(set_name="MySet", set_size=80),
            "theme_input": ms.ThemeInputSource(kind="pdf", filename="x.pdf"),
            "break_points": {"card_gen": "review"},
        }
    )
    ms.apply_settings("ASD", settings)

    resp = client.post(
        "/api/wizard/project/preset/save",
        json={"set_code": "ASD", "name": "my-template"},
    )
    assert resp.status_code == 200
    import tomllib

    profile_path = ms.SETTINGS_DIR / "my-template.toml"
    with open(profile_path, "rb") as f:
        data = tomllib.load(f)
    assert "set_params" not in data
    assert "theme_input" not in data
    assert data.get("break_points") == {"card_gen": "review"}


# ---------------------------------------------------------------------------
# POST /api/wizard/project/start
# ---------------------------------------------------------------------------


def test_start_with_no_input_returns_400(client):
    _make_set("ASD")
    resp = client.post("/api/wizard/project/start", json={"set_code": "ASD"})
    assert resp.status_code == 400


def test_start_with_existing_skips_extraction(client):
    """kind=existing already has theme.json on disk — Start just navigates."""
    _make_set(
        "ASD",
        theme={"code": "ASD", "name": "X"},  # triggers seed-time migration to "existing"
    )
    resp = client.post("/api/wizard/project/start", json={"set_code": "ASD"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["extraction_started"] is False
    assert body["navigate_to"] == "/pipeline/theme"


def test_start_with_pdf_needs_live_upload(client):
    """If theme_input.upload_id has expired from cache, return 410."""
    _make_set("ASD")
    # Save a theme-input pointing at a non-existent upload_id.
    client.post(
        "/api/wizard/project/theme-input",
        json={
            "set_code": "ASD",
            "kind": "pdf",
            "upload_id": "ghosted0",
            "filename": "x.pdf",
            "char_count": 100,
        },
    )
    resp = client.post("/api/wizard/project/start", json={"set_code": "ASD"})
    assert resp.status_code == 410
