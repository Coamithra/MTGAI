"""Heuristic design-judgment checks for finished cards.

These were originally MANUAL-tier outputs of the gen-time validator, where they
got stamped on each card's ``generation_attempts[].validation_errors`` and
re-read hours later by the council reviewer. They've moved here so they:

* Don't pollute the gen-time return with non-actionable warnings
  (gen time only acts on schema parse failures and text overflow, both of which
  trigger a regen via :mod:`mtgai.validation`).
* Get computed *fresh* against the card the council is about to review, rather
  than against the gen-time snapshot — important because a prior reviewer in
  the council loop may have already mutated the card.
* Live next to the other analysis surfaces (balance, conformance, interactions)
  so the design-judgment heuristics are findable as a family.

The findings are :class:`ValidationError` instances with severity ``MANUAL``,
shaped exactly like the legacy ride-along errors so existing prompt-stuffing
formatters and report writers consume them without changes.
"""

from __future__ import annotations

from mtgai.models.card import Card
from mtgai.validation import ValidationError
from mtgai.validation.color_pie import validate_color_pie
from mtgai.validation.power_level import validate_power_level
from mtgai.validation.uniqueness import validate_mechanical_similarity


def check_card_heuristics(
    card: Card, existing_cards: list[Card] | None = None
) -> list[ValidationError]:
    """Run the design-judgment heuristics against ``card``.

    Aggregates power-level checks (P+T vs CMC, NWO complexity, removal
    efficiency), color-pie adherence, and mechanical-similarity findings
    against ``existing_cards``. All findings are MANUAL — they inform human /
    LLM review but never auto-fix and never trigger a regen.

    ``existing_cards`` is optional; if omitted, mechanical-similarity is
    skipped (the per-card checks still run).
    """
    findings: list[ValidationError] = []
    findings += validate_power_level(card)
    findings += validate_color_pie(card)
    if existing_cards:
        findings += validate_mechanical_similarity(card, existing_cards)
    return findings


def format_findings_for_prompt(findings: list[ValidationError]) -> str:
    """Render heuristic findings as a deduped bullet list for an LLM prompt.

    Returns an empty string when there are no findings, so the caller can
    skip the whole hints section without an extra check. The findings are framed
    as *hints* (not hard rules) — power-level/color-pie heuristics are advisory
    and the reviewer is told to override them when the card warrants it.
    """
    if not findings:
        return ""
    seen: set[str] = set()
    lines: list[str] = []
    for f in findings:
        key = f.message
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"  - {f.message}")
    return "Auto-validator hints (rough guidance, not rules):\n" + "\n".join(lines)
