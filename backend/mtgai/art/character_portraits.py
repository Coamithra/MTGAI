"""Character reference portrait generator.

Generates neutral headshot portraits for legendary characters using ComfyUI + Flux.
These serve as identity references for later character-consistent card art generation.

Portraits are front-facing, plain background, even lighting — designed for
identity reference, not card art. 3 versions per character for selection.

Output: output/sets/<SET>/art-direction/character-refs/<slug>_v<N>.png

CLI usage:
    python -m mtgai.art.character_portraits --set ASD [--char feretha] [--dry-run]
"""

import argparse
import json
import logging
import re
import time
import traceback
from pathlib import Path

from mtgai.art.image_generator import (
    ensure_comfyui,
    generate_image_comfyui,
    is_comfyui_running,
    kill_comfyui,
)

logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path("C:/Programming/MTGAI/output")
VISUAL_REFS_PATH = Path("C:/Programming/MTGAI/output/sets/ASD/art-direction/visual-references.json")

# Portrait settings — taller than wide for headshots
PORTRAIT_WIDTH = 768
PORTRAIT_HEIGHT = 1024
VERSIONS_PER_CHARACTER = 3
RESTART_EVERY_N = 0  # Disabled — flush_comfyui() now clears CUDA caches after each image

# Style prefix for all portraits — matches style guide
STYLE_PREFIX = (
    "Stylized digital illustration, bold shapes, strong silhouettes, "
    "painterly texture, concept art style. "
    "Not photorealistic, slightly exaggerated proportions. "
)

# Suffix for all portraits — neutral reference shot
PORTRAIT_SUFFIX = (
    "Front-facing portrait, head and upper shoulders, "
    "plain dark neutral background, even soft studio lighting, "
    "character reference sheet style, clean composition, "
    "sharp focus on face and defining features"
)


def _slugify(name: str) -> str:
    """Convert character name to filesystem-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")


def _build_portrait_prompts(visual_refs: dict) -> list[dict]:
    """Build Flux-optimized portrait prompts from character descriptions.

    Returns list of dicts with keys: key, name, prompt, description.
    """
    characters = visual_refs.get("legendary_characters", {})
    flux_replacements = visual_refs.get("flux_term_replacements", {})

    prompts = []
    for key, description in characters.items():
        # Extract character name (everything before the first colon)
        name_match = re.match(r"^([^:]+):", description)
        char_name = name_match.group(1).strip() if name_match else key.title()

        # Build the visual description — strip the character name prefix
        visual_desc = description
        if ":" in visual_desc:
            visual_desc = visual_desc.split(":", 1)[1].strip()

        # Apply Flux term replacements for setting-specific terms
        for term, replacement in flux_replacements.items():
            visual_desc = re.sub(
                rf"\b{re.escape(term)}\b", replacement, visual_desc, flags=re.IGNORECASE
            )

        # Extract the most portrait-relevant details (appearance, clothing, features)
        # Keep it under ~60 words for Flux optimal range
        portrait_desc = _extract_portrait_details(key, visual_desc)

        prompt = f"{STYLE_PREFIX}{portrait_desc}. {PORTRAIT_SUFFIX}"

        prompts.append(
            {
                "key": key,
                "name": char_name,
                "slug": _slugify(char_name),
                "prompt": prompt,
                "description": description,
            }
        )

    return prompts


def _extract_portrait_details(key: str, description: str) -> str:
    """Extract portrait-relevant visual details from a character description.

    Focuses on face, clothing, and distinguishing features. Strips action/lore
    details that aren't relevant to a neutral headshot.
    """
    # Character-specific portrait extractions — hand-tuned for best Flux results
    # These focus on what you'd SEE in a close-up portrait
    portraits = {
        "feretha": (
            "Dead wizard-ruler, desiccated corpse on a technological throne. "
            "Hollow skull with cables and fluid tubes plugged into it, "
            "golden crown that doubles as a neural interface headset. "
            "Empty open eyes, decayed royal robes, ancient server rack behind him. "
            "Sickly green-gold glow from machinery"
        ),
        "koyl": (
            "50-year-old man with sharp calculating eyes, clean-shaven, lean build. "
            "Immaculately dressed in dark formal robes with subtle embroidery. "
            "Quiet absolute authority in his expression. "
            "Former slave who became a ruler — dignified, precise, dangerous"
        ),
        "marcus tyro": (
            "Battle-scarred military commander, weathered face, short-cropped hair. "
            "Practical uniform with splint mail armor, ceremonial insignia on armor. "
            "Large revolver-style pistol holstered at side. "
            "Pragmatic, tired, unyielding expression. Warm sandstone lighting"
        ),
        "fereyn": (
            "A wizard sitting inside a giant detachable stone head — "
            "the upper portion of a 60-foot statue with a 20-foot bearded stone face. "
            "Glowing blue eyes on the stone face that fire lasers. "
            "The wizard operates controls inside, speaks through a microphone. "
            "Majestic and absurd, treated with complete seriousness"
        ),
        "monsator": (
            "Gaunt wizard in a ragged black cloak, mounted on a draft horse. "
            "Commands animated stalks of corn that walk on root-like feet. "
            "Weathered face, dark eyes, agricultural menace. "
            "Cornstalk warriors with crude wooden spears visible behind him"
        ),
        "head scientist": (
            "Towering figure standing 12 feet tall on concealed stilts. "
            "Enormous lab coat hiding the stilts completely. "
            "Multiple prosthetic tool-arms extending from the coat. "
            "Goggles pushed up on forehead, wild unkempt hair, manic expression. "
            "Tattered lab coat over improvised protective gear"
        ),
        "karak": (
            "Large scarred bandit king draped in stolen finery mixed with scavenged tech. "
            "Gold chains, fur-lined cloak, rings on every finger. "
            "Many visible weapons. He grins too wide — menacing smile. "
            "Rough face with prominent scars, dangerous charisma"
        ),
        "jace": (
            "Young man with glowing blue eyes, short dark hair, lean build. "
            "Clean blue robes with geometric patterns — no grime or wear. "
            "Distinctly out of place, too clean for this world. "
            "Calm intelligence in expression. Blue geometric light patterns around him"
        ),
    }

    return portraits.get(key, description[:200])


def generate_character_portraits(
    set_code: str,
    char_filter: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    """Generate character reference portraits for all legendary characters.

    Args:
        set_code: Set code (e.g., "ASD").
        char_filter: Optional character key to generate only one.
        dry_run: Log without generating.
        force: Regenerate even if portraits exist.

    Returns summary dict.
    """
    from mtgai.io.asset_paths import set_artifact_dir

    set_dir = set_artifact_dir(set_code)
    refs_path = set_dir / "art-direction" / "visual-references.json"
    if not refs_path.exists():
        raise FileNotFoundError(f"Visual references not found: {refs_path}")

    visual_refs = json.loads(refs_path.read_text(encoding="utf-8"))
    prompts = _build_portrait_prompts(visual_refs)

    if char_filter:
        prompts = [p for p in prompts if p["key"] == char_filter or char_filter in p["slug"]]
        if not prompts:
            raise ValueError(f"No character matching '{char_filter}'")

    out_dir = set_dir / "art-direction" / "character-refs"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir = out_dir / "logs"
    log_dir.mkdir(exist_ok=True)

    # Log all prompts
    logger.info("=" * 60)
    logger.info("Character Reference Portrait Generation")
    logger.info("=" * 60)
    logger.info("Characters: %d", len(prompts))
    logger.info("Versions per character: %d", VERSIONS_PER_CHARACTER)
    logger.info("Total images: %d", len(prompts) * VERSIONS_PER_CHARACTER)
    logger.info("Resolution: %dx%d", PORTRAIT_WIDTH, PORTRAIT_HEIGHT)
    logger.info("Output: %s", out_dir)
    logger.info("")

    for p in prompts:
        logger.info("  %s (%s)", p["name"], p["key"])
        logger.info("    Prompt: %s", p["prompt"][:120] + "...")
    logger.info("")

    if dry_run:
        logger.info("[DRY RUN] Would generate %d images", len(prompts) * VERSIONS_PER_CHARACTER)
        return {
            "set_code": set_code,
            "characters": len(prompts),
            "generated": 0,
            "skipped": 0,
            "failed": 0,
            "errors": [],
            "dry_run": True,
        }

    # Build flat work list for progress tracking
    work_items = []
    for p in prompts:
        for version in range(1, VERSIONS_PER_CHARACTER + 1):
            work_items.append((p, version))
    total_items = len(work_items)

    # Ensure ComfyUI is running — log output to file for crash diagnosis
    comfyui_proc = ensure_comfyui(log_dir=log_dir)

    generated = 0
    skipped = 0
    failed = 0
    errors = []
    start_time = time.time()

    # Progress file — written after every image so we know exactly where a crash happened
    progress_path = log_dir / "progress.json"

    def _save_progress():
        progress = {
            "generated": generated,
            "skipped": skipped,
            "failed": failed,
            "errors": errors,
            "elapsed_seconds": round(time.time() - start_time, 1),
            "last_completed": None,
        }
        progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")

    try:
        for idx, (p, version) in enumerate(work_items, 1):
            slug = p["slug"]
            dest = out_dir / f"{slug}_v{version}.png"
            progress_label = f"[{idx}/{total_items}]"

            if dest.exists() and not force:
                logger.info("%s SKIP %s v%d — already exists", progress_label, p["name"], version)
                skipped += 1
                continue

            # Health check — restart ComfyUI if it died between images
            if not is_comfyui_running():
                logger.warning("ComfyUI is not responding — restarting...")
                kill_comfyui(comfyui_proc)
                time.sleep(3)
                comfyui_proc = ensure_comfyui(log_dir=log_dir)
                logger.info("ComfyUI restarted, continuing generation")

            logger.info("%s GENERATE %s v%d...", progress_label, p["name"], version)

            try:
                image_data, metadata = generate_image_comfyui(
                    prompt=p["prompt"],
                    width=PORTRAIT_WIDTH,
                    height=PORTRAIT_HEIGHT,
                )

                dest.write_bytes(image_data)
                logger.info(
                    "  SAVED %s (%.1fs, %s bytes)",
                    dest.name,
                    metadata["elapsed_seconds"],
                    f"{len(image_data):,}",
                )

                # Save generation log
                log_entry = {
                    "character": p["key"],
                    "name": p["name"],
                    "version": version,
                    "prompt": p["prompt"],
                    "output_path": str(dest),
                    "file_size_bytes": len(image_data),
                    **metadata,
                }
                log_path = log_dir / f"{slug}_v{version}.json"
                log_path.write_text(json.dumps(log_entry, indent=2), encoding="utf-8")

                generated += 1

                # Update crash-safe progress after every successful image
                progress_data = {
                    "generated": generated,
                    "skipped": skipped,
                    "failed": failed,
                    "errors": errors,
                    "elapsed_seconds": round(time.time() - start_time, 1),
                    "last_completed": f"{p['name']} v{version}",
                }
                progress_path.write_text(json.dumps(progress_data, indent=2), encoding="utf-8")

            except Exception as e:
                logger.error("%s FAILED %s v%d: %s", progress_label, p["name"], version, e)
                failed += 1
                errors.append({"character": p["key"], "version": version, "error": str(e)})

    except KeyboardInterrupt:
        logger.info("\nInterrupted! Progress saved. Re-run to resume from where you left off.")
        _save_progress()
        raise
    except Exception as e:
        tb = traceback.format_exc()
        logger.error("CRASH after %d generated, %d skipped, %d failed", generated, skipped, failed)
        logger.error("Exception: %s", e)
        logger.error("Traceback:\n%s", tb)
        # Save crash info so we can diagnose without scrolling terminal history
        crash_data = {
            "generated": generated,
            "skipped": skipped,
            "failed": failed,
            "errors": errors,
            "elapsed_seconds": round(time.time() - start_time, 1),
            "crash": str(e),
            "traceback": tb,
        }
        crash_path = log_dir / "crash.json"
        crash_path.write_text(json.dumps(crash_data, indent=2), encoding="utf-8")
        logger.error("Crash details saved to %s", crash_path)
        logger.info("Re-run to resume from where you left off.")
        raise
    finally:
        kill_comfyui(comfyui_proc)

    elapsed = time.time() - start_time

    summary = {
        "set_code": set_code,
        "characters": len(prompts),
        "generated": generated,
        "skipped": skipped,
        "failed": failed,
        "errors": errors,
        "elapsed_seconds": round(elapsed, 1),
        "dry_run": False,
    }

    # Save summary
    summary_path = log_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Save prompt reference (all prompts in one file for easy review)
    prompt_ref = {p["key"]: {"name": p["name"], "prompt": p["prompt"]} for p in prompts}
    prompt_ref_path = out_dir / "prompts.json"
    prompt_ref_path.write_text(json.dumps(prompt_ref, indent=2), encoding="utf-8")

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Generate character reference portraits via ComfyUI + Flux"
    )
    parser.add_argument("--set", default="ASD", help="Set code (default: ASD)")
    parser.add_argument("--char", default=None, help="Single character key (e.g. feretha, koyl)")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without generating")
    parser.add_argument("--force", action="store_true", help="Regenerate existing portraits")
    args = parser.parse_args()

    # Log to both console AND file — if the process gets killed, the file survives.
    # Routed through set_artifact_dir so the log lands in the project's
    # asset_folder when configured (matches generate_character_portraits).
    from mtgai.io.asset_paths import set_artifact_dir

    log_file = (
        set_artifact_dir(args.set)
        / "art-direction"
        / "character-refs"
        / "logs"
        / "run.log"
    )
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(str(log_file), mode="a", encoding="utf-8"),
        ],
    )

    import os

    logger.info("=" * 40)
    logger.info("Process PID: %d", os.getpid())
    logger.info("Log file: %s", log_file)
    logger.info("=" * 40)

    summary = generate_character_portraits(
        set_code=args.set,
        char_filter=args.char,
        dry_run=args.dry_run,
        force=args.force,
    )

    print(f"\n{'=' * 60}")
    print(f"Character Portraits — {summary['set_code']}")
    print(f"{'=' * 60}")
    print(f"Characters: {summary['characters']}")
    print(f"Generated:  {summary['generated']}")
    print(f"Skipped:    {summary['skipped']}")
    print(f"Failed:     {summary['failed']}")
    if not summary["dry_run"]:
        print(f"Elapsed:    {summary['elapsed_seconds']:.0f}s")
    if summary["errors"]:
        print("\nErrors:")
        for e in summary["errors"]:
            print(f"  {e['character']} v{e['version']}: {e['error']}")


if __name__ == "__main__":
    main()
