"""Set-level interaction analysis — LLM-based degenerate combo detection.

Feeds the full card pool to an LLM and asks it to identify dangerous 2-3 card
interactions: infinite combos, degenerate loops, and unintended synergies that
break the format.

For each flagged interaction, the LLM identifies the "enabler" card — the one
whose design is the root cause. This feeds into the skeleton reviser to replace
enablers with fresh designs that avoid the problematic pattern.

Usage:
    from mtgai.analysis.interactions import analyze_interactions

    flags, issues = analyze_interactions(cards, mechanics)
"""

from __future__ import annotations

import logging
import re

from mtgai.analysis.models import AnalysisIssue, AnalysisSeverity, InteractionFlag
from mtgai.generation.llm_client import cost_from_result, generate_with_tool
from mtgai.models.card import Card

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-6"
EFFORT = None  # Sonnet doesn't support effort
TEMPERATURE = 0.3  # Low temp for analytical task
MAX_TOKENS = 8192

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
- Strong synergies that are intentional design (e.g., artifact payoffs with \
artifacts — that's the set's theme)
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
                        "cards_involved": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Names of the 2-3 cards involved",
                        },
                        "interaction_type": {
                            "type": "string",
                            "enum": [
                                "infinite_combo",
                                "degenerate_synergy",
                                "unintended_loop",
                            ],
                            "description": "Category of the interaction",
                        },
                        "description": {
                            "type": "string",
                            "description": (
                                "Step-by-step description of how the interaction works"
                            ),
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["WARN", "FAIL"],
                            "description": (
                                "FAIL for true infinite combos or game-breaking interactions. "
                                "WARN for degenerate but bounded synergies."
                            ),
                        },
                        "enabler_card": {
                            "type": "string",
                            "description": "Name of the card that is the root cause",
                        },
                        "enabler_slot_id": {
                            "type": "string",
                            "description": "Slot ID / collector number of the enabler",
                        },
                        "why_enabler": {
                            "type": "string",
                            "description": ("Why this card is the problem, not the other card(s)"),
                        },
                        "replacement_constraint": {
                            "type": "string",
                            "description": (
                                "What the replacement card should avoid to prevent "
                                "this interaction. Brief structural constraint only."
                            ),
                        },
                    },
                    "required": [
                        "cards_involved",
                        "interaction_type",
                        "description",
                        "severity",
                        "enabler_card",
                        "enabler_slot_id",
                        "why_enabler",
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
) -> tuple[list[InteractionFlag], list[AnalysisIssue]]:
    """Run LLM-based interaction analysis on the full card pool.

    Returns (interaction_flags, analysis_issues).
    """
    if not cards:
        return [], []

    user_prompt = _build_interaction_prompt(cards, mechanics)

    logger.info(
        "Interaction analysis: %d cards, prompt %d chars",
        len(cards),
        len(user_prompt),
    )

    result = generate_with_tool(
        system_prompt=INTERACTION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        tool_schema=INTERACTION_TOOL_SCHEMA,
        model=MODEL,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        effort=EFFORT,
    )

    cost = cost_from_result(result)
    logger.info(
        "Interaction API: %d in / %d out tokens, $%.4f",
        result["input_tokens"],
        result["output_tokens"],
        cost,
    )

    raw = result["result"]
    analysis_text = raw.get("analysis", "")
    raw_flags = raw.get("flags", [])

    logger.info("Analysis: %s", analysis_text[:200])
    logger.info("Flags found: %d", len(raw_flags))

    # Parse into structured models
    flags: list[InteractionFlag] = []
    issues: list[AnalysisIssue] = []

    for rf in raw_flags:
        flag = InteractionFlag(
            cards_involved=rf["cards_involved"],
            interaction_type=rf["interaction_type"],
            description=rf["description"],
            severity=rf["severity"],
            enabler_card=rf["enabler_card"],
            enabler_slot_id=rf["enabler_slot_id"],
            why_enabler=rf["why_enabler"],
            replacement_constraint=rf["replacement_constraint"],
        )
        flags.append(flag)

        severity = AnalysisSeverity.FAIL if rf["severity"] == "FAIL" else AnalysisSeverity.WARN

        issue = AnalysisIssue(
            check="interactions.degenerate_combo",
            severity=severity,
            slot_id=rf["enabler_slot_id"],
            card_name=rf["enabler_card"],
            message=(
                f"{rf['interaction_type']}: {', '.join(rf['cards_involved'])} — "
                f"{rf['description'][:120]}"
            ),
        )
        issues.append(issue)

        logger.info(
            "  [%s] %s: %s (enabler: %s @ %s)",
            rf["severity"],
            rf["interaction_type"],
            ", ".join(rf["cards_involved"]),
            rf["enabler_card"],
            rf["enabler_slot_id"],
        )

    return flags, issues
