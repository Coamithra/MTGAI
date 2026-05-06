"""App-wide runtime state aggregator.

Single source of truth for "what's going on right now across the app",
consumed by ``GET /api/runtime/state`` and used by every page on mount
to hydrate without losing track of in-flight AI work.

The endpoint returns four orthogonal slices:

- ``ai_lock``: the same payload as ``/api/ai/status`` (running flag,
  action name, started_at, log_path).
- ``active_runs``: higher-level "what kinds of work are in flight"
  - currently just ``theme_extraction`` when the extraction-run buffer
  has a live run; forward-compatible with future mechanic / card-gen
  / balance runs.
- ``pipeline``: a thin slice of the most-recent ``PipelineState`` if
  one exists on disk.
- ``theme``: the saved ``theme.json`` for the resolved active set, or
  ``None`` if absent.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from mtgai.runtime import ai_lock, extraction_run

logger = logging.getLogger(__name__)

# `<repo>/output/...`. `runtime_state.py` lives at
# `<repo>/backend/mtgai/runtime/`, so four parents up lands at the repo root.
OUTPUT_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "output"
SETS_ROOT = OUTPUT_ROOT / "sets"


def _resolve_active_set_code() -> str | None:
    """Return the active project's set_code, or None if no project is loaded.

    With a project open the wizard hydrates against its data; with no
    project loaded the callers render the empty New / Open shell (the
    Project Settings tab stays gated until the user materialises a
    project).
    """
    # Lazy import — active_project imports OUTPUT_ROOT/SETS_ROOT from this
    # module, so importing at module top would create a cycle.
    from mtgai.runtime.active_project import read_active_set

    return read_active_set()


def _load_theme() -> dict | None:
    """Read the active project's ``theme.json`` if present.

    Returns ``None`` when no project is open, no ``asset_folder`` is
    configured, or the file is missing / unparseable. Routes through
    :func:`set_artifact_dir` so reads honour the user's chosen
    ``asset_folder``.
    """
    from mtgai.io.asset_paths import NoAssetFolderError, set_artifact_dir

    try:
        path = set_artifact_dir() / "theme.json"
    except NoAssetFolderError:
        return None
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Failed to read theme.json for %s: %s", _resolve_active_set_code(), e)
        return None


def _load_pipeline_summary(set_code: str) -> dict | None:
    """Slice of the pipeline state the dashboard banner needs.

    Imports lazily — the runtime module is loaded by the FastAPI server
    process anyway, but the lazy import keeps it cheap when the
    endpoint is hit in a context where pipeline state isn't relevant.
    Returns ``None`` when ``load_state`` can't reach the artifact dir
    (no project open, or asset_folder unset).
    """
    from mtgai.io.asset_paths import NoAssetFolderError
    from mtgai.pipeline.engine import load_state

    try:
        state = load_state(set_code)
    except NoAssetFolderError:
        return None
    if state is None:
        return None
    current = state.current_stage()
    return {
        "set_code": state.config.set_code,
        "set_name": state.config.set_name,
        "overall_status": state.overall_status,
        "current_stage_id": state.current_stage_id,
        "current_stage": current.display_name if current else None,
        "total_cost_usd": state.total_cost_usd,
        "run_id": state.run_id,
        "updated_at": state.updated_at.isoformat(),
    }


def _active_runs_payload() -> dict[str, dict[str, Any]]:
    """Map of in-flight AI runs the UI may want to reattach to."""
    runs: dict[str, dict[str, Any]] = {}
    er = extraction_run.current()
    if er is None:
        return runs
    # Take the run's lock for a consistent read of status + events
    # length — the worker thread mutates `events` via append_event and
    # `status` via mark_done, both already under this same lock.
    with er.lock:
        if er.status == "running":
            runs["theme_extraction"] = {
                "upload_id": er.upload_id,
                "started_at": er.started_at.isoformat(),
                "events_count": len(er.events),
            }
    return runs


def resolve_active_set_code() -> str | None:
    """Public entry-point for the active-set resolution chain.

    Returns ``None`` when no project is loaded — callers must handle
    that case (typically by rendering the no-project shell).
    """
    return _resolve_active_set_code()


def compute_runtime_state() -> dict[str, Any]:
    """Build the ``/api/runtime/state`` payload.

    ``active_set`` is ``None`` when no project file is open. The
    pipeline and theme slices are also ``None`` in that case — there
    is no set on disk to load them from.
    """
    active_set = _resolve_active_set_code()
    return {
        "active_set": active_set,
        "ai_lock": ai_lock.busy_payload(),
        "active_runs": _active_runs_payload(),
        "pipeline": _load_pipeline_summary(active_set) if active_set else None,
        "theme": _load_theme() if active_set else None,
    }
