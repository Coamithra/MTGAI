"""Tests for review decisions model, save/load, dispatch, and progress tracking."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from mtgai.review.decisions import (
    CardDecision,
    CardProgress,
    ReviewAction,
    ReviewDecisions,
    dispatch_decisions,
    get_review_round,
    init_progress,
    load_decisions,
    load_progress,
    save_decisions,
    save_progress,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 21, 14, 30, 0, tzinfo=UTC)


def _make_decisions(**overrides) -> ReviewDecisions:
    """Build a ReviewDecisions with sensible defaults."""
    defaults: dict = {
        "set_code": "TST",
        "review_round": 1,
        "timestamp": _NOW,
        "decisions": {
            "W-C-01": CardDecision(action=ReviewAction.OK),
            "B-R-02": CardDecision(action=ReviewAction.REMAKE, note="Too weak"),
            "U-R-01": CardDecision(action=ReviewAction.REMAKE, note="Boring"),
            "R-U-03": CardDecision(action=ReviewAction.ART_REDO, note="Bad hands"),
            "W-U-02": CardDecision(action=ReviewAction.ART_REDO),
            "G-C-03": CardDecision(action=ReviewAction.MANUAL_TWEAK, note="Fix mana cost"),
        },
    }
    defaults.update(overrides)
    return ReviewDecisions(**defaults)


def _create_card_json(cards_dir: Path, collector_number: str, name: str) -> Path:
    """Write a minimal card JSON fixture and return the path."""
    slug = name.lower().replace(" ", "_")
    path = cards_dir / f"{collector_number}_{slug}.json"
    data = {
        "name": name,
        "collector_number": collector_number,
        "set_code": "TST",
        "mana_cost": "{1}{W}",
        "cmc": 2.0,
        "type_line": "Creature — Human",
        "oracle_text": "Lifelink",
        "rarity": "common",
        "colors": ["W"],
        "color_identity": ["W"],
        "card_types": ["Creature"],
        "subtypes": ["Human"],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


# ===========================================================================
# ReviewDecisions model tests
# ===========================================================================


class TestReviewDecisionsModel:
    def test_creation(self):
        d = _make_decisions()
        assert d.set_code == "TST"
        assert d.review_round == 1
        assert len(d.decisions) == 6

    def test_summary_counts(self):
        d = _make_decisions()
        s = d.summary
        assert s["ok"] == 1
        assert s["remake"] == 2
        assert s["art_redo"] == 2
        assert s["manual_tweak"] == 1

    def test_remakes_list(self):
        d = _make_decisions()
        assert sorted(d.remakes) == ["B-R-02", "U-R-01"]

    def test_art_redos_list(self):
        d = _make_decisions()
        assert sorted(d.art_redos) == ["R-U-03", "W-U-02"]

    def test_manual_tweaks_list(self):
        d = _make_decisions()
        assert d.manual_tweaks == ["G-C-03"]

    def test_all_ok(self):
        d = _make_decisions(
            decisions={
                "W-C-01": CardDecision(action=ReviewAction.OK),
                "B-C-01": CardDecision(action=ReviewAction.OK),
            }
        )
        assert d.summary == {"ok": 2}
        assert d.remakes == []
        assert d.art_redos == []
        assert d.manual_tweaks == []

    def test_empty_decisions(self):
        d = _make_decisions(decisions={})
        assert d.summary == {}
        assert d.remakes == []

    def test_card_decision_defaults(self):
        cd = CardDecision()
        assert cd.action == ReviewAction.OK
        assert cd.note == ""


# ===========================================================================
# Save / Load round-trip tests
# ===========================================================================


class TestSaveLoad:
    def test_round_trip(self, tmp_path: Path):
        d = _make_decisions()
        save_decisions(d, "TST", base_dir=tmp_path)
        loaded = load_decisions("TST", base_dir=tmp_path)
        assert loaded is not None
        assert loaded.set_code == d.set_code
        assert loaded.review_round == d.review_round
        assert loaded.decisions.keys() == d.decisions.keys()
        for cn in d.decisions:
            assert loaded.decisions[cn].action == d.decisions[cn].action
            assert loaded.decisions[cn].note == d.decisions[cn].note

    def test_saves_latest_and_round_files(self, tmp_path: Path):
        d = _make_decisions()
        save_decisions(d, "TST", base_dir=tmp_path)
        assert (tmp_path / "review-decisions.json").exists()
        assert (tmp_path / "review-decisions-round-1.json").exists()

    def test_load_returns_none_when_missing(self, tmp_path: Path):
        assert load_decisions("TST", base_dir=tmp_path) is None

    def test_multiple_rounds_preserved(self, tmp_path: Path):
        d1 = _make_decisions(review_round=1)
        d2 = _make_decisions(review_round=2)
        save_decisions(d1, "TST", base_dir=tmp_path)
        save_decisions(d2, "TST", base_dir=tmp_path)
        # Latest should be round 2
        loaded = load_decisions("TST", base_dir=tmp_path)
        assert loaded is not None
        assert loaded.review_round == 2
        # But round 1 file still exists
        assert (tmp_path / "review-decisions-round-1.json").exists()
        assert (tmp_path / "review-decisions-round-2.json").exists()


# ===========================================================================
# Review round number tests
# ===========================================================================


class TestGetReviewRound:
    def test_first_round(self, tmp_path: Path):
        assert get_review_round("TST", base_dir=tmp_path) == 1

    def test_increments_after_round_1(self, tmp_path: Path):
        d = _make_decisions(review_round=1)
        save_decisions(d, "TST", base_dir=tmp_path)
        assert get_review_round("TST", base_dir=tmp_path) == 2

    def test_increments_after_round_3(self, tmp_path: Path):
        for i in range(1, 4):
            d = _make_decisions(review_round=i)
            save_decisions(d, "TST", base_dir=tmp_path)
        assert get_review_round("TST", base_dir=tmp_path) == 4


# ===========================================================================
# Dispatch tests
# ===========================================================================


class TestDispatch:
    def test_creates_remake_queue(self, tmp_path: Path):
        d = _make_decisions()
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        result = dispatch_decisions(d, base_dir=tmp_path)
        assert result.remake_count == 2
        assert result.remake_queue_path is not None
        assert result.remake_queue_path.exists()
        queue = json.loads(result.remake_queue_path.read_text(encoding="utf-8"))
        assert sorted(queue["cards"]) == ["B-R-02", "U-R-01"]
        assert queue["review_round"] == 1

    def test_creates_art_redo_queue(self, tmp_path: Path):
        d = _make_decisions()
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        result = dispatch_decisions(d, base_dir=tmp_path)
        assert result.art_redo_count == 2
        assert result.art_redo_queue_path is not None
        assert result.art_redo_queue_path.exists()
        queue = json.loads(result.art_redo_queue_path.read_text(encoding="utf-8"))
        assert sorted(queue["cards"]) == ["R-U-03", "W-U-02"]

    def test_manual_tweak_finds_card_json(self, tmp_path: Path):
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        card_path = _create_card_json(cards_dir, "G-C-03", "Forest Dweller")
        d = _make_decisions()
        result = dispatch_decisions(d, base_dir=tmp_path)
        assert len(result.manual_tweak_paths) == 1
        assert result.manual_tweak_paths[0] == card_path

    def test_manual_tweak_missing_card_json(self, tmp_path: Path):
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        # No card JSON for G-C-03
        d = _make_decisions()
        result = dispatch_decisions(d, base_dir=tmp_path)
        assert len(result.manual_tweak_paths) == 0

    def test_ok_count(self, tmp_path: Path):
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        d = _make_decisions()
        result = dispatch_decisions(d, base_dir=tmp_path)
        assert result.ok_count == 1

    def test_all_ok_no_queues(self, tmp_path: Path):
        """When all decisions are OK, no queue files should be written."""
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        d = _make_decisions(
            decisions={
                "W-C-01": CardDecision(action=ReviewAction.OK),
                "B-C-01": CardDecision(action=ReviewAction.OK),
            }
        )
        result = dispatch_decisions(d, base_dir=tmp_path)
        assert result.ok_count == 2
        assert result.remake_count == 0
        assert result.art_redo_count == 0
        assert result.remake_queue_path is None
        assert result.art_redo_queue_path is None
        assert result.manual_tweak_paths == []
        # No queue files should exist
        assert not (tmp_path / "remake-queue.json").exists()
        assert not (tmp_path / "art-redo-queue.json").exists()

    def test_empty_decisions_no_queues(self, tmp_path: Path):
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        d = _make_decisions(decisions={})
        result = dispatch_decisions(d, base_dir=tmp_path)
        assert result.ok_count == 0
        assert result.remake_count == 0
        assert result.art_redo_count == 0

    def test_queue_timestamp_format(self, tmp_path: Path):
        """Queue files contain ISO-format timestamp."""
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        d = _make_decisions()
        dispatch_decisions(d, base_dir=tmp_path)
        queue = json.loads(
            (tmp_path / "remake-queue.json").read_text(encoding="utf-8")
        )
        # Should be parseable as ISO datetime
        parsed = datetime.fromisoformat(queue["timestamp"])
        assert parsed.year == 2026


# ===========================================================================
# Progress tracking tests
# ===========================================================================


class TestProgressTracking:
    def test_init_from_decisions(self):
        d = _make_decisions()
        progress = init_progress(d)
        assert progress.set_code == "TST"
        assert progress.review_round == 1
        # OK cards are excluded from progress
        assert "W-C-01" not in progress.cards
        # Non-OK cards are included
        assert "B-R-02" in progress.cards
        assert "U-R-01" in progress.cards
        assert "R-U-03" in progress.cards
        assert "G-C-03" in progress.cards
        assert len(progress.cards) == 5

    def test_init_preserves_action_and_note(self):
        d = _make_decisions()
        progress = init_progress(d)
        assert progress.cards["B-R-02"].action == ReviewAction.REMAKE
        assert progress.cards["B-R-02"].note == "Too weak"
        assert progress.cards["G-C-03"].action == ReviewAction.MANUAL_TWEAK
        assert progress.cards["G-C-03"].note == "Fix mana cost"

    def test_all_pending_initially(self):
        d = _make_decisions()
        progress = init_progress(d)
        for cp in progress.cards.values():
            assert cp.status == "pending"

    def test_summary_counts(self):
        d = _make_decisions()
        progress = init_progress(d)
        assert progress.summary == {"pending": 5}

    def test_all_complete_false_when_pending(self):
        d = _make_decisions()
        progress = init_progress(d)
        assert not progress.all_complete

    def test_all_complete_true_when_done(self):
        d = _make_decisions()
        progress = init_progress(d)
        for cp in progress.cards.values():
            cp.status = "completed"
        assert progress.all_complete

    def test_all_complete_with_errors(self):
        d = _make_decisions()
        progress = init_progress(d)
        for i, cp in enumerate(progress.cards.values()):
            cp.status = "error" if i == 0 else "completed"
        assert progress.all_complete

    def test_all_complete_empty(self):
        """All-OK decisions produce an empty progress, which is vacuously complete."""
        d = _make_decisions(
            decisions={"W-C-01": CardDecision(action=ReviewAction.OK)}
        )
        progress = init_progress(d)
        assert progress.all_complete

    def test_save_load_round_trip(self, tmp_path: Path):
        d = _make_decisions()
        progress = init_progress(d)
        progress.cards["B-R-02"].status = "completed"
        save_progress(progress, "TST", base_dir=tmp_path)
        loaded = load_progress("TST", base_dir=tmp_path)
        assert loaded is not None
        assert loaded.set_code == progress.set_code
        assert loaded.review_round == progress.review_round
        assert loaded.cards["B-R-02"].status == "completed"
        assert loaded.cards["U-R-01"].status == "pending"

    def test_load_returns_none_when_missing(self, tmp_path: Path):
        assert load_progress("TST", base_dir=tmp_path) is None

    def test_card_progress_defaults(self):
        cp = CardProgress(
            collector_number="W-C-01",
            action=ReviewAction.REMAKE,
        )
        assert cp.status == "pending"
        assert cp.note == ""
        assert cp.error_message is None
