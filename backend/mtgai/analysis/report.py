"""Report generation -- Markdown and JSON output for balance analysis results."""

from __future__ import annotations

from pathlib import Path

from mtgai.analysis.models import AnalysisSeverity, BalanceAnalysisResult


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


def _severity_icon(severity: AnalysisSeverity) -> str:
    if severity == AnalysisSeverity.PASS:
        return "PASS"
    if severity == AnalysisSeverity.WARN:
        return "WARN"
    return "FAIL"


def generate_markdown_report(result: BalanceAnalysisResult) -> str:
    """Generate a human-readable Markdown balance report."""
    lines: list[str] = []

    lines.append(f"# Balance Analysis Report: {result.set_code}")
    lines.append("")
    lines.append(
        f"**Cards**: {result.total_cards} | "
        f"**Skeleton slots**: {result.total_skeleton_slots} | "
        f"**PASS**: {result.summary.get('PASS', 0)} | "
        f"**WARN**: {result.summary.get('WARN', 0)} | "
        f"**FAIL**: {result.summary.get('FAIL', 0)}"
    )
    lines.append("")

    # --- Skeleton Conformance ---
    lines.append("## Skeleton Conformance")
    lines.append("")

    matched = sum(1 for r in result.conformance if r.matched)
    total = len(result.conformance)
    lines.append(f"**{matched}/{total}** slots matched perfectly.")
    lines.append("")

    mismatches = [r for r in result.conformance if not r.matched]
    if mismatches:
        lines.append("| Slot | Card | Issues |")
        lines.append("|------|------|--------|")
        for r in mismatches:
            card_name = r.card_name or "(missing)"
            issue_strs = [f"[{_severity_icon(i.severity)}] {i.message}" for i in r.issues]
            lines.append(f"| {r.slot_id} | {card_name} | {'; '.join(issue_strs)} |")
        lines.append("")

    # --- Color Coverage ---
    lines.append("## Color Coverage")
    lines.append("")

    for cc in result.color_coverage:
        lines.append(f"### {cc.color}")
        lines.append(
            f"Cards: {cc.total_cards} | "
            f"Creatures: {cc.total_creatures} | "
            f"Removal: {cc.removal_count} | "
            f"Card Advantage: {cc.card_advantage_count}"
        )
        lines.append("")

        if cc.creature_cmc_buckets:
            lines.append("**Creature CMC curve:**")
            lines.append("")
            lines.append("| CMC | Count |")
            lines.append("|-----|-------|")
            for cmc in sorted(cc.creature_cmc_buckets.keys()):
                label = f"{cmc}+" if cmc == 6 else str(cmc)
                lines.append(f"| {label} | {cc.creature_cmc_buckets[cmc]} |")
            lines.append("")

        if cc.creature_cmc_gaps:
            lines.append(f"**CMC gaps:** {', '.join(str(g) for g in cc.creature_cmc_gaps)}")
            lines.append("")

        if cc.creature_sizes:
            lines.append("**Size distribution:**")
            for entry in cc.creature_sizes:
                lines.append(f"- {entry.weight_class}: {entry.count}")
            lines.append("")

        if cc.removal_cards:
            lines.append(f"**Removal:** {', '.join(cc.removal_cards)}")
            lines.append("")

        if cc.card_advantage_cards:
            lines.append(f"**Card advantage:** {', '.join(cc.card_advantage_cards)}")
            lines.append("")

    # --- Mechanic Distribution ---
    lines.append("## Mechanic Distribution")
    lines.append("")
    lines.append("| Mechanic | Planned | Actual | Status |")
    lines.append("|----------|---------|--------|--------|")
    for md in result.mechanic_distribution:
        diff = md.total_actual - md.total_planned
        if abs(diff) <= 1:
            status = "PASS"
        elif md.total_actual > md.total_planned:
            status = f"WARN (+{diff})"
        else:
            status = f"WARN ({diff})"
        lines.append(f"| {md.mechanic_name} | {md.total_planned} | {md.total_actual} | {status} |")
    lines.append("")

    # Per-mechanic rarity breakdown
    for md in result.mechanic_distribution:
        if md.actual:
            lines.append(f"**{md.mechanic_name}** rarity breakdown:")
            lines.append("| Rarity | Planned | Actual |")
            lines.append("|--------|---------|--------|")
            all_rarities = sorted(set(list(md.planned.keys()) + list(md.actual.keys())))
            for r in all_rarities:
                lines.append(f"| {r} | {md.planned.get(r, 0)} | {md.actual.get(r, 0)} |")
            lines.append("")

    # --- Mana Fixing ---
    lines.append("## Mana Fixing")
    lines.append("")
    if result.mana_fixing_sources:
        lines.append(f"**{len(result.mana_fixing_sources)} sources found:**")
        for name in result.mana_fixing_sources:
            lines.append(f"- {name}")
    else:
        lines.append("**No mana fixing sources detected.**")
    lines.append("")

    # --- Color Balance ---
    lines.append("## Color Balance (mono-color cards)")
    lines.append("")
    lines.append("| Color | Count |")
    lines.append("|-------|-------|")
    for color in ["W", "U", "B", "R", "G"]:
        count = result.color_balance.get(color, 0)
        lines.append(f"| {color} | {count} |")
    lines.append("")

    # --- Interaction Analysis ---
    lines.append("## Interaction Analysis")
    lines.append("")
    if result.interaction_flags:
        lines.append(
            f"**{len(result.interaction_flags)} potential degenerate interaction(s) flagged:**"
        )
        lines.append("")
        for flag in result.interaction_flags:
            severity = "FAIL" if flag.severity == "FAIL" else "WARN"
            lines.append(f"### [{severity}] {flag.interaction_type}")
            lines.append(f"**Cards:** {', '.join(flag.cards_involved)}")
            lines.append(f"**Description:** {flag.description}")
            lines.append(f"**Enabler:** {flag.enabler_card} ({flag.enabler_slot_id})")
            lines.append(f"**Why enabler:** {flag.why_enabler}")
            lines.append(f"**Replacement constraint:** {flag.replacement_constraint}")
            lines.append("")
    else:
        lines.append("No degenerate interactions found.")
        lines.append("")

    # --- All Issues ---
    lines.append("## All Issues")
    lines.append("")
    if result.issues:
        lines.append("| Severity | Check | Message |")
        lines.append("|----------|-------|---------|")
        for issue in result.issues:
            lines.append(f"| {_severity_icon(issue.severity)} | {issue.check} | {issue.message} |")
    else:
        lines.append("No issues found.")
    lines.append("")

    return "\n".join(lines)


def save_report(
    result: BalanceAnalysisResult,
    set_code: str,
) -> tuple[Path, Path]:
    """Save both JSON and Markdown reports.

    Returns (json_path, md_path).
    """
    from mtgai.io.asset_paths import set_artifact_dir

    sdir = set_artifact_dir() / "reports"
    sdir.mkdir(parents=True, exist_ok=True)

    json_path = sdir / "balance-analysis.json"
    json_path.write_text(
        result.model_dump_json(indent=2),
        encoding="utf-8",
    )

    md_path = sdir / "balance-report.md"
    md_path.write_text(
        generate_markdown_report(result),
        encoding="utf-8",
    )

    return json_path, md_path
