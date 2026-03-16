"""Image generation pipeline for card art.

Generates art images for cards using their pre-built art prompts.
Supports local ComfyUI (Flux GGUF) with a swappable backend design
for future cloud API integration (fal.ai, Replicate, Midjourney).

Prerequisites:
    - ComfyUI running at http://127.0.0.1:8188
    - Flux.1-dev GGUF + T5-XXL + CLIP-L + VAE loaded
    - Art prompts already generated on card JSONs (see prompt_builder.py)

CLI usage:
    python -m mtgai.art.image_generator --set ASD [--card W-C-01] [--dry-run]
"""

import argparse
import json
import logging
import random
import subprocess
import time
import urllib.request
from pathlib import Path

from mtgai.io.card_io import load_card
from mtgai.io.paths import art_path, card_slug

logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path("C:/Programming/MTGAI/output")
COMFYUI_ROOT = Path("C:/Programming/ComfyUI")
COMFYUI_URL = "http://127.0.0.1:8188"
WORKFLOW_PATH = Path("C:/Programming/MTGAI/backend/mtgai/art/workflows/flux_dev_gguf.json")

# Generation defaults
DEFAULT_STEPS = 30
DEFAULT_GUIDANCE = 3.5
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 768
POLL_INTERVAL = 3  # seconds between completion checks
GENERATION_TIMEOUT = 600  # 10 minutes max per image (cold start model loading can take 3-5 min)


# Minimum free VRAM required (MB) — Flux Q8_0 needs ~9.6GB for models + ~1GB compute
MIN_VRAM_FREE_MB = 10_500


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


def start_comfyui() -> subprocess.Popen:
    """Start ComfyUI server as a subprocess."""
    python_exe = COMFYUI_ROOT / "venv" / "Scripts" / "python.exe"
    main_py = COMFYUI_ROOT / "main.py"

    if not python_exe.exists():
        raise FileNotFoundError(f"ComfyUI Python not found: {python_exe}")

    logger.info("Starting ComfyUI server...")
    # Use DEVNULL for stdout/stderr to avoid Windows pipe issues
    # (tqdm progress bars crash with OSError: [Errno 22] on piped stderr)
    proc = subprocess.Popen(
        [str(python_exe), str(main_py), "--listen", "127.0.0.1", "--port", "8188"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(COMFYUI_ROOT),
    )

    # Wait for server to become responsive
    for i in range(60):
        time.sleep(2)
        if is_comfyui_running():
            logger.info("ComfyUI ready after %ds", (i + 1) * 2)
            return proc
        if proc.poll() is not None:
            raise RuntimeError("ComfyUI process exited unexpectedly")

    proc.kill()
    raise TimeoutError("ComfyUI failed to start within 120 seconds")


def ensure_comfyui() -> subprocess.Popen | None:
    """Ensure ComfyUI is running. Starts it if needed. Returns process or None.

    Checks VRAM availability before starting to fail fast with an
    actionable error instead of crashing mid-generation.
    """
    if is_comfyui_running():
        logger.info("ComfyUI already running at %s", COMFYUI_URL)
        return None
    check_vram()
    return start_comfyui()


def kill_comfyui(proc: subprocess.Popen | None = None) -> None:
    """Kill ComfyUI and free VRAM. Works whether we started it or it was already running.

    Tries the process handle first (if we started it), then falls back to
    finding and killing the ComfyUI Python process by its command line.
    """
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
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            raise TimeoutError(f"Generation timed out after {timeout}s")

        try:
            resp = urllib.request.urlopen(f"{COMFYUI_URL}/history/{prompt_id}")
            history = json.loads(resp.read())
        except Exception:
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
    resp = urllib.request.urlopen(f"{COMFYUI_URL}/view?{params}")
    return resp.read()


# ---------------------------------------------------------------------------
# Image generation (local ComfyUI backend)
# ---------------------------------------------------------------------------


def generate_image_comfyui(
    prompt: str,
    seed: int | None = None,
    steps: int = DEFAULT_STEPS,
    guidance: float = DEFAULT_GUIDANCE,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> tuple[bytes, dict]:
    """Generate an image via local ComfyUI.

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

    # Queue and wait
    prompt_id = _queue_prompt(workflow)
    logger.info("  Queued prompt %s (seed=%s)", prompt_id[:8], workflow["8"]["inputs"]["seed"])

    result = _poll_completion(prompt_id)
    logger.info("  Generated in %.1fs: %s", result["elapsed"], result["filename"])

    # Download the image
    image_data = _download_image(result["filename"], result["subfolder"])

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
    }
    return image_data, metadata


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
    progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")


def generate_art_for_set(
    set_code: str,
    card_filter: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    max_attempts: int = 2,
) -> dict:
    """Generate art images for all cards in a set.

    Args:
        set_code: The set code (e.g., "ASD").
        card_filter: Optional collector number prefix to filter cards.
        dry_run: If True, log what would be done but don't generate.
        force: If True, regenerate even if art already exists.
        max_attempts: Max generation attempts per card.

    Returns summary dict with stats.
    """
    cards_dir = OUTPUT_ROOT / "sets" / set_code / "cards"
    art_dir = OUTPUT_ROOT / "sets" / set_code / "art"
    log_dir = OUTPUT_ROOT / "sets" / set_code / "art-generation-logs"
    art_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Progress file for resumability
    progress_path = log_dir / "progress.json"
    progress = _load_progress(progress_path)

    # Load all card files
    card_files = sorted(cards_dir.glob("*.json"))
    if card_filter:
        card_files = [f for f in card_files if f.name.startswith(card_filter)]

    if not card_files:
        raise ValueError(f"No cards found matching filter: {card_filter}")

    # Ensure ComfyUI is running (unless dry run)
    comfyui_proc = None
    if not dry_run:
        comfyui_proc = ensure_comfyui()

    generated = 0
    skipped = 0
    failed = 0
    errors = []

    try:
        for card_file in card_files:
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

            # Determine version number
            existing = list(art_dir.glob(f"{card_slug(cn, card.name)}_v*.png"))
            version = len(existing) + 1
            if force:
                version = 1  # overwrite

            dest = art_path(OUTPUT_ROOT, set_code, cn, card.name, version=version)

            logger.info(
                "GENERATE %s: %s (v%d)%s",
                cn,
                card.name,
                version,
                " [DRY RUN]" if dry_run else "",
            )
            logger.info("  Prompt: %s", card.art_prompt[:100] + "...")

            if dry_run:
                generated += 1
                continue

            # Generate with retry
            attempt_errors = []
            for attempt in range(1, max_attempts + 1):
                try:
                    image_data, metadata = generate_image_comfyui(
                        prompt=card.art_prompt,
                    )

                    # Save image
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(image_data)
                    logger.info(
                        "  SAVED %s (%.1fs, %s bytes)",
                        dest.name,
                        metadata["elapsed_seconds"],
                        f"{len(image_data):,}",
                    )

                    # Log generation details
                    log_entry = {
                        "collector_number": cn,
                        "name": card.name,
                        "version": version,
                        "attempt": attempt,
                        "prompt": card.art_prompt,
                        "output_path": str(dest),
                        "file_size_bytes": len(image_data),
                        **metadata,
                    }
                    log_path = log_dir / f"{cn}_v{version}.json"
                    log_path.write_text(json.dumps(log_entry, indent=2), encoding="utf-8")

                    # Track progress
                    progress["completed"][cn] = {
                        "version": version,
                        "path": str(dest),
                        "elapsed": metadata["elapsed_seconds"],
                    }
                    _save_progress(progress, progress_path)

                    generated += 1
                    break

                except Exception as e:
                    logger.error("  ATTEMPT %d/%d failed for %s: %s", attempt, max_attempts, cn, e)
                    attempt_errors.append({"attempt": attempt, "error": str(e)})

                    if attempt < max_attempts:
                        time.sleep(5)
            else:
                # All attempts failed
                failed += 1
                errors.append({"card": cn, "attempts": attempt_errors})
                progress["failed"][cn] = attempt_errors
                _save_progress(progress, progress_path)

    finally:
        # Always kill ComfyUI on exit to free VRAM
        kill_comfyui(comfyui_proc)

    summary = {
        "set_code": set_code,
        "generated": generated,
        "skipped": skipped,
        "failed": failed,
        "errors": errors,
        "dry_run": dry_run,
    }

    # Save summary
    summary_path = log_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Generate card art images via ComfyUI + Flux")
    parser.add_argument("--set", default="ASD", help="Set code (default: ASD)")
    parser.add_argument("--card", default=None, help="Single card collector number (e.g. R-C-01)")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without generating")
    parser.add_argument("--force", action="store_true", help="Regenerate existing art")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    summary = generate_art_for_set(
        set_code=args.set,
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
