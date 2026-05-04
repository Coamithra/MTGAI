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
import os
from pathlib import Path
from typing import Any

from mtgai.runtime import ai_lock, extraction_run

logger = logging.getLogger(__name__)

# `<repo>/output/...`. `runtime_state.py` lives at
# `<repo>/backend/mtgai/runtime/`, so four parents up lands at the repo root.
OUTPUT_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "output"
SETS_ROOT = OUTPUT_ROOT / "sets"


def _resolve_active_set_code(override: str | None) -> str:
    """Pick the set code the front-end should hydrate against.

    Resolution order:

    1. Explicit ``override`` arg if non-empty.
    2. The set whose ``pipeline-state.json`` *or* ``theme.json`` was
       most recently touched on disk — both markers are merged into
       one mtime-sorted candidate list, so a freshly-saved theme can
       win over a stale pipeline-state and vice versa.
    3. ``MTGAI_REVIEW_SET`` env var.
    4. ``"ASD"``.
    """
    if override:
        return override.strip().upper()

    if SETS_ROOT.exists():
        candidates: list[tuple[float, str]] = []
        for marker in ("pipeline-state.json", "theme.json"):
            for f in SETS_ROOT.glob(f"*/{marker}"):
                try:
                    candidates.append((f.stat().st_mtime, f.parent.name))
                except OSError:
                    continue
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]

    return os.environ.get("MTGAI_REVIEW_SET", "ASD")


def _load_theme(set_code: str) -> dict | None:
    """Read ``output/sets/<CODE>/theme.json`` if present."""
    path = SETS_ROOT / set_code / "theme.json"
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


def compute_runtime_state(set_code_override: str | None = None) -> dict[str, Any]:
    """Build the ``/api/runtime/state`` payload."""
    active_set = _resolve_active_set_code(set_code_override)
    return {
        "active_set": active_set,
        "ai_lock": ai_lock.busy_payload(),
        "active_runs": _active_runs_payload(),
        "pipeline": _load_pipeline_summary(active_set),
        "theme": _load_theme(active_set),
    }
