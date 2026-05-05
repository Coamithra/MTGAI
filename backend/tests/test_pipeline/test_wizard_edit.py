"""HTTP-level tests for the wizard edit-flow cascade endpoints.

Covers ``POST /api/wizard/edit/preview`` and ``POST /api/wizard/edit/accept``
— the §9 cascade-clear flow that lets the user re-run a stage and
discard everything downstream.

Engine kickoff is stubbed at ``threading.Thread`` (same pattern as
``test_wizard_advance``) so the real engine loop never runs and these
tests stay focused on the cascade plumbing: payload shape, status
codes, on-disk artifact removal, pipeline-state.json reset, and
navigation routing.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mtgai.pipeline import server as pipeline_server
from mtgai.pipeline import stages as stages_mod
from mtgai.pipeline.engine import load_state, save_state
from mtgai.pipeline.models import (
    PipelineConfig,
    PipelineState,
    PipelineStatus,
    StageStatus,
    create_pipeline_state,
)
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
    from mtgai.runtime import active_set, runtime_state

    monkeypatch.setattr(runtime_state, "SETS_ROOT", sets_root)
    monkeypatch.setattr(runtime_state, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(engine, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(pipeline_server, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(stages_mod, "OUTPUT_ROOT", tmp_path)
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
    pipeline_server._engine = None
    pipeline_server._engine_task = None
    yield
    ms.invalidate_cache()
    ai_lock.reset_for_tests()
    extraction_run.reset()
    pipeline_server._engine = None
    pipeline_server._engine_task = None


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def no_thread_start(monkeypatch):
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


def _make_set(code: str, *, theme: dict | None = None) -> Path:
    set_dir = pipeline_server.OUTPUT_ROOT / "sets" / code
    set_dir.mkdir(parents=True, exist_ok=True)
    if theme is not None:
        (set_dir / "theme.json").write_text(json.dumps(theme), encoding="utf-8")
    return set_dir


def _seed_state(code: str, *, overall_status: PipelineStatus) -> PipelineState:
    state = create_pipeline_state(
        PipelineConfig(set_code=code, set_name=code, set_size=20),
    )
    state.overall_status = overall_status
    save_state(state)
    return state


# ---------------------------------------------------------------------------
# /api/wizard/edit/preview
# ---------------------------------------------------------------------------


def test_preview_lists_completed_downstream_stages(client):
    _make_set("ASD", theme={"code": "ASD", "name": "Test"})
    state = _seed_state("ASD", overall_status=PipelineStatus.PAUSED)
    state.stages[0].status = StageStatus.COMPLETED
    state.stages[0].progress.completed_items = 60
    state.stages[1].status = StageStatus.COMPLETED
    state.stages[1].progress.completed_items = 5
    state.stages[2].status = StageStatus.PAUSED_FOR_REVIEW
    state.stages[2].progress.completed_items = 6
    save_state(state)

    resp = client.post(
        "/api/wizard/edit/preview",
        json={"set_code": "ASD", "from_stage": "skeleton"},
    )
    assert resp.status_code == 200
    data = resp.json()
    cleared_ids = [c["stage_id"] for c in data["cleared"]]
    # All three non-pending stages reported, in pipeline order.
    assert cleared_ids[:3] == ["skeleton", "reprints", "lands"]
    # Item counts come through.
    assert data["cleared"][0]["item_count"] == 60
    # No theme.json wipe by default.
    assert data["clear_theme_json"] is False


def test_preview_skips_pending_stages(client):
    _make_set("ASD", theme={"code": "ASD"})
    state = _seed_state("ASD", overall_status=PipelineStatus.NOT_STARTED)
    state.stages[0].status = StageStatus.COMPLETED
    save_state(state)

    resp = client.post(
        "/api/wizard/edit/preview",
        json={"set_code": "ASD", "from_stage": "theme"},
    )
    data = resp.json()
    # Only the one COMPLETED stage shows up; PENDING ones are skipped.
    assert [c["stage_id"] for c in data["cleared"]] == ["skeleton"]


def test_preview_clear_theme_json_reflects_disk(client):
    """``clear_theme_json`` only flips on when theme.json actually exists."""
    _make_set("ASD")  # No theme.json
    resp = client.post(
        "/api/wizard/edit/preview",
        json={"set_code": "ASD", "from_stage": "project", "clear_theme_json": True},
    )
    data = resp.json()
    assert data["clear_theme_json"] is False  # nothing on disk to clear

    _make_set("ASD", theme={"code": "ASD"})  # Now theme.json exists
    resp = client.post(
        "/api/wizard/edit/preview",
        json={"set_code": "ASD", "from_stage": "project", "clear_theme_json": True},
    )
    assert resp.json()["clear_theme_json"] is True


def test_preview_400_for_unknown_stage(client):
    _make_set("ASD")
    _seed_state("ASD", overall_status=PipelineStatus.PAUSED)
    resp = client.post(
        "/api/wizard/edit/preview",
        json={"set_code": "ASD", "from_stage": "nonexistent"},
    )
    assert resp.status_code == 400


def test_preview_400_for_missing_from_stage(client):
    _make_set("ASD")
    resp = client.post("/api/wizard/edit/preview", json={"set_code": "ASD"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /api/wizard/edit/accept — cascade clear + state reset
# ---------------------------------------------------------------------------


def test_accept_cascades_artifacts_and_resets_stages(client, no_thread_start):
    """Accepting a Skeleton edit clears skeleton.json, cards/, art/, etc."""
    set_dir = _make_set("ASD", theme={"code": "ASD"})
    (set_dir / "skeleton.json").write_text("{}", encoding="utf-8")
    (set_dir / "reprint_selection.json").write_text("{}", encoding="utf-8")
    cards = set_dir / "cards"
    cards.mkdir()
    (cards / "001_foo.json").write_text("{}", encoding="utf-8")

    state = _seed_state("ASD", overall_status=PipelineStatus.PAUSED)
    state.stages[0].status = StageStatus.COMPLETED  # skeleton
    state.stages[1].status = StageStatus.COMPLETED  # reprints
    state.stages[3].status = StageStatus.PAUSED_FOR_REVIEW  # card_gen
    state.current_stage_id = state.stages[3].stage_id
    save_state(state)

    resp = client.post(
        "/api/wizard/edit/accept",
        json={"set_code": "ASD", "from_stage": "skeleton"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    # theme.json still exists -> kickoff requested, navigate to first PENDING.
    assert data["engine_started"] is True
    assert data["next_stage_id"] == "skeleton"
    assert data["navigate_to"] == "/pipeline/skeleton"

    assert not (set_dir / "skeleton.json").exists()
    assert not (set_dir / "reprint_selection.json").exists()
    assert not cards.exists()

    reloaded = load_state("ASD")
    assert reloaded is not None
    assert all(s.status == StageStatus.PENDING for s in reloaded.stages)
    assert reloaded.current_stage_id is None


def test_accept_from_theme_resets_all_pipeline_stages(client, no_thread_start):
    set_dir = _make_set("ASD", theme={"code": "ASD"})
    (set_dir / "skeleton.json").write_text("{}", encoding="utf-8")

    state = _seed_state("ASD", overall_status=PipelineStatus.PAUSED)
    state.stages[0].status = StageStatus.COMPLETED
    save_state(state)

    resp = client.post(
        "/api/wizard/edit/accept",
        json={"set_code": "ASD", "from_stage": "theme"},
    )
    assert resp.status_code == 200
    assert resp.json()["next_stage_id"] == "skeleton"
    assert not (set_dir / "skeleton.json").exists()


def test_accept_from_theme_persists_payload(client, no_thread_start):
    set_dir = _make_set("ASD", theme={"code": "ASD", "name": "Old"})
    new_theme = {
        "code": "ASD",
        "name": "Renamed",
        "constraints": [{"text": "no dragons", "source": "human"}],
    }
    resp = client.post(
        "/api/wizard/edit/accept",
        json={
            "set_code": "ASD",
            "from_stage": "theme",
            "theme_payload": new_theme,
        },
    )
    assert resp.status_code == 200
    on_disk = json.loads((set_dir / "theme.json").read_text(encoding="utf-8"))
    assert on_disk["name"] == "Renamed"
    assert on_disk["constraints"][0]["text"] == "no dragons"


def test_accept_clear_theme_json_returns_to_project(client, no_thread_start):
    """Theme-input change wipes theme.json; user is sent back to /pipeline/project."""
    set_dir = _make_set("ASD", theme={"code": "ASD"})
    (set_dir / "skeleton.json").write_text("{}", encoding="utf-8")
    _seed_state("ASD", overall_status=PipelineStatus.PAUSED)

    resp = client.post(
        "/api/wizard/edit/accept",
        json={
            "set_code": "ASD",
            "from_stage": "project",
            "clear_theme_json": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["navigate_to"] == "/pipeline/project"
    assert data["engine_started"] is False
    assert data["next_stage_id"] is None
    assert not (set_dir / "theme.json").exists()
    assert not (set_dir / "skeleton.json").exists()
    # State is preserved with everything reset to PENDING — the user
    # clicks Start to re-extract.
    reloaded = load_state("ASD")
    assert reloaded is not None
    assert all(s.status == StageStatus.PENDING for s in reloaded.stages)


def test_accept_persists_set_params_patch(client, no_thread_start):
    _make_set("ASD", theme={"code": "ASD"})
    _seed_state("ASD", overall_status=PipelineStatus.PAUSED)

    resp = client.post(
        "/api/wizard/edit/accept",
        json={
            "set_code": "ASD",
            "from_stage": "project",
            "set_params_patch": {"set_size": 80},
        },
    )
    assert resp.status_code == 200
    settings = ms.get_settings("ASD")
    assert settings.set_params.set_size == 80


def test_accept_persists_theme_input_patch(client, no_thread_start):
    set_dir = _make_set("ASD", theme={"code": "ASD"})
    (set_dir / "skeleton.json").write_text("{}", encoding="utf-8")
    _seed_state("ASD", overall_status=PipelineStatus.PAUSED)

    resp = client.post(
        "/api/wizard/edit/accept",
        json={
            "set_code": "ASD",
            "from_stage": "project",
            "clear_theme_json": True,
            "theme_input": {
                "kind": "pdf",
                "filename": "new.pdf",
                "upload_id": "abc123",
                "char_count": 12345,
            },
        },
    )
    assert resp.status_code == 200
    settings = ms.get_settings("ASD")
    assert settings.theme_input.kind == "pdf"
    assert settings.theme_input.filename == "new.pdf"
    assert settings.theme_input.upload_id == "abc123"


def test_accept_409_when_engine_running(client, monkeypatch):
    set_dir = _make_set("ASD", theme={"code": "ASD"})
    (set_dir / "skeleton.json").write_text("{}", encoding="utf-8")
    seeded = _seed_state("ASD", overall_status=PipelineStatus.RUNNING)
    seeded.stages[0].status = StageStatus.COMPLETED
    seeded.stages[0].progress.completed_items = 60
    save_state(seeded)
    seeded_dump = load_state("ASD").model_dump(mode="json")

    class _BusyEngine:
        is_running = True

        def __init__(self) -> None:
            self.state = create_pipeline_state(
                PipelineConfig(set_code="ASD", set_name="ASD", set_size=20),
            )

    monkeypatch.setattr(pipeline_server, "_engine", _BusyEngine())

    resp = client.post(
        "/api/wizard/edit/accept",
        json={"set_code": "ASD", "from_stage": "skeleton"},
    )
    assert resp.status_code == 409
    assert "running" in resp.json()["error"].lower()
    # 409 must not have mutated state on disk: the cascade-clear writes
    # are gated behind the engine-running check, so pipeline-state.json
    # and skeleton.json should be untouched.
    assert (set_dir / "skeleton.json").exists()
    assert load_state("ASD").model_dump(mode="json") == seeded_dump


def test_accept_409_when_extraction_running(client):
    """A mid-flight theme extraction also blocks Accept — a new theme.json
    write would race the cascade clear."""
    _make_set("ASD", theme={"code": "ASD"})
    _seed_state("ASD", overall_status=PipelineStatus.PAUSED)
    extraction_run.start_run("upload-xyz")

    resp = client.post(
        "/api/wizard/edit/accept",
        json={"set_code": "ASD", "from_stage": "skeleton"},
    )
    assert resp.status_code == 409
    assert "extraction" in resp.json()["error"].lower()


def test_accept_400_for_invalid_set_size(client):
    _make_set("ASD", theme={"code": "ASD"})
    _seed_state("ASD", overall_status=PipelineStatus.PAUSED)

    for bad in (-3, 0, "abc", None):
        resp = client.post(
            "/api/wizard/edit/accept",
            json={
                "set_code": "ASD",
                "from_stage": "project",
                "set_params_patch": {"set_size": bad},
            },
        )
        assert resp.status_code == 400, f"Expected 400 for set_size={bad!r}, got {resp.status_code}"


def test_accept_400_for_negative_mechanic_count(client):
    _make_set("ASD", theme={"code": "ASD"})
    _seed_state("ASD", overall_status=PipelineStatus.PAUSED)
    resp = client.post(
        "/api/wizard/edit/accept",
        json={
            "set_code": "ASD",
            "from_stage": "project",
            "set_params_patch": {"mechanic_count": -1},
        },
    )
    assert resp.status_code == 400


def test_accept_400_for_non_dict_patch(client):
    _make_set("ASD", theme={"code": "ASD"})
    _seed_state("ASD", overall_status=PipelineStatus.PAUSED)
    resp = client.post(
        "/api/wizard/edit/accept",
        json={
            "set_code": "ASD",
            "from_stage": "project",
            "set_params_patch": [1, 2, 3],
        },
    )
    assert resp.status_code == 400


def test_accept_400_for_unknown_stage(client):
    _make_set("ASD", theme={"code": "ASD"})
    resp = client.post(
        "/api/wizard/edit/accept",
        json={"set_code": "ASD", "from_stage": "nonexistent"},
    )
    assert resp.status_code == 400


def test_accept_400_for_missing_from_stage(client):
    _make_set("ASD", theme={"code": "ASD"})
    resp = client.post("/api/wizard/edit/accept", json={"set_code": "ASD"})
    assert resp.status_code == 400


def test_accept_400_for_invalid_theme_input_kind(client):
    _make_set("ASD", theme={"code": "ASD"})
    _seed_state("ASD", overall_status=PipelineStatus.PAUSED)
    resp = client.post(
        "/api/wizard/edit/accept",
        json={
            "set_code": "ASD",
            "from_stage": "project",
            "theme_input": {"kind": "garbage"},
        },
    )
    assert resp.status_code == 400


def test_accept_idempotent_when_no_state_on_disk(client, no_thread_start):
    """A brand-new set (no pipeline-state.json) accepts a project edit
    by writing settings + bouncing to /pipeline/project. Mostly a guard
    against a stale wizard tab calling Accept after the user wiped the
    set folder; the endpoint should not 500."""
    _make_set("ASD")  # no theme.json, no pipeline-state.json
    resp = client.post(
        "/api/wizard/edit/accept",
        json={"set_code": "ASD", "from_stage": "project"},
    )
    assert resp.status_code == 200
    assert resp.json()["navigate_to"] == "/pipeline/project"


def test_resolve_edit_point_zero_for_project_and_theme():
    state = create_pipeline_state(
        PipelineConfig(set_code="ASD", set_name="ASD", set_size=20),
    )
    assert pipeline_server._resolve_edit_point("project", state) == 0
    assert pipeline_server._resolve_edit_point("theme", state) == 0


def test_resolve_edit_point_returns_stage_index():
    state = create_pipeline_state(
        PipelineConfig(set_code="ASD", set_name="ASD", set_size=20),
    )
    # card_gen is the 4th stage (index 3) per STAGE_DEFINITIONS.
    assert pipeline_server._resolve_edit_point("card_gen", state) == 3


def test_resolve_edit_point_raises_for_unknown_stage():
    state = create_pipeline_state(
        PipelineConfig(set_code="ASD", set_name="ASD", set_size=20),
    )
    with pytest.raises(ValueError):
        pipeline_server._resolve_edit_point("garbage", state)
