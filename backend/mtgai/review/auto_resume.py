"""Unattended server-side reopen + retry resume for the supervised server.

``serve --supervised`` already auto-restarts the server on a silent crash (the
``art_gen`` Flux OS-kill), but resume was manual: the user re-opened the project
in the wizard — where :func:`cleanup_orphan_running_stages` demotes the orphaned
``RUNNING`` stage to ``FAILED`` — and clicked "Retry this step". This module makes
that resume automatic behind the opt-in ``serve --supervised --auto-resume`` flag,
so a long art run finishes overnight with zero human nursing.

How it fits together:

* The server endpoints persist the active project's ``.mtg`` (its TOML body — the
  browser ships content, not a path) to ``output/supervisor/last-project.mtg``
  while running under the supervisor, so a fresh child process can recover which
  project was open (the in-memory ``active_project`` pointer is lost on restart).
* The supervisor clears that file at session start and re-sets it only as the
  child opens a project, then flags a *restart* child with
  ``MTGAI_AUTO_RESUME=1`` (never the first spawn — a fresh launch must not resume
  a stale project).
* On such a restart the child's lifespan calls :func:`start_auto_resume`, which
  re-opens the persisted project **server-side** (parse + pin +
  ``cleanup_orphan_running_stages`` — exactly what ``/api/project/open`` does),
  finds the orphaned-then-FAILED stage, applies the per-stage retry ceiling, and
  fires ``engine.retry_current`` (resume-skip ⇒ no lost work) via the retry
  endpoint's shared engine-spawn helper.

The whole path is best-effort: any failure logs and leaves the project for a
manual retry, never crashing the boot.
"""

from __future__ import annotations

import json
import logging
import os
import threading

from mtgai.io.atomic import atomic_write_text
from mtgai.runtime import heartbeat

logger = logging.getLogger(__name__)

# Set by the supervisor on a *restart* child (never the first spawn) when
# ``--auto-resume`` is on; tells the child's lifespan to attempt a resume.
ENV_AUTO_RESUME = "MTGAI_AUTO_RESUME"

# How many times we re-fire a FAILED stage that crashes *without making progress*
# before giving up and leaving it for a manual retry. A stage that crashes while
# advancing (the bounded art_gen kill) is never counted against this — see
# :func:`decide` — so a healthy long run resumes indefinitely; this ceiling only
# stops a genuine poison stage that a restart can't get past.
RESUME_CEILING = 3


def is_auto_resume_boot() -> bool:
    """True when the supervisor flagged this child to attempt an auto-resume."""
    return os.environ.get(ENV_AUTO_RESUME) == "1"


def last_project_path():
    """Path of the persisted ``.mtg`` TOML the child recovers on restart."""
    return heartbeat.supervisor_dir() / "last-project.mtg"


def state_path():
    """Path of the per-stage retry-ceiling counter (JSON)."""
    return heartbeat.supervisor_dir() / "auto-resume-state.json"


def write_last_project(toml_text: str) -> None:
    """Persist the active project's ``.mtg`` body (best-effort, atomic)."""
    try:
        path = last_project_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, toml_text)
    except Exception:
        logger.debug("write_last_project failed", exc_info=True)


def read_last_project() -> str | None:
    """Read the persisted ``.mtg`` body, or ``None`` if absent/unreadable."""
    try:
        return last_project_path().read_text(encoding="utf-8")
    except Exception:
        return None


def clear_last_project() -> None:
    """Forget the persisted project (best-effort)."""
    try:
        last_project_path().unlink(missing_ok=True)
    except Exception:
        logger.debug("clear_last_project failed", exc_info=True)


def read_state() -> dict | None:
    """Read the retry-ceiling counter, or ``None`` if absent/unreadable.

    A counter file that parses to a non-dict (corruption / hand-edit) is treated
    as absent so :func:`decide` never sees a non-``dict`` ``prev``.
    """
    try:
        data = json.loads(state_path().read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def write_state(state: dict) -> None:
    """Persist the retry-ceiling counter (best-effort, atomic)."""
    try:
        path = state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, json.dumps(state, indent=2))
    except Exception:
        logger.debug("write_state failed", exc_info=True)


def clear_state() -> None:
    """Reset the retry-ceiling counter (best-effort)."""
    try:
        state_path().unlink(missing_ok=True)
    except Exception:
        logger.debug("clear_state failed", exc_info=True)


def decide(prev: dict | None, instance_id: str, completed: int) -> tuple[bool, dict]:
    """Per-stage retry-ceiling decision (pure).

    ``prev`` is the persisted ``{"instance_id", "attempts", "completed"}`` from the
    previous auto-resume, or ``None`` on the first. Returns
    ``(should_resume, new_state)`` where ``new_state`` is persisted by the caller.

    The guard is **progress-aware**: a stage that crashes while *advancing*
    (``completed`` grew since the last attempt — the bounded ``art_gen`` Flux kill,
    which resume-skip carries past each round) resets the counter, so a long run
    resumes indefinitely. A stage that crashes *without* advancing is a poison pill
    a restart can't fix — its attempts accrue and we stop after ``RESUME_CEILING``,
    pairing with the supervisor's fast-failure boot-loop guard to prevent an endless
    crash-resume loop.
    """
    if prev is None or prev.get("instance_id") != instance_id:
        # First time we see this stage (or the pipeline moved on to a new one).
        return True, {"instance_id": instance_id, "attempts": 1, "completed": completed}

    prev_completed = prev.get("completed", 0) or 0
    if completed > prev_completed:
        # Forward progress since the last attempt → not a poison pill; reset.
        return True, {"instance_id": instance_id, "attempts": 1, "completed": completed}

    attempts = (prev.get("attempts", 0) or 0) + 1
    new_state = {"instance_id": instance_id, "attempts": attempts, "completed": completed}
    return attempts <= RESUME_CEILING, new_state


def start_auto_resume() -> None:
    """Spawn the auto-resume on a daemon thread so it never blocks server boot."""
    threading.Thread(target=maybe_auto_resume, name="mtgai-auto-resume", daemon=True).start()


def maybe_auto_resume() -> None:
    """Re-open the last project and resume its FAILED stage. Best-effort entry point."""
    try:
        _run_auto_resume()
    except Exception:
        logger.exception("auto-resume failed; project left for manual retry")


def _run_auto_resume() -> None:
    toml_text = read_last_project()
    if not toml_text:
        logger.info("auto-resume: no persisted project to resume")
        return

    from mtgai.pipeline import server as pipeline_server
    from mtgai.pipeline.engine import cleanup_orphan_running_stages, load_state, save_state
    from mtgai.pipeline.models import StageStatus
    from mtgai.runtime import active_project, extraction_run
    from mtgai.settings.model_settings import parse_project_toml

    # Defensive: a fresh boot has no engine/extraction running, but the resume
    # thread is detached from the lifespan and spawns an engine directly — never
    # stomp ``_engine``/``_engine_task`` if something already started one (mirrors
    # the manual /instance/retry endpoint's 409 guards).
    if pipeline_server._engine is not None and pipeline_server._engine.is_running:
        logger.warning("auto-resume: a pipeline engine is already running; skipping")
        return
    extraction = extraction_run.current()
    if extraction is not None and extraction.status == "running":
        logger.warning("auto-resume: a theme extraction is already running; skipping")
        return

    try:
        set_code, settings = parse_project_toml(toml_text)
    except ValueError:
        logger.exception("auto-resume: persisted project is unparseable; skipping")
        return

    # Re-open server-side — the exact contract of /api/project/open: pin the
    # pointer, then demote any orphaned RUNNING stage to FAILED.
    active_project.write_active_project(
        active_project.ProjectState(set_code=set_code, settings=settings)
    )
    demoted = cleanup_orphan_running_stages()
    logger.info(
        "auto-resume: reopened %s; demoted orphan stage(s): %s", set_code, demoted or "none"
    )

    state = load_state()
    if state is None:
        logger.info("auto-resume: no pipeline state; nothing to resume")
        return
    target = state.current_stage()
    if target is None or target.status != StageStatus.FAILED:
        target = next((s for s in state.stages if s.status == StageStatus.FAILED), None)
    if target is None:
        logger.info("auto-resume: no failed stage to resume (clean state)")
        return

    completed = target.progress.completed_items or 0
    proceed, new_state = decide(read_state(), target.instance_id, completed)
    write_state(new_state)
    if not proceed:
        logger.warning(
            "auto-resume: stage %s hit the retry ceiling (%d attempts without progress) — "
            "leaving FAILED for manual retry to avoid a crash-resume loop.",
            target.instance_id,
            new_state["attempts"],
        )
        return

    # Anchor the engine on the failed stage (an orphan-reset leaves
    # current_instance_id untouched) and dispatch retry_current via the same
    # helper the manual /instance/retry endpoint uses.
    state.current_instance_id = target.instance_id
    save_state(state)
    logger.warning(
        "auto-resume: resuming FAILED stage %s (attempt %d) after supervised restart",
        target.instance_id,
        new_state["attempts"],
    )
    pipeline_server._spawn_retry_engine(state, set_code)
