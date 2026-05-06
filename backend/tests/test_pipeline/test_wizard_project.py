"""HTTP-level tests for the Project Settings wizard endpoints.

Covers the eight ``/api/wizard/project*`` routes the kickoff tab calls
on first paint and on every form change. Underlying ``ModelSettings``
schema is unit-tested in ``test_settings/test_per_set_settings.py``;
these tests pin the FastAPI contract — payload shape, status codes, and
the cascade-clear gate.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mtgai.review.server import app
from mtgai.runtime import active_project, ai_lock, extraction_run
from mtgai.settings import model_settings as ms


@pytest.fixture(autouse=True)
def _reset(isolated_output):
    ai_lock.reset_for_tests()
    extraction_run.reset()
    yield
    ai_lock.reset_for_tests()
    extraction_run.reset()


@pytest.fixture
def client():
    return TestClient(app)


def _open_project(
    code: str,
    *,
    asset_dir=None,
    set_params: ms.SetParams | None = None,
    theme_input: ms.ThemeInputSource | None = None,
) -> None:
    """Pin ``code`` as the active project with the given settings overrides.

    By default seeds an asset_folder so the wizard cascade-clear gate
    can resolve ``set_artifact_dir`` for ``pipeline-state.json``-checks.
    Tests that need a missing asset_folder pass ``asset_dir=""``.
    """
    settings = ms.ModelSettings.from_preset("recommended")
    if set_params is not None:
        settings = settings.model_copy(update={"set_params": set_params})
    if theme_input is not None:
        settings = settings.model_copy(update={"theme_input": theme_input})
    if asset_dir is None:
        # Default asset folder under the patched OUTPUT_ROOT so endpoints can
        # resolve set_artifact_dir without bouncing on a 409.
        asset_dir = ms.OUTPUT_ROOT / "sets" / code
    if asset_dir != "":
        from pathlib import Path

        Path(asset_dir).mkdir(parents=True, exist_ok=True)
        settings = settings.model_copy(update={"asset_folder": str(asset_dir)})
    active_project.write_active_project(
        active_project.ProjectState(set_code=code, settings=settings)
    )


# ---------------------------------------------------------------------------
# GET /api/wizard/project
# ---------------------------------------------------------------------------


def test_get_project_payload_shape(client):
    _open_project("ASD")
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


def test_get_project_payload_409_when_no_project_open(client):
    """Endpoint reads from the active project — 409 ``no_active_project`` when none is open.

    Set_code is no longer a query/body param: the server uses the
    in-memory pointer (set by /api/project/{open,materialize}) and
    bounces the client to New / Open via the 409.
    """
    resp = client.get("/api/wizard/project")
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_active_project"


# ---------------------------------------------------------------------------
# POST /api/wizard/project/params
# ---------------------------------------------------------------------------


def test_save_params_live_applies_name_and_mechanic_count(client):
    _open_project("ASD")
    resp = client.post(
        "/api/wizard/project/params",
        json={"set_code": "ASD", "set_name": "Avoria", "mechanic_count": 4},
    )
    assert resp.status_code == 200
    settings = active_project.require_active_project().settings
    assert settings.set_params.set_name == "Avoria"
    assert settings.set_params.mechanic_count == 4


def test_save_params_rejects_negative_mechanic_count(client):
    _open_project("ASD")
    resp = client.post(
        "/api/wizard/project/params",
        json={"set_code": "ASD", "mechanic_count": -1},
    )
    assert resp.status_code == 400


def test_save_params_blocks_set_size_change_post_pipeline(client):
    """set_size lives behind the cascade-clear gate once a pipeline-state.json exists."""
    _open_project("ASD")
    asset_dir = active_project.require_active_project().settings.asset_folder
    from pathlib import Path

    (Path(asset_dir) / "pipeline-state.json").write_text("{}", encoding="utf-8")

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
    _open_project("ASD")
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
    ti = active_project.require_active_project().settings.theme_input
    assert ti.kind == "pdf"
    assert ti.upload_id == "abcd1234"
    assert ti.uploaded_at is not None  # server stamps this


def test_save_theme_input_blocks_kind_change_post_pipeline(client):
    _open_project("ASD")
    asset_dir = active_project.require_active_project().settings.asset_folder
    from pathlib import Path

    (Path(asset_dir) / "pipeline-state.json").write_text("{}", encoding="utf-8")
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
    _open_project("ASD")
    resp_on = client.post(
        "/api/wizard/project/breaks",
        json={"set_code": "ASD", "stage_id": "card_gen", "review": True},
    )
    assert resp_on.status_code == 200
    assert active_project.require_active_project().settings.break_points == {"card_gen": "review"}

    resp_off = client.post(
        "/api/wizard/project/breaks",
        json={"set_code": "ASD", "stage_id": "card_gen", "review": False},
    )
    assert resp_off.status_code == 200
    assert active_project.require_active_project().settings.break_points == {}


def test_save_break_human_review_stage_can_be_unchecked(client):
    _open_project("ASD")
    resp = client.post(
        "/api/wizard/project/breaks",
        json={"set_code": "ASD", "stage_id": "human_card_review", "review": False},
    )
    assert resp.status_code == 200
    assert (
        active_project.require_active_project().settings.break_points["human_card_review"] == "auto"
    )


# ---------------------------------------------------------------------------
# POST /api/wizard/project/models
# ---------------------------------------------------------------------------


def test_save_model_llm(client):
    _open_project("ASD")
    resp = client.post(
        "/api/wizard/project/models",
        json={"set_code": "ASD", "kind": "llm", "stage_id": "card_gen", "value": "haiku"},
    )
    assert resp.status_code == 200
    assert active_project.require_active_project().settings.llm_assignments["card_gen"] == "haiku"


def test_save_model_effort_clears_on_empty_value(client):
    _open_project("ASD")
    # Default has card_gen effort = max
    assert (
        active_project.require_active_project().settings.effort_overrides.get("card_gen") == "max"
    )
    resp = client.post(
        "/api/wizard/project/models",
        json={"set_code": "ASD", "kind": "effort", "stage_id": "card_gen", "value": ""},
    )
    assert resp.status_code == 200
    assert "card_gen" not in active_project.require_active_project().settings.effort_overrides


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------


def test_apply_preset_replaces_models_and_breaks_only(client):
    """Built-in presets travel with model + break-point changes; per-set
    set_params and theme_input are kept."""
    _open_project(
        "ASD",
        set_params=ms.SetParams(set_name="MySet", set_size=80),
        theme_input=ms.ThemeInputSource(kind="pdf", filename="x.pdf"),
    )

    resp = client.post(
        "/api/wizard/project/preset/apply",
        json={"set_code": "ASD", "name": "all-haiku"},
    )
    assert resp.status_code == 200
    after = active_project.require_active_project().settings
    # Models swapped.
    assert after.llm_assignments["card_gen"] == "haiku"
    # Per-set fields preserved.
    assert after.set_params.set_name == "MySet"
    assert after.theme_input.kind == "pdf"


def test_apply_preset_rejects_unknown_name(client):
    _open_project("ASD")
    resp = client.post(
        "/api/wizard/project/preset/apply",
        json={"set_code": "ASD", "name": "does-not-exist"},
    )
    assert resp.status_code == 400


def test_save_profile_excludes_set_params_and_theme_input(client):
    _open_project(
        "ASD",
        set_params=ms.SetParams(set_name="MySet", set_size=80),
        theme_input=ms.ThemeInputSource(kind="pdf", filename="x.pdf"),
    )
    # Layer break_points on top after open.
    settings = active_project.require_active_project().settings
    ms.apply_settings(settings.model_copy(update={"break_points": {"card_gen": "review"}}))

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
    _open_project("ASD")
    resp = client.post("/api/wizard/project/start", json={"set_code": "ASD"})
    assert resp.status_code == 400


def test_start_with_existing_skips_extraction(client):
    """kind=existing already has theme.json on disk — Start just navigates."""
    _open_project("ASD", theme_input=ms.ThemeInputSource(kind="existing"))
    resp = client.post("/api/wizard/project/start", json={"set_code": "ASD"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["extraction_started"] is False
    assert body["navigate_to"] == "/pipeline/theme"


def test_start_with_pdf_needs_live_upload(client):
    """If theme_input.upload_id has expired from cache, return 410."""
    _open_project("ASD")
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
