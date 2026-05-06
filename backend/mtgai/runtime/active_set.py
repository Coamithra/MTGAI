"""In-memory active-project pointer.

The active set is which MTG project the UI is currently working on.
Since the .mtg file became the persistent project artifact, the
active-set pointer dropped its on-disk form (``last_set.toml``) — a
fresh server process boots with no project loaded, and the wizard
greets the user with New / Open. The pointer lives only in process
memory:

- Set on ``/api/project/{open,materialize}``.
- Cleared on ``/api/project/new``.
- Survives page reload (process is the same).
- Lost on server restart (process death == "no project loaded").

A single Python attribute read/write is atomic in CPython, so no
explicit lock guards ``_active_code``. The project-switch endpoints
that mutate it call :func:`await_lock_release` first to drain any
in-flight AI work — see the lifecycle section in
``plans/tracker_refactor_remove-active-set.md``.

The code shape (``[A-Z0-9]{2,5}``) is the same regex enforced by
``pipeline.server._theme_path`` — kept consistent so set codes
written here can't produce paths the theme endpoints would reject.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time

from mtgai.runtime import ai_lock
from mtgai.runtime.runtime_state import OUTPUT_ROOT, SETS_ROOT

logger = logging.getLogger(__name__)

SET_CODE_RE = re.compile(r"^[A-Z0-9]{2,5}$")

__all__ = [
    "OUTPUT_ROOT",
    "SETS_ROOT",
    "SET_CODE_RE",
    "await_lock_release",
    "await_lock_release_async",
    "clear_active_set",
    "is_valid_set_code",
    "iter_known_set_codes",
    "normalize_code",
    "read_active_set",
    "write_active_set",
]

_active_code: str | None = None


def is_valid_set_code(code: str | None) -> bool:
    """Return True if ``code`` matches the [A-Z0-9]{2,5} shape after
    trimming + uppercasing. Used as the gate on every endpoint so a
    bogus code can't slip through to disk-touching helpers."""
    if not code:
        return False
    return bool(SET_CODE_RE.fullmatch(code.strip().upper()))


def normalize_code(code: str) -> str:
    """Trim and uppercase a set code. Pair with :func:`is_valid_set_code`
    before using the result on disk; this helper does no validation."""
    return code.strip().upper()


def read_active_set() -> str | None:
    """Return the active-project code, or None if no project is open."""
    return _active_code


def write_active_set(code: str) -> None:
    """Set the active-project code. Validates + normalises first."""
    global _active_code
    if not is_valid_set_code(code):
        raise ValueError(f"Invalid set code: {code!r}")
    _active_code = normalize_code(code)


def clear_active_set() -> None:
    """Forget the active project. Used by ``/api/project/new``."""
    global _active_code
    _active_code = None


def iter_known_set_codes() -> list[str]:
    """Yield set codes for every project registered under ``output/sets/``.

    A project is *registered* by a ``settings.toml`` at the canonical
    ``output/sets/<CODE>/settings.toml`` path. The artifact dir for that
    code may then live elsewhere via ``asset_folder``.

    Codes are filtered through :data:`SET_CODE_RE` so stray scratch dirs
    under ``output/sets/`` don't pollute the iteration. Returned sorted
    so callers can rely on a stable order.
    """
    if not SETS_ROOT.exists():
        return []
    out: list[str] = []
    for child in sorted(SETS_ROOT.iterdir()):
        if not child.is_dir() or not SET_CODE_RE.fullmatch(child.name):
            continue
        if not (child / "settings.toml").exists():
            continue
        out.append(child.name)
    return out


def await_lock_release(deadline_s: float = 5.0) -> bool:
    """Block until the AI lock is free, or the deadline elapses.

    Returns True on clean release (or if the lock was never held), False
    on timeout. Synchronous variant for non-async callers / tests; the
    HTTP layer uses :func:`await_lock_release_async` so the event loop
    isn't frozen for up to ``deadline_s``.
    """
    deadline = time.monotonic() + deadline_s
    while ai_lock.is_running():
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)
    return True


async def await_lock_release_async(deadline_s: float = 5.0) -> bool:
    """Async variant of :func:`await_lock_release`.

    Used by ``/api/project/{new,open,materialize}`` after they call
    :func:`ai_lock.request_cancel` to drain a cancellable AI run before
    swapping the active-project pointer. On timeout, callers log a
    warning and proceed anyway — the cancel signal has been sent and the
    run will wind down; we don't block the user forever. Yields to the
    loop between polls so other requests (state aggregator, SSE
    keepalives) keep flowing while we wait.
    """
    deadline = time.monotonic() + deadline_s
    while ai_lock.is_running():
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(0.1)
    return True
