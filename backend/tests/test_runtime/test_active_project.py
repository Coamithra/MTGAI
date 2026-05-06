"""Unit tests for the :class:`ProjectState` API.

The shim functions (``read_active_set`` / ``write_active_set`` /
``clear_active_set``) are covered in ``test_active_set.py``; this
module pins the new ProjectState-shaped surface that callers will
migrate to in a follow-up.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mtgai.runtime import active_project
from mtgai.settings import model_settings as ms


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Patch path constants + clear the active-project pointer between tests."""
    sets_root = tmp_path / "sets"
    settings_dir = tmp_path / "settings"
    sets_root.mkdir(parents=True)
    settings_dir.mkdir(parents=True)

    monkeypatch.setattr(active_project, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(active_project, "SETS_ROOT", sets_root)
    monkeypatch.setattr(ms, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(ms, "SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(ms, "SETS_DIR", sets_root)
    monkeypatch.setattr(ms, "GLOBAL_TOML", settings_dir / "global.toml")
    monkeypatch.setattr(ms, "LEGACY_CURRENT_TOML", settings_dir / "current.toml")

    active_project.clear_active_project()
    ms.invalidate_cache()
    yield
    active_project.clear_active_project()
    ms.invalidate_cache()


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


def test_write_normalises_lowercase_set_code():
    settings = ms.ModelSettings()
    project = active_project.ProjectState(set_code="asd", settings=settings)
    active_project.write_active_project(project)

    loaded = active_project.read_active_project()
    assert loaded is not None
    assert loaded.set_code == "ASD"


def test_write_rejects_invalid_set_code():
    settings = ms.ModelSettings()
    project = active_project.ProjectState(set_code="../escape", settings=settings)
    with pytest.raises(ValueError):
        active_project.write_active_project(project)


def test_clear_resets_to_none():
    settings = ms.ModelSettings()
    project = active_project.ProjectState(set_code="ABC", settings=settings)
    active_project.write_active_project(project)
    active_project.clear_active_project()
    assert active_project.read_active_project() is None


def test_apply_settings_syncs_active_project():
    """``apply_settings`` for the active project rebuilds the pointer's settings.

    Required so ``set_artifact_dir`` (which reads
    ``_active_project.settings.asset_folder``) sees changes made via
    the live-apply endpoints without a cache round-trip.
    """
    initial = ms.ModelSettings(asset_folder="D:/old")
    ms.apply_settings("ABC", initial)
    active_project.write_active_set("ABC")

    updated = initial.model_copy(update={"asset_folder": "D:/new"})
    ms.apply_settings("ABC", updated)

    project = active_project.read_active_project()
    assert project is not None
    assert project.settings.asset_folder == "D:/new"


def test_apply_settings_for_other_set_does_not_touch_active_project():
    """Editing a non-active set leaves the active ProjectState alone."""
    ms.apply_settings("ABC", ms.ModelSettings(asset_folder="D:/abc"))
    active_project.write_active_set("ABC")

    ms.apply_settings("XYZ", ms.ModelSettings(asset_folder="D:/xyz"))

    project = active_project.read_active_project()
    assert project is not None
    assert project.set_code == "ABC"
    assert project.settings.asset_folder == "D:/abc"


def test_write_active_set_shim_builds_project_state_from_cache():
    """The legacy ``write_active_set(code)`` shim packs ``get_settings``
    into a ProjectState so callers that haven't migrated yet still
    leave the new pointer fully populated."""
    ms.apply_settings("ASD", ms.ModelSettings(asset_folder="D:/asd"))
    active_project.write_active_set("ASD")

    project = active_project.read_active_project()
    assert project is not None
    assert project.set_code == "ASD"
    assert project.settings.asset_folder == "D:/asd"
    assert project.mtg_path is None
