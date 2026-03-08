"""Tests for Set, SetSkeleton, and DraftArchetype models."""

from datetime import UTC, datetime

import pytest

from mtgai.models.card import Card
from mtgai.models.enums import Rarity
from mtgai.models.mechanic import Mechanic
from mtgai.models.set import DraftArchetype, Set, SetSkeleton

# ---------------------------------------------------------------------------
# Basic creation and round-trip
# ---------------------------------------------------------------------------


def test_set_creation(sample_set):
    """A set can be created with cards and skeleton."""
    assert sample_set.name == "Test Set"
    assert sample_set.code == "TST"
    assert len(sample_set.cards) == 2
    assert sample_set.skeleton is not None
    assert sample_set.skeleton.total_cards == 280


def test_set_round_trip(sample_set):
    """Set survives JSON round-trip."""
    json_str = sample_set.model_dump_json()
    loaded = Set.model_validate_json(json_str)
    assert loaded.name == "Test Set"
    assert len(loaded.cards) == 2
    assert loaded.cards[0].name == "Serra Angel"


def test_set_skeleton():
    """Skeleton rarity counts are stored correctly."""
    skeleton = SetSkeleton(
        total_cards=280,
        commons=101,
        uncommons=80,
        rares=60,
        mythics=20,
        basic_lands=5,
    )
    assert skeleton.commons + skeleton.uncommons + skeleton.rares + skeleton.mythics == 261


def test_draft_archetype():
    """Draft archetypes have required fields."""
    arch = DraftArchetype(
        color_pair="BR",
        name="Rakdos Sacrifice",
        description="Sacrifice creatures for value",
        primary_mechanics=["sacrifice"],
        signpost_uncommon="Rakdos Pyromancer",
    )
    assert arch.color_pair == "BR"
    assert arch.signpost_uncommon == "Rakdos Pyromancer"


def test_empty_set():
    """A set can be created with no cards."""
    s = Set(name="Empty Set", code="EMP", theme="Nothing")
    assert len(s.cards) == 0
    assert s.skeleton is None


# ---------------------------------------------------------------------------
# SetSkeleton depth
# ---------------------------------------------------------------------------


def test_skeleton_with_slot_matrix():
    """Skeleton stores a slot_matrix dict for detailed slot information."""
    slot_matrix = {
        "common_white_creature_1": {"rarity": "common", "color": "W", "type": "creature"},
        "common_white_creature_2": {"rarity": "common", "color": "W", "type": "creature"},
        "uncommon_blue_instant_1": {"rarity": "uncommon", "color": "U", "type": "instant"},
    }
    skeleton = SetSkeleton(
        total_cards=280,
        commons=101,
        uncommons=80,
        rares=60,
        mythics=20,
        basic_lands=5,
        slot_matrix=slot_matrix,
    )
    assert len(skeleton.slot_matrix) == 3
    assert skeleton.slot_matrix["common_white_creature_1"]["color"] == "W"


def test_skeleton_slot_matrix_round_trip():
    """Slot matrix survives JSON serialization."""
    slot_matrix = {
        "slot_1": {"rarity": "common", "color": "W"},
        "slot_2": {"rarity": "rare", "color": "U"},
    }
    skeleton = SetSkeleton(
        total_cards=10,
        commons=5,
        uncommons=3,
        rares=1,
        mythics=1,
        basic_lands=0,
        slot_matrix=slot_matrix,
    )
    json_str = skeleton.model_dump_json()
    restored = SetSkeleton.model_validate_json(json_str)
    assert restored.slot_matrix == slot_matrix


def test_skeleton_empty_slot_matrix():
    """Default slot_matrix is an empty dict."""
    skeleton = SetSkeleton(
        total_cards=0,
        commons=0,
        uncommons=0,
        rares=0,
        mythics=0,
        basic_lands=0,
    )
    assert skeleton.slot_matrix == {}


def test_skeleton_rarity_counts_consistency():
    """Rarity counts plus basic_lands can equal total_cards for a realistic set."""
    skeleton = SetSkeleton(
        total_cards=266,
        commons=101,
        uncommons=80,
        rares=60,
        mythics=20,
        basic_lands=5,
    )
    total = (
        skeleton.commons
        + skeleton.uncommons
        + skeleton.rares
        + skeleton.mythics
        + skeleton.basic_lands
    )
    assert total == skeleton.total_cards


# ---------------------------------------------------------------------------
# DraftArchetype — all 10 color pairs
# ---------------------------------------------------------------------------


ALL_COLOR_PAIRS = [
    ("WU", "Azorius"),
    ("WB", "Orzhov"),
    ("WR", "Boros"),
    ("WG", "Selesnya"),
    ("UB", "Dimir"),
    ("UR", "Izzet"),
    ("UG", "Simic"),
    ("BR", "Rakdos"),
    ("BG", "Golgari"),
    ("RG", "Gruul"),
]


@pytest.mark.parametrize("pair,guild", ALL_COLOR_PAIRS)
def test_all_color_pair_archetypes(pair, guild):
    """All 10 two-color draft archetypes can be created."""
    arch = DraftArchetype(
        color_pair=pair,
        name=f"{guild} Archetype",
        description=f"Draft strategy for {guild}",
    )
    assert arch.color_pair == pair
    assert guild in arch.name


def test_archetype_minimal():
    """Archetype with only required fields."""
    arch = DraftArchetype(color_pair="WU", name="Fliers", description="Fly high")
    assert arch.primary_mechanics == []
    assert arch.signpost_uncommon is None


def test_archetype_round_trip():
    """DraftArchetype survives JSON serialization."""
    arch = DraftArchetype(
        color_pair="UB",
        name="Dimir Control",
        description="Tempo and removal",
        primary_mechanics=["surveil", "tempo"],
        signpost_uncommon="Dimir Spybug",
    )
    json_str = arch.model_dump_json()
    restored = DraftArchetype.model_validate_json(json_str)
    assert restored == arch


# ---------------------------------------------------------------------------
# Set with mechanics
# ---------------------------------------------------------------------------


def test_set_with_mechanics():
    """A set can contain a list of mechanics and round-trip."""
    mechanic = Mechanic(
        name="Investigate",
        keyword_type="keyword_action",
        reminder_text="Create a Clue token.",
        rules_template="Investigate",
    )
    s = Set(
        name="Clue Set",
        code="CLU",
        theme="Mystery",
        mechanics=[mechanic],
    )
    json_str = s.model_dump_json()
    restored = Set.model_validate_json(json_str)
    assert len(restored.mechanics) == 1
    assert restored.mechanics[0].name == "Investigate"


def test_set_with_multiple_mechanics():
    """A set with several mechanics."""
    mechanics = [
        Mechanic(
            name="Investigate",
            keyword_type="keyword_action",
            reminder_text="Create a Clue token.",
            rules_template="Investigate",
        ),
        Mechanic(
            name="Delirium",
            keyword_type="ability_word",
            reminder_text="If there are four or more card types among cards in your graveyard...",
            rules_template="Delirium — [effect]",
        ),
    ]
    s = Set(name="Test", code="TST", theme="Test", mechanics=mechanics)
    assert len(s.mechanics) == 2


# ---------------------------------------------------------------------------
# Large set
# ---------------------------------------------------------------------------


def test_large_set_serialization():
    """A set with 280+ cards serializes and deserializes."""
    cards = [
        Card(
            name=f"Card {i:03d}",
            type_line="Creature",
            collector_number=f"{i:03d}",
            set_code="BIG",
            rarity=Rarity.COMMON,
        )
        for i in range(1, 285)
    ]
    s = Set(name="Big Set", code="BIG", theme="Everything", cards=cards)
    assert len(s.cards) == 284

    json_str = s.model_dump_json()
    restored = Set.model_validate_json(json_str)
    assert len(restored.cards) == 284
    assert restored.cards[0].name == "Card 001"
    assert restored.cards[-1].name == "Card 284"


# ---------------------------------------------------------------------------
# Set metadata
# ---------------------------------------------------------------------------


def test_set_version_default():
    """Default version is '0.1.0'."""
    s = Set(name="Test", code="TST", theme="Test")
    assert s.version == "0.1.0"


def test_set_custom_version():
    """Version can be set to any string."""
    s = Set(name="Test", code="TST", theme="Test", version="1.0.0-beta")
    assert s.version == "1.0.0-beta"


def test_set_timestamps():
    """Set timestamps work correctly."""
    now = datetime.now(tz=UTC)
    s = Set(
        name="Timed",
        code="TMD",
        theme="Time",
        created_at=now,
        updated_at=now,
    )
    assert s.created_at == now
    assert s.updated_at == now


def test_set_timestamps_default_none():
    """Set timestamps default to None."""
    s = Set(name="Test", code="TST", theme="Test")
    assert s.created_at is None
    assert s.updated_at is None


def test_set_empty_description():
    """Set description defaults to empty string."""
    s = Set(name="Test", code="TST", theme="Test")
    assert s.description == ""


def test_set_with_description():
    """Set description can be provided."""
    s = Set(
        name="Test",
        code="TST",
        theme="Test",
        description="A gothic horror themed set.",
    )
    assert s.description == "A gothic horror themed set."


def test_set_with_all_10_archetypes():
    """A complete set has all 10 draft archetypes."""
    archetypes = [
        DraftArchetype(
            color_pair=pair,
            name=f"{guild} Archetype",
            description=f"Strategy for {guild}",
        )
        for pair, guild in ALL_COLOR_PAIRS
    ]
    s = Set(
        name="Full Draft",
        code="FDR",
        theme="Draft",
        draft_archetypes=archetypes,
    )
    assert len(s.draft_archetypes) == 10
    pairs = {a.color_pair for a in s.draft_archetypes}
    assert len(pairs) == 10
