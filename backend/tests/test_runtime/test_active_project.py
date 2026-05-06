"""Unit tests for the :class:`ProjectState` API."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtgai.runtime import active_project
from mtgai.settings import model_settings as ms


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Patch path constants + clear the active-project pointer between tests."""
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir(parents=True)

    monkeypatch.setattr(ms, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(ms, "SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(ms, "GLOBAL_TOML", settings_dir / "global.toml")
    monkeypatch.setattr(ms, "LEGACY_CURRENT_TOML", settings_dir / "current.toml")

    active_project.clear_active_project()
    yield
    active_project.clear_active_project()


def test_read_returns_none_when_no_project_open():
    assert active_project.read_active_project() is None


def test_write_then_read_roundtrips_state():
    settings = ms.ModelSettings(asset_folder="D:/proj/abc")
    project = active_project.ProjectState(set_code="ABC", settings=settings)
    active_project.write_active_project(project)

    loaded = active_project.read_active_project()
    assert loaded is not None
    assert loaded.set_code == "ABC"
    assert loaded.settings.asset_folder == "D:/proj/abc"
    assert loaded.mtg_path is None


def test_write_carries_mtg_path():
    settings = ms.ModelSettings()
    mtg_path = Path("C:/projects/avoria.mtg")
    project = active_project.ProjectState(
        set_code="AVO",
        settings=settings,
        mtg_path=mtg_path,
    )
    active_project.write_active_project(project)

    loaded = active_project.read_active_project()
    assert loaded is not None
    assert loaded.mtg_path == mtg_path


def test_write_trims_whitespace_around_set_code():
    """Whitespace is stripped, but case is preserved verbatim — the
    relaxed validator no longer uppercases."""
    settings = ms.ModelSettings()
    project = active_project.ProjectState(set_code="  asd  ", settings=settings)
    active_project.write_active_project(project)

    loaded = active_project.read_active_project()
    assert loaded is not None
    assert loaded.set_code == "asd"


def test_write_rejects_empty_set_code():
    settings = ms.ModelSettings()
    project = active_project.ProjectState(set_code="   ", settings=settings)
    with pytest.raises(ValueError):
        active_project.write_active_project(project)


def test_clear_resets_to_none():
    settings = ms.ModelSettings()
    project = active_project.ProjectState(set_code="ABC", settings=settings)
    active_project.write_active_project(project)
    active_project.clear_active_project()
    assert active_project.read_active_project() is None


def test_apply_settings_updates_active_project():
    """``apply_settings`` rewrites the pointer's settings field so subsequent
    ``set_artifact_dir`` reads see the new value."""
    initial = ms.ModelSettings(asset_folder="D:/old")
    active_project.write_active_project(
        active_project.ProjectState(set_code="ABC", settings=initial)
    )

    updated = initial.model_copy(update={"asset_folder": "D:/new"})
    ms.apply_settings(updated)

    loaded = active_project.read_active_project()
    assert loaded is not None
    assert loaded.settings.asset_folder == "D:/new"
    assert loaded.set_code == "ABC"


def test_apply_settings_raises_when_no_project_open():
    from mtgai.io.asset_paths import NoAssetFolderError

    with pytest.raises(NoAssetFolderError):
        ms.apply_settings(ms.ModelSettings())


def test_require_active_project_raises_when_unset():
    from mtgai.io.asset_paths import NoAssetFolderError

    with pytest.raises(NoAssetFolderError):
        active_project.require_active_project()
