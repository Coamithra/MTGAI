"""Enumerations for card attributes, pipeline status, and layout types."""

from enum import StrEnum


class Color(StrEnum):
    WHITE = "W"
    BLUE = "U"
    BLACK = "B"
    RED = "R"
    GREEN = "G"


class Rarity(StrEnum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    MYTHIC = "mythic"


class CardType(StrEnum):
    """Primary card types (supertypes and subtypes are separate fields)."""

    CREATURE = "Creature"
    INSTANT = "Instant"
    SORCERY = "Sorcery"
    ENCHANTMENT = "Enchantment"
    ARTIFACT = "Artifact"
    PLANESWALKER = "Planeswalker"
    LAND = "Land"


class Supertype(StrEnum):
    LEGENDARY = "Legendary"
    BASIC = "Basic"
    SNOW = "Snow"
    WORLD = "World"


class CardStatus(StrEnum):
    """Pipeline status for a card. Transitions are forward-only (with manual override)."""

    DRAFT = "draft"
    VALIDATED = "validated"
    APPROVED = "approved"
    ART_GENERATED = "art_generated"
    RENDERED = "rendered"
    PRINT_READY = "print_ready"


class CardLayout(StrEnum):
    """Card layout type. Maps to Scryfall's 'layout' field."""

    NORMAL = "normal"
    SPLIT = "split"
    MODAL_DFC = "modal_dfc"
    TRANSFORM = "transform"
    SAGA = "saga"
    ADVENTURE = "adventure"
