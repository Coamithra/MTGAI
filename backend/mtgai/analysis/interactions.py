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
from mtgai.generation.token_budgets import HEAVY
from mtgai.generation.token_utils import SAFETY_MARGIN, count_tokens, get_context_window
from mtgai.models.card import Card

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Model + effort come from per-set model_settings at runtime.
TEMPERATURE = temps.ANALYTICAL  # analytical scan (see temperatures.py)
# Flag-only output is short; a large ceiling is just truncation insurance.
MAX_TOKENS = HEAVY
# New cards checked per streamed call (existing cards ride along as context).
# Kept small (20) so the local model's reasoning over each batch's new-vs-pool
# combinations stays tractable and terminates instead of looping (the demonstrated
# "Tame Gemma 4 local overthinking" failure was this step at batch 40).
BATCH_SIZE = 20

# Flat token reserve for the parts of the batch prompt that are neither the system
# prompt, the existing-context block, nor the new-card listing: the section
# headers, code fences, the Task paragraph, and ``count_messages_tokens``'
# per-message overhead. Kept generous so the existing-context bound stays safely
# under ``check_pre_call``'s budget (overflow there raises ``ContextOverflowError``,
# which ``stream_flag_batch`` treats as a failed attempt — silently losing the
# batch). Used by :func:`_bound_existing_context`.
_PROMPT_SCAFFOLD_TOKENS = 600

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


def _bound_existing_context(
    existing: list[Card],
    *,
    model: str,
    new_tokens: int,
    mechanics_tokens: int,
    system_tokens: int,
    tok_by_id: dict[str, int],
) -> tuple[list[Card], int]:
    """Trim the cumulative existing-context to the most-recent cards that fit the
    assigned model's ACTUAL context window.

    The interaction step's existing-context grows with set size; on a model whose
    ``context_window`` is smaller than the full pool, the untrimmed prompt trips
    ``check_pre_call``'s ``ContextOverflowError``, which ``stream_flag_batch``
    treats as a failed attempt — retried at the same size, then the batch's cards
    are left ``interacts=None`` (silently unchecked). Bounding the context to a
    sliding window of the most-recent cards keeps each batch's prompt under the
    window: full cross-batch coverage when the model is large enough (nothing
    dropped), a bounded most-recent window when it is not.

    The budget mirrors ``token_utils.check_pre_call`` exactly — the same
    ``int(ctx * (1 - SAFETY_MARGIN)) - output_reserve`` arithmetic, with
    ``output_reserve == MAX_TOKENS`` (what ``analyze_interactions`` sends) — so a
    fit here guarantees a fit there. The most-recent cards are kept (the tail of
    ``existing``) because a later batch's new cards are most likely to interact
    with their nearest neighbours; far-apart-pair coverage is the accepted
    trade-off (the cumulative scan's whole-pool guarantee can't hold under a window
    too small to hold the whole pool).

    Returns ``(kept_existing, dropped_count)``.
    """
    ctx = get_context_window(model)
    safe_budget = int(ctx * (1 - SAFETY_MARGIN)) - MAX_TOKENS
    fixed = system_tokens + new_tokens + mechanics_tokens + _PROMPT_SCAFFOLD_TOKENS
    existing_budget = safe_budget - fixed
    if existing_budget <= 0:
        # Even the new batch + system barely fits this window — send no existing
        # context (the new cards still get checked against each other).
        return [], len(existing)
    kept_rev: list[Card] = []
    used = 0
    for card in reversed(existing):
        cost = tok_by_id.get(_card_id(card), 0)
        if used + cost > existing_budget:
            break
        used += cost
        kept_rev.append(card)
    kept = list(reversed(kept_rev))
    return kept, len(existing) - len(kept)


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
1. **Infinite combos** — two or three cards that create a genuinely UNBOUNDED loop \
(infinite damage, infinite tokens, infinite life, infinite mana, etc.) with no \
natural stopping point.
2. **Degenerate synergies** — two cards that together produce an effect so far \
beyond their rarity and mana cost that they warp a limited game (a turn-two kill, \
a soft-lock, near-unbeatable repeatable value at common/uncommon).
3. **Unintended loops** — cards that trigger each other repeatedly without a \
natural stopping point.

You are NOT looking for:
- **Strong-but-bounded cards.** A card that is individually powerful — or a tutor, \
search, or value engine that fires AT MOST ONCE PER TURN — is NOT a degenerate \
interaction; it is just a strong card. Power level is a SEPARATE concern from combo \
health: do not flag a card here merely for being strong.
- Strong synergies that are intentional design (a payoff card rewarding the \
mechanic, card type, or archetype it is built around is the set working as \
intended, not a degenerate interaction).
- Three-card combos that require very specific board states (too unlikely in limited).
- Color-pair synergies that only work if you draft both colors (that's normal).

## Respect rate limiters before claiming a loop

An ability can ONLY anchor an infinite or repeatable loop if it can actually be \
activated repeatedly within a single turn at no net cost. BEFORE flagging any loop \
or "repeatable" interaction, read the enabling ability's own text and check for a \
limiter that breaks it:
- "Activate only once each turn" / "once each turn" / "once per turn" — caps the \
ability at one use; it CANNOT loop, no matter how many counters/resources exist.
- Sorcery-speed / "only as a sorcery" / "only during your turn" — no instant-speed loop.
- A tap ({T}) cost with no built-in untap — the permanent stays tapped, so the \
ability fires once per turn unless ANOTHER card untaps it; if so, that free \
repeatable untapper is the real enabler, not this card.
- A one-shot or counting cost (sacrifice, exile, "remove a counter") the combo \
cannot replenish fast enough to sustain a loop.

To flag a loop you MUST be able to name the exact repeatable cycle (A enables B \
enables A …) and confirm that NO clause on any card in it breaks the repetition. A \
"counter generator + counter consumer" pair is a loop ONLY if the consumer can fire \
repeatedly each turn — if it reads "once each turn", it cannot. If a limiter caps \
the interaction, it is not a loop: do not flag it.

## Weigh rarity

Each card's rarity is shown. Higher rarities are ALLOWED to be more powerful: a \
strong tutor, engine, or payoff at **rare or mythic** is acceptable design, not a \
problem to flag. Reserve flags for interactions degenerate even after accounting \
for the enabler's rarity. Be most suspicious of two-card combos at \
**common/uncommon**, which most drafters will actually assemble.

## Identify the true enabler — it is often an EARLIER card

For each problematic interaction, name the **enabler**: the single card whose \
design is the ROOT CAUSE and must change to break the interaction. The enabler is \
typically the card providing the undercosted or unrestricted effect (free untap, \
cost reduction, repeated recursion, a free repeatable trigger); the other card(s) \
are usually individually fine.

Do NOT default to blaming the NEW card under review. The new card is frequently an \
innocent payoff that merely USES an enabler already present in the set — in that \
case flag the EXISTING enabler, NOT the new payoff. The enabler may be a NEW card \
or an EXISTING (already-reviewed) one; pick whichever is genuinely the root cause, \
even if it appears earlier in the listing. Ask: "which card, if redesigned, makes \
this interaction fair?" — that card is the enabler.

Do NOT fabricate problems — false positives waste design time and wrongly nerf \
good cards. When in doubt, do not flag.

## Output format

For each degenerate interaction you find, emit a block — and ONLY for real problems:

--CARD <enabler_slot_id>--
<one line: which cards combo and step-by-step how the degenerate interaction \
works; name the other card(s) involved and the exact repeatable cycle>
AVOID: <a brief structural constraint the regenerated enabler must satisfy, e.g. \
"no free untap of a creature" — not a restatement of the problem>

Use the id shown at the start of the enabler's line (the value before the first \
``|``) — and make sure it is the ENABLER's id, which may be an EXISTING card from \
an earlier batch, not necessarily the new card. If a new card creates no \
degenerate interaction, output nothing for it — do NOT emit a ``--CARD`` block to \
say a card is clean or has no interaction; a block means a real degenerate \
interaction was found. If the whole batch is clean, output nothing at all. Write \
no preamble, summary, or commentary — emit only ``--CARD`` blocks."""


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
        "for each REAL problem, naming the root-cause **enabler** — which may be an "
        "existing card above, not necessarily the new card. Emit nothing for clean "
        "cards, for merely-strong cards, and for any interaction a rate limiter "
        "(once each turn / sorcery-speed / tap-with-no-untap) already caps.\n\n"
        "Remember: this is a limited format (draft/sealed). Players open ~45 cards "
        "and build 40-card decks. Two-card combos at common are much more likely "
        "than three-card combos at rare; a strong card at rare/mythic is fine. "
        "Weight severity accordingly."
    )
    return "\n\n---\n\n".join(sections)


# A drifting local model sometimes ignores the flag-only contract and emits a
# ``--CARD`` block for a card with NO degenerate interaction (body "No combo
# found." / "None."). Firing it as a flag needlessly regenerates a fine card.
# ``_is_interaction_flag`` is the durable backstop, mirroring conformance's.
#
# The guard is deliberately conservative — it must NEVER drop a real combo flag.
# A genuine flag often *opens* with clean-sounding words because the prompt notes
# the other card "is usually fine on its own" ("Fine alone but combos with Y for
# infinite mana"). So a block is dropped only when ALL of:
#   * it carries no ``AVOID:`` line (a real flag's required replacement constraint),
#   * its body *starts* with an all-clear opener (``_CLEAN_OPENER_RE``), and
#   * it contains no positive combo cue or contrastive conjunction
#     (``_POSITIVE_COMBO_RE``) that betrays a real interaction being described.
# "No combo." is dropped; "No issues alone BUT combos with Y" is kept.
_CLEAN_OPENER_RE = re.compile(
    r"^(?:none|n/?a|clean|nothing(?:\s+problematic)?|all\s+clear"
    r"|no\s+(?:degenerate\s+)?(?:interactions?|combos?|loops?|synerg\w*"
    r"|issues?|problems?|concerns?))\b",
    re.IGNORECASE,
)
# A combo word stated positively (NOT negated by a preceding "no"/"not") or a
# contrastive conjunction means the body is describing a real interaction even
# though it opened with clean-sounding words — keep the block.
_POSITIVE_COMBO_RE = re.compile(
    r"\b(?:but|however|yet|though|although|except)\b"
    r"|(?<!no )(?<!not )\b(?:combos?|loops?|infinite|untaps?|recursion|together|chains?)\b",
    re.IGNORECASE,
)


def _has_avoid_line(block: str) -> bool:
    return any(_AVOID_RE.match(line.strip()) for line in block.splitlines())


def _is_interaction_flag(block: str) -> bool:
    """True when a ``--CARD`` block is a genuine degenerate-interaction flag.

    Returns False (drop) only for a clear all-clear note with no ``AVOID:`` line:
    the body opens with an all-clear verdict and carries no positive combo cue or
    contrastive conjunction. A block with an ``AVOID:`` line, one that does not
    open clean, or one whose body betrays a real interaction is kept — so a real
    flag is never newly dropped (the worst case is the pre-fix behaviour).
    """
    if _has_avoid_line(block):
        return True  # carries the required replacement constraint -> real flag
    body = " ".join(block.split())  # collapse whitespace/newlines to one line
    if not body:
        return True  # bare flag — honour it (parse defaults the reason)
    # Drop only a clean-opening note with no positive combo cue / contrast.
    return not (_CLEAN_OPENER_RE.match(body) and not _POSITIVE_COMBO_RE.search(body))


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
    new_only: set[str] | None = None,
    on_start: Callable[[list[dict]], None] | None = None,
    on_card: Callable[[dict], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[list[InteractionFlag], str, float]:
    """Scan the pool for degenerate interactions, one streamed batch at a time.

    Skips basic lands + reprints. Returns ``(flags, analysis_text, cost_usd)``;
    each flag names an enabler card (by ``enabler_slot_id``) the runner will flag
    for regeneration.

    ``new_only`` (a set of card ids) scopes the scan to the cards regenerated
    since a *later* gate instance's predecessor ran: those become the "new" cards
    to check, while every other card rides along as fixed **existing context**.
    Each regenerated card is thus still checked against the whole pool, but pairs
    of two unchanged cards (already vetted by an earlier instance) are not
    re-scanned. The flagged enabler may still be an existing (unchanged) card —
    a regenerated card can create a combo whose root cause is an old card.
    ``None`` checks every card as new (the backbone / first-instance behaviour).

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

    valid_ids = {_card_id(c) for c in gate_cards}  # an enabler may be an existing card
    name_by = {_card_id(c): c.name for c in gate_cards}

    # Scope: a later instance checks only the regenerated cards (``to_check``)
    # against everything else as fixed existing context (``context``). The
    # backbone treats every card as new with no prior context.
    if new_only is not None:
        context = [c for c in gate_cards if _card_id(c) not in new_only]
        to_check = [c for c in gate_cards if _card_id(c) in new_only]
    else:
        context, to_check = [], gate_cards

    if not to_check:
        return [], "No new cards to check.", 0.0

    if on_start is not None:
        on_start([{"slot_id": _card_id(c), "card_name": c.name} for c in to_check])

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
    thinking = settings.get_thinking("conformance")

    # Per-card serialized token cost + the fixed prompt parts, precomputed once so
    # each batch can bound its cumulative existing-context to the assigned model's
    # ACTUAL context window (see _bound_existing_context). On a large window this
    # drops nothing; on a low-context local model it slides the window so the
    # prompt never overflows check_pre_call (the silent-skip bug this fixes).
    tok_by_id = {_card_id(c): count_tokens(_serialize_card_full(c)) for c in gate_cards}
    system_tokens = count_tokens(INTERACTION_SYSTEM_PROMPT)
    mechanics_tokens = (
        count_tokens(
            "\n".join(f"- **{m['name']}**: {m.get('reminder_text', '')}" for m in mechanics)
        )
        if mechanics
        else 0
    )

    batches = [to_check[i : i + BATCH_SIZE] for i in range(0, len(to_check), BATCH_SIZE)]
    logger.info(
        "Interaction analysis: %d new card(s) in %d batch(es) of up to %d (+%d existing context)",
        len(to_check),
        len(batches),
        BATCH_SIZE,
        len(context),
    )

    flags: dict[str, tuple[str, str]] = {}  # enabler slot_id -> (reason, constraint)
    total_cost = 0.0
    max_context_dropped = 0  # most cards a single batch had to drop to fit the window

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
        # Existing context = the always-present fixed context (unchanged cards on
        # a scoped run; empty on the backbone) + the new cards already processed.
        existing = context + to_check[: (bi - 1) * BATCH_SIZE]
        # Bound it to the assigned model's actual context window so a low-context
        # local model never overflows check_pre_call (which silently skips the
        # batch). A large window drops nothing — full coverage preserved.
        new_tokens = sum(tok_by_id.get(_card_id(c), 0) for c in new_batch)
        existing, dropped = _bound_existing_context(
            existing,
            model=model,
            new_tokens=new_tokens,
            mechanics_tokens=mechanics_tokens,
            system_tokens=system_tokens,
            tok_by_id=tok_by_id,
        )
        max_context_dropped = max(max_context_dropped, dropped)
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
            is_flag_block=_is_interaction_flag,
            thinking=thinking,
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

    if max_context_dropped:
        # Degrade LOUDLY: the assigned model's window can't hold the whole pool, so
        # the cumulative scan ran on a most-recent sliding window — far-apart pairs
        # may have been missed. (Better than the old silent skip, but a sign the
        # conformance stage wants a larger-context model for this set size.)
        logger.warning(
            "Interaction scan: model %s (context_window=%d) too small to hold the "
            "%d-card pool; up to %d existing-context card(s) were dropped from the "
            "largest batch (sliding window). Far-apart-pair coverage is reduced — "
            "assign a larger-context model to the conformance stage for full coverage.",
            model,
            get_context_window(model),
            len(gate_cards),
            max_context_dropped,
        )

    analysis = (
        f"{len(flags_out)} degenerate interaction(s) flagged."
        if flags_out
        else "No degenerate interactions found."
    )
    logger.info("Interactions: %d flagged, $%.4f", len(flags_out), total_cost)
    return flags_out, analysis, total_cost
