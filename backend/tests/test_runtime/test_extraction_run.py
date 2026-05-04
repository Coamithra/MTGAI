"""Unit tests for the broadcastable extraction run buffer."""

from __future__ import annotations

import threading
import time

import pytest

from mtgai.runtime import extraction_run


@pytest.fixture(autouse=True)
def _reset_run():
    extraction_run.reset()
    yield
    extraction_run.reset()


def test_idle_state():
    assert extraction_run.current() is None


def test_subscribe_with_no_run_returns_done_immediately():
    run, q = extraction_run.subscribe()
    assert run is None
    # Sentinel is queued so the SSE handler exits cleanly.
    item = q.get_nowait()
    assert extraction_run.is_done_sentinel(item)


def test_start_run_initialises_state():
    run = extraction_run.start_run("upload-1")
    assert run.upload_id == "upload-1"
    assert run.status == "running"
    assert run.events == []
    assert run.finished_at is None
    assert extraction_run.current() is run


def test_append_event_records_and_broadcasts():
    extraction_run.start_run("upload-1")
    _, q = extraction_run.subscribe()

    extraction_run.append_event({"type": "theme_chunk", "text": "foo"})
    extraction_run.append_event({"type": "complete", "cost_usd": 0.0})

    first = q.get(timeout=0.5)
    second = q.get(timeout=0.5)
    assert first == {"type": "theme_chunk", "text": "foo"}
    assert second == {"type": "complete", "cost_usd": 0.0}

    # Persisted on the run for late subscribers to replay.
    run = extraction_run.current()
    assert run is not None
    assert run.events == [first, second]


def test_late_subscriber_replays_past_events():
    """A subscriber that arrives after some events have been emitted
    receives all of them in order before any new ones."""
    extraction_run.start_run("upload-1")
    extraction_run.append_event({"type": "theme_chunk", "text": "first"})
    extraction_run.append_event({"type": "theme_chunk", "text": "second"})

    _, q = extraction_run.subscribe()

    # Replay arrives synchronously in subscribe(), no waiting needed.
    a = q.get_nowait()
    b = q.get_nowait()
    assert a["text"] == "first"
    assert b["text"] == "second"

    # And subsequent events keep flowing.
    extraction_run.append_event({"type": "theme_chunk", "text": "third"})
    c = q.get(timeout=0.5)
    assert c["text"] == "third"


def test_two_subscribers_both_receive_future_events():
    """Multi-subscriber: every active subscriber gets the same events.

    This is the headline reason the buffer exists — disconnect should
    unsubscribe one client while leaving others (and any future
    reattaches) live."""
    extraction_run.start_run("upload-1")
    _, q1 = extraction_run.subscribe()
    _, q2 = extraction_run.subscribe()

    extraction_run.append_event({"type": "theme_chunk", "text": "x"})

    e1 = q1.get(timeout=0.5)
    e2 = q2.get(timeout=0.5)
    assert e1 == e2
    assert e1["text"] == "x"


def test_unsubscribe_doesnt_drop_other_subscribers():
    extraction_run.start_run("upload-1")
    _, q1 = extraction_run.subscribe()
    _, q2 = extraction_run.subscribe()

    extraction_run.unsubscribe(q1)

    extraction_run.append_event({"type": "theme_chunk", "text": "after-unsub"})

    # q1 received nothing new (it was unsubscribed before append); q2 did.
    assert q1.empty()
    e = q2.get(timeout=0.5)
    assert e["text"] == "after-unsub"


def test_unsubscribe_is_idempotent():
    extraction_run.start_run("upload-1")
    _, q = extraction_run.subscribe()
    extraction_run.unsubscribe(q)
    # Calling twice must not raise.
    extraction_run.unsubscribe(q)


def test_mark_done_emits_sentinel_to_subscribers():
    extraction_run.start_run("upload-1")
    _, q1 = extraction_run.subscribe()
    _, q2 = extraction_run.subscribe()

    extraction_run.mark_done("completed")

    a = q1.get(timeout=0.5)
    b = q2.get(timeout=0.5)
    assert extraction_run.is_done_sentinel(a)
    assert extraction_run.is_done_sentinel(b)

    run = extraction_run.current()
    assert run is not None
    assert run.status == "completed"
    assert run.finished_at is not None


def test_subscribe_after_done_replays_then_terminates():
    """A user who tabs in *after* extraction finished still gets the
    full event log (so the UI can render the final state) followed by
    the sentinel so the SSE handler closes cleanly."""
    extraction_run.start_run("upload-1")
    extraction_run.append_event({"type": "theme_chunk", "text": "hello"})
    extraction_run.append_event({"type": "done", "total_cost_usd": 0.01})
    extraction_run.mark_done("completed")

    _, q = extraction_run.subscribe()
    first = q.get_nowait()
    second = q.get_nowait()
    sentinel = q.get_nowait()

    assert first["text"] == "hello"
    assert second["type"] == "done"
    assert extraction_run.is_done_sentinel(sentinel)


def test_start_run_replaces_previous_run():
    """A new extraction wipes the old buffer. Late subscribers from
    the previous run will not see the new run's events because they
    were unsubscribed at mark_done — the contract."""
    old = extraction_run.start_run("upload-A")
    extraction_run.append_event({"type": "theme_chunk", "text": "old"})
    extraction_run.mark_done("completed")

    new = extraction_run.start_run("upload-B")
    assert new is not old
    assert new.upload_id == "upload-B"
    assert new.events == []
    assert new.status == "running"


def test_append_with_no_run_is_noop():
    """Defensive: a stray append after reset must not crash."""
    extraction_run.reset()
    # Doesn't raise.
    extraction_run.append_event({"type": "theme_chunk", "text": "stray"})


def test_concurrent_append_and_subscribe():
    """Worker thread appending while a new subscriber arrives — the
    new subscriber should get a complete prefix replay plus all
    subsequent events, with no duplicates and no losses."""
    extraction_run.start_run("upload-1")
    stop = threading.Event()

    def appender():
        i = 0
        while not stop.is_set() and i < 20:
            extraction_run.append_event({"type": "theme_chunk", "text": str(i)})
            i += 1
            time.sleep(0.005)

    t = threading.Thread(target=appender, daemon=True)
    t.start()
    time.sleep(0.02)  # let some events accumulate

    _, q = extraction_run.subscribe()
    # Wait for the appender to finish.
    t.join(timeout=1.0)
    stop.set()

    received: list[int] = []
    while True:
        try:
            evt = q.get(timeout=0.1)
        except Exception:
            break
        received.append(int(evt["text"]))

    # Strictly increasing, no duplicates, contains 0 (replayed).
    assert received[0] == 0
    assert received == sorted(set(received))
