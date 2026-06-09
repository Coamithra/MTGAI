"""Tests for colored-artifact frame selection.

Colored artifacts (artifact + color identity) now map to a tinted frame
``AW``..``AG`` / ``AM`` instead of the flat gray ``A``. These tests pin the
key-derivation logic (``colors.artifact_frame_key``), the filename mapping
(``layout.frame_path`` / ``pt_box_path``), and the renderer's
``determine_frame_key`` dispatch — no image compositing, so they run without
the frame PNGs present.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from mtgai.models.card import Card
from mtgai.models.enums import Color, Rarity
from mtgai.rendering.card_renderer import CardRenderer
from mtgai.rendering.colors import artifact_frame_key
from mtgai.rendering.layout import frame_path, pt_box_path


def _make_card(**overrides) -> Card:
    defaults = {
        "name": "Test Artifact",
        "mana_cost": "{2}",
        "cmc": 2.0,
        "type_line": "Artifact",
        "oracle_text": "",
        "rarity": Rarity.RARE,
        "color_identity": [],
        "collector_number": "001",
        "set_code": "TST",
    }
    defaults.update(overrides)
    return Card(**defaults)


class TestArtifactFrameKey:
    def test_colorless_artifact_stays_gray(self):
        assert artifact_frame_key([]) == "A"

    @pytest.mark.parametrize(
        ("color", "expected"),
        [("W", "AW"), ("U", "AU"), ("B", "AB"), ("R", "AR"), ("G", "AG")],
    )
    def test_mono_color_artifact(self, color, expected):
        assert artifact_frame_key([color]) == expected

    def test_multicolor_artifact_is_gold(self):
        assert artifact_frame_key(["U", "B"]) == "AM"
        assert artifact_frame_key(["W", "U", "B"]) == "AM"

    def test_order_independent(self):
        assert artifact_frame_key(["B", "U"]) == artifact_frame_key(["U", "B"]) == "AM"


class TestFramePathArtifactKeys:
    @pytest.mark.parametrize("key", ["AW", "AU", "AB", "AR", "AG", "AM"])
    def test_frame_path_filename(self, key):
        assert frame_path(key).name == f"m15Frame{key}.png"

    @pytest.mark.parametrize("key", ["AW", "AU", "AB", "AR", "AG", "AM"])
    def test_pt_box_path_filename(self, key):
        assert pt_box_path(key).name == f"m15PT{key}.png"

    def test_single_color_keys_unchanged(self):
        assert frame_path("A").name == "m15FrameA.png"
        assert frame_path("W").name == "m15FrameW.png"
        assert pt_box_path("A").name == "m15PTA.png"

    def test_land_keys_unchanged(self):
        # Lowercase land variants must still resolve to their own files,
        # not be swallowed by the new two-letter artifact branch.
        assert frame_path("lw").name == "lw.png"
        assert frame_path("lm").name == "lm.png"


class TestDetermineFrameKey:
    def setup_method(self):
        self.renderer = CardRenderer()

    def test_colored_artifact(self):
        card = _make_card(type_line="Artifact", color_identity=[Color.WHITE])
        assert self.renderer.determine_frame_key(card) == "AW"

    def test_colored_artifact_creature(self):
        card = _make_card(
            type_line="Artifact Creature — Construct",
            color_identity=[Color.RED],
            power="3",
            toughness="3",
        )
        assert self.renderer.determine_frame_key(card) == "AR"

    def test_colorless_artifact(self):
        card = _make_card(type_line="Artifact", color_identity=[])
        assert self.renderer.determine_frame_key(card) == "A"

    def test_multicolor_artifact(self):
        card = _make_card(type_line="Artifact", color_identity=[Color.WHITE, Color.BLUE])
        assert self.renderer.determine_frame_key(card) == "AM"

    def test_artifact_land_uses_land_frame(self):
        # An artifact *land* is a land first — it must not get an artifact key.
        card = _make_card(type_line="Artifact Land", color_identity=[])
        assert self.renderer.determine_frame_key(card) == "L"

    def test_non_artifact_unaffected(self):
        card = _make_card(
            type_line="Creature — Bear", color_identity=[Color.GREEN], power="2", toughness="2"
        )
        assert self.renderer.determine_frame_key(card) == "G"
