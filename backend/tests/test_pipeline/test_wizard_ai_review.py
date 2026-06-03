"""HTTP-level tests for the AI Design Review wizard endpoints.

Pin the FastAPI contract for ``GET /api/wizard/ai_review/state`` (the per-card
tile shape merging the card pool + persisted reviews + the user-decisions
sidecar, with the effective approved/rejected/pending stamp resolved), the
no-LLM manual actions (``/approve`` writes a decision + clears the regen flag;
``/regenerate`` flags the slot back to card_gen), and the validation / 409 paths.

The ``/revise`` endpoint makes a real LLM call, so it isn't HTTP-tested here —
``revise_card_in_place`` is unit-tested in ``test_review/test_ai_review_ui.py``.
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


def _write_card(asset_dir: Path, **fields) -> Path:
    cards = asset_dir / "cards"
    cards.mkdir(parents=True, exist_ok=True)
    cn = fields["collector_number"]
    path = cards / f"{cn}_{fields.get('name', 'card').replace(' ', '_')}.json"
    base = {
        "name": "Card",
        "mana_cost": "{1}",
        "type_line": "Creature — Bear",
        "oracle_text": "",
        "rarity": "common",
        "colors": [],
        "status": "draft",
    }
    base.update(fields)
    path.write_text(json.dumps(base), encoding="utf-8")
    return path


def _write_review(asset_dir: Path, collector_number: str, verdict: str, issues=None) -> None:
    reviews = asset_dir / "reviews"
    reviews.mkdir(parents=True, exist_ok=True)
    payload = {
        "collector_number": collector_number,
        "card_name": "Card",
        "rarity": "common",
        "review_tier": "single",
        "original_card": {},
        "final_verdict": verdict,
        "final_issues": issues or [],
        "card_was_changed": False,
    }
    (reviews / f"{collector_number}.json").write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# GET /api/wizard/ai_review/state
# ---------------------------------------------------------------------------


def test_state_no_project_409(client):
    active_project.clear_active_project()
    resp = client.get("/api/wizard/ai_review/state")
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_active_project"


def test_state_empty_before_run(client, isolated_output, tmp_path):
    _seed_project(tmp_path / "asset")
    resp = client.get("/api/wizard/ai_review/state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_content"] is False
    assert body["cards"] == []
    assert body["summary"]["total"] == 0


def test_state_merges_cards_reviews_and_effective_stamp(client, isolated_output, tmp_path):
    asset = tmp_path / "asset"
    _seed_project(asset)
    # An OK card (approved), a reviewed-REVISE card with an issue (rejected), and
    # an unreviewed card (pending). Lands are excluded by the loader.
    _write_card(asset, collector_number="W-C-01", name="Good Bear", rarity="common")
    _write_card(asset, collector_number="W-C-02", name="Bad Bear", rarity="common")
    _write_card(asset, collector_number="W-C-03", name="New Bear", rarity="common")
    _write_card(asset, collector_number="L-01", name="Plains", type_line="Basic Land — Plains")
    _write_review(asset, "W-C-01", "OK")
    _write_review(
        asset,
        "W-C-02",
        "REVISE",
        issues=[{"severity": "FAIL", "category": "balance", "description": "above rate"}],
    )

    resp = client.get("/api/wizard/ai_review/state")
    assert resp.status_code == 200
    body = resp.json()
    by_cn = {t["collector_number"]: t for t in body["cards"]}
    assert set(by_cn) == {"W-C-01", "W-C-02", "W-C-03"}  # land excluded
    assert by_cn["W-C-01"]["effective"]["verdict"] == "approved"
    assert by_cn["W-C-02"]["effective"]["verdict"] == "rejected"
    assert "above rate" in by_cn["W-C-02"]["effective"]["reason"]
    assert by_cn["W-C-03"]["effective"]["verdict"] == "pending"
    assert body["summary"] == {
        "reviewed": 2,
        "revised": 0,
        "approved": 1,
        "rejected": 1,
        "pending": 1,
        "total": 3,
    }


# ---------------------------------------------------------------------------
# POST /api/wizard/ai_review/approve
# ---------------------------------------------------------------------------


def test_approve_writes_decision_and_clears_flag(client, isolated_output, tmp_path):
    asset = tmp_path / "asset"
    _seed_project(asset)
    _write_card(
        asset,
        collector_number="W-C-02",
        name="Bad Bear",
        regen_reason="too strong",
        flagged_by="ai_review",
    )

    resp = client.post("/api/wizard/ai_review/approve", json={"collector_number": "W-C-02"})
    assert resp.status_code == 200
    tile = resp.json()["tile"]
    assert tile["effective"]["verdict"] == "approved"
    assert tile["flagged"] is False

    # The regen flag was cleared on disk.
    from mtgai.review.ai_review import load_decisions

    assert load_decisions(asset)["W-C-02"]["verdict"] == "approved"
    card_path = next((asset / "cards").glob("W-C-02_*.json"))
    saved = json.loads(card_path.read_text(encoding="utf-8"))
    assert saved.get("regen_reason") in (None, "")


def test_approve_missing_collector_number_400(client, isolated_output, tmp_path):
    _seed_project(tmp_path / "asset")
    resp = client.post("/api/wizard/ai_review/approve", json={})
    assert resp.status_code == 400


def test_approve_unknown_card_404(client, isolated_output, tmp_path):
    _seed_project(tmp_path / "asset")
    resp = client.post("/api/wizard/ai_review/approve", json={"collector_number": "ZZ-99"})
    assert resp.status_code == 404


def test_approve_does_not_prefix_collide(client, isolated_output, tmp_path):
    """``W-C-01`` must not resolve to ``W-C-011`` (filename is ``<cn>_<slug>``)."""
    asset = tmp_path / "asset"
    _seed_project(asset)
    _write_card(
        asset, collector_number="W-C-011", name="Eleven", regen_reason="x", flagged_by="ai_review"
    )

    resp = client.post("/api/wizard/ai_review/approve", json={"collector_number": "W-C-01"})
    assert resp.status_code == 404  # no W-C-01 card; must not match W-C-011


# ---------------------------------------------------------------------------
# POST /api/wizard/ai_review/regenerate
# ---------------------------------------------------------------------------


def test_regenerate_flags_card_and_records_rejection(client, isolated_output, tmp_path):
    asset = tmp_path / "asset"
    _seed_project(asset)
    _write_card(asset, collector_number="W-C-02", name="Bad Bear", slot_id="W-C-02")

    resp = client.post("/api/wizard/ai_review/regenerate", json={"collector_number": "W-C-02"})
    assert resp.status_code == 200
    tile = resp.json()["tile"]
    assert tile["flagged"] is True
    assert tile["effective"]["verdict"] == "rejected"

    card_path = next((asset / "cards").glob("W-C-02_*.json"))
    saved = json.loads(card_path.read_text(encoding="utf-8"))
    assert saved.get("flagged_by") == "ai_review"
    assert saved.get("regen_reason")


# ---------------------------------------------------------------------------
# POST /api/wizard/ai_review/revise (validation only — no LLM)
# ---------------------------------------------------------------------------


def test_revise_requires_instructions(client, isolated_output, tmp_path):
    asset = tmp_path / "asset"
    _seed_project(asset)
    _write_card(asset, collector_number="W-C-01", name="Bear")
    resp = client.post(
        "/api/wizard/ai_review/revise", json={"collector_number": "W-C-01", "instructions": "  "}
    )
    assert resp.status_code == 400
