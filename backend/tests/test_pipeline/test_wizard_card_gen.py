"""HTTP-level tests for the Card Generation wizard endpoints.

Pin the FastAPI contract for ``GET /api/wizard/card_gen/state``: the tile shape
read from the card-gen-owned JSONs in ``<asset>/cards/`` (everything except the
Lands tab's ``L-*`` basics/dual), the empty-before-run case, the
no-active-project 409, and that lands-stage cards are excluded.

Also pin ``POST /api/wizard/card_gen/refresh``: the tab's manual re-roll
regenerates the set from scratch under the AI lock — it wipes the prior card-gen
cards + ``generation_progress.json`` (but keeps the ``L-*`` lands), runs
``generate_set``, and returns the freshly-written cards (200); 400 without a
skeleton; 409 when the AI lock is held / no project is open.
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


def _write_card(asset_dir: Path, filename: str, **fields) -> Path:
    cards = asset_dir / "cards"
    cards.mkdir(parents=True, exist_ok=True)
    path = cards / filename
    path.write_text(json.dumps(fields), encoding="utf-8")
    return path


def _write_skeleton(asset: Path) -> None:
    (asset / "skeleton.json").write_text(json.dumps({"slots": []}), encoding="utf-8")


# ---------------------------------------------------------------------------
# GET /api/wizard/card_gen/state
# ---------------------------------------------------------------------------


def test_state_empty_before_run(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    data = client.get("/api/wizard/card_gen/state").json()
    assert data["has_content"] is False
    assert data["cards"] == []
    assert data["stage_status"] == "pending"
    assert data["set_params"]["set_name"] == "Brass Sky"


def test_state_returns_card_gen_cards(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_card(
        asset,
        "001_brass_sentinel.json",
        collector_number="001",
        name="Brass Sentinel",
        mana_cost="{2}{W}",
        type_line="Creature — Construct",
        oracle_text="Vigilance",
        rarity="uncommon",
        power="2",
        toughness="4",
        colors=["W"],
        status="draft",
    )
    data = client.get("/api/wizard/card_gen/state").json()
    assert data["has_content"] is True
    by_cn = {c["collector_number"]: c for c in data["cards"]}
    assert set(by_cn) == {"001"}
    card = by_cn["001"]
    assert card["name"] == "Brass Sentinel"
    assert card["rarity"] == "uncommon"
    assert card["power"] == "2"
    assert card["colors"] == ["W"]


def test_state_excludes_lands_stage_cards(client, isolated_output):
    # The Lands tab owns the L-* basics/dual; they must not appear on the Cards
    # tab. Land *cycles* (non-L collector numbers) are card-gen-owned and DO show.
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_card(asset, "001_card.json", collector_number="001", name="A Card", rarity="common")
    _write_card(
        asset, "L-01a_plains.json", collector_number="L-01a", name="Plains", rarity="common"
    )
    _write_card(
        asset, "120_azorius_gate.json", collector_number="120", name="Azorius Gate", rarity="common"
    )
    data = client.get("/api/wizard/card_gen/state").json()
    cns = {c["collector_number"] for c in data["cards"]}
    assert cns == {"001", "120"}  # the L-* land is excluded; the cycle land stays


def test_state_409_when_no_active_project(client):
    resp = client.get("/api/wizard/card_gen/state")
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_active_project"


# ---------------------------------------------------------------------------
# POST /api/wizard/card_gen/refresh
# ---------------------------------------------------------------------------


def test_refresh_regenerates_from_scratch(client, isolated_output, monkeypatch):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)

    # Pre-existing state a from-scratch run must clear: an old card-gen card, a
    # progress file, and an L-* land that must SURVIVE the wipe.
    old_card = _write_card(
        asset, "001_old.json", collector_number="001", name="Old", rarity="common"
    )
    land = _write_card(
        asset, "L-02_island.json", collector_number="L-02", name="Island", rarity="common"
    )
    progress = asset / "generation_progress.json"
    progress.write_text(json.dumps({"filled_slots": {"001": "x"}}), encoding="utf-8")

    def stub_generate_set(*_args, **_kwargs):
        # The real generator regenerates slots; the old "001" was just wiped, so
        # write a fresh card the endpoint's re-read of /state will surface.
        _write_card(
            asset,
            "002_fresh_titan.json",
            collector_number="002",
            name="Fresh Titan",
            mana_cost="{4}{G}",
            type_line="Creature — Giant",
            oracle_text="Trample",
            rarity="rare",
            power="6",
            toughness="6",
            colors=["G"],
            status="draft",
        )
        return {"total_slots": 1, "filled": 1, "failed": 0, "cancelled": False, "summary": "ok"}

    monkeypatch.setattr("mtgai.generation.card_generator.generate_set", stub_generate_set)

    resp = client.post("/api/wizard/card_gen/refresh", json={})
    assert resp.status_code == 200
    data = resp.json()
    by_cn = {c["collector_number"]: c for c in data["cards"]}
    assert set(by_cn) == {"002"}  # fresh card present; old "001" wiped
    assert by_cn["002"]["name"] == "Fresh Titan"

    # From-scratch wipe: old card + progress gone, but the land is preserved.
    assert not old_card.exists()
    assert not progress.exists()
    assert land.exists()


def test_refresh_streams_reset_then_card_events(client, isolated_output, monkeypatch):
    """The /refresh endpoint must publish ``card_gen_reset`` *before* the run
    starts (so the tab clears its prior local list) and a ``card_gen_card``
    event per saved card (so each card pops in live). Engine path does not
    emit reset — only the manual /refresh wipes prior cards on disk."""
    from mtgai.models.card import Card
    from mtgai.models.enums import CardStatus, Color, Rarity
    from mtgai.pipeline import server as srv

    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)

    def _make_card(cn: str, name: str) -> Card:
        return Card(
            name=name,
            mana_cost="{1}{W}",
            cmc=2.0,
            type_line="Creature — Robot",
            oracle_text="Vigilance",
            rarity=Rarity.COMMON,
            colors=[Color.WHITE],
            color_identity=[Color.WHITE],
            collector_number=cn,
            set_code="TST",
            power="2",
            toughness="2",
            card_types=["Creature"],
            subtypes=["Robot"],
            status=CardStatus.DRAFT,
        )

    def stub_generate_set(*_args, **kwargs):
        cb = kwargs.get("card_saved_callback")
        if cb is not None:
            cb(_make_card("001", "Sentinel Mk I"))
            cb(_make_card("002", "Sentinel Mk II"))
        return {"total_slots": 2, "filled": 2, "failed": 0, "cancelled": False, "summary": "ok"}

    monkeypatch.setattr("mtgai.generation.card_generator.generate_set", stub_generate_set)

    # Spy on event_bus.publish to capture the emitted SSE events in order.
    published: list[tuple[str, dict]] = []
    real_publish = srv.event_bus.publish

    def spy_publish(event_type, data):
        published.append((event_type, data))
        return real_publish(event_type, data)

    monkeypatch.setattr(srv.event_bus, "publish", spy_publish)

    resp = client.post("/api/wizard/card_gen/refresh", json={})
    assert resp.status_code == 200

    # card_gen_reset must come BEFORE any card_gen_card event so the client
    # wipes its local list before the new run starts streaming in.
    by_type = [t for t, _ in published]
    first_reset = by_type.index("card_gen_reset")
    card_event_idxs = [i for i, t in enumerate(by_type) if t == "card_gen_card"]
    assert card_event_idxs, "no card_gen_card events were published"
    assert first_reset < card_event_idxs[0]

    # One card_gen_card event per saved card, in save order, each carrying the
    # tile shape the /state endpoint emits (so the merge by collector_number
    # stays a no-op when /state's response repaints the grid).
    card_payloads = [data["card"] for t, data in published if t == "card_gen_card"]
    assert [c["collector_number"] for c in card_payloads] == ["001", "002"]
    assert card_payloads[0]["name"] == "Sentinel Mk I"
    assert card_payloads[0]["rarity"] == "common"
    assert card_payloads[0]["colors"] == ["W"]
    assert card_payloads[0]["power"] == "2"


def test_refresh_400_when_no_skeleton(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)  # no skeleton.json written
    resp = client.post("/api/wizard/card_gen/refresh", json={})
    assert resp.status_code == 400


def test_refresh_409_when_ai_busy(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)
    with ai_lock.hold("Other action") as acquired:
        assert acquired
        resp = client.post("/api/wizard/card_gen/refresh", json={})
        assert resp.status_code == 409
        assert resp.json()["running_action"] == "Other action"


def test_refresh_409_when_no_active_project(client):
    resp = client.post("/api/wizard/card_gen/refresh", json={})
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_active_project"


def test_refresh_heals_stuck_failed_card_gen(client, isolated_output, monkeypatch):
    """A successful from-scratch refresh clears a stuck FAILED card_gen stage
    (left by a cancel / interrupt) so the failure modal stops re-firing."""
    from mtgai.pipeline import server as srv
    from mtgai.pipeline.models import (
        PipelineConfig,
        PipelineState,
        PipelineStatus,
        StageStatus,
        create_pipeline_state,
    )

    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)
    # Force disk-backed state (no in-memory engine attached in this process).
    monkeypatch.setattr(srv, "_engine", None)

    state = create_pipeline_state(PipelineConfig(set_code="TST", set_name="T", set_size=60))
    cg = next(s for s in state.stages if s.stage_id == "card_gen")
    cg.status = StageStatus.FAILED
    cg.progress.error_message = "Interrupted — server restart"
    state.overall_status = PipelineStatus.FAILED
    state.current_stage_id = "card_gen"
    (asset / "pipeline-state.json").write_text(
        json.dumps(state.model_dump(mode="json"), indent=2, default=str), encoding="utf-8"
    )

    def stub_generate_set(*_args, **_kwargs):
        _write_card(asset, "002_fresh.json", collector_number="002", name="Fresh", rarity="rare")
        return {"total_slots": 1, "filled": 1, "failed": 0, "cancelled": False, "summary": "ok"}

    monkeypatch.setattr("mtgai.generation.card_generator.generate_set", stub_generate_set)

    resp = client.post("/api/wizard/card_gen/refresh", json={})
    assert resp.status_code == 200

    reloaded = PipelineState.model_validate_json(
        (asset / "pipeline-state.json").read_text(encoding="utf-8")
    )
    healed = next(s for s in reloaded.stages if s.stage_id == "card_gen")
    assert healed.status == StageStatus.PAUSED_FOR_REVIEW  # no longer FAILED
    assert healed.progress.error_message is None
    assert reloaded.overall_status == PipelineStatus.PAUSED  # no longer FAILED


def test_refresh_cancelled_does_not_heal(client, isolated_output, monkeypatch):
    """If the refresh run is cancelled, a FAILED card_gen is left as-is (the user
    stopped it — don't paper over the failure)."""
    from mtgai.pipeline import server as srv
    from mtgai.pipeline.models import (
        PipelineConfig,
        PipelineState,
        PipelineStatus,
        StageStatus,
        create_pipeline_state,
    )

    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)
    monkeypatch.setattr(srv, "_engine", None)

    state = create_pipeline_state(PipelineConfig(set_code="TST", set_name="T", set_size=60))
    cg = next(s for s in state.stages if s.stage_id == "card_gen")
    cg.status = StageStatus.FAILED
    state.overall_status = PipelineStatus.FAILED
    (asset / "pipeline-state.json").write_text(
        json.dumps(state.model_dump(mode="json"), indent=2, default=str), encoding="utf-8"
    )

    def stub_cancelled(*_args, **_kwargs):
        return {"total_slots": 1, "filled": 0, "failed": 0, "cancelled": True, "summary": "x"}

    monkeypatch.setattr("mtgai.generation.card_generator.generate_set", stub_cancelled)

    assert client.post("/api/wizard/card_gen/refresh", json={}).status_code == 200
    reloaded = PipelineState.model_validate_json(
        (asset / "pipeline-state.json").read_text(encoding="utf-8")
    )
    healed = next(s for s in reloaded.stages if s.stage_id == "card_gen")
    assert healed.status == StageStatus.FAILED  # left failed — cancel doesn't heal
