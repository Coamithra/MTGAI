"""Tests for ``cleanup_orphan_running_stages``.

A pipeline-state.json with a ``RUNNING`` stage on disk only ever
exists if a previous server process exited mid-stage; on boot we
demote those stages to ``FAILED`` so the wizard surfaces a Retry
button instead of a stuck spinner.
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


@pytest.fixture
def fake_output_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(engine_mod, "OUTPUT_ROOT", tmp_path)
    (tmp_path / "sets").mkdir()
    return tmp_path


def _write_state(root: Path, state: PipelineState) -> Path:
    set_dir = root / "sets" / state.config.set_code
    set_dir.mkdir(parents=True, exist_ok=True)
    path = set_dir / "pipeline-state.json"
    path.write_text(
        json.dumps(state.model_dump(mode="json"), indent=2, default=str),
        encoding="utf-8",
    )
    return path


def _state_with_running_stage(set_code: str, stage_id: str) -> PipelineState:
    state = create_pipeline_state(PipelineConfig(set_code=set_code, set_name="Test", set_size=20))
    for stage in state.stages:
        if stage.stage_id == stage_id:
            stage.status = StageStatus.RUNNING
            break
    state.overall_status = PipelineStatus.RUNNING
    state.current_stage_id = stage_id
    return state


def test_demotes_running_stage_to_failed(fake_output_root: Path) -> None:
    state = _state_with_running_stage("AAA", "card_gen")
    path = _write_state(fake_output_root, state)

    demoted = engine_mod.cleanup_orphan_running_stages()

    assert demoted == ["AAA:card_gen"]
    reloaded = PipelineState.model_validate_json(path.read_text(encoding="utf-8"))
    card_gen = next(s for s in reloaded.stages if s.stage_id == "card_gen")
    assert card_gen.status == StageStatus.FAILED
    assert card_gen.progress.error_message == "Interrupted — server restart"
    assert card_gen.progress.finished_at is not None
    assert reloaded.overall_status == PipelineStatus.FAILED


def test_demotes_overall_status_when_no_running_stage(fake_output_root: Path) -> None:
    """Overall RUNNING with no individual RUNNING stage is still cleaned up.

    This shouldn't happen in normal operation but the helper should
    leave consistent state on disk regardless of what it finds.
    """
    state = create_pipeline_state(PipelineConfig(set_code="BBB", set_name="Test", set_size=20))
    state.overall_status = PipelineStatus.RUNNING
    path = _write_state(fake_output_root, state)

    demoted = engine_mod.cleanup_orphan_running_stages()

    assert demoted == []
    reloaded = PipelineState.model_validate_json(path.read_text(encoding="utf-8"))
    assert reloaded.overall_status == PipelineStatus.FAILED


def test_leaves_completed_state_alone(fake_output_root: Path) -> None:
    state = create_pipeline_state(PipelineConfig(set_code="CCC", set_name="Test", set_size=20))
    state.overall_status = PipelineStatus.COMPLETED
    path = _write_state(fake_output_root, state)
    before = path.read_text(encoding="utf-8")

    demoted = engine_mod.cleanup_orphan_running_stages()

    assert demoted == []
    assert path.read_text(encoding="utf-8") == before


def test_handles_missing_sets_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No sets directory at all should not raise."""
    monkeypatch.setattr(engine_mod, "OUTPUT_ROOT", tmp_path)
    assert engine_mod.cleanup_orphan_running_stages() == []


def test_loads_legacy_state_with_skip_stages_field(fake_output_root: Path) -> None:
    """Old on-disk state JSONs may carry a now-removed ``skip_stages`` key.

    Pydantic v2's default behaviour ignores extra fields, so loading
    must succeed silently — there's no migration step. Lock that in
    so a future ``model_config = ConfigDict(extra='forbid')`` can't
    silently break startup for users with existing sets.
    """
    state = create_pipeline_state(PipelineConfig(set_code="LEG", set_name="Test", set_size=20))
    raw = state.model_dump(mode="json")
    raw["config"]["skip_stages"] = ["lands", "rendering"]
    set_dir = fake_output_root / "sets" / "LEG"
    set_dir.mkdir(parents=True)
    state_path = set_dir / "pipeline-state.json"
    state_path.write_text(json.dumps(raw, default=str), encoding="utf-8")

    # Should not raise — the cleanup helper round-trips the state.
    engine_mod.cleanup_orphan_running_stages()
    reloaded = engine_mod.load_state("LEG")
    assert reloaded is not None
    # The legacy field is silently dropped on load + re-save.
    assert not hasattr(reloaded.config, "skip_stages")


def test_skips_unparseable_state_files(fake_output_root: Path) -> None:
    """A corrupt state file shouldn't crash the boot path."""
    bad_dir = fake_output_root / "sets" / "BAD"
    bad_dir.mkdir()
    (bad_dir / "pipeline-state.json").write_text("{not valid json", encoding="utf-8")

    good = _state_with_running_stage("GOOD", "skeleton")
    _write_state(fake_output_root, good)

    demoted = engine_mod.cleanup_orphan_running_stages()
    assert demoted == ["GOOD:skeleton"]
