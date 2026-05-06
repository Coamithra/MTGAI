"""Tests for the project-aware artifact path helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtgai.io import asset_paths
from mtgai.runtime import active_project
from mtgai.settings import model_settings as ms


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path, monkeypatch):
    """Point the settings module at a tmp tree + clear the active-project pointer."""
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir(parents=True)

    monkeypatch.setattr(ms, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(ms, "SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(ms, "GLOBAL_TOML", settings_dir / "global.toml")
    monkeypatch.setattr(ms, "LEGACY_CURRENT_TOML", settings_dir / "current.toml")

    active_project.clear_active_project()
    yield
    active_project.clear_active_project()


def _open_project(code: str, asset_folder: str) -> None:
    """Helper: pin ``code`` as the active project with the given asset folder."""
    active_project.write_active_project(
        active_project.ProjectState(
            set_code=code, settings=ms.ModelSettings(asset_folder=asset_folder)
        )
    )


def test_raises_when_no_project_open():
    """No active project → :class:`NoAssetFolderError`."""
    with pytest.raises(asset_paths.NoAssetFolderError):
        asset_paths.set_artifact_dir()


def test_raises_when_asset_folder_empty():
    """Active project with empty ``asset_folder`` → :class:`NoAssetFolderError`.

    The legacy fallback to ``output/sets/<CODE>/`` was removed; callers
    surface a 409 instead of silently writing to the registry path.
    """
    _open_project("ABC", "")
    with pytest.raises(asset_paths.NoAssetFolderError):
        asset_paths.set_artifact_dir()


def test_returns_configured_asset_folder(tmp_path):
    """A non-empty ``asset_folder`` is returned verbatim as a Path."""
    target = tmp_path / "external" / "my-project"
    _open_project("DEF", str(target))
    assert asset_paths.set_artifact_dir() == target


def test_helper_does_not_mkdir(tmp_path):
    """Resolution is path-only; writers stay responsible for mkdir.

    Stage runners must ``parent.mkdir(parents=True, exist_ok=True)`` the
    same way they did under the legacy layout — the helper must not
    silently create the asset folder on a read-only path (e.g. inside
    ``clear_*`` helpers).
    """
    target = tmp_path / "external" / "absent"
    _open_project("GHI", str(target))
    resolved = asset_paths.set_artifact_dir()
    assert resolved == target
    assert not target.exists()


def test_helper_returns_pathlib_path():
    """``asset_folder`` is stored as a string; the helper must wrap it."""
    _open_project("JKL", "D:/proj/jkl")
    result = asset_paths.set_artifact_dir()
    assert isinstance(result, Path)
