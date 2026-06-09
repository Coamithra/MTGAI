"""Character / location reference-image generator (the ``char_portraits`` stage).

Reworked from the old always-on, ASD-hardcoded portrait stage into a *targeted*
reference-image stage (card 6a20aa84). It runs AFTER ``art_prompts`` (it reads
each card's ``art_prompt``) and does three things:

1. **Detect recurring entities** — the recurring (2+ card) entities are derived
   from the unified per-card entity tags (``art-direction/entity-tags.json``,
   produced by the ``art_prompts`` stage via :mod:`mtgai.art.entity_tags`), so
   the appearance-TEXT path and this reference-IMAGE path agree on what each card
   features (card 6a27581d). When the sidecar is absent (a standalone / out-of-
   order run) the detection pass runs here as a fallback. A one-card entity gets
   no reference (nothing to be consistent with).

2. **Generate a NEUTRAL reference image per entity** — a plain canonical
   identity/appearance depiction ("what this person / place / thing looks
   like"), NOT styled card art: no dramatic composition, no artist style. The
   appearance is pulled from the art-direction dictionary
   (``art-direction/visual-references.json``) so the reference matches the set's
   established look. ``VERSIONS_PER_ENTITY`` versions per entity for selection.

3. **Attach references to the cards, structured** — every card featuring a
   recurring entity gets ``art_character_refs`` populated
   (``[ArtCharacterRef(entity_key, ref_image_path)]``). This replaces the old
   scan-at-render-time ``get_character_ref_paths`` approach with an explicit
   produced artifact the Art Generation stage reads to feed PuLID / IP-Adapter.

Output images: ``<asset>/art-direction/character-refs/<slug>_v<N>.png``
LLM transcripts: ``<asset>/char_portraits/logs`` (convention §16).

CLI usage:
    python -m mtgai.art.character_portraits --mtg path/to/project.mtg [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path

from mtgai.art.image_generator import (
    ensure_comfyui,
    generate_image_comfyui,
    is_comfyui_running,
    kill_comfyui,
)
from mtgai.io.atomic import atomic_write_text

logger = logging.getLogger(__name__)

# Reference-image settings — taller than wide for a clean identity shot.
REF_WIDTH = 768
REF_HEIGHT = 1024
VERSIONS_PER_ENTITY = 3

# The art-direction dictionary's keyed sub-dicts that hold appearance prose, in
# priority order. ``entity_key`` slugs in ``art_character_refs`` are keys in one
# of these (contract: plans/art-render-contracts.md §2).
_REF_CATEGORIES = ("legendary_characters", "creature_types", "factions", "landmarks")

# Neutral-reference style: a clean canonical depiction, NOT styled card art.
# Deliberately omits any artist style or dramatic composition so the image is
# usable as identity conditioning (PuLID / IP-Adapter) rather than finished art.
_NEUTRAL_STYLE_SUFFIX = (
    "Clean reference-sheet depiction, plain neutral grey background, "
    "even soft studio lighting, no dramatic composition, no action, "
    "centered subject, sharp focus on defining identifying features."
)


def _slugify(name: str) -> str:
    """Convert an entity name to a filesystem-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")


# ---------------------------------------------------------------------------
# Step 2 — neutral reference-image prompt
# ---------------------------------------------------------------------------


def _appearance_for_entity(entity: dict, visual_refs: dict) -> str:
    """Pull the entity's appearance prose from the art-direction dictionary.

    Looks the ``entity_key`` up across the keyed sub-dicts (matched on the
    normalized slug, so a ``the_spire`` key resolves a ``the spire`` dictionary
    entry); falls back to the entity's own note when the dictionary has no entry.
    No ASD-hardcoded descriptions — the appearance always comes from the
    per-project dictionary or the note.
    """
    from mtgai.art.visual_reference import normalize_entity_key

    key = normalize_entity_key(str(entity.get("entity_key", "")))
    for category in _REF_CATEGORIES:
        sub = visual_refs.get(category, {})
        if not isinstance(sub, dict):
            continue
        for dict_key, dict_desc in sub.items():
            if normalize_entity_key(str(dict_key)) != key:
                continue
            desc = str(dict_desc)
            # Strip a leading "Name:" prefix the dictionary prose often carries.
            if ":" in desc:
                desc = desc.split(":", 1)[1].strip()
            return desc
    return str(entity.get("note") or entity.get("name") or key.replace("_", " "))


def build_neutral_prompt(entity: dict, visual_refs: dict) -> str:
    """Build the neutral reference-image prompt for an entity.

    Applies the dictionary's Flux term replacements so invented set words become
    renderable phrases, then frames the subject as a person OR a place depending
    on the entity kind and appends the neutral reference-sheet style suffix.
    """
    appearance = _appearance_for_entity(entity, visual_refs)
    replacements = visual_refs.get("flux_term_replacements", {})
    if isinstance(replacements, dict):
        for term, replacement in replacements.items():
            appearance = re.sub(
                rf"\b{re.escape(str(term))}\b",
                str(replacement),
                appearance,
                flags=re.IGNORECASE,
            )

    kind = (entity.get("kind") or "").lower()
    if kind in ("location", "landmark", "place"):
        framing = "A clear establishing view of this place:"
    elif kind == "faction":
        framing = "A representative depiction of this faction's look:"
    else:
        framing = "A neutral identity reference of this character:"

    appearance = appearance.rstrip(". ")
    return f"{framing} {appearance}. {_NEUTRAL_STYLE_SUFFIX}"


# ---------------------------------------------------------------------------
# Step 3 — attach references to cards
# ---------------------------------------------------------------------------


def attach_refs_to_cards(
    entities: list[dict],
    ref_paths: dict[str, str],
    cards_dir: Path,
) -> int:
    """Populate ``art_character_refs`` on every card featuring a recurring entity.

    ``ref_paths`` maps ``entity_key`` → the chosen reference image path
    (repo-relative under the asset folder). Cards are rewritten immutably via the
    Card model so the on-disk JSON stays schema-valid. Each card's refs for the
    entities this stage produced are replaced (so a re-run is idempotent), while
    refs for entities NOT in this run's set are preserved. Returns the number of
    cards modified.
    """
    from mtgai.io.card_io import load_card, save_card
    from mtgai.models.card import ArtCharacterRef

    # Build collector_number -> [(entity_key, ref_image_path)] for entities that
    # actually have a generated reference image.
    by_card: dict[str, list[tuple[str, str]]] = {}
    produced_keys: set[str] = set()
    for entity in entities:
        key = entity["entity_key"]
        path = ref_paths.get(key)
        if not path:
            continue
        produced_keys.add(key)
        for cn in entity["cards"]:
            by_card.setdefault(cn, []).append((key, path))

    if not cards_dir.exists():
        return 0

    modified = 0
    set_dir = cards_dir.parent
    for card_file in sorted(cards_dir.glob("*.json")):
        try:
            card = load_card(card_file)
        except Exception:
            logger.warning("Skipping unreadable card %s", card_file.name)
            continue
        cn = card.collector_number
        new_for_card = by_card.get(cn, [])
        # Keep any pre-existing refs whose entity_key this run did NOT produce
        # (don't clobber refs for entities outside this run); replace the rest.
        kept = [r for r in card.art_character_refs if r.entity_key not in produced_keys]
        rebuilt = kept + [
            ArtCharacterRef(entity_key=key, ref_image_path=path) for key, path in new_for_card
        ]
        # Only rewrite when the ref list actually changed (stable serialization).
        before = [(r.entity_key, r.ref_image_path) for r in card.art_character_refs]
        after = [(r.entity_key, r.ref_image_path) for r in rebuilt]
        if before == after:
            continue
        updated = card.model_copy(update={"art_character_refs": rebuilt})
        save_card(updated, set_dir=set_dir)
        modified += 1
    return modified


def clear_refs_on_cards(cards_dir: Path) -> int:
    """Strip ``art_character_refs`` from every card. Used by the stage clearer so
    a cascade/edit re-run starts from a clean slate. Returns cards modified."""
    from mtgai.io.card_io import load_card, save_card

    if not cards_dir.exists():
        return 0
    modified = 0
    set_dir = cards_dir.parent
    for card_file in sorted(cards_dir.glob("*.json")):
        try:
            card = load_card(card_file)
        except Exception:
            continue
        if not card.art_character_refs:
            continue
        save_card(card.model_copy(update={"art_character_refs": []}), set_dir=set_dir)
        modified += 1
    return modified


# ---------------------------------------------------------------------------
# Stage entry point
# ---------------------------------------------------------------------------


def _rel_ref_path(dest: Path, set_dir: Path) -> str:
    """Reference image path as a POSIX string relative to the asset folder
    (the form ``ArtCharacterRef.ref_image_path`` stores)."""
    try:
        return dest.relative_to(set_dir).as_posix()
    except ValueError:
        return dest.as_posix()


def generate_character_refs(
    dry_run: bool = False,
    force: bool = False,
    should_cancel: Callable[[], bool] | None = None,
    on_entity_start: Callable[[dict], None] | None = None,
    on_entity_image: Callable[[str, str], None] | None = None,
    on_reset: Callable[[], None] | None = None,
    detect_poller: AbstractContextManager | None = None,
) -> dict:
    """Generate neutral reference images for recurring entities and attach them.

    Args:
        dry_run: Detect + persist entities but don't generate images or write cards.
        force: Regenerate even if reference images already exist.
        should_cancel: Polled at image boundaries; stop early (keep partial output).
        on_entity_start: ``on_entity_start(entity)`` before an entity's images gen.
        on_entity_image: ``on_entity_image(entity_key, ref_image_rel_path)`` after
            each saved image (per-version live stream).
        on_reset: fired once before image generation begins.
        detect_poller: optional context manager wrapping ONLY the step-1 LLM
            detection call (the tok/s telemetry poller). It must NOT span the
            ComfyUI image-generation phase — polling a llama-swap model endpoint
            there would reload the (deliberately unloaded) LLM into VRAM and
            starve Flux (card 6a25497b). Defaults to a no-op context.

    Returns a summary dict.
    """
    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    project = require_active_project()
    set_code = project.set_code
    set_dir = set_artifact_dir()
    refs_path = set_dir / "art-direction" / "visual-references.json"
    visual_refs: dict = {}
    if refs_path.exists():
        try:
            loaded = json.loads(refs_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                visual_refs = loaded
        except Exception:
            logger.warning("Could not parse %s; proceeding with empty dictionary", refs_path)

    cards_dir = set_dir / "cards"
    cards: list[dict] = []
    if cards_dir.exists():
        for path in sorted(cards_dir.glob("*.json")):
            try:
                loaded_card = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            # Skip cards the finalize sanity gate soft-excluded — they won't reach
            # print, so they shouldn't seed a recurring-entity reference.
            if isinstance(loaded_card, dict) and not loaded_card.get("sanity_excluded"):
                cards.append(loaded_card)

    out_dir = set_dir / "art-direction" / "character-refs"
    log_dir = set_dir / "char_portraits" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    model_id = project.settings.get_llm_model_id("char_portraits")
    thinking = project.settings.get_thinking("char_portraits")

    # Step 1 — recurring (2+ card) entities, derived from the unified per-card
    # entity tags (``art-direction/entity-tags.json``) the art_prompts stage
    # produced — the SAME source the appearance-TEXT path reads, so the two agree.
    # ``ensure_entity_tags`` reuses that sidecar with no LLM call; only when it's
    # absent (a standalone / out-of-order run) does detection run here. The tok/s
    # poller wraps that fallback LLM call only — never the ComfyUI image phase
    # below, where polling would reload the unloaded LLM and contend with Flux
    # (card 6a25497b).
    from mtgai.art.entity_tags import ensure_entity_tags, recurring_from_tags

    logger.info("Resolving recurring entities across %d cards...", len(cards))
    with detect_poller or nullcontext():
        tags_data, cost = ensure_entity_tags(
            set_dir, cards, visual_refs, model_id=model_id, log_dir=log_dir, thinking=thinking
        )
    entities = recurring_from_tags(tags_data)
    logger.info("Found %d recurring entities", len(entities))
    for e in entities:
        logger.info("  %s (%s) on %d cards", e["name"], e["kind"], len(e["cards"]))

    # Persist the detection result as the durable artifact the tab reads.
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "entities.json", json.dumps(entities, indent=2, ensure_ascii=False))

    base_summary = {
        "set_code": set_code,
        "entities": len(entities),
        "generated": 0,
        "skipped": 0,
        "failed": 0,
        "cards_modified": 0,
        "cost_usd": round(cost, 4),
        "errors": [],
    }

    if dry_run:
        return {**base_summary, "dry_run": True}

    if not entities:
        logger.info("No recurring entities — nothing to reference.")
        atomic_write_text(
            out_dir / "summary.json", json.dumps({**base_summary, "dry_run": False}, indent=2)
        )
        return {**base_summary, "dry_run": False}

    if on_reset is not None:
        on_reset()

    generated = 0
    skipped = 0
    failed = 0
    errors: list[dict] = []
    cancelled = False
    # entity_key -> chosen reference image (the first available, repo-relative).
    ref_paths: dict[str, str] = {}

    comfyui_proc = ensure_comfyui(log_dir=log_dir)
    try:
        for entity in entities:
            if should_cancel is not None and should_cancel():
                cancelled = True
                break
            key = entity["entity_key"]
            slug = _slugify(entity["name"]) or key
            prompt = build_neutral_prompt(entity, visual_refs)
            if on_entity_start is not None:
                on_entity_start(entity)

            for version in range(1, VERSIONS_PER_ENTITY + 1):
                if should_cancel is not None and should_cancel():
                    cancelled = True
                    break
                dest = out_dir / f"{slug}_v{version}.png"
                rel = _rel_ref_path(dest, set_dir)
                if dest.exists() and not force:
                    skipped += 1
                    ref_paths.setdefault(key, rel)
                    if on_entity_image is not None:
                        on_entity_image(key, rel)
                    continue

                if not is_comfyui_running():
                    logger.warning("ComfyUI not responding — restarting...")
                    kill_comfyui(comfyui_proc)
                    time.sleep(3)
                    comfyui_proc = ensure_comfyui(log_dir=log_dir)

                logger.info("GENERATE %s v%d...", entity["name"], version)
                try:
                    image_data, metadata = generate_image_comfyui(
                        prompt=prompt, width=REF_WIDTH, height=REF_HEIGHT
                    )
                    dest.write_bytes(image_data)
                    generated += 1
                    ref_paths.setdefault(key, rel)
                    log_entry = {
                        "entity_key": key,
                        "name": entity["name"],
                        "version": version,
                        "prompt": prompt,
                        "output_path": str(dest),
                        **metadata,
                    }
                    atomic_write_text(
                        log_dir / f"{slug}_v{version}.json", json.dumps(log_entry, indent=2)
                    )
                    if on_entity_image is not None:
                        on_entity_image(key, rel)
                except Exception as e:
                    logger.error("FAILED %s v%d: %s", entity["name"], version, e)
                    failed += 1
                    errors.append({"entity": key, "version": version, "error": str(e)})
            if cancelled:
                break
    finally:
        kill_comfyui(comfyui_proc)

    # Step 3 — attach the chosen references to the cards.
    cards_modified = attach_refs_to_cards(entities, ref_paths, cards_dir)
    logger.info("Attached references to %d cards", cards_modified)

    summary = {
        **base_summary,
        "generated": generated,
        "skipped": skipped,
        "failed": failed,
        "cards_modified": cards_modified,
        "errors": errors,
        "dry_run": False,
    }
    if cancelled:
        summary["cancelled"] = True
    atomic_write_text(out_dir / "summary.json", json.dumps(summary, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Generate neutral reference images for recurring entities via ComfyUI + Flux"
    )
    parser.add_argument(
        "--mtg",
        required=True,
        help="Path to a .mtg project file (the project's asset_folder must be set)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Detect only; don't generate")
    parser.add_argument("--force", action="store_true", help="Regenerate existing references")
    args = parser.parse_args()

    from mtgai.runtime.cli_shim import activate_from_mtg

    activate_from_mtg(args.mtg)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    summary = generate_character_refs(dry_run=args.dry_run, force=args.force)

    print(f"\n{'=' * 60}")
    print(f"Character References — {summary['set_code']}")
    print(f"{'=' * 60}")
    print(f"Recurring entities: {summary['entities']}")
    print(f"Images generated:   {summary['generated']}")
    print(f"Skipped:            {summary['skipped']}")
    print(f"Failed:             {summary['failed']}")
    print(f"Cards modified:     {summary['cards_modified']}")
    print(f"Cost:               ${summary['cost_usd']:.4f}")
    if summary["errors"]:
        print("\nErrors:")
        for e in summary["errors"]:
            print(f"  {e['entity']} v{e['version']}: {e['error']}")


if __name__ == "__main__":
    main()
