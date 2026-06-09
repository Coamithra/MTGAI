"""Regression: the engine's inter-stage window runs under the AI lock.

Card 6a2869af — after a stage runner returns (and releases its own
``ai_lock.hold``), ``_run_loop`` used to run ``_snapshot_instance_output`` (a
copy of the live ``cards/`` folder) and ``_handle_rerun`` (the regen-span
insertion that consumes the just-stamped flags) with NO lock held, so a
guarded_ai endpoint (e.g. ``card_gen/refresh`` -> ``clear_card_gen_cards``)
could acquire the lock in that window and mutate the pool mid-copy /
mid-insert. The fix re-acquires the lock around both, releasing it before the
loop walks into the next stage (the lock is strictly non-reentrant — a held
lock would busy-back the next runner's own ``hold`` and silently skip it).

The synchronization is a from-thread lock probe inside the monkeypatched seam
(NOT a sleep), mirroring ``test_gate_flag_lock.py``: a competitor
``try_acquire`` failing == "the engine holds the lock at this exact moment".
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from mtgai.pipeline import engine as engine_mod
from mtgai.pipeline import history
from mtgai.pipeline.engine import PipelineEngine
from mtgai.pipeline.events import EventBus
from mtgai.pipeline.models import (
    STAGE_DEFINITIONS,
    PipelineConfig,
    PipelineState,
    PipelineStatus,
    StageReviewMode,
    StageState,
    StageStatus,
)
from mtgai.pipeline.stages import StageResult
from mtgai.runtime import active_project, ai_lock
from mtgai.settings.model_settings import ModelSettings

_DEFN = {d["stage_id"]: d for d in STAGE_DEFINITIONS}


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


def _state(stage_ids: list[str]) -> PipelineState:
    stages = [
        StageState(
            stage_id=sid,
            display_name=_DEFN[sid]["display_name"],
            review_eligible=_DEFN[sid]["review_eligible"],
            review_mode=StageReviewMode.AUTO,
            status=StageStatus.PENDING,
        )
        for sid in stage_ids
    ]
    return PipelineState(config=PipelineConfig(set_code="ABC", set_name="T"), stages=stages)


def _clean(_pc, _em):
    return StageResult(detail="ok")


def _competitor_acquire_result() -> object:
    """Run ``ai_lock.try_acquire`` on a fresh thread and return its result.

    A separate thread so the acquire contends with the engine thread's held
    lock the way a real concurrent endpoint would. Releases on success so it
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


def test_snapshot_runs_under_ai_lock(project, monkeypatch):
    """While the engine copies the live pool into history/, a competitor
    acquire must fail — the inter-stage hold closes the lock-free window."""
    probed: dict[str, object] = {}
    real_snapshot = history.snapshot_instance

    def probing_snapshot(instance_id, asset=None):
        probed[instance_id] = _competitor_acquire_result()
        return real_snapshot(instance_id, asset)

    monkeypatch.setattr(history, "snapshot_instance", probing_snapshot)
    monkeypatch.setitem(engine_mod.STAGE_RUNNERS, "lands", _clean)

    state = _state(["lands"])
    PipelineEngine(state, EventBus()).run()

    assert probed == {"lands": None}  # busy during the copy == lock was held
    assert state.overall_status == PipelineStatus.COMPLETED
    assert ai_lock.is_running() is False  # no leak once the run finished


def test_rerun_span_insertion_runs_under_ai_lock(project, monkeypatch):
    """The regen-span insertion (_handle_rerun) must also sit inside the
    inter-stage hold — it consumes the flags the gate just stamped."""
    probes: list[object] = []
    real_handle = PipelineEngine._handle_rerun

    def probing_handle(self, result, index):
        probes.append(_competitor_acquire_result())
        return real_handle(self, result, index)

    monkeypatch.setattr(PipelineEngine, "_handle_rerun", probing_handle)

    flagged = [False]

    def gate(_pc, _em):
        if not flagged[0]:
            flagged[0] = True
            return StageResult(detail="flagged", rerun_from="card_gen")
        return StageResult(detail="clean")

    for sid in ("card_gen", "finalize"):
        monkeypatch.setitem(engine_mod.STAGE_RUNNERS, sid, _clean)
    monkeypatch.setitem(engine_mod.STAGE_RUNNERS, "conformance", gate)

    state = _state(["card_gen", "conformance", "finalize"])
    PipelineEngine(state, EventBus()).run()

    # Every inter-stage _handle_rerun call saw a held lock — including the one
    # that inserted the regen span.
    assert probes and all(p is None for p in probes)
    ids = [s.instance_id for s in state.stages]
    assert "card_gen.2" in ids and "conformance.2" in ids
    assert state.overall_status == PipelineStatus.COMPLETED
    assert ai_lock.is_running() is False


def test_busy_lock_skips_snapshot_but_still_inserts_rerun_span(project, monkeypatch):
    """If an endpoint won the sub-ms release->reacquire race, the engine must
    NOT copy a pool in flux (snapshot skipped — degrades to a from-live
    re-run) but the span insertion still runs: it's engine-owned state, and
    skipping it would orphan the gate's stamped flags."""
    snapshot_calls: list[str] = []
    monkeypatch.setattr(
        history, "snapshot_instance", lambda iid, asset=None: snapshot_calls.append(iid) or True
    )

    flagged = [False]

    def gate(_pc, _em):
        if not flagged[0]:
            flagged[0] = True
            return StageResult(detail="flagged", rerun_from="card_gen")
        return StageResult(detail="clean")

    for sid in ("card_gen", "finalize"):
        monkeypatch.setitem(engine_mod.STAGE_RUNNERS, sid, _clean)
    monkeypatch.setitem(engine_mod.STAGE_RUNNERS, "conformance", gate)

    # A competitor (an endpoint) holds the lock for the whole run, so every
    # inter-stage hold comes back busy. The stubbed runners don't take the
    # lock themselves, so the walk still proceeds.
    assert ai_lock.try_acquire("endpoint holding the lock") is not None
    try:
        state = _state(["card_gen", "conformance", "finalize"])
        PipelineEngine(state, EventBus()).run()
    finally:
        ai_lock.release()

    assert snapshot_calls == []  # never copied a pool that might be in flux
    ids = [s.instance_id for s in state.stages]
    assert "card_gen.2" in ids and "conformance.2" in ids  # regen loop intact
    assert state.overall_status == PipelineStatus.COMPLETED


def test_engine_releases_lock_before_calling_next_runner(project, monkeypatch):
    """The lock is strictly non-reentrant: if the engine still held it when
    invoking the next stage's runner, that runner's own ``ai_lock.hold``
    would yield busy and its work would silently not run. Pin that every
    runner can take its own hold."""
    acquired: dict[str, object] = {}

    def locking_runner(stage_id: str):
        def run(_pc, _em):
            with ai_lock.hold(f"runner {stage_id}") as run_id:
                acquired[stage_id] = run_id
            return StageResult(detail="ok")

        return run

    # lands is snapshot-eligible, so the inter-stage hold fires between the
    # two stages — card_gen's acquire proves the engine released it.
    monkeypatch.setitem(engine_mod.STAGE_RUNNERS, "lands", locking_runner("lands"))
    monkeypatch.setitem(engine_mod.STAGE_RUNNERS, "card_gen", locking_runner("card_gen"))

    state = _state(["lands", "card_gen"])
    PipelineEngine(state, EventBus()).run()

    assert acquired["lands"] is not None
    assert acquired["card_gen"] is not None
    assert state.overall_status == PipelineStatus.COMPLETED
    assert ai_lock.is_running() is False
