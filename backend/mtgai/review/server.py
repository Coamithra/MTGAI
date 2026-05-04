"""FastAPI review server — local dev tool for reviewing MTG AI card sets.

Serves the review gallery, handles review submissions, and provides
progress/booster APIs. Localhost-only, no auth, no CORS.

Start via CLI:
    python -m mtgai.review serve --set ASD --port 8080

Or directly:
    uvicorn mtgai.review.server:app --host 127.0.0.1 --port 8080
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from mtgai.pipeline.server import api_router as pipeline_api_router
from mtgai.pipeline.server import get_pipeline_banner_context
from mtgai.pipeline.server import router as pipeline_router

if TYPE_CHECKING:
    from mtgai.models.card import Card

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _project_root() -> Path:
    """Return the project root (parent of backend/)."""
    # server.py -> review/ -> mtgai/ -> backend/ -> PROJECT_ROOT
    return Path(__file__).resolve().parent.parent.parent.parent


def _templates_dir() -> Path:
    """Return the path to the gallery Jinja2 templates."""
    return Path(__file__).resolve().parent.parent / "gallery" / "templates"


def _static_dir() -> Path:
    """Return the path to the static assets directory."""
    return _templates_dir() / "static"


class NoCacheStaticFiles(StaticFiles):
    # Browsers heavily cache JS/CSS; that hides server-side renames until a
    # hard refresh. Force revalidation so dev edits land on next reload.
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


def _set_dir(set_code: str) -> Path:
    """Return the output directory for a set code."""
    return _project_root() / "output" / "sets" / set_code


def _get_set_code() -> str:
    """Resolve the active set code via the runtime-state chain.

    Reuses the same resolver the ``/api/runtime/state`` endpoint uses
    so the review/booster/progress pages pick up the picker-persisted
    set without a separate code path. Falls through to the env var and
    "ASD" defaults inside the resolver.
    """
    from mtgai.runtime.runtime_state import _resolve_active_set_code

    return _resolve_active_set_code(None)


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncGenerator[None]:
    """Mount render and art directories as static file servers on startup.

    This allows the gallery to load card images via /renders/... and /art/...
    instead of relative file paths.
    """
    from mtgai.settings.model_settings import get_settings

    # Eagerly load the last-applied model settings (output/settings/current.toml)
    # so they are in effect before any request arrives. get_settings() is a
    # lazy singleton; calling it here just forces the load + log up front.
    settings = get_settings()
    logger.info(
        "Active model settings: %s",
        {k: v for k, v in settings.llm_assignments.items()},
    )

    set_code = _get_set_code()
    set_dir = _set_dir(set_code)

    renders_dir = set_dir / "renders"
    if renders_dir.exists():
        application.mount("/renders", StaticFiles(directory=str(renders_dir)), name="renders")
        logger.info("Mounted renders directory: %s", renders_dir)

    art_dir = set_dir / "art"
    if art_dir.exists():
        application.mount("/art", StaticFiles(directory=str(art_dir)), name="art")
        logger.info("Mounted art directory: %s", art_dir)

    yield


app = FastAPI(title="MTGAI Review Server", lifespan=_lifespan)

# Mount static assets (CSS, JS)
app.mount("/static", NoCacheStaticFiles(directory=str(_static_dir())), name="static")

# Jinja2 templates
templates = Jinja2Templates(directory=str(_templates_dir()))

# Mount pipeline routes
app.include_router(pipeline_router)
app.include_router(pipeline_api_router)

# Inject pipeline banner context into all Jinja2 templates
templates.env.globals["pipeline_banner"] = None  # default


@app.middleware("http")
async def inject_pipeline_banner(request: Request, call_next):
    """Inject pipeline banner context for Jinja2 templates on each request."""
    templates.env.globals["pipeline_banner"] = get_pipeline_banner_context()
    response = await call_next(request)
    return response


# ---------------------------------------------------------------------------
# Card serialization helper
# ---------------------------------------------------------------------------


def _discover_images(set_code: str) -> tuple[dict[str, str], dict[str, str]]:
    """Discover render and art files on disk, keyed by collector number.

    Falls back to filesystem glob when card JSONs don't have paths populated.
    Returns (render_map, art_map) where values are server route paths.
    """
    set_dir = _set_dir(set_code)
    render_map: dict[str, str] = {}
    art_map: dict[str, str] = {}

    renders_dir = set_dir / "renders"
    if renders_dir.exists():
        for f in renders_dir.glob("*.png"):
            # Filename pattern: <collector_number>_<slug>.png
            # collector_number uses dashes: W-C-01, B-M-01, etc.
            parts = f.stem.split("_", 1)
            if len(parts) >= 1:
                # Reconstruct collector number from the prefix
                # Files like "W-C-01_guardian_of_threshold.png"
                collector = parts[0]
                # Handle cases like "B-C-01" (3 parts joined by dash)
                # The slug starts after the first underscore
                render_map[collector] = f"/renders/{f.name}"

    art_dir = set_dir / "art"
    if art_dir.exists():
        # Collect all art files per collector, pick highest version
        art_versions: dict[str, list[Path]] = {}
        for f in sorted(art_dir.glob("*.png")):
            collector = f.stem.split("_", 1)[0]
            if collector not in art_versions:
                art_versions[collector] = []
            art_versions[collector].append(f)
        for collector, files in art_versions.items():
            # Last sorted file = highest version (v1 < v2 < v3)
            art_map[collector] = f"/art/{files[-1].name}"

    return render_map, art_map


# Module-level cache for image discovery (refreshed per request cycle)
_image_cache: dict[str, tuple[dict[str, str], dict[str, str]]] = {}


def _get_image_maps(set_code: str, refresh: bool = False) -> tuple[dict[str, str], dict[str, str]]:
    """Get image maps, discovering from disk on first call or refresh."""
    if refresh or set_code not in _image_cache:
        _image_cache[set_code] = _discover_images(set_code)
    return _image_cache[set_code]


def _card_to_server_dict(card: Card, render_map: dict[str, str], art_map: dict[str, str]) -> dict:
    """Convert a Card model to a dict for the server JSON.

    Image paths are resolved from card JSON first, then discovered from disk.
    """

    d: dict = {
        "collector_number": card.collector_number,
        "name": card.name,
        "mana_cost": card.mana_cost,
        "cmc": card.cmc,
        "colors": [c.value for c in card.colors],
        "color_identity": [c.value for c in card.color_identity],
        "type_line": card.type_line,
        "oracle_text": card.oracle_text,
        "flavor_text": card.flavor_text,
        "power": card.power,
        "toughness": card.toughness,
        "rarity": card.rarity.value,
        "set_code": card.set_code,
        "render_path": None,
        "art_path": None,
        "mechanic_tags": list(card.mechanic_tags),
        "slot_id": card.slot_id,
        "is_reprint": card.is_reprint,
    }

    # Try card JSON paths first, then fall back to disk discovery
    if card.render_path:
        render_filename = Path(card.render_path).name
        d["render_path"] = f"/renders/{render_filename}"
    elif card.collector_number in render_map:
        d["render_path"] = render_map[card.collector_number]

    if card.art_path:
        art_filename = Path(card.art_path).name
        d["art_path"] = f"/art/{art_filename}"
    elif card.collector_number in art_map:
        d["art_path"] = art_map[card.collector_number]

    return d


def _load_cards_as_json(set_code: str) -> tuple[list[dict], str]:
    """Load all cards and return (list of dicts, JSON string).

    Returns:
        Tuple of (card dicts list, JSON string for template injection).
    """
    from mtgai.review.loaders import load_cards

    cards = load_cards(set_code)
    render_map, art_map = _get_image_maps(set_code)
    card_dicts = [_card_to_server_dict(c, render_map, art_map) for c in cards]
    cards_json = json.dumps(card_dicts, ensure_ascii=False)
    return card_dicts, cards_json


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=RedirectResponse)
async def root() -> RedirectResponse:
    """Redirect to review page."""
    return RedirectResponse(url="/review")


@app.get("/review", response_class=HTMLResponse)
async def review_page(request: Request, set_code: str | None = None) -> HTMLResponse:
    """Serve the review gallery page.

    Loads all cards, serializes to JSON, passes to the review.html template.
    """
    if set_code is None:
        set_code = _get_set_code()

    from mtgai.review.decisions import get_review_round

    _, cards_json = _load_cards_as_json(set_code)
    current_round = get_review_round(set_code)

    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "set_code": set_code,
            "cards_json": cards_json,
            "review_round": current_round,
        },
    )


@app.get("/progress", response_class=HTMLResponse)
async def progress_page(request: Request, set_code: str | None = None) -> HTMLResponse:
    """Serve the progress tracking page.

    Shows pending/completed/error status for all non-OK cards.
    """
    if set_code is None:
        set_code = _get_set_code()

    from mtgai.review.decisions import load_progress

    progress = load_progress(set_code)
    progress_json = progress.model_dump_json() if progress else "{}"

    return templates.TemplateResponse(
        request,
        "progress.html",
        {
            "set_code": set_code,
            "progress_json": progress_json,
        },
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    """Serve the model settings configuration page."""
    from mtgai.settings.model_registry import get_registry
    from mtgai.settings.model_settings import (
        IMAGE_STAGE_NAMES,
        LLM_STAGE_NAMES,
        PRESETS,
        get_settings,
        list_profiles,
    )

    registry = get_registry()
    settings = get_settings()

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "model_registry": json.dumps(registry.to_dict()),
            "current_settings": json.dumps(settings.model_dump()),
            "saved_profiles": json.dumps(list_profiles()),
            "llm_stages": json.dumps(LLM_STAGE_NAMES),
            "image_stages": json.dumps(IMAGE_STAGE_NAMES),
            "presets": json.dumps(PRESETS),
        },
    )


@app.get("/booster", response_class=HTMLResponse)
async def booster_page(request: Request, set_code: str | None = None) -> HTMLResponse:
    """Serve the booster pack viewer page."""
    if set_code is None:
        set_code = _get_set_code()

    _, cards_json = _load_cards_as_json(set_code)

    return templates.TemplateResponse(
        request,
        "booster.html",
        {
            "set_code": set_code,
            "cards_json": cards_json,
        },
    )


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


@app.post("/api/review/submit", response_class=JSONResponse)
async def submit_review(request: Request, set_code: str | None = None) -> JSONResponse:
    """Handle review submission.

    Receives decisions JSON, saves to disk, dispatches to pipelines.
    Returns summary of what was dispatched.

    Request body:
        {"decisions": {"W-C-01": {"action": "ok", "note": ""}, ...}}
    """
    if set_code is None:
        set_code = _get_set_code()

    from mtgai.review.decisions import (
        CardDecision,
        ReviewDecisions,
        dispatch_decisions,
        get_review_round,
        init_progress,
        save_decisions,
        save_progress,
    )

    body = await request.json()
    raw_decisions = body.get("decisions", {})

    # Parse into Pydantic models
    card_decisions: dict[str, CardDecision] = {}
    for cn, data in raw_decisions.items():
        card_decisions[cn] = CardDecision(
            action=data.get("action", "ok"),
            note=data.get("note", ""),
        )

    review_round = get_review_round(set_code)

    decisions = ReviewDecisions(
        set_code=set_code,
        review_round=review_round,
        timestamp=datetime.now(tz=UTC),
        decisions=card_decisions,
    )

    # Save decisions to disk
    save_decisions(decisions, set_code)

    # Dispatch — write queue files for downstream pipelines
    dispatch_result = dispatch_decisions(decisions)

    # Init progress tracking for non-OK cards
    progress = init_progress(decisions)
    save_progress(progress, set_code)

    # Build summary response
    summary = decisions.summary
    manual_paths = [str(p) for p in dispatch_result.manual_tweak_paths]

    # Open manual tweak JSON files in the system editor
    if dispatch_result.manual_tweak_paths:
        import os
        import sys

        for p in dispatch_result.manual_tweak_paths:
            if p.exists():
                if sys.platform == "win32":
                    os.startfile(str(p))
                elif sys.platform == "darwin":
                    import subprocess

                    subprocess.Popen(["open", str(p)])
                else:
                    import subprocess

                    subprocess.Popen(["xdg-open", str(p)])

    return JSONResponse(
        {
            "success": True,
            "review_round": review_round,
            "summary": summary,
            "remake_count": dispatch_result.remake_count,
            "art_redo_count": dispatch_result.art_redo_count,
            "manual_tweak_paths": manual_paths,
        }
    )


@app.get("/api/cards", response_class=JSONResponse)
async def get_cards(set_code: str | None = None) -> JSONResponse:
    """Return all cards as JSON (for client-side use)."""
    if set_code is None:
        set_code = _get_set_code()

    card_dicts, _ = _load_cards_as_json(set_code)
    return JSONResponse(card_dicts)


@app.get("/api/progress", response_class=JSONResponse)
async def get_progress(set_code: str | None = None) -> JSONResponse:
    """Return current progress as JSON (for polling)."""
    if set_code is None:
        set_code = _get_set_code()

    from mtgai.review.decisions import load_progress

    progress = load_progress(set_code)
    if progress is None:
        return JSONResponse({"cards": {}, "summary": {}})

    return JSONResponse(progress.model_dump(mode="json"))


@app.post("/api/progress/reload-manual", response_class=JSONResponse)
async def reload_manual_edits(set_code: str | None = None) -> JSONResponse:
    """Re-read card JSONs for manual tweak cards.

    Finds cards marked as manual_tweak in the current decisions,
    re-reads their JSON files, re-runs validation, and marks them
    as completed in progress.
    """
    if set_code is None:
        set_code = _get_set_code()

    from mtgai.review.decisions import (
        ReviewAction,
        load_decisions,
        load_progress,
        save_progress,
    )
    from mtgai.review.loaders import load_cards

    decisions = load_decisions(set_code)
    progress = load_progress(set_code)

    if decisions is None or progress is None:
        return JSONResponse(
            {"success": False, "error": "No decisions or progress found."},
            status_code=404,
        )

    # Find manual_tweak cards
    manual_cns = [
        cn for cn, d in decisions.decisions.items() if d.action == ReviewAction.MANUAL_TWEAK
    ]

    if not manual_cns:
        return JSONResponse({"success": True, "updated": [], "cards": []})

    # Re-read all cards from disk
    all_cards = load_cards(set_code)
    card_by_cn = {c.collector_number: c for c in all_cards}

    updated: list[str] = []
    updated_cards: list[dict] = []

    for cn in manual_cns:
        card = card_by_cn.get(cn)
        if card is None:
            logger.warning("Manual tweak card %s not found on disk", cn)
            continue

        # Mark as completed in progress
        if cn in progress.cards:
            progress.cards[cn].status = "completed"
            updated.append(cn)

        r_map, a_map = _get_image_maps(set_code)
        updated_cards.append(_card_to_server_dict(card, r_map, a_map))

    # Save updated progress
    save_progress(progress, set_code)

    return JSONResponse(
        {
            "success": True,
            "updated": updated,
            "cards": updated_cards,
        }
    )


# ---------------------------------------------------------------------------
# Settings API routes
# ---------------------------------------------------------------------------


@app.post("/api/settings/apply", response_class=JSONResponse)
async def apply_settings(request: Request) -> JSONResponse:
    """Apply model settings as the active configuration."""
    from mtgai.settings.model_settings import ModelSettings
    from mtgai.settings.model_settings import apply_settings as _apply

    body = await request.json()
    try:
        settings = ModelSettings(**body)
        _apply(settings)
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/settings/save", response_class=JSONResponse)
async def save_settings_profile(request: Request) -> JSONResponse:
    """Save model settings as a named profile."""
    from mtgai.settings.model_settings import ModelSettings

    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return JSONResponse({"error": "Profile name required"}, status_code=400)

    try:
        settings = ModelSettings(**body.get("settings", {}))
        path = settings.save(name=name)
        return JSONResponse({"success": True, "path": str(path)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/settings/load", response_class=JSONResponse)
async def load_settings_profile(name: str) -> JSONResponse:
    """Load a named settings profile."""
    from mtgai.settings.model_settings import SETTINGS_DIR, ModelSettings

    path = SETTINGS_DIR / f"{name}.toml"
    if not path.exists():
        return JSONResponse({"error": f"Profile '{name}' not found"}, status_code=404)

    try:
        settings = ModelSettings.load_from_file(path)
        return JSONResponse({"settings": settings.model_dump()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/booster", response_class=JSONResponse)
async def get_booster(set_code: str | None = None, seed: int | None = None) -> JSONResponse:
    """Generate and return a random booster pack."""
    if set_code is None:
        set_code = _get_set_code()

    from mtgai.packs import generate_booster_pack
    from mtgai.review.loaders import load_cards

    cards = load_cards(set_code)
    if not cards:
        return JSONResponse(
            {"error": "No cards found for set."},
            status_code=404,
        )

    try:
        pack = generate_booster_pack(cards, seed=seed)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    r_map, a_map = _get_image_maps(set_code)
    pack_dicts = [_card_to_server_dict(c, r_map, a_map) for c in pack]
    return JSONResponse(pack_dicts)
