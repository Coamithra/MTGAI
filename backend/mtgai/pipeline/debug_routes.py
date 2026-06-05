"""Debug / QA-harness endpoints — mounted only under ``serve --debug``.

These exist to let a self-driving QA bot (the "QA Bot" card) drive the wizard
via claude-in-chrome without getting stuck on things a browser agent can't do:

* The ``.mtg`` save/open flow uses the browser's native
  ``window.showSaveFilePicker()`` — an OS dialog invisible to the DOM. The
  :func:`debug_save_mtg` / :func:`debug_open_path` / :func:`debug_quick_project`
  endpoints write/read the ``.mtg`` **server-side** so no picker ever appears.
* The pipeline's early stages are slow. :func:`debug_seed_stage` copies a
  finished "golden" project's artifacts into a throwaway QA run and rewrites
  ``pipeline-state.json`` so the wizard lands directly on any chosen stage.

Everything here is gated behind :func:`is_debug_enabled` (env ``MTGAI_DEBUG``,
set by ``review serve --debug``). When debug mode is off the router isn't even
mounted (see :mod:`mtgai.review.server`), so the surface is invisible in a
normal run.

The endpoints deliberately reuse the production seams — ``active_project``,
``ModelSettings.from_preset``, ``engine.load_state``/``save_state`` — rather
than reinventing project setup, so a QA project behaves exactly like a real one.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from mtgai.io.paths import output_root, repo_root

DEBUG_ENV = "MTGAI_DEBUG"

# Dirs we never copy when cloning a golden project into a QA run: LLM transcript
# dumps (``*/logs``) and the regen archive are bulk we don't need to exercise a
# stage's tab. Keeping cards/, theme.json, skeleton.json, reviews/, reports/,
# history/ etc. preserves everything the wizard tabs actually read.
_CLONE_IGNORE = shutil.ignore_patterns("logs", "_regen_archive", "*.log")


def is_debug_enabled() -> bool:
    """True when the QA/debug surface should be active.

    Driven by the ``MTGAI_DEBUG`` env var (``review serve --debug`` sets it to
    ``"1"``). Any non-empty value other than ``"0"``/``"false"`` counts as on so
    a bare ``MTGAI_DEBUG=1`` from a shell works too.
    """
    val = os.environ.get(DEBUG_ENV, "").strip().lower()
    return bool(val) and val not in ("0", "false", "no", "off")


router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _qa_runs_root() -> Path:
    """``<repo>/output/qa-runs`` — throwaway home for QA project clones."""
    return output_root() / "qa-runs"


def _slug(name: str) -> str:
    """Filesystem-safe lowercase slug for a QA-run directory name."""
    out = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")
    return out or "qa"


def _unique_run_dir(label: str) -> Path:
    """A fresh, non-colliding ``output/qa-runs/<label>[-N]`` directory path.

    Uses a counter rather than a timestamp because ``datetime.now()`` is fine
    here (server code), but a counter keeps names short and predictable for a
    bot reading them back. Does not create the dir — the caller does.
    """
    base = _qa_runs_root()
    base.mkdir(parents=True, exist_ok=True)
    name = _slug(label)
    candidate = base / name
    n = 2
    while candidate.exists():
        candidate = base / f"{name}-{n}"
        n += 1
    return candidate


def _golden_candidates() -> list[dict[str, str]]:
    """Discover finished projects usable as a :func:`debug_seed_stage` source.

    A candidate is any directory holding both ``pipeline-state.json`` and
    ``theme.json``. Searches, in order: ``$MTGAI_QA_GOLDEN`` (an explicit
    override path), the repo's ``sets (new)/*`` projects, and ``output/sets/*``.
    Returns ``[{path, name}]`` newest-mtime first so the panel can default to
    the freshest. QA-run clones under ``output/qa-runs`` are excluded so a clone
    can't become its own source.
    """
    seen: set[Path] = set()
    found: list[Path] = []

    def consider(d: Path) -> None:
        d = d.resolve()
        if d in seen:
            return
        seen.add(d)
        if (d / "pipeline-state.json").is_file() and (d / "theme.json").is_file():
            found.append(d)

    env_override = os.environ.get("MTGAI_QA_GOLDEN", "").strip()
    if env_override:
        consider(Path(env_override))

    roots = [repo_root() / "sets (new)", output_root() / "sets"]
    qa_root = _qa_runs_root().resolve()
    for root in roots:
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if child.is_dir() and qa_root not in child.resolve().parents:
                consider(child)

    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"path": str(p), "name": p.name} for p in found]


def _write_active_qa_project(set_code: str, asset_dir: Path, *, preset: str = "qa") -> None:
    """Materialize + activate a QA project rooted at ``asset_dir``.

    Loads the named preset (default ``qa`` — all-Gemma-2bit, thinking off),
    points its ``asset_folder`` at ``asset_dir``, pins it as the active project,
    and writes the canonical ``.mtg`` into ``asset_dir`` so the project is a
    real, openable file (no browser picker involved).
    """
    from mtgai.runtime import active_project
    from mtgai.settings.model_settings import ModelSettings, dump_project_toml

    try:
        settings = ModelSettings.from_preset(preset)
    except ValueError:
        settings = ModelSettings()
    settings = settings.model_copy(update={"asset_folder": str(asset_dir)})

    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / "qa.mtg").write_text(dump_project_toml(set_code, settings), encoding="utf-8")
    active_project.write_active_project(
        active_project.ProjectState(
            set_code=set_code, settings=settings, mtg_path=asset_dir / "qa.mtg"
        )
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/debug/state")
async def debug_state() -> JSONResponse:
    """Report what the debug surface can do right now.

    The wizard's debug panel polls this on load: ``enabled`` gates the panel,
    and the rest seeds its controls (which golden sources exist, whether the
    prefab pool is populated, the stage dropdown, the active project).
    """
    from mtgai.generation import prefab
    from mtgai.pipeline.models import STAGE_DEFINITIONS
    from mtgai.runtime import active_project

    proj = active_project.read_active_project()
    return JSONResponse(
        {
            "enabled": True,  # router only mounts when enabled
            "prefab_cards": prefab.prefab_cards_available(),
            "prefab_mechanics": prefab.prefab_mechanics_available(),
            "golden_candidates": _golden_candidates(),
            "stages": [
                {"stage_id": d["stage_id"], "display_name": d["display_name"]}
                for d in STAGE_DEFINITIONS
            ],
            "active": (
                None
                if proj is None
                else {"set_code": proj.set_code, "asset_folder": proj.settings.asset_folder}
            ),
        }
    )


@router.post("/api/debug/quick-project")
async def debug_quick_project(request: Request) -> JSONResponse:
    """Create + activate a fresh QA project with NO file picker.

    Body (all optional): ``{set_code, set_size, theme_text, prefab}``.

    * Applies the ``qa`` preset (cheap 2-bit Gemma, thinking off).
    * ``set_size`` shrinks the pipeline for speed (default 60).
    * ``prefab`` (default true) flips on ``use_prefab_cards`` +
      ``use_prefab_mechanics`` so card_gen/mechanics short-circuit.
    * ``theme_text`` — inline prose written as ``theme_source.txt`` and pinned
      as a ``text`` theme input, so the bot can kick off extraction.

    Returns ``{navigate}`` pointing at the Project Settings tab.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    from mtgai.settings.model_settings import (
        DebugSettings,
        SetParams,
        ThemeInputSource,
        apply_settings,
    )

    set_code = str(body.get("set_code") or "QA").strip() or "QA"
    try:
        set_size = int(body.get("set_size") or 60)
    except (TypeError, ValueError):
        set_size = 60
    set_size = max(10, min(set_size, 720))
    use_prefab = bool(body.get("prefab", True))
    theme_text = body.get("theme_text")

    asset_dir = _unique_run_dir(f"{set_code}-quick")
    _write_active_qa_project(set_code, asset_dir)

    # Layer the per-project knobs (set size, prefab, optional theme) on top of
    # the activated qa-preset settings.
    from mtgai.runtime import active_project

    settings = active_project.require_active_project().settings
    sp = SetParams(set_name=f"{set_code} QA", set_size=set_size, mechanic_count=2)
    theme_input = settings.theme_input
    if isinstance(theme_text, str) and theme_text.strip():
        (asset_dir / "theme_source.txt").write_text(theme_text, encoding="utf-8")
        theme_input = ThemeInputSource(
            kind="text", filename="theme_source.txt", char_count=len(theme_text)
        )
    new = settings.model_copy(
        update={
            "set_params": sp,
            "theme_input": theme_input,
            "debug": DebugSettings(use_prefab_cards=use_prefab, use_prefab_mechanics=use_prefab),
        }
    )
    apply_settings(new)

    return JSONResponse(
        {
            "success": True,
            "set_code": set_code,
            "asset_folder": str(asset_dir),
            "navigate": "/pipeline/project",
        }
    )


@router.post("/api/debug/seed-stage")
async def debug_seed_stage(request: Request) -> JSONResponse:
    """Clone a finished project and jump the wizard to a chosen stage.

    Body: ``{target_stage, source_dir?}``. Copies ``source_dir`` (default: the
    newest golden candidate) into a fresh ``output/qa-runs/`` dir, activates it
    as a QA project, then rewrites ``pipeline-state.json`` so every backbone
    stage up to **and including** ``target_stage`` is COMPLETED and everything
    after is reset PENDING. The pipeline ends PAUSED at the target, so the
    wizard opens that tab populated with the cloned artifacts — exactly the
    "skip to a state" the QA card asks for.

    Inserted regen-loop instances (``card_gen.2`` …) are dropped: the live
    ``cards/`` folder is already the loop tip, which is all a seeded tab needs.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    from mtgai.pipeline import engine
    from mtgai.pipeline.models import STAGE_DEFINITIONS, PipelineStatus, StageStatus

    target = str(body.get("target_stage") or "").strip()
    valid = {d["stage_id"] for d in STAGE_DEFINITIONS}
    if target not in valid:
        return JSONResponse(
            {"error": f"target_stage must be one of {sorted(valid)}"}, status_code=400
        )

    source_dir = body.get("source_dir")
    if isinstance(source_dir, str) and source_dir.strip():
        src = Path(source_dir.strip())
    else:
        candidates = _golden_candidates()
        if not candidates:
            return JSONResponse(
                {"error": "No golden source project found (need pipeline-state.json + theme.json)"},
                status_code=400,
            )
        src = Path(candidates[0]["path"])
    if not (src / "pipeline-state.json").is_file():
        return JSONResponse({"error": f"Not a finished project: {src}"}, status_code=400)

    # Clone artifacts (minus logs) into a throwaway run dir.
    dest = _unique_run_dir(f"{src.name}-at-{target}")
    shutil.copytree(src, dest, ignore=_CLONE_IGNORE, dirs_exist_ok=True)
    # Drop any stale .mtg cloned from the source — we write our own qa.mtg.
    for stray in dest.glob("*.mtg"):
        if stray.name != "qa.mtg":
            stray.unlink()

    set_code = src.name.upper()[:8] or "QA"
    _write_active_qa_project(set_code, dest)

    # Rewrite the cloned pipeline-state: backbone-only, target+predecessors
    # COMPLETED, downstream PENDING, paused at the target.
    state = engine.load_state()
    if state is None:
        return JSONResponse({"error": "Clone has no loadable pipeline-state"}, status_code=500)

    order = [d["stage_id"] for d in STAGE_DEFINITIONS]
    target_idx = order.index(target)
    backbone = [s for s in state.stages if s.instance_id == s.stage_id]
    for s in backbone:
        try:
            idx = order.index(s.stage_id)
        except ValueError:
            continue
        if idx <= target_idx:
            s.status = StageStatus.COMPLETED
        else:
            s.status = StageStatus.PENDING
            s.result = {}
            s.progress.error_message = None
    state.stages = backbone
    state.current_instance_id = target
    state.overall_status = PipelineStatus.PAUSED
    engine.save_state(state)

    return JSONResponse(
        {
            "success": True,
            "set_code": set_code,
            "source": str(src),
            "asset_folder": str(dest),
            "target_stage": target,
            "navigate": f"/pipeline/{target}",
        }
    )


@router.post("/api/debug/open-path")
async def debug_open_path(request: Request) -> JSONResponse:
    """Open a ``.mtg`` from a server-side path — no browser picker.

    Body: ``{path}``. Mirrors ``/api/project/open`` but reads the TOML off disk
    so a bot can reopen a prior QA run (or any project) headlessly.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    path = (body or {}).get("path") if isinstance(body, dict) else None
    if not isinstance(path, str) or not path.strip():
        return JSONResponse({"error": "path required"}, status_code=400)
    p = Path(path.strip())
    if p.is_dir():
        mtgs = sorted(p.glob("*.mtg"))
        if not mtgs:
            return JSONResponse({"error": f"No .mtg in {p}"}, status_code=400)
        p = mtgs[0]
    if not p.is_file():
        return JSONResponse({"error": f"No such file: {p}"}, status_code=400)

    from mtgai.pipeline.engine import cleanup_orphan_running_stages
    from mtgai.runtime import active_project
    from mtgai.settings.model_settings import parse_project_toml

    try:
        set_code, settings = parse_project_toml(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        return JSONResponse({"error": f"Invalid .mtg: {e}"}, status_code=400)
    active_project.write_active_project(
        active_project.ProjectState(set_code=set_code, settings=settings, mtg_path=p)
    )
    cleanup_orphan_running_stages()
    return JSONResponse({"success": True, "set_code": set_code, "path": str(p)})


@router.post("/api/debug/save-mtg")
async def debug_save_mtg() -> JSONResponse:
    """Write the active project's ``.mtg`` to its asset folder — the Save bypass.

    The wizard's Save button normally calls ``showSaveFilePicker()`` (an OS
    dialog). In debug mode the client routes here instead so a bot can "Save"
    headlessly. Writes ``<asset_folder>/<set_code or qa>.mtg``.
    """
    from mtgai.runtime import active_project
    from mtgai.settings.model_settings import dump_project_toml

    proj = active_project.read_active_project()
    if proj is None:
        return JSONResponse({"error": "No project open"}, status_code=409)
    folder = proj.settings.asset_folder
    if not folder:
        return JSONResponse({"error": "Active project has no asset folder"}, status_code=409)
    dest_dir = Path(folder)
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = _slug(proj.set_code) if proj.set_code else "qa"
    dest = dest_dir / f"{name}.mtg"
    dest.write_text(dump_project_toml(proj.set_code, proj.settings), encoding="utf-8")
    return JSONResponse({"success": True, "path": str(dest)})


def attach_debug_routes(app: Any) -> bool:
    """Mount the debug router on ``app`` iff debug mode is enabled.

    Returns whether it was mounted, so the caller can log it. Kept here (not in
    server.py) so the gating + router live together and server.py just calls it.
    """
    if not is_debug_enabled():
        return False
    app.include_router(router)
    return True
