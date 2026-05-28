"""Pins that every stage runner emits a terminal ``phase("done", ...)``.

Without this, the global progress strip (``#wiz-progress-strip``, driven by SSE
``phase`` events and replayed to late subscribers via the per-run event log)
stays stuck on the last ``phase("running", ...)`` whenever a stage finishes
into PAUSED_FOR_REVIEW — the ``pipeline_status`` terminal events the client
also listens to only hide the strip on ``completed | cancelled | failed``, not
``paused``.

The bug this regression-tests: ``run_card_gen`` used to skip the done emission,
so a successful card-gen pause left the strip showing "Generating cards from
skeleton slots" forever.
"""

from __future__ import annotations

import pytest

from mtgai.pipeline import stages
from mtgai.pipeline.events import StageEmitter


class _SpyEmitter(StageEmitter):
    """``StageEmitter`` subclass that records every ``.phase()`` + ``.event()``.

    Subclasses (rather than duck-types) so the runner's typed signature is
    happy and any sibling helpers keep their bus-less no-op behavior from
    the base class.
    """

    def __init__(self) -> None:
        super().__init__(None, "card_gen", 0.0)
        self.calls: list[tuple[str, str]] = []
        self.events: list[tuple[str, dict]] = []

    def phase(self, phase: str, activity: str, **_extra) -> None:
        self.calls.append((phase, activity))

    def event(self, event_type: str, **data) -> None:
        self.events.append((event_type, data))


@pytest.fixture(autouse=True)
def _reset_ai_lock():
    from mtgai.runtime import ai_lock

    ai_lock.reset_for_tests()
    yield
    ai_lock.reset_for_tests()


def _stub_generate_set_factory(result: dict):
    def stub(**_kwargs):
        return result

    return stub


def test_run_card_gen_emits_done_on_success(monkeypatch) -> None:
    """A normal (or cap-truncated) successful run must close out with
    ``phase("done", ...)`` so the global progress strip clears."""
    monkeypatch.setattr(
        "mtgai.generation.card_generator.generate_set",
        _stub_generate_set_factory(
            {
                "total_slots": 272,
                "filled": 15,
                "failed": 0,
                "cost_usd": 0.0,
                "summary": "Generated 15 cards in 141s ($0.0000)",
                "cancelled": False,
            }
        ),
    )

    spy = _SpyEmitter()
    result = stages.run_card_gen(progress_cb=None, emitter=spy)

    assert result.success is True
    phase_names = [name for name, _ in spy.calls]
    assert "done" in phase_names, f"missing terminal phase('done'); got {spy.calls}"
    # And the done activity carries the run summary (so the replay buffer
    # has a meaningful terminal message even though the client only reads
    # the phase name to clear the strip).
    done_activity = next(activity for name, activity in spy.calls if name == "done")
    assert "Generated 15" in done_activity


def test_run_card_gen_streams_card_event_per_save(monkeypatch) -> None:
    """The engine path must call ``emitter.event("card_gen_card", ...)`` per
    saved card so the Card Generation tab pops each card in live (the same
    streaming UX the manual /refresh endpoint provides). No reset event from
    the engine path — first runs start on an empty cards/ dir and a resume
    must keep existing cards on screen."""
    from mtgai.models.card import Card
    from mtgai.models.enums import Color, Rarity

    saved_cards = [
        Card(
            name=f"Card {i}",
            mana_cost="{1}{W}",
            cmc=2.0,
            type_line="Creature",
            oracle_text="",
            rarity=Rarity.COMMON,
            colors=[Color.WHITE],
            color_identity=[Color.WHITE],
            collector_number=f"{i:03d}",
            set_code="TST",
            card_types=["Creature"],
        )
        for i in (1, 2, 3)
    ]

    def stub(**kwargs):
        cb = kwargs.get("card_saved_callback")
        if cb is not None:
            for c in saved_cards:
                cb(c)
        return {
            "total_slots": 3,
            "filled": 3,
            "failed": 0,
            "cost_usd": 0.0,
            "summary": "Generated 3 cards",
            "cancelled": False,
        }

    monkeypatch.setattr("mtgai.generation.card_generator.generate_set", stub)

    spy = _SpyEmitter()
    result = stages.run_card_gen(progress_cb=None, emitter=spy)

    assert result.success is True
    card_events = [data for name, data in spy.events if name == "card_gen_card"]
    assert len(card_events) == 3
    assert [e["card"]["collector_number"] for e in card_events] == ["001", "002", "003"]
    # Tile shape is what /state would return — same source-of-truth helper.
    assert card_events[0]["card"]["name"] == "Card 1"
    assert card_events[0]["card"]["rarity"] == "common"
    assert card_events[0]["card"]["colors"] == ["W"]

    # And no card_gen_reset — engine path must never wipe a resume's cards.
    assert not any(name == "card_gen_reset" for name, _ in spy.events)


def test_run_card_gen_emits_done_on_cancelled(monkeypatch) -> None:
    """A user-cancel exit must also close the strip — otherwise a cancel that
    leaves the run mid-flight leaves the strip stuck the same way."""
    monkeypatch.setattr(
        "mtgai.generation.card_generator.generate_set",
        _stub_generate_set_factory(
            {
                "total_slots": 272,
                "filled": 3,
                "failed": 0,
                "cost_usd": 0.0,
                "summary": "Cancelled after 3 cards",
                "cancelled": True,
            }
        ),
    )

    spy = _SpyEmitter()
    result = stages.run_card_gen(progress_cb=None, emitter=spy)

    assert result.success is False
    assert result.error_message == "Cancelled after 3 cards"
    phase_names = [name for name, _ in spy.calls]
    assert "done" in phase_names, f"missing terminal phase('done'); got {spy.calls}"
