"""Tests for enum values and completeness."""

from mtgai.models.enums import CardLayout, CardStatus, CardType, Color, Rarity, Supertype


def test_color_values():
    """All five MTG colors are present with correct abbreviations."""
    assert Color.WHITE == "W"
    assert Color.BLUE == "U"
    assert Color.BLACK == "B"
    assert Color.RED == "R"
    assert Color.GREEN == "G"
    assert len(Color) == 5


def test_rarity_values():
    """All four rarities are present."""
    assert Rarity.COMMON == "common"
    assert Rarity.UNCOMMON == "uncommon"
    assert Rarity.RARE == "rare"
    assert Rarity.MYTHIC == "mythic"
    assert len(Rarity) == 4


def test_card_type_values():
    """All primary card types are present."""
    assert CardType.CREATURE == "Creature"
    assert CardType.INSTANT == "Instant"
    assert CardType.SORCERY == "Sorcery"
    assert CardType.ENCHANTMENT == "Enchantment"
    assert CardType.ARTIFACT == "Artifact"
    assert CardType.PLANESWALKER == "Planeswalker"
    assert CardType.LAND == "Land"
    assert len(CardType) == 7


def test_card_status_values():
    """All pipeline statuses exist."""
    assert CardStatus.DRAFT == "draft"
    assert CardStatus.VALIDATED == "validated"
    assert CardStatus.APPROVED == "approved"
    assert CardStatus.ART_GENERATED == "art_generated"
    assert CardStatus.RENDERED == "rendered"
    assert CardStatus.PRINT_READY == "print_ready"
    assert len(CardStatus) == 6


def test_card_layout_values():
    """Layout types match Scryfall's layout field values."""
    assert CardLayout.NORMAL == "normal"
    assert CardLayout.TRANSFORM == "transform"
    assert CardLayout.MODAL_DFC == "modal_dfc"
    assert CardLayout.SAGA == "saga"
    assert CardLayout.ADVENTURE == "adventure"
    assert CardLayout.SPLIT == "split"


def test_supertype_values():
    """Supertypes are present."""
    assert Supertype.LEGENDARY == "Legendary"
    assert Supertype.BASIC == "Basic"
    assert Supertype.SNOW == "Snow"
