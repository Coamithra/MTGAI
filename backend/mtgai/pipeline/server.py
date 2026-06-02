"""Pipeline API server — FastAPI routes for pipeline orchestration.

Provides endpoints for starting, monitoring, pausing, and resuming
the unified pipeline, plus SSE for real-time progress streaming.
Mounted as a sub-router on the existing review server.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates

from mtgai.io.asset_paths import NoAssetFolderError, set_artifact_dir
from mtgai.io.atomic import atomic_write_text
from mtgai.pipeline.engine import PipelineEngine, load_state, save_state
from mtgai.pipeline.events import EventBus, StageEmitter, format_sse
from mtgai.pipeline.models import (
    STAGE_DEFINITIONS,
    PipelineConfig,
    PipelineState,
    PipelineStatus,
    StageReviewMode,
    StageStatus,
    create_pipeline_state,
)
from mtgai.pipeline.stage_hooks import (
    build_card_gen_hooks,
    build_mechanic_hooks,
    build_skeleton_hooks,
    card_tile_dict,
    emit_card_gen_reset,
    emit_skeleton_done,
    slots_by_id_from_skeleton,
)
from mtgai.pipeline.wizard import build_wizard_state
from mtgai.pipeline.wizard import serialize as serialize_wizard_state
from mtgai.runtime import active_project, ai_lock, extraction_run
from mtgai.runtime.runtime_state import compute_runtime_state

if TYPE_CHECKING:
    from mtgai.skeleton.knobs import SkeletonKnobs

logger = logging.getLogger(__name__)


def _theme_path() -> Path:
    """Resolve the active project's ``theme.json``.

    Propagates :class:`NoAssetFolderError` from :func:`set_artifact_dir`
    when no project is open; callers translate that into a 409.
    """
    return set_artifact_dir() / "theme.json"


def _no_asset_folder_response(exc: NoAssetFolderError) -> JSONResponse:
    """Standard 409 payload for a missing ``asset_folder``.

    Mirrors the shape of the AI-busy 409 (``error`` plus a stable
    machine-readable ``code``) so the wizard client can spot it and
    bounce the user to Project Settings without parsing strings.
    """
    return JSONResponse(
        {"error": str(exc), "code": "no_asset_folder"},
        status_code=409,
    )


def _no_active_project_response() -> JSONResponse:
    """Standard 409 payload for "no project is open".

    Wizard endpoints call :func:`_require_active_project` and return
    this response when the in-memory pointer is ``None`` — the same
    posture the asset-folder 409 uses, so the client can surface a
    consistent "open or create a project" prompt.
    """
    return JSONResponse(
        {"error": "No project is open", "code": "no_active_project"},
        status_code=409,
    )


def _busy_response() -> JSONResponse:
    """The one source of the "another AI action holds the lock" 409.

    ``ai_lock.busy_payload()`` at status 409 — the shape the wizard client
    renders as the shared "AI is busy" toast. Emitted by :func:`guarded_ai`
    (the acquiring endpoints), the bare ``is_running()`` gates (theme section
    refresh / kickoff, which don't hold the lock at the check), and
    :func:`_project_switch_guard`, so every busy 409 the server returns is
    byte-identical.
    """
    return JSONResponse(ai_lock.busy_payload(), status_code=409)


def _reject_if_busy() -> JSONResponse | None:
    """Return the 409 busy response if an AI action is in flight, else ``None``.

    For the gate-only endpoints that check the lock is *free* before kicking off
    work the worker acquires itself later — they can't use :func:`guarded_ai`
    (which holds the lock). ``None`` means "clear to proceed".
    """
    return _busy_response() if ai_lock.is_running() else None


class AIActionError(Exception):
    """A guarded AI worker raised — rendered as ``500 {"error": <msg>}``.

    :func:`guarded_ai` wraps any exception escaping its body in this so the
    registered handler emits the flat ``{"error": ...}`` envelope the wizard
    client reads (``W.reportError`` keys on ``data.error``) instead of FastAPI's
    default ``{"detail": ...}`` 500. The message is the original ``str(exc)``;
    an endpoint that wants its own 500 (e.g. "LLM returned nothing usable")
    raises this directly and no success-heal fires.
    """


class _AIGuard:
    """Handle yielded by :func:`guarded_ai` — see it for the full lifecycle.

    ``busy`` is True when the lock was already held: the endpoint must return
    ``busy_response`` immediately and do no work. ``skip_heal`` lets an endpoint
    suppress the success-heal after its worker reports a *cancelled* run (the
    card-gen contract — a user cancel isn't a recovery).
    """

    __slots__ = ("run_id", "skip_heal")

    def __init__(self, run_id: int | None) -> None:
        self.run_id = run_id
        self.skip_heal = False

    @property
    def busy(self) -> bool:
        return self.run_id is None

    @property
    def busy_response(self) -> JSONResponse:
        return _busy_response()


@contextmanager
def guarded_ai(label: str, *, stage_id: str | None = None, heal: bool = True):
    """Own the AI-tab action lifecycle for a wizard endpoint body.

    The single collapse of the ``ai_lock.hold → 409`` + ``try: <work> except:
    500 {"error": str}`` + ``_heal_failed_stage`` boilerplate every refresh /
    re-pick / regenerate endpoint repeated. Usage::

        with guarded_ai("Land generation", stage_id="lands") as guard:
            if guard.busy:
                return guard.busy_response
            await asyncio.to_thread(generate_lands)
        return await wizard_lands_state()

    Lifecycle:

    * **Acquire / busy.** Tries the AI lock. If busy, yields a guard with
      ``busy is True`` and never touches the lock — the caller returns
      ``guard.busy_response`` (the 409) and does nothing else.
    * **Run.** Validation / project + asset resolution belong *before* the block,
      so a no-project / no-asset / malformed-body request 409s/400s without
      grabbing the lock.
    * **Error → 500.** Any exception escaping the block is logged and re-raised as
      :class:`AIActionError`, rendered ``500 {"error": str(exc)}`` by the handler.
      Do NOT ``return`` an error ``JSONResponse`` from inside the block — that is a
      *clean* exit, so the heal would wrongly fire; ``raise AIActionError`` instead.
    * **Heal.** On a clean exit ``_heal_failed_stage(stage_id)`` runs — unless
      ``heal`` is False or the endpoint set ``guard.skip_heal`` (the single opt-out,
      e.g. after a worker reports a *cancelled* run, since a cancel is not a
      recovery). The guard does NOT itself inspect ``ai_lock.is_cancelled()``: an
      endpoint that healed unconditionally before keeps doing so unless it opts out.
    * **Release** always happens on exit.

    Strictly NOT reentrant (the AI lock isn't): never nest ``guarded_ai`` inside
    another held one — the inner acquire sees busy and silently skips its work.
    """
    run_id = ai_lock.try_acquire(label)
    guard = _AIGuard(run_id)
    if run_id is None:
        yield guard  # busy — caller returns guard.busy_response; nothing acquired
        return
    try:
        yield guard
    except AIActionError:
        raise  # already shaped; failure, so no heal
    except Exception as exc:
        logger.exception("Guarded AI action failed: %s", label)
        raise AIActionError(str(exc)) from exc
    else:
        # Wrapped so a heal failure can't turn the success response into a
        # non-enveloped 500 (the else/finally run outside the except above).
        if heal and stage_id and not guard.skip_heal:
            try:
                _heal_failed_stage(stage_id)
            except Exception:
                logger.exception("Post-action heal failed for stage %s", stage_id)
    finally:
        ai_lock.release()


class _NoActiveProjectError(Exception):
    """Sentinel raised by :func:`_require_active_project` when no project is open.

    Endpoints catch this and return :func:`_no_active_project_response`. Using
    an exception (instead of a tuple-unpack pattern) keeps the happy path
    linear so the type checker can narrow ``project`` for the rest of the
    handler without a redundant ``project is None`` guard.
    """


def _require_active_project() -> active_project.ProjectState:
    """Return the active project; raise :class:`_NoActiveProjectError` if none is open."""
    project = active_project.read_active_project()
    if project is None:
        raise _NoActiveProjectError
    return project


def read_theme_or_none() -> Any:
    """Return the active project's parsed ``theme.json``, or ``None`` if unavailable.

    Names the "swallow :class:`NoAssetFolderError` → None" intent shared by the
    mechanics / archetypes / skeleton ``state`` endpoints: no project open (or no
    asset folder picked yet) isn't an error for first-paint state — the tab just
    renders without the theme excerpt.
    """
    try:
        return _read_json(_theme_path(), None)
    except NoAssetFolderError:
        return None


def register_exception_handlers(app: FastAPI) -> None:
    """Register the wizard's 409 guard handlers on the FastAPI ``app``.

    Endpoints let :class:`_NoActiveProjectError` / :class:`NoAssetFolderError`
    propagate instead of each wrapping the guard in a ``try/except`` — these
    handlers centralize the translation, so the duplicated guard prologue
    collapses to a single inline ``_require_active_project()`` /
    ``set_artifact_dir()`` call. The flat ``{error, code}`` payload (which the
    wizard client + tests rely on) is preserved; a bare ``HTTPException`` would
    nest it under ``detail``.
    """

    @app.exception_handler(_NoActiveProjectError)
    async def _handle_no_active_project(
        request: Request, exc: _NoActiveProjectError
    ) -> JSONResponse:
        return _no_active_project_response()

    @app.exception_handler(NoAssetFolderError)
    async def _handle_no_asset_folder(request: Request, exc: NoAssetFolderError) -> JSONResponse:
        return _no_asset_folder_response(exc)

    @app.exception_handler(AIActionError)
    async def _handle_ai_action_error(request: Request, exc: AIActionError) -> JSONResponse:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# Singleton state
# ---------------------------------------------------------------------------

event_bus = EventBus()
_engine: PipelineEngine | None = None
_engine_task: asyncio.Task | None = None


def _refresh_emitter(stage_id: str) -> StageEmitter:
    """A :class:`StageEmitter` for the manual-refresh path so it shares the
    engine's stream-hook builders (``stage_hooks``) and emits byte-identical
    SSE payloads. ``started_at=0.0`` → phase ticks report elapsed 0; the refresh
    path drives the progress strip its own way (showBusy / stage_phase), so the
    elapsed field is unused there."""
    return StageEmitter(event_bus, stage_id, 0.0)


@contextmanager
def _bus_poller(
    stage_id: str,
    *,
    activity_prefix: str = "",
    phase_kind: str = "running",
    emit_done: bool = True,
):
    """Wrap a synchronous local-LLM tab-refresh call so the progress strip shows
    live prompt-eval heartbeat / generation tok/s, then tears down cleanly.

    The refresh endpoints today paint the strip with an indeterminate
    ``showBusy()`` bar (no rate). This upgrades them to the same live telemetry
    the engine stages emit: it spins a :class:`PromptEvalPoller` for the stage's
    model and routes its ticks through the shared ``event_bus`` (the same strip),
    stamping a real ticking ``elapsed_s`` so the client clock advances. No-op for
    a cloud model (``make_poller`` → ``NullPoller``) — those keep the showBusy bar.

    On exit a terminal ``phase: "done"`` fires (only when a live poller ran) so
    the *last* SSE event hides the strip even if a trailing generation tick races
    the client's ``clearBusy()``. Pass ``emit_done=False`` when this is not the
    last poller of the endpoint (the first of two sequential spans, whose "done"
    would blink the strip off; or a path that emits its own terminal "done") so
    exactly one "done" closes the strip.
    """
    import time as _t

    from mtgai.generation.phase_poller import PromptEvalPoller, make_poller

    t0 = _t.monotonic()

    def _emit(phase: str, activity: str, **extra: Any) -> None:
        extra.setdefault("elapsed_s", round(_t.monotonic() - t0, 2))
        event_bus.stage_phase(stage_id, phase, activity, **extra)

    poller = make_poller(stage_id, _emit, activity_prefix=activity_prefix, phase_kind=phase_kind)
    live = isinstance(poller, PromptEvalPoller)
    try:
        with poller:
            yield
    finally:
        if live and emit_done:
            event_bus.stage_phase(stage_id, "done", "")


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

    With no project loaded the only visible tab is Project Settings —
    requests for any other fragment redirect there. Once a project is
    open, normal tab routing resumes (see :func:`build_wizard_state`).
    """
    ws = build_wizard_state(requested_tab=requested_tab)
    if requested_tab is not None and ws.active_tab_id != requested_tab:
        return RedirectResponse(
            url=f"/pipeline/{ws.active_tab_id}",
            status_code=302,
        )
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

    With no project loaded the redirect always lands on Project Settings;
    once one is open it follows the same latest-tab logic as before.
    """
    ws = build_wizard_state(requested_tab=None)
    return RedirectResponse(url=f"/pipeline/{ws.latest_tab_id}", status_code=302)


@router.get("/pipeline/configure")
async def pipeline_configure() -> RedirectResponse:
    """Legacy route — redirect into the wizard, theme-aware (single hop).

    The standalone configure page was subsumed by the wizard. Resolves to the
    latest visible tab — Project Settings when no ``theme.json`` exists (where
    a theme is authored before the pipeline can run), else the theme/stage
    surface the user left off on — matching ``/pipeline`` but without the extra
    redirect hop.
    """
    ws = build_wizard_state(requested_tab=None)
    return RedirectResponse(url=f"/pipeline/{ws.latest_tab_id}", status_code=302)


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
async def runtime_state() -> JSONResponse:
    """Aggregate runtime snapshot used by every page on mount.

    Returns active set code, AI-lock payload, in-flight runs (theme
    extraction etc.), pipeline summary if one exists, and the saved
    theme.json for the active set. Pages hydrate from this so tab
    switches and reloads pick up server-side state without losing
    track of in-flight AI work.

    Reads the active project from in-memory state — no query params.
    With no project open the active_set / pipeline / theme slices are
    all ``None``.
    """
    return JSONResponse(compute_runtime_state())


# ---------------------------------------------------------------------------
# Theme API routes
# ---------------------------------------------------------------------------


@api_router.post("/theme/save")
async def save_theme(request: Request):
    """Save theme.json for the active project.

    The body is the assembled theme payload. Returns 409 if no project
    is open (the wizard sends the user to Project Settings to fix it).
    """
    project = _require_active_project()
    body, err = await _read_request_json(request)
    if err is not None:
        return err
    theme_path = _theme_path()

    theme_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        theme_path,
        json.dumps(body, indent=2, ensure_ascii=False),
    )
    logger.info("Theme saved to %s", theme_path)

    return JSONResponse(
        {
            "success": True,
            "path": str(theme_path),
            "set_code": project.set_code,
        }
    )


@api_router.get("/theme/load")
async def load_theme():
    """Return the saved theme.json for the active project, or 404 if absent."""
    _require_active_project()
    theme_path = _theme_path()
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

    # Mirror the extracted text to disk under the active project's
    # asset folder so reloads after a server restart still find the
    # source. The .mtg only carries an upload_id, which is meaningless
    # once the in-memory cache evaporates — without this fallback,
    # hitting Start on a reloaded project trips "Upload expired".
    try:
        asset_dir = set_artifact_dir()
        asset_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(asset_dir / "theme_source.txt", text)
    except NoAssetFolderError:
        pass  # asset_folder not picked yet — best effort
    except OSError as e:
        logger.warning("Failed to mirror theme upload to disk: %s", e)

    return JSONResponse(
        {
            "upload_id": upload_id,
            "filename": filename,
            "char_count": len(text),
            "preview": text[:500],
        }
    )


def _theme_extract_model_key() -> str:
    """Look up the configured model key for the theme_extract stage.

    Reads from the active project's settings; falls back to the
    built-in default if no project is open. Lets the analyze /
    section-refresh endpoints estimate cost before a project is set
    up, without forcing a 409.
    """
    from mtgai.settings.model_settings import DEFAULT_LLM_ASSIGNMENTS

    project = active_project.read_active_project()
    default = DEFAULT_LLM_ASSIGNMENTS.get("theme_extract", "haiku")
    if project is None:
        return default
    return project.settings.llm_assignments.get("theme_extract", default)


@api_router.post("/theme/analyze")
async def analyze_extraction_endpoint(request: Request):
    """Analyze uploaded content: count tokens, estimate cost."""
    body, err = await _read_request_json(request)
    if err is not None:
        return err
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

    # Mirror the streaming-relevant events to the global event
    # bus so the Theme tab can stream tokens into its textarea
    # in real time. Restricted set of types so we don't flood
    # subscribers with internals.
    bus_events = {
        "theme_chunk",
        "constraints",
        "card_suggestions",
        "constraints_error",
        "suggestions_error",
        "done",
        "error",
        "cancelled",
        "status",
    }

    def _bus_mirror(event: dict) -> None:
        etype = event.get("type")
        if etype in bus_events:
            with suppress(Exception):
                event_bus.publish(f"theme_{etype}", event)

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
            # Also publish to the global event bus so the wizard's progress
            # strip (which tails /api/pipeline/events) shows the run.
            def _phase_dual_emit(event: dict) -> None:
                extraction_run.append_event(event)
                with suppress(Exception):
                    event_bus.publish("phase", event)

            set_phase_emitter(_phase_dual_emit)

            for event in stream_theme_extraction(source_text, model_key):
                etype = event.get("type")
                if etype == "theme_chunk":
                    theme_parts.append(event["text"])
                elif etype == "complete":
                    theme_cost = event.get("cost_usd", 0.0)
                extraction_run.append_event(event)
                _bus_mirror(event)
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
                    # Set when auto-advance kicked off the engine, so the
                    # watching Theme tab can open the first stage's tab (the
                    # engine runs in this worker thread with no client to
                    # navigate it).
                    navigate_to: str | None = None
                    if save_to_set:
                        _persist_extraction_to_theme_json(
                            full_theme, constraints_list, card_suggestions
                        )
                        # Auto-advance to Skeleton unless the user asked
                        # the wizard to break after Theme Generation.
                        # _resolve_break_point falls back to the
                        # DEFAULT_BREAK_POINTS table (theme_extract is on
                        # by default).
                        from mtgai.pipeline.models import _resolve_break_point

                        proj = active_project.read_active_project()
                        bps = proj.settings.break_points if proj else {}
                        if _resolve_break_point("theme_extract", bps):
                            logger.info(
                                "Theme break-point set; pausing for review on %s",
                                save_to_set,
                            )
                        else:
                            kicked, kickoff_err = _kickoff_pipeline_engine(save_to_set)
                            if kickoff_err is not None or kicked is None:
                                # Warning, not info: the user expected
                                # the wizard to flow into Skeleton and
                                # it didn't — surfacing this at default
                                # log levels gives the operator a chance
                                # to spot it.
                                logger.warning(
                                    "Theme to engine auto-advance skipped for %s: %s",
                                    save_to_set,
                                    kickoff_err,
                                )
                            else:
                                next_id = _first_pending_stage_id(kicked)
                                if next_id:
                                    navigate_to = f"/pipeline/{next_id}"
                    done_event: dict[str, Any] = {
                        "type": "done",
                        "total_cost_usd": round(total_cost, 4),
                    }
                    if navigate_to:
                        done_event["navigate_to"] = navigate_to
                    extraction_run.append_event(done_event)
                    _bus_mirror(done_event)
                    continue
                extraction_run.append_event(event)
                _bus_mirror(event)
        except Exception as e:
            logger.error("Theme extraction stream failed: %s", e, exc_info=True)
            err_event = {"type": "error", "message": str(e)}
            extraction_run.append_event(err_event)
            _bus_mirror(err_event)
        finally:
            clear_phase_emitter()
            run = extraction_run.current()
            status = _terminal_status(run.events) if run is not None else "error"
            extraction_run.mark_done(status)
            _upload_cache.pop(upload_id, None)

    threading.Thread(target=worker, daemon=True).start()


def _persist_extraction_to_theme_json(
    setting_text: str,
    constraints: list[str],
    card_suggestions: list[dict[str, str]],
) -> None:
    """Write the assembled extraction result to ``theme.json``.

    Called from the wizard "Start project" worker once both extraction
    passes finish. Reads the active project for ``set_code`` + settings;
    existing keys (``code``, ``name``) are preserved so the set picker
    keeps showing the right title.

    Card suggestions arrive as ``{name, description}`` from the LLM
    JSON pass; the Theme tab UI expects ``{text, source}`` items so we
    flatten ``"<name> — <description>"`` here. ``source: "ai"`` is the
    AI-generated badge the wizard renders next to each item.
    """
    project = active_project.require_active_project()
    set_code = project.set_code
    settings = project.settings

    theme_path = set_artifact_dir() / "theme.json"
    existing: dict[str, Any] = {}
    if theme_path.exists():
        try:
            existing = json.loads(theme_path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = {}
        except (OSError, json.JSONDecodeError):
            existing = {}

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
    atomic_write_text(
        theme_path,
        json.dumps(payload, indent=2, ensure_ascii=False),
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
            return _busy_response()
        else:
            cached = _upload_cache.get(upload_id)
            text = cached["text"] if cached else None
            if text is None:
                # Cache miss — fall back to the on-disk mirror written by
                # the upload handler so reload+refresh still works.
                try:
                    mirror = set_artifact_dir() / "theme_source.txt"
                    if mirror.exists():
                        text = mirror.read_text(encoding="utf-8")
                except NoAssetFolderError:
                    text = None
            if text is None:
                return JSONResponse({"error": "Upload expired"}, status_code=404)
            if not model_key:
                model_key = _theme_extract_model_key()
            extraction_run.start_run(upload_id)
            try:
                save_to = active_project.read_active_project()
                save_to_set = save_to.set_code if save_to else None
            except Exception:
                save_to_set = None
            _start_extraction_worker(upload_id, text, model_key, save_to_set=save_to_set)
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
    done_sentinel = object()

    def push_event(event: dict) -> None:
        q.put(event)
        # Mirror to the global event bus so the wizard's progress strip
        # tracks section refreshes the same way it tracks full extractions.
        with suppress(Exception):
            event_bus.publish("phase", event)

    def worker() -> None:
        try:
            set_phase_emitter(push_event)
            for event in stream_section_extraction(theme_text, model_key, kind):
                q.put(event)
                # Section results (constraints / card_suggestions /
                # constraints_error / suggestions_error / done) also
                # broadcast on event_bus so the Theme tab can apply
                # them without a separate stream subscription.
                etype = event.get("type")
                if etype in (
                    "constraints",
                    "card_suggestions",
                    "constraints_error",
                    "suggestions_error",
                    "done",
                ):
                    with suppress(Exception):
                        event_bus.publish(f"section_{etype}", event)
        except Exception as e:
            logger.error("Section refresh (%s) failed: %s", kind, e, exc_info=True)
            q.put({"type": "error", "message": str(e)})
            with suppress(Exception):
                event_bus.publish("section_done", {"type": "done"})
        finally:
            clear_phase_emitter()
            q.put(done_sentinel)

    threading.Thread(target=worker, name=f"section-refresh-{kind}", daemon=True).start()
    return q, done_sentinel


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
    body, err = await _read_request_json(request)
    if err is not None:
        return err
    theme_text = body.get("theme_text", "")
    kind = body.get("kind", "constraints")
    model_key = body.get("model_key") or _theme_extract_model_key()

    if not theme_text.strip():
        return JSONResponse({"error": "No theme text provided"}, status_code=400)
    if kind not in ("constraints", "card_suggestions"):
        return JSONResponse({"error": f"Unknown kind: {kind}"}, status_code=400)

    if (resp := _reject_if_busy()) is not None:
        return resp

    q, done_sentinel = _stream_section_refresh(theme_text, kind, model_key)

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
                if event is done_sentinel:
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
    from mtgai.pipeline.models import STAGE_DEFINITIONS, _resolve_break_point, break_point_states
    from mtgai.settings.model_settings import STRUCTURAL_BREAK_POINTS

    review_by_stage = break_point_states(settings_obj.break_points)
    # Theme extraction isn't a pipeline stage (it runs before the engine
    # kicks off), but the user can still ask the wizard to pause after
    # it for review. Surface it as the first row.
    rows: list[dict[str, Any]] = [
        {
            "stage_id": "theme_extract",
            "display_name": "Theme Generation",
            "review": _resolve_break_point("theme_extract", settings_obj.break_points),
            "structural": "theme_extract" in STRUCTURAL_BREAK_POINTS,
        }
    ]
    rows.extend(
        {
            "stage_id": defn["stage_id"],
            "display_name": defn["display_name"],
            "review": review_by_stage[defn["stage_id"]],
            "structural": defn["stage_id"] in STRUCTURAL_BREAK_POINTS,
        }
        for defn in STAGE_DEFINITIONS
    )
    return rows


def _project_payload(project: active_project.ProjectState) -> dict[str, Any]:
    """Bundle everything the Project Settings tab needs on first paint."""
    from mtgai.settings.model_registry import get_registry
    from mtgai.settings.model_settings import (
        PRESETS,
        list_profiles,
    )

    set_code = project.set_code
    settings = project.settings
    registry = get_registry()
    try:
        pipeline_started = (set_artifact_dir() / "pipeline-state.json").exists()
    except NoAssetFolderError:
        # No asset folder yet — the user hasn't picked one. The Project
        # Settings tab is exactly where they fix that, so render the
        # form with ``pipeline_started=False`` instead of bouncing off
        # a 409.
        pipeline_started = False
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
            "effort_levels": list(m.effort_levels),
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
        "asset_folder": settings.asset_folder,
        "break_points": _break_points_payload(settings),
        "llm_assignments": dict(settings.llm_assignments),
        "image_assignments": dict(settings.image_assignments),
        "effort_overrides": dict(settings.effort_overrides),
        "debug": settings.debug.model_dump(),
        "llm_models": llm_models,
        "image_models": image_models,
        "builtin_presets": sorted(PRESETS),
        "saved_profiles": list_profiles(),
        "pipeline_started": pipeline_started,
        "extraction_active": extraction_active,
    }


@router.get("/api/wizard/project")
async def wizard_project_payload() -> JSONResponse:
    """Bundle the Project Settings tab's first-paint state.

    Reads the active project from in-memory state — no query params.
    Returns 409 ``no_active_project`` when nothing is open so the
    client can prompt the user to New / Open.
    """
    project = _require_active_project()
    return JSONResponse(_project_payload(project))


@router.post("/api/wizard/project/set-code")
async def wizard_project_save_set_code(request: Request) -> JSONResponse:
    """Live-apply set_code (cosmetic label printed on the card frame).

    set_code is a top-level ProjectState field, not inside set_params,
    so it gets its own tiny endpoint instead of riding /params. Empty
    is allowed (the label is purely cosmetic).
    """
    project = _require_active_project()
    body, err = await _read_request_json(request)
    if err is not None:
        return err
    raw = body.get("set_code", "")
    if not isinstance(raw, str):
        return JSONResponse({"error": "set_code must be a string"}, status_code=400)
    code = raw.strip()
    active_project.write_active_project(project.model_copy(update={"set_code": code}))
    return JSONResponse({"success": True, "set_code": code})


@router.post("/api/wizard/project/params")
async def wizard_project_save_params(request: Request) -> JSONResponse:
    """Live-apply set_name / mechanic_count; gate set_size post-Start.

    set_name + mechanic_count flow through immediately — they don't
    invalidate any downstream artifact. set_size flips the skeleton's
    target so editing it once a pipeline-state.json exists requires the
    cascade-clear edit flow (§9 card). Until that ships the field is
    read-only post-Start; this endpoint rejects the change with 409.
    """
    from mtgai.settings.model_settings import SetParams, apply_settings

    project = _require_active_project()
    settings = project.settings
    body, err = await _read_request_json(request)
    if err is not None:
        return err

    current = settings.set_params
    name = body.get("set_name", current.set_name)
    mech = body.get("mechanic_count", current.mechanic_count)
    size = body.get("set_size", current.set_size)

    if not isinstance(name, str):
        return JSONResponse({"error": "set_name must be a string"}, status_code=400)
    if not isinstance(mech, int) or mech < 0:
        return JSONResponse({"error": "mechanic_count must be a non-negative int"}, status_code=400)
    # Mechanic generation produces a candidate pool of twice ``mechanic_count``
    # and the user picks ``mechanic_count`` of it, so the pool always satisfies
    # the save-and-continue gate. We still cap the count itself so an absurd
    # value (e.g. 20) can't trigger a runaway 40-candidate generation.
    from mtgai.generation.mechanic_generator import MAX_MECHANIC_COUNT

    if mech > MAX_MECHANIC_COUNT:
        return JSONResponse(
            {
                "error": (
                    f"mechanic_count cannot exceed {MAX_MECHANIC_COUNT} "
                    f"(maximum mechanics per set); got {mech}"
                )
            },
            status_code=400,
        )
    if not isinstance(size, int) or size <= 0:
        return JSONResponse({"error": "set_size must be a positive int"}, status_code=400)

    try:
        pipeline_started = (set_artifact_dir() / "pipeline-state.json").exists()
    except NoAssetFolderError:
        # Editing params before the user has picked an asset folder is
        # always allowed — the cascade-clear gate is moot because no
        # downstream artifacts can exist yet.
        pipeline_started = False
    if pipeline_started and size != current.set_size:
        return JSONResponse(
            {
                "error": (
                    "Target size is a cascade-clear field after the pipeline has started. "
                    "Click Edit on the Set parameters section and Accept to apply."
                ),
            },
            status_code=409,
        )

    new = settings.model_copy(
        update={"set_params": SetParams(set_name=name, set_size=size, mechanic_count=mech)}
    )
    apply_settings(new)
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
    from mtgai.settings.model_settings import ThemeInputSource, apply_settings

    project = _require_active_project()
    settings = project.settings
    body, err = await _read_request_json(request)
    if err is not None:
        return err

    kind = body.get("kind")
    if kind not in ("none", "pdf", "text", "existing"):
        return JSONResponse({"error": "Invalid theme-input kind"}, status_code=400)
    try:
        pipeline_started = (set_artifact_dir() / "pipeline-state.json").exists()
    except NoAssetFolderError:
        # No asset folder yet → no downstream artifacts to invalidate.
        pipeline_started = False
    if pipeline_started and settings.theme_input.kind != kind:
        return JSONResponse(
            {
                "error": (
                    "Theme input is a cascade-clear field after the pipeline has started. "
                    "Click Edit on the Set parameters section and Accept to apply."
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
    apply_settings(new)
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
    from mtgai.settings.model_settings import apply_settings

    project = _require_active_project()
    settings = project.settings
    body, err = await _read_request_json(request)
    if err is not None:
        return err

    stage_id = body.get("stage_id")
    review = body.get("review")
    if not isinstance(stage_id, str) or not isinstance(review, bool):
        return JSONResponse({"error": "stage_id (str) and review (bool) required"}, status_code=400)

    # theme_extract is a virtual row in the break-points list (theme
    # extraction runs before the engine kicks off, so it's not in
    # STAGE_DEFINITIONS) — accept it explicitly.
    if stage_id != "theme_extract":
        defn = next((d for d in STAGE_DEFINITIONS if d["stage_id"] == stage_id), None)
        if defn is None:
            return JSONResponse({"error": f"Unknown stage_id {stage_id!r}"}, status_code=400)

    from mtgai.settings.model_settings import (
        DEFAULT_BREAK_POINTS,
        STRUCTURAL_BREAK_POINTS,
    )

    # Structural break-points (e.g. ``mechanics``) cannot be unset —
    # their wizard tab is the only producer of the stage's output.
    if not review and stage_id in STRUCTURAL_BREAK_POINTS:
        return JSONResponse(
            {
                "error": (
                    f"The {stage_id!r} pause is structural — the wizard tab "
                    "is the only path that produces the stage's output. "
                    "Cancel the pipeline and re-kick instead."
                )
            },
            status_code=400,
        )

    breaks = dict(settings.break_points)
    if review:
        # If the default already says "review", we don't need to write anything;
        # only persist when the user's choice diverges from the default.
        if DEFAULT_BREAK_POINTS.get(stage_id) == "review":
            breaks.pop(stage_id, None)
        else:
            breaks[stage_id] = "review"
    else:
        # Same logic mirrored: store "auto" only when overriding a "review" default.
        if DEFAULT_BREAK_POINTS.get(stage_id) == "review":
            breaks[stage_id] = "auto"
        else:
            breaks.pop(stage_id, None)

    new = settings.model_copy(update={"break_points": breaks})
    apply_settings(new)
    return JSONResponse({"success": True, "break_points": breaks})


@router.post("/api/wizard/project/models")
async def wizard_project_save_model(request: Request) -> JSONResponse:
    """Live-apply a single model assignment (or effort override).

    Body: ``{set_code, kind: "llm" | "image" | "effort", stage_id, value}``.
    The wizard's dropdowns POST one of these per change so we don't have
    to round-trip the entire ``ModelSettings`` shape on every keystroke.
    """
    from mtgai.settings.model_settings import apply_settings

    project = _require_active_project()
    settings = project.settings
    body, err = await _read_request_json(request)
    if err is not None:
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

    apply_settings(new)
    return JSONResponse({"success": True})


@router.post("/api/wizard/project/preset/apply")
async def wizard_project_apply_preset(request: Request) -> JSONResponse:
    """Apply a built-in preset or saved profile to this set's settings.

    Per §6.8 / §6.4, model assignments and break points come from the
    preset; per-set values (set_params, theme_input) are NOT touched.
    Live-apply — no cascade clear — because model swaps don't
    invalidate already-generated artifacts.
    """
    from mtgai.settings.model_settings import ModelSettings, apply_settings

    project = _require_active_project()
    current = project.settings
    body, err = await _read_request_json(request)
    if err is not None:
        return err
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        return JSONResponse({"error": "Preset name required"}, status_code=400)

    try:
        preset = ModelSettings.from_preset(name.strip())
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    merged = current.model_copy(
        update={
            "llm_assignments": dict(preset.llm_assignments),
            "image_assignments": dict(preset.image_assignments),
            "effort_overrides": dict(preset.effort_overrides),
            "break_points": dict(preset.break_points),
        }
    )
    apply_settings(merged)
    return JSONResponse({"success": True})


@router.post("/api/wizard/project/preset/save")
async def wizard_project_save_preset(request: Request) -> JSONResponse:
    """Save the active project's model assignments + break points as a profile."""
    project = _require_active_project()
    settings = project.settings
    body, err = await _read_request_json(request)
    if err is not None:
        return err
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        return JSONResponse({"error": "Profile name required"}, status_code=400)

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
    project = _require_active_project()
    settings = project.settings

    if not settings.asset_folder:
        return _no_asset_folder_response(
            NoAssetFolderError("Asset folder required — pick one on the Project Settings tab"),
        )
    kind = settings.theme_input.kind
    if kind == "none":
        return JSONResponse(
            {"error": "Choose a theme input before starting"},
            status_code=400,
        )

    try:
        body = await request.json()
    except Exception:
        body = {}
    force = bool(body.get("force") if isinstance(body, dict) else False)

    if kind == "existing" and not force:
        # Theme.json already on disk — Project Settings is done; the
        # wizard transitions to Theme without spawning an extraction.
        return JSONResponse(
            {"success": True, "extraction_started": False, "navigate_to": "/pipeline/theme"}
        )

    # If theme.json already exists for this asset folder, treat it as
    # "existing" too — the user re-loaded a project that's been through
    # extraction before, so re-running it would discard their reviewed
    # theme. force=true (Refresh-AI from the Theme tab) bypasses this.
    if not force:
        try:
            if (set_artifact_dir() / "theme.json").exists():
                return JSONResponse(
                    {
                        "success": True,
                        "extraction_started": False,
                        "navigate_to": "/pipeline/theme",
                    }
                )
        except NoAssetFolderError:
            pass

    upload_id = settings.theme_input.upload_id
    if not upload_id:
        return JSONResponse(
            {"error": "Theme input is missing upload_id — re-upload the file"},
            status_code=400,
        )

    cached = _upload_cache.get(upload_id)
    text = cached["text"] if cached else None
    if text is None:
        # Cache miss (server restart or TTL eviction). Fall back to the
        # mirrored copy under the asset folder, which the upload handler
        # writes alongside the in-memory entry.
        try:
            mirror = set_artifact_dir() / "theme_source.txt"
            if mirror.exists():
                text = mirror.read_text(encoding="utf-8")
        except NoAssetFolderError:
            text = None
    if text is None:
        return JSONResponse(
            {"error": "Upload expired — please re-upload the file"},
            status_code=410,
        )

    # The fresh-start race in /theme/extract-stream is guarded by an
    # extra module-level lock; the kickoff path can't collide with that
    # because it acquires the AI lock atomically below before starting
    # the worker, and the new worker is the only writer to
    # extraction_run._run after we call start_run().
    if (resp := _reject_if_busy()) is not None:
        return resp

    model_key = settings.llm_assignments.get("theme_extract", "haiku")
    extraction_run.start_run(upload_id)
    _start_extraction_worker(upload_id, text, model_key, save_to_set=project.set_code)
    return JSONResponse(
        {
            "success": True,
            "extraction_started": True,
            "navigate_to": "/pipeline/theme",
            "upload_id": upload_id,
        }
    )


# ---------------------------------------------------------------------------
# .mtg project file — New / Open / Save / Save-as
# ---------------------------------------------------------------------------
#
# A .mtg file is the user's only persistent project artifact: a TOML
# document with ``set_code`` + ``mtg_file_version`` headers wrapping the
# settings body. The browser reads + writes it through the File System
# Access API. ``open`` and ``materialize`` parse the body and pin the
# resulting :class:`ProjectState` as the active project (no on-disk
# settings store); ``serialize`` re-emits the active project's TOML so
# the browser can write it back.


async def _project_switch_guard(body: object) -> JSONResponse | None:
    """Drain in-flight AI work before swapping the active-project pointer.

    Switching projects mid-run would orphan a background AI task against
    a project no longer "open". The guard surfaces a 409 with the busy
    payload so the client can render a confirmation modal naming what
    it would interrupt; on retry with ``force=true`` we signal cancel
    and wait for the lock to drain. On drain timeout we still proceed
    (the cancel signal has been sent and the run will wind down) — the
    user shouldn't be blocked indefinitely on a stuck loop.

    ``body`` is whatever the request JSON deserialised to — if it isn't
    a dict (a list, scalar, or null), we treat ``force`` as absent so
    the busy path still 409s cleanly instead of crashing on
    ``.get("force")``.

    Returns None when it's safe to proceed; returns the JSONResponse to
    return otherwise.
    """
    if not ai_lock.is_running():
        return None
    force = isinstance(body, dict) and body.get("force") is True
    if not force:
        return _busy_response()
    ai_lock.request_cancel()
    if not await active_project.await_lock_release_async():
        logger.warning(
            "AI lock did not release within deadline after cancel; "
            "proceeding with project switch anyway"
        )
    return None


@router.post("/api/project/new")
async def project_new(request: Request) -> JSONResponse:
    """Forget the current active project; return a blank-form payload.

    Clears the in-memory active-project pointer and returns a
    blank-form draft seeded from the user's default preset. The blank
    payload mirrors the shape of ``/api/wizard/project`` so the
    Project Settings tab can render an editable form against the same
    fields without a second fetch. ``set_params`` and ``theme_input``
    always start blank (per-project, not template-able).

    Body (optional): ``{"force": true}`` — required when an AI action
    is in flight. Without it, a 409 returns the busy payload so the UI
    can prompt for confirmation; with it, the in-flight action is
    cancelled before the pointer is cleared.
    """
    from mtgai.settings.model_registry import get_registry
    from mtgai.settings.model_settings import (
        DEFAULT_BREAK_POINTS,
        PRESETS,
        ModelSettings,
        get_global_settings,
        list_profiles,
    )

    try:
        body = await request.json()
    except json.JSONDecodeError:
        body = {}
    if (resp := await _project_switch_guard(body)) is not None:
        return resp
    if not isinstance(body, dict):
        body = {}

    # Seed the form from the user's default preset so they don't have
    # to re-pick model assignments every New. set_params + theme_input
    # always start blank — those are per-project, not template-able.
    glob = get_global_settings()
    try:
        seeded = ModelSettings.from_preset(glob.default_preset)
    except ValueError:
        seeded = ModelSettings()

    # Pin the seeded settings as the active project so subsequent edits
    # live-apply and survive page navigation. Without this pin, the
    # browser-side draft would be lost the moment the user opens any
    # other page (Model Registry, etc.). set_code starts empty (purely
    # cosmetic), set_params + theme_input + asset_folder are blank.
    active_project.write_active_project(active_project.ProjectState(set_code="", settings=seeded))

    registry = get_registry()
    break_points = _break_points_payload(seeded)
    return JSONResponse(
        {
            "success": True,
            "draft": {
                "set_code": "",
                "set_params": {"set_name": "", "set_size": 277, "mechanic_count": 3},
                "theme_input": {"kind": "none"},
                "asset_folder": "",
                "break_points": break_points,
                "llm_assignments": dict(seeded.llm_assignments),
                "image_assignments": dict(seeded.image_assignments),
                "effort_overrides": dict(seeded.effort_overrides),
                "debug": seeded.debug.model_dump(),
                "llm_models": [
                    {
                        "key": m.key,
                        "name": m.name,
                        "tier": m.tier,
                        "supports_effort": m.supports_effort,
                        "effort_levels": list(m.effort_levels),
                    }
                    for m in registry.list_llm()
                ],
                "image_models": [
                    {"key": m.key, "name": m.name, "implemented": m.implemented}
                    for m in registry.list_image()
                ],
                "builtin_presets": sorted(PRESETS),
                "saved_profiles": list_profiles(),
                "pipeline_started": False,
                "extraction_active": False,
                "default_breaks": dict(DEFAULT_BREAK_POINTS),
            },
        }
    )


@router.post("/api/project/open")
async def project_open(request: Request) -> JSONResponse:
    """Load a .mtg TOML body, set it as the active project.

    Body: ``{"toml": "<text>", "force": <bool>}`` — the browser reads
    the file via the File System Access API and posts the contents
    here. Server parses the body, pins the resulting
    ``ProjectState`` as the active project, and demotes any leftover
    ``RUNNING`` stage on disk so the wizard surfaces a Retry instead of
    a stuck spinner. Returns the parsed set_code so the client can
    navigate to ``/pipeline/<tab>``. ``force=true`` is required when an
    AI action is in flight; without it, a 409 returns the busy payload
    so the UI can prompt for confirmation.
    """
    from mtgai.pipeline.engine import cleanup_orphan_running_stages
    from mtgai.settings.model_settings import parse_project_toml

    body, err = await _read_request_json(request)
    if err is not None:
        return err
    if (resp := await _project_switch_guard(body)) is not None:
        return resp
    if not isinstance(body, dict):
        return JSONResponse({"error": "toml body required"}, status_code=400)
    text = body.get("toml")
    if not isinstance(text, str) or not text.strip():
        return JSONResponse({"error": "toml body required"}, status_code=400)
    try:
        set_code, settings = parse_project_toml(text)
    except ValueError as e:
        return JSONResponse({"error": f"Invalid .mtg file: {e}"}, status_code=400)

    active_project.write_active_project(
        active_project.ProjectState(set_code=set_code, settings=settings)
    )
    cleanup_orphan_running_stages()
    return JSONResponse({"success": True, "set_code": set_code})


@router.post("/api/project/materialize")
async def project_materialize(request: Request) -> JSONResponse:
    """Pin in-form state as the active project, return the .mtg TOML.

    Used by Save & Start when the project hasn't been written to a .mtg
    yet — the JS holds the form state in memory, posts the full payload
    here, and the server pins the resulting ``ProjectState`` as the
    active project. Returns the .mtg TOML the browser then writes via
    the File System Access API. Body shape mirrors what
    ``/api/wizard/project`` returns for a populated project (set_code,
    set_params, theme_input, asset_folder, llm_assignments,
    image_assignments, effort_overrides, break_points). ``force=true``
    is required when an AI action is in flight — defensive only, since
    materialize fires from the kickoff flow on a fresh draft, before
    any AI work has started.
    """
    from mtgai.pipeline.engine import cleanup_orphan_running_stages
    from mtgai.settings.model_settings import (
        DebugSettings,
        ModelSettings,
        SetParams,
        ThemeInputSource,
        dump_project_toml,
    )

    body, err = await _read_request_json(request)
    if err is not None:
        return err
    if (resp := await _project_switch_guard(body)) is not None:
        return resp
    if not isinstance(body, dict):
        return JSONResponse({"error": "Invalid project body"}, status_code=400)
    raw_code = body.get("set_code", "")
    if not isinstance(raw_code, str):
        return JSONResponse({"error": "set_code must be a string"}, status_code=400)
    set_code = raw_code.strip()

    try:
        settings = ModelSettings(
            llm_assignments=body.get("llm_assignments", {}) or {},
            image_assignments=body.get("image_assignments", {}) or {},
            effort_overrides=body.get("effort_overrides", {}) or {},
            break_points=body.get("break_points", {}) or {},
            set_params=SetParams(**(body.get("set_params") or {})),
            theme_input=ThemeInputSource(**(body.get("theme_input") or {})),
            debug=DebugSettings(**(body.get("debug") or {})),
            asset_folder=body.get("asset_folder", "") or "",
        )
    except Exception as e:  # pydantic validation, etc.
        return JSONResponse({"error": f"Invalid project body: {e}"}, status_code=400)

    active_project.write_active_project(
        active_project.ProjectState(set_code=set_code, settings=settings)
    )
    cleanup_orphan_running_stages()

    return JSONResponse(
        {
            "success": True,
            "set_code": set_code,
            "mtg_toml": dump_project_toml(set_code, settings),
        }
    )


@router.get("/api/project/serialize")
async def project_serialize() -> JSONResponse:
    """Return the .mtg TOML for the active project.

    Used by Save when a .mtg path already exists — the browser asks the
    server for the canonical TOML, then writes it through the existing
    file handle.
    """
    from mtgai.settings.model_settings import dump_project_toml

    project = _require_active_project()
    return JSONResponse(
        {
            "success": True,
            "set_code": project.set_code,
            "mtg_toml": dump_project_toml(project.set_code, project.settings),
        }
    )


@router.post("/api/wizard/project/pick-folder")
async def wizard_project_pick_folder() -> JSONResponse:
    """Pop a native OS folder dialog and return the picked absolute path.

    Browser-only `showDirectoryPicker` hands back a sandboxed handle with
    no real path, so we run a tkinter dialog on the local server process
    instead — only sane because the server runs on the user's machine.
    Returns ``{"path": "..."}`` on selection, ``{"path": null}`` if the
    user cancelled. Runs the dialog in a worker thread so the event
    loop isn't blocked.
    """
    import asyncio
    import tkinter as tk
    from tkinter import filedialog

    def _pick() -> str:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            return filedialog.askdirectory(parent=root, mustexist=True) or ""
        finally:
            root.destroy()

    try:
        path = await asyncio.to_thread(_pick)
    except Exception as e:
        return JSONResponse({"error": f"Folder picker failed: {e}"}, status_code=500)
    return JSONResponse({"path": path or None})


@router.post("/api/wizard/project/asset-folder")
async def wizard_project_save_asset_folder(request: Request) -> JSONResponse:
    """Live-apply asset_folder for the active project.

    Plain string field — the browser captures it from showDirectoryPicker
    (or the "use project file folder" button) and posts it here. Stage
    runners route their outputs through ``set_artifact_dir`` so the
    setting takes effect on the next stage that runs.

    Cascade-clear gate: once a ``pipeline-state.json`` exists for the
    current ``asset_folder``, swapping the folder would orphan every
    artifact already on disk. Refuse with 409 so the user goes through
    the §9 edit flow instead. Setting the folder for the first time
    (current empty) and identical writes are still allowed.
    """
    from mtgai.settings.model_settings import apply_settings

    project = _require_active_project()
    settings = project.settings
    body, err = await _read_request_json(request)
    if err is not None:
        return err
    folder = body.get("asset_folder", "")
    if not isinstance(folder, str):
        return JSONResponse({"error": "asset_folder must be a string"}, status_code=400)
    if folder != settings.asset_folder and settings.asset_folder:
        try:
            pipeline_started = (set_artifact_dir() / "pipeline-state.json").exists()
        except NoAssetFolderError:
            pipeline_started = False
        if pipeline_started:
            return JSONResponse(
                {
                    "error": (
                        "Asset folder is a cascade-clear field after the pipeline has started. "
                        "Click Edit on the Project Settings section and Accept to apply."
                    ),
                },
                status_code=409,
            )
    new = settings.model_copy(update={"asset_folder": folder})
    apply_settings(new)
    return JSONResponse({"success": True, "asset_folder": folder})


@router.post("/api/wizard/project/debug")
async def wizard_project_save_debug(request: Request) -> JSONResponse:
    """Live-apply a single debug toggle (e.g. response_cache).

    Body: ``{flag: str, value: bool}``. Per-project debug state — no
    cascade-clear gate because debug flags don't invalidate any artifact
    on disk (response caching just reroutes future calls). Unknown flag
    names 400 so a typo can't silently no-op.
    """
    from mtgai.settings.model_settings import DebugSettings, apply_settings

    project = _require_active_project()
    settings = project.settings
    body, err = await _read_request_json(request)
    if err is not None:
        return err

    flag = body.get("flag")
    value = body.get("value")
    if not isinstance(flag, str):
        return JSONResponse({"error": "flag (str) required"}, status_code=400)
    if flag not in DebugSettings.model_fields:
        return JSONResponse({"error": f"Unknown debug flag {flag!r}"}, status_code=400)
    if not isinstance(value, bool):
        return JSONResponse({"error": "value (bool) required"}, status_code=400)

    new_debug = settings.debug.model_copy(update={flag: value})
    new = settings.model_copy(update={"debug": new_debug})
    apply_settings(new)
    return JSONResponse({"success": True, "debug": new_debug.model_dump()})


# ---------------------------------------------------------------------------
# Wizard advance — auto-advance + Next-step button
# ---------------------------------------------------------------------------


def _build_pipeline_config_from_settings(set_code: str) -> PipelineConfig:
    """Build a :class:`PipelineConfig` from the per-set settings.toml.

    Wizard kickoff path uses this to translate the persisted
    ``set_params`` + ``break_points`` into the engine's input shape:
    set parameters become top-level fields; break_points (``"review"``
    / ``"auto"``) translate to ``StageReviewMode`` entries keyed by
    stage_id. Defaults from :data:`DEFAULT_BREAK_POINTS` apply when a
    stage is unset.
    """
    from mtgai.pipeline.models import _resolve_break_point

    settings = active_project.require_active_project().settings
    sp = settings.set_params
    review_modes: dict[str, StageReviewMode] = {}
    for defn in STAGE_DEFINITIONS:
        sid = defn["stage_id"]
        if _resolve_break_point(sid, settings.break_points):
            review_modes[sid] = StageReviewMode.REVIEW
    return PipelineConfig(
        set_code=set_code,
        set_name=sp.set_name or set_code,
        set_size=sp.set_size,
        stage_review_modes=review_modes,
    )


def _first_pending_stage_id(state: PipelineState) -> str | None:
    """Return the *instance id* (tab id) of the first non-completed stage.

    Walks the runtime ``state.stages`` (which may contain dynamically-inserted
    instances), so the value is the tab to navigate to — ``instance_id``, not
    the template ``stage_id`` (identical for backbone stages, differs for an
    inserted ``card_gen.2`` etc.).
    """
    for stage in state.stages:
        if stage.status not in (StageStatus.COMPLETED, StageStatus.SKIPPED):
            return stage.instance_id
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
      demote those on project open; reaching this branch means something
      raced after the open-time cleanup.
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

    existing = load_state()
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
async def wizard_advance() -> JSONResponse:
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
    project = _require_active_project()

    existing = load_state()
    if existing is None:
        # Brand-new — kick off the engine. The wizard reaches this from
        # the Theme tab's Next-step button when the user manually
        # advances after extraction (auto-advance handles the common
        # case from the worker thread).
        state, kickoff_err = _kickoff_pipeline_engine(project.set_code)
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
    # ``from_stage`` is a wizard tab id == an ``instance_id`` (the client sends
    # ``tab.id``), so match on instance_id to land on the exact instance the
    # user edited from; the cascade then clears that index onward.
    for idx, stage in enumerate(state.stages):
        if stage.instance_id == from_stage:
            return idx
    raise ValueError(f"Unknown stage id {from_stage!r}")


def _compute_cascade_preview(
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
    try:
        state = load_state()
    except NoAssetFolderError:
        state = None
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
    try:
        theme_json_present = (set_artifact_dir() / "theme.json").exists()
    except NoAssetFolderError:
        theme_json_present = False
    return {
        "cleared": cleared,
        "clear_theme_json": bool(clear_theme_json and theme_json_present),
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
    _require_active_project()
    body, err = await _read_request_json(request)
    if err is not None:
        return err
    from_stage = body.get("from_stage")
    if not isinstance(from_stage, str) or not from_stage:
        return JSONResponse({"error": "from_stage required"}, status_code=400)
    clear_theme_json = bool(body.get("clear_theme_json"))

    try:
        return JSONResponse(_compute_cascade_preview(from_stage, clear_theme_json=clear_theme_json))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


def _apply_cascade_clear(state: PipelineState, start_idx: int) -> None:
    """Run STAGE_CLEARERS for stages[start_idx:] and reset them to PENDING.

    Persists the updated pipeline-state.json in a ``finally`` block so a
    partially-applied cascade is durable even if a clearer throws
    unexpectedly. Per-stage clearers handle their own idempotency
    (missing files / dirs are fine). ``current_stage_id`` is dropped if
    it pointed at a stage in the cleared range.
    """
    from mtgai.pipeline import history
    from mtgai.pipeline.stages import clear_stage_artifacts

    try:
        for stage in state.stages[start_idx:]:
            # Drop this instance's card-pool snapshot — it describes now-discarded
            # output and would mislead per-instance viewing / tip-detection on the
            # re-run. (The dedicated /instance/rerun path restores entry snapshots;
            # the generic edit-cascade just clears + lets the engine rebuild.)
            history.delete_snapshot(stage.instance_id)
            try:
                clear_stage_artifacts(stage.stage_id)
            except (OSError, KeyError) as e:
                # OSError = filesystem I/O hiccup; KeyError = the
                # registry contract slipped (a new stage was added to
                # STAGE_DEFINITIONS without a clearer entry). Log and
                # keep going — the loop still resets the in-memory
                # status, and the persisted state reflects what we
                # could clear.
                logger.warning(
                    "Cascade clear for %s raised %s; continuing",
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

        if state.current_instance_id is not None:
            cleared_ids = {s.instance_id for s in state.stages[start_idx:]}
            if state.current_instance_id in cleared_ids:
                state.current_instance_id = None

        # After cascade, overall_status is one of:
        #   - NOT_STARTED — at least one stage left non-completed
        #     (the common case; engine kickoff picks up here)
        #   - COMPLETED   — cascade was a no-op on a fully-done pipeline
        #     (start_idx points past the end)
        if any(s.status != StageStatus.COMPLETED for s in state.stages):
            state.overall_status = PipelineStatus.NOT_STARTED
    finally:
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
    )

    project = _require_active_project()
    body, err = await _read_request_json(request)
    if err is not None:
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

    # Theme extraction runs through extraction_run on its own worker
    # thread (separate from _engine), so the engine.is_running check
    # above misses it. A mid-extraction Accept could race the worker's
    # final theme.json write against our cascade clear. Require the
    # user to cancel from the global progress strip first.
    er = extraction_run.current()
    if er is not None and er.status == "running":
        return JSONResponse(
            {
                "error": (
                    "Theme extraction is currently running. Cancel it from the "
                    "global progress strip, then retry the edit."
                )
            },
            status_code=409,
        )

    state = load_state()
    try:
        start_idx = _resolve_edit_point(from_stage, state)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    # 1. Persist any caller-supplied input edits before touching artifacts.
    set_params_patch = body.get("set_params_patch")
    theme_input_patch = body.get("theme_input")
    theme_payload = body.get("theme_payload")

    if set_params_patch is not None or theme_input_patch is not None:
        if (set_params_patch is not None and not isinstance(set_params_patch, dict)) or (
            theme_input_patch is not None and not isinstance(theme_input_patch, dict)
        ):
            return JSONResponse(
                {"error": "set_params_patch and theme_input must be objects"},
                status_code=400,
            )
        settings = project.settings
        update: dict[str, Any] = {}
        if isinstance(set_params_patch, dict):
            sp = settings.set_params
            new_name = set_params_patch.get("set_name", sp.set_name)
            new_size = set_params_patch.get("set_size", sp.set_size)
            new_mech = set_params_patch.get("mechanic_count", sp.mechanic_count)
            # Validate the same way the live-apply /params endpoint
            # does so a hand-poked client (or a buggy form) gets a
            # clear 400 instead of a 500 from Pydantic.
            if not isinstance(new_name, str):
                return JSONResponse(
                    {"error": "set_params_patch.set_name must be a string"},
                    status_code=400,
                )
            if not isinstance(new_size, int) or new_size <= 0:
                return JSONResponse(
                    {"error": "set_params_patch.set_size must be a positive int"},
                    status_code=400,
                )
            if not isinstance(new_mech, int) or new_mech < 0:
                return JSONResponse(
                    {"error": "set_params_patch.mechanic_count must be a non-negative int"},
                    status_code=400,
                )
            new_sp = SetParams(
                set_name=new_name,
                set_size=new_size,
                mechanic_count=new_mech,
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
        apply_settings(settings.model_copy(update=update))

    artifact_dir = set_artifact_dir()

    if theme_payload is not None:
        if not isinstance(theme_payload, dict):
            return JSONResponse({"error": "theme_payload must be an object"}, status_code=400)
        theme_path = artifact_dir / "theme.json"
        theme_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            theme_path,
            json.dumps(theme_payload, indent=2, ensure_ascii=False),
        )

    # 2. Cascade-clear pipeline artifacts + reset stages to PENDING.
    if state is not None:
        _apply_cascade_clear(state, start_idx)

    # 3. theme.json wipe (Project Settings → theme_input change).
    if clear_theme_json:
        theme_path = artifact_dir / "theme.json"
        if theme_path.exists():
            try:
                theme_path.unlink()
            except OSError as e:
                logger.warning("Failed to delete %s: %s", theme_path, e)

    # 4. Decide where to navigate / whether to re-kick the engine.
    theme_path = artifact_dir / "theme.json"
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
    new_state, kickoff_err = _kickoff_pipeline_engine(project.set_code)
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


@router.post("/api/wizard/instance/rerun")
async def wizard_instance_rerun(request: Request) -> JSONResponse:
    """Re-run a looping-stage instance from the card pool it received on entry.

    Body: ``{"instance_id": "<card_gen|conformance|balance|ai_review[.N]>"}``.
    Restores the instance's entry-pool snapshot, drops every downstream instance
    (+ their history), resets the instance, re-appends the canonical forward path,
    and kicks the engine — the forward mirror of the engine's own review->regen
    insertion (see ``engine.rerun_instance``). Past instances are untouched.

    Because it regenerates all downstream output (gates, finalize, art, renders),
    it carries the same cascade contract as ``edit/accept`` — the client confirms
    when art/renders already exist. 409 if the engine or a theme extraction is
    running (cancel first); 400 for an unknown / non-re-runnable instance.
    """
    from mtgai.pipeline import history
    from mtgai.pipeline.engine import rerun_instance

    project = _require_active_project()
    body, err = await _read_request_json(request)
    if err is not None:
        return err
    instance_id = body.get("instance_id")
    if not isinstance(instance_id, str) or not instance_id:
        return JSONResponse({"error": "instance_id required"}, status_code=400)

    if _engine is not None and _engine.is_running:
        return JSONResponse(
            {
                "error": (
                    "A pipeline stage is currently running. Cancel it from the "
                    "global progress strip, then retry the re-run."
                )
            },
            status_code=409,
        )
    er = extraction_run.current()
    if er is not None and er.status == "running":
        return JSONResponse(
            {
                "error": (
                    "Theme extraction is currently running. Cancel it from the "
                    "global progress strip, then retry the re-run."
                )
            },
            status_code=409,
        )

    state = load_state()
    if state is None:
        return JSONResponse({"error": "No pipeline state to re-run"}, status_code=400)
    idx = next((i for i, s in enumerate(state.stages) if s.instance_id == instance_id), None)
    if idx is None:
        return JSONResponse({"error": f"Unknown instance {instance_id!r}"}, status_code=400)
    target = state.stages[idx]
    if target.stage_id not in history.RERUNNABLE_STAGES:
        return JSONResponse(
            {"error": f"Stage {target.stage_id!r} is not re-runnable"}, status_code=400
        )

    # Note a missing entry snapshot (migration) so the client can surface that the
    # re-run started from the live pool rather than a faithful entry snapshot.
    entry_pred = target.entry_snapshot_id or (
        state.stages[idx - 1].instance_id if idx > 0 else None
    )
    missing_snapshot = entry_pred is not None and not history.snapshot_exists(entry_pred)

    rerun_instance(state, instance_id)

    new_state, kickoff_err = _kickoff_pipeline_engine(project.set_code)
    resp: dict[str, Any] = {
        "success": True,
        "engine_started": kickoff_err is None and new_state is not None,
        "navigate_to": f"/pipeline/{instance_id}",
    }
    if kickoff_err is not None or new_state is None:
        resp["warning"] = kickoff_err or "Engine kickoff skipped"
    elif missing_snapshot:
        resp["warning"] = (
            "No entry snapshot for this instance (created before version "
            "tracking) — re-ran from the current card pool."
        )
    return JSONResponse(resp)


# ---------------------------------------------------------------------------
# Wizard Mechanics tab — bespoke candidates strip (TC-2)
# ---------------------------------------------------------------------------


def _mechanics_dir() -> Path:
    """``<asset_folder>/mechanics`` for the active project."""
    return set_artifact_dir() / "mechanics"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read %s; treating as %r", path, default)
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        path,
        json.dumps(payload, indent=2, ensure_ascii=False),
    )


def _theme_summary(theme: dict | None) -> str:
    if not theme:
        return ""
    text = theme.get("theme") or theme.get("setting") or ""
    if not isinstance(text, str):
        return ""
    text = text.strip()
    return text[:600] + ("…" if len(text) > 600 else "")


def _stage_status_in_state(stage_id: str) -> str:
    """Return the current stage status string ("pending" if no state)."""
    state = _get_current_state()
    if state is None:
        return "pending"
    for s in state.stages:
        if s.stage_id == stage_id:
            return s.status.value
    return "pending"


def _stage_state_base(stage_id: str, settings: Any) -> dict:
    """The common tail every stage tab's ``/state`` payload shares.

    The mechanics / archetypes / skeleton ``state`` endpoints all surface the
    same four fields — set params, the theme excerpt, the stage's assigned LLM,
    and its current status (the model assignment is keyed by ``stage_id``). Each
    endpoint merges its tab-specific keys on top of this base.
    """
    return {
        "set_params": settings.set_params.model_dump(),
        "theme_summary": _theme_summary(read_theme_or_none()),
        # Display the base model the user assigned, not the internal context-tier
        # twin get_llm_model_id resolves to at runtime.
        "model_id": settings.get_assigned_model_id(stage_id),
        "stage_status": _stage_status_in_state(stage_id),
    }


def _next_stage_nav(stage_id: str) -> str:
    """``navigate_to`` for the stage after ``stage_id`` in ``STAGE_DEFINITIONS``.

    The ``save`` endpoints return this so the client redirects to whatever stage
    actually follows (rather than a hardcoded target), keeping the footer label
    and this redirect in lockstep when stages are inserted between. ``/pipeline``
    when ``stage_id`` is last or unknown.
    """
    idx = next((i for i, d in enumerate(STAGE_DEFINITIONS) if d["stage_id"] == stage_id), -1)
    next_id = (
        STAGE_DEFINITIONS[idx + 1]["stage_id"] if 0 <= idx < len(STAGE_DEFINITIONS) - 1 else None
    )
    return f"/pipeline/{next_id}" if next_id else "/pipeline"


@router.get("/api/wizard/mechanics/state")
async def wizard_mechanics_state() -> JSONResponse:
    """First-paint state for the Mechanics tab.

    Reads ``candidates.json`` + ``approved.json`` from disk, surfaces
    the current ``set_params`` + theme summary, and reports the stage
    status so the strip can render itself in the right mode (running /
    paused_for_review / completed / pending).
    """
    from mtgai.generation.mechanic_generator import detect_keyword_collisions

    project = _require_active_project()
    settings = project.settings

    mech_dir = _mechanics_dir()

    candidates = _read_json(mech_dir / "candidates.json", [])
    approved = _read_json(mech_dir / "approved.json", None)
    pick_rationale = _read_json(mech_dir / "pick-rationale.json", None)
    if not isinstance(candidates, list):
        candidates = []

    collisions = detect_keyword_collisions(candidates)
    return JSONResponse(
        {
            "candidates": candidates,
            "approved": approved,
            "pick_rationale": pick_rationale,
            "collisions": {str(idx): name for idx, name in collisions.items()},
            **_stage_state_base("mechanics", settings),
        }
    )


def _coerce_candidates_payload(value: Any) -> list[dict] | None:
    """Validate the ``candidates`` field of refresh / save bodies."""
    if not isinstance(value, list):
        return None
    out: list[dict] = []
    for entry in value:
        if not isinstance(entry, dict):
            return None
        out.append(entry)
    return out


def _coerce_indices(value: Any, max_count: int) -> list[int] | None:
    """Strict index list coercer — every entry must be in range [0, max_count).

    The merged candidates list is padded / trimmed to the candidate-pool
    size server-side, so ``max_count`` is the post-pad bound. Out-of-range
    or duplicate entries are rejected outright (returning None) — the
    refresh-all merge loop relies on the indices being in-bounds.
    """
    if not isinstance(value, list):
        return None
    out: list[int] = []
    seen: set[int] = set()
    for entry in value:
        if not isinstance(entry, int) or entry < 0 or entry >= max_count:
            return None
        if entry in seen:
            return None
        seen.add(entry)
        out.append(entry)
    return out


async def _read_request_json(request: Request) -> tuple[Any, JSONResponse | None]:
    """Decode the request body or short-circuit with a 400.

    Mirrors the inline ``request.json()`` calls elsewhere in this
    module but turns a malformed payload into a clean 400 instead of a
    500 from the FastAPI default error path.
    """
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return None, JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    return body, None


@router.post("/api/wizard/mechanics/refresh-card")
async def wizard_mechanics_refresh_card(request: Request) -> JSONResponse:
    """Regenerate a single candidate within the paused mechanics stage.

    Body: ``{candidate_index: int, candidates: list[dict]}``. The client
    sends its current view of the candidates list (so user edits to
    other rows are preserved); the server runs the LLM, replaces the
    indexed slot with the first newly-generated candidate (tagged
    ``_ai_generated: true``), persists the merged list to
    ``candidates.json`` inside the AI lock, and returns the merged
    list so the client can rerender.

    Refusal modes:
    * 409 ``no_active_project`` — no project open.
    * 409 ``no_asset_folder`` — project open but asset_folder unset.
    * 409 + ``busy_payload`` — another AI action holds the lock.
    """
    from mtgai.generation.mechanic_generator import (
        candidate_count,
        generate_mechanic_candidates,
    )

    project = _require_active_project()
    pool = candidate_count(project.settings.set_params.mechanic_count)
    body, err = await _read_request_json(request)
    if err is not None:
        return err
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON body required"}, status_code=400)
    candidates = _coerce_candidates_payload(body.get("candidates"))
    if candidates is None:
        return JSONResponse({"error": "candidates must be a list of dicts"}, status_code=400)
    idx = body.get("candidate_index")
    if not isinstance(idx, int) or idx < 0 or idx >= pool:
        return JSONResponse(
            {"error": (f"candidate_index must be an int in [0, {pool})")},
            status_code=400,
        )
    mech_dir = _mechanics_dir()

    # Stream the regenerated candidate into the wizard via the same hooks the
    # engine path uses (``stage_hooks``), rebound to the *one* slot being
    # refreshed: ``slot_for`` pins every loop position to ``idx`` so the emitted
    # position is idx+1 and the persist lands in ``merged[idx]``. No reset — a
    # targeted refresh leaves the other rows alone (on_reset isn't wired).
    # ``known_keywords`` is built once outside the LLM call.
    from mtgai.generation.mechanic_generator import known_keyword_set

    known_keywords = known_keyword_set()

    # Build the merged list up front from the user's snapshot so the on_finalized
    # hook can mutate + persist it incrementally. Without this, candidates.json
    # only gets rewritten when the request returns — so a browser F5 mid-run reads
    # the pre-refresh snapshot and looks like a regression.
    merged = list(candidates)
    while len(merged) < pool:
        merged.append({})
    merged = merged[:pool]

    hooks = build_mechanic_hooks(
        _refresh_emitter("mechanics"),
        pool=pool,
        merged=merged,
        candidates_path=mech_dir / "candidates.json",
        known_keywords=known_keywords,
        slot_for=lambda _position: idx,
    )

    with guarded_ai("Mechanic candidate refresh", stage_id="mechanics") as guard:
        if guard.busy:
            return guard.busy_response
        # Only the first result is used to replace the one slot — ask
        # for exactly one so we don't run the full top-up loop.
        with _bus_poller("mechanics", activity_prefix="Designing mechanic"):
            response = await asyncio.to_thread(
                generate_mechanic_candidates,
                count=1,
                on_draft=hooks.on_draft,
                on_finalized=hooks.on_finalized,
                on_council=hooks.on_council,
            )
        new_mechanics = response["mechanics"]
        if not new_mechanics:
            raise AIActionError("LLM returned no candidates")
        # ``merged`` is already up to date via the on_finalized callback — the new
        # mechanic landed in slot ``idx`` and was written to disk; the guard heals
        # the stage + releases on a clean exit.

    return JSONResponse(
        {
            "success": True,
            "candidates": merged,
            "model_id": response.get("model_id"),
        }
    )


@router.post("/api/wizard/mechanics/refresh-all")
async def wizard_mechanics_refresh_all(request: Request) -> JSONResponse:
    """Regenerate AI-flagged candidates, or kick off initial generation.

    Body: ``{indices: list[int], candidates: list[dict]}``.

    * Both empty → initial generation from scratch (the "Generate AI
      candidates" button on an empty mechanics tab — used to recover
      from a stuck/failed initial run without going back through the
      Theme edit cascade).
    * ``indices`` non-empty → regenerate those rows only; user-edited
      rows in ``candidates`` survive untouched.

    Returns ``collisions`` alongside ``candidates`` so the client can
    re-render warnings without a separate state fetch.
    """
    from mtgai.generation.mechanic_generator import (
        candidate_count,
        detect_keyword_collisions,
        generate_mechanic_candidates,
        persist_mechanic_selection,
        pick_best_mechanics,
    )

    project = _require_active_project()
    pool = candidate_count(project.settings.set_params.mechanic_count)
    body, err = await _read_request_json(request)
    if err is not None:
        return err
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON body required"}, status_code=400)
    candidates = _coerce_candidates_payload(body.get("candidates"))
    if candidates is None:
        return JSONResponse({"error": "candidates must be a list of dicts"}, status_code=400)
    # Indices are bound by the post-pad pool size (we pad / trim
    # ``candidates`` below to that size). Reject duplicates + out-of-range
    # values up front so the merge loop can trust them.
    indices = _coerce_indices(body.get("indices"), pool)
    if indices is None:
        return JSONResponse(
            {"error": (f"indices must be a list of unique ints in [0, {pool})")},
            status_code=400,
        )
    initial_generate = not indices and not candidates
    if not indices and not initial_generate:
        return JSONResponse({"error": "Nothing to refresh — no AI-flagged rows"}, status_code=400)
    mech_dir = _mechanics_dir()

    # Stream candidates into the wizard via the same SSE events the engine
    # path uses. Two modes:
    #   * initial_generate — emit a full reset + position 1..pool as the loop
    #     produces them.
    #   * targeted refresh — no reset (preserve untouched rows); remap each
    #     loop position (1..len(indices)) back to its real slot index so the
    #     wizard updates the right card.
    from mtgai.generation.mechanic_generator import known_keyword_set

    known_keywords = known_keyword_set()

    def _slot_for(position: int) -> int:
        """0-based slot index for the loop's 1-based ``position``.

        For initial generation the loop's position *is* the slot index + 1.
        For a targeted refresh, position N maps to ``indices[N-1]`` because
        the loop walks them in order; we cap defensively in case the model
        somehow returns more candidates than we asked for.
        """
        if initial_generate:
            return position - 1
        i = position - 1
        return indices[i] if 0 <= i < len(indices) else position - 1

    # Build the merged list up front so the on_finalized callback can mutate
    # + persist it incrementally. Each finalized mechanic lands on disk
    # immediately, so a browser F5 mid-run sees the latest snapshot instead
    # of the pre-refresh state. Initial-generate starts from a blank pool;
    # targeted refresh starts from the user's snapshot (preserving untouched
    # rows).
    if initial_generate:
        merged: list[dict] = [{} for _ in range(pool)]
    else:
        merged = list(candidates)
        while len(merged) < pool:
            merged.append({})
        merged = merged[:pool]

    # Same hooks the engine path uses (``stage_hooks``): ``_slot_for`` remaps
    # each loop position to its real slot, and ``fire_reset`` gates the reset
    # event to the full-pool (initial-generate) path — a targeted refresh leaves
    # untouched rows alone. The hooks own the persist + collision + payloads.
    hooks = build_mechanic_hooks(
        _refresh_emitter("mechanics"),
        pool=pool,
        merged=merged,
        candidates_path=mech_dir / "candidates.json",
        known_keywords=known_keywords,
        slot_for=_slot_for,
        fire_reset=initial_generate,
    )

    with guarded_ai("Mechanic candidate refresh", stage_id="mechanics") as guard:
        if guard.busy:
            return guard.busy_response
        # Initial generation wants the full pool; a targeted refresh only
        # needs as many fresh candidates as there are flagged rows.
        gen_count = pool if initial_generate else len(indices)
        # First of two sequential spans (generate, then pick) — suppress this
        # one's terminal "done" so the strip doesn't blink off before the pick.
        with _bus_poller("mechanics", activity_prefix="Designing mechanics", emit_done=False):
            response = await asyncio.to_thread(
                generate_mechanic_candidates,
                count=gen_count,
                on_reset=hooks.on_reset,
                on_draft=hooks.on_draft,
                on_finalized=hooks.on_finalized,
                on_council=hooks.on_council,
            )

        # ``merged`` is already up to date via the on_finalized callback —
        # each finalized mechanic landed in its slot and was written to disk.
        # ``response["mechanics"]`` matches what's in merged; we don't need
        # to redo the merge.
        _ = response["mechanics"]

        # Whenever we replaced anything, re-run the AI picker on the merged
        # slate — the prior selection points at rows that may have been
        # vanished or rewritten, so leaving it alone leaves a stale-looking
        # Final Picks box on the tab. Same call the stage runner makes;
        # ``persist_mechanic_selection`` writes candidates.json + approved.json
        # + sidecars so disk + memory agree on the new selection.
        with _bus_poller("mechanics", activity_prefix="Picking the best mechanics"):
            pick = await asyncio.to_thread(pick_best_mechanics, candidates=merged)
        persist_mechanic_selection(
            mech_dir,
            merged,
            pick["picks"],
            source="ai",
            overall_rationale=pick["overall_rationale"],
            selections=pick["selections"],
            model_id=pick["model_id"],
        )
        # The guard heals a stuck FAILED stage (e.g. an initial generation that
        # ran below the floor) on a clean exit, so Save & Continue reappears.

    collisions = detect_keyword_collisions(merged)
    return JSONResponse(
        {
            "success": True,
            "candidates": merged,
            "collisions": {str(idx): name for idx, name in collisions.items()},
            "model_id": response.get("model_id"),
            "picks": pick["picks"],
            "selections": pick["selections"],
            "overall_rationale": pick["overall_rationale"],
        }
    )


@router.post("/api/wizard/mechanics/save")
async def wizard_mechanics_save(request: Request) -> JSONResponse:
    """Persist the user's picks as ``approved.json`` plus auto-sidecars.

    Body: ``{picks: list[int], candidates: list[dict]}``. Picks index
    into ``candidates`` (which carries any inline edits). The handler:

    1. Validates that ``len(picks) == settings.set_params.mechanic_count``
       and that each pick is in range.
    2. Writes ``candidates.json`` (snapshot of the user's working state).
    3. Projects picked candidates → ``approved.json`` shape via
       :func:`mtgai.generation.mechanic_generator.candidate_to_approved`
       (copies the field whitelist, renames ``design_rationale`` →
       ``design_notes``, derives ``rarity_range``).
    4. Writes the auto-sidecars: ``evergreen-keywords.json`` (default
       per-color table), ``pointed-questions.json`` (canonical template
       with ``{mechanic_names}`` substituted), ``functional-tags.json``
       (empty stub), and ``pick-rationale.json`` (marked ``source: user``,
       overwriting any AI-picker rationale).
    5. Returns ``{success, navigate_to}`` pointing at the stage that
       follows ``mechanics`` in ``STAGE_DEFINITIONS`` (``archetypes``
       today) — the client follows up with ``POST /api/wizard/advance``
       to flip the stage to COMPLETED and resume the engine.

    The write order (sidecars + candidates first, ``approved.json`` last) is
    owned by :func:`mtgai.generation.mechanic_generator.persist_mechanic_selection`,
    shared with the stage runner's AI picker and the re-pick endpoint.
    """
    from mtgai.generation.mechanic_generator import persist_mechanic_selection

    project = _require_active_project()
    settings = project.settings
    body, err = await _read_request_json(request)
    if err is not None:
        return err
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON body required"}, status_code=400)
    candidates = _coerce_candidates_payload(body.get("candidates"))
    if candidates is None:
        return JSONResponse({"error": "candidates must be a list of dicts"}, status_code=400)
    picks_raw = body.get("picks")
    if not isinstance(picks_raw, list):
        return JSONResponse({"error": "picks must be a list of indices"}, status_code=400)
    expected = settings.set_params.mechanic_count
    if len(picks_raw) != expected:
        return JSONResponse(
            {"error": f"Expected exactly {expected} picks, got {len(picks_raw)}"},
            status_code=400,
        )
    picks: list[int] = []
    for entry in picks_raw:
        if not isinstance(entry, int) or entry < 0 or entry >= len(candidates):
            return JSONResponse(
                {"error": "Each pick must be an int within candidates"},
                status_code=400,
            )
        picks.append(entry)
    if len(set(picks)) != len(picks):
        return JSONResponse({"error": "picks must be unique"}, status_code=400)

    mech_dir = _mechanics_dir()

    approved = persist_mechanic_selection(
        mech_dir,
        candidates,
        picks,
        source="user",
        selections=[{"name": (candidates[i].get("name") or "?"), "reason": ""} for i in picks],
        model_id=settings.get_assigned_model_id("mechanics"),
    )
    _heal_failed_stage("mechanics")

    logger.info(
        "Mechanics save: %d picks → %s; sidecars written", len(picks), mech_dir / "approved.json"
    )
    return JSONResponse(
        {
            "success": True,
            "approved": approved,
            "navigate_to": _next_stage_nav("mechanics"),
        }
    )


@router.post("/api/wizard/mechanics/pick")
async def wizard_mechanics_pick(request: Request) -> JSONResponse:
    """Re-run the AI picker over the current candidates and write the selection.

    Body: ``{candidates: list[dict]}`` — the client's current working view
    (inline edits included). Runs :func:`pick_best_mechanics` inside the AI
    lock, writes ``approved.json`` + sidecars + ``pick-rationale.json``
    (``source: ai``) via the shared persist helper, and returns the chosen
    indices + per-pick reasons so the strip can pre-select and surface them
    without a separate state fetch.

    Lets the user ask the AI to (re-)choose without manually ticking
    checkboxes — e.g. after editing or regenerating candidates. The picker
    degrades to the first N candidates rather than failing, so a successful
    call always leaves a valid selection on disk.

    Refusal modes mirror the other mechanics AI endpoints: 409
    ``no_active_project`` / ``no_asset_folder``, or 409 + ``busy_payload``
    when another AI action holds the lock.
    """
    from mtgai.generation.mechanic_generator import (
        persist_mechanic_selection,
        pick_best_mechanics,
    )

    _require_active_project()
    body, err = await _read_request_json(request)
    if err is not None:
        return err
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON body required"}, status_code=400)
    candidates = _coerce_candidates_payload(body.get("candidates"))
    if candidates is None:
        return JSONResponse({"error": "candidates must be a list of dicts"}, status_code=400)
    if not candidates:
        return JSONResponse({"error": "No candidates to pick from"}, status_code=400)
    mech_dir = _mechanics_dir()

    with guarded_ai("Mechanic AI pick", stage_id="mechanics") as guard:
        if guard.busy:
            return guard.busy_response
        with _bus_poller("mechanics", activity_prefix="Picking the best mechanics"):
            pick = await asyncio.to_thread(pick_best_mechanics, candidates=candidates)
        approved = persist_mechanic_selection(
            mech_dir,
            candidates,
            pick["picks"],
            source="ai",
            overall_rationale=pick["overall_rationale"],
            selections=pick["selections"],
            model_id=pick["model_id"],
        )
        # The guard heals a FAILED stage on a clean exit — a successful pick
        # means the stage is healthy and Save & Continue should reappear.

    return JSONResponse(
        {
            "success": True,
            "picks": pick["picks"],
            "selections": pick["selections"],
            "overall_rationale": pick["overall_rationale"],
            "approved": approved,
            "model_id": pick["model_id"],
        }
    )


# ---------------------------------------------------------------------------
# Wizard Archetypes tab — bespoke per-color-pair review strip (TC-3)
#
# Unlike mechanics there's no "pick" step: all ten two-color pairs are kept,
# one archetype each. The tab is a 10-card grid the user can edit + refresh.
# ``archetypes.json`` is the canonical artifact (strictly color_pair / name /
# description); AI-vs-human provenance is kept out of it in a sidecar
# ``archetypes/provenance.json`` (color_pair -> "ai"|"human") so the
# preserve-on-refresh contract (§5) survives reloads without polluting the
# downstream-consumed file. A pair missing from the sidecar defaults to "ai"
# (the stage runner writes archetypes.json with no provenance).
# ---------------------------------------------------------------------------


def _order_working_archetypes(working: list[dict] | None) -> list[dict]:
    """Normalize a working archetype list to one entry per pair in WUBRG order.

    Returns exactly ten ``{color_pair, name, description, _ai_generated}``
    dicts (one per :data:`COLOR_PAIRS` entry), filling any missing pair with
    an empty AI-flagged placeholder. Input pairs are canonicalised; the first
    entry seen per pair wins and any extras / malformed entries are dropped.
    """
    from mtgai.generation.archetype_generator import COLOR_PAIRS, normalize_color_pair

    by_pair: dict[str, dict] = {}
    for a in working or []:
        if not isinstance(a, dict):
            continue
        cp = normalize_color_pair(a.get("color_pair"))
        if cp is None or cp in by_pair:
            continue
        by_pair[cp] = a
    out: list[dict] = []
    for p in COLOR_PAIRS:
        a = by_pair.get(p)
        out.append(
            {
                "color_pair": p,
                "name": (a.get("name") or "") if a else "",
                "description": (a.get("description") or "") if a else "",
                "_ai_generated": bool(a.get("_ai_generated", True)) if a else True,
            }
        )
    return out


def _persist_archetypes_working(asset_dir: Path, ordered: list[dict]) -> list[dict]:
    """Write ``archetypes.json`` (clean) + the provenance sidecar.

    ``ordered`` is the ten-entry working view. Empty placeholder pairs (no
    name and no description) are skipped from both files so the canonical
    artifact never carries junk entries. Returns the list written to
    ``archetypes.json`` (clean, content-only).
    """
    clean: list[dict] = []
    provenance: dict[str, str] = {}
    for a in ordered:
        pair = a["color_pair"]
        name = (a.get("name") or "").strip()
        desc = (a.get("description") or "").strip()
        if not name and not desc:
            continue
        clean.append({"color_pair": pair, "name": name, "description": desc})
        provenance[pair] = "ai" if a.get("_ai_generated", True) else "human"
    _write_json(asset_dir / "archetypes.json", clean)
    _write_json(asset_dir / "archetypes" / "provenance.json", provenance)
    return clean


@router.get("/api/wizard/archetypes/state")
async def wizard_archetypes_state() -> JSONResponse:
    """First-paint state for the Archetypes tab.

    Reads ``archetypes.json`` + the provenance sidecar, folds provenance
    into per-pair ``_ai_generated`` flags, and returns the full ten-pair
    working view (missing pairs as empty AI placeholders) alongside the
    canonical pair order/labels, set params, theme excerpt, model id, and
    the current stage status.
    """
    from mtgai.generation.archetype_generator import (
        COLOR_PAIRS,
        normalize_color_pair,
        pair_label,
    )

    project = _require_active_project()
    settings = project.settings

    asset = set_artifact_dir()

    archetypes = _read_json(asset / "archetypes.json", [])
    if not isinstance(archetypes, list):
        archetypes = []
    provenance = _read_json(asset / "archetypes" / "provenance.json", {})
    prov = provenance if isinstance(provenance, dict) else {}

    flagged: list[dict] = []
    for a in archetypes:
        if not isinstance(a, dict):
            continue
        cp = normalize_color_pair(a.get("color_pair"))
        if cp is None:
            continue
        flagged.append({**a, "color_pair": cp, "_ai_generated": prov.get(cp) != "human"})
    working = _order_working_archetypes(flagged)
    has_content = any((a["name"] or a["description"]) for a in working)

    return JSONResponse(
        {
            "archetypes": working,
            "has_content": has_content,
            "pairs": [{"pair": p, "label": pair_label(p)} for p in COLOR_PAIRS],
            **_stage_state_base("archetypes", settings),
        }
    )


@router.post("/api/wizard/archetypes/refresh-card")
async def wizard_archetypes_refresh_card(request: Request) -> JSONResponse:
    """Regenerate the archetype for a single color pair.

    Body: ``{color_pair: str, archetypes: list[dict]}``. The client sends
    its current working view (so edits to other pairs survive); the server
    runs a *focused* regeneration (``generate_archetypes(focus_pairs=[pair],
    existing=working)``) so the new design stays distinct from the kept
    pairs, swaps the one pair in (tagged AI), persists, and returns the
    merged working view.

    Refusal modes mirror the mechanics AI endpoints: 409 ``no_active_project``
    / ``no_asset_folder``, or 409 + ``busy_payload`` when the AI lock is held.
    """
    from mtgai.generation.archetype_generator import generate_archetypes, normalize_color_pair

    _require_active_project()
    body, err = await _read_request_json(request)
    if err is not None:
        return err
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON body required"}, status_code=400)
    color_pair = normalize_color_pair(body.get("color_pair"))
    if color_pair is None:
        return JSONResponse(
            {"error": "color_pair must be a valid two-color pair (WUBRG order)"},
            status_code=400,
        )
    working = _coerce_candidates_payload(body.get("archetypes"))
    if working is None:
        return JSONResponse({"error": "archetypes must be a list of dicts"}, status_code=400)

    asset = set_artifact_dir()

    ordered = _order_working_archetypes(working)
    with guarded_ai("Archetype refresh", stage_id="archetypes") as guard:
        if guard.busy:
            return guard.busy_response
        with _bus_poller("archetypes", activity_prefix="Designing archetype"):
            response = await asyncio.to_thread(
                generate_archetypes, focus_pairs=[color_pair], existing=ordered
            )
        fresh = response["archetypes"]
        new_entry = next((a for a in fresh if a.get("color_pair") == color_pair), None)
        if new_entry is None:
            raise AIActionError(f"Regeneration produced no archetype for {color_pair}")
        for entry in ordered:
            if entry["color_pair"] == color_pair:
                entry["name"] = new_entry.get("name") or ""
                entry["description"] = new_entry.get("description") or ""
                entry["_ai_generated"] = True
                break
        _persist_archetypes_working(asset, ordered)

    return JSONResponse(
        {"success": True, "archetypes": ordered, "model_id": response.get("model_id")}
    )


@router.post("/api/wizard/archetypes/refresh-all")
async def wizard_archetypes_refresh_all(request: Request) -> JSONResponse:
    """Regenerate AI-flagged pairs, or kick off initial generation.

    Body: ``{pairs: list[str], archetypes: list[dict]}``.

    * Both empty → initial full generation (the "Generate" button on an
      empty Archetypes tab — recovers a stuck/failed initial run without the
      Theme/Mechanics edit cascade). All ten pairs come back AI-flagged.
    * ``pairs`` non-empty → a single full regeneration, then only the listed
      pairs are swapped in (re-tagged AI); pairs the user hand-edited survive
      untouched. Generating the full set in one coherent pass keeps the kept
      and refreshed archetypes consistent with each other.
    """
    from mtgai.generation.archetype_generator import generate_archetypes, normalize_color_pair

    _require_active_project()
    body, err = await _read_request_json(request)
    if err is not None:
        return err
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON body required"}, status_code=400)
    working = _coerce_candidates_payload(body.get("archetypes"))
    if working is None:
        return JSONResponse({"error": "archetypes must be a list of dicts"}, status_code=400)

    raw_pairs = body.get("pairs")
    if not isinstance(raw_pairs, list):
        return JSONResponse({"error": "pairs must be a list of color-pair codes"}, status_code=400)
    refresh_pairs: set[str] = set()
    for entry in raw_pairs:
        cp = normalize_color_pair(entry)
        if cp is None:
            return JSONResponse(
                {"error": f"Invalid color pair in pairs: {entry!r}"}, status_code=400
            )
        refresh_pairs.add(cp)

    has_working = any(
        isinstance(a, dict)
        and ((a.get("name") or "").strip() or (a.get("description") or "").strip())
        for a in working
    )
    initial_generate = not refresh_pairs and not has_working
    if not refresh_pairs and not initial_generate:
        return JSONResponse({"error": "Nothing to refresh — no AI-flagged pairs"}, status_code=400)

    asset = set_artifact_dir()

    ordered = _order_working_archetypes(working)
    with guarded_ai("Archetype refresh", stage_id="archetypes") as guard:
        if guard.busy:
            return guard.busy_response
        with _bus_poller("archetypes", activity_prefix="Designing archetypes"):
            response = await asyncio.to_thread(generate_archetypes)
        fresh_by_pair = {a["color_pair"]: a for a in response["archetypes"]}
        for entry in ordered:
            pair = entry["color_pair"]
            replace = initial_generate or pair in refresh_pairs
            if replace and pair in fresh_by_pair:
                fresh = fresh_by_pair[pair]
                entry["name"] = fresh.get("name") or ""
                entry["description"] = fresh.get("description") or ""
                entry["_ai_generated"] = True
        _persist_archetypes_working(asset, ordered)

    return JSONResponse(
        {"success": True, "archetypes": ordered, "model_id": response.get("model_id")}
    )


@router.post("/api/wizard/archetypes/save")
async def wizard_archetypes_save(request: Request) -> JSONResponse:
    """Persist the reviewed archetypes and report the next stage.

    Body: ``{archetypes: list[dict]}`` — the ten-pair working view with any
    inline edits. Validates that every pair has a non-empty name +
    description, writes ``archetypes.json`` (clean) + the provenance sidecar,
    and returns ``{success, navigate_to}`` pointing at the stage that follows
    ``archetypes`` in ``STAGE_DEFINITIONS`` (``skeleton`` today). The client
    follows up with ``POST /api/wizard/advance`` to flip the stage
    COMPLETED and resume the engine.

    No AI lock — this is a pure disk write (matches ``mechanics/save``).
    """
    from mtgai.generation.archetype_generator import pair_label

    _require_active_project()
    body, err = await _read_request_json(request)
    if err is not None:
        return err
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON body required"}, status_code=400)
    working = _coerce_candidates_payload(body.get("archetypes"))
    if working is None:
        return JSONResponse({"error": "archetypes must be a list of dicts"}, status_code=400)

    ordered = _order_working_archetypes(working)
    for a in ordered:
        if not (a.get("name") or "").strip() or not (a.get("description") or "").strip():
            return JSONResponse(
                {"error": f"{pair_label(a['color_pair'])} needs both a name and a description."},
                status_code=400,
            )

    asset = set_artifact_dir()

    clean = _persist_archetypes_working(asset, ordered)
    logger.info("Archetypes save: %d archetypes → %s", len(clean), asset / "archetypes.json")
    _heal_failed_stage("archetypes")

    return JSONResponse(
        {
            "success": True,
            "archetypes": clean,
            "navigate_to": _next_stage_nav("archetypes"),
        }
    )


# ---------------------------------------------------------------------------
# Skeleton — default vs LLM-relabeled, reviewed on the Skeleton tab
# ---------------------------------------------------------------------------


def _skeleton_slot_view(slot: dict) -> dict:
    """Shape one skeleton slot for the tab: id + default descriptor + tweak."""
    from mtgai.skeleton.generator import render_slot_string

    default_text = render_slot_string(slot)
    tweaked = (slot.get("tweaked_text") or "").strip()
    return {
        "slot_id": slot.get("slot_id"),
        "default_text": default_text,
        "tweaked_text": tweaked or default_text,
        "reserved_card": slot.get("reserved_card"),
        "cycle_id": slot.get("cycle_id"),
    }


def _skeleton_knobs_payload(skeleton: dict) -> dict:
    """The knobs / cycles / specs block of the Skeleton tab state.

    Reads the persisted ``knobs`` off ``skeleton.json`` (defaulting when absent —
    a pre-knobs skeleton) and pairs it with the spec bounds the UI renders
    controls from. Kept separate so both ``/state`` and the knob endpoints return
    the same shape.
    """
    from mtgai.skeleton.knobs import SkeletonKnobs, cycle_options_payload, knob_specs_payload

    raw = skeleton.get("knobs")
    knobs = SkeletonKnobs.model_validate(raw) if isinstance(raw, dict) else SkeletonKnobs()
    # The cycles the build actually KEPT live at the top level of the result
    # (cycles too big for their rarity budget are dropped from there but remain in
    # ``knobs.cycles`` as proposed); show the kept ones so the UI never lists a
    # cycle that isn't in the matrix. Fall back to the proposed list for a
    # pre-knobs skeleton with no top-level ``cycles``.
    kept_cycles = skeleton.get("cycles")
    cycles = (
        kept_cycles if isinstance(kept_cycles, list) else [c.model_dump() for c in knobs.cycles]
    )
    return {
        "knobs": knobs.model_dump(),
        "knob_specs": knob_specs_payload(),
        "cycles": cycles,
        "cycle_options": cycle_options_payload(),
        "knobs_defaulted": bool(skeleton.get("knobs_defaulted")),
        "knob_warnings": skeleton.get("knob_warnings", []),
    }


def _reprint_slot_count(asset: Path) -> int | None:
    """Count of unfilled skeleton slots a reprint could fill (None if no skeleton)."""
    from mtgai.generation.reprint_selector import _load_slot_texts

    skeleton_path = asset / "skeleton.json"
    if not skeleton_path.exists():
        return None
    return len(_load_slot_texts(skeleton_path))


def _reprint_knobs_payload(asset: Path) -> dict:
    """Knob state for the Reprints tab: per-rarity targets, jitter, provenance,
    rates, and the un-jittered preview.

    ``preview_targets`` is the *un-jittered* resolution of the current knobs — the
    central per-rarity mix the run targets (the live run adds ``jitter_pct`` of
    random +/- on top). ``slot_count`` is how many slots a reprint could land on.
    """
    from mtgai.generation.reprint_knobs import RARITIES, REPRINT_RARITY_RATES, resolve_targets
    from mtgai.generation.reprint_selector import extract_set_config, load_reprint_knobs

    knobs = load_reprint_knobs(asset)
    slot_count = _reprint_slot_count(asset)
    skeleton_path = asset / "skeleton.json"
    set_size = (
        int(extract_set_config(skeleton_path).get("set_size", 0)) if skeleton_path.exists() else 0
    )
    preview = resolve_targets(knobs.model_copy(update={"jitter_pct": 0.0}), set_size)
    return {
        "knobs": {r: getattr(knobs, r) for r in RARITIES} | {"jitter_pct": knobs.jitter_pct},
        "provenance": knobs.provenance(),
        "rates": REPRINT_RARITY_RATES,
        "set_size": set_size,
        "slot_count": slot_count,
        "preview_targets": preview,
        "preview_count": sum(preview.values()),
    }


@router.get("/api/wizard/reprints/state")
async def wizard_reprints_state() -> JSONResponse:
    """First-paint state for the Reprints tab.

    Reads ``<asset>/reprint_selection.json`` (the LLM's picks + per-pick
    reasoning + the target count it was asked for), the count knob, and recomputes
    the pool / slot counts so the tab shows what was decided and why, surviving
    reloads. The reprints stage emits live tiles over SSE while it runs, but those
    are ephemeral — this endpoint is the durable source the tab bootstraps from.
    """
    _require_active_project()
    asset = set_artifact_dir()

    selection = _read_json(asset / "reprint_selection.json", {})
    selection = selection if isinstance(selection, dict) else {}
    selections = selection.get("selections") or []
    if not isinstance(selections, list):
        selections = []

    pool_size: int | None = None
    knobs_payload: dict = {}
    try:
        from mtgai.generation.reprint_selector import load_reprint_pool

        pool = load_reprint_pool()
        pool_size = sum(1 for c in pool if c.setting_agnostic is not False)
        knobs_payload = _reprint_knobs_payload(asset)
    except Exception:
        logger.warning("Failed to compute reprint pool/knob state", exc_info=True)

    return JSONResponse(
        {
            "selections": selections,
            "has_content": bool(selections),
            "pool_size": pool_size,
            "eligible_slots": knobs_payload.get("slot_count"),
            "target_count": selection.get("target_reprint_count"),
            "per_rarity_targets": selection.get("per_rarity_targets"),
            "stage_status": _stage_status_in_state("reprints"),
            **knobs_payload,
        }
    )


def _write_reprint_knobs(asset: Path, body: dict) -> None:
    """Validate + persist the tab's knob edits to ``<asset>/reprints/knobs.json``."""
    from mtgai.generation.reprint_knobs import RARITIES, from_payload

    knobs = from_payload(body.get("knobs") if isinstance(body.get("knobs"), dict) else body)
    out = {r: getattr(knobs, r) for r in RARITIES} | {"jitter_pct": knobs.jitter_pct}
    (asset / "reprints").mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        asset / "reprints" / "knobs.json", json.dumps(out, indent=2, ensure_ascii=False)
    )


@router.post("/api/wizard/reprints/knobs")
async def wizard_reprints_knobs(request: Request) -> JSONResponse:
    """Validate + persist the per-rarity reprint knobs. No AI — a pure disk write.

    Body: ``{knobs: {common, uncommon, rare, mythic, jitter_pct}}`` (a ``null``
    rarity = auto). Returns the clamped knobs + the un-jittered preview targets.
    The user then hits Refresh to re-run selection with these knobs.
    """
    _require_active_project()
    body, err = await _read_request_json(request)
    if err is not None:
        return err
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON body required"}, status_code=400)
    asset = set_artifact_dir()

    _write_reprint_knobs(asset, body)
    return JSONResponse({"success": True, **_reprint_knobs_payload(asset)})


@router.post("/api/wizard/reprints/refresh")
async def wizard_reprints_refresh(request: Request) -> JSONResponse:
    """Persist any supplied knobs, then re-run reprint selection under the AI lock.

    Body (optional): ``{knobs: {...}}`` — persisted first so the run uses the
    tab's current targets. Runs at a non-zero temperature so a manual re-roll
    surfaces alternative picks (the engine stage stays deterministic at temp 0).
    Writes ``reprint_selection.json`` and returns the same shape as ``/state``.
    """
    _require_active_project()
    body, err = await _read_request_json(request)
    if err is not None:
        return err
    asset = set_artifact_dir()

    skeleton_path = asset / "skeleton.json"
    if not skeleton_path.exists():
        return JSONResponse(
            {"error": "No skeleton.json yet — run Skeleton Generation first."}, status_code=400
        )
    if isinstance(body, dict) and isinstance(body.get("knobs"), dict):
        _write_reprint_knobs(asset, body)

    from mtgai.generation.reprint_selector import apply_selection_to_skeleton, select_reprints

    with guarded_ai("Reprint selection", stage_id="reprints") as guard:
        if guard.busy:
            return guard.busy_response
        with _bus_poller("reprints", activity_prefix="Selecting reprints"):
            result = await asyncio.to_thread(
                select_reprints, skeleton_path=skeleton_path, temperature=0.7
            )
        if ai_lock.is_cancelled():
            # A Cancel mid-run leaves `result` partial/empty — persisting it would
            # clobber the prior good reprint_selection.json + skeleton stamps, so
            # skip the write entirely and don't count the cancel as a recovery.
            guard.skip_heal = True
        else:
            atomic_write_text(
                asset / "reprint_selection.json",
                json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False),
            )
            # Stamp the picks into the skeleton (reset-then-stamp) so card-gen skips
            # them and the lands investigation sees an accurate unfilled-slot view. A
            # manual re-roll replaces the prior stamps cleanly. Kept inside the guard
            # so the persist + stamp run under the same lock that produced them.
            apply_selection_to_skeleton(skeleton_path, result)

    # On cancel nothing was written — return the preserved on-disk state instead of
    # the aborted (empty) result so the tab keeps showing the prior picks.
    if ai_lock.is_cancelled():
        return await wizard_reprints_state()

    selections = result.model_dump(mode="json")["selections"]
    knobs_payload = _reprint_knobs_payload(asset)
    return JSONResponse(
        {
            "success": True,
            "selections": selections,
            "has_content": bool(selections),
            "target_count": result.target_reprint_count,
            "per_rarity_targets": result.per_rarity_targets,
            "eligible_slots": knobs_payload.get("slot_count"),
            "stage_status": _stage_status_in_state("reprints"),
            **knobs_payload,
        }
    )


@router.get("/api/wizard/lands/state")
async def wizard_lands_state() -> JSONResponse:
    """First-paint state for the Lands tab.

    Reads the lands-stage card JSONs from ``<asset>/cards/`` — the 5 basics
    (``L-01``..``L-05``) plus the optional investigated dual (``L-06``) — and
    returns the simplified tile shape the tab renders. Land *cycles* are owned by
    card-gen (they appear on the Cards tab), so they're excluded here via the
    ``L-`` collector-number convention the lands stage uses. The stage emits live
    tiles over SSE while running; this endpoint is the durable source the tab
    bootstraps from on reload.
    """
    _require_active_project()
    asset = set_artifact_dir()

    cards_dir = asset / "cards"
    lands: list[dict] = []
    if cards_dir.exists():
        for path in sorted(cards_dir.glob("*.json")):
            card = _read_json(path, None)
            if not isinstance(card, dict):
                continue
            if not str(card.get("collector_number") or "").upper().startswith("L-"):
                continue
            lands.append(
                {
                    "name": card.get("name") or "",
                    "type_line": card.get("type_line") or "",
                    "rarity": card.get("rarity") or "",
                    "oracle_text": card.get("oracle_text") or "",
                    "flavor_text": card.get("flavor_text") or "",
                    "collector_number": card.get("collector_number") or "",
                    # The per-alternate art brief lives in design_notes
                    # ("Alternate basic land art — <scene>"); the tab surfaces it
                    # so the variant printings of a basic are visibly distinct.
                    "design_notes": card.get("design_notes") or "",
                }
            )

    return JSONResponse(
        {
            "lands": lands,
            "has_content": bool(lands),
            "stage_status": _stage_status_in_state("lands"),
        }
    )


@router.post("/api/wizard/lands/refresh")
async def wizard_lands_refresh() -> JSONResponse:
    """Manual re-roll of the lands stage under the AI lock — the engine runs this
    stage automatically, but the tab's Refresh button calls here.

    Re-runs ``generate_lands`` (basic-land alternate arts + the dual-land fixing
    investigation). Each run first clears the prior ``L-*`` card JSONs, so a
    refresh fully replaces the basics' alternates (the random per-type count +
    lettered collector numbers mean a fresh run can't reliably overwrite the old
    set in place). Returns the same shape as ``/state`` so the tab repaints from
    the freshly-written cards. Requires ``skeleton.json`` — lands read the set's
    fixing context from the skeleton's slots.
    """
    _require_active_project()
    asset = set_artifact_dir()

    skeleton_path = asset / "skeleton.json"
    if not skeleton_path.exists():
        return JSONResponse(
            {"error": "No skeleton.json yet — run Skeleton Generation first."}, status_code=400
        )

    from mtgai.generation.land_generator import generate_lands

    with guarded_ai("Land generation", stage_id="lands") as guard:
        if guard.busy:
            return guard.busy_response
        with _bus_poller("lands", activity_prefix="Designing lands"):
            result = await asyncio.to_thread(generate_lands)
        # A cancel isn't a recovery — leave a stuck FAILED stage as-is. (Lands
        # clears-then-writes its L-* cards, so a cancel leaves basics only; the
        # re-read below surfaces whatever was written.)
        if isinstance(result, dict) and result.get("cancelled"):
            guard.skip_heal = True
        else:
            # Keep the lands snapshot in step with the just-rewritten live pool so a
            # later backbone card_gen re-run restores the refreshed lands, not stale.
            _resnapshot_stage_tip("lands")

    # Re-read the freshly-written L-* cards into the tile shape (same source of
    # truth the tab bootstraps from), keeping the response shape DRY.
    return await wizard_lands_state()


def _is_land_stage_card(card: dict) -> bool:
    """True for a lands-stage basic/dual (collector number ``L-*``).

    Thin re-export of :func:`mtgai.pipeline.stages._is_land_stage_card` so the
    card_gen state/refresh endpoints and the cascade clearer share one
    definition of "what the Lands tab owns".
    """
    from mtgai.pipeline.stages import _is_land_stage_card as _impl

    return _impl(card)


def _heal_failed_stage(stage_id: str) -> None:
    """Clear a stuck FAILED stage after a successful manual recovery.

    When a stage fails (the engine's initial run hit an exception, e.g. the
    local model fixated on a printed-keyword name and exhausted its retry
    budget; a cancel returned ``success=False``; a server-restart interrupt),
    its status flips to FAILED and ``overall_status`` flips to FAILED. From
    there ``engine.resume()`` (which ``/api/wizard/advance`` calls) refuses
    to advance until the stage is PAUSED_FOR_REVIEW, so the Save & Continue
    button never appears in the wizard's footer — even after the user has
    hit Refresh AI / Re-pick / Save and populated valid output on disk.

    A successful manual recovery (refresh, re-pick, knob retune, edit, save)
    means the stage is healthy again: demote FAILED status → PAUSED_FOR_REVIEW
    (its natural "output ready, awaiting human" state) and flip overall_status
    FAILED → PAUSED. Persists + emits SSE so open tabs update without a reload.

    No-op when the stage is not failed — idempotent and cheap to call from
    every recovery-style endpoint. Every refresh / save / regenerate endpoint
    on every stage should call this after its successful write; see
    ``plans/wizard-tab-conventions.md`` § "Failed-stage recovery" for the
    convention.
    """
    from datetime import UTC, datetime

    state = _get_current_state()
    if state is None:
        return
    stage = next((s for s in state.stages if s.stage_id == stage_id), None)
    changed = False
    if stage is not None and stage.status == StageStatus.FAILED:
        stage.status = StageStatus.PAUSED_FOR_REVIEW
        stage.progress.error_message = None
        stage.progress.finished_at = datetime.now(UTC)
        changed = True
    if state.overall_status == PipelineStatus.FAILED:
        state.overall_status = PipelineStatus.PAUSED
        changed = True
    if not changed:
        return
    save_state(state)
    if stage is not None:
        event_bus.stage_update(
            stage_id,
            stage.status.value,
            stage.progress.model_dump(mode="json"),
            instance_id=stage.instance_id,
        )
    event_bus.pipeline_status(state.overall_status.value, state.current_instance_id)


def _resnapshot_stage_tip(stage_id: str) -> None:
    """Re-snapshot a stage's tip instance after a manual refresh rewrote the live pool.

    The engine snapshots each instance's output at completion, but a tab "Refresh"
    regenerates the live ``cards/`` afterward *without* going through the engine — so
    ``history/<instance_id>/`` would otherwise stay stale and a later
    ``rerun_instance`` would restore the pre-refresh pool (silent data loss).
    Snapshotting the stage's most-recent instance keeps history in step with the live
    pool the refresh just wrote. Best-effort; no-op for a non-snapshot stage.
    """
    from mtgai.pipeline import history

    if stage_id not in history.SNAPSHOT_STAGES:
        return
    state = load_state()
    if state is None:
        return
    inst = next((s for s in reversed(state.stages) if s.stage_id == stage_id), None)
    if inst is None:
        return
    try:
        history.snapshot_instance(inst.instance_id)
    except Exception:
        logger.exception("Re-snapshot after %s refresh failed (continuing)", stage_id)


def _resolve_view_cards_dir(instance_id: str | None, asset: Path) -> Path:
    """Cards dir a tab should read for ``instance_id``.

    Live ``cards/`` reflects the output of the loop *tip* — the last instance that
    has run. A completed *non-tip* instance reads its own output from
    ``history/<instance_id>/cards`` instead, which fixes the bug where an old
    card_gen tab (viewed after a later instance ran) showed the latest pool rather
    than its own. Falls back to live for the tip, a missing snapshot (migration),
    or no instance hint.
    """
    from mtgai.pipeline import history

    live = asset / "cards"
    if not instance_id:
        return live
    state = load_state()
    if state is None:
        return live
    ran = [
        s
        for s in state.stages
        if s.status in (StageStatus.RUNNING, StageStatus.PAUSED_FOR_REVIEW, StageStatus.COMPLETED)
    ]
    tip = ran[-1].instance_id if ran else None
    if instance_id == tip:
        return live
    snap = history.snapshot_dir(instance_id, asset) / "cards"
    return snap if snap.is_dir() else live


@router.get("/api/wizard/card_gen/state")
async def wizard_card_gen_state(instance_id: str | None = None) -> JSONResponse:
    """First-paint state for the Card Generation tab.

    Reads the card-gen-owned JSONs from ``<asset>/cards/`` (everything except the
    Lands tab's ``L-*`` basics/dual) into the tile shape the grid renders, plus
    set params and the persisted stage status. The stage emits live progress over
    SSE while running; this endpoint is the durable source the tab bootstraps from
    on reload and re-reads after a manual refresh.
    """
    project = _require_active_project()
    settings = project.settings
    asset = set_artifact_dir()

    # Load the skeleton once so each card tile gets the final relabeled
    # descriptor for its slot — the tab shows it under the card so you can
    # eyeball "did the card design fulfil the slot's brief?". Reserved-card
    # slots already land their request text in tweaked_text via the relabel's
    # Pass 2, so this single resolver covers them too.
    slots_by_id = slots_by_id_from_skeleton(asset / "skeleton.json")

    # Per-instance read-routing: a completed non-tip instance reads its own
    # snapshot under history/; the tip / in-flight instance reads the live pool.
    cards_dir = _resolve_view_cards_dir(instance_id, asset)
    cards: list[dict] = []
    if cards_dir.exists():
        for path in sorted(cards_dir.glob("*.json")):
            card = _read_json(path, None)
            if not isinstance(card, dict) or _is_land_stage_card(card):
                continue
            # Use the shared tile helper so this endpoint and the per-card SSE
            # stream emit byte-identical shapes — the tab merges streamed cards
            # into a list eventually repainted from this response, so any drift
            # would surface as layout flicker.
            cards.append(card_tile_dict(card, slots_by_id))

    return JSONResponse(
        {
            "cards": cards,
            "has_content": bool(cards),
            "set_params": settings.set_params.model_dump(),
            "stage_status": _stage_status_in_state("card_gen"),
        }
    )


@router.post("/api/wizard/card_gen/refresh")
async def wizard_card_gen_refresh() -> JSONResponse:
    """Regenerate the set's cards from scratch under the AI lock.

    The engine runs ``card_gen`` automatically; this is the tab's manual re-roll.
    Wipes the card-gen-owned card JSONs + ``generation_progress.json`` (the Lands
    tab's ``L-*`` cards are preserved), then regenerates every unfilled slot — a
    true from-scratch run (subject to the temporary ``TEMP_CARD_LIMIT`` cap).
    Per-batch progress streams over SSE (``item_progress``) so the tab's bar moves;
    returns the same shape as ``/state`` so the grid repaints. Requires
    ``skeleton.json``. A cancel from the progress strip stops it at the next batch
    boundary (``generate_set`` polls ``ai_lock.is_cancelled()``).
    """
    _require_active_project()
    asset = set_artifact_dir()

    skeleton_path = asset / "skeleton.json"
    if not skeleton_path.exists():
        return JSONResponse(
            {"error": "No skeleton.json yet — run Skeleton Generation first."}, status_code=400
        )

    from mtgai.generation.card_generator import generate_set
    from mtgai.pipeline.stages import clear_card_gen_cards

    with guarded_ai("Card generation", stage_id="card_gen") as guard:
        if guard.busy:
            return guard.busy_response

        # From-scratch: drop the prior card-gen cards + progress + regen archive
        # so every slot regenerates. The shared clearer keeps the Lands tab's L-*
        # basics/dual — a card-gen re-roll shouldn't cost the user their
        # separately-generated lands — so this stays in lock-step with the
        # cascade clearer (one definition, no drift).
        clear_card_gen_cards()

        def _on_progress(item: str, completed: int, total: int, detail: str, cost: float) -> None:
            event_bus.item_progress("card_gen", item, completed, total, detail)

        # Reuse the engine's card-gen stream hooks (``stage_hooks``) via a
        # refresh-path emitter so the streamed tile shape stays byte-identical
        # to /state and run_card_gen.
        emitter = _refresh_emitter("card_gen")

        # Tell the tab to drop its local card list before the new run streams
        # in (the cards/ dir was just wiped above — the SSE reset event is how
        # the client learns about it without a separate /state poll). Engine
        # path doesn't emit this: a first run already starts empty, a resume
        # must keep existing cards visible.
        emit_card_gen_reset(emitter)

        # Load the skeleton once so each streamed card tile gets the final
        # relabeled descriptor for its slot, same shape /state emits, then stream
        # each saved card to the tab as it lands so the grid pops in one card at
        # a time (same payload as /state → the client merge is a no-op on repaint).
        slots_by_id = slots_by_id_from_skeleton(skeleton_path)
        cg_hooks = build_card_gen_hooks(emitter, slots_by_id=slots_by_id)

        with _bus_poller("card_gen", activity_prefix="Generating cards"):
            result = await asyncio.to_thread(
                generate_set,
                progress_callback=_on_progress,
                card_saved_callback=cg_hooks.on_card_saved,
            )

        # A cancel isn't a recovery: suppress the guard's success-heal so a stuck
        # FAILED card_gen stays FAILED. A clean (non-cancelled) regen means the
        # stage is healthy, so the guard heals it and the failure modal stops.
        if isinstance(result, dict) and result.get("cancelled"):
            guard.skip_heal = True
        else:
            # The refresh rewrote the live pool without going through the engine;
            # re-snapshot this stage's tip so a later re-run restores the refreshed
            # pool, not the stale pre-refresh one.
            _resnapshot_stage_tip("card_gen")

    return await wizard_card_gen_state()


@router.get("/api/wizard/skeleton/state")
async def wizard_skeleton_state() -> JSONResponse:
    """First-paint state for the Skeleton tab.

    Returns each slot as its deterministic default descriptor + the LLM-relabeled
    ``tweaked_text`` (the tab diffs the two), plus whether the relabel has run,
    set params, theme excerpt, model id, and the skeleton stage status.
    """
    project = _require_active_project()
    settings = project.settings
    asset = set_artifact_dir()

    skeleton = _read_json(asset / "skeleton.json", {})
    raw = skeleton.get("slots") if isinstance(skeleton, dict) else None
    slots = [_skeleton_slot_view(s) for s in (raw or []) if isinstance(s, dict)]
    has_tweaked = any(
        isinstance(s, dict) and (s.get("tweaked_text") or "").strip() for s in (raw or [])
    )

    return JSONResponse(
        {
            "slots": slots,
            "has_tweaked": has_tweaked,
            **_stage_state_base("skeleton", settings),
            # Surfaced so the tab can warn after a reload that the last relabel
            # was kept partial. Persisted on skeleton.json by the stage/refresh.
            "incomplete": bool(skeleton.get("relabel_incomplete"))
            if isinstance(skeleton, dict)
            else False,
            "relabeled": int(skeleton.get("relabeled_slots", 0))
            if isinstance(skeleton, dict)
            else 0,
            **_skeleton_knobs_payload(skeleton if isinstance(skeleton, dict) else {}),
        }
    )


def _rebuild_skeleton_from_knobs(asset, skeleton: dict, knobs) -> dict:
    """Deterministically rebuild ``skeleton.json`` from new knobs, in place.

    Rebuilding changes the slot matrix, so the LLM relabel (``tweaked_text`` +
    request placements) is dropped — the tab tells the user to Refresh to
    re-theme. Returns the new skeleton dict (also written to disk).
    """
    from mtgai.skeleton.generator import SetConfig, generate_skeleton

    config_raw = skeleton.get("config") if isinstance(skeleton, dict) else None
    config = SetConfig.model_validate(config_raw) if isinstance(config_raw, dict) else None
    if config is None:
        raise ValueError("skeleton.json has no config to rebuild from")
    result = generate_skeleton(config, knobs=knobs)
    new_skeleton = result.model_dump(mode="json")
    atomic_write_text(
        asset / "skeleton.json", json.dumps(new_skeleton, indent=2, ensure_ascii=False)
    )
    return new_skeleton


def _skeleton_knobs_from_body(body: dict) -> tuple[SkeletonKnobs, list[str]]:
    """Overlay the Skeleton tab's knob-edit payload onto :class:`SkeletonKnobs`.

    The tab POSTs ``{knobs: {...}, cycles, pinned, provenance}``; both the
    deterministic rebuild (``/skeleton/knobs``) and the AI re-tune base
    (``/skeleton/knobs/tune``) read the same overlay shape. Returns the
    validated/clamped knobs + any clamp warnings (``SkeletonKnobs.from_payload``).
    """
    from mtgai.skeleton.knobs import SkeletonKnobs

    payload = dict(body.get("knobs") or {})
    payload["cycles"] = body.get("cycles", payload.get("cycles", []))
    payload["pinned"] = body.get("pinned", [])
    payload["provenance"] = body.get("provenance", {})
    return SkeletonKnobs.from_payload(payload)


@router.post("/api/wizard/skeleton/knobs")
async def wizard_skeleton_knobs(request: Request) -> JSONResponse:
    """Validate edited knobs and rebuild the default skeleton deterministically.

    Body: ``{knobs: {...}, provenance: {...}, pinned: [...]}``. The knobs are
    validated/clamped through :class:`SkeletonKnobs` (so a hand-typed value can
    never produce an illegal skeleton), then ``generate_skeleton`` rebuilds the
    matrix. No AI lock — a pure deterministic rebuild. The relabel is dropped;
    the client then hits Refresh to re-theme. Returns the new slots + knobs +
    any clamp warnings.
    """
    _require_active_project()
    body, err = await _read_request_json(request)
    if err is not None:
        return err
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON body required"}, status_code=400)
    asset = set_artifact_dir()

    skeleton = _read_json(asset / "skeleton.json", {})
    if not isinstance(skeleton, dict) or not skeleton.get("slots"):
        return JSONResponse(
            {"error": "No skeleton.json yet — run Skeleton Generation first."}, status_code=400
        )

    knobs, warnings = _skeleton_knobs_from_body(body)
    try:
        new_skeleton = _rebuild_skeleton_from_knobs(asset, skeleton, knobs)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    logger.info("Skeleton knobs applied (rebuilt %d slots)", len(new_skeleton.get("slots", [])))
    return JSONResponse(
        {
            "success": True,
            "slots": [_skeleton_slot_view(s) for s in new_skeleton.get("slots", [])],
            "warnings": warnings + list(new_skeleton.get("knob_warnings", [])),
            **_skeleton_knobs_payload(new_skeleton),
        }
    )


@router.post("/api/wizard/skeleton/knobs/tune")
async def wizard_skeleton_knobs_tune(request: Request) -> JSONResponse:
    """Re-run the phase-0 LLM knob tuner, respecting pinned knobs, then rebuild.

    Body (optional): ``{knobs, cycles, pinned, provenance}`` — the tab's current
    knob values, used as the tuner's base so unsaved hand-edits + pins survive the
    re-roll. When absent (or empty) the persisted ``skeleton.json`` knobs are the
    base. Holds the AI lock (it is an LLM call). On any tuner failure the base (or
    defaults) is used — never a hard error. Returns the rebuilt slots + the
    freshly-tuned knobs; the client then cascades into the relabel.
    """
    from mtgai.generation.skeleton_knobs_tuner import tune_skeleton_knobs
    from mtgai.skeleton.knobs import SkeletonKnobs

    _require_active_project()
    body, err = await _read_request_json(request)
    if err is not None:
        return err
    asset = set_artifact_dir()

    skeleton = _read_json(asset / "skeleton.json", {})
    if not isinstance(skeleton, dict) or not skeleton.get("slots"):
        return JSONResponse(
            {"error": "No skeleton.json yet — run Skeleton Generation first."}, status_code=400
        )
    # Tuner base: the tab's live knob values (so pins + hand-edits are honored)
    # when supplied, else the persisted skeleton knobs.
    knobs_body = body.get("knobs") if isinstance(body, dict) else None
    if isinstance(knobs_body, dict) and knobs_body:
        base, _ = _skeleton_knobs_from_body(body)
    else:
        raw = skeleton.get("knobs")
        base = SkeletonKnobs.model_validate(raw) if isinstance(raw, dict) else SkeletonKnobs()

    with guarded_ai("Skeleton knob tuning", stage_id="skeleton") as guard:
        if guard.busy:
            return guard.busy_response
        with _bus_poller("skeleton", activity_prefix="Tuning skeleton knobs"):
            knobs, meta = await asyncio.to_thread(tune_skeleton_knobs, base=base)
        new_skeleton = _rebuild_skeleton_from_knobs(asset, skeleton, knobs)

    return JSONResponse(
        {
            "success": True,
            "slots": [_skeleton_slot_view(s) for s in new_skeleton.get("slots", [])],
            "defaulted": bool(meta.get("defaulted")),
            "model_id": meta.get("model_id"),
            "warnings": list(new_skeleton.get("knob_warnings", [])),
            **_skeleton_knobs_payload(new_skeleton),
        }
    )


@router.post("/api/wizard/skeleton/refresh")
async def wizard_skeleton_refresh() -> JSONResponse:
    """Re-run the LLM relabel over the current default skeleton.

    Reads ``skeleton.json``'s structured slots (the deterministic default),
    re-runs ``relabel_skeleton`` (Pass 1 relabel + Pass 2 request placement),
    writes the fresh ``tweaked_text`` + ``reserved_card`` back, and returns the
    updated slot views. The relabel streams each slot live via ``skeleton_slot``
    / ``skeleton_relabel_reset`` SSE events while it runs; this response is the
    authoritative final state the tab reconciles to. Holds the AI lock; the §13
    recovery path when the stage produced no tweaks.
    """
    from mtgai.generation.skeleton_relabel import relabel_skeleton

    _require_active_project()
    asset = set_artifact_dir()

    skeleton = _read_json(asset / "skeleton.json", {})
    if not isinstance(skeleton, dict) or not skeleton.get("slots"):
        return JSONResponse(
            {"error": "No skeleton.json yet — run Skeleton Generation first."}, status_code=400
        )

    with guarded_ai("Skeleton relabel", stage_id="skeleton") as guard:
        if guard.busy:
            return guard.busy_response
        # Reuse the engine's relabel stream hooks (``stage_hooks``) via a
        # refresh-path emitter so the streamed slot/reset/done payloads stay
        # identical to run_skeleton. on_progress stays a plain stage_phase tick
        # (it drives the strip's activity line, not the tab's live slot view).
        sk_emitter = _refresh_emitter("skeleton")
        sk_hooks = build_skeleton_hooks(sk_emitter)
        try:
            # emit_done=False: the manual finally below already emits the single
            # terminal "done" (it also covers the cloud/NullPoller case).
            with _bus_poller("skeleton", activity_prefix="Relabeling skeleton", emit_done=False):
                relabel = await asyncio.to_thread(
                    relabel_skeleton,
                    slots=skeleton["slots"],
                    # Drive the progress strip's activity line ("attempt N/M") from
                    # the relabel's retry loop. Runs in the worker thread; the bus
                    # is thread-safe.
                    on_progress=lambda msg: event_bus.stage_phase("skeleton", "running", msg),
                    on_slot=sk_hooks.on_slot,
                    on_reset=sk_hooks.on_reset,
                )
        finally:
            # Terminal phase so the strip clears even on SSE replay, error or
            # success — this path emits no pipeline_status terminal event of its
            # own; the guard renders any worker error as the 500 envelope.
            event_bus.stage_phase("skeleton", "done", "")
        if ai_lock.is_cancelled():
            # A Cancel mid-relabel leaves a partial/empty result — applying it would
            # clobber the prior themed tweaked_text with defaults, so skip the apply
            # + persist entirely (the prior skeleton on disk stays intact) and don't
            # count the cancel as a recovery.
            guard.skip_heal = True
        else:
            updates = relabel["updates"]
            for slot in skeleton["slots"]:
                upd = updates.get(slot.get("slot_id"))
                if not upd:
                    continue
                slot["tweaked_text"] = upd.get("tweaked_text")
                # Replace (don't union) — a re-roll fully recomputes request
                # placements, so a slot the new run didn't place must lose its prior
                # "specially requested card" tag. reserved_card is only ever set by
                # the relabel's Pass 2 (the deterministic skeleton never stamps it),
                # so there's no generator-anchor value to preserve here.
                slot["reserved_card"] = upd.get("reserved_card")
            # Persist the relabel outcome so a reload still shows the incomplete warning.
            skeleton["relabel_incomplete"] = bool(relabel.get("incomplete"))
            skeleton["relabeled_slots"] = int(relabel.get("relabeled", 0))
            atomic_write_text(
                asset / "skeleton.json", json.dumps(skeleton, indent=2, ensure_ascii=False)
            )
            # Terminal stream event (mirrors the engine path) so the live view
            # settles even if these events are later replayed from the bus buffer.
            emit_skeleton_done(
                sk_emitter,
                incomplete=bool(relabel.get("incomplete")),
                relabeled=int(relabel.get("relabeled", 0)),
            )
        # The guard heals a stuck FAILED skeleton stage on a clean exit.

    # On cancel nothing was applied — return the preserved prior slots so the tab
    # reverts its live (partial) view to what's on disk.
    if ai_lock.is_cancelled():
        return await wizard_skeleton_state()

    return JSONResponse(
        {
            "success": True,
            "slots": [_skeleton_slot_view(s) for s in skeleton["slots"]],
            "model_id": relabel.get("model_id"),
            "incomplete": bool(relabel.get("incomplete")),
            "relabeled": int(relabel.get("relabeled", 0)),
        }
    )


@router.post("/api/wizard/skeleton/save")
async def wizard_skeleton_save(request: Request) -> JSONResponse:
    """Persist edited tweaked descriptors and report the next stage.

    Body: ``{slots: [{slot_id, tweaked_text}]}`` — the relabeled descriptors with
    any inline edits. Updates each matching slot's ``tweaked_text`` in
    ``skeleton.json`` (structured fields untouched) and returns
    ``{success, navigate_to}`` pointing at the stage after ``skeleton``
    (``reprints``). The client follows up with ``POST /api/wizard/advance``.
    No AI lock — a pure disk write.
    """
    _require_active_project()
    body, err = await _read_request_json(request)
    if err is not None:
        return err
    if not isinstance(body, dict):
        return JSONResponse({"error": "JSON body required"}, status_code=400)
    raw = body.get("slots")
    if not isinstance(raw, list) or not raw:
        return JSONResponse({"error": "slots must be a non-empty list"}, status_code=400)

    edits: dict[str, str] = {}
    for s in raw:
        if not isinstance(s, dict):
            return JSONResponse({"error": "each slot must be an object"}, status_code=400)
        sid = str(s.get("slot_id") or "").strip()
        text = str(s.get("tweaked_text") or "").strip()
        if not sid or not text:
            return JSONResponse(
                {"error": f"slot {sid or '?'} needs a non-empty tweaked descriptor"},
                status_code=400,
            )
        edits[sid] = text

    asset = set_artifact_dir()

    skeleton = _read_json(asset / "skeleton.json", {})
    if not isinstance(skeleton, dict) or not skeleton.get("slots"):
        return JSONResponse({"error": "No skeleton.json to save into."}, status_code=400)
    for slot in skeleton["slots"]:
        text = edits.get(slot.get("slot_id"))
        if text is not None:
            slot["tweaked_text"] = text
    atomic_write_text(asset / "skeleton.json", json.dumps(skeleton, indent=2, ensure_ascii=False))
    logger.info("Skeleton save: %d edited descriptors → %s", len(edits), asset / "skeleton.json")
    _heal_failed_stage("skeleton")

    return JSONResponse({"success": True, "navigate_to": _next_stage_nav("skeleton")})


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

    body, err = await _read_request_json(request)
    if err is not None:
        return err
    config = PipelineConfig(**body)

    # Check for existing state — allow resume from previous run
    existing = load_state()
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

    set_dir = set_artifact_dir()

    # Map stage_id to likely log locations
    log_paths: dict[str, list[Path]] = {
        "mechanics": [set_dir / "mechanics" / "logs"],
        "card_gen": [set_dir / "card_gen" / "logs"],
        "ai_review": [set_dir / "reviews"],
        "conformance": [set_dir / "conformance" / "logs"],
        "art_prompts": [set_dir / "art-direction" / "prompt-logs"],
        "art_select": [set_dir / "art-direction" / "selections"],
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
    """Get the current pipeline state, preferring in-memory engine state.

    Falls back to the active project's persisted ``pipeline-state.json``
    when no engine is running in this process. With no project loaded
    (or the persisted file unreachable) returns ``None``.
    """
    global _engine
    if _engine is not None:
        return _engine.state

    if active_project.read_active_project() is None:
        return None
    try:
        return load_state()
    except NoAssetFolderError:
        return None
    except Exception:
        logger.warning("Skipping unparseable pipeline-state.json for active project")
        return None


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
        # The instance/tab id of the live stage (== stage_id for backbone), so
        # the client can highlight the right tab even for an inserted instance.
        "current_stage_id": current.instance_id if current else None,
        "total_cost_usd": state.total_cost_usd,
        "run_id": state.run_id,
    }
