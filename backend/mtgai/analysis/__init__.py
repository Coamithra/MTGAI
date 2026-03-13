"""Set balance analysis -- skeleton conformance and gameplay coverage checks.

Two categories of analysis:
    A. Skeleton conformance (per-slot) -- did the generated card match what was planned?
    B. Set-wide coverage -- does the set provide enough removal, card advantage, mana curve, etc.?

Usage:
    from mtgai.analysis import analyze_set

    result = analyze_set("ASD")
    print(result.summary)
"""

from mtgai.analysis.balance import analyze_set
from mtgai.analysis.models import (
    AnalysisIssue,
    AnalysisSeverity,
    BalanceAnalysisResult,
    ColorCoverageResult,
    MechanicDistribution,
    SlotConformanceResult,
)

__all__ = [
    "AnalysisIssue",
    "AnalysisSeverity",
    "BalanceAnalysisResult",
    "ColorCoverageResult",
    "MechanicDistribution",
    "SlotConformanceResult",
    "analyze_set",
]
