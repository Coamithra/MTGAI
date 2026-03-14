"""Tests for the reminder text injection pipeline."""

from __future__ import annotations

from mtgai.generation.reminder_injector import (
    finalize_reminder_text,
    inject_reminder_text,
    strip_reminder_text,
)
from mtgai.models.card import Card
from mtgai.models.enums import Color, Rarity

# ---------------------------------------------------------------------------
# Test mechanic definitions (matching approved.json structure)
# ---------------------------------------------------------------------------

MECHANICS = [
    {
        "name": "Salvage",
        "keyword_type": "keyword_ability",
        "reminder_text": (
            "(Look at the top X cards of your library. You may put an "
            "artifact card from among them into your hand. Put the rest "
            "on the bottom of your library in any order.)"
        ),
    },
    {
        "name": "Malfunction",
        "keyword_type": "keyword_ability",
        "reminder_text": (
            "(This permanent enters tapped with N malfunction counters "
            "on it. At the beginning of your upkeep, remove a malfunction "
            "counter from it.)"
        ),
    },
    {
        "name": "Overclock",
        "keyword_type": "keyword_action",
        "reminder_text": (
            "(Exile the top three cards of your library. You may play them until end of turn.)"
        ),
    },
]


def _make_card(**overrides) -> Card:
    defaults = {
        "name": "Test Card",
        "mana_cost": "{2}{G}",
        "cmc": 3.0,
        "type_line": "Creature — Beast",
        "oracle_text": "",
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


# ===========================================================================
# strip_reminder_text
# ===========================================================================


class TestStripReminderText:
    def test_strip_long_parenthesized_text(self):
        oracle = (
            "Salvage 3. (Look at the top three cards of your library. "
            "You may put an artifact card from among them into your hand. "
            "Put the rest on the bottom of your library in any order.)"
        )
        result = strip_reminder_text(oracle)
        assert result == "Salvage 3."

    def test_preserves_short_parenthesized_text(self):
        """Short parens (< 20 chars) like mode choices are kept."""
        oracle = "Choose one (or both)"
        result = strip_reminder_text(oracle)
        assert result == "Choose one (or both)"

    def test_strip_multiple_reminder_texts(self):
        oracle = (
            "Salvage 3. (Look at the top three cards of your library. "
            "You may put an artifact card from among them into your hand. "
            "Put the rest on the bottom of your library in any order.)\n"
            "Malfunction 2. (This permanent enters tapped with two "
            "malfunction counters on it. At the beginning of your upkeep, "
            "remove a malfunction counter from it.)"
        )
        result = strip_reminder_text(oracle)
        assert "Look at" not in result
        assert "enters tapped" not in result
        assert "Salvage 3." in result
        assert "Malfunction 2." in result

    def test_strip_preserves_non_reminder_content(self):
        oracle = (
            "When ~ enters, salvage 3. (Look at the top three cards of "
            "your library. You may put an artifact card from among them "
            "into your hand. Put the rest on the bottom of your library "
            "in any order.)\nDraw a card."
        )
        result = strip_reminder_text(oracle)
        assert "When ~ enters, salvage 3." in result
        assert "Draw a card." in result

    def test_empty_oracle(self):
        assert strip_reminder_text("") == ""

    def test_no_reminder_text_unchanged(self):
        oracle = "When ~ enters, draw a card."
        assert strip_reminder_text(oracle) == oracle


# ===========================================================================
# inject_reminder_text — USES (should inject)
# ===========================================================================


class TestInjectUses:
    def test_salvage_with_number(self):
        card = _make_card(oracle_text="When ~ enters, salvage 3.")
        result = inject_reminder_text(card, MECHANICS)
        assert "(Look at the top three cards" in result.oracle_text

    def test_salvage_number_substitution(self):
        card = _make_card(oracle_text="Salvage 5")
        result = inject_reminder_text(card, MECHANICS)
        assert "(Look at the top five cards" in result.oracle_text

    def test_malfunction_with_number(self):
        card = _make_card(oracle_text="Malfunction 2")
        result = inject_reminder_text(card, MECHANICS)
        assert "(This permanent enters tapped with two" in result.oracle_text

    def test_malfunction_singular(self):
        card = _make_card(oracle_text="Malfunction 1")
        result = inject_reminder_text(card, MECHANICS)
        assert "one malfunction counter on it" in result.oracle_text
        assert "counters" not in result.oracle_text.split("(")[1]

    def test_overclock_activated_ability(self):
        card = _make_card(oracle_text="{2}{B}, {T}: Overclock.")
        result = inject_reminder_text(card, MECHANICS)
        assert "(Exile the top three cards" in result.oracle_text

    def test_overclock_triggered_effect(self):
        """'When ~ enters, overclock.' = the card performs the action."""
        card = _make_card(oracle_text="When ~ enters, overclock.")
        result = inject_reminder_text(card, MECHANICS)
        assert "(Exile the top three cards" in result.oracle_text

    def test_overclock_upkeep_trigger(self):
        card = _make_card(oracle_text="At the beginning of your upkeep, overclock.")
        result = inject_reminder_text(card, MECHANICS)
        assert "(Exile the top three cards" in result.oracle_text

    def test_grants_malfunction(self):
        """'It gains malfunction 2' = granting the ability."""
        card = _make_card(oracle_text="It gains malfunction 2.")
        result = inject_reminder_text(card, MECHANICS)
        assert "(This permanent enters tapped with two" in result.oracle_text

    def test_only_first_use_gets_reminder(self):
        card = _make_card(
            oracle_text=("When ~ enters, salvage 3.\nWhenever an artifact enters, salvage 2.")
        )
        result = inject_reminder_text(card, MECHANICS)
        count = result.oracle_text.count("(Look at the top")
        assert count == 1
        assert "(Look at the top three cards" in result.oracle_text

    def test_multiple_keywords_on_same_card(self):
        card = _make_card(oracle_text="Salvage 3\nMalfunction 2")
        result = inject_reminder_text(card, MECHANICS)
        assert "(Look at the top three cards" in result.oracle_text
        assert "(This permanent enters tapped with two" in result.oracle_text

    def test_case_insensitive(self):
        card = _make_card(oracle_text="When ~ enters, SALVAGE 4.")
        result = inject_reminder_text(card, MECHANICS)
        assert "(Look at the top four cards" in result.oracle_text

    def test_keyword_in_quoted_ability(self):
        """Granted ability in quotes still gets reminder text."""
        card = _make_card(oracle_text=('Create a token with "When this creature dies, salvage 5."'))
        result = inject_reminder_text(card, MECHANICS)
        assert "(Look at the top five cards" in result.oracle_text

    def test_overclock_with_use_and_trigger_on_same_card(self):
        """Card that both USES overclock and triggers off it."""
        card = _make_card(
            oracle_text=(
                "Deathtouch\n"
                "{2}{B}, {T}: Overclock.\n"
                "Whenever ~ overclocks, each opponent loses 2 life."
            )
        )
        result = inject_reminder_text(card, MECHANICS)
        # Reminder on the USE line
        assert "Overclock. (Exile the top three" in result.oracle_text
        # Only one reminder text
        assert result.oracle_text.count("(Exile the top three") == 1


# ===========================================================================
# inject_reminder_text — REFERENCES (should NOT inject)
# ===========================================================================


class TestInjectReferences:
    def test_no_inject_whenever_you_overclock(self):
        """'Whenever you overclock' is a trigger — no reminder text."""
        card = _make_card(oracle_text="Whenever you overclock, draw a card.")
        result = inject_reminder_text(card, MECHANICS)
        assert "(Exile" not in result.oracle_text

    def test_no_inject_whenever_tilde_overclocks(self):
        """'Whenever ~ overclocks' uses conjugated form — won't match."""
        card = _make_card(oracle_text="Whenever ~ overclocks, deal 2 damage.")
        result = inject_reminder_text(card, MECHANICS)
        assert "(Exile" not in result.oracle_text

    def test_no_inject_if_you_overclock(self):
        card = _make_card(oracle_text="If you overclock this turn, draw a card.")
        result = inject_reminder_text(card, MECHANICS)
        assert "(Exile" not in result.oracle_text

    def test_no_inject_malfunction_counter(self):
        """'malfunction counter' is a reference, not the ability."""
        card = _make_card(
            oracle_text=("When the last malfunction counter is removed from ~, draw a card.")
        )
        result = inject_reminder_text(card, MECHANICS)
        assert "(This permanent" not in result.oracle_text

    def test_no_inject_bare_salvage_without_number(self):
        """'whenever you salvage' without a number = reference."""
        card = _make_card(oracle_text="Whenever you salvage, you gain 1 life.")
        result = inject_reminder_text(card, MECHANICS)
        assert "(Look at" not in result.oracle_text

    def test_no_inject_creatures_with_malfunction(self):
        """Lord effect referencing keyword — no reminder text."""
        card = _make_card(oracle_text=("All creatures with malfunction get +1/+1."))
        result = inject_reminder_text(card, MECHANICS)
        assert "(This permanent" not in result.oracle_text

    def test_no_inject_keyword_absent(self):
        card = _make_card(oracle_text="Flying, trample")
        result = inject_reminder_text(card, MECHANICS)
        assert result.oracle_text == "Flying, trample"

    def test_empty_oracle_unchanged(self):
        card = _make_card(oracle_text="")
        result = inject_reminder_text(card, MECHANICS)
        assert result.oracle_text == ""


# ===========================================================================
# finalize_reminder_text (strip + inject)
# ===========================================================================


class TestFinalizeReminderText:
    def test_strips_old_then_injects_fresh(self):
        """Old LLM-generated reminder text is replaced with correct version."""
        card = _make_card(
            oracle_text=(
                "When ~ enters, salvage 3. (Look at the top 3 cards of "
                "your library. You may put an artifact card from among "
                "them into your hand. Put the rest on the bottom of your "
                "library in any order.)"
            )
        )
        result = finalize_reminder_text(card, MECHANICS)
        # Old text used "3" (digit), new text should use "three" (word)
        assert "top three cards" in result.oracle_text
        # Only one reminder text present
        assert result.oracle_text.count("(Look at the top") == 1

    def test_finalize_card_without_mechanics(self):
        card = _make_card(oracle_text="Flying, trample")
        result = finalize_reminder_text(card, MECHANICS)
        assert result.oracle_text == "Flying, trample"

    def test_finalize_idempotent(self):
        """Running finalize twice produces the same result."""
        card = _make_card(oracle_text="Salvage 3")
        first = finalize_reminder_text(card, MECHANICS)
        second = finalize_reminder_text(first, MECHANICS)
        assert first.oracle_text == second.oracle_text

    def test_finalize_reference_only_card(self):
        """Card that only references keywords gets no reminder text."""
        card = _make_card(oracle_text="Whenever you overclock, draw a card.")
        result = finalize_reminder_text(card, MECHANICS)
        assert result.oracle_text == "Whenever you overclock, draw a card."
