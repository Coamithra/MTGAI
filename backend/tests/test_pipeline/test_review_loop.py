"""Part 2 — the review→regen loop + stage split.

Covers the engine's forward-only re-entrancy (a gate that flags cards bounces to
``card_gen`` by inserting a fresh instance span and walking into it; the loop is
uncapped — a gate keeps bouncing until its cards conform), the span scope (cost
rule: a conformance
bounce re-inserts only ``[card_gen, conformance]``), the card-flag substrate
(``regen_reason`` collected by card_gen, archived, threaded into the prompt,
flagged by a gate runner), and that a legacy ``skeleton_rev`` stage reconciles
cleanly out of a loaded state.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mtgai.pipeline import engine as engine_mod
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
from mtgai.runtime import active_project
from mtgai.settings.model_settings import ModelSettings

_DEFN = {d["stage_id"]: d for d in STAGE_DEFINITIONS}


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


def _flagging(times: int, counter: list[int]):
    """A gate runner that flags (rerun_from=card_gen) the first ``times`` calls."""

    def run(_pc, _em):
        if counter[0] < times:
            counter[0] += 1
            return StageResult(detail="flagged 1", rerun_from="card_gen")
        return StageResult(detail="clean")

    return run


def _patch_clean(monkeypatch, *stage_ids):
    for sid in stage_ids:
        monkeypatch.setitem(engine_mod.STAGE_RUNNERS, sid, _clean)


_SPAN = ["card_gen", "conformance", "ai_review", "finalize"]


# ----------------------------------------------------------------------
# Engine insertion + uncapped loop
# ----------------------------------------------------------------------


def test_gate_flags_then_passes_inserts_spans_and_advances(project, monkeypatch):
    """A late gate (ai_review) flags twice then passes -> 3 instances each of
    card_gen/conformance/ai_review, and the run advances to completion."""
    state = _state(_SPAN)
    counter = [0]
    _patch_clean(monkeypatch, "card_gen", "conformance", "finalize")
    monkeypatch.setitem(engine_mod.STAGE_RUNNERS, "ai_review", _flagging(2, counter))

    PipelineEngine(state, EventBus()).run()

    ids = [s.instance_id for s in state.stages]
    assert sum(1 for s in state.stages if s.stage_id == "ai_review") == 3, ids
    assert sum(1 for s in state.stages if s.stage_id == "card_gen") == 3, ids
    assert sum(1 for s in state.stages if s.stage_id == "conformance") == 3, ids
    # Inserted instances carry the ".N" suffix + ordinal display name.
    assert "ai_review.2" in ids and "ai_review.3" in ids
    ar3 = next(s for s in state.stages if s.instance_id == "ai_review.3")
    assert ar3.display_name == "AI Design Review 3"
    assert state.overall_status == PipelineStatus.COMPLETED
    assert all(s.status == StageStatus.COMPLETED for s in state.stages)


def test_gate_loop_is_uncapped(project, monkeypatch):
    """There is no round cap: a gate that flags well past the old 3-round limit
    keeps bouncing to card_gen, then completes once its cards finally conform —
    it never pauses the pipeline for human review."""
    state = _state(_SPAN)
    counter = [0]
    _patch_clean(monkeypatch, "card_gen", "conformance", "finalize")
    # Flag 6 times (double the old MAX_REVIEW_ROUNDS) then pass.
    monkeypatch.setitem(engine_mod.STAGE_RUNNERS, "ai_review", _flagging(6, counter))

    PipelineEngine(state, EventBus()).run()

    ar = [s for s in state.stages if s.stage_id == "ai_review"]
    # 6 flagging rounds + 1 clean = 7 ai_review instances, all completed.
    assert len(ar) == 7, [s.instance_id for s in state.stages]
    assert all(s.status == StageStatus.COMPLETED for s in ar)
    assert state.overall_status == PipelineStatus.COMPLETED
    assert all(s.status == StageStatus.COMPLETED for s in state.stages)


def test_conformance_bounce_reinserts_only_card_gen_and_conformance(project, monkeypatch):
    """Cost rule: a bounce at conformance re-inserts only [card_gen, conformance]."""
    state = _state(_SPAN)
    counter = [0]
    _patch_clean(monkeypatch, "card_gen", "ai_review", "finalize")
    monkeypatch.setitem(engine_mod.STAGE_RUNNERS, "conformance", _flagging(1, counter))

    PipelineEngine(state, EventBus()).run()

    # The inserted span is exactly [card_gen.2, conformance.2] -- no ai_review.2.
    assert sum(1 for s in state.stages if s.stage_id == "card_gen") == 2
    assert sum(1 for s in state.stages if s.stage_id == "conformance") == 2
    assert sum(1 for s in state.stages if s.stage_id == "ai_review") == 1
    assert "ai_review.2" not in [s.instance_id for s in state.stages]
    assert state.overall_status == PipelineStatus.COMPLETED


def test_build_rerun_span_ordinals_and_scope(project):
    state = _state(_SPAN)
    eng = PipelineEngine(state, EventBus())
    span = eng._build_rerun_span("card_gen", "ai_review")
    assert [s.instance_id for s in span] == ["card_gen.2", "conformance.2", "ai_review.2"]
    assert [s.display_name for s in span] == [
        "Card Generation 2",
        "Conformance & Interactions 2",
        "AI Design Review 2",
    ]
    assert all(s.review_mode == StageReviewMode.AUTO for s in span)
    assert all(s.status == StageStatus.PENDING for s in span)


# ----------------------------------------------------------------------
# Legacy skeleton_rev reconciles cleanly out of a loaded state
# ----------------------------------------------------------------------


def test_legacy_skeleton_rev_dropped_on_sync():
    state = _state(["card_gen", "conformance", "ai_review"])
    # Splice in a legacy skeleton_rev backbone (removed from STAGE_DEFINITIONS).
    state.stages.insert(
        2,
        StageState(stage_id="skeleton_rev", display_name="Skeleton Revision"),
    )
    changed = engine_mod._sync_stages_with_definitions(state)
    assert changed is True
    assert "skeleton_rev" not in [s.stage_id for s in state.stages]


# ----------------------------------------------------------------------
# Card-flag substrate
# ----------------------------------------------------------------------


def _make_card(slot_id: str, **overrides):
    from mtgai.models.card import Card

    data = {
        "name": f"Card {slot_id}",
        "slot_id": slot_id,
        "collector_number": slot_id,
        "type_line": "Creature — Test",
    }
    data.update(overrides)
    return Card(**data)


def test_collect_flagged_slots(project):
    from mtgai.generation.card_generator import _collect_flagged_slots
    from mtgai.io.card_io import save_card

    save_card(_make_card("W-C-01"), set_dir=project)
    save_card(_make_card("W-C-02", regen_reason="slot wants white, card is blue"), set_dir=project)

    flagged = _collect_flagged_slots(project / "cards")
    assert flagged == {"W-C-02": "slot wants white, card is blue"}


def test_archive_card_moves_file(project):
    from mtgai.generation.card_generator import archive_card
    from mtgai.io.card_io import save_card

    path = save_card(_make_card("W-C-01"), set_dir=project)
    assert path.exists()
    archive_dir = project / "cards" / "_regen_archive"
    name = archive_card("W-C-01", project / "cards", archive_dir)
    assert name is not None
    assert not path.exists()
    assert (archive_dir / path.name).exists()


def test_regen_reason_threads_into_prompt():
    from mtgai.generation.prompts import format_slot_specs

    slot = {
        "slot_id": "W-C-01",
        "tweaked_text": "White common creature",
        "regen_reason": "too strong",
    }
    spec = format_slot_specs([slot])
    assert "REGENERATION" in spec
    assert "too strong" in spec


def test_flag_cards_for_regen_round_trip(project):
    from mtgai.io.card_io import load_card, save_card
    from mtgai.models.enums import CardStatus
    from mtgai.pipeline.stages import _flag_cards_for_regen

    save_card(_make_card("W-C-01"), set_dir=project)
    flagged = _flag_cards_for_regen([("W-C-01", "needs a fix")], "conformance")
    assert flagged == [{"slot_id": "W-C-01", "card_name": "Card W-C-01", "reason": "needs a fix"}]

    # The flag is persisted on the card, demoted to DRAFT.
    cards = list((project / "cards").glob("*.json"))
    card = load_card(cards[0])
    assert card.regen_reason == "needs a fix"
    assert card.flagged_by == "conformance"
    assert card.status == CardStatus.DRAFT
