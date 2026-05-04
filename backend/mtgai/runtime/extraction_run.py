"""Module-level singleton for the active theme extraction run.

The previous design coupled the SSE stream to a single client: the
worker pushed into one queue, and ``request.is_disconnected()``
triggered ``ai_lock.request_cancel()``. So tabbing away mid-extraction
killed the run — the UI had no way to come back to it.

This module replaces that with a broadcastable buffer:

- One ``ExtractionRun`` lives at module scope.
- The worker pushes events through :func:`append_event`, which appends
  to the persistent ``events`` log AND fans out to every subscribed
  queue under a single lock.
- Late subscribers (``subscribe()``) get all past events replayed into
  their queue immediately, then keep receiving new ones.
- Disconnects unsubscribe but do **not** cancel — cancel is opt-in,
  via ``ai_lock.request_cancel()`` from the cancel button.
- After ``mark_done()``, late subscribers still get the full event
  log (including the terminating event) so they can render the final
  state without re-running.

A new run replaces the old one in :func:`start_run`. We keep one slot
because ``ai_lock`` already enforces "one AI action at a time" — a
new run can only start after the previous one's lock release. Late
subscribers that arrive after a new run started lose access to the
old log; that's acceptable because by then the old run's user-facing
result lives on disk in ``theme.json`` (if the user clicked Save) or
in their own browser's localStorage drafts.
"""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# Sentinel pushed onto subscriber queues when the run terminates so the
# SSE handler can break out of its read loop without polling a flag.
_RUN_DONE = object()


@dataclass
class ExtractionRun:
    """The active or most-recent theme extraction run."""

    upload_id: str
    started_at: datetime
    events: list[dict] = field(default_factory=list)
    finished_at: datetime | None = None
    status: str = "running"
    subscribers: set[queue.Queue] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)


_run: ExtractionRun | None = None


def start_run(upload_id: str) -> ExtractionRun:
    """Replace any previous run with a fresh one. Returns the new run."""
    global _run
    _run = ExtractionRun(
        upload_id=upload_id,
        started_at=datetime.now(tz=UTC),
    )
    logger.info("Extraction run started: upload_id=%s", upload_id)
    return _run


def append_event(event: dict) -> None:
    """Append to the run log and fan out to every subscriber.

    Called from the worker thread. No-op if no run is active (defensive
    — append should only be called between :func:`start_run` and
    :func:`mark_done`).
    """
    run = _run
    if run is None:
        logger.warning("append_event called with no active run; dropping %r", event.get("type"))
        return
    with run.lock:
        run.events.append(event)
        for q in list(run.subscribers):
            q.put(event)


def subscribe() -> tuple[ExtractionRun | None, queue.Queue]:
    """Register a new subscriber.

    Returns ``(run, queue)`` where the queue is pre-loaded with every
    event so far (replay). If the run has already terminated, the
    sentinel is appended so the consumer's read loop exits naturally
    after replay. If no run exists, returns ``(None, empty queue)``.
    """
    run = _run
    q: queue.Queue = queue.Queue()
    if run is None:
        q.put(_RUN_DONE)
        return None, q
    with run.lock:
        for event in run.events:
            q.put(event)
        if run.status != "running":
            q.put(_RUN_DONE)
        else:
            run.subscribers.add(q)
    return run, q


def unsubscribe(q: queue.Queue) -> None:
    """Remove a subscriber. Idempotent."""
    run = _run
    if run is None:
        return
    with run.lock:
        run.subscribers.discard(q)


def mark_done(status: str) -> None:
    """Close out the run. Drops all subscribers and emits the sentinel."""
    run = _run
    if run is None:
        return
    with run.lock:
        run.status = status
        run.finished_at = datetime.now(tz=UTC)
        for q in list(run.subscribers):
            q.put(_RUN_DONE)
        run.subscribers.clear()
    logger.info("Extraction run done: status=%s upload_id=%s", status, run.upload_id)


def current() -> ExtractionRun | None:
    """Snapshot of the active or most-recent run, or None if never started."""
    return _run


def reset() -> None:
    """Test-only: forcibly clear the singleton state."""
    global _run
    _run = None


def is_done_sentinel(value: object) -> bool:
    """True if ``value`` is the sentinel pushed onto subscriber queues at end-of-run."""
    return value is _RUN_DONE
