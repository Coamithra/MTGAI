"""Image generation pipeline for card art.

Generates art images for cards using their pre-built art prompts. Two backends,
dispatched per the active project's ``art_gen`` image assignment:
  - ``comfyui`` — local Flux GGUF via a direct ComfyUI API path (no llmfacade).
  - hosted (``openai`` / ``gemini``) — routed through llmfacade's
    ``generate_image`` (OpenAI Images / Gemini-native). The provider + model id
    come from the image registry (``models.toml`` ``[image.*]``).

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
import re
import subprocess
import time
import urllib.request
import uuid
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

# Periodic ComfyUI recycle to bound VRAM/native-CUDA accumulation across a long
# art run. The per-image ``flush_comfyui()`` only calls torch.cuda.empty_cache()
# (models stay resident), which doesn't recover the fragmentation / native CUDA
# context growth that silently kills the process after ~18-20 images. Tearing
# ComfyUI down and back up every N *images* hands the GPU back to the OS, which
# reclaims everything, so a 60-card / 180-image run survives one server lifetime.
# Default 16 sits below the observed ~18-20 death threshold; 0 disables.
COMFYUI_RECYCLE_EVERY = int(os.environ.get("MTGAI_COMFYUI_RECYCLE_EVERY", "16"))

# PuLID-Flux character face-lock (the ComfyUI-PuLID-Flux custom-node pack).
# The .safetensors filename lives in ComfyUI's ``models/pulid`` dir, listed by
# ``PulidFluxModelLoader``; override per-machine with MTGAI_PULID_MODEL.
PULID_FLUX_MODEL = os.environ.get("MTGAI_PULID_MODEL", "pulid_flux_v0.9.1.safetensors")
# InsightFace execution provider for the face-analysis loader (CUDA on the GPU
# Flux box; CPU/ROCM available via the node). Override with MTGAI_PULID_PROVIDER.
PULID_INSIGHTFACE_PROVIDER = os.environ.get("MTGAI_PULID_PROVIDER", "CUDA")
# Identity-lock strength fed to ApplyPulidFlux (node range -1.0..5.0; 1.0 is the
# node default — a faithful lock that still lets the prompt pose/style the scene).
PULID_WEIGHT = float(os.environ.get("MTGAI_PULID_WEIGHT", "1.0"))


def art_image_url(filename: str) -> str:
    """URL the Art Generation tab's ``<img>`` points at for a generated PNG.

    Mirrors the ``/api/wizard/art_gen/image/<filename>`` route; centralized here
    so the bootstrap state and the live ``art_gen_card`` stream build it the same
    way.
    """
    return f"/api/wizard/art_gen/image/{filename}"


def art_versions_for_card(asset_dir: Path, cn: str, name: str) -> list[dict[str, str]]:
    """On-disk art version tiles (``{filename, url}``) for one card, ``v1``..``vN``.

    The streaming counterpart to the Art Generation tab's bootstrap state: lets a
    per-card ``art_gen_card`` SSE event carry the freshly written PNGs so the tab
    renders them live instead of waiting for the stage to finish (or a manual F5).
    """
    art_dir = asset_dir / "art"
    slug = card_slug(cn, name)
    return [
        {"filename": p.name, "url": art_image_url(p.name)}
        for p in sorted(art_dir.glob(f"{slug}_v*.png"))
    ]


def card_names_by_collector_number(asset_dir: Path) -> dict[str, str]:
    """Map each card's collector number -> name from ``<asset>/cards/*.json``.

    Lets a per-``cn`` progress callback resolve the art slug
    (``<cn>_<name_slug>``) — and thus the card's PNGs — without re-reading every
    card JSON on each streamed event.
    """
    names: dict[str, str] = {}
    cards_dir = asset_dir / "cards"
    if not cards_dir.exists():
        return names
    for path in sorted(cards_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        cn = str(data.get("collector_number") or "")
        if cn:
            names[cn] = data.get("name") or ""
    return names


# VRAM-aware Flux quant selection
# ---------------------------------------------------------------------------
# The current ComfyUI build loads flux1-dev-Q8_0 at a ~12.2GB VRAM footprint
# (a regression vs the older build's ~9.6GB), so on a 12GB card Q8 spills ~2.8GB
# to CPU and runs ~12x slower (~31-37s/step vs ~2.9s/step). flux1-dev-Q5_K_S
# (~8.3GB) loads fully on 12GB and is the safe default/floor; Q8 is only chosen
# when there's comfortable headroom for its larger footprint (>=16GB cards).
#
# Both GGUFs live in ComfyUI's models/unet/ — the workflow JSON's UnetLoaderGGUF
# node names the file, and generate_image_comfyui overwrites it per-run with the
# VRAM-chosen quant (the JSON default mirrors FLUX_QUANT_DEFAULT as a fallback).
FLUX_QUANT_DEFAULT = "flux1-dev-Q5_K_S.gguf"  # safe floor — fits fully on 12GB
FLUX_QUANT_HIGH_VRAM = "flux1-dev-Q8_0.gguf"  # higher quality, needs headroom
# Free VRAM (MB) at/above which Q8 loads fully under the current ComfyUI (its
# ~12.2GB footprint + text encoder + activations).
FLUX_Q8_MIN_FREE_MB = 14_000

# Minimum free VRAM required (MB) — Q5_K_S needs ~8GB for models + ~1GB compute;
# the gate sits below FLUX_Q8_MIN_FREE_MB so a 12GB card passes and runs Q5.
MIN_VRAM_FREE_MB = 9_000

# Per-process cache of the resolved quant. The choice must be made ONCE from the
# pre-load VRAM state and reused for the whole ComfyUI session: once Flux is
# resident, free VRAM has dropped below FLUX_Q8_MIN_FREE_MB, so a per-image
# re-query would flip Q8->Q5 and force a costly model reload (and quality drift)
# mid-set. ``ensure_comfyui`` resets it when it (re)starts ComfyUI.
_SELECTED_FLUX_QUANT: str | None = None


def select_flux_quant(free_mb: int | None = None) -> str:
    """Pick the Flux GGUF quant that fits the available VRAM.

    Returns ``FLUX_QUANT_HIGH_VRAM`` (Q8_0) only when free VRAM comfortably
    exceeds its current-ComfyUI footprint (``FLUX_Q8_MIN_FREE_MB``); otherwise
    ``FLUX_QUANT_DEFAULT`` (Q5_K_S), the safe floor that loads fully on a 12GB
    card. ``free_mb`` is queried via nvidia-smi when not supplied; any query
    failure degrades to the safe default rather than risking the partial-offload
    slowdown.

    The result is cached per process (``reset_flux_quant`` clears it) so the
    quant is decided once from the pre-load VRAM and stays stable across every
    image in a ComfyUI session. Passing an explicit ``free_mb`` always recomputes
    and does not touch the cache (the pure-decision path, for callers/tests).
    """
    if free_mb is not None:
        return FLUX_QUANT_HIGH_VRAM if free_mb >= FLUX_Q8_MIN_FREE_MB else FLUX_QUANT_DEFAULT

    global _SELECTED_FLUX_QUANT
    if _SELECTED_FLUX_QUANT is not None:
        return _SELECTED_FLUX_QUANT
    try:
        free = get_vram_info()["free_mb"]
        chosen = FLUX_QUANT_HIGH_VRAM if free >= FLUX_Q8_MIN_FREE_MB else FLUX_QUANT_DEFAULT
    except Exception:
        chosen = FLUX_QUANT_DEFAULT
    _SELECTED_FLUX_QUANT = chosen
    return chosen


def reset_flux_quant() -> None:
    """Clear the cached quant so the next ``select_flux_quant()`` re-queries VRAM.

    Called when a new ComfyUI session starts (the VRAM picture is fresh) so a
    later run on a now-different GPU state re-decides instead of reusing a stale
    choice.
    """
    global _SELECTED_FLUX_QUANT
    _SELECTED_FLUX_QUANT = None


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


def _check_vram_with_retry(attempts: int = 3, delay_s: float = 1.0) -> None:
    """``check_vram`` with a short bounded poll for VRAM to be reclaimed.

    Used right after unloading the local LLM: the driver can lag the unload's
    HTTP ack by a beat, so a single immediate check could spuriously fail.
    Retries on the ``RuntimeError`` ``check_vram`` raises; the final attempt
    re-raises so the actionable message still surfaces if VRAM never frees.
    """
    for attempt in range(1, attempts + 1):
        try:
            check_vram()
            return
        except RuntimeError:
            if attempt >= attempts:
                raise
            logger.info("VRAM not yet reclaimed (attempt %d/%d) — retrying...", attempt, attempts)
            time.sleep(delay_s)


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
    # Hand the GPU off to Flux: free the managed local LLM's VRAM (it owns a
    # llama-server subprocess) before the VRAM check, so the art tail can run
    # after any local-LLM stage on a single GPU. Best-effort, no-op when no
    # local model is resident. Lazy import — llm_client never imports the art
    # layer, so this stays one-directional with no module-load coupling.
    from mtgai.generation.llm_client import unload_local_models

    unloaded = unload_local_models()
    # VRAM reclamation after the llama-swap unload is near-immediate, but the
    # driver may lag the HTTP ack by a beat. Only when we actually unloaded
    # something, re-query a few times before failing — a cloud-only / other-app
    # shortfall (nothing unloaded) still fails fast with the actionable message.
    _check_vram_with_retry() if unloaded else check_vram()
    # Fresh ComfyUI session -> re-decide the Flux quant from the now-freed VRAM
    # on the next generation (and not a stale earlier-session choice).
    reset_flux_quant()
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


def recycle_comfyui(
    proc: subprocess.Popen | None, log_dir: Path | None = None
) -> subprocess.Popen | None:
    """Tear ComfyUI down and bring it back up to fully reclaim GPU memory.

    The per-image ``flush_comfyui()`` keeps models resident, so VRAM
    fragmentation and native CUDA-context growth still accumulate across a long
    run until the process is silently OS-killed (~18-20 images). A full restart
    is the only thing that hands *all* of that back to the OS. Called every
    ``COMFYUI_RECYCLE_EVERY`` images by ``generate_art_for_set``.

    Returns the new process handle (or ``None`` if a start was skipped, e.g.
    ComfyUI was externally managed and is already back up).
    """
    logger.info("Recycling ComfyUI to reclaim VRAM (per %d images)...", COMFYUI_RECYCLE_EVERY)
    kill_comfyui(proc)
    # Give the OS a beat to reap the process + release the GPU before the
    # restart's pre-flight VRAM check, which would otherwise see the dying
    # process's memory and mis-pick the Flux quant.
    time.sleep(3)
    return ensure_comfyui(log_dir=log_dir)


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


def _upload_image_to_comfyui(path: str) -> str:
    """Upload a local image to ComfyUI's input dir; return the name a ``LoadImage``
    node references.

    ComfyUI's core ``LoadImage`` only reads from its own ``input`` directory (it
    can't load an arbitrary absolute path), so a character-reference PNG sitting
    under the project asset folder has to be POSTed to ``/upload/image`` first.
    ``overwrite=true`` keeps the input dir from accumulating ``ref (1).png`` dupes
    across re-runs. Returns the ``subfolder/name`` (or bare ``name``) string.
    """
    p = Path(path)
    boundary = f"----mtgai{uuid.uuid4().hex}"
    parts: list[bytes] = []
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(f'Content-Disposition: form-data; name="image"; filename="{p.name}"\r\n'.encode())
    parts.append(b"Content-Type: application/octet-stream\r\n\r\n")
    parts.append(p.read_bytes())
    parts.append(f"\r\n--{boundary}\r\n".encode())
    parts.append(b'Content-Disposition: form-data; name="overwrite"\r\n\r\n')
    parts.append(b"true")
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)

    req = urllib.request.Request(
        f"{COMFYUI_URL}/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    name = result["name"]
    subfolder = result.get("subfolder", "")
    return f"{subfolder}/{name}" if subfolder else name


def _apply_character_refs(workflow: dict, ref_paths: list[str]) -> bool:
    """Inject PuLID-Flux character face-lock conditioning into the Flux workflow.

    Reads the resolved reference-image paths a card carries via
    ``Card.art_character_refs`` (produced by the ``char_portraits`` stage) and
    wires the bundled ``flux_dev_gguf.json`` graph so a card featuring a recurring
    *character* is generated with that character's face locked, not a fresh
    interpretation. The caller (``generate_art_for_set``) has already narrowed
    ``ref_paths`` to a single humanoid-character ref (PuLID locks one identity;
    multi-face masking is out of scope), so this wires the first existing path.

    Graph (ComfyUI-PuLID-Flux custom nodes): PulidFluxModelLoader +
    PulidFluxEvaClipLoader + PulidFluxInsightFaceLoader feed ``ApplyPulidFlux``,
    which patches the UnetLoaderGGUF model (node ``"1"``); the KSampler (node
    ``"8"``) model input is rewired to the patched model. The ref PNG is uploaded
    to ComfyUI's input dir and loaded via ``LoadImage``.

    Returns True when the graph was wired (so metadata reports refs applied),
    False when there's nothing to apply or the upload failed — the caller then
    falls back to plain text-to-image. Note: a wired graph whose ref image has no
    detectable face has PuLID gracefully no-op at run time (it returns the
    unpatched model), so "wired" is not a guarantee a face was found.
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

    ref_path = existing[0]
    try:
        uploaded = _upload_image_to_comfyui(ref_path)
    except Exception as e:
        logger.warning(
            "  Character ref upload to ComfyUI failed (%s) — generating without face-lock: %s",
            Path(ref_path).name,
            e,
        )
        return False

    # Namespaced node ids so the injected nodes never collide with the base
    # workflow's "1".."10".
    workflow["pulid_model"] = {
        "class_type": "PulidFluxModelLoader",
        "inputs": {"pulid_file": PULID_FLUX_MODEL},
    }
    workflow["pulid_eva"] = {"class_type": "PulidFluxEvaClipLoader", "inputs": {}}
    workflow["pulid_face"] = {
        "class_type": "PulidFluxInsightFaceLoader",
        "inputs": {"provider": PULID_INSIGHTFACE_PROVIDER},
    }
    workflow["pulid_image"] = {"class_type": "LoadImage", "inputs": {"image": uploaded}}
    workflow["pulid_apply"] = {
        "class_type": "ApplyPulidFlux",
        "inputs": {
            "model": ["1", 0],
            "pulid_flux": ["pulid_model", 0],
            "eva_clip": ["pulid_eva", 0],
            "face_analysis": ["pulid_face", 0],
            "image": ["pulid_image", 0],
            "weight": PULID_WEIGHT,
            "start_at": 0.0,
            "end_at": 1.0,
        },
    }
    # Route the KSampler through the PuLID-patched model.
    workflow["8"]["inputs"]["model"] = ["pulid_apply", 0]
    logger.info("  PuLID-Flux face-lock wired from ref: %s", Path(ref_path).name)
    return True


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

    # Pick the Flux quant that fits the GPU and inject it into the UnetLoaderGGUF
    # node (the JSON default is the safe floor; this upgrades to Q8 when there's
    # headroom and re-pins Q5 when there isn't).
    quant = select_flux_quant()
    workflow["1"]["inputs"]["unet_name"] = quant

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
        "model": quant.removesuffix(".gguf"),
        "character_refs_applied": refs_applied,
    }
    return image_data, metadata


# Hosted providers we route through llmfacade. "google" is llmfacade's alias
# for "gemini"; both resolve to the Gemini-native image path.
_HOSTED_PROVIDERS = frozenset({"openai", "gemini", "google"})

# Per-provider default model id, used only when the registry entry omits one.
_HOSTED_DEFAULT_MODEL = {
    "openai": "gpt-image-1",
    "gemini": "gemini-2.5-flash-image",
    "google": "gemini-2.5-flash-image",
}


def _openai_size(width: int, height: int, model_id: str | None) -> str:
    """Map our art window to the nearest OpenAI-supported size string.

    OpenAI's image models reject arbitrary sizes: our 4:3-ish landscape default
    (1024x768) is not valid for either family, so we snap to the closest
    supported landscape/portrait size. gpt-image-1: 1024x1024 / 1536x1024 /
    1024x1536; dall-e-3: 1024x1024 / 1792x1024 / 1024x1792.
    """
    landscape = width >= height
    mid = (model_id or "").lower()
    if "dall-e" in mid:
        return "1792x1024" if landscape else "1024x1792"
    return "1536x1024" if landscape else "1024x1536"


def _aspect_ratio(width: int, height: int) -> str:
    """Reduce a pixel WxH to the simple ``w:h`` ratio Gemini's image_config wants
    (1024x768 -> ``4:3``). Gemini ignores ``size`` and takes ``aspect_ratio``."""
    from math import gcd

    g = gcd(width, height) or 1
    return f"{width // g}:{height // g}"


def generate_image_hosted(
    prompt: str,
    provider: str,
    *,
    model_id: str | None = None,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    ref_paths: list[str] | None = None,
) -> tuple[bytes, dict]:
    """Generate an image via a hosted provider (OpenAI / Gemini) through llmfacade.

    Routes to ``LLM.default().generate_image`` (the same manager ``llm_client``
    configures, so ``.env`` API keys are shared). ``model_id`` is the provider's
    image model (resolved from the registry by the caller); when omitted we fall
    back to the provider's default. Sizing is provider-specific: OpenAI takes a
    constrained ``size``, Gemini an ``aspect_ratio``, so we map our pixel art
    window accordingly. ``ref_paths`` that exist on disk become
    ``reference_images`` (provider reference-conditioning: OpenAI's edit
    endpoint, Gemini inline parts). Returns ``(image_bytes, metadata)``.
    """
    from llmfacade import LLM
    from llmfacade.models import ImageBlock

    if model_id is None:
        model_id = _HOSTED_DEFAULT_MODEL.get(provider)

    # Reference conditioning: only forward refs that actually exist on disk
    # (char_portraits may not have produced them yet).
    reference_images: list[ImageBlock] | None = None
    if ref_paths:
        existing = [p for p in ref_paths if Path(p).exists()]
        if existing:
            reference_images = [ImageBlock.from_path(p) for p in existing]

    call_kwargs: dict = {
        "provider": "google" if provider in ("gemini", "google") else provider,
        "model": model_id,
        "reference_images": reference_images,
    }
    if provider == "openai":
        call_kwargs["size"] = _openai_size(width, height, model_id)
    else:  # gemini / google
        call_kwargs["aspect_ratio"] = _aspect_ratio(width, height)

    start = time.time()
    result = LLM.default().generate_image(prompt, **call_kwargs)
    elapsed = time.time() - start

    if not result.images:
        raise RuntimeError(f"Hosted image provider {provider!r} returned no images")
    block = result.images[0]

    usage = result.usage
    metadata = {
        "backend": f"llmfacade_{provider}",
        "provider": provider,
        "model": result.model or model_id,
        "media_type": block.media_type,
        "width": width,
        "height": height,
        "elapsed_seconds": round(elapsed, 1),
        "character_refs_applied": reference_images is not None,
        "input_tokens": usage.input_tokens if usage else 0,
        "output_tokens": usage.output_tokens if usage else 0,
        "image_count": usage.image_count if usage else len(result.images),
    }
    return block.data, metadata


def generate_image(
    prompt: str,
    *,
    provider: str = "comfyui",
    model_id: str | None = None,
    seed: int | None = None,
    ref_paths: list[str] | None = None,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> tuple[bytes, dict]:
    """Provider-dispatching single-image generation entry point.

    - ``comfyui`` -> local Flux (a direct ComfyUI path, no llmfacade).
    - ``openai`` / ``gemini`` -> hosted, routed through llmfacade's
      ``generate_image``. ``model_id`` is the provider image model (from the
      registry); ``None`` falls back to the provider default.

    Other providers raise ``ValueError``. The Art Generation stage calls this
    per candidate version; it resolves the provider + model id from the active
    project's ``art_gen`` image assignment.
    """
    if provider == "comfyui":
        return generate_image_comfyui(
            prompt, seed=seed, ref_paths=ref_paths, width=width, height=height
        )
    if provider in _HOSTED_PROVIDERS:
        return generate_image_hosted(
            prompt, provider, model_id=model_id, ref_paths=ref_paths, width=width, height=height
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


def _resolve_flux_character_ref(card, set_dir: Path) -> tuple[str, str] | None:
    """The single ``(entity_key, abs_path)`` humanoid-character ref to face-lock, or None.

    The local-Flux/PuLID path conditions on *one humanoid character's face* (scope
    decision: characters only — not locations/factions; max one per card, since
    PuLID locks a single identity). Walks the card's ``art_character_refs`` in
    order and returns the first whose entity is a ``legendary_characters`` entry
    *and* whose image exists on disk. Returns None when the card has no character
    ref (the run then falls back to plain text-to-image).
    """
    from mtgai.art import visual_reference

    for ref in getattr(card, "art_character_refs", None) or []:
        entity_key = getattr(ref, "entity_key", None)
        raw = getattr(ref, "ref_image_path", None)
        if not entity_key or not raw:
            continue
        try:
            if not visual_reference.is_character_entity(entity_key):
                continue
        except Exception:
            continue
        p = Path(raw)
        if not p.is_absolute():
            p = set_dir / raw
        if p.exists():
            return entity_key, str(p)
    return None


def _substitute_entity_name(prompt: str, entity_key: str) -> str:
    """Swap a face-locked character's *name* in the prompt for its appearance prose.

    Flux's T5/CLIP text encoder can't resolve a name ("Optimus Prime" means
    nothing to it) and PuLID injects the face embedding separately from the text,
    so a name-based art prompt is replaced — at send time, on the Flux path only —
    with the entity's appearance description from the visual-reference dict:
    "Optimus Prime raising a fist" -> "a towering blue-and-red robot ... raising a
    fist", while PuLID supplies the actual face. A no-op when the name isn't in the
    prompt (today's prompts are already appearance-based) or the entity has no
    description — so it's harmless ahead of the name-based-prompt sibling work and
    activates automatically once prompts go name-based. Only the *face-locked*
    entity is substituted; other named entities are the appearance-text path's job.
    """
    from mtgai.art import visual_reference

    try:
        appearance = visual_reference.get_character_appearance(entity_key)
    except Exception:
        appearance = None
    if not appearance:
        return prompt
    pattern = re.compile(re.escape(entity_key), re.IGNORECASE)
    if not pattern.search(prompt):
        return prompt
    # Function replacement so backslashes/group-refs in the LLM-authored appearance
    # prose are taken verbatim (a plain string replacement would interpret \1, \g).
    return pattern.sub(lambda _m: appearance, prompt)


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


def _resolve_image_model():
    """The ``ImageModel`` assigned to ``art_gen``, or ``None``.

    Returns ``None`` when no project is open or the assigned key can't be
    resolved, so callers degrade to local Flux/ComfyUI.
    """
    try:
        from mtgai.runtime.active_project import require_active_project
        from mtgai.settings.model_registry import get_registry

        key = require_active_project().settings.get_image_model_key("art_gen")
        return get_registry().get_image(key)
    except Exception:
        return None


def _resolve_provider() -> str:
    """The image provider for the ``art_gen`` stage (from its image assignment).

    Falls back to local Flux/ComfyUI when no project is open or the assigned
    model can't be resolved.
    """
    model = _resolve_image_model()
    return model.provider if model is not None else "comfyui"


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
    image_model = _resolve_image_model()
    provider = image_model.provider if image_model is not None else "comfyui"
    model_id = image_model.model_id if image_model is not None else None

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
    # Images generated since the last ComfyUI restart — drives the periodic
    # recycle that bounds VRAM accumulation (see COMFYUI_RECYCLE_EVERY).
    images_since_recycle = 0
    recycle_enabled = not dry_run and provider == "comfyui" and COMFYUI_RECYCLE_EVERY > 0

    try:
        for card_idx, card_file in enumerate(card_files):
            if should_cancel is not None and should_cancel():
                logger.info("Art generation cancelled by user after %d card(s)", generated)
                cancelled = True
                break

            card = load_card(card_file)
            cn = card.collector_number

            # Skip cards the finalize sanity gate soft-excluded (defence in depth —
            # they normally have no art_prompt, so the next check would catch them).
            if card.sanity_excluded:
                logger.info("SKIP %s — excluded by finalize sanity check", cn)
                skipped += 1
                continue

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

            # Reference conditioning diverges by provider. Local Flux/PuLID locks a
            # single humanoid character's face, so it takes at most one character
            # ref and substitutes that character's name in the prompt for its
            # appearance (PuLID supplies the face). Hosted providers forward every
            # ref as generic image-conditioning and keep the prompt verbatim.
            effective_prompt = card.art_prompt
            if provider == "comfyui":
                char_ref = _resolve_flux_character_ref(card, set_dir)
                if char_ref is not None:
                    entity_key, ref_path = char_ref
                    ref_paths = [ref_path]
                    effective_prompt = _substitute_entity_name(card.art_prompt, entity_key)
                else:
                    ref_paths = []
            else:
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
            logger.info("  Prompt: %s", effective_prompt[:100] + "...")

            if dry_run:
                generated += 1
                continue

            # Best-of-N: generate ``n_versions`` candidates numbered v1..vN
            # (gaps only where a version exhausts its retries). On a non-force
            # resume the card was never recorded ``completed`` (else it'd have
            # been skipped above), so any ``*_v*.png`` on disk are crash-orphans
            # from a run killed mid-card — delete them, plus their per-version
            # log sidecars, so we regenerate exactly N instead of appending N
            # fresh after the K orphans. The old ``base_version = len(existing)``
            # left K+N PNGs, which the disk-globbing art selector then judged as
            # K+N candidates instead of N. ``force`` overwrites v1..vN in place
            # (its existing contract) and deliberately does NOT delete higher
            # versions: a user-uploaded extra (v(N+1), source="user") only
            # attaches to a *completed* card, which the resume path never
            # reaches, so leaving force untouched can't orphan that upload's
            # saved pick.
            if not force:
                for stale in (
                    *art_dir.glob(f"{slug}_v*.png"),
                    *log_dir.glob(f"{cn}_v*.json"),
                ):
                    try:
                        stale.unlink(missing_ok=True)
                    except OSError as e:
                        # A locked orphan (Windows file handle) degrades to the
                        # old K+N rather than killing the whole run.
                        logger.warning("Could not delete stale art file %s: %s", stale, e)

            saved_versions: list[dict] = []
            version_errors: list[dict] = []
            for i in range(1, n_versions + 1):
                version = i
                dest = art_dir / f"{slug}_v{version}.png"
                for attempt in range(1, max_attempts_per_version + 1):
                    try:
                        image_data, metadata = generate_image(
                            effective_prompt,
                            provider=provider,
                            model_id=model_id,
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
                            "prompt": effective_prompt,
                            "output_path": str(dest),
                            "file_size_bytes": len(image_data),
                            "character_refs": ref_paths,
                            **(
                                {"original_prompt": card.art_prompt}
                                if effective_prompt != card.art_prompt
                                else {}
                            ),
                            **metadata,
                        }
                        atomic_write_text(
                            log_dir / f"{cn}_v{version}.json", json.dumps(log_entry, indent=2)
                        )
                        saved_versions.append({"version": version, "path": str(dest)})
                        break
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

            # Bound VRAM accumulation: every COMFYUI_RECYCLE_EVERY GPU generations,
            # restart ComfyUI so the OS reclaims all GPU memory (the per-image flush
            # can't). Recycle at the card boundary (never mid-card) so a card's
            # versions stay on one session. We count every Flux *attempt* that ran —
            # saved or failed — because each one loaded the GPU and contributes to
            # the accumulation; for the common no-retry case that's exactly the
            # image count, and a retry-heavy run just recycles a little sooner
            # (harmless — the threshold is a safety floor, not a precise budget).
            images_since_recycle += len(saved_versions) + len(version_errors)
            is_last_card = card_idx == len(card_files) - 1
            if (
                recycle_enabled
                and not is_last_card
                and images_since_recycle >= COMFYUI_RECYCLE_EVERY
            ):
                comfyui_proc = recycle_comfyui(comfyui_proc, log_dir=log_dir)
                images_since_recycle = 0

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
