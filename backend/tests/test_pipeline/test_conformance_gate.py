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
    # ``instance_id`` defaults to the backbone gate id, so run_conformance scopes
    # to the whole pool (recheck is None) — what every test here but the
    # later-instance scoping ones expect.
    def __init__(self, instance_id: str = "conformance"):
        self.instance_id = instance_id
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
        lambda cards, mechanics, **kw: (
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
    # conformance_step per step. The algorithmic economy analysis streams first
    # (right after the no-LLM duplicate scan, before the LLM steps), then
    # conformance, then interactions. The duplicate check has no section of its
    # own — its hits fold into conformance.
    assert [t for t, _ in emitter.events] == [
        "conformance_reset",
        "conformance_step",
        "conformance_step",
        "conformance_step",
    ]
    streamed = [d["step"]["id"] for t, d in emitter.events if t == "conformance_step"]
    assert streamed == ["economy", "conformance", "interactions"]

    steps = result.artifacts["steps"]
    assert [s["id"] for s in steps] == ["conformance", "interactions", "economy"]
    conf, inter, economy = steps
    assert economy["id"] == "economy"
    assert "resources" in economy["report"]
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


def _fake_stream(flag_map: dict[str, str], *, stop_reason: str = "stop"):
    """A ``stream_text`` stand-in for the batched conformance scan.

    Emits a ``--CARD <id>--`` block (with its reason) for each slot in
    ``flag_map`` that appears in the batch's user prompt, then one ``complete``
    event carrying ``stop_reason`` (use ``"length"`` to simulate truncation).
    Counts invocations on the returned function's ``calls`` attribute.
    """

    def stream_text(**kwargs):
        user_prompt = kwargs.get("user_prompt", "")
        stream_text.calls += 1
        text = "".join(
            f"--CARD {sid}--\n{reason}\n"
            for sid, reason in flag_map.items()
            if f"--SLOT {sid}--" in user_prompt
        )
        if text:
            yield {"type": "text_delta", "text": text}
        yield {
            "type": "complete",
            "text": text,
            "stop_reason": stop_reason,
            "input_tokens": 5,
            "output_tokens": 5,
            "model": kwargs.get("model", "m"),
        }

    stream_text.calls = 0
    return stream_text


def test_check_conformance_batches_and_streams(project, monkeypatch):
    """check_conformance streams batched flag-only blocks into a live checklist."""
    from mtgai.analysis import conformance as conf_mod

    cards = [_make_card("W-C-01"), _make_card("W-C-02"), _make_card("W-C-03")]
    slots = {
        c.slot_id: {"slot_id": c.slot_id, "tweaked_text": "White common creature"} for c in cards
    }

    # All three cards fit one batch; the model flags only the 2nd.
    fake = _fake_stream({"W-C-02": "wrong color"})
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.01)

    started: list[list[dict]] = []
    streamed: list[dict] = []
    findings, analysis, cost = conf_mod.check_conformance(
        cards,
        slots,
        on_start=lambda lst: started.append(lst),
        on_card=lambda rec: streamed.append(rec),
    )

    # One streamed call for the whole batch (not one per card).
    assert fake.calls == 1
    # on_start fired once with the full card list (names only) up front.
    assert len(started) == 1
    assert [c["slot_id"] for c in started[0]] == ["W-C-01", "W-C-02", "W-C-03"]
    # on_card fired once per card, in listing order: the flag for W-C-02 advances
    # the approved frontier (W-C-01 ✓), then W-C-02 ✗, then W-C-03 ✓ at batch end.
    assert [(r["slot_id"], r["conforms"]) for r in streamed] == [
        ("W-C-01", True),
        ("W-C-02", False),
        ("W-C-03", True),
    ]
    # Only the flagged card becomes a finding.
    assert [f.slot_id for f in findings] == ["W-C-02"]
    assert findings[0].reason == "wrong color"
    assert cost == pytest.approx(0.01)
    assert "2/3" in analysis


def test_check_conformance_drops_conforms_block(project, monkeypatch):
    """A --CARD block whose body says the card CONFORMS is dropped, not flagged.

    The local model sometimes ignores the flag-only contract and emits a block
    for a conforming card too ("... Conforms."). The parser guard must treat that
    as a non-flag so the good card is not needlessly regenerated."""
    from mtgai.analysis import conformance as conf_mod

    cards = [_make_card("W-C-01"), _make_card("W-C-02")]
    slots = {
        c.slot_id: {"slot_id": c.slot_id, "tweaked_text": "White common creature"} for c in cards
    }

    # The model emits a block for W-C-01 affirming it conforms (a false flag).
    fake = _fake_stream({"W-C-01": "Spec calls for white common creature; card matches. Conforms."})
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    streamed: list[dict] = []
    findings, analysis, _cost = conf_mod.check_conformance(
        cards, slots, on_card=lambda rec: streamed.append(rec)
    )

    # The "Conforms" block was dropped: nothing flagged, both cards conform.
    assert findings == []
    assert "2/2" in analysis
    assert {(r["slot_id"], r["conforms"]) for r in streamed} == {
        ("W-C-01", True),
        ("W-C-02", True),
    }


def test_check_conformance_keeps_real_flag_mentioning_conform(project, monkeypatch):
    """A genuine non-conformance that NEGATES conform ("does not conform") is kept."""
    from mtgai.analysis import conformance as conf_mod

    cards = [_make_card("W-C-01"), _make_card("W-C-02")]
    slots = {
        c.slot_id: {"slot_id": c.slot_id, "tweaked_text": "White common creature"} for c in cards
    }

    fake = _fake_stream({"W-C-02": "Does not conform: card is blue, spec wants white."})
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    findings, _analysis, _cost = conf_mod.check_conformance(cards, slots)
    assert [f.slot_id for f in findings] == ["W-C-02"]


def test_check_conformance_keeps_partial_conformance_flag(project, monkeypatch):
    """A real flag that says the card 'conforms' only partially must NOT be dropped.

    The prompt's own non-conformance vocabulary ("Ignores a theme constraint") and
    qualifiers like "only"/"otherwise" appear alongside "conforms" in genuine
    flags; the guard keeps them (the dangerous false-negative direction)."""
    from mtgai.analysis import conformance as conf_mod

    cards = [_make_card("W-C-01"), _make_card("W-C-02")]
    slots = {
        c.slot_id: {"slot_id": c.slot_id, "tweaked_text": "White common creature"} for c in cards
    }

    fake = _fake_stream({"W-C-02": "Conforms in color only; ignores the assigned mechanic."})
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    findings, _analysis, _cost = conf_mod.check_conformance(cards, slots)
    assert [f.slot_id for f in findings] == ["W-C-02"]


def test_check_conformance_truncation_marks_unknown(project, monkeypatch):
    """A batch that keeps truncating leaves its unreached cards unknown, not flagged."""
    from mtgai.analysis import conformance as conf_mod

    cards = [_make_card("W-C-01"), _make_card("W-C-02")]
    slots = {
        c.slot_id: {"slot_id": c.slot_id, "tweaked_text": "White common creature"} for c in cards
    }

    # Every attempt truncates with no flag blocks emitted.
    fake = _fake_stream({}, stop_reason="length")
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    streamed: list[dict] = []
    findings, analysis, _cost = conf_mod.check_conformance(
        cards, slots, on_card=lambda rec: streamed.append(rec)
    )

    # Retried up to the budget, then both cards reported unknown (not flagged).
    assert fake.calls == gate_common.MAX_BATCH_ATTEMPTS
    assert all(r["conforms"] is None for r in streamed)
    assert findings == []
    assert "could not be checked" in analysis


def test_check_conformance_retry_recovers(project, monkeypatch):
    """A truncated batch is re-rolled; a clean retry yields verdicts."""
    from mtgai.analysis import conformance as conf_mod

    cards = [_make_card("W-C-01"), _make_card("W-C-02")]
    slots = {
        c.slot_id: {"slot_id": c.slot_id, "tweaked_text": "White common creature"} for c in cards
    }

    state = {"n": 0}

    def fake(**kwargs):
        state["n"] += 1
        truncated = state["n"] == 1
        text = "" if truncated else "--CARD W-C-02--\nwrong color\n"
        if text:
            yield {"type": "text_delta", "text": text}
        yield {
            "type": "complete",
            "text": text,
            "stop_reason": "length" if truncated else "stop",
            "input_tokens": 1,
            "output_tokens": 1,
            "model": "m",
        }

    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    findings, analysis, _cost = conf_mod.check_conformance(cards, slots)

    assert state["n"] == 2  # one truncation, then a clean retry
    assert [f.slot_id for f in findings] == ["W-C-02"]
    assert "1/2" in analysis


def test_check_conformance_honors_cancel(project, monkeypatch):
    """should_cancel halts the loop between batches."""
    from mtgai.analysis import conformance as conf_mod

    cards = [_make_card("W-C-01"), _make_card("W-C-02")]
    slots = {
        c.slot_id: {"slot_id": c.slot_id, "tweaked_text": "White common creature"} for c in cards
    }

    # One card per batch so the cancel check between batches is meaningful.
    monkeypatch.setattr(conf_mod, "BATCH_SIZE", 1)
    fake = _fake_stream({})
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    # Cancel before the second batch.
    conf_mod.check_conformance(cards, slots, should_cancel=lambda: fake.calls >= 1)
    assert fake.calls == 1


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

    def fake_interactions(cards, mechanics, **kw):
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
        lambda cards, mechanics, **kw: ([], "pool clean", 0.0),
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

    # The non-duplicate card conforms (empty stream); the duplicate skips the LLM.
    fake = _fake_stream({})
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    started: list[list[dict]] = []
    streamed: list[dict] = []
    findings, analysis, _cost = conf_mod.check_conformance(
        cards,
        slots,
        pre_flagged={"W-C-02": "Functionally identical to Card W-C-01 (ignoring mana cost)."},
        on_start=lambda lst: started.append(lst),
        on_card=lambda rec: streamed.append(rec),
    )

    # Only the non-duplicate card hit the LLM (one batch); the duplicate skipped it.
    assert fake.calls == 1
    # The summary denominator excludes the pre-flagged duplicate (it never ran
    # the conformance check): 1 checked, 1 conforms — not "1/2".
    assert analysis == "1/1 cards conform."
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

    # The kept card (W-C-01) conforms (empty stream); the duplicate (W-C-02)
    # never reaches the LLM — it's pre-flagged by the algorithmic duplicate scan.
    monkeypatch.setattr(gate_common, "stream_text", _fake_stream({}))
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)
    monkeypatch.setattr(
        "mtgai.analysis.interactions.analyze_interactions",
        lambda cards, mechanics, **kw: ([], "pool clean", 0.0),
    )
    monkeypatch.setattr(stages_mod, "make_poller", lambda *a, **k: contextlib.nullcontext())

    result = stages_mod.run_conformance(None, _Emitter())

    # The duplicate folds into conformance (no separate step); the economy
    # analysis is the always-present third algorithmic step.
    steps = result.artifacts["steps"]
    assert [s["id"] for s in steps] == ["conformance", "interactions", "economy"]
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
# analyze_interactions: batched cumulative-context streamed scan
# ----------------------------------------------------------------------


def _fake_inter_stream(enablers: dict[str, tuple[str, str]], *, stop_reason: str = "stop"):
    """A ``stream_text`` stand-in for the batched interaction scan.

    ``enablers`` maps ``slot_id -> (reason, avoid)``. A block is emitted for an
    enabler only in the batch where it appears in the "New cards to check"
    section (so a cumulative-context enabler is flagged once, when it is new).
    Records each batch's user prompt on the returned function's ``prompts``.
    """

    def stream_text(**kwargs):
        up = kwargs.get("user_prompt", "")
        stream_text.prompts.append(up)
        stream_text.calls += 1
        new_section = up.split("## New cards to check")[-1]
        text = ""
        for sid, (reason, avoid) in enablers.items():
            if f"{sid} |" in new_section:
                text += f"--CARD {sid}--\n{reason}\nAVOID: {avoid}\n"
        if text:
            yield {"type": "text_delta", "text": text}
        yield {
            "type": "complete",
            "text": text,
            "stop_reason": stop_reason,
            "input_tokens": 5,
            "output_tokens": 5,
            "model": kwargs.get("model", "m"),
        }

    stream_text.calls = 0
    stream_text.prompts = []
    return stream_text


def test_analyze_interactions_batches_and_streams(project, monkeypatch):
    """analyze_interactions streams a per-card interaction verdict, flagging enablers."""
    from mtgai.analysis import interactions as inter_mod

    cards = [_make_card("W-C-01"), _make_card("W-C-02"), _make_card("W-C-03")]

    fake = _fake_inter_stream({"W-C-02": ("infinite loop with W-C-01", "no free untap")})
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.01)

    started: list[list[dict]] = []
    streamed: list[dict] = []
    flags, analysis, cost = inter_mod.analyze_interactions(
        cards,
        [],
        on_start=lambda lst: started.append(lst),
        on_card=lambda rec: streamed.append(rec),
    )

    # One batch (3 < BATCH_SIZE) -> one streamed call.
    assert fake.calls == 1
    # Seed listed every card up front.
    assert [c["slot_id"] for c in started[0]] == ["W-C-01", "W-C-02", "W-C-03"]
    # The enabler is flagged with its reason + replacement constraint.
    assert [f.enabler_slot_id for f in flags] == ["W-C-02"]
    assert flags[0].replacement_constraint == "no free untap"
    assert "infinite loop" in flags[0].reason
    # Per-card verdicts: the enabler flagged, the others checked clean.
    by_slot = {r["slot_id"]: r["interacts"] for r in streamed}
    assert by_slot == {"W-C-01": True, "W-C-02": False, "W-C-03": True}
    assert cost == pytest.approx(0.01)
    assert "1 degenerate interaction" in analysis


def test_analyze_interactions_cumulative_context(project, monkeypatch):
    """Each batch sees the prior batches' cards as existing context."""
    from mtgai.analysis import interactions as inter_mod

    cards = [_make_card(f"W-C-0{i}") for i in range(1, 6)]  # 5 cards
    monkeypatch.setattr(inter_mod, "BATCH_SIZE", 2)
    fake = _fake_inter_stream({})
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    inter_mod.analyze_interactions(cards, [])

    # 5 cards / 2 per batch = 3 batches.
    assert fake.calls == 3
    # Batch 1: no existing context. Batch 2: the first 2 cards are existing.
    assert "None yet" in fake.prompts[0]
    assert "Existing cards (2)" in fake.prompts[1]
    assert "Existing cards (4)" in fake.prompts[2]


def test_analyze_interactions_truncation_marks_unknown(project, monkeypatch):
    """A batch that keeps truncating leaves its new cards' interaction verdict unknown."""
    from mtgai.analysis import interactions as inter_mod

    cards = [_make_card("W-C-01"), _make_card("W-C-02")]
    fake = _fake_inter_stream({}, stop_reason="length")
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    streamed: list[dict] = []
    flags, _analysis, _cost = inter_mod.analyze_interactions(
        cards, [], on_card=lambda rec: streamed.append(rec)
    )

    assert fake.calls == gate_common.MAX_BATCH_ATTEMPTS
    assert all(r["interacts"] is None for r in streamed)
    assert flags == []


def test_analyze_interactions_drops_no_interaction_block(project, monkeypatch):
    """A --CARD block with no AVOID line saying "no interaction" is dropped.

    Mirrors the conformance false-flag guard for the interactions step: a drifting
    model emitting a block for a clean card must not flag its enabler for regen."""
    from mtgai.analysis import interactions as inter_mod

    cards = [_make_card("W-C-01"), _make_card("W-C-02")]

    def fake(**kwargs):
        fake.calls += 1
        # The model emits a (false) block for W-C-01 with no AVOID + a clean verdict.
        text = "--CARD W-C-01--\nNo degenerate interaction found.\n"
        yield {"type": "text_delta", "text": text}
        yield {
            "type": "complete",
            "text": text,
            "stop_reason": "stop",
            "input_tokens": 1,
            "output_tokens": 1,
            "model": "m",
        }

    fake.calls = 0
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    streamed: list[dict] = []
    flags, _analysis, _cost = inter_mod.analyze_interactions(
        cards, [], on_card=lambda rec: streamed.append(rec)
    )

    # The clean block was dropped: no enabler flagged, both cards checked clean.
    assert flags == []
    assert {(r["slot_id"], r["interacts"]) for r in streamed} == {
        ("W-C-01", True),
        ("W-C-02", True),
    }


def test_analyze_interactions_keeps_combo_opening_clean(project, monkeypatch):
    """A real combo flag that OPENS with clean-sounding words (and has no AVOID
    line) must NOT be dropped — the prompt invites "fine on its own but combos…"
    phrasing, the dangerous false-negative direction."""
    from mtgai.analysis import interactions as inter_mod

    cards = [_make_card("W-C-01"), _make_card("W-C-02")]

    def fake(**kwargs):
        fake.calls += 1
        # Opens "Fine alone" but describes a real loop, with no AVOID line.
        text = "--CARD W-C-01--\nFine alone, but loops with W-C-02 for infinite mana.\n"
        yield {"type": "text_delta", "text": text}
        yield {
            "type": "complete",
            "text": text,
            "stop_reason": "stop",
            "input_tokens": 1,
            "output_tokens": 1,
            "model": "m",
        }

    fake.calls = 0
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    flags, _analysis, _cost = inter_mod.analyze_interactions(cards, [])

    # The combo flag was kept: W-C-01 is flagged as the enabler.
    assert [f.enabler_slot_id for f in flags] == ["W-C-01"]
    assert "loops" in flags[0].reason


# ----------------------------------------------------------------------
# Later-instance scoping — re-check only newly regenerated cards
# ----------------------------------------------------------------------


def test_check_conformance_restrict_to_scopes_check(project, monkeypatch):
    """restrict_to limits the conformance check to the named cards only."""
    from mtgai.analysis import conformance as conf_mod

    cards = [_make_card("W-C-01"), _make_card("W-C-02"), _make_card("W-C-03")]
    slots = {
        c.slot_id: {"slot_id": c.slot_id, "tweaked_text": "White common creature"} for c in cards
    }
    fake = _fake_stream({})  # nothing flagged
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    started: list[list[dict]] = []
    findings, analysis, _cost = conf_mod.check_conformance(
        cards, slots, restrict_to={"W-C-02"}, on_start=lambda lst: started.append(lst)
    )

    # Only the in-scope card was ever listed/checked; the others were skipped.
    assert [c["slot_id"] for c in started[0]] == ["W-C-02"]
    assert findings == []
    assert analysis == "1/1 cards conform."


def test_analyze_interactions_new_only_uses_rest_as_context(project, monkeypatch):
    """new_only checks just the regenerated cards, with the rest as fixed context."""
    from mtgai.analysis import interactions as inter_mod

    cards = [_make_card("W-C-01"), _make_card("W-C-02"), _make_card("W-C-03")]
    fake = _fake_inter_stream({})
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    started: list[list[dict]] = []
    streamed: list[dict] = []
    inter_mod.analyze_interactions(
        cards,
        [],
        new_only={"W-C-02"},
        on_start=lambda lst: started.append(lst),
        on_card=lambda rec: streamed.append(rec),
    )

    # One streamed call: only W-C-02 is new; W-C-01 + W-C-03 ride along as context.
    assert fake.calls == 1
    assert [c["slot_id"] for c in started[0]] == ["W-C-02"]
    prompt = fake.prompts[0]
    assert "Existing cards (2)" in prompt
    new_section = prompt.split("## New cards to check")[-1]
    assert "W-C-02 |" in new_section
    assert "W-C-01 |" not in new_section and "W-C-03 |" not in new_section
    # Only the in-scope card gets a per-card verdict.
    assert [r["slot_id"] for r in streamed] == ["W-C-02"]


def test_analyze_interactions_flags_earlier_card_from_later_batch(project, monkeypatch):
    """Attribution fix (card 6a26ecc6): a LATER batch can name an EARLIER card as
    the enabler. A new payoff that merely uses an existing enabler must flag the
    enabler, not itself — so the flag lands on the earlier card, not the new one."""
    from mtgai.analysis import interactions as inter_mod

    cards = [_make_card(f"W-C-0{i}") for i in range(1, 5)]  # 4 cards
    monkeypatch.setattr(inter_mod, "BATCH_SIZE", 2)

    def fake(**kwargs):
        fake.calls += 1
        new_section = kwargs.get("user_prompt", "").split("## New cards to check")[-1]
        # Only when the batch-2 payoff W-C-03 appears do we blame the batch-1
        # enabler W-C-01 (an existing-context card by then).
        text = ""
        if "W-C-03 |" in new_section:
            text = (
                "--CARD W-C-01--\n"
                "W-C-03 abuses W-C-01's free untap for an infinite loop.\n"
                "AVOID: no free untap\n"
            )
        if text:
            yield {"type": "text_delta", "text": text}
        yield {
            "type": "complete",
            "text": text,
            "stop_reason": "stop",
            "input_tokens": 1,
            "output_tokens": 1,
            "model": "m",
        }

    fake.calls = 0
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    streamed: list[dict] = []
    flags, _analysis, _cost = inter_mod.analyze_interactions(
        cards, [], on_card=lambda rec: streamed.append(rec)
    )

    assert fake.calls == 2  # 4 cards / 2 per batch
    # The flag lands on the EARLIER enabler W-C-01, not the new payoff W-C-03.
    assert [f.enabler_slot_id for f in flags] == ["W-C-01"]
    assert flags[0].replacement_constraint == "no free untap"
    # W-C-01 ends up flagged (✗) even though it was checked clean in batch 1;
    # the new payoff W-C-03 is itself checked clean (✓).
    by_slot = {r["slot_id"]: r["interacts"] for r in streamed}
    assert by_slot["W-C-01"] is False
    assert by_slot["W-C-03"] is True


def test_analyze_interactions_scoped_flags_existing_context_enabler(project, monkeypatch):
    """Attribution fix on a SCOPED re-run: a regenerated card can flag an EXISTING
    context card (not itself in scope) as the enabler — the root cause is an old
    card the regen exposed. The flag still lands on the existing enabler."""
    from mtgai.analysis import interactions as inter_mod

    cards = [_make_card("W-C-01"), _make_card("W-C-02"), _make_card("W-C-03")]

    def fake(**kwargs):
        fake.calls += 1
        text = (
            "--CARD W-C-01--\n"
            "W-C-03 + W-C-01 form a degenerate recursion loop.\n"
            "AVOID: no free recursion\n"
        )
        yield {"type": "text_delta", "text": text}
        yield {
            "type": "complete",
            "text": text,
            "stop_reason": "stop",
            "input_tokens": 1,
            "output_tokens": 1,
            "model": "m",
        }

    fake.calls = 0
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    started: list[list[dict]] = []
    streamed: list[dict] = []
    flags, _analysis, _cost = inter_mod.analyze_interactions(
        cards,
        [],
        new_only={"W-C-03"},
        on_start=lambda lst: started.append(lst),
        on_card=lambda rec: streamed.append(rec),
    )

    # Only the regenerated W-C-03 is seeded/in-scope, but the flag lands on the
    # existing context card W-C-01 — the validated enabler space is the whole pool.
    assert [c["slot_id"] for c in started[0]] == ["W-C-03"]
    assert [f.enabler_slot_id for f in flags] == ["W-C-01"]
    by_slot = {r["slot_id"]: r["interacts"] for r in streamed}
    assert by_slot["W-C-01"] is False  # existing enabler surfaced as flagged
    assert by_slot["W-C-03"] is True


def test_interaction_prompt_encodes_precision_and_attribution_guidance():
    """The interactions prompt must retain the rate-limiter / rarity / root-cause
    enabler guidance — the durable contract behind the two precision+attribution
    bugs (6a26ec63 false-positives, 6a26ecc6 attribution bias)."""
    from mtgai.analysis import interactions as inter_mod

    p = inter_mod.INTERACTION_SYSTEM_PROMPT.lower()
    # 6a26ec63: respect explicit rate limiters before claiming a loop.
    assert "once each turn" in p
    assert "limiter" in p
    # 6a26ec63: rarity-aware power tolerance (strong at rare/mythic is fine).
    assert "rarity" in p and "mythic" in p
    # 6a26ecc6: attribute to the root-cause enabler, which may be an existing card.
    assert "enabler" in p
    assert "root cause" in p
    assert "existing" in p


# ----------------------------------------------------------------------
# Low-context bounding — the cumulative existing-context is trimmed to the
# assigned model's actual context window (card 5rK8AkcW).
# ----------------------------------------------------------------------


def _fake_count_by_cards(*, base: int = 100, per_card: int = 50):
    """A ``count_messages_tokens`` stand-in: ``base`` + ``per_card`` x (number of
    cards in the user message). Each serialized card line contains "| Card " (its
    name is ``Card <slot_id>``), so counting that substring counts the cards
    present — deterministic, independent of the real tokenizer."""

    def count(messages, tools=None):
        user = next(m["content"] for m in messages if m["role"] == "user")
        return base + per_card * user.count("| Card ")

    return count


def test_bound_existing_context_large_window_keeps_all(monkeypatch):
    """A roomy window drops nothing — full cross-batch coverage preserved."""
    from mtgai.analysis import interactions as inter_mod

    monkeypatch.setattr(inter_mod, "get_context_window", lambda m: 200_000)
    monkeypatch.setattr(inter_mod, "count_messages_tokens", _fake_count_by_cards())
    existing = [_make_card(f"C-{i}") for i in range(5)]

    kept, dropped = inter_mod._bound_existing_context(existing, [], [], model="m", output_reserve=0)
    assert dropped == 0
    assert [c.slot_id for c in kept] == [c.slot_id for c in existing]


def test_bound_existing_context_small_window_keeps_recent_tail(monkeypatch):
    """A tight window keeps only the most-recent cards (the tail), dropping the
    rest — the sliding-window behaviour the low-context fix relies on."""
    from mtgai.analysis import interactions as inter_mod

    # count = 100 + 50 x cards; budget = int(232 x 0.95) - 0 = 220, so the most
    # cards that fit is k where 100 + 50k <= 220 -> k = 2 (250 > 220).
    monkeypatch.setattr(inter_mod, "get_context_window", lambda m: 232)
    monkeypatch.setattr(inter_mod, "count_messages_tokens", _fake_count_by_cards())
    existing = [_make_card(f"C-{i}") for i in range(5)]

    kept, dropped = inter_mod._bound_existing_context(existing, [], [], model="m", output_reserve=0)
    # The two most-recent cards (tail) are kept; the three oldest are dropped.
    assert [c.slot_id for c in kept] == ["C-3", "C-4"]
    assert dropped == 3


def test_bound_existing_context_tiny_window_drops_all(monkeypatch):
    """When even an empty existing-context overflows, no context is sent."""
    from mtgai.analysis import interactions as inter_mod

    # budget = int(100 x 0.95) = 95 < base 100, so even keep=0 doesn't fit.
    monkeypatch.setattr(inter_mod, "get_context_window", lambda m: 100)
    monkeypatch.setattr(inter_mod, "count_messages_tokens", _fake_count_by_cards())
    existing = [_make_card(f"C-{i}") for i in range(3)]

    kept, dropped = inter_mod._bound_existing_context(existing, [], [], model="m", output_reserve=0)
    assert kept == []
    assert dropped == 3


def test_analyze_interactions_low_context_bounds_existing(project, monkeypatch):
    """On a low-context model the cumulative scan bounds (here fully drops) its
    existing-context instead of overflowing: the largest batch no longer carries
    the full pool, and the run still completes (no card left interacts=None)."""
    from mtgai.analysis import interactions as inter_mod

    cards = [_make_card(f"W-C-0{i}") for i in range(1, 6)]  # 5 cards
    monkeypatch.setattr(inter_mod, "BATCH_SIZE", 2)
    # A window too small to hold the whole pool forces the bound on. With the real
    # MAX_TOKENS output reserve this fully drops the existing-context (the WARN
    # path); the deterministic partial-tail slide is covered by the unit test above.
    monkeypatch.setattr(inter_mod, "get_context_window", lambda m: 18_000)
    fake = _fake_inter_stream({})
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    streamed: list[dict] = []
    flags, _analysis, _cost = inter_mod.analyze_interactions(
        cards, [], on_card=lambda rec: streamed.append(rec)
    )

    assert fake.calls == 3  # 5 cards / 2 per batch
    # The last batch would carry 4 existing cards untrimmed; the bound dropped them.
    assert "Existing cards (4)" not in fake.prompts[2]
    # The scan still finished cleanly — every card got a real verdict, none unknown.
    assert flags == []
    assert all(r["interacts"] is True for r in streamed)


def test_analyze_interactions_new_only_empty_is_clean_noop(project, monkeypatch):
    """An empty new_only (nothing regenerated) makes no LLM call and passes."""
    from mtgai.analysis import interactions as inter_mod

    cards = [_make_card("W-C-01"), _make_card("W-C-02")]
    fake = _fake_inter_stream({})
    monkeypatch.setattr(gate_common, "stream_text", fake)
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)

    flags, _analysis, cost = inter_mod.analyze_interactions(cards, [], new_only=set())

    assert fake.calls == 0
    assert flags == []
    assert cost == 0.0


def _state(*instance_ids: str):
    from mtgai.pipeline.models import PipelineConfig, PipelineState, StageState

    stages = [
        StageState(stage_id=iid.split(".")[0], instance_id=iid, display_name=iid)
        for iid in instance_ids
    ]
    return PipelineState(config=PipelineConfig(set_code="ABC", set_name="ABC"), stages=stages)


def test_cards_to_recheck_backbone_checks_whole_pool(project, monkeypatch):
    """The backbone conformance instance scopes to None (the whole pool)."""
    from mtgai.pipeline import engine as engine_mod

    cards = [_make_card("W-C-01"), _make_card("W-C-02")]
    monkeypatch.setattr(engine_mod, "load_state", lambda: _state("card_gen", "conformance"))

    assert stages_mod._cards_to_recheck("conformance", cards) is None


def test_cards_to_recheck_later_instance_diffs_snapshot(project, monkeypatch):
    """A later instance scopes to the cards changed since the previous instance ran."""
    from mtgai.io.card_io import save_card
    from mtgai.pipeline import engine as engine_mod
    from mtgai.pipeline import history

    # Two cards present when the backbone conformance instance ran -> snapshot it.
    save_card(_make_card("W-C-01", oracle_text="Original one."), set_dir=project)
    save_card(_make_card("W-C-02", oracle_text="Original two."), set_dir=project)
    assert history.snapshot_instance("conformance") is True

    # card_gen.2 regenerates only W-C-02; the live pool now differs there.
    save_card(_make_card("W-C-02", oracle_text="Regenerated two."), set_dir=project)
    cards = [_make_card("W-C-01"), _make_card("W-C-02")]

    monkeypatch.setattr(
        engine_mod,
        "load_state",
        lambda: _state("card_gen", "conformance", "card_gen.2", "conformance.2"),
    )

    recheck = stages_mod._cards_to_recheck("conformance.2", cards)
    assert recheck == {"W-C-02"}


def test_cards_to_recheck_missing_snapshot_falls_back_to_whole_pool(project, monkeypatch):
    """No predecessor snapshot (pre-version-tracking) -> re-check everything (None)."""
    from mtgai.pipeline import engine as engine_mod

    cards = [_make_card("W-C-01")]
    monkeypatch.setattr(
        engine_mod,
        "load_state",
        lambda: _state("card_gen", "conformance", "card_gen.2", "conformance.2"),
    )
    # No history/conformance snapshot was written.
    assert stages_mod._cards_to_recheck("conformance.2", cards) is None


def test_run_conformance_later_instance_scopes_both_steps(project, monkeypatch):
    """run_conformance on a later instance passes the regenerated-card scope to
    both the conformance (restrict_to) and interactions (new_only) steps."""
    from mtgai.io.card_io import save_card
    from mtgai.pipeline import engine as engine_mod
    from mtgai.pipeline import history
    from mtgai.runtime import ai_lock

    ai_lock.reset_for_tests()

    save_card(_make_card("W-C-01", oracle_text="Original one."), set_dir=project)
    save_card(_make_card("W-C-02", oracle_text="Original two."), set_dir=project)
    assert history.snapshot_instance("conformance") is True
    # Only W-C-02 is regenerated since the backbone instance ran.
    save_card(_make_card("W-C-02", oracle_text="Regenerated two."), set_dir=project)

    monkeypatch.setattr(
        engine_mod,
        "load_state",
        lambda: _state("card_gen", "conformance", "card_gen.2", "conformance.2"),
    )

    seen: dict[str, set | None] = {}

    def fake_conformance(cards, slots, **kw):
        seen["restrict_to"] = kw.get("restrict_to")
        return ([], "all conform", 0.0)

    def fake_interactions(cards, mechanics, **kw):
        seen["new_only"] = kw.get("new_only")
        return ([], "pool clean", 0.0)

    monkeypatch.setattr("mtgai.analysis.conformance.check_conformance", fake_conformance)
    monkeypatch.setattr("mtgai.analysis.interactions.analyze_interactions", fake_interactions)
    monkeypatch.setattr(stages_mod, "make_poller", lambda *a, **k: contextlib.nullcontext())

    stages_mod.run_conformance(None, _Emitter(instance_id="conformance.2"))

    assert seen["restrict_to"] == {"W-C-02"}
    assert seen["new_only"] == {"W-C-02"}

    ai_lock.reset_for_tests()


def test_run_conformance_recheck_flags_regenerated_functional_duplicate(project, monkeypatch):
    """A recheck round where the regenerated card is a functional duplicate of a
    carried-over vetted twin AND holds the lower collector number: the regen card
    must be the one flagged, and that flag must survive the recheck scoping.

    Without the regen keep-bias the functional scan keeps the lower-numbered
    (regenerated) card and flags the carried-over twin — whose flag is then
    dropped because it isn't in the recheck set, shipping the duplicate.
    """
    from mtgai.io.card_io import load_card, save_card
    from mtgai.pipeline import engine as engine_mod
    from mtgai.pipeline import history
    from mtgai.runtime import ai_lock

    ai_lock.reset_for_tests()

    # Backbone ran with both cards distinct -> snapshot. W-C-02 is the vetted,
    # carried-over card (higher collector number).
    save_card(_dup_card("W-C-01", oracle="Unique original one."), set_dir=project)
    save_card(_dup_card("W-C-02", oracle="Flying"), set_dir=project)
    assert history.snapshot_instance("conformance") is True
    # card_gen.2 regenerates W-C-01 into a functional duplicate of W-C-02; the
    # regenerated card keeps the LOWER collector number (W-C-01 < W-C-02).
    save_card(_dup_card("W-C-01", oracle="Flying", mana="{3}{W}"), set_dir=project)

    monkeypatch.setattr(
        engine_mod,
        "load_state",
        lambda: _state("card_gen", "conformance", "card_gen.2", "conformance.2"),
    )

    # The LLM steps see nothing (the regen card is pre-flagged by the dup scan;
    # the carried-over card is out of the recheck scope).
    monkeypatch.setattr(gate_common, "stream_text", _fake_stream({}))
    monkeypatch.setattr(gate_common, "cost_from_result", lambda r: 0.0)
    monkeypatch.setattr(
        "mtgai.analysis.interactions.analyze_interactions",
        lambda cards, mechanics, **kw: ([], "pool clean", 0.0),
    )
    monkeypatch.setattr(stages_mod, "make_poller", lambda *a, **k: contextlib.nullcontext())

    result = stages_mod.run_conformance(None, _Emitter(instance_id="conformance.2"))

    # The REGENERATED card (W-C-01) is flagged, not the carried-over twin.
    flagged_slots = {f["slot_id"] for f in result.artifacts["flagged"]}
    assert flagged_slots == {"W-C-01"}
    assert result.rerun_from == "card_gen"
    cards_by_slot = {load_card(p).slot_id: load_card(p) for p in (project / "cards").glob("*.json")}
    assert "Functionally identical" in (cards_by_slot["W-C-01"].regen_reason or "")
    # The carried-over W-C-02 is untouched (no stale flag).
    assert cards_by_slot["W-C-02"].regen_reason in (None, "")

    ai_lock.reset_for_tests()


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


def test_find_duplicates_biases_flag_to_regenerated_card():
    from mtgai.analysis.duplicates import find_duplicates

    # The regenerated card (#01) took the LOWER collector number and is
    # functionally identical (modulo mana cost) to a carried-over vetted twin
    # (#02). Default keep-lowest would keep #01 and flag #02 — but #02 is not in
    # the regen recheck set, so its flag would be dropped downstream and the
    # duplicate would ship. The regen bias keeps the carried-over #02 and flags
    # the regenerated #01 (whose flag survives the recheck scoping).
    cards = [
        _dup_card("01", oracle="Flying", mana="{1}{G}"),
        _dup_card("02", oracle="Flying", mana="{3}{G}"),
    ]
    findings, _ = find_duplicates(cards, regenerating={"01"})
    assert [f.slot_id for f in findings] == ["01"]
    assert findings[0].duplicate_of == "Card 02"

    # Without the bias the lowest collector number is kept (default behaviour).
    findings_default, _ = find_duplicates(cards)
    assert [f.slot_id for f in findings_default] == ["02"]


def _named_card(slot_id: str, name: str, *, oracle: str = "Flying"):
    from mtgai.models.card import Card

    return Card(
        name=name,
        slot_id=slot_id,
        collector_number=slot_id,
        type_line="Creature — Test",
        mana_cost="{1}{G}",
        oracle_text=oracle,
    )


def test_find_duplicate_names_flags_all_but_lowest_collector():
    from mtgai.analysis.duplicates import find_duplicate_names

    # Two distinct cards (different function) sharing a name — the functional
    # scan misses this, but the name scan flags the higher collector number.
    cards = [
        _named_card("044", "Skyguard Ace", oracle="Flying"),
        _named_card("058", "Skyguard Ace", oracle="Vigilance, haste"),
    ]
    findings, analysis = find_duplicate_names(cards)

    assert [f.slot_id for f in findings] == ["058"]
    assert findings[0].duplicate_of == "Skyguard Ace"
    assert "Duplicate card name" in findings[0].reason
    assert "044" in findings[0].reason
    assert "share a name" in analysis


def test_find_duplicate_names_biases_flag_to_regenerated_card():
    from mtgai.analysis.duplicates import find_duplicate_names

    # The regenerated card (#044) took the LOWER collector number and collided
    # with a carried-over twin (#058). Default keep-lowest would keep #044 and
    # flag #058 — but #058 is not in the regen recheck set, so its flag would be
    # dropped downstream and the collision would ship. The regen bias keeps the
    # carried-over #058 and flags the regenerated #044 (which survives scoping).
    cards = [
        _named_card("044", "Skyguard Ace", oracle="Flying"),
        _named_card("058", "Skyguard Ace", oracle="Vigilance"),
    ]
    findings, _ = find_duplicate_names(cards, regenerating={"044"})
    assert [f.slot_id for f in findings] == ["044"]
    assert findings[0].duplicate_of == "Skyguard Ace"

    # Without the bias the lowest collector number is kept (default behaviour).
    findings_default, _ = find_duplicate_names(cards)
    assert [f.slot_id for f in findings_default] == ["058"]


def test_find_duplicate_names_is_case_insensitive():
    from mtgai.analysis.duplicates import find_duplicate_names

    cards = [
        _named_card("01", "Storm Crow"),
        _named_card("02", "STORM CROW"),
    ]
    findings, _ = find_duplicate_names(cards)
    assert [f.slot_id for f in findings] == ["02"]


def test_find_duplicate_names_distinct_names_are_clean():
    from mtgai.analysis.duplicates import find_duplicate_names

    cards = [
        _named_card("01", "Storm Crow"),
        _named_card("02", "Thunder Hawk"),
    ]
    findings, analysis = find_duplicate_names(cards)
    assert findings == []
    assert "No duplicate card names" in analysis


def test_find_duplicate_names_skips_basics_and_reprints():
    from mtgai.analysis.duplicates import find_duplicate_names
    from mtgai.models.card import Card

    # Two basic lands legitimately share the name "Forest" — never flagged.
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
    forest_b = forest_a.model_copy(update={"slot_id": "L-02", "collector_number": "L-02"})
    reprint_a = _named_card("R1", "Lightning Bolt").model_copy(update={"is_reprint": True})
    reprint_b = _named_card("R2", "Lightning Bolt").model_copy(update={"is_reprint": True})

    findings, _ = find_duplicate_names([forest_a, forest_b, reprint_a, reprint_b])
    assert findings == []
