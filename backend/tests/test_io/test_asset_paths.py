"""Tests for the project-aware artifact path helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtgai.io import asset_paths
from mtgai.runtime import active_project
from mtgai.settings import model_settings as ms


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path, monkeypatch):
    """Point both modules at a tmp tree.

    ``model_settings`` and ``asset_paths`` each capture path constants
    at import time. The settings module is the source of truth for
    ``asset_folder`` and the asset_paths module reads from the active
    project, so we patch both and clear the active-project pointer
    between tests.
    """
    settings_dir = tmp_path / "settings"
    sets_dir = tmp_path / "sets"
    settings_dir.mkdir(parents=True)
    sets_dir.mkdir(parents=True)

    monkeypatch.setattr(ms, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(ms, "SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(ms, "SETS_DIR", sets_dir)
    monkeypatch.setattr(ms, "GLOBAL_TOML", settings_dir / "global.toml")
    monkeypatch.setattr(ms, "LEGACY_CURRENT_TOML", settings_dir / "current.toml")
    monkeypatch.setattr(asset_paths, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(asset_paths, "SETS_ROOT", sets_dir)

    ms.invalidate_cache()
    active_project.clear_active_set()
    yield
    active_project.clear_active_set()
    ms.invalidate_cache()


def _open_project(code: str, asset_folder: str) -> None:
    """Helper: pin ``code`` as the active project with the given asset folder."""
    ms.apply_settings(code, ms.ModelSettings(asset_folder=asset_folder))
    active_project.write_active_set(code)


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
