"""Review decisions model and dispatch logic.

Captures human review decisions (ok / remake / art_redo / manual_tweak) for each
card, persists them as JSON, and dispatches queue files that downstream pipelines
(card generator, art pipeline) can read.

Usage:
    from mtgai.review.decisions import (
        ReviewDecisions, CardDecision, ReviewAction,
        save_decisions, load_decisions, dispatch_decisions,
    )
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _project_root() -> Path:
    """Return the project root (parent of backend/)."""
    return Path(__file__).resolve().parent.parent.parent.parent


def _set_dir(set_code: str) -> Path:
    """Return the artifact directory for ``set_code``.

    Routes through :func:`set_artifact_dir` so reads honour the
    project's configured ``asset_folder``.
    """
    from mtgai.io.asset_paths import set_artifact_dir

    return set_artifact_dir(set_code)


# ---------------------------------------------------------------------------
# Enums & Models
# ---------------------------------------------------------------------------


class ReviewAction(StrEnum):
    OK = "ok"
    REMAKE = "remake"
    ART_REDO = "art_redo"
    MANUAL_TWEAK = "manual_tweak"


class CardDecision(BaseModel):
    """Decision for a single card."""

    action: ReviewAction = ReviewAction.OK
    note: str = ""


class ReviewDecisions(BaseModel):
    """All decisions from a review round."""

    set_code: str
    review_round: int = 1
    timestamp: datetime
    decisions: dict[str, CardDecision]  # keyed by collector_number

    @property
    def summary(self) -> dict[str, int]:
        """Count decisions by action type."""
        counts: dict[str, int] = {}
        for d in self.decisions.values():
            counts[d.action.value] = counts.get(d.action.value, 0) + 1
        return counts

    @property
    def remakes(self) -> list[str]:
        """Collector numbers of cards marked for remake."""
        return [cn for cn, d in self.decisions.items() if d.action == ReviewAction.REMAKE]

    @property
    def art_redos(self) -> list[str]:
        """Collector numbers of cards marked for art redo."""
        return [cn for cn, d in self.decisions.items() if d.action == ReviewAction.ART_REDO]

    @property
    def manual_tweaks(self) -> list[str]:
        """Collector numbers of cards marked for manual tweak."""
        return [cn for cn, d in self.decisions.items() if d.action == ReviewAction.MANUAL_TWEAK]


# ---------------------------------------------------------------------------
# Save / Load
# ---------------------------------------------------------------------------


def save_decisions(
    decisions: ReviewDecisions,
    set_code: str,
    *,
    base_dir: Path | None = None,
) -> Path:
    """Save review decisions to output/sets/<code>/review-decisions.json.

    Also saves the round-specific file: review-decisions-round-N.json
    (so previous rounds are preserved as audit trail).

    Args:
        decisions: The decisions to save.
        set_code: Set code (e.g. "ASD").
        base_dir: Override the set directory (useful for testing).

    Returns:
        Path to the saved latest decisions file.
    """
    out_dir = base_dir if base_dir is not None else _set_dir(set_code)
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = decisions.model_dump_json(indent=2)

    # Always write the latest file
    latest_path = out_dir / "review-decisions.json"
    latest_path.write_text(payload, encoding="utf-8")
    logger.info("Saved review decisions to %s", latest_path)

    # Also write the round-specific file for audit trail
    round_path = out_dir / f"review-decisions-round-{decisions.review_round}.json"
    round_path.write_text(payload, encoding="utf-8")
    logger.info("Saved round %d decisions to %s", decisions.review_round, round_path)

    return latest_path


def load_decisions(
    set_code: str,
    *,
    base_dir: Path | None = None,
) -> ReviewDecisions | None:
    """Load the latest review decisions. Returns None if no decisions file exists."""
    out_dir = base_dir if base_dir is not None else _set_dir(set_code)
    path = out_dir / "review-decisions.json"
    if not path.exists():
        return None
    return ReviewDecisions.model_validate_json(path.read_text(encoding="utf-8"))


def get_review_round(
    set_code: str,
    *,
    base_dir: Path | None = None,
) -> int:
    """Get the next review round number (1 if no previous rounds)."""
    out_dir = base_dir if base_dir is not None else _set_dir(set_code)
    existing = sorted(out_dir.glob("review-decisions-round-*.json"))
    if not existing:
        return 1
    # Extract the highest round number from existing files
    max_round = 0
    for p in existing:
        # Filename: review-decisions-round-N.json
        stem = p.stem  # review-decisions-round-N
        try:
            n = int(stem.rsplit("-", 1)[1])
            max_round = max(max_round, n)
        except (ValueError, IndexError):
            continue
    return max_round + 1


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


class DispatchResult(BaseModel):
    """Result of dispatching review decisions."""

    remake_queue_path: Path | None = None
    remake_count: int = 0
    art_redo_queue_path: Path | None = None
    art_redo_count: int = 0
    manual_tweak_paths: list[Path] = []
    ok_count: int = 0

    model_config = {"arbitrary_types_allowed": True}


def _find_card_json(cards_dir: Path, collector_number: str) -> Path | None:
    """Find the card JSON file for a collector number.

    Globs for <collector_number>_*.json in the cards directory.
    Returns None if no match found.
    """
    matches = list(cards_dir.glob(f"{collector_number}_*.json"))
    if not matches:
        return None
    # Should be exactly one match; take the first
    return matches[0]


def dispatch_decisions(
    decisions: ReviewDecisions,
    *,
    base_dir: Path | None = None,
) -> DispatchResult:
    """Process review decisions and write queue files for pipelines.

    1. Write remake-queue.json with collector numbers for full remake.
    2. Write art-redo-queue.json with collector numbers for art redo.
    3. Return list of manual tweak file paths (card JSON paths).

    Does NOT actually run the pipelines — just writes the queue files
    that the pipelines will read.

    Args:
        decisions: The review decisions to dispatch.
        base_dir: Override the set directory (useful for testing).

    Returns:
        DispatchResult with paths and counts.
    """
    set_dir = base_dir if base_dir is not None else _set_dir(decisions.set_code)
    set_dir.mkdir(parents=True, exist_ok=True)
    cards_dir = set_dir / "cards"

    result = DispatchResult()

    # Count OKs
    result.ok_count = sum(1 for d in decisions.decisions.values() if d.action == ReviewAction.OK)

    # Remakes
    remakes = decisions.remakes
    if remakes:
        queue = {
            "cards": remakes,
            "review_round": decisions.review_round,
            "timestamp": decisions.timestamp.isoformat(),
        }
        remake_path = set_dir / "remake-queue.json"
        remake_path.write_text(json.dumps(queue, indent=2), encoding="utf-8")
        result.remake_queue_path = remake_path
        result.remake_count = len(remakes)
        logger.info("Wrote remake queue: %d card(s) -> %s", len(remakes), remake_path)

    # Art redos
    art_redos = decisions.art_redos
    if art_redos:
        queue = {
            "cards": art_redos,
            "review_round": decisions.review_round,
            "timestamp": decisions.timestamp.isoformat(),
        }
        art_redo_path = set_dir / "art-redo-queue.json"
        art_redo_path.write_text(json.dumps(queue, indent=2), encoding="utf-8")
        result.art_redo_queue_path = art_redo_path
        result.art_redo_count = len(art_redos)
        logger.info("Wrote art-redo queue: %d card(s) -> %s", len(art_redos), art_redo_path)

    # Manual tweaks — resolve to actual card JSON paths
    manual_tweaks = decisions.manual_tweaks
    for cn in manual_tweaks:
        card_path = _find_card_json(cards_dir, cn)
        if card_path is not None:
            result.manual_tweak_paths.append(card_path)
            logger.info("Manual tweak: %s -> %s", cn, card_path)
        else:
            logger.warning("No card JSON found for collector number %s in %s", cn, cards_dir)

    logger.info(
        "Dispatch complete: %d ok, %d remakes, %d art redos, %d manual tweaks",
        result.ok_count,
        result.remake_count,
        result.art_redo_count,
        len(result.manual_tweak_paths),
    )

    return result


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------


class CardProgress(BaseModel):
    """Progress status for a single card in the pipeline."""

    collector_number: str
    action: ReviewAction
    status: str = "pending"  # pending, in_progress, completed, error
    note: str = ""
    error_message: str | None = None


class ReviewProgress(BaseModel):
    """Overall progress for a review round."""

    set_code: str
    review_round: int
    cards: dict[str, CardProgress]  # keyed by collector_number

    @property
    def summary(self) -> dict[str, int]:
        """Count by status."""
        counts: dict[str, int] = {}
        for cp in self.cards.values():
            counts[cp.status] = counts.get(cp.status, 0) + 1
        return counts

    @property
    def all_complete(self) -> bool:
        """True if every card is completed or errored (nothing pending/in_progress)."""
        return all(cp.status in ("completed", "error") for cp in self.cards.values())


def init_progress(decisions: ReviewDecisions) -> ReviewProgress:
    """Create initial progress from decisions (all non-OK cards are pending)."""
    cards: dict[str, CardProgress] = {}
    for cn, d in decisions.decisions.items():
        if d.action == ReviewAction.OK:
            continue
        cards[cn] = CardProgress(
            collector_number=cn,
            action=d.action,
            note=d.note,
        )
    return ReviewProgress(
        set_code=decisions.set_code,
        review_round=decisions.review_round,
        cards=cards,
    )


def save_progress(
    progress: ReviewProgress,
    set_code: str,
    *,
    base_dir: Path | None = None,
) -> Path:
    """Save progress to output/sets/<code>/review-progress.json."""
    out_dir = base_dir if base_dir is not None else _set_dir(set_code)
    out_dir.mkdir(parents=True, exist_ok=True)

    path = out_dir / "review-progress.json"
    path.write_text(progress.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Saved review progress to %s", path)
    return path


def load_progress(
    set_code: str,
    *,
    base_dir: Path | None = None,
) -> ReviewProgress | None:
    """Load current progress. Returns None if no progress file."""
    out_dir = base_dir if base_dir is not None else _set_dir(set_code)
    path = out_dir / "review-progress.json"
    if not path.exists():
        return None
    return ReviewProgress.model_validate_json(path.read_text(encoding="utf-8"))
