"""Integration coverage for the Finalization tab's wizard endpoints.

Drives ``/api/wizard/finalize/{state,save-card,save}`` against a real active
project + asset dir (the same fixture style as test_card_gen_state_routing) so
the editable-card flow — read state, badge auto-edited cards, persist a manual
edit, round-trip it back — is pinned end to end. The pure field-apply helper is
unit-tested in test_review/test_finalize_endpoints.py; this covers the wiring.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mtgai.review.server import app
from mtgai.runtime import active_project
from mtgai.settings.model_settings import ModelSettings


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def project(tmp_path: Path):
    asset_dir = tmp_path / "asset"
    (asset_dir / "cards").mkdir(parents=True)
    active_project.write_active_project(
        active_project.ProjectState(
            set_code="ABC", settings=ModelSettings(asset_folder=str(asset_dir))
        )
    )
    yield asset_dir
    active_project.clear_active_project()


def _write_card(asset: Path, fname: str, body: dict) -> None:
    (asset / "cards" / fname).write_text(json.dumps(body), encoding="utf-8")


def _card_body(cn: str, name: str, **extra) -> dict:
    base = {
        "name": name,
        "mana_cost": "{1}{G}",
        "cmc": 2.0,
        "colors": ["G"],
        "type_line": "Creature — Beast",
        "oracle_text": "Trample",
        "power": "2",
        "toughness": "2",
        "rarity": "common",
        "collector_number": cn,
        "set_code": "ABC",
        "card_types": ["Creature"],
        "subtypes": ["Beast"],
    }
    base.update(extra)
    return base


def test_state_lists_cards_and_badges_auto_edits(client, project: Path) -> None:
    _write_card(project, "001_alpha.json", _card_body("001", "Alpha"))
    _write_card(project, "002_beta.json", _card_body("002", "Beta"))
    # A finalize report marking 002 as auto-edited with a before/after.
    report = {
        "total_cards": 2,
        "cards_modified": 1,
        "total_auto_fixes": 1,
        "total_manual_errors": 0,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "cards": [
            {
                "collector_number": "002",
                "name": "Beta",
                "fixes_applied": ["etb: rewrote 'enters the battlefield'"],
                "original_oracle_text": "When ~ enters the battlefield, draw.",
                "manual_errors": [],
            }
        ],
    }
    (project / "reports").mkdir()
    (project / "reports" / "finalize-report.json").write_text(json.dumps(report), encoding="utf-8")

    resp = client.get("/api/wizard/finalize/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_content"] is True
    assert data["report"]["cards_modified"] == 1
    by_cn = {c["collector_number"]: c for c in data["cards"]}
    assert by_cn["001"]["auto_edited"] is False
    assert by_cn["002"]["auto_edited"] is True
    assert by_cn["002"]["fixes_applied"]
    assert by_cn["002"]["original_oracle_text"].startswith("When ~ enters the battlefield")


def test_save_card_persists_edit_and_marks_user_edited(client, project: Path) -> None:
    _write_card(project, "001_alpha.json", _card_body("001", "Alpha"))

    resp = client.post(
        "/api/wizard/finalize/save-card",
        json={"collector_number": "001", "fields": {"oracle_text": "Flying\n{T}: Draw a card."}},
    )
    assert resp.status_code == 200

    # The edit hit disk...
    saved = json.loads((project / "cards" / "001_alpha.json").read_text(encoding="utf-8"))
    assert saved["oracle_text"] == "Flying\n{T}: Draw a card."
    # ...and the card is now flagged user-edited in the next /state read.
    state = client.get("/api/wizard/finalize/state").json()
    card = next(c for c in state["cards"] if c["collector_number"] == "001")
    assert card["user_edited"] is True


def test_save_card_rename_on_name_change_no_duplicate(client, project: Path) -> None:
    """Editing the name must not fork a second file (the slug is name-derived)."""
    _write_card(project, "001_alpha.json", _card_body("001", "Alpha"))

    resp = client.post(
        "/api/wizard/finalize/save-card",
        json={"collector_number": "001", "fields": {"name": "Alpha Prime"}},
    )
    assert resp.status_code == 200

    files = sorted(p.name for p in (project / "cards").glob("*.json"))
    # The old slug file is gone; exactly one card file remains.
    assert files == ["001_alpha_prime.json"]
    saved = json.loads((project / "cards" / "001_alpha_prime.json").read_text(encoding="utf-8"))
    assert saved["name"] == "Alpha Prime"
    # And /state still shows a single card for cn 001.
    state = client.get("/api/wizard/finalize/state").json()
    assert [c["collector_number"] for c in state["cards"]] == ["001"]


def test_save_card_rejects_non_editable_field(client, project: Path) -> None:
    _write_card(project, "001_alpha.json", _card_body("001", "Alpha"))
    resp = client.post(
        "/api/wizard/finalize/save-card",
        json={"collector_number": "001", "fields": {"set_code": "HAX"}},
    )
    assert resp.status_code == 400
    assert "editable" in resp.json()["error"].lower()


def test_save_card_unknown_collector_number_404(client, project: Path) -> None:
    _write_card(project, "001_alpha.json", _card_body("001", "Alpha"))
    resp = client.post(
        "/api/wizard/finalize/save-card",
        json={"collector_number": "999", "fields": {"name": "Ghost"}},
    )
    assert resp.status_code == 404


def test_bulk_save_returns_next_stage_nav(client, project: Path) -> None:
    _write_card(project, "001_alpha.json", _card_body("001", "Alpha"))
    resp = client.post(
        "/api/wizard/finalize/save",
        json={"cards": [{"collector_number": "001", "fields": {"name": "Alpha Prime"}}]},
    )
    assert resp.status_code == 200
    data = resp.json()
    # finalize is followed by human_card_review in STAGE_DEFINITIONS.
    assert data["navigate_to"] == "/pipeline/human_card_review"
    saved = json.loads((project / "cards" / "001_alpha_prime.json").read_text(encoding="utf-8"))
    assert saved["name"] == "Alpha Prime"
