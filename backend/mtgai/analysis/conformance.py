"""Conformance gate — LLM per-card adherence to its slot spec.

The first post-card_gen review gate. Unlike the interaction check (which needs
the whole pool in one prompt to spot cross-card combos), conformance is a purely
**per-card** judgement, so it runs **one LLM call per card**: a single prompt,
repeated for each generated card paired with its slot's relabeled spec
(``tweaked_text``, falling back to the default ``render_slot_string``). The model
judges adherence **holistically — no descriptor parser** — and returns a simple
``conforms`` verdict + one-line reason per card.

Running card-by-card lets the tab fill in a live checklist (one ✓/✗ per card as
it's evaluated, via the ``on_start`` / ``on_card`` hooks) and keeps each call
small + focused (less local-model truncation than one giant whole-set call). A
single card whose call errors is marked *unknown* (not flagged) and the gate
keeps going, so one bad response can't tank the whole check.

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
from collections.abc import Callable

from mtgai.analysis.gate_common import filter_gate_cards, generate_gate_tool
from mtgai.analysis.models import ConformanceFinding
from mtgai.generation import temperatures as temps
from mtgai.generation.llm_client import cost_from_result
from mtgai.generation.token_budgets import COMPACT
from mtgai.models.card import Card

logger = logging.getLogger(__name__)

TEMPERATURE = temps.PRECISE  # objective adherence check (see temperatures.py)
MAX_TOKENS = COMPACT  # One card per call: a tiny verdict + room for a short CoT


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
    # Surface the precomputed CMC beside the cost so the gate can judge a
    # "mana cost way off" deviation without doing pip arithmetic on the cost
    # string itself (local models miscount {2}{U}{R} etc.).
    if card.cmc is not None:
        cmc = int(card.cmc) if float(card.cmc).is_integer() else card.cmc
        cost = f"{cost} (CMC {cmc})".strip()
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
The card below was built to fill a specific design slot. You are given its \
printed details and the SLOT SPEC it was meant to fulfil.

Decide whether the card CONFORMS to its slot spec. A card does NOT conform when \
it clearly fails the spec:
- Wrong color, card type, or rarity vs. what the slot calls for.
- Misses the slot's assigned/named mechanic when the spec names one.
- Mana cost is way off: the card's converted mana cost (shown as "CMC N" beside \
the mana cost) is far from the cost the slot spec calls for — a gap of roughly 2 \
or more. Read the spec's stated cost or power tier as the target; flag only a \
clear, large mismatch. If the spec gives no sense of cost, do not flag on this basis.
- Ignores a theme constraint or a specific card request stated in the spec.
- Misses the relabeled design intent (e.g. the spec describes a signpost gold \
uncommon for an archetype, a cycle member following a shared template, or a \
named reserved card, and the card is unrelated).

Judge holistically. Minor wording or flavor differences are fine — a card that \
fulfils its spec in spirit conforms. Do NOT fabricate problems: a false \
non-conformance wastes a regeneration cycle. Set ``conforms`` true when the card \
fulfils its slot; set it false only for a real, structural deviation, and give a \
one-line reason naming what the slot wants vs. what the card is."""

CONFORMANCE_TOOL_SCHEMA = {
    "name": "report_card_conformance",
    "description": "Report whether one card conforms to its assigned slot spec",
    "input_schema": {
        "type": "object",
        "properties": {
            "conforms": {
                "type": "boolean",
                "description": "True if the card fulfils its slot spec.",
            },
            "reason": {
                "type": "string",
                "description": (
                    "One line: when the card does NOT conform, what the slot wants "
                    "vs. what the card is. Empty when it conforms."
                ),
            },
        },
        "required": ["conforms", "reason"],
    },
}


def _build_card_prompt(slot_id: str, card: Card, spec: str) -> str:
    """Build the user prompt for a single card vs. its slot spec."""
    return (
        "## Card vs. its slot spec\n\n"
        f"--SLOT {slot_id}--\n"
        f"  CARD: {_serialize_card(card)}\n"
        f"  SPEC: {spec}\n\n"
        "## Task\n\nDecide whether this card fulfils its SLOT SPEC. Set "
        "conforms=true if it does; otherwise conforms=false with a one-line reason."
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def check_conformance(
    cards: list[Card],
    slots_by_id: dict[str, dict],
    *,
    pre_flagged: dict[str, str] | None = None,
    on_start: Callable[[list[dict]], None] | None = None,
    on_card: Callable[[dict], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[list[ConformanceFinding], str, float]:
    """Check each card against its slot spec with one LLM call per card.

    Skips basic lands + reprints, and any card whose slot has no resolvable
    spec. Returns ``(findings, analysis_text, cost_usd)`` where ``findings``
    is one :class:`ConformanceFinding` per non-conforming card.

    ``pre_flagged`` (``{slot_id: reason}``) folds an upstream verdict — the
    algorithmic functional-duplicate scan — into this per-card checklist: a
    pre-flagged card is seeded non-conforming (an X in the tab from the first
    paint), its per-card LLM call is skipped (it will be regenerated anyway), and
    it is returned as a finding carrying the given reason. Such a card is kept
    even when its slot has no resolvable spec, so a duplicate is never dropped.

    Hooks (all optional) drive the live tab checklist:

    * ``on_start(card_list)`` — fired once with ``[{slot_id, card_name}, ...]``
      for every card about to be checked, so the tab can render the full list
      up front in a pending state.
    * ``on_card(record)`` — fired after each card with
      ``{slot_id, card_name, conforms, reason}``; ``conforms`` is ``None`` when
      the card's check errored (shown as unknown, never flagged).
    * ``should_cancel()`` — polled before each card so the Cancel button halts
      the loop between cards (an in-flight call is killed by the lock cancel).
    """
    pre_flagged = pre_flagged or {}
    pairs: list[tuple[str, Card, str]] = []
    for card in filter_gate_cards(cards):
        if not card.slot_id:
            continue
        if card.slot_id in pre_flagged:
            # Pre-flagged (duplicate) — keep it in the checklist even without a
            # spec; its spec is never read (the LLM call is skipped below).
            pairs.append((card.slot_id, card, ""))
            continue
        spec = slot_spec_text(slots_by_id.get(card.slot_id, {}))
        if not spec:
            continue
        pairs.append((card.slot_id, card, spec))

    if not pairs:
        return [], "", 0.0

    if on_start is not None:
        start_list: list[dict] = []
        for sid, card, _ in pairs:
            entry: dict = {"slot_id": sid, "card_name": card.name}
            if sid in pre_flagged:
                # Seed the duplicate as a failed (X) row from the very first paint.
                entry["conforms"] = False
                entry["reason"] = pre_flagged[sid]
            start_list.append(entry)
        on_start(start_list)

    logger.info("Conformance check: %d cards, one LLM call each", len(pairs))

    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    settings = require_active_project().settings
    try:
        log_dir = set_artifact_dir() / "conformance" / "logs"
    except Exception:
        log_dir = None
    model = settings.get_llm_model_id("conformance")
    effort = settings.get_effort("conformance")

    findings: list[ConformanceFinding] = []
    total_cost = 0.0
    passed = 0
    pre_flagged_seen = 0
    for idx, (slot_id, card, spec) in enumerate(pairs, 1):
        if should_cancel is not None and should_cancel():
            logger.warning("Conformance cancelled after %d/%d cards", idx - 1, len(pairs))
            break

        if slot_id in pre_flagged:
            # Duplicate flagged upstream — already an X; skip the LLM call and
            # record it (with the duplicate reason) as non-conforming. It never
            # ran the conformance check, so it's excluded from the summary
            # denominator (a duplicate finding, not a conformance failure).
            pre_flagged_seen += 1
            reason = pre_flagged[slot_id]
            findings.append(ConformanceFinding(slot_id=slot_id, card_name=card.name, reason=reason))
            if on_card is not None:
                on_card(
                    {
                        "slot_id": slot_id,
                        "card_name": card.name,
                        "conforms": False,
                        "reason": reason,
                    }
                )
            continue

        user_prompt = _build_card_prompt(slot_id, card, spec)
        try:
            result = generate_gate_tool(
                base_temperature=TEMPERATURE,
                system_prompt=CONFORMANCE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                tool_schema=CONFORMANCE_TOOL_SCHEMA,
                model=model,
                max_tokens=MAX_TOKENS,
                effort=effort,
                log_dir=log_dir,
            )
        except Exception as exc:
            # One card's check failing (persistent truncation, etc.) must not
            # tank the gate after evaluating the rest. Mark it unknown (not
            # flagged), surface it on the tab, and keep going.
            logger.warning("Conformance check failed for %s (%s): %s", slot_id, card.name, exc)
            if on_card is not None:
                on_card(
                    {
                        "slot_id": slot_id,
                        "card_name": card.name,
                        "conforms": None,
                        "reason": f"check failed: {exc}",
                    }
                )
            continue

        total_cost += cost_from_result(result)
        raw = result["result"] if isinstance(result.get("result"), dict) else {}
        conforms = bool(raw.get("conforms"))
        reason = (raw.get("reason") or "").strip()
        if conforms:
            passed += 1
            reason = ""
        else:
            reason = reason or "Does not match slot spec."
            findings.append(ConformanceFinding(slot_id=slot_id, card_name=card.name, reason=reason))
            logger.info("  conformance [%d/%d]: %s — %s", idx, len(pairs), slot_id, reason)
        if on_card is not None:
            on_card(
                {
                    "slot_id": slot_id,
                    "card_name": card.name,
                    "conforms": conforms,
                    "reason": reason,
                }
            )

    # Pre-flagged duplicates skip the LLM check entirely — they're duplicate
    # findings, not conformance failures — so drop them from the denominator
    # rather than counting them against the conformance rate.
    checked = len(pairs) - pre_flagged_seen
    analysis = f"{passed}/{checked} cards conform."
    logger.info(
        "Conformance: %d/%d conform, %d flagged, $%.4f",
        passed,
        checked,
        len(findings),
        total_cost,
    )
    return findings, analysis, total_cost
