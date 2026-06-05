"""HTTP-level tests for the Reprints wizard state endpoint.

Pin the FastAPI contract for ``GET /api/wizard/reprints/state``: the payload
shape (selections + reasons, pool/slot counts, target count, stage status), the
empty-before-run case, and the no-active-project 409. This is the durable source
the Reprints tab bootstraps from — the stage's live SSE tiles are ephemeral, so
without this the tab can't show what was decided after a reload.
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


def _write_skeleton(asset_dir: Path) -> None:
    """Minimal skeleton with one reprint-eligible slot (B common instant, evergreen)."""
    skeleton = {
        "config": {"name": "Test Set", "code": "TST", "set_size": 1},
        "slots": [
            {
                "slot_id": "B-C-03",
                "color": "B",
                "rarity": "common",
                "card_type": "instant",
                "cmc_target": 3,
                "mechanic_tag": "evergreen",
                "card_id": None,
            }
        ],
        "total_slots": 1,
    }
    (asset_dir / "skeleton.json").write_text(json.dumps(skeleton), encoding="utf-8")


def _write_selection(asset_dir: Path) -> None:
    selection = {
        "set_code": "TST",
        "set_size": 60,
        "target_reprint_count": 2,
        "all_candidates_considered": 167,
        "selection_timestamp": "2026-05-27T00:00:00+00:00",
        "selections": [
            {
                "slot": {
                    "slot_id": "B-C-03",
                    "color": "B",
                    "rarity": "common",
                    "card_type": "instant",
                    "role_needed": "removal_hard_kill",
                    "cmc_target": 3,
                    "mechanic_tag": "evergreen",
                },
                "candidate": {
                    "name": "Murder",
                    "mana_cost": "{1}{B}{B}",
                    "cmc": 3.0,
                    "type_line": "Instant",
                    "oracle_text": "Destroy target creature.",
                    "colors": ["B"],
                    "rarity": "common",
                    "role": "removal_hard_kill",
                },
                "reason": "Essential hard removal at common for black.",
            }
        ],
    }
    (asset_dir / "reprint_selection.json").write_text(json.dumps(selection), encoding="utf-8")


def test_state_empty_before_run(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)
    data = client.get("/api/wizard/reprints/state").json()
    assert data["has_content"] is False
    assert data["selections"] == []
    assert data["target_count"] is None
    assert data["eligible_slots"] == 1  # the one evergreen B common instant slot
    assert data["pool_size"] and data["pool_size"] > 0  # curated pool is static
    assert data["stage_status"] == "pending"


def test_state_returns_selections_and_reasons(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)
    _write_selection(asset)
    data = client.get("/api/wizard/reprints/state").json()
    assert data["has_content"] is True
    assert data["target_count"] == 2
    assert len(data["selections"]) == 1
    sel = data["selections"][0]
    assert sel["candidate"]["name"] == "Murder"
    assert sel["slot"]["slot_id"] == "B-C-03"
    assert sel["reason"].startswith("Essential hard removal")


def test_state_tolerates_missing_skeleton(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_selection(asset)  # selection exists, but no skeleton.json
    data = client.get("/api/wizard/reprints/state").json()
    assert data["has_content"] is True
    assert data["eligible_slots"] is None  # unknown without a skeleton, not 0


def test_state_409_when_no_active_project(client):
    resp = client.get("/api/wizard/reprints/state")
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_active_project"


# ---------------------------------------------------------------------------
# Knobs payload + GET /state knob fields
# ---------------------------------------------------------------------------


def test_state_includes_knob_payload(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)
    data = client.get("/api/wizard/reprints/state").json()
    assert data["knobs"]["common"] is None  # auto by default
    assert data["knobs"]["jitter_pct"] == 0.25
    assert data["provenance"]["common"] == "auto"
    assert data["rates"]["common"] == 0.030
    assert "preview_targets" in data
    assert data["slot_count"] == 1


# ---------------------------------------------------------------------------
# POST /api/wizard/reprints/knobs
# ---------------------------------------------------------------------------


def test_knobs_persist_and_clamp(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)
    resp = client.post(
        "/api/wizard/reprints/knobs",
        json={"knobs": {"common": -5, "rare": 9999, "jitter_pct": 0.4}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["knobs"]["common"] == 0  # clamped up from negative
    assert data["knobs"]["rare"] == 40  # clamped down to max
    assert data["knobs"]["jitter_pct"] == 0.4
    assert data["provenance"]["common"] == "user"
    on_disk = json.loads((asset / "reprints" / "knobs.json").read_text())
    assert on_disk["common"] == 0 and on_disk["rare"] == 40


def test_knobs_infinity_does_not_500(client, isolated_output):
    # Regression: JSON ``1e400`` parses to ``float('inf')`` server-side; the int()
    # path raised an uncaught OverflowError -> 500. It must now clamp to auto (200).
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)
    resp = client.post(
        "/api/wizard/reprints/knobs",
        content='{"knobs": {"common": 1e400, "uncommon": -1e400, "jitter_pct": 1e400}}',
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Non-finite values drop to auto (None) — never a crash.
    assert data["knobs"]["common"] is None
    assert data["knobs"]["uncommon"] is None
    assert data["knobs"]["jitter_pct"] == 0.25  # non-finite jitter -> default


def test_knobs_409_when_no_active_project(client):
    resp = client.post("/api/wizard/reprints/knobs", json={"knobs": {}})
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# POST /api/wizard/reprints/refresh
# ---------------------------------------------------------------------------


def _stub_pick(monkeypatch, slot_id: str, card_name: str) -> None:
    """Dispatch on tool name: select returns the card, place assigns it to a slot."""

    def stub(**kwargs):
        if kwargs["tool_schema"]["name"] == "select_reprints":
            result = {"selections": [{"card_name": card_name, "reason": "r"}]}
        else:
            result = {"assignments": [{"card_name": card_name, "slot_id": slot_id, "reason": "r"}]}
        return {"result": result, "input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr("mtgai.generation.llm_client.generate_with_tool", stub)


def test_refresh_runs_selection_with_pinned_knob(client, isolated_output, monkeypatch):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)  # B-C-03 slot, no tweaked_text → rendered default text
    _stub_pick(monkeypatch, "B-C-03", "Murder")  # Murder is in the curated pool
    resp = client.post(
        "/api/wizard/reprints/refresh",
        json={"knobs": {"common": 1, "uncommon": 0, "rare": 0, "mythic": 0, "jitter_pct": 0.0}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_count"] == 1  # sum of per-rarity targets
    assert data["per_rarity_targets"]["common"] == 1
    assert len(data["selections"]) == 1
    assert data["selections"][0]["candidate"]["name"] == "Murder"
    # knobs + selection both persisted
    assert json.loads((asset / "reprints" / "knobs.json").read_text())["common"] == 1
    assert (asset / "reprint_selection.json").exists()
    # The pick is stamped back into the skeleton so card-gen skips the slot and the
    # lands investigation sees it as filled.
    slot = json.loads((asset / "skeleton.json").read_text())["slots"][0]
    assert slot["slot_id"] == "B-C-03"
    assert slot["is_reprint_slot"] is True
    assert "Murder" in slot["reprint_card"]


def test_refresh_cancel_preserves_prior_selection(client, isolated_output, monkeypatch):
    """A Cancel landing mid-reroll must not clobber the prior reprint_selection.json
    or the skeleton stamps — the endpoint skips the persist and returns prior state.
    (Before B2's worker cancellation, Cancel was a no-op here; the fix makes sure
    enabling it doesn't turn an abort into data loss.)"""
    from mtgai.generation import reprint_selector as rs

    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)  # B-C-03 slot

    # Prior good selection on disk + a stamped skeleton slot.
    prior = {
        "set_code": "TST",
        "set_size": 60,
        "target_reprint_count": 1,
        "per_rarity_targets": {"common": 1, "uncommon": 0, "rare": 0, "mythic": 0},
        "selections": [
            {
                "slot": {"slot_id": "B-C-03", "descriptor": "d"},
                "candidate": {
                    "name": "Murder",
                    "cmc": 3,
                    "type_line": "Instant",
                    "rarity": "common",
                    "role": "removal",
                },
                "reason": "prior",
            }
        ],
        "all_candidates_considered": 1,
        "selection_timestamp": "t",
    }
    (asset / "reprint_selection.json").write_text(json.dumps(prior), encoding="utf-8")
    sk = json.loads((asset / "skeleton.json").read_text())
    sk["slots"][0]["is_reprint_slot"] = True
    sk["slots"][0]["reprint_card"] = "Murder · Instant · {1}{B}{B}"
    (asset / "skeleton.json").write_text(json.dumps(sk), encoding="utf-8")

    def stub_cancel(*_a, **_k):
        ai_lock.request_cancel()  # a user Cancel landing mid-run (lock is held)
        return rs.ReprintSelection(
            set_code="TST",
            set_size=60,
            target_reprint_count=0,
            per_rarity_targets=None,
            selections=[],
            all_candidates_considered=0,
            selection_timestamp="t",
        )

    monkeypatch.setattr(rs, "select_reprints", stub_cancel)
    resp = client.post("/api/wizard/reprints/refresh", json={})
    assert resp.status_code == 200
    # Prior selection preserved on disk (not overwritten with the empty result).
    on_disk = json.loads((asset / "reprint_selection.json").read_text())
    assert len(on_disk["selections"]) == 1
    assert on_disk["selections"][0]["candidate"]["name"] == "Murder"
    # Skeleton stamp survives the cancelled re-roll.
    assert json.loads((asset / "skeleton.json").read_text())["slots"][0]["is_reprint_slot"] is True
    # Response is the preserved prior state, not the aborted empty result.
    assert len(resp.json()["selections"]) == 1


def test_refresh_400_when_no_skeleton(client, isolated_output, monkeypatch):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _stub_pick(monkeypatch, "B-C-03", "Murder")
    resp = client.post("/api/wizard/reprints/refresh", json={})
    assert resp.status_code == 400


def test_refresh_409_when_ai_busy(client, isolated_output, monkeypatch):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)
    _stub_pick(monkeypatch, "B-C-03", "Murder")
    with ai_lock.hold("Other action") as acquired:
        assert acquired
        resp = client.post("/api/wizard/reprints/refresh", json={})
        assert resp.status_code == 409
        assert resp.json()["running_action"] == "Other action"


def test_refresh_preserves_pinned_pick_no_ai(client, isolated_output, monkeypatch):
    """A Refresh whose pins already cover the target keeps them verbatim and makes
    no LLM call (ai_target == 0)."""
    from mtgai.generation import llm_client

    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)  # one slot B-C-03

    def boom(**_kwargs):
        raise AssertionError("LLM must not be called when pins cover the target")

    monkeypatch.setattr(llm_client, "generate_with_tool", boom)
    resp = client.post(
        "/api/wizard/reprints/refresh",
        json={
            "knobs": {"common": 1, "uncommon": 0, "rare": 0, "mythic": 0, "jitter_pct": 0.0},
            "pinned": [{"card_name": "Murder", "slot_id": "B-C-03", "reason": "mine"}],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert [s["candidate"]["name"] for s in data["selections"]] == ["Murder"]
    assert data["selections"][0]["pinned"] is True
    # Stamped into the skeleton like any placed reprint.
    slot = json.loads((asset / "skeleton.json").read_text())["slots"][0]
    assert slot["is_reprint_slot"] is True and "Murder" in slot["reprint_card"]


# ---------------------------------------------------------------------------
# GET /api/wizard/reprints/pool
# ---------------------------------------------------------------------------


def test_pool_lists_candidates_and_open_slots(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)
    data = client.get("/api/wizard/reprints/pool").json()
    assert isinstance(data["pool"], list) and len(data["pool"]) > 0
    assert any(c["name"] == "Murder" for c in data["pool"])
    assert data["open_slots"] == [{"slot_id": "B-C-03", "text": "Black common instant CMC3"}] or (
        data["open_slots"] and data["open_slots"][0]["slot_id"] == "B-C-03"
    )


def test_pool_409_when_no_active_project(client):
    resp = client.get("/api/wizard/reprints/pool")
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_active_project"


# ---------------------------------------------------------------------------
# POST /api/wizard/reprints/save
# ---------------------------------------------------------------------------


def test_save_persists_manual_selection_and_stamps_skeleton(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)
    resp = client.post(
        "/api/wizard/reprints/save",
        json={"selections": [{"card_name": "Murder", "slot_id": "B-C-03", "pinned": True}]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_content"] is True
    assert data["target_count"] == 1
    assert data["selections"][0]["candidate"]["name"] == "Murder"
    assert data["selections"][0]["pinned"] is True
    assert "navigate_to" in data
    # Written + stamped.
    on_disk = json.loads((asset / "reprint_selection.json").read_text())
    assert on_disk["selections"][0]["candidate"]["name"] == "Murder"
    slot = json.loads((asset / "skeleton.json").read_text())["slots"][0]
    assert slot["is_reprint_slot"] is True and "Murder" in slot["reprint_card"]


def test_save_empty_selection_is_valid(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)
    resp = client.post("/api/wizard/reprints/save", json={"selections": []})
    assert resp.status_code == 200
    assert resp.json()["has_content"] is False
    assert (asset / "reprint_selection.json").exists()


def test_save_rejects_unknown_card(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)
    resp = client.post(
        "/api/wizard/reprints/save",
        json={"selections": [{"card_name": "Not A Real Card", "slot_id": "B-C-03"}]},
    )
    assert resp.status_code == 400
    assert "Unknown reprint card" in resp.json()["error"]


def test_save_rejects_unknown_slot(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)
    resp = client.post(
        "/api/wizard/reprints/save",
        json={"selections": [{"card_name": "Murder", "slot_id": "NOPE"}]},
    )
    assert resp.status_code == 400


def test_save_rejects_duplicate_card(client, isolated_output):
    asset = isolated_output / "sets" / "TST"
    _seed_project(asset)
    _write_skeleton(asset)
    resp = client.post(
        "/api/wizard/reprints/save",
        json={
            "selections": [
                {"card_name": "Murder", "slot_id": "B-C-03"},
                {"card_name": "Murder", "slot_id": "B-C-03"},
            ]
        },
    )
    assert resp.status_code == 400


def test_save_409_when_no_active_project(client):
    resp = client.post("/api/wizard/reprints/save", json={"selections": []})
    assert resp.status_code == 409
