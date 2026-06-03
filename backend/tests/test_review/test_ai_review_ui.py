"""Tests for the AI Design Review UI backend helpers.

Covers the wizard tab's building blocks: the per-card tile shape, the
user-decisions sidecar round-trip, the effective-decision precedence, the live
council stream emitted through ``_review_single``, and the manual
``revise_card_in_place`` single-call revision. ``generate_with_tool`` is
monkeypatched so no real model is ever loaded.
"""

from __future__ import annotations

import pytest

from mtgai.review import ai_review
from mtgai.review.ai_review import CardReviewResult, ReviewIssue

_CARD = {
    "collector_number": "W-C-01",
    "name": "Test Bear",
    "mana_cost": "{1}{W}",
    "type_line": "Creature — Bear",
    "oracle_text": "Vigilance",
    "rarity": "common",
    "power": "2",
    "toughness": "2",
    "colors": ["W"],
}


@pytest.fixture(autouse=True)
def _no_cost(monkeypatch):
    monkeypatch.setattr(ai_review, "cost_from_result", lambda _r: 0.0)


# ---------------------------------------------------------------------------
# review_tile
# ---------------------------------------------------------------------------


class TestReviewTile:
    def test_unreviewed_card(self):
        tile = ai_review.review_tile(_CARD, None)
        assert tile["collector_number"] == "W-C-01"
        assert tile["name"] == "Test Bear"
        assert tile["reviewed"] is False
        assert tile["verdict"] is None
        assert tile["issues"] == []
        assert tile["council"] == []

    def test_reviewed_ok_card(self):
        review = CardReviewResult(
            collector_number="W-C-01",
            card_name="Test Bear",
            rarity="common",
            review_tier="single",
            original_card=_CARD,
            final_verdict="OK",
        )
        tile = ai_review.review_tile(_CARD, review)
        assert tile["reviewed"] is True
        assert tile["verdict"] == "OK"
        assert tile["review_tier"] == "single"

    def test_reviewed_revise_carries_issues_and_council(self):
        review = CardReviewResult(
            collector_number="W-C-01",
            card_name="Test Bear",
            rarity="rare",
            review_tier="council",
            original_card=_CARD,
            final_verdict="REVISE",
            final_issues=[
                ReviewIssue(severity="FAIL", category="balance", description="above rate")
            ],
            council_reviews=[],
        )
        tile = ai_review.review_tile(_CARD, review)
        assert tile["verdict"] == "REVISE"
        assert tile["issues"] == [
            {"severity": "FAIL", "category": "balance", "description": "above rate"}
        ]
        assert tile["review_tier"] == "council"


# ---------------------------------------------------------------------------
# decisions sidecar
# ---------------------------------------------------------------------------


class TestDecisions:
    def test_roundtrip(self, tmp_path):
        assert ai_review.load_decisions(tmp_path) == {}
        ai_review.save_decision(
            tmp_path, "W-C-01", {"verdict": "approved", "reason": "", "source": "user"}
        )
        loaded = ai_review.load_decisions(tmp_path)
        assert loaded["W-C-01"]["verdict"] == "approved"
        assert loaded["W-C-01"]["source"] == "user"

    def test_save_merges_without_clobbering(self, tmp_path):
        ai_review.save_decision(tmp_path, "A", {"verdict": "approved", "source": "user"})
        ai_review.save_decision(tmp_path, "B", {"verdict": "rejected", "source": "user"})
        loaded = ai_review.load_decisions(tmp_path)
        assert set(loaded) == {"A", "B"}

    def test_clear_removes_entry(self, tmp_path):
        ai_review.save_decision(tmp_path, "A", {"verdict": "approved", "source": "user"})
        ai_review.clear_decision(tmp_path, "A")
        assert ai_review.load_decisions(tmp_path) == {}

    def test_clear_missing_is_noop(self, tmp_path):
        ai_review.clear_decision(tmp_path, "nope")  # no file yet; must not raise
        assert ai_review.load_decisions(tmp_path) == {}


# ---------------------------------------------------------------------------
# live council stream through _review_single
# ---------------------------------------------------------------------------


class TestCouncilStream:
    def test_single_review_emits_council_rounds(self, monkeypatch):
        """A single-reviewer iteration emits a round event with one verdict slot."""
        monkeypatch.setattr(
            ai_review,
            "generate_with_tool",
            lambda **_k: {
                "result": {"verdict": "OK", "issues": [], "revised_card": None},
                "input_tokens": 1,
                "output_tokens": 1,
                "model": "m",
            },
        )
        events: list[dict] = []
        ai_review._review_single(_CARD, [], [], "m", None, on_council=events.append)
        rounds = [e for e in events if e.get("kind") == "round"]
        assert rounds, "expected at least one council round event"
        # The terminal round for an OK verdict carries the resolved 'ok' slot.
        assert rounds[-1]["verdicts"] == ["ok"]

    def test_council_hook_error_does_not_break_review(self, monkeypatch):
        monkeypatch.setattr(
            ai_review,
            "generate_with_tool",
            lambda **_k: {
                "result": {"verdict": "OK", "issues": [], "revised_card": None},
                "input_tokens": 1,
                "output_tokens": 1,
                "model": "m",
            },
        )

        def _boom(_event):
            raise RuntimeError("hook blew up")

        result = ai_review._review_single(_CARD, [], [], "m", None, on_council=_boom)
        assert result.final_verdict == "OK"  # review still completed


# ---------------------------------------------------------------------------
# revise_card_in_place
# ---------------------------------------------------------------------------


class TestReviseInPlace:
    def test_returns_revised_card(self, monkeypatch):
        revised = {**_CARD, "oracle_text": "Vigilance, trample"}
        monkeypatch.setattr(
            ai_review,
            "generate_with_tool",
            lambda **_k: {
                "result": {"verdict": "REVISE", "issues": [], "revised_card": revised},
                "input_tokens": 1,
                "output_tokens": 1,
                "model": "m",
            },
        )
        out = ai_review.revise_card_in_place(_CARD, "add trample", [], [], "m", None)
        assert out is not None
        assert out["oracle_text"] == "Vigilance, trample"

    def test_no_revision_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            ai_review,
            "generate_with_tool",
            lambda **_k: {
                "result": {"verdict": "OK", "issues": [], "revised_card": None},
                "input_tokens": 1,
                "output_tokens": 1,
                "model": "m",
            },
        )
        assert ai_review.revise_card_in_place(_CARD, "no-op", [], [], "m", None) is None

    def test_llm_failure_returns_none(self, monkeypatch):
        def _raise(**_k):
            raise RuntimeError("transport down")

        monkeypatch.setattr(ai_review, "generate_with_tool", _raise)
        assert ai_review.revise_card_in_place(_CARD, "x", [], [], "m", None) is None
