"""Tests for mtgai.review.loaders — card loading, filtering, and sorting."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mtgai.models.card import Card
from mtgai.models.enums import Color, Rarity
from mtgai.review.loaders import (
    SORT_KEYS,
    CardFilter,
    filter_cards,
    load_cards,
    load_cards_raw,
    sort_cards,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_card(**overrides) -> Card:
    """Create a Card with sane defaults, overridable by keyword args."""
    defaults = {
        "name": "Test Creature",
        "mana_cost": "{2}{G}",
        "cmc": 3.0,
        "type_line": "Creature -- Beast",
        "oracle_text": "Trample",
        "power": "3",
        "toughness": "3",
        "rarity": Rarity.COMMON,
        "colors": [Color.GREEN],
        "color_identity": [Color.GREEN],
        "collector_number": "G-C-01",
        "set_code": "TST",
        "card_types": ["Creature"],
        "subtypes": ["Beast"],
    }
    defaults.update(overrides)
    return Card(**defaults)


def _write_card_json(cards_dir: Path, card: Card) -> Path:
    """Write a Card model as JSON to the given directory. Returns the path."""
    slug = card.name.lower().replace(" ", "_").replace(",", "").replace("'", "")
    filename = f"{card.collector_number}_{slug}.json"
    path = cards_dir / filename
    path.write_text(card.model_dump_json(indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Fixture cards
# ---------------------------------------------------------------------------

# A diverse set of cards for testing filters and sorting
CARDS = [
    _make_card(
        name="Savannah Lions",
        mana_cost="{W}",
        cmc=1.0,
        type_line="Creature -- Cat",
        oracle_text="",
        power="2",
        toughness="1",
        rarity=Rarity.COMMON,
        colors=[Color.WHITE],
        color_identity=[Color.WHITE],
        collector_number="W-C-01",
        card_types=["Creature"],
        subtypes=["Cat"],
        mechanic_tags=["vanilla"],
    ),
    _make_card(
        name="Counterspell",
        mana_cost="{U}{U}",
        cmc=2.0,
        type_line="Instant",
        oracle_text="Counter target spell.",
        power=None,
        toughness=None,
        rarity=Rarity.UNCOMMON,
        colors=[Color.BLUE],
        color_identity=[Color.BLUE],
        collector_number="U-U-01",
        card_types=["Instant"],
        subtypes=[],
    ),
    _make_card(
        name="Lightning Bolt",
        mana_cost="{R}",
        cmc=1.0,
        type_line="Instant",
        oracle_text="Lightning Bolt deals 3 damage to any target.",
        power=None,
        toughness=None,
        rarity=Rarity.COMMON,
        colors=[Color.RED],
        color_identity=[Color.RED],
        collector_number="R-C-01",
        card_types=["Instant"],
        subtypes=[],
    ),
    _make_card(
        name="Salvage Beetle",
        mana_cost="{1}{G}",
        cmc=2.0,
        type_line="Creature -- Insect",
        oracle_text="Salvage 2 (When this creature dies, return up to two target cards "
        "from your graveyard to your hand.)",
        power="2",
        toughness="2",
        rarity=Rarity.UNCOMMON,
        colors=[Color.GREEN],
        color_identity=[Color.GREEN],
        collector_number="G-U-01",
        card_types=["Creature"],
        subtypes=["Insect"],
        mechanic_tags=["salvage"],
    ),
    _make_card(
        name="Murder",
        mana_cost="{1}{B}{B}",
        cmc=3.0,
        type_line="Instant",
        oracle_text="Destroy target creature.",
        power=None,
        toughness=None,
        rarity=Rarity.COMMON,
        colors=[Color.BLACK],
        color_identity=[Color.BLACK],
        collector_number="B-C-03",
        card_types=["Instant"],
        subtypes=[],
        is_reprint=True,
    ),
    _make_card(
        name="Azorius Signet",
        mana_cost="{2}",
        cmc=2.0,
        type_line="Artifact",
        oracle_text="{1}, {T}: Add {W}{U}.",
        power=None,
        toughness=None,
        rarity=Rarity.COMMON,
        colors=[],
        color_identity=[Color.WHITE, Color.BLUE],
        collector_number="M-C-01",
        card_types=["Artifact"],
        subtypes=[],
    ),
    _make_card(
        name="Overclock Engine",
        mana_cost="{3}{U}{R}",
        cmc=5.0,
        type_line="Artifact Creature -- Construct",
        oracle_text="Overclock. (Exile the top three cards of your library. "
        "You may play them until end of turn.)",
        power="4",
        toughness="3",
        rarity=Rarity.RARE,
        colors=[Color.BLUE, Color.RED],
        color_identity=[Color.BLUE, Color.RED],
        collector_number="M-R-01",
        card_types=["Artifact", "Creature"],
        subtypes=["Construct"],
        mechanic_tags=["overclock"],
    ),
    _make_card(
        name="Dragon God",
        mana_cost="{4}{R}{R}{R}",
        cmc=7.0,
        type_line="Legendary Creature -- Dragon God",
        oracle_text="Flying, haste\nWhenever Dragon God attacks, it deals 5 damage "
        "to each opponent.",
        power="7",
        toughness="7",
        rarity=Rarity.MYTHIC,
        colors=[Color.RED],
        color_identity=[Color.RED],
        collector_number="R-M-01",
        card_types=["Creature"],
        subtypes=["Dragon", "God"],
        supertypes=["Legendary"],
    ),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cards_dir(tmp_path: Path) -> Path:
    """Create a temp cards directory with fixture card JSONs."""
    d = tmp_path / "cards"
    d.mkdir()
    for card in CARDS:
        _write_card_json(d, card)
    return d


@pytest.fixture
def all_cards() -> list[Card]:
    """Return the full fixture card list (no disk I/O)."""
    return list(CARDS)


# ---------------------------------------------------------------------------
# Tests: load_cards
# ---------------------------------------------------------------------------


class TestLoadCards:
    """Tests for load_cards() — loading Card models from JSON files."""

    def test_load_from_dir(self, cards_dir: Path) -> None:
        """Cards are loaded and parsed into Card models."""
        result = load_cards(cards_dir=cards_dir)
        assert len(result) == len(CARDS)
        assert all(isinstance(c, Card) for c in result)

    def test_sorted_by_collector_number(self, cards_dir: Path) -> None:
        """Cards are sorted by collector_number by default."""
        result = load_cards(cards_dir=cards_dir)
        numbers = [c.collector_number for c in result]
        assert numbers == sorted(numbers)

    def test_card_fields_preserved(self, cards_dir: Path) -> None:
        """Card fields survive the JSON round-trip."""
        result = load_cards(cards_dir=cards_dir)
        lions = next(c for c in result if c.name == "Savannah Lions")
        assert lions.mana_cost == "{W}"
        assert lions.cmc == 1.0
        assert lions.rarity == Rarity.COMMON
        assert Color.WHITE in lions.color_identity
        assert lions.collector_number == "W-C-01"

    def test_empty_dir(self, tmp_path: Path) -> None:
        """An empty cards directory returns an empty list."""
        d = tmp_path / "cards"
        d.mkdir()
        assert load_cards(cards_dir=d) == []

    def test_missing_dir(self, tmp_path: Path) -> None:
        """A nonexistent cards directory returns an empty list."""
        d = tmp_path / "does_not_exist"
        assert load_cards(cards_dir=d) == []

    def test_malformed_json_skipped(self, cards_dir: Path) -> None:
        """Malformed JSON files are skipped (not crash)."""
        bad_file = cards_dir / "BAD-01_broken.json"
        bad_file.write_text("{not valid json!!!}", encoding="utf-8")
        result = load_cards(cards_dir=cards_dir)
        # All good cards loaded, bad one skipped
        assert len(result) == len(CARDS)

    def test_invalid_card_data_skipped(self, cards_dir: Path) -> None:
        """JSON that doesn't match the Card schema is skipped."""
        bad_file = cards_dir / "BAD-02_invalid.json"
        bad_file.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
        result = load_cards(cards_dir=cards_dir)
        assert len(result) == len(CARDS)

    def test_non_json_files_ignored(self, cards_dir: Path) -> None:
        """Non-JSON files in the directory are ignored."""
        (cards_dir / "readme.txt").write_text("not a card", encoding="utf-8")
        (cards_dir / "notes.md").write_text("# notes", encoding="utf-8")
        result = load_cards(cards_dir=cards_dir)
        assert len(result) == len(CARDS)


# ---------------------------------------------------------------------------
# Tests: load_cards_raw
# ---------------------------------------------------------------------------


class TestLoadCardsRaw:
    """Tests for load_cards_raw() — backward-compatible dict loader."""

    def test_returns_dicts(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """load_cards_raw returns list[dict].

        Phase 2: ``loaders._set_dir`` routes through
        :func:`set_artifact_dir`, which falls back to
        ``asset_paths.SETS_ROOT / set_code`` when the set has no
        configured ``asset_folder``. We patch both the asset helper and
        ``model_settings`` so the fallback lands inside ``tmp_path``.
        """
        from mtgai.io import asset_paths
        from mtgai.settings import model_settings as ms

        sets_root = tmp_path / "sets"
        settings_dir = tmp_path / "settings"
        sets_root.mkdir(parents=True)
        settings_dir.mkdir(parents=True)

        cards_dir = sets_root / "TST" / "cards"
        cards_dir.mkdir(parents=True)
        card = _make_card(name="Test", collector_number="T-01")
        _write_card_json(cards_dir, card)

        monkeypatch.setattr(asset_paths, "OUTPUT_ROOT", tmp_path)
        monkeypatch.setattr(asset_paths, "SETS_ROOT", sets_root)
        monkeypatch.setattr(ms, "OUTPUT_ROOT", tmp_path)
        monkeypatch.setattr(ms, "SETTINGS_DIR", settings_dir)
        monkeypatch.setattr(ms, "SETS_DIR", sets_root)
        monkeypatch.setattr(ms, "GLOBAL_TOML", settings_dir / "global.toml")
        monkeypatch.setattr(ms, "LEGACY_CURRENT_TOML", settings_dir / "current.toml")
        ms.invalidate_cache()
        try:
            result = load_cards_raw("TST")
        finally:
            ms.invalidate_cache()
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["name"] == "Test"


# ---------------------------------------------------------------------------
# Tests: filter_cards
# ---------------------------------------------------------------------------


class TestFilterCards:
    """Tests for filter_cards() with CardFilter."""

    def test_no_filter(self, all_cards: list[Card]) -> None:
        """Empty filter returns all cards."""
        result = filter_cards(all_cards, CardFilter())
        assert len(result) == len(all_cards)

    # --- Color filters ---

    def test_filter_by_color_white(self, all_cards: list[Card]) -> None:
        """Filter by color W matches cards with W in color_identity."""
        result = filter_cards(all_cards, CardFilter(color="W"))
        names = {c.name for c in result}
        assert "Savannah Lions" in names
        assert "Azorius Signet" in names  # color_identity includes W
        assert "Lightning Bolt" not in names

    def test_filter_by_color_case_insensitive(self, all_cards: list[Card]) -> None:
        """Color filter is case-insensitive."""
        result = filter_cards(all_cards, CardFilter(color="u"))
        names = {c.name for c in result}
        assert "Counterspell" in names

    def test_filter_by_colors_multi(self, all_cards: list[Card]) -> None:
        """Multiple colors filter with OR logic within."""
        result = filter_cards(all_cards, CardFilter(colors=["W", "B"]))
        names = {c.name for c in result}
        assert "Savannah Lions" in names  # W
        assert "Murder" in names  # B
        assert "Azorius Signet" in names  # WU identity
        assert "Lightning Bolt" not in names

    # --- Rarity filters ---

    def test_filter_by_rarity_common(self, all_cards: list[Card]) -> None:
        """Filter by rarity common."""
        result = filter_cards(all_cards, CardFilter(rarity="common"))
        assert all(c.rarity == Rarity.COMMON for c in result)
        names = {c.name for c in result}
        assert "Savannah Lions" in names
        assert "Lightning Bolt" in names
        assert "Counterspell" not in names  # uncommon

    def test_filter_by_rarity_mythic(self, all_cards: list[Card]) -> None:
        """Filter by rarity mythic."""
        result = filter_cards(all_cards, CardFilter(rarity="mythic"))
        assert len(result) == 1
        assert result[0].name == "Dragon God"

    def test_filter_by_rarity_case_insensitive(self, all_cards: list[Card]) -> None:
        """Rarity filter is case-insensitive."""
        result = filter_cards(all_cards, CardFilter(rarity="UNCOMMON"))
        assert all(c.rarity == Rarity.UNCOMMON for c in result)

    # --- Card type filters ---

    def test_filter_by_type_creature(self, all_cards: list[Card]) -> None:
        """Filter by card type creature (substring match in type_line)."""
        result = filter_cards(all_cards, CardFilter(card_type="creature"))
        names = {c.name for c in result}
        assert "Savannah Lions" in names
        assert "Salvage Beetle" in names
        assert "Overclock Engine" in names  # Artifact Creature
        assert "Dragon God" in names
        assert "Counterspell" not in names

    def test_filter_by_type_instant(self, all_cards: list[Card]) -> None:
        """Filter by card type instant."""
        result = filter_cards(all_cards, CardFilter(card_type="instant"))
        names = {c.name for c in result}
        assert "Counterspell" in names
        assert "Lightning Bolt" in names
        assert "Murder" in names
        assert "Savannah Lions" not in names

    def test_filter_by_type_artifact(self, all_cards: list[Card]) -> None:
        """Filter by card type artifact."""
        result = filter_cards(all_cards, CardFilter(card_type="artifact"))
        names = {c.name for c in result}
        assert "Azorius Signet" in names
        assert "Overclock Engine" in names  # Artifact Creature

    def test_filter_by_type_legendary(self, all_cards: list[Card]) -> None:
        """Supertype 'Legendary' in type_line is matchable."""
        result = filter_cards(all_cards, CardFilter(card_type="legendary"))
        assert len(result) == 1
        assert result[0].name == "Dragon God"

    # --- CMC filters ---

    def test_filter_by_cmc_exact(self, all_cards: list[Card]) -> None:
        """Filter by exact CMC."""
        result = filter_cards(all_cards, CardFilter(cmc=2.0))
        names = {c.name for c in result}
        assert "Counterspell" in names
        assert "Salvage Beetle" in names
        assert "Azorius Signet" in names
        assert "Savannah Lions" not in names

    def test_filter_by_cmc_min(self, all_cards: list[Card]) -> None:
        """Filter by minimum CMC."""
        result = filter_cards(all_cards, CardFilter(cmc_min=5.0))
        names = {c.name for c in result}
        assert "Overclock Engine" in names  # cmc 5
        assert "Dragon God" in names  # cmc 7
        assert "Murder" not in names  # cmc 3

    def test_filter_by_cmc_max(self, all_cards: list[Card]) -> None:
        """Filter by maximum CMC."""
        result = filter_cards(all_cards, CardFilter(cmc_max=1.0))
        names = {c.name for c in result}
        assert "Savannah Lions" in names
        assert "Lightning Bolt" in names
        assert len(result) == 2

    def test_filter_by_cmc_range(self, all_cards: list[Card]) -> None:
        """Filter by CMC range (min + max)."""
        result = filter_cards(all_cards, CardFilter(cmc_min=2.0, cmc_max=3.0))
        names = {c.name for c in result}
        assert "Counterspell" in names  # 2
        assert "Salvage Beetle" in names  # 2
        assert "Murder" in names  # 3
        assert "Savannah Lions" not in names  # 1
        assert "Dragon God" not in names  # 7

    # --- Keyword filters ---

    def test_filter_by_keyword_in_name(self, all_cards: list[Card]) -> None:
        """Keyword search matches card name."""
        result = filter_cards(all_cards, CardFilter(keyword="dragon"))
        assert len(result) == 1
        assert result[0].name == "Dragon God"

    def test_filter_by_keyword_in_oracle(self, all_cards: list[Card]) -> None:
        """Keyword search matches oracle_text."""
        result = filter_cards(all_cards, CardFilter(keyword="counter target"))
        assert len(result) == 1
        assert result[0].name == "Counterspell"

    def test_filter_by_keyword_in_type_line(self, all_cards: list[Card]) -> None:
        """Keyword search matches type_line."""
        result = filter_cards(all_cards, CardFilter(keyword="insect"))
        assert len(result) == 1
        assert result[0].name == "Salvage Beetle"

    def test_filter_by_keyword_case_insensitive(self, all_cards: list[Card]) -> None:
        """Keyword search is case-insensitive."""
        result = filter_cards(all_cards, CardFilter(keyword="TRAMPLE"))
        # Salvage Beetle oracle has "Salvage", not "Trample" — but let's check
        # No card in our set has "TRAMPLE" in oracle... wait, none do. Let me pick "flying"
        result = filter_cards(all_cards, CardFilter(keyword="FLYING"))
        assert len(result) == 1
        assert result[0].name == "Dragon God"

    # --- Mechanic tag filters ---

    def test_filter_by_mechanic_tag(self, all_cards: list[Card]) -> None:
        """Filter by mechanic_tags."""
        result = filter_cards(all_cards, CardFilter(mechanic="salvage"))
        assert len(result) == 1
        assert result[0].name == "Salvage Beetle"

    def test_filter_by_mechanic_tag_case_insensitive(self, all_cards: list[Card]) -> None:
        """Mechanic tag filter is case-insensitive."""
        result = filter_cards(all_cards, CardFilter(mechanic="OVERCLOCK"))
        assert len(result) == 1
        assert result[0].name == "Overclock Engine"

    def test_filter_by_mechanic_tag_no_match(self, all_cards: list[Card]) -> None:
        """Mechanic tag with no matches returns empty."""
        result = filter_cards(all_cards, CardFilter(mechanic="nonexistent"))
        assert result == []

    # --- Set mechanic name in oracle text ---

    def test_filter_by_mechanic_name_in_oracle(self, all_cards: list[Card]) -> None:
        """Filter by set mechanic name in oracle_text."""
        result = filter_cards(all_cards, CardFilter(mechanic_name="Salvage"))
        assert len(result) == 1
        assert result[0].name == "Salvage Beetle"

    def test_filter_by_mechanic_name_overclock(self, all_cards: list[Card]) -> None:
        """Filter by Overclock in oracle text."""
        result = filter_cards(all_cards, CardFilter(mechanic_name="overclock"))
        assert len(result) == 1
        assert result[0].name == "Overclock Engine"

    # --- Combined (AND) filters ---

    def test_combined_color_and_rarity(self, all_cards: list[Card]) -> None:
        """Color + rarity filters are AND-combined."""
        result = filter_cards(all_cards, CardFilter(color="R", rarity="common"))
        assert len(result) == 1
        assert result[0].name == "Lightning Bolt"

    def test_combined_type_and_cmc(self, all_cards: list[Card]) -> None:
        """Card type + CMC filters are AND-combined."""
        result = filter_cards(all_cards, CardFilter(card_type="creature", cmc_max=2.0))
        names = {c.name for c in result}
        assert "Savannah Lions" in names  # creature, cmc 1
        assert "Salvage Beetle" in names  # creature, cmc 2
        assert "Dragon God" not in names  # creature, cmc 7
        assert "Counterspell" not in names  # instant

    def test_combined_color_type_rarity(self, all_cards: list[Card]) -> None:
        """Three-way AND filter."""
        result = filter_cards(
            all_cards,
            CardFilter(color="R", card_type="creature", rarity="mythic"),
        )
        assert len(result) == 1
        assert result[0].name == "Dragon God"

    def test_combined_all_restrictive(self, all_cards: list[Card]) -> None:
        """Highly restrictive combined filter with no matches."""
        result = filter_cards(
            all_cards,
            CardFilter(color="W", rarity="mythic", card_type="instant"),
        )
        assert result == []

    # --- Empty results ---

    def test_filter_empty_input(self) -> None:
        """Filtering an empty list returns empty."""
        result = filter_cards([], CardFilter(color="W"))
        assert result == []

    def test_filter_no_match(self, all_cards: list[Card]) -> None:
        """Filter that matches nothing returns empty."""
        result = filter_cards(all_cards, CardFilter(keyword="xyzzyplugh"))
        assert result == []


# ---------------------------------------------------------------------------
# Tests: sort_cards
# ---------------------------------------------------------------------------


class TestSortCards:
    """Tests for sort_cards()."""

    def test_sort_by_name(self, all_cards: list[Card]) -> None:
        """Sort by name alphabetically."""
        result = sort_cards(all_cards, sort_by="name")
        names = [c.name for c in result]
        assert names == sorted(names, key=str.lower)

    def test_sort_by_cmc(self, all_cards: list[Card]) -> None:
        """Sort by CMC ascending."""
        result = sort_cards(all_cards, sort_by="cmc")
        cmcs = [c.cmc for c in result]
        assert cmcs == sorted(cmcs)

    def test_sort_by_cmc_descending(self, all_cards: list[Card]) -> None:
        """Sort by CMC descending with reverse=True."""
        result = sort_cards(all_cards, sort_by="cmc", reverse=True)
        cmcs = [c.cmc for c in result]
        assert cmcs == sorted(cmcs, reverse=True)

    def test_sort_by_rarity(self, all_cards: list[Card]) -> None:
        """Sort by rarity (common < uncommon < rare < mythic)."""
        result = sort_cards(all_cards, sort_by="rarity")
        rarities = [c.rarity for c in result]
        # Verify ordering: commons first, then uncommons, then rares, then mythics
        from mtgai.review.loaders import RARITY_ORDER

        rarity_indices = [RARITY_ORDER[r] for r in rarities]
        assert rarity_indices == sorted(rarity_indices)

    def test_sort_by_color(self, all_cards: list[Card]) -> None:
        """Sort by color (colorless first, then WUBRG)."""
        result = sort_cards(all_cards, sort_by="color")
        # First card should be the colorless artifact (Azorius Signet has WU identity,
        # but no card has empty color_identity)
        # Let's verify the order is sensible: W before U before B before R before G
        colors_first = []
        for c in result:
            if not c.color_identity:
                colors_first.append(-1)
            else:
                from mtgai.review.loaders import COLOR_ORDER

                colors_first.append(COLOR_ORDER.get(c.color_identity[0], 99))
        assert colors_first == sorted(colors_first)

    def test_sort_by_collector_number(self, all_cards: list[Card]) -> None:
        """Sort by collector_number (default)."""
        result = sort_cards(all_cards, sort_by="collector_number")
        numbers = [c.collector_number for c in result]
        assert numbers == sorted(numbers)

    def test_sort_invalid_key(self, all_cards: list[Card]) -> None:
        """Invalid sort key raises ValueError."""
        with pytest.raises(ValueError, match="Unknown sort key"):
            sort_cards(all_cards, sort_by="nonexistent")

    def test_sort_empty_list(self) -> None:
        """Sorting an empty list returns empty."""
        result = sort_cards([], sort_by="name")
        assert result == []

    def test_sort_preserves_all_cards(self, all_cards: list[Card]) -> None:
        """Sorting doesn't lose or duplicate cards."""
        result = sort_cards(all_cards, sort_by="name")
        assert len(result) == len(all_cards)
        assert {c.name for c in result} == {c.name for c in all_cards}

    def test_all_sort_keys_valid(self, all_cards: list[Card]) -> None:
        """Every key in SORT_KEYS works without error."""
        for key in SORT_KEYS:
            result = sort_cards(all_cards, sort_by=key)
            assert len(result) == len(all_cards)


# ---------------------------------------------------------------------------
# Tests: integration (load + filter + sort)
# ---------------------------------------------------------------------------


class TestIntegration:
    """Integration tests combining load, filter, and sort."""

    def test_load_filter_sort(self, cards_dir: Path) -> None:
        """Full pipeline: load from disk -> filter -> sort."""
        cards = load_cards(cards_dir=cards_dir)
        filtered = filter_cards(cards, CardFilter(card_type="creature"))
        sorted_cards = sort_cards(filtered, sort_by="cmc")

        # All results should be creatures
        assert all("Creature" in c.type_line for c in sorted_cards)
        # Should be sorted by CMC
        cmcs = [c.cmc for c in sorted_cards]
        assert cmcs == sorted(cmcs)

    def test_load_then_filter_by_rarity_and_color(self, cards_dir: Path) -> None:
        """Load + filter by rarity and color together."""
        cards = load_cards(cards_dir=cards_dir)
        result = filter_cards(cards, CardFilter(rarity="common", color="R"))
        assert len(result) == 1
        assert result[0].name == "Lightning Bolt"

    def test_filter_then_sort_by_name(self, cards_dir: Path) -> None:
        """Filter instants then sort by name."""
        cards = load_cards(cards_dir=cards_dir)
        instants = filter_cards(cards, CardFilter(card_type="instant"))
        sorted_instants = sort_cards(instants, sort_by="name")
        names = [c.name for c in sorted_instants]
        assert names == sorted(names, key=str.lower)
