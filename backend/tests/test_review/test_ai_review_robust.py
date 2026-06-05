"""Regression tests for ai_review robustness against malformed LLM output.

Guards the cluster of crashes where a local model returned a wrong-shaped review
payload that the stage indexed blindly:

- ``KeyError: 'name'`` — a revised_card dict missing ``name`` fed to the prompt
  builder / markdown renderer.
- ``string indices must be integers`` — a non-dict ``result["result"]`` or a
  bare-string ``issues`` item indexed as a dict.
- "every LLM review call failed" — a single transient failure dropping a card
  out of review with no retry.
- reviewer/synth baking parenthetical reminder text into a revised ``oracle_text``
  (reminder text is injected programmatically at finalize, never LLM-authored).

``generate_with_tool`` is monkeypatched so no real model is ever loaded.
"""

from __future__ import annotations

import pytest

from mtgai.models.card import Card
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
_POINTED_QUESTIONS: list[dict] = [
    {"id": "q1", "question": "Is this card balanced?", "category": "balance"},
]


@pytest.fixture(autouse=True)
def _no_cost(monkeypatch):
    monkeypatch.setattr(ai_review, "cost_from_result", lambda _r: 0.0)


# ---------------------------------------------------------------------------
# Malformed-shape guards (no crash)
# ---------------------------------------------------------------------------


class TestMalformedShapesDoNotCrash:
    def test_format_card_missing_name(self):
        """A revised_card dict missing ``name`` must not KeyError the prompt builder."""
        block = ai_review._format_card_for_review({"oracle_text": "Flying", "rarity": "rare"})
        assert "Name: ???" in block

    def test_format_card_non_dict(self):
        """A non-dict card (a stray string) returns empty, never raises."""
        assert ai_review._format_card_for_review("not a card") == ""  # type: ignore[arg-type]

    def test_build_review_prompt_with_string_pointed_question(self):
        """A pointed question that's a bare string (not a dict) must not crash."""
        prompt = ai_review._build_review_prompt(_CARD, _MECHANICS, ["plain string question"])
        assert "plain string question" in prompt

    def test_build_iteration_prompt_with_string_issue(self):
        """An ``issues`` item that's a bare string must not ``string indices`` crash."""
        verdict = {"verdict": "REVISE", "issues": ["a bare string issue"], "revised_card": None}
        # Must not raise (the bad item is skipped).
        ai_review._build_iteration_prompt(verdict)

    def test_coerce_verdict_data_non_dict(self):
        """A non-dict tool result coerces to ``{}`` (the source of the string-index crash)."""
        assert ai_review._coerce_verdict_data("just a string") == {}
        assert ai_review._coerce_verdict_data(["a", "list"]) == {}
        assert ai_review._coerce_verdict_data(None) == {}
        assert ai_review._coerce_verdict_data({"verdict": "OK"}) == {"verdict": "OK"}

    def test_coerce_issues_drops_junk_and_fills_defaults(self):
        """Bare strings are dropped; a dict missing keys is filled, never raising."""
        issues = ai_review._coerce_issues(
            [
                "a bare string",
                {"description": "missing severity and category"},
                {"severity": "FAIL", "category": "design", "description": "ok"},
                42,
            ]
        )
        # Two valid issues survive (the string + the int are dropped).
        assert len(issues) == 2
        # The partial dict is filled with safe defaults.
        partial = issues[0]
        assert partial.severity == "WARN"
        assert partial.category == "other"
        assert partial.description == "missing severity and category"

    def test_review_single_with_string_result_does_not_crash(self, monkeypatch):
        """A reviewer returning a bare-string ``result`` is treated as a safe OK, not a crash."""

        def stub(**_kwargs):
            return {
                "result": "I think this card looks fine to me!",  # wrong shape
                "input_tokens": 10,
                "output_tokens": 5,
                "model": "test-model",
            }

        monkeypatch.setattr(ai_review, "generate_with_tool", stub)
        result = ai_review._review_single(_CARD, _MECHANICS, _POINTED_QUESTIONS, "test-model", None)
        # Coerced to {} → verdict defaults to OK; no crash, one iteration recorded.
        assert result.final_verdict == "OK"
        assert len(result.iterations) == 1

    def test_council_with_malformed_revised_card_does_not_crash(self, monkeypatch):
        """A synth revised_card missing ``name`` flows through the next panel without KeyError."""
        calls = {"n": 0}

        def stub(**kwargs):
            calls["n"] += 1
            name = kwargs["tool_schema"]["name"]
            if name == "submit_synthesis":
                # Revised card MISSING 'name' (the local-model corruption pattern).
                return {
                    "result": {
                        "verdict": "REVISE",
                        "issues": [],
                        "revised_card": {"oracle_text": "Flying", "rarity": "rare"},
                    },
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "model": "test-model",
                }
            # Round 1 flags REVISE (consensus), round 2 OKs the (nameless) revision.
            verdict = "REVISE" if calls["n"] <= 3 else "OK"
            issues = [] if verdict == "OK" else [{"severity": "FAIL", "category": "x", "d": 1}]
            return {
                "result": {"verdict": verdict, "issues": issues, "revised_card": None},
                "input_tokens": 10,
                "output_tokens": 5,
                "model": "test-model",
            }

        monkeypatch.setattr(ai_review, "generate_with_tool", stub)
        result = ai_review._review_council(
            _CARD, _MECHANICS, _POINTED_QUESTIONS, "test-model", None
        )
        # The nameless revision was accepted without crashing the council loop.
        assert result.card_was_changed is True
        assert result.final_verdict == "OK"


# ---------------------------------------------------------------------------
# Transient-failure retry (card could not be reviewed)
# ---------------------------------------------------------------------------


class TestTransientRetry:
    def test_one_transient_failure_then_success(self, monkeypatch):
        """A single transient failure is retried inside the same call, not dropped."""
        calls = {"n": 0}

        def stub(**_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient blip")
            return {
                "result": {"verdict": "OK", "issues": [], "revised_card": None},
                "input_tokens": 10,
                "output_tokens": 5,
                "model": "test-model",
            }

        monkeypatch.setattr(ai_review, "generate_with_tool", stub)
        result = ai_review._review_single(_CARD, _MECHANICS, _POINTED_QUESTIONS, "test-model", None)
        # The retry recovered: a real verdict, not a flagged review_error.
        assert result.final_verdict == "OK"
        assert calls["n"] == 2
        assert not any(i.category == "review_error" for i in result.final_issues)

    def test_retries_exhausted_flags_for_attention(self, monkeypatch):
        """Only after MAX_CALL_ATTEMPTS genuine failures is the card flagged."""
        calls = {"n": 0}

        def stub(**_kwargs):
            calls["n"] += 1
            raise RuntimeError("persistent failure")

        monkeypatch.setattr(ai_review, "generate_with_tool", stub)
        result = ai_review._review_single(_CARD, _MECHANICS, _POINTED_QUESTIONS, "test-model", None)
        # The single iteration retried MAX_CALL_ATTEMPTS times before giving up.
        assert calls["n"] == ai_review.MAX_CALL_ATTEMPTS
        assert result.final_verdict == ai_review._REVIEW_FAILED_VERDICT
        assert any(i.category == "review_error" for i in result.final_issues)


# ---------------------------------------------------------------------------
# Reminder text must not survive a revision
# ---------------------------------------------------------------------------


class TestReminderTextStrippedFromRevision:
    def test_apply_revision_strips_parenthetical_reminder(self):
        """A revised oracle_text with baked-in reminder text is stripped to canonical form."""
        original = Card(
            collector_number="001",
            name="Energon Condensate",
            mana_cost="{1}{G}",
            type_line="Artifact Creature — BotBot",
            oracle_text="When this enters, energize.",
            rarity="common",
            power="2",
            toughness="2",
            colors=["G"],
            color_identity=["G"],
            cmc=2,
        )
        revised = {
            "oracle_text": (
                "When Energon Condensate enters, energize. (To energize, create an "
                "Energon token. It's a colorless artifact with \"{T}, Sacrifice this "
                'artifact: Add one mana of any color.")'
            ),
        }
        updated = ai_review._apply_revision(original, revised)
        assert "(" not in updated.oracle_text
        assert "To energize" not in updated.oracle_text
        assert updated.oracle_text == "When Energon Condensate enters, energize."

    def test_apply_revision_keeps_short_parentheticals(self):
        """Short parentheticals (P/T notes, not reminder text) are left untouched."""
        original = Card(
            collector_number="002",
            name="Test",
            mana_cost="{1}",
            type_line="Artifact",
            oracle_text="Original.",
            rarity="common",
            colors=[],
            color_identity=[],
            cmc=1,
        )
        # A short parenthetical (<20 chars) is below the reminder-strip threshold.
        revised = {"oracle_text": "Do a thing (up to two)."}
        updated = ai_review._apply_revision(original, revised)
        assert updated.oracle_text == "Do a thing (up to two)."
