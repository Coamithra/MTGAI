"""Tests for post-review finalization pipeline."""

from __future__ import annotations

from mtgai.models.card import Card
from mtgai.models.enums import Color, Rarity
from mtgai.review.finalize import finalize_card

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
            "(Exile the top three cards of your library. You may play "
            "them until end of turn.)"
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
        card = _make_card(
            oracle_text="When ~ enters the battlefield, salvage 3."
        )
        finalized, fixes, _manual = finalize_card(card, MECHANICS)
        assert "enters the battlefield" not in finalized.oracle_text
        assert "enters," in finalized.oracle_text
        assert any("etb" in f.lower() for f in fixes)

    def test_manual_errors_surfaced(self):
        """Haste+Malfunction nonbo should appear as MANUAL error."""
        card = _make_card(
            oracle_text="Haste\nMalfunction 2",
            mechanic_tags=["malfunction"],
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
