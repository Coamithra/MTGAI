"""Art prompt generation pipeline.

Assembles Flux-optimized image-generation prompts for cards by combining:
1. LLM-generated visual description (Haiku translates MTG → plain English)
2. Concise style + context line (from card colors + world-building)

Flux prompt best practices (from BFL docs):
- Front-load the subject (Flux pays most attention to what comes first)
- 30-80 words is the sweet spot
- Natural language, not keyword lists
- Avoid negative phrasing ("no text") — use positive alternatives
- Structure: Subject + Action + Style + Context

CLI usage:
    python -m mtgai.art.prompt_builder --set ASD [--card W-C-01] [--dry-run]
"""

import argparse
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path

from mtgai.art.visual_reference import (
    detect_named_characters,
    get_flux_replacements,
    get_visual_references,
)
from mtgai.generation.llm_client import generate_with_tool
from mtgai.io.card_io import load_card, save_card
from mtgai.models.card import Card

logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path("C:/Programming/MTGAI/output")

# ---------------------------------------------------------------------------
# Style lines — one concise line per color, appended after the subject
# ---------------------------------------------------------------------------

STYLE_LINES: dict[str, str] = {
    "W": (
        "Stylized digital illustration, structured balanced composition, "
        "warm sandstone and ivory tones, golden-hour lighting with long shadows, "
        "post-apocalyptic science-fantasy setting"
    ),
    "U": (
        "Stylized digital illustration, geometric composition, "
        "cool steel-blue and teal palette, screen-glow lighting, "
        "post-apocalyptic science-fantasy setting"
    ),
    "B": (
        "Stylized digital illustration, heavy shadows with minimal light, "
        "organic textures and wet surfaces, unsettling asymmetry, "
        "post-apocalyptic science-fantasy setting"
    ),
    "R": (
        "Stylized digital illustration, dynamic tilted composition, "
        "warm fire-tones with high contrast, kinetic energy, "
        "post-apocalyptic science-fantasy setting"
    ),
    "G": (
        "Stylized digital illustration, wide naturalist composition, "
        "rich earth tones with dappled light, layered depth, "
        "post-apocalyptic science-fantasy setting"
    ),
    "COLORLESS": (
        "Stylized digital illustration, centered object-focused composition, "
        "self-illuminated subject against dark background, "
        "ancient technology aesthetic"
    ),
    "LAND": (
        "Stylized digital illustration, panoramic landscape, "
        "dramatic atmospheric perspective, concept-art establishing shot, "
        "post-apocalyptic science-fantasy setting"
    ),
}


def get_style_line(card: Card) -> str:
    """Select the one-line style directive based on card colors and type."""
    if "Land" in card.type_line:
        return STYLE_LINES["LAND"]
    if not card.colors:
        return STYLE_LINES["COLORLESS"]
    primary = card.colors[0]
    return STYLE_LINES.get(primary, STYLE_LINES["COLORLESS"])


# ---------------------------------------------------------------------------
# Card type detection
# ---------------------------------------------------------------------------


def get_card_type_category(card: Card) -> str:
    """Categorize a card into a broad type for template selection."""
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
# LLM visual description generation
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an art director writing image generation prompts for Flux (a diffusion \
model). Your job is to translate card game data into concise, vivid visual \
descriptions.

CRITICAL RULES FOR FLUX PROMPTS:
- Front-load the subject. Start with WHAT we see, not style or mood.
- Target 40-60 words total. Dense, specific, every word earns its place.
- Use natural descriptive language, not keyword lists.
- Be concrete: "a gaunt pale humanoid with reflective cat-eyes crouching \
  in a dark corridor" not "a mysterious dungeon creature."
- DO NOT use character names — the image model doesn't know them. Describe \
  their APPEARANCE instead.
- DO NOT use made-up race/creature names (moktar, morlock, screechman, \
  grunkie, peryton, etc.) — the image model doesn't know them. Use the \
  visual description provided instead. Write "a muscular grey-green \
  skinned tribal humanoid" not "a moktar."
- DO NOT use negative phrasing ("no text", "without borders"). Describe only \
  what IS in the image.
- DO NOT mention game mechanics, stats, or rules.
- DO NOT say "card game illustration" or reference cards/frames.
- Rarity guides detail level: common = simple/grounded, mythic = epic/detailed.
- If visual references are provided for setting-specific creatures or factions, \
  incorporate their described appearance naturally — never the label/name."""

TOOL_SCHEMA = {
    "name": "art_description",
    "description": "Generate a Flux-optimized visual description for card art.",
    "input_schema": {
        "type": "object",
        "properties": {
            "visual_description": {
                "type": "string",
                "description": (
                    "A 40-60 word vivid visual description starting with the "
                    "subject. Concrete, specific, natural language. Describe "
                    "appearance not names."
                ),
            },
        },
        "required": ["visual_description"],
    },
}


def _build_llm_user_prompt(card: Card, visual_refs: str) -> str:
    """Build the user prompt for the LLM to generate a visual description."""
    card_type_cat = get_card_type_category(card)

    # Concise type-specific hints
    composition_hints = {
        "creature": "Subject fills 60-70% of frame, action pose.",
        "instant": "Frozen moment of dramatic action, tight crop.",
        "sorcery": "Sweeping display of power, wider framing.",
        "enchantment": "Persistent ethereal effect transforming a scene, atmospheric.",
        "artifact": "Object centered with fine detail, muted background.",
        "equipment": "Item being wielded, item is the focal point.",
        "basic_land": "Panoramic landscape, no figures, ancient ruins in nature.",
        "nonbasic_land": "Panoramic location, no prominent figures, sense of place.",
    }
    hint = composition_hints.get(card_type_cat, "")

    parts = [
        f"Card: {card.name}",
        f"Type: {card.type_line}",
        f"Rarity: {card.rarity}",
    ]
    if card.power is not None:
        parts.append(f"Size: {card.power}/{card.toughness}")
    if card.oracle_text:
        parts.append(f"Abilities (context only): {card.oracle_text}")
    if card.flavor_text:
        parts.append(f"Flavor: {card.flavor_text}")
    if card.design_notes:
        parts.append(f"Notes: {card.design_notes}")

    card_info = "\n".join(parts)

    prompt = f"""{card_info}

Composition: {hint}"""

    if "Legendary" in (card.type_line or ""):
        prompt += "\nThis is a unique, named character — distinctive features, imposing."

    if visual_refs:
        prompt += f"""

VISUAL APPEARANCE REFERENCES (use these, don't use character names):
{visual_refs}"""

    prompt += """

Write a 40-60 word visual description. Start with the subject. \
Describe appearance, not names. Plain English, concrete details."""

    return prompt


def generate_visual_description(card: Card, set_code: str = "ASD") -> tuple[str, int, int]:
    """Call Haiku to generate a visual description for a card.

    Returns (description, input_tokens, output_tokens).
    """
    visual_refs = get_visual_references(
        card.name,
        card.type_line,
        card.oracle_text,
        card.flavor_text,
        set_code=set_code,
    )

    user_prompt = _build_llm_user_prompt(card, visual_refs)

    result = generate_with_tool(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        tool_schema=TOOL_SCHEMA,
        model="claude-haiku-4-5-20251001",
        temperature=0.6,
        max_tokens=512,
    )

    desc = result["result"]["visual_description"]
    return desc, result["input_tokens"], result["output_tokens"]


# ---------------------------------------------------------------------------
# Full prompt assembly (Flux-optimized)
# ---------------------------------------------------------------------------


def _sanitize_for_flux(text: str, set_code: str = "ASD") -> str:
    """Replace setting-specific terms that Flux won't understand.

    Replacements are loaded from visual-references.json (flux_term_replacements),
    so they're data-driven per set, not hardcoded.
    """
    import re

    replacements = get_flux_replacements(set_code)
    for term, replacement in replacements.items():
        text = re.sub(rf"\b{re.escape(term)}\b", replacement, text, flags=re.IGNORECASE)
    return text


def assemble_full_prompt(card: Card, visual_description: str, set_code: str = "ASD") -> str:
    """Assemble the Flux-optimized prompt: subject first, then style."""
    # Sanitize setting-specific terms Flux won't understand
    clean_desc = _sanitize_for_flux(visual_description, set_code)

    # Subject description (front-loaded — Flux prioritizes this)
    # Style line (concise, appended after subject)
    style = get_style_line(card)

    # Strip trailing period from description to avoid double-period
    clean_desc = clean_desc.rstrip(". ")
    return f"{clean_desc}. {style}."


# ---------------------------------------------------------------------------
# Character reference image tracking
# ---------------------------------------------------------------------------


def get_character_ref_paths(card: Card, set_code: str) -> list[dict]:
    """Check if any named characters on this card have reference images.

    Returns list of {character_name, ref_image_path} for characters that
    have reference images generated. These should be used as IP-Adapter
    or img2img conditioning in the ComfyUI workflow.
    """
    refs_dir = OUTPUT_ROOT / "sets" / set_code / "art-direction" / "character-refs"
    if not refs_dir.exists():
        return []

    # Detect which named characters appear on this card
    characters = detect_named_characters(
        card.name,
        card.type_line,
        card.oracle_text,
        card.flavor_text,
        set_code=set_code,
    )

    results = []
    for char_key in characters:
        # Look for reference image files matching the character key
        for ext in (".png", ".jpg", ".webp"):
            ref_path = refs_dir / f"{char_key}{ext}"
            if ref_path.exists():
                results.append(
                    {
                        "character": char_key,
                        "ref_image_path": str(ref_path),
                    }
                )
                break

    return results


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------


def generate_prompts_for_set(
    set_code: str,
    card_filter: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    progress_callback: Callable[[str, int, int, str, float], None] | None = None,
) -> dict:
    """Generate art prompts for all cards in a set.

    Args:
        set_code: The set code (e.g., "ASD").
        card_filter: Optional collector number to process a single card.
        dry_run: If True, generate prompts but don't save to card JSON.
        force: If True, regenerate even if art_prompt already exists.

    Returns summary dict with stats.
    """
    cards_dir = OUTPUT_ROOT / "sets" / set_code / "cards"
    if not cards_dir.exists():
        raise FileNotFoundError(f"Cards directory not found: {cards_dir}")

    card_files = sorted(cards_dir.glob("*.json"))
    if card_filter:
        card_files = [f for f in card_files if f.name.startswith(card_filter)]

    if not card_files:
        raise ValueError(f"No cards found matching filter: {card_filter}")

    total_input_tokens = 0
    total_output_tokens = 0
    processed = 0
    skipped = 0
    errors = []

    # Log directory for prompt generation
    log_dir = OUTPUT_ROOT / "sets" / set_code / "art-direction" / "prompt-logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Generating art prompts for %d cards in %s", len(card_files), set_code)

    for card_file in card_files:
        card = load_card(card_file)

        # Skip cards that already have prompts (resumable) unless forced
        if card.art_prompt and not card_filter and not force:
            logger.info("SKIP %s — already has art_prompt", card.collector_number)
            skipped += 1
            continue

        try:
            logger.info("Generating prompt for %s: %s", card.collector_number, card.name)

            # Generate visual description via LLM
            visual_desc, in_tok, out_tok = generate_visual_description(card, set_code=set_code)
            total_input_tokens += in_tok
            total_output_tokens += out_tok

            # Assemble full prompt
            full_prompt = assemble_full_prompt(card, visual_desc, set_code=set_code)

            # Check for character reference images
            char_refs = get_character_ref_paths(card, set_code)

            # Log the prompt
            log_entry = {
                "collector_number": card.collector_number,
                "name": card.name,
                "type_line": card.type_line,
                "visual_description": visual_desc,
                "full_prompt": full_prompt,
                "character_refs": char_refs,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
            }
            log_path = log_dir / f"{card.collector_number}.json"
            log_path.write_text(json.dumps(log_entry, indent=2), encoding="utf-8")

            if not dry_run:
                card.art_prompt = full_prompt
                save_card(card, OUTPUT_ROOT)

            processed += 1
            logger.info(
                "  → %s (%d+%d tok, %d char_refs) — %s",
                "DRY RUN" if dry_run else "SAVED",
                in_tok,
                out_tok,
                len(char_refs),
                visual_desc[:80] + "..." if len(visual_desc) > 80 else visual_desc,
            )

            if progress_callback is not None:
                card_cost = (in_tok * 0.80 / 1_000_000) + (out_tok * 4.0 / 1_000_000)
                progress_callback(
                    card.collector_number,
                    processed + skipped,
                    len(card_files),
                    f"Generated prompt for {card.name}",
                    card_cost,
                )

            # Rate limit: small delay between API calls
            time.sleep(0.1)

        except Exception as e:
            logger.error("ERROR on %s: %s", card.collector_number, e)
            errors.append({"card": card.collector_number, "error": str(e)})

    # Estimate cost (Haiku pricing: $0.80/M input, $4/M output as of 2025)
    est_cost = (total_input_tokens * 0.80 / 1_000_000) + (total_output_tokens * 4.0 / 1_000_000)

    summary = {
        "set_code": set_code,
        "processed": processed,
        "skipped": skipped,
        "errors": len(errors),
        "error_details": errors,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "estimated_cost_usd": round(est_cost, 4),
        "dry_run": dry_run,
    }

    # Save summary
    summary_path = log_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    logger.info(
        "Done: %d processed, %d skipped, %d errors. ~$%.4f",
        processed,
        skipped,
        len(errors),
        est_cost,
    )

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Generate art prompts for cards")
    parser.add_argument("--set", default="ASD", help="Set code (default: ASD)")
    parser.add_argument("--card", default=None, help="Single card collector number")
    parser.add_argument("--dry-run", action="store_true", help="Don't save to card JSON")
    parser.add_argument("--force", action="store_true", help="Regenerate existing prompts")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    summary = generate_prompts_for_set(
        set_code=args.set,
        card_filter=args.card,
        dry_run=args.dry_run,
        force=args.force,
    )

    print(f"\n{'=' * 60}")
    print(f"Art Prompt Generation — {summary['set_code']}")
    print(f"{'=' * 60}")
    print(f"Processed: {summary['processed']}")
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
