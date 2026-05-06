"""Tests for ``cleanup_orphan_running_stages``.

A pipeline-state.json with a ``RUNNING`` stage on disk only ever
exists if a previous server process exited mid-stage. The post-Refactor-3
helper operates on the active project's asset_folder only — it's called
from ``/api/project/{open,materialize}`` once the pointer is set, not at
server boot. These tests exercise the per-project demote pass.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mtgai.pipeline import engine as engine_mod
from mtgai.pipeline.models import (
    PipelineConfig,
    PipelineState,
    PipelineStatus,
    StageStatus,
    create_pipeline_state,
)
from mtgai.runtime import active_project
from mtgai.settings.model_settings import ModelSettings


@pytest.fixture
def project_with_state(tmp_path: Path):
    """Pin an active project at ``tmp_path`` and yield (asset_dir, write_state)."""
    asset_dir = tmp_path / "asset"
    asset_dir.mkdir()
    active_project.write_active_project(
        active_project.ProjectState(
            set_code="ABC", settings=ModelSettings(asset_folder=str(asset_dir))
        )
    )

    def _write(state: PipelineState) -> Path:
        path = asset_dir / "pipeline-state.json"
        path.write_text(
            json.dumps(state.model_dump(mode="json"), indent=2, default=str),
            encoding="utf-8",
        )
        return path

    yield asset_dir, _write
    active_project.clear_active_project()


def _state_with_running_stage(set_code: str, stage_id: str) -> PipelineState:
    state = create_pipeline_state(PipelineConfig(set_code=set_code, set_name="Test", set_size=20))
    for stage in state.stages:
        if stage.stage_id == stage_id:
            stage.status = StageStatus.RUNNING
            break
    state.overall_status = PipelineStatus.RUNNING
    state.current_stage_id = stage_id
    return state


def test_demotes_running_stage_to_failed(project_with_state):
    asset_dir, write_state = project_with_state
    state = _state_with_running_stage("AAA", "card_gen")
    path = write_state(state)

    demoted = engine_mod.cleanup_orphan_running_stages()

    assert demoted == ["AAA:card_gen"]
    reloaded = PipelineState.model_validate_json(path.read_text(encoding="utf-8"))
    card_gen = next(s for s in reloaded.stages if s.stage_id == "card_gen")
    assert card_gen.status == StageStatus.FAILED
    assert card_gen.progress.error_message == "Interrupted — server restart"
    assert card_gen.progress.finished_at is not None
    assert reloaded.overall_status == PipelineStatus.FAILED


def test_demotes_overall_status_when_no_running_stage(project_with_state):
    """Overall RUNNING with no individual RUNNING stage is still cleaned up.

    This shouldn't happen in normal operation but the helper should
    leave consistent state on disk regardless of what it finds.
    """
    asset_dir, write_state = project_with_state
    state = create_pipeline_state(PipelineConfig(set_code="BBB", set_name="Test", set_size=20))
    state.overall_status = PipelineStatus.RUNNING
    path = write_state(state)

    demoted = engine_mod.cleanup_orphan_running_stages()

    assert demoted == []
    reloaded = PipelineState.model_validate_json(path.read_text(encoding="utf-8"))
    assert reloaded.overall_status == PipelineStatus.FAILED


def test_leaves_completed_state_alone(project_with_state):
    asset_dir, write_state = project_with_state
    state = create_pipeline_state(PipelineConfig(set_code="CCC", set_name="Test", set_size=20))
    state.overall_status = PipelineStatus.COMPLETED
    path = write_state(state)
    before = path.read_text(encoding="utf-8")

    demoted = engine_mod.cleanup_orphan_running_stages()

    assert demoted == []
    assert path.read_text(encoding="utf-8") == before


def test_returns_empty_when_no_project_open():
    """No-op when no active project — no asset folder to scan."""
    active_project.clear_active_project()
    assert engine_mod.cleanup_orphan_running_stages() == []


def test_returns_empty_when_asset_folder_unset(tmp_path):
    """No-op when the active project has no asset_folder configured."""
    active_project.write_active_project(
        active_project.ProjectState(set_code="XYZ", settings=ModelSettings(asset_folder=""))
    )
    try:
        assert engine_mod.cleanup_orphan_running_stages() == []
    finally:
        active_project.clear_active_project()


def test_returns_empty_when_no_pipeline_state_file(project_with_state):
    """No-op when no pipeline-state.json exists yet for the open project."""
    assert engine_mod.cleanup_orphan_running_stages() == []


def test_loads_legacy_state_with_skip_stages_field(project_with_state):
    """Old on-disk state JSONs may carry a now-removed ``skip_stages`` key.

    Pydantic v2's default behaviour ignores extra fields, so loading
    must succeed silently — there's no migration step. Lock that in
    so a future ``model_config = ConfigDict(extra='forbid')`` can't
    silently break the open path for users with existing projects.
    """
    asset_dir, write_state = project_with_state
    state = create_pipeline_state(PipelineConfig(set_code="LEG", set_name="Test", set_size=20))
    raw = state.model_dump(mode="json")
    raw["config"]["skip_stages"] = ["lands", "rendering"]
    state_path = asset_dir / "pipeline-state.json"
    state_path.write_text(json.dumps(raw, default=str), encoding="utf-8")

    # Should not raise — the cleanup helper round-trips the state.
    engine_mod.cleanup_orphan_running_stages()
    reloaded = engine_mod.load_state()
    assert reloaded is not None
    # The legacy field is silently dropped on load + re-save.
    assert not hasattr(reloaded.config, "skip_stages")


def test_skips_unparseable_state_file(project_with_state):
    """A corrupt state file shouldn't crash the open path."""
    asset_dir, write_state = project_with_state
    (asset_dir / "pipeline-state.json").write_text("{not valid json", encoding="utf-8")

    demoted = engine_mod.cleanup_orphan_running_stages()
    assert demoted == []
