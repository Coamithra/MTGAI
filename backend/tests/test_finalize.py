"""Tests for post-review finalization pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mtgai.models.card import Card
from mtgai.models.enums import Color, Rarity
from mtgai.review.finalize import finalize_card, finalize_set

MECHANICS = [
    {
        "name": "Salvage",
        "reminder_text": (
            "(Look at the top X cards of your library. You may put an "
            "artifact card from among them into your hand. Put the rest "
            "on the bottom of your library in any order.)"
        ),
    },
    {
        "name": "Malfunction",
        "reminder_text": (
            "(This permanent enters tapped with N malfunction counters "
            "on it. At the beginning of your upkeep, remove a malfunction "
            "counter from it.)"
        ),
    },
    {
        "name": "Overclock",
        "reminder_text": (
            "(Exile the top three cards of your library. You may play them until end of turn.)"
        ),
    },
]


def _make_card(**overrides) -> Card:
    defaults = {
        "name": "Test Creature",
        "mana_cost": "{2}{G}",
        "cmc": 3.0,
        "type_line": "Creature — Beast",
        "oracle_text": "Trample",
        "power": "3",
        "toughness": "3",
        "rarity": Rarity.COMMON,
        "colors": [Color.GREEN],
        "color_identity": [Color.GREEN],
        "collector_number": "001",
        "set_code": "TST",
        "card_types": ["Creature"],
        "subtypes": ["Beast"],
    }
    defaults.update(overrides)
    return Card(**defaults)


class TestFinalizeCard:
    def test_injects_reminder_text(self):
        card = _make_card(oracle_text="When ~ enters, salvage 3.")
        finalized, _fixes, _manual = finalize_card(card, MECHANICS)
        assert "(Look at the top three cards" in finalized.oracle_text

    def test_auto_fixes_applied(self):
        """ETB phrasing should be auto-fixed during finalization."""
        card = _make_card(oracle_text="When ~ enters the battlefield, salvage 3.")
        finalized, fixes, _manual = finalize_card(card, MECHANICS)
        assert "enters the battlefield" not in finalized.oracle_text
        assert "enters," in finalized.oracle_text
        assert any("etb" in f.lower() for f in fixes)

    def test_manual_errors_surfaced(self):
        """A haste + enters-tapped nonbo should appear as a MANUAL error."""
        card = _make_card(
            oracle_text="Haste\nThis creature enters tapped.",
        )
        _finalized, _fixes, manual = finalize_card(card, MECHANICS)
        assert any("nonbo" in e.message.lower() for e in manual)

    def test_clean_card_no_errors(self):
        card = _make_card(oracle_text="Trample", power="2", toughness="2")
        finalized, fixes, manual = finalize_card(card, MECHANICS)
        assert len(fixes) == 0
        assert len(manual) == 0
        assert finalized.oracle_text == "Trample"

    def test_strips_old_reminder_and_reinjects(self):
        """Old LLM reminder text is replaced with correct version."""
        card = _make_card(
            oracle_text=(
                "When ~ enters, salvage 3. (Look at the top 3 cards of "
                "your library. You may put an artifact card from among "
                "them into your hand. Put the rest on the bottom of your "
                "library in any order.)"
            )
        )
        finalized, _fixes, _manual = finalize_card(card, MECHANICS)
        # Old "3" replaced with "three"
        assert "top three cards" in finalized.oracle_text
        # Only one reminder text
        assert finalized.oracle_text.count("(Look at the top") == 1

    def test_chained_auto_fixes_with_injection(self):
        """Multiple auto-fixable issues + reminder injection all apply."""
        card = _make_card(
            name="Test Card",
            oracle_text="When Test Card enters the battlefield, salvage 3.",
        )
        finalized, _fixes, _manual = finalize_card(card, MECHANICS)
        # Card name → ~
        assert "Test Card" not in finalized.oracle_text
        assert "~" in finalized.oracle_text
        # ETB → enters
        assert "enters the battlefield" not in finalized.oracle_text
        # Reminder text injected
        assert "(Look at the top three cards" in finalized.oracle_text


@pytest.fixture
def active_asset(tmp_path: Path):
    """An active project rooted at a tmp asset dir with cards/ + mechanics/."""
    from mtgai.runtime import active_project
    from mtgai.settings.model_settings import ModelSettings

    asset_dir = tmp_path / "asset"
    (asset_dir / "cards").mkdir(parents=True)
    (asset_dir / "mechanics").mkdir(parents=True)
    (asset_dir / "mechanics" / "approved.json").write_text("[]", encoding="utf-8")
    active_project.write_active_project(
        active_project.ProjectState(
            set_code="TST", settings=ModelSettings(asset_folder=str(asset_dir))
        )
    )
    yield asset_dir
    active_project.clear_active_project()


class TestFinalizeSetResilience:
    """One malformed card must not abort the whole finalize stage."""

    def test_unloadable_card_is_skipped_and_recorded(self, active_asset: Path) -> None:
        cards_dir = active_asset / "cards"
        # Two healthy cards finalize normally...
        (cards_dir / "001_alpha.json").write_text(
            _make_card(name="Alpha", collector_number="001").model_dump_json(),
            encoding="utf-8",
        )
        (cards_dir / "002_beta.json").write_text(
            _make_card(name="Beta", collector_number="002").model_dump_json(),
            encoding="utf-8",
        )
        # ...while a card with an unanticipated malformation (invalid rarity enum)
        # is valid JSON but fails the strict Card load.
        (cards_dir / "003_broken.json").write_text(
            json.dumps(
                {
                    "name": "Broken",
                    "collector_number": "003",
                    "set_code": "TST",
                    "type_line": "Creature — Beast",
                    "rarity": "ultramega",
                }
            ),
            encoding="utf-8",
        )

        # dry_run skips the LLM sanity pass + disk writes; the per-card load is
        # still exercised, which is what we're testing.
        summary = finalize_set(dry_run=True)

        # The healthy pair finalized; the broken card did not abort the run.
        assert summary["total_cards"] == 2
        assert {c["name"] for c in summary["cards"]} == {"Alpha", "Beta"}

        failures = summary["load_failures"]
        assert len(failures) == 1
        failure = failures[0]
        assert failure["collector_number"] == "003"
        assert failure["name"] == "Broken"
        assert failure["file"] == "003_broken.json"
        assert failure["error"]

    def test_no_failures_when_pool_is_clean(self, active_asset: Path) -> None:
        cards_dir = active_asset / "cards"
        (cards_dir / "001_alpha.json").write_text(
            _make_card(name="Alpha", collector_number="001").model_dump_json(),
            encoding="utf-8",
        )

        summary = finalize_set(dry_run=True)

        assert summary["total_cards"] == 1
        assert summary["load_failures"] == []
