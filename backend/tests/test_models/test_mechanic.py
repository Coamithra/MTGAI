"""Tests for the Mechanic model."""

import pytest

from mtgai.models.enums import Color, Rarity
from mtgai.models.mechanic import Mechanic

# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


def test_mechanic_full_fields(sample_mechanic):
    """A mechanic with all fields populated."""
    assert sample_mechanic.name == "Investigate"
    assert sample_mechanic.keyword_type == "keyword_action"
    assert len(sample_mechanic.colors) == 3
    assert len(sample_mechanic.allowed_rarities) == 3


def test_mechanic_minimal():
    """A mechanic with only required fields."""
    m = Mechanic(
        name="Flying",
        keyword_type="keyword_ability",
        reminder_text="(This creature can't be blocked except by creatures with flying or reach.)",
        rules_template="Flying",
    )
    assert m.name == "Flying"
    assert m.description == ""
    assert m.colors == []
    assert m.allowed_rarities == []
    assert m.card_type_affinity == []
    assert m.is_evergreen is False
    assert m.example_cards == []
    assert m.design_notes is None


def test_mechanic_all_fields():
    """A mechanic with every field explicitly set."""
    m = Mechanic(
        name="Investigate",
        keyword_type="keyword_action",
        reminder_text="Create a Clue token.",
        rules_template="Investigate",
        description="Clue token generation for card advantage",
        colors=[Color.WHITE, Color.BLUE, Color.GREEN],
        allowed_rarities=[Rarity.COMMON, Rarity.UNCOMMON, Rarity.RARE, Rarity.MYTHIC],
        card_type_affinity=["Creature", "Instant", "Sorcery"],
        is_evergreen=False,
        example_cards=["Tireless Tracker", "Bygone Bishop"],
        design_notes="Primary mechanic for the mystery theme",
    )
    assert len(m.colors) == 3
    assert len(m.allowed_rarities) == 4
    assert len(m.card_type_affinity) == 3
    assert len(m.example_cards) == 2
    assert m.design_notes is not None


# ---------------------------------------------------------------------------
# Round-trip serialization
# ---------------------------------------------------------------------------


def test_mechanic_round_trip(sample_mechanic):
    """Mechanic survives JSON round-trip."""
    json_str = sample_mechanic.model_dump_json()
    restored = Mechanic.model_validate_json(json_str)
    assert restored == sample_mechanic
    assert restored.name == "Investigate"
    assert restored.colors == sample_mechanic.colors


def test_mechanic_minimal_round_trip():
    """Minimal mechanic round-trips correctly."""
    m = Mechanic(
        name="Haste",
        keyword_type="keyword_ability",
        reminder_text="(This creature can attack and {T} as soon as it comes under your control.)",
        rules_template="Haste",
    )
    restored = Mechanic.model_validate_json(m.model_dump_json())
    assert restored.name == "Haste"
    assert restored.colors == []
    assert restored.allowed_rarities == []


# ---------------------------------------------------------------------------
# Color and rarity lists
# ---------------------------------------------------------------------------


def test_mechanic_empty_colors():
    """Mechanic with no color restriction."""
    m = Mechanic(
        name="Colorless Mechanic",
        keyword_type="keyword_ability",
        reminder_text="Test",
        rules_template="Test",
        colors=[],
    )
    assert m.colors == []


def test_mechanic_single_color():
    """Mechanic restricted to a single color."""
    m = Mechanic(
        name="Bloodthirst",
        keyword_type="keyword_ability",
        reminder_text="Test",
        rules_template="Bloodthirst N",
        colors=[Color.RED],
    )
    assert m.colors == [Color.RED]


def test_mechanic_all_colors():
    """Mechanic available in all five colors."""
    m = Mechanic(
        name="Kicker",
        keyword_type="keyword_ability",
        reminder_text="You may pay an additional cost.",
        rules_template="Kicker {cost}",
        colors=[Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN],
    )
    assert len(m.colors) == 5


def test_mechanic_empty_rarities():
    """Mechanic with no rarity restriction."""
    m = Mechanic(
        name="Open",
        keyword_type="ability_word",
        reminder_text="Test",
        rules_template="Test",
        allowed_rarities=[],
    )
    assert m.allowed_rarities == []


def test_mechanic_single_rarity():
    """Mechanic allowed at a single rarity."""
    m = Mechanic(
        name="Mythic-Only",
        keyword_type="keyword_ability",
        reminder_text="Test",
        rules_template="Test",
        allowed_rarities=[Rarity.MYTHIC],
    )
    assert m.allowed_rarities == [Rarity.MYTHIC]


def test_mechanic_all_rarities():
    """Mechanic allowed at all rarities."""
    m = Mechanic(
        name="Universal",
        keyword_type="keyword_ability",
        reminder_text="Test",
        rules_template="Test",
        allowed_rarities=[Rarity.COMMON, Rarity.UNCOMMON, Rarity.RARE, Rarity.MYTHIC],
    )
    assert len(m.allowed_rarities) == 4


# ---------------------------------------------------------------------------
# Evergreen vs custom
# ---------------------------------------------------------------------------


def test_evergreen_mechanic():
    """Evergreen mechanics have is_evergreen=True."""
    m = Mechanic(
        name="Flying",
        keyword_type="keyword_ability",
        reminder_text="(This creature can't be blocked except by creatures with flying or reach.)",
        rules_template="Flying",
        is_evergreen=True,
    )
    assert m.is_evergreen is True


def test_custom_mechanic():
    """Custom set mechanics have is_evergreen=False (default)."""
    m = Mechanic(
        name="Investigate",
        keyword_type="keyword_action",
        reminder_text="Create a Clue token.",
        rules_template="Investigate",
    )
    assert m.is_evergreen is False


@pytest.mark.parametrize(
    "keyword_type",
    ["keyword_ability", "ability_word", "keyword_action"],
)
def test_keyword_types(keyword_type):
    """All three keyword types are accepted."""
    m = Mechanic(
        name="Test",
        keyword_type=keyword_type,
        reminder_text="Test",
        rules_template="Test",
    )
    assert m.keyword_type == keyword_type
