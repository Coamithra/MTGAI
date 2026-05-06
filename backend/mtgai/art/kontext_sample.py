"""Sample card art generation with Flux Kontext Dev for character identity testing.

Generates sample card arts using character reference portraits to evaluate
whether Kontext Dev maintains character identity across different scenes.

For each character-featuring card, generates two versions:
  1. Regular Flux.1-dev (no reference) — baseline
  2. Kontext Dev with character portrait as reference — identity-preserved

This allows side-by-side comparison to evaluate character consistency.

Output: output/sets/<SET>/art-direction/kontext-samples/

CLI usage:
    python -m mtgai.art.kontext_sample --set ASD [--dry-run]
"""

import argparse
import json
import logging
import random
import shutil
import time
import urllib.request
from pathlib import Path

from mtgai.art.image_generator import (
    COMFYUI_URL,
    ensure_comfyui,
    flush_comfyui,
    kill_comfyui,
)

logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path("C:/Programming/MTGAI/output")
COMFYUI_INPUT_DIR = Path("C:/Programming/ComfyUI/input")

WORKFLOW_KONTEXT = Path("C:/Programming/MTGAI/backend/mtgai/art/workflows/flux_kontext_gguf.json")
WORKFLOW_BASELINE = Path("C:/Programming/MTGAI/backend/mtgai/art/workflows/flux_dev_gguf.json")

# Cards that depict legendary characters in their art
SAMPLE_CARDS = [
    {
        "collector_number": "W-M-01",
        "name": "Feretha, the Hollow Founder",
        "character": "feretha",
        "portrait_file": "feretha_the_hollow_founder_v2.png",
    },
    {
        "collector_number": "B-R-01",
        "name": "Koyl Yrenum, the Vizier",
        "character": "koyl",
        "portrait_file": "koyl_yrenum_the_vizier_v3.png",
    },
    {
        "collector_number": "W-R-02",
        "name": "The Vizier's Decree",
        "character": "koyl",
        "portrait_file": "koyl_yrenum_the_vizier_v3.png",
    },
    {
        "collector_number": "B-R-02",
        "name": "The Brain Engine",
        "character": "feretha",
        "portrait_file": "feretha_the_hollow_founder_v2.png",
    },
    {
        "collector_number": "B-M-01",
        "name": "Koyl's Reanimated Maw",
        "character": "koyl",
        "portrait_file": "koyl_yrenum_the_vizier_v3.png",
    },
    {
        "collector_number": "R-U-03",
        "name": "Combustion Cascade",
        "character": "head_scientist",
        "portrait_file": "the_head_scientist_v1.png",
    },
    {
        "collector_number": "W-C-04",
        "name": "Requisition Sweep",
        "character": "feretha",
        "portrait_file": "feretha_the_hollow_founder_v2.png",
    },
]

POLL_INTERVAL = 3
GENERATION_TIMEOUT = 600


def _load_workflow(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _queue_prompt(workflow: dict) -> str:
    payload = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    return result["prompt_id"]


def _poll_completion(prompt_id: str) -> dict:
    start = time.time()
    consecutive_failures = 0
    while True:
        elapsed = time.time() - start
        if elapsed > GENERATION_TIMEOUT:
            raise TimeoutError(f"Generation timed out after {GENERATION_TIMEOUT}s")
        try:
            resp = urllib.request.urlopen(f"{COMFYUI_URL}/history/{prompt_id}")
            history = json.loads(resp.read())
            consecutive_failures = 0
        except Exception as e:
            consecutive_failures += 1
            if consecutive_failures >= 5:
                raise RuntimeError(f"ComfyUI died — {consecutive_failures} failures: {e}") from e
            time.sleep(POLL_INTERVAL)
            continue

        if prompt_id not in history:
            time.sleep(POLL_INTERVAL)
            continue

        entry = history[prompt_id]
        status = entry.get("status", {})
        if status.get("completed") or status.get("status_str") == "success":
            for node_out in entry.get("outputs", {}).values():
                if "images" in node_out:
                    for img in node_out["images"]:
                        return {
                            "filename": img["filename"],
                            "subfolder": img.get("subfolder", ""),
                            "elapsed": elapsed,
                        }
            raise RuntimeError("Completed but no image in outputs")
        if status.get("status_str") == "error":
            error_msg = "Unknown error"
            for msg_type, msg_data in status.get("messages", []):
                if msg_type == "execution_error":
                    error_msg = (
                        f"{msg_data.get('exception_type', '?')}: "
                        f"{msg_data.get('exception_message', '?').strip()} "
                        f"(node: {msg_data.get('node_type', '?')})"
                    )
                    break
            raise RuntimeError(f"ComfyUI error: {error_msg}")
        time.sleep(POLL_INTERVAL)


def _download_image(filename: str, subfolder: str = "") -> bytes:
    params = f"filename={filename}"
    if subfolder:
        params += f"&subfolder={subfolder}"
    resp = urllib.request.urlopen(f"{COMFYUI_URL}/view?{params}")
    return resp.read()


def _copy_portrait_to_comfyui_input(portrait_path: Path) -> str:
    """Copy portrait to ComfyUI's input directory so LoadImage can find it."""
    COMFYUI_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = COMFYUI_INPUT_DIR / portrait_path.name
    if not dest.exists():
        shutil.copy2(portrait_path, dest)
        logger.info("  Copied portrait to ComfyUI input: %s", dest.name)
    return portrait_path.name


def generate_kontext_sample(
    art_prompt: str,
    portrait_path: Path,
    dest: Path,
    seed: int | None = None,
) -> dict:
    """Generate a single image using Kontext with character reference."""
    workflow = _load_workflow(WORKFLOW_KONTEXT)

    # Copy portrait to ComfyUI input dir
    ref_filename = _copy_portrait_to_comfyui_input(portrait_path)

    actual_seed = seed if seed is not None else random.randint(0, 2**32)

    # Inject parameters
    workflow["11"]["inputs"]["image"] = ref_filename
    workflow["4"]["inputs"]["text"] = art_prompt
    workflow["8"]["inputs"]["seed"] = actual_seed
    workflow["8"]["inputs"]["steps"] = 30

    prompt_id = _queue_prompt(workflow)
    logger.info("  Queued Kontext prompt %s (seed=%s)", prompt_id[:8], actual_seed)

    result = _poll_completion(prompt_id)
    logger.info("  Generated in %.1fs", result["elapsed"])

    image_data = _download_image(result["filename"], result["subfolder"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(image_data)

    flush_comfyui()

    return {
        "prompt_id": prompt_id,
        "seed": actual_seed,
        "elapsed_seconds": round(result["elapsed"], 1),
        "file_size_bytes": len(image_data),
        "backend": "kontext_q4_k_s",
    }


def generate_baseline_sample(
    art_prompt: str,
    dest: Path,
    seed: int | None = None,
) -> dict:
    """Generate a single image using regular Flux.1-dev (no reference)."""
    workflow = _load_workflow(WORKFLOW_BASELINE)

    actual_seed = seed if seed is not None else random.randint(0, 2**32)

    workflow["4"]["inputs"]["text"] = art_prompt
    workflow["7"]["inputs"]["width"] = 1024
    workflow["7"]["inputs"]["height"] = 768
    workflow["8"]["inputs"]["seed"] = actual_seed
    workflow["8"]["inputs"]["steps"] = 30

    prompt_id = _queue_prompt(workflow)
    logger.info("  Queued baseline prompt %s (seed=%s)", prompt_id[:8], actual_seed)

    result = _poll_completion(prompt_id)
    logger.info("  Generated in %.1fs", result["elapsed"])

    image_data = _download_image(result["filename"], result["subfolder"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(image_data)

    flush_comfyui()

    return {
        "prompt_id": prompt_id,
        "seed": actual_seed,
        "elapsed_seconds": round(result["elapsed"], 1),
        "file_size_bytes": len(image_data),
        "backend": "flux_dev_q8_0",
    }


def run_samples(set_code: str, dry_run: bool = False) -> dict:
    """Generate Kontext vs baseline comparison samples for character cards."""
    refs_dir = OUTPUT_ROOT / "sets" / set_code / "art-direction" / "character-refs"
    cards_dir = OUTPUT_ROOT / "sets" / set_code / "cards"
    out_dir = OUTPUT_ROOT / "sets" / set_code / "art-direction" / "kontext-samples"
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("Kontext Character Identity Test")
    logger.info("=" * 60)
    logger.info("Sample cards: %d", len(SAMPLE_CARDS))
    logger.info("Output: %s", out_dir)
    logger.info("")

    # Load art prompts from card JSONs
    samples = []
    for card_info in SAMPLE_CARDS:
        cn = card_info["collector_number"]
        card_file = list(cards_dir.glob(f"{cn}_*.json"))
        if not card_file:
            logger.warning("SKIP %s — card file not found", cn)
            continue
        card_data = json.loads(card_file[0].read_text(encoding="utf-8"))
        art_prompt = card_data.get("art_prompt")
        if not art_prompt:
            logger.warning("SKIP %s — no art_prompt", cn)
            continue

        portrait_path = refs_dir / card_info["portrait_file"]
        if not portrait_path.exists():
            logger.warning("SKIP %s — portrait not found: %s", cn, card_info["portrait_file"])
            continue

        samples.append({**card_info, "art_prompt": art_prompt, "portrait_path": portrait_path})
        logger.info("  %s: %s (ref: %s)", cn, card_info["name"], card_info["character"])

    if dry_run:
        logger.info(
            "\n[DRY RUN] Would generate %d x 2 = %d images",
            len(samples),
            len(samples) * 2,
        )
        return {"samples": len(samples), "generated": 0, "dry_run": True}

    # We need to swap models between Kontext and baseline runs.
    # Generate all Kontext samples first, then all baseline samples,
    # to minimize model reloading.
    comfyui_proc = ensure_comfyui()
    generated = 0
    results = []
    start_time = time.time()

    try:
        # Phase 1: Kontext samples (loads kontext model)
        logger.info("\n--- Phase 1: Kontext (with character reference) ---")
        for i, s in enumerate(samples, 1):
            cn = s["collector_number"]
            slug = cn.replace("-", "_").lower()
            dest = out_dir / f"{slug}_kontext.png"

            if dest.exists():
                logger.info("[%d/%d] SKIP %s kontext — exists", i, len(samples), cn)
                generated += 1
                continue

            logger.info("[%d/%d] GENERATE %s kontext...", i, len(samples), cn)
            try:
                meta = generate_kontext_sample(
                    art_prompt=s["art_prompt"],
                    portrait_path=s["portrait_path"],
                    dest=dest,
                )
                results.append({"card": cn, "type": "kontext", **meta})
                generated += 1
            except Exception as e:
                logger.error("  FAILED: %s", e)
                results.append({"card": cn, "type": "kontext", "error": str(e)})

        # Kill ComfyUI to unload Kontext model before loading baseline Flux
        logger.info("\nSwitching models: Kontext → Flux dev...")
        kill_comfyui(comfyui_proc)
        time.sleep(5)
        comfyui_proc = ensure_comfyui()

        # Phase 2: Baseline samples (loads flux-dev model)
        logger.info("\n--- Phase 2: Baseline Flux.1-dev (no reference) ---")
        for i, s in enumerate(samples, 1):
            cn = s["collector_number"]
            slug = cn.replace("-", "_").lower()
            dest = out_dir / f"{slug}_baseline.png"

            if dest.exists():
                logger.info("[%d/%d] SKIP %s baseline — exists", i, len(samples), cn)
                generated += 1
                continue

            logger.info("[%d/%d] GENERATE %s baseline...", i, len(samples), cn)
            try:
                meta = generate_baseline_sample(
                    art_prompt=s["art_prompt"],
                    dest=dest,
                )
                results.append({"card": cn, "type": "baseline", **meta})
                generated += 1
            except Exception as e:
                logger.error("  FAILED: %s", e)
                results.append({"card": cn, "type": "baseline", "error": str(e)})

    finally:
        kill_comfyui(comfyui_proc)

    elapsed = time.time() - start_time

    summary = {
        "samples": len(samples),
        "generated": generated,
        "elapsed_seconds": round(elapsed, 1),
        "results": results,
        "dry_run": False,
    }

    # Save results
    results_path = out_dir / "results.json"
    results_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Generate comparison HTML
    _generate_comparison_html(samples, out_dir)

    return summary


def _generate_comparison_html(
    samples: list[dict],
    out_dir: Path,
) -> None:
    """Generate HTML for side-by-side Kontext vs baseline comparison."""
    # Write as a standalone HTML file — not subject to Python line limits
    html_path = out_dir / "comparison.html"
    refs_dir = "../character-refs"

    rows = []
    for s in samples:
        cn = s["collector_number"]
        slug = cn.replace("-", "_").lower()
        prompt_trunc = s["art_prompt"][:200] + "..."
        rows.append(
            f'<div class="card-comparison">'
            f'<h2>{s["name"]} <span class="cn">({cn})</span></h2>'
            f'<p class="character">Character: {s["character"]}'
            f" &mdash; Portrait: {s['portrait_file']}</p>"
            f'<p class="prompt">{prompt_trunc}</p>'
            f'<div class="images">'
            f'<div class="img-col"><h3>Baseline</h3>'
            f'<img src="{slug}_baseline.png" alt="Baseline"></div>'
            f'<div class="img-col ref-col"><h3>Reference</h3>'
            f'<img src="{refs_dir}/{s["portrait_file"]}"'
            f' alt="Ref" class="portrait"></div>'
            f'<div class="img-col"><h3>Kontext</h3>'
            f'<img src="{slug}_kontext.png" alt="Kontext"></div>'
            f"</div></div>"
        )

    body = "\n".join(rows)
    html_path.write_text(
        "<!DOCTYPE html><html><head><meta charset=UTF-8>"
        "<title>Kontext vs Baseline</title><style>"
        "*{margin:0;padding:0;box-sizing:border-box}"
        "body{background:#1a1a2e;color:#e0e0e0;"
        "font-family:'Segoe UI',system-ui,sans-serif;padding:2rem}"
        "h1{text-align:center;color:#c9a54e;margin-bottom:.3rem}"
        ".subtitle{text-align:center;color:#888;margin-bottom:2rem}"
        ".card-comparison{background:#16213e;border-radius:12px;"
        "padding:1.5rem;margin-bottom:2rem;border:1px solid #0f3460}"
        ".card-comparison h2{color:#e0c97f;margin-bottom:.3rem}"
        ".cn{color:#888;font-size:.85rem;font-weight:normal}"
        ".character{color:#6a9fd8;font-size:.85rem;margin-bottom:.3rem}"
        ".prompt{color:#777;font-size:.8rem;font-style:italic;"
        "margin-bottom:1rem;max-width:100ch}"
        ".images{display:flex;gap:1rem;align-items:flex-start}"
        ".img-col{flex:1;text-align:center}"
        ".img-col h3{font-size:.9rem;margin-bottom:.5rem;color:#aaa}"
        ".img-col img{width:100%;border-radius:6px;"
        "border:2px solid #0f3460}"
        ".ref-col{flex:.6}"
        ".portrait{max-height:350px;width:auto!important}"
        "</style></head><body>"
        "<h1>Kontext vs Baseline</h1>"
        '<p class="subtitle">Does Flux Kontext Dev preserve '
        "character identity from reference portraits?</p>"
        f"{body}</body></html>",
        encoding="utf-8",
    )
    logger.info("Comparison HTML: %s", html_path)


def main():
    import sys

    print(
        "kontext_sample is legacy A/B-test tooling and was not migrated to the\n"
        ".mtg / asset_folder layout. It still hardcodes paths under\n"
        "output/sets/<CODE>/ and will read empty inputs / write outputs in the\n"
        "wrong place for any project whose asset_folder is configured.\n"
        "\n"
        "If you actually need this script, port its paths through\n"
        "mtgai.io.asset_paths.set_artifact_dir first (see kontext_sample.py:453)\n"
        "and remove this guard.",
        file=sys.stderr,
    )
    sys.exit(2)

    # ---- legacy body below (left in place for the eventual port) ----
    parser = argparse.ArgumentParser(description="Kontext character identity test samples")
    parser.add_argument("--set", default="ASD", help="Set code")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    log_dir = OUTPUT_ROOT / "sets" / args.set / "art-direction" / "kontext-samples"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "run.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(str(log_file), mode="a", encoding="utf-8"),
        ],
    )

    summary = run_samples(set_code=args.set, dry_run=args.dry_run)

    print(f"\n{'=' * 60}")
    print(f"Kontext Sample Generation — {args.set}")
    print(f"{'=' * 60}")
    print(f"Samples:   {summary['samples']}")
    print(f"Generated: {summary['generated']}")
    if not summary["dry_run"]:
        print(f"Elapsed:   {summary['elapsed_seconds']:.0f}s")


if __name__ == "__main__":
    main()
