"""HTTP-level tests for the Archetypes wizard endpoints (TC-3 UI).

Pin the FastAPI contract: payload shape, status codes, the AI-busy 409,
the preserve-on-refresh contract, and the side effects of /save
(archetypes.json clean + provenance sidecar). The underlying generator is
monkey-patched so tests don't hit a real LLM.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mtgai.generation import archetype_generator as ag
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


def _seed_project(asset_dir: Path) -> None:
    """Active project + the theme.json and approved.json the generator reads."""
    (asset_dir / "mechanics").mkdir(parents=True, exist_ok=True)
    (asset_dir / "theme.json").write_text(
        json.dumps(
            {
                "code": "TST",
                "name": "Test Set",
                "theme": "Steampunk dragons in a clockwork sky.",
                "flavor_description": "Brass cities tethered by chains.",
                "constraints": [{"text": "At least 6 artifact creatures."}],
            }
        ),
        encoding="utf-8",
    )
    (asset_dir / "mechanics" / "approved.json").write_text(
        json.dumps([{"name": "Salvage", "colors": ["W"], "complexity": 1, "reminder_text": "(x)"}]),
        encoding="utf-8",
    )
    settings = ms.ModelSettings(
        asset_folder=str(asset_dir),
        set_params=ms.SetParams(set_name="Brass Sky", set_size=120, mechanic_count=3),
    )
    active_project.write_active_project(
        active_project.ProjectState(set_code="TST", settings=settings)
    )


def _arch(pair: str, name: str, *, ai: bool = True) -> dict:
    return {
        "color_pair": pair,
        "name": name,
        "description": f"win via {pair}",
        "_ai_generated": ai,
    }


def _full_working() -> list[dict]:
    return [_arch(p, f"User {p}") for p in ag.COLOR_PAIRS]


def _stub_llm(monkeypatch) -> None:
    """Stub ``generate_with_tool`` to return all ten archetypes named by pair."""

    def stub(*args, **kwargs):
        return {
            "result": {
                "archetypes": [
                    {"color_pair": p, "name": f"AI {p}", "description": f"ai plan {p}"}
                    for p in ag.COLOR_PAIRS
                ]
            },
            "input_tokens": 1,
            "output_tokens": 2,
        }

    monkeypatch.setattr(ag, "generate_with_tool", stub)


# ---------------------------------------------------------------------------
# GET /api/wizard/archetypes/state
# ---------------------------------------------------------------------------


def test_state_returns_ten_empty_pairs_when_nothing_generated(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    data = client.get("/api/wizard/archetypes/state").json()
    assert data["has_content"] is False
    assert len(data["archetypes"]) == 10
    assert [a["color_pair"] for a in data["archetypes"]] == ag.COLOR_PAIRS
    assert all(a["name"] == "" and a["description"] == "" for a in data["archetypes"])
    assert [p["pair"] for p in data["pairs"]] == ag.COLOR_PAIRS
    assert data["set_params"]["set_size"] == 120
    assert data["stage_status"] == "pending"


def test_state_folds_provenance_into_flags(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    (asset / "archetypes.json").write_text(
        json.dumps(
            [{"color_pair": p, "name": f"N{p}", "description": "d"} for p in ag.COLOR_PAIRS]
        ),
        encoding="utf-8",
    )
    (asset / "archetypes").mkdir(exist_ok=True)
    (asset / "archetypes" / "provenance.json").write_text(
        json.dumps({"WU": "human", "WB": "ai"}), encoding="utf-8"
    )
    data = client.get("/api/wizard/archetypes/state").json()
    assert data["has_content"] is True
    by_pair = {a["color_pair"]: a for a in data["archetypes"]}
    assert by_pair["WU"]["_ai_generated"] is False  # marked human
    assert by_pair["WB"]["_ai_generated"] is True
    assert by_pair["RG"]["_ai_generated"] is True  # absent → defaults to AI


def test_state_409_when_no_active_project(client):
    resp = client.get("/api/wizard/archetypes/state")
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_active_project"


# ---------------------------------------------------------------------------
# POST /api/wizard/archetypes/refresh-card
# ---------------------------------------------------------------------------


def test_refresh_card_replaces_only_one_pair(client, isolated_output, monkeypatch):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _stub_llm(monkeypatch)
    resp = client.post(
        "/api/wizard/archetypes/refresh-card",
        json={"color_pair": "UG", "archetypes": _full_working()},
    )
    assert resp.status_code == 200
    out = {a["color_pair"]: a for a in resp.json()["archetypes"]}
    assert out["UG"]["name"] == "AI UG"
    assert out["UG"]["_ai_generated"] is True
    # Every other pair survives untouched.
    for p in ag.COLOR_PAIRS:
        if p != "UG":
            assert out[p]["name"] == f"User {p}"
    # Persisted clean (no _ai_generated) + provenance sidecar.
    on_disk = json.loads((asset / "archetypes.json").read_text())
    assert "_ai_generated" not in on_disk[0]
    prov = json.loads((asset / "archetypes" / "provenance.json").read_text())
    assert prov["UG"] == "ai"


def test_refresh_card_400_on_bad_pair(client, isolated_output, monkeypatch):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _stub_llm(monkeypatch)
    resp = client.post(
        "/api/wizard/archetypes/refresh-card",
        json={"color_pair": "ZZ", "archetypes": _full_working()},
    )
    assert resp.status_code == 400


def test_refresh_card_409_when_ai_busy(client, isolated_output, monkeypatch):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _stub_llm(monkeypatch)
    with ai_lock.hold("Other action") as acquired:
        assert acquired
        resp = client.post(
            "/api/wizard/archetypes/refresh-card",
            json={"color_pair": "WU", "archetypes": _full_working()},
        )
        assert resp.status_code == 409
        assert resp.json()["running_action"] == "Other action"


# ---------------------------------------------------------------------------
# POST /api/wizard/archetypes/refresh-all
# ---------------------------------------------------------------------------


def test_refresh_all_initial_generates_all_ten(client, isolated_output, monkeypatch):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _stub_llm(monkeypatch)
    resp = client.post(
        "/api/wizard/archetypes/refresh-all",
        json={"pairs": [], "archetypes": []},
    )
    assert resp.status_code == 200
    out = resp.json()["archetypes"]
    assert len(out) == 10
    assert all(a["name"].startswith("AI ") for a in out)
    assert all(a["_ai_generated"] for a in out)


def test_refresh_all_partial_preserves_unlisted_pairs(client, isolated_output, monkeypatch):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _stub_llm(monkeypatch)
    resp = client.post(
        "/api/wizard/archetypes/refresh-all",
        json={"pairs": ["WU", "RG"], "archetypes": _full_working()},
    )
    assert resp.status_code == 200
    out = {a["color_pair"]: a for a in resp.json()["archetypes"]}
    assert out["WU"]["name"] == "AI WU"
    assert out["RG"]["name"] == "AI RG"
    assert out["WB"]["name"] == "User WB"  # not listed → kept


def test_refresh_all_400_when_pairs_empty_but_content_exists(client, isolated_output, monkeypatch):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _stub_llm(monkeypatch)
    resp = client.post(
        "/api/wizard/archetypes/refresh-all",
        json={"pairs": [], "archetypes": _full_working()},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/wizard/archetypes/save
# ---------------------------------------------------------------------------


def test_save_writes_clean_json_and_provenance(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    working = _full_working()
    working[0]["_ai_generated"] = False  # WU hand-edited
    resp = client.post("/api/wizard/archetypes/save", json={"archetypes": working})
    assert resp.status_code == 200
    data = resp.json()
    assert data["navigate_to"] == "/pipeline/skeleton"
    on_disk = json.loads((asset / "archetypes.json").read_text())
    assert len(on_disk) == 10
    assert set(on_disk[0]) == {"color_pair", "name", "description"}  # no _ai_generated leak
    prov = json.loads((asset / "archetypes" / "provenance.json").read_text())
    assert prov["WU"] == "human"
    assert prov["WB"] == "ai"


def test_save_400_when_a_pair_is_incomplete(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    working = _full_working()
    working[3]["description"] = "   "  # WG blank intent
    resp = client.post("/api/wizard/archetypes/save", json={"archetypes": working})
    assert resp.status_code == 400
    assert "WG" in resp.json()["error"]
