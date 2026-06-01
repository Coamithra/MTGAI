"""Unit tests for the app-wide AI mutex (`mtgai.runtime.ai_lock`)."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from mtgai.runtime import ai_lock


@pytest.fixture(autouse=True)
def _reset_ai_lock():
    """Make every test start from a clean idle state.

    Cancel-hook registrations persist across ``reset_for_tests`` by design
    (they're process-wide wiring), so snapshot + restore them here to keep a
    test that registers a hook from leaking it into the next test (and to keep
    the real ``llm_client`` interrupt hook, registered at import, intact).
    """
    saved_hooks = list(ai_lock._cancel_hooks)
    ai_lock.reset_for_tests()
    yield
    ai_lock.reset_for_tests()
    ai_lock._cancel_hooks[:] = saved_hooks


def test_idle_state():
    assert ai_lock.is_running() is False
    assert ai_lock.current_action() is None
    assert ai_lock.is_cancelled() is False


def test_try_acquire_publishes_action():
    run_id = ai_lock.try_acquire("Theme extraction")
    assert isinstance(run_id, int) and run_id >= 1
    try:
        action = ai_lock.current_action()
        assert action is not None
        assert action.name == "Theme extraction"
        assert action.log_path is None
        assert ai_lock.current_run_id() == run_id
    finally:
        ai_lock.release()


def test_try_acquire_returns_none_when_held():
    first_id = ai_lock.try_acquire("first")
    assert isinstance(first_id, int) and first_id >= 1
    try:
        assert ai_lock.try_acquire("second") is None
        # The published action stays as the original holder.
        action = ai_lock.current_action()
        assert action is not None
        assert action.name == "first"
        assert ai_lock.current_run_id() == first_id
    finally:
        ai_lock.release()


def test_release_clears_state():
    ai_lock.try_acquire("a")
    ai_lock.release()
    assert ai_lock.is_running() is False
    assert ai_lock.current_action() is None


def test_hold_context_yields_run_id_on_success():
    with ai_lock.hold("ctx") as run_id:
        assert isinstance(run_id, int) and run_id >= 1
        assert ai_lock.is_running() is True
        assert ai_lock.current_run_id() == run_id
    assert ai_lock.is_running() is False
    # Released runs report idle.
    assert ai_lock.current_run_id() == 0


def test_hold_context_yields_none_when_busy():
    assert ai_lock.try_acquire("first") is not None
    try:
        with ai_lock.hold("second") as run_id:
            assert run_id is None
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


def test_run_id_is_monotonic_across_acquires():
    """Each acquire gets a strictly larger run_id; idle reports 0."""
    assert ai_lock.current_run_id() == 0

    first = ai_lock.try_acquire("a")
    assert isinstance(first, int) and first >= 1
    ai_lock.release()
    assert ai_lock.current_run_id() == 0

    second = ai_lock.try_acquire("b")
    assert isinstance(second, int)
    ai_lock.release()

    third = ai_lock.try_acquire("c")
    assert isinstance(third, int)
    ai_lock.release()

    assert first < second < third


def test_request_cancel_with_matching_run_id_cancels():
    """Passing the held run's id cancels it (same as the None path)."""
    run_id = ai_lock.try_acquire("a")
    assert run_id is not None
    try:
        assert ai_lock.request_cancel(run_id=run_id) is True
        assert ai_lock.is_cancelled() is True
    finally:
        ai_lock.release()


def test_stale_cancel_does_not_kill_a_newer_run():
    """A cancel scoped to an old run_id is a no-op once a new run holds the lock.

    This is the race the run_id guard closes: a cancel request captured
    run A's id, but by the time it fires run A has released and run B has
    acquired the lock reusing the same lock state. request_cancel(A) must
    NOT abort B.
    """
    # Run A acquires, then releases (as if it finished naturally).
    run_a = ai_lock.try_acquire("run A")
    assert run_a is not None
    ai_lock.release()

    # Run B acquires next — different, larger run_id.
    run_b = ai_lock.try_acquire("run B")
    assert run_b is not None
    assert run_b != run_a
    try:
        # The stale cancel aimed at A must not touch B.
        assert ai_lock.request_cancel(run_id=run_a) is False
        assert ai_lock.is_cancelled() is False
        # B's own id still cancels B.
        assert ai_lock.request_cancel(run_id=run_b) is True
        assert ai_lock.is_cancelled() is True
    finally:
        ai_lock.release()


def test_request_cancel_with_run_id_when_idle_is_false():
    """A run-scoped cancel against an idle lock is a no-op."""
    assert ai_lock.request_cancel(run_id=1) is False
    assert ai_lock.is_cancelled() is False


def test_request_cancel_none_still_cancels_current_run():
    """The legacy arg-less call cancels whatever is running (UI cancel path)."""
    ai_lock.try_acquire("a")
    try:
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
    results: list[int | None] = []
    lock = threading.Lock()

    def worker(name: str):
        barrier.wait()
        got = ai_lock.try_acquire(name)
        with lock:
            results.append(got)
        if got is not None:
            # Hold briefly so the other thread sees it as locked.
            time.sleep(0.05)
            ai_lock.release()

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one winner (a run_id) and one loser (None).
    winners = [r for r in results if r is not None]
    losers = [r for r in results if r is None]
    assert len(winners) == 1
    assert len(losers) == 1
    assert winners[0] >= 1


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


def test_hold_releases_on_exception():
    """The lock must be released when the body of `hold(...)` raises.

    Without the `finally` in the context manager, an unrelated worker
    bug would brick the whole AI subsystem until the process restarts.
    """
    with pytest.raises(RuntimeError), ai_lock.hold("crashy") as run_id:
        assert isinstance(run_id, int) and run_id >= 1
        raise RuntimeError("boom")

    # Lock must be free after the exception unwinds.
    assert ai_lock.is_running() is False
    assert ai_lock.try_acquire("next") is not None
    ai_lock.release()


def test_release_when_idle_is_safe():
    """Stray `release()` calls without a held lock must not corrupt state."""
    # Idle release: warns but doesn't raise.
    ai_lock.release()
    assert ai_lock.is_running() is False

    # And a new acquire still works.
    assert ai_lock.try_acquire("after-bad-release") is not None
    try:
        action = ai_lock.current_action()
        assert action is not None
        assert action.name == "after-bad-release"
    finally:
        ai_lock.release()


def test_cross_thread_cancel_visible_via_is_cancelled():
    """A cancel issued from one thread is visible to the worker thread.

    The worker polls `is_cancelled()` in its inner loop; the user's
    cancel arrives via an HTTP handler running on a different thread.
    """
    saw_cancel = threading.Event()
    started = threading.Event()
    stop_at = time.monotonic() + 1.0  # safety timeout

    def worker():
        ai_lock.try_acquire("worker")
        try:
            started.set()
            while time.monotonic() < stop_at:
                if ai_lock.is_cancelled():
                    saw_cancel.set()
                    return
                time.sleep(0.005)
        finally:
            ai_lock.release()

    t = threading.Thread(target=worker)
    t.start()
    assert started.wait(timeout=1.0)
    # Caller thread requests cancel.
    assert ai_lock.request_cancel() is True
    t.join(timeout=1.5)
    assert saw_cancel.is_set()


def test_busy_payload_idle_shape():
    """`busy_payload()` while idle returns the documented all-null shape."""
    payload = ai_lock.busy_payload()
    assert payload == {
        "running": False,
        "running_action": None,
        "started_at": None,
        "log_path": None,
    }


def test_busy_payload_includes_action_metadata():
    """`busy_payload()` while busy reflects the published action."""
    log_path = Path("/tmp/xyz")
    ai_lock.try_acquire("Theme extraction", log_path=log_path)
    try:
        payload = ai_lock.busy_payload()
        assert payload["running"] is True
        assert payload["running_action"] == "Theme extraction"
        # str(Path) is platform-specific; just confirm the path round-trips.
        assert payload["log_path"] == str(log_path)
        # ISO 8601 timestamp string.
        assert payload["started_at"] is not None
        assert "T" in payload["started_at"]
    finally:
        ai_lock.release()


# ── Cancel hooks ─────────────────────────────────────────────────────


def test_cancel_hook_fires_on_cancel():
    """A registered hook runs when a cancel is actually signalled."""
    calls: list[int] = []
    ai_lock.register_cancel_hook(lambda: calls.append(1))
    ai_lock.try_acquire("a")
    try:
        assert ai_lock.request_cancel() is True
        assert calls == [1]
    finally:
        ai_lock.release()


def test_cancel_hook_not_fired_when_idle():
    """No running action → no cancel signalled → hook must not fire."""
    calls: list[int] = []
    ai_lock.register_cancel_hook(lambda: calls.append(1))
    assert ai_lock.request_cancel() is False
    assert calls == []


def test_cancel_hook_not_fired_on_stale_run_id():
    """A stale run-scoped cancel is a no-op, so its hooks must not fire."""
    calls: list[int] = []
    ai_lock.register_cancel_hook(lambda: calls.append(1))

    run_a = ai_lock.try_acquire("run A")
    assert run_a is not None
    ai_lock.release()
    run_b = ai_lock.try_acquire("run B")
    assert run_b is not None
    try:
        # Cancel aimed at the already-finished run A: no-op, no hook.
        assert ai_lock.request_cancel(run_id=run_a) is False
        assert calls == []
        # B's own id fires it.
        assert ai_lock.request_cancel(run_id=run_b) is True
        assert calls == [1]
    finally:
        ai_lock.release()


def test_register_cancel_hook_is_idempotent():
    """Registering the same callable twice fires it only once per cancel."""
    calls: list[int] = []

    def hook():
        calls.append(1)

    ai_lock.register_cancel_hook(hook)
    ai_lock.register_cancel_hook(hook)
    ai_lock.try_acquire("a")
    try:
        ai_lock.request_cancel()
        assert calls == [1]
    finally:
        ai_lock.release()


def test_cancel_hook_exception_is_swallowed():
    """A raising hook must not break cancellation or sibling hooks."""
    calls: list[str] = []

    def bad():
        raise RuntimeError("boom")

    ai_lock.register_cancel_hook(bad)
    ai_lock.register_cancel_hook(lambda: calls.append("good"))
    ai_lock.try_acquire("a")
    try:
        # request_cancel still reports success and the event is set despite the
        # bad hook, and the sibling hook still ran.
        assert ai_lock.request_cancel() is True
        assert ai_lock.is_cancelled() is True
        assert calls == ["good"]
    finally:
        ai_lock.release()
