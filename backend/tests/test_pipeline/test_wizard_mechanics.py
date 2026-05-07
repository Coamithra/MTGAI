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
from mtgai.review.server import app
from mtgai.runtime import active_project, ai_lock, extraction_run
from mtgai.settings import model_settings as ms


@pytest.fixture(autouse=True)
def _reset(isolated_output):
    ai_lock.reset_for_tests()
    extraction_run.reset()
    yield
    ai_lock.reset_for_tests()
    extraction_run.reset()


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
        "distribution": {"common": 2, "uncommon": 1, "rare": 1, "mythic": 0},
    }


def _stub_llm(monkeypatch) -> None:
    """Make ``generate_with_tool`` a no-LLM stub returning 6 candidates."""

    def stub(*args, **kwargs):
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
    assert data["navigate_to"] == "/pipeline/skeleton"
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
    assert "example_cards" not in approved[0]
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
