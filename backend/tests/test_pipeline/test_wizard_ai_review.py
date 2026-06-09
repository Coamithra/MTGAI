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


# ---------------------------------------------------------------------------
# Decision staleness across a regen (card 6a285a6b)
# ---------------------------------------------------------------------------


def _rewrite_card_body(asset: Path, cn: str, **fields) -> None:
    """Replace a card's on-disk body (simulating a card_gen regen of the slot)."""
    path = next((asset / "cards").glob(f"{cn}_*.json"))
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(fields)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_stale_approve_does_not_override_fresh_regen_flag(client, isolated_output, tmp_path):
    """A user-approved card that's later regenerated+re-flagged stops painting approved.

    The bug: the approve decision (recorded against the OLD body, keyed by collector
    number) outranked everything and painted "approved" forever even after a later
    round re-flagged the card for regen. The signature check makes it stale.
    """
    asset = tmp_path / "asset"
    _seed_project(asset)
    _write_card(asset, collector_number="W-C-02", name="Bear", oracle_text="Draw a card.")

    # User approves v1.
    assert (
        client.post(
            "/api/wizard/ai_review/approve", json={"collector_number": "W-C-02"}
        ).status_code
        == 200
    )
    by_cn = {
        t["collector_number"]: t for t in client.get("/api/wizard/ai_review/state").json()["cards"]
    }
    assert by_cn["W-C-02"]["effective"]["verdict"] == "approved"

    # A later round regenerates the slot into a new body AND re-flags it for regen.
    _rewrite_card_body(
        asset,
        "W-C-02",
        oracle_text="Draw three cards.",
        regen_reason="too strong",
        flagged_by="conformance",
    )

    tile = {
        t["collector_number"]: t for t in client.get("/api/wizard/ai_review/state").json()["cards"]
    }["W-C-02"]
    # The stale approval no longer wins; the fresh flagged state surfaces instead.
    assert tile["effective"]["verdict"] == "rejected"
    assert tile["effective"]["source"] == "ai"
    assert "too strong" in tile["effective"]["reason"]


def test_reflag_overrides_approval_even_when_body_unchanged(client, isolated_output, tmp_path):
    """A gate re-flagging an approved card (body unchanged) overrides the approval.

    The flag fields (regen_reason/flagged_by) are excluded from the signature, so a
    re-flag WITHOUT a body change isn't caught by the signature check. The approve
    endpoint clears the flag, so a flag co-existing with an approval is always a
    LATER gate re-flag — the gate's regen decision wins, not the stale green stamp.
    """
    asset = tmp_path / "asset"
    _seed_project(asset)
    _write_card(asset, collector_number="W-C-02", name="Bear", oracle_text="Draw a card.")

    assert (
        client.post(
            "/api/wizard/ai_review/approve", json={"collector_number": "W-C-02"}
        ).status_code
        == 200
    )
    # Same body, but a later gate re-flags it for regen (no oracle change).
    _rewrite_card_body(asset, "W-C-02", regen_reason="combo enabler", flagged_by="conformance")

    tile = {
        t["collector_number"]: t for t in client.get("/api/wizard/ai_review/state").json()["cards"]
    }["W-C-02"]
    assert tile["effective"]["verdict"] == "rejected"
    assert tile["effective"]["source"] == "ai"
    assert "combo enabler" in tile["effective"]["reason"]


def test_stale_reject_does_not_override_fresh_clean_card(client, isolated_output, tmp_path):
    """A user-rejected card that's regenerated into a fresh OK card stops painting rejected."""
    asset = tmp_path / "asset"
    _seed_project(asset)
    _write_card(asset, collector_number="W-C-02", name="Bear", oracle_text="Bad.", slot_id="W-C-02")

    # User rejects v1 (flags for regen + records a rejected decision).
    assert (
        client.post(
            "/api/wizard/ai_review/regenerate", json={"collector_number": "W-C-02"}
        ).status_code
        == 200
    )

    # card_gen regenerates the slot into a fresh, unflagged body.
    _rewrite_card_body(asset, "W-C-02", oracle_text="Good.", regen_reason=None, flagged_by=None)
    _write_review(asset, "W-C-02", "OK")

    tile = {
        t["collector_number"]: t for t in client.get("/api/wizard/ai_review/state").json()["cards"]
    }["W-C-02"]
    # The stale rejection no longer wins; the fresh AI OK verdict surfaces.
    assert tile["effective"]["verdict"] == "approved"
    assert tile["effective"]["source"] == "ai"


def test_decision_on_unchanged_card_still_applies(client, isolated_output, tmp_path):
    """A decision whose card body is unchanged keeps its absolute precedence."""
    asset = tmp_path / "asset"
    _seed_project(asset)
    # A reviewed-REVISE card the user nonetheless approves; nothing regenerates it.
    _write_card(asset, collector_number="W-C-02", name="Bear", oracle_text="Draw a card.")
    _write_review(
        asset,
        "W-C-02",
        "REVISE",
        issues=[{"severity": "FAIL", "category": "balance", "description": "above rate"}],
    )
    assert (
        client.post(
            "/api/wizard/ai_review/approve", json={"collector_number": "W-C-02"}
        ).status_code
        == 200
    )

    tile = {
        t["collector_number"]: t for t in client.get("/api/wizard/ai_review/state").json()["cards"]
    }["W-C-02"]
    # Body unchanged -> the user's approval still overrides the AI REVISE.
    assert tile["effective"]["verdict"] == "approved"
    assert tile["effective"]["source"] == "user"


# ---------------------------------------------------------------------------
# Concurrency guard (card 6a285a13): approve/regenerate/revise must refuse while
# the AI lock is held (run_ai_review running) or an extraction is in flight, so
# they can never mutate the live pool / overwrite the tip snapshot mid-run.
# ---------------------------------------------------------------------------


def _card_disk_state(asset: Path, cn: str) -> tuple[str, dict | None]:
    """The card file's raw text + the user-decisions entry — to assert no mutation."""
    from mtgai.review.ai_review import load_decisions

    path = next((asset / "cards").glob(f"{cn}_*.json"))
    return path.read_text(encoding="utf-8"), load_decisions(asset).get(cn)


@pytest.mark.parametrize(
    ("endpoint", "action"),
    [
        ("/api/wizard/ai_review/approve", "approval"),
        ("/api/wizard/ai_review/regenerate", "regeneration"),
        ("/api/wizard/ai_review/revise", "revision"),
    ],
)
def test_mutating_endpoint_409_while_ai_lock_held(
    client, isolated_output, tmp_path, endpoint, action
):
    """With the AI lock held (run_ai_review running), the endpoint 409s and changes nothing."""
    asset = tmp_path / "asset"
    _seed_project(asset)
    _write_card(
        asset,
        collector_number="W-C-02",
        name="Bear",
        oracle_text="Draw a card.",
        slot_id="W-C-02",
    )
    before = _card_disk_state(asset, "W-C-02")

    run_id = ai_lock.try_acquire("AI design review")
    assert run_id is not None  # the lock is now held, simulating a running review
    try:
        body = {"collector_number": "W-C-02"}
        if "revise" in endpoint:
            body["instructions"] = "Make it weaker."
        resp = client.post(endpoint, json=body)
    finally:
        ai_lock.release()

    assert resp.status_code == 409
    # The live card file + the decisions sidecar are byte-for-byte untouched.
    assert _card_disk_state(asset, "W-C-02") == before
    assert not (asset / "history").exists()  # no tip snapshot was written


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/wizard/ai_review/approve",
        "/api/wizard/ai_review/regenerate",
        "/api/wizard/ai_review/revise",
    ],
)
def test_mutating_endpoint_409_while_extraction_running(
    client, isolated_output, tmp_path, endpoint
):
    """A running theme extraction also blocks these endpoints (no concurrent writer)."""
    asset = tmp_path / "asset"
    _seed_project(asset)
    _write_card(asset, collector_number="W-C-02", name="Bear", oracle_text="Draw a card.")
    before = _card_disk_state(asset, "W-C-02")

    extraction_run.start_run("upload-xyz")
    assert extraction_run.current().status == "running"

    body = {"collector_number": "W-C-02"}
    if "revise" in endpoint:
        body["instructions"] = "Make it weaker."
    resp = client.post(endpoint, json=body)

    assert resp.status_code == 409
    assert _card_disk_state(asset, "W-C-02") == before


def test_approve_works_once_lock_released(client, isolated_output, tmp_path):
    """Sanity: the guard only blocks while busy — an idle approve still succeeds."""
    asset = tmp_path / "asset"
    _seed_project(asset)
    _write_card(
        asset,
        collector_number="W-C-02",
        name="Bear",
        regen_reason="too strong",
        flagged_by="ai_review",
    )

    run_id = ai_lock.try_acquire("AI design review")
    assert run_id is not None
    busy = client.post("/api/wizard/ai_review/approve", json={"collector_number": "W-C-02"})
    assert busy.status_code == 409
    ai_lock.release()

    resp = client.post("/api/wizard/ai_review/approve", json={"collector_number": "W-C-02"})
    assert resp.status_code == 200
    assert resp.json()["tile"]["effective"]["verdict"] == "approved"
