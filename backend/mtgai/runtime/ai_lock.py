"""App-wide mutex for AI-touching actions.

A single ``threading.Lock`` (``_state_lock``) atomically guards both the
"is anything running" predicate and the published :class:`AIAction`
metadata. Conflicting callers bounce out immediately and can read
:func:`current_action` to tell the user what's already running.

Cancel signalling rides alongside: any thread can call
:func:`request_cancel`, and long-running callers poll :func:`is_cancelled`
to abort.

**Run identity.** Each successful acquire stamps the run with a
monotonically increasing ``run_id`` (>= 1), returned by
:func:`try_acquire` / :func:`hold` and exposed via :func:`current_run_id`.
:func:`request_cancel` accepts an optional ``run_id`` so a *stale* cancel
(a slow cancel request that fires after the run it meant to kill already
released and a *different* run reacquired the lock) is dropped instead of
aborting the wrong run. See :func:`request_cancel` for the exact race.

**WARNING — strictly non-reentrant; this is NOT an ``RLock``.** A thread
that already holds the lock and calls :func:`try_acquire` / :func:`hold`
again does NOT re-enter: the nested call sees the lock as held and returns
busy (``None`` from :func:`try_acquire`, a falsy yield from :func:`hold`),
so the nested work *silently does not run*. The previous theme-only
``RLock`` allowed re-entry, but every real caller released between phases,
so reentrancy was unused. A future caller that needs nested AI work must
acquire ONCE at the outermost layer and pass the held state inward — do
not reintroduce an ``RLock`` (it would let two logically distinct AI
actions run concurrently under one acquire, defeating the mutex). See
:func:`hold` for the same warning at the call-site level.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator
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

# Monotonic per-acquire counter. Bumped inside the critical section on every
# successful acquire so each run gets a unique, ever-increasing id (>= 1).
# ``_current_run_id`` mirrors the active run's id while held; 0 means idle.
_run_counter = 0
_current_run_id = 0

# Cancel hooks: callables fired (best-effort) whenever :func:`request_cancel`
# actually signals a running action. They let a higher layer react to a cancel
# beyond the polled ``_cancel_event`` — specifically, ``llm_client`` registers a
# hook that hard-kills the in-flight local llama-server, since a synchronous
# in-flight LLM call can't be interrupted by polling alone. Kept here (not in
# llm_client) so this low-level primitive stays import-free of the generation
# layer; callers register inward. Hooks run on the cancelling thread, OUTSIDE
# ``_state_lock``, so a slow hook (a process kill) can't stall lock readers.
# Return value is ignored, so the hook may return anything (e.g. a bool).
_cancel_hooks: list[Callable[[], object]] = []
_cancel_hooks_lock = threading.Lock()


def register_cancel_hook(hook: Callable[[], object]) -> None:
    """Register a callable to run whenever a cancel is signalled.

    Idempotent per callable (registering the same hook twice is a no-op).
    Hooks fire on the thread calling :func:`request_cancel`, after the cancel
    event is set and the state lock is released, and any exception a hook
    raises is logged and swallowed so one bad hook can't break cancellation.
    Registrations persist across :func:`reset_for_tests` (they're process-wide
    wiring, not per-run state).
    """
    with _cancel_hooks_lock:
        if hook not in _cancel_hooks:
            _cancel_hooks.append(hook)


def _fire_cancel_hooks() -> None:
    """Invoke every registered cancel hook, best-effort."""
    with _cancel_hooks_lock:
        hooks = list(_cancel_hooks)
    for hook in hooks:
        try:
            hook()
        except Exception:
            logger.exception("Cancel hook %r raised; continuing", getattr(hook, "__name__", hook))


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


def current_run_id() -> int:
    """The id of the run currently holding the lock, or 0 if idle.

    Run ids are monotonic and start at 1 (see :func:`try_acquire`), so a
    return of 0 unambiguously means "no run is held". Callers that want to
    cancel only their *own* run pass this value to :func:`request_cancel`.
    """
    with _state_lock:
        return _current_run_id


def request_cancel(run_id: int | None = None) -> bool:
    """Signal the active action to abort.

    Returns True if a matching action was running and was signalled, False
    if there was nothing to cancel (idle, or ``run_id`` named a run that is
    no longer the one holding the lock). Safe to call from any thread.

    ``run_id`` closes a stale-cancel race. Without it, "cancel whatever is
    running now" can mis-fire: run A acquires (id 1), the user's cancel HTTP
    handler is dispatched, A finishes and releases, run B acquires (id 2),
    *then* the handler finally calls ``request_cancel()`` — which would set
    the cancel flag on B even though the user meant to stop A. A caller that
    captured A's id at acquire time and passes ``request_cancel(run_id=1)``
    is instead a no-op once B holds the lock, so B runs undisturbed.

    Passing ``None`` keeps the legacy "cancel the current run, whatever it
    is" behavior — appropriate for UI-driven cancels where the user is
    explicitly aborting whatever they can see is running right now.
    """
    with _state_lock:
        if _current is None:
            return False
        if run_id is not None and run_id != _current_run_id:
            logger.info(
                "Stale cancel ignored: requested run_id=%s but active run_id=%s (%s)",
                run_id,
                _current_run_id,
                _current.name,
            )
            return False
        action_name = _current.name
        _cancel_event.set()
    logger.info("Cancel requested for active AI action: %s", action_name)
    # Fire hooks outside _state_lock: a hook may hard-kill a subprocess (the
    # local-inference interrupt), which we must not do while holding the mutex
    # that every status/acquire read contends on.
    _fire_cancel_hooks()
    return True


def try_acquire(name: str, log_path: Path | None = None) -> int | None:
    """Atomically claim the lock and publish :class:`AIAction`.

    Returns the new run's monotonic ``run_id`` (an ``int`` >= 1, always
    truthy) on success, or ``None`` if another action is already running.
    Callers MUST pair a successful acquire with :func:`release` (a
    ``try / finally`` is enough — see :func:`hold` for the context-manager
    form). Hold onto the returned id if you intend to cancel only your own
    run later via :func:`request_cancel`.
    """
    with _state_lock:
        global _current, _run_counter, _current_run_id
        if _current is not None:
            return None
        _run_counter += 1
        _current_run_id = _run_counter
        _current = AIAction(
            name=name,
            started_at=datetime.now(tz=UTC),
            log_path=log_path,
        )
        _cancel_event.clear()
        run_id = _current_run_id
    logger.info("AI lock acquired: %s (run_id=%s)", name, run_id)
    return run_id


def release() -> None:
    """Release the lock and clear the published action.

    No-op if no action is currently held — defensive against stray
    double-releases (the production code paths only call this from inside
    ``hold(...)``'s ``finally`` after a successful acquire, so this branch
    should never fire in practice).
    """
    with _state_lock:
        global _current, _current_run_id
        if _current is None:
            logger.warning("ai_lock.release() called when no action was held")
            return
        _current = None
        _current_run_id = 0


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
def hold(name: str, log_path: Path | None = None) -> Iterator[int | None]:
    """Acquire the AI lock for the duration of a ``with`` block.

    Yields the new run's ``run_id`` (an ``int`` >= 1, always truthy) on
    success, or ``None`` if another action is already running. On success
    the lock is released on context exit even if the body raises. The
    caller is expected to bail out (yield an error event, return 409) when
    ``None`` is yielded — the idiom is ``with hold(...) as acquired: if not
    acquired: <bail>``.

    **WARNING — strictly non-reentrant; this is NOT an ``RLock``.** Calling
    ``hold(...)`` (or :func:`try_acquire`) again from a thread that is
    already inside a held ``hold(...)`` block does NOT re-enter: the nested
    call sees the lock as held and yields ``None`` (busy), so the nested
    body is skipped and its work silently does not run — it does NOT raise,
    so the bug can hide. Structure nested AI work to acquire ONCE at the
    outermost layer and pass the held state inward; never wrap an
    inner AI step in its own ``hold(...)`` when an outer one is live.
    """
    run_id = try_acquire(name, log_path=log_path)
    try:
        yield run_id
    finally:
        if run_id is not None:
            release()


def reset_for_tests() -> None:
    """Test-only: forcibly clear lock + cancel state.

    Real callers must NEVER use this — it bypasses every invariant the
    rest of the API exists to enforce. Tests use it to isolate from each
    other and from leftover state if a test crashes mid-acquire.
    """
    global _current, _current_run_id
    with _state_lock:
        _current = None
        _current_run_id = 0
    _cancel_event.clear()
