"""Post-review finalization — inject reminder text, re-validate, auto-fix, save.

Runs after the AI review pipeline completes.  For every card in the set:

1. Strip any existing inline reminder text (old LLM-generated)
2. Inject fresh reminder text from mechanic definitions
3. Run the full validation suite
4. Auto-fix any AUTO errors
5. Save the card back to disk
6. Collect remaining MANUAL errors for human review

Produces a markdown report in the active project's ``reports/finalize-report.md``
listing all MANUAL errors the human reviewer should check.

Usage:
    python -m mtgai.review finalize [--dry-run]
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from mtgai.generation.reminder_injector import finalize_reminder_text
from mtgai.io.atomic import atomic_write_text
from mtgai.io.card_io import load_card, save_card
from mtgai.models.card import Card
from mtgai.validation import (
    ValidationError,
    auto_fix_card,
    validate_card,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core finalization logic
# ---------------------------------------------------------------------------


def _load_mechanics() -> list[dict]:
    from mtgai.io.asset_paths import set_artifact_dir

    path = set_artifact_dir() / "mechanics" / "approved.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _card_files() -> list[Path]:
    from mtgai.io.asset_paths import set_artifact_dir

    cards_dir = set_artifact_dir() / "cards"
    return sorted(cards_dir.glob("*.json"))


def _is_basic_land(card: Card) -> bool:
    return "Basic" in card.supertypes and "Land" in card.card_types


def finalize_card(
    card: Card,
    mechanics: list[dict],
    existing_cards: list[Card] | None = None,
) -> tuple[Card, list[str], list[ValidationError]]:
    """Finalize a single card: inject reminder text, validate, auto-fix.

    Returns:
        (finalized_card, applied_fixes, remaining_manual_errors)
    """
    # Step 1: Reminder text injection
    card = finalize_reminder_text(card, mechanics)

    # Step 2: Full validation
    errors = validate_card(card, existing_cards)

    # Step 3: Auto-fix
    result = auto_fix_card(card, errors)

    return result.card, result.applied_fixes, result.remaining_errors


def finalize_set(
    *,
    dry_run: bool = False,
    card_filter: str | None = None,
) -> dict:
    """Finalize all cards in the active project after AI review.

    Returns a summary dict with counts and per-card details.
    """
    from mtgai.runtime.active_project import require_active_project

    set_code = require_active_project().set_code
    mechanics = _load_mechanics()
    card_paths = _card_files()

    if card_filter:
        card_paths = [p for p in card_paths if card_filter.upper() in p.stem.upper()]

    results: list[dict] = []
    total_fixes = 0
    total_manual = 0
    cards_modified = 0

    logger.info(
        "Finalizing %d card(s) for set %s%s",
        len(card_paths),
        set_code,
        " (dry run)" if dry_run else "",
    )

    # Hoist the artifact-dir resolution outside the loop — it's constant
    # for the whole call and the helper triggers a settings.toml read.
    from mtgai.io.asset_paths import set_artifact_dir

    set_dir = set_artifact_dir()

    for path in card_paths:
        card = load_card(path)

        # Skip basic lands — nothing to finalize
        if _is_basic_land(card):
            logger.debug("Skipping basic land: %s", card.name)
            continue

        original_oracle = card.oracle_text

        finalized, fixes, manual_errors = finalize_card(card, mechanics)

        modified = finalized.oracle_text != original_oracle or len(fixes) > 0

        entry = {
            "collector_number": card.collector_number,
            "name": card.name,
            "fixes_applied": fixes,
            # The pre-finalize oracle text, kept only when finalize actually
            # rewrote it, so the Finalization tab can show a before/after diff of
            # what the stage changed (reminder injection + auto-fixes).
            "original_oracle_text": (
                original_oracle if finalized.oracle_text != original_oracle else None
            ),
            "manual_errors": [
                {
                    "code": e.error_code,
                    "field": e.field,
                    "message": e.message,
                    "suggestion": e.suggestion,
                }
                for e in manual_errors
            ],
            "modified": modified,
        }
        results.append(entry)
        total_fixes += len(fixes)
        total_manual += len(manual_errors)

        if modified:
            cards_modified += 1

        if fixes:
            logger.info(
                "  %s (%s): %d auto-fix(es) applied",
                card.collector_number,
                card.name,
                len(fixes),
            )
            for fix in fixes:
                logger.info("    - %s", fix)

        if manual_errors:
            logger.warning(
                "  %s (%s): %d MANUAL error(s) for human review",
                card.collector_number,
                card.name,
                len(manual_errors),
            )
            for err in manual_errors:
                logger.warning("    - [%s] %s", err.error_code, err.message)

        if not dry_run and modified:
            save_card(finalized, set_dir=set_dir)

    summary = {
        "set_code": set_code,
        "timestamp": datetime.now(UTC).isoformat(),
        "dry_run": dry_run,
        "total_cards": len(results),
        "cards_modified": cards_modified,
        "total_auto_fixes": total_fixes,
        "total_manual_errors": total_manual,
        "cards": results,
    }

    # Write report
    if not dry_run:
        _write_report(summary)
        _write_report_json(summary)

    logger.info(
        "Finalization complete: %d cards, %d modified, %d auto-fixes, %d MANUAL errors",
        len(results),
        cards_modified,
        total_fixes,
        total_manual,
    )

    return summary


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _write_report(summary: dict) -> Path:
    """Write a markdown finalization report for human review."""
    from mtgai.io.asset_paths import set_artifact_dir

    reports_dir = set_artifact_dir() / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "finalize-report.md"

    lines: list[str] = [
        "# Post-Review Finalization Report",
        "",
        f"**Set:** {summary['set_code']}",
        f"**Timestamp:** {summary['timestamp']}",
        f"**Cards processed:** {summary['total_cards']}",
        f"**Cards modified:** {summary['cards_modified']}",
        f"**Auto-fixes applied:** {summary['total_auto_fixes']}",
        f"**MANUAL errors for review:** {summary['total_manual_errors']}",
        "",
    ]

    # Auto-fixes section
    fix_cards = [c for c in summary["cards"] if c["fixes_applied"]]
    if fix_cards:
        lines.append("## Auto-Fixes Applied")
        lines.append("")
        for card in fix_cards:
            lines.append(f"### {card['collector_number']} — {card['name']}")
            for fix in card["fixes_applied"]:
                lines.append(f"- {fix}")
            lines.append("")

    # MANUAL errors section — the key part for human reviewers
    manual_cards = [c for c in summary["cards"] if c["manual_errors"]]
    if manual_cards:
        lines.append("## MANUAL Errors (Human Review Required)")
        lines.append("")
        for card in manual_cards:
            lines.append(f"### {card['collector_number']} — {card['name']}")
            for err in card["manual_errors"]:
                code = err.get("code", "unknown")
                msg = err["message"]
                sug = err.get("suggestion")
                line = f"- **[{code}]** {msg}"
                if sug:
                    line += f"\n  - *Suggestion:* {sug}"
                lines.append(line)
            lines.append("")
    else:
        lines.append("## No MANUAL Errors Found")
        lines.append("")
        lines.append("All cards passed validation after auto-fix.")
        lines.append("")

    report_text = "\n".join(lines)
    atomic_write_text(report_path, report_text)
    logger.info("Report written to %s", report_path)
    return report_path


def _write_report_json(summary: dict) -> Path:
    """Write the finalize summary as JSON for the Finalization wizard tab.

    The markdown report is for humans reading a file; the JSON sidecar is the
    durable source the ``/api/wizard/finalize/state`` endpoint reads back so the
    tab can badge auto-edited cards and show the before/after of what finalize
    changed without re-running the stage.
    """
    from mtgai.io.asset_paths import set_artifact_dir

    reports_dir = set_artifact_dir() / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "finalize-report.json"
    atomic_write_text(report_path, json.dumps(summary, indent=2, ensure_ascii=False))
    logger.debug("Finalize JSON report written to %s", report_path)
    return report_path
