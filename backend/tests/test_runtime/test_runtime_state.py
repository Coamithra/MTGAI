"""Unit tests for the runtime-state aggregator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mtgai.runtime import active_project, ai_lock, extraction_run, runtime_state


@pytest.fixture(autouse=True)
def _reset(isolated_output):
    """Per-test reset of run-state singletons.

    ``isolated_output`` (in :mod:`tests.conftest`) handles the full
    artifact-path patching chain — resolver helpers, runtime modules,
    pipeline-server module, and active-project state. This wrapper just
    resets the singletons this test module exercises.
    """
    ai_lock.reset_for_tests()
    extraction_run.reset()
    yield
    ai_lock.reset_for_tests()
    extraction_run.reset()


def _write_theme(set_dir: Path, theme: dict) -> None:
    set_dir.mkdir(parents=True, exist_ok=True)
    (set_dir / "theme.json").write_text(json.dumps(theme), encoding="utf-8")


def _open_project(code: str, asset_folder: Path) -> None:
    """Helper: pin ``code`` as the active project with its assets at ``asset_folder``.

    Mirrors the production sequence: ``apply_settings`` writes the
    settings.toml + ``asset_folder`` pointer, then
    ``write_active_set`` flips the in-memory pointer (re-reading
    settings to populate the ProjectState).
    """
    from mtgai.settings.model_settings import ModelSettings, apply_settings

    apply_settings(code, ModelSettings(asset_folder=str(asset_folder)))
    active_project.write_active_set(code)


def _empty_state_shape(payload: dict) -> None:
    assert payload["ai_lock"]["running"] is False
    assert payload["active_runs"] == {}
    assert payload["pipeline"] is None


def test_compute_returns_none_when_no_project_loaded(monkeypatch):
    """No active-project pointer + nothing else → ``active_set`` is ``None``.

    The legacy mtime / env / "ASD" fallbacks were dropped when projects
    moved to .mtg files: a server start with no project chosen leaves
    the wizard in the New / Open state rather than silently picking
    a half-stale set.
    """
    monkeypatch.delenv("MTGAI_REVIEW_SET", raising=False)
    payload = runtime_state.compute_runtime_state()
    assert payload["active_set"] is None
    _empty_state_shape(payload)
    assert payload["theme"] is None


def test_compute_ignores_disk_sets_without_explicit_pointer(monkeypatch):
    """A theme.json on disk no longer auto-picks the active set.

    The mtime fallback was the legacy resolver's last-resort heuristic;
    today the only way to make a set "active" is via the active-project
    pointer set by ``/api/project/open`` or ``/api/project/materialize``.
    """
    monkeypatch.delenv("MTGAI_REVIEW_SET", raising=False)
    sets_root = runtime_state.SETS_ROOT
    _write_theme(sets_root / "ABC", {"code": "ABC", "name": "Test"})
    payload = runtime_state.compute_runtime_state()
    assert payload["active_set"] is None
    assert payload["theme"] is None


def test_compute_includes_ai_lock_running_payload():
    """When the lock is held, the payload reflects it."""
    assert ai_lock.try_acquire("Test action") is True
    try:
        payload = runtime_state.compute_runtime_state()
        assert payload["ai_lock"]["running"] is True
        assert payload["ai_lock"]["running_action"] == "Test action"
    finally:
        ai_lock.release()


def test_compute_includes_active_extraction_run():
    """A live extraction run shows up under active_runs."""
    extraction_run.start_run("upload-xyz")
    extraction_run.append_event({"type": "theme_chunk", "text": "hi"})
    payload = runtime_state.compute_runtime_state()
    assert "theme_extraction" in payload["active_runs"]
    er = payload["active_runs"]["theme_extraction"]
    assert er["upload_id"] == "upload-xyz"
    assert er["events_count"] == 1
    assert isinstance(er["started_at"], str)


def test_compute_omits_completed_extraction_run():
    """Once the run is marked done, it disappears from active_runs."""
    extraction_run.start_run("upload-xyz")
    extraction_run.mark_done("completed")
    payload = runtime_state.compute_runtime_state()
    assert payload["active_runs"] == {}


def test_compute_loads_theme_when_present():
    """Theme.json under the active project's asset_folder is surfaced."""
    sets_root = runtime_state.SETS_ROOT
    asset_dir = sets_root / "TST"
    _write_theme(
        asset_dir,
        {
            "code": "TST",
            "name": "Test Set",
            "constraints": ["c1", "c2"],
            "card_requests": ["r1"],
            "set_size": 60,
        },
    )
    _open_project("TST", asset_dir)
    payload = runtime_state.compute_runtime_state()
    assert payload["theme"]["name"] == "Test Set"
    assert payload["theme"]["constraints"] == ["c1", "c2"]


def test_compute_returns_none_theme_when_asset_folder_empty():
    """Active project without an asset_folder set → theme is ``None``.

    ``set_artifact_dir`` raises NoAssetFolderError; ``_load_theme``
    swallows it and returns ``None`` so the wizard renders the no-theme
    state instead of 500ing the runtime endpoint.
    """
    from mtgai.settings.model_settings import ModelSettings, apply_settings

    apply_settings("TST", ModelSettings(asset_folder=""))
    active_project.write_active_set("TST")
    payload = runtime_state.compute_runtime_state()
    assert payload["active_set"] == "TST"
    assert payload["theme"] is None


def test_in_memory_pointer_drives_resolution(monkeypatch):
    """Setting the in-memory active-project pointer surfaces in the payload."""
    monkeypatch.delenv("MTGAI_REVIEW_SET", raising=False)
    sets_root = runtime_state.SETS_ROOT
    _write_theme(sets_root / "OLD", {"code": "OLD"})
    _write_theme(sets_root / "PIN", {"code": "PIN", "name": "Pinned"})

    _open_project("PIN", sets_root / "PIN")

    payload = runtime_state.compute_runtime_state()
    assert payload["active_set"] == "PIN"
    assert payload["theme"]["name"] == "Pinned"


def test_clear_pointer_yields_no_project(monkeypatch):
    """Clearing the in-memory pointer surfaces the empty New/Open state."""
    monkeypatch.delenv("MTGAI_REVIEW_SET", raising=False)
    sets_root = runtime_state.SETS_ROOT
    _write_theme(sets_root / "ALIVE", {"code": "ALIVE"})

    _open_project("ALIVE", sets_root / "ALIVE")
    active_project.clear_active_set()

    payload = runtime_state.compute_runtime_state()
    assert payload["active_set"] is None


def test_compute_swallows_corrupt_theme_json():
    """A malformed theme.json doesn't blow up the endpoint."""
    sets_root = runtime_state.SETS_ROOT
    bad = sets_root / "BAD"
    bad.mkdir(parents=True)
    (bad / "theme.json").write_text("{ not valid json", encoding="utf-8")
    _open_project("BAD", bad)
    payload = runtime_state.compute_runtime_state()
    assert payload["theme"] is None
