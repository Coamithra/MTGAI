"""Part 1 (instance-based, growable pipeline) acceptance tests.

The pipeline can carry a stage more than once: each definition has one
*backbone* instance (``instance_id == stage_id``) plus zero or more inserted
copies (``f"{stage_id}.{n}"``) the review→regen loop appends. These tests pin
the foundational, behavior-neutral guarantees:

* ``StageState.instance_id`` backfills to ``stage_id`` (old state loads as
  all-backbone).
* A state containing inserted duplicates round-trips through ``load_state()``
  unchanged (the reconciler preserves them instead of destroying them).
* ``PipelineState.current_stage()`` resolves by instance, and the legacy
  ``current_stage_id`` JSON key still loads.
* ``_sync_stages_with_definitions`` inserts missing backbone stages and drops
  removed ones while keeping inserts anchored to their preceding backbone.
* The wizard emits one distinct tab per instance.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mtgai.pipeline import engine as engine_mod
from mtgai.pipeline.models import (
    PipelineConfig,
    PipelineState,
    StageState,
    StageStatus,
    create_pipeline_state,
    make_instance_id,
)
from mtgai.pipeline.wizard import compute_visible_tabs
from mtgai.runtime import active_project
from mtgai.settings.model_settings import ModelSettings


@pytest.fixture
def project_with_state(tmp_path: Path):
    """Pin an active project at ``tmp_path`` and yield (asset_dir, write_state)."""
    asset_dir = tmp_path / "asset"
    asset_dir.mkdir()
    active_project.write_active_project(
        active_project.ProjectState(
            set_code="ABC", settings=ModelSettings(asset_folder=str(asset_dir))
        )
    )

    def _write(state: PipelineState) -> Path:
        path = asset_dir / "pipeline-state.json"
        path.write_text(
            json.dumps(state.model_dump(mode="json"), indent=2, default=str),
            encoding="utf-8",
        )
        return path

    yield asset_dir, _write
    active_project.clear_active_project()


def _state_with_inserted_dupes() -> PipelineState:
    """A backbone state with ``card_gen.2`` + ``conformance.2`` inserted after conformance."""
    state = create_pipeline_state(PipelineConfig(set_code="ABC", set_name="Test", set_size=20))
    idx = next(i for i, s in enumerate(state.stages) if s.stage_id == "conformance")
    cg2 = StageState(
        stage_id="card_gen",
        instance_id="card_gen.2",
        display_name="Card Generation 2",
        status=StageStatus.COMPLETED,
    )
    bal2 = StageState(
        stage_id="conformance",
        instance_id="conformance.2",
        display_name="Conformance & Interactions 2",
        status=StageStatus.PAUSED_FOR_REVIEW,
    )
    state.stages[idx + 1 : idx + 1] = [cg2, bal2]
    return state


# ----------------------------------------------------------------------
# instance_id backfill + helper
# ----------------------------------------------------------------------


def test_backbone_instance_id_defaults_to_stage_id():
    s = StageState(stage_id="conformance", display_name="Conformance")
    assert s.instance_id == "conformance"
    assert s.result == {}


def test_make_instance_id():
    assert make_instance_id("conformance", 1) == "conformance"
    assert make_instance_id("conformance", 2) == "conformance.2"
    assert make_instance_id("card_gen", 3) == "card_gen.3"


def test_build_stages_are_all_backbone():
    state = create_pipeline_state(PipelineConfig(set_code="ABC", set_name="Test"))
    assert all(s.instance_id == s.stage_id for s in state.stages)


# ----------------------------------------------------------------------
# current_stage() + legacy alias
# ----------------------------------------------------------------------


def test_current_stage_resolves_instance():
    state = _state_with_inserted_dupes()
    state.current_instance_id = "conformance.2"
    current = state.current_stage()
    assert current is not None
    assert current.instance_id == "conformance.2"
    assert current.stage_id == "conformance"
    assert current.display_name == "Conformance & Interactions 2"


def test_legacy_current_stage_id_alias_loads():
    """Old pipeline-state.json used ``current_stage_id``; it must still load."""
    state = create_pipeline_state(PipelineConfig(set_code="ABC", set_name="Test"))
    raw = state.model_dump(mode="json")
    raw.pop("current_instance_id", None)
    raw["current_stage_id"] = "skeleton"  # legacy key
    loaded = PipelineState.model_validate(raw)
    assert loaded.current_instance_id == "skeleton"
    # Round-trips out under the new name.
    assert loaded.model_dump(mode="json")["current_instance_id"] == "skeleton"


# ----------------------------------------------------------------------
# _sync_stages_with_definitions — preserve / insert / drop
# ----------------------------------------------------------------------


def test_sync_clean_backbone_is_noop():
    state = create_pipeline_state(PipelineConfig(set_code="ABC", set_name="Test"))
    assert engine_mod._sync_stages_with_definitions(state) is False


def test_sync_preserves_inserted_instances():
    state = _state_with_inserted_dupes()
    before = [s.instance_id for s in state.stages]
    changed = engine_mod._sync_stages_with_definitions(state)
    after = [s.instance_id for s in state.stages]
    assert after == before
    assert changed is False
    # The inserts trail the backbone they were anchored to.
    bal = after.index("conformance")
    assert after[bal : bal + 3] == ["conformance", "card_gen.2", "conformance.2"]


def test_sync_inserts_missing_backbone():
    state = create_pipeline_state(PipelineConfig(set_code="ABC", set_name="Test"))
    # Drop the skeleton backbone; sync must re-insert it at its canonical slot.
    state.stages = [s for s in state.stages if s.stage_id != "skeleton"]
    changed = engine_mod._sync_stages_with_definitions(state)
    assert changed is True
    ids = [s.stage_id for s in state.stages]
    assert ids.index("skeleton") == ids.index("archetypes") + 1


def test_sync_drops_unknown_backbone():
    state = create_pipeline_state(PipelineConfig(set_code="ABC", set_name="Test"))
    state.stages.append(StageState(stage_id="bogus_stage", display_name="Bogus"))
    changed = engine_mod._sync_stages_with_definitions(state)
    assert changed is True
    assert "bogus_stage" not in [s.stage_id for s in state.stages]


# ----------------------------------------------------------------------
# load_state round-trip with disk
# ----------------------------------------------------------------------


def test_inserted_instances_roundtrip_through_load_state(project_with_state):
    _asset_dir, write_state = project_with_state
    original = _state_with_inserted_dupes()
    write_state(original)

    loaded = engine_mod.load_state()
    assert loaded is not None
    assert [s.instance_id for s in loaded.stages] == [s.instance_id for s in original.stages]
    by_inst = {s.instance_id: s for s in loaded.stages}
    assert by_inst["card_gen.2"].display_name == "Card Generation 2"
    assert by_inst["conformance.2"].display_name == "Conformance & Interactions 2"
    assert by_inst["conformance.2"].stage_id == "conformance"


# ----------------------------------------------------------------------
# wizard tabs — one per instance
# ----------------------------------------------------------------------


def test_compute_visible_tabs_emits_distinct_tab_per_instance():
    state = _state_with_inserted_dupes()
    # Make every stage up through conformance.2 visible (non-PENDING).
    last = next(i for i, s in enumerate(state.stages) if s.instance_id == "conformance.2")
    for s in state.stages[: last + 1]:
        if s.status == StageStatus.PENDING:
            s.status = StageStatus.COMPLETED

    tabs = compute_visible_tabs(state=state, theme={"name": "x"})
    ids = [t.id for t in tabs]
    assert "conformance" in ids and "conformance.2" in ids
    titles = {t.id: t.title for t in tabs}
    assert titles["conformance"] == "Conformance & Interactions"  # merged gate display
    assert titles["conformance.2"] == "Conformance & Interactions 2"
    # Distinct tabs, no collision.
    assert len(ids) == len(set(ids))
