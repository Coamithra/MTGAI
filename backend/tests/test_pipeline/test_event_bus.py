"""Tests for the SSE EventBus, focused on cross-thread publish delivery.

The pipeline engine runs in a daemon thread and calls ``EventBus.publish``,
while the SSE consumer awaits ``queue.get()`` on the server's event loop.
``asyncio.Queue`` is not thread-safe, so publish must route the queue write
onto the loop via ``call_soon_threadsafe`` — otherwise a consumer blocked in
``await queue.get()`` is only un-stalled by its 30s timeout. These tests pin
that contract without relying on any real timeout.
"""

from __future__ import annotations

import asyncio
import threading

from mtgai.pipeline.events import EventBus


def test_cross_thread_publish_wakes_awaiting_consumer() -> None:
    """A publish from a non-loop thread must promptly wake ``queue.get()``.

    Regression guard: a raw cross-thread ``put_nowait`` can leave a consumer
    blocked in ``await queue.get()`` until an unrelated wakeup. Here the
    consumer awaits with a short timeout that is far below the SSE loop's real
    30s ceiling, so a hang means the wake never happened.
    """

    async def scenario() -> dict:
        bus = EventBus()
        queue = bus.subscribe()  # captures this running loop

        # Publish from a *separate* OS thread, mimicking the engine daemon.
        def worker() -> None:
            bus.publish("stage_update", {"stage_id": "skeleton", "status": "running"})

        # Start the consumer's get() first, then fire the cross-thread publish,
        # so we exercise the "getter already waiting" wake path.
        getter = asyncio.ensure_future(asyncio.wait_for(queue.get(), timeout=2.0))
        await asyncio.sleep(0)  # let the getter actually block on get()
        threading.Thread(target=worker, daemon=True).start()
        event = await getter
        return event

    event = asyncio.run(scenario())
    assert event["type"] == "stage_update"
    assert event["data"]["stage_id"] == "skeleton"


def test_cross_thread_publish_preserves_order() -> None:
    """Sequential cross-thread publishes arrive in submission order."""

    async def scenario() -> list[str]:
        bus = EventBus()
        queue = bus.subscribe()

        def worker() -> None:
            for i in range(5):
                bus.publish("phase", {"stage_id": "card_gen", "n": i})

        threading.Thread(target=worker, daemon=True).start()

        received: list[int] = []
        for _ in range(5):
            ev = await asyncio.wait_for(queue.get(), timeout=2.0)
            received.append(ev["data"]["n"])
        return received

    assert asyncio.run(scenario()) == [0, 1, 2, 3, 4]


def test_publish_before_any_subscriber_does_not_crash() -> None:
    """A publish with no captured loop (no subscriber yet) degrades silently.

    The event still lands in the replay buffer, so a subscriber attaching
    afterwards receives it.
    """
    bus = EventBus()
    # No subscribe() yet — no loop captured. Must not raise.
    bus.publish("log_line", {"stage_id": "mechanics", "message": "early"})

    async def scenario() -> dict:
        queue = bus.subscribe()  # replays the buffered event
        return await asyncio.wait_for(queue.get(), timeout=2.0)

    event = asyncio.run(scenario())
    assert event["type"] == "log_line"
    assert event["data"]["message"] == "early"


def test_publish_on_loop_thread_still_delivers() -> None:
    """Publishing from within the loop thread delivers via call_soon_threadsafe."""

    async def scenario() -> dict:
        bus = EventBus()
        queue = bus.subscribe()
        bus.publish("cost_update", {"stage_cost": 1.0, "total_cost": 2.0})
        return await asyncio.wait_for(queue.get(), timeout=2.0)

    event = asyncio.run(scenario())
    assert event["type"] == "cost_update"
    assert event["data"]["total_cost"] == 2.0
