"""Legendary crown coverage: every legendary permanent gets the crown, not just creatures.

``render_card`` used to gate the crown on ``"legendary" in type AND "creature" in type``,
so a legendary artifact/enchantment/land rendered crownless. Real M15+ frames crown every
legendary card except planeswalkers (whose frame has no crown). These tests render each
card type with and without the Legendary supertype and assert the crown zone (above the
art window) differs — the crown underlay + overlay are the only compositing difference
there for an otherwise-identical card.
"""

from __future__ import annotations

import pytest
from PIL import ImageChops

from mtgai.models.card import Card
from mtgai.rendering.card_renderer import CardRenderer
from mtgai.rendering.layout import CANVAS_H, CANVAS_W, FRAME_H, NATIVE_ART_WINDOW
from mtgai.runtime import active_project
from mtgai.settings.model_settings import ModelSettings

# Scaled row of the art window top in the final render; the crown zone sits above it.
# Pull the crop in a few rows so LANCZOS edge blending can't bleed across.
_CROWN_BAND_BOTTOM = int(NATIVE_ART_WINDOW.top * (CANVAS_H / FRAME_H)) - 4


@pytest.fixture
def open_project(tmp_path):
    settings = ModelSettings(asset_folder=str(tmp_path))
    active_project.write_active_project(
        active_project.ProjectState(set_code="TST", settings=settings)
    )
    yield
    active_project.clear_active_project()


def _crown_band(renderer: CardRenderer, type_line: str, identity: list[str]):
    card = Card(name="Test Card", type_line=type_line, color_identity=identity)
    img = renderer.render_card(card)
    return img.crop((0, 0, CANVAS_W, _CROWN_BAND_BOTTOM))


@pytest.mark.parametrize(
    ("type_line", "identity"),
    [
        ("Artifact — Equipment", []),
        ("Enchantment", ["W"]),
        ("Land", []),
        ("Creature — Elf", ["G"]),  # the previously-crowned case must keep its crown
        ("Sorcery", ["W"]),  # Dominaria legendary sorceries carry the crown
    ],
)
def test_legendary_permanent_renders_with_crown(open_project, type_line, identity):
    r = CardRenderer()
    plain = _crown_band(r, type_line, identity)
    legendary = _crown_band(r, f"Legendary {type_line}", identity)
    diff = ImageChops.difference(plain, legendary)
    assert diff.getbbox() is not None, f"no crown rendered for 'Legendary {type_line}'"


def test_legendary_planeswalker_renders_without_crown(open_project):
    # Real planeswalker frames have no crown; until the dedicated planeswalker
    # frame template exists they render on the generic frame, still crownless.
    r = CardRenderer()
    plain = _crown_band(r, "Planeswalker — Test", ["U"])
    legendary = _crown_band(r, "Legendary Planeswalker — Test", ["U"])
    assert ImageChops.difference(plain, legendary).getbbox() is None


def test_non_legendary_renders_are_stable(open_project):
    # Two renders of the same non-legendary card are pixel-identical in the crown
    # zone — the diff above can only come from the crown, not render noise.
    r = CardRenderer()
    a = _crown_band(r, "Artifact — Equipment", [])
    b = _crown_band(r, "Artifact — Equipment", [])
    assert ImageChops.difference(a, b).getbbox() is None


def test_load_legendary_crown_routes_artifact_and_land():
    r = CardRenderer()
    artifact = Card(name="T", type_line="Legendary Artifact", color_identity=[])
    land = Card(name="T", type_line="Legendary Land", color_identity=[])
    assert r._load_legendary_crown(artifact) is not None  # crowns/Artifact.png
    assert r._load_legendary_crown(land) is not None  # crowns/Land.png
