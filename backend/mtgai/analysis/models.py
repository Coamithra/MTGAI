"""Pydantic models for the post-card_gen review gates.

The set-level balance / coverage / algorithmic-conformance machinery (and its
``BalanceAnalysisResult`` aggregate) was removed when the balance stage became
the review→regen loop. What remains
are the structured findings the two LLM gates produce: ``InteractionFlag`` (the
whole-pool degenerate-combo scan) and ``ConformanceFinding`` (per-card adherence
to its slot spec).
"""

from __future__ import annotations

from pydantic import BaseModel


class InteractionFlag(BaseModel):
    """A degenerate card interaction flagged by the LLM interaction scanner.

    Minimal by design: the only consumer is ``run_conformance``, which flags the
    enabler card (joined by ``enabler_slot_id``) for regeneration with a reason
    built from ``reason`` (the diagnosis) + ``replacement_constraint`` (the fix).
    """

    enabler_slot_id: str  # join key — which card gets flagged for regen
    reason: str  # what the degenerate interaction is (the diagnosis)
    replacement_constraint: str  # what the regenerated card must avoid (the fix)


class ConformanceFinding(BaseModel):
    """One non-conforming card flagged by the LLM conformance gate.

    The model judges each card against its slot's relabeled spec holistically;
    a finding names the offending ``slot_id`` and a one-line reason ("slot wants
    X, card is Y") that becomes the card's ``regen_reason``.
    """

    slot_id: str
    card_name: str | None = None
    reason: str
