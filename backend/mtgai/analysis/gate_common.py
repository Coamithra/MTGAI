"""Shared helpers for the post-card_gen review gates.

Both LLM steps (conformance, interactions) of the merged ``conformance`` gate
scan the same subset of the pool: every generated card *except* basic lands and
reprints. Basic lands carry no design to conform or combo; reprints are
pre-balanced staples (and aren't even materialized as cards yet). Keeping the
filter in one place means the two steps never drift on what they consider.

The gate's single LLM round-trip also goes through :func:`generate_gate_tool`,
which retries a truncated (repetition-looped) local-model response.
"""

from __future__ import annotations

import logging

from mtgai.generation.llm_client import generate_with_tool
from mtgai.generation.token_utils import OutputTruncatedError
from mtgai.models.card import Card
from mtgai.runtime import ai_lock

logger = logging.getLogger(__name__)


def generate_gate_tool(
    *,
    base_temperature: float,
    retries: int = 2,
    temperature_step: float = 0.2,
    **kwargs,
) -> dict:
    """Run a gate's ``generate_with_tool`` call, retrying on output truncation.

    Local models (Gemma) occasionally fall into a repetition loop and exhaust
    the output budget mid-tool-call, surfacing as :class:`OutputTruncatedError`.
    A plain re-roll at the same low temperature tends to reproduce the loop, so
    each retry **bumps the temperature** by ``temperature_step`` to perturb the
    decode out of it (a verified lever where ``repeat_penalty`` escalation is
    not — see ``learnings/gemma-repetition-loops.md``).

    Makes up to ``retries + 1`` attempts. Honours cancellation between attempts
    (so the Cancel button still halts the gate) and re-raises the last
    ``OutputTruncatedError`` after the final attempt — the merged gate runner
    lets that propagate so the stage fails visibly rather than silently
    skipping a check. ``kwargs`` are forwarded to ``generate_with_tool``
    verbatim (it must NOT include ``temperature`` — this helper owns it).
    """
    last_exc: OutputTruncatedError | None = None
    for attempt in range(retries + 1):
        if attempt and ai_lock.is_cancelled():
            raise last_exc if last_exc else RuntimeError("gate cancelled")
        temperature = base_temperature + temperature_step * attempt
        try:
            return generate_with_tool(temperature=temperature, **kwargs)
        except OutputTruncatedError as exc:
            last_exc = exc
            logger.warning(
                "Gate LLM output truncated (attempt %d/%d at temp %.2f): %s",
                attempt + 1,
                retries + 1,
                temperature,
                exc,
            )
    assert last_exc is not None
    raise last_exc


def is_basic_land(card: Card) -> bool:
    """True for a basic land printing (``Basic`` supertype + ``Land`` type)."""
    return "Basic" in (card.supertypes or []) and "Land" in (card.card_types or [])


def filter_gate_cards(cards: list[Card]) -> list[Card]:
    """Drop basic lands and reprints — the cards a review gate never flags."""
    return [c for c in cards if not c.is_reprint and not is_basic_land(c)]
