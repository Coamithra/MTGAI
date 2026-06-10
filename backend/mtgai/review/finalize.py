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
from collections.abc import Callable
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

# Runaway-safeguard: if the sanity check flags MORE than this fraction of the
# checked pool, the local model almost certainly misbehaved (looped / hallucinated
# defects), so we exclude NOTHING and surface a loud warning for manual review
# instead of auto-gutting the set. A real set has only a handful of genuinely
# broken cards; a flag rate above 5% is a red flag, not a verdict.
SANITY_CAP_FRACTION = 0.05


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


def _describe_load_failure(path: Path, exc: Exception) -> dict:
    """Best-effort identity for a card whose strict :class:`Card` load failed.

    The file can't be loaded as a ``Card`` (an unanticipated malformation past
    the model-boundary coercion, or unparseable JSON), so pull
    ``collector_number``/``name`` straight from the raw JSON when it parses,
    falling back to the filename. Used to record the skipped card in the finalize
    report (and, when the JSON parses, the Finalization tab — which renders the
    live raw JSON) so it can be hand-fixed instead of the stage aborting on it.
    """
    collector_number = ""
    name = ""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            collector_number = str(raw.get("collector_number") or "")
            name = str(raw.get("name") or "")
    except Exception:
        # Best-effort: if the JSON itself won't parse, the original exc already
        # describes the parse failure — fall back to the filename below.
        pass
    return {
        "file": path.name,
        "collector_number": collector_number,
        "name": name or path.stem,
        "error": str(exc),
    }


def finalize_card(
    card: Card,
    mechanics: list[dict],
    existing_cards: list[Card] | None = None,
) -> tuple[Card, list[str], list[ValidationError]]:
    """Finalize a single card: inject reminder text, validate, auto-fix.

    Returns:
        (finalized_card, applied_fixes, remaining_manual_errors)
    """
    from mtgai.validation.whitespace import prenormalize_card_whitespace

    # Step 0: Heal literal \n / \t escapes first — the reminder injector and
    # the line-based validators below all derive line structure from the text,
    # so they must see real newlines (findings are computed once, pre-fix).
    card, ws_fixes = prenormalize_card_whitespace(card)

    # Step 1: Reminder text injection
    card = finalize_reminder_text(card, mechanics)

    # Step 2: Full validation
    errors = validate_card(card, existing_cards)

    # Step 3: Auto-fix
    result = auto_fix_card(card, errors)

    return result.card, ws_fixes + result.applied_fixes, result.remaining_errors


def finalize_set(
    *,
    dry_run: bool = False,
    card_filter: str | None = None,
    on_sanity_start: Callable[[list[dict]], None] | None = None,
    on_sanity_card: Callable[[dict], None] | None = None,
    on_sanity_progress: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict:
    """Finalize all cards in the active project after AI review.

    Runs reminder-text injection + validation + auto-fix on every card, then a
    final LLM **sanity check** (``review/sanity_check.py``) that soft-excludes any
    card with an obvious unfixable defect (missing P/T, garbled text, bogus mana
    symbol) — capped at :data:`SANITY_CAP_FRACTION` of the pool (see
    ``_apply_sanity_check``). The ``on_sanity_*`` / ``should_cancel`` hooks stream
    the sanity pass into the Finalization tab + honour the Cancel button; they are
    no-ops for the CLI caller.

    **Per-card resilience:** a card that can't even be loaded as a :class:`Card`
    (an unanticipated malformation past the model-boundary coercion, or unparseable
    JSON) is **skipped + recorded** in ``summary["load_failures"]`` rather than
    raising and aborting the entire stage — the rest of the pool still finalizes.
    When the file's JSON parses (the common coercion-failure case), the tab also
    surfaces the skipped card (it renders the live raw JSON) for a hand fix; an
    unparseable file shows up only in the report.

    Returns a summary dict with counts and per-card details.
    """
    from mtgai.runtime.active_project import require_active_project

    set_code = require_active_project().set_code
    mechanics = _load_mechanics()
    card_paths = _card_files()

    if card_filter:
        card_paths = [p for p in card_paths if card_filter.upper() in p.stem.upper()]

    results: list[dict] = []
    finalized_cards: list[Card] = []
    load_failures: list[dict] = []
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
        try:
            card = load_card(path)
        except Exception as exc:
            # Defense-in-depth: a card that still fails to load/validate (an
            # UNANTICIPATED malformation past the model-boundary coercion, or
            # unparseable JSON) must not abort the whole stage. Skip it, record
            # it for the report so the Finalization tab surfaces it for a hand
            # fix, and finalize the rest.
            failure = _describe_load_failure(path, exc)
            load_failures.append(failure)
            logger.warning(
                "  %s: failed to load (%s) — skipped, flagged for manual review",
                failure["file"],
                failure["error"],
            )
            continue

        # Skip basic lands — nothing to finalize
        if _is_basic_land(card):
            logger.debug("Skipping basic land: %s", card.name)
            continue

        original_oracle = card.oracle_text

        finalized, fixes, manual_errors = finalize_card(card, mechanics)
        finalized_cards.append(finalized)

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

    # Final LLM sanity pass — soft-exclude any card with an obvious unfixable
    # defect (capped at SANITY_CAP_FRACTION; nondestructive + reversible).
    sanity = _apply_sanity_check(
        finalized_cards,
        set_dir,
        dry_run=dry_run,
        on_start=on_sanity_start,
        on_card=on_sanity_card,
        on_progress=on_sanity_progress,
        should_cancel=should_cancel,
    )

    summary = {
        "set_code": set_code,
        "timestamp": datetime.now(UTC).isoformat(),
        "dry_run": dry_run,
        # Successfully-finalized cards only — excludes basic lands and any
        # load_failures (skipped), so it can be < the number of files on disk.
        "total_cards": len(results),
        "cards_modified": cards_modified,
        "total_auto_fixes": total_fixes,
        "total_manual_errors": total_manual,
        "cards": results,
        # Cards that couldn't even be loaded as a Card (skipped, not aborted on);
        # surfaced in the report so the tab can flag them for a manual fix.
        "load_failures": load_failures,
        **sanity,
    }

    # Write report
    if not dry_run:
        _write_report(summary)
        _write_report_json(summary)

    logger.info(
        "Finalization complete: %d cards, %d modified, %d auto-fixes, %d MANUAL errors, "
        "%d sanity-excluded%s, %d load-failure(s)",
        len(results),
        cards_modified,
        total_fixes,
        total_manual,
        len(sanity.get("excluded_cards", [])),
        " (cap breached — none excluded)" if sanity.get("sanity_cap_breached") else "",
        len(load_failures),
    )

    return summary


def _apply_sanity_check(
    cards: list[Card],
    set_dir: Path,
    *,
    dry_run: bool,
    on_start: Callable[[list[dict]], None] | None,
    on_card: Callable[[dict], None] | None,
    on_progress: Callable[[str], None] | None,
    should_cancel: Callable[[], bool] | None,
) -> dict:
    """Run the LLM sanity check over the finalized pool and apply the result.

    Flags are applied as the reversible ``sanity_excluded`` marker (cleared again
    on a re-run when a card is no longer flagged), UNLESS the flag rate exceeds
    :data:`SANITY_CAP_FRACTION` — then nothing is excluded (prior flags are
    cleared) and a warning is surfaced. Returns the sanity portion of the
    finalize summary.
    """
    from mtgai.analysis.gate_common import filter_gate_cards
    from mtgai.review.sanity_check import check_sanity

    checkable = [c for c in filter_gate_cards(cards) if c.collector_number]
    checked = len(checkable)
    base = {
        "sanity_checked_count": checked,
        "sanity_flagged_count": 0,
        "sanity_cap_breached": False,
        "sanity_warning": None,
        "sanity_cost": 0.0,
        "sanity_analysis": "",
        "excluded_cards": [],
    }
    # Dry-run is a side-effect-free preview — don't spend LLM calls on the sanity
    # pass (and nothing would be persisted anyway).
    if checked == 0 or dry_run:
        return base

    flagged, analysis, cost = check_sanity(
        cards,
        on_start=on_start,
        on_card=on_card,
        on_progress=on_progress,
        should_cancel=should_cancel,
    )

    breached = (len(flagged) / checked) > SANITY_CAP_FRACTION
    effective = {} if breached else flagged

    excluded: list[dict] = []
    for card in cards:
        cn = card.collector_number
        if not cn:
            continue
        want = cn in effective
        reason = effective.get(cn) if want else None
        cur_reason = card.sanity_exclusion_reason or None
        changed = bool(card.sanity_excluded) != want or cur_reason != reason
        if changed and not dry_run:
            save_card(
                card.model_copy(
                    update={"sanity_excluded": want, "sanity_exclusion_reason": reason}
                ),
                set_dir=set_dir,
            )
        if want:
            excluded.append({"collector_number": cn, "name": card.name, "reason": reason})

    warning = None
    if breached:
        pct = int(SANITY_CAP_FRACTION * 100)
        warning = (
            f"Sanity check flagged {len(flagged)} of {checked} cards "
            f"(over the {pct}% safety cap) — none were excluded automatically. "
            "The model may have misbehaved; review the flagged cards manually."
        )
        logger.warning(warning)

    return {
        "sanity_checked_count": checked,
        "sanity_flagged_count": len(flagged),
        "sanity_cap_breached": breached,
        "sanity_warning": warning,
        "sanity_cost": cost,
        "sanity_analysis": analysis,
        "excluded_cards": excluded,
    }


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
        f"**Sanity-excluded cards:** {len(summary.get('excluded_cards') or [])}",
        f"**Cards that failed to load:** {len(summary.get('load_failures') or [])}",
        "",
    ]

    # Load-failure section — cards that couldn't be parsed/validated as a Card and
    # were skipped (the stage no longer aborts on them); listed so the human knows
    # to hand-fix the raw JSON in the Finalization tab.
    load_failures = summary.get("load_failures") or []
    if load_failures:
        lines.append("## Cards That Failed to Load (Skipped)")
        lines.append("")
        lines.append(
            "These cards could not be loaded/validated and were skipped — fix the raw "
            "JSON by hand in the Finalization tab:"
        )
        lines.append("")
        for f in load_failures:
            cn = f.get("collector_number") or "?"
            name = f.get("name") or f.get("file") or "?"
            lines.append(f"- **{cn} — {name}** (`{f.get('file')}`): {f.get('error') or ''}")
        lines.append("")

    # Sanity-check section — the cards soft-excluded for an obvious defect (or the
    # cap-breach warning when the model flagged too many to trust).
    if summary.get("sanity_cap_breached"):
        lines.append("## Sanity Check — Cap Breached")
        lines.append("")
        lines.append(summary.get("sanity_warning") or "Too many cards flagged; none excluded.")
        lines.append("")
    elif summary.get("excluded_cards"):
        lines.append("## Sanity Check — Excluded Cards")
        lines.append("")
        lines.append("These cards failed the final sanity check and were excluded from the set:")
        lines.append("")
        for c in summary["excluded_cards"]:
            lines.append(f"- **{c['collector_number']} — {c['name']}**: {c.get('reason') or ''}")
        lines.append("")

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
