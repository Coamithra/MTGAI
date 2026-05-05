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
    StageReviewMode,
    StageStatus,
    create_pipeline_state,
)
from mtgai.pipeline.wizard import build_wizard_state
from mtgai.pipeline.wizard import serialize as serialize_wizard_state
from mtgai.runtime import active_set, ai_lock, extraction_run
from mtgai.runtime.runtime_state import (
    OUTPUT_ROOT,
    compute_runtime_state,
    resolve_active_set_code,
)

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


def _render_wizard(request: Request, requested_tab: str | None) -> HTMLResponse | RedirectResponse:
    """Render the wizard shell, or redirect when the requested tab isn't visible.

    Centralises the routing rule: a URL fragment must resolve to a
    visible tab via :func:`build_wizard_state`. If the user typed
    ``/pipeline/skeleton`` before that stage exists, we redirect to the
    latest visible tab so refresh always lands on a real surface.
    """
    set_code = resolve_active_set_code(None)
    ws = build_wizard_state(set_code, requested_tab=requested_tab)
    if requested_tab is not None and ws.active_tab_id != requested_tab:
        return RedirectResponse(
            url=f"/pipeline/{ws.active_tab_id}",
            status_code=302,
        )
    # Pass the serialized snapshot as a dict so Jinja's `tojson` filter
    # in the template can produce a `</script>`-safe blob. `default=str`
    # is unnecessary because `serialize_wizard_state` already coerces
    # `pipeline_state` to JSON-safe types via `model_dump(mode="json")`.
    return templates.TemplateResponse(
        "wizard.html",
        {
            "request": request,
            "wizard_state": serialize_wizard_state(ws),
        },
    )


@router.get("/pipeline", response_class=HTMLResponse)
async def pipeline_root(request: Request):
    """Wizard root — redirect to the latest visible tab.

    Refresh of the bare ``/pipeline`` URL lands on whatever tab is
    currently the right surface for the active set's state (per design
    §11). Bookmarking ``/pipeline`` therefore always re-resolves.
    """
    set_code = resolve_active_set_code(None)
    ws = build_wizard_state(set_code, requested_tab=None)
    return RedirectResponse(url=f"/pipeline/{ws.latest_tab_id}", status_code=302)


@router.get("/pipeline/configure")
async def pipeline_configure() -> RedirectResponse:
    """Legacy route — redirects to the wizard's Project Settings tab."""
    return RedirectResponse(url="/pipeline/project", status_code=302)


@router.get("/pipeline/{tab_id}", response_class=HTMLResponse)
async def pipeline_tab(request: Request, tab_id: str):
    """Wizard tab route — server pre-renders the active tab.

    Tab kinds: ``project`` (always present), ``theme`` (visible once a
    theme.json exists), or one of the pipeline ``stage_id``s. Unknown
    or not-yet-visible fragments redirect to the latest tab so the URL
    always reflects a real surface.
    """
    return _render_wizard(request, requested_tab=tab_id)


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


def _start_extraction_worker(
    upload_id: str,
    source_text: str,
    model_key: str,
    *,
    save_to_set: str | None = None,
) -> None:
    """Spawn the extraction worker thread and wire it to the run buffer.

    When ``save_to_set`` is provided, the worker also writes the
    assembled extraction result to ``output/sets/<SET>/theme.json`` on
    successful completion. This is the path used by the wizard's "Start
    project" button — the user is navigated to the Theme tab while the
    worker runs, and the Theme tab finds a populated theme.json once the
    run terminates.
    """
    from mtgai.pipeline.theme_extractor import (
        clear_phase_emitter,
        set_phase_emitter,
        stream_constraints_extraction,
        stream_theme_extraction,
    )

    def worker() -> None:
        theme_parts: list[str] = []
        theme_cost = 0.0
        constraints_list: list[str] = []
        card_suggestions: list[dict[str, str]] = []
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
                if etype == "constraints":
                    constraints_list = list(event.get("constraints", []))
                elif etype == "card_suggestions":
                    event["suggestions"] = [
                        {
                            "name": s.get("name", ""),
                            "description": s.get("description", ""),
                        }
                        for s in event.get("suggestions", [])
                    ]
                    card_suggestions = list(event["suggestions"])
                if etype == "done":
                    total_cost = theme_cost + event.get("cost_usd", 0.0)
                    if save_to_set:
                        _persist_extraction_to_theme_json(
                            save_to_set, full_theme, constraints_list, card_suggestions
                        )
                        # Auto-advance: with theme.json now on disk, kick
                        # off the pipeline engine so Skeleton (the first
                        # real stage) starts running. The helper refuses
                        # to act on RUNNING / PAUSED states, so re-running
                        # extraction on an in-flight set is a safe no-op.
                        _, kickoff_err = _kickoff_pipeline_engine(save_to_set)
                        if kickoff_err is not None:
                            # Warning, not info: the user expected the
                            # wizard to flow into Skeleton and it didn't
                            # — surfacing this at default log levels
                            # gives the operator a chance to spot it.
                            logger.warning(
                                "Theme to engine auto-advance skipped for %s: %s",
                                save_to_set,
                                kickoff_err,
                            )
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


def _persist_extraction_to_theme_json(
    set_code: str,
    setting_text: str,
    constraints: list[str],
    card_suggestions: list[dict[str, str]],
) -> None:
    """Write the assembled extraction result to ``theme.json``.

    Called from the wizard "Start project" worker once both extraction
    passes finish. Existing keys (``code``, ``name``) are preserved so
    the set picker keeps showing the right title; everything else is
    rewritten from this run.

    Card suggestions arrive as ``{name, description}`` from the LLM
    JSON pass; the Theme tab UI expects ``{text, source}`` items so we
    flatten ``"<name> — <description>"`` here. ``source: "ai"`` is the
    AI-generated badge the wizard renders next to each item.
    """
    from mtgai.settings import model_settings as _ms

    theme_path = OUTPUT_ROOT / "sets" / set_code / "theme.json"
    existing: dict[str, Any] = {}
    if theme_path.exists():
        try:
            existing = json.loads(theme_path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = {}
        except (OSError, json.JSONDecodeError):
            existing = {}

    settings = _ms.get_settings(set_code)
    name = existing.get("name") or settings.set_params.set_name or set_code
    payload = {
        **existing,
        "code": set_code,
        "name": name,
        "setting": setting_text,
        "constraints": [{"text": c, "source": "ai"} for c in constraints if c],
        "card_requests": [
            {
                "text": _format_card_suggestion(s),
                "source": "ai",
            }
            for s in card_suggestions
            if (s.get("name") or s.get("description"))
        ],
    }
    theme_path.parent.mkdir(parents=True, exist_ok=True)
    theme_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Persisted extraction result to %s", theme_path)


def _format_card_suggestion(s: dict[str, str]) -> str:
    name = (s.get("name") or "").strip()
    desc = (s.get("description") or "").strip()
    if name and desc:
        return f"{name} — {desc}"
    return name or desc


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
# Wizard Project Settings tab — set params, theme input, breaks, models, kickoff
# ---------------------------------------------------------------------------


# One row per pipeline stage in pipeline order, including the locked-on
# human_* rows. Render shape for the Project Settings break-points
# section. The bool ("review") comes from the shared
# break_point_states helper so this stays in lockstep with the wizard
# bootstrap payload (mtgai.pipeline.wizard).
def _break_points_payload(settings_obj) -> list[dict[str, Any]]:
    from mtgai.pipeline.models import STAGE_DEFINITIONS, break_point_states

    review_by_stage = break_point_states(settings_obj.break_points)
    return [
        {
            "stage_id": defn["stage_id"],
            "display_name": defn["display_name"],
            "always_review": defn["always_review"],
            "review": review_by_stage[defn["stage_id"]],
        }
        for defn in STAGE_DEFINITIONS
    ]


def _project_payload(set_code: str) -> dict[str, Any]:
    """Bundle everything the Project Settings tab needs on first paint."""
    from mtgai.settings.model_registry import get_registry
    from mtgai.settings.model_settings import (
        PRESETS,
        get_settings,
        list_profiles,
    )

    settings = get_settings(set_code)
    registry = get_registry()
    pipeline_started = (OUTPUT_ROOT / "sets" / set_code / "pipeline-state.json").exists()
    er = extraction_run.current()
    extraction_active = er is not None and er.status == "running"

    # Lightweight registry slice — enough for the dropdowns to render
    # name + tier without a second fetch. Image models too because the
    # Project Settings tab dropdowns include both.
    llm_models = [
        {
            "key": m.key,
            "name": m.name,
            "tier": m.tier,
            "supports_effort": m.supports_effort,
        }
        for m in registry.list_llm()
    ]
    image_models = [
        {"key": m.key, "name": m.name, "implemented": m.implemented} for m in registry.list_image()
    ]

    return {
        "set_code": set_code,
        "set_params": settings.set_params.model_dump(),
        "theme_input": settings.theme_input.model_dump(mode="json"),
        "break_points": _break_points_payload(settings),
        "llm_assignments": dict(settings.llm_assignments),
        "image_assignments": dict(settings.image_assignments),
        "effort_overrides": dict(settings.effort_overrides),
        "llm_models": llm_models,
        "image_models": image_models,
        "builtin_presets": sorted(PRESETS),
        "saved_profiles": list_profiles(),
        "pipeline_started": pipeline_started,
        "extraction_active": extraction_active,
    }


def _validate_set_code_in_body(body: dict) -> tuple[str, JSONResponse | None]:
    """Pull set_code out of a request body, validating it.

    Returns ``(code, None)`` on success or ``("", JSONResponse(400))``
    so callers can ``if err: return err``. Centralised so every wizard
    endpoint reports the same shape.
    """
    raw = body.get("set_code")
    if not isinstance(raw, str) or not active_set.is_valid_set_code(raw):
        return "", JSONResponse({"error": "Invalid set_code"}, status_code=400)
    return active_set.normalize_code(raw), None


@router.get("/api/wizard/project")
async def wizard_project_payload(set_code: str | None = None) -> JSONResponse:
    """Bundle the Project Settings tab's first-paint state.

    Falls back to the active set when ``set_code`` is omitted so the
    wizard's URL routing (which never carries the set in the URL path)
    can call this without an explicit query string.
    """
    if not set_code:
        set_code = active_set.read_active_set()
    if not set_code or not active_set.is_valid_set_code(set_code):
        return JSONResponse({"error": "No active set"}, status_code=400)
    code = active_set.normalize_code(set_code)
    if not (OUTPUT_ROOT / "sets" / code).is_dir():
        return JSONResponse({"error": f"Set {code} does not exist"}, status_code=404)
    return JSONResponse(_project_payload(code))


@router.post("/api/wizard/project/params")
async def wizard_project_save_params(request: Request) -> JSONResponse:
    """Live-apply set_name / mechanic_count; gate set_size post-Start.

    set_name + mechanic_count flow through immediately — they don't
    invalidate any downstream artifact. set_size flips the skeleton's
    target so editing it once a pipeline-state.json exists requires the
    cascade-clear edit flow (§9 card). Until that ships the field is
    read-only post-Start; this endpoint rejects the change with 409.
    """
    from mtgai.settings.model_settings import (
        SetParams,
        apply_settings,
        get_settings,
    )

    body = await request.json()
    code, err = _validate_set_code_in_body(body)
    if err:
        return err

    settings = get_settings(code)
    current = settings.set_params
    name = body.get("set_name", current.set_name)
    mech = body.get("mechanic_count", current.mechanic_count)
    size = body.get("set_size", current.set_size)

    if not isinstance(name, str):
        return JSONResponse({"error": "set_name must be a string"}, status_code=400)
    if not isinstance(mech, int) or mech < 0:
        return JSONResponse({"error": "mechanic_count must be a non-negative int"}, status_code=400)
    if not isinstance(size, int) or size <= 0:
        return JSONResponse({"error": "set_size must be a positive int"}, status_code=400)

    pipeline_started = (OUTPUT_ROOT / "sets" / code / "pipeline-state.json").exists()
    if pipeline_started and size != current.set_size:
        return JSONResponse(
            {
                "error": (
                    "Changing target size after the pipeline has started requires "
                    "the Edit flow — POST /api/wizard/edit/accept with from_stage='project' "
                    "and set_params_patch={set_size: ...}."
                ),
            },
            status_code=409,
        )

    new = settings.model_copy(
        update={"set_params": SetParams(set_name=name, set_size=size, mechanic_count=mech)}
    )
    apply_settings(code, new)
    return JSONResponse({"success": True, "set_params": new.set_params.model_dump()})


@router.post("/api/wizard/project/theme-input")
async def wizard_project_save_theme_input(request: Request) -> JSONResponse:
    """Persist the Project Settings theme-input pointer.

    Receives the result of an upload (``upload_id`` + filename +
    char_count) or a switch back to ``existing`` (the user picked
    "Load existing theme.json"). Same cascade-clear gate as
    :func:`wizard_project_save_params` — once a pipeline state exists,
    swapping the input source is deferred to the §9 edit flow.
    """
    from mtgai.settings.model_settings import (
        ThemeInputSource,
        apply_settings,
        get_settings,
    )

    body = await request.json()
    code, err = _validate_set_code_in_body(body)
    if err:
        return err

    kind = body.get("kind")
    if kind not in ("none", "pdf", "text", "existing"):
        return JSONResponse({"error": "Invalid theme-input kind"}, status_code=400)

    settings = get_settings(code)
    pipeline_started = (OUTPUT_ROOT / "sets" / code / "pipeline-state.json").exists()
    if pipeline_started and settings.theme_input.kind != kind:
        return JSONResponse(
            {
                "error": (
                    "Changing the theme input after the pipeline has started requires "
                    "the Edit flow — POST /api/wizard/edit/accept with from_stage='project', "
                    "theme_input={...}, and clear_theme_json=true."
                ),
            },
            status_code=409,
        )

    new_input = ThemeInputSource(
        kind=kind,
        filename=body.get("filename") if isinstance(body.get("filename"), str) else None,
        upload_id=body.get("upload_id") if isinstance(body.get("upload_id"), str) else None,
        char_count=body.get("char_count") if isinstance(body.get("char_count"), int) else None,
    )
    if new_input.kind in ("pdf", "text"):
        # Stamp uploaded_at server-side so the client can't lie about
        # freshness — the upload-cache TTL check in `start` is what
        # actually prevents a stale extraction from running, but the
        # timestamp gives the audit trail the right value too.
        from datetime import UTC, datetime

        new_input = new_input.model_copy(update={"uploaded_at": datetime.now(UTC)})

    new = settings.model_copy(update={"theme_input": new_input})
    apply_settings(code, new)
    return JSONResponse({"success": True, "theme_input": new.theme_input.model_dump(mode="json")})


@router.post("/api/wizard/project/breaks")
async def wizard_project_save_break(request: Request) -> JSONResponse:
    """Toggle one break point on or off (live-apply).

    Body: ``{set_code, stage_id, review: bool}``. Always_review stages
    are rejected with 400 — those are locked-on at the engine level and
    the UI renders them as such, so accepting writes for them would
    silently no-op and confuse anyone hand-poking the endpoint.
    """
    from mtgai.pipeline.models import STAGE_DEFINITIONS
    from mtgai.settings.model_settings import apply_settings, get_settings

    body = await request.json()
    code, err = _validate_set_code_in_body(body)
    if err:
        return err

    stage_id = body.get("stage_id")
    review = body.get("review")
    if not isinstance(stage_id, str) or not isinstance(review, bool):
        return JSONResponse({"error": "stage_id (str) and review (bool) required"}, status_code=400)

    defn = next((d for d in STAGE_DEFINITIONS if d["stage_id"] == stage_id), None)
    if defn is None:
        return JSONResponse({"error": f"Unknown stage_id {stage_id!r}"}, status_code=400)
    if defn["always_review"]:
        return JSONResponse(
            {"error": f"{stage_id} is always_review — break point is locked on"},
            status_code=400,
        )

    settings = get_settings(code)
    breaks = dict(settings.break_points)
    if review:
        breaks[stage_id] = "review"
    else:
        breaks.pop(stage_id, None)

    new = settings.model_copy(update={"break_points": breaks})
    apply_settings(code, new)
    return JSONResponse({"success": True, "break_points": breaks})


@router.post("/api/wizard/project/models")
async def wizard_project_save_model(request: Request) -> JSONResponse:
    """Live-apply a single model assignment (or effort override).

    Body: ``{set_code, kind: "llm" | "image" | "effort", stage_id, value}``.
    The wizard's dropdowns POST one of these per change so we don't have
    to round-trip the entire ``ModelSettings`` shape on every keystroke.
    """
    from mtgai.settings.model_settings import apply_settings, get_settings

    body = await request.json()
    code, err = _validate_set_code_in_body(body)
    if err:
        return err

    kind = body.get("kind")
    stage_id = body.get("stage_id")
    value = body.get("value")
    if kind not in ("llm", "image", "effort"):
        return JSONResponse({"error": "kind must be llm | image | effort"}, status_code=400)
    if not isinstance(stage_id, str) or not stage_id:
        return JSONResponse({"error": "stage_id required"}, status_code=400)
    if not isinstance(value, str):
        return JSONResponse({"error": "value must be a string"}, status_code=400)

    settings = get_settings(code)
    if kind == "llm":
        new_map = dict(settings.llm_assignments)
        new_map[stage_id] = value
        new = settings.model_copy(update={"llm_assignments": new_map})
    elif kind == "image":
        new_map = dict(settings.image_assignments)
        new_map[stage_id] = value
        new = settings.model_copy(update={"image_assignments": new_map})
    else:  # effort
        new_map = dict(settings.effort_overrides)
        if value:
            new_map[stage_id] = value
        else:
            new_map.pop(stage_id, None)
        new = settings.model_copy(update={"effort_overrides": new_map})

    apply_settings(code, new)
    return JSONResponse({"success": True})


@router.post("/api/wizard/project/preset/apply")
async def wizard_project_apply_preset(request: Request) -> JSONResponse:
    """Apply a built-in preset or saved profile to this set's settings.

    Per §6.8 / §6.4, model assignments and break points come from the
    preset; per-set values (set_params, theme_input) are NOT touched.
    Live-apply — no cascade clear — because model swaps don't
    invalidate already-generated artifacts.
    """
    from mtgai.settings.model_settings import (
        ModelSettings,
        apply_settings,
        get_settings,
    )

    body = await request.json()
    code, err = _validate_set_code_in_body(body)
    if err:
        return err
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        return JSONResponse({"error": "Preset name required"}, status_code=400)

    try:
        preset = ModelSettings.from_preset(name.strip())
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    current = get_settings(code)
    merged = current.model_copy(
        update={
            "llm_assignments": dict(preset.llm_assignments),
            "image_assignments": dict(preset.image_assignments),
            "effort_overrides": dict(preset.effort_overrides),
            "break_points": dict(preset.break_points),
        }
    )
    apply_settings(code, merged)
    return JSONResponse({"success": True})


@router.post("/api/wizard/project/preset/save")
async def wizard_project_save_preset(request: Request) -> JSONResponse:
    """Save this set's model assignments + break points as a profile."""
    from mtgai.settings.model_settings import get_settings

    body = await request.json()
    code, err = _validate_set_code_in_body(body)
    if err:
        return err
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        return JSONResponse({"error": "Profile name required"}, status_code=400)

    settings = get_settings(code)
    try:
        path = settings.save_profile(name.strip())
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"success": True, "path": str(path)})


@router.post("/api/wizard/project/start")
async def wizard_project_start(request: Request) -> JSONResponse:
    """Kick off theme extraction for the chosen input.

    Three branches by ``settings.theme_input.kind``:

    * ``"existing"`` — theme.json already exists; just tell the wizard
      to navigate to the Theme tab. No extraction runs.
    * ``"pdf"`` / ``"text"`` — look up the cached upload, start the
      extraction worker (which writes theme.json on completion), and
      return the navigation hint. Returns 409 if the AI mutex is held.
    * ``"none"`` — refuse with 400; the Start button should not have
      been enabled.
    """
    from mtgai.settings.model_settings import get_settings

    body = await request.json()
    code, err = _validate_set_code_in_body(body)
    if err:
        return err

    settings = get_settings(code)
    kind = settings.theme_input.kind
    if kind == "none":
        return JSONResponse(
            {"error": "Choose a theme input before starting"},
            status_code=400,
        )

    if kind == "existing":
        # Theme.json already on disk — Project Settings is done; the
        # wizard transitions to Theme without spawning an extraction.
        return JSONResponse(
            {"success": True, "extraction_started": False, "navigate_to": "/pipeline/theme"}
        )

    upload_id = settings.theme_input.upload_id
    if not upload_id:
        return JSONResponse(
            {"error": "Theme input is missing upload_id — re-upload the file"},
            status_code=400,
        )

    cached = _upload_cache.get(upload_id)
    if not cached:
        return JSONResponse(
            {"error": "Upload expired — please re-upload the file"},
            status_code=410,
        )

    # The fresh-start race in /theme/extract-stream is guarded by an
    # extra module-level lock; the kickoff path can't collide with that
    # because it acquires the AI lock atomically below before starting
    # the worker, and the new worker is the only writer to
    # extraction_run._run after we call start_run().
    if ai_lock.is_running():
        return JSONResponse(ai_lock.busy_payload(), status_code=409)

    model_key = settings.llm_assignments.get("theme_extract", "haiku")
    extraction_run.start_run(upload_id)
    _start_extraction_worker(upload_id, cached["text"], model_key, save_to_set=code)
    return JSONResponse(
        {
            "success": True,
            "extraction_started": True,
            "navigate_to": "/pipeline/theme",
            "upload_id": upload_id,
        }
    )


# ---------------------------------------------------------------------------
# Wizard advance — auto-advance + Next-step button
# ---------------------------------------------------------------------------


def _build_pipeline_config_from_settings(set_code: str) -> PipelineConfig:
    """Build a :class:`PipelineConfig` from the per-set settings.toml.

    Wizard kickoff path uses this to translate the persisted
    ``set_params`` + ``break_points`` into the engine's input shape:
    set parameters become top-level fields; break_points (str
    ``"review"`` / ``"auto"``) translate to ``StageReviewMode`` entries
    keyed by stage_id. ``always_review`` stages are also forced to
    REVIEW so the engine pauses for them even if settings.toml omits
    the entry.
    """
    from mtgai.settings.model_settings import get_settings

    settings = get_settings(set_code)
    sp = settings.set_params
    review_modes: dict[str, StageReviewMode] = {}
    for defn in STAGE_DEFINITIONS:
        sid = defn["stage_id"]
        if defn["always_review"] or settings.break_points.get(sid) == "review":
            review_modes[sid] = StageReviewMode.REVIEW
    return PipelineConfig(
        set_code=set_code,
        set_name=sp.set_name or set_code,
        set_size=sp.set_size,
        stage_review_modes=review_modes,
    )


def _first_pending_stage_id(state: PipelineState) -> str | None:
    """Return the stage_id of the first non-completed, non-skipped stage."""
    for stage in state.stages:
        if stage.status not in (StageStatus.COMPLETED, StageStatus.SKIPPED):
            return stage.stage_id
    return None


def _kickoff_pipeline_engine(set_code: str) -> tuple[PipelineState | None, str | None]:
    """Spawn the engine for ``set_code`` if it isn't already running.

    Used by the wizard's Theme→Skeleton handoff (both the explicit
    Next-step button on Theme and the post-extraction auto-advance hook
    in the worker thread). Refuses to act on a state that's already
    live or that needs a different transition:

    * Engine already running in this process → returns ``"A pipeline is
      already running"``.
    * Disk state has overall_status RUNNING with no attached engine →
      returns the orphan error. ``cleanup_orphan_running_stages`` should
      demote those at boot; reaching this branch means something raced.
    * Disk state has overall_status PAUSED → returns ``"Pipeline is
      paused, use resume instead"``. Re-entering ``engine.run`` on a
      PAUSED state would re-call the runner of the paused stage and
      discard the human review (engine.py only skips
      ``COMPLETED``/``SKIPPED``).
    * Otherwise (no state, NOT_STARTED, FAILED, COMPLETED, CANCELLED) →
      reuse or create the state, persist, and spawn the engine.

    Spawned in a daemon thread so the helper is callable from a worker
    thread (no asyncio loop) and from async handlers (no await needed).

    Returns ``(state, error)``. On success, ``state`` is non-None and
    ``error`` is None. On failure, returns ``(None, "<reason>")``.
    """
    global _engine, _engine_task

    if _engine is not None and _engine.is_running:
        return None, "A pipeline is already running"

    existing = load_state(set_code)
    if existing is not None:
        if existing.overall_status == PipelineStatus.RUNNING:
            return None, "Pipeline state is RUNNING but no engine is attached"
        if existing.overall_status == PipelineStatus.PAUSED:
            return None, "Pipeline is paused, use resume instead"

    if existing is None:
        state = create_pipeline_state(_build_pipeline_config_from_settings(set_code))
    else:
        state = existing

    save_state(state)
    event_bus.reset_buffer()
    _engine = PipelineEngine(state, event_bus)
    threading.Thread(target=_engine.run, name=f"pipeline-{set_code}", daemon=True).start()
    _engine_task = None
    return state, None


@router.post("/api/wizard/advance")
async def wizard_advance(request: Request) -> JSONResponse:
    """Single Next-step entry point used by the wizard footer button.

    Routes by the current pipeline state for the given set:

    * No pipeline-state.json yet → kick off the engine (Theme tab footer
      hits this once the user is ready to start the pipeline; the theme
      extraction worker also calls the underlying helper directly so
      auto-advance works even if no client is watching).
    * ``overall_status == PAUSED`` → resume the engine (the typical
      path after a break point or always_review pause).
    * Otherwise → 400; the wizard hides the button in those states, so
      reaching this branch implies a client/server state drift.

    Always returns the next stage id under ``next_stage_id`` so the
    client can update the URL on the explicit click path. Auto-advance
    paths don't need this — SSE handles tab spawning in place.
    """
    body = await request.json()
    code, err = _validate_set_code_in_body(body)
    if err:
        return err

    existing = load_state(code)
    if existing is None:
        # Brand-new — kick off the engine. The wizard reaches this from
        # the Theme tab's Next-step button when the user manually
        # advances after extraction (auto-advance handles the common
        # case from the worker thread).
        state, kickoff_err = _kickoff_pipeline_engine(code)
        if kickoff_err is not None or state is None:
            return JSONResponse({"error": kickoff_err or "Kickoff failed"}, status_code=409)
        next_id = _first_pending_stage_id(state)
        return JSONResponse(
            {
                "success": True,
                "next_stage_id": next_id,
                "navigate_to": f"/pipeline/{next_id}" if next_id else "/pipeline",
            }
        )

    if existing.overall_status == PipelineStatus.PAUSED:
        global _engine, _engine_task

        # Same guard the kickoff helper uses + every other engine-touching
        # endpoint (start/resume/retry/skip): refuse to clobber a live
        # engine reference. Without this a double-click or a concurrent
        # request would overwrite ``_engine`` mid-run, leaving the prior
        # daemon thread orphaned and untraceable.
        if _engine is not None and _engine.is_running:
            return JSONResponse({"error": "A pipeline is already running"}, status_code=409)

        _engine = PipelineEngine(existing, event_bus)
        _engine_task = asyncio.create_task(asyncio.to_thread(_engine.resume))
        # Don't return navigate_to on resume: the user clicked Next-step
        # from the paused tab, so we want them to stay there (SSE will
        # spawn the next tab in the strip without stealing focus).
        return JSONResponse({"success": True})

    return JSONResponse(
        {"error": f"Pipeline is {existing.overall_status.value}, cannot advance"},
        status_code=400,
    )


# ---------------------------------------------------------------------------
# Wizard edit flow — cascade-clear past tabs (design §9)
# ---------------------------------------------------------------------------


def _resolve_edit_point(from_stage: str, state: PipelineState | None) -> int:
    """Translate an edit-point label to the first pipeline-stage index to reset.

    Project Settings and Theme are pre-pipeline surfaces (the user is editing
    inputs that feed stage 0), so an edit on either resets the whole pipeline.
    A pipeline ``stage_id`` resets that stage + everything after.

    Returns the integer index into ``state.stages`` where the cascade starts.
    Raises ``ValueError`` for an unknown ``from_stage`` so the caller can
    surface a 400.
    """
    if from_stage in ("project", "theme"):
        return 0
    if state is None:
        raise ValueError(f"Cannot resolve {from_stage!r}: no pipeline state on disk")
    for idx, stage in enumerate(state.stages):
        if stage.stage_id == from_stage:
            return idx
    raise ValueError(f"Unknown stage id {from_stage!r}")


def _compute_cascade_preview(
    set_code: str,
    from_stage: str,
    *,
    clear_theme_json: bool,
) -> dict[str, Any]:
    """Enumerate what the §9 cascade-clear would remove.

    Read-only — does not mutate state. Counts come from the on-disk
    pipeline-state.json's per-stage progress so they reflect what was
    actually generated, not what the design tops out at.

    The returned ``cleared`` list is in pipeline order (matches
    STAGE_DEFINITIONS) for stages from the cascade boundary onward whose
    status is anything other than ``PENDING`` — completed, running,
    paused, failed, or skipped artifacts all get reported. PENDING stages
    have nothing to clear so they're omitted from the list (the modal
    looks empty for those, which is the right "nothing to lose" signal).
    """
    state = load_state(set_code)
    start_idx = _resolve_edit_point(from_stage, state)
    cleared: list[dict[str, Any]] = []
    if state is not None:
        for stage in state.stages[start_idx:]:
            if stage.status == StageStatus.PENDING:
                continue
            count = stage.progress.completed_items or stage.progress.total_items
            cleared.append(
                {
                    "stage_id": stage.stage_id,
                    "display_name": stage.display_name,
                    "status": stage.status.value,
                    "item_count": int(count or 0),
                }
            )
    theme_json_present = (OUTPUT_ROOT / "sets" / set_code / "theme.json").exists()
    return {
        "cleared": cleared,
        "clear_theme_json": bool(clear_theme_json and theme_json_present),
        "pipeline_running": _engine is not None and _engine.is_running,
    }


@router.post("/api/wizard/edit/preview")
async def wizard_edit_preview(request: Request) -> JSONResponse:
    """Return the cascade enumeration the §9 modal renders.

    Body: ``{set_code, from_stage, clear_theme_json?}``. ``from_stage``
    is ``"project"``, ``"theme"``, or one of the pipeline stage_ids; the
    helper resolves it to the first stage index to reset. ``clear_theme_json``
    is set when the user is editing the theme-input field on Project Settings
    (the cascade also wipes theme.json so the next Start re-extracts).
    """
    body = await request.json()
    code, err = _validate_set_code_in_body(body)
    if err:
        return err
    from_stage = body.get("from_stage")
    if not isinstance(from_stage, str) or not from_stage:
        return JSONResponse({"error": "from_stage required"}, status_code=400)
    clear_theme_json = bool(body.get("clear_theme_json"))

    try:
        return JSONResponse(
            _compute_cascade_preview(code, from_stage, clear_theme_json=clear_theme_json)
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


def _apply_cascade_clear(
    set_code: str,
    state: PipelineState,
    start_idx: int,
) -> None:
    """Run STAGE_CLEARERS for stages[start_idx:] and reset them to PENDING.

    Persists the updated pipeline-state.json. Per-stage clearers handle
    their own idempotency (missing files / dirs are fine), so this is
    safe to call whether or not the cascade overlaps already-cleared
    state. ``current_stage_id`` is dropped if it pointed at a stage in
    the cleared range.
    """
    from mtgai.pipeline.stages import clear_stage_artifacts

    for stage in state.stages[start_idx:]:
        try:
            clear_stage_artifacts(stage.stage_id, set_code)
        except OSError as e:
            logger.warning(
                "Cascade clear for %s/%s raised %s; continuing",
                set_code,
                stage.stage_id,
                e,
            )
        stage.status = StageStatus.PENDING
        stage.progress = stage.progress.model_copy(
            update={
                "total_items": 0,
                "completed_items": 0,
                "failed_items": 0,
                "current_item": None,
                "detail": "",
                "cost_usd": 0.0,
                "started_at": None,
                "finished_at": None,
                "error_message": None,
            }
        )

    if state.current_stage_id is not None:
        cleared_ids = {s.stage_id for s in state.stages[start_idx:]}
        if state.current_stage_id in cleared_ids:
            state.current_stage_id = None

    if any(s.status != StageStatus.COMPLETED for s in state.stages):
        state.overall_status = PipelineStatus.NOT_STARTED
    save_state(state)


@router.post("/api/wizard/edit/accept")
async def wizard_edit_accept(request: Request) -> JSONResponse:
    """Persist edits, run cascade clear, kick the engine off again.

    Body shape::

        {
          set_code: str,
          from_stage: "project" | "theme" | <stage_id>,
          clear_theme_json: bool,
          # Optional payloads (combined as needed for the edit point):
          theme_payload: <theme.json content>,
          set_params_patch: { set_size?, set_name?, mechanic_count? },
          theme_input: { kind, upload_id?, filename?, char_count? },
        }

    Refuses with 409 if the pipeline engine is currently running — the
    user must cancel the in-flight stage first. This keeps the cascade
    code synchronous + simple at the cost of one extra click for the
    rare case of mid-run edits (acceptable for v1).

    Returns ``{success, navigate_to, next_stage_id?}``. ``navigate_to``
    points at the project tab when theme.json was cleared (the user
    clicks Start to re-extract), otherwise at the first stage that will
    re-run.
    """
    from mtgai.settings.model_settings import (
        SetParams,
        ThemeInputSource,
        apply_settings,
        get_settings,
    )

    body = await request.json()
    code, err = _validate_set_code_in_body(body)
    if err:
        return err
    from_stage = body.get("from_stage")
    if not isinstance(from_stage, str) or not from_stage:
        return JSONResponse({"error": "from_stage required"}, status_code=400)
    clear_theme_json = bool(body.get("clear_theme_json"))

    if _engine is not None and _engine.is_running:
        return JSONResponse(
            {
                "error": (
                    "A pipeline stage is currently running. Cancel it from the "
                    "global progress strip, then retry the edit."
                )
            },
            status_code=409,
        )

    state = load_state(code)
    try:
        start_idx = _resolve_edit_point(from_stage, state)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    # 1. Persist any caller-supplied input edits before touching artifacts.
    set_params_patch = body.get("set_params_patch")
    theme_input_patch = body.get("theme_input")
    theme_payload = body.get("theme_payload")

    if set_params_patch is not None or theme_input_patch is not None:
        if not isinstance(set_params_patch or {}, dict) or not isinstance(
            theme_input_patch or {}, dict
        ):
            return JSONResponse(
                {"error": "set_params_patch and theme_input must be objects"},
                status_code=400,
            )
        settings = get_settings(code)
        update: dict[str, Any] = {}
        if isinstance(set_params_patch, dict):
            sp = settings.set_params
            new_sp = SetParams(
                set_name=set_params_patch.get("set_name", sp.set_name),
                set_size=set_params_patch.get("set_size", sp.set_size),
                mechanic_count=set_params_patch.get("mechanic_count", sp.mechanic_count),
            )
            update["set_params"] = new_sp
        if isinstance(theme_input_patch, dict):
            kind = theme_input_patch.get("kind")
            if kind not in ("none", "pdf", "text", "existing"):
                return JSONResponse(
                    {"error": f"Invalid theme_input.kind {kind!r}"},
                    status_code=400,
                )
            new_ti = ThemeInputSource(
                kind=kind,
                filename=theme_input_patch.get("filename")
                if isinstance(theme_input_patch.get("filename"), str)
                else None,
                upload_id=theme_input_patch.get("upload_id")
                if isinstance(theme_input_patch.get("upload_id"), str)
                else None,
                char_count=theme_input_patch.get("char_count")
                if isinstance(theme_input_patch.get("char_count"), int)
                else None,
            )
            if new_ti.kind in ("pdf", "text"):
                from datetime import UTC, datetime

                new_ti = new_ti.model_copy(update={"uploaded_at": datetime.now(UTC)})
            update["theme_input"] = new_ti
        apply_settings(code, settings.model_copy(update=update))

    if theme_payload is not None:
        if not isinstance(theme_payload, dict):
            return JSONResponse({"error": "theme_payload must be an object"}, status_code=400)
        theme_path = OUTPUT_ROOT / "sets" / code / "theme.json"
        theme_path.parent.mkdir(parents=True, exist_ok=True)
        theme_path.write_text(
            json.dumps(theme_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # 2. Cascade-clear pipeline artifacts + reset stages to PENDING.
    if state is not None:
        _apply_cascade_clear(code, state, start_idx)

    # 3. theme.json wipe (Project Settings → theme_input change).
    if clear_theme_json:
        theme_path = OUTPUT_ROOT / "sets" / code / "theme.json"
        if theme_path.exists():
            try:
                theme_path.unlink()
            except OSError as e:
                logger.warning("Failed to delete %s: %s", theme_path, e)

    # 4. Decide where to navigate / whether to re-kick the engine.
    theme_path = OUTPUT_ROOT / "sets" / code / "theme.json"
    if not theme_path.exists():
        # No theme means there's nothing for the engine to start from —
        # send the user back to Project Settings to choose an input + Start.
        return JSONResponse(
            {
                "success": True,
                "navigate_to": "/pipeline/project",
                "next_stage_id": None,
                "engine_started": False,
            }
        )

    # Theme.json exists; re-kick the engine for the cleared cascade.
    new_state, kickoff_err = _kickoff_pipeline_engine(code)
    if kickoff_err is not None or new_state is None:
        # Engine refused (state-level race, or kickoff path unavailable).
        # Surface to the client so the wizard reloads and the user can
        # retry — the cascade clear has already happened, so retrying
        # advance from the wizard footer is safe.
        return JSONResponse(
            {
                "success": True,
                "engine_started": False,
                "next_stage_id": None,
                "navigate_to": "/pipeline",
                "warning": kickoff_err or "Engine kickoff skipped",
            }
        )
    next_id = _first_pending_stage_id(new_state)
    return JSONResponse(
        {
            "success": True,
            "engine_started": True,
            "next_stage_id": next_id,
            "navigate_to": f"/pipeline/{next_id}" if next_id else "/pipeline",
        }
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
