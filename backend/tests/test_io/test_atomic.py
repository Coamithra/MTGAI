"""Tests for atomic, retry-resilient file writes (``mtgai.io.atomic``)."""

import os
from pathlib import Path

import pytest

from mtgai.io.atomic import atomic_write_bytes, atomic_write_text, replace_with_retry


def test_atomic_write_text_round_trip(tmp_path: Path):
    """Content lands intact and the return value is the path written."""
    target = tmp_path / "state.json"
    result = atomic_write_text(target, '{"k": "v"}')
    assert result == target
    assert target.read_text(encoding="utf-8") == '{"k": "v"}'


def test_atomic_write_creates_parent_dirs(tmp_path: Path):
    """Missing parent directories are created, like the engine relies on."""
    target = tmp_path / "deep" / "nested" / "out.json"
    atomic_write_text(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"


def test_atomic_write_overwrites_atomically(tmp_path: Path):
    """A second write replaces the first; no temp residue is left behind."""
    target = tmp_path / "state.json"
    atomic_write_text(target, "first")
    atomic_write_text(target, "second")
    assert target.read_text(encoding="utf-8") == "second"
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "state.json"]
    assert leftovers == []


def test_atomic_write_bytes_round_trip(tmp_path: Path):
    target = tmp_path / "blob.bin"
    payload = bytes(range(256))
    atomic_write_bytes(target, payload)
    assert target.read_bytes() == payload


def _make_os_error(winerror: int | None, errno_val: int) -> OSError:
    """Build an OSError that looks like the real thing.

    On Windows the 4-arg form sets the read-only ``.winerror`` slot (and
    derives ``.errno`` from it). Off Windows ``.winerror`` is always None, so
    ``_is_transient`` falls back to the ``errno`` check — which is exactly the
    code path we want to exercise there.
    """
    if winerror is not None:
        return OSError(errno_val, "boom", None, winerror)
    return OSError(errno_val, "boom")


def test_replace_retries_then_succeeds(tmp_path: Path, monkeypatch):
    """A transient WinError-5 on the first attempt is retried, not raised."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.write_text("payload", encoding="utf-8")

    real_replace = os.replace
    calls = {"n": 0}

    def flaky_replace(a, b):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _make_os_error(5, 13)  # ACCESS_DENIED / EACCES
        return real_replace(a, b)

    monkeypatch.setattr(os, "replace", flaky_replace)
    replace_with_retry(src, dst, base_delay=0)  # base_delay=0 → instant retries

    assert calls["n"] == 2
    assert dst.read_text(encoding="utf-8") == "payload"


def test_replace_gives_up_after_retries(tmp_path: Path, monkeypatch):
    """A persistent transient-looking error eventually propagates."""
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.write_text("x", encoding="utf-8")

    def always_locked(*_args):
        raise _make_os_error(32, 13)  # SHARING_VIOLATION

    monkeypatch.setattr(os, "replace", always_locked)
    with pytest.raises(OSError):
        replace_with_retry(src, dst, retries=2, base_delay=0)


def test_replace_does_not_retry_fatal_errors(tmp_path: Path, monkeypatch):
    """Non-transient errors (e.g. ENOSPC) are raised immediately, no retry."""
    import errno

    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.write_text("x", encoding="utf-8")

    calls = {"n": 0}

    def out_of_space(*_args):
        calls["n"] += 1
        raise _make_os_error(None, errno.ENOSPC)

    monkeypatch.setattr(os, "replace", out_of_space)
    with pytest.raises(OSError):
        replace_with_retry(src, dst, retries=5, base_delay=0)
    assert calls["n"] == 1  # raised on first attempt, never retried


def test_atomic_write_cleans_temp_on_failure(tmp_path: Path, monkeypatch):
    """If the replace ultimately fails, the temp file is unlinked."""
    import errno

    target = tmp_path / "state.json"

    def out_of_space(*_args):
        raise _make_os_error(None, errno.ENOSPC)

    monkeypatch.setattr(os, "replace", out_of_space)
    with pytest.raises(OSError):
        atomic_write_text(target, "data")
    assert list(tmp_path.iterdir()) == []  # no .state.json.* temp left behind
