"""Regression: the gate runners hold the AI lock THROUGH flag-stamping.

Card 6a285a0e — the merge + ``_flag_cards_for_regen`` (which rewrites
``cards/*.json`` and demotes cards to DRAFT) used to run *after* the runner's
``with ai_lock.hold(...)`` block exited, so a guarded_ai endpoint could acquire
the lock and mutate the pool mid-stamp. The fix moves the flagging inside the
hold. These tests pin that contract deterministically: while the flag step runs,
a competitor ``ai_lock.try_acquire`` must fail (the lock is held); once the
runner returns, the lock is free again.

The synchronization is a barrier inside the monkeypatched LLM step (NOT a sleep):
the step probes ``ai_lock.try_acquire`` from a *separate* thread and only returns
once that probe has resolved, so the assertion observes the lock state at exactly
the moment the runner is about to flag.
"""

from __future__ import annotations

import contextlib
import threading
from pathlib import Path

import pytest

from mtgai.analysis.models import ConformanceFinding
from mtgai.io.card_io import load_card, save_card
from mtgai.models.card import Card
from mtgai.models.enums import CardStatus
from mtgai.pipeline import stages as stages_mod
from mtgai.runtime import active_project, ai_lock
from mtgai.settings.model_settings import ModelSettings


@pytest.fixture
def project(tmp_path: Path):
    asset_dir = tmp_path / "asset"
    asset_dir.mkdir()
    ai_lock.reset_for_tests()
    active_project.write_active_project(
        active_project.ProjectState(
            set_code="ABC", settings=ModelSettings(asset_folder=str(asset_dir))
        )
    )
    yield asset_dir
    active_project.clear_active_project()
    ai_lock.reset_for_tests()


class _Emitter:
    def __init__(self, instance_id: str = "conformance"):
        self.instance_id = instance_id

    def phase(self, state, detail=""):
        pass

    def event(self, event_type, **data):
        pass


def _make_card(slot_id: str) -> Card:
    return Card(
        name=f"Card {slot_id}",
        slot_id=slot_id,
        collector_number=slot_id,
        type_line="Creature — Test",
        oracle_text=f"Unique ability {slot_id}.",
    )


def _competitor_acquire_result() -> object:
    """Run ``ai_lock.try_acquire`` on a fresh thread and return its result.

    A separate thread is used so the acquire contends with the runner thread's
    held lock the way a real concurrent endpoint would (and so a same-thread
    quirk can't mask a true holder). The competitor releases on success so it
    never leaks the lock.
    """
    box: dict[str, object] = {}

    def worker():
        run_id = ai_lock.try_acquire("competitor endpoint")
        box["run_id"] = run_id
        if run_id is not None:
            ai_lock.release()

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    return box["run_id"]


def test_run_conformance_holds_lock_through_flagging(project, monkeypatch):
    save_card(_make_card("W-C-01"), set_dir=project)

    probed: dict[str, object] = {}

    # The flag step runs after both LLM steps return. We probe the lock from a
    # competitor thread DURING ``_flag_cards_for_regen`` (wrapping the real one),
    # which only the lock-held window can reach.
    real_flag = stages_mod._flag_cards_for_regen

    def wrapped_flag(flags, flagged_by):
        probed["during_flag"] = _competitor_acquire_result()
        return real_flag(flags, flagged_by)

    monkeypatch.setattr(stages_mod, "_flag_cards_for_regen", wrapped_flag)
    monkeypatch.setattr(
        "mtgai.analysis.conformance.check_conformance",
        lambda cards, slots, **kw: (
            [ConformanceFinding(slot_id="W-C-01", card_name="Card W-C-01", reason="wrong color")],
            "analysis",
            0.0,
        ),
    )
    monkeypatch.setattr(
        "mtgai.analysis.interactions.analyze_interactions",
        lambda cards, mechanics, **kw: ([], "clean", 0.0),
    )
    monkeypatch.setattr(stages_mod, "make_poller", lambda *a, **k: contextlib.nullcontext())

    result = stages_mod.run_conformance(None, _Emitter())

    # The competitor's acquire FAILED while the runner was flagging — the lock
    # was held through the stamp.
    assert probed["during_flag"] is None
    # The flag actually landed (the stamp ran under the lock, not skipped).
    assert {f["slot_id"] for f in result.artifacts["flagged"]} == {"W-C-01"}
    card = load_card(next((project / "cards").glob("*.json")))
    assert card.flagged_by == "conformance"
    assert card.status == CardStatus.DRAFT
    # Once the runner returned, the lock is free again (no leak).
    assert ai_lock.is_running() is False
    assert _competitor_acquire_result() is not None


def test_run_ai_review_holds_lock_through_flagging(project, monkeypatch):
    save_card(_make_card("W-C-01"), set_dir=project)

    probed: dict[str, object] = {}
    real_flag = stages_mod._flag_cards_for_regen

    def wrapped_flag(flags, flagged_by):
        probed["during_flag"] = _competitor_acquire_result()
        return real_flag(flags, flagged_by)

    monkeypatch.setattr(stages_mod, "_flag_cards_for_regen", wrapped_flag)
    monkeypatch.setattr(
        "mtgai.review.ai_review.review_all_cards",
        lambda **kw: {
            "reviewed": 1,
            "revised": 0,
            "unfixable": [{"slot_id": "W-C-01", "reason": "still broken"}],
            "cost_usd": 0.0,
        },
    )
    monkeypatch.setattr(stages_mod, "make_poller", lambda *a, **k: contextlib.nullcontext())

    result = stages_mod.run_ai_review(None, _Emitter(instance_id="ai_review"))

    assert probed["during_flag"] is None
    assert {f["slot_id"] for f in result.artifacts["flagged"]} == {"W-C-01"}
    card = load_card(next((project / "cards").glob("*.json")))
    assert card.flagged_by == "ai_review"
    assert card.status == CardStatus.DRAFT
    assert ai_lock.is_running() is False
    assert _competitor_acquire_result() is not None
