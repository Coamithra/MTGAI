"""Tests for mtgai.gallery.generator — card export, static assets, gallery build."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mtgai.gallery.generator import (
    _card_to_gallery_dict,
    build_gallery,
    copy_static_assets,
    export_cards_json,
)
from mtgai.models.card import Card
from mtgai.models.enums import Color, Rarity

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
        "flavor_text": "It tramples.",
        "power": "3",
        "toughness": "3",
        "rarity": Rarity.COMMON,
        "colors": [Color.GREEN],
        "color_identity": [Color.GREEN],
        "collector_number": "G-C-01",
        "set_code": "TST",
        "card_types": ["Creature"],
        "subtypes": ["Beast"],
        "mechanic_tags": ["trample"],
        "slot_id": "G-C-01",
        "is_reprint": False,
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
# Tests: _card_to_gallery_dict
# ---------------------------------------------------------------------------


class TestCardToGalleryDict:
    """Tests for the card-to-dict serialization helper."""

    def test_basic_fields(self, tmp_path: Path) -> None:
        """All expected gallery fields are present with correct values."""
        card = _make_card()
        gallery_dir = tmp_path / "gallery"
        set_dir = tmp_path / "set"

        result = _card_to_gallery_dict(card, gallery_dir, set_dir)

        assert result["collector_number"] == "G-C-01"
        assert result["name"] == "Test Creature"
        assert result["mana_cost"] == "{2}{G}"
        assert result["cmc"] == 3.0
        assert result["colors"] == ["G"]
        assert result["color_identity"] == ["G"]
        assert result["type_line"] == "Creature -- Beast"
        assert result["oracle_text"] == "Trample"
        assert result["flavor_text"] == "It tramples."
        assert result["power"] == "3"
        assert result["toughness"] == "3"
        assert result["rarity"] == "common"
        assert result["set_code"] == "TST"
        assert result["mechanic_tags"] == ["trample"]
        assert result["slot_id"] == "G-C-01"
        assert result["is_reprint"] is False

    def test_no_extra_fields(self, tmp_path: Path) -> None:
        """The dict should not include internal pipeline fields."""
        card = _make_card()
        gallery_dir = tmp_path / "gallery"
        set_dir = tmp_path / "set"

        result = _card_to_gallery_dict(card, gallery_dir, set_dir)

        expected_keys = {
            "collector_number",
            "name",
            "mana_cost",
            "cmc",
            "colors",
            "color_identity",
            "type_line",
            "oracle_text",
            "flavor_text",
            "power",
            "toughness",
            "rarity",
            "set_code",
            "render_path",
            "art_path",
            "mechanic_tags",
            "slot_id",
            "is_reprint",
        }
        assert set(result.keys()) == expected_keys

    def test_null_image_paths(self, tmp_path: Path) -> None:
        """Cards with no art/render should have null paths."""
        card = _make_card(art_path=None, render_path=None)
        gallery_dir = tmp_path / "gallery"
        set_dir = tmp_path / "set"

        result = _card_to_gallery_dict(card, gallery_dir, set_dir)

        assert result["render_path"] is None
        assert result["art_path"] is None

    def test_relative_render_path(self, tmp_path: Path) -> None:
        """render_path should be relative to the gallery dir."""
        card = _make_card(render_path="renders/G-C-01_test_creature.png")
        gallery_dir = tmp_path / "gallery"
        set_dir = tmp_path

        result = _card_to_gallery_dict(card, gallery_dir, set_dir)

        assert result["render_path"] == "../renders/G-C-01_test_creature.png"

    def test_relative_art_path(self, tmp_path: Path) -> None:
        """art_path should be relative to the gallery dir."""
        card = _make_card(art_path="art/G-C-01_test_creature_v1.png")
        gallery_dir = tmp_path / "gallery"
        set_dir = tmp_path

        result = _card_to_gallery_dict(card, gallery_dir, set_dir)

        assert result["art_path"] == "../art/G-C-01_test_creature_v1.png"

    def test_multicolor_card(self, tmp_path: Path) -> None:
        """Multicolor cards serialize color lists correctly."""
        card = _make_card(
            colors=[Color.WHITE, Color.BLUE],
            color_identity=[Color.WHITE, Color.BLUE],
            mana_cost="{W}{U}",
            cmc=2.0,
        )
        gallery_dir = tmp_path / "gallery"
        set_dir = tmp_path / "set"

        result = _card_to_gallery_dict(card, gallery_dir, set_dir)

        assert result["colors"] == ["W", "U"]
        assert result["color_identity"] == ["W", "U"]

    def test_noncreature_card(self, tmp_path: Path) -> None:
        """Non-creature cards have null power/toughness."""
        card = _make_card(
            name="Lightning Bolt",
            type_line="Instant",
            oracle_text="Lightning Bolt deals 3 damage to any target.",
            power=None,
            toughness=None,
            mana_cost="{R}",
            cmc=1.0,
            colors=[Color.RED],
            color_identity=[Color.RED],
        )
        gallery_dir = tmp_path / "gallery"
        set_dir = tmp_path / "set"

        result = _card_to_gallery_dict(card, gallery_dir, set_dir)

        assert result["power"] is None
        assert result["toughness"] is None


# ---------------------------------------------------------------------------
# Tests: export_cards_json
# ---------------------------------------------------------------------------


class TestExportCardsJson:
    """Tests for export_cards_json."""

    @pytest.fixture(autouse=True)
    def _open_active_project(self, tmp_path: Path, monkeypatch):
        """Pin TST as the active project so ``_set_dir`` resolves.

        ``export_cards_json`` calls ``_set_dir(set_code)`` to compute
        relative paths for the gallery's render/art links; that helper
        now reads from the active project, so we have to materialise one
        before the function is called.
        """
        from mtgai.io import asset_paths
        from mtgai.runtime import active_project
        from mtgai.settings import model_settings as ms

        sets_root = tmp_path / "output" / "sets"
        settings_dir = tmp_path / "output" / "settings"
        sets_root.mkdir(parents=True, exist_ok=True)
        settings_dir.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(asset_paths, "OUTPUT_ROOT", tmp_path / "output")
        monkeypatch.setattr(asset_paths, "SETS_ROOT", sets_root)
        monkeypatch.setattr(ms, "OUTPUT_ROOT", tmp_path / "output")
        monkeypatch.setattr(ms, "SETTINGS_DIR", settings_dir)
        monkeypatch.setattr(ms, "SETS_DIR", sets_root)
        monkeypatch.setattr(ms, "GLOBAL_TOML", settings_dir / "global.toml")
        monkeypatch.setattr(ms, "LEGACY_CURRENT_TOML", settings_dir / "current.toml")
        ms.invalidate_cache()
        active_project.clear_active_set()
        ms.apply_settings("TST", ms.ModelSettings(asset_folder=str(sets_root / "TST")))
        active_project.write_active_set("TST")
        yield
        active_project.clear_active_set()
        ms.invalidate_cache()

    def test_produces_valid_json(self, tmp_path: Path) -> None:
        """The output file should contain valid JSON."""
        cards = [
            _make_card(name="Alpha", collector_number="G-C-01"),
            _make_card(name="Beta", collector_number="G-C-02"),
        ]
        output_dir = tmp_path / "gallery"

        json_path = export_cards_json("TST", output_dir, cards=cards)

        assert json_path.exists()
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 2

    def test_expected_fields_present(self, tmp_path: Path) -> None:
        """Each card dict in the JSON should have all expected fields."""
        cards = [_make_card()]
        output_dir = tmp_path / "gallery"

        json_path = export_cards_json("TST", output_dir, cards=cards)
        data = json.loads(json_path.read_text(encoding="utf-8"))

        card_dict = data[0]
        assert "collector_number" in card_dict
        assert "name" in card_dict
        assert "mana_cost" in card_dict
        assert "cmc" in card_dict
        assert "colors" in card_dict
        assert "color_identity" in card_dict
        assert "type_line" in card_dict
        assert "oracle_text" in card_dict
        assert "rarity" in card_dict
        assert "render_path" in card_dict
        assert "art_path" in card_dict
        assert "mechanic_tags" in card_dict
        assert "slot_id" in card_dict
        assert "is_reprint" in card_dict

    def test_sorted_by_collector_number(self, tmp_path: Path) -> None:
        """Cards should be sorted by collector_number in the JSON output."""
        cards = [
            _make_card(name="Zeta", collector_number="R-C-03"),
            _make_card(name="Alpha", collector_number="G-C-01"),
            _make_card(name="Mid", collector_number="G-C-02"),
        ]
        output_dir = tmp_path / "gallery"

        json_path = export_cards_json("TST", output_dir, cards=cards)
        data = json.loads(json_path.read_text(encoding="utf-8"))

        numbers = [d["collector_number"] for d in data]
        assert numbers == ["G-C-01", "G-C-02", "R-C-03"]

    def test_empty_card_set(self, tmp_path: Path) -> None:
        """An empty card list should produce an empty JSON array."""
        output_dir = tmp_path / "gallery"

        json_path = export_cards_json("TST", output_dir, cards=[])
        data = json.loads(json_path.read_text(encoding="utf-8"))

        assert data == []

    def test_output_path(self, tmp_path: Path) -> None:
        """The JSON file should be at output_dir/data/cards.json."""
        output_dir = tmp_path / "gallery"

        json_path = export_cards_json("TST", output_dir, cards=[])

        assert json_path == output_dir / "data" / "cards.json"
        assert json_path.exists()

    def test_no_pipeline_fields_in_output(self, tmp_path: Path) -> None:
        """Pipeline-internal fields should not appear in the JSON."""
        cards = [_make_card()]
        output_dir = tmp_path / "gallery"

        json_path = export_cards_json("TST", output_dir, cards=cards)
        data = json.loads(json_path.read_text(encoding="utf-8"))

        card_dict = data[0]
        assert "generation_attempts" not in card_dict
        assert "mana_cost_parsed" not in card_dict
        assert "status" not in card_dict
        assert "art_prompt" not in card_dict
        assert "design_notes" not in card_dict
        assert "created_at" not in card_dict
        assert "updated_at" not in card_dict
        assert "id" not in card_dict


# ---------------------------------------------------------------------------
# Tests: copy_static_assets
# ---------------------------------------------------------------------------


class TestCopyStaticAssets:
    """Tests for copy_static_assets."""

    def test_copies_css_and_js(self, tmp_path: Path) -> None:
        """CSS and JS files should be copied to output_dir/static/."""
        # Set up a fake templates dir with static assets
        templates_dir = tmp_path / "templates"
        static_src = templates_dir / "static"
        static_src.mkdir(parents=True)
        (static_src / "style.css").write_text("body { color: red; }")
        (static_src / "review.js").write_text("console.log('hello');")

        output_dir = tmp_path / "gallery"
        output_dir.mkdir()

        copy_static_assets(templates_dir, output_dir)

        assert (output_dir / "static" / "style.css").exists()
        assert (output_dir / "static" / "review.js").exists()
        assert (output_dir / "static" / "style.css").read_text() == "body { color: red; }"
        assert (output_dir / "static" / "review.js").read_text() == "console.log('hello');"

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        """Existing static files should be overwritten with fresh copies."""
        templates_dir = tmp_path / "templates"
        static_src = templates_dir / "static"
        static_src.mkdir(parents=True)
        (static_src / "style.css").write_text("body { color: blue; }")

        output_dir = tmp_path / "gallery"
        static_dst = output_dir / "static"
        static_dst.mkdir(parents=True)
        (static_dst / "style.css").write_text("body { color: old; }")

        copy_static_assets(templates_dir, output_dir)

        assert (output_dir / "static" / "style.css").read_text() == "body { color: blue; }"

    def test_missing_static_dir_no_error(self, tmp_path: Path) -> None:
        """If templates_dir has no static/ subdir, just log and return."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()

        output_dir = tmp_path / "gallery"
        output_dir.mkdir()

        # Should not raise
        copy_static_assets(templates_dir, output_dir)

        assert not (output_dir / "static").exists()


# ---------------------------------------------------------------------------
# Tests: build_gallery
# ---------------------------------------------------------------------------


class TestBuildGallery:
    """Tests for the build_gallery orchestrator."""

    def _patch_paths(self, monkeypatch, tmp_path: Path, set_code: str = "TST") -> None:
        """Monkeypatch artifact paths so build_gallery sees tmp_path/output.

        Routes go through :func:`set_artifact_dir` which now reads
        exclusively from the active project. Patch the whole chain
        (asset helper + settings module) and pin ``set_code`` as the
        active project with the legacy registry path as its asset
        folder so seeded files are resolved.
        """
        from mtgai.io import asset_paths
        from mtgai.runtime import active_project
        from mtgai.settings import model_settings as ms

        sets_root = tmp_path / "output" / "sets"
        settings_dir = tmp_path / "output" / "settings"
        sets_root.mkdir(parents=True, exist_ok=True)
        settings_dir.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(asset_paths, "OUTPUT_ROOT", tmp_path / "output")
        monkeypatch.setattr(asset_paths, "SETS_ROOT", sets_root)
        monkeypatch.setattr(ms, "OUTPUT_ROOT", tmp_path / "output")
        monkeypatch.setattr(ms, "SETTINGS_DIR", settings_dir)
        monkeypatch.setattr(ms, "SETS_DIR", sets_root)
        monkeypatch.setattr(ms, "GLOBAL_TOML", settings_dir / "global.toml")
        monkeypatch.setattr(ms, "LEGACY_CURRENT_TOML", settings_dir / "current.toml")
        ms.invalidate_cache()
        active_project.clear_active_set()
        ms.apply_settings(set_code, ms.ModelSettings(asset_folder=str(sets_root / set_code)))
        active_project.write_active_set(set_code)
        monkeypatch.setattr(
            "mtgai.gallery.generator._templates_dir",
            lambda: (
                Path(__file__).resolve().parent.parent.parent / "mtgai" / "gallery" / "templates"
            ),
        )

    def test_creates_directory_structure(self, tmp_path: Path, monkeypatch) -> None:
        """build_gallery should create gallery/, data/, and static/ dirs."""
        # Set up a fake set with cards
        set_code = "TST"
        set_dir = tmp_path / "output" / "sets" / set_code
        cards_dir = set_dir / "cards"
        cards_dir.mkdir(parents=True)
        card = _make_card()
        _write_card_json(cards_dir, card)

        gallery_dir = set_dir / "gallery"

        # Monkeypatch the path helpers to use tmp_path
        self._patch_paths(monkeypatch, tmp_path)

        result = build_gallery(set_code, gallery_dir)

        assert result == gallery_dir
        assert gallery_dir.exists()
        assert (gallery_dir / "data").exists()
        assert (gallery_dir / "data" / "cards.json").exists()
        assert (gallery_dir / "static").exists()
        assert (gallery_dir / "index.html").exists()

    def test_cards_json_content(self, tmp_path: Path, monkeypatch) -> None:
        """The cards.json produced by build_gallery should contain card data."""
        set_code = "TST"
        set_dir = tmp_path / "output" / "sets" / set_code
        cards_dir = set_dir / "cards"
        cards_dir.mkdir(parents=True)

        card1 = _make_card(name="Alpha", collector_number="G-C-01")
        card2 = _make_card(name="Beta", collector_number="G-C-02")
        _write_card_json(cards_dir, card1)
        _write_card_json(cards_dir, card2)

        gallery_dir = set_dir / "gallery"

        self._patch_paths(monkeypatch, tmp_path)

        build_gallery(set_code, gallery_dir)

        data = json.loads((gallery_dir / "data" / "cards.json").read_text(encoding="utf-8"))
        assert len(data) == 2
        names = [d["name"] for d in data]
        assert "Alpha" in names
        assert "Beta" in names

    def test_static_assets_copied(self, tmp_path: Path, monkeypatch) -> None:
        """build_gallery should copy CSS/JS from templates to output."""
        set_code = "TST"
        set_dir = tmp_path / "output" / "sets" / set_code
        cards_dir = set_dir / "cards"
        cards_dir.mkdir(parents=True)

        gallery_dir = set_dir / "gallery"

        self._patch_paths(monkeypatch, tmp_path)

        build_gallery(set_code, gallery_dir)

        # The real templates dir has style.css
        assert (gallery_dir / "static" / "style.css").exists()

    def test_index_html_rendered(self, tmp_path: Path, monkeypatch) -> None:
        """build_gallery should render base.html as index.html."""
        set_code = "TST"
        set_dir = tmp_path / "output" / "sets" / set_code
        cards_dir = set_dir / "cards"
        cards_dir.mkdir(parents=True)

        gallery_dir = set_dir / "gallery"

        self._patch_paths(monkeypatch, tmp_path)

        build_gallery(set_code, gallery_dir)

        index_html = (gallery_dir / "index.html").read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in index_html
        assert "MTGAI" in index_html

    def test_returns_output_path(self, tmp_path: Path, monkeypatch) -> None:
        """build_gallery should return the gallery output directory."""
        set_code = "TST"
        set_dir = tmp_path / "output" / "sets" / set_code
        cards_dir = set_dir / "cards"
        cards_dir.mkdir(parents=True)

        gallery_dir = set_dir / "gallery"

        self._patch_paths(monkeypatch, tmp_path)

        result = build_gallery(set_code, gallery_dir)

        assert result == gallery_dir
