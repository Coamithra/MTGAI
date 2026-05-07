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
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from mtgai.runtime import ai_lock
from mtgai.settings.model_settings import ModelSettings

logger = logging.getLogger(__name__)

__all__ = [
    "ProjectState",
    "await_lock_release",
    "await_lock_release_async",
    "clear_active_project",
    "is_valid_set_code",
    "read_active_project",
    "require_active_project",
    "write_active_project",
]


class ProjectState(BaseModel):
    """The currently-open project (settings + .mtg path).

    Holds the resolved ``ModelSettings`` instance directly so callers
    don't need to re-query settings every time they want the active
    project's asset folder or model assignments. The
    ``model_settings.apply_settings`` path keeps this in sync — it
    rewrites the pointer with a fresh ``ModelSettings`` so reads always
    see the latest values.

    ``mtg_path`` is the intended on-disk location of the source .mtg
    file. The current ``/api/project/open`` flow doesn't carry the
    path through (the browser ships only the TOML body via the File
    System Access API), so this field is always ``None`` in production
    today; a follow-up commit plumbs the path through the endpoint and
    populates it on open.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    set_code: str
    settings: ModelSettings
    mtg_path: Path | None = None


_active_project: ProjectState | None = None


def is_valid_set_code(code: str | None) -> bool:
    """Return True if ``code`` is a string (any value, including empty).

    ``set_code`` is purely the label printed on the card frame and stored
    in card JSON — nothing in the runtime keys off it, so empty is fine.
    The only check left is the type guard so endpoints don't accept
    ``None`` / non-string payloads.
    """
    return isinstance(code, str)


def read_active_project() -> ProjectState | None:
    """Return the current :class:`ProjectState`, or None if no project is open."""
    return _active_project


def require_active_project() -> ProjectState:
    """Return the current :class:`ProjectState` or raise.

    Stage runners + helpers operate inside an engine run that's been
    gated at the endpoint layer — by the time they're called, an active
    project must exist. A missing one is a programming error in those
    contexts, so this helper raises rather than returning ``None``. The
    raised :class:`NoAssetFolderError` matches the type
    :func:`set_artifact_dir` raises so callers that already translate
    that to a 409 keep working unchanged.
    """
    from mtgai.io.asset_paths import NoAssetFolderError

    if _active_project is None:
        raise NoAssetFolderError("No project is open")
    return _active_project


def write_active_project(project: ProjectState) -> None:
    """Set the active project.

    Replaces the previous pointer wholesale; callers wanting to update
    only ``settings`` or ``mtg_path`` should ``model_copy`` the existing
    state and pass the result. ``set_code`` is trimmed (no other
    normalisation) — the printed card glyph reflects exactly what the
    user typed; empty strings are accepted (it's purely cosmetic).
    """
    global _active_project
    if not isinstance(project.set_code, str):
        raise ValueError(f"set_code must be a string, got {type(project.set_code).__name__}")
    code = project.set_code.strip()
    if code != project.set_code:
        project = project.model_copy(update={"set_code": code})
    _active_project = project


def clear_active_project() -> None:
    """Forget the active project. Used by ``/api/project/new``."""
    global _active_project
    _active_project = None


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
