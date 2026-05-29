"""HTTP-level tests for the Lands wizard endpoints.

Pin the FastAPI contract for ``GET /api/wizard/lands/state``: the tile shape read
from the lands-stage card JSONs in ``<asset>/cards/`` (per-type basic alternates
``L-01a``..``L-05x`` plus the optional investigated dual ``L-06``, each carrying
its art brief in ``design_notes``), the empty-before-run case, the no-active-project
409, and that land *cycle* cards (owned by card-gen, non-``L-`` collector numbers)
are excluded. This is the durable source the Lands tab bootstraps from after a
reload — its live SSE tiles are ephemeral.

Also pin ``POST /api/wizard/lands/refresh``: the tab's manual re-roll re-runs the
lands stage under the AI lock and returns the freshly-written cards (200), 400
without a skeleton, and 409 when the AI lock is held / no project is open.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
    asset_dir.mkdir(parents=True, exist_ok=True)
    settings = ms.ModelSettings(
        asset_folder=str(asset_dir),
        set_params=ms.SetParams(set_name="Brass Sky", set_size=60, mechanic_count=3),
    )
    active_project.write_active_project(
        active_project.ProjectState(set_code="TST", settings=settings)
    )


def _write_card(asset_dir: Path, filename: str, **fields) -> None:
    cards = asset_dir / "cards"
    cards.mkdir(parents=True, exist_ok=True)
    (cards / filename).write_text(json.dumps(fields), encoding="utf-8")


def test_state_empty_before_run(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    data = client.get("/api/wizard/lands/state").json()
    assert data["has_content"] is False
    assert data["lands"] == []
    assert data["stage_status"] == "pending"


def test_state_returns_basics_and_dual(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_card(
        asset,
        "L-01a_plains.json",
        collector_number="L-01a",
        name="Plains",
        type_line="Basic Land — Plains",
        rarity="common",
        oracle_text="",
        flavor_text="Flat fields.",
        design_notes="Alternate basic land art — sunlit terraced fields under a brass sky",
    )
    _write_card(
        asset,
        "L-06_energon_nexus.json",
        collector_number="L-06",
        name="Energon Nexus",
        type_line="Land",
        rarity="rare",
        oracle_text="{T}: Add {W} or {U}.",
        flavor_text="Where two currents meet.",
    )
    data = client.get("/api/wizard/lands/state").json()
    assert data["has_content"] is True
    by_cn = {land["collector_number"]: land for land in data["lands"]}
    assert set(by_cn) == {"L-01a", "L-06"}
    assert by_cn["L-06"]["rarity"] == "rare"
    assert by_cn["L-06"]["name"] == "Energon Nexus"
    assert by_cn["L-01a"]["type_line"].startswith("Basic Land")
    # The per-alternate art brief is surfaced so variant printings are distinct.
    assert "terraced fields" in by_cn["L-01a"]["design_notes"]


def test_state_excludes_land_cycle_cards(client, isolated_output):
    # Card-gen owns land cycles now; a guildgate (Land type, non-L collector
    # number) belongs on the Cards tab, not the Lands tab.
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_card(
        asset,
        "L-02_island.json",
        collector_number="L-02",
        name="Island",
        type_line="Basic Land — Island",
        rarity="common",
    )
    _write_card(
        asset,
        "120_azorius_gate.json",
        collector_number="120",
        name="Azorius Gate",
        type_line="Land",
        rarity="common",
    )
    data = client.get("/api/wizard/lands/state").json()
    cns = {land["collector_number"] for land in data["lands"]}
    assert cns == {"L-02"}  # the guildgate cycle land is excluded


def test_state_409_when_no_active_project(client):
    resp = client.get("/api/wizard/lands/state")
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_active_project"


# ---------------------------------------------------------------------------
# POST /api/wizard/lands/refresh
# ---------------------------------------------------------------------------


def _write_skeleton(asset: Path) -> None:
    (asset / "skeleton.json").write_text(json.dumps({"slots": []}), encoding="utf-8")


def test_refresh_reruns_and_returns_fresh_cards(client, isolated_output, monkeypatch):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)

    # Stub the generator: write one alternate basic the way the real stage does,
    # so the endpoint's re-read of the L-* cards has something to surface.
    def stub_generate_lands(*_args, **_kwargs):
        _write_card(
            asset,
            "L-04a_mountain.json",
            collector_number="L-04a",
            name="Mountain",
            type_line="Basic Land — Mountain",
            rarity="common",
            design_notes="Alternate basic land art — a smoking caldera ringed with obsidian",
        )
        return {"total_cards": 1, "cost_usd": 0.0}

    monkeypatch.setattr("mtgai.generation.land_generator.generate_lands", stub_generate_lands)

    resp = client.post("/api/wizard/lands/refresh", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_content"] is True
    by_cn = {land["collector_number"]: land for land in data["lands"]}
    assert "L-04a" in by_cn
    assert "smoking caldera" in by_cn["L-04a"]["design_notes"]


def test_refresh_500_when_generator_raises(client, isolated_output, monkeypatch):
    """A worker exception is rendered as 500 ``{"error": ...}`` by the guarded_ai
    AIActionError handler — the flat shape ``W.reportError`` reads, not FastAPI's
    default ``{"detail": ...}``. Pins the guard's try/500 ownership + that the
    lock is released after a failure."""
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)

    def boom(*_args, **_kwargs):
        raise RuntimeError("generator exploded")

    monkeypatch.setattr("mtgai.generation.land_generator.generate_lands", boom)
    resp = client.post("/api/wizard/lands/refresh", json={})
    assert resp.status_code == 500
    assert "generator exploded" in resp.json()["error"]
    # The guard released the lock on the failure — a follow-up isn't wrongly 409'd.
    assert ai_lock.is_running() is False


def test_refresh_400_when_no_skeleton(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)  # no skeleton.json written
    resp = client.post("/api/wizard/lands/refresh", json={})
    assert resp.status_code == 400


def test_refresh_409_when_ai_busy(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)
    with ai_lock.hold("Other action") as acquired:
        assert acquired
        resp = client.post("/api/wizard/lands/refresh", json={})
        assert resp.status_code == 409
        assert resp.json()["running_action"] == "Other action"


def test_refresh_409_when_no_active_project(client):
    resp = client.post("/api/wizard/lands/refresh", json={})
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_active_project"
