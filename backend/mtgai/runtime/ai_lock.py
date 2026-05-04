"""App-wide mutex for AI-touching actions.

A single ``threading.Lock`` (``_state_lock``) atomically guards both the
"is anything running" predicate and the published :class:`AIAction`
metadata. Conflicting callers bounce out immediately and can read
:func:`current_action` to tell the user what's already running.

Cancel signalling rides alongside: any thread can call
:func:`request_cancel`, and long-running callers poll :func:`is_cancelled`
to abort.

**WARNING — non-reentrant.** Call sites must acquire and release
sequentially; nesting from inside a held ``with hold(...)`` block on the
same thread will return ``False`` (i.e. "busy") and the inner work won't
run. The previous theme-only ``RLock`` allowed re-entry but every actual
caller released between phases, so reentrancy was unused. If a future
caller needs to nest, restructure to acquire once at the outer layer
rather than reintroducing reentrancy.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AIAction:
    """Snapshot of what's currently running under the AI lock."""

    name: str
    started_at: datetime
    log_path: Path | None = None


# ``_state_lock`` is *the* mutex — protecting ``_current`` IS the lock.
# A non-None ``_current`` means an AI action is in flight; checking and
# updating that field happens atomically inside the same critical section.
_state_lock = threading.Lock()
_current: AIAction | None = None
_cancel_event = threading.Event()


def is_running() -> bool:
    """True iff an AI action is currently in flight."""
    with _state_lock:
        return _current is not None


def current_action() -> AIAction | None:
    """Snapshot of the running action, or ``None`` if idle."""
    with _state_lock:
        return _current


def is_cancelled() -> bool:
    """True if the active action has been asked to abort."""
    return _cancel_event.is_set()


def request_cancel() -> bool:
    """Signal the active action to abort.

    Returns True if an action was running, False if idle. Safe to call
    from any thread.
    """
    with _state_lock:
        if _current is None:
            return False
        action_name = _current.name
        _cancel_event.set()
    logger.info("Cancel requested for active AI action: %s", action_name)
    return True


def try_acquire(name: str, log_path: Path | None = None) -> bool:
    """Atomically claim the lock and publish :class:`AIAction`.

    Returns True on success, False if another action is already running.
    Callers MUST pair True with :func:`release` (a ``try / finally`` is
    enough — see :func:`hold` for the context-manager form).
    """
    with _state_lock:
        global _current
        if _current is not None:
            return False
        _current = AIAction(
            name=name,
            started_at=datetime.now(tz=UTC),
            log_path=log_path,
        )
        _cancel_event.clear()
    logger.info("AI lock acquired: %s", name)
    return True


def release() -> None:
    """Release the lock and clear the published action.

    No-op if no action is currently held — defensive against stray
    double-releases (the production code paths only call this from inside
    ``hold(...)``'s ``finally`` after a successful acquire, so this branch
    should never fire in practice).
    """
    with _state_lock:
        global _current
        if _current is None:
            logger.warning("ai_lock.release() called when no action was held")
            return
        _current = None


def update_log_path(log_path: Path) -> None:
    """Late-bind the log path on the current action.

    Theme extraction creates its per-run log directory *after* it acquires
    the lock — this lets it publish that path so ``/api/ai/status`` reports
    a live tail target. No-op if no action is currently held.
    """
    with _state_lock:
        global _current
        if _current is None:
            return
        _current = replace(_current, log_path=log_path)


def busy_payload() -> dict[str, Any]:
    """JSON-shape snapshot of the lock state.

    Returned by ``GET /api/ai/status`` and used as the body of every 409
    Conflict response from a guarded endpoint, so the UI can render the
    same "AI is busy" toast wherever the rejection happened.
    """
    action = current_action()
    if action is None:
        return {
            "running": False,
            "running_action": None,
            "started_at": None,
            "log_path": None,
        }
    return {
        "running": True,
        "running_action": action.name,
        "started_at": action.started_at.isoformat(),
        "log_path": str(action.log_path) if action.log_path else None,
    }


@contextmanager
def hold(name: str, log_path: Path | None = None) -> Iterator[bool]:
    """Acquire the AI lock for the duration of a ``with`` block.

    Yields True on success and False if another action is already running.
    On True, the lock is released on context exit even if the body raises.
    The caller is expected to bail out (yield an error event, return 409)
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

    Real callers must NEVER use this — it bypasses every invariant the
    rest of the API exists to enforce. Tests use it to isolate from each
    other and from leftover state if a test crashes mid-acquire.
    """
    global _current
    with _state_lock:
        _current = None
    _cancel_event.clear()
