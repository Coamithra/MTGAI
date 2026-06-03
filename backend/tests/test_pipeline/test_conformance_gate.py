"""The merged Conformance & Interactions gate + its truncation-retry helper.

Covers ``analysis.gate_common.generate_gate_tool`` (retries a truncated local
response, bumping temperature; raises after exhausting retries) and
``pipeline.stages.run_conformance`` (runs both LLM steps, combines findings into
per-step artifacts, flags each step's cards for regen, and bounces to card_gen).
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import pytest

from mtgai.analysis import gate_common
from mtgai.analysis.models import ConformanceFinding, InteractionFlag
from mtgai.generation.token_utils import OutputTruncatedError
from mtgai.pipeline import stages as stages_mod
from mtgai.runtime import active_project
from mtgai.settings.model_settings import ModelSettings

# ----------------------------------------------------------------------
# generate_gate_tool — truncation retry
# ----------------------------------------------------------------------


def test_generate_gate_tool_retries_then_succeeds(monkeypatch):
    temps: list[float] = []

    def fake(**kwargs):
        temps.append(kwargs["temperature"])
        if len(temps) < 2:
            raise OutputTruncatedError("trunc", eval_count=10, num_predict=10)
        return {"result": {"ok": True}}

    monkeypatch.setattr(gate_common, "generate_with_tool", fake)
    out = gate_common.generate_gate_tool(base_temperature=0.2, system_prompt="s", user_prompt="u")
    assert out == {"result": {"ok": True}}
    # First attempt at the base temp; the retry is nudged up to escape the loop.
    assert temps == [pytest.approx(0.2), pytest.approx(0.4)]


def test_generate_gate_tool_raises_after_exhausting_retries(monkeypatch):
    attempts = [0]

    def fake(**kwargs):
        attempts[0] += 1
        raise OutputTruncatedError("trunc", eval_count=10, num_predict=10)

    monkeypatch.setattr(gate_common, "generate_with_tool", fake)
    with pytest.raises(OutputTruncatedError):
        gate_common.generate_gate_tool(
            base_temperature=0.2, retries=2, system_prompt="s", user_prompt="u"
        )
    assert attempts[0] == 3  # retries + 1


# ----------------------------------------------------------------------
# run_conformance — merged gate
# ----------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path):
    asset_dir = tmp_path / "asset"
    asset_dir.mkdir()
    active_project.write_active_project(
        active_project.ProjectState(
            set_code="ABC", settings=ModelSettings(asset_folder=str(asset_dir))
        )
    )
    yield asset_dir
    active_project.clear_active_project()


class _Emitter:
    def __init__(self):
        self.phases: list[tuple[str, str]] = []
        self.events: list[tuple[str, dict]] = []

    def phase(self, state, detail=""):
        self.phases.append((state, detail))

    def event(self, event_type, **data):
        # The merged gate streams each step live (conformance_reset +
        # one conformance_step per step) so the tab fills in independently.
        self.events.append((event_type, data))


def _make_card(slot_id: str, oracle_text: str | None = None):
    from mtgai.models.card import Card

    # Default each card a distinct oracle text so the algorithmic Duplicate
    # Check does not treat the shared "Creature — Test" type line as a dup;
    # tests that exercise the dup step pass identical oracle text explicitly.
    return Card(
        name=f"Card {slot_id}",
        slot_id=slot_id,
        collector_number=slot_id,
        type_line="Creature — Test",
        oracle_text=oracle_text if oracle_text is not None else f"Unique ability {slot_id}.",
    )


def test_run_conformance_merges_both_steps(project, monkeypatch):
    from mtgai.io.card_io import load_card, save_card
    from mtgai.models.enums import CardStatus

    save_card(_make_card("W-C-01"), set_dir=project)
    save_card(_make_card("W-C-02"), set_dir=project)

    monkeypatch.setattr(
        "mtgai.analysis.conformance.check_conformance",
        lambda cards, slots, **kw: (
            [ConformanceFinding(slot_id="W-C-01", card_name="Card W-C-01", reason="wrong color")],
            "conformance analysis",
            0.01,
        ),
    )
    monkeypatch.setattr(
        "mtgai.analysis.interactions.analyze_interactions",
        lambda cards, mechanics: (
            [
                InteractionFlag(
                    enabler_slot_id="W-C-02",
                    reason="infinite loop with X",
                    replacement_constraint="no free untap",
                )
            ],
            "interaction analysis",
            0.02,
        ),
    )
    monkeypatch.setattr(stages_mod, "make_poller", lambda *a, **k: contextlib.nullcontext())

    emitter = _Emitter()
    result = stages_mod.run_conformance(None, emitter)

    assert result.success is True
    assert result.rerun_from == "card_gen"
    assert result.cost_usd == pytest.approx(0.03)

    # Each step streamed to the tab the moment it returned: a reset, then one
    # conformance_step per step (conformance, then interactions). The algorithmic
    # duplicate check has no section of its own — its hits fold into conformance.
    assert [t for t, _ in emitter.events] == [
        "conformance_reset",
        "conformance_step",
        "conformance_step",
    ]
    streamed = [d["step"]["id"] for t, d in emitter.events if t == "conformance_step"]
    assert streamed == ["conformance", "interactions"]

    steps = result.artifacts["steps"]
    assert [s["id"] for s in steps] == ["conformance", "interactions"]
    conf, inter = steps
    assert conf["flagged"][0]["slot_id"] == "W-C-01"
    assert conf["flagged"][0]["card_name"] == "Card W-C-01"
    assert conf["passed"] is False
    assert inter["flagged"][0]["slot_id"] == "W-C-02"
    assert "no free untap" in inter["flagged"][0]["reason"]
    assert inter["passed"] is False

    # Both cards persisted as flagged-for-regen by the merged stage.
    flagged_slots = {f["slot_id"] for f in result.artifacts["flagged"]}
    assert flagged_slots == {"W-C-01", "W-C-02"}
    for p in (project / "cards").glob("*.json"):
        card = load_card(p)
        assert card.flagged_by == "conformance"
        assert card.status == CardStatus.DRAFT
        assert card.regen_reason


def test_check_conformance_is_per_card_and_streams(project, monkeypatch):
    """check_conformance makes one call per card and streams a live checklist."""
    from mtgai.analysis import conformance as conf_mod

    cards = [_make_card("W-C-01"), _make_card("W-C-02"), _make_card("W-C-03")]
    slots = {
        c.slot_id: {"slot_id": c.slot_id, "tweaked_text": "White common creature"} for c in cards
    }

    # One LLM call per card; the 2nd card is judged non-conforming.
    calls = {"n": 0}

    def fake_gate(**kwargs):
        calls["n"] += 1
        conforms = calls["n"] != 2
        return {
            "result": {"conforms": conforms, "reason": "" if conforms else "wrong color"},
            "input_tokens": 5,
            "output_tokens": 5,
        }

    monkeypatch.setattr(conf_mod, "generate_gate_tool", fake_gate)
    monkeypatch.setattr(conf_mod, "cost_from_result", lambda r: 0.01)

    started: list[list[dict]] = []
    streamed: list[dict] = []
    findings, analysis, cost = conf_mod.check_conformance(
        cards,
        slots,
        on_start=lambda lst: started.append(lst),
        on_card=lambda rec: streamed.append(rec),
    )

    # One call per card.
    assert calls["n"] == 3
    # on_start fired once with the full card list (names only) up front.
    assert len(started) == 1
    assert [c["slot_id"] for c in started[0]] == ["W-C-01", "W-C-02", "W-C-03"]
    # on_card streamed a verdict per card, in order.
    assert [r["conforms"] for r in streamed] == [True, False, True]
    # Only the non-conforming card becomes a finding.
    assert [f.slot_id for f in findings] == ["W-C-02"]
    assert findings[0].reason == "wrong color"
    assert cost == pytest.approx(0.03)
    assert "2/3" in analysis


def test_check_conformance_tolerates_a_failed_card(project, monkeypatch):
    """A card whose LLM call errors is marked unknown (not flagged); others proceed."""
    from mtgai.analysis import conformance as conf_mod

    cards = [_make_card("W-C-01"), _make_card("W-C-02")]
    slots = {
        c.slot_id: {"slot_id": c.slot_id, "tweaked_text": "White common creature"} for c in cards
    }

    calls = {"n": 0}

    def fake_gate(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("truncated")
        return {"result": {"conforms": True, "reason": ""}, "input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(conf_mod, "generate_gate_tool", fake_gate)
    monkeypatch.setattr(conf_mod, "cost_from_result", lambda r: 0.0)

    streamed: list[dict] = []
    findings, _analysis, _cost = conf_mod.check_conformance(
        cards, slots, on_card=lambda rec: streamed.append(rec)
    )

    # The failed card streams conforms=None and is NOT flagged for regen.
    assert streamed[0]["conforms"] is None
    assert findings == []


def test_check_conformance_honors_cancel(project, monkeypatch):
    """should_cancel halts the per-card loop between cards."""
    from mtgai.analysis import conformance as conf_mod

    cards = [_make_card("W-C-01"), _make_card("W-C-02")]
    slots = {
        c.slot_id: {"slot_id": c.slot_id, "tweaked_text": "White common creature"} for c in cards
    }

    calls = {"n": 0}

    def fake_gate(**kwargs):
        calls["n"] += 1
        return {"result": {"conforms": True, "reason": ""}, "input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(conf_mod, "generate_gate_tool", fake_gate)
    monkeypatch.setattr(conf_mod, "cost_from_result", lambda r: 0.0)

    # Cancel before the second card.
    conf_mod.check_conformance(cards, slots, should_cancel=lambda: calls["n"] >= 1)
    assert calls["n"] == 1


def test_run_conformance_cancel_halts_before_interactions(project, monkeypatch):
    """A user Cancel during the per-card conformance pass must stop before the
    whole-set interactions LLM call and before flagging — otherwise a partial
    conformance pass + a full interactions pass stamp regen flags on a cancelled
    run (the opposite of the clean halt the other gates give)."""
    from mtgai.io.card_io import load_card, save_card
    from mtgai.runtime import ai_lock

    ai_lock.reset_for_tests()
    save_card(_make_card("W-C-01"), set_dir=project)

    def fake_conformance(cards, slots, **kw):
        # The user hits Cancel mid-pass; check_conformance breaks its loop and
        # returns whatever it found so far (here, a partial flag).
        ai_lock.request_cancel()
        return (
            [ConformanceFinding(slot_id="W-C-01", card_name="Card W-C-01", reason="partial")],
            "partial analysis",
            0.01,
        )

    interaction_calls: list[int] = []

    def fake_interactions(cards, mechanics):
        interaction_calls.append(1)
        return ([], "pool clean", 0.0)

    monkeypatch.setattr("mtgai.analysis.conformance.check_conformance", fake_conformance)
    monkeypatch.setattr("mtgai.analysis.interactions.analyze_interactions", fake_interactions)
    monkeypatch.setattr(stages_mod, "make_poller", lambda *a, **k: contextlib.nullcontext())

    result = stages_mod.run_conformance(None, _Emitter())

    assert result.success is False
    assert "cancelled" in (result.error_message or "").lower()
    # The interactions LLM call never ran.
    assert interaction_calls == []
    # No card was flagged (the partial conformance finding was discarded).
    card = load_card(next((project / "cards").glob("*.json")))
    assert card.flagged_by is None
    assert card.regen_reason is None

    ai_lock.reset_for_tests()


def test_run_conformance_clean_pass_advances(project, monkeypatch):
    from mtgai.io.card_io import save_card

    save_card(_make_card("W-C-01"), set_dir=project)
    monkeypatch.setattr(
        "mtgai.analysis.conformance.check_conformance",
        lambda cards, slots, **kw: ([], "all conform", 0.0),
    )
    monkeypatch.setattr(
        "mtgai.analysis.interactions.analyze_interactions",
        lambda cards, mechanics: ([], "pool clean", 0.0),
    )
    monkeypatch.setattr(stages_mod, "make_poller", lambda *a, **k: contextlib.nullcontext())

    result = stages_mod.run_conformance(None, _Emitter())

    assert result.rerun_from is None
    assert result.artifacts["passed"] is True
    assert all(s["passed"] for s in result.artifacts["steps"])
    assert result.artifacts["flagged"] == []


def test_check_conformance_pre_flagged_seeds_x_and_skips_llm(project, monkeypatch):
    """A pre_flagged (duplicate) card seeds an X, skips its LLM call, and is a finding."""
    from mtgai.analysis import conformance as conf_mod

    cards = [_make_card("W-C-01"), _make_card("W-C-02")]
    slots = {
        c.slot_id: {"slot_id": c.slot_id, "tweaked_text": "White common creature"} for c in cards
    }

    calls = {"n": 0}

    def fake_gate(**kwargs):
        calls["n"] += 1
        return {"result": {"conforms": True, "reason": ""}, "input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(conf_mod, "generate_gate_tool", fake_gate)
    monkeypatch.setattr(conf_mod, "cost_from_result", lambda r: 0.0)

    started: list[list[dict]] = []
    streamed: list[dict] = []
    findings, _analysis, _cost = conf_mod.check_conformance(
        cards,
        slots,
        pre_flagged={"W-C-02": "Functionally identical to Card W-C-01 (ignoring mana cost)."},
        on_start=lambda lst: started.append(lst),
        on_card=lambda rec: streamed.append(rec),
    )

    # Only the non-duplicate card hit the LLM; the duplicate skipped it.
    assert calls["n"] == 1
    # The duplicate is seeded in the up-front list as conforms=False (an X) + reason.
    by_slot = {c["slot_id"]: c for c in started[0]}
    assert by_slot["W-C-02"]["conforms"] is False
    assert "Functionally identical" in by_slot["W-C-02"]["reason"]
    # The non-duplicate carries no seeded verdict (renders pending).
    assert "conforms" not in by_slot["W-C-01"]
    # The duplicate is returned as a finding with the duplicate reason.
    assert [f.slot_id for f in findings] == ["W-C-02"]
    assert "Functionally identical" in findings[0].reason
    # It also streamed as a failed card row.
    dup_rec = next(r for r in streamed if r["slot_id"] == "W-C-02")
    assert dup_rec["conforms"] is False


def test_run_conformance_folds_duplicates_into_conformance(project, monkeypatch):
    """Two functionally-identical cards: the duplicate is flagged via conformance."""
    from mtgai.analysis import conformance as conf_mod
    from mtgai.io.card_io import load_card, save_card

    # Identical text/type/stats, differing only in collector number + mana cost.
    save_card(_dup_card("W-C-01", oracle="Flying", mana="{1}{W}"), set_dir=project)
    save_card(_dup_card("W-C-02", oracle="Flying", mana="{3}{W}"), set_dir=project)
    # Give both slots a spec so the kept card runs the real conformance path.
    skeleton = {
        "slots": [
            {"slot_id": "W-C-01", "tweaked_text": "White common flyer"},
            {"slot_id": "W-C-02", "tweaked_text": "White common flyer"},
        ]
    }
    (project / "skeleton.json").write_text(json.dumps(skeleton), encoding="utf-8")

    # The kept card (W-C-01) conforms; the duplicate (W-C-02) never reaches the LLM.
    def fake_gate(**kwargs):
        return {"result": {"conforms": True, "reason": ""}, "input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(conf_mod, "generate_gate_tool", fake_gate)
    monkeypatch.setattr(conf_mod, "cost_from_result", lambda r: 0.0)
    monkeypatch.setattr(
        "mtgai.analysis.interactions.analyze_interactions",
        lambda cards, mechanics: ([], "pool clean", 0.0),
    )
    monkeypatch.setattr(stages_mod, "make_poller", lambda *a, **k: contextlib.nullcontext())

    result = stages_mod.run_conformance(None, _Emitter())

    # Only two sections; the duplicate folds into conformance, no separate step.
    steps = result.artifacts["steps"]
    assert [s["id"] for s in steps] == ["conformance", "interactions"]
    # The duplicate W-C-02 is flagged through the conformance step.
    conf = steps[0]
    assert {f["slot_id"] for f in conf["flagged"]} == {"W-C-02"}
    assert "Functionally identical" in conf["flagged"][0]["reason"]
    assert result.rerun_from == "card_gen"

    flagged_slots = {f["slot_id"] for f in result.artifacts["flagged"]}
    assert flagged_slots == {"W-C-02"}
    cards_by_slot = {load_card(p).slot_id: load_card(p) for p in (project / "cards").glob("*.json")}
    dup_card = cards_by_slot["W-C-02"]
    assert dup_card.flagged_by == "conformance"
    assert "Functionally identical" in (dup_card.regen_reason or "")


# ----------------------------------------------------------------------
# Duplicate Check — algorithmic functional-duplicate scan
# ----------------------------------------------------------------------


def _dup_card(
    slot_id: str, *, oracle: str, type_line: str = "Creature — Test", mana: str = "{1}{G}"
):
    from mtgai.models.card import Card

    return Card(
        name=f"Card {slot_id}",
        slot_id=slot_id,
        collector_number=slot_id,
        type_line=type_line,
        mana_cost=mana,
        oracle_text=oracle,
    )


def test_find_duplicates_flags_all_but_lowest_collector():
    from mtgai.analysis.duplicates import find_duplicates

    # Three functionally identical cards differing only in mana cost; the lowest
    # collector number (01) is kept and the other two are flagged.
    cards = [
        _dup_card("02", oracle="Flying", mana="{2}{G}"),
        _dup_card("01", oracle="Flying", mana="{1}{G}"),
        _dup_card("03", oracle="Flying", mana="{3}{G}"),
    ]
    findings, analysis = find_duplicates(cards)

    assert {f.slot_id for f in findings} == {"02", "03"}
    assert all(f.duplicate_of == "Card 01" for f in findings)
    assert "duplicate group" in analysis


def test_find_duplicates_ignores_keyword_order():
    from mtgai.analysis.duplicates import find_duplicates

    # "Flying, vigilance" vs "Vigilance, flying" normalize to the same signature.
    cards = [
        _dup_card("01", oracle="Flying, vigilance"),
        _dup_card("02", oracle="Vigilance, flying"),
    ]
    findings, _ = find_duplicates(cards)
    assert [f.slot_id for f in findings] == ["02"]


def test_find_duplicates_ignores_mana_cost_only():
    from mtgai.analysis.duplicates import find_duplicates

    # Identical text + type + stats, only the mana cost differs -> duplicate.
    a = _dup_card("01", oracle="Draw a card.", mana="{2}{U}")
    b = _dup_card("02", oracle="Draw a card.", mana="{4}{U}")
    findings, _ = find_duplicates([a, b])
    assert [f.slot_id for f in findings] == ["02"]


def test_find_duplicates_distinct_text_is_clean():
    from mtgai.analysis.duplicates import find_duplicates

    cards = [
        _dup_card("01", oracle="Draw a card."),
        _dup_card("02", oracle="Gain 3 life."),
    ]
    findings, analysis = find_duplicates(cards)
    assert findings == []
    assert "No functional duplicates" in analysis


def test_find_duplicates_distinct_type_or_stats_is_clean():
    from mtgai.analysis.duplicates import find_duplicates

    # Same text but different type lines -> not duplicates.
    cards = [
        _dup_card("01", oracle="Flying", type_line="Creature — Bird"),
        _dup_card("02", oracle="Flying", type_line="Creature — Drake"),
    ]
    findings, _ = find_duplicates(cards)
    assert findings == []


def test_find_duplicates_folds_self_name_reference():
    from mtgai.analysis.duplicates import find_duplicates
    from mtgai.models.card import Card

    # Each card refers to itself by its own name; folding the name to a token
    # makes the two texts identical.
    a = Card(
        name="Alpha",
        slot_id="01",
        collector_number="01",
        type_line="Creature — Test",
        mana_cost="{1}{R}",
        oracle_text="Whenever Alpha attacks, draw a card.",
    )
    b = Card(
        name="Beta",
        slot_id="02",
        collector_number="02",
        type_line="Creature — Test",
        mana_cost="{2}{R}",
        oracle_text="Whenever Beta attacks, draw a card.",
    )
    findings, _ = find_duplicates([a, b])
    assert [f.slot_id for f in findings] == ["02"]


def test_find_duplicates_skips_basics_and_reprints():
    from mtgai.analysis.duplicates import find_duplicates
    from mtgai.models.card import Card

    forest_a = Card(
        name="Forest",
        slot_id="L-01",
        collector_number="L-01",
        type_line="Basic Land — Forest",
        supertypes=["Basic"],
        card_types=["Land"],
        subtypes=["Forest"],
        oracle_text="",
    )
    forest_b = Card(
        name="Forest",
        slot_id="L-02",
        collector_number="L-02",
        type_line="Basic Land — Forest",
        supertypes=["Basic"],
        card_types=["Land"],
        subtypes=["Forest"],
        oracle_text="",
    )
    reprint_a = _dup_card("R1", oracle="Flying")
    reprint_a = reprint_a.model_copy(update={"is_reprint": True})
    reprint_b = _dup_card("R2", oracle="Flying")
    reprint_b = reprint_b.model_copy(update={"is_reprint": True})

    findings, _ = find_duplicates([forest_a, forest_b, reprint_a, reprint_b])
    assert findings == []
