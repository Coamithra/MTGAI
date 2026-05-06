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


def _resolve_active_set_code(override: str | None) -> str | None:
    """Pick the set code the front-end should hydrate against.

    Resolution order:

    1. Explicit ``override`` arg if non-empty.
    2. The set persisted in ``output/settings/last_set.toml``. Stale
       entries — codes whose set dir no longer exists — are skipped.
    3. ``None`` — no project is open. Callers must handle this by
       rendering the empty toolbar-only state (Project Settings shows
       only New / Open until the user materialises a project).

    The legacy mtime + ``MTGAI_REVIEW_SET`` + ``"ASD"`` fallbacks were
    dropped when projects became `.mtg` files: a server restart or a
    fresh clone has *no* implicit project, so the wizard greets the
    user with New / Open instead of silently dropping them into a
    half-stale set.
    """
    if override:
        return override.strip().upper()

    # Lazy import — active_set imports OUTPUT_ROOT/SETS_ROOT from this
    # module, so importing at module top would create a cycle.
    from mtgai.runtime.active_set import read_active_set

    return read_active_set()


def _load_theme(set_code: str) -> dict | None:
    """Read the project's ``theme.json`` if present.

    Routes through :func:`set_artifact_dir` so theme.json is read from
    the project's configured ``asset_folder`` when present, else the
    legacy ``output/sets/<CODE>/`` location.
    """
    from mtgai.io.asset_paths import set_artifact_dir

    path = set_artifact_dir(set_code) / "theme.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Failed to read theme.json for %s: %s", set_code, e)
        return None


def _load_pipeline_summary(set_code: str) -> dict | None:
    """Slice of the pipeline state the dashboard banner needs.

    Imports lazily — the runtime module is loaded by the FastAPI server
    process anyway, but the lazy import keeps it cheap when the
    endpoint is hit in a context where pipeline state isn't relevant.
    """
    from mtgai.pipeline.engine import load_state

    state = load_state(set_code)
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


def resolve_active_set_code(override: str | None = None) -> str | None:
    """Public entry-point for the active-set resolution chain.

    Returns ``None`` when no project is loaded — callers must handle
    that case (typically by rendering the no-project shell).
    """
    return _resolve_active_set_code(override)


def compute_runtime_state(set_code_override: str | None = None) -> dict[str, Any]:
    """Build the ``/api/runtime/state`` payload.

    ``active_set`` is ``None`` when no project file is open. The
    pipeline and theme slices are also ``None`` in that case — there
    is no set on disk to load them from.
    """
    from mtgai.runtime.active_set import list_sets

    active_set = _resolve_active_set_code(set_code_override)
    return {
        "active_set": active_set,
        "available_sets": list_sets(),
        "ai_lock": ai_lock.busy_payload(),
        "active_runs": _active_runs_payload(),
        "pipeline": _load_pipeline_summary(active_set) if active_set else None,
        "theme": _load_theme(active_set) if active_set else None,
    }
