"""Unit tests for the wizard state resolver.

Covers the visible-tab + latest-tab + URL-resolution logic in
``mtgai.pipeline.wizard`` against the six §11 startup states.
"""

from __future__ import annotations

import json

import pytest

from mtgai.pipeline.models import (
    PipelineConfig,
    PipelineState,
    PipelineStatus,
    StageStatus,
    create_pipeline_state,
)
from mtgai.pipeline.wizard import (
    PROJECT_TAB_ID,
    THEME_TAB_ID,
    build_wizard_state,
    compute_latest_tab,
    compute_visible_tabs,
    resolve_tab,
    serialize,
)


@pytest.fixture
def sets_root(tmp_path, monkeypatch):
    root = tmp_path / "sets"
    root.mkdir()
    monkeypatch.setattr("mtgai.pipeline.wizard.SETS_ROOT", root)
    monkeypatch.setattr("mtgai.pipeline.engine.OUTPUT_ROOT", tmp_path)
    return root


def _state_for(set_code: str = "TST") -> PipelineState:
    return create_pipeline_state(
        PipelineConfig(set_code=set_code, set_name="Test", set_size=20),
    )


# ----------------------------------------------------------------------
# compute_visible_tabs — six §11 startup states
# ----------------------------------------------------------------------


def test_brand_new_only_project_visible():
    tabs = compute_visible_tabs(state=None, theme=None)
    assert [t.id for t in tabs] == [PROJECT_TAB_ID]


def test_theme_only_adds_theme_tab():
    tabs = compute_visible_tabs(state=None, theme={"code": "TST"})
    assert [t.id for t in tabs] == [PROJECT_TAB_ID, THEME_TAB_ID]


def test_state_with_no_started_stages_only_shows_theme_and_project():
    """Pipeline state created but every stage still PENDING — no stage tabs yet."""
    state = _state_for()
    tabs = compute_visible_tabs(state=state, theme={"code": "TST"})
    assert [t.id for t in tabs] == [PROJECT_TAB_ID, THEME_TAB_ID]


def test_running_stage_extends_visibility_through_running():
    """First two stages: completed + running → both stage tabs visible."""
    state = _state_for()
    state.stages[0].status = StageStatus.COMPLETED
    state.stages[1].status = StageStatus.RUNNING
    tabs = compute_visible_tabs(state=state, theme={"code": "TST"})
    expected = [
        PROJECT_TAB_ID,
        THEME_TAB_ID,
        state.stages[0].stage_id,
        state.stages[1].stage_id,
    ]
    assert [t.id for t in tabs] == expected


def test_paused_for_review_keeps_paused_stage_visible():
    state = _state_for()
    state.stages[0].status = StageStatus.PAUSED_FOR_REVIEW
    tabs = compute_visible_tabs(state=state, theme={"code": "TST"})
    assert tabs[-1].id == state.stages[0].stage_id
    assert tabs[-1].status == StageStatus.PAUSED_FOR_REVIEW.value


def test_failed_stage_visible_through_failure():
    state = _state_for()
    state.stages[0].status = StageStatus.COMPLETED
    state.stages[1].status = StageStatus.FAILED
    tabs = compute_visible_tabs(state=state, theme={"code": "TST"})
    assert [t.id for t in tabs[-2:]] == [
        state.stages[0].stage_id,
        state.stages[1].stage_id,
    ]
    assert tabs[-1].status == StageStatus.FAILED.value


def test_fully_complete_shows_every_stage():
    state = _state_for()
    for stage in state.stages:
        stage.status = StageStatus.COMPLETED
    state.overall_status = PipelineStatus.COMPLETED
    tabs = compute_visible_tabs(state=state, theme={"code": "TST"})
    expected_count = 2 + len(state.stages)
    assert len(tabs) == expected_count
    assert tabs[-1].id == state.stages[-1].stage_id


# ----------------------------------------------------------------------
# compute_latest_tab + resolve_tab
# ----------------------------------------------------------------------


def test_latest_is_rightmost_tab():
    tabs = compute_visible_tabs(state=None, theme={"code": "TST"})
    assert compute_latest_tab(tabs) == THEME_TAB_ID


def test_latest_is_project_when_no_other_tabs():
    tabs = compute_visible_tabs(state=None, theme=None)
    assert compute_latest_tab(tabs) == PROJECT_TAB_ID


def test_resolve_tab_returns_requested_when_visible():
    tabs = compute_visible_tabs(state=None, theme={"code": "TST"})
    assert resolve_tab("theme", tabs) == "theme"


def test_resolve_tab_falls_back_to_latest_when_unknown():
    tabs = compute_visible_tabs(state=None, theme=None)
    # Stage tab not visible yet — should drop to project.
    assert resolve_tab("skeleton", tabs) == PROJECT_TAB_ID


def test_resolve_tab_handles_none_request():
    tabs = compute_visible_tabs(state=None, theme={"code": "TST"})
    assert resolve_tab(None, tabs) == THEME_TAB_ID


# ----------------------------------------------------------------------
# build_wizard_state — disk wiring
# ----------------------------------------------------------------------


def test_build_wizard_state_brand_new(sets_root):
    (sets_root / "TST").mkdir()
    ws = build_wizard_state("TST", requested_tab=None)
    assert ws.active_set == "TST"
    assert ws.pipeline_state is None
    assert ws.theme is None
    assert ws.active_tab_id == PROJECT_TAB_ID
    assert ws.latest_tab_id == PROJECT_TAB_ID


def test_build_wizard_state_with_theme(sets_root):
    set_dir = sets_root / "TST"
    set_dir.mkdir()
    (set_dir / "theme.json").write_text(
        json.dumps({"code": "TST", "name": "Test"}),
        encoding="utf-8",
    )
    ws = build_wizard_state("TST", requested_tab=None)
    assert ws.theme == {"code": "TST", "name": "Test"}
    assert ws.active_tab_id == THEME_TAB_ID


def test_build_wizard_state_tolerates_corrupt_theme(sets_root):
    set_dir = sets_root / "TST"
    set_dir.mkdir()
    (set_dir / "theme.json").write_text("{ not valid json", encoding="utf-8")
    ws = build_wizard_state("TST", requested_tab=None)
    # Corrupt theme is treated as absent — wizard still resolves to project.
    assert ws.theme is None
    assert ws.active_tab_id == PROJECT_TAB_ID


def test_serialize_round_trips_visible_tabs(sets_root):
    set_dir = sets_root / "TST"
    set_dir.mkdir()
    (set_dir / "theme.json").write_text(json.dumps({"code": "TST"}), encoding="utf-8")
    ws = build_wizard_state("TST", requested_tab="theme")
    blob = serialize(ws)
    assert blob["active_tab_id"] == "theme"
    assert [t["id"] for t in blob["visible_tabs"]] == ["project", "theme"]
    assert blob["pipeline_state"] is None
    assert blob["theme"] == {"code": "TST"}
