"""Two-colour frame treatment: cost-derived split|gold + gradient pair crowns.

Card 6a28a052 replaced the old ``SetParams.two_color_frame`` project toggle with
the real-Magic canon rule: a two-colour card's frame is a pure function of its
**mana cost**. An all-hybrid-of-the-pair cost ({G/U}{G/U}, {1}{R/W}) wears the
two-tone split frame (what the committed split assets were stacked from); a plain
gold cost ({G}{U}, {1}{W}{B}), any mix of plain + hybrid pips, or no cost at all
collapses to the flat gold M frame. The legendary crown follows the same choice
(gradient-blended pair crown for split, Gold crown for M).

Earlier (card 6a2881ee) the two-colour legendary crowns gained their gradient
seam, synthesized at load time by blending the mono crowns instead of the
hard-split committed pair PNGs (kept as fallback when a mono source is missing) —
those synthesis tests are retained below.
"""

from __future__ import annotations

from PIL import Image

from mtgai.models.card import Card
from mtgai.rendering.card_renderer import CardRenderer


def _card(type_line: str, identity: list[str], mana_cost: str = "") -> Card:
    return Card(
        name="Test Card",
        type_line=type_line,
        color_identity=identity,
        mana_cost=mana_cost,
    )


# ---------------------------------------------------------------------------
# Cost-derived frame-key routing
# ---------------------------------------------------------------------------


def test_all_hybrid_pair_cost_gets_split_key():
    r = CardRenderer()
    # Every colored pip is a hybrid spanning the card's two colours -> split.
    assert r.determine_frame_key(_card("Creature — Wizard", ["U", "W"], "{W/U}{W/U}")) == "WU"
    # A single hybrid pip + generic is still all-hybrid-of-the-pair -> split.
    assert r.determine_frame_key(_card("Creature — Wizard", ["R", "W"], "{1}{R/W}")) == "WR"


def test_plain_gold_pair_cost_collapses_to_m():
    r = CardRenderer()
    # Plain colored pips -> the flat gold M frame (canon for gold costs).
    assert r.determine_frame_key(_card("Creature — Wizard", ["U", "W"], "{W}{U}")) == "M"
    assert r.determine_frame_key(_card("Creature — Wizard", ["W", "B"], "{1}{W}{B}")) == "M"


def test_mixed_hybrid_and_plain_cost_collapses_to_m():
    r = CardRenderer()
    # A plain colored pip alongside a hybrid -> gold M (the real-card pattern is
    # ALL-hybrid; any plain colored pip breaks the split).
    assert r.determine_frame_key(_card("Creature — Wizard", ["U", "W"], "{W/U}{W}")) == "M"
    assert r.determine_frame_key(_card("Creature — Wizard", ["G", "U"], "{G/U}{U}")) == "M"


def test_two_color_card_with_no_cost_is_gold():
    r = CardRenderer()
    # No cost (back faces, etc.) -> no hybrid signal -> gold M.
    assert r.determine_frame_key(_card("Creature — Wizard", ["U", "W"], "")) == "M"


def test_phyrexian_pip_counts_as_plain_color_not_hybrid_pair():
    r = CardRenderer()
    # {W/P} is a single-colour (W) pip — P is not a colour — so {W/P}{U} is a
    # plain W pip + plain U pip = gold M, NOT a WU split.
    assert r.determine_frame_key(_card("Creature — Wizard", ["U", "W"], "{W/P}{U}")) == "M"


def test_mono_color_twobrid_keeps_mono_frame():
    r = CardRenderer()
    # A lone twobrid {2/W} is a mono-colour card -> the mono W frame, untouched
    # (the split-vs-gold collapse only applies to a 2-colour identity).
    assert r.determine_frame_key(_card("Creature — Wizard", ["W"], "{2/W}")) == "W"


def test_mono_and_multicolor_are_untouched():
    r = CardRenderer()
    assert r.determine_frame_key(_card("Creature — Elf", ["G"], "{G}")) == "G"
    assert r.determine_frame_key(_card("Creature — Dragon", ["U", "B", "R"], "{U}{B}{R}")) == "M"


def test_cost_derived_routing_leaves_artifacts_and_lands_alone():
    r = CardRenderer()
    # Two-colour artifacts keep the gold-tinted AM frame regardless of cost;
    # two-colour lands stay lm (lands have no cost anyway).
    assert r.determine_frame_key(_card("Artifact — Equipment", ["W", "U"], "{2}")) == "AM"
    assert r.determine_frame_key(_card("Land", ["W", "U"], "")) == "lm"


# ---------------------------------------------------------------------------
# Crown routing follows the frame key
# ---------------------------------------------------------------------------


def test_plain_gold_pair_crown_is_gold():
    r = CardRenderer()
    two = r._load_legendary_crown(_card("Legendary Creature — Wizard", ["W", "U"], "{W}{U}"))
    three = r._load_legendary_crown(
        _card("Legendary Creature — Dragon", ["U", "B", "R"], "{U}{B}{R}")
    )
    assert two is not None and three is not None
    # A plain gold two-colour cost takes the cached Gold crown like 3+ colours.
    assert two is three


def test_hybrid_pair_crown_differs_from_gold():
    r = CardRenderer()
    two = r._load_legendary_crown(_card("Legendary Creature — Wizard", ["W", "U"], "{W/U}{W/U}"))
    gold = r._load_legendary_crown(
        _card("Legendary Creature — Dragon", ["U", "B", "R"], "{U}{B}{R}")
    )
    assert two is not None and gold is not None
    # The hybrid pair gets the synthesized split crown, not the Gold one.
    assert two is not gold


# ---------------------------------------------------------------------------
# Gradient pair crown synthesis (card 6a2881ee — retained)
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


def test_split_crown_is_synthesized_not_the_committed_png(monkeypatch):
    # The loaded WU crown overlay must route through the gradient blend, not
    # the hard-split committed pair PNG: spy on _blend_pair_crown and assert
    # its result is what the overlay is built from.
    r = CardRenderer()
    calls: list[str] = []
    real_blend = CardRenderer._blend_pair_crown

    def spy(self, pair, crown_dir):
        calls.append(pair)
        return real_blend(self, pair, crown_dir)

    monkeypatch.setattr(CardRenderer, "_blend_pair_crown", spy)
    overlay = r._load_legendary_crown(
        _card("Legendary Creature — Wizard", ["W", "U"], "{W/U}{W/U}")
    )
    assert overlay is not None
    assert calls == ["WU"]

    # Sanity: the synthesized crown is not byte-identical to the committed one
    # (the committed PNG hard-splits at center; the blend has a gradient seam).
    crown_dir = r.assets_root / "frames" / "m15" / "crowns"
    committed = Image.open(crown_dir / "WU.png").convert("RGBA")
    blended = r._blend_pair_crown("WU", crown_dir)
    assert blended is not None
    assert blended.tobytes() != committed.tobytes()


def test_split_crown_falls_back_to_committed_png_when_blend_unavailable(monkeypatch):
    # When a mono source is missing (_blend_pair_crown -> None) the loader
    # falls back to the committed crowns/WU.png and still produces a crown.
    r = CardRenderer()
    monkeypatch.setattr(CardRenderer, "_blend_pair_crown", lambda self, pair, crown_dir: None)
    overlay = r._load_legendary_crown(
        _card("Legendary Creature — Wizard", ["W", "U"], "{W/U}{W/U}")
    )
    assert overlay is not None
    gold = r._load_legendary_crown(
        _card("Legendary Creature — Dragon", ["U", "B", "R"], "{U}{B}{R}")
    )
    assert overlay is not gold
