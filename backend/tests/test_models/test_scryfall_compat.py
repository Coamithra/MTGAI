"""Integration tests: load real Scryfall card data and verify compatibility with our Card model.

Uses actual card data from research/raw-data/dsk/cards.json (and lci for DFCs).
"""

import json
from pathlib import Path

import pytest

from mtgai.models.card import Card, CardFace
from mtgai.models.enums import CardLayout, Color, Rarity

# Paths to real Scryfall data files
_RAW_DATA = Path(__file__).parent.parent.parent.parent / "research" / "raw-data"
DSK_CARDS_PATH = _RAW_DATA / "dsk" / "cards.json"
LCI_CARDS_PATH = _RAW_DATA / "lci" / "cards.json"


def _load_scryfall(path: Path) -> list[dict]:
    """Load Scryfall cards from a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def _scryfall_to_card(sc: dict) -> Card:
    """Map overlapping fields from a Scryfall card dict to our Card model.

    Only maps fields that exist in both models. Scryfall-only fields are ignored.
    """
    color_map = {
        "W": Color.WHITE,
        "U": Color.BLUE,
        "B": Color.BLACK,
        "R": Color.RED,
        "G": Color.GREEN,
    }
    layout_map = {
        "normal": CardLayout.NORMAL,
        "transform": CardLayout.TRANSFORM,
        "modal_dfc": CardLayout.MODAL_DFC,
        "split": CardLayout.SPLIT,
        "saga": CardLayout.SAGA,
        "adventure": CardLayout.ADVENTURE,
    }
    rarity_map = {
        "common": Rarity.COMMON,
        "uncommon": Rarity.UNCOMMON,
        "rare": Rarity.RARE,
        "mythic": Rarity.MYTHIC,
    }

    layout_str = sc.get("layout", "normal")
    layout = layout_map.get(layout_str, CardLayout.NORMAL)

    colors = [color_map[c] for c in sc.get("colors", []) if c in color_map]
    color_identity = [color_map[c] for c in sc.get("color_identity", []) if c in color_map]
    rarity = rarity_map.get(sc.get("rarity", "common"), Rarity.COMMON)

    # Build card_faces if present
    card_faces = None
    if sc.get("card_faces"):
        card_faces = []
        for face in sc["card_faces"]:
            face_colors = [color_map[c] for c in face.get("colors", []) if c in color_map]
            card_faces.append(
                CardFace(
                    name=face.get("name", ""),
                    mana_cost=face.get("mana_cost"),
                    type_line=face.get("type_line", ""),
                    oracle_text=face.get("oracle_text", ""),
                    flavor_text=face.get("flavor_text"),
                    power=face.get("power"),
                    toughness=face.get("toughness"),
                    loyalty=face.get("loyalty"),
                    colors=face_colors,
                )
            )

    return Card(
        name=sc.get("name", ""),
        layout=layout,
        mana_cost=sc.get("mana_cost"),
        cmc=sc.get("cmc", 0.0),
        colors=colors,
        color_identity=color_identity,
        type_line=sc.get("type_line", ""),
        oracle_text=sc.get("oracle_text", ""),
        flavor_text=sc.get("flavor_text"),
        power=sc.get("power"),
        toughness=sc.get("toughness"),
        loyalty=sc.get("loyalty"),
        collector_number=sc.get("collector_number", ""),
        rarity=rarity,
        set_code=sc.get("set", ""),
        artist=sc.get("artist", "AI Generated"),
        card_faces=card_faces,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dsk_cards() -> list[dict]:
    if not DSK_CARDS_PATH.exists():
        pytest.skip("DSK Scryfall data not available")
    return _load_scryfall(DSK_CARDS_PATH)


@pytest.fixture(scope="module")
def lci_cards() -> list[dict]:
    if not LCI_CARDS_PATH.exists():
        pytest.skip("LCI Scryfall data not available")
    return _load_scryfall(LCI_CARDS_PATH)


# ---------------------------------------------------------------------------
# Load and map real cards
# ---------------------------------------------------------------------------


def test_load_real_creature(dsk_cards):
    """A real creature from DSK can be mapped to our Card model."""
    creature = next(
        (
            c
            for c in dsk_cards
            if "Creature" in c.get("type_line", "") and c.get("layout") == "normal"
        ),
        None,
    )
    assert creature is not None, "No creature found in DSK data"
    card = _scryfall_to_card(creature)
    assert card.name != ""
    assert "Creature" in card.type_line
    assert card.power is not None
    assert card.toughness is not None


def test_load_real_instant(dsk_cards):
    """A real instant from DSK can be mapped to our Card model."""
    instant = next(
        (
            c
            for c in dsk_cards
            if "Instant" in c.get("type_line", "") and c.get("layout") == "normal"
        ),
        None,
    )
    assert instant is not None, "No instant found in DSK data"
    card = _scryfall_to_card(instant)
    assert "Instant" in card.type_line
    assert card.power is None
    assert card.toughness is None


def test_load_real_sorcery(dsk_cards):
    """A real sorcery from DSK can be mapped."""
    sorcery = next(
        (
            c
            for c in dsk_cards
            if "Sorcery" in c.get("type_line", "") and c.get("layout") == "normal"
        ),
        None,
    )
    assert sorcery is not None
    card = _scryfall_to_card(sorcery)
    assert "Sorcery" in card.type_line


def test_load_real_enchantment(dsk_cards):
    """A real enchantment from DSK can be mapped."""
    enchantment = next(
        (
            c
            for c in dsk_cards
            if "Enchantment" in c.get("type_line", "")
            and "Creature" not in c.get("type_line", "")
            and c.get("layout") == "normal"
        ),
        None,
    )
    assert enchantment is not None
    card = _scryfall_to_card(enchantment)
    assert "Enchantment" in card.type_line


def test_load_real_artifact(dsk_cards):
    """A real artifact from DSK can be mapped."""
    artifact = next(
        (
            c
            for c in dsk_cards
            if "Artifact" in c.get("type_line", "")
            and "Creature" not in c.get("type_line", "")
            and c.get("layout") == "normal"
        ),
        None,
    )
    assert artifact is not None
    card = _scryfall_to_card(artifact)
    assert "Artifact" in card.type_line


def test_load_real_land(dsk_cards):
    """A real land from DSK can be mapped."""
    land = next(
        (
            c
            for c in dsk_cards
            if "Land" in c.get("type_line", "")
            and "Basic" not in c.get("type_line", "")
            and c.get("layout") == "normal"
        ),
        None,
    )
    assert land is not None
    card = _scryfall_to_card(land)
    assert "Land" in card.type_line
    assert card.mana_cost is None or card.cmc == 0.0


def test_load_real_dfc(lci_cards):
    """A real transform DFC from LCI can be mapped with card_faces."""
    dfc = next(
        (c for c in lci_cards if c.get("layout") == "transform"),
        None,
    )
    assert dfc is not None, "No transform DFC found in LCI data"
    card = _scryfall_to_card(dfc)
    assert card.layout == CardLayout.TRANSFORM
    assert card.card_faces is not None
    assert len(card.card_faces) == 2
    assert card.card_faces[0].name != ""
    assert card.card_faces[1].name != ""


# ---------------------------------------------------------------------------
# Field name compatibility
# ---------------------------------------------------------------------------


# Fields that are always present on every Scryfall card object (top-level)
UNIVERSAL_SHARED_FIELDS = [
    "name",
    "cmc",
    "colors",
    "color_identity",
    "type_line",
    "collector_number",
    "rarity",
    "layout",
    "artist",
]

# Fields only present on some card types (creature has power/toughness, etc.)
CONDITIONAL_SHARED_FIELDS = [
    "mana_cost",
    "oracle_text",
    "flavor_text",
    "power",
    "toughness",
    "loyalty",
]


def test_universal_field_names_exist_in_scryfall(dsk_cards):
    """Our universal shared field names match Scryfall's for all cards."""
    sample = dsk_cards[0]
    scryfall_keys = set(sample.keys())
    for field in UNIVERSAL_SHARED_FIELDS:
        assert field in scryfall_keys, f"Field '{field}' not found in Scryfall data"


def test_conditional_fields_exist_on_relevant_cards(dsk_cards):
    """Conditional fields (power, toughness, etc.) exist on the right card types."""
    # Find a creature to check power/toughness
    creature = next(
        (
            c
            for c in dsk_cards
            if "Creature" in c.get("type_line", "") and c.get("layout") == "normal"
        ),
        None,
    )
    assert creature is not None
    assert "power" in creature
    assert "toughness" in creature


def test_shared_field_names_exist_in_card_model():
    """All shared field names exist in our Card model."""
    card = Card(name="Test", type_line="Instant")
    model_fields = set(card.model_dump().keys())
    for field in UNIVERSAL_SHARED_FIELDS + CONDITIONAL_SHARED_FIELDS:
        assert field in model_fields, f"Field '{field}' not found in Card model"


# ---------------------------------------------------------------------------
# Rarity distribution in real data
# ---------------------------------------------------------------------------


def test_rarity_distribution(dsk_cards):
    """Real data contains all expected rarity values."""
    rarities = {c.get("rarity") for c in dsk_cards}
    assert "common" in rarities
    assert "uncommon" in rarities
    assert "rare" in rarities
    assert "mythic" in rarities


def test_rarity_distribution_counts(dsk_cards):
    """Real set has reasonable rarity distribution (more commons than mythics)."""
    from collections import Counter

    counts = Counter(c.get("rarity") for c in dsk_cards)
    assert counts["common"] > counts["mythic"]
    assert counts["uncommon"] > counts["mythic"]


# ---------------------------------------------------------------------------
# Round-trip real cards through our model
# ---------------------------------------------------------------------------


def test_real_card_round_trip(dsk_cards):
    """A real Scryfall card mapped to our model survives JSON round-trip."""
    sc = dsk_cards[0]
    card = _scryfall_to_card(sc)
    json_str = card.model_dump_json()
    restored = Card.model_validate_json(json_str)
    assert restored.name == card.name
    assert restored.type_line == card.type_line
    assert restored.rarity == card.rarity


def test_multiple_real_cards_round_trip(dsk_cards):
    """First 20 real Scryfall cards all survive mapping and round-trip."""
    for sc in dsk_cards[:20]:
        card = _scryfall_to_card(sc)
        json_str = card.model_dump_json()
        restored = Card.model_validate_json(json_str)
        assert restored.name == card.name
