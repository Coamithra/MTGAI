"""Unit tests for the in-memory active-project pointer."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from mtgai.runtime import active_set, ai_lock


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path, monkeypatch):
    """Redirect output-touching modules at a tmp dir + clear in-memory state.

    ``active_set`` and ``asset_paths`` capture path constants at import
    time, so they have to be patched on the modules themselves. The
    in-memory active-project pointer is cleared between tests so leakage
    can't taint a later assertion.
    """
    from mtgai.io import asset_paths
    from mtgai.settings import model_settings as ms

    sets_root = tmp_path / "sets"
    sets_root.mkdir(parents=True)

    monkeypatch.setattr(active_set, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(active_set, "SETS_ROOT", sets_root)
    monkeypatch.setattr(asset_paths, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(asset_paths, "SETS_ROOT", sets_root)
    monkeypatch.setattr(ms, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(ms, "SETS_DIR", sets_root)
    monkeypatch.setattr(ms, "SETTINGS_DIR", tmp_path / "settings")
    monkeypatch.setattr(ms, "GLOBAL_TOML", tmp_path / "settings" / "global.toml")
    monkeypatch.setattr(ms, "LEGACY_CURRENT_TOML", tmp_path / "settings" / "current.toml")

    active_set.clear_active_set()
    ai_lock.reset_for_tests()
    ms.invalidate_cache()
    yield
    active_set.clear_active_set()
    ai_lock.reset_for_tests()
    ms.invalidate_cache()


def _make_set(set_code: str) -> Path:
    """Materialise ``set_code`` as a registered project for iter checks."""
    set_dir = active_set.SETS_ROOT / set_code
    set_dir.mkdir(parents=True, exist_ok=True)
    (set_dir / "settings.toml").write_text("", encoding="utf-8")
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
# read / write / clear round-trip
# ---------------------------------------------------------------------------


def test_read_returns_none_when_unset():
    assert active_set.read_active_set() is None


def test_write_then_read_roundtrip():
    active_set.write_active_set("ASD")
    assert active_set.read_active_set() == "ASD"


def test_write_normalizes_lowercase():
    active_set.write_active_set("asd")
    assert active_set.read_active_set() == "ASD"


def test_write_rejects_invalid_code():
    with pytest.raises(ValueError):
        active_set.write_active_set("../escape")


def test_clear_resets_to_none():
    active_set.write_active_set("ASD")
    active_set.clear_active_set()
    assert active_set.read_active_set() is None


# ---------------------------------------------------------------------------
# iter_known_set_codes
# ---------------------------------------------------------------------------


def test_iter_returns_empty_when_root_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(active_set, "SETS_ROOT", tmp_path / "absent")
    assert active_set.iter_known_set_codes() == []


def test_iter_lists_registered_projects_alpha():
    _make_set("ASD")
    _make_set("DKSN")
    _make_set("DS1")
    assert active_set.iter_known_set_codes() == ["ASD", "DKSN", "DS1"]


def test_iter_skips_unregistered_dirs():
    _make_set("ASD")
    (active_set.SETS_ROOT / "DKSN").mkdir()  # no settings.toml
    assert active_set.iter_known_set_codes() == ["ASD"]


def test_iter_skips_dirs_outside_set_code_shape():
    _make_set("ASD")
    (active_set.SETS_ROOT / "DARKSUN").mkdir()  # 7 chars, > regex limit
    (active_set.SETS_ROOT / "DARKSUN" / "settings.toml").write_text("", encoding="utf-8")
    assert active_set.iter_known_set_codes() == ["ASD"]


# ---------------------------------------------------------------------------
# await_lock_release
# ---------------------------------------------------------------------------


def test_await_returns_true_when_idle():
    assert active_set.await_lock_release(deadline_s=0.5) is True


def test_await_returns_true_when_lock_releases_in_time():
    """Background thread holds the lock for 200 ms; deadline is 2 s."""

    def _hold_briefly() -> None:
        with ai_lock.hold("test"):
            time.sleep(0.2)

    t = threading.Thread(target=_hold_briefly, daemon=True)
    t.start()
    # Give the thread a moment to actually acquire before we start polling.
    time.sleep(0.05)
    assert ai_lock.is_running()
    assert active_set.await_lock_release(deadline_s=2.0) is True
    t.join(timeout=1.0)
    assert not ai_lock.is_running()


def test_await_returns_false_on_timeout():
    """Lock held longer than the deadline -> False, lock still held on return."""
    release_event = threading.Event()

    def _hold_until_event() -> None:
        with ai_lock.hold("test"):
            release_event.wait(timeout=2.0)

    t = threading.Thread(target=_hold_until_event, daemon=True)
    t.start()
    time.sleep(0.05)
    assert ai_lock.is_running()
    assert active_set.await_lock_release(deadline_s=0.3) is False
    assert ai_lock.is_running()  # still held
    release_event.set()
    t.join(timeout=2.0)
