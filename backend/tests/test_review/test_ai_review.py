"""Regression tests for the AI design-review loop's empty-iterations handling.

Guards the bug where a transient/persistent LLM failure during review left
``iterations`` empty and the final-result code defaulted ``final_verdict`` to
``"OK"`` — silently passing an un-reviewed card and defeating the gate. Both
review tiers must instead surface a non-OK (flagged) verdict so the runner
treats the card as unfixable. ``generate_with_tool`` is monkeypatched so no real
model is ever loaded.
"""

from __future__ import annotations

import pytest

from mtgai.review import ai_review

_CARD = {
    "collector_number": "W-C-01",
    "name": "Test Bear",
    "rarity": "common",
    "type_line": "Creature — Bear",
    "oracle_text": "",
    "power": "2",
    "toughness": "2",
    "colors": ["W"],
}

_MECHANICS: list[dict] = []
_POINTED_QUESTIONS: list[dict] = []


def _ok_result() -> dict:
    """A successful ``generate_with_tool`` payload with an OK verdict."""
    return {
        "result": {"verdict": "OK", "issues": [], "revised_card": None},
        "input_tokens": 10,
        "output_tokens": 5,
        "model": "test-model",
    }


def _raise(**_kwargs):
    raise RuntimeError("simulated LLM transport failure")


@pytest.fixture(autouse=True)
def _no_cost(monkeypatch):
    monkeypatch.setattr(ai_review, "cost_from_result", lambda _r: 0.0)


class TestReviewSingleEmptyIterations:
    def test_first_iteration_failure_does_not_pass_as_ok(self, monkeypatch):
        """All LLM calls raising must yield a flagged (non-OK) verdict, not OK."""
        monkeypatch.setattr(ai_review, "generate_with_tool", _raise)

        result = ai_review._review_single(_CARD, _MECHANICS, _POINTED_QUESTIONS, "test-model", None)

        assert result.final_verdict != "OK"
        assert result.final_verdict == ai_review._REVIEW_FAILED_VERDICT
        assert result.iterations == []
        assert result.card_was_changed is False
        assert result.revised_card is None
        # Observable: a review_error issue is recorded so the failure isn't silent.
        assert any(i.category == "review_error" for i in result.final_issues)

    def test_successful_review_returns_real_verdict(self, monkeypatch):
        """Regression guard: a normal OK review path is unaffected."""
        monkeypatch.setattr(ai_review, "generate_with_tool", lambda **_k: _ok_result())

        result = ai_review._review_single(_CARD, _MECHANICS, _POINTED_QUESTIONS, "test-model", None)

        assert result.final_verdict == "OK"
        assert len(result.iterations) == 1
        assert result.final_issues == []


class TestReviewCouncilEmptyIterations:
    def test_synthesis_failure_does_not_pass_as_ok(self, monkeypatch):
        """Reviewers flag REVISE, then every synthesis call fails — flag, not OK."""
        calls = {"n": 0}

        def stub(**_kwargs):
            calls["n"] += 1
            if calls["n"] <= 3:
                # Three independent reviewers all flag REVISE so synthesis runs.
                return {
                    "result": {
                        "verdict": "REVISE",
                        "issues": [
                            {"severity": "FAIL", "category": "design", "description": "bad"}
                        ],
                        "revised_card": None,
                    },
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "model": "test-model",
                }
            raise RuntimeError("simulated synthesis failure")

        monkeypatch.setattr(ai_review, "generate_with_tool", stub)

        result = ai_review._review_council(
            _CARD, _MECHANICS, _POINTED_QUESTIONS, "test-model", None
        )

        assert result.final_verdict != "OK"
        assert result.final_verdict == ai_review._REVIEW_FAILED_VERDICT
        assert result.iterations == []
        assert result.card_was_changed is False
        assert result.revised_card is None
        assert any(i.category == "review_error" for i in result.final_issues)
        # The completed reviewer assessments (and their cost) are preserved.
        assert len(result.council_reviews) == 3

    def test_all_reviewers_fail_does_not_pass_as_ok(self, monkeypatch):
        """Every reviewer call failing also must not default to OK."""
        monkeypatch.setattr(ai_review, "generate_with_tool", _raise)

        result = ai_review._review_council(
            _CARD, _MECHANICS, _POINTED_QUESTIONS, "test-model", None
        )

        assert result.final_verdict != "OK"
        assert result.final_verdict == ai_review._REVIEW_FAILED_VERDICT
        assert any(i.category == "review_error" for i in result.final_issues)

    def test_all_reviewers_ok_returns_real_verdict(self, monkeypatch):
        """Regression guard: all-OK council short-circuits to a real OK verdict."""
        monkeypatch.setattr(ai_review, "generate_with_tool", lambda **_k: _ok_result())

        result = ai_review._review_council(
            _CARD, _MECHANICS, _POINTED_QUESTIONS, "test-model", None
        )

        assert result.final_verdict == "OK"
        assert len(result.council_reviews) == 3
        assert result.iterations == []
