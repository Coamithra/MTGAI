"""Top-level orchestrator for Phase 4A balance analysis.

Loads all inputs, runs conformance and coverage checks, aggregates results.
"""

from __future__ import annotations

import json
from pathlib import Path

from mtgai.analysis.conformance import analyze_conformance
from mtgai.analysis.coverage import (
    analyze_color_balance,
    analyze_color_coverage,
    analyze_mana_fixing,
    analyze_mechanic_distribution,
)
from mtgai.analysis.interactions import analyze_interactions
from mtgai.analysis.models import BalanceAnalysisResult
from mtgai.io.card_io import load_card
from mtgai.models.card import Card
from mtgai.skeleton.generator import SkeletonSlot


def _project_root() -> Path:
    """Return the project root (parent of backend/)."""
    return Path(__file__).resolve().parent.parent.parent.parent


def load_analysis_inputs() -> tuple[
    list[Card], list[SkeletonSlot], list[dict], dict[str, list[str]]
]:
    """Load all inputs for the balance analysis from the active project.

    Returns (cards, skeleton_slots, mechanics, functional_tags).
    """
    from mtgai.io.asset_paths import set_artifact_dir

    sdir = set_artifact_dir()

    # Load cards
    cards_dir = sdir / "cards"
    cards: list[Card] = []
    if cards_dir.exists():
        for path in sorted(cards_dir.glob("*.json")):
            cards.append(load_card(path))

    # Load skeleton
    skeleton_path = sdir / "skeleton.json"
    slots: list[SkeletonSlot] = []
    if skeleton_path.exists():
        raw = json.loads(skeleton_path.read_text(encoding="utf-8"))
        slots = [SkeletonSlot(**s) for s in raw.get("slots", [])]

    # Load mechanics
    mechanics_path = sdir / "mechanics" / "approved.json"
    mechanics: list[dict] = []
    if mechanics_path.exists():
        mechanics = json.loads(mechanics_path.read_text(encoding="utf-8"))

    # Load functional tags (sidecar file or from mechanics themselves)
    tags_path = sdir / "mechanics" / "functional-tags.json"
    functional_tags: dict[str, list[str]] = {}
    if tags_path.exists():
        functional_tags = json.loads(tags_path.read_text(encoding="utf-8"))

    # Merge tags from mechanic definitions if they have functional_tags field
    for mech in mechanics:
        name = mech["name"]
        mech_tags = mech.get("functional_tags", [])
        if mech_tags and name not in functional_tags:
            functional_tags[name] = mech_tags

    return cards, slots, mechanics, functional_tags


def analyze_set() -> BalanceAnalysisResult:
    """Run the full Phase 4A balance analysis on the active project.

    1. Load all inputs
    2. Run skeleton conformance checks
    3. Run set-wide coverage checks
    4. Aggregate issues and summary counts
    """
    from mtgai.runtime.active_project import require_active_project

    set_code = require_active_project().set_code
    cards, slots, mechanics, functional_tags = load_analysis_inputs()

    mechanic_names = {m["name"] for m in mechanics}
    all_issues = []

    # --- Conformance ---
    conformance, conformance_issues = analyze_conformance(cards, slots)
    all_issues.extend(conformance_issues)

    # --- Coverage ---
    color_coverage, coverage_issues = analyze_color_coverage(cards, mechanic_names, functional_tags)
    all_issues.extend(coverage_issues)

    mech_dist, mech_issues = analyze_mechanic_distribution(cards, mechanics)
    all_issues.extend(mech_issues)

    fixing_sources = analyze_mana_fixing(cards)

    color_balance, balance_issues = analyze_color_balance(cards)
    all_issues.extend(balance_issues)

    # --- Interactions ---
    interaction_flags, interaction_issues = analyze_interactions(cards, mechanics)
    all_issues.extend(interaction_issues)

    # --- Summary ---
    summary = {
        "PASS": 0,
        "WARN": 0,
        "FAIL": 0,
    }
    for issue in all_issues:
        summary[issue.severity.value] += 1

    # Count conformance passes
    matched_slots = sum(1 for r in conformance if r.matched)
    summary["PASS"] += matched_slots

    # Extract LLM analysis text from flags (logged separately)
    interaction_analysis = ""
    if interaction_flags:
        interaction_analysis = f"{len(interaction_flags)} interaction(s) flagged for review"

    return BalanceAnalysisResult(
        set_code=set_code,
        total_cards=len(cards),
        total_skeleton_slots=len(slots),
        conformance=conformance,
        color_coverage=color_coverage,
        mechanic_distribution=mech_dist,
        mana_fixing_sources=fixing_sources,
        color_balance=color_balance,
        interaction_flags=interaction_flags,
        interaction_analysis=interaction_analysis,
        issues=all_issues,
        summary=summary,
    )
