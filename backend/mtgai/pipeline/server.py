"""Pipeline API server — FastAPI routes for pipeline orchestration.

Provides endpoints for starting, monitoring, pausing, and resuming
the unified pipeline, plus SSE for real-time progress streaming.
Mounted as a sub-router on the existing review server.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from mtgai.pipeline.engine import PipelineEngine, load_state, save_state
from mtgai.pipeline.events import EventBus, format_sse
from mtgai.pipeline.models import (
    PipelineConfig,
    PipelineState,
    PipelineStatus,
    StageStatus,
    create_pipeline_state,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton state
# ---------------------------------------------------------------------------

event_bus = EventBus()
_engine: PipelineEngine | None = None
_engine_task: asyncio.Task | None = None

# Templates
_templates_dir = Path(__file__).resolve().parent.parent / "gallery" / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter()
api_router = APIRouter(prefix="/api/pipeline")


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------


@router.get("/pipeline", response_class=HTMLResponse)
async def pipeline_dashboard(request: Request):
    """Main pipeline dashboard page."""
    # Try to load state for any existing set
    state = _get_current_state()
    state_json = json.dumps(state.model_dump(mode="json"), default=str) if state else "null"
    return templates.TemplateResponse(
        "pipeline.html",
        {
            "request": request,
            "pipeline_state": state_json,
        },
    )


@router.get("/pipeline/configure", response_class=HTMLResponse)
async def pipeline_configure(request: Request):
    """Pipeline configuration wizard page."""
    from mtgai.pipeline.models import STAGE_DEFINITIONS

    return templates.TemplateResponse(
        "configure.html",
        {
            "request": request,
            "stage_definitions": json.dumps(STAGE_DEFINITIONS),
        },
    )


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


@api_router.get("/state")
async def get_state():
    """Get current pipeline state."""
    state = _get_current_state()
    if state is None:
        return JSONResponse({"status": "no_pipeline"})
    return JSONResponse(state.model_dump(mode="json"))


@api_router.post("/start")
async def start_pipeline(request: Request):
    """Start a new pipeline run with the given configuration."""
    global _engine, _engine_task

    if _engine is not None and _engine.is_running:
        return JSONResponse({"error": "A pipeline is already running"}, status_code=409)

    body = await request.json()
    config = PipelineConfig(**body)

    # Check for existing state — allow resume from previous run
    existing = load_state(config.set_code)
    if existing and existing.overall_status in (
        PipelineStatus.PAUSED,
        PipelineStatus.FAILED,
    ):
        state = existing
        # Update review modes from new config
        for stage in state.stages:
            if stage.stage_id in config.stage_review_modes:
                stage.review_mode = config.stage_review_modes[stage.stage_id]
        state.config = config
    else:
        state = create_pipeline_state(config)

    save_state(state)

    _engine = PipelineEngine(state, event_bus)
    _engine_task = asyncio.create_task(asyncio.to_thread(_engine.run))

    logger.info("Pipeline started for set %s (%d cards)", config.set_code, config.set_size)
    return JSONResponse({"success": True, "run_id": state.run_id})


@api_router.post("/resume")
async def resume_pipeline():
    """Resume pipeline after human review."""
    global _engine, _engine_task

    state = _get_current_state()
    if state is None:
        return JSONResponse({"error": "No pipeline state found"}, status_code=404)

    if state.overall_status != PipelineStatus.PAUSED:
        return JSONResponse(
            {"error": f"Pipeline is {state.overall_status}, not paused"},
            status_code=400,
        )

    _engine = PipelineEngine(state, event_bus)
    _engine_task = asyncio.create_task(asyncio.to_thread(_engine.resume))

    return JSONResponse({"success": True})


@api_router.post("/cancel")
async def cancel_pipeline():
    """Cancel the running pipeline."""
    if _engine is None or not _engine.is_running:
        return JSONResponse({"error": "No pipeline is running"}, status_code=400)

    _engine.cancel()
    return JSONResponse({"success": True})


@api_router.post("/retry")
async def retry_stage():
    """Retry the current failed stage."""
    global _engine, _engine_task

    state = _get_current_state()
    if state is None:
        return JSONResponse({"error": "No pipeline state found"}, status_code=404)

    if state.overall_status != PipelineStatus.FAILED:
        return JSONResponse(
            {"error": f"Pipeline is {state.overall_status}, not failed"},
            status_code=400,
        )

    _engine = PipelineEngine(state, event_bus)
    _engine_task = asyncio.create_task(asyncio.to_thread(_engine.retry_current))

    return JSONResponse({"success": True})


@api_router.post("/skip")
async def skip_stage():
    """Skip the current paused or failed stage."""
    global _engine, _engine_task

    state = _get_current_state()
    if state is None:
        return JSONResponse({"error": "No pipeline state found"}, status_code=404)

    current = state.current_stage()
    if current is None or current.status not in (
        StageStatus.PAUSED_FOR_REVIEW,
        StageStatus.FAILED,
    ):
        return JSONResponse({"error": "Current stage cannot be skipped"}, status_code=400)

    _engine = PipelineEngine(state, event_bus)
    _engine_task = asyncio.create_task(asyncio.to_thread(_engine.skip_current))

    return JSONResponse({"success": True})


@api_router.get("/events")
async def pipeline_events(request: Request):
    """SSE endpoint for real-time pipeline progress updates."""
    queue = event_bus.subscribe()

    async def event_stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield format_sse(event)
                except TimeoutError:
                    # Send keepalive comment to prevent connection timeout
                    yield ": keepalive\n\n"
        finally:
            event_bus.unsubscribe(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering if present
        },
    )


@api_router.get("/logs/{stage_id}")
async def get_stage_logs(stage_id: str):
    """Get log files for a specific stage."""
    state = _get_current_state()
    if state is None:
        return JSONResponse({"error": "No pipeline state"}, status_code=404)

    set_code = state.config.set_code
    set_dir = Path("C:/Programming/MTGAI/output/sets") / set_code

    # Map stage_id to likely log locations
    log_paths: dict[str, list[Path]] = {
        "card_gen": [set_dir / "generation_logs"],
        "ai_review": [set_dir / "reviews"],
        "skeleton_rev": [set_dir / "revision_logs"],
        "art_prompts": [set_dir / "art-direction" / "prompt-logs"],
        "art_select": [set_dir / "art-direction" / "selections"],
        "balance": [set_dir / "reports"],
        "finalize": [set_dir / "reports"],
    }

    paths = log_paths.get(stage_id, [])
    logs: list[dict[str, Any]] = []

    for log_dir in paths:
        if log_dir.exists():
            for f in sorted(log_dir.glob("*.json"))[-20:]:  # Last 20 files
                logs.append(
                    {
                        "filename": f.name,
                        "path": str(f),
                        "size_bytes": f.stat().st_size,
                    }
                )
            for f in sorted(log_dir.glob("*.md"))[-10:]:
                logs.append(
                    {
                        "filename": f.name,
                        "path": str(f),
                        "size_bytes": f.stat().st_size,
                    }
                )

    return JSONResponse({"stage_id": stage_id, "logs": logs})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_current_state() -> PipelineState | None:
    """Get the current pipeline state, preferring in-memory engine state."""
    global _engine
    if _engine is not None:
        return _engine.state

    # Fall back to loading from disk — check all set directories
    output_root = Path("C:/Programming/MTGAI/output/sets")
    if not output_root.exists():
        return None

    # Find the most recently modified pipeline-state.json
    state_files = list(output_root.glob("*/pipeline-state.json"))
    if not state_files:
        return None

    latest = max(state_files, key=lambda p: p.stat().st_mtime)
    set_code = latest.parent.name
    return load_state(set_code)


def get_pipeline_banner_context() -> dict[str, Any] | None:
    """Get minimal pipeline context for the status banner in base.html.

    Returns None if no pipeline is active, otherwise a dict with
    overall_status, current_stage display name, and total_cost.
    """
    state = _get_current_state()
    if state is None:
        return None
    if state.overall_status in (
        PipelineStatus.NOT_STARTED,
        PipelineStatus.COMPLETED,
    ):
        return None

    current = state.current_stage()
    return {
        "overall_status": state.overall_status,
        "current_stage": current.display_name if current else None,
        "current_stage_id": current.stage_id if current else None,
        "total_cost_usd": state.total_cost_usd,
        "run_id": state.run_id,
    }
