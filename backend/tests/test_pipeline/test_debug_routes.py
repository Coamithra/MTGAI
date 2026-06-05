"""Tests for the QA/debug surface (`mtgai/pipeline/debug_routes.py`).

The debug router only mounts under ``serve --debug`` in production; here we
mount it directly on a throwaway app so we can exercise the endpoints without
the env gate. ``output_root``/``repo_root`` are monkeypatched to a tmp tree so
QA-run clones never touch the real ``output/`` dir.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mtgai.pipeline import debug_routes
from mtgai.pipeline.models import (
    STAGE_DEFINITIONS,
    PipelineConfig,
    PipelineState,
    PipelineStatus,
    StageState,
    StageStatus,
)
from mtgai.runtime import active_project


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    """Sandbox the debug routes' filesystem roots + clear the project pointer."""
    root = tmp_path / "repo"
    out = root / "output"
    out.mkdir(parents=True)
    monkeypatch.setattr(debug_routes, "output_root", lambda: out)
    monkeypatch.setattr(debug_routes, "repo_root", lambda: root)
    monkeypatch.delenv("MTGAI_QA_GOLDEN", raising=False)
    monkeypatch.delenv(debug_routes.DEBUG_ENV, raising=False)
    active_project.clear_active_project()
    yield root, out
    active_project.clear_active_project()


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(debug_routes.router)
    return TestClient(app)


def _make_golden(folder, *, last_completed: str) -> None:
    """Write a minimal finished-project layout (pipeline-state.json + theme.json).

    All backbone stages up to ``last_completed`` are COMPLETED, the rest PENDING.
    """
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "theme.json").write_text(json.dumps({"setting": "test"}), encoding="utf-8")
    order = [d["stage_id"] for d in STAGE_DEFINITIONS]
    cut = order.index(last_completed)
    stages = [
        StageState(
            stage_id=d["stage_id"],
            display_name=d["display_name"],
            review_eligible=d["review_eligible"],
            status=StageStatus.COMPLETED if i <= cut else StageStatus.PENDING,
        )
        for i, d in enumerate(STAGE_DEFINITIONS)
    ]
    state = PipelineState(
        config=PipelineConfig(set_code="GOLD", set_name="Gold"),
        stages=stages,
        overall_status=PipelineStatus.PAUSED,
    )
    (folder / "pipeline-state.json").write_text(
        json.dumps(state.model_dump(mode="json"), default=str), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Gating
# ---------------------------------------------------------------------------


def test_is_debug_enabled_reflects_env(monkeypatch):
    monkeypatch.delenv(debug_routes.DEBUG_ENV, raising=False)
    assert debug_routes.is_debug_enabled() is False
    monkeypatch.setenv(debug_routes.DEBUG_ENV, "1")
    assert debug_routes.is_debug_enabled() is True
    monkeypatch.setenv(debug_routes.DEBUG_ENV, "0")
    assert debug_routes.is_debug_enabled() is False
    monkeypatch.setenv(debug_routes.DEBUG_ENV, "false")
    assert debug_routes.is_debug_enabled() is False


def test_attach_debug_routes_gated(monkeypatch):
    app = FastAPI()
    monkeypatch.delenv(debug_routes.DEBUG_ENV, raising=False)
    assert debug_routes.attach_debug_routes(app) is False
    monkeypatch.setenv(debug_routes.DEBUG_ENV, "1")
    assert debug_routes.attach_debug_routes(app) is True


# ---------------------------------------------------------------------------
# /api/debug/state
# ---------------------------------------------------------------------------


def test_state_reports_stages_and_golden(client, _sandbox):
    _root, out = _sandbox
    _make_golden(out / "sets" / "MYSET", last_completed="ai_review")
    resp = client.get("/api/debug/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert any(s["stage_id"] == "card_gen" for s in data["stages"])
    assert any(c["name"] == "MYSET" for c in data["golden_candidates"])
    assert data["active"] is None


# ---------------------------------------------------------------------------
# /api/debug/quick-project
# ---------------------------------------------------------------------------


def test_quick_project_creates_and_activates(client):
    resp = client.post(
        "/api/debug/quick-project",
        json={"set_code": "ZZ", "set_size": 30, "prefab": True, "theme_text": "a world"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["navigate"] == "/pipeline/project"
    proj = active_project.read_active_project()
    assert proj is not None
    assert proj.set_code == "ZZ"
    # qa preset applied (cheap gemma everywhere) + thinking off + prefab on.
    assert proj.settings.llm_assignments["card_gen"] == "gemma4-26b-iq2m"
    assert proj.settings.thinking_overrides.get("card_gen") == "disabled"
    assert proj.settings.debug.use_prefab_cards is True
    assert proj.settings.set_params.set_size == 30
    assert proj.settings.theme_input.kind == "text"
    # The .mtg + theme source were written server-side (no picker).
    from pathlib import Path

    folder = Path(proj.settings.asset_folder)
    assert (folder / "qa.mtg").is_file()
    assert (folder / "theme_source.txt").read_text(encoding="utf-8") == "a world"


# ---------------------------------------------------------------------------
# /api/debug/seed-stage
# ---------------------------------------------------------------------------


def test_seed_stage_jumps_to_target(client, _sandbox):
    _root, out = _sandbox
    src = out / "sets" / "GOLDEN"
    _make_golden(src, last_completed="ai_review")
    (src / "cards").mkdir()
    (src / "cards" / "001_x.json").write_text("{}", encoding="utf-8")

    resp = client.post(
        "/api/debug/seed-stage", json={"target_stage": "card_gen", "source_dir": str(src)}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["target_stage"] == "card_gen"
    assert data["navigate"] == "/pipeline/card_gen"

    # The active project now points at the clone with a rewritten state.
    from mtgai.pipeline import engine

    state = engine.load_state()
    assert state is not None
    assert state.overall_status == PipelineStatus.PAUSED
    by_id = {s.stage_id: s for s in state.stages if s.instance_id == s.stage_id}
    assert by_id["mechanics"].status == StageStatus.COMPLETED
    assert by_id["card_gen"].status == StageStatus.COMPLETED  # target inclusive
    assert by_id["conformance"].status == StageStatus.PENDING  # downstream reset
    assert by_id["ai_review"].status == StageStatus.PENDING
    # Cloned artifacts came along.
    from pathlib import Path

    assert (Path(data["asset_folder"]) / "cards" / "001_x.json").is_file()


def test_seed_stage_rejects_bad_stage(client, _sandbox):
    _root, out = _sandbox
    src = out / "sets" / "GOLDEN"
    _make_golden(src, last_completed="card_gen")
    resp = client.post(
        "/api/debug/seed-stage", json={"target_stage": "nonsense", "source_dir": str(src)}
    )
    assert resp.status_code == 400


def test_seed_stage_no_source(client):
    resp = client.post("/api/debug/seed-stage", json={"target_stage": "card_gen"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /api/debug/open-path + save-mtg
# ---------------------------------------------------------------------------


def test_open_path_and_save_roundtrip(client, _sandbox, tmp_path):
    # Make a real .mtg via quick-project, then reopen it from its folder path.
    client.post("/api/debug/quick-project", json={"set_code": "RT"})
    proj = active_project.read_active_project()
    assert proj is not None
    folder = proj.settings.asset_folder
    active_project.clear_active_project()

    resp = client.post("/api/debug/open-path", json={"path": folder})
    assert resp.status_code == 200, resp.text
    assert resp.json()["set_code"] == "RT"
    assert active_project.read_active_project() is not None

    save = client.post("/api/debug/save-mtg", json={})
    assert save.status_code == 200
    from pathlib import Path

    assert Path(save.json()["path"]).is_file()


def test_save_mtg_no_project(client):
    resp = client.post("/api/debug/save-mtg", json={})
    assert resp.status_code == 409
