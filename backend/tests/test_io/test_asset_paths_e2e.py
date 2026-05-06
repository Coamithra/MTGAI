"""End-to-end smoke test for asset_folder routing.

Verifies that when the active project's settings carry ``asset_folder``,
stage clearers + the stages._set_dir helper land in that folder. The
legacy fallback to ``output/sets/<CODE>/`` is gone — endpoints surface a
409 when no asset folder is configured (covered by the unit tests on
``set_artifact_dir`` itself).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from mtgai.io import asset_paths
from mtgai.pipeline import stages as stages_mod
from mtgai.runtime import active_project
from mtgai.settings import model_settings as ms


@pytest.fixture
def configured_project(tmp_path, monkeypatch) -> Iterator[tuple[str, Path]]:
    """Configure an active project whose ``asset_folder`` points outside ``output/``.

    Returns ``(set_code, asset_dir)`` so tests can assert that artifacts
    land in ``asset_dir``.
    """
    settings_dir = tmp_path / "output" / "settings"
    settings_dir.mkdir(parents=True)
    asset_dir = tmp_path / "external" / "my-project"
    asset_dir.mkdir(parents=True)

    monkeypatch.setattr(ms, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(ms, "SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(ms, "GLOBAL_TOML", settings_dir / "global.toml")
    monkeypatch.setattr(ms, "LEGACY_CURRENT_TOML", settings_dir / "current.toml")
    active_project.clear_active_project()

    code = "TST"
    active_project.write_active_project(
        active_project.ProjectState(
            set_code=code, settings=ms.ModelSettings(asset_folder=str(asset_dir))
        )
    )

    yield code, asset_dir
    active_project.clear_active_project()


def test_set_dir_resolves_to_asset_folder(configured_project):
    """``stages._set_dir`` honours the active project's configured ``asset_folder``."""
    _code, asset_dir = configured_project
    assert stages_mod._set_dir() == asset_dir


def test_skeleton_clearer_targets_asset_folder(configured_project):
    """``clear_skeleton`` removes the skeleton.json under ``asset_folder``."""
    _code, asset_dir = configured_project

    skel_path = asset_dir / "skeleton.json"
    skel_path.write_text("{}", encoding="utf-8")

    stages_mod.clear_stage_artifacts("skeleton")

    assert not skel_path.exists(), "asset-folder skeleton should be gone"


def test_card_gen_clearer_targets_asset_folder(configured_project):
    """``clear_card_gen`` wipes the cards/ dir under ``asset_folder``."""
    _code, asset_dir = configured_project

    cards_dir = asset_dir / "cards"
    cards_dir.mkdir(parents=True)
    (cards_dir / "001_test.json").write_text("{}", encoding="utf-8")

    stages_mod.clear_stage_artifacts("card_gen")

    assert not cards_dir.exists(), "asset-folder cards/ should be gone"


def test_render_clearer_targets_asset_folder(configured_project):
    """``clear_rendering`` wipes the renders/ dir under ``asset_folder``."""
    _code, asset_dir = configured_project

    renders_dir = asset_dir / "renders"
    renders_dir.mkdir(parents=True)
    (renders_dir / "001_test.png").write_bytes(b"\x89PNG")

    stages_mod.clear_stage_artifacts("rendering")

    assert not renders_dir.exists(), "asset-folder renders/ should be gone"


def test_set_artifact_dir_raises_when_no_asset_folder(tmp_path, monkeypatch):
    """An active project with empty ``asset_folder`` → :class:`NoAssetFolderError`.

    The legacy fallback to ``output/sets/<CODE>/`` was removed; callers
    surface a 409 instead of silently writing to the registry path.
    """
    settings_dir = tmp_path / "output" / "settings"
    settings_dir.mkdir(parents=True)

    monkeypatch.setattr(ms, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(ms, "SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(ms, "GLOBAL_TOML", settings_dir / "global.toml")
    monkeypatch.setattr(ms, "LEGACY_CURRENT_TOML", settings_dir / "current.toml")
    active_project.clear_active_project()

    active_project.write_active_project(
        active_project.ProjectState(set_code="OLD", settings=ms.ModelSettings(asset_folder=""))
    )

    with pytest.raises(asset_paths.NoAssetFolderError):
        asset_paths.set_artifact_dir()

    active_project.clear_active_project()


def test_pipeline_state_lives_under_asset_folder(configured_project):
    """``pipeline-state.json`` resolves under the active project's ``asset_folder``."""
    from mtgai.pipeline.engine import _state_path

    _code, asset_dir = configured_project
    expected = asset_dir / "pipeline-state.json"
    assert _state_path() == expected
    assert _state_path().parent == asset_dir


def test_theme_path_resolves_under_asset_folder(configured_project):
    """The wizard-side theme loader reads ``theme.json`` from the asset folder."""
    from mtgai.pipeline.wizard import _load_active_theme

    code, asset_dir = configured_project

    theme_payload = {"code": code, "name": "Routed", "setting": "asset folder"}
    (asset_dir / "theme.json").write_text(json.dumps(theme_payload), encoding="utf-8")

    loaded = _load_active_theme()
    assert loaded == theme_payload
