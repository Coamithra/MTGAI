"""FastAPI server for the MTGAI wizard. Localhost-only, no auth, no CORS.

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


def _set_dir() -> Path:
    """Return the active project's artifact directory.

    Routes through :func:`set_artifact_dir` so reads honour the
    project's configured ``asset_folder``.
    """
    from mtgai.io.asset_paths import set_artifact_dir

    return set_artifact_dir()


def _get_set_code() -> str | None:
    """Resolve the active set code, or ``None`` if no project is open."""
    from mtgai.runtime.runtime_state import resolve_active_set_code

    return resolve_active_set_code()


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncGenerator[None]:
    """Boot tasks: clean up stale pipeline state.

    The active-project pointer is in-memory and a fresh process boots
    with no project loaded — the user has to click New / Open to pick
    up where they left off (the .mtg file is the only persistent
    project artifact). Render / art directories are no longer mounted
    at startup because we don't know which project to mount until one
    is opened; lazy mounting on first open is deferred to a follow-up
    once assets actually live in the asset folder.
    """
    from mtgai.pipeline.engine import cleanup_orphan_running_stages

    # Any pipeline-state.json with a RUNNING stage on disk was left
    # there by a process that exited mid-stage. Demote those to
    # FAILED so the wizard surfaces a Retry instead of a stuck spinner.
    cleanup_orphan_running_stages()

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


def _discover_images() -> tuple[dict[str, str], dict[str, str]]:
    """Discover render and art files in the active project, keyed by collector number.

    Falls back to filesystem glob when card JSONs don't have paths populated.
    Returns (render_map, art_map) where values are server route paths.
    """
    set_dir = _set_dir()
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


# Module-level cache for image discovery, keyed by the active project's
# set_code so opening a different project doesn't pick up stale maps.
_image_cache: dict[str, tuple[dict[str, str], dict[str, str]]] = {}


def _get_image_maps(refresh: bool = False) -> tuple[dict[str, str], dict[str, str]]:
    """Get image maps for the active project, discovering from disk on first call or refresh."""
    set_code = _get_set_code() or ""
    if refresh or set_code not in _image_cache:
        _image_cache[set_code] = _discover_images()
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
    render_map, art_map = _get_image_maps()
    card_dicts = [_card_to_server_dict(c, render_map, art_map) for c in cards]
    cards_json = json.dumps(card_dicts, ensure_ascii=False)
    return card_dicts, cards_json


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=RedirectResponse)
async def root() -> RedirectResponse:
    """Redirect to the wizard."""
    return RedirectResponse(url="/pipeline")


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    """Serve the cross-set defaults page (default preset + profiles + registry).

    Per-stage assignments live on the per-set Project Settings tab now;
    this page only owns user-level defaults and the saved-profile library.
    """
    from mtgai.settings.model_registry import get_registry
    from mtgai.settings.model_settings import (
        PRESETS,
        get_global_settings,
        list_profiles,
    )

    registry = get_registry()
    glob = get_global_settings()

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "model_registry": registry.to_dict(),
            "default_preset": glob.default_preset,
            "builtin_presets": sorted(PRESETS),
            "saved_profiles": list_profiles(),
        },
    )


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


@app.get("/api/cards", response_class=JSONResponse)
async def get_cards() -> JSONResponse:
    """Return all cards in the active project as JSON (for client-side use)."""
    from mtgai.io.asset_paths import NoAssetFolderError

    set_code = _get_set_code()
    if set_code is None:
        return JSONResponse(
            {"error": "No project is open", "code": "no_active_project"},
            status_code=409,
        )

    try:
        card_dicts, _ = _load_cards_as_json(set_code)
    except NoAssetFolderError as exc:
        return JSONResponse(
            {"error": str(exc), "code": "no_asset_folder"},
            status_code=409,
        )
    return JSONResponse(card_dicts)


# ---------------------------------------------------------------------------
# Settings API routes
# ---------------------------------------------------------------------------


@app.post("/api/settings/apply", response_class=JSONResponse)
async def apply_settings(request: Request) -> JSONResponse:
    """Apply model settings as the active configuration for the open project."""
    from mtgai.settings.model_settings import ModelSettings
    from mtgai.settings.model_settings import apply_settings as _apply

    set_code = _get_set_code()
    if set_code is None:
        return JSONResponse(
            {"error": "No project is open", "code": "no_active_project"},
            status_code=409,
        )

    body = await request.json()
    try:
        settings = ModelSettings(**body)
        _apply(set_code, settings)
        return JSONResponse({"success": True, "set_code": set_code})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/settings/save", response_class=JSONResponse)
async def save_settings_profile(request: Request) -> JSONResponse:
    """Save model settings as a named profile in the global library."""
    from mtgai.settings.model_settings import ModelSettings

    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return JSONResponse({"error": "Profile name required"}, status_code=400)

    try:
        settings = ModelSettings(**body.get("settings", {}))
        path = settings.save_profile(name=name)
        return JSONResponse({"success": True, "path": str(path)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/settings/load", response_class=JSONResponse)
async def load_settings_profile(name: str) -> JSONResponse:
    """Load a named settings profile."""
    from mtgai.settings.model_settings import (
        SETTINGS_DIR,
        ModelSettings,
        validate_profile_name,
    )

    try:
        validate_profile_name(name)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    path = SETTINGS_DIR / f"{name}.toml"
    if not path.exists():
        return JSONResponse({"error": f"Profile '{name}' not found"}, status_code=404)

    try:
        settings = ModelSettings.load_from_file(path)
        return JSONResponse({"settings": settings.model_dump()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.delete("/api/settings/profile/{name}", response_class=JSONResponse)
async def delete_settings_profile(name: str) -> JSONResponse:
    """Delete a named settings profile from the global library.

    Refuses to delete the profile currently used as the cross-set
    default — orphaning ``global.toml`` would silently fall back to
    built-in defaults on the next new-set seed.
    """
    from mtgai.settings.model_settings import (
        SETTINGS_DIR,
        get_global_settings,
        validate_profile_name,
    )

    try:
        validate_profile_name(name)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    if name == get_global_settings().default_preset:
        return JSONResponse(
            {
                "error": (
                    f"Profile '{name}' is the current default for new sets. "
                    "Pick a different default first."
                )
            },
            status_code=409,
        )

    path = SETTINGS_DIR / f"{name}.toml"
    if not path.exists():
        return JSONResponse({"error": f"Profile '{name}' not found"}, status_code=404)

    try:
        path.unlink()
        return JSONResponse({"success": True})
    except OSError as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/settings/global", response_class=JSONResponse)
async def get_global_settings_endpoint() -> JSONResponse:
    """Return cross-set defaults (currently just default_preset)."""
    from mtgai.settings.model_settings import (
        PRESETS,
        get_global_settings,
        list_profiles,
    )

    glob = get_global_settings()
    return JSONResponse(
        {
            "default_preset": glob.default_preset,
            "builtin_presets": sorted(PRESETS),
            "saved_profiles": list_profiles(),
        }
    )


@app.post("/api/settings/global", response_class=JSONResponse)
async def update_global_settings(request: Request) -> JSONResponse:
    """Update the cross-set default preset."""
    from mtgai.settings.model_settings import (
        GlobalSettings,
        apply_global_settings,
    )

    body = await request.json()
    raw = body.get("default_preset", "")
    if not isinstance(raw, str) or not raw.strip():
        return JSONResponse({"error": "default_preset required"}, status_code=400)

    name = raw.strip()
    try:
        apply_global_settings(GlobalSettings(default_preset=name))
        return JSONResponse({"success": True, "default_preset": name})
    except (ValueError, OSError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
