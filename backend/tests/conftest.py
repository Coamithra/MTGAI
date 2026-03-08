"""Shared test fixtures for sample cards and sets."""

import pytest

from mtgai.models.card import Card, CardFace
from mtgai.models.enums import CardLayout, Color, Rarity
from mtgai.models.mechanic import Mechanic
from mtgai.models.set import DraftArchetype, Set, SetSkeleton


@pytest.fixture
def sample_creature() -> Card:
    """A standard creature card (Serra Angel)."""
    return Card(
        name="Serra Angel",
        mana_cost="{3}{W}{W}",
        cmc=5.0,
        type_line="Creature — Angel",
        oracle_text="Flying, vigilance",
        power="4",
        toughness="4",
        rarity=Rarity.UNCOMMON,
        colors=[Color.WHITE],
        color_identity=[Color.WHITE],
        collector_number="034",
        set_code="TST",
        supertypes=[],
        card_types=["Creature"],
        subtypes=["Angel"],
    )


@pytest.fixture
def sample_instant() -> Card:
    """A simple instant card (Lightning Bolt)."""
    return Card(
        name="Lightning Bolt",
        mana_cost="{R}",
        cmc=1.0,
        type_line="Instant",
        oracle_text="Lightning Bolt deals 3 damage to any target.",
        rarity=Rarity.COMMON,
        colors=[Color.RED],
        color_identity=[Color.RED],
        collector_number="141",
        set_code="TST",
        card_types=["Instant"],
    )


@pytest.fixture
def sample_planeswalker() -> Card:
    """A planeswalker card."""
    return Card(
        name="Jace, Test Subject",
        mana_cost="{1}{U}{U}",
        cmc=3.0,
        type_line="Legendary Planeswalker — Jace",
        oracle_text=(
            "+1: Draw a card.\n"
            "-3: Return target creature to its owner's hand.\n"
            "-7: You draw seven cards."
        ),
        loyalty="3",
        rarity=Rarity.MYTHIC,
        colors=[Color.BLUE],
        color_identity=[Color.BLUE],
        collector_number="058",
        set_code="TST",
        supertypes=["Legendary"],
        card_types=["Planeswalker"],
        subtypes=["Jace"],
    )


@pytest.fixture
def sample_dfc() -> Card:
    """A double-faced (transform) card."""
    return Card(
        name="Daybound Wolf // Nightbound Terror",
        type_line="Creature — Wolf // Creature — Werewolf",
        layout=CardLayout.TRANSFORM,
        rarity=Rarity.UNCOMMON,
        set_code="TST",
        collector_number="200",
        card_faces=[
            CardFace(
                name="Daybound Wolf",
                mana_cost="{1}{G}",
                type_line="Creature — Wolf",
                oracle_text="Daybound",
                power="2",
                toughness="2",
                colors=[Color.GREEN],
            ),
            CardFace(
                name="Nightbound Terror",
                type_line="Creature — Werewolf",
                oracle_text="Nightbound",
                power="4",
                toughness="4",
                colors=[Color.GREEN],
            ),
        ],
    )


@pytest.fixture
def sample_mechanic() -> Mechanic:
    """A set-specific mechanic."""
    return Mechanic(
        name="Investigate",
        keyword_type="keyword_action",
        reminder_text=(
            "(Create a Clue token. It's an artifact with "
            '"{2}, Sacrifice this artifact: Draw a card.")'
        ),
        rules_template="Investigate",
        description="Create Clue tokens for card advantage",
        colors=[Color.WHITE, Color.BLUE, Color.GREEN],
        allowed_rarities=[Rarity.COMMON, Rarity.UNCOMMON, Rarity.RARE],
    )


@pytest.fixture
def sample_set(sample_creature: Card, sample_instant: Card) -> Set:
    """A minimal test set."""
    return Set(
        name="Test Set",
        code="TST",
        theme="Testing",
        description="A set used for unit testing.",
        cards=[sample_creature, sample_instant],
        skeleton=SetSkeleton(
            total_cards=280,
            commons=101,
            uncommons=80,
            rares=60,
            mythics=20,
            basic_lands=5,
        ),
        draft_archetypes=[
            DraftArchetype(
                color_pair="WU",
                name="Azorius Fliers",
                description="Evasive creatures with tempo support",
            ),
        ],
    )
