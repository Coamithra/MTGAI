"""Tests for mtgai.review.exporters — CSV / JSON / print export.

No LLM or active project is required: the exporters take explicit card lists
(and, for print, an explicit renders directory).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from mtgai.io.paths import card_slug
from mtgai.models.card import Card
from mtgai.models.enums import Color, Rarity
from mtgai.review.exporters import (
    CSV_COLUMNS,
    PrintExportResult,
    card_to_row,
    export_csv,
    export_json,
    export_print,
)


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


SAMPLE_CARDS = [
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
        mechanic_tags=["vanilla"],
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
        mechanic_tags=["mana_rock", "filter"],
    ),
]


# ---------------------------------------------------------------------------
# card_to_row
# ---------------------------------------------------------------------------


class TestCardToRow:
    def test_keys_match_columns(self) -> None:
        row = card_to_row(SAMPLE_CARDS[0])
        assert set(row.keys()) == set(CSV_COLUMNS)

    def test_none_becomes_empty_string(self) -> None:
        row = card_to_row(SAMPLE_CARDS[1])  # Murder has no power/toughness
        assert row["power"] == ""
        assert row["toughness"] == ""
        assert row["loyalty"] == ""

    def test_bool_rendered_as_lowercase(self) -> None:
        assert card_to_row(SAMPLE_CARDS[1])["is_reprint"] == "true"
        assert card_to_row(SAMPLE_CARDS[0])["is_reprint"] == "false"

    def test_whole_cmc_rendered_as_int(self) -> None:
        assert card_to_row(SAMPLE_CARDS[0])["cmc"] == "1"
        assert "." not in card_to_row(SAMPLE_CARDS[0])["cmc"]

    def test_color_identity_joined_with_semicolon(self) -> None:
        row = card_to_row(SAMPLE_CARDS[2])  # WU identity
        assert row["color_identity"] == "W;U"

    def test_mechanic_tags_joined_with_semicolon(self) -> None:
        assert card_to_row(SAMPLE_CARDS[2])["mechanic_tags"] == "mana_rock;filter"

    def test_empty_color_identity(self) -> None:
        colorless = _make_card(color_identity=[], colors=[])
        assert card_to_row(colorless)["color_identity"] == ""

    def test_rarity_is_string_value(self) -> None:
        assert card_to_row(SAMPLE_CARDS[0])["rarity"] == "common"


# ---------------------------------------------------------------------------
# export_csv
# ---------------------------------------------------------------------------


class TestExportCsv:
    def test_returns_count(self, tmp_path: Path) -> None:
        count = export_csv(SAMPLE_CARDS, tmp_path / "cards.csv")
        assert count == len(SAMPLE_CARDS)

    def test_header_matches_columns(self, tmp_path: Path) -> None:
        out = tmp_path / "cards.csv"
        export_csv(SAMPLE_CARDS, out)
        with out.open(encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader)
        assert header == CSV_COLUMNS

    def test_round_trips_through_dictreader(self, tmp_path: Path) -> None:
        out = tmp_path / "cards.csv"
        export_csv(SAMPLE_CARDS, out)
        with out.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == len(SAMPLE_CARDS)
        names = {r["name"] for r in rows}
        assert {"Savannah Lions", "Murder", "Azorius Signet"} == names

    def test_oracle_text_with_newline_survives(self, tmp_path: Path) -> None:
        card = _make_card(oracle_text="Flying\nVigilance", collector_number="X-01")
        out = tmp_path / "nl.csv"
        export_csv([card], out)
        with out.open(encoding="utf-8", newline="") as fh:
            row = next(csv.DictReader(fh))
        assert row["oracle_text"] == "Flying\nVigilance"

    def test_utf8_content_preserved(self, tmp_path: Path) -> None:
        card = _make_card(name="Æther Spike — Test", collector_number="X-02")
        out = tmp_path / "utf8.csv"
        export_csv([card], out)
        with out.open(encoding="utf-8", newline="") as fh:
            row = next(csv.DictReader(fh))
        assert row["name"] == "Æther Spike — Test"

    def test_creates_parent_dir(self, tmp_path: Path) -> None:
        out = tmp_path / "nested" / "deep" / "cards.csv"
        export_csv(SAMPLE_CARDS, out)
        assert out.exists()

    def test_empty_card_list_writes_header_only(self, tmp_path: Path) -> None:
        out = tmp_path / "empty.csv"
        count = export_csv([], out)
        assert count == 0
        with out.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        assert rows == [CSV_COLUMNS]


# ---------------------------------------------------------------------------
# export_json
# ---------------------------------------------------------------------------


class TestExportJson:
    def test_returns_count(self, tmp_path: Path) -> None:
        count = export_json(SAMPLE_CARDS, tmp_path / "cards.json")
        assert count == len(SAMPLE_CARDS)

    def test_top_level_is_list(self, tmp_path: Path) -> None:
        out = tmp_path / "cards.json"
        export_json(SAMPLE_CARDS, out)
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(payload, list)
        assert len(payload) == len(SAMPLE_CARDS)

    def test_entries_reparse_as_cards(self, tmp_path: Path) -> None:
        out = tmp_path / "cards.json"
        export_json(SAMPLE_CARDS, out)
        payload = json.loads(out.read_text(encoding="utf-8"))
        reloaded = [Card(**entry) for entry in payload]
        assert [c.name for c in reloaded] == [c.name for c in SAMPLE_CARDS]
        assert [c.color_identity for c in reloaded] == [c.color_identity for c in SAMPLE_CARDS]

    def test_enums_serialized_as_strings(self, tmp_path: Path) -> None:
        out = tmp_path / "cards.json"
        export_json(SAMPLE_CARDS, out)
        payload = json.loads(out.read_text(encoding="utf-8"))
        # rarity is a StrEnum -> must be a plain string in the JSON
        assert payload[0]["rarity"] == "common"
        assert payload[2]["color_identity"] == ["W", "U"]

    def test_datetime_serialized(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        card = _make_card(created_at=datetime(2026, 1, 1, tzinfo=UTC))
        out = tmp_path / "dt.json"
        export_json([card], out)
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(payload[0]["created_at"], str)

    def test_creates_parent_dir(self, tmp_path: Path) -> None:
        out = tmp_path / "nested" / "cards.json"
        export_json(SAMPLE_CARDS, out)
        assert out.exists()


# ---------------------------------------------------------------------------
# export_print
# ---------------------------------------------------------------------------


def _write_render(renders_dir: Path, card: Card) -> Path:
    """Write a fake render PNG for a card by its slug. Returns the path."""
    renders_dir.mkdir(parents=True, exist_ok=True)
    path = renders_dir / f"{card_slug(card.collector_number, card.name)}.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
    return path


class TestExportPrint:
    def test_copies_present_renders_by_slug(self, tmp_path: Path) -> None:
        renders = tmp_path / "renders"
        for card in SAMPLE_CARDS:
            _write_render(renders, card)
        out = tmp_path / "print"
        result = export_print(SAMPLE_CARDS, renders, out)
        assert result.copied_count == len(SAMPLE_CARDS)
        assert result.missing_count == 0
        copied_files = sorted(p.name for p in out.glob("*.png"))
        assert len(copied_files) == len(SAMPLE_CARDS)

    def test_flat_output_keeps_slug_filename(self, tmp_path: Path) -> None:
        renders = tmp_path / "renders"
        card = SAMPLE_CARDS[0]
        _write_render(renders, card)
        out = tmp_path / "print"
        export_print([card], renders, out)
        expected = f"{card_slug(card.collector_number, card.name)}.png"
        assert (out / expected).exists()

    def test_records_missing(self, tmp_path: Path) -> None:
        renders = tmp_path / "renders"
        _write_render(renders, SAMPLE_CARDS[0])  # only first has a render
        out = tmp_path / "print"
        result = export_print(SAMPLE_CARDS, renders, out)
        assert result.copied == ["W-C-01"]
        assert set(result.missing) == {"B-C-03", "M-C-01"}

    def test_respects_explicit_render_path_relative(self, tmp_path: Path) -> None:
        # render_path is relative to the asset folder (renders_dir.parent)
        renders = tmp_path / "renders"
        renders.mkdir()
        custom = tmp_path / "renders" / "custom.png"
        custom.write_bytes(b"\x89PNGcustom")
        card = _make_card(collector_number="C-01", render_path="renders/custom.png")
        out = tmp_path / "print"
        result = export_print([card], renders, out)
        assert result.copied == ["C-01"]
        # Destination is named after the card slug, not the source basename.
        assert (out / f"{card_slug(card.collector_number, card.name)}.png").exists()

    def test_respects_explicit_render_path_absolute(self, tmp_path: Path) -> None:
        abs_png = tmp_path / "elsewhere" / "abs.png"
        abs_png.parent.mkdir(parents=True)
        abs_png.write_bytes(b"\x89PNGabs")
        card = _make_card(collector_number="C-02", render_path=str(abs_png))
        renders = tmp_path / "renders"
        renders.mkdir()
        out = tmp_path / "print"
        result = export_print([card], renders, out)
        assert result.copied == ["C-02"]
        # Destination is named after the card slug, not the source basename.
        assert (out / f"{card_slug(card.collector_number, card.name)}.png").exists()

    def test_falls_back_to_slug_when_render_path_missing(self, tmp_path: Path) -> None:
        # render_path points nowhere, but a slug render exists -> use the slug
        renders = tmp_path / "renders"
        card = _make_card(collector_number="C-03", render_path="renders/gone.png")
        _write_render(renders, card)
        out = tmp_path / "print"
        result = export_print([card], renders, out)
        assert result.copied == ["C-03"]

    def test_creates_out_dir(self, tmp_path: Path) -> None:
        renders = tmp_path / "renders"
        renders.mkdir()
        out = tmp_path / "does" / "not" / "exist"
        result = export_print([SAMPLE_CARDS[0]], renders, out)
        assert out.exists()
        assert result.missing_count == 1  # no render written

    def test_idempotent_rerun(self, tmp_path: Path) -> None:
        renders = tmp_path / "renders"
        _write_render(renders, SAMPLE_CARDS[0])
        out = tmp_path / "print"
        export_print([SAMPLE_CARDS[0]], renders, out)
        result = export_print([SAMPLE_CARDS[0]], renders, out)  # second run
        assert result.copied_count == 1
        assert len(list(out.glob("*.png"))) == 1

    def test_same_basename_renders_do_not_collide(self, tmp_path: Path) -> None:
        # Two distinct cards whose source renders share a basename must land as
        # two distinct files (named after each card's slug), not overwrite.
        renders = tmp_path / "renders"
        renders.mkdir()
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "card.png").write_bytes(b"AAA")
        (tmp_path / "b").mkdir()
        (tmp_path / "b" / "card.png").write_bytes(b"BBB")
        c1 = _make_card(collector_number="X-01", render_path=str(tmp_path / "a" / "card.png"))
        c2 = _make_card(collector_number="X-02", render_path=str(tmp_path / "b" / "card.png"))
        out = tmp_path / "print"
        result = export_print([c1, c2], renders, out)
        assert result.copied == ["X-01", "X-02"]
        assert len(list(out.glob("*.png"))) == 2

    def test_result_is_pydantic_model(self, tmp_path: Path) -> None:
        renders = tmp_path / "renders"
        renders.mkdir()
        result = export_print([], renders, tmp_path / "print")
        assert isinstance(result, PrintExportResult)
        assert result.copied == []
        assert result.missing == []
