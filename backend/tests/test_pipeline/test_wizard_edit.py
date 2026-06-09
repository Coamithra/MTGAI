"""HTTP-level tests for the wizard edit-flow cascade endpoints.

Covers ``POST /api/wizard/edit/preview`` and ``POST /api/wizard/edit/accept``
— the §9 cascade-clear flow that lets the user re-run a stage and
discard everything downstream.

Engine kickoff is stubbed at ``threading.Thread`` (same pattern as
``test_wizard_advance``) so the real engine loop never runs and these
tests stay focused on the cascade plumbing: payload shape, status
codes, on-disk artifact removal, pipeline-state.json reset, and
navigation routing.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mtgai.pipeline import server as pipeline_server
from mtgai.pipeline.engine import load_state, save_state
from mtgai.pipeline.models import (
    PipelineConfig,
    PipelineState,
    PipelineStatus,
    StageState,
    StageStatus,
    create_pipeline_state,
)
from mtgai.review.server import app
from mtgai.runtime import ai_lock, extraction_run
from mtgai.settings import model_settings as ms


@pytest.fixture(autouse=True)
def _reset(isolated_output):
    ai_lock.reset_for_tests()
    extraction_run.reset()
    pipeline_server._engine = None
    pipeline_server._engine_task = None
    yield
    ai_lock.reset_for_tests()
    extraction_run.reset()
    pipeline_server._engine = None
    pipeline_server._engine_task = None


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def no_thread_start(monkeypatch):
    started: list[threading.Thread] = []

    class FakeThread:
        def __init__(self, *_, **kwargs):
            self._target = kwargs.get("target")
            self._kwargs = kwargs

        def start(self):
            started.append(self)

        def join(self, *_a, **_kw):
            return None

    monkeypatch.setattr(pipeline_server.threading, "Thread", FakeThread)
    return started


def _make_set(code: str, *, theme: dict | None = None) -> Path:
    """Pin ``code`` as the active project against an asset folder under the tmp tree."""
    from mtgai.runtime import active_project

    set_dir = ms.OUTPUT_ROOT / "sets" / code
    set_dir.mkdir(parents=True, exist_ok=True)
    if theme is not None:
        (set_dir / "theme.json").write_text(json.dumps(theme), encoding="utf-8")
    active_project.write_active_project(
        active_project.ProjectState(
            set_code=code, settings=ms.ModelSettings(asset_folder=str(set_dir))
        )
    )
    return set_dir


def _seed_state(code: str, *, overall_status: PipelineStatus) -> PipelineState:
    state = create_pipeline_state(
        PipelineConfig(set_code=code, set_name=code, set_size=20),
    )
    state.overall_status = overall_status
    save_state(state)
    return state


# ---------------------------------------------------------------------------
# /api/wizard/edit/preview
# ---------------------------------------------------------------------------


def test_preview_lists_completed_downstream_stages(client):
    _make_set("TST", theme={"code": "TST", "name": "Test"})
    state = _seed_state("TST", overall_status=PipelineStatus.PAUSED)
    # Post-reorder: mechanics[0], archetypes[1]; skeleton/reprints/lands
    # are stages[2..4] (visual_refs moved down to just before art_prompts).
    state.stages[2].status = StageStatus.COMPLETED
    state.stages[2].progress.completed_items = 60
    state.stages[3].status = StageStatus.COMPLETED
    state.stages[3].progress.completed_items = 5
    state.stages[4].status = StageStatus.PAUSED_FOR_REVIEW
    state.stages[4].progress.completed_items = 6
    save_state(state)

    resp = client.post(
        "/api/wizard/edit/preview",
        json={"set_code": "TST", "from_stage": "skeleton"},
    )
    assert resp.status_code == 200
    data = resp.json()
    cleared_ids = [c["stage_id"] for c in data["cleared"]]
    # All three non-pending stages reported, in pipeline order.
    assert cleared_ids[:3] == ["skeleton", "reprints", "lands"]
    # Item counts come through.
    assert data["cleared"][0]["item_count"] == 60
    # No theme.json wipe by default.
    assert data["clear_theme_json"] is False


def test_preview_skips_pending_stages(client):
    _make_set("TST", theme={"code": "TST"})
    state = _seed_state("TST", overall_status=PipelineStatus.NOT_STARTED)
    # Mark skeleton (stages[2] post-reorder) COMPLETED; mechanics +
    # archetypes + downstream stay PENDING and excluded from the cleared list.
    state.stages[2].status = StageStatus.COMPLETED
    save_state(state)

    resp = client.post(
        "/api/wizard/edit/preview",
        json={"set_code": "TST", "from_stage": "theme"},
    )
    data = resp.json()
    # Only the one COMPLETED stage shows up; PENDING ones are skipped.
    assert [c["stage_id"] for c in data["cleared"]] == ["skeleton"]


def test_preview_clear_theme_json_reflects_disk(client):
    """``clear_theme_json`` only flips on when theme.json actually exists."""
    _make_set("TST")  # No theme.json
    resp = client.post(
        "/api/wizard/edit/preview",
        json={"set_code": "TST", "from_stage": "project", "clear_theme_json": True},
    )
    data = resp.json()
    assert data["clear_theme_json"] is False  # nothing on disk to clear

    _make_set("TST", theme={"code": "TST"})  # Now theme.json exists
    resp = client.post(
        "/api/wizard/edit/preview",
        json={"set_code": "TST", "from_stage": "project", "clear_theme_json": True},
    )
    assert resp.json()["clear_theme_json"] is True


def test_preview_400_for_unknown_stage(client):
    _make_set("TST")
    _seed_state("TST", overall_status=PipelineStatus.PAUSED)
    resp = client.post(
        "/api/wizard/edit/preview",
        json={"set_code": "TST", "from_stage": "nonexistent"},
    )
    assert resp.status_code == 400


def test_preview_400_for_missing_from_stage(client):
    _make_set("TST")
    resp = client.post("/api/wizard/edit/preview", json={"set_code": "TST"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /api/wizard/edit/accept — cascade clear + state reset
# ---------------------------------------------------------------------------


def test_accept_cascades_artifacts_and_resets_stages(client, no_thread_start):
    """Accepting a Skeleton edit clears skeleton.json, card_gen cards, art/, etc."""
    set_dir = _make_set("TST", theme={"code": "TST"})
    (set_dir / "skeleton.json").write_text("{}", encoding="utf-8")
    (set_dir / "reprint_selection.json").write_text("{}", encoding="utf-8")
    cards = set_dir / "cards"
    cards.mkdir()
    (cards / "001_foo.json").write_text("{}", encoding="utf-8")

    state = _seed_state("TST", overall_status=PipelineStatus.PAUSED)
    # Post-reorder: mechanics[0], archetypes[1], skeleton[2], reprints[3],
    # lands[4], card_gen[5]. (visual_refs moved down to before art_prompts,
    # so it's no longer upstream of skeleton.)
    state.stages[0].status = StageStatus.COMPLETED  # mechanics (upstream of cascade)
    state.stages[1].status = StageStatus.COMPLETED  # archetypes (upstream of cascade)
    state.stages[2].status = StageStatus.COMPLETED  # skeleton
    state.stages[3].status = StageStatus.COMPLETED  # reprints
    state.stages[5].status = StageStatus.PAUSED_FOR_REVIEW  # card_gen
    state.current_instance_id = state.stages[5].instance_id
    save_state(state)

    resp = client.post(
        "/api/wizard/edit/accept",
        json={"set_code": "TST", "from_stage": "skeleton"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    # theme.json still exists -> kickoff requested, navigate to first PENDING.
    assert data["engine_started"] is True
    assert data["next_stage_id"] == "skeleton"
    assert data["navigate_to"] == "/pipeline/skeleton"

    assert not (set_dir / "skeleton.json").exists()
    assert not (set_dir / "reprint_selection.json").exists()
    # Scoped clear removes the card_gen-owned card (the dir itself may remain,
    # now that clear_card_gen preserves the lands stage's L-* in place).
    assert not (cards / "001_foo.json").exists()

    reloaded = load_state()
    assert reloaded is not None
    # mechanics (upstream of the cascade boundary) stays COMPLETED;
    # everything from skeleton onward resets to PENDING.
    by_id = {s.stage_id: s for s in reloaded.stages}
    assert by_id["mechanics"].status == StageStatus.COMPLETED
    assert by_id["archetypes"].status == StageStatus.COMPLETED
    for sid in ("skeleton", "reprints", "lands", "card_gen"):
        assert by_id[sid].status == StageStatus.PENDING
    assert reloaded.current_instance_id is None


def test_accept_from_theme_resets_all_pipeline_stages(client, no_thread_start):
    set_dir = _make_set("TST", theme={"code": "TST"})
    (set_dir / "skeleton.json").write_text("{}", encoding="utf-8")

    state = _seed_state("TST", overall_status=PipelineStatus.PAUSED)
    state.stages[2].status = StageStatus.COMPLETED  # skeleton (post-reorder ordering)
    save_state(state)

    resp = client.post(
        "/api/wizard/edit/accept",
        json={"set_code": "TST", "from_stage": "theme"},
    )
    assert resp.status_code == 200
    # Cascade from "theme" resets every pipeline stage; the engine's
    # first PENDING after the reset is mechanics (the first pipeline
    # stage).
    assert resp.json()["next_stage_id"] == "mechanics"
    assert not (set_dir / "skeleton.json").exists()


def test_accept_from_theme_persists_payload(client, no_thread_start):
    set_dir = _make_set("TST", theme={"code": "TST", "name": "Old"})
    new_theme = {
        "code": "TST",
        "name": "Renamed",
        "constraints": [{"text": "no dragons", "source": "human"}],
    }
    resp = client.post(
        "/api/wizard/edit/accept",
        json={
            "set_code": "TST",
            "from_stage": "theme",
            "theme_payload": new_theme,
        },
    )
    assert resp.status_code == 200
    on_disk = json.loads((set_dir / "theme.json").read_text(encoding="utf-8"))
    assert on_disk["name"] == "Renamed"
    assert on_disk["constraints"][0]["text"] == "no dragons"


def test_accept_clear_theme_json_returns_to_project(client, no_thread_start):
    """Theme-input change wipes theme.json; user is sent back to /pipeline/project."""
    set_dir = _make_set("TST", theme={"code": "TST"})
    (set_dir / "skeleton.json").write_text("{}", encoding="utf-8")
    _seed_state("TST", overall_status=PipelineStatus.PAUSED)

    resp = client.post(
        "/api/wizard/edit/accept",
        json={
            "set_code": "TST",
            "from_stage": "project",
            "clear_theme_json": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["navigate_to"] == "/pipeline/project"
    assert data["engine_started"] is False
    assert data["next_stage_id"] is None
    assert not (set_dir / "theme.json").exists()
    assert not (set_dir / "skeleton.json").exists()
    # State is preserved with everything reset to PENDING — the user
    # clicks Start to re-extract.
    reloaded = load_state()
    assert reloaded is not None
    assert all(s.status == StageStatus.PENDING for s in reloaded.stages)


def test_accept_persists_set_params_patch(client, no_thread_start):
    _make_set("TST", theme={"code": "TST"})
    _seed_state("TST", overall_status=PipelineStatus.PAUSED)

    resp = client.post(
        "/api/wizard/edit/accept",
        json={
            "set_code": "TST",
            "from_stage": "project",
            "set_params_patch": {"set_size": 80},
        },
    )
    assert resp.status_code == 200
    settings = ms.get_active_settings()
    assert settings.set_params.set_size == 80


def test_accept_persists_theme_input_patch(client, no_thread_start):
    set_dir = _make_set("TST", theme={"code": "TST"})
    (set_dir / "skeleton.json").write_text("{}", encoding="utf-8")
    _seed_state("TST", overall_status=PipelineStatus.PAUSED)

    resp = client.post(
        "/api/wizard/edit/accept",
        json={
            "set_code": "TST",
            "from_stage": "project",
            "clear_theme_json": True,
            "theme_input": {
                "kind": "pdf",
                "filename": "new.pdf",
                "upload_id": "abc123",
                "char_count": 12345,
            },
        },
    )
    assert resp.status_code == 200
    settings = ms.get_active_settings()
    assert settings.theme_input.kind == "pdf"
    assert settings.theme_input.filename == "new.pdf"
    assert settings.theme_input.upload_id == "abc123"


def test_accept_409_when_engine_running(client, monkeypatch):
    set_dir = _make_set("TST", theme={"code": "TST"})
    (set_dir / "skeleton.json").write_text("{}", encoding="utf-8")
    seeded = _seed_state("TST", overall_status=PipelineStatus.RUNNING)
    seeded.stages[0].status = StageStatus.COMPLETED
    seeded.stages[0].progress.completed_items = 60
    save_state(seeded)
    seeded_dump = load_state().model_dump(mode="json")

    class _BusyEngine:
        is_running = True

        def __init__(self) -> None:
            self.state = create_pipeline_state(
                PipelineConfig(set_code="TST", set_name="TST", set_size=20),
            )

    monkeypatch.setattr(pipeline_server, "_engine", _BusyEngine())

    resp = client.post(
        "/api/wizard/edit/accept",
        json={"set_code": "TST", "from_stage": "skeleton"},
    )
    assert resp.status_code == 409
    assert "running" in resp.json()["error"].lower()
    # 409 must not have mutated state on disk: the cascade-clear writes
    # are gated behind the engine-running check, so pipeline-state.json
    # and skeleton.json should be untouched.
    assert (set_dir / "skeleton.json").exists()
    assert load_state().model_dump(mode="json") == seeded_dump


def test_accept_409_when_extraction_running(client):
    """A mid-flight theme extraction also blocks Accept — a new theme.json
    write would race the cascade clear."""
    _make_set("TST", theme={"code": "TST"})
    _seed_state("TST", overall_status=PipelineStatus.PAUSED)
    extraction_run.start_run("upload-xyz")

    resp = client.post(
        "/api/wizard/edit/accept",
        json={"set_code": "TST", "from_stage": "skeleton"},
    )
    assert resp.status_code == 409
    assert "extraction" in resp.json()["error"].lower()


def test_accept_400_for_invalid_set_size(client):
    from mtgai.settings.model_settings import MAX_SET_SIZE

    _make_set("TST", theme={"code": "TST"})
    _seed_state("TST", overall_status=PipelineStatus.PAUSED)

    for bad in (-3, 0, "abc", None, MAX_SET_SIZE + 1):
        resp = client.post(
            "/api/wizard/edit/accept",
            json={
                "set_code": "TST",
                "from_stage": "project",
                "set_params_patch": {"set_size": bad},
            },
        )
        assert resp.status_code == 400, f"Expected 400 for set_size={bad!r}, got {resp.status_code}"


def test_accept_400_for_negative_mechanic_count(client):
    from mtgai.generation.mechanic_generator import MAX_MECHANIC_COUNT

    _make_set("TST", theme={"code": "TST"})
    _seed_state("TST", overall_status=PipelineStatus.PAUSED)
    for bad in (-1, MAX_MECHANIC_COUNT + 1):
        resp = client.post(
            "/api/wizard/edit/accept",
            json={
                "set_code": "TST",
                "from_stage": "project",
                "set_params_patch": {"mechanic_count": bad},
            },
        )
        assert resp.status_code == 400, (
            f"Expected 400 for mechanic_count={bad!r}, got {resp.status_code}"
        )


def test_accept_400_for_non_dict_patch(client):
    _make_set("TST", theme={"code": "TST"})
    _seed_state("TST", overall_status=PipelineStatus.PAUSED)
    resp = client.post(
        "/api/wizard/edit/accept",
        json={
            "set_code": "TST",
            "from_stage": "project",
            "set_params_patch": [1, 2, 3],
        },
    )
    assert resp.status_code == 400


def test_accept_400_for_unknown_stage(client):
    _make_set("TST", theme={"code": "TST"})
    resp = client.post(
        "/api/wizard/edit/accept",
        json={"set_code": "TST", "from_stage": "nonexistent"},
    )
    assert resp.status_code == 400


def test_accept_400_for_missing_from_stage(client):
    _make_set("TST", theme={"code": "TST"})
    resp = client.post("/api/wizard/edit/accept", json={"set_code": "TST"})
    assert resp.status_code == 400


def test_accept_400_for_invalid_theme_input_kind(client):
    _make_set("TST", theme={"code": "TST"})
    _seed_state("TST", overall_status=PipelineStatus.PAUSED)
    resp = client.post(
        "/api/wizard/edit/accept",
        json={
            "set_code": "TST",
            "from_stage": "project",
            "theme_input": {"kind": "garbage"},
        },
    )
    assert resp.status_code == 400


def test_accept_idempotent_when_no_state_on_disk(client, no_thread_start):
    """A brand-new set (no pipeline-state.json) accepts a project edit
    by writing settings + bouncing to /pipeline/project. Mostly a guard
    against a stale wizard tab calling Accept after the user wiped the
    set folder; the endpoint should not 500."""
    _make_set("TST")  # no theme.json, no pipeline-state.json
    resp = client.post(
        "/api/wizard/edit/accept",
        json={"set_code": "TST", "from_stage": "project"},
    )
    assert resp.status_code == 200
    assert resp.json()["navigate_to"] == "/pipeline/project"


def test_resolve_edit_point_zero_for_project_and_theme():
    state = create_pipeline_state(
        PipelineConfig(set_code="TST", set_name="TST", set_size=20),
    )
    assert pipeline_server._resolve_edit_point("project", state) == 0
    assert pipeline_server._resolve_edit_point("theme", state) == 0


def test_resolve_edit_point_returns_stage_index():
    state = create_pipeline_state(
        PipelineConfig(set_code="TST", set_name="TST", set_size=20),
    )
    # card_gen is the 6th stage (index 5) per STAGE_DEFINITIONS post-reorder:
    # mechanics, archetypes, skeleton, reprints, lands, card_gen
    # (visual_refs moved down to just before art_prompts).
    assert pipeline_server._resolve_edit_point("card_gen", state) == 5


def test_resolve_edit_point_raises_for_unknown_stage():
    state = create_pipeline_state(
        PipelineConfig(set_code="TST", set_name="TST", set_size=20),
    )
    with pytest.raises(ValueError):
        pipeline_server._resolve_edit_point("garbage", state)


# ---------------------------------------------------------------------------
# _apply_cascade_clear — regen-instance truncation
# ---------------------------------------------------------------------------


def _loop_state(code: str) -> PipelineState:
    """A run that bounced once: a regen span (card_gen.2, conformance.2) was
    inserted after the backbone loop, mirroring the engine's review->regen
    insertion. ``lands`` precedes the loop so there is an untouched prefix."""
    order = [
        ("lands", "lands", "Land Generation"),
        ("card_gen", "card_gen", "Card Generation"),
        ("conformance", "conformance", "Conformance & Interactions"),
        ("ai_review", "ai_review", "AI Design Review"),
        ("card_gen", "card_gen.2", "Card Generation 2"),
        ("conformance", "conformance.2", "Conformance & Interactions 2"),
        ("ai_review", "ai_review.2", "AI Design Review 2"),
    ]
    stages = [
        StageState(
            stage_id=sid,
            instance_id=iid,
            display_name=dn,
            status=StageStatus.COMPLETED,
        )
        for sid, iid, dn in order
    ]
    return PipelineState(
        config=PipelineConfig(set_code=code, set_name=code, set_size=20),
        stages=stages,
        current_instance_id="ai_review.2",
    )


def test_cascade_clear_drops_regen_inserted_instances():
    _make_set("TST")
    state = _loop_state("TST")
    # Cascade from the backbone card_gen (index 1) — clears card_gen onward.
    pipeline_server._apply_cascade_clear(state, 1)

    ids = [s.instance_id for s in state.stages]
    # The untouched prefix survives; only backbone instances of each cleared
    # stage_id remain (the regen-inserted .2 duplicates are gone), so the engine
    # can't re-run them as stale duplicate rounds.
    assert ids == ["lands", "card_gen", "conformance", "ai_review"]
    # Cleared backbones reset to PENDING; the prefix is untouched.
    by_id = {s.instance_id: s for s in state.stages}
    assert by_id["lands"].status == StageStatus.COMPLETED
    assert by_id["card_gen"].status == StageStatus.PENDING
    assert by_id["conformance"].status == StageStatus.PENDING
    assert by_id["ai_review"].status == StageStatus.PENDING
    # current_instance_id pointed at a now-removed instance -> dropped.
    assert state.current_instance_id is None
    assert state.overall_status == PipelineStatus.NOT_STARTED


def test_cascade_clear_keeps_full_prefix_when_start_is_zero():
    _make_set("TST")
    state = _loop_state("TST")
    pipeline_server._apply_cascade_clear(state, 0)
    ids = [s.instance_id for s in state.stages]
    assert ids == ["lands", "card_gen", "conformance", "ai_review"]
    assert all(s.status == StageStatus.PENDING for s in state.stages)


# ---------------------------------------------------------------------------
# _apply_downstream_clear + /api/wizard/edit/unlock — keep edited stage,
# discard downstream (the "Edit" model)
# ---------------------------------------------------------------------------


def test_downstream_clear_keeps_edited_stage_and_drops_regen_instances():
    set_dir = _make_set("TST")
    # The edited backbone card_gen's live output must survive — even though a
    # downstream regen duplicate (card_gen.2) shares its stage_id, whose clearer
    # would otherwise wipe the shared cards/ dir.
    cards = set_dir / "cards"
    cards.mkdir()
    (cards / "001_foo.json").write_text("{}", encoding="utf-8")

    state = _loop_state("TST")
    # Unlock the backbone card_gen (index 1): keep lands + card_gen, discard
    # everything after, drop the regen-inserted .2 duplicates.
    pipeline_server._apply_downstream_clear(state, 1)

    # The edited stage's own card files are preserved (the unlock invariant).
    assert (cards / "001_foo.json").exists()

    ids = [s.instance_id for s in state.stages]
    assert ids == ["lands", "card_gen", "conformance", "ai_review"]
    by_id = {s.instance_id: s for s in state.stages}
    # The edited stage keeps its output and becomes the paused, editable tip.
    assert by_id["lands"].status == StageStatus.COMPLETED  # untouched prefix
    assert by_id["card_gen"].status == StageStatus.PAUSED_FOR_REVIEW
    # Downstream reset to PENDING.
    assert by_id["conformance"].status == StageStatus.PENDING
    assert by_id["ai_review"].status == StageStatus.PENDING
    assert state.current_instance_id == "card_gen"
    assert state.overall_status == PipelineStatus.PAUSED


def test_downstream_clear_preserves_pool_across_loop_stage_with_regen_card_gen():
    """Regression: unlocking a review-gate tab (``conformance``) must NOT wipe
    the generated card pool when a regen ``card_gen.N`` sits downstream.

    The loop stages (lands / card_gen / conformance / ai_review) all share ONE
    live ``cards/`` working set keyed by stage_id. After a review->regen bounce
    the plan contains a downstream ``card_gen.2`` whose stage_id (``card_gen``)
    differs from the EDITED stage_id (``conformance``); the old
    ``stage.stage_id != edited_stage_id`` guard therefore ran
    ``clear_card_gen`` and deleted every non-``L-*`` ``cards/*.json`` — silently
    losing the whole generated set while the backbone card_gen stayed
    COMPLETED. The fix skips the artifact-clear for the entire pool-sharing
    loop-stage set, so the kept pool survives."""
    set_dir = _make_set("TST")
    cards = set_dir / "cards"
    cards.mkdir()
    # A generated card (owned by the kept backbone card_gen) + a land card.
    (cards / "001_foo.json").write_text("{}", encoding="utf-8")
    (cards / "L-01_plains.json").write_text(
        '{"collector_number": "L-01", "supertypes": ["Basic"], "type_line": "Basic Land"}',
        encoding="utf-8",
    )

    state = _loop_state("TST")
    # Unlock the BACKBONE conformance (index 2): keep lands + card_gen +
    # conformance, discard ai_review onward — which includes the downstream
    # regen ``card_gen.2`` (index 4).
    pipeline_server._apply_downstream_clear(state, 2)

    # The generated pool must survive — the unlock keeps the kept upstream
    # card_gen output, and the downstream card_gen.2 clear must NOT fire.
    assert (cards / "001_foo.json").exists()
    assert (cards / "L-01_plains.json").exists()

    ids = [s.instance_id for s in state.stages]
    # lands + card_gen + conformance kept; ai_review reset; regen .2 duplicates
    # dropped.
    assert ids == ["lands", "card_gen", "conformance", "ai_review"]
    by_id = {s.instance_id: s for s in state.stages}
    assert by_id["lands"].status == StageStatus.COMPLETED
    assert by_id["card_gen"].status == StageStatus.COMPLETED
    assert by_id["conformance"].status == StageStatus.PAUSED_FOR_REVIEW
    assert by_id["ai_review"].status == StageStatus.PENDING
    assert state.current_instance_id == "conformance"
    assert state.overall_status == PipelineStatus.PAUSED


def test_unlock_endpoint_keeps_stage_clears_downstream(client):
    set_dir = _make_set("TST", theme={"code": "TST"})
    (set_dir / "skeleton.json").write_text("{}", encoding="utf-8")
    (set_dir / "reprint_selection.json").write_text("{}", encoding="utf-8")

    state = _seed_state("TST", overall_status=PipelineStatus.PAUSED)
    # mechanics[0], archetypes[1], skeleton[2], reprints[3], lands[4]...
    for i in range(5):
        state.stages[i].status = StageStatus.COMPLETED
    state.current_instance_id = state.stages[4].instance_id
    save_state(state)

    resp = client.post("/api/wizard/edit/unlock", json={"from_stage": "skeleton"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["navigate_to"] == "/pipeline/skeleton"

    # The edited stage keeps its artifact; downstream is cleared.
    assert (set_dir / "skeleton.json").exists()
    assert not (set_dir / "reprint_selection.json").exists()

    reloaded = load_state()
    by_id = {s.stage_id: s for s in reloaded.stages}
    assert by_id["mechanics"].status == StageStatus.COMPLETED  # upstream untouched
    assert by_id["archetypes"].status == StageStatus.COMPLETED
    assert by_id["skeleton"].status == StageStatus.PAUSED_FOR_REVIEW  # kept + active
    for sid in ("reprints", "lands"):
        assert by_id[sid].status == StageStatus.PENDING
    assert reloaded.overall_status == PipelineStatus.PAUSED
    assert reloaded.current_instance_id == by_id["skeleton"].instance_id


def test_unlock_resyncs_stale_in_memory_engine(client):
    """Regression: after an unlock, ``_get_current_state()`` must serve the
    freshly-cleared on-disk state, not a stale in-memory engine.

    Repro (the filed bug): the project paused at a tip with the engine still
    retained in memory (e.g. after a regen loop). ``_get_current_state()``
    prefers ``_engine.state`` whenever an engine exists, so the unlock used to
    rewrite pipeline-state.json correctly but leave the UI serving the
    pre-unlock state (deleted regen tabs, a now-removed tip) until a server
    restart.
    """
    _make_set("TST", theme={"code": "TST"})
    state = _seed_state("TST", overall_status=PipelineStatus.PAUSED)
    # A full run paused downstream: mechanics..lands done, card_gen the tip.
    for i in range(6):
        state.stages[i].status = StageStatus.COMPLETED
    state.current_instance_id = state.stages[5].instance_id  # card_gen
    save_state(state)

    # An engine retained in memory holding the PRE-unlock snapshot — exactly the
    # stale state _get_current_state() would otherwise keep serving (it prefers
    # _engine.state whenever an engine exists). Idle, so the running-guard lets
    # the unlock proceed. Capture the pre-unlock view to prove it's stale after.
    pre = load_state()
    pipeline_server._engine = pipeline_server.PipelineEngine(pre, pipeline_server.event_bus)
    assert pipeline_server._engine.is_running is False
    assert pipeline_server._get_current_state().stages[5].status == StageStatus.COMPLETED

    resp = client.post("/api/wizard/edit/unlock", json={"from_stage": "skeleton"})
    assert resp.status_code == 200

    # WITHOUT a server/engine restart, the served state must match the on-disk
    # state (the bug: the engine kept serving the pre-unlock state until restart).
    served = pipeline_server._get_current_state()
    on_disk = load_state()
    assert served is not None and on_disk is not None
    assert served.model_dump(mode="json") == on_disk.model_dump(mode="json")

    by_id = {s.stage_id: s for s in served.stages}
    # The edited stage is the paused, editable tip; downstream reset to PENDING.
    assert by_id["skeleton"].status == StageStatus.PAUSED_FOR_REVIEW
    assert served.current_instance_id == by_id["skeleton"].instance_id
    assert served.overall_status == PipelineStatus.PAUSED
    for sid in ("reprints", "lands", "card_gen"):
        assert by_id[sid].status == StageStatus.PENDING
    # And the in-memory engine itself was repointed (not just the disk).
    assert pipeline_server._engine.state.current_instance_id == by_id["skeleton"].instance_id


def test_unlock_409_when_engine_running(client, monkeypatch):
    set_dir = _make_set("TST", theme={"code": "TST"})
    (set_dir / "skeleton.json").write_text("{}", encoding="utf-8")
    seeded = _seed_state("TST", overall_status=PipelineStatus.RUNNING)
    seeded.stages[2].status = StageStatus.COMPLETED
    save_state(seeded)
    seeded_dump = load_state().model_dump(mode="json")

    class _BusyEngine:
        is_running = True

        def __init__(self) -> None:
            self.state = create_pipeline_state(
                PipelineConfig(set_code="TST", set_name="TST", set_size=20),
            )

    monkeypatch.setattr(pipeline_server, "_engine", _BusyEngine())

    resp = client.post("/api/wizard/edit/unlock", json={"from_stage": "skeleton"})
    assert resp.status_code == 409
    assert "running" in resp.json()["error"].lower()
    # No mutation on a 409.
    assert (set_dir / "skeleton.json").exists()
    assert load_state().model_dump(mode="json") == seeded_dump


def test_unlock_400_for_project_or_theme(client):
    _make_set("TST", theme={"code": "TST"})
    _seed_state("TST", overall_status=PipelineStatus.PAUSED)
    for bad in ("project", "theme"):
        resp = client.post("/api/wizard/edit/unlock", json={"from_stage": bad})
        assert resp.status_code == 400


def test_unlock_400_for_unknown_stage(client):
    _make_set("TST", theme={"code": "TST"})
    _seed_state("TST", overall_status=PipelineStatus.PAUSED)
    resp = client.post("/api/wizard/edit/unlock", json={"from_stage": "garbage"})
    assert resp.status_code == 400


def test_preview_after_only_lists_downstream_only(client):
    _make_set("TST", theme={"code": "TST"})
    state = _seed_state("TST", overall_status=PipelineStatus.PAUSED)
    # skeleton[2], reprints[3], lands[4] all completed.
    for i in (2, 3, 4):
        state.stages[i].status = StageStatus.COMPLETED
        state.stages[i].progress.completed_items = 5
    save_state(state)

    resp = client.post(
        "/api/wizard/edit/preview",
        json={"from_stage": "skeleton", "after_only": True},
    )
    assert resp.status_code == 200
    cleared_ids = [c["stage_id"] for c in resp.json()["cleared"]]
    # skeleton itself is kept (after_only) — only downstream is listed.
    assert "skeleton" not in cleared_ids
    assert cleared_ids[:2] == ["reprints", "lands"]


# ---------------------------------------------------------------------------
# _resolve_stage_instance / status + heal prefer the active regen instance
# ---------------------------------------------------------------------------


def test_resolve_stage_instance_prefers_current_instance():
    state = _loop_state("TST")
    state.current_instance_id = "card_gen.2"
    state.stages[4].status = StageStatus.RUNNING  # card_gen.2
    resolved = pipeline_server._resolve_stage_instance(state, "card_gen")
    assert resolved is not None
    assert resolved.instance_id == "card_gen.2"


def test_resolve_stage_instance_falls_back_to_backbone():
    state = _loop_state("TST")
    # current_instance_id belongs to a *different* stage_id -> use the backbone.
    state.current_instance_id = "conformance.2"
    resolved = pipeline_server._resolve_stage_instance(state, "card_gen")
    assert resolved is not None
    assert resolved.instance_id == "card_gen"


def test_resolve_stage_instance_none_for_unknown_stage():
    state = _loop_state("TST")
    assert pipeline_server._resolve_stage_instance(state, "nope") is None


def test_stage_status_prefers_active_regen_instance():
    _make_set("TST")
    state = _loop_state("TST")
    state.current_instance_id = "card_gen.2"
    state.stages[1].status = StageStatus.COMPLETED  # backbone card_gen
    state.stages[4].status = StageStatus.RUNNING  # card_gen.2
    save_state(state)
    # Reports the active instance's RUNNING, not the backbone's COMPLETED.
    assert pipeline_server._stage_status_in_state("card_gen") == "running"


def test_heal_failed_stage_heals_active_regen_instance():
    _make_set("TST")
    state = _loop_state("TST")
    state.current_instance_id = "card_gen.2"
    state.stages[1].status = StageStatus.COMPLETED  # backbone card_gen
    state.stages[4].status = StageStatus.FAILED  # card_gen.2
    state.overall_status = PipelineStatus.FAILED
    save_state(state)

    pipeline_server._heal_failed_stage("card_gen")

    healed = load_state()
    by_id = {s.instance_id: s for s in healed.stages}
    # The active failed instance was demoted; the backbone is untouched.
    assert by_id["card_gen.2"].status == StageStatus.PAUSED_FOR_REVIEW
    assert by_id["card_gen"].status == StageStatus.COMPLETED
    assert healed.overall_status == PipelineStatus.PAUSED
