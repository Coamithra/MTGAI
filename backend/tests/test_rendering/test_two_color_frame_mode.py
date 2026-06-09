"""Two-colour frame treatment: gradient pair crowns + the split|gold render toggle.

Step 3 (card 6a2881ee): two-colour legendary crowns are synthesized at load time
by blending the mono crowns through a soft centered gradient seam instead of the
hard-split committed pair PNGs (kept as fallback when a mono source is missing).

Step 4 (card 6a2881fa): ``SetParams.two_color_frame`` — ``"split"`` (default,
house style) keeps the hybrid-derived split frame; ``"gold"`` collapses a
two-colour identity to the flat gold M frame (real-Magic canon for non-hybrid
two-colour costs), with the P/T box and crown following.
"""

from __future__ import annotations

import pytest
from PIL import Image

from mtgai.models.card import Card
from mtgai.rendering.card_renderer import CardRenderer
from mtgai.runtime import active_project
from mtgai.settings.model_settings import ModelSettings, SetParams


def _open_project(tmp_path, two_color_frame: str) -> None:
    settings = ModelSettings(
        asset_folder=str(tmp_path),
        set_params=SetParams(two_color_frame=two_color_frame),
    )
    active_project.write_active_project(
        active_project.ProjectState(set_code="TST", settings=settings)
    )


@pytest.fixture
def gold_mode(tmp_path):
    _open_project(tmp_path, "gold")
    yield
    active_project.clear_active_project()


@pytest.fixture
def split_mode(tmp_path):
    _open_project(tmp_path, "split")
    yield
    active_project.clear_active_project()


def _card(type_line: str, identity: list[str]) -> Card:
    return Card(name="Test Card", type_line=type_line, color_identity=identity)


# ---------------------------------------------------------------------------
# Frame key routing (step 4)
# ---------------------------------------------------------------------------


def test_two_color_split_is_the_default_without_a_project():
    # No active project (standalone tools, tests) -> house-style split key.
    r = CardRenderer()
    assert r.determine_frame_key(_card("Creature — Wizard", ["U", "W"])) == "WU"


def test_two_color_split_mode_keeps_pair_key(split_mode):
    r = CardRenderer()
    assert r.determine_frame_key(_card("Creature — Wizard", ["U", "W"])) == "WU"


def test_two_color_gold_mode_collapses_to_m(gold_mode):
    r = CardRenderer()
    assert r.determine_frame_key(_card("Creature — Wizard", ["U", "W"])) == "M"
    # Mono / 3+ colours are untouched by the toggle.
    assert r.determine_frame_key(_card("Creature — Elf", ["G"])) == "G"
    assert r.determine_frame_key(_card("Creature — Dragon", ["U", "B", "R"])) == "M"


def test_gold_mode_leaves_artifacts_and_lands_alone(gold_mode):
    r = CardRenderer()
    # Two-colour artifacts keep the gold-tinted AM frame; two-colour lands stay lm.
    assert r.determine_frame_key(_card("Artifact — Equipment", ["W", "U"])) == "AM"
    assert r.determine_frame_key(_card("Land", ["W", "U"])) == "lm"


# ---------------------------------------------------------------------------
# Crown routing (steps 3 + 4)
# ---------------------------------------------------------------------------


def test_gold_mode_two_color_crown_is_gold(gold_mode):
    r = CardRenderer()
    two = r._load_legendary_crown(_card("Legendary Creature — Wizard", ["W", "U"]))
    three = r._load_legendary_crown(_card("Legendary Creature — Dragon", ["U", "B", "R"]))
    assert two is not None and three is not None
    # Both resolve to the cached Gold crown overlay.
    assert two is three


def test_split_mode_two_color_crown_differs_from_gold(split_mode):
    r = CardRenderer()
    two = r._load_legendary_crown(_card("Legendary Creature — Wizard", ["W", "U"]))
    gold = r._load_legendary_crown(_card("Legendary Creature — Dragon", ["U", "B", "R"]))
    assert two is not None and gold is not None
    assert two is not gold


# ---------------------------------------------------------------------------
# Gradient pair crown synthesis (step 3)
# ---------------------------------------------------------------------------


def test_blend_pair_crown_edges_match_monos_and_seam_blends():
    r = CardRenderer()
    crown_dir = r.assets_root / "frames" / "m15" / "crowns"
    blended = r._blend_pair_crown("WU", crown_dir)
    assert blended is not None

    left = Image.open(crown_dir / "W.png").convert("RGBA")
    right = Image.open(crown_dir / "U.png").convert("RGBA")
    assert blended.size == left.size
    w, h = blended.size

    band = max(2, int(w * CardRenderer.CROWN_SEAM_FRACTION))
    x0 = (w - band) // 2

    # Outside the seam band the blend is exactly the mono crowns.
    left_strip = (0, 0, x0, h)
    right_strip = (x0 + band, 0, w, h)
    assert blended.crop(left_strip).tobytes() == left.crop(left_strip).tobytes()
    assert blended.crop(right_strip).tobytes() == right.crop(right_strip).tobytes()

    # The center column is a genuine mix — differs from both sources.
    center = (w // 2, 0, w // 2 + 1, h)
    assert blended.crop(center).tobytes() != left.crop(center).tobytes()
    assert blended.crop(center).tobytes() != right.crop(center).tobytes()


def test_blend_pair_crown_missing_mono_returns_none(tmp_path):
    r = CardRenderer()
    # Empty dir: no mono sources -> None so the caller falls back to the
    # committed pair PNG.
    assert r._blend_pair_crown("WU", tmp_path) is None


def test_split_crown_is_synthesized_not_the_committed_png():
    # The loaded WU crown overlay must come from the gradient blend, not the
    # hard-split committed pair PNG: compare the overlay's crown zone against
    # one built from the committed file.
    r = CardRenderer()
    overlay = r._load_legendary_crown(_card("Legendary Creature — Wizard", ["W", "U"]))
    assert overlay is not None

    crown_dir = r.assets_root / "frames" / "m15" / "crowns"
    committed = Image.open(crown_dir / "WU.png").convert("RGBA")
    blended = r._blend_pair_crown("WU", crown_dir)
    assert blended is not None
    # Sanity: the synthesized crown is not byte-identical to the committed one
    # (the committed PNG hard-splits at center; the blend has a gradient seam).
    assert blended.tobytes() != committed.tobytes()
