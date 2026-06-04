"""Set-level interaction analysis — LLM-based degenerate combo detection.

The whole-pool interaction step of the merged ``conformance`` gate (displayed
"Conformance & Interactions"). Finds dangerous 2-3 card interactions: infinite
combos, degenerate loops, and unintended synergies that break a limited format.

**Batched, flag-only, streamed** — the same shape as the conformance step (see
``conformance.py`` + ``gate_common.stream_flag_batch``). The pool is grouped into
batches of ``BATCH_SIZE`` *new* cards; each batch is one streamed call that shows
the model the cards reviewed so far as **existing context** plus the batch's new
cards, and asks it to flag every degenerate interaction the new cards create with
the existing cards or with each other. This way each ordered pair ``(a, b)`` is
checked exactly once — in the batch where ``b`` is new and ``a`` is already
existing context — so coverage is complete with O(batches) streamed calls instead
of one giant whole-pool call (which a local model scans poorly and which truncates
on a large flag list). The growing existing-context prefix is the price of full
cross-batch coverage.

For each flagged interaction the model names the **enabler** — the single card
(new OR existing) whose design is the root cause — via a ``--CARD <slot_id>--``
block whose body carries the diagnosis and an ``AVOID:`` line (the replacement
constraint). The runner (:func:`mtgai.pipeline.stages.run_conformance`) flags that
enabler card for regeneration, threading the constraint into its ``regen_reason``.

Each new card streams a per-card interaction verdict (✓ checked-clean / ✗ flagged
enabler) so the tab can show a second checkbox per card beside the conformance one.

Usage:
    from mtgai.analysis.interactions import analyze_interactions

    flags, analysis_text, cost = analyze_interactions(cards, mechanics)
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

from mtgai.analysis import gate_common
from mtgai.analysis.gate_common import filter_gate_cards
from mtgai.analysis.models import InteractionFlag
from mtgai.generation import temperatures as temps
from mtgai.generation.token_budgets import STANDARD
from mtgai.models.card import Card

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Model + effort come from per-set model_settings at runtime.
TEMPERATURE = temps.ANALYTICAL  # analytical scan (see temperatures.py)
# Flag-only output is short; a large ceiling is just truncation insurance.
MAX_TOKENS = STANDARD
# New cards checked per streamed call (existing cards ride along as context).
BATCH_SIZE = 40

# An ``AVOID: <constraint>`` line inside a flagged block — the replacement
# constraint the regenerated enabler must satisfy. Case-insensitive.
_AVOID_RE = re.compile(r"^\s*AVOID\s*:\s*(.+)$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Card serialization — full oracle text, no truncation
# ---------------------------------------------------------------------------


def _card_id(card: Card) -> str:
    """The id used in the listing + enabler references — slot id, else number."""
    return card.slot_id or card.collector_number or "?"


def _serialize_card_full(card: Card) -> str:
    """Full card text for interaction analysis — no truncation."""
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

    return f"{_card_id(card)} | {name} | {cost} | {tl}{stats} | {rarity} | {oracle}"


def _serialize_cards(cards: list[Card]) -> str:
    return "\n".join(_serialize_card_full(c) for c in cards)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

INTERACTION_SYSTEM_PROMPT = """\
You are an expert Magic: The Gathering developer specializing in play design and \
format health. You are reviewing a set in batches. You are given the EXISTING \
cards of the set (already reviewed) and a batch of NEW cards. Find degenerate \
card interactions that each NEW card creates — with the existing cards or with \
the other new cards — that would be problematic in a limited (draft/sealed) format.

You are looking for:
1. **Infinite combos** — two or three cards that create an unbounded loop \
(infinite damage, infinite tokens, infinite life, infinite mana, etc.)
2. **Degenerate synergies** — two cards that together produce an effect far \
beyond what either card's rarity and mana cost should allow.
3. **Unintended loops** — cards that trigger each other repeatedly without \
a natural stopping point.

You are NOT looking for:
- Strong synergies that are intentional design (a payoff card rewarding the \
mechanic, card type, or archetype it is built around is the set working as \
intended, not a degenerate interaction).
- Cards that are individually strong but don't create problematic interactions.
- Three-card combos that require very specific board states (too unlikely in limited).
- Color-pair synergies that only work if you draft both colors (that's normal).

For each problematic interaction, identify the **enabler** — the single card \
whose design is the root cause and should be regenerated. It is typically the \
card that provides an undercosted or unrestricted effect (free untap, cost \
reduction, repeated recursion); the other card(s) are usually fine on their own. \
The enabler may be a NEW card or an EXISTING one.

Do NOT fabricate problems — false positives waste design time.

## Output format

For each degenerate interaction you find, emit a block — and ONLY for real problems:

--CARD <enabler_slot_id>--
<one line: which cards combo and step-by-step how the degenerate interaction \
works; name the other card(s) involved>
AVOID: <a brief structural constraint the regenerated enabler must satisfy, e.g. \
"no free untap of a creature" — not a restatement of the problem>

Use the id shown at the start of the enabler's line (the value before the first \
``|``). If a new card creates no degenerate interaction, output nothing for it. \
If the whole batch is clean, output nothing at all. Write no preamble, summary, \
or commentary — emit only ``--CARD`` blocks."""


def _build_batch_prompt(existing: list[Card], new: list[Card], mechanics: list[dict]) -> str:
    """Build the user prompt: existing context + the new cards to check."""
    sections: list[str] = []
    if existing:
        sections.append(
            f"## Existing cards ({len(existing)})\n\n```\n{_serialize_cards(existing)}\n```"
        )
    else:
        sections.append("## Existing cards\n\nNone yet — this is the first batch.")

    if mechanics:
        mech_lines = [f"- **{m['name']}**: {m.get('reminder_text', '')}" for m in mechanics]
        sections.append("## Custom Mechanics\n\n" + "\n".join(mech_lines))

    sections.append(f"## New cards to check ({len(new)})\n\n```\n{_serialize_cards(new)}\n```")

    sections.append(
        "## Task\n\n"
        "Check EACH new card for degenerate interactions with the existing cards "
        "and with the other new cards. Emit a `--CARD <enabler_slot_id>--` block "
        "(naming the enabler) for each problem; emit nothing for clean cards.\n\n"
        "Remember: this is a limited format (draft/sealed). Players open ~45 cards "
        "and build 40-card decks. Two-card combos at common are much more likely "
        "than three-card combos at rare. Weight severity accordingly."
    )
    return "\n\n---\n\n".join(sections)


def _parse_interaction_block(block: str) -> tuple[str, str]:
    """Split a flagged block into ``(reason, replacement_constraint)``.

    The reason is every non-empty line except the ``AVOID:`` line (joined); the
    constraint is the first ``AVOID:`` line's content. Either may be empty.
    """
    reason_lines: list[str] = []
    constraint = ""
    for line in block.splitlines():
        s = line.strip()
        if not s:
            continue
        m = _AVOID_RE.match(s)
        if m and not constraint:
            constraint = m.group(1).strip()
            continue
        reason_lines.append(s)
    reason = " ".join(reason_lines).strip() or "Degenerate interaction."
    return reason, constraint


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def analyze_interactions(
    cards: list[Card],
    mechanics: list[dict],
    *,
    on_start: Callable[[list[dict]], None] | None = None,
    on_card: Callable[[dict], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[list[InteractionFlag], str, float]:
    """Scan the pool for degenerate interactions, one streamed batch at a time.

    Skips basic lands + reprints. Returns ``(flags, analysis_text, cost_usd)``;
    each flag names an enabler card (by ``enabler_slot_id``) the runner will flag
    for regeneration.

    Hooks (all optional) drive the live per-card interaction checklist (the second
    checkbox per card in the tab):

    * ``on_start(card_list)`` — fired once with ``[{slot_id, card_name}, ...]`` for
      every card in scope, so the tab seeds the interaction column up front.
    * ``on_card(record)`` — fired once per card as its batch resolves, with
      ``{slot_id, card_name, interacts, reason}``: ``interacts`` is ``False`` for a
      flagged enabler, ``True`` for a checked-clean new card, ``None`` when its
      batch truncated. A clean new card may later flip to ``False`` if a *later*
      batch flags it as an enabler against newer cards.
    * ``on_progress(message)`` — ``"batch N/M"`` for the progress strip.
    * ``should_cancel()`` — polled before each batch so Cancel halts between batches.
    """
    gate_cards = filter_gate_cards(cards)
    if not gate_cards:
        return [], "", 0.0

    valid_ids = {_card_id(c) for c in gate_cards}
    name_by = {_card_id(c): c.name for c in gate_cards}

    if on_start is not None:
        on_start([{"slot_id": _card_id(c), "card_name": c.name} for c in gate_cards])

    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    settings = require_active_project().settings
    try:
        # Shares the merged gate's log dir; distinct convo names keep the two
        # steps' transcripts separate.
        log_dir = set_artifact_dir() / "conformance" / "logs"
    except Exception:
        log_dir = None
    model = settings.get_llm_model_id("conformance")

    batches = [gate_cards[i : i + BATCH_SIZE] for i in range(0, len(gate_cards), BATCH_SIZE)]
    logger.info(
        "Interaction analysis: %d cards in %d batch(es) of up to %d new cards",
        len(gate_cards),
        len(batches),
        BATCH_SIZE,
    )

    flags: dict[str, tuple[str, str]] = {}  # enabler slot_id -> (reason, constraint)
    total_cost = 0.0

    def _fire_inter(slot_id: str, interacts: bool | None, reason: str) -> None:
        if on_card is None:
            return
        on_card(
            {
                "slot_id": slot_id,
                "card_name": name_by.get(slot_id, ""),
                "interacts": interacts,
                "reason": reason,
            }
        )

    def _on_block(slot_id: str, block: str) -> None:
        if slot_id in flags:  # an enabler already flagged in an earlier batch
            return
        reason, constraint = _parse_interaction_block(block)
        flags[slot_id] = (reason, constraint)
        _fire_inter(slot_id, False, reason)

    for bi, new_batch in enumerate(batches, 1):
        if should_cancel is not None and should_cancel():
            logger.warning("Interactions cancelled after %d/%d batches", bi - 1, len(batches))
            break
        if on_progress is not None:
            on_progress(f"Scanning interactions — batch {bi}/{len(batches)}")
        existing = gate_cards[: (bi - 1) * BATCH_SIZE]
        completed, cost = gate_common.stream_flag_batch(
            system_prompt=INTERACTION_SYSTEM_PROMPT,
            user_prompt=_build_batch_prompt(existing, new_batch, mechanics),
            model=model,
            base_temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            log_dir=log_dir,
            name="report_interactions",
            valid_ids=valid_ids,  # an enabler may be an existing card
            on_block=_on_block,
        )
        total_cost += cost
        # Every new card not flagged as an enabler is interaction-checked: ✓ on a
        # clean finish, unknown if the batch kept truncating past it.
        verdict = True if completed else None
        for card in new_batch:
            cid = _card_id(card)
            if cid not in flags:
                _fire_inter(cid, verdict, "")

    flags_out = [
        InteractionFlag(enabler_slot_id=sid, reason=reason, replacement_constraint=constraint)
        for sid, (reason, constraint) in flags.items()
    ]
    for f in flags_out:
        logger.info(
            "  enabler %s: %s | avoid: %s",
            f.enabler_slot_id,
            f.reason[:120],
            f.replacement_constraint[:80],
        )

    analysis = (
        f"{len(flags_out)} degenerate interaction(s) flagged."
        if flags_out
        else "No degenerate interactions found."
    )
    logger.info("Interactions: %d flagged, $%.4f", len(flags_out), total_cost)
    return flags_out, analysis, total_cost
