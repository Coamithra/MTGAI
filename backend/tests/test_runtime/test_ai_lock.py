"""Unit tests for the app-wide AI mutex (`mtgai.runtime.ai_lock`)."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from mtgai.runtime import ai_lock


@pytest.fixture(autouse=True)
def _reset_ai_lock():
    """Make every test start from a clean idle state."""
    ai_lock.reset_for_tests()
    yield
    ai_lock.reset_for_tests()


def test_idle_state():
    assert ai_lock.is_running() is False
    assert ai_lock.current_action() is None
    assert ai_lock.is_cancelled() is False


def test_try_acquire_publishes_action():
    assert ai_lock.try_acquire("Theme extraction") is True
    try:
        action = ai_lock.current_action()
        assert action is not None
        assert action.name == "Theme extraction"
        assert action.log_path is None
    finally:
        ai_lock.release()


def test_try_acquire_returns_false_when_held():
    assert ai_lock.try_acquire("first") is True
    try:
        assert ai_lock.try_acquire("second") is False
        # The published action stays as the original holder.
        action = ai_lock.current_action()
        assert action is not None
        assert action.name == "first"
    finally:
        ai_lock.release()


def test_release_clears_state():
    ai_lock.try_acquire("a")
    ai_lock.release()
    assert ai_lock.is_running() is False
    assert ai_lock.current_action() is None


def test_hold_context_yields_true_on_success():
    with ai_lock.hold("ctx") as ok:
        assert ok is True
        assert ai_lock.is_running() is True
    assert ai_lock.is_running() is False


def test_hold_context_yields_false_when_busy():
    assert ai_lock.try_acquire("first") is True
    try:
        with ai_lock.hold("second") as ok:
            assert ok is False
            # The first holder is still the published action.
            action = ai_lock.current_action()
            assert action is not None
            assert action.name == "first"
    finally:
        ai_lock.release()


def test_request_cancel_returns_false_when_idle():
    assert ai_lock.request_cancel() is False
    assert ai_lock.is_cancelled() is False


def test_request_cancel_sets_event_when_held():
    ai_lock.try_acquire("a")
    try:
        assert ai_lock.is_cancelled() is False
        assert ai_lock.request_cancel() is True
        assert ai_lock.is_cancelled() is True
    finally:
        ai_lock.release()


def test_cancel_event_clears_on_next_acquire():
    ai_lock.try_acquire("a")
    ai_lock.request_cancel()
    assert ai_lock.is_cancelled() is True
    ai_lock.release()
    # Next acquisition starts fresh: cancel is cleared.
    ai_lock.try_acquire("b")
    try:
        assert ai_lock.is_cancelled() is False
    finally:
        ai_lock.release()


def test_update_log_path_threads_through():
    ai_lock.try_acquire("a")
    try:
        # Initially no log path.
        assert ai_lock.current_action().log_path is None  # type: ignore[union-attr]
        ai_lock.update_log_path(Path("/tmp/extract"))
        action = ai_lock.current_action()
        assert action is not None
        assert action.log_path == Path("/tmp/extract")
        # Other fields preserved.
        assert action.name == "a"
    finally:
        ai_lock.release()


def test_update_log_path_when_idle_is_noop():
    # No action published — should silently no-op (not raise).
    ai_lock.update_log_path(Path("/tmp/foo"))
    assert ai_lock.current_action() is None


def test_only_one_thread_wins():
    """Two threads racing for the lock — exactly one acquires."""
    barrier = threading.Barrier(2)
    results: list[bool] = []
    lock = threading.Lock()

    def worker(name: str):
        barrier.wait()
        got = ai_lock.try_acquire(name)
        with lock:
            results.append(got)
        if got:
            # Hold briefly so the other thread sees it as locked.
            time.sleep(0.05)
            ai_lock.release()

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert sorted(results) == [False, True]


def test_started_at_is_monotonic_within_run():
    """`started_at` should be set on acquire and stay stable."""
    ai_lock.try_acquire("a")
    try:
        first = ai_lock.current_action().started_at  # type: ignore[union-attr]
        time.sleep(0.01)
        same = ai_lock.current_action().started_at  # type: ignore[union-attr]
        assert first == same
    finally:
        ai_lock.release()
