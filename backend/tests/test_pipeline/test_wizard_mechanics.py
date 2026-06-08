"""HTTP-level tests for the Mechanics wizard endpoints (TC-2).

Pin the FastAPI contract: payload shape, status codes, the AI-busy 409,
and the side effects of /save (approved.json + sidecars). The
underlying generator is monkey-patched so tests don't hit a real LLM.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mtgai.generation import mechanic_generator as mg
from mtgai.pipeline import server as pipeline_server
from mtgai.pipeline.engine import save_state
from mtgai.pipeline.models import (
    PipelineConfig,
    PipelineStatus,
    StageStatus,
    create_pipeline_state,
)
from mtgai.review.server import app
from mtgai.runtime import active_project, ai_lock, extraction_run
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


def _seed_project(asset_dir: Path, *, mechanic_count: int = 3) -> None:
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / "theme.json").write_text(
        json.dumps(
            {
                "code": "TST",
                "name": "Test Set",
                "theme": "Steampunk dragons.",
                "flavor_description": "Brass cities tethered by chains.",
                "draft_archetypes": [{"color_pair": "WU", "name": "Aether"}],
                "creature_types": ["Dragon"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    settings = ms.ModelSettings(
        asset_folder=str(asset_dir),
        set_params=ms.SetParams(set_name="Brass Sky", set_size=60, mechanic_count=mechanic_count),
    )
    active_project.write_active_project(
        active_project.ProjectState(set_code="TST", settings=settings)
    )


def _make_candidate(name: str) -> dict:
    return {
        "name": name,
        "keyword_type": "keyword_ability",
        "reminder_text": f"({name} reminder)",
        "colors": ["W"],
        "complexity": 1,
        "flavor_connection": "fits",
        "design_rationale": f"why {name}",
        "common_patterns": ["pattern"],
        "uncommon_patterns": [],
        "rare_patterns": [],
        "example_cards": [],
    }


def _stub_llm(monkeypatch) -> None:
    """Make ``generate_with_tool`` a no-LLM stub: generation returns 6 candidates;
    every council reviewer passes OK (so no synth runs and drafts are accepted
    unchanged — the cheap path)."""

    def stub(*args, **kwargs):
        schema = kwargs.get("tool_schema") or (args[2] if len(args) >= 3 else {})
        if (schema or {}).get("name") == "submit_mechanic_review":
            return {
                "result": {"verdict": "OK", "issues": []},
                "input_tokens": 0,
                "output_tokens": 0,
            }
        return {
            "result": {"mechanics": [_make_candidate(f"M{i}") for i in range(6)]},
            "input_tokens": 1,
            "output_tokens": 2,
        }

    monkeypatch.setattr(mg, "generate_with_tool", stub)


# ---------------------------------------------------------------------------
# GET /api/wizard/mechanics/state
# ---------------------------------------------------------------------------


def test_state_returns_set_params_and_status_when_no_candidates(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    resp = client.get("/api/wizard/mechanics/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["candidates"] == []
    assert data["approved"] is None
    assert data["set_params"]["mechanic_count"] == 3
    assert data["set_params"]["set_size"] == 60
    assert data["theme_summary"].startswith("Steampunk dragons")
    assert data["stage_status"] == "pending"  # no engine state yet


def test_state_surfaces_existing_candidates_and_collisions(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    candidates = [_make_candidate(f"C{i}") for i in range(6)]
    candidates[2]["name"] = "Scavenge"  # printed-keyword collision
    (asset / "mechanics").mkdir()
    (asset / "mechanics" / "candidates.json").write_text(json.dumps(candidates), encoding="utf-8")
    resp = client.get("/api/wizard/mechanics/state")
    data = resp.json()
    assert len(data["candidates"]) == 6
    assert data["collisions"]["2"] == "Scavenge"


def test_state_409_when_no_active_project(client):
    resp = client.get("/api/wizard/mechanics/state")
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_active_project"


# ---------------------------------------------------------------------------
# POST /api/wizard/mechanics/refresh-card
# ---------------------------------------------------------------------------


def test_refresh_card_replaces_only_indexed_slot(client, isolated_output, monkeypatch):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _stub_llm(monkeypatch)
    candidates = [_make_candidate(f"User{i}") for i in range(6)]

    resp = client.post(
        "/api/wizard/mechanics/refresh-card",
        json={"candidate_index": 2, "candidates": candidates},
    )
    assert resp.status_code == 200
    data = resp.json()
    new = data["candidates"]
    assert len(new) == 6
    # User-edited rows survive.
    for i, mech in enumerate(new):
        if i == 2:
            assert mech["name"] == "M0"  # stub returns M0..M5; first one lands here
        else:
            assert mech["name"] == f"User{i}"
    # Persisted to candidates.json.
    on_disk = json.loads((asset / "mechanics" / "candidates.json").read_text())
    assert on_disk[2]["name"] == "M0"


def test_refresh_card_500_envelope_when_no_candidates(client, isolated_output, monkeypatch):
    """A direct ``raise AIActionError`` inside a guarded endpoint ("LLM returned no
    candidates") renders as the flat 500 ``{"error": ...}`` envelope (not FastAPI's
    ``{"detail": ...}``), and the guard releases the lock afterwards."""

    def stub_empty(*_a, **_k):
        return {"mechanics": [], "model_id": "m"}

    monkeypatch.setattr(mg, "generate_mechanic_candidates", stub_empty)
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    resp = client.post(
        "/api/wizard/mechanics/refresh-card",
        json={"candidate_index": 0, "candidates": [_make_candidate(f"U{i}") for i in range(6)]},
    )
    assert resp.status_code == 500
    assert "no candidates" in resp.json()["error"]
    assert ai_lock.is_running() is False  # guard released the lock on the raise


def test_refresh_card_400_on_bad_index(client, isolated_output, monkeypatch):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _stub_llm(monkeypatch)
    resp = client.post(
        "/api/wizard/mechanics/refresh-card",
        json={"candidate_index": 99, "candidates": [_make_candidate("X")]},
    )
    assert resp.status_code == 400


def test_refresh_card_409_when_ai_busy(client, isolated_output, monkeypatch):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _stub_llm(monkeypatch)
    # Use the canonical context-manager pattern so the test couples to
    # the same surface the production callers do. Hold the lock for
    # the duration of the request to simulate concurrent AI work.
    with ai_lock.hold("Other action") as acquired:
        assert acquired
        resp = client.post(
            "/api/wizard/mechanics/refresh-card",
            json={"candidate_index": 0, "candidates": [_make_candidate("X")]},
        )
        assert resp.status_code == 409
        assert resp.json()["running_action"] == "Other action"


# ---------------------------------------------------------------------------
# POST /api/wizard/mechanics/refresh-all
# ---------------------------------------------------------------------------


def test_refresh_all_replaces_only_listed_indices(client, isolated_output, monkeypatch):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _stub_llm(monkeypatch)
    candidates = [_make_candidate(f"User{i}") for i in range(6)]

    resp = client.post(
        "/api/wizard/mechanics/refresh-all",
        json={"indices": [0, 3], "candidates": candidates},
    )
    assert resp.status_code == 200
    new = resp.json()["candidates"]
    assert new[0]["name"] == "M0"
    assert new[3]["name"] == "M1"
    # Untouched indices preserve user edits.
    assert new[1]["name"] == "User1"
    assert new[2]["name"] == "User2"
    assert new[4]["name"] == "User4"
    assert new[5]["name"] == "User5"


def test_refresh_all_reruns_picker_and_returns_picks(client, isolated_output, monkeypatch):
    """Refresh-all replaces candidates AND re-runs the AI picker — the prior
    selection points at rows that may have been vanished/rewritten, so leaving
    it stale is a foot-gun. Targeted refresh-all (any non-empty indices) gets
    the same treatment as initial-generate."""
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset, mechanic_count=3)

    # Tool-aware stub: generation returns the canned 6-mechanic array; every
    # council reviewer passes OK (so no synth runs and drafts are accepted
    # unchanged); the picker returns a fixed 1-based selection mapping to
    # 0-based picks [0, 2, 4].
    def stub(*args, **kwargs):
        schema = kwargs.get("tool_schema") or (args[2] if len(args) >= 3 else {})
        name = (schema or {}).get("name", "")
        if name == "submit_mechanic_review":
            return {
                "result": {"verdict": "OK", "issues": []},
                "input_tokens": 0,
                "output_tokens": 0,
            }
        if name == "select_best_mechanics":
            return {
                "result": {
                    "selections": [
                        {"candidate_number": 1, "reason": "a"},
                        {"candidate_number": 3, "reason": "b"},
                        {"candidate_number": 5, "reason": "c"},
                    ],
                    "overall_rationale": "balanced",
                },
                "input_tokens": 1,
                "output_tokens": 1,
            }
        # generation tool
        return {
            "result": {"mechanics": [_make_candidate(f"M{i}") for i in range(6)]},
            "input_tokens": 1,
            "output_tokens": 2,
        }

    monkeypatch.setattr(mg, "generate_with_tool", stub)

    candidates = [_make_candidate(f"User{i}") for i in range(6)]
    resp = client.post(
        "/api/wizard/mechanics/refresh-all",
        json={"indices": [0, 3], "candidates": candidates},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Picker response surfaces; client uses these to pre-select.
    assert data["picks"] == [0, 2, 4]
    assert data["overall_rationale"] == "balanced"
    assert [s["name"] for s in data["selections"]] == ["M0", "User2", "User4"]
    # Refreshed slots are the new AI mechanics; untouched stays.
    assert data["candidates"][0]["name"] == "M0"
    assert data["candidates"][1]["name"] == "User1"
    # approved.json + pick-rationale.json persisted (was a gap on targeted
    # refresh — only initial-generate used to persist).
    mech_dir = asset / "mechanics"
    approved = json.loads((mech_dir / "approved.json").read_text(encoding="utf-8"))
    assert [a["name"] for a in approved] == ["M0", "User2", "User4"]
    rationale = json.loads((mech_dir / "pick-rationale.json").read_text(encoding="utf-8"))
    assert rationale["source"] == "ai"
    assert rationale["overall_rationale"] == "balanced"


def test_refresh_all_400_when_indices_empty(client, isolated_output, monkeypatch):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _stub_llm(monkeypatch)
    resp = client.post(
        "/api/wizard/mechanics/refresh-all",
        json={"indices": [], "candidates": [_make_candidate("X")]},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/wizard/mechanics/save
# ---------------------------------------------------------------------------


def test_save_writes_approved_and_sidecars(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset, mechanic_count=2)
    candidates = [_make_candidate(f"M{i}") for i in range(6)]

    resp = client.post(
        "/api/wizard/mechanics/save",
        json={"picks": [0, 4], "candidates": candidates},
    )
    assert resp.status_code == 200
    data = resp.json()
    # The stage after mechanics is archetypes (not skeleton — archetypes
    # + visual_refs were inserted between them).
    assert data["navigate_to"] == "/pipeline/archetypes"
    assert len(data["approved"]) == 2
    assert data["approved"][0]["name"] == "M0"
    assert data["approved"][1]["name"] == "M4"
    # Sidecars all written.
    mech_dir = asset / "mechanics"
    approved = json.loads((mech_dir / "approved.json").read_text(encoding="utf-8"))
    assert len(approved) == 2
    assert approved[0]["name"] == "M0"
    assert "design_notes" in approved[0]
    assert "design_rationale" not in approved[0]
    # example_cards now propagate so card-gen can use them as concrete
    # reference designs (fixture sets it to []; the field rides through).
    assert "example_cards" in approved[0]
    assert "rarity_range" in approved[0]
    pq = json.loads((mech_dir / "pointed-questions.json").read_text(encoding="utf-8"))
    by_id = {q["id"]: q for q in pq}
    # mechanic_names placeholder substituted with "M0, M4".
    assert "M0, M4" in by_id["reminder_text"]["question"]
    assert "M0, M4" in by_id["keyword_collision"]["question"]
    ev = json.loads((mech_dir / "evergreen-keywords.json").read_text(encoding="utf-8"))
    assert set(ev) == {"W", "U", "B", "R", "G"}
    ft = json.loads((mech_dir / "functional-tags.json").read_text(encoding="utf-8"))
    assert ft == {}
    # candidates.json is the snapshot of edits.
    snap = json.loads((mech_dir / "candidates.json").read_text(encoding="utf-8"))
    assert len(snap) == 6


def test_save_400_when_picks_count_mismatches(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset, mechanic_count=3)
    candidates = [_make_candidate(f"M{i}") for i in range(6)]
    resp = client.post(
        "/api/wizard/mechanics/save",
        json={"picks": [0, 1], "candidates": candidates},
    )
    assert resp.status_code == 400
    assert "Expected exactly 3" in resp.json()["error"]


def test_save_400_when_picks_duplicate(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset, mechanic_count=2)
    candidates = [_make_candidate(f"M{i}") for i in range(6)]
    resp = client.post(
        "/api/wizard/mechanics/save",
        json={"picks": [0, 0], "candidates": candidates},
    )
    assert resp.status_code == 400
    assert "unique" in resp.json()["error"]


def test_save_writes_pick_rationale_marked_user(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset, mechanic_count=2)
    candidates = [_make_candidate(f"M{i}") for i in range(6)]
    resp = client.post(
        "/api/wizard/mechanics/save",
        json={"picks": [1, 3], "candidates": candidates},
    )
    assert resp.status_code == 200
    rationale = json.loads(
        (asset / "mechanics" / "pick-rationale.json").read_text(encoding="utf-8")
    )
    assert rationale["source"] == "user"
    assert [s["name"] for s in rationale["selections"]] == ["M1", "M3"]


# ---------------------------------------------------------------------------
# POST /api/wizard/mechanics/pick (AI picker)
# ---------------------------------------------------------------------------


def _stub_pick(monkeypatch, candidate_numbers: list[int]) -> None:
    """Stub ``generate_with_tool`` to return a fixed AI pick selection."""

    def stub(*args, **kwargs):
        return {
            "result": {
                "selections": [
                    {"candidate_number": n, "reason": f"reason {n}"} for n in candidate_numbers
                ],
                "overall_rationale": "good spread",
            },
            "input_tokens": 3,
            "output_tokens": 4,
        }

    monkeypatch.setattr(mg, "generate_with_tool", stub)


def test_pick_writes_approved_and_returns_picks(client, isolated_output, monkeypatch):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset, mechanic_count=3)
    _stub_pick(monkeypatch, [2, 4, 6])  # 1-based
    candidates = [_make_candidate(f"M{i}") for i in range(6)]

    resp = client.post("/api/wizard/mechanics/pick", json={"candidates": candidates})
    assert resp.status_code == 200
    data = resp.json()
    assert data["picks"] == [1, 3, 5]  # 0-based
    assert data["overall_rationale"] == "good spread"
    assert [a["name"] for a in data["approved"]] == ["M1", "M3", "M5"]
    # approved.json + AI rationale persisted.
    mech_dir = asset / "mechanics"
    approved = json.loads((mech_dir / "approved.json").read_text(encoding="utf-8"))
    assert [a["name"] for a in approved] == ["M1", "M3", "M5"]
    rationale = json.loads((mech_dir / "pick-rationale.json").read_text(encoding="utf-8"))
    assert rationale["source"] == "ai"


def test_pick_400_when_no_candidates(client, isolated_output, monkeypatch):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _stub_pick(monkeypatch, [1, 2, 3])
    resp = client.post("/api/wizard/mechanics/pick", json={"candidates": []})
    assert resp.status_code == 400


def test_pick_409_when_ai_busy(client, isolated_output, monkeypatch):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _stub_pick(monkeypatch, [1, 2, 3])
    candidates = [_make_candidate(f"M{i}") for i in range(6)]
    with ai_lock.hold("Other action") as acquired:
        assert acquired
        resp = client.post("/api/wizard/mechanics/pick", json={"candidates": candidates})
        assert resp.status_code == 409
        assert resp.json()["running_action"] == "Other action"


def test_state_surfaces_pick_rationale(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    mech_dir = asset / "mechanics"
    mech_dir.mkdir()
    (mech_dir / "candidates.json").write_text(
        json.dumps([_make_candidate(f"C{i}") for i in range(6)]), encoding="utf-8"
    )
    (mech_dir / "pick-rationale.json").write_text(
        json.dumps({"source": "ai", "overall_rationale": "balanced", "selections": []}),
        encoding="utf-8",
    )
    data = client.get("/api/wizard/mechanics/state").json()
    assert data["pick_rationale"]["source"] == "ai"
    assert data["pick_rationale"]["overall_rationale"] == "balanced"


# ---------------------------------------------------------------------------
# Refresh-recovery auto-resume (BUG A)
#
# When the initial engine run fails the mechanics floor check (overall FAILED),
# a full refresh / re-pick writes a valid selection + the guarded_ai heal demotes
# FAILED→PAUSED. The endpoint then auto-resumes the pipeline IFF mechanics is
# effective-AUTO (no live break-point) — matching how a normal run auto-advances
# an auto stage. A REVIEW break-point leaves it paused for Save & Continue.
# ``_resume_paused_engine`` is stubbed so the real engine never spawns; we only
# assert the endpoint's resume *decision*.
# ---------------------------------------------------------------------------


def _full_gen_stub(monkeypatch) -> None:
    """Tool-aware stub: generation → 6 mechanics; council reviewers OK; picker
    selects candidates 1/3/5 (0-based 0/2/4). The ``select_best_mechanics`` arm is
    needed because ``refresh-all`` re-runs the AI picker internally after it
    regenerates candidates."""

    def stub(*args, **kwargs):
        schema = kwargs.get("tool_schema") or (args[2] if len(args) >= 3 else {})
        name = (schema or {}).get("name", "")
        if name == "submit_mechanic_review":
            return {
                "result": {"verdict": "OK", "issues": []},
                "input_tokens": 0,
                "output_tokens": 0,
            }
        if name == "select_best_mechanics":
            return {
                "result": {
                    "selections": [
                        {"candidate_number": 1, "reason": "a"},
                        {"candidate_number": 3, "reason": "b"},
                        {"candidate_number": 5, "reason": "c"},
                    ],
                    "overall_rationale": "balanced",
                },
                "input_tokens": 1,
                "output_tokens": 1,
            }
        return {
            "result": {"mechanics": [_make_candidate(f"M{i}") for i in range(6)]},
            "input_tokens": 1,
            "output_tokens": 2,
        }

    monkeypatch.setattr(mg, "generate_with_tool", stub)


def _seed_failed_mechanics(*, break_points: dict[str, str]) -> None:
    """Seed a FAILED pipeline (mechanics FAILED) + re-pin the project's break_points."""
    proj = active_project.read_active_project()
    assert proj is not None
    new = proj.settings.model_copy(update={"break_points": break_points})
    active_project.write_active_project(active_project.ProjectState(set_code="TST", settings=new))
    state = create_pipeline_state(PipelineConfig(set_code="TST", set_name="Brass Sky", set_size=60))
    state.overall_status = PipelineStatus.FAILED
    mech = next(s for s in state.stages if s.stage_id == "mechanics")
    mech.status = StageStatus.FAILED
    mech.progress.error_message = "produced only 1 valid candidate(s); need at least 3"
    state.current_instance_id = mech.instance_id
    save_state(state)


def _capture_resume(monkeypatch) -> list[int]:
    calls: list[int] = []

    def _fake_resume() -> None:
        calls.append(1)
        return None

    monkeypatch.setattr(pipeline_server, "_resume_paused_engine", _fake_resume)
    return calls


def test_refresh_all_auto_resumes_recovered_auto_mechanics(client, isolated_output, monkeypatch):
    """Initial-generate that recovers a FAILED, break-point-off mechanics stage
    auto-resumes the pipeline."""
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset, mechanic_count=3)
    _seed_failed_mechanics(break_points={"mechanics": "auto"})
    _full_gen_stub(monkeypatch)
    resumes = _capture_resume(monkeypatch)

    resp = client.post("/api/wizard/mechanics/refresh-all", json={"indices": [], "candidates": []})
    assert resp.status_code == 200
    # Heal recovered the stage and the endpoint kicked off the resume.
    assert len(resumes) == 1
    reloaded = pipeline_server.load_state()
    assert reloaded is not None
    assert reloaded.overall_status == PipelineStatus.PAUSED


def test_refresh_all_keeps_paused_when_review_break_point(client, isolated_output, monkeypatch):
    """A live "Stop after this step" on mechanics keeps the recovered stage paused
    for Save & Continue — no surprise auto-resume."""
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset, mechanic_count=3)
    _seed_failed_mechanics(break_points={"mechanics": "review"})
    _full_gen_stub(monkeypatch)
    resumes = _capture_resume(monkeypatch)

    resp = client.post("/api/wizard/mechanics/refresh-all", json={"indices": [], "candidates": []})
    assert resp.status_code == 200
    assert resumes == []  # paused for review, not auto-resumed
    reloaded = pipeline_server.load_state()
    assert reloaded is not None
    assert reloaded.overall_status == PipelineStatus.PAUSED  # healed, just not resumed


def test_pick_auto_resumes_recovered_auto_mechanics(client, isolated_output, monkeypatch):
    """The AI re-pick endpoint shares the recovery contract."""
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset, mechanic_count=3)
    _seed_failed_mechanics(break_points={"mechanics": "auto"})
    _stub_pick(monkeypatch, [1, 2, 3])
    resumes = _capture_resume(monkeypatch)

    candidates = [_make_candidate(f"M{i}") for i in range(6)]
    resp = client.post("/api/wizard/mechanics/pick", json={"candidates": candidates})
    assert resp.status_code == 200
    assert len(resumes) == 1
    reloaded = pipeline_server.load_state()
    assert reloaded is not None
    assert reloaded.overall_status == PipelineStatus.PAUSED  # heal ran before resume


def test_refresh_all_no_resume_when_not_previously_failed(client, isolated_output, monkeypatch):
    """No prior FAILED state → never auto-resume, even for an auto mechanics stage
    (a normal generate from a paused/new tab must not stampede the pipeline)."""
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset, mechanic_count=3)
    # PAUSED (not FAILED) pipeline with mechanics paused for review.
    proj = active_project.read_active_project()
    assert proj is not None
    new = proj.settings.model_copy(update={"break_points": {"mechanics": "auto"}})
    active_project.write_active_project(active_project.ProjectState(set_code="TST", settings=new))
    state = create_pipeline_state(PipelineConfig(set_code="TST", set_name="Brass Sky", set_size=60))
    state.overall_status = PipelineStatus.PAUSED
    mech = next(s for s in state.stages if s.stage_id == "mechanics")
    mech.status = StageStatus.PAUSED_FOR_REVIEW
    state.current_instance_id = mech.instance_id
    save_state(state)
    _full_gen_stub(monkeypatch)
    resumes = _capture_resume(monkeypatch)

    resp = client.post("/api/wizard/mechanics/refresh-all", json={"indices": [], "candidates": []})
    assert resp.status_code == 200
    assert resumes == []
