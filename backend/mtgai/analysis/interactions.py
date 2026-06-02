"""Set-level interaction analysis — LLM-based degenerate combo detection.

The whole-pool interaction step of the merged ``conformance`` gate (displayed
"Conformance & Interactions"). Feeds the generated pool — minus basic lands and reprints — to an LLM
and asks it to identify dangerous 2-3 card interactions: infinite combos,
degenerate loops, and unintended synergies that break the format.

For each flagged interaction the LLM names the "enabler" card — the one whose
design is the root cause — and a ``replacement_constraint``. The runner
(:func:`mtgai.pipeline.stages.run_conformance`) flags that enabler card for
regeneration, threading the constraint into its ``regen_reason``.

Usage:
    from mtgai.analysis.interactions import analyze_interactions

    flags, analysis_text, cost = analyze_interactions(cards, mechanics)
"""

from __future__ import annotations

import logging
import re

from mtgai.analysis.gate_common import filter_gate_cards, generate_gate_tool
from mtgai.analysis.models import InteractionFlag
from mtgai.generation import temperatures as temps
from mtgai.generation.llm_client import cost_from_result
from mtgai.generation.token_budgets import HEAVY
from mtgai.models.card import Card

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Model + effort come from per-set model_settings at runtime.
TEMPERATURE = temps.ANALYTICAL  # analytical scan (see temperatures.py)
MAX_TOKENS = HEAVY

# ---------------------------------------------------------------------------
# Card serialization — full oracle text, no truncation
# ---------------------------------------------------------------------------


def _serialize_card_full(card: Card) -> str:
    """Full card text for interaction analysis — no truncation."""
    slot = card.slot_id or card.collector_number or "?"
    name = card.name
    cost = card.mana_cost or ""
    tl = card.type_line
    rarity = card.rarity or "?"

    stats = ""
    if card.power is not None and card.toughness is not None:
        stats = f" [{card.power}/{card.toughness}]"
    elif card.loyalty is not None:
        stats = f" [Loyalty: {card.loyalty}]"

    oracle = card.oracle_text or ""
    # Strip reminder text for readability — mechanics are explained separately
    oracle = re.sub(r"\([^)]{20,}\)", "", oracle).strip()
    oracle = re.sub(r"\n+", " / ", oracle)

    return f"{slot} | {name} | {cost} | {tl}{stats} | {rarity} | {oracle}"


def _serialize_all_cards_full(cards: list[Card]) -> str:
    """Serialize all cards with full oracle text."""
    lines = [_serialize_card_full(c) for c in cards]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt and tool schema
# ---------------------------------------------------------------------------

INTERACTION_SYSTEM_PROMPT = """\
You are an expert Magic: The Gathering developer specializing in play design \
and format health. Your job is to analyze a card pool and identify degenerate \
card interactions that would be problematic in a limited (draft/sealed) format.

You are looking for:
1. **Infinite combos** — two or three cards that create an unbounded loop \
(infinite damage, infinite tokens, infinite life, infinite mana, etc.)
2. **Degenerate synergies** — two cards that together produce an effect far \
beyond what either card's rarity and mana cost should allow (e.g., a common \
that accidentally enables a mythic-level board state)
3. **Unintended loops** — cards that trigger each other repeatedly without \
a natural stopping point

You are NOT looking for:
- Strong synergies that are intentional design (e.g., a payoff card \
rewarding the mechanic, card type, or archetype it is built around is the \
set's theme working as intended, not a degenerate interaction)
- Cards that are individually strong but don't create problematic interactions
- Three-card combos that require very specific board states (too unlikely in limited)
- Color-pair synergies that only work if you draft both colors (that's normal)

For each problematic interaction, identify the **enabler** — the card whose \
design is the root cause. The enabler is typically the card that provides an \
undercosted or unrestricted effect (free untap, cost reduction, repeated \
recursion). The other card(s) in the combo are usually fine on their own.

If no degenerate interactions exist, return an empty flags list. Do not \
fabricate problems — false positives waste design time."""

INTERACTION_TOOL_SCHEMA = {
    "name": "report_interactions",
    "description": "Report degenerate card interactions found in the card pool",
    "input_schema": {
        "type": "object",
        "properties": {
            "analysis": {
                "type": "string",
                "description": (
                    "Brief overall assessment of the card pool's interaction health. "
                    "Note any general patterns of concern even if they don't rise to "
                    "the level of a specific flag."
                ),
            },
            "flags": {
                "type": "array",
                "description": ("List of degenerate interactions found. Empty if none."),
                "items": {
                    "type": "object",
                    "properties": {
                        "enabler_slot_id": {
                            "type": "string",
                            "description": (
                                "Slot ID / collector number of the enabler — the one "
                                "card whose design is the root cause and should be "
                                "regenerated. This is required; a flag without it is "
                                "dropped."
                            ),
                        },
                        "reason": {
                            "type": "string",
                            "description": (
                                "The diagnosis: which cards combo, and step-by-step how "
                                "the degenerate interaction works. Name the other card(s) "
                                "involved here so the explanation stands on its own."
                            ),
                        },
                        "replacement_constraint": {
                            "type": "string",
                            "description": (
                                "The fix: what the regenerated enabler card must avoid to "
                                "prevent this interaction. A brief structural constraint "
                                "(e.g. 'no free untap of a creature'), not a restatement "
                                "of the problem."
                            ),
                        },
                    },
                    "required": [
                        "enabler_slot_id",
                        "reason",
                        "replacement_constraint",
                    ],
                },
            },
        },
        "required": ["analysis", "flags"],
    },
}


# ---------------------------------------------------------------------------
# Build prompt
# ---------------------------------------------------------------------------


def _build_interaction_prompt(
    cards: list[Card],
    mechanics: list[dict],
) -> str:
    """Build the user prompt for interaction analysis."""
    sections: list[str] = []

    # Card pool
    card_text = _serialize_all_cards_full(cards)
    sections.append(f"## Card Pool ({len(cards)} cards)\n\n```\n{card_text}\n```")

    # Mechanic definitions
    mech_lines: list[str] = []
    for mech in mechanics:
        mech_lines.append(f"- **{mech['name']}**: {mech['reminder_text']}")
    sections.append("## Custom Mechanics\n\n" + "\n".join(mech_lines))

    # Instructions
    sections.append(
        "## Task\n\n"
        "Analyze this card pool for degenerate interactions. For each problem "
        "found, identify the enabler card (the one to replace) and explain "
        "step-by-step how the interaction works.\n\n"
        "Remember: this is a limited format (draft/sealed). Players open ~45 "
        "cards and build 40-card decks. Two-card combos at common are much more "
        "likely to occur than three-card combos at rare. Weight your severity "
        "accordingly.\n\n"
        "If the card pool is clean, return an empty flags list."
    )

    return "\n\n---\n\n".join(sections)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def analyze_interactions(
    cards: list[Card],
    mechanics: list[dict],
) -> tuple[list[InteractionFlag], str, float]:
    """Scan the pool for degenerate interactions.

    Skips basic lands + reprints. Returns ``(flags, analysis_text, cost_usd)``;
    each flag names an enabler card (by ``enabler_slot_id``) the runner will
    flag for regeneration. Flags missing an enabler slot id are dropped — they
    can't drive a regen, and bare-tier local models sometimes omit fields the
    schema marks required, so every field is read defensively.
    """
    gate_cards = filter_gate_cards(cards)
    if not gate_cards:
        return [], "", 0.0

    user_prompt = _build_interaction_prompt(gate_cards, mechanics)

    logger.info(
        "Interaction analysis: %d cards, prompt %d chars",
        len(gate_cards),
        len(user_prompt),
    )

    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    settings = require_active_project().settings
    try:
        # The interaction step shares the merged ``conformance`` gate's log dir
        # (distinct convo names keep the two steps' transcripts separate).
        log_dir = set_artifact_dir() / "conformance" / "logs"
    except Exception:
        log_dir = None
    result = generate_gate_tool(
        base_temperature=TEMPERATURE,
        system_prompt=INTERACTION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        tool_schema=INTERACTION_TOOL_SCHEMA,
        model=settings.get_llm_model_id("conformance"),
        max_tokens=MAX_TOKENS,
        effort=settings.get_effort("conformance"),
        log_dir=log_dir,
    )

    cost = cost_from_result(result)
    logger.info(
        "Interaction API: %d in / %d out tokens, $%.4f",
        result["input_tokens"],
        result["output_tokens"],
        cost,
    )

    raw = result["result"] if isinstance(result.get("result"), dict) else {}
    analysis_text = raw.get("analysis") or ""
    raw_flags = raw.get("flags") or []

    logger.info("Analysis: %s", analysis_text[:200])
    logger.info("Flags found: %d", len(raw_flags))

    flags: list[InteractionFlag] = []
    for rf in raw_flags:
        if not isinstance(rf, dict):
            continue
        slot_id = (rf.get("enabler_slot_id") or "").strip()
        if not slot_id:
            logger.warning("Interaction flag missing enabler_slot_id — dropping: %r", rf)
            continue
        flag = InteractionFlag(
            enabler_slot_id=slot_id,
            reason=rf.get("reason") or "",
            replacement_constraint=rf.get("replacement_constraint") or "",
        )
        flags.append(flag)
        logger.info(
            "  enabler %s: %s | avoid: %s",
            flag.enabler_slot_id,
            flag.reason[:120],
            flag.replacement_constraint[:80],
        )

    return flags, analysis_text, cost
