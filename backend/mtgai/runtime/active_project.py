"""In-memory active-project pointer.

The active project is which MTG project the UI is currently working on.
Since the .mtg file became the persistent project artifact, the
active-project pointer dropped its on-disk form (``last_set.toml``) — a
fresh server process boots with no project loaded, and the wizard
greets the user with New / Open. The pointer lives only in process
memory:

- Set on ``/api/project/{open,materialize}``.
- Cleared on ``/api/project/new``.
- Survives page reload (process is the same).
- Lost on server restart (process death == "no project loaded").

A single Python attribute read/write is atomic in CPython, so no
explicit lock guards ``_active_project``. The project-switch endpoints
that mutate it call :func:`await_lock_release` first to drain any
in-flight AI work.

The :class:`ProjectState` carries ``set_code`` + ``settings`` +
``mtg_path``: enough for any helper to resolve the artifact directory,
the model assignments, and the on-disk file path of the source .mtg.
``read_active_set`` / ``write_active_set`` / ``clear_active_set`` are
thin shims kept for callers that haven't been migrated to the
ProjectState API yet.

The code shape (``[A-Z0-9]{2,5}``) is the same regex enforced by
``pipeline.server._theme_path`` — kept consistent so set codes
written here can't produce paths the theme endpoints would reject.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from mtgai.runtime import ai_lock
from mtgai.runtime.runtime_state import OUTPUT_ROOT, SETS_ROOT
from mtgai.settings.model_settings import ModelSettings, get_settings

logger = logging.getLogger(__name__)

SET_CODE_RE = re.compile(r"^[A-Z0-9]{2,5}$")

__all__ = [
    "OUTPUT_ROOT",
    "SETS_ROOT",
    "SET_CODE_RE",
    "ProjectState",
    "await_lock_release",
    "await_lock_release_async",
    "clear_active_project",
    "clear_active_set",
    "is_valid_set_code",
    "iter_known_set_codes",
    "normalize_code",
    "read_active_project",
    "read_active_set",
    "write_active_project",
    "write_active_set",
]


class ProjectState(BaseModel):
    """The currently-open project (settings + .mtg path).

    Holds the resolved ``ModelSettings`` instance directly so callers
    don't need to re-query ``get_settings(set_code)`` every time they
    want the active project's asset folder or model assignments. The
    ``model_settings.apply_settings`` path keeps this in sync — a
    write for the active set rebuilds the ``_active_project`` pointer
    so reads always see the latest values.

    ``mtg_path`` is the on-disk location of the source .mtg file when
    the project was loaded via ``/api/project/open`` and the browser
    forwarded the path. It's ``None`` for projects materialised in-form
    (Save & Start before the user has chosen a file location).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    set_code: str
    settings: ModelSettings
    mtg_path: Path | None = None


_active_project: ProjectState | None = None


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


def read_active_project() -> ProjectState | None:
    """Return the current :class:`ProjectState`, or None if no project is open."""
    return _active_project


def write_active_project(project: ProjectState) -> None:
    """Set the active project. Validates + normalises ``set_code`` first.

    Replaces the previous pointer wholesale; callers wanting to update
    only ``settings`` or ``mtg_path`` should ``model_copy`` the existing
    state and pass the result.
    """
    global _active_project
    if not is_valid_set_code(project.set_code):
        raise ValueError(f"Invalid set code: {project.set_code!r}")
    code = normalize_code(project.set_code)
    if code != project.set_code:
        project = project.model_copy(update={"set_code": code})
    _active_project = project


def clear_active_project() -> None:
    """Forget the active project. Used by ``/api/project/new``."""
    global _active_project
    _active_project = None


def read_active_set() -> str | None:
    """Return the active project's set_code, or None if no project is open.

    Shim around :func:`read_active_project` for callers that only need
    the code. Will be removed when those callers migrate to the
    ProjectState API.
    """
    return _active_project.set_code if _active_project is not None else None


def write_active_set(code: str) -> None:
    """Set the active project from a bare set_code.

    Shim around :func:`write_active_project`: looks up the matching
    settings via ``get_settings(code)`` and packs them into a
    :class:`ProjectState` with no ``mtg_path``. Used by callers that
    haven't been updated to construct a ProjectState directly.
    """
    if not is_valid_set_code(code):
        raise ValueError(f"Invalid set code: {code!r}")
    code = normalize_code(code)
    settings = get_settings(code)
    write_active_project(ProjectState(set_code=code, settings=settings))


def clear_active_set() -> None:
    """Shim — calls :func:`clear_active_project`."""
    clear_active_project()


def iter_known_set_codes() -> list[str]:
    """Yield set codes for every project registered under ``output/sets/``.

    A project is *registered* by a ``settings.toml`` at the canonical
    ``output/sets/<CODE>/settings.toml`` path. The artifact dir for that
    code may then live elsewhere via ``asset_folder``.

    Codes are filtered through :data:`SET_CODE_RE` so stray scratch dirs
    under ``output/sets/`` don't pollute the iteration. Returned sorted
    so callers can rely on a stable order.

    Vestigial — used today only by boot-time cleanup + the dashboard's
    "find the most-recent pipeline" fallback. Slated for deletion in a
    follow-up refactor.
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
