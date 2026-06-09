"""Frame-key resolution + two-color split frame assets.

Covers the multicolor (two-color) split frame work: ``colors.frame_key_for_identity`` /
``two_color_key``, ``layout.frame_path`` / ``pt_box_path``, ``CardRenderer.determine_frame_key``,
that the generated ``m15Frame<PAIR>`` assets exist, load, and carry the gold ``m15FrameM``
bars, and that a split key's P/T box resolves to the shared gold ``m15PTM``.
"""

from __future__ import annotations

import pytest
from PIL import Image, ImageChops

from mtgai.models.card import Card
from mtgai.rendering.card_renderer import CardRenderer
from mtgai.rendering.colors import frame_key_for_identity, two_color_key
from mtgai.rendering.layout import FRAME_H, FRAME_W, frame_path, pt_box_path

# All ten colour pairs in canonical WUBRG order (matches the asset filenames).
PAIRS = ["WU", "WB", "WR", "WG", "UB", "UR", "UG", "BR", "BG", "RG"]


def _card(type_line: str, identity: list[str]) -> Card:
    return Card(name="Test Card", type_line=type_line, color_identity=identity)


# --------------------------------------------------------------------------- #
# two_color_key — canonical WUBRG ordering, input order irrelevant
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("colors", "expected"),
    [
        (["U", "W"], "WU"),
        (["W", "U"], "WU"),
        (["G", "W"], "WG"),
        (["R", "B"], "BR"),
        (["G", "R"], "RG"),
        (["B", "U"], "UB"),
    ],
)
def test_two_color_key_canonical_order(colors, expected):
    assert two_color_key(colors) == expected


# --------------------------------------------------------------------------- #
# frame_key_for_identity
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("identity", "expected"),
    [
        ([], "A"),
        (["W"], "W"),
        (["G"], "G"),
        (["U", "W"], "WU"),  # two-color split
        (["R", "G"], "RG"),
        (["W", "U", "B"], "M"),  # three colors -> gold
        (["W", "U", "B", "R", "G"], "M"),
    ],
)
def test_frame_key_for_identity_nonland(identity, expected):
    assert frame_key_for_identity(identity, is_land=False) == expected


@pytest.mark.parametrize(
    ("identity", "expected"),
    [
        ([], "L"),
        (["W"], "lw"),
        (["U"], "lu"),
        (["W", "U"], "lm"),  # multicolor land stays gold-land
        (["W", "U", "B"], "lm"),
    ],
)
def test_frame_key_for_identity_land(identity, expected):
    assert frame_key_for_identity(identity, is_land=True) == expected


# --------------------------------------------------------------------------- #
# CardRenderer.determine_frame_key
# --------------------------------------------------------------------------- #
def test_determine_frame_key_two_color_creature():
    assert CardRenderer().determine_frame_key(_card("Creature — Bird", ["U", "W"])) == "WU"


def test_determine_frame_key_two_color_artifact_is_not_split():
    # Artifacts route through artifact_frame_key, not the two-color split: a
    # multicolor artifact gets the gold-tinted "AM", never "WU".
    card = _card("Artifact — Equipment", ["U", "W"])
    assert CardRenderer().determine_frame_key(card) == "AM"


def test_determine_frame_key_mono_and_colorless_and_tricolor():
    r = CardRenderer()
    assert r.determine_frame_key(_card("Creature — Elf", ["G"])) == "G"
    assert r.determine_frame_key(_card("Artifact", [])) == "A"
    assert r.determine_frame_key(_card("Creature — Spirit", ["W", "U", "B"])) == "M"


def test_determine_frame_key_two_color_land_is_gold_land():
    assert CardRenderer().determine_frame_key(_card("Land", ["U", "W"])) == "lm"


# --------------------------------------------------------------------------- #
# layout path mapping
# --------------------------------------------------------------------------- #
def test_frame_path_keys():
    assert frame_path("WU").name == "m15FrameWU.png"
    assert frame_path("W").name == "m15FrameW.png"
    assert frame_path("M").name == "m15FrameM.png"
    assert frame_path("lw").name == "lw.png"


def test_pt_box_path_keys():
    # Two-color split keys map to the gold M box (real hybrid/gold convention);
    # there are no per-pair P/T assets.
    assert pt_box_path("WU").name == "m15PTM.png"
    assert pt_box_path("W").name == "m15PTW.png"
    assert pt_box_path("M").name == "m15PTM.png"
    assert pt_box_path("AW").name == "m15PTAW.png"  # colored artifact keeps its tint
    assert pt_box_path("lw").name == "m15PTW.png"  # land -> first color


# --------------------------------------------------------------------------- #
# Generated assets exist and load at the expected size
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("pair", PAIRS)
def test_two_color_frame_asset_exists(pair):
    fp = frame_path(pair)
    assert fp.is_file(), f"missing {fp}"
    with Image.open(fp) as img:
        assert img.size == (FRAME_W, FRAME_H)


def test_two_color_pt_box_resolves_to_gold():
    # Every split key resolves to the one shared gold box; check the file once.
    pp = pt_box_path("WU")
    assert pp.name == "m15PTM.png"
    assert pp.is_file(), f"missing {pp}"
    with Image.open(pp) as img:
        assert img.size == (377, 206)


@pytest.mark.parametrize("pair", PAIRS)
def test_two_color_frame_has_gold_bars(pair):
    """The split frames carry m15FrameM's gold title/type bars verbatim.

    generate_two_color_frames._clean_bars pastes the gold frame through the
    title/type masks, so where a mask is fully opaque the split frame's RGB
    must equal the gold frame's exactly (the canonical hybrid-card look).
    """
    frames_dir = frame_path("M").parent
    gold = Image.open(frames_dir / "m15FrameM.png").convert("RGB")
    split = Image.open(frame_path(pair)).convert("RGB")
    black = Image.new("RGB", gold.size, (0, 0, 0))
    for mask_name in ("m15MaskTitle", "m15MaskType"):
        mask = Image.open(frames_dir / f"{mask_name}.png").convert("RGBA").split()[3]
        solid = mask.point(lambda a: 255 if a == 255 else 0)
        assert solid.getbbox() is not None, f"{mask_name} has no fully-opaque pixels"
        diff = ImageChops.difference(split, gold)
        masked_diff = Image.composite(diff, black, solid)
        assert masked_diff.getbbox() is None, (
            f"{pair} {mask_name} zone is not the gold m15FrameM bar"
        )


# --------------------------------------------------------------------------- #
# Renderer loads the split assets without falling back
# --------------------------------------------------------------------------- #
def test_renderer_loads_two_color_frame_and_pt_box():
    r = CardRenderer()
    frame = r._load_frame("WU")
    assert frame.size == (FRAME_W, FRAME_H)
    pt = r._load_pt_box("WU")
    assert pt.size == (377, 206)


def test_renderer_loads_two_color_legendary_crown():
    r = CardRenderer()
    crown = r._load_legendary_crown(_card("Legendary Creature — Bird", ["U", "W"]))
    assert crown is not None  # crowns/WU.png exists
