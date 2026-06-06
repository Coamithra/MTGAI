"""Enumerations for card attributes, pipeline status, and layout types."""

from enum import StrEnum


class Color(StrEnum):
    WHITE = "W"
    BLUE = "U"
    BLACK = "B"
    RED = "R"
    GREEN = "G"

    @classmethod
    def coerce(cls, value: object) -> "Color":
        """Map a canonical WUBRG letter OR a full color name to a ``Color``.

        Card JSON is sometimes persisted with full color names (``"blue"``,
        ``"White"``) instead of the Scryfall-canonical single letter. Both are
        accepted here, case-insensitively, and normalized to the letter — so
        ``"blue"`` and ``"u"`` both yield ``Color.BLUE`` (``"U"``). Already-canonical
        ``Color`` instances pass through. Raises ``ValueError`` on anything else.
        """
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"invalid color: {value!r}")
        text = value.strip()
        # Canonical letter (case-insensitive: 'U' / 'u').
        try:
            return cls(text.upper())
        except ValueError:
            pass
        # Full color name (case-insensitive: 'blue' / 'Blue').
        named = _COLOR_NAME_TO_LETTER.get(text.lower())
        if named is not None:
            return cls(named)
        raise ValueError(f"invalid color: {value!r}")


_COLOR_NAME_TO_LETTER: dict[str, str] = {
    "white": "W",
    "blue": "U",
    "black": "B",
    "red": "R",
    "green": "G",
}


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
