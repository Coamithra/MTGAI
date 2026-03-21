"""Tests for the FastAPI review server.

Verifies that endpoints return correct status codes and content types.
Uses FastAPI TestClient with minimal fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from mtgai.review.server import app


@pytest.fixture()
def client():
    """Create a TestClient for the FastAPI app."""
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helpers — minimal card fixtures
# ---------------------------------------------------------------------------


def _make_card(**overrides):
    """Build a Card model with minimal valid defaults."""
    from mtgai.models.card import Card

    defaults = {
        "name": "Test Guardian",
        "mana_cost": "{1}{W}",
        "cmc": 2.0,
        "colors": ["W"],
        "color_identity": ["W"],
        "type_line": "Creature — Human Soldier",
        "oracle_text": "Vigilance",
        "rarity": "common",
        "set_code": "TST",
        "collector_number": "W-C-01",
        "power": "2",
        "toughness": "2",
    }
    defaults.update(overrides)
    return Card(**defaults)


def _make_card_list():
    """Build a small set of cards with mixed rarities for booster tests."""
    cards = []
    # 10 commons
    for i in range(1, 11):
        cards.append(
            _make_card(
                name=f"Common {i}",
                collector_number=f"W-C-{i:02d}",
                rarity="common",
            )
        )
    # 3 uncommons
    for i in range(1, 4):
        cards.append(
            _make_card(
                name=f"Uncommon {i}",
                collector_number=f"W-U-{i:02d}",
                rarity="uncommon",
            )
        )
    # 1 rare
    cards.append(
        _make_card(
            name="Rare Card",
            collector_number="W-R-01",
            rarity="rare",
        )
    )
    # 1 basic land
    cards.append(
        _make_card(
            name="Plains",
            collector_number="L-C-01",
            rarity="common",
            type_line="Basic Land — Plains",
            oracle_text="",
            mana_cost="",
            cmc=0.0,
            power=None,
            toughness=None,
        )
    )
    return cards


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------


class TestRootRedirect:
    def test_redirects_to_review(self, client: TestClient):
        response = client.get("/", follow_redirects=False)
        assert response.status_code in (301, 302, 307)
        assert "/review" in response.headers.get("location", "")


class TestReviewPage:
    @patch("mtgai.review.server._load_cards_as_json")
    @patch("mtgai.review.server._get_set_code", return_value="TST")
    def test_review_page_loads(self, mock_set, mock_cards, client: TestClient):
        mock_cards.return_value = ([], "[]")
        response = client.get("/review")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @patch("mtgai.review.server._load_cards_as_json")
    @patch("mtgai.review.server._get_set_code", return_value="TST")
    def test_review_page_contains_set_code(self, mock_set, mock_cards, client: TestClient):
        mock_cards.return_value = ([], "[]")
        response = client.get("/review?set_code=TST")
        assert response.status_code == 200
        assert "TST" in response.text


class TestProgressPage:
    @patch("mtgai.review.server._get_set_code", return_value="TST")
    def test_progress_page_loads_no_data(self, mock_set, client: TestClient):
        with patch("mtgai.review.decisions.load_progress", return_value=None):
            response = client.get("/progress")
            assert response.status_code == 200
            assert "text/html" in response.headers.get("content-type", "")


class TestBoosterPage:
    @patch("mtgai.review.server._load_cards_as_json")
    @patch("mtgai.review.server._get_set_code", return_value="TST")
    def test_booster_page_loads(self, mock_set, mock_cards, client: TestClient):
        mock_cards.return_value = ([], "[]")
        response = client.get("/booster")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


class TestApiCards:
    @patch("mtgai.review.server._load_cards_as_json")
    @patch("mtgai.review.server._get_set_code", return_value="TST")
    def test_returns_json_list(self, mock_set, mock_cards, client: TestClient):
        mock_cards.return_value = ([{"name": "Test"}], '[{"name": "Test"}]')
        response = client.get("/api/cards")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1


class TestApiProgress:
    @patch("mtgai.review.server._get_set_code", return_value="TST")
    def test_returns_empty_when_no_progress(self, mock_set, client: TestClient):
        with patch("mtgai.review.decisions.load_progress", return_value=None):
            response = client.get("/api/progress")
            assert response.status_code == 200
            data = response.json()
            assert "cards" in data
            assert data["cards"] == {}


class TestApiSubmitReview:
    @patch("mtgai.review.server._get_set_code", return_value="TST")
    def test_submit_review(self, mock_set, client: TestClient, tmp_path: Path):
        """Submit a review and verify response structure."""
        # Patch save/dispatch to use tmp_path so we don't write to real output
        with (
            patch("mtgai.review.decisions._set_dir", return_value=tmp_path),
            patch("mtgai.review.decisions.get_review_round", return_value=1),
        ):
            # Create a minimal cards dir so dispatch can find card files
            cards_dir = tmp_path / "cards"
            cards_dir.mkdir()
            (cards_dir / "W-C-01_test_guardian.json").write_text(
                json.dumps({"name": "Test Guardian", "collector_number": "W-C-01"}),
                encoding="utf-8",
            )

            body = {
                "decisions": {
                    "W-C-01": {"action": "ok", "note": ""},
                    "B-R-02": {"action": "remake", "note": "too weak"},
                }
            }
            response = client.post("/api/review/submit", json=body)
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["review_round"] == 1
            assert "summary" in data


class TestApiBooster:
    @patch("mtgai.review.server._get_set_code", return_value="TST")
    def test_booster_returns_pack(self, mock_set, client: TestClient):
        cards = _make_card_list()
        with patch("mtgai.review.loaders.load_cards", return_value=cards):
            response = client.get("/api/booster?seed=42")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            # Standard pack should have ~15 cards
            assert len(data) >= 10

    @patch("mtgai.review.server._get_set_code", return_value="TST")
    def test_booster_empty_set(self, mock_set, client: TestClient):
        with patch("mtgai.review.loaders.load_cards", return_value=[]):
            response = client.get("/api/booster")
            assert response.status_code == 404


class TestApiReloadManual:
    @patch("mtgai.review.server._get_set_code", return_value="TST")
    def test_reload_no_decisions(self, mock_set, client: TestClient):
        with (
            patch("mtgai.review.decisions.load_decisions", return_value=None),
            patch("mtgai.review.decisions.load_progress", return_value=None),
        ):
            response = client.post("/api/progress/reload-manual")
            assert response.status_code == 404


# ---------------------------------------------------------------------------
# Card serialization
# ---------------------------------------------------------------------------


class TestCardToServerDict:
    def test_render_path_rewritten(self):
        from mtgai.review.server import _card_to_server_dict

        card = _make_card(render_path="renders/W-C-01_test_guardian.png")
        d = _card_to_server_dict(card, {}, {})
        assert d["render_path"] == "/renders/W-C-01_test_guardian.png"

    def test_art_path_rewritten(self):
        from mtgai.review.server import _card_to_server_dict

        card = _make_card(art_path="art/W-C-01_test_guardian_v1.png")
        d = _card_to_server_dict(card, {}, {})
        assert d["art_path"] == "/art/W-C-01_test_guardian_v1.png"

    def test_null_paths_with_disk_discovery(self):
        from mtgai.review.server import _card_to_server_dict

        render_map = {"W-C-01": "/renders/W-C-01_test_guardian.png"}
        art_map = {"W-C-01": "/art/W-C-01_test_guardian_v3.png"}
        card = _make_card()
        d = _card_to_server_dict(card, render_map, art_map)
        assert d["render_path"] == "/renders/W-C-01_test_guardian.png"
        assert d["art_path"] == "/art/W-C-01_test_guardian_v3.png"

    def test_null_paths_no_discovery(self):
        from mtgai.review.server import _card_to_server_dict

        card = _make_card()
        d = _card_to_server_dict(card, {}, {})
        assert d["render_path"] is None
        assert d["art_path"] is None
