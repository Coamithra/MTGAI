"""Per-set model_settings + global.toml + migration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtgai.settings import model_settings as ms


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path, monkeypatch):
    """Redirect every path the module reads/writes to a tmp tree.

    Settings + sets dirs are captured at module-import time as constants,
    so we patch them on the module itself for each test. The cache is
    flushed too so tests don't see each other's state.
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

    ms.invalidate_cache()
    yield
    ms.invalidate_cache()


def _make_set_dir(set_code: str) -> Path:
    set_dir = ms.SETS_DIR / set_code
    set_dir.mkdir(parents=True, exist_ok=True)
    return set_dir


# ---------------------------------------------------------------------------
# get_settings(set_code)
# ---------------------------------------------------------------------------


def test_get_settings_requires_set_code():
    with pytest.raises(ValueError):
        ms.get_settings("")


@pytest.mark.parametrize("bad", ["A", "TOOLONG", "../etc", "AB-CD", "AB CD", "asd"])
def test_get_settings_rejects_invalid_set_codes(bad):
    """Lowercase and out-of-shape codes are rejected upfront so a typo
    can't poison output/sets/<garbage>/."""
    with pytest.raises(ValueError):
        ms.get_settings(bad)


def test_apply_settings_rejects_invalid_set_code():
    with pytest.raises(ValueError):
        ms.apply_settings("../escape", ms.ModelSettings())


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


def test_get_settings_seeds_default_preset_for_brand_new_set():
    """No legacy current.toml + no per-set file → seed from global default."""
    _make_set_dir("ASD")
    settings = ms.get_settings("ASD")

    # Default preset is "recommended", which assigns Opus to card_gen.
    assert settings.llm_assignments["card_gen"] == "opus"
    # Per-set file is now on disk.
    assert (ms.SETS_DIR / "ASD" / "settings.toml").exists()


def test_get_settings_caches_after_first_load():
    _make_set_dir("ASD")
    s1 = ms.get_settings("ASD")
    s2 = ms.get_settings("ASD")
    assert s1 is s2


def test_get_settings_loads_existing_per_set_file():
    """Hand-edited per-set TOML is round-tripped into a ModelSettings."""
    _make_set_dir("ASD")
    custom = ms.ModelSettings(
        llm_assignments={"card_gen": "haiku", "ai_review": "sonnet"},
        image_assignments={},
        effort_overrides={},
    )
    custom.write_toml(ms.SETS_DIR / "ASD" / "settings.toml")
    ms.invalidate_cache()

    loaded = ms.get_settings("ASD")
    assert loaded.llm_assignments["card_gen"] == "haiku"
    assert loaded.llm_assignments["ai_review"] == "sonnet"


def test_get_settings_isolated_per_set():
    """ASD changes don't bleed into DSN."""
    _make_set_dir("ASD")
    _make_set_dir("DSN")

    asd = ms.get_settings("ASD")
    dsn = ms.get_settings("DSN")

    new = ms.ModelSettings(
        llm_assignments={"card_gen": "haiku"},
        image_assignments=dict(asd.image_assignments),
        effort_overrides=dict(asd.effort_overrides),
    )
    ms.apply_settings("ASD", new)

    asd_after = ms.get_settings("ASD")
    dsn_after = ms.get_settings("DSN")

    assert asd_after.llm_assignments["card_gen"] == "haiku"
    assert dsn_after.llm_assignments["card_gen"] == dsn.llm_assignments["card_gen"]


def test_get_settings_recovers_from_corrupt_per_set_file():
    """Invalid TOML in settings.toml falls back to seeding (no crash)."""
    _make_set_dir("ASD")
    (ms.SETS_DIR / "ASD" / "settings.toml").write_text("{ not valid toml ::: ", encoding="utf-8")
    ms.invalidate_cache()

    settings = ms.get_settings("ASD")
    # Recovered to defaults; the corrupt file was overwritten with seed.
    assert "card_gen" in settings.llm_assignments


# ---------------------------------------------------------------------------
# Migration: legacy current.toml
# ---------------------------------------------------------------------------


def test_get_settings_migrates_from_legacy_current_toml():
    """A pre-existing current.toml seeds new sets with its values, not defaults."""
    legacy = ms.ModelSettings(
        llm_assignments={"card_gen": "haiku", "ai_review": "haiku"},
        image_assignments={"art_gen": "flux-local"},
        effort_overrides={},
    )
    legacy.write_toml(ms.LEGACY_CURRENT_TOML)
    _make_set_dir("ASD")

    settings = ms.get_settings("ASD")
    assert settings.llm_assignments["card_gen"] == "haiku"
    assert settings.llm_assignments["ai_review"] == "haiku"


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
    # global.toml is now persisted too.
    assert ms.GLOBAL_TOML.exists()


def test_global_toml_first_create_no_legacy_uses_recommended():
    """No current.toml → default_preset stays 'recommended'."""
    glob = ms.get_global_settings()
    assert glob.default_preset == "recommended"
    assert ms.GLOBAL_TOML.exists()


def test_global_toml_round_trip():
    """apply_global_settings persists + invalidates cache."""
    new = ms.GlobalSettings(default_preset="all-haiku")
    ms.apply_global_settings(new)

    ms.invalidate_cache()
    reloaded = ms.get_global_settings()
    assert reloaded.default_preset == "all-haiku"


def test_seed_uses_global_default_preset_when_set():
    """global.toml's default_preset wins over the built-in 'recommended'."""
    ms.apply_global_settings(ms.GlobalSettings(default_preset="all-haiku"))
    _make_set_dir("ASD")

    settings = ms.get_settings("ASD")
    # all-haiku assigns haiku to every stage, including card_gen.
    assert settings.llm_assignments["card_gen"] == "haiku"


# ---------------------------------------------------------------------------
# apply_settings + cache invalidation
# ---------------------------------------------------------------------------


def test_apply_settings_writes_only_target_set():
    _make_set_dir("ASD")
    _make_set_dir("DSN")
    # Touch both so files exist.
    ms.get_settings("ASD")
    ms.get_settings("DSN")

    asd_path = ms.SETS_DIR / "ASD" / "settings.toml"
    dsn_path = ms.SETS_DIR / "DSN" / "settings.toml"
    dsn_mtime = dsn_path.stat().st_mtime_ns

    new = ms.ModelSettings(
        llm_assignments={"card_gen": "sonnet"},
        image_assignments={},
        effort_overrides={},
    )
    ms.apply_settings("ASD", new)

    # ASD content actually changed (mtime alone is a tautology — it can't
    # go backwards even if apply did nothing).
    assert ms.ModelSettings.load_from_file(asd_path).llm_assignments["card_gen"] == "sonnet"
    # DSN was not touched.
    assert dsn_path.stat().st_mtime_ns == dsn_mtime


def test_apply_settings_replaces_cache():
    _make_set_dir("ASD")
    ms.get_settings("ASD")  # populate cache

    new = ms.ModelSettings(
        llm_assignments={"card_gen": "haiku"},
        image_assignments={},
        effort_overrides={},
    )
    ms.apply_settings("ASD", new)

    assert ms.get_settings("ASD").llm_assignments["card_gen"] == "haiku"


def test_apply_settings_requires_set_code():
    new = ms.ModelSettings()
    with pytest.raises(ValueError):
        ms.apply_settings("", new)


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------


def test_get_llm_model_resolves_via_registry():
    _make_set_dir("ASD")
    model_id = ms.get_llm_model("card_gen", "ASD")
    # 'recommended' assigns 'opus' to card_gen → registry resolves to claude-opus model_id.
    assert "opus" in model_id.lower()


def test_get_image_model_returns_key():
    _make_set_dir("ASD")
    key = ms.get_image_model("art_gen", "ASD")
    assert key == "flux-local"


def test_get_effort_returns_none_when_unset_for_stage():
    _make_set_dir("ASD")
    # 'recommended' doesn't set effort for theme_extract.
    assert ms.get_effort("theme_extract", "ASD") is None


def test_get_effort_returns_value_when_set():
    _make_set_dir("ASD")
    assert ms.get_effort("card_gen", "ASD") == "max"


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
