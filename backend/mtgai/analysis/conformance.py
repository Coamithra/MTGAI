"""Conformance gate — LLM per-card adherence to its slot spec.

The first post-card_gen review gate (``plans/review-loop-stage-split.md``). One
whole-set LLM call pairs each generated card with its slot's relabeled spec
(``tweaked_text``, falling back to the default ``render_slot_string``) and asks
the model to judge adherence **holistically — no descriptor parser**. Per card:
color / type / rarity match, the slot's assigned mechanic, theme constraints and
``card_requests`` placed on the slot, and the relabeled design intent (signpost
archetype, cycle-member template, reserved-card request).

Skips basic lands + reprints. Runs first because it is the most objective gate,
the one most likely to flag a fresh set, and a bounce re-runs only ``card_gen``
(the cheapest span). Returns one :class:`ConformanceFinding` per non-conforming
card; the runner flags those for regeneration.

Usage:
    from mtgai.analysis.conformance import check_conformance

    findings, analysis_text, cost = check_conformance(cards, slots_by_id)
"""

from __future__ import annotations

import logging
import re

from mtgai.analysis.gate_common import filter_gate_cards
from mtgai.analysis.models import ConformanceFinding
from mtgai.generation.llm_client import cost_from_result, generate_with_tool
from mtgai.models.card import Card

logger = logging.getLogger(__name__)

TEMPERATURE = 0.2  # Low temp — objective adherence check
MAX_TOKENS = 8192


# ---------------------------------------------------------------------------
# Slot spec + card serialization
# ---------------------------------------------------------------------------


def slot_spec_text(slot: dict) -> str:
    """The one-line design spec a card must fulfil for its slot.

    Prefers the relabeled ``tweaked_text`` (what card-gen actually designed to);
    falls back to the default structured descriptor when a slot was never
    relabeled. Tolerant of slot dicts that don't reconstruct into a SkeletonSlot.
    """
    tweaked = (slot.get("tweaked_text") or "").strip()
    if tweaked:
        return tweaked
    try:
        from mtgai.skeleton.generator import render_slot_string

        return render_slot_string(slot)
    except Exception:
        # Last resort: stitch the obvious structured fields.
        bits = [slot.get("color"), slot.get("rarity"), slot.get("card_type")]
        return " · ".join(b for b in bits if b)


def _serialize_card(card: Card) -> str:
    """Printed card details, reminder text stripped, on one line."""
    name = card.name or "?"
    cost = card.mana_cost or ""
    tl = card.type_line
    rarity = card.rarity or "?"
    stats = ""
    if card.power is not None and card.toughness is not None:
        stats = f" [{card.power}/{card.toughness}]"
    elif card.loyalty is not None:
        stats = f" [Loyalty: {card.loyalty}]"
    oracle = card.oracle_text or ""
    oracle = re.sub(r"\([^)]{20,}\)", "", oracle).strip()
    oracle = re.sub(r"\n+", " / ", oracle)
    return f"{name} | {cost} | {tl}{stats} | {rarity} | {oracle}"


# ---------------------------------------------------------------------------
# Prompt + tool schema
# ---------------------------------------------------------------------------

CONFORMANCE_SYSTEM_PROMPT = """\
You are an expert Magic: The Gathering set developer running a conformance check. \
Each generated card was built to fill a specific design slot. You are given, per \
card, its printed details and the SLOT SPEC it was meant to fulfil.

Flag a card as NON-CONFORMING only when it clearly fails to fulfil its slot spec:
- Wrong color, card type, or rarity vs. what the slot calls for.
- Misses the slot's assigned/named mechanic when the spec names one.
- Ignores a theme constraint or a specific card request stated in the spec.
- Misses the relabeled design intent (e.g. the spec describes a signpost gold \
uncommon for an archetype, a cycle member following a shared template, or a \
named reserved card, and the card is unrelated).

Judge holistically. Minor wording or flavor differences are fine — only flag a \
real, structural deviation a regeneration should fix. A card that fulfils its \
spec in spirit conforms. Do NOT fabricate problems: every false positive wastes \
a regeneration cycle. If every card conforms, return an empty list."""

CONFORMANCE_TOOL_SCHEMA = {
    "name": "report_conformance",
    "description": "Report cards that do not conform to their assigned slot spec",
    "input_schema": {
        "type": "object",
        "properties": {
            "analysis": {
                "type": "string",
                "description": "Brief overall assessment of how well the set conforms to plan.",
            },
            "nonconforming": {
                "type": "array",
                "description": "Cards that fail their slot spec. Empty if all conform.",
                "items": {
                    "type": "object",
                    "properties": {
                        "slot_id": {
                            "type": "string",
                            "description": "Slot ID of the non-conforming card (as labeled).",
                        },
                        "reason": {
                            "type": "string",
                            "description": "One line: what the slot wants vs. what the card is.",
                        },
                    },
                    "required": ["slot_id", "reason"],
                },
            },
        },
        "required": ["analysis", "nonconforming"],
    },
}


def _build_prompt(pairs: list[tuple[str, Card, str]]) -> str:
    """Build the user prompt — one block per (slot_id, card, spec)."""
    lines: list[str] = [f"## Cards vs. their slot specs ({len(pairs)} cards)\n"]
    for slot_id, card, spec in pairs:
        lines.append(f"--SLOT {slot_id}--")
        lines.append(f"  CARD: {_serialize_card(card)}")
        lines.append(f"  SPEC: {spec}")
        lines.append("")
    lines.append(
        "## Task\n\nFor each card, decide whether it fulfils its SLOT SPEC. "
        "Report only the slot_ids that clearly do not, with a one-line reason. "
        "Return an empty list if the set conforms."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def check_conformance(
    cards: list[Card],
    slots_by_id: dict[str, dict],
) -> tuple[list[ConformanceFinding], str, float]:
    """Check each card against its slot spec via one whole-set LLM call.

    Skips basic lands + reprints, and any card whose slot has no resolvable
    spec. Returns ``(findings, analysis_text, cost_usd)``.
    """
    pairs: list[tuple[str, Card, str]] = []
    by_slot: dict[str, Card] = {}
    for card in filter_gate_cards(cards):
        if not card.slot_id:
            continue
        spec = slot_spec_text(slots_by_id.get(card.slot_id, {}))
        if not spec:
            continue
        pairs.append((card.slot_id, card, spec))
        by_slot[card.slot_id] = card

    if not pairs:
        return [], "", 0.0

    user_prompt = _build_prompt(pairs)
    logger.info("Conformance check: %d cards, prompt %d chars", len(pairs), len(user_prompt))

    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    settings = require_active_project().settings
    try:
        log_dir = set_artifact_dir() / "conformance" / "logs"
    except Exception:
        log_dir = None
    result = generate_with_tool(
        system_prompt=CONFORMANCE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        tool_schema=CONFORMANCE_TOOL_SCHEMA,
        model=settings.get_llm_model_id("conformance"),
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        effort=settings.get_effort("conformance"),
        log_dir=log_dir,
    )

    cost = cost_from_result(result)
    raw = result["result"] if isinstance(result.get("result"), dict) else {}
    analysis_text = raw.get("analysis") or ""
    raw_items = raw.get("nonconforming") or []
    logger.info(
        "Conformance API: %d in / %d out tokens, $%.4f — %d flagged",
        result["input_tokens"],
        result["output_tokens"],
        cost,
        len(raw_items),
    )

    findings: list[ConformanceFinding] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        slot_id = (item.get("slot_id") or "").strip()
        # Only trust a flag that names a real, in-scope slot — local models
        # occasionally hallucinate slot ids or omit them entirely.
        if not slot_id or slot_id not in by_slot or slot_id in seen:
            if slot_id and slot_id not in by_slot:
                logger.warning("Conformance flag for unknown slot %s — dropping", slot_id)
            continue
        seen.add(slot_id)
        findings.append(
            ConformanceFinding(
                slot_id=slot_id,
                card_name=by_slot[slot_id].name,
                reason=(item.get("reason") or "Does not match slot spec.").strip(),
            )
        )
        logger.info("  conformance: %s — %s", slot_id, findings[-1].reason)

    return findings, analysis_text, cost
