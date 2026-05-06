"""Tests for the project-aware artifact path helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtgai.io import asset_paths
from mtgai.settings import model_settings as ms


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path, monkeypatch):
    """Point both modules at a tmp tree.

    ``model_settings`` and ``asset_paths`` each capture path constants
    at import time. The settings module is the source of truth for
    `asset_folder`, so it has to read settings.toml from the same tmp
    location ``asset_paths`` falls back to when no folder is configured.
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
    yield
    ms.invalidate_cache()


def test_legacy_default_when_asset_folder_unset(tmp_path):
    """A set with no ``asset_folder`` falls back to ``output/sets/<CODE>/``."""
    (tmp_path / "sets" / "ABC").mkdir(parents=True)
    ms.apply_settings("ABC", ms.ModelSettings(asset_folder=""))
    assert asset_paths.set_artifact_dir("ABC") == tmp_path / "sets" / "ABC"


def test_returns_configured_asset_folder(tmp_path):
    """A non-empty ``asset_folder`` is returned verbatim as a Path."""
    (tmp_path / "sets" / "DEF").mkdir(parents=True)
    target = tmp_path / "external" / "my-project"
    ms.apply_settings("DEF", ms.ModelSettings(asset_folder=str(target)))
    assert asset_paths.set_artifact_dir("DEF") == target


def test_helper_does_not_mkdir(tmp_path):
    """Resolution is path-only; writers stay responsible for mkdir.

    Mirrors the legacy ``OUTPUT_ROOT / 'sets' / set_code`` behaviour so
    swapping the call site doesn't accidentally create the asset folder
    on a read-only path (e.g. inside ``clear_*`` helpers).
    """
    (tmp_path / "sets" / "GHI").mkdir(parents=True)
    target = tmp_path / "external" / "absent"
    ms.apply_settings("GHI", ms.ModelSettings(asset_folder=str(target)))
    resolved = asset_paths.set_artifact_dir("GHI")
    assert resolved == target
    assert not target.exists()


def test_brand_new_set_seeds_legacy_path(tmp_path):
    """A set with no settings.toml yet seeds defaults (asset_folder='') and
    falls back to the legacy path. Important: this is what happens when a
    new code is referenced before the wizard has materialised it."""
    # No prior apply_settings — the helper must trigger the seeding path.
    assert asset_paths.set_artifact_dir("NEW") == tmp_path / "sets" / "NEW"


def test_helper_returns_pathlib_path(tmp_path):
    """``asset_folder`` is stored as a string; the helper must wrap it."""
    (tmp_path / "sets" / "JKL").mkdir(parents=True)
    ms.apply_settings("JKL", ms.ModelSettings(asset_folder="D:/proj/jkl"))
    result = asset_paths.set_artifact_dir("JKL")
    assert isinstance(result, Path)
