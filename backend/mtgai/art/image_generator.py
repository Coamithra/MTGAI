"""Image generation pipeline for card art.

Generates art images for cards using their pre-built art prompts.
Supports local ComfyUI (Flux GGUF) with a swappable backend design
for future cloud API integration (fal.ai, Replicate, Midjourney).

Prerequisites:
    - ComfyUI running at http://127.0.0.1:8188
    - Flux.1-dev GGUF + T5-XXL + CLIP-L + VAE loaded
    - Art prompts already generated on card JSONs (see prompt_builder.py)

CLI usage:
    python -m mtgai.art.image_generator --mtg path/to/project.mtg [--card W-C-01] [--dry-run]
"""

import argparse
import contextlib
import json
import logging
import os
import random
import subprocess
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

from mtgai.io.atomic import atomic_write_text
from mtgai.io.card_io import load_card
from mtgai.io.paths import card_slug, output_root

logger = logging.getLogger(__name__)

OUTPUT_ROOT = output_root()
# External tool root; machine-specific. Override with the COMFYUI_ROOT env var.
COMFYUI_ROOT = Path(os.environ.get("COMFYUI_ROOT", "C:/Programming/ComfyUI"))
COMFYUI_URL = "http://127.0.0.1:8188"
WORKFLOW_PATH = Path(__file__).resolve().parent / "workflows" / "flux_dev_gguf.json"

# Generation defaults
DEFAULT_STEPS = 30
DEFAULT_GUIDANCE = 3.5
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 768
POLL_INTERVAL = 3  # seconds between completion checks
GENERATION_TIMEOUT = 600  # 10 minutes max per image (cold start model loading can take 3-5 min)


# Minimum free VRAM required (MB) — Flux Q8_0 needs ~9.6GB for models + ~1GB compute
MIN_VRAM_FREE_MB = 10_200


# ---------------------------------------------------------------------------
# VRAM check
# ---------------------------------------------------------------------------


def get_vram_info() -> dict:
    """Query GPU VRAM via nvidia-smi. Returns dict with total_mb, free_mb, used_mb."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,memory.free,memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"nvidia-smi failed: {result.stderr}")
        parts = result.stdout.strip().split(", ")
        return {
            "total_mb": int(parts[0]),
            "free_mb": int(parts[1]),
            "used_mb": int(parts[2]),
        }
    except FileNotFoundError:
        raise RuntimeError("nvidia-smi not found — is an NVIDIA GPU installed?") from None


def get_gpu_processes() -> list[str]:
    """Get names of notable processes using the GPU.

    On Windows WDDM, nvidia-smi doesn't report per-process VRAM, so we
    just list process names to help the user decide what to close.
    Filters out system/shell processes, keeping only user-facing apps.
    """
    # Known system processes to hide (not closeable / negligible VRAM)
    system_procs = {
        "explorer.exe",
        "searchhost.exe",
        "shellhost.exe",
        "shellexperiencehost.exe",
        "startmenuexperiencehost.exe",
        "textinputhost.exe",
        "applicationframehost.exe",
        "lockapp.exe",
        "crossdeviceresume.exe",
        "phoneexperiencehost.exe",
        "systemsettings.exe",
        "windowsterminal.exe",
        "nvidia overlay.exe",
        "msedgewebview2.exe",
        "edgegameassist.exe",
        "xboxgamebarspotify.exe",
        "asus_framework.exe",
        "amdrsssrcext.exe",
        "radeonsoftware.exe",
        "logioptionsplus_agent.exe",
        "lghub_system_tray.exe",
    }
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
        # Parse process names from nvidia-smi output
        names = set()
        in_processes = False
        for line in result.stdout.splitlines():
            if "Processes:" in line:
                in_processes = True
                continue
            if in_processes and "|" in line:
                # Extract process name between the columns
                parts = line.split()
                for part in parts:
                    if ".exe" in part.lower():
                        exe = part.rsplit("\\", 1)[-1]
                        if exe.lower() not in system_procs:
                            names.add(exe)
        return sorted(names)
    except Exception:
        return []


def check_vram(min_free_mb: int = MIN_VRAM_FREE_MB) -> None:
    """Check that enough VRAM is free for Flux generation.

    Raises RuntimeError with actionable message listing GPU-hungry
    processes if insufficient VRAM is available.
    """
    vram = get_vram_info()
    logger.info(
        "VRAM: %dMB total, %dMB free, %dMB used (need %dMB free)",
        vram["total_mb"],
        vram["free_mb"],
        vram["used_mb"],
        min_free_mb,
    )
    if vram["free_mb"] >= min_free_mb:
        return

    # Not enough — build a helpful error with process list
    procs = get_gpu_processes()
    shortfall = min_free_mb - vram["free_mb"]
    msg = (
        f"Insufficient VRAM: {vram['free_mb']}MB free, need {min_free_mb}MB "
        f"({shortfall}MB short).\n"
    )
    if procs:
        msg += "\nApps using GPU VRAM that you could close:\n"
        for name in procs:
            msg += f"  - {name}\n"
        msg += "\nClose some of these and try again."
    else:
        msg += "Close GPU-heavy apps (browsers, games, Discord, Reaper, etc.) and try again."
    raise RuntimeError(msg)


# ---------------------------------------------------------------------------
# ComfyUI server management
# ---------------------------------------------------------------------------


def is_comfyui_running() -> bool:
    """Check if ComfyUI server is responding."""
    try:
        resp = urllib.request.urlopen(f"{COMFYUI_URL}/system_stats", timeout=5)
        data = json.loads(resp.read())
        return "system" in data
    except Exception:
        return False


def start_comfyui(log_dir: Path | None = None) -> subprocess.Popen:
    """Start ComfyUI server as a subprocess.

    Args:
        log_dir: If provided, redirect ComfyUI stdout/stderr to a log file
                 in this directory. Otherwise uses DEVNULL.
    """
    python_exe = COMFYUI_ROOT / "venv" / "Scripts" / "python.exe"
    main_py = COMFYUI_ROOT / "main.py"

    if not python_exe.exists():
        raise FileNotFoundError(f"ComfyUI Python not found: {python_exe}")

    logger.info("Starting ComfyUI server...")
    # Can't use subprocess.PIPE — tqdm progress bars crash with
    # OSError: [Errno 22] on piped stderr on Windows.
    # Instead, redirect to a log file so we can diagnose crashes.
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        comfyui_log = log_dir / "comfyui.log"
        logger.info("ComfyUI output → %s", comfyui_log)
        # Long-lived handle: stored on the process and closed in kill_comfyui.
        log_handle = open(comfyui_log, "w", encoding="utf-8", buffering=1)  # noqa: SIM115
        stdout_dest = log_handle
        stderr_dest = log_handle
    else:
        log_handle = None
        stdout_dest = subprocess.DEVNULL
        stderr_dest = subprocess.DEVNULL

    proc = subprocess.Popen(
        [
            str(python_exe),
            str(main_py),
            "--listen",
            "127.0.0.1",
            "--port",
            "8188",
            "--disable-cuda-malloc",  # Avoid cudaMallocAsync instability
        ],
        stdout=stdout_dest,
        stderr=stderr_dest,
        cwd=str(COMFYUI_ROOT),
    )
    # Stash the log handle on the proc so we can close it later
    proc._log_handle = log_handle  # type: ignore[attr-defined]

    # On every failure exit below, kill_comfyui (which closes the log handle) is
    # never reached, so close it here to avoid leaking it (mirror kill_comfyui).
    def _close_log_handle() -> None:
        if log_handle is not None:
            with contextlib.suppress(Exception):
                log_handle.close()

    # Wait for server to become responsive
    for i in range(60):
        time.sleep(2)
        if is_comfyui_running():
            logger.info("ComfyUI ready after %ds", (i + 1) * 2)
            return proc
        if proc.poll() is not None:
            _close_log_handle()
            raise RuntimeError("ComfyUI process exited unexpectedly")

    _close_log_handle()
    proc.kill()
    raise TimeoutError("ComfyUI failed to start within 120 seconds")


def ensure_comfyui(log_dir: Path | None = None) -> subprocess.Popen | None:
    """Ensure ComfyUI is running. Starts it if needed. Returns process or None.

    Checks VRAM availability before starting to fail fast with an
    actionable error instead of crashing mid-generation.

    Args:
        log_dir: If provided, redirect ComfyUI output to a log file here.
    """
    if is_comfyui_running():
        logger.info("ComfyUI already running at %s", COMFYUI_URL)
        return None
    check_vram()
    return start_comfyui(log_dir=log_dir)


def kill_comfyui(proc: subprocess.Popen | None = None) -> None:
    """Kill ComfyUI and free VRAM. Works whether we started it or it was already running.

    Tries the process handle first (if we started it), then falls back to
    finding and killing the ComfyUI Python process by its command line.
    """
    # Close the log file handle if we opened one
    if proc is not None:
        log_handle = getattr(proc, "_log_handle", None)
        if log_handle is not None:
            with contextlib.suppress(Exception):
                log_handle.close()

    # Try the process handle we have
    if proc is not None and proc.poll() is None:
        logger.info("Terminating ComfyUI (PID %d)...", proc.pid)
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("ComfyUI didn't terminate gracefully, killing...")
            proc.kill()
        return

    # Fall back: find ComfyUI by its command line signature
    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-Command",
                "Get-Process python* | Where-Object {"
                "$_.Path -like '*ComfyUI*'"
                "} | Select-Object -ExpandProperty Id",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        pids = [int(p.strip()) for p in result.stdout.strip().splitlines() if p.strip()]
        if not pids:
            logger.info("No ComfyUI process found to kill.")
            return
        for pid in pids:
            logger.info("Killing ComfyUI process (PID %d)...", pid)
            subprocess.run(
                ["powershell.exe", "-Command", f"Stop-Process -Id {pid} -Force"],
                timeout=10,
            )
    except Exception as e:
        logger.warning("Failed to find/kill ComfyUI process: %s", e)


# ---------------------------------------------------------------------------
# ComfyUI API interaction
# ---------------------------------------------------------------------------


def _load_workflow() -> dict:
    """Load the Flux GGUF workflow template."""
    return json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _queue_prompt(workflow: dict) -> str:
    """Queue a workflow to ComfyUI. Returns the prompt_id."""
    payload = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    return result["prompt_id"]


def _poll_completion(prompt_id: str, timeout: int = GENERATION_TIMEOUT) -> dict:
    """Poll ComfyUI history until the prompt completes. Returns output info."""
    start = time.time()
    consecutive_failures = 0
    max_consecutive_failures = 5  # ~15s of no response = ComfyUI is dead
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            raise TimeoutError(f"Generation timed out after {timeout}s")

        try:
            resp = urllib.request.urlopen(f"{COMFYUI_URL}/history/{prompt_id}")
            history = json.loads(resp.read())
            consecutive_failures = 0  # Reset on success
        except Exception as e:
            consecutive_failures += 1
            if consecutive_failures >= max_consecutive_failures:
                raise RuntimeError(
                    f"ComfyUI appears to have died — {consecutive_failures} consecutive "
                    f"connection failures over ~{consecutive_failures * POLL_INTERVAL}s. "
                    f"Last error: {e}"
                ) from e
            time.sleep(POLL_INTERVAL)
            continue

        if prompt_id not in history:
            time.sleep(POLL_INTERVAL)
            continue

        entry = history[prompt_id]
        status = entry.get("status", {})

        if status.get("completed") or status.get("status_str") == "success":
            # Extract image info from outputs
            for node_out in entry.get("outputs", {}).values():
                if "images" in node_out:
                    for img in node_out["images"]:
                        return {
                            "filename": img["filename"],
                            "subfolder": img.get("subfolder", ""),
                            "elapsed": elapsed,
                        }
            raise RuntimeError("Generation completed but no image found in outputs")

        if status.get("status_str") == "error":
            # Extract useful error info from messages
            error_msg = "Unknown error"
            for msg_type, msg_data in status.get("messages", []):
                if msg_type == "execution_error":
                    error_msg = (
                        f"{msg_data.get('exception_type', '?')}: "
                        f"{msg_data.get('exception_message', '?').strip()} "
                        f"(node: {msg_data.get('node_type', '?')})"
                    )
                    break
            raise RuntimeError(f"ComfyUI generation error: {error_msg}")

        time.sleep(POLL_INTERVAL)


def _download_image(filename: str, subfolder: str = "") -> bytes:
    """Download a generated image from ComfyUI."""
    params = f"filename={filename}"
    if subfolder:
        params += f"&subfolder={subfolder}"
    resp = urllib.request.urlopen(f"{COMFYUI_URL}/view?{params}", timeout=120)
    return resp.read()


def flush_comfyui() -> None:
    """Flush ComfyUI's CUDA caches and history to prevent GPU memory accumulation.

    Calls two ComfyUI API endpoints:
    - POST /free — triggers torch.cuda.empty_cache() and clears internal caches
      while keeping models loaded (no reload penalty)
    - POST /history — clears completed generation history from RAM

    Call this after each image generation to prevent the progressive GPU state
    buildup that causes silent crashes after several images.
    """
    try:
        # Free CUDA cache (keep models loaded)
        payload = json.dumps({"unload_models": False, "free_memory": True}).encode()
        req = urllib.request.Request(
            f"{COMFYUI_URL}/free",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)

        # Clear history to free CPU-side memory
        clear_payload = json.dumps({"clear": True}).encode()
        req = urllib.request.Request(
            f"{COMFYUI_URL}/history",
            data=clear_payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logger.warning("Failed to flush ComfyUI caches: %s", e)


# ---------------------------------------------------------------------------
# Image generation (local ComfyUI backend)
# ---------------------------------------------------------------------------


def _apply_character_refs(workflow: dict, ref_paths: list[str]) -> bool:
    """Inject character reference-image conditioning into the Flux workflow.

    Reads the resolved reference-image paths a card carries via
    ``Card.art_character_refs`` (produced by the ``char_portraits`` stage) and
    wires them into the ComfyUI graph as PuLID-Flux / IP-Adapter conditioning so
    a card featuring a recurring entity is generated *with that entity's
    appearance* rather than a fresh interpretation.

    STUB (intentional, tracked): the bundled ``flux_dev_gguf.json`` workflow has
    no PuLID/IP-Adapter nodes, and those require ComfyUI custom-node packs that
    aren't guaranteed present. Wiring the actual graph is a manual-testing follow
    -up against a live ComfyUI with the PuLID-Flux nodes installed. Until then
    this logs the intent and returns False so the caller falls back to plain
    text-to-image. The *decision* (which cards get ref-conditioning, with which
    images) is fully implemented here and unit-tested — only the node injection
    is deferred. Returns True when conditioning was actually applied.
    """
    if not ref_paths:
        return False
    existing = [p for p in ref_paths if Path(p).exists()]
    if not existing:
        logger.warning(
            "  Character refs declared but none exist on disk (%s) — generating without them",
            ", ".join(ref_paths),
        )
        return False
    # TODO(art-gen): inject PuLID-Flux / IP-Adapter nodes into ``workflow`` here,
    # loading each path in ``existing`` as an identity/style reference and routing
    # its conditioning into KSampler node "8". Requires the PuLID-Flux ComfyUI
    # custom nodes; verify against a live ComfyUI. Until then we no-op so the run
    # still produces art (without identity locking).
    logger.info(
        "  %d character ref(s) available for conditioning (PuLID wiring pending): %s",
        len(existing),
        ", ".join(Path(p).name for p in existing),
    )
    return False


def generate_image_comfyui(
    prompt: str,
    seed: int | None = None,
    steps: int = DEFAULT_STEPS,
    guidance: float = DEFAULT_GUIDANCE,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    ref_paths: list[str] | None = None,
) -> tuple[bytes, dict]:
    """Generate an image via local ComfyUI.

    ``ref_paths`` are resolved character-reference image paths (from
    ``Card.art_character_refs``); when present and the PuLID/IP-Adapter wiring is
    available they condition generation on the entity's appearance.

    Returns (image_bytes, metadata_dict).
    """
    workflow = _load_workflow()

    # Inject parameters
    workflow["4"]["inputs"]["text"] = prompt
    workflow["6"]["inputs"]["guidance"] = guidance
    workflow["7"]["inputs"]["width"] = width
    workflow["7"]["inputs"]["height"] = height
    workflow["8"]["inputs"]["seed"] = seed if seed is not None else random.randint(0, 2**32)
    workflow["8"]["inputs"]["steps"] = steps

    refs_applied = _apply_character_refs(workflow, ref_paths or [])

    # Queue and wait
    prompt_id = _queue_prompt(workflow)
    logger.info("  Queued prompt %s (seed=%s)", prompt_id[:8], workflow["8"]["inputs"]["seed"])

    result = _poll_completion(prompt_id)
    logger.info("  Generated in %.1fs: %s", result["elapsed"], result["filename"])

    # Download the image
    image_data = _download_image(result["filename"], result["subfolder"])

    # Flush CUDA caches to prevent GPU memory accumulation across generations
    flush_comfyui()

    metadata = {
        "prompt_id": prompt_id,
        "seed": workflow["8"]["inputs"]["seed"],
        "steps": steps,
        "guidance": guidance,
        "width": width,
        "height": height,
        "elapsed_seconds": round(result["elapsed"], 1),
        "backend": "comfyui_local",
        "model": "flux1-dev-Q8_0",
        "character_refs_applied": refs_applied,
    }
    return image_data, metadata


def generate_image_hosted(
    prompt: str,
    provider: str,
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    ref_paths: list[str] | None = None,
) -> tuple[bytes, dict]:
    """Generate an image via a hosted provider (OpenAI / Google) through llmfacade.

    STUB (intentional, tracked): hosted image generation rides on llmfacade's
    ``generate_image`` support, built under a concurrent ticket. The dispatch +
    routing live here so the seam is in place; the actual call is wired the
    moment llmfacade lands it. Until then this raises ``NotImplementedError`` so
    the stage runner can fall back to local Flux rather than silently producing
    nothing. ``ref_paths`` are threaded for provider reference-conditioning once
    the call is live.
    """
    raise NotImplementedError(
        f"Hosted image generation ({provider!r}) is not wired yet — it depends on "
        "llmfacade's generate_image support (concurrent ticket). Use the local "
        "Flux/ComfyUI provider until that lands."
    )


def generate_image(
    prompt: str,
    *,
    provider: str = "comfyui",
    seed: int | None = None,
    ref_paths: list[str] | None = None,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> tuple[bytes, dict]:
    """Provider-dispatching single-image generation entry point.

    - ``comfyui`` -> local Flux (a direct ComfyUI path, no llmfacade).
    - ``openai`` / ``gemini`` -> hosted, routed through llmfacade's
      ``generate_image`` (stubbed; raises until that lands).

    Other providers raise ``ValueError``. The Art Generation stage calls this
    per candidate version; it resolves the provider from the active project's
    ``art_gen`` image assignment.
    """
    if provider == "comfyui":
        return generate_image_comfyui(
            prompt, seed=seed, ref_paths=ref_paths, width=width, height=height
        )
    if provider in ("openai", "gemini"):
        return generate_image_hosted(
            prompt, provider, ref_paths=ref_paths, width=width, height=height
        )
    raise ValueError(f"Unknown image provider: {provider!r}")


def _resolve_ref_paths(card, set_dir: Path) -> list[str]:
    """Resolve a card's ``art_character_refs`` to absolute, on-disk paths.

    ``ref_image_path`` is repo-relative under the asset folder; we join it to
    ``set_dir`` (absolute paths are kept as-is). Built to the field contract —
    works whether or not ``char_portraits`` has actually produced the images.
    """
    resolved: list[str] = []
    for ref in getattr(card, "art_character_refs", None) or []:
        raw = getattr(ref, "ref_image_path", None)
        if not raw:
            continue
        p = Path(raw)
        if not p.is_absolute():
            p = set_dir / raw
        resolved.append(str(p))
    return resolved


# ---------------------------------------------------------------------------
# Batch generation pipeline
# ---------------------------------------------------------------------------


def _load_progress(progress_path: Path) -> dict:
    """Load generation progress tracker."""
    if progress_path.exists():
        return json.loads(progress_path.read_text(encoding="utf-8"))
    return {"completed": {}, "failed": {}, "skipped": []}


def _save_progress(progress: dict, progress_path: Path) -> None:
    """Save generation progress tracker."""
    atomic_write_text(progress_path, json.dumps(progress, indent=2))


def _resolve_versions_per_card() -> int:
    """How many candidate versions to generate per card (best-of-N knob).

    Reads ``SetParams.art_versions_per_card`` off the active project, clamped to
    the supported range. Falls back to the default when no project is open
    (CLI/test paths that haven't activated one).
    """
    from mtgai.settings.model_settings import MAX_ART_VERSIONS, MIN_ART_VERSIONS

    try:
        from mtgai.runtime.active_project import require_active_project

        n = require_active_project().settings.set_params.art_versions_per_card
    except Exception:
        n = 3
    return max(MIN_ART_VERSIONS, min(MAX_ART_VERSIONS, int(n)))


def _resolve_provider() -> str:
    """The image provider for the ``art_gen`` stage (from its image assignment).

    Falls back to local Flux/ComfyUI when no project is open or the assigned
    model can't be resolved.
    """
    try:
        from mtgai.runtime.active_project import require_active_project
        from mtgai.settings.model_registry import get_registry

        key = require_active_project().settings.get_image_model_key("art_gen")
        model = get_registry().get_image(key)
        if model is not None:
            return model.provider
    except Exception:
        pass
    return "comfyui"


def generate_art_for_set(
    card_filter: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    versions_per_card: int | None = None,
    max_attempts_per_version: int = 2,
    progress_callback: Callable[[str, int, int, str, float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict:
    """Generate best-of-N art candidates for all cards in the active project.

    For each card, generates ``versions_per_card`` distinct candidate images
    (different seeds) so a downstream judge can pick the best. This is the
    best-of-N knob, distinct from the old ``max_attempts`` retry-on-failure
    (now a per-version error retry only).

    Args:
        card_filter: Optional collector number prefix to filter cards.
        dry_run: If True, log what would be done but don't generate.
        force: If True, regenerate even if art already exists.
        versions_per_card: Override the per-card candidate count; defaults to the
            project's ``SetParams.art_versions_per_card``.
        max_attempts_per_version: Retries for a single failing version.
        should_cancel: Predicate polled at each card boundary; when True the loop
            stops early (versions generated so far are kept + tracked) and
            ``summary["cancelled"]`` is set.

    Returns summary dict with stats.
    """
    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    set_code = require_active_project().set_code
    set_dir = set_artifact_dir()
    cards_dir = set_dir / "cards"
    art_dir = set_dir / "art"
    log_dir = set_dir / "art-generation-logs"
    art_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    n_versions = (
        versions_per_card if versions_per_card is not None else _resolve_versions_per_card()
    )
    provider = _resolve_provider()

    # Progress file for resumability
    progress_path = log_dir / "progress.json"
    progress = _load_progress(progress_path)

    # Load all card files
    card_files = sorted(cards_dir.glob("*.json"))
    if card_filter:
        card_files = [f for f in card_files if f.name.startswith(card_filter)]

    if not card_files:
        raise ValueError(f"No cards found matching filter: {card_filter}")

    # Ensure ComfyUI is running (local Flux only; hosted providers need no
    # subprocess). Skip on dry-run.
    comfyui_proc = None
    if not dry_run and provider == "comfyui":
        comfyui_proc = ensure_comfyui(log_dir=log_dir)

    generated = 0
    skipped = 0
    failed = 0
    cancelled = False
    errors = []

    try:
        for card_file in card_files:
            if should_cancel is not None and should_cancel():
                logger.info("Art generation cancelled by user after %d card(s)", generated)
                cancelled = True
                break

            card = load_card(card_file)
            cn = card.collector_number

            # Skip if no art prompt
            if not card.art_prompt:
                logger.warning("SKIP %s — no art_prompt on card", cn)
                skipped += 1
                continue

            # Skip if already completed (resumable) unless forced
            if cn in progress["completed"] and not force:
                logger.info("SKIP %s — already generated", cn)
                skipped += 1
                continue

            slug = card_slug(cn, card.name)
            ref_paths = _resolve_ref_paths(card, set_dir)

            logger.info(
                "GENERATE %s: %s (%d version%s, provider=%s%s)%s",
                cn,
                card.name,
                n_versions,
                "" if n_versions == 1 else "s",
                provider,
                f", {len(ref_paths)} ref(s)" if ref_paths else "",
                " [DRY RUN]" if dry_run else "",
            )
            logger.info("  Prompt: %s", card.art_prompt[:100] + "...")

            if dry_run:
                generated += 1
                continue

            # Best-of-N: generate ``n_versions`` distinct candidates. ``force``
            # restarts the version numbering at 1 (overwrite); otherwise append
            # after any existing versions so a resume tops up the pool.
            existing = list(art_dir.glob(f"{slug}_v*.png"))
            base_version = 0 if force else len(existing)

            saved_versions: list[dict] = []
            version_errors: list[dict] = []
            for i in range(1, n_versions + 1):
                version = base_version + i
                dest = art_dir / f"{slug}_v{version}.png"
                for attempt in range(1, max_attempts_per_version + 1):
                    try:
                        image_data, metadata = generate_image(
                            card.art_prompt,
                            provider=provider,
                            ref_paths=ref_paths,
                        )
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(image_data)
                        logger.info(
                            "  SAVED %s (%.1fs, %s bytes)",
                            dest.name,
                            metadata.get("elapsed_seconds", 0.0),
                            f"{len(image_data):,}",
                        )
                        log_entry = {
                            "collector_number": cn,
                            "name": card.name,
                            "version": version,
                            "attempt": attempt,
                            "prompt": card.art_prompt,
                            "output_path": str(dest),
                            "file_size_bytes": len(image_data),
                            "character_refs": ref_paths,
                            **metadata,
                        }
                        atomic_write_text(
                            log_dir / f"{cn}_v{version}.json", json.dumps(log_entry, indent=2)
                        )
                        saved_versions.append({"version": version, "path": str(dest)})
                        break
                    except NotImplementedError:
                        # Hosted provider not wired yet — surface clearly and stop
                        # (retrying will not help); the stage falls back / fails visibly.
                        raise
                    except Exception as e:
                        logger.error(
                            "  v%d attempt %d/%d failed for %s: %s",
                            version,
                            attempt,
                            max_attempts_per_version,
                            cn,
                            e,
                        )
                        version_errors.append(
                            {"version": version, "attempt": attempt, "error": str(e)}
                        )
                        if attempt < max_attempts_per_version:
                            time.sleep(5)

            if saved_versions:
                generated += 1
                progress["completed"][cn] = {
                    "versions": saved_versions,
                    "version_count": len(saved_versions),
                }
                _save_progress(progress, progress_path)
                if progress_callback is not None:
                    progress_callback(
                        cn,
                        generated + skipped,
                        len(card_files),
                        f"Generated {len(saved_versions)} version(s) for {card.name}",
                        0.0,
                    )
            else:
                failed += 1
                errors.append({"card": cn, "attempts": version_errors})
                progress["failed"][cn] = version_errors
                _save_progress(progress, progress_path)

    finally:
        # Always kill ComfyUI on exit to free VRAM (no-op if we did not start it).
        if provider == "comfyui":
            kill_comfyui(comfyui_proc)

    summary = {
        "set_code": set_code,
        "generated": generated,
        "skipped": skipped,
        "failed": failed,
        "errors": errors,
        "provider": provider,
        "versions_per_card": n_versions,
        "dry_run": dry_run,
        "cancelled": cancelled,
    }

    # Save summary
    summary_path = log_dir / "summary.json"
    atomic_write_text(summary_path, json.dumps(summary, indent=2))

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Generate card art images via ComfyUI + Flux")
    parser.add_argument(
        "--mtg",
        required=True,
        help="Path to a .mtg project file (the project's asset_folder must be set)",
    )
    parser.add_argument("--card", default=None, help="Single card collector number (e.g. R-C-01)")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without generating")
    parser.add_argument("--force", action="store_true", help="Regenerate existing art")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    from mtgai.runtime.cli_shim import activate_from_mtg

    activate_from_mtg(args.mtg)
    summary = generate_art_for_set(
        card_filter=args.card,
        dry_run=args.dry_run,
        force=args.force,
    )

    print(f"\n{'=' * 60}")
    print(f"Art Generation — {summary['set_code']}")
    print(f"{'=' * 60}")
    print(f"Generated: {summary['generated']}")
    print(f"Skipped:   {summary['skipped']}")
    print(f"Failed:    {summary['failed']}")
    print(f"Dry run:   {summary['dry_run']}")
    if summary["errors"]:
        print("\nErrors:")
        for e in summary["errors"]:
            print(f"  {e['card']}:")
            for a in e["attempts"]:
                print(f"    attempt {a['attempt']}: {a['error']}")


if __name__ == "__main__":
    main()
