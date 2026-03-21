"""Pydantic models for balance analysis results.

These structured outputs are consumed by Phase 4B's AI review and also
serialized to JSON/Markdown reports.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class AnalysisSeverity(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class AnalysisIssue(BaseModel):
    """A single finding from the balance analysis."""

    check: str  # e.g. "conformance.color", "coverage.cmc_gap"
    severity: AnalysisSeverity
    slot_id: str | None = None
    card_name: str | None = None
    message: str
    expected: str | None = None
    actual: str | None = None


class SlotConformanceResult(BaseModel):
    """Result of checking one skeleton slot against its generated card."""

    slot_id: str
    card_name: str | None = None
    matched: bool
    issues: list[AnalysisIssue] = Field(default_factory=list)


class CreatureSizeEntry(BaseModel):
    """Count of creatures in a weight class for a single color."""

    weight_class: str  # small, medium, beefy, huge
    count: int


class ColorCoverageResult(BaseModel):
    """Per-color analysis of creature curve, removal, and card advantage."""

    color: str
    total_cards: int
    total_creatures: int
    creature_cmc_buckets: dict[int, int] = Field(default_factory=dict)  # cmc -> count
    creature_cmc_gaps: list[int] = Field(default_factory=list)  # missing CMCs
    creature_sizes: list[CreatureSizeEntry] = Field(default_factory=list)
    removal_count: int = 0
    removal_cards: list[str] = Field(default_factory=list)
    card_advantage_count: int = 0
    card_advantage_cards: list[str] = Field(default_factory=list)


class MechanicDistribution(BaseModel):
    """Planned vs actual distribution for a single set mechanic."""

    mechanic_name: str
    planned: dict[str, int] = Field(default_factory=dict)  # rarity -> count
    actual: dict[str, int] = Field(default_factory=dict)  # rarity -> count
    total_planned: int = 0
    total_actual: int = 0


class InteractionFlag(BaseModel):
    """A degenerate card interaction flagged by the LLM interaction scanner."""

    cards_involved: list[str]
    interaction_type: str  # infinite_combo, degenerate_synergy, unintended_loop
    description: str
    severity: str  # WARN or FAIL
    enabler_card: str
    enabler_slot_id: str
    why_enabler: str
    replacement_constraint: str


class BalanceAnalysisResult(BaseModel):
    """Top-level result of the full Phase 4A balance analysis."""

    set_code: str
    total_cards: int
    total_skeleton_slots: int

    # Per-slot conformance
    conformance: list[SlotConformanceResult] = Field(default_factory=list)

    # Set-wide coverage
    color_coverage: list[ColorCoverageResult] = Field(default_factory=list)
    mechanic_distribution: list[MechanicDistribution] = Field(default_factory=list)
    mana_fixing_sources: list[str] = Field(default_factory=list)
    color_balance: dict[str, int] = Field(default_factory=dict)  # color -> count

    # Interaction analysis
    interaction_flags: list[InteractionFlag] = Field(default_factory=list)
    interaction_analysis: str = ""  # LLM's overall assessment

    # All issues aggregated
    issues: list[AnalysisIssue] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)  # {PASS: N, WARN: N, FAIL: N}
