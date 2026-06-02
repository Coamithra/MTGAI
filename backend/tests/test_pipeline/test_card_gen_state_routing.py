"""Read-routing for the Card Generation tab's old/new view.

The /state endpoint diffs the *viewed* instance's pool against its *entry*
snapshot. Two helpers pick the two dirs: ``_resolve_view_cards_dir`` (live pool
for the loop tip, the instance's own ``history/`` snapshot otherwise) and
``_entry_snapshot_cards_dir`` (the predecessor snapshot pinned as
``entry_snapshot_id``). The pure diff is covered in test_card_gen_regen_diff;
this pins the wiring that decides which two dirs get diffed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mtgai.pipeline import history
from mtgai.pipeline.engine import save_state
from mtgai.pipeline.models import PipelineConfig, PipelineState, StageState, StageStatus
from mtgai.pipeline.server import _entry_snapshot_cards_dir, _resolve_view_cards_dir
from mtgai.runtime import active_project
from mtgai.settings.model_settings import ModelSettings


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


def _write_card(asset: Path, name: str, body: dict) -> None:
    cards = asset / "cards"
    cards.mkdir(parents=True, exist_ok=True)
    (cards / name).write_text(json.dumps(body), encoding="utf-8")


def _save_loop_state(stages: list[tuple[str, str, StageStatus, str | None]]) -> None:
    """Persist a pipeline-state.json from (stage_id, instance_id, status, entry)."""
    config = PipelineConfig(set_code="ABC", set_name="Test", set_size=20)
    st = [
        StageState(
            stage_id=sid, instance_id=iid, display_name=iid, status=status, entry_snapshot_id=entry
        )
        for sid, iid, status, entry in stages
    ]
    save_state(PipelineState(config=config, stages=st, current_instance_id=st[-1].instance_id))


# ---------------------------------------------------------------------------
# _entry_snapshot_cards_dir
# ---------------------------------------------------------------------------


def test_entry_snapshot_dir_none_without_state(project: Path) -> None:
    """No pipeline-state.json on disk (migration / first run) -> no entry dir, so
    the tab degrades to no old/new highlight."""
    assert _entry_snapshot_cards_dir("card_gen", project) is None


def test_entry_snapshot_dir_resolves_predecessor_snapshot(project: Path) -> None:
    _write_card(project, "001_a.json", {"collector_number": "001", "flagged_by": "conformance"})
    history.snapshot_instance("conformance")  # snapshot the (flagged) pool
    _save_loop_state(
        [
            ("lands", "lands", StageStatus.COMPLETED, None),
            ("card_gen", "card_gen", StageStatus.COMPLETED, "lands"),
            ("conformance", "conformance", StageStatus.COMPLETED, "card_gen"),
            ("card_gen", "card_gen.2", StageStatus.RUNNING, "conformance"),
        ]
    )
    got = _entry_snapshot_cards_dir("card_gen.2", project)
    assert got == history.snapshot_dir("conformance", project) / "cards"
    assert got is not None and got.is_dir()


def test_entry_snapshot_dir_none_when_no_entry_or_missing_snapshot(project: Path) -> None:
    _save_loop_state(
        [
            ("lands", "lands", StageStatus.COMPLETED, None),
            # backbone card_gen's entry is lands, which has no snapshot on disk here
            ("card_gen", "card_gen", StageStatus.COMPLETED, "lands"),
        ]
    )
    # No entry_snapshot_id (the first stage) -> None.
    assert _entry_snapshot_cards_dir("lands", project) is None
    # Entry pinned but its snapshot folder doesn't exist -> None (safe degrade).
    assert _entry_snapshot_cards_dir("card_gen", project) is None
    # Unknown instance id -> None.
    assert _entry_snapshot_cards_dir("ghost.9", project) is None


# ---------------------------------------------------------------------------
# _resolve_view_cards_dir
# ---------------------------------------------------------------------------


def test_view_dir_tip_reads_live_pool(project: Path) -> None:
    _save_loop_state(
        [
            ("card_gen", "card_gen", StageStatus.COMPLETED, "lands"),
            ("conformance", "conformance", StageStatus.COMPLETED, "card_gen"),
            ("card_gen", "card_gen.2", StageStatus.COMPLETED, "conformance"),
        ]
    )
    # card_gen.2 is the last ran instance -> the tip -> live cards/.
    assert _resolve_view_cards_dir("card_gen.2", project) == project / "cards"


def test_view_dir_non_tip_reads_own_snapshot(project: Path) -> None:
    _write_card(project, "001_a.json", {"collector_number": "001"})
    history.snapshot_instance("card_gen")  # the backbone's own snapshot
    _save_loop_state(
        [
            ("card_gen", "card_gen", StageStatus.COMPLETED, "lands"),
            ("conformance", "conformance", StageStatus.COMPLETED, "card_gen"),
            ("card_gen", "card_gen.2", StageStatus.COMPLETED, "conformance"),
        ]
    )
    # Backbone card_gen is non-tip and has a snapshot -> reads history/, not live.
    assert _resolve_view_cards_dir("card_gen", project) == (
        history.snapshot_dir("card_gen", project) / "cards"
    )


def test_view_dir_non_tip_without_snapshot_falls_back_to_live(project: Path) -> None:
    _save_loop_state(
        [
            ("card_gen", "card_gen", StageStatus.COMPLETED, "lands"),
            ("conformance", "conformance", StageStatus.COMPLETED, "card_gen"),
            ("card_gen", "card_gen.2", StageStatus.COMPLETED, "conformance"),
        ]
    )
    # conformance is non-tip but has no snapshot on disk -> live fallback.
    assert _resolve_view_cards_dir("conformance", project) == project / "cards"
