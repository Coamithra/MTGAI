"""Art prompt generation pipeline (artist-driven, LLM-authored).

Each card's Flux art prompt is **authored in full by an LLM** in the voice of a
chosen artist, grounded in the set's art direction + theme setting prose + the
card's own text, with an occasional deliberate cameo of a named style-guide
entity. The pipeline:

1. Assign an artist from the project's Artist Directory
   (``art-direction/artists.json``) to each card and persist it onto
   ``card.artist`` (the rendered credit line).
2. Roll a per-card cameo chance (the ``cameo_probability`` knob); on a hit, pick
   a style-guide entity and instruct the LLM to feature it.
3. Ask the LLM to author the whole prompt from {artist style + set art direction
   + theme prose + card text}, told explicitly the reference material may not fit
   this card — use what fits, ignore the rest.
4. Sanitize the authored prompt for Flux (``_sanitize_for_flux``) as a lean
   safety-net post-pass.

Flux prompt best practices (from BFL docs):
- Front-load the subject (Flux pays most attention to what comes first)
- 40-70 words is the sweet spot
- Natural language, not keyword lists
- Avoid negative phrasing ("no text") — use positive alternatives
- Structure: Subject + Action + Style + Context

CLI usage:
    python -m mtgai.art.prompt_builder --mtg path/to/project.mtg [--card W-C-01] \
        [--dry-run] [--force] [--cameo-prob 0.25]
"""

import argparse
import json
import logging
import random
import time
from collections.abc import Callable
from pathlib import Path

from mtgai.art.artist_assignment import assign_artists, load_art_prompt_knobs
from mtgai.art.visual_reference import (
    detect_named_characters,
    get_artists,
    get_cameo_entities,
    get_flux_replacements,
    get_refs,
    get_set_art_direction,
    get_visual_references,
)
from mtgai.generation import temperatures as temps
from mtgai.generation.llm_client import generate_with_tool
from mtgai.io.atomic import atomic_write_text
from mtgai.io.card_io import load_card, save_card
from mtgai.io.paths import output_root
from mtgai.models.card import Card

logger = logging.getLogger(__name__)

OUTPUT_ROOT = output_root()

DEFAULT_ARTIST = "AI Generated"

# Deterministic per-card cameo RNG: seed the roll on the collector number so a
# resume / re-run reproduces the same cameo decisions (no reshuffle on retry).
_CAMEO_SEED_SALT = "art-prompt-cameo"


# ---------------------------------------------------------------------------
# Style lines — legacy per-color composition fallback. The LLM now authors the
# whole prompt (style included), so these are only used by ``assemble_full_prompt``
# when no LLM-authored prompt is available (the old code path / tests).
# ---------------------------------------------------------------------------

COLOR_COMPOSITION: dict[str, str] = {
    "W": (
        "Stylized digital illustration, structured balanced composition, "
        "warm sandstone and ivory tones, golden-hour lighting with long shadows"
    ),
    "U": (
        "Stylized digital illustration, geometric composition, "
        "cool steel-blue and teal palette, screen-glow lighting"
    ),
    "B": (
        "Stylized digital illustration, heavy shadows with minimal light, "
        "organic textures and wet surfaces, unsettling asymmetry"
    ),
    "R": (
        "Stylized digital illustration, dynamic tilted composition, "
        "warm fire-tones with high contrast, kinetic energy"
    ),
    "G": (
        "Stylized digital illustration, wide naturalist composition, "
        "rich earth tones with dappled light, layered depth"
    ),
    "COLORLESS": (
        "Stylized digital illustration, centered object-focused composition, "
        "self-illuminated subject against dark background"
    ),
    "LAND": (
        "Stylized digital illustration, panoramic landscape, "
        "dramatic atmospheric perspective, concept-art establishing shot"
    ),
}


def _motifs_suffix() -> str:
    """Return a ", motif, motif, motif" suffix from the active project's
    ``visual_motifs``, or "" if none are available. Capped at 3 motifs."""
    try:
        refs = get_refs()
    except Exception:
        return ""
    motifs = refs.get("visual_motifs") or []
    motifs = [str(m).strip() for m in motifs if str(m).strip()]
    if not motifs:
        return ""
    return ", " + ", ".join(motifs[:3])


def get_style_line(card: Card) -> str:
    """Legacy per-color composition + motif style line (fallback only)."""
    if "Land" in card.type_line:
        base = COLOR_COMPOSITION["LAND"]
    elif not card.colors:
        base = COLOR_COMPOSITION["COLORLESS"]
    else:
        base = COLOR_COMPOSITION.get(card.colors[0], COLOR_COMPOSITION["COLORLESS"])
    return base + _motifs_suffix()


# ---------------------------------------------------------------------------
# Card type detection
# ---------------------------------------------------------------------------


def get_card_type_category(card: Card) -> str:
    """Categorize a card into a broad type for composition hints."""
    tl = card.type_line.lower()
    if "land" in tl:
        if any(s in tl for s in ["plains", "island", "swamp", "mountain", "forest"]):
            return "basic_land"
        return "nonbasic_land"
    if "creature" in tl:
        return "creature"
    if "instant" in tl:
        return "instant"
    if "sorcery" in tl:
        return "sorcery"
    if "enchantment" in tl:
        return "enchantment"
    if "artifact" in tl:
        if "equipment" in tl:
            return "equipment"
        return "artifact"
    return "creature"  # fallback


# ---------------------------------------------------------------------------
# LLM art-prompt authoring
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a Magic: The Gathering art director writing a single image-generation \
prompt for Flux (a diffusion model), authored in the voice of a specific \
illustrator. You receive: the chosen artist's style, the set's overall art \
direction, the setting prose, and the card's own text. You output ONE finished \
Flux prompt.

HOW TO USE THE MATERIAL:
- The art direction and setting prose are REFERENCE. They describe the world at \
  large and MAY NOT fit this particular card. Use only what genuinely fits this \
  card's subject; freely ignore motifs, factions, or locations that don't apply. \
  Never force every motif in.
- Let the chosen artist's style shape the composition, palette, brushwork, and \
  mood — that is the through-line that makes the set feel cohesive across many \
  artists.
- Ground the subject in the card's name, type, flavor, and design notes. Oracle \
  text is CONTEXT for what the card does — translate it into a visual moment, \
  never depict rules, mana symbols, or numbers.

FLUX PROMPT RULES:
- Front-load the subject. Start with WHAT we see, then action, then style/mood, \
  then setting context.
- Target 40-70 words. Dense, specific, every word earns its place. Natural \
  descriptive language, not keyword lists.
- Be concrete: "a gaunt pale humanoid with reflective cat-eyes crouching in a \
  dark corridor", not "a mysterious dungeon creature".
- DO NOT use character names or made-up race/creature names the model won't know \
  (moktar, peryton, screechman, etc.) — describe APPEARANCE instead. If a \
  visual-reference description is given for an entity, render that description.
- DO NOT use negative phrasing ("no text", "without borders"). Describe only \
  what IS in the image.
- DO NOT mention game mechanics, stats, rules, cards, or frames.
- Rarity guides detail: common = simple/grounded, mythic = epic/detailed.
- You MAY occasionally weave in a named style-guide character / location / \
  element when it fits the card — but only when it fits. If the user message \
  explicitly asks for a specific cameo, feature it prominently (by appearance, \
  never by name)."""

TOOL_SCHEMA = {
    "name": "art_prompt",
    "description": "Author a finished Flux art prompt for one card.",
    "input_schema": {
        "type": "object",
        "properties": {
            "art_prompt": {
                "type": "string",
                "description": (
                    "A finished 40-70 word Flux prompt, subject first, natural "
                    "language, in the chosen artist's style. Appearance not names; "
                    "no game mechanics or card references."
                ),
            },
        },
        "required": ["art_prompt"],
    },
}

# Type-specific composition hints (woven into the user prompt, not the schema).
_COMPOSITION_HINTS = {
    "creature": "Subject fills 60-70% of frame, action pose.",
    "instant": "Frozen moment of dramatic action, tight crop.",
    "sorcery": "Sweeping display of power, wider framing.",
    "enchantment": "Persistent ethereal effect transforming a scene, atmospheric.",
    "artifact": "Object centered with fine detail, muted background.",
    "equipment": "Item being wielded, item is the focal point.",
    "basic_land": "Panoramic landscape, no figures, evocative sense of place.",
    "nonbasic_land": "Panoramic location, no prominent figures, sense of place.",
}


def _build_card_block(card: Card) -> str:
    """The card-text block fed to the LLM (name, type, oracle context, flavor, notes)."""
    parts = [
        f"Card: {card.name}",
        f"Type: {card.type_line}",
        f"Rarity: {card.rarity}",
    ]
    if card.power is not None:
        parts.append(f"Size: {card.power}/{card.toughness}")
    if card.oracle_text:
        parts.append(
            f"Abilities (context only — depict the moment, not the rules): {card.oracle_text}"
        )
    if card.flavor_text:
        parts.append(f"Flavor: {card.flavor_text}")
    if card.design_notes:
        parts.append(f"Design notes: {card.design_notes}")
    return "\n".join(parts)


def build_art_prompt_user_message(
    card: Card,
    *,
    artist_style: str,
    set_art_direction: str,
    setting_prose: str,
    visual_refs: str,
    cameo: dict[str, str] | None,
) -> str:
    """Assemble the user message for the art-prompt LLM call.

    All of ``artist_style`` / ``set_art_direction`` / ``setting_prose`` /
    ``visual_refs`` may be empty (degraded inputs); the corresponding section is
    simply omitted. ``cameo`` (when present) names a specific style-guide entity
    to feature.
    """
    card_type_cat = get_card_type_category(card)
    hint = _COMPOSITION_HINTS.get(card_type_cat, "")

    sections: list[str] = []
    if artist_style:
        sections.append(f"ARTIST STYLE (author the prompt in this voice):\n{artist_style}")
    if set_art_direction:
        sections.append(
            f"SET ART DIRECTION (reference — use only what fits this card):\n{set_art_direction}"
        )
    if setting_prose:
        sections.append("SETTING (reference — use only what fits this card):\n" + setting_prose)

    sections.append("CARD:\n" + _build_card_block(card))

    if hint:
        sections.append(f"Composition: {hint}")
    if "Legendary" in (card.type_line or ""):
        sections.append("This is a unique, named character — distinctive features, imposing.")

    if visual_refs:
        sections.append(
            "VISUAL APPEARANCE REFERENCES (render these appearances, never the names):\n"
            f"{visual_refs}"
        )

    if cameo:
        sections.append(
            f"CAMEO REQUEST: Feature this {cameo['kind']} from the set's style guide in the "
            f"art — render it by appearance, not name: {cameo['description']}"
        )

    sections.append(
        "Author ONE finished Flux prompt (40-70 words). Subject first, then action, then "
        "style and mood, then setting context. Appearance not names; no mechanics or card "
        "references."
    )
    return "\n\n".join(sections)


def generate_art_prompt(
    card: Card,
    *,
    artist_style: str,
    set_art_direction: str,
    setting_prose: str,
    cameo: dict[str, str] | None,
    log_dir: Path | None = None,
) -> tuple[str, int, int]:
    """Call the LLM to author the full art prompt for a card.

    Returns ``(art_prompt, input_tokens, output_tokens)``. The returned prompt is
    NOT yet Flux-sanitized — the caller applies :func:`_sanitize_for_flux`.
    """
    visual_refs = get_visual_references(
        card.name,
        card.type_line,
        card.oracle_text,
        card.flavor_text,
    )

    user_message = build_art_prompt_user_message(
        card,
        artist_style=artist_style,
        set_art_direction=set_art_direction,
        setting_prose=setting_prose,
        visual_refs=visual_refs,
        cameo=cameo,
    )

    from mtgai.runtime.active_project import require_active_project

    _settings = require_active_project().settings
    result = generate_with_tool(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_message,
        tool_schema=TOOL_SCHEMA,
        model=_settings.get_llm_model_id("art_prompts"),
        thinking=_settings.get_thinking("art_prompts"),
        temperature=temps.GROUNDED,
        max_tokens=640,
        log_dir=log_dir,
    )

    prompt = result["result"]["art_prompt"]
    return prompt, result["input_tokens"], result["output_tokens"]


# ---------------------------------------------------------------------------
# Flux sanitization (safety-net post-pass) + legacy full-prompt assembly
# ---------------------------------------------------------------------------


def _sanitize_for_flux(text: str) -> str:
    """Replace setting-specific terms Flux won't understand.

    Replacements are loaded from the active project's visual-references.json
    (``flux_term_replacements``), so they're data-driven per set. Kept lean: the
    LLM authors the prompt; this is a safety-net so an invented word that slipped
    through still maps to something renderable.
    """
    import re

    replacements = get_flux_replacements()
    for term, replacement in replacements.items():
        text = re.sub(rf"\b{re.escape(term)}\b", replacement, text, flags=re.IGNORECASE)
    return text


def assemble_full_prompt(card: Card, visual_description: str) -> str:
    """Legacy assembly: sanitize a bare description + append the per-color style line.

    Retained for the old visual-description path / tests. The artist-driven
    pipeline lets the LLM author the whole prompt and only sanitizes it.
    """
    clean_desc = _sanitize_for_flux(visual_description).rstrip(". ")
    style = get_style_line(card)
    return f"{clean_desc}. {style}."


# ---------------------------------------------------------------------------
# Cameo selection
# ---------------------------------------------------------------------------


def _roll_cameo(card: Card, probability: float) -> dict[str, str] | None:
    """Decide whether this card gets a cameo and, if so, which entity.

    Deterministic per card (seeded on the collector number) so a resume / re-run
    reproduces the same decision. Returns the chosen ``{key, kind, description}``
    entity, or ``None`` (no cameo this card). A probability <= 0 or an empty
    style guide always yields ``None``.
    """
    if probability <= 0.0:
        return None
    entities = get_cameo_entities()
    if not entities:
        return None
    rng = random.Random(f"{_CAMEO_SEED_SALT}:{card.collector_number}")
    if rng.random() >= probability:
        return None
    return rng.choice(entities)


# ---------------------------------------------------------------------------
# Character reference image tracking (legacy scan path; art_gen reads the
# structured card.art_character_refs written by char_portraits instead)
# ---------------------------------------------------------------------------


def get_character_ref_paths(card: Card) -> list[dict]:
    """Check if any named characters on this card have reference images.

    Returns list of {character_name, ref_image_path} for characters that
    have reference images generated. These should be used as IP-Adapter
    or img2img conditioning in the ComfyUI workflow.

    DEPRECATED scan-at-render-time approach. The Character References stage
    (``char_portraits``) now writes ``card.art_character_refs`` as an explicit
    produced artifact (it runs after ``art_prompts``, so this scan returns
    nothing at prompt time on a first pass — the bug it replaces). Downstream
    art generation should read ``card.art_character_refs`` instead; this remains
    only as informational logging in the art-prompt stage until the Art
    Generation rework (card 6a20adda) switches the consumer over.
    """
    from mtgai.io.asset_paths import set_artifact_dir

    refs_dir = set_artifact_dir() / "art-direction" / "character-refs"
    if not refs_dir.exists():
        return []

    characters = detect_named_characters(
        card.name,
        card.type_line,
        card.oracle_text,
        card.flavor_text,
    )

    results = []
    for char_key in characters:
        for ext in (".png", ".jpg", ".webp"):
            ref_path = refs_dir / f"{char_key}{ext}"
            if ref_path.exists():
                results.append({"character": char_key, "ref_image_path": str(ref_path)})
                break
    return results


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------


def _is_credited_card(card: Card) -> bool:
    """True for a card that should be assigned a directory artist.

    Excludes reprints (their printed artist is the original's) and basic lands
    (alternate-art basics get a generic credit, not a directory painter).
    """
    if card.is_reprint:
        return False
    tl = (card.type_line or "").lower()
    return not ("basic" in tl and "land" in tl)


def generate_prompts_for_set(
    card_filter: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    progress_callback: Callable[[str, int, int, str, float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    card_saved_callback: Callable[[Card], None] | None = None,
    cameo_probability: float | None = None,
) -> dict:
    """Generate artist-driven, LLM-authored art prompts for the active project.

    Args:
        card_filter: Optional collector number to process a single card.
        dry_run: Generate prompts but don't save to card JSON.
        force: Regenerate even if ``art_prompt`` already exists.
        progress_callback: ``(cn, completed, total, detail, cost)`` per card.
        should_cancel: Polled at each card boundary; True stops the loop early
            (prompts written so far stay saved, so a resume skips them). Sets
            ``summary["cancelled"]``.
        card_saved_callback: Called with each freshly-saved ``Card`` so the
            wizard tab can stream it in live (mirrors card_gen).
        cameo_probability: Override the persisted knob (UI / CLI). ``None`` reads
            ``art-prompt-knobs.json``.

    Returns a summary dict with stats.
    """
    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    set_code = require_active_project().set_code
    set_dir = set_artifact_dir()
    cards_dir = set_dir / "cards"
    if not cards_dir.exists():
        raise FileNotFoundError(f"Cards directory not found: {cards_dir}")

    card_files = sorted(cards_dir.glob("*.json"))
    if card_filter:
        card_files = [f for f in card_files if f.name.startswith(card_filter)]
    if not card_files:
        raise ValueError(f"No cards found matching filter: {card_filter}")

    # Stage inputs (all degrade gracefully to empty).
    artists = get_artists()
    set_art_direction = get_set_art_direction()
    theme = _load_theme(set_dir)
    from mtgai.generation.prompts import format_setting_prose

    setting_prose = format_setting_prose(theme)

    if cameo_probability is None:
        cameo_probability = load_art_prompt_knobs(set_dir).cameo_probability

    # Artist assignment over the *whole* credited pool (not just the filter), so a
    # single-card run still credits that card consistently with a full run.
    all_cards = [load_card(f) for f in sorted(cards_dir.glob("*.json"))]
    credited = [c for c in all_cards if _is_credited_card(c)]
    artist_by_cn = assign_artists(
        [
            {
                "collector_number": c.collector_number,
                "rarity": str(c.rarity),
                "colors": [str(x) for x in c.colors],
            }
            for c in credited
        ],
        artists,
    )
    style_by_name = {a["name"]: a.get("style_prompt", "") for a in artists}

    total_input_tokens = 0
    total_output_tokens = 0
    processed = 0
    skipped = 0
    cameos = 0
    errors: list[dict] = []

    log_dir = set_dir / "art_prompts" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    prompt_log_dir = set_dir / "art_prompts" / "prompt-logs"
    prompt_log_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Generating art prompts for %d cards in %s (%d artists, cameo p=%.2f)",
        len(card_files),
        set_code,
        len(artists),
        cameo_probability,
    )

    cancelled = False
    for card_file in card_files:
        if should_cancel is not None and should_cancel():
            logger.info("Art-prompt generation cancelled by user after %d card(s)", processed)
            cancelled = True
            break

        card = load_card(card_file)

        # Skip cards that already have prompts (resumable) unless forced. A
        # single-card filter run always regenerates (the user targeted it).
        if card.art_prompt and not card_filter and not force:
            logger.info("SKIP %s — already has art_prompt", card.collector_number)
            skipped += 1
            continue

        try:
            logger.info("Authoring prompt for %s: %s", card.collector_number, card.name)

            artist_name = artist_by_cn.get(card.collector_number) or card.artist or DEFAULT_ARTIST
            artist_style = style_by_name.get(artist_name, "")
            cameo = _roll_cameo(card, cameo_probability)
            if cameo:
                cameos += 1

            full_prompt_raw, in_tok, out_tok = generate_art_prompt(
                card,
                artist_style=artist_style,
                set_art_direction=set_art_direction,
                setting_prose=setting_prose,
                cameo=cameo,
                log_dir=log_dir,
            )
            full_prompt = _sanitize_for_flux(full_prompt_raw)
            total_input_tokens += in_tok
            total_output_tokens += out_tok

            log_entry = {
                "collector_number": card.collector_number,
                "name": card.name,
                "type_line": card.type_line,
                "artist": artist_name,
                "cameo": cameo,
                "art_prompt": full_prompt,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
            }
            atomic_write_text(
                prompt_log_dir / f"{card.collector_number}.json",
                json.dumps(log_entry, indent=2),
            )

            update: dict = {"art_prompt": full_prompt}
            # Only stamp the credited pool's artist; reprints/basics keep theirs.
            if card.collector_number in artist_by_cn:
                update["artist"] = artist_name
            card = card.model_copy(update=update)

            if not dry_run:
                save_card(card, set_dir=set_dir)

            processed += 1
            logger.info(
                "  → %s [%s]%s (%d+%d tok) — %s",
                "DRY RUN" if dry_run else "SAVED",
                artist_name,
                " +cameo" if cameo else "",
                in_tok,
                out_tok,
                full_prompt[:80] + "..." if len(full_prompt) > 80 else full_prompt,
            )

            if card_saved_callback is not None and not dry_run:
                card_saved_callback(card)

            if progress_callback is not None:
                card_cost = (in_tok * 0.80 / 1_000_000) + (out_tok * 4.0 / 1_000_000)
                progress_callback(
                    card.collector_number,
                    processed + skipped,
                    len(card_files),
                    f"Authored prompt for {card.name}",
                    card_cost,
                )

            time.sleep(0.1)

        except Exception as e:
            logger.error("ERROR on %s: %s", card.collector_number, e)
            errors.append({"card": card.collector_number, "error": str(e)})

    est_cost = (total_input_tokens * 0.80 / 1_000_000) + (total_output_tokens * 4.0 / 1_000_000)

    summary = {
        "set_code": set_code,
        "processed": processed,
        "skipped": skipped,
        "cameos": cameos,
        "errors": len(errors),
        "error_details": errors,
        "artist_count": len(artists),
        "cameo_probability": cameo_probability,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "estimated_cost_usd": round(est_cost, 4),
        "dry_run": dry_run,
        "cancelled": cancelled,
    }

    atomic_write_text(prompt_log_dir / "summary.json", json.dumps(summary, indent=2))

    logger.info(
        "Done: %d processed (%d cameos), %d skipped, %d errors. ~$%.4f",
        processed,
        cameos,
        skipped,
        len(errors),
        est_cost,
    )

    return summary


def _load_theme(set_dir: Path) -> dict | None:
    """Load ``theme.json`` for setting prose, tolerating absence/malformed."""
    theme_path = set_dir / "theme.json"
    if not theme_path.exists():
        return None
    try:
        return json.loads(theme_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Could not read theme.json (%s); art prompts run without setting prose", e)
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Generate art prompts for cards")
    parser.add_argument(
        "--mtg",
        required=True,
        help="Path to a .mtg project file (the project's asset_folder must be set)",
    )
    parser.add_argument("--card", default=None, help="Single card collector number")
    parser.add_argument("--dry-run", action="store_true", help="Don't save to card JSON")
    parser.add_argument("--force", action="store_true", help="Regenerate existing prompts")
    parser.add_argument(
        "--cameo-prob",
        type=float,
        default=None,
        help="Override the per-card cameo probability (0.0-1.0)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    from mtgai.runtime.cli_shim import activate_from_mtg

    activate_from_mtg(args.mtg)
    summary = generate_prompts_for_set(
        card_filter=args.card,
        dry_run=args.dry_run,
        force=args.force,
        cameo_probability=args.cameo_prob,
    )

    print(f"\n{'=' * 60}")
    print(f"Art Prompt Generation — {summary['set_code']}")
    print(f"{'=' * 60}")
    print(f"Artists:   {summary['artist_count']}")
    print(f"Processed: {summary['processed']}  ({summary['cameos']} cameos)")
    print(f"Skipped:   {summary['skipped']}")
    print(f"Errors:    {summary['errors']}")
    print(
        f"Tokens:    {summary['total_input_tokens']:,} in / {summary['total_output_tokens']:,} out"
    )
    print(f"Est. cost: ${summary['estimated_cost_usd']:.4f}")
    print(f"Dry run:   {summary['dry_run']}")
    if summary["error_details"]:
        print("\nErrors:")
        for e in summary["error_details"]:
            print(f"  {e['card']}: {e['error']}")


if __name__ == "__main__":
    main()
