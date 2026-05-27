"""Prompt construction for card generation.

Builds system prompts and user prompts from slot specs, mechanics, set theme,
and previously generated cards.  The 8 pointed questions from Phase 1B are
folded into the generation prompt as preventive design guidance.
"""

from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# System prompt — loaded once from the markdown file, with the fenced block
# extracted so we don't send the design-notes section to the LLM.
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_PATH = Path("C:/Programming/MTGAI/research/prompt-templates/system-prompt-v1.md")
_SYSTEM_PROMPT_CACHE: str | None = None


def load_system_prompt() -> str:
    """Return the system prompt text (cached after first load)."""
    global _SYSTEM_PROMPT_CACHE
    if _SYSTEM_PROMPT_CACHE is not None:
        return _SYSTEM_PROMPT_CACHE

    raw = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    # Extract the fenced code block between the first pair of ```
    match = re.search(r"```[^\n]*\n(.*?)```", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No fenced code block found in {_SYSTEM_PROMPT_PATH}")
    _SYSTEM_PROMPT_CACHE = match.group(1).strip()
    return _SYSTEM_PROMPT_CACHE


# ---------------------------------------------------------------------------
# Preventive design guidance — the 8 pointed questions from Phase 1B,
# rewritten as directives instead of questions.
# ---------------------------------------------------------------------------

def format_preventive_guidance(mechanics: list[dict] | None = None) -> str:
    """Build the preventive-design checklist for the current set.

    Set-agnostic: the custom-keyword line is derived from the set's actual
    ``mechanics`` (``approved.json``) rather than hardcoded, so the rules never
    reference mechanics that don't belong to the set being generated. Trimmed to
    the few high-value, simple directives the LLM most often breaks.
    """
    names = [m.get("name", "") for m in (mechanics or []) if m.get("name")]
    mech_line = ", ".join(names) if names else "none — use only standard evergreen keywords"
    return f"""\
## Preventive Design Checklist (read before designing the card)

1. **Use only this set's keywords.** The custom keywords for this set are: \
{mech_line}. Do NOT invent other named keywords, and do NOT reuse a named \
keyword from a real MTG set. Standard evergreen keywords (Flying, Trample, \
Vigilance, Deathtouch, …) are always fine.
2. **No reminder text.** Never write the parenthetical reminder for a keyword — \
give just the keyword and any number (e.g. the keyword and its value, not the \
"(Look at the top ...)" explanation). Reminder text is added automatically later.
3. **One idea per card.** Each card does ONE thing well — don't staple unrelated \
effects together. At common that means a single keyword OR one short ability, \
not both.
4. **No pointless conditionals.** Don't gate an effect on something that is \
always true (e.g. a condition the spell's own mandatory cost already satisfies). \
The condition must be able to fail in normal play.
5. **No anti-synergy keywords.** Don't combine keywords that fight each other \
(e.g. haste on a creature that enters tapped, or flying on a defender that never \
uses it)."""


# ---------------------------------------------------------------------------
# Color name expansion — Sonnet can confuse single-letter abbreviations
# (especially R != Red). Always spell out full color names in prompts.
# ---------------------------------------------------------------------------

COLOR_NAMES = {
    "W": "White",
    "U": "Blue",
    "B": "Black",
    "R": "Red",
    "G": "Green",
    "colorless": "Colorless",
    "multicolor": "Multicolor",
}


def _expand_color(code: str) -> str:
    return COLOR_NAMES.get(code, code)


# ---------------------------------------------------------------------------
# Mechanic definitions — only include mechanics relevant to a batch
# ---------------------------------------------------------------------------


def format_mechanic_block(mechanics: list[dict], relevant_colors: set[str]) -> str:
    """Return mechanic definition text for mechanics that overlap with the given colors."""
    lines: list[str] = []
    for mech in mechanics:
        mech_colors = set(mech["colors"])
        if mech_colors & relevant_colors or not relevant_colors:
            lines.append(f"### {mech['name']}")
            lines.append(f"- Type: {mech['keyword_type']}")
            lines.append(f"- Reminder text: {mech['reminder_text']}")
            lines.append(f"- Colors: {', '.join(_expand_color(c) for c in mech['colors'])}")
            lines.append(f"- Complexity: {mech['complexity']}")
            rarity_range = mech.get("rarity_range", [])
            if rarity_range:
                lines.append(f"- Appears at: {', '.join(rarity_range)}")
            lines.append(f"- Design notes: {mech['design_notes']}")
            lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Set context — compressed summary of already-generated cards
# ---------------------------------------------------------------------------


def format_set_context(existing_cards: list[dict]) -> str:
    """Build a compressed context block from previously generated cards.

    Each card gets a one-line summary. Color distribution stats appended.
    ``existing_cards`` is a list of Card-like dicts (or Card model instances
    serialized to dict).
    """
    if not existing_cards:
        return ""

    lines: list[str] = ["**Cards already in the set** (do NOT duplicate names or effects):"]
    color_counts: dict[str, int] = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0}

    for c in existing_cards:
        name = c.get("name", "?")
        cost = c.get("mana_cost", "")
        tl = c.get("type_line", "")
        oracle = c.get("oracle_text", "")
        # Truncate oracle at a clause boundary (sentence end or newline) up to 120 chars
        flat = oracle.replace("\n", " | ")
        if len(flat) <= 120:
            summary = flat
        else:
            cut = flat[:120]
            # Try to break at a sentence boundary
            last_period = cut.rfind(". ")
            last_pipe = cut.rfind(" | ")
            break_at = max(last_period + 1, last_pipe) if max(last_period, last_pipe) > 40 else 120
            summary = cut[:break_at].rstrip() + "..."
        # Include P/T for creatures so the model can gauge stat lines already in
        # the set (helps avoid duplicating bodies / mis-curving).
        power, toughness = c.get("power"), c.get("toughness")
        pt = f" {power}/{toughness}" if power is not None and toughness is not None else ""
        lines.append(f"- {name} ({cost}) — {tl}{pt} — {summary}")

        for clr in c.get("colors", []):
            if clr in color_counts:
                color_counts[clr] += 1

    lines.append("")
    lines.append(f"**Color distribution so far**: {color_counts}")
    lines.append(f"**Total cards**: {len(existing_cards)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Slot specification — what the LLM needs to generate
# ---------------------------------------------------------------------------


def format_slot_specs(
    slots: list[dict],
    theme: dict | None = None,
    archetypes: list[dict] | None = None,
) -> str:
    """Format a list of skeleton slots into a generation request.

    ``theme`` is the set theme.json dict (optional, for archetype descriptions).
    ``archetypes``, when provided, is the TC-3 ``archetypes.json`` list and
    overrides the theme's ``draft_archetypes`` for slot annotations. Both
    shapes carry the same ``color_pair`` / ``name`` / ``description`` keys.
    """
    arch_source = (
        archetypes if archetypes is not None else (theme or {}).get("draft_archetypes", [])
    )
    archetype_map: dict[str, str] = {}
    for arch in arch_source:
        pair = arch.get("color_pair")
        if pair:
            archetype_map[pair] = f"{arch.get('name', '')}: {arch.get('description', '')}"

    lines: list[str] = [f"Generate exactly {len(slots)} card(s):\n"]

    for i, slot in enumerate(slots, 1):
        # Relabeled-skeleton path (Skeleton Generation): the slot's spec is the
        # LLM-rewritten one-line descriptor (``tweaked_text``) — color, rarity,
        # type, mechanic, role are all in it — so we emit it verbatim instead of
        # rebuilding a structured line. ``reserved_card`` is repeated explicitly
        # in case the descriptor didn't fold the request in.
        tweaked = (slot.get("tweaked_text") or "").strip()
        if tweaked:
            spec = f"Card {i}: {tweaked}"
            reserved = (slot.get("reserved_card") or "").strip()
            if reserved and reserved != tweaked:
                # Descriptor and request differ (legacy / deterministic-reserved
                # path) — spell the request out so it isn't lost.
                spec += f"\n   REQUESTED CARD — design this slot as: {reserved}"
            elif reserved:
                # The descriptor already IS the request (Skeleton assign pass) —
                # flag it as fixed instead of repeating the same text.
                spec += "\n   REQUESTED CARD — this slot is a specifically requested card."
            # The structural flags survive the relabel untouched, so keep their
            # deterministic instructions rather than trusting the blob's prose.
            if slot.get("is_reprint_slot"):
                spec += (
                    "\n   REPRINT SLOT — design a card suitable as a reprint from an existing set"
                )
            signpost_for = (slot.get("signpost_for") or "").strip()
            if signpost_for:
                arch = archetype_map.get(signpost_for)
                arch_note = f" — {arch}" if arch else ""
                spec += (
                    f"\n   SIGNPOST UNCOMMON for the {signpost_for} archetype{arch_note}. "
                    "Design the gold uncommon that defines and enables this archetype."
                )
            else:
                # Ordinary gold slot: point at the archetype it serves so the
                # relabeled descriptor is anchored to a strategy (signpost slots
                # already state their archetype above). Full descriptions live in
                # the Draft Archetypes section.
                color_pair = slot.get("color_pair")
                if color_pair and color_pair in archetype_map:
                    spec += f"\n   Archetype — {archetype_map[color_pair]}"
            spec += _cycle_note(slot)
            lines.append(spec)
            continue

        color = slot["color"]
        color_name = _expand_color(color)
        rarity = slot["rarity"]
        card_type = slot["card_type"]
        cmc = slot["cmc_target"]
        mechanic_tag = slot.get("mechanic_tag", "")
        color_pair = slot.get("color_pair")

        spec = f"Card {i}: {color_name} {rarity} {card_type}, CMC ~{cmc}"

        if mechanic_tag and mechanic_tag not in ("vanilla", "french_vanilla", "evergreen"):
            spec += f", mechanic: {mechanic_tag}"
        elif mechanic_tag == "vanilla":
            spec += ", vanilla (no abilities or keyword-only)"
        elif mechanic_tag == "french_vanilla":
            spec += ", french vanilla (one evergreen keyword only)"

        if color_pair:
            spec += f", colors: {_expand_color(color_pair[0])}/{_expand_color(color_pair[1])}"
            if color_pair in archetype_map:
                spec += f"\n   Archetype — {archetype_map[color_pair]}"

        # Include archetype guidance for monocolor slots via archetype_tags
        archetype_tags = slot.get("archetype_tags", [])
        if archetype_tags and not color_pair:
            arch_descs = [archetype_map[tag] for tag in archetype_tags if tag in archetype_map]
            if arch_descs:
                spec += f"\n   Supports archetypes: {'; '.join(arch_descs)}"

        if slot.get("is_reprint_slot"):
            spec += "\n   REPRINT SLOT — design a card suitable as a reprint from an existing set"

        reserved_card = (slot.get("reserved_card") or "").strip()
        if reserved_card:
            spec += f"\n   REQUESTED CARD — design this slot as: {reserved_card}"

        signpost_for = (slot.get("signpost_for") or "").strip()
        if signpost_for:
            arch = archetype_map.get(signpost_for)
            arch_note = f" — {arch}" if arch else ""
            spec += (
                f"\n   SIGNPOST UNCOMMON for the {signpost_for} archetype{arch_note}. "
                "Design the gold uncommon that defines and enables this archetype — the "
                "card a drafter sees and immediately knows what deck to build."
            )

        notes = slot.get("notes", "").strip()
        if notes:
            spec += f"\n   Notes: {notes}"

        spec += _cycle_note(slot)
        lines.append(spec)

    return "\n".join(lines)


def _cycle_note(slot: dict) -> str:
    """A CYCLE instruction for a cycle-member slot, else "".

    Card-gen batches a cycle's members together; this tells the model they are one
    family that must share a design template / parallel structure. The shared
    template is stamped onto the slot dict (``cycle_template``) by card_generator.
    """
    if not slot.get("cycle_id"):
        return ""
    template = (slot.get("cycle_template") or "").strip()
    note = (
        "\n   CYCLE MEMBER — this card is one of a cycle generated together; "
        "give the family parallel structure and a shared design."
    )
    if template:
        note += f" Cycle template: {template}"
    return note


# ---------------------------------------------------------------------------
# Setting prose — the set's flavor section, read from theme.json
# ---------------------------------------------------------------------------


def format_setting_prose(theme: dict | None) -> str:
    """Build the set-flavor section from ``theme.json`` setting prose.

    Reads the prose fields the theme extractor writes, tolerating any
    setting's shape (no hardcoded ASD structure, no required keys):

    * ``name`` — display name (optional)
    * ``theme`` — a one-line premise (optional; older ASD-style themes)
    * ``setting`` / ``flavor_description`` — the multi-paragraph setting prose.
      The pipeline (``_persist_extraction_to_theme_json``) writes the full
      world document to ``setting``; ASD-style themes use ``flavor_description``.
    * ``flavor_text_guidelines.tone`` — flavor-text tone hint (optional)

    Returns an empty string when no prose is present, so the caller can
    skip the section entirely.
    """
    theme = theme or {}
    name = (theme.get("name") or "").strip()
    one_liner = (theme.get("theme") or "").strip()
    prose = (theme.get("flavor_description") or theme.get("setting") or "").strip()
    guidelines = theme.get("flavor_text_guidelines") or {}
    tone = (guidelines.get("tone") or "").strip() if isinstance(guidelines, dict) else ""

    if not (one_liner or prose):
        return ""

    parts: list[str] = [f"## Set: {name}" if name else "## Setting"]
    if one_liner:
        parts.append(f"Theme: {one_liner}")
    if prose:
        parts.append(prose)
    if tone:
        parts.append(f"Flavor text tone: {tone}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Draft archetypes — the set's two-color strategic map, shown as set context
# ---------------------------------------------------------------------------


def format_archetypes_section(
    archetypes: list[dict] | None = None,
    theme: dict | None = None,
) -> str:
    """Build the Draft Archetypes context block (one line per color pair).

    Surfaces the set's draft strategies up front so the model has the strategic
    map when designing any card — not just the signpost uncommons. ``archetypes``
    (TC-3 ``archetypes.json``) overrides the theme's ``draft_archetypes`` when
    provided, mirroring :func:`format_slot_specs`. Returns "" when there are none.
    """
    arch_source = (
        archetypes if archetypes is not None else (theme or {}).get("draft_archetypes", [])
    )
    rows: list[str] = []
    for arch in arch_source:
        pair = arch.get("color_pair")
        if not pair:
            continue
        name = arch.get("name", "")
        desc = arch.get("description", "")
        rows.append(f"- {pair} — {name}: {desc}" if desc else f"- {pair} — {name}")
    if not rows:
        return ""
    return (
        "## Draft Archetypes\n\n"
        "The set's two-color draft strategies. Design each card to reinforce the "
        "archetype(s) that match its colors:\n" + "\n".join(rows)
    )


# ---------------------------------------------------------------------------
# Full user prompt assembly
# ---------------------------------------------------------------------------


def build_user_prompt(
    slots: list[dict],
    mechanics: list[dict],
    existing_cards: list[dict],
    theme: dict | None = None,
    archetypes: list[dict] | None = None,
) -> str:
    """Assemble the complete user prompt for a batch generation call.

    Includes: set flavor (setting prose from ``theme.json``), relevant
    mechanics, preventive guidance, existing card context, and slot
    specifications. ``archetypes`` (the TC-3 ``archetypes.json`` list)
    overrides the theme's ``draft_archetypes`` when provided.
    """
    sections: list[str] = []

    # Set flavor — setting prose, robust to any setting's theme.json shape
    if theme:
        prose_block = format_setting_prose(theme)
        if prose_block:
            sections.append(prose_block)

    # Custom mechanics — include ALL of the set's mechanics, not just those whose
    # colors match the batch. There are only a handful, and the skeleton relabel
    # can assign any mechanic to a slot regardless of the slot's default color, so
    # color-filtering would drop the very definition the card needs. (An empty
    # color set means "include all" in format_mechanic_block.)
    mech_block = format_mechanic_block(mechanics, set())
    if mech_block.strip():
        sections.append(f"## Custom Mechanics for This Set\n\n{mech_block}")

    # Draft archetypes — the set's strategic map (shown whenever available).
    arch_block = format_archetypes_section(archetypes, theme)
    if arch_block:
        sections.append(arch_block)

    # Preventive guidance — set-agnostic; names this set's own mechanics.
    sections.append(format_preventive_guidance(mechanics))

    # Existing card context
    ctx = format_set_context(existing_cards)
    if ctx:
        sections.append(ctx)

    # Slot specs
    sections.append(format_slot_specs(slots, theme, archetypes))

    return "\n\n---\n\n".join(sections)
