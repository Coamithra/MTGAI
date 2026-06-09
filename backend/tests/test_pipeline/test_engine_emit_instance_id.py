"""Regression tests for instance_id on engine-published ``stage_update`` events.

A stage can appear more than once: ``StageState.instance_id`` is ``stage_id``
for the backbone instance and ``f"{stage_id}.{n}"`` (e.g. ``card_gen.2``) for
an inserted regen-loop copy. The wizard shell routes a ``stage_update`` to a
tab by its ``instance_id``, so every engine emit must thread the *instance's*
id — not the bare ``stage_id``, which would misroute to the backbone tab.

``resume()`` (Save & Continue on a paused, possibly-inserted tip) and
``skip_current()`` (skip a FAILED stage, which can be an inserted regen copy)
both previously called ``bus.stage_update(current.stage_id, ...)`` without
``instance_id`` — so the COMPLETED/SKIPPED event carried the backbone
``stage_id`` and updated the wrong tab. These tests fail without the fix.
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


def _inserted_instance_state(status: StageStatus) -> PipelineState:
    """A pipeline whose single, current stage is an inserted (non-backbone)
    instance ``card_gen.2`` (``instance_id != stage_id``)."""
    return PipelineState(
        config=PipelineConfig(set_code="ABC", set_name="Test", set_size=20),
        stages=[
            StageState(
                stage_id="card_gen",
                instance_id="card_gen.2",
                display_name="Card Generation 2",
                status=status,
                review_eligible=True,
            )
        ],
        current_instance_id="card_gen.2",
    )


def _stage_update_instance_ids(bus: EventBus, status: StageStatus) -> list[str]:
    """Every ``stage_update`` event the bus buffered with the given status."""
    return [
        ev["data"]["instance_id"]
        for ev in bus._buffer
        if ev["type"] == "stage_update" and ev["data"]["status"] == status
    ]


def test_resume_emits_instance_id_for_inserted_instance(pinned_project):
    """``resume()`` on ``card_gen.2`` must publish COMPLETED for ``card_gen.2``."""
    bus = EventBus()
    state = _inserted_instance_state(StageStatus.PAUSED_FOR_REVIEW)
    engine = PipelineEngine(state, bus)

    engine.resume()

    completed = _stage_update_instance_ids(bus, StageStatus.COMPLETED)
    assert "card_gen.2" in completed
    # Must NOT misroute to the backbone tab.
    assert "card_gen" not in completed


def test_skip_current_emits_instance_id_for_inserted_instance(pinned_project):
    """``skip_current()`` on ``card_gen.2`` must publish SKIPPED for ``card_gen.2``."""
    bus = EventBus()
    state = _inserted_instance_state(StageStatus.FAILED)
    engine = PipelineEngine(state, bus)

    engine.skip_current()

    skipped = _stage_update_instance_ids(bus, StageStatus.SKIPPED)
    assert "card_gen.2" in skipped
    assert "card_gen" not in skipped
