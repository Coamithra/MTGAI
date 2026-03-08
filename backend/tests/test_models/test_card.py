"""Tests for Card model creation, serialization, and Scryfall compatibility."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from mtgai.models.card import Card, CardFace, GenerationAttempt, ManaCost
from mtgai.models.enums import CardLayout, CardStatus, Color, Rarity

# ---------------------------------------------------------------------------
# Basic creation and round-trip
# ---------------------------------------------------------------------------


def test_card_creation_minimal():
    """A card can be created with just name and type_line."""
    card = Card(name="Lightning Bolt", type_line="Instant")
    assert card.name == "Lightning Bolt"
    assert card.status == CardStatus.DRAFT
    assert card.cmc == 0.0
    assert card.colors == []


def test_card_creation_full(sample_creature):
    """A card with all fields populated round-trips through JSON."""
    json_str = sample_creature.model_dump_json()
    round_tripped = Card.model_validate_json(json_str)
    assert round_tripped == sample_creature
    assert round_tripped.name == "Serra Angel"
    assert round_tripped.power == "4"
    assert round_tripped.toughness == "4"


def test_card_scryfall_field_names():
    """Verify we use Scryfall-compatible field names."""
    card = Card(name="Test", type_line="Creature")
    data = card.model_dump()
    assert "oracle_text" in data
    assert "color_identity" in data
    assert "collector_number" in data
    assert "type_line" in data
    assert "mana_cost" in data
    assert "cmc" in data
    assert "colors" in data
    assert "rarity" in data
    assert "layout" in data
    assert "card_faces" in data


def test_planeswalker_card(sample_planeswalker):
    """Planeswalker cards have loyalty but no power/toughness."""
    assert sample_planeswalker.loyalty == "3"
    assert sample_planeswalker.power is None
    assert sample_planeswalker.toughness is None


def test_double_faced_card(sample_dfc):
    """DFC cards have card_faces."""
    assert sample_dfc.layout == CardLayout.TRANSFORM
    assert sample_dfc.card_faces is not None
    assert len(sample_dfc.card_faces) == 2
    assert sample_dfc.card_faces[0].name == "Daybound Wolf"
    assert sample_dfc.card_faces[1].power == "4"


def test_dfc_round_trip(sample_dfc):
    """DFC cards survive JSON round-trip."""
    json_str = sample_dfc.model_dump_json()
    round_tripped = Card.model_validate_json(json_str)
    assert round_tripped.card_faces is not None
    assert len(round_tripped.card_faces) == 2
    assert round_tripped.card_faces[0].name == "Daybound Wolf"


def test_default_status_is_draft():
    """New cards default to DRAFT status."""
    card = Card(name="Test", type_line="Instant")
    assert card.status == CardStatus.DRAFT


def test_card_with_all_colors():
    """A five-color card."""
    card = Card(
        name="WUBRG Card",
        type_line="Sorcery",
        colors=[Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN],
    )
    assert len(card.colors) == 5


def test_colorless_card():
    """An artifact with no colors."""
    card = Card(
        name="Sol Ring",
        type_line="Artifact",
        mana_cost="{1}",
        cmc=1.0,
        colors=[],
    )
    assert card.colors == []


def test_card_design_metadata():
    """Pipeline-specific fields are present."""
    card = Card(
        name="Test",
        type_line="Creature",
        draft_archetype="WU_fliers",
        mechanic_tags=["investigate", "flying"],
        slot_id="common_white_creature_2cmc_01",
        design_notes="A simple common flier for the WU archetype.",
        is_reprint=False,
    )
    assert card.draft_archetype == "WU_fliers"
    assert "investigate" in card.mechanic_tags
    assert card.slot_id is not None


# ---------------------------------------------------------------------------
# Enum enforcement — invalid values must be rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_rarity", ["legendary", "special", "COMMON", "0", ""])
def test_invalid_rarity_rejected(bad_rarity):
    """Pydantic rejects invalid rarity strings."""
    with pytest.raises(ValidationError):
        Card(name="Bad", type_line="Instant", rarity=bad_rarity)


@pytest.mark.parametrize("bad_color", ["X", "white", "w", "1", ""])
def test_invalid_color_rejected(bad_color):
    """Pydantic rejects invalid color values in the colors list."""
    with pytest.raises(ValidationError):
        Card(name="Bad", type_line="Instant", colors=[bad_color])


@pytest.mark.parametrize("bad_status", ["pending", "deleted", "DRAFT", "1", ""])
def test_invalid_status_rejected(bad_status):
    """Pydantic rejects invalid status values."""
    with pytest.raises(ValidationError):
        Card(name="Bad", type_line="Instant", status=bad_status)


@pytest.mark.parametrize("bad_layout", ["double_faced", "flip", "NORMAL", ""])
def test_invalid_layout_rejected(bad_layout):
    """Pydantic rejects invalid layout values."""
    with pytest.raises(ValidationError):
        Card(name="Bad", type_line="Instant", layout=bad_layout)


# ---------------------------------------------------------------------------
# ManaCost model
# ---------------------------------------------------------------------------


def test_manacost_simple():
    """A plain white mana cost."""
    mc = ManaCost(raw="{W}", cmc=1.0, colors=[Color.WHITE], white=1)
    assert mc.raw == "{W}"
    assert mc.cmc == 1.0
    assert mc.white == 1
    assert mc.generic == 0
    assert mc.x_count == 0


def test_manacost_generic_plus_colors():
    """A mana cost like {2}{W}{U}."""
    mc = ManaCost(
        raw="{2}{W}{U}",
        cmc=4.0,
        colors=[Color.WHITE, Color.BLUE],
        generic=2,
        white=1,
        blue=1,
    )
    assert mc.cmc == 4.0
    assert mc.generic == 2
    assert len(mc.colors) == 2


def test_manacost_empty():
    """A card with no mana cost (e.g. a land)."""
    mc = ManaCost(raw="", cmc=0.0)
    assert mc.raw == ""
    assert mc.colors == []
    assert mc.cmc == 0.0


def test_manacost_x_cost():
    """A mana cost containing X."""
    mc = ManaCost(raw="{X}{R}", cmc=1.0, colors=[Color.RED], red=1, x_count=1)
    assert mc.x_count == 1
    assert mc.red == 1


def test_manacost_colorless():
    """A mana cost with only colorless mana."""
    mc = ManaCost(raw="{3}", cmc=3.0, generic=3)
    assert mc.colorless == 0
    assert mc.generic == 3
    assert mc.colors == []


def test_manacost_round_trip():
    """ManaCost survives JSON round-trip."""
    mc = ManaCost(
        raw="{1}{B}{G}",
        cmc=3.0,
        colors=[Color.BLACK, Color.GREEN],
        generic=1,
        black=1,
        green=1,
    )
    json_str = mc.model_dump_json()
    restored = ManaCost.model_validate_json(json_str)
    assert restored == mc


def test_manacost_all_colors():
    """A ManaCost using all five colors."""
    mc = ManaCost(
        raw="{W}{U}{B}{R}{G}",
        cmc=5.0,
        colors=[Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN],
        white=1,
        blue=1,
        black=1,
        red=1,
        green=1,
    )
    assert len(mc.colors) == 5
    assert mc.cmc == 5.0


def test_card_with_parsed_manacost():
    """Card can embed a parsed ManaCost object."""
    mc = ManaCost(raw="{1}{R}", cmc=2.0, colors=[Color.RED], generic=1, red=1)
    card = Card(name="Shock", type_line="Instant", mana_cost="{1}{R}", mana_cost_parsed=mc)
    assert card.mana_cost_parsed is not None
    assert card.mana_cost_parsed.red == 1
    # Round-trip
    restored = Card.model_validate_json(card.model_dump_json())
    assert restored.mana_cost_parsed is not None
    assert restored.mana_cost_parsed.red == 1


# ---------------------------------------------------------------------------
# GenerationAttempt
# ---------------------------------------------------------------------------


def test_generation_attempt_creation():
    """A generation attempt with all fields."""
    now = datetime.now(tz=UTC)
    ga = GenerationAttempt(
        attempt_number=1,
        timestamp=now,
        prompt_used="Generate a creature",
        model_used="claude-sonnet-4-20250514",
        success=True,
        input_tokens=500,
        output_tokens=200,
        cost_usd=0.0035,
        prompt_version="v1.2",
    )
    assert ga.attempt_number == 1
    assert ga.success is True
    assert ga.input_tokens == 500
    assert ga.output_tokens == 200
    assert ga.cost_usd == pytest.approx(0.0035)
    assert ga.prompt_version == "v1.2"


def test_generation_attempt_failure():
    """A failed generation attempt has error_message and validation_errors."""
    ga = GenerationAttempt(
        attempt_number=2,
        timestamp=datetime.now(tz=UTC),
        success=False,
        error_message="Rate limit exceeded",
        validation_errors=["Missing oracle_text", "Invalid mana cost"],
    )
    assert ga.success is False
    assert ga.error_message == "Rate limit exceeded"
    assert len(ga.validation_errors) == 2


def test_generation_attempt_round_trip():
    """GenerationAttempt survives JSON round-trip."""
    ga = GenerationAttempt(
        attempt_number=1,
        timestamp=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
        prompt_used="test prompt",
        model_used="test-model",
        success=True,
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.001,
    )
    json_str = ga.model_dump_json()
    restored = GenerationAttempt.model_validate_json(json_str)
    assert restored.attempt_number == ga.attempt_number
    assert restored.cost_usd == pytest.approx(ga.cost_usd)


def test_generation_attempt_minimal():
    """A generation attempt with only required fields."""
    ga = GenerationAttempt(
        attempt_number=1,
        timestamp=datetime.now(tz=UTC),
        success=True,
    )
    assert ga.prompt_used is None
    assert ga.model_used is None
    assert ga.error_message is None
    assert ga.input_tokens is None
    assert ga.output_tokens is None
    assert ga.cost_usd is None
    assert ga.validation_errors == []


def test_card_with_generation_attempts():
    """Card tracks multiple generation attempts."""
    attempts = [
        GenerationAttempt(
            attempt_number=1,
            timestamp=datetime.now(tz=UTC),
            success=False,
            error_message="bad output",
        ),
        GenerationAttempt(
            attempt_number=2,
            timestamp=datetime.now(tz=UTC),
            success=True,
            input_tokens=400,
            output_tokens=300,
            cost_usd=0.005,
        ),
    ]
    card = Card(
        name="Test Card",
        type_line="Creature",
        generation_attempts=attempts,
    )
    assert len(card.generation_attempts) == 2
    assert card.generation_attempts[0].success is False
    assert card.generation_attempts[1].success is True
    assert card.generation_attempts[1].cost_usd == pytest.approx(0.005)


# ---------------------------------------------------------------------------
# CardFace
# ---------------------------------------------------------------------------


def test_card_face_standalone():
    """A CardFace can be created on its own."""
    face = CardFace(
        name="Front Face",
        type_line="Creature — Human",
        oracle_text="Lifelink",
        power="2",
        toughness="3",
        colors=[Color.WHITE],
    )
    assert face.name == "Front Face"
    assert face.power == "2"
    assert face.colors == [Color.WHITE]


def test_card_face_minimal():
    """A CardFace with only required fields."""
    face = CardFace(name="Simple Face", type_line="Instant")
    assert face.mana_cost is None
    assert face.oracle_text == ""
    assert face.flavor_text is None
    assert face.power is None
    assert face.toughness is None
    assert face.loyalty is None
    assert face.colors == []
    assert face.art_path is None
    assert face.art_prompt is None


def test_card_face_all_fields():
    """A CardFace with every optional field populated."""
    face = CardFace(
        name="Full Face",
        mana_cost="{2}{B}{B}",
        type_line="Creature — Zombie",
        oracle_text="Deathtouch\nWhen this creature dies, draw a card.",
        flavor_text="The dead walk among us.",
        power="3",
        toughness="2",
        loyalty=None,
        colors=[Color.BLACK],
        art_path="art/full_face_v1.png",
        art_prompt="A zombie rising from a swamp",
    )
    assert face.flavor_text is not None
    assert face.art_path == "art/full_face_v1.png"


def test_card_face_round_trip():
    """CardFace round-trips through JSON."""
    face = CardFace(
        name="Test Face",
        mana_cost="{1}{R}",
        type_line="Instant",
        oracle_text="Deal 3 damage.",
        flavor_text="Burn them all.",
        colors=[Color.RED],
    )
    json_str = face.model_dump_json()
    restored = CardFace.model_validate_json(json_str)
    assert restored == face


# ---------------------------------------------------------------------------
# Edge cases: names
# ---------------------------------------------------------------------------


def test_empty_name_allowed():
    """An empty name string is technically valid for the model."""
    card = Card(name="", type_line="Instant")
    assert card.name == ""


def test_very_long_card_name():
    """Names over 100 characters are accepted by the model."""
    long_name = "A" * 150
    card = Card(name=long_name, type_line="Creature")
    assert len(card.name) == 150


@pytest.mark.parametrize(
    "name",
    [
        "Serra's Angel",
        "Korvold, Fae-Cursed King",
        "Nicol Bolas, Dragon-God",
        "Fire // Ice",
        "Lim-Dul's Vault",
        "Look at Me, I'm the DCI",
        "Who / What / When / Where / Why",
    ],
)
def test_special_characters_in_names(name):
    """Card names with apostrophes, commas, colons, slashes, hyphens."""
    card = Card(name=name, type_line="Creature")
    json_str = card.model_dump_json()
    restored = Card.model_validate_json(json_str)
    assert restored.name == name


def test_unicode_in_flavor_text():
    """Unicode characters in flavor text survive serialization."""
    card = Card(
        name="Test",
        type_line="Creature",
        flavor_text="\u2014 Jace Beleren\n\u201cThe mind is a terrible thing to waste.\u201d",
    )
    json_str = card.model_dump_json()
    restored = Card.model_validate_json(json_str)
    assert "\u2014" in restored.flavor_text
    assert "\u201c" in restored.flavor_text


def test_em_dash_in_type_line():
    """The em-dash separator in type_lines round-trips correctly."""
    card = Card(name="Test", type_line="Creature \u2014 Human Wizard")
    restored = Card.model_validate_json(card.model_dump_json())
    assert "\u2014" in restored.type_line


# ---------------------------------------------------------------------------
# Null / optional field handling
# ---------------------------------------------------------------------------


def test_all_optional_fields_none():
    """A card with only required fields has None for all optional fields."""
    card = Card(name="Minimal", type_line="Instant")
    assert card.id is None
    assert card.mana_cost is None
    assert card.mana_cost_parsed is None
    assert card.flavor_text is None
    assert card.reminder_text is None
    assert card.power is None
    assert card.toughness is None
    assert card.loyalty is None
    assert card.art_path is None
    assert card.render_path is None
    assert card.art_prompt is None
    assert card.design_notes is None
    assert card.scryfall_id is None
    assert card.draft_archetype is None
    assert card.slot_id is None
    assert card.card_faces is None
    assert card.created_at is None
    assert card.updated_at is None


def test_explicit_none_vs_default():
    """Explicitly setting None matches the default."""
    card_default = Card(name="Test", type_line="Instant")
    card_explicit = Card(
        name="Test",
        type_line="Instant",
        mana_cost=None,
        power=None,
        toughness=None,
        flavor_text=None,
    )
    assert card_default.mana_cost == card_explicit.mana_cost
    assert card_default.power == card_explicit.power


# ---------------------------------------------------------------------------
# List fields: empty vs populated
# ---------------------------------------------------------------------------


def test_empty_list_fields():
    """Default list fields are empty lists, not None."""
    card = Card(name="Test", type_line="Instant")
    assert card.colors == []
    assert card.color_identity == []
    assert card.supertypes == []
    assert card.card_types == []
    assert card.subtypes == []
    assert card.mechanic_tags == []
    assert card.generation_attempts == []
    assert card.art_generation_attempts == []
    assert card.render_attempts == []


def test_populated_list_fields():
    """List fields retain their values after creation."""
    card = Card(
        name="Test",
        type_line="Creature — Human Wizard",
        colors=[Color.BLUE, Color.RED],
        color_identity=[Color.BLUE, Color.RED],
        supertypes=["Legendary"],
        card_types=["Creature"],
        subtypes=["Human", "Wizard"],
        mechanic_tags=["prowess", "spellslinger"],
    )
    assert len(card.colors) == 2
    assert len(card.subtypes) == 2
    assert "prowess" in card.mechanic_tags


# ---------------------------------------------------------------------------
# Timestamp fields
# ---------------------------------------------------------------------------


def test_timestamps_with_real_datetimes():
    """Timestamps accept real datetime objects."""
    now = datetime.now(tz=UTC)
    card = Card(
        name="Timestamped",
        type_line="Instant",
        created_at=now,
        updated_at=now,
    )
    assert card.created_at == now
    assert card.updated_at == now


def test_timestamps_default_none():
    """Timestamps default to None."""
    card = Card(name="Test", type_line="Instant")
    assert card.created_at is None
    assert card.updated_at is None


def test_timestamps_round_trip():
    """Datetime timestamps survive JSON serialization."""
    now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
    card = Card(name="Test", type_line="Instant", created_at=now)
    restored = Card.model_validate_json(card.model_dump_json())
    assert restored.created_at is not None
    assert restored.created_at.year == 2025
    assert restored.created_at.month == 6


# ---------------------------------------------------------------------------
# model_copy updates
# ---------------------------------------------------------------------------


def test_model_copy_single_field():
    """model_copy can update a single field."""
    card = Card(name="Original", type_line="Instant")
    updated = card.model_copy(update={"name": "Updated"})
    assert updated.name == "Updated"
    assert card.name == "Original"


def test_model_copy_multiple_fields():
    """model_copy can update multiple fields at once."""
    card = Card(name="Test", type_line="Instant", rarity=Rarity.COMMON)
    updated = card.model_copy(
        update={
            "name": "New Name",
            "rarity": Rarity.RARE,
            "status": CardStatus.VALIDATED,
            "mana_cost": "{2}{U}",
        }
    )
    assert updated.name == "New Name"
    assert updated.rarity == Rarity.RARE
    assert updated.status == CardStatus.VALIDATED
    assert updated.mana_cost == "{2}{U}"
    # Original unchanged
    assert card.name == "Test"
    assert card.rarity == Rarity.COMMON
    assert card.status == CardStatus.DRAFT
    assert card.mana_cost is None


def test_model_copy_preserves_other_fields():
    """model_copy only changes specified fields."""
    card = Card(
        name="Test",
        type_line="Creature",
        mana_cost="{1}{G}",
        colors=[Color.GREEN],
        oracle_text="Trample",
    )
    updated = card.model_copy(update={"status": CardStatus.APPROVED})
    assert updated.mana_cost == "{1}{G}"
    assert updated.colors == [Color.GREEN]
    assert updated.oracle_text == "Trample"


# ---------------------------------------------------------------------------
# Rarity values via parametrize
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rarity",
    [Rarity.COMMON, Rarity.UNCOMMON, Rarity.RARE, Rarity.MYTHIC],
)
def test_all_valid_rarities(rarity):
    """All rarity enum members can be assigned to a card."""
    card = Card(name="Test", type_line="Instant", rarity=rarity)
    assert card.rarity == rarity


# ---------------------------------------------------------------------------
# Layout values via parametrize
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "layout",
    [
        CardLayout.NORMAL,
        CardLayout.SPLIT,
        CardLayout.MODAL_DFC,
        CardLayout.TRANSFORM,
        CardLayout.SAGA,
        CardLayout.ADVENTURE,
    ],
)
def test_all_valid_layouts(layout):
    """All layout enum members can be assigned to a card."""
    card = Card(name="Test", type_line="Instant", layout=layout)
    assert card.layout == layout
