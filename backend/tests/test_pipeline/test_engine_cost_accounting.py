"""Regression tests for ``PipelineEngine`` run-cost accounting.

The engine must count each stage's cost exactly ONCE in
``state.total_cost_usd``. Two distinct cost-reporting shapes exist:

* a stage that streams per-item cost through the progress callback AND
  returns the same total as ``StageResult.cost_usd`` (card_gen, ai_review,
  art_prompts, art_gen) — the old ``+= cost`` per item *plus*
  ``+= result.cost_usd`` at completion double-counted these (~2x);
* a stage that only sets ``StageResult.cost_usd`` with no per-item callbacks
  (mechanics, skeleton, conformance, …) — must still be added exactly once.

Plus the resume case: a resumed card_gen returns ``result.cost_usd`` ==
``progress.total_cost_usd`` which *includes* prior-run cost the callbacks
never re-emit, so the old completion add re-counted the prior run too.

These tests drive the real ``_run_loop`` over synthetic stages with fake
runners; they fail against the pre-fix ``+= result.cost_usd`` accounting.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mtgai.pipeline.engine import PipelineEngine
from mtgai.pipeline.events import EventBus
from mtgai.pipeline.models import (
    PipelineConfig,
    PipelineState,
    StageState,
    StageStatus,
)
from mtgai.pipeline.stages import STAGE_RUNNERS, StageResult
from mtgai.runtime import active_project
from mtgai.settings.model_settings import ModelSettings


@pytest.fixture
def pinned_project(tmp_path: Path):
    """Pin an active project so ``save_state`` writes under tmp_path."""
    asset_dir = tmp_path / "asset"
    asset_dir.mkdir()
    active_project.write_active_project(
        active_project.ProjectState(
            set_code="ABC", settings=ModelSettings(asset_folder=str(asset_dir))
        )
    )
    yield asset_dir
    active_project.clear_active_project()


@pytest.fixture
def restore_runners():
    """Snapshot/restore the global STAGE_RUNNERS registry around a test."""
    saved = dict(STAGE_RUNNERS)
    yield
    STAGE_RUNNERS.clear()
    STAGE_RUNNERS.update(saved)


def _single_stage_state(stage_id: str) -> PipelineState:
    """A pipeline of exactly one review-ineligible (never-pauses) stage."""
    return PipelineState(
        config=PipelineConfig(set_code="ABC", set_name="Test", set_size=20),
        stages=[
            StageState(
                stage_id=stage_id,
                display_name=stage_id,
                status=StageStatus.PENDING,
                review_eligible=False,
            )
        ],
    )


def _run_single_stage(state: PipelineState) -> float:
    engine = PipelineEngine(state, EventBus())
    engine.run()
    assert all(s.status in (StageStatus.COMPLETED, StageStatus.SKIPPED) for s in state.stages), [
        s.status for s in state.stages
    ]
    return state.total_cost_usd


def test_per_item_callback_stage_counted_once(pinned_project, restore_runners):
    """A stage that streams per-item cost AND returns the same total must not 2x.

    The fake runner mirrors card_gen: it emits ``0.10`` per item through the
    progress callback for 3 items, then returns ``cost_usd=0.30`` (the run
    total). True cost is $0.30 — the old engine recorded $0.60.
    """
    per_item = 0.10
    n_items = 3

    def fake_runner(progress_cb, emitter) -> StageResult:
        for i in range(n_items):
            if progress_cb is not None:
                progress_cb(f"item {i}", i + 1, n_items, "", per_item)
        return StageResult(
            total_items=n_items,
            completed_items=n_items,
            cost_usd=per_item * n_items,
        )

    STAGE_RUNNERS["card_gen"] = fake_runner
    total = _run_single_stage(_single_stage_state("card_gen"))
    assert total == pytest.approx(per_item * n_items)


def test_result_only_stage_added_once(pinned_project, restore_runners):
    """A stage with NO per-item callbacks still adds ``result.cost_usd`` once."""

    def fake_runner(progress_cb, emitter) -> StageResult:
        # No progress_cb cost emission — only the final result carries cost.
        return StageResult(total_items=1, completed_items=1, cost_usd=0.25)

    STAGE_RUNNERS["mechanics"] = fake_runner
    total = _run_single_stage(_single_stage_state("mechanics"))
    assert total == pytest.approx(0.25)


def test_resumed_stage_does_not_readd_prior_run_cost(pinned_project, restore_runners):
    """A resumed card_gen returns prior+new total without re-emitting prior cost.

    Mirrors the resume case: ``progress.total_cost_usd`` persists $0.40 of
    prior-run cost, this run generates 2 new batches at $0.10 each (only those
    flow through the callback), and the runner returns ``cost_usd=0.60`` (prior
    $0.40 + new $0.20). True total is $0.60 — the old engine recorded $0.80
    (0.40 persisted prior re-added + 0.20 callbacks counted twice... here, the
    callbacks add 0.20 and completion re-adds the full 0.60).
    """
    prior = 0.40
    new_per_batch = 0.10
    new_batches = 2

    def fake_runner(progress_cb, emitter) -> StageResult:
        for i in range(new_batches):
            if progress_cb is not None:
                progress_cb(f"batch {i}", i + 1, new_batches, "", new_per_batch)
        return StageResult(
            total_items=new_batches,
            completed_items=new_batches,
            cost_usd=prior + new_per_batch * new_batches,
        )

    STAGE_RUNNERS["card_gen"] = fake_runner
    total = _run_single_stage(_single_stage_state("card_gen"))
    assert total == pytest.approx(prior + new_per_batch * new_batches)


def test_multiple_stages_sum_once_each(pinned_project, restore_runners):
    """Two stages (one callback-reporting, one result-only) sum exactly once."""

    def cb_runner(progress_cb, emitter) -> StageResult:
        if progress_cb is not None:
            progress_cb("only", 1, 1, "", 0.30)
        return StageResult(total_items=1, completed_items=1, cost_usd=0.30)

    def result_runner(progress_cb, emitter) -> StageResult:
        return StageResult(total_items=1, completed_items=1, cost_usd=0.20)

    STAGE_RUNNERS["card_gen"] = cb_runner
    STAGE_RUNNERS["mechanics"] = result_runner

    state = PipelineState(
        config=PipelineConfig(set_code="ABC", set_name="Test", set_size=20),
        stages=[
            StageState(
                stage_id="card_gen",
                display_name="card_gen",
                status=StageStatus.PENDING,
                review_eligible=False,
            ),
            StageState(
                stage_id="mechanics",
                display_name="mechanics",
                status=StageStatus.PENDING,
                review_eligible=False,
            ),
        ],
    )
    total = _run_single_stage(state)
    assert total == pytest.approx(0.50)


def test_recompute_total_cost_is_idempotent(pinned_project):
    """``_recompute_total_cost`` sums per-stage costs and is repeatable."""
    state = _single_stage_state("card_gen")
    state.stages[0].progress.cost_usd = 0.42
    engine = PipelineEngine(state, EventBus())
    engine._recompute_total_cost()
    assert state.total_cost_usd == pytest.approx(0.42)
    # Idempotent — calling again does not accumulate.
    engine._recompute_total_cost()
    assert state.total_cost_usd == pytest.approx(0.42)
