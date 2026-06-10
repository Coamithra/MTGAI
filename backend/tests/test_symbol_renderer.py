"""Tests for SVG path tracing in symbol_renderer.

``_draw_svg_path_data`` imports ``svg.path`` lazily inside the function, so the
tests inject a lightweight fake ``svg.path`` module and a recording Cairo
context. This lets us assert the emitted Cairo operations without pycairo or
svg.path installed.
"""

import sys
import types

import pytest

# symbol_renderer (via mtgai.rendering.__init__ -> fonts) imports Pillow at
# module load; skip the whole module where Pillow is unavailable.
pytest.importorskip("PIL")

from mtgai.rendering import symbol_renderer


class _RecordingCtx:
    """Records Cairo path ops as ``(op, *args)`` tuples."""

    def __init__(self) -> None:
        self.ops: list[tuple] = []

    def move_to(self, x, y):
        self.ops.append(("move_to", x, y))

    def line_to(self, x, y):
        self.ops.append(("line_to", x, y))

    def curve_to(self, *args):
        self.ops.append(("curve_to", *args))

    def close_path(self):
        self.ops.append(("close_path",))


class _Pt:
    def __init__(self, real, imag):
        self.real = real
        self.imag = imag


class _FakeArc:
    """An Arc segment with a fixed start and a linear point sampler."""

    def __init__(self, start, end):
        self.start = start
        self.end = end

    def point(self, t):
        return _Pt(self.start.real + t, self.start.imag + t)


class _FakeMove:
    def __init__(self, end):
        self.end = end


@pytest.fixture
def fake_svg_path(monkeypatch):
    """Install a fake ``svg.path`` module yielding caller-supplied segments."""
    segments: list = []

    fake = types.ModuleType("svg.path")
    fake.Arc = _FakeArc
    fake.Move = _FakeMove
    # Distinct sentinel classes so isinstance checks never accidentally match.
    fake.Close = type("Close", (), {})
    fake.CubicBezier = type("CubicBezier", (), {})
    fake.Line = type("Line", (), {})
    fake.QuadraticBezier = type("QuadraticBezier", (), {})
    fake.parse_path = lambda d: list(segments)

    parent = types.ModuleType("svg")
    parent.path = fake
    monkeypatch.setitem(sys.modules, "svg", parent)
    monkeypatch.setitem(sys.modules, "svg.path", fake)
    return segments


def test_arc_emits_move_to_before_sampling(fake_svg_path):
    """An Arc opening a subpath must start with move_to(seg.start), not just
    line_to from the previous position (regression: distorted geometry)."""
    fake_svg_path.append(_FakeArc(_Pt(5.0, 7.0), _Pt(25.0, 27.0)))

    ctx = _RecordingCtx()
    symbol_renderer._draw_svg_path_data(ctx, "ignored")

    assert ctx.ops[0] == ("move_to", 5.0, 7.0)
    # Followed by the 20 sampled line_to points.
    assert all(op[0] == "line_to" for op in ctx.ops[1:])
    assert len(ctx.ops) == 1 + 20


def test_arc_following_other_segment_still_moves_to_its_start(fake_svg_path):
    """Even mid-path, the Arc re-anchors at its own start so it can't inherit a
    stale pen position from a preceding Move/Close."""
    fake_svg_path.extend(
        [
            _FakeMove(_Pt(0.0, 0.0)),
            _FakeArc(_Pt(10.0, 10.0), _Pt(30.0, 30.0)),
        ]
    )

    ctx = _RecordingCtx()
    symbol_renderer._draw_svg_path_data(ctx, "ignored")

    assert ctx.ops[0] == ("move_to", 0.0, 0.0)  # the Move
    assert ctx.ops[1] == ("move_to", 10.0, 10.0)  # the Arc re-anchors
    assert ctx.ops[2][0] == "line_to"


# ---------------------------------------------------------------------------
# _parse_svg_color — 3-digit hex shorthand
# ---------------------------------------------------------------------------


def test_parse_svg_color_full_hex():
    assert symbol_renderer._parse_svg_color("#CAC5C0") == pytest.approx(
        (0xCA / 255, 0xC5 / 255, 0xC0 / 255)
    )


@pytest.mark.parametrize(
    ("shorthand", "expected"),
    [
        ("#000", (0.0, 0.0, 0.0)),
        ("#fff", (1.0, 1.0, 1.0)),
        ("#f00", (1.0, 0.0, 0.0)),
        ("#abc", (0xAA / 255, 0xBB / 255, 0xCC / 255)),
    ],
)
def test_parse_svg_color_shorthand_expands(shorthand, expected):
    """3-digit ``#RGB`` shorthand must expand (#000 -> #000000), not return None.

    Regression: the {C} colorless symbol's diamond path is ``fill='#000'``; an
    un-expanded shorthand parsed as None, so the diamond was dropped and {C}
    rendered as a featureless grey circle (Trello card 239 / Fnz4C8UH)."""
    assert symbol_renderer._parse_svg_color(shorthand) == pytest.approx(expected)


@pytest.mark.parametrize(
    "bad",
    [None, "", "none", "rgb(0,0,0)", "#12", "#12345", "#xyz", "#GGGGGG"],
)
def test_parse_svg_color_rejects_unparseable(bad):
    """Unparseable input returns None — including correct-length strings whose
    digits aren't valid hex (``#xyz`` / ``#GGGGGG``), which must not raise."""
    assert symbol_renderer._parse_svg_color(bad) is None


# ---------------------------------------------------------------------------
# Compound mana pips — hybrid {G/U}, twobrid {2/W}, phyrexian {W/P}
#
# These have no SVG asset; symbol_renderer synthesizes them at render time from
# the mono glyph parts. The synthesis needs an SVG backend (the glyphs come from
# the IcoMoon SVGs), so the pixel-sampling tests skip where none is available —
# the documented graceful-degrade (the text-label fallback) covers that path.
# ---------------------------------------------------------------------------

from mtgai.rendering.colors import (  # noqa: E402
    MANA_COLORS,
    MANA_GENERIC_BG,
    MANA_GENERIC_FG,
)


def _has_svg_backend() -> bool:
    return symbol_renderer.svg_backend() in ("cairosvg", "pycairo")


def _color_present(img, rgb, tol=40) -> bool:
    """True if any pixel of ``img`` is within ``tol`` of ``rgb`` on every channel."""
    px = img.convert("RGB").load()
    w, h = img.size
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            r, g, b = px[x, y]
            if abs(r - rgb[0]) <= tol and abs(g - rgb[1]) <= tol and abs(b - rgb[2]) <= tol:
                return True
    return False


@pytest.mark.parametrize("symbol", ["G/U", "G/W", "R/W", "2/W", "W/P", "U/P"])
def test_compound_symbol_is_not_text_fallback(symbol):
    """A compound pip synthesizes a real split/phyrexian disc, not the gray
    text-label fallback (which would carry MANA_GENERIC_BG everywhere)."""
    if not _has_svg_backend():
        pytest.skip("no SVG backend for glyph rasterization")
    img = symbol_renderer._make_compound_mana_symbol(symbol, 200)
    assert img is not None
    assert img.size == (200, 200)


@pytest.mark.parametrize(
    ("symbol", "first", "second"),
    [
        ("G/U", "G", "U"),  # green upper-left, blue lower-right
        ("G/W", "G", "W"),
        ("R/W", "R", "W"),  # a wheel-wrap pair
    ],
)
def test_hybrid_both_half_disc_colors_present(symbol, first, second):
    """Both halves of a hybrid pip carry their own disc background color, in the
    written order (first → upper-left, second → lower-right)."""
    if not _has_svg_backend():
        pytest.skip("no SVG backend for glyph rasterization")
    img = symbol_renderer.get_mana_symbol(symbol, 200).convert("RGB")
    first_bg = MANA_COLORS[first]
    second_bg = MANA_COLORS[second]
    # Sample a representative point in each triangle (off the glyph centroid).
    assert _color_present(img.crop((10, 10, 90, 90)), first_bg), "first half bg missing"
    assert _color_present(img.crop((110, 110, 190, 190)), second_bg), "second half bg missing"


def test_twobrid_has_generic_and_color_halves():
    """{2/W}: generic-gray ground upper-left (the '2' numeral), white disc
    lower-right."""
    if not _has_svg_backend():
        pytest.skip("no SVG backend for glyph rasterization")
    img = symbol_renderer.get_mana_symbol("2/W", 200).convert("RGB")
    assert _color_present(img.crop((10, 10, 90, 90)), MANA_GENERIC_BG)
    assert _color_present(img.crop((110, 110, 190, 190)), MANA_COLORS["W"])


def test_phyrexian_is_single_colored_disc():
    """{W/P} is NOT split — a single colored disc with the phi glyph. The disc
    color fills both corners (no second color)."""
    if not _has_svg_backend():
        pytest.skip("no SVG backend for glyph rasterization")
    img = symbol_renderer.get_mana_symbol("W/P", 200).convert("RGB")
    white_bg = MANA_COLORS["W"]
    # Both upper-left and lower-right corners carry the white disc background.
    assert _color_present(img.crop((20, 20, 70, 70)), white_bg)
    assert _color_present(img.crop((130, 130, 180, 180)), white_bg)
    # The phi glyph's foreground color is present somewhere on the disc.
    assert _color_present(img, MANA_GENERIC_FG) or _color_present(img, (33, 28, 20))


def test_compound_symbol_caches():
    """A compound pip is cached like a mono symbol — repeat calls return the
    same Image object (the _mana_cache hit)."""
    if not _has_svg_backend():
        pytest.skip("no SVG backend for glyph rasterization")
    a = symbol_renderer.get_mana_symbol("G/U", 128)
    b = symbol_renderer.get_mana_symbol("G/U", 128)
    assert a is b


def test_compound_symbol_first_half_is_upper_left():
    """The FIRST written half occupies the UPPER-LEFT triangle (canonical MTG
    hybrid order; the cost string is already wheel-ordered upstream)."""
    if not _has_svg_backend():
        pytest.skip("no SVG backend for glyph rasterization")
    img = symbol_renderer.get_mana_symbol("R/G", 200).convert("RGB")
    # Red disc upper-left, green disc lower-right — not the reverse.
    assert _color_present(img.crop((10, 10, 80, 80)), MANA_COLORS["R"])
    assert _color_present(img.crop((120, 120, 190, 190)), MANA_COLORS["G"])
    assert not _color_present(img.crop((10, 10, 80, 80)), MANA_COLORS["G"], tol=20)


@pytest.mark.parametrize("bad", ["G/U/W", "G", "GU"])
def test_malformed_compound_returns_none(bad):
    """A non-two-part string falls through to None so get_mana_symbol degrades
    to the normal mono/fallback path (no crash)."""
    assert symbol_renderer._make_compound_mana_symbol(bad, 64) is None


def test_is_compound_symbol():
    assert symbol_renderer._is_compound_symbol("G/U")
    assert symbol_renderer._is_compound_symbol("2/W")
    assert symbol_renderer._is_compound_symbol("W/P")
    assert not symbol_renderer._is_compound_symbol("G")
    assert not symbol_renderer._is_compound_symbol("2")
