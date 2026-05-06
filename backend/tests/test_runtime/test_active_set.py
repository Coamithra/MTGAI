"""Behavioural tests for ``await_lock_release`` and ``is_valid_set_code``.

The legacy ``active_set`` shim API (read/write/clear shims +
iter_known_set_codes + normalize_code + the [A-Z0-9]{2,5} regex) was
removed when the on-disk registry went away. The active-project pointer
itself is covered in ``test_active_project.py``; this file holds the
narrower lock-drain + validator coverage that doesn't fit there.
"""

from __future__ import annotations

import threading
import time

import pytest

from mtgai.runtime import active_project, ai_lock


@pytest.fixture(autouse=True)
def _reset_state():
    active_project.clear_active_project()
    ai_lock.reset_for_tests()
    yield
    active_project.clear_active_project()
    ai_lock.reset_for_tests()


# ---------------------------------------------------------------------------
# is_valid_set_code (relaxed: any non-empty trimmed string)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code", ["AS", "ASD", "DRKSN", "DARKSUN", "asd", "AB-CD", "12345"])
def test_valid_codes_accept_free_form_strings(code):
    assert active_project.is_valid_set_code(code)


@pytest.mark.parametrize("code", [None, "", "   ", "\t\n"])
def test_invalid_codes_reject_empty_and_whitespace(code):
    assert not active_project.is_valid_set_code(code)


def test_invalid_code_rejects_non_string():
    assert not active_project.is_valid_set_code(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# await_lock_release
# ---------------------------------------------------------------------------


def test_await_returns_true_when_idle():
    assert active_project.await_lock_release(deadline_s=0.5) is True


def test_await_returns_true_when_lock_releases_in_time():
    """Background thread holds the lock for 200 ms; deadline is 2 s."""

    def _hold_briefly() -> None:
        with ai_lock.hold("test"):
            time.sleep(0.2)

    t = threading.Thread(target=_hold_briefly, daemon=True)
    t.start()
    # Poll until the thread actually acquires — a fixed sleep can fall
    # through the window under load and produce a flaky failure here.
    deadline = time.monotonic() + 1.0
    while not ai_lock.is_running():
        if time.monotonic() >= deadline:
            raise AssertionError("background thread never acquired the lock")
        time.sleep(0.01)
    assert active_project.await_lock_release(deadline_s=2.0) is True
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
    assert active_project.await_lock_release(deadline_s=0.3) is False
    assert ai_lock.is_running()  # still held
    release_event.set()
    t.join(timeout=2.0)
