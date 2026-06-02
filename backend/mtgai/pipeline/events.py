"""Thread-safe event bus for SSE pipeline progress updates.

The pipeline engine runs in a background thread and publishes events here.
The SSE endpoint subscribes and streams events to the browser.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class EventBus:
    """Thread-safe pub/sub for pipeline SSE events.

    Publishers call ``publish()`` from any thread. Subscribers receive events
    via an ``asyncio.Queue`` obtained from ``subscribe()``.
    """

    # Cap on the per-run replay buffer. ~10k events covers a long card_gen
    # batch (per-tile updates x ~60 cards x multiple update kinds) with room
    # to spare. When exceeded the oldest events are dropped — the only ones
    # at risk of being lost are early stage_update / phase ticks the user
    # already has on screen anyway.
    _MAX_BUFFERED_EVENTS = 10_000

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self._lock = threading.Lock()
        # Per-run event log replayed to new subscribers. Without this,
        # events emitted between POST /start and the browser arriving on
        # /pipeline (a common race during the redirect) are lost — and
        # short stages like skeleton could complete entirely in that gap.
        self._buffer: list[dict[str, Any]] = []

    def reset_buffer(self) -> None:
        """Drop the replay buffer. Call when a fresh pipeline run starts."""
        with self._lock:
            self._buffer.clear()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Create a new subscriber queue. Returns an asyncio.Queue.

        New subscribers receive the full event log (subject to
        ``_MAX_BUFFERED_EVENTS``) before tailing live events, so a
        late-attaching browser still sees everything the engine emitted.
        """
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=10_240)
        with self._lock:
            # Replay first so historical events arrive in order, then
            # the queue tails live ones.
            for past in self._buffer:
                try:
                    q.put_nowait(past)
                except asyncio.QueueFull:
                    break
            self._subscribers.append(q)
        logger.debug("SSE subscriber added (total: %d)", len(self._subscribers))
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        """Remove a subscriber queue."""
        import contextlib

        with self._lock, contextlib.suppress(ValueError):
            self._subscribers.remove(q)
        logger.debug("SSE subscriber removed (total: %d)", len(self._subscribers))

    def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish an event to all subscribers. Safe to call from any thread.

        Also appends to the replay buffer so late-attaching subscribers
        get the full run history.
        """
        event = {"type": event_type, "data": data}
        with self._lock:
            self._buffer.append(event)
            if len(self._buffer) > self._MAX_BUFFERED_EVENTS:
                # Trim oldest in chunks so we don't pop one-by-one for every event.
                excess = len(self._buffer) - self._MAX_BUFFERED_EVENTS
                del self._buffer[:excess]
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    # Drop events if a client can't keep up — better than blocking
                    logger.warning("SSE queue full, dropping event: %s", event_type)

    # -- Convenience publishers for common event types --

    def stage_update(
        self,
        stage_id: str,
        status: str,
        progress: dict | None = None,
        instance_id: str | None = None,
        result: dict | None = None,
    ) -> None:
        """Publish a stage status change.

        ``instance_id`` identifies which stage *instance* changed (a stage can
        appear more than once); it defaults to ``stage_id`` for backbone
        instances, so it's always present in the payload for the shell to route
        on. ``result`` carries the instance's runner output (e.g. a review
        gate's flagged-card list) so its tab can render findings live without a
        separate fetch.
        """
        payload: dict[str, Any] = {
            "stage_id": stage_id,
            "instance_id": instance_id or stage_id,
            "status": status,
        }
        if progress is not None:
            payload["progress"] = progress
        if result is not None:
            payload["result"] = result
        self.publish("stage_update", payload)

    def item_progress(
        self,
        stage_id: str,
        item: str,
        completed: int,
        total: int,
        detail: str = "",
        instance_id: str | None = None,
    ) -> None:
        """Publish per-item progress within a stage."""
        self.publish(
            "item_progress",
            {
                "stage_id": stage_id,
                "instance_id": instance_id or stage_id,
                "item": item,
                "completed": completed,
                "total": total,
                "detail": detail,
            },
        )

    def cost_update(self, stage_cost: float, total_cost: float) -> None:
        """Publish a cost update."""
        self.publish("cost_update", {"stage_cost": stage_cost, "total_cost": total_cost})

    def pipeline_status(self, status: str, current_stage: str | None = None) -> None:
        """Publish overall pipeline status change."""
        self.publish(
            "pipeline_status",
            {"overall_status": status, "current_stage": current_stage},
        )

    def log_line(self, stage_id: str, level: str, message: str) -> None:
        """Publish a log line from a stage."""
        self.publish(
            "log_line",
            {"stage_id": stage_id, "level": level, "message": message},
        )

    def stage_sections_init(
        self, stage_id: str, sections: list[dict[str, Any]], instance_id: str | None = None
    ) -> None:
        """Declare the sections a stage will populate.

        Each section dict has at least ``section_id``, ``title``, and
        ``content_type``. Optional: ``status`` (default "pending") and a
        ``content`` seed.
        """
        self.publish(
            "stage_section_init",
            {"stage_id": stage_id, "instance_id": instance_id or stage_id, "sections": sections},
        )

    def stage_section_update(
        self, stage_id: str, section_id: str, instance_id: str | None = None, **fields: Any
    ) -> None:
        """Patch a previously-declared section.

        Recognised optional fields: ``status``, ``content`` (replaces),
        ``append_text`` (markdown/text append), ``append_item`` (grid
        append), ``detail`` (sub-line). Unknown fields are forwarded so
        the frontend can opt-in to new shapes.
        """
        payload: dict[str, Any] = {
            "stage_id": stage_id,
            "instance_id": instance_id or stage_id,
            "section_id": section_id,
        }
        payload.update(fields)
        self.publish("stage_section_update", payload)

    def stage_phase(
        self,
        stage_id: str,
        phase: str,
        activity: str,
        instance_id: str | None = None,
        **extra: Any,
    ) -> None:
        """Publish a stage-scoped phase tick (drives the activity banner).

        Mirrors the theme-extractor phase event shape so the same UI
        renderer can consume both. ``extra`` may include
        ``prompt_eval``, ``generation``, ``elapsed_s``, ``structural``.
        """
        payload: dict[str, Any] = {
            "stage_id": stage_id,
            "instance_id": instance_id or stage_id,
            "phase": phase,
            "activity": activity,
        }
        payload.update(extra)
        self.publish("phase", payload)


class StageEmitter:
    """Per-stage convenience wrapper around an :class:`EventBus`.

    Pipeline runners receive an instance of this so they can publish
    section + phase events without knowing about the bus. Constructed
    by the engine with ``stage_id`` already bound, so callers stay
    uncluttered.

    A no-op emitter (created via :meth:`null`) is also provided so
    CLI / test callers that invoke stage functions outside the
    pipeline don't need to pass anything.
    """

    def __init__(
        self,
        bus: EventBus | None,
        stage_id: str,
        started_at: float,
        instance_id: str | None = None,
    ) -> None:
        self._bus = bus
        self._stage_id = stage_id
        # Backbone instances pass nothing → instance_id == stage_id. Inserted
        # instances pass their own id so events route to the right tab.
        self._instance_id = instance_id or stage_id
        self._started_at = started_at

    @classmethod
    def null(cls) -> StageEmitter:
        """Emitter that swallows every call. Useful for CLI/test paths."""
        return cls(None, "", 0.0)

    def _elapsed(self) -> float:
        if self._started_at <= 0:
            return 0.0
        import time as _t

        return round(_t.monotonic() - self._started_at, 2)

    def init_sections(self, sections: list[dict[str, Any]]) -> None:
        if self._bus is None:
            return
        self._bus.stage_sections_init(self._stage_id, sections, instance_id=self._instance_id)

    def update(self, section_id: str, **fields: Any) -> None:
        if self._bus is None:
            return
        self._bus.stage_section_update(
            self._stage_id, section_id, instance_id=self._instance_id, **fields
        )

    def phase(self, phase: str, activity: str, **extra: Any) -> None:
        if self._bus is None:
            return
        extra.setdefault("elapsed_s", self._elapsed())
        self._bus.stage_phase(
            self._stage_id, phase, activity, instance_id=self._instance_id, **extra
        )

    def event(self, event_type: str, **data: Any) -> None:
        """Publish a raw stage-scoped SSE event of an arbitrary type.

        For bespoke per-stage streams that don't fit the section/phase shapes —
        the skeleton relabel uses it for ``skeleton_slot`` /
        ``skeleton_relabel_reset`` so the Skeleton tab can fill in cards live.
        ``stage_id`` + ``instance_id`` are folded into the payload so the
        consumer can scope it to the right tab."""
        if self._bus is None:
            return
        self._bus.publish(
            event_type,
            {"stage_id": self._stage_id, "instance_id": self._instance_id, **data},
        )


def format_sse(event: dict[str, Any]) -> str:
    """Format an event dict as an SSE message string."""
    event_type = event["type"]
    data = json.dumps(event["data"])
    return f"event: {event_type}\ndata: {data}\n\n"
