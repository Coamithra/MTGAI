"""Finalize sanity gate — a light LLM "is this even a valid card?" pass.

The terminal check inside the ``finalize`` stage. The validators auto-fix what
they can and surface the rest as MANUAL errors, but nothing hard-blocks a card the
local model emitted broken-but-unfixable — a creature with no power/toughness, a
garbled run-on oracle line, a bogus mana symbol — from flowing on to art and
render and printing with a blank P/T box. This gate is that hard block: an LLM
gives every card one quick sanity look and the caller soft-excludes anything it
flags (nondestructive + reversible; see ``review/finalize.py`` for the 5% cap).

**Batched, flag-only, streamed** — the exact shape of the conformance gate
(:mod:`mtgai.analysis.conformance`), reusing :func:`gate_common.stream_flag_batch`
so it inherits the local-model robustness (temp-floor off the near-greedy loop,
DRY-sampler retry on truncation, an unreached tail left "unknown / never flagged"
rather than silently passed). The pool is grouped into batches of ``BATCH_SIZE``;
each batch is one streamed call where the model emits a ``--CARD <id>--`` block
**only for a card with an obvious defect**. A clean card produces no output.

Unlike the conformance gate this keys by ``collector_number`` (the id the
Finalization tab marks + the field the exclusion is stamped onto), not ``slot_id``,
and it is **theme-free / spec-free** — it judges the card on its own, not against
a slot. It is explicitly NOT a balance or design-taste check: a legal-but-weak
card is fine; a false flag soft-removes a good card.

Usage:
    from mtgai.review.sanity_check import check_sanity

    flagged, analysis, cost = check_sanity(cards)
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

from mtgai.analysis import gate_common
from mtgai.analysis.gate_common import filter_gate_cards
from mtgai.generation import temperatures as temps
from mtgai.generation.token_budgets import HEAVY
from mtgai.models.card import Card

logger = logging.getLogger(__name__)

TEMPERATURE = temps.PRECISE  # objective defect check (floored for local models)
# Flag-only output is short (one terse block per *broken* card), so a large
# ceiling is just truncation insurance — the model almost never approaches it.
MAX_TOKENS = HEAVY
# Cards per streamed call. Kept small (20) so each batch's reasoning space stays
# tractable and the local model terminates instead of looping — same value and
# rationale as the conformance gate.
BATCH_SIZE = 20


# ---------------------------------------------------------------------------
# Card serialization
# ---------------------------------------------------------------------------


def _serialize_card(card: Card) -> str:
    """Printed card details, reminder text stripped, on one line.

    Stats are shown only when present — a creature/vehicle whose ``Creature`` (or
    ``Vehicle``) type line carries no ``[P/T …]`` is exactly the missing-P/T defect
    the gate should catch, so the absence is left visible rather than papered over.
    """
    name = card.name or "?"
    cost = card.mana_cost or "(no cost)"
    tl = card.type_line or "(no type line)"
    rarity = card.rarity or "?"
    stats = ""
    if card.power is not None and card.toughness is not None:
        stats = f" [P/T {card.power}/{card.toughness}]"
    elif card.loyalty is not None:
        stats = f" [Loyalty: {card.loyalty}]"
    oracle = card.oracle_text or ""
    oracle = re.sub(r"\([^)]{20,}\)", "", oracle).strip()
    oracle = re.sub(r"\n+", " / ", oracle)
    return f"{name} | {cost} | {tl}{stats} | {rarity} | {oracle}"


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SANITY_SYSTEM_PROMPT = """\
You are an expert Magic: The Gathering editor doing a quick, final SANITY CHECK \
on a batch of finished cards. You are NOT judging power level, balance, design \
quality, or flavor — only whether each card is a structurally valid, sensible \
Magic card.

Flag a card ONLY when it has an obvious, objective defect such as:
- A creature or Vehicle with no power/toughness (the listing shows no "[P/T x/y]").
- A planeswalker with no loyalty.
- Garbled, truncated, nonsensical, or repeated/looping rules text.
- A nonexistent or malformed mana symbol or broken templating (stray braces, \
half-written tokens, machine artifacts, leftover prompt text).
- A clearly broken card: empty/placeholder name, a type line that is not a real \
Magic type, mana cost that is gibberish.

Do NOT flag a card just because it is simple, weak, oddly costed, or unusual — a \
legal-but-unexciting card PASSES. When in doubt, do NOT flag: a false flag removes \
a good card from the set.

## Output format

Go through the cards IN THE ORDER LISTED. For EACH card with an obvious defect, \
emit a block — and ONLY for broken cards:

--CARD <id>--
<one short line naming the defect>

Use the id shown in the listing (the value after ``--CARD-ID``). Output NOTHING \
for a card that is fine — skip it silently. Do NOT emit a ``--CARD`` block to say \
a card is fine or valid; a block means the card has a defect. If every card in \
the batch is fine, output nothing at all. No preamble, summary, or commentary; \
emit only ``--CARD`` blocks for the cards you are flagging."""


# A drifting local model sometimes ignores the flag-only contract and emits a
# ``--CARD`` block for a CLEAN card too (body "No defects." / "Looks fine."). Here
# a false flag soft-removes a good card from print, so the parser guard matters
# even more than in the conformance gate. ``_is_sanity_flag`` drops a block only
# when its body OPENS with an unambiguous all-clear verdict — a real defect reason
# ("Creature with no power/toughness", "Garbled rules text", "No loyalty on
# planeswalker") never starts with one, and the ``no <X>`` opener is restricted to
# defect-nouns so "no power"/"no loyalty" stay genuine flags.
_SANITY_CLEAN_RE = re.compile(
    r"^(?:none|n/?a|fine|ok(?:ay)?|valid|legal|clean|all\s+clear|nothing(?:\s+wrong)?"
    r"|no\s+(?:defects?|issues?|problems?|errors?|concerns?)"
    r"|looks?\s+(?:fine|ok(?:ay)?|valid|good)|is\s+(?:fine|ok(?:ay)?|valid))\b",
    re.IGNORECASE,
)


def _is_sanity_flag(block: str) -> bool:
    """True when a ``--CARD`` block is a genuine sanity-defect flag.

    Returns False (drop) only when the body opens with an unambiguous all-clear
    verdict, so a real defect reason is never newly dropped — the worst case is a
    verbose all-clear note left as a flag (the pre-fix behaviour), not a card
    wrongly kept in print.
    """
    body = " ".join(block.split())
    if not body:
        return True  # bare flag — honour it (parse defaults the reason)
    return not _SANITY_CLEAN_RE.match(body)


def _build_batch_prompt(batch: list[tuple[str, Card]]) -> str:
    """Build the user prompt listing every card in the batch with its id."""
    lines: list[str] = ["## Cards to sanity-check\n"]
    for cn, card in batch:
        lines.append(f"--CARD-ID {cn}--")
        lines.append(f"  {_serialize_card(card)}")
    lines.append(
        "\n## Task\n\nFor each card above with an obvious structural defect, emit a "
        "`--CARD <id>--` block naming the defect. Emit nothing for cards that are fine."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-batch streamed check
# ---------------------------------------------------------------------------


def _check_batch(
    batch: list[tuple[str, Card]],
    *,
    model: str,
    log_dir,
    on_card: Callable[[dict], None] | None,
    thinking: str | None = None,
) -> tuple[dict[str, str], set[str], list[str], float]:
    """Stream-check one batch. Returns ``(flagged, resolved, unknown, cost)``.

    * ``flagged`` — ``{collector_number: reason}`` for the cards the model flagged.
    * ``resolved`` — collector numbers that got a real verdict (ok or flagged).
    * ``unknown`` — collector numbers left undecided (persistent truncation tail).
    * ``cost`` — summed USD across attempts.

    Fires ``on_card`` once per card the moment it is decided: a flag block streams
    in ✗ (advancing an approved frontier — every earlier not-yet-flagged card flips
    to ✓ ``ok=True``), then ✓ for the rest when the call returns clean. A batch that
    keeps truncating reports its unreached tail ``ok=None`` (unknown, never flagged).
    """
    order = [cn for cn, _ in batch]
    valid_ids = set(order)
    pos = {cn: i for i, cn in enumerate(order)}
    name_by = {cn: card.name for cn, card in batch}

    flagged: dict[str, str] = {}
    resolved: set[str] = set()
    frontier = 0

    def _fire(cn: str, ok: bool | None, reason: str) -> None:
        if on_card is None:
            return
        on_card(
            {
                "collector_number": cn,
                "card_name": name_by.get(cn, ""),
                "ok": ok,
                "reason": reason,
            }
        )

    def _approve_through(p: int) -> None:
        """Mark every not-yet-resolved card at listing position < ``p`` as OK."""
        nonlocal frontier
        for i in range(frontier, p):
            cn = order[i]
            if cn not in resolved and cn not in flagged:
                resolved.add(cn)
                _fire(cn, True, "")
        frontier = max(frontier, p)

    def _on_block(cn: str, block: str) -> None:
        reason = gate_common.first_line(block) or "Failed sanity check."
        _approve_through(pos[cn])
        first = cn not in flagged
        flagged[cn] = reason
        resolved.add(cn)
        if first:
            _fire(cn, False, reason)

    completed, cost = gate_common.stream_flag_batch(
        system_prompt=SANITY_SYSTEM_PROMPT,
        user_prompt=_build_batch_prompt(batch),
        model=model,
        base_temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        log_dir=log_dir,
        name="check_sanity",
        valid_ids=valid_ids,
        on_block=_on_block,
        is_flag_block=_is_sanity_flag,
        thinking=thinking,
    )

    if completed:
        _approve_through(len(order))
        return flagged, resolved, [], cost

    unknown = [cn for cn in order if cn not in resolved]
    for cn in unknown:
        _fire(cn, None, "check failed: response truncated")
    return flagged, resolved, unknown, cost


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def check_sanity(
    cards: list[Card],
    *,
    on_start: Callable[[list[dict]], None] | None = None,
    on_card: Callable[[dict], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[dict[str, str], str, float]:
    """Sanity-check every card with one streamed call per batch.

    Skips basic lands + reprints (:func:`gate_common.filter_gate_cards`) and any
    card with no ``collector_number``. Returns ``(flagged, analysis_text, cost)``
    where ``flagged`` is ``{collector_number: reason}`` for each card with an
    obvious defect; the caller applies the 5% cap and the exclusion marking.

    Hooks (all optional) drive the live Finalization-tab checklist:

    * ``on_start(card_list)`` — fired once with ``[{collector_number, card_name},
      ...]`` for every card about to be checked, so the tab can render the list up
      front in a pending state.
    * ``on_card(record)`` — fired once per card as decided, with
      ``{collector_number, card_name, ok, reason}``; ``ok`` is ``None`` when the
      card's batch truncated past it (shown unknown, never flagged).
    * ``on_progress(message)`` — fired before each batch (``"batch N/M"``).
    * ``should_cancel()`` — polled before each batch so Cancel halts the loop.
    """
    pairs: list[tuple[str, Card]] = []
    for card in filter_gate_cards(cards):
        if not card.collector_number:
            continue
        pairs.append((card.collector_number, card))

    if not pairs:
        return {}, "", 0.0

    if on_start is not None:
        on_start([{"collector_number": cn, "card_name": card.name} for cn, card in pairs])

    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    settings = require_active_project().settings
    try:
        log_dir = set_artifact_dir() / "finalize" / "logs"
    except Exception:
        log_dir = None
    model = settings.get_llm_model_id("finalize")
    thinking = settings.get_thinking("finalize")

    flagged: dict[str, str] = {}
    total_cost = 0.0
    passed = 0
    unknown_total = 0

    batches = [pairs[i : i + BATCH_SIZE] for i in range(0, len(pairs), BATCH_SIZE)]
    logger.info(
        "Sanity check: %d card(s) in %d batch(es) of up to %d",
        len(pairs),
        len(batches),
        BATCH_SIZE,
    )

    for bi, batch in enumerate(batches, 1):
        if should_cancel is not None and should_cancel():
            logger.warning("Sanity check cancelled after %d/%d batches", bi - 1, len(batches))
            break
        if on_progress is not None:
            on_progress(f"Sanity-checking cards — batch {bi}/{len(batches)}")
        batch_flagged, resolved, unknown, cost = _check_batch(
            batch, model=model, log_dir=log_dir, on_card=on_card, thinking=thinking
        )
        total_cost += cost
        unknown_total += len(unknown)
        passed += len(resolved) - len(batch_flagged)
        for cn, reason in batch_flagged.items():
            flagged[cn] = reason
            logger.info("  sanity: %s — %s", cn, reason)

    checked = passed + len(flagged)
    analysis = f"{passed}/{checked} cards passed sanity check." if checked else "No cards to check."
    if unknown_total:
        analysis += f" {unknown_total} card(s) could not be checked (response truncated)."
    logger.info(
        "Sanity check: %d/%d passed, %d flagged, %d unknown, $%.4f",
        passed,
        checked,
        len(flagged),
        unknown_total,
        total_cost,
    )
    return flagged, analysis, total_cost
