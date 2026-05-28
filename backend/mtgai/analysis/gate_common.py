"""Shared helpers for the post-card_gen review gates.

Both LLM gates (conformance, interactions) scan the same subset of the pool:
every generated card *except* basic lands and reprints. Basic lands carry no
design to conform or combo; reprints are pre-balanced staples (and aren't even
materialized as cards yet). Keeping the filter in one place means the two gates
never drift on what they consider.
"""

from __future__ import annotations

from mtgai.models.card import Card


def is_basic_land(card: Card) -> bool:
    """True for a basic land printing (``Basic`` supertype + ``Land`` type)."""
    return "Basic" in (card.supertypes or []) and "Land" in (card.card_types or [])


def filter_gate_cards(cards: list[Card]) -> list[Card]:
    """Drop basic lands and reprints — the cards a review gate never flags."""
    return [c for c in cards if not c.is_reprint and not is_basic_land(c)]
