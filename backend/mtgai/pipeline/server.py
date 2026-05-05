"""Pipeline API server — FastAPI routes for pipeline orchestration.

Provides endpoints for starting, monitoring, pausing, and resuming
the unified pipeline, plus SSE for real-time progress streaming.
Mounted as a sub-router on the existing review server.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates

from mtgai.pipeline.engine import PipelineEngine, load_state, save_state
from mtgai.pipeline.events import EventBus, format_sse
from mtgai.pipeline.models import (
    STAGE_DEFINITIONS,
    PipelineConfig,
    PipelineState,
    PipelineStatus,
    StageStatus,
    create_pipeline_state,
)
from mtgai.runtime import active_set, ai_lock, extraction_run
from mtgai.runtime.runtime_state import OUTPUT_ROOT, compute_runtime_state

logger = logging.getLogger(__name__)

_SET_CODE_RE = re.compile(r"^[A-Z0-9]{2,5}$")


def _theme_path(set_code: str) -> Path | None:
    """Resolve `output/sets/<CODE>/theme.json` for a validated set code.

    Returns None if the code fails the `[A-Z0-9]{2,5}` shape check —
    callers translate that into a 400. Centralising the path means
    tests can patch this single helper instead of the inline `Path(...)`
    construction inside each endpoint.
    """
    code = (set_code or "").strip().upper()
    if not _SET_CODE_RE.fullmatch(code):
        return None
    return OUTPUT_ROOT / "sets" / code / "theme.json"


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


def _render_configure(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "configure.html",
        {
            "request": request,
            "stage_definitions": json.dumps(STAGE_DEFINITIONS),
        },
    )


@router.get("/pipeline", response_class=HTMLResponse)
async def pipeline_dashboard(request: Request):
    """Render the dashboard, or the configure form when no state exists."""
    state = _get_current_state()
    if state is None:
        return _render_configure(request)
    state_json = json.dumps(state.model_dump(mode="json"), default=str)
    return templates.TemplateResponse(
        "pipeline.html",
        {
            "request": request,
            "pipeline_state": state_json,
        },
    )


@router.get("/pipeline/configure")
async def pipeline_configure() -> RedirectResponse:
    """Legacy route — redirects to the wizard's Project Settings tab.

    The wizard's `/pipeline/project` is what owns per-set kickoff now;
    the standalone configure page is gone. The redirect target lands on
    the wizard shell (placeholder until the shell ships in a later phase).
    """
    return RedirectResponse(url="/pipeline/project", status_code=302)


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
# Shared AI-busy endpoints
# ---------------------------------------------------------------------------


@router.get("/api/ai/status")
async def ai_status() -> JSONResponse:
    """Report what AI action (if any) currently holds the app-wide lock.

    Used by the UI to show an informative "busy" toast when a guarded
    action is rejected with 409. Mounted on the root router (not the
    /api/pipeline-prefixed sub-router) because the lock spans the whole
    app, not just the pipeline.
    """
    return JSONResponse(ai_lock.busy_payload())


@router.post("/api/ai/cancel")
async def ai_cancel() -> JSONResponse:
    """Signal the active AI action to abort. No-op if nothing is running."""
    return JSONResponse({"was_running": ai_lock.request_cancel()})


@router.get("/api/runtime/state")
async def runtime_state(set_code: str | None = None) -> JSONResponse:
    """Aggregate runtime snapshot used by every page on mount.

    Returns active set code, the list of available sets, AI-lock
    payload, in-flight runs (theme extraction etc.), pipeline summary
    if one exists, and the saved theme.json for the active set. Pages
    hydrate from this so tab switches and reloads pick up server-side
    state without losing track of in-flight AI work.
    """
    return JSONResponse(compute_runtime_state(set_code))


@router.post("/api/runtime/active-set")
async def set_active_set(request: Request) -> JSONResponse:
    """Persist the top-bar set picker's selection.

    Body: ``{"code": "<CODE>"}``. The code must be a known set
    directory under ``output/sets/`` — switching to a non-existent set
    is rejected with 404 so the UI can surface "create it first" via
    the new-set modal. Returns the refreshed runtime-state payload so
    the caller can re-render without a follow-up GET.
    """
    body = await request.json()
    raw = body.get("code", "")
    if not isinstance(raw, str) or not active_set.is_valid_set_code(raw):
        return JSONResponse({"error": "Invalid set code"}, status_code=400)
    code = active_set.normalize_code(raw)
    # Read SETS_ROOT off the module each call so tests can monkeypatch
    # it without us having captured a stale reference at import time.
    if not (active_set.SETS_ROOT / code).is_dir():
        return JSONResponse({"error": f"Set {code} does not exist"}, status_code=404)
    try:
        active_set.write_active_set(code)
    except OSError as e:
        logger.error("Failed to persist active set: %s", e)
        return JSONResponse({"error": "Failed to persist active set"}, status_code=500)
    return JSONResponse(compute_runtime_state(code))


@router.post("/api/runtime/sets")
async def create_set_endpoint(request: Request) -> JSONResponse:
    """Scaffold a brand-new set and activate it.

    Body: ``{"code": "<CODE>", "name": "<optional display name>"}``.
    Creates ``output/sets/<CODE>/`` (and a stub ``theme.json`` if a
    name is provided so the picker shows "CODE — Name" right away),
    then persists it as the active set. 409 if the directory already
    exists — callers should switch to it via ``POST
    /api/runtime/active-set`` instead.
    """
    body = await request.json()
    raw = body.get("code", "")
    if not isinstance(raw, str) or not active_set.is_valid_set_code(raw):
        return JSONResponse({"error": "Invalid set code"}, status_code=400)
    name = body.get("name")
    if name is not None and not isinstance(name, str):
        return JSONResponse({"error": "Invalid name"}, status_code=400)
    code = active_set.normalize_code(raw)
    try:
        active_set.create_set(code, name=name)
    except FileExistsError:
        return JSONResponse({"error": f"Set {code} already exists"}, status_code=409)
    except OSError as e:
        logger.error("Failed to scaffold set %s: %s", code, e)
        return JSONResponse({"error": "Failed to create set"}, status_code=500)
    try:
        active_set.write_active_set(code)
    except OSError as e:
        # The directory was created but the active-set pointer didn't
        # land; surfacing 500 here lets the modal show the real error
        # instead of pretending the switch worked and silently snapping
        # back to the old set on next page load.
        logger.error("Failed to persist active set after create: %s", e)
        return JSONResponse(
            {"error": f"Set {code} created but active-set pointer failed to persist: {e}"},
            status_code=500,
        )
    return JSONResponse(compute_runtime_state(code))


# ---------------------------------------------------------------------------
# Theme API routes
# ---------------------------------------------------------------------------


@api_router.post("/theme/save")
async def save_theme(request: Request):
    """Save theme.json for a set, and promote it to the active set.

    Saving a theme is the user's "I'm working on this set now"
    signal, so we also persist the code into ``last_set.toml`` —
    otherwise the next page load would resolve a stale active set
    via ``read_active_set`` and the picker would silently snap back.
    """
    body = await request.json()
    code = (body.get("code") or "").strip().upper()
    theme_path = _theme_path(code)
    if theme_path is None:
        return JSONResponse({"error": "Invalid set code"}, status_code=400)

    theme_path.parent.mkdir(parents=True, exist_ok=True)
    theme_path.write_text(
        json.dumps(body, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Theme saved to %s", theme_path)

    # _theme_path already validated the code, so write_active_set won't
    # raise ValueError — only OSError is reachable here.
    try:
        active_set.write_active_set(code)
    except OSError as e:
        logger.warning("Theme saved but failed to persist active set: %s", e)

    return JSONResponse({"success": True, "path": str(theme_path)})


@api_router.get("/theme/load")
async def load_theme(set_code: str):
    """Return the saved theme.json for ``set_code``, or 404 if absent."""
    theme_path = _theme_path(set_code)
    if theme_path is None:
        return JSONResponse({"error": "Invalid set code"}, status_code=400)
    if not theme_path.exists():
        return JSONResponse({"error": "No theme.json for set"}, status_code=404)

    try:
        data = json.loads(theme_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return JSONResponse({"error": f"Failed to read theme: {e}"}, status_code=500)
    return JSONResponse(data)


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


def _theme_extract_model_key(set_code: str | None = None) -> str:
    """Look up the configured model key for the theme_extract stage.

    Falls back to the active set when ``set_code`` is omitted, which keeps
    the legacy theme-wizard endpoints (no per-request set context yet)
    working until the wizard rewrite plumbs set_code through.
    """
    from mtgai.settings.model_settings import DEFAULT_LLM_ASSIGNMENTS, get_settings

    if set_code is None:
        set_code = active_set.read_active_set()

    if not set_code:
        return DEFAULT_LLM_ASSIGNMENTS.get("theme_extract", "haiku")

    return get_settings(set_code).llm_assignments.get(
        "theme_extract", DEFAULT_LLM_ASSIGNMENTS.get("theme_extract", "haiku")
    )


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
    """Signal the active extraction to abort. No-op if nothing is running.

    Kept for backwards compat with existing UI. ``/api/ai/cancel`` is
    the new front door for the same operation.
    """
    return JSONResponse({"was_running": ai_lock.request_cancel()})


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


def _sse_format(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


def _terminal_status(events: list[dict]) -> str:
    """Decide which lifecycle status to attach to a finished run.

    Looks at the last few events because the constraints pass appends a
    final ``done`` even after a partial subcall failure — we want
    "completed" in that case but "error" / "cancelled" for the cases
    where the worker bailed before finishing.

    If we don't see a recognised terminal event at all, default to
    "error". The worker's ``finally`` only runs after an exception or
    an early-return path, neither of which should be reported as
    success — the front-end's "did the run actually finish?" check
    looks for a ``done`` event in the buffer, not a ``status`` field.
    """
    for event in reversed(events):
        etype = event.get("type")
        if etype == "done":
            return "completed"
        if etype == "cancelled":
            return "cancelled"
        if etype == "error":
            return "error"
    return "error"


def _start_extraction_worker(upload_id: str, source_text: str, model_key: str) -> None:
    """Spawn the extraction worker thread and wire it to the run buffer."""
    from mtgai.pipeline.theme_extractor import (
        clear_phase_emitter,
        set_phase_emitter,
        stream_constraints_extraction,
        stream_theme_extraction,
    )

    def worker() -> None:
        theme_parts: list[str] = []
        theme_cost = 0.0
        try:
            # Phase events flow through the same broadcast buffer the SSE
            # endpoint subscribes to. Wiring this here (rather than from
            # inside theme_extractor) keeps the side-channel scoped to the
            # streaming worker — section-refresh and any future non-streaming
            # caller stays free of phase telemetry it has no consumer for.
            set_phase_emitter(extraction_run.append_event)
            for event in stream_theme_extraction(source_text, model_key):
                etype = event.get("type")
                if etype == "theme_chunk":
                    theme_parts.append(event["text"])
                elif etype == "complete":
                    theme_cost = event.get("cost_usd", 0.0)
                extraction_run.append_event(event)
                if etype in ("error", "cancelled"):
                    return

            full_theme = "".join(theme_parts)
            if not full_theme.strip():
                # Theme stage finished but produced no usable text — emit
                # an explicit error so the front-end's progress UI exits
                # cleanly instead of hanging at 75%.
                extraction_run.append_event(
                    {
                        "type": "error",
                        "message": "Theme extraction produced no text",
                    }
                )
                return

            extraction_run.append_event(
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
                    extraction_run.append_event(
                        {
                            "type": "done",
                            "total_cost_usd": round(total_cost, 4),
                        }
                    )
                    continue
                extraction_run.append_event(event)
        except Exception as e:
            logger.error("Theme extraction stream failed: %s", e, exc_info=True)
            extraction_run.append_event({"type": "error", "message": str(e)})
        finally:
            clear_phase_emitter()
            run = extraction_run.current()
            status = _terminal_status(run.events) if run is not None else "error"
            extraction_run.mark_done(status)
            _upload_cache.pop(upload_id, None)

    threading.Thread(target=worker, daemon=True).start()


async def _stream_subscriber(request: Request, q):
    """Drain a subscriber queue, formatting each event as SSE.

    Keeps a 30 s keepalive so reverse-proxies don't reap the connection
    during long LLM stalls. Disconnect just unsubscribes — the worker
    keeps running and any other subscribers (or a future reattach) still
    see the run progress.
    """
    import queue as _queue

    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.to_thread(q.get, timeout=30.0)
            except _queue.Empty:
                yield ": keepalive\n\n"
                continue
            if extraction_run.is_done_sentinel(event):
                break
            # Defensive default — every producer today emits "type" but
            # a future contributor pushing a typeless dict shouldn't
            # blow up the SSE generator (which the `finally` below
            # would silently swallow as a client disconnect).
            yield _sse_format(event.get("type", "message"), event)
    finally:
        extraction_run.unsubscribe(q)


# Module-level lock guarding the "decide whether this is a fresh start
# or a reattach" critical section in extract-stream. Without it, two
# near-simultaneous fresh-start requests for different upload_ids can
# both pass the `ai_lock.is_running()` gate before either worker
# acquires the AI lock — the second would clobber the first run's
# buffer in extraction_run._run, orphaning the first request's
# subscriber.
_extract_start_lock = threading.Lock()


@api_router.get("/theme/extract-stream")
async def extract_theme_stream(
    request: Request,
    upload_id: str,
    model_key: str | None = None,
):
    """SSE endpoint: stream a theme extraction or reattach to one in flight.

    Three paths:

    1. **Reattach.** If the run buffer already holds a run for this
       ``upload_id``, subscribe and stream replayed + tailed events.
       Works whether the run is still running or already finished —
       late subscribers get the full event log either way.
    2. **Busy.** If a different AI action holds the lock, return 409
       with the busy payload so the UI can render the shared toast.
    3. **Fresh start.** Look up the cached upload, start the worker,
       subscribe, and stream.

    Disconnects unsubscribe but do **not** cancel the run; cancel is
    opt-in via ``POST /api/ai/cancel`` (or its theme alias).
    """
    # The reattach / busy-check / fresh-start sequence must be atomic
    # so two near-simultaneous fresh-start requests for different
    # upload_ids can't both pass the gate and clobber each other's
    # run buffer in extraction_run._run.
    with _extract_start_lock:
        existing = extraction_run.current()
        if existing is not None and existing.upload_id == upload_id:
            mode = "reattach"
        elif ai_lock.is_running():
            return JSONResponse(ai_lock.busy_payload(), status_code=409)
        else:
            cached = _upload_cache.get(upload_id)
            if not cached:
                return JSONResponse({"error": "Upload expired"}, status_code=404)
            if not model_key:
                model_key = _theme_extract_model_key()
            extraction_run.start_run(upload_id)
            _start_extraction_worker(upload_id, cached["text"], model_key)
            mode = "fresh"

        # Subscribe under the same lock so a concurrent start can't
        # land between subscribe() and the worker's first append_event.
        _, q = extraction_run.subscribe()

    logger.debug("extract-stream %s upload_id=%s", mode, upload_id)
    return StreamingResponse(
        _stream_subscriber(request, q),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _stream_section_refresh(theme_text: str, kind: str, model_key: str):
    """Generator: run a section refresh, fan its events + phase ticks as SSE.

    Two event sources merge into one queue:

    1. ``stream_section_extraction`` yields the lifecycle events
       (``constraints`` / ``card_suggestions`` / ``*_error`` / ``done`` /
       ``cancelled``).
    2. The poller registered via ``set_phase_emitter`` pushes ``phase``
       events from a daemon thread while the LLM call is in flight.

    Both go through one ``queue.Queue`` so the SSE consumer sees them in
    arrival order. Worker runs on a thread because the underlying
    extraction is sync.
    """
    import queue as _queue

    from mtgai.pipeline.theme_extractor import (
        clear_phase_emitter,
        set_phase_emitter,
        stream_section_extraction,
    )

    q: _queue.Queue = _queue.Queue()
    DONE = object()

    def push_event(event: dict) -> None:
        q.put(event)

    def worker() -> None:
        try:
            set_phase_emitter(push_event)
            for event in stream_section_extraction(theme_text, model_key, kind):
                q.put(event)
        except Exception as e:
            logger.error("Section refresh (%s) failed: %s", kind, e, exc_info=True)
            q.put({"type": "error", "message": str(e)})
        finally:
            clear_phase_emitter()
            q.put(DONE)

    threading.Thread(target=worker, name=f"section-refresh-{kind}", daemon=True).start()
    return q, DONE


@api_router.post("/theme/extract-section")
async def extract_section_endpoint(request: Request):
    """Refresh one of the AI-extracted sections (constraints OR card_suggestions).

    Returns ``text/event-stream`` so the page can render the same live
    progress banner the full extraction shows. Event types over the wire:

    - ``phase`` — emitter-driven progress ticks (TTFT heartbeat / tok-rate)
    - ``status`` — coarse stage labels yielded by the extractor
    - ``constraints`` / ``card_suggestions`` — final result payload
    - ``constraints_error`` / ``suggestions_error`` — extraction failure
    - ``done`` — terminal event with ``cost_usd``
    - ``error`` — fatal worker exception or busy-lock rejection
    """
    body = await request.json()
    theme_text = body.get("theme_text", "")
    kind = body.get("kind", "constraints")
    model_key = body.get("model_key") or _theme_extract_model_key()

    if not theme_text.strip():
        return JSONResponse({"error": "No theme text provided"}, status_code=400)
    if kind not in ("constraints", "card_suggestions"):
        return JSONResponse({"error": f"Unknown kind: {kind}"}, status_code=400)

    if ai_lock.is_running():
        return JSONResponse(ai_lock.busy_payload(), status_code=409)

    q, DONE = _stream_section_refresh(theme_text, kind, model_key)

    async def generate():
        import queue as _queue

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.to_thread(q.get, timeout=30.0)
                except _queue.Empty:
                    yield ": keepalive\n\n"
                    continue
                if event is DONE:
                    break
                yield _sse_format(event.get("type", "message"), event)
        except Exception as e:
            logger.error("Section refresh stream failed: %s", e, exc_info=True)
            yield _sse_format("error", {"type": "error", "message": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
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

    # Drop the previous run's replay buffer so a fresh subscriber doesn't
    # get historical events from a different run mixed into its stream.
    event_bus.reset_buffer()
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
