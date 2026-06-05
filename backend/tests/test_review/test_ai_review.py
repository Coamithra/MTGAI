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
    def test_synthesis_failure_flags_with_council_issues(self, monkeypatch):
        """Reviewers flag REVISE, then the synth (reviser) call fails.

        The card can't be improved, so it's left REVISE carrying the council's *real*
        finding (not a synthetic review_error) — the runner flags it for regen.
        """
        calls = {"n": 0}

        def stub(**_kwargs):
            calls["n"] += 1
            if calls["n"] <= 3:
                # Three independent reviewers all flag REVISE so the synth runs.
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

        assert result.final_verdict == "REVISE"  # flagged for regen
        assert result.iterations == []  # the synth never produced a revision
        assert result.card_was_changed is False
        assert result.revised_card is None
        # The surviving council finding rides into the regen reason — NOT review_error.
        assert any(i.category == "design" for i in result.final_issues)
        # Only the (single) initial panel ran; its assessments are preserved.
        assert len(result.council_reviews) == 3
        assert {cr.round for cr in result.council_reviews} == {1}

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


# ---------------------------------------------------------------------------
# Fresh-council-per-revision loop (the card's core behaviour)
# ---------------------------------------------------------------------------


def _verdict_payload(verdict: str, *, revised: dict | None = None) -> dict:
    """A ``generate_with_tool`` payload with the given verdict (+ optional revision)."""
    return {
        "result": {
            "verdict": verdict,
            "issues": (
                []
                if verdict == "OK"
                else [{"severity": "FAIL", "category": "design", "description": "bad"}]
            ),
            "revised_card": revised,
        },
        "input_tokens": 10,
        "output_tokens": 5,
        "model": "test-model",
    }


_REVISED_CARD = {**_CARD, "name": "Revised Bear", "oracle_text": "Trample"}


class _CouncilScript:
    """Scripts ``generate_with_tool`` for the council loop.

    ``rounds`` is the per-panel reviewer verdicts, e.g.
    ``[["REVISE", "REVISE", "REVISE"], ["OK", "OK", "OK"]]``. Calls are routed by
    tool name: ``submit_review`` consumes the current round's verdicts in order;
    ``submit_synthesis`` advances to the next round and returns a revision (with the
    given ``synth_verdict``). The round index = number of synth calls so far.
    """

    def __init__(self, rounds, *, synth_verdict="REVISE", synth_revises=True):
        self.rounds = rounds
        self.synth_verdict = synth_verdict
        self.synth_revises = synth_revises
        self.synth_count = 0
        self.reviewer_idx = 0

    def __call__(self, **kwargs):
        name = kwargs["tool_schema"]["name"]
        if name == "submit_synthesis":
            self.synth_count += 1
            self.reviewer_idx = 0
            revised = dict(_REVISED_CARD) if self.synth_revises else None
            return _verdict_payload(self.synth_verdict, revised=revised)
        verdicts = self.rounds[self.synth_count]
        verdict = verdicts[self.reviewer_idx]
        self.reviewer_idx += 1
        return _verdict_payload(verdict)


class TestReviewCouncilFreshLoop:
    def test_two_of_three_ok_passes_without_synth(self, monkeypatch):
        """A 2-of-3 OK consensus on the initial panel approves the card — no synth."""
        script = _CouncilScript([["OK", "OK", "REVISE"]])
        monkeypatch.setattr(ai_review, "generate_with_tool", script)

        result = ai_review._review_council(
            _CARD, _MECHANICS, _POINTED_QUESTIONS, "test-model", None
        )

        assert result.final_verdict == "OK"
        assert result.iterations == []  # consensus reached before any synth call
        assert result.card_was_changed is False
        assert len(result.council_reviews) == 3
        assert script.synth_count == 0

    def test_revise_then_fresh_council_oks(self, monkeypatch):
        """Panel flags → synth revises → a FRESH council OKs the revision → pass."""
        script = _CouncilScript([["REVISE", "REVISE", "REVISE"], ["OK", "OK", "OK"]])
        monkeypatch.setattr(ai_review, "generate_with_tool", script)

        result = ai_review._review_council(
            _CARD, _MECHANICS, _POINTED_QUESTIONS, "test-model", None
        )

        assert result.final_verdict == "OK"
        assert result.card_was_changed is True
        assert result.revised_card is not None
        assert result.revised_card["name"] == "Revised Bear"
        assert len(result.iterations) == 1  # one synth revision
        # Two panels ran (initial + one fresh council), 3 reviewers each.
        assert len(result.council_reviews) == 6
        assert {cr.round for cr in result.council_reviews} == {1, 2}
        assert script.synth_count == 1

    def test_persistently_problematic_flags_for_regen(self, monkeypatch):
        """Every fresh council still flags → REVISE (flagged for regen) after 3 rounds."""
        script = _CouncilScript([["REVISE", "REVISE", "REVISE"]] * 4)
        monkeypatch.setattr(ai_review, "generate_with_tool", script)

        result = ai_review._review_council(
            _CARD, _MECHANICS, _POINTED_QUESTIONS, "test-model", None
        )

        assert result.final_verdict == "REVISE"  # → unfixable → flagged_by='ai_review'
        # Initial panel + MAX_COUNCIL_ROUNDS fresh councils, 3 reviewers each.
        expected_panels = 1 + ai_review.MAX_COUNCIL_ROUNDS
        assert len(result.council_reviews) == expected_panels * 3
        assert len(result.iterations) == ai_review.MAX_COUNCIL_ROUNDS  # one synth per round
        assert script.synth_count == ai_review.MAX_COUNCIL_ROUNDS
        # The surviving council issues become the regen reason.
        assert any(i.category == "design" for i in result.final_issues)

    def test_synth_self_verdict_is_ignored(self, monkeypatch):
        """A synth that grades its own revision OK does NOT short-circuit the loop.

        Only the independent fresh council decides; here every council still flags, so
        the card is flagged for regen despite the synth's repeated self-OK.
        """
        script = _CouncilScript(
            [["REVISE", "REVISE", "REVISE"]] * 4, synth_verdict="OK", synth_revises=True
        )
        monkeypatch.setattr(ai_review, "generate_with_tool", script)

        result = ai_review._review_council(
            _CARD, _MECHANICS, _POINTED_QUESTIONS, "test-model", None
        )

        assert result.final_verdict == "REVISE"
        # The synth claimed OK every time, but the loop never trusted it.
        assert result.iterations and all(it.verdict == "OK" for it in result.iterations)
        assert script.synth_count == ai_review.MAX_COUNCIL_ROUNDS

    def test_synth_declining_to_revise_flags_immediately(self, monkeypatch):
        """A synth that produces no revised card on a consensus-flagged card → regen.

        Nothing changed, so re-running a fresh council would only re-flag it; the loop
        flags for regen right away (it does NOT burn the remaining council rounds).
        """
        script = _CouncilScript([["REVISE", "REVISE", "REVISE"]] * 4, synth_revises=False)
        monkeypatch.setattr(ai_review, "generate_with_tool", script)

        result = ai_review._review_council(
            _CARD, _MECHANICS, _POINTED_QUESTIONS, "test-model", None
        )

        assert result.final_verdict == "REVISE"
        assert result.card_was_changed is False
        assert result.revised_card is None
        assert len(result.iterations) == 1  # the one (no-op) synth call
        assert script.synth_count == 1  # stopped after the first declined revision
        assert len(result.council_reviews) == 3  # only the initial panel ran
        assert any(i.category == "design" for i in result.final_issues)

    def test_collapsed_later_panel_flags_from_last_real_panel(self, monkeypatch):
        """A later round whose whole panel errors flags from the last real panel.

        Round 1 flags + the synth revises; round 2's reviewers all fail. The loop must
        not synthesize against zero feedback or flag with an empty reason — it stops
        and flags REVISE carrying round 1's issues.
        """
        calls = {"n": 0}

        def stub(**kwargs):
            calls["n"] += 1
            name = kwargs["tool_schema"]["name"]
            if name == "submit_synthesis":
                return _verdict_payload("REVISE", revised=dict(_REVISED_CARD))
            if calls["n"] <= 3:  # round 1 reviewers
                return _verdict_payload("REVISE")
            raise RuntimeError("round 2 reviewer down")  # round 2 panel collapses

        monkeypatch.setattr(ai_review, "generate_with_tool", stub)

        result = ai_review._review_council(
            _CARD, _MECHANICS, _POINTED_QUESTIONS, "test-model", None
        )

        assert result.final_verdict == "REVISE"
        assert len(result.iterations) == 1  # the round-1 synth ran
        assert result.card_was_changed is True  # round-1 revision kept
        assert len(result.council_reviews) == 3  # only round 1 produced reviews
        assert any(i.category == "design" for i in result.final_issues)


_UNCOMMON_CARD = {
    "collector_number": "W-U-20",
    "name": "Ark Bear",
    "rarity": "uncommon",
    "type_line": "Artifact Creature — Bear",
    "mana_cost": "{4}{W}{W}",
    "oracle_text": "Vigilance",
    "power": "5",
    "toughness": "5",
    "colors": ["W"],
}


class TestPartialRevisionMerge:
    """A partial ``revised_card`` (the model omits a field) must not blank that field
    for the next round's judge, and the accumulated revision must keep it.

    Regression for the loop feeding the raw partial revise dict forward: when round 1
    dropped ``mana_cost`` while only setting ``cmc``, round 2 judged a blank-cost,
    colorless card and burned a round on a phantom color-pie REVISE (the
    Ark-Class Peacekeeper case). The loop now accumulates each revision onto the
    current card via ``_merge_revision_into_dict``.
    """

    def test_single_omitted_field_preserved_and_accumulated(self, monkeypatch):
        judge_prompts: list[str] = []

        def stub(**kwargs):
            name = kwargs["tool_schema"]["name"]
            if name == "submit_revision":
                # Partial revision: change oracle_text + power, but DROP mana_cost.
                return {
                    "result": {
                        "verdict": "REVISE",
                        "issues": [],
                        "revised_card": {
                            "name": "Ark Bear",
                            "type_line": "Artifact Creature — Bear",
                            "oracle_text": "Vigilance\nWhen Ark Bear dies, create a 1/1 token.",
                            "power": "6",
                        },
                    },
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "model": "test-model",
                }
            judge_prompts.append(kwargs["user_prompt"])
            verdict = "REVISE" if len(judge_prompts) == 1 else "OK"
            issues = (
                [{"category": "balance", "description": "too low", "severity": "FAIL"}]
                if verdict == "REVISE"
                else []
            )
            return {
                "result": {"verdict": verdict, "issues": issues},
                "input_tokens": 10,
                "output_tokens": 5,
                "model": "test-model",
            }

        monkeypatch.setattr(ai_review, "generate_with_tool", stub)

        result = ai_review._review_single(
            _UNCOMMON_CARD, _MECHANICS, _POINTED_QUESTIONS, "test-model", None
        )

        assert result.final_verdict == "OK"
        assert result.card_was_changed is True
        # The omitted field survives; the model's edits are accumulated.
        assert result.revised_card["mana_cost"] == "{4}{W}{W}"
        assert "dies" in result.revised_card["oracle_text"]
        assert result.revised_card["power"] == "6"
        # The round-2 judge saw the preserved mana cost, not a blanked one.
        assert "{4}{W}{W}" in judge_prompts[1]

    def test_in_progress_revision_streamed_to_council(self, monkeypatch):
        """Each round's revision is pushed as a ``{"kind": "card"}`` council event so
        the tab's tile can update mid-loop."""
        events: list[dict] = []

        def stub(**kwargs):
            name = kwargs["tool_schema"]["name"]
            if name == "submit_revision":
                return {
                    "result": {
                        "verdict": "REVISE",
                        "issues": [],
                        "revised_card": {"power": "6", "toughness": "6"},
                    },
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "model": "test-model",
                }
            verdict = "REVISE" if not any(e.get("kind") == "card" for e in events) else "OK"
            issues = (
                [{"category": "balance", "description": "x", "severity": "FAIL"}]
                if verdict == "REVISE"
                else []
            )
            return {
                "result": {"verdict": verdict, "issues": issues},
                "input_tokens": 10,
                "output_tokens": 5,
                "model": "test-model",
            }

        monkeypatch.setattr(ai_review, "generate_with_tool", stub)

        ai_review._review_single(
            _UNCOMMON_CARD,
            _MECHANICS,
            _POINTED_QUESTIONS,
            "test-model",
            None,
            on_council=events.append,
        )

        card_events = [e for e in events if e.get("kind") == "card"]
        assert len(card_events) == 1
        tile = card_events[0]["card"]
        # Carries the live (merged) display body: the revised P/T over the kept cost.
        assert tile["mana_cost"] == "{4}{W}{W}"
        assert tile["power"] == "6"
        assert tile["toughness"] == "6"
