"""Unit tests for the persistent active-set selector."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mtgai.runtime import active_set


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path, monkeypatch):
    """Redirect every output-touching module to a tmp dir.

    Both ``active_set`` and the artifact resolver chain (asset_paths +
    model_settings) capture path constants at import time, so they have
    to be patched on the modules themselves. The model_settings cache is
    invalidated so each test sees a fresh seed.
    """
    from mtgai.io import asset_paths
    from mtgai.settings import model_settings as ms

    sets_root = tmp_path / "sets"
    settings_dir = tmp_path / "settings"
    sets_root.mkdir(parents=True)
    settings_dir.mkdir(parents=True)

    monkeypatch.setattr(active_set, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(active_set, "SETS_ROOT", sets_root)
    monkeypatch.setattr(active_set, "_SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(active_set, "_LAST_SET_PATH", settings_dir / "last_set.toml")
    monkeypatch.setattr(asset_paths, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(asset_paths, "SETS_ROOT", sets_root)
    monkeypatch.setattr(ms, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(ms, "SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(ms, "SETS_DIR", sets_root)
    monkeypatch.setattr(ms, "GLOBAL_TOML", settings_dir / "global.toml")
    monkeypatch.setattr(ms, "LEGACY_CURRENT_TOML", settings_dir / "current.toml")

    ms.invalidate_cache()
    yield
    ms.invalidate_cache()


def _make_set(set_code: str, *, theme_name: str | None = None) -> Path:
    """Materialise ``set_code`` as a registered project.

    ``settings.toml`` is the canonical "this project exists" marker —
    ``iter_known_set_codes`` filters dirs without one. Tests that just
    want a set discoverable need both the directory and the registry
    pointer; an empty TOML is enough since the model parses missing keys
    as defaults.
    """
    set_dir = active_set.SETS_ROOT / set_code
    set_dir.mkdir(parents=True, exist_ok=True)
    (set_dir / "settings.toml").write_text("", encoding="utf-8")
    if theme_name is not None:
        (set_dir / "theme.json").write_text(
            json.dumps({"code": set_code, "name": theme_name}), encoding="utf-8"
        )
    return set_dir


# ---------------------------------------------------------------------------
# is_valid_set_code
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code", ["AS", "ASD", "DRKSN", "AB12", "12345", "asd"])
def test_valid_codes(code):
    """Lowercase is auto-uppercased before validation."""
    assert active_set.is_valid_set_code(code)


@pytest.mark.parametrize(
    "code",
    [None, "", "A", "TOOLONG", "../etc", "AB-CD", "AB CD"],
)
def test_invalid_codes(code):
    assert not active_set.is_valid_set_code(code)


# ---------------------------------------------------------------------------
# read_active_set / write_active_set round-trip
# ---------------------------------------------------------------------------


def test_read_returns_none_when_file_missing():
    assert active_set.read_active_set() is None


def test_write_then_read_roundtrip():
    _make_set("ASD")
    active_set.write_active_set("ASD")
    assert active_set.read_active_set() == "ASD"


def test_write_normalizes_lowercase():
    _make_set("ASD")
    active_set.write_active_set("asd")
    assert active_set.read_active_set() == "ASD"


def test_write_rejects_invalid_code():
    with pytest.raises(ValueError):
        active_set.write_active_set("../escape")


def test_read_returns_none_when_set_dir_missing():
    """A persisted code whose dir was deleted is treated as no preference."""
    active_set._LAST_SET_PATH.parent.mkdir(parents=True, exist_ok=True)
    active_set._LAST_SET_PATH.write_text('[runtime]\nactive_set = "GONE"\n', encoding="utf-8")
    assert active_set.read_active_set() is None


def test_read_returns_none_on_garbage_toml():
    active_set._LAST_SET_PATH.parent.mkdir(parents=True, exist_ok=True)
    active_set._LAST_SET_PATH.write_text("[[[ not toml", encoding="utf-8")
    assert active_set.read_active_set() is None


def test_read_returns_none_when_payload_invalid():
    """File present but value isn't a valid set code -> None."""
    active_set._LAST_SET_PATH.parent.mkdir(parents=True, exist_ok=True)
    active_set._LAST_SET_PATH.write_text('[runtime]\nactive_set = "../escape"\n', encoding="utf-8")
    assert active_set.read_active_set() is None


def test_write_is_atomic(monkeypatch):
    """A write that fails partway must not corrupt the existing file."""
    _make_set("OLD")
    active_set.write_active_set("OLD")

    _make_set("NEW")

    # Patch the bound name on the active_set module rather than the
    # global os.replace — keeps the failure scope limited to the
    # write_active_set code path so unrelated stdlib calls during the
    # test (logging rotation, tempfile cleanup) aren't disrupted.
    def boom(*args, **kwargs):
        raise OSError("simulated")

    monkeypatch.setattr(active_set.os, "replace", boom)
    with pytest.raises(OSError):
        active_set.write_active_set("NEW")

    # read_active_set doesn't go through os.replace, so the patch
    # doesn't interfere with the assertion below.
    assert active_set.read_active_set() == "OLD"


# ---------------------------------------------------------------------------
# list_sets
# ---------------------------------------------------------------------------


def test_list_sets_empty_when_root_missing(tmp_path, monkeypatch):
    """SETS_ROOT not present at all -> empty list, not crash."""
    monkeypatch.setattr(active_set, "SETS_ROOT", tmp_path / "absent")
    assert active_set.list_sets() == []


def test_list_sets_returns_directories_in_alpha_order():
    _make_set("ASD", theme_name="Anomalous Descent")
    _make_set("DKSN")
    _make_set("DS1", theme_name="Demo")

    sets = active_set.list_sets()
    assert [s["code"] for s in sets] == ["ASD", "DKSN", "DS1"]


def test_list_sets_includes_theme_name_when_present():
    _make_set("ASD", theme_name="Anomalous Descent")
    _make_set("DKSN")  # no theme.json

    sets = active_set.list_sets()
    by_code = {s["code"]: s["name"] for s in sets}
    assert by_code["ASD"] == "Anomalous Descent"
    assert by_code["DKSN"] is None


def test_list_sets_skips_dirs_outside_set_code_shape():
    """A real-world quirk — pre-existing repos may have set dirs whose
    names are longer than the regex (e.g. 'DARKSUN'). The picker hides
    them so the new-set scaffold can't produce paths the theme
    endpoints would reject as malformed."""
    _make_set("ASD", theme_name="Anomalous Descent")
    _make_set("DARKSUN")  # 7 chars — outside the [A-Z0-9]{2,5} shape

    sets = active_set.list_sets()
    assert [s["code"] for s in sets] == ["ASD"]


def test_list_sets_skips_non_set_directories():
    """Stray dirs that don't match the set-code regex don't show up."""
    _make_set("ASD")
    (active_set.SETS_ROOT / ".cache").mkdir()
    (active_set.SETS_ROOT / "scratch-notes").mkdir()
    sets = active_set.list_sets()
    assert [s["code"] for s in sets] == ["ASD"]


def test_list_sets_skips_files():
    _make_set("ASD")
    (active_set.SETS_ROOT / "stray.txt").write_text("hi", encoding="utf-8")
    sets = active_set.list_sets()
    assert [s["code"] for s in sets] == ["ASD"]


def test_list_sets_handles_corrupt_theme_json():
    """A malformed theme.json doesn't bubble — name just falls to None."""
    _make_set("ASD")
    (active_set.SETS_ROOT / "ASD" / "theme.json").write_text("{ not valid", encoding="utf-8")
    sets = active_set.list_sets()
    assert sets == [{"code": "ASD", "name": None}]


def test_list_sets_treats_blank_name_as_missing():
    _make_set("ASD", theme_name="   ")  # whitespace only
    sets = active_set.list_sets()
    assert sets == [{"code": "ASD", "name": None}]


# ---------------------------------------------------------------------------
# create_set
# ---------------------------------------------------------------------------


def test_create_set_makes_dir_without_name():
    active_set.create_set("NEW")
    assert (active_set.SETS_ROOT / "NEW").is_dir()
    assert not (active_set.SETS_ROOT / "NEW" / "theme.json").exists()


def test_create_set_writes_stub_theme_when_named():
    active_set.create_set("NEW", name="My Set")
    theme_path = active_set.SETS_ROOT / "NEW" / "theme.json"
    assert theme_path.exists()
    data = json.loads(theme_path.read_text(encoding="utf-8"))
    assert data == {"code": "NEW", "name": "My Set"}


def test_create_set_normalizes_lowercase():
    active_set.create_set("new")
    assert (active_set.SETS_ROOT / "NEW").is_dir()


def test_create_set_rejects_existing():
    _make_set("ASD")
    with pytest.raises(FileExistsError):
        active_set.create_set("ASD")


def test_create_set_rejects_invalid_code():
    with pytest.raises(ValueError):
        active_set.create_set("../escape")


def test_create_set_treats_blank_name_as_unnamed():
    active_set.create_set("NEW", name="   ")
    assert not (active_set.SETS_ROOT / "NEW" / "theme.json").exists()
