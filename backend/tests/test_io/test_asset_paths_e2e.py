"""End-to-end smoke test for asset_folder routing.

Verifies that when a project's settings.toml carries ``asset_folder``,
stage clearers + the stages._set_dir helper land in that folder instead
of the legacy ``output/sets/<CODE>/`` path. Targets the cheapest stage
(skeleton) since the full runners pull in heavy LLM dependencies; the
clearer dispatch is what proves the routing is in place for everything
that downstream stages also use.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from mtgai.io import asset_paths
from mtgai.pipeline import stages as stages_mod
from mtgai.settings import model_settings as ms


@pytest.fixture
def configured_project(tmp_path, monkeypatch) -> Iterator[tuple[str, Path, Path]]:
    """Configure a project whose ``asset_folder`` points outside ``output/``.

    Returns ``(set_code, legacy_dir, asset_dir)`` so tests can assert
    that artifacts land in ``asset_dir`` and *not* the legacy path.
    """
    sets_root = tmp_path / "output" / "sets"
    settings_dir = tmp_path / "output" / "settings"
    sets_root.mkdir(parents=True)
    settings_dir.mkdir(parents=True)
    asset_dir = tmp_path / "external" / "my-project"
    asset_dir.mkdir(parents=True)

    monkeypatch.setattr(asset_paths, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(asset_paths, "SETS_ROOT", sets_root)
    monkeypatch.setattr(stages_mod, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(ms, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(ms, "SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(ms, "SETS_DIR", sets_root)
    monkeypatch.setattr(ms, "GLOBAL_TOML", settings_dir / "global.toml")
    monkeypatch.setattr(ms, "LEGACY_CURRENT_TOML", settings_dir / "current.toml")
    ms.invalidate_cache()

    code = "TST"
    ms.apply_settings(code, ms.ModelSettings(asset_folder=str(asset_dir)))
    legacy_dir = sets_root / code

    yield code, legacy_dir, asset_dir
    ms.invalidate_cache()


def test_set_dir_resolves_to_asset_folder(configured_project):
    """``stages._set_dir`` honours the project's configured ``asset_folder``."""
    code, _legacy_dir, asset_dir = configured_project
    assert stages_mod._set_dir(code) == asset_dir


def test_skeleton_clearer_targets_asset_folder(configured_project):
    """``clear_skeleton`` removes the skeleton.json under ``asset_folder``."""
    code, legacy_dir, asset_dir = configured_project

    # Seed a skeleton file in the asset folder. The legacy location stays
    # empty so we can prove the clearer doesn't accidentally fall back.
    skel_path = asset_dir / "skeleton.json"
    skel_path.write_text("{}", encoding="utf-8")
    legacy_skel = legacy_dir / "skeleton.json"
    assert not legacy_skel.exists()

    stages_mod.clear_stage_artifacts("skeleton", code)

    assert not skel_path.exists(), "asset-folder skeleton should be gone"
    assert not legacy_skel.exists(), "legacy path must stay untouched"


def test_card_gen_clearer_targets_asset_folder(configured_project):
    """``clear_card_gen`` wipes the cards/ dir under ``asset_folder``."""
    code, legacy_dir, asset_dir = configured_project

    cards_dir = asset_dir / "cards"
    cards_dir.mkdir(parents=True)
    (cards_dir / "001_test.json").write_text("{}", encoding="utf-8")
    legacy_cards = legacy_dir / "cards"
    assert not legacy_cards.exists()

    stages_mod.clear_stage_artifacts("card_gen", code)

    assert not cards_dir.exists(), "asset-folder cards/ should be gone"
    assert not legacy_cards.exists(), "legacy cards/ must stay untouched"


def test_render_clearer_targets_asset_folder(configured_project):
    """``clear_rendering`` wipes the renders/ dir under ``asset_folder``."""
    code, legacy_dir, asset_dir = configured_project

    renders_dir = asset_dir / "renders"
    renders_dir.mkdir(parents=True)
    (renders_dir / "001_test.png").write_bytes(b"\x89PNG")
    legacy_renders = legacy_dir / "renders"
    assert not legacy_renders.exists()

    stages_mod.clear_stage_artifacts("rendering", code)

    assert not renders_dir.exists(), "asset-folder renders/ should be gone"
    assert not legacy_renders.exists(), "legacy renders/ must stay untouched"


def test_settings_toml_stays_in_canonical_location(configured_project):
    """``settings.toml`` is the project registry — always at ``output/sets/<CODE>/``.

    Phase 2 routes stage *artifacts* via ``asset_folder`` but leaves the
    settings.toml at the canonical location so the project remains
    discoverable through the legacy registry path. This is the
    chicken-and-egg foundation: ``set_artifact_dir`` consults
    settings.toml to find the asset_folder, so it can't itself live in
    the asset folder.
    """
    code, legacy_dir, asset_dir = configured_project

    legacy_settings = legacy_dir / "settings.toml"
    asset_settings = asset_dir / "settings.toml"
    assert legacy_settings.exists(), "settings.toml should be at the canonical location"
    assert not asset_settings.exists(), "settings.toml should NOT be in asset_folder"


def test_legacy_default_when_asset_folder_unset(tmp_path, monkeypatch):
    """A project with no ``asset_folder`` keeps the legacy layout."""
    sets_root = tmp_path / "output" / "sets"
    settings_dir = tmp_path / "output" / "settings"
    sets_root.mkdir(parents=True)
    settings_dir.mkdir(parents=True)

    monkeypatch.setattr(asset_paths, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(asset_paths, "SETS_ROOT", sets_root)
    monkeypatch.setattr(stages_mod, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(ms, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(ms, "SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(ms, "SETS_DIR", sets_root)
    monkeypatch.setattr(ms, "GLOBAL_TOML", settings_dir / "global.toml")
    monkeypatch.setattr(ms, "LEGACY_CURRENT_TOML", settings_dir / "current.toml")
    ms.invalidate_cache()

    code = "OLD"
    ms.apply_settings(code, ms.ModelSettings(asset_folder=""))
    legacy_dir = sets_root / code

    skel_path = legacy_dir / "skeleton.json"
    skel_path.parent.mkdir(parents=True, exist_ok=True)
    skel_path.write_text("{}", encoding="utf-8")

    stages_mod.clear_stage_artifacts("skeleton", code)

    assert not skel_path.exists()
    ms.invalidate_cache()


def test_pipeline_state_lives_under_asset_folder(configured_project):
    """``pipeline-state.json`` resolves under the project's ``asset_folder``."""
    from mtgai.pipeline.engine import _state_path

    code, legacy_dir, asset_dir = configured_project
    expected = asset_dir / "pipeline-state.json"
    assert _state_path(code) == expected
    assert _state_path(code).parent == asset_dir
    assert (legacy_dir / "pipeline-state.json") != _state_path(code)


def test_theme_path_resolves_under_asset_folder(configured_project):
    """The wizard-side theme loader reads ``theme.json`` from the asset folder."""
    from mtgai.pipeline.wizard import _load_theme_for

    code, legacy_dir, asset_dir = configured_project

    theme_payload = {"code": code, "name": "Routed", "setting": "asset folder"}
    (asset_dir / "theme.json").write_text(json.dumps(theme_payload), encoding="utf-8")
    # Drop a decoy at the legacy location to prove the loader doesn't fall back.
    (legacy_dir / "theme.json").write_text(
        json.dumps({"code": code, "name": "Legacy decoy"}), encoding="utf-8"
    )

    loaded = _load_theme_for(code)
    assert loaded == theme_payload
