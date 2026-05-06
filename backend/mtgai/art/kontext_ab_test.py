"""Quick A/B test for Kontext reference methods.

Generates the same 2 cards with 3 different reference methods to find
the best balance between identity preservation and style independence.

Methods tested:
  - offset (default): strongest reference influence
  - index: moderate reference influence
  - index_timestep_zero: weakest, reference only at initial timestep

Output: output/sets/ASD/art-direction/kontext-samples/ab-test/

CLI: python -m mtgai.art.kontext_ab_test --set ASD
"""

import json
import logging
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
WORKFLOW_PATH = Path("C:/Programming/MTGAI/backend/mtgai/art/workflows/flux_kontext_gguf.json")

# Test with 2 cards that had the worst copy-paste effect
TEST_CARDS = [
    {
        "collector_number": "W-M-01",
        "name": "Feretha, the Hollow Founder",
        "portrait_file": "feretha_the_hollow_founder_v2.png",
    },
    {
        "collector_number": "B-R-01",
        "name": "Koyl Yrenum, the Vizier",
        "portrait_file": "koyl_yrenum_the_vizier_v3.png",
    },
]

METHODS = ["offset", "index"]

POLL_INTERVAL = 3
GENERATION_TIMEOUT = 600


def _queue_prompt(workflow: dict) -> str:
    payload = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())["prompt_id"]


def _poll_completion(prompt_id: str) -> dict:
    start = time.time()
    consecutive_failures = 0
    while True:
        elapsed = time.time() - start
        if elapsed > GENERATION_TIMEOUT:
            raise TimeoutError(f"Timed out after {GENERATION_TIMEOUT}s")
        try:
            resp = urllib.request.urlopen(f"{COMFYUI_URL}/history/{prompt_id}")
            history = json.loads(resp.read())
            consecutive_failures = 0
        except Exception as e:
            consecutive_failures += 1
            if consecutive_failures >= 5:
                raise RuntimeError(f"ComfyUI died: {e}") from e
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
            raise RuntimeError("No image in outputs")
        if status.get("status_str") == "error":
            for msg_type, msg_data in status.get("messages", []):
                if msg_type == "execution_error":
                    raise RuntimeError(
                        f"{msg_data.get('exception_type')}: {msg_data.get('exception_message')}"
                    )
            raise RuntimeError("Unknown ComfyUI error")
        time.sleep(POLL_INTERVAL)


def _download_image(filename: str, subfolder: str = "") -> bytes:
    params = f"filename={filename}"
    if subfolder:
        params += f"&subfolder={subfolder}"
    resp = urllib.request.urlopen(f"{COMFYUI_URL}/view?{params}")
    return resp.read()


def main():
    import sys

    print(
        "kontext_ab_test is legacy A/B-test tooling and was not migrated to the\n"
        ".mtg / asset_folder layout. It still hardcodes paths under\n"
        "output/sets/<CODE>/ and will read empty inputs / write outputs in the\n"
        "wrong place for any project whose asset_folder is configured.\n"
        "\n"
        "If you actually need this script, port its paths through\n"
        "mtgai.io.asset_paths.set_artifact_dir first (see kontext_ab_test.py:125)\n"
        "and remove this guard.",
        file=sys.stderr,
    )
    sys.exit(2)

    # ---- legacy body below (left in place for the eventual port) ----
    import argparse

    parser = argparse.ArgumentParser(description="A/B test Kontext reference methods")
    parser.add_argument("--set", default="ASD")
    args = parser.parse_args()

    set_code = args.set
    refs_dir = OUTPUT_ROOT / "sets" / set_code / "art-direction" / "character-refs"
    cards_dir = OUTPUT_ROOT / "sets" / set_code / "cards"
    out_dir = OUTPUT_ROOT / "sets" / set_code / "art-direction" / "kontext-samples" / "ab-test"
    out_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Use a fixed seed so the only variable is the method
    fixed_seed = 777777777

    comfyui_proc = ensure_comfyui()

    try:
        for card in TEST_CARDS:
            cn = card["collector_number"]
            slug = cn.replace("-", "_").lower()

            # Load art prompt
            card_file = list(cards_dir.glob(f"{cn}_*.json"))
            if not card_file:
                logger.warning("Card %s not found, skipping", cn)
                continue
            card_data = json.loads(card_file[0].read_text(encoding="utf-8"))
            art_prompt = card_data.get("art_prompt", "")

            # Copy portrait to ComfyUI input
            portrait_path = refs_dir / card["portrait_file"]
            COMFYUI_INPUT_DIR.mkdir(parents=True, exist_ok=True)
            dest_portrait = COMFYUI_INPUT_DIR / portrait_path.name
            if not dest_portrait.exists():
                shutil.copy2(portrait_path, dest_portrait)

            for method in METHODS:
                dest = out_dir / f"{slug}_{method}.png"
                if dest.exists():
                    logger.info("SKIP %s %s — exists", cn, method)
                    continue

                logger.info("GENERATE %s [%s] %s...", cn, method, card["name"])

                workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))

                # Set reference image, prompt, seed
                workflow["11"]["inputs"]["image"] = portrait_path.name
                workflow["4"]["inputs"]["text"] = art_prompt
                workflow["8"]["inputs"]["seed"] = fixed_seed
                workflow["8"]["inputs"]["steps"] = 30

                # Set the reference method
                workflow["15"]["inputs"]["reference_latents_method"] = method

                prompt_id = _queue_prompt(workflow)
                logger.info("  Queued %s (method=%s)", prompt_id[:8], method)

                result = _poll_completion(prompt_id)
                image_data = _download_image(result["filename"], result["subfolder"])
                dest.write_bytes(image_data)
                logger.info("  SAVED %s (%.1fs)", dest.name, result["elapsed"])

                flush_comfyui()

    finally:
        kill_comfyui(comfyui_proc)

    # Generate comparison HTML
    _generate_html(TEST_CARDS, refs_dir, out_dir)
    logger.info("Done! Open: %s", out_dir / "comparison.html")


def _generate_html(
    cards: list[dict],
    refs_dir: Path,
    out_dir: Path,
) -> None:
    rows = []
    for card in cards:
        cn = card["collector_number"]
        slug = cn.replace("-", "_").lower()
        ref_path = f"../../character-refs/{card['portrait_file']}"
        rows.append(
            f'<div class="card">'
            f"<h2>{card['name']} ({cn})</h2>"
            f'<div class="images">'
            f'<div class="col"><h3>Reference</h3>'
            f'<img src="{ref_path}" class="portrait"></div>'
        )
        for method in METHODS:
            rows.append(f'<div class="col"><h3>{method}</h3><img src="{slug}_{method}.png"></div>')
        rows.append("</div></div>")

    body = "\n".join(rows)
    html = (
        "<!DOCTYPE html><html><head><meta charset=UTF-8>"
        "<title>Kontext A/B: Reference Methods</title><style>"
        "*{margin:0;padding:0;box-sizing:border-box}"
        "body{background:#1a1a2e;color:#e0e0e0;"
        "font-family:'Segoe UI',system-ui,sans-serif;padding:2rem}"
        "h1{text-align:center;color:#c9a54e;margin-bottom:1.5rem}"
        ".card{background:#16213e;border-radius:12px;"
        "padding:1.5rem;margin-bottom:2rem;"
        "border:1px solid #0f3460}"
        ".card h2{color:#e0c97f;margin-bottom:1rem}"
        ".images{display:flex;gap:1rem;align-items:flex-start}"
        ".col{flex:1;text-align:center}"
        ".col h3{font-size:.85rem;margin-bottom:.5rem;color:#aaa}"
        ".col img{width:100%;border-radius:6px;"
        "border:2px solid #0f3460}"
        ".portrait{max-height:300px;width:auto!important}"
        "</style></head><body>"
        "<h1>Kontext A/B: Reference Methods</h1>"
        f"{body}</body></html>"
    )
    path = out_dir / "comparison.html"
    path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
