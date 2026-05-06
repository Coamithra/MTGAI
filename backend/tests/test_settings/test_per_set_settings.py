"""Settings module tests — global defaults, profiles, active-project surface."""

from __future__ import annotations

import pytest

from mtgai.runtime import active_project
from mtgai.settings import model_settings as ms


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path, monkeypatch):
    """Redirect on-disk paths the module reads/writes to a tmp tree.

    Settings + sets dirs are captured at module-import time as constants,
    so we patch them on the module itself for each test. The active
    project pointer is cleared between tests so the in-memory pointer
    can't bleed across runs.
    """
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir(parents=True)

    monkeypatch.setattr(ms, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(ms, "SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(ms, "GLOBAL_TOML", settings_dir / "global.toml")
    monkeypatch.setattr(ms, "LEGACY_CURRENT_TOML", settings_dir / "current.toml")
    monkeypatch.setattr(ms, "_global_cache", None, raising=False)

    active_project.clear_active_project()
    yield
    active_project.clear_active_project()
    monkeypatch.setattr(ms, "_global_cache", None, raising=False)


# ---------------------------------------------------------------------------
# get_active_settings + apply_settings
# ---------------------------------------------------------------------------


def test_get_active_settings_raises_when_no_project_open():
    from mtgai.io.asset_paths import NoAssetFolderError

    with pytest.raises(NoAssetFolderError):
        ms.get_active_settings()


def test_apply_settings_raises_when_no_project_open():
    from mtgai.io.asset_paths import NoAssetFolderError

    with pytest.raises(NoAssetFolderError):
        ms.apply_settings(ms.ModelSettings())


def test_apply_settings_updates_active_project_settings():
    """``apply_settings`` rewrites the active project's settings field
    so subsequent ``get_active_settings`` calls see the new value."""
    initial = ms.ModelSettings(asset_folder="D:/old")
    active_project.write_active_project(
        active_project.ProjectState(set_code="ASD", settings=initial)
    )
    updated = initial.model_copy(update={"asset_folder": "D:/new"})

    ms.apply_settings(updated)

    assert ms.get_active_settings().asset_folder == "D:/new"
    proj = active_project.read_active_project()
    assert proj is not None
    assert proj.set_code == "ASD"  # set_code is preserved


# ---------------------------------------------------------------------------
# Global settings + presets
# ---------------------------------------------------------------------------


def test_apply_global_settings_rejects_unknown_preset():
    """Unknown default_preset would silently fall back to defaults on every
    new set — surface it loudly instead."""
    with pytest.raises(ValueError):
        ms.apply_global_settings(ms.GlobalSettings(default_preset="typo-recommnded"))


def test_apply_global_settings_rejects_reserved_preset():
    with pytest.raises(ValueError):
        ms.apply_global_settings(ms.GlobalSettings(default_preset="global"))


def test_from_preset_rejects_reserved_names():
    """global / current are not user-facing profiles."""
    for name in ("global", "current"):
        with pytest.raises(ValueError):
            ms.ModelSettings.from_preset(name)


def test_from_preset_resolves_builtin():
    settings = ms.ModelSettings.from_preset("recommended")
    assert settings.llm_assignments["card_gen"] == "opus"


def test_global_toml_first_create_imports_legacy_as_profile():
    """When global.toml doesn't exist + current.toml does, we save it as
    'imported' and point default_preset there."""
    legacy = ms.ModelSettings(
        llm_assignments={"card_gen": "haiku"},
        image_assignments={},
        effort_overrides={},
    )
    legacy.write_toml(ms.LEGACY_CURRENT_TOML)

    glob = ms.get_global_settings()
    assert glob.default_preset == "imported"
    assert (ms.SETTINGS_DIR / "imported.toml").exists()
    assert ms.GLOBAL_TOML.exists()


def test_global_toml_first_create_no_legacy_uses_recommended():
    """No current.toml → default_preset stays 'recommended'."""
    glob = ms.get_global_settings()
    assert glob.default_preset == "recommended"
    assert ms.GLOBAL_TOML.exists()


def test_global_toml_round_trip(monkeypatch):
    """apply_global_settings persists, and a fresh load reads the new value."""
    new = ms.GlobalSettings(default_preset="all-haiku")
    ms.apply_global_settings(new)

    monkeypatch.setattr(ms, "_global_cache", None, raising=False)
    reloaded = ms.get_global_settings()
    assert reloaded.default_preset == "all-haiku"


# ---------------------------------------------------------------------------
# ModelSettings TOML round-trip + to_ui_dict
# ---------------------------------------------------------------------------


def test_settings_round_trips_set_params_break_points(tmp_path):
    s = ms.ModelSettings(
        set_params=ms.SetParams(set_name="Test Set", set_size=80, mechanic_count=5),
        break_points={"card_gen": "review", "balance": "review"},
    )
    path = tmp_path / "settings.toml"
    s.write_toml(path)

    loaded = ms.ModelSettings.load_from_file(path)
    assert loaded.set_params.set_name == "Test Set"
    assert loaded.set_params.set_size == 80
    assert loaded.set_params.mechanic_count == 5
    assert loaded.break_points == {"card_gen": "review", "balance": "review"}


def test_settings_round_trips_theme_input(tmp_path):
    s = ms.ModelSettings(
        theme_input=ms.ThemeInputSource(
            kind="pdf", filename="pitch.pdf", upload_id="abcd1234", char_count=12345
        ),
    )
    path = tmp_path / "settings.toml"
    s.write_toml(path)

    loaded = ms.ModelSettings.load_from_file(path)
    assert loaded.theme_input.kind == "pdf"
    assert loaded.theme_input.filename == "pitch.pdf"
    assert loaded.theme_input.upload_id == "abcd1234"
    assert loaded.theme_input.char_count == 12345


def test_default_theme_input_is_omitted_from_toml(tmp_path):
    """``kind == "none"`` is the bootstrap state; don't write it."""
    import tomllib

    s = ms.ModelSettings()
    path = tmp_path / "settings.toml"
    s.write_toml(path)

    with open(path, "rb") as f:
        data = tomllib.load(f)
    assert "theme_input" not in data


def test_to_ui_dict_includes_new_blocks():
    s = ms.ModelSettings(
        set_params=ms.SetParams(set_name="Z", set_size=50),
        break_points={"card_gen": "review"},
    )
    ui = s.to_ui_dict()
    assert ui["set_params"] == {"set_name": "Z", "set_size": 50, "mechanic_count": 3}
    assert ui["break_points"] == {"card_gen": "review"}
    assert ui["theme_input"]["kind"] == "none"


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


def test_save_profile_writes_to_global_library():
    custom = ms.ModelSettings(
        llm_assignments={"card_gen": "haiku"},
        image_assignments={},
        effort_overrides={},
    )
    path = custom.save_profile("my-profile")

    assert path == ms.SETTINGS_DIR / "my-profile.toml"
    assert path.exists()


def test_save_profile_rejects_reserved_names():
    s = ms.ModelSettings()
    for name in ("global", "current"):
        with pytest.raises(ValueError):
            s.save_profile(name)


def test_save_profile_rejects_empty_name():
    with pytest.raises(ValueError):
        ms.ModelSettings().save_profile("")


def test_list_profiles_excludes_reserved():
    ms.ModelSettings().save_profile("alpha")
    ms.ModelSettings().save_profile("beta")
    # Sneak global.toml + current.toml in.
    ms.GlobalSettings().write()
    ms.ModelSettings().write_toml(ms.LEGACY_CURRENT_TOML)

    assert ms.list_profiles() == ["alpha", "beta"]


def test_from_preset_resolves_saved_profile():
    """from_preset falls back to <SETTINGS_DIR>/<name>.toml when not built-in."""
    ms.ModelSettings(
        llm_assignments={"card_gen": "haiku"},
        image_assignments={},
        effort_overrides={},
    ).save_profile("my-profile")

    settings = ms.ModelSettings.from_preset("my-profile")
    assert settings.llm_assignments["card_gen"] == "haiku"


def test_from_preset_raises_for_unknown_name():
    with pytest.raises(ValueError):
        ms.ModelSettings.from_preset("does-not-exist")


def test_save_profile_strips_set_params_and_theme_input():
    """Profiles are reusable templates — per-set values must not leak in."""
    s = ms.ModelSettings(
        set_params=ms.SetParams(set_name="My Set", set_size=99),
        theme_input=ms.ThemeInputSource(kind="pdf", filename="x.pdf"),
        break_points={"card_gen": "review"},
    )
    path = s.save_profile("templ")

    import tomllib

    with open(path, "rb") as f:
        data = tomllib.load(f)
    assert "set_params" not in data
    assert "theme_input" not in data
    # Break points DO travel with the profile (§6.8).
    assert data.get("break_points") == {"card_gen": "review"}


# ---------------------------------------------------------------------------
# .mtg project file (dump / parse)
# ---------------------------------------------------------------------------


def test_dump_and_parse_project_toml_round_trip():
    settings = ms.ModelSettings(
        llm_assignments={"card_gen": "haiku"},
        set_params=ms.SetParams(set_name="Test", set_size=120, mechanic_count=4),
        asset_folder="D:/projects/test",
    )
    text = ms.dump_project_toml("XYZ", settings)
    set_code, parsed = ms.parse_project_toml(text)

    assert set_code == "XYZ"
    assert parsed.llm_assignments["card_gen"] == "haiku"
    assert parsed.set_params.set_name == "Test"
    assert parsed.asset_folder == "D:/projects/test"


def test_parse_project_toml_rejects_empty_set_code():
    text = """mtg_file_version = 1
set_code = ""
"""
    with pytest.raises(ValueError):
        ms.parse_project_toml(text)


def test_parse_project_toml_rejects_future_version():
    text = """mtg_file_version = 99
set_code = "ABC"
"""
    with pytest.raises(ValueError):
        ms.parse_project_toml(text)


def test_dump_project_toml_rejects_empty_set_code():
    with pytest.raises(ValueError):
        ms.dump_project_toml("", ms.ModelSettings())
