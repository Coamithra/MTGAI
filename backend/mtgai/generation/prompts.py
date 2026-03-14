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

PREVENTIVE_GUIDANCE = """\
## Preventive Design Checklist (read before designing each card)

1. **No keyword nonbos.** Do NOT give a creature haste if it enters tapped \
(e.g. via Malfunction). Do NOT give flying to a creature with defender \
unless the card explicitly cares about it.
2. **No reminder text.** Do NOT include reminder text in parentheses for any \
keyword (custom or evergreen). Reminder text is added programmatically later. \
Just write the keyword and any parameters, e.g. "Salvage 3" not \
"Salvage 3 (Look at the top three cards...)".
3. **Meaningful conditionals only.** If an effect says "if you [did X] this \
turn" but X is a mandatory cost of the same spell, the condition is always \
true and therefore pointless. Remove the conditional or make the trigger \
come from a separate source.
4. **Respect rarity power budgets.** Common creatures: P+T <= CMC+3. Commons \
get one keyword OR one short text ability, not both. Unconditional removal \
starts at uncommon. Card draw at common is 1 card with a condition.
5. **Single purpose, not kitchen sink.** Each card should do ONE thing well. \
Do not pile unrelated effects onto a single card.
6. **Real variability only.** If damage/effect scales with a count, the count \
must actually vary in normal gameplay. "Deal damage equal to cards exiled" \
where the exile count is always fixed = fake variability.
7. **No keyword name collisions.** Do NOT use "Scavenge" (existing RTR \
keyword) or "Overload" (existing RTR keyword). Our mechanics are Salvage, \
Malfunction, and Overclock.
8. **Relevant enters-tapped only.** "Enters tapped" is irrelevant on a \
noncreature, non-vehicle permanent with no tap abilities. Only add it where \
it creates a real tempo cost."""


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
        lines.append(f"- {name} ({cost}) — {tl} — {summary}")

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


def format_slot_specs(slots: list[dict], theme: dict | None = None) -> str:
    """Format a list of skeleton slots into a generation request.

    ``theme`` is the set theme.json dict (optional, for archetype descriptions).
    """
    archetype_map: dict[str, str] = {}
    if theme:
        for arch in theme.get("draft_archetypes", []):
            archetype_map[arch["color_pair"]] = f"{arch['name']}: {arch['description']}"

    lines: list[str] = [f"Generate exactly {len(slots)} card(s):\n"]

    for i, slot in enumerate(slots, 1):
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

        notes = slot.get("notes", "").strip()
        if notes:
            spec += f"\n   Notes: {notes}"

        lines.append(spec)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Full user prompt assembly
# ---------------------------------------------------------------------------


def build_user_prompt(
    slots: list[dict],
    mechanics: list[dict],
    existing_cards: list[dict],
    theme: dict | None = None,
) -> str:
    """Assemble the complete user prompt for a batch generation call.

    Includes: set flavor, relevant mechanics, preventive guidance, existing
    card context, and slot specifications.
    """
    sections: list[str] = []

    # Set flavor
    if theme:
        sections.append(
            f"## Set: {theme['name']}\n\n"
            f"Theme: {theme['theme']}\n\n"
            f"{theme['flavor_description']}\n\n"
            f"Flavor text tone: {theme.get('flavor_text_guidelines', {}).get('tone', '')}"
        )

    # Relevant mechanics
    relevant_colors: set[str] = set()
    for slot in slots:
        c = slot["color"]
        if c == "multicolor" and slot.get("color_pair"):
            relevant_colors.update(slot["color_pair"])
        elif c != "colorless":
            relevant_colors.add(c)

    mech_block = format_mechanic_block(mechanics, relevant_colors)
    if mech_block.strip():
        sections.append(f"## Custom Mechanics for This Set\n\n{mech_block}")

    # Preventive guidance
    sections.append(PREVENTIVE_GUIDANCE)

    # Existing card context
    ctx = format_set_context(existing_cards)
    if ctx:
        sections.append(ctx)

    # Slot specs
    sections.append(format_slot_specs(slots, theme))

    return "\n\n---\n\n".join(sections)
