"""Tests for card/set I/O round-trip serialization and path helpers."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mtgai.io.card_io import load_card, load_set, save_card, save_set
from mtgai.io.paths import art_path, card_json_path, card_slug, render_path, set_dir
from mtgai.models.card import Card, CardFace, GenerationAttempt
from mtgai.models.enums import CardLayout, Color, Rarity
from mtgai.models.set import Set

# ---------------------------------------------------------------------------
# card_slug
# ---------------------------------------------------------------------------


def test_card_slug():
    """card_slug produces filesystem-safe names."""
    assert card_slug("001", "Lightning Bolt") == "001_lightning_bolt"
    assert card_slug("042", "Serra's Angel") == "042_serras_angel"
    assert card_slug("200a", "Test Card, Jr.") == "200a_test_card_jr"


@pytest.mark.parametrize(
    "number,name,expected",
    [
        ("001", "Simple Card", "001_simple_card"),
        ("010", "Card with CAPS", "010_card_with_caps"),
        ("099", "Nicol Bolas, Dragon-God", "099_nicol_bolas_dragongod"),
        ("100", "Fire // Ice", "100_fire__ice"),
        ("200", "Lim-Dul's Vault", "200_limduls_vault"),
        ("300", "Card: The Return", "300_card_the_return"),
    ],
)
def test_card_slug_special_characters(number, name, expected):
    """card_slug strips non-alphanumeric characters except underscores."""
    assert card_slug(number, name) == expected


# ---------------------------------------------------------------------------
# Path generation helpers
# ---------------------------------------------------------------------------


def test_set_dir():
    """set_dir builds correct directory structure."""
    root = Path("/output")
    result = set_dir(root, "dsk")
    assert result == Path("/output/sets/DSK")


def test_set_dir_uppercase():
    """set_dir uppercases the set code."""
    result = set_dir(Path("/out"), "abc")
    assert "ABC" in str(result)


def test_card_json_path_structure():
    """card_json_path places cards in the correct subdirectory."""
    root = Path("/output")
    result = card_json_path(root, "TST", "001", "Lightning Bolt")
    assert result == Path("/output/sets/TST/cards/001_lightning_bolt.json")


def test_art_path_default_version():
    """art_path uses version 1 by default."""
    root = Path("/output")
    result = art_path(root, "TST", "001", "Lightning Bolt")
    assert result == Path("/output/sets/TST/art/001_lightning_bolt_v1.png")


def test_art_path_custom_version():
    """art_path accepts a custom version number."""
    root = Path("/output")
    result = art_path(root, "TST", "001", "Lightning Bolt", version=3)
    assert result == Path("/output/sets/TST/art/001_lightning_bolt_v3.png")


def test_render_path_structure():
    """render_path places renders in the correct subdirectory."""
    root = Path("/output")
    result = render_path(root, "TST", "001", "Lightning Bolt")
    assert result == Path("/output/sets/TST/renders/001_lightning_bolt.png")


# ---------------------------------------------------------------------------
# save_card / load_card
# ---------------------------------------------------------------------------


def test_save_and_load_card(tmp_path):
    """Card JSON saves to disk and loads back identically."""
    card = Card(
        name="Test Card",
        type_line="Instant",
        rarity=Rarity.COMMON,
        set_code="TST",
        collector_number="001",
    )
    path = save_card(card, tmp_path)
    assert path.exists()
    loaded = load_card(path)
    assert loaded == card
    assert loaded.name == "Test Card"


def test_save_and_load_set(tmp_path):
    """Set with cards saves to disk and loads back."""
    card = Card(name="Test Card", type_line="Instant", set_code="TST")
    s = Set(name="Test Set", code="TST", theme="Testing", cards=[card])
    path = save_set(s, tmp_path)
    assert path.exists()
    loaded = load_set(path)
    assert loaded.name == "Test Set"
    # save_set strips cards (they're saved individually)
    assert len(loaded.cards) == 0


def test_card_json_content(tmp_path):
    """Saved card JSON is human-readable (indented)."""
    card = Card(
        name="Readable Card",
        type_line="Sorcery",
        set_code="TST",
        collector_number="010",
    )
    path = save_card(card, tmp_path)
    content = path.read_text(encoding="utf-8")
    assert "\n" in content  # indented JSON has newlines
    assert '"name": "Readable Card"' in content


# ---------------------------------------------------------------------------
# Special characters in names survive I/O
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Serra's Angel",
        "Nicol Bolas, Dragon-God",
        "Fire // Ice",
        "Korvold, Fae-Cursed King",
    ],
)
def test_special_name_save_load(tmp_path, name):
    """Cards with special characters in names save and load correctly."""
    card = Card(
        name=name,
        type_line="Creature",
        set_code="TST",
        collector_number="001",
    )
    path = save_card(card, tmp_path)
    loaded = load_card(path)
    assert loaded.name == name


# ---------------------------------------------------------------------------
# Overwrite behavior
# ---------------------------------------------------------------------------


def test_overwrite_same_card(tmp_path):
    """Saving the same card twice overwrites the file; latest version is loaded."""
    card_v1 = Card(
        name="Evolving Card",
        type_line="Creature",
        oracle_text="Version 1",
        set_code="TST",
        collector_number="001",
    )
    card_v2 = Card(
        name="Evolving Card",
        type_line="Creature",
        oracle_text="Version 2",
        set_code="TST",
        collector_number="001",
    )
    path1 = save_card(card_v1, tmp_path)
    path2 = save_card(card_v2, tmp_path)
    # Same path (same slug)
    assert path1 == path2
    loaded = load_card(path2)
    assert loaded.oracle_text == "Version 2"


# ---------------------------------------------------------------------------
# Directory creation
# ---------------------------------------------------------------------------


def test_save_card_creates_directories(tmp_path):
    """save_card creates parent directories if they don't exist."""
    card = Card(
        name="Deep Card",
        type_line="Instant",
        set_code="DEEP",
        collector_number="001",
    )
    # tmp_path/sets/DEEP/cards/ doesn't exist yet
    path = save_card(card, tmp_path)
    assert path.exists()
    assert path.parent.exists()


def test_save_set_creates_directories(tmp_path):
    """save_set creates parent directories if they don't exist."""
    s = Set(name="New Set", code="NEW", theme="Fresh")
    path = save_set(s, tmp_path)
    assert path.exists()
    assert path.parent.exists()


# ---------------------------------------------------------------------------
# Unicode encoding
# ---------------------------------------------------------------------------


def test_unicode_flavor_text_round_trip(tmp_path):
    """Cards with Unicode flavor text survive file I/O."""
    card = Card(
        name="Unicode Card",
        type_line="Creature",
        flavor_text="\u2014 Jace Beleren\n\u201cTo know is to control.\u201d",
        set_code="TST",
        collector_number="042",
    )
    path = save_card(card, tmp_path)
    loaded = load_card(path)
    assert loaded.flavor_text == card.flavor_text
    assert "\u2014" in loaded.flavor_text
    assert "\u201c" in loaded.flavor_text


def test_unicode_oracle_text_round_trip(tmp_path):
    """Cards with Unicode oracle text survive file I/O."""
    card = Card(
        name="Mana Symbol Card",
        type_line="Instant",
        oracle_text="Pay 2 life: Add {B}.\nPay 2 life: Add {R}.",
        set_code="TST",
        collector_number="099",
    )
    path = save_card(card, tmp_path)
    loaded = load_card(path)
    assert loaded.oracle_text == card.oracle_text


# ---------------------------------------------------------------------------
# Large card with many attempts
# ---------------------------------------------------------------------------


def test_large_card_with_attempts(tmp_path):
    """A card with long oracle_text and many generation attempts round-trips via file."""
    long_text = "This is a very detailed card. " * 20  # ~600 chars
    attempts = [
        GenerationAttempt(
            attempt_number=i,
            timestamp=datetime(2025, 1, 1, i, 0, 0, tzinfo=UTC),
            success=(i == 5),
            error_message=f"Error on attempt {i}" if i != 5 else None,
            input_tokens=100 * i,
            output_tokens=50 * i,
            cost_usd=0.001 * i,
        )
        for i in range(1, 6)
    ]
    card = Card(
        name="Complex Card",
        type_line="Creature",
        oracle_text=long_text,
        set_code="TST",
        collector_number="200",
        generation_attempts=attempts,
    )
    path = save_card(card, tmp_path)
    loaded = load_card(path)
    assert loaded.oracle_text == long_text
    assert len(loaded.generation_attempts) == 5
    assert loaded.generation_attempts[4].success is True
    assert loaded.generation_attempts[0].cost_usd == pytest.approx(0.001)


# ---------------------------------------------------------------------------
# DFC card I/O
# ---------------------------------------------------------------------------


def test_dfc_card_save_load(tmp_path):
    """A double-faced card survives save/load."""
    card = Card(
        name="Front // Back",
        type_line="Creature // Land",
        layout=CardLayout.TRANSFORM,
        set_code="TST",
        collector_number="150",
        card_faces=[
            CardFace(
                name="Front",
                mana_cost="{1}{G}",
                type_line="Creature",
                oracle_text="Transform",
                power="2",
                toughness="2",
                colors=[Color.GREEN],
            ),
            CardFace(
                name="Back",
                type_line="Land",
                oracle_text="{T}: Add {G}.",
                colors=[],
            ),
        ],
    )
    path = save_card(card, tmp_path)
    loaded = load_card(path)
    assert loaded.layout == CardLayout.TRANSFORM
    assert len(loaded.card_faces) == 2
    assert loaded.card_faces[0].power == "2"
    assert loaded.card_faces[1].oracle_text == "{T}: Add {G}."
