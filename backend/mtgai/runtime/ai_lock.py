"""App-wide mutex for AI-touching actions.

A single ``threading.Lock`` enforces that only one AI call runs at a time
across the whole process — theme extraction, the per-section refresh
endpoints, and (over time) every other pipeline stage. Conflicting callers
bounce out immediately and can read :func:`current_action` to tell the user
what's already running.

Cancel signalling rides alongside: any thread can call
:func:`request_cancel`, and long-running callers poll
:func:`is_cancelled` (or wait on :func:`cancel_event`) to abort.

The lock is non-reentrant — call sites acquire and release sequentially.
The previous theme-only ``RLock`` allowed re-entry but every actual call
site released between phases, so reentrancy was unused in practice.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AIAction:
    """Snapshot of what's currently running under the AI lock."""

    name: str
    started_at: datetime
    log_path: Path | None = None


_lock = threading.Lock()
_cancel_event = threading.Event()
_state_lock = threading.Lock()
_current: AIAction | None = None


def is_running() -> bool:
    """True iff an AI action holds the lock right now."""
    with _state_lock:
        return _current is not None


def current_action() -> AIAction | None:
    """Snapshot of the running action, or ``None`` if idle."""
    with _state_lock:
        return _current


def cancel_event() -> threading.Event:
    """The threading.Event consumed by long-running AI callers to abort.

    Cleared on every successful acquire; set by :func:`request_cancel`.
    """
    return _cancel_event


def is_cancelled() -> bool:
    return _cancel_event.is_set()


def request_cancel() -> bool:
    """Signal the active action to abort.

    Returns True if an action was running, False if idle.
    """
    with _state_lock:
        if _current is None:
            return False
        action_name = _current.name
    _cancel_event.set()
    logger.info("Cancel requested for active AI action: %s", action_name)
    return True


def try_acquire(name: str, log_path: Path | None = None) -> bool:
    """Non-blocking acquire. Publishes :class:`AIAction` on success.

    Callers MUST pair this with :func:`release` (a ``try / finally`` is
    enough — see :func:`hold` for the context-manager form).
    """
    if not _lock.acquire(blocking=False):
        return False
    _cancel_event.clear()
    with _state_lock:
        global _current
        _current = AIAction(
            name=name,
            started_at=datetime.now(tz=UTC),
            log_path=log_path,
        )
    logger.info("AI lock acquired: %s", name)
    return True


def release() -> None:
    """Release the lock and clear the published action.

    Safe to call even if the caller didn't acquire — ``threading.Lock``
    raises in that case, so we guard. (Defensive; production callers
    should never hit it.)
    """
    with _state_lock:
        global _current
        _current = None
    try:
        _lock.release()
    except RuntimeError:
        logger.warning("ai_lock.release() called without a held lock")


def update_log_path(log_path: Path) -> None:
    """Late-bind the log path on the current action.

    Theme extraction creates its per-run log directory *after* it acquires
    the lock — this lets it publish that path so ``/api/ai/status`` reports
    a live tail target.
    """
    with _state_lock:
        global _current
        if _current is None:
            return
        _current = replace(_current, log_path=log_path)


@contextmanager
def hold(name: str, log_path: Path | None = None) -> Iterator[bool]:
    """Acquire the AI lock for the duration of a ``with`` block.

    Yields True on success and False if the lock was already held — the
    caller is expected to bail out (e.g. yield an error event, return 409)
    when False is yielded.
    """
    acquired = try_acquire(name, log_path=log_path)
    try:
        yield acquired
    finally:
        if acquired:
            release()


def reset_for_tests() -> None:
    """Test-only: forcibly clear lock + cancel state.

    Real callers must NEVER use this. Kept here so the unit tests can
    isolate from each other and from leftover state if a test crashes
    mid-acquire.
    """
    global _current
    with _state_lock:
        _current = None
    _cancel_event.clear()
    if _lock.locked():
        with contextlib.suppress(RuntimeError):
            _lock.release()
