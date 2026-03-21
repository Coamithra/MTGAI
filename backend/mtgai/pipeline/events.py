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

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self._lock = threading.Lock()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Create a new subscriber queue. Returns an asyncio.Queue."""
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        with self._lock:
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
        """Publish an event to all subscribers. Safe to call from any thread."""
        event = {"type": event_type, "data": data}
        with self._lock:
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    # Drop events if a client can't keep up — better than blocking
                    logger.warning("SSE queue full, dropping event: %s", event_type)

    # -- Convenience publishers for common event types --

    def stage_update(self, stage_id: str, status: str, progress: dict | None = None) -> None:
        """Publish a stage status change."""
        payload: dict[str, Any] = {"stage_id": stage_id, "status": status}
        if progress is not None:
            payload["progress"] = progress
        self.publish("stage_update", payload)

    def item_progress(
        self,
        stage_id: str,
        item: str,
        completed: int,
        total: int,
        detail: str = "",
    ) -> None:
        """Publish per-item progress within a stage."""
        self.publish(
            "item_progress",
            {
                "stage_id": stage_id,
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


def format_sse(event: dict[str, Any]) -> str:
    """Format an event dict as an SSE message string."""
    event_type = event["type"]
    data = json.dumps(event["data"])
    return f"event: {event_type}\ndata: {data}\n\n"
