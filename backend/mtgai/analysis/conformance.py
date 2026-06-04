"""Conformance gate — LLM per-card adherence to its slot spec.

The first post-card_gen review gate. Each generated card was built to fill a
specific design slot; this step asks whether each card actually CONFORMS to its
slot's spec (``tweaked_text``, falling back to the default ``render_slot_string``).

**Batched, flag-only, streamed.** A one-LLM-call-per-card design was correct but
unusably slow: the app-wide AI mutex serializes calls and the local model runs
one request at a time, so a ~277-card set meant ~277 sequential round-trips (and
each card's chain-of-thought routinely blew the small output budget, surfacing as
a truncation error). Instead we group the pool into batches of ``BATCH_SIZE`` and
make **one streamed call per batch** via :func:`gate_common.stream_flag_batch`:
the model is shown every card in the batch with its slot spec and emits a
``--CARD <slot_id>--`` block **only for cards that do NOT conform** (the same
plain-text-block format the skeleton relabel + interaction gate use, so a
truncated reply still parses block-by-block). Conforming cards produce no output.
This cuts ~277 calls to ~7, keeps each call's output tiny, and makes truncation
rare; a batch that *does* truncate is retried (bumping temperature, the verified
loop escape) and only its unreached tail is left "unknown".

The model emits flagged cards in listing order, so the tab fills in a live
checklist as the stream arrives: when a flag for card N streams in, every earlier
not-yet-flagged card flips to ✓ (an advancing "approved frontier") and the flagged
card shows ✗; when the batch's call returns clean, its remaining cards flip to ✓.

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

from mtgai.analysis import gate_common
from mtgai.analysis.gate_common import filter_gate_cards
from mtgai.analysis.models import ConformanceFinding
from mtgai.generation import temperatures as temps
from mtgai.generation.token_budgets import STANDARD
from mtgai.models.card import Card

logger = logging.getLogger(__name__)

TEMPERATURE = temps.PRECISE  # objective adherence check (see temperatures.py)
# Flag-only output is short (one terse block per *failing* card), so a large
# ceiling is just truncation insurance — the model almost never approaches it.
MAX_TOKENS = STANDARD
# Cards per streamed call. ~40 keeps each batch's input modest, its output tiny,
# and gives the tab a progress checkpoint every batch while collapsing a ~277-card
# set to ~7 round-trips.
BATCH_SIZE = 40


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
# Prompt
# ---------------------------------------------------------------------------

CONFORMANCE_SYSTEM_PROMPT = """\
You are an expert Magic: The Gathering set developer running a conformance check. \
You are given a batch of cards, each built to fill a specific design slot, paired \
with the SLOT SPEC it was meant to fulfil.

For each card, decide whether it CONFORMS to its slot spec. A card does NOT \
conform when it clearly fails the spec:
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
non-conformance wastes a regeneration cycle.

## Output format

Go through the cards IN THE ORDER LISTED. For EACH card that does NOT conform, \
emit a block — and ONLY for cards that do not conform:

--CARD <slot_id>--
<one line: what the slot wants vs. what the card is>

Use the slot id shown in the listing (the value after ``--SLOT``). Output NOTHING \
for a card that conforms — skip it silently and move on. If every card in the \
batch conforms, output nothing at all. Do not write any preamble, summary, or \
commentary; emit only ``--CARD`` blocks for the cards you are flagging."""


def _build_batch_prompt(batch: list[tuple[str, Card, str]]) -> str:
    """Build the user prompt listing every card in the batch with its slot spec."""
    lines: list[str] = ["## Cards to check\n"]
    for slot_id, card, spec in batch:
        lines.append(f"--SLOT {slot_id}--")
        lines.append(f"  CARD: {_serialize_card(card)}")
        lines.append(f"  SPEC: {spec}")
    lines.append(
        "\n## Task\n\nFor each card above that does NOT conform to its SLOT SPEC, "
        "emit a `--CARD <slot_id>--` block with a one-line reason. Emit nothing for "
        "conforming cards."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-batch streamed check
# ---------------------------------------------------------------------------


def _check_batch(
    batch: list[tuple[str, Card, str]],
    *,
    model: str,
    log_dir,
    on_card: Callable[[dict], None] | None,
) -> tuple[dict[str, str], set[str], list[str], float]:
    """Stream-check one batch. Returns ``(flagged, resolved, unknown, cost)``.

    * ``flagged`` — ``{slot_id: reason}`` for the cards the model flagged.
    * ``resolved`` — slot ids that got a real verdict (approved or flagged).
    * ``unknown`` — slot ids left undecided (persistent truncation tail).
    * ``cost`` — summed USD across attempts.

    Fires ``on_card`` exactly once per card the moment it is decided: ✗ as each
    flag block streams in (advancing an approved frontier — every earlier
    not-yet-flagged card flips to ✓), then ✓ for the rest when the call returns
    clean. A batch that keeps truncating reports its unreached tail
    ``conforms=None`` (unknown, never flagged) and excludes it from ``resolved``.
    """
    order = [sid for sid, _, _ in batch]
    valid_ids = set(order)
    pos = {sid: i for i, sid in enumerate(order)}
    name_by = {sid: card.name for sid, card, _ in batch}

    flagged: dict[str, str] = {}
    resolved: set[str] = set()  # cards fired with a True/False verdict
    frontier = 0  # next listing position not yet approved

    def _fire(slot_id: str, conforms: bool | None, reason: str) -> None:
        if on_card is None:
            return
        on_card(
            {
                "slot_id": slot_id,
                "card_name": name_by.get(slot_id, ""),
                "conforms": conforms,
                "reason": reason,
            }
        )

    def _approve_through(p: int) -> None:
        """Approve every not-yet-resolved card at listing position < ``p``."""
        nonlocal frontier
        for i in range(frontier, p):
            sid = order[i]
            if sid not in resolved and sid not in flagged:
                resolved.add(sid)
                _fire(sid, True, "")
        frontier = max(frontier, p)

    def _on_block(slot_id: str, block: str) -> None:
        reason = gate_common.first_line(block) or "Does not match slot spec."
        # Cards listed before this one (and not themselves flagged) are fine.
        _approve_through(pos[slot_id])
        first = slot_id not in flagged
        flagged[slot_id] = reason
        resolved.add(slot_id)
        if first:
            _fire(slot_id, False, reason)

    completed, cost = gate_common.stream_flag_batch(
        system_prompt=CONFORMANCE_SYSTEM_PROMPT,
        user_prompt=_build_batch_prompt(batch),
        model=model,
        base_temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        log_dir=log_dir,
        name="check_conformance",
        valid_ids=valid_ids,
        on_block=_on_block,
    )

    if completed:
        # Clean finish: every remaining card in the batch conforms.
        _approve_through(len(order))
        return flagged, resolved, [], cost

    # Exhausted retries with the tail still unreached: report the undecided cards
    # as unknown (never flagged), excluded from the conform rate.
    unknown = [sid for sid in order if sid not in resolved]
    for sid in unknown:
        _fire(sid, None, "check failed: response truncated")
    return flagged, resolved, unknown, cost


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
    on_progress: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[list[ConformanceFinding], str, float]:
    """Check each card against its slot spec with one streamed call per batch.

    Skips basic lands + reprints, and any card whose slot has no resolvable
    spec. Returns ``(findings, analysis_text, cost_usd)`` where ``findings``
    is one :class:`ConformanceFinding` per non-conforming card.

    ``pre_flagged`` (``{slot_id: reason}``) folds an upstream verdict — the
    algorithmic functional-duplicate scan — into this per-card checklist: a
    pre-flagged card is seeded non-conforming (an X in the tab from the first
    paint), skipped by the LLM (it will be regenerated anyway), and returned as a
    finding carrying the given reason. Such a card is kept even when its slot has
    no resolvable spec, so a duplicate is never dropped.

    Hooks (all optional) drive the live tab checklist:

    * ``on_start(card_list)`` — fired once with ``[{slot_id, card_name}, ...]``
      for every card about to be checked (pre-flagged ones seeded ``conforms``
      false), so the tab renders the full list up front in a pending state.
    * ``on_card(record)`` — fired once per card as it is decided, with
      ``{slot_id, card_name, conforms, reason}``; ``conforms`` is ``None`` when
      the card's batch truncated past it (shown as unknown, never flagged).
    * ``on_progress(message)`` — fired before each batch (``"batch N/M"``) so the
      runner can surface coarse progress on the wizard strip.
    * ``should_cancel()`` — polled before each batch so the Cancel button halts
      the loop between batches (an in-flight stream is killed by the lock cancel).
    """
    pre_flagged = pre_flagged or {}
    pairs: list[tuple[str, Card, str]] = []
    for card in filter_gate_cards(cards):
        if not card.slot_id:
            continue
        if card.slot_id in pre_flagged:
            # Pre-flagged (duplicate) — keep it in the checklist even without a
            # spec; its spec is never read (it skips the LLM).
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

    from mtgai.io.asset_paths import set_artifact_dir
    from mtgai.runtime.active_project import require_active_project

    settings = require_active_project().settings
    try:
        log_dir = set_artifact_dir() / "conformance" / "logs"
    except Exception:
        log_dir = None
    model = settings.get_llm_model_id("conformance")

    findings: list[ConformanceFinding] = []
    total_cost = 0.0

    # Pre-flagged duplicates are decided up front: emit each as a failed row and a
    # finding, no LLM call. They're duplicate findings, not conformance failures,
    # so they're excluded from the conform-rate denominator below.
    for slot_id, card, _ in pairs:
        if slot_id in pre_flagged:
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

    # The LLM sees only the not-pre-flagged cards, grouped into batches.
    to_check = [p for p in pairs if p[0] not in pre_flagged]
    batches = [to_check[i : i + BATCH_SIZE] for i in range(0, len(to_check), BATCH_SIZE)]
    logger.info(
        "Conformance check: %d cards in %d batch(es) of up to %d (+%d pre-flagged duplicate(s))",
        len(to_check),
        len(batches),
        BATCH_SIZE,
        len(pre_flagged),
    )

    passed = 0
    unknown_total = 0
    for bi, batch in enumerate(batches, 1):
        if should_cancel is not None and should_cancel():
            logger.warning("Conformance cancelled after %d/%d batches", bi - 1, len(batches))
            break
        if on_progress is not None:
            on_progress(f"Checking cards — batch {bi}/{len(batches)}")
        flagged, resolved, unknown, cost = _check_batch(
            batch, model=model, log_dir=log_dir, on_card=on_card
        )
        total_cost += cost
        unknown_total += len(unknown)
        passed += len(resolved) - len(flagged)
        for slot_id, reason in flagged.items():
            name = next((c.name for sid, c, _ in batch if sid == slot_id), "")
            findings.append(ConformanceFinding(slot_id=slot_id, card_name=name, reason=reason))
            logger.info("  conformance: %s — %s", slot_id, reason)

    checked = passed + (len(findings) - len(pre_flagged))
    analysis = f"{passed}/{checked} cards conform." if checked else "No cards to check."
    if unknown_total:
        analysis += f" {unknown_total} card(s) could not be checked (response truncated)."
    logger.info(
        "Conformance: %d/%d conform, %d flagged (incl. %d duplicate), %d unknown, $%.4f",
        passed,
        checked,
        len(findings),
        len(pre_flagged),
        unknown_total,
        total_cost,
    )
    return findings, analysis, total_cost
