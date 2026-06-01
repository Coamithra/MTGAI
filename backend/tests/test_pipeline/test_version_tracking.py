"""Per-instance card-pool version tracking: snapshots + rerun_instance.

Covers the ``history`` sidecar (snapshot/restore round-trip, _regen_archive
exclusion, L-* preservation) and the engine's ``rerun_instance`` (restore entry
pool -> truncate downstream -> reset target -> re-append the canonical forward
path), which is the forward mirror of the review->regen insert span.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mtgai.pipeline import engine as engine_mod
from mtgai.pipeline import history
from mtgai.pipeline.models import (
    PipelineConfig,
    PipelineState,
    PipelineStatus,
    StageState,
    StageStatus,
)
from mtgai.runtime import active_project
from mtgai.settings.model_settings import ModelSettings


@pytest.fixture
def project(tmp_path: Path):
    """Pin an active project at ``tmp_path`` and yield its asset dir."""
    asset_dir = tmp_path / "asset"
    asset_dir.mkdir()
    active_project.write_active_project(
        active_project.ProjectState(
            set_code="ABC", settings=ModelSettings(asset_folder=str(asset_dir))
        )
    )
    yield asset_dir
    active_project.clear_active_project()


def _write_card(asset: Path, name: str, body: dict | None = None) -> Path:
    cards = asset / "cards"
    cards.mkdir(parents=True, exist_ok=True)
    p = cards / name
    p.write_text(json.dumps(body or {"collector_number": name.split("_")[0]}), encoding="utf-8")
    return p


# ----------------------------------------------------------------------
# history snapshot / restore
# ----------------------------------------------------------------------


def test_snapshot_and_restore_round_trip(project: Path) -> None:
    _write_card(project, "001_a.json", {"collector_number": "001", "name": "A"})
    _write_card(project, "002_b.json", {"collector_number": "002", "name": "B"})
    (project / "generation_progress.json").write_text('{"filled_slots": {"001": "x"}}', "utf-8")

    assert history.snapshot_instance("card_gen") is True
    assert history.snapshot_exists("card_gen")

    # Mutate the live pool, then restore.
    (project / "cards" / "001_a.json").write_text('{"mutated": true}', "utf-8")
    (project / "cards" / "003_c.json").write_text("{}", "utf-8")
    (project / "generation_progress.json").write_text("{}", "utf-8")

    assert history.restore_snapshot("card_gen") is True
    assert json.loads((project / "cards" / "001_a.json").read_text())["name"] == "A"
    assert not (project / "cards" / "003_c.json").exists(), "card absent at snapshot must be gone"
    assert json.loads((project / "generation_progress.json").read_text())["filled_slots"]


def test_snapshot_excludes_regen_archive(project: Path) -> None:
    _write_card(project, "001_a.json")
    archive = project / "cards" / "_regen_archive"
    archive.mkdir()
    (archive / "old.json").write_text("{}", "utf-8")

    history.snapshot_instance("card_gen")

    snap_cards = history.snapshot_dir("card_gen") / "cards"
    assert (snap_cards / "001_a.json").exists()
    assert not (snap_cards / "_regen_archive").exists(), "transient archive must not be snapshotted"


def test_snapshot_preserves_lands(project: Path) -> None:
    _write_card(project, "L-01_plains.json", {"collector_number": "L-01"})
    _write_card(project, "001_a.json", {"collector_number": "001"})
    history.snapshot_instance("lands")
    (project / "cards" / "L-01_plains.json").unlink()

    history.restore_snapshot("lands")
    assert (project / "cards" / "L-01_plains.json").exists(), "L-* must round-trip in the snapshot"


def test_restore_clears_stale_regen_archive(project: Path) -> None:
    _write_card(project, "001_a.json")
    history.snapshot_instance("card_gen")
    # A later run leaves a regen archive in the live pool.
    archive = project / "cards" / "_regen_archive"
    archive.mkdir()
    (archive / "old.json").write_text("{}", "utf-8")

    history.restore_snapshot("card_gen")
    assert not archive.exists(), "restore should clear the stale live _regen_archive"


def test_restore_missing_snapshot_returns_false(project: Path) -> None:
    assert history.restore_snapshot("nope") is False


def test_delete_snapshot_is_idempotent(project: Path) -> None:
    _write_card(project, "001_a.json")
    history.snapshot_instance("card_gen")
    history.delete_snapshot("card_gen")
    assert not history.snapshot_exists("card_gen")
    history.delete_snapshot("card_gen")  # no raise


# ----------------------------------------------------------------------
# engine.rerun_instance
# ----------------------------------------------------------------------


def _loop_state() -> PipelineState:
    """A completed run that bounced once: [card_gen, conformance, card_gen.2,
    conformance.2, balance, ai_review, finalize] all COMPLETED, with entry
    pointers stamped as the engine would."""
    config = PipelineConfig(set_code="ABC", set_name="Test", set_size=20)
    order = [
        ("lands", "lands", "Land Generation", None),
        ("card_gen", "card_gen", "Card Generation", "lands"),
        ("conformance", "conformance", "Conformance", "card_gen"),
        ("card_gen", "card_gen.2", "Card Generation 2", "conformance"),
        ("conformance", "conformance.2", "Conformance 2", "card_gen.2"),
        ("balance", "balance", "Interaction Check", "conformance.2"),
        ("ai_review", "ai_review", "AI Design Review", "balance"),
        ("finalize", "finalize", "Finalization", "ai_review"),
    ]
    stages = [
        StageState(
            stage_id=sid,
            instance_id=iid,
            display_name=dn,
            status=StageStatus.COMPLETED,
            entry_snapshot_id=entry,
        )
        for sid, iid, dn, entry in order
    ]
    return PipelineState(config=config, stages=stages, current_instance_id="finalize")


def test_rerun_instance_truncates_and_reappends(project: Path) -> None:
    state = _loop_state()
    engine_mod.rerun_instance(state, "card_gen.2")

    ids = [s.instance_id for s in state.stages]
    # Past instances untouched; card_gen.2 reset; downstream re-appended fresh.
    assert ids[:3] == ["lands", "card_gen", "conformance"]
    # card_gen.2 is still present, reset to PENDING.
    cg2 = next(s for s in state.stages if s.instance_id == "card_gen.2")
    assert cg2.status == StageStatus.PENDING
    assert cg2.result == {}
    # The forward path re-establishes conformance.2 (sibling survives -> ordinal 2)
    # and backbone balance/ai_review/finalize (no survivor -> ordinal 1).
    after_cg2 = ids[ids.index("card_gen.2") + 1 :]
    assert after_cg2[:4] == ["conformance.2", "balance", "ai_review", "finalize"]
    # Canonical tail (art/render/human) is re-appended too.
    assert "rendering" in after_cg2 and "human_final_review" in after_cg2
    # All re-appended stages are PENDING.
    assert all(
        s.status == StageStatus.PENDING
        for s in state.stages[state.stages.index(cg2) + 1 :]
    )
    assert state.current_instance_id == "card_gen.2"
    assert state.overall_status == PipelineStatus.NOT_STARTED


def test_rerun_instance_restores_entry_snapshot(project: Path) -> None:
    # Snapshot conformance.1's (flagged) pool as card_gen.2's entry.
    _write_card(project, "001_a.json", {"collector_number": "001", "flagged_by": "conformance"})
    history.snapshot_instance("conformance")
    # Live pool then diverges (as if a later run overwrote it).
    (project / "cards" / "001_a.json").write_text('{"collector_number": "001"}', "utf-8")
    _write_card(project, "999_extra.json")

    state = _loop_state()
    entry = engine_mod.rerun_instance(state, "card_gen.2")

    assert entry == "conformance"
    restored = json.loads((project / "cards" / "001_a.json").read_text())
    assert restored.get("flagged_by") == "conformance", "entry pool (with flags) restored"
    assert not (project / "cards" / "999_extra.json").exists()


def test_rerun_backbone_card_gen_restores_lands_entry(project: Path) -> None:
    state = _loop_state()
    entry = engine_mod.rerun_instance(state, "card_gen")
    assert entry == "lands"
    # Re-running the backbone card_gen drops every later instance.
    ids = [s.instance_id for s in state.stages]
    assert ids[:2] == ["lands", "card_gen"]
    assert "conformance" in ids and "conformance.2" not in ids
    assert next(s for s in state.stages if s.instance_id == "card_gen").status == (
        StageStatus.PENDING
    )


def test_rerun_unknown_instance_raises(project: Path) -> None:
    state = _loop_state()
    with pytest.raises(ValueError, match="Unknown instance id"):
        engine_mod.rerun_instance(state, "nonesuch.7")


def test_rerun_missing_entry_snapshot_degrades(project: Path) -> None:
    # No history on disk at all (migration / first-ever run): rerun still resets
    # state, just without restoring a pool.
    state = _loop_state()
    entry = engine_mod.rerun_instance(state, "balance")
    assert entry == "conformance.2"  # predecessor pointer, even with no snapshot file
    bal = next(s for s in state.stages if s.instance_id == "balance")
    assert bal.status == StageStatus.PENDING
    # forward path after balance starts with ai_review (backbone), then finalize.
    ids = [s.instance_id for s in state.stages]
    after = ids[ids.index("balance") + 1 :]
    assert after[:2] == ["ai_review", "finalize"]
