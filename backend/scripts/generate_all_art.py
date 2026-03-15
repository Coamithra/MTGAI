"""Generate 3 art versions for every card in the set.

Usage (from backend/):
    .venv/Scripts/python.exe scripts/generate_all_art.py
"""

import json
import logging
import sys
import time
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mtgai.art.image_generator import (
    ensure_comfyui,
    generate_image_comfyui,
)
from mtgai.io.card_io import load_card
from mtgai.io.paths import art_path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path("C:/Programming/MTGAI/output")
VERSIONS_PER_CARD = 3


def main():
    set_code = "ASD"
    cards_dir = OUTPUT_ROOT / "sets" / set_code / "cards"
    art_dir = OUTPUT_ROOT / "sets" / set_code / "art"
    log_dir = OUTPUT_ROOT / "sets" / set_code / "art-generation-logs"
    art_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Progress tracking
    progress_path = log_dir / "batch_progress.json"
    if progress_path.exists():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
    else:
        progress = {"completed": {}}

    # Load all cards
    card_files = sorted(cards_dir.glob("*.json"))
    cards = []
    for cf in card_files:
        card = load_card(cf)
        if card.art_prompt:
            cards.append(card)
        else:
            logger.warning("SKIP %s — no art_prompt", card.collector_number)

    total_images = len(cards) * VERSIONS_PER_CARD
    already_done = sum(len(v) for v in progress["completed"].values())
    remaining = total_images - already_done

    logger.info(
        "Batch generation: %d cards x %d versions = %d images (%d already done, %d remaining)",
        len(cards),
        VERSIONS_PER_CARD,
        total_images,
        already_done,
        remaining,
    )

    if remaining == 0:
        logger.info("All images already generated!")
        return

    # Start ComfyUI
    comfyui_proc = ensure_comfyui()

    generated = 0
    failed = 0
    start_time = time.time()

    try:
        for card in cards:
            cn = card.collector_number

            # Check which versions exist
            if cn not in progress["completed"]:
                progress["completed"][cn] = []

            existing_versions = progress["completed"][cn]

            for version in range(1, VERSIONS_PER_CARD + 1):
                if version in existing_versions:
                    continue  # Already done

                dest = art_path(OUTPUT_ROOT, set_code, cn, card.name, version=version)

                # Also skip if file already exists on disk
                if dest.exists():
                    logger.info("SKIP %s v%d — file exists", cn, version)
                    if version not in existing_versions:
                        existing_versions.append(version)
                        progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")
                    continue

                logger.info(
                    "[%d/%d] Generating %s v%d: %s",
                    generated + already_done + 1,
                    total_images,
                    cn,
                    version,
                    card.name,
                )

                try:
                    image_data, metadata = generate_image_comfyui(
                        prompt=card.art_prompt,
                    )

                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(image_data)

                    # Per-image log
                    log_entry = {
                        "collector_number": cn,
                        "name": card.name,
                        "version": version,
                        "prompt": card.art_prompt,
                        "output_path": str(dest),
                        "file_size_bytes": len(image_data),
                        **metadata,
                    }
                    img_log = log_dir / f"{cn}_v{version}.json"
                    img_log.write_text(json.dumps(log_entry, indent=2), encoding="utf-8")

                    # Update progress
                    existing_versions.append(version)
                    progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")

                    generated += 1
                    elapsed = time.time() - start_time
                    rate = generated / elapsed if elapsed > 0 else 0
                    eta = (remaining - generated) / rate if rate > 0 else 0
                    logger.info(
                        "  SAVED %s (%.1fs) — %d done, ETA %.0f min",
                        dest.name,
                        metadata["elapsed_seconds"],
                        generated,
                        eta / 60,
                    )

                except Exception as e:
                    logger.error("  FAILED %s v%d: %s", cn, version, e)
                    failed += 1
                    time.sleep(5)  # Brief pause on error

    except KeyboardInterrupt:
        logger.info("Interrupted! Progress saved — resume by running again.")
    finally:
        if comfyui_proc is not None:
            logger.info("Shutting down ComfyUI...")
            comfyui_proc.terminate()
            try:
                comfyui_proc.wait(timeout=10)
            except Exception:
                comfyui_proc.kill()

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print("Batch Generation Complete")
    print(f"{'=' * 60}")
    print(f"Generated: {generated}")
    print(f"Failed:    {failed}")
    print(f"Time:      {elapsed / 60:.1f} minutes")
    print(f"Rate:      {elapsed / max(generated, 1):.1f}s per image")
    print("Progress saved — safe to resume if interrupted.")


if __name__ == "__main__":
    main()
