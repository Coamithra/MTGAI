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


@router.get("/pipeline/theme", response_class=HTMLResponse)
async def pipeline_theme(request: Request):
    """Theme creation wizard page."""
    return templates.TemplateResponse(
        "theme.html",
        {
            "request": request,
            "existing_theme": "null",
        },
    )


# ---------------------------------------------------------------------------
# Shared AI-busy payload + endpoints
# ---------------------------------------------------------------------------


def _busy_payload() -> dict[str, Any]:
    """Body returned with 409s and from /api/ai/status when an action holds the lock."""
    from mtgai.runtime import ai_lock

    action = ai_lock.current_action()
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


@router.get("/api/ai/status")
async def ai_status() -> JSONResponse:
    """Report what AI action (if any) currently holds the app-wide lock.

    Used by the UI to show an informative "busy" toast when a guarded
    action is rejected with 409. Mounted on the root router (not the
    /api/pipeline-prefixed sub-router) because the lock spans the whole
    app, not just the pipeline.
    """
    return JSONResponse(_busy_payload())


@router.post("/api/ai/cancel")
async def ai_cancel() -> JSONResponse:
    """Signal the active AI action to abort. No-op if nothing is running."""
    from mtgai.runtime import ai_lock

    was_running = ai_lock.request_cancel()
    return JSONResponse({"was_running": was_running})


# ---------------------------------------------------------------------------
# Theme API routes
# ---------------------------------------------------------------------------


@api_router.post("/theme/save")
async def save_theme(request: Request):
    """Save theme.json for a set."""
    body = await request.json()
    code = body.get("code", "").strip().upper()
    if not code:
        return JSONResponse({"error": "Set code required"}, status_code=400)

    set_dir = Path("C:/Programming/MTGAI/output/sets") / code
    set_dir.mkdir(parents=True, exist_ok=True)
    theme_path = set_dir / "theme.json"

    theme_path.write_text(
        json.dumps(body, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Theme saved to %s", theme_path)
    return JSONResponse({"success": True, "path": str(theme_path)})


# In-memory cache for uploaded file content. Entries are evicted by TTL or
# when their extraction completes.
_UPLOAD_TTL_SECONDS = 30 * 60  # 30 minutes
_upload_cache: dict[str, dict[str, Any]] = {}


def _evict_stale_uploads() -> None:
    """Drop upload-cache entries older than _UPLOAD_TTL_SECONDS."""
    import time as _time

    now = _time.monotonic()
    stale = [
        uid
        for uid, entry in _upload_cache.items()
        if now - entry.get("created_at", now) > _UPLOAD_TTL_SECONDS
    ]
    for uid in stale:
        _upload_cache.pop(uid, None)
    if stale:
        logger.info("Evicted %d stale upload(s) from cache", len(stale))


@api_router.post("/theme/upload")
async def upload_for_extraction(request: Request):
    """Upload a file and extract its text (no LLM call yet)."""
    import time as _time
    import uuid

    from starlette.datastructures import UploadFile

    _evict_stale_uploads()

    form = await request.form()
    file = form.get("file")
    if not isinstance(file, UploadFile):
        return JSONResponse({"error": "No file uploaded"}, status_code=400)

    filename = file.filename or "unknown.txt"
    file_bytes = await file.read()

    from mtgai.pipeline.theme_extractor import extract_file_content

    try:
        text = await asyncio.to_thread(extract_file_content, file_bytes, filename)
    except Exception as e:
        logger.error("File extraction failed: %s", e, exc_info=True)
        return JSONResponse({"error": f"Failed to read file: {e}"}, status_code=400)

    if not text.strip():
        return JSONResponse({"error": "No text content found in file"}, status_code=400)

    upload_id = uuid.uuid4().hex[:8]
    _upload_cache[upload_id] = {
        "text": text,
        "filename": filename,
        "created_at": _time.monotonic(),
    }

    return JSONResponse(
        {
            "upload_id": upload_id,
            "filename": filename,
            "char_count": len(text),
            "preview": text[:500],
        }
    )


def _theme_extract_model_key() -> str:
    """Look up the configured model key for the theme_extract stage."""
    from mtgai.settings.model_settings import get_settings

    return get_settings().llm_assignments.get("theme_extract", "haiku")


@api_router.post("/theme/analyze")
async def analyze_extraction_endpoint(request: Request):
    """Analyze uploaded content: count tokens, estimate cost."""
    body = await request.json()
    upload_id = body.get("upload_id", "")
    model_key = body.get("model_key") or _theme_extract_model_key()

    cached = _upload_cache.get(upload_id)
    if not cached:
        return JSONResponse({"error": "Upload expired or not found"}, status_code=404)

    from mtgai.pipeline.theme_extractor import analyze_extraction

    try:
        plan = await asyncio.to_thread(
            analyze_extraction,
            cached["text"],
            model_key,
        )
    except Exception as e:
        logger.error("Extraction analysis failed: %s", e, exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

    return JSONResponse(
        {
            "token_count": plan.token_count,
            "context_window": plan.context_window,
            "fits_in_context": plan.fits_in_context,
            "chunk_count": plan.chunk_count,
            "estimated_cost_usd": round(plan.estimated_cost_usd, 4),
            "model_key": plan.model_key,
            "model_name": plan.model_name,
        }
    )


@api_router.post("/theme/cancel")
async def cancel_theme_extraction():
    """Signal the active extraction to abort. No-op if nothing is running."""
    from mtgai.pipeline.theme_extractor import is_running, request_cancel

    was_running = is_running()
    request_cancel()
    return JSONResponse({"was_running": was_running})


@api_router.get("/theme/status")
async def theme_extraction_status():
    """Report whether an extraction is currently running.

    Kept for backwards compat with existing UI. New callers should use
    ``/api/ai/status`` (broader scope — every AI action, not just theme).
    """
    from mtgai.pipeline.theme_extractor import get_current_log_path, is_running

    log_path = get_current_log_path()
    return JSONResponse(
        {
            "running": is_running(),
            "log_path": str(log_path) if log_path else None,
        }
    )


@api_router.get("/theme/extract-stream")
async def extract_theme_stream(
    request: Request,
    upload_id: str,
    model_key: str | None = None,
):
    """SSE endpoint: stream theme extraction from uploaded document."""
    if not model_key:
        model_key = _theme_extract_model_key()
    cached = _upload_cache.get(upload_id)
    if not cached:
        return JSONResponse({"error": "Upload expired"}, status_code=404)

    import queue
    import threading

    from mtgai.pipeline.theme_extractor import (
        is_running,
        request_cancel,
        stream_constraints_extraction,
        stream_theme_extraction,
    )

    if is_running():
        return JSONResponse(_busy_payload(), status_code=409)

    def _sse(event_type: str, data: dict) -> str:
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    async def event_stream():
        q: queue.Queue[dict | None] = queue.Queue()
        theme_parts: list[str] = []

        def run_extraction():
            theme_cost = 0.0
            try:
                # Step 1: theme extraction
                for event in stream_theme_extraction(cached["text"], model_key):
                    etype = event.get("type")
                    if etype == "theme_chunk":
                        theme_parts.append(event["text"])
                    elif etype == "complete":
                        theme_cost = event.get("cost_usd", 0.0)
                    q.put(event)
                    if etype in ("error", "cancelled"):
                        return

                # Step 2: constraints + card suggestions (streamed so each
                # appears in the UI the moment its subcall returns - the
                # batch version blocks both events behind the slower of the
                # two LLM calls).
                full_theme = "".join(theme_parts)
                if not full_theme.strip():
                    return
                q.put(
                    {
                        "type": "status",
                        "message": "Extracting constraints and card suggestions...",
                    }
                )
                for event in stream_constraints_extraction(full_theme, model_key):
                    etype = event.get("type")
                    if etype == "card_suggestions":
                        event["suggestions"] = [
                            {
                                "name": s.get("name", ""),
                                "description": s.get("description", ""),
                            }
                            for s in event.get("suggestions", [])
                        ]
                    if etype == "done":
                        total_cost = theme_cost + event.get("cost_usd", 0.0)
                        q.put(
                            {
                                "type": "done",
                                "total_cost_usd": round(total_cost, 4),
                            }
                        )
                        continue
                    q.put(event)
            except Exception as e:
                logger.error("Theme extraction stream failed: %s", e, exc_info=True)
                q.put({"type": "error", "message": str(e)})
            finally:
                q.put(None)  # sentinel

        thread = threading.Thread(target=run_extraction, daemon=True)
        thread.start()

        try:
            while True:
                if await request.is_disconnected():
                    # Browser closed / refreshed mid-stream. Tell the worker
                    # to abort so it releases the run lock.
                    request_cancel()
                    break
                try:
                    event = await asyncio.to_thread(q.get, timeout=30.0)
                except Exception:
                    yield ": keepalive\n\n"
                    continue

                if event is None:
                    break

                yield _sse(event["type"], event)

                if event["type"] in ("error", "cancelled"):
                    break
        finally:
            _upload_cache.pop(upload_id, None)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@api_router.post("/theme/extract-section")
async def extract_section_endpoint(request: Request):
    """Refresh one of the AI-extracted sections (constraints OR card_suggestions).

    Splits the old combined endpoint so a "Refresh AI" click on a single
    section only fires its own LLM subcall instead of paying for both and
    discarding half.
    """
    from mtgai.runtime import ai_lock

    body = await request.json()
    theme_text = body.get("theme_text", "")
    kind = body.get("kind", "constraints")
    model_key = body.get("model_key") or _theme_extract_model_key()

    if not theme_text.strip():
        return JSONResponse({"error": "No theme text provided"}, status_code=400)
    if kind not in ("constraints", "card_suggestions"):
        return JSONResponse({"error": f"Unknown kind: {kind}"}, status_code=400)

    if ai_lock.is_running():
        return JSONResponse(_busy_payload(), status_code=409)

    from mtgai.pipeline.theme_extractor import extract_section

    try:
        result = await asyncio.to_thread(extract_section, theme_text, model_key, kind)
        return JSONResponse(
            {
                "constraints": result.constraints,
                "card_suggestions": result.card_suggestions,
                "cost_usd": round(result.cost_usd, 4),
                "constraints_error": result.constraints_error,
                "constraints_raw": result.constraints_raw,
                "suggestions_error": result.suggestions_error,
                "suggestions_raw": result.suggestions_raw,
            }
        )
    except Exception as e:
        logger.error("Section extraction (%s) failed: %s", kind, e, exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


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
