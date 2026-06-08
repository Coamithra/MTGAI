"""Functional-duplicate detection — the algorithmic third step of the gate.

The merged ``conformance`` gate's final step (displayed "Duplicate Check").
Unlike the conformance and interaction steps, this one makes **no LLM call**: it
is a pure, deterministic scan that flags cards which are *functionally the same
modulo mana cost* — two cards with the same type line, the same power/toughness/
loyalty, and the same rules text once mana cost is set aside.

The signature deliberately **excludes the mana cost** (that's the "modulo mana
cost" in the spec) and normalizes the oracle text so trivial reorderings don't
hide a duplicate: reminder text is stripped, the card's own name is folded to a
placeholder, and the text is split into clauses (on newlines / commas /
semicolons) which are then sorted — so ``"Flying, vigilance"`` and
``"Vigilance, flying"`` produce the same signature.

This is a normalization, not a semantic comparison: a duplicate written with
genuinely different phrasing ("draw a card" vs "put the top card of your library
into your hand") will slip through. That trade-off is accepted — the cheap
algorithmic pass catches the common cases (copy-with-different-cost, reordered
keywords) without an LLM round-trip.

For each duplicate group the **lowest collector number is kept** and the rest are
flagged for regeneration, so the slot still fills but the redundant copies get
redesigned.

Usage:
    from mtgai.analysis.duplicates import find_duplicates

    findings, analysis_text = find_duplicates(cards)
"""

from __future__ import annotations

import logging
import re

from mtgai.analysis.gate_common import filter_gate_cards
from mtgai.analysis.models import DuplicateFinding
from mtgai.models.card import Card

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Normalization — build the mana-cost-agnostic functional signature
# ---------------------------------------------------------------------------


def _normalize_type_line(card: Card) -> str:
    """Type line as a sorted, lowercased token set (order-insensitive)."""
    tl = card.type_line or ""
    # Split on any non-alphanumeric run (whitespace, the supertype/type/subtype
    # dash, hyphens) and sort, so "Artifact Creature" == "Creature Artifact" and
    # the dash glyph variant doesn't matter.
    tokens = re.split(r"[^a-z0-9]+", tl.lower())
    return " ".join(sorted(t for t in tokens if t))


def _normalize_oracle(card: Card) -> str:
    """Rules text reduced to a sorted set of normalized clauses.

    Strips reminder text, folds the card's own name to ``~``, lowercases, then
    splits into clauses and sorts them so keyword/clause ordering can't hide a
    duplicate ("Flying, vigilance" == "Vigilance, flying").
    """
    text = card.oracle_text or ""
    # Reminder text is never authored by the gate's view of the card; drop all
    # parenthetical text so it can't perturb the signature.
    text = re.sub(r"\([^)]*\)", " ", text)
    # Fold the card's own name to a self-reference token, so two otherwise
    # identical cards with different names still match.
    name = (card.name or "").strip()
    if name:
        text = re.sub(re.escape(name), "~", text, flags=re.IGNORECASE)
    text = text.lower()
    # Split into clauses on newlines / commas / semicolons, normalize whitespace,
    # drop surrounding punctuation, then sort to neutralize ordering.
    clauses = [re.sub(r"\s+", " ", c).strip(" .") for c in re.split(r"[\n,;]+", text)]
    clauses = sorted(c for c in clauses if c)
    return " | ".join(clauses)


def _signature(card: Card) -> tuple[str, str | None, str | None, str | None, str]:
    """Functional signature of a card, **excluding its mana cost**.

    Two cards with an equal signature are considered functional duplicates: same
    type line, same power/toughness/loyalty, same normalized rules text.
    """
    return (
        _normalize_type_line(card),
        card.power,
        card.toughness,
        card.loyalty,
        _normalize_oracle(card),
    )


def _collector_key(card: Card) -> tuple[int, str]:
    """Sort key that orders cards by their numeric collector number.

    Falls back to a large sentinel (then the raw string) when no digits are
    present, so cards without a numeric collector number sort last but stably.
    """
    raw = card.collector_number or card.slot_id or ""
    m = re.search(r"\d+", raw)
    return (int(m.group()) if m else 1_000_000, raw)


def _flag_key(card: Card) -> str | None:
    """The id the gate flags a card by — slot_id, falling back to collector number."""
    return card.slot_id or card.collector_number or None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def find_duplicates(cards: list[Card]) -> tuple[list[DuplicateFinding], str]:
    """Scan the pool for functional duplicates (modulo mana cost).

    Skips basic lands + reprints (shared ``filter_gate_cards``). Groups the
    remaining cards by their mana-cost-agnostic functional signature; for each
    group of two or more, keeps the lowest collector number and returns a
    :class:`DuplicateFinding` for every other member. Purely algorithmic — no
    LLM call, so it returns no cost. Returns ``(findings, analysis_text)``.
    """
    gate_cards = filter_gate_cards(cards)
    if not gate_cards:
        return [], ""

    groups: dict[tuple, list[Card]] = {}
    for card in gate_cards:
        groups.setdefault(_signature(card), []).append(card)

    findings: list[DuplicateFinding] = []
    dup_groups = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        dup_groups += 1
        members.sort(key=_collector_key)
        keep, *rest = members
        keep_label = keep.name or keep.slot_id or keep.collector_number or "another card"
        for card in rest:
            slot_id = _flag_key(card)
            if not slot_id:
                logger.warning(
                    "Duplicate card %r has no slot_id/collector_number; skipping", card.name
                )
                continue
            findings.append(
                DuplicateFinding(
                    slot_id=slot_id,
                    card_name=card.name,
                    duplicate_of=keep_label,
                    reason=(
                        f"Functionally identical to {keep_label} (ignoring mana cost). "
                        "Redesign this card so it does something meaningfully different."
                    ),
                )
            )

    if findings:
        analysis = (
            f"{len(findings)} card(s) in {dup_groups} duplicate group(s) "
            "are functionally identical modulo mana cost."
        )
    else:
        analysis = "No functional duplicates found."

    logger.info("Duplicate check: %d card(s) flagged across %d group(s)", len(findings), dup_groups)
    return findings, analysis


def find_duplicate_names(cards: list[Card]) -> tuple[list[DuplicateFinding], str]:
    """Scan the pool for cards that share a name (case-insensitive).

    MTG forbids two *distinct* cards from carrying the same name, but the
    functional-duplicate scan above can't catch a name collision between two
    cards that do different things (its signature is type/P/T/oracle, not name).
    This is the complementary check: group the gate-eligible cards by their
    normalized name and, for each group of two or more, keep the lowest collector
    number and flag the rest for regeneration with a rename instruction.

    Skips basic lands + reprints (shared ``filter_gate_cards``): basic lands
    legitimately repeat a name ("Forest"), and reprints carry real printed names
    and aren't regenerated. Purely algorithmic — no LLM call. Returns
    ``(findings, analysis_text)``.
    """
    gate_cards = filter_gate_cards(cards)
    if not gate_cards:
        return [], ""

    groups: dict[str, list[Card]] = {}
    for card in gate_cards:
        key = (card.name or "").strip().lower()
        if not key:
            continue
        groups.setdefault(key, []).append(card)

    findings: list[DuplicateFinding] = []
    dup_groups = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        dup_groups += 1
        members.sort(key=_collector_key)
        keep, *rest = members
        keep_label = keep.name or keep.slot_id or keep.collector_number or "another card"
        for card in rest:
            slot_id = _flag_key(card)
            if not slot_id:
                logger.warning(
                    "Duplicate-named card %r has no slot_id/collector_number; skipping", card.name
                )
                continue
            findings.append(
                DuplicateFinding(
                    slot_id=slot_id,
                    card_name=card.name,
                    duplicate_of=keep_label,
                    reason=(
                        f'Duplicate card name "{card.name}" — already used by '
                        f"{keep_label} (#{keep.collector_number}). MTG forbids two distinct "
                        "cards sharing a name; give this card a different, fitting name."
                    ),
                )
            )

    if findings:
        analysis = (
            f"{len(findings)} card(s) in {dup_groups} group(s) share a name with another card."
        )
    else:
        analysis = "No duplicate card names found."

    logger.info(
        "Duplicate-name check: %d card(s) flagged across %d group(s)", len(findings), dup_groups
    )
    return findings, analysis
