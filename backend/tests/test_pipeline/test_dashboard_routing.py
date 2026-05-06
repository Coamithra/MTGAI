"""Routing tests for the wizard shell at /pipeline/*.

The wizard replaces the flat dashboard. A bare ``/pipeline`` resolves
to the latest visible tab via :func:`mtgai.pipeline.wizard.build_wizard_state`
and 302s; ``/pipeline/<tab_id>`` either renders the wizard with that
tab active or redirects to the latest tab when the fragment isn't a
visible surface for the active set.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from mtgai.pipeline.models import (
    PipelineConfig,
    PipelineState,
    StageStatus,
    create_pipeline_state,
)
from mtgai.review.server import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def isolate_sets(tmp_path, monkeypatch):
    """Point the wizard's state-resolution helpers at an empty tmp tree.

    Without this, the live ``output/sets`` directory leaks into route
    tests and the brand-new flow asserts fail when a real set exists.
    """
    sets_root = tmp_path / "sets"
    sets_root.mkdir()
    monkeypatch.setattr("mtgai.pipeline.wizard.SETS_ROOT", sets_root)
    monkeypatch.setattr("mtgai.pipeline.engine.OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr("mtgai.runtime.runtime_state.SETS_ROOT", sets_root)
    monkeypatch.setattr("mtgai.runtime.runtime_state.OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr("mtgai.runtime.active_set.SETS_ROOT", sets_root)
    monkeypatch.setattr(
        "mtgai.runtime.active_set._LAST_SET_PATH",
        tmp_path / "settings" / "last_set.toml",
    )
    return sets_root


def _activate(code: str) -> None:
    """Write the active-project pointer so resolve_active_set_code finds it.

    Tests for the wizard render path used to rely on the now-removed
    mtime / env-var fallbacks; they have to opt in to a project the
    same way the runtime does (via the active-set TOML written by the
    Open / Materialise endpoints).
    """
    from mtgai.runtime.active_set import write_active_set

    write_active_set(code)


def _seed_set(
    sets_root, code: str, *, theme: dict | None = None, state: PipelineState | None = None
):
    """Materialise a set on disk so the resolver finds it."""
    set_dir = sets_root / code
    set_dir.mkdir(parents=True, exist_ok=True)
    if theme is not None:
        (set_dir / "theme.json").write_text(json.dumps(theme), encoding="utf-8")
    if state is not None:
        (set_dir / "pipeline-state.json").write_text(
            json.dumps(state.model_dump(mode="json"), default=str),
            encoding="utf-8",
        )


def test_pipeline_root_redirects_to_project_when_brand_new(client, isolate_sets):
    """No theme.json + no pipeline-state.json → only Project tab visible."""
    _seed_set(isolate_sets, "TST")
    resp = client.get("/pipeline", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/pipeline/project"


def test_pipeline_root_redirects_to_theme_when_theme_exists(client, isolate_sets):
    """Theme exists, pipeline not started → latest tab is theme."""
    _seed_set(isolate_sets, "TST", theme={"code": "TST", "name": "Test"})
    _activate("TST")
    resp = client.get("/pipeline", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/pipeline/theme"


def test_pipeline_root_redirects_to_running_stage(client, isolate_sets):
    """A mid-run pipeline lands on the currently running stage."""
    state = create_pipeline_state(
        PipelineConfig(set_code="TST", set_name="Test", set_size=20),
    )
    state.stages[0].status = StageStatus.COMPLETED
    state.stages[1].status = StageStatus.RUNNING
    _seed_set(isolate_sets, "TST", theme={"code": "TST"}, state=state)
    _activate("TST")

    resp = client.get("/pipeline", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == f"/pipeline/{state.stages[1].stage_id}"


def test_pipeline_project_renders_wizard(client, isolate_sets):
    """/pipeline/project always renders the wizard shell directly."""
    _seed_set(isolate_sets, "TST")
    resp = client.get("/pipeline/project")
    assert resp.status_code == 200
    body = resp.text
    assert 'id="wizard-app"' in body
    assert "/static/wizard.js" in body
    assert "WIZARD_STATE" in body


def test_pipeline_project_includes_serialised_state(client, isolate_sets):
    """The wizard bootstrap blob carries active_set + visible_tabs."""
    _seed_set(isolate_sets, "TST", theme={"code": "TST", "name": "Test"})
    _activate("TST")
    resp = client.get("/pipeline/project")
    assert resp.status_code == 200
    body = resp.text
    # The blob is embedded as JSON via Jinja's `| safe` — pull the line.
    line = next(ln for ln in body.splitlines() if "const WIZARD_STATE" in ln)
    payload = json.loads(line.split("=", 1)[1].rstrip(";").strip())
    assert payload["active_set"] == "TST"
    tab_ids = [t["id"] for t in payload["visible_tabs"]]
    assert tab_ids == ["project", "theme"]


def test_pipeline_unknown_tab_redirects_to_latest(client, isolate_sets):
    """A tab id that isn't visible yet 302s to whatever the latest tab is."""
    _seed_set(isolate_sets, "TST")
    resp = client.get("/pipeline/skeleton", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/pipeline/project"


def test_pipeline_theme_redirects_when_no_theme(client, isolate_sets):
    """`/pipeline/theme` falls back to project when no theme.json exists."""
    _seed_set(isolate_sets, "TST")
    resp = client.get("/pipeline/theme", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/pipeline/project"


def test_pipeline_theme_renders_when_theme_exists(client, isolate_sets):
    _seed_set(isolate_sets, "TST", theme={"code": "TST", "name": "Test"})
    resp = client.get("/pipeline/theme")
    assert resp.status_code == 200
    assert 'id="wizard-app"' in resp.text


def test_pipeline_configure_redirects_to_project(client, isolate_sets):
    """Legacy `/pipeline/configure` 302s to the wizard's Project tab."""
    _seed_set(isolate_sets, "TST")
    resp = client.get("/pipeline/configure", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/pipeline/project"
