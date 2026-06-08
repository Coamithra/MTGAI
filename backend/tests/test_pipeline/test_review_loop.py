"""Part 2 — the review→regen loop + stage split.

Covers the engine's forward-only re-entrancy (a gate that flags cards bounces to
``card_gen`` by inserting a fresh instance span and walking into it; the loop is
capped *per gate* — ``MAX_REGEN_ROUNDS`` for conformance, ``MAX_AI_REVIEW_REGEN``
for the council — after which that gate just completes and its cards are accepted
as-is, and conformance churn can't starve the council), the span scope (cost rule: a
conformance bounce re-inserts only ``[card_gen, conformance]``), the card-flag
substrate
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
# Engine insertion + capped regen loop
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


def test_gate_loop_flags_then_passes_under_cap(project, monkeypatch):
    """A gate that flags a few rounds (well under the cap) then passes keeps
    bouncing to card_gen, then completes once its cards finally conform — it
    never pauses the pipeline for human review."""
    state = _state(_SPAN)
    counter = [0]
    _patch_clean(monkeypatch, "card_gen", "ai_review", "finalize")
    # Flag 4 times (under MAX_REGEN_ROUNDS=5) then pass.
    monkeypatch.setitem(engine_mod.STAGE_RUNNERS, "conformance", _flagging(4, counter))

    PipelineEngine(state, EventBus()).run()

    conf = [s for s in state.stages if s.stage_id == "conformance"]
    # 4 flagging rounds + 1 clean = 5 conformance instances, all completed.
    assert len(conf) == 5, [s.instance_id for s in state.stages]
    assert all(s.status == StageStatus.COMPLETED for s in conf)
    assert state.overall_status == PipelineStatus.COMPLETED
    assert all(s.status == StageStatus.COMPLETED for s in state.stages)


def test_conformance_loop_caps_at_max_regen_rounds(project, monkeypatch):
    """The conformance loop is capped: a conformance gate that flags every single
    round stops bouncing after MAX_REGEN_ROUNDS card_gen rounds, then completes
    and accepts the still-flagged cards as-is so the pipeline can finish (never an
    infinite loop, never a human-review pause)."""
    state = _state(_SPAN)
    counter = [0]
    _patch_clean(monkeypatch, "card_gen", "ai_review", "finalize")
    # Flag far more times than the cap — the engine must stop us well before this.
    monkeypatch.setitem(engine_mod.STAGE_RUNNERS, "conformance", _flagging(50, counter))

    PipelineEngine(state, EventBus()).run()

    # backbone card_gen + MAX_REGEN_ROUNDS conformance regen rounds, then accept.
    n = engine_mod.MAX_REGEN_ROUNDS + 1
    ids = [s.instance_id for s in state.stages]
    assert sum(1 for s in state.stages if s.stage_id == "card_gen") == n, ids
    assert sum(1 for s in state.stages if s.stage_id == "conformance") == n, ids
    # A conformance bounce never re-inserts ai_review, so it stays at 1.
    assert sum(1 for s in state.stages if s.stage_id == "ai_review") == 1, ids
    # conformance ran n times and flagged on every one (incl. the last, accepted) —
    # the cap, not the runner finally passing, is what stopped the loop.
    assert counter[0] == n
    assert state.overall_status == PipelineStatus.COMPLETED
    assert all(s.status == StageStatus.COMPLETED for s in state.stages)


def test_ai_review_loop_caps_at_its_own_smaller_budget(project, monkeypatch):
    """The council (ai_review) loop is capped independently at MAX_AI_REVIEW_REGEN
    (smaller than conformance's budget): flagging every round stops bouncing after
    that many rounds and accepts the still-flagged cards as-is."""
    state = _state(_SPAN)
    counter = [0]
    _patch_clean(monkeypatch, "card_gen", "conformance", "finalize")
    monkeypatch.setitem(engine_mod.STAGE_RUNNERS, "ai_review", _flagging(50, counter))

    PipelineEngine(state, EventBus()).run()

    # backbone ai_review + MAX_AI_REVIEW_REGEN regen rounds, then accept-as-is.
    n = engine_mod.MAX_AI_REVIEW_REGEN + 1
    ids = [s.instance_id for s in state.stages]
    assert sum(1 for s in state.stages if s.stage_id == "ai_review") == n, ids
    assert sum(1 for s in state.stages if s.stage_id == "card_gen") == n, ids
    assert counter[0] == n
    assert state.overall_status == PipelineStatus.COMPLETED
    assert all(s.status == StageStatus.COMPLETED for s in state.stages)


def test_conformance_churn_does_not_starve_the_council(project, monkeypatch):
    """The per-gate-budget fix: even when conformance flags every round and burns
    its entire MAX_REGEN_ROUNDS budget, the later council (ai_review) still gets
    its OWN full MAX_AI_REVIEW_REGEN regen rounds — conformance churn no longer
    silently starves a genuine council flag of any regen at all."""
    state = _state(_SPAN)
    conf_counter = [0]
    ar_counter = [0]
    _patch_clean(monkeypatch, "card_gen", "finalize")
    # Both gates flag on every call (far past either cap).
    monkeypatch.setitem(engine_mod.STAGE_RUNNERS, "conformance", _flagging(50, conf_counter))
    monkeypatch.setitem(engine_mod.STAGE_RUNNERS, "ai_review", _flagging(50, ar_counter))

    PipelineEngine(state, EventBus()).run()

    ids = [s.instance_id for s in state.stages]
    # The council ran its full independent budget despite conformance exhausting
    # its own first.
    assert sum(1 for s in state.stages if s.stage_id == "ai_review") == (
        engine_mod.MAX_AI_REVIEW_REGEN + 1
    ), ids
    # Total card_gen rounds = backbone + each gate's full budget (the loop is
    # bounded by the sum, never the old shared single counter).
    assert sum(1 for s in state.stages if s.stage_id == "card_gen") == (
        1 + engine_mod.MAX_REGEN_ROUNDS + engine_mod.MAX_AI_REVIEW_REGEN
    ), ids
    assert sum(1 for s in state.stages if s.stage_id == "conformance") == (
        1 + engine_mod.MAX_REGEN_ROUNDS + engine_mod.MAX_AI_REVIEW_REGEN
    ), ids
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
# resume() from a COMPLETED tip with a PENDING successor (dead-end recovery)
# ----------------------------------------------------------------------


def test_resume_from_completed_tip_advances_to_pending_successor(project, monkeypatch):
    """A project saved/reopened after a review-eligible stage finished but before
    its successor ran persists as overall=PAUSED, tip=COMPLETED, successor=PENDING.
    resume() must NOT no-op there: it re-points the engine at the pending stage and
    runs it, instead of leaving the user permanently stuck.

    Uses two non-review-eligible stages so the successor runs to COMPLETED (a
    review-eligible successor like the real ``rendering`` would correctly pause
    again for its own review — covered separately below)."""
    state = _state(["lands", "card_gen"])
    state.stages[0].status = StageStatus.COMPLETED
    state.stages[1].status = StageStatus.PENDING
    state.current_instance_id = "lands"
    state.overall_status = PipelineStatus.PAUSED
    _patch_clean(monkeypatch, "card_gen")

    PipelineEngine(state, EventBus()).resume()

    successor = state.stages[1]
    assert successor.status == StageStatus.COMPLETED, [s.status for s in state.stages]
    assert state.overall_status == PipelineStatus.COMPLETED
    # The already-completed tip is left completed (not re-run, not re-paused).
    assert state.stages[0].status == StageStatus.COMPLETED


def test_resume_from_completed_tip_into_review_successor_pauses_again(project, monkeypatch):
    """The real art_gen→rendering shape: rendering is review-eligible (default
    break point "review"), so resuming from the completed art_gen tip advances
    INTO rendering, runs it, and pauses it for its own review — the dead-end is
    broken (the successor actually ran) even though the pipeline stays PAUSED."""
    state = _state(["art_gen", "rendering"])
    state.stages[0].status = StageStatus.COMPLETED
    state.stages[1].status = StageStatus.PENDING
    state.current_instance_id = "art_gen"
    state.overall_status = PipelineStatus.PAUSED

    ran: list[str] = []
    monkeypatch.setitem(
        engine_mod.STAGE_RUNNERS,
        "rendering",
        lambda _pc, _em: (ran.append("rendering"), StageResult(detail="ok"))[1],
    )

    PipelineEngine(state, EventBus()).resume()

    rendering = state.stages[1]
    assert ran == ["rendering"]  # the successor actually executed
    assert rendering.status == StageStatus.PAUSED_FOR_REVIEW
    assert state.overall_status == PipelineStatus.PAUSED
    assert state.current_instance_id == rendering.instance_id


def test_resume_from_completed_tip_does_not_rerun_the_tip(project, monkeypatch):
    """The completed tip's runner must not fire again on resume — only the pending
    successor runs. Guards against a regression that re-enters the tip and discards
    its prior (human-reviewed) output."""
    state = _state(["art_gen", "rendering"])
    state.stages[0].status = StageStatus.COMPLETED
    state.stages[1].status = StageStatus.PENDING
    state.current_instance_id = "art_gen"
    state.overall_status = PipelineStatus.PAUSED

    calls: list[str] = []

    def _track(sid):
        def run(_pc, _em):
            calls.append(sid)
            return StageResult(detail="ok")

        return run

    monkeypatch.setitem(engine_mod.STAGE_RUNNERS, "art_gen", _track("art_gen"))
    monkeypatch.setitem(engine_mod.STAGE_RUNNERS, "rendering", _track("rendering"))

    PipelineEngine(state, EventBus()).resume()

    assert calls == ["rendering"]


def test_resume_no_ops_when_completed_tip_has_no_successor(project, monkeypatch):
    """A paused state whose tip completed with nothing left to run can't advance —
    resume() leaves it untouched (no crash, no spurious re-run)."""
    state = _state(["art_gen", "rendering"])
    state.stages[0].status = StageStatus.COMPLETED
    state.stages[1].status = StageStatus.COMPLETED
    state.current_instance_id = "art_gen"
    state.overall_status = PipelineStatus.PAUSED

    calls: list[str] = []
    for sid in ("art_gen", "rendering"):
        monkeypatch.setitem(
            engine_mod.STAGE_RUNNERS,
            sid,
            (lambda s: lambda _pc, _em: (calls.append(s), StageResult(detail="ok"))[1])(sid),
        )

    PipelineEngine(state, EventBus()).resume()

    assert calls == []
    assert state.overall_status == PipelineStatus.PAUSED


def test_resume_normal_paused_for_review_still_completes_tip(project, monkeypatch):
    """The normal break-point path is unchanged: a PAUSED_FOR_REVIEW tip is marked
    COMPLETED and the loop walks forward into the successor."""
    state = _state(["lands", "card_gen"])
    state.stages[0].status = StageStatus.PAUSED_FOR_REVIEW
    state.stages[1].status = StageStatus.PENDING
    state.current_instance_id = "lands"
    state.overall_status = PipelineStatus.PAUSED
    _patch_clean(monkeypatch, "card_gen")

    PipelineEngine(state, EventBus()).resume()

    assert state.stages[0].status == StageStatus.COMPLETED
    assert state.stages[1].status == StageStatus.COMPLETED
    assert state.overall_status == PipelineStatus.COMPLETED


# ----------------------------------------------------------------------
# Mid-run "Stop after this step" toggle (re-resolved from live break points)
# ----------------------------------------------------------------------


def _toggle_break_on(stage_id: str):
    """A clean runner that flips ``stage_id``'s break point on while it runs.

    Simulates the user ticking "Stop after this step" mid-run: the
    /api/wizard/project/breaks endpoint calls ``apply_settings`` with the new
    break_points, which the engine re-reads at its pause decision.
    """

    def run(_pc, _em):
        from mtgai.settings.model_settings import apply_settings, get_active_settings

        s = get_active_settings()
        apply_settings(
            s.model_copy(update={"break_points": {**s.break_points, stage_id: "review"}})
        )
        return StageResult(detail="clean")

    return run


def test_midrun_break_toggle_pauses_after_running_backbone_stage(project, monkeypatch):
    """Ticking "Stop after this step" while a backbone stage runs pauses the
    pipeline after that stage — the engine re-resolves the live break point
    rather than the build-time-frozen (AUTO) review_mode."""
    state = _state(_SPAN)
    _patch_clean(monkeypatch, "card_gen", "ai_review", "finalize")
    monkeypatch.setitem(engine_mod.STAGE_RUNNERS, "conformance", _toggle_break_on("conformance"))

    PipelineEngine(state, EventBus()).run()

    conf = next(s for s in state.stages if s.stage_id == "conformance")
    assert conf.status == StageStatus.PAUSED_FOR_REVIEW
    # The live re-resolve also syncs review_mode so persisted state is honest.
    assert conf.review_mode == StageReviewMode.REVIEW
    assert state.overall_status == PipelineStatus.PAUSED
    # The downstream stage never ran (paused before it).
    assert next(s for s in state.stages if s.stage_id == "ai_review").status == StageStatus.PENDING


def test_midrun_break_toggle_does_not_pause_inserted_loop_instance(project, monkeypatch):
    """An inserted regen-loop instance (conformance.2) stays AUTO even if its
    break point is toggled on mid-run, so the loop still flows. Only backbone
    instances honour a live toggle (preserves the _build_rerun_span contract)."""
    state = _state(_SPAN)
    counter = [0]
    _patch_clean(monkeypatch, "card_gen", "ai_review", "finalize")

    def conformance_runner(_pc, _em):
        # Backbone run flags once -> inserts [card_gen.2, conformance.2].
        if counter[0] == 0:
            counter[0] += 1
            return StageResult(detail="flagged 1", rerun_from="card_gen")
        # The inserted conformance.2 toggles the break on, but as a non-backbone
        # instance it must NOT pause — the regen tail keeps flowing.
        return _toggle_break_on("conformance")(_pc, _em)

    monkeypatch.setitem(engine_mod.STAGE_RUNNERS, "conformance", conformance_runner)

    PipelineEngine(state, EventBus()).run()

    conf2 = next(s for s in state.stages if s.instance_id == "conformance.2")
    assert conf2.status == StageStatus.COMPLETED
    assert conf2.review_mode == StageReviewMode.AUTO
    assert state.overall_status == PipelineStatus.COMPLETED


def test_midrun_break_toggle_off_lets_default_review_stage_continue(project, monkeypatch):
    """The mirror direction: un-ticking a default-on break (skeleton) while it
    runs lets the pipeline auto-continue past it instead of pausing."""
    from mtgai.settings.model_settings import DEFAULT_BREAK_POINTS

    assert DEFAULT_BREAK_POINTS.get("skeleton") == "review"  # guards the premise

    state = _state(["skeleton", "card_gen"])

    def skeleton_runner(_pc, _em):
        from mtgai.settings.model_settings import apply_settings, get_active_settings

        s = get_active_settings()
        apply_settings(
            s.model_copy(update={"break_points": {**s.break_points, "skeleton": "auto"}})
        )
        return StageResult(detail="clean")

    monkeypatch.setitem(engine_mod.STAGE_RUNNERS, "skeleton", skeleton_runner)
    _patch_clean(monkeypatch, "card_gen")

    PipelineEngine(state, EventBus()).run()

    skel = next(s for s in state.stages if s.stage_id == "skeleton")
    assert skel.status == StageStatus.COMPLETED
    assert skel.review_mode == StageReviewMode.AUTO
    assert state.overall_status == PipelineStatus.COMPLETED


def test_midrun_break_toggle_ignored_for_review_ineligible_stage(project, monkeypatch):
    """The live re-read is scoped to review-eligible stages: a review-ineligible
    backbone stage (lands) never pauses, even if its break point is explicitly
    toggled on mid-run."""
    assert _DEFN["lands"]["review_eligible"] is False  # guards the premise

    state = _state(["lands", "card_gen"])
    monkeypatch.setitem(engine_mod.STAGE_RUNNERS, "lands", _toggle_break_on("lands"))
    _patch_clean(monkeypatch, "card_gen")

    PipelineEngine(state, EventBus()).run()

    lands = next(s for s in state.stages if s.stage_id == "lands")
    assert lands.status == StageStatus.COMPLETED
    assert lands.review_mode == StageReviewMode.AUTO
    assert state.overall_status == PipelineStatus.COMPLETED


def test_review_ineligible_stage_with_stale_review_mode_does_not_pause(project, monkeypatch):
    """A review-ineligible stage (lands) that somehow carries a persisted
    review_mode=REVIEW (e.g. a debug-seeded clone that inherited "review" from
    its golden source) must STILL auto-advance — the engine forces an ineligible
    stage to AUTO so a stale/erroneous persisted mode can never pause it. This is
    the documented "review_eligible: False — never pauses for review" contract."""
    assert _DEFN["lands"]["review_eligible"] is False  # guards the premise

    state = _state(["lands", "card_gen"])
    lands = next(s for s in state.stages if s.stage_id == "lands")
    lands.review_mode = StageReviewMode.REVIEW  # stale persisted mode
    monkeypatch.setitem(engine_mod.STAGE_RUNNERS, "lands", _clean)
    _patch_clean(monkeypatch, "card_gen")

    PipelineEngine(state, EventBus()).run()

    lands = next(s for s in state.stages if s.stage_id == "lands")
    assert lands.status == StageStatus.COMPLETED, lands.status
    # The pause check normalized the stale mode back to AUTO.
    assert lands.review_mode == StageReviewMode.AUTO
    # The successor actually ran — the pipeline didn't stall at lands.
    assert next(s for s in state.stages if s.stage_id == "card_gen").status == (
        StageStatus.COMPLETED
    )
    assert state.overall_status == PipelineStatus.COMPLETED


def test_live_break_point_falls_back_to_defaults_without_active_project():
    """_live_break_point degrades to the stage defaults when no project is open
    (the bare-harness path), so a non-wizard caller still gets sane pauses."""
    active_project.clear_active_project()
    assert engine_mod._live_break_point("skeleton") is True  # DEFAULT_BREAK_POINTS -> review
    assert engine_mod._live_break_point("card_gen") is False  # not a default -> auto


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
